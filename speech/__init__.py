"""
speech/ — Jarvis-like voice pipeline for cogman.

All backends are offline-first. No API key ever required.

    from speech import speak, listen, start_listening
    speak("Hello, I am cogman")
    text = listen()          # one-shot mic capture → text
    start_listening(callback) # continuous loop with wake-word
"""
from speech.tts import speak, is_tts_available, get_tts_backend
from speech.stt import listen, transcribe_file, is_stt_available, get_stt_backend
from speech.listener import start_listening, stop_listening

__all__ = [
    "speak", "is_tts_available", "get_tts_backend",
    "listen", "transcribe_file", "is_stt_available", "get_stt_backend",
    "start_listening", "stop_listening",
]
