#!/usr/bin/env python3
"""
brain/ollama_client.py
Two-stage Ollama client:
1. Planner decides focus and actions as JSON.
2. Voice layer writes the final spoken line.
"""

from __future__ import annotations

import asyncio
import base64
import json
import random
import re
from datetime import datetime
from typing import Any

import requests
try:
    import psutil
except ImportError:
    psutil = None

from butler_secrets.loader import get_ollama_secret, get_secret
from memory.graph import read_graph
from utils import _normalize
from butler_config import (
    AGENT_MODEL_CHAINS,
    AGENT_MODELS,
    BUTLER_MODEL_CHAINS,
    BUTLER_MODELS,
    HEARTBEAT_MODEL,
    MODEL_PROVIDER_ENDPOINTS,
    NVIDIA_API_KEY_ENV,
    OLLAMA_FALLBACK,
    OLLAMA_LOCAL_URL,
    OLLAMA_MODEL,
    USE_VPS_OLLAMA,
    VPS_OLLAMA_FALLBACK,
    VPS_OLLAMA_MODEL,
    VPS_OLLAMA_PASS,
    VPS_OLLAMA_URL,
    VPS_OLLAMA_USER,
    split_model_ref,
)
from memory.learner import get_learned_patterns

TIMEOUT = 45
VOICE_TIMEOUT = 12
DEFAULT_TIMEOUT = 20
AGENT_TIMEOUT = 30
CLASSIFIER_TIMEOUT = 4
MEMORY_WARN_GB = 1.5
VPS_REQUEST_TIMEOUT = 8
MLX_VOICE_MODEL_ID = "mlx-community/gemma-4-e4b-it-4bit"
_MLX_VOICE_BACKEND: tuple[Any, Any, Any] | bool | None = None
KNOWN_OLLAMA_MODELS = {
    model_name
    for provider, model_name in (
        split_model_ref(model)
        for model in {
            OLLAMA_MODEL,
            OLLAMA_FALLBACK,
            VPS_OLLAMA_MODEL,
            VPS_OLLAMA_FALLBACK,
            HEARTBEAT_MODEL,
            *BUTLER_MODELS.values(),
            *(model for chain in BUTLER_MODEL_CHAINS.values() for model in chain),
            *AGENT_MODELS.values(),
            *(model for chain in AGENT_MODEL_CHAINS.values() for model in chain),
        }
        if model
    )
    if model_name and provider in {"auto", "ollama_local", "ollama_vps"}
}
_BACKEND_MODEL_MAP_CACHE: dict[str, dict[str, str]] = {"local": {}, "vps": {}}

GREETINGS = {
    "morning": [
        "Morning",
        "Hey, good morning",
        "Rise and grind",
        "Alright, let's get it",
        "Top of the morning",
    ],
    "afternoon": [
        "Hey",
        "Alright",
        "Back at it",
        "What needs shipping",
        "What's next",
    ],
    "evening": [
        "Evening",
        "Still at it",
        "Wrapping up?",
        "One more push",
        "Hey, good evening",
    ],
    "late_night": [
        "Still grinding",
        "Burning the midnight oil",
        "Late one tonight",
        "Night owl mode",
        "Still here",
    ],
}

def build_system_prompt() -> str:
    return """You are Burry's planner running on Aditya's Mac.

Rules:
1. Output ONLY a JSON object.
2. Choose the single best next step from the provided context.
3. Be specific about project, file, or system when possible.
4. Keep actions to max 2 and only use them if genuinely useful.
5. Do not write speech here.
6. Prefer mac-butler or email-infra by name when the context supports it.
7. Do not invent vague work if the context already points to a concrete task.
8. Prefer [PROJECT SNAPSHOT] over [TASK LIST] when both are present.
9. If [DEPENDENCY GRAPH] shows fixing X unblocks Y, prefer X and mention the unblock reason.

Return exactly this schema:
{
  "focus": "specific project or task",
  "why_now": "short reason under 18 words",
  "question": "short follow-up question ending with ?",
  "actions": []
}

Available action types - pick ONLY what is genuinely useful:
Terminal actions:
{"type": "open_terminal", "mode": "tab"}
-> new tab in existing Terminal window
{"type": "open_terminal", "mode": "window"}
-> brand new Terminal window
{"type": "open_terminal", "mode": "tab", "cmd": "npm run dev", "cwd": "~/Burry/mac-butler"}
-> new tab and immediately run a command
Editor actions:
{"type": "open_editor", "path": "~/Burry/mac-butler", "editor": "cursor", "mode": "smart"}
-> open path in Cursor, reuse existing window
{"type": "open_editor", "path": "~/Developer/new-project", "editor": "cursor", "mode": "new_window"}
-> force a brand new Cursor window
{"type": "open_editor", "mode": "focus", "editor": "cursor"}
-> just bring Cursor to front, don't open anything
App actions:
{"type": "open_app", "app": "Spotify", "mode": "smart"}
-> focus if running, launch if not
{"type": "open_app", "app": "Claude", "mode": "smart"}
{"type": "open_app", "app": "Obsidian", "mode": "smart"}
Music actions:
{"type": "search_and_play", "query": "chikni chameli"}
-> actually searches Spotify and plays
{"type": "play_music", "mode": "focus"}
-> plays focus playlist
{"type": "play_music", "mode": "late_night"}
{"type": "play_music", "mode": "off"}
File actions:
{"type": "create_and_open", "path": "~/Developer/my-project", "editor": "cursor"}
{"type": "write_file", "path": "~/notes.md", "content": "...", "mode": "append"}
{"type": "obsidian_note", "title": "...", "content": "...", "folder": "Daily"}
Project actions:
{"type": "open_project", "name": "Adpilot"}
-> use this when the user says "open X" or "work on X"
VPS actions:
{"type": "ssh_open", "host": "user@ip", "label": "My VPS"}
-> SSH in a new Terminal tab
{"type": "ssh_command", "host": "user@ip", "cmd": "docker ps"}
Command actions:
{"type": "run_command", "cmd": "git status", "cwd": "~/Burry/mac-butler"}
{"type": "run_command", "cmd": "npm run dev", "cwd": "~/Burry/mac-butler", "in_terminal": true}
-> runs visibly in a Terminal tab (use for long-running commands)
Agent actions:
{"type": "run_agent", "agent": "news", "topic": "AI news"}
{"type": "run_agent", "agent": "vps", "host": "user@ip"}
Other:
{"type": "notify", "title": "Butler", "message": "..."}
{"type": "remind_in", "minutes": 30, "message": "check deploy"}
KEY RULES for choosing actions:

"open terminal" with no mode specified -> default to "tab"
"new terminal" or "another terminal" -> mode: "window"
"open VS Code / Cursor" when it's already running -> mode: "new_window"
"open [app]" when you don't know if it's running -> mode: "smart"
"open X" or "work on X" for a known project -> prefer {"type":"open_project","name":"X"}
long-running commands (servers, builds) -> always use in_terminal: true
quick commands (git status, ls) -> in_terminal: false
"""


