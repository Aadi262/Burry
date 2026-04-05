#!/usr/bin/env python3
"""
tts.py — Butler's local voice layer.

Priority chain:
1. Kokoro neural TTS on Apple Silicon when available.
2. macOS `say` fallback so Butler never goes silent or crashes.
"""

from __future__ import annotations

import fcntl
import re
import subprocess
import tempfile
import threading
import time
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path

import numpy as np

from butler_config import TTS_ENGINE, TTS_MAX_WORDS, TTS_SPEED, TTS_VOICE

MODELS_DIR = Path(__file__).resolve().parent / "models"
KOKORO_MODEL_PATH = MODELS_DIR / "kokoro-v1.0.onnx"
KOKORO_VOICES_PATH = MODELS_DIR / "voices-v1.0.bin"
TTS_LOCK_PATH = Path(tempfile.gettempdir()) / "mac-butler-tts.lock"
TTS_LOCK_TIMEOUT_SECONDS = 12.0
_PROCESS_TTS_LOCK = threading.Lock()
_RECENT_SPEECH_LOCK = threading.Lock()
_LAST_SPOKEN_TEXT = ""
_LAST_SPOKEN_AT = 0.0


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


def recent_speech_snapshot() -> tuple[str, float]:
    with _RECENT_SPEECH_LOCK:
        return _LAST_SPOKEN_TEXT, _LAST_SPOKEN_AT


def _remember_recent_speech(text: str) -> None:
    global _LAST_SPOKEN_TEXT, _LAST_SPOKEN_AT
    with _RECENT_SPEECH_LOCK:
        _LAST_SPOKEN_TEXT = text
        _LAST_SPOKEN_AT = time.monotonic()


@contextmanager
def _speech_lock(timeout: float = TTS_LOCK_TIMEOUT_SECONDS):
    TTS_LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _PROCESS_TTS_LOCK:
        handle = TTS_LOCK_PATH.open("w")
        acquired = False
        deadline = time.monotonic() + timeout
        try:
            while True:
                try:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    acquired = True
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        break
                    time.sleep(0.05)
            yield acquired
        finally:
            if acquired:
                try:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                except OSError:
                    pass
            handle.close()


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


def _prepare_kokoro_audio(samples) -> np.ndarray:
    audio = np.asarray(samples, dtype=np.float32)
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    if audio.size == 0:
        return audio

    audio = np.nan_to_num(audio, nan=0.0, posinf=0.0, neginf=0.0)
    peak = float(np.max(np.abs(audio))) if audio.size else 0.0
    if peak > 0:
        # Keep headroom so Kokoro output does not clip or crackle on laptop speakers.
        audio = audio / peak * 0.72

    # Soft-limit any remaining spikes instead of hard clipping.
    audio = np.tanh(audio * 1.15).astype(np.float32, copy=False)

    fade = min(256, max(16, audio.size // 200))
    if fade * 2 < audio.size:
        ramp = np.linspace(0.0, 1.0, fade, dtype=np.float32)
        audio[:fade] *= ramp
        audio[-fade:] *= ramp[::-1]

    return np.ascontiguousarray(np.clip(audio, -0.95, 0.95), dtype=np.float32)


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
        audio = _prepare_kokoro_audio(samples)
        if audio.size == 0:
            return False
        print(f"[Voice] 🔊 (kokoro:{TTS_VOICE or 'af_bella'}) {text[:120]}")
        sd.stop()
        sd.play(audio, rate)
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
    with _speech_lock() as acquired:
        if not acquired:
            print("[Voice] Skipping overlapping speech.")
            return
        if _try_kokoro(clean):
            _remember_recent_speech(clean)
            return
        _say_fallback(clean)
        _remember_recent_speech(clean)


if __name__ == "__main__":
    print("=== Butler TTS Test ===\n")
    print(describe_tts())
    speak("Good morning. mac-butler is ready. Want to jump in?")
