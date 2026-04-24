import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from projects.project_store import (
    _explicit_progress_candidate,
    _table_progress_candidate,
    ensure_project_blurb,
    load_projects,
)


class ProjectStoreTests(unittest.TestCase):
    def test_mac_butler_registry_entry_uses_live_phase_files(self):
        path = Path(__file__).resolve().parent.parent / "projects" / "projects.json"
        payload = json.loads(path.read_text(encoding="utf-8"))

        project = next(item for item in payload if item.get("name") == "mac-butler")
        status_files = set(project.get("status_files") or [])
        next_tasks = " ".join(project.get("next_tasks") or [])

        self.assertIn(".CODEX/Codex.md", status_files)
        self.assertIn("docs/phases/PHASE.md", status_files)
        self.assertIn("docs/phases/PHASE_PROGRESS.md", status_files)
        self.assertEqual(project.get("live_url"), "http://127.0.0.1:7532")
        self.assertNotIn("docs/phases/2026-04-08-architecture-remediation-roadmap.md", status_files)
        self.assertNotIn("docs/phases/2026-04-08-architecture-remediation-status.md", status_files)
        self.assertNotIn("BUTLER_STATUS.md", status_files)
        self.assertNotIn("2026-04-08-architecture-remediation-roadmap.md", next_tasks)

    def test_mac_butler_registry_entry_tracks_live_phase3c_state(self):
        path = Path(__file__).resolve().parent.parent / "projects" / "projects.json"
        payload = json.loads(path.read_text(encoding="utf-8"))

        project = next(item for item in payload if item.get("name") == "mac-butler")
        blockers = " ".join(project.get("blockers") or [])
        next_tasks = " ".join(project.get("next_tasks") or [])
        blurb = str(project.get("blurb", "") or "")

        self.assertGreaterEqual(int(project.get("completion", 0) or 0), 80)
        self.assertNotIn("Phase 3 feature completion has not started", blockers)
        self.assertIn("messaging", blockers.lower())
        self.assertTrue("run-tests" in next_tasks.lower() or "attachments" in next_tasks.lower())
        self.assertIn("Phase 3C", blurb)

    def test_explicit_progress_candidate_reads_total_percentage(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "PROGRESS.md"
            path.write_text("**Total: 2 of 6 phases complete (33%)**", encoding="utf-8")

            candidate = _explicit_progress_candidate(path, path.read_text(encoding="utf-8"))

        self.assertIsNotNone(candidate)
        self.assertEqual(candidate["score"], 33)

    def test_table_progress_candidate_aggregates_multiple_status_tables(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "FEATURE_STATUS.md"
            path.write_text(
                """
| Feature | Status | Notes |
|---------|--------|-------|
| A | LIVE | ok |
| B | LIVE | ok |

| Feature | Status | Notes |
|---------|--------|-------|
| C | PARTIAL | ok |
| D | MISSING | ok |
""".strip(),
                encoding="utf-8",
            )

            candidate = _table_progress_candidate(path, path.read_text(encoding="utf-8"))

        self.assertIsNotNone(candidate)
        self.assertEqual(candidate["score"], 65)

    def test_load_projects_derives_completion_from_local_status_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "PROGRESS.md").write_text(
                "# Progress\n\n**Total: 2 of 6 phases complete (33%)**\n",
                encoding="utf-8",
            )

            project = {
                "name": "Demo",
                "aliases": ["demo"],
                "path": str(root),
                "status": "active",
                "completion": 99,
                "blockers": [],
                "status_files": ["PROGRESS.md"],
                "next_tasks": [],
            }

            with patch("projects.project_store._load_raw", return_value=[project]):
                projects = load_projects()

        self.assertEqual(len(projects), 1)
        self.assertEqual(projects[0]["completion"], 33)
        self.assertIn("PROGRESS.md", projects[0]["completion_basis"])

    def test_load_projects_derives_next_tasks_and_blockers(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "STATUS.md").write_text(
                """
## Known Gaps
- Voice follow-up is still weaker than the main TTS path.

## What Should Happen Next
1. Install Piper for local neural TTS.
2. Tighten workspace detection.
""".strip(),
                encoding="utf-8",
            )

            project = {
                "name": "Demo",
                "aliases": ["demo"],
                "path": str(root),
                "status": "active",
                "completion": 99,
                "blockers": ["manual blocker"],
                "status_files": ["STATUS.md"],
                "next_tasks": ["manual task"],
            }

            with patch("projects.project_store._load_raw", return_value=[project]):
                projects = load_projects()

        self.assertEqual(projects[0]["next_tasks_basis"], "STATUS.md")
        self.assertIn("Install Piper for local neural TTS", projects[0]["next_tasks"][0])
        self.assertIn("Voice follow-up is still weaker", projects[0]["blockers"][0])
        self.assertIn("manual task", projects[0]["next_tasks"])
        self.assertIn("manual blocker", projects[0]["blockers"])

    def test_load_projects_derives_health_and_memory_signals(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            project = {
                "name": "Demo",
                "aliases": ["demo"],
                "path": str(root),
                "status": "active",
                "completion": 40,
                "blockers": [],
                "status_files": [],
                "next_tasks": [],
                "live": False,
                "live_url": "http://localhost:3333",
                "last_error": None,
            }

            with patch("projects.project_store._load_raw", return_value=[project]), patch(
                "projects.project_store._local_git_last_commit",
                return_value="2026-04-05T15:00:00Z",
            ), patch(
                "projects.project_store._local_git_branch",
                return_value="main",
            ), patch(
                "projects.project_store._local_git_dirty",
                return_value=False,
            ), patch(
                "projects.project_store._local_live_status",
                return_value={"checked": True, "reachable": True, "status_code": 200},
            ), patch(
                "projects.project_store._project_memory_state",
                return_value={
                    "last_test_status": "ok",
                    "last_test_command": "venv/bin/python -m unittest",
                    "last_verified_at": "2026-04-05T15:01:00",
                    "last_error": "",
                },
            ):
                projects = load_projects()

        self.assertEqual(projects[0]["health_status"], "healthy")
        self.assertEqual(projects[0]["health_signals_ok"], 4)
        self.assertEqual(projects[0]["git_branch"], "main")
        self.assertEqual(projects[0]["last_test_status"], "ok")
        self.assertTrue(projects[0]["live"])

    def test_ensure_project_blurb_persists_generated_summary(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "projects.json"
            path.write_text(
                """
[
  {
    "name": "Demo",
    "aliases": ["demo"],
    "path": "/tmp/demo",
    "description": "Demo project",
    "blurb": "",
    "status": "active",
    "completion": 50,
    "blockers": ["Auth still needs a pass"],
    "next_tasks": ["Ship the dashboard card"],
    "status_files": []
  }
]
""".strip(),
                encoding="utf-8",
            )

            with patch("projects.project_store.PROJECTS_PATH", path), patch(
                "projects.project_store._generate_project_blurb",
                return_value="Demo project is active. Next up is shipping the dashboard card.",
            ):
                project = ensure_project_blurb("Demo")
                payload = path.read_text(encoding="utf-8")

        self.assertIsNotNone(project)
        self.assertEqual(project["blurb"], "Demo project is active. Next up is shipping the dashboard card.")
        self.assertIn('"blurb": "Demo project is active. Next up is shipping the dashboard card."', payload)


if __name__ == "__main__":
    unittest.main()