PLANNER_SYSTEM_PROMPT = build_system_prompt()

SPEECH_SYSTEM_PROMPT = """You are Burry's voice.

Rules:
1. Output ONLY a JSON object with "speech", "greeting", and "actions".
2. Use the provided greeting exactly once.
3. Under 35 words unless execution results are explicitly provided later.
4. Short, decisive sentences.
5. End with exactly one binary question answerable with yes or no.
6. Never start with "Welcome back".
7. Avoid filler like "keep moving", "stay focused", or "continue where you left off".
8. Name mac-butler or email-infra when relevant; if context is thin, say that plainly instead of pretending.
9. If you do not have enough context, ask a short clarifying question instead of filling space.
10. If the project name already appears in the first clause, do not repeat it in the task clause; name the task directly.
11. Match the provided mood instruction explicitly. Keep the tone consistent with it.
"""

FEW_SHOT_SPEECH_EXAMPLES = """Example A:
{"speech": "Morning. mac-butler still needs the router and executor speaking the same language. Want to wire that now?", "greeting": "Morning", "actions": [{"type": "open_editor", "path": "~/Burry/mac-butler", "editor": "cursor", "mode": "smart"}]}
{"speech": "Still grinding. email-infra is bottlenecked on the trust score formula. Want to sketch that first?", "greeting": "Still grinding", "actions": []}
{"speech": "Evening. mac-butler audit is done, but the specialist agents still need a full pass. Want to test them now?", "greeting": "Evening", "actions": []}
{"speech": "Hey. Context is thin on my side. Want me to stay on mac-butler?", "greeting": "Hey", "actions": []}"""

COMPACT_VPS_PLANNER_SYSTEM_PROMPT = """Output only JSON:
{"focus":"...", "next":"...", "actions":[]}
Use the real project name from context when present.
Keep focus and next concise. At most one action.
If [DEPENDENCY GRAPH] shows an unblock path, prefer the step that unblocks another project."""
def _dependency_graph_context(context_text: str, limit: int = 6) -> str:
    try:
        edges = list(read_graph().get("edges") or [])
    except Exception:
        return ""
    if not edges:
        return ""

    normalized_context = _normalize(context_text)
    relevant = []
    for edge in edges:
        source = str(edge.get("from", "")).strip()
        target = str(edge.get("to", "")).strip()
        if not source or not target:
            continue
        if normalized_context:
            if _normalize(source) not in normalized_context and _normalize(target) not in normalized_context:
                continue
        relevant.append(edge)

    if not relevant:
        relevant = edges[:limit]

    relation_map = {
        "depends_on": "depends on",
        "shares_resource": "shares resources with",
        "blocked_by": "is blocked by",
    }
    lines = ["[DEPENDENCY GRAPH]"]
    for edge in relevant[:limit]:
        source = str(edge.get("from", "")).strip()
        target = str(edge.get("to", "")).strip()
        relation = relation_map.get(str(edge.get("type", "")).strip(), str(edge.get("type", "")).replace("_", " "))
        note = " ".join(str(edge.get("note", "")).split()).strip()
        suffix = f" ({note})" if note else ""
        lines.append(f"  {source} {relation} {target}{suffix}")
    return "\n".join(lines)


def _check_memory() -> bool:
    """Returns False if the system is low on memory."""
    if USE_VPS_OLLAMA and VPS_OLLAMA_URL:
        return True
    if psutil is None:
        return True
    try:
        free_gb = psutil.virtual_memory().available / (1024**3)
        if free_gb < MEMORY_WARN_GB:
            print(f"[Brain] WARNING: only {free_gb:.1f}GB RAM free")
            return False
        return True
    except Exception:
        return True


def _get_vps_auth() -> tuple[str, str]:
    secret = get_ollama_secret()
    username = str(
        secret.get("user")
        or secret.get("username")
        or VPS_OLLAMA_USER
    ).strip()
    password = str(secret.get("password") or VPS_OLLAMA_PASS).strip()
    return username or VPS_OLLAMA_USER, password


def _provider_config(provider: str) -> dict[str, Any]:
    return dict(MODEL_PROVIDER_ENDPOINTS.get(str(provider or "").strip(), {}))


def _provider_kind(provider: str) -> str:
    return str(_provider_config(provider).get("kind", "") or "")


def _nvidia_api_key() -> str:
    return get_secret(NVIDIA_API_KEY_ENV, default="")


def _model_provider_and_name(model: str) -> tuple[str, str]:
    provider, model_name = split_model_ref(model)
    return provider, str(model_name or "").strip()


def _provider_ready(provider: str) -> bool:
    kind = _provider_kind(provider)
    if kind == "openai":
        return bool(_nvidia_api_key())
    if provider == "ollama_local":
        return True
    if provider == "ollama_vps":
        return bool(USE_VPS_OLLAMA and VPS_OLLAMA_URL)
    return False


