import tempfile
import unittest
from unittest.mock import patch

from projects.open_project import open_project_by_path


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


if __name__ == "__main__":
    unittest.main()
