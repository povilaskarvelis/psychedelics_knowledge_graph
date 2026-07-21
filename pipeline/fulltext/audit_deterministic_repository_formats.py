#!/usr/bin/env python3
"""Identify ineligible formats from stable DOI, metadata, and repository URL signals."""

from __future__ import annotations

import argparse
from collections import Counter
import datetime as dt
import json
from pathlib import Path
import re

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "data" / "processed" / "corpus"
AUDITS = CORPUS / "audits"
DEFAULT_CANDIDATE = CORPUS / "candidate_papers.parquet"
DEFAULT_OUTPUT = AUDITS / "deterministic_repository_format_audit.csv"
DEFAULT_REPORT = AUDITS / "deterministic_repository_format_audit.json"

URL_COLUMNS = (
    "open_access_url",
    "best_pdf_url",
    "pdf_url_candidates",
    "probable_pdf_url_candidates",
    "other_url_candidates",
)
BMJ_CODED_TITLE_RE = re.compile(
    r"^\s*(?:P|O|OP|PL)\d+(?:[-.]S?\d+)*(?:\s|[\u2000-\u206f])",
    re.IGNORECASE,
)
BMJ_SUPPLEMENT_DOI_RE = re.compile(r"^10\.1136/sextrans-.+\.\d+$", re.IGNORECASE)
SUPPLEMENT_PAGE_RE = re.compile(
    r"/(?:a|s|ii|iii)\d+(?:\.\d+)?(?:\.(?:full|abstract))?(?:\.pdf)?(?:[?#]|$)",
    re.IGNORECASE,
)
CODED_ABSTRACT_TITLE_RE = re.compile(
    r"^\s*(?:"
    r"\d{2,4}\s+|"
    r"(?:P|PS|POS|OR|OP|PL|SA|T|A|B)\s*[-:]?\s*\d+(?:[-.]\d+)*\b|"
    r"\d+[A-Z]{2,5}-\d+\b|"
    r"Speaker\s+\d+\s*:"
    r")",
    re.IGNORECASE,
)
OUP_SUPPLEMENT_DOI_RE = re.compile(r"^10\.1093/[^/]+/[^/]+\.\d+$", re.IGNORECASE)
ELSEVIER_CODED_ABSTRACT_DOI_RE = re.compile(
    r"^10\.1016/(?:j\.(?:artres|cont|jalz|jtho|respe|schres|toxlet|yebeh)\.|"
    r"s(?:0378-4274|0924-9338|0924-977x|0928-0987|1353-8020))",
    re.IGNORECASE,
)
STRONG_CODED_ABSTRACT_TITLE_RE = re.compile(
    r"^\s*(?:P\d+[\-‐‑–.]\d+\s*[:\u2000-\u206f]?|\d{2,4}\s*[-–—]\s+)",
    re.IGNORECASE,
)


