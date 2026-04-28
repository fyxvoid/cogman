"""Network tools: ping, ports, firewall, wifi, download, SSH, DNS, speed."""
import shutil
import logging
import urllib.request
import urllib.parse
from core.tool_registry import ToolRegistry
from core.system_controller import run_shell
from core.safety import confirm

log = logging.getLogger("cogman.tools.network")


def ping(host: str, count: int = 4) -> str:
    return run_shell(f"ping -c {min(count, 10)} {host}")


def traceroute(host: str) -> str:
    tool = "traceroute" if shutil.which("traceroute") else "tracepath"
    return run_shell(f"{tool} {host}")


def dns_lookup(domain: str) -> str:
    result = run_shell(f"nslookup {domain} 2>/dev/null || dig +short {domain} 2>/dev/null || host {domain}")
    return result


def reverse_dns(ip: str) -> str:
    return run_shell(f"nslookup {ip} 2>/dev/null || host {ip}")


def list_open_ports(all_ports: bool = False) -> str:
    flag = "-tlnp" if not all_ports else "-tnp"
    out = run_shell(f"ss {flag} 2>/dev/null")
    if "[exit" in out:
        out = run_shell("netstat -tlnp 2>/dev/null")
    return out


def check_port(host: str, port: int, timeout: int = 3) -> str:
    import socket
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return f"Port {port} on {host} is OPEN"
    except (socket.timeout, ConnectionRefusedError, OSError) as e:
        return f"Port {port} on {host} is CLOSED/UNREACHABLE ({e})"


def firewall_status() -> str:
    for cmd in ["ufw status verbose", "iptables -L -n --line-numbers 2>/dev/null | head -30"]:
        result = run_shell(cmd)
        if result and "[exit" not in result:
            return result
    return "No recognized firewall tool found (ufw/iptables)"


def firewall_allow(port: int, protocol: str = "tcp") -> str:
    if not confirm(f"Allow port {port}/{protocol} in firewall?"):
        return "Cancelled."
    return run_shell(f"sudo ufw allow {port}/{protocol}")


def firewall_deny(port: int, protocol: str = "tcp") -> str:
    if not confirm(f"Deny port {port}/{protocol} in firewall?"):
        return "Cancelled."
    return run_shell(f"sudo ufw deny {port}/{protocol}")


def download_file(url: str, destination: str = "~/Downloads/") -> str:
    import os
    destination = os.path.expanduser(destination)
    if shutil.which("wget"):
        return run_shell(f"wget -P '{destination}' '{url}'")
    elif shutil.which("curl"):
        filename = url.split("/")[-1].split("?")[0] or "download"
        dest_file = os.path.join(destination, filename)
        return run_shell(f"curl -L -o '{dest_file}' '{url}'")
    else:
        # Pure Python fallback
        try:
            filename = url.split("/")[-1] or "download"
            dest_file = os.path.join(destination, filename)
            urllib.request.urlretrieve(url, dest_file)
            return f"Downloaded to {dest_file}"
        except Exception as e:
            return f"Download error: {e}"


def get_public_ip() -> str:
    for url in ["https://ifconfig.me", "https://api.ipify.org", "https://ipecho.net/plain"]:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "curl/7.0"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                return f"Public IP: {resp.read().decode().strip()}"
        except Exception:
            continue
    return "Could not determine public IP"


def get_local_ip() -> str:
    return run_shell("ip -4 addr show | grep -oP '(?<=inet\\s)\\d+(\\.\\d+){3}' | grep -v 127.0.0.1 | head -5")


def wifi_networks() -> str:
    for cmd in ["nmcli dev wifi list", "iwlist scan 2>/dev/null | grep ESSID"]:
        result = run_shell(cmd)
        if result and "[exit" not in result:
            return result
    return "WiFi scan unavailable (needs NetworkManager or wireless tools)"


def wifi_connect(ssid: str, password: str = "") -> str:
    if not confirm(f"Connect to WiFi network '{ssid}'?"):
        return "Cancelled."
    if password:
        return run_shell(f"nmcli dev wifi connect '{ssid}' password '{password}'")
    return run_shell(f"nmcli dev wifi connect '{ssid}'")


def wifi_disconnect() -> str:
    return run_shell("nmcli dev disconnect $(nmcli -t -f DEVICE,TYPE dev | grep wifi | cut -d: -f1 | head -1)")


def speed_test() -> str:
    if shutil.which("speedtest-cli"):
        return run_shell("speedtest-cli --simple")
    if shutil.which("fast"):
        return run_shell("fast --upload")
    # Simple download speed test
    try:
        import time
        url = "http://speedtest.ftp.otenet.gr/files/test1Mb.db"
        start = time.time()
        urllib.request.urlretrieve(url, "/dev/null")
        elapsed = time.time() - start
        speed = (1 * 8) / elapsed  # 1MB file, convert to Mbps
        return f"Estimated download speed: {speed:.1f} Mbps (1MB test)"
    except Exception as e:
        return f"Speed test error: {e}\nInstall: pip install speedtest-cli"


