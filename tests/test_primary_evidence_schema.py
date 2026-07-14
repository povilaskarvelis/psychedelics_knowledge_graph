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
