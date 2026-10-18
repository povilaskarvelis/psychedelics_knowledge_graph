"""Isolated paired primary extraction refinement with unchanged domain schemas.

All generation is opt-in. Frozen sources, requests, normalization hashes and
source-first fresh references are required before paid calls. No publication.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from pipeline import llm
from pipeline.validate import luna_extraction_comparison as transport

OUT = ROOT / 'data/processed/evaluation/primary_refinement_20261018'
PREVIOUS = ROOT / 'data/processed/evaluation/primary_improvement_20261017'
PROMPT = ROOT / 'docs/extraction_profiles/candidates/primary_instruction_refinement_v3.md'
COHORTS = ('existing', 'controlled_historical', 'previous_fresh', 'fresh')
ARMS = ('baseline', 'refined')


def read(path): return json.loads(Path(path).read_text())
def digest(value): return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
def save(path, value): llm.atomic_json(path, value)


def write_once(path, value):
    path = Path(path)
    if path.exists():
        if read(path) != value:
            raise ValueError(f'Frozen artifact differs: {path}')
    else:
        save(path, value)


def candidate_instruction(case):
    base = case['instructions']
    if '## Scope' not in base:
        raise ValueError('Missing explicit domain scope')
    scope = base.split('## Scope', 1)[1].split('## Extraction Outcome', 1)[0].strip()
    prompt = PROMPT.read_text().replace('{{DOMAIN_SCOPE}}', scope)
    if '{{' in prompt:
        raise ValueError('Unresolved candidate prompt placeholder')
    return prompt.strip()


def freeze_existing():
    totals = {}
    for cohort, prior in [('existing', 'existing'), ('controlled_historical', 'controlled_historical'), ('previous_fresh', 'fresh')]:
        cases = copy.deepcopy(read(PREVIOUS / prior / 'cases.json'))
        for case in cases:
            case['cohort'] = cohort
            case['prior_cohort'] = prior
            case['split'] = 'previously_reviewed_development'
        write_once(OUT / cohort / 'cases.json', cases)
        totals[cohort] = {'papers': len({c['study_doi'] for c in cases}), 'tasks': len(cases)}
    return totals


def freeze_requests(cohort):
    cases = read(OUT / cohort / 'cases.json')
    jobs = []
    for case in cases:
        for arm in ARMS:
            jobs.append(dict(key=f"{arm}:{case['case_id']}", arm=arm,
                             case_id=case['case_id'], paper_id=case['paper_id'],
                             audit_id=case['audit_id'],
                             instructions=case['instructions'] if arm == 'baseline' else candidate_instruction(case),
                             schema=copy.deepcopy(case['schema']), content=case['content'], max_output_tokens=16384))
    # Interleave provider calls without choosing order from the outputs.
    jobs.sort(key=lambda j: digest(['primary-refinement-order-20261018', cohort, j['key']]))
    by_case = {c['case_id']: [j for j in jobs if j['case_id'] == c['case_id']] for c in cases}
    assert all(len(js) == 2 and js[0]['schema'] == js[1]['schema'] and js[0]['content'] == js[1]['content'] for js in by_case.values())
    write_once(OUT / cohort / 'paired_jobs.json', jobs)
    write_once(OUT / cohort / 'request_freeze.json', {
        'tasks_per_arm': len(cases), 'requests': len(jobs), 'request_definition_sha256': digest(jobs),
        'candidate_prompt_sha256': hashlib.sha256(PROMPT.read_bytes()).hexdigest(),
        'same_schema_and_content_each_arm': True, 'model': llm.DEFAULT_MODEL,
        'reasoning_effort': llm.REASONING_EFFORT, 'cached_previous_baselines_reused': False})
    return read(OUT / cohort / 'request_freeze.json')


def check_gate(cohort):
    experiment = read(OUT / 'experiment_freeze.json')
    for name, expected in experiment['files'].items():
        assert hashlib.sha256((OUT / name).read_bytes()).hexdigest() == expected, name
    gate = read(OUT / 'normalization_verified.json')
    for name, expected in gate['code_sha256'].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected, name
    assert (OUT / 'evaluation_protocol.md').exists()
    references = read(OUT / 'references_frozen.json')
    for name, expected in references['prior_sets'].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected, name
    if cohort == 'fresh':
        fresh_freeze = read(OUT / 'fresh/references_frozen.json')
        for item in fresh_freeze['files']:
            assert hashlib.sha256((OUT / item['path']).read_bytes()).hexdigest() == item['sha256']
        assert hashlib.sha256((OUT / fresh_freeze['combined_file']).read_bytes()).hexdigest() == fresh_freeze['combined_sha256']
        assert hashlib.sha256((OUT / 'fresh/references.json').read_bytes()).hexdigest() == fresh_freeze['combined_sha256']
        assert hashlib.sha256((OUT / 'fresh/cases.json').read_bytes()).hexdigest() == fresh_freeze['cases_sha256']
    jobs = read(OUT / cohort / 'paired_jobs.json')
    freeze = read(OUT / cohort / 'request_freeze.json')
    assert digest(jobs) == freeze['request_definition_sha256']
    assert hashlib.sha256(PROMPT.read_bytes()).hexdigest() == freeze['candidate_prompt_sha256']
    cases = read(OUT / cohort / 'cases.json')
    assert len(jobs) == 2 * len(cases)
    references_by_id = {r['audit_id']: r for r in read(OUT / cohort / 'references.json')}
    for case in cases:
        assert hashlib.sha256(case['source_text'].encode()).hexdigest() == references_by_id[case['audit_id']]['source_sha256']
        paired = [j for j in jobs if j['case_id'] == case['case_id']]
        assert {j['arm'] for j in paired} == set(ARMS)
        assert all(j['content'] == case['content'] and j['schema'] == case['schema'] for j in paired)
    return jobs


def execute(cohort, workers):
    jobs = check_gate(cohort)
    if not (OUT / 'cost.json').exists():
        save(OUT / 'cost.json', {'limit_usd': 10, 'entries': {}})
    prior = transport.OUT
    try:
        transport.OUT = OUT
        return transport.execute(cohort + '_paired', jobs, workers, result_transform=identity_transform_for_cohort(cohort))
    finally:
        transport.OUT = prior


def apply_trusted_identity_envelope(result, task):
    """Use production identity assignment without changing experimental schemas.

    Echoed bibliographic metadata is not model evidence. Explicit warnings that
    the supplied content belongs to another source remain fatal, as in production.
    The caller preserves raw_text and logs every changed envelope field.
    """
    transport.primary.reject_source_identity_mismatch_warnings(result)
    profile = transport.primary.profile_for_task(task)
    out = transport.primary.inject_route_identity_fields(copy.deepcopy(result), task, profile)
    if 'schema_version' in result:
        out['schema_version'] = result['schema_version']
    fields = ('task_id', 'route_id', 'study_doi', 'domain_route', 'paper_type', 'text_depth', 'source_type')
    mismatches = [{'field': field, 'model_echo': result.get(field), 'trusted_value': out.get(field)}
                  for field in fields if result.get(field) != out.get(field)]
    return out, {'policy': 'production_identity_injection_preserving_experimental_schema',
                 'echo_mismatches': mismatches, 'source_mismatch_warnings_rejected': True}


def identity_transform_for_cohort(cohort):
    tasks = {case['case_id']: case['task'] for case in read(OUT / cohort / 'cases.json')}
    return lambda result, job: apply_trusted_identity_envelope(result, tasks[job['case_id']])


def result_records(cohort, arm):
    records = []
    for case in read(OUT / cohort / 'cases.json'):
        key = f"{arm}:{case['case_id']}"
        path = OUT / (cohort + '_paired') / 'results' / (digest(key)[:24] + '.json')
        if path.exists():
            record = read(path)
            records.append({'case': case, 'record': record, 'result': record['result']})
    return records


def retry_transport(cohort, workers, attempt):
    jobs = check_gate(cohort)
    stage = cohort + '_paired'
    report = read(OUT / stage / 'report.json')
    errors = {e['key']: e for e in report['errors']}
    failed = [j for j in jobs if not (OUT / stage / 'results' / (digest(j['key'])[:24] + '.json')).exists()]
    if any(errors.get(j['key'], {}).get('error_type') not in {'APITimeoutError', 'APIConnectionError', 'RateLimitError'} for j in failed):
        raise RuntimeError('Inspect non-transport failures before retrying')
    retry_stage = stage + f'_retry{attempt}'
    prior = transport.OUT
    try:
        transport.OUT = OUT
        outcome = transport.execute(retry_stage, failed, workers, result_transform=identity_transform_for_cohort(cohort))
    finally:
        transport.OUT = prior
    for job in failed:
        name = digest(job['key'])[:24] + '.json'
        path = OUT / retry_stage / 'results' / name
        if path.exists():
            record = read(path)
            record['transport_retry_stage'] = retry_stage
            record['prior_attempt_billing_unknown'] = True
            write_once(OUT / stage / 'results' / name, record)
    save(OUT / stage / f'reconciliation{attempt}.json', {'original_errors': report['errors'], 'retry': outcome,
         'completed_results': sum(len(result_records(cohort, a)) for a in ARMS)})
    return outcome


def main():
    p = argparse.ArgumentParser()
    p.add_argument('command', choices=['freeze_existing', 'freeze_requests', 'extract', 'retry_transport', 'status'])
    p.add_argument('--cohort', choices=COHORTS, default='existing')
    p.add_argument('--workers', type=int, default=12)
    p.add_argument('--attempt', type=int, default=1)
    a = p.parse_args()
    if a.command == 'freeze_existing': result = freeze_existing()
    elif a.command == 'freeze_requests': result = freeze_requests(a.cohort)
    elif a.command == 'extract': result = execute(a.cohort, a.workers)
    elif a.command == 'retry_transport': result = retry_transport(a.cohort, a.workers, a.attempt)
    else:
        result = {c: {arm: len(result_records(c, arm)) for arm in ARMS}
                  for c in COHORTS if (OUT / c / 'cases.json').exists()}
        if (OUT / 'cost.json').exists():
            cost = read(OUT / 'cost.json')
            result['cost'] = {'actual_usd': sum(v.get('actual_usd', 0) for v in cost['entries'].values()),
                              'unsettled_attempts': sum('actual_usd' not in v for v in cost['entries'].values())}
    print(json.dumps(result, indent=2))


if __name__ == '__main__': main()
