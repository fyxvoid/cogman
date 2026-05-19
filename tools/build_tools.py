"""
Build tools — interface to rogue-linux cogman-planner for the AI agent.

Exposes:
  pkg_plan             — generate a build/install plan from a .toml manifest
  pkg_validate         — validate a .toml manifest schema (dry-run)
  pkg_list_definitions — list all .toml definitions in packages/
  build_status         — check cogman-planner availability
"""
import os
import subprocess
import tempfile
from pathlib import Path

from core.tool_registry import ToolRegistry

# ── Binary resolution ─────────────────────────────────────────────────────────
#
# Search order:
#   1. ~/void/academic/rogue-linux/bin/  (the upstream rogue-linux build)
#   2. Project-local bin/
#   3. PATH fallback

_ROGUE_BIN = Path.home() / "void" / "academic" / "rogue-linux" / "bin"
_PROJECT_BIN = Path(__file__).parent.parent / "bin"
_PACKAGES_DIR = Path(__file__).parent.parent / "packages"


def _find_bin(name: str) -> str:
    for candidate in [_ROGUE_BIN / name, _PROJECT_BIN / name]:
        if candidate.exists():
            return str(candidate)
    return name  # rely on PATH


def _planner() -> str:
    return _find_bin("cogman-planner")


def _run(args: list[str], *, timeout: int = 60) -> tuple[bool, str]:
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        out = (r.stdout + r.stderr).strip()
        return r.returncode == 0, out
    except FileNotFoundError:
        return False, f"Binary not found: {args[0]!r}. Install rogue-linux or add it to PATH."
    except subprocess.TimeoutExpired:
        return False, "Timed out"
    except Exception as e:
        return False, str(e)


# ── Tools ─────────────────────────────────────────────────────────────────────

def pkg_plan(
    toml: str,
    output: str = "",
    rootfs: str = "/",
    variant: str = "build",
    native: bool = False,
    no_cache: bool = False,
) -> str:
    """
    Generate a dependency-ordered build plan from a package .toml manifest.

    Args:
        toml:     Path to the package .toml file.
        output:   Write binary plan to this file (default: /tmp/<name>.plan).
        rootfs:   Installation root for the plan (default: /).
        variant:  'build' (compile from source) or 'binary' (prebuilt install).
        native:   Enable CPU-native optimisations (implies variant=build).
        no_cache: Skip plan cache — always re-plan from scratch.
    """
    if not os.path.exists(toml):
        return f"Error: {toml!r} not found"

    if not output:
        stem = Path(toml).stem
        output = str(Path(tempfile.gettempdir()) / f"{stem}.plan")

    cmd = [_planner(), "build", toml, "--output", output, "--rootfs", rootfs]

    if variant == "binary":
        cmd.append("--binary")
    else:
        cmd.append("--build")

    if native:
        cmd.append("--native")
    if no_cache:
        cmd.append("--no-cache")

    ok, out = _run(cmd, timeout=120)
    if ok:
        size = Path(output).stat().st_size if Path(output).exists() else 0
        return f"Plan written → {output}  ({size} bytes)\n{out}"
    return f"planner error:\n{out}"


def pkg_validate(toml: str) -> str:
    """
    Validate a package .toml manifest against the rogue-linux schema.
    Runs cogman-planner with --no-cache and --explain disabled — stops after
    the validation + dep-resolution phase by writing to /dev/null.
    Returns schema feedback without executing any build steps.
    """
    if not os.path.exists(toml):
        return f"Error: {toml!r} not found"

    cmd = [
        _planner(), "build", toml,
        "--build",
        "--output", "/dev/null",
        "--rootfs", "/",
        "--no-cache",
    ]
    ok, out = _run(cmd, timeout=30)
    # cogman-planner exits 0 on success; any non-zero is a validation failure
    tag = "VALID" if ok else "INVALID"
    return f"[{tag}] {Path(toml).name}\n{out}"


def pkg_list_definitions(packages_dir: str = "") -> str:
    """List all package .toml definitions in the packages/ directory."""
    base = Path(packages_dir) if packages_dir else _PACKAGES_DIR
    if not base.exists():
        return f"packages directory not found: {base}"
    tomls = sorted(base.rglob("*.toml"))
    if not tomls:
        return f"No package definitions found in {base}"
    lines = [f"Package definitions in {base}  ({len(tomls)} found):"]
    for t in tomls:
        rel = t.relative_to(base)
        lines.append(f"  {rel}")
    return "\n".join(lines)


def build_status() -> str:
    """Check if cogman-planner is available and report its version."""
    bin_path = _planner()
    ok, ver = _run([bin_path, "--version"])
    if ok:
        return f"cogman-planner  {ver}\npath: {bin_path}\npackages: {_PACKAGES_DIR}"
    return (
        f"cogman-planner not found at: {bin_path}\n"
        f"Expected location: {_ROGUE_BIN / 'cogman-planner'}\n"
        f"Clone rogue-linux and build it, or set PATH accordingly."
    )


# ── Register ──────────────────────────────────────────────────────────────────

def register_build_tools(registry: ToolRegistry):
    registry.register(
        "pkg_plan",
        pkg_plan,
        "Generate a rogue-linux build plan from a package .toml manifest (cogman-planner)",
        {
            "toml":     {"type": "string", "description": "Path to package .toml file", "required": True},
            "output":   {"type": "string", "description": "Output plan file path (default: /tmp/<name>.plan)"},
            "rootfs":   {"type": "string", "description": "Installation root (default: /)"},
            "variant":  {"type": "string", "description": "build (compile) or binary (prebuilt) — default: build"},
            "native":   {"type": "boolean", "description": "Enable CPU-native optimisations"},
            "no_cache": {"type": "boolean", "description": "Skip plan cache"},
        },
    )
    registry.register(
        "pkg_validate",
        pkg_validate,
        "Validate a package .toml against the rogue-linux schema — no build is executed",
        {
            "toml": {"type": "string", "description": "Path to package .toml file", "required": True},
        },
    )
    registry.register(
        "pkg_list_definitions",
        pkg_list_definitions,
        "List all package .toml definitions in packages/",
        {
            "packages_dir": {"type": "string", "description": "Custom packages directory (default: project packages/)"},
        },
    )
    registry.register(
        "build_status",
        build_status,
        "Check if cogman-planner (rogue-linux) is available and ready",
        {},
    )
