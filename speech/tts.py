"""
Text-to-Speech — offline-first, personality-tuned.

Backend priority:
  1. piper     — neural TTS, natural voice (best quality, fast on CPU)
  2. pyttsx3   — Python, uses espeak/festival under the hood
  3. espeak-ng — system binary, very fast
  4. espeak    — older fallback
  5. spd-say   — speech-dispatcher
  6. festival  — Festival TTS
  7. print     — silent fallback

Piper install:
  pip install piper-tts
  # model downloads automatically on first use to ~/.local/share/piper/

espeak-ng install:
  sudo apt install espeak-ng
"""
from __future__ import annotations

import io
import logging
import shutil
import subprocess
import threading
import wave
from pathlib import Path
from typing import Optional

log = logging.getLogger("cogman.speech.tts")

_backend: str | None = None
_pyttsx3_engine = None
_piper_voice = None
_lock = threading.Lock()

PIPER_MODEL_DIR = Path.home() / ".local" / "share" / "piper"
PIPER_MODEL_DIR.mkdir(parents=True, exist_ok=True)


# ── Backend detection ─────────────────────────────────────────────────────────

def _detect_backend() -> str:
    global _backend
    if _backend:
        return _backend

    # 1. Piper neural TTS
    try:
        from piper import PiperVoice  # noqa
        _backend = "piper"
        log.info("TTS backend: piper")
        return _backend
    except ImportError:
        pass

    # 2. pyttsx3
    try:
        import pyttsx3
        pyttsx3.init()
        _backend = "pyttsx3"
        log.info("TTS backend: pyttsx3")
        return _backend
    except Exception:
        pass

    # 3. espeak-ng
    if shutil.which("espeak-ng"):
        _backend = "espeak-ng"
        return _backend

    # 4. espeak
    if shutil.which("espeak"):
        _backend = "espeak"
        return _backend

    # 5. spd-say
    if shutil.which("spd-say"):
        _backend = "spd-say"
        return _backend

    # 6. festival
    if shutil.which("festival"):
        _backend = "festival"
        return _backend

    _backend = "print"
    log.warning("TTS: no audio backend — using print fallback")
    return _backend


# ── Piper ─────────────────────────────────────────────────────────────────────

def _find_piper_model() -> Optional[Path]:
    preferred = [
        "en_US-ryan-medium", "en_US-amy-medium",
        "en_US-lessac-medium", "en_US-libritts-high",
    ]
    for name in preferred:
        p = PIPER_MODEL_DIR / f"{name}.onnx"
        if p.exists():
            return p
    models = list(PIPER_MODEL_DIR.glob("*.onnx"))
    return models[0] if models else None


def _download_piper_model(model_name: str = "en_US-ryan-medium") -> Optional[Path]:
    onnx_path = PIPER_MODEL_DIR / f"{model_name}.onnx"
    json_path = PIPER_MODEL_DIR / f"{model_name}.onnx.json"
    if onnx_path.exists() and json_path.exists():
        return onnx_path
    base = "https://huggingface.co/rhasspy/piper-voices/resolve/main"
    parts = model_name.split("-")
    if len(parts) < 3:
        return None
    lang_code, speaker, quality = parts[0], parts[1], parts[2]
    lang = lang_code.split("_")[0]
    url_base = f"{base}/{lang}/{lang_code}/{speaker}/{quality}"
    import urllib.request
    log.info("Downloading Piper model %s ...", model_name)
    try:
        urllib.request.urlretrieve(f"{url_base}/{model_name}.onnx", onnx_path)
        urllib.request.urlretrieve(f"{url_base}/{model_name}.onnx.json", json_path)
        return onnx_path
    except Exception as e:
        log.warning("Piper download failed: %s", e)
        onnx_path.unlink(missing_ok=True)
        json_path.unlink(missing_ok=True)
        return None


def _get_piper_voice():
    global _piper_voice
    if _piper_voice is not None:
        return _piper_voice
    with _lock:
        if _piper_voice is not None:
            return _piper_voice
        from piper import PiperVoice
        model = _find_piper_model()
        if model is None:
            model = _download_piper_model()
        if model is None:
            return None
        log.info("Loading Piper voice: %s", model)
        _piper_voice = PiperVoice.load(str(model))
    return _piper_voice


