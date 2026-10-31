"""Apply reviewed extraction-design repairs without changing scientific screening.

The plan is an explicit record-level source/design adjudication, not an automatic
instruction to turn every wrong_source_type answer into a review. Original tasks
and answers remain immutable. Standard packet and task builders create retries.
This module never submits model requests.
"""
from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
from collections import defaultdict
from pathlib import Path

import pandas as pd

from pipeline.extract.build_extraction_routes import stable_id, prompt_profile_for, schema_profile_for
from pipeline.extract.build_extraction_tasks import task_from_route, expected_packet_profile_for_route
from pipeline.extract.build_review_relationship_tasks import build_task as review_task
from pipeline.extract.io_utils import read_jsonl, write_json
from pipeline.fulltext.build_llm_evidence_packets import build_packet


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replace_task_projection(path: Path, scope: set[str], additions: list[dict], receipt_path: Path) -> dict:
    """Replace reviewed DOIs only; preserve all unrelated JSONL bytes exactly."""
    if any(row['study_doi'] not in scope for row in additions):
        raise ValueError('A replacement task is outside the reviewed scope')
    if len({row['task_id'] for row in additions}) != len(additions):
        raise ValueError('Duplicate replacement task identities')
    if receipt_path.exists():
        result = json.loads(receipt_path.read_text())
        if sha(path) != result['after_sha256']:
            raise ValueError('Current projection changed after application; reconcile rather than overwrite')
        return result
    before_sha = sha(path)
    with path.open() as source:
        old_lines = list(source)
    kept, removed = [], []
    for index, line in enumerate(old_lines):
        row = json.loads(line)
        if row.get('study_doi') in scope:
            removed.append({'line_index': index, 'original_jsonl': line})
        else:
            kept.append(line)
    temporary = path.with_suffix(path.suffix + '.routing-repair.tmp')
    temporary.write_text(''.join(kept) + ''.join(json.dumps(row,ensure_ascii=False)+'\n' for row in additions))
    displaced = receipt_path.with_name(receipt_path.stem+'_displaced.jsonl')
    with displaced.open('w') as h:
        for row in removed:h.write(json.dumps(row,ensure_ascii=False)+'\n')
    temporary.replace(path)
    result = {'path':str(path.resolve()),'before_sha256':before_sha,'after_sha256':sha(path),
              'removed_tasks':len(removed),'added_tasks':len(additions),'unrelated_jsonl_bytes_preserved':True,
              'displaced_tasks':str(displaced.resolve())}
    write_json(receipt_path,result)
    return result


def exception_worklist(outputs: list[dict]) -> dict[str, list[dict]]:
    """Only wholly empty source-type exceptions are eligible for this repair."""
    by_doi = defaultdict(list)
    for row in outputs:
        result = row.get('result', {})
        doi = row.get('study_doi') or result.get('study_doi')
        if doi:
            by_doi[doi].append(row)
    return {doi: rows for doi, rows in by_doi.items()
            if any(r.get('result', {}).get('extraction_status') == 'wrong_source_type' for r in rows)
            and all(not r.get('result', {}).get(key) for r in rows
                    for key in ('items', 'relationships', 'synthesis_results', 'recommendation_items'))}


def validate_plan(plan: dict, exceptions: dict, selected_dois: set[str]) -> None:
    seen = set()
    for decision in plan['decisions']:
        doi = decision['doi']
        if doi in seen or doi not in exceptions or doi not in selected_dois:
            raise ValueError('Repair must identify one selected, wholly empty routing exception: ' + doi)
        seen.add(doi)
        if decision['action'] not in {'reroute_review', 'reroute_primary', 'hold_source_review', 'context_only'}:
            raise ValueError('Unsupported repair action')
        if not decision.get('reason') or not decision.get('evidence_artifact'):
            raise ValueError('Every routing repair requires explicit source/design evidence')
        if decision['action'] == 'reroute_primary' and not decision.get('domain_routes'):
            raise ValueError('Primary repair has no assigned profile')


