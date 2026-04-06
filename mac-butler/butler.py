#!/usr/bin/env python3
"""
butler.py
Mac Butler Orchestrator v4
Pipeline: Trigger -> STT -> Intent Router -> Executor -> LLM only if needed -> TTS
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import queue
import random
import re
import signal
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

import requests

from butler_config import (
    BUTLER_MODELS,
    DAILY_INTEL_ENABLED,
    OLLAMA_FALLBACK,
    OLLAMA_LOCAL_URL,
    OLLAMA_MODEL,
    SEARXNG_URL,
    VPS_HOSTS,
)
from daemon.ambient import start_ambient_daemon
from daemon.wake_word import start_wake_word_daemon
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
    is_ambiguous_song_query,
    route,
)
from memory.layered import append_to_index, save_project_detail, save_session
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
    note_tool_finished,
    note_tool_started,
    request_confirmation,
    resolve_confirmation,
)
from state import State, state
from tasks import get_active_tasks
from voice import listen_continuous, speak
from runtime.tracing import add_event, trace_command

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
        from brain.agentscope_backbone import interrupt_agentscope_turn

        interrupt_agentscope_turn(new_command)
    except Exception:
        pass
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
_PENDING_DIALOGUE_LOCK = threading.Lock()
_PENDING_DIALOGUE: dict | None = None
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
_CTX_CACHE_TTL_SECONDS: float = 30.0
_CTX_CACHE_LOCK = threading.Lock()
_SHUTDOWN_HANDLERS_INSTALLED = False
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
)
FAST_PATH_INTENTS = {"greeting", "question", "unknown", "chitchat"}
FAST_PATH_CONFIDENCE = 0.8


class ConversationContext:
    def __init__(self) -> None:
        self.turns: list[dict] = []
        self.last_spoken = ""
        self.last_intent = ""
        self.last_heard = ""
        self._restore_from_runtime()

    def _restore_from_runtime(self) -> None:
        try:
            turns = list(load_runtime_state().get("turns") or [])
        except Exception:
            turns = []
        for turn in turns[-6:]:
            if not isinstance(turn, dict):
                continue
            heard = " ".join(str(turn.get("heard", "")).split()).strip()
            intent = " ".join(str(turn.get("intent", "")).split()).strip()
            spoken = " ".join(str(turn.get("spoken", "")).split()).strip()
            stamp = " ".join(str(turn.get("time", "")).split()).strip()
            if not any((heard, intent, spoken)):
                continue
            self.turns.append(
                {
                    "heard": heard,
                    "intent": intent,
                    "spoken": spoken,
                    "time": stamp,
                }
            )
        if self.turns:
            latest = self.turns[-1]
            self.last_spoken = latest.get("spoken", "")
            self.last_intent = latest.get("intent", "")
            self.last_heard = latest.get("heard", "")

    def add_turn(self, heard: str, intent: str, spoken: str) -> None:
        entry = {
            "heard": " ".join(str(heard or "").split()).strip(),
            "intent": " ".join(str(intent or "").split()).strip(),
            "spoken": " ".join(str(spoken or "").split()).strip(),
            "time": datetime.now().isoformat(),
        }
        self.turns.append(entry)
        self.turns = self.turns[-6:]
        self.last_spoken = entry["spoken"]
        self.last_intent = entry["intent"]
        self.last_heard = entry["heard"]

    def get_context_for_llm(self) -> str:
        if not self.turns:
            return ""
        lines = ["[CONVERSATION]"]
        for turn in self.turns[-3:]:
            if turn["heard"]:
                lines.append(f"  User: {turn['heard']}")
            if turn["spoken"]:
                lines.append(f"  Butler: {turn['spoken']}")
        return "\n".join(lines)

    def get_recent_turns_prompt(self, limit: int = 5) -> str:
        if not self.turns:
            return ""
        lines = ["[RECENT CONVERSATION]"]
        for turn in self.turns[-max(1, limit):]:
            if turn["heard"]:
                lines.append(f"  USER: {turn['heard']}")
            if turn["spoken"]:
                lines.append(f"  BURRY: {turn['spoken']}")
        return "\n".join(lines)

    def clear(self) -> None:
        self.turns = []
        self.last_spoken = ""
        self.last_intent = ""
        self.last_heard = ""


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
STARTUP_BRIEFING_MODEL = "gemma4:e4b"


def _check_searxng() -> bool:
    try:
        response = requests.get(
            f"{SEARXNG_URL}/",
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


def _set_pending_dialogue(kind: str, **metadata) -> None:
    global _PENDING_DIALOGUE
    with _PENDING_DIALOGUE_LOCK:
        _PENDING_DIALOGUE = {"kind": kind, **metadata}


def _get_pending_dialogue() -> dict | None:
    with _PENDING_DIALOGUE_LOCK:
        if _PENDING_DIALOGUE is None:
            return None
        return dict(_PENDING_DIALOGUE)


def _clear_pending_dialogue() -> None:
    global _PENDING_DIALOGUE
    with _PENDING_DIALOGUE_LOCK:
        _PENDING_DIALOGUE = None


def reset_conversation_context() -> None:
    global _briefing_done
    with _CONVERSATION_LOCK:
        _SESSION_CONVERSATION.clear()
        note_conversation_turns([])
    _briefing_done = False


def _remember_conversation_turn(heard: str, intent_name: str, spoken: str) -> None:
    if not spoken:
        return
    with _CONVERSATION_LOCK:
        _SESSION_CONVERSATION.add_turn(heard, intent_name, spoken)
        note_conversation_turns(_SESSION_CONVERSATION.turns)


def _conversation_context_text() -> str:
    with _CONVERSATION_LOCK:
        return _SESSION_CONVERSATION.get_context_for_llm()


def _recent_turns_prompt_text(limit: int = 5) -> str:
    with _CONVERSATION_LOCK:
        prompt = _SESSION_CONVERSATION.get_recent_turns_prompt(limit=limit)
    if prompt:
        return prompt

    try:
        runtime_state = load_runtime_state()
    except Exception:
        return ""

    if not isinstance(runtime_state, dict):
        return ""

    lines = ["[RECENT CONVERSATION]"]
    last_heard = " ".join(str(runtime_state.get("last_heard_text", "")).split()).strip()
    last_spoken = " ".join(str(runtime_state.get("last_spoken_text", "")).split()).strip()
    if last_heard:
        lines.append(f"  USER: {last_heard[:180]}")
    if last_spoken:
        lines.append(f"  BURRY: {last_spoken[:220]}")
    return "\n".join(lines) if len(lines) > 1 else ""


def _resolve_pending_dialogue(text: str) -> IntentResult | None:
    pending = _get_pending_dialogue()
    if not pending:
        return None

    routed = route(text)
    if routed.name != "unknown":
        _clear_pending_dialogue()
        return routed

    if pending.get("kind") == "spotify_song":
        candidate = clean_song_query(re.sub(r"^play\s+", "", text.lower().strip()))
        if not is_ambiguous_song_query(candidate):
            _clear_pending_dialogue()
            return IntentResult("spotify_play", {"song": candidate}, confidence=0.85, raw=text)
        return IntentResult("clarify_song", confidence=0.3, raw=text)

    if pending.get("kind") == "file_name":
        candidate = extract_requested_filename(text) or _filename_from_follow_up(text)
        if candidate:
            _clear_pending_dialogue()
            return IntentResult(
                "create_file",
                {
                    "filename": candidate,
                    "editor": pending.get("editor", "auto"),
                },
                confidence=0.85,
                raw=text,
            )
        return IntentResult(
            "clarify_file",
            {"editor": pending.get("editor", "auto")},
            confidence=0.3,
            raw=text,
        )

    return None


def _unknown_response_for_text(text: str) -> str:
    lowered = text.lower()
    if any(token in lowered for token in ("spotify", "song", "track", "artist", "album")):
        _set_pending_dialogue("spotify_song")
        return "I didn't catch the song. Say the title and artist."
    if any(token in lowered for token in ("file", "document")) and any(
        token in lowered for token in ("make", "create", "new", "name", "named", "called")
    ):
        _set_pending_dialogue("file_name", editor=detect_editor_choice(text))
        return "What should I name the file?"
    return ""


def _should_use_brain_for_unknown(text: str) -> bool:
    lowered = " ".join(str(text or "").lower().split())
    if len(lowered.split()) < 3:
        return False

    starters = (
        "what",
        "why",
        "how",
        "who",
        "when",
        "where",
        "can you",
        "could you",
        "would you",
        "tell me",
        "show me",
        "give me",
        "are you",
        "do you",
        "did you",
        "you are",
        "you're",
        "we are",
        "that",
        "this",
        "it",
    )
    if any(lowered.startswith(prefix) for prefix in starters):
        return True

    signal_words = {
        "news",
        "latest",
        "mail",
        "email",
        "search",
        "open",
        "project",
        "task",
        "doing",
        "build",
        "working",
    }
    return len(lowered.split()) >= 5 and any(token in lowered for token in signal_words)


def _looks_like_followup_reference(text: str) -> bool:
    lowered = " ".join(str(text or "").lower().split())
    if len(lowered.split()) < 2:
        return False
    if any(lowered.startswith(prefix) for prefix in _FOLLOWUP_PREFIXES):
        return True
    if any(
        phrase in lowered
        for phrase in (
            "you said",
            "what you said",
            "same thing",
            "same topic",
            "same one",
        )
    ):
        return True
    return any(
        re.search(pattern, lowered) is not None
        for pattern in (
            r"\bthat\b",
            r"\bit\b",
            r"\bthis\b",
            r"\bthere\b",
            r"\bthey\b",
            r"\bthem\b",
        )
    )


def _recent_dialogue_context() -> str:
    conversation = _conversation_context_text()
    if conversation:
        return conversation

    try:
        runtime_state = load_runtime_state()
    except Exception:
        return ""

    if not isinstance(runtime_state, dict):
        return ""

    lines = []
    last_heard = " ".join(str(runtime_state.get("last_heard_text", "")).split()).strip()
    last_spoken = " ".join(str(runtime_state.get("last_spoken_text", "")).split()).strip()

    if last_heard:
        lines.append(f"Last heard command: {last_heard[:140]}")
    if last_spoken:
        lines.append(f"Last Butler reply: {last_spoken[:180]}")

    return "\n".join(lines)


def _looks_like_greeting(text: str) -> bool:
    lowered = " ".join(str(text or "").lower().split())
    if not lowered:
        return False
    patterns = (
        r"^(?:hi|hello|hey|yo)\b",
        r"\bhow are you\b",
        r"^good (?:morning|afternoon|evening)\b",
    )
    return any(re.search(pattern, lowered) is not None for pattern in patterns)


def _should_use_fast_path_intent(intent_name: str, intent_confidence: float, text: str) -> bool:
    if intent_name == "greeting":
        return True
    if intent_name in FAST_PATH_INTENTS and intent_confidence >= FAST_PATH_CONFIDENCE:
        return True
    return intent_name == "unknown" and _looks_like_greeting(text)


def _fast_path_prompt(intent_name: str, text: str, ctx: dict) -> str:
    formatted = str(ctx.get("formatted", "") or "").strip()[:220]
    dialogue = _recent_turns_prompt_text() or _recent_dialogue_context()
    if intent_name == "greeting":
        return f"""You are Burry, a concise local voice assistant for Aditya.

