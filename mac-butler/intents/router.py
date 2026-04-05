#!/usr/bin/env python3
"""
intents/router.py
Deterministic intent router. No LLM. Handles common commands instantly.
"""

from __future__ import annotations

import re

APP_MAP = {
    "visual studio code": "Visual Studio Code",
    "vs code": "Visual Studio Code",
    "vscode": "Visual Studio Code",
    "cursor": "Cursor",
    "terminal": "Terminal",
    "spotify": "Spotify",
    "claude": "Claude",
    "obsidian": "Obsidian",
    "chrome": "Google Chrome",
    "safari": "Safari",
    "slack": "Slack",
    "notion": "Notion",
    "figma": "Figma",
    "discord": "Discord",
    "telegram": "Telegram",
    "whatsapp": "WhatsApp",
    "postman": "Postman",
    "tableplus": "TablePlus",
    "antigravity": "Antigravity",
    "netflix": ("browser", "https://netflix.com"),
    "youtube": ("browser", "https://youtube.com"),
    "prime": ("browser", "https://primevideo.com"),
    "hotstar": ("browser", "https://hotstar.com"),
    "twitch": ("browser", "https://twitch.tv"),
    "github": ("browser", "https://github.com"),
    "gmail": ("browser", "https://mail.google.com"),
    "twitter": ("browser", "https://x.com"),
    "x": ("browser", "https://x.com"),
    "linear": ("browser", "https://linear.app"),
    "vercel": ("browser", "https://vercel.com"),
}

PROJECT_MAP = {
    "mac-butler": "~/Burry/mac-butler",
    "butler": "~/Burry/mac-butler",
    "email-infra": "~/Developer/email-infra",
    "email infra": "~/Developer/email-infra",
    "developer": "~/Developer",
    "burry": "~/Burry",
}

MUSIC_MODES = {
    "focus": "focus",
    "lofi": "focus",
    "lo-fi": "focus",
    "chill": "chill",
    "relax": "chill",
    "late night": "late_night",
    "synthwave": "late_night",
    "dark": "late_night",
    "ambient": "late_night",
    "hype": "hype",
    "hardstyle": "hype",
    "dnb": "hype",
}

GENERIC_SONG_QUERIES = {
    "",
    "a song",
    "anything",
    "anything good",
    "it",
    "something",
    "song",
    "some song",
    "that",
    "that one",
    "that song",
    "the song",
    "this",
    "this one",
    "this song",
}

EDITOR_HINTS = {
    "visual studio code": "vscode",
    "vs code": "vscode",
    "vscode": "vscode",
    "cursor": "cursor",
}

GENERIC_FILE_NAMES = {
    "",
    "a",
    "file",
    "new file",
    "name",
    "the file",
}


