"""Postvalidation repair probes: these are deliberately separate from holdout validation."""
import pytest
from pipeline.kg import build_evidence_tables as b
from pipeline.kg import convert_routed_extractions_to_evidence_rows as c
from pipeline.extract.clinical_comparator import normalize_clinical_comparator
from pipeline.extract.clinical_followup_window import normalize_clinical_followup_window

@pytest.fixture(scope='module')
def registry():return b.registry_lookup(b.DEFAULT_REGISTRY_PATH)

@pytest.mark.parametrize('label,expected',[
 ('Ketamine, an NMDA receptor antagonist','Ketamine'),
 ('Ketamine (NMDA receptor antagonist)','Ketamine'),
 ('Repeated exposure to the serotonergic psychedelic 25C-NBOMe during adolescence','25C-NBOMe'),
 ('2C-E (2,5-dimethoxy-4-ethylphenethylamine)','2C-E'),
 ('MDMA (75 mg and 125 mg)','MDMA'),
 ('Psilocybin (1 mg/kg, i.p.), compared with saline','Psilocybin'),
])
def test_specific_name_survives_descriptor(label,expected,registry):
 row={'compound':label};c.apply_graph_subject(row);m=b.graphable_subject_match(row,registry)
 if expected:assert m['subject_kind']=='atomic_compound' and m['label']==expected
 assert [x['label']for x in b.overview_graph_subjects(row,m,registry)]==[expected or 'MDMA']

@pytest.mark.parametrize('label', ['Classic psychedelics (LSD, psilocybin)', 'Ketamine and MDMA','Ketamine plus an unknown drug'])
def test_mixed_or_pooled_subject_not_forced_atomic(label,registry):
 row={'compound':label};c.apply_graph_subject(row);m=b.graphable_subject_match(row,registry)
 assert m.get('subject_kind')!='atomic_compound'

@pytest.mark.parametrize('label',['BAB (1-benzyl-2,5-dimethylbufotenin)','1-benzyl-2,5-dimethylbufotenin','Benzyl analog of bufotenin'])
def test_novel_substitution_cannot_inherit_bufotenin(label,registry):
 row={'compound':label};c.apply_graph_subject(row);m=b.graphable_subject_match(row,registry)
 assert m['matched'] and b.overview_graph_subjects(row,m,registry)==[]
 assert m['label']==label

@pytest.mark.parametrize('category,text,expected',[
 ('clinical_trial','Randomized double-blind placebo-controlled trial','randomized_controlled_trial'),
 ('dose_finding','Ascending single-dose randomized parallel-group Phase I study','randomized_controlled_trial'),
 ('clinical_trial','Double-blind placebo-controlled study','other'),
 ('open_label','Open-label clinical trial','other'),
 ('clinical_trial','Non-randomized clinical trial','nonrandomized_clinical_trial'),
 ('clinical_trial','Open-label phase of a randomized controlled trial','nonrandomized_clinical_trial'),
])
def test_generic_design_does_not_assert_allocation(category,text,expected):
 assert c.evidence_design_for({'study_design_category':category,'study_design':text,'population_model_category':'human_participants'})==expected

def test_randomized_animal_remains_preclinical():
 assert c.evidence_design_for({'study_design_category':'clinical_trial','study_design':'Randomized groups','population_model_category':'rat_model'})=='preclinical'

@pytest.mark.parametrize('value,expected',[
 ('Baseline and 230 minutes after treatment','Acute / same day'),
 ('Baseline and 9 months after treatment','Long follow-up (4-12 months)'),
 ('30 minutes before infusion (baseline)','Baseline / pre-treatment'),
 ('Baseline','Baseline / pre-treatment'),
 ('Response described as rapid and sustained; exact clinical outcome assessment times not reported','Follow-up not reported'),
 ('At 2 hours after dosing','Acute / same day'),
])
def test_followup_not_erased_by_baseline(value,expected):assert normalize_clinical_followup_window('',value)==expected

