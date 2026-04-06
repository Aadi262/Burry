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


if __name__ == "__main__":
    unittest.main()
