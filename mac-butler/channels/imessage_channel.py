#!/usr/bin/env python3
"""iMessage channel — polls Messages.app for new messages from approved contacts.
Runs as a background daemon. Sends Burry responses back via iMessage.
Stolen from CoPaw's channel abstraction.
"""
from __future__ import annotations

import subprocess
import threading
import time

from runtime.telemetry import note_agent_result as _note_agent

APPROVED_CONTACTS: list[str] = []  # Add your iCloud email(s) e.g. "you@icloud.com"
POLL_INTERVAL = 5  # seconds

_last_seen_id: str | None = None


def _get_latest_message() -> tuple[str, str, str] | None:
    """Get the most recent iMessage received. Returns (id, content, sender) or None."""
    script = '''
    tell application "Messages"
        if (count of chats) > 0 then
            set latestChat to item 1 of chats
            if (count of messages of latestChat) > 0 then
                set latestMsg to item -1 of messages of latestChat
                set msgId to id of latestMsg as string
                set msgContent to content of latestMsg
                set msgHandle to handle of latestMsg
                return msgId & "|||" & msgContent & "|||" & msgHandle
            end if
        end if
        return ""
    end tell
    '''
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=5)
    raw = result.stdout.strip()
    if not raw or "|||" not in raw:
        return None
    parts = raw.split("|||")
    if len(parts) < 3:
        return None
    return parts[0], parts[1], parts[2]  # id, content, sender


def _send_reply(contact: str, message: str) -> None:
    script = f'tell application "Messages" to send "{message}" to buddy "{contact}"'
    subprocess.run(["osascript", "-e", script], timeout=10)


def _poll_loop() -> None:
    global _last_seen_id
    # Lazy import to avoid circular import at startup
    from butler import handle_input

    while True:
        try:
            result = _get_latest_message()
            if result:
                msg_id, content, sender = result
                if msg_id != _last_seen_id and (not APPROVED_CONTACTS or sender in APPROVED_CONTACTS):
                    _last_seen_id = msg_id
                    _note_agent("imessage", "received", f"from {sender}: {content[:50]}")
                    # Process through full Burry pipeline (synchronous)
                    handle_input(content, test_mode=False)
        except Exception:
            pass
        time.sleep(POLL_INTERVAL)


def start_imessage_channel() -> None:
    """Start iMessage polling in background thread."""
    thread = threading.Thread(target=_poll_loop, daemon=True, name="burry-imessage")
    thread.start()
    print("[Channel] iMessage channel started — message Burry from your iPhone")
