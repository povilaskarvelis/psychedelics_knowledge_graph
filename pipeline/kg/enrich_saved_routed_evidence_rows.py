#!/usr/bin/env python3
"""Apply deterministic proposition metadata to saved routed evidence rows.

This utility deliberately starts from existing extraction output.  It performs
no model calls and lets downstream KG changes be evaluated without rerunning
extraction.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from collections import Counter
from pathlib import Path

try:
    from pipeline.extract.io_utils import write_json
    from pipeline.kg.convert_routed_extractions_to_evidence_rows import (
        apply_graph_subject,
        evidence_design_for,
        normalized_result_direction,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from pipeline.extract.io_utils import write_json
    from pipeline.kg.convert_routed_extractions_to_evidence_rows import (
        apply_graph_subject,
        evidence_design_for,
        normalized_result_direction,
    )


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def enrich_rows(rows: list[dict]) -> tuple[list[dict], dict]:
    subject_kinds: Counter[str] = Counter()
    designs: Counter[str] = Counter()
    direction_values: Counter[str] = Counter()
    changed_subjects = 0
    for row in rows:
        before = str(row.get("compound", "")).strip()
        apply_graph_subject(row)
        after = str(row.get("compound", "")).strip()
        if before != after:
            changed_subjects += 1
        row["result_direction_normalized"] = normalized_result_direction(row.get("result_direction", ""))
        row["evidence_design"] = evidence_design_for(row)
        subject_kinds[str(row.get("graph_subject_kind", ""))] += 1
        designs[str(row.get("evidence_design", ""))] += 1
        direction_values[str(row.get("result_direction_normalized", ""))] += 1
    return rows, {
        "schema_version": "saved_routed_evidence_enrichment_v1",
        "generated_at_utc": now_utc(),
        "rows": len(rows),
        "rows_with_changed_graph_subject": changed_subjects,
        "graph_subject_kind_counts": dict(subject_kinds),
        "evidence_design_counts": dict(designs),
        "normalized_direction_counts": dict(direction_values),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-json", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--report-json", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = json.loads(args.input_json.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"Expected a JSON array in {args.input_json}")
    rows = [row for row in payload if isinstance(row, dict)]
    rows, report = enrich_rows(rows)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    write_json(args.output_json, rows)
    report["input_json"] = str(args.input_json.resolve())
    report["output_json"] = str(args.output_json.resolve())
    write_json(args.report_json, report)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
