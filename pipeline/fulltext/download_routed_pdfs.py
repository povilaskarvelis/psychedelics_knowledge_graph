#!/usr/bin/env python3
"""Download PDFs for routed extraction candidates into the canonical PDF store."""

from __future__ import annotations

import argparse
from collections import Counter, deque
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import sys
import time
from typing import Iterable
from urllib.parse import urlparse

import pandas as pd

try:
    from pipeline.extract.build_extraction_routes import build_extraction_routes
    from pipeline.fulltext.pdf_alternate_sources import (
        collect_alternate_pdf_candidates,
        download_alternate_pdf_candidates,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from pipeline.extract.build_extraction_routes import build_extraction_routes
    from pipeline.fulltext.pdf_alternate_sources import (
        collect_alternate_pdf_candidates,
        download_alternate_pdf_candidates,
    )

try:
    from pipeline.ingest.sync_paper_library import (
        RateLimitedHttpClient,
        download_pdf_candidates,
        is_probable_pdf_url,
        join_candidates,
        normalize,
        normalize_doi,
        pdf_filename_for_doi,
        rank_pdf_candidates,
        split_candidates,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from pipeline.ingest.sync_paper_library import (
        RateLimitedHttpClient,
        download_pdf_candidates,
        is_probable_pdf_url,
        join_candidates,
        normalize,
        normalize_doi,
        pdf_filename_for_doi,
        rank_pdf_candidates,
        split_candidates,
    )


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ROUTE_TABLE = ROOT / "data" / "processed" / "corpus" / "paper_extraction_routes.parquet"
DEFAULT_METADATA_TABLE = ROOT / "data" / "processed" / "corpus" / "paper_metadata_enrichment.parquet"
DEFAULT_CANDIDATE_TABLE = ROOT / "data" / "processed" / "corpus" / "candidate_papers.parquet"
DEFAULT_PDF_DIR = ROOT / "data" / "raw" / "papers" / "pdfs"
DEFAULT_REPORT = ROOT / "data" / "processed" / "corpus" / "audits" / "routed_pdf_download_report.json"
DEFAULT_ROUTE_ACTION = "download_pdf_then_extract"
DEFAULT_PRESCREEN_TABLE = ROOT / "data" / "processed" / "corpus" / "paper_prescreen_decisions.parquet"
DEFAULT_DOMAIN_ROUTING_TABLE = ROOT / "data" / "processed" / "corpus" / "paper_domain_routing_gemini.parquet"
DEFAULT_FULLTEXT_DIR = ROOT / "data" / "processed" / "fulltext"
DEFAULT_ROUTE_SUMMARY_JSON = ROOT / "data" / "processed" / "corpus" / "paper_extraction_routes_summary.json"
DEFAULT_ROUTE_COUNTS_CSV = ROOT / "data" / "processed" / "corpus" / "paper_extraction_routes_counts.csv"
DEFAULT_MANUAL_ROUTE_OVERRIDES = ROOT / "pipeline" / "extract" / "manual_extraction_route_overrides.json"
RETRYABLE_FAILURE_CATEGORIES = {"rate_limited", "provider_error", "timeout"}
URL_RE = re.compile(r"https?://[^\s|]+")


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def clean(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    return str(value).strip()


def truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return clean(value).lower() in {"1", "true", "yes", "y"}


def doi_key(value: object) -> str:
    return normalize_doi(clean(value)).lower()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def read_doi_file(path: Path) -> set[str]:
    if not path.exists():
        raise FileNotFoundError(f"DOI file not found: {path}")
    out: set[str] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        doi = doi_key(line.split(",", 1)[0])
        if doi:
            out.add(doi)
    return out


def metadata_by_doi(metadata_df: pd.DataFrame) -> dict[str, dict]:
    if metadata_df.empty or "doi" not in metadata_df.columns:
        return {}
    out: dict[str, dict] = {}
    for row in metadata_df.to_dict("records"):
        key = doi_key(row.get("doi", ""))
        if key and key not in out:
            out[key] = row
    return out


def add_candidates(values: list[str], raw: object) -> None:
    for value in split_candidates(raw):
        if value and value not in values:
            values.append(value)


def probable_pdf_candidates(values: Iterable[str]) -> list[str]:
    return rank_pdf_candidates(value for value in values if is_probable_pdf_url(value))


def weak_pdf_candidates(values: Iterable[str]) -> list[str]:
    probable = set(probable_pdf_candidates(values))
    return [value for value in rank_pdf_candidates(values) if value not in probable]


def pdf_url_quality(values: Iterable[str]) -> str:
    ranked = rank_pdf_candidates(values)
    if probable_pdf_candidates(ranked):
        return "probable_pdf"
    if ranked:
        return "possible_landing_page"
    return "no_url"


def first_nonempty(rows: list[dict], field: str, fallback: object = "") -> str:
    for row in rows:
        value = clean(row.get(field, ""))
        if value:
            return value
    return clean(fallback)


def join_unique(values: Iterable[object]) -> str:
    out: list[str] = []
    for value in values:
        text = clean(value)
        if text and text not in out:
            out.append(text)
    return "|".join(out)


def selected_route_rows(
    routes_df: pd.DataFrame,
    *,
    route_action: str = DEFAULT_ROUTE_ACTION,
    doi_filter: set[str] | None = None,
) -> pd.DataFrame:
    if routes_df.empty:
        return routes_df.copy()
    out = routes_df.copy()
    if "retained_for_extraction_candidate" in out.columns:
        out = out[out["retained_for_extraction_candidate"].map(truthy)].copy()
    if "route_action" in out.columns:
        out = out[out["route_action"].fillna("").astype(str).eq(route_action)].copy()
    if doi_filter:
        out = out[out["doi"].map(doi_key).isin(doi_filter)].copy()
    return out


def build_download_tasks(
    routes_df: pd.DataFrame,
    metadata_df: pd.DataFrame,
    *,
    doi_filter: set[str] | None = None,
    route_action: str = DEFAULT_ROUTE_ACTION,
    limit: int = 0,
) -> list[dict]:
    selected = selected_route_rows(routes_df, route_action=route_action, doi_filter=doi_filter)
    metadata_map = metadata_by_doi(metadata_df)
    grouped: dict[str, list[dict]] = {}
    for row in selected.to_dict("records"):
        key = doi_key(row.get("doi", ""))
        if not key:
            continue
        grouped.setdefault(key, []).append(row)

    tasks: list[dict] = []
    for key in sorted(grouped):
        rows = grouped[key]
        metadata = metadata_map.get(key, {})
        candidates: list[str] = []
        for row in rows:
            add_candidates(candidates, row.get("best_pdf_url", ""))
            add_candidates(candidates, row.get("pdf_url_candidates", ""))
            add_candidates(candidates, row.get("probable_pdf_url_candidates", ""))
        add_candidates(candidates, metadata.get("best_pdf_url", ""))
        add_candidates(candidates, metadata.get("pdf_url_candidates", ""))
        ranked = rank_pdf_candidates(candidates)
        probable = probable_pdf_candidates(ranked)
        weak = [value for value in ranked if value not in set(probable)]
        tasks.append(
            {
                "doi": key,
                "study_title": first_nonempty(rows, "study_title", metadata.get("study_title", "")),
                "study_year": first_nonempty(rows, "study_year", metadata.get("study_year", "")),
                "route_count": len(rows),
                "route_ids": join_unique(row.get("route_id", "") for row in rows),
                "domain_routes": join_unique(row.get("domain_route", "") for row in rows),
                "prompt_profiles": join_unique(row.get("prompt_profile", "") for row in rows),
                "open_access_status": first_nonempty(rows, "open_access_status", metadata.get("open_access_status", "")),
                "pmid": first_nonempty(rows, "pmid", metadata.get("pmid", "")),
                "pmcid": first_nonempty(rows, "pmcid", metadata.get("pmcid", "")),
                "best_pdf_url": probable[0] if probable else ranked[0] if ranked else "",
                "pdf_url_candidates": join_candidates(ranked),
                "probable_pdf_url_candidates": join_candidates(probable),
                "other_url_candidates": join_candidates(weak),
                "pdf_url_quality": pdf_url_quality(ranked),
            }
        )
        if limit > 0 and len(tasks) >= limit:
            break
    return tasks


def candidate_pdf_status_by_doi(candidate_df: pd.DataFrame) -> dict[str, dict]:
    if candidate_df.empty or "doi" not in candidate_df.columns:
        return {}
    out: dict[str, dict] = {}
    for row in candidate_df.to_dict("records"):
        key = doi_key(row.get("doi", ""))
        if key and key not in out:
            out[key] = row
    return out


def parse_statuses(raw: str) -> set[str]:
    return {part.strip().lower() for part in clean(raw).split(",") if part.strip()}


def parse_csv_values(raw: str) -> set[str]:
    return {part.strip().lower() for part in clean(raw).split(",") if part.strip()}


def split_pipe_values(value: object) -> set[str]:
    return {part.strip().lower() for part in clean(value).split("|") if part.strip()}


def hosts_from_candidates(value: object) -> list[str]:
    hosts: list[str] = []
    for url in split_candidates(value):
        host = urlparse(url).netloc.lower()
        if host and host not in hosts:
            hosts.append(host)
    return hosts


def deprioritize_candidates_by_host(candidates: list[str], deprioritized_hosts: set[str]) -> list[str]:
    if not deprioritized_hosts:
        return list(candidates)
    preferred: list[str] = []
    fallback: list[str] = []
    for candidate in candidates:
        host = urlparse(candidate).netloc.lower()
        if host in deprioritized_hosts:
            fallback.append(candidate)
        else:
            preferred.append(candidate)
    return preferred + fallback


def exclude_candidates_by_host(candidates: list[str], excluded_hosts: set[str]) -> list[str]:
    if not excluded_hosts:
        return list(candidates)
    return [candidate for candidate in candidates if urlparse(candidate).netloc.lower() not in excluded_hosts]


def task_download_candidates(
    task: dict,
    *,
    include_weak_pdf_urls: bool = False,
    deprioritized_hosts: set[str] | None = None,
    excluded_hosts: set[str] | None = None,
) -> list[str]:
    all_candidates = split_candidates(task.get("pdf_url_candidates", ""))
    probable_candidates = split_candidates(task.get("probable_pdf_url_candidates", ""))
    candidates = all_candidates if include_weak_pdf_urls else probable_candidates
    candidates = exclude_candidates_by_host(candidates, excluded_hosts or set())
    return deprioritize_candidates_by_host(candidates, deprioritized_hosts or set())


def task_candidates_for_host(
    task: dict,
    deprioritized_hosts: set[str] | None = None,
    excluded_hosts: set[str] | None = None,
) -> list[str]:
    candidates = split_candidates(task.get("probable_pdf_url_candidates", "")) or split_candidates(task.get("pdf_url_candidates", ""))
    candidates = exclude_candidates_by_host(candidates, excluded_hosts or set())
    return deprioritize_candidates_by_host(candidates, deprioritized_hosts or set())


def task_primary_host(
    task: dict,
    deprioritized_hosts: set[str] | None = None,
    excluded_hosts: set[str] | None = None,
) -> str:
    hosts = [
        urlparse(url).netloc.lower()
        for url in task_candidates_for_host(task, deprioritized_hosts, excluded_hosts)
        if urlparse(url).netloc
    ]
    return hosts[0] if hosts else ""


def interleave_tasks_by_host(
    tasks: list[dict],
    deprioritized_hosts: set[str] | None = None,
    excluded_hosts: set[str] | None = None,
) -> list[dict]:
    buckets: dict[str, deque[dict]] = {}
    for task in tasks:
        host = task_primary_host(task, deprioritized_hosts, excluded_hosts) or "no_pdf_host"
        buckets.setdefault(host, deque()).append(task)

    out: list[dict] = []
    active_hosts = list(buckets)
    while active_hosts:
        next_active: list[str] = []
        for host in active_hosts:
            bucket = buckets[host]
            if bucket:
                out.append(bucket.popleft())
            if bucket:
                next_active.append(host)
        active_hosts = next_active
    return out


def error_part_is_transient_host_failure(part: str) -> bool:
    lowered = part.lower()
    return (
        "http error 429" in lowered
        or "too many requests" in lowered
        or "rate limit" in lowered
        or "http error 500" in lowered
        or "http error 502" in lowered
        or "http error 503" in lowered
        or "http error 504" in lowered
        or "empty_response" in lowered
        or "timeouterror" in lowered
        or "timed out" in lowered
        or "timeout" in lowered
    )


def transient_failure_hosts_from_error(error: object) -> list[str]:
    hosts: list[str] = []
    for part in clean(error).split("||"):
        if not error_part_is_transient_host_failure(part):
            continue
        for match in URL_RE.findall(part):
            host = urlparse(match.strip(" ,;.)]")).netloc.lower()
            if host and host not in hosts:
                hosts.append(host)
    return hosts


def rate_limited_hosts_from_error(error: object) -> list[str]:
    return transient_failure_hosts_from_error(error)


def classify_download_failure(status: str, error: str) -> dict[str, object]:
    status_text = clean(status).lower()
    error_text = clean(error)
    lowered = error_text.lower()
    categories: list[str] = []

    def add(category: str) -> None:
        if category not in categories:
            categories.append(category)

    if status_text in {"downloaded", "already_present", "dry_run"}:
        return {
            "failure_category": "",
            "failure_categories": "",
            "retry_recommended": False,
        }
    if status_text == "no_pdf_url":
        add("no_pdf_url")
    if status_text == "no_probable_pdf_url":
        add("weak_pdf_url_only")
    if status_text == "invalid_pdf_content" or "invalid_pdf_content" in lowered or "response_not_pdf" in lowered:
        add("non_pdf_response")
    if "http error 429" in lowered or "too many requests" in lowered or "rate limit" in lowered:
        add("rate_limited")
    if "http error 500" in lowered or "http error 502" in lowered or "http error 503" in lowered or "http error 504" in lowered:
        add("provider_error")
    if "empty_response" in lowered:
        add("provider_error")
    if "timeouterror" in lowered or "timed out" in lowered or "timeout" in lowered:
        add("timeout")
    if "http error 403" in lowered or "forbidden" in lowered:
        add("forbidden")
    if (
        "challenge_or_access_control" in lowered
        or "access control" in lowered
        or "get access" in lowered
        or "sign in to access" in lowered
        or "login required" in lowered
        or "subscribe or purchase" in lowered
    ):
        add("access_controlled")
    if "http error 404" in lowered or "not found" in lowered:
        add("not_found")
    if status_text == "download_failed" and not categories:
        add("other_download_failure")
    if status_text.startswith("invalid_pdf") and not categories:
        add("non_pdf_response")

    primary = next((category for category in categories if category in RETRYABLE_FAILURE_CATEGORIES), "")
    if not primary:
        primary = categories[0] if categories else ""
    retry_recommended = any(category in RETRYABLE_FAILURE_CATEGORIES for category in categories)
    return {
        "failure_category": primary,
        "failure_categories": "|".join(categories),
        "retry_recommended": retry_recommended,
    }


def filter_tasks_by_candidate_status(
    tasks: list[dict],
    candidate_df: pd.DataFrame,
    *,
    skip_candidate_statuses: set[str],
    only_failure_categories: set[str] | None = None,
) -> tuple[list[dict], list[dict]]:
    candidate_map = candidate_pdf_status_by_doi(candidate_df)
    kept: list[dict] = []
    skipped: list[dict] = []
    for task in tasks:
        row = candidate_map.get(task["doi"], {})
        status = clean(row.get("pdf_download_status", "")).lower()
        local_path = clean(row.get("pdf_local_path", ""))
        annotated = {
            **task,
            "candidate_pdf_download_status": status,
            "candidate_pdf_local_path": local_path,
            "candidate_pdf_failure_category": clean(row.get("pdf_download_failure_category", "")),
            "candidate_pdf_failure_categories": clean(row.get("pdf_download_failure_categories", "")),
            "candidate_pdf_retry_recommended": truthy(row.get("pdf_download_retry_recommended", False)),
        }
        if status in skip_candidate_statuses:
            skipped.append({**annotated, "skip_reason": f"candidate_status:{status}"})
            continue
        if only_failure_categories:
            categories = split_pipe_values(annotated["candidate_pdf_failure_categories"])
            if annotated["candidate_pdf_failure_category"]:
                categories.add(annotated["candidate_pdf_failure_category"].lower())
            if not categories.intersection(only_failure_categories):
                skipped.append({**annotated, "skip_reason": "failure_category_filter"})
                continue
        kept.append(annotated)
    return kept, skipped


def ensure_candidate_columns(df: pd.DataFrame) -> pd.DataFrame:
    defaults = {
        "pdf_local_path": "",
        "local_pdf_paths": "",
        "local_pdf_count": 0,
        "pdf_download_status": "",
        "pdf_sha256": "",
        "flag_has_local_pdf": False,
        "library_status": "",
        "best_pdf_url": "",
        "pdf_url_candidates": "",
        "probable_pdf_url_candidates": "",
        "other_url_candidates": "",
        "pdf_url_quality": "",
        "pdf_download_error": "",
        "pdf_download_failure_category": "",
        "pdf_download_failure_categories": "",
        "pdf_download_retry_recommended": False,
    }
    for column, default in defaults.items():
        if column not in df.columns:
            df[column] = default
    return df


def apply_result_to_candidate_table(
    candidate_df: pd.DataFrame,
    result: dict,
) -> bool:
    doi = doi_key(result.get("doi", ""))
    if not doi or "doi" not in candidate_df.columns:
        return False
    mask = candidate_df["doi"].map(doi_key).eq(doi)
    if not mask.any():
        return False

    candidate_df = ensure_candidate_columns(candidate_df)
    changed = False
    status = clean(result.get("status", ""))
    pdf_path = clean(result.get("pdf_local_path", ""))
    sha = clean(result.get("pdf_sha256", ""))
    best_pdf_url = clean(result.get("selected_url", "")) or clean(result.get("best_pdf_url", ""))
    candidates = clean(result.get("pdf_url_candidates", ""))
    probable_candidates = clean(result.get("probable_pdf_url_candidates", ""))
    other_candidates = clean(result.get("other_url_candidates", ""))
    quality = clean(result.get("pdf_url_quality", ""))
    error = clean(result.get("error", ""))
    failure_category = clean(result.get("failure_category", ""))
    failure_categories = clean(result.get("failure_categories", ""))
    retry_recommended = bool(result.get("retry_recommended", False))

    for index in candidate_df.index[mask]:
        updates: dict[str, object] = {
            "best_pdf_url": best_pdf_url or clean(candidate_df.at[index, "best_pdf_url"]),
            "pdf_url_candidates": candidates or clean(candidate_df.at[index, "pdf_url_candidates"]),
            "probable_pdf_url_candidates": probable_candidates,
            "other_url_candidates": other_candidates,
            "pdf_url_quality": quality,
        }
        if status in {"downloaded", "already_present"} and pdf_path:
            updates.update(
                {
                    "pdf_local_path": pdf_path,
                    "local_pdf_paths": pdf_path,
                    "local_pdf_count": 1,
                    "pdf_download_status": status,
                    "pdf_sha256": sha,
                    "flag_has_local_pdf": True,
                    "library_status": "in_database",
                    "pdf_download_error": "",
                    "pdf_download_failure_category": "",
                    "pdf_download_failure_categories": "",
                    "pdf_download_retry_recommended": False,
                }
            )
        elif status:
            updates.update(
                {
                    "pdf_download_status": status,
                    "flag_has_local_pdf": False,
                    "pdf_download_error": error,
                    "pdf_download_failure_category": failure_category,
                    "pdf_download_failure_categories": failure_categories,
                    "pdf_download_retry_recommended": retry_recommended,
                }
            )

        for field, value in updates.items():
            if field not in candidate_df.columns:
                candidate_df[field] = ""
            current = candidate_df.at[index, field]
            if clean(current) != clean(value):
                candidate_df.at[index, field] = value
                changed = True
    return changed


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def wait_for_host_cooldown(candidates: list[str], cooldown_until_by_host: dict[str, float]) -> None:
    waits: list[float] = []
    now = time.monotonic()
    for host in hosts_from_candidates(join_candidates(candidates)):
        until = cooldown_until_by_host.get(host, 0.0)
        if until > now:
            waits.append(until - now)
    if waits:
        time.sleep(max(waits))


def update_rate_limit_cooldowns(
    *,
    result: dict,
    cooldown_until_by_host: dict[str, float],
    cooldown_sec: float,
) -> None:
    if cooldown_sec <= 0:
        return
    if not split_pipe_values(result.get("failure_categories", "")).intersection(RETRYABLE_FAILURE_CATEGORIES):
        return
    until = time.monotonic() + cooldown_sec
    for host in transient_failure_hosts_from_error(result.get("error", "")):
        current = cooldown_until_by_host.get(host, 0.0)
        if until > current:
            cooldown_until_by_host[host] = until


def skipped_existing_pdf_status_count(skipped_tasks: list[dict]) -> int:
    existing_statuses = {"downloaded", "already_present", "manual_import"}
    count = 0
    for task in skipped_tasks:
        status = clean(task.get("candidate_pdf_download_status", "")).lower()
        if status in existing_statuses:
            count += 1
    return count


def rebuild_routes_after_pdf_downloads(
    *,
    route_table: Path,
    metadata_table: Path,
    candidate_table: Path,
    prescreen_table: Path,
    domain_routing_table: Path | None,
    fulltext_dir: Path,
    pdf_dir: Path,
    route_summary_json: Path,
    route_counts_csv: Path,
    manual_route_overrides: Path | None,
) -> dict:
    domain_table = domain_routing_table if domain_routing_table is not None and domain_routing_table.exists() else None
    print(
        "ROUTE_REBUILD: rebuilding extraction routes after PDF availability update "
        f"domain_routing_table={domain_table if domain_table is not None else '<none>'}",
        flush=True,
    )
    summary = build_extraction_routes(
        metadata_table=metadata_table,
        candidate_table=candidate_table,
        prescreen_table=prescreen_table,
        domain_table=domain_table,
        manual_overrides_path=manual_route_overrides if manual_route_overrides and manual_route_overrides.exists() else None,
        fulltext_dir=fulltext_dir,
        paper_root=pdf_dir,
        output_table=route_table,
        summary_json=route_summary_json,
        counts_csv=route_counts_csv,
        include_non_retained=False,
    )
    print(
        "ROUTE_REBUILD: complete "
        f"route_rows={int(summary.get('route_rows', 0)):,} "
        f"routed_dois={int(summary.get('routed_dois', 0)):,} "
        f"by_access_tier={summary.get('by_access_tier', {})}",
        flush=True,
    )
    return summary


def download_routed_pdfs(
    *,
    route_table: Path = DEFAULT_ROUTE_TABLE,
    metadata_table: Path = DEFAULT_METADATA_TABLE,
    candidate_table: Path = DEFAULT_CANDIDATE_TABLE,
    pdf_dir: Path = DEFAULT_PDF_DIR,
    report_path: Path = DEFAULT_REPORT,
    doi_filter: set[str] | None = None,
    route_action: str = DEFAULT_ROUTE_ACTION,
    limit: int = 0,
    dry_run: bool = False,
    rps: float = 1.0,
    timeout_sec: int = 45,
    max_retries: int = 1,
    max_retry_after_sec: int = 60,
    skip_candidate_statuses: set[str] | None = None,
    only_failure_categories: set[str] | None = None,
    rate_limit_cooldown_sec: float = 0.0,
    host_interleaving: bool = True,
    include_weak_pdf_urls: bool = False,
    deprioritized_hosts: set[str] | None = None,
    excluded_hosts: set[str] | None = None,
    attempt_log_every: int = 1,
    candidate_log_every: int = 1,
    write_every: int = 25,
    progress_every: int = 25,
    alternate_pdf_sources: set[str] | None = None,
    alternate_pdf_min_title_score: float = 0.5,
    rebuild_routes_after: bool = False,
    prescreen_table: Path = DEFAULT_PRESCREEN_TABLE,
    domain_routing_table: Path | None = DEFAULT_DOMAIN_ROUTING_TABLE,
    fulltext_dir: Path = DEFAULT_FULLTEXT_DIR,
    route_summary_json: Path = DEFAULT_ROUTE_SUMMARY_JSON,
    route_counts_csv: Path = DEFAULT_ROUTE_COUNTS_CSV,
    manual_route_overrides: Path | None = DEFAULT_MANUAL_ROUTE_OVERRIDES,
) -> dict:
    routes_df = pd.read_parquet(route_table)
    metadata_df = pd.read_parquet(metadata_table) if metadata_table.exists() else pd.DataFrame()
    candidate_df = pd.read_parquet(candidate_table) if candidate_table.exists() else pd.DataFrame()
    candidate_df = ensure_candidate_columns(candidate_df)

    all_tasks = build_download_tasks(
        routes_df,
        metadata_df,
        doi_filter=doi_filter,
        route_action=route_action,
        limit=0,
    )
    tasks, skipped_tasks = filter_tasks_by_candidate_status(
        all_tasks,
        candidate_df,
        skip_candidate_statuses=skip_candidate_statuses or set(),
        only_failure_categories=only_failure_categories,
    )
    deprioritized_hosts = deprioritized_hosts or set()
    excluded_hosts = excluded_hosts or set()
    alternate_pdf_sources = {clean(source).lower() for source in (alternate_pdf_sources or set()) if clean(source)}
    if excluded_hosts:
        host_filtered_tasks: list[dict] = []
        for task in tasks:
            if task_download_candidates(
                task,
                include_weak_pdf_urls=include_weak_pdf_urls,
                deprioritized_hosts=deprioritized_hosts,
                excluded_hosts=excluded_hosts,
            ):
                host_filtered_tasks.append(task)
            else:
                skipped_tasks.append({**task, "skip_reason": "excluded_hosts_filter"})
        tasks = host_filtered_tasks
    if host_interleaving:
        tasks = interleave_tasks_by_host(tasks, deprioritized_hosts, excluded_hosts)
    deferred_by_limit = 0
    if limit > 0 and len(tasks) > limit:
        deferred_by_limit = len(tasks) - limit
        tasks = tasks[:limit]
    client = RateLimitedHttpClient(
        rps=max(0.01, rps),
        max_retries=max(0, max_retries),
        timeout_sec=max(1, timeout_sec),
        max_retry_after_sec=max(0, max_retry_after_sec),
        user_agent="kg-pipeline/routed-pdf-download",
    )

    records: list[dict] = []
    counts: Counter[str] = Counter()
    failure_category_counts: Counter[str] = Counter()
    retry_recommended_count = 0
    candidate_rows_changed = 0
    pdf_availability_results = 0
    cooldown_until_by_host: dict[str, float] = {}
    pdf_dir.mkdir(parents=True, exist_ok=True)

    if progress_every > 0 or attempt_log_every > 0:
        print(
            "QUEUE: routed PDF download "
            f"tasks={len(tasks):,} "
            f"skipped={len(skipped_tasks):,} "
            f"deferred={deferred_by_limit:,} "
            f"dry_run={dry_run} "
            f"host_interleaving={host_interleaving} "
            f"include_weak_pdf_urls={include_weak_pdf_urls} "
            f"deprioritized_hosts={','.join(sorted(deprioritized_hosts)) or '<none>'} "
            f"excluded_hosts={','.join(sorted(excluded_hosts)) or '<none>'} "
            f"alternate_pdf_sources={','.join(sorted(alternate_pdf_sources)) or '<none>'}",
            flush=True,
        )

    for position, task in enumerate(tasks, start=1):
        doi = task["doi"]
        target_path = pdf_dir / pdf_filename_for_doi(doi)
        candidates = task_download_candidates(
            task,
            include_weak_pdf_urls=include_weak_pdf_urls,
            deprioritized_hosts=deprioritized_hosts,
            excluded_hosts=excluded_hosts,
        )
        all_candidates = split_candidates(task.get("pdf_url_candidates", ""))
        candidate_event_count = 0
        alternate_source_events: list[dict] = []
        alternate_source_status = ""
        alternate_source_selected = ""
        alternate_source_attempts = ""
        alternate_source_candidate_count = 0

        def log_candidate_event(event: dict) -> None:
            nonlocal candidate_event_count
            if candidate_log_every <= 0:
                return
            candidate_event_count += 1
            if candidate_event_count % candidate_log_every != 0:
                return
            event_name = clean(event.get("event", "")).upper()
            status_text = clean(event.get("status", ""))
            error_text = clean(event.get("error", "")).replace("\n", " ")[:180]
            print(
                f"PDF_URL_{event_name}: routed PDF download "
                f"{position:,}/{len(tasks):,} "
                f"doi={doi} "
                f"round={event.get('round', '')} "
                f"host={clean(event.get('host', '')) or '<none>'} "
                f"status={status_text or '<pending>'} "
                f"size={event.get('size', '')} "
                f"error={error_text or '<blank>'}",
                flush=True,
            )

        if attempt_log_every > 0 and (
            position == 1 or position % attempt_log_every == 0 or position == len(tasks)
        ):
            candidate_hosts = hosts_from_candidates(join_candidates(candidates))
            print(
                "ATTEMPT: routed PDF download "
                f"{position:,}/{len(tasks):,} "
                f"doi={doi} "
                f"candidates={len(candidates):,} "
                f"hosts={','.join(candidate_hosts[:3]) or '<none>'} "
                f"previous_status={clean(task.get('candidate_pdf_download_status', '')) or '<blank>'} "
                f"previous_failure={clean(task.get('candidate_pdf_failure_category', '')) or '<blank>'}",
                flush=True,
            )
        if dry_run:
            status, error, size, selected_url, attempts = "dry_run", "", 0, "", join_candidates(candidates)
        elif not candidates and all_candidates:
            status = "no_probable_pdf_url"
            error = "weak_or_landing_page_urls_only"
            size = 0
            selected_url = ""
            attempts = ""
        elif not candidates:
            status, error, size, selected_url, attempts = "no_pdf_url", "no_pdf_url", 0, "", ""
        else:
            status, error, size, selected_url, attempts = download_pdf_candidates(
                client=client,
                pdf_urls=candidates,
                target_path=target_path,
                cooldown_until_by_host=cooldown_until_by_host if rate_limit_cooldown_sec > 0 else None,
                rate_limit_cooldown_sec=rate_limit_cooldown_sec,
                progress_callback=log_candidate_event if candidate_log_every > 0 else None,
                preserve_candidate_order=bool(deprioritized_hosts),
            )

        if (
            not dry_run
            and alternate_pdf_sources
            and status not in {"downloaded", "already_present", "invalid_pdf_existing"}
        ):
            discovery = collect_alternate_pdf_candidates(
                client=client,
                task=task,
                sources=alternate_pdf_sources,
            )
            alternate_source_events.extend(discovery.get("events", []))
            alternate_source_attempts = clean(discovery.get("candidate_urls", ""))
            alternate_source_candidate_count = len(discovery.get("candidates", []))
            if alternate_source_candidate_count:
                alternate_result = download_alternate_pdf_candidates(
                    client=client,
                    candidates=discovery["candidates"],
                    target_path=target_path,
                    study_title=clean(task.get("study_title", "")),
                    min_title_score=max(0.0, alternate_pdf_min_title_score),
                    progress_callback=log_candidate_event if candidate_log_every > 0 else None,
                )
                alternate_source_events.extend(alternate_result.get("events", []))
                alternate_source_status = clean(alternate_result.get("status", ""))
                alternate_source_selected = clean(alternate_result.get("selected_url", ""))
                alternate_source_attempts = clean(alternate_result.get("attempted_pdf_url_candidates", "")) or alternate_source_attempts
                if alternate_source_status in {"downloaded", "already_present"}:
                    status = alternate_source_status
                    error = ""
                    size = int(alternate_result.get("size", 0))
                    selected_url = alternate_source_selected
                    attempts = alternate_source_attempts
                elif status in {"no_pdf_url", "no_probable_pdf_url"}:
                    status = alternate_source_status or status
                    error = clean(alternate_result.get("error", "")) or error
                    size = int(alternate_result.get("size", 0))
                    selected_url = alternate_source_selected
                    attempts = alternate_source_attempts or attempts
                else:
                    alternate_error = clean(alternate_result.get("error", ""))
                    if alternate_error:
                        error = f"{error} || alternate_pdf_sources: {alternate_source_status}: {alternate_error}" if error else alternate_error
            elif status in {"no_pdf_url", "no_probable_pdf_url"}:
                error = "no_alternate_pdf_candidates"

        pdf_exists = target_path.exists() and target_path.is_file() and status in {"downloaded", "already_present"}
        result_pdf_url_candidates = task.get("pdf_url_candidates", "")
        if alternate_source_attempts:
            result_pdf_url_candidates = join_candidates(
                split_candidates(result_pdf_url_candidates) + split_candidates(alternate_source_attempts)
            )
        failure = classify_download_failure(status, error)
        result = {
            **task,
            "status": status,
            "error": error,
            "selected_url": selected_url,
            "pdf_url_candidates": result_pdf_url_candidates,
            "attempted_pdf_url_candidates": attempts,
            "primary_candidate_host": task_primary_host(task, deprioritized_hosts, excluded_hosts),
            "candidate_hosts": "|".join(hosts_from_candidates(attempts or task.get("pdf_url_candidates", ""))),
            "alternate_pdf_sources": "|".join(sorted(alternate_pdf_sources)),
            "alternate_pdf_status": alternate_source_status,
            "alternate_pdf_selected_url": alternate_source_selected,
            "alternate_pdf_candidate_count": alternate_source_candidate_count,
            "alternate_pdf_events": alternate_source_events,
            "pdf_local_path": str(target_path.resolve()) if pdf_exists else "",
            "pdf_size_bytes": int(target_path.stat().st_size) if pdf_exists else size,
            "pdf_sha256": sha256_file(target_path) if pdf_exists else "",
            **failure,
        }
        records.append(result)
        counts[status] += 1
        if status in {"downloaded", "already_present"}:
            pdf_availability_results += 1
        if result["failure_category"]:
            failure_category_counts[clean(result["failure_category"])] += 1
        if result["retry_recommended"]:
            retry_recommended_count += 1
        if attempt_log_every > 0 and (
            position == 1 or position % attempt_log_every == 0 or position == len(tasks)
        ):
            print(
                "RESULT: routed PDF download "
                f"{position:,}/{len(tasks):,} "
                f"doi={doi} "
                f"status={status} "
                f"failure={clean(result.get('failure_category', '')) or '<blank>'} "
                f"retry_recommended={bool(result.get('retry_recommended', False))} "
                f"selected_host={urlparse(selected_url).netloc.lower() if selected_url else '<none>'} "
                f"size={result.get('pdf_size_bytes', 0)}",
                flush=True,
            )
        update_rate_limit_cooldowns(
            result=result,
            cooldown_until_by_host=cooldown_until_by_host,
            cooldown_sec=rate_limit_cooldown_sec,
        )

        if not dry_run and apply_result_to_candidate_table(candidate_df, result):
            candidate_rows_changed += 1
        if not dry_run and write_every > 0 and position % write_every == 0:
            candidate_df.to_parquet(candidate_table, engine="pyarrow", index=False)

        if progress_every > 0 and (position % progress_every == 0 or position == len(tasks)):
            print(
                "PROGRESS: routed PDF download "
                f"{position:,}/{len(tasks):,} "
                f"downloaded={counts.get('downloaded', 0):,} "
                f"already_present={counts.get('already_present', 0):,} "
                f"failed={counts.get('download_failed', 0):,} "
                f"invalid={counts.get('invalid_pdf_content', 0) + counts.get('invalid_pdf_existing', 0):,} "
                f"retryable={retry_recommended_count:,}",
                flush=True,
            )

    if not dry_run:
        candidate_df.to_parquet(candidate_table, engine="pyarrow", index=False)

    skipped_existing = skipped_existing_pdf_status_count(skipped_tasks)
    route_rebuild_summary: dict | None = None
    if rebuild_routes_after and not dry_run and (pdf_availability_results > 0 or skipped_existing > 0):
        route_rebuild_summary = rebuild_routes_after_pdf_downloads(
            route_table=route_table,
            metadata_table=metadata_table,
            candidate_table=candidate_table,
            prescreen_table=prescreen_table,
            domain_routing_table=domain_routing_table,
            fulltext_dir=fulltext_dir,
            pdf_dir=pdf_dir,
            route_summary_json=route_summary_json,
            route_counts_csv=route_counts_csv,
            manual_route_overrides=manual_route_overrides,
        )

    report = {
        "generated_at_utc": now_utc(),
        "dry_run": dry_run,
        "route_table": str(route_table.resolve()),
        "metadata_table": str(metadata_table.resolve()),
        "candidate_table": str(candidate_table.resolve()),
        "pdf_dir": str(pdf_dir.resolve()),
        "route_action": route_action,
        "host_interleaving": host_interleaving,
        "include_weak_pdf_urls": include_weak_pdf_urls,
        "alternate_pdf_sources": sorted(alternate_pdf_sources),
        "alternate_pdf_min_title_score": alternate_pdf_min_title_score,
        "deprioritized_hosts": sorted(deprioritized_hosts),
        "excluded_hosts": sorted(excluded_hosts),
        "attempt_log_every": attempt_log_every,
        "candidate_log_every": candidate_log_every,
        "progress_every": progress_every,
        "write_every": write_every,
        "rebuild_routes_after": rebuild_routes_after,
        "limit": limit,
        "counts": {
            "tasks_before_candidate_filter": len(all_tasks),
            "tasks": len(tasks),
            "skipped_by_candidate_status": len(skipped_tasks),
            "skipped_existing_pdf_status": skipped_existing,
            "deferred_by_limit": deferred_by_limit,
            "candidate_rows_changed": candidate_rows_changed,
            "pdf_availability_results": pdf_availability_results,
            "status": dict(counts),
            "failure_category": dict(failure_category_counts),
            "retry_recommended": retry_recommended_count,
        },
        "route_rebuild": {
            "performed": route_rebuild_summary is not None,
            "summary": route_rebuild_summary or {},
        },
        "records": records,
        "skipped_records": skipped_tasks,
    }
    write_json(report_path, report)
    return report


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Download PDFs for routed extraction candidates.")
    parser.add_argument("--route-table", default=str(DEFAULT_ROUTE_TABLE))
    parser.add_argument("--metadata-table", default=str(DEFAULT_METADATA_TABLE))
    parser.add_argument("--candidate-table", default=str(DEFAULT_CANDIDATE_TABLE))
    parser.add_argument("--pdf-dir", default=str(DEFAULT_PDF_DIR))
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    parser.add_argument("--doi-file", default="")
    parser.add_argument("--route-action", default=DEFAULT_ROUTE_ACTION)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--rps", type=float, default=1.0)
    parser.add_argument("--timeout-sec", type=int, default=45)
    parser.add_argument("--max-retries", type=int, default=1)
    parser.add_argument("--max-retry-after-sec", type=int, default=60)
    parser.add_argument(
        "--skip-candidate-statuses",
        default="downloaded,already_present,manual_import",
        help="Comma-separated candidate-table pdf_download_status values to skip.",
    )
    parser.add_argument(
        "--only-failure-categories",
        default="",
        help="Optional comma-separated candidate failure categories to retry, such as rate_limited,provider_error,timeout.",
    )
    parser.add_argument(
        "--rate-limit-cooldown-sec",
        type=float,
        default=0.0,
        help="Cooldown for hosts that return rate-limit failures before trying that host again.",
    )
    parser.add_argument(
        "--preserve-task-order",
        action="store_true",
        help="Disable host-aware interleaving and process tasks in table order.",
    )
    parser.add_argument(
        "--include-weak-pdf-urls",
        action="store_true",
        help="Also attempt weak or landing-page-like URLs. By default only probable PDF/file URLs are downloaded.",
    )
    parser.add_argument(
        "--deprioritize-hosts",
        default="",
        help="Comma-separated candidate URL hosts to try only after other hosts, for recovery runs.",
    )
    parser.add_argument(
        "--exclude-hosts",
        default="",
        help="Comma-separated candidate URL hosts to skip for a recovery run without removing them from metadata.",
    )
    parser.add_argument(
        "--alternate-pdf-sources",
        default="",
        help=(
            "Optional comma-separated alternate source strategies to try after direct PDF URLs fail. "
            "Supported values: pmc,openalex,semantic_scholar."
        ),
    )
    parser.add_argument(
        "--alternate-pdf-min-title-score",
        type=float,
        default=0.5,
        help="Minimum token title-match score for alternate-source PDFs when extractable text is available.",
    )
    parser.add_argument("--write-every", type=int, default=25)
    parser.add_argument("--progress-every", type=int, default=25)
    parser.add_argument(
        "--attempt-log-every",
        type=int,
        default=1,
        help="Log before every N network attempts; use 0 to disable per-attempt logging.",
    )
    parser.add_argument(
        "--candidate-log-every",
        type=int,
        default=1,
        help="Log every N candidate-URL attempt/result events; use 0 to disable candidate URL logging.",
    )
    parser.add_argument(
        "--no-rebuild-routes-after",
        action="store_true",
        help="Do not rebuild the extraction route table after a real run updates PDF availability.",
    )
    parser.add_argument("--prescreen-table", default=str(DEFAULT_PRESCREEN_TABLE))
    parser.add_argument("--domain-routing-table", default=str(DEFAULT_DOMAIN_ROUTING_TABLE))
    parser.add_argument("--fulltext-dir", default=str(DEFAULT_FULLTEXT_DIR))
    parser.add_argument("--route-summary-json", default=str(DEFAULT_ROUTE_SUMMARY_JSON))
    parser.add_argument("--route-counts-csv", default=str(DEFAULT_ROUTE_COUNTS_CSV))
    parser.add_argument("--manual-route-overrides", default=str(DEFAULT_MANUAL_ROUTE_OVERRIDES))
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    doi_filter = read_doi_file(Path(args.doi_file).resolve()) if clean(args.doi_file) else None
    report = download_routed_pdfs(
        route_table=Path(args.route_table).resolve(),
        metadata_table=Path(args.metadata_table).resolve(),
        candidate_table=Path(args.candidate_table).resolve(),
        pdf_dir=Path(args.pdf_dir).resolve(),
        report_path=Path(args.report).resolve(),
        doi_filter=doi_filter,
        route_action=args.route_action,
        limit=max(0, args.limit),
        dry_run=bool(args.dry_run),
        rps=args.rps,
        timeout_sec=args.timeout_sec,
        max_retries=args.max_retries,
        max_retry_after_sec=args.max_retry_after_sec,
        skip_candidate_statuses=parse_statuses(args.skip_candidate_statuses),
        only_failure_categories=parse_csv_values(args.only_failure_categories) or None,
        rate_limit_cooldown_sec=max(0.0, args.rate_limit_cooldown_sec),
        host_interleaving=not bool(args.preserve_task_order),
        include_weak_pdf_urls=bool(args.include_weak_pdf_urls),
        deprioritized_hosts=parse_csv_values(args.deprioritize_hosts),
        excluded_hosts=parse_csv_values(args.exclude_hosts),
        alternate_pdf_sources=parse_csv_values(args.alternate_pdf_sources),
        alternate_pdf_min_title_score=args.alternate_pdf_min_title_score,
        write_every=args.write_every,
        progress_every=args.progress_every,
        attempt_log_every=args.attempt_log_every,
        candidate_log_every=args.candidate_log_every,
        rebuild_routes_after=not bool(args.no_rebuild_routes_after),
        prescreen_table=Path(args.prescreen_table).resolve(),
        domain_routing_table=Path(args.domain_routing_table).resolve() if clean(args.domain_routing_table) else None,
        fulltext_dir=Path(args.fulltext_dir).resolve(),
        route_summary_json=Path(args.route_summary_json).resolve(),
        route_counts_csv=Path(args.route_counts_csv).resolve(),
        manual_route_overrides=Path(args.manual_route_overrides).resolve() if clean(args.manual_route_overrides) else None,
    )
    status_counts = report["counts"]["status"]
    print(f"Tasks: {report['counts']['tasks']:,}", flush=True)
    print(f"Skipped by candidate status: {report['counts']['skipped_by_candidate_status']:,}", flush=True)
    print(f"Deferred by limit: {report['counts']['deferred_by_limit']:,}", flush=True)
    print(f"Downloaded: {status_counts.get('downloaded', 0):,}", flush=True)
    print(f"Already present: {status_counts.get('already_present', 0):,}", flush=True)
    print(f"Failed: {status_counts.get('download_failed', 0):,}", flush=True)
    print(f"Invalid content: {status_counts.get('invalid_pdf_content', 0):,}", flush=True)
    print(f"No PDF URL: {status_counts.get('no_pdf_url', 0):,}", flush=True)
    print(f"No probable PDF URL: {status_counts.get('no_probable_pdf_url', 0):,}", flush=True)
    print(f"Alternate PDF sources: {','.join(report['alternate_pdf_sources']) or '<none>'}", flush=True)
    print(f"Retry recommended: {report['counts']['retry_recommended']:,}", flush=True)
    print(f"Failure categories: {report['counts']['failure_category']}", flush=True)
    print(f"Candidate rows changed: {report['counts']['candidate_rows_changed']:,}", flush=True)
    print(f"PDF availability results: {report['counts']['pdf_availability_results']:,}", flush=True)
    print(f"Skipped existing PDF status: {report['counts']['skipped_existing_pdf_status']:,}", flush=True)
    print(f"Route rebuild performed: {report['route_rebuild']['performed']}", flush=True)
    print(f"Dry run: {report['dry_run']}", flush=True)
    print(f"Report: {Path(args.report).resolve()}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
