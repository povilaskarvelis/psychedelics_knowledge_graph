import unittest

import pandas as pd

from pipeline.review.run_domain_routing import build_rows


class DomainRoutingTest(unittest.TestCase):
    def test_build_rows_routes_retained_dois_to_each_domain(self) -> None:
        decisions = pd.DataFrame(
            [
                {
                    "run_id": "run-a",
                    "doi": "10.example/a",
                    "dataset": "disorder",
                    "study_title": "Psilocybin therapy with fMRI outcomes",
                    "study_year": "2024",
                    "prescreen_decision": "retain",
                    "retained_for_extraction_candidate": True,
                    "prescreen_action": "retain_for_extraction_candidate",
                    "deterministic_routing_tags": "clinical_outcome|brain_system|bridge_clinical_mechanism",
                },
                {
                    "run_id": "run-a",
                    "doi": "10.example/a",
                    "dataset": "mechanistic",
                    "study_title": "Psilocybin therapy with fMRI outcomes",
                    "study_year": "2024",
                    "prescreen_decision": "retain",
                    "retained_for_extraction_candidate": True,
                    "prescreen_action": "retain_for_extraction_candidate",
                    "deterministic_routing_tags": "molecular_target|brain_system",
                },
                {
                    "run_id": "run-a",
                    "doi": "10.example/excluded",
                    "dataset": "disorder",
                    "prescreen_decision": "exclude",
                    "retained_for_extraction_candidate": False,
                    "prescreen_action": "exclude_obvious_irrelevant",
                    "deterministic_routing_tags": "clinical_outcome",
                },
            ]
        )

        rows = build_rows(decisions, generated_at_utc="now")

        self.assertEqual({row["doi"] for row in rows}, {"10.example/a"})
        self.assertEqual(
            {row["domain_route"] for row in rows},
            {"clinical_outcome", "molecular_target", "brain_system"},
        )
        self.assertTrue(all(row["bridge_clinical_mechanism"] for row in rows))
        self.assertTrue(all(row["domain_route_confidence"] == "medium" for row in rows))

    def test_build_rows_adds_general_topic_fallback_without_domain_tags(self) -> None:
        decisions = pd.DataFrame(
            [
                {
                    "run_id": "run-a",
                    "doi": "10.example/general",
                    "dataset": "mechanistic",
                    "study_title": "Psychedelic overview",
                    "prescreen_decision": "retain",
                    "retained_for_extraction_candidate": True,
                    "prescreen_action": "retain_for_extraction_candidate",
                    "deterministic_routing_tags": "uncertain",
                },
            ]
        )

        rows = build_rows(decisions, generated_at_utc="now")

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["domain_route"], "general_topic")
        self.assertEqual(rows[0]["domain_route_confidence"], "low")
        self.assertEqual(rows[0]["all_domain_tags"], "uncertain")

    def test_build_rows_filters_broad_search_terms_for_domain_routes(self) -> None:
        decisions = pd.DataFrame(
            [
                {
                    "run_id": "run-a",
                    "doi": "10.example/broad",
                    "dataset": "mechanistic",
                    "study_title": "Population receptor model",
                    "prescreen_decision": "retain",
                    "retained_for_extraction_candidate": True,
                    "prescreen_action": "retain_for_extraction_candidate",
                    "deterministic_routing_tags": "molecular_target|real_world_use_public_health|intervention_context",
                },
            ]
        )
        metadata = pd.DataFrame(
            [
                {
                    "doi": "10.example/broad",
                    "study_title": "Population receptor model",
                    "abstract": "This binding assay studied a receptor population after drug treatment.",
                    "mesh_terms": "",
                    "keywords": "",
                    "publication_type": "Journal Article",
                },
            ]
        )

        rows = build_rows(decisions, metadata, generated_at_utc="now")

        self.assertEqual({row["domain_route"] for row in rows}, {"molecular_target"})

    def test_build_rows_keeps_strong_public_health_and_intervention_terms(self) -> None:
        decisions = pd.DataFrame(
            [
                {
                    "run_id": "run-a",
                    "doi": "10.example/survey",
                    "dataset": "disorder",
                    "study_title": "Psychedelic retreat survey",
                    "prescreen_decision": "retain",
                    "retained_for_extraction_candidate": True,
                    "prescreen_action": "retain_for_extraction_candidate",
                    "deterministic_routing_tags": "intervention_context|real_world_use_public_health",
                },
            ]
        )
        metadata = pd.DataFrame(
            [
                {
                    "doi": "10.example/survey",
                    "study_title": "Psychedelic retreat survey",
                    "abstract": "Participants completed a survey after preparation and integration sessions.",
                    "mesh_terms": "",
                    "keywords": "",
                    "publication_type": "Journal Article",
                },
            ]
        )

        rows = build_rows(decisions, metadata, generated_at_utc="now")

        self.assertEqual({row["domain_route"] for row in rows}, {"intervention_context", "real_world_public_health"})


if __name__ == "__main__":
    unittest.main()
