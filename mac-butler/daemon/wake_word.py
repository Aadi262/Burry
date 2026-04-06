#!/usr/bin/env python3
"""Optional wake-word trigger backed by openWakeWord."""

from __future__ import annotations

import importlib
import threading
import time

_WAKE_THREAD: threading.Thread | None = None
_WAKE_LOCK = threading.Lock()
_WAKE_STOP = threading.Event()
_WAKE_THRESHOLD = 0.5
_WAKE_COOLDOWN_SECONDS = 5.0


def _load_dependencies() -> tuple[object, object, object] | None:
    try:
        numpy = importlib.import_module("numpy")
        sounddevice = importlib.import_module("sounddevice")
        model_module = importlib.import_module("openwakeword.model")
    except Exception:
        return None
    model_cls = getattr(model_module, "Model", None)
    if model_cls is None:
        return None
    return numpy, sounddevice, model_cls


def _score_from_prediction(prediction) -> float:
    if isinstance(prediction, dict):
        values = [_score_from_prediction(value) for value in prediction.values()]
        return max(values) if values else 0.0
    if isinstance(prediction, (list, tuple)):
        values = [_score_from_prediction(value) for value in prediction]
        return max(values) if values else 0.0
    try:
        return float(prediction)
    except Exception:
        return 0.0


def _wake_word_loop(on_detect) -> None:
    deps = _load_dependencies()
    if deps is None:
        return

    numpy, sounddevice, model_cls = deps
    last_triggered_at = 0.0
    try:
        model = model_cls()
    except Exception:
        return

    def callback(indata, _frames, _time_info, _status) -> None:
        nonlocal last_triggered_at
        if _WAKE_STOP.is_set():
            return
        try:
            samples = numpy.asarray(indata[:, 0], dtype=numpy.float32)
            audio = (samples * 32767).astype(numpy.int16)
            prediction = model.predict(audio)
            score = _score_from_prediction(prediction)
        except Exception:
            return
        now = time.monotonic()
        if score < _WAKE_THRESHOLD or now - last_triggered_at < _WAKE_COOLDOWN_SECONDS:
            return
        last_triggered_at = now
        threading.Thread(target=on_detect, daemon=True).start()

    try:
        with sounddevice.InputStream(
            samplerate=16000,
            channels=1,
            blocksize=1280,
            dtype="float32",
            callback=callback,
        ):
            while not _WAKE_STOP.is_set():
                time.sleep(0.1)
    except Exception:
        return


def start_wake_word_daemon():
    deps = _load_dependencies()
    if deps is None:
        return None

    with _WAKE_LOCK:
        global _WAKE_THREAD
        if _WAKE_THREAD is not None and _WAKE_THREAD.is_alive():
            return _WAKE_THREAD
        _WAKE_STOP.clear()
        try:
            from trigger import on_trigger
        except Exception:
            return None
        _WAKE_THREAD = threading.Thread(
            target=_wake_word_loop,
            args=(on_trigger,),
            daemon=True,
            name="burry-wake-word",
        )
        _WAKE_THREAD.start()
        return _WAKE_THREAD


__all__ = ["start_wake_word_daemon"]