def _piper_speak(text: str, block: bool = True):
    voice = _get_piper_voice()
    if voice is None:
        raise RuntimeError("no piper model")

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(22050)
        voice.synthesize(text, wf)

    buf.seek(44)    # skip WAV header → raw PCM
    pcm = buf.read()

    # Try aplay first (ALSA), then paplay (PulseAudio), then sounddevice
    for player_cmd in [
        ["aplay", "-r", "22050", "-f", "S16_LE", "-c", "1", "-"],
        ["paplay", "--raw", "--rate=22050", "--format=s16le", "--channels=1"],
    ]:
        if shutil.which(player_cmd[0]):
            proc = subprocess.Popen(
                player_cmd, stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            proc.stdin.write(pcm)
            proc.stdin.close()
            if block:
                proc.wait()
            return

    # sounddevice fallback
    import numpy as np, sounddevice as sd
    arr = np.frombuffer(pcm, dtype="int16")
    sd.play(arr, samplerate=22050, blocking=block)


# ── pyttsx3 ───────────────────────────────────────────────────────────────────

def _get_pyttsx3():
    global _pyttsx3_engine
    if _pyttsx3_engine is None:
        import pyttsx3
        try:
            from core.personality import VOICE_PROFILES
            p = VOICE_PROFILES.get("pyttsx3", {})
        except ImportError:
            p = {}
        _pyttsx3_engine = pyttsx3.init()
        _pyttsx3_engine.setProperty("rate",   p.get("rate", 155))
        _pyttsx3_engine.setProperty("volume", p.get("volume", 0.88))
        voices = _pyttsx3_engine.getProperty("voices")
        idx = p.get("voice_index", 0)
        if voices and idx < len(voices):
            _pyttsx3_engine.setProperty("voice", voices[idx].id)
    return _pyttsx3_engine


# ── Public API ────────────────────────────────────────────────────────────────

def speak(text: str, block: bool = True) -> None:
    """Speak text aloud using the best available offline TTS backend."""
    if not text or not text.strip():
        return
    backend = _detect_backend()
    text = text.strip()
    try:
        if backend == "piper":
            _piper_speak(text, block)

        elif backend == "pyttsx3":
            with _lock:
                engine = _get_pyttsx3()
                engine.say(text)
                engine.runAndWait()

        elif backend == "espeak-ng":
            try:
                from core.personality import VOICE_PROFILES
                p = VOICE_PROFILES.get("espeak-ng", {})
            except ImportError:
                p = {}
            cmd = [
                "espeak-ng",
                "-v", p.get("voice", "en-us"),
                "-s", str(p.get("speed", 155)),
                "-p", str(p.get("pitch", 38)),
                "-g", str(p.get("gap", 8)),
                text,
            ]
            if block:
                subprocess.run(cmd, capture_output=True, timeout=30)
            else:
                subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        elif backend == "espeak":
            try:
                from core.personality import VOICE_PROFILES
                p = VOICE_PROFILES.get("espeak", {})
            except ImportError:
                p = {}
            cmd = ["espeak", "-v", p.get("voice", "en"),
                   "-s", str(p.get("speed", 155)), text]
            if block:
                subprocess.run(cmd, capture_output=True, timeout=30)
            else:
                subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        elif backend == "spd-say":
            try:
                from core.personality import VOICE_PROFILES
                p = VOICE_PROFILES.get("spd-say", {})
            except ImportError:
                p = {}
            cmd = ["spd-say", "-r", str(p.get("rate", -10)), text]
            if block:
                subprocess.run(cmd, capture_output=True, timeout=30)
            else:
                subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        elif backend == "festival":
            proc = subprocess.Popen(
                ["festival", "--tts"], stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            proc.communicate(input=text.encode(), timeout=30)

        else:
            print(f"\n[cogman] {text}")

    except Exception as e:
        log.warning("TTS speak failed (%s): %s — falling back to print", backend, e)
        print(f"\n[cogman] {text}")


def speak_async(text: str) -> None:
    threading.Thread(target=speak, args=(text,), daemon=True).start()


def is_tts_available() -> bool:
    return _detect_backend() != "print"


def get_tts_backend() -> str:
    return _detect_backend()


def set_rate(words_per_minute: int) -> None:
    if _detect_backend() == "pyttsx3":
        with _lock:
            _get_pyttsx3().setProperty("rate", words_per_minute)


def set_volume(level: float) -> None:
    if _detect_backend() == "pyttsx3":
        with _lock:
            _get_pyttsx3().setProperty("volume", max(0.0, min(1.0, level)))


def download_piper_model(model_name: str = "en_US-ryan-medium") -> str:
    path = _download_piper_model(model_name)
    if path:
        global _piper_voice, _backend
        _piper_voice = None
        _backend = None
        return f"Piper model downloaded: {path}"
    return f"Download failed for '{model_name}'. Check connection."


def list_piper_models() -> str:
    models = list(PIPER_MODEL_DIR.glob("*.onnx"))
    if not models:
        return "No Piper models yet. Call download_piper_model()"
    return "Downloaded Piper models:\n" + "\n".join(f"  {m.stem}" for m in sorted(models))
