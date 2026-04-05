#!/usr/bin/env python3

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from brain import mood_engine


class MoodEngineTests(unittest.TestCase):
    def setUp(self):
        super().setUp()
        self._tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tempdir.cleanup)
        self.mood_state_path = Path(self._tempdir.name) / "mood_state.json"
        self.path_patcher = patch.object(mood_engine, "MOOD_STATE_PATH", self.mood_state_path)
        self.path_patcher.start()
        self.addCleanup(self.path_patcher.stop)

    @patch("brain.mood_engine._load_active_task_count", return_value=4)
    @patch(
        "brain.mood_engine._load_project_snapshot",
        return_value=[{"status": "active", "blockers": [], "open_issues": 0}],
    )
    @patch("brain.mood_engine._load_session_summary", return_value="last session fixed live hud")
    @patch("brain.mood_engine.time.time", return_value=1000.0)
    def test_get_mood_prefers_proud_after_recent_progress(self, _mock_time, *_mocks):
        self.assertEqual(mood_engine.get_mood(force_refresh=True), "proud")
        state = mood_engine.load_mood_state()
        self.assertEqual(state["mood"], "proud")
        self.assertEqual(state["reason"], "recent_progress")

    @patch("brain.mood_engine._load_active_task_count", return_value=1)
    @patch(
        "brain.mood_engine._load_project_snapshot",
        return_value=[{"status": "active", "blockers": ["search offline"], "open_issues": 5}],
    )
    @patch("brain.mood_engine._load_session_summary", return_value="search is broken and offline")
    @patch("brain.mood_engine.time.time", return_value=1000.0)
    def test_get_mood_turns_blunt_when_context_is_broken(self, _mock_time, *_mocks):
        self.assertEqual(mood_engine.get_mood(force_refresh=True), "blunt")

    @patch("brain.mood_engine._load_active_task_count", return_value=0)
    @patch("brain.mood_engine._load_project_snapshot", return_value=[])
    @patch("brain.mood_engine._load_session_summary", return_value="")
    @patch("brain.mood_engine.time.time", return_value=1200.0)
    def test_recent_state_stays_stable_until_refresh_window(self, _mock_time, *_mocks):
        mood_engine.save_mood("proud", "recent_progress")
        with patch("brain.mood_engine._evaluate_mood", return_value=("blunt", "negative_signals")):
            self.assertEqual(mood_engine.get_mood(), "proud")

    @patch("brain.mood_engine._load_active_task_count", return_value=0)
    @patch("brain.mood_engine._load_project_snapshot", return_value=[])
    @patch("brain.mood_engine._load_session_summary", return_value="")
    @patch("brain.mood_engine.time.time", return_value=5000.0)
    def test_blunt_mood_decays_to_focused_after_timeout(self, _mock_time, *_mocks):
        self.mood_state_path.write_text(
            '{"mood":"blunt","set_at":1000.0,"reason":"negative_signals"}',
            encoding="utf-8",
        )
        self.assertEqual(mood_engine.get_mood(), "focused")
        state = mood_engine.load_mood_state()
        self.assertEqual(state["mood"], "focused")
        self.assertEqual(state["reason"], "decay")

    @patch(
        "brain.mood_engine._resolve_mood_state",
        return_value={"mood": "focused", "reason": "active_workload", "set_at": 123.0},
    )
    def test_describe_mood_state_returns_instruction_note_and_reason(self, _mock_resolve):
        state = mood_engine.describe_mood_state()
        self.assertEqual(state["name"], "focused")
        self.assertIn("direct", state["instruction"].lower())
        self.assertTrue(state["note"])
        self.assertEqual(state["reason"], "active_workload")
        self.assertEqual(state["set_at"], 123.0)


if __name__ == "__main__":
    unittest.main()
