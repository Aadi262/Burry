#!/usr/bin/env python3
"""
memory/learner.py
Background learner — watches what Butler does and updates profile.yaml
with new patterns, project states, and learned preferences.
Runs silently after each session.
"""

from datetime import datetime
from pathlib import Path

from memory.store import _load, add_pattern


def analyze_and_learn(session_data: dict) -> None:
    """
    After a session, look at what happened and update memory
    with patterns Butler should remember.
    """
    actions = session_data.get("actions", [])

    opened_apps = [action["app"] for action in actions if action.get("type") == "open_app"]
    if "Cursor" in opened_apps and any(
        action.get("type") == "play_music" for action in actions
    ):
        add_pattern("Aditya usually opens Cursor and music together when starting work")

    hour = datetime.now().hour
    if hour >= 23 or hour <= 4:
        add_pattern(f"Aditya works late nights regularly (session at {hour}:00)")

    opened_folders = [
        Path(action["path"]).name
        for action in actions
        if action.get("type") == "open_folder"
    ]
    for folder in opened_folders:
        add_pattern(f"Project '{folder}' opened in this session")


def get_learned_patterns() -> str:
    """Returns patterns as a string for LLM context."""
    data = _load()
    patterns = data.get("patterns", [])
    if not patterns:
        return ""
    return "[LEARNED PATTERNS]\n" + "\n".join(f"  - {pattern}" for pattern in patterns[-10:])


if __name__ == "__main__":
    print(get_learned_patterns() or "No patterns learned yet")
