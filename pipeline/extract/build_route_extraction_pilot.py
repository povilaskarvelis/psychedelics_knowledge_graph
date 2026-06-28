#!/usr/bin/env python3
"""Build a near-balanced task selection from route extraction tasks."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

try:
    from pipeline.fulltext.convert_pdfs import compact_text, normalize
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from pipeline.fulltext.convert_pdfs import compact_text, normalize


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = ROOT / "data" / "processed" / "extraction" / "route_extraction_tasks.jsonl"
DEFAULT_OUT_JSONL = ROOT / "data" / "processed" / "extraction" / "route_extraction_pilot_tasks.jsonl"
DEFAULT_MANIFEST_CSV = ROOT / "data" / "processed" / "extraction" / "route_extraction_pilot_manifest.csv"
DEFAULT_REPORT_JSON = ROOT / "data" / "processed" / "extraction" / "route_extraction_pilot_report.json"
DEFAULT_SEED = "route_extraction_pilot_v1"

PAPER_TYPE_GROUPS = ("primary", "meta_analysis", "review")
TEXT_DEPTHS = ("article_text", "abstract_only")
EVIDENCE_DOMAINS = (
    "clinical_outcome",
    "safety_tolerability",
    "molecular_target",
    "molecular_pathway_readout",
    "brain_system",
    "cognitive_behavioral",
    "subjective_experience",
    "pharmacokinetics_exposure",
    "intervention_context",
    "real_world_public_health",
)

MANIFEST_FIELDS = [
    "selection_rank",
    "cell_rank",
    "paper_type_group",
    "text_depth",
    "domain_route",
    "task_id",
    "route_id",
    "study_doi",
    "study_title",
    "study_year",
    "prompt_profile",
    "schema_profile",
    "source_type",
    "access_level",
    "text_mode",
    "packet_profile",
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
            row = json.loads(text)
            if isinstance(row, dict):
                rows.append(row)
    return rows


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def nested(task: dict, key: str) -> dict:
    value = task.get(key, {})
    return value if isinstance(value, dict) else {}


def task_prompt_profile(task: dict) -> str:
    contract = nested(task, "extraction_contract")
    route_context = nested(task, "route_context")
    return normalize(contract.get("prompt_profile", "")) or normalize(route_context.get("prompt_profile", ""))


def task_schema_profile(task: dict) -> str:
    contract = nested(task, "extraction_contract")
    route_context = nested(task, "route_context")
    return normalize(contract.get("schema_profile", "")) or normalize(route_context.get("schema_profile", ""))


def task_domain_route(task: dict) -> str:
    contract = nested(task, "extraction_contract")
    route_context = nested(task, "route_context")
    return normalize(contract.get("domain_route", "")) or normalize(route_context.get("domain_route", ""))


def paper_type_group(task: dict) -> str:
    prompt_profile = task_prompt_profile(task)
    if prompt_profile.startswith("primary_"):
        return "primary"
    if prompt_profile == "secondary_meta_analysis":
        return "meta_analysis"
    if prompt_profile.startswith("secondary_"):
        return "review"
    return ""


def text_depth(task: dict) -> str:
    text_source = nested(task, "text_source")
    access = normalize(text_source.get("access_level", ""))
    mode = normalize(text_source.get("mode", ""))
    if access == "full_text_seen" or mode == "full_text_packet":
        return "article_text"
    if access == "abstract_only" or mode == "abstract":
        return "abstract_only"
    return ""


def task_is_ready(task: dict) -> bool:
    return normalize(task.get("task_status", "")) == "ready_for_model"


def stable_key(task: dict, seed: str) -> str:
    route_id = normalize(task.get("route_id", ""))
    task_id = normalize(task.get("task_id", ""))
    doi = normalize(task.get("study_doi", ""))
    payload = f"{seed}|{route_id}|{task_id}|{doi}"
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def manifest_row(task: dict, *, selection_rank: int, cell_rank: int) -> dict:
    metadata = nested(task, "paper_metadata")
    contract = nested(task, "extraction_contract")
    text_source = nested(task, "text_source")
    return {
        "selection_rank": selection_rank,
        "cell_rank": cell_rank,
        "paper_type_group": paper_type_group(task),
        "text_depth": text_depth(task),
        "domain_route": task_domain_route(task),
        "task_id": compact_text(task.get("task_id", "")),
        "route_id": compact_text(task.get("route_id", "")),
        "study_doi": compact_text(task.get("study_doi", "")),
        "study_title": compact_text(metadata.get("study_title", "")),
        "study_year": compact_text(metadata.get("study_year", "")),
        "prompt_profile": task_prompt_profile(task),
        "schema_profile": task_schema_profile(task),
        "source_type": compact_text(contract.get("source_type", "")),
        "access_level": compact_text(text_source.get("access_level", "")),
        "text_mode": compact_text(text_source.get("mode", "")),
        "packet_profile": compact_text(text_source.get("packet_profile", "")),
    }


def cell_key(task: dict) -> tuple[str, str, str]:
    return (paper_type_group(task), text_depth(task), task_domain_route(task))


def build_pilot(args: argparse.Namespace) -> tuple[list[dict], list[dict], dict]:
    input_jsonl = Path(args.input_jsonl).resolve()
    tasks = read_jsonl(input_jsonl)
    examples_per_cell = int(args.examples_per_cell)
    domains = EVIDENCE_DOMAINS
    required_cells = [
        (paper_type, depth, domain)
        for paper_type in PAPER_TYPE_GROUPS
        for depth in TEXT_DEPTHS
        for domain in domains
    ]

    by_cell: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    skipped_counts: Counter = Counter()
    for task in tasks:
        key = cell_key(task)
        if not task_is_ready(task):
            skipped_counts["not_ready"] += 1
            continue
        if key[0] not in PAPER_TYPE_GROUPS:
            skipped_counts["unsupported_paper_type_group"] += 1
            continue
        if key[1] not in TEXT_DEPTHS:
            skipped_counts["unsupported_text_depth"] += 1
            continue
        if key[2] not in domains:
            skipped_counts["excluded_domain"] += 1
            continue
        by_cell[key].append(task)

    short_cells = [
        {
            "paper_type_group": paper_type,
            "text_depth": depth,
            "domain_route": domain,
            "available": len(by_cell.get((paper_type, depth, domain), [])),
            "requested": examples_per_cell,
            "selected": min(len(by_cell.get((paper_type, depth, domain), [])), examples_per_cell),
        }
        for paper_type, depth, domain in required_cells
        if len(by_cell.get((paper_type, depth, domain), [])) < examples_per_cell
    ]

    selected: list[dict] = []
    manifest: list[dict] = []
    for key in required_cells:
        candidates = sorted(by_cell[key], key=lambda task: stable_key(task, args.seed))
        for cell_rank, task in enumerate(candidates[:examples_per_cell], start=1):
            selected.append(task)
            manifest.append(
                manifest_row(
                    task,
                    selection_rank=len(selected),
                    cell_rank=cell_rank,
                )
            )

    report = {
        "generated_at_utc": now_utc(),
        "schema_version": "route_extraction_task_selection_v1",
        "inputs": {
            "input_jsonl": str(input_jsonl),
            "selection_label": args.selection_label,
            "examples_per_cell": examples_per_cell,
            "seed": args.seed,
            "domains": list(domains),
            "paper_type_groups": list(PAPER_TYPE_GROUPS),
            "text_depths": list(TEXT_DEPTHS),
        },
        "outputs": {
            "out_jsonl": str(Path(args.out_jsonl).resolve()),
            "manifest_csv": str(Path(args.manifest_csv).resolve()),
            "report_json": str(Path(args.report_json).resolve()),
        },
        "tasks_read": len(tasks),
        "tasks_selected": len(selected),
        "required_cells": len(required_cells),
        "short_cells": short_cells,
        "empty_cells": [cell for cell in short_cells if cell["available"] == 0],
        "skipped_counts": dict(skipped_counts),
        "available_by_cell_min": min(len(by_cell.get(key, [])) for key in required_cells),
        "available_by_cell_max": max(len(by_cell.get(key, [])) for key in required_cells),
        "selected_by_paper_type_group": dict(Counter(row["paper_type_group"] for row in manifest)),
        "selected_by_text_depth": dict(Counter(row["text_depth"] for row in manifest)),
        "selected_by_domain_route": dict(Counter(row["domain_route"] for row in manifest)),
        "selected_by_schema_profile": dict(Counter(row["schema_profile"] for row in manifest)),
    }
    return selected, manifest, report


def write_manifest(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MANIFEST_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-jsonl", default=str(DEFAULT_INPUT))
    parser.add_argument("--out-jsonl", default=str(DEFAULT_OUT_JSONL))
    parser.add_argument("--manifest-csv", default=str(DEFAULT_MANIFEST_CSV))
    parser.add_argument("--report-json", default=str(DEFAULT_REPORT_JSON))
    parser.add_argument("--examples-per-cell", type=int, default=5)
    parser.add_argument("--seed", default=DEFAULT_SEED)
    parser.add_argument("--selection-label", default="pilot")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    selected, manifest, report = build_pilot(args)
    write_jsonl(Path(args.out_jsonl).resolve(), selected)
    write_manifest(Path(args.manifest_csv).resolve(), manifest)
    write_json(Path(args.report_json).resolve(), report)
    print(f"Selection label: {args.selection_label}")
    print(f"Selected tasks: {Path(args.out_jsonl).resolve()}")
    print(f"Selected rows: {report['tasks_selected']}")
    print(f"Short cells: {len(report['short_cells'])}")
    print(f"Manifest: {Path(args.manifest_csv).resolve()}")
    print(f"Report: {Path(args.report_json).resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
