#!/usr/bin/env python3
"""Enrich paper metadata from the unified corpus tables."""

from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.ingest.sync_paper_library import (
    DEFAULT_METADATA_PROVIDER_ORDER,
    PAPER_METADATA_FIELDS,
    PAPER_METADATA_SCHEMA_VERSION,
    RateLimitedHttpClient,
    fetch_metadata_with_fallbacks,
    load_config,
    metadata_has_useful_fields,
    merge_metadata_values,
    normalize_doi,
    parse_provider_order,
    provider_chain,
    read_float,
    read_int,
    row_needs_core_metadata_refresh,
    row_needs_metadata_refresh,
    usable_email,
)

DEFAULT_PAPERS_TABLE = ROOT / "data" / "processed" / "corpus" / "candidate_papers.parquet"
DEFAULT_OUTPUT_TABLE = ROOT / "data" / "processed" / "corpus" / "paper_metadata_enrichment.parquet"

OUTPUT_COLUMNS = (
    "doi",
    "datasets",
    "study_title",
    "study_year",
    "authors",
    "abstract",
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
    "pmid",
    "pmcid",
    "openalex_id",
    "semantic_scholar_id",
    "metadata_provider",
    "metadata_provider_chain",
    "metadata_providers_queried",
    "metadata_lookup_error",
    "metadata_lookup_warnings",
    "metadata_missing_reason",
    "metadata_enrichment_status",
    "metadata_enrichment_run_id",
    "metadata_enriched_at_utc",
    "paper_metadata_schema_version",
    "open_access_is_oa",
    "open_access_status",
    "open_access_url",
    "best_pdf_url",
    "pdf_url_candidates",
)


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def default_run_id() -> str:
    return "metadata_enrichment_" + dt.datetime.now(dt.timezone.utc).strftime("%Y_%m_%d_%H%M%S")


def clean(value: Any) -> str:
    try:
        import pandas as pd

        if pd.isna(value):
            return ""
    except Exception:
        pass
    if value is None:
        return ""
    return str(value).strip()


def read_table(path: Path) -> list[dict]:
    import pandas as pd

    if not path.exists():
        return []
    return pd.read_parquet(path).to_dict("records")


def write_table(path: Path, rows: list[dict]) -> None:
    import pandas as pd

    path.parent.mkdir(parents=True, exist_ok=True)
    normalized_rows = [{column: clean(row.get(column, "")) for column in OUTPUT_COLUMNS} for row in rows]
    pd.DataFrame(normalized_rows, columns=list(OUTPUT_COLUMNS)).to_parquet(path, engine="pyarrow", index=False)


