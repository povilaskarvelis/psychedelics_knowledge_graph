from argparse import Namespace
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pipeline.fulltext.start_grobid import replace_scalar, start_container


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

    @patch("pipeline.fulltext.start_grobid.wait_until_alive", return_value=True)
    @patch("pipeline.fulltext.start_grobid.run")
    def test_container_port_is_bound_to_loopback(
        self, mocked_run, _mocked_wait
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config = Path(tmpdir) / "grobid.yaml"
            config.write_text("grobid: {}\n", encoding="utf-8")
            args = Namespace(
                recreate_config=False,
                config=config,
                image="grobid/grobid:test",
                concurrency=1,
                pdfalto_memory_mb=2048,
                container="test-grobid",
                memory="5g",
                wait_sec=1,
            )

            start_container(args)

        docker_run = mocked_run.call_args_list[1].args[0]
        port_index = docker_run.index("-p") + 1
        self.assertEqual(docker_run[port_index], "127.0.0.1:8070:8070")


if __name__ == "__main__":
    unittest.main()
