"""Semantic planner that maps freeform requests to validated capability tasks."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from brain.query_analyzer import analyze_query
from .contracts import CapabilityTask
from .registry import get_tool_spec, tool_catalog_for_prompt

RUNTIME_STATE_PATH = Path(__file__).resolve().parent.parent / "memory" / "runtime_state.json"

_LIVE_FACT_PATTERNS = (
    "president",
    "prime minister",
    "ceo",
    "stock price",
    "share price",
    "weather",
    "latest",
    "recent",
    "current",
    "today",
    "news",
)


class _SemanticTaskPayload(BaseModel):
    kind: str = "answer"
    goal: str = ""
    tool: str = ""
    args: dict[str, Any] = Field(default_factory=dict)
    answer: str = ""
    needs_clarification: bool = False
    clarification: str = ""


def _normalized(text: str) -> str:
    return " ".join(str(text or "").split()).strip()


def load_runtime_snapshot() -> dict[str, Any]:
    try:
        from runtime import load_runtime_state

        payload = load_runtime_state()
        if isinstance(payload, dict):
            return payload
    except Exception:
        pass

    try:
        payload = json.loads(RUNTIME_STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def frontmost_app(runtime_state: dict[str, Any] | None = None) -> str:
    runtime_state = runtime_state if isinstance(runtime_state, dict) else load_runtime_snapshot()
    workspace = runtime_state.get("workspace") if isinstance(runtime_state.get("workspace"), dict) else {}
    return str(workspace.get("frontmost_app", "") or runtime_state.get("frontmost_app", "") or "").strip()


def resolve_named_path(location: str) -> Path:
    lowered = str(location or "").strip().lower()
    home = Path.home()
    mapping = {
        "desktop": home / "Desktop",
        "downloads": home / "Downloads",
        "documents": home / "Documents",
        "developer": home / "Developer",
        "home": home,
    }
    return mapping.get(lowered, home)


def _clean_name(value: str) -> str:
    cleaned = " ".join(str(value or "").split()).strip(" .,!?:;\"'")
    cleaned = re.sub(r"\s+(?:please|now|for me)$", "", cleaned, flags=re.IGNORECASE)
    return cleaned


def resolve_folder_request(text: str) -> dict[str, str]:
    lowered = " ".join(str(text or "").lower().split())
    location = "desktop" if "desktop" in lowered else "documents" if "documents" in lowered else "downloads" if "downloads" in lowered else "developer"

    patterns = (
        r"\b(?:name|named|called)\s+(.+)$",
        r"\bwith\s+(?:the\s+)?name\s+(.+)$",
        r"\bfolder\s+(.+)$",
    )
    folder_name = ""
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            folder_name = _clean_name(match.group(1))
            break

    if not folder_name:
        compact = re.sub(r"^(?:make|create|open)\s+", "", str(text or "").strip(), flags=re.IGNORECASE)
        compact = re.sub(r"\b(?:one more|another|new)\b", " ", compact, flags=re.IGNORECASE)
        compact = re.sub(r"\bfolder\b", " ", compact, flags=re.IGNORECASE)
        compact = re.sub(r"\bon\s+(desktop|documents|downloads)\b", " ", compact, flags=re.IGNORECASE)
        folder_name = _clean_name(compact)

    root = resolve_named_path(location)
    return {
        "location": location,
        "name": folder_name,
        "path": str(root / folder_name) if folder_name else "",
    }


def resolve_weather_query(text: str) -> str:
    cleaned = " ".join(str(text or "").split())
    match = re.search(r"\bweather(?:\s+(?:in|for|at)\s+(.+))?$", cleaned, flags=re.IGNORECASE)
    if match and match.group(1):
        return f"weather in {_clean_name(match.group(1))}"
    match = re.search(r"\b(?:in|for|at)\s+(.+)$", cleaned, flags=re.IGNORECASE)
    if match:
        return f"weather in {_clean_name(match.group(1))}"
    return _clean_name(cleaned)


def resolve_youtube_query(text: str) -> str:
    cleaned = " ".join(str(text or "").split())
    cleaned = re.sub(r"\bon\s+youtube\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^(?:play|put on|open|search|find)\s+", "", cleaned, flags=re.IGNORECASE)
    return _clean_name(cleaned)


def _clarify(goal: str, question: str, *, intent_name: str, confidence: float = 0.45) -> CapabilityTask:
    return CapabilityTask(
        kind="clarify",
        goal=goal,
        needs_clarification=True,
        clarification=question,
        confidence=confidence,
        intent_name=intent_name,
    )


def _plan_from_heuristics(text: str, *, current_intent: str = "") -> CapabilityTask | None:
    cleaned = _normalized(text)
    lowered = cleaned.lower()
    runtime_state = load_runtime_snapshot()

    if "youtube" in lowered and re.search(r"\b(?:play|put on)\b", lowered):
        query = resolve_youtube_query(cleaned)
        if not query:
            return _clarify("play on YouTube", "What should I play on YouTube?", intent_name="play_youtube")
        return CapabilityTask(
            kind="control",
            goal=f"Open {query} on YouTube",
            tool="play_youtube",
            args={"query": query},
            confidence=0.92,
            intent_name="play_youtube",
            quick_response="Opening that on YouTube.",
            force_override=current_intent == "spotify_play",
        )

    if re.search(r"\bminimi[sz]e\b", lowered) and any(token in lowered for token in ("window", "app", "this")):
        app = frontmost_app(runtime_state)
        if not app:
            return _clarify("minimize current window", "Which app should I minimize?", intent_name="minimize_app")
        return CapabilityTask(
            kind="control",
            goal=f"Minimize {app}",
            tool="minimize_app",
            args={"app": app},
            confidence=0.9,
            intent_name="minimize_app",
            quick_response=f"Minimizing {app}.",
        )

    if "folder" in lowered and any(token in lowered for token in ("make", "create", "new", "one more", "another", "name", "named", "called")):
        folder = resolve_folder_request(cleaned)
        if not folder.get("name") or not folder.get("path"):
            return _clarify("create folder", "What should I name the folder?", intent_name="create_folder")
        location = folder.get("location", "developer")
        return CapabilityTask(
            kind="control",
            goal=f"Create folder {folder['name']} on {location}",
            tool="create_folder",
            args={"path": folder["path"]},
            confidence=0.88,
            intent_name="create_folder",
            quick_response=f"Creating {folder['name']} on {location}.",
            force_override=current_intent == "create_folder" or location != "developer",
        )

    if any(token in lowered for token in ("vps", "server", "container", "docker")) and any(token in lowered for token in ("check", "status", "health", "up", "my")):
        return CapabilityTask(
            kind="lookup",
            goal="Check VPS health",
            tool="check_vps",
            args={},
            confidence=0.88,
            intent_name="vps_status",
            force_override=current_intent in {"vps_status", "docker_status"},
        )

    if "weather" in lowered:
        query = resolve_weather_query(cleaned)
        if not query or query.lower() == "weather":
            return _clarify("check weather", "Which location should I check the weather for?", intent_name="lookup_weather")
        return CapabilityTask(
            kind="lookup",
            goal=f"Check {query}",
            tool="lookup_weather",
            args={"query": query},
            confidence=0.9,
            intent_name="lookup_weather",
        )

    if current_intent == "news" or any(token in lowered for token in ("latest news", "recent news", "breaking news")):
        topic = re.sub(r"\b(?:latest|recent|breaking|news|about|on|for|the)\b", " ", lowered)
        topic = " ".join(topic.split()).strip() or "AI"
        return CapabilityTask(
            kind="lookup",
            goal=f"Fetch latest news about {topic}",
            tool="lookup_news",
            args={"topic": topic if topic != "ai" else "AI"},
            confidence=0.85,
            intent_name="news",
            force_override=current_intent == "news",
        )

    if any(pattern in lowered for pattern in _LIVE_FACT_PATTERNS):
        decision = analyze_query(cleaned)
        if decision["action"] in {"search", "fetch", "news"} or any(token in lowered for token in ("president", "ceo", "weather")):
            return CapabilityTask(
                kind="lookup",
                goal=f"Look up {cleaned}",
                tool="lookup_web",
                args={"query": cleaned.rstrip("?")},
                confidence=max(float(decision.get("confidence", 0.0) or 0.0), 0.7),
                intent_name="lookup_web",
            )

    return None


def _canonical_tool_name(name: str) -> str:
    aliases = {
        "vps_status": "check_vps",
        "weather": "lookup_weather",
        "search": "lookup_web",
        "live_lookup": "lookup_web",
        "news": "lookup_news",
        "youtube_play": "play_youtube",
    }
    cleaned = str(name or "").strip()
    if not cleaned:
        return ""
    spec = get_tool_spec(cleaned)
    if spec is not None:
        return spec.name
    return aliases.get(cleaned, "")


def _plan_with_model(text: str, *, current_intent: str = "") -> CapabilityTask | None:
    try:
        from brain.ollama_client import _call, pick_butler_model
    except Exception:
        return None

    schema = json.dumps(_SemanticTaskPayload.model_json_schema(), indent=2)
    prompt = f"""Return only valid JSON matching this schema.

