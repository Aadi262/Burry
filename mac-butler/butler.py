#!/usr/bin/env python3
"""
butler.py
Mac Butler Orchestrator v4
Pipeline: Trigger -> STT -> Intent Router -> Executor -> LLM only if needed -> TTS
"""

from __future__ import annotations

import atexit
import argparse
import asyncio
import fcntl
import json
import os
import queue
import random
import re
import signal
import subprocess
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path

import requests
import brain.ollama_client as ollama_client
import memory.store as memory_store
import pipeline.speech as pipeline_speech

from butler_config import (
    BUTLER_MODELS,
    DAILY_INTEL_ENABLED,
    OLLAMA_FALLBACK,
    OLLAMA_LOCAL_URL,
    OLLAMA_MODEL,
    SEARXNG_URL,
    STARTUP_BRIEFING_MODEL as CONFIG_STARTUP_BRIEFING_MODEL,
    VPS_HOSTS,
)
from daemon.ambient import start_ambient_daemon
from brain.session_context import ctx
from brain.query_analyzer import analyze_query
from context import build_structured_context
from context.mac_activity import get_state_for_context, load_state as load_mac_state, start_watcher
from executor.engine import Executor
from intents.router import (
    IntentResult,
    clean_song_query,
    detect_editor_choice,
    extract_requested_filename,
    get_project_map,
    instant_route,
    is_ambiguous_song_query,
    route,
)
from memory.layered import save_project_detail, save_session
from memory.learner import analyze_and_learn
from memory.store import _load as _load_memory
from memory.store import (
    get_last_session_summary,
    record_project_execution,
    record_session,
    update_project_state,
)
from runtime import (
    clear_confirmation,
    consume_project_context_hint,
    load_runtime_state,
    notify,
    note_conversation_turns,
    note_heard_text,
    note_intent,
    note_memory_recall,
    note_runtime_event,
    note_session_active,
    note_tool_finished,
    note_tool_started,
    reset_runtime_state,
    request_confirmation,
    resolve_confirmation,
)
from state import State, state
from tasks import get_active_tasks
from voice import listen_continuous, speak
from runtime.tracing import add_event, trace_command

# AP5: Local imports moved to top — avoids re-importing on every call
from brain.ollama_client import (
    _call,
    chat_with_ollama,
    check_vps_connection,
    pick_butler_model,
    send_to_ollama,
    stream_chat_with_ollama,
    stream_llm_tokens,
)
from brain.agentscope_backbone import (
    get_backbone,
    interrupt_agentscope_turn,
    reset_backbone_session,
    run_agentscope_turn,
)
from brain.toolkit import get_toolkit
import brain.tools_registry  # noqa: F401 — registers tools on import
from brain.tools_registry import TOOLS
from memory.bus import record as _bus_record
from memory.graph import observe_project_relationships
from memory.long_term import save_session_state
from memory.long_term import configure_session_restore
from memory.store import load_recent_sessions, semantic_search
from pipeline.orchestrator import (
    TOOL_SYSTEM_PROMPT,
    _brain_context_text,
    _build_voice_prompt,
    _call_tool_with_toolkit,
    _clip_tool_payload,
    _consume_project_context_block,
    _deterministic_greeting_response,
    _fallback_tool_outcome,
    _fallback_tool_response,
    _fallback_tool_speech,
    _fast_path_llm_response,
    _looks_like_greeting,
    _looks_like_memory_question,
    _parse_tool_arguments,
    _recent_dialogue_context,
    _reply_without_action,
    _resolve_followup_text,
    _rewrite_speech_with_agent_results,
    _safe_tool_chat_response,
    _should_use_fast_path_intent,
    _smart_reply,
    _successful_agent_results,
    _tool_chat_endpoint_missing,
    _tool_chat_messages,
    _tool_chat_response,
    _toolkit_result_text,
    _unknown_brain_response,
    observe_and_followup,
)
from pipeline.recorder import (
    ConversationContext,
    _conversation_context_text,
    _recent_turns_prompt_text,
    _record,
    _remember_conversation_turn,
    _remember_project_state,
    reset_conversation_context,
)
from pipeline.router import (
    BACKGROUND_LANE_INTENTS,
    INSTANT_LANE_INTENTS,
    _DETERMINISTIC_CASUAL_RESPONSES,
    _clear_pending_dialogue,
    _dispatch_research,
    _execute_background,
    _execute_instant,
    _get_pending_dialogue,
    _handle_meta_intent,
    _looks_like_followup_reference,
    _route_initial_intent,
    _resolve_pending_dialogue,
    _run_background_action,
    _set_pending_dialogue,
    _should_use_brain_for_unknown,
    _unknown_response_for_text,
    get_quick_response,
    handle_input,
)

executor = Executor()
_WATCHER_LOCK = threading.Lock()
_WATCHER_STARTED = False

# Human-in-loop interrupt support (Phase 7)
_INTERRUPT_EVENT = threading.Event()
_INTERRUPT_MESSAGE = ""
_INTERRUPT_LOCK = threading.Lock()


def interrupt_burry(new_command: str) -> None:
    """Interrupt current Burry task with a new command.
    Called from HUD when user types while Burry is executing.
    """
    global _INTERRUPT_MESSAGE
    with _INTERRUPT_LOCK:
        _INTERRUPT_MESSAGE = new_command
    _INTERRUPT_EVENT.set()
    try:

        interrupt_agentscope_turn(new_command)
    except Exception as _e:
        print(f"[Butler] silent error: {_e}")
    print(f"[Butler] Interrupted — switching to: {new_command[:50]}")


def check_interrupt():
    """Check if user interrupted. Returns new command if yes, None if no."""
    global _INTERRUPT_MESSAGE
    if _INTERRUPT_EVENT.is_set():
        _INTERRUPT_EVENT.clear()
        with _INTERRUPT_LOCK:
            msg = _INTERRUPT_MESSAGE
            _INTERRUPT_MESSAGE = ""
        return msg
    return None


def _clear_pending_command_state() -> None:
    global _INTERRUPT_MESSAGE

    while True:
        try:
            _COMMAND_QUEUE.get_nowait()
        except queue.Empty:
            break

    _INTERRUPT_EVENT.clear()
    with _INTERRUPT_LOCK:
        _INTERRUPT_MESSAGE = ""


_CONVERSATION_LOCK = threading.Lock()
_LEARNING_TRACE_LOCK = threading.Lock()
_LAST_RESOLVED_COMMAND = {
    "text": "",
    "intent_name": "",
    "at": 0.0,
}
_COMMAND_QUEUE: queue.Queue = queue.Queue(maxsize=3)
_CTX_CACHE: dict | None = None
_CTX_CACHE_AT: float = 0.0
_CTX_CACHE_TTL_SECONDS: float = 120.0
_CTX_CACHE_LOCK = threading.Lock()
_SHUTDOWN_HANDLERS_INSTALLED = False
_SESSION_STATE_SAVED = False
_LIVE_RUNTIME_LOCK_HANDLE = None
_LIVE_RUNTIME_LOCK_PATH = Path(tempfile.gettempdir()) / "mac-butler-live-runtime.lock"
_FOLLOWUP_PREFIXES = (
    "and ",
    "then ",
    "so ",
    "what about ",
    "how about ",
    "and what ",
    "and who ",
    "and why ",
    "and how ",
    "with subject ",
    "subject is ",
    "the subject ",
    "body is ",
    "the body says ",
    "body should say ",
    "saying ",
    "message is ",
)
FAST_PATH_INTENTS = {"greeting", "question", "unknown", "chitchat"}
FAST_PATH_CONFIDENCE = 0.8
_SESSION_CONVERSATION = ConversationContext()

