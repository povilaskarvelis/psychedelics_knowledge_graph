"""Summarize paired extraction judgments without treating them as human gold."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
import random

from pipeline.validate import luna_extraction_comparison as experiment


def summarize(split, variant):
    e = experiment
    stage = split + '_judge_' + variant
    mapping = {r['paper_id']: r for r in e.read(e.OUT / stage / 'blinding_key.json')}
    references = e.stage_results('references_reviewed')
    papers = {r['paper_id']: r for r in e.rows(e.OUT / 'papers.jsonl')}
    records = {arm: e.extraction_records(split, arm) for arm in ['baseline', variant]}
    items = {arm: defaultdict(dict) for arm in records}
    for arm, recs in records.items():
        for rec in recs:
            for item in e.normalized_items(rec,include_context=True):
                items[arm][rec['case']['paper_id']][item['item_id']] = item
    scored = []
    problems = []
    retired_reference_ids = []
    reviews = []
    for pid, judgment in sorted(e.stage_results(stage).items()):
        ref = references[pid]['result']
        fact_ids = {f['fact_id'] for f in ref['central_facts']}
        initial_path=e.OUT/'references_reviewed/results'/(e.digest(pid)[:24]+'.json')
        known_fact_ids=fact_ids | {f['fact_id'] for f in e.read(initial_path)['result']['central_facts']}
        row = dict(paper_id=pid, family=papers[pid]['family'],
                   text_depth=papers[pid]['text_depth'], facts=len(fact_ids),
                   eligible=ref['eligible_for_requested_family'],
                   reference_issues=judgment['result']['reference_issues'], arms={})
        for letter in ['X', 'Y']:
            arm = mapping[pid][letter]
            score = judgment['result'][letter]
            sets = {k: set(score[k]) for k in ['covered_fact_ids', 'partially_covered_fact_ids', 'lost_qualification_fact_ids']}
            for key, values in sets.items():
                if values - known_fact_ids:
                    problems.append(dict(paper_id=pid, arm=arm, field=key, invalid_ids=sorted(values-known_fact_ids)))
                if (values & known_fact_ids)-fact_ids:
                    retired_reference_ids.append(dict(paper_id=pid,arm=arm,field=key,excluded_ids=sorted((values&known_fact_ids)-fact_ids)))
            full = sets['covered_fact_ids'] & fact_ids
            partial = (sets['partially_covered_fact_ids'] & fact_ids) - full
            errors = score['errors']
            invalid_errors = [r['item_id'] for r in errors if r['item_id'] not in items[arm][pid]]
            if invalid_errors:
                problems.append(dict(paper_id=pid, arm=arm, field='errors', invalid_ids=invalid_errors))
            material = [r for r in errors if r['severity'] == 'material']
            row['arms'][arm] = dict(full=len(full), partial=len(partial), missing=sorted(fact_ids-full-partial),
                fully_covered_ids=sorted(full), partial_ids=sorted(partial), material_errors=len(material),
                material_items=len({r['item_id'] for r in material}), errors=errors,
                item_count=len(items[arm][pid]), adequate=(len(full)==len(fact_ids) and not material),
                assessment=score['assessment'])
        scored.append(row)
        if (row['reference_issues'] or any(a['material_errors'] for a in row['arms'].values())
                or row['arms']['baseline']['full'] != row['arms'][variant]['full']):
            reviews.append(dict(**row, reference=ref,
                outputs={a:list(items[a][pid].values()) for a in items},
                source_text=papers[pid]['source_text']))
    summary = {}
    for family in ['all', 'primary', 'review', 'meta', 'guideline']:
        selected = [r for r in scored if family == 'all' or r['family'] == family]
        if not selected:
            continue
        by_arm = {}
        for arm in ['baseline', variant]:
            count = lambda key: sum(r['arms'][arm][key] for r in selected)
            facts = sum(r['facts'] for r in selected)
            by_arm[arm] = dict(papers=len(selected), facts=facts, fully_covered=count('full'),
                partially_covered=count('partial'), coverage_pct=round(100*count('full')/facts,2) if facts else None,
                material_error_papers=sum(bool(r['arms'][arm]['material_errors']) for r in selected),
                material_errors=count('material_errors'), material_items=count('material_items'),
                items=count('item_count'), all_central_facts_and_no_material_error=count('adequate'))
            negative=[r for r in selected if not r['eligible']]
            by_arm[arm]['no_eligible_finding_papers']=len(negative)
            by_arm[arm]['no_eligible_finding_with_material_error']=sum(bool(r['arms'][arm]['material_errors']) for r in negative)
        rng=random.Random(17026)
        differences=[]
        for _ in range(3000):
            draw=rng.choices(selected,k=len(selected))
            denominator=sum(r['facts'] for r in draw)
            if denominator:
                differences.append(100*sum(r['arms'][variant]['full']-r['arms']['baseline']['full'] for r in draw)/denominator)
        differences.sort()
        summary[family]=dict(arms=by_arm, coverage_delta_bootstrap_95pct=[round(differences[int(len(differences)*p)],2) for p in [.025,.975]] if differences else None,
            paired_coverage_improved=sum(r['arms'][variant]['full']>r['arms']['baseline']['full'] for r in selected),
            paired_coverage_worse=sum(r['arms'][variant]['full']<r['arms']['baseline']['full'] for r in selected),
            reference_issue_papers=sum(bool(r['reference_issues']) for r in selected))
    operational = {}
    for arm in ['baseline',variant]:
        raw=e.stage_results(split+'_'+arm)
        # Match the baseline cost to the candidate's family/paper cohort.
        selected_pids=set(mapping)
        matched=[r for r in raw.values() if r['paper_id'] in selected_pids]
        operational[arm]=dict(calls=len(matched), cost_usd=sum(r['cost_usd'] for r in matched),
            input_tokens=sum(r['usage']['input_tokens'] for r in matched),
            output_tokens=sum(r['usage']['output_tokens'] for r in matched),
            schema_error_calls=sum(bool(r['schema_errors']) for r in matched),
            mean_call_latency_seconds=sum(r['latency_seconds'] for r in matched)/len(matched) if matched else None)
    result=dict(split=split,variant=variant,summary=summary,operational=operational,
                invalid_judge_ids=problems,retired_reference_ids=retired_reference_ids,method='Anonymous Luna grading filtered by explicitly logged source/scope errata; AI-assisted references, not independent human gold.')
    e.save(e.OUT/stage/'summary.json',result)
    e.save(e.OUT/stage/'scores.json',scored)
    e.save(e.OUT/stage/'review_queue.json',reviews)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--split',required=True)
    parser.add_argument('--variant',required=True)
    args=parser.parse_args()
    print(json.dumps(summarize(args.split,args.variant),indent=2))
