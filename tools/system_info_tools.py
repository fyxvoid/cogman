"""System information: hardware, OS, kernel, sensors, logs, env."""
import os
import platform
import logging
from core.tool_registry import ToolRegistry
from core.system_controller import run_shell

log = logging.getLogger("cogman.tools.sysinfo")


def system_info() -> str:
    import psutil
    uname = platform.uname()
    vm = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    cpu_count = psutil.cpu_count(logical=True)
    cpu_phys = psutil.cpu_count(logical=False)

    return (
        f"OS:       {uname.system} {uname.release} ({uname.machine})\n"
        f"Hostname: {uname.node}\n"
        f"Kernel:   {uname.version[:60]}\n"
        f"Python:   {platform.python_version()}\n"
        f"CPU:      {cpu_phys} physical, {cpu_count} logical cores\n"
        f"RAM:      {vm.total // (1024**3)} GB total\n"
        f"Disk /:   {disk.total // (1024**3)} GB total, {disk.free // (1024**3)} GB free"
    )


def os_release() -> str:
    result = run_shell("cat /etc/os-release 2>/dev/null || lsb_release -a 2>/dev/null")
    return result


def kernel_info() -> str:
    return run_shell("uname -a && cat /proc/version 2>/dev/null | head -2")


def cpu_info() -> str:
    return run_shell("lscpu 2>/dev/null | head -25 || cat /proc/cpuinfo | grep 'model name' | head -4")


def memory_info() -> str:
    return run_shell("free -h && cat /proc/meminfo | grep -E 'MemTotal|MemFree|MemAvailable|SwapTotal|SwapFree'")


def disk_info() -> str:
    return run_shell("lsblk -o NAME,SIZE,TYPE,MOUNTPOINT,FSTYPE 2>/dev/null && echo '' && df -h 2>/dev/null")


def pci_devices() -> str:
    return run_shell("lspci 2>/dev/null | head -30 || echo 'lspci not available'")


def usb_devices() -> str:
    return run_shell("lsusb 2>/dev/null | head -30 || echo 'lsusb not available'")


def hardware_info() -> str:
    return run_shell("sudo dmidecode -t system 2>/dev/null | head -20 || inxi -S 2>/dev/null || echo 'dmidecode/inxi not available'")


def sensors() -> str:
    result = run_shell("sensors 2>/dev/null")
    if "[exit" in result or not result:
        result = run_shell("cat /sys/class/thermal/thermal_zone*/temp 2>/dev/null | awk '{print $1/1000 \"°C\"}'")
    return result or "No sensor data available (install: sudo apt install lm-sensors && sudo sensors-detect)"


def journal_logs(n: int = 30, since: str = "", unit: str = "", level: str = "") -> str:
    parts = ["journalctl --no-pager"]
    if n:
        parts.append(f"-n {n}")
    if since:
        parts.append(f"--since '{since}'")
    if unit:
        parts.append(f"-u {unit}")
    if level:
        parts.append(f"-p {level}")
    return run_shell(" ".join(parts) + " 2>&1")


def syslog(n: int = 30) -> str:
    for log_path in ["/var/log/syslog", "/var/log/messages", "/var/log/kern.log"]:
        if os.path.exists(log_path):
            return run_shell(f"tail -n {n} {log_path} 2>/dev/null")
    return "No syslog found — use journal_logs instead"


def dmesg(n: int = 30, level: str = "") -> str:
    flag = f"--level {level}" if level else ""
    return run_shell(f"dmesg {flag} --human 2>/dev/null | tail -n {n}")


def env_vars(filter_: str = "") -> str:
    if filter_:
        return run_shell(f"env | grep -i '{filter_}'")
    return run_shell("env | sort")


def which_command(command: str) -> str:
    result = run_shell(f"which {command} 2>/dev/null && {command} --version 2>/dev/null | head -2")
    return result or f"'{command}' not found in PATH"


def path_info() -> str:
    path = os.environ.get("PATH", "")
    paths = path.split(":")
    return "PATH entries:\n" + "\n".join(f"  {p}" for p in paths)


def installed_shells() -> str:
    return run_shell("cat /etc/shells 2>/dev/null")


def hostname_info() -> str:
    return run_shell("hostname -f 2>/dev/null; hostname -I 2>/dev/null")


def user_info() -> str:
    return run_shell("id && who && last | head -5")


def load_average() -> str:
    return run_shell("uptime && cat /proc/loadavg")


def boot_time() -> str:
    import psutil, datetime
    bt = datetime.datetime.fromtimestamp(psutil.boot_time())
    return f"System booted: {bt.strftime('%Y-%m-%d %H:%M:%S')}"


def locale_info() -> str:
    return run_shell("locale && timedatectl 2>/dev/null | head -10")


def register_system_info_tools(registry: ToolRegistry):
    registry.register("system_info", system_info, "Get full system overview (OS, CPU, RAM, disk)", {})
    registry.register("os_release", os_release, "Show OS/distribution information", {})
    registry.register("kernel_info", kernel_info, "Show kernel version and info", {})
    registry.register("cpu_info", cpu_info, "Show detailed CPU information", {})
    registry.register("memory_info", memory_info, "Show detailed memory usage", {})
    registry.register("disk_info", disk_info, "Show disk and filesystem info", {})
    registry.register("pci_devices", pci_devices, "List PCI devices (GPU, NIC, etc.)", {})
    registry.register("usb_devices", usb_devices, "List connected USB devices", {})
    registry.register("hardware_info", hardware_info, "Show hardware model info", {})
    registry.register("sensors", sensors, "Show CPU/hardware temperature sensors", {})
    registry.register("journal_logs", journal_logs, "View systemd journal logs",
        {
            "n": {"type": "integer", "description": "Lines to show (default 30)"},
            "since": {"type": "string", "description": "Show logs since e.g. '1 hour ago', '2024-01-01'"},
            "unit": {"type": "string", "description": "Filter by systemd unit"},
            "level": {"type": "string", "description": "Log level: emerg, alert, crit, err, warning, notice, info, debug"},
        })
    registry.register("syslog", syslog, "Show last N lines of system syslog",
        {"n": {"type": "integer", "description": "Lines to show (default 30)"}})
    registry.register("dmesg", dmesg, "Show kernel ring buffer messages",
        {
            "n": {"type": "integer", "description": "Lines to show (default 30)"},
            "level": {"type": "string", "description": "Filter by level: err, warn, info"},
        })
    registry.register("env_vars", env_vars, "Show environment variables",
        {"filter_": {"type": "string", "description": "Filter by keyword (empty = show all)"}})
    registry.register("which_command", which_command, "Find where a command is installed",
        {"command": {"type": "string", "description": "Command name to look up", "required": True}})
    registry.register("path_info", path_info, "Show all directories in $PATH", {})
    registry.register("installed_shells", installed_shells, "List available shells", {})
    registry.register("hostname_info", hostname_info, "Show hostname and IP addresses", {})
    registry.register("user_info", user_info, "Show current user info, who is logged in", {})
    registry.register("load_average", load_average, "Show system load average", {})
    registry.register("boot_time", boot_time, "Show when the system last booted", {})
    registry.register("locale_info", locale_info, "Show locale and timezone settings", {})
