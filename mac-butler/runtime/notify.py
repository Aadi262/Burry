#!/usr/bin/env python3
"""Small macOS notification helper for Burry."""

from __future__ import annotations

import json
import subprocess


def notify(title: str, message: str, subtitle: str = "Burry OS") -> None:
    try:
        subprocess.run(
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
    except Exception:
        pass
