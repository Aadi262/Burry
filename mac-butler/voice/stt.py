#!/usr/bin/env python3
"""
voice/stt.py
Real-time STT using mlx-whisper on Apple Silicon with faster-whisper fallback.
"""

from __future__ import annotations

import io
import os
import re
import threading
import time
import wave
from pathlib import Path

import numpy as np
from butler_config import (
    SPEECH_PROVIDER_ENDPOINTS,
    STT_TARGETS,
    VOICE_FASTER_WHISPER_MODEL,
    VOICE_INPUT_BACKEND,
    VOICE_INPUT_BEAM_SIZE,
    VOICE_INPUT_MODEL,
    VOICE_INPUT_PROMPT,
    STT_MAX_SPEECH_S,
    STT_MIN_SPEECH_S,
    STT_SILENCE_THRESHOLD,
)
from butler_secrets.loader import get_secret

SAMPLE_RATE = 16000
SILENCE_END_S = 0.7
DEFAULT_MLX_MODEL = "mlx-community/whisper-small-mlx"
DEFAULT_FASTER_WHISPER_MODEL = "base.en"
POST_TTS_COOLDOWN_S = 0.85
RECENT_TTS_WINDOW_S = 8.0

_MODEL = None
_BACKEND = "none"
_MLX_MODEL_REPO = DEFAULT_MLX_MODEL
_ACTIVE_STT_TARGET: dict[str, str] = {}


def _requested_voice_input_model() -> str:
    return str(os.getenv("VOICE_INPUT_MODEL", VOICE_INPUT_MODEL) or DEFAULT_MLX_MODEL).strip() or DEFAULT_MLX_MODEL


def _requested_faster_whisper_model() -> str:
    return str(
        os.getenv("VOICE_FASTER_WHISPER_MODEL", VOICE_FASTER_WHISPER_MODEL) or DEFAULT_FASTER_WHISPER_MODEL
    ).strip() or DEFAULT_FASTER_WHISPER_MODEL


def _requested_beam_size() -> int:
    try:
        value = int(os.getenv("VOICE_INPUT_BEAM_SIZE", str(VOICE_INPUT_BEAM_SIZE)))
    except Exception:
        value = 3
    return max(1, min(value, 5))


def _requested_prompt() -> str:
    return " ".join(str(os.getenv("VOICE_INPUT_PROMPT", VOICE_INPUT_PROMPT) or "").split()).strip()


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


def _stt_targets() -> tuple[dict, ...]:
    targets = [dict(target) for target in STT_TARGETS if isinstance(target, dict) and target.get("provider")]
    if not targets:
        targets = [
            {"provider": "mlx", "model": _requested_voice_input_model()},
            {"provider": "faster", "model": _requested_faster_whisper_model(), "beam_size": _requested_beam_size()},
        ]

    backend = str(VOICE_INPUT_BACKEND or "auto").strip().lower()
    if backend == "mlx":
        targets = [target for target in targets if _target_provider(target) == "mlx"] + [
            target for target in targets if _target_provider(target) == "faster"
        ]
    elif backend == "faster":
        targets = [target for target in targets if _target_provider(target) == "faster"] or [
            {"provider": "faster", "model": _requested_faster_whisper_model(), "beam_size": _requested_beam_size()}
        ]
    elif backend == "nvidia_riva_asr":
        targets = [target for target in targets if _target_provider(target) == "nvidia_riva_asr"] + [
            target for target in targets if _target_provider(target) != "nvidia_riva_asr"
        ]
    return tuple(_dedupe_targets(targets))


def _riva_asr_available(target: dict) -> bool:
    config = _provider_config(_target_provider(target))
    api_key_env = str(config.get("api_key_env", "") or "").strip()
    if api_key_env and not get_secret(api_key_env, default=""):
        return False
    try:
        import riva.client  # noqa: F401

        return True
    except Exception:
        return False


def _candidate_mlx_model_repos() -> list[str]:
    configured = _requested_voice_input_model()
    candidates: list[str] = []

    def add(repo: str) -> None:
        repo = str(repo or "").strip()
        if repo and repo not in candidates:
            candidates.append(repo)

    if configured:
        if configured.endswith("-mlx"):
            add(configured)
        else:
            model_name = configured.split("/", 1)[-1]
            add(f"mlx-community/{model_name}-mlx")
            if configured.startswith("mlx-community/"):
                add(configured)

    add(DEFAULT_MLX_MODEL)
    return candidates


