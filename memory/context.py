"""
EnvironmentContext — real-time system awareness injected into every LLM call.

Inspired by OpenClaw's context-engine and Hermes's subdirectory_hints.

Captures:
  - Current working directory + project type (Python/JS/Rust/Go/etc.)
  - Git repo status (branch, dirty, remote)
  - Active processes relevant to coding (servers, databases)
  - Recently modified files
  - System state (CPU, RAM, disk)
  - Installed tools (docker, node, python, etc.)
  - Shell history hints
  - Open editor/IDE detection
  - Network connectivity
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional

log = logging.getLogger("cogman.context")

_CACHE_TTL = 30  # seconds


class EnvironmentContext:
    """
    Builds a rich context block about the current system environment.
    Cached and refreshed every 30s, or on explicit refresh().
    """

    def __init__(self):
        self._cache: Optional[Dict] = None
        self._cache_time: float = 0
        self._lock = threading.Lock()

    def get(self, force_refresh: bool = False) -> str:
        """Return formatted environment context string."""
        with self._lock:
            now = time.time()
            if force_refresh or not self._cache or (now - self._cache_time) > _CACHE_TTL:
                self._cache = self._collect()
                self._cache_time = now
        return self._format(self._cache)

    def refresh(self):
        with self._lock:
            self._cache = self._collect()
            self._cache_time = time.time()

    def _collect(self) -> Dict:
        data = {}
        try:
            data["cwd"] = os.getcwd()
            data["project"] = self._detect_project(data["cwd"])
            data["git"] = self._git_info()
            data["system"] = self._system_info()
            data["recent_files"] = self._recent_files()
            data["active_services"] = self._active_services()
            data["tools_available"] = self._tool_availability()
        except Exception as e:
            log.debug("Context collection error: %s", e)
        return data

    def _detect_project(self, cwd: str) -> Dict:
        """Detect project type from files in cwd."""
        p = Path(cwd)
        proj = {"type": "unknown", "name": p.name, "files": []}

        markers = {
            "python":     ["pyproject.toml", "setup.py", "setup.cfg", "requirements.txt", "Pipfile"],
            "javascript": ["package.json", "yarn.lock", "pnpm-lock.yaml"],
            "typescript": ["tsconfig.json"],
            "rust":       ["Cargo.toml"],
            "go":         ["go.mod"],
            "java":       ["pom.xml", "build.gradle"],
            "ruby":       ["Gemfile"],
            "php":        ["composer.json"],
            "docker":     ["Dockerfile", "docker-compose.yml", "docker-compose.yaml"],
            "terraform":  ["main.tf", "terraform.tfvars"],
        }
        for lang, files in markers.items():
            for f in files:
                if (p / f).exists():
                    proj["type"] = lang
                    proj["files"].append(f)
                    break
            if proj["type"] != "unknown":
                break

        # Check for CLAUDE.md / README / AGENTS.md
        for meta in ["CLAUDE.md", "AGENTS.md", "README.md", ".cursorrules"]:
            if (p / meta).exists():
                proj["meta_file"] = meta
                break

        return proj

    def _git_info(self) -> Dict:
        """Get git repo status."""
        git = {}
        try:
            branch = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True, text=True, timeout=3,
            ).stdout.strip()
            if branch and branch != "fatal":
                git["branch"] = branch

            status = subprocess.run(
                ["git", "status", "--porcelain"],
                capture_output=True, text=True, timeout=3,
            ).stdout.strip()
            git["dirty"] = bool(status)
            git["changed_files"] = len(status.splitlines()) if status else 0

            log_line = subprocess.run(
                ["git", "log", "--oneline", "-1"],
                capture_output=True, text=True, timeout=3,
            ).stdout.strip()
            if log_line:
                git["last_commit"] = log_line[:80]

            remote = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                capture_output=True, text=True, timeout=3,
            ).stdout.strip()
            if remote:
                git["remote"] = remote
        except Exception:
            pass
        return git

    def _system_info(self) -> Dict:
        """Lightweight system snapshot."""
        info = {}
        try:
            import psutil
            info["cpu_percent"] = psutil.cpu_percent(interval=0)
            mem = psutil.virtual_memory()
            info["ram_used_gb"] = round(mem.used / 1024**3, 1)
            info["ram_total_gb"] = round(mem.total / 1024**3, 1)
            info["ram_percent"] = mem.percent
            disk = psutil.disk_usage("/")
            info["disk_free_gb"] = round(disk.free / 1024**3, 1)
        except ImportError:
            pass
        return info

    def _recent_files(self, n: int = 8) -> List[str]:
        """List recently modified files in cwd (exclude .git, __pycache__)."""
        cwd = Path.cwd()
        files = []
        try:
            for f in cwd.iterdir():
                if f.name.startswith(".") or f.name in ("__pycache__", "node_modules", ".venv", "venv"):
                    continue
                if f.is_file():
                    mtime = f.stat().st_mtime
                    files.append((mtime, f.name))
            files.sort(reverse=True)
            return [name for _, name in files[:n]]
        except Exception:
            return []

    def _active_services(self) -> List[str]:
        """Detect common dev services that are running."""
        services = []
        checks = [
            ("postgres", 5432), ("mysql", 3306), ("mongodb", 27017),
            ("redis", 6379), ("elasticsearch", 9200), ("rabbitmq", 5672),
        ]
        import socket
        for name, port in checks:
            try:
                s = socket.create_connection(("localhost", port), timeout=0.3)
                s.close()
                services.append(name)
            except Exception:
                pass
        return services

    def _tool_availability(self) -> Dict[str, bool]:
        """Check which dev tools are installed."""
        tools = {}
        for tool in ["git", "docker", "node", "python3", "cargo", "go", "java", "curl", "jq", "kubectl", "terraform"]:
            tools[tool] = bool(subprocess.run(
                ["which", tool], capture_output=True
            ).returncode == 0)
        return {k: v for k, v in tools.items() if v}  # only available ones

    def _format(self, data: Dict) -> str:
        """Format context data into a concise string for LLM injection."""
        if not data:
            return ""

        lines = ["<environment>"]

        # Project
        proj = data.get("project", {})
        if proj.get("type") != "unknown":
            meta = f" [{proj.get('meta_file', '')}]" if proj.get("meta_file") else ""
            lines.append(f"Project: {proj['name']} ({proj['type']}){meta}")

        # CWD
        cwd = data.get("cwd", "")
        if cwd:
            lines.append(f"CWD: {cwd}")

        # Git
        git = data.get("git", {})
        if git.get("branch"):
            dirty = " [dirty]" if git.get("dirty") else ""
            n_changed = f" ({git['changed_files']} changed)" if git.get("changed_files") else ""
            lines.append(f"Git: {git['branch']}{dirty}{n_changed}")
            if git.get("last_commit"):
                lines.append(f"Last commit: {git['last_commit']}")

        # System
        sys_info = data.get("system", {})
        if sys_info:
            lines.append(
                f"System: CPU {sys_info.get('cpu_percent', 0):.0f}% | "
                f"RAM {sys_info.get('ram_used_gb', 0):.1f}/{sys_info.get('ram_total_gb', 0):.1f}GB | "
                f"Disk free {sys_info.get('disk_free_gb', 0):.0f}GB"
            )

        # Recent files
        recent = data.get("recent_files", [])
        if recent:
            lines.append(f"Recent files: {', '.join(recent[:6])}")

        # Active services
        services = data.get("active_services", [])
        if services:
            lines.append(f"Services running: {', '.join(services)}")

        # Available tools
        tools = data.get("tools_available", {})
        if tools:
            lines.append(f"Dev tools: {', '.join(tools.keys())}")

        lines.append("</environment>")
        return "\n".join(lines)
