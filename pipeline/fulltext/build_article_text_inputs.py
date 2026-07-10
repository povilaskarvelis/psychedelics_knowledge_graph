#!/usr/bin/env python3
"""Build article text inputs from the extraction route table."""

from __future__ import annotations

import argparse
from collections import Counter
import csv
import datetime as dt
import json
from pathlib import Path
import sys

import pandas as pd

try:
    from pipeline.extract.build_extraction_tasks import (
        PACKET_PROFILE_NOT_APPLICABLE,
        PACKET_PROFILE_PRIMARY,
        PACKET_PROFILE_REVIEW_COVERAGE,
        PACKET_PROFILE_SECONDARY_SYNTHESIS,
        expected_packet_profile_for_route,
    )
    from pipeline.extract.export_packet_profile_queues import (
        canonical_section_selection_strategy,
        command_section_selection_strategy,
    )
    from pipeline.fulltext.audit_article_text_inputs import (
        AUDIT_FIELDS,
        audit_queue_row,
        split_values,
        write_csv,
        write_markdown,
        write_jsonl,
    )
    from pipeline.fulltext.convert_pdfs import compact_text, normalize, normalize_doi, write_json
    from pipeline.fulltext.source_identity_audit_gate import SourceIdentityAuditGate
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from pipeline.extract.build_extraction_tasks import (
        PACKET_PROFILE_NOT_APPLICABLE,
        PACKET_PROFILE_PRIMARY,
        PACKET_PROFILE_REVIEW_COVERAGE,
        PACKET_PROFILE_SECONDARY_SYNTHESIS,
        expected_packet_profile_for_route,
    )
    from pipeline.extract.export_packet_profile_queues import (
        canonical_section_selection_strategy,
        command_section_selection_strategy,
    )
    from pipeline.fulltext.audit_article_text_inputs import (
        AUDIT_FIELDS,
        audit_queue_row,
        split_values,
        write_csv,
        write_markdown,
        write_jsonl,
    )
    from pipeline.fulltext.convert_pdfs import compact_text, normalize, normalize_doi, write_json
    from pipeline.fulltext.source_identity_audit_gate import SourceIdentityAuditGate


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ROUTE_TABLE = ROOT / "data" / "processed" / "corpus" / "paper_extraction_routes.parquet"
DEFAULT_OUT_JSONL = ROOT / "data" / "processed" / "extraction" / "fulltext_packets.jsonl"
DEFAULT_REPORT_JSON = ROOT / "data" / "processed" / "extraction" / "article_text_inputs_report.json"
DEFAULT_AUDIT_CSV = ROOT / "data" / "processed" / "extraction" / "article_text_inputs_audit.csv"
DEFAULT_AUDIT_MD = ROOT / "data" / "processed" / "extraction" / "article_text_inputs_audit.md"
DEFAULT_SOURCE_IDENTITY_AUDIT = ROOT / "data" / "processed" / "fulltext" / "source_identity_audit.json"
SCHEMA_VERSION = "article_text_inputs_v1"
DEFAULT_ROUTE_ACTION = "extract_from_full_text"
DEFAULT_PRIMARY_STRATEGY = "primary_study"
DEFAULT_SECONDARY_STRATEGY = "all_sections"


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def clean_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return normalize(value).lower() in {"1", "true", "yes", "y"}


def add_unique(values: list[str], value: object) -> None:
    text = compact_text(value)
    if text and text not in values:
        values.append(text)


def resolve_artifact_path(value: object) -> str:
    for raw_path in split_values(value):
        path = Path(raw_path).expanduser()
        if not path.is_absolute():
            path = ROOT / path
        if path.exists():
            return str(path.resolve())
    return ""


def enforce_source_identity_gate(route_rows: list[dict], audit_path: Path) -> tuple[list[dict], list[dict]]:
    gate = SourceIdentityAuditGate(audit_path)
    eligible: list[dict] = []
    rejected: list[dict] = []
    for row in route_rows:
        doi = normalize_doi(row.get("doi", ""))
        artifact_path = resolve_artifact_path(row.get("fulltext_artifact_paths", ""))
        if normalize(row.get("route_action", "")) != DEFAULT_ROUTE_ACTION or not artifact_path:
            eligible.append(row)
            continue
        if not gate.is_verified(doi, Path(artifact_path)):
            rejected.append(
                {
                    "doi": doi,
                    "artifact_path": artifact_path,
                    "reason": "artifact is absent from the verified source-identity audit",
                }
            )
            continue
        eligible.append(row)
    return eligible, rejected


