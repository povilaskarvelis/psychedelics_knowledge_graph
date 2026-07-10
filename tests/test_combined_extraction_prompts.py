from pipeline.extract.extraction_profile_matrix import (
    PRIMARY_PROMPT_BY_DOMAIN,
    TEXT_DEPTH_ABSTRACT,
    TEXT_DEPTH_ARTICLE,
)
from pipeline.extract.route_extraction_profiles import (
    build_system_instruction,
    load_schema,
    load_schema_for_profile,
    profile_for_key,
    schema_for_assigned_domain,
    schema_for_native,
)


PRIMARY_DOMAINS = tuple(PRIMARY_PROMPT_BY_DOMAIN)
SECONDARY_DOMAINS = tuple(domain for domain in PRIMARY_DOMAINS if domain != "general_primary") + ("general_topic_coverage",)
TEXT_DEPTHS = (TEXT_DEPTH_ARTICLE, TEXT_DEPTH_ABSTRACT)
BAD_PROMPT_TERMS = (
    "routed paper",
    "route-specific",
    "all possible domains",
    "choose the domain",
    "full text",
    "full-text",
    "full_text",
    "domain-specific addendum",
    "domain addendum",
    "assigned-domain",
    "assigned evidence domain",
    "assigned domain",
    "assigned relationship domain",
    "assigned json schema",
    "below",
    "evidence focus:",
    "scope notes:",
    "## extraction status",
    "## result direction",
)
DOMAIN_EXAMPLE_TERMS = (
    "clinical trial",
    "observational result",
    "naturalistic data",
    "case series",
    "animal experiment",
    "in vitro",
    "ex vivo",
    "imaging study",
    "behavioral experiment",
    "pharmacokinetic measurement",
    "safety/tolerability",
)


def assembled_prompt_scenarios() -> list[tuple[str, str, str, str]]:
    rows = []
    for domain, prompt_profile in PRIMARY_PROMPT_BY_DOMAIN.items():
        profile = profile_for_key(prompt_profile, "primary_evidence_schema")
        schema = load_schema(profile.schema_path)
        for depth in TEXT_DEPTHS:
            rows.append(("primary", domain, depth, build_system_instruction(profile, schema, "native", domain_route=domain, text_depth=depth)))
    for domain in SECONDARY_DOMAINS:
        for prompt_profile, schema_profile, family in (
            ("secondary_meta_analysis", "meta_analysis_evidence_schema", "meta_analysis"),
            ("secondary_review_coverage", "review_coverage_schema", "review_coverage"),
        ):
            profile = profile_for_key(prompt_profile, schema_profile)
            for depth in TEXT_DEPTHS:
                schema = (
                    load_schema_for_profile(profile, domain)
                    if family in {"meta_analysis", "review_coverage"}
                    else load_schema(profile.schema_path)
                )
                rows.append((family, domain, depth, build_system_instruction(profile, schema, "native", domain_route=domain, text_depth=depth)))
    return rows


def test_all_combined_prompts_have_one_domain_one_depth_and_no_old_shorthand() -> None:
    scenarios = assembled_prompt_scenarios()

    assert len(scenarios) == 66
    for family, domain, depth, prompt in scenarios:
        lower = " ".join(prompt.lower().split())
        assert prompt.count("## Scope") == 1, (family, domain, depth)
        assert "Text-depth instructions:" not in prompt
        if family == "primary" and depth == TEXT_DEPTH_ARTICLE:
            assert "Primary Study Article-Text Extraction" in prompt
        if family == "primary" and depth == TEXT_DEPTH_ABSTRACT:
            assert "Primary Study Abstract Extraction" in prompt
        if family == "meta_analysis" and depth == TEXT_DEPTH_ARTICLE:
            assert "Secondary Meta-Analysis Article-Text Extraction" in prompt
        if family == "meta_analysis" and depth == TEXT_DEPTH_ABSTRACT:
            assert "Secondary Meta-Analysis Abstract Extraction" in prompt
        if family == "review_coverage" and depth == TEXT_DEPTH_ARTICLE:
            assert "Secondary Review Article-Text Extraction" in prompt
        if family == "review_coverage" and depth == TEXT_DEPTH_ABSTRACT:
            assert "Secondary Review Abstract Extraction" in prompt
        assert prompt.count("response_json_schema") == 1, (family, domain, depth)
        for term in BAD_PROMPT_TERMS:
            assert term not in lower, (family, domain, depth, term)


