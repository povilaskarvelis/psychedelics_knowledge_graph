#!/usr/bin/env python3
"""Recover PDFs from open landing pages that need lightweight URL resolution."""

from __future__ import annotations

import argparse
from collections import Counter
import datetime as dt
import html
import json
from pathlib import Path
import re
import sys
import time
from typing import Iterable
from urllib.parse import urljoin, urlparse

import pandas as pd
import requests

try:
    from pipeline.fulltext.download_routed_pdfs import (
        apply_result_to_candidate_table,
        classify_download_failure,
        rebuild_routes_after_pdf_downloads,
        sha256_file,
    )
    from pipeline.fulltext.pdf_alternate_sources import title_validation_result
    from pipeline.ingest.metadata_utils import (
        file_is_valid_pdf,
        is_probable_pdf_url,
        join_candidates,
        looks_like_pdf_bytes,
        normalize_doi,
        pdf_filename_for_doi,
        rank_pdf_candidates,
        split_candidates,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from pipeline.fulltext.download_routed_pdfs import (
        apply_result_to_candidate_table,
        classify_download_failure,
        rebuild_routes_after_pdf_downloads,
        sha256_file,
    )
    from pipeline.fulltext.pdf_alternate_sources import title_validation_result
    from pipeline.ingest.metadata_utils import (
        file_is_valid_pdf,
        is_probable_pdf_url,
        join_candidates,
        looks_like_pdf_bytes,
        normalize_doi,
        pdf_filename_for_doi,
        rank_pdf_candidates,
        split_candidates,
    )


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANUAL_CSV = ROOT / "data" / "processed" / "corpus" / "audits" / "manual_pdf_download_dois.csv"
DEFAULT_CANDIDATE_TABLE = ROOT / "data" / "processed" / "corpus" / "candidate_papers.parquet"
DEFAULT_PDF_DIR = ROOT / "data" / "raw" / "papers" / "pdfs"
DEFAULT_REPORT = ROOT / "data" / "processed" / "corpus" / "audits" / "pdf_landing_page_recovery_report.json"
DEFAULT_ROUTE_TABLE = ROOT / "data" / "processed" / "corpus" / "paper_extraction_routes.parquet"
DEFAULT_METADATA_TABLE = ROOT / "data" / "processed" / "corpus" / "paper_metadata_enrichment.parquet"
DEFAULT_PRESCREEN_TABLE = ROOT / "data" / "processed" / "corpus" / "paper_prescreen_decisions.parquet"
DEFAULT_DOMAIN_ROUTING_TABLE = ROOT / "data" / "processed" / "corpus" / "paper_domain_routing_gemini.parquet"
DEFAULT_FULLTEXT_DIR = ROOT / "data" / "processed" / "fulltext"
DEFAULT_ROUTE_SUMMARY_JSON = ROOT / "data" / "processed" / "corpus" / "paper_extraction_routes_summary.json"
DEFAULT_ROUTE_COUNTS_CSV = ROOT / "data" / "processed" / "corpus" / "paper_extraction_routes_counts.csv"
DEFAULT_MANUAL_ROUTE_OVERRIDES = ROOT / "pipeline" / "extract" / "manual_extraction_route_overrides.json"
DEFAULT_RECOVERY_CATEGORIES = "non_pdf_response,provider_error,timeout"
BROAD_RESCUE_CATEGORIES = "forbidden,non_pdf_response,provider_error,timeout,other_download_failure,not_found"
AKJOURNALS_RESCUE_HOSTS = {"akjournals.com", "www.akjournals.com", "www.akjournals.com:443"}
RESCUE_PRESETS = {"", "none", "akjournals"}
FIGSHARE_REDIRECT_HOSTS = {
    "sro.sussex.ac.uk",
}

LANDING_PAGE_RECOVERY_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept": "application/pdf,text/html;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

CHALLENGE_MARKERS = (
    "recaptcha",
    "captcha",
    "altcha",
    "awswaf",
    "aws waf",
    "g-recaptcha",
    "checking your browser",
    "verify you are human",
    "gauging your humanity",
    "access denied",
    "sign in to access",
    "login required",
)

NO_ANCHOR_PARSE_HOSTS = {
    "link.springer.com",
    "www.nature.com",
    "onlinelibrary.wiley.com",
    "academic.oup.com",
    "journals.sagepub.com",
    "www.tandfonline.com",
}

OSF_GUID_PATTERNS = (
    re.compile(r"10\.3123[49]/osf\.io/([a-z0-9]+(?:_v\d+)?)", flags=re.IGNORECASE),
    re.compile(r"/preprints/[^/]+/([a-z0-9]+(?:_v\d+)?)", flags=re.IGNORECASE),
    re.compile(r"osf\.io/(?!preprints/|download/)([a-z0-9]+(?:_v\d+)?)", flags=re.IGNORECASE),
)
FIGSHARE_ARTICLE_ID_RE = re.compile(r"/articles/[^/]+/[^/]+/(\d+)(?:/|$)", flags=re.IGNORECASE)


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def clean(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    return str(value).strip()


def doi_key(value: object) -> str:
    return normalize_doi(clean(value)).lower()


def parse_csv_values(raw: str) -> set[str]:
    return {part.strip().lower() for part in clean(raw).split(",") if part.strip()}


def rescue_preset_hosts(preset: str) -> set[str]:
    preset = clean(preset).lower()
    if preset in {"", "none"}:
        return set()
    if preset == "akjournals":
        return set(AKJOURNALS_RESCUE_HOSTS)
    raise ValueError(f"Unknown rescue preset: {preset}")


def rescue_preset_categories(preset: str) -> set[str]:
    preset = clean(preset).lower()
    if preset in {"", "none"}:
        return set()
    if preset == "akjournals":
        return parse_csv_values(BROAD_RESCUE_CATEGORIES)
    raise ValueError(f"Unknown rescue preset: {preset}")


def host_for(url: str) -> str:
    return urlparse(clean(url)).netloc.lower()


def is_challenge_page(text: str) -> bool:
    lowered = text[:8000].lower()
    return any(marker in lowered for marker in CHALLENGE_MARKERS)


def extract_href_values(page_url: str, text: str) -> list[str]:
    links: list[str] = []
    for match in re.finditer(r"""href\s*=\s*["']([^"']+)["']""", text, flags=re.IGNORECASE):
        href = html.unescape(match.group(1)).strip()
        if not href or href.startswith("#") or href.lower().startswith(("javascript:", "mailto:")):
            continue
        links.append(urljoin(page_url, href))
    return links


def same_host_pdf_links(page_url: str, text: str) -> list[str]:
    page_host = host_for(page_url)
    if page_host in NO_ANCHOR_PARSE_HOSTS:
        return []
    out: list[str] = []
    for link in extract_href_values(page_url, text):
        link_host = host_for(link)
        lowered = link.lower()
        if link_host != page_host:
            continue
        if ".pdf" not in lowered and not is_probable_pdf_url(link):
            continue
        if link not in out:
            out.append(link)
    return rank_pdf_candidates(out)


def osf_guid_candidates(value: object) -> list[str]:
    text = clean(value).lower()
    out: list[str] = []
    for pattern in OSF_GUID_PATTERNS:
        for match in pattern.finditer(text):
            guid = match.group(1).strip("/")
            if guid and guid not in out:
                out.append(guid)
            base = re.sub(r"_v\d+$", "", guid)
            if base and base not in out:
                out.append(base)
    return out


def osf_download_urls_for_guid(session: requests.Session, guid: str, timeout_sec: int) -> tuple[list[str], list[dict]]:
    events: list[dict] = []
    urls: list[str] = []
    for candidate_guid in osf_guid_candidates(guid) or [guid]:
        api_url = f"https://api.osf.io/v2/preprints/{candidate_guid}/"
        try:
            response = session.get(
                api_url,
                timeout=timeout_sec,
                allow_redirects=True,
                headers={"Accept": "application/vnd.api+json,application/json;q=0.9,*/*;q=0.1"},
            )
        except requests.RequestException as err:
            events.append(
                {"event": "osf_preprint_error", "url": api_url, "error": f"{type(err).__name__}: {err}"}
            )
            continue
        events.append({"event": "osf_preprint_response", "input_url": api_url, **response_summary(response)})
        if response.status_code != 200:
            continue
        try:
            data = response.json().get("data", {})
        except ValueError:
            continue
        relationships = data.get("relationships", {}) if isinstance(data, dict) else {}
        primary_file = relationships.get("primary_file", {}) if isinstance(relationships, dict) else {}
        related = primary_file.get("links", {}).get("related", {}).get("href", "") if isinstance(primary_file, dict) else ""
        if not related:
            continue
        try:
            file_response = session.get(
                related,
                timeout=timeout_sec,
                allow_redirects=True,
                headers={"Accept": "application/vnd.api+json,application/json;q=0.9,*/*;q=0.1"},
            )
        except requests.RequestException as err:
            events.append(
                {"event": "osf_primary_file_error", "url": related, "error": f"{type(err).__name__}: {err}"}
            )
            continue
        events.append({"event": "osf_primary_file_response", "input_url": related, **response_summary(file_response)})
        if file_response.status_code != 200:
            continue
        try:
            file_data = file_response.json().get("data", {})
        except ValueError:
            continue
        attributes = file_data.get("attributes", {}) if isinstance(file_data, dict) else {}
        links = file_data.get("links", {}) if isinstance(file_data, dict) else {}
        name = clean(attributes.get("name", ""))
        download_url = clean(links.get("download", ""))
        events.append({"event": "osf_primary_file", "guid": candidate_guid, "name": name, "download_url": download_url})
        if download_url and download_url not in urls:
            urls.append(download_url)
    return urls, events


def figshare_article_ids(value: object) -> list[str]:
    text = clean(value)
    out: list[str] = []
    for match in FIGSHARE_ARTICLE_ID_RE.finditer(text):
        article_id = match.group(1)
        if article_id and article_id not in out:
            out.append(article_id)
    return out


def figshare_download_urls_for_article(
    session: requests.Session,
    article_id: str,
    timeout_sec: int,
) -> tuple[list[str], list[dict]]:
    api_url = f"https://api.figshare.com/v2/articles/{article_id}"
    events: list[dict] = []
    try:
        response = session.get(
            api_url,
            timeout=timeout_sec,
            allow_redirects=True,
            headers={"Accept": "application/json,*/*;q=0.1"},
        )
    except requests.RequestException as err:
        return [], [{"event": "figshare_article_error", "url": api_url, "error": f"{type(err).__name__}: {err}"}]
    events.append({"event": "figshare_article_response", "input_url": api_url, **response_summary(response)})
    if response.status_code != 200:
        return [], events
    try:
        payload = response.json()
    except ValueError:
        return [], events
    urls: list[str] = []
    for file_payload in payload.get("files", []) if isinstance(payload, dict) else []:
        if not isinstance(file_payload, dict):
            continue
        name = clean(file_payload.get("name", ""))
        download_url = clean(file_payload.get("download_url", ""))
        events.append(
            {
                "event": "figshare_file",
                "article_id": article_id,
                "name": name,
                "download_url": download_url,
                "mimetype": clean(file_payload.get("mimetype", "")),
            }
        )
        mimetype = clean(file_payload.get("mimetype", "")).lower()
        if download_url and (
            name.lower().endswith(".pdf")
            or ".pdf" in download_url.lower()
            or mimetype == "application/pdf"
        ):
            urls.append(download_url)
    return urls, events


def expanded_candidates(row: dict) -> list[str]:
    candidates: list[str] = []
    for field in ("best_pdf_url", "pdf_url_candidates", "open_access_url", "doi"):
        for candidate in split_candidates(row.get(field, "")):
            if candidate not in candidates:
                candidates.append(candidate)
    return rank_pdf_candidates(candidates)


def standard_recovery_values(row: dict) -> list[str]:
    values: list[str] = []
    for field in ("doi", "best_pdf_url", "pdf_url_candidates", "open_access_url"):
        value = clean(row.get(field, ""))
        if value:
            values.append(value)
    return values


def has_standard_recovery_signal(row: dict) -> bool:
    """Keep the default recovery stage focused on repository APIs we understand."""

    for value in standard_recovery_values(row):
        if osf_guid_candidates(value) or figshare_article_ids(value):
            return True
        if host_for(value) in FIGSHARE_REDIRECT_HOSTS:
            return True
    return False


def response_summary(response: requests.Response) -> dict[str, object]:
    return {
        "status_code": int(response.status_code),
        "url": response.url,
        "content_type": response.headers.get("content-type", ""),
        "size_bytes": len(response.content),
    }


def try_candidate(
    *,
    session: requests.Session,
    url: str,
    timeout_sec: int,
    allow_landing_resolution: bool,
) -> tuple[str, bytes, list[dict]]:
    events: list[dict] = []
    try:
        response = session.get(url, timeout=timeout_sec, allow_redirects=True)
    except requests.RequestException as err:
        events.append({"event": "request_error", "url": url, "error": f"{type(err).__name__}: {err}"})
        return "", b"", events
    events.append({"event": "candidate_response", "input_url": url, **response_summary(response)})

    if looks_like_pdf_bytes(response.content):
        return response.url, response.content, events

    article_ids = figshare_article_ids(response.url)
    for article_id in article_ids:
        download_urls, figshare_events = figshare_download_urls_for_article(session, article_id, timeout_sec)
        events.extend(figshare_events)
        for download_url in download_urls:
            try:
                download_response = session.get(download_url, timeout=timeout_sec, allow_redirects=True)
            except requests.RequestException as err:
                events.append(
                    {
                        "event": "figshare_download_error",
                        "url": download_url,
                        "error": f"{type(err).__name__}: {err}",
                    }
                )
                continue
            events.append(
                {
                    "event": "figshare_download_response",
                    "input_url": download_url,
                    **response_summary(download_response),
                }
            )
            if looks_like_pdf_bytes(download_response.content):
                return download_response.url, download_response.content, events

    text = response.text if response.text else ""
    if is_challenge_page(text):
        events.append({"event": "challenge_or_access_control", "url": response.url})
        return "", b"", events

    if not allow_landing_resolution:
        events.append({"event": "not_pdf", "url": response.url})
        return "", b"", events

    for linked_url in same_host_pdf_links(response.url, text):
        try:
            linked_response = session.get(linked_url, timeout=timeout_sec, allow_redirects=True)
        except requests.RequestException as err:
            events.append(
                {"event": "linked_request_error", "url": linked_url, "error": f"{type(err).__name__}: {err}"}
            )
            continue
        events.append({"event": "linked_response", "input_url": linked_url, **response_summary(linked_response)})
        if looks_like_pdf_bytes(linked_response.content):
            return linked_response.url, linked_response.content, events
        if is_challenge_page(linked_response.text or ""):
            events.append({"event": "linked_challenge_or_access_control", "url": linked_response.url})
    return "", b"", events


def try_osf_candidates(
    *,
    session: requests.Session,
    row: dict,
    timeout_sec: int,
) -> tuple[str, bytes, list[dict]]:
    values = [
        row.get("doi", ""),
        row.get("best_pdf_url", ""),
        row.get("pdf_url_candidates", ""),
        row.get("open_access_url", ""),
    ]
    guid_candidates: list[str] = []
    for value in values:
        for guid in osf_guid_candidates(value):
            if guid not in guid_candidates:
                guid_candidates.append(guid)
    events: list[dict] = []
    download_urls: list[str] = []
    for guid in guid_candidates:
        urls, guid_events = osf_download_urls_for_guid(session, guid, timeout_sec)
        events.extend(guid_events)
        for url in urls:
            if url not in download_urls:
                download_urls.append(url)
    for url in download_urls:
        selected_url, body, candidate_events = try_candidate(
            session=session,
            url=url,
            timeout_sec=timeout_sec,
            allow_landing_resolution=False,
        )
        events.extend(candidate_events)
        if selected_url and body:
            return selected_url, body, events
    return "", b"", events


def try_figshare_candidates(
    *,
    session: requests.Session,
    row: dict,
    timeout_sec: int,
) -> tuple[str, bytes, list[dict]]:
    values = [
        row.get("best_pdf_url", ""),
        row.get("pdf_url_candidates", ""),
        row.get("open_access_url", ""),
    ]
    article_ids: list[str] = []
    for value in values:
        for article_id in figshare_article_ids(value):
            if article_id not in article_ids:
                article_ids.append(article_id)
    events: list[dict] = []
    download_urls: list[str] = []
    for article_id in article_ids:
        urls, article_events = figshare_download_urls_for_article(session, article_id, timeout_sec)
        events.extend(article_events)
        for url in urls:
            if url not in download_urls:
                download_urls.append(url)
    for url in download_urls:
        selected_url, body, candidate_events = try_candidate(
            session=session,
            url=url,
            timeout_sec=timeout_sec,
            allow_landing_resolution=False,
        )
        events.extend(candidate_events)
        if selected_url and body:
            return selected_url, body, events
    return "", b"", events


def selected_rows(
    manual_df: pd.DataFrame,
    *,
    doi_filter: set[str] | None,
    hosts: set[str],
    categories: set[str],
    standard_recovery_only: bool = False,
) -> list[dict]:
    rows: list[dict] = []
    for row in manual_df.to_dict("records"):
        doi = doi_key(row.get("doi", ""))
        if not doi:
            continue
        if doi_filter and doi not in doi_filter:
            continue
        category = clean(row.get("pdf_download_failure_category", "")).lower()
        if categories and category not in categories:
            continue
        if standard_recovery_only and not has_standard_recovery_signal(row):
            continue
        candidates = expanded_candidates(row)
        if hosts:
            candidates = [candidate for candidate in candidates if host_for(candidate) in hosts]
            if not candidates:
                continue
        rows.append({**row, "doi": doi, "candidate_urls": candidates})
    return rows


def read_doi_file(path: Path) -> set[str]:
    out: set[str] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        out.add(doi_key(line.split(",", 1)[0]))
    return {doi for doi in out if doi}


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def recover_pdf_landing_pages(
    *,
    manual_csv: Path = DEFAULT_MANUAL_CSV,
    candidate_table: Path = DEFAULT_CANDIDATE_TABLE,
    pdf_dir: Path = DEFAULT_PDF_DIR,
    report_path: Path = DEFAULT_REPORT,
    doi_filter: set[str] | None = None,
    hosts: set[str] | None = None,
    categories: set[str] | None = None,
    rescue_preset: str = "",
    standard_recovery_only: bool = False,
    limit: int = 0,
    timeout_sec: int = 30,
    rps: float = 0.5,
    min_title_score: float = 0.86,
    apply: bool = False,
    allow_landing_resolution: bool = True,
    rebuild_routes_after: bool = False,
    route_table: Path = DEFAULT_ROUTE_TABLE,
    metadata_table: Path = DEFAULT_METADATA_TABLE,
    prescreen_table: Path = DEFAULT_PRESCREEN_TABLE,
    domain_routing_table: Path | None = DEFAULT_DOMAIN_ROUTING_TABLE,
    fulltext_dir: Path = DEFAULT_FULLTEXT_DIR,
    route_summary_json: Path = DEFAULT_ROUTE_SUMMARY_JSON,
    route_counts_csv: Path = DEFAULT_ROUTE_COUNTS_CSV,
    manual_route_overrides: Path | None = DEFAULT_MANUAL_ROUTE_OVERRIDES,
) -> dict:
    rescue_preset = clean(rescue_preset).lower()
    if rescue_preset not in RESCUE_PRESETS:
        raise ValueError(f"Unknown rescue preset: {rescue_preset}")
    preset_hosts = rescue_preset_hosts(rescue_preset)
    selected_hosts = set(hosts or set()) or preset_hosts
    selected_categories = set(categories or set()) or rescue_preset_categories(rescue_preset)

    manual_df = pd.read_csv(manual_csv).fillna("")
    candidate_df = pd.read_parquet(candidate_table) if candidate_table.exists() else pd.DataFrame()
    rows = selected_rows(
        manual_df,
        doi_filter=doi_filter,
        hosts=selected_hosts,
        categories=selected_categories,
        standard_recovery_only=standard_recovery_only,
    )
    if limit > 0:
        rows = rows[:limit]

    session = requests.Session()
    session.headers.update(LANDING_PAGE_RECOVERY_HEADERS)
    min_interval = 1.0 / max(0.01, rps)
    last_request_at = 0.0
    records: list[dict] = []
    counts: Counter[str] = Counter()
    rows_changed = 0
    pdf_dir.mkdir(parents=True, exist_ok=True)

    print(
        "QUEUE: PDF landing-page recovery "
        f"tasks={len(rows):,} dry_run={not apply} "
        f"hosts={','.join(sorted(selected_hosts)) or '<any>'} "
        f"categories={','.join(sorted(selected_categories)) or '<any>'} "
        f"rescue_preset={rescue_preset or 'none'} "
        f"standard_recovery_only={standard_recovery_only}",
        flush=True,
    )

    for index, row in enumerate(rows, start=1):
        doi = doi_key(row.get("doi", ""))
        target_path = pdf_dir / pdf_filename_for_doi(doi)
        candidates = list(row.get("candidate_urls", []))
        status = "download_failed"
        error = ""
        selected_url = ""
        recovered_size = 0
        events: list[dict] = []
        identity_errors: list[str] = []

        def recovered_body_matches(body: bytes, source_url: str) -> bool:
            accepted, score, basis = title_validation_result(
                clean(row.get("study_title", "")),
                body,
                max(0.0, min_title_score),
                study_doi=doi,
            )
            events.append(
                {
                    "event": "title_validation",
                    "url": source_url,
                    "score": round(score, 4),
                    "basis": basis,
                    "accepted": accepted,
                }
            )
            if not accepted:
                identity_errors.append(f"source_identity_mismatch:{basis}:{score:.3f}")
            return accepted

        if target_path.exists() and file_is_valid_pdf(target_path):
            if recovered_body_matches(target_path.read_bytes(), str(target_path)):
                status = "already_present"
                selected_url = ""
            else:
                status = "invalid_pdf_existing"
                error = identity_errors[-1]
        else:
            selected_url, body, osf_events = try_osf_candidates(
                session=session,
                row=row,
                timeout_sec=timeout_sec,
            )
            events.extend(osf_events)
            if selected_url and body and recovered_body_matches(body, selected_url):
                recovered_size = len(body)
                if apply:
                    tmp_path = target_path.with_suffix(".tmp")
                    tmp_path.write_bytes(body)
                    tmp_path.replace(target_path)
                    status = "downloaded"
                else:
                    status = "would_download"
            if status not in {"downloaded", "would_download"}:
                selected_url, body, figshare_events = try_figshare_candidates(
                    session=session,
                    row=row,
                    timeout_sec=timeout_sec,
                )
                events.extend(figshare_events)
                if selected_url and body and recovered_body_matches(body, selected_url):
                    recovered_size = len(body)
                    if apply:
                        tmp_path = target_path.with_suffix(".tmp")
                        tmp_path.write_bytes(body)
                        tmp_path.replace(target_path)
                        status = "downloaded"
                    else:
                        status = "would_download"
            for candidate in candidates:
                if status in {"downloaded", "would_download"}:
                    break
                elapsed = time.monotonic() - last_request_at
                if elapsed < min_interval:
                    time.sleep(min_interval - elapsed)
                selected_url, body, candidate_events = try_candidate(
                    session=session,
                    url=candidate,
                    timeout_sec=timeout_sec,
                    allow_landing_resolution=allow_landing_resolution,
                )
                last_request_at = time.monotonic()
                events.extend(candidate_events)
                if selected_url and body and recovered_body_matches(body, selected_url):
                    recovered_size = len(body)
                    if apply:
                        tmp_path = target_path.with_suffix(".tmp")
                        tmp_path.write_bytes(body)
                        tmp_path.replace(target_path)
                        status = "downloaded"
                    else:
                        status = "would_download"
                    break
            if status == "download_failed":
                if identity_errors:
                    error = identity_errors[-1]
                elif any(event.get("event", "").endswith("challenge_or_access_control") for event in events):
                    error = "challenge_or_access_control"
                elif events:
                    error = "no_valid_pdf_recovered"
                else:
                    error = "no_candidate_url"

        pdf_exists = target_path.exists() and file_is_valid_pdf(target_path)
        if status == "would_download":
            pdf_path = ""
            pdf_size = recovered_size
            pdf_sha = ""
        else:
            pdf_path = str(target_path.resolve()) if pdf_exists else ""
            pdf_size = int(target_path.stat().st_size) if pdf_exists else 0
            pdf_sha = sha256_file(target_path) if pdf_exists else ""
        failure_status = "downloaded" if status == "would_download" else status
        failure = classify_download_failure(failure_status, error)
        result = {
            "doi": doi,
            "study_title": clean(row.get("study_title", "")),
            "status": status,
            "error": error,
            "selected_url": selected_url,
            "pdf_local_path": pdf_path,
            "pdf_size_bytes": pdf_size,
            "pdf_sha256": pdf_sha,
            "best_pdf_url": selected_url or clean(row.get("best_pdf_url", "")),
            "pdf_url_candidates": join_candidates(candidates),
            "probable_pdf_url_candidates": join_candidates([url for url in candidates if is_probable_pdf_url(url)]),
            "other_url_candidates": join_candidates([url for url in candidates if not is_probable_pdf_url(url)]),
            "pdf_url_quality": "probable_pdf" if selected_url else clean(row.get("pdf_url_quality", "")),
            "events": events,
            **failure,
        }
        records.append(result)
        counts[status] += 1
        print(
            "RESULT: PDF landing-page recovery "
            f"{index:,}/{len(rows):,} doi={doi} status={status} "
            f"selected_host={host_for(selected_url) if selected_url else '<none>'} "
            f"events={len(events):,}",
            flush=True,
        )
        if apply and status in {"downloaded", "already_present"}:
            if apply_result_to_candidate_table(candidate_df, result):
                rows_changed += 1

    if apply and not candidate_df.empty:
        candidate_df.to_parquet(candidate_table, engine="pyarrow", index=False)

    route_rebuild_summary: dict | None = None
    if apply and rebuild_routes_after and any(record["status"] in {"downloaded", "already_present"} for record in records):
        domain_table = domain_routing_table if domain_routing_table is not None and domain_routing_table.exists() else None
        route_rebuild_summary = rebuild_routes_after_pdf_downloads(
            route_table=route_table,
            metadata_table=metadata_table,
            prescreen_table=prescreen_table,
            domain_routing_table=domain_table,
            fulltext_dir=fulltext_dir,
            pdf_dir=pdf_dir,
            route_summary_json=route_summary_json,
            route_counts_csv=route_counts_csv,
            manual_route_overrides=manual_route_overrides,
        )

    report = {
        "generated_at_utc": now_utc(),
        "dry_run": not apply,
        "manual_csv": str(manual_csv.resolve()),
        "candidate_table": str(candidate_table.resolve()),
        "pdf_dir": str(pdf_dir.resolve()),
        "hosts": sorted(hosts or []),
        "categories": sorted(categories or []),
        "standard_recovery_only": standard_recovery_only,
        "limit": limit,
        "allow_landing_resolution": allow_landing_resolution,
        "min_title_score": min_title_score,
        "counts": {
            "tasks": len(rows),
            "status": dict(counts),
            "candidate_rows_changed": rows_changed,
        },
        "rescue_preset": rescue_preset or "none",
        "selected_hosts": sorted(selected_hosts),
        "selected_categories": sorted(selected_categories),
        "route_rebuild": {
            "performed": route_rebuild_summary is not None,
            "summary": route_rebuild_summary or {},
        },
        "records": records,
    }
    write_json(report_path, report)
    return report


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manual-csv", default=str(DEFAULT_MANUAL_CSV))
    parser.add_argument("--candidate-table", default=str(DEFAULT_CANDIDATE_TABLE))
    parser.add_argument("--pdf-dir", default=str(DEFAULT_PDF_DIR))
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    parser.add_argument("--doi-file", default="")
    parser.add_argument("--hosts", default="", help="Comma-separated URL hosts to include.")
    parser.add_argument(
        "--categories",
        default="",
        help="Comma-separated previous failure categories to include.",
    )
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument(
        "--standard-recovery-only",
        action="store_true",
        help=(
            "Only recover rows with clear repository API signals "
            "(OSF/PsyArXiv or Figshare-style article URLs)."
        ),
    )
    parser.add_argument(
        "--rescue-preset",
        choices=sorted(RESCUE_PRESETS - {""}),
        default="none",
        help="Named opt-in host/category preset for broader landing-page rescue runs.",
    )
    parser.add_argument("--timeout-sec", type=int, default=30)
    parser.add_argument("--rps", type=float, default=0.5)
    parser.add_argument(
        "--min-title-score",
        type=float,
        default=0.86,
        help="Minimum extracted-title score required before a recovered PDF is saved.",
    )
    parser.add_argument("--no-landing-resolution", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--rebuild-routes-after", action="store_true")
    parser.add_argument("--route-table", default=str(DEFAULT_ROUTE_TABLE))
    parser.add_argument("--metadata-table", default=str(DEFAULT_METADATA_TABLE))
    parser.add_argument("--prescreen-table", default=str(DEFAULT_PRESCREEN_TABLE))
    parser.add_argument("--domain-routing-table", default=str(DEFAULT_DOMAIN_ROUTING_TABLE))
    parser.add_argument("--fulltext-dir", default=str(DEFAULT_FULLTEXT_DIR))
    parser.add_argument("--route-summary-json", default=str(DEFAULT_ROUTE_SUMMARY_JSON))
    parser.add_argument("--route-counts-csv", default=str(DEFAULT_ROUTE_COUNTS_CSV))
    parser.add_argument("--manual-route-overrides", default=str(DEFAULT_MANUAL_ROUTE_OVERRIDES))
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    doi_filter = read_doi_file(Path(args.doi_file)) if clean(args.doi_file) else None
    if clean(args.categories):
        categories = parse_csv_values(args.categories)
    elif clean(args.rescue_preset).lower() in {"", "none"}:
        categories = parse_csv_values(DEFAULT_RECOVERY_CATEGORIES)
    else:
        categories = None
    recover_pdf_landing_pages(
        manual_csv=Path(args.manual_csv).resolve(),
        candidate_table=Path(args.candidate_table).resolve(),
        pdf_dir=Path(args.pdf_dir).resolve(),
        report_path=Path(args.report).resolve(),
        doi_filter=doi_filter,
        hosts=parse_csv_values(args.hosts),
        categories=categories,
        rescue_preset=args.rescue_preset,
        standard_recovery_only=bool(args.standard_recovery_only),
        limit=args.limit,
        timeout_sec=args.timeout_sec,
        rps=args.rps,
        min_title_score=args.min_title_score,
        apply=bool(args.apply),
        allow_landing_resolution=not args.no_landing_resolution,
        rebuild_routes_after=bool(args.rebuild_routes_after),
        route_table=Path(args.route_table).resolve(),
        metadata_table=Path(args.metadata_table).resolve(),
        prescreen_table=Path(args.prescreen_table).resolve(),
        domain_routing_table=Path(args.domain_routing_table).resolve() if clean(args.domain_routing_table) else None,
        fulltext_dir=Path(args.fulltext_dir).resolve(),
        route_summary_json=Path(args.route_summary_json).resolve(),
        route_counts_csv=Path(args.route_counts_csv).resolve(),
        manual_route_overrides=Path(args.manual_route_overrides).resolve()
        if clean(args.manual_route_overrides)
        else None,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
