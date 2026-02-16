#!/usr/bin/env python3
"""Audit recall of known relevant DOIs across search pipeline stages."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
from pathlib import Path
from typing import Dict, List, Set

ROOT = Path(__file__).resolve().parents[2]


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def normalize(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def normalize_doi(raw: object) -> str:
    text = normalize(raw)
    if not text:
        return ""
    lowered = text.lower()
    if lowered.startswith("https://doi.org/"):
        text = text[len("https://doi.org/") :]
    elif lowered.startswith("http://doi.org/"):
        text = text[len("http://doi.org/") :]
    elif lowered.startswith("doi:"):
        text = text[4:]
    return text.strip().lower()


def read_known_dois(path: Path) -> List[str]:
    if not path.exists():
        raise FileNotFoundError(f"Known DOI file not found: {path}")

    out: List[str] = []
    seen: Set[str] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        candidate = line.split(",", 1)[0].strip()
        doi = normalize_doi(candidate)
        if not doi or doi in seen:
            continue
        seen.add(doi)
        out.append(doi)
    return out


def read_queue_dois(path: Path) -> Set[str]:
    if not path.exists():
        return set()

    out: Set[str] = set()
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        for row in reader:
            if not row:
                continue
            first = normalize(row[0])
            if first.startswith("#"):
                continue
            doi = normalize_doi(first)
            if doi:
                out.add(doi)
    return out


def read_paper_library(path: Path) -> Dict[str, dict]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        return {}

    out: Dict[str, dict] = {}
    for row in payload:
        if not isinstance(row, dict):
            continue
        doi = normalize_doi(row.get("study_doi", ""))
        if not doi:
            continue
        existing = out.get(doi)
        if not existing:
            out[doi] = row
            continue

        # Prefer row that has a local PDF path if there are duplicates.
        existing_pdf = normalize(existing.get("pdf_local_path", ""))
        row_pdf = normalize(row.get("pdf_local_path", ""))
        if row_pdf and not existing_pdf:
            out[doi] = row
    return out


def read_curated_dois(path: Path) -> Set[str]:
    if not path.exists():
        return set()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        return set()
    out: Set[str] = set()
    for row in payload:
        if not isinstance(row, dict):
            continue
        doi = normalize_doi(row.get("study_doi", ""))
        if doi:
            out.add(doi)
    return out


def pct(found: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return (found / total) * 100.0


def main() -> int:
    parser = argparse.ArgumentParser(description="Recall audit for known relevant DOI benchmark set")
    parser.add_argument("--dataset", choices=["mechanistic", "disorder"], required=True)
    parser.add_argument("--known-doi-file", required=True, help="Plain-text list of known relevant DOIs")
    parser.add_argument("--discovered-queue", default="", help="Optional override for discovered queue path")
    parser.add_argument("--triage-queue", default="", help="Optional override for triage queue path")
    parser.add_argument("--paper-library", default="", help="Optional override for paper library JSON")
    parser.add_argument("--curated", default="", help="Optional override for curated claims JSON")
    parser.add_argument("--report-out", default="", help="JSON report path")
    parser.add_argument("--csv-out", default="", help="CSV report path")
    args = parser.parse_args()

    dataset = args.dataset
    known_doi_file = Path(args.known_doi_file).resolve()
    discovered_queue = (
        Path(args.discovered_queue).resolve()
        if args.discovered_queue
        else ROOT / "data" / "raw" / f"doi_queue.{dataset}.discovered.txt"
    )
    triage_queue = (
        Path(args.triage_queue).resolve()
        if args.triage_queue
        else ROOT / "data" / "raw" / f"doi_queue.{dataset}.triage_relevant.txt"
    )
    paper_library = (
        Path(args.paper_library).resolve()
        if args.paper_library
        else ROOT / "data" / "processed" / f"paper_library_{dataset}.json"
    )
    curated = (
        Path(args.curated).resolve()
        if args.curated
        else (
            ROOT / "data" / "curated" / "claims.json"
            if dataset == "mechanistic"
            else ROOT / "data" / "curated" / "disorder_claims.json"
        )
    )

    report_out = (
        Path(args.report_out).resolve()
        if args.report_out
        else ROOT / "data" / "processed" / f"recall_audit_{dataset}.json"
    )
    csv_out = (
        Path(args.csv_out).resolve()
        if args.csv_out
        else ROOT / "data" / "processed" / f"recall_audit_{dataset}.csv"
    )

    known_dois = read_known_dois(known_doi_file)
    known_set = set(known_dois)
    discovered_set = read_queue_dois(discovered_queue)
    triage_set = read_queue_dois(triage_queue)
    library_map = read_paper_library(paper_library)
    curated_set = read_curated_dois(curated)

    rows: List[dict] = []
    for doi in known_dois:
        library_row = library_map.get(doi, {})
        pdf_local_path = normalize(library_row.get("pdf_local_path", ""))
        in_library = doi in library_map
        with_pdf = bool(pdf_local_path)
        rows.append(
            {
                "doi": doi,
                "in_discovered_queue": doi in discovered_set,
                "in_triage_queue": doi in triage_set,
                "in_paper_library": in_library,
                "has_local_pdf": with_pdf,
                "in_curated_claims": doi in curated_set,
                "library_status": normalize(library_row.get("library_status", "")),
                "pdf_download_status": normalize(library_row.get("pdf_download_status", "")),
                "study_title": normalize(library_row.get("study_title", "")),
            }
        )

    known_total = len(known_set)
    discovered_hits = sum(1 for doi in known_set if doi in discovered_set)
    triage_hits = sum(1 for doi in known_set if doi in triage_set)
    library_hits = sum(1 for doi in known_set if doi in library_map)
    with_pdf_hits = sum(1 for doi in known_set if normalize(library_map.get(doi, {}).get("pdf_local_path", "")))
    curated_hits = sum(1 for doi in known_set if doi in curated_set)

    report = {
        "generated_at_utc": now_utc(),
        "dataset": dataset,
        "inputs": {
            "known_doi_file": str(known_doi_file),
            "discovered_queue": str(discovered_queue),
            "triage_queue": str(triage_queue),
            "paper_library": str(paper_library),
            "curated": str(curated),
        },
        "counts": {
            "known_total": known_total,
            "discovered_hits": discovered_hits,
            "triage_hits": triage_hits,
            "paper_library_hits": library_hits,
            "with_local_pdf_hits": with_pdf_hits,
            "curated_hits": curated_hits,
        },
        "coverage_percent": {
            "discovered": round(pct(discovered_hits, known_total), 2),
            "triage": round(pct(triage_hits, known_total), 2),
            "paper_library": round(pct(library_hits, known_total), 2),
            "with_local_pdf": round(pct(with_pdf_hits, known_total), 2),
            "curated": round(pct(curated_hits, known_total), 2),
        },
        "missing": {
            "discovered": sorted([doi for doi in known_set if doi not in discovered_set]),
            "triage": sorted([doi for doi in known_set if doi not in triage_set]),
            "paper_library": sorted([doi for doi in known_set if doi not in library_map]),
            "with_local_pdf": sorted(
                [
                    doi
                    for doi in known_set
                    if not normalize(library_map.get(doi, {}).get("pdf_local_path", ""))
                ]
            ),
            "curated": sorted([doi for doi in known_set if doi not in curated_set]),
        },
        "rows": rows,
    }

    report_out.parent.mkdir(parents=True, exist_ok=True)
    report_out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    csv_out.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "doi",
        "in_discovered_queue",
        "in_triage_queue",
        "in_paper_library",
        "has_local_pdf",
        "in_curated_claims",
        "library_status",
        "pdf_download_status",
        "study_title",
    ]
    with csv_out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Dataset: {dataset}")
    print(f"Known DOIs: {known_total}")
    print(f"In discovered queue: {discovered_hits}")
    print(f"In triage queue: {triage_hits}")
    print(f"In paper library: {library_hits}")
    print(f"With local PDF: {with_pdf_hits}")
    print(f"In curated claims: {curated_hits}")
    print(f"Report JSON: {report_out}")
    print(f"Report CSV: {csv_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
