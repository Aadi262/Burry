"""pipeline/orchestrator.py — fast-path and AgentScope orchestration."""

from __future__ import annotations

import asyncio
import json
import queue
import re

import requests

import brain.agentscope_backbone as backbone
import brain.ollama_client as ollama_client
import brain.toolkit as toolkit_module
import memory.store as memory_store
from brain.query_analyzer import analyze_query
from brain.tools_registry import TOOLS


def _butler():
    import butler  # noqa: PLC0415

    return butler


def _recent_dialogue_context() -> str:
    b = _butler()
    conversation = b._conversation_context_text()
    if conversation:
        return conversation

    try:
        runtime_state = b.load_runtime_state()
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
        r"\bhow are (?:you|u)\b",
        r"\bhow r u\b",
        r"^good (?:morning|afternoon|evening)\b",
    )
    return any(re.search(pattern, lowered) is not None for pattern in patterns)


def _deterministic_greeting_response(text: str) -> str:
    lowered = " ".join(str(text or "").lower().split())
    if re.search(r"\bhow are (?:you|u)\b", lowered) or re.search(r"\bhow r u\b", lowered):
        return "I'm good. What do you need?"
    if lowered.startswith("good morning"):
        return "Morning. What do you need?"
    if lowered.startswith("good afternoon"):
        return "Afternoon. What do you need?"
    if lowered.startswith("good evening"):
        return "Evening. What do you need?"
    return "Hey. What do you need?"


def _should_use_fast_path_intent(intent_name: str, intent_confidence: float, text: str) -> bool:
    b = _butler()
    if intent_name == "greeting":
        return True
    if intent_name in b.FAST_PATH_INTENTS and intent_confidence >= b.FAST_PATH_CONFIDENCE:
        return True
    return intent_name == "unknown" and _looks_like_greeting(text)


def _fast_path_prompt(intent_name: str, text: str, ctx: dict) -> str:
    b = _butler()
    formatted = str(ctx.get("formatted", "") or "").strip()[:220]
    dialogue = b._recent_turns_prompt_text() or _recent_dialogue_context()
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
    b = _butler()
    if intent_name == "greeting" or _looks_like_greeting(text):
        return _deterministic_greeting_response(text)

    prompt = _fast_path_prompt(intent_name, text, ctx)
    voice_model = b.pick_butler_model("voice", override=model)
    response = b._call(
        prompt,
        voice_model,
        temperature=0.25,
        max_tokens=150,
        timeout_hint="voice",
    )
    return b._normalize_response(response, max_words=28)


_SMART_REPLY_SYSTEM = (
    "You are Burry, a local Mac AI assistant. Answer in 1-2 sentences maximum. "
    "If you need tools or research say exactly NEEDS_TOOLS. "
    "If you need project or task context say exactly NEEDS_CONTEXT."
)
_SMART_REPLY_MODEL = "gemma4:e4b"


def _smart_reply(text: str, ctx: dict, *, model: str | None = None) -> str | None:
    b = _butler()
    fast_model = model or _SMART_REPLY_MODEL
    generate_url, headers = b._get_ollama_url()
    chat_url = generate_url.replace("/api/generate", "/api/chat")
    use_vps_backend = generate_url != f"{b.OLLAMA_LOCAL_URL.rstrip('/')}/api/generate"
    resolved_model = b._resolve_backend_model(fast_model, use_vps_backend)

    messages = [{"role": "system", "content": _SMART_REPLY_SYSTEM}]
    if ctx:
        formatted = ctx.get("formatted", "")
        if formatted:
            messages.append(
                {
                    "role": "system",
                    "content": f"Current context:\n{formatted[:600]}",
                }
            )
    messages.append({"role": "user", "content": text})

    payload = {
        "model": resolved_model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": 0.1, "num_predict": 80},
    }
    try:
        response = requests.post(chat_url, json=payload, headers=headers, timeout=15)
        response.raise_for_status()
        raw = response.json().get("message", {}).get("content", "").strip()
        if not raw:
            return None
        if "NEEDS_TOOLS" in raw:
            return "NEEDS_TOOLS"
        if "NEEDS_CONTEXT" in raw:
            return "NEEDS_CONTEXT"
        return raw
    except Exception:
        return None


def _unknown_brain_response(text: str, model: str | None = None) -> str:
    b = _butler()
    ctx = b._get_cached_context()
    dialogue = b._recent_turns_prompt_text() or _recent_dialogue_context()
    prompt = f"""You are Butler in an active voice session.

Current work context:
{ctx.get('formatted', '')[:220]}

{dialogue}

User just said: "{text}"

If the user refers to "that", "it", or previous work, resolve it from the last Butler reply.
Reply in under 18 words.
If the request is still unclear, ask one short clarifying question instead of saying try again.
Output ONLY the response text."""
    fast_model = model or b.OLLAMA_FALLBACK or b.OLLAMA_MODEL
    response = b._normalize_response(
        b._raw_llm(prompt, model=fast_model, max_tokens=80),
        max_words=18,
    )
    if not response or response == "Something went wrong.":
        return ""
    return response


