"""Current source units and Safety family identity, including attribution controls."""
import pytest
from pipeline.kg import build_evidence_tables as b

@pytest.fixture(scope='module')
def registry():
    return b.registry_lookup(b.DEFAULT_REGISTRY_PATH)

@pytest.mark.parametrize('label', sorted({label for _,label in b.SAFETY_ENDPOINT_PATTERNS}))
def test_controlled_safety_families_round_trip(label):
    assert b.safety_category_for_text(label)==label

@pytest.mark.parametrize('event,parent',[
    ('Serotonin toxicity','Serotonin syndrome'),
    ('Addiction','Abuse/dependence liability'),
    ('Withdrawal symptoms','Abuse/dependence liability'),
    ('Diplopia','Visual impairment'),
    ('Hallucinogen persisting perception disorder','Flashbacks/HPPD'),
    ('Challenging experiences','Challenging subjective effects'),
])
def test_literal_safety_endpoint_aliases(event,parent):
    assert b.safety_endpoint_label({'safety_event_or_measure':event})==parent

def test_addiction_therapy_and_study_dropout_are_not_withdrawal_symptoms():
    assert b.safety_category_for_text('Addiction treatment efficacy')==''
    assert b.safety_category_for_text('Study withdrawal due to adverse effects')=='Discontinuation due to adverse events'

@pytest.mark.parametrize('statement',[
    'In mice, 5-MeO-DMT increased theta and beta coherence, but psychedelic effects on prefrontal-hippocampal coherence remain poorly characterized.',
    'The psychedelic manifestations were associated with increased neural signal complexity.',
])
def test_unqualified_psychedelic_effects_do_not_manufacture_worsened_safety(statement):
    row={'domain':'clinical_outcome','entity_role':'outcome','graph_entity_label':'Theta and beta coherence',
         'outcome_measure':'Theta and beta coherence','finding_summary':statement,'support':statement,'result_direction':'mixed'}
    assert b.safety_endpoint_label(row)==''
    assert not b.row_reports_worsened_safety_risk(row)
    assert not b.clinical_endpoint_rows([row],[{}])

@pytest.mark.parametrize('event',['Distressing psychedelic effects','Adverse psychedelic manifestations'])
def test_explicitly_adverse_psychedelic_effects_retain_safety_path(event):
    assert b.safety_category_for_text(event)=='Challenging subjective effects'

def test_current_review_therapeutic_seizure_context_does_not_generate_adverse_projection():
    r={'domain':'clinical_outcome','entity_role':'outcome','source_item_type':'review_relationship',
       'relationship_domain_labels_json':'["clinical_outcome"]','graph_entity_label':'Earlier seizure treatment','compound':'Ketamine',
       'finding_summary':'Ketamine may offer greater effectiveness for refractory seizures with earlier treatment; this remains unproven.',
       'result_direction':'mixed'}
    assert all(x.get('entity_role')!='safety_or_adverse_event' for x in b.clinical_endpoint_rows([r],[{}]))

def test_higher_recovery_proportion_is_not_a_worsened_anxiety_event():
    r={'domain':'clinical_outcome','entity_role':'condition','source_item_type':'review_relationship','compound':'LSD',
       'relationship_domain_labels_json':'["clinical_outcome"]','graph_entity_label':'Historic anxiety reaction',
       'finding_summary':'Anxiety reaction had a higher proportion rated moderate improvement to recovery than phobic reaction.',
       'result_direction':'supports'}
    assert all(x.get('entity_role')!='safety_or_adverse_event' for x in b.clinical_endpoint_rows([r],[{}]))

def test_mixed_therapeutic_benefit_and_actual_worsening_are_not_blanket_suppressed():
    r={'domain':'clinical_outcome','entity_role':'condition','source_item_type':'review_relationship','compound':'Harmine',
       'relationship_domain_labels_json':'["clinical_outcome"]','graph_entity_label':'Parkinsonism',
       'finding_summary':'Harmine produced rapid improvement in some motor symptoms, but tremor could worsen.',
       'result_direction':'mixed'}
    assert any(x.get('entity_role')=='safety_or_adverse_event' for x in b.clinical_endpoint_rows([r],[{}]))

