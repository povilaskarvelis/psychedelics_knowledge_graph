#!/usr/bin/env python3
"""Audit browser-retrieved PDFs for identity and ineligible publication formats."""

from __future__ import annotations

import argparse
from collections import Counter
import datetime as dt
import json
from pathlib import Path
import re

import pandas as pd
from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INBOX = ROOT / "data" / "raw" / "papers" / "manual_pdf_inbox"
DEFAULT_BROWSER_REPORT = (
    ROOT
    / "data"
    / "processed"
    / "corpus"
    / "audits"
    / "doi_browser_pdf_recovery_new_doi_full_20260719_v1.json"
)
DEFAULT_IMPORT_REPORT = (
    ROOT
    / "data"
    / "processed"
    / "corpus"
    / "audits"
    / "doi_browser_pdf_import_full_20260719_v1_dry_run.json"
)
DEFAULT_QUEUE_CSV = (
    ROOT / "data" / "processed" / "corpus" / "audits" / "manual_pdf_download_dois.csv"
)
DEFAULT_CANDIDATE_TABLE = ROOT / "data" / "processed" / "corpus" / "candidate_papers.parquet"
DEFAULT_OUTPUT_CSV = (
    ROOT
    / "data"
    / "processed"
    / "corpus"
    / "audits"
    / "doi_browser_pdf_publication_format_audit.csv"
)
DEFAULT_REPORT_JSON = DEFAULT_OUTPUT_CSV.with_suffix(".json")

DOI_PATTERN = re.compile(r"10\.\d{4,9}/[-._;()/:a-z0-9]+", re.IGNORECASE)
MEETING_PATTERN = re.compile(
    r"\b(?:conference|congress|annual meeting|scientific meeting|poster session|meeting abstracts?)\b",
    re.IGNORECASE,
)
THESIS_PATTERN = re.compile(
    r"\b(?:a thesis submitted|doctoral dissertation|doctoral thesis|master(?:'s)? thesis|"
    r"submitted in partial fulfil?ment|requirements for the degree)\b",
    re.IGNORECASE,
)


