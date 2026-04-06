#!/usr/bin/env python3
"""Open a known project in the first available editor."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

try:
    from .project_store import ensure_project_blurb, get_project, mark_error, set_last_opened
except ImportError:
    from project_store import ensure_project_blurb, get_project, mark_error, set_last_opened

EDITOR_CHAIN = [
    ("claude", lambda p: f"claude '{p}'"),
    ("codex", lambda p: f"codex '{p}'"),
    ("cursor", lambda p: f"cursor '{p}'"),
    ("code", lambda p: f"code '{p}'"),
]

ANTIGRAVITY_APP_CANDIDATES = [
    Path("/Applications/Antigravity.app"),
    Path.home() / "Applications" / "Antigravity.app",
]
CURSOR_APP_CANDIDATES = [
    Path("/Applications/Cursor.app"),
    Path.home() / "Applications" / "Cursor.app",
]
VSCODE_APP_CANDIDATES = [
    Path("/Applications/Visual Studio Code.app"),
    Path("/Applications/Code.app"),
    Path.home() / "Applications" / "Visual Studio Code.app",
    Path.home() / "Applications" / "Code.app",
]
CURSOR_CLI_CANDIDATES = [
    Path("/Applications/Cursor.app/Contents/Resources/app/bin/cursor"),
    Path.home() / "Applications" / "Cursor.app" / "Contents" / "Resources" / "app" / "bin" / "cursor",
]
VSCODE_CLI_CANDIDATES = [
    Path("/Applications/Visual Studio Code.app/Contents/Resources/app/bin/code"),
    Path("/Applications/Code.app/Contents/Resources/app/bin/code"),
    Path.home() / "Applications" / "Visual Studio Code.app" / "Contents" / "Resources" / "app" / "bin" / "code",
    Path.home() / "Applications" / "Code.app" / "Contents" / "Resources" / "app" / "bin" / "code",
]
ANTIGRAVITY_CLI_CANDIDATES = [
    Path.home() / ".antigravity" / "antigravity" / "bin" / "antigravity",
]


def _app_exists(name: str) -> bool:
    """Check if CLI tool is available in PATH."""
    import shutil

    return shutil.which(name) is not None


def _first_existing_path(candidates: list[Path]) -> str | None:
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return None


def _launch(command: list[str]) -> None:
    subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def _open_in_terminal(tool_name: str, path: str) -> None:
    quoted_path = "'" + path.replace("'", "'\\''") + "'"
    script = (
        'tell application "Terminal"\n'
        "    activate\n"
        f'    do script "cd {quoted_path} && {tool_name}"\n'
        "end tell"
    )
    _launch(["osascript", "-e", script])


def _launch_antigravity(path: str) -> bool:
    cli = _first_existing_path(ANTIGRAVITY_CLI_CANDIDATES)
    if cli:
        _launch([cli, path])
        return True
    if any(candidate.exists() for candidate in ANTIGRAVITY_APP_CANDIDATES):
        _launch(["open", "-a", "Antigravity", path])
        return True
    return False


def _launch_cursor(path: str) -> bool:
    cli = _first_existing_path(CURSOR_CLI_CANDIDATES)
    if cli:
        _launch([cli, path])
        return True
    if any(candidate.exists() for candidate in CURSOR_APP_CANDIDATES):
        _launch(["open", "-a", "Cursor", path])
        return True
    return False


def _launch_vscode(path: str) -> bool:
    cli = _first_existing_path(VSCODE_CLI_CANDIDATES)
    if cli:
        _launch([cli, path])
        return True
    if any(candidate.exists() for candidate in VSCODE_APP_CANDIDATES):
        app_name = "Visual Studio Code" if Path("/Applications/Visual Studio Code.app").exists() else "Code"
        _launch(["open", "-a", app_name, path])
        return True
    return False


def _launch_claude(path: str) -> bool:
    if _app_exists("claude"):
        _open_in_terminal("claude", path)
        return True
    return False


def _launch_codex(path: str) -> bool:
    if _app_exists("codex"):
        _open_in_terminal("codex", path)
        return True
    return False


def _editor_launchers() -> list[tuple[str, callable]]:
    return [
        ("antigravity", _launch_antigravity),
        ("cursor", _launch_cursor),
        ("code", _launch_vscode),
        ("claude", _launch_claude),
        ("codex", _launch_codex),
    ]


def open_project_by_path(path: str) -> dict:
    """Same chain but takes a direct path."""
    expanded = os.path.expanduser(path)
    if not os.path.exists(expanded):
        return {
            "status": "error",
            "editor_used": None,
            "project_name": None,
            "path": expanded,
        }

    for editor_name, launcher in _editor_launchers():
        try:
            if not launcher(expanded):
                continue
            return {
                "status": "ok",
                "editor_used": editor_name,
                "project_name": os.path.basename(expanded.rstrip("/")) or expanded,
                "path": expanded,
            }
        except Exception:
            continue

    try:
        subprocess.Popen(
            ["open", expanded],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return {
            "status": "ok",
            "editor_used": "finder",
            "project_name": os.path.basename(expanded.rstrip("/")) or expanded,
            "path": expanded,
        }
    except Exception:
        return {
            "status": "error",
            "editor_used": None,
            "project_name": os.path.basename(expanded.rstrip("/")) or expanded,
            "path": expanded,
        }


def open_project(name: str) -> dict:
    """
    Find project by name (fuzzy), try editors in order.
    Returns: {status, editor_used, project_name, path}

    Also calls set_last_opened() on success.
    Falls back down the chain if app not found.
    If all fail, opens in Finder as last resort.
    """
    project = get_project(name, hydrate_blurb=True)
    if not project:
        return {
            "status": "error",
            "editor_used": None,
            "project_name": None,
            "path": None,
        }

    result = open_project_by_path(project.get("path", ""))
    result["project_name"] = project.get("name")

    if result.get("status") == "ok":
        set_last_opened(project["name"])
        try:
            ensure_project_blurb(project["name"])
        except Exception:
            pass
        return result

    mark_error(project["name"], f"Could not open project: {project.get('path', '')}")
    return result


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python projects/open_project.py <project-name>")
        raise SystemExit(1)
    print(open_project(sys.argv[1]))
