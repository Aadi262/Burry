#!/usr/bin/env python3
"""Shared live runtime telemetry for Butler and the dashboard."""

from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path

RUNTIME_STATE_PATH = Path(__file__).resolve().parent.parent / "memory" / "runtime_state.json"
MAX_EVENTS = 18
_RUNTIME_LOCK = threading.Lock()


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _default_runtime_state() -> dict:
    now = _now_iso()
    return {
        "updated_at": now,
        "session_active": False,
        "session_changed_at": "",
        "state": "idle",
        "state_changed_at": "",
        "last_heard_text": "",
        "last_heard_at": "",
        "last_intent": {
            "name": "",
            "params": {},
            "confidence": 0.0,
            "raw": "",
            "at": "",
        },
        "last_spoken_text": "",
        "last_spoken_at": "",
        "workspace": {
            "focus_project": "",
            "frontmost_app": "",
            "workspace": "",
            "at": "",
        },
        "last_agent_result": {
            "agent": "",
            "status": "",
            "result": "",
            "at": "",
        },
        "active_tools": [],
        "tool_stream": [],
        "last_memory_recall": {
            "query": "",
            "matches": [],
            "at": "",
        },
        "ambient_context": [],
        "events": [],
    }


def _clip_text(text: str, limit: int = 220) -> str:
    cleaned = " ".join(str(text or "").split()).strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 3].rstrip() + "..."


