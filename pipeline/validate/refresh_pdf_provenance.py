#!/usr/bin/env python3
"""Refresh stale abstract locators for rows already marked full_text_seen."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Tuple

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.review.autofill_disorder_from_pdfs import (
    choose_pdf_locator as choose_disorder_locator,
    extract_pdf_segments as extract_disorder_segments,
    infer_evidence_location as infer_disorder_location,
    normalize as normalize_disorder,
    normalize_doi as normalize_disorder_doi,
    normalize_text as normalize_disorder_text,
)
from pipeline.review.autofill_mechanistic_from_pdfs import (
    extract_candidate_from_segments,
    extract_pdf_segments as extract_mechanistic_segments,
    normalize as normalize_mechanistic,
    normalize_doi as normalize_mechanistic_doi,
    normalize_text as normalize_mechanistic_text,
    target_aliases,
)

DATASETS = {
    "mechanistic": {
        "curated_json": ROOT / "data" / "curated" / "claims.json",
        "curated_csv": ROOT / "data" / "curated" / "claims.csv",
        "paper_db_json": ROOT / "data" / "processed" / "paper_library_mechanistic.json",
        "relation_key": "target",
        "match_fields": [
            "compound",
            "target",
            "study_title",
            "study_doi",
            "paper_type",
            "source_type",
            "evidence_level",
            "access_level",
        ],
    },
    "disorder": {
        "curated_json": ROOT / "data" / "curated" / "disorder_claims.json",
        "curated_csv": ROOT / "data" / "curated" / "disorder_claims.csv",
        "paper_db_json": ROOT / "data" / "processed" / "paper_library_disorder.json",
        "relation_key": "disorder",
        "match_fields": [
            "compound",
            "disorder",
            "study_title",
            "study_doi",
            "paper_type",
            "source_type",
            "evidence_level",
            "access_level",
            "result_direction",
        ],
    },
}


def normalize(value: object) -> str:
    return str(value or "").strip()


def append_note(notes: object, message: str) -> str:
    base = normalize(notes)
    if not message:
        return base
    if base and message.lower() in base.lower():
        return base
    if not base:
        return message
    return f"{base}; {message}"


def load_json_array(path: Path) -> List[dict]:
    return json.loads(path.read_text()) if path.exists() else []


def write_json_array(path: Path, rows: List[dict]) -> None:
    path.write_text(json.dumps(rows, indent=2) + "\n")


def write_csv_rows(path: Path, rows: List[dict], fieldnames: List[str]) -> None:
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def row_matches_candidate(row: dict, candidate: dict, fields: Iterable[str]) -> bool:
    return all(normalize(row.get(field, "")) == normalize(candidate.get(field, "")) for field in fields)


def select_rows(rows: List[dict], candidates: List[dict], fields: List[str]) -> List[Tuple[int, dict]]:
    selected: List[Tuple[int, dict]] = []
    for candidate in candidates:
        row_index = int(candidate["row_index"]) - 1
        matches: List[int] = []
        if 0 <= row_index < len(rows) and row_matches_candidate(rows[row_index], candidate, fields):
            matches = [row_index]
        else:
            for idx, row in enumerate(rows):
                if row_matches_candidate(row, candidate, fields):
                    matches.append(idx)
        if not matches:
            continue
        if len(matches) > 1:
            raise RuntimeError(
                "Ambiguous provenance candidate match for row {row_index}: {study_title}".format(
                    row_index=candidate["row_index"],
                    study_title=candidate.get("study_title", ""),
                )
            )
        selected.append((matches[0], candidate))
    return selected


def choose_mechanistic_locator(row: dict, segments: List[str]) -> str:
    target_terms = target_aliases(row.get("target", ""))
    compound_norm = normalize_mechanistic_text(row.get("compound", ""))
    compound_terms = [compound_norm] if compound_norm else []
    if compound_norm == "s ketamine":
        compound_terms.extend(["esketamine", "s-ketamine", "ketamine"])

    candidate = extract_candidate_from_segments(
        segments=segments,
        target_terms=target_terms,
        compound_terms=compound_terms,
        min_score=6,
    )
    if candidate and normalize(candidate.get("context", "")):
        snippet = normalize(candidate["context"])[:180]
        return f"PDF extraction snippet: {snippet}"

    target_terms_norm = {normalize_mechanistic_text(term) for term in target_terms if normalize_mechanistic_text(term)}
    for line in segments[:12000]:
        line_norm = normalize_mechanistic_text(line)
        if any(term and term in line_norm for term in target_terms_norm):
            snippet = normalize(line)[:180]
            if snippet:
                return f"PDF extraction snippet: {snippet}"

    fallback = normalize(" ".join(segments[:30]))[:180]
    if fallback:
        return f"PDF extraction snippet: {fallback}"
    return "PDF full text reviewed"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cleanup-json",
        type=Path,
        default=ROOT / "data" / "processed" / "cleanup_candidates.json",
        help="Cleanup candidate JSON generated by build_cleanup_report.py",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write refreshed locators back to the curated datasets.",
    )
    parser.add_argument(
        "--report-json",
        type=Path,
        default=ROOT / "data" / "processed" / "provenance_refresh_report.json",
        help="Path to write the provenance refresh report when --apply is used.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cleanup_report = json.loads(args.cleanup_json.read_text())
    refreshed_at = datetime.now(timezone.utc).isoformat()
    report = {
        "generated_at": refreshed_at,
        "cleanup_json": str(args.cleanup_json),
        "datasets": {},
    }

    for dataset, config in DATASETS.items():
        curated_rows = load_json_array(config["curated_json"])
        paper_db = load_json_array(config["paper_db_json"])
        candidates = cleanup_report["datasets"][dataset]["provenance_fix"]
        selected = select_rows(curated_rows, candidates, config["match_fields"])
        fieldnames = list(curated_rows[0].keys()) if curated_rows else config["match_fields"]

        if dataset == "mechanistic":
            paper_by_doi = {
                normalize_mechanistic_doi(row.get("study_doi", "")).lower(): row
                for row in paper_db
                if normalize_mechanistic_doi(row.get("study_doi", ""))
            }
        else:
            paper_by_doi = {
                normalize_disorder_doi(row.get("study_doi", "")).lower(): row
                for row in paper_db
                if normalize_disorder_doi(row.get("study_doi", ""))
            }

        refreshed = 0
        skipped = 0
        sample = []

        for row_idx, candidate in selected:
            row = curated_rows[row_idx]
            locator = normalize(row.get("evidence_locator", ""))
            if not locator.lower().startswith("abstract snippet:"):
                skipped += 1
                continue

            doi_key = (
                normalize_mechanistic_doi(row.get("study_doi", "")).lower()
                if dataset == "mechanistic"
                else normalize_disorder_doi(row.get("study_doi", "")).lower()
            )
            paper = paper_by_doi.get(doi_key, {})
            pdf_path = Path(normalize(paper.get("pdf_local_path", ""))) if paper else Path("")
            if not pdf_path.exists():
                skipped += 1
                continue

            if dataset == "mechanistic":
                segments, _used_ocr = extract_mechanistic_segments(pdf_path)
                if not segments:
                    skipped += 1
                    continue
                new_locator = choose_mechanistic_locator(row, segments)
            else:
                segments = extract_disorder_segments(pdf_path)
                if not segments:
                    skipped += 1
                    continue
                new_locator = choose_disorder_locator(
                    segments=segments,
                    disorder=normalize(row.get("disorder", "")),
                    outcome_measure=normalize(row.get("outcome_measure", "")),
                )
                current_location = normalize(row.get("evidence_location", ""))
                if current_location in {"", "unknown", "abstract"}:
                    text_norm = normalize_disorder_text(
                        f"{normalize(row.get('study_title', ''))} {' '.join(segments[:6000])}"
                    )
                    inferred_location = infer_disorder_location(text_norm, current_location)
                    if inferred_location and inferred_location != current_location:
                        row["evidence_location"] = inferred_location

            if not normalize(new_locator):
                skipped += 1
                continue

            row["evidence_locator"] = new_locator
            row["notes"] = append_note(row.get("notes", ""), "PDF provenance locator refreshed from local full text")
            refreshed += 1

            if len(sample) < 10:
                entry = {
                    "row_index": row_idx + 1,
                    "study_title": normalize(row.get("study_title", "")),
                    "study_doi": normalize(row.get("study_doi", "")),
                    "old_locator": locator[:180],
                    "new_locator": new_locator[:180],
                }
                sample.append(entry)

        report["datasets"][dataset] = {
            "target_rows": len(selected),
            "refreshed": refreshed,
            "skipped": skipped,
            "sample": sample,
        }

        print(f"{dataset}: target_rows={len(selected)}, refreshed={refreshed}, skipped={skipped}")

        if args.apply:
            write_json_array(config["curated_json"], curated_rows)
            write_csv_rows(config["curated_csv"], curated_rows, fieldnames)

    if args.apply:
        args.report_json.write_text(json.dumps(report, indent=2) + "\n")
        print(f"wrote {args.report_json}")


if __name__ == "__main__":
    main()
