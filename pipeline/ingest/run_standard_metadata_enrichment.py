#!/usr/bin/env python3
"""Run role-aware metadata enrichment for the unified paper corpus."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_WORK_DIR = ROOT / "data" / "processed" / "corpus" / "metadata_enrichment_runs"
DEFAULT_PAPERS_TABLE = ROOT / "data" / "processed" / "corpus" / "candidate_papers.parquet"
DEFAULT_METADATA_TABLE = ROOT / "data" / "processed" / "corpus" / "paper_metadata_enrichment.parquet"
DEFAULT_TABLE_OUT_DIR = ROOT / "data" / "processed" / "corpus"
DEFAULT_CONFIG = ROOT / "pipeline" / "config.example.yaml"

CORE_METADATA_PROVIDER_ORDER = "pubmed,pmc,openalex,crossref,semantic_scholar"
OPEN_ACCESS_PROVIDER_ORDER = "unpaywall,openalex,pmc"


def now_run_id() -> str:
    return "standard_metadata_enrichment_" + dt.datetime.now(dt.timezone.utc).strftime("%Y_%m_%d_%H%M%S")


def clean(value: object) -> str:
    return "" if value is None else str(value).strip()


def normalize_doi(raw: object) -> str:
    text = clean(raw)
    lowered = text.lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/", "http://dx.doi.org/", "doi:"):
        if lowered.startswith(prefix):
            text = text[len(prefix) :]
            break
    return text.strip().lower()


def read_dois_from_file(path: Path) -> list[str]:
    dois: list[str] = []
    seen: set[str] = set()
    if not path.exists():
        raise FileNotFoundError(f"DOI file not found: {path}")
    with path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.reader(handle):
            if not row:
                continue
            first = clean(row[0])
            if not first or first.startswith("#") or first.lower() in {"doi", "study_doi"}:
                continue
            doi = normalize_doi(first)
            if not doi or doi in seen:
                continue
            seen.add(doi)
            dois.append(doi)
    return dois


def combine_doi_files(paths: list[Path], output_path: Path) -> tuple[Path, int]:
    all_dois: list[str] = []
    seen: set[str] = set()
    for path in paths:
        for doi in read_dois_from_file(path):
            if doi in seen:
                continue
            seen.add(doi)
            all_dois.append(doi)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        handle.write("# DOI scope for role-aware metadata enrichment\n")
        writer = csv.writer(handle)
        for doi in sorted(all_dois):
            writer.writerow([doi])
    return output_path, len(all_dois)


def add_if_value(command: list[str], flag: str, value: str | int | float | None) -> None:
    if value is None:
        return
    text = clean(value)
    if text:
        command.extend([flag, text])


def build_commands(args: argparse.Namespace, doi_file: Path | None) -> list[tuple[str, list[str]]]:
    commands: list[tuple[str, list[str]]] = []
    python = sys.executable

    if not args.skip_corpus_rebuild:
        commands.append(
            (
                "rebuild unified corpus tables",
                [
                    python,
                    str(ROOT / "pipeline" / "validate" / "build_context_provenance_audit.py"),
                    "--dataset",
                    args.dataset,
                    "--table-out-dir",
                    str(Path(args.table_out_dir).resolve()),
                ],
            )
        )

    if not args.skip_core_metadata:
        command = [
            python,
            str(ROOT / "pipeline" / "ingest" / "enrich_paper_metadata.py"),
            "--papers-table",
            str(Path(args.papers_table).resolve()),
            "--output-table",
            str(Path(args.metadata_table).resolve()),
            "--config",
            str(Path(args.config).resolve()),
            "--run-id",
            args.run_id,
            "--metadata-provider-order",
            args.core_provider_order,
            "--write-every",
            str(args.write_every),
            "--progress-every",
            str(args.progress_every),
            "--timeout-sec",
            str(args.timeout_sec),
            "--max-retry-after-sec",
            str(args.max_retry_after_sec),
        ]
        if args.refresh_existing_core:
            command.append("--refresh-existing")
        else:
            command.append("--retry-missing-metadata")
        if doi_file is not None:
            command.extend(["--doi-file", str(doi_file)])
        add_if_value(command, "--limit", args.limit if args.limit > 0 else None)
        add_if_value(command, "--max-retries", args.max_retries)
        commands.append(("enrich core bibliographic metadata and abstracts", command))

    if not args.skip_publication_types:
        command = [
            python,
            str(ROOT / "pipeline" / "ingest" / "refresh_pubmed_publication_types.py"),
            "--metadata-table",
            str(Path(args.metadata_table).resolve()),
            "--config",
            str(Path(args.config).resolve()),
            "--progress-every",
            str(args.progress_every),
            "--timeout-sec",
            str(args.timeout_sec),
            "--max-retry-after-sec",
            str(args.max_retry_after_sec),
        ]
        if doi_file is not None:
            command.extend(["--doi-file", str(doi_file)])
        add_if_value(command, "--limit", args.limit if args.limit > 0 else None)
        add_if_value(command, "--max-retries", args.max_retries)
        if args.dry_run:
            command.append("--dry-run")
        commands.append(("refresh PubMed publication-type labels", command))

    if not args.skip_open_access:
        command = [
            python,
            str(ROOT / "pipeline" / "ingest" / "refresh_open_access_links.py"),
            "--metadata-table",
            str(Path(args.metadata_table).resolve()),
            "--provider-order",
            args.open_access_provider_order,
            "--config",
            str(Path(args.config).resolve()),
            "--write-every",
            str(args.write_every),
            "--progress-every",
            str(args.progress_every),
            "--timeout-sec",
            str(args.timeout_sec),
            "--max-retry-after-sec",
            str(args.max_retry_after_sec),
        ]
        if not args.refresh_all_open_access:
            command.append("--only-missing-pdf-url")
        if doi_file is not None:
            command.extend(["--doi-file", str(doi_file)])
        add_if_value(command, "--limit", args.limit if args.limit > 0 else None)
        add_if_value(command, "--max-retries", args.max_retries)
        if args.dry_run:
            command.append("--dry-run")
        commands.append(("refresh open-access status and PDF URLs", command))

    return commands


def run_command(label: str, command: list[str], *, dry_run: bool) -> None:
    print(f"\n[{label}]", flush=True)
    print(" ".join(command), flush=True)
    if dry_run:
        return
    subprocess.run(command, cwd=ROOT, check=True)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run role-aware corpus metadata enrichment.")
    parser.add_argument("--dataset", choices=["all", "mechanistic", "disorder"], default="all")
    parser.add_argument("--run-id", default=now_run_id())
    parser.add_argument("--doi-file", action="append", default=[], help="DOI scope file. Can be supplied more than once.")
    parser.add_argument("--work-dir", default=str(DEFAULT_WORK_DIR))
    parser.add_argument("--papers-table", default=str(DEFAULT_PAPERS_TABLE))
    parser.add_argument("--metadata-table", default=str(DEFAULT_METADATA_TABLE))
    parser.add_argument("--table-out-dir", default=str(DEFAULT_TABLE_OUT_DIR))
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--core-provider-order", default=CORE_METADATA_PROVIDER_ORDER)
    parser.add_argument("--open-access-provider-order", default=OPEN_ACCESS_PROVIDER_ORDER)
    parser.add_argument("--skip-corpus-rebuild", action="store_true")
    parser.add_argument("--skip-core-metadata", action="store_true")
    parser.add_argument("--skip-publication-types", action="store_true")
    parser.add_argument("--skip-open-access", action="store_true")
    parser.add_argument("--refresh-existing-core", action="store_true")
    parser.add_argument("--refresh-all-open-access", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--write-every", type=int, default=100)
    parser.add_argument("--progress-every", type=int, default=25)
    parser.add_argument("--timeout-sec", type=int, default=40)
    parser.add_argument("--max-retry-after-sec", type=int, default=120)
    parser.add_argument("--max-retries", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    work_dir = Path(args.work_dir).resolve() / args.run_id
    doi_file = None
    if args.doi_file:
        doi_paths = [Path(path).resolve() for path in args.doi_file]
        doi_file, doi_count = combine_doi_files(doi_paths, work_dir / "doi_scope.txt")
        print(f"DOI scope: {doi_count:,} unique DOIs -> {doi_file}", flush=True)

    commands = build_commands(args, doi_file)
    for label, command in commands:
        run_command(label, command, dry_run=bool(args.dry_run))

    print("\nStandard metadata enrichment complete.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
