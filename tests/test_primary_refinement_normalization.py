"""Source-audit regressions: scientific invariants and contrastive controls.

These fixtures test identities/roles, not historical graph row counts. They
deliberately vary incidental context while keeping the observed endpoint fixed.
"""
import json

import pytest

from pipeline.kg import build_evidence_tables as b
from pipeline.kg import convert_routed_extractions_to_evidence_rows as c
from pipeline.kg import pk_relationships as pk


@pytest.fixture(scope="module")
def registry():
    return b.registry_lookup(b.DEFAULT_REGISTRY_PATH)


@pytest.mark.parametrize("label", [
    "1-methyl-d-lysergic acid diethylamide (MLD-41)",
    "MLD-41, compared with LSD-25",
    "1P-ETH-LAD", "1cP-LSD",
    "1T-LSD", "Cl-MDMA", "6-Cl-MDMA", "2-oxo-3-OH-LSD",
])
def test_unregistered_derivative_never_inherits_parent_identity(label, registry):
    row = {"compound": label}
    c.apply_graph_subject(row)
    match = b.graphable_subject_match(row, registry)
    assert match["matched"]
    assert match["label"] == label
    assert b.overview_graph_subjects(row, match, registry) == []


@pytest.mark.parametrize("label,expected", [
    ("LSD", "LSD"), ("d-lysergic acid diethylamide", "LSD"),
    ("5OMeDMT", "5-MeO-DMT"), ("5-OMe-DMT", "5-MeO-DMT"),
    ("S,R(±)ketamine", "Ketamine"), ("(R,S)-ketamine", "Ketamine"),
    ("R-ketamine", "R-ketamine"), ("S-ketamine", "S-ketamine"),
    ("MDMA", "MDMA"), ("Norketamine", "Norketamine"),
    ("1P-LSD", "1P-LSD"), ("ETH-LAD (6-ethyl-6-nor-lysergic acid diethylamide)", "ETH-LAD"),
])
def test_parent_names_racemate_and_enantiomers_remain_distinct(label, expected, registry):
    match = b.graphable_compound_match(label, registry)
    assert match["matched"] and match["label"] == expected


@pytest.mark.parametrize("study,expected", [
    ("Intravenous ketamine administration to healthy volunteers", "other"),
    ("Exploratory moderation analysis of human self-report", "other"),
    ("Analysis of informed consent documents at outpatient clinics", "other"),
    ("Randomized rat experiment", "preclinical"),
    ("Randomized human controlled trial", "randomized_controlled_trial"),
    ("In vitro pharmacological assay in rat cerebral cortex", "in_vitro"),
    ("Ex vivo measurement in rat brain slices", "ex_vivo"),
    ("Long-term follow-up of a randomized controlled trial", "observational"),
    ("Open-label phase of a randomized clinical trial", "nonrandomized_clinical_trial"),
])
def test_design_regex_uses_whole_words_and_observation_phase(study, expected):
    assert c.evidence_design_for({"study_design_category": "other", "study_design": study}) == expected


@pytest.mark.parametrize("design,system,expected", [
    ("In vitro live-cell imaging", "rat hippocampal neurons", "in_vitro"),
    ("In vitro pharmacological assay", "rat cortex", "in_vitro"),
    ("Ex vivo electrophysiology", "rat brain slices", "ex_vivo"),
    ("Whole-animal behavior", "rat", "in_vivo"),
])
def test_measurement_preparation_precedes_species(design, system, expected):
    assert b.inferred_experimental_system({"study_design": design, "system": system}) == expected


def test_declared_experimental_system_still_wins():
    assert b.inferred_experimental_system({"experimental_system_category": "in_vivo", "study_design": "In vivo exposure followed by ex vivo measurement", "system": "rat"}) == "in_vivo"


@pytest.mark.parametrize("label", ["5-HT2A (serotonin) receptor", "5-hydroxytryptamine 2A (serotonin) receptor"])
def test_parenthetical_ligand_does_not_replace_receptor(label, registry):
    m = b.match_registry_entity(label, "target", registry)
    assert (m["label"], m["kind"]) == ("5-HT2A", "target")


