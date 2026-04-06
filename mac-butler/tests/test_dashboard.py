import asyncio
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from projects import dashboard
from projects.dashboard import (
    _event_stream_message,
    _spawn_native_shell,
    _wait_for_dashboard_health,
    generate_dashboard,
)


class DashboardTests(unittest.TestCase):
    def test_mac_activity_payload_reads_memory_file(self):
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "mac_state.json"
            path.write_text('{"frontmost_app":"Cursor","open_apps":["Cursor","Spotify"]}', encoding="utf-8")
            with patch.object(dashboard, "MAC_STATE_PATH", path):
                payload = dashboard._mac_activity_payload()

        self.assertEqual(payload["frontmost_app"], "Cursor")
        self.assertEqual(payload["open_apps"], ["Cursor", "Spotify"])

    def test_graph_payload_reads_dependency_file(self):
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "graph.json"
            path.write_text('{"edges":[{"from":"mac-butler","to":"email-infra","type":"blocked_by"}]}', encoding="utf-8")
            with patch.object(dashboard, "GRAPH_PATH", path):
                payload = dashboard._graph_payload()

        self.assertEqual(payload["edges"][0]["type"], "blocked_by")

    def test_dashboard_projects_preserves_blurb_field(self):
        with patch(
            "projects.dashboard._load_projects_raw",
            return_value=[
                {
                    "name": "mac-butler",
                    "status": "active",
                    "completion": 71,
                    "description": "Local operator",
                    "blurb": "Local Mac operator stack. Next up is voice follow-up cleanup.",
                    "next_tasks": [],
                    "blockers": [],
                }
            ],
        ):
            projects = dashboard._dashboard_projects()

        self.assertEqual(projects[0]["blurb"], "Local Mac operator stack. Next up is voice follow-up cleanup.")

    def test_tasks_payload_reads_task_file(self):
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "tasks.json"
            path.write_text('{"tasks":[{"project":"mac-butler","title":"Ship HUD graph"}]}', encoding="utf-8")
            with patch.object(dashboard, "TASKS_PATH", path):
                payload = dashboard._tasks_payload()

        self.assertEqual(payload["tasks"][0]["project"], "mac-butler")

    @patch("projects.dashboard.subprocess.run")
    @patch("projects.dashboard.time.monotonic", side_effect=[100.0, 110.0])
    def test_vps_payload_caches_remote_status(self, _mock_time, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='{"status":"online","cpu":31.2,"memory":48.0,"disk":71.5,"uptime":"1024"}',
            stderr="",
        )
        with patch.object(dashboard, "_VPS_CACHE_PAYLOAD", None), patch.object(dashboard, "_VPS_CACHE_AT", 0.0):
            first = dashboard._vps_payload()
            second = dashboard._vps_payload()

        self.assertEqual(first["status"], "online")
        self.assertEqual(second["cpu"], 31.2)
        mock_run.assert_called_once()

    @patch(
        "projects.dashboard.operator_snapshot",
        return_value={
            "session_label": "live",
            "session_tone": "healthy",
            "state_label": "Listening",
            "state_tone": "healthy",
            "last_heard_text": "search ranveer alahabadia on youtube",
            "last_heard_at": "2026-04-05T19:22:55",
            "last_spoken_text": "Opening YouTube results.",
            "last_spoken_at": "2026-04-05T19:22:56",
            "last_intent_name": "open_app",
            "last_intent_confidence": 1.0,
            "focus_project": "mac-butler",
            "frontmost_app": "Terminal",
            "workspace": "/Users/adityatiwari/Burry/mac-butler",
            "active_tools": ["browse_web"],
            "tool_stream": [
                {"tool": "browse_web", "status": "running", "detail": "latest ai news", "at": "2026-04-05T19:22:55"}
            ],
            "memory_recall": {
                "query": "auth decision",
                "matches": [{"speech": "Decided JWT, no sessions.", "timestamp": "2026-04-05T11:00:00"}],
                "at": "2026-04-05T19:22:54",
            },
            "ambient_context": [
                "mac-butler blocker: auth recall path still needs a fix",
                "email-infra depends on VPS stability",
                "Adpilot shares deploy resources with staging",
            ],
            "tasks": ["Ship live operator HUD"],
            "systems": [
                {"name": "Voice", "status": "edge", "detail": "en-US-AvaMultilingualNeural", "tone": "healthy"}
            ],
            "mcp": [
                {"name": "github", "status": "configured", "detail": "Disabled", "tone": "degraded"}
            ],
            "events": [
                {"kind": "heard", "message": "Heard: search ranveer alahabadia on youtube", "at": "2026-04-05T19:22:55"}
            ],
            "updated_at": "2026-04-05T19:22:56",
        },
    )
    @patch(
        "projects.dashboard._load_projects_raw",
        return_value=[
            {
                "name": "mac-butler",
                "status": "active",
                "completion": 71,
                "deploy_target": "Local Mac + Ollama",
                "live": True,
                "last_commit": "2026-04-05T10:00:00Z",
                "open_issues": 0,
                "health_status": "healthy",
                "blockers": ["Need better clap trigger filtering"],
                "next_tasks": ["Ship the dashboard checks"],
            }
        ],
    )
    def test_generate_dashboard_renders_health_and_verification(
        self,
        _mock_load,
        _mock_operator,
    ):
        html = generate_dashboard()

        self.assertIn("Burry Live Operator", html)
        self.assertIn("/style.css", html)
        self.assertIn("/app.js", html)
        self.assertIn("BURRY OS", html)
        self.assertIn("Workspace", html)
        self.assertIn("Ambient", html)
        self.assertIn("Recalled", html)
        self.assertIn("You said:", html)
        self.assertIn("Burry said:", html)
        self.assertIn("Events", html)
        self.assertIn("Projects", html)
        self.assertIn("project-list", html)
        self.assertIn("events-feed", html)
        self.assertIn("orb-canvas", html)
        self.assertIn("network-canvas", html)
        self.assertIn("Ask Burry anything", html)
        self.assertIn("tool-pill-strip", html)
        self.assertIn('type="module" src="/app.js?v=', html)
        self.assertIn('"wsUrl"', html)
        self.assertIn("search ranveer alahabadia on youtube", html)
        self.assertIn('"/vendor/three.module.js"', html)
        self.assertIn('"/vendor/addons/"', html)
        self.assertNotIn("unpkg.com/three", html)

    @patch("projects.dashboard.subprocess.Popen")
    @patch("projects.dashboard._wait_for_dashboard_health", return_value=True)
    @patch("projects.dashboard._native_shell_running", return_value=False)
    @patch("projects.dashboard._native_shell_available", return_value=True)
    def test_spawn_native_shell_uses_detached_process(
        self,
        _mock_available,
        _mock_running,
        _mock_health,
        mock_popen,
    ):
        process = MagicMock()
        mock_popen.return_value = process

        ok = _spawn_native_shell("http://127.0.0.1:3333")

        self.assertTrue(ok)
        self.assertTrue(mock_popen.called)
        self.assertTrue(mock_popen.call_args.kwargs["start_new_session"])

    @patch("projects.dashboard.time.sleep")
    @patch("projects.dashboard._url_ok", side_effect=[False, False, True])
    def test_wait_for_dashboard_health_retries_until_ready(self, mock_ok, _mock_sleep):
        self.assertTrue(_wait_for_dashboard_health("http://127.0.0.1:3333", timeout=1.0))
        self.assertEqual(mock_ok.call_count, 3)
        self.assertTrue(all(call.args[0].endswith("/health") for call in mock_ok.call_args_list))

    def test_event_stream_message_uses_sse_data_format(self):
        payload = {"state": "listening", "focus_project": "mac-butler"}
        frame = _event_stream_message(payload).decode("utf-8")

        self.assertTrue(frame.startswith("data: "))
        self.assertIn('"state":"listening"', frame)
        self.assertTrue(frame.endswith("\n\n"))

    @patch("projects.dashboard._dashboard_projects", return_value=[{"name": "mac-butler"}])
    @patch("projects.dashboard.operator_snapshot", return_value={"state": "listening"})
    def test_ws_handler_sends_operator_and_projects_payloads(self, _mock_operator, _mock_projects):
        websocket = AsyncMock()
        websocket.request = SimpleNamespace(path="/ws")
        websocket.wait_closed.return_value = None

        asyncio.run(dashboard._ws_handler(websocket))

        payloads = [json.loads(call.args[0]) for call in websocket.send.await_args_list]
        self.assertEqual(payloads[0], {"type": "operator", "payload": {"state": "listening"}})
        self.assertEqual(payloads[1], {"type": "projects", "payload": [{"name": "mac-butler"}]})

    @patch("projects.dashboard.subprocess.run")
    @patch("projects.dashboard._wait_for_dashboard_health", return_value=True)
    @patch("projects.dashboard._spawn_native_shell")
    def test_show_dashboard_window_prefers_browser_until_native_is_enabled(
        self,
        mock_spawn_native,
        _mock_health,
        mock_run,
    ):
        mock_run.return_value = MagicMock(returncode=0)
        with patch.object(dashboard, "USE_NATIVE_HUD", False):
            dashboard.show_dashboard_window(force=True)

        mock_spawn_native.assert_not_called()
        self.assertTrue(mock_run.called)

    @patch("brain.mood_engine.describe_mood_state", return_value={"name": "focused", "label": "Focused", "note": "Locked on the next step."})
    @patch("voice.describe_tts", return_value={"backend": "edge", "voice": "Ava"})
    @patch("voice.describe_stt", return_value={"backend": "faster", "active_model": "small.en"})
    @patch("tasks.get_active_tasks", return_value=[{"title": "Ship live HUD"}])
    @patch("runtime.load_runtime_state")
    @patch("context.mac_activity.load_state")
    @patch("projects.dashboard._url_ok", return_value=True)
    def test_operator_snapshot_prefers_runtime_workspace(
        self,
        _mock_url_ok,
        mock_mac_state,
        mock_runtime_state,
        _mock_tasks,
        _mock_stt,
        _mock_tts,
        _mock_mood,
    ):
        mock_runtime_state.return_value = {
            "state": "listening",
            "session_active": True,
            "updated_at": "2026-04-06T12:00:00",
            "workspace": {
                "focus_project": "mac-butler",
                "frontmost_app": "Terminal",
                "workspace": "/Users/adityatiwari/Burry/mac-butler",
            },
            "active_tools": ["recall_memory"],
            "tool_stream": [{"tool": "recall_memory", "status": "ok", "detail": "Found 3 matches", "at": "2026-04-06T12:00:00"}],
            "last_memory_recall": {
                "query": "auth decision",
                "matches": [{"speech": "Decided JWT, no sessions.", "score": 0.91}],
                "at": "2026-04-06T12:00:00",
            },
            "ambient_context": [
                "mac-butler blocker: auth recall path still needs a fix",
                "email-infra depends on VPS stability",
                "Adpilot shares deploy resources with staging",
            ],
            "events": [],
            "last_intent": {},
        }
        mock_mac_state.return_value = {
            "frontmost_app": "Cursor",
            "cursor_workspace": "/Users/adityatiwari/Burry/other-project",
        }

        payload = dashboard.operator_snapshot(
            projects=[{"name": "mac-butler", "path": "/Users/adityatiwari/Burry/mac-butler"}]
        )

        self.assertEqual(payload["focus_project"], "mac-butler")
        self.assertEqual(payload["frontmost_app"], "Terminal")
        self.assertEqual(payload["workspace"], "/Users/adityatiwari/Burry/mac-butler")
        self.assertEqual(payload["active_tools"], ["recall_memory"])
        self.assertEqual(payload["memory_recall"]["query"], "auth decision")
        self.assertEqual(len(payload["ambient_context"]), 3)


if __name__ == "__main__":
    unittest.main()
