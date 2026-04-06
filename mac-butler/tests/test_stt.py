#!/usr/bin/env python3

import unittest
from unittest.mock import patch

from voice import stt


class STTTests(unittest.TestCase):
    @patch("voice.stt.VOICE_INPUT_MODEL", "mlx-community/whisper-tiny")
    def test_candidate_mlx_model_repos_normalize_configured_model(self):
        repos = stt._candidate_mlx_model_repos()
        self.assertEqual(repos[0], "mlx-community/whisper-tiny-mlx")
        self.assertIn("mlx-community/whisper-small-mlx", repos)

    def test_normalize_transcript_fixes_common_voice_aliases(self):
        cleaned = stt._normalize_transcript("search bhuvan bam you do and open g mail")
        self.assertIn("youtube", cleaned)
        self.assertIn("gmail", cleaned)

    @patch("voice.stt.VOICE_INPUT_BEAM_SIZE", 3)
    def test_requested_beam_size_is_clamped(self):
        self.assertEqual(stt._requested_beam_size(), 3)

    @patch("voice.stt._recent_speech_snapshot", return_value=("Checking the latest news.", 100.0))
    @patch("voice.stt.time.monotonic", return_value=101.0)
    def test_strip_recent_speech_echo_removes_butler_prefix(self, _mock_time, _mock_snapshot):
        cleaned = stt._strip_recent_speech_echo(
            "checking the latest news but can you please tell me the latest air news"
        )
        self.assertEqual(cleaned, "but can you please tell me the latest ai news")

    @patch("voice.stt._recent_speech_snapshot", return_value=("Checking the latest news.", 100.0))
    @patch("voice.stt.time.monotonic", return_value=109.5)
    def test_strip_recent_speech_echo_ignores_old_speech(self, _mock_time, _mock_snapshot):
        cleaned = stt._strip_recent_speech_echo("checking the latest news")
        self.assertEqual(cleaned, "checking the latest news")


if __name__ == "__main__":
    unittest.main()
