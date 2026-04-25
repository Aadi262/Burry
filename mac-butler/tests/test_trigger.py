#!/usr/bin/env python3

import threading
import unittest
from unittest.mock import patch

import trigger


class TriggerTests(unittest.TestCase):
    def tearDown(self):
        trigger._session_active = False
        trigger._session_thread = None
        trigger._clap_thread = None
        trigger._wake_thread = None
        trigger._shutdown_event = threading.Event()
        trigger.state.transition(trigger.State.IDLE)

    @patch("trigger.note_runtime_event")
    @patch("voice.speak")
    @patch("trigger.publish_ui_event")
    @patch("brain.briefing.build_briefing", return_value="Mumbai: ☁️ +31°C. What are we building?")
    def test_speak_startup_briefing_broadcasts_and_speaks(
        self,
        _mock_briefing,
        mock_publish,
        mock_speak,
        mock_note_event,
    ):
        trigger._speak_startup_briefing()

        mock_speak.assert_called_once()
        mock_publish.assert_called_once()
        self.assertEqual(mock_publish.call_args.args[0], "briefing_spoken")
        self.assertEqual(mock_publish.call_args.args[1]["text"], "Mumbai. plus 31 degrees Celsius. What are we building?")
        self.assertEqual(mock_speak.call_args.args[0], "Mumbai. plus 31 degrees Celsius. What are we building?")
        mock_note_event.assert_called_once()

    @patch("trigger._planning_keepalive_model", return_value="ollama_local::gemma4:e4b")
    @patch("trigger.requests.post")
    def test_warm_planning_model_uses_keep_alive_request(self, mock_post, _mock_model):
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
        self.assertIn("http://127.0.0.1:7532", printed)

    @patch("trigger.start_wake_word_daemon", return_value=object())
    @patch("trigger.threading.Thread")
    def test_start_passive_triggers_starts_clap_and_wake_paths(self, mock_thread, mock_wake):
        worker = mock_thread.return_value
        worker.is_alive.return_value = False
        trigger._clap_thread = None
        trigger._wake_thread = None

        status = trigger.start_passive_triggers(enable_clap=True, enable_wake=True)

        self.assertEqual(status["clap"], "started")
        self.assertEqual(status["wake"], "started")
        mock_thread.assert_called_once_with(
            target=trigger.start_clap_trigger,
            daemon=True,
            name="burry-clap-trigger",
        )
        worker.start.assert_called_once()
        mock_wake.assert_called_once()

    @patch("trigger._write_session_end_summary")
    @patch("trigger._observe_session_project_relationships")
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
        mock_observe,
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
        mock_observe.assert_called_once()
        trigger._shutdown_event = original_shutdown

    @patch("trigger._write_session_end_summary")
    @patch("trigger._observe_session_project_relationships")
    @patch("butler.reset_conversation_context")
    @patch("butler.handle_input")
    @patch("voice.stt.listen_for_command", side_effect=["hello"])
    @patch("voice.tts.is_speaking", side_effect=[True, False, False])
    @patch("time.sleep")
    @patch("trigger.note_session_active")
    @patch("trigger._clear_session_flag")
    def test_continuous_session_keeps_mic_closed_while_tts_is_active(
        self,
        _mock_clear_flag,
        _mock_note_session,
        mock_sleep,
        _mock_is_speaking,
        _mock_listen,
        mock_handle,
        _mock_reset_context,
        _mock_observe,
        _mock_summary,
    ):
        original_shutdown = trigger._shutdown_event
        trigger._shutdown_event = threading.Event()

        def _handle(_text):
            trigger._shutdown_event.set()

        mock_handle.side_effect = _handle
        trigger.state.transition(trigger.State.WAITING)

        trigger._run_continuous_session()

        mock_sleep.assert_any_call(0.08)
        mock_handle.assert_called_once_with("hello")
        trigger._shutdown_event = original_shutdown

    @patch("trigger._write_session_end_summary")
    @patch("trigger._observe_session_project_relationships")
    @patch("butler.reset_conversation_context")
    @patch("butler.handle_input")
    @patch("voice.stt.listen_for_command", side_effect=[
        "here s a summary of the latest developments about india",
        "sleep",
    ])
    @patch("voice.tts.is_speaking", return_value=False)
    @patch("voice.tts.is_recent_speech_echo", side_effect=[True, False])
    @patch("trigger.note_session_active")
    @patch("trigger._clear_session_flag")
    def test_continuous_session_drops_recent_tts_echo_before_dispatch(
        self,
        _mock_clear_flag,
        _mock_note_session,
        _mock_echo,
        _mock_is_speaking,
        _mock_listen,
        mock_handle,
        _mock_reset_context,
        _mock_observe,
        _mock_summary,
    ):
        original_shutdown = trigger._shutdown_event
        trigger._shutdown_event = threading.Event()
        trigger.state.transition(trigger.State.WAITING)

        trigger._run_continuous_session()

        mock_handle.assert_called_once_with("sleep")
        trigger._shutdown_event = original_shutdown

    @patch(
        "projects.load_projects",
        return_value=[
            {
                "name": "mac-butler",
                "aliases": ["butler"],
                "path": "~/Burry/mac-butler",
            },
            {
                "name": "Adpilot",
                "aliases": ["adpilot"],
                "path": "/Users/adityatiwari/Desktop/Development/Adpilot",
            },
        ],
    )
    def test_session_touched_projects_uses_aliases_and_paths(self, _mock_load_projects):
        touched = trigger._session_touched_projects(
            ["open adpilot and then check mac-butler"],
            [{"type": "run_command", "cwd": "~/Burry/mac-butler"}],
        )

        self.assertIn("mac-butler", touched)
        self.assertIn("Adpilot", touched)

    @patch("memory.graph.observe_project_relationships")
    @patch("trigger._session_touched_projects", return_value=["mac-butler"])
    def test_observe_session_project_relationships_passes_aggregated_context(
        self,
        mock_touched,
        mock_observe,
    ):
        trigger._observe_session_project_relationships(
            ["open mac-butler", "run the tests"],
            ["Opening the project.", "Tests are green."],
            [{"type": "open_project", "name": "mac-butler"}],
        )

        mock_touched.assert_called_once()
        self.assertEqual(mock_observe.call_args.kwargs["text"], "open mac-butler run the tests")
        self.assertEqual(mock_observe.call_args.kwargs["speech"], "Opening the project. Tests are green.")
        self.assertEqual(mock_observe.call_args.kwargs["touched_projects"], ["mac-butler"])

    @patch("butler.reset_live_session_state")
    @patch("butler.reset_conversation_context")
    @patch("trigger.note_session_active")
    @patch("trigger.print")
    def test_on_trigger_ignores_duplicate_active_session(
        self,
        _mock_print,
        mock_note_session,
        _mock_reset_context,
        mock_reset_state,
    ):
        trigger._shutdown_event = threading.Event()
        trigger._session_active = True
        trigger.state.transition(trigger.State.IDLE)

        trigger.on_trigger()

        mock_reset_state.assert_not_called()
        mock_note_session.assert_not_called()


if __name__ == "__main__":
    unittest.main()
