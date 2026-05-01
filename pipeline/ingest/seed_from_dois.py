#!/usr/bin/env python3
"""Generate normalized claim stubs from a DOI queue."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import re
from pathlib import Path
from typing import Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[2]
DISORDER_CANON_PATH = ROOT / "schema" / "disorder_canonicalization.json"
PAPER_METADATA_FIELDS = [
    "study_journal",
    "publication_type",
    "trial_registry_ids",
    "publication_date",
    "journal_issn",
    "journal_eissn",
    "publisher",
    "mesh_terms",
    "keywords",
    "funders",
    "grant_ids",
    "related_dois",
    "publication_relations",
    "is_retracted",
    "has_correction",
    "language",
    "semantic_scholar_id",
]


def normalize_text(raw: str) -> str:
    lowered = (raw or "").strip().lower()
    lowered = re.sub(r"[^a-z0-9]+", " ", lowered)
    return re.sub(r"\s+", " ", lowered).strip()


def load_disorder_alias_map(path: Path = DISORDER_CANON_PATH) -> Dict[str, str]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        return {}

    alias_map: Dict[str, str] = {}
    for canonical, aliases in data.items():
        canonical_label = (canonical or "").strip()
        if not canonical_label:
            continue
        alias_map[normalize_text(canonical_label)] = canonical_label
        if not isinstance(aliases, list):
            continue
        for raw in aliases:
            alias = (raw or "").strip()
            if not alias:
                continue
            alias_map[normalize_text(alias)] = canonical_label
    return alias_map


DISORDER_ALIAS_MAP = load_disorder_alias_map()


def canonicalize_disorder_label(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        return ""
    normalized = normalize_text(text)
    return DISORDER_ALIAS_MAP.get(normalized, text)


def normalize_doi(raw: str) -> str:
    doi = (raw or "").strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/", "http://dx.doi.org/", "doi:"):
        if doi.startswith(prefix):
            return doi[len(prefix) :].strip()
    return doi


def parse_doi_queue(path: Path) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        for line_no, parts in enumerate(csv.reader(handle), start=1):
            if not parts:
                continue
            first = (parts[0] or "").strip()
            if not first or first.startswith("#"):
                continue

            parts = [(value or "").strip() for value in parts]
            doi = parts[0]
            if not doi:
                raise ValueError(f"Line {line_no}: DOI is required")

            row = {
                "study_doi": doi,
                "compound": parts[1] if len(parts) > 1 else "",
                "entity": parts[2] if len(parts) > 2 else "",
                "study_title": parts[3] if len(parts) > 3 else "",
                "study_year": parts[4] if len(parts) > 4 else "",
                "authors": parts[5] if len(parts) > 5 else "",
                **{
                    field: parts[6 + field_idx] if len(parts) > 6 + field_idx else ""
                    for field_idx, field in enumerate(PAPER_METADATA_FIELDS)
                },
            }
            rows.append(row)
    return rows


def mechanistic_stub(item: Dict[str, str], timestamp: str) -> Dict[str, object]:
    return {
        "compound": item["compound"],
        "target": item["entity"],
        "assay_type": "",
        "affinity_type": "Other",
        "affinity_value": "",
        "affinity_unit": "",
        "species": "",
        "system": "unknown",
        "study_doi": item["study_doi"],
        "openalex_id": "",
        "study_title": item["study_title"],
        "authors": item.get("authors", ""),
        "study_year": item["study_year"],
        **{field: item.get(field, "") for field in PAPER_METADATA_FIELDS},
        "paper_type": "other",
        "evidence_level": "low",
        "source": "doi",
        "source_type": "primary_study",
        "access_level": "secondary_summary",
        "evidence_location": "unknown",
        "evidence_locator": "Unspecified",
        "study_design": "pending_curation",
        "notes": "Auto-generated stub from DOI queue",
        "stub_status": "pending_curation",
        "created_at_utc": timestamp,
    }


def disorder_stub(item: Dict[str, str], timestamp: str) -> Dict[str, object]:
    disorder_raw = item["entity"]
    disorder = canonicalize_disorder_label(disorder_raw)
    note = "Auto-generated stub from DOI queue"
    if disorder_raw and disorder and disorder_raw != disorder:
        note = f"{note}; Disorder normalized from `{disorder_raw}`"
    return {
        "compound": item["compound"],
        "disorder": disorder,
        "outcome_type": "",
        "result_direction": "unclear",
        "outcome_measure": "",
        "population": "",
        "system": "unknown",
        "study_doi": item["study_doi"],
        "openalex_id": "",
        "study_title": item["study_title"],
        "authors": item.get("authors", ""),
        "study_year": item["study_year"],
        **{field: item.get(field, "") for field in PAPER_METADATA_FIELDS},
        "paper_type": "other",
        "evidence_level": "low",
        "source": "doi",
        "source_type": "primary_study",
        "access_level": "secondary_summary",
        "evidence_location": "unknown",
        "evidence_locator": "Unspecified",
        "study_design": "pending_curation",
        "notes": note,
        "stub_status": "pending_curation",
        "created_at_utc": timestamp,
    }


def read_existing_json(path: Path) -> List[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, list):
        raise ValueError(f"Expected JSON array at {path}")
    return data


def context_signature(item: dict, dataset: str) -> Tuple[str, str, str]:
    doi = normalize_doi(str(item.get("study_doi", "")))
    compound = normalize_text(str(item.get("compound", "")))
    entity_key = "target" if dataset == "mechanistic" else "disorder"
    entity = str(item.get(entity_key, "") or item.get("entity", ""))
    if dataset == "disorder":
        entity = canonicalize_disorder_label(entity)
    return doi, compound, normalize_text(entity)


def dedupe_by_context(items: List[dict], dataset: str) -> Tuple[List[dict], int]:
    seen = set()
    out: List[dict] = []
    duplicates = 0
    for item in items:
        sig = context_signature(item, dataset)
        if not any(sig):
            out.append(item)
            continue
        if sig in seen:
            duplicates += 1
            continue
        seen.add(sig)
        out.append(item)
    return out, duplicates


def write_csv(path: Path, rows: List[dict]) -> None:
    fieldnames = sorted({k for row in rows for k in row.keys()}) if rows else []
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, rows: List[dict]) -> None:
    path.write_text(json.dumps(rows, indent=2), encoding="utf-8")


def default_output_paths(dataset: str) -> Dict[str, Path]:
    stem = "mechanistic" if dataset == "mechanistic" else "disorder"
    return {
        "json": ROOT / "data" / "processed" / f"{stem}_claim_stubs.json",
        "csv": ROOT / "data" / "processed" / f"{stem}_claim_stubs.csv",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Create claim stubs from DOI queue")
    parser.add_argument("--doi-file", required=True, help="Text file of DOI rows")
    parser.add_argument("--dataset", choices=["mechanistic", "disorder"], required=True)
    parser.add_argument("--json-out", default="", help="Optional JSON output path")
    parser.add_argument("--csv-out", default="", help="Optional CSV output path")
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Replace output files instead of appending with de-duplication",
    )
    args = parser.parse_args()

    doi_file = Path(args.doi_file).resolve()
    if not doi_file.exists():
        raise SystemExit(f"DOI queue file not found: {doi_file}")

    defaults = default_output_paths(args.dataset)
    json_out = Path(args.json_out).resolve() if args.json_out else defaults["json"]
    csv_out = Path(args.csv_out).resolve() if args.csv_out else defaults["csv"]

    timestamp = dt.datetime.now(dt.timezone.utc).isoformat()
    queue_items = parse_doi_queue(doi_file)

    builder = mechanistic_stub if args.dataset == "mechanistic" else disorder_stub
    generated = [builder(item, timestamp) for item in queue_items]

    if args.replace:
        merged, duplicate_contexts = dedupe_by_context(generated, args.dataset)
    else:
        existing = read_existing_json(json_out)
        merged, duplicate_contexts = dedupe_by_context(existing + generated, args.dataset)

    json_out.parent.mkdir(parents=True, exist_ok=True)
    csv_out.parent.mkdir(parents=True, exist_ok=True)
    write_json(json_out, merged)
    write_csv(csv_out, merged)

    print(f"Dataset: {args.dataset}")
    print(f"DOIs read: {len(queue_items)}")
    print(f"Context duplicates skipped: {duplicate_contexts}")
    print(f"Rows written: {len(merged)}")
    print(f"JSON output: {json_out}")
    print(f"CSV output: {csv_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
