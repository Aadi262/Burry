#!/usr/bin/env python3
"""
agents/runner.py
Specialist agent runner for Butler's delegated tasks.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess

import numpy as np
import requests

from butler_config import AGENT_MODEL_CHAINS, AGENT_MODELS, EXA_API_KEY, OLLAMA_MODEL
from brain.ollama_client import (
    _get_available_models,
    _check_memory,
    _get_request_target_for_model,
    _unload_model,
    pick_agent_model,
)
from mcp import MCPError, call_server_tool, list_server_tools, normalize_tool_result
from butler_secrets.loader import get_vps_secret

ROUTED_MODELS = {
    agent_type: (chain[0] if chain else AGENT_MODELS.get(agent_type, OLLAMA_MODEL))
    for agent_type, chain in AGENT_MODEL_CHAINS.items()
}
ROUTED_MODELS.update(AGENT_MODELS)
ROUTED_MODELS["default"] = OLLAMA_MODEL

_installed_models: set[str] = set()
_LAST_FETCH_DATA: dict = {}


def _get_installed_models() -> set[str]:
    global _installed_models
    if _installed_models:
        return _installed_models
    try:
        _installed_models = _get_available_models()
        return _installed_models
    except Exception:
        return set()


def _pick_model(agent_type: str) -> str:
    model = pick_agent_model(agent_type)
    installed = _get_installed_models()
    if installed and model not in installed and model.split(":")[0] not in installed:
        preferred = ROUTED_MODELS.get(agent_type, ROUTED_MODELS["default"])
        print(f"[Agent] {preferred} not installed, using {model}")
    return model


def _prepare_model_request(model: str) -> None:
    _check_memory()
    for candidate in {name for name in ROUTED_MODELS.values() if name and name != model}:
        _unload_model(candidate)


def _call_model(prompt: str, model: str, max_tokens: int = 400) -> str:
    _prepare_model_request(model)
    url, headers, _backend = _get_request_target_for_model(model)
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "keep_alive": "2m",
        "options": {
            "temperature": 0.3,
            "num_predict": max_tokens,
            "num_ctx": 1024,
        },
    }
    response = requests.post(url, json=payload, headers=headers, timeout=90)
    response.raise_for_status()
    return response.json().get("response", "").strip()


def _get_exa_api_key() -> str:
    return os.environ.get("EXA_API_KEY", "").strip() or EXA_API_KEY.strip()


def _cosine_sim(a: list, b: list) -> float:
    """Cosine similarity between two embedding vectors."""
    a_vec, b_vec = np.array(a), np.array(b)
    denom = np.linalg.norm(a_vec) * np.linalg.norm(b_vec)
    return float(np.dot(a_vec, b_vec) / denom) if denom else 0.0


def _embed(text: str) -> list:
    """Get embedding from the active Ollama backend."""
    from butler_config import EMBED_MODEL

    try:
        url, headers, _backend = _get_request_target_for_model(EMBED_MODEL)
        response = requests.post(
            url.replace("/api/generate", "/api/embeddings"),
            json={"model": EMBED_MODEL, "prompt": text[:500]},
            headers=headers,
            timeout=10,
        )
        response.raise_for_status()
        return response.json().get("embedding", [])
    except Exception:
        return []


def _jina_fetch(url: str) -> str:
    """Fetch clean text from any URL via Jina Reader."""
    try:
        response = requests.get(
            f"https://r.jina.ai/{url}",
            headers={"Accept": "text/plain", "X-Return-Format": "text"},
            timeout=10,
        )
        return response.text[:600] if response.status_code == 200 else ""
    except Exception:
        return ""


def _searxng_search(query: str, num: int = 8) -> list:
    """Fetch raw results from local SearXNG."""
    from butler_config import SEARXNG_URL

    try:
        response = requests.get(
            f"{SEARXNG_URL}/search",
            params={
                "q": query,
                "format": "json",
                "categories": "general",
                "language": "en",
            },
            timeout=6,
        )
        response.raise_for_status()
        results = response.json().get("results", [])
        return [
            {
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "content": item.get("content", ""),
            }
            for item in results[:num]
        ]
    except Exception:
        return []


def _exa_search(query: str, num: int = 5) -> list:
    """Premium path using Exa when configured."""
    exa_key = _get_exa_api_key()
    if not exa_key:
        return []

    try:
        response = requests.post(
            "https://api.exa.ai/search",
            headers={
                "x-api-key": exa_key,
                "Content-Type": "application/json",
            },
            json={
                "query": query,
                "type": "auto",
                "numResults": num,
                "contents": {
                    "highlights": {"maxCharacters": 400},
                },
            },
            timeout=8,
        )
        response.raise_for_status()
        results = response.json().get("results", [])
        return [
            {
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "content": (
                    item.get("highlights", [""])[0]
                    if item.get("highlights")
                    else item.get("text", "")[:400]
                ),
            }
            for item in results
        ]
    except Exception:
        return []


def run_agent(agent_type: str, input_data: dict) -> dict:
    """
    Run a specialist agent and return structured results.

    agent_type:
      news | vps | memory | code | search | github | bugfinder
    """
    model = _pick_model(agent_type)
    print(f"[Agent/{agent_type}] Using model: {model}")

    try:
        if agent_type == "news":
            return _news_agent(input_data, model)
        if agent_type == "vps":
            return _vps_agent(input_data, model)
        if agent_type == "memory":
            return _memory_agent(input_data, model)
        if agent_type == "code":
            return _code_agent(input_data, model)
        if agent_type == "search":
            return _search_agent(input_data, model)
        if agent_type == "github":
            return _github_agent(input_data, model)
        if agent_type == "bugfinder":
            return _bugfinder_agent(input_data, model)
        return {"status": "error", "result": f"Unknown agent type: {agent_type}", "data": {}}
    except Exception as exc:
        print(f"[Agent/{agent_type}] Error: {exc}")
        return {"status": "error", "result": str(exc), "data": {}}


def _news_agent(data: dict, model: str) -> dict:
    topic = data.get("topic", "AI and tech news")
    hours = data.get("hours", 24)
    global _LAST_FETCH_DATA
    _LAST_FETCH_DATA = {}
    material = _fetch_headlines(f"{topic} last {hours} hours")
    search_data = (
        dict(_LAST_FETCH_DATA)
        if _LAST_FETCH_DATA.get("text") == material
        else {"backend": "headline_wrapper", "tool": "headlines", "text": material}
    )

    if not material or len(material.strip()) < 20:
        prompt = f"Summarize what you know about recent {topic} news in under 50 words."
        try:
            summary = _call_model(prompt, model, max_tokens=100)
        except Exception:
            summary = f"I couldn't fetch live {topic} news right now."
        return {"status": "ok", "result": summary, "data": {}}

    prompt = f"""Summarize this recent news material about "{topic}".
