"""
Local NLP — zero API, zero cloud.

Provides:
  - Keyword-based intent extraction
  - Fuzzy command matching (rapidfuzz if available, else difflib)
  - Entity extraction: paths, numbers, IPs, URLs, ports, emails
  - Command suggestion when nothing matches

Used as Tier 2 fallback after fast regex rules fail.
"""
import re
import logging
from typing import Optional
from core.intent_parser import IntentResult

log = logging.getLogger("cogman.nlp")


# ── Fuzzy matching ───────────────────────────────────────────────────────────

def _fuzzy_ratio(a: str, b: str) -> float:
    """Returns similarity 0.0–1.0 using rapidfuzz or difflib."""
    try:
        from rapidfuzz import fuzz
        return fuzz.partial_ratio(a, b) / 100.0
    except ImportError:
        from difflib import SequenceMatcher
        return SequenceMatcher(None, a, b).ratio()


# ── Entity extractors ────────────────────────────────────────────────────────

def extract_path(text: str) -> Optional[str]:
    m = re.search(r"(?:~|/)[^\s,;\"']+", text)
    return m.group(0) if m else None


def extract_number(text: str) -> Optional[float]:
    m = re.search(r"\b(\d+(?:\.\d+)?)\b", text)
    return float(m.group(1)) if m else None


def extract_int(text: str) -> Optional[int]:
    n = extract_number(text)
    return int(n) if n is not None else None


def extract_url(text: str) -> Optional[str]:
    m = re.search(r"https?://\S+", text)
    return m.group(0) if m else None


def extract_port(text: str) -> Optional[int]:
    m = re.search(r"\bport\s+(\d+)\b|\b(\d{2,5})\b", text, re.IGNORECASE)
    if m:
        val = int(m.group(1) or m.group(2))
        if 1 <= val <= 65535:
            return val
    return None


def extract_hostname(text: str) -> Optional[str]:
    m = re.search(r"\b(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}\b", text)
    return m.group(0) if m else None


def extract_ip(text: str) -> Optional[str]:
    m = re.search(r"\b(\d{1,3}\.){3}\d{1,3}\b", text)
    return m.group(0) if m else None


def extract_quoted(text: str) -> Optional[str]:
    m = re.search(r'["\'](.+?)["\']', text)
    return m.group(1) if m else None


def extract_email(text: str) -> Optional[str]:
    m = re.search(r"\b[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}\b", text)
    return m.group(0) if m else None


# ── Keyword → tool mapping (local NLP fallback) ───────────────────────────────

