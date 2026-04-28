"""
pattern_engine.py — single source of truth for all tool pattern matching.

Every pattern maps precisely to a tool + exact arguments via named capture groups.
No ambiguity: if a pattern fires, cogman knows exactly what to execute.

Usage:
    from core.pattern_engine import match
    result = match("ping google.com")
    # → IntentResult(tool="ping", args={"host": "google.com"}, ...)
"""
import re
import logging
from typing import Optional, Dict, Any, Callable, List, Tuple
from dataclasses import dataclass

log = logging.getLogger("cogman.pattern_engine")

I = re.IGNORECASE

# ── Result type ───────────────────────────────────────────────────────────────

@dataclass
class IntentResult:
    tool: str
    args: Dict[str, Any]
    confidence: float
    source: str = "pattern"

# ── Pattern registry ──────────────────────────────────────────────────────────

_PATTERNS: List[Tuple[re.Pattern, str, Callable]] = []


def _r(pattern: str, tool: str, builder: Callable = None, flags: int = I):
    _PATTERNS.append((
        re.compile(pattern, flags),
        tool,
        builder or (lambda m, t: {}),
    ))


# ── Arg helpers ───────────────────────────────────────────────────────────────

def _g(m, name: str, default="") -> str:
    try:
        return (m.group(name) or default).strip()
    except IndexError:
        return default

def _gi(m, name: str, default: int = 0) -> int:
    try:
        v = m.group(name)
        return int(v) if v else default
    except (IndexError, ValueError):
        return default

def _gf(m, name: str, default: float = 0.0) -> float:
    try:
        v = m.group(name)
        return float(v) if v else default
    except (IndexError, ValueError):
        return default

def _after(text: str, *words) -> str:
    """Return everything after first occurrence of any word."""
    t = text.strip()
    for w in words:
        idx = t.lower().find(w.lower())
        if idx != -1:
            return t[idx + len(w):].strip()
    return t

def _last_word(text: str) -> str:
    parts = text.strip().split()
    return parts[-1] if parts else ""

def _words_after(text: str, n: int = 1) -> str:
    parts = text.strip().split()
    return " ".join(parts[n:]) if len(parts) > n else ""


# ═══════════════════════════════════════════════════════════════════════════════
# SYSTEM — shell, apps, time, disk, cpu, ram, volume, processes
# ═══════════════════════════════════════════════════════════════════════════════

# run_shell
_r(r"^(?:run|exec(?:ute)?|shell|bash|sh|cmd)\s+(?P<command>.+)$",
   "run_shell", lambda m, t: {"command": _g(m, "command")})
_r(r"^\$\s*(?P<command>.+)$",
   "run_shell", lambda m, t: {"command": _g(m, "command")})
_r(r"^(?:run command|execute command)\s+[\"']?(?P<command>[^\"']+)[\"']?$",
   "run_shell", lambda m, t: {"command": _g(m, "command")})

# open_app
_r(r"(?:open|launch|start|run)\s+(?P<app>firefox|chromium|chrome|google-chrome)",
   "open_app", lambda m, t: {"app": _g(m, "app")})
_r(r"(?:open|launch|start)\s+(?P<app>terminal|konsole|xterm|gnome-terminal|alacritty|kitty)",
   "open_app", lambda m, t: {"app": _g(m, "app")})
_r(r"(?:open|launch|start)\s+(?P<app>file.?manager|nautilus|thunar|dolphin|nemo)",
   "open_app", lambda m, t: {"app": "file_manager"})
_r(r"(?:open|launch|start)\s+(?P<app>browser|web.?browser)",
   "open_app", lambda m, t: {"app": "browser"})
_r(r"(?:open|launch|start)\s+(?P<app>text.?editor|gedit|nano|vim|nvim|code|vscode)",
   "open_app", lambda m, t: {"app": _g(m, "app")})
_r(r"(?:open|launch|start)\s+(?P<app>calculator|galculator|kcalc|gnome-calculator)",
   "open_app", lambda m, t: {"app": "calculator"})
_r(r"(?:open|launch|start)\s+(?P<app>settings|gnome-control-center|systemsettings)",
   "open_app", lambda m, t: {"app": "settings"})
_r(r"(?:open|launch|start)\s+(?P<app>\S+)",
   "open_app", lambda m, t: {"app": _g(m, "app")})

# get_time
_r(r"what(?:'s| is)(?: the)? (?:current )?time",  "get_time")
_r(r"(?:current|show|tell me the|what's) time",    "get_time")
_r(r"what time is it",                             "get_time")
_r(r"time now",                                    "get_time")

# get_date
_r(r"what(?:'s| is)(?: the)? (?:current |today's? )?date", "get_date")
_r(r"(?:what day|today's date|current date)",               "get_date")
_r(r"what(?:'s| is) today",                                 "get_date")

# disk_usage
_r(r"(?:check|show|get|how much|display)\s+(?:disk|storage|drive)\s*(?:usage|space|left|free|available)?(?:\s+(?:on|at)\s+(?P<path>\S+))?",
   "disk_usage", lambda m, t: {"path": _g(m, "path") or "/"})
_r(r"(?:df|disk free|diskspace)(?:\s+(?P<path>\S+))?",
   "disk_usage", lambda m, t: {"path": _g(m, "path") or "/"})
_r(r"how much (?:space|room) (?:is )?(?:left|free|available)",
   "disk_usage")

# memory_usage
_r(r"(?:check|show|get|how much)\s+(?:memory|ram|swap)\s*(?:usage|used|free|available)?", "memory_usage")
_r(r"(?:free|used)\s+(?:memory|ram)",                                                     "memory_usage")
_r(r"memory\s+(?:status|info|stats?)",                                                    "memory_usage")

# cpu_usage
_r(r"(?:check|show|get|what(?:'s| is))\s+(?:the\s+)?cpu\s*(?:usage|load|percent|utilization)?", "cpu_usage")
_r(r"processor\s+(?:usage|load|utilization)",                                                     "cpu_usage")
_r(r"how (?:much|hard) (?:is the )?cpu (?:working|being used)",                                   "cpu_usage")

# screenshot
_r(r"(?:take|capture|grab|make)\s+(?:a\s+)?screenshot(?:\s+(?:to|at|as)\s+(?P<path>\S+))?",
   "screenshot", lambda m, t: {"path": _g(m, "path")})
_r(r"screenshot(?:\s+to\s+(?P<path>\S+))?",
   "screenshot", lambda m, t: {"path": _g(m, "path")})

# lock_screen
_r(r"(?:lock|secure)\s+(?:the\s+)?(?:screen|display|computer|pc|system|session)", "lock_screen")
_r(r"screen\s*lock",                                                                "lock_screen")

# set_volume
_r(r"(?:set|change|put)\s+(?:the\s+)?volume\s+(?:to\s+)?(?P<level>\d+)\s*%?",
   "set_volume", lambda m, t: {"level": _gi(m, "level")})
_r(r"volume\s+(?:to\s+)?(?P<level>\d+)\s*%?",
   "set_volume", lambda m, t: {"level": _gi(m, "level")})
_r(r"(?:turn|crank)\s+(?:volume|sound)\s+(?:up|down)\s+to\s+(?P<level>\d+)",
   "set_volume", lambda m, t: {"level": _gi(m, "level")})

# mute_toggle
_r(r"(?:mute|unmute|toggle\s+mute|silence)\s+(?:the\s+)?(?:audio|sound|volume|mic|speaker)?", "mute_toggle")
_r(r"(?:toggle|switch)\s+(?:audio|sound|mute)",                                                "mute_toggle")

# kill_process
_r(r"(?:kill|end|terminate|force.?quit|stop)\s+(?:process\s+)?(?P<name>.+)",
   "kill_process", lambda m, t: {"name": _g(m, "name")}, flags=I)
_r(r"(?:pkill|killall)\s+(?P<name>\S+)",
   "kill_process", lambda m, t: {"name": _g(m, "name")})

# list_processes
_r(r"(?:list|show|display)\s+(?:all\s+)?(?:running\s+)?processes?", "list_processes")
_r(r"(?:ps|ps aux|process list|running apps)",                       "list_processes")
_r(r"what(?:'s| is) running",                                        "list_processes")

# network_info
_r(r"(?:show|get|display)\s+network\s+(?:info|status|details?|config(?:uration)?)", "network_info")
_r(r"(?:ifconfig|ip addr|network interfaces?)",                                       "network_info")

# battery_status
_r(r"(?:battery|charge)\s*(?:level|status|info|percentage|remaining)?", "battery_status")
_r(r"how much battery (?:is left|do i have|remaining)",                  "battery_status")

# type_text
_r(r"(?:type|write|input|enter)\s+(?:the\s+)?(?:text\s+)?[\"']?(?P<text>[^\"']+)[\"']?(?:\s+into\s+.+)?$",
   "type_text", lambda m, t: {"text": _g(m, "text")})

# ═══════════════════════════════════════════════════════════════════════════════
# FILES
# ═══════════════════════════════════════════════════════════════════════════════

