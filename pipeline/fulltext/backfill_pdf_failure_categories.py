#!/usr/bin/env python3
"""Backfill PDF download failure categories into the corpus table."""

from __future__ import annotations

import argparse
from collections import Counter
import datetime as dt
import glob
import json
from pathlib import Path
import sys

import pandas as pd

try:
    from pipeline.fulltext.download_routed_pdfs import classify_download_failure, clean, doi_key
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from pipeline.fulltext.download_routed_pdfs import classify_download_failure, clean, doi_key


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CANDIDATE_TABLE = ROOT / "data" / "processed" / "corpus" / "candidate_papers.parquet"
DEFAULT_REPORT_JSON = ROOT / "data" / "processed" / "corpus" / "audits" / "pdf_failure_category_backfill_report.json"
DEFAULT_AUDIT_GLOB = str(ROOT / "data" / "processed" / "corpus" / "audits" / "routed_pdf_download_*report.json")
DEFAULT_LEGACY_JSONS = (
    ROOT / "data" / "processed" / "paper_library_mechanistic.json",
    ROOT / "data" / "processed" / "paper_library_disorder.json",
)
FAILURE_STATUSES = {
    "download_failed",
    "invalid_pdf_content",
    "invalid_pdf_existing",
    "no_pdf_url",
    "not_open_access",
}


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def load_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def failure_text_is_better(new_text: str, old_text: str) -> bool:
    if not old_text:
        return True
    if "HTTPError" in new_text and "HTTPError" not in old_text:
        return True
    return len(new_text) > len(old_text)


def load_legacy_failure_texts(paths: list[Path]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for path in paths:
        payload = load_json(path)
        if not isinstance(payload, list):
            continue
        for row in payload:
            if not isinstance(row, dict):
                continue
            doi = doi_key(row.get("study_doi", "") or row.get("doi", ""))
            if not doi:
                continue
            status = clean(row.get("pdf_download_status", ""))
            error = clean(row.get("action_reason", "")) or clean(row.get("pdf_download_error", ""))
            if status not in FAILURE_STATUSES and not error:
                continue
            current = out.get(doi, {})
            if failure_text_is_better(error, clean(current.get("error", ""))):
                out[doi] = {
                    "status": status,
                    "error": error,
                    "source": str(path),
                }
    return out


def load_report_failure_texts(paths: list[Path]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for path in paths:
        payload = load_json(path)
        if not isinstance(payload, dict):
            continue
        for row in payload.get("records", []):
            if not isinstance(row, dict):
                continue
            doi = doi_key(row.get("doi", ""))
            if not doi:
                continue
            status = clean(row.get("status", ""))
            if status in {"", "downloaded", "already_present", "dry_run"}:
                continue
            error = clean(row.get("error", ""))
            current = out.get(doi, {})
            if failure_text_is_better(error, clean(current.get("error", ""))):
                out[doi] = {
                    "status": status,
                    "error": error,
                    "source": str(path),
                }
    return out


def ensure_columns(df: pd.DataFrame) -> pd.DataFrame:
    defaults = {
        "pdf_download_error": "",
        "pdf_download_failure_category": "",
        "pdf_download_failure_categories": "",
        "pdf_download_retry_recommended": False,
    }
    for column, default in defaults.items():
        if column not in df.columns:
            df[column] = default
    return df


def backfill_pdf_failure_categories(
    *,
    candidate_table: Path = DEFAULT_CANDIDATE_TABLE,
    legacy_jsons: list[Path] | None = None,
    audit_report_paths: list[Path] | None = None,
    report_json: Path = DEFAULT_REPORT_JSON,
    overwrite: bool = False,
    dry_run: bool = False,
) -> dict:
    df = pd.read_parquet(candidate_table)
    df = ensure_columns(df)
    legacy_map = load_legacy_failure_texts(legacy_jsons or list(DEFAULT_LEGACY_JSONS))
    report_map = load_report_failure_texts(audit_report_paths or sorted(Path(path) for path in glob.glob(DEFAULT_AUDIT_GLOB)))
    failure_map = {**legacy_map, **report_map}

    updated = 0
    missing_error_text = 0
    category_counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()

    for index, row in df.iterrows():
        doi = doi_key(row.get("doi", ""))
        if not doi:
            continue
        status = clean(row.get("pdf_download_status", ""))
        if status not in FAILURE_STATUSES:
            continue
        if clean(row.get("pdf_download_failure_category", "")) and not overwrite:
            continue

        source_record = failure_map.get(doi, {})
        error = clean(source_record.get("error", ""))
        source = clean(source_record.get("source", ""))
        if not error and status in {"no_pdf_url", "not_open_access"}:
            error = status
        if not error:
            missing_error_text += 1
        failure = classify_download_failure(status, error)
        if not failure["failure_category"] and status == "not_open_access":
            failure = {
                "failure_category": "not_open_access",
                "failure_categories": "not_open_access",
                "retry_recommended": False,
            }

        updates = {
            "pdf_download_error": error,
            "pdf_download_failure_category": failure["failure_category"],
            "pdf_download_failure_categories": failure["failure_categories"],
            "pdf_download_retry_recommended": bool(failure["retry_recommended"]),
        }
        changed = False
        for field, value in updates.items():
            if clean(row.get(field, "")) != clean(value):
                changed = True
                if not dry_run:
                    df.at[index, field] = value
        if changed:
            updated += 1
        category = clean(failure["failure_category"]) or "uncategorized"
        category_counts[category] += 1
        source_counts[source or "no_error_text"] += 1

    if not dry_run:
        df.to_parquet(candidate_table, engine="pyarrow", index=False)

    report = {
        "generated_at_utc": now_utc(),
        "candidate_table": str(candidate_table.resolve()),
        "dry_run": dry_run,
        "overwrite": overwrite,
        "counts": {
            "updated_rows": updated,
            "missing_error_text": missing_error_text,
            "failure_category": dict(category_counts),
            "source": dict(source_counts),
            "legacy_failure_texts": len(legacy_map),
            "report_failure_texts": len(report_map),
        },
    }
    report_json.parent.mkdir(parents=True, exist_ok=True)
    report_json.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Backfill PDF download failure categories into candidate_papers.parquet.")
    parser.add_argument("--candidate-table", default=str(DEFAULT_CANDIDATE_TABLE))
    parser.add_argument("--legacy-json", action="append", default=[])
    parser.add_argument("--audit-report-glob", default=DEFAULT_AUDIT_GLOB)
    parser.add_argument("--report-json", default=str(DEFAULT_REPORT_JSON))
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    legacy_jsons = [Path(path).resolve() for path in args.legacy_json] if args.legacy_json else list(DEFAULT_LEGACY_JSONS)
    audit_report_paths = sorted(Path(path) for path in glob.glob(args.audit_report_glob))
    report = backfill_pdf_failure_categories(
        candidate_table=Path(args.candidate_table).resolve(),
        legacy_jsons=legacy_jsons,
        audit_report_paths=audit_report_paths,
        report_json=Path(args.report_json).resolve(),
        overwrite=bool(args.overwrite),
        dry_run=bool(args.dry_run),
    )
    counts = report["counts"]
    print(f"Updated rows: {counts['updated_rows']:,}")
    print(f"Missing error text: {counts['missing_error_text']:,}")
    print(f"Failure categories: {counts['failure_category']}")
    print(f"Dry run: {report['dry_run']}")
    print(f"Report: {Path(args.report_json).resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