List the 3 most important things. Under 80 words total. Be concrete.

Material:
{material[:2200]}

Summary:"""
    summary = _call_model(prompt, model, max_tokens=160)
    return {"status": "ok", "result": summary, "data": search_data}


def _search_agent(data: dict, model: str) -> dict:
    query = data.get("query", "")
    global _LAST_FETCH_DATA
    _LAST_FETCH_DATA = {}
    material = _fetch_headlines(query)
    search_data = (
        dict(_LAST_FETCH_DATA)
        if _LAST_FETCH_DATA.get("text") == material
        else {"backend": "headline_wrapper", "tool": "headlines", "text": material}
    )

    if not material or len(material.strip()) < 20:
        prompt = f"Answer this concisely in under 40 words: {query}"
        try:
            answer = _call_model(prompt, model, max_tokens=80)
        except Exception:
            answer = f"I couldn't look that up right now: {query}"
        return {"status": "ok", "result": answer, "data": {}}

    prompt = f"""Answer this question directly and specifically.
Question: {query}

Material:
{material[:2200]}

Answer in under 60 words:"""
    answer = _call_model(prompt, model, max_tokens=120)
    return {"status": "ok", "result": answer, "data": search_data}


def _fetch_search_text(query: str, count: int = 5) -> str:
    """
    Mini-Exa pipeline:
      1. Exa if key set
      2. SearXNG if local search is running
      3. Semantic rerank via local embeddings
      4. Jina Reader for top result content
      5. Return ranked snippets plus top content
    """
    global _LAST_FETCH_DATA

    raw = _exa_search(query, num=max(5, count)) if _get_exa_api_key() else []
    backend = "exa" if raw else "searxng"
    if not raw:
        raw = _searxng_search(query, num=max(8, count))
    if not raw:
        _LAST_FETCH_DATA = {"backend": backend, "tool": "semantic", "text": ""}
        return ""

    query_vec = _embed(query)
    if query_vec:
        scored = []
        for result in raw:
            doc_text = f"{result.get('title', '')} {result.get('content', '')}"
            doc_vec = _embed(doc_text)
            score = _cosine_sim(query_vec, doc_vec) if doc_vec else 0.0
            scored.append((score, result))
        scored.sort(key=lambda item: item[0], reverse=True)
        ranked = [result for _, result in scored]
    else:
        ranked = raw

    top_content = ""
    if ranked:
        top_content = _jina_fetch(str(ranked[0].get("url", "")).strip())

    snippets = "\n".join(
        f"{result.get('title', '')}: {str(result.get('content', ''))[:120]}".strip(": ")
        for result in ranked[:4]
    ).strip()
    text = f"{snippets}\n\nTop result:\n{top_content[:400]}".strip() if top_content else snippets
    _LAST_FETCH_DATA = {"backend": backend, "tool": "semantic", "text": text}
    return text


def _fetch_headlines(query: str) -> str:
    global _LAST_FETCH_DATA
    fetched = _fetch_search_text(query, count=6)
    if isinstance(fetched, dict):
        _LAST_FETCH_DATA = dict(fetched)
        return _LAST_FETCH_DATA.get("text", "")
    if isinstance(fetched, str):
        if not _LAST_FETCH_DATA:
            _LAST_FETCH_DATA = {"backend": "semantic", "tool": "search", "text": fetched}
        return fetched
    _LAST_FETCH_DATA = {"backend": "semantic", "tool": "search", "text": ""}
    return ""


def _resolve_ssh_target(host: str) -> str:
    if "@" in host:
        return host
    secret = get_vps_secret(host)
    username = str(secret.get("username", "")).strip()
    return f"{username}@{host}" if username else host


def _vps_agent(data: dict, model: str) -> dict:
    host = data.get("host", "")
    if not host:
        return {"status": "error", "result": "No VPS host configured", "data": {}}

    resolved_host = _resolve_ssh_target(host)
    commands = [
        "docker ps --format 'table {{.Names}}\\t{{.Status}}\\t{{.Ports}}'",
        "df -h / | tail -1",
        "free -h | grep Mem",
        "uptime",
    ]

    secret = get_vps_secret(host)
    raw_outputs = []
    for command in commands:
        shell_cmd = ["ssh", "-o", "ConnectTimeout=8", resolved_host, command]
        if secret.get("password") and shutil.which("sshpass"):
            shell_cmd = ["sshpass", "-p", secret["password"], *shell_cmd]

        try:
            result = subprocess.run(
                shell_cmd,
                capture_output=True,
                text=True,
                timeout=20,
            )
            stdout = (result.stdout or "").strip()
            stderr = (result.stderr or "").strip()
            if stdout or stderr:
                block = stdout or stderr
                raw_outputs.append(f"$ {command}\n{block}")
        except Exception as exc:
            raw_outputs.append(f"$ {command}\nFailed: {exc}")

    if not raw_outputs:
        return {"status": "error", "result": "Could not connect to VPS", "data": {}}

    raw = "\n\n".join(raw_outputs)
    prompt = f"""You are analyzing VPS status output.