Current work context:
{formatted}

{dialogue}

User said: "{text}"

Reply warmly in under 16 words.
Output ONLY the reply text."""

    return f"""You are Burry, a concise local voice assistant for Aditya.

Current work context:
{formatted}

{dialogue}

User said: "{text}"

Reply directly in under 28 words.
Do not mention tools, plans, or internal reasoning.
Output ONLY the reply text."""


def _fast_path_llm_response(
    intent_name: str,
    text: str,
    ctx: dict,
    *,
    model: str | None = None,
) -> str:
    from brain.ollama_client import _call, pick_butler_model

    prompt = _fast_path_prompt(intent_name, text, ctx)
    voice_model = pick_butler_model("voice", override=model)
    response = _call(
        prompt,
        voice_model,
        temperature=0.25,
        max_tokens=150,
    )
    return _normalize_response(response, max_words=28)


def _unknown_brain_response(text: str, model: str | None = None) -> str:
    ctx = _get_cached_context()
    dialogue = _recent_turns_prompt_text() or _recent_dialogue_context()
    prompt = f"""You are Butler in an active voice session.

Current work context:
{ctx.get('formatted', '')[:220]}

{dialogue}

User just said: "{text}"

If the user refers to "that", "it", or previous work, resolve it from the last Butler reply.
Reply in under 18 words.
If the request is still unclear, ask one short clarifying question instead of saying try again.
Output ONLY the response text."""
    fast_model = model or OLLAMA_FALLBACK or OLLAMA_MODEL
    response = _normalize_response(
        _raw_llm(prompt, model=fast_model, max_tokens=80),
        max_words=18,
    )
    if not response or response == "Something went wrong.":
        return ""
    return response


def _resolve_followup_text(text: str, model: str | None = None) -> str:
    if not _looks_like_followup_reference(text):
        return text
    conversation = _recent_turns_prompt_text()
    if not conversation:
        return text

    prompt = f"""Rewrite the user's follow-up into a standalone request using the recent conversation.

{conversation}

Follow-up: "{text}"

Rules:
- Keep the original meaning.
- Resolve words like it, that, this, there, or you said.
- Keep it under 18 words.
- Output ONLY the rewritten request text.
"""
    rewritten = _normalize_response(
        _raw_llm(prompt, model=model or OLLAMA_FALLBACK or OLLAMA_MODEL, max_tokens=80),
        max_words=18,
    ).strip().strip('"')
    if not rewritten or rewritten == "Something went wrong.":
        return text
    return rewritten


def _filename_from_follow_up(text: str) -> str:
    candidate = re.sub(
        r"^(?:call(?: it)?|name(?: it)?|make it|create it as)\s+",
        "",
        text.strip(),
        flags=re.IGNORECASE,
    )
    candidate = candidate.strip().strip("\"'.,!?")
    candidate = re.sub(r"\s+(?:please|now|for me)$", "", candidate, flags=re.IGNORECASE)
    candidate = re.sub(r"\s+", " ", candidate).strip()
    if not candidate:
        return ""
    if candidate.lower() in {"yes", "yeah", "yep", "no", "nope", "ok", "okay"}:
        return ""
    if len(candidate.split()) > 6:
        return ""
    return candidate


def _reply_without_action(
    text: str,
    response: str,
    test_mode: bool = False,
    intent_name: str = "",
    learning_meta: dict | None = None,
) -> None:
    _speak_or_print(response, test_mode=test_mode)
    _record(text, response, [], intent_name=intent_name or "reply", learning_meta=learning_meta)
    state.transition(State.WAITING if not test_mode else State.IDLE)


def _build_voice_prompt(intent: IntentResult, text: str) -> str:
    conversation = _recent_turns_prompt_text()
    if intent.name == "what_next":
        ctx = _get_cached_context()
        mac_state = get_state_for_context()
        return f"""You are Butler, Aditya's local operator.

Current Mac state:
{mac_state}

Current work context:
{ctx['formatted'][:320]}

{conversation}

User asked: "{text}"

Answer in under 20 words.
Be specific to current work.
Recommend the single next step.
Output ONLY the response text:"""

    ctx = _get_cached_context()
    return f"""You are Butler, a concise local voice operator for Aditya.
His main projects are mac-butler and email-infra.

Current work context:
{ctx['formatted'][:220]}

{conversation}

User asked: "{text}"

Answer directly in under 20 words.
Use mac-butler or email-infra by name when clearly relevant.
Never explain uncertainty or hedge.
If context is sparse, ask one short binary clarifying question instead of guessing.
Output ONLY the response text:"""


def _brain_context_text(ctx: dict, user_text: str | None = None) -> str:
    parts = []
    formatted = str(ctx.get("formatted", "")).strip()
    conversation = _recent_turns_prompt_text()
    hint = _consume_project_context_block()

    if formatted:
        parts.append(formatted)
    if conversation:
        parts.append(conversation)
    if hint:
        parts.append(hint)

    if user_text:
        parts.append(f"[CURRENT REQUEST]\n  {user_text}")
        lowered = user_text.lower()
        hints = []
        if any(token in lowered for token in ("news", "latest", "recent", "happening")):
            hints.append('  Consider {"type": "run_agent", "agent": "news"} or search for current info.')
        if any(token in lowered for token in ("search", "look up", "find", "what is")):
            hints.append('  Consider {"type": "run_agent", "agent": "search"} when external lookup is needed.')
        if any(token in lowered for token in ("github", "pull request", "pr", "issue", "repo")):
            hints.append('  Consider {"type": "run_agent", "agent": "github"} for repo questions.')
        if any(token in lowered for token in ("vps", "server", "docker", "container")):
            hints.append('  Consider {"type": "run_agent", "agent": "vps"} for infrastructure status.')
        if hints:
            parts.append("[AGENT HINTS]\n" + "\n".join(hints))

        if any(
            phrase in lowered
            for phrase in (
                "what should i do next",
                "what's next",
                "whats next",
                "what next",
                "next step",
            )
        ):
            snapshot = _project_snapshot_for_planning()
            if snapshot:
                parts.insert(0, snapshot)
            if formatted:
                parts[1 if snapshot else 0] = _strip_context_section(formatted, "[TASK LIST]")

    return "\n\n".join(part for part in parts if part).strip()


def _consume_project_context_block() -> str:
    try:
        payload = consume_project_context_hint()
    except Exception:
        payload = {}
    project = " ".join(str(payload.get("project", "")).split()).strip()
    detail = " ".join(str(payload.get("detail", "")).split()).strip()
    if not project or not detail:
        return ""
    return f"[PROJECT MEMORY]\n  {project}: {detail[:1000]}"


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
    try:
        from memory.store import load_recent_sessions
    except Exception:
        return []

    summaries: list[str] = []
    for session in load_recent_sessions(max(6, limit * 3)):
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
    from brain.ollama_client import send_to_ollama

    fallback = {
        "speech": "Back on mac-butler. Want to jump in?",
        "spoken_text": "Back on mac-butler. Want to jump in?",
        "actions": [],
        "focus": "",
        "why_now": "",
        "greeting": "",
    }

    try:
        raw = send_to_ollama(context_text, model=model)
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


TOOL_SYSTEM_PROMPT = """You are Burry, Aditya's Mac operator.

Use tools when they will materially improve the answer or complete the action.
Tool policy:
- use open_project when the user wants to open or work on a named project
- use focus_app, minimize_app, or hide_app for Mac window management
- use chrome_open_tab, chrome_close_tab, or chrome_focus_tab for Chrome tab actions
- use send_email for Mail.app sends and send_whatsapp for desktop WhatsApp messages
- use run_shell for tests, git, server checks, and safe shell commands
- use browse_web for latest information, search, or reading a page
- use browse_and_act for site navigation or page-specific browser tasks like "latest commit on GitHub"
- use recall_memory for questions about past decisions, prior work, or session history
- use take_screenshot_and_describe for screen questions

