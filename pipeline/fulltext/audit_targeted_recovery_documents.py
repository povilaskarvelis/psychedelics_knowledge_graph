#!/usr/bin/env python3
"""Audit targeted-recovery PDFs before they can enter the canonical store.

This is a deliberately staging-only audit.  It reads selected recovery reports,
the candidate table, and the staged PDFs, then writes the v2 browser-recovery
document-audit CSV.  It never moves, imports, quarantines, or updates a PDF or
candidate record.

Repository wrapper DOIs (for example ZORA and ETH Research Collection DOIs)
are not silently promoted as article identities.  When the first page instead
identifies a matching published article DOI, the artifact is retained in the
inbox but marked for alias/identity review.
"""

from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any

import pandas as pd
from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.fulltext.source_identity import (  # noqa: E402
    DOI_RE,
    clean,
    doi_equivalent,
    normalize_doi,
    title_coverage,
)


REPOSITORY_WRAPPER_PREFIXES = ("10.5167/uzh-", "10.3929/ethz-c-")

CSV_COLUMNS = [
    "recovery_pass",
    "report_path",
    "requested_doi",
    "selected_url",
    "selected_via",
    "selected_kind",
    "selected_text",
    "trail",
    "file_path",
    "file_name",
    "file_sha256",
    "file_size_bytes",
    "pdf_page_count",
    "pdf_title_metadata",
    "pdf_author_metadata",
    "pdf_producer_metadata",
    "candidate_matches",
    "expected_title",
    "expected_year",
    "expected_journal",
    "expected_publication_type",
    "expected_language",
    "candidate_alias_status",
    "candidate_alias_of",
    "front_text_extraction_status",
    "front_dois",
    "expected_doi_on_front",
    "foreign_front_dois",
    "front_title_exact",
    "front_title_score",
    "artifact_class",
    "artifact_evidence",
    "identity_basis",
    "final_outcome",
    "recommended_staging_action",
    "duplicate_pdf_group",
    "first_page_excerpt",
    "audit_error",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def report_records(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return payload.get("records") or payload.get("results") or []


def read_report_spec(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise ValueError("--report must use PASS_LABEL=PATH")
    label, raw_path = value.split("=", 1)
    label = clean(label)
    path = Path(raw_path).expanduser().resolve()
    if not label or not path.is_file():
        raise ValueError(f"Invalid report specification: {value}")
    return label, path


def compact(value: object) -> str:
    return " ".join(str(value or "").split())


def front_dois(text: str) -> list[str]:
    output: list[str] = []
    for match in DOI_RE.findall(text):
        doi = normalize_doi(match)
        if doi and doi not in output:
            output.append(doi)
    # Text extraction sometimes emits a DOI twice: once broken at a line wrap
    # (for example ``10.1093/brain/``) and once complete.  The incomplete
    # prefix is not an independent foreign identity signal.
    return [
        doi
        for doi in output
        if not any(
            other != doi
            and other.startswith(doi.rstrip("/"))
            and len(other) > len(doi.rstrip("/"))
            for other in output
        )
    ]


def has_expected_title(expected_title: str, first_page_text: str) -> tuple[bool, float]:
    """Use complete token coverage because PDFs commonly wrap and style titles."""
    score = title_coverage(expected_title, first_page_text)
    return score >= 0.999, score


def is_repository_wrapper_doi(doi: str) -> bool:
    return doi.startswith(REPOSITORY_WRAPPER_PREFIXES)


def read_pdf(path: Path) -> dict[str, object]:
    reader = PdfReader(str(path), strict=False)
    metadata = reader.metadata or {}
    first_page = reader.pages[0].extract_text() or ""
    return {
        "page_count": len(reader.pages),
        "first_page_text": first_page,
        "first_page_compact": compact(first_page),
        "title_metadata": clean(getattr(metadata, "title", "")),
        "author_metadata": clean(getattr(metadata, "author", "")),
        "producer_metadata": clean(getattr(metadata, "producer", "")),
    }


def candidate_map(path: Path) -> dict[str, list[dict[str, object]]]:
    columns = [
        "doi",
        "study_title",
        "study_year",
        "study_journal",
        "publication_type",
        "language",
        "doi_alias_status",
        "doi_alias_of",
    ]
    frame = pd.read_parquet(path, columns=columns).fillna("")
    output: dict[str, list[dict[str, object]]] = {}
    for row in frame.to_dict("records"):
        doi = normalize_doi(row.get("doi", ""))
        if doi:
            output.setdefault(doi, []).append(row)
    return output


def empty_row(*, label: str, report_path: Path, source: dict[str, Any], error: str) -> dict[str, str]:
    doi = normalize_doi(source.get("doi", ""))
    target = clean(source.get("target", ""))
    return {
        "recovery_pass": label,
        "report_path": str(report_path.relative_to(ROOT)),
        "requested_doi": doi,
        "selected_url": clean(source.get("selected_url", "")),
        "selected_via": clean(source.get("selected_via", "")),
        "selected_kind": clean(source.get("selected_kind", "")),
        "selected_text": clean(source.get("selected_text", "")),
        "trail": json.dumps(source.get("trail", []), ensure_ascii=False),
        "file_path": target,
        "file_name": Path(target).name,
        "front_text_extraction_status": "error",
        "artifact_class": "unreadable_or_missing_pdf",
        "artifact_evidence": "PDF could not be read for first-page identity audit.",
        "identity_basis": "PDF audit error",
        "final_outcome": "identity_uncertain",
        "recommended_staging_action": "identity_review",
        "audit_error": error,
    }


def audit_record(
    *,
    label: str,
    report_path: Path,
    source: dict[str, Any],
    candidates: dict[str, list[dict[str, object]]],
) -> dict[str, str]:
    doi = normalize_doi(source.get("doi", ""))
    target = Path(clean(source.get("target", ""))).expanduser()
    matching_candidates = candidates.get(doi, [])
    expected = matching_candidates[0] if matching_candidates else {}
    if not target.is_file():
        return empty_row(
            label=label,
            report_path=report_path,
            source=source,
            error=f"staged file missing: {target}",
        )
    try:
        pdf = read_pdf(target)
    except Exception as exc:  # Audit must record, not crash, on an anomalous PDF.
        return empty_row(label=label, report_path=report_path, source=source, error=str(exc))

    expected_title = clean(expected.get("study_title", ""))
    first_page_text = str(pdf["first_page_text"])
    title_exact, title_score = has_expected_title(expected_title, first_page_text)
    observed_dois = front_dois(first_page_text)
    expected_doi_on_front = any(doi_equivalent(doi, observed) for observed in observed_dois)
    foreign_dois = [observed for observed in observed_dois if not doi_equivalent(doi, observed)]
    repository_wrapper = is_repository_wrapper_doi(doi)

    artifact_class = "article_pdf" if title_exact else "unclassified_pdf"
    if title_exact and repository_wrapper and foreign_dois:
        artifact_evidence = "Repository wrapper DOI plus matching title and a published article DOI on page 1."
        identity_basis = "foreign published DOI with matching title"
        final_outcome = "alias_or_foreign_doi_mismatch"
        action = "identity_review"
    elif title_exact and foreign_dois and not expected_doi_on_front:
        artifact_evidence = "Matching title with a foreign article DOI on page 1."
        identity_basis = "foreign published DOI with matching title"
        final_outcome = "alias_or_foreign_doi_mismatch"
        action = "identity_review"
    elif title_exact and expected_doi_on_front:
        artifact_evidence = "Expected DOI and article title are on page 1."
        identity_basis = "expected DOI and title on front page"
        final_outcome = "valid_article_or_review"
        action = "eligible_for_import"
    elif title_exact:
        artifact_evidence = "Exact expected article title is on page 1."
        identity_basis = "exact expected title on front page"
        final_outcome = "valid_article_or_review"
        action = "eligible_for_import"
    else:
        artifact_evidence = "Could not corroborate the expected title from the first page."
        identity_basis = "first-page identity evidence insufficient"
        final_outcome = "identity_uncertain"
        action = "identity_review"

    return {
        "recovery_pass": label,
        "report_path": str(report_path.relative_to(ROOT)),
        "requested_doi": doi,
        "selected_url": clean(source.get("selected_url", "")),
        "selected_via": clean(source.get("selected_via", "")),
        "selected_kind": clean(source.get("selected_kind", "")),
        "selected_text": clean(source.get("selected_text", "")),
        "trail": json.dumps(source.get("trail", []), ensure_ascii=False),
        "file_path": str(target.resolve()),
        "file_name": target.name,
        "file_sha256": sha256(target),
        "file_size_bytes": str(target.stat().st_size),
        "pdf_page_count": str(pdf["page_count"]),
        "pdf_title_metadata": clean(pdf["title_metadata"]),
        "pdf_author_metadata": clean(pdf["author_metadata"]),
        "pdf_producer_metadata": clean(pdf["producer_metadata"]),
        "candidate_matches": str(len(matching_candidates)),
        "expected_title": expected_title,
        "expected_year": clean(expected.get("study_year", "")),
        "expected_journal": clean(expected.get("study_journal", "")),
        "expected_publication_type": clean(expected.get("publication_type", "")),
        "expected_language": clean(expected.get("language", "")),
        "candidate_alias_status": clean(expected.get("doi_alias_status", "")),
        "candidate_alias_of": clean(expected.get("doi_alias_of", "")),
        "front_text_extraction_status": "ok",
        "front_dois": " | ".join(observed_dois),
        "expected_doi_on_front": str(expected_doi_on_front),
        "foreign_front_dois": " | ".join(foreign_dois),
        "front_title_exact": str(title_exact),
        "front_title_score": f"{title_score:.4f}",
        "artifact_class": artifact_class,
        "artifact_evidence": artifact_evidence,
        "identity_basis": identity_basis,
        "final_outcome": final_outcome,
        "recommended_staging_action": action,
        "duplicate_pdf_group": "",
        "first_page_excerpt": str(pdf["first_page_compact"])[:1500],
        "audit_error": "",
    }


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--report",
        action="append",
        required=True,
        help="Repeat as PASS_LABEL=PATH; only downloaded records are audited.",
    )
    parser.add_argument(
        "--candidate-table",
        default=str(ROOT / "data" / "processed" / "corpus" / "candidate_papers.parquet"),
    )
    parser.add_argument("--output-csv", required=True)
    args = parser.parse_args()

    candidates = candidate_map(Path(args.candidate_table).resolve())
    rows: list[dict[str, str]] = []
    for raw_spec in args.report:
        label, report_path = read_report_spec(raw_spec)
        payload = json.loads(report_path.read_text(encoding="utf-8"))
        for source in report_records(payload):
            if clean(source.get("status", "")) != "downloaded":
                continue
            rows.append(
                audit_record(
                    label=label,
                    report_path=report_path,
                    source=source,
                    candidates=candidates,
                )
            )

    output_csv = Path(args.output_csv).resolve()
    write_csv(output_csv, rows)
    counts = {
        "records": len(rows),
        "by_recovery_pass": dict(sorted(Counter(row["recovery_pass"] for row in rows).items())),
        "by_final_outcome": dict(sorted(Counter(row["final_outcome"] for row in rows).items())),
        "by_recommended_staging_action": dict(
            sorted(Counter(row["recommended_staging_action"] for row in rows).items())
        ),
    }
    print(json.dumps(counts, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