def test_explicit_review_safety_role_retains_actual_adverse_seizure_projection():
    r={'domain':'clinical_outcome','entity_role':'safety_or_adverse_event','source_item_type':'review_relationship',
       'relationship_domain_labels_json':'["safety_tolerability"]','safety_event_or_measure':'Seizures after exposure',
       'finding_summary':'Two patients developed seizures after exposure.','compound':'LSD'}
    assert any(x.get('graph_entity_label')=='Seizure/convulsion' for x in b.clinical_endpoint_rows([r],[{}]))

@pytest.mark.parametrize('endpoint,statement',[
    ('Ketamine-induced uropathy progressing to end-stage bladder involvement','Ketamine-induced uropathy may progress to end-stage bladder involvement; surgical patients reported greater exposure.'),
    ('Persistent neuropsychopharmacological damage','MDMA-induced neurotoxic lesions and increased damage may persist.'),
    ('Ketamine-induced cell death','Ketamine-induced cell death increases after repeated exposure.'),
    ('Psychotic symptoms','Psychedelic use was associated with higher odds of psychotic symptoms.'),
])
def test_actual_review_harm_endpoint_or_direct_worsening_survives_missing_domain_tag(endpoint,statement):
    r={'domain':'clinical_outcome','entity_role':'outcome','source_item_type':'review_relationship',
       'relationship_domain_labels_json':'["clinical_outcome"]','graph_entity_label':endpoint,
       'finding_summary':statement,'support':statement,'result_direction':'supports','compound':'Ketamine'}
    assert any(x.get('entity_role')=='safety_or_adverse_event' for x in b.clinical_endpoint_rows([r],[{}]))

def test_hypothetical_avoided_emergency_call_is_not_an_observed_adverse_event():
    r={'domain':'safety_tolerability','safety_event_or_measure':'Caller-reported possibility of calling 911 without the helpline conversation',
       'finding_summary':'Callers reported that the helpline conversation may have averted a call to emergency services.'}
    b.current_field_role_boundary(r,'safety_tolerability')
    assert r['graph_admission_reason']=='counterfactual_care_use_not_observed_event'

def test_actual_emergency_attendance_is_not_the_counterfactual_case():
    r={'domain':'safety_tolerability','safety_event_or_measure':'Emergency attendance following acute intoxication',
       'finding_summary':'Seven patients attended the emergency department after acute intoxication.'}
    b.current_field_role_boundary(r,'safety_tolerability')
    assert r.get('graph_admission_reason')!='counterfactual_care_use_not_observed_event'

def test_actual_seizure_event_survives_a_separate_counterfactual_care_clause():
    r={'domain':'safety_tolerability','safety_event_or_measure':'Observed seizures and emergency attendance',
       'finding_summary':'Two patients had seizures and attended hospital. Other callers said they may have called 911 without the helpline.'}
    b.current_field_role_boundary(r,'safety_tolerability')
    assert r.get('graph_admission_reason')!='counterfactual_care_use_not_observed_event'

def test_exposure_trend_with_explicitly_absent_clinical_outcomes_is_not_an_event():
    r={'safety_event_or_measure':'Annual rate of psychoactive mushroom exposures reported to the poison center',
       'finding_summary':'Exposure reports increased. The abstract does not report clinical effects or medical outcomes specifically for psychoactive mushroom exposures.'}
    b.current_field_role_boundary(r,'safety_tolerability')
    assert r['graph_admission_reason']=='exposure_reports_not_observed_safety_event'

def test_poisoning_series_with_actual_clinical_events_is_retained():
    r={'safety_event_or_measure':'Seizures among mushroom exposures reported to the poison center',
       'finding_summary':'Seven patients had seizures after mushroom exposures.'}
    b.current_field_role_boundary(r,'safety_tolerability')
    assert r.get('graph_admission_status')!='paper_detail'