Rules:
- Keep the final spoken answer under 30 words unless summarizing a fetched page or news result
- Sound direct and useful
- If you already have enough context, answer directly without forcing a tool call
- If the request is ambiguous, ask one short clarifying question
"""


def _project_path_for_name(name: str) -> str:
    candidate = " ".join(str(name or "").split()).strip()
    if not candidate:
        return ""
    try:
        from projects import get_project

        project = get_project(candidate, hydrate_blurb=True)
    except Exception:
        project = None
    if not project:
        return ""
    return str(project.get("path", "") or "").strip()


def _minutes_from_time_spec(value: str) -> int:
    text = " ".join(str(value or "").lower().split()).strip()
    if not text:
        return 30
    match = re.search(r"(\d+)", text)
    if not match:
        return 30
    amount = max(1, int(match.group(1)))
    if any(token in text for token in ("hour", "hr", "hrs")):
        return amount * 60
    return amount


def _tool_chat_messages(ctx: dict, user_text: str) -> list[dict]:
    formatted = str(ctx.get("formatted", "") or "").strip()
    recent = _recent_turns_prompt_text()
    prompt_parts = []
    if formatted:
        prompt_parts.append(formatted[:800])
    if recent:
        prompt_parts.append(recent)
    hint = _consume_project_context_block()
    if hint:
        prompt_parts.append(hint)
    prompt_parts.append(f"[CURRENT REQUEST]\n  {user_text}")
    return [
        {"role": "system", "content": TOOL_SYSTEM_PROMPT},
        {"role": "user", "content": "\n\n".join(part for part in prompt_parts if part)},
    ]


def _parse_tool_arguments(arguments) -> dict:
    if isinstance(arguments, dict):
        return dict(arguments)
    if isinstance(arguments, str):
        try:
            parsed = json.loads(arguments)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return {}
    return {}


def _clip_tool_payload(value, limit: int = 2600):
    if isinstance(value, dict):
        clipped = {}
        for key, item in value.items():
            clipped[key] = _clip_tool_payload(item, limit=limit)
        return clipped
    if isinstance(value, list):
        return [_clip_tool_payload(item, limit=limit) for item in value[:5]]
    text = " ".join(str(value or "").split()).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _tool_chat_endpoint_missing(exc: Exception) -> bool:
    lowered = " ".join(str(exc or "").lower().split())
    return "/api/chat" in lowered and "404" in lowered


def _looks_like_memory_question(text: str) -> bool:
    lowered = " ".join(str(text or "").lower().split())
    if not lowered:
        return False
    phrases = (
        "what did we decide",
        "what did we say",
        "do you remember",
        "what was the decision",
        "what did we choose",
        "remember about",
        "recall",
        "last time we",
        "earlier we",
        "before we",
    )
    return any(phrase in lowered for phrase in phrases)


def _fallback_tool_outcome(text: str, ctx: dict) -> dict | None:
    lowered = " ".join(str(text or "").lower().split())
    if _looks_like_memory_question(lowered):
        return _execute_tool_call("recall_memory", {"query": text}, ctx, user_text=text)

    if any(phrase in lowered for phrase in ("what am i looking at", "what's on my screen", "describe this screen", "describe my screen")):
        return _execute_tool_call("take_screenshot_and_describe", {"question": text}, ctx, user_text=text)

    if "github" in lowered and "latest commit" in lowered:
        return _execute_tool_call("browse_and_act", {"task": text}, ctx, user_text=text)

    decision = analyze_query(text, conversation=_conversation_context_text())
    action = str(decision.get("action", "") or "").strip().lower()
    url = str(decision.get("url", "") or "").strip()
    if action == "fetch" and url:
        return _execute_tool_call("browse_web", {"url": url, "query": text}, ctx, user_text=text)
    if action in {"search", "news", "fetch"}:
        return _execute_tool_call("browse_web", {"query": text, "url": url}, ctx, user_text=text)
    return None


def _fallback_tool_speech(text: str, outcome: dict) -> str:
    tool = str(outcome.get("tool", "")).strip()
    payload = outcome.get("payload") if isinstance(outcome.get("payload"), dict) else {}
    results = outcome.get("results") if isinstance(outcome.get("results"), list) else []

    if tool == "recall_memory":
        matches = payload.get("matches") if isinstance(payload.get("matches"), list) else []
        if matches:
            first = matches[0] if isinstance(matches[0], dict) else {}
            candidate = str(first.get("speech", "") or first.get("context", "")).strip()
            if candidate:
                return _normalize_response(candidate, max_words=45)
        return "I couldn't find a matching decision in memory."

    if tool == "browse_web":
        lead = ""
        if results:
            lead = str(results[0].get("result", "") or "").strip()
        lead = lead or str(payload.get("result", "") or "").strip()
        if lead:
            return _normalize_response(lead, max_words=45)
        return "I couldn't pull a useful web answer right now."

    if tool == "take_screenshot_and_describe":
        answer = str(payload.get("result", "") or "").strip()
        if answer:
            return _normalize_response(answer, max_words=45)
        return "I couldn't read the screen clearly right now."

    if results:
        lead = str(results[0].get("result", "") or results[0].get("error", "")).strip()
        if lead:
            return _normalize_response(lead, max_words=45)

    return _normalize_response(str(text or "").strip(), max_words=20) or "Done."


def _fallback_tool_response(text: str, ctx: dict) -> dict | None:
    outcome = _fallback_tool_outcome(text, ctx)
    if not outcome:
        return None
    return {
        "speech": _fallback_tool_speech(text, outcome),
        "actions": outcome.get("actions", []),
        "results": outcome.get("results", []),
    }


def _execute_tool_call(tool_name: str, arguments: dict, ctx: dict, user_text: str = "") -> dict:
    from brain.toolkit import get_toolkit
    import brain.tools_registry  # noqa — triggers all @tool decorations

    name = str(tool_name or "").strip()
    args = dict(arguments or {})
    toolkit = get_toolkit()

    # Legacy path: keep old dispatch for any tools not yet in registry
    _name = name
    _args = args

    if name == "open_project":
        project_name = " ".join(str(args.get("name", "")).split()).strip()
        note_tool_started(name, project_name or "opening project")
        action = {"type": "open_project", "name": project_name}
        results = executor.run([action])
        result = results[0] if results else {"action": "open_project", "status": "error", "error": "No result"}
        note_tool_finished(name, result.get("status", "ok"), result.get("result", "") or result.get("error", ""))
        return {
            "tool": name,
            "actions": [action],
            "results": results,
            "payload": {
                "project": project_name,
                "status": result.get("status", "ok"),
                "result": _clip_tool_payload(result.get("result", "") or result.get("error", "")),
            },
        }

    if name == "run_shell":
        command = " ".join(str(args.get("command", "")).split()).strip()
        project_name = " ".join(str(args.get("project", "")).split()).strip()
        note_tool_started(name, command or project_name or "running shell command")
        cwd = _project_path_for_name(project_name) or _first_workspace_path(ctx) or "~/Burry"
        action = {"type": "run_command", "cmd": command, "cwd": cwd}
        results = executor.run([action])
        result = results[0] if results else {"action": "run_command", "status": "error", "error": "No result"}
        result_text = str(result.get("result", "") or result.get("error", "")).strip()
        output_lines = [line for line in result_text.splitlines() if line.strip()]
        if len(output_lines) > 2:
            try:
                shell_summary = _normalize_response(
                    _raw_llm(
                        f"Summarize this shell output in under 15 words:\n{result_text[:1200]}",
                        model="gemma4:e4b",
                        max_tokens=40,
                        temperature=0.2,
                    ),
                    max_words=15,
                    single_sentence=True,
                )
            except Exception:
                shell_summary = ""
            if shell_summary:
                try:
                    speak(shell_summary)
                except Exception:
                    pass
        note_tool_finished(name, result.get("status", "ok"), result.get("result", "") or result.get("error", ""))
        return {
            "tool": name,
            "actions": [action],
            "results": results,
            "payload": {
                "command": command,
                "cwd": cwd,
                "status": result.get("status", "ok"),
                "result": _clip_tool_payload(result.get("result", "") or result.get("error", "")),
            },
        }

    if name == "git_commit":
        project_name = " ".join(str(args.get("project", "")).split()).strip()
        message_hint = " ".join(str(args.get("message_hint", "")).split()).strip()
        cwd = _project_path_for_name(project_name) or _first_workspace_path(ctx) or "~/Burry/mac-butler"
        expanded_cwd = os.path.expanduser(cwd)
        note_tool_started(name, project_name or expanded_cwd or "generating commit message")
        diff = subprocess.run(
            ["git", "diff", "--cached"],
            cwd=expanded_cwd,
            capture_output=True,
            text=True,
            timeout=20,
        )
        staged_diff = str(diff.stdout or "").strip()
        if not staged_diff:
            note_tool_finished(name, "ok", "No staged changes to commit")
            return {
                "tool": name,
                "actions": [{"type": "git_commit", "cwd": expanded_cwd}],
                "results": [{"action": "git_commit", "status": "ok", "result": "No staged changes to commit"}],
                "payload": {"cwd": expanded_cwd, "message": "", "status": "ok", "result": "No staged changes to commit"},
            }

        prompt = f"""Write a concise git commit message for these staged changes.
Use imperative mood. No quotes. Under 12 words.
Hint: {message_hint or "none"}

