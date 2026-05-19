//! Unix-socket control protocol.
//!
//! Protocol: newline-terminated ASCII frames.
//!   Request:  "<VERB> [arg]\n"
//!   Response: "OK\n<payload>" | "ERR <msg>\n"
//!
//! Verbs: PING LIST STATUS START STOP RESTART LIST_JSON

use std::io::{BufRead, BufReader, Write};
use std::os::unix::net::{UnixListener, UnixStream};
use std::path::Path;
use std::sync::Arc;
use std::time::Duration;

use crate::svc::Supervisor;

pub const SOCK_PATH: &str = "/run/cogman.sock";

// ── Server ────────────────────────────────────────────────────────────────

pub fn serve(sock: &Path, sup: Arc<Supervisor>) {
    let _ = std::fs::remove_file(sock);
    let listener = match UnixListener::bind(sock) {
        Ok(l)  => l,
        Err(e) => { eprintln!("[cogman/ctl] bind {}: {e}", sock.display()); return; }
    };
    eprintln!("[cogman/ctl] socket ready: {}", sock.display());
    for stream in listener.incoming() {
        if let Ok(s) = stream { handle(s, Arc::clone(&sup)); }
    }
}

fn handle(stream: UnixStream, sup: Arc<Supervisor>) {
    let Ok(mut writer) = stream.try_clone() else { return };
    let reader = BufReader::new(stream);
    for line in reader.lines() {
        let Ok(line) = line else { break };
        let resp = dispatch(line.trim(), &sup);
        let _ = writer.write_all(resp.as_bytes());
    }
}

fn dispatch(cmd: &str, sup: &Supervisor) -> String {
    let mut parts = cmd.splitn(2, ' ');
    let verb = parts.next().unwrap_or("").to_ascii_uppercase();
    let arg  = parts.next().unwrap_or("").trim();
    match verb.as_str() {
        "PING"      => "OK\npong\n".into(),
        "LIST"      => format!("OK\n{}", sup.ctl_list()),
        "LIST_JSON" => format!("OK\n{}", sup.ctl_list_json()),
        "STATUS"    => match_arg(arg, "STATUS",  |a| sup.ctl_status(a)),
        "START"     => match_arg(arg, "START",   |a| sup.ctl_start(a).map(|_| format!("started {a}\n"))),
        "STOP"      => match_arg(arg, "STOP",    |a| sup.ctl_stop(a).map(|_| format!("stopped {a}\n"))),
        "RESTART"   => match_arg(arg, "RESTART", |a| sup.ctl_restart(a).map(|_| format!("restarted {a}\n"))),
        other       => format!("ERR unknown command: {other}\n"),
    }
}

fn match_arg<F: Fn(&str) -> Result<String, String>>(arg: &str, verb: &str, f: F) -> String {
    if arg.is_empty() { return format!("ERR {verb} requires a service name\n"); }
    match f(arg) {
        Ok(s)  => format!("OK\n{s}"),
        Err(e) => format!("ERR {e}\n"),
    }
}

// ── Client ────────────────────────────────────────────────────────────────

pub fn send(sock: &Path, cmd: &str) -> Result<String, String> {
    let mut s = UnixStream::connect(sock)
        .map_err(|e| format!("connect {}: {e}", sock.display()))?;
    s.set_read_timeout(Some(Duration::from_secs(5))).ok();
    s.write_all(format!("{cmd}\n").as_bytes())
        .map_err(|e| format!("write: {e}"))?;
    let mut out = String::new();
    let mut reader = BufReader::new(&s);
    loop {
        let mut line = String::new();
        match reader.read_line(&mut line) {
            Ok(0) | Err(_) => break,
            Ok(_) => out.push_str(&line),
        }
    }
    Ok(out)
}

pub fn parse(raw: &str) -> Result<&str, String> {
    if let Some(rest) = raw.strip_prefix("OK\n") { Ok(rest) }
    else if let Some(msg) = raw.strip_prefix("ERR ") { Err(msg.trim_end().into()) }
    else { Err(format!("unexpected: {raw:?}")) }
}
