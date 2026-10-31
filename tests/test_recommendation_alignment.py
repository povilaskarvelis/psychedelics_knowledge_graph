"""Recommendations retain their native semantics without becoming observed effects."""
import json
from pathlib import Path

import pandas as pd
import pytest

from pipeline.kg import build_evidence_tables as b
from pipeline.kg.convert_routed_extractions_to_evidence_rows import evidence_row_for_item
from pipeline.kg.recommendation_identity import explicit_recommendation, ENTITY_KIND, DETAIL_REASON
from pipeline.publish.export_evidence_payload import (
    load_findings, detail_bootstrap_payload, OPTIONAL_RECOMMENDATION_FIELDS,
    secondary_literature_source_key,
)


def recommendation(**changes):
    return {
        'domain': 'general_topic_coverage', 'source_type': 'guideline',
        'source_family': 'secondary_literature', 'paper_assessment_route': 'secondary_literature',
        'source_item_type': 'recommendation_item', 'extraction_schema_version': 'recommendation_consensus_v1',
        'is_in_scope': True, 'has_extractable_scoped_recommendation': True,
        'compound_or_class': 'Psilocybin', 'compound': 'Psilocybin',
        'entity': 'Eligibility and monitoring in depression',
        'recommendation_statement': 'Do not use routinely; further evidence is needed before routine implementation.',
        'recommendation_strength': 'conditional', 'direction_or_tone': 'recommends_against',
        **changes,
    }


@pytest.mark.parametrize('domain', ['general_topic_coverage', 'clinical_outcome', 'safety_tolerability', 'intervention_context'])
def test_recommendations_are_literal_secondary_guidance_in_every_source_domain(domain):
    row = recommendation(domain=domain)
    n = b.normalize_claim_metadata(row, domain)
    assert n['domain'] == 'general_topic_coverage'
    assert n['kg_entity_kind_override'] == ENTITY_KIND
    assert n['graph_entity_label'] == row['entity']
    assert n['support'] == row['recommendation_statement']
    assert n['kg_relation_type_override'] == 'has_recommendation'
    assert n['graph_admission_status'] == 'paper_detail'
    assert n['graph_admission_reason'] == DETAIL_REASON
    assert b.normalize_claim_metadata(n, n['domain']) == n
    match = b.graphable_entity_match(n, n['domain'], ENTITY_KIND, row['entity'], {}, {})
    assert match['label'] == row['entity']
    assert match['match_type'] == 'native_recommendation_topic_detail_only'


@pytest.mark.parametrize('changes', [
    {'source_type': 'primary'}, {'source_type': 'review'}, {'source_type': 'uncertain'},
    {'source_item_type': 'review_relationship'}, {'extraction_schema_version': 'legacy'},
    {'source_family': 'primary_study'}, {'paper_assessment_route': 'primary_study'},
    {'is_in_scope': False}, {'is_in_scope': 'true'}, {'has_extractable_scoped_recommendation': False},
    {'entity': ''}, {'entity': 'not_reported'}, {'compound_or_class': ''},
    {'recommendation_statement': ''}, {'recommendation_statement': 'not_reported'},
    {'entity_split_source_label': 'Parent statement'},
])
def test_explicit_native_contract_is_required(changes):
    assert not explicit_recommendation(recommendation(**changes))


@pytest.mark.parametrize('source_type', ['guideline', 'consensus_statement', 'position_statement', 'expert_recommendation'])
def test_future_converter_retains_recommendation_contract(source_type):
    row = recommendation(source_type=source_type)
    result = {'schema_version': row['extraction_schema_version'], 'domain_route': 'general_topic_coverage',
              'study_doi': '10.1000/guidance', 'task_id': 'guidance', 'source_type': source_type,
              'recommendation_assessment': {'is_in_scope': True, 'has_extractable_scoped_recommendation': True}}
    item = {k: row[k] for k in ('compound_or_class', 'entity', 'recommendation_statement', 'recommendation_strength', 'direction_or_tone')}
    converted = evidence_row_for_item(output_row={'task_id': 'guidance'}, result=result,
                                     item=item, item_kind='recommendation_item', item_index=1, tasks={})
    assert converted is not None
    assert explicit_recommendation(converted)
    assert converted['kg_entity_kind_override'] == ENTITY_KIND
    assert converted['graph_entity_label'] == row['entity']
    assert converted['support'] == row['recommendation_statement']
    assert converted['recommendation_strength'] == 'conditional'
    assert converted['direction_or_tone'] == 'recommends_against'


