import tempfile
import unittest
from pathlib import Path

from pipeline.extract.io_utils import read_jsonl
from pipeline.extract.run_route_extraction_batch_api import append_unique_jsonl


class RouteExtractionBatchApiTest(unittest.TestCase):
    def test_error_to_success_retry_is_appended_but_reparse_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "outputs.jsonl"
            schema_error = {
                "task_id": "task-one",
                "route_id": "route-one",
                "status": "schema_error",
            }
            success = {
                "task_id": "task-one",
                "route_id": "route-one",
                "input_fingerprint": "a" * 64,
                "status": "ok",
            }

            self.assertEqual(append_unique_jsonl(path, [schema_error]), 1)
            self.assertEqual(append_unique_jsonl(path, [success]), 1)
            self.assertEqual(append_unique_jsonl(path, [success]), 0)
            rows = read_jsonl(path)

        self.assertEqual([row["status"] for row in rows], ["schema_error", "ok"])


if __name__ == "__main__":
    unittest.main()
