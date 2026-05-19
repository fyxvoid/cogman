//! Process supervisor — spawn, watch, restart, heal services.
//!
//! Architecture:
//!   - `Supervisor` holds all `ServiceEntry` items behind a `Mutex<Vec<...>>`
//!   - A single `run()` loop runs at 200ms tick: reap dead, tick restarts,
//!     start pending, run health checks
//!   - A control thread binds a Unix socket (`/run/cogman.sock`)

pub mod service;

use service::{ServiceDef, ServiceType, RestartPolicy, HealthProbe, HealthConfig};

use std::io::{Read, Write};
use std::net::TcpStream;
use std::os::unix::process::CommandExt;
use std::path::Path;
use std::process::Command;
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

// ── Service state ────────────────────────────────────────────────────────

#[derive(Debug, Clone, PartialEq)]
pub enum State {
    Pending,
    Starting,
    Running,
    Stopping,
    Stopped,
    Restarting { at: Instant },
    Failed,
    Done,
}

pub struct ServiceEntry {
    pub def:       ServiceDef,
    pub state:     State,
    pub pid:       Option<u32>,
    pub started:   Option<Instant>,
    pub restarts:  u32,
    pub exit_code: Option<i32>,
    pub hfails:    u32,
}

impl ServiceEntry {
    fn new(def: ServiceDef) -> Self {
        ServiceEntry { def, state: State::Pending, pid: None,
                       started: None, restarts: 0, exit_code: None, hfails: 0 }
    }
}

// ── Supervisor ────────────────────────────────────────────────────────────

pub struct Supervisor {
    pub services: Arc<Mutex<Vec<ServiceEntry>>>,
}

impl Supervisor {
    pub fn new() -> Self {
        Supervisor { services: Arc::new(Mutex::new(Vec::new())) }
    }

    pub fn load_dir(&self, dir: &Path) {
        let defs = ServiceDef::load_dir(dir);
        let count = defs.len();
        let mut svcs = self.services.lock().unwrap();
        for d in defs { svcs.push(ServiceEntry::new(d)); }
        eprintln!("[cogman] loaded {} service(s)", count);
    }

    /// Main supervision loop — blocks forever.
    pub fn run(&self) {
        self.start_ready();
        loop {
            self.reap();
            self.tick_restarts();
            self.start_ready();
            self.health_checks();
            std::thread::sleep(Duration::from_millis(250));
        }
    }

    // ── Spawn ─────────────────────────────────────────────────────────────

    fn spawn(entry: &mut ServiceEntry) {
        let def = &entry.def;
        let mut cmd = Command::new("/bin/sh");
        cmd.arg("-c").arg(&def.command);
        for (k, v) in &def.env { cmd.env(k, v); }

        match cmd.spawn() {
            Ok(child) => {
                eprintln!("[cogman] started '{}' pid={}", def.name, child.id());
                entry.pid     = Some(child.id());
                entry.state   = State::Running;
                entry.started = Some(Instant::now());
                std::mem::forget(child);
            }
            Err(e) => {
                eprintln!("[cogman] failed to start '{}': {e}", def.name);
                entry.state = State::Failed;
            }
        }
    }

    // ── Reap dead ─────────────────────────────────────────────────────────

    fn reap(&self) {
        let mut svcs = self.services.lock().unwrap();
        for e in svcs.iter_mut() {
            let Some(pid) = e.pid else { continue };
            if !matches!(e.state, State::Running | State::Starting) { continue; }
            let mut status = 0i32;
            let ret = unsafe { libc::waitpid(pid as libc::pid_t, &mut status, libc::WNOHANG) };
            if ret == 0 { continue; }
            let code = if libc::WIFEXITED(status) { libc::WEXITSTATUS(status) }
                       else if libc::WIFSIGNALED(status) { -(libc::WTERMSIG(status)) }
                       else { -1 };
            eprintln!("[cogman] '{}' exited (pid={pid} code={code})", e.def.name);
            e.pid       = None;
            e.exit_code = Some(code);
            e.hfails    = 0;
            Self::apply_restart(e, code);
        }
    }

