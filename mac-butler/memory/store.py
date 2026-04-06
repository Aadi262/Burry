#!/usr/bin/env python3
"""
memory/store.py
Butler's persistent memory — learns from every interaction.
Stores: command history, what worked, project state, learned patterns.
Updates automatically after each session.
"""

import json
import math
import os
import re
from datetime import datetime
from pathlib import Path

import requests

from butler_config import EMBED_MODEL, OLLAMA_LOCAL_URL
from utils import _clip_text, _now_iso

MEMORY_PATH = Path(__file__).parent / "butler_memory.json"
SESSION_DIR = Path(__file__).parent / "layers" / "sessions"


def _default_memory() -> dict:
    return {
        "command_history": [],
        "learned_commands": {},
        "project_state": {},
        "patterns": [],
        "session_count": 0,
        "last_session": None,
    }


def _load() -> dict:
    if not MEMORY_PATH.exists():
        return _default_memory()
    try:
        return json.loads(MEMORY_PATH.read_text(encoding="utf-8"))
    except Exception:
        return _default_memory()


def _save(data: dict) -> None:
    MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    MEMORY_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
def _append_bounded(items: list[str], value: str, limit: int = 8) -> list[str]:
    cleaned = _clip_text(value, limit=160)
    if not cleaned:
        return items[-limit:]
    kept = [item for item in items if item != cleaned]
    kept.append(cleaned)
    return kept[-limit:]


def _embedding_text(text: str, result: str = "", context: str = "") -> str:
    parts = [
        " ".join(str(text or "").split()).strip(),
        " ".join(str(result or "").split()).strip(),
        " ".join(str(context or "").split()).strip(),
    ]
    combined = " ".join(part for part in parts if part).strip()
    return combined[:1600]


def _embed_text(text: str) -> list[float]:
    cleaned = " ".join(str(text or "").split()).strip()
    if not cleaned:
        return []
    try:
        response = requests.post(
            f"{OLLAMA_LOCAL_URL.rstrip('/')}/api/embeddings",
            json={"model": EMBED_MODEL, "prompt": cleaned[:1600]},
            timeout=8,
        )
        response.raise_for_status()
        embedding = response.json().get("embedding", [])
        if isinstance(embedding, list):
            return [float(value) for value in embedding]
    except Exception:
        return []
    return []


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(float(x) * float(y) for x, y in zip(a, b))
    norm_a = math.sqrt(sum(float(x) ** 2 for x in a))
    norm_b = math.sqrt(sum(float(y) ** 2 for y in b))
    if not norm_a or not norm_b:
        return 0.0
    return dot / (norm_a * norm_b)


def prepare_session_entry(entry: dict) -> dict:
    prepared = dict(entry or {})
    if isinstance(prepared.get("embedding"), list) and prepared.get("embedding"):
        return prepared
    embedding_text = _embedding_text(
        prepared.get("context", "") or prepared.get("context_preview", "") or prepared.get("text", ""),
        prepared.get("speech", "") or prepared.get("result", ""),
        json.dumps(prepared.get("actions", [])[:2]) if isinstance(prepared.get("actions"), list) else "",
    )
    embedding = _embed_text(embedding_text)
    if embedding:
        prepared["embedding"] = embedding
    return prepared


def load_all_sessions(limit_days: int = 7) -> list[dict]:
    entries: list[dict] = []
    if not SESSION_DIR.exists():
        return entries
    for session_file in sorted(SESSION_DIR.glob("*.jsonl"), reverse=True)[:limit_days]:
        for line in session_file.read_text(errors="ignore").splitlines():
            if not line.strip():
                continue
            try:
                data = json.loads(line)
            except Exception:
                continue
            if isinstance(data, dict):
                entries.append(data)
    return entries


def load_recent_sessions(n: int = 5) -> list[dict]:
    sessions = load_all_sessions(limit_days=14)
    sessions.sort(key=lambda item: str(item.get("timestamp", "")), reverse=True)
    return sessions[: max(1, n)]


