import tempfile
import unittest
import json
from pathlib import Path
from unittest import mock

import pandas as pd

from pipeline.publish import promote_routed_run as promotion


class PromoteRoutedRunTest(unittest.TestCase):
    @staticmethod
    def write_corpus_release(path: Path, run_id: str, release_id: str = "") -> None:
        pd.DataFrame(
            [
                {
                    "graph_inclusion_run_id": run_id,
                    "graph_inclusion_release_id": release_id,
                }
            ]
        ).to_parquet(path, index=False)

    def test_pointer_pair_requires_same_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            extraction = root / "active_extraction.json"
            graph = root / "active_graph.json"
            extraction.write_text('{"run_id":"new_run"}', encoding="utf-8")
            graph.write_text(
                '{"kg_dir":"data/processed/kg_routed_runs/old_run"}', encoding="utf-8"
            )
            corpus = root / "candidate_papers.parquet"
            self.write_corpus_release(corpus, "old_run")
            with mock.patch.object(promotion, "ACTIVE_EXTRACTION_POINTER", extraction), mock.patch.object(
                promotion, "ACTIVE_GRAPH_POINTER", graph
            ), mock.patch.object(promotion, "CANDIDATE_PAPERS_TABLE", corpus):
                with self.assertRaisesRegex(ValueError, "Active release mismatch"):
                    promotion.validate_active_pointer_pair()

    def test_pointer_pair_requires_same_release_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            extraction = root / "active_extraction.json"
            graph = root / "active_graph.json"
            extraction.write_text(
                '{"run_id":"same_run","release_id":"release-a"}', encoding="utf-8"
            )
            graph.write_text(
                '{"run_id":"same_run","release_id":"release-b"}', encoding="utf-8"
            )
            corpus = root / "candidate_papers.parquet"
            self.write_corpus_release(corpus, "same_run", "release-b")
            with mock.patch.object(promotion, "ACTIVE_EXTRACTION_POINTER", extraction), mock.patch.object(
                promotion, "ACTIVE_GRAPH_POINTER", graph
            ), mock.patch.object(promotion, "CANDIDATE_PAPERS_TABLE", corpus):
                with self.assertRaisesRegex(ValueError, "release IDs differ"):
                    promotion.validate_active_pointer_pair()

    def test_generated_pointers_share_release_and_run(self) -> None:
        release_id = "candidate:abc123"
        graph = promotion.graph_pointer_for_run("candidate", release_id)
        with tempfile.TemporaryDirectory(dir=promotion.ROOT) as tmpdir:
            root = Path(tmpdir)
            outputs = root / "outputs.jsonl"
            evidence = root / "evidence.json"
            outputs.touch()
            evidence.touch()
            extraction = promotion.extraction_pointer_for_run(
                run_id="candidate",
                release_id=release_id,
                graph_pointer=graph,
                outputs_jsonl=outputs,
                evidence_rows_json=evidence,
                source_update_manifest=None,
            )

        self.assertEqual(extraction["run_id"], graph["run_id"])
        self.assertEqual(extraction["release_id"], graph["release_id"])
        self.assertEqual(extraction["kg_dir"], graph["kg_dir"])
        self.assertEqual(extraction["graph_payload_manifest"], graph["active_manifest"])

    def test_methods_manifest_does_not_retain_staging_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            staged = root / "stage"
            current = root / "current"
            manifest = staged / "manifests" / "build_manifest.json"
            manifest.parent.mkdir(parents=True)
            manifest.write_text(
                json.dumps(
                    {
                        "outputs": {"manifest": str(manifest)},
                        "input_files": [str((root / "staged_candidate.parquet").resolve())],
                    }
                ),
                encoding="utf-8",
            )

            staged_candidate = root / "staged_candidate.parquet"
            current_candidate = root / "candidate_papers.parquet"
            promotion.retarget_methods_manifest(
                staged,
                current,
                staged_candidate_table=staged_candidate,
                current_candidate_table=current_candidate,
            )
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            outputs = payload["outputs"]

        self.assertEqual(outputs["manifest"], str((current / "manifests/build_manifest.json").resolve()))
        self.assertEqual(
            outputs["graph_inclusion_dispositions"],
            str((current / "views/graph_inclusion_dispositions.json").resolve()),
        )
        self.assertFalse(any("/stage/" in path for path in outputs.values()))
        self.assertEqual(payload["input_files"], [str(current_candidate.resolve())])


if __name__ == "__main__":
    unittest.main()
