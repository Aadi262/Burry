import unittest
from unittest.mock import patch

from daemons import ambient


class AmbientDaemonTests(unittest.TestCase):
    @patch("daemons.ambient._bitnet_available", return_value=False)
    @patch("daemons.ambient._call", return_value="- auth recall still blocks startup\n- email-infra depends on VPS stability\n- Adpilot shares staging resources")
    @patch("daemons.ambient.load_projects")
    @patch("daemons.ambient.load_recent_sessions")
    def test_generate_ambient_context_uses_model_output(
        self,
        mock_sessions,
        mock_projects,
        mock_call,
        _mock_bitnet,
    ):
        mock_sessions.return_value = [{"text": "what did we decide about auth", "speech": "Still checking memory"}]
        mock_projects.return_value = [{"name": "mac-butler", "status": "active", "next_tasks": ["Fix auth recall"], "blockers": []}]

        bullets = ambient.generate_ambient_context()

        self.assertEqual(
            bullets,
            [
                "auth recall still blocks startup",
                "email-infra depends on VPS stability",
                "Adpilot shares staging resources",
            ],
        )
        self.assertEqual(mock_call.call_args.args[1], "gemma4:e4b")

    @patch("daemons.ambient.note_ambient_context")
    @patch("daemons.ambient.generate_ambient_context", return_value=["one", "two", "three"])
    def test_ambient_tick_persists_generated_bullets(self, mock_generate, mock_note):
        bullets = ambient.ambient_tick()

        self.assertEqual(bullets, ["one", "two", "three"])
        mock_generate.assert_called_once_with()
        mock_note.assert_called_once_with(["one", "two", "three"])


if __name__ == "__main__":
    unittest.main()
