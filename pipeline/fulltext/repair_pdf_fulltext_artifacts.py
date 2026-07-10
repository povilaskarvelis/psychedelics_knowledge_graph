#!/usr/bin/env python3
"""Replace source-identity failures with independently validated PDFs.

This repair is deliberately stricter than the normal downloader.  A candidate
PDF must put the requested title on page one (and, for short titles, also show
the requested DOI).  Proceedings/container records and known DOI/version
relationships are left for their dedicated repair paths.
"""

from __future__ import annotations

import argparse
from collections import Counter
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile
from typing import Iterable

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.fulltext.convert_pdfs import (  # noqa: E402
    DEFAULT_GROBID_URL,
    build_artifact,
    convert_pdf,
    doi_to_slug,
    grobid_is_available,
)
from pipeline.fulltext.pdf_alternate_sources import (  # noqa: E402
    AlternatePdfCandidate,
    extract_pdf_text_from_bytes,
    fetch_pdf_bytes_for_candidate,
    title_match_score,
)
from pipeline.fulltext.source_identity import (  # noqa: E402
    clean,
    identity_is_verified,
    normalize_doi,
    split_dois,
    title_phrase_match,
    title_tokens,
)
from pipeline.ingest.sync_paper_library import (  # noqa: E402
    RateLimitedHttpClient,
    looks_like_pdf_bytes,
    pdf_filename_for_doi,
    split_candidates,
)


DEFAULT_AUDIT = ROOT / "outputs" / "source_identity_repair_20260710" / "post_manual_jats_audit.json"
DEFAULT_SPECIAL = ROOT / "outputs" / "source_identity_repair_20260710" / "source_identity_special_classes.csv"
DEFAULT_PMC_INVENTORY = ROOT / "outputs" / "source_identity_repair_20260710" / "pmc_identity_inventory.csv"
DEFAULT_PMCID_RESOLUTION = ROOT / "outputs" / "source_identity_repair_20260710" / "artifact_pmcid_resolution.csv"
DEFAULT_METADATA = ROOT / "data" / "processed" / "corpus" / "paper_metadata_enrichment.parquet"
DEFAULT_CANDIDATES = ROOT / "data" / "processed" / "corpus" / "candidate_papers.parquet"
DEFAULT_ARTIFACT_DIR = ROOT / "data" / "processed" / "fulltext" / "articles"
DEFAULT_PDF_DIR = ROOT / "data" / "raw" / "papers" / "pdfs"
DEFAULT_QUARANTINE = ROOT / "data" / "processed" / "fulltext" / "source_identity_quarantine_20260710"
DEFAULT_REPORT = ROOT / "outputs" / "source_identity_repair_20260710" / "pdf_artifact_repair.json"
DEFAULT_MANUAL_URLS = ROOT / "pipeline" / "fulltext" / "manual_pdf_source_identity_repairs.json"

