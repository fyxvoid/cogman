"""Voice layer: Speech-to-Text (Whisper) + Text-to-Speech (Coqui TTS)."""
import logging
import os
import tempfile
from core.config import WHISPER_MODEL, TTS_MODEL, AUDIO_SAMPLE_RATE

log = logging.getLogger("cogman.voice")

_whisper_model = None
_tts_model = None


def _load_whisper():
    global _whisper_model
    if _whisper_model is None:
        try:
            import whisper
            _whisper_model = whisper.load_model(WHISPER_MODEL)
            log.info("Whisper model '%s' loaded", WHISPER_MODEL)
        except ImportError:
            log.error("whisper not installed: pip install openai-whisper")
            raise
    return _whisper_model


def _load_tts():
    global _tts_model
    if _tts_model is None:
        try:
            from TTS.api import TTS
            _tts_model = TTS(TTS_MODEL)
            log.info("TTS model loaded: %s", TTS_MODEL)
        except ImportError:
            log.error("TTS not installed: pip install TTS")
            raise
    return _tts_model


def listen(duration: float = 5.0) -> str:
    """Record from mic and transcribe via Whisper."""
    try:
        import sounddevice as sd
        import numpy as np
        import scipy.io.wavfile as wav

        log.info("Listening for %.1fs...", duration)
        recording = sd.rec(
            int(duration * AUDIO_SAMPLE_RATE),
            samplerate=AUDIO_SAMPLE_RATE,
            channels=1,
            dtype="float32",
        )
        sd.wait()

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            tmp_path = f.name
        wav.write(tmp_path, AUDIO_SAMPLE_RATE, (recording * 32767).astype("int16"))

        model = _load_whisper()
        result = model.transcribe(tmp_path)
        os.unlink(tmp_path)
        text = result["text"].strip()
        log.info("Transcribed: %s", text)
        return text

    except ImportError as e:
        log.error("Missing dependency: %s — install sounddevice, scipy, openai-whisper", e)
        return ""
    except Exception as e:
        log.exception("Voice listen error: %s", e)
        return ""


def speak(text: str) -> None:
    """Synthesize speech and play via TTS."""
    try:
        tts = _load_tts()
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            tmp_path = f.name
        tts.tts_to_file(text=text, file_path=tmp_path)
        os.system(f"aplay -q '{tmp_path}'")
        os.unlink(tmp_path)
    except Exception as e:
        log.warning("TTS failed: %s — falling back to text output", e)
        print(f"[cogman] {text}")


def is_voice_available() -> bool:
    try:
        import sounddevice  # noqa
        import whisper       # noqa
        return True
    except ImportError:
        return False