def _mlx_model_cached(repo: str) -> bool:
    cache_root = (
        Path.home()
        / ".cache"
        / "huggingface"
        / "hub"
        / f"models--{repo.replace('/', '--')}"
    )
    if not cache_root.exists():
        return False

    blobs_dir = cache_root / "blobs"
    if any(path.name.endswith(".incomplete") for path in blobs_dir.glob("*")):
        return False

    snapshots_dir = cache_root / "snapshots"
    for snapshot in snapshots_dir.glob("*"):
        if not snapshot.is_dir():
            continue
        has_config = (snapshot / "config.json").exists()
        has_weights = any(
            any(snapshot.glob(pattern))
            for pattern in ("*.safetensors", "*.npz", "*.bin")
        )
        if has_config and has_weights and sum(1 for _ in snapshot.iterdir()) >= 4:
            return True
    return False


def _load():
    global _MODEL, _BACKEND, _MLX_MODEL_REPO, _ACTIVE_STT_TARGET
    if _MODEL is not None or _BACKEND != "none":
        return _MODEL

    print(f"[STT] Requested model: {_requested_voice_input_model()}")
    for target in _stt_targets():
        provider = _target_provider(target)
        if provider == "nvidia_riva_asr":
            if _riva_asr_available(target):
                _MODEL = object()
                _BACKEND = "nvidia_riva_asr"
                _ACTIVE_STT_TARGET = dict(target)
                print(
                    f"[STT] NVIDIA Riva ASR ready ({target.get('model', '') or 'configured model'}"
                    f", {target.get('language_code', '') or 'default language'})"
                )
                return _MODEL
            continue

        if provider == "mlx":
            for repo in _candidate_mlx_model_repos():
                if not _mlx_model_cached(repo):
                    continue
                try:
                    import mlx_whisper

                    _MODEL = mlx_whisper
                    _BACKEND = "mlx"
                    _MLX_MODEL_REPO = repo
                    _ACTIVE_STT_TARGET = dict(target)
                    print(f"[STT] mlx-whisper loaded (Apple Silicon optimized: {repo})")
                    return _MODEL
                except ImportError:
                    break
            continue

        if provider == "faster":
            try:
                from faster_whisper import WhisperModel

                model_name = str(target.get("model") or _requested_faster_whisper_model()).strip()
                _MODEL = WhisperModel(model_name, device="cpu", compute_type="int8")
                _BACKEND = "faster"
                _ACTIVE_STT_TARGET = dict(target)
                print(f"[STT] faster-whisper loaded (fallback: {model_name})")
                return _MODEL
            except Exception as exc:
                print(f"[STT] faster-whisper unavailable: {exc}")

    print("[STT] No STT model — using text input fallback")
    _MODEL = None
    _BACKEND = "none"
    _ACTIVE_STT_TARGET = {}
    return None


def is_voice_follow_up_available() -> bool:
    try:
        import sounddevice as sd

        return any(device["max_input_channels"] > 0 for device in sd.query_devices())
    except Exception:
        return False


def _audio_to_wav_bytes(audio: np.ndarray) -> bytes:
    source = audio if audio is not None else []
    normalized = np.asarray(source, dtype=np.float32).flatten()
    if normalized.size == 0:
        return b""
    clipped = np.clip(normalized, -1.0, 1.0)
    pcm16 = (clipped * 32767.0).astype(np.int16)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(SAMPLE_RATE)
        handle.writeframes(pcm16.tobytes())
    return buffer.getvalue()


