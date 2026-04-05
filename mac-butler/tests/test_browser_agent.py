#!/usr/bin/env python3

import unittest
from unittest.mock import patch

from browser.agent import BrowsingAgent


class BrowsingAgentTests(unittest.TestCase):
    @patch("browser.agent._call", return_value="Gemma 4 launched with stronger multimodal support and broader deployment options.")
    @patch.object(BrowsingAgent, "_fetch", return_value="Gemma 4 launched with broader deployment support and multimodal features.")
    @patch.object(
        BrowsingAgent,
        "_searxng",
        return_value=[
            {
                "title": "Gemma 4 launch",
                "url": "https://example.com/gemma4",
                "content": "Gemma 4 launch overview",
            }
        ],
    )
    def test_search_reads_pages_and_summarizes(self, _mock_search, _mock_fetch, _mock_call):
        agent = BrowsingAgent(model="test-model")
        result = agent.search("latest news on gemma")

        self.assertEqual(result["status"], "ok")
        self.assertIn("Gemma 4", result["result"])
        self.assertEqual(result["data"]["tool"], "browser_search")
        self.assertEqual(result["data"]["sources"], ["searxng"])

    @patch("browser.agent._call", return_value="The page says Claude 4.5 lowered enterprise cost and improved context handling.")
    @patch.object(BrowsingAgent, "_fetch", return_value="Claude 4.5 improved enterprise cost and context handling.")
    def test_fetch_reads_single_page_and_answers_question(self, _mock_fetch, _mock_call):
        agent = BrowsingAgent(model="test-model")
        result = agent.fetch("https://example.com/claude", "what is new here")

        self.assertEqual(result["status"], "ok")
        self.assertIn("Claude 4.5", result["result"])
        self.assertEqual(result["data"]["tool"], "browser_fetch")


if __name__ == "__main__":
    unittest.main()