def semantic_search(query: str, n: int = 5) -> list[dict]:
    query_text = " ".join(str(query or "").split()).strip()
    if not query_text:
        return []

    query_embedding = _embed_text(query_text)
    sessions = load_all_sessions(limit_days=14)
    if not query_embedding or not sessions:
        lowered = query_text.lower()
        return [
            entry
            for entry in sessions
            if lowered in str(entry.get("speech", "")).lower()
            or lowered in str(entry.get("context", entry.get("context_preview", ""))).lower()
        ][: max(1, n)]

    scored: list[tuple[float, dict]] = []
    for entry in sessions:
        embedding = entry.get("embedding")
        if not isinstance(embedding, list) or not embedding:
            continue
        score = cosine(query_embedding, embedding)
        if score > 0:
            enriched = dict(entry)
            enriched["score"] = round(score, 4)
            scored.append((score, enriched))

    if not scored:
        lowered = query_text.lower()
        return [
            entry
            for entry in sessions
            if lowered in str(entry.get("speech", "")).lower()
            or lowered in str(entry.get("context", entry.get("context_preview", ""))).lower()
        ][: max(1, n)]

    scored.sort(key=lambda item: item[0], reverse=True)
    return [entry for _score, entry in scored[: max(1, n)]]


def _looks_like_verification_command(cmd: str) -> bool:
    normalized = " ".join(str(cmd or "").lower().split())
    if not normalized:
        return False
    return any(
        token in normalized
        for token in (
            "pytest",
            "unittest",
            "nosetests",
            "cargo test",
            "go test",
            "npm test",
            "pnpm test",
            "yarn test",
            "vitest",
            "jest",
            "ruff",
            "mypy",
            "flake8",
            "eslint",
            "tsc",
            "build",
            "health",
            "--test",
        )
    )


def _project_catalog() -> list[dict]:
    try:
        from projects import load_projects

        return load_projects()
    except Exception:
        return []


def _get_project_by_name(name: str) -> dict | None:
    if not name:
        return None
    try:
        from projects import get_project

        return get_project(name)
    except Exception:
        return None


def _normalize_path(path: str) -> Path | None:
    if not path:
        return None
    try:
        return Path(os.path.expanduser(str(path))).resolve(strict=False)
    except Exception:
        return None


def _match_project_by_path(path: str, projects: list[dict] | None = None) -> dict | None:
    candidate = _normalize_path(path)
    if candidate is None:
        return None

    catalog = projects or _project_catalog()
    best: tuple[int, dict] | None = None
    for project in catalog:
        root = _normalize_path(project.get("path", ""))
        if root is None:
            continue
        try:
            if candidate == root or root in candidate.parents:
                score = len(str(root))
                if best is None or score > best[0]:
                    best = (score, project)
        except Exception:
            continue

    if best:
        return best[1]
    return _get_project_by_name(candidate.name)


def _projects_from_text(text: str, projects: list[dict] | None = None) -> list[dict]:
    query = str(text or "").strip()
    if not query:
        return []
    catalog = projects or _project_catalog()
    lowered = query.lower()
    matches: list[dict] = []
    seen: set[str] = set()
    for project in catalog:
        names = [project.get("name", "")]
        names.extend(project.get("aliases", []) or [])
        for candidate in names:
            token = str(candidate or "").strip().lower()
            if token and token in lowered:
                name = project.get("name", "")
                if name and name not in seen:
                    matches.append(project)
                    seen.add(name)
                break
    return matches


