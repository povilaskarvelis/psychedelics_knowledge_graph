import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from pipeline.extract.extraction_v1_utils import write_json
from pipeline.kg.build_evidence_tables import build_tables
from pipeline.kg.convert_routed_extractions_to_evidence_rows import convert_outputs


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


class ConvertRoutedExtractionsToEvidenceRowsTest(unittest.TestCase):
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
                                    "compound_or_class": "Psychedelic therapy",
                                    "entity_type": "public_health_measure",
                                    "entity": "ethnoracial inclusion",
                                    "summary_statement": "The review covers equity concerns in psychedelic services.",
                                    "direction_or_tone": "descriptive_only",
                                    "study_count": "not_reported",
                                    "confidence": 0.78,
                                    "needs_human_review": False,
                                    "domain_result": {
                                        "exposure_or_intervention": "Psychedelic therapy",
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
                        {"label": "Psychedelic therapy", "aliases": [], "ids": {}, "status": "seeded"},
                    ],
                    "targets": [],
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
            claims = pd.read_parquet(out_dir / "claims.parquet")
            brain_claim = claims[claims["domain"] == "brain_system"].iloc[0]
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
            self.assertEqual(public_health_edge["entity_label"], "Equity")
            self.assertEqual(public_health_edge["relation_type"], "discusses_relationship")


if __name__ == "__main__":
    unittest.main()