QUICK_RESPONSES = {
    "spotify_play": "Playing {song}.",
    "clarify_song": "Which song should I play?",
    "spotify_pause": "Paused.",
    "spotify_next": "Next track.",
    "spotify_prev": "Going back.",
    "spotify_volume": "Volume {direction}.",
    "spotify_mode": "{mode} music.",
    "open_app": "Opening {app}.",
    "close_app": "Closing {app}.",
    "create_file": "Created {filename}.",
    "create_folder": "Folder created.",
    "git_status": "Checking git.",
    "git_push": "Pushing to git.",
    "git_commit": "Committing.",
    "vps_status": "Checking VPS.",
    "docker_status": "Checking containers.",
    "deploy": "Deploying.",
    "obsidian_note": "Saved to Obsidian.",
    "open_obsidian": "Opening Obsidian.",
    "set_reminder": "Reminder in {minutes} minutes.",
    "open_project": "Opening {project}.",
    "ssh_open": "Opening SSH.",
    "system_info": "Checking system.",
}

HELP_TEXT = (
    "Try: research AgentScope, play mockingbird, open cursor, note: remember this, "
    "say sleep to go quiet, or clap or press Cmd Shift B to wake me."
)

_briefing_done = False
_SEARCH_CHECKED = False
_SEARCH_CHECKED_AT = 0.0
_SEARCH_CHECK_TTL_SECONDS = 120
_BRAIN_STATUS_CHECKED = False
_LOW_SIGNAL_STARTUP_PATTERNS = (
    "brave mcp",
    "github mcp",
    "mcp secret",
    "install piper",
    "local neural tts backend",
    "wire two-stage llm into butler",
    "add task system",
    "add observe loop",
    "implement layered memory",
)
STARTUP_BRIEFING_MODEL = CONFIG_STARTUP_BRIEFING_MODEL


def _check_searxng() -> bool:
    try:
        response = requests.get(
            f"{SEARXNG_URL}/search",
            params={"q": "butler-health", "format": "json"},
            timeout=2,
        )
        return response.status_code == 200
    except Exception:
        return False


def _warn_if_search_offline() -> None:
    global _SEARCH_CHECKED, _SEARCH_CHECKED_AT
    now = time.monotonic()
    if _SEARCH_CHECKED and (now - _SEARCH_CHECKED_AT) < _SEARCH_CHECK_TTL_SECONDS:
        return
    _SEARCH_CHECKED = True
    _SEARCH_CHECKED_AT = now
    if not _check_searxng():
        print("[Search] SearXNG offline — run: bash scripts/start_searxng.sh")


def _strip_context_section(text: str, header: str) -> str:
    if not text or not header:
        return text
    lines = text.splitlines()
    kept: list[str] = []
    skipping = False
    for line in lines:
        stripped = line.strip()
        if stripped == header:
            skipping = True
            continue
        if skipping and stripped.startswith("[") and stripped.endswith("]"):
            skipping = False
        if not skipping:
            kept.append(line)
    return "\n".join(line for line in kept if line.strip())


def _project_snapshot_for_planning() -> str:
    try:
        from projects import load_projects
    except Exception:
        return ""

    projects = load_projects()
    if not projects:
        return ""

    ordered = sorted(
        projects,
        key=lambda item: (
            {"active": 0, "paused": 1, "done": 2}.get(item.get("status", "paused"), 9),
            -(int(item.get("completion", 0))),
            -(int((item.get("last_opened") or "0").replace("-", "").replace(":", "").replace("T", "").replace("Z", "")[:14] or "0")),
        ),
    )

    lines = ["[PROJECT SNAPSHOT]"]
    for project in ordered[:3]:
        next_task = str((project.get("next_tasks") or ["none"])[0]).strip() or "none"
        blocker = str((project.get("blockers") or ["none"])[0]).strip() or "none"
        lines.append(
            f"  {project.get('name', 'unknown')}: next={next_task[:64]} | blocker={blocker[:64]}"
        )
    return "\n".join(lines)


def _normalize_path_key(path: str) -> str:
    text = os.path.expanduser(str(path or "")).strip()
    if not text:
        return ""
    return os.path.normpath(text).rstrip("/").lower()


def _project_from_path(path: str, projects: list[dict]) -> dict | None:
    candidate = _normalize_path_key(path)
    if not candidate:
        return None

    best: tuple[int, dict] | None = None
    for project in projects:
        root = _normalize_path_key(project.get("path", ""))
        if not root:
            continue
        if candidate == root or candidate.startswith(root + os.sep):
            score = len(root)
            if best is None or score > best[0]:
                best = (score, project)
    return best[1] if best else None


def _recent_speech_keys(limit: int = 6) -> set[str]:
    try:
        memory = _load_memory()
    except Exception:
        return set()

    history = memory.get("command_history", [])
    recent: set[str] = set()
    for entry in history[-limit:]:
        speech = str(entry.get("speech", "")).strip().lower()
        if speech:
            recent.add(re.sub(r"[^a-z0-9]+", "", speech))
    return recent


def _clip_words(text: str, limit: int = 12) -> str:
    cleaned = " ".join(str(text or "").split()).strip(" .,;:-")
    if not cleaned:
        return ""
    words = cleaned.split()
    if len(words) <= limit:
        return cleaned
    trimmed = words[:limit]
    while trimmed and trimmed[-1].lower() in {"if", "and", "or", "to", "for", "with"}:
        trimmed = trimmed[:-1]
    return " ".join(trimmed).rstrip(",;:-")


def _spoken_task(text: str, limit: int = 8) -> str:
    cleaned = re.sub(r"\([^)]*\)", "", str(text or ""))
    cleaned = cleaned.replace("—", " - ").replace("–", " - ")
    lowered = cleaned.lower()
    for token in (" - ", " if ", " because ", " when ", "; "):
        index = lowered.find(token)
        if index != -1:
            cleaned = cleaned[:index]
            break
    cleaned = " ".join(cleaned.split()).strip(" .,;:-")
    return _clip_words(cleaned, limit)


def _filter_startup_items(items: list[str]) -> list[str]:
    filtered = []
    for item in items:
        cleaned = " ".join(str(item or "").split()).strip()
        if not cleaned:
            continue
        lowered = cleaned.lower()
        if any(pattern in lowered for pattern in _LOW_SIGNAL_STARTUP_PATTERNS):
            continue
        filtered.append(cleaned)
    return filtered


def _meaningful_active_tasks(project_name: str) -> list[str]:
    try:
        tasks = get_active_tasks(project_name)
    except Exception:
        return []

    titles = []
    for task in tasks:
        title = " ".join(str(task.get("title", "")).split()).strip()
        if not title:
            continue
        lowered = title.lower()
        if "test task for audit" in lowered:
            continue
        if any(pattern in lowered for pattern in _LOW_SIGNAL_STARTUP_PATTERNS):
            continue
        titles.append(title)
    return titles


