import unittest
from unittest.mock import MagicMock, patch

from agents.runner import _call_model, _github_agent, _pick_model, _search_agent


class AgentTests(unittest.TestCase):
    @patch("agents.runner._prepare_model_request")
    @patch("agents.runner.requests.post")
    def test_call_model_uses_short_keep_alive_and_small_context(
        self,
        mock_post,
        _mock_prepare,
    ):
        response = MagicMock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"response": "ok"}
        mock_post.return_value = response

        result = _call_model("prompt", "test-model", max_tokens=80)

        self.assertEqual(result, "ok")
        payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(payload["keep_alive"], "2m")
        self.assertEqual(payload["options"]["num_ctx"], 1024)

    @patch("agents.runner._call_model", return_value="Qwen2.5 is Alibaba's multilingual model family.")
    @patch("agents.runner._fetch_search_text", return_value={"backend": "stub", "tool": "fake", "text": "Qwen2.5 is a model family."})
    def test_search_agent_uses_fetched_material(self, _mock_fetch, _mock_call):
        result = _search_agent({"query": "what is Qwen2.5"}, "test-model")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["data"]["backend"], "stub")

    @patch("agents.runner.list_server_tools", return_value=[{"name": "list_pull_requests"}, {"name": "search_issues"}])
    def test_github_agent_lists_tools_when_no_tool_requested(self, _mock_tools):
        result = _github_agent({}, "test-model")
        self.assertEqual(result["status"], "ok")
        self.assertIn("list_pull_requests", result["result"])

    @patch("agents.runner._get_installed_models", return_value={"qwen2.5:14b"})
    @patch(
        "brain.ollama_client._get_backend_model_map",
        side_effect=lambda backend, force_refresh=False: (
            {"qwen2.5:14b": "qwen2.5:14b"} if backend == "local" else {}
        ),
    )
    def test_pick_model_uses_agent_chain_fallback(self, _mock_available, _mock_installed):
        self.assertEqual(_pick_model("news"), "qwen2.5:14b")


if __name__ == "__main__":
    unittest.main()
