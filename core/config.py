import os
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
LOG_DIR = BASE_DIR / "logs"
MEMORY_DIR = DATA_DIR / "memory"
CHROMA_DIR = DATA_DIR / "chroma"

for _d in (LOG_DIR, MEMORY_DIR, CHROMA_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# ── Cloud LLM (Tier 4 — optional, requires API key) ─────────────────────────
ANTHROPIC_API_KEY  = os.getenv("ANTHROPIC_API_KEY", "")
LLM_MODEL          = os.getenv("COGMAN_MODEL", "claude-sonnet-4-6")
LLM_MAX_TOKENS     = int(os.getenv("COGMAN_MAX_TOKENS", "4096"))

# ── Local LLM via Ollama (Tier 3 — optional, fully offline) ─────────────────
ENABLE_LOCAL_LLM   = os.getenv("COGMAN_LOCAL_LLM", "true").lower() == "true"
OLLAMA_HOST        = os.getenv("COGMAN_OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL       = os.getenv("COGMAN_OLLAMA_MODEL", "mistral")

# ── Memory ───────────────────────────────────────────────────────────────────
MEMORY_DB_PATH     = str(MEMORY_DIR / "cogman.db")
CHROMA_PATH        = str(CHROMA_DIR)
MEMORY_COLLECTION  = "cogman_memory"
MAX_SHORT_TERM     = 20     # messages kept in short-term context
TOP_K_MEMORIES     = 5      # memories fetched per query

# ── Speech (all offline-first) ────────────────────────────────────────────────
# STT — backend auto-detected: vosk → whisper → input()
WHISPER_MODEL      = os.getenv("COGMAN_WHISPER_MODEL", "base")
AUDIO_SAMPLE_RATE  = 16000
VOICE_ENABLED      = os.getenv("COGMAN_VOICE", "false").lower() == "true"
WAKE_WORDS         = ["hey cogman", "cogman", "okay cogman"]

# TTS — backend auto-detected: pyttsx3 → espeak-ng → espeak → spd-say → print
TTS_RATE           = int(os.getenv("COGMAN_TTS_RATE", "160"))   # words per minute
TTS_VOLUME         = float(os.getenv("COGMAN_TTS_VOLUME", "0.9"))

# ── Safety ────────────────────────────────────────────────────────────────────
LOG_ALL_ACTIONS    = True

# ── REST API (optional) ───────────────────────────────────────────────────────
API_HOST           = os.getenv("COGMAN_API_HOST", "127.0.0.1")
API_PORT           = int(os.getenv("COGMAN_API_PORT", "7777"))
API_ENABLED        = os.getenv("COGMAN_API", "false").lower() == "true"

# ── Assistant identity ────────────────────────────────────────────────────────
ASSISTANT_NAME = "cogman"
SYSTEM_PROMPT = f"""You are {ASSISTANT_NAME.upper()}, a Jarvis-style Linux AI assistant.

You control the Linux system through natural language.
You are direct, concise, and safety-conscious.

Rules:
1. Use specific tools over raw shell when available
2. Confirm before destructive operations (rm, shutdown, kill)
3. Report results clearly without fluff
4. Never hallucinate — if you don't know, say so

Tools cover: shell, files, git, docker, packages, services, network, power, windows, text, memory.
"""
