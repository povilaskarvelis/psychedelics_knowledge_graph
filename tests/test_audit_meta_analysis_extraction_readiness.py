import json
import tempfile
import unittest
from pathlib import Path

from pipeline.extract.audit_meta_analysis_extraction_readiness import build_report, read_jsonl, write_csv


def task_row(**overrides: object) -> dict:
    row = {
        "schema_version": "route_extraction_task_v1",
        "generated_at_utc": "2026-01-01T00:00:00+00:00",
        "task_id": "route-meta-ready",
        "route_id": "route-meta-ready",
        "study_doi": "10.1000/meta-ready",
        "task_status": "ready_for_model",
        "paper_metadata": {
            "doi": "10.1000/meta-ready",
            "study_title": "Ready meta-analysis",
            "study_year": "2025",
            "publication_type": "Journal Article | Meta-Analysis",
            "abstract": "A meta-analysis.",
        },
        "route_context": {
            "route_id": "route-meta-ready",
            "doi": "10.1000/meta-ready",
            "domain_route": "clinical_outcome",
            "access_tier": "full_text_available",
            "route_action": "extract_from_full_text",
            "prompt_profile": "secondary_meta_analysis",
            "schema_profile": "synthesis_evidence_schema",
            "route_basis": "test",
        },
        "extraction_contract": {
            "contract_version": "route_extraction_task_v1",
            "route_id": "route-meta-ready",
            "prompt_profile": "secondary_meta_analysis",
            "schema_profile": "synthesis_evidence_schema",
            "domain_route": "clinical_outcome",
            "output_family": "evidence_synthesis",
            "source_family": "secondary_literature",
            "source_type": "meta_analysis",
            "access_level": "full_text_seen",
            "expected_packet_profile": "secondary_synthesis",
        },
        "text_source": {
            "mode": "full_text_packet",
            "status": "ready_for_model",
            "access_level": "full_text_seen",
            "route_action": "extract_from_full_text",
            "packet_id": "disorder:10.1000/meta-ready",
            "packet_source_path": "/tmp/packets.jsonl",
            "packet_selection_basis": "matched_route_dataset_and_packet_profile:secondary_synthesis",
            "expected_packet_profile": "secondary_synthesis",
            "packet_profile": "secondary_synthesis",
            "packet_profile_status": "matches_expected",
            "fulltext_artifact_paths": ["/tmp/meta.json"],
            "local_pdf_paths": [],
            "abstract_available": True,
        },
        "content": {"title": "Ready meta-analysis", "abstract": "A meta-analysis."},
    }
    row.update(overrides)
    return row


class AuditMetaAnalysisExtractionReadinessTest(unittest.TestCase):
    def test_build_report_counts_meta_analysis_readiness(self) -> None:
        tasks = [
            task_row(),
            task_row(
                task_id="route-meta-mismatch",
                route_id="route-meta-mismatch",
                study_doi="10.1000/meta-mismatch",
                task_status="needs_expected_fulltext_packet",
                text_source={
                    **task_row()["text_source"],
                    "status": "needs_expected_fulltext_packet",
                    "packet_id": "disorder:10.1000/meta-mismatch",
                    "packet_profile": "lean_primary",
                    "packet_profile_status": "profile_mismatch",
                },
            ),
            task_row(
                task_id="route-primary",
                route_id="route-primary",
                study_doi="10.1000/primary",
                extraction_contract={
                    **task_row()["extraction_contract"],
                    "prompt_profile": "primary_clinical",
                    "schema_profile": "primary_evidence_schema",
                    "output_family": "clinical_primary_evidence",
                    "expected_packet_profile": "primary_empirical",
                },
                route_context={
                    **task_row()["route_context"],
                    "prompt_profile": "primary_clinical",
                    "schema_profile": "primary_evidence_schema",
                },
            ),
        ]

        rows, report = build_report(tasks, input_path=Path("/tmp/tasks.jsonl"), generated_at_utc="2026-01-01T00:00:00+00:00")

        self.assertEqual(len(rows), 2)
        self.assertEqual(report["meta_analysis_tasks"], 2)
        self.assertEqual(report["ready_for_model_tasks"], 1)
        self.assertEqual(report["needs_expected_packet_profile_tasks"], 1)
        self.assertEqual(report["by_packet_profile_status"], {"matches_expected": 1, "profile_mismatch": 1})

    def test_read_jsonl_and_write_csv_round_trip_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            input_path = root / "tasks.jsonl"
            input_path.write_text(json.dumps(task_row()) + "\n", encoding="utf-8")
            rows, _ = build_report(read_jsonl(input_path), input_path=input_path)
            out_csv = root / "audit.csv"

            write_csv(out_csv, rows)

            self.assertIn("route-meta-ready", out_csv.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
