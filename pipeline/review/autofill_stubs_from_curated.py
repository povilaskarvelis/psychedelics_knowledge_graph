#!/usr/bin/env python3
"""Autofill stub fields from matching curated rows and optionally mark ready."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Dict, List, Set

ROOT = Path(__file__).resolve().parents[2]

DATASET_CONFIG = {
    "mechanistic": {
        "stubs_json": ROOT / "data" / "processed" / "mechanistic_claim_stubs.json",
        "stubs_csv": ROOT / "data" / "processed" / "mechanistic_claim_stubs.csv",
        "curated_json": ROOT / "data" / "curated" / "claims.json",
        "schema": ROOT / "schema" / "claims.schema.json",
        "match_fields": ["study_doi", "compound", "target"],
    },
    "disorder": {
        "stubs_json": ROOT / "data" / "processed" / "disorder_claim_stubs.json",
        "stubs_csv": ROOT / "data" / "processed" / "disorder_claim_stubs.csv",
        "curated_json": ROOT / "data" / "curated" / "disorder_claims.json",
        "schema": ROOT / "schema" / "disorder_claims.schema.json",
        "match_fields": ["study_doi", "compound", "disorder"],
    },
}


def normalize(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def load_json_array(path: Path) -> List[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, list):
        raise ValueError(f"Expected JSON array at {path}")
    return data


def load_schema(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, rows: List[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: List[dict]) -> None:
    key_set = {k for row in rows for k in row.keys()}
    fieldnames = sorted(key_set)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def signature(row: dict, fields: List[str]) -> str:
    return "|".join(normalize(row.get(field, "")) for field in fields)


def main() -> int:
    parser = argparse.ArgumentParser(description="Autofill stub rows from matching curated rows")
    parser.add_argument("--dataset", choices=["mechanistic", "disorder"], required=True)
    parser.add_argument(
        "--status-filter",
        default="pending_curation",
        help="Only autofill stubs with this status (ignored with --all-statuses)",
    )
    parser.add_argument("--all-statuses", action="store_true", help="Process all stub statuses")
    parser.add_argument("--mark-ready", action="store_true", help="Set autofilled rows to ready_for_promotion")
    parser.add_argument("--apply", action="store_true", help="Write updates to stub files")
    parser.add_argument(
        "--report",
        default="",
        help="Optional report path (defaults to data/processed/autofill_report_<dataset>.json)",
    )
    args = parser.parse_args()

    cfg = DATASET_CONFIG[args.dataset]
    report_path = (
        Path(args.report).resolve()
        if args.report
        else ROOT / "data" / "processed" / f"autofill_report_{args.dataset}.json"
    )

    stubs = load_json_array(cfg["stubs_json"])
    curated = load_json_array(cfg["curated_json"])
    schema = load_schema(cfg["schema"])
    allowed_keys: Set[str] = set(schema["items"]["properties"].keys())

    curated_index: Dict[str, dict] = {}
    for row in curated:
        curated_index[signature(row, cfg["match_fields"])] = row

    updated = 0
    matched = 0
    unmatched = 0
    considered = 0
    rows_report = []

    out_stubs: List[dict] = []
    for idx, stub in enumerate(stubs, start=1):
        status = normalize(stub.get("stub_status", ""))
        if not args.all_statuses and status != args.status_filter:
            out_stubs.append(stub)
            continue

        considered += 1
        sig = signature(stub, cfg["match_fields"])
        curated_row = curated_index.get(sig)
        if curated_row is None:
            unmatched += 1
            out_stubs.append(stub)
            rows_report.append(
                {
                    "stub_index": idx,
                    "status": status,
                    "match": False,
                    "match_key": sig,
                }
            )
            continue

        matched += 1
        new_row = dict(stub)
        changed_fields = []
        for key in allowed_keys:
            old_val = normalize(new_row.get(key, ""))
            cur_val = normalize(curated_row.get(key, ""))
            if old_val == "" and cur_val != "":
                new_row[key] = curated_row.get(key)
                changed_fields.append(key)

        if args.mark_ready:
            if normalize(new_row.get("stub_status", "")) != "ready_for_promotion":
                new_row["stub_status"] = "ready_for_promotion"
                changed_fields.append("stub_status")

        if changed_fields:
            updated += 1

        out_stubs.append(new_row)
        rows_report.append(
            {
                "stub_index": idx,
                "status_before": status,
                "status_after": normalize(new_row.get("stub_status", "")),
                "match": True,
                "match_key": sig,
                "changed_fields": sorted(set(changed_fields)),
            }
        )

    report = {
        "generated_at": now_utc(),
        "dataset": args.dataset,
        "status_filter": "*" if args.all_statuses else args.status_filter,
        "mark_ready": args.mark_ready,
        "apply": args.apply,
        "counts": {
            "stubs_total": len(stubs),
            "considered": considered,
            "matched": matched,
            "unmatched": unmatched,
            "updated_rows": updated,
        },
        "rows": rows_report,
    }

    if args.apply:
        write_json(cfg["stubs_json"], out_stubs)
        write_csv(cfg["stubs_csv"], out_stubs)

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"Dataset: {args.dataset}")
    print(f"Considered rows: {considered}")
    print(f"Matched rows: {matched}")
    print(f"Updated rows: {updated}")
    if unmatched:
        print(f"Unmatched rows: {unmatched}")
    print(f"Report: {report_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
