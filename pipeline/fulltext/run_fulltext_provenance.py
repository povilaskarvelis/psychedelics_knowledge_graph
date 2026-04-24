#!/usr/bin/env python3
"""Run the full-text provenance maintenance stage.

This orchestrates the non-destructive full-text workflow:

1. Convert missing PDFs for stale `full_text_seen` abstract locators.
2. Rebuild provenance repair reports.
3. Export blank accepted-review CSV templates.

It deliberately does not apply repairs to curated claims. Use
apply_provenance_repairs.py with an explicitly reviewed CSV for that step.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List

ROOT = Path(__file__).resolve().parents[2]
FULLTEXT_DIR = ROOT / "pipeline" / "fulltext"
FULLTEXT_DATA_DIR = ROOT / "data" / "processed" / "fulltext"
DEFAULT_DATASETS = ["disorder", "mechanistic"]

try:
    from pipeline.fulltext.convert_pdfs import (
        DATASET_CONFIG as CONVERT_CONFIG,
        DEFAULT_GROBID_URL,
        iter_pdf_rows,
        load_json_array,
        load_json_object,
        normalize,
        normalize_doi,
        stale_fulltext_locator_dois,
    )
    from pipeline.fulltext.start_grobid import (
        DEFAULT_CONFIG as DEFAULT_GROBID_CONFIG,
        DEFAULT_CONTAINER as DEFAULT_GROBID_CONTAINER,
        DEFAULT_IMAGE as DEFAULT_GROBID_IMAGE,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    sys.path.insert(0, str(ROOT))
    from pipeline.fulltext.convert_pdfs import (
        DATASET_CONFIG as CONVERT_CONFIG,
        DEFAULT_GROBID_URL,
        iter_pdf_rows,
        load_json_array,
        load_json_object,
        normalize,
        normalize_doi,
        stale_fulltext_locator_dois,
    )
    from pipeline.fulltext.start_grobid import (
        DEFAULT_CONFIG as DEFAULT_GROBID_CONFIG,
        DEFAULT_CONTAINER as DEFAULT_GROBID_CONTAINER,
        DEFAULT_IMAGE as DEFAULT_GROBID_IMAGE,
    )


@dataclass
class StageCommand:
    dataset: str
    stage: str
    cmd: List[str]


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def shell_join(cmd: List[str]) -> str:
    return " ".join(shlex.quote(part) for part in cmd)


def selected_datasets(value: str) -> List[str]:
    if value == "all":
        return list(DEFAULT_DATASETS)
    return [value]


def limit_for_dataset(args: argparse.Namespace, dataset: str) -> int:
    override = getattr(args, f"{dataset}_limit")
    if override is not None:
        return max(0, override)
    return max(0, args.limit)


def review_csv_path(dataset: str, review_dir: Path) -> Path:
    return review_dir / f"provenance_review_{dataset}.csv"


def successful_backend_in_artifact(artifact_path: Path, backend: str) -> bool:
    artifact = load_json_object(artifact_path)
    if normalize(artifact.get("best_backend", "")) == backend:
        return True
    for extraction in artifact.get("extractions", []):
        if not isinstance(extraction, dict):
            continue
        if normalize(extraction.get("backend", "")) == backend and normalize(extraction.get("status", "")) == "ok":
            return True
    return False


def doi_filter_for_dataset(args: argparse.Namespace, dataset: str) -> set[str] | None:
    if not args.stale_fulltext_locators:
        return None
    cfg = CONVERT_CONFIG[dataset]
    return stale_fulltext_locator_dois(load_json_array(cfg["curated_json"]))


def grobid_conversion_queue(args: argparse.Namespace, dataset: str) -> List[tuple[dict, Path, Path]]:
    """Return candidates that still need a successful GROBID extraction."""
    cfg = CONVERT_CONFIG[dataset]
    rows = load_json_array(cfg["paper_db_json"])
    queue = []
    for row, pdf_path, artifact_path in iter_pdf_rows(
        rows,
        only_missing_artifacts=False,
        out_dir=cfg["out_dir"],
        doi_filter=doi_filter_for_dataset(args, dataset),
    ):
        if args.only_missing_artifacts and artifact_path.exists():
            continue
        if not args.only_missing_artifacts and successful_backend_in_artifact(artifact_path, "grobid"):
            continue
        queue.append((row, pdf_path, artifact_path))

    limit = limit_for_dataset(args, dataset)
    if limit > 0:
        return queue[:limit]
    return queue


def chunked(items: List[tuple[dict, Path, Path]], size: int) -> Iterable[List[tuple[dict, Path, Path]]]:
    size = max(1, size)
    for index in range(0, len(items), size):
        yield items[index : index + size]


def write_doi_batch_file(dataset: str, batch_index: int, rows: List[tuple[dict, Path, Path]], batch_dir: Path) -> Path:
    batch_dir.mkdir(parents=True, exist_ok=True)
    path = batch_dir / f"{dataset}_grobid_batch_{batch_index:04d}.txt"
    dois = [normalize_doi(row.get("study_doi", "")) for row, _pdf_path, _artifact_path in rows]
    path.write_text("\n".join(doi for doi in dois if doi) + "\n", encoding="utf-8")
    return path


def grobid_start_command(args: argparse.Namespace) -> List[str]:
    cmd = [
        args.python,
        str(FULLTEXT_DIR / "start_grobid.py"),
        "--image",
        args.grobid_image,
        "--container",
        args.grobid_container,
        "--config",
        str(Path(args.grobid_config).resolve()),
        "--concurrency",
        str(args.grobid_concurrency),
        "--pdfalto-memory-mb",
        str(args.grobid_pdfalto_memory_mb),
        "--wait-sec",
        str(args.grobid_start_wait_sec),
    ]
    if args.grobid_memory:
        cmd.extend(["--memory", args.grobid_memory])
    if args.recreate_grobid_config:
        cmd.append("--recreate-config")
    return cmd


def grobid_convert_batch_command(
    args: argparse.Namespace,
    dataset: str,
    doi_file: Path,
    report_path: Path,
) -> List[str]:
    cmd = [
        args.python,
        str(FULLTEXT_DIR / "convert_pdfs.py"),
        "--dataset",
        dataset,
        "--backend",
        "grobid",
        "--limit",
        "0",
        "--doi-file",
        str(doi_file),
        "--report",
        str(report_path),
        "--grobid-url",
        args.grobid_url,
        "--grobid-retries",
        str(args.grobid_retries),
        "--grobid-retry-wait-sec",
        str(args.grobid_retry_wait_sec),
        "--grobid-consolidate-header",
        args.grobid_consolidate_header,
        "--grobid-consolidate-citations",
        args.grobid_consolidate_citations,
        "--timeout-sec",
        str(args.grobid_timeout_sec),
    ]
    if args.stale_fulltext_locators:
        cmd.append("--stale-fulltext-locators")
    if args.only_missing_artifacts:
        cmd.append("--only-missing-artifacts")
    if args.no_pdf_env_bootstrap:
        cmd.append("--no-pdf-env-bootstrap")
    return cmd


def build_stage_commands(args: argparse.Namespace) -> List[StageCommand]:
    python_bin = args.python
    review_dir = Path(args.review_dir).resolve()
    stages: List[StageCommand] = []

    for dataset in selected_datasets(args.dataset):
        if not args.skip_conversion:
            cmd = [
                python_bin,
                str(FULLTEXT_DIR / "convert_pdfs.py"),
                "--dataset",
                dataset,
                "--backend",
                args.backend,
                "--limit",
                str(limit_for_dataset(args, dataset)),
            ]
            if args.stale_fulltext_locators:
                cmd.append("--stale-fulltext-locators")
            if args.only_missing_artifacts:
                cmd.append("--only-missing-artifacts")
            if args.no_pdf_env_bootstrap:
                cmd.append("--no-pdf-env-bootstrap")
            if args.backend == "grobid":
                cmd.extend(
                    [
                        "--grobid-url",
                        args.grobid_url,
                        "--grobid-retries",
                        str(args.grobid_retries),
                        "--grobid-retry-wait-sec",
                        str(args.grobid_retry_wait_sec),
                        "--grobid-consolidate-header",
                        args.grobid_consolidate_header,
                        "--grobid-consolidate-citations",
                        args.grobid_consolidate_citations,
                        "--timeout-sec",
                        str(args.grobid_timeout_sec),
                    ]
                )
            stages.append(StageCommand(dataset=dataset, stage="convert", cmd=cmd))

        if not args.skip_repair_report:
            stages.append(
                StageCommand(
                    dataset=dataset,
                    stage="repair_report",
                    cmd=[
                        python_bin,
                        str(FULLTEXT_DIR / "build_provenance_repair_report.py"),
                        "--dataset",
                        dataset,
                    ],
                )
            )

        if not args.skip_evidence_triage:
            stages.append(
                StageCommand(
                    dataset=dataset,
                    stage="evidence_triage",
                    cmd=[
                        python_bin,
                        str(FULLTEXT_DIR / "build_evidence_triage_report.py"),
                        "--dataset",
                        dataset,
                        "--auto-confidence",
                        str(args.evidence_triage_auto_confidence),
                        "--scope",
                        args.evidence_triage_scope,
                    ],
                )
            )

        if not args.skip_review_export:
            stages.append(
                StageCommand(
                    dataset=dataset,
                    stage="review_export",
                    cmd=[
                        python_bin,
                        str(FULLTEXT_DIR / "apply_provenance_repairs.py"),
                        "--dataset",
                        dataset,
                        "--export-review-csv",
                        str(review_csv_path(dataset, review_dir)),
                    ],
                )
            )

    return stages


def run_stage(stage: StageCommand, verbose: bool) -> dict:
    start = time.monotonic()
    print(f"[{stage.dataset}:{stage.stage}] Running...", flush=True)
    if verbose:
        print(f"[{stage.dataset}:{stage.stage}] {shell_join(stage.cmd)}", flush=True)

    proc = subprocess.run(stage.cmd, cwd=ROOT, text=True, capture_output=True)
    elapsed = round(time.monotonic() - start, 3)
    if proc.stdout:
        print(proc.stdout, end="" if proc.stdout.endswith("\n") else "\n")
    if proc.stderr:
        print(proc.stderr, end="" if proc.stderr.endswith("\n") else "\n", file=sys.stderr)

    status = "ok" if proc.returncode == 0 else "failed"
    print(f"[{stage.dataset}:{stage.stage}] {status} in {elapsed}s", flush=True)
    return {
        "dataset": stage.dataset,
        "stage": stage.stage,
        "command": stage.cmd,
        "returncode": proc.returncode,
        "status": status,
        "elapsed_sec": elapsed,
        "stdout_tail": proc.stdout[-2000:],
        "stderr_tail": proc.stderr[-2000:],
    }


def run_managed_grobid_conversion(args: argparse.Namespace, dataset: str) -> dict:
    start = time.monotonic()
    queue = grobid_conversion_queue(args, dataset)
    batch_size = max(1, args.grobid_batch_size)
    batch_dir = Path(args.grobid_batch_dir).resolve()
    report_dir = Path(args.grobid_batch_report_dir).resolve()
    report_dir.mkdir(parents=True, exist_ok=True)

    print(f"[{dataset}:convert] Managed GROBID queue: {len(queue)} PDF(s), batch size {batch_size}", flush=True)
    if not queue:
        elapsed = round(time.monotonic() - start, 3)
        return {
            "dataset": dataset,
            "stage": "convert",
            "mode": "managed_grobid",
            "returncode": 0,
            "status": "ok",
            "elapsed_sec": elapsed,
            "queue_size": 0,
            "batch_size": batch_size,
            "batches": [],
        }

    batch_results = []
    overall_status = "ok"
    overall_returncode = 0
    for batch_index, batch_rows in enumerate(chunked(queue, batch_size), start=1):
        if not args.skip_grobid_managed_start and (args.grobid_restart_each_batch or batch_index == 1):
            start_result = run_stage(
                StageCommand(dataset=dataset, stage=f"grobid_start_{batch_index:04d}", cmd=grobid_start_command(args)),
                verbose=args.verbose,
            )
            batch_results.append(start_result)
            if start_result["returncode"] != 0:
                overall_status = "failed"
                overall_returncode = start_result["returncode"]
                break

        doi_file = write_doi_batch_file(dataset, batch_index, batch_rows, batch_dir=batch_dir)
        report_path = report_dir / f"fulltext_report_{dataset}_grobid_batch_{batch_index:04d}.json"
        convert_result = run_stage(
            StageCommand(
                dataset=dataset,
                stage=f"convert_grobid_batch_{batch_index:04d}",
                cmd=grobid_convert_batch_command(args, dataset, doi_file=doi_file, report_path=report_path),
            ),
            verbose=args.verbose,
        )
        convert_result["doi_file"] = str(doi_file)
        convert_result["batch_report"] = str(report_path)
        convert_result["batch_pdf_count"] = len(batch_rows)
        batch_results.append(convert_result)
        if convert_result["returncode"] != 0:
            overall_status = "failed"
            overall_returncode = convert_result["returncode"]
            if not args.continue_on_error:
                break

    elapsed = round(time.monotonic() - start, 3)
    return {
        "dataset": dataset,
        "stage": "convert",
        "mode": "managed_grobid",
        "returncode": overall_returncode,
        "status": overall_status,
        "elapsed_sec": elapsed,
        "queue_size": len(queue),
        "batch_size": batch_size,
        "batch_count": (len(queue) + batch_size - 1) // batch_size,
        "batches": batch_results,
    }


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def use_managed_grobid(args: argparse.Namespace) -> bool:
    return not args.skip_conversion and args.backend == "grobid" and args.grobid_batch_size > 0


def print_managed_grobid_plan(args: argparse.Namespace) -> None:
    for dataset in selected_datasets(args.dataset):
        queue = grobid_conversion_queue(args, dataset)
        batch_size = max(1, args.grobid_batch_size)
        batch_count = (len(queue) + batch_size - 1) // batch_size
        print(
            f"[{dataset}:convert] managed GROBID batches: "
            f"{len(queue)} PDF(s), batch_size={batch_size}, batches={batch_count}"
        )
        if queue and not args.skip_grobid_managed_start:
            print(f"[{dataset}:grobid_start] {shell_join(grobid_start_command(args))}")
        if queue:
            print(
                f"[{dataset}:convert_grobid_batch] "
                f"{shell_join(grobid_convert_batch_command(args, dataset, Path('<batch-dois.txt>'), Path('<batch-report.json>')))}"
            )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", choices=["all", *DEFAULT_DATASETS], default="all")
    parser.add_argument("--backend", choices=["auto", "all", "docling", "grobid", "pdftotext"], default="auto")
    parser.add_argument("--limit", type=int, default=0, help="Conversion limit per dataset; 0 means all candidates")
    parser.add_argument("--disorder-limit", type=int, default=None, help="Override conversion limit for disorder")
    parser.add_argument("--mechanistic-limit", type=int, default=None, help="Override conversion limit for mechanistic")
    parser.add_argument("--review-dir", default=str(ROOT / "data" / "processed" / "fulltext"))
    parser.add_argument(
        "--out-report",
        default=str(ROOT / "data" / "processed" / "fulltext" / "fulltext_provenance_run_report.json"),
    )
    parser.add_argument("--python", default=sys.executable, help="Python executable for child stage scripts")
    parser.add_argument("--skip-conversion", action="store_true")
    parser.add_argument("--skip-repair-report", action="store_true")
    parser.add_argument("--skip-evidence-triage", action="store_true")
    parser.add_argument("--skip-review-export", action="store_true")
    parser.add_argument("--include-existing-artifacts", action="store_true")
    parser.add_argument("--all-pdf-candidates", action="store_true", help="Do not restrict conversion to stale locators")
    parser.add_argument("--no-pdf-env-bootstrap", action="store_true")
    parser.add_argument("--continue-on-error", action="store_true")
    parser.add_argument("--plan-only", action="store_true", help="Print planned commands without running them")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--evidence-triage-auto-confidence", type=float, default=0.85)
    parser.add_argument(
        "--evidence-triage-scope",
        choices=["full_text_seen", "artifacts", "all"],
        default="full_text_seen",
    )
    parser.add_argument(
        "--grobid-batch-size",
        type=int,
        default=50,
        help="Managed GROBID batch size; 0 disables managed batching and uses one legacy conversion call",
    )
    parser.add_argument("--grobid-url", default=DEFAULT_GROBID_URL)
    parser.add_argument("--grobid-timeout-sec", type=int, default=120)
    parser.add_argument("--grobid-retries", type=int, default=2)
    parser.add_argument("--grobid-retry-wait-sec", type=int, default=5)
    parser.add_argument("--grobid-consolidate-header", choices=["0", "1", "2", "3"], default="0")
    parser.add_argument("--grobid-consolidate-citations", choices=["0", "1", "2"], default="0")
    parser.add_argument("--grobid-batch-dir", default=str(FULLTEXT_DATA_DIR / "grobid_batches"))
    parser.add_argument("--grobid-batch-report-dir", default=str(FULLTEXT_DATA_DIR / "grobid_batch_reports"))
    parser.add_argument("--grobid-image", default=DEFAULT_GROBID_IMAGE)
    parser.add_argument("--grobid-container", default=DEFAULT_GROBID_CONTAINER)
    parser.add_argument("--grobid-config", default=str(DEFAULT_GROBID_CONFIG))
    parser.add_argument("--grobid-concurrency", type=int, default=1)
    parser.add_argument("--grobid-pdfalto-memory-mb", type=int, default=2048)
    parser.add_argument("--grobid-memory", default="5g", help="Docker container memory cap for managed GROBID")
    parser.add_argument("--grobid-start-wait-sec", type=int, default=90)
    parser.add_argument("--recreate-grobid-config", action="store_true")
    parser.add_argument("--skip-grobid-managed-start", action="store_true")
    parser.add_argument(
        "--grobid-restart-each-batch",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Restart the GROBID container before every managed batch",
    )
    args = parser.parse_args()

    args.only_missing_artifacts = not args.include_existing_artifacts
    args.stale_fulltext_locators = not args.all_pdf_candidates
    return args


def main() -> int:
    args = parse_args()
    stages = build_stage_commands(args)
    report_path = Path(args.out_report).resolve()

    print("=== Full-Text Provenance Stage ===")
    print(f"Datasets: {', '.join(selected_datasets(args.dataset))}")
    print(f"Backend: {args.backend}")
    print(f"Only missing artifacts: {'yes' if args.only_missing_artifacts else 'no'}")
    print(f"Stale-locator filter: {'yes' if args.stale_fulltext_locators else 'no'}")
    if use_managed_grobid(args):
        print(f"GROBID mode: managed batches of {max(1, args.grobid_batch_size)}")
        print(f"GROBID restart each batch: {'yes' if args.grobid_restart_each_batch else 'no'}")
    print(f"Mode: {'plan only' if args.plan_only else 'run'}")
    print("")

    if args.plan_only:
        if use_managed_grobid(args):
            print_managed_grobid_plan(args)
            print("")
        for stage in stages:
            if use_managed_grobid(args) and stage.stage == "convert":
                continue
            print(f"[{stage.dataset}:{stage.stage}] {shell_join(stage.cmd)}")
        return 0

    results = []
    overall_status = "ok"
    for stage in stages:
        if use_managed_grobid(args) and stage.stage == "convert":
            result = run_managed_grobid_conversion(args, stage.dataset)
        else:
            result = run_stage(stage, verbose=args.verbose)
        results.append(result)
        if result["returncode"] != 0:
            overall_status = "failed"
            if not args.continue_on_error:
                break

    payload = {
        "generated_at_utc": now_utc(),
        "status": overall_status,
        "inputs": {
            "dataset": args.dataset,
            "backend": args.backend,
            "limit": args.limit,
            "disorder_limit": args.disorder_limit,
            "mechanistic_limit": args.mechanistic_limit,
            "only_missing_artifacts": args.only_missing_artifacts,
            "stale_fulltext_locators": args.stale_fulltext_locators,
            "review_dir": str(Path(args.review_dir).resolve()),
            "evidence_triage_auto_confidence": args.evidence_triage_auto_confidence,
            "evidence_triage_scope": args.evidence_triage_scope,
            "grobid_batch_size": args.grobid_batch_size,
            "grobid_restart_each_batch": args.grobid_restart_each_batch,
            "skip_grobid_managed_start": args.skip_grobid_managed_start,
            "grobid_url": args.grobid_url,
            "grobid_retries": args.grobid_retries,
            "grobid_retry_wait_sec": args.grobid_retry_wait_sec,
            "grobid_consolidate_header": args.grobid_consolidate_header,
            "grobid_consolidate_citations": args.grobid_consolidate_citations,
        },
        "results": results,
    }
    write_json(report_path, payload)
    print("")
    print(f"Run status: {overall_status}")
    print(f"Run report: {report_path}")
    return 0 if overall_status == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