Schema:
{schema}

Available tools:
{tool_catalog_for_prompt()}

Rules:
- Use a tool when the request controls the system or needs current information.
- Prefer play_youtube when the user explicitly says YouTube.
- Prefer minimize_app when the user refers to this window or current app.
- Prefer create_folder for folder creation requests.
- Prefer compose_email for Gmail draft requests.
- Prefer lookup_weather for weather requests.
- Prefer check_vps for VPS or server status.
- Prefer lookup_news for latest news.
- Prefer lookup_web for live current facts.
- If a tool is missing required args, set needs_clarification to true and ask one short question.
- If no tool is needed, leave tool empty and answer directly.

Current deterministic intent: {current_intent or "unknown"}
User request: "{text}"

JSON:"""
    try:
        raw = _call(
            prompt,
            pick_butler_model("planning"),
            temperature=0.0,
            max_tokens=220,
        )
    except Exception:
        return None

    try:
        payload = _SemanticTaskPayload.model_validate_json(raw)
    except Exception:
        try:
            payload = _SemanticTaskPayload.model_validate(json.loads(raw))
        except Exception:
            return None

    tool_name = _canonical_tool_name(payload.tool)
    if payload.needs_clarification:
        return _clarify(payload.goal or _normalized(text), payload.clarification or "Can you clarify that?", intent_name=tool_name or "clarify", confidence=0.5)
    if not tool_name:
        answer = _normalized(payload.answer)
        if answer:
            return CapabilityTask(
                kind="answer",
                goal=_normalized(payload.goal or text),
                answer=answer,
                confidence=0.5,
                intent_name="semantic_answer",
                source="semantic_model",
            )
        return None
    return CapabilityTask(
        kind=payload.kind if payload.kind in {"answer", "control", "lookup", "draft", "plan", "clarify"} else "control",
        goal=_normalized(payload.goal or text),
        tool=tool_name,
        args=dict(payload.args or {}),
        confidence=0.55,
        intent_name=tool_name,
        source="semantic_model",
    )


def plan_semantic_task(text: str, *, current_intent: str = "") -> CapabilityTask | None:
    task = _plan_from_heuristics(text, current_intent=current_intent)
    if task is not None:
        return task
    return _plan_with_model(text, current_intent=current_intent)
