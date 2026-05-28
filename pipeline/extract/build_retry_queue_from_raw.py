#!/usr/bin/env python3
"""Build an extraction retry queue from non-ok raw batch rows."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                item = json.loads(line)
                if isinstance(item, dict):
                    rows.append(item)
    return rows


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-input-jsonl", required=True)
    parser.add_argument("--raw-jsonl", required=True)
    parser.add_argument("--out-jsonl", required=True)
    parser.add_argument("--report-json", required=True)
    parser.add_argument("--include-schema-errors", action="store_true")
    args = parser.parse_args()

    source_rows = read_jsonl(Path(args.source_input_jsonl).resolve())
    raw_rows = read_jsonl(Path(args.raw_jsonl).resolve())
    retry_indexes = []
    issue_counts: Counter[str] = Counter()
    issue_rows = []
    for raw in raw_rows:
        status = str(raw.get("status") or "").strip()
        is_retry = status != "ok" and (args.include_schema_errors or status != "schema_error")
        if not is_retry:
            continue
        index = int(raw.get("input_row_index") or 0)
        if index <= 0 or index > len(source_rows):
            continue
        retry_indexes.append(index)
        issue_counts[status or "unknown"] += 1
        issue_rows.append(
            {
                "input_row_index": index,
                "dataset": raw.get("dataset", ""),
                "study_doi": raw.get("study_doi", ""),
                "status": status,
                "error_type": raw.get("error_type", ""),
                "error": raw.get("error", ""),
                "schema_errors": raw.get("schema_errors", []),
            }
        )

    retry_rows = [source_rows[index - 1] for index in sorted(set(retry_indexes))]
    out_jsonl = Path(args.out_jsonl).resolve()
    report_json = Path(args.report_json).resolve()
    write_jsonl(out_jsonl, retry_rows)
    write_json(
        report_json,
        {
            "schema_version": "extraction_v1_retry_queue_report",
            "inputs": {
                "source_input_jsonl": str(Path(args.source_input_jsonl).resolve()),
                "raw_jsonl": str(Path(args.raw_jsonl).resolve()),
                "include_schema_errors": args.include_schema_errors,
            },
            "outputs": {"out_jsonl": str(out_jsonl), "report_json": str(report_json)},
            "summary": {
                "raw_rows": len(raw_rows),
                "retry_rows": len(retry_rows),
                "issue_counts": dict(issue_counts),
            },
            "issues": issue_rows,
        },
    )
    print(f"Retry rows: {len(retry_rows)}")
    print(f"Retry JSONL: {out_jsonl}")
    print(f"Report: {report_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