def _projects_for_action(action: dict, context_text: str = "") -> list[dict]:
    catalog = _project_catalog()
    matches: list[dict] = []
    seen: set[str] = set()

    def remember(project: dict | None) -> None:
        if not project:
            return
        name = project.get("name", "")
        if not name or name in seen:
            return
        matches.append(project)
        seen.add(name)

    action_type = action.get("type", "")
    if action_type == "open_project":
        remember(_get_project_by_name(action.get("name", "")))
    elif action_type in {"open_folder", "create_and_open", "open_editor", "write_file"}:
        remember(_match_project_by_path(action.get("path", ""), catalog))
    elif action_type == "create_file_in_editor":
        remember(_match_project_by_path(action.get("directory", ""), catalog))
    elif action_type == "run_command":
        remember(_match_project_by_path(action.get("cwd", ""), catalog))
    elif action_type == "run_agent":
        remember(_get_project_by_name(action.get("project", "") or action.get("repo", "")))

    if not matches and context_text:
        for project in _projects_from_text(context_text, catalog):
            remember(project)
    return matches


def _summarize_result(result: dict) -> str:
    status = str(result.get("status", "")).strip() or "ok"
    if status == "error":
        return _clip_text(result.get("error", ""), 140)
    return _clip_text(result.get("result", ""), 140)


def _detail_entry(
    *,
    timestamp: str,
    command_text: str,
    action: dict,
    result: dict,
    project_name: str,
) -> str:
    lines = [f"- request: {_clip_text(command_text, 120)}"]
    lines.append(f"- action: {action.get('type', 'unknown')} [{result.get('status', 'ok')}]")

    if action.get("type") == "run_command" and action.get("cmd"):
        lines.append(f"- command: {_clip_text(action.get('cmd', ''), 120)}")
    if action.get("path"):
        lines.append(f"- path: {_clip_text(action.get('path', ''), 120)}")
    if action.get("directory"):
        lines.append(f"- directory: {_clip_text(action.get('directory', ''), 120)}")
    if action.get("editor"):
        lines.append(f"- editor: {_clip_text(action.get('editor', ''), 60)}")

    summary = _summarize_result(result)
    if summary:
        label = "error" if result.get("status") == "error" else "result"
        lines.append(f"- {label}: {summary}")

    verification = ""
    if action.get("type") == "run_command" and _looks_like_verification_command(action.get("cmd", "")):
        verification = "failed" if result.get("status") == "error" else "passed"
        lines.append(f"- verification: {verification}")

    stamp = timestamp[:16].replace("T", " ")
    header = f"Execution update for {project_name} at {stamp}"
    return header + "\n" + "\n".join(lines)


