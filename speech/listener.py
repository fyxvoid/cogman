"""
Continuous voice listener — Jarvis-style interaction loop.

Flow:
  [idle] → detect wake word → [alert beep] → listen for command
         → transcribe → dispatch to orchestrator → speak response
         → [idle]

Usage:
    from speech.listener import start_listening, stop_listening

    def handle(text: str) -> str:
        return f"You said: {text}"

    start_listening(handle)   # blocks in voice mode
    stop_listening()          # call from another thread to stop
"""
import logging
import threading
import time

log = logging.getLogger("cogman.speech.listener")

_running = False
_hotword_thread: threading.Thread | None = None
_ALERT_FREQ = 880          # Hz, "ready" beep
_ALERT_DUR  = 0.12         # seconds


def _beep(frequency: int = _ALERT_FREQ, duration: float = _ALERT_DUR) -> None:
    """Short system beep to signal cogman is listening."""
    try:
        import numpy as np, sounddevice as sd
        t = np.linspace(0, duration, int(44100 * duration), endpoint=False)
        wave = (np.sin(2 * np.pi * frequency * t) * 0.3 * 32767).astype("int16")
        sd.play(wave, samplerate=44100, blocking=True)
    except Exception:
        pass   # beep is cosmetic, never fatal


def _on_wakeword(wake_text: str, callback) -> None:
    """Called by hotword detector when wake word is heard."""
    log.info("Wake word: %r — now listening for command", wake_text)

    from speech.tts import speak
    from speech.stt import listen

    _beep()                        # audible cue: "I heard you"
    speak("Yes?", block=False)

    command = listen(smart_stop=True)
    if not command:
        speak("I didn't catch that. Please try again.")
        return

    log.info("Command: %r", command)
    speak("On it.", block=False)

    try:
        response = callback(command)
        if response:
            speak(response)
    except Exception as e:
        log.exception("Callback error: %s", e)
        speak("Something went wrong.")


def start_listening(callback, mode: str = "auto") -> None:
    """
    Start the voice listener.

    Args:
        callback: function(text: str) -> str  — receives command, returns spoken response
        mode:     "hotword"  — always-on wake-word mode
                  "push"     — manual press-to-talk (not implemented, use CLI)
                  "auto"     — try hotword, fall back to interactive loop
    """
    global _running
    _running = True

    from speech.stt import is_stt_available, get_stt_backend
    from speech.tts import speak, get_tts_backend

    tts = get_tts_backend()
    stt = get_stt_backend()
    log.info("Starting voice listener | TTS=%s | STT=%s | mode=%s", tts, stt, mode)

    speak(f"cogman online. Say 'Hey cogman' to wake me.")

    if mode in ("hotword", "auto") and is_stt_available():
        _start_hotword_mode(callback)
    else:
        _start_interactive_mode(callback)


def _start_hotword_mode(callback) -> None:
    """Always-on hotword detection loop."""
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
    """Text-input fallback when mic isn't available."""
    from speech.stt import listen
    from speech.tts import speak

    print("\n[cogman] Voice mode (text input fallback)")
    print("[cogman] Type your command or 'quit' to exit\n")

    while _running:
        try:
            command = listen()           # falls back to input()
            if not command:
                continue
            if command.lower() in ("quit", "exit", "bye"):
                speak("Goodbye!")
                break
            response = callback(command)
            if response:
                speak(response)
        except KeyboardInterrupt:
            break


def stop_listening() -> None:
    global _running
    _running = False
    from speech.hotword import stop_hotword
    stop_hotword()
    log.info("Voice listener stopped")