def test_target_reporter_does_not_become_target_abundance(registry):
    row = {"target": "NMDA receptor", "finding_summary": "DOM and NMDA increased cGMP content in cortical slices."}
    m = b.match_registry_entity("NMDA receptor", "target", registry, row)
    assert m["kind"] == "target"
    m = b.match_registry_entity("NMDA receptor protein levels", "target", registry, row)
    assert m["kind"] == "biomarker_readout"


@pytest.mark.parametrize("irrelevant", [
    "The genotype contrast changed the outcome.",
    "BDNF changes correlated with slow-wave activation.",
    "Rapamycin blocked the effect on macrophage marker expression.",
])
def test_unrelated_context_does_not_append_measurement(irrelevant):
    assert b.molecular_readout_display_label({"finding_summary": irrelevant}, "ECoG", "ECoG") == "ECoG"


def test_local_readout_phrase_still_retains_legacy_measurement():
    assert b.molecular_readout_display_label({"support": "BDNF expression increased after treatment."}, "BDNF", "BDNF") == "BDNF expression"


@pytest.mark.parametrize("marker", ["c-Fos/5-HT2A-", "c-Fos+/5-HT2A− cells", "c-Fos-positive/5-HT2A receptor-negative cells"])
def test_negative_cell_population_is_one_measurement(marker, registry):
    row = {"domain": "molecular_pathway_readout", "compound": "DOI", "specific_readout_or_marker": marker,
           "molecular_effect_category": "Immediate early gene activation", "primary_graph_anchor_kind": "biomarker_readout"}
    rows = b.entity_expanded_rows(row, row["domain"], registry, b.node_vocabulary_lookup())
    assert len(rows) == 1
    m = b.graphable_entity_match(row, row["domain"], "biomarker_readout", marker, registry, b.node_vocabulary_lookup())
    assert m["matched"] and m["label"] == marker
    assert b.molecular_parent_from_specific(row, "Receptor regulation & trafficking", marker) == "Gene expression & activity markers"


def test_mixed_depression_cohort_is_not_bipolar_only(registry):
    row = {"population_or_subgroup": "Participants with unipolar or bipolar depression"}
    assert b.specific_condition_from_unambiguous_context(row, "Major depressive episode", "Depressive disorders", registry) == ""
    assert b.specific_condition_from_unambiguous_context({"population_or_subgroup": "Patients with bipolar depression"}, "Major depressive episode", "Depressive disorders", registry) == "Bipolar depression"


def test_mitochondrial_respiration_is_not_breathing_safety():
    row = b.normalize_claim_metadata({"compound": "MDMA", "safety_event_or_measure": "Mitochondrial uncoupling assessed by rates of respiration", "study_design": "Isolated liver mitochondria assay"}, "safety_tolerability")
    assert row["domain"] == "molecular_pathway_readout"
    assert row["molecular_effect_category"] == "Cellular stress & mitochondrial function"
    control = b.normalize_claim_metadata({"compound": "MDMA", "safety_event_or_measure": "Respiratory depression and hypoxia"}, "safety_tolerability")
    assert control["domain"] == "safety_tolerability"


@pytest.mark.parametrize("anchor,summary,reason", [
    ("Concerns about delirium", "Experts reported concern, not an observed event rate.", "anticipated_or_policy_safety_not_observed_event"),
    ("Medication washout requirements", "Organizations required washout; participant-level harms were not measured.", "anticipated_or_policy_safety_not_observed_event"),
    ("Communication about long-term adverse effects in consent documents", "Documents did not describe risks adequately.", "safety_documentation_not_observed_event"),
])
def test_policy_or_perception_survives_as_detail(anchor, summary, reason):
    row = b.normalize_claim_metadata({"compound": "Psilocybin", "safety_event_or_measure": anchor, "finding_summary": summary}, "safety_tolerability")
    assert b.graph_admission_decision(row) == ("paper_detail", reason)
    assert json.loads(row["normalization_repairs_json"])[0]["rule"] == reason
    observed = b.normalize_claim_metadata({"compound": "Psilocybin", "safety_event_or_measure": "Delirium", "finding_summary": "One participant developed delirium after dosing."}, "safety_tolerability")
    assert b.graph_admission_decision(observed)[0] == "main_graph"


