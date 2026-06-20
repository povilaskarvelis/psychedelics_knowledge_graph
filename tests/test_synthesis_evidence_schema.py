import copy
import json
import unittest
from pathlib import Path

from jsonschema import Draft7Validator


ROOT = Path(__file__).resolve().parents[1]


def load_schema() -> dict:
    return json.loads((ROOT / "schema" / "synthesis_evidence.schema.json").read_text(encoding="utf-8"))


def valid_payload() -> dict:
    quote = "Five randomized trials involving 238 participants were included in the meta-analysis."
    return {
        "schema_version": "synthesis_evidence_v1",
        "task_id": "route-meta-clinical",
        "route_id": "route-meta-clinical",
        "study_doi": "10.1000/meta",
        "domain_route": "clinical_outcome",
        "source_type": "meta_analysis",
        "extraction_status": "extracted",
        "synthesis_assessment": {
            "is_in_scope": True,
            "is_meta_analysis": True,
            "is_network_meta_analysis": False,
            "has_extractable_quantitative_results": True,
            "relationship_domain": "clinical_outcome",
            "population_or_system": "Adults with depressive symptoms",
            "primary_compounds_or_classes": "psilocybin",
            "primary_entities": "depressive symptoms",
            "needs_human_review": False,
            "reasoning_summary": "The paper reports a pooled clinical outcome estimate.",
            "evidence_location": "abstract",
            "evidence_locator": "Abstract",
            "supporting_quote": quote,
        },
        "search_methods": {
            "databases_searched": "MEDLINE, Embase, PsycINFO",
            "search_start_date": "not_reported",
            "search_end_date": "2024-01-31",
            "last_search_date": "2024-01-31",
            "search_strategy_summary": "Search terms combined psilocybin and depression.",
            "registration_id": "PROSPERO CRD42000000000",
            "protocol_doi": "not_reported",
            "evidence_location": "text",
            "evidence_locator": "Methods",
            "supporting_quote": "We searched MEDLINE, Embase, and PsycINFO through January 31, 2024.",
        },
        "eligibility_criteria": {
            "population_or_system": "Adults with depressive symptoms",
            "intervention_or_exposure": "psilocybin-assisted therapy",
            "comparators": "placebo or active control",
            "eligible_outcomes_or_entities": "depressive symptom severity",
            "eligible_study_designs": "randomized clinical trials",
            "date_or_language_limits": "English-language articles",
            "exclusion_criteria": "nonrandomized studies",
            "evidence_location": "text",
            "evidence_locator": "Eligibility criteria",
            "supporting_quote": "Eligible studies were randomized clinical trials of psilocybin-assisted therapy for depressive symptoms.",
        },
        "included_evidence_summary": {
            "included_study_count": "5",
            "included_participant_count": "238",
            "included_experiment_or_assay_count": "not_applicable",
            "included_studies_completeness": "partial",
            "included_studies_not_enumerated_reason": "The supplied input lists only selected study rows.",
            "study_year_range": "2016-2023",
            "country_or_region_summary": "United States and Europe",
            "evidence_location": "abstract",
            "evidence_locator": "Abstract",
            "supporting_quote": quote,
        },
        "included_studies": [
            {
                "study_label": "Carhart-Harris 2021",
                "study_doi": "10.1000/included",
                "trial_registry_ids": "NCT00000000",
                "title": "Trial of psilocybin therapy",
                "first_author": "Carhart-Harris",
                "publication_year": "2021",
                "study_design": "randomized clinical trial",
                "sample_size_total": "59",
                "population_or_system": "Adults with major depressive disorder",
                "compound_or_intervention": "psilocybin-assisted therapy",
                "comparator": "escitalopram",
                "outcomes_or_entities_contributed": "depressive symptom severity",
                "included_in_result_ids": ["R1"],
                "evidence_location": "table",
                "evidence_locator": "Table 1",
                "supporting_quote": "Carhart-Harris 2021 | NCT00000000 | 59 participants | psilocybin vs escitalopram",
                "confidence": 0.9,
                "needs_human_review": False,
            }
        ],
        "synthesis_results": [
            {
                "result_id": "R1",
                "relationship_domain": "clinical_outcome",
                "compound_or_class": "psilocybin",
                "entity_type": "disorder",
                "entity": "depressive symptoms",
                "population_or_system": "Adults with depressive symptoms",
                "intervention_or_exposure": "psilocybin-assisted therapy",
                "comparator": "placebo or active control",
                "outcome_or_endpoint": "depressive symptom severity",
                "outcome_measure": "standardized depression scales",
                "timepoint_or_window": "primary endpoint",
                "effect_metric": "standardized mean difference",
                "effect_size": "-0.82",
                "confidence_interval": "95% CI, -1.20 to -0.44",
                "ci_lower": "-1.20",
                "ci_upper": "-0.44",
                "p_value": "p < 0.001",
                "model_type": "random effects",
                "study_count": "5",
                "participant_count": "238",
                "heterogeneity_i2": "41%",
                "heterogeneity_tau2": "not_reported",
                "heterogeneity_q": "not_reported",
                "prediction_interval": "not_reported",
                "result_direction": "positive",
                "authors_interpretation": "Psilocybin was associated with reduced depressive symptoms.",
                "included_study_labels": ["Carhart-Harris 2021"],
                "subgroup_or_sensitivity": "not_reported",
                "evidence_location": "figure",
                "evidence_locator": "Figure 2",
                "supporting_quote": "Psilocybin reduced depressive symptom severity (SMD, -0.82; 95% CI, -1.20 to -0.44; I2 = 41%).",
                "confidence": 0.95,
                "needs_human_review": False,
            }
        ],
        "risk_of_bias_assessments": [
            {
                "tool_or_framework": "RoB 2",
                "scope": "included randomized trials",
                "rating": "some concerns",
                "key_concerns": "small samples and masking concerns",
                "applies_to_result_ids": ["R1"],
                "evidence_location": "text",
                "evidence_locator": "Risk of bias",
                "supporting_quote": "Most trials had some concerns because of small samples and masking limitations.",
            }
        ],
        "certainty_assessments": [
            {
                "framework": "GRADE",
                "outcome_or_endpoint": "depressive symptom severity",
                "certainty_rating": "low",
                "downgrade_or_upgrade_reasons": "risk of bias and imprecision",
                "applies_to_result_ids": ["R1"],
                "evidence_location": "text",
                "evidence_locator": "Certainty of evidence",
                "supporting_quote": "The certainty of evidence was low because of risk of bias and imprecision.",
            }
        ],
        "authors_conclusions": [
            {
                "conclusion_domain": "clinical_outcome",
                "conclusion_text": "Psilocybin may reduce depressive symptoms, but certainty is low.",
                "result_direction": "positive",
                "certainty_or_caution": "low certainty",
                "applies_to_result_ids": ["R1"],
                "evidence_location": "abstract",
                "evidence_locator": "Abstract conclusion",
                "supporting_quote": "Psilocybin may reduce depressive symptoms, although certainty of evidence was low.",
            }
        ],
        "coverage_gaps": [
            {
                "gap_type": "follow_up_duration",
                "gap_text": "Long-term outcomes were sparse.",
                "evidence_location": "text",
                "evidence_locator": "Discussion",
                "supporting_quote": "Long-term outcomes were sparse across included trials.",
            }
        ],
        "extraction_warnings": [],
    }


class SynthesisEvidenceSchemaTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.validator = Draft7Validator(load_schema())

    def assert_valid(self, payload: dict) -> None:
        errors = sorted(self.validator.iter_errors(payload), key=lambda error: list(error.path))
        self.assertEqual(errors, [], [error.message for error in errors])

    def test_accepts_meta_analysis_payload_with_effect_and_included_study(self) -> None:
        self.assert_valid(valid_payload())

    def test_requires_effect_size_fields_for_synthesis_results(self) -> None:
        payload = copy.deepcopy(valid_payload())
        payload["synthesis_results"][0].pop("effect_size")

        errors = sorted(self.validator.iter_errors(payload), key=lambda error: list(error.path))

        self.assertTrue(any("'effect_size' is a required property" in error.message for error in errors))

    def test_prompt_profile_contains_no_invented_doi_guardrail(self) -> None:
        prompt = (ROOT / "docs" / "extraction_profiles" / "paper_type" / "meta_analysis_article_text.md").read_text(encoding="utf-8")
        prompt_one_line = " ".join(prompt.split())

        self.assertIn("Do not infer DOIs", prompt)
        self.assertIn("effect size", prompt)
        self.assertIn("included_studies_completeness", prompt)
        self.assertIn("synthesis_results[]", prompt)
        self.assertIn("If the study list is long", prompt_one_line)


if __name__ == "__main__":
    unittest.main()