    fn apply_restart(e: &mut ServiceEntry, code: i32) {
        if e.def.svc_type == ServiceType::Oneshot {
            e.state = if code == 0 { State::Done } else { State::Failed };
            return;
        }
        if e.def.svc_type == ServiceType::Forking { e.state = State::Done; return; }
        if matches!(e.state, State::Stopping | State::Stopped) { e.state = State::Stopped; return; }
        let restart = match e.def.restart {
            RestartPolicy::Always    => true,
            RestartPolicy::OnFailure => code != 0,
            RestartPolicy::Never     => false,
        };
        if restart {
            let delay = Duration::from_secs(e.def.restart_delay);
            eprintln!("[cogman] restarting '{}' in {}s", e.def.name, e.def.restart_delay);
            e.state = State::Restarting { at: Instant::now() + delay };
        } else {
            e.state = State::Stopped;
        }
    }

    fn tick_restarts(&self) {
        let mut svcs = self.services.lock().unwrap();
        let now = Instant::now();
        for e in svcs.iter_mut() {
            if let State::Restarting { at } = e.state {
                if now >= at { e.restarts += 1; Self::spawn(e); }
            }
        }
    }

    fn start_ready(&self) {
        let mut svcs = self.services.lock().unwrap();
        let satisfied: Vec<String> = svcs.iter()
            .filter(|e| matches!(e.state, State::Running | State::Done))
            .map(|e| e.def.name.clone())
            .collect();
        for e in svcs.iter_mut() {
            if e.state != State::Pending || e.started.is_some() { continue; }
            if e.def.depends.iter().all(|d| satisfied.contains(d)) {
                Self::spawn(e);
            }
        }
    }

    fn health_checks(&self) {
        let mut svcs = self.services.lock().unwrap();
        for e in svcs.iter_mut() {
            if e.state != State::Running { continue; }
            let Some(hc) = &e.def.health.clone() else { continue };
            if probe_ok(&hc.probe, hc.timeout) {
                e.hfails = 0;
            } else {
                e.hfails += 1;
                eprintln!("[cogman] health fail '{}' ({}/{})", e.def.name, e.hfails, hc.retries);
                if e.hfails >= hc.retries {
                    if let Some(pid) = e.pid {
                        unsafe { libc::kill(pid as libc::pid_t, libc::SIGTERM); }
                    }
                    e.hfails = 0;
                }
            }
        }
    }

    // ── Control ops ───────────────────────────────────────────────────────

    pub fn ctl_stop(&self, name: &str) -> Result<(), String> {
        let mut svcs = self.services.lock().unwrap();
        let e = svcs.iter_mut().find(|e| e.def.name == name)
            .ok_or_else(|| format!("service not found: {name}"))?;
        if let Some(pid) = e.pid { unsafe { libc::kill(pid as libc::pid_t, libc::SIGTERM); } }
        e.pid   = None;
        e.state = State::Stopped;
        Ok(())
    }

    pub fn ctl_start(&self, name: &str) -> Result<(), String> {
        let mut svcs = self.services.lock().unwrap();
        let e = svcs.iter_mut().find(|e| e.def.name == name)
            .ok_or_else(|| format!("service not found: {name}"))?;
        e.state   = State::Pending;
        e.started = None;
        Ok(())
    }

    pub fn ctl_restart(&self, name: &str) -> Result<(), String> {
        drop(self.ctl_stop(name));
        self.ctl_start(name)
    }

    pub fn ctl_status(&self, name: &str) -> Result<String, String> {
        let svcs = self.services.lock().unwrap();
        let e = svcs.iter().find(|e| e.def.name == name)
            .ok_or_else(|| format!("service not found: {name}"))?;
        Ok(format_status(e))
    }

    pub fn ctl_list(&self) -> String {
        let svcs = self.services.lock().unwrap();
        if svcs.is_empty() { return "no services loaded\n".into(); }
        let mut out = format!("{} service(s):\n", svcs.len());
        for e in svcs.iter() {
            out.push_str(&format!(
                "  {:24} {:12} pid={}\n",
                e.def.name, state_str(&e.state),
                e.pid.map_or("-".into(), |p| p.to_string()),
            ));
        }
        out
    }