def clean(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip()


def normalize_doi(value: object) -> str:
    text = clean(value).lower()
    return re.sub(r"^https?://(?:dx\.)?doi\.org/", "", text).rstrip(".,; ")


def split_types(value: object) -> set[str]:
    return {part.strip().lower() for part in clean(value).split("|") if part.strip()}


def truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return clean(value).lower() in {"1", "true", "yes", "y"}


def current_retained_scope(candidate: pd.DataFrame) -> pd.DataFrame:
    """Limit the operational audit to records still active after earlier stages."""

    mask = pd.Series(True, index=candidate.index)
    if "retained_for_extraction_candidate" in candidate.columns:
        mask &= candidate["retained_for_extraction_candidate"].map(truthy)
    if "post_retrieval_decision" in candidate.columns:
        mask &= candidate["post_retrieval_decision"].map(clean).str.lower().ne("exclude")
    return candidate.loc[mask].copy()


def combined_urls(row: dict) -> str:
    return "|".join(clean(row.get(column, "")) for column in URL_COLUMNS).lower()


def classify_record(row: dict) -> dict | None:
    doi = normalize_doi(row.get("doi", ""))
    title = re.sub(r"<[^>]+>", "", clean(row.get("study_title", ""))).strip()
    journal = clean(row.get("study_journal", ""))
    publication_types = split_types(row.get("publication_type", ""))
    urls = combined_urls(row)

    if publication_types.intersection({"dissertation", "thesis"}):
        return {
            "publication_format": "dissertation_or_thesis",
            "rule_id": "thesis_or_dissertation_publication_type",
            "format_evidence": f"Bibliographic publication_type={clean(row.get('publication_type', ''))}",
        }

    if publication_types.intersection({"conference poster", "poster", "poster abstract"}):
        return {
            "publication_format": "conference_poster",
            "rule_id": "poster_publication_type",
            "format_evidence": f"Bibliographic publication_type={clean(row.get('publication_type', ''))}",
        }

    if publication_types.intersection({"conference abstract", "conference-abstract", "meeting abstract"}):
        return {
            "publication_format": "conference_abstract",
            "rule_id": "conference_abstract_publication_type",
            "format_evidence": f"Bibliographic publication_type={clean(row.get('publication_type', ''))}",
        }

    if (
        publication_types.intersection({"preprint", "posted-content"})
        or doi.startswith("10.31235/osf.io/")
    ):
        return {
            "publication_format": "preprint_or_unpublished",
            "rule_id": "preprint_publication_type_or_doi",
            "format_evidence": (
                f"Preprint DOI/metadata: doi={doi}; "
                f"publication_type={clean(row.get('publication_type', ''))}"
            ),
        }

    if publication_types.intersection({"letter", "correspondence"}):
        return {
            "publication_format": "correspondence_or_letter",
            "rule_id": "letter_or_correspondence_publication_type",
            "format_evidence": f"Bibliographic publication_type={clean(row.get('publication_type', ''))}",
        }

    if publication_types.intersection({"comment", "commentary", "editorial", "response"}):
        return {
            "publication_format": "commentary_or_editorial",
            "rule_id": "commentary_or_editorial_publication_type",
            "format_evidence": f"Bibliographic publication_type={clean(row.get('publication_type', ''))}",
        }

    vcu_etd = (
        doi.startswith("10.25772/")
        or "scholarscompass.vcu.edu/etd/" in urls
        or ("scholarscompass.vcu.edu/cgi/viewcontent.cgi" in urls and "context=etd" in urls)
    )
    if vcu_etd:
        return {
            "publication_format": "dissertation_or_thesis",
            "rule_id": "vcu_scholars_compass_etd",
            "format_evidence": (
                f"VCU Scholars Compass ETD identifier/route: doi={doi}; urls={urls or 'not retained'}"
            ),
        }

    ubc_thesis = (
        doi.startswith("10.14288/1.")
        or "/collections/ubctheses/" in urls
        or "/media/download/pdf/831/" in urls
    )
    if ubc_thesis:
        return {
            "publication_format": "dissertation_or_thesis",
            "rule_id": "ubc_thesis_collection_route",
            "format_evidence": f"UBC thesis-collection route: {urls}",
        }

    if doi.startswith("10.17632/") or journal.lower() == "mendeley data":
        return {
            "publication_format": "dataset_or_data_deposit",
            "rule_id": "mendeley_data_or_dataset_metadata",
            "format_evidence": (
                f"Dataset identifier/metadata: doi={doi}; publication_type={clean(row.get('publication_type', ''))}; "
                f"journal={journal}"
            ),
        }

    if publication_types.intersection({"book", "monograph"}):
        return {
            "publication_format": "book_or_monograph",
            "rule_id": "book_publication_type",
            "format_evidence": f"Bibliographic publication_type={clean(row.get('publication_type', ''))}",
        }

    if doi.startswith("10.26226/morressier."):
        return {
            "publication_format": "conference_abstract",
            "rule_id": "morressier_conference_deposit",
            "format_evidence": f"Morressier conference-content DOI: doi={doi}; title={title}",
        }

    if ELSEVIER_CODED_ABSTRACT_DOI_RE.search(doi) and STRONG_CODED_ABSTRACT_TITLE_RE.search(title):
        return {
            "publication_format": "conference_abstract",
            "rule_id": "coded_journal_conference_abstract",
            "format_evidence": f"Coded journal-abstract title and DOI family: doi={doi}; title={title}",
        }

    bmj_supplement_url = (
        (".bmj.com/" in urls or "//bmj.com/" in urls)
        and "/suppl_" in urls
        and SUPPLEMENT_PAGE_RE.search(urls)
    )
    bmj_coded_doi = BMJ_SUPPLEMENT_DOI_RE.search(doi) and BMJ_CODED_TITLE_RE.search(title)
    oup_supplement_url = "academic.oup.com/" in urls and (
        "/suppl_" in urls or "/supplement_" in urls
    )
    oup_abstract = oup_supplement_url and (
        OUP_SUPPLEMENT_DOI_RE.search(doi) or CODED_ABSTRACT_TITLE_RE.search(title)
    )
    coded_supplement_abstract = (
        ("/suppl_" in urls or "/supplement_" in urls)
        and CODED_ABSTRACT_TITLE_RE.search(title)
    )
    if bmj_supplement_url or bmj_coded_doi or oup_abstract or coded_supplement_abstract:
        return {
            "publication_format": "conference_abstract",
            "rule_id": "supplement_issue_conference_abstract",
            "format_evidence": f"Supplement issue/coded abstract signal: doi={doi}; title={title}; urls={urls}",
        }

    return None


def build_audit(candidate: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    for raw in candidate.fillna("").to_dict("records"):
        doi = normalize_doi(raw.get("doi", ""))
        if not doi:
            continue
        result = classify_record(raw)
        if not result:
            continue
        rows.append(
            {
                "doi": doi,
                "study_title": clean(raw.get("study_title", "")),
                "recommended_action": "exclude_publication_format",
                **result,
                "decision_method": "deterministic_repository_and_identifier_rule_v1",
                "reviewer": "pipeline_rule",
            }
        )
    return pd.DataFrame(rows).drop_duplicates("doi", keep="last")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-table", default=str(DEFAULT_CANDIDATE))
    parser.add_argument("--output-csv", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--report-json", default=str(DEFAULT_REPORT))
    args = parser.parse_args()

    candidate_path = Path(args.candidate_table).resolve()
    columns = [
        "doi",
        "study_title",
        "study_journal",
        "publication_type",
        "retained_for_extraction_candidate",
        "post_retrieval_decision",
        *URL_COLUMNS,
    ]
    candidate = pd.read_parquet(candidate_path, columns=columns).fillna("")
    scoped_candidate = current_retained_scope(candidate)
    audit = build_audit(scoped_candidate)
    output = Path(args.output_csv).resolve()
    report_path = Path(args.report_json).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    audit.to_csv(output, index=False)
    report = {
        "schema_version": "deterministic_repository_format_audit_v1",
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "candidate_rows": len(candidate),
        "retained_not_post_retrieval_excluded_rows": len(scoped_candidate),
        "excluded_rows": len(audit),
        "format_counts": dict(Counter(audit.get("publication_format", []))),
        "rule_counts": dict(Counter(audit.get("rule_id", []))),
        "output_csv": str(output),
    }
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
