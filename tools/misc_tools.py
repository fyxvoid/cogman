"""Misc tools: clipboard, notifications, cron, calculator, media, user mgmt."""
import os
import shutil
import logging
import subprocess
from core.tool_registry import ToolRegistry
from core.system_controller import run_shell
from core.safety import confirm

log = logging.getLogger("cogman.tools.misc")


# ─── CLIPBOARD ──────────────────────────────────────────────────────────────

def clipboard_copy(text: str) -> str:
    for cmd in [["xclip", "-selection", "clipboard"], ["xsel", "--clipboard", "--input"],
                ["wl-copy"]]:
        if shutil.which(cmd[0]):
            try:
                proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
                proc.communicate(input=text.encode())
                return f"Copied to clipboard ({len(text)} chars)"
            except Exception as e:
                continue
    return "No clipboard tool found — install xclip: sudo apt install xclip"


def clipboard_paste() -> str:
    for cmd in [["xclip", "-selection", "clipboard", "-o"],
                ["xsel", "--clipboard", "--output"], ["wl-paste"]]:
        if shutil.which(cmd[0]):
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
                return result.stdout or "(clipboard is empty)"
            except Exception:
                continue
    return "No clipboard tool found"


# ─── NOTIFICATIONS ──────────────────────────────────────────────────────────

def notify(title: str, message: str = "", urgency: str = "normal", timeout: int = 5000) -> str:
    if not shutil.which("notify-send"):
        print(f"\n[{title}] {message}")
        return f"(notify-send not available — printed to terminal)"
    urgency = urgency if urgency in ("low", "normal", "critical") else "normal"
    result = run_shell(f"notify-send -u {urgency} -t {timeout} '{title}' '{message}'")
    return f"Notification sent: {title}"


# ─── CRON ───────────────────────────────────────────────────────────────────

def cron_list() -> str:
    return run_shell("crontab -l 2>/dev/null || echo '(no crontab for current user)'")


def cron_add(schedule: str, command: str) -> str:
    """Add a cron job. schedule format: '* * * * *' (min hr dom mon dow)"""
    if not confirm(f"Add cron job: [{schedule}] {command}?"):
        return "Cancelled."
    current = run_shell("crontab -l 2>/dev/null || true")
    new_job = f"{schedule} {command}"
    new_crontab = (current.strip() + "\n" + new_job).strip() + "\n"
    proc = subprocess.run(["crontab", "-"], input=new_crontab.encode(), capture_output=True)
    if proc.returncode == 0:
        return f"Cron job added: {new_job}"
    return f"Cron error: {proc.stderr.decode()}"


def cron_remove(pattern: str) -> str:
    if not confirm(f"Remove cron jobs matching '{pattern}'?"):
        return "Cancelled."
    current = run_shell("crontab -l 2>/dev/null || true")
    lines = [l for l in current.split("\n") if pattern not in l]
    new_crontab = "\n".join(lines).strip() + "\n"
    proc = subprocess.run(["crontab", "-"], input=new_crontab.encode(), capture_output=True)
    return f"Removed cron jobs matching '{pattern}'" if proc.returncode == 0 else f"Error: {proc.stderr.decode()}"


# ─── CALCULATOR ─────────────────────────────────────────────────────────────

def calculate(expression: str) -> str:
    import math
    safe_globals = {
        "__builtins__": {},
        "abs": abs, "round": round, "min": min, "max": max, "sum": sum,
        "pow": pow, "int": int, "float": float,
        "sqrt": math.sqrt, "log": math.log, "log2": math.log2, "log10": math.log10,
        "sin": math.sin, "cos": math.cos, "tan": math.tan,
        "asin": math.asin, "acos": math.acos, "atan": math.atan, "atan2": math.atan2,
        "pi": math.pi, "e": math.e, "inf": math.inf,
        "floor": math.floor, "ceil": math.ceil, "factorial": math.factorial,
    }
    try:
        result = eval(expression, safe_globals)
        return f"{expression} = {result}"
    except ZeroDivisionError:
        return "Error: division by zero"
    except Exception as e:
        # Fallback to bc
        if shutil.which("bc"):
            return run_shell(f"echo '{expression}' | bc -l 2>/dev/null")
        return f"Calculation error: {e}"