def saved_rows():
    return json.loads((Path(__file__).parent / 'fixtures/recommendation_saved_rows.json').read_text())


def source_key(row):
    return row['study_doi'], row['task_id'], str(row['source_item_index'])


def test_saved_luna_recommendations_keep_topics_statements_and_scope_holds(tmp_path):
    rows = saved_rows()
    source = tmp_path / 'rows.json'
    source.write_text(json.dumps(rows))
    out = tmp_path / 'tables'
    b.build_tables(graph_sources={'routed_extractions': {'path': source, 'domain': 'routed', 'dataset': 'routed',
                   'default_evidence_type': 'primary_evidence', 'skip_audit': True}}, out_dir=out, write_duckdb=False)
    f = pd.read_parquet(out / 'findings.parquet').fillna('')
    e = pd.read_parquet(out / 'evidence_edges.parquet').fillna('')
    a = pd.read_parquet(out / 'normalization_audit.parquet').fillna('')
    assert len(f) == len(rows) - 3
    assert len(a) == 3
    assert set(a.normalization_status) == {'compound_unmapped', 'compound_out_of_scope_nonpsychedelic'}
    assert f.graph_admission_status.eq('paper_detail').all()
    assert f.domain.eq('general_topic_coverage').all()
    assert f.evidence_type.eq('secondary_literature').all()
    assert f.graph_use_context_projections_json.eq('[]').all()
    assert e.entity_kind.eq(ENTITY_KIND).all()
    assert e.relation_type.eq('has_recommendation').all()
    joint = f[f.study_doi.eq('10.4088/jcp.25cs16066')]
    assert len(joint) == 1
    assert joint.iloc[0].entity_label == 'Ketamine use in treatment-resistant depression with comorbid substance use disorder'
    original = {source_key(r): r for r in rows}
    for result in f.to_dict('records'):
        raw = json.loads(result['raw_row_json']); native = original[source_key(raw)]
        assert result['entity_label'] == native['entity']
        assert result['support'] == native['recommendation_statement']
        for field in [*OPTIONAL_RECOMMENDATION_FIELDS, 'evidence_locator', 'compound_or_class', 'entity', 'item_id']:
            assert raw.get(field) == native.get(field), field


def test_full_recommendation_semantics_survive_public_export(tmp_path):
    native = next(r for r in saved_rows() if r['direction_or_tone'] == 'recommends_against')
    pd.DataFrame([{'finding_id': 'recommendation', 'paper_id': 'paper', 'source_name': 'routed_extractions',
                   'study_doi': native['study_doi'], 'domain': 'general_topic_coverage',
                   'evidence_type': 'secondary_literature', 'source_type': native['source_type'],
                   'compound': 'Psilocybin', 'entity_label': native['entity'], 'raw_row_json': json.dumps(native)}]).to_parquet(tmp_path / 'findings.parquet', index=False)
    payload = detail_bootstrap_payload(load_findings(tmp_path, require_author_identities=False), '2026-10-31', tmp_path, 'reviews')
    row = {k: payload['values'][v] for k, v in zip(payload['fields'], payload['rows'][0])}
    for field in OPTIONAL_RECOMMENDATION_FIELDS:
        assert row[field] == native[field]
    assert row['direction_or_tone'] == 'recommends_against'
    assert 'raw_row_json' not in row


def test_explicit_guidance_source_precedes_meta_analysis_publication_label():
    assert secondary_literature_source_key({'source_type': 'guideline', 'publication_type': 'Meta-analysis'}) == 'reviews'
