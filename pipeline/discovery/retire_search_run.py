#!/usr/bin/env python3
"""Retire an unpromoted discovery run while preserving a compact audit bundle."""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
import shutil
import sys

import pandas as pd
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.discovery.providers import utc_now
from pipeline.discovery.runner import atomic_write_json, read_json


DEFAULT_RUN_ROOT = ROOT / "data" / "processed" / "discovery" / "runs"
DEFAULT_ARCHIVE_ROOT = ROOT / "data" / "processed" / "discovery" / "retired_runs"
PROMOTION_REPORT_NAME = "discovery_promotion_report.json"
PRESERVED_FILES = ("run_manifest.json", "search_plan.parquet", "query_executions.parquet")


def directory_size(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def file_inventory(path: Path) -> list[dict]:
    return [
        {"path": str(item.relative_to(path)), "size_bytes": item.stat().st_size}
        for item in sorted(path.rglob("*"))
        if item.is_file()
    ]


def summarize_state(path: Path) -> dict:
    if not path.exists():
        return {"available": False}
    state = read_json(path)
    executions = state.get("executions", {})
    values = list(executions.values()) if isinstance(executions, dict) else list(executions)
    return {
        "available": True,
        "updated_at_utc": state.get("updated_at_utc", ""),
        "execution_count": len(values),
        "status_counts": dict(sorted(Counter(row.get("status", "unknown") for row in values).items())),
        "expected_total": sum(int(row.get("expected_total", 0) or 0) for row in values),
        "retrieved_total": sum(int(row.get("retrieved_total", 0) or 0) for row in values),
        "page_count": sum(int(row.get("page_count", 0) or 0) for row in values),
        "count_request_count": sum(int(row.get("count_request_count", 0) or 0) for row in values),
        "execution_errors": sum(bool(row.get("error")) for row in values),
    }


def exclusive_direct_pair_records(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    hits = pd.read_parquet(path)
    if "search_type" not in hits or "provider_record_id" not in hits:
        return pd.DataFrame()
    pair = hits.loc[hits["search_type"].eq("direct_pair")].copy()
    if pair.empty:
        return pair
    non_pair_ids = set(
        hits.loc[~hits["search_type"].eq("direct_pair"), "provider_record_id"]
        .fillna("")
        .astype(str)
    )
    exclusive = pair.loc[
        ~pair["provider_record_id"].fillna("").astype(str).isin(non_pair_ids)
    ].drop_duplicates("provider_record_id")
    columns = [
        "provider",
        "provider_record_id",
        "doi",
        "pmid",
        "pmcid",
        "openalex_id",
        "title",
        "authors",
        "publication_year",
        "publication_date",
        "journal",
        "publication_type",
        "abstract",
        "compound",
        "entity",
        "entity_type",
        "search_id",
        "execution_id",
    ]
    return exclusive[[column for column in columns if column in exclusive]].reset_index(drop=True)


def retire_run(
    *,
    run_dir: Path,
    archive_root: Path = DEFAULT_ARCHIVE_ROOT,
    reason: str,
    apply: bool = False,
) -> dict:
    run_dir = Path(run_dir).resolve()
    if not run_dir.is_dir():
        raise FileNotFoundError(f"Run directory not found: {run_dir}")
    manifest_path = run_dir / "run_manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Run manifest not found: {manifest_path}")
    manifest = read_json(manifest_path)
    run_id = str(manifest.get("run_id") or run_dir.name)
    if manifest.get("status") == "promoted" or (run_dir / PROMOTION_REPORT_NAME).exists():
        raise RuntimeError("Refusing to retire a promoted run")
    if manifest.get("status") == "complete" and manifest.get("completion_gate_passed"):
        raise RuntimeError("Refusing to retire a complete promotable run; review or promote it first")

    archive_dir = Path(archive_root).resolve() / run_id
    if archive_dir.exists():
        raise FileExistsError(f"Retirement archive already exists: {archive_dir}")

    inventory = file_inventory(run_dir)
    state_summary = summarize_state(run_dir / "run_state.json")
    exclusive = exclusive_direct_pair_records(run_dir / "provider_hits.parquet")
    retrieved_path = run_dir / "retrieved_records.parquet"
    retrieved_record_count = (
        pq.ParquetFile(retrieved_path).metadata.num_rows if retrieved_path.exists() else 0
    )
    report = {
        "schema_version": "discovery_run_retirement_v1",
        "run_id": run_id,
        "protocol_id": manifest.get("protocol_id", ""),
        "retired_at_utc": utc_now(),
        "reason": reason,
        "original_status": manifest.get("status", ""),
        "completion_gate_passed": bool(manifest.get("completion_gate_passed", False)),
        "promotion_report_present": False,
        "applied": bool(apply),
        "original_run_directory": str(run_dir),
        "archive_directory": str(archive_dir),
        "original_size_bytes": directory_size(run_dir),
        "original_files": inventory,
        "preserved_files": [name for name in PRESERVED_FILES if (run_dir / name).exists()],
        "discarded_files": [row["path"] for row in inventory if row["path"] not in PRESERVED_FILES],
        "state_summary": state_summary,
        "retrieved_record_count": retrieved_record_count,
        "exclusive_direct_pair_record_count": len(exclusive),
        "exclusive_direct_pair_records_file": (
            "exclusive_direct_pair_records.csv" if not exclusive.empty else ""
        ),
    }
    if not apply:
        return report

    archive_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary = archive_dir.with_name(archive_dir.name + ".tmp")
    if temporary.exists():
        shutil.rmtree(temporary)
    temporary.mkdir(parents=True)
    try:
        for name in PRESERVED_FILES:
            source = run_dir / name
            if source.exists():
                shutil.copy2(source, temporary / name)
        atomic_write_json(temporary / "run_state_summary.json", state_summary)
        if not exclusive.empty:
            exclusive.to_csv(temporary / "exclusive_direct_pair_records.csv", index=False)
        report["retained_size_bytes"] = directory_size(temporary)
        report["reclaimed_size_bytes"] = max(
            0, report["original_size_bytes"] - report["retained_size_bytes"]
        )
        atomic_write_json(temporary / "retirement_report.json", report)
        temporary.replace(archive_dir)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    shutil.rmtree(run_dir)
    return report


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Archive the audit essentials and delete the bulk artifacts of an unpromoted run."
    )
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-root", default=str(DEFAULT_RUN_ROOT))
    parser.add_argument("--archive-root", default=str(DEFAULT_ARCHIVE_ROOT))
    parser.add_argument("--reason", required=True)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Perform retirement. Without this flag, report the proposed cleanup only.",
    )
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    report = retire_run(
        run_dir=Path(args.run_root) / args.run_id,
        archive_root=Path(args.archive_root),
        reason=args.reason,
        apply=args.apply,
    )
    print(f"Run ID: {report['run_id']}")
    print(f"Applied: {report['applied']}")
    print(f"Original size bytes: {report['original_size_bytes']}")
    print(f"Retrieved records: {report['retrieved_record_count']}")
    print(f"Exclusive direct-pair records: {report['exclusive_direct_pair_record_count']}")
    if report["applied"]:
        print(f"Archive: {report['archive_directory']}")
        print(f"Reclaimed size bytes: {report['reclaimed_size_bytes']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
