#!/usr/bin/env python3
"""Run deterministic title/abstract pre-screening on the unified corpus tables."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Iterable

import pandas as pd

try:
    from pipeline.ingest.preprint_detection import classify_publication_stage
    from pipeline.review.deterministic_prescreen_rules import (
        deterministic_prescreen_decision,
        normalize_doi,
        normalize_routing_tags,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from pipeline.ingest.preprint_detection import classify_publication_stage
    from pipeline.review.deterministic_prescreen_rules import (
        deterministic_prescreen_decision,
        normalize_doi,
        normalize_routing_tags,
    )


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CORPUS_DIR = ROOT / "data" / "processed" / "corpus"
DEFAULT_PAPERS_TABLE = DEFAULT_CORPUS_DIR / "candidate_papers.parquet"
DEFAULT_METADATA_TABLE = DEFAULT_CORPUS_DIR / "paper_metadata_enrichment.parquet"
DEFAULT_CONTEXTS_TABLE = DEFAULT_CORPUS_DIR / "candidate_contexts.parquet"
DEFAULT_DECISIONS_TABLE = DEFAULT_CORPUS_DIR / "paper_prescreen_decisions.parquet"
DEFAULT_SUMMARY_TABLE = DEFAULT_CORPUS_DIR / "paper_prescreen_summary.parquet"
DEFAULT_CURATED_PUBLICATION_FORMAT_EXCLUSIONS = (
    ROOT / "data" / "curated" / "prescreen_publication_format_exclusions.json"
)
DEFAULT_CURATED_PAPER_METADATA_OVERRIDES = (
    ROOT / "data" / "curated" / "paper_metadata_overrides.json"
)
TABLE_VERSION = "0.1"
METADATA_FIELDS = [
    "study_title",
    "study_year",
    "authors",
    "abstract",
    "study_journal",
    "publication_type",
    "publication_date",
    "pmid",
    "pmcid",
    "openalex_id",
    "semantic_scholar_id",
    "trial_registry_ids",
    "mesh_terms",
    "keywords",
    "publisher",
    "language",
    "metadata_enrichment_status",
    "metadata_enrichment_run_id",
]

NON_PAPER_CONTAINER_PUBLICATION_TYPES = {
    "component",
    "journal",
    "journal-issue",
    "journal-volume",
    "paratext",
    "proceedings-series",
    "report-component",
}
NON_SOURCE_PUBLICATION_TYPES = {
    "book chapter",
    "book-chapter",
    "chapter",
    "comment",
    "commentary",
    "conference abstract",
    "conference-abstract",
    "dissertation",
    "dispatch",
    "editorial",
    "insight",
    "insight article",
    "introductory journal article",
    "letter",
    "meeting abstract",
    "news",
    "newspaper article",
    "poster abstract",
    "perspective",
    "thesis",
    "viewpoint",
    "visual essay",
}
OUT_OF_SCOPE_PUBLICATION_FORMAT_TYPES = {
    "abstract book entry": "conference_abstract",
    "book chapter": "book_chapter",
    "book-chapter": "book_chapter",
    "chapter": "book_chapter",
    "conference abstract": "conference_abstract",
    "conference-abstract": "conference_abstract",
    "commentary": "commentary",
    "dissertation": "dissertation",
    "dispatch": "commentary",
    "insight": "commentary",
    "insight article": "commentary",
    "meeting abstract": "conference_abstract",
    "perspective": "commentary",
    "poster abstract": "conference_abstract",
    "thesis": "dissertation",
    "viewpoint": "commentary",
    "visual essay": "visual_essay",
}
OUT_OF_SCOPE_PUBLICATION_FORMAT_DOI_PATTERNS = (
    (
        re.compile(r"^10\.1093/ijnp/[a-z]{4}\d{3}\.\d{1,4}$", re.IGNORECASE),
        "conference_abstract",
    ),
    (
        re.compile(r"^10\.1007/7854_\d{4}_\d+$", re.IGNORECASE),
        "book_chapter",
    ),
    (
        re.compile(r"^10\.17579/abstractbook", re.IGNORECASE),
        "conference_abstract",
    ),
)
VISUAL_ESSAY_TEXT_RE = re.compile(r"\bvisual essay\b", re.IGNORECASE)
NON_EVIDENCE_TITLE_PATTERNS = (
    re.compile(r"\bauthor correction\b", re.IGNORECASE),
    re.compile(r"\bcorrection:\b", re.IGNORECASE),
    re.compile(r"\berratum\b", re.IGNORECASE),
    re.compile(r"\bcorrigendum\b", re.IGNORECASE),
    re.compile(r"\bdecision letter for\b", re.IGNORECASE),
    re.compile(r"\breview for [\"“]", re.IGNORECASE),
    re.compile(r"\bfaculty opinions recommendation\b", re.IGNORECASE),
    re.compile(r"\bsupplementary material for\b", re.IGNORECASE),
    re.compile(r"\bstudy protocol\b", re.IGNORECASE),
    re.compile(r"\btrial protocol\b", re.IGNORECASE),
    re.compile(r"\bprotocol for\b", re.IGNORECASE),
    re.compile(r"\bstudy flow chart\b", re.IGNORECASE),
    re.compile(r"\bconsort diagram\b", re.IGNORECASE),
    re.compile(r"\bstudy-related adverse events\b", re.IGNORECASE),
    re.compile(r"\bsupporting information\b", re.IGNORECASE),
    re.compile(r"\bsupplementary information\b", re.IGNORECASE),
    re.compile(r"\bsupplemental information\b", re.IGNORECASE),
    re.compile(r"\bsupplementary table\b", re.IGNORECASE),
    re.compile(r"\bsupplemental table\b", re.IGNORECASE),
    re.compile(r"\btable\s*\d+[_:]", re.IGNORECASE),
    re.compile(r"\.xlsx\b", re.IGNORECASE),
    re.compile(r"\bprism file\b", re.IGNORECASE),
)
NON_EVIDENCE_PUBLICATION_PATTERNS = (
    re.compile(r"\bpublished erratum\b", re.IGNORECASE),
    re.compile(r"\berratum\b", re.IGNORECASE),
    re.compile(r"\bretracted publication\b", re.IGNORECASE),
    re.compile(r"\bretraction\b", re.IGNORECASE),
    re.compile(r"\bclinical trial protocol\b", re.IGNORECASE),
    re.compile(r"\bdataset\b", re.IGNORECASE),
)
NON_EVIDENCE_TEXT_PATTERNS = (
    re.compile(r"\bpatent highlight\b", re.IGNORECASE),
)
NON_EVIDENCE_SOURCE_PATTERNS = (
    re.compile(r"\bbrown university(?: child & adolescent)? psychopharmacology update\b", re.IGNORECASE),
)
NUMBERED_TITLE_TOKEN_RE = re.compile(
    r"^\s*(?P<number>\d{1,4})(?P<sep>[.)\]:])?\s+(?P<rest>\S.*)$",
    re.IGNORECASE,
)
NUMBERED_TITLE_PROTECTED_REST_PATTERNS = (
    re.compile(r"^(?:hz|khz|mhz|ghz)\b", re.IGNORECASE),
    re.compile(r"^(?:mg|ug|µg|μg|g|kg|ml|mL|l)\b", re.IGNORECASE),
    re.compile(r"^(?:years?|months?|weeks?|days?|hours?|minutes?|mins?)\b", re.IGNORECASE),
    re.compile(r"^%|\bpercent\b", re.IGNORECASE),
)
NUMBERED_TITLE_CONFERENCE_TITLE_PATTERNS = (
    re.compile(r"\bannual meeting\b", re.IGNORECASE),
    re.compile(r"\bscientific meeting\b", re.IGNORECASE),
    re.compile(r"\bconference abstracts?\b", re.IGNORECASE),
    re.compile(r"\bconference proceedings?\b", re.IGNORECASE),
    re.compile(r"\bcongress\b", re.IGNORECASE),
    re.compile(r"\bsymposium\b", re.IGNORECASE),
    re.compile(r"\bposter\b", re.IGNORECASE),
)
NUMBERED_TITLE_CONFERENCE_PUBLICATION_PATTERNS = (
    re.compile(r"\bconference\b", re.IGNORECASE),
    re.compile(r"\bmeeting abstract\b", re.IGNORECASE),
    re.compile(r"\bcongress\b", re.IGNORECASE),
    re.compile(r"\bposter\b", re.IGNORECASE),
    re.compile(r"\bproceedings\b", re.IGNORECASE),
)
NUMBERED_TITLE_CONFERENCE_JOURNAL_PATTERNS = (
    re.compile(r"\binternational journal of neuropsychopharmacology\b", re.IGNORECASE),
    re.compile(r"\bcns spectrums\b", re.IGNORECASE),
    re.compile(r"\bjournal of clinical and translational science\b", re.IGNORECASE),
    re.compile(r"\bbiological psychiatry\b", re.IGNORECASE),
    re.compile(r"\beuropean psychiatry\b", re.IGNORECASE),
    re.compile(r"\beuropean journal of pain\b", re.IGNORECASE),
    re.compile(r"\bjournal of urology\b", re.IGNORECASE),
    re.compile(r"\bthe journal of urology\b", re.IGNORECASE),
    re.compile(r"\bjournal of burn care\b", re.IGNORECASE),
    re.compile(r"\bsleep\b", re.IGNORECASE),
    re.compile(r"\bjournal of the international neuropsychological society\b", re.IGNORECASE),
)
NUMBERED_TITLE_CONFERENCE_DOI_PATTERNS = (
    re.compile(r"^10\.1093/(?:ijnp|sleep|jbcr)/[a-z]{4}\d{3}\.\d{1,4}$", re.IGNORECASE),
    re.compile(r"^10\.1017/(?:cts|s1092852920)\.?\d*", re.IGNORECASE),
    re.compile(r"^10\.1016/j\.biopsych\.\d{4}\.\d{2}\.\d{2,4}$", re.IGNORECASE),
    re.compile(r"^10\.1016/s\d{4}-\d{4}\(\d{2}\)\d{5}-\d$", re.IGNORECASE),
    re.compile(r"^10\.1136/[a-z0-9-]+\.\d{1,4}$", re.IGNORECASE),
)
NON_EVIDENCE_DOI_PATTERNS = (
    re.compile(r"^10\.1371/journal\.[^.]+\.\d+\.[fgst]\d+$", re.IGNORECASE),
    re.compile(r"^10\.1021/.+\.s\d+$", re.IGNORECASE),
    re.compile(r"^10\.3389/.+\.s\d+$", re.IGNORECASE),
    re.compile(r"^10\.6084/m9\.figshare", re.IGNORECASE),
)
OUT_OF_SCOPE_ACRONYM_FALSE_POSITIVE_PATTERNS = (
    re.compile(r"\blumpy skin disease\b", re.IGNORECASE),
    re.compile(r"\blumpy skin disease virus\b", re.IGNORECASE),
    re.compile(r"\bLSDV\b", re.IGNORECASE),
)
OUT_OF_SCOPE_PRODUCTION_METHOD_FOCUS_PATTERNS = (
    re.compile(r"\bbiosynthesi[sz](?:e|ed|es|ing|s)?\b", re.IGNORECASE),
    re.compile(r"\bbioproduction\b", re.IGNORECASE),
    re.compile(r"\bmetabolic engineering\b", re.IGNORECASE),
    re.compile(r"\bsynthetic biology\b", re.IGNORECASE),
    re.compile(r"\bheterologous expression\b", re.IGNORECASE),
    re.compile(r"\bfermentation\b", re.IGNORECASE),
    re.compile(r"\bproduction (?:of|methods?|platform|pathway|process)\b", re.IGNORECASE),
    re.compile(r"\bsynthesi[sz](?:e|ed|es|ing|s)? pathway\b", re.IGNORECASE),
)
OUT_OF_SCOPE_PRODUCTION_METHOD_CONTEXT_PATTERNS = (
    re.compile(r"\bEscherichia coli\b", re.IGNORECASE),
    re.compile(r"\bE\.?\s*coli\b", re.IGNORECASE),
    re.compile(r"\byeast\b", re.IGNORECASE),
    re.compile(r"\bSaccharomyces\b", re.IGNORECASE),
    re.compile(r"\bmicrobial\b", re.IGNORECASE),
    re.compile(r"\bbacterial\b", re.IGNORECASE),
    re.compile(r"\bbiocatalys(?:is|t|tic)\b", re.IGNORECASE),
    re.compile(r"\benzyme engineering\b", re.IGNORECASE),
    re.compile(r"\bengineered (?:strain|host|microorganism|microbe|bacterium|yeast)\b", re.IGNORECASE),
)
OUT_OF_SCOPE_BROAD_NPS_BACKGROUND_PATTERNS = (
    re.compile(r"\bbrief history of [\"'‘’]?(?:new|novel) psychoactive substances\b", re.IGNORECASE),
)
PLACEHOLDER_ABSTRACTS = {
    "abstract not available",
    "international audience",
    "no abstract",
    "no abstract available",
    "not available",
}
CITATION_ONLY_ABSTRACT_PATTERNS = (
    re.compile(r"^\(\d{4}\)\.\s+.+\.\s+.+:\s+vol\.\s+\d+", re.IGNORECASE),
    re.compile(
        r"^[A-Z][A-Za-z& ]+:\s+[A-Za-z]+\s+\d{4}\s+-\s+Volume\s+\d+\s+-\s+Issue\b.*\bdoi\s*:",
        re.IGNORECASE,
    ),
)
CONTEXT_ENTITY_TYPE_TAGS = {
    "target": "molecular_target",
    "molecular_target": "molecular_target",
    "brain_region_or_network": "brain_system",
    "brain_system": "brain_system",
    "network": "brain_system",
    "circuit": "brain_system",
    "cognitive_behavioral_task": "cognitive_behavioral",
    "cognitive_behavioral": "cognitive_behavioral",
    "molecular_pathway": "molecular_pathway",
    "pathway": "molecular_pathway",
    "subjective_experience": "subjective_experience",
    "acute_subjective_effect": "subjective_experience",
    "pharmacokinetics_exposure": "pharmacokinetics_exposure",
    "pharmacokinetics": "pharmacokinetics_exposure",
    "exposure": "pharmacokinetics_exposure",
    "intervention_context": "intervention_context",
    "psychotherapy_context": "intervention_context",
    "real_world_use_public_health": "real_world_use_public_health",
    "public_health": "real_world_use_public_health",
    "naturalistic_use": "real_world_use_public_health",
    "clinical_symptom_function": "clinical_outcome",
    "clinical_safety": "safety",
    "clinical_mechanism_overlap": "bridge_clinical_mechanism",
    "indication": "clinical_outcome",
    "clinical": "clinical_outcome",
}


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def default_run_id() -> str:
    return "deterministic_prescreen_" + dt.datetime.now(dt.timezone.utc).strftime("%Y_%m_%d")


def clean(value: object) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    return "" if text.lower() in {"nan", "none", "nat"} else text


def clean_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    text = clean(value).lower()
    return text in {"1", "true", "yes", "y"}


def unusable_abstract_reason(value: object) -> str:
    text = re.sub(r"\s+", " ", clean(value)).strip()
    if not text:
        return "No abstract available for title/abstract screening."
    lowered = text.lower().strip(" .[]")
    if lowered in PLACEHOLDER_ABSTRACTS:
        return "Abstract field contains a placeholder rather than a substantive abstract."
    for pattern in CITATION_ONLY_ABSTRACT_PATTERNS:
        if pattern.search(text):
            return "Abstract field contains citation metadata rather than a substantive abstract."
    return ""


def split_values(value: object) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        raw_values = value
    else:
        raw_values = re.split(r"\s*[|,;]\s*", clean(value))
    out: list[str] = []
    seen: set[str] = set()
    for raw in raw_values:
        text = clean(raw)
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def join_values(values: Iterable[object]) -> str:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = clean(value)
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return " | ".join(out)


def stable_id(*parts: object) -> str:
    payload = "\u241f".join(clean(part) for part in parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def read_table(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_parquet(path)


def load_curated_publication_format_exclusions(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    records = payload.get("records", []) if isinstance(payload, dict) else []
    out: dict[str, dict] = {}
    for record in records:
        if not isinstance(record, dict):
            continue
        doi = normalize_doi(clean(record.get("doi", ""))).lower()
        if doi:
            out[doi] = record
    return out


def load_curated_paper_metadata_overrides(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    records = payload.get("records", []) if isinstance(payload, dict) else []
    out: dict[str, dict] = {}
    for record in records:
        if not isinstance(record, dict):
            continue
        doi = normalize_doi(clean(record.get("doi", ""))).lower()
        fields = record.get("fields", {}) if isinstance(record.get("fields"), dict) else {}
        if doi:
            out[doi] = {field: value for field, value in fields.items() if field in METADATA_FIELDS}
    return out


def write_table(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(path, index=False)


def read_doi_file(path: Path) -> set[str]:
    if not path.exists():
        raise FileNotFoundError(f"DOI file does not exist: {path}")
    dois: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        doi = normalize_doi(clean(line))
        if doi and not doi.startswith("#"):
            dois.add(doi)
    return dois


def scoped_dois_from_args(args: argparse.Namespace) -> set[str]:
    dois: set[str] = set()
    doi_file = clean(getattr(args, "doi_file", ""))
    if doi_file:
        dois.update(read_doi_file(Path(doi_file).resolve()))
    for value in getattr(args, "doi", []) or []:
        doi = normalize_doi(clean(value))
        if doi:
            dois.add(doi)
    return dois


def filter_table_to_dois(df: pd.DataFrame, dois: set[str]) -> pd.DataFrame:
    if df.empty or "doi" not in df.columns or not dois:
        return df
    doi_values = df["doi"].map(lambda value: normalize_doi(clean(value)))
    return df[doi_values.isin(dois)].copy()


def existing_run_id(decisions_df: pd.DataFrame) -> str:
    if decisions_df.empty or "run_id" not in decisions_df.columns:
        return ""
    run_ids = [clean(value) for value in decisions_df["run_id"].tolist()]
    run_ids = [value for value in run_ids if value]
    if not run_ids:
        return ""
    return Counter(run_ids).most_common(1)[0][0]


def merge_scoped_decisions(
    existing_rows: list[dict],
    updated_rows: list[dict],
    *,
    scoped_dois: set[str],
) -> tuple[list[dict], int]:
    retained_existing: list[dict] = []
    replaced = 0
    for row in existing_rows:
        doi = normalize_doi(clean(row.get("doi", "")))
        if doi in scoped_dois:
            replaced += 1
            continue
        retained_existing.append(row)
    return [*retained_existing, *updated_rows], replaced


def rows_by_doi(df: pd.DataFrame) -> dict[str, dict]:
    if df.empty or "doi" not in df.columns:
        return {}
    out: dict[str, dict] = {}
    for row in df.to_dict("records"):
        doi = normalize_doi(clean(row.get("doi", "")))
        if doi and doi not in out:
            out[doi] = row
    return out


def contexts_by_doi(contexts_df: pd.DataFrame) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    if contexts_df.empty or "doi" not in contexts_df.columns:
        return out
    for row in contexts_df.to_dict("records"):
        doi = normalize_doi(clean(row.get("doi", "")))
        if not doi:
            continue
        out[doi].append(row)
    return out


def compact_contexts(contexts: list[dict]) -> list[dict]:
    out: list[dict] = []
    seen: set[tuple[str, str, str]] = set()
    for row in contexts:
        item = {
            "compound": clean(row.get("compound", "")),
            "entity": clean(row.get("entity", "")),
            "entity_type": clean(row.get("entity_type", "")),
        }
        marker = (item["compound"], item["entity"], item["entity_type"])
        if not item["compound"] and not item["entity"]:
            continue
        if marker in seen:
            continue
        seen.add(marker)
        out.append(item)
    return out


def context_routing_tags(contexts: list[dict]) -> list[str]:
    tags: list[str] = []
    for context in contexts:
        entity_type = clean(context.get("entity_type", "")).lower().replace("-", "_").replace(" ", "_")
        tag = CONTEXT_ENTITY_TYPE_TAGS.get(entity_type)
        if tag:
            tags.append(tag)
    return normalize_routing_tags(tags)


def merged_screening_row(
    paper: dict,
    metadata: dict | None,
    metadata_overrides: dict[str, dict] | None = None,
) -> dict:
    metadata = metadata or {}
    doi = normalize_doi(clean(paper.get("doi", "")))
    row = {"study_doi": doi}
    for field in METADATA_FIELDS:
        row[field] = clean(metadata.get(field, "")) or clean(paper.get(field, ""))
    for field, value in (metadata_overrides or {}).get(doi, {}).items():
        if field in METADATA_FIELDS and clean(value):
            row[field] = clean(value)
    return row


def missing_abstract_decision(row: dict, contexts: list[dict], reason: str = "") -> dict:
    return {
        "action": "exclude_missing_abstract",
        "confidence": 1.0,
        "supporting_quote": clean(row.get("abstract", "")) or clean(row.get("study_title", "")) or "not_found",
        "reason": reason or "No abstract available for title/abstract screening.",
        "matched_terms": [],
        "routing_tags": context_routing_tags(contexts),
    }


def non_paper_container_without_title_decision(row: dict, contexts: list[dict]) -> dict | None:
    title = clean(row.get("study_title", ""))
    if title:
        return None
    publication_types = {value.lower() for value in split_values(row.get("publication_type", ""))}
    if not publication_types.intersection(NON_PAPER_CONTAINER_PUBLICATION_TYPES):
        return None
    publication_type = join_values(sorted(publication_types))
    return {
        "action": "exclude_non_paper_container",
        "confidence": 1.0,
        "supporting_quote": publication_type or "no paper title",
        "reason": (
            "Metadata identifies this DOI as a journal/container record rather than a titled source paper, "
            "and no paper title is available."
        ),
        "matched_terms": sorted(publication_types),
        "routing_tags": context_routing_tags(contexts),
    }


def out_of_scope_publication_format_decision(row: dict, contexts: list[dict]) -> dict | None:
    doi = normalize_doi(clean(row.get("study_doi", ""))).lower()
    title = clean(row.get("study_title", ""))
    abstract = clean(row.get("abstract", ""))
    publication_types = {value.lower() for value in split_values(row.get("publication_type", ""))}
    matched_formats = {
        OUT_OF_SCOPE_PUBLICATION_FORMAT_TYPES[value]
        for value in publication_types
        if value in OUT_OF_SCOPE_PUBLICATION_FORMAT_TYPES
    }
    matched_terms = sorted(
        value for value in publication_types if value in OUT_OF_SCOPE_PUBLICATION_FORMAT_TYPES
    )
    for pattern, publication_format in OUT_OF_SCOPE_PUBLICATION_FORMAT_DOI_PATTERNS:
        match = pattern.search(doi)
        if match:
            matched_formats.add(publication_format)
            matched_terms.append(match.group(0))
    if VISUAL_ESSAY_TEXT_RE.search(" ".join(value for value in (title, abstract) if value)):
        matched_formats.add("visual_essay")
        matched_terms.append("visual essay")
    if not matched_formats:
        return None
    return {
        "action": "exclude_non_evidence_artifact",
        "confidence": 1.0,
        "supporting_quote": title or clean(row.get("publication_type", "")) or doi,
        "reason": (
            "Record is a book chapter, dissertation/thesis, conference/poster/meeting abstract, "
            "abstract-book contribution, or visual essay rather than an eligible source article, "
            "review, or meta-analysis."
        ),
        "matched_terms": [*sorted(matched_formats), *matched_terms],
        "routing_tags": context_routing_tags(contexts),
    }


def curated_publication_format_exclusion_decision(
    row: dict,
    contexts: list[dict],
    curated_exclusions: dict[str, dict],
) -> dict | None:
    doi = normalize_doi(clean(row.get("study_doi", ""))).lower()
    record = curated_exclusions.get(doi)
    if not record:
        return None
    publication_format = clean(record.get("publication_format", "")) or "out_of_scope_publication_format"
    evidence_basis = clean(record.get("evidence_basis", ""))
    return {
        "action": "exclude_non_evidence_artifact",
        "confidence": 1.0,
        "supporting_quote": clean(row.get("study_title", "")) or evidence_basis or doi,
        "reason": clean(record.get("reason", ""))
        or "Curated publication-format evidence identifies this record as outside the eligible evidence sources.",
        "matched_terms": [
            publication_format,
            *([evidence_basis] if evidence_basis else []),
        ],
        "routing_tags": context_routing_tags(contexts),
    }


def non_evidence_artifact_decision(row: dict, contexts: list[dict]) -> dict | None:
    doi = normalize_doi(clean(row.get("study_doi", "")))
    title = clean(row.get("study_title", ""))
    abstract = clean(row.get("abstract", ""))
    publication_type = clean(row.get("publication_type", ""))
    journal = clean(row.get("study_journal", ""))
    publication_types = {value.lower() for value in split_values(publication_type)}
    title_abstract = " ".join(value for value in (title, abstract) if value)
    matched_terms: list[str] = []
    for pattern in NON_EVIDENCE_DOI_PATTERNS:
        match = pattern.search(doi)
        if match:
            matched_terms.append(match.group(0))
    for pattern in NON_EVIDENCE_TITLE_PATTERNS:
        match = pattern.search(title)
        if match:
            matched_terms.append(match.group(0))
    for pattern in NON_EVIDENCE_PUBLICATION_PATTERNS:
        match = pattern.search(publication_type)
        if match:
            matched_terms.append(match.group(0))
    for pattern in NON_EVIDENCE_TEXT_PATTERNS:
        match = pattern.search(title_abstract)
        if match:
            matched_terms.append(match.group(0))
    for pattern in NON_EVIDENCE_SOURCE_PATTERNS:
        match = pattern.search(journal)
        if match:
            matched_terms.append(match.group(0))
    non_source_publication_types = publication_types.intersection(NON_SOURCE_PUBLICATION_TYPES)
    if non_source_publication_types:
        matched_terms.extend(sorted(non_source_publication_types))
    if not matched_terms:
        return None
    return {
        "action": "exclude_non_evidence_artifact",
        "confidence": 1.0,
        "supporting_quote": title or publication_type or doi,
        "reason": (
            "Record is a protocol, correction, review report, patent highlight, pure "
            "letter/editorial/comment/news item, newsletter/update summary, supplementary material, "
            "figure/table/data deposit, retraction, or citation artifact rather than source evidence."
        ),
        "matched_terms": matched_terms,
        "routing_tags": context_routing_tags(contexts),
    }


def numbered_title_metadata(row: dict) -> dict:
    title = clean(row.get("study_title", ""))
    match = NUMBERED_TITLE_TOKEN_RE.search(title)
    if not match:
        return {}
    number_text = match.group("number")
    rest = clean(match.group("rest") or "").lstrip(" -–—:.)]")
    try:
        number = int(number_text)
    except ValueError:
        return {}
    return {
        "number_text": number_text,
        "number": number,
        "separator": clean(match.group("sep") or ""),
        "rest": rest,
        "title": title,
    }


def numbered_title_is_protected(metadata: dict) -> bool:
    if not metadata:
        return True
    number = int(metadata.get("number", 0))
    rest = clean(metadata.get("rest", ""))
    if 1800 <= number <= 2099 and not any(pattern.search(rest) for pattern in NUMBERED_TITLE_CONFERENCE_TITLE_PATTERNS):
        return True
    return any(pattern.search(rest) for pattern in NUMBERED_TITLE_PROTECTED_REST_PATTERNS)


def mostly_uppercase(text: str) -> bool:
    letters = [char for char in text if char.isalpha()]
    if len(letters) < 12:
        return False
    uppercase = sum(char.isupper() for char in letters)
    return uppercase / len(letters) >= 0.75


def numbered_conference_abstract_decision(row: dict, contexts: list[dict]) -> dict | None:
    metadata = numbered_title_metadata(row)
    if not metadata or numbered_title_is_protected(metadata):
        return None

    doi = normalize_doi(clean(row.get("study_doi", "")))
    title = metadata["title"]
    rest = metadata["rest"]
    number = int(metadata["number"])
    separator = clean(metadata.get("separator", ""))
    publication_type = clean(row.get("publication_type", ""))
    journal = clean(row.get("study_journal", ""))
    matched_terms = [f"numbered_title:{metadata['number_text']}"]

    strong_signal = False
    source_signal = False
    for pattern in NUMBERED_TITLE_CONFERENCE_TITLE_PATTERNS:
        match = pattern.search(title)
        if match:
            matched_terms.append(match.group(0))
            strong_signal = True
    for pattern in NUMBERED_TITLE_CONFERENCE_PUBLICATION_PATTERNS:
        match = pattern.search(publication_type)
        if match:
            matched_terms.append(match.group(0))
            strong_signal = True
    for pattern in NUMBERED_TITLE_CONFERENCE_DOI_PATTERNS:
        match = pattern.search(doi)
        if match:
            matched_terms.append(match.group(0))
            source_signal = True
    for pattern in NUMBERED_TITLE_CONFERENCE_JOURNAL_PATTERNS:
        match = pattern.search(journal)
        if match:
            matched_terms.append(match.group(0))
            source_signal = True

    title_format_signal = bool(separator) or number >= 20 or mostly_uppercase(rest)
    if not strong_signal and not (source_signal and title_format_signal):
        return None

    return {
        "action": "exclude_non_evidence_artifact",
        "confidence": 1.0,
        "supporting_quote": title,
        "reason": (
            "Record appears to be a numbered conference, poster, or meeting abstract "
            "rather than a source article or review."
        ),
        "matched_terms": matched_terms,
        "routing_tags": context_routing_tags(contexts),
    }


def publication_stage_row(row: dict) -> dict:
    out = dict(row)
    if not clean(out.get("doi", "")):
        out["doi"] = clean(row.get("study_doi", ""))
    return out


def preprint_or_unpublished_decision(row: dict, contexts: list[dict]) -> dict | None:
    classification = classify_publication_stage(publication_stage_row(row))
    if clean(classification.get("publication_stage", "")) != "preprint":
        return None
    basis = clean(classification.get("preprint_detection_basis", "")) or "preprint metadata"
    return {
        "action": "exclude_preprint_or_unpublished",
        "confidence": 1.0,
        "supporting_quote": clean(row.get("publication_type", "")) or clean(row.get("study_title", "")) or basis,
        "reason": f"Record appears to be a preprint or unpublished posted-content record: {basis}.",
        "matched_terms": split_values(basis),
        "routing_tags": context_routing_tags(contexts),
    }


def acronym_false_positive_decision(row: dict, contexts: list[dict]) -> dict | None:
    text = " ".join(
        clean(row.get(field, ""))
        for field in ("study_title", "abstract", "keywords", "mesh_terms")
    )
    matched_terms: list[str] = []
    for pattern in OUT_OF_SCOPE_ACRONYM_FALSE_POSITIVE_PATTERNS:
        match = pattern.search(text)
        if match:
            matched_terms.append(match.group(0))
    if not matched_terms:
        return None
    return {
        "action": "exclude_obvious_irrelevant",
        "confidence": 1.0,
        "supporting_quote": clean(row.get("study_title", "")) or matched_terms[0],
        "reason": (
            "Record uses LSD/LSDV in the veterinary lumpy-skin-disease sense, "
            "not as psychedelic evidence."
        ),
        "matched_terms": matched_terms,
        "routing_tags": context_routing_tags(contexts),
    }


def production_method_false_positive_decision(row: dict, contexts: list[dict]) -> dict | None:
    text = " ".join(
        clean(row.get(field, ""))
        for field in ("study_title", "abstract", "keywords", "mesh_terms")
    )
    focus_matches: list[str] = []
    context_matches: list[str] = []
    for pattern in OUT_OF_SCOPE_PRODUCTION_METHOD_FOCUS_PATTERNS:
        match = pattern.search(text)
        if match:
            focus_matches.append(match.group(0))
    for pattern in OUT_OF_SCOPE_PRODUCTION_METHOD_CONTEXT_PATTERNS:
        match = pattern.search(text)
        if match:
            context_matches.append(match.group(0))
    if not focus_matches or not context_matches:
        return None
    return {
        "action": "exclude_obvious_irrelevant",
        "confidence": 1.0,
        "supporting_quote": clean(row.get("study_title", "")) or focus_matches[0],
        "reason": (
            "Record is focused on compound biosynthesis, bioproduction, or manufacturing methods "
            "rather than biological, clinical, pharmacological, or public-health evidence."
        ),
        "matched_terms": [*focus_matches, *context_matches],
        "routing_tags": context_routing_tags(contexts),
    }


def broad_nps_background_false_positive_decision(row: dict, contexts: list[dict]) -> dict | None:
    title = clean(row.get("study_title", ""))
    publication_type = clean(row.get("publication_type", ""))
    matched_terms: list[str] = []
    for pattern in OUT_OF_SCOPE_BROAD_NPS_BACKGROUND_PATTERNS:
        match = pattern.search(title)
        if match:
            matched_terms.append(match.group(0))
    if not matched_terms:
        return None
    return {
        "action": "exclude_obvious_irrelevant",
        "confidence": 1.0,
        "supporting_quote": title or matched_terms[0],
        "reason": (
            "Record is a broad historical or editorial overview of new psychoactive substances, "
            "rather than source evidence or a domain-specific evidence synthesis for the knowledge graph."
        ),
        "matched_terms": [*matched_terms, publication_type] if publication_type else matched_terms,
        "routing_tags": context_routing_tags(contexts),
    }


def before_model_exclusion_decision(
    row: dict,
    contexts: list[dict] | None = None,
    curated_publication_format_exclusions: dict[str, dict] | None = None,
) -> dict | None:
    contexts = contexts or []
    curated_publication_format_exclusions = curated_publication_format_exclusions or {}
    return (
        non_paper_container_without_title_decision(row, contexts)
        or curated_publication_format_exclusion_decision(
            row,
            contexts,
            curated_publication_format_exclusions,
        )
        or out_of_scope_publication_format_decision(row, contexts)
        or non_evidence_artifact_decision(row, contexts)
        or numbered_conference_abstract_decision(row, contexts)
        or preprint_or_unpublished_decision(row, contexts)
        or acronym_false_positive_decision(row, contexts)
        or production_method_false_positive_decision(row, contexts)
        or broad_nps_background_false_positive_decision(row, contexts)
    )


def final_prescreen_fields(decision: dict) -> tuple[str, str, str]:
    action = clean(decision.get("action", ""))
    if action.startswith("exclude"):
        return ("exclude", action, clean(decision.get("reason", "")))
    return ("retain", "retain_for_extraction_candidate", clean(decision.get("reason", "")))


def build_prescreen_decisions(
    papers_df: pd.DataFrame,
    metadata_df: pd.DataFrame,
    contexts_df: pd.DataFrame,
    *,
    run_id: str,
    generated_at_utc: str,
    exclude_missing_abstract: bool = True,
    progress_every: int = 0,
    curated_publication_format_exclusions: dict[str, dict] | None = None,
    curated_paper_metadata_overrides: dict[str, dict] | None = None,
) -> list[dict]:
    if curated_publication_format_exclusions is None:
        curated_publication_format_exclusions = load_curated_publication_format_exclusions(
            DEFAULT_CURATED_PUBLICATION_FORMAT_EXCLUSIONS
        )
    if curated_paper_metadata_overrides is None:
        curated_paper_metadata_overrides = load_curated_paper_metadata_overrides(
            DEFAULT_CURATED_PAPER_METADATA_OVERRIDES
        )
    metadata_by_doi = rows_by_doi(metadata_df)
    contexts_lookup = contexts_by_doi(contexts_df)
    rows: list[dict] = []

    paper_records = papers_df.to_dict("records")
    for paper_index, paper in enumerate(paper_records, start=1):
        if progress_every and paper_index % progress_every == 0:
            print(f"Processed {paper_index:,}/{len(paper_records):,} candidate papers...", flush=True)
        doi = normalize_doi(clean(paper.get("doi", "")))
        if not doi:
            continue
        paper_contexts = compact_contexts(contexts_lookup.get(doi, []))
        context_tags = context_routing_tags(paper_contexts)
        screening_row = merged_screening_row(
            paper,
            metadata_by_doi.get(doi),
            curated_paper_metadata_overrides,
        )
        abstract_status_reason = unusable_abstract_reason(screening_row.get("abstract", ""))
        has_abstract = not bool(abstract_status_reason)
        before_model_decision = before_model_exclusion_decision(
            screening_row,
            paper_contexts,
            curated_publication_format_exclusions,
        )
        if before_model_decision:
            decision = before_model_decision
        elif exclude_missing_abstract and not has_abstract:
            decision = missing_abstract_decision(screening_row, paper_contexts, abstract_status_reason)
        else:
            decision = deterministic_prescreen_decision(screening_row)
        deterministic_tags = normalize_routing_tags(decision.get("routing_tags", []))
        routing_tags = normalize_routing_tags([*deterministic_tags, *context_tags])
        prescreen_decision, prescreen_action, prescreen_reason = final_prescreen_fields(decision)
        retained_for_extraction_candidate = prescreen_decision == "retain" and not clean(
            decision.get("action", "")
        ).startswith("exclude")
        rows.append(
            {
                "table_version": TABLE_VERSION,
                "run_id": run_id,
                "generated_at_utc": generated_at_utc,
                "prescreen_decision_id": stable_id(run_id, doi),
                "doi": doi,
                "study_title": clean(screening_row.get("study_title", "")),
                "study_year": clean(screening_row.get("study_year", "")),
                "has_abstract": has_abstract,
                "abstract_char_count": len(clean(screening_row.get("abstract", ""))),
                "candidate_context_count": len(paper_contexts),
                "context_compounds": join_values(context.get("compound", "") for context in paper_contexts),
                "context_entities": join_values(context.get("entity", "") for context in paper_contexts),
                "context_entity_types": join_values(context.get("entity_type", "") for context in paper_contexts),
                "context_routing_tags": "|".join(context_tags),
                "deterministic_action": clean(decision.get("action", "")),
                "deterministic_reason": clean(decision.get("reason", "")),
                "deterministic_confidence": float(decision.get("confidence", 0) or 0),
                "deterministic_matched_terms": join_values(decision.get("matched_terms", [])),
                "deterministic_supporting_quote": clean(decision.get("supporting_quote", "")),
                "deterministic_routing_tags": "|".join(deterministic_tags),
                "routing_tags": "|".join(routing_tags),
                "prescreen_decision": prescreen_decision,
                "prescreen_action": prescreen_action,
                "prescreen_reason": prescreen_reason,
                "retained_for_extraction_candidate": retained_for_extraction_candidate,
                "metadata_enrichment_status": clean(screening_row.get("metadata_enrichment_status", "")),
                "metadata_enrichment_run_id": clean(screening_row.get("metadata_enrichment_run_id", "")),
            }
        )
    return rows


def build_summary_rows(decisions: list[dict], *, run_id: str, generated_at_utc: str) -> list[dict]:
    rows: list[dict] = []

    def add(metric: str, label: str, count: int) -> None:
        rows.append(
            {
                "table_version": TABLE_VERSION,
                "run_id": run_id,
                "generated_at_utc": generated_at_utc,
                "scope": "all_papers",
                "metric": metric,
                "label": label,
                "count": int(count),
            }
        )

    add("decisions", "total", len(decisions))
    add("papers", "unique_doi", len({row.get("doi") for row in decisions}))
    add("abstract", "missing", sum(not row.get("has_abstract") for row in decisions))
    for field in ("prescreen_decision", "prescreen_action", "deterministic_action"):
        for label, count in Counter(clean(row.get(field, "")) for row in decisions).items():
            add(field, label, count)
    tag_counts: Counter = Counter()
    for row in decisions:
        for tag in normalize_routing_tags(row.get("routing_tags", "")):
            tag_counts[tag] += 1
    for tag, count in tag_counts.items():
        add("routing_tag", tag, count)
    return rows


def run(args: argparse.Namespace) -> tuple[list[dict], list[dict]]:
    decisions_table = Path(args.decisions_table).resolve()
    summary_table = Path(args.summary_table).resolve()
    scoped_dois = scoped_dois_from_args(args)
    existing_decisions_df = read_table(decisions_table) if scoped_dois else pd.DataFrame()
    run_id = clean(args.run_id) or (existing_run_id(existing_decisions_df) if scoped_dois else "") or default_run_id()
    generated_at_utc = now_utc()
    curated_publication_format_exclusions = load_curated_publication_format_exclusions(
        Path(
            getattr(
                args,
                "curated_publication_format_exclusions",
                DEFAULT_CURATED_PUBLICATION_FORMAT_EXCLUSIONS,
            )
        ).resolve()
    )
    curated_paper_metadata_overrides = load_curated_paper_metadata_overrides(
        Path(
            getattr(
                args,
                "curated_paper_metadata_overrides",
                DEFAULT_CURATED_PAPER_METADATA_OVERRIDES,
            )
        ).resolve()
    )

    papers_df = read_table(Path(args.papers_table).resolve())
    metadata_df = read_table(Path(args.metadata_table).resolve())
    contexts_df = read_table(Path(args.contexts_table).resolve())

    if papers_df.empty:
        raise SystemExit(f"No rows found in papers table: {args.papers_table}")
    if scoped_dois:
        if existing_decisions_df.empty:
            raise SystemExit(
                "Scoped deterministic pre-screen updates require an existing decisions table. "
                "Run a full pass first, or omit --doi/--doi-file."
            )
        papers_df = filter_table_to_dois(papers_df, scoped_dois)
        metadata_df = filter_table_to_dois(metadata_df, scoped_dois)
        contexts_df = filter_table_to_dois(contexts_df, scoped_dois)
        if papers_df.empty:
            raise SystemExit("No matching DOI rows found in the papers table for the requested scoped update.")

    updated_decisions = build_prescreen_decisions(
        papers_df,
        metadata_df,
        contexts_df,
        run_id=run_id,
        generated_at_utc=generated_at_utc,
        exclude_missing_abstract=not args.retain_missing_abstract,
        progress_every=getattr(args, "progress_every", 0),
        curated_publication_format_exclusions=curated_publication_format_exclusions,
        curated_paper_metadata_overrides=curated_paper_metadata_overrides,
    )
    if scoped_dois:
        decisions, replaced_count = merge_scoped_decisions(
            existing_decisions_df.to_dict("records"),
            updated_decisions,
            scoped_dois=scoped_dois,
        )
    else:
        decisions = updated_decisions
        replaced_count = 0
    summary = build_summary_rows(decisions, run_id=run_id, generated_at_utc=generated_at_utc)
    write_table(decisions_table, decisions)
    write_table(summary_table, summary)

    by_action = Counter(row["prescreen_action"] for row in decisions)
    print(f"Run ID: {run_id}")
    if scoped_dois:
        print(f"Scoped DOI update: requested={len(scoped_dois):,} matched_papers={len(papers_df):,}")
        print(f"Updated decision rows: {len(updated_decisions):,}")
        print(f"Replaced existing decision rows: {replaced_count:,}")
    print(f"Decision rows: {len(decisions):,}")
    print(f"Unique DOIs: {len({row['doi'] for row in decisions}):,}")
    print(f"Retained: {sum(row['prescreen_decision'] == 'retain' for row in decisions):,}")
    print(f"Excluded: {sum(row['prescreen_decision'] == 'exclude' for row in decisions):,}")
    print(f"Actions: {dict(by_action)}")
    print(f"Decisions table: {decisions_table}")
    print(f"Summary table: {summary_table}")
    return decisions, summary


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run deterministic pre-screening on corpus Parquet tables.")
    parser.add_argument("--papers-table", default=str(DEFAULT_PAPERS_TABLE))
    parser.add_argument("--metadata-table", default=str(DEFAULT_METADATA_TABLE))
    parser.add_argument("--contexts-table", default=str(DEFAULT_CONTEXTS_TABLE))
    parser.add_argument("--decisions-table", default=str(DEFAULT_DECISIONS_TABLE))
    parser.add_argument("--summary-table", default=str(DEFAULT_SUMMARY_TABLE))
    parser.add_argument(
        "--curated-publication-format-exclusions",
        default=str(DEFAULT_CURATED_PUBLICATION_FORMAT_EXCLUSIONS),
        help=(
            "Curated DOI-level publication-format exclusions used when provider metadata is "
            "incomplete or misleading."
        ),
    )
    parser.add_argument(
        "--curated-paper-metadata-overrides",
        default=str(DEFAULT_CURATED_PAPER_METADATA_OVERRIDES),
        help="Curated DOI-level replacements for provider metadata known to belong to another paper.",
    )
    parser.add_argument("--run-id", default="")
    parser.add_argument("--doi-file", default="", help="Optional newline-delimited DOI list for a scoped update.")
    parser.add_argument("--doi", action="append", default=[], help="Single DOI for a scoped update; can be repeated.")
    parser.add_argument(
        "--retain-missing-abstract",
        action="store_true",
        help="Run title-only deterministic rules when abstracts are missing instead of excluding missing-abstract records.",
    )
    parser.add_argument("--progress-every", type=int, default=5000, help="Print progress every N candidate papers; 0 disables progress.")
    return parser


def main() -> None:
    run(build_arg_parser().parse_args())


if __name__ == "__main__":
    main()