class Intent:
    def __init__(
        self,
        name: str,
        params: dict | None = None,
        confidence: float = 1.0,
        raw: str = "",
    ) -> None:
        self.name = name
        self.params = params or {}
        self.confidence = confidence
        self.raw = raw

    @property
    def intent(self) -> str:
        return self.name

    def to_action(self):
        name = self.name
        params = self.params

        if name == "spotify_play":
            return {"type": "search_and_play", "query": params.get("song", "")}
        if name == "spotify_pause":
            return {"type": "spotify_pause"}
        if name == "spotify_next":
            return {"type": "spotify_next"}
        if name == "spotify_prev":
            return {"type": "spotify_prev"}
        if name == "spotify_volume":
            return {
                "type": "spotify_volume",
                "direction": params.get("dir", "up"),
                "amount": 15,
            }
        if name == "spotify_mode":
            return {"type": "play_music", "mode": params.get("mode", "focus")}
        if name == "open_app":
            value = params.get("app")
            if isinstance(value, tuple) and value[0] == "browser":
                return {"type": "open_url_in_browser", "url": value[1]}
            return {"type": "open_app", "app": value, "mode": "smart"}
        if name == "close_app":
            return {"type": "quit_app", "app": params.get("app")}
        if name == "open_project":
            return {"type": "open_project", "name": params.get("name")}
        if name == "open_editor_window":
            action = {
                "type": "open_editor",
                "editor": params.get("editor", "auto"),
                "mode": params.get("mode", "new_window"),
            }
            if params.get("path"):
                action["path"] = params["path"]
            return action
        if name == "create_file":
            return {
                "type": "create_file_in_editor",
                "filename": params.get("filename", "untitled"),
                "editor": params.get("editor", "auto"),
            }
        if name == "create_folder":
            return {"type": "create_folder", "path": params.get("path", "~/Developer/new-folder")}
        if name == "git_status":
            return {
                "type": "run_command",
                "cmd": "git status --short",
                "cwd": params.get("cwd", "."),
            }
        if name == "git_push":
            return {"type": "run_command", "cmd": "git push", "cwd": params.get("cwd", ".")}
        if name == "vps_status":
            return {"type": "run_agent", "agent": "vps", "host": params.get("host", "")}
        if name == "docker_status":
            return {
                "type": "run_command",
                "cmd": "docker ps --format 'table {{.Names}}\\t{{.Status}}'",
            }
        if name == "obsidian_note":
            return {
                "type": "obsidian_note",
                "title": params.get("title", "Quick note"),
                "content": params.get("content", ""),
                "folder": "Daily",
            }
        if name == "set_reminder":
            return {
                "type": "remind_in",
                "minutes": params.get("minutes", 30),
                "message": params.get("message", "Butler reminder"),
            }
        if name == "open_last_workspace":
            return {"type": "open_last_workspace"}
        if name == "open_codex":
            return {
                "type": "open_terminal",
                "mode": "tab",
                "cmd": "codex",
                "cwd": "~/Burry/mac-butler",
            }
        return None

    def needs_llm(self) -> bool:
        return self.name in {"unknown", "what_next", "briefing", "question"}

    def quick_response(self) -> str:
        target_name = (
            self.params.get("name")
            or self.params.get("project")
            or self.params.get("app")
            or ""
        )
        if isinstance(target_name, tuple):
            target_name = self.params.get("name", "")

        responses = {
            "spotify_play": f"Playing {self.params.get('song', 'it')}.",
            "clarify_song": "Which song should I play?",
            "clarify_file": "What should I name the file?",
            "spotify_pause": "Paused.",
            "spotify_next": "Next track.",
            "spotify_prev": "Going back.",
            "spotify_volume": f"Volume {self.params.get('dir', 'adjusted')}.",
            "spotify_mode": f"Switching to {self.params.get('mode', 'focus')} music.",
            "open_app": f"Opening {target_name}.",
            "close_app": f"Closing {target_name}.",
            "open_project": f"Opening {self.params.get('name', 'project')}.",
            "open_editor_window": f"Opening {self.params.get('name', 'editor')}.",
            "create_file": f"Created {self.params.get('filename', 'file')}.",
            "create_folder": "Folder created.",
            "git_status": "Checking git status.",
            "git_push": "Pushing...",
            "vps_status": "Checking VPS...",
            "docker_status": "Checking containers...",
            "obsidian_note": "Saved to Obsidian.",
            "set_reminder": f"Reminder in {self.params.get('minutes', 30)} minutes.",
            "open_last_workspace": "Reopening your last workspace.",
            "open_codex": "Opening Codex.",
        }
        return responses.get(self.name, "")

    def __repr__(self) -> str:
        return f"Intent(name={self.name!r}, params={self.params!r}, confidence={self.confidence:.2f})"


IntentResult = Intent


def clean_song_query(query: str) -> str:
    """Strip noise that STT adds to song names."""
    # Remove "on spotify / apple music / youtube" at the end
    query = re.sub(r'\s+on\s+(spotify|apple\s*music|youtube|tidal|deezer)\b.*$', '', query, flags=re.I)
    # Remove trailing filler
    query = re.sub(r'\s+(please|for\s+me|right\s+now|now)\s*$', '', query, flags=re.I)
    # Strip punctuation
    query = query.strip().strip('.,!?')
    return query


