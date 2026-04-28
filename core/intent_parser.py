import re
import logging
from typing import Optional, Tuple, Dict

log = logging.getLogger("cogman.intent")

# Rule-based fast patterns: (regex, tool_name, arg_extractor)
_RULES: list = []


def rule(pattern: str, tool: str, extractor=None):
    _RULES.append((re.compile(pattern, re.IGNORECASE), tool, extractor))


# --- Register fast rules ---
rule(r"open\s+(browser|chrome|firefox|chromium)", "open_app",
     lambda m: {"app": m.group(1)})
rule(r"open\s+terminal", "open_app",
     lambda m: {"app": "terminal"})
rule(r"open\s+(?:file\s+manager|files)", "open_app",
     lambda m: {"app": "file_manager"})
rule(r"what(?:'s| is) the time", "get_time", lambda m: {})
rule(r"what(?:'s| is) the date", "get_date", lambda m: {})
rule(r"(?:show|check|get)\s+(?:disk|storage)\s*(?:usage|space)?", "disk_usage", lambda m: {})
rule(r"(?:show|check|get)\s+(?:memory|ram)\s*(?:usage)?", "memory_usage", lambda m: {})
rule(r"(?:show|check|get)\s+(?:cpu)\s*(?:usage)?", "cpu_usage", lambda m: {})
rule(r"(?:list|show)\s+(?:running\s+)?processes", "list_processes", lambda m: {})
rule(r"(?:take|capture)\s+(?:a\s+)?screenshot", "screenshot", lambda m: {})
rule(r"(?:lock|secure)\s+(?:screen|computer|pc)", "lock_screen", lambda m: {})
rule(r"set\s+volume\s+(?:to\s+)?(\d+)", "set_volume",
     lambda m: {"level": int(m.group(1))})
rule(r"(?:mute|unmute)\s*(?:audio|sound|volume)?", "mute_toggle", lambda m: {})
rule(r"(?:run|execute|shell)\s+(.+)", "run_shell",
     lambda m: {"command": m.group(1)})
rule(r"(?:remember|note|save)\s+(?:that\s+)?(.+)", "save_memory",
     lambda m: {"content": m.group(1)})
rule(r"(?:recall|what do you know about|search memory for)\s+(.+)", "search_memory",
     lambda m: {"query": m.group(1)})
rule(r"(?:wifi|network)\s+(?:status|info)", "network_info", lambda m: {})
rule(r"(?:battery|charge)\s+(?:status|level)?", "battery_status", lambda m: {})
rule(r"(?:kill|stop|close)\s+(.+)", "kill_process",
     lambda m: {"name": m.group(1)})
rule(r"(?:type|write)\s+(.+)", "type_text",
     lambda m: {"text": m.group(1)})
rule(r"(?:search|google|look up)\s+(.+)", "web_search",
     lambda m: {"query": m.group(1)})
rule(r"(?:list|show)\s+files?\s+(?:in\s+)?(.+)?", "list_files",
     lambda m: {"path": (m.group(1) or "~").strip()})
rule(r"(?:read|cat|show)\s+(?:file\s+)?(.+)", "read_file",
     lambda m: {"path": m.group(1).strip()})

# ─── System Info ─────────────────────────────────────────────────────────────
rule(r"(?:show|get|print)\s+(?:system|os|full)\s+info", "system_info", lambda m: {})
rule(r"(?:what\s+(?:os|linux|distro)|which\s+distro)", "os_release", lambda m: {})
rule(r"(?:show|get)\s+(?:kernel|uname)\s*(?:info|version)?", "kernel_info", lambda m: {})
rule(r"(?:show|get)\s+(?:cpu|processor)\s+info", "cpu_info", lambda m: {})
rule(r"(?:sensor|temperature|temp)\s*(?:info|reading|check)?", "sensors", lambda m: {})
rule(r"(?:hardware|machine|model)\s*info", "hardware_info", lambda m: {})
rule(r"(?:usb|lsusb)\s*(?:devices?|list)?", "usb_devices", lambda m: {})
rule(r"(?:pci|lspci)\s*(?:devices?|list)?", "pci_devices", lambda m: {})
rule(r"(?:system|boot)\s+(?:uptime|up\s+time)", "system_uptime", lambda m: {})
rule(r"(?:load|load\s+average|loadavg)", "load_average", lambda m: {})
rule(r"(?:env|environment)\s*(?:variables?)?", "env_vars", lambda m: {})
rule(r"where\s+is\s+(.+)", "which_command",
     lambda m: {"command": m.group(1).strip()})