def clean(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def normalized_doi(value: object) -> str:
    text = clean(value).lower()
    text = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", text)
    text = re.sub(r"^doi:\s*", "", text)
    return text


def identity_by_filename(payload: dict) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for row in payload.get("imported", []):
        out[Path(clean(row.get("file", ""))).name] = {**row, "identity_status": "matched"}
    for row in payload.get("review", []):
        out[Path(clean(row.get("file", ""))).name] = {**row, "identity_status": "needs_review"}
    for row in payload.get("invalid", []):
        out[Path(clean(row.get("file", ""))).name] = {**row, "identity_status": "invalid"}
    return out


def browser_doi_by_filename(payload: dict) -> dict[str, str]:
    out: dict[str, str] = {}
    for row in payload.get("records", []):
        target = Path(clean(row.get("target", ""))).name
        doi = normalized_doi(row.get("doi", ""))
        if target and doi:
            out[target] = doi
    return out


def metadata_by_doi(path: Path, candidate_table: Path) -> dict[str, dict]:
    frame = pd.read_csv(path).fillna("")
    out = {
        normalized_doi(row.get("doi", "")): row
        for row in frame.to_dict("records")
        if normalized_doi(row.get("doi", ""))
    }
    if candidate_table.is_file():
        candidate = pd.read_parquet(candidate_table, columns=["doi", "language"]).fillna("")
        for row in candidate.to_dict("records"):
            doi = normalized_doi(row.get("doi", ""))
            if doi in out:
                out[doi]["language"] = clean(row.get("language", ""))
    return out


def extract_front_text(path: Path, max_pages: int = 4) -> tuple[int, str, str]:
    reader = PdfReader(path)
    page_count = len(reader.pages)
    chunks: list[str] = []
    for page in reader.pages[: min(page_count, max_pages)]:
        try:
            chunks.append(page.extract_text() or "")
        except Exception:
            continue
    text = "\n".join(chunks)
    compact = " ".join(text.split())
    return page_count, text, compact


def audit_file(
    path: Path,
    *,
    identity: dict,
    browser_doi: str,
    metadata: dict,
) -> dict:
    try:
        page_count, front_text, compact = extract_front_text(path)
    except Exception as exc:
        return {
            "file": str(path.resolve()),
            "doi": browser_doi,
            "identity_status": clean(identity.get("identity_status", "invalid")),
            "recommended_action": "quarantine_invalid_pdf",
            "format_evidence": "pdf_read_error",
            "audit_error": str(exc),
        }

    compact_lower = compact.lower()
    first_5000 = compact_lower[:5000]
    distinct_dois = sorted({match.rstrip(".,;:") for match in DOI_PATTERN.findall(compact_lower)})
    evidence: list[str] = []

    abstract_header = bool(re.search(r"(?:^|\n)\s*abstracts?\s*(?:$|\n)", front_text, re.IGNORECASE))
    multiple_dois = page_count <= 3 and len(distinct_dois) >= 2
    meeting_language = page_count <= 4 and bool(MEETING_PATTERN.search(compact_lower[:12000]))
    explicit_meeting_abstract = page_count <= 4 and bool(
        re.search(r"\b(?:open\s+access\s*)?meeting\s+abstract\b", compact_lower[:2500])
    )
    thesis_title_page = bool(THESIS_PATTERN.search(first_5000))
    product_monograph = "product monograph" in first_5000
    reviewer_list = bool(re.search(r"\breviewers\s+20\d{2}\b", first_5000))
    language = clean(metadata.get("language", "")).lower()
    metadata_non_english = bool(language and language not in {"en", "eng", "english"})
    letters = re.findall(r"[^\W\d_]", compact[:12000], flags=re.UNICODE)
    non_latin_letters = re.findall(r"[\u0400-\u052f\u0600-\u06ff\u4e00-\u9fff]", compact[:12000])
    non_latin_document = bool(letters and len(non_latin_letters) / len(letters) >= 0.20)

    if abstract_header and page_count <= 3:
        evidence.append("short_abstracts_document")
    if multiple_dois:
        evidence.append("short_multiple_dois")
    if meeting_language:
        evidence.append("short_meeting_language")
    if explicit_meeting_abstract:
        evidence.append("explicit_meeting_abstract_label")
    if thesis_title_page:
        evidence.append("thesis_title_page")
    if product_monograph:
        evidence.append("product_monograph")
    if reviewer_list:
        evidence.append("reviewer_list")
    if metadata_non_english:
        evidence.append(f"metadata_language={language}")
    if non_latin_document:
        evidence.append("predominantly_non_latin_document")

    identity_status = clean(identity.get("identity_status", "unclassified"))
    if product_monograph or reviewer_list:
        action = "quarantine_wrong_document"
        publication_format = "wrong_document"
    elif thesis_title_page:
        action = "exclude_publication_format"
        publication_format = "dissertation_or_thesis"
    elif explicit_meeting_abstract or multiple_dois or (abstract_header and meeting_language):
        action = "exclude_publication_format"
        publication_format = "conference_abstract"
    elif identity_status != "matched":
        action = "quarantine_identity_review"
        publication_format = ""
    elif metadata_non_english or non_latin_document:
        action = "exclude_publication_format"
        publication_format = "non_english_article"
    elif meeting_language:
        action = "review_publication_format"
        publication_format = "possible_conference_abstract"
    else:
        action = "import_validated_article_pdf"
        publication_format = "eligible_article_or_review"

    doi = browser_doi or normalized_doi(identity.get("doi", ""))
    excerpt = compact[:800]
    return {
        "file": str(path.resolve()),
        "doi": doi,
        "expected_title": clean(metadata.get("study_title", identity.get("study_title", ""))),
        "source_types": clean(metadata.get("source_types", "")),
        "language": language,
        "identity_status": identity_status,
        "identity_reason": clean(identity.get("reason", identity.get("match_basis", ""))),
        "page_count": page_count,
        "distinct_front_doi_count": len(distinct_dois),
        "format_evidence": "|".join(evidence),
        "publication_format": publication_format,
        "recommended_action": action,
        "evidence_excerpt": excerpt,
        "audit_error": "",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inbox-dir", default=str(DEFAULT_INBOX))
    parser.add_argument("--browser-report", default=str(DEFAULT_BROWSER_REPORT))
    parser.add_argument("--import-report", default=str(DEFAULT_IMPORT_REPORT))
    parser.add_argument("--queue-csv", default=str(DEFAULT_QUEUE_CSV))
    parser.add_argument("--candidate-table", default=str(DEFAULT_CANDIDATE_TABLE))
    parser.add_argument("--output-csv", default=str(DEFAULT_OUTPUT_CSV))
    parser.add_argument("--report-json", default=str(DEFAULT_REPORT_JSON))
    args = parser.parse_args()

    inbox = Path(args.inbox_dir).resolve()
    identities = identity_by_filename(load_json(Path(args.import_report).resolve()))
    browser_dois = browser_doi_by_filename(load_json(Path(args.browser_report).resolve()))
    metadata = metadata_by_doi(Path(args.queue_csv).resolve(), Path(args.candidate_table).resolve())
    rows = []
    for pdf_path in sorted(inbox.glob("*.pdf")):
        doi = browser_dois.get(pdf_path.name, normalized_doi(identities.get(pdf_path.name, {}).get("doi", "")))
        rows.append(
            audit_file(
                pdf_path,
                identity=identities.get(pdf_path.name, {}),
                browser_doi=doi,
                metadata=metadata.get(doi, {}),
            )
        )

    frame = pd.DataFrame(rows)
    output_csv = Path(args.output_csv).resolve()
    report_json = Path(args.report_json).resolve()
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output_csv, index=False)
    report = {
        "schema_version": "retrieved_pdf_publication_format_audit_v1",
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "inputs": {
            "inbox_dir": str(inbox),
            "browser_report": str(Path(args.browser_report).resolve()),
            "import_report": str(Path(args.import_report).resolve()),
            "queue_csv": str(Path(args.queue_csv).resolve()),
            "candidate_table": str(Path(args.candidate_table).resolve()),
        },
        "counts": {
            "files": len(frame),
            "identity_status": dict(Counter(frame.get("identity_status", []))),
            "recommended_action": dict(Counter(frame.get("recommended_action", []))),
            "publication_format": dict(Counter(frame.get("publication_format", []))),
        },
        "output_csv": str(output_csv),
    }
    report_json.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