def test_context_drug_does_not_receive_toxicity_of_another_administered_actor():
    from pipeline.kg.subject_role_guards import structured_subject_role_decision
    r={'domain':'safety_tolerability','compound_or_exposure':'Ammonium chloride (NH4Cl) administered to rats treated with phencyclidine (PCP)',
       'finding_summary':'The six-hourly NH4Cl regimen was dose-dependent in tolerability: 5.0 mEq/kg was described as highly toxic.'}
    assert structured_subject_role_decision(r)['reason']=='eligible_drug_is_context_not_measured_actor'

def test_actual_context_drug_interaction_is_not_removed_by_other_actor_guard():
    from pipeline.kg.subject_role_guards import structured_subject_role_decision
    r={'domain':'safety_tolerability','compound_or_exposure':'Ammonium chloride (NH4Cl) administered to rats treated with phencyclidine (PCP)',
       'finding_summary':'NH4Cl increased PCP elimination and reduced PCP lethality.'}
    assert structured_subject_role_decision(r) is None

def test_support_intervention_is_not_a_measured_psychedelic_class(registry):
    s='Peer-support telephone conversation during or after a psychedelic experience'
    assert b.structured_measured_class_subject(primary_class(s),s,'compound_class',registry) is None

def test_current_grouped_result_keeps_family_and_exact_source_wording():
    event='No complications developed during the session; the patient responded well to the experience.'
    r={'source_item_type':'primary_item','safety_event_or_measure':event,
       'safety_category':'general tolerability/adverse events','frequency_or_rate':'No complications in 1 patient during 1 session'}
    assert b.safety_endpoint_label(r)=='Adverse events'
    assert b.safety_specific_endpoint_label(r,'Adverse events')=='Adverse events'
    assert r['safety_event_or_measure']==event
    assert r['frequency_or_rate']=='No complications in 1 patient during 1 session'

@pytest.mark.parametrize('event',[
    'Predicted eye irritation; irritation was not experimentally assessed',
    'Preferences for low dosing; participants perceived it to be less risky',
    'MAO-A activity; potential monoamine toxicity was discussed',
    'Head-twitch response',
    'Safety concerns',
])
def test_category_does_not_promote_non_event_items(event):
    r={'source_item_type':'primary_item','safety_event_or_measure':event,'safety_category':'general tolerability/adverse events'}
    assert b.declared_safety_event_category(r)==('','')

@pytest.mark.parametrize('category',['radiation safety','hematological safety','Intracranial pressure safety'])
def test_arbitrary_safety_suffix_does_not_imply_overall_tolerability(category):
    r={'source_item_type':'primary_item','safety_event_or_measure':'A specific measurement with a numeric value',
       'safety_category':category}
    assert b.declared_safety_event_category(r)==('','')

@pytest.mark.parametrize('exposure,canonical',[
    ('Subanesthetic intravenous ketamine','Ketamine'),
    ('Sub-anaesthetic ketamine exposure','Ketamine'),
    ('Single subanesthetic ketamine infusion','Ketamine'),
    ('extended-release oral ketamine tablets','Ketamine'),
    ('Repeated intravenous racemic ketamine','Ketamine'),
    ('Intranasal esketamine monotherapy','S-ketamine'),
    ('MDMA administration in clinical settings','MDMA'),
    ('Psilocybin with psychological support','Psilocybin'),
])
def test_route_dose_formulation_is_not_an_unknown_drug(exposure,canonical,registry):
    row={'compound':exposure,'graph_subject_kind':'exposure_context'}
    match=b.graphable_subject_match(row,registry)
    assert [s['label'] for s in b.overview_graph_subjects(row,match,registry)]==[canonical]
    assert row['compound']==exposure

@pytest.mark.parametrize('exposure',[
    '3-MeO-PCP exposure','4-fluoro-ketamine infusion','Ketamine and esketamine infusion',
    'Ketamine with lithium','No ketamine exposure','Ketamine exposure questionnaire',
    'Ketamine versus placebo with psilocybin','Proposed ketamine infusion approach',
    'Recreational ingestion of tablets containing TFMPP and BZP; taken as tablets thought to be MDMA (Ecstasy)',
])
def test_complete_administration_grammar_cannot_hide_actors_or_unknown_names(exposure,registry):
    assert b.registered_administration_identity(exposure,registry)==''