# list_files
_r(r"(?:list|show|display|ls)\s+(?:files?|contents?|dir(?:ectory)?)?\s*(?:in|of|at)?\s+(?P<path>[~./]\S*)",
   "list_files", lambda m, t: {"path": _g(m, "path")})
_r(r"(?:ls|dir)\s+(?P<path>\S+)",
   "list_files", lambda m, t: {"path": _g(m, "path")})
_r(r"(?:list|show)\s+(?:my\s+)?(?:files?|downloads?|documents?|home)",
   "list_files", lambda m, t: {"path": "~"})
_r(r"what(?:'s| is) in (?P<path>\S+)",
   "list_files", lambda m, t: {"path": _g(m, "path")})

# read_file
_r(r"(?:read|cat|show|print|display|open)\s+(?:the\s+)?(?:file\s+)?(?P<path>[~./]\S+)",
   "read_file", lambda m, t: {"path": _g(m, "path")})
_r(r"(?:read|cat|show)\s+(?:the\s+)?(?:contents?\s+of\s+)?(?P<path>\S+\.(?:txt|conf|cfg|ini|log|md|py|js|sh|yaml|yml|json|toml|env))",
   "read_file", lambda m, t: {"path": _g(m, "path")})

# write_file
_r(r"(?:write|save|create)\s+(?:file\s+)?(?P<path>\S+)\s+(?:with\s+(?:content\s+)?)?[\"'](?P<content>[^\"']+)[\"']",
   "write_file", lambda m, t: {"path": _g(m, "path"), "content": _g(m, "content"), "overwrite": True})

# find_files
_r(r"(?:find|search|locate)\s+(?:files?\s+)?(?:matching\s+|named\s+|with\s+extension\s+)?(?P<pattern>\S+)(?:\s+in\s+(?P<directory>\S+))?",
   "find_files", lambda m, t: {"pattern": _g(m, "pattern"), "directory": _g(m, "directory") or "~"})
_r(r"(?:where(?:'s| is)|find)\s+(?P<pattern>\S+\.(?:py|js|sh|txt|log|conf|cfg))\s*(?:files?)?",
   "find_files", lambda m, t: {"pattern": _g(m, "pattern"), "directory": "~"})

# ═══════════════════════════════════════════════════════════════════════════════
# WEB
# ═══════════════════════════════════════════════════════════════════════════════

# web_search
_r(r"(?:search|google|look up|find online|bing|duckduckgo)\s+(?:for\s+)?(?P<query>.+)",
   "web_search", lambda m, t: {"query": _g(m, "query")})
_r(r"(?:what is|who is|how to|why does|when did)\s+(?P<query>.+)\s*\?",
   "web_search", lambda m, t: {"query": _g(m, "query")})

# fetch_url
_r(r"(?:fetch|curl|wget|get|download content from)\s+(?P<url>https?://\S+)",
   "fetch_url", lambda m, t: {"url": _g(m, "url")})

# get_weather
_r(r"(?:weather|forecast)\s+(?:in|for|at)\s+(?P<city>[A-Za-z ]+?)(?:\s*[?.!])?$",
   "get_weather", lambda m, t: {"city": _g(m, "city").strip()})
_r(r"(?:what(?:'s| is)|show|get)\s+the\s+weather(?:\s+(?:in|for)\s+(?P<city>\S+))?",
   "get_weather", lambda m, t: {"city": _g(m, "city")})
_r(r"(?:weather|forecast)(?:\s+(?:in|for)\s+(?P<city>\S+))?",
   "get_weather", lambda m, t: {"city": _g(m, "city")})

# ═══════════════════════════════════════════════════════════════════════════════
# MEMORY
# ═══════════════════════════════════════════════════════════════════════════════

# save_memory
_r(r"(?:remember|memorize|note|save)\s+(?:that\s+)?(?P<content>.+)",
   "save_memory", lambda m, t: {"content": _g(m, "content")})
_r(r"(?:keep in mind|don't forget)\s+(?:that\s+)?(?P<content>.+)",
   "save_memory", lambda m, t: {"content": _g(m, "content")})

# search_memory
_r(r"(?:recall|what do you know about|do you remember|look up in memory)\s+(?P<query>.+)",
   "search_memory", lambda m, t: {"query": _g(m, "query")})
_r(r"(?:memory|remember)\s+(?:search|find|recall)\s+(?P<query>.+)",
   "search_memory", lambda m, t: {"query": _g(m, "query")})

# set_preference
_r(r"(?:set|save|store)\s+(?:my\s+)?preference\s+(?P<key>\S+)\s+(?:to|as|=)\s+(?P<value>.+)",
   "set_preference", lambda m, t: {"key": _g(m, "key"), "value": _g(m, "value")})
_r(r"(?:my\s+)?(?:default|preferred)\s+(?P<key>\S+)\s+(?:is|should be)\s+(?P<value>.+)",
   "set_preference", lambda m, t: {"key": _g(m, "key"), "value": _g(m, "value")})

# get_preference
_r(r"(?:get|what(?:'s| is))\s+(?:my\s+)?preference\s+(?:for\s+)?(?P<key>\S+)",
   "get_preference", lambda m, t: {"key": _g(m, "key")})

# ═══════════════════════════════════════════════════════════════════════════════
# PROCESS MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════════

# process_tree
_r(r"(?:process|task)\s+tree(?:\s+(?:for\s+|of\s+)?(?:pid\s+)?(?P<pid>\d+))?",
   "process_tree", lambda m, t: {"pid": _gi(m, "pid") or None})
_r(r"pstree(?:\s+(?P<pid>\d+))?",
   "process_tree", lambda m, t: {"pid": _gi(m, "pid") or None})

# top_processes
_r(r"(?:top|most|highest)\s+(?P<sort>cpu|memory|ram|mem)\s+(?:consuming\s+)?processes?",
   "top_processes", lambda m, t: {"sort_by": "memory" if "mem" in _g(m, "sort").lower() else "cpu"})
_r(r"(?:what(?:'s| is)|show)\s+(?:using|eating|consuming)\s+(?:the most\s+)?(?P<sort>cpu|memory|ram)",
   "top_processes", lambda m, t: {"sort_by": "memory" if "mem" in _g(m, "sort").lower() else "cpu"})
_r(r"(?:top|htop|heavy|resource.?hungry)\s+processes?",
   "top_processes", lambda m, t: {"sort_by": "cpu"})
_r(r"something is (?:eating|using|consuming|hogging)\s+(?:my\s+)?(?P<sort>cpu|memory|ram|disk)",
   "top_processes", lambda m, t: {"sort_by": "memory" if "mem" in _g(m, "sort").lower() else "cpu"})

# get_process_info
_r(r"(?:info|details?|status)\s+(?:about\s+|of\s+|for\s+)?(?:process\s+|pid\s+)?(?P<name_or_pid>\S+)",
   "get_process_info", lambda m, t: {"name_or_pid": _g(m, "name_or_pid")})
_r(r"(?:what is|show me)\s+(?:process\s+|pid\s+)?(?P<name_or_pid>\d+)",
   "get_process_info", lambda m, t: {"name_or_pid": _g(m, "name_or_pid")})

# set_priority
_r(r"(?:set|change)\s+priority\s+(?:of\s+)?(?:pid\s+)?(?P<pid>\d+)\s+to\s+(?P<priority>-?\d+)",
   "set_priority", lambda m, t: {"pid": _gi(m, "pid"), "priority": _gi(m, "priority")})
_r(r"(?:renice|nice)\s+(?P<pid>\d+)\s+(?:to\s+)?(?P<priority>-?\d+)",
   "set_priority", lambda m, t: {"pid": _gi(m, "pid"), "priority": _gi(m, "priority")})

# run_background
_r(r"(?:run|start|launch)\s+(?P<command>.+)\s+in\s+(?:the\s+)?background",
   "run_background", lambda m, t: {"command": _g(m, "command")})
_r(r"background(?:ify|run)?\s+(?P<command>.+)",
   "run_background", lambda m, t: {"command": _g(m, "command")})

# send_signal
_r(r"send\s+(?:signal\s+)?(?P<sig>SIGTERM|SIGKILL|SIGHUP|SIGINT|SIGSTOP|SIGCONT|TERM|KILL|HUP|INT|STOP|CONT)\s+to\s+(?:pid\s+)?(?P<pid>\d+)",
   "send_signal", lambda m, t: {"pid": _gi(m, "pid"), "sig": _g(m, "sig").replace("SIG", "")})

# find_process_by_port
_r(r"(?:what|who|which)\s+(?:process|program|app|service)\s+(?:is\s+)?(?:using|on|listening\s+on|bound\s+to)\s+port\s+(?P<port>\d+)",
   "find_process_by_port", lambda m, t: {"port": _gi(m, "port")})
_r(r"(?:check|find|show)\s+port\s+(?P<port>\d+)\s+(?:usage|process|owner)",
   "find_process_by_port", lambda m, t: {"port": _gi(m, "port")})