# ─── Process ─────────────────────────────────────────────────────────────────
rule(r"(?:top|most)\s+(?:cpu|memory|ram)\s*(?:processes?|hogs?)?", "top_processes",
     lambda m: {"sort_by": "memory" if "mem" in m.group(0).lower() or "ram" in m.group(0).lower() else "cpu"})
rule(r"(?:info|details?)\s+(?:about\s+)?(?:process|pid)\s+(.+)", "get_process_info",
     lambda m: {"name_or_pid": m.group(1).strip()})
rule(r"(?:run|start)\s+(.+)\s+in\s+(?:the\s+)?background", "run_background",
     lambda m: {"command": m.group(1).strip()})
rule(r"who\s+(?:is\s+)?(?:using|owns?)\s+port\s+(\d+)", "find_process_by_port",
     lambda m: {"port": int(m.group(1))})

# ─── Network ─────────────────────────────────────────────────────────────────
rule(r"ping\s+(.+)", "ping", lambda m: {"host": m.group(1).strip()})
rule(r"(?:trace(?:route)?|tracepath)\s+(.+)", "traceroute",
     lambda m: {"host": m.group(1).strip()})
rule(r"(?:dns|lookup|nslookup|dig)\s+(?:for\s+)?(.+)", "dns_lookup",
     lambda m: {"domain": m.group(1).strip()})
rule(r"(?:open|listening)\s+ports?", "list_open_ports", lambda m: {})
rule(r"(?:my\s+)?(?:public|external)\s+ip", "get_public_ip", lambda m: {})
rule(r"(?:my\s+)?(?:local|private)\s+ip", "get_local_ip", lambda m: {})
rule(r"(?:scan|list)\s+(?:wifi|wireless|wlan)\s*(?:networks?)?", "wifi_networks", lambda m: {})
rule(r"(?:connect\s+to\s+wifi|wifi\s+connect)\s+(.+)", "wifi_connect",
     lambda m: {"ssid": m.group(1).strip()})
rule(r"(?:disconnect|leave)\s+(?:wifi|wireless)", "wifi_disconnect", lambda m: {})
rule(r"(?:speed|internet)\s*test", "speed_test", lambda m: {})
rule(r"(?:firewall|ufw)\s+status", "firewall_status", lambda m: {})
rule(r"(?:download|wget|curl)\s+(.+)", "download_file",
     lambda m: {"url": m.group(1).strip()})
rule(r"(?:network|interface)\s+(?:stats?|statistics|io)", "network_stats", lambda m: {})

# ─── Packages ────────────────────────────────────────────────────────────────
rule(r"(?:install|apt\s+install)\s+(?:package\s+)?(.+)", "apt_install",
     lambda m: {"package": m.group(1).strip()})
rule(r"(?:remove|uninstall|apt\s+remove)\s+(?:package\s+)?(.+)", "apt_remove",
     lambda m: {"package": m.group(1).strip()})
rule(r"(?:apt|system)\s+update", "apt_update", lambda m: {})
rule(r"(?:apt|system)\s+upgrade", "apt_upgrade", lambda m: {})
rule(r"(?:search|find)\s+(?:apt\s+)?package\s+(.+)", "apt_search",
     lambda m: {"query": m.group(1).strip()})
rule(r"(?:installed|list)\s+(?:apt\s+)?packages?", "apt_list_installed", lambda m: {})
rule(r"pip\s+install\s+(.+)", "pip_install",
     lambda m: {"package": m.group(1).strip()})
