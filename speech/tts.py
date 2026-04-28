"""
Text-to-Speech — offline-first, zero API.

Backend priority (tried in order):
  1. pyttsx3    — Python package, uses espeak/festival under the hood
  2. espeak-ng  — system binary, very fast
  3. espeak     — older system binary fallback
  4. spd-say    — speech-dispatcher
  5. festival   — Festival TTS
  6. print      — silent fallback (prints text to terminal)

Install recommended:
  pip install pyttsx3
  sudo apt install espeak-ng
"""
import subprocess
import shutil
import logging
import threading

log = logging.getLogger("cogman.speech.tts")

_backend: str | None = None   # set on first use
_pyttsx3_engine = None
_lock = threading.Lock()


def _detect_backend() -> str:
    global _backend
    if _backend:
        return _backend

    # 1. pyttsx3 (Python package, offline)
    try:
        import pyttsx3
        engine = pyttsx3.init()
        engine.setProperty("rate", 160)
        _backend = "pyttsx3"
        log.info("TTS backend: pyttsx3")
        return _backend
    except Exception:
        pass

    # 2. espeak-ng
    if shutil.which("espeak-ng"):
        _backend = "espeak-ng"
        log.info("TTS backend: espeak-ng")
        return _backend

    # 3. espeak
    if shutil.which("espeak"):
        _backend = "espeak"
        log.info("TTS backend: espeak")
        return _backend

    # 4. spd-say (speech-dispatcher)
    if shutil.which("spd-say"):
        _backend = "spd-say"
        log.info("TTS backend: spd-say")
        return _backend

    # 5. festival
    if shutil.which("festival"):
        _backend = "festival"
        log.info("TTS backend: festival")
        return _backend

    # 6. silent
    _backend = "print"
    log.warning("TTS: no audio backend found — using print fallback")
    return _backend


def _get_pyttsx3():
    global _pyttsx3_engine
    if _pyttsx3_engine is None:
        import pyttsx3
        _pyttsx3_engine = pyttsx3.init()
        _pyttsx3_engine.setProperty("rate", 160)
        _pyttsx3_engine.setProperty("volume", 0.9)
        voices = _pyttsx3_engine.getProperty("voices")
        if voices:
            _pyttsx3_engine.setProperty("voice", voices[0].id)
    return _pyttsx3_engine


def speak(text: str, block: bool = True) -> None:
    """Speak text aloud using the best available offline backend."""
    if not text or not text.strip():
        return

    backend = _detect_backend()
    text = text.strip()

    try:
        if backend == "pyttsx3":
            with _lock:
                engine = _get_pyttsx3()
                engine.say(text)
                engine.runAndWait()

        elif backend in ("espeak-ng", "espeak"):
            cmd = [backend, "-s", "160", "-v", "en", text]
            if block:
                subprocess.run(cmd, capture_output=True, timeout=30)
            else:
                subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        elif backend == "spd-say":
            cmd = ["spd-say", "-r", "-10", text]
            if block:
                subprocess.run(cmd, capture_output=True, timeout=30)
            else:
                subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        elif backend == "festival":
            proc = subprocess.Popen(
                ["festival", "--tts"],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            proc.communicate(input=text.encode(), timeout=30)

        else:
            print(f"\n[cogman] {text}")

    except Exception as e:
        log.warning("TTS speak failed (%s): %s — falling back to print", backend, e)
        print(f"\n[cogman] {text}")


def set_rate(words_per_minute: int) -> None:
    """Set speech rate (words per minute). Only affects pyttsx3."""
    backend = _detect_backend()
    if backend == "pyttsx3":
        with _lock:
            _get_pyttsx3().setProperty("rate", words_per_minute)


def set_volume(level: float) -> None:
    """Set speech volume 0.0–1.0. Only affects pyttsx3."""
    backend = _detect_backend()
    if backend == "pyttsx3":
        with _lock:
            _get_pyttsx3().setProperty("volume", max(0.0, min(1.0, level)))


def is_tts_available() -> bool:
    return _detect_backend() != "print"


def get_tts_backend() -> str:
    return _detect_backend()
