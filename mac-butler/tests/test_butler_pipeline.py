import unittest
from unittest.mock import patch

from brain.ollama_client import _strip_repeated_project_from_task
from butler import (
    _brain_context_text,
    _clear_pending_dialogue,
    _conversation_context_text,
    _contextualize_action,
    _deterministic_project_plan,
    _extract_news_topic,
    _direct_agent_plan_for_text,
    _looks_like_followup_reference,
    _maybe_add_info_followup,
    _normalize_response,
    _plan_with_brain,
    _project_snapshot_for_planning,
    _question_needs_brain_agents,
    _recent_dialogue_context,
    _remember_conversation_turn,
    _resolve_followup_text,
    _rewrite_speech_with_agent_results,
    _resolve_pending_dialogue,
    _run_actions_with_response,
    _tool_chat_response,
    _should_use_brain_for_unknown,
    _startup_session_hint,
    _unknown_brain_response,
    _unknown_response_for_text,
    observe_and_followup,
    get_quick_response,
    reset_conversation_context,
)
from intents.router import IntentResult


class ButlerPipelineTests(unittest.TestCase):
    def tearDown(self):
        _clear_pending_dialogue()
        reset_conversation_context()

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

    def test_unknown_response_defaults_to_empty_for_substantive_text(self):
        self.assertEqual(_unknown_response_for_text("you are integrating that"), "")

    def test_should_use_brain_for_unknown_dialogue_followup(self):
        self.assertTrue(_should_use_brain_for_unknown("you are integrating that"))
        self.assertFalse(_should_use_brain_for_unknown("bye"))

    @patch("butler.load_runtime_state")
    def test_recent_dialogue_context_uses_runtime_state(self, mock_runtime):
        mock_runtime.return_value = {
            "last_heard_text": "what are you doing",
            "last_spoken_text": "Working on integrating AI Trade Bot into mac-butler.",
        }
        context = _recent_dialogue_context()
        self.assertIn("Last heard command", context)
        self.assertIn("Last Butler reply", context)

    def test_recent_dialogue_context_prefers_session_conversation(self):
        _remember_conversation_turn(
            "latest news in india",
            "news",
            "India inflation cooled and elections are dominating headlines.",
        )
        context = _recent_dialogue_context()
        self.assertIn("[CONVERSATION]", context)
        self.assertIn("latest news in india", context)

    def test_followup_reference_detection(self):
        self.assertTrue(_looks_like_followup_reference("you are integrating that"))
        self.assertTrue(_looks_like_followup_reference("what about it"))
        self.assertFalse(_looks_like_followup_reference("open spotify"))

    @patch("butler._raw_llm", return_value="latest news in iran war")
    def test_resolve_followup_text_uses_session_conversation(self, _mock_llm):
        _remember_conversation_turn(
            "latest news in iran war",
            "news",
            "Missile exchanges intensified overnight.",
        )
        resolved = _resolve_followup_text("what about that")
        self.assertEqual(resolved, "latest news in iran war")

    def test_run_actions_with_response_test_mode_remembers_turn(self):
        response, results = _run_actions_with_response(
            text="open google sheet",
            response="Opening Google Sheet.",
            actions=[],
            intent_name="open_app",
            test_mode=True,
        )
        self.assertEqual(response, "Opening Google Sheet.")
        self.assertEqual(results, [])
        self.assertIn("Opening Google Sheet.", _conversation_context_text())

    @patch("butler._raw_llm", return_value="Yes. Integrating AI Trade Bot into mac-butler right now.")
    @patch("butler.build_structured_context", return_value={"formatted": "[FOCUS]\n  project: mac-butler"})
    @patch(
        "butler.load_runtime_state",
        return_value={
            "last_heard_text": "what are you doing",
            "last_spoken_text": "Working on integrating AI Trade Bot into mac-butler.",
        },
    )
    def test_unknown_brain_response_uses_recent_dialogue_context(
        self,
        _mock_runtime,
        _mock_context,
        _mock_llm,
    ):
        response = _unknown_brain_response("you are integrating that")
        self.assertIn("Integrating AI Trade Bot", response)

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
    @patch("agents.runner.run_agent_async")
    @patch("butler.executor.run")
    def test_run_actions_with_response_returns_immediate_voice_for_run_agent_only(
        self,
        mock_run,
        mock_run_agent_async,
        mock_speak_or_print,
        _mock_record,
    ):
        final_response, results = _run_actions_with_response(
            text="trending repos",
            response="Checking trending repos.",
            actions=[{"type": "run_agent", "agent": "github_trending", "language": "python"}],
            test_mode=False,
        )

        self.assertEqual(final_response, "Checking trending repos.")
        self.assertEqual(results[0]["status"], "queued")
        mock_run_agent_async.assert_called_once()
        mock_run.assert_not_called()
        mock_speak_or_print.assert_called_once_with(
            "Checking trending repos.",
            test_mode=False,
        )

    @patch("butler._record")
    @patch("butler._speak_or_print")
    @patch("agents.runner.run_agent_async")
    @patch("butler.executor.run")
    def test_run_actions_with_response_queues_agents_in_background(
        self,
        mock_executor_run,
        mock_run_agent_async,
        mock_speak_or_print,
        mock_record,
    ):
        final_response, results = _run_actions_with_response(
            text="latest ai news",
            response="Checking the latest AI news.",
            actions=[{"type": "run_agent", "agent": "news", "topic": "AI"}],
            test_mode=False,
            intent_name="question",
        )

        self.assertEqual(final_response, "Checking the latest AI news.")
        self.assertEqual(results[0]["status"], "queued")
        mock_run_agent_async.assert_called_once()
        mock_executor_run.assert_not_called()
        mock_speak_or_print.assert_called_once_with("Checking the latest AI news.", test_mode=False)
        mock_record.assert_called_once()

    def test_brain_context_text_includes_request_and_hint(self):
        ctx = {"formatted": "[FOCUS]\n  project: mac-butler"}
        text = _brain_context_text(ctx, "check latest AI news")
        self.assertIn("[CURRENT REQUEST]", text)
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

    def test_brain_context_text_includes_recent_conversation_before_request(self):
        _remember_conversation_turn(
            "open mac-butler",
            "open_project",
            "Opening mac-butler.",
        )
        _remember_conversation_turn(
            "now run the tests",
            "shell",
            "Running the test suite.",
        )
        ctx = {"formatted": "[FOCUS]\n  project: mac-butler"}
        text = _brain_context_text(ctx, "what failed?")
        self.assertIn("[RECENT CONVERSATION]", text)
        self.assertIn("USER: open mac-butler", text)
        self.assertIn("BURRY: Running the test suite.", text)
        self.assertLess(text.index("[RECENT CONVERSATION]"), text.index("[CURRENT REQUEST]"))

    @patch("butler.note_tool_finished")
    @patch("butler.note_memory_recall")
    @patch("butler.note_tool_started")
    @patch("memory.store.semantic_search", return_value=[{"timestamp": "2026-04-06T12:00:00", "speech": "Decided JWT, no sessions.", "score": 0.91}])
    @patch("brain.ollama_client.chat_with_ollama")
    def test_tool_chat_response_executes_recall_memory_before_final_reply(
        self,
        mock_chat,
        _mock_semantic,
        mock_tool_started,
        mock_memory_recall,
        mock_tool_finished,
    ):
        mock_chat.side_effect = [
            {
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "function": {
                                "name": "recall_memory",
                                "arguments": {"query": "auth decision"},
                            }
                        }
                    ],
                }
            },
            {
                "message": {
                    "role": "assistant",
                    "content": "We already chose JWT over sessions.",
                }
            },
        ]

        result = _tool_chat_response("what did we decide about auth", {"formatted": "[FOCUS]\n  project: mac-butler"})

        self.assertEqual(result["speech"], "We already chose JWT over sessions.")
        self.assertEqual(result["actions"][0]["type"], "recall_memory")
        self.assertEqual(result["results"][0]["status"], "ok")
        mock_tool_started.assert_called_once()
        mock_memory_recall.assert_called_once()
        mock_tool_finished.assert_called_once()

    @patch("butler.note_tool_finished")
    @patch("butler.note_tool_started")
    @patch(
        "browser.agent.BrowsingAgent.search",
        return_value={
            "status": "ok",
            "result": "Claude 4.5 lowered enterprise cost and improved context handling.",
            "data": {"tool": "browser_search", "sources": ["searxng"]},
        },
    )
    @patch("brain.ollama_client.chat_with_ollama")
    def test_tool_chat_response_executes_browse_web_via_browser_agent(
        self,
        mock_chat,
        _mock_search,
        mock_tool_started,
        mock_tool_finished,
    ):
        mock_chat.side_effect = [
            {
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "function": {
                                "name": "browse_web",
                                "arguments": {"query": "what is the new product from claude"},
                            }
                        }
                    ],
                }
            },
            {
                "message": {
                    "role": "assistant",
                    "content": "Claude 4.5 lowered enterprise cost and improved context handling.",
                }
            },
        ]

        result = _tool_chat_response(
            "what is the new product from claude",
            {"formatted": "[FOCUS]\n  project: mac-butler"},
        )

        self.assertIn("Claude 4.5", result["speech"])
        self.assertEqual(result["actions"][0]["type"], "browse_web")
        self.assertEqual(result["results"][0]["action"], "browse_web")
        mock_tool_started.assert_called_once()
        mock_tool_finished.assert_called_once()

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
    @patch("butler.get_active_tasks", return_value=[])
    def test_deterministic_project_plan_prefers_current_workspace_project(
        self,
        _mock_tasks,
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
    @patch("butler.get_active_tasks", return_value=[])
    def test_deterministic_project_plan_filters_stale_startup_setup_tasks(
        self,
        _mock_tasks,
        mock_mac_state,
        mock_load_projects,
    ):
        mock_mac_state.return_value = {"cursor_workspace": "/Users/adityatiwari/Burry/mac-butler"}
        mock_load_projects.return_value = [
            {
                "name": "mac-butler",
                "path": "/Users/adityatiwari/Burry/mac-butler",
                "status": "active",
                "completion": 84,
                "next_tasks": [
                    "Configure Brave MCP and GitHub MCP secrets.",
                    "Install and wire a real local neural TTS backend.",
                    "Upgrade live STT to a stronger local path.",
                ],
                "blockers": ["Voice follow-up is still weaker than the main TTS path."],
            }
        ]

        plan = _deterministic_project_plan({"raw": {"editor": {"workspace_paths": []}}})

        self.assertIn("Upgrade live STT", plan["speech"])
        self.assertNotIn("Brave M C P", plan["speech"])

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

    def test_extract_news_topic_strips_leading_preposition(self):
        self.assertEqual(_extract_news_topic("can you tell me latest news on iran and us"), "iran and us")

    @patch("butler.get_last_session_summary", return_value='Last active: Sun 18:53\nRequest: "latest news on google gemma"')
    def test_startup_session_hint_uses_last_request(self, _mock_summary):
        self.assertIn("Last time you asked about", _startup_session_hint())

    def test_direct_agent_plan_for_search_question(self):
        plan = _direct_agent_plan_for_text("what is qwen2.5?")
        self.assertIsNotNone(plan)
        self.assertEqual(plan["actions"][0]["agent"], "search")

    def test_direct_agent_plan_for_url_fetch_question(self):
        plan = _direct_agent_plan_for_text("read this article https://example.com/post")
        self.assertIsNotNone(plan)
        self.assertEqual(plan["actions"][0]["agent"], "fetch")

    def test_info_followup_is_added_for_news_and_search(self):
        self.assertTrue(_maybe_add_info_followup("Gemma 4 just launched.", "news").endswith("Want more?"))
        self.assertEqual(_maybe_add_info_followup("Opening Gmail compose.", "open_app"), "Opening Gmail compose.")

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
