import unittest
from unittest.mock import patch

from projects.dashboard import generate_dashboard


class DashboardTests(unittest.TestCase):
    @patch("projects.dashboard.get_github_context", return_value="[GITHUB]\nAdpilot: 2026-03-17/0i")
    @patch(
        "projects.dashboard.load_projects",
        return_value=[
            {
                "name": "mac-butler",
                "status": "active",
                "completion": 71,
                "completion_basis": "BUTLER_STATUS.md",
                "status_files_found": 2,
                "status_files_total": 3,
                "deploy_target": "Local Mac + Ollama",
                "live": True,
                "last_commit": "2026-04-05T10:00:00Z",
                "open_issues": 0,
                "health_status": "healthy",
                "health_signals_ok": 4,
                "health_signals_total": 4,
                "last_test_status": "ok",
                "git_branch": "main",
                "git_dirty": False,
                "last_verified_at": "2026-04-05T10:10:00",
                "blockers": ["Need better clap trigger filtering"],
                "next_tasks": ["Ship the dashboard checks"],
            }
        ],
    )
    def test_generate_dashboard_renders_health_and_verification(
        self,
        _mock_load,
        _mock_github,
    ):
        html = generate_dashboard()

        self.assertIn("Health:", html)
        self.assertIn("Verify:", html)
        self.assertIn("% estimated", html)
        self.assertIn("Project Command Center", html)


if __name__ == "__main__":
    unittest.main()