rule(r"pip\s+(?:list|show\s+installed)", "pip_list", lambda m: {})
rule(r"(?:outdated|old)\s+(?:pip|python)\s+packages?", "pip_outdated", lambda m: {})
rule(r"snap\s+(?:list|installed)", "snap_list", lambda m: {})
rule(r"snap\s+install\s+(.+)", "snap_install",
     lambda m: {"package": m.group(1).strip()})

# ─── Services ────────────────────────────────────────────────────────────────
rule(r"(?:status\s+of\s+|check\s+)?service\s+(.+?)(?:\s+status)?$", "service_status",
     lambda m: {"name": m.group(1).strip()})
rule(r"start\s+service\s+(.+)", "service_start",
     lambda m: {"name": m.group(1).strip()})
rule(r"stop\s+service\s+(.+)", "service_stop",
     lambda m: {"name": m.group(1).strip()})
rule(r"restart\s+service\s+(.+)", "service_restart",
     lambda m: {"name": m.group(1).strip()})
rule(r"(?:enable|autostart)\s+service\s+(.+)", "service_enable",
     lambda m: {"name": m.group(1).strip()})
rule(r"(?:disable)\s+service\s+(.+)", "service_disable",
     lambda m: {"name": m.group(1).strip()})
rule(r"(?:list|show)\s+(?:running\s+)?services?", "list_services", lambda m: {})
rule(r"failed\s+services?", "failed_services", lambda m: {})
rule(r"logs?\s+(?:for\s+)?(?:service\s+)?(.+)", "service_logs",
     lambda m: {"name": m.group(1).strip()})

# ─── Git ─────────────────────────────────────────────────────────────────────
rule(r"git\s+status", "git_status", lambda m: {})
rule(r"git\s+log", "git_log", lambda m: {})
rule(r"git\s+diff", "git_diff", lambda m: {})
rule(r"git\s+(?:add|stage)\s+(.+)", "git_add",
     lambda m: {"files": m.group(1).strip()})
rule(r"git\s+commit\s+(?:-m\s+)?[\"']?(.+)[\"']?", "git_commit",
     lambda m: {"message": m.group(1).strip("\"'")})
rule(r"git\s+push", "git_push", lambda m: {})
rule(r"git\s+pull", "git_pull", lambda m: {})
rule(r"git\s+clone\s+(\S+)", "git_clone",
     lambda m: {"url": m.group(1).strip()})
rule(r"git\s+branch", "git_branch", lambda m: {})
rule(r"git\s+checkout\s+(.+)", "git_checkout",
     lambda m: {"branch": m.group(1).strip()})
rule(r"git\s+stash", "git_stash", lambda m: {"action": "push"})
rule(r"git\s+stash\s+pop", "git_stash", lambda m: {"action": "pop"})
rule(r"git\s+stash\s+list", "git_stash", lambda m: {"action": "list"})

# ─── Power ───────────────────────────────────────────────────────────────────
rule(r"(?:suspend|sleep)\s+(?:the\s+)?(?:system|computer|laptop|pc)", "suspend", lambda m: {})
rule(r"hibernate\s+(?:the\s+)?(?:system|computer)", "hibernate", lambda m: {})
rule(r"(?:restart|reboot)\s+(?:the\s+)?(?:system|computer|pc)", "reboot", lambda m: {})
rule(r"(?:shutdown|power\s+off|poweroff|turn\s+off)\s+(?:the\s+)?(?:system|computer|pc)?", "shutdown", lambda m: {})
rule(r"cancel\s+(?:shutdown|reboot|restart)", "cancel_shutdown", lambda m: {})
rule(r"(?:brightness|screen\s+brightness|backlight)\s+(\d+)(?:\s*%)?", "set_brightness",
     lambda m: {"percent": int(m.group(1))})
rule(r"(?:get|check|what(?:'s| is))\s+(?:brightness|screen\s+brightness)", "get_brightness", lambda m: {})
rule(r"(?:turn\s+off|blank)\s+(?:the\s+)?screen", "screen_off", lambda m: {})
rule(r"(?:turn\s+on|wake)\s+(?:the\s+)?screen", "screen_on", lambda m: {})
rule(r"(?:power|battery)\s+(?:stats?|info|status)", "power_stats", lambda m: {})

