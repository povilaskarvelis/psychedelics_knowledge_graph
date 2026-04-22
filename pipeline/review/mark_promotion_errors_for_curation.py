#!/usr/bin/env python3
"""Move promotion-blocked ready stubs back into the curation queue."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
from pathlib import Path
from typing import Dict, List


ROOT = Path(__file__).resolve().parents[2]

DATASET_CONFIG = {
    "mechanistic": {
        "stubs_json": ROOT / "data" / "processed" / "mechanistic_claim_stubs.json",
        "stubs_csv": ROOT / "data" / "processed" / "mechanistic_claim_stubs.csv",
        "promotion_report": ROOT / "data" / "processed" / "promotion_report_mechanistic.json",
        "entity_key": "target",
    },
    "disorder": {
        "stubs_json": ROOT / "data" / "processed" / "disorder_claim_stubs.json",
        "stubs_csv": ROOT / "data" / "processed" / "disorder_claim_stubs.csv",
        "promotion_report": ROOT / "data" / "processed" / "promotion_report_disorder.json",
        "entity_key": "disorder",
    },
}


def normalize(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def load_json_array(path: Path) -> List[dict]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, list):
        raise ValueError(f"Expected JSON array at {path}")
    return data


def load_json_object(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object at {path}")
    return data


def write_json(path: Path, rows: List[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: List[dict]) -> None:
    key_set = {key for row in rows for key in row.keys()}
    fieldnames = sorted(key_set)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def append_note(notes: str, message: str) -> str:
    base = normalize(notes)
    msg = normalize(message)
    if not msg:
        return base
    if msg.lower() in base.lower():
        return base
    if not base:
        return msg
    return f"{base}; {msg}"


def truncate(value: str, limit: int = 220) -> str:
    text = normalize(value)
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def index_report_errors_by_ready_row(report: dict) -> Dict[int, dict]:
    out: Dict[int, dict] = {}
    for error in report.get("errors", []):
        row_index = int(error.get("row_index", 0) or 0)
        if row_index <= 0:
            continue
        out[row_index] = error
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Move promotion error rows back to curation")
    parser.add_argument("--dataset", choices=["mechanistic", "disorder"], required=True)
    parser.add_argument("--ready-status", default="ready_for_promotion")
    parser.add_argument("--set-status", default="pending_curation")
    parser.add_argument(
        "--promotion-report",
        default="",
        help="Promotion report to read; defaults to data/processed/promotion_report_<dataset>.json",
    )
    parser.add_argument(
        "--report",
        default="",
        help="Output action report; defaults to data/processed/promotion_error_curation_<dataset>.json",
    )
    parser.add_argument("--apply", action="store_true", help="Write status updates to stubs JSON/CSV")
    args = parser.parse_args()

    cfg = DATASET_CONFIG[args.dataset]
    promotion_report_path = Path(args.promotion_report).resolve() if args.promotion_report else cfg["promotion_report"]
    action_report_path = (
        Path(args.report).resolve()
        if args.report
        else ROOT / "data" / "processed" / f"promotion_error_curation_{args.dataset}.json"
    )

    stubs = load_json_array(cfg["stubs_json"])
    promotion_report = load_json_object(promotion_report_path)
    error_by_ready_row = index_report_errors_by_ready_row(promotion_report)

    ready_positions = [
        idx for idx, row in enumerate(stubs, start=1) if normalize(row.get("stub_status", "")) == args.ready_status
    ]

    updates = []
    errors = []
    timestamp = now_utc()

    for ready_row_index, promotion_error in sorted(error_by_ready_row.items()):
        if ready_row_index > len(ready_positions):
            errors.append(
                {
                    "ready_row_index": ready_row_index,
                    "message": "promotion report row_index is outside current ready row set",
                }
            )
            continue

        stub_index = ready_positions[ready_row_index - 1]
        stub = stubs[stub_index - 1]
        report_doi = normalize(promotion_error.get("study_doi", ""))
        stub_doi = normalize(stub.get("study_doi", ""))
        if report_doi and report_doi != stub_doi:
            errors.append(
                {
                    "ready_row_index": ready_row_index,
                    "stub_index": stub_index,
                    "message": "promotion report DOI does not match current stub row",
                    "report_study_doi": report_doi,
                    "stub_study_doi": stub_doi,
                }
            )
            continue

        messages = [normalize(message) for message in promotion_error.get("messages", []) if normalize(message)]
        blocker_text = " | ".join(messages)
        updated = dict(stub)
        updated["stub_status"] = args.set_status
        updated["promotion_blockers"] = blocker_text
        updated["promotion_blocked_at_utc"] = timestamp
        updated["notes"] = append_note(
            updated.get("notes", ""),
            "Promotion blocked; returned to curation queue",
        )

        updates.append(
            {
                "stub_index": stub_index,
                "ready_row_index": ready_row_index,
                "study_doi": stub_doi,
                "compound": normalize(stub.get("compound", "")),
                cfg["entity_key"]: normalize(stub.get(cfg["entity_key"], "")),
                "old_status": normalize(stub.get("stub_status", "")),
                "new_status": args.set_status,
                "messages": messages,
            }
        )

        if args.apply:
            stubs[stub_index - 1] = updated

    if args.apply and updates and not errors:
        write_json(cfg["stubs_json"], stubs)
        write_csv(cfg["stubs_csv"], stubs)

    action_report = {
        "generated_at": timestamp,
        "dataset": args.dataset,
        "apply": args.apply,
        "promotion_report": str(promotion_report_path),
        "ready_status": args.ready_status,
        "set_status": args.set_status,
        "counts": {
            "stubs_total": len(stubs),
            "ready_rows": len(ready_positions),
            "promotion_error_rows": len(error_by_ready_row),
            "updates": len(updates),
            "mapping_errors": len(errors),
        },
        "updates": updates,
        "errors": errors,
    }
    action_report_path.parent.mkdir(parents=True, exist_ok=True)
    action_report_path.write_text(json.dumps(action_report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"Dataset: {args.dataset}")
    print(f"Promotion error rows: {len(error_by_ready_row)}")
    print(f"Mapped updates: {len(updates)}")
    print(f"Mapping errors: {len(errors)}")
    print(f"Apply: {args.apply}")
    if updates:
        print("Sample updates:")
        for row in updates[:10]:
            label = row.get(cfg["entity_key"], "")
            print(
                "- stub_index={stub_index} DOI={doi} {compound} / {label}: {messages}".format(
                    stub_index=row["stub_index"],
                    doi=row["study_doi"],
                    compound=row["compound"],
                    label=label,
                    messages=truncate("; ".join(row["messages"])),
                )
            )
    if errors:
        print("Mapping errors were found; no files were written unless you used --apply after fixing them.")
    print(f"Report: {action_report_path}")

    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
