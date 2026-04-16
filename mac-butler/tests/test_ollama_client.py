import json
import unittest
from unittest.mock import MagicMock, patch

from brain import ollama_client


class OllamaClientTests(unittest.TestCase):
    def test_planner_prompt_lists_new_action_types(self):
        self.assertIn('"type": "open_terminal"', ollama_client.PLANNER_SYSTEM_PROMPT)
        self.assertIn('"type": "open_editor"', ollama_client.PLANNER_SYSTEM_PROMPT)
        self.assertIn('"type": "search_and_play"', ollama_client.PLANNER_SYSTEM_PROMPT)
        self.assertIn('"type": "play_music"', ollama_client.PLANNER_SYSTEM_PROMPT)
        self.assertIn('"in_terminal": true', ollama_client.PLANNER_SYSTEM_PROMPT)
        self.assertIn("[DEPENDENCY GRAPH]", ollama_client.PLANNER_SYSTEM_PROMPT)

    @patch("brain.ollama_client.requests.get")
    def test_get_ollama_url_falls_back_to_local_when_vps_disabled(self, mock_get):
        with patch.object(ollama_client, "USE_VPS_OLLAMA", False):
            url, headers = ollama_client._get_ollama_url()
        self.assertTrue(url.endswith("/api/generate"))
        self.assertEqual(headers, {})
        mock_get.assert_not_called()

    @patch("brain.ollama_client.requests.get")
    @patch("brain.ollama_client.get_ollama_secret")
    def test_get_ollama_url_uses_secret_auth_when_present(self, mock_secret, mock_get):
        response = MagicMock()
        response.status_code = 200
        mock_get.return_value = response
        mock_secret.return_value = {"user": "butler", "password": "secret-pass"}

        with patch.object(ollama_client, "USE_VPS_OLLAMA", True), patch.object(
            ollama_client,
            "VPS_OLLAMA_URL",
            "http://1.2.3.4:8765/ollama",
        ):
            url, headers = ollama_client._get_ollama_url()

        self.assertEqual(url, "http://1.2.3.4:8765/ollama/api/generate")
        self.assertIn("Authorization", headers)

    def test_resolve_backend_model_prefers_vps_override(self):
        with patch.object(ollama_client, "OLLAMA_MODEL", "qwen2.5:14b"), patch.object(
            ollama_client,
            "VPS_OLLAMA_MODEL",
            "llama3.2:3b",
        ):
            result = ollama_client._resolve_backend_model("qwen2.5:14b", True)

        self.assertEqual(result, "llama3.2:3b")

    def test_pick_butler_model_uses_ordered_chain(self):
        def backend_models(backend, force_refresh=False):
            if backend == "local":
                return {
                    "gemma4:e4b": "gemma4:e4b",
                    "deepseek-r1:14b": "deepseek-r1:14b",
                }
            return {}

        with patch.object(ollama_client, "_get_backend_model_map", side_effect=backend_models), patch.object(
            ollama_client,
            "_provider_ready",
            return_value=False,
        ):
            model = ollama_client.pick_butler_model("voice")

        self.assertEqual(model, "ollama_local::gemma4:e4b")

    @patch("brain.ollama_client._call", return_value="fallback voice")
    @patch("brain.ollama_client._get_mlx_voice_backend", return_value=None)
    def test_call_voice_falls_back_to_ollama_when_mlx_is_unavailable(self, _mock_mlx, mock_call):
        result = ollama_client.call_voice(
            "hello",
            "gemma4:e4b",
            temperature=0.4,
            max_tokens=40,
            system="system prompt",
        )

        self.assertEqual(result, "fallback voice")
        mock_call.assert_called_once_with(
            "hello",
            "gemma4:e4b",
            temperature=0.4,
            max_tokens=40,
            system="system prompt",
            timeout_hint="voice",
        )

    @patch("brain.ollama_client._call")
    @patch("brain.ollama_client._get_mlx_voice_backend")
    def test_call_voice_uses_mlx_for_gemma_voice_model(self, mock_mlx, mock_call):
        mock_generate = MagicMock(return_value="mlx voice")
        mock_mlx.return_value = (object(), object(), mock_generate)

        result = ollama_client.call_voice(
            "hello",
            "gemma4:e4b",
            temperature=0.4,
            max_tokens=40,
            system="system prompt",
        )

        self.assertEqual(result, "mlx voice")
        mock_call.assert_not_called()
        mock_generate.assert_called_once()

    @patch("brain.ollama_client._random_greeting", return_value="Morning")
    @patch("brain.ollama_client._get_mood_state", return_value={"name": "focused", "instruction": "Be sharp and direct.", "note": "Locked on the next concrete step."})
    @patch("brain.ollama_client.call_voice")
    @patch("brain.ollama_client._call")
    @patch("brain.ollama_client.read_graph", return_value={"edges": []})
    def test_send_to_ollama_uses_two_stage_flow(self, mock_graph, mock_call, mock_call_voice, _mock_mood, _mock_greeting):
        with patch.object(ollama_client, "USE_VPS_OLLAMA", False):
            mock_call.side_effect = [
                json.dumps(
                    {
                        "focus": "mac-butler executor",
                        "why_now": "Confirmation logic is half wired.",
                        "question": "Jump in?",
                        "actions": [{"type": "play_music", "mode": "focus"}],
                    }
                ),
            ]
            mock_call_voice.return_value = "Morning. mac-butler executor needs the confirmation path finished. Jump in?"

            raw = ollama_client.send_to_ollama("[FOCUS]\n  project: mac-butler")
            result = json.loads(raw)

        self.assertEqual(mock_call.call_count, 1)
        self.assertTrue(mock_call.call_args_list[0].args[1].endswith("gemma4:e4b"))
        self.assertTrue(mock_call_voice.call_args.args[1].endswith("gemma4:e4b"))
        self.assertIn("Current mood: focused", mock_call_voice.call_args.args[0])
        mock_graph.assert_called_once_with()
        self.assertEqual(result["actions"][0]["type"], "play_music")
        self.assertEqual(result["mood"], "focused")
        self.assertTrue(result["speech"].startswith("Morning"))

    @patch("brain.ollama_client._random_greeting", return_value="Morning")
    @patch("brain.ollama_client._get_mood_state", return_value={"name": "focused", "instruction": "Be sharp and direct.", "note": "Locked on the next concrete step."})
    @patch("brain.ollama_client.call_voice", return_value="Morning. Reachout is blocked until LinkedPilot ownership is settled. Want to fix that now?")
    @patch("brain.ollama_client._call")
    @patch(
        "brain.ollama_client.read_graph",
        return_value={
            "edges": [
                {
                    "from": "Reachout",
                    "to": "LinkedPilot",
                    "type": "blocked_by",
                    "note": "Canonical app root still lives under linkedpilot.",
                }
            ]
        },
    )
    def test_send_to_ollama_includes_dependency_graph_context(
        self,
        _mock_graph,
        mock_call,
        _mock_call_voice,
        _mock_mood,
        _mock_greeting,
    ):
        with patch.object(ollama_client, "USE_VPS_OLLAMA", False):
            mock_call.return_value = json.dumps(
                {
                    "focus": "Reachout",
                    "why_now": "Fixing LinkedPilot ownership unblocks Reachout.",
                    "question": "Do it now?",
                    "actions": [],
                }
            )

            ollama_client.send_to_ollama("[PROJECT SNAPSHOT]\n  Reachout: next=Decide canonical product root")

        self.assertIn("[DEPENDENCY GRAPH]", mock_call.call_args.args[0])
        self.assertIn("Reachout is blocked by LinkedPilot", mock_call.call_args.args[0])

    @patch("brain.ollama_client._random_greeting", return_value="Evening")
    @patch("brain.ollama_client.call_voice")
    @patch("brain.ollama_client._call")
    def test_send_to_ollama_falls_back_when_speech_stage_is_empty(
        self,
        mock_call,
        mock_call_voice,
        _mock_greeting,
    ):
        with patch.object(ollama_client, "USE_VPS_OLLAMA", False):
            mock_call.side_effect = [
                json.dumps(
                    {
                        "focus": "vps cleanup",
                        "why_now": "One container looks stale.",
                        "question": "Check it now?",
                        "actions": [],
                    }
                ),
            ]
            mock_call_voice.return_value = ""

            result = json.loads(ollama_client.send_to_ollama("[VPS]\n  stale container"))
        self.assertIn("vps cleanup", result["speech"].lower())
        self.assertTrue(result["speech"].startswith("Evening"))

    @patch("brain.ollama_client._random_greeting", return_value="Morning")
    @patch("brain.ollama_client._call")
    @patch("brain.ollama_client._backend_for_model", return_value="vps")
    def test_send_to_ollama_uses_single_stage_when_vps_backend_is_selected(
        self,
        _mock_backend,
        mock_call,
        _mock_greeting,
    ):
        mock_call.return_value = json.dumps(
            {
                "focus": "mac-butler executor",
                "why_now": "Confirmation logic is half wired.",
                "question": "Jump in?",
                "actions": [],
            }
        )

        with patch.object(ollama_client, "USE_VPS_OLLAMA", True), patch.object(
            ollama_client,
            "VPS_OLLAMA_URL",
            "http://1.2.3.4:8765/ollama",
        ):
            result = json.loads(ollama_client.send_to_ollama("[FOCUS]\n  project: mac-butler"))

        self.assertEqual(mock_call.call_count, 1)
        self.assertIn("mac-butler executor", result["speech"].lower())

    @patch("brain.ollama_client._random_greeting", return_value="Morning")
    @patch("brain.ollama_client.call_voice")
    @patch("brain.ollama_client._call")
    @patch("brain.ollama_client._backend_for_model", return_value="local")
    def test_send_to_ollama_keeps_two_stage_flow_with_local_models_even_if_vps_enabled(
        self,
        _mock_backend,
        mock_call,
        mock_call_voice,
        _mock_greeting,
    ):
        mock_call.return_value = (
            json.dumps(
                {
                    "focus": "Adpilot",
                    "why_now": "Deploy checks still need a pass.",
                    "question": "Open it now?",
                    "actions": [],
                }
            )
        )
        mock_call_voice.return_value = '{"speech":"Morning. Adpilot still needs the deploy checks pass. Open it now?","greeting":"Morning","actions":[]}'

        with patch.object(ollama_client, "USE_VPS_OLLAMA", True):
            result = json.loads(ollama_client.send_to_ollama("[PROJECT SNAPSHOT]\n  Adpilot: next=Verify deploy checks"))

        self.assertEqual(mock_call.call_count, 1)
        self.assertIn("Adpilot", result["speech"])

    @patch("brain.ollama_client._prepare_model_request")
    @patch("brain.ollama_client.requests.post")
    def test_call_ollama_uses_keep_alive_and_reduced_context(
        self,
        mock_post,
        _mock_prepare,
    ):
        response = MagicMock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"response": "ok"}
        mock_post.return_value = response

        result = ollama_client._call_ollama(
            "prompt",
            "test-model",
            temperature=0.3,
            max_tokens=120,
        )

        self.assertEqual(result, "ok")
        payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(payload["keep_alive"], "5m")
        self.assertEqual(payload["options"]["num_ctx"], 2048)
        self.assertEqual(mock_post.call_args.kwargs["timeout"], ollama_client.DEFAULT_TIMEOUT)

    @patch("brain.ollama_client._prepare_model_request")
    @patch("brain.ollama_client.requests.post")
    def test_call_ollama_uses_voice_timeout_hint(
        self,
        mock_post,
        _mock_prepare,
    ):
        response = MagicMock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"response": "ok"}
        mock_post.return_value = response

        result = ollama_client._call_ollama(
            "prompt",
            "test-model",
            temperature=0.3,
            max_tokens=120,
            timeout_hint="voice",
        )

        self.assertEqual(result, "ok")
        self.assertEqual(mock_post.call_args.kwargs["timeout"], ollama_client.VOICE_TIMEOUT)

    @patch("brain.ollama_client._prepare_model_request")
    @patch("brain.ollama_client.requests.post")
    def test_chat_with_ollama_uses_chat_endpoint_and_tools(
        self,
        mock_post,
        _mock_prepare,
    ):
        response = MagicMock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"message": {"role": "assistant", "content": "ok"}}
        mock_post.return_value = response

        result = ollama_client.chat_with_ollama(
            [{"role": "user", "content": "hello"}],
            model="test-model",
            tools=[{"type": "function", "function": {"name": "open_project"}}],
            max_tokens=90,
        )

        self.assertEqual(result["message"]["content"], "ok")
        self.assertTrue(mock_post.call_args.args[0].endswith("/api/chat"))
        payload = mock_post.call_args.kwargs["json"]
        self.assertIn("tools", payload)
        self.assertEqual(payload["keep_alive"], "5m")
        self.assertEqual(payload["options"]["num_ctx"], 4096)
        self.assertEqual(mock_post.call_args.kwargs["timeout"], ollama_client.DEFAULT_TIMEOUT)

    @patch("brain.ollama_client._prepare_model_request")
    @patch("brain.ollama_client.requests.post")
    def test_chat_with_ollama_uses_agent_timeout_hint(
        self,
        mock_post,
        _mock_prepare,
    ):
        response = MagicMock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"message": {"role": "assistant", "content": "ok"}}
        mock_post.return_value = response

        result = ollama_client.chat_with_ollama(
            [{"role": "user", "content": "hello"}],
            model="test-model",
            max_tokens=90,
            timeout_hint="agent",
        )

        self.assertEqual(result["message"]["content"], "ok")
        self.assertEqual(mock_post.call_args.kwargs["timeout"], ollama_client.AGENT_TIMEOUT)

    @patch("brain.ollama_client.requests.get")
    def test_check_vps_connection_returns_dict(self, mock_get):
        response = MagicMock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"models": [{"name": "qwen2.5:14b"}]}
        mock_get.return_value = response

        result = ollama_client.check_vps_connection()

        self.assertIn("status", result)
        self.assertIn("backend", result)
        self.assertIn("models", result)


if __name__ == "__main__":
    unittest.main()