def _resolve_backend_model(model: str, use_vps_backend: bool) -> str:
    provider, model_name = _model_provider_and_name(model)
    if provider not in {"auto", "ollama_local", "ollama_vps"}:
        return model_name
    if not use_vps_backend:
        return model_name
    if model_name == OLLAMA_MODEL and VPS_OLLAMA_MODEL:
        return VPS_OLLAMA_MODEL
    if model_name == OLLAMA_FALLBACK and VPS_OLLAMA_FALLBACK:
        return VPS_OLLAMA_FALLBACK
    return model_name


def _get_backend_ollama_url(
    backend: str,
    *,
    require_healthy: bool = True,
) -> tuple[str, dict[str, str]]:
    if backend == "local":
        return f"{OLLAMA_LOCAL_URL.rstrip('/')}/api/generate", {}

    if backend != "vps" or not USE_VPS_OLLAMA or not VPS_OLLAMA_URL:
        raise RuntimeError(f"unsupported Ollama backend: {backend}")

    username, password = _get_vps_auth()
    headers: dict[str, str] = {}
    if username and password:
        creds = base64.b64encode(f"{username}:{password}".encode()).decode()
        headers = {"Authorization": f"Basic {creds}"}

    if require_healthy:
        health_url = VPS_OLLAMA_URL.rstrip("/").rsplit("/ollama", 1)[0]
        response = requests.get(f"{health_url}/health", timeout=3)
        response.raise_for_status()

    return f"{VPS_OLLAMA_URL.rstrip('/')}/api/generate", headers


def _get_ollama_url() -> tuple[str, dict[str, str]]:
    """
    Return (generate_url, headers) for the best available Ollama backend.
    Prefer VPS when configured and healthy, otherwise fall back to local.
    """
    if USE_VPS_OLLAMA and VPS_OLLAMA_URL:
        try:
            url, headers = _get_backend_ollama_url("vps", require_healthy=True)
            print(f"[Brain] Using VPS Ollama: {VPS_OLLAMA_URL.rstrip('/')}")
            return url, headers
        except Exception:
            print("[Brain] VPS unreachable, falling back to local Ollama")

    return _get_backend_ollama_url("local", require_healthy=False)


def _unload_model(model: str) -> None:
    """Best-effort request to unload an Ollama model from memory."""
    if not model:
        return
    try:
        url, headers = _get_ollama_url()
        requests.post(
            url,
            json={"model": model, "keep_alive": 0},
            headers=headers,
            timeout=5,
        )
    except Exception:
        pass


def _prepare_model_request(model: str) -> None:
    if _backend_for_model(model) not in {"auto", "local", "vps"}:
        return
    _check_memory()
    for candidate in KNOWN_OLLAMA_MODELS:
        if candidate != model:
            _unload_model(candidate)


def _get_backend_model_map(backend: str, force_refresh: bool = False) -> dict[str, str]:
    global _BACKEND_MODEL_MAP_CACHE
    cached = _BACKEND_MODEL_MAP_CACHE.get(backend, {})
    if cached and not force_refresh:
        return cached
    try:
        url, headers = _get_backend_ollama_url(
            backend,
            require_healthy=(backend == "vps"),
        )
        response = requests.get(
            url.replace("/api/generate", "/api/tags"),
            headers=headers,
            timeout=5,
        )
        response.raise_for_status()
        model_map: dict[str, str] = {}
        for item in response.json().get("models", []):
            name = str(item.get("name", "")).strip()
            if not name:
                continue
            model_map.setdefault(name, name)
            model_map.setdefault(name.split(":")[0], name)
        _BACKEND_MODEL_MAP_CACHE[backend] = model_map
        return model_map
    except Exception:
        return {}


def _get_available_models(force_refresh: bool = False) -> set[str]:
    return set(_get_available_model_map(force_refresh=force_refresh))


def _get_available_model_map(force_refresh: bool = False) -> dict[str, str]:
    combined = dict(_get_backend_model_map("vps", force_refresh=force_refresh))
    combined.update(_get_backend_model_map("local", force_refresh=force_refresh))
    return combined


