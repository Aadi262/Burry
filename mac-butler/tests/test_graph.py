import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from memory import graph


class GraphTests(unittest.TestCase):
    def test_read_graph_defaults_when_missing(self):
        with tempfile.TemporaryDirectory() as tempdir:
            graph_path = Path(tempdir) / "graph.json"
            with patch.object(graph, "GRAPH_PATH", graph_path):
                data = graph.read_graph()

        self.assertEqual(data["edges"], [])

    def test_add_edge_persists_and_dedupes(self):
        with tempfile.TemporaryDirectory() as tempdir:
            graph_path = Path(tempdir) / "graph.json"
            with patch.object(graph, "GRAPH_PATH", graph_path):
                graph.add_edge("Reachout", "LinkedPilot", "blocked_by", "Canonical app root unresolved.")
                graph.add_edge("Reachout", "LinkedPilot", "blocked_by", "Canonical app root still unresolved.")
                data = graph.read_graph()

        self.assertEqual(len(data["edges"]), 1)
        self.assertEqual(data["edges"][0]["type"], "blocked_by")
        self.assertEqual(data["edges"][0]["note"], "Canonical app root still unresolved.")

    @patch("memory.graph._recent_session_window", return_value=[{"timestamp": "2026-04-06T12:00:00", "context": "Reachout depends on LinkedPilot", "speech": ""}])
    @patch(
        "memory.graph._project_catalog",
        return_value=[
            {"name": "Reachout", "blockers": ["Waiting on LinkedPilot auth fix"]},
            {"name": "LinkedPilot", "blockers": []},
        ],
    )
    def test_observe_project_relationships_writes_auto_edges(self, _mock_projects, _mock_sessions):
        with tempfile.TemporaryDirectory() as tempdir:
            graph_path = Path(tempdir) / "graph.json"
            with patch.object(graph, "GRAPH_PATH", graph_path):
                data = graph.observe_project_relationships(
                    text="Reachout and LinkedPilot are both in scope",
                    speech="",
                    actions=[],
                    touched_projects=["Reachout"],
                )

        edge_types = {(edge["from"], edge["to"], edge["type"]) for edge in data["edges"]}
        self.assertIn(("Reachout", "LinkedPilot", "shares_resource"), edge_types)
        self.assertIn(("Reachout", "LinkedPilot", "blocked_by"), edge_types)


if __name__ == "__main__":
    unittest.main()
