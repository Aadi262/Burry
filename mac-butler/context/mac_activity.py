#!/usr/bin/env python3
"""
context/mac_activity.py
Passive Mac activity watcher.
Runs in background, polls every 10s.
Writes to memory/mac_state.json so Butler knows what you're doing.
"""

from __future__ import annotations

import json
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote

try:
    from runtime import note_notifications, note_workspace_context
except Exception:
    def note_workspace_context(*_args, **_kwargs) -> None:
        return None
    def note_notifications(*_args, **_kwargs) -> None:
        return None

STATE_FILE = Path(__file__).resolve().parent.parent / "memory" / "mac_state.json"
_WATCHER_THREAD: threading.Thread | None = None
_WATCHER_LOCK = threading.Lock()


def _run_script(script: str) -> str:
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return (result.stdout or "").strip()
    except Exception:
        return ""


def get_frontmost_app() -> str:
    return _run_script(
        'tell application "System Events" to '
        'set frontApp to name of first application process '
        'whose frontmost is true'
    )


def get_open_apps() -> list[str]:
    raw = _run_script(
        'tell application "System Events" to '
        'get name of every application process '
        'whose background only is false'
    )
    return [app.strip() for app in raw.split(",") if app.strip()]


def get_open_windows() -> list[str]:
    raw = _run_script(
        'tell application "System Events" to tell '
        '(first application process whose frontmost is true) '
        'to get name of every window'
    )
    return [window.strip() for window in raw.split(",") if window.strip()]


