"""
core/monitor.py — proactive system monitor daemon.

Runs as a background thread alongside the agent. Watches CPU, RAM, disk,
temperature, battery, network, services, and USB events. Fires voice +
desktop alerts when thresholds are crossed.

Wire in:
    from core.monitor import SystemMonitor
    monitor = SystemMonitor(speak_fn=speak, notify_fn=notify)
    monitor.start()
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Set

import psutil

log = logging.getLogger("cogman.monitor")


# ── Thresholds — all overridable via env vars ─────────────────────────────────

@dataclass
class Thresholds:
    cpu_percent:      float = float(os.getenv("COGMAN_MON_CPU",   "85"))
    cpu_sustained_s:  float = float(os.getenv("COGMAN_MON_CPU_S", "30"))
    ram_percent:      float = float(os.getenv("COGMAN_MON_RAM",   "88"))
    disk_percent:     float = float(os.getenv("COGMAN_MON_DISK",  "90"))
    temp_celsius:     float = float(os.getenv("COGMAN_MON_TEMP",  "85"))
    battery_low:      float = float(os.getenv("COGMAN_MON_BAT",   "15"))
    battery_critical: float = float(os.getenv("COGMAN_MON_BATC",  "5"))
    check_interval_s: float = float(os.getenv("COGMAN_MON_INT",   "15"))
    # Services to watch (comma-separated, empty = none by default)
    watched_services: List[str] = field(default_factory=lambda: [
        s for s in os.getenv("COGMAN_MON_SVCS", "").split(",") if s.strip()
    ])


# ── Alert state — prevents repeat alerts ─────────────────────────────────────

@dataclass
class _AlertState:
    # Track when each alert was last fired (alert_key → timestamp)
    last_fired: Dict[str, float] = field(default_factory=dict)
    # Track state for edge-triggered alerts (network, usb)
    network_ifaces: Set[str] = field(default_factory=set)
    usb_devices: Set[str] = field(default_factory=set)
    service_states: Dict[str, str] = field(default_factory=dict)
    # CPU: track high readings for sustained-alert
    cpu_high_since: Optional[float] = None

    def should_alert(self, key: str, cooldown_s: float = 300) -> bool:
        """Return True if this alert hasn't fired in the last cooldown_s seconds."""
        now = time.time()
        last = self.last_fired.get(key, 0)
        if now - last >= cooldown_s:
            self.last_fired[key] = now
            return True
        return False

    def reset(self, key: str):
        self.last_fired.pop(key, None)


# ── Monitor ───────────────────────────────────────────────────────────────────

