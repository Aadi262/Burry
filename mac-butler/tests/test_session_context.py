#!/usr/bin/env python3

import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from brain.session_context import SessionContext


class SessionContextTests(unittest.TestCase):
    @patch("brain.session_context._broadcast_pending")
    def test_pending_flow_tracks_missing_fields_in_order(self, _mock_broadcast):
        ctx = SessionContext()
        ctx.set_pending("compose_email", {"recipient": "vedang"}, ["subject", "body"])

        pending = ctx.get_pending()
        self.assertEqual(pending["kind"], "compose_email")
        self.assertEqual(pending["missing"], ["subject", "body"])
        self.assertEqual(pending["next_field"], "subject")

        ctx.fill_pending("project update")
        pending = ctx.get_pending()
        self.assertEqual(pending["subject"], "project update")
        self.assertEqual(pending["missing"], ["body"])
        self.assertEqual(pending["next_field"], "body")

    @patch("brain.session_context._broadcast_pending")
    def test_pending_broadcast_uses_typed_phase2_payload(self, mock_broadcast):
        ctx = SessionContext()
        ctx.set_pending("compose_email", {"recipient": "vedang"}, ["subject", "body"])

        payload = mock_broadcast.call_args_list[-1].args[0]
        self.assertEqual(payload["contract_version"], "1.0")
        self.assertEqual(payload["kind"], "compose_email")
        self.assertEqual(payload["missing_fields"], ["subject", "body"])
        self.assertEqual(payload["details"]["recipient"], "vedang")

    @patch("brain.session_context._broadcast_pending")
    def test_clear_pending_marks_context_inactive(self, _mock_broadcast):
        ctx = SessionContext()
        ctx.set_pending("compose_email", {"recipient": "vedang"}, ["subject"])
        ctx.clear_pending()

        self.assertFalse(ctx.has_pending())
        self.assertIsNone(ctx.get_pending())

    @patch("brain.session_context._persistence_enabled", return_value=True)
    @patch("brain.session_context._broadcast_pending")
    def test_session_context_restores_recent_turns_and_pending_from_disk(self, _mock_broadcast, _mock_enabled):
        with tempfile.TemporaryDirectory() as tempdir:
            snapshot_path = Path(tempdir) / "session_context.json"
            with patch("brain.session_context.SESSION_CONTEXT_PATH", snapshot_path):
                writer = SessionContext()
                writer.add_user("write mail to vedang")
                writer.add_butler("What is the subject?")
                writer.set_pending("compose_email", {"recipient": "vedang"}, ["subject", "body"])
                writer.persist_now()

                restored = SessionContext()
                pending = restored.get_pending()

        self.assertEqual(restored.turns[-2]["text"], "write mail to vedang")
        self.assertEqual(restored.turns[-1]["text"], "What is the subject?")
        self.assertEqual(pending["kind"], "compose_email")
        self.assertEqual(pending["recipient"], "vedang")
        self.assertEqual(pending["missing"], ["subject", "body"])

    @patch("brain.session_context._persistence_enabled", return_value=True)
    @patch("brain.session_context._broadcast_pending")
    def test_session_context_skips_stale_snapshot_restore(self, _mock_broadcast, _mock_enabled):
        with tempfile.TemporaryDirectory() as tempdir:
            snapshot_path = Path(tempdir) / "session_context.json"
            stale_payload = {
                "turns": [{"role": "user", "text": "stale turn"}],
                "pending": {"kind": "compose_email", "data": {"recipient": "vedang"}, "required": ["subject"]},
                "updated_at": (datetime.now() - timedelta(days=2)).isoformat(timespec="seconds"),
            }
            snapshot_path.write_text(json.dumps(stale_payload), encoding="utf-8")
            with patch("brain.session_context.SESSION_CONTEXT_PATH", snapshot_path):
                restored = SessionContext()

        self.assertEqual(restored.turns, [])
        self.assertIsNone(restored.get_pending())


if __name__ == "__main__":
    unittest.main()
