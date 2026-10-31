"""Rebuild canonical pending inputs after the scoped worker completes; no models."""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from pipeline import llm
import pandas as pd

D = ROOT / "data/processed/discovery/runs/pcp_scope_addition_20261019/downstream"
OUT = D / "canonical_input_refresh"


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    with Path(path).open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def main():
    assert read(D / "controller_state.json")["status"] == "complete_at_source_recovery_checkpoint"
    if (OUT / "manifest.json").exists() and read(llm.PIPELINE_STATE).get("extraction_input_refresh") == str(OUT):
        print("Canonical provisional input handoff already completed.")
        return
    OUT.mkdir(parents=True, exist_ok=True)
    paths = {
        "article_inputs": ROOT / "data/processed/extraction/fulltext_packets.jsonl",
        "primary_tasks": ROOT / "data/processed/extraction/route_extraction_tasks.jsonl",
        "review_tasks": ROOT / "data/processed/extraction/review_relationship_tasks/review_relationship_tasks.jsonl",
        "meta_analysis_tasks": ROOT / "data/processed/extraction/meta_analysis_v2_tasks/meta_analysis_v2_tasks.jsonl",
    }
    before = OUT / "before"
    before.mkdir(exist_ok=True)
    for label, path in paths.items():
        destination = before / (label + ".jsonl")
        if path.exists() and not destination.exists():
            shutil.copy2(path, destination)
    previous_state = OUT / "model_pipeline_state.before.json"
    if not previous_state.exists():
        shutil.copy2(llm.PIPELINE_STATE, previous_state)
    commands = [
        ("article_inputs", ["pipeline/fulltext/build_article_text_inputs.py", "--report-json", str(OUT / "article_inputs_report.json"),
            "--audit-csv", str(OUT / "article_inputs_audit.csv"), "--audit-md", str(OUT / "article_inputs_audit.md")]),
        ("primary_tasks", ["pipeline/extract/build_extraction_tasks.py", "--report-json", str(OUT / "primary_tasks_report.json")]),
        ("review_tasks", ["pipeline/extract/build_review_relationship_tasks.py"]),
        ("meta_analysis_tasks", ["pipeline/extract/build_meta_analysis_v2_tasks.py"]),
    ]
    for label, args in commands:
        marker = OUT / (label + ".complete.json")
        if marker.exists():
            continue
        cmd = [sys.executable, *args]
        print(label, flush=True)
        with (OUT / (label + ".log")).open("a") as log:
            result = subprocess.run(cmd, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
        if result.returncode:
            raise RuntimeError(f"{label} failed; inspect its log before resuming")
        llm.atomic_json(marker, {"command": cmd, "completed_at_utc": datetime.now(timezone.utc).isoformat()})
    task_dois = set()
    files = {}
    for label, path in paths.items():
        count = 0
        for line in path.open():
            if line.strip():
                count += 1
                if label != "article_inputs":
                    task_dois.add(json.loads(line)["study_doi"])
        files[label] = {"path": str(path), "sha256": sha(path), "rows": count}
    routes = pd.read_parquet(D / "extraction_routes.parquet")
    expected = set(routes.loc[routes.retained_for_extraction_candidate.fillna(False).astype(bool)
        & routes.route_action.isin(["extract_from_full_text", "extract_from_abstract_only"]), "doi"])
    assert expected <= task_dois, f"New retained papers missing canonical tasks: {sorted(expected-task_dois)[:15]}"
    manifest = {"status": "provisional_manual_fulltext_pending", "files": files,
        "pcp_increment_retained_papers_with_canonical_tasks": len(expected),
        "unique_task_dois_all_families": len(task_dois), "extraction_model_calls": 0,
        "generated_at_utc": datetime.now(timezone.utc).isoformat()}
    llm.atomic_json(OUT / "manifest.json", manifest)
    state = read(llm.PIPELINE_STATE)
    state["extraction_input_refresh"] = str(OUT)
    state["extraction_input_status"] = manifest["status"]
    state["extraction_input_freeze_sha256"] = sha(OUT / "manifest.json")
    state["extraction_status"] = "prepared_provisional_manual_fulltext_pending"
    state["extraction_cost_projection"]["valid_for_current_scope"] = False
    state["extraction_cost_projection"]["superseded_by_pcp_scope_addition"] = "pcp_scope_addition_20261019"
    state["screening_scope_additions"]["pcp_scope_addition_20261019"]["canonical_input_refresh"] = str(OUT / "manifest.json")
    state["manual_fulltext_review_pending"] = True
    llm.atomic_json(llm.PIPELINE_STATE, state)
    print(json.dumps({"canonical_task_papers": len(task_dois), "pcp_increment": len(expected), "model_calls": 0}))


if __name__ == "__main__":
    main()
