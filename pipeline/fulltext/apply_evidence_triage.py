#!/usr/bin/env python3
"""Apply high-confidence evidence triage reclassification proposals.

The default mode is a dry run. In apply mode, only rows marked
`propose_source_reclassification` and `auto_apply_eligible` are changed, and the
script verifies that the curated row still matches the report before writing.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import List

try:
    from pipeline.fulltext.build_evidence_triage_report import TRIAGE_CONFIG
    from pipeline.fulltext.convert_pdfs import normalize, normalize_doi
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from pipeline.fulltext.build_evidence_triage_report import TRIAGE_CONFIG
    from pipeline.fulltext.convert_pdfs import normalize, normalize_doi

ROOT = Path(__file__).resolve().parents[2]


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


def append_note(existing: object, note: str) -> str:
    current = normalize(existing)
    if not current:
        return note
    if note in current:
        return current
    return f"{current}; {note}"


def report_rows_by_key(report: dict) -> dict[tuple[int, str], dict]:
    out = {}
    for row in report.get("rows", []):
        if not isinstance(row, dict):
            continue
        row_index = int(row.get("row_index", 0) or 0)
        doi = normalize_doi(row.get("study_doi", ""))
        if row_index > 0 and doi:
            out[(row_index, doi)] = row
    return out


def eligible_report_rows(report: dict, min_confidence: float) -> list[dict]:
    rows = []
    for row in report.get("rows", []):
        if not isinstance(row, dict):
            continue
        if row.get("action") != "propose_source_reclassification":
            continue
        if row.get("automation_status") != "auto_apply_eligible":
            continue
        if float(row.get("confidence", 0) or 0) < min_confidence:
            continue
        rows.append(row)
    return rows


def validate_row(report_row: dict, curated_row: dict, row_index: int) -> tuple[bool, str]:
    if row_index <= 0:
        return False, "invalid row index"
    if normalize_doi(curated_row.get("study_doi", "")) != normalize_doi(report_row.get("study_doi", "")):
        return False, "curated DOI no longer matches report DOI"
    if normalize(curated_row.get("source_type", "")) != normalize(report_row.get("current_source_type", "")):
        return False, "source_type no longer matches report"
    if normalize(curated_row.get("paper_type", "")) != normalize(report_row.get("current_paper_type", "")):
        return False, "paper_type no longer matches report"
    if normalize(curated_row.get("study_design", "")) != normalize(report_row.get("current_study_design", "")):
        return False, "study_design no longer matches report"
    if not normalize(report_row.get("target_source_type", "")):
        return False, "missing target_source_type"
    if not normalize(report_row.get("target_paper_type", "")):
        return False, "missing target_paper_type"
    return True, ""


def build_change(report_row: dict, row_index: int) -> dict:
    return {
        "row_index": row_index,
        "study_doi": normalize_doi(report_row.get("study_doi", "")),
        "classification": normalize(report_row.get("classification", "")),
        "confidence": float(report_row.get("confidence", 0) or 0),
        "old_source_type": normalize(report_row.get("current_source_type", "")),
        "new_source_type": normalize(report_row.get("target_source_type", "")),
        "old_paper_type": normalize(report_row.get("current_paper_type", "")),
        "new_paper_type": normalize(report_row.get("target_paper_type", "")),
        "old_study_design": normalize(report_row.get("current_study_design", "")),
        "new_study_design": normalize(report_row.get("target_study_design", "")),
        "signals": normalize(report_row.get("signals", "")),
    }


def apply_change(curated_row: dict, change: dict) -> None:
    curated_row["source_type"] = change["new_source_type"]
    curated_row["paper_type"] = change["new_paper_type"]
    if change["new_study_design"]:
        curated_row["study_design"] = change["new_study_design"]
    curated_row["notes"] = append_note(
        curated_row.get("notes", ""),
        (
            f"Automated evidence triage on {now_utc()[:10]} classified this source as "
            f"{change['classification']} (confidence {change['confidence']:.2f})"
        ),
    )


def apply_triage(curated_rows: List[dict], report: dict, min_confidence: float, mutate: bool) -> dict:
    changes = []
    skipped = []
    for report_row in eligible_report_rows(report, min_confidence=min_confidence):
        row_index = int(report_row.get("row_index", 0) or 0)
        doi = normalize_doi(report_row.get("study_doi", ""))
        if row_index > len(curated_rows):
            skipped.append({"row_index": row_index, "study_doi": doi, "reason": "row index beyond curated file"})
            continue
        curated_row = curated_rows[row_index - 1]
        ok, reason = validate_row(report_row, curated_row, row_index)
        if not ok:
            skipped.append({"row_index": row_index, "study_doi": doi, "reason": reason})
            continue
        change = build_change(report_row, row_index)
        changes.append(change)
        if mutate:
            apply_change(curated_row, change)
    return {
        "eligible_rows": len(eligible_report_rows(report, min_confidence=min_confidence)),
        "changes_ready": len(changes),
        "skipped": len(skipped),
        "changes": changes,
        "skipped_rows": skipped,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", choices=sorted(TRIAGE_CONFIG), required=True)
    parser.add_argument("--curated-json", default="", help="Override curated claims JSON")
    parser.add_argument("--triage-report", default="", help="Override evidence triage report JSON")
    parser.add_argument("--out-report", default="", help="Write dry-run/apply report JSON")
    parser.add_argument("--min-confidence", type=float, default=0.85)
    parser.add_argument("--apply", action="store_true", help="Actually update the curated claims JSON")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    cfg = TRIAGE_CONFIG[args.dataset]
    curated_json = Path(args.curated_json).resolve() if args.curated_json else cfg["curated_json"]
    triage_report = (
        Path(args.triage_report).resolve()
        if args.triage_report
        else ROOT / "data" / "processed" / "fulltext" / f"evidence_triage_report_{args.dataset}.json"
    )
    out_report = (
        Path(args.out_report).resolve()
        if args.out_report
        else ROOT / "data" / "processed" / "fulltext" / f"evidence_triage_apply_report_{args.dataset}.json"
    )

    curated_rows = load_json_array(curated_json)
    report = load_json_object(triage_report)
    summary = apply_triage(
        curated_rows,
        report,
        min_confidence=max(0.0, min(1.0, args.min_confidence)),
        mutate=args.apply,
    )
    payload = {
        "generated_at_utc": now_utc(),
        "dataset": args.dataset,
        "mode": "apply" if args.apply else "dry_run",
        "inputs": {
            "curated_json": str(curated_json),
            "triage_report": str(triage_report),
            "min_confidence": args.min_confidence,
        },
        "summary": summary,
    }

    if args.apply and summary["changes_ready"]:
        write_json(curated_json, curated_rows)
    write_json(out_report, payload)

    print(f"Dataset: {args.dataset}")
    print(f"Mode: {payload['mode']}")
    print(f"Eligible rows: {summary['eligible_rows']}")
    print(f"Changes ready: {summary['changes_ready']}")
    print(f"Skipped: {summary['skipped']}")
    print(f"Report: {out_report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
