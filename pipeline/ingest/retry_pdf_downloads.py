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


def read_allowed_dois(path: Path) -> set[str]:
    allowed: set[str] = set()
    if not path.exists():
        raise SystemExit(f"DOI filter file not found: {path}")
    with path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.reader(handle):
            if not row:
                continue
            first = normalize(row[0])
            if not first or first.startswith("#"):
                continue
            doi = normalize_doi(first)
            if doi:
                allowed.add(doi.lower())
    return allowed


def main() -> int:
    parser = argparse.ArgumentParser(description="Retry PDF downloads for selected paper-library statuses")
    parser.add_argument("--dataset", choices=["mechanistic", "disorder"], required=True)
    parser.add_argument(
        "--statuses",
        default="download_failed,no_pdf_url,invalid_pdf_content,invalid_pdf_existing",
        help="Comma-separated pdf_download_status values to retry",
    )
    parser.add_argument("--doi-file", default="", help="Optional DOI queue file limiting which rows can be retried")
    parser.add_argument("--limit", type=int, default=0, help="Optional max DOI rows to queue")
    parser.add_argument("--config", default=str(ROOT / "pipeline" / "config.example.yaml"))
    parser.add_argument("--openalex-email", default="")
    parser.add_argument("--openalex-api-key", default="")
    parser.add_argument("--openalex-rps", default="")
    parser.add_argument("--ncbi-email", default="")
    parser.add_argument("--ncbi-api-key", default="")
    parser.add_argument("--pubmed-rps", default="")
    parser.add_argument("--pmc-rps", default="")
    parser.add_argument("--crossref-email", default="")
    parser.add_argument("--crossref-rps", default="")
    parser.add_argument("--unpaywall-email", default="")
    parser.add_argument("--unpaywall-rps", default="")
    parser.add_argument("--metadata-provider-order", default="")
    parser.add_argument("--max-retries", default="")
    parser.add_argument("--timeout-sec", default="")
    parser.add_argument("--max-retry-after-sec", default="")
    parser.add_argument(
        "--action-reason-contains",
        default="",
        help="Only retry rows whose action_reason contains this text",
    )
    parser.add_argument("--progress-every", type=int, default=25)
    parser.add_argument("--queue-out", default="", help="Optional retry queue output path")
    parser.add_argument("--skip-sync", action="store_true", help="Only generate queue; do not run sync")
    args = parser.parse_args()

    statuses = set(parse_statuses(args.statuses))
    if not statuses:
        raise SystemExit("At least one retry status is required")
    allowed_dois = read_allowed_dois(Path(args.doi_file).resolve()) if normalize(args.doi_file) else set()

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
        if allowed_dois and doi.lower() not in allowed_dois:
            continue
        if normalize(row.get("pdf_download_status", "")) not in statuses:
            continue
        action_reason_filter = normalize(args.action_reason_contains).lower()
        if action_reason_filter and action_reason_filter not in normalize(row.get("action_reason", "")).lower():
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
    if normalize(args.openalex_api_key):
        cmd.extend(["--openalex-api-key", normalize(args.openalex_api_key)])
    if normalize(args.openalex_rps):
        cmd.extend(["--openalex-rps", normalize(args.openalex_rps)])
    if normalize(args.ncbi_email):
        cmd.extend(["--ncbi-email", normalize(args.ncbi_email)])
    if normalize(args.ncbi_api_key):
        cmd.extend(["--ncbi-api-key", normalize(args.ncbi_api_key)])
    if normalize(args.pubmed_rps):
        cmd.extend(["--pubmed-rps", normalize(args.pubmed_rps)])
    if normalize(args.pmc_rps):
        cmd.extend(["--pmc-rps", normalize(args.pmc_rps)])
    if normalize(args.crossref_email):
        cmd.extend(["--crossref-email", normalize(args.crossref_email)])
    if normalize(args.crossref_rps):
        cmd.extend(["--crossref-rps", normalize(args.crossref_rps)])
    if normalize(args.unpaywall_email):
        cmd.extend(["--unpaywall-email", normalize(args.unpaywall_email)])
    if normalize(args.unpaywall_rps):
        cmd.extend(["--unpaywall-rps", normalize(args.unpaywall_rps)])
    if normalize(args.metadata_provider_order):
        cmd.extend(["--metadata-provider-order", normalize(args.metadata_provider_order)])
    if normalize(args.max_retries):
        cmd.extend(["--max-retries", normalize(args.max_retries)])
    if normalize(args.timeout_sec):
        cmd.extend(["--timeout-sec", normalize(args.timeout_sec)])
    if normalize(args.max_retry_after_sec):
        cmd.extend(["--max-retry-after-sec", normalize(args.max_retry_after_sec)])

    print("Sync run: starting retry sync now...")
    proc = subprocess.run(cmd, cwd=ROOT, text=True)
    if proc.returncode != 0:
        raise SystemExit(proc.returncode)
    print("Sync run: done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
