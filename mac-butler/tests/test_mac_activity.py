import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from context import mac_activity


class MacActivityTests(unittest.TestCase):
    def test_save_and_load_state(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            state_file = Path(temp_dir) / "mac_state.json"
            sample = {"frontmost_app": "Cursor", "cursor_workspace": "~/Burry/mac-butler"}
            with patch.object(mac_activity, "STATE_FILE", state_file):
                mac_activity.save_state(sample)
                self.assertEqual(json.loads(state_file.read_text(encoding="utf-8")), sample)
                self.assertEqual(mac_activity.load_state(), sample)

    def test_context_block_includes_relevant_fields(self):
        sample = {
            "frontmost_app": "Cursor",
            "open_windows": ["mac-butler"],
            "open_apps": ["Cursor", "Spotify", "Finder"],
            "cursor_workspace": "/Users/adityatiwari/Burry/mac-butler",
            "spotify_track": "Mockingbird by Eminem",
            "browser_url": "https://github.com/Aadi262/mac-butler",
            "notifications": {
                "items": [
                    {
                        "app": "Slack",
                        "status": "active",
                        "summary": "PR review requested",
                    }
                ]
            },
        }
        with patch.object(mac_activity, "load_state", return_value=sample):
            block = mac_activity.get_state_for_context()
        self.assertIn("[MAC ACTIVITY]", block)
        self.assertIn("Last active app: Cursor", block)
        self.assertIn("Last workspace: /Users/adityatiwari/Burry/mac-butler", block)
        self.assertIn("Playing: Mockingbird by Eminem", block)
        self.assertIn("Browser: GitHub", block)
        self.assertIn("Notifications: Slack (active): PR review requested", block)

    def test_focus_project_name_maps_nested_workspace_to_tracked_project(self):
        state = {
            "cursor_workspace": "/Users/adityatiwari/Burry/mac-butler/projects/frontend",
            "browser_url": "",
        }
        tracked = [
            {"name": "mac-butler", "path": "/Users/adityatiwari/Burry/mac-butler"},
            {"name": "Adpilot", "path": "/Users/adityatiwari/Burry/adpilot"},
        ]

        with patch.object(mac_activity, "_tracked_projects", return_value=tracked):
            focus_project = mac_activity._focus_project_name(state)

        self.assertEqual(focus_project, "mac-butler")

    def test_focus_project_name_maps_github_repo_url_to_tracked_project(self):
        state = {
            "cursor_workspace": "",
            "browser_url": "https://github.com/Aadi262/Burry/issues/12",
        }
        tracked = [
            {"name": "Burry", "repo": "Aadi262/Burry"},
            {"name": "Other", "repo": "Aadi262/Other"},
        ]

        with patch.object(mac_activity, "_tracked_projects", return_value=tracked):
            focus_project = mac_activity._focus_project_name(state)

        self.assertEqual(focus_project, "Burry")


if __name__ == "__main__":
    unittest.main()
