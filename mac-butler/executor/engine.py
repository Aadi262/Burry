#!/usr/bin/env python3
"""
executor/engine.py
App-aware execution engine for Mac Butler.

It distinguishes between:
- opening a fresh app
- focusing an already-running app
- opening a new Terminal tab vs window
- opening editor paths in existing vs new editor windows
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
import threading
import time
import urllib.parse
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Patch PATH so editor CLIs are always found.
EXTRA_PATHS = [
    "/usr/local/bin",
    "/opt/homebrew/bin",
    os.path.expanduser("~/.local/bin"),
    "/Applications/Cursor.app/Contents/Resources/app/bin",
    "/Applications/Visual Studio Code.app/Contents/Resources/app/bin",
]
os.environ["PATH"] = ":".join(EXTRA_PATHS) + ":" + os.environ.get("PATH", "")

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

ALLOWED_COMMANDS = [
    "git",
    "npm",
    "npx",
    "node",
    "python3",
    "pip",
    "pip3",
    "ls",
    "cat",
    "echo",
    "mkdir",
    "touch",
    "cp",
    "mv",
    "open",
    "code",
    "cursor",
    "brew",
    "ollama",
    "systemctl",
    "nginx",
    "pm2",
    "docker",
    "ssh",
    "scp",
    "curl",
    "ping",
    "df",
    "free",
    "uptime",
]

CONFIRM_REQUIRED_PATTERNS = [
    "git push",
    "docker stop",
    "docker rm",
    "docker restart",
    "rm -rf",
    "sudo",
]

try:
    from butler_config import OBSIDIAN_VAULT_NAME, OBSIDIAN_VAULT_PATH

    if OBSIDIAN_VAULT_PATH:
        OBSIDIAN_VAULT = os.path.expanduser(OBSIDIAN_VAULT_PATH)
    else:
        OBSIDIAN_VAULT = os.path.expanduser(
            f"~/Library/Mobile Documents/iCloud~md~obsidian/Documents/{OBSIDIAN_VAULT_NAME}"
        )
except Exception:
    OBSIDIAN_VAULT = ""


class Executor:
    def __init__(self):
        self.results = []

    def run(self, actions: list) -> list:
        self.results = []
        for action in actions:
            try:
                if self._requires_confirmation(action):
                    if not self._ask_confirmation(action):
                        self.results.append(
                            {
                                "action": action.get("type"),
                                "status": "ok",
                                "result": "skipped - user cancelled",
                            }
                        )
                        continue
                result = self._dispatch(action)
                self.results.append(
                    {
                        "action": action.get("type"),
                        "status": "ok",
                        "result": result,
                    }
                )
            except Exception as exc:
                self.results.append(
                    {
                        "action": action.get("type"),
                        "status": "error",
                        "error": str(exc),
                    }
                )
        return self.results

    def _dispatch(self, action: dict) -> str:
        t = action.get("type", "")
        if t == "open_terminal":
            return self.open_terminal(
                action.get("mode", "tab"),
                action.get("cmd", ""),
                action.get("cwd", ""),
            )
        if t == "open_editor":
            return self.open_editor(
                action.get("path", ""),
                action.get("editor", "auto"),
                action.get("mode", "smart"),
            )
        if t == "open_app":
            return self.open_app(
                action["app"],
                action.get("mode", "smart"),
            )
        if t == "open_folder":
            return self.open_folder(action["path"])
        if t == "create_and_open":
            return self.create_and_open(
                action["path"],
                action.get("editor", "auto"),
            )
        if t == "run_command":
            return self.run_command(
                action["cmd"],
                action.get("cwd"),
                action.get("in_terminal", False),
            )
        if t == "play_music":
            return self.play_music(action.get("mode", "focus"))
        if t == "search_and_play":
            return self.search_and_play_spotify(action.get("query", ""))
        if t == "write_file":
            return self.write_file(
                action["path"],
                action["content"],
                action.get("mode", "append"),
            )
        if t == "obsidian_note":
            return self.obsidian_note(
                action["title"],
                action["content"],
                action.get("folder", "Daily"),
            )
        if t == "ssh_open":
            return self.ssh_open(action["host"], action.get("label", "VPS"))
        if t == "ssh_command":
            return self.ssh_command(action["host"], action["cmd"])
        if t == "open_url":
            return self.open_url(action["url"])
        if t == "notify":
            return self.notify(action["title"], action["message"])
        if t == "remind_in":
            return self.remind_in(action["minutes"], action["message"])
        if t == "run_agent":
            return self.run_agent_task(
                action["agent"],
                {k: v for k, v in action.items() if k not in ("type", "agent")},
            )
        if t == "open_project":
            from projects import open_project

            result = open_project(action["name"])
            if result.get("status") != "ok":
                raise RuntimeError(f"could not open project: {action.get('name', '')}")
            return f"opened {result.get('project_name')} in {result.get('editor_used')}"
        if t == "open_dashboard":
            from projects import open_dashboard

            open_dashboard()
            return "opened project dashboard"
        if t == "github_sync":
            from projects import sync_all

            threading.Thread(target=sync_all, daemon=True).start()
            return "started github sync"
        if t == "speak_only":
            return "speech only"

        # Compatibility shims for older deterministic routes.
        if t == "quit_app":
            return self.quit_app(action["app"])
        if t == "open_in_editor":
            return self.open_in_editor(action["app"], action["path"])
        if t == "open_last_workspace":
            return self.open_last_workspace()
        if t == "open_terminal_command":
            return self.open_terminal_command(action["command"])
        if t == "create_file_in_editor":
            return self.create_file_in_editor(
                action["filename"],
                action.get("editor", "Cursor"),
                action.get("directory"),
            )
        if t == "spotify_search_play":
            return self.search_and_play_spotify(action.get("query", ""))
        if t == "spotify_pause":
            return self.spotify_pause()
        if t == "spotify_next":
            return self.spotify_next()
        if t == "spotify_prev":
            return self.spotify_prev()
        if t == "spotify_volume":
            return self.spotify_volume(
                action["direction"],
                action.get("amount", 15),
            )
        if t == "create_folder":
            return self.create_folder(action["path"])
        if t == "open_url_in_browser":
            return self.open_url_in_browser(
                action["url"],
                action.get("app", "Google Chrome"),
            )

        raise ValueError(f"Unknown action type: {t}")

    # ─────────────────────────────────────────────────────
    # TERMINAL
    # ─────────────────────────────────────────────────────

    def open_terminal(
        self,
        mode: str = "tab",
        cmd: str = "",
        cwd: str = "",
    ) -> str:
        """
        mode:
          "tab"    -> new tab in existing Terminal window
          "window" -> brand new Terminal window
          "smart"  -> tab if Terminal is running, else launch fresh
        """
        from executor.app_state import is_app_running

        cwd_expanded = os.path.expanduser(cwd) if cwd else os.path.expanduser("~")
        terminal_command = f"cd {cwd_expanded}"
        if cmd:
            terminal_command = f"{terminal_command}; {cmd}"

        if mode == "smart":
            mode = "tab" if is_app_running("Terminal") else "launch"
        elif mode == "tab" and not is_app_running("Terminal"):
            mode = "launch"

        if mode == "launch":
            script = (
                'tell application "Terminal"\n'
                "    activate\n"
                f"    do script {json.dumps(terminal_command)}\n"
                "end tell"
            )
            subprocess.run(["osascript", "-e", script], timeout=10)
            return "opened Terminal"

        if mode == "tab":
            script = (
                'tell application "Terminal"\n'
                "    activate\n"
                '    tell application "System Events"\n'
                '        keystroke "t" using command down\n'
                "    end tell\n"
                "    delay 0.4\n"
                f"    do script {json.dumps(terminal_command)} in front window\n"
                "end tell"
            )
            subprocess.run(["osascript", "-e", script], timeout=10)
            return "opened new Terminal tab"

        if mode == "window":
            script = (
                'tell application "Terminal"\n'
                "    activate\n"
                f"    do script {json.dumps(terminal_command)}\n"
                "end tell"
            )
            subprocess.run(["osascript", "-e", script], timeout=10)
            return "opened new Terminal window"

        return f"unknown terminal mode: {mode}"

    # ─────────────────────────────────────────────────────
    # EDITOR
    # ─────────────────────────────────────────────────────

    @staticmethod
    def _first_existing_path(candidates: list[Path]) -> str | None:
        for candidate in candidates:
            if candidate.exists():
                return str(candidate)
        return None

    @staticmethod
    def _safe_which(command: str) -> str | None:
        found = shutil.which(command)
        return found if found else None

    @classmethod
    def _cursor_cli_path(cls) -> str | None:
        return cls._first_existing_path(CURSOR_CLI_CANDIDATES) or cls._safe_which("cursor")

    @classmethod
    def _vscode_cli_path(cls) -> str | None:
        bundled = cls._first_existing_path(VSCODE_CLI_CANDIDATES)
        if bundled:
            return bundled
        found = cls._safe_which("code")
        if found and "cursor.app" not in found.lower():
            return found
        return None

    @staticmethod
    def _editor_app_available(app_name: str) -> bool:
        if app_name == "Cursor":
            return any(path.exists() for path in CURSOR_APP_CANDIDATES)
        if app_name == "Visual Studio Code":
            return any(path.exists() for path in VSCODE_APP_CANDIDATES)
        return False

    def _resolve_editor(self, editor: str = "auto") -> tuple[str | None, str | None]:
        normalized = (editor or "auto").lower()
        if normalized == "auto":
            cursor_cli = self._cursor_cli_path()
            if cursor_cli or self._editor_app_available("Cursor"):
                return (cursor_cli, "Cursor")
            vscode_cli = self._vscode_cli_path()
            if vscode_cli or self._editor_app_available("Visual Studio Code"):
                return (vscode_cli, "Visual Studio Code")
            return (None, "Cursor")
        if normalized == "cursor":
            return (self._cursor_cli_path(), "Cursor")
        if normalized in {"vscode", "code", "visual studio code"}:
            return (self._vscode_cli_path(), "Visual Studio Code")
        return (None, None)

    def open_editor(
        self,
        path: str = "",
        editor: str = "auto",
        mode: str = "smart",
    ) -> str:
        """
        mode:
          "smart"      -> reuse existing editor window if possible
          "new_window" -> always open in a brand new window
          "new_tab"    -> open path in current editor context
          "focus"      -> bring the editor to front only
        """
        from executor.app_state import is_app_running

        expanded = os.path.expanduser(path) if path else ""
        cli, app_name = self._resolve_editor(editor)
        if not app_name:
            return "no supported editor found"
        if not cli and not self._editor_app_available(app_name):
            return f"{app_name} is not installed"

        if mode == "focus":
            if is_app_running(app_name):
                script = f'tell application "{app_name}" to activate'
                subprocess.run(["osascript", "-e", script], timeout=5)
                return f"focused {app_name}"
            return "editor not running"

        if mode == "new_window":
            if cli:
                command = [cli, "--new-window"]
                if expanded:
                    command.append(expanded)
                subprocess.Popen(command)
                return f"opened new {cli} window: {expanded or 'empty'}"

            script = (
                f'tell application "{app_name}" to activate\n'
                'tell application "System Events"\n'
                '    keystroke "n" using command down\n'
                "end tell"
            )
            subprocess.run(["osascript", "-e", script], timeout=10)
            if expanded:
                subprocess.Popen(["open", "-a", app_name, expanded])
                return f"opened new {app_name} window: {expanded}"
            return "opened new window via AppleScript"

        if mode == "new_tab":
            if cli and expanded:
                subprocess.Popen([cli, expanded])
                return f"opened {expanded} in {cli}"
            if expanded:
                subprocess.Popen(["open", "-a", app_name, expanded])
                return f"opened {expanded} in {app_name}"
            script = f'tell application "{app_name}" to activate'
            subprocess.run(["osascript", "-e", script], timeout=5)
            return f"focused {app_name}"

        if mode == "smart":
            if cli and expanded:
                subprocess.Popen([cli, expanded])
                return f"opened {expanded} in {cli}"
            if cli and not expanded:
                subprocess.Popen([cli])
                return f"opened {cli}"
            if expanded:
                subprocess.Popen(["open", "-a", app_name, expanded])
                return f"opened {expanded} in {app_name}"
            subprocess.Popen(["open", "-a", app_name])
            return f"opened {app_name}"

        return f"unknown editor mode: {mode}"

    # ─────────────────────────────────────────────────────
    # GENERIC APP OPEN
    # ─────────────────────────────────────────────────────

    def open_app(self, app_name: str, mode: str = "smart") -> str:
        from executor.app_state import is_app_running

        lowered = app_name.lower()
        if lowered in {"terminal", "iterm", "iterm2"}:
            return self.open_terminal("tab" if mode != "new" else "window")
        if lowered in {"cursor", "vscode", "visual studio code", "code"}:
            editor = "cursor" if "cursor" in lowered else "vscode"
            editor_mode = "focus" if mode == "focus" else ("new_window" if mode == "new" else "smart")
            return self.open_editor(editor=editor, mode=editor_mode)

        running = is_app_running(app_name)

        if mode == "new":
            subprocess.Popen(["open", "-n", "-a", app_name])
            return f"opened new {app_name} instance"

        if mode == "focus" or (mode == "smart" and running):
            script = f'tell application "{app_name}" to activate'
            subprocess.run(["osascript", "-e", script], timeout=5)
            return f"focused {app_name}"

        subprocess.Popen(["open", "-a", app_name])
        return f"launched {app_name}"

    def quit_app(self, app_name: str) -> str:
        script = f'tell application "{app_name}" to quit'
        subprocess.run(["osascript", "-e", script], timeout=5)
        return f"quit {app_name}"

    # ─────────────────────────────────────────────────────
    # SPOTIFY
    # ─────────────────────────────────────────────────────

    def play_music(self, mode: str) -> str:
        if mode == "off":
            subprocess.run(
                ["osascript", "-e", 'tell application "Spotify" to pause'],
                timeout=5,
            )
            return "music paused"

        playlists = {
            "focus": "spotify:playlist:37i9dQZF1DX0SM0LYsmbMT",
            "late_night": "spotify:playlist:37i9dQZF1DXdwTUxa7GFkZ",
            "chill": "spotify:playlist:37i9dQZF1DXdwTUxmGKrdN",
            "hype": "spotify:playlist:37i9dQZF1DX76Wlfdnj7AP",
        }
        uri = playlists.get(mode, playlists["focus"])
        script = (
            'tell application "Spotify"\n'
            "    activate\n"
            f'    play track "{uri}"\n'
            "end tell"
        )
        subprocess.run(["osascript", "-e", script], timeout=10)
        return f"playing {mode} playlist"

    def search_and_play_spotify(self, query: str) -> str:
        """Search Spotify and play via AppleScript rather than blind URI open."""
        encoded_query = urllib.parse.quote(query)
        try:
            subprocess.run(
                [
                    "osascript",
                    "-e",
                    'tell application "Spotify" to activate',
                    "-e",
                    f'tell application "Spotify" to play track "spotify:search:{encoded_query}"',
                ],
                timeout=15,
            )
            return f"searched and playing: {query}"
        except subprocess.TimeoutExpired:
            return f"Spotify search timed out for: {query}"

    def spotify_pause(self) -> str:
        subprocess.Popen(["osascript", "-e", 'tell application "Spotify" to pause'])
        return "paused"

    def spotify_next(self) -> str:
        subprocess.Popen(["osascript", "-e", 'tell application "Spotify" to next track'])
        return "next track"

    def spotify_prev(self) -> str:
        subprocess.Popen(["osascript", "-e", 'tell application "Spotify" to previous track'])
        return "previous track"

    def spotify_volume(self, direction: str, amount: int = 15) -> str:
        operator = "+" if direction == "up" else "-"
        script = (
            'tell application "Spotify"\n'
            "    set currentVolume to sound volume\n"
            f"    set targetVolume to currentVolume {operator} {amount}\n"
            "    if targetVolume > 100 then set targetVolume to 100\n"
            "    if targetVolume < 0 then set targetVolume to 0\n"
            "    set sound volume to targetVolume\n"
            "end tell"
        )
        subprocess.Popen(["osascript", "-e", script])
        return f"volume {direction}"

    # ─────────────────────────────────────────────────────
    # FILE + FOLDER ACTIONS
    # ─────────────────────────────────────────────────────

    def open_folder(self, path: str) -> str:
        expanded = os.path.expanduser(path)
        subprocess.Popen(["open", expanded])
        return f"opened {expanded}"

    def create_and_open(self, path: str, editor: str = "auto") -> str:
        expanded = os.path.expanduser(path)
        Path(expanded).mkdir(parents=True, exist_ok=True)
        if not Path(expanded).exists():
            return f"failed to create: {expanded}"
        return self.open_editor(path=expanded, editor=editor, mode="smart")

    def create_folder(self, path: str) -> str:
        expanded = os.path.expanduser(path)
        Path(expanded).mkdir(parents=True, exist_ok=True)
        subprocess.Popen(["open", expanded])
        return f"created {expanded}"

    def run_command(
        self,
        cmd: str,
        cwd: str = None,
        in_terminal: bool = False,
    ) -> str:
        stripped = cmd.strip()
        if not stripped:
            raise ValueError("Command is empty")
        first = stripped.split()[0]
        if first not in ALLOWED_COMMANDS:
            raise PermissionError(f"'{first}' not in allowlist")

        cwd_expanded = os.path.expanduser(cwd) if cwd else os.path.expanduser("~/Developer")
        if not os.path.exists(cwd_expanded):
            Path(cwd_expanded).mkdir(parents=True, exist_ok=True)

        if in_terminal:
            return self.open_terminal(mode="tab", cmd=cmd, cwd=cwd_expanded)

        result = subprocess.run(
            cmd,
            shell=True,
            cwd=cwd_expanded,
            capture_output=True,
            text=True,
            timeout=30,
        )
        output = result.stdout.strip() or result.stderr.strip() or "done"
        return output[:300]

    def create_file_in_editor(
        self,
        filename: str,
        editor: str = "Cursor",
        directory: str | None = None,
    ) -> str:
        base_dir = os.path.expanduser(directory) if directory else os.path.expanduser("~/Developer")
        filepath = Path(base_dir) / filename
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.touch(exist_ok=True)
        normalized = (editor or "auto").lower()
        if "cursor" in normalized:
            editor_name = "cursor"
        elif normalized in {"vscode", "code", "visual studio code"}:
            editor_name = "vscode"
        else:
            editor_name = "auto"
        return self.open_editor(path=str(filepath), editor=editor_name, mode="smart")

    def open_in_editor(self, app: str, path: str) -> str:
        normalized = (app or "").lower()
        if "cursor" in normalized:
            editor_name = "cursor"
        elif normalized in {"vscode", "code", "visual studio code"} or "visual studio code" in normalized:
            editor_name = "vscode"
        else:
            editor_name = "auto"
        return self.open_editor(path=path, editor=editor_name, mode="smart")

    def write_file(self, path: str, content: str, mode: str = "append") -> str:
        expanded = os.path.expanduser(path)
        Path(expanded).parent.mkdir(parents=True, exist_ok=True)
        file_mode = "a" if mode == "append" else "w"
        with open(expanded, file_mode, encoding="utf-8") as handle:
            if mode == "append":
                handle.write(
                    f"\n\n--- {datetime.now().strftime('%Y-%m-%d %H:%M')} ---\n{content}"
                )
            else:
                handle.write(content)
        self.open_editor(path=expanded, editor="cursor", mode="smart")
        return f"wrote to {expanded}"

    def obsidian_note(self, title: str, content: str, folder: str = "Daily") -> str:
        if not OBSIDIAN_VAULT:
            return "Obsidian vault not configured in butler_config.py"
        vault_folder = Path(OBSIDIAN_VAULT) / folder
        vault_folder.mkdir(parents=True, exist_ok=True)
        date_str = datetime.now().strftime("%Y-%m-%d")
        filename = f"{date_str} {title}.md" if folder == "Daily" else f"{title}.md"
        filepath = vault_folder / filename
        file_mode = "a" if filepath.exists() and folder == "Daily" else "w"
        with open(filepath, file_mode, encoding="utf-8") as handle:
            if file_mode == "w":
                handle.write(f"# {title}\n\n{content}\n")
            else:
                handle.write(f"\n\n## {datetime.now().strftime('%H:%M')}\n{content}\n")
        note_path = urllib.parse.quote(str(filepath))
        subprocess.Popen(["open", f"obsidian://open?path={note_path}"])
        return f"saved to Obsidian: {filename}"

    def open_last_workspace(self) -> str:
        try:
            from context.mac_activity import load_state
            from memory.store import _load

            state = load_state()
            workspace = state.get("cursor_workspace", "")
            if workspace:
                return self.open_editor(path=workspace, editor="cursor", mode="smart")

            data = _load()
            for session in reversed(data.get("command_history", [])[-10:]):
                for action in session.get("actions", []):
                    if action.get("type") in {"open_folder", "create_and_open", "open_editor"}:
                        path = action.get("path", "")
                        if path:
                            return self.open_editor(path=path, editor="cursor", mode="smart")
        except Exception:
            pass
        return "No previous workspace found"

    # ─────────────────────────────────────────────────────
    # VPS / SSH
    # ─────────────────────────────────────────────────────

    def _vps_helper_command(self, action: str, host: str = "", remote_cmd: str = "") -> list[str]:
        script_path = Path(__file__).resolve().parent.parent / "scripts" / "vps.py"
        command = ["python3", str(script_path), action]
        if host:
            command.extend(["--host", host])
        if remote_cmd:
            command.append(remote_cmd)
        return command

    def ssh_open(self, host: str, label: str = "VPS") -> str:
        shell_command = " ".join(
            shlex.quote(part)
            for part in self._vps_helper_command("shell", host=host)
        )
        return self.open_terminal(mode="tab", cmd=shell_command, cwd="~")

    def ssh_command(self, host: str, cmd: str) -> str:
        result = subprocess.run(
            self._vps_helper_command("exec", host=host, remote_cmd=cmd),
            capture_output=True,
            text=True,
            timeout=35,
        )
        return (result.stdout.strip() or result.stderr.strip() or "done")[:300]

    # ─────────────────────────────────────────────────────
    # NOTIFICATIONS / REMINDERS
    # ─────────────────────────────────────────────────────

    def open_url(self, url: str) -> str:
        subprocess.Popen(["open", url])
        return f"opened {url}"

    def open_url_in_browser(self, url: str, app: str = "Google Chrome") -> str:
        subprocess.Popen(["open", "-a", app, url])
        return f"opened {url}"

    def notify(self, title: str, message: str) -> str:
        script = (
            f"display notification {json.dumps(message)} "
            f"with title {json.dumps(title)}"
        )
        subprocess.Popen(["osascript", "-e", script])
        return "notified"

    def remind_in(self, minutes: int, message: str) -> str:
        def _remind():
            time.sleep(minutes * 60)
            self.notify("Butler reminder", message)

        threading.Thread(target=_remind, daemon=True).start()
        return f"reminder set for {minutes} min"

    # ─────────────────────────────────────────────────────
    # SPECIALIST AGENTS
    # ─────────────────────────────────────────────────────

    def run_agent_task(self, agent_type: str, input_data: dict) -> str:
        try:
            from agents.runner import run_agent

            result = run_agent(agent_type, input_data)
            return str(result.get("result", "no result"))[:200]
        except Exception as exc:
            return f"agent error: {exc}"

    # ─────────────────────────────────────────────────────
    # SAFETY
    # ─────────────────────────────────────────────────────

    def _requires_confirmation(self, action: dict) -> bool:
        t = action.get("type", "")
        cmd = str(action.get("cmd", "")).lower()
        if t == "run_command":
            return any(pattern in cmd for pattern in CONFIRM_REQUIRED_PATTERNS)
        if t == "ssh_command":
            lowered = str(action.get("cmd", "")).lower()
            return any(token in lowered for token in ["restart", "stop", "rm", "delete", "drop"])
        if t == "write_file" and action.get("mode") == "overwrite":
            return True
        return False

    def _ask_confirmation(self, action: dict) -> bool:
        desc = (
            action.get("cmd")
            or action.get("app")
            or action.get("type", "")
        )[:60]
        script = (
            'display alert "Butler needs confirmation" '
            f'message {json.dumps(f"About to run: {desc}")} '
            'buttons {"Cancel", "Go ahead"} '
            'default button "Go ahead"'
        )
        try:
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=30,
            )
            return "Go ahead" in (result.stdout or "")
        except Exception:
            if sys.stdin and not sys.stdin.closed and sys.stdin.isatty():
                response = input(f"[Butler] Run '{desc}'? (y/n): ").strip().lower()
                return response == "y"
            return False

    def _safe_home_path(self, path: str) -> str:
        return os.path.expanduser(path)

    def open_terminal_command(self, command: str) -> str:
        return self.open_terminal(mode="tab", cmd=command, cwd="~")


if __name__ == "__main__":
    executor = Executor()
    results = executor.run(
        [
            {
                "type": "notify",
                "title": "Engine test",
                "message": "Executor v2 loaded",
            }
        ]
    )
    print(json.dumps(results, indent=2))
