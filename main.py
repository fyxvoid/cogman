#!/usr/bin/env python3
"""
cogman — Self-learning, self-evolving Linux AI Assistant

Modes:
  python main.py              → interactive CLI
  python main.py --voice      → voice mode (wake word: "Hey cogman")
  python main.py --gateway    → multi-channel (Telegram/Discord/Slack/Webhook)
  python main.py --api        → REST API server
  python main.py -c "cmd"     → single command, exit
  python main.py --setup      → download offline speech models
  python main.py --status     → full system status

LLM Providers (set any env var to enable):
  ANTHROPIC_API_KEY   OPENAI_API_KEY   GROQ_API_KEY   GEMINI_API_KEY
  COGMAN_LOCAL_LLM=true + ollama → fully offline
"""
import os
import sys
import argparse
import logging
import signal

sys.path.insert(0, os.path.dirname(__file__))

# ── Imports ───────────────────────────────────────────────────────────────────
from core.config import (
    ASSISTANT_NAME, VOICE_ENABLED, API_HOST, API_PORT, LOG_DIR,
    ENABLE_PROJECT_PLUGINS, SKILLS_DIR,
)
from memory.manager import Memory
from core.tool_registry import ToolRegistry
from core.orchestrator import Orchestrator
from core.command_registry import CommandDispatcher
from core.plugin_engine import PluginEngine
from skills.registry import SkillRegistry
from core.session import SessionManager
from learning.learner import PostInteractionLearner
from learning.evolver import SkillEvolver

# Tools
from tools.system_tools import register_system_tools
from tools.file_tools import register_file_tools
from tools.web_tools import register_web_tools
from tools.memory_tools import register_memory_tools
from tools.process_tools import register_process_tools
from tools.network_tools import register_network_tools
from tools.package_tools import register_package_tools
from tools.service_tools import register_service_tools
from tools.git_tools import register_git_tools
from tools.power_tools import register_power_tools
from tools.window_tools import register_window_tools
from tools.archive_tools import register_archive_tools
from tools.text_tools import register_text_tools
from tools.docker_tools import register_docker_tools
from tools.system_info_tools import register_system_info_tools
from tools.misc_tools import register_misc_tools
from tools.browser_tools import register_browser_tools
from tools.code_tools import register_code_tools
from tools.image_tools import register_image_tools
from tools.build_tools import register_build_tools
from tools.native_pkg_tools import register_native_pkg_tools
from tools.monitor_tools import register_monitor_tools


def setup_logging(debug: bool = False):
    level = logging.DEBUG if debug else logging.WARNING
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        handlers=[
            logging.FileHandler(str(LOG_DIR / "cogman.log")),
        ] + ([logging.StreamHandler(sys.stderr)] if debug else []),
    )


def build_agent():
    """Construct the full cogman agent stack."""
    memory   = Memory()
    registry = ToolRegistry()

    # Register all tools
    register_system_tools(registry)
    register_file_tools(registry)
    register_web_tools(registry)
    register_memory_tools(registry, memory)
    register_process_tools(registry)
    register_network_tools(registry)
    register_package_tools(registry)
    register_service_tools(registry)
    register_git_tools(registry)
    register_power_tools(registry)
    register_window_tools(registry)
    register_archive_tools(registry)
    register_text_tools(registry)
    register_docker_tools(registry)
    register_system_info_tools(registry)
    register_misc_tools(registry)
    register_browser_tools(registry)
    register_code_tools(registry)
    register_image_tools(registry)
    register_build_tools(registry)
    register_native_pkg_tools(registry)

    # Core orchestrator (7-stage pipeline + cognitive loop + env context)
    orchestrator = Orchestrator(registry, memory)

    # Plugin engine (loads from ~/.cogman/plugins/)
    plugin_engine = PluginEngine(registry, allow_project_plugins=ENABLE_PROJECT_PLUGINS)
    plugin_engine.load_all()

    # Skill registry (builtin/ + ~/.cogman/skills/)
    skill_registry = SkillRegistry(SKILLS_DIR)
    skill_registry.load_all(registry)

    # Session manager with FTS5 search + branching + rollback
    session_mgr = SessionManager()

    # Self-learning: extracts facts/preferences after each interaction
    learner = PostInteractionLearner(memory, orchestrator._providers)

    # Self-evolving: auto-creates skills from repeated task patterns
    evolver = SkillEvolver(memory, skill_registry, orchestrator._providers)

    # Slash command dispatcher
    dispatcher = CommandDispatcher(
        orchestrator, memory, registry,
        session_mgr=session_mgr,
        plugin_engine=plugin_engine,
        skill_registry=skill_registry,
    )

    # Wire everything into orchestrator
    orchestrator.plugin_engine  = plugin_engine
    orchestrator.skill_registry = skill_registry
    orchestrator.session_mgr    = session_mgr
    orchestrator.dispatcher     = dispatcher
    orchestrator.learner        = learner
    orchestrator.evolver        = evolver

    # ── System monitor (proactive background watcher) ─────────────────────────
    from core.config import MONITOR_ENABLED
    if MONITOR_ENABLED:
        from core.monitor import SystemMonitor, Thresholds
        from tools.monitor_tools import set_monitor_instance

        def _speak_alert(text):
            try:
                from speech.tts import speak_async
                speak_async(text)
            except Exception:
                pass

        def _notify_alert(title, message):
            try:
                from tools.misc_tools import notify
                notify(title, message)
            except Exception:
                pass

        monitor = SystemMonitor(
            speak_fn=_speak_alert,
            notify_fn=_notify_alert,
        )
        monitor.start()
        set_monitor_instance(monitor)
        register_monitor_tools(registry, monitor)

    return orchestrator, memory, registry, plugin_engine, skill_registry, session_mgr


