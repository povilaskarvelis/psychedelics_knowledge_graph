import json

from pipeline.validate import luna_extraction_comparison as experiment


def test_strip_annotations_preserves_property_named_description():
    schema=dict(type='object',description='Documentation',required=['description'],
                properties=dict(description=dict(type='string',description='Field documentation')))
    experiment.strip_schema_descriptions(schema)
    assert 'description' not in schema
    assert schema['properties']['description']==dict(type='string')


def test_clarification_is_inserted_before_output_contract():
    prompt = experiment.revised_instruction('Task\n## Rules\nReturn JSON.', 'primary')
    assert prompt.index('## Substance and source eligibility') < prompt.index('## Rules')
    assert 'analyzed subgroup denominator' in prompt


def test_anonymous_grading_is_paired_and_preserves_frozen_reference(tmp_path, monkeypatch):
    monkeypatch.setattr(experiment, 'OUT', tmp_path)
    paper = dict(paper_id='primary:10.test/a', family='primary', split='development',
                 domains=['clinical_outcome'], source_text='An exact source statement.')
    experiment.write_rows(tmp_path / 'papers.jsonl', [paper])
    reference = dict(central_facts=[dict(fact_id='F1', statement='Source fact')])
    monkeypatch.setattr(experiment, 'stage_results', lambda _: {paper['paper_id']: dict(result=reference)})

    def records(split, variant):
        return [dict(case=dict(case_id='task-a', paper_id=paper['paper_id'],
                               family='primary', domain='clinical_outcome'),
                     result=dict(items=[dict(statement=variant)]))]

    monkeypatch.setattr(experiment, 'extraction_records', records)
    jobs = list(experiment.judge_jobs('development', 'clarified'))
    body = json.loads(jobs[0]['content'].split('\n\nSOURCE_TEXT:')[0])
    mapping = experiment.read(tmp_path / 'development_judge_clarified/blinding_key.json')[0]
    assert body['reference'] == reference
    assert body['X'][0]['data']['statement'] == mapping['X']
    assert body['Y'][0]['data']['statement'] == mapping['Y']
    assert body['X'][0]['item_id'] == body['Y'][0]['item_id'] == 'task-a:1'
    assert {'baseline', 'clarified'} == {mapping['X'], mapping['Y']}


def test_guideline_items_are_counted():
    record = dict(case=dict(case_id='g', family='guideline', domain='care'),
                  result=dict(recommendation_items=[dict(recommendation='Monitor')]))
    assert len(experiment.normalized_items(record)) == 1


def test_grading_includes_scientific_overview_without_creating_an_abstention_finding():
    record=dict(case=dict(case_id='g',family='guideline',domain='care'),
        result=dict(task_id='g',recommendation_items=[],
                    recommendation_assessment=dict(scope='Initial induction only; maintenance evidence limited')))
    assert experiment.normalized_items(record)==[]
    items=experiment.normalized_items(record,include_context=True)
    assert items[0]['item_id']=='g:context'
    assert items[0]['data']['recommendation_assessment']['scope'].startswith('Initial induction')
    assert 'task_id' not in items[0]['data']