def unit_convert(value: float, from_unit: str, to_unit: str) -> str:
    conversions = {
        # Length
        ("km", "m"): 1000, ("m", "cm"): 100, ("cm", "mm"): 10,
        ("km", "mile"): 0.621371, ("mile", "km"): 1.60934,
        ("m", "ft"): 3.28084, ("ft", "m"): 0.3048,
        ("inch", "cm"): 2.54, ("cm", "inch"): 0.393701,
        # Weight
        ("kg", "lb"): 2.20462, ("lb", "kg"): 0.453592,
        ("kg", "g"): 1000, ("g", "mg"): 1000,
        # Temperature
        ("c", "f"): None, ("f", "c"): None, ("c", "k"): None, ("k", "c"): None,
        # Data
        ("gb", "mb"): 1024, ("mb", "kb"): 1024, ("kb", "b"): 1024,
        ("tb", "gb"): 1024, ("gib", "mib"): 1024,
    }

    from_u = from_unit.lower()
    to_u = to_unit.lower()

    # Temperature special cases
    if from_u == "c" and to_u == "f":
        return f"{value}°C = {value * 9/5 + 32:.4f}°F"
    if from_u == "f" and to_u == "c":
        return f"{value}°F = {(value - 32) * 5/9:.4f}°C"
    if from_u == "c" and to_u == "k":
        return f"{value}°C = {value + 273.15:.4f}K"
    if from_u == "k" and to_u == "c":
        return f"{value}K = {value - 273.15:.4f}°C"

    factor = conversions.get((from_u, to_u))
    if factor:
        return f"{value} {from_unit} = {value * factor:.6g} {to_unit}"

    # Try reverse
    factor = conversions.get((to_u, from_u))
    if factor:
        return f"{value} {from_unit} = {value / factor:.6g} {to_unit}"

    return f"No conversion found for {from_unit} → {to_unit}"


# ─── MEDIA ──────────────────────────────────────────────────────────────────

