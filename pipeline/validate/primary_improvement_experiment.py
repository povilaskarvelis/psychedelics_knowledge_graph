"""Isolated normalization and primary observation-contract experiment.

Artifacts and API responses are staged. Production graph pointers are never
written. Baseline/current prompt and schema arms have separately frozen requests.
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
from pipeline.extract.primary_observation_contract import candidate_instruction, candidate_schema
from pipeline.validate import luna_extraction_comparison as old

OUT = ROOT / 'data/processed/evaluation/primary_improvement_20261017'
AUDIT = ROOT / 'data/processed/evaluation/primary_comprehensive_audit_20261017'
ARMS = ('baseline', 'instructions', 'structured')


def read(path): return json.loads(Path(path).read_text())
def rows(path): return [json.loads(line) for line in Path(path).open() if line.strip()]
def digest(value): return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
def save(path,value): llm.atomic_json(path,value)


def write_once(path, value):
    path=Path(path)
    if path.exists():
        if read(path) != value: raise ValueError(f'Frozen artifact changed: {path}')
    else: save(path,value)


def freeze_existing():
    papers=read(AUDIT/'manifest.json')['papers']
    ids={p['paper_id']:p['audit_id'] for p in papers}
    records=[r for split in ['development','holdout'] for r in old.extraction_records(split,'baseline') if r['case']['family']=='primary']
    cases=[]
    for rec in records:
        case=copy.deepcopy(rec['case']);case['audit_id']=ids[case['paper_id']];case['cohort']='existing'
        cases.append(case)
        record=copy.deepcopy(rec['record']);record['result']=rec['result'];record['reused_saved_baseline']=True
        record['key']=case['case_id'];record['case_id']=case['case_id'];record['paper_id']=case['paper_id']
        write_once(OUT/'existing_baseline/results'/(digest(case['case_id'])[:24]+'.json'),record)
    write_once(OUT/'existing/cases.json',sorted(cases,key=lambda c:c['case_id']))
    return {'papers':len(ids),'tasks':len(cases),'items':sum(len(r['result']['items']) for r in records)}


def freeze_requests(cohort):
    cases=read(OUT/cohort/'cases.json')
    summary={}
    for arm in ARMS:
        jobs=[]
        for c in cases:
            instructions=c['instructions'] if arm=='baseline' else candidate_instruction(c['instructions'],structured=arm=='structured')
            schema=copy.deepcopy(c['schema']) if arm!='structured' else candidate_schema(c['schema'])
            jobs.append(dict(key=c['case_id'],case_id=c['case_id'],paper_id=c['paper_id'],
                             instructions=instructions,schema=schema,content=c['content'],max_output_tokens=16384))
        write_once(OUT/cohort/f'{arm}_jobs.json',jobs)
        summary[arm]={'tasks':len(jobs),'request_definition_sha256':digest(jobs)}
    write_once(OUT/cohort/'request_freeze.json',summary)
    return summary


def execute(cohort, arm, workers):
    if not (OUT/'normalization_verified.json').exists():
        raise RuntimeError('Complete saved-output normalization verification before extraction comparisons')
    if cohort=='fresh' and not (OUT/'fresh/references_frozen.json').exists():
        raise RuntimeError('Freeze source-first fresh references before extraction comparisons')
    jobs=read(OUT/cohort/f'{arm}_jobs.json')
    freeze=read(OUT/cohort/'request_freeze.json')
    if digest(jobs)!=freeze[arm]['request_definition_sha256']:raise ValueError('Frozen requests changed')
    OUT.mkdir(parents=True,exist_ok=True)
    if not (OUT/'cost.json').exists():save(OUT/'cost.json',{'limit_usd':10,'entries':{}})
    original=old.OUT
    try:
        old.OUT=OUT
        return old.execute(cohort+'_'+arm,jobs,workers)
    finally:old.OUT=original


def result_records(cohort,arm):
    cases=read(OUT/cohort/'cases.json');records=[]
    for c in cases:
        p=OUT/(cohort+'_'+arm)/'results'/(digest(c['case_id'])[:24]+'.json')
        if p.exists():
            r=read(p);records.append({'case':c,'record':r,'result':r['result']})
    return records


def retry_transport_failures(cohort, arm, workers):
    """One separately budgeted retry; retain unknown charges from timed-out calls."""
    stage = cohort + '_' + arm
    report = read(OUT/stage/'report.json')
    if any(e['error_type'] not in {'APITimeoutError', 'APIConnectionError'} for e in report['errors']):
        raise RuntimeError('Inspect non-transport failures before retrying')
    failed = {e['key'] for e in report['errors']}
    jobs = [j for j in read(OUT/cohort/f'{arm}_jobs.json') if j['key'] in failed]
    retry_stage = stage + '_transport_retry1'
    original = old.OUT
    try:
        old.OUT = OUT
        result = old.execute(retry_stage, jobs, workers)
    finally:
        old.OUT = original
    for job in jobs:
        name = digest(job['key'])[:24] + '.json'
        path = OUT/retry_stage/'results'/name
        if path.exists():
            record = read(path)
            record['transport_retry_stage'] = retry_stage
            record['prior_timeout_charge_unknown_ceiling_retained'] = True
            write_once(OUT/stage/'results'/name, record)
    save(OUT/stage/'transport_reconciliation.json', {
        'original_failures_retained': report['errors'], 'retry': result,
        'complete_results': len(result_records(cohort, arm)),
        'billing': 'Timed-out attempt ceilings remain reserved; retry usage charged separately.'})
    return result


def main():
    p=argparse.ArgumentParser();p.add_argument('command',choices=['freeze_existing','freeze_requests','extract','retry_transport','status'])
    p.add_argument('--cohort',choices=['existing','fresh','controlled_historical'],default='existing')
    p.add_argument('--arm',choices=ARMS,default='instructions');p.add_argument('--workers',type=int,default=8)
    a=p.parse_args()
    if a.command=='freeze_existing': result=freeze_existing()
    elif a.command=='freeze_requests': result=freeze_requests(a.cohort)
    elif a.command=='extract': result=execute(a.cohort,a.arm,a.workers)
    elif a.command=='retry_transport': result=retry_transport_failures(a.cohort,a.arm,a.workers)
    else:
        result={}
        for cohort in ['existing','fresh','controlled_historical']:
            if (OUT/cohort/'cases.json').exists():result[cohort]={arm:len(result_records(cohort,arm)) for arm in ARMS}
        if (OUT/'cost.json').exists():
            cost=read(OUT/'cost.json');result['cost']={'limit_usd':cost['limit_usd'],'actual_usd':sum(v.get('actual_usd',0) for v in cost['entries'].values()),'unsettled_requests':sum('actual_usd' not in v for v in cost['entries'].values())}
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
