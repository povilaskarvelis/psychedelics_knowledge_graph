import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from pipeline.extract.io_utils import write_json
from pipeline.kg.build_evidence_tables import build_tables
from pipeline.kg.convert_routed_extractions_to_evidence_rows import (
    DEFAULT_ROUTED_RUN_ROOT,
    convert_outputs,
    resolve_output_paths,
)


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


class ConvertRoutedExtractionsToEvidenceRowsTest(unittest.TestCase):
    def test_run_id_resolves_converter_outputs_to_versioned_directory(self) -> None:
        args = resolve_output_paths(
            SimpleNamespace(
                run_id="gemini 3 flash batch",
                run_dir="",
                out_json="",
                report_json="",
            )
        )

        self.assertEqual(args.run_id, "gemini_3_flash_batch")
        self.assertEqual(Path(args.out_json), DEFAULT_ROUTED_RUN_ROOT / "gemini_3_flash_batch" / "routed_evidence_rows.json")
        self.assertEqual(
            Path(args.report_json),
            DEFAULT_ROUTED_RUN_ROOT / "gemini_3_flash_batch" / "routed_evidence_rows_report.json",
        )

    def test_preserves_domain_specific_fields_as_ui_facing_aliases(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            tasks_jsonl = root / "tasks.jsonl"
            outputs_jsonl = root / "outputs.jsonl"
            write_jsonl(
                tasks_jsonl,
                [
                    {
                        "task_id": "clinical",
                        "route_id": "clinical",
                        "study_doi": "10.1000/clinical",
                        "paper_metadata": {
                            "doi": "10.1000/clinical",
                            "study_title": "Clinical trial",
                            "study_year": "2025",
                        },
                    },
                    {
                        "task_id": "target",
                        "route_id": "target",
                        "study_doi": "10.1000/target",
                        "paper_metadata": {
                            "doi": "10.1000/target",
                            "study_title": "Target study",
                            "study_year": "2025",
                        },
                    },
                    {
                        "task_id": "meta",
                        "route_id": "meta",
                        "study_doi": "10.1000/meta",
                        "paper_metadata": {
                            "doi": "10.1000/meta",
                            "study_title": "Clinical meta-analysis",
                            "study_year": "2025",
                        },
                    },
                ],
            )
            write_jsonl(
                outputs_jsonl,
                [
                    {
                        "task_id": "clinical",
                        "route_id": "clinical",
                        "status": "ok",
                        "result": {
                            "task_id": "clinical",
                            "route_id": "clinical",
                            "study_doi": "10.1000/clinical",
                            "domain_route": "clinical_outcome",
                            "source_type": "primary",
                            "paper_type": "primary",
                            "text_depth": "article_text",
                            "extraction_status": "extracted",
                            "items": [
                                {
                                    "compound_or_intervention": "Psilocybin",
                                    "condition_or_population": "Adults with depression",
                                    "sample_size": "80",
                                    "comparator_or_context": "Placebo",
                                    "dose_or_regimen": "25 mg oral psilocybin",
                                    "outcome_measure_or_instrument": "MADRS",
                                    "time_window": "6 weeks",
                                    "effect_or_statistic": "mean difference -6.6",
                                    "primary_graph_anchor_kind": "condition_indication",
                                }
                            ],
                        },
                    },
                    {
                        "task_id": "target",
                        "route_id": "target",
                        "status": "ok",
                        "result": {
                            "task_id": "target",
                            "route_id": "target",
                            "study_doi": "10.1000/target",
                            "domain_route": "molecular_target",
                            "source_type": "primary",
                            "paper_type": "primary",
                            "text_depth": "article_text",
                            "extraction_status": "extracted",
                            "items": [
                                {
                                    "compound": "LSD",
                                    "target": "5-HT2A receptor",
                                    "metric": "Ki",
                                    "value": "2.9",
                                    "unit": "nM",
                                    "assay_or_method": "radioligand binding",
                                    "model_system": "HEK293 cells",
                                    "species_or_cell_line": "human cell line",
                                }
                            ],
                        },
                    },
                    {
                        "task_id": "meta",
                        "route_id": "meta",
                        "status": "ok",
                        "result": {
                            "task_id": "meta",
                            "route_id": "meta",
                            "study_doi": "10.1000/meta",
                            "domain_route": "clinical_outcome",
                            "source_type": "meta_analysis",
                            "text_depth": "article_text",
                            "extraction_status": "extracted",
                            "included_evidence_summary": {
                                "included_study_count": "7",
                                "included_participant_count": "512",
                            },
                            "synthesis_results": [
                                {
                                    "compound_or_class": "Ketamine",
                                    "entity": "depressive symptoms",
                                    "entity_type": "symptom_problem",
                                    "effect_size": "SMD -0.8",
                                    "domain_result": {
                                        "condition_or_population": "Adults with depression",
                                        "outcome_measure": "depression scales",
                                    },
                                }
                            ],
                        },
                    },
                ],
            )

            rows, report = convert_outputs(input_jsonl=outputs_jsonl, tasks_jsonl=tasks_jsonl)

        self.assertEqual(report["rows_written"], 3)
        clinical = next(row for row in rows if row["study_doi"] == "10.1000/clinical")
        self.assertEqual(clinical["population"], "Adults with depression")
        self.assertEqual(clinical["sample_size_total"], "80")
        self.assertEqual(clinical["comparator"], "Placebo")
        self.assertEqual(clinical["dose"], "25 mg oral psilocybin")
        self.assertEqual(clinical["outcome_measure"], "MADRS")
        self.assertEqual(clinical["follow_up_duration"], "6 weeks")
        self.assertEqual(clinical["effect_size"], "mean difference -6.6")

        target = next(row for row in rows if row["study_doi"] == "10.1000/target")
        self.assertEqual(target["affinity_type"], "Ki")
        self.assertEqual(target["affinity_value"], "2.9")
        self.assertEqual(target["affinity_unit"], "nM")
        self.assertEqual(target["assay_type"], "radioligand binding")
        self.assertEqual(target["model_or_system"], "HEK293 cells")
        self.assertEqual(target["species"], "human cell line")

        meta = next(row for row in rows if row["study_doi"] == "10.1000/meta")
        self.assertEqual(meta["included_study_count"], "7")
        self.assertEqual(meta["included_participant_count"], "512")
        self.assertEqual(meta["sample_size_total"], "512")

    def test_converts_routed_outputs_into_rows_consumed_by_kg_builder(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            tasks_jsonl = root / "tasks.jsonl"
            outputs_jsonl = root / "route_outputs.jsonl"
            evidence_rows_json = root / "routed_evidence_rows.json"
            registry_path = root / "registry.json"
            out_dir = root / "kg"

            write_jsonl(
                tasks_jsonl,
                [
                    {
                        "task_id": "route-brain",
                        "route_id": "route-brain",
                        "study_doi": "10.1000/brain-route",
                        "paper_metadata": {
                            "doi": "10.1000/brain-route",
                            "study_title": "Psilocybin and default mode network connectivity",
                            "study_year": "2025",
                            "study_journal": "Neuropsychopharmacology",
                        },
                    },
                    {
                        "task_id": "route-pk",
                        "route_id": "route-pk",
                        "study_doi": "10.1000/pk-route",
                        "paper_metadata": {
                            "doi": "10.1000/pk-route",
                            "study_title": "DMT pharmacokinetics meta-analysis",
                            "study_year": "2024",
                        },
                    },
                    {
                        "task_id": "route-public-health",
                        "route_id": "route-public-health",
                        "study_doi": "10.1000/public-health-route",
                        "paper_metadata": {
                            "doi": "10.1000/public-health-route",
                            "study_title": "Equity in psychedelic services",
                            "study_year": "2023",
                        },
                    },
                ],
            )
            write_jsonl(
                outputs_jsonl,
                [
                    {
                        "task_id": "route-brain",
                        "route_id": "route-brain",
                        "prompt_profile": "primary_brain_system",
                        "schema_profile": "primary_evidence_schema",
                        "status": "ok",
                        "schema_errors": [],
                        "result": {
                            "schema_version": "primary_brain_system_v1",
                            "task_id": "route-brain",
                            "route_id": "route-brain",
                            "study_doi": "10.1000/brain-route",
                            "domain_route": "brain_system",
                            "source_type": "primary_or_unclear",
                            "paper_type": "primary_study",
                            "text_depth": "article_text",
                            "extraction_status": "extracted",
                            "items": [
                                {
                                    "compound_or_exposure": "Psilocybin",
                                    "population_or_system": "adults",
                                    "sample_size": "60",
                                    "study_design": "randomized trial",
                                    "primary_graph_anchor_kind": "brain_network",
                                    "brain_network": "DMN",
                                    "readout": "functional connectivity",
                                    "assessment_timepoint": "2 hours post-dose",
                                    "finding_summary": "Psilocybin altered default mode network connectivity.",
                                    "evidence_location": "text",
                                    "evidence_locator": "Results",
                                }
                            ],
                            "warnings": [],
                        },
                    },
                    {
                        "task_id": "route-pk",
                        "route_id": "route-pk",
                        "prompt_profile": "secondary_meta_analysis",
                        "schema_profile": "meta_analysis_evidence_schema",
                        "status": "ok",
                        "schema_errors": [],
                        "result": {
                            "schema_version": "meta_analysis_evidence_v1",
                            "task_id": "route-pk",
                            "route_id": "route-pk",
                            "study_doi": "10.1000/pk-route",
                            "domain_route": "pharmacokinetics_exposure",
                            "source_type": "meta_analysis",
                            "text_depth": "article_text",
                            "extraction_status": "extracted",
                            "synthesis_results": [
                                {
                                    "result_id": "PK1",
                                    "relationship_domain": "pharmacokinetics_exposure",
                                    "compound_or_class": "DMT",
                                    "entity_type": "target",
                                    "entity": "MAO-A",
                                    "effect_size": "qualitative",
                                    "confidence": 0.86,
                                    "needs_human_review": False,
                                    "domain_result": {
                                        "compound_or_analyte": "DMT",
                                        "primary_graph_anchor_kind": "target",
                                        "metabolic_or_transport_target": "MAO-A",
                                        "pk_or_exposure_parameter": "metabolism",
                                        "synthesis_interpretation": "MAO-A is central to DMT exposure.",
                                    },
                                }
                            ],
                        },
                    },
                    {
                        "task_id": "route-public-health",
                        "route_id": "route-public-health",
                        "prompt_profile": "secondary_review_coverage",
                        "schema_profile": "review_coverage_schema",
                        "status": "ok",
                        "schema_errors": [],
                        "result": {
                            "schema_version": "review_coverage_v1",
                            "task_id": "route-public-health",
                            "route_id": "route-public-health",
                            "study_doi": "10.1000/public-health-route",
                            "domain_route": "real_world_public_health",
                            "source_type": "review",
                            "text_depth": "abstract_only",
                            "extraction_status": "extracted",
                            "coverage_items": [
                                {
                                    "item_id": "PH1",
                                    "relationship_domain": "real_world_public_health",
                                    "coverage_type": "reviews",
                                    "coverage_focus": "main_focus",
                                    "compound_or_class": "Psilocybin",
                                    "entity_type": "public_health_measure",
                                    "entity": "ethnoracial inclusion",
                                    "summary_statement": "The review covers equity concerns in psychedelic services.",
                                    "direction_or_tone": "descriptive_only",
                                    "study_count": "not_reported",
                                    "confidence": 0.78,
                                    "needs_human_review": False,
                                    "domain_result": {
                                        "exposure_or_intervention": "Psilocybin",
                                        "public_health_measure": "ethnoracial inclusion",
                                        "public_health_topic_category": "access and equity",
                                        "review_interpretation": "Equity is a main public-health topic in the review.",
                                    },
                                }
                            ],
                        },
                    },
                    {
                        "task_id": "route-empty",
                        "route_id": "route-empty",
                        "status": "ok",
                        "result": {
                            "schema_version": "review_coverage_v1",
                            "task_id": "route-empty",
                            "route_id": "route-empty",
                            "study_doi": "10.1000/empty",
                            "domain_route": "clinical_outcome",
                            "source_type": "review",
                            "text_depth": "abstract_only",
                            "extraction_status": "no_extractable_scoped_coverage",
                            "coverage_items": [],
                        },
                    },
                ],
            )
            write_json(
                registry_path,
                {
                    "compounds": [
                        {"label": "Psilocybin", "aliases": [], "ids": {}, "status": "seeded"},
                        {"label": "DMT", "aliases": [], "ids": {}, "status": "seeded"},
                    ],
                    "targets": [
                        {
                            "label": "MAO-A",
                            "aliases": ["monoamine oxidase A"],
                            "ids": {},
                            "status": "needs_external_id_lookup",
                        }
                    ],
                    "disorders": [],
                },
            )

            rows, report = convert_outputs(input_jsonl=outputs_jsonl, tasks_jsonl=tasks_jsonl)
            write_json(evidence_rows_json, rows)

            self.assertEqual(report["rows_written"], 3)
            self.assertEqual(report["skipped"], {"extraction_status:no_extractable_scoped_coverage": 1})
            self.assertEqual({row["source_item_type"] for row in rows}, {"primary_item", "synthesis_result", "review_coverage_item"})
            brain_row = next(row for row in rows if row["domain_route"] == "brain_system")
            self.assertEqual(brain_row["study_title"], "Psilocybin and default mode network connectivity")
            self.assertEqual(brain_row["compound"], "Psilocybin")
            self.assertEqual(brain_row["graph_entity_label"], "DMN")
            self.assertEqual(brain_row["assessment_timepoint"], "2 hours post-dose")
            pk_row = next(row for row in rows if row["domain_route"] == "pharmacokinetics_exposure")
            self.assertEqual(pk_row["pk_relationship_type"], "metabolized_by")
            self.assertEqual(pk_row["pk_relationship_label"], "metabolized by")
            self.assertEqual(pk_row["pk_graph_object_kind"], "enzyme_or_transporter")
            self.assertEqual(pk_row["pk_graph_object_label"], "MAO-A")

            manifest = build_tables(
                graph_sources={
                    "routed_extractions": {
                        "path": evidence_rows_json,
                        "domain": "routed",
                        "dataset": "routed",
                        "default_evidence_type": "primary_evidence",
                        "skip_audit": True,
                    }
                },
                registry_path=registry_path,
                out_dir=out_dir,
                write_duckdb=False,
            )
            self.assertEqual(manifest["tables"]["evidence_edges"]["rows"], 3)
            findings = pd.read_parquet(out_dir / "findings.parquet")
            brain_claim = findings[findings["domain"] == "brain_system"].iloc[0]
            self.assertEqual(brain_claim["assessment_timepoint"], "2 hours post-dose")

            edges = pd.read_parquet(out_dir / "evidence_edges.parquet")
            self.assertEqual(set(edges["domain"]), {"brain_system", "pharmacokinetics_exposure", "real_world_public_health"})
            brain_edge = edges[edges["domain"] == "brain_system"].iloc[0]
            self.assertEqual(brain_edge["entity_label"], "Default mode network")
            self.assertEqual(brain_edge["relation_type"], "has_brain_system_effect")
            pk_edge = edges[edges["domain"] == "pharmacokinetics_exposure"].iloc[0]
            self.assertEqual(pk_edge["entity_kind"], "target")
            self.assertEqual(pk_edge["relation_type"], "discusses_relationship")
            public_health_edge = edges[edges["domain"] == "real_world_public_health"].iloc[0]
            self.assertEqual(public_health_edge["entity_label"], "Access to services")
            self.assertEqual(public_health_edge["relation_type"], "discusses_relationship")


if __name__ == "__main__":
    unittest.main()