class SystemMonitor:
    """
    Background thread that proactively watches the system and calls
    speak_fn / notify_fn when thresholds are crossed.
    """

    def __init__(
        self,
        speak_fn: Optional[Callable[[str], None]] = None,
        notify_fn: Optional[Callable[[str, str], None]] = None,
        thresholds: Optional[Thresholds] = None,
    ):
        self._speak  = speak_fn   or _null_speak
        self._notify = notify_fn  or _null_notify
        self._t      = thresholds or Thresholds()
        self._state  = _AlertState()
        self._thread: Optional[threading.Thread] = None
        self._stop   = threading.Event()

    # ── Public API ────────────────────────────────────────────────────────────

    def start(self) -> threading.Thread:
        """Start the monitor in a daemon background thread."""
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, name="cogman-monitor", daemon=True
        )
        self._thread.start()
        log.info(
            "SystemMonitor started (interval=%.0fs, CPU>%.0f%%, RAM>%.0f%%, disk>%.0f%%)",
            self._t.check_interval_s, self._t.cpu_percent,
            self._t.ram_percent, self._t.disk_percent,
        )
        # Seed network/USB baselines immediately
        self._seed_baselines()
        return self._thread

    def stop(self):
        self._stop.set()

    def status(self) -> Dict:
        """Return current readings dict (used by /status command)."""
        vm = psutil.virtual_memory()
        du = psutil.disk_usage("/")
        bat = psutil.sensors_battery()
        return {
            "cpu_percent":  psutil.cpu_percent(interval=0.5),
            "ram_percent":  vm.percent,
            "ram_used_gb":  vm.used / 1024**3,
            "ram_total_gb": vm.total / 1024**3,
            "disk_percent": du.percent,
            "disk_free_gb": du.free / 1024**3,
            "temp_celsius": _read_temp(),
            "battery_pct":  bat.percent if bat else None,
            "battery_plugged": bat.power_plugged if bat else None,
        }

    # ── Main loop ─────────────────────────────────────────────────────────────

    def _loop(self):
        while not self._stop.wait(self._t.check_interval_s):
            try:
                self._check_cpu()
                self._check_ram()
                self._check_disk()
                self._check_temp()
                self._check_battery()
                self._check_network()
                self._check_usb()
                if self._t.watched_services:
                    self._check_services()
            except Exception as e:
                log.debug("Monitor loop error: %s", e)

    # ── Individual checks ─────────────────────────────────────────────────────

    def _check_cpu(self):
        pct = psutil.cpu_percent(interval=1)
        now = time.time()
        if pct >= self._t.cpu_percent:
            if self._state.cpu_high_since is None:
                self._state.cpu_high_since = now
            elapsed = now - self._state.cpu_high_since
            if elapsed >= self._t.cpu_sustained_s and self._state.should_alert("cpu", cooldown_s=120):
                culprit = _top_cpu_process()
                from core.personality import cpu_alert
                msg = cpu_alert(pct, culprit)
                self._alert("CPU Alert", msg)
        else:
            self._state.cpu_high_since = None
            self._state.reset("cpu")

    def _check_ram(self):
        vm = psutil.virtual_memory()
        if vm.percent >= self._t.ram_percent and self._state.should_alert("ram", cooldown_s=180):
            from core.personality import ram_alert
            msg = ram_alert(vm.percent, vm.used / 1024**3, vm.total / 1024**3)
            self._alert("Memory Alert", msg)
        elif vm.percent < self._t.ram_percent - 10:
            self._state.reset("ram")

    def _check_disk(self):
        for part in psutil.disk_partitions(all=False):
            try:
                usage = psutil.disk_usage(part.mountpoint)
            except PermissionError:
                continue
            key = f"disk_{part.mountpoint}"
            if usage.percent >= self._t.disk_percent and self._state.should_alert(key, cooldown_s=600):
                from core.personality import disk_alert
                msg = disk_alert(usage.percent, usage.free / 1024**3, part.mountpoint)
                self._alert("Disk Alert", msg)

    def _check_temp(self):
        temp = _read_temp()
        if temp is None:
            return
        if temp >= self._t.temp_celsius and self._state.should_alert("temp", cooldown_s=120):
            from core.personality import temp_alert
            self._alert("Temperature Alert", temp_alert(temp))
        elif temp < self._t.temp_celsius - 10:
            self._state.reset("temp")

    def _check_battery(self):
        bat = psutil.sensors_battery()
        if bat is None or bat.power_plugged:
            self._state.reset("battery_low")
            self._state.reset("battery_critical")
            return
        pct = bat.percent
        if pct <= self._t.battery_critical and self._state.should_alert("battery_critical", cooldown_s=60):
            from core.personality import battery_alert
            self._alert("Battery Critical", battery_alert(pct, False))
        elif pct <= self._t.battery_low and self._state.should_alert("battery_low", cooldown_s=180):
            from core.personality import battery_alert
            self._alert("Battery Low", battery_alert(pct, False))

    def _check_network(self):
        current = _get_active_ifaces()
        prev = self._state.network_ifaces

        lost = prev - current
        gained = current - prev

        for iface in lost:
            if self._state.should_alert(f"net_down_{iface}", cooldown_s=30):
                from core.personality import network_lost_alert
                self._alert("Network", network_lost_alert(iface))

        for iface in gained:
            if iface in self._state.last_fired.get(f"net_down_{iface}", 0).__class__.__mro__:
                from core.personality import network_up_alert
                self._alert("Network", network_up_alert(iface))

        self._state.network_ifaces = current

    def _check_usb(self):
        current = _get_usb_devices()
        prev = self._state.usb_devices

        added   = current - prev
        removed = prev    - current

        for dev in added:
            from core.personality import usb_connected_alert
            self._speak_only(usb_connected_alert(dev))

        for dev in removed:
            from core.personality import usb_disconnected_alert
            self._speak_only(usb_disconnected_alert(dev))

        self._state.usb_devices = current

    def _check_services(self):
        for svc in self._t.watched_services:
            state = _service_state(svc)
            prev = self._state.service_states.get(svc, "unknown")
            self._state.service_states[svc] = state

            if state == "failed" and prev != "failed":
                from core.personality import service_down_alert
                self._alert(f"Service {svc}", service_down_alert(svc))
                # Attempt restart
                try:
                    subprocess.run(
                        ["systemctl", "restart", svc], timeout=10, capture_output=True
                    )
                    new_state = _service_state(svc)
                    if new_state == "active":
                        from core.personality import service_restarted_alert
                        self._speak_only(service_restarted_alert(svc))
                        self._state.service_states[svc] = "active"
                except Exception:
                    pass

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _alert(self, title: str, message: str):
        log.info("ALERT [%s]: %s", title, message)
        try:
            self._notify(title, message)
        except Exception:
            pass
        try:
            self._speak(message)
        except Exception:
            pass

    def _speak_only(self, message: str):
        log.info("ANNOUNCE: %s", message)
        try:
            self._speak(message)
        except Exception:
            pass

    def _seed_baselines(self):
        """Capture initial state so we only alert on *changes*."""
        self._state.network_ifaces = _get_active_ifaces()
        self._state.usb_devices    = _get_usb_devices()
        for svc in self._t.watched_services:
            self._state.service_states[svc] = _service_state(svc)
        log.debug(
            "Monitor baselines: ifaces=%s usb_devices=%d services=%s",
            self._state.network_ifaces,
            len(self._state.usb_devices),
            list(self._state.service_states.keys()),
        )


