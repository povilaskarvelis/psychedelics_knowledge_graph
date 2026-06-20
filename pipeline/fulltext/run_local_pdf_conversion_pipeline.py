#!/usr/bin/env python3
"""Run local PDF conversion in managed GROBID batches."""

from __future__ import annotations

import argparse
from collections.abc import Iterable
import datetime as dt
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
FULLTEXT_DIR = ROOT / "pipeline" / "fulltext"
EXTRACT_DIR = ROOT / "pipeline" / "extract"
FULLTEXT_DATA_DIR = ROOT / "data" / "processed" / "fulltext"
DEFAULT_BATCH_DIR = FULLTEXT_DATA_DIR / "grobid_local_pdf_batches"
DEFAULT_BATCH_REPORT_DIR = FULLTEXT_DATA_DIR / "grobid_local_pdf_batch_reports"
DEFAULT_REPORT = FULLTEXT_DATA_DIR / "local_pdf_conversion_pipeline_report.json"

try:
    from pipeline.fulltext.convert_pdfs import DEFAULT_GROBID_URL, normalize_doi
    from pipeline.fulltext.convert_routed_local_pdfs import (
        DEFAULT_DOMAIN_ROUTING_TABLE,
        DEFAULT_OUT_DIR,
        DEFAULT_ROUTE_ACTION,
        DEFAULT_SUMMARY_JSON,
        DEFAULT_COUNTS_CSV,
        DEFAULT_FULLTEXT_DIR,
        DEFAULT_LITERATURE_TYPE_TABLE,
        DEFAULT_MANUAL_ROUTE_OVERRIDES,
        DEFAULT_METADATA_TABLE,
        DEFAULT_OUTPUT_TABLE,
        DEFAULT_PAPER_ROOT,
        DEFAULT_PRESCREEN_TABLE,
        read_doi_file,
        selected_pdf_rows,
    )
    from pipeline.fulltext.start_grobid import (
        DEFAULT_CONFIG as DEFAULT_GROBID_CONFIG,
        DEFAULT_CONTAINER as DEFAULT_GROBID_CONTAINER,
        DEFAULT_IMAGE as DEFAULT_GROBID_IMAGE,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    sys.path.insert(0, str(ROOT))
    from pipeline.fulltext.convert_pdfs import DEFAULT_GROBID_URL, normalize_doi
    from pipeline.fulltext.convert_routed_local_pdfs import (
        DEFAULT_DOMAIN_ROUTING_TABLE,
        DEFAULT_OUT_DIR,
        DEFAULT_ROUTE_ACTION,
        DEFAULT_SUMMARY_JSON,
        DEFAULT_COUNTS_CSV,
        DEFAULT_FULLTEXT_DIR,
        DEFAULT_LITERATURE_TYPE_TABLE,
        DEFAULT_MANUAL_ROUTE_OVERRIDES,
        DEFAULT_METADATA_TABLE,
        DEFAULT_OUTPUT_TABLE,
        DEFAULT_PAPER_ROOT,
        DEFAULT_PRESCREEN_TABLE,
        read_doi_file,
        selected_pdf_rows,
    )
    from pipeline.fulltext.start_grobid import (
        DEFAULT_CONFIG as DEFAULT_GROBID_CONFIG,
        DEFAULT_CONTAINER as DEFAULT_GROBID_CONTAINER,
        DEFAULT_IMAGE as DEFAULT_GROBID_IMAGE,
    )


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def shell_join(cmd: list[str]) -> str:
    return " ".join(shlex.quote(part) for part in cmd)


def chunked(values: list[str], size: int) -> Iterable[list[str]]:
    size = max(1, size)
    for index in range(0, len(values), size):
        yield values[index : index + size]


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_doi_batch_file(batch: list[str], batch_index: int, batch_dir: Path, prefix: str = "local_pdf") -> Path:
    batch_dir.mkdir(parents=True, exist_ok=True)
    path = batch_dir / f"{prefix}_grobid_batch_{batch_index:04d}.txt"
    path.write_text("\n".join(normalize_doi(doi) for doi in batch if normalize_doi(doi)) + "\n", encoding="utf-8")
    return path


def child_env() -> dict[str, str]:
    env = dict(os.environ)
    python_dir = str(Path(sys.executable).resolve().parent)
    current_path = env.get("PATH", "")
    env["PATH"] = os.pathsep.join(part for part in [python_dir, current_path] if part)
    return env


def run_command(cmd: list[str], *, label: str, cwd: Path, verbose: bool) -> dict:
    start = time.monotonic()
    print(f"[{label}] Running...", flush=True)
    if verbose:
        print(f"[{label}] {shell_join(cmd)}", flush=True)
    proc = subprocess.run(cmd, cwd=cwd, text=True, env=child_env())
    elapsed = round(time.monotonic() - start, 3)
    status = "ok" if proc.returncode == 0 else "failed"
    print(f"[{label}] {status} in {elapsed}s", flush=True)
    return {
        "label": label,
        "command": cmd,
        "returncode": proc.returncode,
        "status": status,
        "elapsed_sec": elapsed,
    }


def local_pdf_conversion_queue(args: argparse.Namespace) -> list[str]:
    route_table = Path(args.route_table).resolve()
    metadata_table = Path(args.metadata_table).resolve()
    routes_df = pd.read_parquet(route_table)
    metadata_df = pd.read_parquet(metadata_table) if metadata_table.exists() else pd.DataFrame()
    doi_filter = read_doi_file(Path(args.doi_file).resolve()) if args.doi_file.strip() else None
    rows, skipped = selected_pdf_rows(
        routes_df=routes_df,
        metadata_df=metadata_df,
        out_dir=Path(args.out_dir).resolve(),
        doi_filter=doi_filter,
        route_action=args.route_action,
        only_missing_artifacts=not bool(args.include_existing_artifacts),
    )
    if skipped:
        print(f"Queue skipped: {dict(skipped)}", flush=True)
    dois = [row["study_doi"] for row in rows]
    if args.limit > 0:
        dois = dois[: args.limit]
    return dois


def start_grobid_command(args: argparse.Namespace) -> list[str]:
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


def convert_batch_command(args: argparse.Namespace, doi_file: Path, report_path: Path) -> list[str]:
    cmd = [
        args.python,
        str(FULLTEXT_DIR / "convert_routed_local_pdfs.py"),
        "--backend",
        "grobid",
        "--doi-file",
        str(doi_file),
        "--report",
        str(report_path),
        "--route-table",
        str(Path(args.route_table).resolve()),
        "--metadata-table",
        str(Path(args.metadata_table).resolve()),
        "--prescreen-table",
        str(Path(args.prescreen_table).resolve()),
        "--literature-type-table",
        str(Path(args.literature_type_table).resolve()),
        "--fulltext-dir",
        str(Path(args.fulltext_dir).resolve()),
        "--out-dir",
        str(Path(args.out_dir).resolve()),
        "--paper-root",
        str(Path(args.paper_root).resolve()),
        "--route-summary-json",
        str(Path(args.route_summary_json).resolve()),
        "--route-counts-csv",
        str(Path(args.route_counts_csv).resolve()),
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
        "--no-rebuild-routes-after",
    ]
    if args.domain_routing_table.strip():
        cmd.extend(["--domain-routing-table", str(Path(args.domain_routing_table).resolve())])
    else:
        cmd.extend(["--domain-routing-table", ""])
    if args.manual_route_overrides.strip():
        cmd.extend(["--manual-route-overrides", str(Path(args.manual_route_overrides).resolve())])
    else:
        cmd.extend(["--manual-route-overrides", ""])
    if args.no_pdf_env_bootstrap:
        cmd.append("--no-pdf-env-bootstrap")
    if args.include_existing_artifacts:
        cmd.append("--include-existing-artifacts")
    if args.write_failed_artifacts:
        cmd.append("--write-failed-artifacts")
    return cmd


def rebuild_routes_command(args: argparse.Namespace) -> list[str]:
    cmd = [
        args.python,
        str(EXTRACT_DIR / "build_extraction_routes.py"),
        "--metadata-table",
        str(Path(args.metadata_table).resolve()),
        "--prescreen-decisions-table",
        str(Path(args.prescreen_table).resolve()),
        "--literature-type-table",
        str(Path(args.literature_type_table).resolve()),
        "--fulltext-dir",
        str(Path(args.fulltext_dir).resolve()),
        "--paper-root",
        str(Path(args.paper_root).resolve()),
        "--output-table",
        str(Path(args.route_table).resolve()),
        "--summary-json",
        str(Path(args.route_summary_json).resolve()),
        "--counts-csv",
        str(Path(args.route_counts_csv).resolve()),
    ]
    if args.domain_routing_table.strip():
        cmd.extend(["--domain-routing-table", str(Path(args.domain_routing_table).resolve())])
    else:
        cmd.extend(["--domain-routing-table", ""])
    if args.manual_route_overrides.strip():
        cmd.extend(["--manual-route-overrides", str(Path(args.manual_route_overrides).resolve())])
    else:
        cmd.extend(["--manual-route-overrides", ""])
    return cmd


def failed_dois_from_report(report_path: Path) -> list[str]:
    if not report_path.exists():
        return []
    try:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
    except Exception:
        return []
    failed = []
    for record in payload.get("records", []):
        if not isinstance(record, dict):
            continue
        doi = normalize_doi(record.get("study_doi", ""))
        if doi and not str(record.get("best_backend", "")).strip():
            failed.append(doi)
    return failed


def run_batch(args: argparse.Namespace, batch: list[str], batch_index: int, batch_dir: Path, report_dir: Path) -> dict:
    batch_file = write_doi_batch_file(batch, batch_index, batch_dir)
    report_path = report_dir / f"local_pdf_grobid_batch_{batch_index:04d}.json"
    result: dict = {
        "batch_index": batch_index,
        "doi_count": len(batch),
        "doi_file": str(batch_file),
        "report": str(report_path),
        "start": None,
        "convert": None,
        "failed_dois": [],
        "single_retries": [],
    }
    if not args.skip_grobid_managed_start and (args.grobid_restart_each_batch or batch_index == 1):
        start_result = run_command(
            start_grobid_command(args),
            label=f"grobid_start_{batch_index:04d}",
            cwd=Path(args.child_cwd).resolve(),
            verbose=args.verbose,
        )
        result["start"] = start_result
        if start_result["returncode"] != 0:
            result["failed_dois"] = list(batch)
            return result

    convert_result = run_command(
        convert_batch_command(args, batch_file, report_path),
        label=f"convert_local_pdf_grobid_batch_{batch_index:04d}",
        cwd=Path(args.child_cwd).resolve(),
        verbose=args.verbose,
    )
    result["convert"] = convert_result
    failed_dois = failed_dois_from_report(report_path)
    if convert_result["returncode"] != 0 and not failed_dois:
        failed_dois = list(batch)
    result["failed_dois"] = failed_dois
    return result


def retry_single_failures(
    args: argparse.Namespace,
    failed_dois: list[str],
    batch_index: int,
    batch_dir: Path,
    report_dir: Path,
) -> list[dict]:
    retries: list[dict] = []
    if not args.retry_failures_single or not failed_dois:
        return retries
    for retry_index, doi in enumerate(failed_dois, start=1):
        single_file = write_doi_batch_file([doi], batch_index * 10000 + retry_index, batch_dir, prefix="local_pdf_retry")
        report_path = report_dir / f"local_pdf_grobid_batch_{batch_index:04d}_retry_{retry_index:04d}.json"
        retry_record: dict = {
            "doi": doi,
            "doi_file": str(single_file),
            "report": str(report_path),
            "start": None,
            "convert": None,
            "failed_after_retry": [],
        }
        if not args.skip_grobid_managed_start:
            retry_record["start"] = run_command(
                start_grobid_command(args),
                label=f"grobid_start_{batch_index:04d}_retry_{retry_index:04d}",
                cwd=Path(args.child_cwd).resolve(),
                verbose=args.verbose,
            )
        retry_record["convert"] = run_command(
            convert_batch_command(args, single_file, report_path),
            label=f"convert_local_pdf_retry_{batch_index:04d}_{retry_index:04d}",
            cwd=Path(args.child_cwd).resolve(),
            verbose=args.verbose,
        )
        retry_record["failed_after_retry"] = failed_dois_from_report(report_path)
        if retry_record["convert"]["returncode"] != 0 and not retry_record["failed_after_retry"]:
            retry_record["failed_after_retry"] = [doi]
        retries.append(retry_record)
    return retries


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--route-table", default=str(DEFAULT_OUTPUT_TABLE))
    parser.add_argument("--metadata-table", default=str(DEFAULT_METADATA_TABLE))
    parser.add_argument("--prescreen-table", default=str(DEFAULT_PRESCREEN_TABLE))
    parser.add_argument("--literature-type-table", default=str(DEFAULT_LITERATURE_TYPE_TABLE))
    parser.add_argument("--domain-routing-table", default=str(DEFAULT_DOMAIN_ROUTING_TABLE))
    parser.add_argument("--fulltext-dir", default=str(DEFAULT_FULLTEXT_DIR))
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--paper-root", default=str(DEFAULT_PAPER_ROOT))
    parser.add_argument("--route-summary-json", default=str(DEFAULT_SUMMARY_JSON))
    parser.add_argument("--route-counts-csv", default=str(DEFAULT_COUNTS_CSV))
    parser.add_argument("--manual-route-overrides", default=str(DEFAULT_MANUAL_ROUTE_OVERRIDES))
    parser.add_argument("--doi-file", default="", help="Optional DOI list to restrict local PDF conversion.")
    parser.add_argument("--route-action", default=DEFAULT_ROUTE_ACTION)
    parser.add_argument("--limit", type=int, default=0, help="Maximum queued DOIs to process; 0 means all.")
    parser.add_argument("--batch-size", type=int, default=25)
    parser.add_argument("--batch-dir", default=str(DEFAULT_BATCH_DIR))
    parser.add_argument("--batch-report-dir", default=str(DEFAULT_BATCH_REPORT_DIR))
    parser.add_argument("--out-report", default=str(DEFAULT_REPORT))
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--child-cwd", default="/tmp")
    parser.add_argument("--include-existing-artifacts", action="store_true")
    parser.add_argument("--write-failed-artifacts", action="store_true")
    parser.add_argument("--no-pdf-env-bootstrap", action="store_true")
    parser.add_argument("--continue-on-error", action="store_true")
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--skip-route-rebuild", action="store_true")
    parser.add_argument("--retry-failures-single", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--grobid-url", default=DEFAULT_GROBID_URL)
    parser.add_argument("--grobid-timeout-sec", type=int, default=120)
    parser.add_argument("--grobid-retries", type=int, default=2)
    parser.add_argument("--grobid-retry-wait-sec", type=int, default=5)
    parser.add_argument("--grobid-consolidate-header", choices=["0", "1", "2", "3"], default="0")
    parser.add_argument("--grobid-consolidate-citations", choices=["0", "1", "2"], default="0")
    parser.add_argument("--grobid-image", default=DEFAULT_GROBID_IMAGE)
    parser.add_argument("--grobid-container", default=DEFAULT_GROBID_CONTAINER)
    parser.add_argument("--grobid-config", default=str(DEFAULT_GROBID_CONFIG))
    parser.add_argument("--grobid-concurrency", type=int, default=1)
    parser.add_argument("--grobid-pdfalto-memory-mb", type=int, default=1024)
    parser.add_argument("--grobid-memory", default="5g")
    parser.add_argument("--grobid-start-wait-sec", type=int, default=90)
    parser.add_argument("--recreate-grobid-config", action="store_true")
    parser.add_argument("--skip-grobid-managed-start", action="store_true")
    parser.add_argument("--grobid-restart-each-batch", action=argparse.BooleanOptionalAction, default=True)
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    report_path = Path(args.out_report).resolve()
    batch_dir = Path(args.batch_dir).resolve()
    report_dir = Path(args.batch_report_dir).resolve()
    report_dir.mkdir(parents=True, exist_ok=True)

    queue = local_pdf_conversion_queue(args)
    batch_size = max(1, args.batch_size)
    batches = list(chunked(queue, batch_size))
    print("=== Local PDF Conversion Pipeline ===", flush=True)
    print(f"Queued DOIs: {len(queue):,}", flush=True)
    print(f"Batch size: {batch_size:,}", flush=True)
    print(f"Batches: {len(batches):,}", flush=True)
    print(f"GROBID restart each batch: {'yes' if args.grobid_restart_each_batch else 'no'}", flush=True)
    print(f"Single retries: {'yes' if args.retry_failures_single else 'no'}", flush=True)

    if args.plan_only:
        if batches:
            sample_file = batch_dir / "local_pdf_grobid_batch_0001.txt"
            sample_report = report_dir / "local_pdf_grobid_batch_0001.json"
            print(f"[grobid_start] {shell_join(start_grobid_command(args))}", flush=True)
            print(f"[convert_batch] {shell_join(convert_batch_command(args, sample_file, sample_report))}", flush=True)
        print(f"Run report: {report_path}", flush=True)
        return 0

    results = []
    final_failed: set[str] = set()
    overall_status = "ok"
    for batch_index, batch in enumerate(batches, start=1):
        result = run_batch(args, batch, batch_index, batch_dir, report_dir)
        failed = list(result.get("failed_dois", []))
        if failed and len(batch) > 1:
            retries = retry_single_failures(args, failed, batch_index, batch_dir, report_dir)
            result["single_retries"] = retries
            retry_failed = {
                doi
                for retry in retries
                for doi in retry.get("failed_after_retry", [])
            }
            failed = sorted(retry_failed)
        final_failed.update(failed)
        results.append(result)

        batch_failed = bool(failed)
        command_failed = any(
            stage
            and isinstance(stage, dict)
            and int(stage.get("returncode", 0) or 0) != 0
            for stage in [result.get("start"), result.get("convert")]
        )
        if command_failed:
            overall_status = "failed"
        elif batch_failed and overall_status == "ok":
            overall_status = "completed_with_pdf_failures"
        if command_failed and not args.continue_on_error:
            break

    route_rebuild = None
    if not args.skip_route_rebuild:
        rebuild = run_command(
            rebuild_routes_command(args),
            label="route_rebuild",
            cwd=Path(args.child_cwd).resolve(),
            verbose=args.verbose,
        )
        route_rebuild = rebuild
        if rebuild["returncode"] != 0:
            overall_status = "failed"

    payload = {
        "generated_at_utc": now_utc(),
        "status": overall_status,
        "queue_size": len(queue),
        "batch_size": batch_size,
        "batch_count": len(batches),
        "final_failed_dois": sorted(final_failed),
        "route_rebuild": route_rebuild,
        "results": results,
    }
    write_json(report_path, payload)
    print(f"Run status: {overall_status}", flush=True)
    print(f"Run report: {report_path}", flush=True)
    return 0 if overall_status in {"ok", "completed_with_pdf_failures"} or args.continue_on_error else 1


if __name__ == "__main__":
    raise SystemExit(main())
