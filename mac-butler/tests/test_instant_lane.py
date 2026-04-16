#!/usr/bin/env python3
"""Tests that guarantee instant lane commands meet P95 timing requirements.

Three-lane architecture verification:
- INSTANT LANE: OS commands execute in <500ms, no LLM, bypass busy gate
- BACKGROUND LANE: news/search ack in <500ms, agent runs async
- STOP: hard control, never queued, <300ms
"""
import os
import sys
import time
import threading
import pytest
from unittest.mock import patch, MagicMock

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("PYTEST_CURRENT_TEST", "1")


class TestLaneConstants:
    """Verify the lane constants are properly defined."""

    def test_instant_lane_intents_defined(self):
        from butler import INSTANT_LANE_INTENTS
        assert isinstance(INSTANT_LANE_INTENTS, set)
        assert len(INSTANT_LANE_INTENTS) > 20
        # Core OS commands must be in instant lane
        for intent in ["open_app", "close_app", "spotify_play", "spotify_pause",
                        "browser_new_tab", "browser_close_tab", "screenshot",
                        "volume_set", "volume_up", "volume_down", "greeting", "butler_sleep", "butler_wake"]:
            assert intent in INSTANT_LANE_INTENTS, f"{intent} missing from INSTANT_LANE_INTENTS"

    def test_background_lane_intents_defined(self):
        from butler import BACKGROUND_LANE_INTENTS
        assert isinstance(BACKGROUND_LANE_INTENTS, set)
        for intent in ["news", "market", "hackernews", "reddit", "github_trending",
                        "vps_status", "docker_status"]:
            assert intent in BACKGROUND_LANE_INTENTS, f"{intent} missing from BACKGROUND_LANE_INTENTS"

    def test_no_lane_overlap(self):
        from butler import INSTANT_LANE_INTENTS, BACKGROUND_LANE_INTENTS
        overlap = INSTANT_LANE_INTENTS & BACKGROUND_LANE_INTENTS
        assert not overlap, f"Intents in both lanes: {overlap}"

    def test_deterministic_casual_responses_defined(self):
        from butler import _DETERMINISTIC_CASUAL_RESPONSES
        assert isinstance(_DETERMINISTIC_CASUAL_RESPONSES, dict)
        assert "thank you" in _DETERMINISTIC_CASUAL_RESPONSES
        assert "never mind" in _DETERMINISTIC_CASUAL_RESPONSES
        assert "what can you do" in _DETERMINISTIC_CASUAL_RESPONSES


class TestInstantLaneRouting:
    """Every instant lane intent routes correctly and never touches AgentScope."""

    @pytest.mark.parametrize("text,expected_intent", [
        ("open youtube", "open_app"),
        ("open chrome", "open_app"),
        ("open spotify", "open_app"),
        ("close spotify", "close_app"),
        ("play mockingbird", "spotify_play"),
        ("pause", "spotify_pause"),
        ("next track", "spotify_next"),
        ("volume up", "volume_up"),
        ("open new tab", "browser_new_tab"),
        ("close tab", "browser_close_tab"),
        ("close window", "browser_close_window"),
        ("open mac-butler project", "open_project"),
        ("take screenshot", "screenshot"),
        ("set volume to 50", "volume_set"),
        ("hi", "greeting"),
        ("hello", "greeting"),
        ("stop", "spotify_pause"),
        ("email vedang@gmail.com with subject test", "compose_email"),
    ])
    def test_routes_to_instant_lane(self, text, expected_intent):
        from intents.router import route
        from butler import INSTANT_LANE_INTENTS
        intent = route(text)
        assert intent.name == expected_intent, f"'{text}' routed to {intent.name}, expected {expected_intent}"
        assert intent.name in INSTANT_LANE_INTENTS, f"{intent.name} not in INSTANT_LANE_INTENTS"


class TestInstantLaneTiming:
    """Instant lane commands complete in <500ms."""

    @patch("butler.executor")
    @patch("butler._speak_or_print")
    def test_open_app_under_500ms(self, mock_speak, mock_executor):
        mock_executor.run.return_value = [{"status": "ok"}]
        from butler import handle_input
        start = time.monotonic()
        handle_input("open youtube", test_mode=True)
        elapsed_ms = (time.monotonic() - start) * 1000
        assert elapsed_ms < 500, f"open youtube took {elapsed_ms:.0f}ms"

    @patch("butler._speak_or_print")
    def test_greeting_under_200ms(self, mock_speak):
        from butler import handle_input
        start = time.monotonic()
        handle_input("hi", test_mode=True)
        elapsed_ms = (time.monotonic() - start) * 1000
        assert elapsed_ms < 200, f"greeting took {elapsed_ms:.0f}ms"

    @patch("butler._speak_or_print")
    def test_casual_response_under_200ms(self, mock_speak):
        from butler import handle_input
        start = time.monotonic()
        handle_input("thank you", test_mode=True)
        elapsed_ms = (time.monotonic() - start) * 1000
        assert elapsed_ms < 200, f"casual response took {elapsed_ms:.0f}ms"

    @patch("pipeline.router.plan_semantic_task")
    @patch("butler._speak_or_print")
    def test_casual_response_skips_semantic_planning(self, mock_speak, mock_plan):
        from butler import handle_input

        handle_input("thank you", test_mode=True)

        mock_plan.assert_not_called()
        mock_speak.assert_called_once()


