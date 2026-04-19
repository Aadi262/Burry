#!/usr/bin/env python3
"""
intents/router.py
Structured intent router: instant commands first, then classifier, then legacy fallback.
"""

from __future__ import annotations

import json
import os
import re
import sys
import threading
import time
import urllib.parse
from pathlib import Path

from brain.ollama_client import _call
from brain.session_context import ctx
from butler_config import INTENT_CLASSIFIER_MODEL
from contact_utils import normalize_email

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
    "google sheet": ("browser", "https://sheets.new"),
    "google sheets": ("browser", "https://sheets.new"),
    "google doc": ("browser", "https://docs.new"),
    "google docs": ("browser", "https://docs.new"),
    "google drive": ("browser", "https://drive.google.com"),
    "google meet": ("browser", "https://meet.new"),
    "google slides": ("browser", "https://slides.new"),
    "postman": "Postman",
    "tableplus": "TablePlus",
    "antigravity": "Antigravity",
    "netflix": ("browser", "https://netflix.com"),
    "youtube": ("browser", "https://youtube.com"),
    "prime": ("browser", "https://primevideo.com"),
    "hotstar": ("browser", "https://hotstar.com"),
    "twitch": ("browser", "https://twitch.tv"),
    "github": ("browser", "https://github.com/Aadi262"),
    "gmail": ("browser", "https://mail.google.com"),
    "twitter": ("browser", "https://x.com"),
    "x": ("browser", "https://x.com"),
    "linear": ("browser", "https://linear.app"),
    "vercel": ("browser", "https://vercel.com/dashboard"),
    "railway": ("browser", "https://railway.app"),
    "chatgpt": ("browser", "https://chat.openai.com"),
    "perplexity": ("browser", "https://perplexity.ai"),
}

PROJECT_MAP = {
    "mac-butler": "~/Burry/mac-butler",
    "butler": "~/Burry/mac-butler",
    "email-infra": "~/Developer/email-infra",
    "email infra": "~/Developer/email-infra",
    "developer": "~/Developer",
    "burry": "~/Burry",
}
_PROJECT_MAP_CACHE: dict | None = None
_PROJECT_MAP_CACHE_AT = 0.0
_PROJECT_MAP_CACHE_TTL_SECONDS = 30.0

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

LOW_SIGNAL_MAIL_WORDS = {"", "it", "this", "that", "someone", "mail", "email"}
PLATFORM_MAP = {
    "youtube": "youtube",
    "spotify": "spotify",
    "apple music": "apple_music",
    "soundcloud": "soundcloud",
}
FOLDER_LOCATION_MAP = {
    "desktop": "~/Desktop",
    "on the desktop": "~/Desktop",
    "on desktop": "~/Desktop",
    "documents": "~/Documents",
    "in the documents": "~/Documents",
    "in documents": "~/Documents",
    "downloads": "~/Downloads",
    "in the downloads": "~/Downloads",
    "in downloads": "~/Downloads",
    "home": "~",
    "in the home": "~",
    "in home": "~",
}

INSTANT_PATTERNS = {
    "pause": {"type": "spotify_pause"},
    "next song": {"type": "spotify_next"},
    "previous": {"type": "spotify_prev"},
    "mute": {"type": "volume_set", "level": 0},
    "stop": {"type": "spotify_pause"},
    "screenshot": {"type": "screenshot"},
    "new tab": {"type": "browser_new_tab"},
    "close tab": {"type": "browser_close_tab"},
    "lock screen": {"type": "lock_screen"},
    "show desktop": {"type": "show_desktop"},
    "sleep": {"type": "sleep_mac"},
    "volume up": {"type": "volume_up"},
    "volume down": {"type": "volume_down"},
    "brightness up": {"type": "brightness", "direction": "up"},
    "brightness down": {"type": "brightness", "direction": "down"},
    "dark mode on": {"type": "dark_mode", "enable": True},
    "dark mode off": {"type": "dark_mode", "enable": False},
    "do not disturb on": {"type": "do_not_disturb", "enable": True},
    "do not disturb off": {"type": "do_not_disturb", "enable": False},
    "dnd on": {"type": "do_not_disturb", "enable": True},
    "dnd off": {"type": "do_not_disturb", "enable": False},
}

CLASSIFIER_SYSTEM = """You are Burry's brain running on a Mac.
The user spoke to you. Decide what they want.
Return ONLY valid JSON. Nothing else. No explanation.

Available intents:
news             - wants current info, news, weather, facts about anything
play_music       - wants to play audio on spotify or youtube or apple music
open_app         - wants to open any application
compose_email    - wants to write or send an email
create_folder    - wants to make a new directory
create_file      - wants to make a new file
open_file        - wants to open a local file
open_folder      - wants Finder opened at a path
read_file        - wants to read file contents
write_file       - wants to write content to existing file
delete_file      - wants to delete a file (always confirm)
find_file        - wants to find a file by name
list_files       - wants to see files in a location
move_file        - wants to move or rename a file
copy_file        - wants to copy a file
open_url         - wants to go to a specific website
browser_tab      - wants to open close or manage browser tabs
browser_window   - wants to open a new browser window
web_search       - wants to search the web for something
volume_control   - wants to change system volume to specific level
brightness       - wants to change screen brightness
compose_whatsapp - wants to send a WhatsApp message
calendar_read    - wants to know about their schedule or meetings
calendar_add     - wants to add an event or reminder
task_read        - wants to know their pending tasks
task_add         - wants to add a new task
task_done        - wants to mark a task complete
obsidian_note    - wants to add or read an Obsidian note
run_command      - wants to run a terminal or shell command
open_project     - wants to open a coding project in an editor
git_action       - wants to run git command with confirmation
vps_check        - wants to check or connect to VPS
summarize_page   - wants to summarize current webpage
summarize_video  - wants to summarize a YouTube video
read_screen      - wants to know what is on screen right now
take_screenshot  - wants to capture and describe screen
focus_app        - wants to switch to a different app
quit_app         - wants to quit an application
minimize_app     - wants to minimize current window
system_info      - wants battery wifi storage info
dark_mode        - wants to toggle dark mode
do_not_disturb   - wants to toggle do not disturb
conversation     - wants to talk brainstorm discuss argue
unknown          - genuinely cannot determine intent

Recent conversation:
{recent_history}

User said: "{text}"

Return ONLY this JSON:
{{
  "intent": "one intent from the list above",
  "params": {{}},
  "confidence": 0.95,
  "platform": null,
  "needs_confirmation": false
}}

Params by intent examples:
news: {{"topic": "Claude Mythos", "region": "India"}}
play_music: {{"song": "blinding lights", "artist": "weeknd"}}
open_app: {{"app": "Terminal"}}
compose_email: {{"to": "vedang@gmail.com", "subject": "", "body": ""}}
create_folder: {{"name": "client work", "path": "~/Desktop"}}
create_file: {{"name": "notes.txt", "path": "~/Desktop", "content": ""}}
open_file: {{"path": "~/Desktop/notes.txt"}}
open_folder: {{"path": "~/Downloads"}}
read_file: {{"path": "~/Desktop/notes.txt"}}
write_file: {{"path": "~/Desktop/notes.txt", "content": "hello world"}}
delete_file: {{"path": "~/Desktop/notes.txt"}}
find_file: {{"query": "resume"}}
list_files: {{"path": "~/Desktop"}}
move_file: {{"from": "~/Desktop/old.txt", "to": "~/Documents/new.txt"}}
copy_file: {{"from": "~/Desktop/old.txt", "to": "~/Documents/old.txt"}}
open_url: {{"url": "https://github.com"}}
browser_tab: {{"action": "new", "search": "adpilot github"}}
browser_window: {{"action": "new", "url": ""}}
web_search: {{"query": "latest AI news"}}
volume_control: {{"level": 50}}
brightness: {{"level": 70}}
compose_whatsapp: {{"contact": "vedang", "phone": "", "message": "hi"}}
calendar_read: {{"range": "today"}}
calendar_add: {{"title": "meeting", "time": "tomorrow 3pm", "duration": 60}}
task_read: {{"filter": "today"}}
task_add: {{"title": "fix login bug", "project": "adpilot"}}
task_done: {{"title": "fix login bug"}}
obsidian_note: {{"title": "", "content": "fix login bug", "action": "add"}}
run_command: {{"cmd": "git status", "cwd": "~/Burry/mac-butler"}}
open_project: {{"name": "adpilot", "editor": "claude"}}
git_action: {{"cmd": "commit", "message": "fix login", "needs_confirmation": true}}
vps_check: {{"action": "status"}}
summarize_page: {{"url": ""}}
summarize_video: {{"url": "", "save_to_obsidian": false}}
read_screen: {{"describe": true}}
take_screenshot: {{"save": true, "describe": true}}
focus_app: {{"app": "Cursor"}}
quit_app: {{"app": "Chrome"}}
minimize_app: {{"app": ""}}
system_info: {{"query": "battery"}}
dark_mode: {{"enable": true}}
do_not_disturb: {{"enable": true}}
conversation: {{"topic": "brainstorm mac-butler architecture"}}

Real examples of how to classify:
"yo whats up with claude mythos bro" → {{"intent":"news","params":{{"topic":"Claude Mythos"}},"confidence":0.94,"platform":null,"needs_confirmation":false}}
"bro make a folder called client stuff on my desktop" → {{"intent":"create_folder","params":{{"name":"client stuff","path":"~/Desktop"}},"confidence":0.97,"platform":null,"needs_confirmation":false}}
"play that blinding lights song on youtube" → {{"intent":"play_music","params":{{"song":"blinding lights"}},"confidence":0.95,"platform":"youtube","needs_confirmation":false}}
"check if anything happened in india today" → {{"intent":"news","params":{{"topic":"India","region":"India"}},"confidence":0.93,"platform":null,"needs_confirmation":false}}
"open a new tab and search adpilot github" → {{"intent":"browser_tab","params":{{"action":"new","search":"adpilot github"}},"confidence":0.91,"platform":null,"needs_confirmation":false}}
"remind me tomorrow morning to call vedang" → {{"intent":"calendar_add","params":{{"title":"call vedang","time":"tomorrow morning"}},"confidence":0.90,"platform":null,"needs_confirmation":false}}
"whats on my calendar today" → {{"intent":"calendar_read","params":{{"range":"today"}},"confidence":0.96,"platform":null,"needs_confirmation":false}}
"write a mail to vedang about project update" → {{"intent":"compose_email","params":{{"to":"vedang","subject":"project update","body":""}},"confidence":0.88,"platform":null,"needs_confirmation":false}}
"open adpilot in claude code" → {{"intent":"open_project","params":{{"name":"adpilot","editor":"claude"}},"confidence":0.95,"platform":null,"needs_confirmation":false}}
"lets brainstorm the mac-butler architecture" → {{"intent":"conversation","params":{{"topic":"mac-butler architecture"}},"confidence":0.92,"platform":null,"needs_confirmation":false}}
"summarize this youtube video and save to obsidian" → {{"intent":"summarize_video","params":{{"url":"","save_to_obsidian":true}},"confidence":0.91,"platform":null,"needs_confirmation":false}}
"what is on my screen right now" → {{"intent":"read_screen","params":{{"describe":true}},"confidence":0.97,"platform":null,"needs_confirmation":false}}
"how much battery do i have" → {{"intent":"system_info","params":{{"query":"battery"}},"confidence":0.99,"platform":null,"needs_confirmation":false}}
"run git status in mac-butler" → {{"intent":"run_command","params":{{"cmd":"git status","cwd":"~/Burry/mac-butler"}},"confidence":0.96,"platform":null,"needs_confirmation":false}}
"push to main" → {{"intent":"git_action","params":{{"cmd":"push","message":"","needs_confirmation":true}},"confidence":0.95,"platform":null,"needs_confirmation":true}}
"move my resume to documents" → {{"intent":"move_file","params":{{"from":"~/Desktop/resume.pdf","to":"~/Documents/resume.pdf"}},"confidence":0.88,"platform":null,"needs_confirmation":false}}
"add a note in obsidian about the adpilot bug" → {{"intent":"obsidian_note","params":{{"title":"adpilot bug","content":"","action":"add"}},"confidence":0.93,"platform":null,"needs_confirmation":false}}"""