    /// Send SIGTERM to all running services and wait for them to exit.
    pub fn stop_all(&self) {
        let mut svcs = self.services.lock().unwrap();
        for e in svcs.iter_mut() {
            if let Some(pid) = e.pid {
                eprintln!("[cogman] stopping '{}' (pid={pid})", e.def.name);
                unsafe { libc::kill(pid as libc::pid_t, libc::SIGTERM); }
                e.state = State::Stopping;
            }
        }
        drop(svcs);
        // Wait up to 10s for all to exit
        let deadline = std::time::Instant::now() + std::time::Duration::from_secs(10);
        loop {
            let any_running = {
                let svcs = self.services.lock().unwrap();
                svcs.iter().any(|e| e.pid.is_some())
            };
            if !any_running { break; }
            if std::time::Instant::now() > deadline {
                eprintln!("[cogman] timeout waiting for services — sending SIGKILL");
                let svcs = self.services.lock().unwrap();
                for e in svcs.iter() {
                    if let Some(pid) = e.pid {
                        unsafe { libc::kill(pid as libc::pid_t, libc::SIGKILL); }
                    }
                }
                break;
            }
            std::thread::sleep(std::time::Duration::from_millis(200));
        }
        eprintln!("[cogman] all services stopped");
    }

    pub fn ctl_list_json(&self) -> String {
        let svcs = self.services.lock().unwrap();
        let items: Vec<serde_json::Value> = svcs.iter().map(|e| {
            serde_json::json!({
                "name":    e.def.name,
                "state":   state_str(&e.state),
                "pid":     e.pid,
                "restarts": e.restarts,
                "exit_code": e.exit_code,
            })
        }).collect();
        serde_json::to_string_pretty(&items).unwrap_or_default()
    }
}

// ── Health probe ──────────────────────────────────────────────────────────

fn probe_ok(probe: &HealthProbe, timeout: u64) -> bool {
    let t = Duration::from_secs(timeout);
    match probe {
        HealthProbe::Tcp { port } => {
            TcpStream::connect_timeout(&format!("127.0.0.1:{port}").parse().unwrap(), t).is_ok()
        }
        HealthProbe::Http { port, path } => {
            let Ok(mut s) = TcpStream::connect_timeout(&format!("127.0.0.1:{port}").parse().unwrap(), t) else { return false };
            let _ = s.write_all(format!("GET {path} HTTP/1.0\r\nHost: localhost\r\n\r\n").as_bytes());
            let mut resp = String::new();
            let _ = s.read_to_string(&mut resp);
            resp.split_whitespace().nth(1).and_then(|s| s.parse::<u16>().ok()).map_or(false, |c| c < 400)
        }
        HealthProbe::Exec { command } => {
            Command::new("/bin/sh").arg("-c").arg(command)
                .stdin(std::process::Stdio::null())
                .stdout(std::process::Stdio::null())
                .stderr(std::process::Stdio::null())
                .status().map_or(false, |s| s.success())
        }
    }
}

fn state_str(s: &State) -> &'static str {
    match s {
        State::Pending        => "pending",
        State::Starting       => "starting",
        State::Running        => "running",
        State::Stopping       => "stopping",
        State::Stopped        => "stopped",
        State::Restarting {..} => "restarting",
        State::Failed         => "failed",
        State::Done           => "done",
    }
}

fn format_status(e: &ServiceEntry) -> String {
    format!(
        "name:      {}\nstate:     {}\npid:       {}\ntype:      {:?}\nrestart:   {:?}\nrestarts:  {}\nexit_code: {}\n",
        e.def.name, state_str(&e.state),
        e.pid.map_or("-".into(), |p| p.to_string()),
        e.def.svc_type, e.def.restart,
        e.restarts, e.exit_code.unwrap_or(0),
    )
}
