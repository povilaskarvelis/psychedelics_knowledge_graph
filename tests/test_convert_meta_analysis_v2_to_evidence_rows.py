from pipeline.kg.convert_meta_analysis_v2_to_evidence_rows import (
    convert_outputs,
    primary_domain_for,
)


def output_with_result(item: dict, primary_subjects: list[str] | None = None) -> dict:
    return {
        "task_id": "task-1",
        "study_doi": "10.1/meta",
        "study_title": "Meta-analysis",
        "source_depth": "article_text",
        "status": "ok",
        "result": {
            "extraction_status": "extracted",
            "meta_analysis_overview": {"primary_subjects": primary_subjects or []},
            "synthesis_results": [item],
            "risk_of_bias_assessments": [],
            "certainty_assessments": [],
            "overall_limitations": [],
            "warnings": [],
        },
    }


def task() -> dict:
    return {
        "task_id": "task-1",
        "paper_metadata": {
            "study_title": "Meta-analysis",
            "study_year": "2025",
            "meta_analysis_type": "meta_analysis",
        },
    }


def base_item() -> dict:
    return {
        "result_id": "R1",
        "result_role": "primary_synthesis",
        "importance_in_paper": "main",
        "subject_areas": ["clinical_outcome"],
        "relationship_statement": "Ketamine reduced depressive symptoms in adults with major depressive disorder.",
        "intervention_or_exposure": "Ketamine",
        "population_or_system": "Adults with major depressive disorder",
        "outcome_or_entity": "Depressive symptoms",
        "interpretation": {
            "finding_direction": "supports",
            "outcome_orientation": "beneficial",
        },
        "effect_estimate": {
            "metric": "SMD",
            "estimate": "-0.82",
            "interval_reported": "95% CI -1.20 to -0.44",
            "p_value": "p < 0.001",
        },
        "evidence_locators": [
            {
                "location": "results",
                "locator": "Results, primary analysis",
                "supporting_text": "The pooled SMD was -0.82.",
            }
        ],
    }


def test_converter_preserves_meta_analysis_statistics_and_condition_anchor() -> None:
    rows, report = convert_outputs([output_with_result(base_item())], {"task-1": task()})

    assert report["counts"]["rows_written"] == 1
    row = rows[0]
    assert row["domain"] == "clinical_outcome"
    assert row["compound"] == "Ketamine"
    assert row["kg_entity_kind_override"] == "condition_indication"
    assert row["graph_entity_label"] == "Adults with major depressive disorder"
    assert row["clinical_endpoint"] == "Depressive symptoms"
    assert row["population"] == "Adults with major depressive disorder"
    assert row["effect_size"] == "SMD -0.82; 95% CI -1.20 to -0.44"
    assert row["p_value"] == "p < 0.001"


def test_converter_uses_safe_single_paper_subject_fallback() -> None:
    item = base_item()
    item.pop("intervention_or_exposure")
    rows, report = convert_outputs(
        [output_with_result(item, primary_subjects=["Ketamine"])],
        {"task-1": task()},
    )

    assert report["counts"]["rows_written"] == 1
    assert rows[0]["compound"] == "Ketamine"
    assert rows[0]["normalization_subject_source"] == "single_overview_subject_mentioned_in_result"


def test_multi_area_adverse_event_uses_safety_domain() -> None:
    item = base_item()
    item["subject_areas"] = ["safety_tolerability", "subjective_experience"]
    item["relationship_statement"] = "Ketamine increased the risk of dissociation."
    item["outcome_or_entity"] = "Dissociation"

    domain, source = primary_domain_for(item)

    assert domain == "safety_tolerability"
    assert source == "context_rule:safety_tolerability"


def test_converter_holds_result_without_a_result_specific_or_safe_paper_subject() -> None:
    item = base_item()
    item.pop("intervention_or_exposure")
    item["relationship_statement"] = "The intervention reduced depressive symptoms."
    rows, report = convert_outputs(
        [output_with_result(item, primary_subjects=["Ketamine", "Psilocybin"])],
        {"task-1": task()},
    )

    assert rows == []
    assert report["counts"]["held:missing_graph_subject"] == 1
    assert report["held_samples"][0]["result_id"] == "R1"


def test_network_comparison_uses_treatment_pair_and_preserves_network_details() -> None:
    item = base_item()
    item["result_role"] = "network_comparison"
    item["intervention_or_exposure"] = "Ketamine and esketamine"
    item["comparator"] = ""
    item["network_meta_analysis"] = {
        "treatment_a": "Ketamine",
        "treatment_b": "Esketamine",
        "reference_treatment": "Placebo",
        "evidence_type": "mixed",
        "inconsistency_assessment": "No important inconsistency was detected",
    }
    rows, report = convert_outputs([output_with_result(item)], {"task-1": task()})

    assert report["counts"]["rows_written"] == 1
    assert rows[0]["compound"] == "Ketamine"
    assert rows[0]["comparator"] == "Esketamine"
    assert rows[0]["network_reference_treatment"] == "Placebo"
    assert rows[0]["network_evidence_type"] == "mixed"
    assert rows[0]["normalization_subject_source"] == "network_treatment_a"


