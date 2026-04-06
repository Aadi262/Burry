import unittest

from brain.query_analyzer import analyze_query


class QueryAnalyzerTests(unittest.TestCase):
    def test_latest_news_routes_to_news_action(self):
        decision = analyze_query("latest news in india last 24 hours")
        self.assertEqual(decision["action"], "news")
        self.assertTrue(decision["time_sensitive"])

    def test_new_product_question_routes_to_search_action(self):
        decision = analyze_query("what is the new product from claude")
        self.assertEqual(decision["action"], "search")

    def test_url_request_routes_to_fetch_action(self):
        decision = analyze_query("read this article https://example.com/post")
        self.assertEqual(decision["action"], "fetch")
        self.assertEqual(decision["url"], "https://example.com/post")

    def test_domain_only_request_normalizes_fetch_url(self):
        decision = analyze_query("read this page example.com/gemma")
        self.assertEqual(decision["action"], "fetch")
        self.assertEqual(decision["url"], "https://example.com/gemma")

    def test_concept_question_routes_to_internal_action(self):
        decision = analyze_query("explain quantum computing")
        self.assertEqual(decision["action"], "internal")


if __name__ == "__main__":
    unittest.main()
