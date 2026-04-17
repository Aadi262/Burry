import unittest
from unittest.mock import patch

from capabilities.planner import plan_semantic_task
from capabilities.registry import (
    build_action,
    get_capability_descriptor,
    get_tool_spec,
    list_public_capabilities,
    tool_catalog_for_prompt,
)


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

    @patch("capabilities.planner._project_names_with_repos", return_value=["Adpilot"])
    def test_github_issue_phrase_maps_to_github_status_lookup(self, _mock_projects):
        task = plan_semantic_task("any issues on adpilot", current_intent="unknown")

        self.assertIsNotNone(task)
        self.assertEqual(task.tool, "lookup_github_status")
        self.assertEqual(task.args["query"], "any issues on adpilot")
        self.assertEqual(task.intent_name, "lookup_github_status")

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
        self.assertEqual(spec.capability_id, "T14")

    def test_lookup_weather_builds_weather_agent_action(self):
        action = build_action("lookup_weather", {"query": "weather in mumbai"})

        self.assertEqual(action["type"], "run_agent")
        self.assertEqual(action["agent"], "weather")
        self.assertEqual(action["query"], "weather in mumbai")
        self.assertEqual(action["capability_id"], "K04")

    def test_lookup_github_status_builds_github_agent_action(self):
        action = build_action("lookup_github_status", {"query": "any issues on adpilot"})

        self.assertEqual(action["type"], "run_agent")
        self.assertEqual(action["agent"], "github")
        self.assertEqual(action["query"], "any issues on adpilot")
        self.assertEqual(action["capability_id"], "K10")

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
        self.assertEqual(action["capability_id"], "E03")
        self.assertEqual(action["tool_name"], "compose_email")

    def test_public_capability_descriptors_are_stable_and_prompt_catalog_uses_ids(self):
        descriptor = get_capability_descriptor("lookup_news")
        descriptors = list_public_capabilities()
        catalog = tool_catalog_for_prompt()

        self.assertIsNotNone(descriptor)
        self.assertEqual(descriptor.capability_id, "K03")
        self.assertEqual(descriptor.tool_name, "lookup_news")
        self.assertTrue(any(item.capability_id == "SY14" for item in descriptors))
        self.assertIn("[K03] lookup_news", catalog)


if __name__ == "__main__":
    unittest.main()
