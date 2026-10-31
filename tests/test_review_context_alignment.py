"""Review context coverage is retained without implying a component effect."""
import json
from pathlib import Path
import pandas as pd
import pytest
from pipeline.kg import build_evidence_tables as b
from pipeline.kg.intervention_observation_identity import anchored_review_context, intervention_observation_recovery
from pipeline.kg.convert_review_relationship_bundles_to_evidence_rows import convert_bundles
from pipeline.publish.export_evidence_payload import finding_from_record, detail_bootstrap_payload


def context_row(**changes):
    label = 'Clinical and marketed psychedelic administration'
    return {'domain': 'intervention_context', 'source_item_type': 'review_relationship', 'source_type': 'narrative_review',
            'source_family': 'secondary_literature', 'paper_assessment_route': 'secondary_literature',
            'review_extraction_method': 'paper_centered_one_pass_v2', 'review_scope_status': 'in_scope',
            'entity_role': 'intervention_context', 'coverage_type': 'review_synthesis', 'coverage_focus': 'paper_defining',
            'relationship_projection_basis': 'principal_object', 'context_component': label, 'graph_entity_label': label,
            'finding_summary': 'The review calls for safeguards; it does not evaluate whether these improve outcomes.',
            'notes': 'Comparative effects were not evaluated.', 'evidence_locator': 'Discussion', 'source_item_id': 'R1',
            'relationship_source_group_key': '10.example/review#R1', 'graph_subject_label': 'Psilocybin',
            'relationship_domain_labels_json': '["intervention_context"]',
            'relationship_anchors_json': json.dumps([{'role': 'intervention_context', 'label': label, 'anchor_type': 'context'}]),
            **changes}


@pytest.mark.parametrize('length', [30, 80, 81, 250])
def test_exact_context_is_retained_without_a_controlled_parent_or_length_rule(length):
    label = 'Context ' + 'x' * length
    row = context_row(context_component=label, graph_entity_label=label,
                      relationship_anchors_json=json.dumps([{'role': 'intervention_context', 'label': label}]))
    assert anchored_review_context(row)
    result = intervention_observation_recovery(row, label, '')
    assert result['label'] == label
    assert result['match_type'] == 'anchored_review_context_detail_only'
    assert result['reason'] == 'review_context_coverage_not_observed_component_effect'
    assert intervention_observation_recovery(row, 'Music', '') is None


@pytest.mark.parametrize('changes', [
    {'domain': 'clinical_outcome'}, {'source_item_type': 'primary_item'}, {'source_type': 'primary'},
    {'source_type': 'meta_analysis'}, {'source_family': 'primary_study'}, {'paper_assessment_route': 'primary_study'},
    {'review_extraction_method': 'legacy'}, {'review_scope_status': 'psychedelics_peripheral_or_absent'},
    {'entity_role': 'comparator'}, {'entity_role': 'population'}, {'coverage_type': 'uncertain'},
    {'coverage_focus': 'unclear'}, {'relationship_projection_basis': 'inferred'}, {'evidence_locator': 'not_reported'},
    {'source_item_id': ''}, {'relationship_source_group_key': ''}, {'graph_subject_label': ''},
    {'context_component': 'not_reported'}, {'finding_summary': ''}, {'entity_split_source_label': 'parent'},
    {'relationship_domain_labels_json': '["general_topic_coverage"]'}, {'relationship_domain_labels_json': '{}'},
    {'relationship_anchors_json': 'malformed'}, {'relationship_anchors_json': '{}'},
    {'relationship_anchors_json': '[{"role":"comparator","label":"Clinical and marketed psychedelic administration"}]'},
    {'relationship_anchors_json': '[{"role":"intervention_context","label":"Other context"}]'},
])
def test_missing_or_conflicting_source_contract_cannot_supply_eligibility(changes):
    assert not anchored_review_context(context_row(**changes))


