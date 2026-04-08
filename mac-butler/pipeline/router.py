"""pipeline/router.py — pending dialogue state and lane selection."""

from __future__ import annotations

import os
import queue
import re
import threading

import brain.agentscope_backbone as backbone
import brain.toolkit as toolkit_module
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
    "spotify_play",
    "spotify_pause",
    "spotify_next",
    "spotify_prev",
    "spotify_volume",
    "spotify_mode",
    "pause_video",
    "volume_set",
    "system_volume",
    "create_file",
    "create_folder",
    "git_status",
    "git_push",
    "compose_email",
    "whatsapp_open",
    "whatsapp_send",
    "screenshot",
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


def _set_pending_dialogue(kind: str, **metadata) -> None:
    b = _butler()
    with b._PENDING_DIALOGUE_LOCK:
        b._PENDING_DIALOGUE = {"kind": kind, **metadata}


def _get_pending_dialogue() -> dict | None:
    b = _butler()
    with b._PENDING_DIALOGUE_LOCK:
        if b._PENDING_DIALOGUE is None:
            return None
        return dict(b._PENDING_DIALOGUE)


def _clear_pending_dialogue() -> None:
    b = _butler()
    with b._PENDING_DIALOGUE_LOCK:
        b._PENDING_DIALOGUE = None


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
    pending = _get_pending_dialogue()
    if not pending:
        return None

    routed = b.route(text)
    if routed.name != "unknown":
        _clear_pending_dialogue()
        return routed

    if pending.get("kind") == "spotify_song":
        candidate = b.clean_song_query(re.sub(r"^play\s+", "", text.lower().strip()))
        if not b.is_ambiguous_song_query(candidate):
            _clear_pending_dialogue()
            return b.IntentResult("spotify_play", {"song": candidate}, confidence=0.85, raw=text)
        return b.IntentResult("clarify_song", confidence=0.3, raw=text)

    if pending.get("kind") == "file_name":
        candidate = b.extract_requested_filename(text) or _filename_from_follow_up(text)
        if candidate:
            _clear_pending_dialogue()
            return b.IntentResult(
                "create_file",
                {
                    "filename": candidate,
                    "editor": pending.get("editor", "auto"),
                },
                confidence=0.85,
                raw=text,
            )
        return b.IntentResult(
            "clarify_file",
            {"editor": pending.get("editor", "auto")},
            confidence=0.3,
            raw=text,
        )

    return None


