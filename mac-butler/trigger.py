#!/usr/bin/env python3
"""
trigger.py
Unified trigger entrypoint for Mac Butler.
"""

from __future__ import annotations

import argparse
import atexit
import os
import re
import threading
from datetime import datetime
from pathlib import Path

import requests

from daemon.clap_detector import ClapDetector
from butler_config import BUTLER_MODEL_CHAINS, OLLAMA_LOCAL_URL, OLLAMA_MODEL
from runtime import note_session_active
from state import State, state

SESSION_FLAG = Path("/tmp/butler_session.flag")
_session_active = False
_session_lock = threading.Lock()
_shutdown_event = threading.Event()
_session_thread: threading.Thread | None = None
_clap_thread: threading.Thread | None = None
_clap_detector: ClapDetector | None = None


def _planning_keepalive_model() -> str:
    chain = list(BUTLER_MODEL_CHAINS.get("planning") or [])
    return str(chain[0] if chain else OLLAMA_MODEL)


def _start_dashboard_server() -> None:
    try:
        from projects import serve_dashboard, show_dashboard_window
        try:
            from projects.dashboard import dashboard_url
        except Exception:
            dashboard_url = lambda: "http://127.0.0.1:3333"
    except Exception as exc:
        print(f"[Dashboard] HUD startup skipped: {exc}")
        return

    try:
        server = serve_dashboard()
    except Exception as exc:
        print(f"[Dashboard] HUD startup failed: {exc}")
        return

    if server is not None:
        print(f"[Dashboard] Live HUD: {dashboard_url()}")
        try:
            show_dashboard_window()
        except Exception as exc:
            print(f"[Dashboard] HUD window skipped: {exc}")


def _warm_voice_runtime() -> None:
    try:
        from voice.stt import warm_stt

        warm_stt()
    except Exception as exc:
        print(f"[Trigger] STT warmup skipped: {exc}")

    try:
        from voice.tts import warm_tts

        warm_tts()
    except Exception as exc:
        print(f"[Trigger] TTS warmup skipped: {exc}")


def _warm_planning_model() -> None:
    model = _planning_keepalive_model()
    try:
        requests.post(
            f"{OLLAMA_LOCAL_URL.rstrip('/')}/api/generate",
            json={
                "model": model,
                "prompt": " ",
                "stream": False,
                "keep_alive": "10m",
                "options": {
                    "num_predict": 1,
                },
            },
            timeout=2.5,
        )
    except Exception:
        return


def _clear_session_flag() -> None:
    SESSION_FLAG.unlink(missing_ok=True)


def _mark_session_started() -> None:
    SESSION_FLAG.write_text("awake", encoding="utf-8")


def _parse_summary_bullets(raw: str) -> str:
    bullets = []
    for line in str(raw or "").splitlines():
        cleaned = line.strip()
        if not cleaned:
            continue
        if cleaned[0] in "-*•":
            cleaned = cleaned[1:].strip()
        if not cleaned:
            continue
        bullets.append(f"- {cleaned}")
        if len(bullets) >= 3:
            break
    return "\n".join(bullets)


def _fallback_session_summary(sessions: list[dict]) -> str:
    bullets = []
    for session in sessions[:3]:
        context = " ".join(str(session.get("context", "") or session.get("context_preview", "")).split()).strip()
        speech = " ".join(str(session.get("speech", "")).split()).strip()
        if context and speech:
            bullets.append(f"- {context[:60]} -> {speech[:80]}")
        elif context:
            bullets.append(f"- {context[:80]}")
        elif speech:
            bullets.append(f"- {speech[:80]}")
    return "\n".join(bullets[:3])


def _write_session_end_summary() -> None:
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return
    try:
        from brain.ollama_client import _call
        from executor.engine import Executor
        from memory.store import load_recent_sessions
    except Exception:
        return

    today = datetime.now().strftime("%Y-%m-%d")
    sessions = [
        session
        for session in load_recent_sessions(12)
        if str(session.get("timestamp", "")).startswith(today)
    ]
    if not sessions:
        return

    material = "\n".join(
        f"- {str(session.get('timestamp', ''))[:16]} | "
        f"{str(session.get('context', '') or session.get('context_preview', '')).strip()} | "
        f"{str(session.get('speech', '')).strip()}"
        for session in reversed(sessions[:8])
    )
    prompt = f"""Summarize today's Burry session activity into exactly 3 bullet lines.
Each line must start with "- " and stay under 16 words.

Session log:
{material}
"""
    try:
        summary = _parse_summary_bullets(_call(prompt, "gemma4:e4b", temperature=0.2, max_tokens=120))
    except Exception:
        summary = ""
    if not summary:
        summary = _fallback_session_summary(sessions)
    if not summary:
        return
    try:
        Executor().obsidian_note(today, summary, folder="Daily")
    except Exception:
        return