# ── Banner ────────────────────────────────────────────────────────────────────

BANNER = r"""
  ██████╗ ██████╗  ██████╗ ███╗   ███╗ █████╗ ███╗   ██╗
 ██╔════╝██╔═══██╗██╔════╝ ████╗ ████║██╔══██╗████╗  ██║
 ██║     ██║   ██║██║  ███╗██╔████╔██║███████║██╔██╗ ██║
 ██║     ██║   ██║██║   ██║██║╚██╔╝██║██╔══██║██║╚██╗██║
 ╚██████╗╚██████╔╝╚██████╔╝██║ ╚═╝ ██║██║  ██║██║ ╚████║
  ╚═════╝ ╚═════╝  ╚═════╝ ╚═╝     ╚═╝╚═╝  ╚═╝╚═╝  ╚═══╝
        Self-learning Linux AI Assistant
"""


# ── Rich helpers ──────────────────────────────────────────────────────────────

def _try_rich():
    try:
        from rich.console import Console
        from rich.markdown import Markdown
        from rich.panel import Panel
        return Console(), Markdown, Panel
    except ImportError:
        return None, None, None


def _print_response(text: str, console=None, Markdown=None, Panel=None):
    if console and Markdown and Panel:
        try:
            console.print(Panel(Markdown(text), border_style="dim cyan", padding=(0, 1)))
            return
        except Exception:
            pass
    print(f"\ncogman > {text}\n")


def _make_event_handler(console=None):
    """Returns an event listener that shows streaming output and tool calls."""
    from agents.events import ToolExecutionStartEvent, ToolExecutionEndEvent, MessageUpdateEvent

    def handler(event):
        if isinstance(event, MessageUpdateEvent) and event.delta:
            print(event.delta, end="", flush=True)
        elif isinstance(event, ToolExecutionStartEvent):
            args_str = str(event.args)[:60] if event.args else ""
            if console:
                console.print(f"  [dim cyan]→ {event.tool_name}({args_str})[/]", end="")
            else:
                print(f"\n  → {event.tool_name}({args_str})", end="", flush=True)
        elif isinstance(event, ToolExecutionEndEvent):
            status = "✓" if not event.is_error else "✗"
            if console:
                console.print(f" [{status}]")
            else:
                print(f" [{status}]", flush=True)

    return handler


# ── CLI mode ──────────────────────────────────────────────────────────────────

def run_cli(orchestrator, memory, registry, plugin_engine, skill_registry, session_mgr):
    console, Markdown, Panel = _try_rich()

    if console:
        console.print(BANNER, style="bold cyan")
    else:
        print(BANNER)

    n_tools   = len(registry.list_names())
    n_plugins = len(plugin_engine.loaded_names)
    n_skills  = len(skill_registry.list())
    providers = orchestrator._providers.list_available()
    pstr = ", ".join(providers) if providers else "none — set API key or start Ollama"

    print(f"  Tools: {n_tools}  |  Plugins: {n_plugins}  |  Skills: {n_skills}")
    print(f"  Providers: {pstr}")
    print(f"  Session: {session_mgr.session_id}")
    print(f"  /help for commands | 'status' for full info\n")

    orchestrator.add_event_listener(_make_event_handler(console))
    signal.signal(signal.SIGINT, lambda s, f: (print("\n[cogman] Goodbye."), sys.exit(0)))

    while True:
        try:
            if console:
                from rich.prompt import Prompt
                user_input = Prompt.ask("[bold green]you[/bold green]")
            else:
                user_input = input("you > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n[cogman] Goodbye.")
            break

        if not user_input:
            continue

        cmd_lower = user_input.lower()
        if cmd_lower in ("quit", "exit", "bye", "goodbye"):
            print("[cogman] Goodbye.")
            break
        elif cmd_lower == "help":
            from core.command_registry import cli_help_text
            print(cli_help_text())
            continue
        elif cmd_lower == "tools":
            print(f"\n{registry.summary()}\n")
            continue
        elif cmd_lower == "status":
            print(orchestrator.print_status())
            continue
        elif cmd_lower == "clear":
            memory.short.clear()
            os.system("clear")
            continue

        # Auto-title first message
        if session_mgr.current and len(memory.short.get()) <= 1:
            title = session_mgr.auto_title(user_input)
            session_mgr.current.title = title
            session_mgr._save_session(session_mgr.current)

        response = orchestrator.process(user_input)

        if response:
            print()  # newline after streaming
            _print_response(response, console, Markdown, Panel)