def selected_packet_profile_for_route(route_row: dict, args: argparse.Namespace) -> str:
    expected = expected_packet_profile_for_route(route_row)
    if expected == PACKET_PROFILE_PRIMARY:
        return canonical_section_selection_strategy(args.primary_section_selection_strategy)
    if expected in {PACKET_PROFILE_SECONDARY_SYNTHESIS, PACKET_PROFILE_REVIEW_COVERAGE}:
        return canonical_section_selection_strategy(args.secondary_section_selection_strategy)
    return expected


def route_row_matches(row: dict, args: argparse.Namespace) -> bool:
    if not args.include_unretained and not clean_bool(row.get("retained_for_extraction_candidate", False)):
        return False
    if normalize(row.get("route_action", "")) != DEFAULT_ROUTE_ACTION:
        return False
    if not normalize_doi(row.get("doi", "")):
        return False
    if expected_packet_profile_for_route(row) == PACKET_PROFILE_NOT_APPLICABLE:
        return False
    if not resolve_artifact_path(row.get("fulltext_artifact_paths", "")):
        return False
    if args.prompt_profile and normalize(row.get("prompt_profile", "")) not in args.prompt_profile:
        return False
    if args.schema_profile and normalize(row.get("schema_profile", "")) not in args.schema_profile:
        return False
    if args.domain_route and normalize(row.get("domain_route", "")) not in args.domain_route:
        return False
    return True


def build_queue_rows(route_rows: list[dict], args: argparse.Namespace) -> list[dict]:
    grouped: dict[tuple[str, str], dict] = {}
    for row in route_rows:
        if not route_row_matches(row, args):
            continue
        packet_profile = selected_packet_profile_for_route(row, args)
        if not packet_profile or packet_profile == PACKET_PROFILE_NOT_APPLICABLE:
            continue
        doi = normalize_doi(row.get("doi", ""))
        key = (packet_profile, doi)
        entry = grouped.setdefault(
            key,
            {
                **row,
                "packet_profile": packet_profile,
                "doi": doi,
                "study_doi": doi,
                "artifact_path": resolve_artifact_path(row.get("fulltext_artifact_paths", "")),
                "route_ids": [],
                "domain_routes": [],
                "prompt_profiles": [],
                "schema_profiles": [],
                "source_types": [],
            },
        )
        for field, target in [
            ("route_id", "route_ids"),
            ("domain_route", "domain_routes"),
            ("prompt_profile", "prompt_profiles"),
            ("schema_profile", "schema_profiles"),
            ("source_type", "source_types"),
        ]:
            add_unique(entry[target], row.get(field, ""))
        for field in ("study_title", "study_year"):
            if not compact_text(entry.get(field, "")) and compact_text(row.get(field, "")):
                entry[field] = compact_text(row.get(field, ""))

    rows = []
    for entry in grouped.values():
        for field in ["route_ids", "domain_routes", "prompt_profiles", "schema_profiles", "source_types"]:
            entry[field] = "|".join(entry[field])
        rows.append(entry)
    return sorted(rows, key=lambda item: (item["packet_profile"], item["doi"]))


def write_policy_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "doi",
        "packet_profile",
        "section_selection_strategy",
        "route_ids",
        "domain_routes",
        "prompt_profiles",
        "schema_profiles",
        "source_types",
        "study_title",
        "study_year",
        "artifact_path",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    **row,
                    "section_selection_strategy": command_section_selection_strategy(row.get("packet_profile", "")),
                }
            )