def ssh_keygen(key_type: str = "ed25519", comment: str = "") -> str:
    import os
    key_path = os.path.expanduser(f"~/.ssh/id_{key_type}")
    if os.path.exists(key_path):
        return f"Key already exists: {key_path}\nUse -f to overwrite or choose a different type."
    comment_flag = f'-C "{comment}"' if comment else ""
    return run_shell(f"ssh-keygen -t {key_type} {comment_flag} -N '' -f {key_path}")


def list_ssh_keys() -> str:
    import os
    ssh_dir = os.path.expanduser("~/.ssh")
    if not os.path.exists(ssh_dir):
        return "No ~/.ssh directory found"
    result = run_shell(f"ls -la {ssh_dir}")
    pub_keys = run_shell(f"cat {ssh_dir}/*.pub 2>/dev/null")
    return f"SSH Directory:\n{result}\n\nPublic Keys:\n{pub_keys}" if pub_keys else result


def network_stats() -> str:
    import psutil
    counters = psutil.net_io_counters(pernic=True)
    lines = [f"{'Interface':15} {'Sent MB':>10} {'Recv MB':>10} {'Packets Out':>12} {'Packets In':>12}"]
    lines.append("-" * 65)
    for iface, stats in counters.items():
        lines.append(
            f"{iface:15} {stats.bytes_sent//(1024**2):>10} {stats.bytes_recv//(1024**2):>10}"
            f" {stats.packets_sent:>12} {stats.packets_recv:>12}"
        )
    return "\n".join(lines)


def register_network_tools(registry: ToolRegistry):
    registry.register("ping", ping, "Ping a host to check connectivity",
        {
            "host": {"type": "string", "description": "Hostname or IP to ping", "required": True},
            "count": {"type": "integer", "description": "Number of pings (default 4)"},
        })
    registry.register("traceroute", traceroute, "Trace network route to a host",
        {"host": {"type": "string", "description": "Hostname or IP", "required": True}})
    registry.register("dns_lookup", dns_lookup, "DNS lookup for a domain",
        {"domain": {"type": "string", "description": "Domain to look up", "required": True}})
    registry.register("reverse_dns", reverse_dns, "Reverse DNS lookup for an IP",
        {"ip": {"type": "string", "description": "IP address", "required": True}})
    registry.register("list_open_ports", list_open_ports, "List open/listening ports on this machine",
        {"all_ports": {"type": "boolean", "description": "Show all connections, not just listening"}})
    registry.register("check_port", check_port, "Check if a specific port is open on a host",
        {
            "host": {"type": "string", "description": "Hostname or IP", "required": True},
            "port": {"type": "integer", "description": "Port number", "required": True},
            "timeout": {"type": "integer", "description": "Timeout in seconds (default 3)"},
        })
    registry.register("firewall_status", firewall_status, "Show firewall rules and status", {})
    registry.register("firewall_allow", firewall_allow, "Allow a port through the firewall",
        {
            "port": {"type": "integer", "description": "Port to allow", "required": True},
            "protocol": {"type": "string", "description": "tcp or udp (default tcp)"},
        }, requires_confirm=True)
    registry.register("firewall_deny", firewall_deny, "Block a port in the firewall",
        {
            "port": {"type": "integer", "description": "Port to deny", "required": True},
            "protocol": {"type": "string", "description": "tcp or udp (default tcp)"},
        }, requires_confirm=True)
    registry.register("download_file", download_file, "Download a file from a URL",
        {
            "url": {"type": "string", "description": "URL to download", "required": True},
            "destination": {"type": "string", "description": "Save directory (default: ~/Downloads/)"},
        })
    registry.register("get_public_ip", get_public_ip, "Get your public/external IP address", {})
    registry.register("get_local_ip", get_local_ip, "Get local network IP address(es)", {})
    registry.register("wifi_networks", wifi_networks, "Scan and list available WiFi networks", {})
    registry.register("wifi_connect", wifi_connect, "Connect to a WiFi network",
        {
            "ssid": {"type": "string", "description": "WiFi network name (SSID)", "required": True},
            "password": {"type": "string", "description": "WiFi password (leave empty for open networks)"},
        }, requires_confirm=True)
    registry.register("wifi_disconnect", wifi_disconnect, "Disconnect from current WiFi network", {})
    registry.register("speed_test", speed_test, "Test internet connection speed", {})
    registry.register("ssh_keygen", ssh_keygen, "Generate an SSH key pair",
        {
            "key_type": {"type": "string", "description": "Key type: ed25519, rsa, ecdsa (default: ed25519)"},
            "comment": {"type": "string", "description": "Comment/label for the key"},
        })
    registry.register("list_ssh_keys", list_ssh_keys, "List SSH keys in ~/.ssh", {})
    registry.register("network_stats", network_stats, "Show network interface I/O statistics", {})
