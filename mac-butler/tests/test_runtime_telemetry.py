#!/usr/bin/env python3

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from runtime import telemetry


class RuntimeTelemetryTests(unittest.TestCase):
    def test_note_session_intent_and_speech_persist_runtime_state(self):
        with tempfile.TemporaryDirectory() as tempdir:
            runtime_path = Path(tempdir) / "runtime_state.json"
            with patch.object(telemetry, "RUNTIME_STATE_PATH", runtime_path):
                telemetry.note_session_active(True, source="trigger")
                telemetry.note_state_transition("idle", "thinking")
                telemetry.note_heard_text("search ranveer alahabadia on youtube")
                telemetry.note_intent("open_app", {"name": "YouTube results"}, 1.0, raw="search ranveer alahabadia on youtube")
                telemetry.note_spoken_text("Opening YouTube results.")

                state = telemetry.load_runtime_state()

        self.assertTrue(state["session_active"])
        self.assertEqual(state["state"], "thinking")
        self.assertEqual(state["last_heard_text"], "search ranveer alahabadia on youtube")
        self.assertEqual(state["last_intent"]["name"], "open_app")
        self.assertEqual(state["last_spoken_text"], "Opening YouTube results.")
        self.assertGreaterEqual(len(state["events"]), 5)

    def test_note_workspace_context_persists_workspace_payload(self):
        with tempfile.TemporaryDirectory() as tempdir:
            runtime_path = Path(tempdir) / "runtime_state.json"
            with patch.object(telemetry, "RUNTIME_STATE_PATH", runtime_path):
                telemetry.note_workspace_context(
                    focus_project="mac-butler",
                    frontmost_app="Terminal",
                    workspace="/Users/adityatiwari/Burry/mac-butler",
                )
                state = telemetry.load_runtime_state()

        self.assertEqual(state["workspace"]["focus_project"], "mac-butler")
        self.assertEqual(state["workspace"]["frontmost_app"], "Terminal")
        self.assertEqual(state["workspace"]["workspace"], "/Users/adityatiwari/Burry/mac-butler")
        self.assertEqual(state["events"][-1]["kind"], "workspace")

    def test_note_agent_result_persists_latest_agent_result(self):
        with tempfile.TemporaryDirectory() as tempdir:
            runtime_path = Path(tempdir) / "runtime_state.json"
            with patch.object(telemetry, "RUNTIME_STATE_PATH", runtime_path):
                telemetry.note_agent_result("news", "ok", "AI headlines ready")
                state = telemetry.load_runtime_state()

        self.assertEqual(state["last_agent_result"]["agent"], "news")
        self.assertEqual(state["last_agent_result"]["status"], "ok")
        self.assertEqual(state["last_agent_result"]["result"], "AI headlines ready")
        self.assertEqual(state["events"][-1]["kind"], "agent_result")


if __name__ == "__main__":
    unittest.main()
