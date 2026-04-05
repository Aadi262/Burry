import unittest
from unittest.mock import patch

from mcp.client import _fit_arguments, get_server_status


class MCPClientTests(unittest.TestCase):
    def test_fit_arguments_maps_common_aliases(self):
        schema = {"properties": {"q": {}, "limit": {}}}
        fitted = _fit_arguments(schema, {"query": "ai news", "count": 5})
        self.assertEqual(fitted, {"q": "ai news", "limit": 5})

    @patch("mcp.client.get_mcp_secret", return_value={"enabled": True, "env": {"BRAVE_API_KEY": "test-key"}})
    def test_server_status_uses_local_secret_override(self, _mock_secret):
        status = get_server_status("brave")
        self.assertTrue(status["enabled"])
        self.assertTrue(status["configured"])
        self.assertTrue(status["ready"])


if __name__ == "__main__":
    unittest.main()
