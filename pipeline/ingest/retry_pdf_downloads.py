#!/usr/bin/env python3
"""Retry failed/missing OA PDF downloads from existing paper library rows."""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parents[2]


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


def load_json_array(path: Path) -> List[dict]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, list):
        raise ValueError(f"Expected JSON array at {path}")
    return data


def first_context(row: dict) -> Dict[str, str]:
    contexts = row.get("contexts", [])
    if isinstance(contexts, list):
        for item in contexts:
            if isinstance(item, dict):
                return {
                    "compound": normalize(item.get("compound", "")),
                    "entity": normalize(item.get("entity", "")),
                }
    return {"compound": "", "entity": ""}


def write_queue(path: Path, rows: List[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write("# retry queue generated from paper library rows\n")
        handle.write("# doi,compound,target_or_disorder,optional_study_title,optional_study_year,optional_authors\n")
        writer = csv.writer(handle)
        for row in rows:
            ctx = first_context(row)
            writer.writerow(
                [
                    normalize(row.get("study_doi", "")),
                    ctx["compound"],
                    ctx["entity"],
                    normalize(row.get("study_title", "")),
                    normalize(row.get("study_year", "")),
                    normalize(row.get("authors", "")),
                ]
            )


def parse_statuses(raw: str) -> List[str]:
    out = []
    for token in raw.split(","):
        value = normalize(token)
        if value:
            out.append(value)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Retry PDF downloads for selected paper-library statuses")
    parser.add_argument("--dataset", choices=["mechanistic", "disorder"], required=True)
    parser.add_argument(
        "--statuses",
        default="download_failed,no_pdf_url",
        help="Comma-separated pdf_download_status values to retry",
    )
    parser.add_argument("--limit", type=int, default=0, help="Optional max DOI rows to queue")
    parser.add_argument("--config", default=str(ROOT / "pipeline" / "config.example.yaml"))
    parser.add_argument("--openalex-email", default="")
    parser.add_argument("--openalex-rps", default="")
    parser.add_argument("--max-retries", default="")
    parser.add_argument("--progress-every", type=int, default=25)
    parser.add_argument("--queue-out", default="", help="Optional retry queue output path")
    parser.add_argument("--skip-sync", action="store_true", help="Only generate queue; do not run sync")
    args = parser.parse_args()

    statuses = set(parse_statuses(args.statuses))
    if not statuses:
        raise SystemExit("At least one retry status is required")

    paper_db_json = ROOT / "data" / "processed" / f"paper_library_{args.dataset}.json"
    if not paper_db_json.exists():
        raise SystemExit(f"Paper library JSON not found: {paper_db_json}")

    rows = load_json_array(paper_db_json)
    retry_rows: List[dict] = []
    seen = set()
    for row in rows:
        doi = normalize_doi(row.get("study_doi", ""))
        if not doi:
            continue
        if normalize(row.get("pdf_download_status", "")) not in statuses:
            continue
        key = doi.lower()
        if key in seen:
            continue
        seen.add(key)
        retry_rows.append(row)
        if args.limit and len(retry_rows) >= args.limit:
            break

    queue_out = (
        Path(args.queue_out).resolve()
        if args.queue_out
        else ROOT / "data" / "raw" / f"doi_queue.{args.dataset}.retry_pdf.txt"
    )
    write_queue(queue_out, retry_rows)

    print(f"Dataset: {args.dataset}")
    print(f"Statuses retried: {', '.join(sorted(statuses))}")
    print(f"Queue rows written: {len(retry_rows)}")
    print(f"Queue file: {queue_out}")

    if args.skip_sync:
        print("Sync run: skipped (--skip-sync)")
        return 0

    if not retry_rows:
        print("Sync run: skipped (no matching rows)")
        return 0

    cmd = [
        sys.executable,
        str(ROOT / "pipeline" / "ingest" / "sync_paper_library.py"),
        "--dataset",
        args.dataset,
        "--doi-file",
        str(queue_out),
        "--config",
        str(Path(args.config).resolve()),
        "--progress-every",
        str(max(1, args.progress_every)),
    ]
    if normalize(args.openalex_email):
        cmd.extend(["--openalex-email", normalize(args.openalex_email)])
    if normalize(args.openalex_rps):
        cmd.extend(["--openalex-rps", normalize(args.openalex_rps)])
    if normalize(args.max_retries):
        cmd.extend(["--max-retries", normalize(args.max_retries)])

    print("Sync run: starting retry sync now...")
    proc = subprocess.run(cmd, cwd=ROOT, text=True)
    if proc.returncode != 0:
        raise SystemExit(proc.returncode)
    print("Sync run: done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
