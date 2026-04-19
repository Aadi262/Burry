#!/usr/bin/env python3

import argparse
import unittest
from unittest.mock import MagicMock, patch

import butler


class ButlerRuntimeTests(unittest.TestCase):
    def tearDown(self):
        butler._release_live_runtime_lock()

    @patch("butler._save_backbone_session_state")
    @patch("butler.run_interactive")
    @patch("butler.run_passive_service")
    @patch("butler.reset_live_session_state")
    @patch("butler._acquire_live_runtime_lock", return_value=True)
    @patch("butler._report_brain_backend_status")
    @patch("channels.a2a_server.start_agentscope_a2a")
    @patch("brain.mcp_client.load_configured_mcp_servers")
    @patch("skills.load_skills")
    @patch("channels.imessage_channel.start_imessage_channel")
    @patch("butler.get_toolkit", return_value=object())
    @patch("butler.get_backbone", return_value=MagicMock(agent=object()))
    @patch("butler.start_ambient_daemon")
    @patch("butler._ensure_watcher_started")
    @patch("butler.configure_session_restore")
    @patch("butler._install_shutdown_handlers")
    @patch(
        "argparse.ArgumentParser.parse_args",
        return_value=argparse.Namespace(
            test=False,
            model=None,
            interactive=False,
            stt=False,
            briefing=False,
            command=None,
            clap_only=False,
        ),
    )
    def test_main_default_startup_uses_passive_standby(
        self,
        _mock_parse,
        _mock_install,
        _mock_restore,
        _mock_watcher,
        _mock_ambient,
        _mock_backbone,
        _mock_toolkit,
        _mock_imessage,
        _mock_skills,
        _mock_mcp,
        _mock_a2a,
        _mock_backend_status,
        _mock_lock,
        mock_reset_state,
        mock_passive,
        mock_interactive,
        _mock_save_state,
    ):
        butler.main()

        mock_reset_state.assert_called_once_with("default_standby")
        mock_passive.assert_called_once()
        mock_interactive.assert_not_called()

    @patch("butler._save_backbone_session_state")
    @patch("butler.run_interactive")
    @patch("butler.run_passive_service")
    @patch("butler.reset_live_session_state")
    @patch("butler._acquire_live_runtime_lock", return_value=True)
    @patch("butler._report_brain_backend_status")
    @patch("channels.a2a_server.start_agentscope_a2a")
    @patch("brain.mcp_client.load_configured_mcp_servers")
    @patch("skills.load_skills")
    @patch("channels.imessage_channel.start_imessage_channel")
    @patch("butler.get_toolkit", return_value=object())
    @patch("butler.get_backbone", return_value=MagicMock(agent=object()))
    @patch("butler.start_ambient_daemon")
    @patch("butler._ensure_watcher_started")
    @patch("butler.configure_session_restore")
    @patch("butler._install_shutdown_handlers")
    @patch(
        "argparse.ArgumentParser.parse_args",
        return_value=argparse.Namespace(
            test=False,
            model=None,
            interactive=False,
            stt=False,
            briefing=False,
            command=None,
            clap_only=True,
        ),
    )
    def test_main_default_startup_can_force_clap_only_standby(
        self,
        _mock_parse,
        _mock_install,
        _mock_restore,
        _mock_watcher,
        _mock_ambient,
        _mock_backbone,
        _mock_toolkit,
        _mock_imessage,
        _mock_skills,
        _mock_mcp,
        _mock_a2a,
        _mock_backend_status,
        _mock_lock,
        _mock_reset_state,
        mock_passive,
        _mock_interactive,
        _mock_save_state,
    ):
        butler.main()

        self.assertEqual(mock_passive.call_args.kwargs["enable_wake"], False)

    @patch("butler.run_passive_service")
    @patch("butler.reset_live_session_state")
    @patch("butler._acquire_live_runtime_lock", return_value=False)
    @patch("butler._report_brain_backend_status")
    @patch("channels.a2a_server.start_agentscope_a2a")
    @patch("brain.mcp_client.load_configured_mcp_servers")
    @patch("skills.load_skills")
    @patch("channels.imessage_channel.start_imessage_channel")
    @patch("butler.get_toolkit", return_value=object())
    @patch("butler.get_backbone", return_value=MagicMock(agent=object()))
    @patch("butler.start_ambient_daemon")
    @patch("butler._ensure_watcher_started")
    @patch("butler.configure_session_restore")
    @patch("butler._install_shutdown_handlers")
    @patch(
        "argparse.ArgumentParser.parse_args",
        return_value=argparse.Namespace(
            test=False,
            model=None,
            interactive=False,
            stt=False,
            briefing=False,
            command=None,
            clap_only=False,
        ),
    )
    def test_main_exits_when_live_runtime_lock_is_held(
        self,
        _mock_parse,
        _mock_install,
        _mock_restore,
        _mock_watcher,
        _mock_ambient,
        _mock_backbone,
        _mock_toolkit,
        _mock_imessage,
        _mock_skills,
        _mock_mcp,
        _mock_a2a,
        _mock_backend_status,
        _mock_lock,
        mock_reset_state,
        mock_passive,
    ):
        butler.main()

        mock_reset_state.assert_not_called()
        mock_passive.assert_not_called()

    @patch("butler.print")
    @patch("butler.fcntl.flock", side_effect=BlockingIOError)
    @patch("pathlib.Path.mkdir")
    def test_acquire_live_runtime_lock_reports_existing_owner(
        self,
        _mock_mkdir,
        _mock_flock,
        mock_print,
    ):
        handle = MagicMock()
        handle.read.return_value = "4242"
        with patch("pathlib.Path.open", return_value=handle):
            acquired = butler._acquire_live_runtime_lock()

        self.assertFalse(acquired)
        self.assertIsNone(butler._LIVE_RUNTIME_LOCK_HANDLE)
        self.assertIn("pid 4242", mock_print.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