def test_adjunct_continuation_cannot_be_atomic_ketamine_result(registry):
    row = b.normalize_claim_metadata({"compound": "Ketamine", "compound_or_exposure": "Lithium continuation versus placebo following ketamine infusions", "safety_event_or_measure": "Nausea"}, "safety_tolerability")
    match = b.graphable_subject_match(row, registry)
    assert b.overview_graph_subjects(row, match, registry) == []
    assert row["graph_subject_label"] == "Lithium continuation versus placebo following ketamine infusions"
    assert b.graph_admission_decision(row)[0] == "paper_detail"
    control = b.normalize_claim_metadata({"compound": "Ketamine", "compound_or_exposure": "Ketamine versus placebo", "safety_event_or_measure": "Nausea following ketamine"}, "safety_tolerability")
    assert b.graph_admission_decision(control)[0] == "main_graph"


def test_questionnaire_psychotic_score_not_clinical_psychosis():
    row = b.normalize_claim_metadata({"compound": "2C-E", "subjective_construct": "Psychotic symptoms", "finding_summary": "VESSPA psychotic-symptom subscale scores increased acutely."}, "subjective_experience")
    assert row["domain"] == "subjective_experience"
    assert row["graph_entity_label"] != "Psychosis risk"
    control = b.normalize_claim_metadata({"compound": "2C-E", "subjective_construct": "Psychosis", "finding_summary": "Persistent psychosis required hospitalization."}, "subjective_experience")
    assert control["domain"] == "safety_tolerability"


def test_rash_does_not_borrow_renal_followup_context(registry):
    row = {"safety_event_or_measure": "Maculopapular rash", "finding_summary": "The rash resolved at renal clinic follow-up.", "discontinuation_or_withdrawal": "Avoided further infusions pending renal pathology."}
    assert b.safety_endpoint_label(row) != "Renal/muscle toxicity"
    m = b.graphable_entity_match(row, "safety_tolerability", "safety_adverse_event", "Maculopapular rash", registry, b.node_vocabulary_lookup())
    assert m["label"] == "Maculopapular rash" and m["match_type"].endswith("detail_only")


def test_pk_route_alone_does_not_claim_route_effect():
    row = {"compound_or_analyte": "MDMA", "metabolite_or_analyte": "MDMA", "matrix": "blood", "pk_or_exposure_parameter": "concentration", "route_of_administration": "oral"}
    assert pk.infer_pk_relationship(row)["pk_relationship_type"] != "route_or_formulation_changes_exposure"
    association = {**row, "finding_summary": "Blood MDMA levels correlated with subjective feelings."}
    assert pk.infer_pk_relationship(association)["pk_relationship_type"] == "exposure_linked_to_effect"
    comparison = {**row, "matrix": "", "pk_or_exposure_parameter": "bioavailability", "finding_summary": "Oral compared with intravenous administration."}
    assert pk.infer_pk_relationship(comparison)["pk_relationship_type"] == "route_or_formulation_changes_exposure"


def test_comparator_is_not_automatically_drug_interaction():
    row = {"compound_or_analyte": "Ketamine", "pk_or_exposure_parameter": "Cmax", "comparator_or_reference": "baseline or placebo", "finding_summary": "Concentrations were measured after treatment."}
    assert pk.infer_pk_relationship(row)["pk_relationship_type"] != "exposure_altered_by"
    assert pk.infer_pk_relationship({**row, "co_exposure_or_modifier": "Rifampicin pretreatment"})["pk_relationship_type"] == "exposure_altered_by"


