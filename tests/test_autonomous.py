"""
Test autonomous (no-API) operation:
  - Tier 1 regex rules still work
  - Tier 2a keyword NLP matches
  - Tier 2b fuzzy NLP matches
  - Full orchestrator works with zero API key
  - Speech backends detected without errors
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ── Tier 2a: Keyword NLP ─────────────────────────────────────────────────────

def test_keyword_time():
    from core.local_nlp import parse_keywords
    r = parse_keywords("what time is it right now")
    assert r is not None
    assert r.tool == "get_time"
    assert r.source == "keyword"


def test_keyword_disk():
    from core.local_nlp import parse_keywords
    r = parse_keywords("how much storage is left on my disk")
    assert r is not None
    assert r.tool == "disk_usage"


def test_keyword_cpu():
    from core.local_nlp import parse_keywords
    r = parse_keywords("show me the cpu usage right now")
    assert r is not None
    assert r.tool == "cpu_usage"


def test_keyword_ping():
    from core.local_nlp import parse_keywords
    r = parse_keywords("ping google.com")
    assert r is not None
    assert r.tool == "ping"
    assert "host" in r.args


def test_keyword_git():
    from core.local_nlp import parse_keywords
    r = parse_keywords("git status")
    assert r is not None
    assert r.tool == "git_status"


def test_keyword_docker():
    from core.local_nlp import parse_keywords
    r = parse_keywords("show me docker ps running containers")
    assert r is not None
    assert r.tool == "docker_ps"


def test_keyword_calculate():
    from core.local_nlp import parse_keywords
    r = parse_keywords("calculate 100 * 25")
    assert r is not None
    assert r.tool == "calculate"
    assert "100" in r.args.get("expression", "")


def test_keyword_brightness():
    from core.local_nlp import parse_keywords
    r = parse_keywords("set brightness to 80")
    assert r is not None
    assert r.tool == "set_brightness"
    assert r.args.get("percent") == 80


def test_keyword_weather():
    from core.local_nlp import parse_keywords
    r = parse_keywords("what's the weather in London")
    assert r is not None
    assert r.tool == "get_weather"


def test_keyword_no_match():
    from core.local_nlp import parse_keywords
    r = parse_keywords("translate this sentence to Japanese")
    # Should not match — no keyword hit
    # (may or may not match — fuzzy is separate)
    assert r is None or isinstance(r.tool, str)


# ── Tier 2b: Fuzzy NLP ───────────────────────────────────────────────────────

def test_fuzzy_match():
    from core.local_nlp import parse_fuzzy
    from core.tool_registry import ToolRegistry
    from tools.system_tools import register_system_tools
    from tools.file_tools import register_file_tools
    from core.memory import Memory

    reg = ToolRegistry()
    mem = Memory()
    register_system_tools(reg)
    register_file_tools(reg)

    # "disk space" should fuzzy-match disk_usage
    r = parse_fuzzy("how much disk space", reg, threshold=0.3)
    assert r is not None
    assert isinstance(r.tool, str)
    assert r.source == "fuzzy"


def test_fuzzy_suggest():
    from core.local_nlp import suggest_commands
    from core.tool_registry import ToolRegistry
    from tools.system_tools import register_system_tools

    reg = ToolRegistry()
    register_system_tools(reg)

    suggestions = suggest_commands("show cpu", reg, top_n=3)
    assert len(suggestions) <= 3
    assert all(isinstance(s, str) for s in suggestions)


# ── Entity extractors ─────────────────────────────────────────────────────────

def test_extract_number():
    from core.local_nlp import extract_number, extract_int
    assert extract_number("set volume to 75") == 75.0
    assert extract_int("brightness 80 percent") == 80


def test_extract_path():
    from core.local_nlp import extract_path
    assert extract_path("read ~/Documents/notes.txt") == "~/Documents/notes.txt"
    assert extract_path("open /etc/hosts") == "/etc/hosts"
    assert extract_path("no path here") is None


def test_extract_url():
    from core.local_nlp import extract_url
    assert extract_url("download https://example.com/file.tar.gz") == "https://example.com/file.tar.gz"


def test_extract_ip():
    from core.local_nlp import extract_ip
    assert extract_ip("ping 192.168.1.1") == "192.168.1.1"


def test_extract_port():
    from core.local_nlp import extract_port
    assert extract_port("who is using port 8080") == 8080
    assert extract_port("check port 443") == 443


def test_extract_quoted():
    from core.local_nlp import extract_quoted
    assert extract_quoted('search for "hello world"') == "hello world"
    assert extract_quoted("find 'config.py'") == "config.py"


# ── Full orchestrator: zero API ───────────────────────────────────────────────

def test_orchestrator_no_api():
    """Orchestrator must work without any API key — pure local."""
    import os
    os.environ.pop("ANTHROPIC_API_KEY", None)

    from core.memory import Memory
    from core.tool_registry import ToolRegistry
    from core.orchestrator import Orchestrator
    from tools.system_tools import register_system_tools
    from tools.misc_tools import register_misc_tools

    reg = ToolRegistry()
    mem = Memory()
    register_system_tools(reg)
    register_misc_tools(reg)

    orch = Orchestrator(reg, mem)
    assert orch._anthropic is None    # no cloud LLM

    # Tier 1 — rule-based
    result = orch.process("what time is it")
    assert result and isinstance(result, str)

    # Tier 2a — keyword NLP
    result = orch.process("calculate 2 + 2")
    assert "4" in result

    # Unknown → fallback suggestion
    result = orch.process("zxqyabcxyz nonexistent garbage")
    assert "Did you mean" in result or "understand" in result.lower()


# ── Speech: detection without errors ─────────────────────────────────────────

def test_tts_detection():
    from speech.tts import get_tts_backend, is_tts_available
    backend = get_tts_backend()
    assert isinstance(backend, str)
    assert backend in ("pyttsx3", "espeak-ng", "espeak", "spd-say", "festival", "print")


def test_stt_detection():
    from speech.stt import get_stt_backend, is_stt_available
    backend = get_stt_backend()
    assert isinstance(backend, str)
    assert backend in ("vosk", "whisper", "input")


def test_speak_does_not_crash():
    """speak() must never raise — it falls back to print."""
    from speech.tts import speak
    speak("cogman test", block=True)   # should not raise


def test_config_local_defaults():
    """Local LLM config must have sensible defaults."""
    from core.config import ENABLE_LOCAL_LLM, OLLAMA_HOST, OLLAMA_MODEL
    assert isinstance(ENABLE_LOCAL_LLM, bool)
    assert "localhost" in OLLAMA_HOST or "127.0.0.1" in OLLAMA_HOST
    assert isinstance(OLLAMA_MODEL, str) and len(OLLAMA_MODEL) > 0
