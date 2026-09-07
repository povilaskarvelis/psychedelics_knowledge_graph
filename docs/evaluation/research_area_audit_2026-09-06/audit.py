"""Read-only, reproducible semantic-routing triage of the active local KG.

Run from the repository root. Requires pandas/pyarrow. Never changes graph data.
Rules select candidates, NOT errors. manual_judgments.json records reviewed errors.
Unselected/unadjudicated rows are not thereby certified correct.
"""
import hashlib
import json
import re
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
active_path = ROOT / 'data/processed/graph_payload_active.json'
active = json.loads(active_path.read_text())
kg = ROOT / 'data/processed/kg_routed_runs' / active['run_id']
source = kg / 'findings.parquet'
df = pd.read_parquet(source).fillna('')
columns = ['finding_id', 'study_doi', 'compound', 'entity_label', 'domain', 'evidence_type',
           'entity_role', 'support', 'outcome_measure', 'population', 'study_design',
           'graph_admission_status', 'kg_entity_kind_override', 'paper_type', 'endpoint_label_source',
           'graph_overview_subjects_json', 'graph_parent_label', 'proposition_group_id']
rows = df.loc[df.graph_admission_status.eq('main_graph'), columns].to_dict('records')
condition = [r for r in rows if r['kg_entity_kind_override'] == 'condition_indication']
def hit(pattern, text): return bool(re.search(pattern, text, re.I))
def save(name, value): (OUT / name).write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')
initial_pattern = r'precipitat|retract|induc.{0,35}(mania|psychosis|cystitis|parkinson|suicid|schizophren)|(?:develop|onset|exacerbat|trigger).{0,60}(?:after|following|use|exposure)|(?:use|exposure).{0,60}(?:risk of|onset|develop|suicid|uropathy)|(?:abuse|recreational|dependent users|chronic users)|(?:model of|mimic).{0,30}schizophren'
a = [r for r in condition if hit(initial_pattern, r['support']) or r['entity_label'] == 'Ketamine-associated uropathy' or r['entity_role'] == 'population']
seen = {r['finding_id'] for r in a}
b = []
for r in rows:
    if r['finding_id'] in seen: continue
    rules = []
    if r['kg_entity_kind_override'] == 'condition_indication':
        if hit(r'adverse|tolerab|side.effect|safety|manic|hypomani|mania|toxicit|cystitis|mortality|deaths?|hospitaliz|psychotic|psychosis|worsen|exacerbat|dependence liability|abuse potential', r['support']): rules.append('condition_safety')
        if hit(r'model.{0,30}schizophren|schizophren.{0,30}model|healthy.{0,20}(?:volunteer|subject)|(?:patients|participants).{0,30}(?:excluded|contraindicat)|contraindicat|retract', r['support']): rules.append('condition_context')
    elif r['entity_role'] in ['population','comparator','safety_event','safety_or_adverse_event'] and r['kg_entity_kind_override'] != 'safety_adverse_event': rules.append('explicit_role_mismatch')
    if rules: b.append(r | {'rules': rules})
c = []
for r in rows:
    k, s = r['kg_entity_kind_override'], r['support']; rules = []
    if k == 'safety_adverse_event' and hit(r'(?:remission|antidepressant response|treat(?:ment of|ing) (?:depression|ptsd|anxiety)|reduced depressive symptoms)', s) and not hit(r'adverse|side.effect|safe|tolerab|risk|toxicit|induc|emergen|switch|no |not |without|neuroprotect', s): rules.append('safety_therapeutic_language')
    if k in ['cognitive_behavioral_construct','subjective_experience_construct','pathway_process','biomarker_readout','brain_region','brain_network','pharmacokinetic_parameter'] and hit(r'(?:fatal|life.threatening|requiring hospital|acute kidney injury|liver failure|suicide attempt|severe manic episode)', s): rules.append('harm_outside_safety')
    if k in ['target','system_family'] and hit(r'^(?:BDNF|Cortisol|C-reactive protein|Interleukin|TNF|IL-6|Glutamate levels)', r['entity_label']): rules.append('readout_as_target')
    if rules: c.append(r | {'rules': rules})
