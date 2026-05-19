"""
Monitor tools — expose the SystemMonitor to the AI agent.

Tools:
  monitor_status    — current CPU/RAM/disk/temp/battery readings
  monitor_thresholds — show or update alert thresholds
  monitor_history   — last N alert events (from log)
  set_watch_service — add/remove a service from the watchlist
"""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from core.tool_registry import ToolRegistry

if TYPE_CHECKING:
    from core.monitor import SystemMonitor

_monitor: Optional["SystemMonitor"] = None


def set_monitor_instance(m: "SystemMonitor"):
    global _monitor
    _monitor = m


# ── Tools ─────────────────────────────────────────────────────────────────────

def monitor_status() -> str:
    """Return live CPU, RAM, disk, temperature, and battery readings."""
    if _monitor is None:
        # Fallback: read directly without monitor instance
        import psutil, platform
        vm   = psutil.virtual_memory()
        du   = psutil.disk_usage("/")
        cpu  = psutil.cpu_percent(interval=1)
        bat  = psutil.sensors_battery()
        try:
            import psutil as _p
            temps = _p.sensors_temperatures()
            temp = None
            for key in ("coretemp", "k10temp", "cpu_thermal", "acpitz"):
                if key in temps and temps[key]:
                    temp = max(r.current for r in temps[key])
                    break
        except Exception:
            temp = None

        lines = [
            f"CPU:      {cpu:.1f}%",
            f"RAM:      {vm.percent:.1f}%  ({vm.used // 1024**2} MB / {vm.total // 1024**2} MB)",
            f"Disk /:   {du.percent:.1f}%  ({du.free // 1024**3} GB free of {du.total // 1024**3} GB)",
        ]
        if temp is not None:
            lines.append(f"Temp:     {temp:.1f}°C")
        if bat is not None:
            plugged = "plugged in" if bat.power_plugged else "on battery"
            lines.append(f"Battery:  {bat.percent:.0f}%  ({plugged})")
        return "\n".join(lines)

    s = _monitor.status()
    lines = [
        f"CPU:      {s['cpu_percent']:.1f}%",
        f"RAM:      {s['ram_percent']:.1f}%  ({s['ram_used_gb']:.1f} GB / {s['ram_total_gb']:.1f} GB)",
        f"Disk /:   {s['disk_percent']:.1f}%  ({s['disk_free_gb']:.1f} GB free)",
    ]
    if s["temp_celsius"] is not None:
        lines.append(f"Temp:     {s['temp_celsius']:.1f}°C")
    if s["battery_pct"] is not None:
        plug = "plugged" if s["battery_plugged"] else "on battery"
        lines.append(f"Battery:  {s['battery_pct']:.0f}%  ({plug})")
    return "\n".join(lines)


def monitor_thresholds(
    cpu: float = 0, ram: float = 0, disk: float = 0,
    temp: float = 0, battery: float = 0
) -> str:
    """
    Show or update alert thresholds.
    Pass non-zero values to update. Pass nothing to just read current thresholds.
    """
    if _monitor is None:
        return "Monitor not running (COGMAN_MONITOR=false)."

    t = _monitor._t
    if cpu   > 0: t.cpu_percent  = cpu
    if ram   > 0: t.ram_percent  = ram
    if disk  > 0: t.disk_percent = disk
    if temp  > 0: t.temp_celsius = temp
    if battery > 0: t.battery_low = battery

    return (
        f"Alert thresholds:\n"
        f"  CPU:     > {t.cpu_percent:.0f}%  (sustained {t.cpu_sustained_s:.0f}s)\n"
        f"  RAM:     > {t.ram_percent:.0f}%\n"
        f"  Disk:    > {t.disk_percent:.0f}%\n"
        f"  Temp:    > {t.temp_celsius:.0f}°C\n"
        f"  Battery: < {t.battery_low:.0f}%\n"
        f"  Interval: {t.check_interval_s:.0f}s\n"
        f"  Watching services: {t.watched_services or '(none)'}"
    )


def set_watch_service(service: str, action: str = "add") -> str:
    """
    Add or remove a systemd service from the monitor watchlist.

    Args:
        service: Service name (e.g. nginx, ssh, postgresql)
        action:  'add' (default) or 'remove'
    """
    if _monitor is None:
        return "Monitor not running."
    svc = service.strip()
    if action == "remove":
        if svc in _monitor._t.watched_services:
            _monitor._t.watched_services.remove(svc)
            return f"Removed '{svc}' from watchlist."
        return f"'{svc}' is not being watched."
    if svc not in _monitor._t.watched_services:
        _monitor._t.watched_services.append(svc)
        _monitor._seed_baselines()
        return f"Now watching '{svc}'. Will alert and auto-restart on failure."
    return f"'{svc}' is already being watched."


def monitor_history(n: int = 20) -> str:
    """Show last N monitor alert lines from the log."""
    import subprocess, shutil
    log_path = "/home/void/void/cogman/logs/cogman.log"
    if not __import__("os").path.exists(log_path):
        return "Log file not found."
    result = subprocess.run(
        ["grep", "-i", "ALERT\|ANNOUNCE\|monitor", log_path],
        capture_output=True, text=True,
    )
    lines = result.stdout.strip().splitlines()
    if not lines:
        return "No monitor alerts in log yet."
    return "\n".join(lines[-n:])


# ── Register ──────────────────────────────────────────────────────────────────

def register_monitor_tools(registry: ToolRegistry, monitor=None):
    if monitor is not None:
        set_monitor_instance(monitor)

    registry.register(
        "monitor_status",
        monitor_status,
        "Live CPU, RAM, disk, temperature, and battery readings",
        {},
    )
    registry.register(
        "monitor_thresholds",
        monitor_thresholds,
        "Show or update system alert thresholds (cpu/ram/disk/temp/battery)",
        {
            "cpu":     {"type": "number", "description": "CPU % threshold (0=no change)"},
            "ram":     {"type": "number", "description": "RAM % threshold"},
            "disk":    {"type": "number", "description": "Disk % threshold"},
            "temp":    {"type": "number", "description": "Temperature °C threshold"},
            "battery": {"type": "number", "description": "Battery % low threshold"},
        },
    )
    registry.register(
        "set_watch_service",
        set_watch_service,
        "Add or remove a systemd service from the proactive monitor watchlist",
        {
            "service": {"type": "string", "description": "Service name e.g. nginx", "required": True},
            "action":  {"type": "string", "description": "add or remove (default: add)"},
        },
    )
    registry.register(
        "monitor_history",
        monitor_history,
        "Show last N alert events from the monitor log",
        {
            "n": {"type": "integer", "description": "Lines to show (default 20)"},
        },
    )