def _transcribe_nvidia_riva(audio: np.ndarray, target: dict) -> str:
    config = _provider_config("nvidia_riva_asr")
    api_key_env = str(config.get("api_key_env", "") or "").strip()
    api_key = get_secret(api_key_env, default="") if api_key_env else ""
    if api_key_env and not api_key:
        return ""

    try:
        import riva.client

        metadata = [("authorization", f"Bearer {api_key}")] if api_key else []
        function_id = str(target.get("function_id", "") or "").strip()
        if function_id:
            metadata.append(("function-id", function_id))

        auth = riva.client.Auth(
            uri=str(config.get("server", "") or "").strip(),
            use_ssl=bool(config.get("use_ssl", True)),
            metadata_args=metadata,
        )
        asr_service = riva.client.ASRService(auth)
        recognition_config = riva.client.RecognitionConfig(
            language_code=str(target.get("language_code", "") or "en-US").strip() or "en-US",
            model=str(target.get("model", "") or "").strip(),
            max_alternatives=1,
            enable_automatic_punctuation=True,
            verbatim_transcripts=True,
        )
        response = asr_service.offline_recognize(_audio_to_wav_bytes(audio), recognition_config)
        transcripts: list[str] = []
        for result in getattr(response, "results", []) or []:
            alternatives = getattr(result, "alternatives", []) or []
            if not alternatives:
                continue
            transcript = str(getattr(alternatives[0], "transcript", "") or "").strip()
            if transcript:
                transcripts.append(transcript)
        return " ".join(transcripts).strip()
    except Exception as exc:
        print(f"[STT] NVIDIA Riva ASR failed: {exc}")
        return ""


def transcribe(audio: np.ndarray) -> str:
    model = _load()
    if model is None:
        return ""

    try:
        if _BACKEND == "nvidia_riva_asr":
            return _transcribe_nvidia_riva(audio, _ACTIVE_STT_TARGET)

        if _BACKEND == "mlx":
            result = model.transcribe(
                audio,
                path_or_hf_repo=_MLX_MODEL_REPO,
                language="en",
            )
            return str(result.get("text", "")).strip()

        if _BACKEND == "faster":
            beam_size = _requested_beam_size()
            segments, _ = model.transcribe(
                audio,
                language="en",
                beam_size=beam_size,
                condition_on_previous_text=False,
                temperature=0.0,
                vad_filter=True,
                initial_prompt=_requested_prompt() or None,
            )
            return " ".join(segment.text for segment in segments).strip()
    except Exception as exc:
        print(f"[STT] Error: {exc}")
    return ""


def warm_stt() -> str:
    _load()
    return _BACKEND


def describe_stt() -> dict:
    active_model = ""
    language_code = str(_ACTIVE_STT_TARGET.get("language_code", "") or "").strip()
    if _BACKEND == "nvidia_riva_asr":
        active_model = str(_ACTIVE_STT_TARGET.get("model", "") or "").strip()
    elif _BACKEND == "mlx":
        active_model = _MLX_MODEL_REPO
    elif _BACKEND == "faster":
        active_model = _requested_faster_whisper_model()

    return {
        "backend": "pending" if _BACKEND == "none" else _BACKEND,
        "requested_model": str(_stt_targets()[0].get("model", "") or _requested_voice_input_model()).strip(),
        "fallback_model": _requested_faster_whisper_model(),
        "active_model": active_model,
        "language_code": language_code,
        "beam_size": _requested_beam_size(),
    }


def _recent_speech_snapshot() -> tuple[str, float]:
    try:
        from .tts import recent_speech_snapshot

        return recent_speech_snapshot()
    except Exception:
        return ("", 0.0)


def _sleep_for_recent_tts(stop_event: threading.Event | None = None) -> None:
    _spoken, spoken_at = _recent_speech_snapshot()
    if spoken_at <= 0:
        return

    remaining = POST_TTS_COOLDOWN_S - (time.monotonic() - spoken_at)
    while remaining > 0:
        if stop_event and stop_event.is_set():
            return
        nap = min(0.05, remaining)
        time.sleep(nap)
        remaining -= nap