Diff:
{staged_diff[:6000]}
"""
        suggestion = _normalize_response(
            _raw_llm(prompt, model=BUTLER_MODELS.get("voice") or "gemma4:e4b", max_tokens=40, temperature=0.2),
            max_words=12,
            single_sentence=True,
        ).strip(" .")
        if not suggestion:
            suggestion = message_hint or "Update staged changes"

        try:
            speak(f"I suggest commit message: {suggestion}. Confirm in the HUD if you want me to commit.")
        except Exception:
            pass
        if not _wait_for_runtime_confirmation(f"Confirm git commit: {suggestion}", "git_commit", timeout_s=30):
            note_tool_finished(name, "ok", "Commit skipped - no confirmation")
            return {
                "tool": name,
                "actions": [{"type": "git_commit", "cwd": expanded_cwd, "message": suggestion}],
                "results": [{"action": "git_commit", "status": "ok", "result": "Commit skipped - no confirmation"}],
                "payload": {"cwd": expanded_cwd, "message": suggestion, "status": "ok", "result": "Commit skipped - no confirmation"},
            }

        commit = subprocess.run(
            ["git", "commit", "-m", suggestion],
            cwd=expanded_cwd,
            capture_output=True,
            text=True,
            timeout=30,
        )
        commit_result = " ".join((commit.stdout or commit.stderr or "").split()).strip()
        status = "ok" if commit.returncode == 0 else "error"
        note_tool_finished(name, status, commit_result or suggestion)
        return {
            "tool": name,
            "actions": [{"type": "git_commit", "cwd": expanded_cwd, "message": suggestion}],
            "results": [{"action": "git_commit", "status": status, "result": commit_result or suggestion}],
            "payload": {"cwd": expanded_cwd, "message": suggestion, "status": status, "result": _clip_tool_payload(commit_result or suggestion)},
        }

    if name == "open_app":
        app = " ".join(str(args.get("app", "")).split()).strip()
        mode = " ".join(str(args.get("mode", "smart")).split()).strip() or "smart"
        note_tool_started(name, app or "opening app")
        action = {"type": "open_app", "app": app, "mode": mode}
        results = executor.run([action])
        result = results[0] if results else {"action": "open_app", "status": "error", "error": "No result"}
        note_tool_finished(name, result.get("status", "ok"), result.get("result", "") or result.get("error", ""))
        return {
            "tool": name,
            "actions": [action],
            "results": results,
            "payload": {"app": app, "mode": mode, "status": result.get("status", "ok"), "result": _clip_tool_payload(result.get("result", "") or result.get("error", ""))},
        }

    if name == "focus_app":
        app = " ".join(str(args.get("app", "")).split()).strip()
        note_tool_started(name, app or "focusing app")
        action = {"type": "focus_app", "app": app}
        results = executor.run([action])
        result = results[0] if results else {"action": "focus_app", "status": "error", "error": "No result"}
        note_tool_finished(name, result.get("status", "ok"), result.get("result", "") or result.get("error", ""))
        return {
            "tool": name,
            "actions": [action],
            "results": results,
            "payload": {"app": app, "status": result.get("status", "ok"), "result": _clip_tool_payload(result.get("result", "") or result.get("error", ""))},
        }

    if name == "minimize_app":
        app = " ".join(str(args.get("app", "")).split()).strip()
        note_tool_started(name, app or "minimizing app")
        action = {"type": "minimize_app", "app": app}
        results = executor.run([action])
        result = results[0] if results else {"action": "minimize_app", "status": "error", "error": "No result"}
        note_tool_finished(name, result.get("status", "ok"), result.get("result", "") or result.get("error", ""))
        return {
            "tool": name,
            "actions": [action],
            "results": results,
            "payload": {"app": app, "status": result.get("status", "ok"), "result": _clip_tool_payload(result.get("result", "") or result.get("error", ""))},
        }

    if name == "hide_app":
        app = " ".join(str(args.get("app", "")).split()).strip()
        note_tool_started(name, app or "hiding app")
        action = {"type": "hide_app", "app": app}
        results = executor.run([action])
        result = results[0] if results else {"action": "hide_app", "status": "error", "error": "No result"}
        note_tool_finished(name, result.get("status", "ok"), result.get("result", "") or result.get("error", ""))
        return {
            "tool": name,
            "actions": [action],
            "results": results,
            "payload": {"app": app, "status": result.get("status", "ok"), "result": _clip_tool_payload(result.get("result", "") or result.get("error", ""))},
        }

    if name == "chrome_open_tab":
        url = " ".join(str(args.get("url", "")).split()).strip()
        note_tool_started(name, url or "opening chrome tab")
        action = {"type": "chrome_open_tab", "url": url}
        results = executor.run([action])
        result = results[0] if results else {"action": "chrome_open_tab", "status": "error", "error": "No result"}
        note_tool_finished(name, result.get("status", "ok"), result.get("result", "") or result.get("error", ""))
        return {
            "tool": name,
            "actions": [action],
            "results": results,
            "payload": {"url": url, "status": result.get("status", "ok"), "result": _clip_tool_payload(result.get("result", "") or result.get("error", ""))},
        }

    if name == "chrome_close_tab":
        tab_title = " ".join(str(args.get("tab_title", "")).split()).strip()
        note_tool_started(name, tab_title or "closing chrome tab")
        action = {"type": "chrome_close_tab", "tab_title": tab_title}
        results = executor.run([action])
        result = results[0] if results else {"action": "chrome_close_tab", "status": "error", "error": "No result"}
        note_tool_finished(name, result.get("status", "ok"), result.get("result", "") or result.get("error", ""))
        return {
            "tool": name,
            "actions": [action],
            "results": results,
            "payload": {"tab_title": tab_title, "status": result.get("status", "ok"), "result": _clip_tool_payload(result.get("result", "") or result.get("error", ""))},
        }

    if name == "chrome_focus_tab":
        tab_title = " ".join(str(args.get("tab_title", "")).split()).strip()
        note_tool_started(name, tab_title or "focusing chrome tab")
        action = {"type": "chrome_focus_tab", "tab_title": tab_title}
        results = executor.run([action])
        result = results[0] if results else {"action": "chrome_focus_tab", "status": "error", "error": "No result"}
        note_tool_finished(name, result.get("status", "ok"), result.get("result", "") or result.get("error", ""))
        return {
            "tool": name,
            "actions": [action],
            "results": results,
            "payload": {"tab_title": tab_title, "status": result.get("status", "ok"), "result": _clip_tool_payload(result.get("result", "") or result.get("error", ""))},
        }

    if name == "send_email":
        to = " ".join(str(args.get("to", "")).split()).strip()
        subject = " ".join(str(args.get("subject", "")).split()).strip()
        body = str(args.get("body", "")).strip()
        note_tool_started(name, to or "sending email")
        action = {"type": "send_email", "to": to, "subject": subject, "body": body}
        results = executor.run([action])
        result = results[0] if results else {"action": "send_email", "status": "error", "error": "No result"}
        note_tool_finished(name, result.get("status", "ok"), result.get("result", "") or result.get("error", ""))
        return {
            "tool": name,
            "actions": [action],
            "results": results,
            "payload": {"to": to, "subject": subject, "status": result.get("status", "ok"), "result": _clip_tool_payload(result.get("result", "") or result.get("error", ""))},
        }

    if name == "send_whatsapp":
        contact = " ".join(str(args.get("contact", "")).split()).strip()
        message = " ".join(str(args.get("message", "")).split()).strip()
        note_tool_started(name, contact or "sending WhatsApp")
        action = {"type": "send_whatsapp", "contact": contact, "message": message}
        results = executor.run([action])
        result = results[0] if results else {"action": "send_whatsapp", "status": "error", "error": "No result"}
        note_tool_finished(name, result.get("status", "ok"), result.get("result", "") or result.get("error", ""))
        return {
            "tool": name,
            "actions": [action],
            "results": results,
            "payload": {"contact": contact, "message": message, "status": result.get("status", "ok"), "result": _clip_tool_payload(result.get("result", "") or result.get("error", ""))},
        }

    if name == "spotify_control":
        action_name = " ".join(str(args.get("action", "")).split()).strip().lower()
        query = " ".join(str(args.get("query", "")).split()).strip()
        note_tool_started(name, action_name or query or "spotify control")
        if action_name == "play" and query:
            action = {"type": "search_and_play", "query": query}
        elif action_name == "play":
            action = {"type": "play_music", "mode": "focus"}
        elif action_name == "pause":
            action = {"type": "spotify_pause"}
        elif action_name == "next":
            action = {"type": "spotify_next"}
        elif action_name == "prev":
            action = {"type": "spotify_prev"}
        elif action_name == "volume_up":
            action = {"type": "spotify_volume", "direction": "up", "amount": 15}
        elif action_name == "volume_down":
            action = {"type": "spotify_volume", "direction": "down", "amount": 15}
        else:
            action = {"type": "spotify_now_playing"}
        results = executor.run([action])
        result = results[0] if results else {"action": action.get("type", "spotify_control"), "status": "error", "error": "No result"}
        note_tool_finished(name, result.get("status", "ok"), result.get("result", "") or result.get("error", ""))
        return {
            "tool": name,
            "actions": [action],
            "results": results,
            "payload": {"action": action_name, "query": query, "status": result.get("status", "ok"), "result": _clip_tool_payload(result.get("result", "") or result.get("error", ""))},
        }

    if name == "set_reminder":
        time_spec = " ".join(str(args.get("time", "")).split()).strip()
        message = " ".join(str(args.get("message", "")).split()).strip() or "Butler reminder"
        minutes = _minutes_from_time_spec(time_spec)
        note_tool_started(name, f"{minutes} minutes")
        action = {"type": "remind_in", "minutes": minutes, "message": message}
        results = executor.run([action])
        result = results[0] if results else {"action": "remind_in", "status": "error", "error": "No result"}
        note_tool_finished(name, result.get("status", "ok"), result.get("result", "") or result.get("error", ""))
        return {
            "tool": name,
            "actions": [action],
            "results": results,
            "payload": {"minutes": minutes, "message": message, "status": result.get("status", "ok"), "result": _clip_tool_payload(result.get("result", "") or result.get("error", ""))},
        }

    if name == "ssh_vps":
        command = " ".join(str(args.get("command", "")).split()).strip()
        host = _default_vps_host()
        note_tool_started(name, command or host or "running vps command")
        action = {"type": "ssh_command", "host": host, "cmd": command}
        results = executor.run([action])
        result = results[0] if results else {"action": "ssh_command", "status": "error", "error": "No result"}
        note_tool_finished(name, result.get("status", "ok"), result.get("result", "") or result.get("error", ""))
        return {
            "tool": name,
            "actions": [action],
            "results": results,
            "payload": {"host": host, "command": command, "status": result.get("status", "ok"), "result": _clip_tool_payload(result.get("result", "") or result.get("error", ""))},
        }

    if name == "obsidian_note":
        title = " ".join(str(args.get("title", "")).split()).strip() or "Quick note"
        content = str(args.get("content", "")).strip()
        note_tool_started(name, title)
        action = {"type": "obsidian_note", "title": title, "content": content, "folder": "Daily"}
        results = executor.run([action])
        result = results[0] if results else {"action": "obsidian_note", "status": "error", "error": "No result"}
        note_tool_finished(name, result.get("status", "ok"), result.get("result", "") or result.get("error", ""))
        return {
            "tool": name,
            "actions": [action],
            "results": results,
            "payload": {"title": title, "status": result.get("status", "ok"), "result": _clip_tool_payload(result.get("result", "") or result.get("error", ""))},
        }

    if name == "send_notification":
        title = " ".join(str(args.get("title", "")).split()).strip() or "Burry"
        message = " ".join(str(args.get("message", "")).split()).strip()
        note_tool_started(name, title)
        action = {"type": "notify", "title": title, "message": message}
        results = executor.run([action])
        result = results[0] if results else {"action": "notify", "status": "error", "error": "No result"}
        note_tool_finished(name, result.get("status", "ok"), result.get("result", "") or result.get("error", ""))
        return {
            "tool": name,
            "actions": [action],
            "results": results,
            "payload": {"title": title, "message": message, "status": result.get("status", "ok"), "result": _clip_tool_payload(result.get("result", "") or result.get("error", ""))},
        }

    if name == "web_search_summarize":
        from browser.agent import BrowsingAgent
        from brain.ollama_client import pick_butler_model

        query = " ".join(str(args.get("query", "")).split()).strip() or user_text
        note_tool_started(name, query or "web search")
        browser = BrowsingAgent(model=pick_butler_model("voice"))
        result = browser.search(query, question=user_text or query)
        summary = _normalize_response(str(result.get("result", "")).strip(), max_words=40) or "I couldn't get a useful web summary right now."
        note_tool_finished(name, result.get("status", "ok"), summary)
        return {
            "tool": name,
            "actions": [{"type": "browse_web", "mode": "search", "query": query}],
            "results": [{"action": "web_search_summarize", "status": result.get("status", "ok"), "result": summary}],
            "payload": {"query": query, "status": result.get("status", "ok"), "result": _clip_tool_payload(summary), "data": _clip_tool_payload(result.get("data", {}))},
        }

    if name == "browse_web":
        from browser.agent import BrowsingAgent
        from brain.ollama_client import pick_butler_model

        query = " ".join(str(args.get("query", "")).split()).strip() or user_text
        url = " ".join(str(args.get("url", "")).split()).strip()
        note_tool_started(name, url or query or "browsing web")
        browser = BrowsingAgent(model=pick_butler_model("voice"))
        if url:
            action = {"type": "browse_web", "mode": "fetch", "query": query or f"Read {url}", "url": url}
            result = browser.fetch(url, query or f"Read {url}")
        else:
            action = {"type": "browse_web", "mode": "search", "query": query}
            result = browser.search(query, question=user_text or query)
        note_tool_finished(name, result.get("status", "ok"), result.get("result", ""))
        result_row = {
            "action": "browse_web",
            "status": result.get("status", "ok"),
            "result": str(result.get("result", "") or ""),
        }
        return {
            "tool": name,
            "actions": [action],
            "results": [result_row],
            "payload": {
                "mode": action.get("mode", "search"),
                "status": result.get("status", "ok"),
                "result": _clip_tool_payload(result.get("result", "")),
                "data": _clip_tool_payload(result.get("data", {})),
            },
        }

    if name == "recall_memory":
        from memory.store import semantic_search

        query = " ".join(str(args.get("query", "")).split()).strip() or user_text
        note_tool_started(name, query or "recalling memory")
        matches = semantic_search(query, n=5)
        items = [
            {
                "timestamp": str(item.get("timestamp", ""))[:16],
                "context": _clip_tool_payload(item.get("context", item.get("context_preview", "")), limit=120),
                "speech": _clip_tool_payload(item.get("speech", ""), limit=140),
                "score": item.get("score", 0.0),
            }
            for item in matches
        ]
        note_memory_recall(query, items)
        note_tool_finished(name, "ok", f"Found {len(items)} memory matches")
        return {
            "tool": name,
            "actions": [{"type": "recall_memory", "query": query}],
            "results": [{"action": "recall_memory", "status": "ok", "result": f"{len(items)} matches"}],
            "payload": {"query": query, "matches": items},
        }

    if name == "take_screenshot_and_describe":
        from agents.vision import describe_screen

        question = " ".join(str(args.get("question", "")).split()).strip() or "What is on the screen right now?"
        note_tool_started(name, question)
        answer = describe_screen(question)
        note_tool_finished(name, "ok", answer)
        return {
            "tool": name,
            "actions": [{"type": "take_screenshot_and_describe", "question": question}],
            "results": [{"action": "take_screenshot_and_describe", "status": "ok", "result": answer}],
            "payload": {"question": question, "result": _clip_tool_payload(answer, limit=220)},
        }

    # Generic toolkit fallback for tools that do not need bespoke payload shaping.
    if name in toolkit._tools:
        note_tool_started(name, str(args)[:120])
        try:
            result = toolkit.call(name, **args)
            result_text = str(result)
            note_tool_finished(name, "ok", result_text[:200])
            return {
                "tool": name,
                "actions": [{"type": name, **args}],
                "results": [{"action": name, "status": "ok", "result": result_text}],
                "payload": {
                    **{key: _clip_tool_payload(value, limit=220) for key, value in args.items()},
                    "status": "ok",
                    "result": _clip_tool_payload(result_text),
                },
                "speech": result_text,
            }
        except Exception as exc:
            note_tool_finished(name, "error", str(exc))
            return {
                "tool": name,
                "actions": [],
                "results": [{"action": name, "status": "error", "error": str(exc)}],
                "payload": {"status": "error", "error": _clip_tool_payload(str(exc), limit=220)},
                "speech": f"I had trouble with {name}.",
            }

    note_tool_finished(name or "unknown", "error", "Unknown tool")
    return {
        "tool": name or "unknown",
        "actions": [],
        "results": [{"action": name or "unknown", "status": "error", "error": "Unknown tool"}],
        "payload": {"error": f"Unknown tool: {name or 'unknown'}"},
    }


def _tool_chat_response(
    text: str,
    ctx: dict,
    model: str | None = None,
    *,
    intent_name: str = "",
    intent_confidence: float = 0.0,
    stream_speech: bool = False,
) -> dict:
    from brain.ollama_client import chat_with_ollama, pick_butler_model
    from brain.tools import TOOLS

    planning_model = pick_butler_model("planning", override=model)
    voice_model = pick_butler_model("voice", override=model)
    messages = _tool_chat_messages(ctx, text)

    if _should_use_fast_path_intent(intent_name, intent_confidence, text):
        try:
            speech = _fast_path_llm_response(intent_name or "unknown", text, ctx, model=voice_model)
        except Exception:
            speech = ""
        if speech:
            return {
                "speech": speech,
                "actions": [],
                "results": [],
                "metadata": {"fast_path": True},
                "spoken": False,
            }

    try:
        from brain.agentscope_backbone import run_agentscope_turn

        backbone_reply = run_agentscope_turn(
            text,
            ctx,
            system_prompt=TOOL_SYSTEM_PROMPT,
            model_name=voice_model,
            intent_name=intent_name or "default",
            stream_speech=stream_speech,
            on_sentence=_speak_stream_chunk if stream_speech else None,
        )
        backbone_meta = backbone_reply.get("metadata", {}) if isinstance(backbone_reply.get("metadata"), dict) else {}
        speech = _normalize_response(str(backbone_reply.get("speech", "")).strip(), max_words=45)
        actions = backbone_reply.get("actions", []) if isinstance(backbone_reply.get("actions"), list) else []
        results = backbone_reply.get("results", []) if isinstance(backbone_reply.get("results"), list) else []
        if backbone_meta.get("interrupted") and not speech:
            speech = "Switching to your new request."
        if speech or actions or results or backbone_meta.get("interrupted"):
            return {
                "speech": speech,
                "actions": actions,
                "results": results,
                "metadata": backbone_meta,
                "spoken": bool(backbone_meta.get("spoken")),
            }
    except Exception as exc:
        print(f"[AgentScope] Backbone fallback: {exc}")

    try:
        first = chat_with_ollama(messages, planning_model, tools=TOOLS, max_tokens=220, temperature=0.2)
    except RuntimeError as exc:
        if not _tool_chat_endpoint_missing(exc):
            raise
        outcome = _fallback_tool_outcome(text, ctx)
        if not outcome:
            speech = _unknown_brain_response(text, model=model)
            return {"speech": speech, "actions": [], "results": []}
        speech = _fallback_tool_speech(text, outcome)
        return {
            "speech": speech,
            "actions": outcome.get("actions", []),
            "results": outcome.get("results", []),
        }
    message = first.get("message", {}) if isinstance(first, dict) else {}
    assistant_content = " ".join(str(message.get("content", "")).split()).strip()
    tool_calls = list(message.get("tool_calls") or [])
    executed_actions: list[dict] = []
    executed_results: list[dict] = []
    last_outcome: dict | None = None

    if not tool_calls:
        fallback = _fallback_tool_response(text, ctx)
        if fallback is not None:
            return fallback
        if stream_speech:
            try:
                streamed = asyncio.run(
                    _stream_chat_response_with_tts(
                        messages,
                        voice_model,
                        max_tokens=140,
                        temperature=0.3,
                    )
                )
            except Exception:
                streamed = ""
            streamed = _normalize_response(streamed, max_words=45)
            if streamed:
                notify("Burry", streamed[:180], subtitle="Response")
                return {"speech": streamed, "actions": [], "results": [], "spoken": True}
        speech = _normalize_response(assistant_content, max_words=45)
        return {"speech": speech, "actions": [], "results": []}

    messages.append(
        {
            "role": "assistant",
            "content": assistant_content,
            "tool_calls": tool_calls,
        }
    )

    for tool_call in tool_calls[:3]:
        # Check for user interrupt before each tool call (Phase 7)
        interrupt = check_interrupt()
        if interrupt:
            try:
                _COMMAND_QUEUE.put_nowait(interrupt)
            except queue.Full:
                return {"speech": "Still busy, please wait.", "actions": [], "results": []}
            _record(text, "Interrupted by user", [], intent_name="interrupted")
            return {
                "speech": "Switching to your new request.",
                "actions": [],
                "results": [{"status": "interrupted", "result": interrupt}],
            }
        function = tool_call.get("function", {}) if isinstance(tool_call, dict) else {}
        tool_name = str(function.get("name", "")).strip()
        arguments = _parse_tool_arguments(function.get("arguments", {}))
        outcome = _execute_tool_call(tool_name, arguments, ctx, user_text=text)
        last_outcome = outcome
        executed_actions.extend(outcome.get("actions", []))
        executed_results.extend(outcome.get("results", []))
        messages.append(
            {
                "role": "tool",
                "name": tool_name,
                "content": json.dumps(outcome.get("payload", {})),
            }
        )

    final_speech = ""
    already_spoken = False
    if stream_speech:
        try:
            streamed = asyncio.run(
                _stream_chat_response_with_tts(
                    messages,
                    voice_model,
                    max_tokens=140,
                    temperature=0.3,
                )
            )
        except Exception:
            streamed = ""
        final_speech = _normalize_response(streamed, max_words=45)
        already_spoken = bool(final_speech)
        if final_speech:
            notify("Burry", final_speech[:180], subtitle="Response")
    if not final_speech:
        final = chat_with_ollama(messages, voice_model, max_tokens=140, temperature=0.3)
        final_message = final.get("message", {}) if isinstance(final, dict) else {}
        final_speech = _normalize_response(str(final_message.get("content", "")).strip(), max_words=45)
    if not final_speech:
        if last_outcome is not None:
            final_speech = _fallback_tool_speech(text, last_outcome)
    if not final_speech:
        final_speech = assistant_content or "Done."
    return {"speech": final_speech, "actions": executed_actions, "results": executed_results, "spoken": already_spoken}


def observe_and_followup(
    plan: dict,
    execution_results: list,
    test_mode: bool = False,
    model: str | None = None,
) -> str:
    """
    After executing actions, feed results back to the model for a short follow-up.
    Only runs when results contain meaningful content worth reporting.
    """
    if test_mode or not execution_results:
        return ""

    trivial_actions = {
        "open_app",
        "quit_app",
        "open_project",
        "open_folder",
        "create_and_open",
        "open_terminal",
        "open_editor",
        "open_in_editor",
        "open_terminal_command",
        "open_url",
        "open_url_in_browser",
        "spotify_search_play",
        "search_and_play",
        "spotify_pause",
        "spotify_next",
        "spotify_prev",
        "spotify_volume",
        "play_music",
    }
    meaningful = [
        result
        for result in execution_results
        if result.get("status") == "ok"
        and result.get("action") not in trivial_actions
        and str(result.get("result", "")).strip()
        and str(result.get("result", "")).strip()
        not in {"speech only", "opened Cursor", "opened Spotify", "music paused"}
    ]
    if not meaningful:
        return ""

    results_text = "\n".join(
        f"  {result['action']}: {str(result.get('result', ''))[:80]}"
        for result in meaningful[:3]
    )
    prompt = f"""Butler just ran these actions and got these results:
{results_text}