_r(r"port\s+(?P<port>\d+)\s+(?:is\s+)?(?:being\s+)?used\s+by",
   "find_process_by_port", lambda m, t: {"port": _gi(m, "port")})
_r(r"kill\s+(?:the\s+)?(?:thing|process|app)\s+(?:using|on)\s+port\s+(?P<port>\d+)",
   "find_process_by_port", lambda m, t: {"port": _gi(m, "port")})

# wait_for_process
_r(r"wait\s+(?:for\s+)?(?:pid\s+|process\s+)?(?P<pid>\d+)(?:\s+for\s+(?P<timeout>\d+)\s*s(?:ec)?)?",
   "wait_for_process", lambda m, t: {"pid": _gi(m, "pid"), "timeout": _gi(m, "timeout") or 30})

# ═══════════════════════════════════════════════════════════════════════════════
# NETWORK
# ═══════════════════════════════════════════════════════════════════════════════

# ping
_r(r"ping\s+(?P<host>\S+)(?:\s+(?P<count>\d+)\s+times?)?",
   "ping", lambda m, t: {"host": _g(m, "host"), "count": _gi(m, "count") or 4})
_r(r"(?:is\s+)?(?P<host>\S+)\s+(?:reachable|up|online|alive)\??",
   "ping", lambda m, t: {"host": _g(m, "host"), "count": 3})
_r(r"can I (?:reach|connect to)\s+(?P<host>\S+)",
   "ping", lambda m, t: {"host": _g(m, "host"), "count": 3})

# traceroute
_r(r"(?:traceroute|tracepath|trace route)\s+(?:to\s+)?(?P<host>\S+)",
   "traceroute", lambda m, t: {"host": _g(m, "host")})
_r(r"(?:trace|route)\s+(?:to\s+)?(?P<host>\S+)",
   "traceroute", lambda m, t: {"host": _g(m, "host")})

# dns_lookup
_r(r"(?:dns|nslookup|dig|lookup|resolve)\s+(?P<domain>\S+)",
   "dns_lookup", lambda m, t: {"domain": _g(m, "domain")})
_r(r"(?:what(?:'s| is) the (?:ip|address) of|resolve)\s+(?P<domain>\S+)",
   "dns_lookup", lambda m, t: {"domain": _g(m, "domain")})
_r(r"(?:ip|address)\s+(?:of|for)\s+(?P<domain>\S+)",
   "dns_lookup", lambda m, t: {"domain": _g(m, "domain")})

# reverse_dns
_r(r"(?:reverse\s+dns|rdns|reverse\s+lookup)\s+(?:for\s+|of\s+)?(?P<ip>\d+\.\d+\.\d+\.\d+)",
   "reverse_dns", lambda m, t: {"ip": _g(m, "ip")})

# list_open_ports
_r(r"(?:list|show|display|what)\s+(?:all\s+)?(?:open|listening|active)\s+ports?",  "list_open_ports")
_r(r"(?:netstat|ss)\s*(?:-tlnp)?",                                                  "list_open_ports")
_r(r"what ports? (?:are|is)\s+(?:open|listening)",                                  "list_open_ports")

# check_port
_r(r"(?:check|is|test)\s+port\s+(?P<port>\d+)\s+(?:on\s+|at\s+)?(?:open\s+on\s+)?(?P<host>\S+)?",
   "check_port", lambda m, t: {"host": _g(m, "host") or "localhost", "port": _gi(m, "port")})
_r(r"(?:is\s+)?port\s+(?P<port>\d+)\s+(?:open|closed|available)(?:\s+on\s+(?P<host>\S+))?",
   "check_port", lambda m, t: {"host": _g(m, "host") or "localhost", "port": _gi(m, "port")})
_r(r"(?:can I|test) connect(?:ion)?\s+to\s+(?P<host>\S+):(?P<port>\d+)",
   "check_port", lambda m, t: {"host": _g(m, "host"), "port": _gi(m, "port")})

# firewall_status / allow / deny
_r(r"(?:ufw|firewall)\s+status(?:\s+verbose)?",                                "firewall_status")
_r(r"(?:show|check|display)\s+(?:the\s+)?firewall(?:\s+rules?)?",              "firewall_status")
_r(r"(?:ufw|firewall)\s+(?:allow|open|permit)\s+(?:port\s+)?(?P<port>\d+)(?:/(?P<protocol>tcp|udp))?",
   "firewall_allow", lambda m, t: {"port": _gi(m, "port"), "protocol": _g(m, "protocol") or "tcp"})
_r(r"(?:ufw|firewall)\s+(?:deny|block|close)\s+(?:port\s+)?(?P<port>\d+)(?:/(?P<protocol>tcp|udp))?",
   "firewall_deny", lambda m, t: {"port": _gi(m, "port"), "protocol": _g(m, "protocol") or "tcp"})
_r(r"(?:block|deny)\s+port\s+(?P<port>\d+)",
   "firewall_deny", lambda m, t: {"port": _gi(m, "port"), "protocol": "tcp"})

# download_file
_r(r"(?:download|wget|fetch|grab)\s+(?P<url>https?://\S+)(?:\s+(?:to|into|as)\s+(?P<destination>\S+))?",
   "download_file", lambda m, t: {"url": _g(m, "url"), "destination": _g(m, "destination") or "~/Downloads/"})

# get_public_ip
_r(r"(?:(?:what(?:'s| is)|show|get|find)\s+)?(?:my\s+)?(?:public|external|wan|internet)\s+(?:ip|ip.?address|address)",
   "get_public_ip")
_r(r"what(?:'s| is) my ip",  "get_public_ip")

# get_local_ip
_r(r"(?:what(?:'s| is)|show|get)\s+(?:my\s+)?(?:local|private|lan|internal)\s+(?:ip|ip.?address|address)", "get_local_ip")
_r(r"(?:local|private|lan)\s+ip(?:\s+address)?",                                                             "get_local_ip")

# wifi_networks
_r(r"(?:scan|list|show|find|detect)\s+(?:available\s+|nearby\s+)?(?:wifi|wireless|wlan|wi-fi)\s+(?:networks?|ssids?|aps?)?", "wifi_networks")
_r(r"(?:what|which)\s+wifi\s+(?:networks?|signals?)\s+(?:are|can I see)",                                                     "wifi_networks")

# wifi_connect
_r(r"(?:connect|join|switch)\s+(?:to\s+)?(?:wifi|wireless|network)\s+[\"']?(?P<ssid>[^\"']+)[\"']?(?:\s+(?:with\s+)?(?:password\s+)?[\"']?(?P<password>[^\"']+)[\"']?)?",
   "wifi_connect", lambda m, t: {"ssid": _g(m, "ssid"), "password": _g(m, "password")})

# wifi_disconnect
_r(r"(?:disconnect|leave|drop)\s+(?:from\s+)?(?:wifi|wireless|network|internet)", "wifi_disconnect")
_r(r"(?:turn\s+off|disable)\s+wifi",                                               "wifi_disconnect")

# speed_test
_r(r"(?:internet\s+|network\s+|connection\s+)?speed\s*test",          "speed_test")
_r(r"(?:how fast|test)\s+(?:is\s+)?(?:my\s+)?(?:internet|network|connection|bandwidth)", "speed_test")

# ssh_keygen
_r(r"(?:generate|create|make)\s+(?:an?\s+)?ssh\s+key(?:\s+(?:type\s+)?(?P<key_type>ed25519|rsa|ecdsa))?(?:\s+(?:for|with\s+comment)\s+(?P<comment>.+))?",
   "ssh_keygen", lambda m, t: {"key_type": _g(m, "key_type") or "ed25519", "comment": _g(m, "comment")})

# list_ssh_keys
_r(r"(?:list|show|display)\s+(?:my\s+)?ssh\s+keys?",  "list_ssh_keys")
_r(r"(?:what|which)\s+ssh\s+keys?\s+do\s+(?:i|I)\s+have", "list_ssh_keys")

# network_stats
_r(r"(?:network|interface|nic)\s+(?:stats?|statistics|traffic|io|throughput)", "network_stats")
_r(r"(?:how much|show)\s+(?:network\s+)?(?:data|traffic|bandwidth)\s+(?:has been\s+)?(?:sent|received|used)", "network_stats")

# ═══════════════════════════════════════════════════════════════════════════════
# PACKAGE MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════════

# apt_install
_r(r"(?:apt(?:-get)?\s+install|install\s+package|sudo\s+apt\s+install)\s+(?P<package>[\w.\-]+(?:\s+[\w.\-]+)*)",
   "apt_install", lambda m, t: {"package": _g(m, "package")})
_r(r"install\s+(?P<package>[\w.\-]+)\s+(?:via\s+|using\s+|with\s+)?apt",
   "apt_install", lambda m, t: {"package": _g(m, "package")})

# apt_remove
_r(r"(?:apt(?:-get)?\s+remove|remove\s+package|uninstall)\s+(?P<package>[\w.\-]+)",
   "apt_remove", lambda m, t: {"package": _g(m, "package")})