def _maybe_add_info_followup(text: str, agent_name: str) -> str:
    if agent_name not in {"news", "search"}:
        return text
    cleaned = _normalize_response(text, max_words=26)
    if not cleaned:
        return text
    if cleaned.endswith("?"):
        return cleaned
    return _normalize_response(f"{cleaned} Want more?", max_words=30)


def _startup_session_hint() -> str:
    summary = " ".join(str(get_last_session_summary() or "").split())
    if not summary or summary == "No previous session.":
        return ""

    action_match = re.search(r"Did:\s*(.+?)(?:\s+(?:Request|Result):|$)", summary, flags=re.IGNORECASE)
    if action_match:
        action = _clip_words(action_match.group(1).strip().strip('"'), 8)
        if action:
            return f"Last time I {action}."

    request_match = re.search(r'Request:\s*"([^"]+)"', summary, flags=re.IGNORECASE)
    if request_match:
        request = request_match.group(1).strip()
        request = re.sub(
            r"^(?:can you|could you|would you|please|tell me|show me|give me|search for|search|find|look up)\s+",
            "",
            request,
            flags=re.IGNORECASE,
        )
        request = _spoken_task(request, 8)
        if request:
            return f"Last time you asked about {request}."

    result_match = re.search(r"Result:\s*(.+)$", summary, flags=re.IGNORECASE)
    if result_match:
        result = _clip_words(result_match.group(1).strip().strip('"'), 8)
        if result:
            return f"Last result: {result}."

    return ""


def _startup_briefing_sessions(limit: int = 3) -> list[str]:
    summaries: list[str] = []
    for session in memory_store.load_recent_sessions(max(6, limit * 3)):
        context = " ".join(
            str(session.get("context", "") or session.get("context_preview", "")).split()
        ).strip()
        speech = " ".join(str(session.get("speech", "")).split()).strip()
        if context.lower().startswith("startup briefing"):
            continue
        if context and speech:
            summaries.append(f"{context[:90]} -> {speech[:110]}")
        elif context:
            summaries.append(context[:140])
        elif speech:
            summaries.append(speech[:140])
        if len(summaries) >= limit:
            break
    return summaries


def _startup_project_state(ctx: dict) -> tuple[dict | None, bool]:
    return _what_next_project(ctx)


def _build_startup_briefing_prompt(ctx: dict) -> str:
    project, in_workspace = _startup_project_state(ctx)
    sessions = _startup_briefing_sessions(limit=3)
    session_block = "\n".join(f"- {item}" for item in sessions) or "- No recent session summaries."
    if project:
        next_task = " ".join(str((project.get("next_tasks") or ["none"])[0]).split()).strip() or "none"
        blocker = " ".join(str((project.get("blockers") or ["none"])[0]).split()).strip() or "none"
        project_block = (
            f"- name: {project.get('name', 'unknown')}\n"
            f"- status: {project.get('status', 'unknown')} ({int(project.get('completion', 0) or 0)}% complete)\n"
            f"- workspace_match: {'yes' if in_workspace else 'no'}\n"
            f"- next_task: {next_task[:140]}\n"
            f"- blocker: {blocker[:140]}"
        )
    else:
        project_block = "- No active project state available."

    return f"""You are Burry speaking once at the start of a new session.
Write exactly 2 short spoken sentences, total under 40 words.
Sentence 1 should say where things stand from the recent session history.
Sentence 2 should say what the current project needs next.
Do not ask a question. Do not greet. Do not use bullets.

Recent session summaries:
{session_block}

Current project state:
{project_block}
"""


def _two_sentence_briefing(text: str, max_words: int = 40) -> str:
    cleaned = " ".join(str(text or "").strip().strip('"').split())
    if not cleaned:
        return ""

    parts = [part.strip() for part in re.split(r"(?<=[.!?])\s+", cleaned) if part.strip()]
    if not parts:
        return ""
    if len(parts) == 1 and parts[0][-1] not in ".!?":
        parts[0] = parts[0].rstrip(",;:-") + "."
    candidate = " ".join(parts[:2])
    words = candidate.split()
    if len(words) > max_words:
        clipped = " ".join(words[:max_words]).rstrip(",;:-")
        if clipped and clipped[-1] not in ".!?":
            clipped += "."
        candidate = clipped
    return candidate


def _startup_briefing_fallback(ctx: dict) -> str:
    project, _in_workspace = _startup_project_state(ctx)
    if not project:
        return "No strong project signal yet. Say what should I work on when you're ready."

    name = str(project.get("name", "your project")).strip() or "your project"
    next_task = _spoken_task((project.get("next_tasks") or ["review the current status file"])[0], 8)
    blocker = _clip_words(str((project.get("blockers") or [""])[0]).strip(), 7)
    first = f"{name} is still the main thread."
    if blocker:
        second = f"Next up is {next_task}, with {blocker} still in the way."
    else:
        second = f"Next up is {next_task}."
    return _two_sentence_briefing(f"{first} {second}", max_words=40)


def _generate_startup_briefing(ctx: dict) -> str:
    prompt = _build_startup_briefing_prompt(ctx)
    raw = _raw_llm(prompt, model=STARTUP_BRIEFING_MODEL, max_tokens=120, temperature=0.2)
    speech = _two_sentence_briefing(raw, max_words=40)
    if speech.lower().strip() in {"something went wrong.", "i'm still thinking, give me a moment."}:
        return _startup_briefing_fallback(ctx)
    return speech or _startup_briefing_fallback(ctx)


def _what_next_project(ctx: dict) -> tuple[dict | None, bool]:
    try:
        from projects import load_projects
    except Exception:
        return (None, False)

    projects = load_projects()
    if not projects:
        return (None, False)

    workspace_candidates = []
    mac_state = load_mac_state()
    workspace = str(mac_state.get("cursor_workspace", "")).strip()
    if workspace:
        workspace_candidates.append(workspace)
    workspace_candidates.extend(ctx.get("raw", {}).get("editor", {}).get("workspace_paths", []) or [])
    remembered = _get_last_project()
    if remembered:
        workspace_candidates.append(remembered)

    for candidate in workspace_candidates:
        project = _project_from_path(candidate, projects)
        if project:
            return (project, True)

    ordered = sorted(
        projects,
        key=lambda item: (
            {"active": 0, "paused": 1, "done": 2}.get(item.get("status", "paused"), 9),
            -int(item.get("completion", 0)),
            str(item.get("last_opened", "")),
        ),
        reverse=False,
    )
    return (ordered[0], False) if ordered else (None, False)