Original plan was: {str(plan.get('speech', ''))[:100]}

In one SHORT sentence under 20 words, what should Butler say about what just happened?
Output ONLY the sentence."""

    raw = _raw_llm(prompt, model=model or OLLAMA_MODEL, max_tokens=60, temperature=0.4)
    return _normalize_response(raw, max_words=20, single_sentence=True)


def _rewrite_speech_with_agent_results(
    speech: str,
    execution_results: list,
    model: str | None = None,
) -> str:
    agent_results = _successful_agent_results(execution_results)
    if not agent_results:
        return ""

    prompt = f"""Butler just got these results from specialist agents:
{chr(10).join(agent_results[:2])}

Original speech: {speech}

Rewrite the speech to include the key info from those results.
Keep it under 45 words.
Output ONLY the new speech text."""

    raw = _raw_llm(prompt, model=model or OLLAMA_MODEL, max_tokens=120, temperature=0.4)
    rewritten = _normalize_response(raw, max_words=45)
    if not rewritten or rewritten == "Something went wrong.":
        return _normalize_response(agent_results[0], max_words=45)
    return rewritten


def _successful_agent_results(execution_results: list) -> list[str]:
    return [
        str(result.get("result", "")).strip()
        for result in execution_results
        if result.get("action") == "run_agent"
        and result.get("status") == "ok"
        and str(result.get("result", "")).strip()
    ]


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

    should_delay_speech = False
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

    sync_results = executor.run(sync_actions) if sync_actions else []
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
        from brain.ollama_client import check_vps_connection

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
    from brain.ollama_client import _get_ollama_url, _resolve_backend_model

    chosen = model or OLLAMA_MODEL
    generate_url, headers = _get_ollama_url()
    chat_url = generate_url.replace("/api/generate", "/api/chat")
    local_chat_url = f"{OLLAMA_LOCAL_URL.rstrip('/')}/api/chat"
    use_vps_backend = generate_url != f"{OLLAMA_LOCAL_URL.rstrip('/')}/api/generate"
    resolved_model = _resolve_backend_model(chosen, use_vps_backend)
    resolved_fallback = _resolve_backend_model(OLLAMA_FALLBACK, use_vps_backend)
    payload = {
        "model": resolved_model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {"temperature": temperature, "num_predict": max_tokens},
    }
    try:
        response = requests.post(
            chat_url,
            json=payload,
            headers=headers,
            timeout=20,
        )
        response.raise_for_status()
        return response.json().get("message", {}).get("content", "").strip()
    except requests.exceptions.ConnectionError:
        if chat_url != local_chat_url:
            response = requests.post(
                local_chat_url,
                json=payload,
                timeout=20,
            )
            response.raise_for_status()
            return response.json().get("message", {}).get("content", "").strip()
        return "Something went wrong."
    except Exception:
        if resolved_fallback and payload["model"] != resolved_fallback:
            payload["model"] = resolved_fallback
            try:
                response = requests.post(
                    chat_url,
                    json=payload,
                    headers=headers,
                    timeout=20,
                )
                response.raise_for_status()
                return response.json().get("message", {}).get("content", "").strip()
            except Exception:
                return "Something went wrong."
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
    except Exception:
        pass
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
        except Exception:
            pass

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

    if action.get("type") in {"run_agent", "ssh_open"} and not action.get("host"):
        host = _default_vps_host()
        if host:
            action["host"] = host

    if intent.intent == "docker_status" and _default_vps_host():
        action = {"type": "run_agent", "agent": "vps", "host": _default_vps_host()}

    return action


def _record(
    text: str,
    speech: str,
    actions: list,
    results: list | None = None,
    intent_name: str = "",
    learning_meta: dict | None = None,
) -> None:
    try:
        learning_payload = dict(learning_meta or {})
        normalized_text = " ".join(str(text or "").split()).strip()
        normalized_intent = " ".join(str(intent_name or "").split()).strip()
        now_mono = time.monotonic()
        with _LEARNING_TRACE_LOCK:
            previous = dict(_LAST_RESOLVED_COMMAND)
            _LAST_RESOLVED_COMMAND.update(
                {
                    "text": normalized_text,
                    "intent_name": normalized_intent,
                    "at": now_mono,
                }
            )
        previous_text = " ".join(str(previous.get("text", "")).split()).strip()
        previous_intent = " ".join(str(previous.get("intent_name", "")).split()).strip()
        previous_at = float(previous.get("at", 0.0) or 0.0)
        if (
            normalized_text
            and previous_text
            and normalized_intent
            and previous_intent == normalized_intent
            and previous_text.lower() != normalized_text.lower()
            and previous_at > 0
            and now_mono - previous_at <= 60
        ):
            learning_payload.update(
                {
                    "previous_age_s": round(now_mono - previous_at, 2),
                    "previous_intent": previous_intent,
                    "previous_text": previous_text,
                }
            )

        _remember_conversation_turn(text, intent_name or "reply", speech)
        # Add to three-tier long-term memory (Phase 6)
        try:
            from memory.long_term import add_to_working_memory
            add_to_working_memory(text[:200], speech[:200])
        except Exception:
            pass
        # Record RL episode for model improvement (Phase 11)
        try:
            from memory.rl_loop import record_episode
            _model = learning_meta.get("model", "") if learning_meta else ""
            _outcome = "success" if speech and not any(
                str(r.get("status", "")).lower() == "error"
                for r in (results or []) if isinstance(r, dict)
            ) else "failure"
            record_episode(text, intent_name or "unknown", _model, speech, _outcome)
        except Exception:
            pass
        record_session(text[:100], speech[:200], actions, results=results or [])
        save_session(
            {
                "timestamp": datetime.now().isoformat(),
                "speech": speech[:200],
                "actions": actions,
                "context_preview": text[:120],
            }
        )
        append_to_index(
            f"{datetime.now().strftime('%m/%d')} command: {text[:80]} -> {speech[:80]}"
        )
        touched = record_project_execution(text, speech, actions, results=results or [])
        with _LEARNING_TRACE_LOCK:
            analyze_and_learn(
                {
                    "text": text,
                    "speech": speech,
                    "actions": actions,
                    "results": results or [],
                    "intent_name": intent_name,
                    "projects": list(touched.keys()),
                    **learning_payload,
                }
            )
        try:
            from memory.graph import observe_project_relationships

            observe_project_relationships(
                text=text,
                speech=speech,
                actions=actions,
                touched_projects=list(touched.keys()),
            )
        except Exception:
            pass
    except Exception:
        pass


def _remember_project_state(action: dict) -> None:
    action_type = action.get("type")
    if action_type == "open_project":
        try:
            from projects import get_project

            project = get_project(action.get("name", ""))
            if not project:
                return
            update_project_state(
                project["name"],
                {
                    "last_workspace_path": project.get("path", ""),
                    "last_opened": datetime.now().isoformat(),
                },
            )
        except Exception:
            pass
        return

    if action_type not in {"open_editor", "create_and_open", "open_folder", "create_file_in_editor"}:
        return

    if action_type == "create_file_in_editor":
        directory = action.get("directory") or "~/Developer"
        filename = action.get("filename", "")
        project_name = Path(os.path.expanduser(directory)).name or "project"
        payload = {
            "last_workspace_path": directory,
            "last_editor": action.get("editor", ""),
        }
        if filename:
            payload["last_file"] = filename
        update_project_state(project_name, payload)
        return

    path = action.get("path", "")
    if not path:
        return
    expanded = os.path.expanduser(path)
    project_root = expanded
    if action_type == "open_editor" and Path(expanded).suffix:
        project_root = str(Path(expanded).parent)
    project_name = Path(project_root).name or "project"
    update_project_state(
        project_name,
        {
            "last_workspace_path": project_root,
            "last_editor": action.get("editor", ""),
            "last_opened": project_root,
        },
    )


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
    if not text:
        return
    state.transition(State.SPEAKING)
    if test_mode:
        print(f"[Butler would say]: {text}")
    else:
        speak(text)
        notify("Burry", text[:180], subtitle="Response")


def _speak_stream_chunk(text: str) -> None:
    cleaned = " ".join(str(text or "").split()).strip()
    if not cleaned:
        return
    state.transition(State.SPEAKING)
    speak(cleaned)


async def _stream_response_with_tts(prompt: str, model: str) -> str:
    """Stream LLM response and speak each sentence as it arrives.
    STEAL 3: user hears first words within 1-2 seconds instead of waiting 45s.
    Falls back silently if streaming fails.
    """
    from brain.ollama_client import stream_llm_tokens
    return await _stream_sentences_with_tts(stream_llm_tokens(prompt, model))


async def _stream_sentences_with_tts(sentence_stream) -> str:
    """Consume streamed sentence chunks and serialize speech so chunks are not dropped."""
    spoken_sentences: list[str] = []
    speech_queue: queue.Queue[str | None] = queue.Queue()

    def _speaker() -> None:
        while True:
            sentence = speech_queue.get()
            try:
                if sentence is None:
                    return
                speak(sentence)
            finally:
                speech_queue.task_done()

    state.transition(State.SPEAKING)
    speaker_thread = threading.Thread(target=_speaker, daemon=True, name="burry-stream-tts")
    speaker_thread.start()
    try:
        async for sentence in sentence_stream:
            cleaned = " ".join(str(sentence or "").split()).strip()
            if not cleaned:
                continue
            spoken_sentences.append(cleaned)
            speech_queue.put(cleaned)
        return " ".join(spoken_sentences).strip()
    except Exception:
        return ""
    finally:
        speech_queue.put(None)
        speech_queue.join()
        speaker_thread.join(timeout=10)


async def _stream_chat_response_with_tts(
    messages: list[dict],
    model: str,
    *,
    max_tokens: int = 140,
    temperature: float = 0.3,
) -> str:
    from brain.ollama_client import stream_chat_with_ollama

    return await _stream_sentences_with_tts(
        stream_chat_with_ollama(
            messages,
            model,
            max_tokens=max_tokens,
            temperature=temperature,
        )
    )


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
    """Return cached build_structured_context(). Rebuilds every 30 seconds."""
    global _CTX_CACHE, _CTX_CACHE_AT
    now = time.monotonic()
    with _CTX_CACHE_LOCK:
        if _CTX_CACHE is not None and now - _CTX_CACHE_AT < _CTX_CACHE_TTL_SECONDS:
            return _CTX_CACHE
    ctx = build_structured_context()
    with _CTX_CACHE_LOCK:
        _CTX_CACHE = ctx
        _CTX_CACHE_AT = now
    return ctx


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


def _handle_meta_intent(intent: IntentResult, test_mode: bool = False) -> bool:
    intent_name = getattr(intent, "name", getattr(intent, "intent", ""))

    if intent_name == "butler_sleep":
        response = "Going quiet. Say wake up to start again."
        _speak_or_print(response, test_mode=test_mode)
        _record(intent.raw, response, [], intent_name=intent_name)
        state.transition(State.IDLE)
        return True

    if intent_name == "butler_wake":
        response = "I'm listening."
        _speak_or_print(response, test_mode=test_mode)
        _record(intent.raw, response, [], intent_name=intent_name)
        state.transition(State.WAITING)
        return True

    if intent_name == "butler_help":
        _speak_or_print(HELP_TEXT, test_mode=test_mode)
        _record(intent.raw, HELP_TEXT, [], intent_name=intent_name)
        state.transition(State.WAITING)
        return True

    if intent_name == "butler_status":
        response = f"I'm {state.current.value}."
        _speak_or_print(response, test_mode=test_mode)
        _record(intent.raw, response, [], intent_name=intent_name)
        state.transition(State.WAITING)
        return True

    if intent_name == "mcp_status":
        try:
            from burry_mcp import describe_servers

            lines = describe_servers()
        except Exception:
            lines = []
        if not lines:
            response = "No M C P servers are configured right now."
        else:
            response = _normalize_response(". ".join(lines), max_words=22)
        _speak_or_print(response, test_mode=test_mode)
        _record(intent.raw, response, [], intent_name=intent_name)
        state.transition(State.WAITING)
        return True

    return False


@trace_command
def handle_input(text: str, test_mode: bool = False, model: str | None = None) -> None:
    _ensure_watcher_started()

    if not text or len(text.strip()) < 2:
        return
    if state.is_busy:
        try:
            _COMMAND_QUEUE.put_nowait(text)
            speak("Got it, finishing current task first.")
        except queue.Full:
            speak("Still busy, please wait.")
        return

    # Check skills FIRST before intent router (STEAL 4)
    try:
        from skills import match_skill
        skill, entities = match_skill(text)
        if skill:
            result = skill["execute"](text, entities)
            _speak_or_print(result.get("speech", "Done."), test_mode=test_mode)
            _record(text, result.get("speech", ""), result.get("actions", []))
            return
    except Exception:
        pass

    note_heard_text(text)
    add_event("stt.complete", {"text": text[:100]})
    state.transition(State.THINKING)
    effective_text = text
    intent = _resolve_pending_dialogue(text) or route(text)
    if _looks_like_followup_reference(text):
        resolved_text = _resolve_followup_text(text, model=model)
        normalized_original = " ".join(str(text or "").lower().split())
        normalized_resolved = " ".join(str(resolved_text or "").lower().split())
        if normalized_resolved and normalized_resolved != normalized_original:
            rerouted = route(resolved_text)
            if rerouted.name != "unknown" or intent.name in {"unknown", "question", "news"}:
                effective_text = resolved_text
                intent = rerouted
                print(f"[Router] follow-up resolved: {effective_text}")
    print(f"[Router] {intent.name} {intent.params} (conf={intent.confidence:.2f})")
    add_event("intent.resolved", {"intent": intent.name, "confidence": str(round(intent.confidence, 2))})
    note_intent(intent.name, intent.params, intent.confidence, raw=text)
    base_learning_meta = {
        "task_type": intent.name,
        "original_text": text,
        "resolved_text": effective_text if " ".join(effective_text.split()).lower() != " ".join(text.split()).lower() else "",
    }
    brain_learning_meta = {
        **base_learning_meta,
        "model": model or BUTLER_MODELS.get("voice") or OLLAMA_MODEL,
    }

    if _handle_meta_intent(intent, test_mode=test_mode):
        return

    if intent.name == "clarify_song":
        _set_pending_dialogue("spotify_song")
        _reply_without_action(
            text,
            get_quick_response(intent),
            test_mode=test_mode,
            intent_name=intent.name,
            learning_meta=base_learning_meta,
        )
        return

    if intent.name == "clarify_file":
        _set_pending_dialogue("file_name", editor=intent.params.get("editor", "auto"))
        _reply_without_action(
            text,
            get_quick_response(intent),
            test_mode=test_mode,
            intent_name=intent.name,
            learning_meta=base_learning_meta,
        )
        return

    if intent.name == "unknown":
        response = _unknown_response_for_text(effective_text)
        if not response and _should_use_brain_for_unknown(effective_text):
            # Fast-path: direct keyword routing so user never waits for LLM to pick a tool
            import re as _re
            _low = effective_text.lower()
            if _re.search(r"\b(research|look up|look into|find out|investigate)\b", _low):
                _speak_or_print("On it, researching now.", test_mode=test_mode)
                _query = _re.sub(r"^(research|look up|look into|find out|investigate)\s+", "", _low).strip()
                tool_reply = {"speech": "", "actions": [], "results": []}
                try:
                    from brain.toolkit import get_toolkit
                    import brain.tools_registry  # noqa
                    result = get_toolkit().call("deep_research", question=_query or effective_text)
                    tool_reply = {"speech": str(result), "actions": [{"type": "deep_research"}], "results": [{"status": "ok", "result": str(result)}]}
                except Exception as _exc:
                    tool_reply = {"speech": f"Research failed: {_exc}", "actions": [], "results": []}
                response = tool_reply.get("speech", "") or "I couldn't find anything on that."
                _speak_or_print(response, test_mode=test_mode)
                _record(text, response, tool_reply.get("actions", []), results=tool_reply.get("results", []), intent_name="deep_research", learning_meta=brain_learning_meta)
                state.transition(State.WAITING if not test_mode else State.IDLE)
                return
            ctx = _get_cached_context()
            _speak_or_print("Let me think about that.", test_mode=test_mode)
            tool_reply = _tool_chat_response(
                effective_text,
                ctx,
                model=model,
                intent_name=intent.name,
                intent_confidence=intent.confidence,
                stream_speech=not test_mode,
            )
            response = tool_reply.get("speech", "") or _unknown_brain_response(effective_text, model=model)
            if response:
                if not tool_reply.get("spoken"):
                    _speak_or_print(response, test_mode=test_mode)
                _record(
                    text,
                    response,
                    tool_reply.get("actions", []),
                    results=tool_reply.get("results", []),
                    intent_name="unknown",
                    learning_meta=brain_learning_meta,
                )
                state.transition(State.WAITING if not test_mode else State.IDLE)
                return
        if not response:
            response = "I didn't catch that. Say open, search, compose mail, or latest news."
        _reply_without_action(
            text,
            response,
            test_mode=test_mode,
            intent_name="unknown",
            learning_meta=brain_learning_meta,
        )
        return

    _clear_pending_dialogue()
    ctx = _get_cached_context()
    _warn_if_search_offline()
    action = _contextualize_action(intent.to_action(), intent, ctx)

    if not intent.needs_llm():
        response = get_quick_response(intent) or "Done."
        _run_actions_with_response(
            text=text,
            response=response,
            actions=[action] if action else [],
            intent_name=intent.name,
            test_mode=test_mode,
            model=model,
            learning_meta=base_learning_meta,
        )
        return

    if intent.name == "what_next":
        plan = _deterministic_project_plan(ctx)
        if not plan:
            tool_reply = _tool_chat_response(
                effective_text,
                ctx,
                model=model,
                intent_name=intent.name,
                intent_confidence=intent.confidence,
                stream_speech=not test_mode,
            )
            speech = tool_reply.get("speech", "") or "Back on mac-butler. Want to jump in?"
            if not tool_reply.get("spoken"):
                _speak_or_print(speech, test_mode=test_mode)
            _record(
                text,
                speech,
                tool_reply.get("actions", []),
                results=tool_reply.get("results", []),
                intent_name=intent.name,
                learning_meta=brain_learning_meta,
            )
            state.transition(State.WAITING if not test_mode else State.IDLE)
            return
        speech = _normalize_response(plan.get("speech", ""), max_words=40) or "Back on mac-butler. Want to jump in?"
        actions = [action for action in plan.get("actions", []) if isinstance(action, dict)]
        if actions:
            _run_actions_with_response(
                text=text,
                response=speech,
                actions=actions,
                intent_name=intent.name,
                test_mode=test_mode,
                model=model,
                learning_meta=brain_learning_meta,
            )
            return
        _reply_without_action(
            text,
            speech,
            test_mode=test_mode,
            intent_name=intent.name,
            learning_meta=brain_learning_meta,
        )
        return

    if intent.name == "question":
        # Acknowledge immediately so user knows we're working
        import re as _re2
        _low2 = effective_text.lower()
        if _re2.search(r"\b(research|look up|look into|find out|investigate)\b", _low2):
            _speak_or_print("On it, researching now.", test_mode=test_mode)
            _q2 = _re2.sub(r"^(research|look up|look into|find out|investigate)\s+", "", _low2).strip()
            try:
                from brain.toolkit import get_toolkit
                import brain.tools_registry  # noqa
                result = get_toolkit().call("deep_research", question=_q2 or effective_text)
                speech = str(result)
            except Exception as _exc:
                speech = f"Research failed: {_exc}"
            _speak_or_print(speech, test_mode=test_mode)
            _record(text, speech, [{"type": "deep_research"}], results=[{"status": "ok"}], intent_name="question", learning_meta=brain_learning_meta)
            state.transition(State.WAITING if not test_mode else State.IDLE)
            return
        _speak_or_print("One moment.", test_mode=test_mode)
        tool_reply = _tool_chat_response(
            effective_text,
            ctx,
            model=model,
            intent_name=intent.name,
            intent_confidence=intent.confidence,
            stream_speech=not test_mode,
        )
        speech = tool_reply.get("speech", "") or "I don't know yet. Ask again in a shorter way."
        if not tool_reply.get("spoken"):
            _speak_or_print(speech, test_mode=test_mode)
        _record(
            text,
            speech,
            tool_reply.get("actions", []),
            results=tool_reply.get("results", []),
            intent_name=intent.name,
            learning_meta=brain_learning_meta,
        )
        state.transition(State.WAITING if not test_mode else State.IDLE)
        return

    tool_reply = _tool_chat_response(
        effective_text,
        ctx,
        model=model,
        intent_name=intent.name,
        intent_confidence=intent.confidence,
        stream_speech=not test_mode,
    )
    response = tool_reply.get("speech", "")
    if not response:
        prompt = _build_voice_prompt(intent, effective_text)
        fast_model = model or OLLAMA_FALLBACK or OLLAMA_MODEL
        response = _normalize_response(
            _raw_llm(prompt, model=fast_model, max_tokens=80),
            max_words=24,
        )
    if not response or response == "Something went wrong.":
        response = "I don't know yet. Ask again in a shorter way."
    if not tool_reply.get("spoken"):
        _speak_or_print(response, test_mode=test_mode)
    _record(
        text,
        response,
        tool_reply.get("actions", []),
        results=tool_reply.get("results", []),
        intent_name=intent.name,
        learning_meta=brain_learning_meta,
    )
    state.transition(State.WAITING if not test_mode else State.IDLE)


handle_command = handle_input


def _on_state_change(old_state: State, new_state: State) -> None:
    """Drain queued commands when butler becomes free."""
    busy = {State.THINKING, State.SPEAKING, State.LISTENING}
    if old_state in busy and new_state not in busy:
        _process_next_queued_command()


state.on_change(_on_state_change)


def run_interactive(use_stt: bool = False, model: str | None = None, test_mode: bool = False) -> None:
    _ensure_watcher_started()
    print("\n" + "=" * 50)
    print("  🎩 Mac Butler — Interactive Mode")
    print("=" * 50)
    print("Type commands or press Ctrl+C to exit")
    print("Examples: play mockingbird, open cursor, note: test this, check vps\n")

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

    try:
        while True:
            user_input = input("\n[You] ").strip()
            if user_input.lower() in {"exit", "quit", "bye"}:
                break
            if user_input:
                handle_command(user_input, test_mode=test_mode, model=model)
    except (KeyboardInterrupt, EOFError):
        pass
    finally:
        state.transition(State.IDLE)
        print("\n[Butler] Goodbye.")


def _save_backbone_session_state() -> None:
    try:
        from brain.agentscope_backbone import get_backbone
        from memory.long_term import save_session_state

        backbone = get_backbone()
        if getattr(backbone, "agent", None) is not None:
            save_session_state(backbone.agent)
    except Exception:
        pass


def _handle_shutdown_signal(_signum, _frame) -> None:
    _save_backbone_session_state()
    raise SystemExit(0)


def _install_shutdown_handlers() -> None:
    global _SHUTDOWN_HANDLERS_INSTALLED
    if _SHUTDOWN_HANDLERS_INSTALLED:
        return
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _handle_shutdown_signal)
        except Exception:
            continue
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
    args = parser.parse_args()

    lightweight_command_mode = bool(args.command and not args.interactive and not args.stt and not args.briefing)

    if lightweight_command_mode:
        try:
            from skills import load_skills

            load_skills()
        except Exception:
            pass
    else:
        _ensure_watcher_started()
        start_ambient_daemon()
        start_wake_word_daemon()
        # Start iMessage channel so you can message Burry from iPhone (STEAL 8)
        try:
            from channels.imessage_channel import start_imessage_channel

            start_imessage_channel()
        except Exception:
            pass
        # Load skills at startup (STEAL 4)
        try:
            from skills import load_skills

            load_skills()
        except Exception:
            pass
        # Load configured MCP servers into toolkit (Phase 2)
        try:
            from brain.mcp_client import load_configured_mcp_servers
            from brain.toolkit import get_toolkit
            import brain.tools_registry  # noqa

            load_configured_mcp_servers(get_toolkit())
        except Exception:
            pass
        # Start A2A server — prefer AgentScope native A2A when available.
        try:
            from brain.agentscope_backbone import get_backbone
            from channels.a2a_server import start_agentscope_a2a

            backbone = get_backbone(model_name=args.model)
            start_agentscope_a2a(backbone.agent)
        except Exception:
            pass
        _report_brain_backend_status()

    if args.command:
        handle_command(args.command, test_mode=args.test, model=args.model)
        _save_backbone_session_state()
        return

    if args.interactive:
        run_interactive(use_stt=args.stt, model=args.model, test_mode=args.test)
        _save_backbone_session_state()
        return

    if args.briefing or (not args.interactive and not args.command):
        run_startup_briefing(test_mode=args.test, model=args.model)
        _save_backbone_session_state()
        return


if __name__ == "__main__":
    main()
