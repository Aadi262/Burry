#!/usr/bin/env python3
"""Research agent wrappers with an AgentScope DeepResearchAgent fallback path."""
from __future__ import annotations

import asyncio
import re

from agentscope.memory import InMemoryMemory
from agentscope.message import Msg
from agentscope.plan import PlanNotebook

from agents.runner import run_agent
from butler_config import BUTLER_MODELS
from brain.agentscope_backbone import build_agentscope_toolkit, create_react_agent
from brain.query_analyzer import analyze_query
from runtime.telemetry import note_agent_result

RESEARCH_MODEL = BUTLER_MODELS.get("review", "")

_RESEARCH_SYSTEM_PROMPT = """You are Burry's research agent.

Research questions using real search and browsing tools. For substantial
queries, create a short plan first, gather evidence from multiple sources,
cross-check important claims, and then produce a concise synthesis.

Prefer search and browsing tools over speculation. If evidence is weak, say
that clearly. Keep the final answer compact and useful for spoken delivery."""

_RESEARCH_TOOLS = {
    "browse_and_act",
    "browse_web",
    "lookup_project_status",
    "read_page",
    "web_search_summarize",
    "search_knowledge_base",
    "recall_memory",
}


def _research_toolkit():
    return build_agentscope_toolkit(
        include_tools=_RESEARCH_TOOLS,
        exclude_tools={"deep_research"},
    )


def _research_topic_hint(question: str) -> str:
    cleaned = " ".join(str(question or "").split()).strip()
    if not cleaned:
        return ""
    topic = re.sub(r"^(research|look up|look into|find out|investigate)\s+", "", cleaned, flags=re.IGNORECASE)
    topic = re.sub(r"\b(latest|recent|breaking)\b", " ", topic, flags=re.IGNORECASE)
    topic = re.sub(r"\bnews\b", " ", topic, flags=re.IGNORECASE)
    topic = re.sub(r"\babout\b", " ", topic, flags=re.IGNORECASE)
    return " ".join(topic.split()).strip() or cleaned


def _fast_research_answer(question: str) -> str:
    cleaned = " ".join(str(question or "").split()).strip()
    if not cleaned:
        return ""
    lowered = cleaned.lower()
    if re.search(r"\b(?:how is|how's|status of|project status)\b", lowered):
        payload = run_agent("project_status", {"query": cleaned})
        answer = " ".join(str(payload.get("result", "") or "").split()).strip()
        if payload.get("status") == "ok" and answer and not answer.lower().startswith("which "):
            return answer

    if "news" in lowered and any(token in lowered for token in ("latest", "recent", "breaking", "today")):
        result = run_agent("news", {"topic": _research_topic_hint(cleaned), "hours": 24, "query": cleaned})
        answer = " ".join(str(result.get("result", "") or "").split()).strip()
        if result.get("status") == "ok" and answer and "still thinking" not in answer.lower():
            return answer

    decision = analyze_query(cleaned)
    action = str(decision.get("action", "") or "").strip()
    if action == "fetch":
        payload = {"query": cleaned}
        url = str(decision.get("url", "") or "").strip()
        if url:
            payload["url"] = url
        result = run_agent("fetch", payload)
    elif action == "news":
        result = run_agent("news", {"topic": _research_topic_hint(cleaned), "hours": 24, "query": cleaned})
    elif action == "search":
        result = run_agent("search", {"query": cleaned})
    else:
        return ""

    answer = " ".join(str(result.get("result", "") or "").split()).strip()
    if result.get("status") != "ok" or not answer:
        return ""
    if "still thinking" in answer.lower():
        return ""
    if answer.lower().startswith(("which ", "tell me ", "i couldn't ", "i could not ", "couldn't ", "could not ")):
        return ""
    return answer


async def _run_research_custom(question: str, model: str) -> str:
    researcher = create_react_agent(
        name="BurryResearch",
        system_prompt=_RESEARCH_SYSTEM_PROMPT,
        model_name=model,
        intent_name="deep_research",
        toolkit=_research_toolkit(),
        memory=InMemoryMemory(),
        plan_notebook=PlanNotebook(max_subtasks=4),
        max_iters=5,
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


def _deep_research_custom(question: str, model: str = RESEARCH_MODEL) -> str:
    import concurrent.futures

    try:
        asyncio.get_running_loop()
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(asyncio.run, _run_research_custom(question, model))
            return future.result(timeout=60)
    except RuntimeError:
        return asyncio.run(_run_research_custom(question, model))


def deep_research(question: str, model: str = RESEARCH_MODEL) -> str:
    """Use AgentScope DeepResearchAgent if available, custom fallback otherwise."""
    fast_answer = _fast_research_answer(question)
    if fast_answer:
        return fast_answer
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
        result = future.result(timeout=60)
        return result.get_text_content() if hasattr(result, "get_text_content") else str(result)
    except (ImportError, Exception):
        pass
    return _deep_research_custom(question, model)