def _deterministic_project_plan(ctx: dict, *, startup: bool = False) -> dict | None:
    project, in_workspace = _what_next_project(ctx)
    if not project:
        return None

    name = str(project.get("name", "")).strip() or "your current project"
    task_titles = _meaningful_active_tasks(name)
    next_tasks = _filter_startup_items(
        task_titles or [str(item).strip() for item in (project.get("next_tasks") or []) if str(item).strip()]
    )
    blockers = _filter_startup_items([str(item).strip() for item in (project.get("blockers") or []) if str(item).strip()])

    first_task = _spoken_task(next_tasks[0] if next_tasks else "review the current status file", 8)
    raw_second_task = str(next_tasks[1]).strip() if len(next_tasks) > 1 else ""
    second_task = _spoken_task(raw_second_task, 5) if raw_second_task and len(raw_second_task.split()) <= 5 else ""
    raw_blocker = str(blockers[0]).strip() if blockers else ""
    blocker = _clip_words(raw_blocker, 7) if raw_blocker and len(raw_blocker.split()) <= 7 else ""
    session_hint = _startup_session_hint() if startup else ""

    lead = f"You're already in {name}" if in_workspace else f"{name} is the clearest next move"
    task_clause = f"Start with {first_task}."
    if second_task and second_task.lower() != first_task.lower() and len(f"{first_task} {second_task}".split()) <= 12:
        task_clause = f"Start with {first_task}, then {second_task}."

    question = (
        "Say recap, tasks, or news."
        if startup
        else (
            "Want the first step?"
            if in_workspace
            else "Want me to open it or map the first step?"
        )
    )

    variants = []
    if session_hint:
        variants.append(f"{lead}. {session_hint} {task_clause} {question}")
    if blocker and len(blocker.split()) <= 7:
        variants.append(f"{lead}. Biggest blocker is {blocker}. {task_clause} {question}")
    variants.append(f"{lead}. {task_clause} {question}")
    variants.append(f"{lead}. Next move is {first_task}. {question}")

    recent = _recent_speech_keys()
    chosen = variants[0]
    for variant in variants:
        key = re.sub(r"[^a-z0-9]+", "", variant.lower())
        if key not in recent:
            chosen = variant
            break

    speech = _normalize_response(chosen, max_words=45)
    return {
        "speech": speech,
        "spoken_text": speech,
        "actions": [],
        "focus": name,
        "why_now": first_task,
        "greeting": "",
    }


def _question_needs_brain_agents(text: str) -> bool:
    lowered = text.lower()
    if any(
        trigger in lowered
        for trigger in (
            "hackernews",
            "hacker news",
            "reddit",
            "market pulse",
            "trending repos",
            "trending repositories",
            "github",
            "pull request",
            "pr ",
            "issue",
            "repo",
            "vps",
            "server",
            "docker",
            "container",
        )
    ):
        return True
    decision = analyze_query(text, conversation=_conversation_context_text())
    return decision["action"] in {"news", "search", "fetch"} and float(decision.get("confidence", 0.0)) >= 0.7


def _extract_news_topic(text: str) -> str:
    lowered = text.lower()
    lowered = lowered.replace("a i", "ai")
    lowered = lowered.replace("air news", "ai news")

    if "tech news" in lowered:
        return "tech"
    if re.search(r"\bai\b.*\bnews\b", lowered) or re.search(r"\bnews\b.*\bai\b", lowered):
        return "AI"

    candidate = re.sub(
        r"\b(you know|checking|check|tell me|show me|give me|can you|could you|would you|please|but|what is|what's|latest|recent|news|about|the)\b",
        " ",
        lowered,
    )
    candidate = re.sub(r"\s+", " ", candidate).strip(" .")
    candidate = re.sub(r"^(?:on|for|regarding)\s+", "", candidate).strip()
    if candidate in {"", "ai", "air"}:
        return "AI and tech news"
    return candidate


def _direct_agent_plan_for_text(text: str) -> dict | None:
    lowered = text.lower().strip().rstrip("?")

    if any(token in lowered for token in ("what's happening in ai", "whats happening in ai", "market pulse")):
        return {
            "speech": "Checking the AI market pulse.",
            "actions": [{"type": "run_agent", "agent": "market", "topics": ["AI agents", "LLMs", "open source"]}],
        }

    if any(token in lowered for token in ("hackernews", "hacker news")):
        return {
            "speech": "Checking Hacker News.",
            "actions": [{"type": "run_agent", "agent": "hackernews", "limit": 10}],
        }

    if any(token in lowered for token in ("reddit saying", "reddit buzz", "what's reddit", "whats reddit", "reddit")):
        return {
            "speech": "Checking Reddit.",
            "actions": [
                {
                    "type": "run_agent",
                    "agent": "reddit",
                    "subreddits": ["MachineLearning", "LocalLLaMA", "programming"],
                    "limit": 5,
                }
            ],
        }

    if any(token in lowered for token in ("trending repos", "trending repositories", "github trending")):
        return {
            "speech": "Checking trending repos.",
            "actions": [{"type": "run_agent", "agent": "github_trending", "language": "python", "since": "daily"}],
        }

    if "tech news" in lowered:
        return {
            "speech": "Checking the latest tech news.",
            "actions": [{"type": "run_agent", "agent": "news", "topic": "tech"}],
        }

    if any(token in lowered for token in ("latest", "news", "recent")):
        topic = _extract_news_topic(lowered)
        spoken_topic = "AI news" if topic == "AI" else f"{topic} news" if topic != "AI and tech news" else "AI and tech news"
        return {
            "speech": f"Checking the latest {spoken_topic}.",
            "actions": [{"type": "run_agent", "agent": "news", "topic": topic}],
        }

    if any(token in lowered for token in ("vps", "server", "docker", "container")):
        host = _default_vps_host()
        action = {"type": "run_agent", "agent": "vps"}
        if host:
            action["host"] = host
        return {
            "speech": "Checking the VPS and containers.",
            "actions": [action],
        }

    decision = analyze_query(text, conversation=_conversation_context_text())

    if decision["action"] == "fetch":
        url_match = re.search(
            r"(https?://[^\s]+|www\.[^\s]+|\b[a-z0-9.-]+\.(?:com|org|net|io|ai|dev|app|co|in)\b)",
            text,
            flags=re.IGNORECASE,
        )
        url = url_match.group(1) if url_match else ""
        return {
            "speech": "Reading that page.",
            "actions": [{"type": "run_agent", "agent": "fetch", "query": text, "url": url}],
        }

    if decision["action"] == "news":
        topic = _extract_news_topic(lowered)
        spoken_topic = "AI news" if topic == "AI" else f"{topic} news" if topic != "AI and tech news" else "AI and tech news"
        return {
            "speech": f"Checking the latest {spoken_topic}.",
            "actions": [{"type": "run_agent", "agent": "news", "topic": topic}],
        }

    if decision["action"] == "search":
        query = text.strip().rstrip("?")
        return {
            "speech": "Looking that up.",
            "actions": [{"type": "run_agent", "agent": "search", "query": query}],
        }

    return None


def _plan_with_brain(context_text: str, model: str | None = None) -> dict:

    fallback = {
        "speech": "Back on mac-butler. Want to jump in?",
        "spoken_text": "Back on mac-butler. Want to jump in?",
        "actions": [],
        "focus": "",
        "why_now": "",
        "greeting": "",
    }

    try:
        raw = ollama_client.send_to_ollama(context_text, model=model)
        data = json.loads(raw) if isinstance(raw, str) else {}
    except Exception:
        return fallback

    speech = _normalize_response(str(data.get("speech", "")).strip(), max_words=40)
    actions = data.get("actions", [])
    if not isinstance(actions, list):
        actions = []

    plan = {
        "speech": speech or fallback["speech"],
        "spoken_text": speech or fallback["spoken_text"],
        "actions": [action for action in actions[:2] if isinstance(action, dict)],
        "focus": str(data.get("focus", "")).strip(),
        "why_now": str(data.get("why_now", "")).strip(),
        "greeting": str(data.get("greeting", "")).strip(),
    }
    return plan


