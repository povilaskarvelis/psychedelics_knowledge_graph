#!/usr/bin/env python3
"""Resume this approved increment through existing pipeline stages, never extraction.

Run from the repository root with the project's Python 3.12 environment.
Stages, commands, receipts and model submissions are durable and resumable.
Screening uses title/abstract records, not retrieved full text or Codex judgments.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import pandas as pd
from pipeline import llm
from pipeline.review import run_domain_routing as screening
from pipeline.review import run_domain_routing_batch as batch

RUN_ID = "pcp_scope_addition_20261019"
RUN = ROOT / "data/processed/discovery/runs" / RUN_ID
D = RUN / "downstream"
FT = D / "fulltext"
SCOPE = D / "scope_dois.txt"
BASE = D / "baseline"
INPUTS = D / "inputs"
INSTRUCTION = INPUTS / "title_abstract_screening_v5_pcp.md"
STATE = D / "controller_state.json"
PYTHON = sys.executable


def now():
    return datetime.now(timezone.utc).isoformat()


def read(path):
    return json.loads(Path(path).read_text())


def save(path, value):
    llm.atomic_json(Path(path), value)


def sha(path):
    with Path(path).open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def update(**fields):
    state = read(STATE) if STATE.exists() else {"run_id": RUN_ID, "done": []}
    state.update(fields, updated_at_utc=now())
    save(STATE, state)
    return state


def command(stage, script, *args):
    state = read(STATE) if STATE.exists() else {"done": []}
    if stage in state["done"]:
        return
    update(status="running", stage=stage)
    cmd = [PYTHON, str(ROOT / script), *map(str, args)]
    log = D / "logs" / (stage + ".log")
    log.parent.mkdir(parents=True, exist_ok=True)
    receipt = {"stage": stage, "command": cmd, "started_at_utc": now()}
    print(f"{now()} {stage}", flush=True)
    with log.open("a") as handle:
        result = subprocess.run(cmd, cwd=ROOT, stdout=handle, stderr=subprocess.STDOUT)
    receipt.update(ended_at_utc=now(), exit_code=result.returncode, log=str(log))
    save(log.with_suffix(".receipt.json"), receipt)
    if result.returncode:
        raise RuntimeError(f"{stage} exited {result.returncode}; see {log}")
    state = update()
    state["done"].append(stage)
    save(STATE, state)


def batch_paths(name):
    folder = D / "screening" / name
    folder.mkdir(parents=True, exist_ok=True)
    return {k: folder / v for k, v in {
        "requests": "requests.jsonl", "manifest": "manifest.json", "job": "job.json",
        "results": "results.jsonl", "raw": "raw.jsonl", "routes": "routes.parquet",
        "summary": "summary.json", "counts": "counts.csv", "report": "parse_report.json",
    }.items()}


def finish_batch(name, doi_file):
    paths = batch_paths(name)
    if not paths["manifest"].exists():
        command(name + "_prepare", "pipeline/review/run_domain_routing_batch.py", "prepare",
            "--candidate-table", INPUTS / "candidate_scope.parquet",
            "--metadata-table", INPUTS / "metadata_scope.parquet",
            "--prescreen-decisions-table", INPUTS / "prescreen_scope.parquet",
            "--doi-file", doi_file, "--screening-profile", "v5_class_scope",
            "--screening-instruction-file", INSTRUCTION,
            "--model", "gpt-6-luna", "--max-output-tokens", "2048",
            "--batch-input-jsonl", paths["requests"], "--manifest-json", paths["manifest"],
            "--raw-jsonl", paths["raw"])
    bodies = [json.loads(line)["body"] for line in paths["requests"].open()]
    assert bodies and all(x["model"] == "gpt-6-luna" and x["reasoning"]["effort"] == "low" for x in bodies)
    assert all(x["instructions"] == INSTRUCTION.read_text().strip() for x in bodies)
    projection = {
        "requests": len(bodies), "request_bytes": paths["requests"].stat().st_size,
        "reservation_ceiling_usd": sum(llm.reservation_cost(x, batch=True) for x in bodies),
        "approximate_input_tokens_char4": sum((len(x["instructions"]) + len(x["input"]) + len(json.dumps(x["text"]))) / 4 for x in bodies),
        "instruction_sha256": hashlib.sha256(INSTRUCTION.read_text().strip().encode()).hexdigest(),
        "batch_discount": True, "extraction_calls": 0,
    }
    save(paths["requests"].with_suffix(".cost.json"), projection)
    print(name, "requests", len(bodies), "reservation ceiling", round(projection["reservation_ceiling_usd"], 4), flush=True)
    api = llm.client(batch.api_key_from_env(type("Args", (), {"env_file": str(ROOT / ".env")})(), required=True))
    if not paths["job"].exists():
        llm.submit(api, requests_path=paths["requests"], job_path=paths["job"], metadata={"stage": "screening", "model": "gpt-6-luna", "run_id": RUN_ID})
    job_id = read(paths["job"]).get("job_name")
    if not job_id:
        raise RuntimeError("Submission receipt requires reconciliation; never repeat an uncertain paid submission")
    update(stage=name + "_batch", batch_job=job_id)
    last = None
    while True:
        job = api.batches.retrieve(job_id)
        snapshot = job.model_dump(mode="json")
        save(paths["job"].with_name("latest_status.json"), snapshot)
        progress = (job.status, json.dumps(snapshot.get("request_counts", {}), sort_keys=True))
        if progress != last:
            print(now(), name, progress, flush=True)
            last = progress
        if job.status in llm.TERMINAL_STATES:
            break
        time.sleep(30)
    if not paths["results"].exists():
        llm.download(api, job, paths["results"])
    if not paths["report"].exists():
        args = type("Args", (), dict(
            batch_output_jsonl=str(paths["results"]), manifest_json=str(paths["manifest"]),
            raw_jsonl=str(paths["raw"]), output_table=str(paths["routes"]),
            summary_json=str(paths["summary"]), counts_csv=str(paths["counts"]), report_json=str(paths["report"]),
            candidate_table=str(INPUTS / "candidate_scope.parquet"), metadata_table=str(INPUTS / "metadata_scope.parquet"),
            prescreen_decisions_table=str(INPUTS / "prescreen_scope.parquet"), env_file=str(ROOT / ".env"), model="gpt-6-luna"))()
        batch.parse_batch_results(args)
    return paths


def build_worklist(label):
    command("worklist_" + label, "pipeline/fulltext/build_fulltext_enrichment_worklist.py",
        "--queue-json", D / "queue.json", "--include-previously-processed",
        "--output-selected-dois", FT / "selected_dois.txt", "--output-enrichment-dois", FT / "enrichment_dois.txt",
        "--output-access-metadata-refresh-dois", FT / "access_refresh_dois.txt",
        "--output-no-accessible-fulltext-dois", FT / "no_accessible_fulltext_dois.txt",
        "--output-oa-landing-dois", FT / "oa_landing_dois.txt",
        "--output-table", FT / "worklist.parquet", "--report-json", FT / "worklist_report.json",
        *sum((["--pmc-report", str(p)] for p in sorted(FT.glob("pmc_*.json"))), []))
    snapshot = FT / ("worklist_report." + label + ".json")
    if not snapshot.exists():
        shutil.copy2(FT / "worklist_report.json", snapshot)


def main():
    D.mkdir(parents=True, exist_ok=True)
    lock = (D / "controller.lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    save(D / "controller_process.json", {"pid": os.getpid(), "command": [PYTHON, str(Path(__file__).resolve())], "started_at_utc": now()})
    scope = set(SCOPE.read_text().splitlines())
    assert scope
    assert read(RUN / "run_manifest.json")["status"] == "promoted"
    abstract_manifest = ROOT / "data/processed/corpus/metadata_enrichment_runs/pcp_scope_20261019_crossref/run_manifest.json"
    while read(abstract_manifest)["status"] not in {"complete", "failed"}:
        update(status="waiting_for_abstract_recovery", stage="metadata")
        time.sleep(10)
    assert read(abstract_manifest)["status"] == "complete"
    command("prescreen", "pipeline/review/run_deterministic_prescreen.py", "--run-id", RUN_ID,
        "--doi-file", SCOPE, "--reconciliation-report", D / "prescreen_reconciliation.json")
    if not (INPUTS / "freeze.json").exists():
        for name, source in [("candidate_scope.parquet", screening.DEFAULT_CANDIDATE_TABLE),
            ("metadata_scope.parquet", screening.DEFAULT_METADATA_TABLE), ("prescreen_scope.parquet", screening.DEFAULT_PRESCREEN_TABLE)]:
            frame = pd.read_parquet(source)
            frame.loc[frame.doi.isin(scope)].to_parquet(INPUTS / name, index=False)
        pre = pd.read_parquet(INPUTS / "prescreen_scope.parquet")
        model_dois = sorted(set(pre.loc[pre.prescreen_decision.eq("retain"), "doi"]))
        (INPUTS / "model_dois.txt").write_text("".join(x + "\n" for x in model_dois))
        save(INPUTS / "freeze.json", {p.name: sha(p) for p in INPUTS.iterdir() if p.is_file() and p.name != "freeze.json"})
    for name, digest in read(INPUTS / "freeze.json").items():
        assert sha(INPUTS / name) == digest, f"Frozen input changed: {name}"
    paths = finish_batch("main", INPUTS / "model_dois.txt")
    raw = [json.loads(line) for line in paths["raw"].open()]
    latest = {x["doi"]: x for x in raw}
    errors = [doi for doi, row in latest.items() if row["status"] != "ok"]
    if errors:
        retry_file = INPUTS / "retry_dois.txt"
        retry_file.write_text("".join(x + "\n" for x in sorted(errors)))
        retry = finish_batch("retry", retry_file)
        retry_rows = [json.loads(line) for line in retry["raw"].open()]
        raw.extend(retry_rows)
        latest.update({x["doi"]: x for x in retry_rows})
    if any(x["status"] != "ok" for x in latest.values()):
        raise RuntimeError("Unresolved screening failures after one retry; no result promotion")
    assert set(latest) == set((INPUTS / "model_dois.txt").read_text().splitlines())
    combined = D / "screening/raw_combined.jsonl"
    combined.write_text("".join(json.dumps({**x, "screening_run_id": RUN_ID}, ensure_ascii=False) + "\n" for x in raw))
    command("combine_screening", "pipeline/review/run_domain_routing.py", "--parse-only",
        "--screening-profile", "v5_class_scope", "--raw-jsonl", combined,
        "--candidate-table", INPUTS / "candidate_scope.parquet", "--metadata-table", INPUTS / "metadata_scope.parquet",
        "--prescreen-decisions-table", INPUTS / "prescreen_scope.parquet", "--output-table", D / "screening/routes.parquet",
        "--summary-json", D / "screening/summary.json", "--counts-csv", D / "screening/counts.csv")
    if not (D / "screening/promotion.json").exists():
        baseline = pd.read_parquet(BASE / "paper_domain_routing.parquet")
        current = pd.read_parquet(screening.DEFAULT_OUTPUT_TABLE)
        increment = pd.read_parquet(D / "screening/routes.parquet")
        outside = baseline.loc[~baseline.doi.isin(scope)].sort_values(["doi", "domain_route"]).reset_index(drop=True)
        actual = current.loc[~current.doi.isin(scope), baseline.columns].sort_values(["doi", "domain_route"]).reset_index(drop=True)
        pd.testing.assert_frame_equal(outside, actual)
        merged = pd.concat([baseline.loc[~baseline.doi.isin(scope)], increment], ignore_index=True)
        tmp = screening.DEFAULT_OUTPUT_TABLE.with_suffix(".parquet.tmp")
        merged.to_parquet(tmp, index=False); tmp.replace(screening.DEFAULT_OUTPUT_TABLE)
        old_raw = screening.DEFAULT_RAW_JSONL
        # Append atomically, detecting a completed prior append if receipt writing was interrupted.
        found_run = any(json.loads(line).get("screening_run_id") == RUN_ID for line in old_raw.open() if line.strip())
        if not found_run:
            tmp = old_raw.with_suffix(".jsonl.tmp")
            with tmp.open("wb") as handle, old_raw.open("rb") as previous:
                shutil.copyfileobj(previous, handle)
                handle.write(combined.read_bytes())
            tmp.replace(old_raw)
        summary, counts = screening.build_summary(merged.to_dict("records"), inputs={"increment": RUN_ID, "prior_table": str(BASE / "paper_domain_routing.parquet")})
        screening.write_json(screening.DEFAULT_SUMMARY_JSON, summary)
        screening.write_counts_csv(screening.DEFAULT_COUNTS_CSV, counts)
        save(D / "screening/promotion.json", {"at_utc": now(), "scope": len(scope), "model_decisions": len(latest),
            "decisions": dict(Counter(x["parsed"]["screening_decision"] for x in latest.values())),
            "outside_scope_rows_verified_unchanged": len(outside), "canonical_sha256": sha(screening.DEFAULT_OUTPUT_TABLE)})
    pipeline_state = read(llm.PIPELINE_STATE)
    pipeline_state.setdefault("screening_scope_additions", {}).setdefault(RUN_ID, {}).update({
        "screening_status": "complete", "scope_file": str(SCOPE),
        "screening_promotion": str(D / "screening/promotion.json"), "fulltext_status": "pending",
    })
    pipeline_state.update(screening_instruction_file="docs/screening/title_abstract_screening_v5_pcp.md",
        screening_instruction_sha256=sha(ROOT / "docs/screening/title_abstract_screening_v5_pcp.md"),
        screening_prompt_amendment="v5_explicit_pcp_20261019",
        screening_table_sha256=sha(screening.DEFAULT_OUTPUT_TABLE),
        extraction_status="inputs_need_refresh_after_pcp_scope_addition")
    save(llm.PIPELINE_STATE, pipeline_state)
    save(D / "queue.json", {"run_id": RUN_ID, "inputs": {"previous_candidate_table": str(BASE / "candidate_papers.parquet")}, "parts": [{"raw_jsonl": str(combined)}]})
    FT.mkdir(parents=True, exist_ok=True)
    build_worklist("initial")
    command("pmc_initial", "pipeline/fulltext/fetch_pmc_fulltext_xml.py", "--selection-table", FT / "worklist.parquet",
        "--report", FT / "pmc_initial.json", "--workers", "8", "--rps", "2", "--timeout-sec", "25", "--no-rebuild-routes-after")
    build_worklist("after_pmc")
    if (FT / "enrichment_dois.txt").read_text().strip():
        command("open_access", "pipeline/ingest/refresh_open_access_links.py", "--doi-file", FT / "enrichment_dois.txt",
            "--config", ROOT / "pipeline/config.local.yaml", "--only-missing-pdf-url", "--workers", "8",
            "--report-json", FT / "access_refresh.json", "--pmc-report", FT / "pmc_initial.json",
            "--timeout-sec", "25", "--max-retries", "1", "--max-retry-after-sec", "30")
    build_worklist("after_access")
    command("pmc_after_access", "pipeline/fulltext/fetch_pmc_fulltext_xml.py", "--selection-table", FT / "worklist.parquet",
        "--report", FT / "pmc_after_access.json", "--workers", "8", "--rps", "2", "--timeout-sec", "25", "--no-rebuild-routes-after")
    build_worklist("before_pdf")
    command("pdf_direct", "pipeline/fulltext/download_fulltext_worklist_pdfs.py", "--selection-table", FT / "worklist.parquet",
        "--report", FT / "pdf_direct.json", "--workers", "10", "--rps", "3", "--timeout-sec", "25", "--max-retries", "1",
        "--include-weak-pdf-urls", "--no-rebuild-routes-after", "--attempt-log-every", "0", "--candidate-log-every", "0")
    build_worklist("after_direct")
    command("pdf_alternate", "pipeline/fulltext/download_fulltext_worklist_pdfs.py", "--selection-table", FT / "worklist.parquet",
        "--report", FT / "pdf_alternate.json", "--workers", "8", "--rps", "2", "--timeout-sec", "25", "--max-retries", "1",
        "--alternate-pdf-sources", "pmc,openalex,semantic_scholar", "--alternate-sources-only", "--include-weak-pdf-urls",
        "--no-rebuild-routes-after", "--attempt-log-every", "0", "--candidate-log-every", "0")
    build_worklist("after_alternate")
    command("convert_pdfs", "pipeline/fulltext/convert_routed_local_pdfs.py", "--selection-table", FT / "worklist.parquet",
        "--doi-file", FT / "selected_dois.txt", "--report", FT / "conversion.json", "--no-rebuild-routes-after", "--backend", "grobid")
    command("source_identity", "pipeline/fulltext/audit_fulltext_source_identity.py")
    build_worklist("final")
    command("scoped_extraction_routes", "pipeline/extract/build_extraction_routes.py", "--doi-file", SCOPE,
        "--output-table", D / "extraction_routes.parquet", "--summary-json", D / "extraction_routes_summary.json", "--counts-csv", D / "extraction_routes_counts.csv")
    from pipeline.extract import build_extraction_routes as routes
    current_routes = pd.read_parquet(routes.DEFAULT_OUTPUT_TABLE)
    increment_routes = pd.read_parquet(D / "extraction_routes.parquet")
    merged_routes = pd.concat([current_routes.loc[~current_routes.doi.isin(scope)], increment_routes], ignore_index=True)
    temporary = routes.DEFAULT_OUTPUT_TABLE.with_suffix(".parquet.tmp")
    merged_routes.to_parquet(temporary, index=False); temporary.replace(routes.DEFAULT_OUTPUT_TABLE)
    route_summary, route_counts = routes.build_summary(merged_routes.to_dict("records"), inputs={"scope_addition": RUN_ID})
    routes.write_json(routes.DEFAULT_SUMMARY_JSON, route_summary)
    routes.write_counts_csv(routes.DEFAULT_COUNTS_CSV, route_counts)
    command("manual_queue", "pipeline/fulltext/export_manual_pdf_queue.py", "--selection-table", FT / "worklist.parquet",
        "--output-csv", FT / "manual_recovery.csv", "--output-txt", FT / "manual_recovery_dois.txt", "--require-automated-retrieval-complete")
    command("article_inputs", "pipeline/fulltext/build_article_text_inputs.py", "--route-table", D / "extraction_routes.parquet",
        "--out-jsonl", D / "article_text_inputs.jsonl", "--report-json", D / "article_text_inputs_report.json",
        "--audit-csv", D / "article_text_inputs_audit.csv", "--audit-md", D / "article_text_inputs_audit.md")
    command("extraction_tasks", "pipeline/extract/build_extraction_tasks.py", "--route-table", D / "extraction_routes.parquet",
        "--doi-file", SCOPE, "--article-text-inputs-jsonl", D / "article_text_inputs.jsonl", "--no-default-article-text-inputs",
        "--out-jsonl", D / "extraction_tasks.jsonl", "--report-json", D / "extraction_tasks_report.json")
    prepared_candidates = D / "prepared_candidates.parquet"
    if not prepared_candidates.exists():
        candidate_frame = pd.read_parquet(screening.DEFAULT_CANDIDATE_TABLE)
        candidate_frame.loc[candidate_frame.doi.isin(scope)].to_parquet(prepared_candidates, index=False)
    command("review_tasks", "pipeline/extract/build_review_relationship_tasks.py", "--candidate-parquet", prepared_candidates,
        "--packets-jsonl", D / "article_text_inputs.jsonl", "--out-dir", D / "review_tasks")
    command("meta_analysis_tasks", "pipeline/extract/build_meta_analysis_v2_tasks.py", "--candidate-parquet", prepared_candidates,
        "--packets-jsonl", D / "article_text_inputs.jsonl", "--out-dir", D / "meta_analysis_tasks")
    # Preserve the published graph and the active extraction release exactly.
    baseline_manifest = read(BASE / "manifest.json")
    for item in baseline_manifest:
        if item["path"] in {"data/processed/graph_payload_active.json", "data/processed/extraction/active_routed_run.json"}:
            assert sha(ROOT / item["path"]) == item["sha256"], "A published release pointer changed"
    current_candidates = pd.read_parquet(screening.DEFAULT_CANDIDATE_TABLE)
    old_candidates = pd.read_parquet(BASE / "candidate_papers.parquet")
    retained = lambda frame: set(frame.loc[frame.retained_for_extraction_candidate.fillna(False).astype(bool), "doi"])
    assert retained(old_candidates) - scope <= retained(current_candidates), "An unrelated retained paper was lost"
    save(D / "completion_integrity.json", {"old_retained_preserved": len(retained(old_candidates) - scope),
        "current_retained": len(retained(current_candidates)), "scope_retained": len(retained(current_candidates) & scope),
        "published_release_pointers_unchanged": True, "extraction_model_calls": 0, "verified_at_utc": now()})
    pipeline_state = read(llm.PIPELINE_STATE)
    pipeline_state["screening_scope_additions"][RUN_ID].update(fulltext_status="automated_complete_manual_queue_prepared",
        path=str(D), worklist_report=str(FT / "worklist_report.json"),
        provisional_extraction_tasks=str(D / "extraction_tasks.jsonl"), extraction_model_calls=0)
    pipeline_state["manual_fulltext_review_pending"] = True
    save(llm.PIPELINE_STATE, pipeline_state)
    update(status="complete_at_source_recovery_checkpoint", stage="complete", extraction_model_calls=0,
        manual_recovery=str(FT / "manual_recovery.csv"), graph_publication=False)
    print(now(), "Complete through source recovery and provisional extraction preparation; no extraction model calls.", flush=True)


if __name__ == "__main__":
    try:
        main()
    except BlockingIOError:
        raise SystemExit("An existing controller owns this run; no duplicate work started.")
    except Exception as exc:
        update(status="failed", error=f"{type(exc).__name__}: {exc}")
        raise
