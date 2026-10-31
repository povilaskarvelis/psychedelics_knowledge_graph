"""Positive and negative role controls from the larger saved-extraction audit."""
import json
import pandas as pd
import pytest
from pipeline.kg import build_evidence_tables as b

@pytest.fixture(scope='module')
def registry(): return b.registry_lookup(b.DEFAULT_REGISTRY_PATH)


def test_compound_alias_inside_binding_site_does_not_define_target(registry):
    assert b.canonicalize_registry_label('mechanistic_entity', 'anti-PCP mAb (KD = 1.3 nM)', registry)[1] is None
    # Historical PCP sites are heterogeneous; an explicit receptor is required.
    assert b.canonicalize_registry_label('mechanistic_entity', 'phencyclidine (PCP) binding sites', registry)[1] is None
    site = b.match_registry_entity('phencyclidine (PCP) binding sites', 'target', registry)
    assert site['match_type'] == 'historical_target_site_detail_only'


def test_unicode_receptor_and_distinct_fly_identity(registry):
    assert b.receptor_identity_label('5-HT₂A') == '5-HT2A'
    for label in ['2C-B-Fly', 'DOB-DragonFLY']:
        row={'compound':label,'graph_subject_kind':'atomic_compound'}
        match=b.graphable_subject_match(row,registry)
        assert b.overview_graph_subjects(row,match,registry)==[]
    row={'compound':'2C-B','graph_subject_kind':'atomic_compound'}
    assert b.overview_graph_subjects(row,b.graphable_subject_match(row,registry),registry)[0]['label']=='2C-B'


def test_statistical_class_does_not_select_first_drug(registry):
    for label,scope in [('Ketamine and psilocybin','pooled_multiple_interventions'),('Placebo','control_arm'),('Ketamine versus psilocybin','comparison_between_interventions')]:
        row={'compound':label,'graph_subject_kind':'atomic_compound','meta_analysis_subject_scope':scope}
        match=b.graphable_subject_match(row,registry)
        assert match['label']==label
        assert b.overview_graph_subjects(row,match,registry)==[]
    assert b.explicit_overview_compound_class_subject('MDMA and classic hallucinogens',registry) is None
    assert b.explicit_overview_compound_class_subject('Classic psychedelics (psilocybin, LSD)',registry)['label']=='Classic psychedelics'


def test_meta_regression_uses_dependent_memory_not_exposure_predictor():
    row={'source_type':'meta_analysis','primary_outcome':'Effect sizes for spatial-element recall or recognition task performance','outcome_measure':'Meta-regression coefficient for the linear relationship between consumption and effect size'}
    assert b.cognitive_behavioral_graph_label(row)=='Spatial memory'
    row['primary_outcome']='Drug self-administration'
    assert b.cognitive_behavioral_graph_label(row)=='Drug self-administration'


@pytest.mark.parametrize('separator', [' ', '-', '\u2010', '\u2011', '\u2013', '\u2014'])
def test_verbal_learning_orthography_preserves_dependent_construct(separator):
    row = {'source_type': 'meta_analysis',
           'primary_outcome': f'Long-delayed verbal{separator}learning recall',
           'outcome_measure': 'Verbal Learning Task long delayed recall'}
    assert b.cognitive_behavioral_graph_label(row) == 'Verbal memory'


def test_incidental_verbal_learning_does_not_replace_measured_visual_memory():
    row = {'source_type': 'meta_analysis', 'primary_outcome': 'Visual memory',
           'outcome_measure': 'Visual recall; verbal-learning task used as covariate'}
    assert b.cognitive_behavioral_graph_label(row) == 'Visual memory'


@pytest.mark.parametrize('endpoint', ['Non-verbal-learning recall', 'Non-verbal memory', 'Non verbal learning'])
def test_nonverbal_construct_does_not_become_verbal_memory(endpoint):
    assert b.cognitive_behavioral_graph_label({'source_type': 'meta_analysis', 'primary_outcome': endpoint}) != 'Verbal memory'


def test_global_cognition_is_not_inferred_executive_function():
    assert b.cognitive_behavioral_graph_label({'source_type':'meta_analysis','primary_outcome':'Postoperative cognitive function measured using MMSE or other reported cognitive scales'})=='Global cognition'
    assert b.cognitive_behavioral_graph_label({'graph_entity_label':'cognitive function'})!='Executive function'
    assert b.cognitive_behavioral_graph_label({'graph_entity_label':'Executive function'})=='Executive function'


