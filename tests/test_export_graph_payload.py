import unittest
import tempfile
from pathlib import Path

import pandas as pd

from pipeline.publish.export_graph_payload import (
    DEFAULT_CLAIM_SOURCE,
    claim_source_paths,
    evidence_role_for_row,
    export_dataset,
    is_secondary_literature_row,
    load_claim_rows_for_source,
    rows_for_view,
    schema_path_for_claim_source,
)


class ExportGraphPayloadViewsTest(unittest.TestCase):
    def test_default_claim_source_uses_projected_extraction_claim_files(self) -> None:
        self.assertEqual(DEFAULT_CLAIM_SOURCE, "gemini_extraction")

        paths = claim_source_paths("mechanistic", DEFAULT_CLAIM_SOURCE)

        self.assertTrue(str(paths["claims_json"]).endswith("data/processed/extraction/mechanistic_claims.json"))
        self.assertEqual(paths["claim_source"], "gemini_extraction")

    def test_normalized_claim_source_uses_graph_claim_files(self) -> None:
        paths = claim_source_paths("disorder", "gemini_normalized")

        self.assertTrue(str(paths["claims_json"]).endswith("data/processed/extraction/disorder_graph_claims.json"))
        self.assertEqual(paths["claim_source"], "gemini_normalized")

    def test_kg_tables_source_uses_parquet_and_source_names(self) -> None:
        paths = claim_source_paths("mechanistic", "kg_tables")

        self.assertTrue(str(paths["claims_parquet"]).endswith("data/processed/kg/claims.parquet"))
        self.assertEqual(paths["primary_source_name"], "mechanistic_primary")
        self.assertEqual(paths["secondary_source_name"], "mechanistic_secondary")
        self.assertEqual(paths["claim_source"], "kg_tables")

        disorder_paths = claim_source_paths("disorder", "kg_tables")
        self.assertEqual(disorder_paths["primary_source_name"], ["clinical_primary", "clinical_primary_endpoints"])
        self.assertEqual(disorder_paths["secondary_source_name"], "clinical_secondary")

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
