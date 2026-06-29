import unittest
import tempfile
import json
from pathlib import Path

import pandas as pd

from pipeline.publish.export_graph_payload import (
    DEFAULT_CLAIM_SOURCE,
    DEFAULT_KG_TABLE_DIR,
    claim_source_paths,
    evidence_role_for_row,
    export_dataset,
    aggregate_payload_summary_stats,
    graph_preview_payload,
    is_secondary_literature_row,
    load_claim_rows_for_source,
    payload_summary_stats,
    rows_for_view,
    schema_path_for_claim_source,
)


class ExportGraphPayloadViewsTest(unittest.TestCase):
    def test_default_claim_source_uses_normalized_kg_tables(self) -> None:
        self.assertEqual(DEFAULT_CLAIM_SOURCE, "kg_tables")

        paths = claim_source_paths("mechanistic", DEFAULT_CLAIM_SOURCE)

        self.assertTrue(str(paths["claims_parquet"]).endswith("data/processed/kg/claims.parquet"))
        self.assertEqual(paths["primary_source_name"], ["mechanistic_primary", "routed_extractions"])
        self.assertEqual(paths["domain_names"], ["brain_system", "mechanistic", "molecular_pathway_readout", "molecular_target", "pharmacokinetics_exposure"])
        self.assertEqual(paths["claim_source"], "kg_tables")

    def test_normalized_claim_source_uses_graph_claim_files(self) -> None:
        paths = claim_source_paths("disorder", "gemini_normalized")

        self.assertTrue(str(paths["claims_json"]).endswith("data/processed/extraction/disorder_graph_claims.json"))
        self.assertEqual(paths["claim_source"], "gemini_normalized")

    def test_kg_tables_source_uses_parquet_and_source_names(self) -> None:
        paths = claim_source_paths("mechanistic", "kg_tables")

        self.assertEqual(paths["claims_parquet"], DEFAULT_KG_TABLE_DIR / "claims.parquet")
        self.assertEqual(paths["primary_source_name"], ["mechanistic_primary", "routed_extractions"])
        self.assertEqual(paths["secondary_source_name"], "mechanistic_secondary")
        self.assertEqual(paths["claim_source"], "kg_tables")

        disorder_paths = claim_source_paths("disorder", "kg_tables")
        self.assertEqual(disorder_paths["primary_source_name"], ["clinical_primary", "clinical_primary_endpoints", "routed_extractions"])
        self.assertEqual(disorder_paths["secondary_source_name"], "clinical_secondary")
        self.assertEqual(
            disorder_paths["domain_names"],
            [
                "clinical",
                "clinical_outcome",
                "cognitive_behavioral",
                "intervention_context",
                "real_world_public_health",
                "safety_tolerability",
                "subjective_experience",
            ],
        )

    def test_kg_tables_source_can_read_from_versioned_kg_directory(self) -> None:
        kg_dir = Path("/tmp/kg_routed_runs/gemini3_flash_first_batch")

        paths = claim_source_paths("mechanistic", "kg_tables", kg_dir=kg_dir)

        self.assertEqual(paths["claims_parquet"], kg_dir / "claims.parquet")
        self.assertEqual(paths["paper_authors_parquet"], kg_dir / "paper_authors.parquet")
        self.assertEqual(paths["primary_source_name"], ["mechanistic_primary", "routed_extractions"])

    def test_legacy_curated_mechanistic_source_uses_legacy_affinity_schema(self) -> None:
        schema_path = schema_path_for_claim_source(
            "mechanistic",
            "legacy_curated",
            {"schema": "schema/claims.schema.json"},
        )

        self.assertTrue(str(schema_path).endswith("schema/legacy_mechanistic_affinity_claims.schema.json"))

    def test_legacy_curated_disorder_source_uses_legacy_disorder_schema(self) -> None:
        schema_path = schema_path_for_claim_source(
            "disorder",
            "legacy_curated",
            {"schema": "schema/disorder_claims.schema.json"},
        )

        self.assertTrue(str(schema_path).endswith("schema/legacy_disorder_claims.schema.json"))

    def test_loads_split_rows_from_kg_claim_table(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "claims.parquet"
            pd.DataFrame(
                [
                    {
                        "claim_id": "claim-1",
                        "source_name": "clinical_primary",
                        "domain": "clinical",
                        "evidence_type": "primary_evidence",
                        "raw_row_json": '{"compound":"Ketamine","disorder":"Depression"}',
                    },
                    {
                        "claim_id": "claim-2",
                        "source_name": "clinical_secondary",
                        "domain": "clinical",
                        "evidence_type": "secondary_literature",
                        "raw_row_json": '{"compound":"Psilocybin","disorder":"PTSD"}',
                    },
                    {
                        "claim_id": "claim-4",
                        "source_name": "clinical_primary_endpoints",
                        "domain": "clinical",
                        "evidence_type": "primary_evidence",
                        "raw_row_json": '{"compound":"Psilocybin","disorder":"WEMWBS"}',
                    },
                    {
                        "claim_id": "claim-3",
                        "source_name": "mechanistic_primary",
                        "domain": "mechanistic",
                        "evidence_type": "primary_evidence",
                        "raw_row_json": '{"compound":"LSD","target":"5-HT2A"}',
                    },
                ]
            ).to_parquet(path, index=False)
            pd.DataFrame(
                [
                    {
                        "claim_id": "claim-1",
                        "evidence_id": "evidence-1",
                        "source_name": "clinical_primary",
                        "domain": "clinical",
                        "entity_kind": "condition_indication",
                        "evidence_type": "primary_evidence",
                        "relation_type": "studied_for_condition",
                    },
                    {
                        "claim_id": "claim-2",
                        "evidence_id": "evidence-2",
                        "source_name": "clinical_secondary",
                        "domain": "clinical",
                        "entity_kind": "symptom_problem",
                        "evidence_type": "secondary_literature",
                        "relation_type": "discusses_relationship",
                    },
                    {
                        "claim_id": "claim-4",
                        "evidence_id": "evidence-4",
                        "source_name": "clinical_primary_endpoints",
                        "domain": "clinical",
                        "entity_kind": "outcome_scale",
                        "evidence_type": "primary_evidence",
                        "relation_type": "reports_outcome_scale",
                    },
                ]
            ).to_parquet(Path(tmpdir) / "evidence_edges.parquet", index=False)

            rows, secondary_rows = load_claim_rows_for_source(
                "disorder",
                "kg_tables",
                {
                    "claims_parquet": path,
                    "primary_source_name": ["clinical_primary", "clinical_primary_endpoints"],
                    "secondary_source_name": "clinical_secondary",
                },
            )

        self.assertEqual(
            rows,
            [
                {
                    "compound": "Ketamine",
                    "disorder": "Depression",
                    "kg_claim_id": "claim-1",
                    "kg_evidence_id": "evidence-1",
                    "kg_source_name": "clinical_primary",
                    "kg_domain": "clinical",
                    "kg_entity_kind": "condition_indication",
                    "kg_evidence_type": "primary_evidence",
                    "kg_relation_type": "studied_for_condition",
                },
                {
                    "compound": "Psilocybin",
                    "disorder": "WEMWBS",
                    "kg_claim_id": "claim-4",
                    "kg_evidence_id": "evidence-4",
                    "kg_source_name": "clinical_primary_endpoints",
                    "kg_domain": "clinical",
                    "kg_entity_kind": "outcome_scale",
                    "kg_evidence_type": "primary_evidence",
                    "kg_relation_type": "reports_outcome_scale",
                },
            ],
        )
        self.assertEqual(
            secondary_rows,
            [
                {
                    "compound": "Psilocybin",
                    "disorder": "PTSD",
                    "kg_claim_id": "claim-2",
                    "kg_evidence_id": "evidence-2",
                    "kg_source_name": "clinical_secondary",
                    "kg_domain": "clinical",
                    "kg_entity_kind": "symptom_problem",
                    "kg_evidence_type": "secondary_literature",
                    "kg_relation_type": "discusses_relationship",
                }
            ],
        )

    def test_routed_kg_rows_are_adapted_for_current_ui_payload_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "claims.parquet"
            pd.DataFrame(
                [
                    {
                        "claim_id": "claim-routed",
                        "source_name": "routed_extractions",
                        "domain": "molecular_pathway_readout",
                        "evidence_type": "primary_evidence",
                        "raw_row_json": json.dumps(
                            {
                                "compound": "LSD",
                                "graph_entity_label": "ERK signaling",
                                "paper_type": "primary_study",
                                "source_type": "primary",
                                "paper_assessment_route": "primary_evidence",
                                "access_level": "article_text",
                                "evidence_location": "Results [C003]",
                                "study_year": "2024",
                            }
                        ),
                    }
                ]
            ).to_parquet(path, index=False)

            rows, secondary_rows = load_claim_rows_for_source(
                "mechanistic",
                "kg_tables",
                {
                    "claims_parquet": path,
                    "primary_source_name": ["mechanistic_primary", "routed_extractions"],
                    "secondary_source_name": "mechanistic_secondary",
                    "domain_names": ["mechanistic", "molecular_pathway_readout"],
                },
            )

        self.assertEqual(secondary_rows, [])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["target"], "ERK signaling")
        self.assertNotIn("claim_type", rows[0])
        self.assertEqual(rows[0]["finding_type"], "molecular_pathway_readout")
        self.assertEqual(rows[0]["paper_type"], "primary_results")
        self.assertEqual(rows[0]["source_type"], "primary_study")
        self.assertEqual(rows[0]["access_level"], "full_text_seen")
        self.assertEqual(rows[0]["evidence_location"], "text")
        self.assertEqual(rows[0]["support"], "supported")

    def test_secondary_literature_detection_is_focused_on_reviews_and_meta_analyses(self) -> None:
        self.assertTrue(
            is_secondary_literature_row(
                {
                    "source_family": "evidence_synthesis",
                    "source_type": "secondary_evidence",
                    "paper_type": "systematic_review",
                }
            )
        )
        self.assertTrue(is_secondary_literature_row({"paper_type": "meta_analysis"}))
        self.assertFalse(
            is_secondary_literature_row(
                {
                    "kg_evidence_type": "primary_evidence",
                    "source_family": "evidence_synthesis",
                    "source_type": "review",
                    "paper_type": "review",
                }
            )
        )
        self.assertFalse(is_secondary_literature_row({"source_type": "commentary", "paper_type": "commentary"}))
        self.assertFalse(is_secondary_literature_row({"source_type": "study_protocol", "paper_type": "protocol"}))

    def test_primary_with_secondary_view_excludes_commentary_context(self) -> None:
        primary = {
            "compound": "Psilocybin",
            "disorder": "Major depressive disorder",
            "study_doi": "10.1000/primary",
            "source_type": "primary_study",
            "paper_type": "primary_results",
            "access_level": "full_text_seen",
        }
        commentary = {
            "compound": "Psilocybin",
            "disorder": "Major depressive disorder",
            "study_doi": "10.1000/commentary",
            "source_type": "commentary",
            "paper_type": "commentary",
            "access_level": "full_text_seen",
        }
        review = {
            "compound": "Psilocybin",
            "disorder": "Major depressive disorder",
            "study_doi": "10.1000/review",
            "source_type": "secondary_evidence",
            "paper_type": "systematic_review",
            "access_level": "full_text_seen",
        }

        rows = rows_for_view(
            [primary, commentary],
            view="primary_with_secondary",
            secondary_rows=[review],
            id_fields=["compound", "disorder", "study_doi"],
        )

        self.assertEqual([row["study_doi"] for row in rows], ["10.1000/primary", "10.1000/review"])

    def test_primary_with_secondary_preserves_duplicate_primary_extraction_rows(self) -> None:
        primary = {
            "compound": "Psilocybin",
            "disorder": "Major depressive disorder",
            "study_doi": "10.1000/primary",
            "source_type": "primary_study",
            "paper_type": "primary_results",
            "access_level": "full_text_seen",
        }

        rows = rows_for_view(
            [primary, dict(primary)],
            view="primary_with_secondary",
            secondary_rows=[],
            id_fields=["compound", "disorder", "study_doi"],
        )

        self.assertEqual(len(rows), 2)

    def test_evidence_role_marks_secondary_literature(self) -> None:
        self.assertEqual(
            evidence_role_for_row({"source_type": "secondary_evidence", "paper_type": "review"}),
            "secondary_literature",
        )
        self.assertEqual(
            evidence_role_for_row(
                {"source_type": "primary_study", "paper_type": "primary_results", "access_level": "full_text_seen"}
            ),
            "primary_evidence",
        )

    def test_payload_summary_stats_count_studies_and_public_entities(self) -> None:
        payload = {
            "contributions": [
                {
                    "paper": {"doi": "10.1000/A"},
                    "resources": {"compound": "Psilocybin", "disorder": "Depression"},
                    "properties": {"kg_entity_kind": "condition_indication"},
                },
                {
                    "paper": {"doi": "10.1000/A"},
                    "resources": {"compound": "Psilocybin", "target": "5-HT2A"},
                    "properties": {"kg_entity_kind": "target"},
                },
                {
                    "paper": {"openalex_id": "W123"},
                    "resources": {"compound": "LSD", "target": "5-HT2A"},
                    "properties": {"entity_kind": "target"},
                },
            ]
        }

        self.assertEqual(
            payload_summary_stats(payload),
            {
                "row_count": 3,
                "study_count": 2,
                "compound_count": 2,
                "indication_count": 1,
                "target_count": 1,
            },
        )

    def test_aggregate_payload_summary_stats_deduplicates_across_datasets(self) -> None:
        disorder_payload = {
            "contributions": [
                {
                    "paper": {"doi": "10.1000/shared"},
                    "resources": {"compound": "Psilocybin", "disorder": "Depression"},
                    "properties": {"kg_entity_kind": "condition_indication"},
                }
            ]
        }
        mechanistic_payload = {
            "contributions": [
                {
                    "paper": {"doi": "10.1000/shared"},
                    "resources": {"compound": "Psilocybin", "target": "5-HT2A"},
                    "properties": {"kg_entity_kind": "target"},
                },
                {
                    "paper": {"doi": "10.1000/mech"},
                    "resources": {"compound": "LSD", "target": "BDNF"},
                    "properties": {"kg_entity_kind": "target"},
                },
            ]
        }

        self.assertEqual(
            aggregate_payload_summary_stats([disorder_payload, mechanistic_payload]),
            {
                "row_count": 3,
                "study_count": 2,
                "compound_count": 2,
                "indication_count": 1,
                "target_count": 2,
            },
        )

    def test_graph_preview_payload_keeps_only_fast_chart_fields(self) -> None:
        payload = {
            "contract_version": "1.0",
            "dataset": "disorder",
            "evidence_view": "all_evidence",
            "evidence_source": "kg_tables",
            "evidence_source_label": "Normalized KG evidence tables",
            "contributions": [
                {
                    "paper": {
                        "doi": "10.1000/example",
                        "openalex_id": "W123",
                        "title": "Example",
                        "year": 2024,
                        "journal": "Journal of Careful Tests",
                        "publication_type": "journal-article",
                        "open_access_is_oa": True,
                        "trial_registry_ids": "NCT01234567",
                        "first_author": {"id": "A1", "name": "Ada Lovelace"},
                        "authors": "Ada Lovelace",
                    },
                    "resources": {"compound": "Psilocybin", "disorder": "Depression"},
                    "properties": {
                        "kg_entity_kind": "condition_indication",
                        "evidence_level": "high",
                        "system": "clinical",
                        "population": "patients with depression",
                        "outcome_type": "symptom_change",
                        "result_direction": "positive",
                        "outcome_measure_normalized": "MADRS",
                        "comparator_normalized": "Placebo / vehicle",
                        "follow_up_window_normalized": "Short follow-up (1-4 weeks)",
                        "supporting_quote": "Large text should stay out of preview.",
                    },
                    "extracted_variables": {"sample_size_total": "42"},
                    "provenance": {
                        "paper_assessment_route": "primary_evidence",
                        "paper_type": "primary_results",
                        "source_type": "primary_study",
                        "access_level": "full_text_seen",
                        "study_design": "randomized controlled trial",
                    },
                }
            ],
        }

        preview = graph_preview_payload(payload)

        self.assertEqual(preview["row_count"], 1)
        self.assertEqual(
            preview["findings"],
            [
                {
                    "compound": "Psilocybin",
                    "disorder": "Depression",
                    "kg_entity_kind": "condition_indication",
                    "entity_kind": "condition_indication",
                    "evidence_level": "high",
                    "paper_assessment_route": "primary_evidence",
                    "paper_type": "primary_results",
                    "source_type": "primary_study",
                    "access_level": "full_text_seen",
                    "source_access_level": "full_text_seen",
                    "study_doi": "10.1000/example",
                    "openalex_id": "W123",
                    "study_year": 2024,
                    "study_journal": "Journal of Careful Tests",
                    "publication_type": "journal-article",
                    "open_access_is_oa": True,
                    "trial_registry_ids": "NCT01234567",
                    "first_author": {"id": "A1", "name": "Ada Lovelace"},
                    "system": "clinical",
                    "population": "patients with depression",
                    "study_design": "randomized controlled trial",
                    "sample_size_total": "42",
                    "outcome_type": "symptom_change",
                    "result_direction": "positive",
                    "outcome_measure_normalized": "MADRS",
                    "comparator_normalized": "Placebo / vehicle",
                    "follow_up_window_normalized": "Short follow-up (1-4 weeks)",
                }
            ],
        )
        self.assertNotIn("authors", preview["findings"][0])
        self.assertNotIn("supporting_quote", preview["findings"][0])
        self.assertEqual(
            evidence_role_for_row(
                {
                    "paper_assessment_route": "primary_evidence",
                    "source_type": "case_report",
                    "paper_type": "case_report",
                    "access_level": "full_text_seen",
                }
            ),
            "primary_evidence",
        )


if __name__ == "__main__":
    unittest.main()
