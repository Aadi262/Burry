import unittest
from unittest.mock import MagicMock, patch

from agents.runner import (
    _call_model,
    _collect_news_items,
    _collect_search_items,
    _duckduckgo_instant_fact,
    _fetch_agent,
    _fetch_search_text,
    _fetch_github_trending_items,
    _google_news_rss_search,
    _github_agent,
    _news_agent,
    _pick_model,
    _project_status_agent,
    _quick_fact_lookup,
    _search_agent,
    _vps_agent,
    _weather_agent,
    _wikipedia_fact_summary,
    run_agent,
    run_agent_async,
)


class AgentTests(unittest.TestCase):
    @patch("agents.runner._call_model", return_value="docker is healthy")
    @patch("agents.runner.subprocess.run")
    @patch("agents.runner.get_vps_secret", return_value={"username": "root"})
    @patch("agents.runner.VPS_HOSTS", [{"host": "194.163.146.149"}])
    def test_vps_agent_uses_default_configured_host_when_missing(
        self,
        _mock_secret,
        mock_run,
        _mock_call_model,
    ):
        mock_run.side_effect = [MagicMock(returncode=0, stdout="ok", stderr="") for _ in range(4)]

        result = _vps_agent({"action": "status"}, "test-model")

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["data"]["host"], "root@194.163.146.149")
        first_call = mock_run.call_args_list[0].args[0]
        self.assertEqual(first_call[:4], ["ssh", "-o", "ConnectTimeout=8", "root@194.163.146.149"])

    @patch("agents.runner.subprocess.run", return_value=MagicMock(returncode=255, stdout="", stderr=""))
    @patch("agents.runner.get_vps_secret", return_value={})
    def test_vps_agent_returns_truthful_connection_error_when_all_checks_fail(self, _mock_secret, _mock_run):
        result = _vps_agent({"host": "194.163.146.149"}, "test-model")

        self.assertEqual(result["status"], "error")
        self.assertIn("Could not connect to VPS", result["result"])
        self.assertIn("194.163.146.149", result["data"]["host"])

    @patch("agents.runner.notify")
    @patch("agents.runner.note_agent_result")
    @patch("agents.runner.run_agent")
    def test_run_agent_async_reports_result_to_runtime(self, mock_run_agent, mock_note_agent, mock_notify):
        mock_run_agent.return_value = {"status": "ok", "result": "All good", "data": {}}
        seen = []

        thread = run_agent_async("news", {"topic": "AI"}, callback=lambda result: seen.append(result["result"]))
        thread.join(timeout=1.0)

        self.assertFalse(thread.is_alive())
        mock_note_agent.assert_called_once_with("news", "ok", "All good")
        mock_notify.assert_called_once()
        self.assertEqual(seen, ["All good"])

    @patch("agents.runner._prepare_model_request")
    @patch("agents.runner._call", return_value="ok")
    def test_call_model_uses_central_provider_aware_caller(
        self,
        mock_call,
        _mock_prepare,
    ):
        result = _call_model("prompt", "test-model", max_tokens=80)

        self.assertEqual(result, "ok")
        mock_call.assert_called_once_with(
            "prompt",
            "test-model",
            temperature=0.3,
            max_tokens=80,
            timeout_hint="agent",
        )

    @patch("agents.runner._quick_fact_lookup", return_value=None)
    @patch("agents.runner._call_model", return_value="Qwen2.5 is Alibaba's multilingual model family.")
    @patch("agents.runner._fetch_search_text", return_value={"backend": "stub", "tool": "fake", "text": "Qwen2.5 is a model family."})
    def test_search_agent_uses_fetched_material(self, _mock_fetch, _mock_call, _mock_fact):
        result = _search_agent({"query": "what is Qwen2.5"}, "test-model")
        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["result"])

    @patch("agents.runner._collect_search_items")
    @patch(
        "agents.runner._quick_fact_lookup",
        return_value={
            "answer": "Qwen2.5 is Alibaba's open-weight model family.",
            "source": "wikipedia",
            "url": "https://en.wikipedia.org/wiki/Qwen",
        },
    )
    def test_search_agent_uses_direct_fact_lookup_before_generic_search(self, _mock_fact, mock_collect):
        result = _search_agent({"query": "what is Qwen2.5"}, "test-model")

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["data"]["tool"], "quick_fact")
        self.assertIn("wikipedia", result["data"]["sources"])
        mock_collect.assert_not_called()

    @patch("agents.runner._fetch_json")
    def test_quick_fact_lookup_resolves_pm_abbreviation_from_wikipedia_incumbent(self, mock_fetch_json):
        mock_fetch_json.return_value = {
            "query": {
                "pages": {
                    "123": {
                        "revisions": [
                            {
                                "slots": {
                                    "main": {
                                        "*": "{{Infobox official post\n| incumbent = [[Narendra Modi]]\n}}"
                                    }
                                }
                            }
                        ]
                    }
                }
            }
        }

        result = _quick_fact_lookup("who is PM of India")

        self.assertEqual(result["answer"], "Narendra Modi is the Prime Minister of India.")
        self.assertEqual(result["tool"], "current_office_holder")
        self.assertEqual(mock_fetch_json.call_args.kwargs["params"]["titles"], "Prime Minister of India")

    @patch("agents.runner._quick_fact_lookup", return_value=None)
    @patch("agents.runner._call_model", return_value="")
    @patch("agents.runner._collect_search_items")
    def test_search_agent_falls_back_to_generic_search_when_direct_fact_lookup_is_empty(self, mock_collect, _mock_call, _mock_fact):
        mock_collect.return_value = (
            [
                {
                    "title": "Claude launches a new product",
                    "url": "https://example.com/claude",
                    "content": "Anthropic introduced a new Claude product for teams.",
                }
            ],
            ["exa"],
        )

        result = _search_agent({"query": "what is the new product from claude"}, "test-model")

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["data"]["tool"], "search_lookup")

    @patch("agents.runner.list_server_tools", return_value=[{"name": "list_pull_requests"}, {"name": "search_issues"}])
    def test_github_agent_lists_tools_when_no_tool_requested(self, _mock_tools):
        result = _github_agent({}, "test-model")
        self.assertEqual(result["status"], "ok")
        self.assertIn("list_pull_requests", result["result"])

    @patch(
        "projects.github_sync.fetch_repo_status",
        return_value={
            "repo": "Aadi262/Adpilot",
            "full_name": "Aadi262/Adpilot",
            "default_branch": "main",
            "pushed_at": "2026-04-16T12:00:00Z",
            "open_issues": 2,
            "open_pull_requests": 1,
            "latest_commit": {"message": "Fix deploy health check", "date": "2026-04-16T11:45:00Z"},
            "workflow": {"name": "CI", "status": "completed", "conclusion": "success"},
            "issues": [{"number": 14, "title": "Fix auth loop"}],
            "pull_requests": [{"number": 22, "title": "Ship deploy guardrails"}],
        },
    )
    @patch("projects.project_store.load_projects", return_value=[{"name": "Adpilot", "aliases": ["adpilot"], "repo": "Aadi262/Adpilot"}])
    @patch("agents.runner.list_server_tools")
    @patch("agents.runner._call_model", return_value="Adpilot has 2 open issues and 1 open pull request. Latest push was 2026-04-16.")
    def test_github_agent_uses_tracked_project_repo_status_before_mcp_tools(
        self,
        _mock_call_model,
        mock_list_tools,
        _mock_load_projects,
        _mock_fetch_status,
    ):
        result = _github_agent({"query": "any issues on adpilot"}, "test-model")

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["data"]["tool"], "repo_status")
        self.assertEqual(result["data"]["repo"], "Aadi262/Adpilot")
        self.assertIn("open issues", result["result"])
        mock_list_tools.assert_not_called()

    def test_github_agent_asks_for_repo_when_query_has_no_repo_hint(self):
        result = _github_agent({"query": "check github status"}, "test-model")

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["result"], "Which GitHub repo or tracked project should I check?")

    @patch(
        "projects.github_sync.fetch_repo_status",
        return_value={
            "repo": "Aadi262/Adpilot",
            "full_name": "Aadi262/Adpilot",
            "open_issues": 2,
            "open_pull_requests": 1,
            "pushed_at": "2026-04-16T12:00:00Z",
            "latest_commit": {"message": "Fix deploy health check"},
        },
    )
    @patch(
        "projects.project_store.get_project",
        return_value={
            "name": "Adpilot",
            "repo": "Aadi262/Adpilot",
            "status": "active",
            "completion": 76,
            "health_status": "degraded",
            "blockers": ["Feature status needs to be reconciled with the actual running stack."],
            "next_tasks": ["Verify the live route set against FEATURE_STATUS and PLAN.md."],
            "blurb": "Adpilot is the AI-powered ad and SEO command center. Next up is verifying the live route set.",
            "git_branch": "main",
            "git_dirty": False,
            "live": False,
        },
    )
    @patch(
        "agents.runner._call_model",
        return_value=(
            "Adpilot is active and about 76% complete. "
            "Main blocker is reconciling the feature status with the real running stack. "
            "GitHub shows 2 open issues and 1 open pull request."
        ),
    )
    def test_project_status_agent_combines_project_registry_and_repo_status(
        self,
        _mock_call_model,
        _mock_get_project,
        _mock_fetch_status,
    ):
        result = run_agent("project_status", {"query": "how is adpilot doing"})

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["data"]["tool"], "project_status")
        self.assertEqual(result["data"]["project"], "Adpilot")
        self.assertEqual(result["data"]["repo"], "Aadi262/Adpilot")
        self.assertIn("76% complete", result["result"])
        self.assertIn("open issues", result["result"])

    @patch(
        "projects.github_sync.fetch_repo_status",
        return_value={
            "repo": "Aadi262/Adpilot",
            "full_name": "Aadi262/Adpilot",
            "open_issues": 2,
            "open_pull_requests": 1,
            "pushed_at": "2026-04-16T12:00:00Z",
            "latest_commit": {"message": "Fix deploy health check"},
        },
    )
    @patch(
        "projects.project_store.get_project",
        return_value={
            "name": "Adpilot",
            "repo": "Aadi262/Adpilot",
            "status": "active",
            "completion": 76,
            "health_status": "degraded",
            "blockers": ["Feature status needs to be reconciled with the actual running stack."],
            "next_tasks": ["Verify the live route set against FEATURE_STATUS and PLAN.md."],
            "blurb": "",
            "git_branch": "main",
            "git_dirty": False,
            "live": False,
        },
    )
    @patch("agents.runner._call_model", return_value="")
    def test_project_status_agent_falls_back_to_truthful_summary_when_model_is_empty(
        self,
        _mock_call_model,
        _mock_get_project,
        _mock_fetch_status,
    ):
        result = _project_status_agent({"query": "how is adpilot doing"}, "test-model")

        self.assertEqual(result["status"], "ok")
        self.assertIn("Main blocker", result["result"])
        self.assertIn("GitHub shows 2 open issues", result["result"])

    @patch("projects.project_store.get_project", return_value=None)
    def test_project_status_agent_asks_for_tracked_project_when_query_is_unknown(self, _mock_get_project):
        result = _project_status_agent({"query": "how is mystery thing doing"}, "test-model")

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["result"], "Which tracked project should I check?")

    @patch(
        "agents.runner._wttr_weather_lookup",
        return_value={
            "provider": "wttr",
            "location": "Mumbai, Maharashtra, India",
            "condition": "Partly cloudy",
            "temp_c": "31",
            "feels_like_c": "34",
            "high_c": "33",
            "low_c": "27",
            "rain_chance": 20,
        },
    )
    @patch("agents.runner._open_meteo_weather_lookup")
    def test_weather_agent_uses_dedicated_weather_provider_first(self, mock_open_meteo, _mock_wttr):
        result = run_agent("weather", {"query": "weather in mumbai"})

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["data"]["tool"], "weather_lookup")
        self.assertEqual(result["data"]["provider"], "wttr")
        self.assertIn("Mumbai", result["result"])
        mock_open_meteo.assert_not_called()

    def test_weather_agent_asks_for_location_when_query_is_missing(self):
        result = _weather_agent({"query": "weather"}, "test-model")

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["result"], "Which location should I check the weather for?")
        self.assertEqual(result["data"], {})

    @patch(
        "agents.runner._wttr_weather_lookup",
        return_value={
            "provider": "wttr",
            "location": "Mumbai, Maharashtra, India",
            "condition": "Light rain",
            "temp_c": "31",
            "feels_like_c": "33",
            "high_c": "34",
            "low_c": "28",
            "rain_chance": 70,
        },
    )
    @patch("agents.runner._open_meteo_weather_lookup")
    def test_weather_agent_formats_tomorrow_forecast_queries(self, mock_open_meteo, _mock_wttr):
        result = _weather_agent({"query": "what's the weather in mumbai tomorrow"}, "test-model")

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["data"]["provider"], "wttr")
        self.assertTrue(result["result"].startswith("Tomorrow in Mumbai"))
        self.assertIn("70% chance of rain", result["result"])
        mock_open_meteo.assert_not_called()

    @patch("agents.runner._wttr_weather_lookup", return_value=None)
    @patch(
        "agents.runner._open_meteo_weather_lookup",
        return_value={
            "provider": "open_meteo",
            "location": "San Francisco, California, United States",
            "condition": "clear",
            "temp_c": "17",
            "feels_like_c": "17",
            "high_c": "19",
            "low_c": "12",
            "rain_chance": 0,
        },
    )
    def test_weather_agent_falls_back_to_open_meteo(self, _mock_open_meteo, _mock_wttr):
        result = run_agent("weather", {"query": "weather in san francisco"})

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["data"]["provider"], "open_meteo")
        self.assertIn("San Francisco", result["result"])

    @patch(
        "agents.runner._fetch_json",
        return_value={
            "Infobox": {
                "content": [
                    {"label": "Born", "value": "1995"},
                    {"label": "Known for", "value": "Reasoning models"},
                ]
            }
        },
    )
    def test_duckduckgo_instant_fact_uses_infobox_rows_when_no_abstract_exists(self, _mock_fetch):
        result = _duckduckgo_instant_fact("who is qwen")

        self.assertIsNotNone(result)
        self.assertEqual(result["source"], "duckduckgo")
        self.assertIn("Born: 1995", result["answer"])
        self.assertIn("Known for: Reasoning models", result["answer"])

    @patch("agents.runner._fetch_json")
    def test_wikipedia_fact_summary_falls_back_to_stripped_subject_candidate(self, mock_fetch_json):
        mock_fetch_json.side_effect = [
            ["who is president of america", [], [], []],
            ["president of america", ["President of the United States"], [""], ["https://example.com/potus"]],
            {
                "extract": "The president of the United States is the head of state of the United States.",
                "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/President_of_the_United_States"}},
            },
        ]

        result = _wikipedia_fact_summary("who is president of america")

        self.assertIsNotNone(result)
        self.assertEqual(result["source"], "wikipedia")
        self.assertEqual(result["title"], "President of the United States")
        self.assertEqual(result["url"], "https://en.wikipedia.org/wiki/President_of_the_United_States")

    @patch("agents.runner._get_installed_models", return_value={"phi4-mini:latest"})
    @patch(
        "brain.ollama_client._get_backend_model_map",
        side_effect=lambda backend, force_refresh=False: (
            {"phi4-mini:latest": "phi4-mini:latest"} if backend == "local" else {}
        ),
    )
    def test_pick_model_uses_agent_chain_fallback(self, _mock_available, _mock_installed):
        with patch("agents.runner.pick_agent_model", return_value="ollama_local::phi4-mini:latest"):
            self.assertEqual(_pick_model("hackernews"), "ollama_local::phi4-mini:latest")

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

    @patch("agents.runner._call_model", return_value="- Reuters says talks are active\n- AP says markets reacted")
    @patch("agents.runner._collect_news_items")
    def test_news_agent_uses_crawled_items(self, mock_collect_news_items, _mock_call):
        mock_collect_news_items.return_value = (
            [
                {
                    "title": "Talks continue",
                    "url": "https://www.reuters.com/world/1",
                    "source": "reuters.com",
                    "article_text": "Diplomatic talks continued after the latest strikes.",
                    "content": "Talks and military updates.",
                },
                {
                    "title": "Regional response",
                    "url": "https://apnews.com/world/2",
                    "source": "apnews.com",
                    "article_text": "Regional governments reacted with new warnings.",
                    "content": "Reaction and warnings.",
                },
            ],
            ["searxng"],
        )

        result = _news_agent({"topic": "Iran and US", "hours": 24}, "test-model")

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["data"]["tool"], "news_crawl")
        self.assertEqual(len(result["data"]["items"]), 2)
        self.assertIn("searxng", result["data"]["sources"])

    @patch("agents.runner._call_model", return_value="")
    @patch("agents.runner._collect_news_items")
    def test_news_agent_falls_back_when_model_returns_empty(self, mock_collect_news_items, _mock_call):
        mock_collect_news_items.return_value = (
            [
                {
                    "title": "Headline 1",
                    "url": "https://example.com/1",
                    "source": "example.com",
                    "article_text": "Talks continue between both sides.",
                    "content": "Talks continue.",
                },
                {
                    "title": "Headline 2",
                    "url": "https://example.com/2",
                    "source": "example.com",
                    "article_text": "Markets responded to the latest escalation.",
                    "content": "Markets reacted.",
                },
            ],
            ["searxng"],
        )

        result = _news_agent({"topic": "AI", "hours": 24}, "test-model")
        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["result"])
        self.assertIn("Headline 1", result["result"])
        self.assertIn("example.com", result["result"])

    @patch("agents.runner._call_model", return_value="I'm still thinking, give me a moment.")
    @patch("agents.runner._collect_news_items")
    def test_news_agent_rejects_timeout_filler_when_items_exist(self, mock_collect_news_items, _mock_call):
        mock_collect_news_items.return_value = (
            [
                {
                    "title": "Nvidia ships faster inference stack",
                    "url": "https://example.com/nvidia",
                    "source": "example.com",
                    "article_text": "Nvidia published a faster serving stack for local inference workloads.",
                    "content": "Nvidia inference update.",
                },
                {
                    "title": "Search latency improves",
                    "url": "https://example.com/search",
                    "source": "example.com",
                    "article_text": "Search providers reported lower latency after cache changes.",
                    "content": "Search cache update.",
                },
            ],
            ["searxng"],
        )

        result = _news_agent({"topic": "AI", "hours": 24}, "test-model")

        self.assertEqual(result["status"], "ok")
        self.assertNotIn("still thinking", result["result"].lower())
        self.assertIn("Nvidia ships faster inference stack", result["result"])
        self.assertEqual(result["data"]["tool"], "news_crawl")

    @patch("agents.runner._fetch_headlines", return_value="")
    @patch("agents.runner._call_model", return_value="I'm still thinking, give me a moment.")
    @patch("agents.runner._collect_news_items", return_value=([], []))
    def test_news_agent_rejects_timeout_filler_when_live_fetch_is_empty(
        self,
        _mock_collect_news_items,
        _mock_call,
        _mock_fetch_headlines,
    ):
        result = _news_agent({"topic": "AI", "hours": 24}, "test-model")

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["result"], "I couldn't fetch live AI news right now.")
        self.assertNotIn("still thinking", result["result"].lower())

    @patch("agents.runner.requests.get")
    def test_google_news_rss_search_parses_feed_items(self, mock_get):
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.text = """
        <rss>
          <channel>
            <item>
              <title>Gemma 4 launches for enterprise AI - Reuters</title>
              <link>https://news.google.com/rss/articles/abc</link>
              <description><![CDATA[<div>Google expanded Gemma 4 deployment options for enterprise teams.</div>]]></description>
              <source url="https://www.reuters.com">Reuters</source>
              <pubDate>Sat, 12 Apr 2026 10:30:00 GMT</pubDate>
            </item>
          </channel>
        </rss>
        """
        mock_get.return_value = mock_response

        items = _google_news_rss_search("Gemma 4", count=2, hours=24)

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["title"], "Gemma 4 launches for enterprise AI")
        self.assertEqual(items[0]["source"], "Reuters")
        self.assertIn("enterprise teams", items[0]["content"])

    @patch("agents.runner._google_news_rss_search")
    @patch("agents.runner._collect_search_items")
    def test_collect_news_items_uses_google_news_rss_when_search_backends_are_empty(
        self,
        mock_collect_search_items,
        mock_rss_search,
    ):
        mock_collect_search_items.side_effect = [
            ([], []),
            ([], []),
            ([], []),
        ]
        mock_rss_search.return_value = [
            {
                "title": "Gemma 4 launches for enterprise AI",
                "url": "https://news.google.com/rss/articles/abc",
                "content": "Google expanded Gemma 4 deployment options for enterprise teams.",
                "source": "Reuters",
                "published": "Sat, 12 Apr 2026 10:30:00 GMT",
            },
            {
                "title": "NVIDIA updates enterprise inference stack",
                "url": "https://news.google.com/rss/articles/def",
                "content": "NVIDIA refreshed its enterprise inference tooling and deployment path.",
                "source": "AP News",
                "published": "Sat, 12 Apr 2026 09:00:00 GMT",
            },
        ]

        items, sources = _collect_news_items("AI", count=2, hours=24)

        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["source"], "Reuters")
        self.assertIn("google_news_rss", sources)

    @patch("agents.runner._call_model", return_value="")
    @patch("agents.runner._google_news_rss_search")
    @patch("agents.runner._collect_search_items")
    def test_news_agent_uses_google_news_rss_fallback_when_search_backends_are_empty(
        self,
        mock_collect_search_items,
        mock_rss_search,
        _mock_call_model,
    ):
        mock_collect_search_items.side_effect = [
            ([], []),
            ([], []),
            ([], []),
        ]
        mock_rss_search.return_value = [
            {
                "title": "Gemma 4 launches for enterprise AI",
                "url": "https://news.google.com/rss/articles/abc",
                "content": "Google expanded Gemma 4 deployment options for enterprise teams.",
                "source": "Reuters",
                "published": "Sat, 12 Apr 2026 10:30:00 GMT",
            }
        ]

        result = _news_agent({"topic": "AI", "hours": 24}, "test-model")

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["data"]["tool"], "news_crawl")
        self.assertIn("google_news_rss", result["data"]["sources"])
        self.assertIn("Reuters", result["result"])

    @patch("agents.runner._exa_search", return_value=[{"title": "Exa story", "url": "https://example.com/exa", "content": "Fresh result"}])
    @patch("agents.runner._duckduckgo_search", return_value=[])
    @patch("agents.runner._searxng_search", return_value=[])
    def test_collect_search_items_uses_exa_when_local_and_free_search_are_empty(self, _mock_searxng, _mock_ddg, _mock_exa):
        items, sources = _collect_search_items("ai news", count=2)
        self.assertEqual(items[0]["title"], "Exa story")
        self.assertIn("exa", sources)

    @patch("agents.runner._exa_search", return_value=[])
    @patch("agents.runner._duckduckgo_search", return_value=[{"title": "DDG story", "url": "https://example.com/ddg", "content": "DuckDuckGo result"}])
    @patch("agents.runner._searxng_search", return_value=[])
    def test_collect_search_items_uses_duckduckgo_before_exa(self, _mock_searxng, _mock_ddg, _mock_exa):
        items, sources = _collect_search_items("ai news", count=2)
        self.assertEqual(items[0]["title"], "DDG story")
        self.assertIn("duckduckgo", sources)
        self.assertNotIn("exa", sources)

    @patch.dict("agents.runner._RETRIEVAL_RESULT_CACHE", {}, clear=True)
    @patch("agents.runner._retrieval_cache_enabled", return_value=True)
    @patch("agents.runner._exa_search", return_value=[])
    @patch("agents.runner._duckduckgo_search", return_value=[])
    @patch(
        "agents.runner._searxng_search",
        return_value=[
            {
                "title": "Low-latency retrieval win",
                "url": "https://example.com/latency",
                "content": "Retriever now reuses cached search results for repeated queries.",
            }
        ],
    )
    def test_collect_search_items_reuses_cached_results_for_repeated_query(
        self,
        mock_searxng,
        _mock_ddg,
        _mock_exa,
        _mock_cache_enabled,
    ):
        first_items, first_sources = _collect_search_items("latency cache query", count=1)
        second_items, second_sources = _collect_search_items("latency cache query", count=1)

        self.assertEqual(first_items, second_items)
        self.assertEqual(first_sources, second_sources)
        mock_searxng.assert_called_once()

    @patch("agents.runner._google_news_rss_search", return_value=[])
    @patch("agents.runner._jina_fetch")
    @patch("agents.runner._cached_page_text", return_value="")
    @patch("agents.runner._collect_search_items")
    def test_collect_news_items_skips_live_fetch_when_search_snippet_is_rich(
        self,
        mock_collect_search_items,
        _mock_cached,
        mock_jina,
        _mock_rss,
    ):
        mock_collect_search_items.return_value = (
            [
                {
                    "title": "Retriever ships a faster cache path",
                    "url": "https://example.com/cache",
                    "content": (
                        "The retrieval owner now reuses prior search results for repeated questions, "
                        "skips unnecessary live page fetches when the provider snippet already carries enough detail, "
                        "and keeps the spoken answer branch fast for repeat lookups in the same session."
                    ),
                }
            ],
            ["searxng"],
        )

        items, sources = _collect_news_items("retrieval latency", count=1, hours=24)

        mock_jina.assert_not_called()
        self.assertEqual(items[0]["article_text"], "")
        self.assertIn("skips unnecessary live page fetches", items[0]["content"])
        self.assertEqual(sources, ["searxng"])

    @patch("agents.runner._google_news_rss_search", return_value=[])
    @patch("agents.runner._remember_page_text")
    @patch("agents.runner._jina_fetch", return_value="Fresh live article text that adds the missing latency details and rollout context.")
    @patch("agents.runner._cached_page_text", return_value="")
    @patch("agents.runner._collect_search_items")
    def test_collect_news_items_fetches_live_page_when_search_snippet_is_thin(
        self,
        mock_collect_search_items,
        _mock_cached,
        mock_jina,
        mock_remember,
        _mock_rss,
    ):
        mock_collect_search_items.return_value = (
            [
                {
                    "title": "Retriever update",
                    "url": "https://example.com/update",
                    "content": "Small update.",
                }
            ],
            ["searxng"],
        )

        items, _sources = _collect_news_items("retrieval latency thin snippet", count=1, hours=24)

        mock_jina.assert_called_once_with("https://example.com/update")
        mock_remember.assert_called_once()
        self.assertIn("Fresh live article text", items[0]["article_text"])

    @patch("agents.runner._retrieval_cache_enabled", return_value=False)
    @patch("agents.runner._jina_fetch")
    @patch("agents.runner._cached_page_text", return_value="")
    @patch("agents.runner._embed", return_value=[])
    @patch("agents.runner._duckduckgo_search", return_value=[])
    @patch("agents.runner._exa_search", return_value=[])
    @patch(
        "agents.runner._searxng_search",
        return_value=[
            {
                "title": "Retriever gets faster on repeated lookups",
                "url": "https://example.com/retrieval",
                "content": (
                    "The provider snippet already explains the repeated-query cache, the snippet-first rule, "
                    "and the lower latency for repeat search and news lookups without needing a second page fetch."
                ),
            }
        ],
    )
    def test_fetch_search_text_skips_live_page_fetch_when_top_snippet_is_rich(
        self,
        _mock_searxng,
        _mock_exa,
        _mock_ddg,
        _mock_embed,
        _mock_cached,
        mock_jina,
        _mock_cache_enabled,
    ):
        material = _fetch_search_text("retrieval latency rich snippet", count=1)

        mock_jina.assert_not_called()
        self.assertIn("Retriever gets faster on repeated lookups", material)

    @patch("agents.runner._jina_fetch", return_value="This page describes Gemma 4 features, pricing, and launch context.")
    @patch("memory.knowledge_base.get_indexed_document", return_value=None)
    @patch("agents.runner._call_model", return_value="The page says Gemma 4 launched with stronger multimodal support and broader deployment options.")
    def test_fetch_agent_reads_and_summarizes_url(self, _mock_call, _mock_cached, _mock_fetch):
        result = _fetch_agent({"query": "read this https://example.com/post", "url": "https://example.com/post"}, "test-model")
        self.assertEqual(result["status"], "ok")
        self.assertIn("Gemma 4", result["result"])
        self.assertEqual(result["data"]["tool"], "jina_fetch")

    @patch("agents.runner._call_model", return_value="Cached page summary.")
    @patch("agents.runner._jina_fetch")
    @patch(
        "memory.knowledge_base.get_indexed_document",
        return_value={"text": "Cached Gemma 4 page snapshot with stronger multimodal support and deployment guidance."},
    )
    def test_fetch_agent_uses_indexed_page_snapshot_before_live_fetch(self, _mock_cached, mock_jina, _mock_call):
        result = _fetch_agent({"query": "read this https://example.com/post", "url": "https://example.com/post"}, "test-model")

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["result"], "Cached page summary.")
        mock_jina.assert_not_called()

    @patch("agents.runner._call_model", return_value="Fresh page summary.")
    @patch("memory.knowledge_base.get_indexed_document", return_value=None)
    @patch("memory.knowledge_base.index_web_page")
    @patch("agents.runner._jina_fetch", return_value="Fresh Gemma 4 page text from live fetch.")
    def test_fetch_agent_indexes_live_page_snapshot_for_reuse(self, _mock_fetch, mock_index, _mock_cached, _mock_call):
        result = _fetch_agent({"query": "read this https://example.com/post", "url": "https://example.com/post"}, "test-model")

        self.assertEqual(result["status"], "ok")
        mock_index.assert_called_once_with(
            "https://example.com/post",
            "Fresh Gemma 4 page text from live fetch.",
            title="",
        )

    @patch("agents.runner._call_model", return_value="This page says Gemma 4 launched with broader deployment support.")
    @patch("agents.runner._cached_or_live_page_text", return_value="Gemma 4 launch notes with broader deployment support and lower latency.")
    @patch("context.mac_activity.get_active_browser_url")
    @patch("context.mac_activity.load_state", return_value={"browser_url": "https://example.com/current"})
    def test_fetch_agent_reads_current_browser_page_without_explicit_url(
        self,
        _mock_state,
        mock_active_url,
        _mock_fetch,
        _mock_call,
    ):
        result = _fetch_agent({"query": "read this page"}, "test-model")

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["data"]["tool"], "current_page_fetch")
        self.assertEqual(result["data"]["url"], "https://example.com/current")
        mock_active_url.assert_not_called()

    @patch("context.mac_activity.get_active_browser_url", return_value="")
    @patch("context.mac_activity.load_state", return_value={})
    def test_fetch_agent_returns_truthful_message_when_current_browser_page_is_unavailable(
        self,
        _mock_state,
        _mock_active_url,
    ):
        result = _fetch_agent({"query": "read this page"}, "test-model")

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["result"], "I couldn't find the current browser page to read.")

    def test_search_agent_asks_for_clarification_on_too_short_query(self):
        result = _search_agent({"query": "what is"}, "test-model")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["result"], "Tell me what to look up.")

    @patch("agents.runner._quick_fact_lookup", return_value=None)
    @patch("agents.runner._call_model", return_value="")
    @patch("agents.runner._collect_search_items")
    def test_search_agent_falls_back_to_first_result_when_model_returns_empty(self, mock_collect_search_items, _mock_call, _mock_fact):
        mock_collect_search_items.return_value = (
            [
                {
                    "title": "Claude launches a new product",
                    "url": "https://example.com/claude",
                    "content": "Anthropic introduced a new Claude product for teams.",
                }
            ],
            ["exa"],
        )

        result = _search_agent({"query": "what is the new product from claude"}, "test-model")

        self.assertEqual(result["status"], "ok")
        self.assertIn("Claude launches a new product", result["result"])

    @patch("agents.runner._quick_fact_lookup", return_value=None)
    @patch(
        "agents.runner._call_model",
        return_value=(
            "Anthropic Unveils Claude 4.5: Smarter Context, Lower Cost for Enterprise AI — Tech Daily Shot. "
            "Unveils Claude 4.5: Smarter Context, Lower Cost for Enterprise AI — Tech Daily Shot ..."
        ),
    )
    @patch("agents.runner._collect_search_items")
    def test_search_agent_rejects_repeated_title_dump(self, mock_collect_search_items, _mock_call, _mock_fact):
        mock_collect_search_items.return_value = (
            [
                {
                    "title": "Anthropic Unveils Claude 4.5: Smarter Context, Lower Cost for Enterprise AI",
                    "url": "https://example.com/claude-45",
                    "content": "Anthropic says the release improves context handling and lowers enterprise cost.",
                }
            ],
            ["exa"],
        )

        result = _search_agent({"query": "what is the new product from claude"}, "test-model")

        self.assertEqual(result["status"], "ok")
        self.assertNotIn("Tech Daily Shot ...", result["result"])
        self.assertIn("The new product looks like Claude 4.5", result["result"])

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

    @patch("agents.runner._call_model", return_value="Fallback summary")
    def test_all_new_agents_have_fallback(self, _mock_call_model):
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
