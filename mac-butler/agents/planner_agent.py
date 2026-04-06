#!/usr/bin/env python3
"""Meta Planner Agent — inspired by AgentScope's Meta Planner.
Decomposes complex tasks into steps and executes them sequentially.
"""
from __future__ import annotations

import json
import re

from brain.ollama_client import _call
from runtime.telemetry import note_agent_result


def plan_and_execute(task: str, ctx: dict, model: str = "gemma4:e4b") -> str:
    """Break a complex task into steps and execute them.

    Example: 'Set up my morning: open mac-butler in Cursor, play focus music,
    check VPS status, and remind me of standup in 30 mins'
    → Plan: [open_project, spotify_control, ssh_vps, set_reminder]
    → Execute each step in order → Report results
    """
    from brain.toolkit import get_toolkit
    import brain.tools_registry  # noqa

    toolkit = get_toolkit()
    available_tools = [t["function"]["name"] for t in toolkit.get_tools()]

    # Generate plan
    plan_prompt = f"""You are a task planner. Break this task into 2-5 steps using ONLY these available tools:
{', '.join(available_tools)}

Task: {task}

Return a JSON array of steps. Each step: {{"tool": "tool_name", "args": {{"param": "value"}}, "reason": "why"}}
Return ONLY the JSON array, nothing else:"""

    raw_plan = _call(plan_prompt, model, max_tokens=400, temperature=0.1)

    try:
        raw_plan = re.sub(r"```json?\s*|\s*```", "", raw_plan or "").strip()
        steps = json.loads(raw_plan)
    except Exception:
        return "I couldn't plan that task. Try breaking it into simpler steps."

    # Execute each step
    results = []
    note_agent_result("planner", "start", f"Executing {len(steps)}-step plan for: {task[:50]}")

    for i, step in enumerate(steps):
        tool_name = step.get("tool", "")
        args = step.get("args", {})

        try:
            result = toolkit.call(tool_name, **args)
            results.append(f"Step {i+1} ({tool_name}): {str(result)[:100]}")
            note_agent_result("planner_step", "ok", f"{tool_name}: {str(result)[:50]}")
        except Exception as exc:
            results.append(f"Step {i+1} ({tool_name}): failed — {str(exc)[:50]}")

    # Summarize
    summary_prompt = f"""Task completed: {task}
Results: {chr(10).join(results)}

Give a brief 1-2 sentence summary of what was accomplished:"""

    summary = _call(summary_prompt, "gemma4:e4b", max_tokens=80, temperature=0.1)
    return summary or f"Completed {len(results)} steps."
