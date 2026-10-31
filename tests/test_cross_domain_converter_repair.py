"""Regression controls for saved-output coverage and complete hold accounting."""

from pipeline.kg.convert_routed_extractions_to_evidence_rows import evidence_row_for_item
from pipeline.kg.convert_meta_analysis_v2_to_evidence_rows import (
    convert_outputs as convert_meta, descriptive_frequency_estimate,
)
import copy
import json
from pipeline.kg.convert_review_relationship_bundles_to_evidence_rows import (
    object_graph_mapping, named_object_domain_supported,
)


def brain_row(item):
    return evidence_row_for_item(
        output_row={"task_id": "brain-task", "status": "ok"},
        result={
            "task_id": "brain-task", "study_doi": "10.1000/control",
            "domain_route": "brain_system", "extraction_status": "extracted",
            "text_depth": "article_text", "source_type": "primary",
        },
        item=item, item_kind="primary_item", item_index=1, tasks={},
    )


def test_named_circuit_survives_empty_preferred_network_field_without_splitting():
    item = {
        "compound_or_exposure": "S-ketamine",
        "primary_graph_anchor_kind": "brain_network",
        "brain_network": "not_reported",
        "brain_region": "pgACC seed; medial prefrontal cortex target",
        "neural_circuit": "pgACC-to-mPFC functional connectivity",
        "readout": "Resting-state functional connectivity",
        "statistic_or_value": "pFWEc < 0.001",
        "finding_summary": "S-ketamine increased pgACC-mPFC functional connectivity.",
    }
    row = brain_row(item)
    assert row["kg_entity_kind_override"] == "neural_circuit"
    assert row["graph_entity_label"] == item["neural_circuit"]
    assert row["primary_graph_anchor_kind"] == "brain_network"
    assert row["normalization_original_brain_anchor_kind"] == "brain_network"
    assert row["normalization_brain_anchor_source_field"] == "neural_circuit"
    for field in ("brain_region", "neural_circuit", "readout", "statistic_or_value", "finding_summary"):
        assert row[field] == item[field]


def test_existing_preferred_network_is_not_replaced_by_context_regions():
    item = {
        "compound_or_exposure": "Psilocybin",
        "primary_graph_anchor_kind": "brain_network",
        "brain_network": "Default mode network",
        "brain_region": "Anterior cingulate cortex",
        "neural_circuit": "ACC-to-PCC connectivity",
    }
    row = brain_row(item)
    assert row["kg_entity_kind_override"] == "brain_network"
    assert row["graph_entity_label"] == "Default mode network"
    assert "normalization_original_brain_anchor_kind" not in row


def test_valid_missing_anchor_can_use_explicit_region_but_not_task_context():
    row = brain_row({
        "compound_or_exposure": "Ketamine",
        "primary_graph_anchor_kind": "brain_network",
        "brain_network": "not_reported", "neural_circuit": "not_reported",
        "brain_region": "Frontal-temporal scalp regions",
        "readout": "EEG delta-band correlation",
    })
    assert row["kg_entity_kind_override"] == "brain_region"
    assert row["graph_entity_label"] == "Frontal-temporal scalp regions"
    assert brain_row({
        "compound_or_exposure": "Ketamine",
        "primary_graph_anchor_kind": "brain_region",
        "brain_region": "not_reported", "brain_network": "not_reported",
        "neural_circuit": "not_reported", "readout": "not_applicable",
        "task_or_state": "Hippocampal-dependent water-maze performance",
    }) is None


def test_explicit_inapplicability_does_not_rescue_behavior_as_neural_measurement():
    assert brain_row({
        "compound_or_exposure": "DOI",
        "primary_graph_anchor_kind": "not_applicable",
        "brain_region": "Hippocampus (background only)",
        "brain_network": "not_applicable", "neural_circuit": "not_applicable",
        "readout": "not_applicable", "task_or_state": "Head-twitch response",
    }) is None


def test_meta_hold_accounting_is_complete_beyond_human_preview_limit():
    items = [{
        "result_id": f"R{i}", "primary_subject_area": "clinical_outcome",
        "subject_areas": ["clinical_outcome"], "result_role": "network_comparison",
        "intervention_or_exposure": "Ketamine", "outcome_or_entity": "Depressive symptoms",
        "population_or_system": "Adults with depression", "comparator": "Placebo",
    } for i in range(1, 106)]
    outputs = [{
        "status": "ok", "task_id": "meta-task", "study_doi": "10.1000/meta-control",
        "result": {"extraction_status": "extracted", "synthesis_results": items},
    }]
    rows, report = convert_meta(outputs, {"meta-task": {"task_id": "meta-task"}})
    assert rows == []
    assert len(report["held_samples"]) == 100
    assert len(report["item_exclusions"]) == 105
    assert report["item_exclusions"][-1]["result_id"] == "R105"
    assert report["item_exclusions"][-1]["source_item_index"] == 105
    assert report["counts"]["held:network_result_missing_structure"] == 105