def build_article_text_inputs(args: argparse.Namespace) -> tuple[dict, list[dict], list[dict]]:
    route_table = Path(args.route_table).resolve()
    route_df = pd.read_parquet(route_table)
    route_rows = route_df.to_dict("records")
    route_rows, identity_rejections = enforce_source_identity_gate(
        route_rows,
        Path(getattr(args, "source_identity_audit", DEFAULT_SOURCE_IDENTITY_AUDIT)).resolve(),
    )
    if identity_rejections:
        sample = ", ".join(row["doi"] for row in identity_rejections[:5])
        raise RuntimeError(
            f"Source-identity gate rejected {len(identity_rejections)} routed artifact(s): {sample}. "
            "No extraction packets were written."
        )
    queue_rows = build_queue_rows(route_rows, args)
    if args.limit > 0:
        queue_rows = queue_rows[: args.limit]

    audit_rows: list[dict] = []
    packets: list[dict] = []
    for row in queue_rows:
        audit_row, packet = audit_queue_row(row, args=args)
        audit_rows.append(audit_row)
        if packet:
            packets.append(packet)

    report = {
        "generated_at_utc": now_utc(),
        "schema_version": SCHEMA_VERSION,
        "route_table": str(route_table),
        "source_identity_gate": {
            "enforced": True,
            "audit_path": str(
                Path(getattr(args, "source_identity_audit", DEFAULT_SOURCE_IDENTITY_AUDIT)).resolve()
            ),
            "rejected": len(identity_rejections),
        },
        "selection_policy": {
            "primary_studies": command_section_selection_strategy(
                canonical_section_selection_strategy(args.primary_section_selection_strategy)
            ),
            "secondary_literature": command_section_selection_strategy(
                canonical_section_selection_strategy(args.secondary_section_selection_strategy)
            ),
        },
        "queue_rows": len(queue_rows),
        "rows_examined": len(audit_rows),
        "successful_article_text_inputs": len(packets),
        "packets_written": len(packets),
        "by_status": dict(Counter(row["status"] for row in audit_rows)),
        "by_packet_profile": dict(Counter(packet.get("packet_profile", "") for packet in packets)),
        "by_strategy": dict(Counter(row["section_selection_strategy"] for row in audit_rows)),
        "by_section_selection_strategy": dict(Counter(row["section_selection_strategy"] for row in audit_rows)),
        "by_issue_flags": dict(Counter(flag for row in audit_rows for flag in split_values(row.get("issue_flags", "")))),
        "outputs": {
            "json": str(Path(args.report_json).resolve()),
            "csv": str(Path(args.audit_csv).resolve()),
            "markdown": str(Path(args.audit_md).resolve()),
            "sample_jsonl": str(Path(args.out_jsonl).resolve()),
            "jsonl": str(Path(args.out_jsonl).resolve()),
            "report_json": str(Path(args.report_json).resolve()),
            "audit_csv": str(Path(args.audit_csv).resolve()),
            "audit_md": str(Path(args.audit_md).resolve()),
            "policy_csv": str(Path(args.policy_csv).resolve()) if args.policy_csv else "",
        },
    }
    return report, audit_rows, packets


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--route-table", default=str(DEFAULT_ROUTE_TABLE))
    parser.add_argument("--out-jsonl", default=str(DEFAULT_OUT_JSONL))
    parser.add_argument("--report-json", default=str(DEFAULT_REPORT_JSON))
    parser.add_argument("--audit-csv", default=str(DEFAULT_AUDIT_CSV))
    parser.add_argument("--audit-md", default=str(DEFAULT_AUDIT_MD))
    parser.add_argument("--policy-csv", default="")
    parser.add_argument("--source-identity-audit", default=str(DEFAULT_SOURCE_IDENTITY_AUDIT))
    parser.add_argument("--primary-section-selection-strategy", default=DEFAULT_PRIMARY_STRATEGY)
    parser.add_argument("--secondary-section-selection-strategy", default=DEFAULT_SECONDARY_STRATEGY)
    parser.add_argument("--prompt-profile", action="append", default=[])
    parser.add_argument("--schema-profile", action="append", default=[])
    parser.add_argument("--domain-route", action="append", default=[])
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--max-chunk-chars", type=int, default=6000)
    parser.add_argument("--chunk-overlap-chars", type=int, default=300)
    parser.add_argument("--max-chunks-per-paper", type=int, default=0)
    parser.add_argument("--max-references", type=int, default=200)
    parser.add_argument("--large-token-threshold", type=int, default=25000)
    parser.add_argument("--include-unretained", action="store_true")
    parser.add_argument("--markdown-preview-limit", type=int, default=30)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.primary_section_selection_strategy = canonical_section_selection_strategy(args.primary_section_selection_strategy)
    args.secondary_section_selection_strategy = canonical_section_selection_strategy(args.secondary_section_selection_strategy)
    report, audit_rows, packets = build_article_text_inputs(args)
    out_jsonl = Path(args.out_jsonl).resolve()
    report_json = Path(args.report_json).resolve()
    audit_csv = Path(args.audit_csv).resolve()
    audit_md = Path(args.audit_md).resolve()

    write_jsonl(out_jsonl, packets)
    write_json(report_json, report)
    write_csv(audit_csv, audit_rows)
    write_markdown(audit_md, report, audit_rows, preview_limit=max(0, args.markdown_preview_limit))
    if args.policy_csv:
        write_policy_csv(Path(args.policy_csv).resolve(), build_queue_rows(pd.read_parquet(Path(args.route_table).resolve()).to_dict("records"), args))

    print(f"Queue rows: {report['queue_rows']}")
    print(f"Article text inputs written: {report['packets_written']}")
    print(f"Status: {report['by_status']}")
    print(f"Packet profiles: {report['by_packet_profile']}")
    print(f"Section strategies: {report['by_section_selection_strategy']}")
    print(f"JSONL: {out_jsonl}")
    print(f"Report: {report_json}")
    print(f"Audit CSV: {audit_csv}")
    print(f"Audit Markdown: {audit_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
