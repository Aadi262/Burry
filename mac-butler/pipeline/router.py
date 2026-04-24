"""pipeline/router.py — pending dialogue state and lane selection."""

from __future__ import annotations

import os
import queue
import re
import threading

import brain.agentscope_backbone as backbone
import brain.toolkit as toolkit_module
from capabilities import build_action, get_tool_spec, looks_like_current_role_lookup, plan_semantic_task
from runtime.tracing import trace_command


def _butler():
    import butler  # noqa: PLC0415

    return butler


INSTANT_LANE_INTENTS = {
    "open_app",
    "close_app",
    "open_project",
    "open_editor_window",
    "open_last_workspace",
    "open_codex",
    "browser_new_tab",
    "browser_search",
    "browser_close_tab",
    "browser_close_window",
    "browser_window",
    "browser_go_back",
    "browser_refresh",
    "spotify_play",
    "spotify_pause",
    "spotify_next",
    "spotify_prev",
    "spotify_volume",
    "play_music",
    "spotify_mode",
    "pause_video",
    "volume_set",
    "volume_up",
    "volume_down",
    "system_volume",
    "create_file",
    "create_folder",
    "git_status",
    "git_push",
    "compose_email",
    "whatsapp_open",
    "whatsapp_send",
    "screenshot",
    "lock_screen",
    "show_desktop",
    "sleep_mac",
    "set_reminder",
    "obsidian_note",
    "butler_sleep",
    "butler_wake",
    "butler_help",
    "butler_status",
    "mcp_status",
    "greeting",
}

BACKGROUND_LANE_INTENTS = {
    "news",
    "market",
    "hackernews",
    "reddit",
    "github_trending",
    "vps_status",
    "docker_status",
}

_DETERMINISTIC_CASUAL_RESPONSES = {
    "thank you": "You're welcome.",
    "thanks": "No problem.",
    "never mind": "Got it.",
    "nevermind": "Got it.",
    "cancel": "Cancelled.",
    "okay": "Alright.",
    "ok": "Alright.",
    "got it": "Good.",
    "cool": "Anything else?",
    "nice": "Anything else?",
    "what can you do": "I can open apps, play music, search the web, check news, send emails, take screenshots, and more. Just ask.",
    "what do you do": "I can open apps, play music, search the web, check news, send emails, take screenshots, and more. Just ask.",
    "are you there": "I'm here.",
    "you there": "I'm here.",
}

_RESEARCH_RE = re.compile(r"\b(research|look up|look into|find out|investigate)\b")
_RESEARCH_STRIP_RE = re.compile(r"^(research|look up|look into|find out|investigate)\s+")
_GENERIC_UNKNOWN_REPLY = "I'm not sure what you want done yet. Tell me the outcome you want, and I'll handle it or ask one quick question."
_GENERIC_QUESTION_REPLY = "I couldn't answer that cleanly yet. Ask it another way or tell me to look it up."
_LOW_SIGNAL_REPLIES = {
    "",
    "something went wrong.",
    "i'm still thinking, give me a moment.",
}
_EXPLICIT_TOOL_QUESTION_RE = re.compile(
    r"\b("
    r"latest|current|today|right now|news|weather|forecast|temperature|stock price|share price|"
    r"look it up|search the web|google|browse|read this page|open this url|url|link"
    r")\b"
)
_PENDING_FIELD_PROMPTS = {
    "subject": "What is the subject?",
    "body": "What should the body say?",
    "filename": "What should I name the file?",
    "song": "Which song should I play?",
    "name": "What should I call it?",
    "query": "What should I look for?",
}


def _set_pending_dialogue(kind: str, **metadata) -> None:
    b = _butler()
    b.ctx.set_pending(kind, **metadata)


def _get_pending_dialogue() -> dict | None:
    b = _butler()
    return b.ctx.get_pending()


def _clear_pending_dialogue() -> None:
    b = _butler()
    b.ctx.clear_pending()


def _route_initial_intent(text: str, *, test_mode: bool = False):
    """Phase 1 source of truth: pending -> instant -> skills -> classifier."""
    b = _butler()
    if b.ctx.has_pending():
        pending_intent = _resolve_pending_dialogue(text)
        if pending_intent is not None:
            return pending_intent

    instant_intent = b.instant_route(text)
    if instant_intent is not None:
        return instant_intent

    if _run_skill_match(text, test_mode=test_mode):
        return None

    return b.route(text, allow_instant=False)


def _run_skill_match(text: str, *, test_mode: bool = False) -> bool:
    b = _butler()
    try:
        from skills import match_skill

        skill, entities = match_skill(text)
        if not skill:
            return False
        result = skill["execute"](text, entities)
        speech = result.get("speech", "Done.")
    except Exception as exc:
        print(f"[Butler] silent error: {exc}")
        return False

    b.note_heard_text(text)
    b.add_event("stt.complete", {"text": text[:100]})
    b._speak_or_print(speech, test_mode=test_mode)
    b._record(text, speech, result.get("actions", []), intent_name=skill.get("name", "skill"))
    return True


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


