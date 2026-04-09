#!/usr/bin/env python3
"""Shared live runtime telemetry for Butler and the dashboard."""

from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

from utils import _clip_text, _now_iso

try:
    from .log_store import append_runtime_event
except Exception:  # pragma: no cover - package/script fallback
    from runtime.log_store import append_runtime_event

RUNTIME_STATE_PATH = Path(__file__).resolve().parent.parent / "memory" / "runtime_state.json"
MAX_EVENTS = 18
_RUNTIME_LOCK = threading.Lock()


def _default_metrics(now: str | None = None) -> dict:
    stamp = now or _now_iso()
    return {
        "heard_commands": 0,
        "intents_resolved": 0,
        "spoken_responses": 0,
        "tool_runs_started": 0,
        "tool_runs_completed": 0,
        "tool_run_errors": 0,
        "agent_runs_started": 0,
        "agent_runs_completed": 0,
        "agent_errors": 0,
        "memory_recalls": 0,
        "confirmations_requested": 0,
        "confirmations_resolved": 0,
        "updated_at": stamp,
        "last_reset_at": stamp,
    }


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
        "turns": [],
        "pending_confirmation": {
            "id": "",
            "prompt": "",
            "action": "",
            "status": "",
            "requested_at": "",
            "resolved_at": "",
            "expires_at": "",
        },
        "project_context_hint": {
            "project": "",
            "detail": "",
            "at": "",
        },
        "ambient_context": [],
        "metrics": _default_metrics(now),
        "events": [],
    }
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
    default["turns"] = [
        turn
        for turn in list(default.get("turns") or [])[-6:]
        if isinstance(turn, dict)
    ]
    default["ambient_context"] = [
        _clip_text(item, limit=140)
        for item in list(default.get("ambient_context") or [])[:3]
        if _clip_text(item, limit=140)
    ]
    if not isinstance(default.get("last_intent"), dict):
        default["last_intent"] = _default_runtime_state()["last_intent"]
    if not isinstance(default.get("pending_confirmation"), dict):
        default["pending_confirmation"] = _default_runtime_state()["pending_confirmation"]
    if not isinstance(default.get("project_context_hint"), dict):
        default["project_context_hint"] = _default_runtime_state()["project_context_hint"]
    metrics = default.get("metrics") if isinstance(default.get("metrics"), dict) else {}
    merged_metrics = _default_metrics()
    merged_metrics.update(metrics)
    default["metrics"] = merged_metrics
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
    append_runtime_event(kind, cleaned, metadata)


def _bump_metric(data: dict, name: str, delta: int = 1) -> None:
    metrics = data.get("metrics") if isinstance(data.get("metrics"), dict) else _default_metrics()
    try:
        current = int(metrics.get(name, 0) or 0)
    except Exception:
        current = 0
    metrics[name] = current + int(delta)
    metrics["updated_at"] = _now_iso()
    data["metrics"] = metrics


def load_runtime_state() -> dict:
    with _RUNTIME_LOCK:
        return _load_unlocked()


def load_metrics() -> dict:
    with _RUNTIME_LOCK:
        data = _load_unlocked()
        metrics = data.get("metrics") if isinstance(data.get("metrics"), dict) else {}
        merged = _default_metrics()
        merged.update(metrics)
        return merged


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
        _bump_metric(data, "heard_commands")
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
        _bump_metric(data, "intents_resolved")
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
        _bump_metric(data, "spoken_responses")
        _append_event(data, "spoken", f"Said: {cleaned}")
        _save_unlocked(data)


def note_conversation_turns(turns: list[dict]) -> None:
    cleaned_turns: list[dict] = []
    for turn in list(turns or [])[-6:]:
        if not isinstance(turn, dict):
            continue
        cleaned_turns.append(
            {
                "heard": _clip_text(turn.get("heard", ""), limit=240),
                "intent": _clip_text(turn.get("intent", ""), limit=80),
                "spoken": _clip_text(turn.get("spoken", ""), limit=240),
                "time": _clip_text(turn.get("time", ""), limit=32),
            }
        )
    with _RUNTIME_LOCK:
        data = _load_unlocked()
        data["turns"] = cleaned_turns
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
        if payload["status"] == "start":
            _bump_metric(data, "agent_runs_started")
        elif payload["status"] == "ok":
            _bump_metric(data, "agent_runs_completed")
        elif payload["status"] == "error":
            _bump_metric(data, "agent_errors")
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
        _bump_metric(data, "tool_runs_started")
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
        _bump_metric(data, "tool_runs_completed")
        if payload["status"] not in {"ok", "success", "skipped"}:
            _bump_metric(data, "tool_run_errors")
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
        _bump_metric(data, "memory_recalls")
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


def request_confirmation(prompt: str, action: str = "", timeout_s: int = 30) -> dict:
    requested_at = _now_iso()
    payload = {
        "id": uuid4().hex,
        "prompt": _clip_text(prompt, limit=220),
        "action": _clip_text(action, limit=80),
        "status": "pending",
        "requested_at": requested_at,
        "resolved_at": "",
        "expires_at": (datetime.now() + timedelta(seconds=max(1, timeout_s))).isoformat(timespec="seconds"),
    }
    with _RUNTIME_LOCK:
        data = _load_unlocked()
        data["pending_confirmation"] = payload
        _bump_metric(data, "confirmations_requested")
        _append_event(data, "confirmation", payload["prompt"], {"action": payload["action"], "timeout_s": timeout_s})
        _save_unlocked(data)
    return payload


def resolve_confirmation(request_id: str, status: str) -> None:
    decision = str(status or "").strip().lower()
    if decision not in {"approved", "rejected", "timeout"}:
        return
    with _RUNTIME_LOCK:
        data = _load_unlocked()
        pending = data.get("pending_confirmation") if isinstance(data.get("pending_confirmation"), dict) else {}
        if pending.get("id") != request_id:
            return
        pending["status"] = decision
        pending["resolved_at"] = _now_iso()
        data["pending_confirmation"] = pending
        _bump_metric(data, "confirmations_resolved")
        _append_event(data, "confirmation", f"Confirmation {decision}.", {"action": pending.get("action", "")})
        _save_unlocked(data)


def clear_confirmation(request_id: str = "") -> None:
    with _RUNTIME_LOCK:
        data = _load_unlocked()
        pending = data.get("pending_confirmation") if isinstance(data.get("pending_confirmation"), dict) else {}
        if request_id and pending.get("id") not in {"", request_id}:
            return
        data["pending_confirmation"] = _default_runtime_state()["pending_confirmation"]
        _save_unlocked(data)


def note_project_context_hint(project: str, detail: str) -> None:
    payload = {
        "project": _clip_text(project, limit=80),
        "detail": _clip_text(detail, limit=1200),
        "at": _now_iso(),
    }
    with _RUNTIME_LOCK:
        data = _load_unlocked()
        data["project_context_hint"] = payload
        _append_event(data, "project_context", f"Loaded project memory for {payload['project']}.")
        _save_unlocked(data)


def consume_project_context_hint() -> dict:
    with _RUNTIME_LOCK:
        data = _load_unlocked()
        payload = data.get("project_context_hint") if isinstance(data.get("project_context_hint"), dict) else {}
        data["project_context_hint"] = _default_runtime_state()["project_context_hint"]
        _save_unlocked(data)
    return payload
