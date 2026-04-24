import unittest
from unittest.mock import patch

from agents.research_agent import deep_research


class ResearchAgentTests(unittest.TestCase):
    @patch("agents.research_agent._deep_research_custom", side_effect=AssertionError("slow research path should not run"))
    @patch(
        "agents.research_agent.run_agent",
        return_value={
            "status": "ok",
            "result": "Adpilot is active and about 76% complete. Main blocker is feature-status drift.",
            "data": {"tool": "project_status"},
        },
    )
    def test_deep_research_uses_fast_project_status_lookup_before_slow_research(
        self,
        mock_run_agent,
        _mock_slow_research,
    ):
        result = deep_research("how is adpilot doing")

        self.assertIn("76% complete", result)
        mock_run_agent.assert_called_once_with("project_status", {"query": "how is adpilot doing"})

    @patch("agents.research_agent._deep_research_custom", side_effect=AssertionError("slow research path should not run"))
    @patch(
        "agents.research_agent.run_agent",
        return_value={
            "status": "ok",
            "result": "- New Gemini launch (Reuters)\n- Nvidia updates local inference stack (The Verge)",
            "data": {"tool": "news_crawl"},
        },
    )
    def test_deep_research_uses_fast_news_lookup_for_live_news_questions(
        self,
        mock_run_agent,
        _mock_slow_research,
    ):
        result = deep_research("research latest ai news")

        self.assertIn("Nvidia", result)
        mock_run_agent.assert_called_once()
        self.assertEqual(mock_run_agent.call_args.args[0], "news")
