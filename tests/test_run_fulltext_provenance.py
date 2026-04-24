import argparse
import json
import tempfile
import unittest
from pathlib import Path

from pipeline.fulltext.run_fulltext_provenance import (
    build_stage_commands,
    chunked,
    limit_for_dataset,
    selected_datasets,
    successful_backend_in_artifact,
    write_doi_batch_file,
)


def args(**overrides) -> argparse.Namespace:
    defaults = {
        "dataset": "all",
        "backend": "auto",
        "limit": 25,
        "disorder_limit": None,
        "mechanistic_limit": None,
        "review_dir": "/tmp/reviews",
        "python": "python",
        "skip_conversion": False,
        "skip_repair_report": False,
        "skip_evidence_triage": False,
        "skip_review_export": False,
        "include_existing_artifacts": False,
        "only_missing_artifacts": True,
        "all_pdf_candidates": False,
        "stale_fulltext_locators": True,
        "no_pdf_env_bootstrap": False,
        "grobid_batch_size": 50,
        "grobid_url": "http://localhost:8070/api/processFulltextDocument",
        "grobid_timeout_sec": 120,
        "grobid_retries": 2,
        "grobid_retry_wait_sec": 5,
        "grobid_consolidate_header": "0",
        "grobid_consolidate_citations": "0",
        "grobid_batch_dir": "/tmp/grobid_batches",
        "grobid_batch_report_dir": "/tmp/grobid_batch_reports",
        "grobid_image": "grobid/grobid:0.9.0-crf",
        "grobid_container": "psychkg-grobid",
        "grobid_config": "/tmp/grobid.safe.yaml",
        "grobid_concurrency": 1,
        "grobid_pdfalto_memory_mb": 2048,
        "grobid_memory": "5g",
        "grobid_start_wait_sec": 90,
        "recreate_grobid_config": False,
        "skip_grobid_managed_start": False,
        "grobid_restart_each_batch": True,
        "continue_on_error": False,
        "verbose": False,
        "evidence_triage_auto_confidence": 0.85,
        "evidence_triage_scope": "full_text_seen",
    }
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


class RunFulltextProvenanceTest(unittest.TestCase):
    def test_selected_datasets_expands_all_in_stable_order(self) -> None:
        self.assertEqual(selected_datasets("all"), ["disorder", "mechanistic"])
        self.assertEqual(selected_datasets("disorder"), ["disorder"])

    def test_limit_for_dataset_uses_dataset_override(self) -> None:
        parsed = args(limit=50, disorder_limit=10)

        self.assertEqual(limit_for_dataset(parsed, "disorder"), 10)
        self.assertEqual(limit_for_dataset(parsed, "mechanistic"), 50)

    def test_build_stage_commands_for_all_datasets(self) -> None:
        stages = build_stage_commands(args(limit=7, backend="docling"))

        self.assertEqual(len(stages), 8)
        self.assertEqual([stage.stage for stage in stages[:4]], ["convert", "repair_report", "evidence_triage", "review_export"])
        self.assertEqual(stages[0].dataset, "disorder")
        self.assertIn("--stale-fulltext-locators", stages[0].cmd)
        self.assertIn("--only-missing-artifacts", stages[0].cmd)
        self.assertIn("--limit", stages[0].cmd)
        self.assertIn("7", stages[0].cmd)
        self.assertIn("--auto-confidence", stages[2].cmd)
        self.assertIn("--scope", stages[2].cmd)
        self.assertTrue(stages[3].cmd[-1].endswith("/reviews/provenance_review_disorder.csv"))
        self.assertEqual(stages[4].dataset, "mechanistic")

    def test_build_stage_commands_can_skip_conversion(self) -> None:
        stages = build_stage_commands(args(dataset="mechanistic", skip_conversion=True))

        self.assertEqual([stage.stage for stage in stages], ["repair_report", "evidence_triage", "review_export"])
        self.assertTrue(all(stage.dataset == "mechanistic" for stage in stages))

    def test_build_stage_commands_can_include_existing_and_all_pdf_candidates(self) -> None:
        stages = build_stage_commands(
            args(
                dataset="disorder",
                only_missing_artifacts=False,
                stale_fulltext_locators=False,
                no_pdf_env_bootstrap=True,
            )
        )

        convert = stages[0].cmd
        self.assertNotIn("--only-missing-artifacts", convert)
        self.assertNotIn("--stale-fulltext-locators", convert)
        self.assertIn("--no-pdf-env-bootstrap", convert)

    def test_successful_backend_in_artifact_checks_best_and_extractions(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact = Path(tmpdir) / "artifact.json"
            artifact.write_text(
                json.dumps(
                    {
                        "best_backend": "docling",
                        "extractions": [
                            {"backend": "docling", "status": "ok"},
                            {"backend": "grobid", "status": "ok"},
                        ],
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            self.assertTrue(successful_backend_in_artifact(artifact, "grobid"))
            self.assertFalse(successful_backend_in_artifact(artifact, "pdftotext"))

    def test_chunked_splits_batches_without_dropping_rows(self) -> None:
        rows = [({"study_doi": f"10.1000/{idx}"}, Path("/tmp/a.pdf"), Path("/tmp/a.json")) for idx in range(5)]

        chunks = list(chunked(rows, 2))

        self.assertEqual([len(chunk) for chunk in chunks], [2, 2, 1])

    def test_write_doi_batch_file_normalizes_dois(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = write_doi_batch_file(
                "mechanistic",
                3,
                [
                    ({"study_doi": "https://doi.org/10.1000/ABC"}, Path("/tmp/a.pdf"), Path("/tmp/a.json")),
                    ({"study_doi": "doi:10.1000/def"}, Path("/tmp/b.pdf"), Path("/tmp/b.json")),
                ],
                Path(tmpdir),
            )

            self.assertEqual(path.name, "mechanistic_grobid_batch_0003.txt")
            self.assertEqual(path.read_text(encoding="utf-8").splitlines(), ["10.1000/abc", "10.1000/def"])


if __name__ == "__main__":
    unittest.main()
