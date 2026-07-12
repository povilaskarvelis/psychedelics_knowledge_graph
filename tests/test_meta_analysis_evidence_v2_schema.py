import json
from copy import deepcopy
from pathlib import Path

from jsonschema import Draft7Validator

from pipeline.extract.route_extraction_profiles import schema_for_native


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schema" / "meta_analysis_evidence_v2.schema.json"
FULL_TEXT_PROMPT_PATH = ROOT / "docs" / "extraction_profiles" / "meta_analysis_v2" / "full_text_extraction.md"
ABSTRACT_PROMPT_PATH = ROOT / "docs" / "extraction_profiles" / "meta_analysis_v2" / "abstract_extraction.md"


def load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def locator() -> dict:
    return {
        "location": "results",
        "locator": "Results, primary analysis",
        "supporting_text": "The pooled effect was -0.82 (95% CI -1.20 to -0.44).",
    }


def valid_payload() -> dict:
    return {
        "extraction_status": "extracted",
        "meta_analysis_overview": {
            "synthesis_types": ["pairwise_meta_analysis"],
            "objective_and_scope": "Estimate the effect of psilocybin-assisted therapy on depressive symptoms.",
            "review_question": {
                "populations_or_systems": ["Adults with depressive disorders"],
                "interventions_or_exposures": ["Psilocybin-assisted therapy"],
                "comparators": ["Placebo or active control"],
                "outcomes_or_entities": ["Depressive symptom severity"],
                "eligible_evidence_designs": ["Randomized controlled trials"],
            },
            "primary_subjects": ["Psilocybin-assisted therapy"],
            "populations_or_systems": ["Adults with depressive disorders"],
            "included_evidence": {
                "study_count": "5",
                "participant_count": "238",
                "effect_or_experiment_count": "not_reported",
                "dataset_or_comparison_count": "not_reported",
                "evidence_design_summary": "Randomized controlled trials",
                "study_year_range": "2016-2023",
                "search_end_date": "2024-01-31",
                "registration_or_protocol": "PROSPERO CRD42000000000",
            },
        },
        "main_questions": [
            {
                "question_id": "Q1",
                "description": "Does psilocybin-assisted therapy reduce depressive symptoms?",
                "importance_in_paper": "main",
            }
        ],
        "synthesis_results": [
            {
                "result_id": "R1",
                "addresses_question_ids": ["Q1"],
                "result_role": "primary_synthesis",
                "importance_in_paper": "main",
                "relationship_statement": "Psilocybin-assisted therapy reduced depressive symptom severity compared with control.",
                "primary_subject_area": "clinical_outcome",
                "subject_areas": ["clinical_outcome"],
                "evidence_source": "human",
                "population_or_system": "Adults with depressive disorders",
                "intervention_or_exposure": "Psilocybin-assisted therapy",
                "comparator": "Placebo or active control",
                "outcome_or_entity": "Depressive symptom severity",
                "outcome_measure": "Standardized depression scales",
                "timepoint_or_window": "Primary endpoint",
                "effect_estimate": {
                    "metric": "standardized mean difference",
                    "estimate": "-0.82",
                    "interval_type": "confidence_interval",
                    "interval_level": "95%",
                    "interval_lower": "-1.20",
                    "interval_upper": "-0.44",
                    "interval_reported": "95% CI -1.20 to -0.44",
                    "standard_error": "not_reported",
                    "p_value": "p < 0.001",
                    "model": "random effects",
                    "analysis_scale": "standardized score",
                    "unit_of_analysis": "participants",
                    "adjustment_status": "unadjusted",
                },
                "evidence_size": {
                    "study_count": "5",
                    "participant_count": "238",
                    "effect_or_experiment_count": "5",
                    "dataset_or_comparison_count": "not_reported",
                },
                "heterogeneity": {
                    "i_squared": "41%",
                    "tau_squared": "not_reported",
                    "q_statistic": "not_reported",
                    "q_p_value": "not_reported",
                    "prediction_interval": "not_reported",
                    "authors_interpretation": "Moderate heterogeneity.",
                },
                "analysis_context": {
                    "analysis_type": "primary pairwise meta-analysis",
                    "subgroup_or_moderator": "not_applicable",
                    "meta_regression_coefficient": "not_applicable",
                    "sensitivity_method": "not_reported",
                    "multiplicity_adjustment": "not_reported",
                    "dependency_handling": "not_reported",
                },
                "interpretation": {
                    "finding_direction": "supports",
                    "favors": "Psilocybin-assisted therapy",
                    "outcome_orientation": "beneficial",
                    "statistical_interpretation": "The pooled estimate favored psilocybin and the interval excluded no difference.",
                    "authors_interpretation": "Psilocybin-assisted therapy may reduce depressive symptoms.",
                },
                "evidence_locators": [locator()],
                "limitations": ["Small included studies"],
            }
        ],
        "risk_of_bias_assessments": [
            {
                "assessment_id": "ROB1",
                "applies_to_result_ids": ["R1"],
                "tool_or_framework": "RoB 2",
                "scope": "Included randomized trials",
                "overall_judgment": "Some concerns",
                "domain_judgments": ["Bias due to deviations from intended interventions: some concerns"],
                "main_concerns": ["Masking limitations"],
                "evidence_locators": [locator()],
            }
        ],
        "certainty_assessments": [
            {
                "assessment_id": "CERT1",
                "applies_to_result_ids": ["R1"],
                "framework": "GRADE",
                "rating": "low",
                "downgrade_reasons": ["Risk of bias", "Imprecision"],
                "upgrade_reasons": [],
                "interpretation": "Confidence in the effect estimate is limited.",
                "evidence_locators": [locator()],
            }
        ],
        "publication_bias_assessments": [
            {
                "assessment_id": "PB1",
                "applies_to_result_ids": ["R1"],
                "method": "Egger test",
                "result": "No evidence of funnel plot asymmetry",
                "small_study_effects": "not detected",
                "adjustment_method": "not_applicable",
                "adjusted_estimate": "not_applicable",
                "evidence_locators": [locator()],
            }
        ],
        "paper_conclusions": [
            {
                "conclusion_id": "C1",
                "statement": "Psilocybin-assisted therapy may reduce depressive symptoms, but certainty is low.",
                "finding_direction": "supports",
                "applies_to_result_ids": ["R1"],
                "certainty_or_caution": "Low-certainty evidence",
                "evidence_locators": [locator()],
            }
        ],
        "overall_limitations": ["Few small trials"],
        "warnings": [],
    }