def _dedupe_models(models: list[str]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for model in models:
        name = str(model or "").strip()
        if not name or name in seen:
            continue
        ordered.append(name)
        seen.add(name)
    return ordered


def _retry_model_chain(model: str) -> list[str]:
    chains = list(BUTLER_MODEL_CHAINS.values()) + list(AGENT_MODEL_CHAINS.values()) + [[f"ollama_local::{OLLAMA_MODEL}", f"ollama_local::{OLLAMA_FALLBACK}"]]
    model_provider, model_name = _model_provider_and_name(model)
    normalized = model_name.split(":")[0]
    matches: list[tuple[int, int, list[str]]] = []
    for chain in chains:
        ordered = _dedupe_models(list(chain) + [f"ollama_local::{OLLAMA_FALLBACK}"])
        for index, candidate in enumerate(ordered):
            candidate_provider, candidate_name = _model_provider_and_name(candidate)
            if candidate == model:
                matches.append((0 if index == 0 else 1, index, ordered))
                break
            if (
                candidate_provider == model_provider
                and (candidate_name == model_name or candidate_name.split(":")[0] == normalized)
            ):
                matches.append((0 if index == 0 else 1, index, ordered))
                break
    if matches:
        _, index, ordered = sorted(matches, key=lambda item: (item[0], item[1]))[0]
        return [item for item in ordered[index + 1:] if item and item != model]
    local_fallback = f"ollama_local::{OLLAMA_FALLBACK}"
    return [item for item in [local_fallback] if item and item != model]


def _post_with_thinking_notice(
    url: str,
    *,
    json_payload: dict[str, Any],
    headers: dict[str, str] | None = None,
    timeout: int | float = 60,
):
    response = requests.post(
        url,
        json=json_payload,
        headers=headers or {},
        timeout=timeout,
    )
    response.raise_for_status()
    return response


def _message_text(content: Any) -> str:
    if isinstance(content, str):
        return _strip_provider_reasoning_markers(content)
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                text = str(item.get("text", "") or "").strip()
                if text:
                    parts.append(text)
        return _strip_provider_reasoning_markers("\n".join(parts))
    return _strip_provider_reasoning_markers(str(content or ""))


def _strip_provider_reasoning_markers(text: str) -> str:
    cleaned = str(text or "").strip()
    if not cleaned:
        return ""
    # Gemma 4 can emit empty or populated thought-channel wrappers even when
    # thinking is disabled. Keep only the final user-facing text.
    cleaned = re.sub(r"(?is)<\|channel\>thought.*?<channel\|>", "", cleaned)
    cleaned = re.sub(r"(?is)<\|channel\>analysis.*?<channel\|>", "", cleaned)
    cleaned = re.sub(r"(?is)<\|channel\>final", "", cleaned)
    cleaned = re.sub(r"(?is)<channel\|>", "", cleaned)
    return cleaned.strip()


def _openai_text_from_response(data: dict[str, Any]) -> str:
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    message = choices[0].get("message", {})
    if not isinstance(message, dict):
        return ""
    return _message_text(message.get("content"))


def _openai_message_from_response(data: dict[str, Any]) -> dict[str, Any]:
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        return {}
    message = choices[0].get("message", {})
    if not isinstance(message, dict):
        return {}
    normalized = dict(message)
    normalized["content"] = _message_text(message.get("content"))
    return normalized


def _system_with_patterns(system: str | None) -> str:
    base = str(system or "").strip()
    patterns = get_learned_patterns()
    if patterns:
        return f"{base}\n\n{patterns}".strip()
    return base


def _prompt_messages(prompt: str, system: str | None = None) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    system_text = _system_with_patterns(system)
    if system_text:
        messages.append({"role": "system", "content": system_text})
    messages.append({"role": "user", "content": prompt})
    return messages


def _request_text_once(
    prompt: str,
    model: str,
    *,
    temperature: float,
    max_tokens: int,
    system: str | None = None,
    timeout_hint: str | None = None,
) -> str:
    url, headers, backend = _get_request_target_for_model(model)
    use_vps_backend = backend == "vps"
    request_timeout = _resolve_request_timeout(timeout_hint, use_vps_backend=use_vps_backend)
    resolved_model = _resolve_backend_model(model, use_vps_backend)
    system_text = _system_with_patterns(system)

    if backend in {"local", "vps", "auto"}:
        _prepare_model_request(resolved_model)
        payload: dict[str, Any] = {
            "model": resolved_model,
            "prompt": prompt,
            "stream": False,
            "keep_alive": "5m",
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
                "num_ctx": 2048,
                "stop": ["```", "\n\n\n"],
            },
        }
        if system_text:
            payload["system"] = system_text
        response = _post_with_thinking_notice(
            url,
            json_payload=payload,
            headers=headers,
            timeout=request_timeout,
        )
        data = response.json()
        return str(data.get("response", "") or "").strip()

    payload = {
        "model": resolved_model,
        "messages": _prompt_messages(prompt, system),
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    response = _post_with_thinking_notice(
        url,
        json_payload=payload,
        headers=headers,
        timeout=request_timeout,
    )
    return _openai_text_from_response(response.json())


def _chat_once(
    messages: list[dict],
    model: str,
    *,
    tools: list[dict] | None = None,
    max_tokens: int = 200,
    temperature: float = 0.2,
    timeout_hint: str | None = None,
) -> dict[str, Any]:
    url, headers, backend = _get_request_target_for_model(model)
    use_vps_backend = backend == "vps"
    request_timeout = _resolve_request_timeout(timeout_hint, use_vps_backend=use_vps_backend)
    resolved_model = _resolve_backend_model(model, use_vps_backend)

    if backend in {"local", "vps", "auto"}:
        request_url = url.replace("/api/generate", "/api/chat")
        _prepare_model_request(resolved_model)
        payload: dict[str, Any] = {
            "model": resolved_model,
            "messages": messages,
            "stream": False,
            "keep_alive": "5m",
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
                "num_ctx": 4096,
            },
        }
        if tools:
            payload["tools"] = tools
        response = _post_with_thinking_notice(
            request_url,
            json_payload=payload,
            headers=headers,
            timeout=request_timeout,
        )
        data = response.json()
        return data if isinstance(data, dict) else {}

    payload: dict[str, Any] = {
        "model": resolved_model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if tools:
        payload["tools"] = tools
    response = _post_with_thinking_notice(
        url,
        json_payload=payload,
        headers=headers,
        timeout=request_timeout,
    )
    data = response.json()
    message = _openai_message_from_response(data)
    return {"message": message} if message else {}


def _pick_model_from_chain(candidates: list[str], label: str) -> str:
    chain = _dedupe_models(candidates)
    if not chain:
        return f"ollama_local::{OLLAMA_MODEL}"

    local_map = _get_backend_model_map("local")
    vps_map = _get_backend_model_map("vps")

    for candidate in chain:
        provider, model_name = _model_provider_and_name(candidate)
        if provider == "nvidia":
            if _provider_ready(provider):
                if candidate != chain[0]:
                    print(f"[Brain] {label} routed to fallback model {model_name}")
                return candidate
            continue

        if provider in {"ollama_local", "auto"}:
            exact_local = local_map.get(model_name) or local_map.get(model_name.split(":")[0])
            if exact_local:
                resolved = f"ollama_local::{exact_local}"
                if candidate != chain[0]:
                    print(f"[Brain] {label} routed to fallback model {exact_local}")
                return resolved

        if provider in {"ollama_vps", "auto"}:
            exact_vps = vps_map.get(model_name) or vps_map.get(model_name.split(":")[0])
            if exact_vps:
                resolved = f"ollama_vps::{exact_vps}"
                if candidate != chain[0]:
                    print(f"[Brain] {label} routed to fallback model {exact_vps}")
                return resolved

    print(f"[Brain] No installed model found for {label}, using {chain[0]}")
    return chain[0]


def pick_butler_model(role: str, override: str | None = None) -> str:
    chain = []
    if override:
        chain.append(override)
    chain.extend(BUTLER_MODEL_CHAINS.get(role, []))
    chain.append(BUTLER_MODELS.get(role, ""))
    if role != "voice":
        chain.append(f"ollama_local::{OLLAMA_MODEL}")
    # RL-informed model selection (Phase 11)
    try:
        from memory.rl_loop import get_best_model_for_intent
        candidates = [m for m in chain if m]
        if candidates:
            rl_best = get_best_model_for_intent(role, candidates)
            if rl_best and rl_best not in chain[:1]:
                chain.insert(0, rl_best)
    except Exception:
        pass
    return _pick_model_from_chain(chain, f"butler:{role}")


def pick_agent_model(agent_type: str, override: str | None = None) -> str:
    chain = []
    if override:
        chain.append(override)
    chain.extend(AGENT_MODEL_CHAINS.get(agent_type, []))
    chain.append(AGENT_MODELS.get(agent_type, ""))
    chain.append(f"ollama_local::{OLLAMA_MODEL}")
    return _pick_model_from_chain(chain, f"agent:{agent_type}")


def _backend_for_model(model: str) -> str:
    provider, model_name = _model_provider_and_name(model)
    if provider == "nvidia":
        return "nvidia"
    if provider == "ollama_local":
        return "local"
    if provider == "ollama_vps":
        return "vps"

    local_map = _get_backend_model_map("local")
    if local_map.get(model_name) or local_map.get(model_name.split(":")[0]):
        return "local"
    vps_map = _get_backend_model_map("vps")
    if vps_map.get(model_name) or vps_map.get(model_name.split(":")[0]):
        return "vps"
    return "auto"


def _get_request_target_for_model(model: str) -> tuple[str, dict[str, str], str]:
    backend = _backend_for_model(model)
    if backend == "nvidia":
        config = _provider_config("nvidia")
        api_key = _nvidia_api_key()
        if not api_key:
            raise RuntimeError(f"{NVIDIA_API_KEY_ENV} is not configured")
        url = f"{str(config.get('base_url', '')).rstrip('/')}/chat/completions"
        return url, {"Authorization": f"Bearer {api_key}"}, "nvidia"
    if backend in {"local", "vps"}:
        try:
            url, headers = _get_backend_ollama_url(
                backend,
                require_healthy=(backend == "vps"),
            )
            return url, headers, backend
        except Exception:
            if backend == "vps":
                local_url, local_headers = _get_backend_ollama_url(
                    "local",
                    require_healthy=False,
                )
                return local_url, local_headers, "local"

    url, headers = _get_ollama_url()
    backend = "vps" if USE_VPS_OLLAMA and VPS_OLLAMA_URL and VPS_OLLAMA_URL.rstrip("/") in url else "local"
    return url, headers, backend


def check_vps_connection() -> dict:
    """
    Return status details for the currently active Ollama connection.
    """
    url, headers = _get_ollama_url()
    try:
        tags_url = url.replace("/api/generate", "/api/tags")
        response = requests.get(tags_url, headers=headers, timeout=5)
        response.raise_for_status()
        models = [model.get("name", "") for model in response.json().get("models", [])]
        is_vps = bool(
            USE_VPS_OLLAMA
            and VPS_OLLAMA_URL
            and VPS_OLLAMA_URL.rstrip("/") in url
        )
        return {
            "status": "ok",
            "backend": "vps" if is_vps else "local",
            "models": [name for name in models if name],
            "url": url,
        }
    except Exception as exc:
        backend = "vps" if USE_VPS_OLLAMA and VPS_OLLAMA_URL else "local"
        return {
            "status": "error",
            "backend": backend,
            "models": [],
            "url": url,
            "error": str(exc),
        }


def _time_period() -> str:
    hour = datetime.now().hour
    if hour >= 23 or hour <= 4:
        return "late_night"
    if hour < 12:
        return "morning"
    if hour < 17:
        return "afternoon"
    return "evening"


def _random_greeting() -> str:
    period = _time_period()
    return random.choice(GREETINGS.get(period, GREETINGS["afternoon"]))


def _time_greeting() -> str:
    period = _time_period()
    if period == "morning":
        return "Morning"
    if period == "afternoon":
        return "Welcome back"
    if period == "evening":
        return "Good evening"
    return "Still grinding"


def _get_identity() -> str:
    try:
        from identity.loader import get_identity_context

        return get_identity_context()
    except Exception:
        return ""


def _get_memory() -> str:
    try:
        from memory.store import get_last_session_summary

        summary = get_last_session_summary()
        return f"[LAST SESSION]\n{summary}" if summary else ""
    except Exception:
        try:
            from memory.store import get_memory_context

            context = get_memory_context()
            return context or ""
        except Exception:
            return ""


def _get_mood_state() -> dict:
    try:
        from brain.mood_engine import describe_mood_state

        return describe_mood_state()
    except Exception:
        return {
            "name": "focused",
            "label": "Focused",
            "instruction": "Be sharp and direct. Cut to the next real move with no fluff.",
            "note": "Locked on the next concrete step.",
        }


def _supports_mlx_voice(model: str) -> bool:
    name = str(model or "").strip().lower()
    if not name:
        return False
    base = name.split(":", 1)[0]
    return base == "gemma4"


def _get_mlx_voice_backend() -> tuple[Any, Any, Any] | None:
    global _MLX_VOICE_BACKEND
    if _MLX_VOICE_BACKEND is False:
        return None
    if isinstance(_MLX_VOICE_BACKEND, tuple):
        return _MLX_VOICE_BACKEND

    try:
        from mlx_lm import generate as mlx_generate
        from mlx_lm import load as mlx_load
    except Exception:
        _MLX_VOICE_BACKEND = False
        return None

    try:
        model_obj, tokenizer = mlx_load(MLX_VOICE_MODEL_ID)
    except Exception as exc:
        print(f"[Brain] MLX voice load failed: {exc}")
        _MLX_VOICE_BACKEND = False
        return None

    _MLX_VOICE_BACKEND = (model_obj, tokenizer, mlx_generate)
    return _MLX_VOICE_BACKEND


def call_voice(
    prompt: str,
    model: str,
    *,
    temperature: float,
    max_tokens: int,
    system: str | None = None,
) -> str:
    backend = _get_mlx_voice_backend() if _supports_mlx_voice(model) else None
    if backend:
        model_obj, tokenizer, mlx_generate = backend
        combined_prompt = prompt.strip()
        if system:
            combined_prompt = (
                f"System:\n{system.strip()}\n\n"
                f"User:\n{prompt.strip()}\n\n"
                "Assistant:\n"
            )
        try:
            response = mlx_generate(
                model_obj,
                tokenizer,
                combined_prompt,
                max_tokens=max_tokens,
            )
            return str(response).strip()
        except Exception as exc:
            print(f"[Brain] MLX voice generation failed: {exc}")

    return _call(
        prompt,
        model,
        temperature=temperature,
        max_tokens=max_tokens,
        system=system,
        timeout_hint="voice",
    )


def _default_plan() -> dict:
    return {
        "focus": "current work",
        "why_now": "The next useful step is visible.",
        "question": "Want to tackle it now?",
        "actions": [],
    }


def _parse_plan(raw: str) -> dict:
    default = _default_plan()
    try:
        data = json.loads(_strip(raw))
    except Exception:
        return default

    focus = str(data.get("focus", "")).strip() or default["focus"]
    why_now = str(data.get("why_now", "")).strip() or default["why_now"]
    question = str(data.get("question", "")).strip() or default["question"]
    if not question.endswith("?"):
        question = question.rstrip(".") + "?"

    actions = data.get("actions", [])
    if not isinstance(actions, list):
        actions = []
    actions = [item for item in actions[:2] if isinstance(item, dict)]

    return {
        "focus": focus,
        "next": str(data.get("next", "")).strip(),
        "why_now": why_now,
        "question": question,
        "actions": actions,
    }


def _fallback_speech(greeting: str, plan: dict) -> str:
    focus = plan.get("focus", "current work")
    why_now = plan.get("why_now", "The next useful step is visible.")
    question = plan.get("question", "Want to tackle it now?")
    return f"{greeting}. {focus} is up next. {why_now} {question}"


def _strip_repeated_project_from_task(focus: str, next_action: str) -> str:
    focus_name = (focus or "").strip().lower()
    task = (next_action or "").strip()
    if not focus_name or not task:
        return task

    candidate = task
    candidate = re.sub(
        rf"\b(?:into|for|on|in)\s+{re.escape(focus_name)}\b",
        "",
        candidate,
        flags=re.IGNORECASE,
    )
    candidate = re.sub(r"\s+", " ", candidate).strip(" .,;:-")

    if candidate.lower() == focus_name:
        return task
    if len(candidate.split()) < 3:
        return task
    return candidate


def send_to_ollama(context_text: str, model: str | None = None) -> str:
    planner_model = pick_butler_model("planning", override=model)
    speech_model = pick_butler_model("voice", override=model)
    greeting = _random_greeting()
    compact_vps_mode = _backend_for_model(planner_model) == "vps"
    context_limit = 220 if compact_vps_mode else 600
    plan_max_tokens = 90 if compact_vps_mode else 260
    speech_max_tokens = 180
    mood_state = _get_mood_state()
    mood_name = str(mood_state.get("name", "focused")).strip() or "focused"
    mood_instruction = str(mood_state.get("instruction", "")).strip()
    mood_note = str(mood_state.get("note", "")).strip()
    dependency_block = _dependency_graph_context(context_text)
    planner_context = "\n\n".join(part for part in (dependency_block, context_text) if part)

    if compact_vps_mode:
        plan_prompt = f"""Context:
{planner_context[:context_limit]}

Return ONLY JSON:
{{"focus":"...", "next":"...", "actions":[]}}

Rules:
- Use mac-butler or email-infra exactly if present
- focus = project or immediate task
- next = single concrete next step
- Keep each value under 12 words
- actions can be empty"""
        planner_system = COMPACT_VPS_PLANNER_SYSTEM_PROMPT
    else:
        plan_prompt = f"""You are a planning engine for Aditya.
Rules you MUST follow:
- If context contains project names, use them directly
- Prefer [PROJECT SNAPSHOT] over [TASK LIST] when both exist
- If [DEPENDENCY GRAPH] shows that fixing X unblocks Y, choose X and say why
- NEVER write "current work" — use the actual project name
- NEVER write "next useful step" — name the actual task
- mac-butler = his local voice operator agent project
- email-infra = his cold email system project
- If the user asks to open or work on a project, prefer an open_project action

Context:
{planner_context[:context_limit]}

Output ONLY this JSON object, nothing else:
{{
  "focus": "<exact project or task name from context above>",
  "next": "<specific task, not generic>",
  "actions": []
}}

If context mentions mac-butler -> focus must say mac-butler
If context mentions email-infra -> focus must say email-infra
Output ONLY JSON:"""
        planner_system = PLANNER_SYSTEM_PROMPT

    try:
            planner_raw = _call(
                plan_prompt,
                planner_model,
                temperature=0.3,
                max_tokens=plan_max_tokens,
                system=planner_system,
        )
    except Exception as exc:
        print(f"[Brain] Planner error: {exc}")
        return json.dumps(
            {
                "speech": f"{greeting}. Couldn't reach the brain right now. Want to retry?",
                "greeting": greeting,
                "actions": [],
            }
        )

    plan = _parse_plan(planner_raw)
    focus = plan.get("focus", "").strip() or "mac-butler"
    next_action = plan.get("next") or plan.get("why_now", "").strip() or "finish the next concrete task"
    actions = plan.get("actions", [])

    if focus == "current work":
        lowered = context_text.lower()
        if "mac-butler" in lowered:
            focus = "mac-butler"
        elif "email-infra" in lowered:
            focus = "email-infra"

    if next_action in {"", "The next useful step is visible."} or "next useful step" in next_action.lower():
        next_action = "resolve the top blocker"

    spoken_next_action = _strip_repeated_project_from_task(focus, next_action)

    speech_raw = ""
    if not compact_vps_mode:
        identity_block = _get_identity()
        memory_block = _get_memory()
        speech_prompt = f"""{identity_block}
{memory_block}

You are Burry, Aditya's live operator on Mac.

EXAMPLES OF GOOD OUTPUT (match this quality):
{FEW_SHOT_SPEECH_EXAMPLES}

CURRENT SITUATION:
Focus: {focus}
Next: {spoken_next_action}
Time greeting: {greeting}
Current mood: {mood_name}
Mood instruction: {mood_instruction}
Mood note: {mood_note}

Rules:
- Under 50 words
- End with ONE binary question
- Use mac-butler or email-infra by name when relevant
- If context is thin, say that plainly in one short clause and then ask
- If the project name already appeared, name only the task in the next clause
- No generic filler phrases
- Include these actions: {json.dumps(actions)}

Output ONLY JSON:"""

        try:
            speech_raw = call_voice(
                speech_prompt,
                speech_model,
                temperature=0.5,
                max_tokens=speech_max_tokens,
                system=SPEECH_SYSTEM_PROMPT,
            ).strip()
        except Exception as exc:
            print(f"[Brain] Speech error: {exc}")
            speech_raw = ""

    speech = ""
    final_greeting = greeting
    final_actions = actions
    if speech_raw:
        try:
            speech_data = json.loads(_strip(speech_raw))
            speech = str(speech_data.get("speech", "")).strip()
            final_greeting = str(speech_data.get("greeting", "")).strip() or greeting
            parsed_actions = speech_data.get("actions")
            if isinstance(parsed_actions, list) and parsed_actions:
                final_actions = [item for item in parsed_actions[:2] if isinstance(item, dict)]
        except Exception:
            speech = speech_raw.strip()

    if not speech:
        speech = f"{greeting}. Next up in {focus}: {spoken_next_action}. Want me to line up the first step?"
    elif not speech.lower().startswith(final_greeting.lower()):
        speech = f"{final_greeting}. {speech}"

    if next_action != spoken_next_action and next_action in speech:
        speech = speech.replace(next_action, spoken_next_action)
    speech = speech.replace("current work", focus)
    speech = speech.replace("next useful step", spoken_next_action)

    return json.dumps(
        {
            "speech": speech.strip(),
            "greeting": final_greeting,
            "actions": final_actions,
            "focus": focus,
            "why_now": next_action,
            "mood": mood_name,
        }
    )


def _call_ollama(
    prompt: str,
    model: str,
    temperature: float,
    max_tokens: int,
    system: str | None = None,
    timeout_hint: str | None = None,
) -> str:
    from brain.rate_limiter import get_limiter
    _limiter = get_limiter()
    if not _limiter.acquire(timeout=30.0):
        # Rate limit exceeded — skip rather than crash
        return ""
    try:
        return _call_ollama_inner(
            prompt,
            model,
            temperature,
            max_tokens,
            system,
            timeout_hint=timeout_hint,
        )
    finally:
        _limiter.release()


def _resolve_request_timeout(timeout_hint: str | None, *, use_vps_backend: bool) -> int:
    if use_vps_backend:
        return VPS_REQUEST_TIMEOUT

    hint = str(timeout_hint or "").strip().lower()
    if hint == "classifier":
        return CLASSIFIER_TIMEOUT
    if hint == "voice":
        return VOICE_TIMEOUT
    if hint == "agent":
        return AGENT_TIMEOUT
    return DEFAULT_TIMEOUT


def _call_ollama_inner(
    prompt: str,
    model: str,
    temperature: float,
    max_tokens: int,
    system: str | None = None,
    timeout_hint: str | None = None,
) -> str:
    chain = _dedupe_models([model] + _retry_model_chain(model))
    last_error: Exception | None = None

    for index, candidate in enumerate(chain):
        try:
            return _request_text_once(
                prompt,
                candidate,
                temperature=temperature,
                max_tokens=max_tokens,
                system=system,
                timeout_hint=timeout_hint,
            )
        except requests.exceptions.Timeout as exc:
            last_error = exc
            backend = _backend_for_model(candidate)
            request_timeout = _resolve_request_timeout(timeout_hint, use_vps_backend=(backend == "vps"))
            if index < len(chain) - 1:
                print(f"[Brain] {candidate} timed out after {request_timeout}s, trying {chain[index + 1]}")
                continue
            print(f"[Brain] {candidate} timed out after {request_timeout}s")
            break
        except Exception as exc:
            last_error = exc
            if index < len(chain) - 1:
                print(f"[Brain] {candidate} failed, trying {chain[index + 1]}")
            continue

    if isinstance(last_error, requests.exceptions.ConnectionError):
        raise ConnectionError("LLM backend unreachable. Check Ollama or NVIDIA provider settings.")
    if isinstance(last_error, requests.exceptions.Timeout):
        return ""
    raise RuntimeError(f"Ollama error: {last_error}")


def _call(
    prompt: str,
    model: str,
    temperature: float,
    max_tokens: int,
    system: str | None = None,
    timeout_hint: str | None = None,
) -> str:
    return _call_ollama(
        prompt,
        model,
        temperature=temperature,
        max_tokens=max_tokens,
        system=system,
        timeout_hint=timeout_hint,
    )


def _yield_complete_sentences(buffer: str) -> tuple[list[str], str]:
    sentences: list[str] = []
    working = str(buffer or "")
    while True:
        indexes = [working.find(mark) for mark in (".", "!", "?") if working.find(mark) >= 0]
        if not indexes:
            break
        cutoff = min(indexes) + 1
        sentence = working[:cutoff].strip()
        working = working[cutoff:].strip()
        if sentence:
            sentences.append(sentence)
    return sentences, working


async def stream_llm_tokens(prompt: str, model: str, system: str = ""):
    """Stream tokens from Ollama as they arrive. Yields sentence chunks for TTS.
    STEAL 3 — speak as tokens arrive instead of waiting for full response.
    """
    import httpx
    from typing import AsyncIterator

    backend = _backend_for_model(model)
    if backend not in {"local", "vps", "auto"}:
        text = _call(prompt, model, temperature=0.2, max_tokens=300, system=system)
        if text:
            yield text
        return

    url, headers, resolved_backend = _get_request_target_for_model(model)
    use_vps_backend = resolved_backend == "vps"
    resolved_model = _resolve_backend_model(model, use_vps_backend)
    payload = {
        "model": resolved_model,
        "prompt": prompt,
        "system": _system_with_patterns(system) if system else "",
        "stream": True,
    }
    buffer = ""
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            async with client.stream("POST", url, json=payload, headers=headers) as response:
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                        token = chunk.get("response", "")
                        buffer += token
                        sentences, buffer = _yield_complete_sentences(buffer)
                        for sentence in sentences:
                            yield sentence
                        if chunk.get("done"):
                            if buffer.strip():
                                yield buffer.strip()
                            break
                    except Exception:
                        continue
    except Exception:
        # Fallback: return nothing (caller will use standard _call)
        return


async def stream_chat_with_ollama(
    messages: list[dict],
    model: str,
    *,
    max_tokens: int = 200,
    temperature: float = 0.3,
):
    """Stream assistant chat content sentence-by-sentence for live TTS."""
    import httpx

    url, headers, backend = _get_request_target_for_model(model)
    if backend not in {"local", "vps", "auto"}:
        payload = chat_with_ollama(
            messages,
            model,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        content = _message_text((payload.get("message") or {}).get("content", ""))
        if content:
            yield content
        return

    request_url = url.replace("/api/generate", "/api/chat")
    use_vps_backend = backend == "vps"
    resolved_model = _resolve_backend_model(model, use_vps_backend)
    _prepare_model_request(resolved_model)
    payload: dict[str, Any] = {
        "model": resolved_model,
        "messages": messages,
        "stream": True,
        "keep_alive": "5m",
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens,
            "num_ctx": 4096,
        },
    }
    timeout = httpx.Timeout(connect=5.0, read=90.0, write=15.0, pool=None)
    buffer = ""

    async with httpx.AsyncClient(timeout=timeout) as client:
        async with client.stream("POST", request_url, json=payload, headers=headers) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line:
                    continue
                try:
                    chunk = json.loads(line)
                except Exception:
                    continue
                token = str(chunk.get("message", {}).get("content", "") or "")
                if token:
                    buffer += token
                    sentences, buffer = _yield_complete_sentences(buffer)
                    for sentence in sentences:
                        yield sentence
                if chunk.get("done"):
                    if buffer.strip():
                        yield buffer.strip()
                    break


async def async_call(prompt: str, model: str, system: str = "", max_tokens: int = 300) -> str:
    """Non-blocking async LLM call via httpx. Never blocks the voice pipeline.
    STEAL 9 — use in background daemons so they don't block voice.
    """
    try:
        return await asyncio.to_thread(
            _call,
            prompt,
            model,
            0.2,
            max_tokens,
            system,
            "agent",
        )
    except requests.exceptions.Timeout:
        return ""
    except Exception:
        return ""


def chat_with_ollama(
    messages: list[dict],
    model: str,
    *,
    tools: list[dict] | None = None,
    max_tokens: int = 200,
    temperature: float = 0.2,
    timeout_hint: str | None = None,
) -> dict:
    chain = _dedupe_models([model] + _retry_model_chain(model))
    last_error: Exception | None = None

    for index, candidate in enumerate(chain):
        try:
            return _chat_once(
                messages,
                candidate,
                tools=tools,
                max_tokens=max_tokens,
                temperature=temperature,
                timeout_hint=timeout_hint,
            )
        except requests.exceptions.Timeout as exc:
            last_error = exc
            backend = _backend_for_model(candidate)
            request_timeout = _resolve_request_timeout(timeout_hint, use_vps_backend=(backend == "vps"))
            if index < len(chain) - 1:
                print(f"[Brain] chat {candidate} timed out after {request_timeout}s, trying {chain[index + 1]}")
                continue
            print(f"[Brain] chat {candidate} timed out after {request_timeout}s")
            break
        except Exception as exc:
            last_error = exc
            if index < len(chain) - 1:
                print(f"[Brain] chat {candidate} failed, trying {chain[index + 1]}")
            continue

    if isinstance(last_error, requests.exceptions.ConnectionError):
        raise ConnectionError("LLM backend unreachable. Check Ollama or NVIDIA provider settings.")
    if isinstance(last_error, requests.exceptions.Timeout):
        return {"message": {"content": ""}}
    raise RuntimeError(f"Ollama chat error: {last_error}")


def _strip(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    if "{" in cleaned and "}" in cleaned:
        start = cleaned.index("{")
        end = cleaned.rindex("}") + 1
        cleaned = cleaned[start:end]
    return cleaned


if __name__ == "__main__":
    test_ctx = """[TASK LIST]
  ○ Wire two-stage LLM into butler (mac-butler) [HIGH]
[FOCUS]
  project: mac-butler
[TIME]
  afternoon (01:30 PM)"""
    print("=== Ollama Client Test ===\n")
    print(f"Greeting: {_random_greeting()}")
    print(f"Model: {OLLAMA_MODEL}\n")
    print(send_to_ollama(test_ctx))
