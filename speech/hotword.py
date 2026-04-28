"""
Wake-word detection — offline, zero API.

Strategy (tried in order):
  1. Vosk keyword spotting  — offline, accurate
  2. Energy + keyword check — pure numpy, instant, no model needed
  3. Disabled              — if no mic/audio available

Wake words: "hey cogman", "cogman", "okay cogman"
"""
import logging
import threading
import time

log = logging.getLogger("cogman.speech.hotword")

WAKE_WORDS = ["hey cogman", "cogman", "okay cogman", "hi cogman"]
ENERGY_THRESHOLD = 800          # RMS amplitude to consider "speech"
SAMPLE_RATE = 16000
CHUNK_DURATION = 0.5            # seconds per check chunk

_running = False
_thread: threading.Thread | None = None


def _vosk_hotword_loop(callback, chunk_sec: float = CHUNK_DURATION):
    """
    Continuous Vosk-based wake-word detection.
    Calls callback(pcm_bytes) when a wake word is detected.
    """
    try:
        import sounddevice as sd
        from vosk import Model, KaldiRecognizer
        from speech.stt import VOSK_MODEL_DIR
        import json, numpy as np

        if not VOSK_MODEL_DIR.exists():
            log.warning("Vosk model not found — falling back to energy hotword")
            _energy_hotword_loop(callback, chunk_sec)
            return

        model = Model(str(VOSK_MODEL_DIR))
        rec = KaldiRecognizer(model, SAMPLE_RATE)
        chunk_size = int(SAMPLE_RATE * chunk_sec)

        log.info("Hotword (Vosk): listening for %s", WAKE_WORDS)

        with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16") as stream:
            while _running:
                chunk, _ = stream.read(chunk_size)
                pcm = chunk.tobytes()
                if rec.AcceptWaveform(pcm):
                    result = json.loads(rec.Result())
                    text = result.get("text", "").lower()
                    if any(w in text for w in WAKE_WORDS):
                        log.info("Wake word detected: %r", text)
                        callback(text)
                        rec = KaldiRecognizer(model, SAMPLE_RATE)  # reset

    except ImportError:
        log.info("Vosk not available — using energy-based hotword detection")
        _energy_hotword_loop(callback, chunk_sec)
    except Exception as e:
        log.exception("Hotword loop error: %s", e)


def _energy_hotword_loop(callback, chunk_sec: float = CHUNK_DURATION):
    """
    Simple energy-based wake detector.
    When energy > threshold, capture a short burst and check for wake words
    using the STT backend.
    """
    try:
        import sounddevice as sd
        import numpy as np
    except ImportError:
        log.warning("sounddevice not installed — hotword detection disabled")
        return

    chunk_size = int(SAMPLE_RATE * chunk_sec)
    burst_size = int(SAMPLE_RATE * 2.0)   # 2s burst for transcription

    log.info("Hotword (energy): listening, threshold=%d", ENERGY_THRESHOLD)

    from speech.stt import _detect_backend, _vosk_transcribe, _whisper_transcribe

    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16") as stream:
        while _running:
            chunk, _ = stream.read(chunk_size)
            rms = int(np.sqrt(np.mean(chunk.astype("int32") ** 2)))

            if rms > ENERGY_THRESHOLD:
                # Capture a short burst and transcribe
                burst_frames = [chunk.tobytes()]
                remaining = burst_size - chunk_size
                while remaining > 0 and _running:
                    c, _ = stream.read(min(chunk_size, remaining))
                    burst_frames.append(c.tobytes())
                    remaining -= chunk_size

                pcm = b"".join(burst_frames)
                backend = _detect_backend()
                try:
                    if backend == "vosk":
                        text = _vosk_transcribe(pcm).lower()
                    elif backend == "whisper":
                        text = _whisper_transcribe(pcm).lower()
                    else:
                        continue

                    if any(w in text for w in WAKE_WORDS):
                        log.info("Wake word detected: %r", text)
                        callback(text)
                except Exception as e:
                    log.debug("Transcription error during hotword check: %s", e)


def start_hotword(callback) -> threading.Thread:
    """Start wake-word detection in a background thread."""
    global _running, _thread
    _running = True
    _thread = threading.Thread(target=_vosk_hotword_loop, args=(callback,), daemon=True)
    _thread.start()
    return _thread


def stop_hotword():
    global _running
    _running = False