def _resolve_followup_text(text: str, model: str | None = None) -> str:
    b = _butler()
    if not b._looks_like_followup_reference(text):
        return text
    conversation = b._recent_turns_prompt_text()
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
    rewritten = b._normalize_response(
        b._raw_llm(prompt, model=model or b.OLLAMA_FALLBACK or b.OLLAMA_MODEL, max_tokens=80),
        max_words=18,
    ).strip().strip('"')
    if not rewritten or rewritten == "Something went wrong.":
        return text
    return rewritten


def _reply_without_action(
    text: str,
    response: str,
    test_mode: bool = False,
    intent_name: str = "",
    learning_meta: dict | None = None,
) -> None:
    b = _butler()
    b._speak_or_print(response, test_mode=test_mode)
    b._record(text, response, [], intent_name=intent_name or "reply", learning_meta=learning_meta)
    b.state.transition(b.State.WAITING if not test_mode else b.State.IDLE)


def _consume_project_context_block() -> str:
    b = _butler()
    try:
        payload = b.consume_project_context_hint()
    except Exception:
        payload = {}
    project = " ".join(str(payload.get("project", "")).split()).strip()
    detail = " ".join(str(payload.get("detail", "")).split()).strip()
    if not project or not detail:
        return ""
    return f"[PROJECT MEMORY]\n  {project}: {detail[:1000]}"


def _build_voice_prompt(intent, text: str) -> str:
    b = _butler()
    conversation = b._recent_turns_prompt_text()
    if intent.name == "what_next":
        ctx = b._get_cached_context()
        mac_state = b.get_state_for_context()
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

    ctx = b._get_cached_context()
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
    b = _butler()
    parts = []
    formatted = str(ctx.get("formatted", "")).strip()
    conversation = b._recent_turns_prompt_text()
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
            snapshot = b._project_snapshot_for_planning()
            if snapshot:
                parts.insert(0, snapshot)
            if formatted:
                parts[1 if snapshot else 0] = b._strip_context_section(formatted, "[TASK LIST]")

    return "\n\n".join(part for part in parts if part).strip()


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


def _tool_chat_messages(ctx: dict, user_text: str) -> list[dict]:
    b = _butler()
    formatted = str(ctx.get("formatted", "") or "").strip()
    recent = b._recent_turns_prompt_text()
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
    b = _butler()
    lowered = " ".join(str(text or "").lower().split())
    if _looks_like_memory_question(lowered):
        return _call_tool_with_toolkit("recall_memory", {"query": text})

    if any(
        phrase in lowered
        for phrase in (
            "what am i looking at",
            "what's on my screen",
            "describe this screen",
            "describe my screen",
        )
    ):
        return _call_tool_with_toolkit("take_screenshot_and_describe", {"question": text})

    if "github" in lowered and "latest commit" in lowered:
        return _call_tool_with_toolkit("browse_and_act", {"task": text})

    decision = analyze_query(text, conversation=b._conversation_context_text())
    action = str(decision.get("action", "") or "").strip().lower()
    url = str(decision.get("url", "") or "").strip()
    if action == "fetch" and url:
        return _call_tool_with_toolkit("browse_web", {"url": url, "query": text})
    if action in {"search", "news", "fetch"}:
        return _call_tool_with_toolkit("browse_web", {"query": text, "url": url})
    return None


def _fallback_tool_speech(text: str, outcome: dict) -> str:
    b = _butler()
    tool = str(outcome.get("tool", "")).strip()
    payload = outcome.get("payload") if isinstance(outcome.get("payload"), dict) else {}
    results = outcome.get("results") if isinstance(outcome.get("results"), list) else []

    if tool == "recall_memory":
        matches = payload.get("matches") if isinstance(payload.get("matches"), list) else []
        if matches:
            first = matches[0] if isinstance(matches[0], dict) else {}
            candidate = str(first.get("speech", "") or first.get("context", "")).strip()
            if candidate:
                return b._normalize_response(candidate, max_words=45)
        return "I couldn't find a matching decision in memory."

    if tool == "browse_web":
        lead = ""
        if results:
            lead = str(results[0].get("result", "") or "").strip()
        lead = lead or str(payload.get("result", "") or "").strip()
        if lead:
            return b._normalize_response(lead, max_words=45)
        return "I couldn't pull a useful web answer right now."

    if tool == "take_screenshot_and_describe":
        answer = str(payload.get("result", "") or "").strip()
        if answer:
            return b._normalize_response(answer, max_words=45)
        return "I couldn't read the screen clearly right now."

    if results:
        lead = str(results[0].get("result", "") or results[0].get("error", "")).strip()
        if lead:
            return b._normalize_response(lead, max_words=45)

    return b._normalize_response(str(text or "").strip(), max_words=20) or "Done."


