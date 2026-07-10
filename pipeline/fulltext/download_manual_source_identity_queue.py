#!/usr/bin/env python3
"""Download and identity-check PDFs from the source-identity manual queue.

This is intentionally an inbox-only workflow.  It reads the generated manual
queue, resolves direct PDF and landing-page URLs through the existing PDF
retrieval helpers, validates each response against the requested DOI/title (or
the exact curated PDF hash registry), and writes accepted PDFs only to
``data/raw/papers/manual_pdf_inbox``.

It does not update candidate tables, routes, canonical PDFs, full-text
artifacts, extraction outputs, or the knowledge graph.  A later explicit run of
``pipeline/fulltext/import_manual_pdfs.py`` remains the promotion boundary.
"""

from __future__ import annotations

import argparse
from collections import Counter
import csv
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from typing import Iterable
from urllib.parse import quote, urlparse

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.fulltext.import_manual_pdfs import (  # noqa: E402
    document_front_identity_text,
    document_front_title_text,
    extract_dois_from_text,
    extract_pdf_metadata_text,
    extract_pdf_text,
    title_match_score,
    title_tokens,
)
from pipeline.fulltext.pdf_alternate_sources import (  # noqa: E402
    AlternatePdfCandidate,
    fetch_pdf_bytes_for_candidate,
)
from pipeline.fulltext.source_identity import (  # noqa: E402
    clean,
    load_pdf_hash_attestation_registry,
    normalize_doi,
    pdf_bytes_match_hash_attestation,
)
from pipeline.ingest.sync_paper_library import (  # noqa: E402
    RateLimitedHttpClient,
    looks_like_pdf_bytes,
    pdf_filename_for_doi,
)


REPORT_DIR = ROOT / "outputs" / "source_identity_repair_20260710"
DEFAULT_QUEUE_CSV = REPORT_DIR / "manual_download_queue_all.csv"
DEFAULT_INBOX_DIR = ROOT / "data" / "raw" / "papers" / "manual_pdf_inbox"
DEFAULT_REPORT = REPORT_DIR / "manual_queue_download_attempts.json"
DEFAULT_MANUAL_URLS = ROOT / "pipeline" / "fulltext" / "manual_pdf_source_identity_repairs.json"

PRIORITY_ORDER = {
    "P0_existing_kg_and_retained": 0,
    "P1_existing_kg_or_curated_signal": 1,
    "P2_retained_candidate": 2,
    "not_in_priority_queue": 9,
}
PRIORITY_TIERS = tuple(PRIORITY_ORDER)
PMCID_RE = re.compile(r"\bPMC\d+\b", flags=re.IGNORECASE)
ANCILLARY_URL_RE = re.compile(
    r"(?:supp(?:lement|lementary)?|supporting[_ -]?(?:information|material)|"
    r"appendix|checklist|figure[_ -]?\d|fig[_ -]?\d|treatment[_ -]?manual|"
    r"merit[_ -]?review|grant[_ -]?review|meeting[_ -]?minutes)",
    flags=re.IGNORECASE,
)
ANCILLARY_PAGE_RE = re.compile(
    r"\b(?:supplementary (?:appendix|information|material|methods)|"
    r"supporting information)\b",
    flags=re.IGNORECASE,
)


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def truthy(value: object) -> bool:
    return clean(value).casefold() in {"1", "true", "yes", "y"}


def int_value(value: object) -> int:
    try:
        return int(float(clean(value) or 0))
    except (TypeError, ValueError):
        return 0


def split_urls(value: object) -> list[str]:
    out: list[str] = []
    for part in clean(value).split("|"):
        url = part.strip()
        if url and url not in out:
            out.append(url)
    return out