def is_ambiguous_song_query(query: str) -> bool:
    normalized = re.sub(r"[^a-z0-9\s]", "", query.lower()).strip()
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized in GENERIC_SONG_QUERIES


def _normalize_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


def _phrase_present(haystack: str, needle: str) -> bool:
    pattern = rf"(?<!\w){re.escape(needle)}(?!\w)"
    return re.search(pattern, haystack) is not None


def _match_from_map(target: str, mapping: dict) -> tuple[str | None, object | None]:
    normalized = _normalize_spaces(target.lower())
    for key in sorted(mapping, key=len, reverse=True):
        if _phrase_present(normalized, key):
            return key, mapping[key]
    return None, None


def _project_map() -> dict:
    mapping = dict(PROJECT_MAP)
    try:
        from projects import load_projects

        for project in load_projects():
            path = project.get("path")
            if not path:
                continue
            names = [project.get("name", "")]
            names.extend(project.get("aliases", []) or [])
            for name in names:
                if name:
                    mapping[_normalize_spaces(str(name).lower())] = path
    except Exception:
        pass
    return mapping


def detect_editor_choice(text: str) -> str:
    lowered = _normalize_spaces(text.lower())
    for key, value in sorted(EDITOR_HINTS.items(), key=lambda item: len(item[0]), reverse=True):
        if _phrase_present(lowered, key):
            return value
    return "auto"


def _editor_name(editor: str) -> str:
    return "Visual Studio Code" if editor == "vscode" else "Cursor" if editor == "cursor" else "editor"


