#!/usr/bin/env python3
"""
tts.py — Butler's local voice layer.

Priority chain:
1. Kokoro neural TTS on Apple Silicon when available.
2. macOS `say` fallback so Butler never goes silent or crashes.
"""

from __future__ import annotations

import asyncio
import fcntl
import re
import subprocess
import tempfile
import threading
import time
import unicodedata
import wave
from contextlib import contextmanager
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path

import numpy as np

from butler_config import (
    EDGE_TTS_RATE,
    EDGE_TTS_VOICE,
    NVIDIA_RIVA_TTS_DEFAULT_LANGUAGE_CODE,
    NVIDIA_RIVA_TTS_HINDI_LANGUAGE_CODE,
    SPEECH_PROVIDER_ENDPOINTS,
    TTS_ENGINE,
    TTS_MAX_WORDS,
    TTS_SPEED,
    TTS_TARGETS,
    TTS_VOICE,
)
from butler_secrets.loader import get_secret

try:
    from runtime import note_spoken_text
except Exception:
    def note_spoken_text(*_args, **_kwargs) -> None:
        return None

MODELS_DIR = Path(__file__).resolve().parent / "models"
KOKORO_MODEL_PATH = MODELS_DIR / "kokoro-v1.0.onnx"
KOKORO_VOICES_PATH = MODELS_DIR / "voices-v1.0.bin"
TTS_LOCK_PATH = Path(tempfile.gettempdir()) / "mac-butler-tts.lock"
TTS_LOCK_TIMEOUT_SECONDS = 4.0  # B6: reduced from 12s — fall back to say() faster on stall
_PROCESS_TTS_LOCK = threading.Lock()
_RECENT_SPEECH_LOCK = threading.Lock()
_SPEECH_ACTIVE = threading.Event()
_SPEECH_GRACE_UNTIL = 0.0
_LAST_SPOKEN_TEXT = ""
_LAST_SPOKEN_AT = 0.0
_EDGE_FALLBACK_VOICE = "en-US-AvaMultilingualNeural"
_MOJIBAKE_MARKERS = ("Ã", "Â", "â", "ð", "ï", "\ufffd")


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


@lru_cache(maxsize=1)
def _edge_tts_module():
    import edge_tts

    return edge_tts


def _provider_config(provider: str) -> dict:
    return dict(SPEECH_PROVIDER_ENDPOINTS.get(str(provider or "").strip(), {}))


def _target_provider(target: dict) -> str:
    return str((target or {}).get("provider", "") or "").strip()


def _dedupe_targets(targets: list[dict]) -> list[dict]:
    ordered: list[dict] = []
    seen: set[str] = set()
    for target in targets:
        provider = _target_provider(target)
        if not provider or provider in seen:
            continue
        ordered.append(dict(target))
        seen.add(provider)
    return ordered


def _legacy_tts_targets() -> list[dict]:
    return [
        {"provider": "edge", "voice": EDGE_TTS_VOICE, "rate": EDGE_TTS_RATE},
        {"provider": "kokoro", "voice": TTS_VOICE, "speed": TTS_SPEED},
        {"provider": "say"},
    ]


def _tts_targets() -> tuple[dict, ...]:
    targets = [dict(target) for target in TTS_TARGETS if isinstance(target, dict) and target.get("provider")]
    if not targets:
        targets = _legacy_tts_targets()

    engine = (TTS_ENGINE or "auto").lower().strip()
    if engine == "say":
        targets = [target for target in targets if _target_provider(target) == "say"] or [{"provider": "say"}]
    elif engine == "kokoro":
        targets = [target for target in targets if _target_provider(target) == "kokoro"] + [
            target for target in targets if _target_provider(target) == "say"
        ]
    elif engine == "edge":
        targets = [target for target in targets if _target_provider(target) == "edge"] + [
            target for target in targets if _target_provider(target) in {"kokoro", "say"}
        ]
    elif engine == "nvidia_riva_tts":
        targets = [target for target in targets if _target_provider(target) == "nvidia_riva_tts"] + [
            target for target in targets if _target_provider(target) != "nvidia_riva_tts"
        ]
    return tuple(_dedupe_targets(targets))


def _tts_backend_order() -> tuple[str, ...]:
    return tuple(_target_provider(target) for target in _tts_targets())


