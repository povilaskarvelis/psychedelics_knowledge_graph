from pathlib import Path

from pipeline.extract.build_extraction_routes import (
    PRIMARY_PROMPT_BY_DOMAIN,
    schema_profile_for,
)
from pipeline.extract.route_extraction_profiles import (
    DOMAIN_PROMPT_PATHS,
    PROFILE_STATUS_RUNNABLE,
    PROFILE_STATUS_TERMINAL_NO_MODEL,
    ROUTE_EXTRACTION_PROFILES,
    REVIEW_COVERAGE_PROMPT_PROFILES,
    REVIEW_SCHEMA_PATHS,
    META_ANALYSIS_SCHEMA_PATHS,
    VALID_PROFILE_STATUSES,
    build_system_instruction,
    load_schema,
    load_schema_for_profile,
    profile_for_key,
    schema_path_for_profile,
    supported_profile_keys,
)


ROOT = Path(__file__).resolve().parents[1]


def route_builder_profile_pairs() -> set[tuple[str, str]]:
    prompt_profiles = {
        *PRIMARY_PROMPT_BY_DOMAIN.values(),
        "secondary_meta_analysis",
        "secondary_structured_review",
        "secondary_narrative_review",
        "secondary_review_coverage",
        "guideline_consensus",
        "context_only_or_skip",
        "no_extraction",
    }
    return {(prompt_profile, schema_profile_for(prompt_profile)) for prompt_profile in prompt_profiles}


def test_registry_covers_every_route_builder_prompt_schema_pair() -> None:
    missing = route_builder_profile_pairs() - set(ROUTE_EXTRACTION_PROFILES)

    assert missing == set()


def test_profile_statuses_and_files_are_consistent() -> None:
    for profile in ROUTE_EXTRACTION_PROFILES.values():
        assert profile.status in VALID_PROFILE_STATUSES
        if profile.status == PROFILE_STATUS_TERMINAL_NO_MODEL:
            assert profile.prompt_path is None
            assert profile.schema_path is None
            assert profile.default_max_output_tokens == 0
        else:
            assert profile.prompt_path is not None
            assert profile.schema_path is not None
            assert profile.prompt_path.exists()
            assert profile.schema_path.exists()
            assert profile.default_max_output_tokens > 0


def test_current_runnable_profiles_include_primary_meta_analysis_and_reviews() -> None:
    runnable = {
        (profile.prompt_profile, profile.schema_profile)
        for profile in ROUTE_EXTRACTION_PROFILES.values()
        if profile.status == PROFILE_STATUS_RUNNABLE
    }

    assert ("secondary_meta_analysis", "meta_analysis_evidence_schema") in runnable
    assert ("primary_clinical", "primary_evidence_schema") in runnable
    assert ("primary_molecular_target", "primary_evidence_schema") in runnable
    assert {(prompt, "review_coverage_schema") for prompt in REVIEW_COVERAGE_PROMPT_PROFILES}.issubset(runnable)


def test_domain_prompt_addenda_exist() -> None:
    assert set(DOMAIN_PROMPT_PATHS) >= {
        "clinical_outcome",
        "safety_tolerability",
        "molecular_target",
        "molecular_pathway_readout",
        "brain_system",
        "cognitive_behavioral",
        "subjective_experience",
        "pharmacokinetics_exposure",
        "intervention_context",
        "real_world_public_health",
        "general_primary",
        "general_topic_coverage",
    }
    for path in DOMAIN_PROMPT_PATHS.values():
        assert path.exists()


def test_system_instruction_uses_paper_type_depth_prompt_and_scope_notes_for_primary_profiles() -> None:
    profile = profile_for_key("primary_clinical", "primary_evidence_schema")
    schema = load_schema(profile.schema_path)

    instruction = build_system_instruction(
        profile,
        schema,
        "native",
        domain_route="clinical_outcome",
        text_depth="full_text",
    )

    assert "Primary Study Article-Text Extraction" in instruction
    assert "## Scope" in instruction
    assert "Focus on clinical outcome evidence" in instruction
    assert "Text Depth: Article Text" not in instruction
    assert "response_json_schema" in instruction
    assert profile.schema_path.name == "clinical_outcome.schema.json"


def test_system_instruction_includes_scope_for_secondary_profiles() -> None:
    profile = profile_for_key("secondary_meta_analysis", "meta_analysis_evidence_schema")
    schema = load_schema_for_profile(profile, "clinical_outcome")

    instruction = build_system_instruction(
        profile,
        schema,
        "native",
        domain_route="clinical_outcome",
        text_depth="article_text",
    )

    assert "Secondary Meta-Analysis Article-Text Extraction" in instruction
    assert "## Scope" in instruction
    assert "Focus on clinical outcome evidence" in instruction


def test_meta_analysis_profile_uses_domain_specific_schema_when_available() -> None:
    profile = profile_for_key("secondary_meta_analysis", "meta_analysis_evidence_schema")

    assert schema_path_for_profile(profile, "clinical_outcome") == META_ANALYSIS_SCHEMA_PATHS["clinical_outcome"]
    assert schema_path_for_profile(profile, "safety_tolerability") == META_ANALYSIS_SCHEMA_PATHS["safety_tolerability"]

    clinical_schema = load_schema_for_profile(profile, "clinical_outcome")
    safety_schema = load_schema_for_profile(profile, "safety_tolerability")

    clinical_result = clinical_schema["definitions"]["synthesis_result"]["properties"]["domain_result"]
    safety_result = safety_schema["definitions"]["synthesis_result"]["properties"]["domain_result"]
    assert "clinical_endpoint" in clinical_result["properties"]
    assert "safety_event_or_measure" in safety_result["properties"]


def test_review_profile_uses_domain_specific_schema_when_available() -> None:
    profile = profile_for_key("secondary_review_coverage", "review_coverage_schema")

    assert schema_path_for_profile(profile, "clinical_outcome") == REVIEW_SCHEMA_PATHS["clinical_outcome"]
    assert schema_path_for_profile(profile, "safety_tolerability") == REVIEW_SCHEMA_PATHS["safety_tolerability"]

    clinical_schema = load_schema_for_profile(profile, "clinical_outcome")
    safety_schema = load_schema_for_profile(profile, "safety_tolerability")

    clinical_result = clinical_schema["definitions"]["coverage_item"]["properties"]["domain_result"]
    safety_result = safety_schema["definitions"]["coverage_item"]["properties"]["domain_result"]
    assert "clinical_endpoint_category" in clinical_result["properties"]
    assert "safety_event_or_risk" in safety_result["properties"]


def test_supported_profile_keys_reports_status() -> None:
    rows = supported_profile_keys()

    assert any(row["status"] == PROFILE_STATUS_TERMINAL_NO_MODEL for row in rows)
    assert any(row["status"] == PROFILE_STATUS_RUNNABLE for row in rows)