# Each entry: (keywords_any, tool, arg_builder)
# Matched when ANY keyword from the list appears in the lowercased input.
_KEYWORD_RULES: list[tuple[list[str], str, callable]] = [
    # System
    (["time", "clock", "hour"],             "get_time",     lambda t: {}),
    (["date", "today", "day"],              "get_date",     lambda t: {}),
    (["disk", "storage", "space"],          "disk_usage",   lambda t: {}),
    (["ram", "memory"],                     "memory_usage", lambda t: {}),
    (["cpu", "processor", "cores"],         "cpu_usage",    lambda t: {}),
    # docker keywords must appear before generic "running" to avoid collision
    (["docker ps", "docker containers"],    "docker_ps",    lambda t: {}),
    (["docker images"],                     "docker_images",lambda t: {}),
    (["process", "processes", "running"],   "list_processes", lambda t: {}),
    (["screenshot", "capture screen"],      "screenshot",   lambda t: {}),
    (["lock screen", "lock pc"],            "lock_screen",  lambda t: {}),
    (["volume"],                            "set_volume",   lambda t: {"level": extract_int(t) or 50}),
    (["mute", "unmute", "silence"],         "mute_toggle",  lambda t: {}),
    (["battery", "charge"],                 "battery_status", lambda t: {}),
    (["network", "wifi"],                   "network_info", lambda t: {}),
    # Power
    (["suspend", "sleep"],                  "suspend",      lambda t: {}),
    (["hibernate"],                         "hibernate",    lambda t: {}),
    (["reboot", "restart"],                 "reboot",       lambda t: {}),
    (["shutdown", "power off"],             "shutdown",     lambda t: {}),
    (["brightness"],                        "set_brightness", lambda t: {"percent": extract_int(t) or 70}),
    # Network
    (["ping"],                              "ping",         lambda t: {"host": extract_hostname(t) or extract_ip(t) or "google.com"}),
    (["traceroute", "trace route"],         "traceroute",   lambda t: {"host": extract_hostname(t) or "google.com"}),
    (["dns", "lookup", "resolve"],          "dns_lookup",   lambda t: {"domain": extract_hostname(t) or t.split()[-1]}),
    (["public ip", "my ip", "external ip"],"get_public_ip",lambda t: {}),
    (["local ip", "private ip"],            "get_local_ip", lambda t: {}),
    (["open port", "listening port"],       "list_open_ports", lambda t: {}),
    (["port", "using port"],                "find_process_by_port", lambda t: {"port": extract_port(t) or 80}),
    (["firewall"],                          "firewall_status", lambda t: {}),
    (["download"],                          "download_file",lambda t: {"url": extract_url(t) or ""}),
    (["wifi", "wireless", "wlan"],          "wifi_networks",lambda t: {}),
    (["speed test", "internet speed"],      "speed_test",   lambda t: {}),
    # Files
    (["list files", "ls", "dir"],           "list_files",   lambda t: {"path": extract_path(t) or "~"}),
    (["read file", "cat", "show file"],     "read_file",    lambda t: {"path": extract_path(t) or ""}),
    (["find file", "search file"],          "find_files",   lambda t: {"pattern": extract_quoted(t) or "*.py"}),
    (["diff", "compare files"],             "file_diff",    lambda t: {}),
    (["hash", "checksum", "sha", "md5"],    "hash_file",    lambda t: {"file": extract_path(t) or ""}),
    (["extract", "unzip", "untar"],         "extract",      lambda t: {"archive": extract_path(t) or ""}),
    # Git
    (["git status"],                        "git_status",   lambda t: {}),
    (["git log", "git history"],            "git_log",      lambda t: {}),
    (["git diff"],                          "git_diff",     lambda t: {}),
    (["git push"],                          "git_push",     lambda t: {}),
    (["git pull"],                          "git_pull",     lambda t: {}),
    (["git branch"],                        "git_branch",   lambda t: {}),
    (["git commit"],                        "git_commit",   lambda t: {"message": extract_quoted(t) or "update"}),
    (["git clone"],                         "git_clone",    lambda t: {"url": extract_url(t) or ""}),
    (["git stash"],                         "git_stash",    lambda t: {"action": "push"}),
    # Docker (additional specifics)
    (["docker logs"],                       "docker_logs",  lambda t: {"name_or_id": t.split()[-1]}),
    (["docker stop"],                       "docker_stop",  lambda t: {"name_or_id": t.split()[-1]}),
    (["docker start"],                      "docker_start", lambda t: {"name_or_id": t.split()[-1]}),
    (["docker stats"],                      "docker_stats", lambda t: {}),
    # Services
    (["service status", "systemctl status"],"service_status",lambda t: {"name": t.split()[-1]}),
    (["failed services"],                   "failed_services", lambda t: {}),
    (["running services"],                  "list_services",lambda t: {"state": "running"}),
    (["service logs"],                      "service_logs", lambda t: {"name": t.split()[-1]}),
    # Packages
    (["install package", "apt install"],    "apt_install",  lambda t: {"package": t.split()[-1]}),
    (["remove package", "apt remove"],      "apt_remove",   lambda t: {"package": t.split()[-1]}),
    (["apt update", "update packages"],     "apt_update",   lambda t: {}),
    (["apt upgrade", "upgrade packages"],   "apt_upgrade",  lambda t: {}),
    (["apt search", "search package"],      "apt_search",   lambda t: {"query": t.split()[-1]}),
    (["pip install"],                       "pip_install",  lambda t: {"package": t.split()[-1]}),
    (["pip list", "python packages"],       "pip_list",     lambda t: {}),
    # System info
    (["system info", "sysinfo", "about this machine"], "system_info", lambda t: {}),
    (["os release", "linux version", "distro"], "os_release", lambda t: {}),
    (["kernel", "uname"],                   "kernel_info",  lambda t: {}),
    (["cpu info", "processor info"],        "cpu_info",     lambda t: {}),
    (["uptime", "how long"],               "system_uptime",lambda t: {}),
    (["load average", "load avg"],         "load_average", lambda t: {}),
    (["temperature", "temp", "sensor"],    "sensors",      lambda t: {}),
    (["usb devices", "lsusb"],             "usb_devices",  lambda t: {}),
    (["pci devices", "lspci"],             "pci_devices",  lambda t: {}),
    (["environment", "env vars"],          "env_vars",     lambda t: {}),
    (["boot time", "last boot"],           "boot_time",    lambda t: {}),
    # Misc
    (["clipboard", "paste"],               "clipboard_paste", lambda t: {}),
    (["copy to clipboard"],                "clipboard_copy",lambda t: {"text": extract_quoted(t) or t}),
    (["cron", "crontab"],                  "cron_list",    lambda t: {}),
    (["calculate", "math", "compute"],     "calculate",    lambda t: {"expression": re.sub(r"(?:calculate|math|compute)\s*", "", t, flags=re.I).strip()}),
    (["weather"],                          "get_weather",  lambda t: {"city": re.sub(r"weather\s*(in|for)?\s*", "", t, flags=re.I).strip() or ""}),
    (["notify", "notification", "remind"], "notify",       lambda t: {"title": "cogman", "message": re.sub(r"(?:notify|remind me|notification)\s*(about)?\s*", "", t, flags=re.I).strip()}),
    (["top processes", "heavy processes"],  "top_processes",lambda t: {}),
    (["process info", "process details"],   "get_process_info", lambda t: {"name_or_pid": t.split()[-1]}),
    (["windows", "open windows"],          "list_windows", lambda t: {}),
    (["workspaces", "desktops"],           "list_workspaces", lambda t: {}),
    (["users", "who is logged"],           "who_is_logged_in", lambda t: {}),
    (["whoami", "current user", "who am i"], "current_user", lambda t: {}),
    (["ssh keys"],                         "list_ssh_keys",lambda t: {}),
    (["media info", "file info"],          "get_media_info",lambda t: {"file": extract_path(t) or ""}),
    (["journal", "system logs", "journalctl"], "journal_logs", lambda t: {}),
    (["dmesg", "kernel messages"],         "dmesg",        lambda t: {}),
    (["syslog", "system log"],             "syslog",       lambda t: {}),
    (["open"],                             "open_app",     lambda t: {"app": re.sub(r"open\s*", "", t, flags=re.I).strip()}),
    (["run", "execute", "shell"],          "run_shell",    lambda t: {"command": re.sub(r"(?:run|execute|shell)\s*", "", t, flags=re.I).strip()}),
    (["search", "google", "look up"],      "web_search",   lambda t: {"query": re.sub(r"(?:search|google|look up)\s*(for)?\s*", "", t, flags=re.I).strip()}),
    (["remember", "note", "save fact"],    "save_memory",  lambda t: {"content": re.sub(r"(?:remember|note|save fact that)\s*", "", t, flags=re.I).strip()}),
    (["recall", "what do you know"],       "search_memory",lambda t: {"query": re.sub(r"(?:recall|what do you know about)\s*", "", t, flags=re.I).strip()}),
]