def _latest_recorded_session() -> dict | None:
    try:
        from memory.store import load_recent_sessions
    except Exception:
        return None

    sessions = load_recent_sessions(1)
    if not sessions:
        return None
    latest = sessions[0]
    return dict(latest) if isinstance(latest, dict) else None


def _accumulate_session_outcome(
    *,
    last_timestamp: str,
    session_speeches: list[str],
    session_actions: list[dict],
) -> str:
    latest = _latest_recorded_session()
    if not latest:
        return last_timestamp

    timestamp = str(latest.get("timestamp", "")).strip()
    if not timestamp or timestamp == last_timestamp:
        return last_timestamp

    speech = " ".join(str(latest.get("speech", "")).split()).strip()
    if speech:
        session_speeches.append(speech)
    for action in list(latest.get("actions") or []):
        if isinstance(action, dict):
            session_actions.append(dict(action))
    return timestamp


def _session_touched_projects(texts: list[str], actions: list[dict]) -> list[str]:
    try:
        from projects import load_projects
    except Exception:
        return []

    combined_parts = list(texts)
    for action in actions:
        combined_parts.extend(
            [
                str(action.get("name", "")),
                str(action.get("project", "")),
                str(action.get("path", "")),
                str(action.get("cwd", "")),
            ]
        )
    combined = " ".join(part for part in combined_parts if part)
    normalized = re.sub(r"[^a-z0-9]+", "", combined.lower())
    touched: list[str] = []

    for project in load_projects():
        name = str(project.get("name", "")).strip()
        if not name:
            continue
        aliases = [name] + [str(alias).strip() for alias in list(project.get("aliases") or []) if str(alias).strip()]
        path = os.path.expanduser(str(project.get("path", "") or "")).strip()
        path_key = path.lower().rstrip("/")
        matched = any(re.sub(r"[^a-z0-9]+", "", alias.lower()) in normalized for alias in aliases if alias)
        if not matched and path_key:
            for action in actions:
                for key in ("path", "cwd"):
                    candidate = os.path.expanduser(str(action.get(key, "") or "")).strip().lower().rstrip("/")
                    if candidate and (candidate == path_key or candidate.startswith(path_key + os.sep.lower())):
                        matched = True
                        break
                if matched:
                    break
        if matched and name not in touched:
            touched.append(name)
    return touched


def _observe_session_project_relationships(
    session_texts: list[str],
    session_speeches: list[str],
    session_actions: list[dict],
) -> None:
    text = " ".join(" ".join(str(item or "").split()).strip() for item in session_texts if str(item or "").strip()).strip()
    speech = " ".join(" ".join(str(item or "").split()).strip() for item in session_speeches if str(item or "").strip()).strip()
    if not text and not speech and not session_actions:
        return
    try:
        from memory.graph import observe_project_relationships
    except Exception:
        return

    observe_project_relationships(
        text=text,
        speech=speech,
        actions=session_actions,
        touched_projects=_session_touched_projects(session_texts, session_actions),
    )


def _run_continuous_session() -> None:
    """Listen for commands in a loop — no clap needed between commands.
    Exits when the user says 'sleep' / 'go quiet' (state → IDLE).
    """
    global _session_active
    import time
    from butler import handle_input, reset_conversation_context
    from voice.stt import listen_for_command

    print("[Trigger] Continuous session started — just speak, no clap needed between commands")
    session_texts: list[str] = []
    session_speeches: list[str] = []
    session_actions: list[dict] = []
    last_session_timestamp = ""
    _handle_thread: threading.Thread | None = None

    def _run_handle(cmd: str) -> None:
        handle_input(cmd)

    try:
        while not _shutdown_event.is_set():
            # Sleep / go-quiet command transitions state to IDLE — that ends the session
            if state.current == State.IDLE:
                print("[Trigger] Session ended (sleep command). Clap to start a new session.")
                break

            # Always keep listening — even while thinking.
            # Speaking: skip (don't talk over Burry's response)
            from state import State as _State
            if state.current == _State.SPEAKING:
                time.sleep(0.05)
                continue

            try:
                if state.current not in (_State.LISTENING,):
                    state.transition(_State.LISTENING)
                text = listen_for_command(timeout=10.0, stop_event=_shutdown_event)
            except Exception as exc:
                if _shutdown_event.is_set():
                    break
                print(f"[Trigger] STT stopped: {exc}")
                time.sleep(0.1)
                continue

            if _shutdown_event.is_set():
                break
            if text and len(text) > 2:
                session_texts.append(text)
                # If a handle thread is already running, treat new input as interrupt
                if _handle_thread is not None and _handle_thread.is_alive():
                    try:
                        from butler import interrupt_burry
                        interrupt_burry(text)
                        print(f"[Trigger] Interrupt sent: {text[:50]}")
                    except Exception:
                        pass
                    last_session_timestamp = _accumulate_session_outcome(
                        last_timestamp=last_session_timestamp,
                        session_speeches=session_speeches,
                        session_actions=session_actions,
                    )
                    continue
                # Non-blocking: run handle_input in background thread so mic stays open
                _handle_thread = threading.Thread(target=_run_handle, args=(text,), daemon=True)
                _handle_thread.start()
                _handle_thread.join()  # still wait, but thread is interruptible
                _handle_thread = None
                last_session_timestamp = _accumulate_session_outcome(
                    last_timestamp=last_session_timestamp,
                    session_speeches=session_speeches,
                    session_actions=session_actions,
                )
    finally:
        _observe_session_project_relationships(session_texts, session_speeches, session_actions)
        reset_conversation_context()
        _write_session_end_summary()
        _clear_session_flag()
        with _session_lock:
            _session_active = False
        note_session_active(False, source="trigger")


