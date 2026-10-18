#!/usr/bin/env python3
"""Prepare a clean Luna screening generation, then rebuild extraction from it."""
from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import pandas as pd
from pipeline import llm
from pipeline.review import run_domain_routing as screening
from pipeline.review import build_domain_routing_batch_queue as queue_builder
from pipeline.review import advance_domain_routing_batch_queue as queue_runner

DEFAULT_RUN = "luna_v5_20261017"
RUNS = ROOT / "data/processed/model_runs"
ARCHIVE = ROOT / "data/archive/20261017_gemini_retired"


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024*1024), b""):
            h.update(block)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def save(path, value):
    llm.atomic_json(path, value)


def run_command(args):
    subprocess.run([sys.executable, *map(str, args)], cwd=ROOT, check=True)


def archive_previous_active_outputs():
    """Keep source texts and published releases intact; retire mutable model inputs/outputs."""
    patterns = ["data/processed/corpus/paper_domain_routing_gemini*",
                "data/processed/corpus/paper_extraction_routes*",
                "data/processed/extraction/route_extraction_*",
                "data/processed/extraction/primary_extraction_tasks_update_*",
                "data/processed/extraction/review_relationship_tasks",
                "data/processed/extraction/meta_analysis_v2_tasks"]
    entries = []
    manifest = ARCHIVE / "retired_outputs.json"
    if manifest.exists():
        return read(manifest)
    for pattern in patterns:
        for path in sorted(ROOT.glob(pattern)):
            target = ARCHIVE / "outputs" / path.relative_to(ROOT)
            if target.exists():
                raise RuntimeError(f"Archive destination already exists: {target}")
            target.parent.mkdir(parents=True, exist_ok=True)
            entries.append(dict(source=str(path.relative_to(ROOT)), archived=str(target.relative_to(ROOT)),
                                sha256=sha(path) if path.is_file() else None))
            shutil.move(str(path), str(target))
    # Previous report-level and route-level judgements must not override the fresh run.
    for rel, key in [("data/curated/screening_decision_overrides.json", "overrides"),
                     ("pipeline/extract/manual_extraction_route_overrides.json", "records")]:
        path = ROOT / rel
        if not path.exists():
            continue
        target = ARCHIVE / "overrides" / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        old = read(path)
        save(path, dict(schema_version=old["schema_version"],
                        notes=["Previous scope/routing overrides archived for the complete Luna V5 rerun. No earlier model decisions are reused."],
                        **{key: []}))
        entries.append(dict(source=rel, archived=str(target.relative_to(ROOT)), sha256=sha(target)))
    result = dict(archived_at_utc=dt.datetime.now(dt.timezone.utc).isoformat(), entries=entries,
                  published_release_policy="Previous published release is retained until a complete clean replacement is promoted; never merged into new extraction.",
                  preserved_sources="Bibliographic metadata, PDFs, full-text packets and source-identity/access corrections")
    save(manifest, result)
    return result


def materialize_initial_cleanup(frame, run):
    """Clear stale model selections while preserving bibliography, source files and published graph state."""
    from pipeline.review import run_deterministic_prescreen as initial
    candidate = pd.read_parquet(screening.DEFAULT_CANDIDATE_TABLE)
    indexed = frame.drop_duplicates("doi").set_index("doi")
    dois = candidate.doi.map(screening.normalize_doi)
    selected = dois.map(indexed.retained_for_extraction_candidate).fillna(False).astype(bool)
    mapping = {"prescreen_retained_for_extraction_candidate": "retained_for_extraction_candidate",
               "prescreen_decisions": "prescreen_decision", "prescreen_actions": "prescreen_action",
               "prescreen_reasons": "prescreen_reason", "prescreen_rule_version": "rule_version",
               "prescreen_has_abstract": "has_abstract", "prescreen_abstract_word_count": "abstract_word_count"}
    for dest, source in mapping.items():
        if source in indexed:
            candidate[dest] = dois.map(indexed[source])
    reset = [c for c in candidate if c.startswith("extraction_") or c in {
        "retained_extraction_route_count", "retained_for_extraction_candidate", "literature_source_family",
        "literature_source_type", "literature_type_confidence", "primary_secondary_source_type",
        "secondary_source_types", "non_primary_flags", "flag_in_llm_abstract_screening"}]
    for c in reset:
        candidate[c] = False if c in {"retained_for_extraction_candidate", "flag_in_llm_abstract_screening"} else 0 if c.endswith("_count") else ""
    candidate["extraction_route_status"] = selected.map({True: "awaiting_luna_screening", False: "excluded_by_initial_screening"})
    candidate["pipeline_exclusion_stage"] = selected.map({True: "", False: "prescreen"})
    candidate["pipeline_exclusion_reason"] = candidate["prescreen_reasons"].where(~selected, "")
    candidate["pipeline_exclusion_decision_source"] = candidate["prescreen_rule_version"].where(~selected, "")
    temp = screening.DEFAULT_CANDIDATE_TABLE.with_suffix(".parquet.tmp")
    candidate.to_parquet(temp, index=False)
    temp.replace(screening.DEFAULT_CANDIDATE_TABLE)
    generated = dt.datetime.now(dt.timezone.utc).isoformat()
    summary = initial.build_summary_rows(frame.to_dict("records"), run_id=run.name, generated_at_utc=generated)
    temp = initial.DEFAULT_SUMMARY_TABLE.with_suffix(".parquet.tmp")
    pd.DataFrame(summary).to_parquet(temp, index=False)
    temp.replace(initial.DEFAULT_SUMMARY_TABLE)
    report = dict(selected_for_luna=int(selected.sum()), excluded_before_luna=int((~selected).sum()),
                  reset_model_selection_columns=reset, preserved="Bibliography, PDFs/text, access/identity corrections, and previous published graph state")
    save(run / "initial_cleanup_materialization.json", report)
    return report


