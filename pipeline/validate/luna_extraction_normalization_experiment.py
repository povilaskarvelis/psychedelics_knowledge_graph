"""Cross fixed extraction outputs with old/repaired normalization, in staging."""
from __future__ import annotations
import argparse
import ast
from collections import Counter,defaultdict
from contextlib import contextmanager
import copy
import json
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
import pandas as pd
from pipeline.validate import luna_extraction_comparison as experiment
from pipeline.extract import run_meta_analysis_v2_batch_api as meta
from pipeline.extract.io_utils import normalize
from pipeline.kg import convert_meta_analysis_v2_to_evidence_rows as meta_converter
from pipeline.kg import convert_routed_extractions_to_evidence_rows as primary_converter
from pipeline.kg import convert_review_relationship_bundles_to_evidence_rows as review_converter
from pipeline.kg.build_evidence_tables import build_tables,DEFAULT_REGISTRY_PATH

OUT=experiment.OUT


def old_multiple_estimates():
    tree=ast.parse((OUT/'normalization_before/run_meta_analysis_v2_batch_api.py').read_text())
    function=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='result_bundles_multiple_estimates')
    namespace={'normalize':normalize,'re':re}
    exec(compile(ast.Module(body=[function],type_ignores=[]),'<frozen_old_check>','exec'),namespace)
    return namespace[function.name]


@contextmanager
def use_checks(mode):
    original=(meta.result_bundles_multiple_estimates,meta_converter.result_bundles_multiple_estimates)
    if mode not in {'statistical','repaired','safe'}:meta.result_bundles_multiple_estimates=meta_converter.result_bundles_multiple_estimates=old_multiple_estimates()
    try:yield
    finally:meta.result_bundles_multiple_estimates,meta_converter.result_bundles_multiple_estimates=original


def build(records,label,mode):
    folder=OUT/'normalization'/label/mode
    folder.mkdir(parents=True,exist_ok=True)
    grouped=defaultdict(list)
    for rec in records:grouped[rec['case']['family']].append(rec)
    all_rows=[];reports={}
    with use_checks(mode):
        for family,recs in grouped.items():
            tasks=[r['case']['task'] for r in recs];envelopes=[]
            for rec in recs:
                c=rec['case'];result=rec['result'];flags=[]
                if family=='meta':flags=meta.semantic_qa_flags(result,c['text_depth'])+meta.result_quality_flags(result,c['source_text'])
                elif family=='review':flags=experiment.review.bundle_semantic_errors(result)
                envelopes.append(dict(task_id=c['case_id'],route_id=c['task'].get('route_id',''),input_fingerprint=c['task'].get('input_fingerprint',''),study_doi=c['study_doi'],text_depth=c['text_depth'],source_depth=c['text_depth'],status='schema_error' if rec['record'].get('schema_errors') else 'ok',result=result,qa_flags=flags,model='gpt-6-luna'))
            if family in {'primary','guideline'}:
                experiment.write_rows(folder/f'{family}_outputs.jsonl',envelopes)
                experiment.write_rows(folder/f'{family}_tasks.jsonl',tasks)
                evidence,report=primary_converter.convert_outputs(input_jsonl=folder/f'{family}_outputs.jsonl',tasks_jsonl=folder/f'{family}_tasks.jsonl')
            elif family=='meta':evidence,report=meta_converter.convert_outputs(envelopes,{t['task_id']:t for t in tasks})
            else:evidence,report=review_converter.convert_bundles(envelopes,tasks,experiment.read(DEFAULT_REGISTRY_PATH),active_candidate_dois={t['study_doi'] for t in tasks},project_secondary_named_anchors=mode in {'secondary','repaired'})
            all_rows.extend(evidence);reports[family]=report
    experiment.save(folder/'evidence_rows.json',all_rows)
    vocab=ROOT/'schema/kg_node_vocabularies.json' if mode in {'circuit','safe','repaired'} else OUT/'normalization_before/kg_node_vocabularies.json'
    manifest=build_tables(graph_sources={'routed_extractions':dict(path=folder/'evidence_rows.json',domain='routed',dataset='routed',default_evidence_type='primary_evidence',skip_audit=True)},node_vocabulary_path=vocab,out_dir=folder/'kg',write_duckdb=False)
    findings=pd.read_parquet(folder/'kg/findings.parquet')
    audit=pd.read_parquet(folder/'kg/normalization_audit.parquet')
    summary=dict(label=label,mode=mode,input_tasks=len(records),converted_rows=len(all_rows),conversion=reports,findings=len(findings),papers=findings.study_doi.nunique() if len(findings) else 0,admission=manifest['graph_admission_counts'],audit=audit.normalization_status.value_counts().to_dict() if len(audit) else {},propositions=manifest['proposition_summary'])
    experiment.save(folder/'summary.json',summary)
    return findings,summary


def finding_key(row):
    raw=json.loads(row['raw_row_json'])
    return (row['study_doi'],raw.get('source_item_type'),str(raw.get('source_item_id') or raw.get('source_item_index')),row['compound'],row['entity_label'],row['domain'],row['graph_admission_status'])


def compare(records,label,mode='repaired'):
    old,old_summary=build(records,label,'old');new,new_summary=build(records,label,mode)
    before={finding_key(r):r for r in old.to_dict('records')};after={finding_key(r):r for r in new.to_dict('records')}
    added=[after[k] for k in after.keys()-before.keys()];removed=[before[k] for k in before.keys()-after.keys()]
    delta=dict(label=label,mode=mode,old={k:v for k,v in old_summary.items() if k!='conversion'},repaired={k:v for k,v in new_summary.items() if k!='conversion'},added_findings=len(added),removed_findings=len(removed),changed_papers=sorted({r['study_doi'] for r in added+removed}))
    suffix='' if mode=='repaired' else '_'+mode
    experiment.save(OUT/'normalization'/label/('added_findings'+suffix+'.json'),added)
    experiment.save(OUT/'normalization'/label/('removed_findings'+suffix+'.json'),removed)
    experiment.save(OUT/'normalization'/label/('comparison'+suffix+'.json'),delta)
    return delta


def historical_records():
    bench=ROOT/'data/processed/evaluation/model_head_to_head_20261016'
    cases={c['case_id']:c for c in experiment.rows(bench/'cases.jsonl')}
    out=[]
    for path in sorted((bench/'matched/results').glob('*.json')):
        r=experiment.read(path)
        if r.get('arm')!='luna' or r['family']=='screening':continue
        c=cases[r['case_id']]
        c=dict(case_id=c['task']['task_id'],paper_id=r['case_id'],family=c['family'],task=c['task'],study_doi=c['study_doi'],domain=c.get('domain','all_paper_domains'),text_depth=c['text_depth'],source_text=c['content'].split('ARTICLE_TEXT:\n' if c['text_depth']=='article_text' else 'ABSTRACT_TEXT:\n',1)[-1])
        out.append(dict(case=c,record=r,result=r['result']))
    assert len(out)==120
    return out


def main():
    p=argparse.ArgumentParser();p.add_argument('--split',choices=['historical','development','holdout'],default='historical');p.add_argument('--variant',default='baseline');p.add_argument('--mode',choices=['repaired','safe','statistical','circuit','secondary'],default='repaired');a=p.parse_args()
    records=historical_records() if a.split=='historical' else experiment.extraction_records(a.split,a.variant)
    if not records:raise ValueError('No extraction outputs to replay')
    result=compare(records,a.split+'_'+a.variant,a.mode)
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