_CLASSIFIER_MODEL = INTENT_CLASSIFIER_MODEL
_CLASSIFIER_LOCK = threading.Lock()
_CLASSIFIER_BACKOFF_UNTIL = 0.0
_CLASSIFIER_BACKOFF_SECONDS = 30.0
_CLASSIFIER_TIMEOUT_SECONDS = 4.0


class IntentResult:
    def __init__(
        self,
        name: str,
        params: dict | None = None,
        confidence: float = 1.0,
        raw: str = "",
        platform: str | None = None,
        needs_confirmation: bool = False,
    ) -> None:
        self.name = name
        self.params = params or {}
        self.confidence = confidence
        self.raw = raw
        self.platform = platform
        self.needs_confirmation = needs_confirmation

    @property
    def intent(self) -> str:
        return self.name

    @property
    def entities(self) -> dict:
        return self.params

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
            return {
                "type": "open_project",
                "name": params.get("name"),
                "editor": params.get("editor", "auto"),
            }
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
            file_path = str(params.get("path", "") or "").strip()
            if file_path:
                return {
                    "type": "create_file",
                    "path": file_path,
                    "content": params.get("content", ""),
                }
            return {
                "type": "create_file_in_editor",
                "filename": params.get("filename", "untitled"),
                "editor": params.get("editor", "auto"),
            }
        if name == "create_folder":
            return {
                "type": "create_folder",
                "path": params.get("path", ""),
                "name": params.get("name", ""),
            }
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
        if name == "news":
            return {
                "type": "run_agent",
                "agent": "news",
                "topic": params.get("topic", "AI"),
                "hours": params.get("hours", 24),
            }
        if name == "market":
            return {
                "type": "run_agent",
                "agent": "market",
                "topics": params.get("topics", ["AI agents", "LLMs", "open source"]),
            }
        if name == "hackernews":
            return {
                "type": "run_agent",
                "agent": "hackernews",
                "limit": params.get("limit", 10),
            }
        if name == "reddit":
            return {
                "type": "run_agent",
                "agent": "reddit",
                "subreddits": params.get("subreddits", ["MachineLearning", "LocalLLaMA", "programming"]),
                "limit": params.get("limit", 5),
            }
        if name == "github_trending":
            return {
                "type": "run_agent",
                "agent": "github_trending",
                "language": params.get("language", "python"),
                "since": params.get("since", "daily"),
            }
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
                "type": "set_reminder",
                "minutes": params.get("minutes", 30),
                "when": params.get("when", ""),
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
        if name == "compose_email":
            return {
                "type": "compose_email",
                "recipient": params.get("recipient", ""),
                "subject": params.get("subject", ""),
                "body": params.get("body", ""),
            }
        if name == "whatsapp_open":
            return {
                "type": "whatsapp_open",
                "contact": params.get("contact", ""),
            }
        if name == "whatsapp_send":
            return {
                "type": "whatsapp_send",
                "contact": params.get("contact", ""),
                "phone": params.get("phone", ""),
                "message": params.get("message", ""),
            }
        if name == "browser_new_tab":
            return {
                "type": "browser_new_tab",
                "url": params.get("url", ""),
            }
        if name == "browser_search":
            return {
                "type": "browser_search",
                "query": params.get("query", ""),
                "new_tab": params.get("new_tab", True),
            }
        if name == "browser_close_tab":
            return {"type": "browser_close_tab"}
        if name == "browser_close_window":
            return {"type": "browser_close_window"}
        if name == "browser_go_back":
            return {"type": "browser_go_back"}
        if name == "browser_refresh":
            return {"type": "browser_refresh"}
        if name == "pause_video":
            return {"type": "pause_video"}
        if name == "volume_set":
            return {"type": "volume_set", "level": params.get("level", 50)}
        if name == "volume_up":
            return {"type": "volume_up"}
        if name == "volume_down":
            return {"type": "volume_down"}
        if name == "system_volume":
            return {"type": "system_volume", "direction": params.get("direction", "up")}
        if name == "screenshot":
            return {"type": "screenshot"}
        if name == "lock_screen":
            return {"type": "lock_screen"}
        if name == "show_desktop":
            return {"type": "show_desktop"}
        if name == "sleep_mac":
            return {"type": "sleep_mac"}
        if name == "play_music":
            song = str(params.get("song", "") or "").strip()
            if self.platform == "youtube":
                return {
                    "type": "open_url_in_browser",
                    "url": _youtube_search_url(song or params.get("query", "")),
                }
            if song:
                return {"type": "search_and_play", "query": song}
            return {"type": "play_music", "mode": params.get("mode", "focus")}
        if name == "open_url":
            return {"type": "open_url", "url": params.get("url", "")}
        if name == "browser_tab":
            action_name = str(params.get("action", "new") or "new").strip().lower()
            if action_name == "close":
                return {"type": "browser_close_tab"}
            if action_name == "refresh":
                return {"type": "browser_refresh"}
            if action_name == "back":
                return {"type": "browser_go_back"}
            if str(params.get("url", "") or "").strip():
                return {"type": "browser_go_to", "url": params.get("url", "")}
            if str(params.get("search", "") or "").strip():
                return {"type": "browser_search", "query": params.get("search", ""), "new_tab": action_name != "current"}
            return {"type": "browser_new_tab", "url": params.get("url", "")}
        if name == "browser_window":
            return {"type": "browser_window", "action": params.get("action", "new"), "url": params.get("url", "")}
        if name == "web_search":
            return {"type": "run_agent", "agent": "search", "query": params.get("query", self.raw)}
        if name == "volume_control":
            return {"type": "volume_set", "level": params.get("level", 50)}
        if name == "brightness":
            action = {"type": "brightness"}
            if params.get("direction") is not None:
                action["direction"] = params.get("direction")
            if params.get("level") is not None:
                action["level"] = params.get("level")
            return action
        if name == "compose_whatsapp":
            return {
                "type": "compose_whatsapp",
                "contact": params.get("contact", ""),
                "phone": params.get("phone", ""),
                "message": params.get("message", ""),
            }
        if name == "calendar_read":
            return {"type": "calendar_read", "range": params.get("range", "today")}
        if name == "calendar_add":
            return {
                "type": "calendar_add",
                "title": params.get("title", ""),
                "time": params.get("time", ""),
                "duration": params.get("duration", 60),
            }
        if name == "task_read":
            return {"type": "task_read", "filter": params.get("filter", "today")}
        if name == "task_add":
            return {"type": "task_add", "title": params.get("title", ""), "project": params.get("project", "")}
        if name == "task_done":
            return {"type": "task_done", "title": params.get("title", "")}
        if name == "open_file":
            return {"type": "open_file", "path": params.get("path", "")}
        if name == "open_folder":
            return {"type": "open_folder", "path": params.get("path", "")}
        if name == "read_file":
            return {"type": "read_file", "path": params.get("path", "")}
        if name == "write_file":
            return {"type": "write_file", "path": params.get("path", ""), "content": params.get("content", ""), "mode": params.get("mode", "overwrite")}
        if name == "delete_file":
            return {"type": "delete_file", "path": params.get("path", "")}
        if name == "zip_folder":
            return {"type": "zip_folder", "path": params.get("path", "")}
        if name == "find_file":
            return {"type": "find_file", "query": params.get("query", "")}
        if name == "list_files":
            return {"type": "list_files", "path": params.get("path", "")}
        if name == "move_file":
            return {"type": "move_file", "from": params.get("from", ""), "to": params.get("to", "")}
        if name == "copy_file":
            return {"type": "copy_file", "from": params.get("from", ""), "to": params.get("to", "")}
        if name == "run_command":
            return {"type": "run_command", "cmd": params.get("cmd", ""), "cwd": params.get("cwd", "")}
        if name == "git_action":
            return {"type": "git_action", "cmd": params.get("cmd", ""), "message": params.get("message", ""), "needs_confirmation": self.needs_confirmation}
        if name == "vps_check":
            return {"type": "vps_check", "action": params.get("action", "status")}
        if name == "summarize_page":
            return {"type": "summarize_page", "url": params.get("url", "")}
        if name == "summarize_video":
            return {"type": "summarize_video", "url": params.get("url", ""), "save_to_obsidian": bool(params.get("save_to_obsidian", False))}
        if name == "read_screen":
            return {"type": "read_screen", "describe": bool(params.get("describe", True))}
        if name == "take_screenshot":
            return {"type": "take_screenshot", "save": bool(params.get("save", True)), "describe": bool(params.get("describe", True))}
        if name == "focus_app":
            return {"type": "focus_app", "app": params.get("app", "")}
        if name == "quit_app":
            return {"type": "quit_app", "app": params.get("app", "")}
        if name == "minimize_app":
            return {"type": "minimize_app", "app": params.get("app", "")}
        if name == "system_info":
            return {"type": "system_info", "query": params.get("query", "")}
        if name == "dark_mode":
            return {"type": "dark_mode", "enable": params.get("enable")}
        if name == "do_not_disturb":
            return {"type": "do_not_disturb", "enable": params.get("enable")}
        if name == "conversation":
            return None
        return None

    def needs_llm(self) -> bool:
        return self.name in {"unknown", "what_next", "briefing", "question", "greeting"}

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
            "news": "Checking the latest news.",
            "market": "Checking the market pulse.",
            "hackernews": "Checking Hacker News.",
            "reddit": "Checking Reddit.",
            "github_trending": "Checking trending repos.",
            "docker_status": "Checking containers...",
            "obsidian_note": "Saved to Obsidian.",
            "set_reminder": (
                f"Setting a reminder for {self.params.get('when')}."
                if self.params.get("when")
                else f"Reminder in {self.params.get('minutes', 30)} minutes."
            ),
            "open_last_workspace": "Reopening your last workspace.",
            "open_codex": "Opening Codex.",
            "compose_email": (
                f"Drafting an email to {self.params.get('recipient')}."
                if self.params.get("recipient")
                else "Opening Gmail compose."
            ),
            "whatsapp_open": (
                f"Opening WhatsApp for {self.params.get('contact')}."
                if self.params.get("contact")
                else "Opening WhatsApp."
            ),
            "whatsapp_send": (
                f"Sending a WhatsApp message to {self.params.get('contact')}."
                if self.params.get("contact")
                else "Sending the WhatsApp message."
            ),
            "browser_new_tab": "Opening a new tab.",
            "browser_search": "Opening a new tab and searching.",
            "browser_close_tab": "Closing the tab.",
            "browser_close_window": "Closing the window.",
            "browser_go_back": "Going back.",
            "browser_refresh": "Refreshing the page.",
            "pause_video": "Pausing the video.",
            "volume_set": f"Setting volume to {self.params.get('level', 50)}.",
            "volume_up": "Volume up.",
            "volume_down": "Volume down.",
            "system_volume": f"Volume {self.params.get('direction', 'up')}.",
            "screenshot": "Taking a screenshot.",
            "lock_screen": "Locking the screen.",
            "show_desktop": "Showing the desktop.",
            "sleep_mac": "Putting the Mac to sleep.",
            "play_music": (
                f"Playing {self.params.get('song', 'that')}."
                if self.params.get("song")
                else "Playing music."
            ),
            "open_url": "Opening that.",
            "browser_tab": "Handling the tab.",
            "browser_window": "Opening a browser window.",
            "web_search": "Looking that up.",
            "volume_control": f"Setting volume to {self.params.get('level', 50)}.",
            "brightness": "Adjusting brightness.",
            "compose_whatsapp": "Opening WhatsApp.",
            "calendar_read": "Checking your calendar.",
            "calendar_add": "Adding that to the calendar.",
            "task_read": "",
            "task_add": "Adding that task.",
            "task_done": "Marking that done.",
            "open_file": "Opening that file.",
            "open_folder": "Opening that folder.",
            "read_file": "Reading that file.",
            "write_file": "Writing that file.",
            "delete_file": "Deleting that file.",
            "zip_folder": "Zipping that folder.",
            "find_file": "Finding that file.",
            "list_files": "Listing files there.",
            "move_file": "Moving that file.",
            "copy_file": "Copying that file.",
            "run_command": "Running that command.",
            "git_action": "Running that git action.",
            "vps_check": "Checking the VPS.",
            "summarize_page": "Summarizing the page.",
            "summarize_video": "Summarizing the video.",
            "read_screen": "Reading the screen.",
            "take_screenshot": "Taking a screenshot.",
            "focus_app": f"Switching to {self.params.get('app', 'that app')}.",
            "quit_app": f"Quitting {self.params.get('app', 'that app')}.",
            "minimize_app": "Minimizing that app.",
            "system_info": "",
            "dark_mode": "Toggling dark mode.",
            "do_not_disturb": "Toggling do not disturb.",
            "mcp_status": "Checking M C P status.",
            "butler_sleep": "Going quiet.",
        }
        return responses.get(self.name, "")

    def __repr__(self) -> str:
        return f"IntentResult(name={self.name!r}, params={self.params!r}, confidence={self.confidence:.2f})"


