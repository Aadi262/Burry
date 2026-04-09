import unittest
from types import SimpleNamespace
from unittest.mock import patch

import butler
from agents import runner
from memory import knowledge_base
from projects import dashboard
from state import State


class Phase2QuickWinTests(unittest.TestCase):
    def tearDown(self):
        butler._clear_pending_command_state()
        butler._invalidate_context_cache()
        butler.state.transition(State.IDLE)

    def test_context_cache_ttl_is_120_seconds(self):
        self.assertEqual(butler._CTX_CACHE_TTL_SECONDS, 120.0)

    @patch("butler.build_structured_context", return_value={"formatted": "[FOCUS]\n  project: mac-butler"})
    def test_context_cache_reuses_single_build(self, mock_build):
        butler._invalidate_context_cache()

        first = butler._get_cached_context()
        second = butler._get_cached_context()

        self.assertEqual(first, second)
        mock_build.assert_called_once()

    def test_handle_input_reuses_early_route_result(self):
        intent = SimpleNamespace(name="unknown", params={}, confidence=0.61)
        with patch("butler._ensure_watcher_started"), \
             patch("butler.route", return_value=intent) as mock_route, \
             patch("butler._resolve_pending_dialogue", return_value=None), \
             patch("butler._looks_like_followup_reference", return_value=False), \
             patch("butler._handle_meta_intent", return_value=False), \
             patch("butler._unknown_response_for_text", return_value="Handled."), \
             patch("butler._reply_without_action") as mock_reply:
            butler.handle_input("something odd", test_mode=True)

        self.assertEqual(mock_route.call_count, 1)
        mock_reply.assert_called_once()

    def test_embedding_dimensions_are_static(self):
        self.assertEqual(knowledge_base._detect_embedding_dimensions(), 768)

    @patch("agents.runner._check_memory")
    def test_prepare_model_request_only_checks_memory(self, mock_check_memory):
        runner._prepare_model_request("gemma4:e4b")
        mock_check_memory.assert_called_once()

    def test_dashboard_stream_interval_is_half_second(self):
        self.assertEqual(dashboard.STREAM_INTERVAL_SECONDS, 0.5)


if __name__ == "__main__":
    unittest.main()
