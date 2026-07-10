#!/usr/bin/env python3
"""Build a normalized DOI update scope from report records and DOI files."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

try:
    from pipeline.update.run_scoped_paper_update import (
        normalize_doi,
        read_doi_file,
        write_json_atomic,
        write_lines_atomic,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from pipeline.update.run_scoped_paper_update import (
        normalize_doi,
        read_doi_file,
        write_json_atomic,
        write_lines_atomic,
    )


def parse_selector(value: str) -> tuple[str, str]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("Selectors must use FIELD=VALUE syntax")
    field, expected = value.split("=", 1)
    field = field.strip()
    expected = expected.strip()
    if not field or not expected:
        raise argparse.ArgumentTypeError("Selectors require both FIELD and VALUE")
    return field, expected


def manifest_records(path: Path, records_field: str) -> list[dict]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(value, dict):
        value = value.get(records_field, [])
    if not isinstance(value, list):
        raise ValueError(f"Expected a record list in {path} at field {records_field!r}")
    return [row for row in value if isinstance(row, dict)]


def build_scope(args: argparse.Namespace) -> tuple[list[str], dict]:
    dois: set[str] = set()
    source_counts: Counter = Counter()
    selector_counts: Counter = Counter()
    selectors = list(args.include)

    for raw_path in args.doi_file:
        path = Path(raw_path).resolve()
        values = read_doi_file(path)
        dois.update(values)
        source_counts[str(path)] += len(values)

    for raw_path in args.manifest:
        path = Path(raw_path).resolve()
        records = manifest_records(path, args.records_field)
        selected = []
        for row in records:
            matches = not selectors or any(str(row.get(field, "")).strip() == expected for field, expected in selectors)
            if not matches:
                continue
            doi = normalize_doi(row.get(args.doi_field, ""))
            if doi:
                selected.append(doi)
                for field, expected in selectors:
                    if str(row.get(field, "")).strip() == expected:
                        selector_counts[f"{field}={expected}"] += 1
        dois.update(selected)
        source_counts[str(path)] += len(selected)

    if not dois:
        raise ValueError("No DOI values were selected")
    ordered = sorted(dois)
    report = {
        "schema_version": "doi_update_scope_v1",
        "doi_count": len(ordered),
        "inputs": {
            "manifest": [str(Path(path).resolve()) for path in args.manifest],
            "doi_file": [str(Path(path).resolve()) for path in args.doi_file],
            "records_field": args.records_field,
            "doi_field": args.doi_field,
            "selectors": [f"{field}={expected}" for field, expected in selectors],
        },
        "selected_rows_by_source": dict(source_counts),
        "selected_rows_by_selector": dict(selector_counts),
        "out_doi_file": str(Path(args.out).resolve()),
    }
    return ordered, report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", action="append", default=[])
    parser.add_argument("--doi-file", action="append", default=[])
    parser.add_argument("--records-field", default="records")
    parser.add_argument("--doi-field", default="doi")
    parser.add_argument(
        "--include",
        action="append",
        default=[],
        type=parse_selector,
        help="Include a manifest row when FIELD=VALUE matches; repeated selectors use OR semantics.",
    )
    parser.add_argument("--out", required=True)
    parser.add_argument("--report-json", default="")
    args = parser.parse_args()
    if not args.manifest and not args.doi_file:
        parser.error("Supply at least one --manifest or --doi-file")
    return args


def main() -> int:
    args = parse_args()
    dois, report = build_scope(args)
    out = Path(args.out).resolve()
    write_lines_atomic(out, dois)
    report_path = Path(args.report_json).resolve() if args.report_json else out.with_suffix(".report.json")
    write_json_atomic(report_path, report)
    print(f"DOIs: {len(dois)}")
    print(f"Scope: {out}")
    print(f"Report: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