def _fallback_tool_response(text: str, ctx: dict) -> dict | None:
    outcome = _fallback_tool_outcome(text, ctx)
    if not outcome:
        return None
    return {
        "speech": _fallback_tool_speech(text, outcome),
        "actions": outcome.get("actions", []),
        "results": outcome.get("results", []),
    }


def _toolkit_result_text(result) -> str:
    if isinstance(result, dict):
        preferred = " ".join(str(result.get("result", "") or result.get("speech", "")).split()).strip()
        if preferred:
            return preferred
        return json.dumps(_clip_tool_payload(result), ensure_ascii=True)
    if isinstance(result, list):
        return json.dumps(_clip_tool_payload(result), ensure_ascii=True)
    return " ".join(str(result or "").split()).strip()


def _call_tool_with_toolkit(tool_name: str, arguments: dict) -> dict:
    b = _butler()
    name = str(tool_name or "").strip()
    args = dict(arguments or {})
    toolkit = toolkit_module.get_toolkit()
    b.note_tool_started(name or "unknown", str(args)[:120])
    try:
        result = toolkit.call(name, **args)
        result_text = _toolkit_result_text(result)
        payload_result = result if isinstance(result, dict) else (result_text or "Done.")
        payload: dict[str, object] = {
            "tool": name,
            "args": {key: _clip_tool_payload(value, limit=220) for key, value in args.items()},
            "status": "ok",
            "result": _clip_tool_payload(payload_result),
        }
        if name == "recall_memory":
            matches = memory_store.semantic_search(str(args.get("query", "")).strip(), n=3)
            b.note_memory_recall(str(args.get("query", "")).strip(), matches)
            payload["matches"] = _clip_tool_payload(matches)
        b.note_tool_finished(name, "ok", result_text[:200] or "Done.")
        return {
            "tool": name,
            "actions": [{"type": name, **args}],
            "results": [{"action": name, "status": "ok", "result": result_text or "Done."}],
            "payload": payload,
            "speech": result_text or "Done.",
        }
    except Exception as exc:
        b.note_tool_finished(name or "unknown", "error", str(exc))
        return {
            "tool": name or "unknown",
            "actions": [],
            "results": [{"action": name or "unknown", "status": "error", "error": str(exc)}],
            "payload": {"tool": name or "unknown", "status": "error", "error": _clip_tool_payload(str(exc), limit=220)},
            "speech": f"I had trouble with {name or 'that'}.",
        }


def _safe_tool_chat_response(
    text: str,
    ctx: dict,
    *,
    model: str | None = None,
    intent_name: str = "",
    intent_confidence: float = 0.0,
    stream_speech: bool = False,
    test_mode: bool = False,
) -> dict:
    b = _butler()
    try:
        return _tool_chat_response(
            text,
            ctx,
            model=model,
            intent_name=intent_name,
            intent_confidence=intent_confidence,
            stream_speech=stream_speech,
        )
    except Exception:
        fallback = "I had trouble with that, try again."
        b._speak_or_print(fallback, test_mode=test_mode)
        return {"speech": fallback, "actions": [], "results": [], "spoken": True}


