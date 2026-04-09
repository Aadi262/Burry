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
import re
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

from intents.router import APP_MAP
from utils import _normalize

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
    "ls",
    "pwd",
    "cat",
    "echo",
    "mkdir",
    "cp",
    "mv",
    "rm",
    "python",
    "python3",
    "pip",
    "pip3",
    "npm",
    "npx",
    "node",
    "docker",
    "curl",
    "open",
]

CONFIRM_REQUIRED_PATTERNS = [
    "git push",
    "docker stop",
    "docker rm",
    "docker restart",
    "rm -rf",
    "sudo",
]

DEFAULT_BROWSER_APP = "Google Chrome"
URL_MAP = {
    "google docs": "https://docs.new",
    "google sheets": "https://sheets.new",
    "google meet": "https://meet.new",
    "google slides": "https://slides.new",
    "notion": "https://notion.so",
    "linear": "https://linear.app",
    "figma": "https://figma.com",
    "github": "https://github.com/Aadi262",
    "vercel": "https://vercel.com/dashboard",
    "railway": "https://railway.app",
}
LOCATION_ROOTS = {
    "on the desktop": "~/Desktop",
    "on desktop": "~/Desktop",
    "in documents": "~/Documents",
    "in the documents": "~/Documents",
    "in downloads": "~/Downloads",
    "in the downloads": "~/Downloads",
    "in home": "~",
    "in the home": "~",
}
BROWSER_APP_CANDIDATES = {
    "Google Chrome": [
        Path("/Applications/Google Chrome.app"),
        Path.home() / "Applications" / "Google Chrome.app",
    ],
    "Brave Browser": [
        Path("/Applications/Brave Browser.app"),
        Path.home() / "Applications" / "Brave Browser.app",
    ],
    "Chromium": [
        Path("/Applications/Chromium.app"),
        Path.home() / "Applications" / "Chromium.app",
    ],
    "Safari": [
        Path("/Applications/Safari.app"),
        Path.home() / "Applications" / "Safari.app",
    ],
}

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

    @staticmethod
    def _applescript_string(value: str) -> str:
        return json.dumps(str(value or ""))

    @staticmethod
    def _normalize_browser_url(url: str) -> str:
        cleaned = str(url or "").strip()
        if not cleaned:
            return "chrome://newtab"
        if cleaned.startswith(("http://", "https://", "chrome://")):
            return cleaned
        return f"https://{cleaned}"

    def _run_osascript(self, script: str, timeout: int = 5) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            message = " ".join((result.stderr or result.stdout or "AppleScript failed").split()).strip()
            raise RuntimeError(message or "AppleScript failed")
        return result

    def _is_app_running(self, app_name: str) -> bool:
        script = (
            'tell application "System Events"\n'
            f"    return (name of processes) contains {self._applescript_string(app_name)}\n"
            "end tell"
        )
        try:
            result = self._run_osascript(script, timeout=3)
            return str(result.stdout or "").strip().lower() == "true"
        except Exception:
            try:
                from executor.app_state import is_app_running

                return bool(is_app_running(app_name))
            except Exception:
                return False

    @staticmethod
    def _collapse_text(value: str) -> str:
        return " ".join(str(value or "").split()).strip()

    def _map_url(self, value: str) -> str:
        cleaned = self._collapse_text(value).lower()
        if cleaned in URL_MAP:
            return URL_MAP[cleaned]
        return str(value or "").strip()

    def _speak(self, text: str) -> None:
        try:
            from voice import speak

            speak(text)
        except Exception:
            return

    def _listen_followup(self, timeout: float = 6.0) -> str:
        try:
            from voice.stt import listen_for_command

            return self._collapse_text(listen_for_command(timeout=timeout) or "")
        except Exception:
            return ""

    def _summarize_text(self, text: str, instruction: str) -> str:
        cleaned = self._collapse_text(text)
        if not cleaned:
            return ""
        try:
            from brain.ollama_client import _call

            prompt = f"{instruction}\n\n{cleaned[:12000]}"
            return self._collapse_text(_call(prompt, "gemma4:e4b", temperature=0.1, max_tokens=220))
        except Exception:
            return cleaned[:500]

    def _gmail_compose_url(self, recipient: str = "", subject: str = "", body: str = "") -> str:
        params: list[tuple[str, str]] = []
        if self._collapse_text(recipient):
            params.append(("to", self._collapse_text(recipient)))
        if self._collapse_text(subject):
            params.append(("su", self._collapse_text(subject)))
        if self._collapse_text(body):
            params.append(("body", self._collapse_text(body)))
        base = "https://mail.google.com/mail/u/0/?view=cm&fs=1&tf=1"
        return f"{base}&{urllib.parse.urlencode(params)}" if params else base

    def _current_chrome_url(self) -> str:
        script = (
            'tell application "Google Chrome"\n'
            "    if (count of windows) = 0 then return \"\"\n"
            "    return URL of active tab of front window\n"
            "end tell"
        )
        try:
            result = self._run_osascript(script, timeout=4)
            return self._collapse_text(result.stdout)
        except Exception:
            return ""

    def _fetch_jina_reader(self, url: str) -> str:
        target = self._normalize_browser_url(url)
        try:
            import requests

            response = requests.get(
                f"https://r.jina.ai/{target}",
                headers={"Accept": "text/plain", "X-Return-Format": "text"},
                timeout=10,
            )
            if response.status_code != 200:
                return ""
            return str(response.text or "")
        except Exception:
            return ""

    def _folder_base_path(self, raw: str) -> str:
        lowered = self._collapse_text(raw).lower()
        for phrase, target in LOCATION_ROOTS.items():
            if phrase in lowered:
                return target
        return "~/Desktop"

    def _clean_folder_name(self, raw: str) -> str:
        cleaned = self._collapse_text(raw)
        lowered = cleaned.lower()
        for phrase in LOCATION_ROOTS:
            lowered = lowered.replace(phrase, " ")
        cleaned = re.sub(
            r"\b(?:create|make|new|another|one more|folder|called|named|with name|with the name)\b",
            " ",
            lowered,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" .!/?")
        return cleaned

    def _resolve_folder_target(self, path: str = "", name: str = "") -> Path:
        explicit = self._collapse_text(path)
        if explicit and (explicit.startswith("~") or explicit.startswith("/") or os.sep in explicit):
            return Path(os.path.expanduser(explicit))

        raw = name or path
        base = Path(os.path.expanduser(self._folder_base_path(raw)))
        folder_name = self._clean_folder_name(raw)
        if not folder_name:
            folder_name = "new-folder"
        return base / folder_name

    def _project_launch_order(self, preferred: str = "auto") -> list[str]:
        normalized = str(preferred or "auto").strip().lower()
        if normalized == "vscode":
            normalized = "code"
        ordered = ["claude", "codex", "cursor", "code"]
        if normalized in ordered:
            return [normalized] + [item for item in ordered if item != normalized]
        return ordered

    def _project_launch_command(self, launcher: str, path: str) -> list[str] | None:
        if launcher == "claude":
            cli = self._safe_which("claude")
            return [cli, path] if cli else None
        if launcher == "codex":
            cli = self._safe_which("codex")
            return [cli, path] if cli else None
        if launcher == "cursor":
            cli = self._cursor_cli_path()
            return [cli, path] if cli else None
        if launcher == "code":
            cli = self._vscode_cli_path()
            return [cli, path] if cli else None
        return None

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
        if t == "create_file":
            return self.create_file(
                action.get("path", ""),
                action.get("content", ""),
            )
        if t == "read_file":
            return self.read_file(action.get("path", ""))
        if t == "write_file":
            return self.write_file(
                action.get("path", ""),
                action.get("content", ""),
                action.get("mode", "overwrite"),
            )
        if t == "delete_file":
            return self.delete_file(action.get("path", ""))
        if t == "find_file":
            return self.find_file(
                action.get("query", ""),
                action.get("path", "~"),
            )
        if t == "list_files":
            return self.list_files(action.get("path", "~"))
        if t == "move_file":
            return self.move_file(
                action.get("from", ""),
                action.get("to", ""),
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
            return self.open_url(action.get("url", ""))
        if t == "focus_app":
            return self.focus_app(action["app"])
        if t == "minimize_app":
            return self.minimize_app(action["app"])
        if t == "hide_app":
            return self.hide_app(action["app"])
        if t == "compose_email":
            return self.compose_email(
                action.get("recipient", "") or action.get("to", ""),
                action.get("subject", ""),
                action.get("body", ""),
            )
        if t == "compose_whatsapp":
            return self.compose_whatsapp(
                action.get("contact", ""),
                action.get("phone", ""),
                action.get("message", ""),
            )
        if t == "chrome_open_tab":
            return self.chrome_open_tab(action["url"])
        if t == "chrome_close_tab":
            return self.chrome_close_tab(action["tab_title"])
        if t == "chrome_focus_tab":
            return self.chrome_focus_tab(action["tab_title"])
        if t == "send_email":
            return self.send_email(action["to"], action["subject"], action["body"])
        if t == "send_whatsapp":
            return self.send_whatsapp(action["contact"], action["message"])
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
            return self.open_project(
                action.get("name", ""),
                action.get("editor", "auto"),
            )
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
        if t == "spotify_now_playing":
            return self.spotify_now_playing()
        if t == "create_folder":
            return self.create_folder(
                action.get("path", ""),
                action.get("name", ""),
            )
        if t == "open_url_in_browser":
            return self.open_url_in_browser(
                action["url"],
                action.get("app", DEFAULT_BROWSER_APP),
            )
        if t == "browser_new_tab":
            return self.browser_new_tab(action.get("url", ""))
        if t == "browser_search":
            return self.browser_search(
                action.get("query", ""),
                new_tab=bool(action.get("new_tab", True)),
            )
        if t == "browser_close_tab":
            return self.browser_close_tab()
        if t == "browser_close_window":
            return self.browser_close_window()
        if t == "browser_window":
            return self.browser_window(action.get("url", ""))
        if t == "browser_go_back":
            return self.browser_go_back()
        if t == "browser_refresh":
            return self.browser_refresh()
        if t == "browser_go_to":
            return self.browser_go_to(action.get("url", ""))
        if t == "pause_video":
            return self.pause_video()
        if t == "volume_set":
            return self.volume_set(action.get("level", 50))
        if t == "volume_up":
            return self.volume_up()
        if t == "volume_down":
            return self.volume_down()
        if t == "system_volume":
            return self.system_volume_adjust(action.get("direction", "up"))
        if t == "brightness_up":
            return self.brightness_up()
        if t == "brightness_down":
            return self.brightness_down()
        if t == "brightness":
            direction = str(action.get("direction", "") or "").strip().lower()
            if direction == "down":
                return self.brightness_down()
            return self.brightness_up()
        if t == "lock_screen":
            return self.lock_screen()
        if t == "sleep_mac":
            return self.sleep_mac()
        if t == "show_desktop":
            return self.show_desktop()
        if t == "dark_mode":
            return self.dark_mode(action.get("enable"))
        if t == "do_not_disturb":
            return self.do_not_disturb(action.get("enable"))
        if t == "system_info":
            return self.system_info(action.get("query", ""))
        if t == "screenshot":
            return self.take_screenshot()
        if t == "take_screenshot":
            return self.take_screenshot(
                save=bool(action.get("save", True)),
                describe=bool(action.get("describe", True)),
            )
        if t == "read_screen":
            return self.read_screen()
        if t == "summarize_page":
            return self.summarize_page(action.get("url", ""))
        if t == "summarize_video":
            return self.summarize_video(
                action.get("url", ""),
                save_to_obsidian=bool(action.get("save_to_obsidian", False)),
            )
        if t == "git_action":
            return self.git_action(
                action.get("cmd", ""),
                cwd=action.get("cwd"),
                message=action.get("message", ""),
                push=bool(action.get("push", False)),
            )
        if t == "whatsapp_open":
            return self.whatsapp_open(
                action.get("contact", ""),
                action.get("phone", ""),
            )
        if t == "whatsapp_send":
            return self.whatsapp_send(
                action.get("contact", ""),
                action.get("phone", ""),
                action.get("message", ""),
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

    @staticmethod
    def _browser_app_available(app_name: str) -> bool:
        if not app_name:
            return False
        candidates = list(BROWSER_APP_CANDIDATES.get(app_name, []))
        candidates.append(Path("/Applications") / f"{app_name}.app")
        candidates.append(Path.home() / "Applications" / f"{app_name}.app")
        return any(path.exists() for path in candidates)

    @classmethod
    def _resolve_browser_app(cls, preferred: str = DEFAULT_BROWSER_APP) -> str:
        ordered = [preferred, DEFAULT_BROWSER_APP, "Google Chrome", "Brave Browser", "Chromium", "Safari"]
        seen: set[str] = set()
        for candidate in ordered:
            clean = str(candidate or "").strip()
            if not clean or clean in seen:
                continue
            seen.add(clean)
            if cls._browser_app_available(clean):
                return clean
        return str(preferred or DEFAULT_BROWSER_APP).strip() or DEFAULT_BROWSER_APP

    @staticmethod
    def _browser_family(app_name: str) -> str:
        lowered = str(app_name or "").lower()
        if "safari" in lowered:
            return "safari"
        return "chrome"

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

    def open_project(self, name: str, editor: str = "auto") -> str:
        from memory.layered import get_project_detail
        from projects import get_project
        from runtime import note_project_context_hint

        project = get_project(name, hydrate_blurb=True)
        if not project:
            raise RuntimeError(f"could not find project: {name}")

        expanded = os.path.expanduser(str(project.get("path", "") or ""))
        if not expanded or not os.path.exists(expanded):
            raise RuntimeError(f"missing project path: {expanded or name}")

        for launcher in self._project_launch_order(editor):
            command = self._project_launch_command(launcher, expanded)
            if not command:
                continue
            subprocess.Popen(command)
            project_name = str(project.get("name", "") or Path(expanded).name).strip()
            detail = get_project_detail(project_name)
            if detail:
                note_project_context_hint(project_name, detail[-1000:])
            return f"opened {project_name} in {launcher}"

        subprocess.Popen(["open", expanded])
        return f"opened {Path(expanded).name} in Finder"

    def open_app(self, app_name: str, mode: str = "smart") -> str:
        if isinstance(app_name, tuple) and len(app_name) == 2 and app_name[0] == "browser":
            return self.open_url_in_browser(str(app_name[1]), DEFAULT_BROWSER_APP)

        normalized_label = _normalize(app_name)
        for key, value in APP_MAP.items():
            if _normalize(key) != normalized_label:
                continue
            if isinstance(value, tuple) and len(value) == 2 and value[0] == "browser":
                return self.open_url_in_browser(str(value[1]), DEFAULT_BROWSER_APP)
            break

        lowered = app_name.lower()
        if lowered in {"terminal", "iterm", "iterm2"}:
            if mode == "new":
                return self.open_terminal("window")
            if self._is_app_running("Terminal"):
                self._run_osascript('tell application "Terminal" to activate', timeout=4)
                return "focused Terminal"
            subprocess.Popen(["open", "-a", "Terminal"])
            return "launched Terminal"
        if lowered in {"cursor", "vscode", "visual studio code", "code"}:
            editor = "cursor" if "cursor" in lowered else "vscode"
            editor_mode = "focus" if mode == "focus" else ("new_window" if mode == "new" else "smart")
            return self.open_editor(editor=editor, mode=editor_mode)

        running = self._is_app_running(app_name)

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

    def focus_app(self, app_name: str) -> str:
        script = f"tell application {self._applescript_string(app_name)} to activate"
        self._run_osascript(script, timeout=5)
        return f"Focused {app_name}"

    def minimize_app(self, app_name: str) -> str:
        script = (
            'tell application "System Events"\n'
            f"    tell process {self._applescript_string(app_name)}\n"
            "        set miniaturized of window 1 to true\n"
            "    end tell\n"
            "end tell"
        )
        self._run_osascript(script, timeout=5)
        return f"Minimized {app_name}"

    def hide_app(self, app_name: str) -> str:
        script = (
            'tell application "System Events"\n'
            f"    set visible of process {self._applescript_string(app_name)} to false\n"
            "end tell"
        )
        self._run_osascript(script, timeout=5)
        return f"Hidden {app_name}"

    def chrome_open_tab(self, url: str) -> str:
        target = self._normalize_browser_url(url)
        script = (
            'tell application "Google Chrome"\n'
            "    activate\n"
            "    if (count of windows) = 0 then make new window\n"
            "    tell window 1\n"
            f"        make new tab with properties {{URL:{self._applescript_string(target)}}}\n"
            "    end tell\n"
            "end tell"
        )
        self._run_osascript(script, timeout=5)
        return f"Opened tab {target}"

    def chrome_close_tab(self, tab_title: str) -> str:
        script = (
            'tell application "Google Chrome"\n'
            "    repeat with w in windows\n"
            "        repeat with t in tabs of w\n"
            f"            if title of t contains {self._applescript_string(tab_title)} then\n"
            "                close t\n"
            "                return\n"
            "            end if\n"
            "        end repeat\n"
            "    end repeat\n"
            "end tell"
        )
        self._run_osascript(script, timeout=5)
        return f"Closed tab containing {tab_title}"

    def chrome_focus_tab(self, tab_title: str) -> str:
        script = (
            'tell application "Google Chrome"\n'
            "    activate\n"
            "    repeat with w in windows\n"
            "        set tab_index to 0\n"
            "        repeat with t in tabs of w\n"
            "            set tab_index to tab_index + 1\n"
            f"            if title of t contains {self._applescript_string(tab_title)} then\n"
            "                set active tab index of w to tab_index\n"
            "                return\n"
            "            end if\n"
            "        end repeat\n"
            "    end repeat\n"
            "end tell"
        )
        self._run_osascript(script, timeout=5)
        return f"Focused tab containing {tab_title}"

    def send_email(self, to: str, subject: str, body: str) -> str:
        script = (
            'tell application "Mail"\n'
            "    set newMsg to make new outgoing message with properties {"
            f"subject:{self._applescript_string(subject)}, "
            f"content:{self._applescript_string(body)}, "
            "visible:true}\n"
            "    tell newMsg\n"
            f"        make new to recipient with properties {{address:{self._applescript_string(to)}}}\n"
            "        send\n"
            "    end tell\n"
            "end tell"
        )
        self._run_osascript(script, timeout=10)
        return f"Email sent to {to}"

    def send_whatsapp(self, contact: str, message: str) -> str:
        script = (
            'tell application "WhatsApp"\n'
            "    activate\n"
            "end tell\n"
            "delay 1\n"
            'tell application "System Events"\n'
            '    tell process "WhatsApp"\n'
            '        keystroke "f" using command down\n'
            "        delay 0.5\n"
            f"        keystroke {self._applescript_string(contact)}\n"
            "        delay 1\n"
            "        key code 36\n"
            "        delay 0.5\n"
            f"        keystroke {self._applescript_string(message)}\n"
            "        key code 36\n"
            "    end tell\n"
            "end tell"
        )
        self._run_osascript(script, timeout=15)
        return f"WhatsApp message sent to {contact}"

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

    def spotify_now_playing(self) -> str:
        script = (
            'tell application "Spotify"\n'
            "    if player state is stopped then return \"Nothing is playing\"\n"
            "    return name of current track & \" by \" & artist of current track\n"
            "end tell"
        )
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=5,
        )
        track = " ".join((result.stdout or "").split()).strip()
        return track or "Nothing is playing"

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

    def create_folder(self, path: str = "", name: str = "") -> str:
        target = self._resolve_folder_target(path=path, name=name)
        target.mkdir(parents=True, exist_ok=True)
        subprocess.Popen(["open", str(target)])
        return f"created {target}"

    def create_file(self, path: str, content: str = "") -> str:
        expanded = os.path.expanduser(path)
        if not expanded:
            raise ValueError("File path is required")
        Path(expanded).parent.mkdir(parents=True, exist_ok=True)
        with open(expanded, "w", encoding="utf-8") as handle:
            handle.write(content or "")
        return f"created {expanded}"

    def read_file(self, path: str) -> str:
        expanded = os.path.expanduser(path)
        with open(expanded, "r", encoding="utf-8") as handle:
            content = handle.read()
        cleaned = self._collapse_text(content)
        if len(cleaned) <= 500:
            return cleaned or f"{expanded} is empty"
        summary = self._summarize_text(cleaned, "Summarize this file in under 120 words.")
        return summary or cleaned[:500]

    def run_command(
        self,
        cmd: str,
        cwd: str = None,
        in_terminal: bool = False,
    ) -> str:
        stripped = self._collapse_text(cmd)
        if not stripped:
            raise ValueError("Command is empty")
        try:
            first = shlex.split(stripped)[0]
        except Exception:
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
        open_result = self.open_editor(path=str(filepath), editor=editor_name, mode="smart")
        if "not installed" in open_result.lower():
            return f"created {filepath}, but {open_result}"
        return f"created {filepath} and {open_result}"

    def open_in_editor(self, app: str, path: str) -> str:
        normalized = (app or "").lower()
        if "cursor" in normalized:
            editor_name = "cursor"
        elif normalized in {"vscode", "code", "visual studio code"} or "visual studio code" in normalized:
            editor_name = "vscode"
        else:
            editor_name = "auto"
        return self.open_editor(path=path, editor=editor_name, mode="smart")

    def write_file(self, path: str, content: str, mode: str = "overwrite") -> str:
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
        return f"wrote to {expanded}"

    def delete_file(self, path: str) -> str:
        expanded = os.path.expanduser(path)
        if not os.path.isfile(expanded):
            raise FileNotFoundError(expanded)
        filename = Path(expanded).name
        self._speak(f"delete {filename} are you sure")
        heard = self._listen_followup(timeout=5.0).lower()
        if heard not in {"yes", "yeah", "yep", "confirm", "do it"}:
            return "skipped - user cancelled"
        os.remove(expanded)
        return f"deleted {expanded}"

    def find_file(self, query: str, root: str = "~") -> str:
        cleaned = self._collapse_text(query)
        if not cleaned:
            raise ValueError("Search query is required")
        expanded_root = os.path.expanduser(root or "~")
        result = subprocess.run(
            ["find", expanded_root, "-iname", f"*{cleaned}*"],
            capture_output=True,
            text=True,
            timeout=20,
        )
        matches = [line.strip() for line in str(result.stdout or "").splitlines() if line.strip()]
        if not matches:
            return "no files found"
        return ", ".join(matches[:8])

    def list_files(self, path: str = "~") -> str:
        expanded = os.path.expanduser(path or "~")
        items = sorted(os.listdir(expanded))[:8]
        spoken = ", ".join(items) if items else "no files"
        self._speak(spoken)
        return spoken

    def move_file(self, source: str, destination: str) -> str:
        expanded_source = os.path.expanduser(source)
        expanded_destination = os.path.expanduser(destination)
        Path(expanded_destination).parent.mkdir(parents=True, exist_ok=True)
        shutil.move(expanded_source, expanded_destination)
        return f"moved {expanded_source} to {expanded_destination}"

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
        target = self._map_url(url)
        normalized = self._normalize_browser_url(target)
        subprocess.Popen(["open", normalized])
        return f"opened {normalized}"

    def open_url_in_browser(self, url: str, app: str = "Google Chrome") -> str:
        target = self._normalize_browser_url(self._map_url(url))
        app_name = self._resolve_browser_app(app)
        result = subprocess.run(
            ["open", "-a", app_name, target],
            capture_output=True,
            text=True,
            timeout=8,
        )
        if result.returncode != 0:
            subprocess.run(["open", target], capture_output=True, text=True, timeout=8)
        return f"opened {target}"

    def compose_email(self, recipient: str, subject: str = "", body: str = "") -> str:
        url = self._gmail_compose_url(recipient, subject, body)
        self.open_url_in_browser(url, DEFAULT_BROWSER_APP)
        if self._collapse_text(subject) and self._collapse_text(body):
            time.sleep(3)
            try:
                import pyautogui

                pyautogui.press("tab")
                pyautogui.write(subject)
                pyautogui.press("tab")
                pyautogui.write(body)
            except Exception:
                pass
        return f"opened Gmail compose for {self._collapse_text(recipient) or 'draft'}"

    def compose_whatsapp(self, contact: str = "", phone: str = "", message: str = "") -> str:
        digits = "".join(ch for ch in str(phone) if ch.isdigit() or ch == "+")
        if digits:
            try:
                import pywhatkit

                pywhatkit.sendwhatmsg_instantly(digits, message or "", tab_close=True, close_time=2)
                return f"sent WhatsApp message to {contact or phone}"
            except Exception:
                return self.whatsapp_send(contact, phone, message)

        base = "https://wa.me/"
        if message:
            base = f"{base}?text={urllib.parse.quote_plus(self._collapse_text(message))}"
        self.open_url(base)
        return f"opened WhatsApp compose for {contact or 'the contact'}"

    def browser_new_tab(self, url: str = "") -> str:
        app_name = self._resolve_browser_app(DEFAULT_BROWSER_APP)
        family = self._browser_family(app_name)
        target = str(url or "").strip()
        if family == "safari":
            target = target or "https://www.google.com"
            script = (
                f'tell application "{app_name}"\n'
                "    activate\n"
                "    if (count of windows) = 0 then make new document\n"
                f"    tell front window to set current tab to (make new tab with properties {{URL:{json.dumps(target)}}})\n"
                "end tell"
            )
        else:
            target = target or "chrome://newtab"
            script = (
                f'tell application "{app_name}"\n'
                "    activate\n"
                "    if (count of windows) = 0 then make new window\n"
                f"    make new tab at end of tabs of front window with properties {{URL:{json.dumps(target)}}}\n"
                "    set active tab index of front window to (count of tabs of front window)\n"
                "end tell"
            )
        try:
            self._run_osascript(script, timeout=10)
            return f"opened new browser tab: {target}"
        except Exception:
            return self.open_url_in_browser(target or "https://www.google.com", app_name)

    def browser_search(self, query: str, *, new_tab: bool = True) -> str:
        cleaned = " ".join(str(query or "").split()).strip()
        if not cleaned:
            return self.browser_new_tab()
        url = f"https://www.google.com/search?q={urllib.parse.quote_plus(cleaned)}"
        if new_tab:
            return self.browser_new_tab(url)
        return self.open_url_in_browser(url, DEFAULT_BROWSER_APP)

    def browser_close_tab(self) -> str:
        app_name = self._resolve_browser_app(DEFAULT_BROWSER_APP)
        if self._browser_family(app_name) == "safari":
            script = (
                f'tell application "{app_name}"\n'
                "    if (count of windows) = 0 then return\n"
                "    tell front window to close current tab\n"
                "end tell"
            )
        else:
            script = (
                f'tell application "{app_name}"\n'
                "    if (count of windows) = 0 then return\n"
                "    if (count of tabs of front window) > 0 then close active tab of front window\n"
                "end tell"
            )
        self._run_osascript(script, timeout=10)
        return "closed current browser tab"

    def browser_close_window(self) -> str:
        app_name = self._resolve_browser_app(DEFAULT_BROWSER_APP)
        script = (
            f'tell application "{app_name}"\n'
            "    if (count of windows) = 0 then return\n"
            "    close front window\n"
            "end tell"
        )
        self._run_osascript(script, timeout=10)
        return "closed current browser window"

    def browser_window(self, url: str = "") -> str:
        target = self._normalize_browser_url(url) if self._collapse_text(url) else ""
        script = (
            'tell application "Google Chrome"\n'
            "    activate\n"
            "    make new window\n"
            f'    if {self._applescript_string(target)} is not "" then set URL of active tab of front window to {self._applescript_string(target)}\n'
            "end tell"
        )
        self._run_osascript(script, timeout=10)
        return f"opened browser window{f': {target}' if target else ''}"

    def browser_go_back(self) -> str:
        script = (
            'tell application "Google Chrome"\n'
            "    if (count of windows) = 0 then return\n"
            "    tell active tab of front window to go back\n"
            "end tell"
        )
        self._run_osascript(script, timeout=5)
        return "went back in browser"

    def browser_refresh(self) -> str:
        script = (
            'tell application "Google Chrome"\n'
            "    if (count of windows) = 0 then return\n"
            "    tell active tab of front window to reload\n"
            "end tell"
        )
        self._run_osascript(script, timeout=5)
        return "reloaded browser tab"

    def browser_go_to(self, url: str) -> str:
        target = self._normalize_browser_url(url)
        script = (
            'tell application "Google Chrome"\n'
            "    activate\n"
            "    if (count of windows) = 0 then make new window\n"
            f"    set URL of active tab of front window to {self._applescript_string(target)}\n"
            "end tell"
        )
        self._run_osascript(script, timeout=8)
        return f"navigated browser to {target}"

    def pause_video(self) -> str:
        javascript = (
            '(function(){'
            'const media=[...document.querySelectorAll("video,audio")];'
            "media.forEach(node=>{try{node.pause();}catch(e){}});"
            "return media.length.toString();"
            "})()"
        )
        app_name = self._resolve_browser_app(DEFAULT_BROWSER_APP)
        if self._browser_family(app_name) == "safari":
            script = (
                f'tell application "{app_name}"\n'
                "    if (count of windows) = 0 then return\n"
                f"    do JavaScript {json.dumps(javascript)} in current tab of front window\n"
                "end tell"
            )
        else:
            script = (
                f'tell application "{app_name}"\n'
                "    if (count of windows) = 0 then return\n"
                f"    tell active tab of front window to execute javascript {json.dumps(javascript)}\n"
                "end tell"
        )
        self._run_osascript(script, timeout=10)
        return "paused media in browser"

    def volume_set(self, level: int) -> str:
        safe_level = max(0, min(100, int(level)))
        self._run_osascript(f"set volume output volume {safe_level}", timeout=5)
        return f"set system volume to {safe_level}"

    def system_volume_set(self, level: int) -> str:
        return self.volume_set(level)

    def volume_up(self) -> str:
        script = (
            "set currentVolume to output volume of (get volume settings)\n"
            "set targetVolume to currentVolume + 10\n"
            "if targetVolume > 100 then set targetVolume to 100\n"
            "set volume output volume targetVolume"
        )
        self._run_osascript(script, timeout=5)
        return "adjusted system volume up"

    def volume_down(self) -> str:
        script = (
            "set currentVolume to output volume of (get volume settings)\n"
            "set targetVolume to currentVolume - 10\n"
            "if targetVolume < 0 then set targetVolume to 0\n"
            "set volume output volume targetVolume"
        )
        self._run_osascript(script, timeout=5)
        return "adjusted system volume down"

    def system_volume_adjust(self, direction: str) -> str:
        return self.volume_up() if str(direction).lower() == "up" else self.volume_down()

    def brightness_up(self) -> str:
        self._run_osascript('tell application "System Events" to key code 144', timeout=5)
        return "brightness up"

    def brightness_down(self) -> str:
        self._run_osascript('tell application "System Events" to key code 145', timeout=5)
        return "brightness down"

    def lock_screen(self) -> str:
        self._run_osascript('tell application "System Events" to keystroke "q" using {control down, command down}', timeout=5)
        return "screen locked"

    def sleep_mac(self) -> str:
        self._run_osascript('tell application "Finder" to sleep', timeout=5)
        return "mac sleeping"

    def show_desktop(self) -> str:
        self._run_osascript('tell application "System Events" to key code 103', timeout=5)
        return "showed desktop"

    def dark_mode(self, enable: bool | None = None) -> str:
        if enable is None:
            script = 'tell app "System Events" to tell appearance preferences to set dark mode to not dark mode'
        else:
            script = (
                'tell app "System Events" to tell appearance preferences '
                f'to set dark mode to {"true" if enable else "false"}'
            )
        self._run_osascript(script, timeout=5)
        return "toggled dark mode"

    def do_not_disturb(self, enable: bool | None = None) -> str:
        target_value = ""
        if enable is not None:
            target_value = " on" if enable else " off"
        script = (
            'tell application "System Events"\n'
            '    tell process "ControlCenter"\n'
            "        set frontmost to true\n"
            '        click first menu bar item of menu bar 1 whose description contains "Control Center"\n'
            "        delay 0.6\n"
            "        try\n"
            '            click first checkbox of group 1 of window 1 whose description contains "Do Not Disturb"\n'
            "        on error\n"
            '            click first checkbox of window 1 whose description contains "Do Not Disturb"\n'
            "        end try\n"
            "        key code 53\n"
            "    end tell\n"
            "end tell"
        )
        self._run_osascript(script, timeout=8)
        return f"toggled do not disturb{target_value}"

    def system_info(self, query: str) -> str:
        lowered = self._collapse_text(query).lower()
        if "batt" in lowered:
            result = subprocess.run(["pmset", "-g", "batt"], capture_output=True, text=True, timeout=8)
            return self._collapse_text(result.stdout or result.stderr)
        if "wifi" in lowered or "wi-fi" in lowered:
            hardware = subprocess.run(
                ["networksetup", "-listallhardwareports"],
                capture_output=True,
                text=True,
                timeout=8,
            )
            device_match = re.search(r"Hardware Port: Wi-Fi\s+Device: (\w+)", hardware.stdout, flags=re.MULTILINE)
            device = device_match.group(1) if device_match else "en0"
            result = subprocess.run(
                ["networksetup", "-getairportnetwork", device],
                capture_output=True,
                text=True,
                timeout=8,
            )
            return self._collapse_text(result.stdout or result.stderr)
        if "storage" in lowered or "disk" in lowered:
            result = subprocess.run(["df", "-h", "/"], capture_output=True, text=True, timeout=8)
            lines = [self._collapse_text(line) for line in str(result.stdout or "").splitlines() if self._collapse_text(line)]
            return lines[-1] if lines else "storage unavailable"
        return "ask for battery, wifi, or storage"

    def take_screenshot(self, save: bool = True, describe: bool = False) -> str:
        path = Path("/tmp/burry_screen.png")
        subprocess.run(["screencapture", "-x", str(path)], timeout=10)
        if not describe:
            return str(path)
        description = self.read_screen()
        if not save:
            path.unlink(missing_ok=True)
        return description

    def read_screen(self) -> str:
        subprocess.run(["screencapture", "-x", "/tmp/burry_screen.png"], timeout=10)
        try:
            from agents.vision import describe_screen

            summary = self._collapse_text(describe_screen("Describe the screen briefly.") or "")
        except Exception:
            summary = ""
        if not summary:
            try:
                import pytesseract
                from PIL import Image

                text = pytesseract.image_to_string(Image.open("/tmp/burry_screen.png"))
                summary = self._summarize_text(text, "Summarize what is visible on screen in under 80 words.")
            except Exception:
                summary = "I couldn't read the screen clearly right now."
        self._speak(summary)
        return summary

    def summarize_page(self, url: str = "") -> str:
        target = self._collapse_text(url) or self._current_chrome_url()
        if not target:
            return "no browser page available"
        content = self._fetch_jina_reader(target)
        if not content:
            return "could not fetch the current page"
        summary = self._summarize_text(content, "Summarize this web page in under 120 words.")
        if summary:
            self._speak(summary)
        return summary or "could not summarize the page"

    def summarize_video(self, url: str = "", save_to_obsidian: bool = False) -> str:
        target = self._collapse_text(url) or self._current_chrome_url()
        if not target:
            return "no video url available"
        transcript_text = ""
        try:
            from youtube_transcript_api import YouTubeTranscriptApi

            video_id_match = re.search(r"(?:v=|youtu\.be/)([A-Za-z0-9_-]{11})", target)
            if video_id_match:
                transcript = YouTubeTranscriptApi.get_transcript(video_id_match.group(1))
                transcript_text = " ".join(str(item.get("text", "")).strip() for item in transcript)
        except Exception:
            transcript_text = ""
        if not transcript_text:
            transcript_text = self._fetch_jina_reader(target)
        if not transcript_text:
            return "could not fetch a transcript for that video"
        summary = self._summarize_text(transcript_text, "Summarize this video transcript in under 140 words.")
        if save_to_obsidian and summary:
            title = f"Video Summary {datetime.now().strftime('%Y-%m-%d %H-%M')}"
            self.obsidian_note(title, summary, folder="Daily")
        return summary or "could not summarize the video"

    def whatsapp_open(self, contact: str = "", phone: str = "") -> str:
        if phone:
            digits = "".join(ch for ch in str(phone) if ch.isdigit() or ch == "+").lstrip("+")
            if digits:
                self.open_url(f"https://wa.me/{digits}")
                return f"opened WhatsApp chat for {contact or phone}"
        self.open_url("https://web.whatsapp.com/")
        return f"opened WhatsApp{f' for {contact}' if contact else ''}"

    def whatsapp_send(self, contact: str = "", phone: str = "", message: str = "") -> str:
        cleaned_message = " ".join(str(message or "").split()).strip()
        digits = "".join(ch for ch in str(phone) if ch.isdigit() or ch == "+").lstrip("+")
        if digits:
            url = f"https://wa.me/{digits}"
            if cleaned_message:
                url = f"{url}?text={urllib.parse.quote_plus(cleaned_message)}"
            self.open_url(url)
            return f"opened WhatsApp message flow for {contact or phone}"
        self.open_url("https://web.whatsapp.com/")
        return f"opened WhatsApp to message {contact or 'the contact'}"

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

    def git_action(self, command: str, cwd: str | None = None, message: str = "", push: bool = False) -> str:
        normalized = self._collapse_text(command).lower()
        cwd_expanded = os.path.expanduser(cwd) if cwd else os.path.expanduser("~/Burry/mac-butler")
        if normalized == "status":
            return self.run_command("git status --short", cwd=cwd_expanded)
        if normalized == "log":
            return self.run_command("git log --oneline -5", cwd=cwd_expanded)
        if normalized == "diff":
            return self.run_command("git diff", cwd=cwd_expanded)
        if normalized == "push":
            return self.run_command("git push", cwd=cwd_expanded)
        if normalized == "commit":
            commit_message = self._collapse_text(message) or "Update changes"
            result = subprocess.run(
                ["git", "commit", "-m", commit_message],
                cwd=cwd_expanded,
                capture_output=True,
                text=True,
                timeout=30,
            )
            output = self._collapse_text(result.stdout or result.stderr)
            if push:
                push_output = self.run_command("git push", cwd=cwd_expanded)
                output = f"{output}. {push_output}"
            return output or commit_message
        if normalized in {"commit_push", "commit and push"}:
            return self.git_action("commit", cwd=cwd_expanded, message=message, push=True)
        raise ValueError(f"unsupported git action: {command}")

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
        if t == "git_action":
            normalized = self._collapse_text(action.get("cmd", "")).lower()
            return normalized in {"push", "commit_push", "commit and push"} or bool(action.get("push"))
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
            pass

        if sys.stdin and not sys.stdin.closed and sys.stdin.isatty():
            response = input(f"[Butler] Run '{desc}'? (y/n): ").strip().lower()
            return response == "y"

        from runtime import clear_confirmation, load_runtime_state, request_confirmation, resolve_confirmation
        from voice import speak

        waiting_message = (
            "I need your confirmation before pushing. Say yes or check the HUD."
            if "git push" in str(desc).lower()
            else "I need your confirmation before running that. Say yes or check the HUD."
        )
        skip_message = (
            "Skipping push - no confirmation received."
            if "git push" in str(desc).lower()
            else "Skipping that action - no confirmation received."
        )
        prompt = f"Confirm action: {desc}"
        pending = request_confirmation(prompt, action=action.get("type", ""), timeout_s=30)
        try:
            speak(waiting_message)
        except Exception:
            pass

        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            runtime_state = load_runtime_state()
            current = runtime_state.get("pending_confirmation", {}) if isinstance(runtime_state, dict) else {}
            if current.get("id") != pending.get("id"):
                time.sleep(0.25)
                continue
            status = str(current.get("status", "")).strip().lower()
            if status == "approved":
                clear_confirmation(pending["id"])
                return True
            if status == "rejected":
                clear_confirmation(pending["id"])
                return False
            time.sleep(0.25)

        resolve_confirmation(pending["id"], "timeout")
        try:
            speak(skip_message)
        except Exception:
            pass
        clear_confirmation(pending["id"])
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
