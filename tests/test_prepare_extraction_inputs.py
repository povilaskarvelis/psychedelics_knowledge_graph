import tempfile
import unittest
from pathlib import Path

from pipeline.extract.prepare_extraction_inputs import (
    manifest_screening_inputs,
    render_markdown,
    validate_screening_inputs,
    write_candidates,
)


class PrepareExtractionInputsTest(unittest.TestCase):
    def test_write_candidates_uses_generic_output_names(self) -> None:
        record = {
            "study_doi": "10.1000/test",
            "dataset": "mechanistic",
            "extraction_scope": "psychedelic_compound_x_target",
            "screening_summary": {
                "best_llm_relevance": "relevant",
                "included_from_runs": ["grouped_search_2026_05"],
                "screening_record_count": 1,
            },
            "readiness": {
                "status": "full_text_ready",
                "extraction_input_tier": "full_text",
                "fulltext_ready": True,
                "fulltext_artifact_path": "/tmp/artifact.json",
                "fulltext_char_count": 1000,
                "has_abstract": True,
                "pdf_local_path": "/tmp/paper.pdf",
                "pdf_download_status": "downloaded",
            },
            "paper_metadata": {
                "study_title": "Example",
                "study_year": "2024",
                "authors": "A. Author",
                "study_journal": "Journal",
                "publication_type": "journal-article",
                "publication_date": "2024-01-01",
                "pmid": "123",
                "pmcid": "PMC123",
            },
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            outputs = write_candidates("mechanistic", [record], output_dir=root / "processed", queue_dir=root / "raw")

            output_paths = [outputs["jsonl"], outputs["csv"], *outputs["doi_queues"].values()]

        self.assertTrue(all("v2" not in path.lower() for path in output_paths))
        self.assertIn("mechanistic_extraction_candidates.jsonl", outputs["jsonl"])
        self.assertIn("doi_queue.mechanistic.extraction_fulltext_ready.txt", outputs["doi_queues"]["fulltext_ready"])

    def test_render_markdown_uses_generic_title(self) -> None:
        report = {
            "generated_at_utc": "2026-05-19T00:00:00+00:00",
            "datasets": [
                {
                    "summary": {
                        "dataset": "disorder",
                        "selected_unique_dois": 1,
                        "by_best_llm_relevance": {"relevant": 1},
                        "by_readiness_status": {"full_text_ready": 1},
                        "dois_seen_in_multiple_runs": 0,
                    },
                    "outputs": {
                        "jsonl": "/tmp/disorder_extraction_candidates.jsonl",
                        "csv": "/tmp/disorder_extraction_candidates.csv",
                        "doi_queues": {
                            "fulltext_ready": "/tmp/doi_queue.disorder.extraction_fulltext_ready.txt",
                            "abstract_only": "/tmp/doi_queue.disorder.extraction_abstract_only.txt",
                        },
                    },
                }
            ],
        }

        markdown = render_markdown(report)

        self.assertIn("# Extraction Readiness", markdown)
        self.assertNotIn("V2", markdown)
        self.assertNotIn("v2", markdown)

    def test_manifest_screening_inputs_resolves_included_reports(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            report = root / "data" / "processed" / "report.json"
            report.parent.mkdir(parents=True)
            report.write_text("{}", encoding="utf-8")
            manifest = root / "data" / "processed" / "corpus_manifest.json"
            manifest.write_text(
                """{
  "datasets": {
    "mechanistic": {
      "screening_reports": [
        {"run_id": "grouped_search", "path": "data/processed/report.json"},
        {"run_id": "skipped", "path": "data/processed/skipped.json", "include": false}
      ]
    }
  }
}
""",
                encoding="utf-8",
            )

            inputs = manifest_screening_inputs(manifest, "mechanistic")

        self.assertEqual(len(inputs), 1)
        self.assertEqual(inputs[0]["run_id"], "grouped_search")
        self.assertTrue(inputs[0]["path"].endswith("data/processed/report.json"))

    def test_validate_screening_inputs_checks_manifest_report_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            report = root / "screening_report.json"
            report.write_text('{"rows": []}', encoding="utf-8")

            summary = validate_screening_inputs(
                {
                    "mechanistic": [
                        {
                            "run_id": "grouped_search",
                            "path": str(report),
                        }
                    ]
                }
            )

        self.assertEqual(summary["mechanistic"]["included_reports"], 1)


if __name__ == "__main__":
    unittest.main()
