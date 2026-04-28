#!/usr/bin/env python3
"""
cogman — Jarvis-style Linux AI Assistant

Fully autonomous. No API key needed by default.

Modes:
  python main.py              → interactive CLI
  python main.py --voice      → Jarvis voice mode (wake word: "Hey cogman")
  python main.py --api        → REST API server
  python main.py -c "cmd"     → single command, print result, exit
  python main.py --setup      → download offline speech models
  python main.py --status     → show backend status (tiers active)

Tiers (no config needed for 1 & 2):
  Tier 1: Regex rules    — instant, always on
  Tier 2: Local NLP      — keyword + fuzzy, always on
  Tier 3: Local LLM      — set COGMAN_LOCAL_LLM=true + install Ollama
  Tier 4: Cloud LLM      — set ANTHROPIC_API_KEY
"""
import sys
import os
import argparse
import logging
import signal

sys.path.insert(0, os.path.dirname(__file__))

from core.config import (
    ASSISTANT_NAME, VOICE_ENABLED, API_HOST, API_PORT,
    LOG_DIR, ANTHROPIC_API_KEY, ENABLE_LOCAL_LLM, OLLAMA_HOST, OLLAMA_MODEL,
)
from core.memory import Memory
from core.tool_registry import ToolRegistry
from core.orchestrator import Orchestrator
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


def setup_logging(debug: bool = False):
    level = logging.DEBUG if debug else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        handlers=[
            logging.FileHandler(str(LOG_DIR / "cogman.log")),
        ] + ([logging.StreamHandler(sys.stderr)] if debug else []),
    )


def build_agent() -> tuple[Orchestrator, Memory, ToolRegistry]:
    memory = Memory()
    registry = ToolRegistry()

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

    orchestrator = Orchestrator(registry, memory)
    return orchestrator, memory, registry


BANNER = r"""
   ██████╗ ██████╗  ██████╗ ███╗   ███╗ █████╗ ███╗   ██╗
  ██╔════╝██╔═══██╗██╔════╝ ████╗ ████║██╔══██╗████╗  ██║
  ██║     ██║   ██║██║  ███╗██╔████╔██║███████║██╔██╗ ██║
  ██║     ██║   ██║██║   ██║██║╚██╔╝██║██╔══██║██║╚██╗██║
  ╚██████╗╚██████╔╝╚██████╔╝██║ ╚═╝ ██║██║  ██║██║ ╚████║
   ╚═════╝ ╚═════╝  ╚═════╝ ╚═╝     ╚═╝╚═╝  ╚═╝╚═╝  ╚═══╝
             Jarvis-style Linux AI Assistant
"""


def print_status(orchestrator: Orchestrator):
    from speech.tts import get_tts_backend, is_tts_available
    from speech.stt import get_stt_backend, is_stt_available

    n_tools = len(orchestrator.registry.list_names())
    ollama_ok = orchestrator._check_ollama()

    lines = [
        "─" * 50,
        " cogman status",
        "─" * 50,
        f" Tools loaded : {n_tools}",
        "",
        " Routing tiers:",
        f"  [✓] Tier 1 — Regex rules       (always active)",
        f"  [✓] Tier 2 — Local NLP          (always active)",
        f"  [{'✓' if ollama_ok else '✗'}] Tier 3 — Local LLM (Ollama)  "
        + (f"model={OLLAMA_MODEL}" if ollama_ok else f"not running — start: ollama run {OLLAMA_MODEL}"),
        f"  [{'✓' if ANTHROPIC_API_KEY else '✗'}] Tier 4 — Cloud LLM (Anthropic) "
        + ("active" if ANTHROPIC_API_KEY else "set ANTHROPIC_API_KEY to enable"),
        "",
        " Voice:",
        f"  TTS: {get_tts_backend()}" + (" (audio)" if is_tts_available() else " (print fallback)"),
        f"  STT: {get_stt_backend()}" + (" (mic)" if is_stt_available() else " (keyboard fallback)"),
        "─" * 50,
    ]
    print("\n".join(lines))