def test_converter_preserves_meta_analysis_specific_statistics() -> None:
    item = base_item()
    item["primary_subject_area"] = "clinical_outcome"
    item["evidence_size"] = {
        "study_count": "12 studies",
        "participant_count": "1,204 participants",
        "effect_or_experiment_count": "15 comparisons",
    }
    item["heterogeneity"] = {
        "i_squared": "I² = 61%",
        "tau_squared": "tau² = 0.08",
        "prediction_interval": "95% PI -1.40 to 0.10",
    }
    item["analysis_context"] = {
        "analysis_type": "random-effects meta-analysis",
        "subgroup_or_moderator": "route of administration",
    }
    rows, report = convert_outputs([output_with_result(item)], {"task-1": task()})

    assert report["counts"]["rows_written"] == 1
    row = rows[0]
    assert row["meta_analysis_primary_subject_area"] == "clinical_outcome"
    assert row["meta_analysis_study_count"] == "12 studies"
    assert row["heterogeneity_i_squared"] == "I² = 61%"
    assert row["heterogeneity_prediction_interval"] == "95% PI -1.40 to 0.10"
    assert row["meta_analysis_analysis_type"] == "random-effects meta-analysis"


def test_converter_preserves_paper_level_evidence_size_for_filtering() -> None:
    output = output_with_result(base_item())
    output["result"]["meta_analysis_overview"]["included_evidence"] = {
        "study_count": "29",
        "dataset_or_comparison_count": "34 comparisons",
        "evidence_design_summary": "randomized controlled trials",
        "search_end_date": "January 2025",
    }

    rows, report = convert_outputs([output], {"task-1": task()})

    assert report["counts"]["rows_written"] == 1
    row = rows[0]
    assert row["meta_analysis_overall_study_count"] == "29"
    assert row["meta_analysis_overall_dataset_or_comparison_count"] == "34 comparisons"
    assert row["meta_analysis_evidence_design_summary"] == "randomized controlled trials"
    assert row["meta_analysis_search_end_date"] == "January 2025"


def test_converter_uses_brain_measure_kind_for_connectivity_result() -> None:
    item = base_item()
    item["primary_subject_area"] = "clinical_outcome"
    item["subject_areas"] = ["clinical_outcome", "brain_system"]
    item["population_or_system"] = "Healthy volunteers"
    item["outcome_or_entity"] = "Between-network functional connectivity"
    item["relationship_statement"] = "Psilocybin altered between-network functional connectivity."
    item["intervention_or_exposure"] = "Psilocybin"

    rows, report = convert_outputs([output_with_result(item)], {"task-1": task()})

    assert report["counts"]["rows_written"] == 1
    assert rows[0]["domain"] == "brain_system"
    assert rows[0]["kg_entity_kind_override"] == "brain_measure"
    assert rows[0]["brain_measure"] == "Between-network functional connectivity"


def test_intervention_context_analysis_keeps_treatment_as_subject_and_factor_as_entity() -> None:
    item = base_item()
    item["primary_subject_area"] = "intervention_context"
    item["subject_areas"] = ["intervention_context", "clinical_outcome"]
    item["result_role"] = "meta_regression"
    item["intervention_or_exposure"] = "Integration hours and session count"
    item["outcome_or_entity"] = "Depressive symptom reduction"
    item["population_or_system"] = "Adults with major depressive disorder"
    item["relationship_statement"] = "Integration hours did not moderate depressive symptom reduction."

    rows, report = convert_outputs(
        [output_with_result(item, primary_subjects=["Psilocybin-assisted therapy"])],
        {"task-1": task()},
    )

    assert report["counts"]["rows_written"] == 1
    assert rows[0]["compound"] == "Psilocybin-assisted therapy"
    assert rows[0]["graph_entity_label"] == "Integration hours and session count"
    assert rows[0]["kg_entity_kind_override"] == "intervention_component"


def test_converter_preserves_single_explicit_dose_for_dose_response_grouping() -> None:
    item = base_item()
    item["result_role"] = "dose_response"
    item["relationship_statement"] = "A 75 mg dose of MDMA reduced PTSD symptoms compared with active placebo."
    item["intervention_or_exposure"] = "MDMA"
    item["population_or_system"] = "Adults with PTSD"

    rows, report = convert_outputs([output_with_result(item)], {"task-1": task()})

    assert report["counts"]["rows_written"] == 1
    assert rows[0]["dose"] == "75 mg"


