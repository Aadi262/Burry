#!/usr/bin/env python3
"""
memory/layered.py
Three-layer memory inspired directly by Claude Code's architecture:
  Layer 1 — MEMORY.md: tiny index, always loaded (~150 chars per entry)
  Layer 2 — project detail files: loaded on demand
  Layer 3 — session logs: never loaded wholesale, search only
"""

import json
from datetime import datetime
from pathlib import Path

from memory.store import prepare_session_entry, semantic_search

MEMORY_DIR = Path(__file__).parent / "layers"
MEMORY_INDEX = MEMORY_DIR / "MEMORY.md"
PROJECTS_DIR = MEMORY_DIR / "projects"
SESSIONS_DIR = MEMORY_DIR / "sessions"


def _clip_line(text: str, limit: int = 88) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _ensure_dirs():
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)


def get_memory_index() -> str:
    """Layer 1 — always loaded. Tiny pointers only."""
    _ensure_dirs()
    if not MEMORY_INDEX.exists():
        _init_memory_index()
    text = MEMORY_INDEX.read_text(errors="ignore")
    if len(text) <= 600:
        return text

    lines = [line for line in text.splitlines() if line.strip()]
    head = [_clip_line(line) for line in lines[:5]]
    tail = [_clip_line(line) for line in lines[-4:]]

    compact_lines = head + ["- ..."] + tail
    compact = "\n".join(compact_lines)
    return compact[:700]


def _init_memory_index():
    """Seed memory index with what we know about Aditya."""
    content = """# Butler Memory Index
## Projects
- mac-butler: local operator agent, ~/Burry/mac-butler, active
- email-infra: cold email system like Instantly, architecture phase

## Patterns
- Works late nights regularly
- Uses VS Code and Cursor depending on the current project
- Uses Obsidian for notes and ideas
- Builds systems thinking, not just features

## Last Known
- Building: two-stage LLM, task system, observe loop
"""
    MEMORY_INDEX.write_text(content)


_MAX_INDEX_LINES = 25


def append_to_index(entry: str) -> None:
    """Add a short pointer to Layer 1. Keep recent entries bounded."""
    _ensure_dirs()
    if not MEMORY_INDEX.exists():
        _init_memory_index()
    short = entry[:140]
    lines = MEMORY_INDEX.read_text(errors="ignore").splitlines()
    static_block = lines[:8]
    dynamic_block = [line for line in lines[8:] if line.strip().startswith("-")]
    if f"- {short}" in dynamic_block:
        return
    dynamic_block = dynamic_block[-(_MAX_INDEX_LINES - 1):] + [f"- {short}"]
    MEMORY_INDEX.write_text("\n".join(static_block + dynamic_block) + "\n")


def save_project_detail(project: str, content: str) -> None:
    """Layer 2 — detailed project notes, loaded on demand."""
    _ensure_dirs()
    path = PROJECTS_DIR / f"{project}.md"
    mode = "a" if path.exists() else "w"
    with open(path, mode) as handle:
        handle.write(f"\n## {datetime.now().strftime('%Y-%m-%d %H:%M')}\n{content}\n")


def get_project_detail(project: str) -> str:
    """Load a project's detail file on demand."""
    path = PROJECTS_DIR / f"{project}.md"
    if not path.exists():
        return ""
    return path.read_text(errors="ignore")[-1000:]


def save_session(session_data: dict) -> None:
    """Layer 3 — session archive. Never loaded wholesale."""
    _ensure_dirs()
    date = datetime.now().strftime("%Y-%m-%d")
    path = SESSIONS_DIR / f"{date}.jsonl"
    prepared = prepare_session_entry(session_data)
    with open(path, "a") as handle:
        handle.write(json.dumps(prepared) + "\n")


def search_sessions(query: str, max_results: int = 3) -> list:
    """Search session logs semantically, with keyword fallback handled in store."""
    return semantic_search(query, n=max_results)


if __name__ == "__main__":
    print("=== Layer 1: Memory Index ===")
    print(get_memory_index())
