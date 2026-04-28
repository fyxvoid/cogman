"""System tools: shell, apps, processes, hardware, desktop control."""
import os
import psutil
import logging
from core.tool_registry import ToolRegistry
from core.system_controller import (
    run_shell, open_app, get_time, get_date, screenshot,
    lock_screen, set_volume, mute_toggle, kill_process,
    list_processes, network_info, battery_status, type_text,
)
from core.safety import check_command, confirm

log = logging.getLogger("cogman.tools.system")


def _safe_run_shell(command: str) -> str:
    ok, reason = check_command(command)
    if not ok:
        return f"[BLOCKED] {reason}"
    if reason.startswith("warn:"):
        if not confirm(f"Run: {command}?"):
            return "Cancelled by user."
    return run_shell(command)


def disk_usage(path: str = "/") -> str:
    try:
        usage = psutil.disk_usage(path)
        return (
            f"Disk ({path}):\n"
            f"  Total: {usage.total // (1024**3)} GB\n"
            f"  Used:  {usage.used // (1024**3)} GB ({usage.percent}%)\n"
            f"  Free:  {usage.free // (1024**3)} GB"
        )
    except Exception as e:
        return f"Disk usage error: {e}"


def memory_usage() -> str:
    vm = psutil.virtual_memory()
    sw = psutil.swap_memory()
    return (
        f"RAM: {vm.used // (1024**2)} MB used / {vm.total // (1024**2)} MB total ({vm.percent}%)\n"
        f"Swap: {sw.used // (1024**2)} MB / {sw.total // (1024**2)} MB ({sw.percent}%)"
    )


def cpu_usage() -> str:
    per_cpu = psutil.cpu_percent(interval=1, percpu=True)
    overall = sum(per_cpu) / len(per_cpu)
    cores = "\n".join(f"  Core {i}: {p}%" for i, p in enumerate(per_cpu))
    freq = psutil.cpu_freq()
    freq_str = f"{freq.current:.0f} MHz" if freq else "N/A"
    return f"CPU: {overall:.1f}% overall @ {freq_str}\n{cores}"


def register_system_tools(registry: ToolRegistry):
    registry.register(
        "run_shell",
        _safe_run_shell,
        "Execute a shell command on the Linux system",
        {"command": {"type": "string", "description": "Shell command to run", "required": True}},
        requires_confirm=True,
    )
    registry.register(
        "open_app",
        open_app,
        "Open an application by name (browser, terminal, file_manager, etc.)",
        {"app": {"type": "string", "description": "Application name", "required": True}},
    )
    registry.register("get_time", get_time, "Get the current system time", {})
    registry.register("get_date", get_date, "Get today's date", {})
    registry.register(
        "disk_usage",
        disk_usage,
        "Check disk space usage",
        {"path": {"type": "string", "description": "Path to check (default: /)"}},
    )
    registry.register("memory_usage", memory_usage, "Check RAM and swap usage", {})
    registry.register("cpu_usage", cpu_usage, "Check CPU usage per core", {})
    registry.register("screenshot", screenshot, "Take a screenshot",
                      {"path": {"type": "string", "description": "Save path (optional)"}})
    registry.register("lock_screen", lock_screen, "Lock the screen", {})
    registry.register(
        "set_volume",
        set_volume,
        "Set system audio volume (0–100)",
        {"level": {"type": "integer", "description": "Volume level 0-100", "required": True}},
    )
    registry.register("mute_toggle", mute_toggle, "Toggle audio mute", {})
    registry.register(
        "kill_process",
        kill_process,
        "Kill a process by name",
        {"name": {"type": "string", "description": "Process name or pattern", "required": True}},
        requires_confirm=True,
    )
    registry.register("list_processes", list_processes, "List running processes sorted by CPU", {})
    registry.register("network_info", network_info, "Show network and WiFi status", {})
    registry.register("battery_status", battery_status, "Check battery charge level", {})
    registry.register(
        "type_text",
        type_text,
        "Type text into the active window (requires xdotool)",
        {"text": {"type": "string", "description": "Text to type", "required": True}},
    )