def _load_unlocked() -> dict:
    if not RUNTIME_STATE_PATH.exists():
        return _default_runtime_state()
    try:
        data = json.loads(RUNTIME_STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return _default_runtime_state()

    default = _default_runtime_state()
    default.update(data if isinstance(data, dict) else {})
    default["events"] = list(default.get("events") or [])[-MAX_EVENTS:]
    default["ambient_context"] = [
        _clip_text(item, limit=140)
        for item in list(default.get("ambient_context") or [])[:3]
        if _clip_text(item, limit=140)
    ]
    if not isinstance(default.get("last_intent"), dict):
        default["last_intent"] = _default_runtime_state()["last_intent"]
    return default


def _save_unlocked(data: dict) -> None:
    RUNTIME_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = _now_iso()
    RUNTIME_STATE_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _append_event(data: dict, kind: str, message: str, metadata: dict | None = None) -> None:
    cleaned = _clip_text(message)
    if not cleaned:
        return
    event = {
        "at": _now_iso(),
        "kind": kind,
        "message": cleaned,
    }
    if metadata:
        event["meta"] = metadata
    events = list(data.get("events") or [])
    events.append(event)
    data["events"] = events[-MAX_EVENTS:]


def load_runtime_state() -> dict:
    with _RUNTIME_LOCK:
        return _load_unlocked()


def note_session_active(active: bool, source: str = "") -> None:
    with _RUNTIME_LOCK:
        data = _load_unlocked()
        data["session_active"] = bool(active)
        data["session_changed_at"] = _now_iso()
        message = "Voice session started." if active else "Voice session ended."
        meta = {"source": source} if source else None
        _append_event(data, "session", message, meta)
        _save_unlocked(data)


def note_state_transition(old_state, new_state) -> None:
    old_value = getattr(old_state, "value", str(old_state or "")).strip() or "unknown"
    new_value = getattr(new_state, "value", str(new_state or "")).strip() or "unknown"
    with _RUNTIME_LOCK:
        data = _load_unlocked()
        data["state"] = new_value
        data["state_changed_at"] = _now_iso()
        _append_event(
            data,
            "state",
            f"{old_value.title()} to {new_value.title()}",
            {"from": old_value, "to": new_value},
        )
        _save_unlocked(data)


def note_heard_text(text: str) -> None:
    cleaned = _clip_text(text, limit=240)
    if not cleaned:
        return
    with _RUNTIME_LOCK:
        data = _load_unlocked()
        data["last_heard_text"] = cleaned
        data["last_heard_at"] = _now_iso()
        _append_event(data, "heard", f"Heard: {cleaned}")
        _save_unlocked(data)


def note_intent(name: str, params: dict | None = None, confidence: float | None = None, raw: str = "") -> None:
    intent_name = str(name or "").strip() or "unknown"
    param_map = params if isinstance(params, dict) else {}
    confidence_value = 0.0
    if confidence is not None:
        try:
            confidence_value = float(confidence)
        except Exception:
            confidence_value = 0.0

    with _RUNTIME_LOCK:
        data = _load_unlocked()
        data["last_intent"] = {
            "name": intent_name,
            "params": param_map,
            "confidence": confidence_value,
            "raw": _clip_text(raw, limit=200),
            "at": _now_iso(),
        }
        _append_event(
            data,
            "intent",
            f"Intent: {intent_name}",
            {
                "confidence": round(confidence_value, 2),
                "params": param_map,
            },
        )
        _save_unlocked(data)


def note_spoken_text(text: str) -> None:
    cleaned = _clip_text(text, limit=240)
    if not cleaned:
        return
    with _RUNTIME_LOCK:
        data = _load_unlocked()
        data["last_spoken_text"] = cleaned
        data["last_spoken_at"] = _now_iso()
        _append_event(data, "spoken", f"Said: {cleaned}")
        _save_unlocked(data)


def note_workspace_context(focus_project: str = "", frontmost_app: str = "", workspace: str = "") -> None:
    payload = {
        "focus_project": _clip_text(focus_project, limit=80),
        "frontmost_app": _clip_text(frontmost_app, limit=80),
        "workspace": _clip_text(workspace, limit=180),
        "at": _now_iso(),
    }
    with _RUNTIME_LOCK:
        data = _load_unlocked()
        current = data.get("workspace") if isinstance(data.get("workspace"), dict) else {}
        if (
            current.get("focus_project", "") == payload["focus_project"]
            and current.get("frontmost_app", "") == payload["frontmost_app"]
            and current.get("workspace", "") == payload["workspace"]
        ):
            return
        data["workspace"] = payload
        _append_event(
            data,
            "workspace",
            f"Workspace: {payload['focus_project'] or 'unknown'} · {payload['frontmost_app'] or 'unknown'}",
            {
                "focus_project": payload["focus_project"],
                "frontmost_app": payload["frontmost_app"],
                "workspace": payload["workspace"],
            },
        )
        _save_unlocked(data)


def note_agent_result(agent: str, status: str, result: str) -> None:
    payload = {
        "agent": _clip_text(agent, limit=40),
        "status": _clip_text(status, limit=20),
        "result": _clip_text(result, limit=240),
        "at": _now_iso(),
    }
    with _RUNTIME_LOCK:
        data = _load_unlocked()
        data["last_agent_result"] = payload
        _append_event(
            data,
            "agent_result",
            f"Agent {payload['agent']}: {payload['result'] or payload['status']}",
            {
                "agent": payload["agent"],
                "status": payload["status"],
            },
        )
        _save_unlocked(data)


def note_tool_started(tool: str, detail: str = "") -> None:
    payload = {
        "tool": _clip_text(tool, limit=48),
        "status": "running",
        "detail": _clip_text(detail, limit=180),
        "at": _now_iso(),
    }
    with _RUNTIME_LOCK:
        data = _load_unlocked()
        active = [str(item).strip() for item in list(data.get("active_tools") or []) if str(item).strip()]
        if payload["tool"] and payload["tool"] not in active:
            active.append(payload["tool"])
        data["active_tools"] = active[:6]
        stream = list(data.get("tool_stream") or [])
        stream.append(payload)
        data["tool_stream"] = stream[-10:]
        _append_event(
            data,
            "tool",
            f"Tool {payload['tool']}: {payload['detail'] or 'running'}",
            {"tool": payload["tool"], "status": payload["status"]},
        )
        _save_unlocked(data)


def note_tool_finished(tool: str, status: str, detail: str = "") -> None:
    payload = {
        "tool": _clip_text(tool, limit=48),
        "status": _clip_text(status or "ok", limit=20),
        "detail": _clip_text(detail, limit=180),
        "at": _now_iso(),
    }
    with _RUNTIME_LOCK:
        data = _load_unlocked()
        active = [str(item).strip() for item in list(data.get("active_tools") or []) if str(item).strip()]
        data["active_tools"] = [item for item in active if item != payload["tool"]][:6]
        stream = list(data.get("tool_stream") or [])
        stream.append(payload)
        data["tool_stream"] = stream[-10:]
        _append_event(
            data,
            "tool",
            f"Tool {payload['tool']}: {payload['detail'] or payload['status']}",
            {"tool": payload["tool"], "status": payload["status"]},
        )
        _save_unlocked(data)


def note_memory_recall(query: str, matches: list[dict] | None = None) -> None:
    query_text = _clip_text(query, limit=120)
    items = []
    for match in list(matches or [])[:3]:
        if not isinstance(match, dict):
            continue
        items.append(
            {
                "timestamp": _clip_text(match.get("timestamp", ""), limit=24),
                "context": _clip_text(match.get("context", ""), limit=120),
                "speech": _clip_text(match.get("speech", ""), limit=140),
                "score": float(match.get("score", 0.0) or 0.0),
            }
        )
    payload = {
        "query": query_text,
        "matches": items,
        "at": _now_iso(),
    }
    with _RUNTIME_LOCK:
        data = _load_unlocked()
        data["last_memory_recall"] = payload
        _append_event(
            data,
            "memory",
            f"Recalled {len(items)} memory matches for {query_text or 'recent context'}",
            {"query": query_text, "count": len(items)},
        )
        _save_unlocked(data)


def note_ambient_context(items: list[str] | None = None) -> None:
    bullets = []
    for item in list(items or [])[:3]:
        cleaned = _clip_text(str(item).lstrip("-*• ").strip(), limit=140)
        if cleaned:
            bullets.append(cleaned)
    if not bullets:
        return
    with _RUNTIME_LOCK:
        data = _load_unlocked()
        data["ambient_context"] = bullets
        _append_event(data, "ambient", "Ambient context refreshed", {"count": len(bullets)})
        _save_unlocked(data)
