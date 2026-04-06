import unittest

from utils import _clip_text, _compress_text


class UtilsTests(unittest.TestCase):
    def test_clip_text_trims_long_values(self):
        self.assertEqual(_clip_text("x" * 10, limit=8), "xxxxx...")

    def test_compress_text_preserves_headers_and_shortens_commit_lines(self):
        raw = "[TASK LIST]\nabcdef1 Ship the dashboard utility cleanup\nThis line is intentionally long so it gets clipped in the shared compressor helper.\n"

        compressed = _compress_text(raw, limit=500, line_limit=40)

        self.assertIn("[TASK LIST]", compressed)
        self.assertIn("commit: Ship the dashboard utility cleanup", compressed)
        self.assertIn("This line is intentionally long so it ge...", compressed)


if __name__ == "__main__":
    unittest.main()