def on_trigger():
    global _session_active, _session_thread
    from butler import reset_conversation_context, run_startup_briefing
    try:
        from projects import show_dashboard_window
    except Exception:
        show_dashboard_window = None

    if _shutdown_event.is_set():
        return

    if state.is_busy:
        print(f"[Trigger] Ignoring trigger while {state.current.value}")
        return

    with _session_lock:
        if _session_active:
            print("[Trigger] Session already running — speak a command")
            return
        _session_active = True

    threading.Thread(target=_warm_planning_model, daemon=True).start()

    note_session_active(True, source="trigger")
    reset_conversation_context()
    if show_dashboard_window is not None:
        try:
            show_dashboard_window(force=True)
        except Exception:
            pass

    if not SESSION_FLAG.exists():
        _mark_session_started()

        def _start_session():
            run_startup_briefing()
            _run_continuous_session()

        _session_thread = threading.Thread(target=_start_session, daemon=True)
        _session_thread.start()
    else:
        # Re-activating after a sleep command
        _session_thread = threading.Thread(target=_run_continuous_session, daemon=True)
        _session_thread.start()


def start_keyboard_trigger():
    from pynput import keyboard

    trigger_combo = {
        keyboard.Key.cmd,
        keyboard.Key.shift,
        keyboard.KeyCode.from_char("b"),
    }
    current_keys = set()

    def on_press(key):
        current_keys.add(key)
        if trigger_combo.issubset(current_keys):
            print("\n[Trigger] Cmd+Shift+B pressed")
            threading.Thread(target=on_trigger, daemon=True).start()

    def on_release(key):
        current_keys.discard(key)

    print("[Trigger] Keyboard mode: press Cmd+Shift+B")
    with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
        listener.join()


def start_clap_trigger():
    global _clap_detector
    detector = ClapDetector(on_clap_detected=on_trigger)
    _clap_detector = detector
    try:
        detector.start()
    except Exception as exc:
        print(f"[Trigger] Clap mode unavailable: {exc}")


def shutdown() -> None:
    _shutdown_event.set()
    _clear_session_flag()
    note_session_active(False, source="shutdown")
    try:
        if _clap_detector is not None:
            _clap_detector.stop()
    except Exception:
        pass
    try:
        if _session_thread is not None and _session_thread.is_alive():
            _session_thread.join(timeout=1.5)
    except Exception:
        pass
    try:
        if _clap_thread is not None and _clap_thread.is_alive():
            _clap_thread.join(timeout=1.5)
    except Exception:
        pass


def main():
    _clear_session_flag()
    atexit.register(_clear_session_flag)
    _shutdown_event.clear()

    parser = argparse.ArgumentParser(description="Mac Butler trigger system")
    parser.add_argument("--clap", action="store_true", help="Use clap detection")
    parser.add_argument("--both", action="store_true", help="Use keyboard and clap triggers")
    args = parser.parse_args()

    print("=" * 50)
    print("  🎩 Burry — Trigger Active")
    print("=" * 50)
    print("\nPress Ctrl+C to quit.\n")

    _start_dashboard_server()
    threading.Thread(target=_warm_voice_runtime, daemon=True).start()

    if args.both:
        global _clap_thread
        _clap_thread = threading.Thread(target=start_clap_trigger, daemon=True)
        _clap_thread.start()
        start_keyboard_trigger()
        return

    if args.clap:
        start_clap_trigger()
        return

    start_keyboard_trigger()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        shutdown()
        print("\n[Trigger] Shutting down.")
