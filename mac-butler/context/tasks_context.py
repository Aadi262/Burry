#!/usr/bin/env python3
"""
tasks_context.py — Reads ~/Developer/TODO.md if it exists.

Returns structured task data with priority detection.
Parses markdown checkboxes to separate done vs pending tasks.
"""

import re
from pathlib import Path

from butler_config import DEVELOPER_PATH


# Path to the user's personal TODO file
TODO_PATH = Path(DEVELOPER_PATH).expanduser() / "TODO.md"


def get_tasks_context() -> dict:
    """
    Read ~/Developer/TODO.md and parse tasks into structured data.

    Returns:
        {
            "tasks": ["Review pull requests", "Deploy staging", ...],
            "completed": ["Set up monitoring", ...],
            "priority_section": ["Review pull requests", "Deploy staging", ...],
            "has_tasks": True/False
        }
    """
    result = {"tasks": [], "completed": [], "priority_section": [], "has_tasks": False}

    if not TODO_PATH.exists():
        return result

    try:
        with open(TODO_PATH, "r", encoding="utf-8") as f:
            content = f.read()
    except IOError:
        return result

    # Parse markdown checkboxes
    in_priority = False
    for line in content.splitlines()[:30]:  # Read up to 30 lines
        stripped = line.strip()

        # Detect priority section header
        if re.match(r"^#{1,3}\s*(priority|urgent|today|now)", stripped, re.IGNORECASE):
            in_priority = True
        elif re.match(r"^#{1,3}\s+", stripped):
            in_priority = False  # New section, no longer priority

        # Parse checkbox items
        unchecked = re.match(r"^-\s*\[\s*\]\s*(.+)", stripped)
        checked = re.match(r"^-\s*\[x\]\s*(.+)", stripped, re.IGNORECASE)

        if checked:
            result["completed"].append(checked.group(1).strip())
        elif unchecked:
            task = unchecked.group(1).strip()
            result["tasks"].append(task)
            if in_priority:
                result["priority_section"].append(task)

    result["has_tasks"] = bool(result["tasks"])
    return result


def format_tasks_context(data: dict) -> str:
    """Format task data as a human-readable string."""
    if not data["has_tasks"]:
        return "(No pending tasks found.)"

    lines = []
    if data["priority_section"]:
        lines.append("  Priority: " + ", ".join(data["priority_section"][:3]))

    remaining = [t for t in data["tasks"] if t not in data["priority_section"]]
    if remaining:
        lines.append("  Other: " + ", ".join(remaining[:3]))

    return "\n".join(lines)


if __name__ == "__main__":
    print("=== Tasks Context Test ===\n")
    data = get_tasks_context()
    print(f"Raw data: {data}\n")
    print(f"Formatted:\n{format_tasks_context(data)}")
