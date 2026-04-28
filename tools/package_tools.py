"""Package management: apt, pip, snap, flatpak, npm, cargo."""
import shutil
import logging
from core.tool_registry import ToolRegistry
from core.system_controller import run_shell
from core.safety import confirm

log = logging.getLogger("cogman.tools.package")


# ─── APT ────────────────────────────────────────────────────────────────────

def apt_install(package: str) -> str:
    if not confirm(f"Install package '{package}' via apt?"):
        return "Cancelled."
    return run_shell(f"sudo apt-get install -y {package}")


def apt_remove(package: str) -> str:
    if not confirm(f"Remove package '{package}' via apt?"):
        return "Cancelled."
    return run_shell(f"sudo apt-get remove -y {package}")


def apt_purge(package: str) -> str:
    if not confirm(f"Purge (remove + config) '{package}'?"):
        return "Cancelled."
    return run_shell(f"sudo apt-get purge -y {package}")


def apt_update() -> str:
    return run_shell("sudo apt-get update 2>&1 | tail -5")


def apt_upgrade(full: bool = False) -> str:
    if not confirm("Run apt upgrade?"):
        return "Cancelled."
    cmd = "sudo apt-get dist-upgrade -y" if full else "sudo apt-get upgrade -y"
    return run_shell(cmd)


def apt_search(query: str) -> str:
    return run_shell(f"apt-cache search {query} | head -20")


def apt_show(package: str) -> str:
    return run_shell(f"apt-cache show {package} 2>/dev/null | head -20")


def apt_list_installed() -> str:
    return run_shell("dpkg -l | grep '^ii' | awk '{print $2, $3}' | head -40")


def apt_autoremove() -> str:
    if not confirm("Remove unused packages (apt autoremove)?"):
        return "Cancelled."
    return run_shell("sudo apt-get autoremove -y")


# ─── PIP ────────────────────────────────────────────────────────────────────

def pip_install(package: str, user: bool = True) -> str:
    flag = "--user" if user else ""
    return run_shell(f"pip install {flag} {package}")


def pip_uninstall(package: str) -> str:
    if not confirm(f"Uninstall Python package '{package}'?"):
        return "Cancelled."
    return run_shell(f"pip uninstall -y {package}")


def pip_list() -> str:
    return run_shell("pip list 2>/dev/null | head -30")


def pip_search(query: str) -> str:
    return run_shell(f"pip index versions {query} 2>/dev/null || pip search {query} 2>/dev/null || echo 'pip search disabled; visit pypi.org'")


def pip_show(package: str) -> str:
    return run_shell(f"pip show {package}")


def pip_outdated() -> str:
    return run_shell("pip list --outdated 2>/dev/null | head -20")


def pip_upgrade(package: str) -> str:
    return run_shell(f"pip install --upgrade {package}")


# ─── SNAP ───────────────────────────────────────────────────────────────────

def snap_install(package: str, classic: bool = False) -> str:
    if not shutil.which("snap"):
        return "snap not available on this system"
    if not confirm(f"Install snap '{package}'?"):
        return "Cancelled."
    flag = "--classic" if classic else ""
    return run_shell(f"sudo snap install {flag} {package}")


def snap_remove(package: str) -> str:
    if not shutil.which("snap"):
        return "snap not available"
    if not confirm(f"Remove snap '{package}'?"):
        return "Cancelled."
    return run_shell(f"sudo snap remove {package}")


def snap_list() -> str:
    if not shutil.which("snap"):
        return "snap not available"
    return run_shell("snap list")


def snap_refresh() -> str:
    if not shutil.which("snap"):
        return "snap not available"
    return run_shell("sudo snap refresh")


# ─── FLATPAK ────────────────────────────────────────────────────────────────

def flatpak_install(app_id: str) -> str:
    if not shutil.which("flatpak"):
        return "flatpak not installed"
    if not confirm(f"Install flatpak '{app_id}'?"):
        return "Cancelled."
    return run_shell(f"flatpak install -y {app_id}")


def flatpak_list() -> str:
    if not shutil.which("flatpak"):
        return "flatpak not installed"
    return run_shell("flatpak list --app --columns=name,application,version")


def flatpak_update() -> str:
    if not shutil.which("flatpak"):
        return "flatpak not installed"
    return run_shell("flatpak update -y")


# ─── NPM ────────────────────────────────────────────────────────────────────

