"""Basic smoke tests — no external deps required."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest


def test_config_loads():
    from core.config import ASSISTANT_NAME, SYSTEM_PROMPT
    assert ASSISTANT_NAME == "cogman"
    assert "cogman" in SYSTEM_PROMPT.lower()


def test_safety_blocks_dangerous():
    from core.safety import check_command
    ok, reason = check_command("rm -rf /")
    assert not ok
    assert "Blocked" in reason


def test_safety_allows_safe():
    from core.safety import check_command
    ok, reason = check_command("ls -la ~")
    assert ok


def test_safety_warns_risky():
    from core.safety import check_command
    ok, reason = check_command("sudo apt update")
    assert ok  # allowed but warns
    assert "warn:" in reason


def test_tool_registry():
    from core.tool_registry import ToolRegistry
    reg = ToolRegistry()
    reg.register("hello", lambda name="world": f"Hello, {name}!", "Say hello",
                 {"name": {"type": "string", "description": "Who to greet"}})
    assert "hello" in reg.list_names()
    result = reg.run("hello", {"name": "cogman"})
    assert result == "Hello, cogman!"


def test_tool_registry_unknown():
    from core.tool_registry import ToolRegistry
    reg = ToolRegistry()
    result = reg.run("nonexistent", {})
    assert "Unknown tool" in result


def test_intent_parser_time():
    from core.intent_parser import parse_fast
    intent = parse_fast("what's the time")
    assert intent is not None
    assert intent.tool == "get_time"


def test_intent_parser_open():
    from core.intent_parser import parse_fast
    intent = parse_fast("open firefox please")
    assert intent is not None
    assert intent.tool == "open_app"
    assert intent.args["app"] == "firefox"


def test_intent_parser_shell():
    from core.intent_parser import parse_fast
    intent = parse_fast("run ls -la")
    assert intent is not None
    assert intent.tool == "run_shell"
    assert "ls" in intent.args["command"]


def test_intent_parser_no_match():
    from core.intent_parser import parse_fast
    intent = parse_fast("translate this text to french")
    assert intent is None  # falls through to LLM


def test_memory_short_term():
    from core.memory import ShortTermMemory
    m = ShortTermMemory(max_size=3)
    m.add("user", "hello")
    m.add("assistant", "hi there")
    m.add("user", "how are you")
    m.add("assistant", "great")  # pushes out first
    msgs = m.get()
    assert len(msgs) == 3
    assert msgs[0]["content"] == "hi there"


def test_memory_long_term(tmp_path):
    from core.memory import LongTermMemory
    mem = LongTermMemory(db_path=str(tmp_path / "test.db"))
    mem.save("cogman is a Linux AI assistant", category="facts")
    mem.set_preference("browser", "firefox")
    assert mem.get_preference("browser") == "firefox"
    results = mem.recent(5)
    assert len(results) == 1


def test_schema_generation():
    from core.tool_registry import ToolRegistry
    reg = ToolRegistry()
    reg.register(
        "add",
        lambda a, b: a + b,
        "Add two numbers",
        {
            "a": {"type": "integer", "description": "First number", "required": True},
            "b": {"type": "integer", "description": "Second number", "required": True},
        },
    )
    schemas = reg.all_schemas()
    assert len(schemas) == 1
    s = schemas[0]
    assert s["name"] == "add"
    assert "a" in s["input_schema"]["properties"]
    assert "a" in s["input_schema"]["required"]
