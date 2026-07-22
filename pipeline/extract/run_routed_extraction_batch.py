#!/usr/bin/env python3
"""Run the next batch for an accumulating routed extraction run.

This is a small orchestration layer around the existing route extraction runner:

1. Select the next ready tasks that are not already attempted in the named run.
2. Run those tasks through Gemini and append to the run output JSONL files.
3. Convert the accumulated run outputs into evidence rows.
4. Rebuild versioned normalized KG tables for that run.

The stable current KG tables under data/processed/kg are not overwritten here.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import random
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

try:
    from pipeline.extract.io_utils import normalize, read_jsonl, write_json
    from pipeline.extract.route_extraction_profiles import (
        legacy_v1_secondary_block_message,
        profile_key_for_task,
        task_has_model_profile,
        task_has_registered_profile,
        task_uses_legacy_v1_secondary_profile,
    )
    from pipeline.extract.run_route_extraction import safe_run_id, text_depth_for_task
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from pipeline.extract.io_utils import normalize, read_jsonl, write_json
    from pipeline.extract.route_extraction_profiles import (
        legacy_v1_secondary_block_message,
        profile_key_for_task,
        task_has_model_profile,
        task_has_registered_profile,
        task_uses_legacy_v1_secondary_profile,
    )
    from pipeline.extract.run_route_extraction import safe_run_id, text_depth_for_task


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TASKS_JSONL = ROOT / "data" / "processed" / "extraction" / "route_extraction_tasks.jsonl"
DEFAULT_RUN_ROOT = ROOT / "data" / "processed" / "extraction" / "routed_runs"
DEFAULT_KG_RUN_ROOT = ROOT / "data" / "processed" / "kg_routed_runs"

REPORT_SCHEMA_VERSION = "routed_extraction_batch_report_v1"
BATCH_TASK_RE = re.compile(r"batch_(\d{3,})_tasks\.jsonl$")


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def appendable_output_paths(run_id: str) -> dict[str, Path]:
    run_dir = DEFAULT_RUN_ROOT / safe_run_id(run_id)
    return {
        "run_dir": run_dir,
        "outputs_jsonl": run_dir / "route_extraction_outputs.jsonl",
        "raw_jsonl": run_dir / "route_extraction_raw.jsonl",
        "evidence_rows_json": run_dir / "routed_evidence_rows.json",
        "evidence_rows_report_json": run_dir / "routed_evidence_rows_report.json",
        "kg_run_dir": DEFAULT_KG_RUN_ROOT / safe_run_id(run_id),
    }


def route_key(row: dict) -> str:
    return normalize(row.get("route_id", "")) or normalize(row.get("task_id", ""))


def row_status(row: dict) -> str:
    return normalize(row.get("status", ""))


RETRYABLE_RAW_STATUSES = {"error", "quality_error"}


def attempted_task_keys(run_dir: Path, *, retry_errors: bool = False) -> set[str]:
    keys: set[str] = set()
    output_jsonl = run_dir / "route_extraction_outputs.jsonl"
    raw_jsonl = run_dir / "route_extraction_raw.jsonl"

    for row in read_jsonl(output_jsonl) if output_jsonl.exists() else []:
        key = route_key(row)
        if key:
            keys.add(key)

    for row in read_jsonl(raw_jsonl) if raw_jsonl.exists() else []:
        if retry_errors and row_status(row) in RETRYABLE_RAW_STATUSES:
            continue
        key = route_key(row)
        if key:
            keys.add(key)

    return keys


def stale_input_fingerprint_task_keys(run_dir: Path, tasks: list[dict]) -> set[str]:
    """Return attempted routes whose current model input no longer matches the attempt."""

    current_fingerprints = {
        route_key(task): normalize(task.get("input_fingerprint", ""))
        for task in tasks
        if route_key(task) and normalize(task.get("input_fingerprint", ""))
    }
    stale: set[str] = set()
    for filename in ("route_extraction_outputs.jsonl", "route_extraction_raw.jsonl"):
        path = run_dir / filename
        for row in read_jsonl(path) if path.exists() else []:
            key = route_key(row)
            recorded = normalize(row.get("input_fingerprint", ""))
            current = current_fingerprints.get(key, "")
            if key and recorded and current and recorded != current:
                stale.add(key)
    return stale


def route_domain(task: dict) -> str:
    contract = task.get("extraction_contract", {}) if isinstance(task.get("extraction_contract"), dict) else {}
    context = task.get("route_context", {}) if isinstance(task.get("route_context"), dict) else {}
    return normalize(contract.get("domain_route", "")) or normalize(context.get("domain_route", ""))


def source_type(task: dict) -> str:
    contract = task.get("extraction_contract", {}) if isinstance(task.get("extraction_contract"), dict) else {}
    context = task.get("route_context", {}) if isinstance(task.get("route_context"), dict) else {}
    return (
        normalize(contract.get("source_type", ""))
        or normalize(context.get("source_type", ""))
        or normalize(context.get("primary_secondary_source_type", ""))
    )


def task_is_ready(task: dict) -> bool:
    return normalize(task.get("task_status", "")) == "ready_for_model"


def value_allowed(value: str, allowed: list[str]) -> bool:
    return not allowed or value in allowed


def task_matches_filters(task: dict, args: argparse.Namespace) -> bool:
    if not args.include_not_ready and not task_is_ready(task):
        return False
    if not task_has_registered_profile(task):
        return False
    if not task_has_model_profile(task, include_scaffold=args.include_scaffold_profiles):
        return False

    prompt_profile, schema_profile = profile_key_for_task(task)
    if not value_allowed(prompt_profile, args.prompt_profile):
        return False
    if not value_allowed(schema_profile, args.schema_profile):
        return False
    if not value_allowed(route_domain(task), args.domain_route):
        return False
    if not value_allowed(text_depth_for_task(task), args.text_depth):
        return False
    if not value_allowed(source_type(task), args.source_type):
        return False
    if args.route_id and route_key(task) not in args.route_id:
        return False
    if args.doi and normalize(task.get("study_doi", "")).lower() not in args.doi:
        return False
    return True


def select_next_tasks(tasks: list[dict], attempted: set[str], args: argparse.Namespace) -> list[tuple[int, dict]]:
    candidates = [
        (index, task)
        for index, task in enumerate(tasks, start=1)
        if task_matches_filters(task, args) and route_key(task) not in attempted
    ]
    if args.shuffle:
        rng = random.Random(args.seed)
        rng.shuffle(candidates)
    return candidates[: max(0, int(args.batch_size))]


def next_batch_id(batch_dir: Path) -> str:
    max_seen = 0
    if batch_dir.exists():
        for path in batch_dir.glob("batch_*_tasks.jsonl"):
            match = BATCH_TASK_RE.match(path.name)
            if match:
                max_seen = max(max_seen, int(match.group(1)))
    return f"batch_{max_seen + 1:03d}"


def selected_task_summary(selected: list[tuple[int, dict]]) -> list[dict]:
    return [
        {
            "input_row_index": index,
            "task_id": normalize(task.get("task_id", "")),
            "route_id": normalize(task.get("route_id", "")),
            "study_doi": normalize(task.get("study_doi", "")),
            "prompt_profile": profile_key_for_task(task)[0],
            "schema_profile": profile_key_for_task(task)[1],
            "domain_route": route_domain(task),
            "text_depth": text_depth_for_task(task),
            "source_type": source_type(task),
        }
        for index, task in selected
    ]


def selection_counts(tasks: list[dict], selected: list[tuple[int, dict]], attempted: set[str], args: argparse.Namespace) -> dict:
    eligible = [task for task in tasks if task_matches_filters(task, args)]
    remaining = [task for task in eligible if route_key(task) not in attempted]
    selected_tasks_only = [task for _, task in selected]
    return {
        "tasks_read": len(tasks),
        "eligible_tasks": len(eligible),
        "already_attempted_in_run": len([task for task in eligible if route_key(task) in attempted]),
        "remaining_before_batch": len(remaining),
        "selected_for_batch": len(selected),
        "remaining_after_batch": max(0, len(remaining) - len(selected)),
        "selected_by_prompt_profile": dict(Counter(profile_key_for_task(task)[0] for task in selected_tasks_only)),
        "selected_by_schema_profile": dict(Counter(profile_key_for_task(task)[1] for task in selected_tasks_only)),
        "selected_by_domain_route": dict(Counter(route_domain(task) for task in selected_tasks_only)),
        "selected_by_text_depth": dict(Counter(text_depth_for_task(task) for task in selected_tasks_only)),
        "selected_by_source_type": dict(Counter(source_type(task) for task in selected_tasks_only)),
    }


def run_command(cmd: list[str]) -> dict:
    print(" ".join(cmd), flush=True)
    completed = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)
    if completed.stdout:
        print(completed.stdout, end="", flush=True)
    if completed.stderr:
        print(completed.stderr, end="", file=sys.stderr, flush=True)
    return {
        "cmd": cmd,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def add_optional_runner_args(cmd: list[str], args: argparse.Namespace) -> None:
    if args.include_not_ready:
        cmd.append("--include-not-ready")
    if args.include_scaffold_profiles:
        cmd.append("--include-scaffold-profiles")
    if normalize(args.model):
        cmd.extend(["--model", normalize(args.model)])
    if args.schema_mode:
        cmd.extend(["--schema-mode", args.schema_mode])
    cmd.extend(["--temperature", str(args.temperature)])
    cmd.extend(["--thinking-budget", str(args.thinking_budget)])
    if args.max_output_tokens > 0:
        cmd.extend(["--max-output-tokens", str(args.max_output_tokens)])
    if args.sleep_sec > 0:
        cmd.extend(["--sleep-sec", str(args.sleep_sec)])


def read_json_if_exists(path: Path) -> dict:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def build_report(
    *,
    args: argparse.Namespace,
    paths: dict[str, Path],
    batch_id: str,
    selected: list[tuple[int, dict]],
    tasks: list[dict],
    attempted: set[str],
    status: str,
    commands: list[dict],
    outputs: dict[str, str],
) -> dict:
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "generated_at_utc": now_utc(),
        "status": status,
        "run_id": safe_run_id(args.run_id),
        "run_dir": str(paths["run_dir"]),
        "batch_id": batch_id,
        "inputs": {
            "tasks_jsonl": str(Path(args.input_jsonl).resolve()),
            "batch_size": args.batch_size,
            "shuffle": args.shuffle,
            "seed": args.seed,
            "retry_errors": args.retry_errors,
            "filters": {
                "prompt_profile": args.prompt_profile,
                "schema_profile": args.schema_profile,
                "domain_route": args.domain_route,
                "text_depth": args.text_depth,
                "source_type": args.source_type,
                "route_id": args.route_id,
                "doi": args.doi,
            },
        },
        "counts": selection_counts(tasks, selected, attempted, args),
        "selected_tasks": selected_task_summary(selected),
        "outputs": outputs,
        "commands": commands,
    }


def run_batch(args: argparse.Namespace) -> dict:
    paths = appendable_output_paths(args.run_id)
    run_dir = paths["run_dir"]
    batch_dir = run_dir / "batches"
    batch_id = next_batch_id(batch_dir)
    batch_prefix = batch_dir / batch_id
    batch_tasks_jsonl = batch_prefix.with_name(f"{batch_id}_tasks.jsonl")
    batch_report_json = batch_prefix.with_name(f"{batch_id}_route_extraction_report.json")
    batch_selection_report_json = batch_prefix.with_name(f"{batch_id}_selection_report.json")

    tasks = read_jsonl(Path(args.input_jsonl))
    if any(task_uses_legacy_v1_secondary_profile(task) for task in tasks):
        raise SystemExit(legacy_v1_secondary_block_message(tasks))
    attempted = attempted_task_keys(run_dir, retry_errors=args.retry_errors)
    attempted -= stale_input_fingerprint_task_keys(run_dir, tasks)
    selected = select_next_tasks(tasks, attempted, args)
    base_outputs = {
        "batch_selection_report_json": str(batch_selection_report_json),
        "batch_tasks_jsonl": str(batch_tasks_jsonl) if selected and not args.dry_run else "",
        "batch_route_extraction_report_json": str(batch_report_json) if selected and not args.dry_run else "",
        "run_outputs_jsonl": str(paths["outputs_jsonl"]),
        "run_raw_jsonl": str(paths["raw_jsonl"]),
        "routed_evidence_rows_json": str(paths["evidence_rows_json"]),
        "kg_run_dir": str(paths["kg_run_dir"]),
    }

    if args.dry_run or not selected:
        status = "dry_run" if args.dry_run else "no_tasks_available"
        report = build_report(
            args=args,
            paths=paths,
            batch_id=batch_id,
            selected=selected,
            tasks=tasks,
            attempted=attempted,
            status=status,
            commands=[],
            outputs=base_outputs,
        )
        write_json(batch_selection_report_json, report)
        return report

    write_jsonl(batch_tasks_jsonl, [task for _, task in selected])
    commands: list[dict] = []

    run_cmd = [
        sys.executable,
        "pipeline/extract/run_route_extraction.py",
        "--input-jsonl",
        str(batch_tasks_jsonl),
        "--run-id",
        safe_run_id(args.run_id),
        "--out-jsonl",
        str(paths["outputs_jsonl"]),
        "--raw-jsonl",
        str(paths["raw_jsonl"]),
        "--report-json",
        str(batch_report_json),
    ]
    add_optional_runner_args(run_cmd, args)
    commands.append(run_command(run_cmd))
    if commands[-1]["returncode"] != 0:
        report = build_report(
            args=args,
            paths=paths,
            batch_id=batch_id,
            selected=selected,
            tasks=tasks,
            attempted=attempted,
            status="failed_route_extraction",
            commands=commands,
            outputs=base_outputs,
        )
        write_json(batch_selection_report_json, report)
        raise SystemExit(commands[-1]["returncode"])

    if not args.skip_convert:
        convert_cmd = [
            sys.executable,
            "pipeline/kg/convert_routed_extractions_to_evidence_rows.py",
            "--run-id",
            safe_run_id(args.run_id),
            "--input-jsonl",
            str(paths["outputs_jsonl"]),
            "--tasks-jsonl",
            str(Path(args.input_jsonl).resolve()),
            "--use-default-active-route-table",
        ]
        if args.include_schema_errors:
            convert_cmd.append("--include-schema-errors")
        commands.append(run_command(convert_cmd))
        if commands[-1]["returncode"] != 0:
            report = build_report(
                args=args,
                paths=paths,
                batch_id=batch_id,
                selected=selected,
                tasks=tasks,
                attempted=attempted,
                status="failed_evidence_row_conversion",
                commands=commands,
                outputs=base_outputs,
            )
            write_json(batch_selection_report_json, report)
            raise SystemExit(commands[-1]["returncode"])

    if not args.skip_kg_build:
        kg_cmd = [
            sys.executable,
            "pipeline/kg/build_evidence_tables.py",
            "--source-preset",
            "routed",
            "--run-id",
            safe_run_id(args.run_id),
        ]
        commands.append(run_command(kg_cmd))
        if commands[-1]["returncode"] != 0:
            report = build_report(
                args=args,
                paths=paths,
                batch_id=batch_id,
                selected=selected,
                tasks=tasks,
                attempted=attempted,
                status="failed_kg_table_build",
                commands=commands,
                outputs=base_outputs,
            )
            write_json(batch_selection_report_json, report)
            raise SystemExit(commands[-1]["returncode"])

    outputs = dict(base_outputs)
    outputs["evidence_rows_report"] = read_json_if_exists(paths["evidence_rows_report_json"])
    outputs["kg_manifest"] = read_json_if_exists(paths["kg_run_dir"] / "manifest.json")
    report = build_report(
        args=args,
        paths=paths,
        batch_id=batch_id,
        selected=selected,
        tasks=tasks,
        attempted=attempted,
        status="complete",
        commands=commands,
        outputs=outputs,
    )
    write_json(batch_selection_report_json, report)
    return report


def normalize_list(values: list[str]) -> list[str]:
    return [normalize(value) for value in values if normalize(value)]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True, help="Version label for this accumulating extraction run.")
    parser.add_argument("--input-jsonl", type=Path, default=DEFAULT_TASKS_JSONL)
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--dry-run", action="store_true", help="Select the next batch without calling Gemini.")
    parser.add_argument("--shuffle", action="store_true", help="Randomize eligible remaining tasks before taking the batch.")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--retry-errors", action="store_true", help="Allow tasks with prior raw error rows to be selected again.")
    parser.add_argument("--include-not-ready", action="store_true")
    parser.add_argument("--include-scaffold-profiles", action="store_true")
    parser.add_argument("--prompt-profile", action="append", default=[])
    parser.add_argument("--schema-profile", action="append", default=[])
    parser.add_argument("--domain-route", action="append", default=[])
    parser.add_argument("--text-depth", action="append", default=[])
    parser.add_argument("--source-type", action="append", default=[])
    parser.add_argument("--route-id", action="append", default=[])
    parser.add_argument("--doi", action="append", default=[])
    parser.add_argument("--model", default="")
    parser.add_argument("--schema-mode", choices=["native", "prompt"], default="native")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--thinking-budget", type=int, default=0)
    parser.add_argument("--max-output-tokens", type=int, default=0)
    parser.add_argument("--sleep-sec", type=float, default=0.0)
    parser.add_argument("--include-schema-errors", action="store_true")
    parser.add_argument("--skip-convert", action="store_true")
    parser.add_argument("--skip-kg-build", action="store_true")
    args = parser.parse_args()
    args.run_id = safe_run_id(args.run_id)
    args.prompt_profile = normalize_list(args.prompt_profile)
    args.schema_profile = normalize_list(args.schema_profile)
    args.domain_route = normalize_list(args.domain_route)
    args.text_depth = normalize_list(args.text_depth)
    args.source_type = normalize_list(args.source_type)
    args.route_id = normalize_list(args.route_id)
    args.doi = [normalize(doi).lower() for doi in args.doi if normalize(doi)]
    return args


def main() -> int:
    args = parse_args()
    report = run_batch(args)
    print(f"Status: {report['status']}")
    print(f"Run id: {report['run_id']}")
    print(f"Batch id: {report['batch_id']}")
    print(f"Selected: {report['counts']['selected_for_batch']}")
    print(f"Remaining after batch: {report['counts']['remaining_after_batch']}")
    print(f"Selection report: {report['outputs']['batch_selection_report_json']}")
    kg_manifest = report["outputs"].get("kg_manifest")
    if isinstance(kg_manifest, dict) and kg_manifest.get("tables"):
        claims = kg_manifest["tables"].get("claims", {}).get("rows", 0)
        edges = kg_manifest["tables"].get("evidence_edges", {}).get("rows", 0)
        print(f"KG claims: {claims}")
        print(f"KG evidence edges: {edges}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
