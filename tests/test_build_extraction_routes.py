import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from pipeline.extract.build_extraction_routes import (
    build_route_rows,
    doi_to_slug,
    prescreen_context_by_doi,
)


class BuildExtractionRoutesTests(unittest.TestCase):
    def test_primary_paper_uses_general_route_without_domain_table(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fulltext_dir = Path(tmp) / "fulltext"
            doi = "10.1000/primary"
            artifact = fulltext_dir / "mechanistic" / f"{doi_to_slug(doi)}.json"
            artifact.parent.mkdir(parents=True)
            artifact.write_text(json.dumps({"best_char_count": 1200}), encoding="utf-8")

            metadata_df = pd.DataFrame(
                [
                    {
                        "doi": doi,
                        "datasets": "mechanistic|clinical",
                        "study_title": "Psilocybin trial with imaging outcomes",
                        "study_year": "2024",
                        "abstract": "Patients were randomized and brain network outcomes were measured.",
                        "publication_type": "Journal Article | Randomized Controlled Trial",
                        "trial_registry_ids": "NCT1",
                        "best_pdf_url": "https://example.org/paper.pdf",
                        "open_access_status": "gold",
                    }
                ]
            )
            prescreen_df = pd.DataFrame(
                [
                    {
                        "doi": doi,
                        "dataset": "clinical",
                        "prescreen_decision": "retain",
                        "retained_for_extraction_candidate": True,
                        "prescreen_action": "retain_for_extraction_candidate",
                        "routing_tags": "clinical_outcome|safety|bridge_clinical_mechanism",
                    }
                ]
            )
            literature_df = pd.DataFrame(
                [
                    {
                        "doi": doi,
                        "retained_for_extraction_candidate": True,
                        "source_family": "primary_or_unclear",
                        "literature_type_confidence": "medium",
                    }
                ]
            )

            rows = build_route_rows(
                metadata_df,
                prescreen_df,
                literature_df,
                fulltext_dir=fulltext_dir,
                generated_at_utc="2026-05-28T00:00:00+00:00",
            )

        self.assertEqual({row["domain_route"] for row in rows}, {"general_primary"})
        self.assertEqual({row["prompt_profile"] for row in rows}, {"primary_general"})
        self.assertTrue(all(row["access_tier"] == "full_text_available" for row in rows))
        self.assertTrue(all(row["has_converted_full_text"] for row in rows))
        self.assertTrue(all(row["bridge_clinical_mechanism"] for row in rows))
        self.assertTrue(all(row["route_action"] == "extract_from_full_text" for row in rows))

    def test_secondary_meta_analysis_uses_general_review_profile_without_domain_table(self) -> None:
        metadata_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/meta",
                    "study_title": "A meta-analysis of MDMA treatment",
                    "study_year": "2022",
                    "abstract": "This meta-analysis reviewed randomized trials.",
                    "publication_type": "Journal Article | Meta-Analysis",
                    "best_pdf_url": "",
                }
            ]
        )
        prescreen_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/meta",
                    "dataset": "clinical",
                    "prescreen_decision": "retain",
                    "retained_for_extraction_candidate": True,
                    "prescreen_action": "retain_for_extraction_candidate",
                    "routing_tags": "clinical_outcome|molecular_target",
                }
            ]
        )
        literature_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/meta",
                    "retained_for_extraction_candidate": True,
                    "source_family": "secondary_literature",
                    "primary_secondary_source_type": "meta_analysis",
                    "secondary_source_types": "meta_analysis|review",
                    "literature_type_confidence": "high",
                }
            ]
        )

        rows = build_route_rows(
            metadata_df,
            prescreen_df,
            literature_df,
            fulltext_dir=Path("/tmp/does-not-exist"),
            generated_at_utc="2026-05-28T00:00:00+00:00",
        )

        self.assertEqual({row["domain_route"] for row in rows}, {"general_topic_coverage"})
        self.assertEqual({row["prompt_profile"] for row in rows}, {"secondary_meta_analysis"})
        self.assertEqual({row["schema_profile"] for row in rows}, {"synthesis_evidence_schema"})
        self.assertEqual({row["access_tier"] for row in rows}, {"abstract_only"})
        self.assertEqual({row["route_confidence"] for row in rows}, {"low"})
        self.assertIn("no model-assigned domain table supplied", rows[0]["route_basis"])

    def test_primary_gap_domain_tags_do_not_create_specific_routes_without_domain_table(self) -> None:
        metadata_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/gaps",
                    "study_title": "Psilocybin session and exposure study",
                    "abstract": "The study measured plasma concentration, mystical experience, and preparation.",
                    "publication_type": "Journal Article",
                    "best_pdf_url": "",
                }
            ]
        )
        prescreen_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/gaps",
                    "dataset": "mechanistic",
                    "prescreen_decision": "retain",
                    "retained_for_extraction_candidate": True,
                    "prescreen_action": "retain_for_extraction_candidate",
                    "routing_tags": "subjective_experience|pharmacokinetics_exposure|intervention_context|real_world_use_public_health",
                }
            ]
        )
        literature_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/gaps",
                    "retained_for_extraction_candidate": True,
                    "source_family": "primary_or_unclear",
                    "literature_type_confidence": "medium",
                }
            ]
        )

        rows = build_route_rows(
            metadata_df,
            prescreen_df,
            literature_df,
            fulltext_dir=Path("/tmp/does-not-exist"),
            generated_at_utc="2026-05-28T00:00:00+00:00",
        )

        self.assertEqual({row["domain_route"] for row in rows}, {"general_primary"})
        self.assertEqual({row["prompt_profile"] for row in rows}, {"primary_general"})
        self.assertEqual(rows[0]["domain_tags"], "")
        self.assertIn("no model-assigned domain table supplied", rows[0]["route_basis"])

    def test_domain_routing_table_overrides_prescreen_tag_fallback(self) -> None:
        metadata_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/domain-table",
                    "study_title": "Psilocybin and brain network connectivity",
                    "abstract": "Brain network outcomes were measured.",
                    "publication_type": "Journal Article",
                    "best_pdf_url": "",
                }
            ]
        )
        prescreen_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/domain-table",
                    "dataset": "mechanistic",
                    "prescreen_decision": "retain",
                    "retained_for_extraction_candidate": True,
                    "prescreen_action": "retain_for_extraction_candidate",
                    "routing_tags": "clinical_outcome|brain_system",
                }
            ]
        )
        literature_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/domain-table",
                    "retained_for_extraction_candidate": True,
                    "source_family": "primary_or_unclear",
                    "literature_type_confidence": "medium",
                }
            ]
        )
        domain_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/domain-table",
                    "retained_for_extraction_candidate": True,
                    "domain_route": "brain_system",
                    "domain_tag": "brain_system",
                    "all_domain_tags": "clinical_outcome|brain_system",
                    "primary_domain": "brain_system",
                    "screening_decision": "include_for_extraction",
                    "screening_reason": "In-scope brain-system evidence.",
                    "methodological_validity_tags": "blinding_expectancy_validity",
                    "domain_route_confidence": "medium",
                    "domain_route_basis": "domain tag:brain_system",
                    "needs_human_review": True,
                    "model": "gemini-3-flash-preview",
                }
            ]
        )

        rows = build_route_rows(
            metadata_df,
            prescreen_df,
            literature_df,
            domain_df,
            fulltext_dir=Path("/tmp/does-not-exist"),
            generated_at_utc="2026-05-28T00:00:00+00:00",
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["domain_route"], "brain_system")
        self.assertEqual(rows[0]["prompt_profile"], "primary_brain_system")
        self.assertEqual(rows[0]["domain_routing_primary_domain"], "brain_system")
        self.assertEqual(rows[0]["domain_screening_decision"], "include_for_extraction")
        self.assertEqual(rows[0]["domain_screening_reason"], "In-scope brain-system evidence.")
        self.assertEqual(rows[0]["methodological_validity_tags"], "blinding_expectancy_validity")
        self.assertEqual(rows[0]["domain_routing_model"], "gemini-3-flash-preview")
        self.assertTrue(rows[0]["domain_needs_human_review"])
        self.assertIn("domain_route_basis:domain tag:brain_system", rows[0]["route_basis"])

    def test_methodological_validity_tags_do_not_replace_domain_route(self) -> None:
        metadata_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/methods",
                    "study_title": "Blinding in psychedelic trials",
                    "abstract": "The study evaluates expectancy and blinding validity.",
                    "publication_type": "Journal Article",
                    "best_pdf_url": "",
                }
            ]
        )
        prescreen_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/methods",
                    "dataset": "clinical",
                    "prescreen_decision": "retain",
                    "retained_for_extraction_candidate": True,
                    "prescreen_action": "retain_for_extraction_candidate",
                    "routing_tags": "",
                }
            ]
        )
        literature_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/methods",
                    "retained_for_extraction_candidate": True,
                    "source_family": "primary_or_unclear",
                    "literature_type_confidence": "medium",
                }
            ]
        )
        domain_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/methods",
                    "retained_for_extraction_candidate": True,
                    "domain_route": "clinical_outcome",
                    "domain_tag": "clinical_outcome",
                    "all_domain_tags": "clinical_outcome",
                    "primary_domain": "clinical_outcome",
                    "screening_decision": "include_for_extraction",
                    "methodological_validity_tags": "blinding_expectancy_validity",
                    "domain_route_confidence": "high",
                    "domain_route_basis": "domain tag:clinical_outcome",
                    "needs_human_review": False,
                    "model": "gemini-3-flash-preview",
                }
            ]
        )

        rows = build_route_rows(
            metadata_df,
            prescreen_df,
            literature_df,
            domain_df,
            fulltext_dir=Path("/tmp/does-not-exist"),
            generated_at_utc="2026-05-28T00:00:00+00:00",
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["domain_route"], "clinical_outcome")
        self.assertEqual(rows[0]["prompt_profile"], "primary_clinical")
        self.assertEqual(rows[0]["methodological_validity_tags"], "blinding_expectancy_validity")
        self.assertEqual(rows[0]["schema_profile"], "primary_evidence_schema")

    def test_model_excluded_record_does_not_create_extraction_task(self) -> None:
        metadata_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/out",
                    "study_title": "Non-psychedelic depression paper",
                    "abstract": "This paper studies a non-psychedelic treatment.",
                    "publication_type": "Journal Article",
                    "best_pdf_url": "",
                }
            ]
        )
        prescreen_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/out",
                    "dataset": "clinical",
                    "prescreen_decision": "retain",
                    "retained_for_extraction_candidate": True,
                    "prescreen_action": "retain_for_extraction_candidate",
                    "routing_tags": "clinical_outcome",
                }
            ]
        )
        literature_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/out",
                    "retained_for_extraction_candidate": True,
                    "source_family": "primary_or_unclear",
                    "literature_type_confidence": "medium",
                }
            ]
        )
        domain_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/out",
                    "retained_for_extraction_candidate": False,
                    "domain_route": "general_topic",
                    "domain_tag": "",
                    "all_domain_tags": "",
                    "primary_domain": "general_topic",
                    "screening_decision": "exclude_out_of_scope",
                    "screening_reason": "No in-scope psychedelic evidence.",
                    "methodological_validity_tags": "",
                    "domain_route_confidence": "high",
                    "domain_route_basis": "Gemini title/abstract domain routing: out of scope",
                    "needs_human_review": False,
                    "model": "gemini-3-flash-preview",
                }
            ]
        )

        rows = build_route_rows(
            metadata_df,
            prescreen_df,
            literature_df,
            domain_df,
            fulltext_dir=Path("/tmp/does-not-exist"),
            generated_at_utc="2026-05-28T00:00:00+00:00",
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["domain_route"], "screening_excluded")
        self.assertEqual(rows[0]["route_action"], "exclude_after_model_screen")
        self.assertEqual(rows[0]["prompt_profile"], "no_extraction")
        self.assertEqual(rows[0]["schema_profile"], "no_extraction_schema")
        self.assertFalse(rows[0]["retained_for_extraction_candidate"])
        self.assertEqual(rows[0]["domain_screening_decision"], "exclude_out_of_scope")

    def test_non_primary_publication_collapses_to_context_route(self) -> None:
        metadata_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/editorial",
                    "study_title": "Editorial on psychedelic therapy",
                    "abstract": "This editorial discusses the field.",
                    "publication_type": "Editorial",
                    "best_pdf_url": "",
                }
            ]
        )
        prescreen_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/editorial",
                    "dataset": "clinical",
                    "prescreen_decision": "retain",
                    "retained_for_extraction_candidate": True,
                    "prescreen_action": "retain_for_extraction_candidate",
                    "routing_tags": "clinical_outcome|safety|molecular_target",
                }
            ]
        )
        literature_df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/editorial",
                    "retained_for_extraction_candidate": True,
                    "source_family": "non_primary_publication",
                    "non_primary_flags": "non_primary_publication_type",
                    "literature_type_confidence": "medium",
                }
            ]
        )

        rows = build_route_rows(
            metadata_df,
            prescreen_df,
            literature_df,
            fulltext_dir=Path("/tmp/does-not-exist"),
            generated_at_utc="2026-05-28T00:00:00+00:00",
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["domain_route"], "context_only")
        self.assertEqual(rows[0]["prompt_profile"], "context_only_or_skip")
        self.assertEqual(rows[0]["schema_profile"], "context_only_schema")
        self.assertEqual(rows[0]["route_action"], "skip_or_context_only")

    def test_prescreen_context_ignores_excluded_rows(self) -> None:
        df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/a",
                    "dataset": "clinical",
                    "prescreen_decision": "exclude",
                    "retained_for_extraction_candidate": False,
                    "routing_tags": "clinical_outcome",
                },
                {
                    "doi": "10.1000/a",
                    "dataset": "mechanistic",
                    "prescreen_decision": "retain",
                    "retained_for_extraction_candidate": True,
                    "routing_tags": "molecular_target",
                },
            ]
        )

        context = prescreen_context_by_doi(df)

        self.assertEqual(context["10.1000/a"]["datasets"], ["mechanistic"])
        self.assertEqual(context["10.1000/a"]["routing_tags"], ["molecular_target"])


if __name__ == "__main__":
    unittest.main()