def _unknown_response_for_text(text: str) -> str:
    b = _butler()
    lowered = text.lower()
    if any(token in lowered for token in ("spotify", "song", "track", "artist", "album")):
        _set_pending_dialogue("spotify_song")
        return "I didn't catch the song. Say the title and artist."
    if any(token in lowered for token in ("file", "document")) and any(
        token in lowered for token in ("make", "create", "new", "name", "named", "called")
    ):
        _set_pending_dialogue("file_name", editor=b.detect_editor_choice(text))
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
    response = get_quick_response(intent) or "Working on it."
    b._speak_or_print(response, test_mode=test_mode)

    action_seed = intent.to_action()
    action = b._contextualize_action(action_seed, intent, {}) if action_seed else None
    if action:
        if action.get("type") == "run_agent":
            try:
                from agents.runner import run_agent_async

                agent_name = str(action.get("agent", "")).strip()
                run_agent_async(
                    agent_name,
                    {key: value for key, value in action.items() if key not in ("type", "agent")},
                )
            except Exception as exc:
                print(f"[Background] Agent dispatch failed: {exc}")
        else:
            worker = threading.Thread(
                target=_run_background_action,
                args=(action,),
                daemon=True,
                name=f"bg-{intent.name}",
            )
            worker.start()

    b._record(text, response, [action] if action else [], intent_name=intent.name)
    b.state.transition(b.State.WAITING if not test_mode else b.State.IDLE)


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

    lowered_raw = " ".join(text.lower().split()).strip()
    if lowered_raw in {"stop", "sleep", "quiet", "be quiet", "go quiet", "shut up", "stop listening", "go to sleep", "bye", "goodbye"}:
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

    early_intent = b.route(text)

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

    if lowered_raw in _DETERMINISTIC_CASUAL_RESPONSES:
        b.note_heard_text(text)
        b.add_event("stt.complete", {"text": text[:100]})
        response = _DETERMINISTIC_CASUAL_RESPONSES[lowered_raw]
        b._speak_or_print(response, test_mode=test_mode)
        b._record(text, response, [], intent_name="casual")
        b.state.transition(b.State.WAITING if not test_mode else b.State.IDLE)
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

    try:
        from skills import match_skill

        skill, entities = match_skill(text)
        if skill:
            result = skill["execute"](text, entities)
            b._speak_or_print(result.get("speech", "Done."), test_mode=test_mode)
            b._record(text, result.get("speech", ""), result.get("actions", []))
            return
    except Exception as exc:
        print(f"[Butler] silent error: {exc}")

    b.note_heard_text(text)
    b.add_event("stt.complete", {"text": text[:100]})
    b.state.transition(b.State.THINKING)
    effective_text = text
    intent = _resolve_pending_dialogue(text) or early_intent
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
        _set_pending_dialogue("spotify_song")
        b._reply_without_action(
            text,
            get_quick_response(intent),
            test_mode=test_mode,
            intent_name=intent.name,
            learning_meta=base_learning_meta,
        )
        return

    if intent.name == "clarify_file":
        _set_pending_dialogue("file_name", editor=intent.params.get("editor", "auto"))
        b._reply_without_action(
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
            smart = b._smart_reply(effective_text, {}, model=model)
            if smart and smart not in ("NEEDS_TOOLS", "NEEDS_CONTEXT"):
                b._speak_or_print(smart, test_mode=test_mode)
                b._record(text, smart, [], intent_name="smart_reply", learning_meta=brain_learning_meta)
                b.state.transition(b.State.WAITING if not test_mode else b.State.IDLE)
                return
            if smart == "NEEDS_CONTEXT":
                ctx = b._get_fast_context()
                smart2 = b._smart_reply(effective_text, ctx, model=model)
                if smart2 and smart2 not in ("NEEDS_TOOLS", "NEEDS_CONTEXT"):
                    b._speak_or_print(smart2, test_mode=test_mode)
                    b._record(text, smart2, [], intent_name="smart_reply", learning_meta=brain_learning_meta)
                    b.state.transition(b.State.WAITING if not test_mode else b.State.IDLE)
                    return
            if _dispatch_research(effective_text, text, test_mode=test_mode, learning_meta=brain_learning_meta, intent_name="deep_research"):
                return
            ctx = b._get_cached_context()
            b._speak_or_print("Let me think about that.", test_mode=test_mode)
            tool_reply = b._safe_tool_chat_response(
                effective_text,
                ctx,
                model=model,
                intent_name=intent.name,
                intent_confidence=intent.confidence,
                stream_speech=not test_mode,
                test_mode=test_mode,
            )
            response = tool_reply.get("speech", "") or "I am not sure about that."
            if not tool_reply.get("spoken"):
                b._speak_or_print(response, test_mode=test_mode)
            b._record(
                text,
                response,
                tool_reply.get("actions", []),
                results=tool_reply.get("results", []),
                intent_name="unknown",
                learning_meta=brain_learning_meta,
            )
            b.state.transition(b.State.WAITING if not test_mode else b.State.IDLE)
            return
        if not response:
            response = "I didn't catch that. Say open, search, compose mail, or latest news."
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
        tool_reply = b._safe_tool_chat_response(
            effective_text,
            ctx,
            model=model,
            intent_name=intent.name,
            intent_confidence=intent.confidence,
            stream_speech=not test_mode,
            test_mode=test_mode,
        )
        speech = tool_reply.get("speech", "") or "I don't know yet. Ask again in a shorter way."
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
        response = "I don't know yet. Ask again in a shorter way."
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