def test_schema_is_valid_draft_7_json_schema() -> None:
    Draft7Validator.check_schema(load_schema())


def test_schema_can_be_inlined_for_native_structured_output() -> None:
    native_schema = schema_for_native(load_schema())

    assert "$schema" not in native_schema
    assert "definitions" not in native_schema
    assert "$ref" not in json.dumps(native_schema)


def test_schema_accepts_meta_analysis_payload() -> None:
    errors = sorted(Draft7Validator(load_schema()).iter_errors(valid_payload()), key=lambda error: list(error.path))
    assert errors == [], [error.message for error in errors]


def test_schema_accepts_omitted_unreported_optional_statistics() -> None:
    payload = deepcopy(valid_payload())
    result = payload["synthesis_results"][0]
    result["effect_estimate"] = {
        "metric": "standardized mean difference",
        "estimate": "-0.82",
    }
    result.pop("heterogeneity")
    result.pop("analysis_context")
    payload["risk_of_bias_assessments"] = []
    payload["certainty_assessments"] = []
    payload["publication_bias_assessments"] = []

    errors = sorted(Draft7Validator(load_schema()).iter_errors(payload), key=lambda error: list(error.path))
    assert errors == [], [error.message for error in errors]


def test_schema_requires_graph_anchor_components_but_allows_genuine_nulls() -> None:
    schema = load_schema()
    required = set(schema["definitions"]["synthesis_result"]["required"])
    assert {
        "primary_subject_area",
        "population_or_system",
        "intervention_or_exposure",
        "comparator",
        "outcome_or_entity",
        "timepoint_or_window",
    } <= required

    payload = deepcopy(valid_payload())
    payload["synthesis_results"][0]["intervention_or_exposure"] = None
    payload["synthesis_results"][0]["outcome_or_entity"] = None
    payload["synthesis_results"][0]["population_or_system"] = None
    payload["synthesis_results"][0]["comparator"] = None
    payload["synthesis_results"][0]["timepoint_or_window"] = None
    errors = sorted(Draft7Validator(schema).iter_errors(payload), key=lambda error: list(error.path))
    assert errors == []


