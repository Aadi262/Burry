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
import html
from datetime import datetime, timedelta
from pathlib import Path
import xml.etree.ElementTree as ET

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
    "desktop": "~/Desktop",
    "on the desktop": "~/Desktop",
    "on desktop": "~/Desktop",
    "documents": "~/Documents",
    "in documents": "~/Documents",
    "in the documents": "~/Documents",
    "downloads": "~/Downloads",
    "in downloads": "~/Downloads",
    "in the downloads": "~/Downloads",
    "home": "~",
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
        if cleaned.startswith(("http://", "https://", "chrome://", "file://", "about:", "data:")):
            return cleaned
        return f"https://{cleaned}"

    @staticmethod
    def _web_headers(accept: str = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8") -> dict[str, str]:
        return {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9,hi-IN;q=0.7,hi;q=0.6",
            "Accept": accept,
        }

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

    @staticmethod
    def _automation_access_unavailable(message: str) -> bool:
        lowered = " ".join(str(message or "").split()).lower()
        return any(
            marker in lowered
            for marker in (
                "connection invalid",
                "parameter is missing",
                "application can't be found",
                "application isn’t running",
                "application isn't running",
                "can’t get application",
                "can't get application",
                "file calendar wasn’t found",
                "file calendar wasn't found",
                "not authorized",
                "not permitted",
                "(-1701)",
                "(-1743)",
                "(-600)",
                "(-10827)",
                "(-1728)",
                "(-43)",
            )
        )

    @staticmethod
    def _calendar_write_unavailable_message() -> str:
        return "Calendar event creation is unavailable until Calendar automation access is granted on this host."

    @staticmethod
    def _reminders_unavailable_message() -> str:
        return "Reminder creation is unavailable until Reminders automation access is granted on this host."

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
            from butler_config import TOOL_SUMMARIZER_MODEL

            prompt = f"{instruction}\n\n{cleaned[:12000]}"
            return self._collapse_text(_call(prompt, TOOL_SUMMARIZER_MODEL, temperature=0.1, max_tokens=220))
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

    def _app_snapshot(self, app_name: str) -> dict:
        try:
            from executor.app_state import get_app_state

            snapshot = dict(get_app_state(app_name) or {})
        except Exception:
            snapshot = {"running": False, "window_count": 0, "focused": False}
        snapshot["app"] = str(app_name or "").strip()
        return snapshot

    def _terminal_snapshot(self) -> dict:
        try:
            from executor.app_state import get_terminal_tab_count, get_window_count, is_app_running

            running = bool(is_app_running("Terminal"))
            return {
                "running": running,
                "window_count": int(get_window_count("Terminal") if running else 0),
                "tab_count": int(get_terminal_tab_count() if running else 0),
            }
        except Exception:
            return {"running": False, "window_count": 0, "tab_count": 0}

    def _current_browser_url(self, app_name: str = DEFAULT_BROWSER_APP) -> str:
        app = self._resolve_browser_app(app_name)
        family = self._browser_family(app)
        if family == "safari":
            script = (
                f'tell application "{app}"\n'
                "    if (count of windows) = 0 then return \"\"\n"
                "    return URL of current tab of front window\n"
                "end tell"
            )
        else:
            script = (
                f'tell application "{app}"\n'
                "    if (count of windows) = 0 then return \"\"\n"
                "    return URL of active tab of front window\n"
                "end tell"
            )
        try:
            result = self._run_osascript(script, timeout=4)
            return self._collapse_text(result.stdout)
        except Exception:
            return ""

    def _browser_snapshot(self, app_name: str = DEFAULT_BROWSER_APP) -> dict:
        app = self._resolve_browser_app(app_name)
        snapshot = {
            "app": app,
            "running": self._is_app_running(app),
            "window_count": 0,
            "tab_count": 0,
            "url": "",
        }
        if not snapshot["running"]:
            return snapshot

        family = self._browser_family(app)
        if family == "safari":
            script = (
                f'tell application "{app}"\n'
                "    if (count of windows) = 0 then return \"0|0|\"\n"
                "    set windowCount to count of windows\n"
                "    set tabCount to count of tabs of front window\n"
                "    set currentUrl to URL of current tab of front window\n"
                "    return (windowCount as text) & \"|\" & (tabCount as text) & \"|\" & currentUrl\n"
                "end tell"
            )
        else:
            script = (
                f'tell application "{app}"\n'
                "    if (count of windows) = 0 then return \"0|0|\"\n"
                "    set windowCount to count of windows\n"
                "    set tabCount to count of tabs of front window\n"
                "    set currentUrl to URL of active tab of front window\n"
                "    return (windowCount as text) & \"|\" & (tabCount as text) & \"|\" & currentUrl\n"
                "end tell"
            )
        try:
            result = self._run_osascript(script, timeout=5)
            parts = str(result.stdout or "").strip().split("|", 2)
            snapshot["window_count"] = int(parts[0] or "0")
            snapshot["tab_count"] = int(parts[1] or "0")
            snapshot["url"] = self._collapse_text(parts[2] if len(parts) > 2 else "")
        except Exception:
            snapshot["url"] = self._current_browser_url(app)
        return snapshot

    def _calendar_event_exists(self, title: str) -> bool:
        cleaned_title = self._collapse_text(title)
        if not cleaned_title:
            return False
        script = f'''
tell application "Calendar"
    set lookupStart to (current date) - 1 * days
    set lookupEnd to (current date) + 7 * days
    repeat with c in calendars
        try
            repeat with e in (events of c whose start date >= lookupStart and start date <= lookupEnd)
                if (summary of e as string) contains {self._applescript_string(cleaned_title)} then return "true"
            end repeat
        end try
    end repeat
    return "false"
end tell
'''
        try:
            result = self._run_osascript(script, timeout=6)
            return self._collapse_text(result.stdout).lower() == "true"
        except Exception:
            return False

    def _natural_datetime(self, value: str) -> datetime | None:
        lowered = self._collapse_text(value).lower()
        if not lowered:
            return None

        now = datetime.now()
        target_date = now.date()
        explicit_day = False

        if "day after tomorrow" in lowered:
            target_date = (now + timedelta(days=2)).date()
            explicit_day = True
        elif "tomorrow" in lowered:
            target_date = (now + timedelta(days=1)).date()
            explicit_day = True
        elif "today" in lowered:
            target_date = now.date()
            explicit_day = True
        else:
            weekdays = {
                "monday": 0,
                "tuesday": 1,
                "wednesday": 2,
                "thursday": 3,
                "friday": 4,
                "saturday": 5,
                "sunday": 6,
            }
            for name, weekday in weekdays.items():
                if name in lowered:
                    delta = (weekday - now.weekday()) % 7
                    delta = 7 if delta == 0 else delta
                    target_date = (now + timedelta(days=delta)).date()
                    explicit_day = True
                    break

        time_match = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", lowered)
        if time_match:
            hour = int(time_match.group(1))
            minute = int(time_match.group(2) or "0")
            meridiem = time_match.group(3)
            hour = hour % 12
            if meridiem == "pm":
                hour += 12
        elif "noon" in lowered:
            hour, minute = 12, 0
        elif "midnight" in lowered:
            hour, minute = 0, 0
        elif "morning" in lowered:
            hour, minute = 9, 0
        elif "afternoon" in lowered:
            hour, minute = 15, 0
        elif "evening" in lowered:
            hour, minute = 18, 0
        elif "night" in lowered or "tonight" in lowered:
            hour, minute = 21, 0
        else:
            return None

        parsed = datetime.combine(target_date, datetime.min.time()).replace(hour=hour, minute=minute)
        if not explicit_day and parsed <= now:
            parsed += timedelta(days=1)
        return parsed

    def _applescript_date_expression(self, value: str) -> str:
        parsed = self._natural_datetime(value)
        if parsed is None:
            return f"date {self._applescript_string(value)}"
        formatted = parsed.strftime("%d %B %Y %I:%M:%S %p")
        return f"date {self._applescript_string(formatted)}"

    def _reminder_exists(self, title: str) -> bool:
        cleaned_title = self._collapse_text(title)
        if not cleaned_title:
            return False
        script = f'''
tell application "Reminders"
    repeat with reminderList in lists
        try
            repeat with reminderItem in reminders of reminderList
                if (name of reminderItem as string) contains {self._applescript_string(cleaned_title)} then return "true"
            end repeat
        end try
    end repeat
    return "false"
end tell
'''
        try:
            result = self._run_osascript(script, timeout=6)
            return self._collapse_text(result.stdout).lower() == "true"
        except Exception:
            return False

    def _retry_snapshot(self, loader, predicate, attempts: int = 4, delay: float = 0.25):
        last = None
        for index in range(max(1, attempts)):
            last = loader()
            try:
                if predicate(last):
                    return last
            except Exception:
                return last
            if index < attempts - 1:
                time.sleep(delay)
        return last

    def _verification_payload(self, status: str, detail: str) -> dict:
        return {
            "verification_status": str(status or "").strip() or "degraded",
            "verification_detail": self._collapse_text(detail),
        }

    def _action_target_path(self, action: dict) -> str:
        action_type = str(action.get("type", "") or "").strip()
        if action_type == "create_folder":
            return str(self._resolve_folder_target(action.get("path", ""), action.get("name", "")))
        if action_type in {"open_file", "read_file", "write_file", "delete_file"}:
            try:
                must_exist = action_type in {"open_file", "read_file", "delete_file"}
                return str(self._resolve_file_target(action.get("path", ""), must_exist=must_exist))
            except Exception:
                return os.path.expanduser(str(action.get("path", "") or ""))
        if action_type == "create_file_in_editor":
            directory = os.path.expanduser(str(action.get("directory", "") or "~/Developer"))
            filename = str(action.get("filename", "") or "").strip()
            return str(Path(directory) / filename) if filename else directory
        if action_type == "zip_folder":
            try:
                target = self._resolve_file_target(action.get("path", ""), must_exist=True, allow_directory=True)
                return str(target.parent / f"{target.name}.zip")
            except Exception:
                raw = os.path.expanduser(str(action.get("path", "") or ""))
                target = Path(raw)
                return str(target.parent / f"{target.name}.zip") if raw else ""
        if action_type == "copy_file":
            try:
                source = self._resolve_file_target(action.get("from", ""), must_exist=False)
                return str(self._resolve_destination_target(action.get("to", ""), source))
            except Exception:
                return os.path.expanduser(str(action.get("to", "") or ""))
        if action_type == "move_file":
            try:
                source = self._resolve_file_target(action.get("from", ""), must_exist=False)
                return str(self._resolve_destination_target(action.get("to", ""), source))
            except Exception:
                return os.path.expanduser(str(action.get("to", "") or ""))
        if action_type == "create_and_open":
            return os.path.expanduser(str(action.get("path", "") or ""))
        return os.path.expanduser(str(action.get("path", "") or ""))

    def _compose_browser_target(self, action: dict) -> str:
        action_type = str(action.get("type", "") or "").strip()
        if action_type == "compose_email":
            return "mail.google.com"
        if action_type in {"whatsapp_open", "whatsapp_send", "compose_whatsapp"}:
            phone = "".join(ch for ch in str(action.get("phone", "")) if ch.isdigit() or ch == "+").lstrip("+")
            if phone:
                return f"wa.me/{phone}"
            return "web.whatsapp.com"
        if action_type == "browser_search":
            query = self._collapse_text(action.get("query", ""))
            if not query:
                return "google.com"
            return f"google.com/search?q={urllib.parse.quote_plus(query)}"
        if action_type == "browser_new_tab":
            target = self._collapse_text(action.get("url", ""))
            return self._normalize_browser_url(target) if target else ""
        if action_type == "open_url":
            return self._normalize_browser_url(self._map_url(action.get("url", "")))
        if action_type == "open_url_in_browser":
            return self._normalize_browser_url(self._map_url(action.get("url", "")))
        if action_type == "browser_go_to":
            return self._normalize_browser_url(action.get("url", ""))
        if action_type == "browser_window":
            target = self._collapse_text(action.get("url", ""))
            return self._normalize_browser_url(target) if target else ""
        return ""

    def _capture_verification_state(self, action: dict) -> dict:
        action_type = str(action.get("type", "") or "").strip()
        if action_type in {"open_terminal", "open_terminal_command"}:
            snapshot = self._terminal_snapshot()
            snapshot["kind"] = "terminal"
            return snapshot
        if action_type == "run_command" and bool(action.get("in_terminal", False)):
            snapshot = self._terminal_snapshot()
            snapshot["kind"] = "terminal"
            return snapshot
        if action_type in {
            "open_url",
            "open_url_in_browser",
            "browser_new_tab",
            "browser_search",
            "browser_close_tab",
            "browser_close_window",
            "browser_window",
            "browser_go_back",
            "browser_refresh",
            "browser_go_to",
            "compose_email",
            "whatsapp_open",
            "whatsapp_send",
            "compose_whatsapp",
        }:
            snapshot = self._browser_snapshot(str(action.get("app", DEFAULT_BROWSER_APP) or DEFAULT_BROWSER_APP))
            snapshot["kind"] = "browser"
            return snapshot
        if action_type == "open_project":
            snapshot = {"kind": "project", "path": "", "app": ""}
            try:
                from projects import get_project

                project = get_project(action.get("name", ""), hydrate_blurb=True)
            except Exception:
                project = None
            if project:
                snapshot["path"] = os.path.expanduser(str(project.get("path", "") or ""))
            editor = str(action.get("editor", "") or "").strip().lower()
            if editor == "cursor":
                snapshot["app"] = "Cursor"
            elif editor in {"vscode", "code", "visual studio code"}:
                snapshot["app"] = "Visual Studio Code"
            return snapshot
        if action_type == "send_email":
            snapshot = self._app_snapshot("Mail")
            snapshot["kind"] = "mail"
            return snapshot
        if action_type == "send_whatsapp":
            snapshot = self._app_snapshot("WhatsApp")
            snapshot["kind"] = "whatsapp_app"
            return snapshot
        return {}

    def _verify_action_result(self, action: dict, raw_result: str, before: dict | None = None) -> dict:
        before = dict(before or {})
        action_type = str(action.get("type", "") or "").strip()
        if action_type == "create_file":
            path = self._action_target_path(action)
            if Path(path).is_file():
                return self._verification_payload("verified", f"Confirmed the file exists at {path}.")
            return self._verification_payload("failed", f"I couldn't confirm the file was created at {path}.")
        if action_type == "open_file":
            path = self._action_target_path(action)
            if Path(path).is_file():
                return self._verification_payload("verified", f"Confirmed the file exists at {path}.")
            return self._verification_payload("failed", f"I couldn't confirm the file exists at {path}.")
        if action_type == "write_file":
            path = self._action_target_path(action)
            file_path = Path(path)
            if not file_path.is_file():
                return self._verification_payload("failed", f"I couldn't confirm the file exists at {path}.")
            expected = str(action.get("content", "") or "")
            try:
                actual = file_path.read_text(encoding="utf-8")
            except Exception:
                actual = ""
            mode = str(action.get("mode", "overwrite") or "overwrite").strip().lower()
            matches = expected in actual if mode == "append" else actual == expected
            if matches or not expected:
                return self._verification_payload("verified", f"Confirmed the file was updated at {path}.")
            return self._verification_payload("failed", f"I couldn't confirm the file contents were updated at {path}.")
        if action_type == "delete_file":
            path = self._action_target_path(action)
            if not Path(path).exists():
                return self._verification_payload("verified", f"Confirmed the file was removed from {path}.")
            return self._verification_payload("failed", f"I couldn't confirm the file was deleted from {path}.")
        if action_type == "zip_folder":
            path = self._action_target_path(action)
            if Path(path).is_file():
                return self._verification_payload("verified", f"Confirmed the zip archive exists at {path}.")
            return self._verification_payload("failed", f"I couldn't confirm the zip archive exists at {path}.")
        if action_type == "copy_file":
            source = self._resolve_file_target(action.get("from", ""), must_exist=False)
            destination = self._resolve_destination_target(action.get("to", ""), source)
            if destination.exists() and source.exists():
                return self._verification_payload("verified", f"Confirmed the file was copied to {destination}.")
            return self._verification_payload("failed", f"I couldn't confirm the file was copied to {destination}.")
        if action_type == "move_file":
            source = self._resolve_file_target(action.get("from", ""), must_exist=False)
            destination = self._resolve_destination_target(action.get("to", ""), source)
            if destination.exists() and not source.exists():
                return self._verification_payload("verified", f"Confirmed the file moved to {destination}.")
            return self._verification_payload("failed", f"I couldn't confirm the file moved to {destination}.")
        if action_type == "create_folder":
            path = self._action_target_path(action)
            if Path(path).is_dir():
                return self._verification_payload("verified", f"Confirmed the folder exists at {path}.")
            return self._verification_payload("failed", f"I couldn't confirm the folder was created at {path}.")
        if action_type == "create_and_open":
            path = self._action_target_path(action)
            if Path(path).is_dir():
                return self._verification_payload("verified", f"Confirmed the folder exists at {path}.")
            return self._verification_payload("failed", f"I couldn't confirm the folder exists at {path}.")
        if action_type == "create_file_in_editor":
            path = self._action_target_path(action)
            if Path(path).is_file():
                return self._verification_payload("verified", f"Confirmed the file exists at {path}.")
            return self._verification_payload("failed", f"I couldn't confirm the file was created at {path}.")
        if action_type == "open_folder":
            path = self._action_target_path(action)
            if Path(path).exists():
                return self._verification_payload("verified", f"Confirmed the folder exists at {path}.")
            return self._verification_payload("failed", f"I couldn't confirm the folder exists at {path}.")
        if action_type == "open_project":
            path = str(before.get("path", "") or "").strip()
            if path and not Path(path).exists():
                return self._verification_payload("failed", f"I couldn't confirm the project path exists at {path}.")
            expected_app = str(before.get("app", "") or "").strip()
            if expected_app:
                observed = self._retry_snapshot(lambda: self._app_snapshot(expected_app), lambda item: bool(item.get("running")))
                if observed and observed.get("running"):
                    project_label = Path(path).name if path else str(action.get("name", "") or "the project").strip()
                    return self._verification_payload("verified", f"Confirmed {project_label} opened in {expected_app}.")
            if path and Path(path).exists():
                return self._verification_payload("degraded", f"The project path exists at {path}, but I couldn't verify the editor launch.")
            return self._verification_payload("degraded", "I ran the project open flow, but I couldn't verify the editor launch.")
        if action_type in {"open_terminal", "open_terminal_command"} or (
            action_type == "run_command" and bool(action.get("in_terminal", False))
        ):
            observed = self._retry_snapshot(
                self._terminal_snapshot,
                lambda item: bool(item.get("running")) and (
                    int(item.get("tab_count", 0)) > int(before.get("tab_count", 0))
                    or int(item.get("window_count", 0)) > int(before.get("window_count", 0))
                    or not bool(before.get("running"))
                ),
            )
            if observed and observed.get("running") and (
                int(observed.get("tab_count", 0)) > int(before.get("tab_count", 0))
                or int(observed.get("window_count", 0)) > int(before.get("window_count", 0))
                or not bool(before.get("running"))
            ):
                return self._verification_payload("verified", "Confirmed Terminal opened and accepted the command.")
            return self._verification_payload("degraded", "Terminal handled the request, but I couldn't confirm a new tab or window.")
        if action_type == "run_command":
            return self._verification_payload("verified", "Confirmed the command exited successfully.")
        if action_type in {
            "open_url",
            "open_url_in_browser",
            "browser_new_tab",
            "browser_search",
            "browser_close_tab",
            "browser_close_window",
            "browser_window",
            "browser_go_back",
            "browser_refresh",
            "browser_go_to",
            "compose_email",
            "whatsapp_open",
            "whatsapp_send",
            "compose_whatsapp",
        }:
            browser_app = str(before.get("app", DEFAULT_BROWSER_APP) or DEFAULT_BROWSER_APP)
            expected_target = self._compose_browser_target(action)
            if action_type in {"browser_close_tab", "browser_close_window"}:
                observed = self._retry_snapshot(
                    lambda: self._browser_snapshot(browser_app),
                    lambda item: int(item.get("window_count", 0)) < int(before.get("window_count", 0))
                    or int(item.get("tab_count", 0)) < int(before.get("tab_count", 0))
                    or int(item.get("window_count", 0)) == 0,
                )
                if observed and (
                    int(observed.get("window_count", 0)) < int(before.get("window_count", 0))
                    or int(observed.get("tab_count", 0)) < int(before.get("tab_count", 0))
                    or int(observed.get("window_count", 0)) == 0
                ):
                    noun = "window" if action_type == "browser_close_window" else "tab"
                    return self._verification_payload("verified", f"Confirmed the browser {noun} was closed.")
                noun = "window" if action_type == "browser_close_window" else "tab"
                return self._verification_payload("degraded", f"I ran the browser close request, but I couldn't confirm the {noun} count changed.")

            if action_type == "browser_go_back":
                previous_url = self._collapse_text(before.get("url", "")).lower()
                observed = self._retry_snapshot(
                    lambda: self._browser_snapshot(browser_app),
                    lambda item: bool(self._collapse_text(item.get("url", ""))) and self._collapse_text(item.get("url", "")).lower() != previous_url,
                )
                if observed and self._collapse_text(observed.get("url", "")).lower() != previous_url:
                    observed_url = self._collapse_text(observed.get("url", ""))
                    return self._verification_payload("verified", f"Confirmed the browser navigated back to {observed_url}.")
                return self._verification_payload("degraded", "I ran the browser back request, but I couldn't confirm the page changed.")

            if action_type == "browser_refresh":
                previous_url = self._collapse_text(before.get("url", ""))
                observed = self._retry_snapshot(
                    lambda: self._browser_snapshot(browser_app),
                    lambda item: bool(item.get("running")) and (
                        self._collapse_text(item.get("url", "")) == previous_url or bool(self._collapse_text(item.get("url", "")))
                    ),
                )
                if observed and bool(observed.get("running")):
                    observed_url = self._collapse_text(observed.get("url", "")) or previous_url
                    if observed_url:
                        return self._verification_payload("verified", f"Confirmed the browser refreshed {observed_url}.")
                    return self._verification_payload("verified", "Confirmed the browser handled the refresh request.")
                return self._verification_payload("degraded", "I ran the browser refresh request, but I couldn't confirm the page refreshed.")

            def _browser_matches(item: dict) -> bool:
                observed_url = self._collapse_text(item.get("url", "")).lower()
                if not observed_url and expected_target:
                    return False
                if expected_target:
                    expected = self._collapse_text(expected_target).lower()
                    return expected in observed_url or observed_url.startswith(expected)
                return bool(item.get("running")) and (
                    int(item.get("tab_count", 0)) > int(before.get("tab_count", 0))
                    or int(item.get("window_count", 0)) > int(before.get("window_count", 0))
                )

            observed = self._retry_snapshot(lambda: self._browser_snapshot(browser_app), _browser_matches)
            if observed and _browser_matches(observed):
                observed_url = self._collapse_text(observed.get("url", ""))
                if action_type == "compose_email":
                    return self._verification_payload("verified", "Confirmed Gmail compose is open.")
                if action_type == "whatsapp_send":
                    return self._verification_payload("degraded", "Opened WhatsApp message flow, but I couldn't confirm the message was sent.")
                if action_type == "compose_whatsapp":
                    return self._verification_payload("degraded", "Opened WhatsApp compose flow, but I couldn't confirm a sent message.")
                if action_type == "whatsapp_open":
                    return self._verification_payload("verified", "Confirmed WhatsApp opened in the browser.")
                if observed_url:
                    return self._verification_payload("verified", f"Confirmed the browser is on {observed_url}.")
                return self._verification_payload("verified", "Confirmed the browser handled the request.")
            if action_type in {"whatsapp_send", "compose_whatsapp"}:
                return self._verification_payload("degraded", "I opened WhatsApp, but I couldn't confirm the message flow on screen.")
            if action_type == "compose_email":
                return self._verification_payload("degraded", "I opened the Gmail compose flow, but I couldn't confirm the draft on screen.")
            return self._verification_payload("degraded", "I ran the browser action, but I couldn't confirm the page state.")
        if action_type == "calendar_add":
            if self._calendar_write_unavailable_message().lower() in self._collapse_text(raw_result).lower():
                return self._verification_payload("degraded", raw_result)
            title = self._collapse_text(action.get("title", "")) or self._collapse_text(raw_result)
            observed = self._retry_snapshot(lambda: {"found": self._calendar_event_exists(title)}, lambda item: bool(item.get("found")), attempts=3, delay=0.3)
            if observed and observed.get("found"):
                return self._verification_payload("verified", f"Confirmed the calendar event exists for {title}.")
            return self._verification_payload("failed", f"I couldn't confirm the calendar event exists for {title or 'that event'}.")
        if action_type == "send_email":
            observed = self._retry_snapshot(lambda: self._app_snapshot("Mail"), lambda item: bool(item.get("running")), attempts=2, delay=0.2)
            if observed and observed.get("running"):
                return self._verification_payload("degraded", "Mail accepted the send request, but I couldn't confirm delivery.")
            return self._verification_payload("degraded", "I ran the email send flow, but I couldn't confirm delivery.")
        if action_type == "send_whatsapp":
            observed = self._retry_snapshot(lambda: self._app_snapshot("WhatsApp"), lambda item: bool(item.get("running")), attempts=2, delay=0.2)
            if observed and observed.get("running"):
                return self._verification_payload("degraded", "WhatsApp opened, but I couldn't confirm the message was delivered.")
            return self._verification_payload("degraded", "I ran the WhatsApp send flow, but I couldn't confirm delivery.")
        if action_type in {"remind_in", "set_reminder"}:
            if self._reminders_unavailable_message().lower() in self._collapse_text(raw_result).lower():
                return self._verification_payload("degraded", raw_result)
            title = self._collapse_text(action.get("message", "")) or self._collapse_text(raw_result)
            observed = self._retry_snapshot(lambda: {"found": self._reminder_exists(title)}, lambda item: bool(item.get("found")), attempts=3, delay=0.3)
            if observed and observed.get("found"):
                return self._verification_payload("verified", f"Confirmed the reminder exists for {title}.")
            return self._verification_payload("failed", f"I couldn't confirm the reminder exists for {title or 'that reminder'}.")
        return {}

    def _fetch_jina_reader(self, url: str) -> str:
        target = self._normalize_browser_url(url)
        try:
            import requests

            response = requests.get(
                f"https://r.jina.ai/{target}",
                headers={**self._web_headers("text/plain,*/*;q=0.8"), "X-Return-Format": "text"},
                timeout=10,
            )
            if response.status_code != 200:
                return ""
            return str(response.text or "")
        except Exception:
            return ""

    def _fetch_url_text(self, url: str, *, accept: str = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8", extract_html: bool = True) -> str:
        target = str(url or "").strip()
        if not target.startswith(("http://", "https://")):
            return ""
        try:
            import requests

            response = requests.get(target, headers=self._web_headers(accept), timeout=10)
            if response.status_code != 200:
                return ""
            payload = str(response.text or "")
            if not payload:
                return ""
            headers = getattr(response, "headers", {}) or {}
            content_type = str(headers.get("content-type", "")).lower()
            if extract_html and ("html" in content_type or "<html" in payload.lower()):
                return self._extract_html_text(payload)
            return payload
        except Exception:
            return ""

    def _extract_html_text(self, document: str) -> str:
        raw = str(document or "")
        if not raw:
            return ""

        parts: list[str] = []

        title_match = re.search(r"(?is)<title[^>]*>(.*?)</title>", raw)
        if title_match:
            title = self._collapse_text(html.unescape(re.sub(r"(?is)<[^>]+>", " ", title_match.group(1))))
            if title:
                parts.append(title)

        meta_patterns = (
            r'(?is)<meta[^>]+property=["\']og:description["\'][^>]+content=["\'](.*?)["\']',
            r'(?is)<meta[^>]+content=["\'](.*?)["\'][^>]+property=["\']og:description["\']',
            r'(?is)<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']',
            r'(?is)<meta[^>]+content=["\'](.*?)["\'][^>]+name=["\']description["\']',
        )
        for pattern in meta_patterns:
            match = re.search(pattern, raw)
            if not match:
                continue
            description = self._collapse_text(html.unescape(re.sub(r"(?is)<[^>]+>", " ", match.group(1))))
            if description and description not in parts:
                parts.append(description)
                break

        cleaned = re.sub(r"(?is)<(script|style|noscript|svg|iframe)[^>]*>.*?</\1>", " ", raw)
        cleaned = re.sub(r"(?i)<br\s*/?>", "\n", cleaned)
        cleaned = re.sub(r"(?i)</(?:p|div|section|article|li|ul|ol|h[1-6]|tr|td|blockquote)>", "\n", cleaned)
        cleaned = re.sub(r"(?s)<[^>]+>", " ", cleaned)
        cleaned = html.unescape(cleaned)
        cleaned = re.sub(r"[ \t]+", " ", cleaned)
        lines = [self._collapse_text(line) for line in re.split(r"[\r\n]+", cleaned)]
        body = "\n".join(line for line in lines if line)
        if body:
            parts.append(body)

        return "\n\n".join(part for part in parts if part)[:24000]

    def _subtitle_items_to_text(self, items: list[dict] | tuple[dict, ...]) -> str:
        parts: list[str] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            text = self._collapse_text(html.unescape(str(item.get("text", "") or "")))
            if text:
                parts.append(text)
        return " ".join(parts)

    def _youtube_transcript_with_api(self, target: str) -> str:
        try:
            from youtube_transcript_api import YouTubeTranscriptApi
        except Exception:
            return ""

        video_id = self._youtube_video_id(target)
        if not video_id:
            return ""
        try:
            transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=["en", "hi"])
        except TypeError:
            try:
                transcript = YouTubeTranscriptApi.get_transcript(video_id)
            except Exception:
                return ""
        except Exception:
            return ""
        return self._subtitle_items_to_text(transcript)

    def _youtube_caption_tracks(self, target: str) -> list[dict]:
        video_id = self._youtube_video_id(target)
        if not video_id:
            return []
        watch_html = self._fetch_url_text(f"https://www.youtube.com/watch?v={video_id}", extract_html=False)
        if not watch_html:
            return []

        patterns = (
            r'"captionTracks":(\[.*?\])',
            r'"captions":\{"playerCaptionsTracklistRenderer":\{"captionTracks":(\[.*?\])',
        )
        for pattern in patterns:
            match = re.search(pattern, watch_html, re.DOTALL)
            if not match:
                continue
            try:
                tracks = json.loads(match.group(1))
            except json.JSONDecodeError:
                continue
            if isinstance(tracks, list):
                return [track for track in tracks if isinstance(track, dict) and track.get("baseUrl")]
        return []

    @staticmethod
    def _youtube_caption_track_sort_key(track: dict) -> tuple[int, int, str]:
        language = str(track.get("languageCode", "") or "")
        preferred = {
            "en": 0,
            "en-US": 1,
            "en-GB": 2,
            "hi": 3,
            "hi-IN": 4,
        }
        kind = str(track.get("kind", "") or "").lower()
        return (0 if kind != "asr" else 1, preferred.get(language, 99), language or "zz")

    def _youtube_caption_track_text(self, track: dict) -> str:
        base_url = html.unescape(str(track.get("baseUrl", "") or "")).strip()
        if not base_url:
            return ""
        payload = self._fetch_url_text(base_url, accept="application/xml,text/xml,text/plain,*/*;q=0.8", extract_html=False)
        if not payload:
            return ""

        parts: list[str] = []
        try:
            root = ET.fromstring(payload)
            for node in root.findall(".//text"):
                text = self._collapse_text(html.unescape(" ".join(node.itertext())))
                if text:
                    parts.append(text)
        except ET.ParseError:
            for match in re.findall(r"(?is)<text[^>]*>(.*?)</text>", payload):
                text = self._collapse_text(html.unescape(re.sub(r"(?is)<[^>]+>", " ", match)))
                if text:
                    parts.append(text)
        return " ".join(parts)

    def _youtube_transcript_from_caption_tracks(self, target: str) -> str:
        tracks = sorted(self._youtube_caption_tracks(target), key=self._youtube_caption_track_sort_key)
        for track in tracks:
            transcript = self._youtube_caption_track_text(track)
            if transcript:
                return transcript
        return ""

    def _subtitles_from_ytdlp(self, target: str) -> str:
        yt_dlp = self._safe_which("yt-dlp")
        if not yt_dlp:
            return ""

        scratch = Path("/tmp/burry_video_transcript")
        scratch.mkdir(parents=True, exist_ok=True)
        existing_files = {item.resolve() for item in scratch.glob("*.vtt")}
        output_template = scratch / "%(id)s.%(ext)s"
        download = subprocess.run(
            [
                yt_dlp,
                "--skip-download",
                "--write-auto-subs",
                "--write-subs",
                "--sub-langs",
                "en.*,hi.*,en,hi",
                "--sub-format",
                "vtt",
                "--no-playlist",
                "-o",
                str(output_template),
                target,
            ],
            capture_output=True,
            text=True,
            timeout=180,
        )
        if download.returncode != 0:
            return ""

        subtitle_files = sorted(
            (item for item in scratch.glob("*.vtt") if item.resolve() not in existing_files),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
        if not subtitle_files:
            return ""
        return self._vtt_to_text(subtitle_files[0].read_text(encoding="utf-8", errors="ignore"))

    def _vtt_to_text(self, document: str) -> str:
        raw = str(document or "")
        if not raw:
            return ""
        parts: list[str] = []
        for line in raw.splitlines():
            cleaned = self._collapse_text(html.unescape(re.sub(r"(?is)<[^>]+>", " ", line)))
            if not cleaned:
                continue
            if cleaned == "WEBVTT" or cleaned.startswith(("Kind:", "Language:", "NOTE")):
                continue
            if "-->" in cleaned or re.fullmatch(r"\d+", cleaned):
                continue
            if not parts or parts[-1] != cleaned:
                parts.append(cleaned)
        return " ".join(parts)

    def _video_transcript_text(self, target: str) -> str:
        sources = (
            self._youtube_transcript_from_caption_tracks,
            self._youtube_transcript_with_api,
            self._subtitles_from_ytdlp,
            self._transcribe_video_with_whisper,
            self._fetch_jina_reader,
            self._fetch_url_text,
        )
        for source in sources:
            try:
                payload = self._collapse_text(source(target))
            except Exception:
                payload = ""
            if payload:
                return payload
        return ""

    def _youtube_video_id(self, target: str) -> str:
        text = self._collapse_text(target)
        patterns = (
            r"(?:v=|youtu\.be/)([A-Za-z0-9_-]{11})",
            r"/shorts/([A-Za-z0-9_-]{11})",
            r"/embed/([A-Za-z0-9_-]{11})",
        )
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1)
        return ""

    def _transcribe_video_with_whisper(self, target: str) -> str:
        yt_dlp = self._safe_which("yt-dlp")
        whisper = self._safe_which("whisper")
        if not yt_dlp or not whisper:
            return ""

        scratch = Path("/tmp/burry_video_transcript")
        scratch.mkdir(parents=True, exist_ok=True)
        output_template = scratch / "%(id)s.%(ext)s"
        download = subprocess.run(
            [
                yt_dlp,
                "-x",
                "--audio-format",
                "mp3",
                "--no-playlist",
                "-o",
                str(output_template),
                target,
            ],
            capture_output=True,
            text=True,
            timeout=180,
        )
        if download.returncode != 0:
            return ""

        media_files = sorted(scratch.glob("*.mp3"), key=lambda item: item.stat().st_mtime, reverse=True)
        if not media_files:
            return ""

        media_path = media_files[0]
        transcription = subprocess.run(
            [
                whisper,
                str(media_path),
                "--model",
                "base",
                "--task",
                "transcribe",
                "--output_format",
                "txt",
                "--output_dir",
                str(scratch),
            ],
            capture_output=True,
            text=True,
            timeout=600,
        )
        if transcription.returncode != 0:
            return ""

        transcript_file = scratch / f"{media_path.stem}.txt"
        if transcript_file.exists():
            return transcript_file.read_text(encoding="utf-8", errors="ignore")
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

    def _location_root_from_text(self, raw: str, default: str = "") -> str:
        lowered = self._collapse_text(raw).lower()
        for phrase, target in LOCATION_ROOTS.items():
            if phrase in lowered:
                return target
        return self._collapse_text(default)

    def _strip_location_phrases(self, raw: str) -> str:
        cleaned = self._collapse_text(raw)
        for phrase in sorted(LOCATION_ROOTS, key=len, reverse=True):
            cleaned = re.sub(rf"\b{re.escape(phrase)}\b", " ", cleaned, flags=re.IGNORECASE)
        return self._collapse_text(cleaned)

    def _clean_file_reference(self, raw: str) -> str:
        cleaned = self._strip_location_phrases(raw)
        cleaned = re.sub(
            r"\b(?:read|open|write|append|overwrite|move|copy|rename|find|show|list|delete|remove|the|my|this|that|a|an|please|for me|contents?|content|named|called)\b",
            " ",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(r"\b(?:file|files|document|documents)\b", " ", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" .,!?:;\"'")
        return cleaned

    def _filesystem_search_roots(self, preferred_root: str = "") -> list[Path]:
        roots: list[Path] = []
        candidates = [preferred_root, Path.cwd(), "~/Desktop", "~/Documents", "~/Downloads"]
        for candidate in candidates:
            if not candidate:
                continue
            root = Path(os.path.expanduser(str(candidate)))
            if root.exists() and root.is_dir() and root not in roots:
                roots.append(root)
        return roots

    def _find_path_matches(self, query: str, *, preferred_root: str = "", directories: bool = False, limit: int = 8) -> list[Path]:
        needle = _normalize(self._clean_file_reference(query) or query)
        if not needle:
            return []

        exact_name: list[Path] = []
        exact_stem: list[Path] = []
        partial: list[Path] = []
        for root in self._filesystem_search_roots(preferred_root):
            visited = 0
            for current_root, dirnames, filenames in os.walk(root):
                dirnames[:] = [name for name in dirnames if not name.startswith(".")]
                names = dirnames if directories else filenames
                for name in names:
                    candidate = Path(current_root) / name
                    visited += 1
                    name_key = _normalize(candidate.name)
                    stem_key = _normalize(candidate.stem)
                    if name_key == needle:
                        exact_name.append(candidate)
                    elif stem_key == needle:
                        exact_stem.append(candidate)
                    elif needle in name_key or needle in stem_key:
                        partial.append(candidate)
                    if len(exact_name) >= limit:
                        break
                if len(exact_name) >= limit or visited >= 4000:
                    break
            if len(exact_name) >= limit:
                break

        ordered = exact_name + [item for item in exact_stem if item not in exact_name] + [item for item in partial if item not in exact_name and item not in exact_stem]
        return ordered[:limit]

    def _resolve_file_target(
        self,
        raw: str,
        *,
        must_exist: bool = False,
        allow_directory: bool = False,
        preferred_root: str = "",
    ) -> Path:
        cleaned = self._collapse_text(raw)
        if not cleaned:
            raise ValueError("File path is required")

        if cleaned.startswith(("~", "/")) or "/" in cleaned:
            explicit = Path(os.path.expanduser(cleaned))
            if explicit.exists() or not must_exist:
                return explicit

        location_root = self._location_root_from_text(cleaned, default=preferred_root)
        label = self._clean_file_reference(cleaned)
        if location_root and not label:
            target = Path(os.path.expanduser(location_root))
            if target.exists() or not must_exist or allow_directory:
                return target

        if label:
            direct = Path(os.path.expanduser(label))
            if direct.exists():
                return direct
            if location_root:
                candidate = Path(os.path.expanduser(location_root)) / label
                if candidate.exists() or not must_exist:
                    return candidate
            matches = self._find_path_matches(label, preferred_root=location_root, directories=allow_directory, limit=1)
            if matches:
                return matches[0]
            if location_root:
                return Path(os.path.expanduser(location_root)) / label
            return direct

        target = Path(os.path.expanduser(cleaned))
        if target.exists() or not must_exist:
            return target
        raise FileNotFoundError(cleaned)

    def _resolve_destination_target(self, raw: str, source_path: Path | None = None) -> Path:
        cleaned = self._collapse_text(raw)
        if not cleaned:
            if source_path is None:
                raise ValueError("Destination path is required")
            return source_path

        if cleaned.startswith(("~", "/")) or "/" in cleaned:
            target = Path(os.path.expanduser(cleaned))
            if target.exists() and target.is_dir():
                return target / (source_path.name if source_path else "")
            if cleaned.endswith(os.sep):
                return target / (source_path.name if source_path else "")
            return target

        location_root = self._location_root_from_text(cleaned)
        label = self._clean_file_reference(cleaned)
        if location_root:
            root = Path(os.path.expanduser(location_root))
            if not label:
                return root / (source_path.name if source_path else "")
            return root / label

        if source_path is not None:
            label = label or cleaned
            destination_name = label
            if not Path(destination_name).suffix and source_path.suffix:
                destination_name = f"{destination_name}{source_path.suffix}"
            return source_path.parent / destination_name

        return Path(os.path.expanduser(label or cleaned))

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
                                "tool_name": action.get("tool_name", "") or action.get("type"),
                                "capability_id": action.get("capability_id", ""),
                                "status": "ok",
                                "result": "skipped - user cancelled",
                            }
                        )
                        continue
                before = self._capture_verification_state(action)
                result = self._dispatch(action)
                payload = {
                    "action": action.get("type"),
                    "tool_name": action.get("tool_name", "") or action.get("type"),
                    "capability_id": action.get("capability_id", ""),
                    "status": "ok",
                    "result": result,
                }
                verification = self._verify_action_result(action, result, before)
                if verification:
                    payload.update(verification)
                    if payload.get("verification_status") == "failed":
                        payload["status"] = "error"
                        payload["error"] = payload.get("verification_detail") or "Verification failed"
                self.results.append(payload)
            except Exception as exc:
                self.results.append(
                    {
                        "action": action.get("type"),
                        "tool_name": action.get("tool_name", "") or action.get("type"),
                        "capability_id": action.get("capability_id", ""),
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
        if t == "open_file":
            return self.open_file(action["path"])
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
        if t == "zip_folder":
            return self.zip_folder(action.get("path", ""))
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
        if t == "copy_file":
            return self.copy_file(
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
        if t == "calendar_read":
            return self.calendar_read(action.get("range", "today"))
        if t == "calendar_add":
            return self.calendar_add(
                action.get("title", ""),
                action.get("time", ""),
                int(action.get("duration", 60) or 60),
            )
        if t == "task_read":
            return self.task_read(action.get("filter", "today"))
        if t == "task_add":
            return self.task_add(
                action.get("title", ""),
                action.get("project", ""),
            )
        if t == "task_done":
            return self.task_done(action.get("title", ""))
        if t == "vps_check":
            return self.vps_check(action.get("action", "status"))
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
        if t == "set_reminder":
            return self.set_reminder(
                minutes=action.get("minutes"),
                when=action.get("when", ""),
                message=action.get("message", ""),
            )
        if t == "remind_in":
            return self.set_reminder(
                minutes=action.get("minutes"),
                message=action.get("message", ""),
            )
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
            level = action.get("level")
            if level is not None:
                return self.brightness_set(level)
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
        target = self._resolve_file_target(path, must_exist=False, allow_directory=True)
        target.mkdir(parents=True, exist_ok=True)
        subprocess.Popen(["open", str(target)])
        return f"opened {target}"

    def open_file(self, path: str) -> str:
        target = self._resolve_file_target(path, must_exist=True)
        subprocess.Popen(["open", str(target)])
        return f"opened {target}"

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
        target = self._resolve_file_target(path, must_exist=False)
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "w", encoding="utf-8") as handle:
            handle.write(content or "")
        return f"created {target}"

    def read_file(self, path: str) -> str:
        target = self._resolve_file_target(path, must_exist=True)
        with open(target, "r", encoding="utf-8") as handle:
            content = handle.read()
        cleaned = self._collapse_text(content)
        if len(cleaned) <= 500:
            return cleaned or f"{target} is empty"
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
        if int(getattr(result, "returncode", 0) or 0) != 0:
            raise RuntimeError(output[:300] or f"command failed with exit code {result.returncode}")
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
        target = self._resolve_file_target(path, must_exist=False)
        target.parent.mkdir(parents=True, exist_ok=True)
        file_mode = "a" if mode == "append" else "w"
        with open(target, file_mode, encoding="utf-8") as handle:
            if mode == "append":
                handle.write(
                    f"\n\n--- {datetime.now().strftime('%Y-%m-%d %H:%M')} ---\n{content}"
                )
            else:
                handle.write(content)
        return f"wrote to {target}"

    def delete_file(self, path: str) -> str:
        target = self._resolve_file_target(path, must_exist=True)
        if not target.is_file():
            raise FileNotFoundError(str(target))
        filename = target.name
        self._speak(f"delete {filename} are you sure")
        heard = self._listen_followup(timeout=5.0).lower()
        if heard not in {"yes", "yeah", "yep", "confirm", "do it"}:
            return "skipped - user cancelled"
        os.remove(target)
        return f"deleted {target}"

    def zip_folder(self, path: str) -> str:
        target = self._resolve_file_target(path, must_exist=True, allow_directory=True)
        if not target.is_dir():
            raise NotADirectoryError(str(target))
        archive_base = target.parent / target.name
        archive_path = Path(shutil.make_archive(str(archive_base), "zip", root_dir=str(target.parent), base_dir=target.name))
        return f"zipped {target} to {archive_path}"

    def find_file(self, query: str, root: str = "~") -> str:
        cleaned = self._collapse_text(query)
        if not cleaned:
            raise ValueError("Search query is required")
        preferred_root = self._location_root_from_text(root, default=root or "")
        matches = [str(item) for item in self._find_path_matches(cleaned, preferred_root=preferred_root, limit=8)]
        if not matches:
            return "no files found"
        return ", ".join(matches[:8])

    def list_files(self, path: str = "~") -> str:
        target = self._resolve_file_target(path or "~", must_exist=False, allow_directory=True)
        target.mkdir(parents=True, exist_ok=True)
        items = sorted(os.listdir(target))[:8]
        spoken = ", ".join(items) if items else "no files"
        self._speak(spoken)
        return spoken

    def move_file(self, source: str, destination: str) -> str:
        source_path = self._resolve_file_target(source, must_exist=True)
        destination_path = self._resolve_destination_target(destination, source_path)
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source_path), str(destination_path))
        return f"moved {source_path} to {destination_path}"

    def copy_file(self, source: str, destination: str) -> str:
        source_path = self._resolve_file_target(source, must_exist=True)
        destination_path = self._resolve_destination_target(destination, source_path)
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, destination_path)
        return f"copied {source_path} to {destination_path}"

    def _calendar_range_mode(self, range_name: str) -> str:
        lowered = self._collapse_text(str(range_name or "").replace("_", " ")).lower()
        if "next week" in lowered:
            return "next_week"
        if "this week" in lowered or "rest of the week" in lowered or "rest of week" in lowered:
            return "this_week"
        if re.search(r"\b(?:next|upcoming)\b", lowered):
            return "next"
        if "tomorrow" in lowered:
            return "tomorrow"
        return "today"

    @staticmethod
    def _calendar_range_label(mode: str) -> str:
        labels = {
            "today": "today",
            "tomorrow": "tomorrow",
            "next": "the upcoming schedule",
            "this_week": "this week",
            "next_week": "next week",
        }
        return labels.get(mode, "today")

    def _calendar_items_from_json(self, payload: str) -> list[dict]:
        text = str(payload or "").strip()
        if not text.startswith("["):
            return []
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return []
        items: list[dict] = []
        for item in parsed:
            if not isinstance(item, dict):
                continue
            title = self._collapse_text(item.get("title", ""))
            if not title:
                continue
            items.append(
                {
                    "title": title,
                    "start": self._collapse_text(item.get("start", "")),
                    "end": self._collapse_text(item.get("end", "")),
                    "calendar": self._collapse_text(item.get("calendar", "")),
                }
            )
        return items

    @staticmethod
    def _calendar_datetime(value: str) -> datetime | None:
        text = str(value or "").strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
        return parsed.astimezone() if parsed.tzinfo else parsed

    @staticmethod
    def _calendar_time_label(value: datetime, *, include_day: bool) -> str:
        hour = value.strftime("%I").lstrip("0") or "0"
        minute = value.strftime("%M")
        suffix = value.strftime("%p")
        if include_day:
            return f"{value.strftime('%a')} {hour}:{minute} {suffix}"
        return f"{hour}:{minute} {suffix}"

    def _calendar_event_label(self, item: dict, *, include_day: bool) -> str:
        title = self._collapse_text(item.get("title", "")) or "Untitled event"
        start = self._calendar_datetime(item.get("start", ""))
        if start is None:
            return title
        return f"{title} at {self._calendar_time_label(start, include_day=include_day)}"

    def _calendar_summary(self, items: list[dict], mode: str) -> str:
        label = self._calendar_range_label(mode)
        if not items:
            if mode == "next":
                return "no upcoming calendar events"
            return f"no calendar events for {label}"

        if mode == "next":
            return f"your next event is {self._calendar_event_label(items[0], include_day=True)}"

        include_day = mode in {"this_week", "next_week"}
        visible = [self._calendar_event_label(item, include_day=include_day) for item in items[:4]]
        prefix = f"you have {len(items)} calendar event{'s' if len(items) != 1 else ''} {label}: "
        if len(items) > 4:
            return f"{prefix}{'; '.join(visible)}; plus {len(items) - 4} more"
        return f"{prefix}{'; '.join(visible)}"

    def calendar_read(self, range_name: str = "today") -> str:
        mode = self._calendar_range_mode(range_name)
        script = f'''
var Calendar = Application("/System/Applications/Calendar.app");
var startDate = new Date();
var endDate = new Date(startDate.getTime());
var mode = {json.dumps(mode)};
var now = new Date();
function startOfDay(value) {{
    var copy = new Date(value.getTime());
    copy.setHours(0);
    copy.setMinutes(0);
    copy.setSeconds(0);
    copy.setMilliseconds(0);
    return copy;
}}
var todayStart = startOfDay(now);
var mondayStart = new Date(todayStart.getTime());
var weekdayIndex = (todayStart.getDay() + 6) % 7;
mondayStart.setDate(mondayStart.getDate() - weekdayIndex);
var nextWeekStart = new Date(mondayStart.getTime());
nextWeekStart.setDate(nextWeekStart.getDate() + 7);
var upcomingOnly = false;
if (mode === "tomorrow") {{
    startDate = new Date(todayStart.getTime());
    startDate.setDate(startDate.getDate() + 1);
    endDate = new Date(startDate.getTime());
    endDate.setDate(endDate.getDate() + 1);
}} else if (mode === "next") {{
    startDate = new Date(now.getTime());
    endDate = new Date(now.getTime());
    endDate.setDate(endDate.getDate() + 30);
    upcomingOnly = true;
}} else if (mode === "this_week") {{
    startDate = new Date(todayStart.getTime());
    endDate = new Date(nextWeekStart.getTime());
}} else if (mode === "next_week") {{
    startDate = new Date(nextWeekStart.getTime());
    endDate = new Date(nextWeekStart.getTime());
    endDate.setDate(endDate.getDate() + 7);
}} else {{
    startDate = new Date(todayStart.getTime());
    endDate = new Date(startDate.getTime());
    endDate.setDate(endDate.getDate() + 1);
}}
var entries = [];
var calendars = Calendar.calendars();
for (var i = 0; i < calendars.length; i++) {{
    try {{
        var events = calendars[i].events();
        for (var j = 0; j < events.length; j++) {{
            var eventStart = new Date(events[j].startDate());
            if (upcomingOnly && eventStart < startDate) {{
                continue;
            }}
            if (!upcomingOnly && !(eventStart >= startDate && eventStart < endDate)) {{
                continue;
            }}
            if (upcomingOnly && eventStart >= endDate) {{
                continue;
            }}
            var eventEnd = "";
            try {{
                eventEnd = new Date(events[j].endDate()).toISOString();
            }} catch (error) {{}}
            entries.push({{
                title: String(events[j].summary()),
                start: eventStart.toISOString(),
                end: eventEnd,
                calendar: String(calendars[i].name())
            }});
        }}
    }} catch (error) {{}}
}}
entries.sort(function(left, right) {{
    return new Date(left.start) - new Date(right.start);
}});
if (mode === "next" && entries.length > 1) {{
    entries = [entries[0]];
}}
JSON.stringify(entries.slice(0, 8));
'''
        try:
            result = subprocess.run(
                ["osascript", "-l", "JavaScript", "-e", script],
                capture_output=True,
                text=True,
                timeout=8,
            )
        except subprocess.TimeoutExpired:
            return "Calendar read is unavailable until Calendar automation access is granted on this host."
        stdout = self._collapse_text(result.stdout or "")
        stderr = self._collapse_text(result.stderr or "")
        error_text = f"{stdout}\n{stderr}".lower()
        if any(
            marker in error_text
            for marker in (
                "connection invalid",
                "parameter is missing",
                "application can't be found",
                "not authorized",
                "(-1701)",
                "(-1743)",
            )
        ):
            return "Calendar read is unavailable until Calendar automation access is granted on this host."
        parsed_items = self._calendar_items_from_json(stdout)
        if parsed_items:
            return self._calendar_summary(parsed_items, mode)
        summary = stdout or stderr
        lowered = self._calendar_range_label(mode)
        return summary or f"no calendar events for {lowered or 'today'}"

    def calendar_add(self, title: str, when: str, duration: int = 60) -> str:
        cleaned_title = self._collapse_text(title) or "Untitled event"
        cleaned_when = self._collapse_text(when)
        start_date_expr = self._applescript_date_expression(cleaned_when) if cleaned_when else "current date"
        script = f'''
tell application "Calendar"
    activate
    tell calendar 1
        set startDate to {start_date_expr}
        set endDate to startDate + ({max(1, int(duration))} * minutes)
        set newEvent to make new event with properties {{summary:{self._applescript_string(cleaned_title)}, start date:startDate, end date:endDate}}
        return summary of newEvent
    end tell
end tell
'''
        try:
            self._run_osascript(script, timeout=15)
        except Exception as exc:
            if self._automation_access_unavailable(str(exc)):
                return self._calendar_write_unavailable_message()
            raise
        return f"added calendar event {cleaned_title}"

    def task_read(self, filter_name: str = "today") -> str:
        from tasks.task_store import get_active_tasks

        tasks = get_active_tasks()
        if not tasks:
            return "no pending tasks"
        lines = []
        for task in tasks[:4]:
            title = self._collapse_text(task.get("title", ""))[:80]
            project = self._collapse_text(task.get("project", ""))
            lines.append(f"{title}{f' ({project})' if project else ''}")
        prefix = "Pending today" if "today" in self._collapse_text(filter_name).lower() else "Pending tasks"
        return f"{prefix}: " + "; ".join(lines)

    def task_add(self, title: str, project: str = "") -> str:
        from tasks.task_store import add_task

        task = add_task(self._collapse_text(title), project=self._collapse_text(project))
        return f"added task {self._collapse_text(task.get('title', ''))}"

    def task_done(self, title: str) -> str:
        from tasks.task_store import get_active_tasks, update_task_status

        cleaned = self._collapse_text(title)
        if not cleaned:
            raise ValueError("Task title is required")
        if update_task_status(cleaned, "done"):
            return f"marked {cleaned} done"
        for task in get_active_tasks():
            current_title = self._collapse_text(task.get("title", ""))
            if cleaned.lower() in current_title.lower():
                update_task_status(str(task.get("id", "")), "done")
                return f"marked {current_title} done"
        return f"could not find task {cleaned}"

    def vps_check(self, action: str = "status") -> str:
        return self.run_agent_task("vps", {"action": self._collapse_text(action) or "status"})

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
        app_name = self._resolve_browser_app(DEFAULT_BROWSER_APP)
        family = self._browser_family(app_name)
        target = self._normalize_browser_url(url) if self._collapse_text(url) else ""
        if family == "safari":
            if target:
                script = (
                    f'tell application "{app_name}"\n'
                    "    activate\n"
                    f"    make new document with properties {{URL:{json.dumps(target)}}}\n"
                    "end tell"
                )
            else:
                script = (
                    f'tell application "{app_name}"\n'
                    "    activate\n"
                    "    make new document\n"
                    "end tell"
                )
        else:
            script = (
                f'tell application "{app_name}"\n'
                "    activate\n"
                "    make new window\n"
                f'    if {self._applescript_string(target)} is not "" then set URL of active tab of front window to {self._applescript_string(target)}\n'
                "end tell"
            )
        self._run_osascript(script, timeout=10)
        return f"opened browser window{f': {target}' if target else ''}"

    def browser_go_back(self) -> str:
        app_name = self._resolve_browser_app(DEFAULT_BROWSER_APP)
        if self._browser_family(app_name) == "safari":
            script = (
                f'tell application "{app_name}"\n'
                "    if (count of windows) = 0 then return\n"
                '    do JavaScript "history.back();" in current tab of front window\n'
                "end tell"
            )
        else:
            script = (
                f'tell application "{app_name}"\n'
                "    if (count of windows) = 0 then return\n"
                "    tell active tab of front window to go back\n"
                "end tell"
            )
        self._run_osascript(script, timeout=5)
        return "went back in browser"

    def browser_refresh(self) -> str:
        app_name = self._resolve_browser_app(DEFAULT_BROWSER_APP)
        if self._browser_family(app_name) == "safari":
            script = (
                f'tell application "{app_name}"\n'
                "    if (count of windows) = 0 then return\n"
                '    do JavaScript "window.location.reload();" in current tab of front window\n'
                "end tell"
            )
        else:
            script = (
                f'tell application "{app_name}"\n'
                "    if (count of windows) = 0 then return\n"
                "    tell active tab of front window to reload\n"
                "end tell"
            )
        self._run_osascript(script, timeout=5)
        return "reloaded browser tab"

    def browser_go_to(self, url: str) -> str:
        target = self._normalize_browser_url(url)
        app_name = self._resolve_browser_app(DEFAULT_BROWSER_APP)
        if self._browser_family(app_name) == "safari":
            script = (
                f'tell application "{app_name}"\n'
                "    activate\n"
                "    if (count of windows) = 0 then make new document\n"
                f"    set URL of current tab of front window to {self._applescript_string(target)}\n"
                "end tell"
            )
        else:
            script = (
                f'tell application "{app_name}"\n'
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

    def brightness_set(self, level: int) -> str:
        safe_level = max(0, min(100, int(level)))
        total_steps = 16
        target_steps = round((safe_level / 100) * total_steps)
        script_lines = ['tell application "System Events"']
        script_lines.extend('key code 145' for _ in range(total_steps))
        script_lines.extend('key code 144' for _ in range(target_steps))
        script_lines.append("end tell")
        self._run_osascript("\n".join(script_lines), timeout=8)
        return f"set brightness to {safe_level}"

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
        normalized_target = self._normalize_browser_url(target)
        content = ""
        try:
            from memory.knowledge_base import get_indexed_document

            cached = get_indexed_document(normalized_target)
            content = str((cached or {}).get("text", "") or "").strip()
        except Exception:
            content = ""
        if not content:
            content = self._fetch_jina_reader(normalized_target)
        if not content:
            content = self._fetch_url_text(normalized_target)
        if not content:
            return "could not fetch the current page"
        try:
            from memory.knowledge_base import index_web_page

            index_web_page(normalized_target, content)
        except Exception:
            pass
        summary = self._summarize_text(content, "Summarize this web page in under 120 words.")
        if summary:
            self._speak(summary)
        return summary or "could not summarize the page"

    def summarize_video(self, url: str = "", save_to_obsidian: bool = False) -> str:
        target = self._collapse_text(url) or self._current_chrome_url()
        if not target:
            return "no video url available"
        transcript_text = self._video_transcript_text(self._normalize_browser_url(target))
        if not transcript_text:
            return "could not fetch a usable transcript for that video"
        summary = self._summarize_text(transcript_text, "Summarize this video transcript in under 140 words.")
        if summary:
            self._speak(summary)
        if save_to_obsidian and summary:
            title = f"Video Summary {datetime.now().strftime('%Y-%m-%d %H-%M')}"
            note_result = self.obsidian_note(title, summary, folder="Daily")
            return f"{summary} {note_result}".strip()
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

    def set_reminder(self, minutes: int | None = None, message: str = "", when: str = "") -> str:
        cleaned_message = self._collapse_text(message) or "Butler reminder"
        cleaned_when = self._collapse_text(when)
        safe_minutes = max(1, int(minutes or 30))
        remind_date_expr = (
            self._applescript_date_expression(cleaned_when)
            if cleaned_when
            else f"(current date) + ({safe_minutes} * minutes)"
        )
        script = f'''
tell application "Reminders"
    set remindDate to {remind_date_expr}
    tell default list
        set newReminder to make new reminder with properties {{name:{self._applescript_string(cleaned_message)}, body:{self._applescript_string(cleaned_message)}, remind me date:remindDate, due date:remindDate}}
        return name of newReminder
    end tell
end tell
'''
        try:
            self._run_osascript(script, timeout=15)
        except Exception as exc:
            if self._automation_access_unavailable(str(exc)):
                return self._reminders_unavailable_message()
            raise
        if cleaned_when:
            return f"reminder set for {cleaned_when}"
        return f"reminder set for {safe_minutes} min"

    def remind_in(self, minutes: int, message: str) -> str:
        return self.set_reminder(minutes=minutes, message=message)

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
