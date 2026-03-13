#!/usr/bin/env python3
"""Review queue for claim stubs with blocker detection and batch status updates."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple

ROOT = Path(__file__).resolve().parents[2]

DATASET_CONFIG = {
    "mechanistic": {
        "stubs_json": ROOT / "data" / "processed" / "mechanistic_claim_stubs.json",
        "stubs_csv": ROOT / "data" / "processed" / "mechanistic_claim_stubs.csv",
        "schema": ROOT / "schema" / "claims.schema.json",
        "entity_field": "target",
    },
    "disorder": {
        "stubs_json": ROOT / "data" / "processed" / "disorder_claim_stubs.json",
        "stubs_csv": ROOT / "data" / "processed" / "disorder_claim_stubs.csv",
        "schema": ROOT / "schema" / "disorder_claims.schema.json",
        "entity_field": "disorder",
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


def parse_schema(schema: dict) -> Tuple[List[str], Dict[str, Set[str]], Dict[str, str], List[Set[str]], Set[str]]:
    item = schema["items"]
    required = list(item.get("required", []))
    properties = item.get("properties", {})

    enums: Dict[str, Set[str]] = {}
    types: Dict[str, str] = {}
    for key, prop in properties.items():
        if "enum" in prop:
            enums[key] = set(prop["enum"])
        if "type" in prop:
            types[key] = prop["type"]

    one_of_groups: List[Set[str]] = []
    for group in item.get("oneOf", []):
        if isinstance(group, dict) and "required" in group:
            one_of_groups.append(set(group["required"]))

    return required, enums, types, one_of_groups, set(properties.keys())


def is_valid_type(raw_value: str, expected_type: str) -> bool:
    if raw_value == "":
        return True
    if expected_type == "integer":
        try:
            int(float(raw_value))
            return True
        except Exception:
            return False
    if expected_type == "number":
        try:
            float(raw_value)
            return True
        except Exception:
            return False
    return True


def evaluate_row(
    row: dict,
    required: List[str],
    enums: Dict[str, Set[str]],
    types: Dict[str, str],
    one_of_groups: List[Set[str]],
    allowed_keys: Set[str],
) -> Tuple[List[str], List[dict]]:
    blocker_fields: Set[str] = set()
    blockers: List[dict] = []

    cleaned = {k: row.get(k, "") for k in allowed_keys}

    for field in required:
        value = normalize(cleaned.get(field, ""))
        if value == "":
            blocker_fields.add(field)
            blockers.append({"field": field, "reason": "missing_required"})

    if one_of_groups:
        any_group_satisfied = any(
            any(normalize(cleaned.get(field, "")) for field in group)
            for group in one_of_groups
        )
        if not any_group_satisfied:
            merged = "|".join(sorted({field for group in one_of_groups for field in group}))
            blocker_fields.add(merged)
            blockers.append({"field": merged, "reason": "missing_one_of"})

    for field, allowed in enums.items():
        value = normalize(cleaned.get(field, ""))
        if value and value not in allowed:
            blocker_fields.add(field)
            blockers.append({"field": field, "reason": "invalid_enum", "value": value})

    for field, expected in types.items():
        value = normalize(cleaned.get(field, ""))
        if not is_valid_type(value, expected):
            blocker_fields.add(field)
            blockers.append({"field": field, "reason": "invalid_type", "value": value, "expected": expected})

    return sorted(blocker_fields), blockers


def parse_row_indices(raw: str) -> Set[int]:
    out: Set[int] = set()
    for chunk in raw.split(","):
        token = chunk.strip()
        if not token:
            continue
        out.add(int(token))
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate stub review queue and optional status updates")
    parser.add_argument("--dataset", choices=["mechanistic", "disorder"], required=True)
    parser.add_argument("--status", default="pending_curation", help="Filter queue by current stub_status")
    parser.add_argument("--all-statuses", action="store_true", help="Ignore status filter and scan all stubs")
    parser.add_argument(
        "--report",
        default="",
        help="Optional review report path (defaults to data/processed/review_queue_<dataset>.json)",
    )
    parser.add_argument(
        "--mark-ready",
        action="store_true",
        help="In apply mode, set clean rows in scope to stub_status=ready_for_promotion",
    )
    parser.add_argument(
        "--set-status",
        default="",
        help="In apply mode, set a status for explicit --row-indices",
    )
    parser.add_argument(
        "--row-indices",
        default="",
        help="Comma-separated 1-based stub indices for --set-status",
    )
    parser.add_argument("--apply", action="store_true", help="Write status updates to stubs JSON/CSV")
    args = parser.parse_args()

    if args.apply and args.set_status and not args.row_indices:
        raise SystemExit("--set-status requires --row-indices")
    if args.apply and args.row_indices and not args.set_status:
        raise SystemExit("--row-indices requires --set-status")
    if args.mark_ready and args.set_status:
        raise SystemExit("Use either --mark-ready or --set-status, not both")

    cfg = DATASET_CONFIG[args.dataset]
    report_path = (
        Path(args.report).resolve()
        if args.report
        else ROOT / "data" / "processed" / f"review_queue_{args.dataset}.json"
    )

    stubs = load_json_array(cfg["stubs_json"])
    schema = load_schema(cfg["schema"])
    required, enums, types, one_of_groups, allowed_keys = parse_schema(schema)

    selected: List[Tuple[int, dict]] = []
    for idx, row in enumerate(stubs, start=1):
        status = normalize(row.get("stub_status", ""))
        if args.all_statuses or status == args.status:
            selected.append((idx, row))

    queue_rows = []
    clean_indices = []
    blocked_indices = []

    for idx, row in selected:
        blocker_fields, blockers = evaluate_row(
            row=row,
            required=required,
            enums=enums,
            types=types,
            one_of_groups=one_of_groups,
            allowed_keys=allowed_keys,
        )
        if normalize(row.get("paper_type", "")) != "primary_results":
            blocker_fields = sorted(set(blocker_fields) | {"paper_type"})
            blockers.append({"field": "paper_type", "reason": "not_primary_results"})
        if blockers:
            blocked_indices.append(idx)
        else:
            clean_indices.append(idx)

        queue_rows.append(
            {
                "stub_index": idx,
                "stub_status": normalize(row.get("stub_status", "")),
                "study_doi": normalize(row.get("study_doi", "")),
                "openalex_id": normalize(row.get("openalex_id", "")),
                "compound": normalize(row.get("compound", "")),
                "entity": normalize(row.get(cfg["entity_field"], "")),
                "blocker_count": len(blockers),
                "blocker_fields": blocker_fields,
                "blockers": blockers,
            }
        )

    report = {
        "generated_at": now_utc(),
        "dataset": args.dataset,
        "status_filter": "*" if args.all_statuses else args.status,
        "apply": args.apply,
        "counts": {
            "stubs_total": len(stubs),
            "in_scope": len(selected),
            "clean_rows": len(clean_indices),
            "blocked_rows": len(blocked_indices),
        },
        "status_updates": {
            "mark_ready": args.mark_ready,
            "set_status": args.set_status,
            "row_indices": args.row_indices,
            "updated_count": 0,
        },
        "rows": queue_rows,
    }

    updates = 0
    if args.apply:
        if args.mark_ready:
            clean_set = set(clean_indices)
            for idx in clean_set:
                stubs[idx - 1]["stub_status"] = "ready_for_promotion"
                updates += 1

        if args.set_status:
            index_set = parse_row_indices(args.row_indices)
            for idx in sorted(index_set):
                if idx < 1 or idx > len(stubs):
                    raise SystemExit(f"stub index out of bounds: {idx}")
                stubs[idx - 1]["stub_status"] = args.set_status
                updates += 1

        write_json(cfg["stubs_json"], stubs)
        write_csv(cfg["stubs_csv"], stubs)

    report["status_updates"]["updated_count"] = updates
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"Dataset: {args.dataset}")
    print(f"Rows in scope: {len(selected)}")
    print(f"Clean rows: {len(clean_indices)}")
    print(f"Blocked rows: {len(blocked_indices)}")
    if args.apply:
        print(f"Status updates: {updates}")
    print(f"Report: {report_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