def test_pk_self_exposure_and_self_metabolism_are_distinct():
    row = {"compound": "Bufotenin", "pk_graph_object_kind": "metabolite_or_analyte", "pk_graph_object_label": "Bufotenin", "pk_or_exposure_parameter": "Cmax"}
    assert pk.pk_graph_entity_kind({**row, "pk_relationship_type": "exposure_characterized"}) == "pharmacokinetic_parameter"
    assert pk.pk_graph_entity_kind({**row, "pk_relationship_type": "metabolized_to"}) == "compound"


def test_occupancy_without_exposure_association_remains_target_observation():
    row = {"pk_or_exposure_parameter": "occupancy", "metabolic_or_transport_target": "serotonin transporter", "matrix": "brain_tissue", "finding_summary": "Occupancy did not differ from zero after ketamine."}
    assert pk.pk_pharmacodynamic_target(row) == "serotonin transporter"
    assert pk.pk_pharmacodynamic_target({**row, "finding_summary": "Plasma AUC correlated with SERT occupancy."}) == ""


def test_randomized_open_label_trial_is_not_nonrandomized():
    row = {'study_design_category': 'other', 'population_model_category': 'human_participants', 'study_design': 'Randomized open-label trial of ketamine versus standard treatment'}
    assert c.evidence_design_for(row) == 'randomized_controlled_trial'
    row['study_design'] = 'Open-label extension of a randomized clinical trial'
    assert c.evidence_design_for(row) == 'nonrandomized_clinical_trial'


@pytest.mark.parametrize('summary', [
    'Plasma MDMA concentrations correlated with saliva concentrations.',
    'Plasma MDMA concentrations were associated with higher doses.',
])
def test_pk_correlation_without_response_is_not_exposure_effect(summary):
    row = {'compound': 'MDMA', 'pk_or_exposure_parameter': 'concentration', 'finding_summary': summary}
    assert pk.infer_pk_relationship(row)['pk_relationship_type'] != 'exposure_linked_to_effect'


@pytest.mark.parametrize('marker,category', [
    ('Iba1-positive/CD68-positive cells', 'Neuroinflammation & immune signaling'),
    ('BrdU-positive/DCX-positive cells', 'Neurogenesis'),
    ('TUNEL-positive/NeuN-positive cells', 'Cell injury & survival'),
])
def test_cell_intersection_preserves_non_activity_marker_category(marker, category):
    row = {'specific_readout_or_marker': marker, 'molecular_effect_category': category}
    assert b.is_cell_phenotype_intersection(marker)
    assert b.molecular_effect_label(row, 'biomarker_readout', marker) == category
    assert b.molecular_effect_graph_label(row, 'biomarker_readout', marker) == category
    assert b.molecular_parent_from_specific(row, category, marker) == category


def test_pooled_depression_retains_exact_detail_without_subtype(registry):
    row = {'population': 'Patients with unipolar or bipolar depression'}
    m = b.graphable_entity_match(row, 'clinical_outcome', 'condition_indication', 'Major depressive episode', registry, {})
    assert m['matched'] and m['label'] == 'Major depressive episode'
    assert m['match_type'] == 'pooled_condition_detail_only'


def test_participant_context_does_not_inherit_facilitator_parent(registry):
    row = {'component_type': 'subjective session experience', 'delivery_format': 'Facilitator supported dosing', 'context_component': 'Session experienced as emotional'}
    m = b.graphable_entity_match(row, 'intervention_context', 'intervention_component', row['context_component'], registry, {})
    assert m['match_type'] == 'context_measure_without_canonical_parent_detail_only'
    assert b.intervention_parent_label(row, row['context_component']) == ''
    assert b.intervention_parent_label({**row, 'context_component': 'Ability to surrender'}, 'Ability to surrender') == 'Set & setting'
    assert b.intervention_parent_label({'context_component': 'Facilitator support'}, 'Facilitator support') == 'Facilitator role'


def test_service_integration_is_not_post_session_integration():
    assert b.intervention_parent_label({}, 'Integration into existing care services') == ''
    assert b.intervention_parent_label({}, 'Post-session integration') == 'Integration'


