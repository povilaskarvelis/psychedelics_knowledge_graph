#!/usr/bin/env python3
"""Reconcile successful retry and manual-fallback rows into a Gemini batch queue."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import sys
import tempfile

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.fulltext.convert_pdfs import normalize_doi
from pipeline.review.advance_gemini_domain_routing_batch_queue import part_output_paths, read_json
from pipeline.review.run_gemini_domain_routing import (
    build_summary,
    merged_routing_metadata,
    normalize_payload,
    parsed_rows_from_raw,
    read_table,
    route_rows_from_parsed,
    write_counts_csv,
    write_json,
)


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def read_jsonl(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_jsonl_atomic(path: Path, rows: list[dict]) -> None:
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        with temporary.open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def write_parquet_atomic(path: Path, rows: list[dict]) -> None:
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".parquet", dir=path.parent)
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        pd.DataFrame(rows).to_parquet(temporary, index=False)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def retry_rows(queue_paths: list[Path]) -> dict[str, dict]:
    recovered: dict[str, dict] = {}
    for queue_path in queue_paths:
        queue = read_json(queue_path)
        for part in queue.get("parts", []):
            raw_path = Path(part["raw_jsonl"]).resolve()
            if not raw_path.exists():
                continue
            for row in read_jsonl(raw_path):
                doi = normalize_doi(row.get("doi", ""))
                if doi and row.get("status") == "ok":
                    recovered[doi] = {**row, "reconciliation_source": str(queue_path.resolve())}
    return recovered


def manual_rows(path: Path) -> dict[str, dict]:
    payload = read_json(path)
    out: dict[str, dict] = {}
    for record in payload.get("records", []):
        doi = normalize_doi(record.get("doi", ""))
        if not doi:
            continue
        parsed = normalize_payload(record)
        out[doi] = {
            "generated_at_utc": now_utc(),
            "doi": doi,
            "model": "manual_review_after_gemini-3-flash-preview_block",
            "status": "ok",
            "response_text": json.dumps(parsed, ensure_ascii=False),
            "parsed": parsed,
            "usage": {},
            "batch_key": "",
            "batch_line_index": 0,
            "batch_error": "",
            "error": "",
            "reconciliation_source": str(path.resolve()),
            "reconciliation_method": "manual_title_abstract_fallback_after_repeated_model_block",
        }
    return out


def reconcile(args: argparse.Namespace) -> dict:
    queue_path = Path(args.queue_json).resolve()
    queue = read_json(queue_path)
    retries = retry_rows([Path(value).resolve() for value in args.retry_queue_json])
    manuals = manual_rows(Path(args.manual_fallback_json).resolve())
    metadata = merged_routing_metadata(
        read_table(Path(queue["inputs"]["candidate_table"]).resolve()),
        read_table(Path(queue["inputs"]["metadata_table"]).resolve()),
    )
    prescreen = read_table(Path(queue["inputs"]["prescreen_decisions_table"]).resolve())
    recovered_dois: list[str] = []
    manual_dois: list[str] = []

    for part in queue.get("parts", []):
        raw_path = Path(part["raw_jsonl"]).resolve()
        rows = read_jsonl(raw_path)
        replaced: list[dict] = []
        for index, row in enumerate(rows):
            if row.get("status") == "ok":
                continue
            doi = normalize_doi(row.get("doi", ""))
            replacement = retries.get(doi) or manuals.get(doi)
            if replacement is None:
                raise RuntimeError(f"No successful retry or manual fallback for {doi}")
            replacement = dict(replacement)
            replacement["original_batch_key"] = row.get("batch_key", "")
            replacement["original_batch_line_index"] = row.get("batch_line_index", 0)
            rows[index] = replacement
            method = "retry" if doi in retries else "manual_fallback"
            replaced.append({"doi": doi, "method": method, "source": replacement["reconciliation_source"]})
            (recovered_dois if method == "retry" else manual_dois).append(doi)

        if any(row.get("status") != "ok" for row in rows):
            raise RuntimeError(f"Part {part['part']} still contains non-ok rows")
        if len(rows) != int(part["requests"]):
            raise RuntimeError(f"Part {part['part']} row count changed: {len(rows)} != {part['requests']}")
        write_jsonl_atomic(raw_path, rows)

        parsed = parsed_rows_from_raw(raw_path, metadata, prescreen)
        routes = route_rows_from_parsed(parsed, now_utc())
        manual_set = set(manuals)
        for route in routes:
            if normalize_doi(route.get("doi", "")) not in manual_set:
                continue
            route["literature_type_confidence"] = "manual"
            route["domain_route_basis"] = "Manual title/abstract fallback after repeated Gemini content block: " + route["screening_reason"]
            route["tag_source_fields"] = "manual_review_after_gemini_block"
        paths = part_output_paths(queue, part)
        write_parquet_atomic(paths["route_table"], routes)
        summary, counts = build_summary(
            routes,
            inputs={"reconciled_raw_jsonl": str(raw_path), "main_queue_json": str(queue_path)},
        )
        write_json(paths["summary_json"], summary)
        write_counts_csv(paths["counts_csv"], counts)

        report_path = Path(part["report_json"]).resolve()
        report = read_json(report_path)
        original = {
            "status": report.get("status", ""),
            "status_counts": report.get("summary", {}).get("status_counts", {}),
        }
        report["status"] = "ok"
        report.setdefault("summary", {})["status_counts"] = {"ok": len(rows)}
        report["summary"].update(
            {
                "raw_outputs": len(rows),
                "parsed_outputs": len(parsed),
                "route_rows": len(routes),
                "routed_dois": len({normalize_doi(row["doi"]) for row in routes}),
            }
        )
        report["reconciliation"] = {
            "generated_at_utc": now_utc(),
            "original_parse": original,
            "replaced_records": replaced,
            "retry_recoveries": sum(item["method"] == "retry" for item in replaced),
            "manual_fallbacks": sum(item["method"] == "manual_fallback" for item in replaced),
            "policy": "strict_complete_coverage_with_auditable_record_level_replacement",
        }
        write_json(report_path, report)

    return {
        "queue": str(queue_path),
        "parts": len(queue.get("parts", [])),
        "records": sum(int(part["requests"]) for part in queue.get("parts", [])),
        "retry_recovered_dois": sorted(set(recovered_dois)),
        "manual_fallback_dois": sorted(set(manual_dois)),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue-json", required=True)
    parser.add_argument("--retry-queue-json", action="append", default=[])
    parser.add_argument("--manual-fallback-json", required=True)
    return parser.parse_args()


if __name__ == "__main__":
    print(json.dumps(reconcile(parse_args()), indent=2, ensure_ascii=False))
