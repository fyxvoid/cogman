"""Systemd service management: start, stop, enable, disable, status, logs."""
import logging
from core.tool_registry import ToolRegistry
from core.system_controller import run_shell
from core.safety import confirm

log = logging.getLogger("cogman.tools.service")


def service_status(name: str) -> str:
    return run_shell(f"systemctl status {name} --no-pager -l 2>&1 | head -30")


def service_start(name: str) -> str:
    if not confirm(f"Start service '{name}'?"):
        return "Cancelled."
    result = run_shell(f"sudo systemctl start {name}")
    return result or f"Service '{name}' started"


def service_stop(name: str) -> str:
    if not confirm(f"Stop service '{name}'?"):
        return "Cancelled."
    result = run_shell(f"sudo systemctl stop {name}")
    return result or f"Service '{name}' stopped"


def service_restart(name: str) -> str:
    if not confirm(f"Restart service '{name}'?"):
        return "Cancelled."
    result = run_shell(f"sudo systemctl restart {name}")
    return result or f"Service '{name}' restarted"


def service_reload(name: str) -> str:
    result = run_shell(f"sudo systemctl reload {name} 2>/dev/null || sudo systemctl reload-or-restart {name}")
    return result or f"Service '{name}' reloaded"


def service_enable(name: str) -> str:
    if not confirm(f"Enable service '{name}' to start on boot?"):
        return "Cancelled."
    result = run_shell(f"sudo systemctl enable {name}")
    return result or f"Service '{name}' enabled"


def service_disable(name: str) -> str:
    if not confirm(f"Disable service '{name}' from starting on boot?"):
        return "Cancelled."
    result = run_shell(f"sudo systemctl disable {name}")
    return result or f"Service '{name}' disabled"


def service_logs(name: str, lines: int = 50, follow: bool = False) -> str:
    if follow:
        return f"Use: journalctl -u {name} -f (interactive, cannot stream here)"
    return run_shell(f"journalctl -u {name} --no-pager -n {lines} 2>/dev/null")


def list_services(state: str = "running") -> str:
    state_map = {
        "running": "--state=running",
        "failed": "--state=failed",
        "enabled": "--state=enabled",
        "disabled": "--state=disabled",
        "all": "",
    }
    flag = state_map.get(state, "--state=running")
    return run_shell(f"systemctl list-units --type=service {flag} --no-pager 2>/dev/null | head -40")


def failed_services() -> str:
    return run_shell("systemctl list-units --type=service --state=failed --no-pager 2>/dev/null")


def daemon_reload() -> str:
    return run_shell("sudo systemctl daemon-reload") or "Daemon reloaded"


def system_uptime() -> str:
    return run_shell("uptime -p && systemctl --no-pager show --property=SystemState")


def list_timers() -> str:
    return run_shell("systemctl list-timers --no-pager 2>/dev/null")


# User services (no sudo)
def user_service_status(name: str) -> str:
    return run_shell(f"systemctl --user status {name} --no-pager 2>&1 | head -20")


def user_service_start(name: str) -> str:
    return run_shell(f"systemctl --user start {name}") or f"User service '{name}' started"


def user_service_stop(name: str) -> str:
    return run_shell(f"systemctl --user stop {name}") or f"User service '{name}' stopped"


def register_service_tools(registry: ToolRegistry):
    registry.register("service_status", service_status, "Check status of a systemd service",
        {"name": {"type": "string", "description": "Service name (e.g. nginx, ssh)", "required": True}})
    registry.register("service_start", service_start, "Start a systemd service",
        {"name": {"type": "string", "description": "Service name", "required": True}},
        requires_confirm=True)
    registry.register("service_stop", service_stop, "Stop a systemd service",
        {"name": {"type": "string", "description": "Service name", "required": True}},
        requires_confirm=True)
    registry.register("service_restart", service_restart, "Restart a systemd service",
        {"name": {"type": "string", "description": "Service name", "required": True}},
        requires_confirm=True)
    registry.register("service_reload", service_reload, "Reload a systemd service config",
        {"name": {"type": "string", "description": "Service name", "required": True}})
    registry.register("service_enable", service_enable, "Enable a service to auto-start on boot",
        {"name": {"type": "string", "description": "Service name", "required": True}},
        requires_confirm=True)
    registry.register("service_disable", service_disable, "Disable a service from auto-starting",
        {"name": {"type": "string", "description": "Service name", "required": True}},
        requires_confirm=True)
    registry.register("service_logs", service_logs, "View systemd service logs via journalctl",
        {
            "name": {"type": "string", "description": "Service name", "required": True},
            "lines": {"type": "integer", "description": "Number of log lines (default 50)"},
        })
    registry.register("list_services", list_services, "List systemd services by state",
        {"state": {"type": "string", "description": "State filter: running, failed, enabled, disabled, all (default: running)"}})
    registry.register("failed_services", failed_services, "List failed systemd services", {})
    registry.register("daemon_reload", daemon_reload, "Reload systemd daemon configuration", {})
    registry.register("system_uptime", system_uptime, "Show system uptime", {})
    registry.register("list_timers", list_timers, "List systemd timers", {})
    registry.register("user_service_status", user_service_status, "Check status of a user systemd service",
        {"name": {"type": "string", "description": "User service name", "required": True}})
    registry.register("user_service_start", user_service_start, "Start a user systemd service",
        {"name": {"type": "string", "description": "User service name", "required": True}})
    registry.register("user_service_stop", user_service_stop, "Stop a user systemd service",
        {"name": {"type": "string", "description": "User service name", "required": True}})