def _run_actions_with_response(
    *,
    text: str,
    response: str,
    actions: list[dict],
    intent_name: str = "",
    test_mode: bool = False,
    model: str | None = None,
    learning_meta: dict | None = None,
) -> tuple[str, list]:
    prepared_actions = []
    for action in actions:
        current = dict(action)
        if current.get("type") == "run_agent" and current.get("agent") == "vps" and not current.get("host"):
            host = _default_vps_host()
            if host:
                current["host"] = host
        if current.get("type") == "ssh_open" and not current.get("host"):
            host = _default_vps_host()
            if host:
                current["host"] = host
        prepared_actions.append(current)
    actions = prepared_actions
    run_agent_only = bool(actions) and all(action.get("type") == "run_agent" for action in actions)

    def _queue_background_agent(action: dict) -> dict:
        try:
            from agents.runner import run_agent_async

            agent_name = str(action.get("agent", "")).strip()
            run_agent_async(
                agent_name,
                {k: v for k, v in action.items() if k not in ("type", "agent")},
            )
            agent_name = str(action.get("agent", "")).strip() or "agent"
            return {
                "action": "run_agent",
                "status": "queued",
                "result": f"{agent_name} running in background",
            }
        except Exception as exc:
            return {
                "action": "run_agent",
                "status": "error",
                "error": str(exc),
                "result": "",
            }

    for action in actions:
        print(f"[Executor] before run: {action}")
    if test_mode:
        if run_agent_only:
            results = executor.run(actions)
            print(f"[Executor] after run: {results}")
            first_error = next(
                (
                    str(result.get("error", "")).strip()
                    for result in results
                    if result.get("status") == "error" and str(result.get("error", "")).strip()
                ),
                "",
            )
            agent_summaries = [
                str(result.get("result", "")).strip()
                for result in results
                if result.get("status") == "ok" and str(result.get("result", "")).strip()
            ]
            final_response = first_error or (agent_summaries[0] if agent_summaries else response)
            print(f"[Butler]: {final_response}")
            _remember_conversation_turn(text, intent_name or "action", final_response)
            state.transition(State.IDLE)
            return final_response, results

        print("[Executor] after run: done (test mode)")
        print(f"[Butler]: {response}")
        _remember_conversation_turn(text, intent_name or "action", response)
        state.transition(State.IDLE)
        return response, []

    queued_agent_results: dict[int, dict] = {}
    sync_actions: list[dict] = []
    sync_indexes: list[int] = []
    for index, action in enumerate(actions):
        if action.get("type") == "run_agent":
            queued_agent_results[index] = _queue_background_agent(action)
        else:
            sync_actions.append(action)
            sync_indexes.append(index)

    should_delay_speech = _should_delay_speech_for_actions(sync_actions)
    speaker_thread = None
    if response and queued_agent_results:
        _speak_or_print(response, test_mode=False)
    elif response and not should_delay_speech:
        speaker_thread = threading.Thread(
            target=speak,
            args=(response,),
            daemon=True,
        )
        speaker_thread.start()

    for action in sync_actions:
        note_tool_started(_action_trace_name(action), _action_trace_detail(action))

    try:
        sync_results = executor.run(sync_actions) if sync_actions else []
    except Exception as exc:
        for action in sync_actions:
            note_tool_finished(_action_trace_name(action), "error", str(exc)[:180])
        raise

    for action, result in zip(sync_actions, sync_results):
        status = str(result.get("status", "ok") or "ok").strip().lower() if isinstance(result, dict) else "ok"
        note_tool_finished(
            _action_trace_name(action),
            status or "ok",
            _action_trace_result_detail(result, _action_trace_detail(action)),
        )
    results: list[dict] = []
    sync_cursor = 0
    for index, _action in enumerate(actions):
        if index in queued_agent_results:
            results.append(queued_agent_results[index])
        else:
            results.append(sync_results[sync_cursor])
            sync_cursor += 1
    print(f"[Executor] after run: {results}")

    final_response = response
    first_error = next(
        (
            str(result.get("error", "")).strip()
            for result in results
            if result.get("status") == "error" and str(result.get("error", "")).strip()
        ),
        "",
    )
    if queued_agent_results and not sync_actions and not first_error:
        _record(
            text,
            final_response,
            actions,
            results=results,
            intent_name=intent_name or "action",
            learning_meta=learning_meta,
        )
        state.transition(State.WAITING)
        return final_response, results

    if first_error:
        final_response = _normalize_response(first_error, max_words=18, single_sentence=True) or "That failed."
    else:
        successful_agent_results = _successful_agent_results(results)
        direct_agent_response = _normalize_response(
            successful_agent_results[0] if successful_agent_results else "",
            max_words=45,
        )
        if run_agent_only and direct_agent_response:
            final_response = _maybe_add_info_followup(
                direct_agent_response,
                str(actions[0].get("agent", "")).strip().lower() if actions else "",
            )
        else:
            rewritten = _rewrite_speech_with_agent_results(response, results, model=model)
            if rewritten:
                final_response = rewritten

    if should_delay_speech:
        if final_response:
            _speak_or_print(final_response, test_mode=False)
    else:
        if first_error:
            if speaker_thread and speaker_thread.is_alive():
                speaker_thread.join(timeout=5)
            speak(final_response)
        else:
            observation = observe_and_followup(
                {"speech": response},
                results,
                test_mode=test_mode,
                model=model,
            )
            if observation:
                final_response = _normalize_response(
                    f"{response} {observation}",
                    max_words=45,
                )
                if speaker_thread and speaker_thread.is_alive():
                    speaker_thread.join(timeout=5)
                speak(observation)

    if speaker_thread and speaker_thread.is_alive():
        speaker_thread.join(timeout=10)

    _record(
        text,
        final_response,
        actions,
        results=results,
        intent_name=intent_name or "action",
        learning_meta=learning_meta,
    )
    state.transition(State.WAITING)
    return final_response, results


def get_quick_response(intent: IntentResult) -> str:
    if hasattr(intent, "quick_response"):
        return intent.quick_response()
    template = QUICK_RESPONSES.get(intent.intent, "")
    if not template:
        return ""
    try:
        return template.format(**intent.params)
    except Exception:
        return template


def _ensure_watcher_started() -> None:
    global _WATCHER_STARTED
    with _WATCHER_LOCK:
        if _WATCHER_STARTED:
            return
        start_watcher(interval=30)
        _WATCHER_STARTED = True


