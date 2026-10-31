"""Safety endpoint vocabulary gaps and result-role controls from the Luna replay."""
import pytest
from pipeline.kg import build_evidence_tables as b
from pipeline.kg.safety_observation_identity import EXPLICIT_EVENT_PATTERNS, is_predicted_safety_endpoint


@pytest.mark.parametrize('event,expected', [
    ('Transient asymptomatic blood-pressure elevation', 'Cardiovascular safety'),
    ('Hypertensive emergency', 'Cardiovascular safety'),
    ('Acute serotonin toxicity', 'Serotonin syndrome'),
    ('Physical dependence and withdrawal', 'Abuse/dependence liability'),
    ('Hearing loss assessed by ABR threshold shifts and cochlear hair-cell damage', 'Tinnitus/auditory symptoms'),
    ('Unilateral optic disc swelling with acute and persistent loss of vision', 'Ocular effects'),
    ('Muscle rigidity', 'Musculoskeletal effects'),
    ('Pruritus during labor: 1/97 (1.0%) versus 9/90 (10.0%)', 'Skin/hypersensitivity effects'),
    ('Immediately after administration, hives developed on the trunk and face; there was no oxygen desaturation.', 'Skin/hypersensitivity effects'),
    ('Upper GI symptoms, including epigastric pain; endoscopic diagnoses included gastritis in 12/14 (85.7%)', 'Gastrointestinal effects'),
    ('Intraocular pressure (IOP)', 'Ocular effects'),
    ('Aplastic anaemia following MDMA exposure; it resolved spontaneously', 'Hematologic effects'),
    ('Thrombocyte levels increased; no other coagulation parameters showed a significant interaction.', 'Hematologic effects'),
    ('Intracranial pressure; ketamine did not increase intracranial pressure', 'Intracranial pressure effects'),
    ('Reduced bone mineral density (BMD) and bone mineral content (BMC)', 'Bone effects'),
])
def test_explicit_events_map_without_rewriting_source(event, expected):
    r={'source_item_type':'primary_item', 'safety_event_or_measure':event, 'frequency_or_rate':'Exact source statistic', 'result_direction':'no_difference'}
    original=r.copy()
    assert b.safety_endpoint_label(r)==expected
    assert r==original


@pytest.mark.parametrize('family', sorted({family for _,family in EXPLICIT_EVENT_PATTERNS}))
def test_added_neutral_families_round_trip(family):
    assert b.safety_category_for_text(family)==family


@pytest.mark.parametrize('event', [
    'Gastritis', 'Pruritus', 'Intraocular pressure', 'Intracranial pressure',
    'Bone mineral density', 'Platelet counts', 'Physical dependence',
])
def test_new_aliases_cannot_project_context_into_safety(event):
    assert b.safety_category_for_text(event)==''
    assert b.safety_endpoint_label({'clinical_endpoint':event})==''


@pytest.mark.parametrize('event', [
    'Addiction treatment efficacy', 'Opioid dependence treatment',
    'Tolerance to antidepressant effects', 'Tolerance to head-twitch response',
    'Treated pain', 'Skin conductance', 'Eye movement task', 'Pressure to participate',
])
def test_nearby_concepts_are_not_new_safety_endpoints(event):
    assert b.safety_endpoint_label({'safety_event_or_measure':event})==''


@pytest.mark.parametrize('event,design', [
    ('Blood pressure response; maximum increase was simulated as ≤10%', 'Population pharmacokinetic/pharmacodynamic modeling'),
    ('No cardiotoxicity was predicted to be present', 'Computational toxicity assessment'),
    ('Predicted hepatotoxicity', 'Computational prediction of toxicity using MetaTOX'),
    ('Predicted acute toxicity expressed as LD50', 'In silico assessment'),
    ('Predicted dose-dependent QTc prolongation after oral ibogaine exposure', 'Computational prediction and validation against published human data'),
    ('Predicted increased risk of adverse events based on increased brain exposure', 'Preclinical pharmacokinetic evaluation'),
    ('Modeled impact of CYP2D6 genetic polymorphism on risk of acute toxicity', 'Physiologically based modeling'),
])
def test_predictions_are_retained_as_detail_even_when_event_has_known_family(event,design):
    r={'safety_event_or_measure':event,'study_design':design,'source_item_type':'primary_item'}
    b.current_field_role_boundary(r,'safety_tolerability')
    assert r['graph_admission_status']=='paper_detail'
    assert r['graph_admission_reason']=='predicted_safety_not_observed_event'
    assert r['safety_event_or_measure']==event


@pytest.mark.parametrize('event,design', [
    ('Baseline systolic blood pressure and NET genotype predicted time to maximal systolic blood pressure', 'Randomized placebo-controlled trial; multiple linear regression'),
    ('Systolic blood pressure response was greater than predicted after the second MDMA dose', 'Randomized placebo-controlled crossover trial'),
    ('Observed QTc prolongation', 'Computational prediction and validation against published human QTc data'),
    ('Predicted and observed QTc prolongation', 'Computational modeling and clinical validation'),
    ('Observed blood-pressure response was predicted by baseline NET genotype', 'Statistical modeling of clinical trial data'),
    ('No rash was observed', 'Clinical trial'),
])
def test_observed_and_null_results_are_not_removed_by_prediction_mentions(event,design):
    assert not is_predicted_safety_endpoint(event,design)
    r={'safety_event_or_measure':event,'study_design':design}
    b.current_field_role_boundary(r,'safety_tolerability')
    assert r.get('graph_admission_reason')!='predicted_safety_not_observed_event'


def test_unresolved_joint_observation_keeps_every_clause():
    event='First unresolved endpoint; second unresolved endpoint; no change in either'
    row={'safety_event_or_measure':event}
    m=b.graphable_entity_match(row,'safety_tolerability','safety_adverse_event',event,{}, {})
    assert m['label']==event
    assert m['match_type']=='unmapped_safety_endpoint_detail_only'


@pytest.mark.parametrize('exposure,source_type,expected', [
    ('Magnesium–ibogaine therapy (MISTIC)', 'primary_item', True),
    ('Magnesium-ibogaine therapy (MISTIC)', 'primary_item', True),
    ('MISTIC', 'primary_item', False),
    ('Proposed Magnesium–ibogaine therapy (MISTIC)', 'primary_item', False),
    ('Magnesium–ibogaine therapy (MISTIC) with lithium', 'primary_item', False),
    ('Magnesium–ibogaine therapy (MISTIC)', 'review_relationship', False),
    ('Ibogaine', 'primary_item', False),
])
def test_only_complete_named_source_regimen_is_recovered(exposure,source_type,expected):
    from pipeline.kg.safety_observation_identity import explicit_named_safety_regimen
    row={'compound_or_exposure':exposure,'source_item_type':source_type,
         'safety_event_or_measure':'No serious adverse events',
         'finding_summary':'No serious treatment-emergent effects during the combined regimen.',
         'evidence_locator':'Results, Table 2'}
    assert bool(explicit_named_safety_regimen(row))==expected
    row.pop('evidence_locator')
    assert not explicit_named_safety_regimen(row)


def test_named_safety_regimen_has_no_ibogaine_overview_projection():
    r={'compound':'Magnesium–ibogaine therapy (MISTIC)','domain':'safety_tolerability'}
    match={'label':r['compound'],'matched':True,'subject_kind':'treatment_regimen',
           'match_type':'safety_regimen_detail_only'}
    assert b.overview_graph_subjects(r,match,b.registry_lookup(b.DEFAULT_REGISTRY_PATH))==[]
