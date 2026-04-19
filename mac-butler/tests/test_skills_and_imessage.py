import unittest
from unittest.mock import MagicMock, patch

import skills
from channels import imessage_channel


class SkillsLoaderTests(unittest.TestCase):
    def tearDown(self):
        skills._REGISTRY = []
        skills._LOADED = False

    def test_load_skills_is_idempotent(self):
        skills.load_skills()
        first = skills.list_skills()

        skills.load_skills()
        second = skills.list_skills()

        self.assertEqual(first, second)
        self.assertEqual(len(second), len(set(second)))

    def test_email_skill_splits_subject_and_body_cleanly(self):
        skills.load_skills()

        skill, entities = skills.match_skill(
            "email vedang@gmail.com with subject test and body hello"
        )

        self.assertIsNotNone(skill)
        self.assertEqual(skill["name"], "email_skill")
        self.assertEqual(entities["subject"], "test")
        self.assertEqual(entities["body"], "hello")

    def test_calendar_create_commands_are_left_for_router_executor_path(self):
        skills.load_skills()

        skill, _entities = skills.match_skill("create a meeting called standup at tomorrow 3pm")

        self.assertIsNone(skill)


class IMessageChannelTests(unittest.TestCase):
    def tearDown(self):
        imessage_channel._last_seen_id = None
        imessage_channel._last_outbound_message = ""

    def test_sender_allowlist_normalizes_chat_and_handle_formats(self):
        with patch(
            "channels.imessage_channel._approved_contacts",
            return_value=["+918169704311", "me@icloud.com"],
        ):
            self.assertTrue(imessage_channel._sender_is_approved("any;-;+918169704311"))
            self.assertTrue(imessage_channel._sender_is_approved("participant id UUID:+918169704311"))
            self.assertTrue(imessage_channel._sender_is_approved("ME@ICLOUD.COM"))
            self.assertFalse(imessage_channel._sender_is_approved("+919999999999"))

    @patch("channels.imessage_channel._send_reply")
    @patch("channels.imessage_channel._latest_reply_after", return_value="Reply back")
    @patch("channels.imessage_channel._latest_recorded_timestamp", return_value="2026-04-06T20:00:00")
    @patch("channels.imessage_channel._approved_contacts", return_value=[])
    @patch("channels.imessage_channel._get_latest_message", return_value=("msg-1", "Check VPS", "me@icloud.com"))
    def test_process_latest_message_runs_butler_and_sends_reply(
        self,
        _mock_message,
        _mock_contacts,
        _mock_timestamp,
        _mock_reply_after,
        mock_send_reply,
    ):
        handler = MagicMock()

        imessage_channel._process_latest_message(handler)

        handler.assert_called_once_with("Check VPS", test_mode=False)
        mock_send_reply.assert_called_once_with("me@icloud.com", "Reply back")
        self.assertEqual(imessage_channel._last_seen_id, "msg-1")

    @patch("channels.imessage_channel._approved_contacts", return_value=[])
    @patch("channels.imessage_channel._get_latest_message", return_value=("msg-2", "Reply back", "me@icloud.com"))
    def test_process_latest_message_skips_outbound_echo(self, _mock_message, _mock_contacts):
        imessage_channel._last_outbound_message = "Reply back"
        handler = MagicMock()

        imessage_channel._process_latest_message(handler)

        handler.assert_not_called()
        self.assertEqual(imessage_channel._last_seen_id, "msg-2")

    @patch("channels.imessage_channel._approved_contacts", return_value=["allowed@icloud.com"])
    @patch("channels.imessage_channel._get_latest_message", return_value=("msg-3", "hello", "other@icloud.com"))
    def test_process_latest_message_respects_contact_allowlist(self, _mock_message, _mock_contacts):
        handler = MagicMock()

        imessage_channel._process_latest_message(handler)

        handler.assert_not_called()
        self.assertIsNone(imessage_channel._last_seen_id)


if __name__ == "__main__":
    unittest.main()
