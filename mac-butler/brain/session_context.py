"""Shared in-memory session context for pending dialogue and recent turns."""

from __future__ import annotations


class SessionContext:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.turns: list[dict[str, str]] = []
        self._pending: dict | None = None

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

    def set_pending(self, kind: str, **metadata) -> None:
        self._pending = {"kind": kind, **metadata}

    def get_pending(self) -> dict | None:
        if self._pending is None:
            return None
        return dict(self._pending)

    def clear_pending(self) -> None:
        self._pending = None

    def has_pending(self) -> bool:
        return self._pending is not None


ctx = SessionContext()
