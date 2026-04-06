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
from utils import _clip_text


def analyze_and_learn(session_data: dict) -> None:
    """
    After a session, look at what happened and update memory
    with patterns Butler should remember.
    """
    text = " ".join(str(session_data.get("text", "")).split()).strip()
    speech = " ".join(str(session_data.get("speech", "")).split()).strip()
    resolved_text = " ".join(str(session_data.get("resolved_text", "")).split()).strip()
    intent_name = " ".join(str(session_data.get("intent_name", "")).split()).strip() or "unknown"
    task_type = " ".join(str(session_data.get("task_type", "")).split()).strip() or intent_name
    model = " ".join(str(session_data.get("model", "")).split()).strip()
    results = [result for result in list(session_data.get("results") or []) if isinstance(result, dict)]
    actions = session_data.get("actions", [])
    success = bool(speech) and not any(str(result.get("status", "")).strip().lower() == "error" for result in results)

    if text and not speech:
        add_pattern(f"failed_intent: {intent_name} produced no reply for '{_clip_text(text, 72)}'")

    if resolved_text and resolved_text.lower() != text.lower():
        add_pattern(
            "corrected_flow: "
            f"'{_clip_text(text, 56)}' -> '{_clip_text(resolved_text, 56)}'"
        )

    if model and task_type:
        outcome = "success" if success else "failure"
        add_pattern(f"model_performance: {model} on {task_type} -> {outcome}")

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
