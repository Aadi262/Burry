#!/usr/bin/env python3
"""ReMe-style long-term memory — three-tier memory management.
Working (current session) → Recent (7 days) → Archive (LLM-summarized).
Burry remembers specific facts and compresses old conversations automatically.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional

MEMORY_PATH = Path(__file__).parent / "long_term_memory.json"
SESSION_FILE = Path(__file__).parent / "burry_session.json"


def _load() -> dict:
    try:
        return json.loads(MEMORY_PATH.read_text())
    except Exception:
        return {"working": [], "recent": [], "archive": [], "facts": {}, "updated_at": ""}


def _save(data: dict) -> None:
    data["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    MEMORY_PATH.write_text(json.dumps(data, indent=2))


def remember_fact(key: str, value: str) -> None:
    """Store a specific fact Burry should always remember.
    Example: remember_fact('standup_time', '10:30am daily')
    """
    data = _load()
    data["facts"][key] = {"value": value, "stored_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    _save(data)


def recall_fact(key: str) -> Optional[str]:
    """Recall a specific stored fact."""
    data = _load()
    fact = data["facts"].get(key)
    return fact["value"] if fact else None


def add_to_working_memory(heard: str, spoken: str) -> None:
    """Add a conversation turn to working memory. Auto-compress when full."""
    data = _load()
    data["working"].append({
        "heard": heard[:200],
        "spoken": spoken[:200],
        "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    })

    # Keep working memory at 6 turns max
    if len(data["working"]) > 6:
        overflow = data["working"][:-6]
        data["recent"].extend(overflow)
        data["working"] = data["working"][-6:]

        # Compress recent to archive if too large
        if len(data["recent"]) > 50:
            _compress_recent_to_archive(data)

    _save(data)


def _compress_recent_to_archive(data: dict) -> None:
    """Compress recent memory into archive summaries using LLM."""
    try:
        from brain.ollama_client import _call

        recent_text = "\n".join(
            f"Q: {t['heard']} A: {t['spoken']}"
            for t in data["recent"][-20:]
        )

        summary = _call(
            f"Summarize these past conversations into 3 bullet points:\n{recent_text}",
            "gemma4:e4b",
            max_tokens=100,
            temperature=0.1,
        )

        if summary:
            data["archive"].append({
                "summary": summary,
                "compressed_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "turns_count": len(data["recent"]),
            })
            data["recent"] = data["recent"][-10:]
    except Exception:
        # Silent fail — compress by truncation
        data["recent"] = data["recent"][-10:]


def get_full_context() -> str:
    """Get complete memory context for LLM injection."""
    data = _load()
    parts = []

    if data["facts"]:
        facts_text = "\n".join(f"- {k}: {v['value']}" for k, v in data["facts"].items())
        parts.append(f"REMEMBERED FACTS:\n{facts_text}")

    if data["archive"]:
        archive_text = "\n".join(f"- {a['summary']}" for a in data["archive"][-3:])
        parts.append(f"PAST CONTEXT:\n{archive_text}")

    if data["recent"]:
        recent_text = "\n".join(f"Q: {t['heard']}\nA: {t['spoken']}" for t in data["recent"][-5:])
        parts.append(f"RECENT SESSIONS:\n{recent_text}")

    if data["working"]:
        working_text = "\n".join(f"Q: {t['heard']}\nA: {t['spoken']}" for t in data["working"])
        parts.append(f"CURRENT SESSION:\n{working_text}")

    return "\n\n".join(parts)


def save_session_state(agent) -> None:
    """Persist AgentScope agent memory to disk for the next session."""
    try:
        messages = []
        memory = getattr(agent, "memory", None)
        memory_state = None
        if memory is not None and hasattr(memory, "state_dict"):
            try:
                memory_state = memory.state_dict()
            except Exception:
                memory_state = None
        if memory is not None and hasattr(memory, "get_memory"):
            raw = memory.get_memory()
            for item in raw if isinstance(raw, list) else []:
                try:
                    messages.append(
                        {
                            "role": getattr(item, "role", "assistant"),
                            "content": (
                                item.get_text_content()
                                if hasattr(item, "get_text_content")
                                else str(item)
                            ),
                        }
                    )
                except Exception:
                    continue
        state = {
            "memory": messages[-20:],
            "saved_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        if isinstance(memory_state, dict):
            state["memory_state"] = memory_state
        SESSION_FILE.write_text(json.dumps(state, indent=2))
        print(f"[Memory] Saved {len(messages)} turns to session file.")
    except Exception as exc:
        print(f"[Memory] save_session_state failed: {exc}")


def restore_session_state(agent) -> None:
    """Restore previous session memory into an AgentScope agent."""
    try:
        if not SESSION_FILE.exists():
            return
        state = json.loads(SESSION_FILE.read_text())
        memory = getattr(agent, "memory", None)
        if memory is None:
            return

        memory_state = state.get("memory_state")
        if isinstance(memory_state, dict) and hasattr(memory, "load_state_dict"):
            try:
                memory.load_state_dict(memory_state)
                print("[Memory] Restored session state from disk.")
                return
            except Exception:
                pass

        messages = state.get("memory", [])
        if not messages:
            return

        from agentscope.message import Msg
        import asyncio

        restored = 0
        add_message = getattr(memory, "add", None)
        if add_message is None:
            return

        for item in messages[-10:]:
            try:
                msg = Msg(
                    name=item.get("role", "assistant"),
                    content=item.get("content", ""),
                    role=item.get("role", "assistant"),
                )
                if asyncio.iscoroutinefunction(add_message):
                    loop = asyncio.new_event_loop()
                    try:
                        loop.run_until_complete(add_message(msg))
                    finally:
                        loop.close()
                else:
                    add_message(msg)
                restored += 1
            except Exception:
                continue
        print(f"[Memory] Restored {restored} turns from previous session.")
    except Exception as exc:
        print(f"[Memory] restore_session_state failed: {exc}")
