import json
import pytest

from pipeline.extract.repair_extraction_routing import exception_worklist, validate_plan, apply_route_owners, replace_task_projection


def output(doi, status, items=None):
    return {'study_doi': doi, 'result': {'extraction_status': status, 'items': items or []}}


def test_only_wholly_empty_exceptions_can_be_replaced():
    rows = [output('10.1/empty', 'wrong_source_type'), output('10.1/partial', 'wrong_source_type'),
            output('10.1/partial', 'extracted', [{'support': 'A real finding'}]),
            output('10.1/irrelevant', 'not_relevant')]
    assert set(exception_worklist(rows)) == {'10.1/empty'}


def test_plan_cannot_resurrect_an_unselected_paper_or_replace_valid_evidence():
    exceptions = exception_worklist([output('10.1/empty', 'wrong_source_type')])
    plan = {'decisions': [{'doi': '10.1/empty', 'action': 'reroute_review', 'reason': 'Verified review genre', 'evidence_artifact': 'source.json'}]}
    validate_plan(plan, exceptions, {'10.1/empty'})
    with pytest.raises(ValueError): validate_plan(plan, exceptions, set())
    with pytest.raises(ValueError): validate_plan(plan, {}, {'10.1/empty'})


def test_owner_application_is_scoped_and_idempotent(tmp_path):
    route_path = tmp_path/'pipeline/extract/manual_extraction_route_overrides.json'
    metadata_path = tmp_path/'data/curated/paper_metadata_overrides.json'
    route_path.parent.mkdir(parents=True); metadata_path.parent.mkdir(parents=True)
    original = {'doi': '10.1/unrelated', 'manual_action': 'hold_source_review', 'manual_reason': 'Existing hold'}
    route_path.write_text(json.dumps({'records': [original]}))
    metadata_path.write_text(json.dumps({'records': [{'doi': '10.1/unrelated', 'fields': {'study_title': 'Keep'}}]}))
    plan_path = tmp_path/'plan.json'
    plan = {'decisions': [{'doi': '10.1/review', 'action': 'reroute_review', 'reason': 'Verified report design', 'evidence_artifact': 'proof.json'}]}
    plan_path.write_text(json.dumps(plan))
    first = apply_route_owners(plan, plan_path, tmp_path)
    assert json.loads(route_path.read_text())['records'][0] == original
    assert json.loads(metadata_path.read_text())['records'] == [{'doi': '10.1/unrelated', 'fields': {'study_title': 'Keep'}}]
    before = route_path.read_bytes()
    assert apply_route_owners(plan, plan_path, tmp_path) == first
    assert route_path.read_bytes() == before
    plan_path.write_text(json.dumps({'decisions': []}))
    with pytest.raises(ValueError): apply_route_owners({'decisions': []}, plan_path, tmp_path)


def test_task_projection_preserves_unrelated_jsonl_and_displaced_history(tmp_path):
    path=tmp_path/'tasks.jsonl'
    unchanged='{"study_doi":"10.1/untouched", "task_id":"stable", "text":"Exact   spacing\u2028inside string"}\n'
    path.write_text(unchanged+'{"study_doi":"10.1/repair","task_id":"old"}\n')
    task={'study_doi':'10.1/repair','task_id':'new'};receipt=tmp_path/'projection.json'
    result=replace_task_projection(path,{'10.1/repair'},[task],receipt)
    assert path.read_text().startswith(unchanged)
    assert result['removed_tasks']==1 and result['added_tasks']==1
    assert 'old' in (tmp_path/'projection_displaced.jsonl').read_text()
    assert replace_task_projection(path,{'10.1/repair'},[task],receipt)==result
    with pytest.raises(ValueError):replace_task_projection(path,set(),[task],tmp_path/'outside.json')
