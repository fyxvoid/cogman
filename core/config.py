import os
from pathlib import Path

BASE_DIR  = Path(__file__).parent.parent
DATA_DIR  = BASE_DIR / "data"
LOG_DIR   = BASE_DIR / "logs"
MEMORY_DIR = DATA_DIR / "memory"
CHROMA_DIR = DATA_DIR / "chroma"

for _d in (LOG_DIR, MEMORY_DIR, CHROMA_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# ── Cloud LLM — Tier 3 providers (Pi Agent Core handles all of these) ─────────
ANTHROPIC_API_KEY  = os.getenv("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY     = os.getenv("OPENAI_API_KEY", "")
GROQ_API_KEY       = os.getenv("GROQ_API_KEY", "")
GEMINI_API_KEY     = os.getenv("GEMINI_API_KEY", "")

# ── Model selection (per provider) ────────────────────────────────────────────
LLM_MODEL          = os.getenv("COGMAN_MODEL", "claude-sonnet-4-6")
LLM_MAX_TOKENS     = int(os.getenv("COGMAN_MAX_TOKENS", "4096"))
COGMAN_OPENAI_MODEL   = os.getenv("COGMAN_OPENAI_MODEL", "gpt-4o")
COGMAN_GROQ_MODEL     = os.getenv("COGMAN_GROQ_MODEL", "llama-3.3-70b-versatile")
COGMAN_GEMINI_MODEL   = os.getenv("COGMAN_GEMINI_MODEL", "gemini-2.0-flash")

# ── Custom OpenAI-compatible endpoint (LM Studio, vLLM, Together, Mistral…) ──
COGMAN_OPENAI_BASE_URL = os.getenv("COGMAN_OPENAI_BASE_URL", "")
COGMAN_OPENAI_API_KEY  = os.getenv("COGMAN_OPENAI_API_KEY", "sk-local")

# ── Local LLM via Ollama (offline) ───────────────────────────────────────────
ENABLE_LOCAL_LLM   = os.getenv("COGMAN_LOCAL_LLM", "true").lower() == "true"
OLLAMA_HOST        = os.getenv("COGMAN_OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL       = os.getenv("COGMAN_OLLAMA_MODEL", "mistral")

# ── Memory ───────────────────────────────────────────────────────────────────
MEMORY_DB_PATH     = str(MEMORY_DIR / "cogman.db")
CHROMA_PATH        = str(CHROMA_DIR)
MEMORY_COLLECTION  = "cogman_memory"
MAX_SHORT_TERM     = int(os.getenv("COGMAN_SHORT_TERM", "30"))   # messages in context
TOP_K_MEMORIES     = int(os.getenv("COGMAN_TOP_K", "5"))          # memories per query

# Context compression — auto-compress at this fraction of context window
CONTEXT_COMPRESS_THRESHOLD = float(os.getenv("COGMAN_COMPRESS_AT", "0.75"))

# ── Speech (offline-first) ───────────────────────────────────────────────────
WHISPER_MODEL      = os.getenv("COGMAN_WHISPER_MODEL", "base")
AUDIO_SAMPLE_RATE  = 16000
VOICE_ENABLED      = os.getenv("COGMAN_VOICE", "false").lower() == "true"
WAKE_WORDS         = ["hey cogman", "cogman", "okay cogman"]
TTS_RATE           = int(os.getenv("COGMAN_TTS_RATE", "160"))
TTS_VOLUME         = float(os.getenv("COGMAN_TTS_VOLUME", "0.9"))

# ── Gateway (OpenClaw-style multi-channel) ───────────────────────────────────
COGMAN_TELEGRAM_TOKEN    = os.getenv("COGMAN_TELEGRAM_TOKEN", "")
COGMAN_DISCORD_TOKEN     = os.getenv("COGMAN_DISCORD_TOKEN", "")
COGMAN_SLACK_BOT_TOKEN   = os.getenv("COGMAN_SLACK_BOT_TOKEN", "")
COGMAN_SLACK_APP_TOKEN   = os.getenv("COGMAN_SLACK_APP_TOKEN", "")
COGMAN_WEBHOOK_PORT      = int(os.getenv("COGMAN_WEBHOOK_PORT", "7778"))

# ── Web / Search ─────────────────────────────────────────────────────────────
BRAVE_API_KEY      = os.getenv("BRAVE_API_KEY", "")
COGMAN_SD_URL      = os.getenv("COGMAN_SD_URL", "")  # Stable Diffusion WebUI

# ── Plugins & Skills (Hermes-style) ──────────────────────────────────────────
COGMAN_HOME        = Path.home() / ".cogman"
PLUGINS_DIR        = COGMAN_HOME / "plugins"
SKILLS_DIR         = COGMAN_HOME / "skills"
SESSIONS_DB        = COGMAN_HOME / "sessions.db"
ENABLE_PROJECT_PLUGINS = os.getenv("COGMAN_PROJECT_PLUGINS", "false").lower() == "true"

for _d in (COGMAN_HOME, PLUGINS_DIR, SKILLS_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# ── Safety ────────────────────────────────────────────────────────────────────
LOG_ALL_ACTIONS    = True

# ── REST API ─────────────────────────────────────────────────────────────────
API_HOST           = os.getenv("COGMAN_API_HOST", "127.0.0.1")
API_PORT           = int(os.getenv("COGMAN_API_PORT", "7777"))
API_ENABLED        = os.getenv("COGMAN_API", "false").lower() == "true"

# ── Assistant identity ────────────────────────────────────────────────────────
ASSISTANT_NAME = "cogman"

SYSTEM_PROMPT = f"""You are COGMAN, a top-notch personal AI assistant for Linux.

You are powerful, direct, and highly capable. You can:
- Control the Linux system (files, processes, services, packages, git, docker)
- Write and execute code (Python, bash, scripts)
- Search the web and fetch pages
- Generate images (DALL-E / Stable Diffusion)
- Manage memory and learn from conversations
- Create reusable skills from experience
- Work autonomously on complex multi-step tasks

You have access to {"{n_tools}"} tools. Use them proactively.

Rules:
1. Be direct and concise — no fluff
2. Use tools rather than explaining how to do something
3. Confirm before destructive operations (rm, shutdown, format)
4. Chain tools together for complex tasks
5. Create and save skills for recurring tasks
6. Remember user preferences and context across sessions
7. Never hallucinate — if you don't know, say so and search for it

When asked to do something complex, break it into steps and execute each one.
"""