# ── System helpers ────────────────────────────────────────────────────────────

def _top_cpu_process(n: int = 1) -> Optional[str]:
    try:
        procs = sorted(
            psutil.process_iter(["name", "cpu_percent"]),
            key=lambda p: p.info["cpu_percent"] or 0,
            reverse=True,
        )
        top = [p.info["name"] for p in procs[:n] if p.info["cpu_percent"] > 5]
        return top[0] if top else None
    except Exception:
        return None


def _read_temp() -> Optional[float]:
    try:
        temps = psutil.sensors_temperatures()
        if not temps:
            return None
        for key in ("coretemp", "k10temp", "cpu_thermal", "acpitz"):
            if key in temps:
                readings = temps[key]
                if readings:
                    return max(r.current for r in readings)
        for readings in temps.values():
            if readings:
                return max(r.current for r in readings)
    except Exception:
        pass
    # Fallback: read sysfs
    try:
        import glob
        zones = glob.glob("/sys/class/thermal/thermal_zone*/temp")
        if zones:
            return max(int(open(z).read()) / 1000 for z in zones)
    except Exception:
        pass
    return None


def _get_active_ifaces() -> Set[str]:
    try:
        stats = psutil.net_if_stats()
        return {k for k, v in stats.items() if v.isup and k != "lo"}
    except Exception:
        return set()


def _get_usb_devices() -> Set[str]:
    try:
        result = subprocess.run(
            ["lsusb"], capture_output=True, text=True, timeout=3
        )
        lines = result.stdout.strip().splitlines()
        devices = set()
        for line in lines:
            # "Bus 002 Device 003: ID 1234:5678 Kingston DataTraveler"
            m = re.search(r"ID \w+:\w+ (.+)$", line)
            if m:
                name = m.group(1).strip()
                # Skip root hubs and internal devices
                if "root hub" not in name.lower() and "hub" not in name.lower():
                    devices.add(name)
        return devices
    except Exception:
        return set()


def _service_state(name: str) -> str:
    try:
        r = subprocess.run(
            ["systemctl", "is-active", name],
            capture_output=True, text=True, timeout=5
        )
        return r.stdout.strip()   # active / inactive / failed / unknown
    except Exception:
        return "unknown"


def _null_speak(text: str):
    log.info("[monitor-speak] %s", text)


def _null_notify(title: str, message: str):
    log.info("[monitor-notify] %s: %s", title, message)