def test_explicit_sae_exclusion_differs_from_null_sae():
    assert b.safety_category_for_text('Other adverse events, excluding serious adverse events')=='Adverse events'
    assert b.safety_category_for_text('No serious adverse events')=='Serious adverse events'


def test_self_reported_sociability_retains_experiential_construct():
    assert b.subjective_experience_graph_label({'graph_entity_label':'Self-reported sociability-related outcomes, including feeling loving, talkative, friendly, sociable, and extraverted'})=='Connectedness'

@pytest.mark.parametrize('population,domain,anchor,measure,expected,label',[
 ('Human ecstasy users','cognitive_behavioral','Self-rated anxiety','self-rated anxiety','subjective_experience','Negative affect'),
 ('Rats','cognitive_behavioral','Anxiety-like behavior','Elevated plus maze','cognitive_behavioral',None),
 ('Rats','subjective_experience','Drug discrimination','drug-appropriate lever responding','cognitive_behavioral','Drug discrimination'),
 ('Healthy adults','subjective_experience','Subjective intensity','VAS intensity','subjective_experience',None),
 ('Patients with alcohol use disorder','subjective_experience','Craving severity','craving scale','cognitive_behavioral','Craving'),
])
def test_explicit_measurement_roles(population,domain,anchor,measure,expected,label):
    row={'population':population,'graph_entity_label':anchor,'outcome_measure':measure}
    assert b.measured_construct_role_boundary(row,domain)==expected
    if label: assert row['graph_entity_label']==label


def test_pooled_conditions_do_not_duplicate_estimate(registry):
    row={'source_type':'meta_analysis','compound':'Ketamine','domain':'clinical_outcome','kg_entity_kind_override':'condition_indication','graph_entity_label':'Patients with alcohol use disorder, cocaine use disorder and major depressive disorder','primary_outcome':'Total symptom score'}
    rows=b.condition_expanded_rows(row,'clinical_outcome',registry)
    assert len(rows)==1
    assert rows[0]['graph_admission_reason']=='pooled_conditions_not_indication_specific'
    row['primary_outcome']='Depression severity in major depressive disorder'
    rows=b.condition_expanded_rows(row,'clinical_outcome',registry)
    assert len(rows)==1
    assert rows[0]['graph_entity_label']=='Major depressive disorder'


def test_explicit_brain_subregions_preserve_specific_location():
    vocabulary=b.node_vocabulary_lookup()
    both=b.brain_entity_split_matches('Nucleus accumbens core and shell',vocabulary)
    assert {x[1] for x in both}=={'Nucleus accumbens core','Nucleus accumbens shell'}
    child=b.brain_entity_split_matches('Prelimbic subregion of medial prefrontal cortex',vocabulary)
    assert child and 'Prelimbic' in child[0][1]
    assert b.brain_measure_graph_label('EEG beta bandpower')=='Oscillatory power'


def test_leading_safety_endpoint_wins_over_context_signs():
    row={'safety_event_or_measure':'Two episodes of apnea during consecutive infusions; transient tachycardia resolved', 'safety_category':'Respiratory safety'}
    parent=b.safety_endpoint_label(row)
    assert parent=='Respiratory safety'
    assert b.safety_specific_endpoint_label(row,parent)=='Respiratory safety'
    assert b.safety_category_for_text('Fatality in an MDMA-related case')=='Serious adverse events'
    assert b.safety_category_for_text('Micronucleus frequency and chromosomal aberrations')=='Neurotoxicity/cytotoxicity'


def test_combined_receptor_response_does_not_select_a_subtype(registry):
    m=b.graphable_entity_match({},'molecular_target','target','5-HT1B/1D receptor-mediated response',registry,b.node_vocabulary_lookup())
    assert m['kind']=='reported_measurement'
    assert m['label']=='5-HT1B/1D receptor-mediated response'


