#!/usr/bin/env python3
"""Refresh open-access status and PDF URL fields without touching core metadata."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Any
from urllib.parse import urlparse

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.ingest.enrich_paper_metadata import DEFAULT_OUTPUT_TABLE, clean
from pipeline.ingest.metadata_utils import (
    RateLimitedHttpClient,
    extract_pmcid_from_url,
    join_candidates,
    load_config,
    lookup_openalex_work,
    lookup_pmc_oa_links,
    lookup_unpaywall_metadata,
    metadata_from_openalex_work,
    normalize,
    normalize_doi,
    rank_pdf_candidates,
    read_float,
    read_int,
    split_candidates,
    status_is_closed,
    status_is_open,
    usable_email,
)

DEFAULT_ROUTING_TABLE = ROOT / "data" / "processed" / "corpus" / "paper_domain_routing_gemini.parquet"
OA_FIELDS = (
    "open_access_is_oa",
    "open_access_status",
    "open_access_url",
    "best_pdf_url",
    "pdf_url_candidates",
)


def read_doi_file(path: Path) -> set[str]:
    if not path.exists():
        raise FileNotFoundError(f"DOI file does not exist: {path}")
    dois: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        doi = normalize_doi(clean(line))
        if doi and not doi.startswith("#"):
            dois.add(doi.lower())
    return dois


def parse_provider_order(raw: str) -> list[str]:
    allowed = {"unpaywall", "openalex", "pmc"}
    providers: list[str] = []
    for part in raw.split(","):
        provider = clean(part).lower()
        if not provider:
            continue
        if provider not in allowed:
            raise ValueError(f"Unsupported OA/PDF URL provider: {provider}")
        if provider not in providers:
            providers.append(provider)
    return providers or ["unpaywall", "openalex", "pmc"]


def parse_csv_values(raw: str) -> set[str]:
    return {clean(part).lower() for part in raw.split(",") if clean(part)}


def pdf_url_hosts_for_row(row: pd.Series) -> set[str]:
    hosts: set[str] = set()
    for field in ("best_pdf_url", "pdf_url_candidates"):
        for url in split_candidates(row.get(field, "")):
            host = urlparse(url).netloc.lower()
            if host:
                hosts.add(host)
    return hosts


def selected_dois_from_routing(routing_table: Path, *, only_retained_secondary: bool) -> set[str]:
    if not only_retained_secondary:
        return set()
    routing = pd.read_parquet(routing_table)
    selected = routing[
        routing["retained_for_extraction_candidate"].fillna(False).astype(bool)
        & routing["source_family"].fillna("").astype(str).eq("secondary_literature")
    ]
    return {
        normalize_doi(clean(value)).lower()
        for value in selected["doi"].tolist()
        if normalize_doi(clean(value))
    }


def candidate_rows(
    df: pd.DataFrame,
    *,
    doi_file: str,
    routing_table: str,
    only_retained_secondary: bool,
    only_missing_pdf_url: bool,
    only_pdf_url_hosts: set[str] | None,
    limit: int,
) -> pd.DataFrame:
    out = df.copy()
    scoped_dois: set[str] = set()
    if clean(doi_file):
        scoped_dois.update(read_doi_file(Path(doi_file).resolve()))
    if only_retained_secondary:
        scoped_dois.update(selected_dois_from_routing(Path(routing_table).resolve(), only_retained_secondary=True))
    if scoped_dois:
        doi_values = out["doi"].map(lambda value: normalize_doi(clean(value)).lower())
        out = out[doi_values.isin(scoped_dois)].copy()
    if only_missing_pdf_url:
        out = out[out["best_pdf_url"].fillna("").astype(str).str.strip().eq("")].copy()
    if only_pdf_url_hosts:
        out = out[out.apply(lambda row: bool(pdf_url_hosts_for_row(row).intersection(only_pdf_url_hosts)), axis=1)].copy()
    if limit > 0:
        out = out.head(limit).copy()
    return out


def paper_payload(row: pd.Series) -> dict[str, Any]:
    return {
        "study_doi": clean(row.get("doi", "")),
        "study_title": clean(row.get("study_title", "")),
        "study_year": clean(row.get("study_year", "")),
        "authors": clean(row.get("authors", "")),
        "abstract": clean(row.get("abstract", "")),
        "publication_type": clean(row.get("publication_type", "")),
        "trial_registry_ids": clean(row.get("trial_registry_ids", "")),
    }


def pmcid_hint_from_row(row: pd.Series) -> str:
    value = clean(row.get("pmcid", ""))
    if value:
        return value
    for field in ("best_pdf_url", "pdf_url_candidates", "open_access_url"):
        for item in split_candidates(row.get(field, "")):
            pmcid = extract_pmcid_from_url(item)
            if pmcid:
                return pmcid
    return ""


def apply_open_access_fields(row: pd.Series, metadata: dict[str, Any], *, authoritative_status: bool) -> tuple[dict[str, str], bool]:
    updates: dict[str, str] = {}
    new_is_oa = clean(metadata.get("is_oa", "")) or clean(metadata.get("open_access_is_oa", ""))
    new_status = clean(metadata.get("oa_status", "")) or clean(metadata.get("open_access_status", ""))
    new_oa_url = clean(metadata.get("oa_url", "")) or clean(metadata.get("open_access_url", ""))
    new_best_pdf = clean(metadata.get("best_pdf_url", ""))
    new_candidates = split_candidates(metadata.get("pdf_url_candidates", ""))

    current_is_oa = clean(row.get("open_access_is_oa", ""))
    current_status = clean(row.get("open_access_status", ""))
    current_oa_url = clean(row.get("open_access_url", ""))
    current_best_pdf = clean(row.get("best_pdf_url", ""))
    current_candidates = split_candidates(row.get("pdf_url_candidates", ""))

    new_is_open = new_is_oa.lower() == "true" or status_is_open(new_status)
    current_is_closed = current_is_oa.lower() == "false" or status_is_closed(current_status)

    if new_is_oa and (authoritative_status or not current_is_oa or new_is_open):
        updates["open_access_is_oa"] = new_is_oa
    if new_status and (authoritative_status or not current_status or (new_is_open and current_is_closed)):
        updates["open_access_status"] = new_status
    if new_oa_url and (authoritative_status or not current_oa_url):
        updates["open_access_url"] = new_oa_url

    combined_candidates = rank_pdf_candidates([*current_candidates, new_best_pdf, *new_candidates])
    if combined_candidates:
        updates["best_pdf_url"] = combined_candidates[0]
        updates["pdf_url_candidates"] = join_candidates(combined_candidates)

    changed = any(clean(row.get(field, "")) != value for field, value in updates.items())
    return updates, changed


def load_settings(args: argparse.Namespace) -> tuple[dict[str, RateLimitedHttpClient], dict[str, str]]:
    config = load_config(Path(args.config).resolve())
    unpaywall_cfg = config.get("unpaywall", {}) if isinstance(config.get("unpaywall", {}), dict) else {}
    openalex_cfg = config.get("openalex", {}) if isinstance(config.get("openalex", {}), dict) else {}
    pmc_cfg = config.get("pmc", {}) if isinstance(config.get("pmc", {}), dict) else {}
    settings = {
        "unpaywall_email": args.unpaywall_email or str(unpaywall_cfg.get("email", "")),
        "openalex_email": args.openalex_email or str(openalex_cfg.get("email", "")),
        "openalex_api_key": args.openalex_api_key or str(openalex_cfg.get("api_key", "")),
    }
    max_retries = args.max_retries if args.max_retries is not None else read_int(unpaywall_cfg.get("max_retries"), 2)
    clients = {
        "unpaywall": RateLimitedHttpClient(
            rps=args.unpaywall_rps if args.unpaywall_rps is not None else read_float(unpaywall_cfg.get("rate_limit_per_sec"), 2.0),
            max_retries=max_retries,
            timeout_sec=max(1, args.timeout_sec),
            max_retry_after_sec=max(0, args.max_retry_after_sec),
            user_agent="kg-pipeline/open-access-link-refresh-unpaywall",
        ),
        "openalex": RateLimitedHttpClient(
            rps=args.openalex_rps if args.openalex_rps is not None else read_float(openalex_cfg.get("rate_limit_per_sec"), 2.0),
            max_retries=max_retries,
            timeout_sec=max(1, args.timeout_sec),
            max_retry_after_sec=max(0, args.max_retry_after_sec),
            user_agent="kg-pipeline/open-access-link-refresh-openalex",
        ),
        "pmc": RateLimitedHttpClient(
            rps=args.pmc_rps if args.pmc_rps is not None else read_float(pmc_cfg.get("rate_limit_per_sec"), 2.5),
            max_retries=max_retries,
            timeout_sec=max(1, args.timeout_sec),
            max_retry_after_sec=max(0, args.max_retry_after_sec),
            user_agent="kg-pipeline/open-access-link-refresh-pmc",
        ),
    }
    return clients, settings


def refresh_row(
    row: pd.Series,
    *,
    provider_order: list[str],
    clients: dict[str, RateLimitedHttpClient],
    settings: dict[str, str],
    expand_existing_pdf_candidates: bool,
) -> tuple[dict[str, str], list[str], list[str]]:
    doi = normalize_doi(clean(row.get("doi", "")))
    updates: dict[str, str] = {}
    providers_queried: list[str] = []
    errors: list[str] = []
    working_row = row.copy()

    for provider in provider_order:
        if clean(working_row.get("best_pdf_url", "")) and not expand_existing_pdf_candidates:
            break
        metadata: dict[str, Any] = {}
        try:
            providers_queried.append(provider)
            if provider == "unpaywall":
                if not usable_email(settings.get("unpaywall_email", "")):
                    raise ValueError("unpaywall_email_missing_or_placeholder")
                metadata = lookup_unpaywall_metadata(
                    clients["unpaywall"],
                    doi=doi,
                    email=settings["unpaywall_email"],
                    paper=paper_payload(working_row),
                ) or {}
            elif provider == "openalex":
                work = lookup_openalex_work(
                    clients["openalex"],
                    doi=doi,
                    email=settings.get("openalex_email", ""),
                    api_key=settings.get("openalex_api_key", ""),
                )
                metadata = metadata_from_openalex_work(work, paper_payload(working_row)) if work else {}
            elif provider == "pmc":
                pmcid = pmcid_hint_from_row(working_row)
                metadata = lookup_pmc_oa_links(clients["pmc"], pmcid=pmcid) if pmcid else {}
        except Exception as err:  # keep going to fallback providers
            errors.append(f"{provider}: {type(err).__name__}: {err}")
            continue

        field_updates, _changed = apply_open_access_fields(
            working_row,
            metadata,
            authoritative_status=provider == "unpaywall",
        )
        if field_updates:
            for field, value in field_updates.items():
                working_row[field] = value
            updates.update(field_updates)
    return updates, providers_queried, errors


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Refresh open-access and PDF URL fields only.")
    parser.add_argument("--metadata-table", default=str(DEFAULT_OUTPUT_TABLE))
    parser.add_argument("--output-table", default="")
    parser.add_argument("--routing-table", default=str(DEFAULT_ROUTING_TABLE))
    parser.add_argument("--only-retained-secondary", action="store_true")
    parser.add_argument("--only-missing-pdf-url", action="store_true")
    parser.add_argument(
        "--only-pdf-url-hosts",
        default="",
        help="Optional comma-separated URL hosts to target, such as europepmc.org,pmc.ncbi.nlm.nih.gov.",
    )
    parser.add_argument(
        "--expand-existing-pdf-candidates",
        action="store_true",
        help="Query providers even when a PDF URL already exists, merging any alternative candidates found.",
    )
    parser.add_argument("--doi-file", default="")
    parser.add_argument("--provider-order", default="unpaywall,openalex,pmc")
    parser.add_argument("--config", default=str(ROOT / "pipeline" / "config.example.yaml"))
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--write-every", type=int, default=100)
    parser.add_argument("--progress-every", type=int, default=50)
    parser.add_argument("--timeout-sec", type=int, default=40)
    parser.add_argument("--max-retry-after-sec", type=int, default=60)
    parser.add_argument("--max-retries", type=int, default=None)
    parser.add_argument("--unpaywall-email", default="")
    parser.add_argument("--unpaywall-rps", type=float, default=None)
    parser.add_argument("--openalex-email", default="")
    parser.add_argument("--openalex-api-key", default="")
    parser.add_argument("--openalex-rps", type=float, default=None)
    parser.add_argument("--pmc-rps", type=float, default=None)
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    metadata_table = Path(args.metadata_table).resolve()
    output_table = Path(args.output_table).resolve() if clean(args.output_table) else metadata_table
    provider_order = parse_provider_order(args.provider_order)
    df = pd.read_parquet(metadata_table)
    selected = candidate_rows(
        df,
        doi_file=args.doi_file,
        routing_table=args.routing_table,
        only_retained_secondary=bool(args.only_retained_secondary),
        only_missing_pdf_url=bool(args.only_missing_pdf_url),
        only_pdf_url_hosts=parse_csv_values(args.only_pdf_url_hosts),
        limit=max(0, args.limit),
    )
    clients, settings = load_settings(args)

    print(
        "START: open-access/PDF URL refresh "
        f"rows={len(selected):,} providers={','.join(provider_order)} output={output_table}",
        flush=True,
    )
    updated_rows = 0
    new_pdf_urls = 0
    changed_best_pdf_urls = 0
    expanded_candidate_rows = 0
    provider_counts = {provider: 0 for provider in provider_order}
    error_count = 0

    for position, (index, row) in enumerate(selected.iterrows(), start=1):
        had_pdf = bool(clean(row.get("best_pdf_url", "")))
        old_best_pdf = clean(row.get("best_pdf_url", ""))
        old_candidates = set(split_candidates(row.get("pdf_url_candidates", "")))
        updates, providers_queried, errors = refresh_row(
            row,
            provider_order=provider_order,
            clients=clients,
            settings=settings,
            expand_existing_pdf_candidates=bool(args.expand_existing_pdf_candidates),
        )
        for provider in providers_queried:
            provider_counts[provider] = provider_counts.get(provider, 0) + 1
        error_count += len(errors)
        if updates:
            updated_rows += 1
            for field, value in updates.items():
                df.at[index, field] = value
            if not had_pdf and clean(updates.get("best_pdf_url", "")):
                new_pdf_urls += 1
            if clean(updates.get("best_pdf_url", "")) and clean(updates.get("best_pdf_url", "")) != old_best_pdf:
                changed_best_pdf_urls += 1
            new_candidates = set(split_candidates(updates.get("pdf_url_candidates", "")))
            if new_candidates and not new_candidates.issubset(old_candidates):
                expanded_candidate_rows += 1
        if not args.dry_run and args.write_every > 0 and position % args.write_every == 0:
            df.to_parquet(output_table, engine="pyarrow", index=False)
        if args.progress_every > 0 and (position % args.progress_every == 0 or position == len(selected)):
            print(
                "PROGRESS: open-access/PDF URL refresh "
                f"{position:,}/{len(selected):,} updated={updated_rows:,} new_pdf_urls={new_pdf_urls:,} "
                f"changed_best_pdf_urls={changed_best_pdf_urls:,} expanded_candidates={expanded_candidate_rows:,} errors={error_count:,}",
                flush=True,
            )

    if not args.dry_run:
        output_table.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(output_table, engine="pyarrow", index=False)

    print(f"Rows considered: {len(selected):,}")
    print(f"Rows updated: {updated_rows:,}")
    print(f"New best PDF URLs: {new_pdf_urls:,}")
    print(f"Changed best PDF URLs: {changed_best_pdf_urls:,}")
    print(f"Rows with expanded PDF candidates: {expanded_candidate_rows:,}")
    print(f"Provider queries: {provider_counts}")
    print(f"Provider errors: {error_count:,}")
    print(f"Dry run: {bool(args.dry_run)}")
    print(f"Metadata table: {output_table}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
