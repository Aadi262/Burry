#!/usr/bin/env python3

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class TestProjectMemoryWriteBack(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.memory_path = Path(self.tmpdir.name) / "butler_memory.json"

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_run_command_records_verification_state_for_project(self):
        from memory import store

        with patch.object(store, "MEMORY_PATH", self.memory_path), patch(
            "memory.layered.save_project_detail"
        ) as save_detail:
            touched = store.record_project_execution(
                "run the full test suite for mac-butler",
                "Running the checks.",
                [
                    {
                        "type": "run_command",
                        "cmd": "venv/bin/python -m unittest tests.test_comprehensive -v",
                        "cwd": "~/Burry/mac-butler",
                    }
                ],
                [{"status": "ok", "result": "92 tests passed"}],
            )

        self.assertIn("mac-butler", touched)
        state = json.loads(self.memory_path.read_text(encoding="utf-8"))["project_state"]["mac-butler"]
        self.assertEqual(state["last_action"], "run_command")
        self.assertEqual(state["last_test_status"], "ok")
        self.assertIn("unittest", state["last_test_command"])
        self.assertTrue(state.get("last_verified_at"))
        self.assertTrue(save_detail.called)

    def test_failed_project_command_keeps_failure_history(self):
        from memory import store

        with patch.object(store, "MEMORY_PATH", self.memory_path), patch(
            "memory.layered.save_project_detail"
        ):
            store.record_project_execution(
                "debug adpilot health check",
                "Checking Adpilot.",
                [
                    {
                        "type": "run_command",
                        "cmd": "curl -i http://127.0.0.1:3000/health",
                        "cwd": "/Users/adityatiwari/Desktop/Development/Adpilot",
                    }
                ],
                [{"status": "error", "error": "connection refused"}],
            )

        state = json.loads(self.memory_path.read_text(encoding="utf-8"))["project_state"]["Adpilot"]
        self.assertEqual(state["last_status"], "error")
        self.assertEqual(state["last_error"], "connection refused")
        self.assertIn("run_command: connection refused", state["recent_failures"][-1])

    def test_open_project_tracks_workspace_and_editor(self):
        from memory import store

        with patch.object(store, "MEMORY_PATH", self.memory_path), patch(
            "memory.layered.save_project_detail"
        ):
            store.record_project_execution(
                "open adpilot in antigravity",
                "Opening Adpilot.",
                [{"type": "open_project", "name": "adpilot", "editor": "antigravity"}],
                [{"status": "ok", "result": "opened Adpilot in antigravity"}],
            )

        state = json.loads(self.memory_path.read_text(encoding="utf-8"))["project_state"]["Adpilot"]
        self.assertEqual(state["last_editor"], "antigravity")
        self.assertEqual(
            state["last_workspace_path"],
            "/Users/adityatiwari/Desktop/Development/Adpilot",
        )
        self.assertTrue(state.get("last_opened"))


if __name__ == "__main__":
    unittest.main()
