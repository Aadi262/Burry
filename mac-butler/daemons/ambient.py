#!/usr/bin/env python3
"""Background ambient context summaries for the Burry HUD."""

from __future__ import annotations

import json
import os
import shutil
import threading
import time

from brain.ollama_client import _call
from memory.store import load_recent_sessions
from projects.project_store import load_projects
from runtime import note_ambient_context

AMBIENT_INTERVAL_SECONDS = 10 * 60
AMBIENT_FALLBACK_MODEL = "gemma4:e4b"
_AMBIENT_LOCK = threading.Lock()
_AMBIENT_THREAD: threading.Thread | None = None


def _clip(text: str, limit: int = 120) -> str:
    cleaned = " ".join(str(text or "").split()).strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 3].rstrip() + "..."


def _bitnet_available() -> bool:
    binary = os.environ.get("BITNET_BIN", "").strip() or "bitnet"
    return shutil.which(binary) is not None


def _ambient_model() -> str:
    if _bitnet_available():
        return os.environ.get("BURRY_AMBIENT_MODEL", "").strip() or "bitnet"
    return AMBIENT_FALLBACK_MODEL


def _session_brief(entry: dict) -> str:
    question = _clip(entry.get("text", ""), limit=72)
    speech = _clip(entry.get("speech", ""), limit=88)
    if question and speech:
        return f"{question} -> {speech}"
    return question or speech or _clip(entry.get("context", ""), limit=88) or "No recent session detail."


def _project_brief(project: dict) -> str:
    name = _clip(project.get("name", ""), limit=40) or "unknown"
    status = _clip(project.get("status", ""), limit=20) or "unknown"
    next_tasks = [str(item).strip() for item in list(project.get("next_tasks") or []) if str(item).strip()]
    blockers = [str(item).strip() for item in list(project.get("blockers") or []) if str(item).strip()]
    if blockers:
        return f"{name} [{status}] blocker: {_clip(blockers[0], limit=88)}"
    if next_tasks:
        return f"{name} [{status}] next: {_clip(next_tasks[0], limit=88)}"
    return f"{name} [{status}] steady"


def _fallback_bullets(sessions: list[dict], projects: list[dict]) -> list[str]:
    bullets: list[str] = []
    if sessions:
        bullets.append(_clip(f"Last session: {_session_brief(sessions[0])}", limit=120))
    active = [project for project in projects if str(project.get("status", "")).lower() == "active"]
    if active:
        bullets.append(_clip(_project_brief(active[0]), limit=120))
    if len(active) > 1:
        bullets.append(_clip(_project_brief(active[1]), limit=120))
    elif len(projects) > 1:
        bullets.append(_clip(_project_brief(projects[1]), limit=120))
    elif projects and len(bullets) < 3:
        bullets.append(_clip(_project_brief(projects[0]), limit=120))
    if not bullets:
        bullets = [
            "No recent ambient context yet.",
            "Project state is still syncing.",
            "Recent sessions will appear after the next interaction.",
        ]
    while len(bullets) < 3:
        bullets.append(bullets[-1])
    return bullets[:3]


def _parse_bullets(raw: str) -> list[str]:
    bullets: list[str] = []
    for line in str(raw or "").splitlines():
        cleaned = line.strip()
        if not cleaned:
            continue
        if cleaned[0] in "-*•":
            cleaned = cleaned[1:].strip()
        if not cleaned:
            continue
        bullets.append(_clip(cleaned, limit=120))
        if len(bullets) >= 3:
            break
    return bullets


def _ambient_prompt(sessions: list[dict], projects: list[dict]) -> str:
    session_lines = "\n".join(
        f"- {_session_brief(entry)}"
        for entry in sessions[:3]
    ) or "- No recent sessions."
    project_lines = "\n".join(
        f"- {_project_brief(project)}"
        for project in projects[:6]
    ) or "- No tracked projects."
    return f"""You are Burry's ambient context daemon.
Summarize the operator state into exactly 3 concise bullet lines.

Rules:
- Output exactly 3 lines
- Each line must start with "- "
- Mention blockers or dependencies when clear
- Keep each line under 14 words
- No intro, no numbering, no extra commentary

Recent sessions:
{session_lines}

Project states:
{project_lines}
"""


def generate_ambient_context() -> list[str]:
    sessions = load_recent_sessions(3)
    projects = load_projects()
    prompt = _ambient_prompt(sessions, projects)
    model = _ambient_model()
    try:
        raw = _call(prompt, model, temperature=0.2, max_tokens=120)
        bullets = _parse_bullets(raw)
        if len(bullets) == 3:
            return bullets
    except Exception:
        pass

    if model != AMBIENT_FALLBACK_MODEL:
        try:
            raw = _call(prompt, AMBIENT_FALLBACK_MODEL, temperature=0.2, max_tokens=120)
            bullets = _parse_bullets(raw)
            if len(bullets) == 3:
                return bullets
        except Exception:
            pass

    return _fallback_bullets(sessions, projects)


def ambient_tick() -> list[str]:
    bullets = generate_ambient_context()
    note_ambient_context(bullets)
    return bullets


def _ambient_loop() -> None:
    while True:
        try:
            ambient_tick()
        except Exception:
            pass
        time.sleep(AMBIENT_INTERVAL_SECONDS)


def start_ambient_daemon() -> threading.Thread:
    global _AMBIENT_THREAD
    with _AMBIENT_LOCK:
        if _AMBIENT_THREAD is not None and _AMBIENT_THREAD.is_alive():
            return _AMBIENT_THREAD
        _AMBIENT_THREAD = threading.Thread(target=_ambient_loop, daemon=True, name="burry-ambient")
        _AMBIENT_THREAD.start()
        return _AMBIENT_THREAD