def row_by_doi(rows: list[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for row in rows:
        doi = normalize_doi(clean(row.get("doi") or row.get("study_doi")))
        if doi:
            out[doi.lower()] = row
    return out


def candidate_metadata_row(row: dict) -> dict:
    doi = normalize_doi(clean(row.get("doi") or row.get("study_doi")))
    out = {column: "" for column in OUTPUT_COLUMNS}
    out.update(
        {
            "doi": doi,
            "datasets": clean(row.get("datasets", "")),
            "study_title": clean(row.get("study_title", "")),
            "study_year": clean(row.get("study_year", "")),
            "authors": clean(row.get("authors", "")),
            "abstract": clean(row.get("abstract", "")),
            "pmid": clean(row.get("pmid", "")),
            "pmcid": clean(row.get("pmcid", "")),
            "openalex_id": clean(row.get("openalex_id", "")),
            "semantic_scholar_id": clean(row.get("semantic_scholar_id", "")),
            "paper_metadata_schema_version": PAPER_METADATA_SCHEMA_VERSION,
            "open_access_status": clean(row.get("open_access_status", "")),
        }
    )
    for field in PAPER_METADATA_FIELDS:
        out[field] = clean(row.get(field, ""))
    return out


def merge_rows(primary: dict, fallback: dict) -> dict:
    out = {column: clean(fallback.get(column, "")) for column in OUTPUT_COLUMNS}
    for column in OUTPUT_COLUMNS:
        value = clean(primary.get(column, ""))
        if value:
            out[column] = value
    return out


def fetch_metadata_row(
    *,
    doi: str,
    base_row: dict,
    provider_order: list[str],
    clients: dict[str, RateLimitedHttpClient],
    openalex_email: str,
    openalex_api_key: str,
    ncbi_email: str,
    ncbi_api_key: str,
    crossref_email: str,
    unpaywall_email: str,
    semantic_scholar_api_key: str,
    run_id: str,
) -> tuple[dict, list[dict], list[str]]:
    paper = {
        "study_doi": doi,
        "study_title": clean(base_row.get("study_title", "")),
        "study_year": clean(base_row.get("study_year", "")),
        "authors": clean(base_row.get("authors", "")),
        "abstract": clean(base_row.get("abstract", "")),
        **{field: clean(base_row.get(field, "")) for field in PAPER_METADATA_FIELDS},
    }
    metadata, provider_errors, providers_queried = fetch_metadata_with_fallbacks(
        doi=doi,
        paper=paper,
        provider_order=provider_order,
        clients=clients,
        openalex_email=openalex_email,
        openalex_api_key=openalex_api_key,
        ncbi_email=ncbi_email,
        ncbi_api_key=ncbi_api_key,
        crossref_email=crossref_email,
        unpaywall_email=unpaywall_email,
        semantic_scholar_api_key=semantic_scholar_api_key,
        initial_metadata=None,
    )

    metadata_error = ""
    if not metadata_has_useful_fields(metadata):
        metadata_error = "all_metadata_providers_failed"
        if provider_errors:
            metadata_error = " | ".join(f"{err['provider']}: {err['error']}" for err in provider_errors)
        metadata = {}

    merged_metadata = merge_metadata_values(metadata, base_row)
    out = {column: "" for column in OUTPUT_COLUMNS}
    out.update(
        {
            "doi": doi,
            "datasets": clean(base_row.get("datasets", "")),
            "study_title": clean(merged_metadata.get("study_title", "")),
            "study_year": clean(merged_metadata.get("study_year", "")),
            "authors": clean(merged_metadata.get("authors", "")),
            "abstract": clean(merged_metadata.get("abstract", "")),
            "pmid": clean(merged_metadata.get("pmid", "")),
            "pmcid": clean(merged_metadata.get("pmcid", "")),
            "openalex_id": clean(merged_metadata.get("openalex_id", "")),
            "semantic_scholar_id": clean(merged_metadata.get("semantic_scholar_id", "")),
            "metadata_provider": clean(merged_metadata.get("metadata_provider", "")),
            "metadata_provider_chain": clean(merged_metadata.get("metadata_provider_chain", "")),
            "metadata_providers_queried": clean(merged_metadata.get("metadata_providers_queried", ""))
            or "|".join(providers_queried),
            "metadata_lookup_error": metadata_error,
            "metadata_lookup_warnings": clean(merged_metadata.get("metadata_lookup_warnings", "")),
            "metadata_missing_reason": clean(merged_metadata.get("metadata_missing_reason", "")),
            "metadata_enrichment_status": "enriched" if not metadata_error else "metadata_unresolved",
            "metadata_enrichment_run_id": run_id,
            "metadata_enriched_at_utc": now_utc(),
            "paper_metadata_schema_version": PAPER_METADATA_SCHEMA_VERSION,
            "open_access_is_oa": clean(
                merged_metadata.get("is_oa", "")
                or merged_metadata.get("open_access_is_oa", "")
                or merged_metadata.get("unpaywall_is_oa", "")
            ),
            "open_access_status": clean(
                merged_metadata.get("oa_status", "")
                or merged_metadata.get("open_access_status", "")
                or merged_metadata.get("unpaywall_oa_status", "")
            ),
            "open_access_url": clean(
                merged_metadata.get("oa_url", "")
                or merged_metadata.get("open_access_url", "")
                or merged_metadata.get("unpaywall_best_url", "")
            ),
            "best_pdf_url": clean(merged_metadata.get("best_pdf_url", "") or merged_metadata.get("unpaywall_best_pdf_url", "")),
            "pdf_url_candidates": clean(
                merged_metadata.get("pdf_url_candidates", "")
                or merged_metadata.get("unpaywall_pdf_url_candidates", "")
            ),
        }
    )
    for field in PAPER_METADATA_FIELDS:
        out[field] = clean(merged_metadata.get(field, ""))
    return out, provider_errors, providers_queried


def should_query_provider(
    *,
    existing_row: dict | None,
    base_row: dict,
    provider_order: list[str],
    retry_core_metadata: bool,
    retry_missing_metadata: bool,
    refresh_existing: bool,
) -> bool:
    if not provider_order:
        return False
    if refresh_existing:
        return True
    if existing_row is None:
        return True
    if retry_missing_metadata:
        return row_needs_metadata_refresh(base_row)
    if retry_core_metadata:
        return row_needs_core_metadata_refresh(base_row)
    return False


def load_provider_settings(args: argparse.Namespace) -> tuple[dict[str, RateLimitedHttpClient], dict[str, Any]]:
    config = load_config(Path(args.config).resolve())
    oa_cfg = config.get("openalex", {}) if isinstance(config.get("openalex", {}), dict) else {}
    s2_cfg = config.get("semantic_scholar", {}) if isinstance(config.get("semantic_scholar", {}), dict) else {}
    pubmed_cfg = config.get("pubmed", {}) if isinstance(config.get("pubmed", {}), dict) else {}
    pmc_cfg = config.get("pmc", {}) if isinstance(config.get("pmc", {}), dict) else {}
    crossref_cfg = config.get("crossref", {}) if isinstance(config.get("crossref", {}), dict) else {}
    unpaywall_cfg = config.get("unpaywall", {}) if isinstance(config.get("unpaywall", {}), dict) else {}

    settings = {
        "openalex_email": args.openalex_email or str(oa_cfg.get("email", "")) or os.getenv("OPENALEX_EMAIL", ""),
        "openalex_api_key": args.openalex_api_key or str(oa_cfg.get("api_key", "")) or os.getenv("OPENALEX_API_KEY", ""),
        "semantic_scholar_api_key": args.semantic_scholar_api_key
        or str(s2_cfg.get("api_key", ""))
        or os.getenv("S2_API_KEY", ""),
        "ncbi_email": args.ncbi_email or str(pubmed_cfg.get("email", "")) or os.getenv("NCBI_EMAIL", ""),
        "ncbi_api_key": args.ncbi_api_key or str(pubmed_cfg.get("api_key", "")) or os.getenv("NCBI_API_KEY", ""),
        "crossref_email": args.crossref_email or str(crossref_cfg.get("email", "")) or os.getenv("CROSSREF_EMAIL", ""),
    }
    settings["unpaywall_email"] = (
        args.unpaywall_email
        or str(unpaywall_cfg.get("email", ""))
        or os.getenv("UNPAYWALL_EMAIL", "")
        or settings["crossref_email"]
        or settings["openalex_email"]
    )

    max_retries = args.max_retries if args.max_retries is not None else read_int(s2_cfg.get("max_retries"), 4)
    clients = {
        "openalex": RateLimitedHttpClient(
            rps=args.openalex_rps if args.openalex_rps is not None else read_float(oa_cfg.get("rate_limit_per_sec"), 2.0),
            max_retries=max_retries,
            timeout_sec=max(1, args.timeout_sec),
            max_retry_after_sec=max(0, args.max_retry_after_sec),
            user_agent="kg-pipeline/metadata-enrichment-openalex",
        ),
        "pubmed": RateLimitedHttpClient(
            rps=args.pubmed_rps if args.pubmed_rps is not None else read_float(pubmed_cfg.get("rate_limit_per_sec"), 2.5),
            max_retries=max_retries,
            timeout_sec=max(1, args.timeout_sec),
            max_retry_after_sec=max(0, args.max_retry_after_sec),
            user_agent="kg-pipeline/metadata-enrichment-pubmed",
        ),
        "pmc": RateLimitedHttpClient(
            rps=args.pmc_rps if args.pmc_rps is not None else read_float(pmc_cfg.get("rate_limit_per_sec"), 2.5),
            max_retries=max_retries,
            timeout_sec=max(1, args.timeout_sec),
            max_retry_after_sec=max(0, args.max_retry_after_sec),
            user_agent="kg-pipeline/metadata-enrichment-pmc",
        ),
        "crossref": RateLimitedHttpClient(
            rps=args.crossref_rps if args.crossref_rps is not None else read_float(crossref_cfg.get("rate_limit_per_sec"), 5.0),
            max_retries=max_retries,
            timeout_sec=max(1, args.timeout_sec),
            max_retry_after_sec=max(0, args.max_retry_after_sec),
            user_agent="kg-pipeline/metadata-enrichment-crossref",
        ),
        "unpaywall": RateLimitedHttpClient(
            rps=args.unpaywall_rps if args.unpaywall_rps is not None else read_float(unpaywall_cfg.get("rate_limit_per_sec"), 2.0),
            max_retries=max_retries,
            timeout_sec=max(1, args.timeout_sec),
            max_retry_after_sec=max(0, args.max_retry_after_sec),
            user_agent="kg-pipeline/metadata-enrichment-unpaywall",
        ),
        "semantic_scholar": RateLimitedHttpClient(
            rps=args.semantic_scholar_rps
            if args.semantic_scholar_rps is not None
            else read_float(s2_cfg.get("rate_limit_per_sec"), 0.33),
            max_retries=max_retries,
            timeout_sec=max(1, args.timeout_sec),
            max_retry_after_sec=max(0, args.max_retry_after_sec),
            user_agent="kg-pipeline/metadata-enrichment-semantic-scholar",
        ),
    }
    return clients, settings


def main() -> int:
    parser = argparse.ArgumentParser(description="Enrich paper metadata from unified corpus tables")
    parser.add_argument("--papers-table", default=str(DEFAULT_PAPERS_TABLE))
    parser.add_argument("--output-table", default=str(DEFAULT_OUTPUT_TABLE))
    parser.add_argument("--run-id", default="")
    parser.add_argument("--config", default=str(ROOT / "pipeline" / "config.example.yaml"))
    parser.add_argument(
        "--metadata-provider-order",
        default=",".join(DEFAULT_METADATA_PROVIDER_ORDER),
        help="Comma-separated metadata providers, or `none` to only materialize existing corpus metadata.",
    )
    parser.add_argument("--retry-core-metadata", action="store_true", help="Retry previous lookup errors or missing titles.")
    parser.add_argument("--retry-missing-metadata", action="store_true", help="Retry title, abstract, or metadata-error gaps.")
    parser.add_argument("--refresh-existing", action="store_true", help="Query providers for all rows.")
    parser.add_argument("--openalex-email", default="")
    parser.add_argument("--openalex-api-key", default="")
    parser.add_argument("--openalex-rps", type=float, default=None)
    parser.add_argument("--semantic-scholar-api-key", default="")
    parser.add_argument("--semantic-scholar-rps", type=float, default=None)
    parser.add_argument("--ncbi-email", default="")
    parser.add_argument("--ncbi-api-key", default="")
    parser.add_argument("--pubmed-rps", type=float, default=None)
    parser.add_argument("--pmc-rps", type=float, default=None)
    parser.add_argument("--crossref-email", default="")
    parser.add_argument("--crossref-rps", type=float, default=None)
    parser.add_argument("--unpaywall-email", default="")
    parser.add_argument("--unpaywall-rps", type=float, default=None)
    parser.add_argument("--max-retries", type=int, default=None)
    parser.add_argument("--timeout-sec", type=int, default=40)
    parser.add_argument("--max-retry-after-sec", type=int, default=120)
    parser.add_argument("--write-every", type=int, default=100, help="Rewrite the output Parquet table every N rows.")
    parser.add_argument("--progress-every", type=int, default=25)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    provider_order = []
    if clean(args.metadata_provider_order).lower() != "none":
        try:
            provider_order = parse_provider_order(args.metadata_provider_order)
        except ValueError as err:
            raise SystemExit(str(err)) from err
        clients, provider_settings = load_provider_settings(args)
        if "unpaywall" in provider_order and not usable_email(provider_settings["unpaywall_email"]):
            provider_order = [provider for provider in provider_order if provider != "unpaywall"]
            print("WARN: Unpaywall skipped because no real email is configured", file=sys.stderr, flush=True)
    else:
        clients = {}
        provider_settings = {
            "openalex_email": "",
            "openalex_api_key": "",
            "semantic_scholar_api_key": "",
            "ncbi_email": "",
            "ncbi_api_key": "",
            "crossref_email": "",
            "unpaywall_email": "",
        }

    papers_table = Path(args.papers_table).resolve()
    output_table = Path(args.output_table).resolve()
    run_id = clean(args.run_id) or default_run_id()
    candidate_rows = [candidate_metadata_row(row) for row in read_table(papers_table)]
    candidate_rows = [row for row in candidate_rows if row["doi"]]
    if args.limit > 0:
        candidate_rows = candidate_rows[: args.limit]

    existing_rows = read_table(output_table)
    existing_by_doi = row_by_doi(existing_rows)
    output_by_doi: dict[str, dict] = {}
    provider_success_counts: Counter[str] = Counter()
    provider_error_counts: Counter[str] = Counter()
    enriched_now = 0
    reused_existing = 0
    carried_from_candidate = 0
    unresolved = 0

    print(
        "START: metadata enrichment "
        f"papers={len(candidate_rows)} providers={','.join(provider_order) if provider_order else 'none'} "
        f"output={output_table}",
        flush=True,
    )

    for idx, candidate in enumerate(candidate_rows, start=1):
        doi = candidate["doi"]
        existing = existing_by_doi.get(doi.lower())
        base_row = merge_rows(existing or {}, candidate)
        query = should_query_provider(
            existing_row=existing,
            base_row=base_row,
            provider_order=provider_order,
            retry_core_metadata=args.retry_core_metadata,
            retry_missing_metadata=args.retry_missing_metadata,
            refresh_existing=args.refresh_existing,
        )
        if query:
            row, provider_errors, _queried = fetch_metadata_row(
                doi=doi,
                base_row=base_row,
                provider_order=provider_order,
                clients=clients,
                openalex_email=provider_settings["openalex_email"],
                openalex_api_key=provider_settings["openalex_api_key"],
                ncbi_email=provider_settings["ncbi_email"],
                ncbi_api_key=provider_settings["ncbi_api_key"],
                crossref_email=provider_settings["crossref_email"],
                unpaywall_email=provider_settings["unpaywall_email"],
                semantic_scholar_api_key=provider_settings["semantic_scholar_api_key"],
                run_id=run_id,
            )
            for provider in provider_chain(row):
                provider_success_counts[provider] += 1
            for error in provider_errors:
                provider_error_counts[clean(error.get("provider", ""))] += 1
            if clean(row.get("metadata_lookup_error", "")):
                unresolved += 1
            else:
                enriched_now += 1
        else:
            row = base_row
            if existing:
                reused_existing += 1
                if not clean(row.get("metadata_enrichment_status", "")):
                    row["metadata_enrichment_status"] = "existing"
            else:
                carried_from_candidate += 1
                row["metadata_enrichment_status"] = "candidate_metadata"
                row["metadata_enrichment_run_id"] = run_id
                row["metadata_enriched_at_utc"] = now_utc()
            row["paper_metadata_schema_version"] = PAPER_METADATA_SCHEMA_VERSION

        output_by_doi[doi.lower()] = {column: clean(row.get(column, "")) for column in OUTPUT_COLUMNS}

        if args.write_every > 0 and idx % args.write_every == 0:
            write_table(output_table, sorted(output_by_doi.values(), key=lambda item: item["doi"]))
        if args.progress_every > 0 and (idx % args.progress_every == 0 or idx == len(candidate_rows)):
            print(
                "PROGRESS: metadata enrichment "
                f"{idx}/{len(candidate_rows)} enriched_now={enriched_now} reused={reused_existing} "
                f"carried_from_candidate={carried_from_candidate} unresolved={unresolved}",
                flush=True,
            )

    for doi, row in existing_by_doi.items():
        if doi not in output_by_doi:
            output_by_doi[doi] = {column: clean(row.get(column, "")) for column in OUTPUT_COLUMNS}

    final_rows = sorted(output_by_doi.values(), key=lambda item: item["doi"])
    write_table(output_table, final_rows)

    print(f"Metadata enrichment table: {output_table}")
    print(f"Rows written: {len(final_rows)}")
    print(f"Enriched this run: {enriched_now}")
    print(f"Reused existing metadata: {reused_existing}")
    print(f"Carried from candidate table: {carried_from_candidate}")
    print(f"Unresolved this run: {unresolved}")
    print(f"Provider successes: {dict(provider_success_counts)}")
    print(f"Provider errors: {dict(provider_error_counts)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
