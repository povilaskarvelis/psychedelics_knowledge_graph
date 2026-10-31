import copy
import json
from pathlib import Path

import pytest

from pipeline.kg.measured_endpoint_repairs import apply_measured_endpoint_repairs

FIXTURES = json.loads((Path(__file__).parent / 'fixtures/measured_endpoint_source_cases.json').read_text())


def source(index, domain, item=1):
    return copy.deepcopy(next(x['row'] for x in FIXTURES if x['audit_index'] == index and x['row']['domain'] == domain and x['row']['source_item_index'] == item))


def apply(row):
    return apply_measured_endpoint_repairs(row, row['domain'])


def test_saved_self_connection_proposes_only_explicit_region_fallback():
    row = source(42, 'brain_system')
    out, domain = apply(row)
    assert domain == 'brain_system'
    assert out['graph_entity_label'] == row['graph_entity_label']
    assert json.loads(out['measured_endpoint_brain_region_candidates_json']) == row['brain_region'].split('; ')
    assert out['measured_endpoint_brain_fallback_only']
    assert out['readout'] == row['readout']
    assert out['finding_summary'] == row['finding_summary']
    assert 'measured_endpoint_repair_version' not in row


@pytest.mark.parametrize('circuit', ['Directed effective connectivity from IFG to FG', 'Prefrontal-amygdala connectivity', 'Increased activation in all visual regions'])
def test_connectivity_or_activation_does_not_become_local_region_results(circuit):
    row = source(42, 'brain_system'); row['neural_circuit'] = circuit
    assert apply(row)[0] == row


def test_acronym_only_region_field_does_not_invent_definitions():
    row = source(42, 'brain_system'); row['brain_region'] = 'EVA; FG; IFG; IPS'
    assert apply(row)[0] == row


@pytest.mark.parametrize('item,topic', [(1,'Implementation & acceptability'), (2,'Perceived benefits & harms')])
def test_provider_vignette_results_are_perceptions_not_patient_effects(item, topic):
    row = source(57, 'intervention_context', item)
    out, domain = apply(row)
    assert domain == 'real_world_public_health'
    assert out['public_health_graph_label'] == topic
    assert out['compound'] == row['compound']
    assert out['effect_or_statistic'] == row['effect_or_statistic']
    assert out['measured_endpoint_observation_kind'] == 'provider_perception_not_patient_drug_effect'
    assert apply(out) == (out, domain)


@pytest.mark.parametrize('change', [{'population_or_setting':'Patients receiving MDMA therapy', 'population':'Patients receiving MDMA therapy'}, {'study_design':'Randomized clinical trial', 'delivery_format':'Clinical sessions'}, {'context_component':'Preparation and psychological support', 'component_type':'session support'}])
def test_patient_acceptability_or_session_context_is_not_provider_attitudes(change):
    row = source(57, 'intervention_context'); row.update(change)
    assert apply(row)[0] == row


def test_descriptive_hallucinogen_cases_keep_broad_class_and_denominator():
    row = source(74, 'clinical_outcome')
    out, domain = apply(row)
    assert domain == 'real_world_public_health'
    assert out['graph_entity_label'] == 'Health & functioning outcomes'
    assert out['compound'] == row['compound']
    assert out['sample_size'] == row['sample_size']
    assert out['finding_summary'] == row['finding_summary']


@pytest.mark.parametrize('change', [{'study_design':'Randomized intervention trial'}, {'comparator':'Ketamine treatment'}, {'clinical_endpoint':'Treatment response'}, {'condition_or_indication':'Substance use disorder'}])
def test_case_count_rule_does_not_recast_treatment_or_other_diagnoses(change):
    row = source(74,'clinical_outcome');row.update(change)
    assert apply(row)[0] == row


def test_ptsd_total_symptom_score_is_not_diagnosis_or_single_subscale():
    row = source(157,'clinical_outcome')
    out, domain = apply(row)
    assert domain == 'clinical_outcome'
    assert out['kg_entity_kind_override'] == 'symptom_problem'
    assert out['endpoint_label_source'] == 'clinical_symptom_endpoint'
    assert out['graph_entity_label'] == 'Post-traumatic stress symptoms'
    assert out['condition_or_indication'] == row['condition_or_indication']
    assert out['finding_summary'] == row['finding_summary']