Intent = IntentResult


def clean_song_query(query: str) -> str:
    """Strip noise that STT adds to song names."""
    # Remove "on spotify / apple music / youtube" at the end
    query = re.sub(r'\s+on\s+(spotify|apple\s*music|youtube|tidal|deezer)\b.*$', '', query, flags=re.I)
    # Remove trailing filler
    query = re.sub(r'\s+(please|for\s+me|right\s+now|now)\s*$', '', query, flags=re.I)
    # Strip punctuation
    query = query.strip().strip('.,!?')
    return query


def _extract_platform(text: str) -> str | None:
    lowered = _normalize_spaces(str(text or "").lower())
    for keyword, platform in PLATFORM_MAP.items():
        if keyword in lowered:
            return platform
    return None


def is_ambiguous_song_query(query: str) -> bool:
    normalized = re.sub(r"[^a-z0-9\s]", "", query.lower()).strip()
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized in GENERIC_SONG_QUERIES


def _normalize_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


def _normalize_voice_aliases(text: str) -> str:
    normalized = _normalize_spaces(text)
    replacements = (
        (r"\byou\s+tube\b", "youtube"),
        (r"\bu\s*tube\b", "youtube"),
        (r"\byou\s+do\b", "youtube"),
        (r"\bg\s*mail\b", "gmail"),
        (r"\be\s*mail\b", "email"),
    )
    for pattern, replacement in replacements:
        normalized = re.sub(pattern, replacement, normalized, flags=re.IGNORECASE)
    return _normalize_spaces(normalized)


