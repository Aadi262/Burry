"""Shared in-memory session context for pending dialogue and recent turns."""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime
from pathlib import Path

from capabilities.contracts import PendingState

SESSION_CONTEXT_PATH = Path(__file__).resolve().parent.parent / "memory" / "session_context.json"
SESSION_CONTEXT_MAX_AGE_SECONDS = 6 * 60 * 60
SESSION_CONTEXT_PERSIST_DELAY_SECONDS = 0.15


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _persistence_enabled() -> bool:
    return not bool(os.environ.get("PYTEST_CURRENT_TEST"))


def _snapshot_recent_enough(saved_at: str) -> bool:
    cleaned = str(saved_at or "").strip()
    if not cleaned:
        return False
    try:
        saved_dt = datetime.fromisoformat(cleaned)
    except Exception:
        return False
    age_seconds = max(0.0, (datetime.now() - saved_dt).total_seconds())
    return age_seconds <= SESSION_CONTEXT_MAX_AGE_SECONDS


def _broadcast_pending(payload: dict) -> None:
    try:
        from runtime import publish_ui_event

        publish_ui_event("pending_update", payload)
    except Exception:
        return


class SessionContext:
    def __init__(self) -> None:
        self.turns: list[dict[str, str]] = []
        self._pending: dict | None = None
        self._persist_lock = threading.Lock()
        self._persist_timer: threading.Timer | None = None
        self._restore_from_disk()
        self._broadcast_pending_state()

    def _snapshot(self) -> dict:
        return {
            "turns": [dict(turn) for turn in self.turns[-12:]],
            "pending": dict(self._pending) if isinstance(self._pending, dict) else None,
            "updated_at": _now_iso(),
        }

    def _restore_from_disk(self) -> None:
        if not _persistence_enabled() or not SESSION_CONTEXT_PATH.exists():
            return
        try:
            payload = json.loads(SESSION_CONTEXT_PATH.read_text(encoding="utf-8"))
        except Exception:
            return
        if not isinstance(payload, dict) or not _snapshot_recent_enough(payload.get("updated_at", "")):
            return
        turns = payload.get("turns")
        pending = payload.get("pending")
        if isinstance(turns, list):
            self.turns = [
                {
                    "role": str(item.get("role", "")).strip(),
                    "text": " ".join(str(item.get("text", "")).split()).strip(),
                }
                for item in turns[-12:]
                if isinstance(item, dict) and str(item.get("role", "")).strip() and str(item.get("text", "")).strip()
            ]
        if isinstance(pending, dict):
            self._pending = {
                "kind": str(pending.get("kind", "") or "").strip(),
                "data": dict(pending.get("data") or {}),
                "required": [str(field).strip() for field in list(pending.get("required") or []) if str(field).strip()],
                "created_at": str(pending.get("created_at", "") or _now_iso()),
                "updated_at": str(pending.get("updated_at", "") or _now_iso()),
            }

    def _persist_state(self) -> None:
        if not _persistence_enabled():
            return
        snapshot = self._snapshot()
        SESSION_CONTEXT_PATH.parent.mkdir(parents=True, exist_ok=True)
        SESSION_CONTEXT_PATH.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")

    def _schedule_persist(self) -> None:
        if not _persistence_enabled():
            return
        with self._persist_lock:
            if self._persist_timer is not None:
                self._persist_timer.cancel()
            self._persist_timer = threading.Timer(SESSION_CONTEXT_PERSIST_DELAY_SECONDS, self.persist_now)
            self._persist_timer.daemon = True
            self._persist_timer.start()

    def persist_now(self) -> None:
        with self._persist_lock:
            if self._persist_timer is not None:
                self._persist_timer.cancel()
                self._persist_timer = None
        try:
            self._persist_state()
        except Exception:
            return

    def reset(self, *, persist: bool = True) -> None:
        self.turns: list[dict[str, str]] = []
        self._pending: dict | None = None
        self._broadcast_pending_state()
        if persist:
            self._schedule_persist()

    def add_user(self, text: str) -> None:
        cleaned = " ".join(str(text or "").split()).strip()
        if not cleaned:
            return
        self.turns.append({"role": "user", "text": cleaned})
        self.turns = self.turns[-12:]
        self._schedule_persist()

    def add_butler(self, text: str) -> None:
        cleaned = " ".join(str(text or "").split()).strip()
        if not cleaned:
            return
        self.turns.append({"role": "butler", "text": cleaned})
        self.turns = self.turns[-12:]
        self._schedule_persist()

    def _pending_snapshot(self) -> dict:
        if self._pending is None:
            return {
                "kind": "",
                "data": {},
                "required": [],
                "missing": [],
                "next_field": "",
                "active": False,
                "at": _now_iso(),
            }

        data = dict(self._pending.get("data") or {})
        required = [field for field in list(self._pending.get("required") or []) if str(field).strip()]
        missing = [field for field in required if not str(data.get(field, "") or "").strip()]
        snapshot = {
            "kind": str(self._pending.get("kind", "") or "").strip(),
            "data": data,
            "required": required,
            "missing": missing,
            "next_field": missing[0] if missing else "",
            "active": True,
            "at": str(self._pending.get("updated_at", "") or _now_iso()),
        }
        snapshot.update(data)
        return snapshot

    def _broadcast_pending_state(self) -> None:
        pending = self._pending_snapshot()
        _broadcast_pending(
            PendingState(
                active=bool(pending.get("active")),
                kind=str(pending.get("kind", "") or ""),
                next_field=str(pending.get("next_field", "") or ""),
                missing_fields=[str(field).strip() for field in list(pending.get("missing") or []) if str(field).strip()],
                details=dict(pending.get("data") or {}),
                updated_at=str(pending.get("at", "") or _now_iso()),
            ).to_dict()
        )

    def set_pending(self, kind: str, data: dict | None = None, required: list[str] | None = None, **metadata) -> None:
        payload = {}
        if isinstance(data, dict):
            payload.update(data)
        payload.update(metadata)
        required_fields = [str(field).strip() for field in list(required or []) if str(field).strip()]
        now = _now_iso()
        self._pending = {
            "kind": str(kind or "").strip(),
            "data": payload,
            "required": required_fields,
            "created_at": now,
            "updated_at": now,
        }
        self._broadcast_pending_state()
        self._schedule_persist()

    def get_pending(self) -> dict | None:
        if self._pending is None:
            return None
        return self._pending_snapshot()

    def pending_missing_fields(self) -> list[str]:
        pending = self.get_pending()
        return list(pending.get("missing") or []) if pending else []

    def next_pending_field(self) -> str:
        pending = self.get_pending()
        if not pending:
            return ""
        return str(pending.get("next_field", "") or "").strip()

    def fill_pending(self, value: str, field: str | None = None) -> dict | None:
        if self._pending is None:
            return None
        target = str(field or self.next_pending_field() or "").strip()
        if not target:
            return self.get_pending()
        cleaned = " ".join(str(value or "").split()).strip()
        self._pending.setdefault("data", {})[target] = cleaned
        self._pending["updated_at"] = _now_iso()
        self._broadcast_pending_state()
        self._schedule_persist()
        return self.get_pending()

    def clear_pending(self) -> None:
        self._pending = None
        self._broadcast_pending_state()
        self._schedule_persist()

    def has_pending(self) -> bool:
        return self._pending is not None


ctx = SessionContext()
