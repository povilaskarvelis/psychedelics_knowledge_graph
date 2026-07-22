import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
from jsonschema import Draft7Validator

from pipeline.extract.build_extraction_tasks import (
    TASK_SCHEMA_VERSION,
    build_tasks,
    input_fingerprint_for_task,
)


ROOT = Path(__file__).resolve().parents[1]


def make_args(root: Path, *, packet_paths: list[Path] | None = None, only_ready: bool = False) -> SimpleNamespace:
    return SimpleNamespace(
        route_table=str(root / "routes.parquet"),
        metadata_table=str(root / "metadata.parquet"),
        out_jsonl=str(root / "tasks.jsonl"),
        report_json=str(root / "report.json"),
        schema=str(ROOT / "schema" / "extraction_task.schema.json"),
        doi_file="",
        fulltext_packets_jsonl=[str(path) for path in (packet_paths or [])],
        route_action=[],
        prompt_profile=[],
        schema_profile=[],
        domain_route=[],
        limit=0,
        include_packet_content=False,
        only_ready=only_ready,
        only_retained=True,
    )


def route_row(**overrides: object) -> dict:
    row = {
        "route_id": "route-primary-clinical",
        "doi": "10.1000/full",
        "retained_for_extraction_candidate": True,
        "study_title": "Full text psilocybin trial",
        "study_year": "2024",
        "publication_type": "Journal Article",
        "source_family": "primary_or_unclear",
        "source_type": "primary_or_unclear",
        "secondary_source_types": "",
        "primary_secondary_source_type": "",
        "literature_type_confidence": "medium",
        "domain_route": "clinical_outcome",
        "domain_tags": "clinical_outcome|safety_tolerability",
        "domain_routing_primary_domain": "clinical_outcome",
        "methodological_validity_tags": "",
        "domain_screening_decision": "include_in_scope",
        "domain_screening_reason": "Clinical trial abstract.",
        "domain_routing_model": "gemini-test",
        "domain_needs_human_review": False,
        "domain_route_confidence": "high",
        "bridge_clinical_mechanism": False,
        "study_system_hint": "clinical",
        "access_tier": "full_text_available",
        "has_abstract": True,
        "has_pdf_url": True,
        "has_converted_full_text": True,
        "fulltext_artifact_paths": "/tmp/full.json",
        "fulltext_char_count": 15000,
        "has_local_pdf": False,
        "local_pdf_paths": "",
        "local_pdf_count": 0,
        "open_access_status": "gold",
        "best_pdf_url": "https://example.org/full.pdf",
        "route_action": "extract_from_full_text",
        "prompt_profile": "primary_clinical",
        "schema_profile": "primary_evidence_schema",
        "route_priority": 10,
        "route_confidence": "high",
        "route_basis": "source_family:primary_or_unclear",
    }
    row.update(overrides)
    return row