@pytest.mark.parametrize('value,expected',[
 ('Normal saline infusion group; cognitive finding described as not impairing function after a single low dose','Placebo'),
 ('Escitalopram arm: 2 × 1 mg oral psilocybin, 3 weeks apart, plus 6 weeks of daily escitalopram (10–20 mg)','Active treatment'),
 ('Midazolam active placebo','Active placebo'),('1 mg psilocybin','Active placebo'),
 ('Scores immediately after the final ketamine infusion','Other'),
 ('Within-participant scores before treatment','Baseline'),
])
def test_comparator_anchor_precedes_incidental_dose(value,expected):assert normalize_clinical_comparator(value)==expected

@pytest.mark.parametrize('marker,expected', [('IL-10','Anti-inflammatory cytokines'),('interleukin-10','Anti-inflammatory cytokines'),('IL-1beta','IL-1 signaling'),('IL-6','IL-6 & related cytokines'),('IL-17A','Cytokines & chemokines')])
def test_cytokine_numeric_boundaries(marker,expected):
 assert b.molecular_subtopic_match('Neuroinflammation & immune signaling',marker,allow_residual=True)==expected

@pytest.mark.parametrize('text',['Diarrhea','Gastrointestinal discomfort','Constipation'])
def test_gi_event_does_not_invent_nausea(text):assert b.safety_category_for_text(text)!='Nausea/vomiting'
def test_nausea_still_matches():assert b.safety_category_for_text('Nausea and vomiting')=='Nausea/vomiting'

def test_plain_use_does_not_invent_disorder(registry):
 m=b.match_registry_entity('Methamphetamine use','condition_indication',registry)
 assert m['label']=='Methamphetamine use' and m['match_type'].endswith('detail_only')
 assert b.match_registry_entity('Methamphetamine use disorder','condition_indication',registry)['label']=='Methamphetamine use disorder'

def test_numbered_source_local_compound_requires_chemical_evidence(registry):
 row={'compound':'10','domain':'molecular_target','finding_summary':'Compound 10 bound 5-HT2B.'};c.apply_graph_subject(row)
 m=b.graphable_subject_match(row,registry);assert m['matched'] and b.overview_graph_subjects(row,m,registry)==[]
 row={'compound':'10','domain':'clinical_outcome','finding_summary':'Ten participants improved.'};c.apply_graph_subject(row)
 assert not b.graphable_subject_match(row,registry)['matched']

def test_rescue_agent_sequence_is_package(registry):
 row=b.normalize_claim_metadata({'compound':'Ketamine','compound_or_exposure':'Risperidone or Salix mucronata treatment following ketamine induction','specific_readout_or_marker':'Dopamine concentration'},'molecular_pathway_readout')
 assert b.graph_admission_decision(row)[0]=='paper_detail'
 assert b.overview_graph_subjects(row,b.graphable_subject_match(row,registry),registry)==[]

def test_pk_method_validation_and_observed_detection_have_distinct_roles():
 raw={'compound':'LSD','pk_or_exposure_parameter':'Limit of detection','finding_summary':'Analytical method validation in spiked urine samples.'}
 assert b.graph_admission_decision(b.normalize_claim_metadata(raw,'pharmacokinetics_exposure'))[0]=='paper_detail'
 observed={**raw,'pk_or_exposure_parameter':'Detection','finding_summary':'LSD was detected in samples from 20 drivers.'}
 assert b.graph_admission_decision(b.normalize_claim_metadata(observed,'pharmacokinetics_exposure'))[0]=='main_graph'
 stability={'compound':'Psilocin','pk_graph_object_label':'analytical-process stability','finding_summary':'The extraction process lost 6–9% of signal.'}
 assert b.graph_admission_decision(b.normalize_claim_metadata(stability,'pharmacokinetics_exposure'))[0]=='paper_detail'

def test_validation_label_does_not_hide_actual_dose_association():
 row={'compound':'Psilocybin','subjective_construct':'Ego dissolution','study_design':'Psychometric validation','finding_summary':'Factor analysis identified a coherent scale.','relationship_to_outcome':'Ego dissolution correlated with estimated dose.'}
 assert b.graph_admission_decision(b.normalize_claim_metadata(row,'subjective_experience'))[0]=='main_graph'
 pure={**row,'relationship_to_outcome':'Internal consistency was high.'}
 assert b.graph_admission_decision(b.normalize_claim_metadata(pure,'subjective_experience'))[0]=='paper_detail'

