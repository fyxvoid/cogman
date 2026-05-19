"""
Native package tools — interface to rogue-linux cogman for the AI agent.

Uses the `cogman` unified binary from ~/void/academic/rogue-linux/bin/:
  cogman pkg install <toml>     install a package from .toml definition
  cogman pkg remove  <name>     remove an installed package
  cogman pkg upgrade <toml>     remove + reinstall
  cogman pkg list               list installed packages
  cogman svc list               list supervisor-managed services
  cogman svc status  <name>     service status
  cogman svc start/stop/restart <name>
"""
import os
import subprocess
from pathlib import Path

from core.tool_registry import ToolRegistry

# ── Binary resolution ─────────────────────────────────────────────────────────

_ROGUE_BIN = Path.home() / "void" / "academic" / "rogue-linux" / "bin"
_PROJECT_BIN = Path(__file__).parent.parent / "bin"


def _find_bin(name: str) -> str:
    for candidate in [_ROGUE_BIN / name, _PROJECT_BIN / name]:
        if candidate.exists():
            return str(candidate)
    return name  # PATH fallback


def _cogman() -> str:
    return _find_bin("cogman")


def _run(args: list[str], *, timeout: int = 60) -> tuple[bool, str]:
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        out = (r.stdout + r.stderr).strip()
        return r.returncode == 0, out
    except FileNotFoundError:
        return False, (
            f"Binary not found: {args[0]!r}\n"
            f"Expected: {_ROGUE_BIN / 'cogman'}\n"
            f"Ensure rogue-linux is built and in PATH."
        )
    except subprocess.TimeoutExpired:
        return False, "Timed out"
    except Exception as e:
        return False, str(e)


# ── Package management ─────────────────────────────────────────────────────────

def cogman_pkg_install(toml: str, root: str = "") -> str:
    """Install a rogue-linux native package from its .toml manifest."""
    if not os.path.exists(toml):
        return f"Error: {toml!r} not found"
    cmd = [_cogman(), "pkg", "install", toml]
    if root:
        cmd += ["--root", root]
    ok, out = _run(cmd, timeout=300)
    return out


def cogman_pkg_remove(name: str) -> str:
    """Remove a rogue-linux native package by name."""
    ok, out = _run([_cogman(), "pkg", "remove", name])
    return out


def cogman_pkg_upgrade(toml: str, root: str = "") -> str:
    """Upgrade a rogue-linux native package (remove old + install new)."""
    if not os.path.exists(toml):
        return f"Error: {toml!r} not found"
    cmd = [_cogman(), "pkg", "upgrade", toml]
    if root:
        cmd += ["--root", root]
    ok, out = _run(cmd, timeout=300)
    return out


def cogman_pkg_list() -> str:
    """List all rogue-linux natively installed packages."""
    ok, out = _run([_cogman(), "pkg", "list"])
    return out if out else "No packages installed"


def cogman_pkg_info(name: str) -> str:
    """Show detailed info about an installed rogue-linux package."""
    ok, out = _run([_cogman(), "pkg", "info", name])
    return out


# ── Service control ───────────────────────────────────────────────────────────

def cogman_svc_list() -> str:
    """List all services managed by the cogman supervisor."""
    ok, out = _run([_cogman(), "svc", "list"])
    if not ok:
        return (
            f"{out}\n"
            f"(Is cogman-supervisor running?  "
            f"Start it with: cogman daemon --services /etc/cogman/services)"
        )
    return out


def cogman_svc_status(name: str) -> str:
    """Show status of a cogman-managed service."""
    ok, out = _run([_cogman(), "svc", "status", name])
    return out


def cogman_svc_start(name: str) -> str:
    """Start a cogman-managed service."""
    ok, out = _run([_cogman(), "svc", "start", name])
    return out


def cogman_svc_stop(name: str) -> str:
    """Stop a cogman-managed service."""
    ok, out = _run([_cogman(), "svc", "stop", name])
    return out


def cogman_svc_restart(name: str) -> str:
    """Restart a cogman-managed service."""
    ok, out = _run([_cogman(), "svc", "restart", name])
    return out


def cogman_svc_ping() -> str:
    """Ping the cogman daemon to check if it is running."""
    ok, out = _run([_cogman(), "svc", "ping"])
    return "daemon: running" if ok else f"daemon: not running\n{out}"


def cogman_core_status() -> str:
    """Check if the cogman binary is available and report its version."""
    bin_path = _cogman()
    ok, ver = _run([bin_path, "--version"])
    if ok:
        # Also check daemon liveness
        ok2, ping = _run([bin_path, "svc", "ping"])
        daemon = "running" if ok2 else "not running"
        return f"cogman  {ver}\npath:   {bin_path}\ndaemon: {daemon}"
    return (
        f"cogman not found at: {bin_path}\n"
        f"Expected: {_ROGUE_BIN / 'cogman'}\n"
        f"Build rogue-linux or add its bin/ to PATH."
    )


# ── Register ──────────────────────────────────────────────────────────────────

def register_native_pkg_tools(registry: ToolRegistry):
    registry.register(
        "cogman_pkg_install",
        cogman_pkg_install,
        "Install a rogue-linux native package from its .toml manifest",
        {
            "toml": {"type": "string", "description": "Path to package .toml", "required": True},
            "root": {"type": "string", "description": "Custom install root (default: /)"},
        },
    )
    registry.register(
        "cogman_pkg_remove",
        cogman_pkg_remove,
        "Remove a rogue-linux native package by name",
        {"name": {"type": "string", "description": "Package name to remove", "required": True}},
    )
    registry.register(
        "cogman_pkg_upgrade",
        cogman_pkg_upgrade,
        "Upgrade a rogue-linux native package (remove + reinstall from .toml)",
        {
            "toml": {"type": "string", "description": "Path to updated package .toml", "required": True},
            "root": {"type": "string", "description": "Custom install root"},
        },
    )
    registry.register(
        "cogman_pkg_list",
        cogman_pkg_list,
        "List all rogue-linux natively installed packages",
        {},
    )
    registry.register(
        "cogman_pkg_info",
        cogman_pkg_info,
        "Show info about an installed rogue-linux package",
        {"name": {"type": "string", "description": "Package name", "required": True}},
    )
    registry.register(
        "cogman_svc_list",
        cogman_svc_list,
        "List all services managed by the cogman supervisor",
        {},
    )
    registry.register(
        "cogman_svc_status",
        cogman_svc_status,
        "Show status of a cogman-managed service",
        {"name": {"type": "string", "description": "Service name", "required": True}},
    )
    registry.register(
        "cogman_svc_start",
        cogman_svc_start,
        "Start a cogman-managed service",
        {"name": {"type": "string", "description": "Service name", "required": True}},
    )
    registry.register(
        "cogman_svc_stop",
        cogman_svc_stop,
        "Stop a cogman-managed service",
        {"name": {"type": "string", "description": "Service name", "required": True}},
    )
    registry.register(
        "cogman_svc_restart",
        cogman_svc_restart,
        "Restart a cogman-managed service",
        {"name": {"type": "string", "description": "Service name", "required": True}},
    )
    registry.register(
        "cogman_svc_ping",
        cogman_svc_ping,
        "Ping the cogman daemon — check liveness",
        {},
    )
    registry.register(
        "cogman_core_status",
        cogman_core_status,
        "Check cogman binary availability and daemon status",
        {},
    )
