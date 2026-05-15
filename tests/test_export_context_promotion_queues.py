import csv
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from pipeline.validate.export_context_promotion_queues import export_queues, select_rows


def row(
    *,
    stage: str,
    dataset: str = "disorder",
    doi: str = "10.example/a",
    compound: str = "Psilocybin",
    entity: str = "Major depressive disorder",
    priority: int = 50,
) -> dict:
    return {
        "priority_score": priority,
        "promotion_stage": stage,
        "recommended_action": f"action_for_{stage}",
        "dataset": dataset,
        "doi": doi,
        "compound": compound,
        "entity": entity,
        "entity_type": "indication",
        "verification_layer": "candidate_context",
        "revalidation_status": "needs_revalidation",
        "study_title": "Example paper",
        "study_year": "2024",
        "context_sources": ["paper_library_context"],
        "blocking_flags": [],
        "source_artifacts": ["data/processed/example.json"],
        "context_id": f"{dataset}|{doi}|{compound}|{entity}",
    }


class ExportContextPromotionQueuesTest(unittest.TestCase):
    def test_exports_stage_csv_and_dataset_doi_queues(self) -> None:
        records = [
            row(stage="full_text_extraction_ready", doi="10.example/a", priority=10),
            row(stage="full_text_extraction_ready", doi="10.example/a", priority=9),
            row(
                stage="abstract_screening_needed",
                dataset="mechanistic",
                doi="10.example/b",
                compound="LSD",
                entity="5-HT2A",
                priority=20,
            ),
            row(stage="verified_evidence", doi="10.example/verified", priority=99),
        ]

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            manifest = export_queues(
                records,
                queue_dir=root / "queues",
                doi_dir=root / "doi_queues",
                include_verified=False,
            )

            self.assertEqual(manifest["summary"]["exported_contexts"], 3)
            self.assertIn("full_text_extraction_ready", manifest["queue_files"])
            self.assertNotIn("verified_evidence", manifest["queue_files"])

            csv_path = Path(manifest["queue_files"]["full_text_extraction_ready"])
            with csv_path.open("r", encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 2)

            doi_info = manifest["doi_queue_files"]["full_text_extraction_ready"]["disorder"]
            self.assertEqual(doi_info["context_rows"], 2)
            self.assertEqual(doi_info["unique_doi_context_rows"], 1)
            doi_path = Path(doi_info["path"])
            with doi_path.open("r", encoding="utf-8", newline="") as handle:
                doi_rows = [parts for parts in csv.reader(handle) if parts and not parts[0].startswith("#")]
            self.assertEqual(len(doi_rows), 1)
            self.assertEqual(doi_rows[0][0], "10.example/a")

    def test_select_rows_filters_dataset_and_limits_by_priority(self) -> None:
        records = [
            row(stage="abstract_screening_needed", dataset="disorder", doi="10.example/low", priority=1),
            row(stage="abstract_screening_needed", dataset="disorder", doi="10.example/high", priority=100),
            row(stage="abstract_screening_needed", dataset="mechanistic", doi="10.example/other", priority=200),
        ]

        selected = select_rows(records, dataset="disorder", limit_per_stage=1)

        self.assertEqual(len(selected["abstract_screening_needed"]), 1)
        self.assertEqual(selected["abstract_screening_needed"][0]["doi"], "10.example/high")


if __name__ == "__main__":
    unittest.main()
