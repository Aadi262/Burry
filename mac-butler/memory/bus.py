"""memory/bus.py — Lightweight memory bus for Burry.

record(event) batches writes to memory/event_log.json via a background thread
that flushes every 2 seconds, replacing the 9+ synchronous per-command writes.

recall(query) returns the 5 most recent relevant entries using keyword matching
(or semantic similarity when nomic-embed-text is available).
"""

from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime
from typing import Any

_LOG_PATH = os.path.join(os.path.dirname(__file__), "event_log.json")
_FLUSH_INTERVAL = 2.0  # seconds between background flushes

# Pending events not yet flushed to disk
_PENDING: list[dict] = []
_LOCK = threading.Lock()
_FLUSH_THREAD: threading.Thread | None = None
_STARTED = False


def _ensure_started() -> None:
    global _FLUSH_THREAD, _STARTED
    if _STARTED:
        return
    _STARTED = True
    _FLUSH_THREAD = threading.Thread(target=_flush_loop, daemon=True, name="burry-mem-bus")
    _FLUSH_THREAD.start()


def _flush_loop() -> None:
    while True:
        time.sleep(_FLUSH_INTERVAL)
        _flush_pending()


def _flush_pending() -> None:
    with _LOCK:
        if not _PENDING:
            return
        batch = list(_PENDING)
        _PENDING.clear()

    # Load existing log
    existing: list[dict] = []
    if os.path.exists(_LOG_PATH):
        try:
            with open(_LOG_PATH, "r", encoding="utf-8") as f:
                existing = json.load(f)
                if not isinstance(existing, list):
                    existing = []
        except Exception:
            existing = []

    existing.extend(batch)
    # Keep last 500 events to prevent unbounded growth
    if len(existing) > 500:
        existing = existing[-500:]

    try:
        with open(_LOG_PATH, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=None, separators=(",", ":"))
    except Exception:
        pass


def record(event: dict[str, Any]) -> None:
    """Queue an event for batched write. Non-blocking — returns immediately.

    Expected keys: text, intent, speech, model, outcome, timestamp.
    Missing keys are filled with defaults.
    """
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return  # Never write during tests

    entry = {
        "text": str(event.get("text", ""))[:200],
        "intent": str(event.get("intent", ""))[:80],
        "speech": str(event.get("speech", ""))[:200],
        "model": str(event.get("model", "")),
        "outcome": str(event.get("outcome", "success")),
        "timestamp": event.get("timestamp") or datetime.now().isoformat(),
    }
    with _LOCK:
        _PENDING.append(entry)
    _ensure_started()


def recall(query: str, n: int = 5) -> list[dict]:
    """Return the n most recent events relevant to query.

    Uses keyword matching by default. Falls back to semantic similarity
    when nomic-embed-text is available.
    """
    # Flush pending so recall sees the latest events
    _flush_pending()

    existing: list[dict] = []
    if os.path.exists(_LOG_PATH):
        try:
            with open(_LOG_PATH, "r", encoding="utf-8") as f:
                existing = json.load(f)
                if not isinstance(existing, list):
                    existing = []
        except Exception:
            return []

    if not existing:
        return []

    # Try semantic similarity first
    try:
        results = _semantic_recall(query, existing, n)
        if results:
            return results
    except Exception:
        pass

    # Keyword fallback
    lowered = query.lower()
    keywords = [w for w in lowered.split() if len(w) > 2]
    scored: list[tuple[int, dict]] = []
    for entry in existing:
        haystack = (
            entry.get("text", "") + " " + entry.get("speech", "") + " " + entry.get("intent", "")
        ).lower()
        score = sum(1 for kw in keywords if kw in haystack)
        if score > 0:
            scored.append((score, entry))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [e for _, e in scored[:n]]


def _semantic_recall(query: str, events: list[dict], n: int) -> list[dict]:
    """Rank events by cosine similarity using nomic-embed-text."""
    import requests

    url = "http://localhost:11434/api/embeddings"

    def embed(text: str) -> list[float]:
        r = requests.post(
            url,
            json={"model": "nomic-embed-text", "prompt": text},
            timeout=5,
        )
        r.raise_for_status()
        return r.json()["embedding"]

    q_vec = embed(query)

    import math

    def cosine(a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        mag_a = math.sqrt(sum(x * x for x in a))
        mag_b = math.sqrt(sum(x * x for x in b))
        if mag_a == 0 or mag_b == 0:
            return 0.0
        return dot / (mag_a * mag_b)

    scored: list[tuple[float, dict]] = []
    for entry in events:
        text = entry.get("text", "") + " " + entry.get("speech", "")
        try:
            vec = embed(text[:300])
            sim = cosine(q_vec, vec)
            scored.append((sim, entry))
        except Exception:
            continue

    scored.sort(key=lambda x: x[0], reverse=True)
    return [e for _, e in scored[:n]]
