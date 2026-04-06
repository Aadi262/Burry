#!/usr/bin/env python3
"""Cross-project dependency graph helpers."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from utils import _clip_text, _normalize, _now_iso

GRAPH_PATH = Path(__file__).resolve().parent / "layers" / "graph.json"
EDGE_TYPES = {"depends_on", "shares_resource", "blocked_by"}


def _default_graph() -> dict:
    return {"updated_at": "", "edges": []}


def _normalize_edge(edge: dict) -> dict | None:
    source = _clip_text(edge.get("from", ""), limit=80)
    target = _clip_text(edge.get("to", ""), limit=80)
    edge_type = str(edge.get("type", "")).strip()
    if not source or not target or edge_type not in EDGE_TYPES:
        return None
    return {
        "from": source,
        "to": target,
        "type": edge_type,
        "note": _clip_text(edge.get("note", ""), limit=180),
    }


def read_graph() -> dict:
    if not GRAPH_PATH.exists():
        return _default_graph()
    try:
        data = json.loads(GRAPH_PATH.read_text(encoding="utf-8"))
    except Exception:
        return _default_graph()

    graph = _default_graph()
    graph["updated_at"] = str(data.get("updated_at", "") or "")
    edges = []
    for edge in list(data.get("edges") or []):
        if not isinstance(edge, dict):
            continue
        normalized = _normalize_edge(edge)
        if normalized:
            edges.append(normalized)
    graph["edges"] = edges
    return graph


def add_edge(source: str, target: str, edge_type: str, note: str = "") -> dict:
    graph = read_graph()
    normalized = _normalize_edge({"from": source, "to": target, "type": edge_type, "note": note})
    if normalized is None:
        raise ValueError(f"Unsupported graph edge: {edge_type}")

    edges = []
    replaced = False
    for edge in graph.get("edges", []):
        same_edge = (
            edge.get("from") == normalized["from"]
            and edge.get("to") == normalized["to"]
            and edge.get("type") == normalized["type"]
        )
        if same_edge:
            edges.append(normalized)
            replaced = True
        else:
            edges.append(edge)
    if not replaced:
        edges.append(normalized)

    graph["edges"] = edges
    graph["updated_at"] = _now_iso()
    GRAPH_PATH.parent.mkdir(parents=True, exist_ok=True)
    GRAPH_PATH.write_text(json.dumps(graph, indent=2), encoding="utf-8")
    return graph


def _project_catalog() -> list[dict]:
    try:
        from projects import load_projects

        return load_projects()
    except Exception:
        return []


def _project_aliases(project: dict) -> list[str]:
    names = [str(project.get("name", "")).strip()]
    names.extend(str(alias).strip() for alias in list(project.get("aliases") or []))
    return [name for name in names if name]


def _mentioned_projects(text: str, projects: list[dict]) -> list[str]:
    normalized_text = _normalize(text)
    matches: list[str] = []
    for project in projects:
        project_name = str(project.get("name", "")).strip()
        if not project_name:
            continue
        for alias in _project_aliases(project):
            if _normalize(alias) and _normalize(alias) in normalized_text:
                if project_name not in matches:
                    matches.append(project_name)
                break
    return matches


def _recent_session_window(minutes: int = 30) -> list[dict]:
    try:
        from memory.store import load_recent_sessions

        sessions = load_recent_sessions(24)
    except Exception:
        return []

    cutoff = datetime.now().timestamp() - (minutes * 60)
    window: list[dict] = []
    for session in sessions:
        stamp = str(session.get("timestamp", "")).strip()
        try:
            session_ts = datetime.fromisoformat(stamp).timestamp()
        except Exception:
            continue
        if session_ts >= cutoff:
            window.append(session)
    return window


def observe_project_relationships(
    *,
    text: str,
    speech: str = "",
    actions: list[dict] | None = None,
    touched_projects: list[str] | None = None,
) -> dict:
    projects = _project_catalog()
    if not projects:
        return read_graph()

    combined_parts = [text, speech]
    for action in list(actions or []):
        if isinstance(action, dict):
            combined_parts.append(str(action.get("name", "")))
            combined_parts.append(str(action.get("project", "")))
    for session in _recent_session_window():
        combined_parts.append(str(session.get("context", "")))
        combined_parts.append(str(session.get("context_preview", "")))
        combined_parts.append(str(session.get("speech", "")))
    combined_text = "\n".join(part for part in combined_parts if part)

    project_names = list(touched_projects or [])
    for name in _mentioned_projects(combined_text, projects):
        if name not in project_names:
            project_names.append(name)

    for index, source in enumerate(project_names):
        for target in project_names[index + 1:]:
            if source == target:
                continue
            add_edge(source, target, "shares_resource", "Seen together in recent session context.")

    for project in projects:
        source = str(project.get("name", "")).strip()
        if not source:
            continue
        for blocker in list(project.get("blockers") or []):
            blocker_text = str(blocker).strip()
            if not blocker_text:
                continue
            for target in _mentioned_projects(blocker_text, projects):
                if target and target != source:
                    add_edge(source, target, "blocked_by", blocker_text)

    return read_graph()
