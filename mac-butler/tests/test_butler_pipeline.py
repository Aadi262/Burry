import unittest
from unittest.mock import patch

from brain.ollama_client import _strip_repeated_project_from_task
from butler import (
    _brain_context_text,
    _clear_pending_dialogue,
    _contextualize_action,
    _direct_agent_plan_for_text,
    _normalize_response,
    _plan_with_brain,
    _question_needs_brain_agents,
    _resolve_pending_dialogue,
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

    def test_brain_context_text_includes_request_and_hint(self):
        ctx = {"formatted": "[FOCUS]\n  project: mac-butler"}
        text = _brain_context_text(ctx, "check latest AI news")
        self.assertIn("[USER REQUEST]", text)
        self.assertIn("run_agent", text)

    def test_question_needs_brain_agents_for_external_lookup(self):
        self.assertTrue(_question_needs_brain_agents("what is the latest ai news"))
        self.assertFalse(_question_needs_brain_agents("why did spotify not understand me"))

    def test_direct_agent_plan_for_news_question(self):
        plan = _direct_agent_plan_for_text("what is the latest AI news?")
        self.assertIsNotNone(plan)
        self.assertEqual(plan["actions"][0]["agent"], "news")

    def test_direct_agent_plan_for_search_question(self):
        plan = _direct_agent_plan_for_text("what is qwen2.5?")
        self.assertIsNotNone(plan)
        self.assertEqual(plan["actions"][0]["agent"], "search")


if __name__ == "__main__":
    unittest.main()