SKIP_CLASSIFICATIONS = {
    "benign_conflict",
    "proceedings_container",
    "repository_or_nested_document",
}
SKIP_PMC_CLASSES = {"valid_exact", "valid_known_alias"}
CORRECTION_WORDS = re.compile(r"\b(correction|corrigendum|erratum|retraction)\b", re.IGNORECASE)
ANCILLARY_URL_WORDS = re.compile(
    r"(?:figure|fig(?:ure)?[_ -]?\d|supp(?:lement|lementary)?|appendix|protocol|checklist)",
    re.IGNORECASE,
)
ANCILLARY_PAGE_WORDS = re.compile(
    r"\b(?:supplementary (?:appendix|information|material|methods)|supporting information)\b",
    re.IGNORECASE,
)


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def load_json(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def table_map(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    frame = pd.read_parquet(path).fillna("")
    out: dict[str, dict] = {}
    for row in frame.to_dict("records"):
        doi = normalize_doi(row.get("doi", "") or row.get("study_doi", ""))
        if doi:
            out[doi] = row
    return out


def csv_map(path: Path, key: str = "doi") -> dict[str, dict]:
    if not path.exists():
        return {}
    out: dict[str, dict] = {}
    for row in pd.read_csv(path, dtype=str).fillna("").to_dict("records"):
        doi = normalize_doi(row.get(key, ""))
        if doi:
            out[doi] = row
    return out


def read_doi_file(path: Path) -> set[str]:
    return {
        doi
        for line in path.read_text(encoding="utf-8").splitlines()
        if (doi := normalize_doi(line))
    }


def manual_url_map(path: Path) -> dict[str, list[str]]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    out: dict[str, list[str]] = {}
    for row in payload if isinstance(payload, list) else []:
        if not isinstance(row, dict):
            continue
        doi = normalize_doi(row.get("doi", ""))
        urls = [clean(value) for value in row.get("urls", []) if clean(value)]
        if doi and urls:
            out[doi] = urls
    return out


def candidate_urls(*rows: dict, manual_urls: Iterable[str] = ()) -> list[str]:
    out: list[str] = []
    for value in manual_urls:
        if clean(value) and clean(value) not in out:
            out.append(clean(value))
    for row in rows:
        for field in ("best_pdf_url", "pdf_url_candidates", "open_access_url"):
            for value in split_candidates(row.get(field, "")):
                if value and value not in out:
                    out.append(value)
    return out


def stale_pmcids(row: dict) -> set[str]:
    current = clean(row.get("current_pmcid", "")).upper()
    verified = clean(row.get("verified_pmcid", "")).upper()
    if current and current != verified:
        return {current}
    return set()


def url_is_eligible(url: str, invalid_pmcids: set[str]) -> tuple[bool, str]:
    lowered = clean(url).lower()
    if not lowered.startswith(("http://", "https://")):
        return False, "not_http"
    if any(pmcid.lower() in lowered for pmcid in invalid_pmcids):
        return False, "stale_unverified_pmcid"
    if ANCILLARY_URL_WORDS.search(lowered):
        return False, "ancillary_url"
    return True, ""


def validate_pdf_front_page(
    *,
    doi: str,
    title: str,
    body: bytes,
    min_title_score: float = 0.86,
) -> dict:
    text = extract_pdf_text_from_bytes(body, max_pages=1)
    score = title_match_score(title, text)
    phrase = title_phrase_match(title, text)
    doi_match = any(value == doi for value in split_dois(text))
    tokens = title_tokens(title)
    ancillary = bool(ANCILLARY_PAGE_WORDS.search(text[:3000]))
    enough_text = len(clean(text)) >= 300
    title_agrees = phrase or score >= min_title_score
    # A three- or four-word title is too easy to encounter incidentally.
    short_title_ok = len(tokens) >= 5 or (doi_match and title_agrees)
    accepted = enough_text and title_agrees and short_title_ok and not ancillary
    reason = "verified_front_page" if accepted else ""
    if not enough_text:
        reason = "no_usable_first_page_text"
    elif ancillary:
        reason = "ancillary_document"
    elif not title_agrees:
        reason = "title_mismatch"
    elif not short_title_ok:
        reason = "short_title_without_doi"
    return {
        "accepted": accepted,
        "reason": reason,
        "title_score": round(score, 4),
        "title_phrase_match": bool(phrase),
        "doi_match": bool(doi_match),
        "front_page_char_count": len(clean(text)),
        "front_page_text": text[:1000],
    }


def target_is_repair_candidate(
    audit_row: dict,
    special_row: dict,
    pmc_row: dict,
) -> tuple[bool, str]:
    if bool(audit_row.get("identity_verified")):
        return False, "already_verified"
    classification = clean(special_row.get("classification", ""))
    pmc_class = clean(pmc_row.get("identity_class", ""))
    if classification in SKIP_CLASSIFICATIONS:
        return False, f"dedicated_{classification}_path"
    if pmc_class in SKIP_PMC_CLASSES:
        return False, f"dedicated_{pmc_class}_identity_path"
    if classification == "correction_or_erratum" and CORRECTION_WORDS.search(clean(audit_row.get("requested_title", ""))):
        return False, "requested_record_is_correction"
    return True, ""


def sha256_bytes(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def backup_file(source: Path, target: Path) -> str:
    if not source.exists():
        return ""
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        shutil.copy2(source, target)
    return str(target)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", default=str(DEFAULT_AUDIT))
    parser.add_argument("--special-classes", default=str(DEFAULT_SPECIAL))
    parser.add_argument("--pmc-inventory", default=str(DEFAULT_PMC_INVENTORY))
    parser.add_argument("--pmcid-resolution", default=str(DEFAULT_PMCID_RESOLUTION))
    parser.add_argument("--metadata-table", default=str(DEFAULT_METADATA))
    parser.add_argument("--candidate-table", default=str(DEFAULT_CANDIDATES))
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    parser.add_argument("--pdf-dir", default=str(DEFAULT_PDF_DIR))
    parser.add_argument("--quarantine-dir", default=str(DEFAULT_QUARANTINE))
    parser.add_argument("--manual-urls", default=str(DEFAULT_MANUAL_URLS))
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    parser.add_argument("--doi-file", default="")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--rps", type=float, default=1.5)
    parser.add_argument("--timeout-sec", type=int, default=45)
    parser.add_argument("--max-retries", type=int, default=1)
    parser.add_argument("--grobid-url", default=DEFAULT_GROBID_URL)
    parser.add_argument("--grobid-timeout-sec", type=int, default=180)
    parser.add_argument("--min-title-score", type=float, default=0.86)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--progress-every", type=int, default=10)
    args = parser.parse_args()

    audit = load_json(Path(args.audit).resolve())
    special = csv_map(Path(args.special_classes).resolve())
    pmc_inventory = csv_map(Path(args.pmc_inventory).resolve())
    pmcid_resolution = csv_map(Path(args.pmcid_resolution).resolve())
    metadata = table_map(Path(args.metadata_table).resolve())
    candidates = table_map(Path(args.candidate_table).resolve())
    manual = manual_url_map(Path(args.manual_urls).resolve()) if clean(args.manual_urls) else {}
    doi_filter = read_doi_file(Path(args.doi_file).resolve()) if clean(args.doi_file) else None

    selected: list[dict] = []
    skipped: list[dict] = []
    for row in audit.get("rows", []) if isinstance(audit.get("rows"), list) else []:
        doi = normalize_doi(row.get("requested_doi", ""))
        if not doi or (doi_filter is not None and doi not in doi_filter):
            continue
        accepted, reason = target_is_repair_candidate(row, special.get(doi, {}), pmc_inventory.get(doi, {}))
        if accepted:
            selected.append(row)
        elif not bool(row.get("identity_verified")):
            skipped.append({"doi": doi, "reason": reason})
    if args.limit > 0:
        selected = selected[: args.limit]

    if args.apply and not grobid_is_available(args.grobid_url):
        parser.error(f"GROBID is unavailable at {args.grobid_url}")

    client = RateLimitedHttpClient(
        rps=max(0.1, args.rps),
        max_retries=max(0, args.max_retries),
        timeout_sec=max(1, args.timeout_sec),
        max_retry_after_sec=60,
        user_agent="kg-source-identity-pdf-repair",
    )
    artifact_dir = Path(args.artifact_dir).resolve()
    pdf_dir = Path(args.pdf_dir).resolve()
    quarantine = Path(args.quarantine_dir).resolve()
    records: list[dict] = []
    counts: Counter[str] = Counter()

    for position, audit_row in enumerate(selected, start=1):
        doi = normalize_doi(audit_row.get("requested_doi", ""))
        meta = metadata.get(doi, {})
        candidate = candidates.get(doi, {})
        title = clean(meta.get("study_title", "") or candidate.get("study_title", "") or audit_row.get("requested_title", ""))
        invalid_pmcids = stale_pmcids(pmcid_resolution.get(doi, {}))
        urls = candidate_urls(meta, candidate, manual_urls=manual.get(doi, []))
        record = {
            "doi": doi,
            "title": title,
            "status": "planned" if not args.apply else "not_repaired",
            "candidate_url_count": len(urls),
            "selected_url": "",
            "pdf_path": "",
            "artifact_path": str(artifact_dir / f"{doi_to_slug(doi)}.json"),
            "artifact_backup_path": "",
            "pdf_backup_path": "",
            "source_identity_status": "",
            "attempts": [],
        }
        if not args.apply:
            records.append(record)
            counts[record["status"]] += 1
            continue

        for url in urls:
            eligible, rejection = url_is_eligible(url, invalid_pmcids)
            attempt = {"url": url, "status": "", "error": "", "validation": {}}
            if not eligible:
                attempt["status"] = "skipped"
                attempt["error"] = rejection
                record["attempts"].append(attempt)
                continue
            pdf_candidate = AlternatePdfCandidate(url=url, source="metadata_repair", reason="canonical_metadata_candidate")
            body, events, mode = fetch_pdf_bytes_for_candidate(client=client, candidate=pdf_candidate)
            attempt["download_mode"] = mode
            attempt["events"] = events
            if not looks_like_pdf_bytes(body):
                attempt["status"] = "download_failed"
                attempt["error"] = mode
                record["attempts"].append(attempt)
                continue
            validation = validate_pdf_front_page(
                doi=doi,
                title=title,
                body=body,
                min_title_score=max(0.0, args.min_title_score),
            )
            attempt["validation"] = {key: value for key, value in validation.items() if key != "front_page_text"}
            if not validation["accepted"]:
                attempt["status"] = "identity_rejected"
                attempt["error"] = validation["reason"]
                record["attempts"].append(attempt)
                continue

            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as handle:
                handle.write(body)
                temp_pdf = Path(handle.name)
            try:
                extractions = convert_pdf(
                    pdf_path=temp_pdf,
                    backend="grobid",
                    grobid_url=args.grobid_url,
                    timeout_sec=max(1, args.grobid_timeout_sec),
                    grobid_retries=1,
                    grobid_retry_wait_sec=2,
                )
                row = {
                    "study_doi": doi,
                    "study_title": title,
                    "study_year": clean(meta.get("study_year", "") or candidate.get("study_year", "")),
                    "openalex_id": clean(meta.get("openalex_id", "") or candidate.get("openalex_id", "")),
                    "related_dois": clean(meta.get("related_dois", "")),
                    "publication_relations": clean(meta.get("publication_relations", "")),
                    "published_version_doi": clean(candidate.get("published_version_doi", "")),
                }
                final_pdf = pdf_dir / pdf_filename_for_doi(doi)
                artifact = build_artifact("articles", row, final_pdf, extractions)
                if not artifact.get("best_backend") or int(artifact.get("best_char_count", 0) or 0) < 2000:
                    attempt["status"] = "conversion_rejected"
                    attempt["error"] = "no substantive GROBID extraction"
                    record["attempts"].append(attempt)
                    continue
                parsed_identity = dict(artifact.get("source_identity") or {})
                if not identity_is_verified(parsed_identity):
                    artifact["source_identity"] = {
                        **parsed_identity,
                        "status": "verified_title_only",
                        "verified": True,
                        "basis": "replacement PDF independently matched the requested title on page one",
                        "requested_doi": doi,
                        "requested_title": title,
                        "pdf_front_page_validation": {
                            key: value for key, value in validation.items() if key != "front_page_text"
                        },
                        "parsed_identity_before_repair": parsed_identity,
                    }
                artifact["fulltext_source"] = "validated_pdf_source_identity_repair"
                artifact["source_url"] = url
                artifact["retrieval_endpoint"] = url
                artifact["repair_run_id"] = "source_identity_repair_20260710"
                artifact["repaired_at_utc"] = now_utc()
                artifact["pdf_sha256"] = sha256_bytes(body)

                artifact_path = artifact_dir / f"{doi_to_slug(doi)}.json"
                old_artifact = load_json(artifact_path)
                old_pdf_raw = clean(old_artifact.get("pdf_local_path", ""))
                old_pdf = Path(old_pdf_raw).expanduser() if old_pdf_raw else None
                if old_pdf is not None and not old_pdf.is_absolute():
                    old_pdf = ROOT / old_pdf
                record["artifact_backup_path"] = backup_file(
                    artifact_path,
                    quarantine / "replaced_artifacts" / artifact_path.name,
                )
                if final_pdf.exists() and hashlib.sha256(final_pdf.read_bytes()).digest() != hashlib.sha256(body).digest():
                    record["pdf_backup_path"] = backup_file(
                        final_pdf,
                        quarantine / "replaced_pdfs" / final_pdf.name,
                    )
                if old_pdf is not None and old_pdf.exists() and old_pdf.resolve() != final_pdf.resolve():
                    backup_file(old_pdf, quarantine / "replaced_pdfs" / old_pdf.name)
                final_pdf.parent.mkdir(parents=True, exist_ok=True)
                final_pdf.write_bytes(body)
                write_json(artifact_path, artifact)
                record["status"] = "replaced_validated_pdf"
                record["selected_url"] = url
                record["pdf_path"] = str(final_pdf)
                record["source_identity_status"] = clean((artifact.get("source_identity") or {}).get("status", ""))
                attempt["status"] = "accepted"
                record["attempts"].append(attempt)
                break
            finally:
                temp_pdf.unlink(missing_ok=True)

        counts[record["status"]] += 1
        records.append(record)
        if args.progress_every > 0 and (position % args.progress_every == 0 or position == len(selected)):
            print(
                f"PROGRESS: {position}/{len(selected)} repaired={counts['replaced_validated_pdf']} "
                f"not_repaired={counts['not_repaired']}",
                flush=True,
            )

    report = {
        "generated_at_utc": now_utc(),
        "apply": bool(args.apply),
        "inputs": {
            "audit": str(Path(args.audit).resolve()),
            "metadata_table": str(Path(args.metadata_table).resolve()),
            "candidate_table": str(Path(args.candidate_table).resolve()),
        },
        "counts": {
            "audit_rows": len(audit.get("rows", [])),
            "selected": len(selected),
            "skipped_dedicated_path": len(skipped),
            **dict(counts),
        },
        "skipped": skipped,
        "records": records,
    }
    write_json(Path(args.report).resolve(), report)
    print(json.dumps(report["counts"], indent=2))
    print(f"Report: {Path(args.report).resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
