#!/usr/bin/env python3

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from context import notifications


class NotificationCenterTests(unittest.TestCase):
    def test_parse_notification_lines_extracts_bundle_and_status(self):
        output = """
2026-04-25 19:41:34.401 Df usernoted[610:23fed63] [com.apple.unc:application] Request uuid: C99D7273 from com.google.Chrome.framework.AlertNotificationService expired
2026-04-25 19:41:34.431 Df usernoted[610:23fed63] [com.apple.unc:application] _removeDisplayed: Removing [C99D7273] from com.tinyspeck.slackmacgap
        """.strip()

        items = notifications._parse_notification_lines(output, limit=6)

        self.assertEqual(items[0]["app"], "Google Chrome")
        self.assertEqual(items[0]["status"], "expired")
        self.assertEqual(items[1]["app"], "Slack")
        self.assertEqual(items[1]["status"], "removed")

    @patch("context.notifications.subprocess.run")
    def test_read_recent_notifications_reports_idle_when_no_items_found(self, mock_run):
        mock_run.return_value = SimpleNamespace(returncode=0, stdout="", stderr="")

        payload = notifications.read_recent_notifications(force_refresh=True)

        self.assertEqual(payload["status"], "idle")
        self.assertEqual(payload["items"], [])


if __name__ == "__main__":
    unittest.main()
