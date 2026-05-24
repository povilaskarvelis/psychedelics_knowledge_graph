#!/usr/bin/env python3
"""Validate extraction-v1 outputs and verify evidence quotes."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import sys
from collections import Counter
from pathlib import Path

try:
    from jsonschema import Draft7Validator
except ModuleNotFoundError as err:  # pragma: no cover - environment guard
    raise SystemExit("jsonschema is required for extraction-v1 QA") from err

try:
    from pipeline.extract.extraction_v1_utils import (
        find_context_for_result,
        load_pilot_contexts,
        normalize,
        quote_found_in_context,
        read_jsonl,
        write_json,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from pipeline.extract.extraction_v1_utils import (
        find_context_for_result,
        load_pilot_contexts,
        normalize,
        quote_found_in_context,
        read_jsonl,
        write_json,
    )


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCHEMA = ROOT / "schema" / "extraction_v1.schema.json"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "processed" / "extraction"


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def load_schema(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def quote_checks_for_result(result: dict, context_text: str) -> list[dict]:
    checks = []
    assessment = result.get("paper_assessment", {}) if isinstance(result.get("paper_assessment"), dict) else {}
    checks.append(
        {
            "scope": "paper_assessment",
            "index": "",
            "quote": normalize(assessment.get("supporting_quote", "")),
            "verified": quote_found_in_context(assessment.get("supporting_quote", ""), context_text),
        }
    )
    claims = result.get("claims", []) if isinstance(result.get("claims"), list) else []
    for index, claim in enumerate(claims):
        if not isinstance(claim, dict):
            continue
        checks.append(
            {
                "scope": "claim",
                "index": index,
                "quote": normalize(claim.get("supporting_quote", "")),
                "verified": quote_found_in_context(claim.get("supporting_quote", ""), context_text),
            }
        )
    coverage_mentions = result.get("coverage_mentions", []) if isinstance(result.get("coverage_mentions"), list) else []
    for index, mention in enumerate(coverage_mentions):
        if not isinstance(mention, dict):
            continue
        checks.append(
            {
                "scope": "coverage_mention",
                "index": index,
                "quote": normalize(mention.get("supporting_quote", "")),
                "verified": quote_found_in_context(mention.get("supporting_quote", ""), context_text),
            }
        )
    return checks


def qa_rows(results: list[dict], validator: Draft7Validator, contexts: dict[tuple[str, str], dict]) -> tuple[list[dict], list[dict]]:
    rows = []
    details = []
    for idx, result in enumerate(results, start=1):
        schema_errors = sorted(validator.iter_errors(result), key=lambda error: list(error.path))
        context_item = find_context_for_result(result, contexts) if contexts else {}
        context_text = normalize(context_item.get("context_text", ""))
        context_status = "found" if context_text else ("not_configured" if not contexts else "missing")
        quote_checks = quote_checks_for_result(result, context_text) if context_text else []
        quote_failures = [check for check in quote_checks if not check["verified"]]
        status = "ok"
        if schema_errors:
            status = "schema_error"
        elif context_status == "missing":
            status = "context_missing"
        elif quote_failures:
            status = "quote_error"

        row = {
            "row_index": idx,
            "status": status,
            "dataset": normalize(result.get("dataset", "")),
            "study_doi": normalize(result.get("study_doi", "")),
            "input_record_id": normalize(result.get("input_record_id", "")),
            "input_packet_id": normalize(result.get("input_packet_id", "")),
            "relevance": normalize((result.get("paper_assessment") or {}).get("relevance", "")) if isinstance(result.get("paper_assessment"), dict) else "",
            "route": normalize((result.get("paper_assessment") or {}).get("route", "")) if isinstance(result.get("paper_assessment"), dict) else "",
            "claim_count": len(result.get("claims", [])) if isinstance(result.get("claims"), list) else "",
            "coverage_mention_count": len(result.get("coverage_mentions", [])) if isinstance(result.get("coverage_mentions"), list) else "",
            "context_status": context_status,
            "schema_error_count": len(schema_errors),
            "quote_check_count": len(quote_checks),
            "quote_failure_count": len(quote_failures),
        }
        rows.append(row)

        for error in schema_errors:
            details.append(
                {
                    "row_index": idx,
                    "check_type": "schema",
                    "scope": ".".join(str(part) for part in error.path),
                    "message": error.message,
                }
            )
        for failure in quote_failures:
            details.append(
                {
                    "row_index": idx,
                    "check_type": "quote",
                    "scope": failure["scope"],
                    "message": f"quote not found in supplied context: {failure['quote'][:160]}",
                }
            )
        if context_status == "missing":
            details.append(
                {
                    "row_index": idx,
                    "check_type": "context",
                    "scope": "input",
                    "message": "no matching pilot/input context found for quote verification",
                }
            )
    return rows, details


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys()) if rows else [
        "row_index",
        "status",
        "dataset",
        "study_doi",
        "input_record_id",
        "input_packet_id",
        "relevance",
        "route",
        "claim_count",
        "coverage_mention_count",
        "context_status",
        "schema_error_count",
        "quote_check_count",
        "quote_failure_count",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main() -> int:
    parser = argparse.ArgumentParser(description="QA extraction-v1 model outputs")
    parser.add_argument("--input-jsonl", required=True, help="Extraction-v1 output JSONL")
    parser.add_argument("--pilot-input-jsonl", default="", help="Optional pilot/input JSONL used to verify quotes")
    parser.add_argument("--schema", default=str(DEFAULT_SCHEMA))
    parser.add_argument("--out-json", default=str(DEFAULT_OUTPUT_DIR / "extraction_v1_qa_report.json"))
    parser.add_argument("--out-csv", default=str(DEFAULT_OUTPUT_DIR / "extraction_v1_qa_rows.csv"))
    args = parser.parse_args()

    input_jsonl = Path(args.input_jsonl).resolve()
    schema_path = Path(args.schema).resolve()
    results = read_jsonl(input_jsonl)
    validator = Draft7Validator(load_schema(schema_path))
    contexts = load_pilot_contexts(Path(args.pilot_input_jsonl).resolve()) if args.pilot_input_jsonl else {}
    rows, details = qa_rows(results, validator, contexts)
    status_counts = Counter(row["status"] for row in rows)
    quote_failures = sum(int(row.get("quote_failure_count", 0) or 0) for row in rows)
    schema_errors = sum(int(row.get("schema_error_count", 0) or 0) for row in rows)
    report = {
        "generated_at_utc": now_utc(),
        "schema_version": "extraction_v1_qa_report",
        "status": "ok" if not details else "issues_found",
        "inputs": {
            "input_jsonl": str(input_jsonl),
            "pilot_input_jsonl": str(Path(args.pilot_input_jsonl).resolve()) if args.pilot_input_jsonl else "",
            "schema": str(schema_path),
        },
        "summary": {
            "rows": len(rows),
            "status_counts": dict(status_counts),
            "schema_errors": schema_errors,
            "quote_failures": quote_failures,
            "details": len(details),
        },
        "rows": rows,
        "details": details,
    }
    write_json(Path(args.out_json).resolve(), report)
    write_csv(Path(args.out_csv).resolve(), rows)
    print(f"Rows: {len(rows)}")
    print(f"Status counts: {dict(status_counts)}")
    print(f"Schema errors: {schema_errors}")
    print(f"Quote failures: {quote_failures}")
    print(f"Report: {Path(args.out_json).resolve()}")
    print(f"CSV: {Path(args.out_csv).resolve()}")
    return 1 if details else 0


if __name__ == "__main__":
    raise SystemExit(main())
