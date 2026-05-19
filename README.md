# COGMAN — Linux Personal AI Assistant

```
  ██████╗ ██████╗  ██████╗ ███╗   ███╗ █████╗ ███╗   ██╗
 ██╔════╝██╔═══██╗██╔════╝ ████╗ ████║██╔══██╗████╗  ██║
 ██║     ██║   ██║██║  ███╗██╔████╔██║███████║██╔██╗ ██║
 ██║     ██║   ██║██║   ██║██║╚██╔╝██║██╔══██║██║╚██╗██║
 ╚██████╗╚██████╔╝╚██████╔╝██║ ╚═╝ ██║██║  ██║██║ ╚████║
  ╚═════╝ ╚═════╝  ╚═════╝ ╚═╝     ╚═╝╚═╝  ╚═╝╚═╝  ╚═══╝
```

**COGMAN** is a self-learning, self-evolving AI assistant built exclusively for Linux. It runs as a systemd daemon, integrates deeply with your system, and gets smarter with every interaction.

---

## Features

- **Deep Linux integration** — controls processes, services, packages, files, git, docker, cron
- **Multi-provider LLM** — Anthropic Claude, OpenAI, Groq, Gemini, Ollama (fully offline)
- **Self-learning** — extracts facts and preferences from every conversation
- **Self-evolving** — auto-generates reusable skills from repeated task patterns
- **Voice interface** — offline STT (Vosk/Whisper) + TTS (pyttsx3/espeak), wake-word detection
- **Multi-channel gateway** — Telegram, Discord, Slack, IRC, Webhook
- **REST API** — FastAPI server for programmatic access
- **Systemd daemon** — runs as a background service with socket activation
- **7-stage pipeline** — normalize → route → assemble → plugin hook → infer → ReAct → persist
- **Plugin engine** — load external plugins from `~/.cogman/plugins/`
- **Skill registry** — composable, auto-discoverable skills in `~/.cogman/skills/`
- **Session management** — FTS5-indexed sessions with branching and rollback
- **Context compression** — automatically compresses long conversations

---

## Quick Start

```bash
# 1. Clone and install
git clone <repo> cogman && cd cogman
pip install -r requirements.txt

# 2. Set your LLM key (at least one)
export ANTHROPIC_API_KEY=sk-ant-...
# or
export OPENAI_API_KEY=sk-...
# or use Ollama (fully offline, no key needed)
curl -fsSL https://ollama.ai/install.sh | sh && ollama pull mistral

# 3. Run
python main.py              # interactive CLI
python main.py --voice      # voice mode
python main.py --gateway    # multi-channel (Telegram/Discord/Slack)
python main.py --api        # REST API
python main.py -c "cmd"     # one-shot command
python main.py --status     # full status
```

---

## Systemd Daemon

COGMAN is designed to run as a persistent Linux service.

```bash
# Install as a user service
bash daemon/install_daemon.sh

# Control the service
systemctl --user start cogman
systemctl --user stop cogman
systemctl --user status cogman
systemctl --user restart cogman

# View live logs
journalctl --user -u cogman -f

# Enable at login
systemctl --user enable cogman
loginctl enable-linger $USER   # persist after logout
```

The service reads credentials from `~/.config/cogman/env`:

```ini
ANTHROPIC_API_KEY=sk-ant-...
COGMAN_MODEL=claude-sonnet-4-6
COGMAN_API=true
COGMAN_API_PORT=7777
```

---

## Directory Layout

```
cogman/
├── main.py                 # entry point
├── core/
│   ├── orchestrator.py     # 7-stage processing pipeline
│   ├── gateway.py          # multi-channel gateway adapters
│   ├── config.py           # configuration + system prompt
│   ├── intent_parser.py    # Tier 1 regex intent routing
│   ├── local_nlp.py        # Tier 2 keyword/fuzzy NLP
│   ├── safety.py           # command safety + action logging
│   ├── plugin_engine.py    # plugin loader
│   ├── session.py          # session manager (FTS5)
│   └── command_registry.py # slash command registry
├── agents/
│   ├── loop.py             # cognitive agent loop (ReAct + tool use)
│   ├── providers.py        # multi-provider LLM abstraction
│   └── events.py           # event types for streaming
├── tools/                  # Linux system tools (70+)
│   ├── system_tools.py     # shell, env, systemd
│   ├── file_tools.py       # read/write/search/diff
│   ├── process_tools.py    # ps, kill, top
│   ├── service_tools.py    # systemctl, journalctl
│   ├── package_tools.py    # apt/pacman/dnf
│   ├── git_tools.py        # git operations
│   ├── docker_tools.py     # docker/podman
│   ├── network_tools.py    # ping, curl, nmap
│   ├── web_tools.py        # search, fetch
│   └── ...
├── memory/
│   ├── manager.py          # short-term + long-term memory
│   ├── context.py          # environment context injector
│   └── session.py          # conversation sessions
├── learning/
│   ├── learner.py          # post-interaction learning
│   └── evolver.py          # skill auto-generation
├── skills/
│   ├── registry.py         # skill loader + tool bridge
│   └── builtin/            # built-in skills (weather, remind, notes…)
├── speech/
│   ├── tts.py              # offline TTS (pyttsx3/espeak)
│   ├── stt.py              # offline STT (Vosk/Whisper)
│   ├── listener.py         # wake-word + mic capture
│   └── hotword.py          # hotword detection
├── api/
│   └── server.py           # FastAPI REST server
├── daemon/
│   ├── cogman.service      # systemd unit file
│   └── install_daemon.sh   # service installer
└── data/
    └── memory/             # SQLite memory database
```

