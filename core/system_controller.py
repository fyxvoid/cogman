import subprocess
import shutil
import logging
import os
import time
from typing import Optional

log = logging.getLogger("cogman.system")

APP_MAP = {
    "browser": ["xdg-open", "https://"],
    "chrome": ["google-chrome"],
    "chromium": ["chromium-browser"],
    "firefox": ["firefox"],
    "terminal": ["x-terminal-emulator"],
    "file_manager": ["xdg-open", os.path.expanduser("~")],
    "text_editor": ["xdg-open", "~"],
    "calculator": ["gnome-calculator", "kcalc", "galculator"],
    "settings": ["gnome-control-center", "systemsettings5"],
}


def run_shell(command: str, timeout: int = 30) -> str:
    try:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True, timeout=timeout
        )
        out = result.stdout.strip()
        err = result.stderr.strip()
        if result.returncode != 0:
            return f"[exit {result.returncode}] {err or out}"
        return out or "(command completed with no output)"
    except subprocess.TimeoutExpired:
        return f"Command timed out after {timeout}s"
    except Exception as e:
        return f"Shell error: {e}"


def open_app(app: str) -> str:
    app_key = app.lower().strip()
    candidates = APP_MAP.get(app_key, [app_key])

    for cmd_parts in [candidates]:
        bin_name = cmd_parts[0]
        if shutil.which(bin_name):
            try:
                subprocess.Popen(cmd_parts, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return f"Opened {app}"
            except Exception as e:
                return f"Failed to open {app}: {e}"

    # Fallback: try xdg-open
    try:
        subprocess.Popen(["xdg-open", app_key], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return f"Attempted to open '{app}' via xdg-open"
    except Exception as e:
        return f"Could not open '{app}': {e}"


def get_time() -> str:
    return time.strftime("Current time: %H:%M:%S %Z")


def get_date() -> str:
    return time.strftime("Today is %A, %B %d, %Y")


def screenshot(path: str = None) -> str:
    path = path or os.path.expanduser(f"~/screenshot_{int(time.time())}.png")
    for tool in [["scrot", path], ["import", "-window", "root", path], ["gnome-screenshot", "-f", path]]:
        if shutil.which(tool[0]):
            result = subprocess.run(tool, capture_output=True)
            if result.returncode == 0:
                return f"Screenshot saved to {path}"
    return "No screenshot tool found (install scrot or gnome-screenshot)"


def lock_screen() -> str:
    for cmd in [["loginctl", "lock-session"], ["gnome-screensaver-command", "--lock"], ["xscreensaver-command", "-lock"]]:
        if shutil.which(cmd[0]):
            subprocess.Popen(cmd)
            return "Screen locked"
    return "Could not lock screen — no locker found"


def set_volume(level: int) -> str:
    level = max(0, min(100, level))
    result = run_shell(f"pactl set-sink-volume @DEFAULT_SINK@ {level}%")
    if "error" in result.lower():
        result = run_shell(f"amixer set Master {level}%")
    return f"Volume set to {level}%" if not result.startswith("[exit") else result


def mute_toggle() -> str:
    result = run_shell("pactl set-sink-mute @DEFAULT_SINK@ toggle")
    if result.startswith("[exit"):
        result = run_shell("amixer set Master toggle")
    return "Audio mute toggled"


def kill_process(name: str) -> str:
    result = run_shell(f"pkill -f '{name}'")
    if result.startswith("[exit"):
        return f"No process matching '{name}' found"
    return f"Killed process matching '{name}'"


def list_processes(top: int = 15) -> str:
    return run_shell(f"ps aux --sort=-%cpu | head -{top + 1}")


def network_info() -> str:
    out = run_shell("ip addr show | grep -E 'inet |state ' | head -20")
    wifi = run_shell("iwgetid -r 2>/dev/null || echo 'Not connected to WiFi'")
    return f"Network:\n{out}\nWiFi SSID: {wifi}"


def battery_status() -> str:
    result = run_shell("cat /sys/class/power_supply/BAT*/capacity 2>/dev/null && cat /sys/class/power_supply/BAT*/status 2>/dev/null")
    if not result or result.startswith("[exit"):
        result = run_shell("acpi -b 2>/dev/null || echo 'No battery info available'")
    return result


def type_text(text: str) -> str:
    if not shutil.which("xdotool"):
        return "xdotool not installed — run: sudo apt install xdotool"
    run_shell(f"xdotool type --clearmodifiers '{text}'")
    return f"Typed: {text}"
