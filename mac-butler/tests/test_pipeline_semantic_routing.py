import unittest
from unittest.mock import patch

import butler
from intents.router import IntentResult


class SemanticRoutingIntegrationTests(unittest.TestCase):
    def setUp(self):
        butler.ctx.reset()

    def tearDown(self):
        butler.ctx.reset()

    @patch("capabilities.planner.load_runtime_snapshot", return_value={"workspace": {"frontmost_app": "Google Chrome"}})
    @patch("butler.note_intent")
    @patch("butler._record")
    @patch("butler._speak_or_print")
    def test_handle_input_executes_semantic_minimize(self, mock_speak, _mock_record, mock_note_intent, _mock_runtime):
        butler.handle_input("minimize this window", test_mode=True)

        mock_note_intent.assert_any_call("minimize_app", {"app": "Google Chrome"}, 0.9, raw="minimize this window")

    @patch("butler.note_intent")
    @patch("butler.executor.run", return_value=[{"action": "run_agent", "status": "ok", "result": "CPU is healthy and memory is stable."}])
    @patch("butler._record")
    @patch("butler._speak_or_print")
    def test_handle_input_executes_semantic_vps_lookup(self, mock_speak, mock_record, mock_run, mock_note_intent):
        butler.handle_input("check my vps", test_mode=True)

        mock_run.assert_called_once()
        action = mock_run.call_args.args[0][0]
        self.assertEqual(action["type"], "run_agent")
        self.assertEqual(action["agent"], "vps")
        mock_note_intent.assert_any_call("vps_status", {}, 0.88, raw="check my vps")
        recorded_intent = mock_record.call_args.kwargs["intent_name"]
        self.assertEqual(recorded_intent, "vps_status")

    @patch("butler.note_intent")
    @patch("butler._record")
    @patch("butler._speak_or_print")
    def test_handle_input_routes_youtube_play_directly(self, mock_speak, _mock_record, mock_note_intent):
        butler.handle_input("play shape of you on youtube", test_mode=True)

        mock_note_intent.assert_any_call(
            "open_app",
            {
                "app": ("browser", "https://www.youtube.com/results?search_query=shape+of+you"),
                "name": "YouTube results",
            },
            1.0,
            raw="play shape of you on youtube",
        )

    @patch("butler.note_intent")
    @patch("butler._record")
    @patch("butler._speak_or_print")
    def test_handle_input_overrides_old_folder_route_for_desktop_path(self, mock_speak, _mock_record, mock_note_intent):
        butler.handle_input("create a folder on desktop with name aditya test", test_mode=True)

        mock_note_intent.assert_any_call(
            "create_folder",
            {"path": "~/Desktop", "name": "aditya test"},
            1.0,
            raw="create a folder on desktop with name aditya test",
        )

    @patch("butler.note_intent")
    @patch("butler.executor.run", return_value=[{"action": "run_agent", "status": "ok", "result": "Mumbai is 31 degrees and hazy."}])
    @patch("butler._record")
    @patch("butler._speak_or_print")
    def test_handle_input_executes_weather_lookup_before_fallback(self, mock_speak, mock_record, mock_run, mock_note_intent):
        butler.handle_input("search weather in mumbai", test_mode=True)

        mock_run.assert_called_once()
        action = mock_run.call_args.args[0][0]
        self.assertEqual(action["type"], "run_agent")
        self.assertEqual(action["agent"], "weather")
        self.assertEqual(action["query"], "weather in mumbai")
        mock_note_intent.assert_any_call("lookup_weather", {"query": "weather in mumbai"}, 0.9, raw="search weather in mumbai")
        recorded_intent = mock_record.call_args.kwargs["intent_name"]
        self.assertEqual(recorded_intent, "lookup_weather")

    @patch("capabilities.planner._project_names_with_repos", return_value=["Adpilot"])
    @patch("butler.note_intent")
    @patch("butler.executor.run", return_value=[{"action": "run_agent", "status": "ok", "result": "Adpilot has 2 open issues and 1 open pull request."}])
    @patch("butler._record")
    @patch("butler._speak_or_print")
    def test_handle_input_executes_github_status_lookup_before_generic_fallback(
        self,
        mock_speak,
        mock_record,
        mock_run,
        mock_note_intent,
        _mock_projects,
    ):
        butler.handle_input("any issues on adpilot", test_mode=True)

        mock_run.assert_called_once()
        action = mock_run.call_args.args[0][0]
        self.assertEqual(action["type"], "run_agent")
        self.assertEqual(action["agent"], "github")
        self.assertEqual(action["query"], "any issues on adpilot")
        mock_note_intent.assert_any_call("lookup_github_status", {"query": "any issues on adpilot"}, 0.88, raw="any issues on adpilot")
        recorded_intent = mock_record.call_args.kwargs["intent_name"]
        self.assertEqual(recorded_intent, "lookup_github_status")

    @patch("capabilities.planner._project_names", return_value=["Adpilot"])
    @patch("butler.note_intent")
    @patch("butler.executor.run", return_value=[{"action": "run_agent", "status": "ok", "result": "Adpilot is active and 76% complete."}])
    @patch("butler._record")
    @patch("butler._speak_or_print")
    def test_handle_input_executes_project_status_lookup_before_generic_fallback(
        self,
        mock_speak,
        mock_record,
        mock_run,
        mock_note_intent,
        _mock_projects,
    ):
        butler.handle_input("how is adpilot doing", test_mode=True)

        mock_run.assert_called_once()
        action = mock_run.call_args.args[0][0]
        self.assertEqual(action["type"], "run_agent")
        self.assertEqual(action["agent"], "project_status")
        self.assertEqual(action["query"], "how is adpilot doing")
        mock_note_intent.assert_any_call("lookup_project_status", {"query": "how is adpilot doing"}, 0.86, raw="how is adpilot doing")
        recorded_intent = mock_record.call_args.kwargs["intent_name"]
        self.assertEqual(recorded_intent, "lookup_project_status")

    @patch("capabilities.planner.load_runtime_snapshot", return_value={"browser_url": "https://example.com/current"})
    @patch("butler.note_intent")
    @patch("butler.executor.run", return_value=[{"action": "run_agent", "status": "ok", "result": "This page is about Gemma 4."}])
    @patch("butler._record")
    @patch("butler._speak_or_print")
    def test_handle_input_executes_page_lookup_before_generic_fallback(
        self,
        mock_speak,
        mock_record,
        mock_run,
        mock_note_intent,
        _mock_runtime,
    ):
        butler.handle_input("read this page", test_mode=True)

        mock_run.assert_called_once()
        action = mock_run.call_args.args[0][0]
        self.assertEqual(action["type"], "run_agent")
        self.assertEqual(action["agent"], "fetch")
        self.assertEqual(action["query"], "read this page")
        self.assertEqual(action["url"], "https://example.com/current")
        mock_note_intent.assert_any_call(
            "lookup_page",
            {"query": "read this page", "url": "https://example.com/current"},
            0.88,
            raw="read this page",
        )
        recorded_intent = mock_record.call_args.kwargs["intent_name"]
        self.assertEqual(recorded_intent, "lookup_page")

    @patch("agents.runner.run_agent", return_value={"result": "Top AI story: new model release."})
    @patch("butler.note_intent")
    @patch("butler._record")
    @patch("butler._speak_or_print")
    def test_handle_input_overrides_background_news_with_sync_lookup(self, mock_speak, mock_record, mock_note_intent, mock_run_agent):
        butler.handle_input("latest ai news", test_mode=True)

        mock_run_agent.assert_called_once()
        self.assertEqual(mock_run_agent.call_args.args[0], "news")
        self.assertEqual(mock_run_agent.call_args.args[1]["topic"], "AI")
        mock_note_intent.assert_any_call("news", {"topic": "AI", "hours": 24}, 1.0, raw="latest ai news")
        recorded_intent = mock_record.call_args.kwargs["intent_name"]
        self.assertEqual(recorded_intent, "news")

    @patch("skills.match_skill", return_value=(None, {}))
    @patch("butler.instant_route", return_value=None)
    @patch("butler.route", return_value=IntentResult("question", confidence=0.9, raw="who is PM of India"))
    @patch("pipeline.router._lightweight_reply", side_effect=AssertionError("current role lookup must not ask the lightweight model first"))
    @patch("butler._get_cached_context", return_value={})
    @patch("butler._warn_if_search_offline")
    @patch("butler.note_intent")
    @patch("butler.executor.run", return_value=[{"action": "run_agent", "status": "ok", "result": "Narendra Modi is the Prime Minister of India."}])
    @patch("butler._record")
    @patch("butler._speak_or_print")
    def test_handle_input_routes_pm_question_to_search_not_news_or_model_fallback(
        self,
        mock_speak,
        mock_record,
        mock_run,
        mock_note_intent,
        _mock_search_warning,
        _mock_context,
        mock_lightweight,
        _mock_route,
        _mock_instant,
        _mock_skill,
    ):
        butler.handle_input("who is PM of India", test_mode=True)

        mock_run.assert_called_once()
        mock_lightweight.assert_not_called()
        action = mock_run.call_args.args[0][0]
        self.assertEqual(action["type"], "run_agent")
        self.assertEqual(action["agent"], "search")
        self.assertEqual(action["query"], "who is PM of India")
        mock_note_intent.assert_any_call("lookup_web", {"query": "who is PM of India"}, 0.76, raw="who is PM of India")
        mock_speak.assert_called_once_with("Narendra Modi is the Prime Minister of India.", test_mode=True)
        recorded_intent = mock_record.call_args.kwargs["intent_name"]
        self.assertEqual(recorded_intent, "lookup_web")


if __name__ == "__main__":
    unittest.main()
