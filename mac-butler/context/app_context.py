#!/usr/bin/env python3
"""
app_context.py — Reads frontmost and running macOS apps for Butler.
"""

import subprocess


def _osascript(script: str) -> str:
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=2,
        )
        return (result.stdout or "").strip()
    except Exception:
        return ""


def get_app_context() -> dict:
    frontmost_app = _osascript(
        'tell application "System Events" to get name of first application process whose frontmost is true'
    )

    front_window = ""
    if frontmost_app:
        front_window = _osascript(
            'tell application "System Events"\n'
            f'  tell process "{frontmost_app}"\n'
            "    if (count of windows) > 0 then\n"
            "      get name of front window\n"
            "    end if\n"
            "  end tell\n"
            "end tell"
        )

    running_raw = _osascript(
        'tell application "System Events" to get name of every application process whose background only is false'
    )
    running_apps = [name.strip() for name in running_raw.split(",") if name.strip()]

    return {
        "frontmost_app": frontmost_app,
        "front_window": front_window,
        "running_apps": running_apps[:12],
        "has_data": bool(frontmost_app or running_apps),
    }


if __name__ == "__main__":
    print(get_app_context())
