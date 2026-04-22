#!/usr/bin/env python3
"""Export DOI queues from cumulative discovery ledgers without rerunning search."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.ingest.discover_literature import normalize, normalize_doi, now_utc, write_queue  # noqa: E402


def doi_key(raw: object) -> str:
    return normalize_doi(raw).lower()


def load_ledger_payload(path: Path, dataset: str) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Discovery ledger not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"Ledger is not a JSON object: {path}")
    if normalize(payload.get("dataset", "")) != dataset:
        raise ValueError(f"Ledger dataset mismatch: expected {dataset}, found {payload.get('dataset')}")
    return payload


def choose_context(entry: dict) -> dict:
    contexts = entry.get("contexts", [])
    if not isinstance(contexts, list):
        return {}

    valid = [context for context in contexts if isinstance(context, dict)]
    if not valid:
        return {}

    preferred_prefixes = ("discovery:", "benchmark:", "curated", "triage_queue", "paper_library")
    for prefix in preferred_prefixes:
        for context in valid:
            if normalize(context.get("source", "")).startswith(prefix):
                return context
    return valid[0]


def row_from_entry(entry: dict) -> dict:
    context = choose_context(entry)
    return {
        "doi": normalize(entry.get("doi", "")),
        "compound": normalize(context.get("compound", "")),
        "entity": normalize(context.get("entity", "")),
        "title": normalize(entry.get("title", "")) or normalize(context.get("study_title", "")),
        "year": normalize(entry.get("year", "")) or normalize(context.get("study_year", "")),
        "authors": normalize(entry.get("authors", "")),
        "seen_in_latest_run": bool(entry.get("seen_in_latest_run")),
        "retained_in_latest_queue": bool(entry.get("retained_in_latest_queue")),
        "is_benchmark": bool(entry.get("is_benchmark")),
        "is_curated": bool(entry.get("is_curated")),
        "in_paper_library": bool(entry.get("in_paper_library")),
        "in_triage_queue": bool(entry.get("in_triage_queue")),
    }


def latest_rows_from_ledger(payload: dict, include_history: bool) -> List[dict]:
    entries = payload.get("entries", [])
    if not isinstance(entries, list):
        return []
    rows = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if not include_history and not entry.get("seen_in_latest_run"):
            continue
        if not doi_key(entry.get("doi", "")):
            continue
        rows.append(row_from_entry(entry))
    return rows


def year_sort_value(row: dict) -> int:
    try:
        return int(normalize(row.get("year", "")) or 0)
    except ValueError:
        return 0


def ledger_priority(row: dict) -> tuple:
    protected = bool(
        row.get("is_benchmark")
        or row.get("is_curated")
        or row.get("in_paper_library")
        or row.get("in_triage_queue")
    )
    return (
        not protected,
        not row.get("retained_in_latest_queue", False),
        -year_sort_value(row),
        normalize(row.get("title", "")).lower(),
        doi_key(row.get("doi", "")),
    )


def read_queue_rows(path: Path, dataset: str) -> List[dict]:
    if not path.exists():
        return []
    entity_name = "target" if dataset == "mechanistic" else "disorder"
    rows: List[dict] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(line for line in handle if not line.startswith("#"))
        for record in reader:
            if len(record) < 1:
                continue
            record = record + [""] * (6 - len(record))
            rows.append(
                {
                    "doi": normalize(record[0]),
                    "compound": normalize(record[1]),
                    "entity": normalize(record[2]),
                    "title": normalize(record[3]),
                    "year": normalize(record[4]),
                    "authors": normalize(record[5]),
                    "queue_entity_name": entity_name,
                }
            )
    return rows


def build_export_rows(
    ledger_rows: List[dict],
    current_queue_rows: List[dict],
    max_results: int,
    preserve_current_order: bool = True,
) -> List[dict]:
    by_doi: Dict[str, dict] = {doi_key(row.get("doi", "")): row for row in ledger_rows if doi_key(row.get("doi", ""))}
    selected: List[dict] = []
    seen = set()

    if preserve_current_order:
        for queue_row in current_queue_rows:
            key = doi_key(queue_row.get("doi", ""))
            if not key or key in seen or key not in by_doi:
                continue
            merged = {**by_doi[key], **{k: v for k, v in queue_row.items() if normalize(v)}}
            selected.append(merged)
            seen.add(key)
            if max_results > 0 and len(selected) >= max_results:
                return selected

    remaining = [row for row in ledger_rows if doi_key(row.get("doi", "")) not in seen]
    remaining.sort(key=ledger_priority)
    for row in remaining:
        key = doi_key(row.get("doi", ""))
        if not key or key in seen:
            continue
        selected.append(row)
        seen.add(key)
        if max_results > 0 and len(selected) >= max_results:
            break
    return selected


def export_queue_from_ledger(
    dataset: str,
    ledger_path: Path,
    queue_out: Path,
    report_out: Path,
    max_results: int,
    include_history: bool,
    preserve_current_order: bool,
) -> dict:
    payload = load_ledger_payload(ledger_path, dataset)
    ledger_rows = latest_rows_from_ledger(payload, include_history=include_history)
    current_queue_rows = read_queue_rows(queue_out, dataset) if preserve_current_order else []
    rows = build_export_rows(
        ledger_rows=ledger_rows,
        current_queue_rows=current_queue_rows,
        max_results=max_results,
        preserve_current_order=preserve_current_order,
    )
    write_queue(queue_out, rows, dataset)
    retained_count = sum(1 for row in ledger_rows if row.get("retained_in_latest_queue"))
    summary = {
        "generated_at_utc": now_utc(),
        "dataset": dataset,
        "ledger": str(ledger_path),
        "queue_out": str(queue_out),
        "report_out": str(report_out),
        "ledger_rows_considered": len(ledger_rows),
        "previous_retained_rows": retained_count,
        "exported_rows": len(rows),
        "recovered_rows_over_previous_retained": max(0, len(rows) - retained_count),
        "max_results": max_results,
        "include_history": include_history,
        "preserve_current_order": preserve_current_order,
    }
    report_out.parent.mkdir(parents=True, exist_ok=True)
    report_out.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Export an uncapped discovery queue from a discovery ledger")
    parser.add_argument("--dataset", choices=["mechanistic", "disorder"], required=True)
    parser.add_argument("--ledger", default="")
    parser.add_argument("--queue-out", default="")
    parser.add_argument("--report-out", default="")
    parser.add_argument("--max-results", type=int, default=0, help="0 exports all selected ledger rows")
    parser.add_argument(
        "--include-history",
        action="store_true",
        help="Include older ledger entries not seen in the latest discovery run",
    )
    parser.add_argument(
        "--no-preserve-current-order",
        action="store_true",
        help="Do not preserve the existing queue order before appending recovered rows",
    )
    args = parser.parse_args()

    ledger_path = (
        Path(args.ledger).resolve()
        if args.ledger
        else ROOT / "data" / "processed" / f"discovery_ledger_{args.dataset}.json"
    )
    queue_out = (
        Path(args.queue_out).resolve()
        if args.queue_out
        else ROOT / "data" / "raw" / f"doi_queue.{args.dataset}.discovered.txt"
    )
    report_out = (
        Path(args.report_out).resolve()
        if args.report_out
        else ROOT / "data" / "processed" / f"discovery_queue_export_{args.dataset}.json"
    )
    summary = export_queue_from_ledger(
        dataset=args.dataset,
        ledger_path=ledger_path,
        queue_out=queue_out,
        report_out=report_out,
        max_results=max(0, args.max_results),
        include_history=args.include_history,
        preserve_current_order=not args.no_preserve_current_order,
    )

    print(f"Dataset: {summary['dataset']}")
    print(f"Ledger rows considered: {summary['ledger_rows_considered']}")
    print(f"Previous retained rows: {summary['previous_retained_rows']}")
    print(f"Exported rows: {summary['exported_rows']}")
    print(f"Recovered rows over previous retained: {summary['recovered_rows_over_previous_retained']}")
    print(f"Queue: {summary['queue_out']}")
    print(f"Report: {summary['report_out']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
