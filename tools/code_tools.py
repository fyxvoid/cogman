"""
Code execution tools — inspired by Hermes Agent tools/code_execution_tool.py.

Tools:
  run_python     — execute Python code in a subprocess sandbox
  run_script     — execute a shell script
  check_syntax   — check Python syntax without running
  format_code    — format Python code with black/autopep8
  lint_code      — lint Python code with pylint/flake8/ruff
  install_and_run— pip install a package then use it
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import textwrap
from typing import Optional

_MAX_OUTPUT = 8000  # max chars to return


def run_python(code: str, timeout: int = 30, packages: str = "") -> str:
    """
    Execute Python code in a subprocess sandbox.
    Optionally install packages first (comma-separated).
    Returns stdout + stderr (truncated if long).
    """
    if packages:
        pkg_list = [p.strip() for p in packages.split(",") if p.strip()]
        for pkg in pkg_list:
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "-q", pkg],
                capture_output=True, timeout=60,
            )

    # Write to temp file for cleaner tracebacks
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        # Dedent in case LLM adds leading whitespace
        f.write(textwrap.dedent(code))
        tmp_path = f.name

    try:
        result = subprocess.run(
            [sys.executable, tmp_path],
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, "PYTHONPATH": "."},
        )
        output = ""
        if result.stdout:
            output += result.stdout
        if result.stderr:
            output += "\n[stderr]\n" + result.stderr
        if not output:
            output = "(no output)"
        return output[:_MAX_OUTPUT]
    except subprocess.TimeoutExpired:
        return f"Timeout after {timeout}s"
    except Exception as e:
        return f"Execution error: {e}"
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


def run_script(script: str, shell: str = "bash", timeout: int = 60) -> str:
    """
    Execute a shell script (bash/zsh/sh/fish).
    Returns stdout + stderr.
    """
    valid_shells = {"bash", "sh", "zsh", "fish", "dash"}
    if shell not in valid_shells:
        return f"Invalid shell: {shell}. Use: {', '.join(valid_shells)}"

    # Safety: warn about obviously dangerous patterns
    dangerous = [
        r"rm\s+-rf\s+/",
        r"mkfs\.",
        r":(){:|:&};:",   # fork bomb
        r">\s*/dev/sd",
        r"dd\s+if=.*of=/dev/",
    ]
    for pat in dangerous:
        if re.search(pat, script):
            return f"Blocked: script contains dangerous pattern ({pat}). Rewrite to be safer."

    with tempfile.NamedTemporaryFile(mode="w", suffix=".sh", delete=False) as f:
        f.write(f"#!/usr/bin/{shell}\nset -euo pipefail\n\n{script}\n")
        tmp_path = f.name

    os.chmod(tmp_path, 0o700)
    try:
        result = subprocess.run(
            [shell, tmp_path],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = result.stdout
        if result.stderr:
            output += "\n[stderr]\n" + result.stderr
        if result.returncode != 0:
            output += f"\n[exit {result.returncode}]"
        return output[:_MAX_OUTPUT] or "(no output)"
    except subprocess.TimeoutExpired:
        return f"Script timeout after {timeout}s"
    except Exception as e:
        return f"Script error: {e}"
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


def check_syntax(code: str, language: str = "python") -> str:
    """Check syntax of code without executing it."""
    if language.lower() == "python":
        try:
            import ast
            ast.parse(code)
            return "Syntax OK — no errors found."
        except SyntaxError as e:
            return f"SyntaxError at line {e.lineno}: {e.msg}\n  {e.text}"
    elif language.lower() in ("bash", "sh"):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".sh", delete=False) as f:
            f.write(code)
            tmp = f.name
        try:
            result = subprocess.run(["bash", "-n", tmp], capture_output=True, text=True)
            if result.returncode == 0:
                return "Syntax OK — no errors found."
            return result.stderr
        except FileNotFoundError:
            return "bash not found."
        finally:
            os.unlink(tmp)
    else:
        return f"Syntax check not supported for: {language}"


def format_code(code: str, language: str = "python") -> str:
    """Format code using black, autopep8, or prettier."""
    if language.lower() == "python":
        # Try black first
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            tmp = f.name
        try:
            result = subprocess.run(
                ["black", "--quiet", tmp], capture_output=True, text=True,
            )
            if result.returncode == 0:
                with open(tmp) as f:
                    return f.read()
            # Try autopep8
            result = subprocess.run(
                ["autopep8", "-"], input=code, capture_output=True, text=True,
            )
            if result.returncode == 0 and result.stdout:
                return result.stdout
            return f"Formatting failed. Install: pip install black"
        finally:
            try:
                os.unlink(tmp)
            except Exception:
                pass
    elif language.lower() in ("js", "javascript", "ts", "typescript"):
        result = subprocess.run(
            ["prettier", "--stdin-filepath", f"file.{language}"],
            input=code, capture_output=True, text=True,
        )
        if result.returncode == 0:
            return result.stdout
        return "Install prettier: npm install -g prettier"
    return f"Format not supported for: {language}"


def lint_code(code: str, language: str = "python") -> str:
    """Lint code for errors and style issues."""
    if language.lower() != "python":
        return f"Linting not supported for: {language}"

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(code)
        tmp = f.name

    try:
        # Try ruff (fastest)
        result = subprocess.run(
            ["ruff", "check", tmp, "--output-format=text"],
            capture_output=True, text=True,
        )
        if result.returncode in (0, 1):
            return result.stdout or "No issues found (ruff)."

        # Try flake8
        result = subprocess.run(
            ["flake8", "--max-line-length=100", tmp],
            capture_output=True, text=True,
        )
        if result.returncode in (0, 1):
            return result.stdout or "No issues found (flake8)."

        return "Install a linter: pip install ruff  or  pip install flake8"
    finally:
        try:
            os.unlink(tmp)
        except Exception:
            pass


def run_python_with_input(code: str, stdin_data: str = "", timeout: int = 30) -> str:
    """Run Python code with stdin data."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(textwrap.dedent(code))
        tmp = f.name
    try:
        result = subprocess.run(
            [sys.executable, tmp],
            input=stdin_data,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = result.stdout + (("\n[stderr]\n" + result.stderr) if result.stderr else "")
        return output[:_MAX_OUTPUT] or "(no output)"
    except subprocess.TimeoutExpired:
        return f"Timeout after {timeout}s"
    finally:
        try:
            os.unlink(tmp)
        except Exception:
            pass


def explain_error(error_text: str) -> str:
    """Format a Python traceback for easier reading."""
    lines = error_text.strip().splitlines()
    if not lines:
        return "No error text provided."
    # Find the actual error type and message
    for line in reversed(lines):
        if re.match(r"^\w+Error:", line) or re.match(r"^\w+Exception:", line):
            return f"Error: {line}\n\nFull traceback:\n{error_text}"
    return error_text


def register_code_tools(registry):
    registry.register(
        "run_python",
        run_python,
        "Execute Python code in a subprocess sandbox and return output",
        parameters={
            "code": {"type": "string", "description": "Python code to execute", "required": True},
            "timeout": {"type": "integer", "description": "Timeout in seconds (default 30)"},
            "packages": {"type": "string", "description": "Comma-separated pip packages to install first"},
        },
    )
    registry.register(
        "run_script",
        run_script,
        "Execute a shell script (bash/sh/zsh) and return output",
        parameters={
            "script": {"type": "string", "description": "Shell script to run", "required": True},
            "shell": {"type": "string", "description": "Shell to use: bash, sh, zsh (default bash)"},
            "timeout": {"type": "integer", "description": "Timeout in seconds (default 60)"},
        },
    )
    registry.register(
        "check_syntax",
        check_syntax,
        "Check code syntax without executing it",
        parameters={
            "code": {"type": "string", "description": "Code to check", "required": True},
            "language": {"type": "string", "description": "Language: python, bash (default python)"},
        },
    )
    registry.register(
        "format_code",
        format_code,
        "Format code using black (Python) or prettier (JS/TS)",
        parameters={
            "code": {"type": "string", "description": "Code to format", "required": True},
            "language": {"type": "string", "description": "Language: python, javascript, typescript"},
        },
    )
    registry.register(
        "lint_code",
        lint_code,
        "Lint code for errors and style issues using ruff or flake8",
        parameters={
            "code": {"type": "string", "description": "Python code to lint", "required": True},
        },
    )
    registry.register(
        "run_python_with_input",
        run_python_with_input,
        "Run Python code with stdin data",
        parameters={
            "code": {"type": "string", "description": "Python code", "required": True},
            "stdin_data": {"type": "string", "description": "Data to pass to stdin"},
            "timeout": {"type": "integer", "description": "Timeout in seconds"},
        },
    )
