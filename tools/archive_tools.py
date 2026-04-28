"""Archive tools: tar, zip, gzip, bzip2, 7z — create and extract."""
import os
import shutil
import logging
from core.tool_registry import ToolRegistry
from core.system_controller import run_shell

log = logging.getLogger("cogman.tools.archive")


def _expand(path: str) -> str:
    return os.path.expanduser(path)


def extract(archive: str, destination: str = "") -> str:
    archive = _expand(archive)
    dest = _expand(destination) if destination else os.path.dirname(archive) or "."
    os.makedirs(dest, exist_ok=True)

    a = archive.lower()
    if a.endswith(".tar.gz") or a.endswith(".tgz"):
        return run_shell(f"tar -xzf '{archive}' -C '{dest}'") or f"Extracted to {dest}"
    elif a.endswith(".tar.bz2") or a.endswith(".tbz2"):
        return run_shell(f"tar -xjf '{archive}' -C '{dest}'") or f"Extracted to {dest}"
    elif a.endswith(".tar.xz") or a.endswith(".txz"):
        return run_shell(f"tar -xJf '{archive}' -C '{dest}'") or f"Extracted to {dest}"
    elif a.endswith(".tar.zst"):
        return run_shell(f"tar --zstd -xf '{archive}' -C '{dest}'") or f"Extracted to {dest}"
    elif a.endswith(".tar"):
        return run_shell(f"tar -xf '{archive}' -C '{dest}'") or f"Extracted to {dest}"
    elif a.endswith(".zip"):
        return run_shell(f"unzip -o '{archive}' -d '{dest}'")
    elif a.endswith(".gz"):
        return run_shell(f"gunzip -k '{archive}'") or f"Extracted {archive}"
    elif a.endswith(".bz2"):
        return run_shell(f"bunzip2 -k '{archive}'") or f"Extracted {archive}"
    elif a.endswith(".xz"):
        return run_shell(f"unxz -k '{archive}'") or f"Extracted {archive}"
    elif a.endswith(".7z"):
        if shutil.which("7z"):
            return run_shell(f"7z x '{archive}' -o'{dest}'")
        return "7z not installed: sudo apt install p7zip-full"
    elif a.endswith(".rar"):
        if shutil.which("unrar"):
            return run_shell(f"unrar x '{archive}' '{dest}/'")
        return "unrar not installed: sudo apt install unrar"
    else:
        # Try auto-detect
        return run_shell(f"file '{archive}' && tar -xf '{archive}' -C '{dest}' 2>/dev/null || unzip '{archive}' -d '{dest}' 2>/dev/null")


def create_tar(output: str, files: str, compress: str = "gz") -> str:
    output = _expand(output)
    compress_flags = {"gz": "z", "bz2": "j", "xz": "J", "none": ""}.get(compress, "z")
    ext_map = {"gz": ".tar.gz", "bz2": ".tar.bz2", "xz": ".tar.xz", "none": ".tar"}
    ext = ext_map.get(compress, ".tar.gz")

    if not output.endswith(ext):
        output += ext

    return run_shell(f"tar -c{compress_flags}f '{output}' {files}") or f"Created {output}"


def create_zip(output: str, files: str) -> str:
    output = _expand(output)
    if not output.endswith(".zip"):
        output += ".zip"
    return run_shell(f"zip -r '{output}' {files}") or f"Created {output}"


def list_archive(archive: str) -> str:
    archive = _expand(archive)
    a = archive.lower()

    if ".tar" in a:
        return run_shell(f"tar -tf '{archive}' 2>&1 | head -50")
    elif a.endswith(".zip"):
        return run_shell(f"unzip -l '{archive}' 2>&1 | head -50")
    elif a.endswith(".7z"):
        return run_shell(f"7z l '{archive}' 2>&1 | head -50")
    elif a.endswith(".rar"):
        return run_shell(f"unrar l '{archive}' 2>&1 | head -50")
    return f"Unknown archive format: {archive}"


def compress_file(file: str, method: str = "gzip") -> str:
    file = _expand(file)
    if method == "gzip":
        return run_shell(f"gzip -k '{file}'") or f"Compressed: {file}.gz"
    elif method == "bzip2":
        return run_shell(f"bzip2 -k '{file}'") or f"Compressed: {file}.bz2"
    elif method == "xz":
        return run_shell(f"xz -k '{file}'") or f"Compressed: {file}.xz"
    elif method == "zstd":
        return run_shell(f"zstd '{file}'") or f"Compressed: {file}.zst"
    return f"Unknown method: {method}"


def register_archive_tools(registry: ToolRegistry):
    registry.register("extract", extract, "Extract any archive (tar, zip, gz, bz2, xz, 7z, rar)",
        {
            "archive": {"type": "string", "description": "Path to archive file", "required": True},
            "destination": {"type": "string", "description": "Extraction destination directory"},
        })
    registry.register("create_tar", create_tar, "Create a tar archive",
        {
            "output": {"type": "string", "description": "Output archive path", "required": True},
            "files": {"type": "string", "description": "Files/directories to include", "required": True},
            "compress": {"type": "string", "description": "Compression: gz, bz2, xz, none (default: gz)"},
        })
    registry.register("create_zip", create_zip, "Create a zip archive",
        {
            "output": {"type": "string", "description": "Output zip file path", "required": True},
            "files": {"type": "string", "description": "Files/directories to include", "required": True},
        })
    registry.register("list_archive", list_archive, "List contents of an archive without extracting",
        {"archive": {"type": "string", "description": "Archive file path", "required": True}})
    registry.register("compress_file", compress_file, "Compress a single file",
        {
            "file": {"type": "string", "description": "File to compress", "required": True},
            "method": {"type": "string", "description": "Method: gzip, bzip2, xz, zstd (default: gzip)"},
        })
