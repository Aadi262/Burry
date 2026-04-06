#!/usr/bin/env python3
"""PlanNotebook — inspired by AgentScope's PlanNotebook.
Tracks multi-step plans across sessions. Burry remembers
what it was doing and picks up where it left off.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional

NOTEBOOK_PATH = Path(__file__).parent / "plan_notebook.json"


def _load() -> dict:
    try:
        return json.loads(NOTEBOOK_PATH.read_text())
    except Exception:
        return {"active_plans": [], "completed_plans": []}


def _save(data: dict) -> None:
    NOTEBOOK_PATH.write_text(json.dumps(data, indent=2))


def create_plan(title: str, steps: list[str]) -> str:
    """Create a new multi-step plan. Returns plan ID."""
    data = _load()
    plan = {
        "id": f"plan_{int(time.time())}",
        "title": title,
        "steps": [
            {"text": s, "done": False, "started_at": None, "completed_at": None}
            for s in steps
        ],
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "status": "active",
    }
    data["active_plans"].append(plan)
    _save(data)
    return plan["id"]


def get_current_plan() -> Optional[dict]:
    """Get the most recent active plan."""
    data = _load()
    active = [p for p in data["active_plans"] if p["status"] == "active"]
    return active[-1] if active else None


def advance_plan(plan_id: str) -> Optional[str]:
    """Mark current step done. Returns next step text, or None if plan complete."""
    data = _load()
    for plan in data["active_plans"]:
        if plan["id"] == plan_id:
            for step in plan["steps"]:
                if not step["done"]:
                    step["done"] = True
                    step["completed_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
                    break

            next_steps = [s for s in plan["steps"] if not s["done"]]
            if not next_steps:
                plan["status"] = "completed"
                data["completed_plans"].append(plan)
                data["active_plans"] = [p for p in data["active_plans"] if p["id"] != plan_id]
                _save(data)
                return None

            _save(data)
            return next_steps[0]["text"]
    return None


def get_plan_status() -> str:
    """Get readable status of current plan for HUD display."""
    plan = get_current_plan()
    if not plan:
        return "No active plan"
    done = sum(1 for s in plan["steps"] if s["done"])
    total = len(plan["steps"])
    next_step = next((s["text"] for s in plan["steps"] if not s["done"]), "All done")
    return f"{plan['title']}: {done}/{total} steps. Next: {next_step}"


def cancel_plan(plan_id: str) -> bool:
    """Cancel an active plan."""
    data = _load()
    before = len(data["active_plans"])
    data["active_plans"] = [p for p in data["active_plans"] if p["id"] != plan_id]
    if len(data["active_plans"]) < before:
        _save(data)
        return True
    return False