def record_project_execution(
    command_text: str,
    speech: str,
    actions: list,
    results: list | None = None,
) -> dict[str, dict]:
    """
    Persist structured execution outcomes back into project memory.

    Returns a map of project name -> latest state snapshot for the projects
    touched by this interaction.
    """
    data = _load()
    project_states = data.get("project_state", {})
    now = _now_iso()
    results = results or []
    touched: dict[str, dict] = {}

    try:
        from memory.layered import save_project_detail
    except Exception:
        save_project_detail = None

    for index, action in enumerate(actions):
        result = results[index] if index < len(results) else {"status": "ok", "result": ""}
        for project in _projects_for_action(action, command_text):
            project_name = project.get("name", "")
            if not project_name:
                continue

            state = dict(project_states.get(project_name, {}))
            action_type = action.get("type", "")
            status = str(result.get("status", "ok")).strip() or "ok"
            summary = _summarize_result(result)

            state["last_request"] = _clip_text(command_text, 140)
            state["last_speech"] = _clip_text(speech, 160)
            state["last_action"] = action_type
            state["last_status"] = status
            state["last_result"] = summary
            state["last_updated"] = now

            if status == "ok":
                state["last_ok_at"] = now
                state["last_error"] = ""
            else:
                state["last_error"] = _clip_text(result.get("error", ""), 160)

            if action_type == "run_command":
                command = _clip_text(action.get("cmd", ""), 140)
                if command:
                    state["last_command"] = command
                cwd = action.get("cwd", "")
                if cwd:
                    state["last_command_cwd"] = cwd
                    state["last_workspace_path"] = cwd
                if _looks_like_verification_command(action.get("cmd", "")):
                    state["last_test_command"] = command
                    state["last_test_status"] = status
                    state["last_test_result"] = summary
                    if status == "ok":
                        state["last_verified_at"] = now
                        state["last_verification_error"] = ""
                    else:
                        state["last_verification_error"] = state.get("last_error", "")

            if action_type in {"open_project", "open_folder", "create_and_open", "open_editor", "write_file"}:
                path = action.get("path", "") or project.get("path", "")
                if path:
                    state["last_workspace_path"] = path
                if status == "ok":
                    state["last_opened"] = now

            if action_type == "create_file_in_editor":
                directory = action.get("directory", "")
                filename = action.get("filename", "")
                if directory:
                    state["last_workspace_path"] = directory
                if filename:
                    state["last_file"] = filename
                if status == "ok":
                    state["last_opened"] = now

            if action.get("editor"):
                state["last_editor"] = action.get("editor", "")
            if action.get("path") and Path(str(action.get("path"))).suffix:
                state["last_file"] = os.path.basename(str(action.get("path")))

            activity_line = f"{action_type} [{status}]"
            if summary:
                activity_line = f"{activity_line}: {summary}"
            state["recent_activity"] = _append_bounded(
                list(state.get("recent_activity", []) or []),
                activity_line,
                limit=8,
            )
            if status == "error" and state.get("last_error"):
                state["recent_failures"] = _append_bounded(
                    list(state.get("recent_failures", []) or []),
                    f"{action_type}: {state['last_error']}",
                    limit=5,
                )

            project_states[project_name] = state
            touched[project_name] = state

            if save_project_detail is not None:
                try:
                    save_project_detail(
                        project_name,
                        _detail_entry(
                            timestamp=now,
                            command_text=command_text,
                            action=action,
                            result=result,
                            project_name=project_name,
                        ),
                    )
                except Exception:
                    pass

    if touched:
        data["project_state"] = project_states
        _save(data)
    return touched


def record_session(
    context_summary: str,
    speech: str,
    actions: list,
    results: list | None = None,
) -> None:
    """Called after every Butler interaction to build memory."""
    data = _load()
    now = _now_iso()
    results = results or []
    data["session_count"] = data.get("session_count", 0) + 1
    data["last_session"] = now

    entry = {
        "timestamp": now,
        "context": context_summary[:200],
        "speech": speech[:200],
        "actions": actions,
        "results": results,
    }
    embedded_entry = prepare_session_entry(entry)
    history = data.get("command_history", [])
    history.append(embedded_entry)
    data["command_history"] = history[-50:]

    learned = data.get("learned_commands", {})
    for action, result in zip(actions, results):
        if action.get("type") != "run_command":
            continue
        cmd = action.get("cmd", "")
        cwd = action.get("cwd", "")
        key = f"{cwd}:{cmd}"
        if result.get("status") != "ok":
            learned.pop(key, None)
            continue
        if key not in learned:
            learned[key] = {
                "cmd": cmd,
                "cwd": cwd,
                "first_seen": now,
                "run_count": 0,
            }
        learned[key]["run_count"] = learned[key].get("run_count", 0) + 1
        learned[key]["last_run"] = now
    data["learned_commands"] = learned

    _save(data)


def update_project_state(project_name: str, state: dict) -> None:
    """Track what's happening in each project."""
    data = _load()
    projects = data.get("project_state", {})
    if project_name not in projects:
        projects[project_name] = {}
    projects[project_name].update(state)
    projects[project_name]["last_updated"] = _now_iso()
    data["project_state"] = projects
    _save(data)