def primary_class(exposure):
    return {'compound':exposure,'compound_or_exposure':exposure,'graph_subject_kind':'compound_class',
            'source_item_type':'primary_item','source_type':'primary','domain':'safety_tolerability'}

@pytest.mark.parametrize('exposure',[
    'Lifetime naturalistic psychedelic use',
    'Psychedelic use (LSD or psilocybin)',
    'Psychedelics (unspecified compounds)',
    'Psychedelic use during a two-month study period',
])
def test_measured_primary_class_is_one_valid_unit_without_member_drug_effects(exposure,registry):
    r=primary_class(exposure)
    s=b.overview_graph_subjects(r,b.graphable_subject_match(r,registry),registry)
    assert [(x['label'],x['kind']) for x in s]==[(b.BROAD_PSYCHEDELIC_CLASS_LABEL,'compound_class')]

@pytest.mark.parametrize('exposure',[
    'No psychedelic administration; survey elicited attitudes toward psychedelic use',
    'Psychedelic exposure defined as heroin',
    'Psychedelic use with cannabis',
    'Psychiatric medication and psychedelic used on the same day',
    'Recommendations for combining psychedelics with other substances',
])
def test_absent_conflicting_and_joint_exposures_do_not_get_a_pure_class_projection(exposure,registry):
    assert b.structured_measured_class_subject(primary_class(exposure),exposure,'compound_class',registry) is None

def test_statistical_pool_and_comparison_are_not_split_by_class_repair(registry):
    for scope,label in [('pooled_multiple_interventions','Ketamine or esketamine'),
                        ('comparison_between_interventions','Psychedelics')]:
        r={**primary_class(label),'source_type':'meta_analysis','meta_analysis_subject_scope':scope}
        assert b.overview_graph_subjects(r,b.graphable_subject_match(r,registry),registry)==[]

def test_measured_psychotomimetic_anchor_does_not_require_summary_keyword_repetition():
    r={'graph_entity_label':'Psychotomimetic effects','finding_summary':
       'Among participants reporting psychedelic use, higher baseline self-compassion was associated with less severe challenging experiences.'}
    out,domain=b.apply_psychosis_family_boundary(r,'cognitive_behavioral')
    assert domain=='cognitive_behavioral'
    assert out['graph_entity_label']=='Psychotomimetic effects'
    assert out.get('safety_event_or_measure')!='Psychosis risk'

def test_actual_psychotic_episode_is_not_downgraded_by_model_anchor():
    r={'graph_entity_label':'Psychotomimetic effects','finding_summary':
       'The patient developed a psychotic episode requiring hospitalization after drug administration.'}
    out,domain=b.apply_psychosis_family_boundary(r,'cognitive_behavioral')
    assert domain=='safety_tolerability'
    assert out['graph_entity_label']=='Psychosis risk'

def test_serious_persistent_symptoms_do_not_require_the_word_psychosis():
    r={'graph_entity_label':'Psychotomimetic effects','finding_summary':
       'Persistent delusions and hallucinations required inpatient treatment after administration.'}
    out,domain=b.apply_psychosis_family_boundary(r,'cognitive_behavioral')
    assert domain=='safety_tolerability'
    assert out['graph_entity_label']=='Psychosis risk'

def test_negated_persistence_does_not_make_an_acute_model_a_clinical_episode():
    r={'graph_entity_label':'Psychotomimetic effects','finding_summary':
       'Transient perceptual effects were reported, without persistent hallucinations.'}
    _,domain=b.apply_psychosis_family_boundary(r,'cognitive_behavioral')
    assert domain=='cognitive_behavioral'

@pytest.mark.parametrize('statement',[
    'The hallucinations took six weeks to completely recede.',
    'Recurrent flashbacks were reported after exposure.',
])
def test_explicit_postacute_harms_stay_in_safety(statement):
    out,domain=b.apply_psychosis_family_boundary({'graph_entity_label':'Psychotomimetic effects','finding_summary':statement},'cognitive_behavioral')
    assert domain=='safety_tolerability'
