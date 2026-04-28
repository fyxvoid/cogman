"""Advanced process management: tree, priority, background jobs, signals."""
import os
import signal
import subprocess
import logging
import psutil
from core.tool_registry import ToolRegistry
from core.safety import check_command, confirm
from core.system_controller import run_shell

log = logging.getLogger("cogman.tools.process")


def process_tree(pid: int = None) -> str:
    try:
        if pid:
            proc = psutil.Process(pid)
            children = proc.children(recursive=True)
            lines = [f"[{proc.pid}] {proc.name()} (root)"]
            for c in children:
                lines.append(f"  └─ [{c.pid}] {c.name()}")
            return "\n".join(lines)
        else:
            return run_shell("pstree -p 2>/dev/null || ps -ejH 2>/dev/null | head -40")
    except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
        return f"Error: {e}"


def top_processes(n: int = 10, sort_by: str = "cpu") -> str:
    sort_key = {"cpu": "cpu_percent", "memory": "memory_percent", "pid": "pid"}.get(sort_by, "cpu_percent")
    procs = []
    for proc in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent", "status", "username"]):
        try:
            procs.append(proc.info)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    procs.sort(key=lambda p: p.get(sort_key, 0), reverse=True)
    lines = [f"{'PID':>7} {'CPU%':>6} {'MEM%':>6} {'STATUS':>10} {'USER':>10}  NAME"]
    lines.append("-" * 55)
    for p in procs[:n]:
        lines.append(
            f"{p['pid']:>7} {p['cpu_percent']:>6.1f} {p['memory_percent']:>6.1f}"
            f" {p['status']:>10} {(p['username'] or '?')[:10]:>10}  {p['name']}"
        )
    return "\n".join(lines)


def get_process_info(name_or_pid: str) -> str:
    try:
        pid = int(name_or_pid)
        procs = [psutil.Process(pid)]
    except ValueError:
        procs = [p for p in psutil.process_iter() if p.name().lower() == name_or_pid.lower()]

    if not procs:
        return f"No process found: {name_or_pid}"

    out = []
    for p in procs[:3]:
        try:
            mem = p.memory_info()
            out.append(
                f"PID: {p.pid} | Name: {p.name()} | Status: {p.status()}\n"
                f"  CPU: {p.cpu_percent(interval=0.1):.1f}% | "
                f"RAM: {mem.rss // (1024**2)} MB\n"
                f"  Cmd: {' '.join(p.cmdline()[:6])}\n"
                f"  CWD: {p.cwd()}"
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
            out.append(f"PID {p.pid}: {e}")
    return "\n\n".join(out)


def set_priority(pid: int, priority: int) -> str:
    """Set process priority (niceness). priority: -20 (highest) to 19 (lowest)."""
    priority = max(-20, min(19, priority))
    try:
        proc = psutil.Process(pid)
        proc.nice(priority)
        return f"Set priority of PID {pid} to {priority}"
    except psutil.AccessDenied:
        result = run_shell(f"sudo renice {priority} -p {pid}")
        return result or f"Set priority of PID {pid} to {priority} (via sudo)"
    except psutil.NoSuchProcess:
        return f"No process with PID {pid}"


def run_background(command: str) -> str:
    ok, reason = check_command(command)
    if not ok:
        return f"[BLOCKED] {reason}"
    if reason.startswith("warn:"):
        if not confirm(f"Run in background: {command}?"):
            return "Cancelled."
    try:
        proc = subprocess.Popen(
            command, shell=True,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return f"Started in background. PID: {proc.pid}"
    except Exception as e:
        return f"Error: {e}"


def send_signal(pid: int, sig: str = "TERM") -> str:
    sig_map = {
        "TERM": signal.SIGTERM, "KILL": signal.SIGKILL,
        "HUP": signal.SIGHUP, "INT": signal.SIGINT,
        "STOP": signal.SIGSTOP, "CONT": signal.SIGCONT,
        "USR1": signal.SIGUSR1, "USR2": signal.SIGUSR2,
    }
    sig_val = sig_map.get(sig.upper())
    if not sig_val:
        return f"Unknown signal: {sig}. Available: {list(sig_map.keys())}"
    if sig.upper() in ("KILL", "STOP") and not confirm(f"Send {sig} to PID {pid}?"):
        return "Cancelled."
    try:
        os.kill(pid, sig_val)
        return f"Sent {sig} to PID {pid}"
    except ProcessLookupError:
        return f"No process with PID {pid}"
    except PermissionError:
        return f"Permission denied — try with sudo"


def find_process_by_port(port: int) -> str:
    return run_shell(f"ss -tlnp 2>/dev/null | grep :{port} || lsof -i :{port} 2>/dev/null")


def wait_for_process(pid: int, timeout: int = 30) -> str:
    try:
        proc = psutil.Process(pid)
        proc.wait(timeout=timeout)
        return f"PID {pid} finished"
    except psutil.TimeoutExpired:
        return f"Timed out waiting for PID {pid} after {timeout}s"
    except psutil.NoSuchProcess:
        return f"PID {pid} already gone"


def register_process_tools(registry: ToolRegistry):
    registry.register("process_tree", process_tree, "Show process tree",
        {"pid": {"type": "integer", "description": "Root PID (default: show full tree)"}})
    registry.register("top_processes", top_processes, "Show top processes by CPU/memory",
        {
            "n": {"type": "integer", "description": "Number of processes (default 10)"},
            "sort_by": {"type": "string", "description": "Sort by: cpu, memory, pid (default: cpu)"},
        })
    registry.register("get_process_info", get_process_info, "Get detailed info about a process by name or PID",
        {"name_or_pid": {"type": "string", "description": "Process name or PID", "required": True}})
    registry.register("set_priority", set_priority, "Set process CPU priority (niceness -20 to 19)",
        {
            "pid": {"type": "integer", "description": "Process PID", "required": True},
            "priority": {"type": "integer", "description": "Niceness value -20 (highest) to 19 (lowest)", "required": True},
        })
    registry.register("run_background", run_background, "Run a command in the background (detached)",
        {"command": {"type": "string", "description": "Command to run in background", "required": True}})
    registry.register("send_signal", send_signal, "Send a signal to a process (TERM, KILL, HUP, INT, STOP, CONT)",
        {
            "pid": {"type": "integer", "description": "Target PID", "required": True},
            "sig": {"type": "string", "description": "Signal name: TERM, KILL, HUP, INT, STOP, CONT (default: TERM)"},
        }, requires_confirm=True)
    registry.register("find_process_by_port", find_process_by_port, "Find which process is using a port",
        {"port": {"type": "integer", "description": "Port number to check", "required": True}})
    registry.register("wait_for_process", wait_for_process, "Wait for a process to finish",
        {
            "pid": {"type": "integer", "description": "PID to wait for", "required": True},
            "timeout": {"type": "integer", "description": "Max wait seconds (default 30)"},
        })