def _riva_tts_available() -> bool:
    config = _provider_config("nvidia_riva_tts")
    api_key_env = str(config.get("api_key_env", "") or "").strip()
    if api_key_env and not get_secret(api_key_env, default=""):
        return False
    try:
        import riva.client  # noqa: F401
        from riva.client.proto.riva_audio_pb2 import AudioEncoding  # noqa: F401

        return True
    except Exception:
        return False


def _resolve_tts_language(text: str, target: dict) -> str:
    configured = str(target.get("language_code", "") or "").strip()
    if configured and configured.lower() not in {"auto", "default"}:
        return configured
    if re.search(r"[\u0900-\u097F]", str(text or "")):
        return NVIDIA_RIVA_TTS_HINDI_LANGUAGE_CODE
    return NVIDIA_RIVA_TTS_DEFAULT_LANGUAGE_CODE


def _resolve_riva_voice(target: dict, language_code: str) -> str:
    voice = str(target.get("voice", "") or "").strip()
    if voice and language_code and language_code not in voice:
        return ""
    return voice


def _try_nvidia_riva_tts(text: str, target: dict) -> bool:
    config = _provider_config("nvidia_riva_tts")
    api_key_env = str(config.get("api_key_env", "") or "").strip()
    api_key = get_secret(api_key_env, default="") if api_key_env else ""
    if api_key_env and not api_key:
        return False

    wav_path = Path(tempfile.mkstemp(prefix="mac-butler-riva-tts-", suffix=".wav")[1])
    try:
        import riva.client
        from riva.client.proto.riva_audio_pb2 import AudioEncoding

        metadata = [("authorization", f"Bearer {api_key}")] if api_key else []
        function_id = str(target.get("function_id", "") or "").strip()
        if function_id:
            metadata.append(("function-id", function_id))

        auth = riva.client.Auth(
            uri=str(config.get("server", "") or "").strip(),
            use_ssl=bool(config.get("use_ssl", True)),
            metadata_args=metadata,
        )
        service = riva.client.SpeechSynthesisService(auth)
        language_code = _resolve_tts_language(text, target)
        voice = _resolve_riva_voice(target, language_code)
        sample_rate_hz = int(target.get("sample_rate_hz") or 44100)
        response = service.synthesize(
            text,
            voice or None,
            language_code,
            sample_rate_hz=sample_rate_hz,
            encoding=AudioEncoding.LINEAR_PCM,
        )
        audio = bytes(getattr(response, "audio", b"") or b"")
        if not audio:
            return False

        with wave.open(str(wav_path), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(sample_rate_hz)
            handle.writeframes(audio)

        print(f"[Voice] 🔊 (nvidia_riva_tts:{language_code}) {text[:120]}")
        subprocess.run(["afplay", "-v", "0.85", str(wav_path)], check=False)
        return True
    except Exception as exc:
        print(f"[Voice] NVIDIA Riva TTS unavailable, falling back: {exc}")
        return False
    finally:
        try:
            wav_path.unlink(missing_ok=True)
        except OSError:
            pass


def _edge_tts_available() -> bool:
    try:
        _edge_tts_module()
        return True
    except Exception:
        return False


def _edge_voice_name() -> str:
    configured = str(EDGE_TTS_VOICE or "").strip()
    return configured or _EDGE_FALLBACK_VOICE


def describe_tts() -> dict:
    for target in _tts_targets():
        backend = _target_provider(target)
        if backend == "nvidia_riva_tts" and _riva_tts_available():
            return {
                "backend": backend,
                "model": str(target.get("model", "") or "").strip(),
                "voice": _resolve_riva_voice(target, NVIDIA_RIVA_TTS_DEFAULT_LANGUAGE_CODE),
                "language_code": str(target.get("language_code", "") or "auto").strip() or "auto",
            }
        if backend == "edge" and _edge_tts_available():
            return {"backend": "edge", "voice": _edge_voice_name(), "rate": EDGE_TTS_RATE}
        if backend == "kokoro" and KOKORO_MODEL_PATH.exists() and KOKORO_VOICES_PATH.exists():
            return {"backend": "kokoro", "voice": TTS_VOICE, "speed": TTS_SPEED}
        if backend == "say":
            return {"backend": "say", "voice": _pick_say_voice(), "rate": 165}
    return {"backend": "say", "voice": _pick_say_voice(), "rate": 165}


def warm_tts() -> bool:
    warmed = False
    for target in _tts_targets():
        backend = _target_provider(target)
        if backend == "nvidia_riva_tts":
            if _riva_tts_available():
                return True
            continue
        if backend == "edge":
            try:
                _edge_tts_module()
                warmed = True
                if (TTS_ENGINE or "auto").lower().strip() == "edge":
                    return True
            except Exception as exc:
                print(f"[Voice] Edge TTS warmup skipped: {exc}")
        elif backend == "kokoro":
            if not KOKORO_MODEL_PATH.exists() or not KOKORO_VOICES_PATH.exists():
                continue
            try:
                _get_kokoro()
                return True
            except Exception as exc:
                print(f"[Voice] Kokoro warmup skipped: {exc}")
        elif backend == "say":
            return warmed
    return warmed


def warmup_tts() -> bool:
    """Backward-compatible warmup entrypoint for trigger/startup code."""
    return warm_tts()


def recent_speech_snapshot() -> tuple[str, float]:
    with _RECENT_SPEECH_LOCK:
        return _LAST_SPOKEN_TEXT, _LAST_SPOKEN_AT


def _mark_speech_active(active: bool) -> None:
    global _SPEECH_GRACE_UNTIL
    if active:
        _SPEECH_ACTIVE.set()
        return
    _SPEECH_GRACE_UNTIL = time.monotonic() + 0.8
    _SPEECH_ACTIVE.clear()


def is_speaking() -> bool:
    return _SPEECH_ACTIVE.is_set() or time.monotonic() < _SPEECH_GRACE_UNTIL


def _normalize_echo_text(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(text or "").lower()).strip()


def is_recent_speech_echo(text: str, *, window_seconds: float = 12.0, threshold: float = 0.82) -> bool:
    heard = _normalize_echo_text(text)
    if len(heard) < 8:
        return False
    spoken, spoken_at = recent_speech_snapshot()
    if not spoken or time.monotonic() - spoken_at > window_seconds:
        return False
    spoken_norm = _normalize_echo_text(spoken)
    if not spoken_norm:
        return False
    if heard in spoken_norm or spoken_norm in heard:
        return True
    return SequenceMatcher(None, heard, spoken_norm).ratio() >= threshold


def _remember_recent_speech(text: str) -> None:
    global _LAST_SPOKEN_TEXT, _LAST_SPOKEN_AT
    with _RECENT_SPEECH_LOCK:
        _LAST_SPOKEN_TEXT = text
        _LAST_SPOKEN_AT = time.monotonic()


def _mojibake_score(text: str) -> int:
    sample = str(text or "")
    return sum(sample.count(marker) for marker in _MOJIBAKE_MARKERS)


def _repair_common_mojibake(text: str) -> str:
    raw = str(text or "")
    best = raw
    best_score = _mojibake_score(raw)
    if best_score <= 0:
        return raw

    for encoding in ("latin-1", "cp1252"):
        try:
            candidate = raw.encode(encoding).decode("utf-8")
        except Exception:
            continue
        candidate_score = _mojibake_score(candidate)
        if candidate_score < best_score:
            best = candidate
            best_score = candidate_score
    return best


def _strip_unstable_speech_symbols(text: str) -> str:
    cleaned = unicodedata.normalize("NFKC", str(text or ""))
    cleaned = cleaned.replace("\u00a0", " ")
    cleaned = re.sub(r"(?<!\w)\+(\d)", r"plus \1", cleaned)
    cleaned = re.sub(
        r"([+-]?\d+(?:\.\d+)?)\s*[°º]\s*([CF])\b",
        lambda match: f"{match.group(1)} degrees {'Celsius' if match.group(2).lower() == 'c' else 'Fahrenheit'}",
        cleaned,
    )
    cleaned = re.sub(r"([+-]?\d+(?:\.\d+)?)\s*°\b", r"\1 degrees", cleaned)

    allowed_chars: list[str] = []
    for char in cleaned:
        codepoint = ord(char)
        if codepoint in {0x200C, 0x200D} or 0xFE00 <= codepoint <= 0xFE0F:
            continue
        category = unicodedata.category(char)
        if char in "\n\t " or category[0] in {"L", "M", "N", "P"}:
            allowed_chars.append(char)
            continue
        if category == "Zs":
            allowed_chars.append(" ")
    return "".join(allowed_chars)


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
    cleaned = _repair_common_mojibake(text or "")
    cleaned = _strip_unstable_speech_symbols(cleaned)
    cleaned = re.sub(r"\[\[slnc\s+\d+\]\]", " ", cleaned)
    cleaned = re.sub(r"[*_`#]", "", cleaned)
    cleaned = re.sub(r"https?://\S+", "", cleaned)
    cleaned = re.sub(r"^\s*[-*]\s*", "", cleaned, flags=re.MULTILINE)
    cleaned = cleaned.replace("|", ", ")
    cleaned = cleaned.replace("&", " and ")
    cleaned = re.sub(r"\s*;\s*", ". ", cleaned)
    cleaned = re.sub(r"\s*:\s*", ". ", cleaned)
    cleaned = cleaned.replace("->", " to ")
    cleaned = re.sub(r"\bAI\b", "A I", cleaned)
    cleaned = cleaned.replace("LLM", "L L M")
    cleaned = cleaned.replace("API", "A P I")
    cleaned = cleaned.replace("VPS", "V P S")
    cleaned = cleaned.replace("MCP", "M C P")
    cleaned = re.sub(r"\bGitHub\b", "Git hub", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bYouTube\b", "You tube", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bGmail\b", "G mail", cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.replace('"', "")
    cleaned = cleaned.replace("...", ".")
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
        audio = audio / peak * 0.58

    # Soft-limit any remaining spikes instead of hard clipping.
    audio = np.tanh(audio * 1.05).astype(np.float32, copy=False)

    pad = min(480, max(120, audio.size // 250))
    if pad > 0:
        silence = np.zeros(pad, dtype=np.float32)
        audio = np.concatenate((silence, audio, silence))

    fade = min(768, max(64, audio.size // 120))
    if fade * 2 < audio.size:
        ramp = np.linspace(0.0, 1.0, fade, dtype=np.float32)
        audio[:fade] *= ramp
        audio[-fade:] *= ramp[::-1]

    return np.ascontiguousarray(np.clip(audio, -0.82, 0.82), dtype=np.float32)


def _try_kokoro(text: str) -> bool:
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


def _run_async(coro) -> None:
    try:
        asyncio.run(coro)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(coro)
        finally:
            loop.close()


def _try_edge_tts(text: str) -> bool:
    try:
        edge_tts = _edge_tts_module()
    except Exception as exc:
        print(f"[Voice] Edge TTS unavailable, falling back: {exc}")
        return False

    mp3_path = Path(tempfile.mkstemp(prefix="mac-butler-tts-", suffix=".mp3")[1])
    try:
        communicate = edge_tts.Communicate(
            text,
            voice=_edge_voice_name(),
            rate=EDGE_TTS_RATE or "+0%",
        )
        _run_async(communicate.save(str(mp3_path)))
        if not mp3_path.exists() or mp3_path.stat().st_size <= 0:
            return False
        print(f"[Voice] 🔊 (edge:{_edge_voice_name()}) {text[:120]}")
        subprocess.run(
            ["afplay", "-v", "0.85", str(mp3_path)],
            check=False,
        )
        return True
    except Exception as exc:
        print(f"[Voice] Edge TTS failed, falling back: {exc}")
        return False
    finally:
        try:
            mp3_path.unlink(missing_ok=True)
        except OSError:
            pass


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
        _mark_speech_active(True)
        try:
            for target in _tts_targets():
                backend = _target_provider(target)
                if backend == "nvidia_riva_tts" and _try_nvidia_riva_tts(clean, target):
                    _remember_recent_speech(clean)
                    note_spoken_text(clean)
                    return
                if backend == "edge" and _try_edge_tts(clean):
                    _remember_recent_speech(clean)
                    note_spoken_text(clean)
                    return
                if backend == "kokoro" and _try_kokoro(clean):
                    _remember_recent_speech(clean)
                    note_spoken_text(clean)
                    return
                if backend == "say":
                    _say_fallback(clean)
                    _remember_recent_speech(clean)
                    note_spoken_text(clean)
                    return
            _remember_recent_speech(clean)
            note_spoken_text(clean)
        finally:
            _mark_speech_active(False)


if __name__ == "__main__":
    print("=== Butler TTS Test ===\n")
    print(describe_tts())
    speak("Good morning. mac-butler is ready. Want to jump in?")