def apply_route_owners(plan: dict, plan_path: Path, root: Path) -> dict:
    path = root / 'pipeline/extract/manual_extraction_route_overrides.json'
    receipt = plan_path.with_name(plan_path.stem + '_owner_application.json')
    if receipt.exists():
        saved = json.loads(receipt.read_text())
        if saved['plan_sha256'] != sha(plan_path):
            raise ValueError('Applied plan changed; use an explicit new revision')
        return saved
    before = plan_path.with_name(plan_path.stem + '_before_manual_route_owner.json')
    if before.exists():
        raise ValueError('Unreconciled previous owner application')
    before.write_bytes(path.read_bytes())
    payload = json.loads(path.read_text())
    metadata_path = root / 'data/curated/paper_metadata_overrides.json'
    metadata_payload = json.loads(metadata_path.read_text())
    plan_path.with_name(plan_path.stem + '_before_metadata_owner.json').write_bytes(metadata_path.read_bytes())
    for decision in plan['decisions']:
        record = next((r for r in payload['records'] if r.get('doi') == decision['doi']), None)
        if record is None:
            record = {'doi': decision['doi']}; payload['records'].append(record)
        else:
            record.setdefault('routing_repair_history', []).append(copy.deepcopy(record))
        record.update(manual_reason=decision['reason'], evidence_artifact=decision['evidence_artifact'],
                      reviewed_by='Codex_source_design_review', routing_repair_plan=str(plan_path.resolve()))
        if decision.get('metadata_fields'):
            entry = next((r for r in metadata_payload['records'] if r.get('doi') == decision['doi']), None)
            if entry is None:
                entry = {'doi': decision['doi'], 'fields': {}}; metadata_payload['records'].append(entry)
            entry.setdefault('fields', {}).update(decision['metadata_fields'])
            entry['evidence_basis'] = decision['reason'] + ' Evidence: ' + decision['evidence_artifact']
        if decision['action'] in {'hold_source_review', 'context_only'}:
            record['manual_action'] = decision['action']
        else:
            secondary = decision['action'] == 'reroute_review'
            record.update(manual_action='route_domains', manual_source_family='secondary_literature' if secondary else 'primary',
                          manual_source_type=decision.get('source_type', 'review' if secondary else 'primary'),
                          manual_domain_routes='general_topic_coverage' if secondary else ' | '.join(decision['domain_routes']),
                          manual_paper_type_reason=decision['reason'])
    temp = path.with_suffix('.json.tmp'); write_json(temp, payload); temp.replace(path)
    temp = metadata_path.with_suffix('.json.tmp'); write_json(temp, metadata_payload); temp.replace(metadata_path)
    result = {'plan': str(plan_path.resolve()), 'plan_sha256': sha(plan_path), 'owner_sha256': sha(path),
              'records': len(plan['decisions']), 'screening_changed': False}
    write_json(receipt, result)
    return result