p = [r for r in rows if r['entity_label'] == 'Psychosis risk' and hit(r'improv|remission|antidepress|reduc.{0,25}(?:depress|suicid)|suicid.{0,40}resolved',r['support'])]
for name, subset in [('condition_candidates_initial',a),('additional_candidates',b),('cross_area_candidates',c),('psychosis_candidates',p)]: save(name+'.json',subset)
candidates = {r['finding_id']: r for r in a+b+c+p}
judgments = {r['finding_id']:r for r in json.loads((OUT/'manual_judgments.json').read_text())}
assert judgments.keys() <= candidates.keys(), 'Judgments no longer match current active inputs'
edge_sets = {}
for source_name, path in active['active_graph_bootstraps'].items():
    edges = json.loads((ROOT/path).read_text())['edges']
    edge_sets[source_name] = {(e['compound'], e['entity_label'], e['entity_kind']) for e in edges}
def source_for(r):
    if r['paper_type'] == 'meta_analysis': return 'meta_analyses'
    return 'primary' if r['evidence_type']=='primary_evidence' else 'reviews'
def has_edge(r):
    subjects = json.loads(r['graph_overview_subjects_json'] or '[]')
    labels = {r['entity_label'], r['graph_parent_label']}
    return any((s['label'],label,r['kg_entity_kind_override']) in edge_sets[source_for(r)] for s in subjects for label in labels if label)
queue = []
for fid, r in candidates.items():
    queue.append(r | {'assessment':'high_confidence_semantic_misclassification' if fid in judgments else 'not_confirmed_by_this_audit',
                      'matching_edge_in_active_bootstrap':has_edge(r)} | judgments.get(fid,{}))
confirmed = pd.DataFrame([r for r in queue if r['finding_id'] in judgments])
confirmed['source_partition'] = confirmed.apply(source_for,axis=1)
# Exact duplicates here are normalized finding statements, not source-paper findings.
statement_key = ['study_doi','compound','entity_label','support']
summary = {
    'run_id':active['run_id'], 'release_id':active['release_id'],
    'scope':'Active local release. Not a fresh download or verification of the live production release.',
    'findings_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
    'total_normalized_rows':len(df), 'main_graph_admitted_rows':len(rows),
    'condition_rows_all':int(df.kg_entity_kind_override.eq('condition_indication').sum()),
    'condition_rows_main_graph':len(condition),
    'candidate_rows':len(candidates), 'high_confidence_rows':len(confirmed),
    'distinct_dois':int(confirmed.study_doi.nunique()),
    'distinct_statement_keys':len(confirmed.drop_duplicates(statement_key)),
    'condition_high_confidence_rows':int(confirmed.kg_entity_kind_override.eq('condition_indication').sum()),
    'rows_with_matching_bootstrap_edge':int(confirmed.matching_edge_in_active_bootstrap.sum()),
    'distinct_compound_entity_kind_pairs':len(confirmed.drop_duplicates(['compound','entity_label','kg_entity_kind_override'])),
    'by_category':confirmed.category.value_counts().to_dict(),
    'by_source':confirmed.source_partition.value_counts().to_dict(),
    'by_current_entity_kind':confirmed.kg_entity_kind_override.value_counts().to_dict(),
    'by_compound':confirmed.compound.value_counts().to_dict(),
    'limits':['Heuristic census plus manual targeted semantic review, not exhaustive full-text adjudication or a prevalence estimate.',
              'A matching bootstrap edge establishes that the concept link is exported, not that every individual row survives all UI filters.',
              'Counts are normalized rows, not independent experiments. Exact repeated statement keys are also reported.',
              'Other candidates include legitimate rows and unresolved mixed-role findings; not_confirmed does not mean correct.']}
save('summary.json',summary)
save('review_queue.json',queue)
confirmed.to_csv(OUT/'high_confidence_findings.csv',index=False)
pd.DataFrame(queue).to_csv(OUT/'review_queue.csv',index=False)
print(json.dumps(summary,indent=2))
