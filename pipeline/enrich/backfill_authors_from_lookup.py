#!/usr/bin/env python3
"""Backfill `authors` in curated datasets from DOI-level lookup."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parents[2]

DATASETS = {
    "mechanistic": {
        "json": ROOT / "data" / "curated" / "claims.json",
        "csv": ROOT / "data" / "curated" / "claims.csv",
        "csv_order": [
            "compound",
            "target",
            "assay_type",
            "affinity_type",
            "affinity_value",
            "affinity_unit",
            "species",
            "system",
            "study_doi",
            "openalex_id",
            "study_title",
            "authors",
            "study_year",
            "evidence_level",
            "source",
            "source_type",
            "access_level",
            "evidence_location",
            "evidence_locator",
            "study_design",
            "notes",
        ],
    },
    "disorder": {
        "json": ROOT / "data" / "curated" / "disorder_claims.json",
        "csv": ROOT / "data" / "curated" / "disorder_claims.csv",
        "csv_order": [
            "compound",
            "disorder",
            "outcome_type",
            "outcome_measure",
            "population",
            "system",
            "study_doi",
            "openalex_id",
            "study_title",
            "authors",
            "study_year",
            "evidence_level",
            "source",
            "source_type",
            "access_level",
            "evidence_location",
            "evidence_locator",
            "study_design",
            "notes",
        ],
    },
}


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def normalize(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def load_json_array(path: Path) -> List[dict]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, list):
        raise ValueError(f"Expected JSON array at {path}")
    return data


def write_json(path: Path, rows: List[dict]) -> None:
    path.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: List[dict], preferred_order: List[str]) -> None:
    key_set = {k for row in rows for k in row.keys()}
    ordered = [k for k in preferred_order if k in key_set]
    tail = sorted(key_set - set(ordered))
    fieldnames = ordered + tail
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def apply_lookup(rows: List[dict], lookup: Dict[str, str], unresolved_text: str) -> dict:
    updated = 0
    preserved = 0
    unresolved = 0
    missing_doi = 0
    missing_lookup = []

    for row in rows:
        doi = normalize(row.get("study_doi", ""))
        existing = normalize(row.get("authors", ""))

        if existing:
            preserved += 1
            continue

        if not doi:
            row["authors"] = unresolved_text
            missing_doi += 1
            unresolved += 1
            updated += 1
            continue

        mapped = lookup.get(doi)
        if mapped:
            row["authors"] = mapped
            updated += 1
        else:
            row["authors"] = unresolved_text
            missing_lookup.append(doi)
            unresolved += 1
            updated += 1

    return {
        "updated_rows": updated,
        "preserved_rows": preserved,
        "unresolved_rows": unresolved,
        "missing_doi_rows": missing_doi,
        "missing_lookup_dois": sorted(set(missing_lookup)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill authors in curated datasets from DOI lookup")
    parser.add_argument(
        "--lookup",
        default=str(ROOT / "data" / "raw" / "doi_authors_lookup.json"),
        help="JSON map of DOI -> authors string",
    )
    parser.add_argument(
        "--unresolved-text",
        default="Not available (DOI metadata unresolved)",
        help="Fallback value when DOI mapping is missing",
    )
    parser.add_argument(
        "--report",
        default=str(ROOT / "data" / "processed" / "authors_backfill_report.json"),
        help="Backfill report output path",
    )
    parser.add_argument("--apply", action="store_true", help="Write changes to curated JSON/CSV")
    args = parser.parse_args()

    lookup_path = Path(args.lookup).resolve()
    report_path = Path(args.report).resolve()
    lookup = json.loads(lookup_path.read_text(encoding="utf-8"))

    report = {
        "generated_at": now_utc(),
        "lookup_file": str(lookup_path),
        "apply": args.apply,
        "datasets": {},
    }

    for name, cfg in DATASETS.items():
        rows = load_json_array(cfg["json"])
        summary = apply_lookup(rows, lookup, args.unresolved_text)
        summary["rows"] = len(rows)
        report["datasets"][name] = summary

        if args.apply:
            write_json(cfg["json"], rows)
            write_csv(cfg["csv"], rows, cfg["csv_order"])

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    for name, info in report["datasets"].items():
        print(
            f"{name}: rows={info['rows']} updated={info['updated_rows']} "
            f"unresolved={info['unresolved_rows']}"
        )
    print(f"Report: {report_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
