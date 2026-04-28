"""Power management: suspend, hibernate, reboot, shutdown, brightness, screen."""
import shutil
import logging
from core.tool_registry import ToolRegistry
from core.system_controller import run_shell
from core.safety import confirm

log = logging.getLogger("cogman.tools.power")


def suspend() -> str:
    if not confirm("Suspend the system?"):
        return "Cancelled."
    return run_shell("systemctl suspend 2>/dev/null || pm-suspend 2>/dev/null || echo 'suspend unavailable'")


def hibernate() -> str:
    if not confirm("Hibernate the system?"):
        return "Cancelled."
    return run_shell("systemctl hibernate 2>/dev/null || pm-hibernate 2>/dev/null || echo 'hibernate unavailable'")


def reboot(delay: int = 0) -> str:
    if not confirm(f"Reboot the system{f' in {delay} minutes' if delay else ''}?"):
        return "Cancelled."
    if delay:
        return run_shell(f"sudo shutdown -r +{delay}")
    return run_shell("sudo reboot")


def shutdown(delay: int = 0) -> str:
    if not confirm(f"Shut down the system{f' in {delay} minutes' if delay else ''}?"):
        return "Cancelled."
    if delay:
        return run_shell(f"sudo shutdown -h +{delay}")
    return run_shell("sudo shutdown -h now")


def cancel_shutdown() -> str:
    return run_shell("sudo shutdown -c 2>/dev/null") or "Shutdown cancelled"


def get_brightness() -> str:
    # Try different brightness interfaces
    for path in [
        "/sys/class/backlight/intel_backlight",
        "/sys/class/backlight/acpi_video0",
        "/sys/class/backlight/amdgpu_bl0",
    ]:
        try:
            with open(f"{path}/brightness") as f:
                current = int(f.read().strip())
            with open(f"{path}/max_brightness") as f:
                max_b = int(f.read().strip())
            pct = round(current / max_b * 100)
            return f"Brightness: {pct}% ({current}/{max_b})"
        except FileNotFoundError:
            continue

    # Try xrandr
    if shutil.which("xrandr"):
        result = run_shell("xrandr --verbose 2>/dev/null | grep -i brightness | head -3")
        if result and "[exit" not in result:
            return result

    return "Brightness control not available (no backlight interface found)"


def set_brightness(percent: int) -> str:
    percent = max(5, min(100, percent))

    # Try brightnessctl first
    if shutil.which("brightnessctl"):
        return run_shell(f"brightnessctl set {percent}%")

    # Try sysfs
    for path in [
        "/sys/class/backlight/intel_backlight",
        "/sys/class/backlight/acpi_video0",
        "/sys/class/backlight/amdgpu_bl0",
    ]:
        try:
            with open(f"{path}/max_brightness") as f:
                max_b = int(f.read().strip())
            value = round(max_b * percent / 100)
            result = run_shell(f"sudo tee {path}/brightness <<< {value}")
            if "[exit" not in result:
                return f"Brightness set to {percent}%"
        except FileNotFoundError:
            continue

    # Try xrandr as fallback
    if shutil.which("xrandr"):
        gamma = percent / 100
        displays = run_shell("xrandr | grep ' connected' | awk '{print $1}'").split()
        for d in displays:
            run_shell(f"xrandr --output {d} --brightness {gamma:.2f}")
        return f"Brightness set to {percent}% via xrandr"

    return "Could not set brightness — install brightnessctl: sudo apt install brightnessctl"


def screen_off() -> str:
    for cmd in ["xset dpms force off", "xrandr --output $(xrandr | grep ' connected' | awk '{print $1}' | head -1) --off"]:
        result = run_shell(cmd)
        if "[exit" not in result:
            return "Screen turned off"
    return "Could not turn off screen"


def screen_on() -> str:
    result = run_shell("xset dpms force on && xset s reset")
    return "Screen turned on" if "[exit" not in result else result


def set_screen_timeout(minutes: int) -> str:
    seconds = minutes * 60
    result = run_shell(f"xset s {seconds} {seconds} && xset dpms {seconds} {seconds} {seconds}")
    return f"Screen timeout set to {minutes} minutes" if "[exit" not in result else result


def power_stats() -> str:
    battery = run_shell("cat /sys/class/power_supply/BAT*/capacity 2>/dev/null && cat /sys/class/power_supply/BAT*/status 2>/dev/null")
    ac = run_shell("cat /sys/class/power_supply/AC*/online 2>/dev/null")
    uptime = run_shell("uptime -p")
    load = run_shell("cat /proc/loadavg")

    ac_str = "AC: Connected" if ac.strip() == "1" else "AC: Unplugged"
    return f"Uptime: {uptime}\nLoad: {load}\n{ac_str}\nBattery: {battery}"


def register_power_tools(registry: ToolRegistry):
    registry.register("suspend", suspend, "Suspend (sleep) the system", {}, requires_confirm=True)
    registry.register("hibernate", hibernate, "Hibernate the system", {}, requires_confirm=True)
    registry.register("reboot", reboot, "Reboot the system",
        {"delay": {"type": "integer", "description": "Delay in minutes (default: 0 = immediate)"}},
        requires_confirm=True)
    registry.register("shutdown", shutdown, "Shut down the system",
        {"delay": {"type": "integer", "description": "Delay in minutes (default: 0 = immediate)"}},
        requires_confirm=True)
    registry.register("cancel_shutdown", cancel_shutdown, "Cancel a scheduled shutdown or reboot", {})
    registry.register("get_brightness", get_brightness, "Get screen brightness level", {})
    registry.register("set_brightness", set_brightness, "Set screen brightness (5–100%)",
        {"percent": {"type": "integer", "description": "Brightness percentage 5-100", "required": True}})
    registry.register("screen_off", screen_off, "Turn the screen off immediately", {})
    registry.register("screen_on", screen_on, "Turn the screen back on", {})
    registry.register("set_screen_timeout", set_screen_timeout, "Set screen auto-off timeout",
        {"minutes": {"type": "integer", "description": "Minutes before screen turns off", "required": True}})
    registry.register("power_stats", power_stats, "Show power, battery, and load stats", {})
