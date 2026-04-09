#!/usr/bin/env python3

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from runtime import log_store
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

    def test_tool_activity_and_memory_recall_persist_runtime_state(self):
        with tempfile.TemporaryDirectory() as tempdir:
            runtime_path = Path(tempdir) / "runtime_state.json"
            with patch.object(telemetry, "RUNTIME_STATE_PATH", runtime_path):
                telemetry.note_tool_started("browse_web", "latest AI news")
                telemetry.note_tool_finished("browse_web", "ok", "Read 3 pages")
                telemetry.note_memory_recall(
                    "auth decision",
                    [{"timestamp": "2026-04-06T12:00:00", "speech": "Decided JWT, no sessions.", "score": 0.91}],
                )
                state = telemetry.load_runtime_state()

        self.assertEqual(state["active_tools"], [])
        self.assertEqual(state["tool_stream"][-2]["status"], "running")
        self.assertEqual(state["tool_stream"][-1]["status"], "ok")
        self.assertEqual(state["last_memory_recall"]["query"], "auth decision")
        self.assertEqual(state["last_memory_recall"]["matches"][0]["speech"], "Decided JWT, no sessions.")
        self.assertEqual(state["events"][-1]["kind"], "memory")

    def test_note_ambient_context_persists_three_bullets(self):
        with tempfile.TemporaryDirectory() as tempdir:
            runtime_path = Path(tempdir) / "runtime_state.json"
            with patch.object(telemetry, "RUNTIME_STATE_PATH", runtime_path):
                telemetry.note_ambient_context(
                    [
                        "- mac-butler blocker: auth recall still fails",
                        "- adpilot depends on deploy creds",
                        "- email-infra shares VPS with staging queue",
                        "- ignored extra bullet",
                    ]
                )
                state = telemetry.load_runtime_state()

        self.assertEqual(len(state["ambient_context"]), 3)
        self.assertEqual(state["ambient_context"][0], "mac-butler blocker: auth recall still fails")
        self.assertEqual(state["events"][-1]["kind"], "ambient")

    def test_conversation_turns_and_project_hint_persist(self):
        with tempfile.TemporaryDirectory() as tempdir:
            runtime_path = Path(tempdir) / "runtime_state.json"
            with patch.object(telemetry, "RUNTIME_STATE_PATH", runtime_path):
                telemetry.note_conversation_turns(
                    [
                        {"heard": "what's next", "intent": "what_next", "spoken": "Fix auth recall.", "time": "2026-04-06T12:00:00"},
                    ]
                )
                telemetry.note_project_context_hint("mac-butler", "Auth recall notes")
                hint = telemetry.consume_project_context_hint()
                state = telemetry.load_runtime_state()

        self.assertEqual(state["turns"][0]["intent"], "what_next")
        self.assertEqual(hint["project"], "mac-butler")
        self.assertEqual(state["project_context_hint"]["project"], "")

    def test_metrics_and_jsonl_logs_are_persisted(self):
        with tempfile.TemporaryDirectory() as tempdir:
            runtime_path = Path(tempdir) / "runtime_state.json"
            log_path = Path(tempdir) / "runtime_events.jsonl"
            with patch.object(telemetry, "RUNTIME_STATE_PATH", runtime_path), patch.object(
                log_store,
                "RUNTIME_EVENT_LOG_PATH",
                log_path,
            ):
                telemetry.note_heard_text("open youtube")
                telemetry.note_intent("open_app", {"app": "youtube"}, 1.0, raw="open youtube")
                telemetry.note_spoken_text("Opening YouTube.")
                telemetry.note_tool_started("open_url_in_browser", "https://youtube.com")
                telemetry.note_tool_finished("open_url_in_browser", "ok", "opened https://youtube.com")

                metrics = telemetry.load_metrics()
                logs = log_store.load_recent_runtime_events(limit=10)

        self.assertEqual(metrics["heard_commands"], 1)
        self.assertEqual(metrics["intents_resolved"], 1)
        self.assertEqual(metrics["spoken_responses"], 1)
        self.assertEqual(metrics["tool_runs_started"], 1)
        self.assertEqual(metrics["tool_runs_completed"], 1)
        self.assertGreaterEqual(len(logs), 5)
        self.assertEqual(logs[-1]["kind"], "tool")


if __name__ == "__main__":
    unittest.main()
