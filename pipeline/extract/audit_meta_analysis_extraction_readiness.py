#!/usr/bin/env python3
"""Audit meta-analysis extraction readiness from route-aware task records.

This script does not call a model. It summarizes whether routed
`secondary_meta_analysis` tasks have usable abstract text or the expected
full-text packet profile before they are sent to extraction.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Iterable

try:
    from pipeline.fulltext.convert_pdfs import compact_text, normalize, normalize_doi
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from pipeline.fulltext.convert_pdfs import compact_text, normalize, normalize_doi


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TASKS_JSONL = ROOT / "data" / "processed" / "extraction" / "route_extraction_tasks.jsonl"
DEFAULT_OUT_JSON = ROOT / "data" / "processed" / "extraction" / "meta_analysis_extraction_readiness_report.json"
DEFAULT_OUT_CSV = ROOT / "data" / "processed" / "extraction" / "meta_analysis_extraction_readiness.csv"
AUDIT_SCHEMA_VERSION = "meta_analysis_extraction_readiness_v1"
META_ANALYSIS_SCHEMA_PROFILE = "meta_analysis_evidence_schema"

CSV_FIELDS = [
    "route_id",
    "task_id",
    "study_doi",
    "study_title",
    "study_year",
    "task_status",
    "route_action",
    "text_mode",
    "access_level",
    "domain_route",
    "expected_packet_profile",
    "packet_profile",
    "packet_profile_status",
    "packet_id",
    "packet_source_path",
    "packet_selection_basis",
    "abstract_available",
    "fulltext_artifact_paths",
    "local_pdf_paths",
    "route_basis",
]


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def read_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            text = line.strip()
            if not text:
                continue
            item = json.loads(text)
            if isinstance(item, dict):
                rows.append(item)
    return rows


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def join_values(values: object) -> str:
    if isinstance(values, list):
        return "|".join(compact_text(value) for value in values if compact_text(value))
    return compact_text(values)


def nested_dict(task: dict, key: str) -> dict:
    value = task.get(key, {})
    return value if isinstance(value, dict) else {}


def is_meta_analysis_task(task: dict) -> bool:
    contract = nested_dict(task, "extraction_contract")
    route_context = nested_dict(task, "route_context")
    return (
        normalize(contract.get("prompt_profile", "")) == "secondary_meta_analysis"
        or normalize(contract.get("schema_profile", "")) == META_ANALYSIS_SCHEMA_PROFILE
        or normalize(route_context.get("prompt_profile", "")) == "secondary_meta_analysis"
        or normalize(route_context.get("schema_profile", "")) == META_ANALYSIS_SCHEMA_PROFILE
    )


def audit_row(task: dict) -> dict:
    metadata = nested_dict(task, "paper_metadata")
    route_context = nested_dict(task, "route_context")
    contract = nested_dict(task, "extraction_contract")
    text_source = nested_dict(task, "text_source")
    doi = normalize_doi(task.get("study_doi", "") or metadata.get("doi", "") or route_context.get("doi", ""))
    return {
        "route_id": compact_text(task.get("route_id", "") or contract.get("route_id", "")),
        "task_id": compact_text(task.get("task_id", "")),
        "study_doi": doi,
        "study_title": compact_text(metadata.get("study_title", "")),
        "study_year": compact_text(metadata.get("study_year", "")),
        "task_status": compact_text(task.get("task_status", "")),
        "route_action": compact_text(text_source.get("route_action", "") or route_context.get("route_action", "")),
        "text_mode": compact_text(text_source.get("mode", "")),
        "access_level": compact_text(text_source.get("access_level", "") or contract.get("access_level", "")),
        "domain_route": compact_text(contract.get("domain_route", "") or route_context.get("domain_route", "")),
        "expected_packet_profile": compact_text(
            text_source.get("expected_packet_profile", "") or contract.get("expected_packet_profile", "")
        ),
        "packet_profile": compact_text(text_source.get("packet_profile", "")),
        "packet_profile_status": compact_text(text_source.get("packet_profile_status", "")),
        "packet_id": compact_text(text_source.get("packet_id", "")),
        "packet_source_path": compact_text(text_source.get("packet_source_path", "")),
        "packet_selection_basis": compact_text(text_source.get("packet_selection_basis", "")),
        "abstract_available": bool(text_source.get("abstract_available", False)),
        "fulltext_artifact_paths": join_values(text_source.get("fulltext_artifact_paths", [])),
        "local_pdf_paths": join_values(text_source.get("local_pdf_paths", [])),
        "route_basis": compact_text(route_context.get("route_basis", "")),
    }


def count_by(rows: Iterable[dict], field: str) -> dict[str, int]:
    return dict(Counter(compact_text(row.get(field, "")) or "missing" for row in rows))


def build_report(tasks: list[dict], *, input_path: Path, generated_at_utc: str | None = None) -> tuple[list[dict], dict]:
    generated_at_utc = generated_at_utc or now_utc()
    meta_rows = [audit_row(task) for task in tasks if is_meta_analysis_task(task)]
    ready_fulltext = [
        row
        for row in meta_rows
        if row["task_status"] == "ready_for_model"
        and row["text_mode"] == "full_text_packet"
        and row["packet_profile_status"] in {"matches_expected", "compatible_full_packet", "missing_packet_profile"}
    ]
    ready_abstract = [
        row
        for row in meta_rows
        if row["task_status"] == "ready_for_model" and row["text_mode"] == "abstract"
    ]
    needs_expected_packet = [
        row
        for row in meta_rows
        if row["task_status"] == "needs_expected_fulltext_packet" or row["packet_profile_status"] == "profile_mismatch"
    ]
    needs_any_packet = [
        row
        for row in meta_rows
        if row["task_status"] in {"needs_fulltext_packet", "needs_expected_fulltext_packet"}
    ]
    report = {
        "generated_at_utc": generated_at_utc,
        "schema_version": AUDIT_SCHEMA_VERSION,
        "input_tasks_jsonl": str(input_path),
        "total_tasks_read": len(tasks),
        "meta_analysis_tasks": len(meta_rows),
        "unique_meta_analysis_dois": len({row["study_doi"] for row in meta_rows if row["study_doi"]}),
        "ready_for_model_tasks": sum(1 for row in meta_rows if row["task_status"] == "ready_for_model"),
        "ready_fulltext_tasks": len(ready_fulltext),
        "ready_abstract_only_tasks": len(ready_abstract),
        "needs_fulltext_packet_tasks": len(needs_any_packet),
        "needs_expected_packet_profile_tasks": len(needs_expected_packet),
        "by_task_status": count_by(meta_rows, "task_status"),
        "by_route_action": count_by(meta_rows, "route_action"),
        "by_text_mode": count_by(meta_rows, "text_mode"),
        "by_access_level": count_by(meta_rows, "access_level"),
        "by_expected_packet_profile": count_by(meta_rows, "expected_packet_profile"),
        "by_packet_profile": count_by(meta_rows, "packet_profile"),
        "by_packet_profile_status": count_by(meta_rows, "packet_profile_status"),
        "samples": {
            "ready_fulltext": ready_fulltext[:50],
            "ready_abstract_only": ready_abstract[:50],
            "needs_fulltext_packet": needs_any_packet[:50],
            "needs_expected_packet_profile": needs_expected_packet[:50],
        },
    }
    return meta_rows, report


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tasks-jsonl", default=str(DEFAULT_TASKS_JSONL))
    parser.add_argument("--out-json", default=str(DEFAULT_OUT_JSON))
    parser.add_argument("--out-csv", default=str(DEFAULT_OUT_CSV))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    tasks_jsonl = Path(args.tasks_jsonl).resolve()
    if not tasks_jsonl.exists():
        raise FileNotFoundError(f"Task JSONL not found: {tasks_jsonl}")
    rows, report = build_report(read_jsonl(tasks_jsonl), input_path=tasks_jsonl)
    out_json = Path(args.out_json).resolve()
    out_csv = Path(args.out_csv).resolve()
    write_json(out_json, report)
    write_csv(out_csv, rows)
    print(f"Meta-analysis tasks: {report['meta_analysis_tasks']}")
    print(f"Ready for model: {report['ready_for_model_tasks']}")
    print(f"Needs full-text packet: {report['needs_fulltext_packet_tasks']}")
    print(f"JSON report: {out_json}")
    print(f"CSV rows: {out_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
