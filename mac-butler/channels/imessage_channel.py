#!/usr/bin/env python3
"""iMessage channel — polls Messages.app for new messages from approved contacts.
Runs as a background daemon. Sends Burry responses back via iMessage.
Stolen from CoPaw's channel abstraction.
"""
from __future__ import annotations

import os
import re
import sqlite3
import subprocess
import threading
import time
from pathlib import Path

from runtime.telemetry import note_agent_result as _note_agent

APPROVED_CONTACTS: list[str] = []  # Add your iCloud email(s) e.g. "you@icloud.com"
POLL_INTERVAL = 5  # seconds
MESSAGES_DB_PATH = Path.home() / "Library" / "Messages" / "chat.db"

_last_seen_id: str | None = None
_last_outbound_message = ""
_last_receive_diagnostic = ""


def _set_receive_diagnostic(message: str) -> None:
    global _last_receive_diagnostic
    _last_receive_diagnostic = " ".join(str(message or "").split()).strip()


def get_last_receive_diagnostic() -> str:
    return _last_receive_diagnostic


def _approved_contacts() -> list[str]:
    raw = os.environ.get("BURRY_IMESSAGE_APPROVED", "").strip()
    if raw:
        return [item.strip() for item in raw.split(",") if item.strip()]
    return list(APPROVED_CONTACTS)


def _normalize_contact(value: str) -> str:
    text = " ".join(str(value or "").split()).strip()
    if not text:
        return ""
    if text.startswith("participant id "):
        text = text[len("participant id "):].strip()
    if text.startswith("any;-;"):
        text = text.split("any;-;", 1)[1]
    if ":" in text and "@" not in text:
        left, right = text.rsplit(":", 1)
        if re.fullmatch(r"[0-9A-F-]{8,}", left, flags=re.IGNORECASE):
            text = right
    lowered = text.lower()
    if "@" in lowered:
        return lowered
    digits = re.sub(r"[^\d+]", "", text)
    if digits.startswith("00"):
        digits = "+" + digits[2:]
    if digits and not digits.startswith("+"):
        digits = "+" + re.sub(r"\D", "", digits)
    return digits or lowered


def _sender_is_approved(sender: str) -> bool:
    approved = _approved_contacts()
    if not approved:
        return True
    normalized_sender = _normalize_contact(sender)
    normalized_approved = {
        _normalize_contact(contact)
        for contact in approved
        if _normalize_contact(contact)
    }
    raw_approved = {contact.strip() for contact in approved if contact.strip()}
    return sender in raw_approved or normalized_sender in normalized_approved


def _osascript_literal(value: str) -> str:
    return str(value or "").replace("\\", "\\\\").replace('"', '\\"')


def _get_latest_message_from_db() -> tuple[str, str, str] | None:
    """Read the latest inbound text message from the local Messages database."""
    if not MESSAGES_DB_PATH.exists():
        _set_receive_diagnostic(f"missing_db:{MESSAGES_DB_PATH}")
        return None

    query = """
        select
            message.ROWID as message_id,
            coalesce(handle.id, '') as sender,
            coalesce(message.text, '') as content
        from message
        left join handle on handle.ROWID = message.handle_id
        where ifnull(message.is_from_me, 0) = 0
          and trim(coalesce(message.text, '')) <> ''
        order by message.date desc
        limit 1
    """
    try:
        conn = sqlite3.connect(f"file:{MESSAGES_DB_PATH}?mode=ro", uri=True)
        try:
            row = conn.execute(query).fetchone()
        finally:
            conn.close()
    except sqlite3.Error as exc:
        _set_receive_diagnostic(f"db_error:{exc}")
        return None

    if not row:
        _set_receive_diagnostic("db_empty")
        return None

    message_id = str(row[0] or "").strip()
    content = str(row[2] or "").strip()
    sender = str(row[1] or "").strip()
    if not message_id or not content:
        _set_receive_diagnostic("db_missing_fields")
        return None
    _set_receive_diagnostic(f"db_ok:{message_id}:{_normalize_contact(sender)}")
    return message_id, content, sender


def _get_latest_message_from_applescript() -> tuple[str, str, str] | None:
    """Fallback probe. Modern Messages builds often do not expose message history reliably."""
    try:
        result = subprocess.run(
            ["osascript", "-e", 'tell application "Messages" to return participants of first chat'],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception as exc:
        _set_receive_diagnostic(f"osascript_error:{exc}")
        return None

    raw = " ".join((result.stdout or "").split()).strip()
    if result.returncode != 0:
        _set_receive_diagnostic(f"osascript_failed:{(result.stderr or '').strip()}")
        return None
    if not raw:
        _set_receive_diagnostic("osascript_empty")
        return None
    _set_receive_diagnostic(f"osascript_unusable:{raw[:120]}")
    return None


def _get_latest_message() -> tuple[str, str, str] | None:
    """Get the most recent iMessage received. Returns (id, content, sender) or None."""
    result = _get_latest_message_from_db()
    if result:
        return result
    return _get_latest_message_from_applescript()


def _send_reply(contact: str, message: str) -> None:
    global _last_outbound_message
    safe_contact = _osascript_literal(_normalize_contact(contact) or contact)
    safe_message = _osascript_literal(message)
    _last_outbound_message = " ".join(str(message or "").split()).strip()
    script = f'tell application "Messages" to send "{safe_message}" to buddy "{safe_contact}"'
    subprocess.run(["osascript", "-e", script], timeout=10)


def _latest_recorded_timestamp() -> str:
    try:
        from memory.store import load_recent_sessions
    except Exception:
        return ""

    latest = load_recent_sessions(1)
    if not latest:
        return ""
    return str(latest[0].get("timestamp", "")).strip()


def _latest_reply_after(timestamp: str) -> str:
    try:
        from memory.store import load_recent_sessions
    except Exception:
        return ""

    latest = load_recent_sessions(1)
    if not latest:
        return ""
    entry = latest[0] if isinstance(latest[0], dict) else {}
    latest_timestamp = str(entry.get("timestamp", "")).strip()
    if not latest_timestamp or latest_timestamp == timestamp:
        return ""
    return " ".join(str(entry.get("speech", "")).split()).strip()


def _process_latest_message(handle_input_func) -> None:
    global _last_seen_id
    result = _get_latest_message()
    if not result:
        return

    msg_id, content, sender = result
    normalized_content = " ".join(str(content or "").split()).strip()

    if not msg_id or msg_id == _last_seen_id:
        return
    if not _sender_is_approved(sender):
        _set_receive_diagnostic(f"sender_not_approved:{sender}")
        return
    if normalized_content and normalized_content == _last_outbound_message:
        _last_seen_id = msg_id
        return

    before_timestamp = _latest_recorded_timestamp()
    _last_seen_id = msg_id
    _note_agent("imessage", "received", f"from {sender}: {normalized_content[:50]}")
    handle_input_func(content, test_mode=False)
    reply = _latest_reply_after(before_timestamp)
    if reply and sender:
        _send_reply(sender, reply)


def _poll_loop() -> None:
    # Lazy import to avoid circular import at startup
    from butler import handle_input

    while True:
        try:
            _process_latest_message(handle_input)
        except Exception:
            pass
        time.sleep(POLL_INTERVAL)


def start_imessage_channel() -> None:
    """Start iMessage polling in background thread."""
    thread = threading.Thread(target=_poll_loop, daemon=True, name="burry-imessage")
    thread.start()
    print("[Channel] iMessage channel started — message Burry from your iPhone")
