import json

import pandas as pd
import pytest

from pipeline.kg import build_evidence_tables as b
from pipeline.kg.build_author_tables import best_author_identity_confidence
from pipeline.kg.measured_endpoint_repairs import apply_measured_endpoint_repairs
from pipeline.publish.export_evidence_payload import public_author_row


def test_author_aggregate_does_not_erase_conflict_quarantine():
    confidence = best_author_identity_confidence('openalex:A123', [
        'openalex_author_id', 'openalex_author_id_orcid_conflict'])
    assert confidence == 'openalex_author_id_orcid_conflict'
    assert not public_author_row({'author_id':'openalex:A123','identity_confidence':confidence})


def connectivity_row():
    return {'domain':'brain_system','paper_type':'primary_study','source_item_type':'primary_item',
        'primary_graph_anchor_kind':'neural_circuit', 'kg_entity_kind_override':'neural_circuit',
        'compound':'LSD', 'graph_entity_label':'Retinotopically congruent and incongruent V1–V3 patch pairs',
        'neural_circuit':'Retinotopically congruent and incongruent V1–V3 patch pairs',
        'brain_region':'Primary visual cortex (V1) and visual area V3',
        'readout':'Retinotopic coordination: difference between RSFC of congruent and incongruent V1–V3 patches',
        'finding_summary':'The congruent–incongruent connectivity contrast increased; imagery correlation was null.',
        'result_direction':'increase','evidence_locator':'Figure 2'}


def test_connectivity_pair_fallback_keeps_the_connection_and_null_qualification():
    row=connectivity_row();out,domain=apply_measured_endpoint_repairs(row,'brain_system')
    assert out['measured_endpoint_brain_relationship']=='pairwise_connectivity'
    assert out['neural_circuit']==row['neural_circuit']
    assert out['finding_summary']==row['finding_summary']
    projected=b.entity_expanded_rows(out,domain,b.registry_lookup(b.DEFAULT_REGISTRY_PATH),b.node_vocabulary_lookup())
    assert {r['graph_entity_label'] for r in projected}=={'Primary visual cortex','Visual area V3'}
    assert all(r['readout']==row['readout'] and r['neural_circuit']==row['neural_circuit'] for r in projected)
    assert all(r['result_direction']==row['result_direction'] for r in projected)
    assert len({b.proposition_identifiers(r,'LSD','brain_region',r['graph_entity_label'])[0] for r in projected})==1


@pytest.mark.parametrize('change', [
    {'brain_region':'V1 and V3'},
    {'brain_region':'Primary visual cortex and an unknown cortex'},
    {'neural_circuit':'Activation in two areas'},
    {'readout':'Regional activation'},
])
def test_missing_or_unresolvable_pair_never_gets_a_partial_anatomical_projection(change):
    row=connectivity_row();row.update(change)
    out,domain=apply_measured_endpoint_repairs(row,'brain_system')
    if 'measured_endpoint_brain_relationship' not in out:
        assert out==row
    else:
        projected=b.entity_expanded_rows(out,domain,b.registry_lookup(b.DEFAULT_REGISTRY_PATH),b.node_vocabulary_lookup())
        assert not any(r.get('entity_split_source_label') for r in projected)


@pytest.mark.parametrize('label,family',[
    ('Brain activity entropy','Neural signal complexity'),
    ('Brain criticality','Network dynamics'),
    ('Cortical functional hierarchy','Network topology'),
    ('Functional harmonic ψ2','Network dynamics'),
])
def test_global_neural_measurements_are_retained_without_anatomical_claims(label,family):
    match=b.graphable_entity_match({'readout':label},'brain_system','brain_network',label,
                                  b.registry_lookup(b.DEFAULT_REGISTRY_PATH),b.node_vocabulary_lookup())
    assert match['matched'] and match['kind']=='brain_measure' and match['label']==family


def test_entropy_pathway_repair_does_not_turn_gene_entropy_into_a_neural_measure():
    base={'domain':'molecular_pathway_readout','kg_entity_kind_override':'pathway_process',
          'compound':'LSD','source_item_type':'review_relationship','graph_entity_label':'Brain activity entropy'}
    out=b.normalize_claim_metadata(base,base['domain'])
    assert out['domain']=='brain_system' and out['kg_entity_kind_override']=='brain_measure'
    molecular={**base,'graph_entity_label':'Gene expression entropy','assay_type':'RNA sequencing'}
    out=b.normalize_claim_metadata(molecular,molecular['domain'])
    assert out['domain']=='molecular_pathway_readout'


@pytest.mark.parametrize('label,canonical',[
    ('Food-reinforced operant responding','Operant responding'),
    ('Cognitive performance','Global cognition'),
    ('Letter fluency','Verbal fluency'),
    ('Nature relatedness','Nature relatedness'),
    ('Suggestibility','Suggestibility'),
    ('Conscientiousness','Conscientiousness'),
    ('Dyskinesia','Dyskinesia'),
])
def test_reviewed_construct_identity_does_not_require_effect_or_diagnosis_inference(label,canonical):
    match=b.match_vocabulary_entity(label,'cognitive_behavioral_construct',b.node_vocabulary_lookup())
    assert match['matched'] and match['label']==canonical


def test_specific_personality_and_behavioural_constructs_do_not_collapse_into_each_other():
    vocab=b.node_vocabulary_lookup()
    for label in ['Neuroticism','Openness to experience','Conscientiousness','Agreeableness','Extraversion','Suggestibility']:
        assert b.match_vocabulary_entity(label,'cognitive_behavioral_construct',vocab)['label']==label
    for label in ['Behavior','Memory and attention','Unknown construct XYZZY']:
        assert not b.match_vocabulary_entity(label,'cognitive_behavioral_construct',vocab)['matched']


@pytest.mark.parametrize('label',[
    'Implicit suicide-related cognition','Suicide-related cognition',
    'Implicit cognition','Spatial cognitive performance','Ontological openness',
    'Absorption of MDMA',
])
def test_generic_synonym_does_not_erase_a_more_specific_unmapped_construct(label):
    match=b.match_vocabulary_entity(label,'cognitive_behavioral_construct',b.node_vocabulary_lookup())
    assert not match['matched']


def test_exact_cognition_synonym_still_works_without_substring_matching():
    vocab=b.node_vocabulary_lookup()
    assert b.match_vocabulary_entity('Cognition','cognitive_behavioral_construct',vocab)['label']=='Global cognition'
    assert not b.node_vocabulary_hits_in_text('implicit suicide-related cognition',['cognitive_behavioral_construct'],vocab)
    assert not b.literal_node_vocabulary_hits_in_text('implicit suicide-related cognition',['cognitive_behavioral_construct'],vocab)


def test_neural_measure_admission_matches_the_existing_anatomical_view_contract():
    row={'domain':'brain_system','kg_entity_kind_override':'brain_measure','graph_entity_label':'Neural signal complexity'}
    assert b.graph_admission_decision(row)==('paper_detail','neural_measure_without_anatomical_anchor')
    anatomical={**row,'kg_entity_kind_override':'brain_region','graph_entity_label':'Hippocampus'}
    assert b.graph_admission_decision(anatomical)==('main_graph','semantically_complete')
