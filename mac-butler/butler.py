#!/usr/bin/env python3
"""
butler.py
Mac Butler Orchestrator v4
Pipeline: Trigger -> STT -> Intent Router -> Executor -> LLM only if needed -> TTS
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import threading
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
from context import build_structured_context
from context.mac_activity import get_state_for_context, load_state as load_mac_state, start_watcher
from executor.engine import Executor
from intents.router import (
    IntentResult,
    PROJECT_MAP,
    clean_song_query,
    detect_editor_choice,
    extract_requested_filename,
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
from state import State, state
from voice import listen_continuous, speak

executor = Executor()
_WATCHER_LOCK = threading.Lock()
_WATCHER_STARTED = False
_PENDING_DIALOGUE_LOCK = threading.Lock()
_PENDING_DIALOGUE: dict | None = None

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
    "Try: play mockingbird, open cursor, note: remember this, "
    "check VPS, git status, or ask what's next."
)

_briefing_done = False
_SEARCH_CHECKED = False
_BRAIN_STATUS_CHECKED = False


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
    global _SEARCH_CHECKED
    if _SEARCH_CHECKED:
        return
    _SEARCH_CHECKED = True
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
    return "Try again?"


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


def _reply_without_action(text: str, response: str, test_mode: bool = False) -> None:
    _speak_or_print(response, test_mode=test_mode)
    _record(text, response, [])
    state.transition(State.WAITING if not test_mode else State.IDLE)


def _build_voice_prompt(intent: IntentResult, text: str) -> str:
    if intent.name == "what_next":
        ctx = build_structured_context()
        mac_state = get_state_for_context()
        return f"""You are Butler, Aditya's local operator.

Current Mac state:
{mac_state}

Current work context:
{ctx['formatted'][:320]}

User asked: "{text}"

Answer in under 20 words.
Be specific to current work.
Recommend the single next step.
Output ONLY the response text:"""

    ctx = build_structured_context()
    return f"""You are Butler, a concise local voice operator for Aditya.
His main projects are mac-butler and email-infra.

Current work context:
{ctx['formatted'][:220]}

User asked: "{text}"

