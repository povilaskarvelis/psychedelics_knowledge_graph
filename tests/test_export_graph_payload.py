import unittest

from pipeline.publish.export_graph_payload import (
    DEFAULT_CLAIM_SOURCE,
    claim_source_paths,
    evidence_role_for_row,
    is_secondary_literature_row,
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