Summarize what is running, what looks healthy, and what needs attention.
Under 60 words. Name containers explicitly when present.

Raw output:
{raw[:2200]}

Plain English summary:"""
    summary = _call_model(prompt, model, max_tokens=120)
    return {"status": "ok", "result": summary, "data": {"raw": raw[:2400], "host": resolved_host}}


def _memory_agent(data: dict, model: str) -> dict:
    sessions = data.get("sessions", [])
    if not sessions:
        return {"status": "ok", "result": "Nothing to compress", "data": {}}

    session_text = "\n".join(
        [
            f"- {session.get('timestamp', '')[:16]}: {session.get('speech', '')[:100]}"
            for session in sessions[-10:]
        ]
    )

    prompt = f"""Compress these Butler sessions into 3 key memory points.
Each point must stay under 120 characters and start with the date.

Sessions:
{session_text}

3 memory points:"""
    summary = _call_model(prompt, model, max_tokens=200)
    points = [line.strip("- *").strip() for line in summary.splitlines() if line.strip()]
    return {"status": "ok", "result": summary, "data": {"points": points[:3]}}


def _code_agent(data: dict, model: str) -> dict:
    task = data.get("task", "")
    context = data.get("context", "")
    language = data.get("language", "python")

    prompt = f"""Write {language} code for this task.