# ─── Windows / Desktop ───────────────────────────────────────────────────────
rule(r"(?:list|show)\s+(?:open|all)\s+windows?", "list_windows", lambda m: {})
rule(r"focus\s+(?:window\s+)?(.+)", "focus_window",
     lambda m: {"title": m.group(1).strip()})
rule(r"close\s+window\s+(.+)", "close_window",
     lambda m: {"title": m.group(1).strip()})
rule(r"maximize\s+(?:window\s+)?(.+)?", "maximize_window",
     lambda m: {"title": (m.group(1) or "").strip()})
rule(r"minimize\s+(?:window\s+)?(.+)?", "minimize_window",
     lambda m: {"title": (m.group(1) or "").strip()})
rule(r"(?:switch|go)\s+to\s+workspace\s+(\d+)", "switch_workspace",
     lambda m: {"number": int(m.group(1))})
rule(r"active\s+window", "get_active_window", lambda m: {})
rule(r"set\s+wallpaper\s+(.+)", "set_wallpaper",
     lambda m: {"path": m.group(1).strip()})

# ─── Archives ────────────────────────────────────────────────────────────────
rule(r"(?:extract|unzip|untar)\s+(.+?)(?:\s+to\s+(.+))?$", "extract",
     lambda m: {"archive": m.group(1).strip(), "destination": (m.group(2) or "").strip()})
rule(r"(?:zip|compress|archive)\s+(.+)\s+(?:to|as|into)\s+(.+)", "create_zip",
     lambda m: {"output": m.group(2).strip(), "files": m.group(1).strip()})
rule(r"list\s+(?:archive|contents\s+of)\s+(.+)", "list_archive",
     lambda m: {"archive": m.group(1).strip()})

# ─── Text ─────────────────────────────────────────────────────────────────────
rule(r"(?:grep|search\s+for)\s+[\"']?(.+?)[\"']?\s+in\s+(?:file\s+)?(.+)", "grep_in_file",
     lambda m: {"pattern": m.group(1).strip(), "file": m.group(2).strip()})
rule(r"(?:hash|checksum|sha256|md5)\s+(?:of\s+)?(?:file\s+)?(.+)", "hash_file",
     lambda m: {"file": m.group(1).strip()})
rule(r"(?:head|first\s+\d+\s+lines?\s+of)\s+(.+)", "head_file",
     lambda m: {"file": m.group(1).strip()})
rule(r"(?:tail|last\s+\d+\s+lines?\s+of)\s+(.+)", "tail_file",
     lambda m: {"file": m.group(1).strip()})
rule(r"(?:diff|compare)\s+(.+)\s+(?:and|vs\.?)\s+(.+)", "file_diff",
     lambda m: {"file1": m.group(1).strip(), "file2": m.group(2).strip()})
rule(r"(?:count\s+words?|word\s+count|wc)\s+(?:in\s+)?(.+)", "word_count",
     lambda m: {"file": m.group(1).strip()})
rule(r"(?:base64\s+encode)\s+(.+)", "base64_encode",
     lambda m: {"text": m.group(1).strip()})
rule(r"(?:base64\s+decode)\s+(.+)", "base64_decode",
     lambda m: {"text": m.group(1).strip()})
rule(r"(?:json|jq)\s+(.+)", "json_query",
     lambda m: {"file": m.group(1).strip()})

# ─── Docker ──────────────────────────────────────────────────────────────────
rule(r"docker\s+ps", "docker_ps", lambda m: {})
rule(r"docker\s+images?", "docker_images", lambda m: {})
rule(r"docker\s+stop\s+(.+)", "docker_stop",
     lambda m: {"name_or_id": m.group(1).strip()})
rule(r"docker\s+start\s+(.+)", "docker_start",
     lambda m: {"name_or_id": m.group(1).strip()})
