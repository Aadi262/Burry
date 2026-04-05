#!/usr/bin/env python3

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from memory import layered, store


class MemorySemanticTests(unittest.TestCase):
    def test_search_sessions_uses_semantic_similarity_when_embeddings_exist(self):
        def fake_embed(text: str) -> list[float]:
            lowered = text.lower()
            if "ship" in lowered or "win" in lowered:
                return [1.0, 0.0]
            if "auth" in lowered:
                return [0.0, 1.0]
            return [0.2, 0.2]

        with tempfile.TemporaryDirectory() as tempdir:
            temp_sessions = Path(tempdir) / "sessions"
            temp_sessions.mkdir(parents=True, exist_ok=True)
            with patch.object(store, "SESSION_DIR", temp_sessions), patch.object(layered, "SESSIONS_DIR", temp_sessions):
                with patch("memory.store._embed_text", side_effect=fake_embed):
                    layered.save_session(
                        {
                            "timestamp": "2026-04-06T12:00:00",
                            "speech": "Shipped the new auth flow and closed the blocker.",
                            "context_preview": "worked on auth",
                            "actions": [],
                        }
                    )
                    layered.save_session(
                        {
                            "timestamp": "2026-04-06T13:00:00",
                            "speech": "Looked into the VPS issue.",
                            "context_preview": "server debugging",
                            "actions": [],
                        }
                    )

                    results = layered.search_sessions("show me recent wins", max_results=2)

        self.assertTrue(results)
        self.assertIn("Shipped the new auth flow", results[0]["speech"])


if __name__ == "__main__":
    unittest.main()
