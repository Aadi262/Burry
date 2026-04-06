import json
import unittest
from unittest.mock import MagicMock, patch

from daemon import bug_hunter, heartbeat


class DaemonConfigTests(unittest.TestCase):
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

    @patch("daemon.heartbeat._call", return_value="nothing")
    @patch("daemon.heartbeat.build_structured_context", return_value={"formatted": "[TASK LIST]\n  ○ Ship HUD"})
    @patch("daemon.heartbeat._upcoming_calendar_lines", return_value=["Upcoming: Demo at 2 PM"])
    @patch("daemon.heartbeat.datetime")
    def test_heartbeat_uses_lightweight_model(self, mock_datetime, _mock_calendar, _mock_ctx, mock_call):
        mock_datetime.now.return_value.hour = 12

        heartbeat.heartbeat_tick()

        self.assertTrue(heartbeat.HEARTBEAT_ENABLED)
        self.assertEqual(heartbeat.HEARTBEAT_MODEL, "gemma4:e4b")
        self.assertEqual(mock_call.call_args.args[1], "gemma4:e4b")
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
        self.assertEqual(bug_hunter.BUG_HUNTER_MODEL, "gemma4:e4b")
        self.assertEqual(mock_run_agent.call_args.kwargs["model_override"], "gemma4:e4b")


if __name__ == "__main__":
    unittest.main()
