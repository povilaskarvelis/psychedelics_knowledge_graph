#!/usr/bin/env python3
"""Combine accepted meta-analysis rows with explicit paper-level source choices."""

from __future__ import annotations

import argparse
from collections import Counter
import datetime as dt
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = Path(__file__).with_name("meta_analysis_v2_combination_manifest.json")
DEFAULT_OUT_DIR = (
    ROOT
    / "data"
    / "processed"
    / "extraction"
    / "meta_analysis_v2_runs"
    / "meta_analysis_v2_complete_268_20260712"
)


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def clean(value: object) -> str:
    return "" if value is None else str(value).strip()


def read_json(path: Path) -> object:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def row_key(row: dict) -> tuple[str, str]:
    doi = clean(row.get("study_doi", "")).lower()
    item_id = clean(row.get("source_item_id", ""))
    if not doi or not item_id:
        raise ValueError("Every combined row must have study_doi and source_item_id")
    return doi, item_id


def combine_rows(
    base_sources: list[tuple[str, list[dict]]],
    paper_overrides: list[tuple[str, str, list[dict], str]],
) -> tuple[list[dict], dict]:
    selected_by_doi: dict[str, tuple[str, list[dict]]] = {}
    for label, rows in base_sources:
        grouped: dict[str, list[dict]] = {}
        for row in rows:
            doi, _ = row_key(row)
            grouped.setdefault(doi, []).append(row)
        for doi, paper_rows in grouped.items():
            if doi in selected_by_doi:
                previous = selected_by_doi[doi][0]
                raise ValueError(
                    f"Base sources overlap for {doi}: {previous} and {label}; use a paper override"
                )
            selected_by_doi[doi] = (label, paper_rows)

    applied_overrides: list[dict] = []
    for doi, label, rows, reason in paper_overrides:
        doi = clean(doi).lower()
        paper_rows = [row for row in rows if clean(row.get("study_doi", "")).lower() == doi]
        if not paper_rows:
            raise ValueError(f"Paper override source {label} has no accepted rows for {doi}")
        selected_by_doi[doi] = (label, paper_rows)
        applied_overrides.append(
            {"study_doi": doi, "source": label, "rows": len(paper_rows), "reason": reason}
        )

    combined: list[dict] = []
    source_counts: Counter = Counter()
    for doi in sorted(selected_by_doi):
        label, rows = selected_by_doi[doi]
        for row in sorted(rows, key=lambda value: row_key(value)[1]):
            combined.append(row)
            source_counts[label] += 1

    keys = [row_key(row) for row in combined]
    if len(keys) != len(set(keys)):
        duplicates = [key for key, count in Counter(keys).items() if count > 1]
        raise ValueError(f"Duplicate DOI/result IDs in combined rows: {duplicates[:10]}")

    report = {
        "schema_version": "meta_analysis_v2_combination_report_v1",
        "generated_at_utc": now_utc(),
        "counts": {
            "rows": len(combined),
            "papers": len(selected_by_doi),
            "paper_overrides": len(applied_overrides),
        },
        "rows_by_source": dict(sorted(source_counts.items())),
        "paper_overrides": applied_overrides,
    }
    return combined, report


def resolve_path(value: object) -> Path:
    path = Path(clean(value))
    return path if path.is_absolute() else ROOT / path


def combine_from_manifest(manifest_path: Path) -> tuple[list[dict], dict]:
    manifest = read_json(manifest_path)
    if not isinstance(manifest, dict):
        raise ValueError("Combination manifest must be a JSON object")
    base_sources: list[tuple[str, list[dict]]] = []
    for source in manifest.get("base_sources", []):
        path = resolve_path(source.get("path", ""))
        rows = read_json(path)
        if not isinstance(rows, list):
            raise ValueError(f"Base source must contain a JSON list: {path}")
        base_sources.append((clean(source.get("label", "")) or str(path), rows))

    paper_overrides: list[tuple[str, str, list[dict], str]] = []
    for source in manifest.get("paper_source_overrides", []):
        path = resolve_path(source.get("path", ""))
        rows = read_json(path)
        if not isinstance(rows, list):
            raise ValueError(f"Override source must contain a JSON list: {path}")
        paper_overrides.append(
            (
                clean(source.get("study_doi", "")),
                clean(source.get("label", "")) or str(path),
                rows,
                clean(source.get("reason", "")),
            )
        )

    combined, report = combine_rows(base_sources, paper_overrides)
    report["manifest"] = str(manifest_path.resolve())
    return combined, report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--out-json", type=Path, default=DEFAULT_OUT_DIR / "meta_analysis_v2_evidence_rows.json")
    parser.add_argument("--report-json", type=Path, default=DEFAULT_OUT_DIR / "combination_report.json")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rows, report = combine_from_manifest(args.manifest.resolve())
    report["outputs"] = {
        "evidence_rows_json": str(args.out_json.resolve()),
        "report_json": str(args.report_json.resolve()),
    }
    write_json(args.out_json, rows)
    write_json(args.report_json, report)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
