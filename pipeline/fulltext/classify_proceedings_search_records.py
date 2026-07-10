#!/usr/bin/env python3
"""Classify proceedings-source failures at the search-record level.

Class A is an individual paper, abstract, poster, or session contribution whose
downloaded artifact is a larger container.  Class B is a search record that is
itself an abstract book, supplement, meeting, or proceedings container.  This
audit does not mutate the corpus, artifacts, extraction outputs, or KG.
"""

from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.fulltext.source_identity import clean, normalize_doi, title_similarity  # noqa: E402


DEFAULT_INPUT = ROOT / "outputs" / "source_identity_repair_20260710" / "source_identity_special_classes.csv"
DEFAULT_CANDIDATE_TABLE = ROOT / "data" / "processed" / "corpus" / "candidate_papers.parquet"
DEFAULT_METADATA_TABLE = ROOT / "data" / "processed" / "corpus" / "paper_metadata_enrichment.parquet"
DEFAULT_OUTPUT_CSV = (
    ROOT
    / "outputs"
    / "source_identity_repair_20260710"
    / "proceedings_search_record_classification.csv"
)
DEFAULT_OUTPUT_JSON = DEFAULT_OUTPUT_CSV.with_suffix(".json")


CONTAINER_TITLE_RE = re.compile(
    r"^(?:the\s+)?(?:abstracts?|abstract\s+book|conference\s+abstracts?|"
    r"meeting\s+abstracts?|proceedings|conference\s+proceedings|"
    r"congress\s+proceedings|supplement|table\s+of\s+contents|"
    r"conference\s+program(?:me)?|meeting\s+program(?:me)?)\b"
    r"|^(?:(?:annual|international|world|national)\s+)?"
    r"(?:meeting|conference|congress|symposium)\s+"
    r"(?:abstracts?|proceedings|program(?:me)?)\b",
    flags=re.IGNORECASE,
)


DOI_PATTERNS: list[tuple[str, re.Pattern[str], str, str]] = [
    (
        "cambridge_european_psychiatry_item",
        re.compile(r"^10\.1192/j\.eurpsy\.\d{4}\.\d+$"),
        "individual_conference_or_journal_item",
        "terminal year-and-item number",
    ),
    (
        "oxford_ijnp_item",
        re.compile(r"^10\.1093/ijnp/[a-z0-9]+\.\d+$"),
        "individual_conference_abstract",
        "terminal abstract number after the supplement/article code",
    ),
    (
        "oxford_schizophrenia_bulletin_item",
        re.compile(r"^10\.1093/schbul/[a-z0-9]+(?:\.\d+){1,2}$"),
        "individual_conference_or_journal_item",
        "terminal abstract number or volume-issue-page locator",
    ),
    (
        "oxford_sleep_item",
        re.compile(r"^10\.1093/sleep/[a-z0-9]+(?:\.\d+){1,2}$"),
        "individual_conference_or_journal_item",
        "terminal abstract number or volume-issue-page locator",
    ),
    (
        "cambridge_cts_item",
        re.compile(r"^10\.1017/cts\.\d{4}\.\d+$"),
        "individual_conference_abstract",
        "terminal year-and-item number",
    ),
    (
        "bmj_esra_item",
        re.compile(r"^10\.1136/rapm-\d{4}-esra\.\d+$"),
        "individual_expert_session_contribution",
        "terminal ESRA contribution number",
    ),
    (
        "endocrine_society_item",
        re.compile(r"^10\.1210/jendso/[a-z0-9]+\.\d+$"),
        "individual_conference_abstract",
        "terminal presentation number after the supplement code",
    ),
    (
        "dual_disorders_abstract_item",
        re.compile(r"^10\.17579/abstractbookdualdisorders-(?:co|p|cr)-\d+$"),
        "individual_abstract_book_entry",
        "explicit oral/poster/case item code and number",
    ),
    (
        "rowan_research_day_item",
        re.compile(r"^10\.31986/issn\.[a-z0-9._-]+\.\d+_\d{4}$"),
        "individual_research_day_item",
        "terminal repository item number and year",
    ),
    (
        "acta_supplement_article",
        re.compile(r"^10\.56126/\d+\.s\d+\.\d+$"),
        "individual_supplement_article",
        "terminal article number within the supplement",
    ),
    (
        "elsevier_european_psychiatry_item",
        re.compile(r"^10\.1016/j\.eurpsy\.\d{4}\.\d+\.\d+$"),
        "individual_conference_or_journal_item",
        "journal article sequence ending in an item number",
    ),
    (
        "elsevier_pii_item",
        re.compile(r"^10\.1016/s0924-9338\(\d{2}\)\d{5}-\d$"),
        "individual_conference_or_journal_item",
        "individual Elsevier PII-based DOI",
    ),
]