def prepare_repair_tasks(plan: dict, frozen_inputs: Path, out_dir: Path) -> dict:
    """Regenerate appropriate packets and stable standard tasks for reviewed DOIs."""
    out_dir.mkdir(parents=True, exist_ok=False)
    routes = pd.read_parquet(frozen_inputs/'paper_extraction_routes.parquet')
    candidates = pd.read_parquet(frozen_inputs/'candidate_papers.parquet')
    wanted = {d['doi'] for d in plan['decisions']}
    meta = {str(r['doi']): r for r in candidates[candidates.doi.isin(wanted)].to_dict('records')}
    old_tasks = defaultdict(list)
    for family in ('primary', 'meta'):
        for task in read_jsonl(frozen_inputs/f'{family}_tasks.jsonl'):
            if task['study_doi'] in wanted:
                old_tasks[task['study_doi']].append(task)
    # Read only the source packets linked by the frozen task records.
    paths = set()
    for tasks in old_tasks.values():
        for task in tasks:
            source = task.get('text_source', task.get('source', {}))
            path = source.get('packet_source_path') or source.get('packet_path')
            if path: paths.add(Path(path))
    previous_packets = {}
    for path in paths:
        with path.open() as source:
            for line in source:
                packet = json.loads(line)
                doi = packet.get('study_doi')
                if doi in wanted:
                    previous_packets.setdefault(doi, packet)
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    packet_path = out_dir/'packets.jsonl'
    packets, source_receipts, repaired_routes = [], [], []
    primary_tasks, review_tasks = [], []
    for decision in plan['decisions']:
        if not decision['action'].startswith('reroute_'): continue
        doi = decision['doi']; secondary = decision['action'] == 'reroute_review'
        current = routes[routes.doi.eq(doi)].to_dict('records')
        if not current: raise ValueError('Missing frozen route: ' + doi)
        template = copy.deepcopy(next((r for r in current if r.get('route_action') == 'extract_from_full_text'), current[0]))
        metadata = copy.deepcopy(meta[doi]); metadata.update(decision.get('metadata_fields', {}))
        source_type = decision.get('source_type', 'review' if secondary else 'primary')
        source_family = 'secondary_literature' if secondary else 'primary'
        domains = ['general_topic_coverage'] if secondary else decision['domain_routes']
        packet = None
        original = previous_packets.get(doi)
        if template.get('route_action') == 'extract_from_full_text':
            if original is None: raise ValueError('Fulltext route has no verified frozen source packet: ' + doi)
            artifact_path = Path(decision.get('artifact_path_override') or original['fulltext_provenance']['artifact_path'])
            profile = 'review_coverage' if secondary else 'primary_empirical'
            # Same identity-accepted artifact, appropriate section selection.
            packet = build_packet('article', artifact_path, json.loads(artifact_path.read_text()),
                                  {**metadata, 'source_family': source_family}, max_chunk_chars=6000,
                                  overlap_chars=300, max_chunks_per_paper=0, max_references=200,
                                  include_section_text=False, include_candidate_contexts=False, packet_profile=profile)
            if not packet.get('llm_chunks'): raise ValueError('Regenerated article packet is empty: ' + doi)
            packets.append(packet)
            source_receipts.append({'doi': doi, 'artifact_path': str(artifact_path), 'artifact_sha256': sha(artifact_path),
                                    'old_packet_profile': original.get('packet_profile'), 'new_packet_profile': profile,
                                    'document_summary': packet['document_summary'], 'identity_basis': 'same artifact as frozen validated extraction task'})
        for domain in domains:
            route = copy.deepcopy(template)
            prompt = prompt_profile_for(source_family, source_type, domain)
            route.update(source_family=source_family, source_type=source_type, domain_route=domain,
                         prompt_profile=prompt, schema_profile=schema_profile_for(prompt),
                         paper_type_reason=decision['reason'], domain_route_basis=decision['reason'])
            route['route_id'] = stable_id(doi, source_family, source_type, domain, route.get('access_tier', ''), prompt)
            repaired_routes.append(route)
            if secondary:
                depth = 'article_text' if packet else 'abstract_only'
                review_tasks.append(review_task({'doi': doi, 'review_type': source_type, 'text_depth': depth}, metadata, packet, packet_path))
            else:
                task = task_from_route(route, metadata_by_doi={doi: metadata},
                                       packets_by_doi={doi: [{**packet, '_packet_source_path': str(packet_path.resolve())}]} if packet else {},
                                       generated_at_utc=now, include_packet_content=False)
                primary_tasks.append(task)
    for name, rows in [('packets', packets), ('primary_tasks', primary_tasks), ('review_tasks', review_tasks)]:
        with (out_dir/f'{name}.jsonl').open('w') as h:
            for row in rows: h.write(json.dumps(row, ensure_ascii=False, default=str)+'\n')
    pd.DataFrame(repaired_routes).to_parquet(out_dir/'repaired_routes.parquet', index=False)
    write_json(out_dir/'source_receipts.json', source_receipts)
    result = {'primary_tasks': len(primary_tasks), 'review_tasks': len(review_tasks),
              'rerun_papers': len({t['study_doi'] for t in primary_tasks+review_tasks}),
              'held_or_context_papers': sum(not d['action'].startswith('reroute_') for d in plan['decisions']),
              'model_calls': 0, 'screening_changed': False}
    write_json(out_dir/'preparation.json', result)
    return result


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'apply'])
    parser.add_argument('--plan', required=True, type=Path)
    parser.add_argument('--frozen-inputs', required=True, type=Path)
    parser.add_argument('--out-dir', type=Path)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text())
    outputs = [row for family in ('primary', 'review', 'meta')
               for row in read_jsonl(args.frozen_inputs/f'{family}_outputs.jsonl')]
    frame = pd.read_parquet(args.frozen_inputs/'candidate_papers.parquet')
    selected = set(frame.loc[frame.retained_for_extraction_candidate.fillna(False).astype(bool), 'doi'])
    validate_plan(plan, exception_worklist(outputs), selected)
    if args.action == 'apply':
        result = apply_route_owners(plan, args.plan, args.root)
    else:
        if args.out_dir is None: parser.error('prepare requires --out-dir')
        result = prepare_repair_tasks(plan, args.frozen_inputs, args.out_dir)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
