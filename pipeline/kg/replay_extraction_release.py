"""Rebuild a staged graph from frozen standard extraction inputs, without LLMs.

This is the common replay path for normalization-only changes and incremental
extraction releases. It records input/code identities, resumes completed stages
only when those identities still match, and never changes a deployment pointer.
"""
from __future__ import annotations
import argparse
import ast
import datetime as dt
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]


def execution_dependencies(root: Path=ROOT) -> list[Path]:
    """Archive local import closure plus KG dynamic modules and graph schemas."""
    pending=list((root/'pipeline/kg').glob('*.py'));seen=set()
    while pending:
        path=pending.pop()
        if path in seen or not path.is_file():continue
        seen.add(path)
        for node in ast.walk(ast.parse(path.read_text())):
            names=[]
            if isinstance(node,ast.Import):names=[n.name for n in node.names]
            elif isinstance(node,ast.ImportFrom) and node.module:
                names=[node.module]+[node.module+'.'+n.name for n in node.names]
            for name in names:
                if not name.startswith('pipeline.'):continue
                candidate=root/(name.replace('.','/')+'.py')
                if candidate.is_file() and candidate not in seen:pending.append(candidate)
    return sorted(seen|{p for p in (root/'schema').rglob('*.json') if p.is_file()})


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replay(source_release: Path, out: Path, run_id: str) -> dict:
    if not run_id or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in run_id):
        raise ValueError('Use a plain unique run identifier')
    source_release=source_release.resolve();out=out.resolve();I=out/'inputs'
    manifest_path=out/'input_manifest.json'
    if not manifest_path.exists():
        if out.exists() and any(out.iterdir()):raise ValueError('Output directory must be empty for a new replay')
        I.mkdir(parents=True,exist_ok=True)
        for p in sorted((source_release/'inputs').iterdir()):
            if p.is_file():shutil.copy2(p,I/p.name)
        shutil.copy2(source_release/'selected_dois.txt',out/'selected_dois.txt')
        inputs=[{'path':str(p),'source':str(source_release/'inputs'/p.name),'sha256':sha(p)} for p in I.iterdir() if p.is_file()]
        inputs.append({'path':str(out/'selected_dois.txt'),'source':str(source_release/'selected_dois.txt'),'sha256':sha(out/'selected_dois.txt')})
        sources=execution_dependencies()
        execution=[]
        for p in sources:
            dest=out/'execution_sources'/p.relative_to(ROOT);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dest)
            execution.append({'path':str(p),'snapshot':str(dest),'sha256':sha(p)})
        manifest={'source_release':str(source_release),'run_id':run_id,'input_assets':inputs,'execution_sources':execution,
                  'new_model_calls':0,'deployment_pointer_changed':False,'screening_changed':False}
        manifest_path.write_text(json.dumps(manifest,indent=2))
    manifest=json.loads(manifest_path.read_text())
    if manifest['source_release']!=str(source_release) or manifest['run_id']!=run_id:raise ValueError('Replay identity changed')
    def verify():
        for item in manifest['input_assets']+manifest['execution_sources']:
            if sha(Path(item['path']))!=item['sha256']:raise ValueError('Replay dependency changed: '+item['path'])
    verify();py=sys.executable
    evidence=ROOT/'data/processed/extraction/routed_runs'/run_id
    if evidence.exists() and not (out/'assemble_completion.json').exists() and any(evidence.iterdir()):
        raise ValueError('Run identifier already has unrelated extraction artifacts')
    commands=[
      ('convert_primary',[py,'-m','pipeline.kg.convert_routed_extractions_to_evidence_rows','--input-jsonl',str(I/'primary_outputs.jsonl'),'--tasks-jsonl',str(I/'primary_tasks.jsonl'),'--active-route-table',str(I/'paper_extraction_routes.parquet'),'--out-json',str(out/'primary_evidence.json'),'--report-json',str(out/'primary_conversion_report.json')]),
      ('convert_reviews',[py,'-m','pipeline.kg.convert_review_relationship_bundles_to_evidence_rows','--bundles-jsonl',str(I/'review_outputs.jsonl'),'--tasks-jsonl',str(I/'review_tasks.jsonl'),'--registry-json',str(I/'entity_registry.json'),'--candidate-parquet',str(I/'candidate_papers.parquet'),'--out-json',str(out/'review_evidence.json'),'--report-json',str(out/'review_conversion_report.json')]),
      ('convert_meta',[py,'-m','pipeline.kg.convert_meta_analysis_v2_to_evidence_rows','--input-jsonl',str(I/'meta_outputs.jsonl'),'--tasks-jsonl',str(I/'meta_tasks.jsonl'),'--out-json',str(out/'meta_evidence.json'),'--report-json',str(out/'meta_conversion_report.json')]),
      ('assemble',[py,'-m','pipeline.kg.assemble_combined_release','--run-id',run_id,'--base-evidence',str(out/'primary_evidence.json'),'--evidence-overlay','reviews='+str(out/'review_evidence.json'),'--evidence-overlay','meta='+str(out/'meta_evidence.json'),'--base-outputs',str(I/'primary_outputs.jsonl'),'--output-overlay','reviews='+str(I/'review_outputs.jsonl'),'--output-overlay','meta='+str(I/'meta_outputs.jsonl'),'--candidate-table',str(I/'candidate_papers.parquet'),'--doi-alias-registry',str(I/'doi_alias_registry.json'),'--metadata-overrides',str(I/'paper_metadata_overrides.json'),'--required-output-dois',str(out/'selected_dois.txt'),'--out-dir',str(evidence)]),
      ('normalize',[py,'-m','pipeline.kg.build_evidence_tables','--source-preset','routed','--run-id',run_id,'--registry',str(I/'entity_registry.json'),'--doi-alias-registry',str(I/'doi_alias_registry.json'),'--skip-duckdb'])]
    for stage,command in commands:
        verify();marker=out/(stage+'_completion.json')
        if marker.exists():print('PRESERVED_COMPLETED',stage,flush=True);continue
        print('START',stage,flush=True)
        with (out/(stage+'.log')).open('w') as log:process=subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
        record={'stage':stage,'command':command,'exit_code':process.returncode,'at_utc':dt.datetime.now(dt.timezone.utc).isoformat()}
        (out/(stage+('_completion.json' if process.returncode==0 else '_failure.json'))).write_text(json.dumps(record,indent=2))
        if process.returncode:raise RuntimeError('Replay failed at '+stage+'; inspect saved log')
    verify();result={'complete':True,'run_id':run_id,'source_release':str(source_release),'new_model_calls':0,'deployment_pointer_changed':False,'screening_changed':False}
    (out/'replay_completion.json').write_text(json.dumps(result,indent=2));return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source-release',type=Path,required=True);p.add_argument('--out-dir',type=Path,required=True);p.add_argument('--run-id',required=True)
    args=p.parse_args();print(json.dumps(replay(args.source_release,args.out_dir,args.run_id),indent=2))

if __name__=='__main__':main()
