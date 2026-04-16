#!/usr/bin/env python3
"""AgentScope-backed meta planner for multi-step execution."""
from __future__ import annotations

import asyncio

from agentscope.memory import InMemoryMemory
from agentscope.message import Msg
from agentscope.plan import PlanNotebook

from butler_config import BUTLER_MODELS
from brain.agentscope_backbone import build_agentscope_toolkit, create_react_agent
from runtime.telemetry import note_agent_result

PLANNER_MODEL = BUTLER_MODELS.get("planning", "")

_PLANNER_SYSTEM_PROMPT = """You are Burry's planning agent.

Use AgentScope's planning tools for requests that require multiple dependent
actions. Create a concrete plan when needed, execute the steps with real tools,
update subtask state as you progress, and finish the plan when the task is
complete. Do not narrate imagined work. Use tools for actual actions.

Return a concise operator summary of what you completed, what failed, and what
still needs follow-up."""


def _planner_toolkit():
    return build_agentscope_toolkit(exclude_tools={"plan_and_execute"})


async def _run_plan(task: str, ctx: dict, model: str) -> str:
    planner = create_react_agent(
        name="BurryPlanner",
        system_prompt=_PLANNER_SYSTEM_PROMPT,
        model_name=model,
        intent_name="plan_and_execute",
        toolkit=_planner_toolkit(),
        memory=InMemoryMemory(),
        plan_notebook=PlanNotebook(max_subtasks=8),
        max_iters=8,
        stream=False,
    )

    focus_project = str(ctx.get("focus_project", "") or "")
    workspace = str(ctx.get("workspace", "") or "")
    context_bits = []
    if focus_project:
        context_bits.append(f"Focus project: {focus_project}")
    if workspace:
        context_bits.append(f"Workspace: {workspace}")
    if ctx.get("formatted"):
        context_bits.append(f"Context:\n{str(ctx['formatted'])[:2500]}")

    prompt = task.strip()
    if context_bits:
        prompt = f"{task.strip()}\n\n" + "\n\n".join(context_bits)

    note_agent_result("planner", "start", f"Planning task: {task[:80]}")
    reply = await planner(
        Msg(
            "user",
            prompt,
            "user",
            metadata={
                "focus_project": focus_project,
                "workspace": workspace,
            },
        ),
    )
    speech = " ".join(str(reply.get_text_content() or "").split()).strip()
    speech = speech or "I couldn't complete that plan."
    note_agent_result("planner", "ok", speech[:120])
    return speech


def plan_and_execute(task: str, ctx: dict, model: str = PLANNER_MODEL) -> str:
    """Plan and execute a complex task with AgentScope orchestration."""
    import concurrent.futures

    try:
        asyncio.get_running_loop()
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(asyncio.run, _run_plan(task, ctx or {}, model))
            return future.result(timeout=120)
    except RuntimeError:
        return asyncio.run(_run_plan(task, ctx or {}, model))
