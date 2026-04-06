#!/usr/bin/env python3

import threading
import unittest
from unittest.mock import patch

import trigger


class TriggerTests(unittest.TestCase):
    @patch("trigger.requests.post")
    def test_warm_planning_model_uses_keep_alive_request(self, mock_post):
        trigger._warm_planning_model()

        self.assertTrue(mock_post.called)
        payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(payload["prompt"], " ")
        self.assertEqual(payload["keep_alive"], "10m")
        self.assertEqual(payload["options"]["num_predict"], 1)

    @patch("trigger.print")
    @patch("projects.show_dashboard_window")
    @patch("projects.serve_dashboard", return_value=object())
    def test_start_dashboard_server_announces_live_hud(self, _mock_serve_dashboard, _mock_window, mock_print):
        trigger._start_dashboard_server()

        printed = "\n".join(str(call.args[0]) for call in mock_print.call_args_list if call.args)
        self.assertIn("http://127.0.0.1:3333", printed)

    @patch("trigger._write_session_end_summary")
    @patch("butler.reset_conversation_context")
    @patch("butler.handle_input")
    @patch("voice.stt.listen_for_command", side_effect=["hello"])
    @patch("trigger.note_session_active")
    @patch("trigger._clear_session_flag")
    def test_continuous_session_marks_listening_before_stt(
        self,
        _mock_clear_flag,
        _mock_note_session,
        _mock_listen,
        mock_handle,
        _mock_reset_context,
        _mock_summary,
    ):
        original_shutdown = trigger._shutdown_event
        trigger._shutdown_event = threading.Event()

        def _handle(_text):
            trigger._shutdown_event.set()

        mock_handle.side_effect = _handle
        trigger.state.transition(trigger.State.WAITING)

        with patch.object(trigger.state, "transition", wraps=trigger.state.transition) as mock_transition:
            trigger._run_continuous_session()

        transitioned_states = [call.args[0] for call in mock_transition.call_args_list if call.args]
        self.assertIn(trigger.State.LISTENING, transitioned_states)
        trigger._shutdown_event = original_shutdown


if __name__ == "__main__":
    unittest.main()