def npm_install(package: str, global_: bool = False) -> str:
    if not shutil.which("npm"):
        return "npm not installed — install Node.js first"
    flag = "-g" if global_ else ""
    if global_ and not confirm(f"Globally install npm package '{package}'?"):
        return "Cancelled."
    return run_shell(f"npm install {flag} {package}")


def npm_list(global_: bool = False) -> str:
    if not shutil.which("npm"):
        return "npm not installed"
    flag = "-g" if global_ else ""
    return run_shell(f"npm list {flag} --depth=0 2>/dev/null | head -30")


# ─── CARGO ──────────────────────────────────────────────────────────────────

def cargo_install(crate: str) -> str:
    if not shutil.which("cargo"):
        return "cargo not installed — install Rust first: https://rustup.rs"
    if not confirm(f"Install Rust crate '{crate}' via cargo?"):
        return "Cancelled."
    return run_shell(f"cargo install {crate}")


def register_package_tools(registry: ToolRegistry):
    # APT
    registry.register("apt_install", apt_install, "Install a package via apt",
        {"package": {"type": "string", "description": "Package name(s) to install", "required": True}},
        requires_confirm=True)
    registry.register("apt_remove", apt_remove, "Remove a package via apt",
        {"package": {"type": "string", "description": "Package name to remove", "required": True}},
        requires_confirm=True)
    registry.register("apt_purge", apt_purge, "Purge a package and its config files",
        {"package": {"type": "string", "description": "Package name to purge", "required": True}},
        requires_confirm=True)
    registry.register("apt_update", apt_update, "Update apt package list", {})
    registry.register("apt_upgrade", apt_upgrade, "Upgrade installed packages",
        {"full": {"type": "boolean", "description": "Full dist-upgrade instead of upgrade"}},
        requires_confirm=True)
    registry.register("apt_search", apt_search, "Search apt packages",
        {"query": {"type": "string", "description": "Search term", "required": True}})
    registry.register("apt_show", apt_show, "Show apt package details",
        {"package": {"type": "string", "description": "Package name", "required": True}})
    registry.register("apt_list_installed", apt_list_installed, "List installed apt packages", {})
    registry.register("apt_autoremove", apt_autoremove, "Remove unused apt packages", {}, requires_confirm=True)

    # PIP
    registry.register("pip_install", pip_install, "Install a Python package via pip",
        {
            "package": {"type": "string", "description": "Package name(s)", "required": True},
            "user": {"type": "boolean", "description": "Install to user site (default True)"},
        })
    registry.register("pip_uninstall", pip_uninstall, "Uninstall a Python package",
        {"package": {"type": "string", "description": "Package name", "required": True}},
        requires_confirm=True)
    registry.register("pip_list", pip_list, "List installed Python packages", {})
    registry.register("pip_show", pip_show, "Show Python package info",
        {"package": {"type": "string", "description": "Package name", "required": True}})
    registry.register("pip_outdated", pip_outdated, "List outdated Python packages", {})
    registry.register("pip_upgrade", pip_upgrade, "Upgrade a Python package",
        {"package": {"type": "string", "description": "Package name", "required": True}})

    # SNAP
    registry.register("snap_install", snap_install, "Install a snap package",
        {
            "package": {"type": "string", "description": "Snap package name", "required": True},
            "classic": {"type": "boolean", "description": "Use --classic confinement"},
        }, requires_confirm=True)
    registry.register("snap_remove", snap_remove, "Remove a snap package",
        {"package": {"type": "string", "description": "Snap package name", "required": True}},
        requires_confirm=True)
    registry.register("snap_list", snap_list, "List installed snaps", {})
    registry.register("snap_refresh", snap_refresh, "Update all snap packages", {})

    # FLATPAK
    registry.register("flatpak_install", flatpak_install, "Install a flatpak app",
        {"app_id": {"type": "string", "description": "Flatpak app ID", "required": True}},
        requires_confirm=True)
    registry.register("flatpak_list", flatpak_list, "List installed flatpak apps", {})
    registry.register("flatpak_update", flatpak_update, "Update all flatpak apps", {})

    # NPM
    registry.register("npm_install", npm_install, "Install an npm package",
        {
            "package": {"type": "string", "description": "Package name", "required": True},
            "global_": {"type": "boolean", "description": "Install globally (-g)"},
        })
    registry.register("npm_list", npm_list, "List installed npm packages",
        {"global_": {"type": "boolean", "description": "List global packages"}})

    # CARGO
    registry.register("cargo_install", cargo_install, "Install a Rust crate via cargo",
        {"crate": {"type": "string", "description": "Crate name", "required": True}},
        requires_confirm=True)