def parse_keywords(text: str) -> Optional[IntentResult]:
    """Match using keyword presence. Faster than fuzzy, covers broad categories."""
    t = text.lower().strip()

    for keywords, tool, builder in _KEYWORD_RULES:
        if any(kw in t for kw in keywords):
            try:
                args = builder(t)
                return IntentResult(tool=tool, args=args, confidence=0.6, source="keyword")
            except Exception as e:
                log.debug("Keyword builder failed for %s: %s", tool, e)

    return None


# ── Fuzzy matching against known tool descriptions ────────────────────────────

_TOOL_DESCRIPTIONS: dict[str, str] = {}
_TOOL_DESCRIPTIONS_REGISTRY_ID: int = -1   # track which registry was indexed


def _load_tool_descriptions(registry) -> None:
    global _TOOL_DESCRIPTIONS, _TOOL_DESCRIPTIONS_REGISTRY_ID
    rid = id(registry)
    if rid != _TOOL_DESCRIPTIONS_REGISTRY_ID:
        _TOOL_DESCRIPTIONS = {t.name: t.description.lower() for t in registry._tools.values()}
        _TOOL_DESCRIPTIONS_REGISTRY_ID = rid


def parse_fuzzy(text: str, registry, threshold: float = 0.55) -> Optional[IntentResult]:
    """
    Fuzzy-match the input against all tool descriptions.
    Returns the best match if confidence ≥ threshold.
    """
    _load_tool_descriptions(registry)
    t = text.lower().strip()

    best_tool, best_score = None, 0.0
    for name, desc in _TOOL_DESCRIPTIONS.items():
        score = _fuzzy_ratio(t, desc)
        if score > best_score:
            best_score, best_tool = score, name

    if best_tool and best_score >= threshold:
        log.debug("Fuzzy match: %s (score=%.2f)", best_tool, best_score)
        return IntentResult(tool=best_tool, args={}, confidence=best_score * 0.85, source="fuzzy")

    return None


def suggest_commands(text: str, registry, top_n: int = 3) -> list[str]:
    """Return top-N most similar tool names for user suggestions."""
    _load_tool_descriptions(registry)
    t = text.lower().strip()

    scored = [
        (name, _fuzzy_ratio(t, desc))
        for name, desc in _TOOL_DESCRIPTIONS.items()
    ]
    scored.sort(key=lambda x: x[1], reverse=True)
    return [name for name, _ in scored[:top_n]]
