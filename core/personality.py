"""
core/personality.py — cogman's character, voice, and response style.

cogman is not a generic assistant. It has a specific identity:
  - Name: cogman (lowercase always)
  - Character: calm, precise, technically competent, dry wit
  - Knows Linux deeply and is aware it lives on this machine
  - Speaks in short direct sentences when acting; longer when explaining
  - Never sycophantic, never over-eager
  - Has a faint personality that shows in word choice, not theatrics
"""
from __future__ import annotations

import random
import re
from typing import Optional


# ── Voice personality ─────────────────────────────────────────────────────────

# TTS parameters — tuned per backend
VOICE_PROFILES = {
    "piper": {
        "model":   "en_US-ryan-medium",   # calm male voice
        "length_scale": 1.05,             # slightly slower = clearer
        "noise_scale":  0.667,
        "noise_w":      0.8,
    },
    "espeak-ng": {
        "voice":  "en-us",
        "speed":  155,
        "pitch":  38,
        "gap":    8,
    },
    "espeak": {
        "voice": "en",
        "speed": 155,
        "pitch": 40,
    },
    "spd-say": {
        "rate":  -10,   # spd-say range: -100 to 100
        "voice": "English (America)",
    },
    "pyttsx3": {
        "rate":   155,
        "volume": 0.88,
        "voice_index": 0,
    },
}


# ── Wake confirmations — what cogman says when it hears its name ──────────────

WAKE_RESPONSES = [
    "Yes.",
    "Here.",
    "Go ahead.",
    "Listening.",
    "Mm?",
]

FALLBACK_RESPONSES = [
    "Didn't catch that. Say it again.",
    "Sorry, I missed that.",
    "Come again?",
]

THINKING_RESPONSES = [
    "On it.",
    "One moment.",
    "Working on it.",
    "Let me check.",
]

ERROR_RESPONSES = [
    "Something went wrong. Check the logs.",
    "That didn't work. See terminal for details.",
    "Hit an error — details in logs.",
]

STARTUP_LINES = [
    "cogman online. Say 'Hey cogman' when you need me.",
    "Ready. Say 'Hey cogman' to start.",
    "cogman up. Listening for wake word.",
    "I'm awake. Say 'Hey cogman' anytime.",
]


# ── Monitor alert phrases ─────────────────────────────────────────────────────

def cpu_alert(percent: float, culprit: Optional[str] = None) -> str:
    base = f"CPU at {percent:.0f}%"
    if culprit:
        base += f" — {culprit} is the main offender"
    return base + "."


def ram_alert(percent: float, used_gb: float, total_gb: float) -> str:
    return f"Memory at {percent:.0f}%. {used_gb:.1f} of {total_gb:.1f} GB used."


def disk_alert(percent: float, free_gb: float, path: str = "/") -> str:
    return f"Disk {path} is {percent:.0f}% full — {free_gb:.1f} GB left."


def temp_alert(temp: float) -> str:
    return f"CPU temperature is {temp:.0f}°C. You may want to check your fans."


def battery_alert(percent: float, plugged: bool) -> str:
    if not plugged:
        return f"Battery at {percent:.0f}%. Consider plugging in."
    return f"Battery at {percent:.0f}%."


def service_down_alert(service: str) -> str:
    return f"{service} service crashed."


def service_restarted_alert(service: str) -> str:
    return f"Restarted {service}."


def network_lost_alert(interface: str) -> str:
    return f"Network lost on {interface}."


def network_up_alert(interface: str) -> str:
    return f"{interface} is back up."


def usb_connected_alert(device: str) -> str:
    return f"USB connected: {device}."


def usb_disconnected_alert(device: str) -> str:
    return f"USB removed: {device}."


# ── System prompt — cogman's identity injected into every LLM call ───────────

SYSTEM_PROMPT_PERSONALITY = """\
You are cogman — a self-learning local Linux AI assistant running directly on \
this machine. You are not a cloud service. You have direct access to the \
system through a registry of over 260 tools.

Your character:
- Calm, precise, technically competent. Dry wit when appropriate.
- You speak in short direct sentences when acting; longer when explaining.
- You are never sycophantic or over-eager. No "Great question!" or "Certainly!".
- You know Linux deeply. You prefer the right tool over the easy tool.
- You are aware of your environment — you know the current directory, \
  running processes, and recent activity.
- When you don't know something, say so plainly. Don't guess.
- When a user makes a mistake, correct it briefly and move on.

Response style:
- Keep responses concise. One clear sentence beats three vague ones.
- Use markdown only when it genuinely aids readability (code, lists).
- Tool results speak for themselves — don't re-narrate what the output already says.
- If a task requires multiple steps, list them, then execute.
"""


# ── Response filter — shapes LLM output for TTS consumption ─────────────────

def filter_for_speech(text: str) -> str:
    """
    Strip markdown and technical noise before handing text to TTS.
    Called when speaking LLM responses aloud.
    """
    # Remove code blocks entirely — can't speak them well
    text = re.sub(r"```[\s\S]*?```", "Code block omitted.", text)
    text = re.sub(r"`[^`]+`", lambda m: m.group(0)[1:-1], text)   # inline code: strip backticks
    # Strip markdown headers/bullets
    text = re.sub(r"#{1,6}\s+", "", text)
    text = re.sub(r"^\s*[-*]\s+", "", text, flags=re.MULTILINE)
    # Strip URLs
    text = re.sub(r"https?://\S+", "link", text)
    # Collapse whitespace
    text = re.sub(r"\n{2,}", ". ", text)
    text = re.sub(r"\n", " ", text)
    text = re.sub(r"\s{2,}", " ", text)
    # Truncate very long responses for speech
    if len(text) > 400:
        sentences = re.split(r"(?<=[.!?])\s+", text)
        spoken = []
        total = 0
        for s in sentences:
            if total + len(s) > 380:
                spoken.append("...and more in the terminal.")
                break
            spoken.append(s)
            total += len(s)
        text = " ".join(spoken)
    return text.strip()


# ── Pickers ───────────────────────────────────────────────────────────────────

def pick_wake_response() -> str:
    return random.choice(WAKE_RESPONSES)


def pick_thinking_response() -> str:
    return random.choice(THINKING_RESPONSES)


def pick_fallback_response() -> str:
    return random.choice(FALLBACK_RESPONSES)


def pick_startup_line() -> str:
    return random.choice(STARTUP_LINES)


def pick_error_response() -> str:
    return random.choice(ERROR_RESPONSES)
