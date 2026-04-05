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
                "properties": {
                    "name": {"type": "string"},
                },
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
                "properties": {
                    "question": {"type": "string"},
                },
            },
        },
    },
]

