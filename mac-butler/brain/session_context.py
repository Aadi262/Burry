"""Shared in-memory session context for pending dialogue and recent turns."""

from __future__ import annotations

from datetime import datetime

from capabilities.contracts import PendingState


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _broadcast_pending(payload: dict) -> None:
    try:
        from runtime import publish_ui_event

        publish_ui_event("pending_update", payload)
    except Exception:
        return


class SessionContext:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.turns: list[dict[str, str]] = []
        self._pending: dict | None = None
        self._broadcast_pending_state()

    def add_user(self, text: str) -> None:
        cleaned = " ".join(str(text or "").split()).strip()
        if not cleaned:
            return
        self.turns.append({"role": "user", "text": cleaned})
        self.turns = self.turns[-12:]

    def add_butler(self, text: str) -> None:
        cleaned = " ".join(str(text or "").split()).strip()
        if not cleaned:
            return
        self.turns.append({"role": "butler", "text": cleaned})
        self.turns = self.turns[-12:]

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
        return self.get_pending()

    def clear_pending(self) -> None:
        self._pending = None
        self._broadcast_pending_state()

    def has_pending(self) -> bool:
        return self._pending is not None


ctx = SessionContext()
