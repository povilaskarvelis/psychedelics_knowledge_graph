from pathlib import Path
from types import SimpleNamespace
import json
import pytest
from pipeline.extract import run_review_relationship_batch_api as review, run_meta_analysis_v2_batch_api as meta
from pipeline.extract.task_contract_identity import secondary_contract_fingerprint

@pytest.mark.parametrize("module,filename",[(review,"paper_relationship_bundles.jsonl"),(meta,"meta_analysis_extractions.jsonl")])
def test_changed_task_same_doi_is_not_silently_reused(tmp_path,monkeypatch,module,filename):
    (tmp_path/"async_batches").mkdir();tasks=tmp_path/"tasks.jsonl"
    tasks.write_text(json.dumps({"task_id":"new-contract","study_doi":"10.1/a","task_status":"ready_for_model"})+'\n')
    (tmp_path/filename).write_text(json.dumps({"task_id":"old-contract","study_doi":"10.1/a","status":"ok"})+'\n')
    monkeypatch.setattr(module,"run_dir",lambda args:tmp_path)
    args=SimpleNamespace(tasks_jsonl=str(tasks),batch_id="batch2",retry_attempted=False,exclude_output_jsonl=[],shuffle=False,seed=1,batch_size=10,full_text_count=-1)
    assert len(module.selected_tasks(args))==1
    (tmp_path/filename).write_text(json.dumps({"task_id":"new-contract","study_doi":"10.1/a","status":"ok"})+'\n')
    assert module.selected_tasks(args)==[]

@pytest.mark.parametrize("family",["review","meta"])
def test_prompt_change_changes_secondary_contract(family,tmp_path):
    folder="review_relationships_v2" if family=="review" else "meta_analysis_v2"
    d=tmp_path/"docs/extraction_profiles"/folder;d.mkdir(parents=True)
    for n in ["abstract_extraction.md","full_text_extraction.md"]:(d/n).write_text(n)
    s=tmp_path/"schema";s.mkdir();name="review_relationships_v2.bundle.schema.json" if family=="review" else "meta_analysis_evidence_v2.schema.json";(s/name).write_text('{}')
    a=secondary_contract_fingerprint(family,root=tmp_path);(d/"abstract_extraction.md").write_text('new prompt')
    assert secondary_contract_fingerprint(family,root=tmp_path)!=a