def get_memory_context() -> str:
    """Returns formatted memory block for LLM — what Butler remembers."""
    data = _load()
    count = data.get("session_count", 0)
    history = data.get("command_history", [])
    project_states = data.get("project_state", {})
    learned = data.get("learned_commands", {})
    patterns = data.get("patterns", [])

    if not any([count, history, project_states, learned, patterns]):
        return ""

    lines = []
    last = data.get("last_session", "never") or "never"
    if last != "never":
        try:
            last = datetime.fromisoformat(last).strftime("%a %H:%M")
        except Exception:
            pass
    lines.append(f"Sessions so far: {count} | Last active: {last}")

    if history:
        recent = history[-3:]
        lines.append("Recent Butler moves:")
        for item in recent:
            stamp = item.get("timestamp", "")[:16]
            actions = item.get("actions", [])
            if actions:
                summary = ", ".join(
                    action.get("type", "unknown") for action in actions[:3]
                )
                lines.append(f"  [{stamp}] actions: {summary}")
            else:
                speech = item.get("speech", "")[:80]
                lines.append(f"  [{stamp}] said: {speech}")

    if project_states:
        lines.append("Project memory:")
        for name, state in project_states.items():
            parts = []
            if state.get("last_action"):
                parts.append(f"{state['last_action']} [{state.get('last_status', 'ok')}]")
            if state.get("last_test_command"):
                parts.append(f"verify {state.get('last_test_status', '?')}")
            if state.get("last_file"):
                parts.append(state["last_file"])
            elif state.get("last_workspace_path"):
                parts.append(state["last_workspace_path"])
            elif state.get("notes"):
                parts.append(state["notes"])
            if state.get("last_error"):
                parts.append(_clip_text(state["last_error"], 60))
            detail = " | ".join(part for part in parts if part)
            if detail:
                lines.append(f"  {name}: {detail}")

    if learned:
        top = sorted(
            learned.values(),
            key=lambda item: item.get("run_count", 0),
            reverse=True,
        )[:3]
        if top:
            lines.append("Commands Butler knows work:")
            for command in top:
                lines.append(
                    f"  '{command['cmd']}' in {command.get('cwd', '~')} "
                    f"(used {command['run_count']}x)"
                )

    if patterns:
        lines.append("Learned patterns:")
        for pattern in patterns[-5:]:
            lines.append(f"  - {pattern}")

    return "[BUTLER'S MEMORY]\n" + "\n".join(lines) if lines else ""


def add_pattern(pattern: str) -> None:
    """Store a learned behavior pattern."""
    data = _load()
    patterns = data.get("patterns", [])
    if pattern not in patterns:
        patterns.append(pattern)
    data["patterns"] = patterns[-20:]
    _save(data)


def get_last_session_summary() -> str:
    """3-line max summary of last real command (skips startup briefings)."""
    data = _load()
    history = data.get("command_history", [])
    if not history:
        return "No previous session."

    # Skip startup briefing entries — they echo back and cause repetition
    last = None
    for entry in reversed(history):
        if entry.get("context", "").startswith("startup briefing"):
            continue
        last = entry
        break
    if last is None:
        return "No previous session."
    try:
        ts = datetime.fromisoformat(last["timestamp"]).strftime("%a %H:%M")
    except Exception:
        ts = "recently"

    actions = last.get("actions", [])
    results = last.get("results", []) or []
    request = _clip_text(last.get("context", ""), 70)
    action_parts = []
    for action in actions[:2]:
        action_type = action.get("type", "")
        if action_type == "open_app":
            action_parts.append(f"opened {action.get('app')}")
        elif action_type == "open_folder":
            action_parts.append(f"opened {Path(action.get('path', '')).name}")
        elif action_type == "run_command":
            action_parts.append(f"ran {action.get('cmd', '')[:25]}")

    lines = [f"Last active: {ts}"]
    if request:
        lines.append(f'Request: "{request}"')
    if action_parts:
        lines.append(f"Did: {', '.join(action_parts)}")
    else:
        for result in results[:1]:
            summary = _summarize_result(result)
            if summary:
                lines.append(f"Result: {summary}")
                break
    return "\n".join(lines[:3])


if __name__ == "__main__":
    print(get_memory_context() or "No memory yet — first session")
