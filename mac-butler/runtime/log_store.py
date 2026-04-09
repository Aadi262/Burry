#!/usr/bin/env python3
"""Persistent JSONL logs for runtime events and trace spans."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from uuid import uuid4

from utils import _now_iso

LOGS_ROOT = Path(__file__).resolve().parent.parent / "memory" / "logs"
RUNTIME_EVENT_LOG_PATH = LOGS_ROOT / "runtime_events.jsonl"
TRACE_LOG_PATH = LOGS_ROOT / "traces.jsonl"
_LOG_LOCK = threading.Lock()


def _append_jsonl(path: Path, payload: dict) -> None:
    if not isinstance(payload, dict):
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(payload, ensure_ascii=True) + "\n"
    with _LOG_LOCK:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line)


def _load_recent_jsonl(path: Path, limit: int = 50) -> list[dict]:
    safe_limit = max(1, min(200, int(limit or 50)))
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return []

    items: list[dict] = []
    for line in lines[-safe_limit:]:
        try:
            payload = json.loads(line)
        except Exception:
            continue
        if isinstance(payload, dict):
            items.append(payload)
    return items


def append_runtime_event(kind: str, message: str, metadata: dict | None = None) -> None:
    payload = {
        "id": uuid4().hex,
        "at": _now_iso(),
        "kind": str(kind or "").strip() or "event",
        "message": str(message or "").strip(),
    }
    if isinstance(metadata, dict) and metadata:
        payload["meta"] = metadata
    _append_jsonl(RUNTIME_EVENT_LOG_PATH, payload)


def load_recent_runtime_events(limit: int = 50) -> list[dict]:
    return _load_recent_jsonl(RUNTIME_EVENT_LOG_PATH, limit=limit)


def append_trace_span(payload: dict) -> None:
    body = {
        "id": uuid4().hex,
        "at": _now_iso(),
    }
    if isinstance(payload, dict):
        body.update(payload)
    _append_jsonl(TRACE_LOG_PATH, body)


def load_recent_trace_spans(limit: int = 50) -> list[dict]:
    return _load_recent_jsonl(TRACE_LOG_PATH, limit=limit)
