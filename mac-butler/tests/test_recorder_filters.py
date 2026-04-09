import threading
import unittest
from unittest.mock import Mock, patch

from pipeline import recorder


class _StubConversation:
    def __init__(self):
        self.turns = []

    def add_turn(self, heard, intent, spoken):
        self.turns.append({"heard": heard, "intent": intent, "spoken": spoken})


def _stub_butler():
    stub = Mock()
    stub._LEARNING_TRACE_LOCK = threading.Lock()
    stub._CONVERSATION_LOCK = threading.Lock()
    stub._LAST_RESOLVED_COMMAND = {}
    stub._SESSION_CONVERSATION = _StubConversation()
    stub.ctx = Mock()
    stub.note_conversation_turns = Mock()
    stub._bus_record = Mock()
    stub.add_to_working_memory = Mock()
    stub.record_episode_with_agentscope_feedback = Mock()
    stub.record_session = Mock()
    stub.save_session = Mock()
    stub.append_to_index = Mock()
    stub.record_project_execution = Mock(return_value={})
    stub.analyze_and_learn = Mock()
    stub.observe_project_relationships = Mock()
    return stub


class RecorderFilterTests(unittest.TestCase):
    @patch.dict("os.environ", {"PYTEST_CURRENT_TEST": ""}, clear=False)
    @patch("pipeline.recorder._butler")
    def test_low_signal_fallback_is_not_learned(self, mock_butler):
        stub = _stub_butler()
        mock_butler.return_value = stub

        recorder._record(
            "search weather in mumbai",
            "I didn't catch that. Say open, search, compose mail, or latest news.",
            [],
            intent_name="unknown",
        )

        stub._bus_record.assert_not_called()
        stub.note_conversation_turns.assert_not_called()
        stub.add_to_working_memory.assert_not_called()
        stub.record_episode_with_agentscope_feedback.assert_not_called()
        stub.record_session.assert_not_called()
        stub.save_session.assert_not_called()
        stub.append_to_index.assert_not_called()
        stub.record_project_execution.assert_not_called()
        stub.analyze_and_learn.assert_not_called()
        stub.observe_project_relationships.assert_not_called()

    @patch.dict("os.environ", {"PYTEST_CURRENT_TEST": ""}, clear=False)
    @patch("pipeline.recorder._butler")
    def test_normal_response_still_records_learning(self, mock_butler):
        stub = _stub_butler()
        mock_butler.return_value = stub

        recorder._record(
            "check my vps",
            "CPU is healthy and memory is stable.",
            [{"type": "run_agent", "agent": "vps"}],
            results=[{"status": "ok", "result": "CPU is healthy and memory is stable."}],
            intent_name="vps_status",
        )

        stub._bus_record.assert_called_once()
        stub.note_conversation_turns.assert_called_once()
        stub.record_session.assert_called_once()
        stub.save_session.assert_called_once()
        stub.record_project_execution.assert_called_once()
        stub.analyze_and_learn.assert_called_once()
        stub.observe_project_relationships.assert_called_once()


if __name__ == "__main__":
    unittest.main()
