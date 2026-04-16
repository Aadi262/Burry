#!/usr/bin/env python3

import unittest
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


if __name__ == "__main__":
    unittest.main()
