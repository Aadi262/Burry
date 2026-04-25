#!/usr/bin/env python3
"""Best-effort recent macOS notification activity for Butler."""

from __future__ import annotations

import re
import subprocess
import threading
import time

from utils import _clip_text, _now_iso

_CACHE_LOCK = threading.Lock()
_CACHE_TTL_SECONDS = 20.0
_CACHE_PAYLOAD: dict | None = None
_CACHE_AT = 0.0

_NOTIFICATION_LOG_PREDICATE = 'process == "usernoted"'
_BUNDLE_RE = re.compile(r"\bbundle=([A-Za-z0-9._-]+)")
_FROM_RE = re.compile(r"\bfrom ([A-Za-z0-9._-]+)")
_TIMESTAMP_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+)")

_BUNDLE_LABELS = {
    "com.apple.MobileSMS": "Messages",
    "com.apple.mail": "Mail",
    "com.apple.mailserviceagent": "Mail",
    "com.apple.MobileMail": "Mail",
    "com.apple.reminders": "Reminders",
    "com.apple.calendar": "Calendar",
    "com.apple.Safari": "Safari",
    "com.google.Chrome": "Google Chrome",
    "com.google.Chrome.framework.AlertNotificationService": "Google Chrome",
    "com.tinyspeck.slackmacgap": "Slack",
    "com.discord": "Discord",
    "com.hnc.Discord": "Discord",
    "ru.keepcoder.Telegram": "Telegram",
    "com.tdesktop.Telegram": "Telegram",
    "com.spotify.client": "Spotify",
    "company.thebrowser.Browser": "Arc",
    "md.obsidian": "Obsidian",
    "com.openai.chat": "ChatGPT",
    "com.anthropic.claudedesktop": "Claude",
}


def _bundle_label(bundle: str) -> str:
    cleaned = str(bundle or "").strip()
    if not cleaned:
        return "Notification"
    if cleaned in _BUNDLE_LABELS:
        return _BUNDLE_LABELS[cleaned]

    stripped = cleaned.replace(".framework.AlertNotificationService", "")
    if stripped in _BUNDLE_LABELS:
        return _BUNDLE_LABELS[stripped]

    leaf = stripped.split(".")[-1]
    leaf = re.sub(r"(?<!^)([A-Z])", r" \1", leaf).strip()
    return leaf or stripped or "Notification"


def _status_from_line(line: str) -> str:
    lowered = line.lower()
    if "expired" in lowered:
        return "expired"
    if "_removedelivered" in lowered or "_removedisplayed" in lowered or "delete" in lowered:
        return "removed"
    if "request uuid:" in lowered or "enqueueing" in lowered:
        return "active"
    return "activity"


def _extract_bundle(line: str) -> str:
    for pattern in (_BUNDLE_RE, _FROM_RE):
        match = pattern.search(line)
        if match:
            return match.group(1).strip()
    return ""


def _parse_notification_lines(output: str, *, limit: int = 6) -> list[dict]:
    items: list[dict] = []
    seen: set[tuple[str, str, str]] = set()

    for raw_line in str(output or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        bundle = _extract_bundle(line)
        if not bundle:
            continue
        status = _status_from_line(line)
        timestamp_match = _TIMESTAMP_RE.match(line)
        at = timestamp_match.group(1) if timestamp_match else _now_iso()
        item = {
            "app": _bundle_label(bundle),
            "bundle": _clip_text(bundle, limit=120),
            "status": status,
            "source": "usernoted_log",
            "summary": _clip_text(f"{_bundle_label(bundle)} notification {status}", limit=120),
            "detail": _clip_text("Notification content is hidden by macOS log privacy on this path.", limit=180),
            "at": _clip_text(at, limit=40),
        }
        signature = (item["bundle"], item["status"], item["at"])
        if signature in seen:
            continue
        seen.add(signature)
        items.append(item)
        if len(items) >= max(1, int(limit or 1)):
            break
    return items


def read_recent_notifications(*, lookback: str = "8m", limit: int = 6, force_refresh: bool = False) -> dict:
    global _CACHE_AT, _CACHE_PAYLOAD

    now = time.monotonic()
    with _CACHE_LOCK:
        if not force_refresh and _CACHE_PAYLOAD is not None and now - _CACHE_AT <= _CACHE_TTL_SECONDS:
            return dict(_CACHE_PAYLOAD)

    payload = {
        "source": "usernoted_log",
        "status": "unavailable",
        "detail": "Notification activity is not available yet.",
        "items": [],
        "at": _now_iso(),
    }
    try:
        result = subprocess.run(
            [
                "/usr/bin/log",
                "show",
                "--style",
                "compact",
                "--last",
                str(lookback or "8m"),
                "--predicate",
                _NOTIFICATION_LOG_PREDICATE,
            ],
            capture_output=True,
            text=True,
            timeout=6,
            check=False,
        )
        if result.returncode == 0:
            items = _parse_notification_lines(result.stdout or "", limit=limit)
            payload["items"] = items
            payload["status"] = "ok" if items else "idle"
            payload["detail"] = (
                "Recent notification activity from usernoted. Message text may stay private."
                if items
                else "No recent notification activity was found in usernoted."
            )
        else:
            stderr = " ".join(str(result.stderr or "").split())
            if stderr:
                payload["detail"] = _clip_text(stderr, limit=180)
    except Exception as exc:
        payload["detail"] = _clip_text(str(exc), limit=180) or payload["detail"]

    with _CACHE_LOCK:
        _CACHE_PAYLOAD = dict(payload)
        _CACHE_AT = time.monotonic()
    return dict(payload)
