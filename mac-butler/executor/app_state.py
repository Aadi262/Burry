#!/usr/bin/env python3
"""
executor/app_state.py
Detect running app state before deciding what action to take.
Uses AppleScript via osascript to query macOS directly.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ALWAYS_RUNNING_APPS = {"finder"}


def is_app_running(app_name: str) -> bool:
    """Check if an app process is currently running."""
    normalized_name = app_name.strip().lower()

    # Finder is the macOS shell and is effectively always running on a normal
    # desktop session. Treat it as running when automation APIs are unreliable.
    if normalized_name in ALWAYS_RUNNING_APPS:
        return True

    script = f'''
    tell application "System Events"
        return (name of processes) contains "{app_name}"
    end tell
    '''
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return "true" in (result.stdout or "").lower()
    except Exception:
        pass

    # Some sandboxed shells cannot query System Events reliably, but a direct
    # application-level check still works for normal scriptable apps.
    direct_script = f'application "{app_name}" is running'
    try:
        result = subprocess.run(
            ["osascript", "-e", direct_script],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            output = (result.stdout or "").strip().lower()
            if output in {"true", "false"}:
                return output == "true"
    except Exception:
        pass

    try:
        result = subprocess.run(
            ["pgrep", "-x", app_name],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False


def get_window_count(app_name: str) -> int:
    """Get the number of open windows for an app."""
    script = f'''
    tell application "{app_name}"
        return count of windows
    end tell
    '''
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return int((result.stdout or "0").strip() or "0")
    except Exception:
        return 0


def get_terminal_tab_count() -> int:
    """Get the total number of Terminal tabs across all windows."""
    script = '''
    tell application "Terminal"
        set tabCount to 0
        repeat with w in windows
            set tabCount to tabCount + (count of tabs of w)
        end repeat
        return tabCount
    end tell
    '''
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return int((result.stdout or "0").strip() or "0")
    except Exception:
        return 0


def get_app_state(app_name: str) -> dict:
    """
    Return a state snapshot for an app.
    Example: {"running": True, "window_count": 2, "focused": False}
    """
    running = is_app_running(app_name)
    if not running:
        return {"running": False, "window_count": 0, "focused": False}

    window_count = get_window_count(app_name)
    focus_script = '''
    tell application "System Events"
        return name of first application process whose frontmost is true
    end tell
    '''
    try:
        result = subprocess.run(
            ["osascript", "-e", focus_script],
            capture_output=True,
            text=True,
            timeout=5,
        )
        focused = app_name.lower() in (result.stdout or "").lower()
    except Exception:
        focused = False

    return {
        "running": running,
        "window_count": window_count,
        "focused": focused,
    }


if __name__ == "__main__":
    for app in ["Terminal", "Code", "Cursor", "Spotify"]:
        state = get_app_state(app)
        print(f"{app}: {state}")
