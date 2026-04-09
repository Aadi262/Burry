import unittest
from unittest.mock import patch

from capabilities.planner import plan_semantic_task
from capabilities.registry import build_action, get_tool_spec


class SemanticPlannerTests(unittest.TestCase):
    @patch("capabilities.planner.load_runtime_snapshot", return_value={"workspace": {"frontmost_app": "Google Chrome"}})
    def test_minimize_current_window_resolves_frontmost_app(self, _mock_runtime):
        task = plan_semantic_task("minimize this window", current_intent="unknown")
        self.assertIsNotNone(task)
        self.assertEqual(task.tool, "minimize_app")
        self.assertEqual(task.args["app"], "Google Chrome")

    def test_folder_request_on_desktop_maps_to_create_folder(self):
        task = plan_semantic_task("make one more folder on desktop with name aditya test", current_intent="unknown")
        self.assertIsNotNone(task)
        self.assertEqual(task.tool, "create_folder")
        self.assertTrue(task.args["path"].endswith("/Desktop/aditya test"))

    def test_desktop_folder_request_overrides_old_create_folder_route(self):
        task = plan_semantic_task("create a folder on desktop with name aditya test", current_intent="create_folder")
        self.assertIsNotNone(task)
        self.assertTrue(task.force_override)
        self.assertTrue(task.args["path"].endswith("/Desktop/aditya test"))

    def test_check_my_vps_maps_to_sync_vps_lookup(self):
        task = plan_semantic_task("check my vps", current_intent="unknown")
        self.assertIsNotNone(task)
        self.assertEqual(task.tool, "check_vps")
        self.assertEqual(task.kind, "lookup")
        self.assertEqual(task.intent_name, "vps_status")

    def test_weather_phrase_maps_to_weather_lookup(self):
        task = plan_semantic_task("search weather in mumbai", current_intent="unknown")
        self.assertIsNotNone(task)
        self.assertEqual(task.tool, "lookup_weather")
        self.assertEqual(task.args["query"], "weather in mumbai")

    def test_youtube_play_overrides_spotify_route(self):
        task = plan_semantic_task("play shape of you on youtube", current_intent="spotify_play")
        self.assertIsNotNone(task)
        self.assertEqual(task.tool, "play_youtube")
        self.assertTrue(task.force_override)
        action = build_action(task.tool, task.args)
        self.assertEqual(action["type"], "open_url_in_browser")
        self.assertIn("youtube.com/results", action["url"])

    def test_latest_news_maps_to_sync_news_lookup(self):
        task = plan_semantic_task("latest ai news", current_intent="news")
        self.assertIsNotNone(task)
        self.assertEqual(task.tool, "lookup_news")
        self.assertTrue(task.force_override)
        self.assertEqual(task.args["topic"], "AI")


class ToolRegistryTests(unittest.TestCase):
    def test_check_vps_spec_is_sync(self):
        spec = get_tool_spec("check_vps")
        self.assertIsNotNone(spec)
        self.assertTrue(spec.sync_execution)

    def test_compose_email_builds_browser_action(self):
        action = build_action(
            "compose_email",
            {
                "recipient": "vedang2803@gmail.com",
                "subject": "test gmail",
                "body": "how are u",
            },
        )
        self.assertEqual(action["type"], "open_url_in_browser")
        self.assertIn("to=vedang2803%40gmail.com", action["url"])
        self.assertIn("body=how+are+u", action["url"])


if __name__ == "__main__":
    unittest.main()
