"""
Continuous voice listener — cogman Jarvis-style interaction loop.

Flow:
  [idle] → detect wake word → [beep] → "Yes." → listen for command
         → transcribe → dispatch → filter for speech → speak response
         → [idle]

Usage:
    from speech.listener import start_listening, stop_listening

    def handle(text: str) -> str:
        return orchestrator.process(text)

    start_listening(handle)
    stop_listening()   # from another thread
"""
from __future__ import annotations

import logging
import threading
import time

log = logging.getLogger("cogman.speech.listener")

_running       = False
_hotword_thread: threading.Thread | None = None
_BEEP_FREQ     = 880      # Hz — "ready" tone
_BEEP_DUR      = 0.10     # seconds


def _beep(freq: int = _BEEP_FREQ, dur: float = _BEEP_DUR) -> None:
    try:
        import numpy as np, sounddevice as sd
        t    = __import__("numpy").linspace(0, dur, int(44100 * dur), endpoint=False)
        wave = (np.sin(2 * 3.14159 * freq * t) * 0.25 * 32767).astype("int16")
        sd.play(wave, samplerate=44100, blocking=True)
    except Exception:
        pass


def _on_wakeword(wake_text: str, callback) -> None:
    """Handle a detected wake word: beep → acknowledge → listen → respond."""
    from speech.tts  import speak
    from speech.stt  import listen
    from core.personality import (
        pick_wake_response, pick_thinking_response,
        pick_fallback_response, pick_error_response,
        filter_for_speech,
    )

    _beep()
    speak(pick_wake_response(), block=False)

    command = listen(smart_stop=True)
    if not command:
        speak(pick_fallback_response())
        return

    log.info("Voice command: %r", command)
    speak(pick_thinking_response(), block=False)

    try:
        response = callback(command)
        if response:
            spoken = filter_for_speech(response)
            if spoken:
                speak(spoken)
    except Exception as e:
        log.exception("Voice callback error: %s", e)
        speak(pick_error_response())


def start_listening(callback, mode: str = "auto") -> None:
    """
    Start the voice listener.

    Args:
        callback: function(text) -> str — receives command, returns spoken response
        mode:     "hotword" | "auto" (try hotword, fall back to interactive)
    """
    global _running
    _running = True

    from speech.stt     import is_stt_available, get_stt_backend
    from speech.tts     import speak, get_tts_backend
    from speech.hotword import get_hotword_backend
    from core.personality import pick_startup_line

    log.info("Voice | TTS=%s | STT=%s | hotword=%s | mode=%s",
             get_tts_backend(), get_stt_backend(), get_hotword_backend(), mode)

    speak(pick_startup_line())

    if mode in ("hotword", "auto") and is_stt_available():
        _start_hotword_mode(callback)
    else:
        _start_interactive_mode(callback)


def _start_hotword_mode(callback) -> None:
    global _hotword_thread
    from speech.hotword import start_hotword, stop_hotword

    def on_wake(text):
        if _running:
            _on_wakeword(text, callback)

    _hotword_thread = start_hotword(on_wake)
    try:
        while _running:
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        stop_hotword()


def _start_interactive_mode(callback) -> None:
    from speech.stt   import listen
    from speech.tts   import speak
    from core.personality import filter_for_speech, pick_error_response

    print("\n[cogman] Voice mode (text input — mic not available)")
    while _running:
        try:
            command = listen()
            if not command:
                continue
            if command.lower() in ("quit", "exit", "bye", "goodbye"):
                speak("Goodbye.")
                break
            try:
                response = callback(command)
                if response:
                    spoken = filter_for_speech(response)
                    if spoken:
                        speak(spoken)
            except Exception as e:
                log.exception("Voice callback error: %s", e)
                speak(pick_error_response())
        except KeyboardInterrupt:
            break


def stop_listening() -> None:
    global _running
    _running = False
    try:
        from speech.hotword import stop_hotword
        stop_hotword()
    except Exception:
        pass
    log.info("Voice listener stopped")