def _clean_lookup_query(query: str) -> str:
    cleaned = _normalize_spaces(query)
    cleaned = re.sub(r"^(?:for|about|please|the)\s+", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+(?:please|thanks|thank you)$", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip(" .!?")


def _extract_news_hours(text: str) -> tuple[str, int]:
    cleaned = _normalize_spaces(text)
    hours = 24

    def replace_match(match: re.Match) -> str:
        nonlocal hours
        amount = int(match.group(1))
        unit = match.group(2).lower()
        hours = amount * 24 if unit.startswith("day") else amount
        return " "

    cleaned = re.sub(
        r"\s*(?:in\s+)?(?:the\s+)?(?:last|past)\s+(\d+)\s*(hours?|days?)\b",
        replace_match,
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"\b(?:today|in the last day|in the past day)\b",
        " ",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = _normalize_spaces(cleaned)
    return cleaned, hours


def _extract_news_request(text: str) -> dict | None:
    normalized = _normalize_voice_aliases(text)
    lowered = normalized.lower()
    if not any(token in lowered for token in ("news", "happened", "happening")):
        return None

    cleaned, hours = _extract_news_hours(lowered)
    if re.search(r"\b(?:air|ai)\s+news\b", cleaned):
        return {"topic": "AI", "hours": max(1, hours)}
    if re.search(r"\btech\s+news\b", cleaned):
        return {"topic": "tech", "hours": max(1, hours)}
    patterns = (
        r"(?:tell me|show me|give me|can you tell me|can you show me|what is|what's)\s+(?:the\s+)?(?:latest|recent|current|breaking)\s+news\s+(.+)$",
        r"(?:latest|recent|current|breaking)\s+news\s+(.+)$",
        r"(?:news)\s+(?:about|on|for|regarding|in)\s+(.+)$",
        r"(?:what happened|what's happening|whats happening)\s+in\s+(.+)$",
        r"(.+?)\s+news$",
    )

    topic = ""
    for pattern in patterns:
        match = re.search(pattern, cleaned)
        if match:
            topic = match.group(1).strip(" .!?")
            break

    if not topic:
        return None

    topic = re.sub(r"^(?:on|about|for|regarding|in)\s+", "", topic).strip()
    topic = _clean_lookup_query(topic)
    topic = re.sub(r"\bair news\b", "ai news", topic, flags=re.IGNORECASE)
    topic = re.sub(r"\bair\b", "AI", topic, flags=re.IGNORECASE)
    topic = re.sub(r"\s+", " ", topic).strip(" .!?")

    if not topic:
        topic = "AI and tech news"
    elif topic.lower() == "tech":
        topic = "tech"
    elif topic.lower() in {"ai", "ai news"}:
        topic = "AI"

    return {"topic": topic, "hours": max(1, hours)}


def _phrase_present(haystack: str, needle: str) -> bool:
    pattern = rf"(?<!\w){re.escape(needle)}(?!\w)"
    return re.search(pattern, haystack) is not None


def _match_from_map(target: str, mapping: dict) -> tuple[str | None, object | None]:
    normalized = _normalize_spaces(target.lower())
    for key in sorted(mapping, key=len, reverse=True):
        if _phrase_present(normalized, key):
            return key, mapping[key]
    return None, None


def _browser_target_from_text(target: str) -> str:
    cleaned = _normalize_spaces(str(target or "").strip().rstrip(".,!?"))
    if not cleaned:
        return ""
    if re.match(r"^https?://", cleaned, flags=re.IGNORECASE):
        return cleaned
    if re.match(r"^(?:www\.)?[a-z0-9.-]+\.[a-z]{2,}(?:/[^\s]*)?$", cleaned, flags=re.IGNORECASE):
        return cleaned if cleaned.lower().startswith("http") else f"https://{cleaned}"
    _matched, value = _match_from_map(cleaned, APP_MAP)
    if isinstance(value, tuple) and len(value) == 2 and value[0] == "browser":
        return str(value[1]).strip()
    return ""


def get_project_map() -> dict:
    global _PROJECT_MAP_CACHE, _PROJECT_MAP_CACHE_AT

    now = time.monotonic()
    if _PROJECT_MAP_CACHE is not None and now - _PROJECT_MAP_CACHE_AT < _PROJECT_MAP_CACHE_TTL_SECONDS:
        return dict(_PROJECT_MAP_CACHE)

    mapping = dict(PROJECT_MAP)
    try:
        from projects.project_store import load_projects

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
    _PROJECT_MAP_CACHE = dict(mapping)
    _PROJECT_MAP_CACHE_AT = now
    return mapping


def detect_editor_choice(text: str) -> str:
    lowered = _normalize_spaces(text.lower())
    for key, value in sorted(EDITOR_HINTS.items(), key=lambda item: len(item[0]), reverse=True):
        if _phrase_present(lowered, key):
            return value
    return "auto"


def _editor_name(editor: str) -> str:
    return "Visual Studio Code" if editor == "vscode" else "Cursor" if editor == "cursor" else "editor"


def _youtube_search_url(query: str) -> str:
    return f"https://www.youtube.com/results?search_query={urllib.parse.quote_plus(_clean_lookup_query(query))}"


def _normalize_spoken_email(recipient: str) -> str:
    cleaned = _clean_lookup_query(recipient)
    if not cleaned:
        return ""
    return normalize_email(cleaned)


def _extract_compose_email_params(text: str) -> dict | None:
    normalized = _normalize_spaces(text)
    lowered = normalized.lower()
    lowered = re.sub(r"\bmale\b", "mail", lowered)

    match = (
        re.search(
            r"\b(?:compose|draft|write|send|open)\s+(?:a\s+)?(?:new\s+)?(?:mail|email)\b(.*)$",
            lowered,
        )
        or re.search(r"\bnew\s+(?:mail|email)\b(.*)$", lowered)
        or re.match(r"^email\b(.*)$", lowered)
    )
    if not match:
        return None

    remainder = _normalize_spaces(match.group(1))
    subject = ""
    body = ""

    body_match = re.search(
        r'\b(?:body|message|saying|says|boyd|massage|massaging|content|text|write|telling)\s+(.+)$',
        remainder,
        flags=re.IGNORECASE,
    )
    if body_match:
        body = body_match.group(1).strip()
        remainder = remainder[: body_match.start()].strip()

    subject_match = re.search(r"\b(?:subject|about)\s+(.+)$", remainder, flags=re.IGNORECASE)
    if subject_match:
        subject = re.sub(r"\s+\b(?:and|with)\b\s*$", "", subject_match.group(1).strip(), flags=re.IGNORECASE)
        remainder = remainder[: subject_match.start()].strip()

    _TRAILING_NOISE = re.compile(
        r'\s+\b(with|and|that|saying|about|regarding|to|for|the|a|an)\b.*$',
        re.IGNORECASE,
    )
    recipient_match = re.search(r"\bto\s+(.+)$", remainder, flags=re.IGNORECASE)
    if recipient_match:
        recipient_text = recipient_match.group(1).strip()
    else:
        # Fallback: extract first email-like token directly
        direct_email = re.search(r'\S+@\S+', remainder)
        recipient_text = direct_email.group(0) if direct_email else ""
    if recipient_text:
        recipient_text = recipient_text.strip(" .!?")
        recipient_text = _TRAILING_NOISE.sub("", recipient_text).strip()
    recipient = _normalize_spoken_email(recipient_text)

    result = {
        "recipient": recipient,
        "subject": _clean_lookup_query(subject),
        "body": " ".join(body.split()).strip(),
    }
    # Fallback: if regex missed subject/body, use LLM structured extraction
    if not result["subject"] and not result["body"]:
        try:
            from brain.structured_output import extract_structured, EmailIntent
            extracted = extract_structured(text, EmailIntent)
            if extracted:
                result["recipient"] = result["recipient"] or extracted.recipient or ""
                result["subject"] = extracted.subject or ""
                result["body"] = extracted.body or ""
        except Exception:
            pass
    return result


def _extract_whatsapp_params(text: str) -> dict | None:
    normalized = _normalize_spaces(text)
    lowered = normalized.lower()

    patterns = (
        r"\bwhatsapp\s+(.+?)(?:\s+(?:message|saying)\s+(.+))?$",
        r"\bsend\s+(?:a\s+)?whatsapp(?:\s+message)?\s+to\s+(.+?)(?:\s+(?:message|saying)\s+(.+))?$",
        r"\bmessage\s+(.+?)\s+on\s+whatsapp(?:\s+(?:message|saying)\s+(.+))?$",
        r"\bopen\s+whatsapp\s+chat(?:\s+with)?\s+(.+)$",
    )

    for pattern in patterns:
        match = re.search(pattern, lowered, flags=re.IGNORECASE)
        if not match:
            continue
        contact = _clean_lookup_query(match.group(1))
        message = _clean_lookup_query(match.group(2)) if match.lastindex and match.lastindex >= 2 and match.group(2) else ""
        phone = ""
        if re.fullmatch(r"[\d+\-\s]{8,20}", contact):
            phone = re.sub(r"[^\d+]", "", contact)
            if phone.startswith("00"):
                phone = f"+{phone[2:]}"
        if not contact:
            return None
        return {
            "contact": contact,
            "phone": phone,
            "message": message,
        }
    return None


def _gmail_compose_url(recipient: str = "", subject: str = "", body: str = "") -> str:
    base = "https://mail.google.com/mail/u/0/?view=cm&fs=1&tf=1"
    cleaned = _normalize_spoken_email(recipient)
    subject_clean = " ".join(str(subject or "").split()).strip()
    body_clean = " ".join(str(body or "").split()).strip()
    params: list[tuple[str, str]] = []
    if cleaned.lower() in LOW_SIGNAL_MAIL_WORDS:
        cleaned = ""
    if cleaned:
        params.append(("to", cleaned))
    if subject_clean:
        params.append(("su", subject_clean))
    if body_clean:
        params.append(("body", body_clean))
    if not params:
        return base
    return f"{base}&{urllib.parse.urlencode(params)}"


def _folder_base_path(text: str) -> str:
    lowered = _normalize_spaces(str(text or "").lower())
    for phrase, target in sorted(FOLDER_LOCATION_MAP.items(), key=lambda item: len(item[0]), reverse=True):
        if phrase in lowered:
            return target
    return "~/Desktop"


def _clean_folder_name(text: str) -> str:
    cleaned = _normalize_spaces(text)
    for phrase in sorted(FOLDER_LOCATION_MAP, key=len, reverse=True):
        cleaned = re.sub(rf"\b{re.escape(phrase)}\b", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(
        r"\b(?:create|make|open|me|a|an|new|folder|called|named|with name|with the name)\b",
        " ",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .!?")
    return cleaned


def _extract_create_folder_params(text: str) -> dict | None:
    normalized = _normalize_spaces(text)
    lowered = normalized.lower()
    if not re.search(r"\b(?:create|make|open)\b", lowered) or "folder" not in lowered:
        return None

    path = _folder_base_path(lowered)
    candidate = ""
    patterns = (
        r"\bfolder\s+(?:called|named)\s+(.+)$",
        r"\b(?:called|named)\s+(.+)$",
        r"\bfolder\s+(.+)$",
    )
    for pattern in patterns:
        match = re.search(pattern, normalized, flags=re.IGNORECASE)
        if match:
            candidate = match.group(1).strip()
            break
    if not candidate:
        candidate = normalized

    name = _clean_folder_name(candidate)
    return {"path": path, "name": name}


def _location_path_for_text(text: str, default: str = "") -> str:
    lowered = _normalize_spaces(str(text or "").lower())
    for phrase, target in sorted(FOLDER_LOCATION_MAP.items(), key=lambda item: len(item[0]), reverse=True):
        if phrase in lowered:
            return target
    return default


def _strip_location_phrases(text: str) -> str:
    cleaned = _normalize_spaces(str(text or ""))
    for phrase in sorted(FOLDER_LOCATION_MAP, key=len, reverse=True):
        cleaned = re.sub(rf"\b{re.escape(phrase)}\b", " ", cleaned, flags=re.IGNORECASE)
    return _normalize_spaces(cleaned)


def _looks_like_file_reference(text: str) -> bool:
    cleaned = _normalize_spaces(str(text or ""))
    lowered = cleaned.lower()
    return bool(
        cleaned.startswith(("~", "/"))
        or "/" in cleaned
        or re.search(r"\.[a-z0-9]{1,8}\b", lowered)
        or any(token in lowered for token in (" file", "file ", "document", "folder"))
        or any(phrase in lowered for phrase in FOLDER_LOCATION_MAP)
    )


def _clean_file_reference(text: str) -> str:
    cleaned = _strip_location_phrases(text)
    cleaned = re.sub(
        r"\b(?:read|open|write|append|overwrite|move|copy|rename|find|show|list|delete|remove|the|my|this|that|a|an|please|for me|contents?|content|named|called)\b",
        " ",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\b(?:file|files|document|documents)\b", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .,!?:;\"'")
    return cleaned


def _file_target_from_text(text: str, default_root: str = "") -> str:
    cleaned = _normalize_spaces(str(text or ""))
    if not cleaned:
        return default_root
    if cleaned.startswith(("~", "/")) or "/" in cleaned:
        return cleaned
    location_root = _location_path_for_text(cleaned, default=default_root)
    filename = _clean_file_reference(cleaned)
    if location_root and filename:
        return str(Path(location_root) / filename)
    return location_root or filename


def _extract_open_folder_params(text: str) -> dict | None:
    lowered = _normalize_spaces(str(text or "").lower())
    if not (
        re.search(r"\bopen\s+finder\b", lowered)
        or re.search(r"\bopen\s+.+\bfolder\b", lowered)
        or re.search(r"\bopen\s+(?:the\s+)?(?:desktop|documents|downloads|home)\b", lowered)
    ):
        return None
    path = _location_path_for_text(text)
    if not path:
        return None
    return {"path": path}


def _extract_open_file_params(text: str) -> dict | None:
    normalized = _normalize_spaces(text)
    lowered = normalized.lower()
    match = re.match(r"^(?:open|launch|start)\s+(.+)$", normalized, flags=re.IGNORECASE)
    if not match:
        return None
    target = match.group(1).strip()
    if not _looks_like_file_reference(target):
        return None
    if "folder" in lowered or "finder" in lowered:
        return None
    return {"path": _file_target_from_text(target)}


def _extract_create_file_params(text: str) -> dict | None:
    normalized = _normalize_spaces(text)
    lowered = normalized.lower()
    if not re.search(r"\b(?:(?:create|make|open)\s+(?:a\s+)?(?:brand\s+new\s+|new\s+)?file|new\s+file)\b", lowered):
        return None

    location_root = _location_path_for_text(normalized)
    filename = extract_requested_filename(text)

    if location_root:
        target_name = filename or "untitled.txt"
        return {"path": str(Path(location_root) / target_name), "filename": target_name}

    if filename:
        return {"filename": filename, "editor": detect_editor_choice(text)}

    return None


def _extract_read_file_params(text: str) -> dict | None:
    normalized = _normalize_spaces(text)
    lowered = normalized.lower()
    if "read" not in lowered:
        return None
    if not _looks_like_file_reference(normalized):
        return None
    if any(token in lowered for token in ("email", "emails", "calendar", "schedule", "screen", "image", "video", "article", "page", "news")):
        return None
    match = re.search(r"\bread\s+(?:the\s+contents\s+of\s+)?(.+)$", normalized, flags=re.IGNORECASE)
    if not match:
        return None
    return {"path": _file_target_from_text(match.group(1))}


def _extract_write_file_params(text: str) -> dict | None:
    normalized = _normalize_spaces(text)
    patterns = (
        (r"\bappend\s+(.+?)\s+to\s+(.+)$", "append"),
        (r"\bwrite\s+(.+?)\s+(?:to|into|in)\s+(.+)$", "overwrite"),
    )
    for pattern, mode in patterns:
        match = re.search(pattern, normalized, flags=re.IGNORECASE)
        if not match:
            continue
        content = match.group(1).strip().strip("\"'")
        target = match.group(2).strip()
        if not content or not target or not _looks_like_file_reference(target):
            return None
        return {"path": _file_target_from_text(target), "content": content, "mode": mode}
    return None


def _extract_delete_file_params(text: str) -> dict | None:
    normalized = _normalize_spaces(text)
    lowered = normalized.lower()
    if not re.search(r"\b(?:delete|remove|trash)\b", lowered):
        return None
    match = re.search(r"\b(?:delete|remove|trash)\s+(.+)$", normalized, flags=re.IGNORECASE)
    if not match:
        return None
    target = match.group(1).strip()
    if not target or not _looks_like_file_reference(target):
        return None
    cleaned = _file_target_from_text(target)
    if not cleaned or cleaned in {"~", "~/Desktop", "~/Documents", "~/Downloads"}:
        return None
    return {"path": cleaned}


def _extract_find_file_params(text: str) -> dict | None:
    normalized = _normalize_spaces(text)
    lowered = normalized.lower()
    if "youtube" in lowered or "google" in lowered:
        return None
    patterns = (
        r"\bfind\s+(?:my\s+)?(.+?)(?:\s+file|\s+document)?$",
        r"\bwhere\s+is\s+(?:my\s+)?(.+?)(?:\s+file|\s+document)?$",
    )
    for pattern in patterns:
        match = re.search(pattern, normalized, flags=re.IGNORECASE)
        if not match:
            continue
        query = _clean_file_reference(match.group(1))
        if query:
            return {"query": query}
    return None


def _extract_list_files_params(text: str) -> dict | None:
    lowered = _normalize_spaces(str(text or "").lower())
    if re.search(r"\bwhat(?:'s| is)\s+on\s+my\s+(?:desktop|documents|downloads|home)\b", lowered):
        path = _location_path_for_text(lowered)
        return {"path": path or "~/Desktop"}
    if re.search(r"\b(?:list|show)\s+(?:my\s+)?files?\b", lowered):
        path = _location_path_for_text(lowered, default="~/Desktop")
        return {"path": path}
    return None


def _extract_move_file_params(text: str) -> dict | None:
    normalized = _normalize_spaces(text)
    match = re.search(r"\bmove\s+(.+?)\s+to\s+(.+)$", normalized, flags=re.IGNORECASE)
    if not match:
        return None
    source = _clean_file_reference(match.group(1))
    destination = _file_target_from_text(match.group(2))
    if not source or not destination:
        return None
    return {"from": source, "to": destination}


def _extract_copy_file_params(text: str) -> dict | None:
    normalized = _normalize_spaces(text)
    match = re.search(r"\bcopy\s+(.+?)\s+to\s+(.+)$", normalized, flags=re.IGNORECASE)
    if not match:
        return None
    source = _clean_file_reference(match.group(1))
    destination = _file_target_from_text(match.group(2))
    if not source or not destination:
        return None
    return {"from": source, "to": destination}


def _extract_rename_file_params(text: str) -> dict | None:
    normalized = _normalize_spaces(text)
    match = re.search(r"\brename\s+(.+?)\s+to\s+(.+)$", normalized, flags=re.IGNORECASE)
    if not match:
        return None
    source = _clean_file_reference(match.group(1))
    destination = _clean_file_reference(match.group(2))
    if not source or not destination:
        return None
    return {"from": source, "to": destination}


def _extract_zip_folder_params(text: str) -> dict | None:
    normalized = _normalize_spaces(text)
    lowered = normalized.lower()
    if not re.search(r"\b(?:zip|archive)\b", lowered):
        return None

    if re.search(r"\b(?:zip|archive)\s+(?:this|that)\s+folder\b", lowered):
        return {"path": ""}

    path = _location_path_for_text(normalized)
    if path and "folder" in lowered:
        return {"path": path}
    if path and re.search(r"\b(?:zip|archive)\b", lowered):
        return {"path": path}

    match = re.search(r"\b(?:zip|archive)\s+(.+?)(?:\s+folder)?$", normalized, flags=re.IGNORECASE)
    if not match:
        return None
    target = match.group(1).strip()
    if not target:
        return None
    cleaned = _file_target_from_text(target)
    return {"path": cleaned} if cleaned else None


def _task_filter_for_text(text: str) -> str:
    lowered = _normalize_spaces(str(text or "").lower())
    if "tomorrow" in lowered:
        return "tomorrow"
    if any(token in lowered for token in ("today", "right now", "now")):
        return "today"
    return "today"


def _calendar_range_for_text(text: str) -> str:
    lowered = _normalize_spaces(str(text or "").lower())
    if "next week" in lowered:
        return "next_week"
    if "this week" in lowered or "rest of the week" in lowered or "rest of week" in lowered:
        return "this_week"
    if re.search(r"\b(?:next|upcoming)\b", lowered) and any(
        token in lowered for token in ("meeting", "meetings", "event", "events", "appointment", "call", "calendar", "schedule", "agenda")
    ):
        return "next"
    if "tomorrow" in lowered:
        return "tomorrow"
    return "today"


def _extract_calendar_read_params(text: str) -> dict | None:
    lowered = _normalize_spaces(str(text or "").lower())
    if not any(
        token in lowered
        for token in ("calendar", "schedule", "meeting", "meetings", "agenda", "free", "busy", "booked", "available")
    ):
        return None
    if re.search(
        r"\b(?:what(?:'s| is| are)|show|check|read|do i have|am i free|any|when(?:'s| is)?|free|busy|booked|available)\b",
        lowered,
    ):
        return {"range": _calendar_range_for_text(text)}
    return None


def _extract_calendar_add_params(text: str) -> dict | None:
    normalized = _normalize_spaces(text)
    lowered = normalized.lower()
    if re.search(r"\b(?:task|todo|to-do)\b", lowered):
        return None
    if not any(token in lowered for token in ("calendar", "schedule", "meeting", "event", "call")):
        return None

    patterns = (
        r"\b(?:add|put)\s+(.+?)\s+(?:to|on)\s+(?:my\s+)?calendar(?:\s+(?:for|at|on)\s+(.+))?$",
        r"\b(?:schedule|book)\s+(.+?)\s+(?:for|at|on)\s+(.+)$",
    )
    for pattern in patterns:
        match = re.search(pattern, normalized, flags=re.IGNORECASE)
        if not match:
            continue
        title = _normalize_spaces(match.group(1))
        when = _normalize_spaces(match.group(2) or "")
        title = re.sub(r"^(?:a|an|the)\s+", "", title, flags=re.IGNORECASE).strip()
        if title and when:
            return {"title": title, "time": when, "duration": 60}

    generic = re.search(
        r"\b(?:add|create|make|schedule|book)\s+(?:a\s+|an\s+)?(.+)$",
        normalized,
        flags=re.IGNORECASE,
    )
    if not generic:
        return None
    remainder = _normalize_spaces(generic.group(1))
    time_anchor = re.search(
        r"\b(?:"
        r"today|tomorrow|tonight|"
        r"this\s+(?:morning|afternoon|evening|week)|"
        r"next\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|week)|"
        r"(?:at\s+)?\d{1,2}(?::\d{2})?\s*(?:am|pm)|"
        r"noon|midnight"
        r")\b",
        remainder,
        flags=re.IGNORECASE,
    )
    if not time_anchor:
        return None
    title = _normalize_spaces(remainder[: time_anchor.start()])
    when = _normalize_spaces(remainder[time_anchor.start() :])
    title = re.sub(r"\s+(?:for|at|on)$", "", title, flags=re.IGNORECASE).strip()
    title = re.sub(r"^(?:a|an|the)\s+", "", title, flags=re.IGNORECASE).strip()
    named_title = re.search(
        r"^(?:meeting|event|appointment|call)\s+(?:called|named|titled)\s+(.+)$",
        title,
        flags=re.IGNORECASE,
    )
    if named_title:
        title = _normalize_spaces(named_title.group(1))
    if title and when:
        return {"title": title, "time": when, "duration": 60}
    return None


def _extract_reminder_params(text: str) -> dict | None:
    normalized = _normalize_spaces(text)
    lowered = normalized.lower()
    if "remind me" not in lowered:
        return None

    relative = re.search(
        r"\bremind me in (\d+)\s*(minutes|minute|hours|hour|hr|min)s?(?:\s+to\s+(.+))?",
        lowered,
    )
    if relative:
        amount = int(relative.group(1))
        unit = relative.group(2)
        minutes = amount * 60 if unit in {"hour", "hours", "hr"} else amount
        return {
            "minutes": minutes,
            "message": relative.group(3) or "Butler reminder",
        }

    absolute_patterns = (
        r"\bremind me (?:at|on)\s+(.+?)\s+to\s+(.+)$",
        r"\bremind me\s+(tomorrow(?:\s+(?:morning|afternoon|evening|night))?|tonight|this evening|today(?:\s+at\s+.+)?)\s+to\s+(.+)$",
    )
    for pattern in absolute_patterns:
        match = re.search(pattern, normalized, flags=re.IGNORECASE)
        if not match:
            continue
        if len(match.groups()) == 2:
            when, message = match.group(1), match.group(2)
        else:
            continue
        cleaned_when = _normalize_spaces(when)
        cleaned_message = _normalize_spaces(message)
        if cleaned_when and cleaned_message:
            return {"when": cleaned_when, "message": cleaned_message}
    return None


def _extract_task_add_params(text: str) -> dict | None:
    normalized = _normalize_spaces(text)
    patterns = (
        r"\b(?:add|create|make)\s+(?:a\s+)?task\s+to\s+(.+?)(?:\s+for\s+([a-z0-9][\w .-]*))?$",
        r"\b(?:add|create|make)\s+(.+?)\s+to\s+(?:my\s+)?tasks?(?:\s+for\s+([a-z0-9][\w .-]*))?$",
    )
    for pattern in patterns:
        match = re.search(pattern, normalized, flags=re.IGNORECASE)
        if not match:
            continue
        title = _clean_lookup_query(match.group(1))
        project = _clean_lookup_query(match.group(2) or "")
        if title:
            return {"title": title, "project": project}
    return None


def _system_info_query(text: str) -> str:
    lowered = _normalize_spaces(str(text or "").lower())
    if "wifi" in lowered or "wi-fi" in lowered:
        return "wifi"
    if "storage" in lowered or "disk" in lowered or re.search(r"\bspace\b", lowered):
        return "storage"
    if "battery" in lowered or "charge" in lowered:
        return "battery"
    return ""


def _extract_system_control_intent(text: str) -> IntentResult | None:
    lowered = _normalize_spaces(_normalize_voice_aliases(str(text or "").lower()))

    if re.search(r"\bmute(?:\s+(?:the\s+)?(?:system|volume|sound|audio))?\b", lowered) and "unmute" not in lowered:
        return Intent("volume_set", {"level": 0}, confidence=0.95, raw=text)

    brightness_match = re.search(r"\b(?:set|make|change)\s+(?:the\s+)?brightness\s+(?:to)?\s*(\d{1,3})\b", lowered)
    if brightness_match:
        level = max(0, min(100, int(brightness_match.group(1))))
        return Intent("brightness", {"level": level}, confidence=0.95, raw=text)

    if re.search(
        r"\b(?:brightness up|increase brightness|raise brightness|brighten(?: the)? screen|make(?: the)? screen brighter)\b",
        lowered,
    ):
        return Intent("brightness", {"direction": "up"}, confidence=0.95, raw=text)

    if re.search(
        r"\b(?:brightness down|decrease brightness|lower brightness|dim(?: the)? screen|make(?: the)? screen dimmer)\b",
        lowered,
    ):
        return Intent("brightness", {"direction": "down"}, confidence=0.95, raw=text)

    if re.search(r"\b(?:turn on|enable|use)\s+dark mode\b|\bdark mode on\b", lowered):
        return Intent("dark_mode", {"enable": True}, confidence=0.95, raw=text)

    if re.search(r"\b(?:turn off|disable)\s+dark mode\b|\bdark mode off\b|\buse light mode\b|\blight mode\b", lowered):
        return Intent("dark_mode", {"enable": False}, confidence=0.95, raw=text)

    if re.search(r"\b(?:turn on|enable)\s+(?:do not disturb|dnd)\b|\b(?:do not disturb|dnd)\s+on\b", lowered):
        return Intent("do_not_disturb", {"enable": True}, confidence=0.95, raw=text)

    if re.search(r"\b(?:turn off|disable)\s+(?:do not disturb|dnd)\b|\b(?:do not disturb|dnd)\s+off\b", lowered):
        return Intent("do_not_disturb", {"enable": False}, confidence=0.95, raw=text)

    if re.search(r"\b(?:lock(?: my)? screen|lock the screen)\b", lowered):
        return Intent("lock_screen", confidence=0.95, raw=text)

    if re.search(r"\b(?:show(?: me)?(?: the)? desktop)\b", lowered):
        return Intent("show_desktop", confidence=0.95, raw=text)

    if re.search(r"\b(?:put (?:my |the )?(?:mac|computer) to sleep)\b", lowered):
        return Intent("sleep_mac", confidence=0.95, raw=text)

    return None


def _broadcast_classifier_result(intent_name: str, confidence: float, text: str) -> None:
    from capabilities.contracts import ClassifierResult

    payload = ClassifierResult(
        intent=str(intent_name or "unknown").strip() or "unknown",
        confidence=round(float(confidence or 0.0), 3),
        raw_text=_normalize_spaces(text)[:200],
        source=_CLASSIFIER_MODEL,
        at=time.strftime("%Y-%m-%dT%H:%M:%S"),
    ).to_dict()
    try:
        from runtime import note_runtime_event, publish_ui_event

        publish_ui_event("classifier_result", payload)
        note_runtime_event(
            "classifier_result",
            f"Classifier: {payload['intent']}",
            {
                "confidence": payload["confidence"],
                "text": payload.get("raw_text", ""),
            },
        )
    except Exception:
        pass


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


def _normalize_recent_history(turn_limit: int, current_text: str) -> str:
    turns = list(getattr(ctx, "turns", []) or [])
    cleaned_current = _normalize_spaces(str(current_text or ""))
    if turns:
        last = turns[-1]
        if (
            isinstance(last, dict)
            and str(last.get("role", "")).strip().lower() == "user"
            and _normalize_spaces(str(last.get("text", ""))) == cleaned_current
        ):
            turns = turns[:-1]

    lines = []
    for turn in turns[-turn_limit:]:
        if not isinstance(turn, dict):
            continue
        role = str(turn.get("role", "")).strip().lower()
        text = _normalize_spaces(str(turn.get("text", "")))
        if not text:
            continue
        speaker = "User" if role == "user" else "Burry"
        lines.append(f"{speaker}: {text}")
    return "\n".join(lines) if lines else "None"


def _strip_json_envelope(raw: str) -> str:
    cleaned = str(raw or "").strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    if cleaned.startswith("{") and cleaned.endswith("}"):
        return cleaned
    match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    return match.group(0) if match else cleaned


def _running_under_tests() -> bool:
    forced = str(os.environ.get("BURRY_FORCE_CLASSIFIER_ROUTE", "")).strip().lower()
    if forced in {"1", "true", "yes", "on"}:
        return False
    argv = " ".join(sys.argv).lower()
    return "pytest" in argv or "unittest" in argv


def _classifier_prompt(text: str) -> str:
    return CLASSIFIER_SYSTEM.format(
        recent_history=_normalize_recent_history(4, text),
        text=str(text or "").replace('"', '\\"'),
    )


def _instant_action_for_text(text: str) -> dict | None:
    normalized = _normalize_voice_aliases(text).lower().strip(" .!?")
    for phrase, action in INSTANT_PATTERNS.items():
        if " " in phrase:
            if normalized == phrase:
                return dict(action)
            continue
        if normalized == phrase:
            return dict(action)
    return None


def _intent_from_action(action: dict, text: str) -> IntentResult:
    action_type = str(action.get("type", "")).strip()
    if action_type == "volume_set":
        return Intent("volume_set", {"level": action.get("level", 0)}, confidence=1.0, raw=text)
    if action_type == "brightness":
        return Intent("brightness", {"direction": action.get("direction", "up")}, confidence=1.0, raw=text)
    if action_type == "dark_mode":
        return Intent("dark_mode", {"enable": action.get("enable")}, confidence=1.0, raw=text)
    if action_type == "do_not_disturb":
        return Intent("do_not_disturb", {"enable": action.get("enable")}, confidence=1.0, raw=text)
    if action_type in {"spotify_pause", "spotify_next", "spotify_prev", "screenshot", "lock_screen", "show_desktop", "sleep_mac", "volume_up", "volume_down"}:
        return Intent(action_type, confidence=1.0, raw=text)
    if action_type == "browser_new_tab":
        return Intent("browser_new_tab", confidence=1.0, raw=text)
    if action_type == "browser_close_tab":
        return Intent("browser_close_tab", confidence=1.0, raw=text)
    return Intent("unknown", confidence=0.0, raw=text)


def _classifier_backoff_active() -> bool:
    with _CLASSIFIER_LOCK:
        return time.monotonic() < _CLASSIFIER_BACKOFF_UNTIL


def _mark_classifier_backoff() -> None:
    global _CLASSIFIER_BACKOFF_UNTIL
    with _CLASSIFIER_LOCK:
        _CLASSIFIER_BACKOFF_UNTIL = time.monotonic() + _CLASSIFIER_BACKOFF_SECONDS


def _clear_classifier_backoff() -> None:
    global _CLASSIFIER_BACKOFF_UNTIL
    with _CLASSIFIER_LOCK:
        _CLASSIFIER_BACKOFF_UNTIL = 0.0


def _call_classifier(prompt: str) -> str:
    if _running_under_tests() or _classifier_backoff_active():
        return ""

    try:
        result = _call(
            prompt,
            _CLASSIFIER_MODEL,
            temperature=0.0,
            max_tokens=260,
            timeout_hint="classifier",
        )
        _clear_classifier_backoff()
        return str(result or "").strip()
    except Exception:
        _mark_classifier_backoff()
        return ""


def _normalize_classifier_payload(intent_name: str, params: dict, platform: str | None, text: str) -> tuple[str, dict, str | None]:
    normalized_intent = str(intent_name or "unknown").strip() or "unknown"
    normalized_params = dict(params or {})
    normalized_platform = str(platform or "").strip() or None

    if normalized_intent == "compose_email":
        recipient = str(normalized_params.get("to", "") or normalized_params.get("recipient", "")).strip()
        normalized_params["recipient"] = recipient
        normalized_params["to"] = recipient
        normalized_params.setdefault("subject", "")
        normalized_params.setdefault("body", "")
    if normalized_intent == "play_music":
        song = str(normalized_params.get("song", "") or normalized_params.get("query", "")).strip()
        artist = str(normalized_params.get("artist", "") or "").strip()
        if artist and song and artist.lower() not in song.lower():
            song = f"{song} {artist}".strip()
        normalized_params["song"] = song or clean_song_query(text)
        if not normalized_platform:
            normalized_platform = _extract_platform(text)
    if normalized_intent == "open_app":
        app = str(normalized_params.get("app", "") or "").strip()
        if app:
            app_key, mapped = _match_from_map(app, APP_MAP)
            if mapped is not None:
                normalized_params["app"] = mapped
                normalized_params.setdefault("name", app_key if isinstance(mapped, tuple) else mapped)
    if normalized_intent == "open_project":
        normalized_params.setdefault("editor", detect_editor_choice(text))
    if normalized_intent == "browser_tab":
        normalized_params["action"] = str(normalized_params.get("action", "new") or "new").strip().lower()
    if normalized_intent == "volume_control":
        try:
            normalized_params["level"] = max(0, min(100, int(normalized_params.get("level", 50))))
        except Exception:
            normalized_params["level"] = 50
    if normalized_intent == "create_folder":
        extracted = _extract_create_folder_params(text) or {}
        name = str(normalized_params.get("name", "") or extracted.get("name", "")).strip()
        path = str(normalized_params.get("path", "") or extracted.get("path", "")).strip()
        normalized_params["name"] = _clean_folder_name(name) if name else ""
        normalized_params["path"] = path or "~/Desktop"
    if normalized_intent == "create_file":
        extracted = _extract_create_file_params(text) or {}
        normalized_params.setdefault("filename", str(normalized_params.get("filename", "") or extracted.get("filename", "") or extract_requested_filename(text) or "untitled.txt"))
        if extracted.get("path"):
            normalized_params["path"] = str(normalized_params.get("path", "") or extracted.get("path", ""))
    if normalized_intent == "set_reminder":
        extracted = _extract_reminder_params(text) or {}
        normalized_params.setdefault("message", extracted.get("message", "Butler reminder"))
        if extracted.get("minutes") is not None:
            normalized_params["minutes"] = int(normalized_params.get("minutes", extracted.get("minutes", 30)) or extracted.get("minutes", 30))
        if extracted.get("when"):
            normalized_params["when"] = str(normalized_params.get("when", "") or extracted.get("when", ""))
    if normalized_intent in {"open_file", "read_file"}:
        normalized_params["path"] = _file_target_from_text(str(normalized_params.get("path", "") or text))
    if normalized_intent == "open_folder":
        normalized_params["path"] = _location_path_for_text(str(normalized_params.get("path", "") or text), default="~/Desktop")
    if normalized_intent == "write_file":
        normalized_params["path"] = _file_target_from_text(str(normalized_params.get("path", "") or text))
        normalized_params.setdefault("mode", "overwrite")
    if normalized_intent in {"move_file", "copy_file"}:
        normalized_params["from"] = _clean_file_reference(str(normalized_params.get("from", "") or ""))
        normalized_params["to"] = _file_target_from_text(str(normalized_params.get("to", "") or ""))
    if normalized_intent == "find_file":
        normalized_params["query"] = _clean_file_reference(str(normalized_params.get("query", "") or text))
    if normalized_intent == "list_files":
        normalized_params["path"] = _location_path_for_text(str(normalized_params.get("path", "") or text), default="~/Desktop")
    if normalized_intent == "delete_file":
        normalized_params["path"] = _file_target_from_text(str(normalized_params.get("path", "") or text))
    if normalized_intent == "zip_folder":
        normalized_params["path"] = _file_target_from_text(str(normalized_params.get("path", "") or text))
    if normalized_intent == "conversation":
        normalized_params.setdefault("topic", _clean_lookup_query(text))
    return normalized_intent, normalized_params, normalized_platform


def _classifier_intent(text: str) -> IntentResult | None:
    raw = _call_classifier(_classifier_prompt(text))
    if not raw:
        return None

    try:
        payload = json.loads(_strip_json_envelope(raw))
    except Exception:
        return None

    intent_name, params, platform = _normalize_classifier_payload(
        payload.get("intent", "unknown"),
        payload.get("params") if isinstance(payload.get("params"), dict) else {},
        payload.get("platform"),
        text,
    )
    try:
        confidence = float(payload.get("confidence", 0.0) or 0.0)
    except Exception:
        confidence = 0.0
    needs_confirmation = bool(payload.get("needs_confirmation", False))
    _broadcast_classifier_result(intent_name, confidence, text)

    if confidence < 0.4:
        return Intent(
            "conversation",
            {"topic": params.get("topic", _clean_lookup_query(text) or text)},
            confidence=confidence,
            raw=text,
            platform=platform,
            needs_confirmation=needs_confirmation,
        )

    return Intent(
        intent_name,
        params,
        confidence=confidence,
        raw=text,
        platform=platform,
        needs_confirmation=needs_confirmation,
    )


def _legacy_route(text: str) -> IntentResult:
    lowered = _normalize_voice_aliases(text.lower())
    lowered_compact = _normalize_spaces(lowered)

    if lowered_compact in {
        "what's next",
        "whats next",
        "what should i",
        "what do i work on",
        "what should i do",
    }:
        return Intent("what_next", confidence=0.95, raw=text)

    if lowered in {
        "bye",
        "goodbye",
        "sleep",
        "stop",
        "quiet",
        "be quiet",
        "go quiet",
        "go silent",
        "shut up",
        "stop listening",
        "burry sleep",
        "go to sleep",
        "go to sleep burry",
    }:
        return Intent("butler_sleep", raw=text)

    if re.search(r"\b(wake up|wake|burry wake|start listening|hey burry|listen up)\b", lowered):
        return Intent("butler_wake", raw=text)

    calendar_read_params = _extract_calendar_read_params(text)
    if calendar_read_params is not None:
        return Intent("calendar_read", calendar_read_params, confidence=0.95, raw=text)

    calendar_add_params = _extract_calendar_add_params(text)
    if calendar_add_params is not None:
        return Intent("calendar_add", calendar_add_params, confidence=0.9, raw=text)

    task_add_params = _extract_task_add_params(text)
    if task_add_params is not None:
        return Intent("task_add", task_add_params, confidence=0.9, raw=text)

    if re.search(r"\b(?:what(?:'s| is| are)\s+)?(?:my\s+)?(?:pending\s+)?tasks?\b", lowered):
        return Intent("task_read", {"filter": _task_filter_for_text(text)}, confidence=0.95, raw=text)

    if lowered in {"recap", "recap me", "tasks", "my tasks", "pending tasks", "what are my tasks"}:
        return Intent("what_next", confidence=0.95, raw=text)

    system_query = _system_info_query(text)
    if system_query:
        return Intent("system_info", {"query": system_query}, confidence=0.95, raw=text)

    system_control_intent = _extract_system_control_intent(text)
    if system_control_intent is not None:
        return system_control_intent

    if re.search(r"\bsummarize\s+(?:this|the current)?\s*(?:page|article|web\s*page|website)\b", lowered):
        return Intent("summarize_page", {"url": ""}, confidence=0.95, raw=text)

    if re.search(r"\bsave\s+(?:notes?|summary)\s+from\s+(?:this|the current)?\s*(?:youtube\s+)?video\b", lowered):
        return Intent(
            "summarize_video",
            {
                "url": "",
                "save_to_obsidian": True,
            },
            confidence=0.95,
            raw=text,
        )

    if re.search(r"\bsummarize\s+(?:this|the current)?\s*(?:youtube\s+)?video\b", lowered):
        return Intent(
            "summarize_video",
            {
                "url": "",
                "save_to_obsidian": "obsidian" in lowered,
            },
            confidence=0.95,
            raw=text,
        )

    if re.search(r"\b(?:what(?:'s| is)\s+on\s+my\s+screen|read\s+(?:the\s+)?screen|describe\s+(?:the\s+)?screen)\b", lowered):
        return Intent("read_screen", {"describe": True}, confidence=0.95, raw=text)

    if lowered in {"news", "latest news", "recent news"}:
        return Intent("news", {"topic": "AI and tech news", "hours": 24}, raw=text)

    if any(value in lowered for value in ("mcp status", "which mcp", "brave mcp", "github mcp")):
        return Intent("mcp_status", confidence=0.95, raw=text)

    search_tab_match = re.search(
        r"\b(?:open|create)\s+(?:a\s+)?new\s+tab(?:\s+to\s+search)?\s+(.+)$",
        lowered,
    )
    if search_tab_match:
        query = _clean_lookup_query(search_tab_match.group(1))
        if query:
            return Intent("browser_search", {"query": query, "new_tab": True}, raw=text)
        return Intent("browser_new_tab", raw=text)

    if lowered in {"open a new tab to search", "open new tab to search"}:
        return Intent("browser_new_tab", raw=text)

    if re.search(r"\b(?:open|create)\s+(?:a\s+)?new\s+tab\b", lowered) or lowered in {"open tab", "new tab"}:
        return Intent("browser_new_tab", raw=text)

    new_window_match = re.search(
        r"\b(?:open|create)\s+(?:a\s+)?new\s+(?:browser\s+)?window(?:\s+(?:to|for|with)\s+(.+))?$",
        lowered,
    )
    target_window_match = re.search(
        r"\bopen\s+(.+?)\s+in\s+(?:a\s+)?new\s+(?:browser\s+)?window\b",
        lowered,
    )
    if new_window_match or target_window_match:
        target_text = ""
        if target_window_match:
            target_text = target_window_match.group(1)
        elif new_window_match:
            target_text = new_window_match.group(1) or ""
        params = {}
        target_url = _browser_target_from_text(target_text)
        if target_url:
            params["url"] = target_url
        return Intent("browser_window", params, raw=text)

    if re.search(r"\bclose\s+(?:the\s+)?tabs?\b", lowered):
        return Intent("browser_close_tab", raw=text)

    if re.search(r"\bclose\s+(?:the\s+)?(?:window|screen)\b", lowered):
        return Intent("browser_close_window", raw=text)

    if lowered in {"go back", "go back page"} or re.search(
        r"\bgo\s+back(?:\s+(?:in|on)\s+(?:the\s+)?)?(?:browser|page|tab|site)?\b",
        lowered,
    ):
        return Intent("browser_go_back", raw=text)

    if lowered in {"refresh", "reload"} or re.search(
        r"\b(?:refresh|reload)\s+(?:the\s+)?(?:page|tab|browser|window|site)?\b",
        lowered,
    ):
        return Intent("browser_refresh", raw=text)

    if any(
        value in lowered
        for value in (
            "what's happening in ai",
            "whats happening in ai",
            "market pulse",
        )
    ):
        return Intent("market", {"topics": ["AI agents", "LLMs", "open source"]}, raw=text)

    if any(
        value in lowered
        for value in (
            "what's on hackernews",
            "whats on hackernews",
            "what's on hacker news",
            "whats on hacker news",
            "check hackernews",
            "check hacker news",
            "hackernews",
            "hacker news",
        )
    ):
        return Intent("hackernews", {"limit": 10}, raw=text)

    news_request = _extract_news_request(text)
    if news_request is not None:
        return Intent("news", news_request, raw=text)

    whatsapp_params = _extract_whatsapp_params(text)
    if whatsapp_params is not None:
        intent_name = "whatsapp_send" if whatsapp_params.get("message") else "whatsapp_open"
        return Intent(intent_name, whatsapp_params, raw=text)

    if re.search(r"\b(?:take|capture)\s+(?:a\s+)?screenshot\b", lowered):
        return Intent("screenshot", raw=text)

    if re.search(r"\b(?:pause|stop)\s+(?:the\s+)?video\b", lowered):
        return Intent("pause_video", raw=text)

    match = re.search(r"\b(?:set|make)\s+(?:the\s+)?volume\s+(?:to)?\s*(\d{1,3})\b", lowered)
    if match:
        level = max(0, min(100, int(match.group(1))))
        return Intent("volume_set", {"level": level}, raw=text)

    if re.search(r"\b(?:volume up|turn up the volume|increase volume|louder)\b", lowered):
        return Intent("system_volume", {"direction": "up"}, raw=text)

    if re.search(r"\b(?:volume down|turn down the volume|decrease volume|quieter)\b", lowered):
        return Intent("system_volume", {"direction": "down"}, raw=text)

    youtube_match = re.search(r"(?:search|find)\s+(.+?)\s+(?:(?:on|in)\s+)?youtube\b", lowered)
    if youtube_match:
        query = _clean_lookup_query(youtube_match.group(1))
        if query:
            return Intent(
                "open_app",
                {
                    "app": ("browser", _youtube_search_url(query)),
                    "name": "YouTube results",
                },
                raw=text,
            )

    youtube_match = re.search(r"(?:open|launch|start)\s+youtube\s+(?:and\s+)?search\s+(.+)$", lowered)
    if youtube_match:
        query = _clean_lookup_query(youtube_match.group(1))
        if query:
            return Intent(
                "open_app",
                {
                    "app": ("browser", _youtube_search_url(query)),
                    "name": "YouTube results",
                },
                raw=text,
            )

    compose_params = _extract_compose_email_params(text)
    if compose_params is not None:
        return Intent("compose_email", compose_params, raw=text)

    match = re.match(r"^(?:play|put on)\s+(.+)$", lowered)
    if match:
        platform = _extract_platform(match.group(1))
        if platform == "youtube":
            query = _clean_lookup_query(
                re.sub(r"\b(?:play|put on|on|youtube|music|song)\b", " ", match.group(1), flags=re.IGNORECASE)
            )
            if query:
                return Intent(
                    "open_app",
                    {
                        "app": ("browser", _youtube_search_url(query)),
                        "name": "YouTube results",
                    },
                    raw=text,
                )
        query = clean_song_query(match.group(1).strip())
        if is_ambiguous_song_query(query):
            return Intent("clarify_song", raw=text)
        for key, value in MUSIC_MODES.items():
            if key in query:
                return Intent("spotify_mode", {"mode": value}, raw=text)
        return Intent("spotify_play", {"song": query}, raw=text)

    match = re.search(
        r"(?:change|switch)\s+(?:the\s+)?(?:music|song|track)(?:\s+to)?\s+(.+)$",
        lowered,
    )
    if match:
        platform = _extract_platform(match.group(1))
        if platform == "youtube":
            query = _clean_lookup_query(
                re.sub(r"\b(?:change|switch|music|song|track|to|on|youtube)\b", " ", match.group(1), flags=re.IGNORECASE)
            )
            if query:
                return Intent(
                    "open_app",
                    {
                        "app": ("browser", _youtube_search_url(query)),
                        "name": "YouTube results",
                    },
                    raw=text,
                )
        query = clean_song_query(match.group(1).strip())
        if is_ambiguous_song_query(query):
            return Intent("clarify_song", raw=text)
        return Intent("spotify_play", {"song": query}, raw=text)

    if lowered == "pause" or any(value in lowered for value in ("pause music", "stop music", "pause spotify", "mute")):
        return Intent("spotify_pause", raw=text)

    if any(value in lowered for value in ("next song", "next track", "skip")):
        return Intent("spotify_next", raw=text)

    if any(value in lowered for value in ("previous", "prev song")):
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

    create_file_params = _extract_create_file_params(text)
    if create_file_params is not None:
        return Intent("create_file", create_file_params, raw=text)

    if re.search(r"\b(?:(?:create|make|open)\s+(?:a\s+)?(?:brand\s+new\s+|new\s+)?file|new\s+file)\b", lowered):
        return Intent("clarify_file", {"editor": detect_editor_choice(text)}, confidence=0.55, raw=text)

    folder_params = _extract_create_folder_params(text)
    if folder_params is not None:
        return Intent("create_folder", folder_params, raw=text)

    open_folder_params = _extract_open_folder_params(text)
    if open_folder_params is not None:
        return Intent("open_folder", open_folder_params, raw=text)

    list_files_params = _extract_list_files_params(text)
    if list_files_params is not None:
        return Intent("list_files", list_files_params, raw=text)

    write_file_params = _extract_write_file_params(text)
    if write_file_params is not None:
        return Intent("write_file", write_file_params, raw=text)

    delete_file_params = _extract_delete_file_params(text)
    if delete_file_params is not None:
        return Intent("delete_file", delete_file_params, raw=text)

    read_file_params = _extract_read_file_params(text)
    if read_file_params is not None:
        return Intent("read_file", read_file_params, raw=text)

    move_file_params = _extract_move_file_params(text)
    if move_file_params is not None:
        return Intent("move_file", move_file_params, raw=text)

    copy_file_params = _extract_copy_file_params(text)
    if copy_file_params is not None:
        return Intent("copy_file", copy_file_params, raw=text)

    rename_file_params = _extract_rename_file_params(text)
    if rename_file_params is not None:
        return Intent("move_file", rename_file_params, raw=text)

    find_file_params = _extract_find_file_params(text)
    if find_file_params is not None:
        return Intent("find_file", find_file_params, raw=text)

    zip_folder_params = _extract_zip_folder_params(text)
    if zip_folder_params is not None:
        return Intent("zip_folder", zip_folder_params, raw=text)

    open_file_params = _extract_open_file_params(text)
    if open_file_params is not None:
        return Intent("open_file", open_file_params, raw=text)

    if re.search(r"\b(?:open|launch|start)\s+(?:a\s+)?new project\b", lowered):
        editor = detect_editor_choice(text)
        project_map = get_project_map()
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

    reminder_params = _extract_reminder_params(text)
    if reminder_params is not None:
        return Intent("set_reminder", reminder_params, raw=text)

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
    if any(value in lowered for value in ("ai news", "a i news", "air news", "tech news")):
        topic = "tech" if "tech news" in lowered else "AI"
        return Intent("news", {"topic": topic, "hours": 24}, raw=text)
    if any(value in lowered for value in ("trending repos", "trending repositories", "github trending")):
        return Intent("github_trending", {"language": "python", "since": "daily"}, raw=text)
    if any(
        value in lowered
        for value in (
            "what's reddit saying",
            "whats reddit saying",
            "reddit saying",
            "reddit buzz",
        )
    ):
        return Intent(
            "reddit",
            {"subreddits": ["MachineLearning", "LocalLLaMA", "programming"], "limit": 5},
            raw=text,
        )

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
        project_key, path = _match_from_map(target, get_project_map())
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

    if re.match(
        r"^(?:hi|hello|hey|yo)(?:\s+there)?(?:\s+how are you)?[.!? ]*$",
        lowered,
    ) or re.match(r"^how are (?:you|u)[.!? ]*$", lowered) or re.match(r"^how r u[.!? ]*$", lowered):
        return Intent("greeting", confidence=0.95, raw=text)

    if lowered.endswith("?") or re.match(
        r"^(?:what|why|how|when|where|who|which|can|could|would|should|is|are|am|do|does|did|will)\b",
        lowered,
    ):
        confidence = 0.9 if len(lowered.split()) <= 8 else 0.85
        return Intent("question", confidence=confidence, raw=text)

    # Multi-step complex task pattern → Meta Planner (Phase 5)
    if re.search(r"\b(set up|prepare|do all|everything for|my morning|my routine|and then|step by step)\b", lowered):
        return Intent("plan_and_execute", {"task": text}, confidence=0.7, raw=text)

    return Intent("unknown", confidence=0.0, raw=text)


def _extract_from_conversational(text: str, lowered: str) -> IntentResult | None:
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

    m = re.search(r"\b(?:search|find)\s+(.+?)\s+(?:(?:on|in)\s+)?youtube\b", lowered)
    if m:
        query = _clean_lookup_query(m.group(1))
        if query:
            return Intent(
                "open_app",
                {
                    "app": ("browser", _youtube_search_url(query)),
                    "name": "YouTube results",
                },
                raw=text,
            )

    compose_params = _extract_compose_email_params(text)
    if compose_params is not None:
        return Intent("compose_email", compose_params, raw=text)

    if re.search(r"\bclose\s+(?:the\s+)?tabs?\b", lowered):
        return Intent("browser_close_tab", raw=text)

    if re.search(r"\bclose\s+(?:the\s+)?(?:window|screen)\b", lowered):
        return Intent("browser_close_window", raw=text)

    if re.search(r"\b(?:open|create)\s+(?:a\s+)?new\s+tab\b", lowered):
        return Intent("browser_new_tab", raw=text)

    for extractor, intent_name in (
        (_extract_open_folder_params, "open_folder"),
        (_extract_list_files_params, "list_files"),
        (_extract_write_file_params, "write_file"),
        (_extract_read_file_params, "read_file"),
        (_extract_move_file_params, "move_file"),
        (_extract_copy_file_params, "copy_file"),
        (_extract_rename_file_params, "move_file"),
        (_extract_find_file_params, "find_file"),
        (_extract_open_file_params, "open_file"),
    ):
        params = extractor(text)
        if params is not None:
            return Intent(intent_name, params, raw=text)

    # open a new project window anywhere in text
    if re.search(r"\b(?:open|launch|start)\s+(?:a\s+)?new project\b", lowered):
        editor = detect_editor_choice(text)
        project_map = get_project_map()
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
        project_key, path = _match_from_map(target, get_project_map())
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


def instant_route(text: str) -> IntentResult | None:
    instant_action = _instant_action_for_text(text)
    if instant_action is None:
        return None
    return _intent_from_action(instant_action, text)


def route(text: str, *, allow_instant: bool = True) -> IntentResult:
    if allow_instant:
        instant = instant_route(text)
        if instant is not None:
            return instant

    deterministic = _legacy_route(text)
    if deterministic.name != "unknown" and float(deterministic.confidence or 0.0) >= 0.85:
        return deterministic

    classified = _classifier_intent(text)
    if classified is not None:
        return classified

    return deterministic


# Alias for tests and external callers
route_intent = route


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
