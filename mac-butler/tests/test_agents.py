import unittest
from unittest.mock import MagicMock, patch

from agents.runner import (
    _call_model,
    _fetch_github_trending_items,
    _github_agent,
    _news_agent,
    _pick_model,
    _search_agent,
    run_agent,
)


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

    @patch("agents.runner._call_model", return_value="- Story one\n- Story two\n- Story three")
    @patch("agents.runner._fetch_json")
    def test_hackernews_agent_structure(self, mock_fetch_json, _mock_call_model):
        mock_fetch_json.side_effect = [
            [101, 102, 103],
            {"id": 101, "title": "HN One", "url": "https://example.com/1", "score": 180, "descendants": 45, "by": "a"},
            {"id": 102, "title": "HN Two", "url": "https://example.com/2", "score": 160, "descendants": 21, "by": "b"},
            {"id": 103, "title": "HN Three", "url": "https://example.com/3", "score": 140, "descendants": 9, "by": "c"},
        ]

        result = run_agent("hackernews", {"limit": 3})

        self.assertEqual(result["status"], "ok")
        self.assertIsInstance(result["result"], str)
        self.assertIsInstance(result["data"], dict)
        self.assertIsInstance(result["data"]["items"], list)
        self.assertEqual(len(result["data"]["items"]), 3)

    @patch("agents.runner._call_model", return_value="")
    @patch("agents.runner._fetch_headlines", return_value="Headline 1\nHeadline 2\nHeadline 3")
    def test_news_agent_falls_back_when_model_returns_empty(self, _mock_fetch, _mock_call):
        result = _news_agent({"topic": "AI", "hours": 24}, "test-model")
        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["result"])
        self.assertIn("Headline 1", result["result"])

    @patch("agents.runner._call_model", return_value="- LocalLLaMA is active\n- OSS agent tooling is rising")
    @patch("agents.runner._fetch_json")
    def test_reddit_agent_structure(self, mock_fetch_json, _mock_call_model):
        mock_fetch_json.return_value = {
            "data": {
                "children": [
                    {
                        "data": {
                            "title": "LocalLLaMA discussion",
                            "score": 420,
                            "url": "https://reddit.com/r/LocalLLaMA/1",
                            "num_comments": 120,
                            "permalink": "/r/LocalLLaMA/comments/1",
                        }
                    }
                ]
            }
        }

        result = run_agent("reddit", {"subreddits": ["LocalLLaMA"], "limit": 3})

        self.assertEqual(result["status"], "ok")
        self.assertIsInstance(result["data"]["items"], list)
        self.assertEqual(result["data"]["items"][0]["subreddit"], "LocalLLaMA")

    @patch("agents.runner._fetch_json", return_value={"data": {"children": []}})
    def test_reddit_agent_handles_empty_subreddit_gracefully(self, _mock_fetch_json):
        result = run_agent("reddit", {"subreddits": ["EmptySub"], "limit": 3})
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["data"]["items"], [])

    @patch("agents.runner._call_model", return_value="- Agents are rising\n- Open-source LLM tooling is moving fast\n- Infra is consolidating")
    @patch("agents.runner._collect_search_items")
    def test_market_agent_combines_sources(self, mock_collect_search_items, _mock_call_model):
        mock_collect_search_items.side_effect = [
            (
                [{"title": "AI agents story", "url": "https://example.com/a", "content": "agents are shipping", "query": "AI agents"}],
                ["searxng"],
            ),
            (
                [{"title": "LLM story", "url": "https://example.com/b", "content": "llm usage is growing", "query": "LLMs"}],
                ["searxng"],
            ),
            (
                [{"title": "OSS story", "url": "https://example.com/c", "content": "oss momentum is strong", "query": "open source"}],
                ["searxng"],
            ),
        ]

        result = run_agent("market", {"topics": ["AI agents", "LLMs", "open source"]})

        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["result"])
        self.assertGreaterEqual(len(result["data"]["items"]), 3)

    @patch("agents.runner._call_model", return_value="- Local models are hot\n- OSS infra is moving\n- Community buzz is rising")
    @patch("agents.runner._fetch_github_trending_items")
    @patch("agents.runner._fetch_hackernews_items")
    @patch("agents.runner._fetch_reddit_items")
    @patch("agents.runner._collect_search_items", return_value=([], []))
    def test_market_agent_uses_public_fallback_when_search_is_down(
        self,
        _mock_collect_search_items,
        mock_reddit_items,
        mock_hn_items,
        mock_github_items,
        _mock_call_model,
    ):
        mock_reddit_items.return_value = [
            {"subreddit": "LocalLLaMA", "title": "Gemma 4 is strong", "url": "https://reddit.com/1", "score": 262, "comments": 96}
        ]
        mock_hn_items.return_value = [
            {"title": "LLM Wiki launches", "url": "https://example.com/hn", "score": 180, "comments": 45}
        ]
        mock_github_items.return_value = [
            {"title": "microsoft/agent-framework", "url": "https://github.com/microsoft/agent-framework", "description": "Agent tooling", "score": 1200}
        ]

        result = run_agent("market", {"topics": ["AI agents", "LLMs", "open source"]})

        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["result"])
        self.assertGreaterEqual(len(result["data"]["items"]), 3)
        self.assertIn("reddit", result["data"]["sources"])

    @patch("agents.runner.requests.get")
    def test_github_trending_agent_parses_github_html_when_api_unavailable(self, mock_get):
        html_response = MagicMock()
        html_response.raise_for_status.return_value = None
        html_response.text = """
        <article class="Box-row">
          <h2 class="h3 lh-condensed">
            <a href="/Blaizzy/mlx-vlm">Blaizzy / mlx-vlm</a>
          </h2>
          <p class="col-9 color-fg-muted my-1 pr-4">MLX vision language models on Mac.</p>
          <a href="/Blaizzy/mlx-vlm/stargazers">3,758</a>
        </article>
        <article class="Box-row">
          <h2 class="h3 lh-condensed">
            <a href="/onyx-dot-app/onyx">onyx-dot-app / onyx</a>
          </h2>
          <p class="col-9 color-fg-muted my-1 pr-4">Open-source enterprise search and assistants.</p>
          <a href="/onyx-dot-app/onyx/stargazers">12,400</a>
        </article>
        """

        def fake_get(url, *args, **kwargs):
            if "github.com/trending" in url:
                return html_response
            raise RuntimeError("gitter down")

        mock_get.side_effect = fake_get

        items = _fetch_github_trending_items(language="python", since="daily", limit=5)

        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["title"], "Blaizzy/mlx-vlm")

    def test_all_new_agents_have_fallback(self):
        with patch("agents.runner._collect_search_items", return_value=([], [])):
            market = run_agent("market", {"topics": ["AI agents"]})
        with patch("agents.runner._fetch_json", side_effect=RuntimeError("network down")):
            hn = run_agent("hackernews", {"limit": 5})
        with patch("agents.runner._fetch_json", side_effect=RuntimeError("network down")):
            reddit = run_agent("reddit", {"subreddits": ["LocalLLaMA"], "limit": 3})
        with patch("agents.runner.requests.get", side_effect=RuntimeError("network down")), patch(
            "agents.runner._jina_fetch", return_value=""
        ):
            trending = run_agent("github_trending", {"language": "python", "since": "daily"})

        for result in (market, hn, reddit, trending):
            self.assertEqual(result["status"], "ok")
            self.assertIsInstance(result["result"], str)


if __name__ == "__main__":
    unittest.main()
