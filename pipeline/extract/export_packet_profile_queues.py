#!/usr/bin/env python3
"""Export DOI queues for route-specific article text selection strategies.

The article text builder works from DOI lists plus a section selection strategy.
This script derives those DOI lists from the extraction route table so primary
study, meta-analysis, and review article text inputs can be built from the same
table-native routing layer.
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

import pandas as pd

try:
    from pipeline.extract.build_extraction_tasks import (
        PACKET_PROFILE_NOT_APPLICABLE,
        expected_packet_profile_for_route,
    )
    from pipeline.fulltext.convert_pdfs import compact_text, normalize, normalize_doi
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from pipeline.extract.build_extraction_tasks import (
        PACKET_PROFILE_NOT_APPLICABLE,
        expected_packet_profile_for_route,
    )
    from pipeline.fulltext.convert_pdfs import compact_text, normalize, normalize_doi


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ROUTE_TABLE = ROOT / "data" / "processed" / "corpus" / "paper_extraction_routes.parquet"
DEFAULT_OUT_DIR = ROOT / "data" / "processed" / "extraction" / "article_text_queues"
DEFAULT_REPORT_JSON = ROOT / "data" / "processed" / "extraction" / "article_text_queues_report.json"
DEFAULT_ROWS_CSV = ROOT / "data" / "processed" / "extraction" / "article_text_queues.csv"
QUEUE_SCHEMA_VERSION = "article_text_queues_v1"
DEFAULT_ROUTE_ACTIONS = {"extract_from_full_text"}
SECTION_SELECTION_STRATEGY_ALIASES = {
    "all_sections": "full",
    "primary_study": "primary_empirical",
    "meta_analysis": "secondary_synthesis",
    "review": "review_coverage",
}
SECTION_SELECTION_STRATEGY_COMMAND_LABELS = {
    "full": "all_sections",
    "primary_empirical": "primary_study",
    "secondary_synthesis": "meta_analysis",
    "review_coverage": "review",
}

CSV_FIELDS = [
    "section_selection_strategy",
    "packet_profile",
    "doi",
    "route_ids",
    "domain_routes",
    "prompt_profiles",
    "schema_profiles",
    "source_types",
    "access_tiers",
    "route_actions",
    "study_title",
    "study_year",
]


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def clean_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return normalize(value).lower() in {"1", "true", "yes", "y"}


def split_values(value: object) -> list[str]:
    text = normalize(value)
    if not text:
        return []
    return [part.strip() for part in text.split("|") if part.strip()]


def canonical_section_selection_strategy(value: object) -> str:
    text = normalize(value)
    return SECTION_SELECTION_STRATEGY_ALIASES.get(text, text)


def command_section_selection_strategy(packet_profile: str) -> str:
    return SECTION_SELECTION_STRATEGY_COMMAND_LABELS.get(packet_profile, packet_profile)


def add_unique(values: list[str], value: object) -> None:
    text = compact_text(value)
    if text and text not in values:
        values.append(text)


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def row_matches_filters(row: dict, args: argparse.Namespace) -> bool:
    if args.only_retained and not clean_bool(row.get("retained_for_extraction_candidate", False)):
        return False
    route_action = normalize(row.get("route_action", ""))
    route_actions = set(args.route_action or DEFAULT_ROUTE_ACTIONS)
    if route_action not in route_actions:
        return False
    packet_profile = expected_packet_profile_for_route(row)
    if packet_profile == PACKET_PROFILE_NOT_APPLICABLE:
        return False
    if args.packet_profile and packet_profile not in args.packet_profile:
        return False
    if args.prompt_profile and normalize(row.get("prompt_profile", "")) not in args.prompt_profile:
        return False
    if args.schema_profile and normalize(row.get("schema_profile", "")) not in args.schema_profile:
        return False
    if args.domain_route and normalize(row.get("domain_route", "")) not in args.domain_route:
        return False
    return True


def queue_rows(route_rows: Iterable[dict], args: argparse.Namespace) -> list[dict]:
    grouped: dict[tuple[str, str], dict] = {}
    for row in route_rows:
        if not row_matches_filters(row, args):
            continue
        doi = normalize_doi(row.get("doi", ""))
        if not doi:
            continue
        packet_profile = expected_packet_profile_for_route(row)
        key = (packet_profile, doi)
        entry = grouped.setdefault(
            key,
            {
                "section_selection_strategy": command_section_selection_strategy(packet_profile),
                "packet_profile": packet_profile,
                "doi": doi,
                "route_ids": [],
                "domain_routes": [],
                "prompt_profiles": [],
                "schema_profiles": [],
                "source_types": [],
                "access_tiers": [],
                "route_actions": [],
                "study_title": compact_text(row.get("study_title", "")),
                "study_year": compact_text(row.get("study_year", "")),
            },
        )
        for source_field, target_field in [
            ("route_id", "route_ids"),
            ("domain_route", "domain_routes"),
            ("prompt_profile", "prompt_profiles"),
            ("schema_profile", "schema_profiles"),
            ("source_type", "source_types"),
            ("access_tier", "access_tiers"),
            ("route_action", "route_actions"),
        ]:
            add_unique(entry[target_field], row.get(source_field, ""))
        if not entry["study_title"]:
            entry["study_title"] = compact_text(row.get("study_title", ""))
        if not entry["study_year"]:
            entry["study_year"] = compact_text(row.get("study_year", ""))

    rows = []
    for entry in grouped.values():
        row = dict(entry)
        for field in [
            "route_ids",
            "domain_routes",
            "prompt_profiles",
            "schema_profiles",
            "source_types",
            "access_tiers",
            "route_actions",
        ]:
            row[field] = "|".join(row[field])
        rows.append(row)
    return sorted(rows, key=lambda item: (item["packet_profile"], item["doi"]))


def queue_file_name(packet_profile: str) -> str:
    return f"{command_section_selection_strategy(packet_profile)}.txt"


def write_queue_files(rows: list[dict], out_dir: Path) -> dict[str, dict]:
    out_dir.mkdir(parents=True, exist_ok=True)
    by_group: dict[str, list[str]] = {}
    for row in rows:
        by_group.setdefault(row["packet_profile"], []).append(row["doi"])
    outputs = {}
    for packet_profile, dois in sorted(by_group.items()):
        path = out_dir / queue_file_name(packet_profile)
        unique_dois = sorted(dict.fromkeys(dois))
        path.write_text("\n".join(unique_dois) + ("\n" if unique_dois else ""), encoding="utf-8")
        strategy = command_section_selection_strategy(packet_profile)
        outputs[strategy] = {
            "section_selection_strategy": strategy,
            "packet_profile": packet_profile,
            "doi_count": len(unique_dois),
            "doi_file": str(path),
            "suggested_article_text_inputs_jsonl": str(
                ROOT / "data" / "processed" / "extraction" / f"{strategy}_article_text_inputs.jsonl"
            ),
        }
    return outputs


def count_by(rows: Iterable[dict], field: str) -> dict[str, int]:
    return dict(Counter(compact_text(row.get(field, "")) or "missing" for row in rows))


def build_report(rows: list[dict], *, route_table: Path, out_dir: Path, queue_outputs: dict[str, dict]) -> dict:
    return {
        "generated_at_utc": now_utc(),
        "schema_version": QUEUE_SCHEMA_VERSION,
        "route_table": str(route_table),
        "out_dir": str(out_dir),
        "queue_rows": len(rows),
        "unique_dois": len({row["doi"] for row in rows}),
        "by_section_selection_strategy": count_by(rows, "section_selection_strategy"),
        "by_packet_profile": count_by(rows, "packet_profile"),
        "by_domain_route": count_by(rows, "domain_routes"),
        "by_prompt_profile": count_by(rows, "prompt_profiles"),
        "queue_outputs": queue_outputs,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--route-table", default=str(DEFAULT_ROUTE_TABLE))
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--report-json", default=str(DEFAULT_REPORT_JSON))
    parser.add_argument("--rows-csv", default=str(DEFAULT_ROWS_CSV))
    parser.add_argument("--route-action", action="append", default=[])
    parser.add_argument(
        "--section-selection-strategy",
        "--packet-profile",
        dest="packet_profile",
        action="append",
        default=[],
        help=(
            "Filter to one article text section selection strategy. Standard aliases: "
            "primary_study, meta_analysis, review, all_sections. Compatibility names "
            "such as primary_empirical are also accepted."
        ),
    )
    parser.add_argument("--prompt-profile", action="append", default=[])
    parser.add_argument("--schema-profile", action="append", default=[])
    parser.add_argument("--domain-route", action="append", default=[])
    parser.add_argument("--include-unretained", action="store_true")
    args = parser.parse_args()
    args.only_retained = not args.include_unretained
    args.packet_profile = [canonical_section_selection_strategy(value) for value in args.packet_profile]
    return args


def main() -> int:
    args = parse_args()
    route_table = Path(args.route_table).resolve()
    if not route_table.exists():
        raise FileNotFoundError(f"Route table not found: {route_table}")
    rows = queue_rows(pd.read_parquet(route_table).to_dict("records"), args)
    out_dir = Path(args.out_dir).resolve()
    queue_outputs = write_queue_files(rows, out_dir)
    rows_csv = Path(args.rows_csv).resolve()
    report_json = Path(args.report_json).resolve()
    write_csv(rows_csv, rows)
    report = build_report(rows, route_table=route_table, out_dir=out_dir, queue_outputs=queue_outputs)
    report["outputs"] = {
        "rows_csv": str(rows_csv),
        "report_json": str(report_json),
    }
    write_json(report_json, report)
    print(f"Queue rows: {report['queue_rows']}")
    print(f"Unique DOIs: {report['unique_dois']}")
    print(f"Section selection strategies: {report['by_section_selection_strategy']}")
    print(f"Rows CSV: {rows_csv}")
    print(f"Report: {report_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
