#!/usr/bin/env python3
"""Refresh open-access status and PDF URL fields without touching core metadata."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import datetime as dt
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from typing import Any
from urllib.parse import urlparse

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.ingest.enrich_paper_metadata import (  # noqa: E402
    DEFAULT_OUTPUT_TABLE,
    DEFAULT_PAPERS_TABLE,
    OUTPUT_COLUMNS,
    candidate_metadata_row,
    clean,
    merge_rows,
    merged_output_rows,
    row_by_doi,
)
from pipeline.ingest.candidate_status import apply_candidate_updates  # noqa: E402
from pipeline.ingest.metadata_utils import (  # noqa: E402
    RateLimitedHttpClient,
    extract_pmcid_from_url,
    is_probable_pdf_url,
    join_candidates,
    load_config,
    lookup_openalex_work,
    lookup_openalex_work_by_id,
    lookup_pmc_oa_links,
    lookup_unpaywall_metadata,
    metadata_from_openalex_work,
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


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def write_parquet_atomic(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent, delete=False)
    temporary = Path(handle.name)
    handle.close()
    try:
        frame.to_parquet(temporary, engine="pyarrow", index=False)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def write_json_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
        delete=False,
    )
    temporary = Path(handle.name)
    try:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
        handle.close()
        os.replace(temporary, path)
    finally:
        if not handle.closed:
            handle.close()
        temporary.unlink(missing_ok=True)


def is_doi_identifier(value: object) -> bool:
    return bool(re.fullmatch(r"10\.\d{4,9}/\S+", normalize_doi(clean(value)), flags=re.IGNORECASE))


def row_has_probable_pdf_url(row: pd.Series) -> bool:
    return any(
        is_probable_pdf_url(url)
        for field in ("best_pdf_url", "pdf_url_candidates")
        for url in split_candidates(row.get(field, ""))
    )


def materialize_scoped_metadata(
    metadata_df: pd.DataFrame,
    papers_table: Path,
    scoped_dois: set[str],
) -> tuple[pd.DataFrame, int]:
    """Give a scoped refresh complete candidate-ledger coverage."""
    if not scoped_dois:
        return metadata_df, 0
    existing_by_doi = row_by_doi(metadata_df.to_dict("records"))
    papers = pd.read_parquet(papers_table)
    candidate_by_doi: dict[str, dict] = {}
    for raw in papers.to_dict("records"):
        candidate = candidate_metadata_row(raw)
        doi = normalize_doi(candidate.get("doi", "")).lower()
        if doi in scoped_dois:
            candidate_by_doi[doi] = candidate

    missing = sorted(scoped_dois - set(existing_by_doi) - set(candidate_by_doi))
    if missing:
        examples = ", ".join(missing[:10])
        raise ValueError(f"Scoped identifiers missing from metadata and candidate tables: {len(missing)} ({examples})")

    added = 0
    for doi in sorted(scoped_dois):
        candidate = candidate_by_doi.get(doi, {})
        if doi not in existing_by_doi:
            added += 1
        existing_by_doi[doi] = merge_rows(existing_by_doi.get(doi, {}), candidate)
    rows = merged_output_rows({}, existing_by_doi)
    return pd.DataFrame(rows, columns=list(OUTPUT_COLUMNS)), added


def load_pmc_identity_blocked_dois(path: Path | None) -> set[str]:
    """Return records whose PMC source was proven to be the wrong article."""
    if path is None or not path.is_file():
        return set()
    payload = json.loads(path.read_text(encoding="utf-8"))
    out: set[str] = set()
    for row in payload.get("records", []):
        if not isinstance(row, dict):
            continue
        error = clean(row.get("error", ""))
        doi = normalize_doi(clean(row.get("doi", ""))).lower()
        if doi and clean(row.get("status", "")) == "failed" and "identity mismatch" in error.lower():
            out.add(doi)
    return out


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
        out = out[~out.apply(row_has_probable_pdf_url, axis=1)].copy()
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


def fresh_open_access_observation(metadata: dict[str, Any]) -> dict[str, Any]:
    """Record only OA evidence returned by a provider in the current run.

    The merged metadata row can contain an OA label from an older run. Keeping
    this observation separate prevents historical backfills from mistaking a
    stale stored label for fresh positive OA evidence.
    """
    is_oa = clean(metadata.get("is_oa", "")) or clean(metadata.get("open_access_is_oa", ""))
    status = clean(metadata.get("oa_status", "")) or clean(metadata.get("open_access_status", ""))
    oa_url = clean(metadata.get("oa_url", "")) or clean(metadata.get("open_access_url", ""))
    return {
        "positive": is_oa.lower() == "true" or status_is_open(status),
        "is_oa": is_oa,
        "status": status,
        "oa_url": oa_url,
        "best_pdf_url": clean(metadata.get("best_pdf_url", "")),
        "pdf_url_candidates": join_candidates(split_candidates(metadata.get("pdf_url_candidates", ""))),
    }


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
    blocked_providers: set[str] | None = None,
) -> tuple[dict[str, str], list[str], list[str], list[str], dict[str, dict[str, Any]]]:
    doi = normalize_doi(clean(row.get("doi", "")))
    updates: dict[str, str] = {}
    providers_queried: list[str] = []
    errors: list[str] = []
    providers_skipped: list[str] = []
    provider_oa_observations: dict[str, dict[str, Any]] = {}
    working_row = row.copy()
    blocked_providers = blocked_providers or set()

    def skip_reason(provider: str) -> str:
        if provider in blocked_providers:
            return "blocked_by_identity_audit"
        if provider == "unpaywall" and not is_doi_identifier(doi):
            return "non_doi_identifier"
        if provider == "openalex" and not clean(working_row.get("openalex_id", "")) and not is_doi_identifier(doi):
            return "no_supported_identifier"
        if provider == "pmc" and not pmcid_hint_from_row(working_row):
            return "no_pmcid"
        return ""

    def lookup_provider(provider: str, source_row: pd.Series) -> dict[str, Any]:
        if provider == "unpaywall":
            if not usable_email(settings.get("unpaywall_email", "")):
                raise ValueError("unpaywall_email_missing_or_placeholder")
            return lookup_unpaywall_metadata(
                clients["unpaywall"],
                doi=doi,
                email=settings["unpaywall_email"],
                paper=paper_payload(source_row),
            ) or {}
        if provider == "openalex":
            openalex_id = clean(source_row.get("openalex_id", ""))
            if openalex_id:
                work = lookup_openalex_work_by_id(
                    clients["openalex"],
                    openalex_id=openalex_id,
                    email=settings.get("openalex_email", ""),
                    api_key=settings.get("openalex_api_key", ""),
                )
            else:
                work = lookup_openalex_work(
                    clients["openalex"],
                    doi=doi,
                    email=settings.get("openalex_email", ""),
                    api_key=settings.get("openalex_api_key", ""),
                )
            return metadata_from_openalex_work(work, paper_payload(source_row)) if work else {}
        if provider == "pmc":
            return lookup_pmc_oa_links(clients["pmc"], pmcid=pmcid_hint_from_row(source_row))
        return {}

    def apply_provider_result(provider: str, metadata: dict[str, Any]) -> None:
        nonlocal working_row

        field_updates, _changed = apply_open_access_fields(
            working_row,
            metadata,
            authoritative_status=provider == "unpaywall",
        )
        if field_updates:
            for field, value in field_updates.items():
                working_row[field] = value
            updates.update(field_updates)

    if row_has_probable_pdf_url(working_row) and not expand_existing_pdf_candidates:
        return updates, providers_queried, errors, providers_skipped, provider_oa_observations

    for provider in provider_order:
        if row_has_probable_pdf_url(working_row) and not expand_existing_pdf_candidates:
            break
        reason = skip_reason(provider)
        if reason:
            providers_skipped.append(f"{provider}: {reason}")
            continue
        providers_queried.append(provider)
        try:
            provider_metadata = lookup_provider(provider, working_row.copy())
            provider_oa_observations[provider] = fresh_open_access_observation(provider_metadata)
            apply_provider_result(provider, provider_metadata)
        except Exception as err:  # keep going to fallback providers
            errors.append(f"{provider}: {type(err).__name__}: {err}")
    return updates, providers_queried, errors, providers_skipped, provider_oa_observations


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Refresh open-access and PDF URL fields only.")
    parser.add_argument("--metadata-table", default=str(DEFAULT_OUTPUT_TABLE))
    parser.add_argument("--papers-table", default=str(DEFAULT_PAPERS_TABLE))
    parser.add_argument(
        "--no-update-candidate-table",
        action="store_true",
        help="Do not synchronize refreshed access fields back to the candidate ledger after completion.",
    )
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
    parser.add_argument("--pmc-report", default="", help="PMC XML report used to block identity-mismatched PMC links.")
    parser.add_argument("--report-json", default="", help="Optional versioned per-record run report.")
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
    parser.add_argument("--workers", type=int, default=8, help="Concurrent records; provider clients enforce shared RPS limits.")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    metadata_table = Path(args.metadata_table).resolve()
    output_table = Path(args.output_table).resolve() if clean(args.output_table) else metadata_table
    provider_order = parse_provider_order(args.provider_order)
    df = pd.read_parquet(metadata_table)
    scoped_dois = read_doi_file(Path(args.doi_file).resolve()) if clean(args.doi_file) else set()
    materialized_rows = 0
    if scoped_dois:
        df, materialized_rows = materialize_scoped_metadata(
            df,
            Path(args.papers_table).resolve(),
            scoped_dois,
        )
    pmc_report_path = Path(args.pmc_report).resolve() if clean(args.pmc_report) else None
    pmc_identity_blocked = load_pmc_identity_blocked_dois(pmc_report_path)
    report_path = Path(args.report_json).resolve() if clean(args.report_json) else None
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
        f"rows={len(selected):,} scope={len(scoped_dois):,} materialized={materialized_rows:,} "
        f"providers={','.join(provider_order)} workers={max(1, args.workers)} output={output_table}",
        flush=True,
    )
    started_at_utc = now_utc()
    updated_rows = 0
    new_pdf_urls = 0
    changed_best_pdf_urls = 0
    expanded_candidate_rows = 0
    provider_counts = {provider: 0 for provider in provider_order}
    error_count = 0
    skipped_provider_count = 0
    fresh_oa_positive_rows = 0
    report_records: list[dict] = []
    candidate_update_summary: dict = {}

    def checkpoint(position: int) -> None:
        if args.dry_run:
            return
        write_parquet_atomic(output_table, df)
        if report_path is not None:
            write_json_atomic(
                report_path,
                {
                    "schema_version": "open_access_link_refresh_report_v2",
                    "started_at_utc": started_at_utc,
                    "updated_at_utc": now_utc(),
                    "complete": position == len(selected),
                    "inputs": {
                        "metadata_table": str(metadata_table),
                        "papers_table": str(Path(args.papers_table).resolve()),
                        "doi_file": str(Path(args.doi_file).resolve()) if clean(args.doi_file) else "",
                        "pmc_report": str(pmc_report_path) if pmc_report_path else "",
                        "provider_order": provider_order,
                        "workers": max(1, args.workers),
                        "only_missing_pdf_url": bool(args.only_missing_pdf_url),
                    },
                    "counts": {
                        "scope": len(scoped_dois),
                        "scope_rows_materialized": materialized_rows,
                        "rows_selected": len(selected),
                        "rows_processed": position,
                        "rows_updated": updated_rows,
                        "new_pdf_urls": new_pdf_urls,
                        "changed_best_pdf_urls": changed_best_pdf_urls,
                        "expanded_candidate_rows": expanded_candidate_rows,
                        "provider_queries": provider_counts,
                        "provider_errors": error_count,
                        "provider_skips": skipped_provider_count,
                        "fresh_oa_positive_rows": fresh_oa_positive_rows,
                        "pmc_identity_blocked_dois": len(pmc_identity_blocked),
                        "candidate_update": candidate_update_summary,
                    },
                    "records": report_records,
                },
            )

    def refresh_selected(item: tuple[object, pd.Series]) -> tuple:
        index, row = item
        doi = normalize_doi(clean(row.get("doi", ""))).lower()
        blocked_providers = {"pmc"} if doi in pmc_identity_blocked else set()
        updates, providers_queried, errors, providers_skipped, provider_oa_observations = refresh_row(
            row,
            provider_order=provider_order,
            clients=clients,
            settings=settings,
            expand_existing_pdf_candidates=bool(args.expand_existing_pdf_candidates),
            blocked_providers=blocked_providers,
        )
        return (
            index,
            row,
            doi,
            updates,
            providers_queried,
            errors,
            providers_skipped,
            provider_oa_observations,
        )

    row_executor = ThreadPoolExecutor(max_workers=max(1, args.workers))
    refreshed_rows = row_executor.map(refresh_selected, selected.iterrows())
    for position, result in enumerate(refreshed_rows, start=1):
        (
            index,
            row,
            doi,
            updates,
            providers_queried,
            errors,
            providers_skipped,
            provider_oa_observations,
        ) = result
        had_pdf = row_has_probable_pdf_url(row)
        old_best_pdf = clean(row.get("best_pdf_url", ""))
        old_candidates = set(split_candidates(row.get("pdf_url_candidates", "")))
        for provider in providers_queried:
            provider_counts[provider] = provider_counts.get(provider, 0) + 1
        error_count += len(errors)
        skipped_provider_count += len(providers_skipped)
        fresh_positive_providers = [
            provider
            for provider, observation in provider_oa_observations.items()
            if observation.get("positive") is True
        ]
        if fresh_positive_providers:
            fresh_oa_positive_rows += 1
        added_candidate_urls: list[str] = []
        if updates:
            updated_rows += 1
            for field, value in updates.items():
                df.at[index, field] = value
            if clean(updates.get("best_pdf_url", "")) and clean(updates.get("best_pdf_url", "")) != old_best_pdf:
                changed_best_pdf_urls += 1
            new_candidates = set(split_candidates(updates.get("pdf_url_candidates", "")))
            added_candidate_urls = sorted(new_candidates - old_candidates)
            if added_candidate_urls:
                if not had_pdf:
                    new_pdf_urls += 1
                expanded_candidate_rows += 1
        final_row = row.copy()
        for field, value in updates.items():
            final_row[field] = value
        report_records.append(
            {
                "doi": doi,
                "status": (
                    "pdf_url_found"
                    if row_has_probable_pdf_url(final_row)
                    else "pdf_candidate_found"
                    if added_candidate_urls
                    else "error_without_pdf"
                    if errors
                    else "no_pdf_url"
                ),
                "providers_queried": providers_queried,
                "providers_skipped": providers_skipped,
                "errors": errors,
                "fresh_open_access_positive": bool(fresh_positive_providers),
                "fresh_open_access_positive_providers": fresh_positive_providers,
                "provider_open_access_observations": provider_oa_observations,
                "added_pdf_url_candidates": added_candidate_urls,
                "best_pdf_url": clean(final_row.get("best_pdf_url", "")),
                "pdf_url_candidates": clean(final_row.get("pdf_url_candidates", "")),
                "final_open_access_is_oa": clean(final_row.get("open_access_is_oa", "")),
                "final_open_access_status": clean(final_row.get("open_access_status", "")),
                "final_open_access_url": clean(final_row.get("open_access_url", "")),
            }
        )
        if not args.dry_run and args.write_every > 0 and position % args.write_every == 0:
            checkpoint(position)
        if args.progress_every > 0 and (position % args.progress_every == 0 or position == len(selected)):
            print(
                "PROGRESS: open-access/PDF URL refresh "
                f"{position:,}/{len(selected):,} updated={updated_rows:,} new_pdf_urls={new_pdf_urls:,} "
                f"changed_best_pdf_urls={changed_best_pdf_urls:,} expanded_candidates={expanded_candidate_rows:,} errors={error_count:,}",
                flush=True,
            )

    row_executor.shutdown(wait=True)

    if not args.dry_run:
        if not args.no_update_candidate_table:
            update_scope = scoped_dois or {
                normalize_doi(clean(value)).lower()
                for value in selected.get("doi", pd.Series(dtype="string"))
                if normalize_doi(clean(value))
            }
            update_rows = df[
                df["doi"].map(lambda value: normalize_doi(clean(value)).lower()).isin(update_scope)
            ][["doi", *OA_FIELDS]].copy()
            candidate_update_summary = apply_candidate_updates(
                candidate_table=Path(args.papers_table).resolve(),
                updates=update_rows,
            )
        checkpoint(len(selected))

    print(f"Rows considered: {len(selected):,}")
    print(f"Rows updated: {updated_rows:,}")
    print(f"Rows with new PDF URL candidates: {new_pdf_urls:,}")
    print(f"Changed best PDF URLs: {changed_best_pdf_urls:,}")
    print(f"Rows with expanded PDF candidates: {expanded_candidate_rows:,}")
    print(f"Provider queries: {provider_counts}")
    print(f"Provider errors: {error_count:,}")
    print(f"Provider skips: {skipped_provider_count:,}")
    print(f"Rows with fresh positive OA evidence: {fresh_oa_positive_rows:,}")
    print(f"Scoped rows materialized: {materialized_rows:,}")
    print(f"PMC identity-blocked records: {len(pmc_identity_blocked):,}")
    print(f"Dry run: {bool(args.dry_run)}")
    print(f"Metadata table: {output_table}")
    if candidate_update_summary:
        print(
            "Candidate table update: "
            f"matched={candidate_update_summary.get('matched_candidate_rows', 0):,} "
            f"updated={candidate_update_summary.get('updated_candidate_rows', 0):,}"
        )
    if report_path is not None:
        print(f"Report: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