def test_assay_probe_is_not_coadministered_drug_interaction():
    assert b.safety_category_for_text('[3H]paroxetine binding reduction') != 'Drug interaction risk'
    assert b.safety_category_for_text('Drug interaction between MDMA and paroxetine co-administration') == 'Drug interaction risk'


def test_explicit_human_trial_unit_precedes_companion_assays():
    row = {'study_design_category': 'randomized_controlled_trial', 'experimental_system_category': 'clinical', 'population_model_category': 'human_participants', 'study_design': 'Randomized human trial with companion in vitro binding assays'}
    assert c.evidence_design_for(row) == 'randomized_controlled_trial'
    assert b.inferred_experimental_system(row) == 'clinical'
    assert c.evidence_design_for({'study_design_category': 'other', 'study_design': 'Randomized controlled trial with long-term follow-up'}) == 'randomized_controlled_trial'


def test_generic_receptor_with_qualifier_is_not_ligand(registry):
    raw = '5-hydroxytryptamine (5-HT) receptor-mediated neuronal responses; receptor subtype not specified'
    m = b.match_registry_entity(raw, 'target', registry, {'target': raw})
    assert m['kind'] == 'system_family'
    assert m['label'] == '5-HT receptor family'


def test_instrument_reliability_does_not_demote_an_observed_association():
    row = {'subjective_construct': 'Psychological insight', 'outcome_measure': 'Insight scale; internal consistency alpha=0.80', 'study_design': 'Cross-sectional observational survey', 'finding_summary': 'Insight was associated with perceived support.'}
    b.current_field_role_boundary(row, 'subjective_experience')
    assert row.get('graph_admission_status') != 'paper_detail'
    row['study_design'] = 'Psychometric validation and factor analysis of the insight scale'
    b.current_field_role_boundary(row, 'subjective_experience')
    assert row['graph_admission_reason'] == 'measurement_validation_not_drug_effect'


def test_distinct_measured_metabolites_keep_their_identity():
    row = {'compound': 'MDMA', 'pk_relationship_type': 'exposure_characterized', 'pk_graph_object_kind': 'metabolite_or_analyte', 'pk_graph_object_label': 'HMMA', 'pk_or_exposure_parameter': 'concentration'}
    assert pk.pk_graph_entity_kind(row) == 'compound'
    assert pk.pk_graph_entity_label(row) == 'HMMA'


def test_open_label_without_allocation_information_is_unknown():
    assert c.evidence_design_for({'study_design': 'Open-label clinical trial with a delayed treatment control group'}) == 'unspecified'
    assert c.evidence_design_for({'study_design': 'Subchronic administration', 'population': 'Rats (Sprague-Dawley)'}) == 'preclinical'
    assert c.evidence_design_for({'system': 'in_vitro', 'study_design': 'In vitro and ex vivo mitochondrial study'}) == 'in_vitro'
    assert c.evidence_design_for({'experimental_system_category': 'in_vivo', 'study_design_category': 'functional_assay', 'population_model_category': 'animal_model'}) == 'preclinical'


def test_arterial_pressure_fall_is_not_falling_behavior():
    assert b.safety_endpoint_label({'safety_event_or_measure': 'Arterial pressure fall', 'safety_category': 'cardiovascular safety'}) == 'Cardiovascular safety'
    assert b.safety_category_for_text('Falls due to motor impairment') == 'Sedation/cognitive or motor impairment'
    assert b.safety_endpoint_label({'safety_event_or_measure': 'Dropouts due to intolerable symptoms'}) == 'Discontinuation due to adverse events'


def test_mortality_denominator_does_not_replace_use_context_endpoint():
    assert b.public_health_graph_label({'public_health_measure': 'Proportion of deaths occurring in recreational-use versus dependent-use contexts', 'public_health_topic_category': 'Use patterns & practices'}) == 'Use patterns & practices'
    assert b.public_health_graph_label({'public_health_measure': 'Annual deaths with illicit ketamine detected at post-mortem', 'public_health_topic_category': 'Population use & trends'}) == 'Acute harms & healthcare use'


