import unittest
from types import SimpleNamespace
from unittest.mock import patch

import butler
from agents import runner
from capabilities.contracts import (
    CONTRACT_VERSION,
    ApiError,
    ApiResponse,
    CapabilityDescriptor,
    ClassifierResult,
    CommandRequest,
    CommandResult,
    HudEventEnvelope,
    PendingState,
    ToolInvocation,
    ToolResult,
    ToolSpec,
)
from memory import knowledge_base
from projects import dashboard
from state import State


class Phase2QuickWinTests(unittest.TestCase):
    def tearDown(self):
        butler._clear_pending_command_state()
        butler._invalidate_context_cache()
        butler.state.transition(State.IDLE)

    def test_context_cache_ttl_is_120_seconds(self):
        self.assertEqual(butler._CTX_CACHE_TTL_SECONDS, 120.0)

    @patch("butler.build_structured_context", return_value={"formatted": "[FOCUS]\n  project: mac-butler"})
    def test_context_cache_reuses_single_build(self, mock_build):
        butler._invalidate_context_cache()

        first = butler._get_cached_context()
        second = butler._get_cached_context()

        self.assertEqual(first, second)
        mock_build.assert_called_once()

    def test_handle_input_reuses_early_route_result(self):
        intent = SimpleNamespace(name="unknown", params={}, confidence=0.61)
        with patch("butler._ensure_watcher_started"), \
             patch("butler.route", return_value=intent) as mock_route, \
             patch("butler._resolve_pending_dialogue", return_value=None), \
             patch("butler._looks_like_followup_reference", return_value=False), \
             patch("butler._handle_meta_intent", return_value=False), \
             patch("butler._unknown_response_for_text", return_value="Handled."), \
             patch("butler._reply_without_action") as mock_reply:
            butler.handle_input("something odd", test_mode=True)

        self.assertEqual(mock_route.call_count, 1)
        mock_reply.assert_called_once()

    def test_embedding_dimensions_are_static(self):
        self.assertEqual(knowledge_base._detect_embedding_dimensions(), 768)

    @patch("agents.runner._check_memory")
    def test_prepare_model_request_only_checks_memory(self, mock_check_memory):
        runner._prepare_model_request("gemma4:e4b")
        mock_check_memory.assert_called_once()

    def test_dashboard_stream_interval_is_half_second(self):
        self.assertEqual(dashboard.STREAM_INTERVAL_SECONDS, 0.5)

    def test_command_request_and_result_preserve_contract_version(self):
        request = CommandRequest.from_dict({"text": "open terminal", "source": "hud", "timeout": "3"})
        result = CommandResult(status="accepted", data={"text": request.text}).to_dict()

        self.assertEqual(request.contract_version, CONTRACT_VERSION)
        self.assertEqual(request.timeout, 3.0)
        self.assertEqual(result["contract_version"], CONTRACT_VERSION)
        self.assertEqual(result["data"]["text"], "open terminal")
        self.assertEqual(result["text"], "open terminal")

    def test_hud_event_envelope_keeps_data_and_legacy_payload(self):
        envelope = HudEventEnvelope(type="operator", data={"state": "listening"}).to_dict()

        self.assertEqual(envelope["event_version"], CONTRACT_VERSION)
        self.assertEqual(envelope["type"], "operator")
        self.assertEqual(envelope["data"], {"state": "listening"})
        self.assertEqual(envelope["payload"], {"state": "listening"})

    def test_api_response_and_error_are_versioned(self):
        response = ApiResponse(kind="operator", data={"state": "idle"}).to_dict()
        error = ApiError(error="Not found", status=404, code="not_found").to_dict()

        self.assertEqual(response["contract_version"], CONTRACT_VERSION)
        self.assertEqual(response["kind"], "operator")
        self.assertEqual(response["data"]["state"], "idle")
        self.assertEqual(error["contract_version"], CONTRACT_VERSION)
        self.assertEqual(error["status"], 404)
        self.assertEqual(error["code"], "not_found")

    def test_phase2_dtos_cover_tool_pending_and_classifier_shapes(self):
        spec = ToolSpec(
            name="open_terminal",
            action_type="open_terminal",
            kind="control",
            description="Open Terminal",
        )
        descriptor = CapabilityDescriptor.from_tool_spec("T01", spec).to_dict()
        invocation = ToolInvocation(tool="open_terminal", args={"profile": "default"}, capability_id="T01").to_dict()
        result = ToolResult(tool="open_terminal", status="ok", capability_id="T01").to_dict()
        pending = PendingState(active=True, kind="email", next_field="subject").to_dict()
        classifier = ClassifierResult(intent="open_app", confidence=0.91).to_dict()

        self.assertEqual(descriptor["capability_id"], "T01")
        self.assertEqual(invocation["capability_id"], "T01")
        self.assertEqual(result["capability_id"], "T01")
        self.assertEqual(pending["next_field"], "subject")
        self.assertEqual(classifier["intent"], "open_app")


if __name__ == "__main__":
    unittest.main()
