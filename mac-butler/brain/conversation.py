"""Conversation-mode replies for Burry's direct chat path."""

from __future__ import annotations

from brain.ollama_client import chat_with_ollama
from brain.session_context import ctx

CONVERSATION_MODEL = "gemma4:e4b"
CONVERSATION_SYSTEM = """You are Burry — Aditya's personal Mac AI.
You know everything about him:
- Works at IEX as a backend engineer (C#, SQL, Redis, Service Fabric)
- Side projects: Adpilot (AI ads), mac-butler (this), ai-sdr-agent,
  Highway, MaxLeads, email-infra
- Based in Mumbai. Works late nights.
- Target: 60-70 LPA by 29 through IEX + side project revenue

Your personality:
- Sharp and direct. No fluff.
- Sarcastic when he's slacking
- Energetic when he's shipping
- Argues back when he's wrong
- Has real opinions about his projects
- Calls out patterns you notice
- Under 40 words unless brainstorming
- Never says "I am an AI" or "As an AI"
- Never says "Sir"
- Knows his project names, uses them directly

Examples of how you talk:
Late night, no commits: "Bro it's 2am and nothing shipped today. What's actually blocking you?"
After good session: "Four commits. Adpilot is moving. What's next?"
Asked to brainstorm: actually brainstorm properly, be specific
Asked opinion: give your actual opinion, argue if needed"""


def _normalize(text: str) -> str:
    return " ".join(str(text or "").split()).strip()


def conversation_messages(text: str, turn_limit: int = 8) -> list[dict[str, str]]:
    normalized_text = _normalize(text)
    history = list(getattr(ctx, "turns", []) or [])

    messages: list[dict[str, str]] = [{"role": "system", "content": CONVERSATION_SYSTEM}]
    for turn in history[-turn_limit:]:
        if not isinstance(turn, dict):
            continue
        content = _normalize(turn.get("text", ""))
        if not content:
            continue
        role = "assistant" if str(turn.get("role", "")).strip().lower() == "butler" else "user"
        messages.append({"role": role, "content": content})

    if not history or _normalize(history[-1].get("text", "")) != normalized_text:
        messages.append({"role": "user", "content": normalized_text})
    return messages


def generate_conversation_reply(text: str) -> str:
    messages = conversation_messages(text)
    try:
        payload = chat_with_ollama(
            messages,
            CONVERSATION_MODEL,
            max_tokens=140,
            temperature=0.7,
            timeout_hint="voice",
        )
    except Exception:
        return ""

    message = payload.get("message") if isinstance(payload, dict) else {}
    return _normalize(message.get("content", "") if isinstance(message, dict) else "")