Task: {task}
Context: {context}

Output only the code:"""
    code = _call_model(prompt, model, max_tokens=600)
    return {"status": "ok", "result": code, "data": {"language": language}}


def _github_agent(data: dict, model: str) -> dict:
    tool_name = data.get("tool", "")
    arguments = data.get("arguments", {}) if isinstance(data.get("arguments"), dict) else {}
    question = data.get("question", "")

    if not tool_name:
        tools = list_server_tools("github")
        names = [tool.get("name", "") for tool in tools if tool.get("name")]
        result = "Available GitHub MCP tools: " + ", ".join(names[:12]) if names else "No GitHub MCP tools available"
        return {"status": "ok", "result": result, "data": {"tools": names[:20]}}

    result = call_server_tool(
        "github",
        arguments=arguments,
        preferred_tool=tool_name,
        hints=["repo", "pull", "issue", "github"],
    )
    raw_text = normalize_tool_result(result)
    if not question:
        return {
            "status": "ok",
            "result": raw_text[:1000] or "GitHub MCP call returned no text",
            "data": {"tool": tool_name},
        }

    prompt = f"""Answer this GitHub question directly.
Question: {question}

GitHub tool output:
{raw_text[:2600]}

Answer in under 80 words:"""
    answer = _call_model(prompt, model, max_tokens=140)
    return {"status": "ok", "result": answer, "data": {"tool": tool_name}}


def _bugfinder_agent(data: dict, model: str) -> dict:
    logs = data.get("logs", "")
    if isinstance(logs, list):
        logs = "\n".join(str(item) for item in logs)
    target = data.get("target", "system")
    scope = data.get("scope", "quick")

    if not logs:
        logs = json.dumps(data, indent=2)

    prompt = f"""You are Butler's bug finder.
Analyze these diagnostics for target "{target}" (scope: {scope}).
Return the top bugs or regressions, likely root cause, and next fix.
Under 120 words. Be specific.

Diagnostics:
{logs[:3200]}

Bug summary:"""
    summary = _call_model(prompt, model, max_tokens=220)
    return {"status": "ok", "result": summary, "data": {"target": target, "scope": scope}}


if __name__ == "__main__":
    print("=== Specialist Agent Tests ===\n")

    failures = 0
    for agent_name, payload in [
        ("news", {"topic": "AI agents 2026", "hours": 24}),
        ("search", {"query": "what is Qwen2.5 model"}),
        (
            "memory",
            {
                "sessions": [
                    {"timestamp": "2026-04-04T01:30", "speech": "Still grinding on mac-butler executor"},
                    {"timestamp": "2026-04-04T02:00", "speech": "Fixed voice layer, now using Samantha"},
                    {"timestamp": "2026-04-04T13:00", "speech": "Back at it, wiring multi-agent system"},
                ]
            },
        ),
    ]:
        print(f"Testing {agent_name} agent...")
        result = run_agent(agent_name, payload)
        print(f"  Status: {result['status']}")
        print(f"  Result: {result['result'][:180]}\n")
        if result["status"] != "ok":
            failures += 1

    raise SystemExit(0 if failures == 0 else 1)