def _email_followup_value(text: str, field: str) -> str:
    candidate = _normalize_email_followup(text, field)
    return candidate.strip().strip("\"'.,!?")


def _normalize_email_followup(text: str, field: str) -> str:
    cleaned = " ".join(str(text or "").split()).strip()
    if not cleaned:
        return ""

    if field == "subject":
        cleaned = re.sub(
            r"^(?:with\s+subject|subject\s+is|the\s+subject(?:\s+is)?|subject)\s+",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
    else:
        cleaned = re.sub(
            r"^(?:with\s+body|body\s+is|the\s+body\s+says|body\s+should\s+say|the\s+body|body|message\s+is|message|saying)\s+",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
    return cleaned.strip()


def _pending_prompt(field: str, pending: dict | None = None) -> str:
    message = _PENDING_FIELD_PROMPTS.get(field)
    if message:
        return message
    label = str(field or "value").replace("_", " ").strip() or "value"
    return f"What should the {label} be?"


def _normalize_pending_value(kind: str, field: str, text: str) -> str:
    b = _butler()
    cleaned = " ".join(str(text or "").split()).strip()
    if not cleaned:
        return ""
    if field == "subject":
        return _email_followup_value(cleaned, "subject")
    if field == "body":
        return _email_followup_value(cleaned, "body")
    if field == "filename":
        return b.extract_requested_filename(cleaned) or _filename_from_follow_up(cleaned)
    if field == "song":
        candidate = b.clean_song_query(re.sub(r"^play\s+", "", cleaned.lower().strip()))
        return "" if b.is_ambiguous_song_query(candidate) else candidate
    return cleaned.strip().strip("\"'.,!?")


def _coerce_pending_state(pending: dict | None) -> dict | None:
    if not pending:
        return None
    kind = str(pending.get("kind", "") or "").strip()
    data = dict(pending.get("data") or {})
    required = list(pending.get("required") or [])

    if kind == "spotify_song":
        kind = "spotify_play"
        required = required or ["song"]
    elif kind == "file_name":
        kind = "create_file"
        required = required or ["filename"]
        if "editor" in pending and "editor" not in data:
            data["editor"] = pending.get("editor", "auto")
    elif kind == "pending_email":
        kind = "compose_email"
        required = required or ["subject", "body"]
        for key in ("recipient", "subject", "body"):
            if key in pending and key not in data:
                data[key] = pending.get(key, "")

    snapshot = dict(pending)
    snapshot["kind"] = kind
    snapshot["data"] = data
    snapshot["required"] = required
    snapshot.update(data)
    missing = [field for field in required if not str(data.get(field, "") or "").strip()]
    snapshot["missing"] = missing
    snapshot["next_field"] = missing[0] if missing else ""
    return snapshot


def get_quick_response(intent) -> str:
    b = _butler()
    if hasattr(intent, "quick_response"):
        return intent.quick_response()
    template = b.QUICK_RESPONSES.get(intent.intent, "")
    if not template:
        return ""
    try:
        return template.format(**intent.params)
    except Exception:
        return template


def _resolve_pending_dialogue(text: str):
    b = _butler()
    pending = _coerce_pending_state(_get_pending_dialogue())
    if not pending:
        return None

    routed = b.route(text)
    if routed.name != "unknown":
        _clear_pending_dialogue()
        return routed

    next_field = str(pending.get("next_field", "") or "").strip()
    kind = str(pending.get("kind", "") or "").strip()
    if next_field:
        value = _normalize_pending_value(kind, next_field, text)
        if not value:
            if kind == "spotify_play":
                return b.IntentResult("clarify_song", confidence=0.3, raw=text)
            if kind == "create_file":
                return b.IntentResult(
                    "clarify_file",
                    {"editor": pending.get("editor", "auto")},
                    confidence=0.3,
                    raw=text,
                )
            return b.IntentResult(
                "clarify_pending",
                {"message": _pending_prompt(next_field, pending)},
                confidence=0.3,
                raw=text,
            )

        filled = b.ctx.fill_pending(value, field=next_field) or {}
        filled = _coerce_pending_state(filled) or {}
        if filled.get("missing"):
            return b.IntentResult(
                "clarify_pending",
                {"message": _pending_prompt(str(filled.get("next_field", "") or ""), filled)},
                confidence=0.85,
                raw=text,
            )
        data = dict(filled.get("data") or {})
        _clear_pending_dialogue()
        return b.IntentResult(kind, data, confidence=0.85, raw=text)

    return None


def _unknown_response_for_text(text: str) -> str:
    b = _butler()
    lowered = text.lower()
    if any(token in lowered for token in ("spotify", "song", "track", "artist", "album")):
        _set_pending_dialogue("spotify_play", data={}, required=["song"])
        return _pending_prompt("song")
    if any(token in lowered for token in ("file", "document")) and any(
        token in lowered for token in ("make", "create", "new", "name", "named", "called")
    ):
        _set_pending_dialogue(
            "create_file",
            data={"editor": b.detect_editor_choice(text)},
            required=["filename"],
        )
        return _pending_prompt("filename")
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
    b = _butler()
    lowered = " ".join(str(text or "").lower().split())
    if len(lowered.split()) < 2:
        return False
    if any(lowered.startswith(prefix) for prefix in b._FOLLOWUP_PREFIXES):
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


def _clarification_question_for_intent(intent) -> str:
    name = str(getattr(intent, "name", getattr(intent, "intent", "")) or "").strip()
    params = getattr(intent, "params", {}) if isinstance(getattr(intent, "params", {}), dict) else {}

    if name == "unknown":
        return "What do you want me to do?"
    if name == "open_app":
        app = str(params.get("app", "") or params.get("name", "")).strip()
        return f"Open {app}?" if app else "Which app should I open?"
    if name == "play_music":
        song = str(params.get("song", "") or "").strip()
        return f"Play {song}?" if song else "What should I play?"
    if name == "compose_email":
        recipient = str(params.get("recipient", "") or params.get("to", "")).strip()
        return f"Email {recipient}?" if recipient else "Who is the email to?"
    if name == "create_folder":
        folder = str(params.get("name", "") or "").strip()
        return f"Create {folder}?" if folder else "What should I name the folder?"
    if name == "create_file":
        filename = str(params.get("name", "") or params.get("filename", "")).strip()
        return f"Create {filename}?" if filename else "What should I name the file?"
    if name == "news":
        topic = str(params.get("topic", "") or params.get("region", "")).strip()
        return f"News on {topic}?" if topic else "What news topic?"
    if name == "web_search":
        query = str(params.get("query", "") or "").strip()
        return f"Search for {query}?" if query else "What should I search for?"
    if name == "open_url":
        return "Which website should I open?"
    if name == "browser_tab":
        return "Open, close, or search?"
    if name == "run_command":
        cmd = str(params.get("cmd", "") or "").strip()
        return f"Run {cmd}?" if cmd else "Which command should I run?"
    if name == "system_info":
        query = str(params.get("query", "") or "").strip()
        return f"Check {query}?" if query else "Battery, wifi, or storage?"
    return "What exactly do you want?"


def _question_prefers_tools(text: str) -> bool:
    lowered = " ".join(str(text or "").lower().split())
    if not lowered:
        return False
    if _RESEARCH_RE.search(lowered):
        return True
    if re.search(r"https?://|www\.", lowered):
        return True
    if looks_like_current_role_lookup(lowered):
        return True
    if re.search(r"\b(?:how is|how's)\s+.+\s+doing\b", lowered):
        return True
    if any(
        phrase in lowered
        for phrase in (
            "project status",
            "status of ",
            "progress on ",
            "read this page",
            "read the page",
            "read this article",
            "current page",
            "this article",
        )
    ):
        return True
    return _EXPLICIT_TOOL_QUESTION_RE.search(lowered) is not None


def _lightweight_reply(text: str, *, model: str | None = None) -> str | None:
    b = _butler()
    reply = b._smart_reply(text, {}, model=model)
    if reply == "NEEDS_CONTEXT":
        reply = b._smart_reply(text, b._get_fast_context(), model=model)
    cleaned = " ".join(str(reply or "").split()).strip()
    if cleaned.lower() in _LOW_SIGNAL_REPLIES:
        return None
    return reply


def _respond_lightweight(
    raw_text: str,
    response: str,
    *,
    test_mode: bool = False,
    intent_name: str,
    learning_meta: dict | None = None,
) -> None:
    b = _butler()
    b._speak_or_print(response, test_mode=test_mode)
    b._record(raw_text, response, [], intent_name=intent_name, learning_meta=learning_meta)
    b.state.transition(b.State.WAITING if not test_mode else b.State.IDLE)


def _handle_meta_intent(intent, test_mode: bool = False) -> bool:
    b = _butler()
    intent_name = getattr(intent, "name", getattr(intent, "intent", ""))

    if intent_name == "butler_sleep":
        b._clear_pending_command_state()
        response = "Going quiet. Say wake up to start again."
        b._speak_or_print(response, test_mode=test_mode)
        b._record(intent.raw, response, [], intent_name=intent_name)
        b.state.transition(b.State.IDLE)
        return True

    if intent_name == "butler_wake":
        response = "I'm listening."
        b._speak_or_print(response, test_mode=test_mode)
        b._record(intent.raw, response, [], intent_name=intent_name)
        b.state.transition(b.State.WAITING)
        return True

    if intent_name == "butler_help":
        b._speak_or_print(b.HELP_TEXT, test_mode=test_mode)
        b._record(intent.raw, b.HELP_TEXT, [], intent_name=intent_name)
        b.state.transition(b.State.WAITING)
        return True

    if intent_name == "butler_status":
        response = f"I'm {b.state.current.value}."
        b._speak_or_print(response, test_mode=test_mode)
        b._record(intent.raw, response, [], intent_name=intent_name)
        b.state.transition(b.State.WAITING)
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
            response = b._normalize_response(". ".join(lines), max_words=22)
        b._speak_or_print(response, test_mode=test_mode)
        b._record(intent.raw, response, [], intent_name=intent_name)
        b.state.transition(b.State.WAITING)
        return True

    return False


def _execute_instant(intent, text: str, *, test_mode: bool = False) -> None:
    b = _butler()
    if _handle_meta_intent(intent, test_mode=test_mode):
        return

    if intent.name == "greeting" or b._looks_like_greeting(text):
        response = b._deterministic_greeting_response(text)
        b._speak_or_print(response, test_mode=test_mode)
        b._record(text, response, [], intent_name="greeting")
        b.state.transition(b.State.WAITING if not test_mode else b.State.IDLE)
        return

    if intent.name == "compose_email":
        recipient = str(intent.params.get("recipient", "") or "").strip()
        subject = str(intent.params.get("subject", "") or "").strip()
        body = str(intent.params.get("body", "") or "").strip()
        if recipient and not subject:
            _set_pending_dialogue(
                "compose_email",
                data={"recipient": recipient, "to": recipient, "subject": "", "body": ""},
                required=["subject", "body"],
            )
            response = _pending_prompt("subject")
            b._speak_or_print(response, test_mode=test_mode)
            b._record(text, response, [], intent_name=intent.name)
            b.state.transition(b.State.WAITING if not test_mode else b.State.IDLE)
            return
        if recipient and subject and not body:
            _set_pending_dialogue(
                "compose_email",
                data={"recipient": recipient, "to": recipient, "subject": subject, "body": ""},
                required=["body"],
            )
            response = _pending_prompt("body")
            b._speak_or_print(response, test_mode=test_mode)
            b._record(text, response, [], intent_name=intent.name)
            b.state.transition(b.State.WAITING if not test_mode else b.State.IDLE)
            return

    action = intent.to_action()
    response = get_quick_response(intent) or "Done."
    results: list[dict] = []

    if action:
        b.note_tool_started(b._action_trace_name(action), b._action_trace_detail(action))
        try:
            results = b.executor.run([action])
        except Exception as exc:
            b.note_tool_finished(b._action_trace_name(action), "error", str(exc)[:180])
            response = b._normalize_response(str(exc), max_words=18, single_sentence=True) or "That failed."
            results = [{"action": action.get("type"), "status": "error", "error": str(exc)}]
        else:
            result = results[0] if results else {}
            status = str(result.get("status", "ok") or "ok").strip().lower()
            b.note_tool_finished(
                b._action_trace_name(action),
                status or "ok",
                b._action_trace_result_detail(result, b._action_trace_detail(action)),
            )
            if status == "ok":
                b._remember_project_state(action)
            else:
                response = (
                    b._normalize_response(str(result.get("error", "")), max_words=18, single_sentence=True)
                    or "That failed."
                )

    b._speak_or_print(response, test_mode=test_mode)
    b._record(
        text,
        response,
        [action] if action else [],
        results=results,
        intent_name=intent.name,
    )
    b.state.transition(b.State.WAITING if not test_mode else b.State.IDLE)


def _run_background_action(action: dict) -> None:
    b = _butler()
    b.note_tool_started(b._action_trace_name(action), b._action_trace_detail(action))
    try:
        results = b.executor.run([action])
    except Exception as exc:
        b.note_tool_finished(b._action_trace_name(action), "error", str(exc)[:180])
        return

    result = results[0] if results else {}
    status = str(result.get("status", "ok") or "ok").strip().lower()
    b.note_tool_finished(
        b._action_trace_name(action),
        status or "ok",
        b._action_trace_result_detail(result, b._action_trace_detail(action)),
    )
    if status == "ok":
        b._remember_project_state(action)


def _execute_background(intent, text: str, *, test_mode: bool = False) -> None:
    b = _butler()
    action_seed = intent.to_action()
    action = b._contextualize_action(action_seed, intent, {}) if action_seed else None
    if action:
        if action.get("type") == "run_agent":
            try:
                from agents.runner import run_agent, run_agent_async

                agent_name = str(action.get("agent", "")).strip()
                agent_payload = {key: value for key, value in action.items() if key not in ("type", "agent")}
                if agent_name == "news":
                    result = run_agent(agent_name, agent_payload)
                    response = str(result.get("result", "") or "No news found.").strip() or "No news found."
                    b._speak_or_print(response, test_mode=test_mode)
                    b._record(
                        text,
                        response,
                        [action],
                        results=[result],
                        intent_name=intent.name,
                    )
                    b.state.transition(b.State.WAITING if not test_mode else b.State.IDLE)
                    return
                response = get_quick_response(intent) or "Working on it."
                b._speak_or_print(response, test_mode=test_mode)
                run_agent_async(
                    agent_name,
                    agent_payload,
                )
            except Exception as exc:
                print(f"[Background] Agent dispatch failed: {exc}")
        else:
            response = get_quick_response(intent) or "Working on it."
            b._speak_or_print(response, test_mode=test_mode)
            worker = threading.Thread(
                target=_run_background_action,
                args=(action,),
                daemon=True,
                name=f"bg-{intent.name}",
            )
            worker.start()
    else:
        response = get_quick_response(intent) or "Working on it."
        b._speak_or_print(response, test_mode=test_mode)

    b._record(text, response, [action] if action else [], intent_name=intent.name)
    b.state.transition(b.State.WAITING if not test_mode else b.State.IDLE)


def _semantic_learning_meta(learning_meta: dict | None, task) -> dict:
    payload = dict(learning_meta or {})
    payload["semantic_goal"] = str(task.goal or "")[:160]
    payload["semantic_source"] = str(task.source or "semantic_planner")
    if task.tool:
        payload["semantic_tool"] = task.tool
    return payload


def _execute_semantic_task(task, text: str, *, test_mode: bool = False, learning_meta: dict | None = None) -> bool:
    b = _butler()
    intent_name = str(task.intent_name or task.tool or task.kind or "semantic_task").strip()
    meta = _semantic_learning_meta(learning_meta, task)

    if getattr(task, "needs_clarification", False):
        question = str(task.clarification or "Can you clarify that?").strip() or "Can you clarify that?"
        b.note_intent(intent_name, getattr(task, "args", {}), getattr(task, "confidence", 0.0), raw=text)
        b._reply_without_action(
            text,
            question,
            test_mode=test_mode,
            intent_name=intent_name,
            learning_meta=meta,
        )
        return True

    if getattr(task, "answer", "") and not getattr(task, "tool", ""):
        answer = str(task.answer).strip()
        if not answer:
            return False
        b.note_intent(intent_name, getattr(task, "args", {}), getattr(task, "confidence", 0.0), raw=text)
        b._reply_without_action(
            text,
            answer,
            test_mode=test_mode,
            intent_name=intent_name,
            learning_meta=meta,
        )
        return True

    tool_name = str(getattr(task, "tool", "") or "").strip()
    spec = get_tool_spec(tool_name)
    action = build_action(tool_name, getattr(task, "args", {}))
    if spec is None or action is None:
        return False

    b.note_intent(intent_name, getattr(task, "args", {}), getattr(task, "confidence", 0.0), raw=text)
    b.add_event("semantic.accepted", {"intent": intent_name, "tool": spec.name, "goal": str(task.goal or "")[:140]})

    if spec.sync_execution:
        b.note_tool_started(b._action_trace_name(action), b._action_trace_detail(action))
        try:
            results = b.executor.run([action])
        except Exception as exc:
            b.note_tool_finished(b._action_trace_name(action), "error", str(exc)[:180])
            failure = b._normalize_response(str(exc), max_words=18, single_sentence=True) or "That failed."
            b._reply_without_action(
                text,
                failure,
                test_mode=test_mode,
                intent_name=intent_name,
                learning_meta=meta,
            )
            return True

        result = results[0] if results else {}
        status = str(result.get("status", "ok") or "ok").strip().lower()
        b.note_tool_finished(
            b._action_trace_name(action),
            status or "ok",
            b._action_trace_result_detail(result, b._action_trace_detail(action)),
        )
        if status == "ok":
            raw_result = str(result.get("result", "") or "").strip()
            response = b._normalize_response(raw_result, max_words=48) or str(task.quick_response or spec.quick_response or "Done.").strip()
        else:
            response = b._normalize_response(str(result.get("error", "") or ""), max_words=18, single_sentence=True) or "That failed."
        b._speak_or_print(response, test_mode=test_mode)
        b._record(
            text,
            response,
            [action],
            results=results,
            intent_name=intent_name,
            learning_meta=meta,
        )
        b.state.transition(b.State.WAITING if not test_mode else b.State.IDLE)
        return True

    response = str(task.quick_response or spec.quick_response or "On it.").strip() or "On it."
    b._run_actions_with_response(
        text=text,
        response=response,
        actions=[action],
        intent_name=intent_name,
        test_mode=test_mode,
        learning_meta=meta,
    )
    return True


def _dispatch_research(
    effective_text: str,
    raw_text: str,
    *,
    test_mode: bool = False,
    learning_meta: dict | None = None,
    intent_name: str = "deep_research",
) -> bool:
    b = _butler()
    lowered = effective_text.lower()
    if not _RESEARCH_RE.search(lowered):
        return False

    b._speak_or_print("On it, researching now.", test_mode=test_mode)
    query = _RESEARCH_STRIP_RE.sub("", lowered).strip()
    tool_reply: dict = {"speech": "", "actions": [], "results": []}
    try:
        result = toolkit_module.get_toolkit().call("deep_research", question=query or effective_text)
        tool_reply = {
            "speech": str(result),
            "actions": [{"type": "deep_research"}],
            "results": [{"status": "ok", "result": str(result)}],
        }
    except Exception as exc:
        tool_reply = {"speech": f"Research failed: {exc}", "actions": [], "results": []}

    response = tool_reply.get("speech", "") or "I couldn't find anything on that."
    b._speak_or_print(response, test_mode=test_mode)
    b._record(
        raw_text,
        response,
        tool_reply.get("actions", []),
        results=tool_reply.get("results", []),
        intent_name=intent_name,
        learning_meta=learning_meta,
    )
    b.state.transition(b.State.WAITING if not test_mode else b.State.IDLE)
    return True


@trace_command
def handle_input(text: str, test_mode: bool = False, model: str | None = None) -> None:
    b = _butler()
    if not test_mode and not os.environ.get("PYTEST_CURRENT_TEST"):
        b._ensure_watcher_started()

    if not text or len(text.strip()) < 2:
        return
    b.ctx.add_user(text)

    lowered_raw = " ".join(text.lower().split()).strip()
    if lowered_raw in {"quiet", "be quiet", "go quiet", "shut up", "stop listening", "go to sleep burry", "burry sleep", "bye", "goodbye"}:
        b.note_heard_text(text)
        b.add_event("stt.complete", {"text": text[:100]})
        b._clear_pending_command_state()
        try:
            backbone.interrupt_agentscope_turn("stop")
        except Exception as exc:
            print(f"[Butler] silent error: {exc}")
        b._speak_or_print("Going quiet. Say wake up to start again.", test_mode=test_mode)
        b._record(text, "Going quiet. Say wake up to start again.", [], intent_name="butler_sleep")
        b.state.transition(b.State.IDLE)
        return

    early_intent = _route_initial_intent(text, test_mode=test_mode)
    if early_intent is None:
        return

    if lowered_raw in _DETERMINISTIC_CASUAL_RESPONSES:
        b.note_heard_text(text)
        b.add_event("stt.complete", {"text": text[:100]})
        response = _DETERMINISTIC_CASUAL_RESPONSES[lowered_raw]
        b._speak_or_print(response, test_mode=test_mode)
        b._record(text, response, [], intent_name="casual")
        b.state.transition(b.State.WAITING if not test_mode else b.State.IDLE)
        return

    semantic_task = plan_semantic_task(text, current_intent=early_intent.name) if early_intent.name == "unknown" else None

    if 0.4 <= float(getattr(early_intent, "confidence", 0.0) or 0.0) <= 0.7 and early_intent.name not in {"conversation", "question", "unknown"}:
        b.note_heard_text(text)
        b.add_event("stt.complete", {"text": text[:100]})
        b.note_intent(early_intent.name, early_intent.params, early_intent.confidence, raw=text)
        b._reply_without_action(
            text,
            _clarification_question_for_intent(early_intent),
            test_mode=test_mode,
            intent_name="clarify_intent",
            learning_meta={"task_type": "clarify_intent", "original_intent": early_intent.name},
        )
        return

    if semantic_task is not None and getattr(semantic_task, "force_override", False):
        b.note_heard_text(text)
        b.add_event("stt.complete", {"text": text[:100]})
        if _execute_semantic_task(semantic_task, text, test_mode=test_mode):
            return

    if early_intent.name in INSTANT_LANE_INTENTS:
        b.note_heard_text(text)
        b.add_event("stt.complete", {"text": text[:100]})
        b.note_intent(early_intent.name, early_intent.params, early_intent.confidence, raw=text)
        if b.state.is_busy:
            b._clear_pending_command_state()
            try:
                backbone.interrupt_agentscope_turn(text)
            except Exception as exc:
                print(f"[Butler] silent error: {exc}")
            b.add_event("interrupt.instant", {"intent": early_intent.name})
        _execute_instant(early_intent, text, test_mode=test_mode)
        return

    if early_intent.name in BACKGROUND_LANE_INTENTS:
        b.note_heard_text(text)
        b.add_event("stt.complete", {"text": text[:100]})
        b.note_intent(early_intent.name, early_intent.params, early_intent.confidence, raw=text)
        _execute_background(early_intent, text, test_mode=test_mode)
        return

    if b.state.is_busy:
        try:
            b._COMMAND_QUEUE.put_nowait(text)
            b._speak_or_print("Got it, finishing current task first.", test_mode=test_mode)
        except queue.Full:
            b._speak_or_print("Still busy, please wait.", test_mode=test_mode)
        return

    b.note_heard_text(text)
    b.add_event("stt.complete", {"text": text[:100]})
    b.state.transition(b.State.THINKING)
    effective_text = text
    intent = early_intent
    if _looks_like_followup_reference(text):
        resolved_text = b._resolve_followup_text(text, model=model)
        normalized_original = " ".join(str(text or "").lower().split())
        normalized_resolved = " ".join(str(resolved_text or "").lower().split())
        if normalized_resolved and normalized_resolved != normalized_original:
            rerouted = b.route(resolved_text)
            if rerouted.name != "unknown" or intent.name in {"unknown", "question", "news"}:
                effective_text = resolved_text
                intent = rerouted
                print(f"[Router] follow-up resolved: {effective_text}")
    print(f"[Router] {intent.name} {intent.params} (conf={intent.confidence:.2f})")
    b.add_event("intent.resolved", {"intent": intent.name, "confidence": str(round(intent.confidence, 2))})
    b.note_intent(intent.name, intent.params, intent.confidence, raw=text)
    base_learning_meta = {
        "task_type": intent.name,
        "original_text": text,
        "resolved_text": effective_text if " ".join(effective_text.split()).lower() != " ".join(text.split()).lower() else "",
    }
    brain_learning_meta = {
        **base_learning_meta,
        "model": model or b.BUTLER_MODELS.get("voice") or b.OLLAMA_MODEL,
    }

    if _handle_meta_intent(intent, test_mode=test_mode):
        return

    if intent.name == "clarify_song":
        _set_pending_dialogue("spotify_play", data={}, required=["song"])
        b._reply_without_action(
            text,
            _pending_prompt("song"),
            test_mode=test_mode,
            intent_name=intent.name,
            learning_meta=base_learning_meta,
        )
        return

    if intent.name == "clarify_file":
        _set_pending_dialogue(
            "create_file",
            data={"editor": intent.params.get("editor", "auto")},
            required=["filename"],
        )
        b._reply_without_action(
            text,
            _pending_prompt("filename"),
            test_mode=test_mode,
            intent_name=intent.name,
            learning_meta=base_learning_meta,
        )
        return

    if intent.name == "clarify_pending":
        response = str(intent.params.get("message", "") or "").strip() or "What should I fill in?"
        b._reply_without_action(
            text,
            response,
            test_mode=test_mode,
            intent_name="clarify_pending",
            learning_meta=base_learning_meta,
        )
        return

    if intent.name == "conversation":
        try:
            from brain.conversation import generate_conversation_reply
        except Exception:
            generate_conversation_reply = lambda _text: ""

        speech = generate_conversation_reply(effective_text) or "Say it straight. What are we actually doing?"
        b._reply_without_action(
            text,
            speech,
            test_mode=test_mode,
            intent_name=intent.name,
            learning_meta=brain_learning_meta,
        )
        return

    if intent.name == "unknown":
        response = _unknown_response_for_text(effective_text)
        if not response and _should_use_brain_for_unknown(effective_text):
            smart = _lightweight_reply(effective_text, model=model)
            if smart and smart not in ("NEEDS_TOOLS", "NEEDS_CONTEXT"):
                _respond_lightweight(
                    text,
                    smart,
                    test_mode=test_mode,
                    intent_name="smart_reply",
                    learning_meta=brain_learning_meta,
                )
                return
        if not response and semantic_task is not None:
            if _execute_semantic_task(semantic_task, text, test_mode=test_mode, learning_meta=brain_learning_meta):
                return
        if not response and _dispatch_research(effective_text, text, test_mode=test_mode, learning_meta=brain_learning_meta, intent_name="deep_research"):
            return
        if not response:
            response = _GENERIC_UNKNOWN_REPLY
        b._reply_without_action(
            text,
            response,
            test_mode=test_mode,
            intent_name="unknown",
            learning_meta=brain_learning_meta,
        )
        return

    _clear_pending_dialogue()
    action_seed = intent.to_action()

    if not intent.needs_llm():
        action_ctx = b._get_cached_context() if b._action_needs_runtime_context(action_seed) else {}
        action = b._contextualize_action(action_seed, intent, action_ctx)
        response = get_quick_response(intent) or "Done."
        b._run_actions_with_response(
            text=text,
            response=response,
            actions=[action] if action else [],
            intent_name=intent.name,
            test_mode=test_mode,
            model=model,
            learning_meta=base_learning_meta,
        )
        return

    if intent.name == "greeting":
        b._reply_without_action(
            text,
            b._deterministic_greeting_response(effective_text),
            test_mode=test_mode,
            intent_name=intent.name,
            learning_meta=base_learning_meta,
        )
        return

    ctx = b._get_cached_context()
    b._warn_if_search_offline()
    action = b._contextualize_action(action_seed, intent, ctx)

    if intent.name == "what_next":
        plan = b._deterministic_project_plan(ctx)
        if not plan:
            tool_reply = b._safe_tool_chat_response(
                effective_text,
                ctx,
                model=model,
                intent_name=intent.name,
                intent_confidence=intent.confidence,
                stream_speech=not test_mode,
                test_mode=test_mode,
            )
            speech = tool_reply.get("speech", "") or "Back on mac-butler. Want to jump in?"
            if not tool_reply.get("spoken"):
                b._speak_or_print(speech, test_mode=test_mode)
            b._record(
                text,
                speech,
                tool_reply.get("actions", []),
                results=tool_reply.get("results", []),
                intent_name=intent.name,
                learning_meta=brain_learning_meta,
            )
            b.state.transition(b.State.WAITING if not test_mode else b.State.IDLE)
            return
        speech = b._normalize_response(plan.get("speech", ""), max_words=40) or "Back on mac-butler. Want to jump in?"
        actions = [item for item in plan.get("actions", []) if isinstance(item, dict)]
        if actions:
            b._run_actions_with_response(
                text=text,
                response=speech,
                actions=actions,
                intent_name=intent.name,
                test_mode=test_mode,
                model=model,
                learning_meta=brain_learning_meta,
            )
            return
        b._reply_without_action(
            text,
            speech,
            test_mode=test_mode,
            intent_name=intent.name,
            learning_meta=brain_learning_meta,
        )
        return

    if intent.name == "question":
        if _dispatch_research(effective_text, text, test_mode=test_mode, learning_meta=brain_learning_meta, intent_name="question"):
            return
        prefers_tools = _question_prefers_tools(effective_text)
        smart = None if prefers_tools else _lightweight_reply(effective_text, model=model)
        if not prefers_tools and smart and smart not in ("NEEDS_TOOLS", "NEEDS_CONTEXT"):
            _respond_lightweight(
                text,
                smart,
                test_mode=test_mode,
                intent_name="smart_reply",
                learning_meta=brain_learning_meta,
            )
            return

        if not prefers_tools and smart not in {"NEEDS_TOOLS", "NEEDS_CONTEXT"}:
            fast_reply = b._fast_path_llm_response(intent.name, effective_text, ctx, model=model)
            normalized_fast_reply = " ".join(str(fast_reply or "").split()).strip().lower()
            if fast_reply and normalized_fast_reply not in _LOW_SIGNAL_REPLIES:
                _respond_lightweight(
                    text,
                    fast_reply,
                    test_mode=test_mode,
                    intent_name="fast_path_question",
                    learning_meta=brain_learning_meta,
                )
                return

        question_task = None
        if smart == "NEEDS_TOOLS" or prefers_tools:
            question_task = plan_semantic_task(effective_text, current_intent=intent.name)
            if question_task is not None and _execute_semantic_task(question_task, text, test_mode=test_mode, learning_meta=brain_learning_meta):
                return

            tool_reply = b._safe_tool_chat_response(
                effective_text,
                ctx,
                model=model,
                intent_name=intent.name,
                intent_confidence=intent.confidence,
                stream_speech=not test_mode,
                test_mode=test_mode,
            )
            speech = tool_reply.get("speech", "") or _GENERIC_QUESTION_REPLY
            if not tool_reply.get("spoken"):
                b._speak_or_print(speech, test_mode=test_mode)
            b._record(
                text,
                speech,
                tool_reply.get("actions", []),
                results=tool_reply.get("results", []),
                intent_name=intent.name,
                learning_meta=brain_learning_meta,
            )
            b.state.transition(b.State.WAITING if not test_mode else b.State.IDLE)
            return

        b._reply_without_action(
            text,
            _GENERIC_QUESTION_REPLY,
            test_mode=test_mode,
            intent_name=intent.name,
            learning_meta=brain_learning_meta,
        )
        return

    tool_reply = b._safe_tool_chat_response(
        effective_text,
        ctx,
        model=model,
        intent_name=intent.name,
        intent_confidence=intent.confidence,
        stream_speech=not test_mode,
        test_mode=test_mode,
    )
    response = tool_reply.get("speech", "")
    if not response:
        prompt = b._build_voice_prompt(intent, effective_text)
        fast_model = model or b.OLLAMA_FALLBACK or b.OLLAMA_MODEL
        response = b._normalize_response(
            b._raw_llm(prompt, model=fast_model, max_tokens=80),
            max_words=24,
        )
    if not response or response == "Something went wrong.":
        response = _GENERIC_QUESTION_REPLY
    if not tool_reply.get("spoken"):
        b._speak_or_print(response, test_mode=test_mode)
    b._record(
        text,
        response,
        tool_reply.get("actions", []),
        results=tool_reply.get("results", []),
        intent_name=intent.name,
        learning_meta=brain_learning_meta,
    )
    b.state.transition(b.State.WAITING if not test_mode else b.State.IDLE)
