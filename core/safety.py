import re
import logging
import shlex
from typing import Tuple
from core.config import LOG_ALL_ACTIONS, LOG_DIR

DANGEROUS_COMMANDS = [
    "rm -rf /", ":(){ :|:& };:", "dd if=/dev/zero",
    "mkfs", "shutdown -h now", "reboot", "halt",
    "chmod -R 777 /", "> /dev/sda", "dd if=/dev/random",
    "fork bomb", "mv /* /dev/null", "cat /dev/null >",
    "shred /dev", "wipefs", "> /etc/passwd",
    "curl | bash", "wget -O- | bash", "curl | sh", "wget | sh",
]

REQUIRE_CONFIRM = [
    "rm", "sudo", "kill", "pkill", "reboot", "shutdown",
    "systemctl stop", "systemctl disable", "apt-get remove",
    "apt-get purge", "docker rm", "docker rmi", "chmod", "chown",
    "git push", "git reset --hard", "crontab",
]

log = logging.getLogger("cogman.safety")
_action_log = logging.getLogger("cogman.actions")

_fh = logging.FileHandler(str(LOG_DIR / "actions.log"))
_fh.setFormatter(logging.Formatter("%(asctime)s | %(message)s"))
_action_log.addHandler(_fh)
_action_log.setLevel(logging.INFO)


def check_command(cmd: str) -> Tuple[bool, str]:
    """Returns (is_safe, reason). Blocks or warns on dangerous patterns."""
    cmd_lower = cmd.strip().lower()

    for dangerous in DANGEROUS_COMMANDS:
        if dangerous in cmd_lower:
            return False, f"Blocked: matches dangerous pattern '{dangerous}'"

    try:
        parts = shlex.split(cmd)
    except ValueError:
        parts = cmd.split()

    if parts:
        base = parts[0].split("/")[-1]
        if base in REQUIRE_CONFIRM:
            return True, f"warn:Command uses '{base}' — requires confirmation"

    if re.search(r";\s*(rm|dd|mkfs|format)", cmd_lower):
        return False, "Blocked: chained destructive command detected"

    if "> /dev/" in cmd or ">/dev/" in cmd:
        return False, "Blocked: writing to device files"

    return True, "ok"


def validate_path(path: str) -> Tuple[bool, str]:
    """Prevent path traversal and writes to system dirs."""
    resolved = path
    system_dirs = ["/etc", "/sys", "/proc", "/boot", "/dev", "/bin", "/sbin", "/usr/bin"]
    for d in system_dirs:
        if resolved.startswith(d):
            return False, f"Blocked: access to system path '{d}'"
    if ".." in path:
        return False, "Blocked: path traversal detected"
    return True, "ok"


def log_action(tool: str, args: dict, result: str):
    if LOG_ALL_ACTIONS:
        _action_log.info("TOOL=%s ARGS=%s RESULT=%s", tool, args, result[:200])


def confirm(prompt: str) -> bool:
    """Interactive confirmation for risky actions."""
    try:
        answer = input(f"\n[cogman] {prompt} (y/N): ").strip().lower()
        return answer in ("y", "yes")
    except (EOFError, KeyboardInterrupt):
        return False
