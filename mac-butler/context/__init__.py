# context/ — Gathers information about the user's current work environment.
# Modules return structured data. This __init__ assembles it into
# a clean, labeled context block for the LLM.

"""
Context engine for Mac Butler.

The key function is build_structured_context() which:
1. Calls all context modules for structured data
2. Determines context priority (active coding vs idle)
3. Builds a clean labeled block for the LLM
"""

import threading
import time
from datetime import datetime
from .git_context import get_git_context, format_git_context
from .vscode_context import get_vscode_context, format_vscode_context
from .app_context import get_app_context
from .mac_activity import get_state_for_context
from .obsidian_context import get_obsidian_context
from .vps_context import get_vps_context
from .mcp_context import get_mcp_context
from memory.layered import get_memory_index
from projects import get_projects_for_prompt
from tasks.task_store import get_tasks_for_prompt, sync_from_todo_md

__all__ = [
    "get_git_context",
    "get_vscode_context",
    "get_app_context",
    "get_state_for_context",
    "get_obsidian_context",
    "get_vps_context",
    "get_mcp_context",
    "build_structured_context",
]

_TASK_CACHE_LOCK = threading.Lock()
_TASK_CACHE_TEXT = ""
_TASK_CACHE_UPDATED_AT = 0.0
_TASK_SYNC_THREAD: threading.Thread | None = None
_TASK_SYNC_INTERVAL_SECONDS = 60

def _compress(raw: str, limit: int = 500) -> str:
    """Clean context before sending to LLM. Remove noise, keep signal."""
    lines = []
    for line in raw.split("\n"):
        line = line.strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            lines.append(line)
            continue
        words = line.split()
        if words and len(words[0]) == 7 and all(
            c in "0123456789abcdef" for c in words[0].lower()
        ):
            msg = " ".join(words[1:])[:55]
            lines.append(f"  commit: {msg}")
            continue
        lines.append(line[:75] + "..." if len(line) > 75 else line)

    result = "\n".join(lines)
    return result[:limit] + "..." if len(result) > limit else result


def _get_time_context() -> dict:
    """Get time-of-day context for personality."""
    now = datetime.now()
    hour = now.hour

    if 5 <= hour < 12:
        period = "morning"
        greeting = "Good morning"
    elif 12 <= hour < 17:
        period = "afternoon"
        greeting = "Good afternoon"
    elif 17 <= hour < 21:
        period = "evening"
        greeting = "Good evening"
    else:
        period = "late_night"
        greeting = "Still working late?"

    return {
        "hour": hour,
        "period": period,
        "greeting": greeting,
        "time_string": now.strftime("%I:%M %p"),
    }


def _refresh_task_cache() -> None:
    global _TASK_CACHE_TEXT, _TASK_CACHE_UPDATED_AT
    try:
        sync_from_todo_md()
    except Exception:
        pass
    text = get_tasks_for_prompt()
    with _TASK_CACHE_LOCK:
        _TASK_CACHE_TEXT = text
        _TASK_CACHE_UPDATED_AT = time.monotonic()


def _task_sync_loop() -> None:
    while True:
        time.sleep(_TASK_SYNC_INTERVAL_SECONDS)
        _refresh_task_cache()


def _ensure_task_cache_thread() -> None:
    global _TASK_SYNC_THREAD
    with _TASK_CACHE_LOCK:
        if _TASK_SYNC_THREAD is not None and _TASK_SYNC_THREAD.is_alive():
            return
        _TASK_SYNC_THREAD = threading.Thread(
            target=_task_sync_loop,
            daemon=True,
            name="burry-task-sync",
        )
        _TASK_SYNC_THREAD.start()


def _cached_tasks_for_prompt() -> str:
    _ensure_task_cache_thread()
    with _TASK_CACHE_LOCK:
        cached = _TASK_CACHE_TEXT
    if cached:
        return cached
    return get_tasks_for_prompt()


