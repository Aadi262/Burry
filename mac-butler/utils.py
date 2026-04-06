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


def _compress_text(raw: str, limit: int = 500, line_limit: int = 75) -> str:
    lines = []
    for line in str(raw or "").split("\n"):
        line = line.strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            lines.append(line)
            continue
        words = line.split()
        if words and len(words[0]) == 7 and all(c in "0123456789abcdef" for c in words[0].lower()):
            msg = " ".join(words[1:])[:55]
            lines.append(f"  commit: {msg}")
            continue
        lines.append(line[:line_limit] + "..." if len(line) > line_limit else line)

    result = "\n".join(lines)
    return result[:limit] + "..." if len(result) > limit else result


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(text or "").lower())


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")
