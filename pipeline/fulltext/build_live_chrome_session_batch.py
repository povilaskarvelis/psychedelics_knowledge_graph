#!/usr/bin/env python3
"""Build a strict, staging-only external-Chrome PDF recovery batch.

The source is the internal DOI landing-page audit.  A record is eligible only
when that audit explicitly observed a matching, accessible PDF control and the
current candidate record is retained and labelled open access.  This script is
deliberately a queue builder: it neither opens a browser nor downloads,
imports, moves, quarantines, or updates any candidate record.
"""

from __future__ import annotations

import argparse
from collections import Counter
import datetime as dt
import json
from pathlib import Path
import re
from urllib.parse import urlparse

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
AUDITS = ROOT / "data" / "processed" / "corpus" / "audits"
DEFAULT_INTERNAL_AUDIT = AUDITS / "internal_browser_doi_landing_pass_20260719_v1.json"
DEFAULT_CANDIDATES = ROOT / "data" / "processed" / "corpus" / "candidate_papers.parquet"
DEFAULT_CHECKPOINT = AUDITS / "external_chrome_pdf_recovery_checkpoint_20260719_v1.json"
DEFAULT_INBOX = ROOT / "data" / "raw" / "papers" / "manual_pdf_inbox"
DEFAULT_CANONICAL = ROOT / "data" / "raw" / "papers" / "pdfs"
DEFAULT_OUTPUT_CSV = AUDITS / "external_chrome_session_bound_pdf_batch_20260719_v1.csv"
DEFAULT_OUTPUT_JSON = AUDITS / "external_chrome_session_bound_pdf_batch_20260719_v1.json"

NONARTICLE_RE = re.compile(
    r"conference|poster|proceeding|abstract|dissertation|thesis|dataset|"
    r"editorial|commentary|correction|erratum|news|peer.?review|supplement|"
    r"author response|letter to (the )?editor",
    re.IGNORECASE,
)
DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:a-z0-9]+", re.IGNORECASE)