@pytest.mark.parametrize('change', [{'condition_or_indication':'PTSD'}, {'clinical_endpoint':'Blood cortisol', 'outcome_measure':'Cortisol'}, {'condition_or_indication':'Complex posttraumatic stress symptoms (self-organization)'}])
def test_ptsd_eligibility_stress_and_complex_subscale_are_not_total_symptom_score(change):
    row = source(157,'clinical_outcome');row.update(change)
    assert apply(row)[0] == row


@pytest.mark.parametrize('domain,item', [('molecular_pathway_readout',9), ('molecular_pathway_readout',10), ('pharmacokinetics_exposure',1), ('pharmacokinetics_exposure',2)])
def test_observed_combined_concentration_preserves_aggregate_and_source(domain,item):
    row=source(240,domain,item);out,new_domain=apply(row)
    assert new_domain=='pharmacokinetics_exposure'
    assert out['graph_entity_label']=='Concentration'
    assert out['kg_entity_kind_override']=='pharmacokinetic_parameter'
    assert out['pk_relationship_type']=='exposure_characterized'
    assert out['measured_endpoint_aggregate_analytes']
    assert out['graph_admission_status'] == 'paper_detail'
    assert out['graph_admission_reason'] == 'combined_analyte_concentration_not_single_drug'
    assert out['compound']==row['compound']
    assert out['finding_summary']==row['finding_summary']
    assert out['effect_or_statistic']==row['effect_or_statistic']


@pytest.mark.parametrize('marker', ['Extracellular serotonin concentration', 'GABA and glutamate concentrations after ketamine', 'Ketamine receptor concentration-response EC50', 'Ketamine CYP2B6 genotype concentrations', 'Ketamine storage stability concentrations', 'Endogenous DMT brain concentration', 'Spiked ketamine plasma concentration', 'Predicted ketamine plasma concentration'])
def test_non_pk_markers_and_synthetic_exposure_are_not_rerouted(marker):
    row=source(240,'molecular_pathway_readout',9);row['specific_readout_or_marker']=marker
    assert apply(row)[0]==row


def test_in_vitro_measured_drug_does_not_satisfy_in_vivo_rule():
    row=source(240,'molecular_pathway_readout',9);row['population_or_system']='Human liver microsomes, in vitro';row['population']='Human liver microsomes, in vitro'
    assert apply(row)[0]==row


def test_review_or_meta_result_not_repaired_by_primary_rules():
    row=source(157,'clinical_outcome');row.update(source_item_type='synthesis_result', paper_type='meta_analysis')
    assert apply(row)[0]==row


def test_specific_avoidance_subscale_does_not_become_generic_total_ptsd_score():
    row=source(157,'clinical_outcome')
    row.update(clinical_endpoint='Association between avoidance symptoms and hallucinogen use', outcome_measure='PTSD symptom cluster of avoidance')
    assert apply(row)[0]==row


@pytest.mark.parametrize('relationship,label,parameter', [
    ('exposure_linked_to_effect','Exposure-response relationship','Ketamine concentration and effect'),
    ('distributed_to','Tissue distribution','Brain concentration'),
    ('metabolized_to','Norketamine','Norketamine plasma concentration'),
    ('exposure_characterized','Cmax','Maximum concentration; Cmax'),
])
def test_existing_nonaggregate_pk_semantics_are_preserved(relationship,label,parameter):
    row=source(240,'pharmacokinetics_exposure',2)
    row.update(pk_relationship_type=relationship, graph_entity_label=label, pk_or_exposure_parameter=parameter)
    assert apply(row)[0]==row


@pytest.mark.parametrize('marker', ['Ketamine plasma concentration; half-life', 'MDMA/MDA concentration ratio', '5-HT axonal markers; plasma MDMA concentrations'])
def test_mixed_pk_and_pathway_measurements_remain_for_separate_review(marker):
    row=source(240,'molecular_pathway_readout',9);row['specific_readout_or_marker']=marker
    assert apply(row)[0]==row