def test_combined_prompts_start_with_summary_paragraph_and_end_with_output() -> None:
    for family, _domain, _depth, prompt in assembled_prompt_scenarios():
        lines = [line for line in prompt.splitlines() if line.strip()]
        assert not lines[1].startswith("## "), family
        assert "## Task" not in prompt
        assert prompt.count("## Scope") == 1
        assert prompt.count("## Extraction Outcome") == 1
        assert prompt.count("## Output") == 1
        output_index = prompt.rfind("## Output")
        scope_index = prompt.find("## Scope")
        extraction_status_index = prompt.find("## Extraction Outcome")
        what_to_extract_index = prompt.find("## What To Extract")
        first_detail_index = min(index for index in (extraction_status_index, what_to_extract_index) if index >= 0)
        assert output_index > 0
        assert "You are a researcher extracting structured evidence" in prompt.split("\n\n", 2)[1]
        assert output_index > scope_index
        assert 0 < scope_index < first_detail_index
        assert "Return exactly one JSON object" in prompt[output_index:]
        assert "response_json_schema" in prompt[output_index:]


def test_scope_section_is_used_for_every_model_prompt() -> None:
    for _family, _domain, _depth, prompt in assembled_prompt_scenarios():
        assert prompt.count("## Scope") == 1


def test_non_extracted_outputs_must_include_warning_reason() -> None:
    for family, domain, depth, prompt in assembled_prompt_scenarios():
        lower = " ".join(prompt.lower().split())
        assert "for any status other than `extracted`, add one short reason" in lower, (family, domain, depth)
        if family == "primary":
            assert "to `warnings`" in lower, (family, domain, depth)
            assert "keep `items` empty" in lower, (family, domain, depth)
        elif family == "meta_analysis":
            assert "to `extraction_warnings`" in lower, (family, domain, depth)
            assert "keep `synthesis_results` empty" in lower, (family, domain, depth)
        else:
            assert "to `extraction_warnings`" in lower, (family, domain, depth)
            assert "keep `coverage_items` empty" in lower, (family, domain, depth)


def test_meta_analysis_prompts_reject_reviews_that_only_cite_meta_analyses() -> None:
    for family, domain, depth, prompt in assembled_prompt_scenarios():
        lower = " ".join(prompt.lower().split())
        if family == "meta_analysis":
            assert "the paper itself must be a meta-analysis" in lower, (domain, depth)
            assert "only cites or summarizes meta-analyses from other papers" in lower, (domain, depth)
        else:
            assert "only cites or summarizes meta-analyses from other papers" not in lower, (family, domain, depth)


def test_opening_context_stays_paper_type_only_not_domain_examples() -> None:
    for family, domain, depth, prompt in assembled_prompt_scenarios():
        opening = " ".join(prompt[: prompt.find("## Scope")].lower().split())
        for term in DOMAIN_EXAMPLE_TERMS:
            assert term not in opening, (family, domain, depth, term)


def test_secondary_combined_prompts_do_not_list_other_domain_ids() -> None:
    for family, domain, _depth, prompt in assembled_prompt_scenarios():
        if family == "primary":
            continue
        other_domains = set(SECONDARY_DOMAINS) - {domain}
        leaked_domains = [other for other in other_domains if other in prompt]
        assert leaked_domains == [], (family, domain, leaked_domains)


def test_secondary_schema_is_specialized_to_single_assigned_domain() -> None:
    profile = profile_for_key("secondary_meta_analysis", "meta_analysis_evidence_schema")
    schema = load_schema_for_profile(profile, "clinical_outcome")
    model_schema = schema_for_native(schema_for_assigned_domain(schema, "clinical_outcome"))

    assert model_schema["properties"]["domain_route"]["const"] == "clinical_outcome"
    assert (
        model_schema["properties"]["synthesis_assessment"]["properties"]["relationship_domain"]["const"]
        == "clinical_outcome"
    )
    assert model_schema["properties"]["synthesis_results"]["items"]["properties"]["relationship_domain"]["const"] == "clinical_outcome"
    assert model_schema["properties"]["synthesis_results"]["items"]["properties"]["entity_type"]["enum"] == [
        "disorder",
        "symptom_or_outcome",
        "not_applicable",
        "uncertain",
    ]
    assert "clinical_endpoint" in (
        model_schema["properties"]["synthesis_results"]["items"]["properties"]["domain_result"]["properties"]
    )

    review_profile = profile_for_key("secondary_review_coverage", "review_coverage_schema")
    review_schema = load_schema_for_profile(review_profile, "clinical_outcome")
    review_model_schema = schema_for_native(schema_for_assigned_domain(review_schema, "clinical_outcome"))

    assert review_model_schema["properties"]["domain_route"]["const"] == "clinical_outcome"
    assert (
        review_model_schema["properties"]["review_assessment"]["properties"]["relationship_domain"]["const"]
        == "clinical_outcome"
    )
    assert review_model_schema["properties"]["coverage_items"]["items"]["properties"]["relationship_domain"]["const"] == "clinical_outcome"
    assert review_model_schema["properties"]["coverage_items"]["items"]["properties"]["entity_type"]["enum"] == [
        "disorder",
        "symptom_or_outcome",
        "not_applicable",
        "uncertain",
    ]
    assert "clinical_endpoint_category" in (
        review_model_schema["properties"]["coverage_items"]["items"]["properties"]["domain_result"]["properties"]
    )


