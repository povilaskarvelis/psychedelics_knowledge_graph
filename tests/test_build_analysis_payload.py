import json
from scripts.build_analysis_payload import build_analysis_release, columnar, compact_row, CHUNK_SIZE
from scripts.build_analysis_index import load_columnar


def test_compact_payload_keeps_finding_scope_and_complete_details_on_demand(tmp_path):
    rows = [dict(study_doi='10.1/paper', study_year='2024', entity_kind='condition_indication',
                 graph_entity_label='Depression', compound='Psilocybin', support=f'Exact quotation {i}',
                 population_model_category='human', effect_size='0.5', proposition_group_id=f'p{i}')
            for i in range(CHUNK_SIZE + 1)]
    source = tmp_path / 'detail.json'
    source.write_text(json.dumps(columnar(rows)))
    result = build_analysis_release({'primary': source}, tmp_path)
    payload = json.loads(result['sources']['primary'].read_text())
    assert payload['row_count'] == len(rows)
    assert 'support' not in payload['fields']
    assert 'population_model_category' in payload['fields']
    assert len(payload['detail_chunks']) == 2
    restored = []
    for filename in payload['detail_chunks']:
        restored.extend(load_columnar(tmp_path / filename))
    assert [row.pop('__analysis_row') for row in restored] == list(range(len(rows)))
    assert restored == rows
    again = build_analysis_release({'primary': source}, tmp_path)
    assert again['sources'] == result['sources']
    assert again['files'] == result['files']


def test_author_compaction_preserves_all_browser_identity_aliases():
    row = {'first_author': {'id': 'orcid:a', 'display_name': 'A', 'institutions': ['Large metadata'], 'orcid': 'a'}}
    assert compact_row(row)['first_author'] == {'id': 'orcid:a', 'display_name': 'A', 'orcid': 'a'}
    assert 'institutions' in row['first_author']
