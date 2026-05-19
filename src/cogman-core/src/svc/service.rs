//! Service definition — parsed from /etc/cogman/services/*.service
//!
//! File format (INI-like):
//!
//! ```ini
//! [service]
//! name    = my-app
//! command = /usr/bin/my-app --flag
//! type    = process          # process | oneshot | forking
//! restart = on-failure       # never | on-failure | always
//! restart_delay = 2          # seconds before restart
//! depends = other-svc, db    # comma-separated
//!
//! [env]
//! MY_VAR = value
//!
//! [health]
//! type     = tcp             # tcp | http | exec
//! port     = 8080
//! interval = 10
//! timeout  = 3
//! retries  = 3
//!
//! [policy]
//! allow_read  = /usr, /etc
//! allow_write = /var/run/my-app
//! ```

use std::collections::HashMap;
use std::fs;
use std::path::Path;

// ── Enums ────────────────────────────────────────────────────────────────

#[derive(Debug, Clone, PartialEq)]
pub enum ServiceType { Process, Oneshot, Forking }

#[derive(Debug, Clone, PartialEq)]
pub enum RestartPolicy { Never, OnFailure, Always }

#[derive(Debug, Clone)]
pub enum HealthProbe {
    Tcp  { port: u16 },
    Http { port: u16, path: String },
    Exec { command: String },
}

#[derive(Debug, Clone)]
pub struct HealthConfig {
    pub probe:    HealthProbe,
    pub interval: u64,
    pub timeout:  u64,
    pub retries:  u32,
}

// ── ServiceDef ───────────────────────────────────────────────────────────

#[derive(Debug, Clone)]
pub struct ServiceDef {
    pub name:          String,
    pub command:       String,
    pub svc_type:      ServiceType,
    pub restart:       RestartPolicy,
    pub restart_delay: u64,
    pub depends:       Vec<String>,
    pub env:           HashMap<String, String>,
    pub health:        Option<HealthConfig>,
    pub allow_read:    Vec<String>,
    pub allow_write:   Vec<String>,
}

impl Default for ServiceDef {
    fn default() -> Self {
        ServiceDef {
            name:          String::new(),
            command:       String::new(),
            svc_type:      ServiceType::Process,
            restart:       RestartPolicy::Never,
            restart_delay: 1,
            depends:       Vec::new(),
            env:           HashMap::new(),
            health:        None,
            allow_read:    Vec::new(),
            allow_write:   Vec::new(),
        }
    }
}

impl ServiceDef {
    /// Load all *.service files from a directory.
    pub fn load_dir(dir: &Path) -> Vec<ServiceDef> {
        let Ok(rd) = fs::read_dir(dir) else {
            eprintln!("[cogman] services dir not found: {}", dir.display());
            return Vec::new();
        };
        let mut paths: Vec<_> = rd.filter_map(|e| e.ok())
            .filter(|e| e.path().extension().map_or(false, |x| x == "service"))
            .map(|e| e.path())
            .collect();
        paths.sort();

        let mut svcs = Vec::new();
        for p in paths {
            match Self::parse_file(&p) {
                Ok(s)  => { eprintln!("[cogman] loaded service '{}'", s.name); svcs.push(s); }
                Err(e) => eprintln!("[cogman] skip {} — {e}", p.display()),
            }
        }
        svcs
    }

    pub fn parse_file(path: &Path) -> Result<ServiceDef, String> {
        let src = fs::read_to_string(path).map_err(|e| format!("read: {e}"))?;
        Self::parse_str(&src)
    }

    pub fn parse_str(src: &str) -> Result<ServiceDef, String> {
        let mut svc = ServiceDef::default();
        let mut section = String::new();

        for raw in src.lines() {
            let line = raw.trim();
            if line.is_empty() || line.starts_with('#') { continue; }
            if line.starts_with('[') && line.ends_with(']') {
                section = line[1..line.len()-1].to_lowercase();
                continue;
            }
            let (k, v) = line.split_once('=')
                .map(|(a,b)| (a.trim(), b.trim()))
                .ok_or_else(|| format!("bad line: {line}"))?;
            match section.as_str() {
                "service" => svc_kv(&mut svc, k, v)?,
                "env"     => { svc.env.insert(k.into(), v.into()); }
                "health"  => health_kv(&mut svc, k, v)?,
                "policy"  => policy_kv(&mut svc, k, v)?,
                _         => {}
            }
        }

        if svc.name.is_empty()    { return Err("missing name".into()); }
        if svc.command.is_empty() { return Err("missing command".into()); }
        Ok(svc)
    }
}

fn svc_kv(s: &mut ServiceDef, k: &str, v: &str) -> Result<(), String> {
    match k {
        "name"          => s.name = v.into(),
        "command"       => s.command = v.into(),
        "type"          => s.svc_type = match v {
            "oneshot" => ServiceType::Oneshot,
            "forking" => ServiceType::Forking,
            _         => ServiceType::Process,
        },
        "restart"       => s.restart = match v {
            "always"     => RestartPolicy::Always,
            "on-failure" => RestartPolicy::OnFailure,
            _            => RestartPolicy::Never,
        },
        "restart_delay" => s.restart_delay = v.parse().unwrap_or(1),
        "depends"       => s.depends = v.split(',').map(str::trim).filter(|x| !x.is_empty()).map(String::from).collect(),
        _ => {}
    }
    Ok(())
}

fn health_kv(s: &mut ServiceDef, k: &str, v: &str) -> Result<(), String> {
    let hc = s.health.get_or_insert(HealthConfig {
        probe:    HealthProbe::Exec { command: "true".into() },
        interval: 10,
        timeout:  3,
        retries:  3,
    });
    match k {
        "type" => hc.probe = match v {
            "tcp"  => HealthProbe::Tcp  { port: 80 },
            "http" => HealthProbe::Http { port: 80, path: "/".into() },
            _      => HealthProbe::Exec { command: "true".into() },
        },
        "port" => match &mut hc.probe {
            HealthProbe::Tcp  { port } | HealthProbe::Http { port, .. } => *port = v.parse().unwrap_or(80),
            _ => {}
        },
        "path"     => if let HealthProbe::Http { path, .. } = &mut hc.probe { *path = v.into(); },
        "command"  => if let HealthProbe::Exec { command }   = &mut hc.probe { *command = v.into(); },
        "interval" => hc.interval = v.parse().unwrap_or(10),
        "timeout"  => hc.timeout  = v.parse().unwrap_or(3),
        "retries"  => hc.retries  = v.parse().unwrap_or(3),
        _ => {}
    }
    Ok(())
}

fn policy_kv(s: &mut ServiceDef, k: &str, v: &str) -> Result<(), String> {
    let paths: Vec<String> = v.split(',').map(str::trim).filter(|x| !x.is_empty()).map(String::from).collect();
    match k {
        "allow_read"  => s.allow_read  = paths,
        "allow_write" => s.allow_write = paths,
        _ => {}
    }
    Ok(())
}
