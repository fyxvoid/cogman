"""
Wake-word detection — offline, zero API.

Backend priority:
  1. openWakeWord — neural, accurate, "hey jarvis" / custom models
  2. Vosk keyword spotting — offline, good
  3. Energy + keyword fallback — pure numpy, no model needed

Wake phrase: "hey cogman" (also responds to "cogman", "okay cogman")

Install:
  pip install openwakeword sounddevice
  pip install vosk sounddevice          # alternative
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Callable

log = logging.getLogger("cogman.speech.hotword")

WAKE_WORDS  = ["hey cogman", "cogman", "okay cogman", "hi cogman"]
SAMPLE_RATE = 16000
CHUNK_SEC   = 0.5           # seconds per detection chunk
ENERGY_THRESHOLD = 600      # RMS amplitude floor

_running = False
_thread: threading.Thread | None = None


# ── openWakeWord (primary) ───────────────────────────────────────────────────

def _oww_hotword_loop(callback: Callable[[str], None]):
    """
    Always-on wake-word detection using openWakeWord.
    Falls back to Vosk loop on import error.
    """
    try:
        import numpy as np
        import sounddevice as sd
        from openwakeword.model import Model

        # openWakeWord ships with "hey_jarvis" and other pre-trained models.
        # We use "hey_jarvis" as a proxy for "hey cogman" since it's phonetically
        # similar and works offline. Users can train a custom model later.
        oww_models = []
        try:
            # Try loading a hey_jarvis or alexa model as cogman wake word
            oww = Model(
                wakeword_models=["hey_jarvis"],
                inference_framework="onnx",
                enable_speex_noise_suppression=False,
            )
            oww_models = ["hey_jarvis"]
            log.info("Hotword backend: openWakeWord (hey_jarvis proxy for 'hey cogman')")
        except Exception:
            # No pre-trained model found — fall back to Vosk
            raise ImportError("no oww model")

        chunk_size = int(SAMPLE_RATE * CHUNK_SEC)

        with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16") as stream:
            while _running:
                chunk, _ = stream.read(chunk_size)
                pcm = chunk.flatten().astype("int16")
                scores = oww.predict(pcm)
                # scores is dict: {model_name: score}
                for model_name, score in scores.items():
                    if score > 0.5:
                        log.info("Wake word detected via openWakeWord (score=%.2f)", score)
                        callback("hey cogman")
                        oww.reset()     # clear state after trigger
                        break

    except ImportError:
        log.info("openWakeWord not available — falling back to Vosk hotword")
        _vosk_hotword_loop(callback)
    except Exception as e:
        log.exception("openWakeWord loop error: %s — falling back", e)
        _vosk_hotword_loop(callback)


# ── Vosk keyword spotting (secondary) ───────────────────────────────────────

def _vosk_hotword_loop(callback: Callable[[str], None]):
    try:
        import json
        import sounddevice as sd
        from vosk import Model, KaldiRecognizer
        from speech.stt import VOSK_MODEL_DIR

        if not VOSK_MODEL_DIR.exists():
            log.info("Vosk model not found — falling back to energy hotword")
            _energy_hotword_loop(callback)
            return

        model     = Model(str(VOSK_MODEL_DIR))
        rec       = KaldiRecognizer(model, SAMPLE_RATE)
        chunk_size = int(SAMPLE_RATE * CHUNK_SEC)

        log.info("Hotword backend: Vosk keyword spotting")

        with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16") as stream:
            while _running:
                chunk, _ = stream.read(chunk_size)
                pcm = chunk.tobytes()
                if rec.AcceptWaveform(pcm):
                    result = json.loads(rec.Result())
                    text   = result.get("text", "").lower()
                    if any(w in text for w in WAKE_WORDS):
                        log.info("Wake word detected (Vosk): %r", text)
                        callback(text)
                        rec = KaldiRecognizer(model, SAMPLE_RATE)   # reset

    except ImportError:
        log.info("Vosk not available — using energy-based hotword")
        _energy_hotword_loop(callback)
    except Exception as e:
        log.exception("Vosk hotword error: %s", e)


# ── Energy-based fallback (no model needed) ──────────────────────────────────

def _energy_hotword_loop(callback: Callable[[str], None]):
    try:
        import numpy as np
        import sounddevice as sd
    except ImportError:
        log.warning("sounddevice not installed — hotword detection disabled")
        return

    chunk_size  = int(SAMPLE_RATE * CHUNK_SEC)
    burst_size  = int(SAMPLE_RATE * 2.0)

    log.info("Hotword backend: energy + STT fallback (threshold=%d)", ENERGY_THRESHOLD)

    from speech.stt import _detect_backend, _vosk_transcribe, _whisper_transcribe

    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16") as stream:
        while _running:
            chunk, _ = stream.read(chunk_size)
            rms = int(np.sqrt(np.mean(chunk.astype("int32") ** 2)))

            if rms > ENERGY_THRESHOLD:
                # Capture burst and transcribe
                burst = [chunk.tobytes()]
                remaining = burst_size - chunk_size
                while remaining > 0 and _running:
                    c, _ = stream.read(min(chunk_size, remaining))
                    burst.append(c.tobytes())
                    remaining -= chunk_size

                pcm = b"".join(burst)
                backend = _detect_backend()
                try:
                    if backend == "vosk":
                        text = _vosk_transcribe(pcm).lower()
                    elif backend == "whisper":
                        text = _whisper_transcribe(pcm).lower()
                    else:
                        continue

                    if any(w in text for w in WAKE_WORDS):
                        log.info("Wake word (energy+STT): %r", text)
                        callback(text)
                except Exception as e:
                    log.debug("Energy hotword transcription error: %s", e)


# ── Public API ────────────────────────────────────────────────────────────────

def start_hotword(callback: Callable[[str], None]) -> threading.Thread:
    """Start wake-word detection in a background daemon thread."""
    global _running, _thread
    _running = True
    _thread  = threading.Thread(
        target=_oww_hotword_loop, args=(callback,),
        name="cogman-hotword", daemon=True,
    )
    _thread.start()
    return _thread


def stop_hotword():
    global _running
    _running = False


def get_hotword_backend() -> str:
    try:
        from openwakeword.model import Model  # noqa
        return "openWakeWord"
    except ImportError:
        pass
    try:
        import vosk  # noqa
        from speech.stt import VOSK_MODEL_DIR
        if VOSK_MODEL_DIR.exists():
            return "vosk"
    except ImportError:
        pass
    try:
        import sounddevice  # noqa
        return "energy+stt"
    except ImportError:
        pass
    return "disabled"
