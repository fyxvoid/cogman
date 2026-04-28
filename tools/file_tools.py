"""File system tools: list, read, write, find."""
import os
import glob
import logging
from pathlib import Path
from core.tool_registry import ToolRegistry
from core.safety import validate_path, confirm

log = logging.getLogger("cogman.tools.file")


def list_files(path: str = "~") -> str:
    path = os.path.expanduser(path)
    ok, reason = validate_path(path)
    if not ok:
        return f"[BLOCKED] {reason}"
    try:
        entries = sorted(Path(path).iterdir(), key=lambda p: (p.is_file(), p.name))
        lines = []
        for e in entries[:50]:
            kind = "DIR" if e.is_dir() else "FILE"
            size = e.stat().st_size if e.is_file() else "-"
            lines.append(f"  [{kind}] {e.name}" + (f"  ({size} bytes)" if e.is_file() else ""))
        result = "\n".join(lines) or "(empty directory)"
        total = len(list(Path(path).iterdir()))
        if total > 50:
            result += f"\n  ... and {total - 50} more"
        return f"Contents of {path}:\n{result}"
    except PermissionError:
        return f"Permission denied: {path}"
    except FileNotFoundError:
        return f"Directory not found: {path}"


def read_file(path: str) -> str:
    path = os.path.expanduser(path)
    ok, reason = validate_path(path)
    if not ok:
        return f"[BLOCKED] {reason}"
    try:
        size = os.path.getsize(path)
        if size > 100_000:
            return f"File too large ({size} bytes). Use 'run_shell head -n 100 {path}' instead."
        with open(path, "r", errors="replace") as f:
            return f.read()
    except FileNotFoundError:
        return f"File not found: {path}"
    except PermissionError:
        return f"Permission denied: {path}"
    except Exception as e:
        return f"Error reading file: {e}"


def write_file(path: str, content: str, overwrite: bool = False) -> str:
    path = os.path.expanduser(path)
    ok, reason = validate_path(path)
    if not ok:
        return f"[BLOCKED] {reason}"
    if os.path.exists(path) and not overwrite:
        if not confirm(f"File {path} exists. Overwrite?"):
            return "Write cancelled."
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            f.write(content)
        return f"Written {len(content)} bytes to {path}"
    except Exception as e:
        return f"Write error: {e}"


def find_files(pattern: str, directory: str = "~") -> str:
    directory = os.path.expanduser(directory)
    ok, reason = validate_path(directory)
    if not ok:
        return f"[BLOCKED] {reason}"
    try:
        matches = glob.glob(os.path.join(directory, "**", pattern), recursive=True)[:30]
        if not matches:
            return f"No files matching '{pattern}' found in {directory}"
        return f"Found {len(matches)} file(s):\n" + "\n".join(f"  {m}" for m in matches)
    except Exception as e:
        return f"Search error: {e}"


def register_file_tools(registry: ToolRegistry):
    registry.register(
        "list_files",
        list_files,
        "List files in a directory",
        {
            "path": {"type": "string", "description": "Directory path (default: ~)"},
        },
    )
    registry.register(
        "read_file",
        read_file,
        "Read the contents of a file",
        {"path": {"type": "string", "description": "File path to read", "required": True}},
    )
    registry.register(
        "write_file",
        write_file,
        "Write content to a file",
        {
            "path": {"type": "string", "description": "File path to write", "required": True},
            "content": {"type": "string", "description": "Content to write", "required": True},
            "overwrite": {"type": "boolean", "description": "Overwrite if exists (default false)"},
        },
        requires_confirm=True,
    )
    registry.register(
        "find_files",
        find_files,
        "Find files matching a glob pattern",
        {
            "pattern": {"type": "string", "description": "Glob pattern e.g. *.py", "required": True},
            "directory": {"type": "string", "description": "Search root directory (default: ~)"},
        },
    )
