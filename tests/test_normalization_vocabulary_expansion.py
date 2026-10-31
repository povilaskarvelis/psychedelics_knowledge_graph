"""Vocabulary expansion must resolve identities without fabricating specificity."""
import pytest
from pipeline.kg import build_evidence_tables as b
from pipeline.kg.safety_observation_identity import is_predicted_safety_endpoint

@pytest.fixture(scope='module')
def vocab():
    return b.node_vocabulary_lookup()

@pytest.fixture(scope='module')
def registry():
    return b.registry_lookup(b.DEFAULT_REGISTRY_PATH)

@pytest.mark.parametrize('raw,label',[
    ('Cognitive inhibition','Inhibitory control'),('Mental set switching','Set shifting'),
    ('Head twitches','Head-twitch response'),('Cataleptic behavior','Catalepsy'),
    ('Serial learning','Sequence learning'),('Motor skill learning','Motor learning'),
    ('Convergent thinking','Convergent thinking'),('Social functioning','Social functioning'),
    ('Visual learning','Visual learning'),('Overall cognitive performance','Global cognition'),
])
def test_complete_constructs(raw,label,vocab):
    match=b.match_vocabulary_entity(raw,'cognitive_behavioral_construct',vocab)
    assert match['matched'] and match['label']==label

@pytest.mark.parametrize('raw',[
    'Convergent thinking and unrelated outcome','Unknown result (Convergent thinking)',
    'Motor learning (combined with unrelated measure)',
    'Cognitive inhibition and an unidentified outcome',
    'Predicted Serial learning proxy (not measured)',
])
def test_complete_alias_does_not_discard_other_words(raw,vocab):
    assert not b.match_vocabulary_entity(raw,'cognitive_behavioral_construct',vocab)['matched']

def test_neighboring_constructs_remain_distinct(vocab):
    for a,c in [('Social functioning','Social interaction'),('Visual learning','Visual memory'),
                ('Motor learning','Motor coordination'),('Convergent thinking','Creativity')]:
        assert b.match_vocabulary_entity(a,'cognitive_behavioral_construct',vocab)['label'] != c
    assert not b.match_vocabulary_entity('Ego dissolution','cognitive_behavioral_construct',vocab)['matched']

@pytest.mark.parametrize('raw,label',[
    ('2-Br-LSD','2-bromo-LSD'),('BOL-148','2-bromo-LSD'),('MXE','Methoxetamine'),
    ('Psilocine','Psilocin'),('4-HO-DiPT','4-OH-DiPT'),
])
def test_verified_compound_aliases(raw,label,registry):
    row={'compound':raw,'graph_subject_kind':'atomic_compound'}
    m=b.graphable_subject_match(row,registry)
    assert m['label']==label
    assert [x['label'] for x in b.overview_graph_subjects(row,m,registry)]==[label]

@pytest.mark.parametrize('raw',[
    '2-Br-LSD analogue 4a','N1-([11C]-methyl)-2-Br-LSD ([11C]-MBL)',
    '4-HO-DiPT versus 4-MeO-DiPT','4-HO-MET','Psilocine derivative 4f',
    'MXE analogue 25a',
    'N-4-MXE (compound 19)', 'DM-nor-MXE (compound 20)',
    'DM-nor-4-MXE (compound 21)', 'Desmethyl-4-MXE (compound 23)',
    '4-OH-DiPT-glucuronide', '4-OH-DiPT-sulfate', '4-OH-DiPT-N-oxide',
])
def test_aliases_do_not_promote_analogues_or_split_pools(raw,registry):
    row={'compound':raw,'graph_subject_kind':'atomic_compound'}
    match=b.graphable_subject_match(row,registry)
    assert not b.overview_graph_subjects(row,match,registry)

