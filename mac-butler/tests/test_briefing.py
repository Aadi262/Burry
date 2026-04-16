#!/usr/bin/env python3

import unittest
from unittest.mock import MagicMock, patch

from brain.briefing import build_briefing


class BriefingTests(unittest.TestCase):
    @patch("brain.briefing.subprocess.run")
    @patch("brain.briefing.requests.get")
    @patch("tasks.task_store.get_active_tasks")
    def test_build_briefing_assembles_parallel_sources(
        self,
        mock_tasks,
        mock_get,
        mock_run,
    ):
        github_response = MagicMock()
        github_response.content = b"1"
        github_response.json.return_value = [
            {
                "type": "PushEvent",
                "repo": {"name": "Aadi262/mac-butler"},
                "payload": {"commits": [{"message": "ship briefing flow"}]},
            }
        ]
        weather_response = MagicMock()
        weather_response.text = "Mumbai: 31C"
        weather_response.content = b"1"
        mock_get.side_effect = [github_response, weather_response]
        mock_tasks.return_value = [{"title": "Ship startup briefing"}, {"title": "Fix pending flow"}]
        mock_run.return_value = MagicMock(stdout="Demo, Review", stderr="", returncode=0)

        briefing = build_briefing()

        self.assertIn("Last push: mac-butler", briefing)
        self.assertIn("Mumbai: 31C", briefing)
        self.assertIn("Pending: Ship startup briefing", briefing)
        self.assertTrue(briefing.endswith("What are we building?"))


if __name__ == "__main__":
    unittest.main()