class BuildExtractionTasksTest(unittest.TestCase):
    def test_prompt_or_schema_asset_change_invalidates_task_identity(self) -> None:
        route_context = {"domain_route": "clinical_outcome", "route_action": "extract_from_abstract_only"}
        contract = {
            "prompt_profile": "primary_clinical",
            "schema_profile": "primary_evidence_schema",
            "contract_version": TASK_SCHEMA_VERSION,
            "contract_assets_fingerprint": "a" * 64,
        }
        first = input_fingerprint_for_task(
            route_id="route-one",
            route_context=route_context,
            contract=contract,
            source_fingerprint="c" * 64,
        )
        second = input_fingerprint_for_task(
            route_id="route-one",
            route_context=route_context,
            contract={**contract, "contract_assets_fingerprint": "b" * 64},
            source_fingerprint="c" * 64,
        )

        self.assertNotEqual(first, second)

    def test_build_tasks_uses_source_fingerprinted_task_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            routes = pd.DataFrame(
                [
                    route_row(),
                    route_row(
                        route_id="route-primary-safety",
                        domain_route="safety_tolerability",
                        prompt_profile="primary_safety",
                    ),
                    route_row(
                        route_id="route-meta",
                        doi="10.1000/meta",
                        study_title="Meta-analysis of psilocybin trials",
                        source_family="secondary_literature",
                        source_type="meta_analysis",
                        primary_secondary_source_type="meta_analysis",
                        domain_route="clinical_outcome",
                        access_tier="abstract_only",
                        has_converted_full_text=False,
                        fulltext_artifact_paths="",
                        fulltext_char_count=0,
                        route_action="extract_from_abstract_only",
                        prompt_profile="secondary_meta_analysis",
                        schema_profile="meta_analysis_evidence_schema",
                    ),
                    route_row(
                        route_id="route-review-v1",
                        doi="10.1000/review-v1",
                        study_title="Legacy routed review",
                        source_family="secondary_literature",
                        source_type="review",
                        primary_secondary_source_type="review",
                        access_tier="abstract_only",
                        has_converted_full_text=False,
                        fulltext_artifact_paths="",
                        fulltext_char_count=0,
                        route_action="extract_from_abstract_only",
                        prompt_profile="secondary_review_coverage",
                        schema_profile="review_coverage_schema",
                    ),
                    route_row(
                        route_id="route-download-first",
                        doi="10.1000/download-first",
                        route_action="download_pdf_then_extract",
                        access_tier="pdf_download_url_available",
                    ),
                    route_row(
                        route_id="route-excluded",
                        doi="10.1000/excluded",
                        route_action="exclude_after_model_screen",
                        prompt_profile="no_extraction",
                        schema_profile="no_extraction_schema",
                    ),
                ]
            )
            routes.to_parquet(root / "routes.parquet", index=False)
            metadata = pd.DataFrame(
                [
                    {
                        "doi": "10.1000/full",
                        "study_title": "Full text psilocybin trial",
                        "study_year": "2024",
                        "abstract": "Participants received psilocybin.",
                        "publication_type": "Journal Article | Randomized Controlled Trial",
                        "open_access_status": "gold",
                        "best_pdf_url": "https://example.org/full.pdf",
                    },
                    {
                        "doi": "10.1000/meta",
                        "study_title": "Meta-analysis of psilocybin trials",
                        "study_year": "2025",
                        "abstract": "We meta-analyzed randomized trials.",
                        "publication_type": "Journal Article | Meta-Analysis",
                    },
                ]
            )
            metadata.to_parquet(root / "metadata.parquet", index=False)
            packets = root / "packets.jsonl"
            packets.write_text(
                json.dumps(
                    {
                        "packet_id": "article:10.1000/full",
                        "packet_profile": "primary_empirical",
                        "study_doi": "10.1000/full",
                        "document_summary": {"packet_profile": "primary_empirical", "chunk_count": 2},
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            tasks, report = build_tasks(make_args(root, packet_paths=[packets]))

        self.assertEqual(report["tasks_written"], 2)
        self.assertEqual({task["schema_version"] for task in tasks}, {TASK_SCHEMA_VERSION})
        self.assertTrue(all(task["task_id"] != task["route_id"] for task in tasks))
        self.assertTrue(all(len(task["task_id"]) == 20 for task in tasks))
        self.assertTrue(all(len(task["input_fingerprint"]) == 64 for task in tasks))
        self.assertTrue(all(len(task["text_source"]["source_fingerprint"]) == 64 for task in tasks))
        self.assertEqual(
            {task["route_id"] for task in tasks},
            {"route-primary-clinical", "route-primary-safety"},
        )
        self.assertEqual({task["task_status"] for task in tasks}, {"ready_for_model"})
        self.assertEqual(
            {task["extraction_contract"]["schema_profile"] for task in tasks},
            {"primary_evidence_schema"},
        )
        self.assertEqual(report["by_output_family"]["primary_evidence"], 2)
        self.assertEqual(report["legacy_v1_secondary_route_rows_hard_disabled"], 2)
        by_route_id = {task["route_id"]: task for task in tasks}
        self.assertNotIn("datasets", by_route_id["route-primary-clinical"]["route_context"])
        self.assertNotIn("dataset", by_route_id["route-primary-clinical"]["content"]["packet_summary"])
        self.assertEqual(
            by_route_id["route-primary-clinical"]["extraction_contract"]["expected_packet_profile"],
            "primary_empirical",
        )
        self.assertEqual(report["by_expected_packet_profile"]["primary_empirical"], 2)

        schema = json.loads((ROOT / "schema" / "extraction_task.schema.json").read_text(encoding="utf-8"))
        validator = Draft7Validator(schema)
        errors = [error.message for task in tasks for error in validator.iter_errors(task)]
        self.assertEqual(errors, [])

    def test_abstract_change_invalidates_task_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            pd.DataFrame(
                [
                    route_row(
                        route_id="route-abstract",
                        access_tier="abstract_only",
                        has_converted_full_text=False,
                        fulltext_artifact_paths="",
                        route_action="extract_from_abstract_only",
                    )
                ]
            ).to_parquet(root / "routes.parquet", index=False)
            metadata_path = root / "metadata.parquet"
            pd.DataFrame(
                [
                    {
                        "doi": "10.1000/full",
                        "study_title": "Abstract-routed study",
                        "abstract": "First public abstract version.",
                    }
                ]
            ).to_parquet(metadata_path, index=False)
            first, _ = build_tasks(make_args(root))
            pd.DataFrame(
                [
                    {
                        "doi": "10.1000/full",
                        "study_title": "Abstract-routed study",
                        "abstract": "Corrected public abstract version.",
                    }
                ]
            ).to_parquet(metadata_path, index=False)
            second, _ = build_tasks(make_args(root))

        self.assertNotEqual(first[0]["input_fingerprint"], second[0]["input_fingerprint"])
        self.assertNotEqual(first[0]["task_id"], second[0]["task_id"])

    def test_fulltext_route_without_packet_is_kept_but_not_ready(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            pd.DataFrame([route_row()]).to_parquet(root / "routes.parquet", index=False)
            pd.DataFrame(
                [
                    {
                        "doi": "10.1000/full",
                        "study_title": "Full text psilocybin trial",
                        "abstract": "Participants received psilocybin.",
                    }
                ]
            ).to_parquet(root / "metadata.parquet", index=False)

            tasks, report = build_tasks(make_args(root))
            ready_tasks, ready_report = build_tasks(make_args(root, only_ready=True))

        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["task_status"], "needs_fulltext_packet")
        self.assertEqual(tasks[0]["text_source"]["mode"], "full_text_artifact")
        self.assertEqual(report["by_task_status"], {"needs_fulltext_packet": 1})
        self.assertEqual(ready_tasks, [])
        self.assertEqual(ready_report["tasks_written"], 0)

    def test_runnable_guideline_profile_requires_compatible_article_packet(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            pd.DataFrame(
                [
                    route_row(
                        route_id="route-guideline",
                        prompt_profile="guideline_consensus",
                        schema_profile="recommendation_consensus_schema",
                    )
                ]
            ).to_parquet(root / "routes.parquet", index=False)
            pd.DataFrame(
                [
                    {
                        "doi": "10.1000/full",
                        "study_title": "Guideline paper",
                        "abstract": "A guideline abstract.",
                    }
                ]
            ).to_parquet(root / "metadata.parquet", index=False)

            tasks, report = build_tasks(make_args(root))

        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["task_status"], "needs_fulltext_packet")
        self.assertEqual(tasks[0]["text_source"]["mode"], "full_text_artifact")
        self.assertEqual(tasks[0]["text_source"]["expected_packet_profile"], "full")
        self.assertEqual(tasks[0]["text_source"]["packet_profile_status"], "no_packet")
        schema = json.loads((ROOT / "schema" / "extraction_task.schema.json").read_text(encoding="utf-8"))
        self.assertEqual([error.message for error in Draft7Validator(schema).iter_errors(tasks[0])], [])
        self.assertEqual(report["by_task_status"], {"needs_fulltext_packet": 1})

    def test_fulltext_meta_analysis_v1_route_is_hard_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            pd.DataFrame(
                [
                    route_row(
                        route_id="route-meta-fulltext",
                        doi="10.1000/meta-fulltext",
                        study_title="Full text meta-analysis",
                        source_family="secondary_literature",
                        source_type="meta_analysis",
                        primary_secondary_source_type="meta_analysis",
                        domain_route="clinical_outcome",
                        access_tier="full_text_available",
                        has_converted_full_text=True,
                        route_action="extract_from_full_text",
                        prompt_profile="secondary_meta_analysis",
                        schema_profile="meta_analysis_evidence_schema",
                    )
                ]
            ).to_parquet(root / "routes.parquet", index=False)
            pd.DataFrame(
                [
                    {
                        "doi": "10.1000/meta-fulltext",
                        "study_title": "Full text meta-analysis",
                        "abstract": "We meta-analyzed trials.",
                        "publication_type": "Journal Article | Meta-Analysis",
                    }
                ]
            ).to_parquet(root / "metadata.parquet", index=False)
            packets = root / "packets.jsonl"
            packets.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "packet_id": "article:10.1000/meta-fulltext:lean",
                                "packet_profile": "primary_empirical",
                                "study_doi": "10.1000/meta-fulltext",
                                "document_summary": {"packet_profile": "primary_empirical"},
                            }
                        ),
                        json.dumps(
                            {
                                "packet_id": "article:10.1000/meta-fulltext:synthesis",
                                "packet_profile": "secondary_synthesis",
                                "study_doi": "10.1000/meta-fulltext",
                                "document_summary": {"packet_profile": "secondary_synthesis"},
                            }
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            tasks, report = build_tasks(make_args(root, packet_paths=[packets]))

        self.assertEqual(tasks, [])
        self.assertEqual(report["tasks_written"], 0)
        self.assertEqual(report["legacy_v1_secondary_route_rows_hard_disabled"], 1)

    def test_legacy_meta_profile_is_not_emitted_even_with_packet_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            pd.DataFrame(
                [
                    route_row(
                        route_id="route-meta-mismatch",
                        doi="10.1000/meta-mismatch",
                        source_family="secondary_literature",
                        source_type="meta_analysis",
                        primary_secondary_source_type="meta_analysis",
                        access_tier="full_text_available",
                        route_action="extract_from_full_text",
                        prompt_profile="secondary_meta_analysis",
                        schema_profile="meta_analysis_evidence_schema",
                    )
                ]
            ).to_parquet(root / "routes.parquet", index=False)
            pd.DataFrame(
                [
                    {
                        "doi": "10.1000/meta-mismatch",
                        "study_title": "Mismatched packet meta-analysis",
                        "abstract": "A meta-analysis.",
                    }
                ]
            ).to_parquet(root / "metadata.parquet", index=False)
            packets = root / "packets.jsonl"
            packets.write_text(
                json.dumps(
                    {
                        "packet_id": "article:10.1000/meta-mismatch",
                        "packet_profile": "primary_empirical",
                        "study_doi": "10.1000/meta-mismatch",
                        "document_summary": {"packet_profile": "primary_empirical"},
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            tasks, report = build_tasks(make_args(root, packet_paths=[packets]))
            ready_tasks, _ = build_tasks(make_args(root, packet_paths=[packets], only_ready=True))

        self.assertEqual(tasks, [])
        self.assertEqual(report["legacy_v1_secondary_route_rows_hard_disabled"], 1)
        self.assertEqual(ready_tasks, [])


if __name__ == "__main__":
    unittest.main()