def test_converter_holds_a_result_that_bundles_multiple_estimates() -> None:
    item = base_item()
    item["relationship_statement"] = (
        "Drug use improved (g = 1.35, 95% CI 0.63 to 2.07), while alcohol use "
        "improved (g = 0.65, 95% CI 0.31 to 0.99)."
    )

    rows, report = convert_outputs([output_with_result(item)], {"task-1": task()})

    assert rows == []
    assert report["counts"]["held:multiple_estimates_in_one_result"] == 1


def test_converter_holds_network_role_without_network_structure() -> None:
    item = base_item()
    item["result_role"] = "network_comparison"

    rows, report = convert_outputs([output_with_result(item)], {"task-1": task()})

    assert rows == []
    assert report["counts"]["held:network_result_missing_structure"] == 1


def test_converter_holds_a_non_atomic_effect_range() -> None:
    item = base_item()
    item["effect_estimate"]["estimate"] = "-1.48 to -2.36"

    rows, report = convert_outputs([output_with_result(item)], {"task-1": task()})

    assert rows == []
    assert report["counts"]["held:non_atomic_effect_estimate_range"] == 1


def test_converter_holds_unsupported_numbers_and_direction_conflicts() -> None:
    output = output_with_result(base_item())
    output["qa_flags"] = [
        "numeric_value_not_in_source:R1:interval_upper",
        "supports_with_interval_including_null:R1",
    ]

    rows, report = convert_outputs([output], {"task-1": task()})

    assert rows == []
    assert report["counts"]["held:numeric_value_not_in_source"] == 1
    assert report["counts"]["held:statistical_direction_conflict"] == 1


def test_converter_marks_written_result_with_nonblocking_qa_flag_for_review() -> None:
    output = output_with_result(base_item())
    output["qa_flags"] = ["nonverbatim_supporting_text:R1:1"]

    rows, report = convert_outputs([output], {"task-1": task()})

    assert report["counts"]["rows_written"] == 1
    assert rows[0]["needs_human_review"] is True
    assert rows[0]["extraction_warnings"] == "nonverbatim_supporting_text:R1:1"


def test_generic_clinical_endpoint_uses_unambiguous_paper_objective_context() -> None:
    item = base_item()
    item["outcome_or_entity"] = "Remission rate"
    item.pop("population_or_system")
    output = output_with_result(item)
    output["result"]["meta_analysis_overview"]["objective_and_scope"] = (
        "Evaluate ketamine for adults with treatment-resistant depression."
    )

    rows, report = convert_outputs([output], {"task-1": task()})

    assert report["counts"]["rows_written"] == 1
    assert rows[0]["raw_entity_label"] == "Remission rate"
    assert rows[0]["primary_outcome"] == "Remission rate"
    assert rows[0]["clinical_endpoint"] == "Depressive symptoms"
    assert rows[0]["clinical_context_condition"] == "Depressive symptoms"


def test_generic_clinical_endpoint_does_not_choose_between_multiple_conditions() -> None:
    item = base_item()
    item["outcome_or_entity"] = "Response"
    item.pop("population_or_system")
    output = output_with_result(item)
    output["result"]["meta_analysis_overview"]["objective_and_scope"] = (
        "Evaluate treatment effects on depression and anxiety."
    )

    rows, report = convert_outputs([output], {"task-1": task()})

    assert report["counts"]["rows_written"] == 1
    assert rows[0]["clinical_endpoint"] == "Response"
    assert "clinical_context_condition" not in rows[0]


def test_converter_uses_only_unambiguous_overview_population_and_comparator() -> None:
    item = base_item()
    item.pop("population_or_system")
    item.pop("comparator", None)
    output = output_with_result(item)
    output["result"]["meta_analysis_overview"]["populations_or_systems"] = ["Adults with depression"]
    output["result"]["meta_analysis_overview"]["review_question"] = {
        "comparators": ["Placebo"]
    }

    rows, report = convert_outputs([output], {"task-1": task()})

    assert report["counts"]["rows_written"] == 1
    assert rows[0]["population"] == "Adults with depression"
    assert rows[0]["comparator"] == "Placebo"
    assert rows[0]["normalization_population_source"] == "single_overview_population"
    assert rows[0]["normalization_comparator_source"] == "single_overview_comparator"


def test_converter_does_not_assign_ambiguous_overview_context_to_a_result() -> None:
    item = base_item()
    item.pop("population_or_system")
    item.pop("comparator", None)
    output = output_with_result(item)
    output["result"]["meta_analysis_overview"]["populations_or_systems"] = ["Adults", "Adolescents"]
    output["result"]["meta_analysis_overview"]["review_question"] = {
        "comparators": ["Placebo", "Active control"]
    }

    rows, report = convert_outputs([output], {"task-1": task()})

    assert report["counts"]["rows_written"] == 1
    assert "population" not in rows[0]
    assert "comparator" not in rows[0]
