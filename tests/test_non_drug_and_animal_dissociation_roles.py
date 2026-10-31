"""Non-drug states and animal behavior must not become human drug experience."""
import copy
import pytest
from pipeline.kg import build_evidence_tables as b


def source(domain, exposure, population, summary, **fields):
    return dict(domain=domain, domain_route=domain, dataset=domain,
                source_type='primary', paper_type='primary_study',
                paper_assessment_route='primary_evidence',
                compound=exposure, compound_or_exposure=exposure,
                population=population, population_or_system=population,
                finding_summary=summary, support=summary, **fields)


@pytest.mark.parametrize('exposure,summary,dose',[
    ('Spontaneous pre-seizure dissociative aura',
     'During spontaneous aura a cortical rhythm appeared.', ''),
    ('Rhythmic optogenetic activation of RSP neurons, without ketamine',
     'The rhythm reproduced components of dissociation-like behavior.', ''),
    ('Rhythmic optogenetic activation of RSP neurons',
     'In the absence of ketamine, stimulation reduced paw licking.', ''),
    ('Brief electrical stimulation of posteromedial cortex',
     'The patient reported dissociation after stimulation.', 'No psychedelic compound administered.'),
])
def test_explicit_non_drug_actor_has_no_drug_class_projection(exposure, summary, dose):
    row=source('brain_system',exposure,'One patient with epilepsy',summary,
               dose_or_regimen=dose,brain_region='Posterior cingulate cortex')
    original=copy.deepcopy(row)
    out=b.normalize_claim_metadata(row,'brain_system')
    assert out['graph_admission_status']=='paper_detail'
    assert out['graph_subject_kind'] in {'exposure_context','paper_topic'}
    assert out['graph_subject_label']==exposure
    assert out['compound_or_exposure']==original['compound_or_exposure']
    assert out['finding_summary']==original['finding_summary']


@pytest.mark.parametrize('exposure',[
    'Ketamine 50 mg/kg during optogenetic inhibition of dorsal thalamic inputs',
    'Phencyclidine treatment during electrical stimulation',
    'Ketamine with optogenetic inhibition, without PCP',
    'Spontaneous aura during psychedelic drug exposure',
    'Optogenetic stimulation during hallucinogen administration, without ketamine',
])
def test_actual_drug_and_manipulation_is_not_removed(exposure):
    row=source('brain_system',exposure,'Mice',
               'The manipulation changed the drug-induced cortical rhythm.',
               brain_region='Retrosplenial cortex')
    out=b.normalize_claim_metadata(row,'brain_system')
    assert out.get('graph_admission_reason')!='non_drug_intervention_or_spontaneous_state'


@pytest.mark.parametrize('population',['Mice','Adult mice','Rats'])
def test_animal_dissociation_behavior_is_not_human_subjective(population):
    row=source('subjective_experience','Ketamine',population,
               'Ketamine elicited a dissociation-like behavioral phenotype.',
               subjective_construct='Dissociation',
               instrument_or_measure='Operational dissociation-like behavior: hot-plate paw-flick and paw-lick responses')
    out=b.normalize_claim_metadata(row,'subjective_experience')
    assert out['domain']=='cognitive_behavioral'
    assert out['graph_entity_label']=='Dissociation-like behavior'
    assert out['graph_admission_status']=='paper_detail'
    assert out['kg_entity_kind_override']=='reported_measurement'


@pytest.mark.parametrize('population',['Healthy human volunteers','Adult patients','Mice and human participants'])
def test_human_or_explicit_mixed_population_is_not_relabelled_as_animal(population):
    row=source('subjective_experience','Ketamine',population,
               'Participants reported dissociation after ketamine.',
               subjective_construct='Dissociation',instrument_or_measure='Patient subjective dissociation questionnaire')
    assert b.normalize_claim_metadata(row,'subjective_experience')['domain']=='subjective_experience'


@pytest.mark.parametrize('population',['Adult male rats','Adult male squirrel monkeys'])
def test_adult_age_does_not_cancel_explicit_animal_discrimination(population):
    row=source('subjective_experience','MDMA',population,
               'The animals selected the drug-appropriate lever after MDMA.',
               subjective_construct='Subjective intensity',
               outcome_measure='Drug discrimination and drug-appropriate lever responding')
    out=b.normalize_claim_metadata(row,'subjective_experience')
    assert out['domain']=='cognitive_behavioral'
    assert out['graph_entity_label']=='Drug discrimination'


def test_behavioral_measurement_keeps_literal_endpoint_through_table_identity():
    row=source('subjective_experience','PCP','Mice',
               'PCP elicited a dissociation-like behavioral pattern in mice.',
               subjective_construct='Dissociation',
               outcome_measure='Hot-plate paw-flick and paw-lick responses and escape behavior')
    out=b.normalize_claim_metadata(row,'subjective_experience')
    kind=b.entity_kind_for(out,out['domain'])
    assert kind=='reported_measurement'
    assert b.entity_label_for(out,out['domain'],kind)=='Dissociation-like behavior'
