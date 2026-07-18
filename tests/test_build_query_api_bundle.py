import json
import tempfile
import unittest
from pathlib import Path

from pipeline.publish.build_query_api_bundle import build_bundle
from tests.query_api_fixtures import build_active_query_release


class BuildQueryApiBundleTest(unittest.TestCase):
    def test_bundles_only_active_pointer_and_query_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            pointer, query_runs = build_active_query_release(root)
            out_dir = root / "bundle"
            result = build_bundle(
                active_pointer=pointer,
                query_runs_dir=query_runs,
                out_dir=out_dir,
            )
            bundled_pointer = json.loads(
                (out_dir / "data/processed/graph_payload_active.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(result["release_id"], "test_run:r1")
            self.assertEqual(bundled_pointer["run_id"], "test_run")
            self.assertTrue(
                (out_dir / "data/processed/query_api_runs/test_run/public_api.duckdb").is_file()
            )


if __name__ == "__main__":
    unittest.main()