def test_current_converter_preserves_the_context_source_contract():
    row = context_row()
    relationship = {'item_id': 'R1', 'relationship_statement': row['finding_summary'], 'relationship_kind': 'review_synthesis',
                    'paper_prominence': 'paper_defining', 'graph_eligibility': 'main_graph', 'graph_form': 'context',
                    'direction_or_tone': 'descriptive_only', 'domain_labels': ['intervention_context'],
                    'limitations': [row['notes']], 'evidence_locators': [{'location': 'discussion', 'locator': 'Discussion', 'supporting_text': ''}],
                    'anchors': [{'role': 'compound', 'label': 'Psilocybin', 'anchor_type': 'named_entity'},
                                {'role': 'intervention_context', 'label': row['context_component'], 'anchor_type': 'context'}]}
    bundles = [{'status': 'ok', 'study_doi': '10.example/review', 'study_title': 'Psilocybin clinical context',
                'text_depth': 'article_text', 'result': {'paper_frame': {}, 'relationships': [relationship]}}]
    tasks = [{'study_doi': '10.example/review', 'paper_metadata': {'study_title': 'Psilocybin clinical context'}}]
    registry = {'compounds': [{'label': 'Psilocybin', 'aliases': []}], 'targets': [], 'disorders': []}
    converted, _ = convert_bundles(bundles, tasks, registry, active_candidate_dois={'10.example/review'})
    assert len(converted) == 1
    assert anchored_review_context(converted[0])
    assert converted[0]['finding_summary'] == row['finding_summary']
    assert converted[0]['notes'] == row['notes']


def fixture():
    return json.loads((Path(__file__).parent / 'fixtures/review_context_saved_rows.json').read_text())


def source_key(row):
    return tuple(str(row.get(k, '')) for k in ('study_doi', 'source_item_id', 'source_item_index',
                  'relationship_projection_basis', 'relationship_projection_anchor_index', 'context_component'))


def test_saved_reviews_recover_intact_context_and_keep_existing_scope_decisions(tmp_path):
    data = fixture(); rows = data['rows']; path = tmp_path / 'rows.json'; path.write_text(json.dumps(rows))
    b.build_tables(graph_sources={'routed_extractions': {'path': path, 'domain': 'routed', 'dataset': 'routed',
                   'default_evidence_type': 'primary_evidence', 'skip_audit': True}}, out_dir=tmp_path / 'tables', write_duckdb=False)
    f = pd.read_parquet(tmp_path / 'tables/findings.parquet').fillna('')
    a = pd.read_parquet(tmp_path / 'tables/normalization_audit.parquet').fillna('')
    original = {source_key(r): r for r in rows}
    recovered = f[f.entity_match_type.eq('anchored_review_context_detail_only')]
    assert len(recovered) == len(data['recovered_keys']) == 10
    assert recovered.graph_admission_status.eq('paper_detail').all()
    assert recovered.graph_parent_label.eq('').all()
    assert recovered.graph_use_context_projections_json.eq('[]').all()
    assert recovered.evidence_type.eq('secondary_literature').all()
    actual = {}
    for r in f.to_dict('records'):
        raw = json.loads(r['raw_row_json']); key = source_key(raw); actual[key] = r
        for field in ['context_component', 'finding_summary', 'support', 'notes', 'evidence_locator',
                      'relationship_anchors_json', 'relationship_domain_labels_json', 'relationship_graph_form']:
            assert raw.get(field) == original[key].get(field), field
        if r['entity_match_type'] == 'anchored_review_context_detail_only':
            assert r['entity_label'] == original[key]['context_component']
    for expected in data['accepted']:
        for field in ['entity_label', 'entity_match_type', 'graph_admission_status']:
            assert actual[tuple(expected['key'])][field] == expected[field]
    holds = {source_key(json.loads(r['raw_row_json'])): r['normalization_status'] for r in a.to_dict('records')}
    assert holds == {tuple(r['key']): r['reason'] for r in data['held']}


def test_source_context_summary_and_limitations_survive_public_export():
    native = context_row()
    record = {'finding_id': 'review', 'paper_id': 'paper', 'domain': 'intervention_context',
              'evidence_type': 'secondary_literature', 'raw_row_json': json.dumps(native)}
    finding = finding_from_record(record, {})
    payload = detail_bootstrap_payload([finding], '2026-10-31', Path('.'), 'reviews')
    public = {k: payload['values'][v] for k, v in zip(payload['fields'], payload['rows'][0])}
    assert public['review_context_component'] == native['context_component']
    assert public['review_context_summary'] == native['finding_summary']
    assert public['review_context_limitations'] == native['notes']
    invalid = finding_from_record({**record, 'raw_row_json': json.dumps(context_row(source_item_type='primary_item'))}, {})
    assert not any(k.startswith('review_context_') for k in invalid)