# apt_purge
_r(r"(?:apt(?:-get)?\s+purge|purge)\s+(?P<package>[\w.\-]+)",
   "apt_purge", lambda m, t: {"package": _g(m, "package")})

# apt_update
_r(r"(?:apt(?:-get)?\s+update|update\s+(?:apt\s+)?(?:package\s+)?(?:list|cache|sources?))",  "apt_update")
_r(r"(?:refresh|sync)\s+(?:apt|package)\s+(?:list|cache)",                                    "apt_update")

# apt_upgrade
_r(r"(?:apt(?:-get)?\s+upgrade|upgrade\s+(?:all\s+)?(?:apt\s+)?packages?)",  "apt_upgrade")
_r(r"(?:update|upgrade)\s+(?:my\s+)?system\s+packages?",                      "apt_upgrade")

# apt_search
_r(r"(?:apt(?:-get)?\s+|apt\s+cache\s+)?search\s+(?:package\s+|for\s+)?(?P<query>[\w.\-]+)",
   "apt_search", lambda m, t: {"query": _g(m, "query")})
_r(r"find\s+(?:apt\s+)?package\s+(?:for\s+)?(?P<query>.+)",
   "apt_search", lambda m, t: {"query": _g(m, "query")})

# apt_show
_r(r"(?:apt(?:-get)?\s+show|show\s+package|info\s+(?:about\s+)?package)\s+(?P<package>[\w.\-]+)",
   "apt_show", lambda m, t: {"package": _g(m, "package")})

# apt_list_installed
_r(r"(?:list|show|display)\s+(?:all\s+)?(?:installed|apt)\s+packages?", "apt_list_installed")
_r(r"(?:what\s+packages?|dpkg\s+-l)\s+(?:are\s+)?installed",            "apt_list_installed")

# apt_autoremove
_r(r"(?:apt(?:-get)?\s+autoremove|autoremove|remove\s+unused\s+packages?)",  "apt_autoremove")
_r(r"clean\s+up\s+(?:unused\s+|orphaned\s+)?(?:apt\s+)?packages?",           "apt_autoremove")

# pip_install
_r(r"pip(?:3)?\s+install\s+(?P<package>[\w.\-\[\],]+(?:\s+[\w.\-\[\],]+)*)",
   "pip_install", lambda m, t: {"package": _g(m, "package")})
_r(r"install\s+(?:python\s+(?:package|lib|library)\s+)?(?P<package>[\w.\-]+)\s+(?:via\s+|using\s+|with\s+)?pip",
   "pip_install", lambda m, t: {"package": _g(m, "package")})

# pip_uninstall
_r(r"pip(?:3)?\s+uninstall\s+(?P<package>[\w.\-]+)",
   "pip_uninstall", lambda m, t: {"package": _g(m, "package")})

# pip_list
_r(r"pip(?:3)?\s+list|(?:list|show)\s+(?:installed\s+)?(?:python|pip)\s+packages?",  "pip_list")

# pip_show
_r(r"pip(?:3)?\s+show\s+(?P<package>[\w.\-]+)",
   "pip_show", lambda m, t: {"package": _g(m, "package")})

# pip_outdated
_r(r"pip(?:3)?\s+list\s+--outdated|(?:outdated|old)\s+(?:python\s+|pip\s+)?packages?",  "pip_outdated")

# pip_upgrade
_r(r"pip(?:3)?\s+install\s+--upgrade\s+(?P<package>[\w.\-]+)",
   "pip_upgrade", lambda m, t: {"package": _g(m, "package")})
_r(r"upgrade\s+(?:python\s+package\s+)?(?P<package>[\w.\-]+)\s+(?:via\s+|with\s+)?pip",
   "pip_upgrade", lambda m, t: {"package": _g(m, "package")})

# snap_install / remove / list / refresh
_r(r"snap\s+install\s+(?P<package>[\w.\-]+)(?:\s+(?P<classic>--classic))?",
   "snap_install", lambda m, t: {"package": _g(m, "package"), "classic": bool(_g(m, "classic"))})
_r(r"snap\s+remove\s+(?P<package>[\w.\-]+)",
   "snap_remove", lambda m, t: {"package": _g(m, "package")})
_r(r"snap\s+(?:list|installed)|(?:list|show)\s+snaps?",   "snap_list")
_r(r"snap\s+refresh|update\s+snaps?",                      "snap_refresh")

# flatpak
_r(r"flatpak\s+install\s+(?P<app_id>[\w.\-]+)",
   "flatpak_install", lambda m, t: {"app_id": _g(m, "app_id")})
_r(r"flatpak\s+(?:list|installed)|(?:list|show)\s+flatpaks?",  "flatpak_list")
_r(r"flatpak\s+update|update\s+flatpaks?",                      "flatpak_update")

# npm_install / list
_r(r"npm\s+install\s+(?P<package>[\w.\-@/]+)(?:\s+(?P<global>-g|--global))?",
   "npm_install", lambda m, t: {"package": _g(m, "package"), "global_": bool(_g(m, "global"))})
_r(r"npm\s+(?:list|ls)(?:\s+(?P<global>-g|--global))?",
   "npm_list", lambda m, t: {"global_": bool(_g(m, "global"))})

# cargo_install
_r(r"cargo\s+install\s+(?P<crate>[\w.\-]+)",
   "cargo_install", lambda m, t: {"crate": _g(m, "crate")})

# ═══════════════════════════════════════════════════════════════════════════════
# SERVICES
# ═══════════════════════════════════════════════════════════════════════════════

_svc = r"(?:service\s+)?(?P<name>[\w.\-@]+)"

_r(rf"(?:systemctl\s+status|status\s+(?:of\s+|for\s+)?(?:service\s+)?|check\s+(?:service\s+)?){_svc}",
   "service_status", lambda m, t: {"name": _g(m, "name")})
_r(rf"(?:is\s+)?{_svc}\s+(?:service\s+)?(?:running|active|up|started)",
   "service_status", lambda m, t: {"name": _g(m, "name")})
_r(rf"systemctl\s+start\s+{_svc}",
   "service_start",  lambda m, t: {"name": _g(m, "name")})
_r(rf"start\s+(?:service\s+|the\s+service\s+)?{_svc}",
   "service_start",  lambda m, t: {"name": _g(m, "name")})
_r(rf"systemctl\s+stop\s+{_svc}",
   "service_stop",   lambda m, t: {"name": _g(m, "name")})
_r(rf"stop\s+(?:service\s+|the\s+service\s+)?{_svc}",
   "service_stop",   lambda m, t: {"name": _g(m, "name")})
_r(rf"systemctl\s+restart\s+{_svc}",
   "service_restart", lambda m, t: {"name": _g(m, "name")})
_r(rf"restart\s+(?:service\s+|the\s+service\s+)?{_svc}",
   "service_restart", lambda m, t: {"name": _g(m, "name")})
_r(rf"systemctl\s+reload\s+{_svc}",
   "service_reload",  lambda m, t: {"name": _g(m, "name")})
_r(rf"systemctl\s+enable\s+{_svc}",
   "service_enable",  lambda m, t: {"name": _g(m, "name")})
_r(rf"enable\s+(?:service\s+|autostart\s+for\s+)?{_svc}(?:\s+on\s+boot)?",
   "service_enable",  lambda m, t: {"name": _g(m, "name")})
_r(rf"(?:make\s+)?{_svc}\s+start\s+(?:automatically\s+)?on\s+boot",
   "service_enable",  lambda m, t: {"name": _g(m, "name")})
_r(rf"systemctl\s+disable\s+{_svc}",
   "service_disable", lambda m, t: {"name": _g(m, "name")})
_r(rf"disable\s+(?:service\s+)?{_svc}",
   "service_disable", lambda m, t: {"name": _g(m, "name")})
_r(rf"(?:show\s+|get\s+)?logs?\s+(?:for\s+|of\s+)?(?:service\s+)?(?P<name>[\w.\-@]+)(?:\s+(?:last\s+)?(?P<lines>\d+)\s+lines?)?",
   "service_logs", lambda m, t: {"name": _g(m, "name"), "lines": _gi(m, "lines") or 50})
_r(rf"journalctl\s+(?:-u\s+)?(?P<name>[\w.\-@]+)",
   "service_logs", lambda m, t: {"name": _g(m, "name")})
_r(r"(?:list|show)\s+(?:all\s+)?(?:running|active|enabled|disabled|failed)?\s*services?",
   "list_services", lambda m, t: {"state": "running" if "running" in t.lower() else ("failed" if "failed" in t.lower() else "running")})
_r(r"(?:failed|broken|dead)\s+services?",    "failed_services")
_r(r"services?\s+(?:that\s+)?(?:failed|are\s+failing|crashed)", "failed_services")
_r(r"(?:systemctl\s+)?daemon.?reload",       "daemon_reload")
_r(r"(?:show|get|system)\s+uptime",          "system_uptime")
_r(r"how long\s+(?:has\s+(?:the\s+)?system\s+been\s+)?(?:up|running)", "system_uptime")
_r(r"(?:list|show)\s+(?:systemd\s+)?timers?", "list_timers")