def _normalized_tokens(text: str) -> list[str]:
    cleaned = str(text or "").lower()
    cleaned = cleaned.replace("a i", "ai")
    cleaned = cleaned.replace("air news", "ai news")
    cleaned = re.sub(r"[^a-z0-9\s]+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned.split()


def _normalize_transcript(text: str) -> str:
    cleaned = " ".join(str(text or "").split()).strip()
    replacements = (
        (r"\byou\s+do\b", "youtube"),
        (r"\byou\s+tube\b", "youtube"),
        (r"\bu\s*tube\b", "youtube"),
        (r"\bg\s*mail\b", "gmail"),
    )
    for pattern, replacement in replacements:
        cleaned = re.sub(pattern, replacement, cleaned, flags=re.IGNORECASE)
    return cleaned


def _strip_recent_speech_echo(text: str) -> str:
    transcript_tokens = _normalized_tokens(text)
    if not transcript_tokens:
        return ""

    spoken_text, spoken_at = _recent_speech_snapshot()
    if not spoken_text or (time.monotonic() - spoken_at) > RECENT_TTS_WINDOW_S:
        return " ".join(transcript_tokens)

    spoken_tokens = _normalized_tokens(spoken_text)
    overlap = 0
    max_overlap = min(len(spoken_tokens), len(transcript_tokens))
    for size in range(max_overlap, 2, -1):
        if transcript_tokens[:size] == spoken_tokens[-size:] or transcript_tokens[:size] == spoken_tokens[:size]:
            overlap = size
            break

    cleaned_tokens = transcript_tokens[overlap:] if overlap else transcript_tokens
    return " ".join(cleaned_tokens).strip()


def listen(timeout: float = 8.0, stop_event: threading.Event | None = None) -> str:
    try:
        import sounddevice as sd
    except ImportError:
        return input("[You] ").strip()

    if not is_voice_follow_up_available():
        return input("[You] ").strip()
    if stop_event and stop_event.is_set():
        return ""

    _sleep_for_recent_tts(stop_event)
    if stop_event and stop_event.is_set():
        return ""

    chunks: list[float] = []
    speaking = False
    silence_count = 0
    chunk_size = int(SAMPLE_RATE * 0.03)
    silence_needed = int(SILENCE_END_S / 0.03)
    max_chunks = int(STT_MAX_SPEECH_S / 0.03)

    print("[STT] 👂 Listening...")
    start = time.time()

    try:
        with sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="float32",
            blocksize=chunk_size,
        ) as stream:
            while time.time() - start < timeout:
                if stop_event and stop_event.is_set():
                    return ""
                try:
                    chunk, _ = stream.read(chunk_size)
                except Exception as exc:
                    if stop_event and stop_event.is_set():
                        return ""
                    print(f"[STT] Audio stream stopped: {exc}")
                    return ""

                flat = chunk.flatten()
                level = float(np.abs(flat).mean())

                if level > STT_SILENCE_THRESHOLD:
                    speaking = True
                    silence_count = 0
                    chunks.extend(flat.tolist())
                    if len(chunks) > max_chunks * chunk_size:
                        break
                elif speaking:
                    silence_count += 1
                    chunks.extend(flat.tolist())
                    if silence_count >= silence_needed:
                        break
    except Exception as exc:
        if stop_event and stop_event.is_set():
            return ""
        print(f"[STT] Input stream unavailable: {exc}")
        return ""

    if not speaking or not chunks:
        return ""

    audio = np.array(chunks, dtype=np.float32)
    if len(audio) / SAMPLE_RATE < STT_MIN_SPEECH_S:
        return ""

    raw_text = _normalize_transcript(transcribe(audio))
    text = _strip_recent_speech_echo(raw_text)
    if text:
        print(f"[STT] Heard: '{text}'")
    return text


def listen_loop(callback, stop_event: threading.Event | None = None):
    if stop_event is None:
        stop_event = threading.Event()

    _load()
    print("[STT] Continuous listen mode active")
    while not stop_event.is_set():
        text = listen(timeout=10.0, stop_event=stop_event)
        if stop_event.is_set():
            break
        if text and len(text) > 2:
            callback(text)
        time.sleep(0.05)


def listen_for_command(timeout: float = 8.0, stop_event: threading.Event | None = None) -> str:
    return listen(timeout=timeout, stop_event=stop_event)


def listen_continuous(callback, stop_event: threading.Event | None = None):
    listen_loop(callback, stop_event)


def listen_for_follow_up(seconds: float = 4.0) -> str | None:
    text = listen(timeout=seconds)
    return text or None


if __name__ == "__main__":
    _load()
    print("Say something:")
    print(f"Result: '{listen()}'")
