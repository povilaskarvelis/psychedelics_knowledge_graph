#!/usr/bin/env python3
"""Build a staging-only, high-probability PDF-recovery queue.

This is deliberately narrower than the prior DOI landing-page sweeps.  It
selects only unresolved records for which a *new, concrete* legal route is
known: a metadata-provided direct PDF endpoint that was not sent to the
latest direct-url runner, a repository API/landing route, a browser-audited
session-bound PDF control, or the one transient browser failure.  It does not
download, move, import, quarantine, or update ``candidate_papers``.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import datetime as dt
import json
from pathlib import Path
import re
from urllib.parse import urlparse

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
AUDITS = ROOT / "data" / "processed" / "corpus" / "audits"
DEFAULT_PASS_REPORTS = [
    AUDITS / "doi_browser_pass1_direct_attachment_20260719_v1.json",
    AUDITS / "doi_browser_pass2_technical_retry_recovery_20260719_v1.json",
    AUDITS / "doi_browser_pass3_lower_yield_recovery_20260719_v1.json",
]
DEFAULT_RANKED = AUDITS / "manual_pdf_download_ranked.csv"
DEFAULT_CANDIDATES = ROOT / "data" / "processed" / "corpus" / "candidate_papers.parquet"
DEFAULT_INTERNAL_AUDIT = AUDITS / "internal_browser_doi_landing_pass_20260719_v1.json"
DEFAULT_DOCUMENT_AUDIT = AUDITS / "browser_recovery_document_audit_20260719_v2.json"
DEFAULT_CHECKPOINT = AUDITS / "external_chrome_pdf_recovery_checkpoint_20260719_v1.json"
DEFAULT_INBOX = ROOT / "data" / "raw" / "papers" / "manual_pdf_inbox"
DEFAULT_PASS2_QUEUE = AUDITS / "internal_browser_technical_retry_pass2_queue_20260719.csv"
DEFAULT_OUTPUT_CSV = AUDITS / "targeted_pdf_recovery_queue_20260719_v1.csv"
DEFAULT_OUTPUT_JSON = AUDITS / "targeted_pdf_recovery_queue_20260719_v1.json"

DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:a-z0-9]+", re.IGNORECASE)
RESOLVER_HOSTS = {
    "doi.org",
    "dx.doi.org",
    "api.openalex.org",
    "openalex.org",
    "pubmed.ncbi.nlm.nih.gov",
    "scopus.com",
}
UNTRUSTED_HOSTS = {"scholarhub.ui.ac.id"}
ENGLISH = {"", "en", "eng", "english"}
CHROME_ONLY_HOSTS = {
    "academic.oup.com",
    "onlinelibrary.wiley.com",
    "analyticalsciencejournals.onlinelibrary.wiley.com",
    "associationofanaesthetists-publications.onlinelibrary.wiley.com",
    "bpspubs.onlinelibrary.wiley.com",
    "journals.sagepub.com",
    "tandfonline.com",
    "pubs.asahq.org",
    "jpet.aspetjournals.org",
    "molpharm.aspetjournals.org",
    "journals.lww.com",
    "sciencedirect.com",
    "linkinghub.elsevier.com",
    "karger.com",
    "bmj.com",
    "emj.bmj.com",
    "thorax.bmj.com",
    "nejm.org",
    "muse.jhu.edu",
    "psychiatryonline.org",
    "ajp.psychiatryonline.org",
    "n.neurology.org",
    "cdnsciencepub.com",
}
REPOSITORY_HINTS = (
    "repository",
    "repo.",
    "eprint",
    "espace.",
    "opus.",
    "zora.",
    "soar.",
    "iris.",
    "digitalcommons.",
    "academiccommons.",
    "figshare.",
    "zenodo.",
    "osf.io",
    "archive.org",
    "hdl.handle.net",
    "handle.",
    "research-collection.",
    "lawcat.",
    "mdsoar.",
    "pure.",
    "e-space.",
    "sro.",
    "research.",
    ".edu",
    ".ac.uk",
)

# These URLs were individually checked against the public repository APIs in
# the host-route audit.  They are deliberately explicit rather than inferred
# from a publisher URL, so the next pass can start with genuine PDF bytes.
VERIFIED_DIRECT_OVERRIDES = {
    "10.5167/uzh-291670": ("zora_dspace_bitstream", "https://www.zora.uzh.ch/server/api/core/bitstreams/7a5a899d-11da-4b75-b783-ab22194a82c5/content"),
    "10.5167/uzh-280475": ("zora_dspace_bitstream", "https://www.zora.uzh.ch/server/api/core/bitstreams/15674571-8f34-43f3-b8ec-6d3679619530/content"),
    "10.5167/uzh-280550": ("zora_dspace_bitstream", "https://www.zora.uzh.ch/server/api/core/bitstreams/204d7782-ecd1-4789-81f3-6a207c67fc86/content"),
    "10.5167/uzh-284111": ("zora_dspace_bitstream", "https://www.zora.uzh.ch/server/api/core/bitstreams/c76efb87-454b-4f9e-8dd6-7e65e5a4df12/content"),
    "10.5167/uzh-284146": ("zora_dspace_bitstream", "https://www.zora.uzh.ch/server/api/core/bitstreams/192e6c2a-874d-4831-b55f-f6bf8047d336/content"),
    "10.5167/uzh-284302": ("zora_dspace_bitstream", "https://www.zora.uzh.ch/server/api/core/bitstreams/bff3201d-376d-420c-ac06-5752ca530556/content"),
    "10.5167/uzh-284377": ("zora_dspace_bitstream", "https://www.zora.uzh.ch/server/api/core/bitstreams/4b947b4b-74dd-438c-80a3-0bca08faf4ff/content"),
    "10.5167/uzh-284451": ("zora_dspace_bitstream", "https://www.zora.uzh.ch/server/api/core/bitstreams/880cfb46-13ad-4160-9a72-0cf334a4f10e/content"),
    "10.5167/uzh-290810": ("zora_dspace_bitstream", "https://www.zora.uzh.ch/server/api/core/bitstreams/099a27d7-601c-40a9-b367-d330ac621bd9/content"),
    "10.5167/uzh-291896": ("zora_dspace_bitstream", "https://www.zora.uzh.ch/server/api/core/bitstreams/cc7acbc0-cddd-4322-8465-87c512ec98fd/content"),
    "10.5167/uzh-434709": ("zora_dspace_bitstream", "https://www.zora.uzh.ch/server/api/core/bitstreams/29572587-d709-401d-8eb4-ba332e2f6775/content"),
    "10.1016/j.neubiorev.2022.105020": ("zora_dspace_bitstream", "https://www.zora.uzh.ch/server/api/core/bitstreams/c915d5a5-6500-455c-a322-bf1ff3d1b0ef/content"),
    "10.1016/j.jpsychires.2023.01.009": ("zora_dspace_bitstream", "https://www.zora.uzh.ch/server/api/core/bitstreams/8f1470a9-41e0-4a4a-9a3f-5adad06c5009/content"),
    "10.31235/osf.io/429dw_v1": ("osf_direct_pdf", "https://osf.io/download/69e8e78224141f4890affb96/"),
    "10.31235/osf.io/tk2dv": ("osf_direct_pdf", "https://osf.io/download/bx42m/"),
    "10.31235/osf.io/fv6wj_v2": ("osf_direct_pdf", "https://osf.io/download/692ead115884d43265e644c8/"),
    "10.31235/osf.io/tk4bv_v1": ("osf_direct_pdf", "https://osf.io/download/6a328050aa796896eb9450da/"),
    "10.1016/j.neuroimage.2017.11.030": ("figshare_direct_pdf", "https://ndownloader.figshare.com/files/41160143"),
    "10.1016/j.neuropsychologia.2016.04.005": ("figshare_direct_pdf", "https://ndownloader.figshare.com/files/41142668"),
    "10.1016/j.forc.2020.100263": ("figshare_direct_pdf", "https://ndownloader.figshare.com/files/65202042"),
    "10.1016/j.drugpo.2015.12.025": ("figshare_direct_pdf", "https://ndownloader.figshare.com/files/18313265"),
}


def clean(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip()


def doi_key(value: object) -> str:
    text = clean(value).lower()
    text = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", text)
    return re.sub(r"^doi:\s*", "", text).rstrip(".,; ")


def slug(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "_", clean(value).lower()).strip("_")


def split_urls(value: object) -> list[str]:
    return [part.strip() for part in clean(value).split("|") if part.strip()]


def host(url: object) -> str:
    value = clean(url)
    parsed = urlparse(value)
    output = parsed.netloc.lower().removeprefix("www.")
    return output


def is_independent_http_url(url: object) -> bool:
    value = clean(url)
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(host(value)) and host(value) not in RESOLVER_HOSTS | UNTRUSTED_HOSTS


def is_direct_pdf_url(url: object) -> bool:
    value = clean(url)
    if not is_independent_http_url(value):
        return False
    parsed = urlparse(value)
    path = parsed.path.lower()
    return (
        path.endswith(".pdf")
        or "pdf?" in value.lower()
        or "download?" in value.lower()
        or any(token in path for token in ("/pdf", "pdf/", "bitstream", "download", "viewcontent", "fulltext", "getpdf", "article-pdf", "epdf"))
    )


def is_repository_like(url: object, manual_class: object) -> bool:
    if clean(manual_class) in {"repository_or_preprint", "institutional_repository"}:
        return True
    value = host(url)
    return any(token in value for token in REPOSITORY_HINTS)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def report_records(payload: dict) -> list[dict]:
    return payload.get("records") or payload.get("results") or []


def load_latest_reports(paths: list[Path]) -> tuple[dict[str, dict], dict[str, list[str]]]:
    latest: dict[str, dict] = {}
    passes: dict[str, list[str]] = defaultdict(list)
    for index, path in enumerate(paths, start=1):
        label = f"pass{index}"
        for row in report_records(load_json(path)):
            doi = doi_key(row.get("doi", ""))
            if not doi:
                continue
            passes[doi].append(label)
            latest[doi] = {**row, "source_pass": label, "source_report": str(path.resolve())}
    return latest, passes


def input_urls(row: dict) -> list[tuple[str, str]]:
    """Return metadata URLs in stable order, retaining their provenance."""
    fields = (
        "open_access_url_rank",
        "best_pdf_url_rank",
        "pdf_url_candidates_rank",
        "open_access_url",
        "best_pdf_url",
        "pdf_url_candidates",
        "probable_pdf_url_candidates",
        "other_url_candidates",
    )
    output: list[tuple[str, str]] = []
    seen: set[str] = set()
    for field in fields:
        for value in split_urls(row.get(field, "")):
            if value not in seen:
                output.append((field, value))
                seen.add(value)
    return output


def api_route_for(url: str, doi: str) -> tuple[str, str] | None:
    """Return a legal repository API discovery route when it is deterministic."""
    value_host = host(url)
    path = urlparse(url).path
    doi_lower = doi.lower()
    if value_host.endswith("figshare.com"):
        match = re.search(r"/articles/(?:[^/]+/)?(\d+)(?:/|$)", path)
        if match:
            return "figshare_api_article", f"https://api.figshare.com/v2/articles/{match.group(1)}"
    if value_host == "zenodo.org":
        match = re.search(r"/(?:record|records)/(\d+)(?:/|$)", path)
        if match:
            return "zenodo_record_api", f"https://zenodo.org/api/records/{match.group(1)}"
    if value_host == "osf.io" or value_host.endswith(".osf.io"):
        code = ""
        if doi_lower.startswith("10.31235/osf.io/"):
            code = doi_lower.split("10.31235/osf.io/", 1)[1].split("_", 1)[0].split("/", 1)[0]
            if code:
                return "osf_preprint_api", f"https://api.osf.io/v2/preprints/{code}/"
        parts = [part for part in path.split("/") if part]
        if parts and re.fullmatch(r"[a-z0-9]{4,8}", parts[0], re.IGNORECASE):
            return "osf_node_files_api", f"https://api.osf.io/v2/nodes/{parts[0]}/files/"
    return None


def source_pass2_known_direct_urls(path: Path) -> dict[str, set[str]]:
    if not path.is_file():
        return {}
    frame = pd.read_csv(path).fillna("")
    output: dict[str, set[str]] = defaultdict(set)
    for row in frame.to_dict("records"):
        doi = doi_key(row.get("doi", ""))
        value = clean(row.get("known_pdf_url", ""))
        if doi and value:
            output[doi].add(value)
    return output


def direct_route_for(row: dict, *, previously_sent: set[str]) -> tuple[str, str, str] | None:
    """Choose the strongest metadata direct URL not already sent to direct runner."""
    options: list[tuple[int, str, str]] = []
    for source, value in input_urls(row):
        if value in previously_sent or not is_direct_pdf_url(value):
            continue
        value_host = host(value)
        # A direct response that previously mismatched the requested record is
        # evidence against that route, not a reason to re-fetch it.
        if value_host in UNTRUSTED_HOSTS:
            continue
        if is_repository_like(value, row.get("manual_host_class", "")):
            score = 0
            route_type = "repository_direct_pdf"
        elif value_host in CHROME_ONLY_HOSTS:
            score = 2
            route_type = "publisher_direct_pdf_chrome"
        else:
            score = 1
            route_type = "public_direct_pdf"
        # explicit OA URL is stronger than a generic candidate field.
        if source.startswith("open_access_url"):
            score -= 1
        options.append((score, route_type, value))
    if not options:
        return None
    score, route_type, value = sorted(options, key=lambda item: (item[0], item[2]))[0]
    return route_type, value, host(value)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pass-report", action="append", default=[])
    parser.add_argument("--ranked-csv", default=str(DEFAULT_RANKED))
    parser.add_argument("--candidate-table", default=str(DEFAULT_CANDIDATES))
    parser.add_argument("--internal-audit", default=str(DEFAULT_INTERNAL_AUDIT))
    parser.add_argument("--document-audit", default=str(DEFAULT_DOCUMENT_AUDIT))
    parser.add_argument("--checkpoint", default=str(DEFAULT_CHECKPOINT))
    parser.add_argument("--inbox-dir", default=str(DEFAULT_INBOX))
    parser.add_argument("--pass2-queue", default=str(DEFAULT_PASS2_QUEUE))
    parser.add_argument(
        "--verified-only",
        action="store_true",
        help="Emit only independently verified repository API/PDF endpoints; defer Chrome-only routes.",
    )
    parser.add_argument("--output-csv", default=str(DEFAULT_OUTPUT_CSV))
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    args = parser.parse_args()

    pass_paths = [Path(value).resolve() for value in args.pass_report] or DEFAULT_PASS_REPORTS
    for path in pass_paths:
        if not path.is_file():
            raise FileNotFoundError(path)
    latest, pass_history = load_latest_reports(pass_paths)
    unresolved = {
        doi: row
        for doi, row in latest.items()
        if clean(row.get("status", "")) in {"not_recovered", "browser_error"}
    }

    ranked = pd.read_csv(Path(args.ranked_csv).resolve()).fillna("")
    ranked["doi"] = ranked["doi"].map(doi_key)
    candidates = pd.read_parquet(Path(args.candidate_table).resolve()).fillna("")
    candidates["doi"] = candidates["doi"].map(doi_key)
    frame = pd.DataFrame([{"doi": doi, **row} for doi, row in unresolved.items()])
    frame = frame.merge(ranked, on="doi", how="left", suffixes=("", "_rank"))
    frame = frame.merge(candidates, on="doi", how="left", suffixes=("_rank", ""))

    internal_payload = load_json(Path(args.internal_audit).resolve())
    internal_rows = pd.DataFrame(internal_payload.get("outcomes", [])).fillna("")
    internal_rows["doi"] = internal_rows.get("doi", pd.Series(dtype=str)).map(doi_key)
    internal_rows = internal_rows.rename(
        columns={"status": "internal_browser_status", "reason": "internal_browser_reason", "pdf": "internal_browser_pdf_url"}
    )
    keep_internal = [column for column in ("doi", "internal_browser_status", "internal_browser_reason", "internal_browser_pdf_url") if column in internal_rows]
    frame = frame.merge(internal_rows[keep_internal], on="doi", how="left").fillna("")

    document_payload = load_json(Path(args.document_audit).resolve())
    document_rows = document_payload.get("records", [])
    audited_requested = {doi_key(row.get("requested_doi", "")) for row in document_rows if doi_key(row.get("requested_doi", ""))}
    audited_foreign: set[str] = set()
    for row in document_rows:
        audited_foreign.update(doi_key(value) for value in DOI_RE.findall(clean(row.get("foreign_front_dois", ""))))

    checkpoint_payload = load_json(Path(args.checkpoint).resolve())
    checkpoint_saved = {
        doi_key(row.get("doi", ""))
        for row in checkpoint_payload.get("results", [])
        if clean(row.get("status", "")) == "verified_download" and doi_key(row.get("doi", ""))
    }
    canonical = set(
        frame.loc[
            (frame.get("pdf_local_path", "").astype(str) != "")
            | (frame.get("local_pdf_paths", "").astype(str) != "")
            | (frame.get("flag_has_local_pdf", False) == True),
            "doi",
        ]
    )
    inbox_slugs = {slug(path.stem.split("__", 1)[0]) for path in Path(args.inbox_dir).resolve().glob("*.pdf")}
    pass2_sent = source_pass2_known_direct_urls(Path(args.pass2_queue).resolve())

    exclusions: Counter[str] = Counter()
    selected: list[dict] = []
    for row in frame.to_dict("records"):
        doi = doi_key(row.get("doi", ""))
        if not doi:
            exclusions["missing_doi"] += 1
            continue
        internal_status = clean(row.get("internal_browser_status", ""))
        language = clean(row.get("language", "")).lower()
        failure = clean(row.get("pdf_download_failure_category", "")).lower()
        oa_status = clean(row.get("open_access_status", "")).lower()
        if doi in audited_requested or doi in audited_foreign:
            exclusions["already_staged_or_alias_from_document_audit"] += 1
            continue
        if doi in checkpoint_saved:
            exclusions["verified_external_chrome_download"] += 1
            continue
        if doi in canonical:
            exclusions["canonical_pdf_present"] += 1
            continue
        if slug(doi) in inbox_slugs:
            exclusions["matching_inbox_filename"] += 1
            continue
        if internal_status.startswith("exclude_"):
            exclusions["known_publication_format_exclusion"] += 1
            continue
        if internal_status == "retry_identity_alias" or clean(row.get("doi_alias_status", "")) or clean(row.get("doi_alias_of", "")):
            exclusions["known_doi_alias_or_identity_mismatch"] += 1
            continue
        if failure == "source_identity_mismatch":
            exclusions["previous_source_identity_mismatch"] += 1
            continue
        if language not in ENGLISH:
            exclusions["metadata_non_english"] += 1
            continue
        if oa_status == "closed":
            exclusions["metadata_closed_access"] += 1
            continue
        # A host-route audit can establish a valid public PDF even when the
        # earlier metadata pass had only marked the record abstract-only.
        if doi not in VERIFIED_DIRECT_OVERRIDES and clean(row.get("source_text_state", "")) != "public_full_text_candidate":
            exclusions["not_public_fulltext_candidate"] += 1
            continue
        if args.verified_only and doi not in VERIFIED_DIRECT_OVERRIDES:
            exclusions["deferred_nonverified_route"] += 1
            continue

        source_pass = clean(row.get("source_pass", ""))
        direct_previously_sent: set[str] = set()
        # Pass 1 was explicitly a direct-attachment sweep; re-sending exactly
        # the same metadata endpoints would be redundant.  Pass 2 had three
        # explicit direct URLs sent to the CJS runner; all other metadata
        # endpoints remained untried by that runner.
        if source_pass == "pass1":
            direct_previously_sent = {value for _, value in input_urls(row) if is_direct_pdf_url(value)}
        elif source_pass == "pass2":
            direct_previously_sent = pass2_sent.get(doi, set())

        candidate: dict | None = None
        if doi in VERIFIED_DIRECT_OVERRIDES:
            route_type, target_url = VERIFIED_DIRECT_OVERRIDES[doi]
            candidate = {
                "priority": "A0",
                "priority_score": 110,
                "retrieval_mode": "automated_verified_repository_direct_pdf",
                "route_type": route_type,
                "route_url": target_url,
                "route_host": host(target_url),
                "route_evidence": "Host-route audit independently verified this public repository item exposes a PDF bitstream.",
            }
        exact_pdf = clean(row.get("internal_browser_pdf_url", ""))
        exact_control = internal_status in {
            "accessible_session_bound_pdf",
            "pdf_candidate",
            "retry_forbidden",
            "retry_nonpdf",
            "retry_zero_byte",
        }
        if candidate is None and exact_control and (exact_pdf or internal_status == "pdf_candidate"):
            target_url = exact_pdf or clean(row.get("manual_doi_landing_url", "")) or f"https://doi.org/{doi}"
            candidate = {
                "priority": "A1",
                "priority_score": 100,
                "retrieval_mode": "external_chrome_confirmed_pdf_control",
                "route_type": "session_bound_or_audited_pdf_control",
                "route_url": target_url,
                "route_host": host(target_url),
                "route_evidence": f"Internal browser audit={internal_status}; {clean(row.get('internal_browser_reason', ''))}",
            }
        if candidate is None:
            # Prefer deterministic repository APIs over landing-page clicks.
            api_options: list[tuple[str, str, str]] = []
            for _, value in input_urls(row):
                if is_independent_http_url(value):
                    api = api_route_for(value, doi)
                    if api:
                        api_options.append((api[0], api[1], value))
            if api_options:
                route_type, route_url, evidence_url = sorted(api_options, key=lambda item: (item[0], item[1]))[0]
                candidate = {
                    "priority": "A2",
                    "priority_score": 96,
                    "retrieval_mode": "repository_api_then_direct",
                    "route_type": route_type,
                    "route_url": route_url,
                    "route_host": host(evidence_url),
                    "route_evidence": f"Metadata exposes repository route {evidence_url}; use its public API to enumerate the primary PDF.",
                }
            else:
                direct = direct_route_for(row, previously_sent=direct_previously_sent)
                if direct:
                    route_type, route_url, route_host = direct
                    if route_type == "repository_direct_pdf":
                        priority, score, mode = "A3", 92, "automated_direct_pdf"
                    elif route_type == "publisher_direct_pdf_chrome":
                        priority, score, mode = "C1", 72, "external_chrome_direct_pdf"
                    else:
                        priority, score, mode = "B1", 84, "automated_direct_pdf"
                    candidate = {
                        "priority": priority,
                        "priority_score": score,
                        "retrieval_mode": mode,
                        "route_type": route_type,
                        "route_url": route_url,
                        "route_host": route_host,
                        "route_evidence": "Untried metadata direct-PDF endpoint; validate bytes and article identity before any import.",
                    }
                elif internal_status == "retry_waf":
                    target_url = clean(row.get("manual_doi_landing_url", "")) or f"https://doi.org/{doi}"
                    candidate = {
                        "priority": "C2",
                        "priority_score": 68,
                        "retrieval_mode": "external_chrome_waf_session",
                        "route_type": "browser_waf_retry",
                        "route_url": target_url,
                        "route_host": host(target_url),
                        "route_evidence": "Internal browser audit saw a WAF response. Do not retry headlessly; Chrome may establish a normal legal session.",
                    }
                elif clean(row.get("status", "")) == "browser_error":
                    target_url = clean(row.get("manual_doi_landing_url", "")) or f"https://doi.org/{doi}"
                    candidate = {
                        "priority": "D1",
                        "priority_score": 50,
                        "retrieval_mode": "single_automated_doi_retry",
                        "route_type": "transient_connection_retry",
                        "route_url": target_url,
                        "route_host": host(target_url),
                        "route_evidence": f"Last attempt was a browser transport failure: {clean(row.get('error', ''))[:240]}",
                    }

        if not candidate:
            exclusions["no_new_concrete_route_after_prior_passes"] += 1
            continue

        all_direct = [value for _, value in input_urls(row) if is_direct_pdf_url(value)]
        landing = clean(row.get("manual_doi_landing_url", "")) or f"https://doi.org/{doi}"
        selected.append(
            {
                **candidate,
                "doi": doi,
                "doi_landing_url": landing,
                "all_direct_pdf_urls": " | ".join(all_direct),
                "source_pass": source_pass,
                "prior_passes": " | ".join(pass_history.get(doi, [])),
                "prior_retrieval_status": clean(row.get("status", "")),
                "prior_retrieval_reason": clean(row.get("reason", "")),
                "internal_browser_status": internal_status,
                "internal_browser_reason": clean(row.get("internal_browser_reason", "")),
                "internal_browser_pdf_url": exact_pdf,
                "study_title": clean(row.get("study_title", row.get("study_title_rank", ""))),
                "study_year": clean(row.get("study_year", row.get("study_year_rank", ""))),
                "study_journal": clean(row.get("study_journal", row.get("study_journal_rank", ""))),
                "publication_type": clean(row.get("publication_type", "")),
                "language": language,
                "open_access_status": oa_status,
                "open_access_is_oa": clean(row.get("open_access_is_oa", "")),
                "source_text_state": clean(row.get("source_text_state", "")),
                "previous_download_failure_category": failure,
                "manual_host_class": clean(row.get("manual_host_class", "")),
                "staging_policy": "Save only to manual_pdf_inbox; then validate PDF bytes, DOI/title identity, and publication format. Do not update candidate_papers in this pass.",
            }
        )

    output = pd.DataFrame(selected)
    if not output.empty:
        output = output.sort_values(
            ["priority_score", "retrieval_mode", "route_host", "doi"],
            ascending=[False, True, True, True],
        ).reset_index(drop=True)
        output.insert(0, "queue_rank", range(1, len(output) + 1))

    output_csv = Path(args.output_csv).resolve()
    output_json = Path(args.output_json).resolve()
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    output.to_csv(output_csv, index=False)
    report = {
        "schema_version": "targeted_pdf_recovery_queue_v1",
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "staging_only": True,
        "candidate_table_modified": False,
        "download_performed": False,
        "inputs": {
            "pass_reports": [str(path.resolve()) for path in pass_paths],
            "ranked_csv": str(Path(args.ranked_csv).resolve()),
            "candidate_table": str(Path(args.candidate_table).resolve()),
            "internal_audit": str(Path(args.internal_audit).resolve()),
            "document_audit": str(Path(args.document_audit).resolve()),
            "external_chrome_checkpoint": str(Path(args.checkpoint).resolve()),
            "inbox_dir": str(Path(args.inbox_dir).resolve()),
        },
        "selection_policy": {
            "included": [
                "untried metadata direct-PDF endpoints from Pass 2/Pass 3",
                "deterministic OSF/Figshare/Zenodo repository APIs",
                "browser-audited session-bound or explicit PDF controls",
                "one transient browser connection retry",
            ],
            "excluded": [
                "already staged/audited PDFs, canonical PDFs, Chrome checkpoint downloads, and matching inbox filenames",
                "known publication-format exclusions, aliases, identity mismatches, metadata non-English records, and closed-access metadata",
                "generic landing pages with no new concrete route after the three passes",
                "direct URLs already sent in Pass 1 or explicit Pass-2 direct inputs",
            ],
        },
        "counts": {
            "latest_unresolved_records": len(unresolved),
            "selected": len(output),
            "by_priority": dict(Counter(output.get("priority", pd.Series(dtype=str)))),
            "by_retrieval_mode": dict(Counter(output.get("retrieval_mode", pd.Series(dtype=str)))),
            "by_route_type": dict(Counter(output.get("route_type", pd.Series(dtype=str)))),
            "by_route_host": dict(Counter(output.get("route_host", pd.Series(dtype=str)))),
            "exclusions": dict(exclusions),
        },
        "output_csv": str(output_csv),
    }
    output_json.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(
        f"TARGETED_PDF_RECOVERY_QUEUE: unresolved={len(unresolved):,} selected={len(output):,} "
        f"automated={(output.get('retrieval_mode', pd.Series(dtype=str)).str.startswith('automated').sum() if not output.empty else 0):,} "
        f"chrome={(output.get('retrieval_mode', pd.Series(dtype=str)).str.startswith('external_chrome').sum() if not output.empty else 0):,}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
