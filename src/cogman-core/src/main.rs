//! cogman-core — PID 1 init + package manager + process supervisor.
//!
//! When run as PID 1:
//!   cogman-core daemon          → full init: mount filesystems, run services, reap zombies
//!
//! When run as a normal process:
//!   cogman-core daemon          → supervisor-only (no mounts, no halt)
//!   cogman-core svc list|…      → control running daemon via Unix socket
//!   cogman-core pkg install|…   → native package management
//!   cogman-core validate <toml> → validate a package manifest
//!
//! Kernel cmdline: init=/usr/bin/cogman-core
//! Service dir:    /etc/cogman/services/

mod init;
mod pkg;
mod svc;
mod ctl;

use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::thread;
use std::time::Duration;

use clap::{Parser, Subcommand};
use init::{SHUTDOWN, is_pid1, become_subreaper, mount_essential, setup_signals,
           system_halt, print_init_banner, kmsg};
use ctl::{send, parse, SOCK_PATH};
use pkg::Installer;
use std::sync::atomic::Ordering;

// ── CLI ───────────────────────────────────────────────────────────────────

#[derive(Parser)]
#[command(
    name    = "cogman-core",
    version = "1.0.0",
    about   = "COGMAN — PID 1 init, package manager, and process supervisor",
)]
struct Cli {
    #[arg(long, default_value = SOCK_PATH, env = "COGMAN_SOCK")]
    sock: PathBuf,

    #[arg(long, short = 'j')]
    json: bool,

    #[command(subcommand)]
    cmd: TopCmd,
}

#[derive(Subcommand)]
enum TopCmd {
    /// Run as supervisor/init daemon. Automatically enters PID 1 mode if pid==1.
    Daemon {
        #[arg(long, default_value = "/etc/cogman/services", env = "COGMAN_SERVICES")]
        services: PathBuf,
        /// Force halt/poweroff when all services exit (PID 1 only).
        #[arg(long)]
        halt_on_exit: bool,
        /// Reboot instead of halt on exit (PID 1 only).
        #[arg(long)]
        reboot_on_exit: bool,
    },

    /// Control the running daemon via Unix socket.
    #[command(subcommand)]
    Svc(SvcCmd),

    /// Native package management.
    #[command(subcommand)]
    Pkg(PkgCmd),

    /// Validate a package manifest without installing.
    Validate { toml: PathBuf },

    /// Reload services (send SIGHUP to daemon).
    Reload,
}