def test_review_named_outcome_uses_explicit_domain_in_human_and_mixed_sources():
    anchor = {"role": "outcome", "label": "Prepulse inhibition (PPI)", "anchor_type": "named_entity"}
    for stratum in ("human", "human_and_preclinical", "preclinical", "unclear"):
        relation = {"domain_labels": ["cognitive_behavioral"], "evidence_stratum": stratum}
        assert object_graph_mapping(relation, anchor) == (
            "cognitive_behavioral", "cognitive_behavioral_construct", "graph_construct_label",
        )
        assert named_object_domain_supported(relation, anchor)


def test_review_named_neural_readout_is_not_a_patient_condition():
    relation = {"domain_labels": ["brain_system"]}
    anchor = {"role": "outcome", "label": "Reduced alpha power", "anchor_type": "named_entity"}
    assert object_graph_mapping(relation, anchor) == ("brain_system", "brain_measure", "readout")


def test_review_does_not_infer_domain_for_mixed_broad_or_untyped_outcomes():
    anchor = {"role": "outcome", "label": "PPI", "anchor_type": "named_entity"}
    assert object_graph_mapping({"domain_labels": ["clinical_outcome", "cognitive_behavioral"]}, anchor)[0] == "clinical_outcome"
    assert object_graph_mapping({"domain_labels": []}, anchor)[0] == "clinical_outcome"
    broad = {"role": "outcome", "label": "Subjective, cardiovascular, and adverse effects", "anchor_type": "other"}
    assert object_graph_mapping({"domain_labels": ["safety_tolerability"]}, broad)[0] == "clinical_outcome"
    condition = {"role": "condition", "label": "Depressive disorder", "anchor_type": "named_entity"}
    assert object_graph_mapping({"domain_labels": ["cognitive_behavioral"]}, condition)[0] == "clinical_outcome"


def descriptive_incidence_item():
    return {
        "result_id": "R1", "primary_subject_area": "real_world_public_health",
        "subject_areas": ["real_world_public_health", "safety_tolerability"],
        "result_role": "primary_synthesis", "importance_in_paper": "main",
        "intervention_or_exposure": "Ritual ayahuasca or peyote use", "comparator": None,
        "outcome_or_entity": "Incidence of psychosis", "population_or_system": "Ritual-use populations",
        "relationship_statement": "The pooled incidence was 0.002% (95% CI 0 to 0.006).",
        "effect_estimate": {"metric": "Incidence", "estimate": "0.002%", "interval_lower": "0", "interval_upper": "0.006"},
        "interpretation": {"finding_direction": "supports", "statistical_interpretation": "The incidence was 0.002%."},
    }


def test_nonclinical_review_topic_does_not_become_a_condition_from_incidental_pain():
    anchor = {"role": "outcome", "anchor_type": "paper_topic", "label": "Pain-mediated spiritual transformation and altered consciousness"}
    assert object_graph_mapping({"domain_labels": ["subjective_experience", "intervention_context"]}, anchor) == (
        "general_topic_coverage", "reported_measurement", "graph_entity_label",
    )
    assert object_graph_mapping({"domain_labels": ["clinical_outcome", "subjective_experience"]}, anchor)[0] == "clinical_outcome"


def test_descriptive_incidence_preserves_zero_interval_without_inventing_significance():
    item = descriptive_incidence_item()
    original = copy.deepcopy(item)
    output = {"status": "ok", "task_id": "meta-task", "study_doi": "10.1000/incidence",
              "qa_flags": ["supports_with_interval_including_null:R1"],
              "result": {"extraction_status": "extracted", "synthesis_results": [item]}}
    rows, report = convert_meta([output], {"meta-task": {"task_id": "meta-task"}})
    assert item == original
    assert len(rows) == 1 and report["item_exclusions"] == []
    assert rows[0]["estimate_value"] == "0.002%"
    assert rows[0]["meta_analysis_interval_lower"] == "0"
    assert rows[0]["meta_analysis_interval_upper"] == "0.006"
    recheck = json.loads(rows[0]["statistical_validation_recheck_json"])
    assert recheck["superseded_source_validation_flags"] == ["supports_with_interval_including_null:R1"]
    assert not rows[0].get("needs_human_review", False)
    assert output["qa_flags"] == ["supports_with_interval_including_null:R1"]


def test_frequency_exception_does_not_clear_contrasts_pvalues_or_significance_claims():
    base = descriptive_incidence_item()
    variants = [
        {"comparator": "Nonusers"},
        {"relationship_statement": "The incidence was significantly above zero."},
        {"effect_estimate": {**base["effect_estimate"], "metric": "Incidence rate ratio"}},
        {"effect_estimate": {**base["effect_estimate"], "p_value": "0.02"}},
        {"result_role": "meta_regression"},
    ]
    for change in variants:
        assert not descriptive_frequency_estimate({**base, **change})
