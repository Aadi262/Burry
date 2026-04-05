#!/usr/bin/env python3
"""Dynamic speech mood for Burry's live operator voice."""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path


MOODS = {
    "focused": {
        "label": "Focused",
        "instruction": "Be sharp and direct. Cut to the next real move with no fluff.",
        "note": "Locked on the next concrete step.",
    },
    "hyped": {
        "label": "Hyped",
        "instruction": "Be energetic and decisive. Celebrate real momentum without sounding fake.",
        "note": "Momentum is up. Push the next win.",
    },
    "proud": {
        "label": "Proud",
        "instruction": "Be warm and confident. Acknowledge real progress, then keep moving.",
        "note": "Recent progress is real. Keep shipping.",
    },
    "playful": {
        "label": "Playful",
        "instruction": "Be light, curious, and slightly teasing while staying useful.",
        "note": "Loose tone, but still useful.",
    },
    "tired": {
        "label": "Tired",
        "instruction": "Be calm and honest. Short lines, low drama, focus on the quickest path.",
        "note": "Late-hour mode. Keep it short and useful.",
    },
    "blunt": {
        "label": "Blunt",
        "instruction": "Be direct and unsentimental. Call out the blocker clearly, without being rude.",
        "note": "Something is broken or stalled. Say it plainly.",
    },
}

_POSITIVE_TOKENS = ("fixed", "done", "shipped", "merged", "pushed", "completed", "working")
_NEGATIVE_TOKENS = ("error", "broken", "failed", "offline", "stuck", "segfault", "crash", "bug")
DEFAULT_MOOD = "focused"
MOOD_REFRESH_SECONDS = 600
MOOD_DECAY_SECONDS = 1800
DECAYABLE_MOODS = {"blunt", "urgent"}
MOOD_STATE_PATH = Path(__file__).resolve().parents[1] / "memory" / "mood_state.json"


def _default_mood_state() -> dict:
    return {"mood": DEFAULT_MOOD, "set_at": 0.0, "reason": "default"}


def load_mood_state() -> dict:
    if not MOOD_STATE_PATH.exists():
        return _default_mood_state()
    try:
        data = json.loads(MOOD_STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return _default_mood_state()
    if not isinstance(data, dict):
        return _default_mood_state()
    mood = str(data.get("mood", DEFAULT_MOOD) or DEFAULT_MOOD).strip().lower()
    set_at = data.get("set_at", 0.0)
    reason = str(data.get("reason", "default") or "default").strip()
    try:
        set_at_value = float(set_at or 0.0)
    except Exception:
        set_at_value = 0.0
    return {
        "mood": mood if mood in MOODS else DEFAULT_MOOD,
        "set_at": set_at_value,
        "reason": reason,
    }


def save_mood(mood: str, reason: str) -> dict:
    state = {
        "mood": str(mood or DEFAULT_MOOD).strip().lower() or DEFAULT_MOOD,
        "set_at": float(time.time()),
        "reason": str(reason or "manual").strip() or "manual",
    }
    if state["mood"] not in MOODS:
        state["mood"] = DEFAULT_MOOD
    MOOD_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    MOOD_STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")
    return state


def _load_session_summary() -> str:
    try:
        from memory.store import get_last_session_summary

        return " ".join(str(get_last_session_summary() or "").split()).lower()
    except Exception:
        return ""


def _load_project_snapshot() -> list[dict]:
    try:
        from projects.project_store import load_projects

        return load_projects() or []
    except Exception:
        return []


def _load_active_task_count() -> int:
    try:
        from tasks import get_active_tasks

        return len(get_active_tasks() or [])
    except Exception:
        return 0


def _active_projects(projects: list[dict]) -> list[dict]:
    return [project for project in projects if str(project.get("status", "")).lower() == "active"]


def _blocker_count(projects: list[dict]) -> int:
    count = 0
    for project in projects:
        count += len([item for item in (project.get("blockers") or []) if str(item).strip()])
        try:
            count += int(project.get("open_issues", 0) or 0)
        except Exception:
            continue
    return count


def _has_token(summary: str, tokens: tuple[str, ...]) -> bool:
    return any(token in summary for token in tokens)


def _evaluate_mood() -> tuple[str, str]:
    now = datetime.now()
    hour = now.hour
    summary = _load_session_summary()
    projects = _load_project_snapshot()
    active_projects = _active_projects(projects)
    blockers = _blocker_count(active_projects or projects)
    task_count = _load_active_task_count()

    if _has_token(summary, _NEGATIVE_TOKENS) or blockers >= 5:
        return "blunt", "negative_signals"

    if _has_token(summary, ("shipped", "merged", "pushed")) and blockers <= 2:
        return "hyped", "recent_shipping"

    if _has_token(summary, _POSITIVE_TOKENS):
        return "proud", "recent_progress"

    if 1 <= hour <= 5:
        return "tired", "late_hours"

    if active_projects and task_count >= 3:
        return "focused", "active_workload"

    if 9 <= hour <= 12:
        return "focused", "morning_focus"

    if 20 <= hour <= 23:
        return "playful", "evening_tone"

    return "playful", "default_playful"


def _should_refresh(state: dict, now_ts: float) -> bool:
    age = now_ts - float(state.get("set_at", 0.0) or 0.0)
    if age < 0:
        return True
    if not state.get("set_at"):
        return True
    if str(state.get("reason", "")).strip().lower() == "default":
        return True
    return age >= MOOD_REFRESH_SECONDS


def _resolve_mood_state(*, force_refresh: bool = False) -> dict:
    state = load_mood_state()
    now_ts = float(time.time())
    age = now_ts - float(state.get("set_at", 0.0) or 0.0)
    if age > MOOD_DECAY_SECONDS and state.get("mood") in DECAYABLE_MOODS:
        return save_mood(DEFAULT_MOOD, "decay")
    if not force_refresh and not _should_refresh(state, now_ts):
        return state
    mood, reason = _evaluate_mood()
    if state.get("mood") == mood and state.get("reason") == reason and state.get("set_at"):
        return save_mood(mood, reason)
    return save_mood(mood, reason)


def get_mood(*, force_refresh: bool = False) -> str:
    return str(_resolve_mood_state(force_refresh=force_refresh).get("mood", DEFAULT_MOOD) or DEFAULT_MOOD)


def get_mood_instruction(mood: str) -> str:
    return MOODS.get(mood, MOODS[DEFAULT_MOOD])["instruction"]


def get_mood_note(mood: str) -> str:
    return MOODS.get(mood, MOODS[DEFAULT_MOOD])["note"]


def describe_mood_state() -> dict:
    resolved = _resolve_mood_state()
    mood = str(resolved.get("mood", DEFAULT_MOOD) or DEFAULT_MOOD)
    config = MOODS.get(mood, MOODS[DEFAULT_MOOD])
    return {
        "name": mood,
        "label": config["label"],
        "instruction": config["instruction"],
        "note": config["note"],
        "reason": str(resolved.get("reason", "") or ""),
        "set_at": float(resolved.get("set_at", 0.0) or 0.0),
    }
