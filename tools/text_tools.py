"""Text processing: grep, diff, wc, hash, base64, sort, jq, regex, template."""
import os
import hashlib
import base64
import re
import logging
from core.tool_registry import ToolRegistry
from core.system_controller import run_shell

log = logging.getLogger("cogman.tools.text")


def grep_in_file(pattern: str, file: str, ignore_case: bool = False,
                 line_numbers: bool = True, context: int = 0) -> str:
    file = os.path.expanduser(file)
    flags = []
    if ignore_case:
        flags.append("-i")
    if line_numbers:
        flags.append("-n")
    if context > 0:
        flags.append(f"-C {context}")
    flag_str = " ".join(flags)
    return run_shell(f"grep {flag_str} -E '{pattern}' '{file}' 2>&1 | head -50")


def grep_in_dir(pattern: str, directory: str = ".", file_pattern: str = "",
                ignore_case: bool = False, recursive: bool = True) -> str:
    directory = os.path.expanduser(directory)
    flags = ["-r" if recursive else "", "-n", "-i" if ignore_case else ""]
    flag_str = " ".join(f for f in flags if f)
    include = f"--include='{file_pattern}'" if file_pattern else ""
    return run_shell(f"grep {flag_str} {include} -E '{pattern}' '{directory}' 2>&1 | head -40")


def word_count(file: str) -> str:
    file = os.path.expanduser(file)
    result = run_shell(f"wc -lwc '{file}'")
    return result


def file_diff(file1: str, file2: str, unified: bool = True) -> str:
    file1, file2 = os.path.expanduser(file1), os.path.expanduser(file2)
    flag = "-u" if unified else ""
    return run_shell(f"diff {flag} '{file1}' '{file2}' 2>&1 | head -60")


