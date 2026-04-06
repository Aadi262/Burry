#!/usr/bin/env python3

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from agents import vision


class VisionTests(unittest.TestCase):
    @patch("agents.vision.pick_butler_model", return_value="gemma4:e4b")
    @patch("agents.vision.chat_with_ollama", return_value={"message": {"content": "Terminal and editor are open."}})
    @patch("agents.vision.subprocess.run")
    def test_describe_screen_prefers_vision_model_chain(self, mock_run, mock_chat, mock_pick):
        mock_run.return_value = MagicMock(returncode=0)
        with tempfile.TemporaryDirectory() as tempdir:
            screenshot = Path(tempdir) / "screen.png"
            screenshot.write_bytes(b"fake-image")
            with patch.object(vision, "SCREENSHOT_PATH", screenshot):
                result = vision.describe_screen("what is on the screen")

        self.assertEqual(result, "Terminal and editor are open.")
        mock_pick.assert_called_once_with("vision", override=None)
        mock_chat.assert_called_once()


if __name__ == "__main__":
    unittest.main()
