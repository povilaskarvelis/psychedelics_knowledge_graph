#!/usr/bin/env python3
"""Apply explicitly accepted provenance repair candidates.

This script is intentionally conservative:

- It only considers `propose_locator_repair` rows from a repair report.
- It only applies rows explicitly marked accepted in a review file.
- It verifies the report still matches the current curated row before writing.
- It defaults to dry-run; pass `--apply` to update curated claims.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Iterable, List

try:
    from pipeline.fulltext.build_provenance_repair_report import DATASET_CONFIG, is_stale_fulltext_locator
    from pipeline.fulltext.convert_pdfs import normalize, normalize_doi
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from pipeline.fulltext.build_provenance_repair_report import DATASET_CONFIG, is_stale_fulltext_locator
    from pipeline.fulltext.convert_pdfs import normalize, normalize_doi

ROOT = Path(__file__).resolve().parents[2]

ACCEPT_VALUES = {"1", "accept", "accepted", "approve", "approved", "true", "yes", "y"}
REJECT_VALUES = {"0", "defer", "deferred", "false", "no", "n", "reject", "rejected", "skip", ""}


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def load_json_array(path: Path) -> List[dict]:
    data = load_json(path)
    if not isinstance(data, list):
        raise ValueError(f"Expected JSON array at {path}")
    return [row for row in data if isinstance(row, dict)]


def load_json_object(path: Path) -> dict:
    data = load_json(path)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object at {path}")
    return data


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: Iterable[dict], fieldnames: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def read_csv_dicts(path: Path) -> List[dict]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def decision_value(row: dict) -> str:
    for key in ("decision", "accepted", "status", "review_decision"):
        if key in row:
            return normalize(row.get(key, "")).lower()
    return ""


def is_accepted(row: dict) -> bool:
    value = decision_value(row)
    if value in ACCEPT_VALUES:
        return True
    if value in REJECT_VALUES:
        return False
    return False


def load_decisions(path: Path) -> dict[tuple[int, str], dict]:
    if path.suffix.lower() == ".json":
        data = load_json(path)
        if isinstance(data, dict) and isinstance(data.get("rows"), list):
            rows = [row for row in data["rows"] if isinstance(row, dict)]
        elif isinstance(data, list):
            rows = [row for row in data if isinstance(row, dict)]
        else:
            raise ValueError(f"Expected decision JSON array or object with rows at {path}")
    else:
        rows = read_csv_dicts(path)

    accepted: dict[tuple[int, str], dict] = {}
    for row in rows:
        if not is_accepted(row):
            continue
        row_index = int(normalize(row.get("row_index", "0")) or "0")
        doi = normalize_doi(row.get("study_doi", ""))
        if row_index <= 0 or not doi:
            raise ValueError(f"Accepted decision is missing row_index or study_doi: {row}")
        accepted[(row_index, doi)] = row
    return accepted


def report_rows_by_key(report: dict) -> dict[tuple[int, str], dict]:
    rows = report.get("rows", [])
    if not isinstance(rows, list):
        raise ValueError("Repair report must contain a rows array")
    out = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        row_index = int(row.get("row_index", 0) or 0)
        doi = normalize_doi(row.get("study_doi", ""))
        if row_index > 0 and doi:
            out[(row_index, doi)] = row
    return out


def accepted_review_rows(report: dict) -> List[dict]:
    rows = [row for row in report.get("rows", []) if isinstance(row, dict)]
    out = []
    for row in rows:
        if row.get("action") != "propose_locator_repair":
            continue
        out.append(
            {
                "decision": "",
                "reviewer": "",
                "review_notes": "",
                "row_index": row.get("row_index", ""),
                "study_doi": row.get("study_doi", ""),
                "compound": row.get("compound", ""),
                "entity": row.get("entity", ""),
                "study_title": row.get("study_title", ""),
                "score": row.get("score", ""),
                "proposed_evidence_location": row.get("proposed_evidence_location", ""),
                "proposed_evidence_locator": row.get("proposed_evidence_locator", ""),
                "reason": row.get("reason", ""),
                "artifact_path": row.get("artifact_path", ""),
            }
        )
    return out


def export_review_template(report: dict, out_csv: Path) -> int:
    rows = accepted_review_rows(report)
    write_csv(
        out_csv,
        rows,
        [
            "decision",
            "reviewer",
            "review_notes",
            "row_index",
            "study_doi",
            "compound",
            "entity",
            "study_title",
            "score",
            "proposed_evidence_location",
            "proposed_evidence_locator",
            "reason",
            "artifact_path",
        ],
    )
    return len(rows)


def append_note(existing: object, note: str) -> str:
    current = normalize(existing)
    if not current:
        return note
    if note in current:
        return current
    return f"{current}; {note}"


def validate_candidate(report_row: dict, curated_row: dict, row_index: int) -> tuple[bool, str]:
    if report_row.get("action") != "propose_locator_repair":
        return False, "report row is not a proposed locator repair"
    if normalize_doi(curated_row.get("study_doi", "")) != normalize_doi(report_row.get("study_doi", "")):
        return False, "curated DOI no longer matches report DOI"
    if not is_stale_fulltext_locator(curated_row):
        return False, "curated row is no longer a stale full_text_seen abstract locator"
    if normalize(curated_row.get("evidence_locator", "")) != normalize(report_row.get("current_evidence_locator", "")):
        return False, "current evidence locator no longer matches report"
    if not normalize(report_row.get("proposed_evidence_locator", "")):
        return False, "report row is missing proposed evidence locator"
    if not normalize(report_row.get("proposed_evidence_location", "")):
        return False, "report row is missing proposed evidence location"
    if row_index <= 0:
        return False, "invalid row index"
    return True, ""


def build_change(report_row: dict, curated_row: dict, row_index: int, reviewer_note: str = "") -> dict:
    old_location = normalize(curated_row.get("evidence_location", ""))
    old_locator = normalize(curated_row.get("evidence_locator", ""))
    new_location = normalize(report_row.get("proposed_evidence_location", ""))
    new_locator = normalize(report_row.get("proposed_evidence_locator", ""))
    return {
        "row_index": row_index,
        "study_doi": normalize_doi(curated_row.get("study_doi", "")),
        "compound": normalize(curated_row.get("compound", "")),
        "entity": normalize(report_row.get("entity", "")),
        "old_evidence_location": old_location,
        "new_evidence_location": new_location,
        "old_evidence_locator": old_locator,
        "new_evidence_locator": new_locator,
        "reviewer_note": reviewer_note,
    }


def apply_change(curated_row: dict, change: dict) -> None:
    curated_row["evidence_location"] = change["new_evidence_location"]
    curated_row["evidence_locator"] = change["new_evidence_locator"]
    curated_row["notes"] = append_note(
        curated_row.get("notes", ""),
        f"Provenance locator repaired from accepted full-text review on {now_utc()[:10]}",
    )


def apply_repairs(
    curated_rows: List[dict],
    report: dict,
    accepted: dict[tuple[int, str], dict],
    mutate: bool,
) -> dict:
    by_key = report_rows_by_key(report)
    changes = []
    skipped = []

    for key, decision in sorted(accepted.items()):
        row_index, doi = key
        report_row = by_key.get(key)
        if not report_row:
            skipped.append({"row_index": row_index, "study_doi": doi, "reason": "accepted row not found in report"})
            continue
        if row_index > len(curated_rows):
            skipped.append({"row_index": row_index, "study_doi": doi, "reason": "row index beyond curated file"})
            continue
        curated_row = curated_rows[row_index - 1]
        ok, reason = validate_candidate(report_row, curated_row, row_index)
        if not ok:
            skipped.append({"row_index": row_index, "study_doi": doi, "reason": reason})
            continue
        change = build_change(
            report_row,
            curated_row,
            row_index,
            reviewer_note=normalize(decision.get("review_notes", "")),
        )
        changes.append(change)
        if mutate:
            apply_change(curated_row, change)

    return {
        "accepted_decisions": len(accepted),
        "changes_ready": len(changes),
        "skipped": len(skipped),
        "changes": changes,
        "skipped_rows": skipped,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", choices=sorted(DATASET_CONFIG), required=True)
    parser.add_argument("--curated-json", default="", help="Override curated claims JSON")
    parser.add_argument("--repair-report", default="", help="Override provenance repair report JSON")
    parser.add_argument("--accepted-review", default="", help="CSV/JSON review file with accepted decisions")
    parser.add_argument("--export-review-csv", default="", help="Write a decision template CSV and exit")
    parser.add_argument("--out-report", default="", help="Write dry-run/apply report JSON")
    parser.add_argument("--apply", action="store_true", help="Actually update the curated claims JSON")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    cfg = DATASET_CONFIG[args.dataset]
    curated_json = Path(args.curated_json).resolve() if args.curated_json else cfg["curated_json"]
    repair_report = (
        Path(args.repair_report).resolve()
        if args.repair_report
        else ROOT / "data" / "processed" / "fulltext" / f"provenance_repair_report_{args.dataset}.json"
    )
    out_report = (
        Path(args.out_report).resolve()
        if args.out_report
        else ROOT / "data" / "processed" / "fulltext" / f"provenance_apply_report_{args.dataset}.json"
    )

    report = load_json_object(repair_report)
    if args.export_review_csv:
        row_count = export_review_template(report, Path(args.export_review_csv).resolve())
        print(f"Exported review rows: {row_count}")
        print(f"Review CSV: {Path(args.export_review_csv).resolve()}")
        return 0

    if not args.accepted_review:
        raise SystemExit("--accepted-review is required unless --export-review-csv is used")

    curated_rows = load_json_array(curated_json)
    accepted = load_decisions(Path(args.accepted_review).resolve())
    summary = apply_repairs(curated_rows, report, accepted, mutate=args.apply)
    payload = {
        "generated_at_utc": now_utc(),
        "dataset": args.dataset,
        "mode": "apply" if args.apply else "dry_run",
        "inputs": {
            "curated_json": str(curated_json),
            "repair_report": str(repair_report),
            "accepted_review": str(Path(args.accepted_review).resolve()),
        },
        "summary": summary,
    }

    if args.apply and summary["changes_ready"]:
        write_json(curated_json, curated_rows)
    write_json(out_report, payload)

    print(f"Dataset: {args.dataset}")
    print(f"Mode: {payload['mode']}")
    print(f"Accepted decisions: {summary['accepted_decisions']}")
    print(f"Changes ready: {summary['changes_ready']}")
    print(f"Skipped: {summary['skipped']}")
    print(f"Report: {out_report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
