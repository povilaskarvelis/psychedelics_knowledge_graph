#!/usr/bin/env python3
"""Assemble the complete routed evidence file from explicit source layers.

The graph build accepts one routed evidence JSON file. This assembler keeps a
known-complete primary/review base, overlays only explicitly selected primary
retry papers, and replaces the meta-analysis layer as a whole. That prevents a
small retry run from accidentally replacing the complete primary corpus.
"""

from __future__ import annotations

import argparse
from collections import Counter
import datetime as dt
import json
from pathlib import Path


def clean(value: object) -> str:
    return "" if value is None else str(value).strip()


def resolve_doi(doi: object, aliases: dict[str, str] | None = None) -> str:
    resolved = clean(doi).lower()
    aliases = aliases or {}
    seen: set[str] = set()
    while resolved in aliases and resolved not in seen:
        seen.add(resolved)
        resolved = aliases[resolved]
    return resolved


def normalized_doi(row: dict, aliases: dict[str, str] | None = None) -> str:
    return resolve_doi(row.get("study_doi") or row.get("doi"), aliases)


def is_primary_row(row: dict) -> bool:
    return clean(row.get("source_type")).lower() == "primary"


def is_meta_analysis_row(row: dict) -> bool:
    return clean(row.get("source_type")).lower() == "meta_analysis"


def row_identity(row: dict) -> tuple[str, str, str, str]:
    return (
        normalized_doi(row),
        clean(row.get("task_id")),
        clean(row.get("source_item_type")),
        clean(row.get("source_item_id") or row.get("source_item_index")),
    )


def assemble_rows(
    base_rows: list[dict],
    primary_retry_rows: list[dict],
    primary_retry_dois: set[str],
    meta_analysis_rows: list[dict],
    *,
    replace_primary_layer: bool = False,
    doi_aliases: dict[str, str] | None = None,
) -> tuple[list[dict], dict]:
    aliases = {
        clean(alias).lower(): clean(canonical).lower()
        for alias, canonical in (doi_aliases or {}).items()
        if clean(alias) and clean(canonical)
    }
    raw_retry_dois = {clean(doi).lower() for doi in primary_retry_dois if clean(doi)}
    retry_dois = {resolve_doi(doi, aliases) for doi in raw_retry_dois}
    exact_retry_rows = [
        row
        for row in primary_retry_rows
        if is_primary_row(row) and normalized_doi(row) in raw_retry_dois
    ]
    exact_retry_dois_found = {
        normalized_doi(row, aliases) for row in exact_retry_rows
    }
    fallback_retry_dois = retry_dois - exact_retry_dois_found
    retry_rows = (
        [row for row in primary_retry_rows if is_primary_row(row)]
        if replace_primary_layer
        else [
            row
            for row in primary_retry_rows
            if is_primary_row(row)
            and (
                normalized_doi(row) in raw_retry_dois
                or normalized_doi(row, aliases) in fallback_retry_dois
            )
        ]
    )
    retry_dois_found = {normalized_doi(row, aliases) for row in retry_rows}
    missing_retry_dois = sorted(retry_dois - retry_dois_found)
    if missing_retry_dois:
        raise ValueError(f"No primary retry rows found for: {missing_retry_dois}")
    if replace_primary_layer and not retry_rows:
        raise ValueError("Complete primary replacement input contains no primary rows")

    invalid_meta_rows = [row for row in meta_analysis_rows if not is_meta_analysis_row(row)]
    if invalid_meta_rows:
        raise ValueError(
            f"Meta-analysis input contains {len(invalid_meta_rows)} non-meta-analysis rows"
        )

    removed_primary_rows = [
        row
        for row in base_rows
        if is_primary_row(row)
        and (replace_primary_layer or normalized_doi(row, aliases) in retry_dois)
    ]
    removed_meta_rows = [row for row in base_rows if is_meta_analysis_row(row)]
    kept_base = [
        row
        for row in base_rows
        if not (
            is_primary_row(row)
            and (replace_primary_layer or normalized_doi(row, aliases) in retry_dois)
        )
        and not is_meta_analysis_row(row)
    ]
    combined = [*kept_base, *retry_rows, *meta_analysis_rows]

    identities = [row_identity(row) for row in combined]
    duplicate_identities = [
        identity for identity, count in Counter(identities).items() if count > 1
    ]
    if duplicate_identities:
        raise ValueError(
            "Duplicate routed evidence identities after assembly: "
            f"{duplicate_identities[:10]}"
        )

    report = {
        "schema_version": "routed_evidence_assembly_report_v2",
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "primary_replacement_mode": "complete_layer" if replace_primary_layer else "selected_papers",
        "doi_aliases_applied": len(aliases),
        "counts": {
            "base_rows": len(base_rows),
            "base_rows_kept": len(kept_base),
            "primary_retry_rows_removed": len(removed_primary_rows),
            "primary_retry_rows_added": len(retry_rows),
            "primary_retry_papers_added": len(retry_dois_found),
            "meta_analysis_rows_removed": len(removed_meta_rows),
            "meta_analysis_rows_added": len(meta_analysis_rows),
            "meta_analysis_papers_added": len(
                {normalized_doi(row) for row in meta_analysis_rows}
            ),
            "combined_rows": len(combined),
        },
        "primary_retry_dois": sorted(retry_dois_found),
        "combined_source_types": dict(
            sorted(Counter(clean(row.get("source_type")) for row in combined).items())
        ),
    }
    return combined, report


def read_rows(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"Expected a JSON list: {path}")
    return payload


def read_doi_aliases(path: Path | None) -> dict[str, str]:
    if path is None:
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    records = payload.get("records") if isinstance(payload, dict) else None
    if not isinstance(records, list):
        raise ValueError(f"Expected a DOI alias registry with a records list: {path}")
    return {
        clean(record.get("alias_doi")).lower(): clean(record.get("canonical_doi")).lower()
        for record in records
        if isinstance(record, dict)
        and clean(record.get("alias_doi"))
        and clean(record.get("canonical_doi"))
    }


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-json", type=Path, required=True)
    parser.add_argument("--primary-retry-json", type=Path, required=True)
    parser.add_argument(
        "--primary-retry-doi",
        action="append",
        default=[],
        help="Primary DOI to replace from the retry file; repeat for each paper.",
    )
    parser.add_argument(
        "--replace-primary-layer",
        action="store_true",
        help="Replace every primary row in the base with the complete primary layer from --primary-retry-json.",
    )
    parser.add_argument("--meta-analysis-json", type=Path, required=True)
    parser.add_argument(
        "--doi-alias-registry",
        type=Path,
        help="Optional registry used to match legacy DOI spellings to selected retry papers.",
    )
    parser.add_argument("--out-json", type=Path, required=True)
    parser.add_argument("--report-json", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rows, report = assemble_rows(
        read_rows(args.base_json),
        read_rows(args.primary_retry_json),
        set(args.primary_retry_doi),
        read_rows(args.meta_analysis_json),
        replace_primary_layer=args.replace_primary_layer,
        doi_aliases=read_doi_aliases(args.doi_alias_registry),
    )
    report["inputs"] = {
        "base_json": str(args.base_json.resolve()),
        "primary_retry_json": str(args.primary_retry_json.resolve()),
        "meta_analysis_json": str(args.meta_analysis_json.resolve()),
        "doi_alias_registry": (
            str(args.doi_alias_registry.resolve()) if args.doi_alias_registry else None
        ),
    }
    report["outputs"] = {
        "evidence_json": str(args.out_json.resolve()),
        "report_json": str(args.report_json.resolve()),
    }
    write_json(args.out_json, rows)
    write_json(args.report_json, report)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
