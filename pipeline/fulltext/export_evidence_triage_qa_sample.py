#!/usr/bin/env python3
"""Export stratified quality-check samples for evidence triage.

The goal is not to manually review every uncertain row. Instead, this script
creates a small reproducible sample that can estimate rule quality and reveal
which deterministic rules should be tightened next.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable, List

try:
    from pipeline.fulltext.build_evidence_triage_report import TRIAGE_CONFIG
    from pipeline.fulltext.convert_pdfs import normalize
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from pipeline.fulltext.build_evidence_triage_report import TRIAGE_CONFIG
    from pipeline.fulltext.convert_pdfs import normalize

ROOT = Path(__file__).resolve().parents[2]
FULLTEXT_DIR = ROOT / "data" / "processed" / "fulltext"
DEFAULT_DATASETS = ["disorder", "mechanistic"]


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def load_json_object(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object at {path}")
    return data


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: Iterable[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "qa_decision",
        "correct_classification",
        "correct_source_type",
        "correct_paper_type",
        "correct_study_design",
        "correct_primary_vs_non_primary",
        "reviewer",
        "review_notes",
        "sample_group",
        "dataset",
        "row_index",
        "study_doi",
        "compound",
        "entity",
        "study_title",
        "classification",
        "confidence",
        "confidence_band",
        "action",
        "automation_status",
        "current_source_type",
        "target_source_type",
        "current_paper_type",
        "target_paper_type",
        "current_study_design",
        "target_study_design",
        "signals",
        "artifact_path",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def selected_datasets(value: str) -> List[str]:
    if value == "all":
        return list(DEFAULT_DATASETS)
    return [value]


def default_report_path(dataset: str) -> Path:
    return FULLTEXT_DIR / f"evidence_triage_report_{dataset}.json"


def confidence(row: dict) -> float:
    try:
        return float(row.get("confidence", 0) or 0)
    except (TypeError, ValueError):
        return 0.0


def confidence_band(row: dict) -> str:
    value = confidence(row)
    if value >= 0.85:
        return "high"
    if value >= 0.75:
        return "medium"
    return "low"


def stable_sample_key(row: dict, salt: str) -> str:
    raw = "|".join(
        [
            salt,
            normalize(row.get("dataset", "")),
            normalize(row.get("sample_group", "")),
            normalize(row.get("classification", "")),
            normalize(row.get("row_index", "")),
            normalize(row.get("study_doi", "")),
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def choose_rows(rows: List[dict], limit: int, salt: str) -> List[dict]:
    if limit <= 0:
        return []
    return sorted(rows, key=lambda row: stable_sample_key(row, salt))[:limit]


def sample_by_class(rows: List[dict], per_class: int, sample_group: str, salt: str) -> List[dict]:
    by_class: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        classification = normalize(row.get("classification", "")) or "unclassified"
        row["sample_group"] = sample_group
        row["confidence_band"] = confidence_band(row)
        by_class[classification].append(row)

    out: List[dict] = []
    for classification in sorted(by_class):
        class_rows = by_class[classification]
        by_band: dict[str, list[dict]] = defaultdict(list)
        for row in class_rows:
            by_band[row["confidence_band"]].append(row)

        selected: List[dict] = []
        # Spread the sample across confidence bands when possible.
        for band in ["high", "medium", "low"]:
            if len(selected) >= per_class:
                break
            selected.extend(choose_rows(by_band.get(band, []), 1, salt=f"{salt}|{classification}|{band}"))

        if len(selected) < per_class:
            selected_keys = {(row.get("row_index"), row.get("study_doi")) for row in selected}
            remaining = [
                row
                for row in class_rows
                if (row.get("row_index"), row.get("study_doi")) not in selected_keys
            ]
            selected.extend(choose_rows(remaining, per_class - len(selected), salt=f"{salt}|{classification}|rest"))
        out.extend(selected[:per_class])
    return out


def sample_report(
    dataset: str,
    report: dict,
    per_class_targeted: int,
    per_class_audit: int,
    primary_controls: int,
    salt: str,
) -> list[dict]:
    rows = [row for row in report.get("rows", []) if isinstance(row, dict)]
    for row in rows:
        row["dataset"] = dataset

    targeted = [
        dict(row)
        for row in rows
        if row.get("action") == "propose_source_reclassification"
        and row.get("automation_status") == "needs_targeted_qa"
    ]
    audited = [
        dict(row)
        for row in rows
        if row.get("action") in {"keep_non_empirical", "keep_non_primary"}
    ]
    controls = [
        dict(row)
        for row in rows
        if row.get("action") in {"keep_original_empirical", "keep_primary"}
    ]

    sample = []
    sample.extend(sample_by_class(targeted, per_class_targeted, "targeted_rule_qa", salt=f"{salt}|targeted"))
    sample.extend(sample_by_class(audited, per_class_audit, "auto_triage_audit", salt=f"{salt}|audit"))

    control_rows = []
    for row in controls:
        row["sample_group"] = "primary_control"
        row["confidence_band"] = confidence_band(row)
        control_rows.append(row)
    sample.extend(choose_rows(control_rows, primary_controls, salt=f"{salt}|primary_control"))

    for row in sample:
        row.setdefault("qa_decision", "")
        row.setdefault("correct_classification", "")
        row.setdefault("correct_source_type", "")
        row.setdefault("correct_paper_type", "")
        row.setdefault("correct_study_design", "")
        row.setdefault("correct_primary_vs_non_primary", "")
        row.setdefault("reviewer", "")
        row.setdefault("review_notes", "")
    return sorted(
        sample,
        key=lambda row: (
            row.get("dataset", ""),
            row.get("sample_group", ""),
            row.get("classification", ""),
            int(row.get("row_index", 0) or 0),
        ),
    )


def summarize(rows: List[dict]) -> dict:
    return {
        "sample_rows": len(rows),
        "by_dataset": dict(Counter(row.get("dataset", "") for row in rows)),
        "by_sample_group": dict(Counter(row.get("sample_group", "") for row in rows)),
        "by_classification": dict(Counter(row.get("classification", "") for row in rows)),
        "by_confidence_band": dict(Counter(row.get("confidence_band", "") for row in rows)),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", choices=["all", *DEFAULT_DATASETS], default="all")
    parser.add_argument("--triage-report", default="", help="Override report path; only valid with one dataset")
    parser.add_argument(
        "--out-csv",
        default=str(FULLTEXT_DIR / "evidence_triage_qa_sample.csv"),
        help="Output CSV review template",
    )
    parser.add_argument(
        "--out-json",
        default=str(FULLTEXT_DIR / "evidence_triage_qa_sample.json"),
        help="Output JSON sample/report",
    )
    parser.add_argument("--per-class-targeted", type=int, default=6)
    parser.add_argument("--per-class-audit", type=int, default=3)
    parser.add_argument("--primary-controls", type=int, default=6)
    parser.add_argument("--salt", default="psychkg-evidence-triage-qa-v1")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    datasets = selected_datasets(args.dataset)
    if args.triage_report and len(datasets) != 1:
        raise SystemExit("--triage-report can only be used when --dataset is not all")

    sample_rows: List[dict] = []
    inputs = {}
    for dataset in datasets:
        report_path = Path(args.triage_report).resolve() if args.triage_report else default_report_path(dataset)
        report = load_json_object(report_path)
        inputs[dataset] = str(report_path)
        sample_rows.extend(
            sample_report(
                dataset=dataset,
                report=report,
                per_class_targeted=max(0, args.per_class_targeted),
                per_class_audit=max(0, args.per_class_audit),
                primary_controls=max(0, args.primary_controls),
                salt=args.salt,
            )
        )

    out_csv = Path(args.out_csv).resolve()
    out_json = Path(args.out_json).resolve()
    payload = {
        "generated_at_utc": now_utc(),
        "inputs": inputs,
        "parameters": {
            "dataset": args.dataset,
            "per_class_targeted": args.per_class_targeted,
            "per_class_audit": args.per_class_audit,
            "primary_controls": args.primary_controls,
            "salt": args.salt,
        },
        "summary": summarize(sample_rows),
        "rows": sample_rows,
    }
    write_csv(out_csv, sample_rows)
    write_json(out_json, payload)

    print(f"Datasets: {', '.join(datasets)}")
    print(f"Sample rows: {len(sample_rows)}")
    print(f"By group: {payload['summary']['by_sample_group']}")
    print(f"CSV: {out_csv}")
    print(f"JSON: {out_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