def _report_brain_backend_status() -> None:
    global _BRAIN_STATUS_CHECKED
    if _BRAIN_STATUS_CHECKED:
        return
    _BRAIN_STATUS_CHECKED = True
    try:

        conn = check_vps_connection()
        if conn["status"] == "ok":
            print(
                f"[Brain] Backend: {conn['backend']} | "
                f"Models: {', '.join(conn['models'][:3])}"
            )
        else:
            print(f"[Brain] WARNING: {conn['error']}")
    except Exception as exc:
        print(f"[Brain] WARNING: {exc}")


def _raw_llm(prompt: str, model: str | None = None, max_tokens: int = 80, temperature: float = 0.4) -> str:
    try:
        payload = chat_with_ollama(
            [{"role": "user", "content": prompt}],
            model or OLLAMA_MODEL,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        message = payload.get("message") if isinstance(payload, dict) else {}
        return str((message or {}).get("content", "") or "").strip()
    except Exception:
        return "Something went wrong."


def _normalize_response(text: str, max_words: int = 40, single_sentence: bool = False) -> str:
    cleaned = " ".join((text or "").strip().strip('"').split())
    if not cleaned:
        return ""

    if single_sentence:
        parts = re.split(r"(?<=[.!?])\s+", cleaned, maxsplit=1)
        cleaned = parts[0]

    words = cleaned.split()
    if len(words) > max_words:
        cleaned = " ".join(words[:max_words]).rstrip(",;:-")
        if cleaned and cleaned[-1] not in ".!?":
            cleaned += "."
    return cleaned


def _get_last_project() -> str:
    try:
        data = _load_memory()
        history = data.get("command_history", [])
        for session in reversed(history[-10:]):
            for action in session.get("actions", []):
                if action.get("type") in {"open_folder", "create_and_open", "open_editor"}:
                    return action.get("path", "")
    except Exception as _e:
        print(f"[Butler] silent error: {_e}")
    return ""


def _default_vps_host() -> str:
    if VPS_HOSTS:
        return VPS_HOSTS[0].get("host", "")
    return ""


def _first_workspace_path(ctx: dict) -> str:
    editor = ctx.get("raw", {}).get("editor", {})
    for path in editor.get("workspace_paths", []) or []:
        return path
    return ""


def _project_path_from_text(text: str) -> str:
    lowered = text.lower()
    for project, path in get_project_map().items():
        if project in lowered:
            return path
    return ""


def _editor_key(value: str) -> str:
    lowered = str(value or "").lower()
    if "visual studio code" in lowered or lowered in {"vscode", "code"}:
        return "vscode"
    if "cursor" in lowered:
        return "cursor"
    return ""


def _preferred_editor(ctx: dict, project_path: str = "") -> str:
    current_app = ctx.get("raw", {}).get("editor", {}).get("app_name", "")
    current = _editor_key(current_app)
    if current:
        return current

    project_name = Path(os.path.expanduser(project_path)).name if project_path else ""
    if project_name:
        try:
            memory = _load_memory()
            state = memory.get("project_state", {}).get(project_name, {})
            remembered = _editor_key(state.get("last_editor", ""))
            if remembered:
                return remembered
        except Exception as _e:
            print(f"[Butler] silent error: {_e}")

    return "auto"


def _contextualize_action(action: dict | None, intent: IntentResult, ctx: dict) -> dict | None:
    if action is None:
        return None

    workspace_path = _first_workspace_path(ctx)
    project_path = _project_path_from_text(intent.raw)
    working_path = project_path or workspace_path or "~/Developer"
    preferred_editor = _preferred_editor(ctx, project_path or workspace_path)

    if action.get("type") in {"create_file_in_editor", "open_editor"}:
        editor_value = str(action.get("editor", "")).strip().lower()
        if editor_value in {"", "auto"} and preferred_editor != "auto":
            action["editor"] = preferred_editor

    if action.get("type") == "create_file_in_editor":
        action.setdefault("directory", project_path or workspace_path or "~/Developer")

    if action.get("type") == "open_terminal":
        if action.get("cwd") in {None, "", ".", "~"}:
            action["cwd"] = working_path

    if action.get("type") == "open_editor":
        if not action.get("path") and project_path:
            action["path"] = project_path

    if action.get("type") == "open_project" and not action.get("name"):
        guessed_project = intent.params.get("name") or intent.params.get("project")
        if guessed_project:
            action["name"] = guessed_project

    if action.get("type") == "run_command":
        if action.get("cwd") in {None, "", ".", "~"}:
            action["cwd"] = working_path

    if action.get("type") == "create_folder" and action.get("path") == "~/Developer/new-folder":
        action["path"] = f"{working_path.rstrip('/')}/new-folder"

    if action.get("type") == "zip_folder" and not action.get("path"):
        action["path"] = working_path

    if action.get("type") in {"run_agent", "ssh_open"} and not action.get("host"):
        host = _default_vps_host()
        if host:
            action["host"] = host

    if intent.intent == "docker_status" and _default_vps_host():
        action = {"type": "run_agent", "agent": "vps", "host": _default_vps_host()}

    return action


# _FAST_INTERRUPT_INTENTS is now superseded by INSTANT_LANE_INTENTS
_FAST_INTERRUPT_INTENTS = INSTANT_LANE_INTENTS

_CONTEXT_HEAVY_ACTION_TYPES = {
    "create_file_in_editor",
    "open_editor",
    "open_terminal",
    "run_command",
    "create_folder",
    "zip_folder",
}

_DELAYED_SPEECH_ACTION_TYPES = {
    "open_app",
    "quit_app",
    "open_project",
    "open_editor",
    "create_file_in_editor",
    "create_folder",
    "open_terminal",
    "open_url",
    "open_url_in_browser",
    "browser_new_tab",
    "browser_search",
    "browser_close_tab",
    "browser_close_window",
    "focus_app",
    "minimize_app",
    "lock_screen",
    "volume_up",
    "volume_down",
    "volume_mute",
    "system_volume",
    "volume_set",
    "clipboard_read",
    "clipboard_write",
    "dark_mode_toggle",
    "obsidian_note",
}


def _intent_can_preempt_busy_work(intent: IntentResult) -> bool:
    return str(getattr(intent, "name", "") or "").strip() in _FAST_INTERRUPT_INTENTS


def _action_needs_runtime_context(action: dict | None) -> bool:
    if not isinstance(action, dict):
        return False
    return str(action.get("type", "") or "").strip() in _CONTEXT_HEAVY_ACTION_TYPES


def _action_trace_name(action: dict) -> str:
    return str(action.get("type", "") or "action").strip() or "action"


def _action_trace_detail(action: dict) -> str:
    keys = ("app", "name", "url", "cmd", "command", "filename", "path", "cwd", "query", "title", "message")
    for key in keys:
        value = " ".join(str(action.get(key, "") or "").split()).strip()
        if value:
            return value[:180]
    return _action_trace_name(action)


def _action_trace_result_detail(result: dict, fallback: str = "") -> str:
    if not isinstance(result, dict):
        return fallback
    for key in ("verification_detail", "result", "error"):
        value = " ".join(str(result.get(key, "") or "").split()).strip()
        if value:
            return value[:180]
    status = " ".join(str(result.get("status", "") or "").split()).strip().lower()
    return fallback or status or "done"


def _should_delay_speech_for_actions(actions: list[dict]) -> bool:
    action_types = [
        str(action.get("type", "") or "").strip()
        for action in list(actions or [])
        if isinstance(action, dict)
    ]
    return bool(action_types) and all(action_type in _DELAYED_SPEECH_ACTION_TYPES for action_type in action_types)


def _summarize_result(result_text: str, model: str | None = None) -> str:
    if not result_text or len(result_text.strip()) < 10:
        return ""
    summary = _quick_summarize(result_text, model=model)
    return _normalize_response(summary, max_words=18, single_sentence=True)


def _quick_summarize(text: str, model: str | None = None) -> str:
    return _raw_llm(
        f"Summarize in ONE sentence under 12 words: {text[:200]}",
        model=model or BUTLER_MODELS.get("review") or OLLAMA_FALLBACK or OLLAMA_MODEL,
        max_tokens=40,
    )


def _speak_or_print(text: str, test_mode: bool = False) -> None:
    pipeline_speech.speak_or_print(text, test_mode=test_mode, speak_fn=speak, notify_fn=notify)


def _speak_stream_chunk(text: str) -> None:
    pipeline_speech.speak_stream_chunk(text, speak_fn=speak)


_stream_response_with_tts = pipeline_speech.stream_response_with_tts
_stream_sentences_with_tts = pipeline_speech.stream_sentences_with_tts
_stream_chat_response_with_tts = pipeline_speech.stream_chat_response_with_tts


def _wait_for_runtime_confirmation(prompt: str, action: str, timeout_s: int = 30) -> bool:
    pending = request_confirmation(prompt, action=action, timeout_s=timeout_s)
    deadline = time.monotonic() + max(1, timeout_s)
    while time.monotonic() < deadline:
        runtime_state = load_runtime_state()
        current = runtime_state.get("pending_confirmation", {}) if isinstance(runtime_state, dict) else {}
        if current.get("id") != pending.get("id"):
            time.sleep(0.25)
            continue
        status = str(current.get("status", "")).strip().lower()
        if status == "approved":
            clear_confirmation(pending["id"])
            return True
        if status == "rejected":
            clear_confirmation(pending["id"])
            return False
        time.sleep(0.25)
    resolve_confirmation(pending["id"], "timeout")
    clear_confirmation(pending["id"])
    return False


def _get_cached_context() -> dict:
    """Return cached build_structured_context(). Rebuilds every 120 seconds."""
    global _CTX_CACHE, _CTX_CACHE_AT
    now = time.monotonic()
    with _CTX_CACHE_LOCK:
        if _CTX_CACHE is not None and now - _CTX_CACHE_AT < _CTX_CACHE_TTL_SECONDS:
            return _CTX_CACHE
        # Build inside the lock to prevent duplicate work from concurrent threads
        ctx = build_structured_context()
        _CTX_CACHE = ctx
        _CTX_CACHE_AT = time.monotonic()
    return ctx


def _get_fast_context() -> dict:
    """B3: Return a fast 3-source context (app + time + memory) for the smart reply lane.
    No git, VSCode, Obsidian, VPS, MCP — no subprocesses or network calls.
    """
    return build_structured_context(fast=True)


def _get_structured_context() -> dict:
    return _get_cached_context()


def _invalidate_context_cache() -> None:
    global _CTX_CACHE, _CTX_CACHE_AT
    with _CTX_CACHE_LOCK:
        _CTX_CACHE = None
        _CTX_CACHE_AT = 0.0


def _process_next_queued_command() -> None:
    """Drain one item from the command queue if available."""
    try:
        queued_text = _COMMAND_QUEUE.get_nowait()
    except queue.Empty:
        return
    threading.Thread(target=handle_input, args=(queued_text,), daemon=True).start()


def run_startup_briefing(test_mode: bool = False, model: str | None = None) -> None:
    global _briefing_done
    _ensure_watcher_started()
    _report_brain_backend_status()
    if _briefing_done:
        return
    if state.is_busy:
        return
    _briefing_done = True

    state.transition(State.THINKING)
    ctx = _get_cached_context()
    speech = _generate_startup_briefing(ctx)
    _speak_or_print(speech, test_mode=test_mode)
    _record(
        "startup briefing",
        speech,
        [],
        intent_name="briefing",
        learning_meta={"task_type": "briefing", "model": STARTUP_BRIEFING_MODEL},
    )
    state.transition(State.WAITING if not test_mode else State.IDLE)


def _startup_intelligence_line() -> str:
    try:
        from agents.runner import run_agent
    except Exception:
        return ""

    try:
        result = run_agent("hackernews", {"limit": 3})
    except Exception:
        return ""

    items = result.get("data", {}).get("items", []) if isinstance(result, dict) else []
    titles = [str(item.get("title", "")).strip() for item in items[:3] if str(item.get("title", "")).strip()]
    if not titles:
        return ""
    clipped = ", ".join(title[:56].rstrip(" .,;:-") for title in titles)
    return f"Top on HN: {clipped}."


handle_command = handle_input


def reset_live_session_state(source: str = "voice_startup") -> None:
    global _SESSION_STATE_SAVED, _briefing_done
    try:
        configure_session_restore(enabled=False)
    except Exception as exc:
        print(f"[Butler] session restore config failed: {exc}")
    try:
        reset_backbone_session()
    except Exception as exc:
        print(f"[Butler] backbone reset failed: {exc}")
    try:
        reset_runtime_state(reason=source, preserve_workspace=True, preserve_metrics=True)
    except Exception as exc:
        print(f"[Butler] runtime reset failed: {exc}")
    _clear_pending_command_state()
    reset_conversation_context()
    state.reset()
    _briefing_done = False
    _SESSION_STATE_SAVED = False


def _on_state_change(old_state: State, new_state: State) -> None:
    """Drain queued commands when butler becomes free."""
    busy = {State.THINKING, State.SPEAKING}
    if old_state in busy and new_state not in busy:
        _process_next_queued_command()


state.on_change(_on_state_change)


def _acquire_live_runtime_lock() -> bool:
    global _LIVE_RUNTIME_LOCK_HANDLE
    if _LIVE_RUNTIME_LOCK_HANDLE is not None:
        return True

    _LIVE_RUNTIME_LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    handle = _LIVE_RUNTIME_LOCK_PATH.open("a+", encoding="utf-8")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        try:
            handle.seek(0)
            owner = handle.read().strip()
        except Exception:
            owner = ""
        handle.close()
        owner_note = f" (pid {owner})" if owner else ""
        print(f"[Butler] Another live runtime is already active{owner_note}. Reuse it instead of starting a second voice session.")
        return False

    handle.seek(0)
    handle.truncate()
    handle.write(str(os.getpid()))
    handle.flush()
    _LIVE_RUNTIME_LOCK_HANDLE = handle
    return True


def _release_live_runtime_lock() -> None:
    global _LIVE_RUNTIME_LOCK_HANDLE
    handle = _LIVE_RUNTIME_LOCK_HANDLE
    _LIVE_RUNTIME_LOCK_HANDLE = None
    if handle is None:
        return
    try:
        handle.seek(0)
        handle.truncate()
        handle.flush()
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    except Exception:
        pass
    try:
        handle.close()
    except Exception:
        pass


def run_passive_service(
    model: str | None = None,
    test_mode: bool = False,
    *,
    enable_wake: bool = True,
) -> None:
    _ensure_watcher_started()
    try:
        from trigger import shutdown as shutdown_triggers
        from trigger import start_passive_triggers
    except Exception as exc:
        print(f"[Butler] Passive standby unavailable: {exc}")
        return

    status = start_passive_triggers(enable_clap=True, enable_wake=enable_wake)
    note_runtime_event(
        "standby",
        "Passive standby active. Waiting for a clap or explicit command."
        if not enable_wake
        else "Passive standby active. Waiting for a clap, wake phrase, or explicit command.",
        {"triggers": status, "mode": "passive"},
    )

    print("\n" + "=" * 50)
    print("  🎩 Mac Butler — Passive Standby")
    print("=" * 50)
    print("Backend is live on http://127.0.0.1:3335")
    print("Voice stays quiet until an explicit wake event.")
    if enable_wake:
        print("Wake paths: clap, wake phrase, or HUD/API command.\n")
    else:
        print("Wake paths: clap or HUD/API command.\n")

    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        try:
            shutdown_triggers()
        except Exception:
            pass
        state.transition(State.IDLE)
        if not test_mode:
            print("\n[Butler] Passive standby stopped.")


def run_interactive(use_stt: bool = False, model: str | None = None, test_mode: bool = False) -> None:
    _ensure_watcher_started()
    print("\n" + "=" * 50)
    print("  🎩 Mac Butler — Interactive Mode")
    print("=" * 50)
    print("Type commands or press Ctrl+C to exit")
    print("Examples: play mockingbird, open cursor, note: test this, check vps\n")

    try:
        note_session_active(True, source="butler")
        run_startup_briefing(test_mode=test_mode, model=model)

        if use_stt:
            stop_event = threading.Event()
            try:
                listen_continuous(
                    lambda heard: handle_command(heard, test_mode=test_mode, model=model),
                    stop_event,
                )
            except KeyboardInterrupt:
                stop_event.set()
                state.transition(State.IDLE)
            return

        while True:
            user_input = input("\n[You] ").strip()
            if user_input.lower() in {"exit", "quit", "bye"}:
                break
            if user_input:
                handle_command(user_input, test_mode=test_mode, model=model)
    except (KeyboardInterrupt, EOFError):
        pass
    finally:
        note_session_active(False, source="butler")
        state.transition(State.IDLE)
        print("\n[Butler] Goodbye.")


def _save_backbone_session_state() -> None:
    global _SESSION_STATE_SAVED
    if _SESSION_STATE_SAVED:
        return
    try:
        from memory.long_term import save_session_state

        backbone = get_backbone()
        if getattr(backbone, "agent", None) is not None:
            save_session_state(backbone.agent)
            _SESSION_STATE_SAVED = True
    except Exception as _e:
        print(f"[Butler] silent error: {_e}")


def _shutdown_handler(signum=None, frame=None) -> None:
    """Clean shutdown - save AgentScope session state before exit."""
    global _SESSION_STATE_SAVED
    if _SESSION_STATE_SAVED:
        _release_live_runtime_lock()
        if signum is not None:
            raise SystemExit(0)
        return
    print("[Butler] Shutting down - saving session state...")
    try:
        from memory.long_term import save_session_state
        from runtime.tracing import shutdown_tracing

        backbone = get_backbone()
        if backbone and hasattr(backbone, "agent") and backbone.agent:
            save_session_state(backbone.agent)
            _SESSION_STATE_SAVED = True
            print("[Butler] Session state saved.")
        shutdown_tracing()
    except Exception as exc:
        print(f"[Butler] Could not save session state: {exc}")
    finally:
        _release_live_runtime_lock()
    if signum is not None:
        raise SystemExit(0)


def _install_shutdown_handlers() -> None:
    global _SHUTDOWN_HANDLERS_INSTALLED
    if _SHUTDOWN_HANDLERS_INSTALLED:
        return
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _shutdown_handler)
        except Exception:
            continue
    atexit.register(_shutdown_handler)
    _SHUTDOWN_HANDLERS_INSTALLED = True