#[derive(Subcommand)]
enum SvcCmd {
    List,
    Status { name: String },
    Start  { name: String },
    Stop   { name: String },
    Restart{ name: String },
    Ping,
    /// Enable a service (symlink into services dir).
    Enable { name: String, #[arg(long, default_value = "/etc/cogman/services")] services: PathBuf },
    /// Disable a service.
    Disable{ name: String, #[arg(long, default_value = "/etc/cogman/services")] services: PathBuf },
}

#[derive(Subcommand)]
enum PkgCmd {
    Install { toml: PathBuf, #[arg(long)] root: Option<PathBuf> },
    Remove  { name: String },
    Upgrade { toml: PathBuf, #[arg(long)] root: Option<PathBuf> },
    List,
    Info    { name: String },
}

// ── Entry point ───────────────────────────────────────────────────────────

fn main() {
    let pid = std::process::id();
    let pid1 = is_pid1();

    // Always become a subreaper so we reap all descendants
    become_subreaper();

    let cli = Cli::parse();

    match cli.cmd {
        TopCmd::Daemon { services, halt_on_exit, reboot_on_exit } => {
            run_daemon(&services, &cli.sock, pid1, halt_on_exit, reboot_on_exit);
        }
        TopCmd::Svc(cmd)        => run_svc(cmd, &cli.sock, cli.json),
        TopCmd::Pkg(cmd)        => run_pkg(cmd, cli.json),
        TopCmd::Validate { toml } => run_validate(&toml),
        TopCmd::Reload          => {
            // Send SIGHUP to daemon PID (stored in pidfile)
            if let Ok(pid_str) = std::fs::read_to_string("/run/cogman.pid") {
                if let Ok(p) = pid_str.trim().parse::<i32>() {
                    unsafe { libc::kill(p, libc::SIGHUP); }
                    println!("Reload signal sent to pid {p}");
                }
            } else {
                eprintln!("cogman daemon not found (no /run/cogman.pid)");
            }
        }
    }
}

// ── Daemon ────────────────────────────────────────────────────────────────

fn run_daemon(services: &Path, sock: &Path, pid1: bool, halt_on_exit: bool, reboot_on_exit: bool) {
    let pid = std::process::id();

    // Write pidfile
    let _ = std::fs::write("/run/cogman.pid", format!("{pid}\n"));

    setup_signals();

    if pid1 {
        print_init_banner(pid);
        kmsg(&format!("cogman-core: PID 1 init starting (services={})", services.display()));
        mount_essential();
        kmsg("cogman-core: filesystems mounted");
    } else {
        eprintln!("  ╔════════════════════════════════════════════╗");
        eprintln!("  ║  COGMAN CORE  —  Process Supervisor        ║");
        eprintln!("  ║  pid={:<38} ║", pid);
        eprintln!("  ╚════════════════════════════════════════════╝");
    }

    let sup = Arc::new(svc::Supervisor::new());
    sup.load_dir(services);

    // Control socket thread
    let sup_ctl  = Arc::clone(&sup);
    let sock_buf = sock.to_path_buf();
    thread::spawn(move || ctl::serve(&sock_buf, sup_ctl));

    // Main supervision loop + shutdown watcher
    let sup_loop = Arc::clone(&sup);
    let shutdown_watcher = thread::spawn(move || {
        loop {
            if SHUTDOWN.load(Ordering::SeqCst) { break; }
            thread::sleep(Duration::from_millis(100));
        }
        eprintln!("[cogman] shutdown signal received — stopping all services");
        sup_loop.stop_all();
    });

    eprintln!("[cogman] supervision loop running");
    sup.run();

    // If we reach here, run() returned (only on shutdown)
    let _ = shutdown_watcher.join();

    if pid1 && (halt_on_exit || reboot_on_exit) {
        eprintln!("[cogman] all services stopped — halting system");
        system_halt(reboot_on_exit);
    }

    // Remove pidfile
    let _ = std::fs::remove_file("/run/cogman.pid");
}

// ── Service control ───────────────────────────────────────────────────────

fn run_svc(cmd: SvcCmd, sock: &Path, json: bool) {
    let req = match &cmd {
        SvcCmd::List          => if json { "LIST_JSON".into() } else { "LIST".into() },
        SvcCmd::Status{name}  => format!("STATUS {name}"),
        SvcCmd::Start {name}  => format!("START {name}"),
        SvcCmd::Stop  {name}  => format!("STOP {name}"),
        SvcCmd::Restart{name} => format!("RESTART {name}"),
        SvcCmd::Ping          => "PING".into(),
        SvcCmd::Enable { name, services } => {
            // symlink /etc/cogman/services/<name>.service if found
            let src = PathBuf::from(format!("/etc/cogman/services.available/{name}.service"));
            let dst = services.join(format!("{name}.service"));
            if src.exists() {
                let _ = std::os::unix::fs::symlink(&src, &dst);
                println!("enabled: {name}");
            } else {
                eprintln!("service definition not found: {}", src.display());
            }
            return;
        }
        SvcCmd::Disable { name, services } => {
            let dst = services.join(format!("{name}.service"));
            let _ = std::fs::remove_file(&dst);
            println!("disabled: {name}");
            return;
        }
    };

    match send(sock, &req) {
        Err(e) => {
            eprintln!("[cogman] daemon unreachable: {e}");
            eprintln!("  hint: start with 'cogman-core daemon'");
            std::process::exit(1);
        }
        Ok(raw) => match parse(&raw) {
            Ok(p)  => print!("{p}"),
            Err(e) => { eprintln!("[cogman] {e}"); std::process::exit(1); }
        }
    }
}

// ── Package management ────────────────────────────────────────────────────

fn run_pkg(cmd: PkgCmd, json: bool) {
    match cmd {
        PkgCmd::Install { toml, root } => {
            let mut inst = open_installer(root.as_deref());
            match inst.install(&toml) {
                Ok(r) => {
                    if json { println!("{}", serde_json::to_string_pretty(&r).unwrap_or_default()); }
                    else    { println!("[cogman] installed: {}/{} v{}", r.category, r.name, r.version); }
                }
                Err(e) => { eprintln!("[cogman] install error: {e}"); std::process::exit(1); }
            }
        }
        PkgCmd::Remove { name } => {
            let mut inst = open_installer(None);
            match inst.remove(&name) {
                Ok(()) => println!("[cogman] removed: {name}"),
                Err(e) => { eprintln!("[cogman] remove error: {e}"); std::process::exit(1); }
            }
        }
        PkgCmd::Upgrade { toml, root } => {
            let mut inst = open_installer(root.as_deref());
            match inst.upgrade(&toml) {
                Ok(r) => println!("[cogman] upgraded: {} v{}", r.name, r.version),
                Err(e) => { eprintln!("[cogman] upgrade error: {e}"); std::process::exit(1); }
            }
        }
        PkgCmd::List => {
            let inst = open_installer(None);
            if json {
                let db = pkg::PackageDb::system().unwrap_or_else(|_| unreachable!());
                println!("{}", serde_json::to_string_pretty(db.list()).unwrap_or_default());
            } else {
                let pkgs = inst.list();
                if pkgs.is_empty() { println!("[cogman] no packages installed"); }
                else { for p in &pkgs { println!("  {p}"); } }
            }
        }
        PkgCmd::Info { name } => {
            let inst = open_installer(None);
            match inst.info(&name) {
                Some(r) => {
                    if json { println!("{}", serde_json::to_string_pretty(r).unwrap_or_default()); }
                    else {
                        println!("name:     {}", r.name);
                        println!("version:  {}", r.version);
                        println!("category: {}", r.category);
                        println!("root:     {}", r.install_root);
                        println!("files:    {}", r.files.len());
                    }
                }
                None => { eprintln!("[cogman] not installed: {name}"); std::process::exit(1); }
            }
        }
    }
}

fn run_validate(toml: &Path) {
    match pkg::PackageMeta::load(toml) {
        Ok(m) => {
            println!("[cogman] OK  {}/{} v{}", m.identity.category, m.identity.name, m.identity.version);
            println!("  build:  {:?} ({} steps)", m.build.system, m.build.steps.len());
            println!("  deps:   {:?}", m.identity.depends.build);
            println!("  write:  {:?}", m.policy.filesystem.write);
        }
        Err(e) => { eprintln!("[cogman] invalid: {e}"); std::process::exit(1); }
    }
}

fn open_installer(root: Option<&Path>) -> Installer {
    Installer::new(root).unwrap_or_else(|e| {
        eprintln!("[cogman] cannot open package db: {e}");
        std::process::exit(1);
    })
}