def extract_requested_filename(text: str) -> str:
    compact = _normalize_spaces(text)
    patterns = (
        r"(?:create|make|open)\s+(?:a\s+)?(?:brand\s+new\s+|new\s+)?file(?:\s+(?:with\s+(?:the\s+)?)?(?:name|named|called))?\s+(.+)",
        r"(?:file|document)\s+(?:named|called)\s+(.+)",
    )
    candidate = ""
    for pattern in patterns:
        match = re.search(pattern, compact, flags=re.IGNORECASE)
        if match:
            candidate = match.group(1).strip()
            break

    if not candidate:
        return ""

    candidate = re.split(
        r"\s+(?:in|inside|using|with)\s+(?:cursor|vs code|visual studio code|vscode|antigravity)\b",
        candidate,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    candidate = re.sub(r"\s+(?:please|now|for me|right now)$", "", candidate, flags=re.IGNORECASE)
    candidate = candidate.strip().strip(".,!?")
    candidate = candidate.strip("\"'")
    candidate = _normalize_spaces(candidate)

    if candidate.lower() in GENERIC_FILE_NAMES:
        return ""
    return candidate


def route(text: str) -> Intent:
    lowered = _normalize_spaces(text.lower())

    match = re.match(r"^play\s+(.+)$", lowered)
    if match:
        query = clean_song_query(match.group(1).strip())
        if is_ambiguous_song_query(query):
            return Intent("clarify_song", raw=text)
        for key, value in MUSIC_MODES.items():
            if key in query:
                return Intent("spotify_mode", {"mode": value}, raw=text)
        return Intent("spotify_play", {"song": query}, raw=text)

    if any(value in lowered for value in ("pause music", "stop music", "pause spotify", "mute")):
        return Intent("spotify_pause", raw=text)

    if any(value in lowered for value in ("next song", "next track", "skip")):
        return Intent("spotify_next", raw=text)

    if any(value in lowered for value in ("previous", "prev song", "go back")):
        return Intent("spotify_prev", raw=text)

    if re.search(r"volume (up|down|louder|quieter)|turn (up|down)", lowered):
        direction = "up" if any(value in lowered for value in ("up", "louder")) else "down"
        return Intent("spotify_volume", {"dir": direction}, raw=text)

    match = re.match(r"^(?:close|quit|kill)\s+(.+)$", lowered)
    if match:
        target = match.group(1).strip()
        _matched, app = _match_from_map(target, APP_MAP)
        if app is None:
            app = APP_MAP.get(target, target.title())
        if isinstance(app, tuple):
            app = target.title()
        return Intent("close_app", {"app": app, "name": app}, raw=text)

    if re.search(r"\b(?:create|make|open)\s+(?:a\s+)?(?:brand\s+new\s+|new\s+)?file\b", lowered):
        filename = extract_requested_filename(text)
        editor = detect_editor_choice(text)
        if filename:
            return Intent("create_file", {"filename": filename, "editor": editor}, raw=text)
        return Intent("clarify_file", {"editor": editor}, confidence=0.55, raw=text)

    match = re.search(r"(?:create|make|new) (?:a )?folder (?:called |named )?([a-zA-Z0-9_\-]+)", lowered)
    if match:
        return Intent("create_folder", {"path": f"~/Developer/{match.group(1)}"}, raw=text)

    if re.search(r"\b(?:open|launch|start)\s+(?:a\s+)?new project\b", lowered):
        editor = detect_editor_choice(text)
        project_map = _project_map()
        return Intent(
            "open_editor_window",
            {
                "path": project_map["developer"],
                "editor": editor,
                "mode": "new_window",
                "name": _editor_name(editor),
            },
            raw=text,
        )

    match = re.search(
        r"remind me in (\d+)\s*(minutes|minute|hours|hour|hr|min)s?(?:\s+to\s+(.+))?",
        lowered,
    )
    if match:
        amount = int(match.group(1))
        unit = match.group(2)
        message = match.group(3) or "Butler reminder"
        minutes = amount * 60 if unit in {"hour", "hours", "hr"} else amount
        return Intent("set_reminder", {"minutes": minutes, "message": message}, raw=text)

    match = re.match(r"^(?:note:|remember|write down|jot down|save this:?)\s*(.+)$", lowered)
    if match:
        content = match.group(1)
        return Intent(
            "obsidian_note",
            {"title": content[:35], "content": content},
            raw=text,
        )

    if "git status" in lowered or "what changed" in lowered:
        return Intent("git_status", raw=text)
    if "git push" in lowered or "push to" in lowered:
        return Intent("git_push", raw=text)

    if any(value in lowered for value in ("vps status", "check server", "is server up", "check vps")):
        return Intent("vps_status", raw=text)
    if any(value in lowered for value in ("docker", "containers")):
        return Intent("docker_status", raw=text)

    if any(value in lowered for value in ("last workspace", "where i was", "reopen", "continue where")):
        return Intent("open_last_workspace", raw=text)

    if re.match(r"^(?:open|launch|start)\s+codex(?:\s+in\s+terminal)?$", lowered):
        return Intent("open_codex", raw=text)

    match = re.match(
        r"^(?:open|launch|start)\s+spotify\s+(?:and\s+)?play\s+(.+)$",
        lowered,
    )
    if match:
        query = clean_song_query(match.group(1).strip())
        if is_ambiguous_song_query(query):
            return Intent("clarify_song", raw=text)
        for key, value in MUSIC_MODES.items():
            if key in query:
                return Intent("spotify_mode", {"mode": value}, raw=text)
        return Intent("spotify_play", {"song": query}, raw=text)

    match = re.match(r"^(?:open|launch|start|switch to)\s+(.+)$", lowered)
    if match:
        target = match.group(1).strip()
        editor = detect_editor_choice(text)
        project_key, path = _match_from_map(target, _project_map())
        if project_key and path:
            mode = "new_window" if "new window" in target else "smart"
            return Intent(
                "open_project",
                {"name": project_key, "path": path, "editor": editor, "mode": mode},
                raw=text,
            )
        app_key, value = _match_from_map(target, APP_MAP)
        if value is not None:
            label = app_key if isinstance(value, tuple) else value
            return Intent("open_app", {"app": value, "name": label}, raw=text)
        title = target.title()
        return Intent("open_app", {"app": title, "name": title}, confidence=0.7, raw=text)

    if any(value in lowered for value in ("what should", "what next", "next task", "brief me", "catch me up")):
        return Intent("what_next", confidence=0.9, raw=text)

    # Conversational fallback: extract command buried in natural speech
    extracted = _extract_from_conversational(text, lowered)
    if extracted:
        return extracted

    if lowered.endswith("?") or re.match(
        r"^(?:what|why|how|when|where|who|which|can|could|would|should|is|are|am|do|does|did|will)\b",
        lowered,
    ):
        return Intent("question", confidence=0.6, raw=text)

    return Intent("unknown", confidence=0.0, raw=text)


def _extract_from_conversational(text: str, lowered: str) -> Intent | None:
    """Extract command intent from conversational / noisy STT speech.
    Used when direct pattern matching fails — searches anywhere in the string.
    """
    # create or make a file anywhere in text
    if re.search(r"\b(?:create|make|open)\s+(?:a\s+)?(?:brand\s+new\s+|new\s+)?file\b", lowered):
        filename = extract_requested_filename(text)
        editor = detect_editor_choice(text)
        if filename:
            return Intent("create_file", {"filename": filename, "editor": editor}, raw=text)
        return Intent("clarify_file", {"editor": editor}, confidence=0.55, raw=text)

    # open a new project window anywhere in text
    if re.search(r"\b(?:open|launch|start)\s+(?:a\s+)?new project\b", lowered):
        editor = detect_editor_choice(text)
        project_map = _project_map()
        return Intent(
            "open_editor_window",
            {
                "path": project_map["developer"],
                "editor": editor,
                "mode": "new_window",
                "name": _editor_name(editor),
            },
            raw=text,
        )

    # play <song or mode> anywhere in text
    m = re.search(
        r"\bplay\s+([a-z][\w\s]{0,40}?)(?:[.,!?]|$|\s+and\b|\s+on\b)",
        lowered,
    )
    if m:
        query = clean_song_query(m.group(1).strip())
        if is_ambiguous_song_query(query):
            return Intent("clarify_song", raw=text)
        for key, value in MUSIC_MODES.items():
            if key in query:
                return Intent("spotify_mode", {"mode": value}, raw=text)
        return Intent("spotify_play", {"song": query}, raw=text)

    # open/launch/start <app or project> anywhere in text
    m = re.search(
        r"\b(?:open|launch|start|show)\s+(?:the\s+|up\s+)?([a-z][\w\s]{0,25}?)(?:\s+and\b|\s+please\b|\s+now\b|[.,!?]|$)",
        lowered,
    )
    if m:
        target = m.group(1).strip().rstrip(".,!? ")
        editor = detect_editor_choice(text)
        project_key, path = _match_from_map(target, _project_map())
        if project_key and path:
            mode = "new_window" if "new window" in target else "smart"
            return Intent(
                "open_project",
                {"name": project_key, "path": path, "editor": editor, "mode": mode},
                raw=text,
            )
        app_key, value = _match_from_map(target, APP_MAP)
        if value is not None:
            label = app_key if isinstance(value, tuple) else value
            return Intent("open_app", {"app": value, "name": label}, raw=text)

    # pause / stop music anywhere
    if re.search(r"\b(?:pause|stop)\s+(?:the\s+)?(?:music|spotify|song|playback)\b", lowered):
        return Intent("spotify_pause", raw=text)

    # skip / next anywhere
    if re.search(r"\b(?:skip|next)\s+(?:this\s+)?(?:song|track|one)?\b", lowered):
        return Intent("spotify_next", raw=text)

    return None


if __name__ == "__main__":
    tests = [
        "play mockingbird",
        "play lofi",
        "open cursor",
        "open netflix",
        "open mac-butler",
        "pause music",
        "next song",
        "volume up",
        "create file auth.py",
        "create file test in antigravity",
        "remind me in 30 minutes to check deployments",
        "note: trust score = reputation / send volume",
        "check vps status",
        "what should i do next",
        "open last workspace",
        "close spotify",
    ]
    print("=" * 60)
    for test in tests:
        intent = route(test)
        action = intent.to_action()
        print(f"{test!r}")
        print(f"  -> {intent.name} {intent.params}")
        print(f"  -> action: {action}")
        print(f"  -> needs_llm: {intent.needs_llm()}")
        print()
