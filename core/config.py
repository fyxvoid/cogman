import os
from pathlib import Path

BASE_DIR  = Path(__file__).parent.parent
DATA_DIR  = BASE_DIR / "data"
LOG_DIR   = BASE_DIR / "logs"
MEMORY_DIR = DATA_DIR / "memory"
CHROMA_DIR = DATA_DIR / "chroma"

for _d in (LOG_DIR, MEMORY_DIR, CHROMA_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# ── Cloud LLM — Tier 3 providers ─────────────────────────────────────────────
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

# ── Gateway (multi-channel messaging) ────────────────────────────────────────
COGMAN_TELEGRAM_TOKEN    = os.getenv("COGMAN_TELEGRAM_TOKEN", "")
COGMAN_DISCORD_TOKEN     = os.getenv("COGMAN_DISCORD_TOKEN", "")
COGMAN_SLACK_BOT_TOKEN   = os.getenv("COGMAN_SLACK_BOT_TOKEN", "")
COGMAN_SLACK_APP_TOKEN   = os.getenv("COGMAN_SLACK_APP_TOKEN", "")
COGMAN_WEBHOOK_PORT      = int(os.getenv("COGMAN_WEBHOOK_PORT", "7778"))
COGMAN_IRC_HOST          = os.getenv("COGMAN_IRC_HOST", "")
COGMAN_IRC_PORT          = int(os.getenv("COGMAN_IRC_PORT", "6667"))
COGMAN_IRC_NICK          = os.getenv("COGMAN_IRC_NICK", "cogman")
COGMAN_IRC_CHANNEL       = os.getenv("COGMAN_IRC_CHANNEL", "#cogman")

# ── Web / Search ─────────────────────────────────────────────────────────────
BRAVE_API_KEY      = os.getenv("BRAVE_API_KEY", "")
COGMAN_SD_URL      = os.getenv("COGMAN_SD_URL", "")  # Stable Diffusion WebUI

# ── Plugins & Skills ─────────────────────────────────────────────────────────
COGMAN_HOME        = Path.home() / ".cogman"
PLUGINS_DIR        = COGMAN_HOME / "plugins"
SKILLS_DIR         = COGMAN_HOME / "skills"
SESSIONS_DB        = COGMAN_HOME / "sessions.db"
ENABLE_PROJECT_PLUGINS = os.getenv("COGMAN_PROJECT_PLUGINS", "false").lower() == "true"

for _d in (COGMAN_HOME, PLUGINS_DIR, SKILLS_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# ── Safety ────────────────────────────────────────────────────────────────────
LOG_ALL_ACTIONS    = True

# ── Monitor ───────────────────────────────────────────────────────────────────
MONITOR_ENABLED        = os.getenv("COGMAN_MONITOR", "true").lower() == "true"
MONITOR_CPU_THRESHOLD  = float(os.getenv("COGMAN_MON_CPU",  "85"))
MONITOR_RAM_THRESHOLD  = float(os.getenv("COGMAN_MON_RAM",  "88"))
MONITOR_DISK_THRESHOLD = float(os.getenv("COGMAN_MON_DISK", "90"))
MONITOR_TEMP_THRESHOLD = float(os.getenv("COGMAN_MON_TEMP", "85"))
MONITOR_BAT_THRESHOLD  = float(os.getenv("COGMAN_MON_BAT",  "15"))
MONITOR_INTERVAL_S     = float(os.getenv("COGMAN_MON_INT",  "15"))
MONITOR_SERVICES       = [s for s in os.getenv("COGMAN_MON_SVCS", "").split(",") if s.strip()]

# ── Personality / Voice ───────────────────────────────────────────────────────
PIPER_MODEL_NAME   = os.getenv("COGMAN_PIPER_MODEL", "en_US-ryan-medium")
TTS_RATE           = int(os.getenv("COGMAN_TTS_RATE", "155"))
TTS_VOLUME         = float(os.getenv("COGMAN_TTS_VOLUME", "0.88"))

# ── REST API ─────────────────────────────────────────────────────────────────
API_HOST           = os.getenv("COGMAN_API_HOST", "127.0.0.1")
API_PORT           = int(os.getenv("COGMAN_API_PORT", "7777"))
API_ENABLED        = os.getenv("COGMAN_API", "false").lower() == "true"

# ── Assistant identity ────────────────────────────────────────────────────────
ASSISTANT_NAME = "cogman"

SYSTEM_PROMPT = """You are cogman — a self-learning local Linux AI assistant running directly on this machine.
You are not a cloud service. You live here.

Character:
- Calm, precise, technically competent. Dry wit when it fits.
- Direct sentences when acting. Concise explanations when asked.
- Never sycophantic. No "Great question!", no "Certainly!".
- You know Linux deeply. You prefer the right tool over the easy one.
- When you don't know — say so. Never hallucinate.

Capabilities (260+ tools):
- Linux control: files, processes, services, packages, git, docker, cron, network
- Code execution: Python, bash, Rust — run_python, run_script, check_syntax
- Web: fetch_page, web_search, get_weather, check_url
- Memory: save_memory, search_memory, set_preference, get_preference
- Voice: speak via TTS, listen via STT, always-on wake word
- Native package manager (rogue-linux): pkg_plan, pkg_validate, cogman_pkg_install
- Self-learning + skill evolution: learns from every interaction

Package manifests (packages/<category>/<name>/<name>.toml):
  [identity] name, version, category, source, depends
  [build]    system (autotools|cmake|make|rust|python|go), steps
  [installer] steps, verify.expected_files
  [policy]   filesystem.write=="/", network.outbound=false

Operating rules:
1. Use tools — don't explain what you could do, do it.
2. Confirm before destructive ops (rm, shutdown, kill).
3. Chain tools for multi-step tasks without asking permission between steps.
4. Prefer local tools over cloud calls.
5. Remember preferences across sessions via set_preference.
6. Check build_status before using pkg_plan.
"""
