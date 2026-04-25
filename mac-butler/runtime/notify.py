#!/usr/bin/env python3
"""Small macOS notification helper for Burry."""

from __future__ import annotations

import json
import subprocess

try:
    from .telemetry import note_notification
except Exception:
    try:
        from runtime.telemetry import note_notification
    except Exception:
        def note_notification(*_args, **_kwargs) -> None:
            return None


def notify(title: str, message: str, subtitle: str = "Burry OS") -> None:
    status = "sent"
    try:
        result = subprocess.run(
            [
                "osascript",
                "-e",
                (
                    f"display notification {json.dumps(str(message or ''))} "
                    f"with title {json.dumps(str(title or 'Burry'))} "
                    f"subtitle {json.dumps(str(subtitle or 'Burry OS'))}"
                ),
            ],
            capture_output=True,
            timeout=3,
        )
        if int(getattr(result, "returncode", 1) or 0) != 0:
            status = "failed"
    except Exception:
        status = "failed"
    finally:
        try:
            note_notification(
                str(title or "Burry"),
                str(message or ""),
                subtitle=str(subtitle or "Burry OS"),
                source="butler",
                app="Burry",
                status=status,
            )
        except Exception:
            pass