def test_schema_preserves_optional_statistical_detail_without_forcing_absent_fields() -> None:
    schema = load_schema()
    result = schema["definitions"]["synthesis_result"]["properties"]
    estimate = schema["definitions"]["effect_estimate"]["properties"]
    heterogeneity = schema["definitions"]["heterogeneity"]["properties"]

    assert "domain_route" not in schema["properties"]
    assert "main_questions" in schema["properties"]
    assert {"metric", "estimate", "interval_lower", "interval_upper", "p_value", "model"} <= set(estimate)
    assert {"i_squared", "tau_squared", "q_statistic", "prediction_interval"} <= set(heterogeneity)
    assert {"risk_of_bias_assessments", "certainty_assessments", "publication_bias_assessments"} <= set(
        schema["properties"]
    )
    assert {"importance_in_paper", "relationship_statement", "subject_areas"} <= set(result)
    assert "effect_estimate" not in schema["definitions"]["synthesis_result"]["required"]
    assert "heterogeneity" not in schema["definitions"]["synthesis_result"]["required"]
    assert "network_meta_analysis" not in schema["definitions"]["synthesis_result"]["required"]


def test_full_text_prompt_explains_missing_metrics_and_uses_the_full_text() -> None:
    prompt = FULL_TEXT_PROMPT_PATH.read_text(encoding="utf-8")
    normalized = " ".join(prompt.split())

    assert "Extract the main quantitative synthesis evidence reported in the supplied paper" in normalized
    assert "Base every value and interpretation on the supplied metadata and article text" in normalized
    assert "Omit unreported optional fields" in normalized
    assert "Do not calculate, convert, infer, or reconstruct statistics" in normalized
    assert "Do not create an unreported rating or judgment" in normalized
    assert "confidence or credible interval" in normalized
    assert "I-squared" in normalized
    assert "One result item represents one outcome" in normalized
    assert "short contiguous verbatim excerpt" in normalized


def test_abstract_prompt_has_a_strict_abstract_only_evidence_boundary() -> None:
    prompt = ABSTRACT_PROMPT_PATH.read_text(encoding="utf-8")
    normalized = " ".join(prompt.split())

    assert "The title, abstract, and metadata are the complete evidence available" in normalized
    assert "Omit an optional field or object" in normalized
    assert "Do not calculate, convert, infer, or reconstruct an unreported statistic" in normalized
    assert "Use an empty array when an assessment type is not reported" in normalized
    assert "One result item represents one outcome" in normalized
    assert "short contiguous verbatim excerpt" in normalized


def test_model_contract_excludes_deterministic_processing_metadata() -> None:
    schema = load_schema()
    prompt_text = "\n".join(
        [
            FULL_TEXT_PROMPT_PATH.read_text(encoding="utf-8"),
            ABSTRACT_PROMPT_PATH.read_text(encoding="utf-8"),
        ]
    )

    assert "schema_version" not in schema["properties"]
    assert "source_depth" not in schema["properties"]
    assert "source_completeness" not in json.dumps(schema)
    assert "abstract_only_limited_detail" not in prompt_text
    assert "Set `source_depth`" not in prompt_text


def test_prompts_do_not_frame_the_task_as_processing_multiple_papers() -> None:
    prompt_text = "\n".join(
        [
            FULL_TEXT_PROMPT_PATH.read_text(encoding="utf-8"),
            ABSTRACT_PROMPT_PATH.read_text(encoding="utf-8"),
        ]
    ).lower()

    for phrase in ("some papers", "other papers", "every paper", "across papers"):
        assert phrase not in prompt_text


def test_meta_analysis_contract_does_not_expose_review_or_graph_workflow_jargon() -> None:
    schema_text = SCHEMA_PATH.read_text(encoding="utf-8")
    prompt_text = "\n".join(
        [
            FULL_TEXT_PROMPT_PATH.read_text(encoding="utf-8"),
            ABSTRACT_PROMPT_PATH.read_text(encoding="utf-8"),
        ]
    )
    combined = f"{schema_text}\n{prompt_text}".lower()

    for term in (
        "paper_frame",
        "paper-centered",
        "paper_centered",
        "bundle",
        "centrality",
        "prominence",
        "anchors",
        "graph_form",
        "graph_eligibility",
        "main_graph",
        "domain_labels",
        "evidence_stratum",
        "paper_defining",
        "major_supporting",
        "secondary_context",
        "source_item_ids",
    ):
        assert term not in combined
