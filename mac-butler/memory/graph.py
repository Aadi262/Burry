#!/usr/bin/env python3
"""Cross-project dependency graph helpers."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

GRAPH_PATH = Path(__file__).resolve().parent / "layers" / "graph.json"
EDGE_TYPES = {"depends_on", "shares_resource", "blocked_by"}


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _clean(text: str, limit: int = 120) -> str:
    cleaned = " ".join(str(text or "").split()).strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 3].rstrip() + "..."


def _default_graph() -> dict:
    return {"updated_at": "", "edges": []}


def _normalize_edge(edge: dict) -> dict | None:
    source = _clean(edge.get("from", ""), limit=80)
    target = _clean(edge.get("to", ""), limit=80)
    edge_type = str(edge.get("type", "")).strip()
    if not source or not target or edge_type not in EDGE_TYPES:
        return None
    return {
        "from": source,
        "to": target,
        "type": edge_type,
        "note": _clean(edge.get("note", ""), limit=180),
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