Answer directly in under 20 words.
Use mac-butler or email-infra by name when clearly relevant.
Never explain uncertainty or hedge.
If context is sparse, ask one short binary clarifying question instead of guessing.
Output ONLY the response text:"""


def _brain_context_text(ctx: dict, user_text: str | None = None) -> str:
    parts = []
    formatted = str(ctx.get("formatted", "")).strip()

    if user_text:
        parts.append(f"[USER REQUEST]\n  {user_text}")
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
                parts.insert(1 if snapshot else 0, _strip_context_section(formatted, "[TASK LIST]"))
        elif formatted:
            parts.insert(0, formatted)
    elif formatted:
        parts.append(formatted)

    return "\n\n".join(part for part in parts if part).strip()


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
    next_tasks = [str(item).strip() for item in (project.get("next_tasks") or []) if str(item).strip()]
    blockers = [str(item).strip() for item in (project.get("blockers") or []) if str(item).strip()]

    first_task = _spoken_task(next_tasks[0] if next_tasks else "review the current status file", 8)
    raw_second_task = str(next_tasks[1]).strip() if len(next_tasks) > 1 else ""
    second_task = _spoken_task(raw_second_task, 5) if raw_second_task and len(raw_second_task.split()) <= 5 else ""
    raw_blocker = str(blockers[0]).strip() if blockers else ""
    blocker = _clip_words(raw_blocker, 7) if raw_blocker and len(raw_blocker.split()) <= 7 else ""

    lead = f"You're already in {name}" if in_workspace else f"{name} is the clearest next move"
    task_clause = f"Start with {first_task}."
    if second_task and second_task.lower() != first_task.lower() and len(f"{first_task} {second_task}".split()) <= 12:
        task_clause = f"Start with {first_task}, then {second_task}."

    question = (
        "Say open it, start it, or switch."
        if startup
        else (
            "Want the first step?"
            if in_workspace
            else "Want me to open it or map the first step?"
        )
    )

    variants = []
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
    triggers = (
        "latest",
        "news",
        "recent",
        "hackernews",
        "hacker news",
        "reddit",
        "market pulse",
        "trending repos",
        "trending repositories",
        "look up",
        "search",
        "find",
        "what is",
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
    return any(trigger in lowered for trigger in triggers)


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
        topic = re.sub(r"\b(what is|what's|tell me|show me|give me|the|latest|recent|news|about)\b", " ", lowered)
        topic = re.sub(r"\s+", " ", topic).strip(" .") or "AI and tech news"
        return {
            "speech": f"Checking the latest {topic}.",
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

    if any(token in lowered for token in ("what is", "look up", "search", "find")):
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
    test_mode: bool = False,
    model: str | None = None,
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
            state.transition(State.IDLE)
            return final_response, results

        print("[Executor] after run: done (test mode)")
        print(f"[Butler]: {response}")
        state.transition(State.IDLE)
        return response, []

    should_delay_speech = any(action.get("type") == "run_agent" for action in actions)
    speaker_thread = None
    if response and not should_delay_speech:
        speaker_thread = threading.Thread(
            target=speak,
            args=(response,),
            daemon=True,
        )
        speaker_thread.start()

    results = executor.run(actions) if actions else []
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
    if first_error:
        final_response = _normalize_response(first_error, max_words=18, single_sentence=True) or "That failed."
    else:
        successful_agent_results = _successful_agent_results(results)
        direct_agent_response = _normalize_response(
            successful_agent_results[0] if successful_agent_results else "",
            max_words=45,
        )
        if run_agent_only and direct_agent_response:
            final_response = direct_agent_response
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

    _record(text, final_response, actions, results=results)
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
    for project, path in PROJECT_MAP.items():
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


def _record(text: str, speech: str, actions: list, results: list | None = None) -> None:
    try:
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
        analyze_and_learn({"actions": actions, "speech": speech})
        record_project_execution(text, speech, actions, results=results or [])
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
    ctx = build_structured_context()
    _warn_if_search_offline()
    plan = _deterministic_project_plan(ctx, startup=True)
    if not plan:
        context_text = _brain_context_text(ctx, "startup briefing")
        plan = _plan_with_brain(context_text, model=model)
    speech = _normalize_response(plan.get("speech", ""), max_words=35)
    if not speech:
        speech = "Back on mac-butler. Want to jump in?"
    if DAILY_INTEL_ENABLED:
        intel_line = _startup_intelligence_line()
        if intel_line:
            speech = _normalize_response(f"{speech} {intel_line}", max_words=55)

    actions = [action for action in plan.get("actions", []) if isinstance(action, dict)]
    if actions:
        _run_actions_with_response(
            text="startup briefing",
            response=speech,
            actions=actions,
            test_mode=test_mode,
            model=model,
        )
        return

    _speak_or_print(speech, test_mode=test_mode)
    _record("startup briefing", speech, [])
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
        response = "Going quiet."
        _speak_or_print(response, test_mode=test_mode)
        _record(intent.raw, response, [])
        state.transition(State.IDLE)
        return True

    if intent_name == "butler_help":
        _speak_or_print(HELP_TEXT, test_mode=test_mode)
        _record(intent.raw, HELP_TEXT, [])
        state.transition(State.WAITING)
        return True

    if intent_name == "butler_status":
        response = f"I'm {state.current.value}."
        _speak_or_print(response, test_mode=test_mode)
        _record(intent.raw, response, [])
        state.transition(State.WAITING)
        return True

    return False


def handle_command(text: str, test_mode: bool = False, model: str | None = None) -> None:
    _ensure_watcher_started()

    if not text or len(text.strip()) < 2:
        return
    if state.is_busy:
        print("[Butler] Still processing previous command")
        return

    state.transition(State.THINKING)
    intent = _resolve_pending_dialogue(text) or route(text)
    print(f"[Router] {intent.name} {intent.params} (conf={intent.confidence:.2f})")

    if _handle_meta_intent(intent, test_mode=test_mode):
        return

    if intent.name == "clarify_song":
        _set_pending_dialogue("spotify_song")
        _reply_without_action(text, get_quick_response(intent), test_mode=test_mode)
        return

    if intent.name == "clarify_file":
        _set_pending_dialogue("file_name", editor=intent.params.get("editor", "auto"))
        _reply_without_action(text, get_quick_response(intent), test_mode=test_mode)
        return

    if intent.name == "unknown":
        _reply_without_action(text, _unknown_response_for_text(text), test_mode=test_mode)
        return

    _clear_pending_dialogue()
    ctx = build_structured_context()
    _warn_if_search_offline()
    action = _contextualize_action(intent.to_action(), intent, ctx)

    if not intent.needs_llm():
        response = get_quick_response(intent) or "Done."
        _run_actions_with_response(
            text=text,
            response=response,
            actions=[action] if action else [],
            test_mode=test_mode,
            model=model,
        )
        return

    if intent.name == "what_next":
        plan = _deterministic_project_plan(ctx) or _plan_with_brain(_brain_context_text(ctx, text), model=model)
        speech = _normalize_response(plan.get("speech", ""), max_words=40) or "Back on mac-butler. Want to jump in?"
        actions = [action for action in plan.get("actions", []) if isinstance(action, dict)]
        if actions:
            _run_actions_with_response(
                text=text,
                response=speech,
                actions=actions,
                test_mode=test_mode,
                model=model,
            )
            return
        _reply_without_action(text, speech, test_mode=test_mode)
        return

    if intent.name == "question" and _question_needs_brain_agents(text):
        plan = _direct_agent_plan_for_text(text) or _plan_with_brain(_brain_context_text(ctx, text), model=model)
        speech = _normalize_response(plan.get("speech", ""), max_words=45) or "I don't know yet. Ask again in a shorter way."
        actions = [action for action in plan.get("actions", []) if isinstance(action, dict)]
        if actions:
            _run_actions_with_response(
                text=text,
                response=speech,
                actions=actions,
                test_mode=test_mode,
                model=model,
            )
            return
        _reply_without_action(text, speech, test_mode=test_mode)
        return

    prompt = _build_voice_prompt(intent, text)
    fast_model = model or OLLAMA_FALLBACK or OLLAMA_MODEL
    response = _normalize_response(
        _raw_llm(prompt, model=fast_model, max_tokens=80),
        max_words=24,
    )
    if not response or response == "Something went wrong.":
        response = "I don't know yet. Ask again in a shorter way."

    _reply_without_action(text, response, test_mode=test_mode)


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


def main() -> None:
    _ensure_watcher_started()
    _report_brain_backend_status()
    parser = argparse.ArgumentParser(description="Mac Butler")
    parser.add_argument("--test", action="store_true", help="Print-only, no voice or execution")
    parser.add_argument("--model", default=None, help="Override Ollama model")
    parser.add_argument("--interactive", "-i", action="store_true", help="Interactive command mode")
    parser.add_argument("--stt", action="store_true", help="Use voice STT input")
    parser.add_argument("--briefing", action="store_true", help="Run startup briefing only")
    parser.add_argument("--command", "-c", default=None, help="Run a single command")
    args = parser.parse_args()

    if args.command:
        handle_command(args.command, test_mode=args.test, model=args.model)
        return

    if args.interactive:
        run_interactive(use_stt=args.stt, model=args.model, test_mode=args.test)
        return

    if args.briefing or (not args.interactive and not args.command):
        run_startup_briefing(test_mode=args.test, model=args.model)
        return


if __name__ == "__main__":
    main()
