import unittest
from unittest.mock import patch

import butler as butler_module
import pipeline.router as router_module
from brain.conversation import CONVERSATION_MODEL, CONVERSATION_SYSTEM, conversation_messages, generate_conversation_reply
from brain.session_context import ctx
from intents.router import IntentResult
from state import State


class ConversationModeTests(unittest.TestCase):
    def tearDown(self):
        ctx.reset()
        butler_module.state.transition(State.IDLE)

    def test_conversation_messages_use_last_eight_turns(self):
        ctx.reset()
        for index in range(10):
            ctx.add_user(f"user {index}")
            ctx.add_butler(f"butler {index}")

        messages = conversation_messages("fresh prompt", turn_limit=8)

        self.assertEqual(messages[0]["role"], "system")
        self.assertEqual(messages[0]["content"], CONVERSATION_SYSTEM)
        self.assertEqual(len(messages[1:]), 9)
        self.assertEqual(messages[1]["content"], "user 6")
        self.assertEqual(messages[-2]["content"], "butler 9")
        self.assertEqual(messages[-1]["content"], "fresh prompt")

    @patch("brain.conversation.chat_with_ollama")
    def test_generate_conversation_reply_uses_configured_temperature(self, mock_chat):
        mock_chat.return_value = {"message": {"content": "Adpilot should own the event pipeline first."}}

        reply = generate_conversation_reply("brainstorm adpilot")

        self.assertEqual(reply, "Adpilot should own the event pipeline first.")
        self.assertEqual(mock_chat.call_args.args[1], CONVERSATION_MODEL)
        self.assertEqual(mock_chat.call_args.kwargs["temperature"], 0.7)

    @patch("brain.conversation.generate_conversation_reply", return_value="Adpilot needs a tighter event bus first.")
    @patch("pipeline.router.plan_semantic_task", return_value=None)
    @patch("pipeline.router._run_skill_match", return_value=False)
    @patch(
        "pipeline.router._route_initial_intent",
        return_value=IntentResult(
            "conversation",
            {"topic": "adpilot architecture"},
            0.92,
            "let's brainstorm adpilot architecture",
        ),
    )
    @patch("butler._record")
    @patch("butler._speak_or_print")
    def test_handle_input_routes_conversation_through_conversation_module(
        self,
        mock_speak,
        _mock_record,
        _mock_route,
        _mock_skill,
        _mock_semantic,
        mock_conversation,
    ):
        butler_module.state.transition(State.IDLE)

        router_module.handle_input("let's brainstorm adpilot architecture", test_mode=True)

        mock_conversation.assert_called_once_with("let's brainstorm adpilot architecture")
        mock_speak.assert_called_once_with("Adpilot needs a tighter event bus first.", test_mode=True)


if __name__ == "__main__":
    unittest.main()