CSV_COLUMNS = [
    "doi",
    "search_record_class",
    "search_record_class_label",
    "recommended_action",
    "remove_as_container",
    "classification_confidence",
    "record_level_form",
    "doi_pattern_family",
    "doi_individual_locator_evidence",
    "requested_title",
    "study_year",
    "study_journal",
    "publication_type",
    "authors",
    "abstract_present",
    "abstract_char_count",
    "abstract_excerpt",
    "metadata_provider",
    "metadata_provider_chain",
    "title_container_signal",
    "title_matches_manifest",
    "artifact_identity_status",
    "artifact_document_doi",
    "artifact_document_title",
    "artifact_title_similarity",
    "target_title_exact_in_artifact",
    "target_doi_literal_in_artifact",
    "current_kg_finding_count",
    "artifact_scope_assessment",
    "decision_reason",
    "caveats",
    "separate_evidence_screening_note",
]


def load_table(path: Path) -> dict[str, dict]:
    rows = pd.read_parquet(path).fillna("").to_dict("records")
    return {
        doi: row
        for row in rows
        if (doi := normalize_doi(row.get("doi", "") or row.get("study_doi", "")))
    }


def doi_pattern(doi: str) -> tuple[str, str, str]:
    for family, pattern, record_form, evidence in DOI_PATTERNS:
        if pattern.fullmatch(doi):
            return family, record_form, evidence
    return "unrecognized", "uncertain", "no recognized per-item DOI locator"


def bool_value(value: object) -> bool:
    return clean(value).casefold() in {"1", "true", "yes"}


def int_value(value: object) -> int:
    try:
        return int(float(clean(value) or 0))
    except ValueError:
        return 0


def artifact_scope_assessment(source: dict) -> str:
    status = clean(source.get("identity_status", ""))
    title_exact = bool_value(source.get("target_title_exact_in_artifact", ""))
    doi_literal = bool_value(source.get("target_doi_literal_in_artifact", ""))
    if status == "verified_exact_doi":
        return "target item is present, but the acquired file was identified as a multi-item container"
    if title_exact and doi_literal:
        return "container includes the target item, while its header or opening item identifies another contribution"
    if title_exact:
        return "container text includes the target title, but document-level DOI identity is not isolated"
    return "acquired file does not reliably isolate the target item from the larger container"