def prepare(args):
    run = RUNS / args.run_id
    requested_scope = "all_candidates" if args.all_candidates else "cleanup_only" if args.reopen_topical else "deterministic_prescreen"
    if (run / "run.json").exists():
        previous = read(run / "run.json")
        if previous["scope"] == requested_scope:
            return previous
        if previous["screening_status"] != "prepared" or list((run / "screening").glob("*job*.json")):
            raise ValueError("A submitted run cannot change scope; use a new run ID")
        save(run / "superseded_scope_plan.json", previous)
        (run / "screening").rename(run / "superseded_prescreen_queue")
    inputs = run / "inputs"
    inputs.mkdir(parents=True, exist_ok=True)
    sources = {"candidate_table": screening.DEFAULT_CANDIDATE_TABLE,
               "metadata_table": screening.DEFAULT_METADATA_TABLE,
               "original_prescreen_table": screening.DEFAULT_PRESCREEN_TABLE,
               "screening_prompt": screening.SCREENING_PROMPT_PATH}
    frozen = {}
    for name, source in sources.items():
        dest = inputs / source.name
        if not dest.exists():
            shutil.copy2(source, dest)
        frozen[name] = dict(path=str(dest), sha256=sha(dest), original=str(source))
    metadata = screening.merged_routing_metadata(pd.read_parquet(frozen["candidate_table"]["path"]),
                                                pd.read_parquet(frozen["metadata_table"]["path"]))
    prescreen = pd.read_parquet(frozen["original_prescreen_table"]["path"])
    if args.all_candidates:
        frame = pd.DataFrame({"doi": sorted(set(metadata.doi.dropna().map(screening.normalize_doi)))})
        frame["retained_for_extraction_candidate"] = True
        frame["prescreen_decision"] = "retain"
    elif args.reopen_topical:
        frame = prescreen.copy()
        reopened = frame.prescreen_action.eq("exclude_obvious_irrelevant") & frame.has_abstract.fillna(False)
        frame.loc[reopened, ["retained_for_screening", "retained_for_extraction_candidate"]] = True
        frame.loc[reopened, "prescreen_decision"] = "retain"
        frame.loc[reopened, "prescreen_action"] = "retain_for_screening"
        frame.loc[reopened, "prescreen_reason"] = "Topical exclusion reopened for Luna V5; original publication/language/usable-text gates preserved."
        frame.loc[reopened, "deterministic_action"] = "retain_for_screening"
        frame.loc[reopened, "deterministic_reason"] = frame.loc[reopened, "prescreen_reason"]
        frame["rule_version"] = "cleanup_only_luna_v5_20261017"
    else:
        frame = prescreen
    frame_path = inputs / "screening_frame.parquet"
    frame.to_parquet(frame_path, index=False)
    frozen["screening_frame"] = dict(path=str(frame_path), sha256=sha(frame_path))
    queue_path = run / "screening/queue.json"
    qargs = queue_builder.parse_args([
        "--fresh", "--prepare", "--tag", args.run_id,
        "--candidate-table", frozen["candidate_table"]["path"],
        "--metadata-table", frozen["metadata_table"]["path"],
        "--prescreen-decisions-table", str(frame_path),
        "--out-dir", str(run / "screening"), "--queue-json", str(queue_path),
        "--python", sys.executable, "--max-approx-input-tokens", "1500000",
        "--max-output-tokens", "2048", "--model", llm.DEFAULT_MODEL])
    queue = queue_builder.build_queue(qargs)
    queue["inputs"]["screening_prompt_sha256"] = sha(screening.SCREENING_PROMPT_PATH)
    save(queue_path, queue)
    archived = archive_previous_active_outputs()
    state = dict(run_id=args.run_id, model=llm.DEFAULT_MODEL, reasoning_effort="low",
                 screening_prompt_version="v5_class_scope", screening_status="prepared",
                 extraction_status="waiting_for_screening", scope=requested_scope,
                 prepared_at_utc=dt.datetime.now(dt.timezone.utc).isoformat(),
                 expected_screening_papers=queue["summary"]["records"],
                 screening_parts=queue["summary"]["parts"], queue=str(queue_path),
                 frozen_inputs=frozen, archive=str(ARCHIVE / "retired_outputs.json"),
                 archived_paths=len(archived["entries"]), reuse_previous_decisions=False,
                 reuse_previous_extraction=False, remote_batches_submitted=0)
    state["model_api_budget_usd"] = args.budget_usd
    if args.reopen_topical:
        state["reopened_topical_papers"] = int(reopened.sum())
        temp = screening.DEFAULT_PRESCREEN_TABLE.with_suffix(".parquet.tmp")
        shutil.copy2(frame_path, temp)
        temp.replace(screening.DEFAULT_PRESCREEN_TABLE)
        materialize_initial_cleanup(frame, run)
    save(run / "run.json", state)
    save(llm.PIPELINE_STATE, state)
    return state


