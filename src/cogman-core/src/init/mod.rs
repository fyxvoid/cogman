//! PID 1 / init mode for cogman-core.
//!
//! When cogman-core detects it is running as PID 1, it switches into
//! full init mode:
//!   1. Sets itself as subreaper for all orphan processes
//!   2. Mounts essential virtual filesystems (proc, sys, devtmpfs)
//!   3. Sets up signal handlers (SIGCHLD, SIGTERM, SIGINT, SIGHUP)
//!   4. Logs to /dev/kmsg if available
//!   5. Runs the supervision loop forever
//!   6. On SIGTERM/SIGINT: sends SIGTERM to all services, waits, then halts
//!
//! When not PID 1 (normal invocation), only the subreaper bit is set.

use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::time::Duration;
use std::fs;
use std::io::Write;
use std::os::unix::fs::PermissionsExt;

// Global shutdown flag set by signal handler
pub static SHUTDOWN: AtomicBool = AtomicBool::new(false);

/// Returns true if this process is PID 1.
pub fn is_pid1() -> bool {
    std::process::id() == 1
}

/// Set this process as the subreaper for orphaned child processes.
/// Even when not PID 1, this ensures we reap all descendants.
pub fn become_subreaper() {
    unsafe {
        libc::prctl(libc::PR_SET_CHILD_SUBREAPER, 1u64, 0u64, 0u64, 0u64);
    }
}

/// Mount essential virtual filesystems needed in a minimal Linux environment.
/// Only called when running as PID 1.
pub fn mount_essential() {
    let mounts = [
        ("proc",     "/proc",     "proc",     libc::MS_NOSUID | libc::MS_NODEV | libc::MS_NOEXEC),
        ("sysfs",    "/sys",      "sysfs",    libc::MS_NOSUID | libc::MS_NODEV | libc::MS_NOEXEC),
        ("devtmpfs", "/dev",      "devtmpfs", libc::MS_NOSUID | libc::MS_RELATIME),
        ("devpts",   "/dev/pts",  "devpts",   libc::MS_NOSUID | libc::MS_NOEXEC),
        ("tmpfs",    "/dev/shm",  "tmpfs",    libc::MS_NOSUID | libc::MS_NODEV),
        ("tmpfs",    "/run",      "tmpfs",    libc::MS_NOSUID | libc::MS_NODEV),
        ("tmpfs",    "/tmp",      "tmpfs",    libc::MS_NOSUID | libc::MS_NODEV),
    ];

    for (source, target, fstype, flags) in mounts {
        // Skip if already mounted (check /proc/mounts for target)
        if is_mounted(target) { continue; }

        // Ensure mountpoint exists
        let _ = fs::create_dir_all(target);

        let src  = std::ffi::CString::new(source).unwrap();
        let tgt  = std::ffi::CString::new(target).unwrap();
        let fst  = std::ffi::CString::new(fstype).unwrap();
        let data = std::ffi::CString::new("").unwrap();

        let ret = unsafe {
            libc::mount(src.as_ptr(), tgt.as_ptr(), fst.as_ptr(), flags as u64, data.as_ptr() as *const libc::c_void)
        };

        if ret == 0 {
            kmsg(&format!("cogman: mounted {target} ({fstype})"));
        } else {
            let err = std::io::Error::last_os_error();
            kmsg(&format!("cogman: warn: mount {target}: {err}"));
        }
    }

    // /dev/null, /dev/console, /dev/zero — best effort
    for (path, major, minor, mode) in [
        ("/dev/null",    1u32, 3u32, 0o666u32),
        ("/dev/zero",    1,    5,    0o666),
        ("/dev/console", 5,    1,    0o600),
        ("/dev/random",  1,    8,    0o444),
        ("/dev/urandom", 1,    9,    0o444),
    ] {
        if !std::path::Path::new(path).exists() {
            let cpath = std::ffi::CString::new(path).unwrap();
            let dev   = unsafe { libc::makedev(major, minor) };
            unsafe { libc::mknod(cpath.as_ptr(), libc::S_IFCHR | mode, dev); }
        }
    }
}

/// Install signal handlers.
pub fn setup_signals() {
    unsafe {
        // SIGTERM → graceful shutdown
        libc::signal(libc::SIGTERM, sigterm_handler as libc::sighandler_t);
        // SIGINT  → graceful shutdown
        libc::signal(libc::SIGINT,  sigterm_handler as libc::sighandler_t);
        // SIGCHLD → ignored here; we poll with waitpid in the supervisor loop
        libc::signal(libc::SIGCHLD, libc::SIG_DFL);
        // SIGHUP  → reload (set flag for future use)
        libc::signal(libc::SIGHUP,  libc::SIG_IGN);
    }
}

extern "C" fn sigterm_handler(_: libc::c_int) {
    SHUTDOWN.store(true, Ordering::SeqCst);
}

/// Perform system halt after all services have exited.
/// Only called when running as PID 1.
pub fn system_halt(reboot: bool) {
    kmsg("cogman: initiating system halt");

    // Sync filesystems
    unsafe { libc::sync(); }

    // Unmount filesystems in reverse order
    for target in ["/tmp", "/run", "/dev/shm", "/dev/pts", "/dev", "/sys", "/proc"] {
        if is_mounted(target) {
            let ct = std::ffi::CString::new(target).unwrap();
            unsafe { libc::umount2(ct.as_ptr(), libc::MNT_DETACH); }
        }
    }

    let cmd = if reboot { libc::LINUX_REBOOT_CMD_RESTART } else { libc::LINUX_REBOOT_CMD_POWER_OFF };
    unsafe {
        libc::reboot(cmd);
    }
}

/// Write a message to /dev/kmsg (kernel ring buffer) for early-boot visibility.
pub fn kmsg(msg: &str) {
    if let Ok(mut f) = fs::OpenOptions::new().write(true).open("/dev/kmsg") {
        let _ = writeln!(f, "<6>{}",  msg); // priority 6 = INFO
    } else {
        eprintln!("{msg}");
    }
}

/// Print the PID 1 banner.
pub fn print_init_banner(pid: u32) {
    eprintln!();
    eprintln!("  ╔══════════════════════════════════════════════════════════╗");
    eprintln!("  ║   COGMAN INIT  —  Linux userland controller + supervisor ║");
    eprintln!("  ║   PID 1 — all your processes belong to us               ║");
    eprintln!("  ║   pid={:<52} ║", pid);
    eprintln!("  ╚══════════════════════════════════════════════════════════╝");
    eprintln!();
}

// ── Helpers ───────────────────────────────────────────────────────────────

fn is_mounted(target: &str) -> bool {
    let Ok(mounts) = fs::read_to_string("/proc/mounts") else { return false };
    mounts.lines().any(|l| l.split_whitespace().nth(1) == Some(target))
}
