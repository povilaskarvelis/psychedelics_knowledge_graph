import json
from pathlib import Path

from pipeline.kg.convert_meta_analysis_v2_to_evidence_rows import (
    convert_outputs,
    primary_domain_for,
    result_subject_scope,
)


def test_saved_source_result_scopes_do_not_individualize_pooled_effects():
    fixtures = json.loads((Path(__file__).parent / 'fixtures/meta_source_subject_cases.json').read_text())
    expected = {(441, 'R3'): 'intervention_class', (449, 'R1'): 'pooled_multiple_interventions',
                (449, 'R2'): 'pooled_multiple_interventions', (449, 'R3'): None,
                (451, 'R3'): None, (451, 'R5'): None, (451, 'R8'): 'pooled_multiple_interventions',
                (451, 'R9'): 'comparison_between_interventions', (469, 'R6'): 'control_arm'}
    for case in fixtures:
        key = case['audit_index'], case['item']['result_id']
        if key not in expected:
            continue
        subject = case['item']['intervention_or_exposure']
        contract = result_subject_scope(subject, case['item'])
        assert contract.get('meta_analysis_subject_scope') == expected[key], key
        if key == (449, 'R1'):
            assert json.loads(contract['meta_analysis_subject_components_json']) == ['DOI', 'N,N-DMT', 'psilocybin']
        if key == (441, 'R3'):
            assert json.loads(contract['meta_analysis_subject_components_json']) == ['ketamine', 'D-cycloserine', 'minocycline']


def test_subject_scope_preserves_atomic_network_and_coadministered_regimen():
    assert not result_subject_scope('Ketamine', {'relationship_statement': 'Pooled ketamine effect across studies.'})
    assert not result_subject_scope('Ketamine plus propofol', {'relationship_statement': 'The pooled effect of the combination was null.'})
    assert not result_subject_scope('Ketamine', {'result_role': 'network_comparison', 'network_meta_analysis': {'treatment_a': 'Ketamine', 'treatment_b': 'Psilocybin'}})


def test_same_drug_descriptor_alternatives_are_not_multiple_interventions():
    cases = [
        'Moderate- or high-dose psilocybin',
        'Ecstasy use before or during sex',
        'Ecstasy/MDMA use; estimated lifetime use ranged between 30 and 668 tablets',
        'Psilocybin-assisted therapy with psychological support or psychotherapy',
        'Psilocybin-assisted therapy with manualized directive psychotherapy, non-manualized nondirective psychological support, or non-manualized supportive psychotherapy',
        'Psilocybin administration; the broader review includes psilocybin-assisted therapy',
        'Psilocybin or psilocybin-assisted therapy',
        'Chronic/repetitive or continuous ketamine administration',
        'Oral or intravenous ketamine',
        'Ketamine with or without psychological support',
    ]
    for subject in cases:
        item = base_item()
        item.update(intervention_or_exposure=subject,
                    relationship_statement='The pooled association across studies was null.')
        assert not result_subject_scope(subject, item), subject
        rows, _ = convert_outputs([output_with_result(item)], {'task-1': task()})
        assert rows[0]['compound'] == subject
        assert not rows[0].get('meta_analysis_subject_scope'), subject


def test_subject_scope_does_not_discard_unknown_drugs_controls_or_true_comparisons():
    pooled = [
        'Ketamine or esketamine',
        'Psilocybin or compound 37',
        'Ketamine and novel analogue ZTX-71',
        'Ketamine with or without psilocybin',
        'Oral or intravenous ketamine or psilocybin',
        'Psilocybin; other unidentified compounds',
        'DMT/5-MeO-DMT interventions',
        'Psychedelic treatment or psychedelic-assisted therapy',
    ]
    for subject in pooled:
        contract = result_subject_scope(subject, {'relationship_statement': 'The pooled effect across interventions was null.'})
        assert contract.get('meta_analysis_subject_scope') in {'pooled_multiple_interventions', 'intervention_class'}, subject
    for subject in ['Psilocybin-trial control treatment', 'Inert placebo in trials of ketamine',
                    'Inert placebo in trials of ketamine or esketamine', 'Active placebo in psilocybin trials']:
        control = result_subject_scope(subject, {})
        assert control['meta_analysis_subject_scope'] == 'control_arm', subject
    contrast = result_subject_scope('Single-dose intranasal ketamine versus single-dose intravenous ketamine', {})
    assert contrast['meta_analysis_subject_scope'] == 'comparison_between_interventions'