def test_explicit_attribution_limits_and_parallel_positive():
    from pipeline.kg.subject_role_guards import structured_subject_role_decision
    row={'domain':'brain_system','compound_or_exposure':'Before esketamine initiation', 'finding_summary':'At baseline, lower brain volumes were a disease-associated comparison, not an esketamine treatment effect.'}
    assert structured_subject_role_decision(row)['reason']=='baseline_disease_comparison_not_drug_effect'
    row['finding_summary']='After treatment, volumes changed from baseline.'
    assert structured_subject_role_decision(row) is None
    row={'domain':'molecular_target','compound':'TCB-2, DOI, DOB (abstract does not identify which compounds show the effect)','finding_summary':'Some drugs had different activity.'}
    assert structured_subject_role_decision(row)['action']=='paper_detail'
    row={'domain':'brain_system','compound_or_exposure':'Ketamine, phencyclidine, quipazine and SKF-10 047','finding_summary':'All four compounds produced spike-and-wave complexes.'}
    assert structured_subject_role_decision(row)['action']=='parallel_subjects'

@pytest.mark.parametrize('outcome,expected', [
 ('Updating, a working-memory executive subcomponent','Working memory'),
 ('Attention shifting, a working-memory executive subcomponent','Attention'),
 ('Inhibition, a working-memory executive subcomponent','Inhibitory control'),
 ('Working memory','Working memory'),
 ('Memory and attention','Memory'),
])
def test_meta_explicit_subcomponent_precedes_taxonomic_description(outcome,expected):
    assert b.cognitive_behavioral_graph_label({'source_type':'meta_analysis','primary_outcome':outcome})==expected


def test_secondary_imaging_peak_preserves_explicit_multiplicity_qualification():
    row={'domain':'brain_system','kg_entity_kind_override':'brain_region','meta_analysis_result_role':'secondary_synthesis',
         'meta_analysis_analysis_type':'Functional neuroimaging meta-analysis',
         'meta_analysis_multiplicity_adjustment':'Uncorrected results'}
    assert b.graph_admission_decision(row)==('paper_detail','secondary_uncorrected_neuroimaging_result')
    for updates in [ {'meta_analysis_multiplicity_adjustment':'Stringent statistical threshold (TFCE <0.05)'},
                     {'meta_analysis_multiplicity_adjustment':''},
                     {'meta_analysis_result_role':'primary_synthesis'},
                     {'domain':'clinical_outcome'},
                     {'meta_analysis_analysis_type':'Pairwise meta-analysis'} ]:
        assert b.graph_admission_decision({**row,**updates})[0]=='main_graph'


def test_ptsd_symptom_score_is_not_a_diagnosis_or_background_condition():
    assert b.symptom_endpoint_label({'raw_entity_label':'Posttraumatic stress symptoms','outcome_measure':'PCL-5 score'})=='Post-traumatic stress symptoms'
    assert b.symptom_endpoint_label({'raw_entity_label':'Cortisol concentration','finding_summary':'The sample had elevated PTSD symptoms at baseline.'})!='Post-traumatic stress symptoms'
    assert b.symptom_endpoint_label({'raw_entity_label':'Post-traumatic stress disorder'})!='Post-traumatic stress symptoms'


def test_explicit_measured_endpoint_repairs_survive_actual_builder_sequence(registry):
    from pathlib import Path
    rows=json.loads((Path(__file__).parent/'fixtures/measured_endpoint_source_cases.json').read_text())
    vocabulary=b.node_vocabulary_lookup()
    expected={42:('brain_system',{'Early visual areas','Fusiform gyrus','Inferior frontal gyrus','Intraparietal sulcus'}),
              57:('real_world_public_health',None),74:('real_world_public_health',{'Health & functioning outcomes'}),
              157:('clinical_outcome',{'Post-traumatic stress symptoms'}),240:('pharmacokinetics_exposure',{'Concentration'})}
    for case in rows:
        source=case['row'];out=b.normalize_claim_metadata(source,source['domain']);labels=set()
        for expanded in b.entity_expanded_rows(out,out['domain'],registry,vocabulary):
            final=b.normalize_claim_metadata(expanded,expanded['domain'])
            kind=b.entity_kind_for(final,final['domain']);label=b.entity_label_for(final,final['domain'],kind)
            matched=b.graphable_entity_match(final,final['domain'],kind,label,registry,vocabulary)
            assert matched['matched'],(case['audit_index'],label)
            assert final['domain']==expected[case['audit_index']][0]
            labels.add(matched['label'])
            assert final['finding_summary']==source['finding_summary']
            if case['audit_index']==240:assert b.graph_admission_decision(final)[0]=='paper_detail'
            if case['audit_index']==157:assert kind=='symptom_problem'
        if expected[case['audit_index']][1] is not None:assert labels==expected[case['audit_index']][1]
