import json
import time
import unittest
from unittest.mock import MagicMock, patch

import numpy as np
from daemon import bug_hunter, heartbeat
from daemon import clap_detector, wake_word


class DaemonConfigTests(unittest.TestCase):
    def test_start_wake_word_daemon_returns_none_without_dependencies(self):
        with patch("daemon.wake_word._load_dependencies", return_value=None):
            self.assertIsNone(wake_word.start_wake_word_daemon())

    def test_stop_wake_word_daemon_joins_active_thread(self):
        thread = MagicMock()
        thread.is_alive.return_value = True
        wake_word._WAKE_THREAD = thread
        wake_word._WAKE_STOP.clear()

        wake_word.stop_wake_word_daemon(timeout=0.25)

        thread.join.assert_called_once_with(timeout=0.25)
        self.assertTrue(wake_word._WAKE_STOP.is_set())
        self.assertIsNone(wake_word._WAKE_THREAD)

    def test_clap_detector_ignores_audio_before_arming_and_while_session_active(self):
        detector = clap_detector.ClapDetector(on_clap_detected=MagicMock())
        detector.threshold = 0.05
        sample = np.ones((clap_detector.BLOCK_SIZE, 1), dtype=np.float32)

        detector.armed_at = time.time() + 5.0
        detector._audio_callback(sample, clap_detector.BLOCK_SIZE, None, None)
        self.assertFalse(detector.waiting_for_second)

        detector.armed_at = 0.0
        detector.waiting_for_second = True
        with patch("pathlib.Path.exists", return_value=True):
            detector._audio_callback(sample, clap_detector.BLOCK_SIZE, None, None)
        self.assertFalse(detector.waiting_for_second)

    def test_clap_detector_requires_sharp_transient_shape(self):
        detector = clap_detector.ClapDetector(on_clap_detected=MagicMock())
        detector.threshold = 0.05
        detector.armed_at = 0.0

        sustained = np.ones((clap_detector.BLOCK_SIZE, 1), dtype=np.float32) * 0.3
        detector._audio_callback(sustained, clap_detector.BLOCK_SIZE, None, None)
        self.assertFalse(detector.waiting_for_second)

        transient = np.zeros((clap_detector.BLOCK_SIZE, 1), dtype=np.float32)
        transient[:4, 0] = 1.0
        detector._audio_callback(transient, clap_detector.BLOCK_SIZE, None, None)
        self.assertTrue(detector.waiting_for_second)

    def test_wake_word_score_uses_max_prediction_value(self):
        score = wake_word._score_from_prediction({"hey_burry": 0.18, "other": [0.3, 0.81]})
        self.assertEqual(score, 0.81)

    def test_wake_word_dependency_help_mentions_install_steps(self):
        help_text = wake_word._dependency_help_text()
        self.assertIn("openwakeword", help_text)
        self.assertIn("venv/bin/pip install", help_text)
        self.assertIn("daemon/wake_word.py", help_text)

    @patch("builtins.print")
    @patch("daemon.wake_word.start_wake_word_daemon", return_value=None)
    def test_wake_word_main_prints_help_when_dependencies_missing(self, _mock_start, mock_print):
        result = wake_word.main()

        self.assertEqual(result, 1)
        printed = "\n".join(str(call.args[0]) for call in mock_print.call_args_list if call.args)
        self.assertIn("openWakeWord is not installed", printed)

    @patch("daemon.heartbeat.subprocess.run")
    def test_heartbeat_calendar_lines_format_upcoming_events(self, mock_run):
        mock_run.return_value = MagicMock(
            stdout="Standup||Tuesday, April 7, 2026 at 10:00:00 AM\n1:1||Tuesday, April 7, 2026 at 3:00:00 PM\n",
            stderr="",
            returncode=0,
        )

        lines = heartbeat._upcoming_calendar_lines(limit=2)

        self.assertEqual(
            lines,
            [
                "Upcoming: Standup at Tuesday, April 7, 2026 at 10:00:00 AM",
                "Upcoming: 1:1 at Tuesday, April 7, 2026 at 3:00:00 PM",
            ],
        )

    @patch("daemon.heartbeat._background_model_call", return_value="nothing")
    @patch("daemon.heartbeat.build_structured_context", return_value={"formatted": "[TASK LIST]\n  ○ Ship HUD"})
    @patch("daemon.heartbeat._upcoming_calendar_lines", return_value=["Upcoming: Demo at 2 PM"])
    @patch("daemon.heartbeat.datetime")
    def test_heartbeat_uses_lightweight_model(self, mock_datetime, _mock_calendar, _mock_ctx, mock_call):
        mock_datetime.now.return_value.hour = 12

        heartbeat.heartbeat_tick()

        self.assertTrue(heartbeat.HEARTBEAT_ENABLED)
        self.assertTrue(heartbeat.HEARTBEAT_MODEL.startswith("nvidia::"))
        self.assertEqual(mock_call.call_args.args[1], heartbeat.HEARTBEAT_MODEL)
        self.assertIn("[CALENDAR]", mock_call.call_args.args[0])

    @patch("daemon.bug_hunter.notify")
    @patch("daemon.bug_hunter.Executor")
    @patch("daemon.bug_hunter.run_agent", return_value={"result": "Blocker found"})
    @patch("daemon.bug_hunter.subprocess.run")
    def test_bug_hunter_uses_lightweight_model(self, mock_subprocess, mock_run_agent, mock_executor, _mock_notify):
        mock_subprocess.return_value = MagicMock(
            stdout=json.dumps(
                {
                    "ok": False,
                    "steps": [{"name": "system_check", "ok": False, "output": "boom"}],
                }
            ),
            stderr="",
        )
        mock_executor.return_value = MagicMock()

        bug_hunter.run_bug_hunt_once()

        self.assertTrue(bug_hunter.BUG_HUNTER_ENABLED)
        self.assertTrue(bug_hunter.BUG_HUNTER_MODEL.startswith("nvidia::"))
        self.assertEqual(mock_run_agent.call_args.kwargs["model_override"], bug_hunter.BUG_HUNTER_MODEL)
        command = mock_subprocess.call_args.args[0]
        self.assertIn("--phase1-host", command)
        self.assertIn("--phase1-host-only", command)
        self.assertIn("--phase3a-host", command)
        self.assertIn("--phase3a-host-only", command)


if __name__ == "__main__":
    unittest.main()