@pytest.mark.parametrize('raw,expected',[
    ('RS130-180 + 2-Br-LSD', {'2-bromo-LSD'}),
    ('4-HO-DiPT or 4-HO-McPT', {'4-OH-DiPT'}),
    ('2-Br-LSD + LSD', {'2-bromo-LSD','LSD'}),
    ('4-HO-DiPT + DiPT', {'4-OH-DiPT','DiPT'}),
])
def test_registered_alias_does_not_add_parent_drug(raw,expected,registry):
    assert b.prune_compound_text_labels(raw,b.registry_compound_labels_in_text(raw,registry)) == expected

def test_other_intervention_oxide_does_not_erase_named_drug(registry):
    assert not b.unregistered_chemical_identity('Ketamine plus clozapine-N-oxide (CNO)', registry)

def test_explicitly_registered_conjugate_keeps_its_own_identity(registry):
    registry = dict(registry)
    label = '4-OH-DiPT-glucuronide'
    registry[('compound',b.label_key(label))] = {'label':label,'aliases':[]}
    assert not b.unregistered_chemical_identity(label, registry)
    assert b.graphable_compound_match(label,registry)['label'] == label

def test_pooled_native_result_is_not_split_by_new_aliases(registry):
    row={'compound':'Ketamine and esketamine','graph_subject_kind':'compound_combination',
         'source_type':'meta_analysis','meta_analysis_subject_scope':'pooled_named_drugs'}
    match=b.graphable_subject_match(row,registry)
    assert not b.overview_graph_subjects(row,match,registry)

@pytest.mark.parametrize('raw,label,kind',[
    ('α1-adrenoceptor','alpha1 adrenoceptor family','system_family'),
    ('Peripheral α1-adrenoceptors','alpha1 adrenoceptor family','system_family'),
    ('α2-adrenoceptors','alpha2 adrenoceptor family','system_family'),
    ('β-adrenoceptor','beta adrenoceptor family','system_family'),
    ('α1A-adrenoceptor','alpha1A adrenoceptor (ADRA1A)','target'),
    ('CYP3A','CYP3A enzyme family','system_family'),('CYP3A4','CYP3A4','target'),
    ('Butyrylcholinesterase (BChE)','Butyrylcholinesterase (BCHE)','target'),
])
def test_target_specificity(raw,label,kind,registry):
    m=b.match_registry_entity(raw,'target',registry,{'assay_type':'Radioligand binding'})
    assert (m['matched'],m['label'],m['kind'])==(True,label,kind)

@pytest.mark.parametrize('raw',['CYP3A99','alpha1Z-adrenoceptor','Butyrylcholinesterase mutant X99',
                              'Butyrylcholinesterase and unidentified receptor'])
def test_unknown_targets_stay_unresolved(raw,registry):
    assert not b.match_registry_entity(raw,'target',registry,{'assay_type':'Radioligand binding'})['matched']

def test_target_name_does_not_establish_direct_assay(registry):
    from pipeline.kg.target_identity import recovered_target_detail_reason
    row={'source_item_type':'primary_item','compound':'MDMA',
         'assay_type':'Antagonist pretreatment followed by behavioral testing'}
    assert recovered_target_detail_reason(row)=='target_mechanism_without_direct_assay'

@pytest.mark.parametrize('event,parent',[
    ('Nightmares','Sleep disturbance'),('Cerebral oedema','Adverse events'),
    ('Dysgeusia','Adverse events'),('Paresthesia','Adverse events'),
    ('All-cause treatment discontinuation','All-cause discontinuation'),
    ('Dropouts for any cause','All-cause discontinuation'),
])
def test_explicit_safety_endpoint_vocabulary(event,parent):
    assert b.safety_category_for_text(event,explicit_event=True)==parent
    assert b.safety_endpoint_label({'safety_event_or_measure':event})==parent

def test_safety_aliases_do_not_supply_missing_cause_or_erase_predictions():
    assert not b.safety_category_for_text('Tolerance',explicit_event=True)
    assert not b.safety_category_for_text('Participant dropout',explicit_event=True)
    assert not b.safety_category_for_text('Risk profiles',explicit_event=True)
    assert is_predicted_safety_endpoint('Predicted cerebral edema','QSAR')
