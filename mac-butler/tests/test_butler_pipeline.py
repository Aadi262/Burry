import unittest
from unittest.mock import patch

from brain.ollama_client import _strip_repeated_project_from_task
from butler import (
    _brain_context_text,
    _clear_pending_dialogue,
    _contextualize_action,
    _deterministic_project_plan,
    _extract_news_topic,
    _direct_agent_plan_for_text,
    _normalize_response,
    _plan_with_brain,
    _project_snapshot_for_planning,
    _question_needs_brain_agents,
    _rewrite_speech_with_agent_results,
    _resolve_pending_dialogue,
    _run_actions_with_response,
    _unknown_response_for_text,
    observe_and_followup,
    get_quick_response,
)
from intents.router import IntentResult


class ButlerPipelineTests(unittest.TestCase):
    def tearDown(self):
        _clear_pending_dialogue()

    def test_contextualize_create_file_uses_workspace(self):
        action = {"type": "create_file_in_editor", "filename": "demo.py", "editor": "Cursor"}
        intent = IntentResult("create_file", {"filename": "demo.py"}, 0.9, "create file demo.py")
        ctx = {"raw": {"editor": {"workspace_paths": ["~/Burry/mac-butler"]}}}
        enriched = _contextualize_action(action, intent, ctx)
        self.assertEqual(enriched["directory"], "~/Burry/mac-butler")

    def test_quick_response_for_open_project(self):
        intent = IntentResult("open_project", {"project": "mac-butler"}, 0.9, "open mac-butler")
        self.assertIn("Opening", get_quick_response(intent))

    def test_normalize_response_collapses_lines(self):
        text = "Still grinding on mac-butler.\nWant to wire the validator next?"
        normalized = _normalize_response(text, max_words=20)
        self.assertEqual(
            normalized,
            "Still grinding on mac-butler. Want to wire the validator next?",
        )

    def test_unknown_music_request_sets_song_clarification(self):
        response = _unknown_response_for_text("spotify song please")
        self.assertEqual(response, "I didn't catch the song. Say the title and artist.")

        follow_up = _resolve_pending_dialogue("mockingbird by eminem")
        self.assertIsNotNone(follow_up)
        self.assertEqual(follow_up.name, "spotify_play")
        self.assertEqual(follow_up.params["song"], "mockingbird by eminem")

    def test_unknown_file_request_sets_name_clarification(self):
        response = _unknown_response_for_text("make a new file")
        self.assertEqual(response, "What should I name the file?")

        follow_up = _resolve_pending_dialogue("Aditya")
        self.assertIsNotNone(follow_up)
        self.assertEqual(follow_up.name, "create_file")
        self.assertEqual(follow_up.params["filename"], "Aditya")

    def test_strip_repeated_project_from_task_clause(self):
        cleaned = _strip_repeated_project_from_task(
            "mac-butler",
            "wire the two-stage LLM into mac-butler",
        )
        self.assertEqual(cleaned, "wire the two-stage LLM")

    @patch("brain.ollama_client.send_to_ollama")
    def test_plan_with_brain_parses_speech_and_actions(self, mock_send_to_ollama):
        mock_send_to_ollama.return_value = (
            '{"speech":"Open mac-butler and ship the router fix.","actions":'
            '[{"type":"open_editor","path":"~/Burry/mac-butler","editor":"cursor","mode":"smart"}],'
            '"focus":"mac-butler","why_now":"Router is the blocker."}'
        )

        plan = _plan_with_brain("[FOCUS]\n  project: mac-butler")

        self.assertEqual(plan["focus"], "mac-butler")
        self.assertEqual(plan["actions"][0]["type"], "open_editor")
        self.assertIn("router fix", plan["speech"])

    @patch("butler._raw_llm", return_value="Docker looks healthy overall.")
    def test_observe_and_followup_summarizes_meaningful_results(self, _mock_llm):
        observation = observe_and_followup(
            {"speech": "Checking VPS."},
            [{"action": "run_agent", "status": "ok", "result": "docker ps output"}],
            test_mode=False,
        )
        self.assertEqual(observation, "Docker looks healthy overall.")

    def test_observe_and_followup_skips_open_project_results(self):
        observation = observe_and_followup(
            {"speech": "Opening Adpilot."},
            [{"action": "open_project", "status": "ok", "result": "opened Adpilot in antigravity"}],
            test_mode=False,
        )
        self.assertEqual(observation, "")

    @patch("butler._raw_llm", return_value="Something went wrong.")
    def test_rewrite_speech_with_agent_results_falls_back_to_agent_output(self, _mock_llm):
        rewritten = _rewrite_speech_with_agent_results(
            "Checking trending repos.",
            [{"action": "run_agent", "status": "ok", "result": "- Blaizzy/mlx-vlm is trending.\n- onyx is climbing."}],
        )
        self.assertIn("Blaizzy/mlx-vlm", rewritten)
        self.assertNotEqual(rewritten, "Something went wrong.")

    @patch("butler._record")
    @patch("butler._speak_or_print")
    @patch("butler._rewrite_speech_with_agent_results")
    @patch("butler.executor.run")
    def test_run_actions_with_response_uses_agent_summary_directly_for_run_agent_only(
        self,
        mock_run,
        mock_rewrite,
        mock_speak_or_print,
        _mock_record,
    ):
        mock_run.return_value = [
            {
                "action": "run_agent",
                "status": "ok",
                "result": "MLX VLM is trending and Onyx just shipped a new release.",
            }
        ]

        final_response, _results = _run_actions_with_response(
            text="trending repos",
            response="Checking trending repos.",
            actions=[{"type": "run_agent", "agent": "github_trending", "language": "python"}],
            test_mode=False,
        )

        self.assertEqual(final_response, "MLX VLM is trending and Onyx just shipped a new release.")
        mock_rewrite.assert_not_called()
        mock_speak_or_print.assert_called_once_with(
            "MLX VLM is trending and Onyx just shipped a new release.",
            test_mode=False,
        )

    def test_brain_context_text_includes_request_and_hint(self):
        ctx = {"formatted": "[FOCUS]\n  project: mac-butler"}
        text = _brain_context_text(ctx, "check latest AI news")
        self.assertIn("[USER REQUEST]", text)
        self.assertIn("run_agent", text)

    @patch("projects.load_projects")
    def test_brain_context_text_includes_project_snapshot_for_what_next(self, mock_load_projects):
        mock_load_projects.return_value = [
            {
                "name": "Adpilot",
                "status": "active",
                "completion": 94,
                "last_opened": "2026-04-05T15:00:00",
                "next_tasks": ["Verify deploy checks"],
                "blockers": ["OAuth still needs final setup"],
            }
        ]
        ctx = {"formatted": "[FOCUS]\n  project: Adpilot"}
        text = _brain_context_text(ctx, "what should i do next")
        self.assertIn("[PROJECT SNAPSHOT]", text)
        self.assertIn("Verify deploy checks", text)

    @patch("projects.load_projects")
    def test_project_snapshot_for_planning_prefers_real_project_state(self, mock_load_projects):
        mock_load_projects.return_value = [
            {
                "name": "Adpilot",
                "status": "active",
                "completion": 94,
                "last_opened": "2026-04-05T15:00:00",
                "next_tasks": ["Verify deploy checks"],
                "blockers": ["OAuth still needs final setup"],
            },
            {
                "name": "mac-butler",
                "status": "active",
                "completion": 71,
                "last_opened": "2026-04-05T14:00:00",
                "next_tasks": ["Tighten follow-up voice behavior"],
                "blockers": ["Project OS layer is not fully wired yet"],
            },
        ]
        snapshot = _project_snapshot_for_planning()
        self.assertIn("[PROJECT SNAPSHOT]", snapshot)
        self.assertIn("Adpilot", snapshot)
        self.assertIn("Verify deploy checks", snapshot)

    @patch("projects.load_projects")
    @patch("butler.load_mac_state")
    def test_deterministic_project_plan_prefers_current_workspace_project(
        self,
        mock_mac_state,
        mock_load_projects,
    ):
        mock_mac_state.return_value = {
            "cursor_workspace": "/Users/adityatiwari/Desktop/Development/Ai Trade Bot"
        }
        mock_load_projects.return_value = [
            {
                "name": "mac-butler",
                "path": "~/Burry/mac-butler",
                "status": "active",
                "completion": 80,
                "next_tasks": ["Install Piper"],
                "blockers": ["TTS is still weak"],
            },
            {
                "name": "Ai Trade Bot",
                "path": "/Users/adityatiwari/Desktop/Development/Ai Trade Bot",
                "status": "active",
                "completion": 70,
                "next_tasks": [
                    "Run the backend and frontend together",
                    "Manually QA the new Signals desk flow",
                ],
                "blockers": ["Runtime QA is still pending"],
            },
        ]

        plan = _deterministic_project_plan({"raw": {"editor": {"workspace_paths": []}}})

        self.assertEqual(plan["focus"], "Ai Trade Bot")
        self.assertIn("Ai Trade Bot", plan["speech"])
        self.assertIn("Run the backend and frontend together", plan["speech"])
        self.assertEqual(plan["actions"], [])

    @patch("projects.load_projects")
    @patch("butler.load_mac_state")
    @patch("butler._load_memory")
    def test_deterministic_project_plan_avoids_repeating_recent_speech(
        self,
        mock_load_memory,
        mock_mac_state,
        mock_load_projects,
    ):
        recent = (
            "You're already in Ai Trade Bot. Biggest blocker is Runtime QA is still pending. "
            "Start with Run the backend and frontend together, then Manually QA the new Signals desk flow. "
            "Want me to break down the first step?"
        )
        mock_load_memory.return_value = {
            "command_history": [{"speech": recent}],
        }
        mock_mac_state.return_value = {
            "cursor_workspace": "/Users/adityatiwari/Desktop/Development/Ai Trade Bot"
        }
        mock_load_projects.return_value = [
            {
                "name": "Ai Trade Bot",
                "path": "/Users/adityatiwari/Desktop/Development/Ai Trade Bot",
                "status": "active",
                "completion": 70,
                "next_tasks": [
                    "Run the backend and frontend together",
                    "Manually QA the new Signals desk flow",
                ],
                "blockers": ["Runtime QA is still pending"],
            }
        ]

        plan = _deterministic_project_plan({"raw": {"editor": {"workspace_paths": []}}})

        self.assertNotEqual(plan["speech"], recent)
        self.assertNotIn("needs attention", plan["speech"].lower())

    def test_question_needs_brain_agents_for_external_lookup(self):
        self.assertTrue(_question_needs_brain_agents("what is the latest ai news"))
        self.assertTrue(_question_needs_brain_agents("what's on hackernews"))
        self.assertFalse(_question_needs_brain_agents("why did spotify not understand me"))

    def test_direct_agent_plan_for_news_question(self):
        plan = _direct_agent_plan_for_text("what is the latest AI news?")
        self.assertIsNotNone(plan)
        self.assertEqual(plan["actions"][0]["agent"], "news")

    def test_extract_news_topic_maps_air_to_ai(self):
        self.assertEqual(_extract_news_topic("but can you please tell me the latest air news"), "AI")

    def test_direct_agent_plan_for_search_question(self):
        plan = _direct_agent_plan_for_text("what is qwen2.5?")
        self.assertIsNotNone(plan)
        self.assertEqual(plan["actions"][0]["agent"], "search")

    def test_direct_agent_plan_for_hackernews_question(self):
        plan = _direct_agent_plan_for_text("what's on hackernews?")
        self.assertIsNotNone(plan)
        self.assertEqual(plan["actions"][0]["agent"], "hackernews")

    def test_direct_agent_plan_for_reddit_question(self):
        plan = _direct_agent_plan_for_text("what's reddit saying about llms?")
        self.assertIsNotNone(plan)
        self.assertEqual(plan["actions"][0]["agent"], "reddit")

    def test_direct_agent_plan_for_trending_repos(self):
        plan = _direct_agent_plan_for_text("trending repos")
        self.assertIsNotNone(plan)
        self.assertEqual(plan["actions"][0]["agent"], "github_trending")


if __name__ == "__main__":
    unittest.main()