def clean(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip()


def doi_key(value: object) -> str:
    text = clean(value).lower()
    text = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", text)
    return re.sub(r"^doi:\s*", "", text).rstrip(".,; ")


def truthy(value: object) -> bool:
    return clean(value).lower() in {"true", "1", "yes", "y"}


def host(value: object) -> str:
    return urlparse(clean(value)).netloc.lower().removeprefix("www.")


def doi_filename_prefix(doi: str) -> str:
    return doi.replace("/", "_")


def extracted_dois(value: object) -> set[str]:
    return {doi_key(item) for item in DOI_RE.findall(clean(value)) if doi_key(item)}


def audit_dois(directory: Path) -> set[str]:
    """Return requested/front-page DOI identities already examined in document audits."""
    output: set[str] = set()
    for path in sorted(directory.glob("*document_audit*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for row in payload.get("records", []):
            for field in ("requested_doi", "front_dois", "foreign_front_dois"):
                output.update(extracted_dois(row.get(field, "")))
    return output


def formatted_exclusions(directory: Path) -> set[str]:
    """Load only explicit publication-format exclusions, never inferred scope calls."""
    output: set[str] = set()
    for path in sorted(directory.glob("*publication_format*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for row in payload.get("records", []):
            status = clean(row.get("status", "")).lower()
            action = clean(row.get("recommended_action", "")).lower()
            publication_format = clean(row.get("publication_format", ""))
            if (
                "exclude" in status
                or "exclude" in action
                or NONARTICLE_RE.search(publication_format)
            ):
                doi = doi_key(row.get("doi", ""))
                if doi:
                    output.add(doi)
    # The larger format audit is CSV-backed, with the JSON only summarising it.
    for path in sorted(directory.glob("*publication_format*.csv")):
        try:
            frame = pd.read_csv(path, usecols=lambda column: column in {"doi", "recommended_action", "publication_format"}).fillna("")
        except (OSError, ValueError, pd.errors.EmptyDataError):
            continue
        for row in frame.to_dict("records"):
            if "exclude" in clean(row.get("recommended_action", "")).lower() or NONARTICLE_RE.search(clean(row.get("publication_format", ""))):
                doi = doi_key(row.get("doi", ""))
                if doi:
                    output.add(doi)
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--internal-audit", default=str(DEFAULT_INTERNAL_AUDIT))
    parser.add_argument("--candidate-table", default=str(DEFAULT_CANDIDATES))
    parser.add_argument("--checkpoint", default=str(DEFAULT_CHECKPOINT))
    parser.add_argument("--inbox-dir", default=str(DEFAULT_INBOX))
    parser.add_argument("--canonical-dir", default=str(DEFAULT_CANONICAL))
    parser.add_argument("--output-csv", default=str(DEFAULT_OUTPUT_CSV))
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    args = parser.parse_args()

    internal_path = Path(args.internal_audit).resolve()
    candidates_path = Path(args.candidate_table).resolve()
    checkpoint_path = Path(args.checkpoint).resolve()
    inbox_dir = Path(args.inbox_dir).resolve()
    canonical_dir = Path(args.canonical_dir).resolve()
    internal = json.loads(internal_path.read_text(encoding="utf-8"))
    source = [
        dict(row)
        for row in internal.get("outcomes", [])
        if clean(row.get("status", "")) == "accessible_session_bound_pdf" and doi_key(row.get("doi", ""))
    ]

    columns = [
        "doi", "study_title", "study_year", "study_journal", "publication_type", "language",
        "retained_for_extraction_candidate", "prescreen_retained_for_extraction_candidate",
        "open_access_status", "open_access_is_oa", "pdf_local_path", "local_pdf_paths",
        "flag_has_local_pdf", "doi_alias_status", "doi_alias_of", "published_version_doi",
    ]
    candidates = pd.read_parquet(candidates_path, columns=columns).fillna("")
    candidates["doi"] = candidates["doi"].map(doi_key)
    candidate_map = {row["doi"]: row for row in candidates.to_dict("records") if row["doi"]}

    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    checkpoint_dois = {
        doi_key(row.get("doi", ""))
        for row in checkpoint.get("results", [])
        if clean(row.get("status", "")) == "verified_download" and doi_key(row.get("doi", ""))
    }
    document_audited = audit_dois(AUDITS)
    nonarticle_audited = formatted_exclusions(AUDITS)
    inbox_names = {path.stem for path in inbox_dir.glob("*.pdf")}
    canonical_names = {path.stem for path in canonical_dir.glob("*.pdf")}

    selected: list[dict[str, object]] = []
    exclusions: Counter[str] = Counter()
    seen: set[str] = set()
    for source_row in source:
        doi = doi_key(source_row.get("doi", ""))
        if doi in seen:
            exclusions["duplicate_source_doi"] += 1
            continue
        seen.add(doi)
        candidate = candidate_map.get(doi)
        if not candidate:
            exclusions["missing_candidate"] += 1
            continue
        if not truthy(candidate.get("retained_for_extraction_candidate")) or not truthy(candidate.get("prescreen_retained_for_extraction_candidate")):
            exclusions["not_retained"] += 1
            continue
        if not truthy(candidate.get("open_access_is_oa")) or clean(candidate.get("open_access_status")).lower() == "closed":
            exclusions["not_open_access"] += 1
            continue
        if doi in checkpoint_dois:
            exclusions["verified_external_chrome_checkpoint"] += 1
            continue
        if doi in document_audited:
            exclusions["already_document_audited"] += 1
            continue
        if doi in nonarticle_audited or NONARTICLE_RE.search(clean(candidate.get("publication_type", ""))):
            exclusions["known_nonarticle"] += 1
            continue
        if clean(candidate.get("doi_alias_status")) or clean(candidate.get("doi_alias_of")):
            exclusions["known_doi_alias"] += 1
            continue
        prefix = doi_filename_prefix(doi)
        if any(name == prefix or name.startswith(prefix + "__") for name in inbox_names):
            exclusions["matching_current_inbox_file"] += 1
            continue
        if any(name == prefix or name.startswith(prefix + "__") for name in canonical_names):
            exclusions["matching_canonical_file"] += 1
            continue
        if clean(candidate.get("pdf_local_path")) or clean(candidate.get("local_pdf_paths")) or truthy(candidate.get("flag_has_local_pdf")):
            exclusions["candidate_already_has_local_pdf"] += 1
            continue

        direct_url = clean(source_row.get("pdf", ""))
        landing_url = clean(source_row.get("page_url", "")) or f"https://doi.org/{doi}"
        launch_url = direct_url or landing_url
        selected.append(
            {
                "source_audit_index": int(source_row.get("index", 0) or 0),
                "doi": doi,
                "study_title": clean(candidate.get("study_title", "")),
                "study_year": clean(candidate.get("study_year", "")),
                "study_journal": clean(candidate.get("study_journal", "")),
                "publication_type": clean(candidate.get("publication_type", "")),
                "open_access_status": clean(candidate.get("open_access_status", "")),
                "direct_pdf_url": direct_url,
                "landing_url": landing_url,
                "launch_url": launch_url,
                "host": host(launch_url),
                "observed_control": "exact_pdf_url" if direct_url else "matching_pdf_control_on_landing_page",
                "evidence": clean(source_row.get("reason", "")) or "Internal browser audit recorded an accessible matching PDF control.",
                "staging_policy": "Download only into manual_pdf_inbox; later validate PDF bytes, DOI/title identity, and publication format before any reconciliation or candidate update.",
            }
        )

    # Start with the six exact PDF endpoints, then use the audit's original
    # deterministic order. This avoids inventing a relevance rank.
    selected.sort(key=lambda row: (0 if row["direct_pdf_url"] else 1, row["source_audit_index"], row["doi"]))
    for order, row in enumerate(selected, start=1):
        row["batch_order"] = order
    order = [
        "batch_order", "doi", "study_title", "study_year", "study_journal", "publication_type",
        "open_access_status", "launch_url", "direct_pdf_url", "landing_url", "host", "observed_control",
        "evidence", "source_audit_index", "staging_policy",
    ]
    frame = pd.DataFrame(selected, columns=order)
    output_csv = Path(args.output_csv).resolve()
    output_json = Path(args.output_json).resolve()
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output_csv, index=False)
    report = {
        "schema_version": "external_chrome_session_bound_pdf_batch_v1",
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "staging_only": True,
        "browser_opened": False,
        "download_performed": False,
        "candidate_table_modified": False,
        "inputs": {
            "internal_audit": str(internal_path),
            "candidate_table": str(candidates_path),
            "external_chrome_checkpoint": str(checkpoint_path),
            "inbox_dir": str(inbox_dir),
            "canonical_dir": str(canonical_dir),
        },
        "selection_policy": {
            "included": [
                "internal audit status accessible_session_bound_pdf",
                "both current retained flags true",
                "open_access_is_oa true and not closed",
                "matching PDF control observed by the internal audit",
            ],
            "excluded": [
                "verified external-Chrome checkpoint DOI",
                "DOI represented by current inbox/canonical filename or candidate local-PDF fields",
                "any DOI represented in document-audit records",
                "known publication-format exclusion or DOI alias",
            ],
        },
        "counts": {
            "accessible_session_bound_pdf_source": len(source),
            "selected": len(frame),
            "with_exact_direct_pdf_url": int(frame["direct_pdf_url"].ne("").sum()) if not frame.empty else 0,
            "landing_page_control_only": int(frame["direct_pdf_url"].eq("").sum()) if not frame.empty else 0,
            "by_host": dict(Counter(frame["host"])) if not frame.empty else {},
            "exclusions": dict(exclusions),
        },
        "output_csv": str(output_csv),
        "records": frame.to_dict("records"),
    }
    output_json.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"LIVE_CHROME_SESSION_BATCH: source={len(source)} selected={len(frame)} exclusions={dict(exclusions)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