def run_cli(orchestrator: Orchestrator):
    print(BANNER)
    n = len(orchestrator.registry.list_names())
    print(f"  {n} tools loaded | type 'help' for commands | 'status' for tier info\n")

    signal.signal(signal.SIGINT, lambda s, f: (print("\n[cogman] Goodbye."), sys.exit(0)))

    while True:
        try:
            user_input = input("you > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n[cogman] Goodbye.")
            break

        if not user_input:
            continue

        cmd = user_input.lower()

        if cmd in ("quit", "exit", "bye", "goodbye"):
            print("[cogman] Goodbye.")
            break
        elif cmd == "help":
            print(f"\nAvailable tools ({n}):\n{orchestrator.registry.summary()}\n")
            print("Meta commands: help, tools, status, clear, quit")
            continue
        elif cmd == "tools":
            print(f"\n{orchestrator.registry.summary()}\n")
            continue
        elif cmd == "status":
            print_status(orchestrator)
            continue
        elif cmd == "clear":
            orchestrator.memory.short.clear()
            print("[cogman] Conversation cleared.")
            continue

        response = orchestrator.process(user_input)
        print(f"\ncogman > {response}\n")


def run_voice(orchestrator: Orchestrator):
    from speech.tts import speak, get_tts_backend
    from speech.stt import get_stt_backend, is_stt_available
    from speech.listener import start_listening

    print(BANNER)
    print(f"  Voice mode | TTS={get_tts_backend()} | STT={get_stt_backend()}")
    print("  Say 'Hey cogman' to wake me | Ctrl+C to stop\n")

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
        print("\n[cogman] Voice mode stopped.")


def run_setup():
    print("[cogman] Setup — downloading offline speech models\n")

    print("[1/2] Installing STT model (Vosk small ~50MB)...")
    try:
        from speech.stt import download_vosk_model
        result = download_vosk_model("small")
        print(f"  {result}")
    except Exception as e:
        print(f"  Error: {e}")
        print("  Manual: pip install vosk sounddevice")

    print("\n[2/2] TTS check...")
    try:
        from speech.tts import get_tts_backend
        backend = get_tts_backend()
        print(f"  TTS backend: {backend}")
        if backend == "print":
            print("  Install pyttsx3: pip install pyttsx3")
            print("  Or system TTS:   sudo apt install espeak-ng")
    except Exception as e:
        print(f"  Error: {e}")

    print("\n[cogman] Setup complete. Run with --voice to test.")


def run_api(orchestrator: Orchestrator, memory: Memory):
    try:
        import uvicorn
        from api.server import app, init as api_init
    except ImportError:
        print("[cogman] Install: pip install fastapi uvicorn")
        sys.exit(1)

    api_init(orchestrator, memory)
    print(f"[cogman] API: http://{API_HOST}:{API_PORT}")
    uvicorn.run(app, host=API_HOST, port=API_PORT, log_level="warning")


def main():
    parser = argparse.ArgumentParser(prog="cogman", description="cogman — Jarvis-style Linux AI")
    parser.add_argument("--voice",  action="store_true", help="Wake-word voice mode")
    parser.add_argument("--api",    action="store_true", help="Start REST API server")
    parser.add_argument("--setup",  action="store_true", help="Download offline speech models")
    parser.add_argument("--status", action="store_true", help="Show tier/backend status")
    parser.add_argument("-c", "--command", type=str, help="Run one command and exit")
    parser.add_argument("--debug",  action="store_true", help="Verbose debug logging")
    args = parser.parse_args()

    setup_logging(args.debug)

    if args.setup:
        run_setup()
        return

    orchestrator, memory, registry = build_agent()

    if args.status:
        print_status(orchestrator)
        return

    if args.command:
        print(orchestrator.process(args.command))
        return

    if args.voice:
        run_voice(orchestrator)
    elif args.api:
        run_api(orchestrator, memory)
    else:
        run_cli(orchestrator)


if __name__ == "__main__":
    main()
