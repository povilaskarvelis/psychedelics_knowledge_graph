import unittest

import pandas as pd

from pipeline.review.run_literature_type_routing import (
    build_rows,
    classify_literature_type,
    metadata_secondary_types,
)


class LiteratureTypeRoutingTest(unittest.TestCase):
    def test_metadata_secondary_types_ignores_peer_review_artifact(self) -> None:
        types, terms = metadata_secondary_types("Journal Article | Review | peer-review")

        self.assertEqual(types, ["review"])
        self.assertEqual(terms, ["Review"])

    def test_classifies_meta_analysis_from_pubmed_metadata(self) -> None:
        row = {
            "study_title": "Ketamine for depression",
            "abstract": "",
            "publication_type": "Journal Article | Meta-Analysis | Systematic Review",
        }

        classification = classify_literature_type(row)

        self.assertEqual(classification["source_family"], "secondary_literature")
        self.assertEqual(classification["primary_secondary_source_type"], "meta_analysis")
        self.assertIn("systematic_review", classification["secondary_source_types"])

    def test_classifies_specific_title_when_metadata_is_generic(self) -> None:
        row = {
            "study_title": "Psilocybin for depression: a systematic review and meta-analysis",
            "abstract": "",
            "publication_type": "Journal Article",
        }

        classification = classify_literature_type(row)

        self.assertEqual(classification["source_family"], "secondary_literature")
        self.assertEqual(classification["primary_secondary_source_type"], "meta_analysis")
        self.assertEqual(classification["literature_type_confidence"], "high")

    def test_review_protocol_routes_as_non_primary_not_completed_review(self) -> None:
        row = {
            "study_title": "Ketamine for depression: protocol for a systematic review",
            "abstract": "",
            "publication_type": "Journal Article",
        }

        classification = classify_literature_type(row)

        self.assertEqual(classification["source_family"], "non_primary_publication")
        self.assertEqual(classification["literature_route"], "non_primary_context_or_skip")
        self.assertIn("review_protocol", classification["non_primary_flags"])

    def test_completed_review_mentioning_protocol_development_stays_secondary(self) -> None:
        row = {
            "study_title": "Adverse event reporting in psilocybin therapy: a systematic review to guide protocol development",
            "abstract": "",
            "publication_type": "Journal Article | Systematic Review",
        }

        classification = classify_literature_type(row)

        self.assertEqual(classification["source_family"], "secondary_literature")
        self.assertNotIn("review_protocol", classification["non_primary_flags"])

    def test_response_as_outcome_does_not_route_as_non_primary(self) -> None:
        row = {
            "study_title": "Proteomic patterns associated with ketamine response in major depressive disorder",
            "abstract": "This study tested biomarkers associated with ketamine treatment response.",
            "publication_type": "Journal Article",
        }

        classification = classify_literature_type(row)

        self.assertEqual(classification["source_family"], "primary_or_unclear")
        self.assertNotIn("non_primary_title", classification["non_primary_flags"])

    def test_response_to_measurement_target_does_not_route_as_non_primary(self) -> None:
        row = {
            "study_title": "Amygdala response to emotional faces following acute administration of psilocybin",
            "abstract": "This study measured amygdala responses to emotional faces.",
            "publication_type": "Journal Article",
        }

        classification = classify_literature_type(row)

        self.assertEqual(classification["source_family"], "primary_or_unclear")
        self.assertNotIn("non_primary_title", classification["non_primary_flags"])

    def test_actual_response_to_article_routes_as_non_primary(self) -> None:
        row = {
            "study_title": "Response to: Ketamine for treatment-resistant depression",
            "abstract": "Letter response.",
            "publication_type": "Journal Article",
        }

        classification = classify_literature_type(row)

        self.assertEqual(classification["source_family"], "non_primary_publication")
        self.assertIn("non_primary_title", classification["non_primary_flags"])

    def test_book_container_routes_as_non_primary_even_with_review_language(self) -> None:
        row = {
            "study_title": "Future Challenges for the Diagnosis and Management of Affective Disorders",
            "abstract": "This book discusses systematic reviews and meta-analyses of affective disorders.",
            "publication_type": "book",
        }

        classification = classify_literature_type(row)

        self.assertEqual(classification["source_family"], "non_primary_publication")
        self.assertEqual(classification["literature_route"], "non_primary_context_or_skip")
        self.assertEqual(classification["literature_type_confidence"], "high")
        self.assertIn("non_paper_container_publication_type", classification["non_primary_flags"])

    def test_build_rows_can_route_only_retained_candidates(self) -> None:
        metadata = pd.DataFrame(
            [
                {
                    "doi": "10.example/retained",
                    "study_title": "Psilocybin for depression: a systematic review",
                    "abstract": "",
                    "publication_type": "Journal Article",
                },
                {
                    "doi": "10.example/excluded",
                    "study_title": "Excluded review",
                    "abstract": "",
                    "publication_type": "Journal Article | Review",
                },
            ]
        )
        decisions = pd.DataFrame(
            [
                {
                    "doi": "10.example/retained",
                    "dataset": "disorder",
                    "prescreen_decision": "retain",
                    "prescreen_action": "retain_for_extraction_candidate",
                    "retained_for_extraction_candidate": True,
                },
                {
                    "doi": "10.example/excluded",
                    "dataset": "disorder",
                    "prescreen_decision": "exclude",
                    "prescreen_action": "exclude_obvious_irrelevant",
                    "retained_for_extraction_candidate": False,
                },
            ]
        )

        rows = build_rows(metadata, decisions, generated_at_utc="now", only_retained=True)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["doi"], "10.example/retained")
        self.assertEqual(rows[0]["source_family"], "secondary_literature")

    def test_excluded_prescreen_row_is_not_routing_ready_candidate(self) -> None:
        metadata = pd.DataFrame(
            [
                {
                    "doi": "10.example/protected",
                    "study_title": "Author Correction: MDMA-assisted therapy",
                    "abstract": "Correction notice.",
                    "publication_type": "Published Erratum",
                }
            ]
        )
        decisions = pd.DataFrame(
            [
                {
                    "doi": "10.example/protected",
                    "dataset": "disorder",
                    "prescreen_decision": "exclude",
                    "prescreen_action": "exclude_non_evidence_artifact",
                    "retained_for_extraction_candidate": False,
                }
            ]
        )

        rows = build_rows(metadata, decisions, generated_at_utc="now", only_retained=True)

        self.assertEqual(rows, [])


if __name__ == "__main__":
    unittest.main()
