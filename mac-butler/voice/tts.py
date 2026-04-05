#!/usr/bin/env python3
"""
tts.py — Butler's natural voice layer.

Uses macOS `say` with the best available premium voice.
Heavy text shaping before speaking: breath pauses between sentences,
acronym expansion, and word trimming so it sounds like a human colleague.
"""

import re
import subprocess
from functools import lru_cache

from butler_config import TTS_MAX_WORDS, TTS_RATE, TTS_VOICE


@lru_cache(maxsize=1)
def _available_voices() -> set[str]:
    try:
        result = subprocess.run(
            ["say", "-v", "?"],
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception:
        return set()

    voices = set()
    for line in (result.stdout or "").splitlines():
        parts = re.split(r"\s{2,}", line.strip(), maxsplit=1)
        if parts and parts[0]:
            voices.add(parts[0])
    return voices


def _pick_voice() -> str:
    available = _available_voices()
    for candidate in (TTS_VOICE, "Tara", "Samantha", "Daniel", "Rishi"):
        if candidate and (not available or candidate in available):
            return candidate
    return TTS_VOICE or "Samantha"


def describe_tts() -> dict:
    return {"backend": "macos", "voice": _pick_voice(), "rate": TTS_RATE}


def shape_for_speech(text: str) -> str:
    cleaned = re.sub(r"\[\[slnc\s+\d+\]\]", " ", text or "")
    cleaned = cleaned.replace('"', "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    words = cleaned.split()
    if len(words) > TTS_MAX_WORDS:
        cleaned = " ".join(words[:TTS_MAX_WORDS]).rstrip(",;:-")
        if cleaned and cleaned[-1] not in ".!?":
            cleaned += "."
    return cleaned


def speak(text: str) -> None:
    clean_text = shape_for_speech(text)
    if not clean_text:
        return
    voice = _pick_voice()
    print(f"[Voice] 🔊 ({voice}) {clean_text[:120]}")
    subprocess.run(["say", "-v", voice, "-r", str(TTS_RATE), clean_text], check=False)


if __name__ == "__main__":
    print("=== Butler TTS Test ===\n")
    info = describe_tts()
    print(f"Backend: {info['backend']}, Voice: {info['voice']}, Rate: {info['rate']}\n")

    sample = (
        "Still grinding. [[slnc 300]] "
        "mac-butler's voice loop needs tightening. "
        "DKIM validation is still pending in email-infra. "
        "Want to start with the voice fix?"
    )
    print(f"Raw:\n{sample}\n")
    shaped = shape_for_speech(sample)
    print(f"Shaped:\n{shaped}\n")
    speak(sample)
    print("Done!")