def sha256_bytes(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def load_queue_rows(path: Path) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(f"Manual queue CSV not found: {path}")
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def load_manual_urls(path: Path) -> dict[str, list[str]]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    records = payload if isinstance(payload, list) else payload.get("records", [])
    out: dict[str, list[str]] = {}
    for row in records:
        if not isinstance(row, dict):
            continue
        doi = normalize_doi(row.get("doi", "")).casefold()
        if not doi:
            continue
        urls = row.get("urls", [])
        if isinstance(urls, str):
            urls = split_urls(urls)
        if isinstance(urls, list):
            out[doi] = [clean(url) for url in urls if clean(url)]
    return out


def read_doi_file(path: Path) -> set[str]:
    return {
        doi
        for line in path.read_text(encoding="utf-8").splitlines()
        if (doi := normalize_doi(line).casefold())
    }


def select_queue_rows(
    rows: Iterable[dict],
    *,
    priority_only: bool = False,
    priority_tiers: set[str] | None = None,
    min_priority_score: int = 0,
    doi_filter: set[str] | None = None,
    limit: int = 0,
) -> list[dict]:
    selected: list[dict] = []
    normalized_filter = (
        None
        if doi_filter is None
        else {normalize_doi(value).casefold() for value in doi_filter if normalize_doi(value)}
    )
    for row in rows:
        doi = normalize_doi(row.get("doi", "")).casefold()
        if not doi:
            continue
        if "repair_eligible" in row and not truthy(row.get("repair_eligible", False)):
            continue
        if clean(row.get("recommended_acquisition_route", "")).startswith("none_"):
            continue
        if clean(row.get("curated_access_status", "")) in {
            "user_confirmed_no_public_full_text",
            "no_verified_public_full_text",
        }:
            continue
        if normalized_filter is not None and doi not in normalized_filter:
            continue
        if priority_only and not truthy(row.get("priority_eligible", False)):
            continue
        tier = clean(row.get("priority_tier", "")) or "not_in_priority_queue"
        if priority_tiers and tier not in priority_tiers:
            continue
        if int_value(row.get("priority_score", 0)) < min_priority_score:
            continue
        selected.append(row)
    selected.sort(
        key=lambda row: (
            PRIORITY_ORDER.get(clean(row.get("priority_tier", "")), 8),
            -int_value(row.get("priority_score", 0)),
            -int_value(row.get("kg_finding_count", 0)),
            normalize_doi(row.get("doi", "")).casefold(),
        )
    )
    return selected[:limit] if limit > 0 else selected


def candidate_evidence_sources(row: dict) -> dict[str, str]:
    raw = clean(row.get("candidate_url_evidence_json", ""))
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(payload, list):
        return {}
    return {
        clean(item.get("url", "")): clean(item.get("source", ""))
        for item in payload
        if isinstance(item, dict) and clean(item.get("url", ""))
    }


def verified_pmcid(row: dict) -> str:
    value = clean(row.get("verified_pmcid", "")).upper()
    return value if re.fullmatch(r"PMC\d+", value) else ""


def queue_candidate_is_safe(
    url: str,
    *,
    verified_pmc: str,
    allow_ancillary_name: bool,
) -> tuple[bool, str]:
    parsed = urlparse(clean(url))
    if parsed.scheme.casefold() not in {"http", "https"} or not parsed.netloc:
        return False, "not_http_url"
    if not allow_ancillary_name and ANCILLARY_URL_RE.search(url):
        return False, "ancillary_url_pattern"
    url_pmcids = {match.upper() for match in PMCID_RE.findall(url)}
    if url_pmcids and (not verified_pmc or url_pmcids != {verified_pmc}):
        return False, "unverified_or_stale_pmcid"
    return True, ""


def doi_landing_url(doi: str) -> str:
    return f"https://doi.org/{quote(normalize_doi(doi), safe='/:;()._-')}"


def is_doi_resolver_url_for(url: str, doi: str) -> bool:
    parsed = urlparse(clean(url))
    host = parsed.netloc.casefold().removeprefix("www.")
    return host in {"doi.org", "dx.doi.org"} and normalize_doi(url).casefold() == normalize_doi(doi).casefold()


def candidate_records_from_queue_row(
    row: dict,
    *,
    manual_urls: Iterable[str] = (),
) -> tuple[list[AlternatePdfCandidate], list[dict]]:
    """Return deduplicated, re-screened queue candidates in attempt order."""

    doi = normalize_doi(row.get("doi", "")).casefold()
    pmcid = verified_pmcid(row)
    evidence = candidate_evidence_sources(row)
    candidates: list[AlternatePdfCandidate] = []
    exclusions: list[dict] = []
    seen: set[str] = set()

    def add(url: str, source: str, reason: str, *, allow_ancillary_name: bool = False) -> None:
        url = clean(url)
        if not url or url in seen:
            return
        seen.add(url)
        safe, rejection = queue_candidate_is_safe(
            url,
            verified_pmc=pmcid,
            allow_ancillary_name=allow_ancillary_name,
        )
        if not safe:
            exclusions.append({"url": url, "source": source, "reason": rejection})
            return
        candidates.append(
            AlternatePdfCandidate(
                url=url,
                source=source,
                reason=reason,
                host_type="repository" if "pmc" in source else "",
            )
        )

    for url in manual_urls:
        add(url, "manual_url_registry", "curator_verified_exact_pdf_url", allow_ancillary_name=True)
    for url in split_urls(row.get("curated_exact_pdf_urls", "")):
        add(url, "queue_curated_exact", "curated_exact_pdf_url", allow_ancillary_name=True)
    for url in split_urls(row.get("candidate_urls_requiring_validation", "")):
        # Avoid retrying an alternate spelling of the DOI resolver before the
        # one canonical DOI landing candidate appended below.
        if is_doi_resolver_url_for(url, doi):
            continue
        source = evidence.get(url, "")
        add(
            url,
            f"queue_candidate:{source}" if source else "queue_candidate",
            "safe_generated_queue_candidate",
        )
    if pmcid:
        add(
            f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/",
            "verified_pmc",
            "verified_pmc_landing_url",
            allow_ancillary_name=True,
        )
    if doi:
        add(
            doi_landing_url(doi),
            "doi_landing",
            "canonical_doi_landing_url",
            allow_ancillary_name=True,
        )
    return candidates, exclusions


def extract_pdf_identity_texts(body: bytes) -> tuple[str, str]:
    """Extract bounded PDF text and embedded metadata without retaining a file."""

    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as handle:
            handle.write(body)
            temp_path = Path(handle.name)
        return extract_pdf_text(temp_path, max_pages=1), extract_pdf_metadata_text(temp_path)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def validate_downloaded_pdf(
    *,
    doi: str,
    title: str,
    body: bytes,
    min_title_score: float = 0.86,
    pdf_hash_attestations: dict[str, dict] | None = None,
) -> dict:
    """Validate one PDF using exact-front DOI, page-top title, or exact hash."""

    requested = normalize_doi(doi).casefold()
    result = {
        "accepted": False,
        "basis": "",
        "requested_doi": requested,
        "pdf_sha256": sha256_bytes(body),
        "pdf_size": len(body),
        "front_dois": [],
        "metadata_dois": [],
        "title_score": 0.0,
        "title_token_count": len(title_tokens(title)),
    }
    if not looks_like_pdf_bytes(body):
        return {**result, "basis": "not_pdf"}
    attestations = (
        load_pdf_hash_attestation_registry()["records"]
        if pdf_hash_attestations is None
        else pdf_hash_attestations
    )
    if pdf_bytes_match_hash_attestation(requested, body, attestations):
        return {**result, "accepted": True, "basis": "curated_pdf_hash", "title_score": 1.0}

    text, metadata_text = extract_pdf_identity_texts(body)
    first_page = clean(text).split("\f", 1)[0]
    ancillary = bool(ANCILLARY_PAGE_RE.search(first_page[:4000]))
    metadata_dois = extract_dois_from_text(metadata_text)
    front_dois = extract_dois_from_text(document_front_identity_text(text, ""))
    result.update(
        {
            "front_dois": front_dois,
            "metadata_dois": metadata_dois,
            "front_page_char_count": len(clean(first_page)),
            "metadata_char_count": len(clean(metadata_text)),
            "ancillary_document": ancillary,
        }
    )
    if ancillary:
        return {**result, "basis": "ancillary_document"}

    metadata_conflicts = [value for value in metadata_dois if value != requested]
    if requested in metadata_dois:
        return {**result, "accepted": True, "basis": "pdf_metadata_doi"}
    if metadata_conflicts:
        return {**result, "basis": "pdf_metadata_doi_conflict"}

    front_conflicts = [value for value in front_dois if value != requested]
    if requested in front_dois and not front_conflicts:
        return {**result, "accepted": True, "basis": "document_front_doi"}
    if front_conflicts:
        return {**result, "basis": "document_front_doi_conflict"}

    if not clean(first_page):
        return {**result, "basis": "no_usable_first_page_text"}
    score = title_match_score(title, document_front_title_text(text, ""))
    result["title_score"] = round(score, 4)
    if len(title_tokens(title)) < 5:
        return {**result, "basis": "short_title_without_exact_doi"}
    if min_title_score <= 0 or score < min_title_score:
        return {**result, "basis": "front_title_mismatch"}
    return {**result, "accepted": True, "basis": "bounded_page_top_title"}


def atomic_write_bytes(path: Path, body: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


def atomic_write_json(path: Path, payload: object) -> None:
    body = (json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    atomic_write_bytes(path, body)


def download_manual_queue(
    *,
    queue_csv: Path = DEFAULT_QUEUE_CSV,
    inbox_dir: Path = DEFAULT_INBOX_DIR,
    report_path: Path = DEFAULT_REPORT,
    apply: bool = False,
    priority_only: bool = False,
    priority_tiers: set[str] | None = None,
    min_priority_score: int = 0,
    doi_filter: set[str] | None = None,
    limit: int = 0,
    min_title_score: float = 0.86,
    replace_existing: bool = False,
    client: RateLimitedHttpClient | None = None,
    pdf_hash_attestations: dict[str, dict] | None = None,
    manual_urls_path: Path = DEFAULT_MANUAL_URLS,
) -> dict:
    if limit < 0:
        raise ValueError("limit must be >= 0")
    if min_title_score <= 0:
        raise ValueError("min_title_score must be > 0")
    rows = load_queue_rows(queue_csv)
    selected = select_queue_rows(
        rows,
        priority_only=priority_only,
        priority_tiers=priority_tiers,
        min_priority_score=min_priority_score,
        doi_filter=doi_filter,
        limit=limit,
    )
    if apply and client is None:
        client = RateLimitedHttpClient(
            rps=1.0,
            max_retries=1,
            timeout_sec=45,
            max_retry_after_sec=60,
            user_agent="kg-manual-source-identity-downloader",
        )
    attestations = (
        load_pdf_hash_attestation_registry()["records"]
        if pdf_hash_attestations is None
        else pdf_hash_attestations
    )
    manual_urls_by_doi = load_manual_urls(manual_urls_path)
    records: list[dict] = []
    counts: Counter[str] = Counter()

    for row in selected:
        doi = normalize_doi(row.get("doi", "")).casefold()
        title = clean(row.get("title", ""))
        destination = inbox_dir / pdf_filename_for_doi(doi)
        candidates, exclusions = candidate_records_from_queue_row(
            row,
            manual_urls=manual_urls_by_doi.get(doi, []),
        )
        record = {
            "doi": doi,
            "title": title,
            "priority_tier": clean(row.get("priority_tier", "")),
            "priority_score": int_value(row.get("priority_score", 0)),
            "final_action_category": clean(row.get("final_action_category", "")),
            "status": "planned",
            "destination": str(destination.resolve()),
            "candidate_count": len(candidates),
            "candidate_urls": [candidate.url for candidate in candidates],
            "excluded_candidates": exclusions,
            "attempts": [],
            "selected_url": "",
            "selected_sha256": "",
        }

        if destination.exists() and destination.is_file():
            existing = validate_downloaded_pdf(
                doi=doi,
                title=title,
                body=destination.read_bytes(),
                min_title_score=min_title_score,
                pdf_hash_attestations=attestations,
            )
            record["existing_validation"] = existing
            if existing["accepted"]:
                record["status"] = "already_present_validated"
                record["selected_sha256"] = existing["pdf_sha256"]
                records.append(record)
                counts[record["status"]] += 1
                continue
            if not replace_existing:
                record["status"] = "existing_file_identity_rejected"
                records.append(record)
                counts[record["status"]] += 1
                continue

        if not apply:
            record["status"] = "planned" if candidates else "no_candidate_url"
            records.append(record)
            counts[record["status"]] += 1
            continue

        assert client is not None
        for candidate in candidates:
            attempt = {
                "url": candidate.url,
                "source": candidate.source,
                "reason": candidate.reason,
                "status": "",
                "download_mode": "",
                "events": [],
                "validation": {},
            }
            body, events, mode = fetch_pdf_bytes_for_candidate(
                client=client,
                candidate=candidate,
                allow_landing_resolution=True,
            )
            attempt["download_mode"] = mode
            attempt["events"] = events
            if not looks_like_pdf_bytes(body):
                attempt["status"] = "download_not_pdf"
                record["attempts"].append(attempt)
                continue
            validation = validate_downloaded_pdf(
                doi=doi,
                title=title,
                body=body,
                min_title_score=min_title_score,
                pdf_hash_attestations=attestations,
            )
            attempt["validation"] = validation
            if not validation["accepted"]:
                attempt["status"] = "identity_rejected"
                record["attempts"].append(attempt)
                continue
            atomic_write_bytes(destination, body)
            attempt["status"] = "accepted_saved"
            record["attempts"].append(attempt)
            record["status"] = "downloaded_validated"
            record["selected_url"] = candidate.url
            record["selected_sha256"] = validation["pdf_sha256"]
            break
        else:
            record["status"] = "download_failed" if candidates else "no_candidate_url"

        records.append(record)
        counts[record["status"]] += 1

    report = {
        "schema_version": 1,
        "generated_at_utc": now_utc(),
        "apply": apply,
        "scope": "manual_pdf_inbox_only",
        "queue_csv": str(queue_csv.resolve()),
        "manual_urls_path": str(manual_urls_path.resolve()),
        "inbox_dir": str(inbox_dir.resolve()),
        "report_path": str(report_path.resolve()),
        "filters": {
            "priority_only": priority_only,
            "priority_tiers": sorted(priority_tiers or set()),
            "min_priority_score": min_priority_score,
            "doi_filter_count": len(doi_filter or set()),
            "limit": limit,
        },
        "queue_row_count": len(rows),
        "selected_row_count": len(selected),
        "counts": dict(sorted(counts.items())),
        "records": records,
    }
    atomic_write_json(report_path, report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue-csv", default=str(DEFAULT_QUEUE_CSV))
    parser.add_argument("--inbox-dir", default=str(DEFAULT_INBOX_DIR))
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    parser.add_argument("--manual-urls", default=str(DEFAULT_MANUAL_URLS))
    parser.add_argument("--priority-only", action="store_true")
    parser.add_argument(
        "--priority-tier",
        action="append",
        choices=PRIORITY_TIERS,
        default=[],
        help="Restrict to one or more queue priority tiers; repeat the option.",
    )
    parser.add_argument("--min-priority-score", type=int, default=0)
    parser.add_argument("--doi-file", default="")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--min-title-score", type=float, default=0.86)
    parser.add_argument("--replace-existing", action="store_true")
    parser.add_argument("--rps", type=float, default=1.0)
    parser.add_argument("--timeout-sec", type=int, default=45)
    parser.add_argument("--max-retries", type=int, default=1)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    if args.limit < 0:
        parser.error("--limit must be >= 0")
    if args.min_title_score <= 0:
        parser.error("--min-title-score must be > 0")
    doi_filter = read_doi_file(Path(args.doi_file).resolve()) if clean(args.doi_file) else None
    client = None
    if args.apply:
        client = RateLimitedHttpClient(
            rps=max(0.1, args.rps),
            max_retries=max(0, args.max_retries),
            timeout_sec=max(1, args.timeout_sec),
            max_retry_after_sec=60,
            user_agent="kg-manual-source-identity-downloader",
        )
    report = download_manual_queue(
        queue_csv=Path(args.queue_csv).resolve(),
        inbox_dir=Path(args.inbox_dir).resolve(),
        report_path=Path(args.report).resolve(),
        apply=args.apply,
        priority_only=args.priority_only,
        priority_tiers=set(args.priority_tier),
        min_priority_score=args.min_priority_score,
        doi_filter=doi_filter,
        limit=args.limit,
        min_title_score=args.min_title_score,
        replace_existing=args.replace_existing,
        client=client,
        manual_urls_path=Path(args.manual_urls).resolve(),
    )
    print(
        json.dumps(
            {
                "apply": report["apply"],
                "selected_row_count": report["selected_row_count"],
                "counts": report["counts"],
                "report_path": report["report_path"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
