#!/usr/bin/env python3
"""
state.py
Thread-safe Butler runtime state.
"""

import threading
import time
from enum import Enum

from butler_config import VERBOSE_LOGS

try:
    from runtime import note_state_transition
except Exception:
    def note_state_transition(*_args, **_kwargs) -> None:
        return None


class State(Enum):
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"
    WAITING = "waiting"


ButlerState = State

STATE_ICONS = {
    State.IDLE: "💤",
    State.LISTENING: "👂",
    State.THINKING: "🧠",
    State.SPEAKING: "🔊",
    State.WAITING: "⏳",
}

BUSY_STATES = {State.LISTENING, State.THINKING, State.SPEAKING}


class StateMachine:
    """Thread-safe state machine with a WAITING state that can still accept commands."""

    def __init__(self):
        self._state = State.IDLE
        self._lock = threading.Lock()
        self._listeners = []

    @property
    def state(self) -> State:
        with self._lock:
            return self._state

    @property
    def current(self) -> State:
        return self.state

    @property
    def is_busy(self) -> bool:
        return self.state in BUSY_STATES

    def transition(self, new_state: State) -> bool:
        with self._lock:
            old_state = self._state
            if new_state == State.LISTENING and old_state in BUSY_STATES:
                if VERBOSE_LOGS:
                    print(f"[State] ⚠️ Already busy ({old_state.value}), ignoring trigger")
                return False

            self._state = new_state
            if VERBOSE_LOGS:
                icon = STATE_ICONS.get(new_state, "")
                print(f"[State] {icon} {old_state.value} -> {new_state.value}")

            note_state_transition(old_state, new_state)
            for callback in list(self._listeners):
                try:
                    callback(old_state, new_state)
                except Exception:
                    pass
            return True

    def on_change(self, callback) -> None:
        self._listeners.append(callback)

    def reset(self) -> None:
        with self._lock:
            self._state = State.IDLE
        if VERBOSE_LOGS:
            print("[State] Reset to IDLE")


state = StateMachine()
butler_state = state


if __name__ == "__main__":
    print("=== State Machine Test ===\n")
    sm = StateMachine()
    print(f"Initial state: {sm.current.value}")
    print(f"Is busy: {sm.is_busy}\n")

    for next_state in [
        State.LISTENING,
        State.THINKING,
        State.SPEAKING,
        State.WAITING,
        State.IDLE,
    ]:
        sm.transition(next_state)
        time.sleep(0.2)

    print(f"\nFinal state: {sm.current.value}")
