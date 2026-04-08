"""pipeline/recorder.py — conversation and memory recording helpers."""

from __future__ import annotations

import os
import time
from datetime import datetime
from pathlib import Path


def _butler():
    import butler  # noqa: PLC0415

    return butler


class ConversationContext:
    def __init__(self) -> None:
        self.turns: list[dict] = []
        self.last_spoken = ""
        self.last_intent = ""
        self.last_heard = ""
        self._restore_from_runtime()

    def _restore_from_runtime(self) -> None:
        b = _butler()
        try:
            turns = list(b.load_runtime_state().get("turns") or [])
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


def reset_conversation_context() -> None:
    b = _butler()
    with b._CONVERSATION_LOCK:
        b._SESSION_CONVERSATION.clear()
        b.note_conversation_turns([])
    b._briefing_done = False


def _remember_conversation_turn(heard: str, intent_name: str, spoken: str) -> None:
    if not spoken:
        return
    b = _butler()
    with b._CONVERSATION_LOCK:
        b._SESSION_CONVERSATION.add_turn(heard, intent_name, spoken)
        b.note_conversation_turns(b._SESSION_CONVERSATION.turns)


def _conversation_context_text() -> str:
    b = _butler()
    with b._CONVERSATION_LOCK:
        return b._SESSION_CONVERSATION.get_context_for_llm()


def _recent_turns_prompt_text(limit: int = 5) -> str:
    b = _butler()
    with b._CONVERSATION_LOCK:
        prompt = b._SESSION_CONVERSATION.get_recent_turns_prompt(limit=limit)
    if prompt:
        return prompt

    try:
        runtime_state = b.load_runtime_state()
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


def _record(
    text: str,
    speech: str,
    actions: list,
    results: list | None = None,
    intent_name: str = "",
    learning_meta: dict | None = None,
) -> None:
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return

    b = _butler()
    try:
        learning_payload = dict(learning_meta or {})
        normalized_text = " ".join(str(text or "").split()).strip()
        normalized_intent = " ".join(str(intent_name or "").split()).strip()
        now_mono = time.monotonic()
        with b._LEARNING_TRACE_LOCK:
            previous = dict(b._LAST_RESOLVED_COMMAND)
            b._LAST_RESOLVED_COMMAND.update(
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

        try:
            outcome = "success" if speech and not any(
                str(item.get("status", "")).lower() == "error"
                for item in (results or [])
                if isinstance(item, dict)
            ) else "failure"
            b._bus_record(
                {
                    "text": text,
                    "intent": intent_name or "unknown",
                    "speech": speech,
                    "model": (learning_meta or {}).get("model", ""),
                    "outcome": outcome,
                }
            )
        except Exception as exc:
            print(f"[Butler] silent error: {exc}")

        _remember_conversation_turn(text, intent_name or "reply", speech)
        try:
            b.add_to_working_memory(text[:200], speech[:200])
        except Exception as exc:
            print(f"[Butler] silent error: {exc}")
        try:
            model_name = learning_meta.get("model", "") if learning_meta else ""
            outcome = "success" if speech and not any(
                str(item.get("status", "")).lower() == "error"
                for item in (results or [])
                if isinstance(item, dict)
            ) else "failure"
            b.record_episode_with_agentscope_feedback(
                text=text,
                intent=intent_name or "unknown",
                model=model_name,
                response=speech,
                outcome=outcome,
            )
        except Exception as exc:
            print(f"[Butler] silent error: {exc}")
        b.record_session(text[:100], speech[:200], actions, results=results or [])
        b.save_session(
            {
                "timestamp": datetime.now().isoformat(),
                "speech": speech[:200],
                "actions": actions,
                "context_preview": text[:120],
            }
        )
        b.append_to_index(
            f"{datetime.now().strftime('%m/%d')} command: {text[:80]} -> {speech[:80]}"
        )
        touched = b.record_project_execution(text, speech, actions, results=results or [])
        with b._LEARNING_TRACE_LOCK:
            b.analyze_and_learn(
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
            b.observe_project_relationships(
                text=text,
                speech=speech,
                actions=actions,
                touched_projects=list(touched.keys()),
            )
        except Exception as exc:
            print(f"[Butler] silent error: {exc}")
    except Exception as exc:
        print(f"[Butler] silent error: {exc}")


def _remember_project_state(action: dict) -> None:
    b = _butler()
    action_type = action.get("type")
    if action_type == "open_project":
        try:
            from projects import get_project

            project = get_project(action.get("name", ""))
            if not project:
                return
            b.update_project_state(
                project["name"],
                {
                    "last_workspace_path": project.get("path", ""),
                    "last_opened": datetime.now().isoformat(),
                },
            )
        except Exception as exc:
            print(f"[Butler] silent error: {exc}")
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
        b.update_project_state(project_name, payload)
        return

    path = action.get("path", "")
    if not path:
        return
    expanded = os.path.expanduser(path)
    project_root = expanded
    if action_type == "open_editor" and Path(expanded).suffix:
        project_root = str(Path(expanded).parent)
    project_name = Path(project_root).name or "project"
    b.update_project_state(
        project_name,
        {
            "last_workspace_path": project_root,
            "last_editor": action.get("editor", ""),
            "last_opened": project_root,
        },
    )


def record(*args, **kwargs):  # type: ignore[override]
    return _record(*args, **kwargs)
