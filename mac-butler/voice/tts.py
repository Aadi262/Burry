#!/usr/bin/env python3
"""
tts.py — Butler's local voice layer.

Priority chain:
1. Kokoro neural TTS on Apple Silicon when available.
2. macOS `say` fallback so Butler never goes silent or crashes.
"""

from __future__ import annotations

import re
import subprocess
from functools import lru_cache
from pathlib import Path

from butler_config import TTS_ENGINE, TTS_MAX_WORDS, TTS_SPEED, TTS_VOICE

MODELS_DIR = Path(__file__).resolve().parent / "models"
KOKORO_MODEL_PATH = MODELS_DIR / "kokoro-v1.0.onnx"
KOKORO_VOICES_PATH = MODELS_DIR / "voices-v1.0.bin"


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


def _pick_say_voice() -> str:
    available = _available_voices()
    for candidate in ("Daniel", "Samantha", "Tara", "Rishi"):
        if not available or candidate in available:
            return candidate
    return "Daniel"


@lru_cache(maxsize=1)
def _get_kokoro():
    from kokoro_onnx import Kokoro

    return Kokoro(str(KOKORO_MODEL_PATH), str(KOKORO_VOICES_PATH))


def describe_tts() -> dict:
    engine = (TTS_ENGINE or "auto").lower()
    if engine != "say" and KOKORO_MODEL_PATH.exists() and KOKORO_VOICES_PATH.exists():
        return {"backend": "kokoro", "voice": TTS_VOICE, "speed": TTS_SPEED}
    return {"backend": "say", "voice": _pick_say_voice(), "rate": 165}


def _shape_for_speech(text: str) -> str:
    cleaned = text or ""
    cleaned = re.sub(r"\[\[slnc\s+\d+\]\]", " ", cleaned)
    cleaned = re.sub(r"[*_`#]", "", cleaned)
    cleaned = re.sub(r"https?://\S+", "", cleaned)
    cleaned = cleaned.replace("LLM", "L L M")
    cleaned = cleaned.replace("API", "A P I")
    cleaned = cleaned.replace("VPS", "V P S")
    cleaned = cleaned.replace("MCP", "M C P")
    cleaned = cleaned.replace('"', "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    words = cleaned.split()
    if len(words) > TTS_MAX_WORDS:
        cleaned = " ".join(words[:TTS_MAX_WORDS]).rstrip(",;:-")
        if cleaned and cleaned[-1] not in ".!?":
            cleaned += "."
    return cleaned


def shape_for_speech(text: str) -> str:
    """Compatibility wrapper for older callers/tests."""
    return _shape_for_speech(text)


def _try_kokoro(text: str) -> bool:
    engine = (TTS_ENGINE or "auto").lower()
    if engine == "say":
        return False
    if not KOKORO_MODEL_PATH.exists() or not KOKORO_VOICES_PATH.exists():
        return False

    try:
        import sounddevice as sd

        kokoro = _get_kokoro()
        samples, rate = kokoro.create(
            text,
            voice=TTS_VOICE or "af_bella",
            speed=float(TTS_SPEED or 1.0),
            lang="en-us",
        )
        print(f"[Voice] 🔊 (kokoro:{TTS_VOICE or 'af_bella'}) {text[:120]}")
        sd.play(samples, rate)
        sd.wait()
        return True
    except Exception as exc:
        print(f"[Voice] Kokoro unavailable, falling back to say: {exc}")
        return False


def _say_fallback(text: str) -> None:
    voice = _pick_say_voice()
    print(f"[Voice] 🔊 ({voice}) {text[:120]}")
    subprocess.run(
        ["say", "-v", voice, "-r", "165", text],
        check=False,
    )


def speak(text: str) -> None:
    clean = _shape_for_speech(text)
    if not clean:
        return
    if _try_kokoro(clean):
        return
    _say_fallback(clean)


if __name__ == "__main__":
    print("=== Butler TTS Test ===\n")
    print(describe_tts())
    speak("Good morning. mac-butler is ready. Want to jump in?")
