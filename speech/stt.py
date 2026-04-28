"""
Speech-to-Text — offline-first, zero API.

Backend priority (tried in order):
  1. vosk       — offline, fast, tiny model (~50 MB), best default
  2. whisper    — offline, accurate, larger model (openai-whisper)
  3. input()    — text fallback (no mic needed)

Vosk model auto-download:
  python -c "from speech.stt import download_vosk_model; download_vosk_model()"

Manual install:
  pip install vosk sounddevice
  pip install openai-whisper sounddevice scipy    # for Whisper
"""
import os
import logging
import tempfile
import threading
from pathlib import Path

log = logging.getLogger("cogman.speech.stt")

VOSK_MODEL_DIR = Path(__file__).parent.parent / "data" / "vosk_model"
SAMPLE_RATE = 16000
RECORD_SECONDS = 5      # default single-shot recording length

_backend: str | None = None
_vosk_model = None
_whisper_model = None
_lock = threading.Lock()


def _detect_backend() -> str:
    global _backend
    if _backend:
        return _backend

    # 1. Vosk (offline, fast)
    try:
        import vosk  # noqa
        import sounddevice  # noqa
        if VOSK_MODEL_DIR.exists():
            _backend = "vosk"
            log.info("STT backend: vosk (model: %s)", VOSK_MODEL_DIR)
            return _backend
        else:
            log.info("Vosk installed but no model found — run: python -c \"from speech.stt import download_vosk_model; download_vosk_model()\"")
    except ImportError:
        pass

    # 2. Whisper (offline, accurate)
    try:
        import whisper  # noqa
        import sounddevice  # noqa
        _backend = "whisper"
        log.info("STT backend: openai-whisper")
        return _backend
    except ImportError:
        pass

    # 3. Text fallback
    _backend = "input"
    log.warning("STT: no audio backend — using keyboard input fallback")
    return _backend


def _get_vosk_model():
    global _vosk_model
    if _vosk_model is None:
        from vosk import Model
        with _lock:
            if _vosk_model is None:
                _vosk_model = Model(str(VOSK_MODEL_DIR))
    return _vosk_model


def _get_whisper_model():
    global _whisper_model
    if _whisper_model is None:
        import whisper
        from core.config import WHISPER_MODEL
        with _lock:
            if _whisper_model is None:
                log.info("Loading Whisper model '%s'...", WHISPER_MODEL)
                _whisper_model = whisper.load_model(WHISPER_MODEL)
    return _whisper_model


def _record(seconds: float = RECORD_SECONDS) -> bytes:
    """Record from default mic and return raw PCM bytes."""
    import sounddevice as sd
    import numpy as np

    log.debug("Recording %.1fs...", seconds)
    frames = sd.rec(
        int(seconds * SAMPLE_RATE),
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="int16",
    )
    sd.wait()
    return frames.tobytes()


def _record_until_silence(max_seconds: float = 10.0, silence_thresh: int = 500,
                           silence_duration: float = 1.5) -> bytes:
    """
    Record until silence is detected (VAD-lite: amplitude threshold).
    Stops after silence_duration seconds of quiet or max_seconds total.
    """
    import sounddevice as sd
    import numpy as np

    chunk_size = int(SAMPLE_RATE * 0.1)   # 100ms chunks
    max_chunks = int(max_seconds * 10)
    silence_chunks = int(silence_duration * 10)

    all_frames = []
    silent_count = 0
    started = False

    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16") as stream:
        for _ in range(max_chunks):
            chunk, _ = stream.read(chunk_size)
            amp = np.abs(chunk).mean()
            all_frames.append(chunk.tobytes())

            if amp > silence_thresh:
                started = True
                silent_count = 0
            elif started:
                silent_count += 1
                if silent_count >= silence_chunks:
                    break

    return b"".join(all_frames)


def _vosk_transcribe(pcm_bytes: bytes) -> str:
    from vosk import KaldiRecognizer
    import json

    model = _get_vosk_model()
    rec = KaldiRecognizer(model, SAMPLE_RATE)
    rec.AcceptWaveform(pcm_bytes)
    result = json.loads(rec.FinalResult())
    return result.get("text", "").strip()


def _whisper_transcribe(pcm_bytes: bytes) -> str:
    import scipy.io.wavfile as wav
    import numpy as np

    model = _get_whisper_model()
    samples = np.frombuffer(pcm_bytes, dtype="int16").astype("float32") / 32768.0

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        tmp = f.name
    wav.write(tmp, SAMPLE_RATE, (samples * 32767).astype("int16"))

    result = model.transcribe(tmp)
    os.unlink(tmp)
    return result["text"].strip()


def listen(seconds: float = None, smart_stop: bool = True) -> str:
    """
    Capture one voice command and return as text.

    Args:
        seconds:    Fixed recording duration. If None, uses smart_stop.
        smart_stop: Auto-stop on silence (recommended).
    Returns:
        Transcribed text, or "" on failure.
    """
    backend = _detect_backend()

    if backend == "input":
        return input("(mic unavailable) you > ").strip()

    try:
        if seconds is not None:
            pcm = _record(seconds)
        elif smart_stop:
            pcm = _record_until_silence()
        else:
            pcm = _record(RECORD_SECONDS)

        if backend == "vosk":
            text = _vosk_transcribe(pcm)
        else:  # whisper
            text = _whisper_transcribe(pcm)

        log.info("STT: %r", text)
        return text

    except Exception as e:
        log.warning("STT listen failed: %s", e)
        return ""


def transcribe_file(path: str) -> str:
    """Transcribe an audio file to text (supports Whisper and Vosk)."""
    backend = _detect_backend()
    path = os.path.expanduser(path)

    if backend == "whisper":
        model = _get_whisper_model()
        result = model.transcribe(path)
        return result["text"].strip()

    elif backend == "vosk":
        import scipy.io.wavfile as wav
        rate, data = wav.read(path)
        if data.dtype != "int16":
            data = (data * 32767).astype("int16")
        return _vosk_transcribe(data.tobytes())

    return "No STT backend available"


def download_vosk_model(size: str = "small") -> str:
    """
    Download a Vosk model automatically.
    size: "small" (~50 MB, fast) | "large" (~1.8 GB, accurate)
    """
    import urllib.request
    import zipfile

    models = {
        "small": ("vosk-model-small-en-us-0.15",
                  "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip"),
        "large": ("vosk-model-en-us-0.22",
                  "https://alphacephei.com/vosk/models/vosk-model-en-us-0.22.zip"),
    }
    name, url = models.get(size, models["small"])
    dest = VOSK_MODEL_DIR.parent

    if VOSK_MODEL_DIR.exists():
        return f"Vosk model already exists: {VOSK_MODEL_DIR}"

    zip_path = dest / f"{name}.zip"
    print(f"Downloading Vosk model ({size}) from {url} ...")
    urllib.request.urlretrieve(url, zip_path)

    print(f"Extracting to {dest} ...")
    with zipfile.ZipFile(zip_path, "r") as z:
        z.extractall(dest)

    extracted = dest / name
    extracted.rename(VOSK_MODEL_DIR)
    zip_path.unlink()

    return f"Vosk model installed: {VOSK_MODEL_DIR}"


def is_stt_available() -> bool:
    return _detect_backend() != "input"


def get_stt_backend() -> str:
    return _detect_backend()