def test_converter_emits_scope_contract_without_altering_raw_exposure():
    item = base_item()
    item['intervention_or_exposure'] = 'Ketamine or psilocybin'
    item['relationship_statement'] = 'Pooling both interventions, the association was negative.'
    rows, _ = convert_outputs([output_with_result(item)], {'task-1': task()})
    assert rows[0]['compound'] == 'Ketamine or psilocybin'
    assert rows[0]['graph_subject_kind'] == 'compound_class'
    assert rows[0]['meta_analysis_subject_scope'] == 'pooled_multiple_interventions'


def test_saved_outcome_roles_preserve_clinical_dependents_and_subjective_endpoints():
    fixtures = json.loads((Path(__file__).parent / 'fixtures/meta_source_outcome_role_cases.json').read_text())
    expected = {428: 'clinical_outcome', 431: 'subjective_experience',
                438: 'safety_tolerability', 458: 'clinical_outcome', 462: 'subjective_experience'}
    for case in fixtures:
        item = case['item']
        assert primary_domain_for(item)[0] == expected[case['audit_index']]
        if case['audit_index'] == 458:
            rows, _ = convert_outputs([output_with_result(item)], {'task-1': task()})
            assert rows[0]['clinical_endpoint'] == 'Change in death anxiety'
            assert rows[0]['meta_analysis_subgroup_or_moderator'] == 'Mystical-experience score, continuous moderator'
            assert rows[0]['meta_analysis_regression_coefficient'] == 'B = 4.90'
            assert item['primary_subject_area'] == 'subjective_experience'


def test_meta_regression_domain_does_not_follow_a_background_clinical_mention():
    item = base_item()
    item.update(result_role='meta_regression', primary_subject_area='subjective_experience',
                subject_areas=['subjective_experience', 'clinical_outcome'],
                outcome_or_entity='Mystical experience score',
                relationship_statement='Participants had depression; dose predicted mystical experience.')
    assert primary_domain_for(item) == ('subjective_experience', 'explicit_primary_subject_area')


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


def test_converter_uses_reported_endpoint_for_broad_transdiagnostic_population() -> None:
    item = base_item()
    item["population_or_system"] = "Adults with mental health disorders"
    item["outcome_or_entity"] = "Psychiatric symptom severity"
    item["relationship_statement"] = "The augmentation reduced psychiatric symptom severity."

    rows, report = convert_outputs([output_with_result(item)], {"task-1": task()})

    assert report["counts"]["rows_written"] == 1
    assert rows[0]["kg_entity_kind_override"] == "symptom_problem"
    assert rows[0]["graph_entity_label"] == "Psychiatric symptom severity"
    assert rows[0]["normalization_entity_source"] == "result_outcome_or_entity"


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


def test_converter_preserves_structured_brain_entities_separately_from_measure() -> None:
    item = base_item()
    item["primary_subject_area"] = "brain_system"
    item["subject_areas"] = ["brain_system"]
    item["population_or_system"] = "Healthy volunteers"
    item["outcome_or_entity"] = "Between-network functional connectivity"
    item["relationship_statement"] = (
        "Psilocybin altered connectivity in the default mode and visual networks."
    )
    item["intervention_or_exposure"] = "Psilocybin"
    item["brain_system_entities"] = [
        {"entity_type": "brain_network", "label": "Default mode network"},
        {"entity_type": "brain_network", "label": "Visual network"},
    ]

    rows, report = convert_outputs([output_with_result(item)], {"task-1": task()})

    assert report["counts"]["rows_written"] == 1
    row = rows[0]
    assert row["graph_entity_label"] == "Default mode network; Visual network"
    assert row["kg_entity_kind_override"] == "brain_network"
    assert row["brain_measure"] == "Between-network functional connectivity"
    assert json.loads(row["brain_system_entities_json"]) == item["brain_system_entities"]


