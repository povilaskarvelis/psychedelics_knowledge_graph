#!/usr/bin/env python3
"""Import manually acquired PDFs into paper library using DOI-based filename matching."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.fulltext.import_manual_pdfs import (  # noqa: E402
    build_filename_slug_lookup,
    extract_pdf_metadata_text,
    extract_pdf_text,
    looks_like_pdf,
    select_match,
)


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def normalize(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def normalize_doi(raw: str) -> str:
    text = normalize(raw)
    if not text:
        return ""
    if text.lower().startswith("doi:"):
        text = text[4:]
    for prefix in (
        "https://doi.org/",
        "http://doi.org/",
        "https://dx.doi.org/",
        "http://dx.doi.org/",
    ):
        if text.lower().startswith(prefix):
            text = text[len(prefix) :]
            break
    return text.strip()


def pdf_filename_for_doi(doi: str) -> str:
    slug = re.sub(r"[^a-z0-9._-]+", "_", normalize_doi(doi).lower())
    slug = re.sub(r"_+", "_", slug).strip("._")
    if not slug:
        slug = "paper"
    digest = hashlib.sha1(normalize_doi(doi).encode("utf-8")).hexdigest()[:10]
    slug = slug[:90]
    return f"{slug}__{digest}.pdf"


def load_json_array(path: Path) -> List[dict]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, list):
        raise ValueError(f"Expected JSON array at {path}")
    return data


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def flatten_db_row(row: dict) -> dict:
    out = dict(row)
    contexts = out.get("contexts", [])
    out["contexts"] = json.dumps(contexts, ensure_ascii=False) if isinstance(contexts, list) else normalize(contexts)
    return out


def write_csv(path: Path, rows: List[dict]) -> None:
    fieldnames = sorted({k for row in rows for k in row.keys()}) if rows else []
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def parse_candidate_doi_from_stem(stem: str) -> str:
    raw = unquote(stem)
    if raw.lower().startswith("doi_"):
        raw = raw[4:]
    raw = raw.replace("doi.org_", "")
    raw = raw.replace("https_doi.org_", "")
    raw = raw.replace("http_doi.org_", "")

    if raw.startswith("10.") and "/" in raw:
        return normalize_doi(raw)
    if raw.startswith("10.") and "_" in raw:
        # common manual naming: 10.xxxx_yyyy  => 10.xxxx/yyyy
        return normalize_doi(raw.replace("_", "/", 1))
    return ""


def resolve_doi_for_file(path: Path, filename_to_doi: Dict[str, str], slug_to_doi: Dict[str, str]) -> str:
    name = path.name
    stem = path.stem

    if name in filename_to_doi:
        return filename_to_doi[name]

    parsed = parse_candidate_doi_from_stem(stem)
    if parsed:
        return parsed

    if "__" in stem:
        prefix = stem.split("__", 1)[0].lower()
        if prefix in slug_to_doi:
            return slug_to_doi[prefix]

    if stem.lower() in slug_to_doi:
        return slug_to_doi[stem.lower()]

    return ""


def verify_manual_pdf_identity(
    path: Path,
    expected_doi: str,
    known_records: Dict[str, dict],
    *,
    min_title_score: float = 0.86,
    max_pages: int = 3,
) -> tuple[bool, str, list[dict]]:
    if not looks_like_pdf(path):
        return False, "file_does_not_start_with_pdf_header", []
    text = extract_pdf_text(path, max_pages=max_pages)
    metadata_text = extract_pdf_metadata_text(path)
    matched_doi, basis, candidates = select_match(
        file_path=path,
        known_records=known_records,
        text=text,
        metadata_text=metadata_text,
        enable_title_match=True,
        min_title_score=min_title_score,
        min_title_margin=0.12,
        filename_slug_lookup=build_filename_slug_lookup(known_records),
    )
    if normalize_doi(matched_doi).lower() != normalize_doi(expected_doi).lower():
        return False, basis or "source_identity_unverified", candidates
    return True, basis, candidates


def main() -> int:
    parser = argparse.ArgumentParser(description="Import manually downloaded PDFs into paper library")
    parser.add_argument("--dataset", choices=["mechanistic", "disorder"], required=True)
    parser.add_argument("--source-dir", required=True, help="Directory containing manual PDFs")
    parser.add_argument("--paper-db-json", default="", help="Paper DB JSON path override")
    parser.add_argument("--paper-db-csv", default="", help="Paper DB CSV path override")
    parser.add_argument("--pdf-dir", default="", help="Target PDF directory override")
    parser.add_argument("--move", action="store_true", help="Move files instead of copying")
    parser.add_argument("--apply", action="store_true", help="Write changes (default is dry-run)")
    parser.add_argument("--min-title-score", type=float, default=0.86)
    parser.add_argument("--max-pages", type=int, default=3)
    parser.add_argument(
        "--report",
        default="",
        help="Optional report path (defaults to data/processed/manual_pdf_import_report_<dataset>.json)",
    )
    args = parser.parse_args()

    source_dir = Path(args.source_dir).resolve()
    if not source_dir.exists() or not source_dir.is_dir():
        raise SystemExit(f"Source dir not found or not a directory: {source_dir}")

    paper_db_json = (
        Path(args.paper_db_json).resolve()
        if args.paper_db_json
        else ROOT / "data" / "processed" / f"paper_library_{args.dataset}.json"
    )
    paper_db_csv = (
        Path(args.paper_db_csv).resolve()
        if args.paper_db_csv
        else ROOT / "data" / "processed" / f"paper_library_{args.dataset}.csv"
    )
    pdf_dir = (
        Path(args.pdf_dir).resolve()
        if args.pdf_dir
        else ROOT / "data" / "raw" / "papers" / "pdfs"
    )
    report_path = (
        Path(args.report).resolve()
        if args.report
        else ROOT / "data" / "processed" / f"manual_pdf_import_report_{args.dataset}.json"
    )

    if not paper_db_json.exists():
        raise SystemExit(f"Paper DB JSON not found: {paper_db_json}")

    rows = load_json_array(paper_db_json)
    row_by_doi: Dict[str, dict] = {}
    filename_to_doi: Dict[str, str] = {}
    slug_to_doi: Dict[str, str] = {}
    for row in rows:
        doi = normalize_doi(row.get("study_doi", ""))
        if not doi:
            continue
        row_by_doi[doi.lower()] = row
        canonical = pdf_filename_for_doi(doi)
        filename_to_doi[canonical] = doi
        slug_to_doi[canonical.split("__", 1)[0].lower()] = doi

    files = sorted([p for p in source_dir.iterdir() if p.is_file() and p.suffix.lower() == ".pdf"])
    imported: List[dict] = []
    unresolved: List[dict] = []
    skipped: List[dict] = []

    for file_path in files:
        doi = resolve_doi_for_file(file_path, filename_to_doi=filename_to_doi, slug_to_doi=slug_to_doi)
        doi_key = normalize_doi(doi).lower()
        if not doi_key:
            unresolved.append({"file": str(file_path), "reason": "could_not_resolve_doi_from_filename"})
            continue

        row = row_by_doi.get(doi_key)
        if not row:
            unresolved.append({"file": str(file_path), "reason": f"doi_not_in_paper_library: {doi}"})
            continue

        verified, identity_basis, identity_candidates = verify_manual_pdf_identity(
            file_path,
            doi,
            row_by_doi,
            min_title_score=args.min_title_score,
            max_pages=max(1, args.max_pages),
        )
        if not verified:
            unresolved.append(
                {
                    "file": str(file_path),
                    "doi": doi,
                    "reason": identity_basis,
                    "candidate_matches": identity_candidates,
                }
            )
            continue

        canonical_name = pdf_filename_for_doi(doi)
        dest_path = pdf_dir / canonical_name

        if args.apply:
            pdf_dir.mkdir(parents=True, exist_ok=True)
            if file_path.resolve() != dest_path.resolve():
                if args.move:
                    shutil.move(str(file_path), str(dest_path))
                else:
                    shutil.copy2(str(file_path), str(dest_path))
            size = int(dest_path.stat().st_size) if dest_path.exists() else 0
            digest = sha256_file(dest_path) if dest_path.exists() and size > 0 else ""
            row["pdf_local_path"] = str(dest_path) if size > 0 else ""
            row["pdf_size_bytes"] = size if size > 0 else ""
            row["pdf_sha256"] = digest
            row["pdf_download_status"] = "manual_import"
            row["library_status"] = "in_database" if size > 0 else normalize(row.get("library_status", ""))
            row["action_reason"] = "manual_pdf_import"
            row["last_checked_utc"] = now_utc()
        else:
            if dest_path.exists() and dest_path.stat().st_size > 0:
                skipped.append({"file": str(file_path), "doi": doi, "reason": "destination_already_exists"})
                continue

        imported.append(
            {
                "file": str(file_path),
                "doi": doi,
                "destination": str(dest_path),
                "mode": "move" if args.move else "copy",
                "source_identity_basis": identity_basis,
            }
        )

    report = {
        "generated_at": now_utc(),
        "dataset": args.dataset,
        "source_dir": str(source_dir),
        "pdf_dir": str(pdf_dir),
        "apply": args.apply,
        "move": args.move,
        "counts": {
            "source_pdf_files": len(files),
            "imported_matches": len(imported),
            "unresolved": len(unresolved),
            "skipped": len(skipped),
        },
        "imported": imported,
        "unresolved": unresolved,
        "skipped": skipped,
    }

    if args.apply:
        write_json(paper_db_json, rows)
        write_csv(paper_db_csv, [flatten_db_row(row) for row in rows])

    write_json(report_path, report)
    print(f"Dataset: {args.dataset}")
    print(f"Source PDF files: {len(files)}")
    print(f"Imported matches: {len(imported)}")
    print(f"Unresolved files: {len(unresolved)}")
    print(f"Skipped files: {len(skipped)}")
    print(f"Apply mode: {'yes' if args.apply else 'no (dry-run)'}")
    if args.apply:
        print(f"Paper DB JSON: {paper_db_json}")
        print(f"Paper DB CSV: {paper_db_csv}")
    print(f"Report: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
