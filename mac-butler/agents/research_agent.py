#!/usr/bin/env python3
"""Research agent wrappers with an AgentScope DeepResearchAgent fallback path."""
from __future__ import annotations

import asyncio

from agentscope.memory import InMemoryMemory
from agentscope.message import Msg
from agentscope.plan import PlanNotebook

from brain.agentscope_backbone import build_agentscope_toolkit, create_react_agent
from runtime.telemetry import note_agent_result

_RESEARCH_SYSTEM_PROMPT = """You are Burry's research agent.

Research questions using real search and browsing tools. For substantial
queries, create a short plan first, gather evidence from multiple sources,
cross-check important claims, and then produce a concise synthesis.

Prefer search and browsing tools over speculation. If evidence is weak, say
that clearly. Keep the final answer compact and useful for spoken delivery."""

_RESEARCH_TOOLS = {
    "browse_and_act",
    "browse_web",
    "web_search_summarize",
    "search_knowledge_base",
    "recall_memory",
}


def _research_toolkit():
    return build_agentscope_toolkit(
        include_tools=_RESEARCH_TOOLS,
        exclude_tools={"deep_research"},
    )


async def _run_research_custom(question: str, model: str) -> str:
    researcher = create_react_agent(
        name="BurryResearch",
        system_prompt=_RESEARCH_SYSTEM_PROMPT,
        model_name=model,
        intent_name="deep_research",
        toolkit=_research_toolkit(),
        memory=InMemoryMemory(),
        plan_notebook=PlanNotebook(max_subtasks=4),
        max_iters=7,
        stream=False,
    )

    note_agent_result("research", "start", f"Researching: {question[:80]}")
    reply = await researcher(
        Msg(
            "user",
            question.strip(),
            "user",
        ),
    )
    answer = " ".join(str(reply.get_text_content() or "").split()).strip()
    answer = answer or "I couldn't find enough reliable information on that."
    note_agent_result("research", "ok", answer[:120])
    return answer


def _deep_research_custom(question: str, model: str = "gemma4:e4b") -> str:
    import concurrent.futures

    try:
        asyncio.get_running_loop()
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(asyncio.run, _run_research_custom(question, model))
            return future.result(timeout=120)
    except RuntimeError:
        return asyncio.run(_run_research_custom(question, model))


def deep_research(question: str, model: str = "gemma4:e4b") -> str:
    """Use AgentScope DeepResearchAgent if available, custom fallback otherwise."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        pass
    try:
        from agentscope.agents import DeepResearchAgent
        from agentscope.formatter import OllamaChatFormatter
        from agentscope.message import Msg

        from brain.agentscope_backbone import _get_persistent_loop, ensure_agentscope_initialized
        from brain.agentscope_ollama_model import BurryOllamaChatModel

        ensure_agentscope_initialized()
        agent = DeepResearchAgent(
            name="burry-researcher",
            model=BurryOllamaChatModel(
                model_name=model,
                stream=False,
                options={"num_ctx": 8192},
            ),
            formatter=OllamaChatFormatter(max_tokens=1024),
        )
        loop = _get_persistent_loop()
        future = asyncio.run_coroutine_threadsafe(
            agent(Msg("user", question, "user")),
            loop,
        )
        result = future.result(timeout=90)
        return result.get_text_content() if hasattr(result, "get_text_content") else str(result)
    except (ImportError, Exception):
        pass
    return _deep_research_custom(question, model)