def advance(args):
    path = RUNS / args.run_id / "run.json"
    state = read(path)
    for item in state["frozen_inputs"].values():
        if sha(item["path"]) != item["sha256"]:
            raise ValueError("Frozen rerun input changed")
    if sha(screening.SCREENING_PROMPT_PATH) != state["frozen_inputs"]["screening_prompt"]["sha256"]:
        raise ValueError("Screening prompt changed since preparation")
    out = RUNS / args.run_id / "screening"
    argv = ["--queue-json", state["queue"],
            "--candidate-table", state["frozen_inputs"]["candidate_table"]["path"],
            "--metadata-table", state["frozen_inputs"]["metadata_table"]["path"],
            "--prescreen-decisions-table", state["frozen_inputs"]["screening_frame"]["path"],
            "--output-table", str(out / "paper_domain_routing.parquet"),
            "--raw-jsonl", str(out / "paper_domain_routing_raw.jsonl"),
            "--summary-json", str(out / "paper_domain_routing_summary.json"),
            "--counts-csv", str(out / "paper_domain_routing_counts.csv"),
            "--max-active", str(args.max_active or state.get("screening_queue_limits", {}).get("max_active", 1)),
            "--max-enqueued-approx-tokens", str(args.max_enqueued_tokens or state.get("screening_queue_limits", {}).get("max_enqueued_tokens", 2000000))]
    if args.submit:
        argv += ["--submit"]
    result = queue_runner.advance_queue(queue_runner.parse_args(argv))
    state["last_screening_progress"] = result
    parts = read(state["queue"])["parts"]
    state["remote_batches_submitted"] = sum(bool(read(part["job_json"]).get("job_name"))
                                           for part in parts if Path(part["job_json"]).exists())
    state["screened_papers_completed"] = sum(read(part["report_json"]).get("summary", {}).get("parsed_outputs", 0)
                                             for part in parts if Path(part["report_json"]).exists())
    if result["action"] == "complete":
        table = pd.read_parquet(out / "paper_domain_routing.parquet")
        if table.doi.nunique() != state["expected_screening_papers"] or set(table.model) != {llm.DEFAULT_MODEL}:
            raise ValueError("Complete screening must cover every frozen paper with Luna-only provenance")
        for source, dest in [(out / "paper_domain_routing.parquet", screening.DEFAULT_OUTPUT_TABLE),
                             (out / "paper_domain_routing_raw.jsonl", screening.DEFAULT_RAW_JSONL),
                             (out / "paper_domain_routing_summary.json", screening.DEFAULT_SUMMARY_JSON),
                             (out / "paper_domain_routing_counts.csv", screening.DEFAULT_COUNTS_CSV)]:
            temp = dest.with_suffix(dest.suffix + ".tmp")
            shutil.copy2(source, temp)
            temp.replace(dest)
        state["screening_status"] = "complete"
        state["screening_table_sha256"] = sha(screening.DEFAULT_OUTPUT_TABLE)
        state["extraction_status"] = "ready_to_prepare"
    elif result.get("submitted_now") or result.get("active"):
        state["screening_status"] = "running"
    save(path, state)
    save(llm.PIPELINE_STATE, state)
    return result