def test_mechanistic_prompts_do_not_force_valenced_result_direction() -> None:
    mechanistic_domains = {"molecular_target", "molecular_pathway_readout"}
    for family, domain, depth, prompt in assembled_prompt_scenarios():
        if domain not in mechanistic_domains:
            continue
        lower = " ".join(prompt.lower().split())
        assert "## result direction" not in lower, (family, domain, depth)
        assert "result_direction" not in lower, (family, domain, depth)
        assert "positive" not in lower, (family, domain, depth)
        assert "negative" not in lower, (family, domain, depth)
        assert "therapeutic benefit or harm" in lower, (family, domain, depth)


def test_mechanistic_meta_schema_constrains_result_direction_to_not_applicable() -> None:
    profile = profile_for_key("secondary_meta_analysis", "meta_analysis_evidence_schema")
    schema = load_schema_for_profile(profile, "molecular_target")

    non_valenced_domains = set(SECONDARY_DOMAINS) - {"clinical_outcome", "safety_tolerability"}
    for domain in non_valenced_domains:
        schema = load_schema_for_profile(profile, domain)
        model_schema = schema_for_native(schema_for_assigned_domain(schema, domain))
        result_direction = model_schema["properties"]["synthesis_results"]["items"]["properties"]["result_direction"]

        assert result_direction == {"type": "string", "const": "not_applicable"}


def test_primary_result_direction_only_appears_in_clinical_and_safety_prompts() -> None:
    result_direction_domains = {
        domain
        for family, domain, _depth, prompt in assembled_prompt_scenarios()
        if family == "primary" and "result_direction" in prompt
    }

    assert result_direction_domains == {"clinical_outcome", "safety_tolerability"}


def test_schema_in_prompt_mode_does_not_reintroduce_other_secondary_domain_ids() -> None:
    profile = profile_for_key("secondary_meta_analysis", "meta_analysis_evidence_schema")
    schema = load_schema_for_profile(profile, "clinical_outcome")

    prompt = build_system_instruction(
        profile,
        schema,
        "prompt",
        domain_route="clinical_outcome",
        text_depth=TEXT_DEPTH_ARTICLE,
    )

    assert '"const":"clinical_outcome"' in prompt
    for other_domain in set(SECONDARY_DOMAINS) - {"clinical_outcome"}:
        assert other_domain not in prompt


def test_meta_analysis_abstract_prompt_is_leaner_than_article_text_prompt() -> None:
    profile = profile_for_key("secondary_meta_analysis", "meta_analysis_evidence_schema")
    schema = load_schema_for_profile(profile, "clinical_outcome")

    abstract_prompt = build_system_instruction(
        profile,
        schema,
        "native",
        domain_route="clinical_outcome",
        text_depth=TEXT_DEPTH_ABSTRACT,
    )
    article_prompt = build_system_instruction(
        profile,
        schema,
        "native",
        domain_route="clinical_outcome",
        text_depth=TEXT_DEPTH_ARTICLE,
    )

    assert "Secondary Meta-Analysis Abstract Extraction" in abstract_prompt
    assert "individual included studies" in abstract_prompt
    assert "included-study DOIs" in abstract_prompt
    assert "included_studies" not in abstract_prompt
    assert "Included Studies" not in abstract_prompt
    assert "Search Methods" not in abstract_prompt
    assert "Eligibility Criteria" not in abstract_prompt
    assert "Risk Of Bias And Certainty" not in abstract_prompt
    assert "network comparison" in abstract_prompt
    assert len(abstract_prompt) < len(article_prompt)