def main() -> None:
    _install_shutdown_handlers()
    parser = argparse.ArgumentParser(description="Mac Butler")
    parser.add_argument("--test", action="store_true", help="Print-only, no voice or execution")
    parser.add_argument("--model", default=None, help="Override Ollama model")
    parser.add_argument("--interactive", "-i", action="store_true", help="Interactive command mode")
    parser.add_argument("--stt", action="store_true", help="Use voice STT input")
    parser.add_argument("--briefing", action="store_true", help="Run startup briefing only")
    parser.add_argument("--command", "-c", default=None, help="Run a single command")
    parser.add_argument("--clap-only", action="store_true", help="Passive standby wakes only on clap or explicit HUD/API command")
    args = parser.parse_args()
    default_standby_mode = not args.command and not args.interactive and not args.briefing

    lightweight_command_mode = bool(args.command and not args.interactive and not args.stt and not args.briefing)

    if lightweight_command_mode:
        try:
            from skills import load_skills

            load_skills()
        except Exception as _e:
            print(f"[Butler] silent error: {_e}")
    else:
        configure_session_restore(enabled=False)
        _ensure_watcher_started()
        start_ambient_daemon()
        # Start iMessage channel so you can message Burry from iPhone (STEAL 8)
        try:
            from channels.imessage_channel import start_imessage_channel

            start_imessage_channel()
        except Exception as _e:
            print(f"[Butler] silent error: {_e}")
        # Load skills at startup (STEAL 4)
        try:
            from skills import load_skills

            load_skills()
        except Exception as _e:
            print(f"[Butler] silent error: {_e}")
        # Load configured MCP servers into toolkit (Phase 2)
        try:
            from brain.mcp_client import load_configured_mcp_servers

            load_configured_mcp_servers(get_toolkit())
        except Exception as _e:
            print(f"[Butler] silent error: {_e}")
        # Start A2A server — prefer AgentScope native A2A when available.
        try:
            from channels.a2a_server import start_agentscope_a2a

            backbone = get_backbone(model_name=args.model)
            start_agentscope_a2a(backbone.agent)
        except Exception as _e:
            print(f"[Butler] silent error: {_e}")
        _report_brain_backend_status()

    if args.command:
        reset_live_session_state("single_command")
        ctx.reset()
        handle_command(args.command, test_mode=args.test, model=args.model)
        _save_backbone_session_state()
        return

    requires_live_runtime_lock = bool(default_standby_mode or args.interactive or args.briefing)
    if requires_live_runtime_lock and not _acquire_live_runtime_lock():
        return

    if args.interactive:
        reset_live_session_state("interactive")
        run_interactive(use_stt=args.stt, model=args.model, test_mode=args.test)
        _save_backbone_session_state()
        return

    if args.briefing:
        reset_live_session_state("briefing_only")
        run_startup_briefing(test_mode=args.test, model=args.model)
        _save_backbone_session_state()
        return

    if default_standby_mode:
        reset_live_session_state("default_standby")
        run_passive_service(model=args.model, test_mode=args.test, enable_wake=not args.clap_only)
        _save_backbone_session_state()
        return


if __name__ == "__main__":
    main()
