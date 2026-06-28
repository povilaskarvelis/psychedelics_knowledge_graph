import json
from pathlib import Path

from jsonschema import Draft7Validator


ROOT = Path(__file__).resolve().parents[1]
PRIMARY_SCHEMA_DIR = ROOT / "schema" / "extraction_profiles" / "primary"
PRIMARY_STATUS_ENUM = [
    "extracted",
    "no_extractable_scoped_evidence",
    "wrong_source_type",
    "not_relevant",
    "human_review",
]
PRIMARY_RESULT_DIRECTION_DOMAINS = {"clinical_outcome", "safety_tolerability"}


def minimal_primary_result() -> dict:
    quote = "Participants receiving psilocybin showed greater reductions in depression scores."
    return {
        "schema_version": "primary_evidence_v1",
        "task_id": "route-primary",
        "route_id": "route-primary",
        "study_doi": "10.1000/primary",
        "domain_route": "clinical_outcome",
        "source_type": "primary_or_unclear",
        "extraction_status": "extracted",
        "paper_assessment": {
            "is_in_scope": True,
            "has_original_results": True,
            "has_extractable_evidence_for_route": True,
            "study_design": "randomized controlled trial",
            "study_system": "clinical",
            "population_or_system": "Adults with depression",
            "compound_or_exposure": "psilocybin",
            "route_relevance_summary": "The paper reports clinical outcome results for psilocybin.",
            "needs_human_review": False,
            "evidence_location": "abstract",
            "evidence_locator": "Abstract",
        },
        "evidence_items": [
            {
                "item_id": "E1",
                "relationship_domain": "clinical_outcome",
                "compound_or_class": "psilocybin",
                "entity_type": "disorder",
                "entity": "depression",
                "raw_endpoint_or_measure": "depression scores",
                "population_or_system": "Adults with depression",
                "sample_size": "not_reported",
                "species_or_cell_line": "not_applicable",
                "intervention_or_exposure": "psilocybin",
                "comparator": "not_reported",
                "dose_or_exposure": "not_reported",
                "timepoint_or_window": "not_reported",
                "assay_or_measurement_method": "clinical rating scale",
                "result_summary": "Depression scores improved more with psilocybin.",
                "result_direction": "positive",
                "quantitative_value": "not_reported",
                "quantitative_unit": "not_reported",
                "effect_size_or_statistic": "not_reported",
                "statistical_support": "not_reported",
                "study_design": "randomized controlled trial",
                "study_system": "clinical",
                "graph_candidate_label": "depression",
                "graph_candidate_type": "condition_indication",
                "graph_include_candidate": True,
                "graph_exclusion_reason": "not_applicable",
                "evidence_location": "abstract",
                "evidence_locator": "Abstract",
                "confidence": 0.8,
                "needs_human_review": False,
            }
        ],
        "extraction_warnings": [],
    }


def test_minimal_primary_result_validates() -> None:
    schema = json.loads((ROOT / "schema" / "primary_evidence.schema.json").read_text(encoding="utf-8"))
    errors = sorted(Draft7Validator(schema).iter_errors(minimal_primary_result()), key=lambda error: list(error.path))

    assert errors == [], [error.message for error in errors]


def test_minimal_domain_specific_clinical_primary_result_validates() -> None:
    schema = json.loads(
        (ROOT / "schema" / "extraction_profiles" / "primary" / "clinical_outcome.schema.json").read_text(encoding="utf-8")
    )
    result = {
        "schema_version": "primary_clinical_outcome_v1",
        "task_id": "route-primary",
        "route_id": "route-primary",
        "study_doi": "10.1000/primary",
        "source_type": "primary_or_unclear",
        "domain_route": "clinical_outcome",
        "paper_type": "primary_study",
        "text_depth": "abstract_only",
        "extraction_status": "extracted",
        "items": [
            {
                "condition_or_population": "Adults with depression",
                "compound_or_intervention": "psilocybin",
                "comparator": "not_reported",
                "dose_or_regimen": "not_reported",
                "sample_size": "not_reported",
                "outcome_measure": "depression scores",
                "clinical_endpoint": "depressive symptoms",
                "assessment_timepoint": "not_reported",
                "result_direction": "positive",
                "effect_or_statistic": "not_reported",
                "finding_summary": "Psilocybin was associated with improved depression scores.",
                "evidence_location": "abstract",
                "evidence_locator": "Abstract",
                "study_design": "not_reported"
            }
        ],
        "warnings": ["abstract_only_limited_detail"]
    }
    errors = sorted(Draft7Validator(schema).iter_errors(result), key=lambda error: list(error.path))

    assert errors == [], [error.message for error in errors]


def test_domain_specific_primary_status_enums_match_prompts() -> None:
    for path in sorted(PRIMARY_SCHEMA_DIR.glob("*.schema.json")):
        schema = json.loads(path.read_text(encoding="utf-8"))

        assert schema["properties"]["extraction_status"]["enum"] == PRIMARY_STATUS_ENUM, path.name


def test_primary_result_direction_only_in_domains_with_clear_valence() -> None:
    for path in sorted(PRIMARY_SCHEMA_DIR.glob("*.schema.json")):
        schema = json.loads(path.read_text(encoding="utf-8"))
        domain = schema["properties"]["domain_route"]["const"]
        item = schema["definitions"]["item"]

        if domain in PRIMARY_RESULT_DIRECTION_DOMAINS:
            assert "result_direction" in item["required"], path.name
            assert "result_direction" in item["properties"], path.name
        else:
            assert "result_direction" not in item["required"], path.name
            assert "result_direction" not in item["properties"], path.name


def test_primary_result_direction_uses_no_detected_effect_not_null() -> None:
    for path in sorted(PRIMARY_SCHEMA_DIR.glob("*.schema.json")):
        schema = json.loads(path.read_text(encoding="utf-8"))
        item = schema["definitions"]["item"]
        direction = item["properties"].get("result_direction", {})
        enum = direction.get("enum", [])
        if enum:
            assert "no_detected_effect" in enum, path.name
            assert "null" not in enum, path.name


def test_primary_domain_schemas_do_not_request_low_value_fields() -> None:
    for path in sorted(PRIMARY_SCHEMA_DIR.glob("*.schema.json")):
        schema = json.loads(path.read_text(encoding="utf-8"))
        item = schema["definitions"]["item"]

        for field in ("p_value", "confidence_interval", "evidence_quote", "supporting_quote"):
            assert field not in item["required"], path.name
            assert field not in item["properties"], path.name


def test_primary_intervention_context_excludes_low_yield_comparator_field() -> None:
    schema = json.loads((PRIMARY_SCHEMA_DIR / "intervention_context.schema.json").read_text(encoding="utf-8"))
    item = schema["definitions"]["item"]

    assert "comparator_or_control" not in item["required"]
    assert "comparator_or_control" not in item["properties"]