# ═══════════════════════════════════════════════════════════════════════════════
# GIT
# ═══════════════════════════════════════════════════════════════════════════════

_gp = r"(?:\s+(?:in|at|from)\s+(?P<path>\S+))?"   # optional path suffix

_r(rf"git\s+status{_gp}",       "git_status",  lambda m, t: {"path": _g(m, "path") or "."})
_r(rf"(?:show|what(?:'s| is))\s+(?:the\s+)?git\s+status{_gp}", "git_status", lambda m, t: {"path": _g(m, "path") or "."})
_r(rf"git\s+log(?:\s+-(?:n\s+)?(?P<n>\d+))?{_gp}",
   "git_log", lambda m, t: {"path": _g(m, "path") or ".", "n": _gi(m, "n") or 10})
_r(rf"(?:show|git)\s+(?:commit\s+)?history{_gp}",
   "git_log", lambda m, t: {"path": _g(m, "path") or ".", "n": 10})
_r(rf"git\s+diff(?:\s+(?P<staged>--staged|--cached))?{_gp}",
   "git_diff", lambda m, t: {"path": _g(m, "path") or ".", "staged": bool(_g(m, "staged"))})
_r(r"git\s+add\s+(?P<files>.+)",
   "git_add", lambda m, t: {"files": _g(m, "files"), "path": "."})
_r(r"(?:stage|git\s+add)\s+(?:all\s+)?(?:changes?|files?)",
   "git_add", lambda m, t: {"files": ".", "path": "."})
_r(r"git\s+commit\s+(?:-m\s+)?[\"']?(?P<message>[^\"']+)[\"']?(?:\s+--all)?",
   "git_commit", lambda m, t: {"message": _g(m, "message"), "path": "."})
_r(r"commit\s+(?:with\s+message\s+)?[\"'](?P<message>[^\"']+)[\"']",
   "git_commit", lambda m, t: {"message": _g(m, "message"), "path": "."})
_r(r"git\s+push(?:\s+(?P<remote>\S+))?(?:\s+(?P<branch>\S+))?",
   "git_push", lambda m, t: {"remote": _g(m, "remote") or "origin", "branch": _g(m, "branch")})
_r(r"(?:push|publish)\s+(?:to\s+)?(?:remote|origin|github|gitlab)?",
   "git_push", lambda m, t: {"remote": "origin", "branch": ""})
_r(r"git\s+pull(?:\s+(?P<remote>\S+))?(?:\s+(?P<branch>\S+))?",
   "git_pull", lambda m, t: {"remote": _g(m, "remote") or "origin", "branch": _g(m, "branch")})
_r(r"git\s+clone\s+(?P<url>\S+)(?:\s+(?P<destination>\S+))?",
   "git_clone", lambda m, t: {"url": _g(m, "url"), "destination": _g(m, "destination")})
_r(r"clone\s+(?:repo(?:sitory)?\s+)?(?P<url>https?://\S+|git@\S+)",
   "git_clone", lambda m, t: {"url": _g(m, "url")})
_r(rf"git\s+branch(?:\s+(?P<all>-a|--all))?{_gp}",
   "git_branch", lambda m, t: {"path": _g(m, "path") or ".", "all_": bool(_g(m, "all"))})
_r(r"git\s+checkout\s+(?:(?P<create>-b)\s+)?(?P<branch>\S+)",
   "git_checkout", lambda m, t: {"branch": _g(m, "branch"), "create": bool(_g(m, "create"))})
_r(r"(?:switch|go)\s+to\s+(?:branch\s+)?(?P<branch>\S+)",
   "git_checkout", lambda m, t: {"branch": _g(m, "branch"), "create": False})
_r(r"(?:create|make)\s+(?:new\s+)?(?:git\s+)?branch\s+(?P<branch>\S+)",
   "git_checkout", lambda m, t: {"branch": _g(m, "branch"), "create": True})
_r(r"git\s+merge\s+(?P<branch>\S+)",
   "git_merge", lambda m, t: {"branch": _g(m, "branch")})
_r(r"git\s+stash(?:\s+(?P<action>push|pop|list|drop|show))?",
   "git_stash", lambda m, t: {"action": _g(m, "action") or "push"})
_r(r"stash\s+(?:my\s+)?(?:changes?|work)",
   "git_stash", lambda m, t: {"action": "push"})
_r(r"(?:pop|restore)\s+(?:git\s+)?stash",
   "git_stash", lambda m, t: {"action": "pop"})
_r(r"git\s+reset\s+(?P<mode>--soft|--mixed|--hard)?\s*(?P<ref>\S+)?",
   "git_reset", lambda m, t: {"mode": _g(m, "mode").lstrip("-") or "soft", "ref": _g(m, "ref") or "HEAD~1"})
_r(r"git\s+remote(?:\s+-v)?",
   "git_remote", lambda m, t: {})
_r(r"git\s+tag(?:\s+(?P<name>\S+))?(?:\s+-m\s+[\"']?(?P<message>[^\"']+)[\"']?)?",
   "git_tag", lambda m, t: {"name": _g(m, "name"), "message": _g(m, "message")})
_r(r"git\s+blame\s+(?P<file>\S+)",
   "git_blame", lambda m, t: {"file": _g(m, "file")})
_r(r"(?:who\s+(?:wrote|changed|edited))\s+(?P<file>\S+)",
   "git_blame", lambda m, t: {"file": _g(m, "file")})
_r(r"git\s+show(?:\s+(?P<ref>\S+))?",
   "git_show", lambda m, t: {"ref": _g(m, "ref") or "HEAD"})
_r(r"git\s+init(?:\s+(?P<path>\S+))?",
   "git_init", lambda m, t: {"path": _g(m, "path") or "."})
_r(r"(?:init(?:ialise|ialize)?\s+)?(?:new\s+)?git\s+repo(?:sitory)?(?:\s+(?:in|at)\s+(?P<path>\S+))?",
   "git_init", lambda m, t: {"path": _g(m, "path") or "."})
_r(r"git\s+config\s+(?P<key>[\w.]+)(?:\s+(?P<value>.+))?",
   "git_config", lambda m, t: {"key": _g(m, "key"), "value": _g(m, "value")})

# ═══════════════════════════════════════════════════════════════════════════════
# POWER
# ═══════════════════════════════════════════════════════════════════════════════

_r(r"(?:suspend|sleep|put\s+to\s+sleep)\s+(?:the\s+)?(?:system|computer|laptop|machine|pc)?", "suspend")
_r(r"hibernate\s+(?:the\s+)?(?:system|computer|laptop|machine|pc)?",                          "hibernate")
_r(r"(?:reboot|restart)\s+(?:the\s+)?(?:system|computer|machine|pc)?(?:\s+in\s+(?P<delay>\d+)\s+min(?:utes?)?)?",
   "reboot", lambda m, t: {"delay": _gi(m, "delay")})
_r(r"(?:shutdown|shut\s*down|power\s*off|turn\s+off)\s+(?:the\s+)?(?:system|computer|machine|pc)?(?:\s+in\s+(?P<delay>\d+)\s+min(?:utes?)?)?",
   "shutdown", lambda m, t: {"delay": _gi(m, "delay")})
_r(r"(?:cancel|abort)\s+(?:the\s+)?(?:scheduled\s+)?(?:shutdown|reboot|restart)",  "cancel_shutdown")
_r(r"(?:get|check|what(?:'s| is))\s+(?:the\s+)?(?:screen\s+)?brightness",          "get_brightness")
_r(r"brightness\s*(?:level|percentage)?(?:\s*\??)?$",                               "get_brightness")
_r(r"(?:set|change|adjust)\s+(?:screen\s+|display\s+)?brightness\s+(?:to\s+)?(?P<percent>\d+)\s*%?",
   "set_brightness", lambda m, t: {"percent": _gi(m, "percent")})
_r(r"brightness\s+(?P<percent>\d+)\s*%?",
   "set_brightness", lambda m, t: {"percent": _gi(m, "percent")})
_r(r"(?:dim|darken)\s+(?:the\s+)?(?:screen|display|monitor)",
   "set_brightness", lambda m, t: {"percent": 20})
_r(r"(?:brighten)\s+(?:the\s+)?(?:screen|display|monitor)",
   "set_brightness", lambda m, t: {"percent": 100})
_r(r"(?:turn\s+off|blank|shut\s+off)\s+(?:the\s+)?(?:screen|display|monitor)",   "screen_off")
_r(r"(?:turn\s+on|wake\s+up|enable)\s+(?:the\s+)?(?:screen|display|monitor)",    "screen_on")
_r(r"(?:set\s+)?screen\s+(?:timeout|blank)\s+(?:to\s+)?(?P<minutes>\d+)\s*min",
   "set_screen_timeout", lambda m, t: {"minutes": _gi(m, "minutes")})
_r(r"(?:power|battery|system)\s+(?:stats?|status|info)",  "power_stats")

