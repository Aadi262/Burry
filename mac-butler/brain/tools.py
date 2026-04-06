#!/usr/bin/env python3
"""Tool schema for Burry's tool-calling brain path."""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "open_project",
            "description": "Open a project in the editor by name.",
            "parameters": {
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_shell",
            "description": "Run a safe shell command in a project directory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string"},
                    "project": {"type": "string"},
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browse_web",
            "description": "Search the web or fetch and summarize a URL.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "url": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "recall_memory",
            "description": "Search past sessions and memory for relevant context.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "project": {"type": "string"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "take_screenshot_and_describe",
            "description": "Take a screenshot of the current screen and describe it.",
            "parameters": {
                "type": "object",
                "properties": {"question": {"type": "string"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_commit",
            "description": "Generate a commit message from staged git changes, request confirmation, and commit.",
            "parameters": {
                "type": "object",
                "properties": {
                    "project": {"type": "string"},
                    "message_hint": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_app",
            "description": "Open or focus a macOS application by name.",
            "parameters": {
                "type": "object",
                "properties": {
                    "app": {"type": "string"},
                    "mode": {"type": "string", "enum": ["smart", "focus", "new"]},
                },
                "required": ["app"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "spotify_control",
            "description": "Control Spotify playback or report the current track.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["play", "pause", "next", "prev", "volume_up", "volume_down", "now_playing"],
                    },
                    "query": {"type": "string"},
                },
                "required": ["action"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_reminder",
            "description": "Create a reminder after a time offset.",
            "parameters": {
                "type": "object",
                "properties": {
                    "time": {"type": "string"},
                    "message": {"type": "string"},
                },
                "required": ["time", "message"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ssh_vps",
            "description": "Run a shell command on the configured VPS.",
            "parameters": {
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "obsidian_note",
            "description": "Create or append an Obsidian note.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["title", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_notification",
            "description": "Send a desktop notification on the Mac.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "message": {"type": "string"},
                },
                "required": ["title", "message"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search_summarize",
            "description": "Search the web and speak a short summary.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    },
]
