#!/usr/bin/env python3
"""Prune PDFs for triaged-irrelevant papers."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import shutil
import sys
from pathlib import Path
from typing import Dict, List, Set

ROOT = Path(__file__).resolve().parents[2]


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


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: List[dict]) -> None:
    fieldnames = sorted({k for row in rows for k in row.keys()}) if rows else []
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def flatten_db_row(row: dict) -> dict:
    out = dict(row)
    contexts = out.get("contexts", [])
    if isinstance(contexts, list):
        out["contexts"] = json.dumps(contexts, ensure_ascii=False)
    else:
        out["contexts"] = normalize(contexts)
    return out


def parse_csv_set(raw: str) -> Set[str]:
    return {normalize(item) for item in raw.split(",") if normalize(item)}


def unique_target_path(target: Path) -> Path:
    if not target.exists():
        return target
    stem = target.stem
    suffix = target.suffix
    parent = target.parent
    idx = 1
    while True:
        candidate = parent / f"{stem}.dup{idx}{suffix}"
        if not candidate.exists():
            return candidate
        idx += 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Prune PDFs for triaged-irrelevant papers")
    parser.add_argument("--dataset", choices=["mechanistic", "disorder"], required=True)
    parser.add_argument(
        "--triage-json",
        default="",
        help="Path to triage report JSON (default data/processed/triage_report_<dataset>.json)",
    )
    parser.add_argument(
        "--paper-db-json",
        default="",
        help="Path to paper library JSON (default data/processed/paper_library_<dataset>.json)",
    )
    parser.add_argument(
        "--paper-db-csv",
        default="",
        help="Path to paper library CSV (default data/processed/paper_library_<dataset>.csv)",
    )
    parser.add_argument(
        "--relevance-labels",
        default="likely_irrelevant",
        help="Comma-separated triage relevance labels to prune",
    )
    parser.add_argument(
        "--mode",
        choices=["move", "delete"],
        default="move",
        help="move (default) archives files; delete permanently removes files",
    )
    parser.add_argument(
        "--archive-dir",
        default="",
        help="Archive directory when --mode move (default data/raw/papers/<dataset>/excluded)",
    )
    parser.add_argument(
        "--report-json",
        default="",
        help="Cleanup report JSON path (default data/processed/pdf_cleanup_report_<dataset>.json)",
    )
    parser.add_argument("--apply", action="store_true", help="Execute filesystem changes")
    args = parser.parse_args()

    triage_json = (
        Path(args.triage_json).resolve()
        if args.triage_json
        else ROOT / "data" / "processed" / f"triage_report_{args.dataset}.json"
    )
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
    archive_dir = (
        Path(args.archive_dir).resolve()
        if args.archive_dir
        else ROOT / "data" / "raw" / "papers" / args.dataset / "excluded"
    )
    report_json = (
        Path(args.report_json).resolve()
        if args.report_json
        else ROOT / "data" / "processed" / f"pdf_cleanup_report_{args.dataset}.json"
    )

    if not triage_json.exists():
        raise SystemExit(f"Triage report not found: {triage_json}")
    if not paper_db_json.exists():
        raise SystemExit(f"Paper library not found: {paper_db_json}")

    relevance_labels = parse_csv_set(args.relevance_labels)
    triage = load_json(triage_json)
    if not isinstance(triage, dict):
        raise SystemExit(f"Expected triage JSON object at {triage_json}")
    triage_rows = triage.get("rows", [])
    if not isinstance(triage_rows, list):
        raise SystemExit(f"Expected triage rows array at {triage_json}")

    triage_by_doi: Dict[str, dict] = {}
    for row in triage_rows:
        if not isinstance(row, dict):
            continue
        doi = normalize_doi(row.get("study_doi", "")).lower()
        if doi:
            triage_by_doi[doi] = row

    library_rows = load_json(paper_db_json)
    if not isinstance(library_rows, list):
        raise SystemExit(f"Expected paper library JSON array at {paper_db_json}")

    candidates: List[dict] = []
    for idx, row in enumerate(library_rows, start=1):
        if not isinstance(row, dict):
            continue
        doi = normalize_doi(row.get("study_doi", "")).lower()
        if not doi:
            continue
        triage_row = triage_by_doi.get(doi)
        if not triage_row:
            continue
        relevance = normalize(triage_row.get("relevance_suggested", ""))
        if relevance_labels and relevance not in relevance_labels:
            continue

        pdf_path_text = normalize(row.get("pdf_local_path", ""))
        if not pdf_path_text:
            continue
        pdf_path = Path(pdf_path_text)
        exists = pdf_path.exists()
        if not exists:
            continue

        candidates.append(
            {
                "row_index": idx,
                "study_doi": normalize(row.get("study_doi", "")),
                "study_title": normalize(row.get("study_title", "")),
                "relevance_suggested": relevance,
                "source_type_suggested": normalize(triage_row.get("source_type_suggested", "")),
                "pdf_path": str(pdf_path),
                "pdf_size_bytes": int(pdf_path.stat().st_size),
            }
        )

    operations = []
    moved = 0
    deleted = 0
    failed = 0
    bytes_affected = 0

    if args.apply and args.mode == "move":
        archive_dir.mkdir(parents=True, exist_ok=True)

    for candidate in candidates:
        src = Path(candidate["pdf_path"])
        op = {
            "study_doi": candidate["study_doi"],
            "pdf_path_before": str(src),
            "mode": args.mode,
            "status": "planned",
            "error": "",
            "pdf_size_bytes": candidate["pdf_size_bytes"],
            "pdf_path_after": "",
        }
        if not args.apply:
            operations.append(op)
            continue

        try:
            if args.mode == "move":
                dst = unique_target_path(archive_dir / src.name)
                shutil.move(str(src), str(dst))
                op["pdf_path_after"] = str(dst)
                op["status"] = "moved"
                moved += 1
            else:
                src.unlink()
                op["status"] = "deleted"
                deleted += 1
            bytes_affected += int(candidate["pdf_size_bytes"])
        except Exception as err:
            op["status"] = "failed"
            op["error"] = f"{type(err).__name__}: {err}"
            failed += 1
        operations.append(op)

    updated_rows = library_rows
    if args.apply:
        doi_to_op = {normalize_doi(op["study_doi"]).lower(): op for op in operations if op["status"] in {"moved", "deleted"}}
        timestamp = now_utc()
        for row in updated_rows:
            doi = normalize_doi(row.get("study_doi", "")).lower()
            if doi not in doi_to_op:
                continue
            row["pdf_local_path"] = ""
            row["pdf_size_bytes"] = ""
            row["pdf_sha256"] = ""
            row["pdf_download_status"] = "pruned_irrelevant"
            row["library_status"] = "excluded_not_relevant"
            row["action_reason"] = "triage_excluded_irrelevant"
            row["last_checked_utc"] = timestamp

        write_json(paper_db_json, updated_rows)
        write_csv(paper_db_csv, [flatten_db_row(row) for row in updated_rows if isinstance(row, dict)])

    report = {
        "generated_at": now_utc(),
        "dataset": args.dataset,
        "apply": args.apply,
        "mode": args.mode,
        "relevance_labels": sorted(relevance_labels),
        "triage_json": str(triage_json),
        "paper_db_json": str(paper_db_json),
        "paper_db_csv": str(paper_db_csv),
        "archive_dir": str(archive_dir),
        "counts": {
            "candidates": len(candidates),
            "operations_planned": len(operations),
            "moved": moved,
            "deleted": deleted,
            "failed": failed,
            "bytes_affected": bytes_affected,
        },
        "operations": operations,
        "candidates": candidates,
    }
    write_json(report_json, report)

    print(f"Dataset: {args.dataset}")
    print(f"Apply mode: {args.apply}")
    print(f"Operation mode: {args.mode}")
    print(f"Relevance labels: {','.join(sorted(relevance_labels))}")
    print(f"Candidate PDFs: {len(candidates)}")
    if args.apply:
        print(f"Moved: {moved}")
        print(f"Deleted: {deleted}")
        print(f"Failed: {failed}")
        print(f"Bytes affected: {bytes_affected}")
        print(f"Updated paper DB JSON: {paper_db_json}")
        print(f"Updated paper DB CSV: {paper_db_csv}")
        if args.mode == "move":
            print(f"Archive dir: {archive_dir}")
    print(f"Report JSON: {report_json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