def test_downstream_release_is_not_a_direct_transporter_assay():
    assert pk.pk_pharmacodynamic_target({'pk_or_exposure_parameter': 'dose-response', 'metabolic_or_transport_target': 'serotonin transporter', 'pk_graph_object_label': 'striatal serotonin release'}) == ''


def test_broad_assay_class_retains_class_without_metabolite_parent_alias(registry):
    row = {'compound': 'LSD, 2-oxo-3-OH-LSD, psilocin, and other hallucinogens', 'graph_subject_label': 'LSD, 2-oxo-3-OH-LSD, psilocin, and other hallucinogens', 'graph_subject_kind': 'compound_class'}
    m = b.graphable_subject_match(row, registry)
    assert b.overview_graph_subjects(row, m, registry) == [{'label': 'Hallucinogens', 'kind': 'compound_class', 'reason': 'controlled_compound_class'}]


def test_global_harm_question_is_not_a_policy_concern():
    assert b.safety_category_for_text('Participant-reported harm from study participation') == 'Overall tolerability'
    assert b.safety_category_for_text('Response to “Do you feel you were harmed by participation in the study?”') == 'Overall tolerability'
    assert b.safety_category_for_text('Acute symptoms of untoward effects after MDMA') == 'Adverse events'


def test_physiological_fall_does_not_generate_second_sedation_endpoint():
    raw = 'Arterial pressure: LSD caused rises in rats and small falls in cats'
    matched = [label for pattern, label in b.SAFETY_ENDPOINT_PATTERNS if pattern.search(raw)]
    assert 'Cardiovascular safety' in matched
    assert 'Sedation/cognitive or motor impairment' not in matched
    assert b.safety_category_for_text('Falls') == 'Sedation/cognitive or motor impairment'


def test_safety_shared_negation_is_not_split_into_affirmative_fragment(registry):
    raw = 'Adverse events occurred; no significant adverse consequences or dropouts due to intolerable symptoms were reported'
    row = {'domain': 'safety_tolerability', 'compound': 'Ketamine', 'safety_event_or_measure': raw, 'graph_entity_label': raw, 'kg_entity_kind_override': 'safety_adverse_event', 'result_direction': 'negative'}
    assert b.entity_expanded_rows(row, 'safety_tolerability', registry, {}) == [row]


def test_pure_validation_and_mixed_dose_association_remain_distinct():
    row = {'subjective_construct': 'Ego dissolution', 'study_design': 'Cross-sectional survey', 'finding_summary': 'The original factor structure was not reproduced; internal consistency was good.'}
    b.current_field_role_boundary(row, 'subjective_experience')
    assert row['graph_admission_status'] == 'paper_detail'
    mixed = {k:v for k,v in row.items() if not k.startswith('graph_admission') and k != 'normalization_repairs_json'}
    mixed['finding_summary'] += ' EDI scores increased with dose and subjective intensity.'
    b.current_field_role_boundary(mixed, 'subjective_experience')
    assert mixed.get('graph_admission_status') != 'paper_detail'


@pytest.mark.parametrize('focal', [
    'Side effects were present in 26% of patients and were described as generally mild and transient; no significant adverse consequences or dropouts due to intolerable symptoms were reported.',
    'Side effects were reported in 26% of patients; common events were transient dissociation (15%), nausea (6%), and dizziness (5%). The paper reports no significant adverse consequences and no dropouts due to intolerable symptoms.',
])
def test_mixed_adverse_event_paragraph_keeps_global_anchor(focal):
    assert b.safety_endpoint_label({'safety_event_or_measure': focal, 'safety_category': 'general tolerability/adverse events'}) == 'Adverse events'


def test_pure_edi_scale_structure_result_has_validation_role():
    row = {'subjective_construct': 'Ego dissolution', 'finding_summary': 'The German EDI did not reproduce the original proposed single-factor ego-dissolution scale structure. Only five of its eight items consistently represented a common ego-dissolution factor.'}
    b.current_field_role_boundary(row, 'subjective_experience')
    assert row['graph_admission_reason'] == 'measurement_validation_not_drug_effect'