def _tool_chat_response(
    text: str,
    ctx: dict,
    model: str | None = None,
    *,
    intent_name: str = "",
    intent_confidence: float = 0.0,
    stream_speech: bool = False,
) -> dict:
    b = _butler()
    planning_model = b.pick_butler_model("planning", override=model)
    voice_model = b.pick_butler_model("voice", override=model)
    messages = _tool_chat_messages(ctx, text)
    backbone_speech = ""

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
        backbone_reply = backbone.run_agentscope_turn(
            text,
            ctx,
            system_prompt=TOOL_SYSTEM_PROMPT,
            model_name=voice_model,
            intent_name=intent_name or "default",
            stream_speech=stream_speech,
            on_sentence=b._speak_stream_chunk if stream_speech else None,
        )
        backbone_meta = backbone_reply.get("metadata", {}) if isinstance(backbone_reply.get("metadata"), dict) else {}
        speech = b._normalize_response(str(backbone_reply.get("speech", "")).strip(), max_words=45)
        actions = backbone_reply.get("actions", []) if isinstance(backbone_reply.get("actions"), list) else []
        results = backbone_reply.get("results", []) if isinstance(backbone_reply.get("results"), list) else []
        if backbone_meta.get("interrupted") and not speech:
            speech = "Switching to your new request."
        if speech or actions or results or backbone_meta.get("interrupted"):
            if speech and not actions and not results and not backbone_meta.get("interrupted") and _looks_like_memory_question(text):
                backbone_speech = speech
            else:
                return {
                    "speech": speech,
                    "actions": actions,
                    "results": results,
                    "metadata": backbone_meta,
                    "spoken": bool(backbone_meta.get("spoken")),
                }
    except Exception as exc:
        print(f"[AgentScope] Backbone fallback: {exc}")
        backbone_speech = ""

    try:
        first = ollama_client.chat_with_ollama(
            messages,
            planning_model,
            tools=TOOLS,
            max_tokens=220,
            temperature=0.2,
            timeout_hint="agent",
        )
    except RuntimeError as exc:
        if not _tool_chat_endpoint_missing(exc):
            raise
        outcome = _fallback_tool_outcome(text, ctx)
        if not outcome:
            speech = backbone_speech or _unknown_brain_response(text, model=model)
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
                    b._stream_chat_response_with_tts(
                        messages,
                        voice_model,
                        max_tokens=140,
                        temperature=0.3,
                    )
                )
            except Exception:
                streamed = ""
            streamed = b._normalize_response(streamed, max_words=45)
            if streamed:
                b.notify("Burry", streamed[:180], subtitle="Response")
                return {"speech": streamed, "actions": [], "results": [], "spoken": True}
        speech = b._normalize_response(assistant_content or backbone_speech, max_words=45)
        return {"speech": speech, "actions": [], "results": []}

    messages.append(
        {
            "role": "assistant",
            "content": assistant_content,
            "tool_calls": tool_calls,
        }
    )

    for tool_call in tool_calls[:3]:
        interrupt = b.check_interrupt()
        if interrupt:
            try:
                b._COMMAND_QUEUE.put_nowait(interrupt)
            except queue.Full:
                return {"speech": "Still busy, please wait.", "actions": [], "results": []}
            b._record(text, "Interrupted by user", [], intent_name="interrupted")
            return {
                "speech": "Switching to your new request.",
                "actions": [],
                "results": [{"status": "interrupted", "result": interrupt}],
            }
        function = tool_call.get("function", {}) if isinstance(tool_call, dict) else {}
        tool_name = str(function.get("name", "")).strip()
        arguments = _parse_tool_arguments(function.get("arguments", {}))
        outcome = _call_tool_with_toolkit(tool_name, arguments)
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
                b._stream_chat_response_with_tts(
                    messages,
                    voice_model,
                    max_tokens=140,
                    temperature=0.3,
                )
            )
        except Exception:
            streamed = ""
        final_speech = b._normalize_response(streamed, max_words=45)
        already_spoken = bool(final_speech)
        if final_speech:
            b.notify("Burry", final_speech[:180], subtitle="Response")
    if not final_speech:
        final = ollama_client.chat_with_ollama(
            messages,
            voice_model,
            max_tokens=140,
            temperature=0.3,
            timeout_hint="voice",
        )
        final_message = final.get("message", {}) if isinstance(final, dict) else {}
        final_speech = b._normalize_response(str(final_message.get("content", "")).strip(), max_words=45)
    if not final_speech and last_outcome is not None:
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
    b = _butler()
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

    raw = b._raw_llm(prompt, model=model or b.OLLAMA_MODEL, max_tokens=60, temperature=0.4)
    return b._normalize_response(raw, max_words=20, single_sentence=True)


def _rewrite_speech_with_agent_results(
    speech: str,
    execution_results: list,
    model: str | None = None,
) -> str:
    b = _butler()
    agent_results = _successful_agent_results(execution_results)
    if not agent_results:
        return ""

    prompt = f"""Butler just got these results from specialist agents:
{chr(10).join(agent_results[:2])}

Original speech: {speech}

Rewrite the speech to include the key info from those results.
Keep it under 45 words.
Output ONLY the new speech text."""

    raw = b._raw_llm(prompt, model=model or b.OLLAMA_MODEL, max_tokens=120, temperature=0.4)
    rewritten = b._normalize_response(raw, max_words=45)
    if not rewritten or rewritten == "Something went wrong.":
        return b._normalize_response(agent_results[0], max_words=45)
    return rewritten


def _successful_agent_results(execution_results: list) -> list[str]:
    return [
        str(result.get("result", "")).strip()
        for result in execution_results
        if result.get("action") == "run_agent"
        and result.get("status") == "ok"
        and str(result.get("result", "")).strip()
    ]