---

## LLM Providers

| Provider | Env Var | Notes |
|----------|---------|-------|
| Anthropic Claude | `ANTHROPIC_API_KEY` | Best quality, priority 100 |
| Groq | `GROQ_API_KEY` | Fast inference, priority 90 |
| OpenAI | `OPENAI_API_KEY` | GPT-4o, priority 80 |
| Google Gemini | `GEMINI_API_KEY` | Gemini Flash, priority 70 |
| Any OpenAI-compat | `COGMAN_OPENAI_BASE_URL` | LM Studio, vLLM, etc., priority 60 |
| Ollama | auto-detected | Fully offline, priority 50 |

Set `COGMAN_MODEL` to override the model for any provider.

---

## Gateway Configuration

```bash
# Telegram
export COGMAN_TELEGRAM_TOKEN=your-bot-token

# Discord
export COGMAN_DISCORD_TOKEN=your-bot-token

# Slack
export COGMAN_SLACK_BOT_TOKEN=xoxb-...
export COGMAN_SLACK_APP_TOKEN=xapp-...

# Webhook (always available if fastapi+uvicorn installed)
# POST http://localhost:7778/chat  {"text": "your message"}

# Run all configured channels
python main.py --gateway
```

---

## Voice Mode

```bash
# Install offline speech models
python main.py --setup

# Run voice mode (say "Hey cogman" to activate)
python main.py --voice
```

Supported STT backends (in order of preference):
- **faster-whisper** — best accuracy, GPU-accelerated
- **Vosk** — lightweight, fully offline
- **SpeechRecognition** — uses system microphone

Supported TTS backends:
- **pyttsx3** — offline, system voices
- **espeak** — lightweight, highly customizable

---

## CLI Commands

| Command | Description |
|---------|-------------|
| `status` | Full system status |
| `tools` | List all available tools |
| `help` | Show help |
| `clear` | Clear screen + short-term memory |
| `/skills` | List loaded skills |
| `/plugins` | List loaded plugins |
| `/session new` | Start new session |
| `/session list` | List sessions |
| `/memory` | Show memory stats |
| `/learn` | Trigger learning cycle |
| `quit` / `exit` | Exit cogman |

---

## Plugin Development

Drop a Python file in `~/.cogman/plugins/`:

```python
# ~/.cogman/plugins/myplugin.py
PLUGIN_NAME = "myplugin"
PLUGIN_VERSION = "1.0"
PLUGIN_DESCRIPTION = "My custom plugin"

def register_tools(registry):
    def my_tool(action: str = "run") -> str:
        return f"Tool executed: {action}"
    registry.register("my_tool", my_tool, "My custom tool", {"action": "string"})

def pre_llm_call(user_input, memory, **kwargs):
    pass  # intercept before LLM

def post_llm_call(user_input, response, **kwargs):
    pass  # intercept after LLM
```

---

## Skill Development

Drop a Python file in `~/.cogman/skills/`:

```python
# ~/.cogman/skills/greet.py
# skill: greet
# description: Greet a user by name
# tags: social, utility

def run(name: str = "world") -> str:
    return f"Hello, {name}! I am COGMAN, your Linux AI assistant."
```

Or let COGMAN generate skills automatically — when it detects a repeated pattern, it evolves a new skill and saves it.

---

## REST API

```bash
python main.py --api
# Starts on http://127.0.0.1:7777

# Example
curl -X POST http://localhost:7777/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "what processes are using the most CPU?"}'
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `COGMAN_MODEL` | `claude-sonnet-4-6` | LLM model |
| `COGMAN_MAX_TOKENS` | `4096` | Max response tokens |
| `COGMAN_LOCAL_LLM` | `true` | Enable Ollama fallback |
| `COGMAN_OLLAMA_HOST` | `http://localhost:11434` | Ollama endpoint |
| `COGMAN_OLLAMA_MODEL` | `mistral` | Ollama model |
| `COGMAN_SHORT_TERM` | `30` | Short-term memory size |
| `COGMAN_TOP_K` | `5` | Memory recall count |
| `COGMAN_VOICE` | `false` | Enable voice mode |
| `COGMAN_API_HOST` | `127.0.0.1` | API bind address |
| `COGMAN_API_PORT` | `7777` | API port |
| `COGMAN_WEBHOOK_PORT` | `7778` | Webhook gateway port |
| `COGMAN_PROJECT_PLUGINS` | `false` | Load project-local plugins |
| `BRAVE_API_KEY` | — | Brave Search API key |

---

## Requirements

- **Python 3.10+**
- **Linux** (Debian/Ubuntu/Arch/Fedora/any distro)
- At least one LLM provider key **or** Ollama running locally

```bash
# Minimal install
pip install psutil rapidfuzz anthropic rich pyyaml

# Full install (all features)
pip install anthropic openai pyyaml rich trafilatura beautifulsoup4 \
            Pillow ruff pyttsx3 vosk sounddevice fastapi uvicorn \
            python-telegram-bot discord.py slack-bolt
```

---

## License

MIT
