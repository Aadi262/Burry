#!/usr/bin/env python3

import sys
import unittest
from unittest.mock import MagicMock, patch

from voice import tts


class TTSVoiceTests(unittest.TestCase):
    def test_shape_for_speech_strips_noise_and_expands_terms(self):
        shaped = tts._shape_for_speech(
            "Hello [[slnc 300]] **LLM** API VPS MCP https://example.com/test"
        )
        self.assertNotIn("[[slnc", shaped)
        self.assertNotIn("https://", shaped)
        self.assertIn("L L M", shaped)
        self.assertIn("A P I", shaped)
        self.assertIn("V P S", shaped)
        self.assertIn("M C P", shaped)

    @patch("voice.tts._say_fallback")
    @patch("voice.tts._try_kokoro", return_value=False)
    def test_speak_falls_back_to_say(self, mock_try_kokoro, mock_say_fallback):
        tts.speak("Good morning. mac-butler is ready.")
        mock_try_kokoro.assert_called_once()
        mock_say_fallback.assert_called_once()

    @patch("voice.tts.TTS_ENGINE", "say")
    def test_try_kokoro_skips_when_engine_forces_say(self):
        self.assertFalse(tts._try_kokoro("hello"))

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


if __name__ == "__main__":
    unittest.main()
