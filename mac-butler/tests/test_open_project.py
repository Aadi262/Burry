import tempfile
import unittest
from unittest.mock import patch

from projects.open_project import open_project, open_project_by_path


class OpenProjectTests(unittest.TestCase):
    def test_open_project_by_path_uses_first_working_launcher(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch(
                "projects.open_project._editor_launchers",
                return_value=[
                    ("antigravity", lambda _path: True),
                    ("cursor", lambda _path: True),
                ],
            ):
                result = open_project_by_path(tmpdir)

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["editor_used"], "antigravity")
        self.assertEqual(result["path"], tmpdir)

    def test_open_project_by_path_returns_error_for_missing_path(self):
        result = open_project_by_path("/tmp/this-path-should-not-exist-butler")

        self.assertEqual(result["status"], "error")
        self.assertIsNone(result["editor_used"])

    @patch("projects.open_project.ensure_project_blurb")
    @patch("projects.open_project.set_last_opened")
    @patch("projects.open_project.open_project_by_path")
    @patch("projects.open_project.get_project")
    def test_open_project_hydrates_blurb_on_success(
        self,
        mock_get_project,
        mock_open_by_path,
        _mock_set_last_opened,
        mock_ensure_blurb,
    ):
        mock_get_project.return_value = {
            "name": "Demo",
            "path": "/tmp/demo",
            "blurb": "",
        }
        mock_open_by_path.return_value = {
            "status": "ok",
            "editor_used": "cursor",
            "project_name": "Demo",
            "path": "/tmp/demo",
        }

        result = open_project("demo")

        self.assertEqual(result["status"], "ok")
        mock_get_project.assert_called_once_with("demo", hydrate_blurb=True)
        mock_ensure_blurb.assert_called_once_with("Demo")


if __name__ == "__main__":
    unittest.main()