def test_converter_preserves_structured_target_entities_separately_from_measure() -> None:
    item = base_item()
    item["primary_subject_area"] = "molecular_target"
    item["subject_areas"] = ["molecular_target"]
    item["population_or_system"] = "Heterologous receptor assays"
    item["outcome_or_entity"] = "Binding selectivity (Ki ratio)"
    item["relationship_statement"] = (
        "Classic psychedelics showed binding selectivity across serotonergic and dopaminergic targets."
    )
    item["intervention_or_exposure"] = "Classic psychedelics"
    item["molecular_target_entities"] = [
        {"entity_type": "target", "label": "5-HT2A"},
        {"entity_type": "target", "label": "Dopamine D2 receptor (DRD2)"},
    ]

    rows, report = convert_outputs([output_with_result(item)], {"task-1": task()})

    assert report["counts"]["rows_written"] == 1
    row = rows[0]
    assert row["graph_entity_label"] == "5-HT2A; Dopamine D2 receptor (DRD2)"
    assert row["kg_entity_kind_override"] == "target"
    assert row["primary_outcome"] == "Binding selectivity (Ki ratio)"
    assert json.loads(row["molecular_target_entities_json"]) == item["molecular_target_entities"]


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


def test_converter_keeps_one_pooled_or_with_its_arm_rates() -> None:
    item = base_item()
    item['relationship_statement'] = 'Ketamine increased response versus placebo: 52.2% versus 7.8%, pooled OR10.09 (95% CI4.96-20.52).'
    item['effect_estimate'] = {'metric': 'Odds ratio', 'estimate': '10.09', 'interval_lower': '4.96', 'interval_upper': '20.52'}
    output = output_with_result(item)
    output['qa_flags'] = ['multiple_estimates_in_one_result:R1', 'nonverbatim_supporting_text:R1:1']
    rows, report = convert_outputs([output], {'task-1': task()})
    assert len(rows) == 1
    assert report['counts'].get('held:multiple_estimates_in_one_result', 0) == 0
    assert 'multiple_estimates_in_one_result' not in rows[0]['extraction_warnings']
    assert 'nonverbatim_supporting_text:R1:1' in rows[0]['extraction_warnings']
    assert json.loads(rows[0]['statistical_validation_recheck_json'])['superseded_source_validation_flags'] == ['multiple_estimates_in_one_result:R1']
    assert output['qa_flags'] == ['multiple_estimates_in_one_result:R1', 'nonverbatim_supporting_text:R1:1']


def test_converter_holds_explicit_rd_nnt_scale_conflict_without_rewriting() -> None:
    item = base_item()
    item['relationship_statement'] = 'Treatment increased response: RD=0.11% and NNT=9.'
    item['effect_estimate'] = {'metric': 'Risk difference', 'estimate': '0.11%', 'interval_lower': '.05', 'interval_upper': '.16'}
    rows, report = convert_outputs([output_with_result(item)], {'task-1': task()})
    assert rows == []
    assert report['counts']['held:effect_estimate_scale_conflict'] == 1
    assert item['effect_estimate']['estimate'] == '0.11%'


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


def test_stable_task_fallback_requires_same_doi_and_text_depth() -> None:
    output = output_with_result(base_item())
    output["task_id"] = "old-task-id"
    current_task = task()
    current_task.update(
        {
            "task_id": "new-task-id",
            "study_doi": "10.1/meta",
            "text_depth": "article_text",
        }
    )

    rows, report = convert_outputs(
        [output],
        {"new-task-id": current_task},
        allow_stable_task_fallback=True,
    )

    assert len(rows) == 1
    assert report["counts"]["stable_task_fallback"] == 1

    changed_depth = dict(current_task, text_depth="abstract_only")
    rows, report = convert_outputs(
        [output],
        {"new-task-id": changed_depth},
        allow_stable_task_fallback=True,
    )

    assert rows == []
    assert report["counts"]["missing_task"] == 1


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


def test_converter_preserves_explicit_multiplicity_adjustment_without_inferring_it():
    baseline, _ = convert_outputs([output_with_result(base_item())], {'task-1': task()})
    for adjustment in ('Uncorrected results', 'TFCE family-wise error corrected', ''):
        item = base_item()
        item['analysis_context'] = {'multiplicity_adjustment': adjustment}
        rows, _ = convert_outputs([output_with_result(item)], {'task-1': task()})
        assert rows[0].get('meta_analysis_multiplicity_adjustment', '') == adjustment
        assert item['analysis_context']['multiplicity_adjustment'] == adjustment
        assert rows[0].get('graph_admission_status') == baseline[0].get('graph_admission_status')
