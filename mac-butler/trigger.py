#!/usr/bin/env python3
"""
trigger.py
Unified trigger entrypoint for Mac Butler.
"""

from __future__ import annotations

import argparse
import atexit
import threading
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


def _run_continuous_session() -> None:
    """Listen for commands in a loop — no clap needed between commands.
    Exits when the user says 'sleep' / 'go quiet' (state → IDLE).
    """
    global _session_active
    import time
    from butler import handle_command, reset_conversation_context
    from voice.stt import listen_for_command

    print("[Trigger] Continuous session started — just speak, no clap needed between commands")
    try:
        while not _shutdown_event.is_set():
            # Sleep / go-quiet command transitions state to IDLE — that ends the session
            if state.current == State.IDLE:
                print("[Trigger] Session ended (sleep command). Clap to start a new session.")
                break

            # Wait if Butler is still thinking / speaking
            if state.is_busy:
                time.sleep(0.05)
                continue

            try:
                if state.current != State.LISTENING:
                    state.transition(State.LISTENING)
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
                handle_command(text)  # blocking — returns only after TTS is done
    finally:
        reset_conversation_context()
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
