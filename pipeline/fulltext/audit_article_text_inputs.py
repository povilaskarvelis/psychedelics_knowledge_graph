#!/usr/bin/env python3
"""Audit article text inputs selected for routed extraction tasks.

This is a no-model audit. It samples routed full-text papers, applies the same
section selection logic used by the article text input builder, and writes
human-readable reports showing which sections/tables/figures/references would
be sent to the extraction model.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable

import pandas as pd

try:
    from pipeline.extract.build_extraction_tasks import (
        PACKET_PROFILE_NOT_APPLICABLE,
        expected_packet_profile_for_route,
    )
    from pipeline.extract.export_packet_profile_queues import (
        canonical_section_selection_strategy,
        command_section_selection_strategy,
    )
    from pipeline.fulltext.build_llm_evidence_packets import (
        best_extraction,
        build_packet,
        sections_from_tei_full,
    )
    from pipeline.fulltext.convert_pdfs import (
        compact_text,
        load_json_object,
        normalize,
        normalize_doi,
        write_json,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from pipeline.extract.build_extraction_tasks import (
        PACKET_PROFILE_NOT_APPLICABLE,
        expected_packet_profile_for_route,
    )
    from pipeline.extract.export_packet_profile_queues import (
        canonical_section_selection_strategy,
        command_section_selection_strategy,
    )
    from pipeline.fulltext.build_llm_evidence_packets import (
        best_extraction,
        build_packet,
        sections_from_tei_full,
    )
    from pipeline.fulltext.convert_pdfs import (
        compact_text,
        load_json_object,
        normalize,
        normalize_doi,
        write_json,
    )


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ROUTE_TABLE = ROOT / "data" / "processed" / "corpus" / "paper_extraction_routes.parquet"
DEFAULT_OUT_JSON = ROOT / "data" / "processed" / "extraction" / "article_text_input_audit_report.json"
DEFAULT_OUT_CSV = ROOT / "data" / "processed" / "extraction" / "article_text_input_audit.csv"
DEFAULT_OUT_MD = ROOT / "data" / "processed" / "extraction" / "article_text_input_audit.md"
DEFAULT_SAMPLE_JSONL = ROOT / "data" / "processed" / "extraction" / "article_text_input_audit_sample.jsonl"
AUDIT_SCHEMA_VERSION = "article_text_input_audit_v1"

AUDIT_FIELDS = [
    "status",
    "section_selection_strategy",
    "internal_packet_profile",
    "doi",
    "study_title",
    "study_year",
    "source_types",
    "domain_routes",
    "prompt_profiles",
    "schema_profiles",
    "route_count",
    "artifact_path",
    "source_section_count",
    "selected_section_count",
    "omitted_section_count",
    "source_table_count",
    "selected_table_count",
    "source_figure_count",
    "selected_figure_count",
    "source_reference_count",
    "selected_reference_count",
    "source_chunk_token_estimate",
    "selected_chunk_token_estimate",
    "chunk_token_reduction_estimate",
    "fallback_used",
    "section_selection_note",
    "issue_flags",
    "selected_sections",
    "omitted_sections",
    "selected_tables",
    "selected_figures",
    "selected_references",
    "reason",
]


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def split_values(value: object) -> list[str]:
    text = normalize(value)
    if not text:
        return []
    return [part.strip() for part in text.split("|") if part.strip()]


def pipe_join(values: Iterable[object], *, limit: int = 30) -> str:
    out = []
    for value in values:
        text = compact_text(value)
        if text:
            out.append(text)
        if len(out) >= limit:
            break
    return " | ".join(out)


def section_label(section: dict) -> str:
    heading = compact_text(section.get("heading", "")) or "Untitled section"
    section_type = compact_text(section.get("section_type", ""))
    if section_type and section_type.lower() not in heading.lower():
        return f"{heading} [{section_type}]"
    return heading


def section_key(section: dict) -> str:
    for field in ("section_id", "xml_id"):
        value = normalize(section.get(field, ""))
        if value:
            return f"{field}:{value}"
    heading = normalize(section.get("heading", "")).lower()
    section_type = normalize(section.get("section_type", "")).lower()
    char_start = normalize(section.get("char_start", ""))
    return f"{heading}|{section_type}|{char_start}"


def item_label(item: dict) -> str:
    return compact_text(
        item.get("heading", "")
        or item.get("title", "")
        or item.get("caption", "")
        or item.get("fig_desc", "")
        or item.get("doi", "")
    )


def load_artifact_index(artifact_dir: Path) -> dict[str, Path]:
    out: dict[str, Path] = {}
    if not artifact_dir.exists():
        return out
    for path in sorted(artifact_dir.glob("*.json")):
        artifact = load_json_object(path)
        doi = normalize_doi(artifact.get("study_doi", "")) or normalize_doi(path.stem.replace("_", "/"))
        if doi and doi not in out:
            out[doi] = path
    return out


def clean_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return normalize(value).lower() in {"1", "true", "yes", "y"}


def resolve_artifact_path(value: object) -> str:
    for raw_path in split_values(value):
        path = Path(raw_path).expanduser()
        if not path.is_absolute():
            path = ROOT / path
        if path.exists():
            return str(path.resolve())
    return ""


def route_row_matches(row: dict, args: argparse.Namespace) -> bool:
    if not args.include_unretained and not clean_bool(row.get("retained_for_extraction_candidate", False)):
        return False
    if normalize(row.get("route_action", "")) != "extract_from_full_text":
        return False
    if not normalize_doi(row.get("doi", "")):
        return False
    packet_profile = expected_packet_profile_for_route(row)
    if packet_profile == PACKET_PROFILE_NOT_APPLICABLE:
        return False
    requested_profiles = [canonical_section_selection_strategy(value) for value in args.section_selection_strategy]
    if requested_profiles and packet_profile not in requested_profiles:
        return False
    return bool(resolve_artifact_path(row.get("fulltext_artifact_paths", "")))


def add_unique(values: list[str], value: object) -> None:
    text = compact_text(value)
    if text and text not in values:
        values.append(text)


def collapsed_route_rows(rows: list[dict], args: argparse.Namespace) -> list[dict]:
    grouped: dict[tuple[str, str], dict] = {}
    for row in rows:
        if not route_row_matches(row, args):
            continue
        packet_profile = expected_packet_profile_for_route(row)
        doi = normalize_doi(row.get("doi", ""))
        key = (packet_profile, doi)
        if not key[0] or not key[1]:
            continue
        entry = grouped.setdefault(
            key,
            {
                **row,
                "packet_profile": packet_profile,
                "doi": doi,
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
    out = []
    for entry in grouped.values():
        for field in [
            "route_ids",
            "domain_routes",
            "prompt_profiles",
            "schema_profiles",
            "source_types",
        ]:
            entry[field] = "|".join(entry[field])
        out.append(entry)
    return sorted(out, key=lambda item: (item["packet_profile"], item["doi"]))


def audit_queue_row(
    row: dict,
    *,
    args: argparse.Namespace,
) -> tuple[dict, dict | None]:
    doi = normalize_doi(row.get("doi", ""))
    packet_profile = normalize(row.get("packet_profile", ""))
    strategy = command_section_selection_strategy(packet_profile)
    base = {
        "status": "ok",
        "section_selection_strategy": strategy,
        "internal_packet_profile": packet_profile,
        "doi": doi,
        "study_title": compact_text(row.get("study_title", "")),
        "study_year": compact_text(row.get("study_year", "")),
        "source_types": compact_text(row.get("source_types", "")),
        "domain_routes": compact_text(row.get("domain_routes", "")),
        "prompt_profiles": compact_text(row.get("prompt_profiles", "")),
        "schema_profiles": compact_text(row.get("schema_profiles", "")),
        "route_count": len(split_values(row.get("route_ids", ""))),
        "artifact_path": "",
        "source_section_count": 0,
        "selected_section_count": 0,
        "omitted_section_count": 0,
        "source_table_count": 0,
        "selected_table_count": 0,
        "source_figure_count": 0,
        "selected_figure_count": 0,
        "source_reference_count": 0,
        "selected_reference_count": 0,
        "source_chunk_token_estimate": 0,
        "selected_chunk_token_estimate": 0,
        "chunk_token_reduction_estimate": 0,
        "fallback_used": False,
        "section_selection_note": "",
        "issue_flags": "",
        "selected_sections": "",
        "omitted_sections": "",
        "selected_tables": "",
        "selected_figures": "",
        "selected_references": "",
        "reason": "",
    }
    artifact_path_raw = normalize(row.get("artifact_path", ""))
    if not artifact_path_raw:
        return {**base, "status": "missing_artifact", "reason": "no extracted text artifact found for DOI"}, None
    artifact_path = Path(artifact_path_raw).expanduser()
    if not artifact_path.is_absolute():
        artifact_path = ROOT / artifact_path
    if not artifact_path.exists():
        return {**base, "status": "missing_artifact", "reason": "extracted text artifact path does not exist"}, None

    artifact = load_json_object(artifact_path)
    extraction = best_extraction(artifact)
    if not extraction:
        return {
            **base,
            "status": "missing_successful_extraction",
            "artifact_path": str(artifact_path),
            "reason": "artifact has no successful extracted text",
        }, None

    raw_text = normalize(extraction.get("text", ""))
    source_sections = sections_from_tei_full(raw_text)
    packet = build_packet(
        "article",
        artifact_path=artifact_path,
        artifact=artifact,
        paper_row=row,
        max_chunk_chars=max(500, args.max_chunk_chars),
        overlap_chars=max(0, args.chunk_overlap_chars),
        max_chunks_per_paper=max(0, args.max_chunks_per_paper),
        max_references=args.max_references,
        include_section_text=False,
        include_candidate_contexts=False,
        packet_profile=strategy,
    )
    summary = packet.get("document_summary", {})
    profile_summary = summary.get("profile_summary", {}) if isinstance(summary.get("profile_summary", {}), dict) else {}
    selected_sections = packet.get("sections", []) if isinstance(packet.get("sections", []), list) else []
    selected_keys = {section_key(section) for section in selected_sections}
    omitted_sections = [section for section in source_sections if section_key(section) not in selected_keys]
    tables = packet.get("tables", []) if isinstance(packet.get("tables", []), list) else []
    figures = packet.get("figures", []) if isinstance(packet.get("figures", []), list) else []
    references = packet.get("references", []) if isinstance(packet.get("references", []), list) else []
    selected_token_estimate = int(summary.get("chunk_token_estimate", 0) or 0)
    source_section_count = int(summary.get("source_section_count", 0) or 0)
    selected_section_count = int(summary.get("section_count", 0) or 0)
    large_token_threshold = int(getattr(args, "large_token_threshold", 25000) or 25000)
    issue_flags = []
    if bool(profile_summary.get("fallback_used", False)):
        issue_flags.append("fallback_used")
    if selected_token_estimate > large_token_threshold:
        issue_flags.append("large_selected_text")
    if source_section_count <= 1 and selected_token_estimate > large_token_threshold:
        issue_flags.append("single_large_document_section")
    if source_section_count > 0 and selected_section_count == source_section_count and source_section_count >= 10:
        issue_flags.append("all_or_most_sections_selected")
    if any(section_label(section).lower().startswith(("document", "section [other]", "body [other]")) for section in selected_sections):
        issue_flags.append("generic_section_heading")

    return {
        **base,
        "artifact_path": str(artifact_path),
        "source_section_count": source_section_count,
        "selected_section_count": selected_section_count,
        "omitted_section_count": len(omitted_sections),
        "source_table_count": int(summary.get("source_table_count", 0) or 0),
        "selected_table_count": int(summary.get("table_count", 0) or 0),
        "source_figure_count": int(summary.get("source_figure_count", 0) or 0),
        "selected_figure_count": int(summary.get("figure_count", 0) or 0),
        "source_reference_count": int(summary.get("source_reference_count", 0) or 0),
        "selected_reference_count": int(summary.get("reference_count", 0) or 0),
        "source_chunk_token_estimate": int(summary.get("source_chunk_token_estimate", 0) or 0),
        "selected_chunk_token_estimate": selected_token_estimate,
        "chunk_token_reduction_estimate": int(summary.get("chunk_token_reduction_estimate", 0) or 0),
        "fallback_used": bool(profile_summary.get("fallback_used", False)),
        "section_selection_note": compact_text(profile_summary.get("section_selection", "")),
        "issue_flags": "|".join(issue_flags),
        "selected_sections": pipe_join(section_label(section) for section in selected_sections),
        "omitted_sections": pipe_join(section_label(section) for section in omitted_sections),
        "selected_tables": pipe_join(item_label(item) for item in tables),
        "selected_figures": pipe_join(item_label(item) for item in figures),
        "selected_references": pipe_join((item.get("doi", "") or item_label(item) for item in references), limit=20),
    }, packet


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=AUDIT_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_jsonl(path: Path, rows: Iterable[dict]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            count += 1
    return count


def markdown_table(rows: list[dict], limit: int) -> str:
    lines = [
        "| Strategy | DOI | Title | Flags | Sections | Omitted | Tables | References | Tokens |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows[:limit]:
        title = compact_text(row.get("study_title", ""))[:90]
        lines.append(
            "| "
            + " | ".join(
                [
                    compact_text(row.get("section_selection_strategy", "")),
                    compact_text(row.get("doi", "")),
                    title.replace("|", "/"),
                    compact_text(row.get("issue_flags", "")).replace("|", "/"),
                    compact_text(row.get("selected_sections", "")).replace("|", "/")[:220],
                    compact_text(row.get("omitted_sections", "")).replace("|", "/")[:160],
                    str(row.get("selected_table_count", "")),
                    str(row.get("selected_reference_count", "")),
                    str(row.get("selected_chunk_token_estimate", "")),
                ]
            )
            + " |"
        )
    return "\n".join(lines)


def write_markdown(path: Path, report: dict, rows: list[dict], *, preview_limit: int) -> None:
    ok_rows = [row for row in rows if row.get("status") == "ok"]
    lines = [
        "# Article Text Input Audit",
        "",
        f"Generated: `{report['generated_at_utc']}`",
        "",
        "This is a no-model audit of the article text selected for routed extraction tasks.",
        "",
        "## Summary",
        "",
        f"- Queue rows considered: `{report['queue_rows']}`",
        f"- Rows examined: `{report['rows_examined']}`",
        f"- Successful article text inputs: `{report['successful_article_text_inputs']}`",
        f"- Sample JSONL: `{report['outputs']['sample_jsonl']}`",
        f"- CSV: `{report['outputs']['csv']}`",
        "",
        "## Counts By Status",
        "",
    ]
    for status, count in report["by_status"].items():
        lines.append(f"- `{status}`: `{count}`")
    if report.get("by_issue_flags"):
        lines.extend(["", "## Counts By Issue Flag", ""])
        for flag, count in report["by_issue_flags"].items():
            lines.append(f"- `{flag}`: `{count}`")
    lines.extend(["", "## Counts By Section Selection Strategy", ""])
    for key, count in report["by_strategy"].items():
        lines.append(f"- `{key}`: `{count}`")
    if ok_rows:
        lines.extend(["", "## Successful Samples", "", markdown_table(ok_rows, preview_limit)])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_audit(args: argparse.Namespace) -> tuple[dict, list[dict], list[dict]]:
    route_table = Path(args.route_table).resolve()
    route_df = pd.read_parquet(route_table)
    rows = collapsed_route_rows(route_df.to_dict("records"), args)
    if args.artifact_dir:
        override_index = load_artifact_index(Path(args.artifact_dir).expanduser().resolve())
        for row in rows:
            override_path = override_index.get(row["doi"])
            if override_path:
                row["artifact_path"] = str(override_path.resolve())

    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        grouped[row["packet_profile"]].append(row)

    audit_rows: list[dict] = []
    sample_packets: list[dict] = []
    examined_by_group: Counter[str] = Counter()
    successful_by_group: Counter[str] = Counter()
    for packet_profile, group_rows in sorted(grouped.items()):
        group_key = command_section_selection_strategy(packet_profile)
        for row in group_rows:
            if examined_by_group[group_key] >= args.max_candidates_per_group:
                break
            if successful_by_group[group_key] >= args.per_strategy:
                break
            audit_row, packet = audit_queue_row(
                row,
                args=args,
            )
            examined_by_group[group_key] += 1
            audit_rows.append(audit_row)
            if packet:
                sample_packets.append(packet)
                successful_by_group[group_key] += 1

    by_status = dict(Counter(row["status"] for row in audit_rows))
    by_strategy = dict(Counter(row["section_selection_strategy"] for row in audit_rows))
    report = {
        "generated_at_utc": now_utc(),
        "schema_version": AUDIT_SCHEMA_VERSION,
        "route_table": str(route_table),
        "artifact_dir_override": str(Path(args.artifact_dir).expanduser().resolve()) if args.artifact_dir else "",
        "queue_rows": len(rows),
        "rows_examined": len(audit_rows),
        "successful_article_text_inputs": len(sample_packets),
        "per_strategy": args.per_strategy,
        "max_candidates_per_group": args.max_candidates_per_group,
        "by_status": by_status,
        "by_strategy": by_strategy,
        "by_issue_flags": dict(Counter(flag for row in audit_rows for flag in split_values(row.get("issue_flags", "")))),
        "successful_by_strategy": dict(successful_by_group),
        "examined_by_strategy": dict(examined_by_group),
        "outputs": {
            "json": str(Path(args.out_json).resolve()),
            "csv": str(Path(args.out_csv).resolve()),
            "markdown": str(Path(args.out_md).resolve()),
            "sample_jsonl": str(Path(args.sample_jsonl).resolve()),
        },
    }
    return report, audit_rows, sample_packets


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--route-table", default=str(DEFAULT_ROUTE_TABLE))
    parser.add_argument("--artifact-dir", default="", help="Optional override directory for extracted text artifacts")
    parser.add_argument("--section-selection-strategy", action="append", default=[])
    parser.add_argument("--per-strategy", type=int, default=3)
    parser.add_argument("--max-candidates-per-group", type=int, default=100)
    parser.add_argument("--max-chunk-chars", type=int, default=6000)
    parser.add_argument("--chunk-overlap-chars", type=int, default=300)
    parser.add_argument("--max-chunks-per-paper", type=int, default=0)
    parser.add_argument("--max-references", type=int, default=200)
    parser.add_argument("--large-token-threshold", type=int, default=25000)
    parser.add_argument("--include-unretained", action="store_true")
    parser.add_argument("--out-json", default=str(DEFAULT_OUT_JSON))
    parser.add_argument("--out-csv", default=str(DEFAULT_OUT_CSV))
    parser.add_argument("--out-md", default=str(DEFAULT_OUT_MD))
    parser.add_argument("--sample-jsonl", default=str(DEFAULT_SAMPLE_JSONL))
    parser.add_argument("--markdown-preview-limit", type=int, default=30)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report, audit_rows, sample_packets = build_audit(args)
    out_json = Path(args.out_json).resolve()
    out_csv = Path(args.out_csv).resolve()
    out_md = Path(args.out_md).resolve()
    sample_jsonl = Path(args.sample_jsonl).resolve()
    write_json(out_json, report)
    write_csv(out_csv, audit_rows)
    write_jsonl(sample_jsonl, sample_packets)
    write_markdown(out_md, report, audit_rows, preview_limit=max(0, args.markdown_preview_limit))
    print(f"Queue rows: {report['queue_rows']}")
    print(f"Rows examined: {report['rows_examined']}")
    print(f"Successful article text inputs: {report['successful_article_text_inputs']}")
    print(f"Status: {report['by_status']}")
    print(f"Report: {out_json}")
    print(f"CSV: {out_csv}")
    print(f"Markdown: {out_md}")
    print(f"Sample JSONL: {sample_jsonl}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