def hash_file(file: str, algorithm: str = "sha256") -> str:
    file = os.path.expanduser(file)
    algo_map = {
        "md5": hashlib.md5, "sha1": hashlib.sha1,
        "sha256": hashlib.sha256, "sha512": hashlib.sha512,
    }
    algo_fn = algo_map.get(algorithm.lower())
    if not algo_fn:
        return f"Unknown algorithm: {algorithm}. Use: md5, sha1, sha256, sha512"
    try:
        h = algo_fn()
        with open(file, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return f"{algorithm.upper()}: {h.hexdigest()}  {file}"
    except FileNotFoundError:
        return f"File not found: {file}"


def hash_text(text: str, algorithm: str = "sha256") -> str:
    algo_map = {
        "md5": hashlib.md5, "sha1": hashlib.sha1,
        "sha256": hashlib.sha256, "sha512": hashlib.sha512,
    }
    algo_fn = algo_map.get(algorithm.lower())
    if not algo_fn:
        return f"Unknown algorithm: {algorithm}"
    h = algo_fn(text.encode()).hexdigest()
    return f"{algorithm.upper()}: {h}"


def base64_encode(text: str) -> str:
    return base64.b64encode(text.encode()).decode()


def base64_decode(text: str) -> str:
    try:
        return base64.b64decode(text.encode()).decode("utf-8", errors="replace")
    except Exception as e:
        return f"Decode error: {e}"


def sort_lines(text: str, reverse: bool = False, unique: bool = False, numeric: bool = False) -> str:
    lines = text.strip().split("\n")
    if numeric:
        try:
            lines.sort(key=lambda x: float(x.split()[0]) if x.strip() else 0, reverse=reverse)
        except ValueError:
            lines.sort(reverse=reverse)
    else:
        lines.sort(reverse=reverse)
    if unique:
        seen = set()
        lines = [l for l in lines if not (l in seen or seen.add(l))]
    return "\n".join(lines)


def replace_in_file(file: str, pattern: str, replacement: str,
                    regex: bool = False, all_occurrences: bool = True) -> str:
    file = os.path.expanduser(file)
    try:
        with open(file, "r") as f:
            content = f.read()
    except Exception as e:
        return f"Read error: {e}"

    if regex:
        count = len(re.findall(pattern, content))
        new_content = re.sub(pattern, replacement, content)
    else:
        count = content.count(pattern)
        if all_occurrences:
            new_content = content.replace(pattern, replacement)
        else:
            new_content = content.replace(pattern, replacement, 1)

    try:
        with open(file, "w") as f:
            f.write(new_content)
        return f"Replaced {count} occurrence(s) in {file}"
    except Exception as e:
        return f"Write error: {e}"


def count_occurrences(pattern: str, text: str = "", file: str = "") -> str:
    if file:
        file = os.path.expanduser(file)
        return run_shell(f"grep -c '{pattern}' '{file}' 2>/dev/null || echo 0")
    count = len(re.findall(pattern, text))
    return f"Found {count} occurrence(s) of '{pattern}'"


def json_query(file: str, query: str = ".") -> str:
    file = os.path.expanduser(file)
    import shutil
    if shutil.which("jq"):
        return run_shell(f"jq '{query}' '{file}' 2>&1 | head -50")
    # Python fallback
    try:
        import json
        with open(file) as f:
            data = json.load(f)
        return str(data)[:2000]
    except Exception as e:
        return f"JSON error: {e}"


def head_file(file: str, lines: int = 20) -> str:
    file = os.path.expanduser(file)
    return run_shell(f"head -n {lines} '{file}'")


def tail_file(file: str, lines: int = 20) -> str:
    file = os.path.expanduser(file)
    return run_shell(f"tail -n {lines} '{file}'")


def column_cut(file: str, delimiter: str = "\t", fields: str = "1") -> str:
    file = os.path.expanduser(file)
    return run_shell(f"cut -d'{delimiter}' -f{fields} '{file}' | head -30")


def register_text_tools(registry: ToolRegistry):
    registry.register("grep_in_file", grep_in_file, "Search for a pattern in a file",
        {
            "pattern": {"type": "string", "description": "Search pattern (regex supported)", "required": True},
            "file": {"type": "string", "description": "File path to search", "required": True},
            "ignore_case": {"type": "boolean", "description": "Case-insensitive search"},
            "line_numbers": {"type": "boolean", "description": "Show line numbers (default true)"},
            "context": {"type": "integer", "description": "Lines of context around matches"},
        })
    registry.register("grep_in_dir", grep_in_dir, "Recursively grep for a pattern in a directory",
        {
            "pattern": {"type": "string", "description": "Search pattern", "required": True},
            "directory": {"type": "string", "description": "Directory to search (default: .)"},
            "file_pattern": {"type": "string", "description": "File glob filter e.g. *.py"},
            "ignore_case": {"type": "boolean", "description": "Case-insensitive"},
            "recursive": {"type": "boolean", "description": "Search recursively (default true)"},
        })
    registry.register("word_count", word_count, "Count words, lines, and characters in a file",
        {"file": {"type": "string", "description": "File path", "required": True}})
    registry.register("file_diff", file_diff, "Show differences between two files",
        {
            "file1": {"type": "string", "description": "First file", "required": True},
            "file2": {"type": "string", "description": "Second file", "required": True},
            "unified": {"type": "boolean", "description": "Unified diff format (default true)"},
        })
    registry.register("hash_file", hash_file, "Compute checksum hash of a file",
        {
            "file": {"type": "string", "description": "File path", "required": True},
            "algorithm": {"type": "string", "description": "Algorithm: md5, sha1, sha256, sha512 (default: sha256)"},
        })
    registry.register("hash_text", hash_text, "Compute hash of a text string",
        {
            "text": {"type": "string", "description": "Text to hash", "required": True},
            "algorithm": {"type": "string", "description": "Algorithm: md5, sha1, sha256 (default: sha256)"},
        })
    registry.register("base64_encode", base64_encode, "Base64 encode a string",
        {"text": {"type": "string", "description": "Text to encode", "required": True}})
    registry.register("base64_decode", base64_decode, "Base64 decode a string",
        {"text": {"type": "string", "description": "Base64 string to decode", "required": True}})
    registry.register("sort_lines", sort_lines, "Sort lines of text",
        {
            "text": {"type": "string", "description": "Multiline text to sort", "required": True},
            "reverse": {"type": "boolean", "description": "Reverse sort"},
            "unique": {"type": "boolean", "description": "Remove duplicates"},
            "numeric": {"type": "boolean", "description": "Numeric sort"},
        })
    registry.register("replace_in_file", replace_in_file, "Find and replace text in a file",
        {
            "file": {"type": "string", "description": "File path", "required": True},
            "pattern": {"type": "string", "description": "Text/pattern to find", "required": True},
            "replacement": {"type": "string", "description": "Replacement text", "required": True},
            "regex": {"type": "boolean", "description": "Treat pattern as regex"},
            "all_occurrences": {"type": "boolean", "description": "Replace all (default true)"},
        })
    registry.register("count_occurrences", count_occurrences, "Count occurrences of a pattern",
        {
            "pattern": {"type": "string", "description": "Pattern to count", "required": True},
            "text": {"type": "string", "description": "Text to search in"},
            "file": {"type": "string", "description": "File to search in"},
        })
    registry.register("json_query", json_query, "Query a JSON file with jq syntax",
        {
            "file": {"type": "string", "description": "JSON file path", "required": True},
            "query": {"type": "string", "description": "jq query (default: . = pretty print all)"},
        })
    registry.register("head_file", head_file, "Show first N lines of a file",
        {
            "file": {"type": "string", "description": "File path", "required": True},
            "lines": {"type": "integer", "description": "Number of lines (default 20)"},
        })
    registry.register("tail_file", tail_file, "Show last N lines of a file",
        {
            "file": {"type": "string", "description": "File path", "required": True},
            "lines": {"type": "integer", "description": "Number of lines (default 20)"},
        })
    registry.register("column_cut", column_cut, "Extract columns from a delimited file",
        {
            "file": {"type": "string", "description": "File path", "required": True},
            "delimiter": {"type": "string", "description": "Field delimiter (default: tab)"},
            "fields": {"type": "string", "description": "Field numbers e.g. 1,2,4 (default: 1)"},
        })