rule(r"docker\s+restart\s+(.+)", "docker_restart",
     lambda m: {"name_or_id": m.group(1).strip()})
rule(r"docker\s+logs?\s+(.+)", "docker_logs",
     lambda m: {"name_or_id": m.group(1).strip()})
rule(r"docker\s+(?:pull|download)\s+(.+)", "docker_pull",
     lambda m: {"image": m.group(1).strip()})
rule(r"docker\s+stats?", "docker_stats", lambda m: {})
rule(r"docker\s+(?:cleanup|prune)", "docker_prune", lambda m: {})

# ─── Clipboard ───────────────────────────────────────────────────────────────
rule(r"(?:copy|clipboard\s+copy)\s+(.+)", "clipboard_copy",
     lambda m: {"text": m.group(1).strip()})
rule(r"(?:paste|clipboard\s+paste|get\s+clipboard)", "clipboard_paste", lambda m: {})

# ─── Notifications ───────────────────────────────────────────────────────────
rule(r"(?:notify|alert|notification)\s+[\"']?(.+?)[\"']?\s+[\"'](.+)[\"']", "notify",
     lambda m: {"title": m.group(1).strip(), "message": m.group(2).strip()})
rule(r"remind\s+me\s+(?:about\s+)?(.+)", "notify",
     lambda m: {"title": "cogman Reminder", "message": m.group(1).strip()})

# ─── Cron ────────────────────────────────────────────────────────────────────
rule(r"(?:list|show)\s+cron(?:tab|jobs?)?", "cron_list", lambda m: {})

# ─── Calculator ──────────────────────────────────────────────────────────────
rule(r"(?:calc(?:ulate)?|compute|math|what\s+is)\s+(.+)", "calculate",
     lambda m: {"expression": m.group(1).strip()})
rule(r"convert\s+([\d.]+)\s+(\w+)\s+to\s+(\w+)", "unit_convert",
     lambda m: {"value": float(m.group(1)), "from_unit": m.group(2), "to_unit": m.group(3)})

# ─── Media ───────────────────────────────────────────────────────────────────
rule(r"play\s+(?:audio\s+|music\s+)?(?:file\s+)?(.+)", "play_audio",
     lambda m: {"file": m.group(1).strip()})
rule(r"play\s+video\s+(?:file\s+)?(.+)", "play_video",
     lambda m: {"file": m.group(1).strip()})
rule(r"(?:media|file)\s+info\s+(?:for\s+)?(.+)", "get_media_info",
     lambda m: {"file": m.group(1).strip()})

# ─── User ────────────────────────────────────────────────────────────────────
rule(r"(?:who\s+am\s+i|current\s+user|whoami)", "current_user", lambda m: {})
rule(r"(?:list|show)\s+users?", "list_users", lambda m: {})
rule(r"who\s+is\s+logged\s+(?:in|on)", "who_is_logged_in", lambda m: {})
rule(r"(?:file\s+)?permissions?\s+(?:of|for)\s+(.+)", "file_permissions",
     lambda m: {"path": m.group(1).strip()})
rule(r"chmod\s+(\S+)\s+(.+)", "chmod_file",
     lambda m: {"permissions": m.group(1), "path": m.group(2).strip()})


class IntentResult:
    def __init__(self, tool: str, args: Dict, confidence: float, source: str):
        self.tool = tool
        self.args = args
        self.confidence = confidence  # 0.0 – 1.0
        self.source = source          # "rule" | "llm"

    def __repr__(self):
        return f"<Intent tool={self.tool} args={self.args} conf={self.confidence:.2f} src={self.source}>"


def parse_fast(text: str) -> Optional[IntentResult]:
    """Try all rule-based patterns first (O(n) but instant)."""
    for pattern, tool, extractor in _RULES:
        m = pattern.search(text)
        if m:
            args = extractor(m) if extractor else {}
            log.debug("Rule matched: %s → %s", pattern.pattern, tool)
            return IntentResult(tool=tool, args=args, confidence=0.95, source="rule")
    return None
