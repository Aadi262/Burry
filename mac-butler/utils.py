#!/usr/bin/env python3
"""Shared lightweight helpers used across Burry runtime modules."""

from __future__ import annotations

import re
from datetime import datetime


def _clip_text(text: str, limit: int = 220) -> str:
    cleaned = " ".join(str(text or "").split()).strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 3].rstrip() + "..."


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(text or "").lower())


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")