def get_cursor_workspace() -> str:
    """Read the most recent Cursor or VS Code workspace from workspaceStorage."""
    paths = [
        "~/Library/Application Support/Cursor/User/workspaceStorage",
        "~/Library/Application Support/Code/User/workspaceStorage",
    ]
    for path_text in paths:
        expanded = Path(path_text).expanduser()
        if not expanded.exists():
            continue

        workspaces = sorted(
            expanded.glob("*/workspace.json"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
        for workspace in workspaces[:3]:
            try:
                data = json.loads(workspace.read_text(encoding="utf-8"))
            except Exception:
                continue
            folder = str(data.get("folder", "")).strip()
            if folder:
                return unquote(folder.replace("file://", ""))

    try:
        from .vscode_context import get_vscode_context
    except Exception:
        try:
            from context.vscode_context import get_vscode_context
        except Exception:
            return ""

    editor_data = get_vscode_context()
    for workspace_path in editor_data.get("workspace_paths", []):
        if workspace_path:
            return workspace_path
    return ""


def _tracked_projects() -> list[dict]:
    try:
        from projects.project_store import load_projects
    except Exception:
        try:
            from project_store import load_projects
        except Exception:
            return []
    try:
        projects = load_projects() or []
    except Exception:
        return []
    return [item for item in projects if isinstance(item, dict)]


def _workspace_project_name(workspace: str, projects: list[dict]) -> str:
    candidate = str(workspace or "").strip()
    if not candidate:
        return ""
    try:
        candidate_path = Path(candidate).expanduser().resolve(strict=False)
    except Exception:
        return Path(candidate).name or candidate

    best: tuple[int, str] | None = None
    for project in projects:
        try:
            root = Path(str(project.get("path", "") or "")).expanduser().resolve(strict=False)
        except Exception:
            continue
        if not str(root).strip():
            continue
        try:
            if candidate_path == root or root in candidate_path.parents:
                score = len(str(root))
                name = str(project.get("name", "") or "").strip()
                if name and (best is None or score > best[0]):
                    best = (score, name)
        except Exception:
            continue
    return best[1] if best else (candidate_path.name or candidate)


def _browser_project_name(browser_url: str, projects: list[dict]) -> str:
    cleaned = str(browser_url or "").strip().lower()
    if not cleaned:
        return ""
    for project in projects:
        repo = str(project.get("repo", "") or "").strip().lower()
        if repo and f"github.com/{repo}" in cleaned:
            return str(project.get("name", "") or "").strip()
    return ""


def get_spotify_track() -> str:
    track = _run_script(
        'tell application "Spotify" to '
        'if player state is playing then '
        'return name of current track & " by " & '
        'artist of current track end if'
    )
    return track or ""


def get_active_browser_url() -> str:
    for script in (
        'tell application "Google Chrome" to get URL of active tab of front window',
        'tell application "Safari" to get URL of front document',
    ):
        result = _run_script(script)
        if result.startswith("http"):
            return result
    return ""


def snapshot() -> dict:
    try:
        from .notifications import read_recent_notifications
    except Exception:
        try:
            from context.notifications import read_recent_notifications
        except Exception:
            read_recent_notifications = lambda **_kwargs: {"status": "unavailable", "detail": "", "items": [], "source": "", "at": ""}
    return {
        "timestamp": datetime.now().isoformat(),
        "frontmost_app": get_frontmost_app(),
        "open_windows": get_open_windows()[:10],
        "open_apps": get_open_apps()[:10],
        "cursor_workspace": get_cursor_workspace(),
        "spotify_track": get_spotify_track(),
        "browser_url": get_active_browser_url(),
        "notifications": read_recent_notifications(limit=6),
    }


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _focus_project_name(state: dict) -> str:
    projects = _tracked_projects()
    workspace = str(state.get("cursor_workspace", "") or "").strip()
    if workspace:
        return _workspace_project_name(workspace, projects)
    browser_url = str(state.get("browser_url", "") or "").strip()
    if browser_url:
        return _browser_project_name(browser_url, projects) or browser_url
    return ""


def _bridge_runtime_workspace(state: dict) -> None:
    note_workspace_context(
        focus_project=_focus_project_name(state),
        frontmost_app=str(state.get("frontmost_app", "") or "").strip(),
        workspace=str(state.get("cursor_workspace", "") or "").strip(),
    )
    notifications = state.get("notifications") if isinstance(state.get("notifications"), dict) else {}
    note_notifications(
        list(notifications.get("items") or []),
        source=str(notifications.get("source", "") or "system_log"),
        status=str(notifications.get("status", "") or "unavailable"),
        detail=str(notifications.get("detail", "") or ""),
    )


def load_state() -> dict:
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def get_state_for_context() -> str:
    state = load_state()
    if not state:
        return ""

    lines = ["[MAC ACTIVITY]"]
    if state.get("frontmost_app"):
        lines.append(f"  Last active app: {state['frontmost_app']}")
    if state.get("open_windows"):
        lines.append(f"  Windows: {', '.join(state['open_windows'][:3])}")
    if state.get("cursor_workspace"):
        lines.append(f"  Last workspace: {state['cursor_workspace']}")
    if state.get("spotify_track"):
        lines.append(f"  Playing: {state['spotify_track']}")
    if state.get("browser_url"):
        url = state["browser_url"]
        lowered = url.lower()
        if "netflix" in lowered:
            lines.append("  Browser: Netflix")
        elif "github" in lowered:
            lines.append(f"  Browser: GitHub — {url}")
        else:
            lines.append(f"  Browser: {url[:60]}")

    apps = state.get("open_apps", [])
    relevant = [
        app
        for app in apps
        if app
        in {
            "Cursor",
            "Code",
            "Terminal",
            "Obsidian",
            "Spotify",
            "Claude",
            "Slack",
            "Discord",
        }
    ]
    if relevant:
        lines.append(f"  Open: {', '.join(relevant)}")

    notifications = state.get("notifications") if isinstance(state.get("notifications"), dict) else {}
    recent_notifications = [
        item
        for item in list(notifications.get("items") or [])[:3]
        if isinstance(item, dict)
    ]
    if recent_notifications:
        rendered = []
        for item in recent_notifications:
            label = str(item.get("app", "") or item.get("bundle", "") or "Notification").strip()
            status = str(item.get("status", "") or "activity").strip()
            summary = str(item.get("message", "") or item.get("summary", "") or "").strip()
            line = f"{label} ({status})"
            if summary:
                line = f"{line}: {summary}"
            rendered.append(line)
        lines.append(f"  Notifications: {' | '.join(rendered)}")

    return "\n".join(lines)


def start_watcher(interval: int = 10) -> threading.Thread:
    """Start the background watcher once and return the watcher thread."""
    global _WATCHER_THREAD
    with _WATCHER_LOCK:
        if _WATCHER_THREAD and _WATCHER_THREAD.is_alive():
            return _WATCHER_THREAD

        def _loop() -> None:
            while True:
                try:
                    state = snapshot()
                    save_state(state)
                    _bridge_runtime_workspace(state)
                except Exception:
                    pass
                time.sleep(interval)

        _WATCHER_THREAD = threading.Thread(
            target=_loop,
            daemon=True,
            name="mac-watcher",
        )
        _WATCHER_THREAD.start()
        print(f"[Watcher] Mac activity watcher started (every {interval}s)")
        return _WATCHER_THREAD


if __name__ == "__main__":
    print("Current Mac state:")
    current_state = snapshot()
    print(json.dumps(current_state, indent=2))
    print("\nContext block:")
    save_state(current_state)
    print(get_state_for_context())