def classify_record(source: dict, candidate: dict, metadata: dict) -> dict:
    doi = normalize_doi(source.get("doi", ""))
    title = clean(candidate.get("study_title", "") or source.get("requested_title", ""))
    abstract = clean(candidate.get("abstract", "") or metadata.get("abstract", ""))
    family, record_form, locator_evidence = doi_pattern(doi)
    container_title = bool(CONTAINER_TITLE_RE.search(title))
    individual_doi = family != "unrecognized"

    # Removal is intentionally high precision: a container-level title and no
    # per-item DOI locator are both required.  Ambiguity defaults to retention
    # for manual review rather than destructive removal.
    if container_title and not individual_doi:
        record_class = "B"
        confidence = "high"
        action = "remove_search_record_as_container"
        class_label = "B_record_is_proceedings_or_supplement_container"
        decision_reason = (
            "The search title names a container and the DOI lacks a per-item locator; "
            "the record itself is not an individual contribution."
        )
    else:
        record_class = "A"
        action = "retain_search_record_and_reacquire_or_slice_exact_item_text"
        class_label = "A_individual_record_with_container_artifact"
        decision_reason = (
            f"The DOI has a {locator_evidence}; the title names a specific contribution; "
            f"and metadata supplies {'an individual abstract' if abstract else 'an item-level record'}. "
            "The whole-proceedings problem belongs to the downloaded artifact, not the search record."
        )
        confidence = "high" if individual_doi and title and abstract and not container_title else "medium"

    caveats: list[str] = []
    if doi.startswith("10.17579/abstractbookdualdisorders-"):
        confidence = "medium"
        caveats.append(
            "OpenAlex abstract/author metadata appears copied from a neighboring abstract; "
            "classification relies on the distinct registered title and explicit per-item CO/P code."
        )
    if re.match(r"^speaker\s+\d+\s*:", title, flags=re.IGNORECASE):
        confidence = "medium"
        record_form = "individual_symposium_contribution"
        caveats.append(
            "This is an individual speaker/session contribution rather than a conventional research paper."
        )
    if record_form == "individual_expert_session_contribution":
        caveats.append(
            "This is an individually DOI-registered expert-session contribution; its evidence type still needs separate review."
        )
    if not abstract:
        caveats.append("No abstract metadata was available; retain conservatively for manual record-level review.")
    elif len(abstract) < 200:
        caveats.append("The available abstract metadata is unusually short or incomplete.")
    if family == "unrecognized":
        caveats.append("DOI did not match a known per-item pattern; removal still requires positive container-level evidence.")

    manifest_title = clean(source.get("requested_title", ""))
    manifest_similarity = title_similarity(title, manifest_title)
    metadata_provider = clean(metadata.get("metadata_provider", "") or candidate.get("metadata_provider", ""))
    metadata_chain = clean(
        metadata.get("metadata_provider_chain", "") or candidate.get("metadata_provider_chain", "")
    )
    return {
        "doi": doi,
        "search_record_class": record_class,
        "search_record_class_label": class_label,
        "recommended_action": action,
        "remove_as_container": record_class == "B",
        "classification_confidence": confidence,
        "record_level_form": record_form,
        "doi_pattern_family": family,
        "doi_individual_locator_evidence": locator_evidence,
        "requested_title": title,
        "study_year": clean(candidate.get("study_year", "") or metadata.get("study_year", "")),
        "study_journal": clean(candidate.get("study_journal", "") or metadata.get("study_journal", "")),
        "publication_type": clean(
            candidate.get("publication_type", "") or metadata.get("publication_type", "")
        ),
        "authors": clean(candidate.get("authors", "") or metadata.get("authors", "")),
        "abstract_present": bool(abstract),
        "abstract_char_count": len(abstract),
        "abstract_excerpt": abstract[:500],
        "metadata_provider": metadata_provider,
        "metadata_provider_chain": metadata_chain,
        "title_container_signal": container_title,
        "title_matches_manifest": bool(manifest_similarity is not None and manifest_similarity >= 0.9),
        "artifact_identity_status": clean(source.get("identity_status", "")),
        "artifact_document_doi": normalize_doi(source.get("document_doi", "")),
        "artifact_document_title": clean(source.get("document_title", "")),
        "artifact_title_similarity": source.get("title_similarity_header", ""),
        "target_title_exact_in_artifact": bool_value(source.get("target_title_exact_in_artifact", "")),
        "target_doi_literal_in_artifact": bool_value(source.get("target_doi_literal_in_artifact", "")),
        "current_kg_finding_count": int_value(source.get("current_kg_finding_count", 0)),
        "artifact_scope_assessment": artifact_scope_assessment(source),
        "decision_reason": decision_reason,
        "caveats": " ".join(caveats),
        "separate_evidence_screening_note": (
            "Class A means only that this is not a container search record. "
            "Study design, publication type, relevance, and extractability still require ordinary screening."
        ),
    }


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--candidate-table", default=str(DEFAULT_CANDIDATE_TABLE))
    parser.add_argument("--metadata-table", default=str(DEFAULT_METADATA_TABLE))
    parser.add_argument("--output-csv", default=str(DEFAULT_OUTPUT_CSV))
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    args = parser.parse_args()

    input_path = Path(args.input).resolve()
    source_rows = [
        row
        for row in csv.DictReader(input_path.open(encoding="utf-8"))
        if clean(row.get("classification", "")) == "proceedings_container"
    ]
    if len(source_rows) != 213:
        raise ValueError(f"Expected 213 proceedings_container rows, found {len(source_rows)}")
    if len({normalize_doi(row.get("doi", "")) for row in source_rows}) != len(source_rows):
        raise ValueError("Proceedings search-record input contains duplicate or invalid DOIs")

    candidates = load_table(Path(args.candidate_table).resolve())
    metadata = load_table(Path(args.metadata_table).resolve())
    missing_candidates = [row["doi"] for row in source_rows if normalize_doi(row["doi"]) not in candidates]
    if missing_candidates:
        raise ValueError(f"Missing canonical candidate metadata for {len(missing_candidates)} rows")

    records = [
        classify_record(
            row,
            candidates[normalize_doi(row["doi"])],
            metadata.get(normalize_doi(row["doi"]), {}),
        )
        for row in source_rows
    ]
    records.sort(key=lambda row: row["doi"])
    unrecognized = [row["doi"] for row in records if row["doi_pattern_family"] == "unrecognized"]
    if unrecognized:
        raise ValueError(f"Unrecognized DOI item patterns require manual classification: {unrecognized}")

    output_csv = Path(args.output_csv).resolve()
    output_json = Path(args.output_json).resolve()
    write_csv(output_csv, records)
    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": (
            "Search-record classification of the 213 rows whose current full-text artifact is a "
            "proceedings or multi-abstract container."
        ),
        "class_definitions": {
            "A": "legitimate individual record whose downloaded artifact is a larger container",
            "B": "record itself is an abstract-book, supplement, meeting, or proceedings container",
        },
        "conservative_removal_policy": (
            "Class B requires positive container-title evidence and absence of a recognized per-item DOI locator. "
            "Ambiguity defaults to retention/manual review, not removal."
        ),
        "input_record_count": len(records),
        "class_counts": dict(Counter(row["search_record_class"] for row in records)),
        "confidence_counts": dict(Counter(row["classification_confidence"] for row in records)),
        "record_level_form_counts": dict(Counter(row["record_level_form"] for row in records)),
        "doi_pattern_family_counts": dict(Counter(row["doi_pattern_family"] for row in records)),
        "publication_type_counts": dict(Counter(row["publication_type"] for row in records)),
        "journal_counts": dict(Counter(row["study_journal"] for row in records)),
        "metadata_provider_counts": dict(Counter(row["metadata_provider"] for row in records)),
        "artifact_identity_status_counts": dict(Counter(row["artifact_identity_status"] for row in records)),
        "title_container_signal_count": sum(bool(row["title_container_signal"]) for row in records),
        "title_matches_manifest_count": sum(bool(row["title_matches_manifest"]) for row in records),
        "abstract_present_count": sum(bool(row["abstract_present"]) for row in records),
        "remove_as_container_count": sum(bool(row["remove_as_container"]) for row in records),
        "current_kg_finding_count_total": sum(row["current_kg_finding_count"] for row in records),
        "interpretation": (
            "No row met the high-precision Class B removal rule. Every search record has an individual-level DOI "
            "locator, a specific contribution title, and nonempty abstract metadata. Artifact failures must be "
            "repaired by exact-item acquisition or slicing rather than deleting these search records."
        ),
        "records": records,
    }
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "output_csv": str(output_csv),
                "output_json": str(output_json),
                "record_count": len(records),
                "class_counts": payload["class_counts"],
                "confidence_counts": payload["confidence_counts"],
                "remove_as_container_count": payload["remove_as_container_count"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