def prepare_extraction(args):
    state_path = RUNS / args.run_id / "run.json"
    state = read(state_path)
    if state["screening_status"] != "complete":
        raise RuntimeError("Complete Luna screening first; no old extraction selection may be reused")
    if sha(screening.DEFAULT_OUTPUT_TABLE) != state["screening_table_sha256"]:
        raise ValueError("Screening table changed after completion")
    run_command(["pipeline/extract/build_extraction_routes.py"])
    run_command(["pipeline/extract/build_extraction_tasks.py", "--only-ready"])
    run_command(["pipeline/extract/build_review_relationship_tasks.py"])
    run_command(["pipeline/extract/build_meta_analysis_v2_tasks.py"])
    state["extraction_status"] = "tasks_prepared"
    state["extraction_run_ids"] = dict(primary=f"{args.run_id}_primary", review=f"{args.run_id}_review", meta=f"{args.run_id}_meta")
    save(state_path, state)
    save(llm.PIPELINE_STATE, state)
    return state


def repack_screening(args):
    from pipeline.review.repack_domain_routing_batch_queue import repack_pending_queue
    path = RUNS / args.run_id / "run.json"
    state = read(path)
    if state["screening_status"] == "complete":
        raise ValueError("Screening is already complete")
    if not args.max_active or not args.max_enqueued_tokens:
        raise ValueError("Specify concurrency and verified account queue capacity when repacking")
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    result = repack_pending_queue(state["queue"], RUNS / args.run_id / "screening" / f"repacked_{stamp}",
                                 max_bytes=args.max_batch_bytes)
    state["screening_parts"] = read(state["queue"])["summary"]["parts"]
    state["screening_queue_limits"] = dict(max_active=args.max_active, max_enqueued_tokens=args.max_enqueued_tokens)
    state["last_queue_repack"] = result
    save(path, state)
    save(llm.PIPELINE_STATE, state)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("command", choices=["prepare", "advance-screening", "repack-screening", "prepare-extraction", "status"])
    p.add_argument("--run-id", default=DEFAULT_RUN)
    scope = p.add_mutually_exclusive_group()
    scope.add_argument("--all-candidates", action="store_true")
    scope.add_argument("--reopen-topical", action="store_true", help="Preserve cleanup rules and let Luna reconsider topical exclusions (default)")
    scope.add_argument("--keep-topical-filters", action="store_false", dest="reopen_topical", help="Reproduce the narrower historical prescreen for audits")
    p.set_defaults(reopen_topical=True)
    p.add_argument("--budget-usd", type=float, default=100)
    p.add_argument("--submit", action="store_true")
    p.add_argument("--max-active", type=int, default=0, help="Override the saved run concurrency")
    p.add_argument("--max-enqueued-tokens", type=int, default=0, help="Override the saved run queue capacity")
    p.add_argument("--max-batch-bytes", type=int, default=150_000_000)
    p.add_argument("--watch", action="store_true", help="Continue advancing submitted screening jobs until completion or an issue")
    p.add_argument("--poll-seconds", type=float, default=60)
    p.add_argument("--prepare-extraction-after-screening", action="store_true")
    args = p.parse_args()
    if args.all_candidates:
        args.reopen_topical = False
    if not args.run_id or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for c in args.run_id):
        raise ValueError("Invalid run ID")
    if args.command in {"advance-screening", "repack-screening"}:
        lock = (RUNS / args.run_id / "controller.lock").open("a")
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit("The screening controller is already running. Use status to inspect progress.")
    action = {"prepare": prepare, "advance-screening": advance, "repack-screening": repack_screening, "prepare-extraction": prepare_extraction,
              "status": lambda a: read(RUNS / a.run_id / "run.json")}[args.command]
    while True:
        result = action(args)
        print(json.dumps(result, indent=2), flush=True)
        if not args.watch or args.command != "advance-screening":
            break
        if result["action"] == "complete":
            if args.prepare_extraction_after_screening:
                print(json.dumps(prepare_extraction(args), indent=2), flush=True)
            break
        if result["action"] in {"terminal_failure", "parse_issues"}:
            raise SystemExit(1)
        time.sleep(max(10, args.poll_seconds))


if __name__ == "__main__":
    main()