# ═══════════════════════════════════════════════════════════════════════════════
# WINDOW MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════════

_r(r"(?:list|show|display)\s+(?:all\s+)?(?:open\s+|active\s+)?windows?",              "list_windows")
_r(r"(?:focus|activate|bring\s+up|switch\s+to)\s+(?:window\s+)?(?P<title>.+)",
   "focus_window", lambda m, t: {"title": _g(m, "title")})
_r(r"(?:close|quit|kill)\s+(?:window\s+)?(?P<title>.+)",
   "close_window", lambda m, t: {"title": _g(m, "title")})
_r(r"(?:maximize|fullscreen)\s+(?:window\s+)?(?P<title>.+)?",
   "maximize_window", lambda m, t: {"title": _g(m, "title")})
_r(r"(?:minimize|hide)\s+(?:window\s+)?(?P<title>.+)?",
   "minimize_window", lambda m, t: {"title": _g(m, "title")})
_r(r"(?:move|drag)\s+(?:window\s+)?(?P<title>.+)\s+to\s+(?P<x>\d+)[, ]+(?P<y>\d+)",
   "move_window", lambda m, t: {"title": _g(m, "title"), "x": _gi(m, "x"), "y": _gi(m, "y")})
_r(r"resize\s+(?:window\s+)?(?P<title>.+)\s+to\s+(?P<width>\d+)[x×]+(?P<height>\d+)",
   "resize_window", lambda m, t: {"title": _g(m, "title"), "width": _gi(m, "width"), "height": _gi(m, "height")})
_r(r"(?:list|show)\s+(?:virtual\s+)?(?:desktops?|workspaces?)",                        "list_workspaces")
_r(r"(?:switch|go|move)\s+to\s+(?:workspace|desktop)\s+(?P<number>\d+)",
   "switch_workspace", lambda m, t: {"number": _gi(m, "number")})
_r(r"(?:what|which)\s+(?:window|app)\s+is\s+(?:active|focused|in\s+front)",           "get_active_window")
_r(r"(?:toggle\s+)?fullscreen(?:\s+(?:window\s+)?(?P<title>.+))?",
   "fullscreen_window", lambda m, t: {"title": _g(m, "title")})
_r(r"(?:toggle\s+)?always\s+on\s+top(?:\s+(?:for\s+)?(?P<title>.+))?",
   "always_on_top", lambda m, t: {"title": _g(m, "title")})
_r(r"(?:set|change)\s+(?:desktop\s+)?wallpaper\s+(?:to\s+)?(?P<path>\S+)",
   "set_wallpaper", lambda m, t: {"path": _g(m, "path")})

# ═══════════════════════════════════════════════════════════════════════════════
# ARCHIVES
# ═══════════════════════════════════════════════════════════════════════════════

_r(r"(?:extract|unzip|untar|decompress)\s+(?P<archive>\S+)(?:\s+(?:to|into|in)\s+(?P<destination>\S+))?",
   "extract", lambda m, t: {"archive": _g(m, "archive"), "destination": _g(m, "destination")})
_r(r"(?:create|make)\s+(?:a\s+)?tar(?:ball)?\s+(?:of\s+|from\s+)?(?P<files>.+)\s+(?:as|to|named)\s+(?P<output>\S+)",
   "create_tar", lambda m, t: {"output": _g(m, "output"), "files": _g(m, "files")})
_r(r"tar\s+(?:-)?czf\s+(?P<output>\S+)\s+(?P<files>.+)",
   "create_tar", lambda m, t: {"output": _g(m, "output"), "files": _g(m, "files"), "compress": "gz"})
_r(r"(?:zip|compress)\s+(?P<files>.+)\s+(?:as|to|into)\s+(?P<output>\S+)",
   "create_zip", lambda m, t: {"output": _g(m, "output"), "files": _g(m, "files")})
_r(r"(?:zip\s+up|archive|compress)\s+(?P<files>.+)\s+to\s+(?P<output>\S+\.zip)",
   "create_zip", lambda m, t: {"output": _g(m, "output"), "files": _g(m, "files")})
_r(r"(?:list|show|peek|inspect)\s+(?:contents?\s+of\s+|inside\s+)?(?P<archive>\S+\.(?:zip|tar\.gz|tgz|tar\.bz2|7z|rar))",
   "list_archive", lambda m, t: {"archive": _g(m, "archive")})
_r(r"(?:compress|gzip|bzip2)\s+(?:file\s+)?(?P<file>\S+)(?:\s+(?:with|using)\s+(?P<method>\w+))?",
   "compress_file", lambda m, t: {"file": _g(m, "file"), "method": _g(m, "method") or "gzip"})

# ═══════════════════════════════════════════════════════════════════════════════
# TEXT PROCESSING
# ═══════════════════════════════════════════════════════════════════════════════

_r(r"(?:grep|search|find)\s+[\"']?(?P<pattern>[^\"']+)[\"']?\s+in\s+(?:file\s+)?(?P<file>\S+)(?:\s+(?P<ignore_case>-i|ignore.?case))?",
   "grep_in_file", lambda m, t: {"pattern": _g(m, "pattern"), "file": _g(m, "file"), "ignore_case": bool(_g(m, "ignore_case"))})
_r(r"grep\s+(?P<pattern>\S+)\s+(?P<file>\S+)",
   "grep_in_file", lambda m, t: {"pattern": _g(m, "pattern"), "file": _g(m, "file")})
_r(r"(?:grep|search)\s+[\"']?(?P<pattern>[^\"']+)[\"']?\s+(?:in|across|through)\s+(?:directory\s+)?(?P<directory>\S+)(?:\s+for\s+(?P<file_pattern>\S+))?",
   "grep_in_dir", lambda m, t: {"pattern": _g(m, "pattern"), "directory": _g(m, "directory"), "file_pattern": _g(m, "file_pattern")})
_r(r"(?:wc|word\s+count|count\s+(?:words?|lines?))\s+(?:in\s+)?(?P<file>\S+)",
   "word_count", lambda m, t: {"file": _g(m, "file")})
_r(r"(?:diff|compare)\s+(?P<file1>\S+)\s+(?:and|vs\.?|with)\s+(?P<file2>\S+)",
   "file_diff", lambda m, t: {"file1": _g(m, "file1"), "file2": _g(m, "file2")})
_r(r"(?:sha256|sha512|sha1|md5|checksum|hash)\s+(?:of\s+|for\s+)?(?:file\s+)?(?P<file>\S+)",
   "hash_file", lambda m, t: {"file": _g(m, "file"), "algorithm": t.split()[0].lower()})
_r(r"(?:hash|checksum)\s+(?:file\s+)?(?P<file>\S+)(?:\s+(?:with|using)\s+(?P<algorithm>\w+))?",
   "hash_file", lambda m, t: {"file": _g(m, "file"), "algorithm": _g(m, "algorithm") or "sha256"})
_r(r"(?:hash|checksum)\s+[\"'](?P<text>[^\"']+)[\"'](?:\s+(?:with|using)\s+(?P<algorithm>\w+))?",
   "hash_text", lambda m, t: {"text": _g(m, "text"), "algorithm": _g(m, "algorithm") or "sha256"})
_r(r"base64\s+(?:encode|enc)\s+[\"']?(?P<text>[^\"']+)[\"']?",
   "base64_encode", lambda m, t: {"text": _g(m, "text")})
_r(r"base64\s+(?:decode|dec)\s+[\"']?(?P<text>[^\"']+)[\"']?",
   "base64_decode", lambda m, t: {"text": _g(m, "text")})
_r(r"(?:sort|order)\s+(?:these\s+)?lines?\s*:\s*(?P<text>.+)",
   "sort_lines", lambda m, t: {"text": _g(m, "text")})
_r(r"(?:find\s+and\s+)?replace\s+[\"'](?P<pattern>[^\"']+)[\"']\s+with\s+[\"'](?P<replacement>[^\"']+)[\"']\s+in\s+(?P<file>\S+)",
   "replace_in_file", lambda m, t: {"file": _g(m, "file"), "pattern": _g(m, "pattern"), "replacement": _g(m, "replacement")})
_r(r"(?:jq|json\s+query)\s+[\"']?(?P<query>[^\"']+)[\"']?\s+(?:from\s+|in\s+)?(?P<file>\S+\.json)",
   "json_query", lambda m, t: {"file": _g(m, "file"), "query": _g(m, "query")})
_r(r"(?:pretty\s*print|view|show)\s+(?P<file>\S+\.json)",
   "json_query", lambda m, t: {"file": _g(m, "file"), "query": "."})
_r(r"(?:head|first\s+(?P<lines>\d+)\s+lines?\s+of)\s+(?P<file>\S+)",
   "head_file", lambda m, t: {"file": _g(m, "file"), "lines": _gi(m, "lines") or 20})
_r(r"(?:tail|last\s+(?P<lines>\d+)\s+lines?\s+of)\s+(?P<file>\S+)",
   "tail_file", lambda m, t: {"file": _g(m, "file"), "lines": _gi(m, "lines") or 20})
