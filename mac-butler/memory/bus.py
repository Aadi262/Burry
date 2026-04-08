"""memory/bus.py — Lightweight memory bus for Burry.

record(event) batches events in memory and a background thread appends them
to memory/event_log.jsonl one JSON line at a time — no full file rewrites.

recall(query) reads the last 100 lines and returns the 5 most relevant by
keyword match (or semantic similarity when nomic-embed-text is available).
"""

from __future__ import annotations

import json
import math
import os
import threading
import time
from datetime import datetime
from typing import Any

_LOG_PATH = os.path.join(os.path.dirname(__file__), "event_log.jsonl")
_FLUSH_INTERVAL = 2.0  # seconds between background flushes
_RECALL_LINES = 100    # lines to scan for recall

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

    # Append-only: one JSON line per event — no full file read/write
    try:
        with open(_LOG_PATH, "a", encoding="utf-8") as f:
            for entry in batch:
                f.write(json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n")
    except Exception:
        pass


def record(event: dict[str, Any]) -> None:
    """Queue an event for batched append. Non-blocking — returns immediately.

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

    Reads the last _RECALL_LINES lines of the JSONL log.
    Uses keyword matching; falls back to semantic similarity when available.
    """
    # Flush pending so recall sees the very latest events
    _flush_pending()

    events = _read_tail(_RECALL_LINES)
    if not events:
        return []

    # Try semantic similarity first
    try:
        results = _semantic_recall(query, events, n)
        if results:
            return results
    except Exception:
        pass

    # Keyword fallback
    lowered = query.lower()
    keywords = [w for w in lowered.split() if len(w) > 2]
    scored: list[tuple[int, dict]] = []
    for entry in events:
        haystack = (
            entry.get("text", "") + " " + entry.get("speech", "") + " " + entry.get("intent", "")
        ).lower()
        score = sum(1 for kw in keywords if kw in haystack)
        if score > 0:
            scored.append((score, entry))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [e for _, e in scored[:n]]


def _read_tail(n: int) -> list[dict]:
    """Read the last n lines from the JSONL log without loading the whole file."""
    if not os.path.exists(_LOG_PATH):
        return []
    try:
        with open(_LOG_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()
        tail = lines[-n:] if len(lines) > n else lines
        entries = []
        for line in tail:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except Exception:
                continue
        return entries
    except Exception:
        return []


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

    def cosine(a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        mag_a = math.sqrt(sum(x * x for x in a))
        mag_b = math.sqrt(sum(x * x for x in b))
        if mag_a == 0 or mag_b == 0:
            return 0.0
        return dot / (mag_a * mag_b)

    q_vec = embed(query)
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
