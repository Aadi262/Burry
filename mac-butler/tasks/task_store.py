#!/usr/bin/env python3
"""
tasks/task_store.py
Butler's persistent task list — inspired by Claude Code's TodoWrite pattern.
Qwen reads this, updates it, Butler writes it back after every session.
This is how Butler remembers what you're building across days.
"""

import json
from datetime import datetime
from pathlib import Path

TASKS_PATH = Path(__file__).parent / "tasks.json"


def _shorten(text: str, limit: int = 32) -> str:
    text = " ".join(str(text).split())
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _load() -> list:
    if not TASKS_PATH.exists():
        return []
    try:
        return json.loads(TASKS_PATH.read_text())
    except Exception:
        return []


def _save(tasks: list) -> None:
    TASKS_PATH.parent.mkdir(parents=True, exist_ok=True)
    TASKS_PATH.write_text(json.dumps(tasks, indent=2))


def get_tasks_for_prompt() -> str:
    """Compact task list for LLM context — always loaded."""
    tasks = [task for task in _load() if task.get("status") != "done"]
    if not tasks:
        return ""

    scoped = [task for task in tasks if task.get("project")]
    candidates = scoped or tasks

    selected = []
    for project in ("mac-butler", "email-infra"):
        project_tasks = [
            task for task in candidates
            if task.get("project", "").lower() == project
        ]
        selected.extend(project_tasks[:2])

    for task in candidates:
        if task not in selected:
            selected.append(task)

    lines = ["[TASK LIST]"]
    for task in selected:
        status_icon = {
            "todo": "○",
            "in_progress": "◉",
            "done": "✓",
            "blocked": "✗",
        }.get(task.get("status", "todo"), "○")

        priority = " [HIGH]" if task.get("priority") == "high" else ""
        project = f" ({task['project']})" if task.get("project") else ""
        title = _shorten(task.get("title", "Untitled task"))
        line = f"  {status_icon} {title}{project}{priority}"
        if len("\n".join(lines + [line])) > 470:
            break
        lines.append(line)

    return "\n".join(lines)


def add_task(title: str, project: str = "", priority: str = "normal") -> dict:
    tasks = _load()
    task = {
        "id": f"t{len(tasks)+1}",
        "title": title,
        "project": project,
        "priority": priority,
        "status": "todo",
        "created": datetime.now().isoformat(),
    }
    tasks.append(task)
    _save(tasks)
    return task


def update_task_status(task_id: str, status: str) -> bool:
    tasks = _load()
    for task in tasks:
        if task["id"] == task_id or task["title"].lower() == task_id.lower():
            task["status"] = status
            task["updated"] = datetime.now().isoformat()
            _save(tasks)
            return True
    return False


def sync_from_todo_md(todo_path: str = "~/Developer/TODO.md") -> int:
    """
    Read TODO.md and sync tasks into task store.
    Called on startup to keep task list current.
    """
    path = Path(todo_path).expanduser()
    if not path.exists():
        return 0

    existing_tasks = _load()
    existing_titles = {task["title"].lower() for task in existing_tasks}
    added = 0

    content = path.read_text(errors="ignore")
    for line in content.split("\n"):
        line = line.strip()
        if line.startswith("- [ ]"):
            title = line[5:].strip()
            if title and title.lower() not in existing_titles:
                add_task(title, priority="normal")
                existing_titles.add(title.lower())
                added += 1
        elif line.startswith("- [x]") or line.startswith("- [X]"):
            title = line[5:].strip()
            if title and title.lower() not in existing_titles:
                task = add_task(title)
                update_task_status(task["id"], "done")
                existing_titles.add(title.lower())

    return added


def get_active_tasks(project: str = None) -> list:
    tasks = _load()
    active = [task for task in tasks if task.get("status") != "done"]
    if project:
        active = [
            task
            for task in active
            if task.get("project", "").lower() == project.lower()
        ]
    return sorted(active, key=lambda item: item.get("priority") == "high", reverse=True)


if __name__ == "__main__":
    if not _load():
        add_task("Wire two-stage LLM into butler", "mac-butler", "high")
        add_task("Add task system (this file)", "mac-butler", "high")
        add_task("Add observe loop (feed results back)", "mac-butler", "high")
        add_task("Implement layered memory (MEMORY.md pattern)", "mac-butler", "normal")
        add_task("Design trust score formula", "email-infra", "high")
        add_task("Build reputation graph schema", "email-infra", "normal")
        add_task("Research warmup simulation engine", "email-infra", "normal")
        print("Seeded initial tasks")

    print(get_tasks_for_prompt())
