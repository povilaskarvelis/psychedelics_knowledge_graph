import json
import tempfile
import unittest
from pathlib import Path

from pipeline.extract.audit_primary_extraction_readiness import build_report, read_jsonl, write_csv


def task_row(**overrides: object) -> dict:
    row = {
        "schema_version": "route_extraction_task_v1",
        "generated_at_utc": "2026-01-01T00:00:00+00:00",
        "task_id": "route-primary-ready",
        "route_id": "route-primary-ready",
        "study_doi": "10.1000/primary-ready",
        "task_status": "ready_for_model",
        "paper_metadata": {
            "doi": "10.1000/primary-ready",
            "study_title": "Ready primary study",
            "study_year": "2025",
            "publication_type": "Journal Article",
            "abstract": "A primary study.",
        },
        "route_context": {
            "route_id": "route-primary-ready",
            "doi": "10.1000/primary-ready",
            "domain_route": "clinical_outcome",
            "access_tier": "full_text_available",
            "route_action": "extract_from_full_text",
            "prompt_profile": "primary_clinical",
            "schema_profile": "primary_evidence_schema",
            "source_family": "primary_or_unclear",
            "source_type": "primary_or_unclear",
            "study_system_hint": "clinical",
            "route_basis": "test",
        },
        "extraction_contract": {
            "contract_version": "route_extraction_task_v1",
            "route_id": "route-primary-ready",
            "prompt_profile": "primary_clinical",
            "schema_profile": "primary_evidence_schema",
            "domain_route": "clinical_outcome",
            "output_family": "clinical_primary_evidence",
            "source_family": "primary_or_unclear",
            "source_type": "primary_or_unclear",
            "access_level": "full_text_seen",
            "expected_packet_profile": "primary_empirical",
        },
        "text_source": {
            "mode": "full_text_packet",
            "status": "ready_for_model",
            "access_level": "full_text_seen",
            "route_action": "extract_from_full_text",
            "packet_id": "disorder:10.1000/primary-ready",
            "packet_source_path": "/tmp/packets.jsonl",
            "packet_selection_basis": "matched_route_dataset_and_packet_profile:primary_empirical",
            "expected_packet_profile": "primary_empirical",
            "packet_profile": "primary_empirical",
            "packet_profile_status": "matches_expected",
            "fulltext_artifact_paths": ["/tmp/primary.json"],
            "local_pdf_paths": [],
            "abstract_available": True,
        },
        "content": {"title": "Ready primary study", "abstract": "A primary study."},
    }
    row.update(overrides)
    return row


class AuditPrimaryExtractionReadinessTest(unittest.TestCase):
    def test_build_report_counts_primary_readiness(self) -> None:
        tasks = [
            task_row(),
            task_row(
                task_id="route-primary-needs-packet",
                route_id="route-primary-needs-packet",
                study_doi="10.1000/primary-needs-packet",
                task_status="needs_fulltext_packet",
                text_source={
                    **task_row()["text_source"],
                    "mode": "full_text_artifact",
                    "status": "needs_fulltext_packet",
                    "packet_id": "",
                    "packet_profile": "",
                    "packet_profile_status": "no_packet",
                },
            ),
            task_row(
                task_id="route-meta",
                route_id="route-meta",
                study_doi="10.1000/meta",
                extraction_contract={
                    **task_row()["extraction_contract"],
                    "prompt_profile": "secondary_meta_analysis",
                    "schema_profile": "meta_analysis_evidence_schema",
                    "output_family": "meta_analysis_evidence",
                    "expected_packet_profile": "secondary_synthesis",
                },
                route_context={
                    **task_row()["route_context"],
                    "prompt_profile": "secondary_meta_analysis",
                    "schema_profile": "meta_analysis_evidence_schema",
                },
            ),
        ]

        rows, report = build_report(tasks, input_path=Path("/tmp/tasks.jsonl"), generated_at_utc="2026-01-01T00:00:00+00:00")

        self.assertEqual(len(rows), 2)
        self.assertEqual(report["primary_tasks"], 2)
        self.assertEqual(report["ready_for_model_tasks"], 1)
        self.assertEqual(report["needs_fulltext_packet_tasks"], 1)
        self.assertEqual(report["by_domain_route"], {"clinical_outcome": 2})
        self.assertEqual(report["by_packet_profile_status"], {"matches_expected": 1, "no_packet": 1})

    def test_read_jsonl_and_write_csv_round_trip_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            input_path = root / "tasks.jsonl"
            input_path.write_text(json.dumps(task_row()) + "\n", encoding="utf-8")
            rows, _ = build_report(read_jsonl(input_path), input_path=input_path)
            out_csv = root / "audit.csv"

            write_csv(out_csv, rows)

            self.assertIn("route-primary-ready", out_csv.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