def play_audio(file: str) -> str:
    file = os.path.expanduser(file)
    for player in ["mpv", "vlc", "aplay", "paplay", "ffplay"]:
        if shutil.which(player):
            subprocess.Popen([player, file], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return f"Playing with {player}: {file}"
    return "No audio player found — install mpv: sudo apt install mpv"


def play_video(file: str) -> str:
    file = os.path.expanduser(file)
    for player in ["mpv", "vlc", "totem", "xdg-open"]:
        if shutil.which(player):
            subprocess.Popen([player, file], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return f"Playing with {player}: {file}"
    return "No video player found"


def ffmpeg_convert(input_: str, output: str, options: str = "") -> str:
    if not shutil.which("ffmpeg"):
        return "ffmpeg not installed: sudo apt install ffmpeg"
    input_ = os.path.expanduser(input_)
    output = os.path.expanduser(output)
    return run_shell(f"ffmpeg -i '{input_}' {options} '{output}' 2>&1 | tail -5")


def get_media_info(file: str) -> str:
    file = os.path.expanduser(file)
    if shutil.which("ffprobe"):
        return run_shell(f"ffprobe -v quiet -print_format json -show_format -show_streams '{file}' 2>&1 | head -40")
    if shutil.which("mediainfo"):
        return run_shell(f"mediainfo '{file}' 2>&1 | head -30")
    return "Install ffmpeg or mediainfo for media info"


# ─── USER MANAGEMENT ────────────────────────────────────────────────────────

def list_users() -> str:
    return run_shell("getent passwd | awk -F: '$3 >= 1000 {print $1, $5, $6}' | head -20")


def current_user() -> str:
    return run_shell("id && echo '' && groups")


def who_is_logged_in() -> str:
    return run_shell("who && w 2>/dev/null")


def add_user(username: str) -> str:
    if not confirm(f"Create system user '{username}'?"):
        return "Cancelled."
    return run_shell(f"sudo adduser {username} 2>&1")


def user_groups(username: str = "") -> str:
    if username:
        return run_shell(f"groups {username}")
    return run_shell("groups")


def add_to_group(username: str, group: str) -> str:
    if not confirm(f"Add {username} to group '{group}'?"):
        return "Cancelled."
    return run_shell(f"sudo usermod -aG {group} {username}")


def chmod_file(path: str, permissions: str) -> str:
    path = os.path.expanduser(path)
    if not confirm(f"Set permissions {permissions} on {path}?"):
        return "Cancelled."
    return run_shell(f"chmod {permissions} '{path}'")


def chown_file(path: str, owner: str, recursive: bool = False) -> str:
    path = os.path.expanduser(path)
    if not confirm(f"Change owner of {path} to {owner}?"):
        return "Cancelled."
    flag = "-R" if recursive else ""
    return run_shell(f"sudo chown {flag} {owner} '{path}'")


def file_permissions(path: str) -> str:
    path = os.path.expanduser(path)
    return run_shell(f"ls -la '{path}' && stat '{path}' 2>/dev/null | head -8")


# ─── REGISTER ───────────────────────────────────────────────────────────────

def register_misc_tools(registry: ToolRegistry):
    # Clipboard
    registry.register("clipboard_copy", clipboard_copy, "Copy text to system clipboard",
        {"text": {"type": "string", "description": "Text to copy", "required": True}})
    registry.register("clipboard_paste", clipboard_paste, "Paste text from system clipboard", {})

    # Notifications
    registry.register("notify", notify, "Send a desktop notification",
        {
            "title": {"type": "string", "description": "Notification title", "required": True},
            "message": {"type": "string", "description": "Notification body"},
            "urgency": {"type": "string", "description": "Urgency: low, normal, critical (default: normal)"},
            "timeout": {"type": "integer", "description": "Display time in ms (default: 5000)"},
        })

    # Cron
    registry.register("cron_list", cron_list, "List all crontab jobs", {})
    registry.register("cron_add", cron_add, "Add a new cron job",
        {
            "schedule": {"type": "string", "description": "Cron schedule e.g. '0 9 * * 1-5'", "required": True},
            "command": {"type": "string", "description": "Command to run", "required": True},
        }, requires_confirm=True)
    registry.register("cron_remove", cron_remove, "Remove cron jobs matching a pattern",
        {"pattern": {"type": "string", "description": "Pattern to match in cron entries", "required": True}},
        requires_confirm=True)

    # Calculator
    registry.register("calculate", calculate, "Evaluate a math expression (supports sin, cos, sqrt, pi, etc.)",
        {"expression": {"type": "string", "description": "Math expression e.g. sqrt(144) + pi", "required": True}})
    registry.register("unit_convert", unit_convert, "Convert between units (length, weight, temperature, data)",
        {
            "value": {"type": "number", "description": "Value to convert", "required": True},
            "from_unit": {"type": "string", "description": "Source unit e.g. km, kg, c, gb", "required": True},
            "to_unit": {"type": "string", "description": "Target unit e.g. mile, lb, f, mb", "required": True},
        })

    # Media
    registry.register("play_audio", play_audio, "Play an audio file",
        {"file": {"type": "string", "description": "Audio file path", "required": True}})
    registry.register("play_video", play_video, "Play a video file",
        {"file": {"type": "string", "description": "Video file path", "required": True}})
    registry.register("ffmpeg_convert", ffmpeg_convert, "Convert media files with ffmpeg",
        {
            "input_": {"type": "string", "description": "Input file path", "required": True},
            "output": {"type": "string", "description": "Output file path", "required": True},
            "options": {"type": "string", "description": "Extra ffmpeg options e.g. -vcodec h264"},
        })
    registry.register("get_media_info", get_media_info, "Get metadata info about a media file",
        {"file": {"type": "string", "description": "Media file path", "required": True}})

    # User management
    registry.register("list_users", list_users, "List system users", {})
    registry.register("current_user", current_user, "Show current user identity and groups", {})
    registry.register("who_is_logged_in", who_is_logged_in, "Show who is currently logged into the system", {})
    registry.register("add_user", add_user, "Create a new system user",
        {"username": {"type": "string", "description": "Username to create", "required": True}},
        requires_confirm=True)
    registry.register("user_groups", user_groups, "Show groups for a user",
        {"username": {"type": "string", "description": "Username (default: current user)"}})
    registry.register("add_to_group", add_to_group, "Add a user to a system group",
        {
            "username": {"type": "string", "description": "Username", "required": True},
            "group": {"type": "string", "description": "Group name", "required": True},
        }, requires_confirm=True)
    registry.register("chmod_file", chmod_file, "Change file/directory permissions",
        {
            "path": {"type": "string", "description": "File or directory path", "required": True},
            "permissions": {"type": "string", "description": "Permission mode e.g. 755, 644, +x", "required": True},
        }, requires_confirm=True)
    registry.register("chown_file", chown_file, "Change file/directory owner",
        {
            "path": {"type": "string", "description": "File or directory path", "required": True},
            "owner": {"type": "string", "description": "Owner e.g. user:group", "required": True},
            "recursive": {"type": "boolean", "description": "Apply recursively"},
        }, requires_confirm=True)
    registry.register("file_permissions", file_permissions, "Show file permissions and ownership",
        {"path": {"type": "string", "description": "File or directory path", "required": True}})
