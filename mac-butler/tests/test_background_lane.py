#!/usr/bin/env python3
"""Tests for background lane — news, search agents, etc.

Verifies that background lane intents:
1. Route correctly
2. Acknowledge instantly (<500ms)
3. Don't block the next command
"""
import os
import sys
import time
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("PYTEST_CURRENT_TEST", "1")


class TestBackgroundLaneRouting:
    """Background lane intents route correctly."""

    @pytest.mark.parametrize("text,expected_intent", [
        ("latest news", "news"),
        ("latest AI news", "news"),
        ("tech news in the last 24 hours", "news"),
        ("market pulse", "market"),
        ("what's happening in ai", "market"),
        ("check hacker news", "hackernews"),
    ])
    def test_routes_to_background_lane(self, text, expected_intent):
        from intents.router import route
        from butler import BACKGROUND_LANE_INTENTS
        intent = route(text)
        assert intent.name == expected_intent, f"'{text}' routed to {intent.name}"
        assert intent.name in BACKGROUND_LANE_INTENTS


class TestBackgroundAcknowledgment:
    """Background lane acknowledges instantly, doesn't block."""

    @patch("butler._speak_or_print")
    @patch("butler._record")
    def test_news_ack_under_500ms(self, mock_record, mock_speak):
        # Mock the agent dispatch so we don't actually run agents
        with patch("agents.runner.run_agent_async", return_value=None):
            from butler import handle_input
            start = time.monotonic()
            handle_input("latest AI news", test_mode=True)
            elapsed_ms = (time.monotonic() - start) * 1000
            assert elapsed_ms < 500, f"news ack took {elapsed_ms:.0f}ms"
            assert mock_speak.called, "No acknowledgment spoken"


class TestBackgroundDoesNotBlock:
    """Background lane doesn't prevent subsequent instant commands."""

    @patch("butler.executor")
    @patch("butler._speak_or_print")
    @patch("butler._record")
    def test_instant_after_background(self, mock_record, mock_speak, mock_executor):
        mock_executor.run.return_value = [{"status": "ok"}]
        with patch("agents.runner.run_agent_async", return_value=None):
            from butler import handle_input
            from state import state, State

            # Fire background command
            handle_input("latest AI news", test_mode=True)
            # State should be IDLE (test_mode) — not blocked
            assert state.current == State.IDLE, f"State stuck at {state.current}"

            # Instant command should work immediately
            mock_speak.reset_mock()
            handle_input("open youtube", test_mode=True)
            assert mock_speak.called, "Instant command blocked after background"

    @patch("butler._speak_or_print")
    @patch("butler._record")
    @patch("agents.runner.run_agent_async")
    def test_docker_status_uses_background_agent_when_vps_host_is_available(
        self,
        mock_agent,
        _mock_record,
        _mock_speak,
    ):
        with patch("butler._default_vps_host", return_value="root@example.com"):
            from butler import handle_input

            handle_input("docker status", test_mode=True)

        mock_agent.assert_called_once_with("vps", {"host": "root@example.com"})