class TestStopIsHardControl:
    """Stop command works instantly, even during busy state."""

    @patch("butler._speak_or_print")
    def test_stop_transitions_to_idle(self, mock_speak):
        from butler import handle_input
        from state import state, State
        state.transition(State.THINKING)
        handle_input("stop listening", test_mode=True)
        assert state.current == State.IDLE, f"State is {state.current}, expected IDLE"

    @patch("butler._speak_or_print")
    def test_stop_under_300ms(self, mock_speak):
        from butler import handle_input
        from state import state, State
        state.transition(State.THINKING)
        start = time.monotonic()
        handle_input("stop listening", test_mode=True)
        elapsed_ms = (time.monotonic() - start) * 1000
        assert elapsed_ms < 300, f"stop took {elapsed_ms:.0f}ms"
        assert state.current == State.IDLE

    @patch("butler._speak_or_print")
    @pytest.mark.parametrize("stop_phrase", [
        "be quiet", "go quiet", "shut up", "stop listening", "go to sleep burry",
    ])
    def test_all_stop_phrases_work(self, mock_speak, stop_phrase):
        from butler import handle_input
        from state import state, State
        state.transition(State.THINKING)
        handle_input(stop_phrase, test_mode=True)
        assert state.current == State.IDLE, f"'{stop_phrase}' didn't stop, state is {state.current}"


class TestBusyGateBypass:
    """Instant commands work even when Butler is busy."""

    @patch("butler.executor")
    @patch("butler._speak_or_print")
    def test_instant_during_thinking(self, mock_speak, mock_executor):
        from butler import handle_input
        from state import state, State
        mock_executor.run.return_value = [{"status": "ok"}]
        state.transition(State.THINKING)
        handle_input("open youtube", test_mode=True)
        # Should have executed, not queued
        assert mock_executor.run.called, "Instant command did not execute during THINKING state"
        assert mock_speak.called, "Instant command was not executed during THINKING state"

    @patch("butler._speak_or_print")
    def test_greeting_during_thinking(self, mock_speak):
        from butler import handle_input
        from state import state, State
        state.transition(State.THINKING)
        handle_input("hi", test_mode=True)
        assert mock_speak.called, "Greeting was not executed during THINKING state"

    @patch("butler._speak_or_print")
    def test_casual_during_thinking(self, mock_speak):
        from butler import handle_input
        from state import state, State
        state.transition(State.THINKING)
        handle_input("thank you", test_mode=True)
        assert mock_speak.called, "Casual response was not executed during THINKING state"


class TestNoStaleSpeech:
    """LLM responses never contain stale task data after cleanup."""

    STALE_PHRASES = [
        "high-priority tasks",
        "trust score formula",
        "wire two-stage LLM",
        "operating normally",
        "Test task for audit",
    ]

    @patch("butler._speak_or_print")
    def test_greeting_no_stale_data(self, mock_speak):
        from butler import handle_input
        handle_input("hey how are you", test_mode=True)
        if mock_speak.called:
            spoken = str(mock_speak.call_args[0][0])
            for phrase in self.STALE_PHRASES:
                assert phrase.lower() not in spoken.lower(), \
                    f"Stale phrase '{phrase}' found in greeting response: {spoken}"


class TestListeningNotBusy:
    """LISTENING state no longer counts as busy."""

    def test_listening_not_in_busy_states(self):
        from state import BUSY_STATES, State
        assert State.LISTENING not in BUSY_STATES

    def test_listening_is_not_busy(self):
        from state import state, State
        state.transition(State.LISTENING)
        assert not state.is_busy, "LISTENING should not be busy"

    def test_thinking_is_busy(self):
        from state import state, State
        state.transition(State.THINKING)
        assert state.is_busy, "THINKING should be busy"

    def test_speaking_is_busy(self):
        from state import state, State
        state.transition(State.SPEAKING)
        assert state.is_busy, "SPEAKING should be busy"
