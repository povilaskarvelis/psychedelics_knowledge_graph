import unittest

from pipeline.publish.export_graph_payload import (
    evidence_role_for_row,
    is_secondary_literature_row,
    rows_for_view,
)


class ExportGraphPayloadViewsTest(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