_r(r"cut\s+(?:column\s+|field\s+)?(?P<fields>\S+)\s+(?:from\s+)?(?P<file>\S+)(?:\s+delimited\s+by\s+[\"']?(?P<delimiter>.)[\"']?)?",
   "column_cut", lambda m, t: {"file": _g(m, "file"), "fields": _g(m, "fields"), "delimiter": _g(m, "delimiter") or "\t"})

# ═══════════════════════════════════════════════════════════════════════════════
# DOCKER
# ═══════════════════════════════════════════════════════════════════════════════

_r(r"docker\s+ps(?:\s+(?P<all>-a|--all))?",
   "docker_ps", lambda m, t: {"all_": bool(_g(m, "all"))})
_r(r"(?:list|show)\s+(?:running\s+)?(?:docker\s+)?containers?",
   "docker_ps", lambda m, t: {"all_": False})
_r(r"docker\s+images?(?:\s+(?P<all>-a))?",
   "docker_images", lambda m, t: {"all_": bool(_g(m, "all"))})
_r(r"(?:list|show)\s+docker\s+images?",
   "docker_images")
_r(r"docker\s+run\s+(?P<image>\S+)(?:\s+--name\s+(?P<name>\S+))?(?:\s+-p\s+(?P<ports>\S+))?(?:\s+(?P<command>.+))?",
   "docker_run", lambda m, t: {"image": _g(m, "image"), "name": _g(m, "name"), "ports": _g(m, "ports"), "command": _g(m, "command")})
_r(r"docker\s+stop\s+(?P<name_or_id>\S+)",
   "docker_stop",    lambda m, t: {"name_or_id": _g(m, "name_or_id")})
_r(r"docker\s+start\s+(?P<name_or_id>\S+)",
   "docker_start",   lambda m, t: {"name_or_id": _g(m, "name_or_id")})
_r(r"docker\s+restart\s+(?P<name_or_id>\S+)",
   "docker_restart", lambda m, t: {"name_or_id": _g(m, "name_or_id")})
_r(r"docker\s+rm\s+(?P<name_or_id>\S+)",
   "docker_rm", lambda m, t: {"name_or_id": _g(m, "name_or_id")})
_r(r"docker\s+rmi\s+(?P<image>\S+)",
   "docker_rmi", lambda m, t: {"image": _g(m, "image")})
_r(r"docker\s+logs?\s+(?P<name_or_id>\S+)(?:\s+(?:last\s+)?(?P<tail>\d+)(?:\s+lines?)?)?",
   "docker_logs", lambda m, t: {"name_or_id": _g(m, "name_or_id"), "tail": _gi(m, "tail") or 50})
_r(r"(?:show\s+|get\s+)?logs?\s+(?:from\s+|for\s+)?container\s+(?P<name_or_id>\S+)",
   "docker_logs", lambda m, t: {"name_or_id": _g(m, "name_or_id")})
_r(r"docker\s+exec\s+(?P<name_or_id>\S+)\s+(?P<command>.+)",
   "docker_exec", lambda m, t: {"name_or_id": _g(m, "name_or_id"), "command": _g(m, "command")})
_r(r"(?:run|execute)\s+(?P<command>.+)\s+in\s+(?:container\s+)?(?P<name_or_id>\S+)",
   "docker_exec", lambda m, t: {"name_or_id": _g(m, "name_or_id"), "command": _g(m, "command")})
_r(r"docker\s+build\s+(?:-t\s+(?P<tag>\S+)\s+)?(?P<context>\S+)?",
   "docker_build", lambda m, t: {"tag": _g(m, "tag") or "my-image", "context": _g(m, "context") or "."})
_r(r"docker\s+pull\s+(?P<image>\S+)",
   "docker_pull", lambda m, t: {"image": _g(m, "image")})
_r(r"docker\s+push\s+(?P<image>\S+)",
   "docker_push", lambda m, t: {"image": _g(m, "image")})
_r(r"docker\s+inspect\s+(?P<name_or_id>\S+)",
   "docker_inspect", lambda m, t: {"name_or_id": _g(m, "name_or_id")})
_r(r"docker\s+stats?",                            "docker_stats")
_r(r"(?:docker\s+)?(?:system\s+)?prune|cleanup\s+docker", "docker_prune")
_r(r"docker.?compose\s+up(?:\s+(?P<path>\S+))?",
   "docker_compose_up", lambda m, t: {"path": _g(m, "path") or "."})
_r(r"docker.?compose\s+down(?:\s+(?P<path>\S+))?",
   "docker_compose_down", lambda m, t: {"path": _g(m, "path") or "."})
_r(r"docker.?compose\s+logs?(?:\s+(?P<path>\S+))?",
   "docker_compose_logs", lambda m, t: {"path": _g(m, "path") or "."})

# ═══════════════════════════════════════════════════════════════════════════════
# SYSTEM INFO
# ═══════════════════════════════════════════════════════════════════════════════

_r(r"(?:full\s+)?system\s+(?:info|overview|summary|details?|report)",    "system_info")
_r(r"(?:about\s+)?this\s+(?:machine|computer|system)",                   "system_info")
_r(r"(?:os|linux|distro(?:bution)?)\s+(?:release|info|version|name)?",  "os_release")
_r(r"what\s+(?:linux|os|distro)\s+(?:am\s+i\s+running|is\s+this|version)", "os_release")
_r(r"(?:kernel|uname)\s*(?:version|info|release)?",                      "kernel_info")
_r(r"uname\s*(?:-a)?",                                                    "kernel_info")
_r(r"(?:cpu|processor)\s+(?:info|details?|specs?|model)",                "cpu_info")
_r(r"lscpu",                                                              "cpu_info")
_r(r"(?:memory|ram)\s+(?:info|details?|breakdown)",                      "memory_info")
_r(r"free\s+-h",                                                          "memory_info")
_r(r"(?:disk|drive|storage)\s+(?:info|details?|layout|breakdown)",       "disk_info")
_r(r"(?:lsblk|blkid|fdisk\s+-l)",                                        "disk_info")
_r(r"(?:pci|lspci)\s*(?:devices?|list)?",                                "pci_devices")
_r(r"(?:usb|lsusb)\s*(?:devices?|list|connected)?",                      "usb_devices")
_r(r"(?:hardware|machine|system)\s+(?:model|brand|info|vendor)",         "hardware_info")
_r(r"(?:temperature|temp|thermal|sensors?)\s*(?:reading|check|info)?",   "sensors")
_r(r"(?:how\s+hot\s+is|cpu\s+temperature|core\s+temp)",                  "sensors")
_r(r"(?:journal(?:ctl)?|system\s+logs?)\s*(?:(?:last\s+)?(?P<n>\d+))?", "journal_logs",
   lambda m, t: {"n": _gi(m, "n") or 30})
_r(r"(?:syslog|system\s+log|/var/log)",                                  "syslog")
_r(r"dmesg(?:\s+(?P<n>\d+))?",
   "dmesg", lambda m, t: {"n": _gi(m, "n") or 30})
_r(r"(?:kernel\s+(?:messages?|log)|ring\s+buffer)",                      "dmesg")
_r(r"(?:show|print|list|get)\s+(?:all\s+)?(?:environment|env)\s*(?:variables?|vars?)?", "env_vars")
_r(r"env(?:ironment)?(?:\s+vars?)?(?:\s+filter\s+(?P<filter_>\S+))?",
   "env_vars", lambda m, t: {"filter_": _g(m, "filter_")})
_r(r"(?:which|where\s+is|locate)\s+(?P<command>\S+)",
   "which_command", lambda m, t: {"command": _g(m, "command")})
_r(r"(?:echo\s+)?\$PATH|(?:show|list|print)\s+PATH(?:\s+entries?)?",    "path_info")
_r(r"(?:list|show|what)\s+(?:available\s+)?shells?",                    "installed_shells")
_r(r"cat\s+/etc/shells",                                                 "installed_shells")
_r(r"hostname(?:\s+info)?|(?:what(?:'s| is)|show)\s+(?:my\s+)?hostname", "hostname_info")
_r(r"(?:who(?:\s+is)?|show|list)\s+(?:logged\s+in|online\s+users?|active\s+sessions?)", "user_info")
_r(r"(?:system\s+)?load\s*(?:average|avg)?",                            "load_average")
_r(r"cat\s+/proc/loadavg",                                              "load_average")
_r(r"(?:system|last)\s+boot\s*(?:time)?|when\s+(?:did|was)\s+(?:the\s+)?(?:system|machine|computer)\s+(?:start|boot|rebooted)", "boot_time")
_r(r"(?:locale|timezone|time\s+zone)\s*(?:info|settings?|config)?",    "locale_info")
_r(r"timedatectl",                                                       "locale_info")

# ═══════════════════════════════════════════════════════════════════════════════
# MISC — clipboard, notifications, cron, calc, media, users, permissions
# ═══════════════════════════════════════════════════════════════════════════════