def test_meta_analysis_uses_same_domain_schema_for_abstract_and_article_text() -> None:
    profile = profile_for_key("secondary_meta_analysis", "meta_analysis_evidence_schema")
    schema = load_schema_for_profile(profile, "clinical_outcome")

    removed_sections = {
        "search_methods",
        "eligibility_criteria",
        "risk_of_bias_assessments",
        "certainty_assessments",
        "authors_conclusions",
        "coverage_gaps",
    }

    assert removed_sections.isdisjoint(set(schema["properties"]))
    assert schema["properties"]["text_depth"]["enum"] == [TEXT_DEPTH_ARTICLE, TEXT_DEPTH_ABSTRACT]
    result_props = schema["definitions"]["synthesis_result"]["properties"]
    assert {"effect_metric", "effect_size", "authors_interpretation"}.issubset(result_props)
    for field in (
        "contrast_type",
        "confidence_interval",
        "p_value",
        "heterogeneity_i2",
        "network_comparison",
        "network_evidence_type",
        "network_rank_or_score",
        "network_inconsistency_or_transitivity",
    ):
        assert field not in result_props


def test_primary_abstract_prompt_is_leaner_than_article_text_prompt() -> None:
    profile = profile_for_key("primary_clinical", "primary_evidence_schema")
    schema = load_schema(profile.schema_path)

    abstract_prompt = build_system_instruction(
        profile,
        schema,
        "native",
        domain_route="clinical_outcome",
        text_depth=TEXT_DEPTH_ABSTRACT,
    )
    article_prompt = build_system_instruction(
        profile,
        schema,
        "native",
        domain_route="clinical_outcome",
        text_depth=TEXT_DEPTH_ARTICLE,
    )

    assert "Primary Study Abstract Extraction" in abstract_prompt
    assert "Do not try to reconstruct methods, tables" in abstract_prompt
    assert "Primary Study Article-Text Extraction" in article_prompt
    assert len(abstract_prompt) < len(article_prompt)


def test_review_abstract_prompt_is_leaner_than_article_text_prompt() -> None:
    profile = profile_for_key("secondary_review_coverage", "review_coverage_schema")
    schema = load_schema_for_profile(profile, "clinical_outcome")

    abstract_prompt = build_system_instruction(
        profile,
        schema,
        "native",
        domain_route="clinical_outcome",
        text_depth=TEXT_DEPTH_ABSTRACT,
    )
    article_prompt = build_system_instruction(
        profile,
        schema,
        "native",
        domain_route="clinical_outcome",
        text_depth=TEXT_DEPTH_ARTICLE,
    )

    assert "Secondary Review Abstract Extraction" in abstract_prompt
    assert "Do not infer the review's full structure" in abstract_prompt
    assert "domain_result" in abstract_prompt
    assert "Secondary Review Article-Text Extraction" in article_prompt
    assert len(abstract_prompt) < len(article_prompt)


def test_review_prompts_preserve_substantially_discussed_review_relationships() -> None:
    profile = profile_for_key("secondary_review_coverage", "review_coverage_schema")
    schema = load_schema_for_profile(profile, "clinical_outcome")

    abstract_prompt = build_system_instruction(
        profile,
        schema,
        "native",
        domain_route="clinical_outcome",
        text_depth=TEXT_DEPTH_ABSTRACT,
    )
    article_prompt = build_system_instruction(
        profile,
        schema,
        "native",
        domain_route="clinical_outcome",
        text_depth=TEXT_DEPTH_ARTICLE,
    )
    abstract_lower = " ".join(abstract_prompt.lower().split())
    article_lower = " ".join(article_prompt.lower().split())

    assert "substantive_coverage_inventory" in article_prompt
    assert "substantially discusses in the selected scope" in article_lower
    assert "keep distinct substantially discussed relationships in separate rows" in article_lower
    assert "substantially discussed compound-entity relationship" in article_lower
    assert "passing mentions" in article_lower
    assert "substantive_coverage_inventory" in abstract_prompt
    assert "substantially discussed in the title and abstract" in abstract_lower
    assert "keep distinct substantially discussed relationships in separate rows" in abstract_lower
    assert "review-level claim" in abstract_lower
    assert "most important topics" not in article_lower
    assert "most important topics" not in abstract_lower


def test_clinical_review_prompt_names_clean_condition_fields_and_scale_guardrails() -> None:
    profile = profile_for_key("secondary_review_coverage", "review_coverage_schema")
    schema = load_schema_for_profile(profile, "clinical_outcome")

    prompt = build_system_instruction(
        profile,
        schema,
        "native",
        domain_route="clinical_outcome",
        text_depth=TEXT_DEPTH_ARTICLE,
    )
    lower = " ".join(prompt.lower().split())

    assert "condition_or_indication" in prompt
    assert "population_or_subgroup" in prompt
    assert "condition_or_population" in prompt
    assert "do not use a scale name as the clinical condition" in lower
    assert "tobacco use disorder" in lower
    assert "distress associated with life-threatening disease" in lower