# ── Voice mode ────────────────────────────────────────────────────────────────

def run_voice(orchestrator):
    from speech.tts import speak, get_tts_backend
    from speech.stt import get_stt_backend
    from speech.listener import start_listening

    print(BANNER)
    print(f"  Voice | TTS={get_tts_backend()} | STT={get_stt_backend()}")
    print("  Say 'Hey cogman' | Ctrl+C to stop\n")

    def handle(text: str) -> str:
        text = text.strip()
        if not text:
            return "I didn't catch that."
        if text.lower() in ("quit", "exit", "goodbye", "stop"):
            speak("Goodbye!")
            sys.exit(0)
        return orchestrator.process(text)

    try:
        start_listening(handle)
    except KeyboardInterrupt:
        from speech.listener import stop_listening
        stop_listening()
        print("\n[cogman] Voice stopped.")


# ── Gateway mode ──────────────────────────────────────────────────────────────

def run_gateway(orchestrator, memory, session_mgr, plugin_engine):
    from core.gateway import GatewayRunner
    print(BANNER)
    GatewayRunner(orchestrator, memory, session_mgr, plugin_engine).start()


# ── API mode ──────────────────────────────────────────────────────────────────

def run_api(orchestrator, memory):
    try:
        import uvicorn
        from api.server import app, init as api_init
    except ImportError:
        print("[cogman] Install: pip install fastapi uvicorn")
        sys.exit(1)
    api_init(orchestrator, memory)
    print(f"[cogman] API: http://{API_HOST}:{API_PORT}")
    uvicorn.run(app, host=API_HOST, port=API_PORT, log_level="warning")


# ── Setup mode ────────────────────────────────────────────────────────────────

def run_setup():
    print("[cogman] Setup — downloading offline speech models\n")
    print("[1/2] Vosk STT model (~50MB)...")
    try:
        from speech.stt import download_vosk_model
        print(f"  {download_vosk_model('small')}")
    except Exception as e:
        print(f"  Error: {e}\n  Manual: pip install vosk sounddevice")
    print("\n[2/2] TTS check...")
    try:
        from speech.tts import get_tts_backend
        print(f"  TTS: {get_tts_backend()}")
    except Exception as e:
        print(f"  Error: {e}")
    print("\n[cogman] Setup complete.")


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(prog="cogman", description="cogman — Self-learning Linux AI")
    parser.add_argument("--voice",   action="store_true", help="Wake-word voice mode")
    parser.add_argument("--gateway", action="store_true", help="Multi-channel gateway")
    parser.add_argument("--api",     action="store_true", help="REST API server")
    parser.add_argument("--setup",   action="store_true", help="Download speech models")
    parser.add_argument("--status",  action="store_true", help="Show system status")
    parser.add_argument("-c", "--command", type=str, help="Run one command and exit")
    parser.add_argument("--debug",   action="store_true", help="Verbose logging")
    args = parser.parse_args()

    setup_logging(args.debug)

    if args.setup:
        run_setup()
        return

    orchestrator, memory, registry, plugin_engine, skill_registry, session_mgr = build_agent()

    if args.status:
        print(orchestrator.print_status())
        return

    if args.command:
        orchestrator.add_event_listener(_make_event_handler())
        response = orchestrator.process(args.command)
        if response:
            print(response)
        return

    if args.voice:
        run_voice(orchestrator)
    elif args.gateway:
        run_gateway(orchestrator, memory, session_mgr, plugin_engine)
    elif args.api:
        run_api(orchestrator, memory)
    else:
        run_cli(orchestrator, memory, registry, plugin_engine, skill_registry, session_mgr)


if __name__ == "__main__":
    main()
