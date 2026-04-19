#!/usr/bin/env python3

from contextlib import contextmanager
import sys
import unittest
from unittest.mock import MagicMock, patch

import numpy as np

from voice import tts


class TTSVoiceTests(unittest.TestCase):
    def test_shape_for_speech_strips_noise_and_expands_terms(self):
        shaped = tts._shape_for_speech(
            "Hello [[slnc 300]] **LLM** API VPS MCP AI GitHub Gmail YouTube https://example.com/test"
        )
        self.assertNotIn("[[slnc", shaped)
        self.assertNotIn("https://", shaped)
        self.assertIn("L L M", shaped)
        self.assertIn("A P I", shaped)
        self.assertIn("V P S", shaped)
        self.assertIn("M C P", shaped)
        self.assertIn("A I", shaped)
        self.assertIn("Git hub", shaped)
        self.assertIn("G mail", shaped)
        self.assertIn("You tube", shaped)

    @patch("voice.tts._say_fallback")
    @patch("voice.tts._try_edge_tts", return_value=False)
    @patch("voice.tts._try_kokoro", return_value=False)
    def test_speak_falls_back_to_say(self, mock_try_kokoro, mock_try_edge_tts, mock_say_fallback):
        with patch("voice.tts.TTS_ENGINE", "auto"):
            tts.speak("Good morning. mac-butler is ready.")
        mock_try_edge_tts.assert_called_once()
        mock_try_kokoro.assert_called_once()
        mock_say_fallback.assert_called_once()

    @patch("voice.tts._say_fallback")
    @patch("voice.tts._try_edge_tts")
    @patch("voice.tts._try_kokoro")
    def test_speak_skips_when_speech_lock_is_busy(self, mock_try_kokoro, mock_try_edge_tts, mock_say_fallback):
        @contextmanager
        def fake_lock(*_args, **_kwargs):
            yield False

        with patch("voice.tts._speech_lock", fake_lock):
            tts.speak("Good morning. mac-butler is ready.")

        mock_try_edge_tts.assert_not_called()
        mock_try_kokoro.assert_not_called()
        mock_say_fallback.assert_not_called()

    @patch("voice.tts.TTS_ENGINE", "say")
    def test_backend_order_honors_say_only_mode(self):
        self.assertEqual(tts._tts_backend_order(), ("say",))

    @patch("voice.tts.TTS_ENGINE", "edge")
    @patch("voice.tts._edge_tts_available", return_value=True)
    def test_describe_tts_prefers_edge_when_available(self, _mock_available):
        desc = tts.describe_tts()
        self.assertEqual(desc["backend"], "edge")

    @patch("voice.tts.TTS_ENGINE", "nvidia_riva_tts")
    def test_nvidia_tts_fallback_uses_edge_before_kokoro(self):
        order = tts._tts_backend_order()

        self.assertEqual(order[:4], ("nvidia_riva_tts", "edge", "kokoro", "say"))

    @patch("voice.tts._get_kokoro")
    def test_warm_tts_preloads_kokoro_when_assets_exist(self, mock_get_kokoro):
        with patch("voice.tts.TTS_ENGINE", "kokoro"), patch("pathlib.Path.exists", return_value=True):
            self.assertTrue(tts.warm_tts())
        mock_get_kokoro.assert_called_once()

    def test_prepare_kokoro_audio_normalizes_and_downmixes(self):
        shaped = tts._prepare_kokoro_audio(
            np.array(
                [
                    [2.0, -2.0],
                    [np.nan, 0.5],
                    [0.2, 0.4],
                    [0.0, np.inf],
                ],
                dtype=np.float32,
            )
        )

        self.assertEqual(shaped.ndim, 1)
        self.assertEqual(shaped.dtype, np.float32)
        self.assertTrue(np.all(np.isfinite(shaped)))
        self.assertLessEqual(float(np.max(np.abs(shaped))), 0.82)
        self.assertGreater(len(shaped), 4)

    @patch("voice.tts._get_kokoro")
    def test_try_kokoro_plays_audio_when_runtime_is_available(
        self,
        mock_get_kokoro,
    ):
        kokoro = mock_get_kokoro.return_value
        kokoro.create.return_value = ([0.1, 0.2], 24000)
        mock_sd = MagicMock()

        with patch("voice.tts.TTS_ENGINE", "kokoro"), patch("voice.tts.TTS_VOICE", "af_bella"), patch(
            "voice.tts.TTS_SPEED", 1.0
        ), patch("pathlib.Path.exists", return_value=True), patch.dict(sys.modules, {"sounddevice": mock_sd}):
            self.assertTrue(tts._try_kokoro("hello"))

        mock_sd.play.assert_called_once()
        mock_sd.wait.assert_called_once()

    @patch("voice.tts._say_fallback")
    @patch("voice.tts._try_kokoro")
    @patch("voice.tts._try_edge_tts", return_value=True)
    def test_speak_uses_edge_before_fallbacks(self, mock_try_edge_tts, mock_try_kokoro, mock_say_fallback):
        with patch("voice.tts.TTS_ENGINE", "edge"):
            tts.speak("hello")

        mock_try_edge_tts.assert_called_once()
        mock_try_kokoro.assert_not_called()
        mock_say_fallback.assert_not_called()


if __name__ == "__main__":
    unittest.main()