def test_natural_reward_not_drug_administration():
 assert b.cognitive_behavioral_graph_label({'behavioral_construct':'Anhedonia','task_or_measure':'Two-bottle choice sucrose preference: sucrose versus water'})=='Anhedonia'
 assert b.cognitive_behavioral_graph_label({'task_or_measure':'Two-bottle choice ethanol consumption'})=='Drug self-administration'

def test_bol_parent_description_not_independent_lsd(registry):
 label='BOL (brom derivative of d-lysergic acid diethylamide), quick injection'
 row={'compound':label};c.apply_graph_subject(row);m=b.graphable_subject_match(row,registry)
 assert [x['label']for x in b.overview_graph_subjects(row,m,registry)]==['2-bromo-LSD']
 row={'compound':'BOL and LSD'};c.apply_graph_subject(row);m=b.graphable_subject_match(row,registry)
 assert {x['label']for x in b.overview_graph_subjects(row,m,registry)}=={'2-bromo-LSD','LSD'}

def test_salvinorin_acid_not_parent(registry):
 assert b.graphable_compound_match('Salvinorin A acid',registry)['match_type']=='unregistered_chemical_identity_detail_only'
 assert b.graphable_compound_match('Salvinorin A',registry)['label']=='Salvinorin A'

def test_sequential_samples_are_not_sequential_treatment():
 assert b.explicit_combination_projection({},'Possible magic mushroom exposure; psilocin detected in three sequential 1-cm hair segments',['Psilocybin','Psilocin']) is None
 actual=b.explicit_combination_projection({},'MDMA followed by psilocybin',['MDMA','Psilocybin'])
 assert actual['kind']=='treatment_regimen'
 assert b.explicit_combination_projection({'study_title':'Consecutive hair segments'},'LSD and psilocin detected',['LSD','Psilocin']) is None

def test_qualitative_risk_not_observed_event():
 concern={'compound':'Psilocybin','study_design':'Qualitative expert interviews','safety_event_or_measure':'Concern about adverse effects such as delirium','finding_summary':'Participants expressed concerns; no adverse events in treated patients were assessed or reported.'}
 assert b.graph_admission_decision(b.normalize_claim_metadata(concern,'safety_tolerability'))[0]=='paper_detail'
 observed={**concern,'study_design':'Clinical trial','safety_event_or_measure':'Delirium','finding_summary':'The patient experienced delirium; clinicians expressed concern about adverse effects.'}
 assert b.graph_admission_decision(b.normalize_claim_metadata(observed,'safety_tolerability'))[0]=='main_graph'

def test_unregistered_product_description_not_class_recovered_atom(registry):
 raw='A distributed blotter product claimed to contain 1D-LSD; chemical analysis identified 1T-LSD instead, together with tryptamine and L-tryptophan methyl ester.'
 row={'compound':raw};c.apply_graph_subject(row);m=b.graphable_subject_match(row,registry)
 assert b.overview_graph_subjects(row,m,registry)==[]
 raw='Hallucinogens (LSD and Oxo-LSD)'
 row={'compound':raw};c.apply_graph_subject(row);m=b.graphable_subject_match(row,registry)
 assert [x['label']for x in b.overview_graph_subjects(row,m,registry)]==['Hallucinogens']

def test_nonchemical_intervention_detail_survives_parenthetical_list(registry):
 row={'compound':'Harm reduction intervention (outreach, counseling, risk-reduction planning)'}
 c.apply_graph_subject(row);m=b.graphable_subject_match(row,registry)
 assert m['matched']
 assert b.overview_graph_subjects(row,m,registry)==[]

@pytest.mark.parametrize('construct',['Hyperactivity','Locomotor hyperactivity'])
def test_explicit_locomotor_construct_preserves_detail_category(construct):
 row={'graph_construct_label':construct,'task_or_measure':'Automated home-cage locomotor activity score','raw_task_or_measure':'Home-cage activity scores recorded during the first hour'}
 assert b.cognitive_behavioral_graph_label(row)=='Locomotor activity'
 assert 'locomotor activity' in b.GENERIC_BEHAVIOR_NOT_GRAPHABLE_KEYS