def build_structured_context() -> dict:
    """
    Master context builder. Gathers all sources and assembles a
    structured context dict + formatted string for the LLM.

    Returns:
        {
            "raw": { "git": {...}, "editor": {...}, "tasks": {...}, "time": {...} },
            "formatted": "the clean labeled text block for LLM",
            "priority": "coding" | "tasks" | "mixed",
        }
    """
    # Gather all raw data
    git_data = get_git_context()
    editor_data = get_vscode_context()
    app_data = get_app_context()
    tasks_text = _cached_tasks_for_prompt()
    projects_text = get_projects_for_prompt()
    obsidian_text = get_obsidian_context()
    vps_text = get_vps_context()
    mcp_text = get_mcp_context()
    mac_state = get_state_for_context()
    memory_index = get_memory_index()
    time_data = _get_time_context()

    # Determine context priority
    has_code_activity = git_data["has_activity"] or editor_data["has_data"]
    has_tasks = bool(tasks_text)

    if has_code_activity and not has_tasks:
        priority = "coding"
    elif has_tasks and not has_code_activity:
        priority = "tasks"
    else:
        priority = "mixed"

    # Build the formatted context block
    sections = []

    # --- FOCUS section (inferred from most recent activity) ---
    focus_parts = []
    if git_data["has_activity"] and git_data["repos"]:
        top_repo = git_data["repos"][0]
        focus_parts.append(f"project: {top_repo['name']}")
        if top_repo["commits"]:
            focus_parts.append(f"last work: {top_repo['commits'][0]}")
    if editor_data["has_data"] and editor_data["workspaces"]:
        focus_parts.append(f"open in editor: {', '.join(editor_data['workspaces'][:3])}")

    if focus_parts:
        sections.append("[FOCUS]\n" + "\n".join(f"  {p}" for p in focus_parts))

    sections.append(f"[TIME]\n  {time_data['period']} ({time_data['time_string']})")

    if tasks_text:
        sections.append(_compress(tasks_text, 180))

    if projects_text:
        sections.append(_compress(projects_text, 300))

    if mac_state:
        sections.append(_compress(mac_state, 200))

    if memory_index:
        sections.append(_compress(memory_index, 140))

    if editor_data["has_data"]:
        editor_lines = []
        if editor_data.get("app_name"):
            editor_lines.append(f"  editor: {editor_data['app_name']}")
        if editor_data.get("workspace_paths"):
            editor_lines.append(
                "  last workspaces: "
                + ", ".join(editor_data["workspaces"][:3])
            )
        if editor_lines:
            sections.append("[EDITOR]\n" + "\n".join(editor_lines))

    # --- RECENT WORK section ---
    if git_data["has_activity"]:
        work_lines = []
        for repo in git_data["repos"][:3]:
            commits_str = ", ".join(repo["commits"][:3])
            work_lines.append(f"  {repo['name']}: {commits_str}")
        sections.append("[RECENT WORK]\n" + "\n".join(work_lines))

    if editor_data["has_data"] and editor_data["recent_files"]:
        sections.append("[RECENT FILES]\n  " + ", ".join(editor_data["recent_files"][:5]))

    if obsidian_text:
        sections.append("[OBSIDIAN]\n" + obsidian_text[:350])

    if vps_text:
        sections.append("[VPS]\n" + vps_text[:160])

    if mcp_text:
        sections.append("[MCP]\n" + mcp_text[:160])

    formatted = _compress("\n\n".join(sections) if sections else "(No context)", limit=650)

    return {
        "raw": {
            "git": git_data,
            "editor": editor_data,
            "app": app_data,
            "tasks": tasks_text,
            "projects": projects_text,
            "obsidian": obsidian_text,
            "vps": vps_text,
            "mcp": mcp_text,
            "mac_activity": mac_state,
            "time": time_data,
        },
        "formatted": formatted,
        "priority": priority,
    }


if __name__ == "__main__":
    print("=== Structured Context Test ===\n")
    ctx = build_structured_context()
    print(f"Priority: {ctx['priority']}\n")
    print("--- Formatted Context ---")
    print(ctx["formatted"])
    print("--- End ---")