# clipboard
_r(r"(?:copy|clipboard\s+copy)\s+[\"'](?P<text>[^\"']+)[\"']",
   "clipboard_copy", lambda m, t: {"text": _g(m, "text")})
_r(r"(?:copy|clipboard\s+copy)\s+(?P<text>.+)\s+to\s+clipboard",
   "clipboard_copy", lambda m, t: {"text": _g(m, "text")})
_r(r"(?:paste|get|show)\s+(?:from\s+)?clipboard|clipboard\s+(?:content|paste)", "clipboard_paste")
_r(r"what(?:'s| is) in (?:the\s+)?clipboard",                                    "clipboard_paste")

# notifications
_r(r"(?:send\s+)?notify(?:-send)?\s+[\"'](?P<title>[^\"']+)[\"']\s+[\"'](?P<message>[^\"']+)[\"']",
   "notify", lambda m, t: {"title": _g(m, "title"), "message": _g(m, "message")})
_r(r"(?:remind|alert|notify)\s+me\s+(?:about\s+|to\s+)?(?P<message>.+)",
   "notify", lambda m, t: {"title": "cogman Reminder", "message": _g(m, "message")})

# cron
_r(r"(?:list|show|display)\s+(?:my\s+)?cron(?:tab|jobs?)?",                   "cron_list")
_r(r"crontab\s+-l",                                                             "cron_list")
_r(r"(?:add|create)\s+cron(?:tab)?\s+(?:job\s+)?[\"']?(?P<schedule>(?:\S+\s+){4}\S+)[\"']?\s+(?P<command>.+)",
   "cron_add", lambda m, t: {"schedule": _g(m, "schedule"), "command": _g(m, "command")})
_r(r"cron(?:tab)?\s+(?:every\s+)?(?P<schedule>@hourly|@daily|@weekly|@monthly|@reboot)\s+(?P<command>.+)",
   "cron_add", lambda m, t: {"schedule": _g(m, "schedule"), "command": _g(m, "command")})
_r(r"(?:remove|delete)\s+cron(?:tab)?\s+(?:job\s+)?(?:matching\s+)?(?P<pattern>.+)",
   "cron_remove", lambda m, t: {"pattern": _g(m, "pattern")})

# calculator
_r(r"(?:calc(?:ulate)?|compute|eval(?:uate)?|math|=)\s+(?P<expression>.+)",
   "calculate", lambda m, t: {"expression": _g(m, "expression")})
_r(r"(?:what(?:'s| is)\s+)?(?P<expression>\d[\d\s+\-*/^().√πe%]+(?:sqrt|sin|cos|tan|log|pow|abs)?[\d\s+\-*/^().]*)\??$",
   "calculate", lambda m, t: {"expression": _g(m, "expression").strip("?")})
_r(r"(?:how much\s+is|what\s+is)\s+(?P<expression>[\d\s+\-*/^().]+)\??",
   "calculate", lambda m, t: {"expression": _g(m, "expression").strip("?")})

# unit convert
_r(r"convert\s+(?P<value>[\d.]+)\s+(?P<from_unit>\w+)\s+(?:to|into|in)\s+(?P<to_unit>\w+)",
   "unit_convert", lambda m, t: {"value": _gf(m, "value"), "from_unit": _g(m, "from_unit"), "to_unit": _g(m, "to_unit")})
_r(r"(?P<value>[\d.]+)\s+(?P<from_unit>km|miles?|kg|lbs?|celsius|fahrenheit|gb|mb|tb|inches?|feet|meters?)\s+(?:to|in)\s+(?P<to_unit>\w+)",
   "unit_convert", lambda m, t: {"value": _gf(m, "value"), "from_unit": _g(m, "from_unit"), "to_unit": _g(m, "to_unit")})

# media
_r(r"(?:play|open|stream)\s+(?:audio\s+|music\s+)?(?:file\s+)?(?P<file>\S+\.(?:mp3|wav|ogg|flac|aac|m4a))",
   "play_audio", lambda m, t: {"file": _g(m, "file")})
_r(r"(?:play|open|watch|stream)\s+(?:video\s+)?(?:file\s+)?(?P<file>\S+\.(?:mp4|mkv|avi|mov|webm|flv))",
   "play_video", lambda m, t: {"file": _g(m, "file")})
_r(r"(?:media|file|video|audio)\s+(?:info|metadata|details?)\s+(?:of\s+|for\s+)?(?P<file>\S+)",
   "get_media_info", lambda m, t: {"file": _g(m, "file")})
_r(r"(?:convert|transcode)\s+(?P<input_>\S+)\s+to\s+(?P<output>\S+\.(?:mp4|mp3|mkv|wav|webm|avi))",
   "ffmpeg_convert", lambda m, t: {"input_": _g(m, "input_"), "output": _g(m, "output")})

# user management
_r(r"(?:list|show|display)\s+(?:all\s+|system\s+)?users?",              "list_users")
_r(r"(?:who\s+am\s+i|whoami|current\s+user|my\s+username)",             "current_user")
_r(r"id(?:\s+(?P<user>\S+))?",
   "current_user")
_r(r"(?:who\s+is\s+|show\s+who\s+is\s+)logged\s+(?:in|on)",            "who_is_logged_in")
_r(r"(?:show\s+|list\s+)?(?:active|current)\s+(?:users?|sessions?)",   "who_is_logged_in")
_r(r"(?:create|add|make|new)\s+user\s+(?P<username>\S+)",
   "add_user", lambda m, t: {"username": _g(m, "username")})
_r(r"(?:what\s+|show\s+)?(?:groups?\s+(?:for|of)\s+|my\s+)?groups?(?:\s+for\s+(?P<username>\S+))?",
   "user_groups", lambda m, t: {"username": _g(m, "username")})
_r(r"add\s+(?P<username>\S+)\s+to\s+(?:group\s+)?(?P<group>\S+)",
   "add_to_group", lambda m, t: {"username": _g(m, "username"), "group": _g(m, "group")})
_r(r"(?:add\s+)?user(?:mod\s+)?(?P<username>\S+)\s+(?:to\s+)?(?P<group>\S+)\s+group",
   "add_to_group", lambda m, t: {"username": _g(m, "username"), "group": _g(m, "group")})

# permissions
_r(r"chmod\s+(?P<permissions>\S+)\s+(?P<path>\S+)",
   "chmod_file", lambda m, t: {"permissions": _g(m, "permissions"), "path": _g(m, "path")})
_r(r"(?:set|change)\s+permissions?\s+(?:of\s+|on\s+|for\s+)?(?P<path>\S+)\s+to\s+(?P<permissions>\S+)",
   "chmod_file", lambda m, t: {"permissions": _g(m, "permissions"), "path": _g(m, "path")})
_r(r"(?:make|mark)\s+(?P<path>\S+)\s+executable",
   "chmod_file", lambda m, t: {"permissions": "+x", "path": _g(m, "path")})
_r(r"chown\s+(?P<owner>\S+)\s+(?P<path>\S+)",
   "chown_file", lambda m, t: {"owner": _g(m, "owner"), "path": _g(m, "path")})
_r(r"(?:change|set)\s+(?:file\s+)?owner(?:ship)?\s+(?:of\s+)?(?P<path>\S+)\s+to\s+(?P<owner>\S+)",
   "chown_file", lambda m, t: {"owner": _g(m, "owner"), "path": _g(m, "path")})
_r(r"(?:show|check|get|ls\s+-la?)\s+(?:file\s+)?permissions?\s+(?:of\s+|for\s+|on\s+)?(?P<path>\S+)",
   "file_permissions", lambda m, t: {"path": _g(m, "path")})
_r(r"stat\s+(?P<path>\S+)",
   "file_permissions", lambda m, t: {"path": _g(m, "path")})


# ═══════════════════════════════════════════════════════════════════════════════
# PUBLIC API
# ═══════════════════════════════════════════════════════════════════════════════

def match(text: str) -> Optional[IntentResult]:
    """
    Match text against all patterns. Returns first match as IntentResult.
    Patterns are tried in registration order (most specific first).
    """
    text = text.strip()
    for pattern, tool, builder in _PATTERNS:
        m = pattern.search(text)
        if m:
            try:
                args = builder(m, text)
                # Strip None values and empty strings for optional args
                args = {k: v for k, v in args.items() if v is not None and v != ""}
                log.debug("Pattern matched: %s → %s %s", pattern.pattern[:40], tool, args)
                return IntentResult(tool=tool, args=args, confidence=1.0, source="pattern")
            except Exception as e:
                log.debug("Pattern builder error (%s): %s", tool, e)
    return None


def coverage_report(registry) -> dict:
    """Report which tools have patterns and which don't."""
    covered = {tool for _, tool, _ in _PATTERNS}
    all_tools = set(registry.list_names())
    uncovered = all_tools - covered
    return {
        "total_tools": len(all_tools),
        "covered": len(covered & all_tools),
        "uncovered": sorted(uncovered),
        "pattern_count": len(_PATTERNS),
    }
