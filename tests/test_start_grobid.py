import tempfile
import unittest
from pathlib import Path

from pipeline.fulltext.start_grobid import replace_scalar


class StartGrobidTest(unittest.TestCase):
    def test_replace_scalar_updates_first_matching_key_preserving_indent(self) -> None:
        text = "grobid:\n  concurrency: 10\n  pdf:\n    pdfalto:\n      memoryLimitMb: 6096\n"

        text = replace_scalar(text, "concurrency", 1)
        text = replace_scalar(text, "memoryLimitMb", 2048)

        self.assertIn("  concurrency: 1", text)
        self.assertIn("      memoryLimitMb: 2048", text)
        self.assertNotIn("concurrency: 10", text)
        self.assertNotIn("memoryLimitMb: 6096", text)

    def test_replace_scalar_raises_for_missing_key(self) -> None:
        with self.assertRaises(ValueError):
            replace_scalar("grobid:\n  concurrency: 10\n", "missingKey", 1)


if __name__ == "__main__":
    unittest.main()
