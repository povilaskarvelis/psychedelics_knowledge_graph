#!/usr/bin/env python3
"""Build the methods-page paper-flow projection from local pipeline artifacts."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[2]
KG_VERSION = "0.1"
CORPUS_MANIFEST = ROOT / "data" / "processed" / "corpus_manifest.json"
KG_CLAIMS_TABLE = ROOT / "data" / "processed" / "kg" / "claims.parquet"
KG_TABLE_MANIFEST = ROOT / "data" / "processed" / "kg" / "manifest.json"
EXTRACTION_PROJECTION_REPORT = ROOT / "data" / "processed" / "extraction" / "projection_report.json"
CANDIDATE_PAPERS_TABLE = ROOT / "data" / "processed" / "corpus" / "candidate_papers.parquet"
GRAPH_PAYLOAD_ACTIVE_POINTER = ROOT / "data" / "processed" / "graph_payload_active.json"

DATASETS = {
    "mechanistic": {
        "paper_library": ROOT / "data" / "processed" / "paper_library_mechanistic.json",
        "triage_report": ROOT / "data" / "processed" / "triage_report_mechanistic.json",
        "fulltext_dir": ROOT / "data" / "processed" / "fulltext" / "mechanistic",
    },
    "disorder": {
        "paper_library": ROOT / "data" / "processed" / "paper_library_disorder.json",
        "triage_report": ROOT / "data" / "processed" / "triage_report_disorder.json",
        "fulltext_dir": ROOT / "data" / "processed" / "fulltext" / "disorder",
    },
}

PAPER_METADATA_FIELDS = (
    "study_doi",
    "openalex_id",
    "study_title",
    "study_year",
    "study_journal",
    "authors",
    "pmid",
    "pmcid",
    "publication_type",
    "publication_date",
    "publisher",
    "language",
    "trial_registry_ids",
    "mesh_terms",
    "keywords",
    "funders",
    "grant_ids",
    "related_dois",
    "publication_relations",
    "is_retracted",
    "has_correction",
    "semantic_scholar_id",
    "open_access_status",
    "open_access_url",
    "pdf_download_status",
    "pdf_local_path",
    "pdf_size_bytes",
    "pdf_sha256",
    "library_status",
)

RETRIEVAL_METADATA_FIELDS = {
    "open_access_status",
    "open_access_url",
    "best_pdf_url",
    "pdf_url_candidates",
    "pdf_download_selected_url",
    "pdf_download_status",
    "pdf_local_path",
    "pdf_size_bytes",
    "pdf_sha256",
    "library_status",
    "action_reason",
}
RETRIEVAL_SIGNAL_FIELDS = RETRIEVAL_METADATA_FIELDS - {"action_reason", "library_status"}

PIPELINE_IDENTITY_FIELDS = (
    "study_doi",
    "study_title",
    "study_year",
)

PIPELINE_SCREENING_FIELDS = (
    "source_type_suggested",
    "paper_type_suggested",
    "relevance_suggested",
    "relevance_score",
    "screening_status",
    "matched_context_count",
    "synthesized_context_count",
    "protected_context_count",
    "needs_metadata_or_manual_screen",
)

RELEVANT_RELEVANCE = {"likely_relevant", "possible_relevant"}
INCLUDED_SCREENING = {
    "included_context_match",
    "included_synthesized_context",
    "included_protected",
    "included_llm_relevant",
    "included_llm_uncertain",
    "retained_for_llm_screening",
}

PRISMA_SCREENING_REASON_LABELS = {
    "excluded_deterministic_prescreen": "No in-scope title/abstract signal",
    "excluded_llm_irrelevant": "LLM abstract screen judged irrelevant",
    "excluded_low_signal": "Low-signal abstract screen",
    "llm_screening_error": "LLM abstract screen failed",
    "needs_context_review": "Possible or contextual signal only",
    "not_screened": "Not screened yet",
    "not_screened_no_abstract": "No abstract available for screening",
    "included_synthesized_context": "Synthesized context, not direct match",
    "needs_metadata_or_manual_screen": "Metadata or manual screen needed",
    "unknown": "Screening status not available",
}

PRISMA_RETRIEVAL_REASON_LABELS = {
    "not_open_access": "Not open access",
    "no_pdf_url": "No PDF URL found",
    "download_failed": "PDF download failed",
    "unusable_pdf_image_only": "Image-only PDF not retained",
    "skipped": "Download not attempted",
    "missing_local_pdf": "Local PDF file missing",
    "pdf_validation_failed": "PDF validation failed",
    "invalid_pdf_existing": "Invalid local PDF",
    "invalid_pdf_content": "Invalid downloaded PDF",
    "not_downloaded": "Not downloaded",
    "pdf_url_known": "PDF URL known, not downloaded",
    "unknown": "Retrieval status not available",
}

PRISMA_CONVERSION_REASON_LABELS = {
    "not_converted": "Conversion not completed",
    "artifact_present": "Artifact present but not confirmed converted",
    "unknown": "Conversion status not available",
}

PRISMA_EXTRACTION_REASON_LABELS = {
    "not_started": "Awaiting LLM extraction",
    "unknown": "Extraction status not available",
}

PRISMA_EXTRACTION_OUTCOME_LABELS = {
    "included_full_text": "Included from full-text evidence",
    "included_secondary_full_text": "Included as secondary evidence from a full-text report",
    "included_abstract_only": "Included from abstract-only evidence",
    "included_secondary_without_full_text": "Included from review summaries",
    "gemini_excluded": "Excluded by Gemini extraction",
    "needs_human_review": "Needs human review",
    "assessed_no_kg_record": "Assessed, no KG record promoted",
    "not_yet_extracted": "Not yet extracted",
}

PRISMA_CANDIDATE_PRESCREEN_LABELS = {
    "exclude_obvious_irrelevant": "No in-scope title/abstract signal",
    "exclude_missing_abstract": "No abstract available",
    "exclude_non_evidence_artifact": "Non-evidence artifact",
    "exclude_non_paper_container": "Non-paper container",
    "exclude_preprint_or_unpublished": "Preprint or unpublished posted content",
    "unknown": "Screening status not available",
}

PRISMA_CANDIDATE_ROUTE_LABELS = {
    "excluded_after_domain_screen": "Excluded during LLM-based screening",
    "context_only_or_skip": "Kept as background/context only",
    "not_retained_for_extraction": "Not selected for evidence extraction",
    "unknown": "LLM-based screening status not available",
}

PRISMA_PUBLIC_LLM_SCREENING_LABELS = {
    "excluded_during_llm_screening": "Excluded during LLM-based screening",
    "background_context_only": "Kept as background/context only",
    "not_selected_for_extraction": "Not selected for evidence extraction",
    "unknown": "LLM-based screening status not available",
}

PRISMA_CANDIDATE_KG_LABELS = {
    "not_graphable": "Not graphable",
    "not_normalized": "Not normalized",
    "no_graph_finding": "No graph finding",
    "unknown": "Knowledge-graph status not available",
}

PRISMA_CANDIDATE_INPUT_LABELS = {
    "ready_for_article_text_extraction": "Selected for evidence extraction",
    "ready_for_abstract_extraction": "Selected for evidence extraction",
    "unknown": "Evidence extraction input not classified",
}

METHODS_BIBLIOGRAPHY_COLUMNS = (
    "id",
    "doi",
    "title",
    "authors",
    "year",
    "journal",
    "initial_screening_status",
    "initial_screening_label",
    "initial_screening_note",
    "llm_screening_status",
    "llm_screening_label",
    "llm_screening_note",
    "extraction_status",
    "extraction_label",
    "extraction_note",
    "kg_status",
    "kg_label",
    "kg_note",
    "stage_key",
    "stage_label",
    "selected_for_extraction",
)

METHODS_BIBLIOGRAPHY_INTERNED_COLUMNS = (
    "initial_screening_status",
    "initial_screening_label",
    "initial_screening_note",
    "llm_screening_status",
    "llm_screening_label",
    "llm_screening_note",
    "extraction_status",
    "extraction_label",
    "extraction_note",
    "kg_status",
    "kg_label",
    "kg_note",
    "stage_key",
    "stage_label",
)

METHODS_BIBLIOGRAPHY_STAGE_LABELS = {
    "selected_for_extraction": "Selected for evidence extraction",
    "excluded_during_llm_screening": "Excluded during LLM-based screening",
    "background_context_only": "Kept as background/context only",
    "not_selected_for_extraction": "Not selected for evidence extraction",
    "excluded_during_initial_screening": "Excluded during initial screening",
    "identified_not_screened": "Identified, not screened",
}

METHODS_BIBLIOGRAPHY_STAGE_ORDER = (
    "selected_for_extraction",
    "excluded_during_llm_screening",
    "background_context_only",
    "not_selected_for_extraction",
    "excluded_during_initial_screening",
    "identified_not_screened",
)

METHODS_BIBLIOGRAPHY_KG_LABEL_ORDER = (
    "In graph",
    "Not graphable",
    "Not normalized",
    "No graph finding",
    "Not reached",
)

KG_AUDIT_REASON_LABELS = {
    "compound_graph_scope_not_graphable": "Compound outside graph scope",
    "compound_class_not_graphable": "Compound class, not a graphable compound",
    "compound_reference_not_graphable": "Reference compound, not a graphable compound",
    "compound_combo_not_graphable": "Compound combination not split into a graphable compound",
    "condition_analog_not_graphable": "Condition analogue not graphable",
    "condition_broad_placeholder_not_graphable": "Condition label too broad for the graph",
    "brain_measure_not_graphable": "Brain measure not mapped to a graph node",
    "broad_brain_system_not_graphable": "Brain-system label too broad for the graph",
    "molecular_effect_placeholder_not_graphable": "Molecular-effect label too broad for the graph",
    "generic_behavior_not_graphable": "Behavior label too generic for the graph",
    "entity_combo_not_graphable": "Combined entity label not split into a graph node",
    "entity_reference_not_graphable": "Reference entity, not a graphable node",
    "compound_unmapped": "Compound was not normalized",
    "entity_unmapped": "Entity was not normalized",
}

KG_AUDIT_REASON_ORDER = (
    "compound_graph_scope_not_graphable",
    "compound_reference_not_graphable",
    "compound_class_not_graphable",
    "compound_combo_not_graphable",
    "compound_unmapped",
    "entity_unmapped",
    "condition_broad_placeholder_not_graphable",
    "condition_analog_not_graphable",
    "brain_measure_not_graphable",
    "broad_brain_system_not_graphable",
    "molecular_effect_placeholder_not_graphable",
    "generic_behavior_not_graphable",
    "entity_combo_not_graphable",
    "entity_reference_not_graphable",
)

METHODS_BIBLIOGRAPHY_PROFILE_LABELS = {
    "primary_evidence_schema": "primary-study evidence",
    "review_coverage_schema": "review evidence",
    "meta_analysis_evidence_schema": "meta-analysis evidence",
    "recommendation_consensus_schema": "guideline/consensus evidence",
    "context_only_schema": "background/context evidence",
    "no_extraction_schema": "no evidence extraction",
}

METHODS_BIBLIOGRAPHY_SCREENING_REASONS = {
    "exclude_obvious_irrelevant": "No in-scope signal",
    "exclude_missing_abstract": "No abstract",
    "exclude_non_evidence_artifact": "Not an evidence paper",
    "exclude_non_paper_container": "Journal/container record",
    "exclude_preprint_or_unpublished": "Preprint/unpublished",
    "retain_for_extraction_candidate": "",
}


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def normalize(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def strip_markup(value: object) -> str:
    text = html.unescape(normalize(value))
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_doi(raw: object) -> str:
    text = normalize(raw)
    if not text:
        return ""
    lowered = text.lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/", "http://dx.doi.org/", "doi:"):
        if lowered.startswith(prefix):
            text = text[len(prefix) :]
            break
    return text.strip().lower()


def compact_key(value: object) -> str:
    text = strip_markup(value).lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def slug(value: object, fallback_prefix: str = "id") -> str:
    key = compact_key(value)
    if not key:
        digest = hashlib.sha1(normalize(value).encode("utf-8")).hexdigest()[:12]
        return f"{fallback_prefix}_{digest}"
    return re.sub(r"[^a-z0-9]+", "_", key).strip("_")[:120]


def digest_id(*parts: object, length: int = 16) -> str:
    canonical = "|".join(normalize(part) for part in parts)
    return hashlib.sha1(canonical.encode("utf-8")).hexdigest()[:length]


def as_int(value: object) -> int | str:
    text = normalize(value)
    if not text:
        return ""
    try:
        return int(float(text))
    except Exception:
        return text


def json_value(value: object) -> object:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return value


def read_json(path: Path, default: object) -> object:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def read_json_array(path: Path) -> list[dict]:
    data = read_json(path, [])
    if not isinstance(data, list):
        raise ValueError(f"Expected JSON array at {path}")
    return [row for row in data if isinstance(row, dict)]


def read_json_object(path: Path) -> dict:
    data = read_json(path, {})
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object at {path}")
    return data


def read_jsonl(path: Path) -> list[dict]:
    rows = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            if isinstance(row, dict):
                rows.append(row)
    return rows


def resolve_project_path(path: object) -> Path:
    value = Path(normalize(path))
    return value if value.is_absolute() else ROOT / value


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def write_compact_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, separators=(",", ":"), ensure_ascii=False) + "\n", encoding="utf-8")


def project_path(root: Path, value: object) -> Path | None:
    raw = normalize(value)
    if not raw:
        return None
    path = Path(raw)
    return path if path.is_absolute() else root / path


def active_routed_kg_dirs(root: Path = ROOT, active_pointer: Path | None = None) -> list[Path]:
    """Return every routed KG run used by the active (possibly mixed) graph."""
    active_pointer = active_pointer or root / "data" / "processed" / "graph_payload_active.json"
    if not active_pointer.exists():
        return []
    try:
        active = read_json_object(active_pointer)
    except Exception:
        return []

    kg_dirs: list[Path] = []
    seen: set[Path] = set()

    def add_kg_dir(value: object) -> None:
        path = project_path(root, value)
        if path is None:
            return
        resolved = path.resolve()
        if resolved not in seen:
            seen.add(resolved)
            kg_dirs.append(resolved)

    add_kg_dir(active.get("kg_dir", ""))

    manifest_values = [active.get("active_manifest", "")]
    detail_bootstraps = active.get("active_detail_bootstraps", {})
    if isinstance(detail_bootstraps, dict):
        for detail_value in detail_bootstraps.values():
            detail_path = project_path(root, detail_value)
            if detail_path is not None:
                manifest_values.append(detail_path.parent / "graph_payload_manifest.json")

    for manifest_value in manifest_values:
        manifest_path = project_path(root, manifest_value)
        if manifest_path is None or not manifest_path.exists():
            continue
        try:
            manifest = read_json_object(manifest_path)
        except Exception:
            continue
        add_kg_dir(manifest.get("kg_dir", ""))

    return kg_dirs


def active_routed_kg_dir(root: Path = ROOT, active_pointer: Path | None = None) -> Path | None:
    """Backward-compatible accessor for callers that expect one active KG run."""
    kg_dirs = active_routed_kg_dirs(root, active_pointer)
    return kg_dirs[0] if kg_dirs else None


def active_detail_study_dois(
    root: Path = ROOT,
    active_pointer: Path | None = None,
) -> tuple[set[str], list[str], list[str], int]:
    """Read the DOI set actually served by the active browser detail payloads."""
    active_pointer = active_pointer or root / "data" / "processed" / "graph_payload_active.json"
    input_files: list[str] = []
    warnings: list[str] = []
    if not active_pointer.exists():
        return set(), input_files, warnings, 0
    try:
        active = read_json_object(active_pointer)
    except Exception as exc:
        warnings.append(f"Could not read active graph payload pointer {active_pointer}: {exc}")
        return set(), input_files, warnings, 0

    detail_bootstraps = active.get("active_detail_bootstraps", {})
    if not isinstance(detail_bootstraps, dict):
        return set(), input_files, warnings, 0

    dois: set[str] = set()
    loaded_sources = 0
    for source, value in sorted(detail_bootstraps.items()):
        path = project_path(root, value)
        if path is None or not path.exists():
            warnings.append(f"Active {source} detail payload is missing: {path or value}")
            continue
        input_files.append(str(path))
        try:
            payload = read_json_object(path)
            fields = payload.get("fields", [])
            values = payload.get("values", [])
            rows = payload.get("rows", [])
            doi_index = fields.index("study_doi")
            for row in rows:
                if not isinstance(row, list) or doi_index >= len(row):
                    continue
                value_index = row[doi_index]
                if not isinstance(value_index, int) or value_index < 0 or value_index >= len(values):
                    continue
                doi = normalize_doi(values[value_index])
                if doi:
                    dois.add(doi)
            loaded_sources += 1
        except Exception as exc:
            warnings.append(f"Could not read active {source} detail payload {path}: {exc}")
    return dois, input_files, warnings, loaded_sources


def unique_public_labels(values: Iterable[object], limit: int = 3) -> str:
    labels = []
    seen = set()
    for value in values:
        label = strip_markup(value)
        if not label or label in seen:
            continue
        labels.append(label)
        seen.add(label)
    if not labels:
        return ""
    shown = labels[:limit]
    suffix = f" +{len(labels) - limit} more" if len(labels) > limit else ""
    return ", ".join(shown) + suffix


def first_nonempty(*values: object) -> object:
    for value in values:
        if normalize(value):
            return value
    return ""


def boolish(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return normalize(value).lower() in {"1", "true", "yes", "y"}


def merge_unique(existing: list, values: Iterable[object]) -> list:
    seen = {json.dumps(item, sort_keys=True, ensure_ascii=False) for item in existing}
    out = list(existing)
    for value in values:
        if value is None or value == "":
            continue
        key = json.dumps(value, sort_keys=True, ensure_ascii=False)
        if key in seen:
            continue
        out.append(value)
        seen.add(key)
    return out


def paper_id_for(row: dict) -> str:
    doi = normalize_doi(row.get("study_doi", ""))
    if doi:
        return f"paper:{doi}"
    openalex = normalize(row.get("openalex_id", "")).lower()
    if openalex:
        return f"paper:openalex:{slug(openalex)}"
    title = strip_markup(row.get("study_title", ""))
    year = normalize(row.get("study_year", ""))
    return f"paper:title:{digest_id(title, year)}"


def local_pdf_exists(row: dict) -> bool:
    raw_path = normalize(row.get("pdf_local_path", ""))
    if not raw_path:
        return False
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        path = ROOT / path
    return path.exists() and path.is_file() and path.stat().st_size > 0


def pdf_status(row: dict) -> str:
    status = normalize(row.get("pdf_download_status", ""))
    if status in {"invalid_pdf_existing", "invalid_pdf_content"}:
        return status
    if status in {"downloaded", "already_present", "manual_import"} and local_pdf_exists(row):
        return "downloaded"
    if status in {"downloaded", "already_present", "manual_import"}:
        return "missing_local_pdf"
    if status:
        return status
    if local_pdf_exists(row):
        return "downloaded"
    if normalize(row.get("pdf_local_path", "")):
        return "missing_local_pdf"
    if normalize(row.get("best_pdf_url", "")):
        return "pdf_url_known"
    return "not_downloaded"


def source_stage(source_file: Path) -> str:
    name = source_file.name
    if name.startswith("paper_library_"):
        return "paper_library"
    if name.startswith("triage_report_"):
        return "triage_report"
    if name.startswith("llm_abstract_screening_report_"):
        return "llm_screening_report"
    if name.startswith("deterministic_prescreen_report_"):
        return "deterministic_prescreen_report"
    if "claim" in name:
        return "claims"
    return source_file.stem


def retrieval_source_rank(stage: str) -> int:
    return {
        "paper_library": 3,
        "triage_report": 1,
        "claims": 0,
    }.get(stage, 0)


def screening_source_rank(stage: str) -> int:
    return {
        "llm_screening_report": 5,
        "deterministic_prescreen_report": 4,
        "triage_report": 3,
        "paper_library": 1,
        "claims": 0,
    }.get(stage, 0)


def retrieval_snapshot(row: dict) -> dict:
    status = pdf_status(row)
    snapshot = {"pdf_status": status}
    has_valid_local_pdf = local_pdf_exists(row)
    for field in RETRIEVAL_METADATA_FIELDS:
        value = row.get(field, "")
        if not normalize(value):
            continue
        if field in {"pdf_local_path", "pdf_size_bytes", "pdf_sha256"} and not (
            has_valid_local_pdf or status == "missing_local_pdf"
        ):
            continue
        snapshot[field] = json_value(value)
    return snapshot


def has_retrieval_signal(row: dict) -> bool:
    return any(normalize(row.get(field, "")) for field in RETRIEVAL_SIGNAL_FIELDS)


def prisma_retrieval_reason(props: dict) -> str:
    status = normalize(props.get("pdf_status", ""))
    if status in {"invalid_pdf_existing", "invalid_pdf_content"}:
        return "pdf_validation_failed"
    if status == "unusable_pdf_image_only":
        return "unusable_pdf_image_only"
    return status or "unknown"


def inferred_prescreen_report_path(llm_report_path: Path, dataset: str) -> Path:
    prefix = f"llm_abstract_screening_report_{dataset}"
    stem = llm_report_path.stem
    suffix = stem[len(prefix) :] if stem.startswith(prefix) else ""
    return llm_report_path.with_name(f"deterministic_prescreen_report_{dataset}{suffix}.json")


def row_flattened(row: dict) -> dict:
    flat = {}
    input_row = row.get("input_row")
    if isinstance(input_row, dict):
        flat.update(input_row)
    flat_row = row.get("flat")
    if isinstance(flat_row, dict):
        flat.update(flat_row)
    return flat


def llm_relevance(row: dict, flat: dict) -> str:
    adjudication = row.get("adjudication") if isinstance(row.get("adjudication"), dict) else {}
    return normalize(flat.get("llm_relevance") or adjudication.get("relevance")).lower()


def relevance_to_pipeline(relevance: str) -> tuple[str, str]:
    if relevance == "relevant":
        return "likely_relevant", "included_llm_relevant"
    if relevance == "uncertain":
        return "possible_relevant", "included_llm_uncertain"
    if relevance == "irrelevant":
        return "likely_irrelevant", "excluded_llm_irrelevant"
    return "unknown", "llm_screening_error"


def deterministic_prescreen_pipeline_row(row: dict) -> dict:
    action = normalize(row.get("deterministic_prescreen_action", ""))
    retained = boolish(row.get("retained_for_llm"))
    if action == "exclude_obvious_irrelevant":
        relevance = "likely_irrelevant"
        screening_status = "excluded_deterministic_prescreen"
    elif retained:
        relevance = "possible_relevant"
        screening_status = "retained_for_llm_screening"
    else:
        relevance = "unknown"
        screening_status = action or "deterministic_prescreen_unknown"
    out = {
        "study_doi": normalize_doi(row.get("study_doi", "")),
        "study_title": strip_markup(row.get("study_title", "")),
        "study_year": row.get("study_year", ""),
        "authors": row.get("authors", ""),
        "pdf_download_status": row.get("pdf_download_status", ""),
        "relevance_suggested": relevance,
        "screening_status": screening_status,
        "matched_context_count": row.get("candidate_context_count", ""),
        "deterministic_prescreen_action": action,
        "deterministic_prescreen_reason": row.get("deterministic_prescreen_reason", ""),
    }
    if row.get("has_abstract") is not None:
        out["abstract_present"] = boolish(row.get("has_abstract"))
    return out


def llm_screening_pipeline_row(dataset: str, row: dict) -> dict:
    flat = row_flattened(row)
    relevance = llm_relevance(row, flat)
    relevance_suggested, screening_status = relevance_to_pipeline(relevance)
    verification = row.get("verification") if isinstance(row.get("verification"), dict) else {}
    out = {
        "study_doi": normalize_doi(flat.get("study_doi", "")),
        "study_title": strip_markup(flat.get("study_title", "")),
        "study_year": flat.get("study_year", ""),
        "authors": flat.get("authors", ""),
        "study_journal": flat.get("study_journal", ""),
        "publication_type": flat.get("publication_type", ""),
        "trial_registry_ids": flat.get("trial_registry_ids", ""),
        "publication_date": flat.get("publication_date", ""),
        "journal_issn": flat.get("journal_issn", ""),
        "journal_eissn": flat.get("journal_eissn", ""),
        "publisher": flat.get("publisher", ""),
        "mesh_terms": flat.get("mesh_terms", ""),
        "keywords": flat.get("keywords", ""),
        "funders": flat.get("funders", ""),
        "grant_ids": flat.get("grant_ids", ""),
        "related_dois": flat.get("related_dois", ""),
        "publication_relations": flat.get("publication_relations", ""),
        "is_retracted": flat.get("is_retracted", ""),
        "has_correction": flat.get("has_correction", ""),
        "language": flat.get("language", ""),
        "semantic_scholar_id": flat.get("semantic_scholar_id", ""),
        "library_status": flat.get("library_status", ""),
        "pdf_download_status": flat.get("pdf_download_status", ""),
        "relevance_suggested": relevance_suggested,
        "screening_status": screening_status,
        "matched_context_count": flat.get("verified_supported_context_count") or len(llm_supported_contexts(row)),
        "llm_relevance": relevance,
        "llm_confidence": flat.get("llm_confidence", ""),
        "quote_verified": flat.get("quote_verified", "") or verification.get("quote_verified", ""),
        "llm_needs_targeted_qa": flat.get("llm_needs_targeted_qa", ""),
        "validation_flags": flat.get("validation_flags", ""),
    }
    if normalize(flat.get("has_abstract", "")):
        out["abstract_present"] = boolish(flat.get("has_abstract", ""))
    return out


def llm_supported_contexts(row: dict) -> list[dict]:
    verification = row.get("verification") if isinstance(row.get("verification"), dict) else {}
    verified = verification.get("verified_supported_contexts")
    if isinstance(verified, list) and verified:
        return [context for context in verified if isinstance(context, dict)]
    adjudication = row.get("adjudication") if isinstance(row.get("adjudication"), dict) else {}
    contexts = adjudication.get("supported_contexts")
    if not isinstance(contexts, list):
        return []
    out = []
    for context in contexts:
        if not isinstance(context, dict):
            continue
        support = normalize(context.get("support", "")).lower()
        if support and support != "supported":
            continue
        out.append(context)
    return out


class MethodsFlowBuilder:
    def __init__(self, root: Path = ROOT, *, routed_kg_dir: Path | None = None) -> None:
        self.root = root
        self.routed_kg_dir = Path(routed_kg_dir).resolve() if routed_kg_dir is not None else None
        self.nodes: dict[str, dict] = {}
        self.papers: dict[str, dict] = {}
        self.candidate_rows: list[dict] = []
        self.kg_graph_status_by_doi: dict[str, dict] = {}
        self.fulltext_by_doi: dict[str, dict] = {}
        self.doi_to_paper_id: dict[str, str] = {}
        self.pipeline_rows: dict[str, dict[str, dict]] = defaultdict(dict)
        self.datasets_with_corpus_screening: set[str] = set()
        self.metadata_conflicts: Counter = Counter()
        self.metadata_conflict_examples: dict[str, list[dict]] = defaultdict(list)
        self.kg_claim_rows_by_dataset: Counter = Counter()
        self.kg_claim_papers_by_dataset: Counter = Counter()
        self.kg_claim_matched_pipeline_rows_by_dataset: Counter = Counter()
        self.kg_claim_access_rows_by_dataset: dict[str, Counter] = defaultdict(Counter)
        self.extraction_output_rows_by_dataset: Counter = Counter()
        self.extraction_output_routes_by_dataset: dict[str, Counter] = defaultdict(Counter)
        self.extraction_matched_pipeline_rows_by_dataset: Counter = Counter()
        self.input_files: list[str] = []
        self.warnings: list[str] = []

    def build(self) -> dict:
        loaded_candidate_table = self.load_candidate_papers()
        self.load_routed_kg_graph_status()
        if not loaded_candidate_table:
            self.load_fulltext_status()
            self.load_paper_libraries()
            self.load_corpus_screening_reports()
            self.load_triage_reports()
            self.finalize_paper_nodes()
            self.load_kg_claim_status()
            self.load_extraction_outcomes()
        return self.payloads()

    def candidate_table_path(self) -> Path:
        return self.root / "data" / "processed" / "corpus" / "candidate_papers.parquet"

    def load_routed_kg_graph_status(self) -> None:
        lookup, input_files, warnings = routed_kg_graph_status_by_doi(
            self.root,
            kg_dir_override=self.routed_kg_dir,
        )
        self.kg_graph_status_by_doi = lookup
        self.input_files.extend(input_files)
        self.warnings.extend(warnings)

    def load_candidate_papers(self, candidate_table: Path | None = None) -> bool:
        candidate_table = Path(candidate_table) if candidate_table is not None else self.candidate_table_path()
        if not candidate_table.exists():
            return False

        self.input_files.append(str(candidate_table))
        try:
            import pandas as pd
        except ModuleNotFoundError as exc:  # pragma: no cover - dependency failure path
            self.warnings.append(f"Could not load candidate paper table because pandas is unavailable: {exc}")
            return False

        try:
            df = pd.read_parquet(candidate_table)
        except Exception as exc:
            self.warnings.append(f"Could not read candidate paper table {candidate_table}: {exc}")
            return False

        self.candidate_rows = df.where(pd.notna(df), "").to_dict(orient="records")
        return True

    def record_metadata_conflict(
        self,
        *,
        dataset: str,
        paper_id: str,
        field: str,
        existing: str,
        incoming: str,
        existing_source: str,
        incoming_source: str,
    ) -> None:
        if not existing or not incoming or existing == incoming:
            return
        key = f"{dataset}:{field}:{existing}->{incoming}"
        self.metadata_conflicts[key] += 1
        examples = self.metadata_conflict_examples[key]
        if len(examples) < 8:
            examples.append(
                {
                    "dataset": dataset,
                    "paper_id": paper_id,
                    "field": field,
                    "existing": existing,
                    "incoming": incoming,
                    "existing_source": existing_source,
                    "incoming_source": incoming_source,
                }
            )

    def merge_retrieval_metadata(
        self,
        props: dict,
        row: dict,
        dataset: str,
        paper_id: str,
        source_file: Path,
    ) -> None:
        stage = source_stage(source_file)
        incoming_rank = retrieval_source_rank(stage)
        if incoming_rank <= 0:
            return
        if not has_retrieval_signal(row):
            return

        incoming = retrieval_snapshot(row)
        incoming_status = normalize(incoming.get("pdf_status", ""))
        existing_status = normalize(props.get("pdf_status", ""))
        existing_source = normalize(props.get("_kg_retrieval_source", ""))
        if existing_status and incoming_status and existing_status != incoming_status:
            self.record_metadata_conflict(
                dataset=dataset,
                paper_id=paper_id,
                field="pdf_status",
                existing=existing_status,
                incoming=incoming_status,
                existing_source=existing_source or "unknown",
                incoming_source=stage,
            )

        existing_rank = int(props.get("_kg_retrieval_source_rank", 0) or 0)
        chosen_status = strongest_pdf_status(existing_status, incoming_status)
        should_update = incoming_rank > existing_rank or (
            incoming_rank == existing_rank and chosen_status == incoming_status and incoming_status != existing_status
        )
        if not should_update:
            if incoming_rank == existing_rank and incoming_status == existing_status:
                for field, value in incoming.items():
                    if normalize(value) and not normalize(props.get(field, "")):
                        props[field] = value
            return

        for field in RETRIEVAL_METADATA_FIELDS:
            props.pop(field, None)
        props.update(incoming)
        props["_kg_retrieval_source"] = stage
        props["_kg_retrieval_source_rank"] = incoming_rank

    def merge_screening_metadata(
        self,
        props: dict,
        row: dict,
        dataset: str,
        paper_id: str,
        source_file: Path,
    ) -> None:
        stage = source_stage(source_file)
        incoming_rank = screening_source_rank(stage)
        if incoming_rank <= 0:
            return
        existing_rank = int(props.get("_kg_screening_source_rank", 0) or 0)
        if incoming_rank < existing_rank:
            return

        for field in PIPELINE_SCREENING_FIELDS:
            value = row.get(field, "")
            if normalize(value) == "":
                continue
            existing_value = normalize(props.get(field, ""))
            incoming_value = normalize(value)
            if existing_value and existing_value != incoming_value and incoming_rank >= existing_rank:
                self.record_metadata_conflict(
                    dataset=dataset,
                    paper_id=paper_id,
                    field=field,
                    existing=existing_value,
                    incoming=incoming_value,
                    existing_source=normalize(props.get("_kg_screening_source", "")) or "unknown",
                    incoming_source=stage,
                )
            props[field] = json_value(value)
        props["_kg_screening_source"] = stage
        props["_kg_screening_source_rank"] = incoming_rank

    def merge_paper(self, row: dict, dataset: str, source_file: Path) -> str:
        paper_id = paper_id_for(row)
        props = self.papers.setdefault(
            paper_id,
            {
                "id": paper_id,
                "type": "Paper",
                "label": "",
                "properties": {
                    "datasets": [],
                    "source_files": [],
                },
            },
        )["properties"]
        props["datasets"] = merge_unique(props.get("datasets", []), [dataset])
        props["source_files"] = merge_unique(props.get("source_files", []), [str(source_file)])

        for field in PAPER_METADATA_FIELDS:
            if field in RETRIEVAL_METADATA_FIELDS:
                continue
            value = row.get(field, "")
            if normalize(value) and not normalize(props.get(field, "")):
                props[field] = json_value(value)
        title = strip_markup(first_nonempty(props.get("study_title", ""), row.get("study_title", "")))
        if title:
            self.papers[paper_id]["label"] = title
            props["study_title"] = title
        year = as_int(first_nonempty(props.get("study_year", ""), row.get("study_year", "")))
        if year != "":
            props["study_year"] = year
        abstract = strip_markup(row.get("abstract", ""))
        if abstract and not props.get("abstract_snippet"):
            props["abstract_present"] = True
            props["abstract_char_count"] = len(abstract)
            props["abstract_snippet"] = abstract[:500]
        self.merge_retrieval_metadata(props, row, dataset, paper_id, source_file)

        doi = normalize_doi(props.get("study_doi", "") or row.get("study_doi", ""))
        if doi:
            props["study_doi"] = doi
            self.doi_to_paper_id[doi] = paper_id
            if doi in self.fulltext_by_doi:
                props.update(self.fulltext_by_doi[doi])
        return paper_id

    def merge_pipeline_row(self, row: dict, dataset: str, paper_id: str, source_file: Path) -> None:
        props = self.pipeline_rows[dataset].setdefault(
            paper_id,
            {
                "paper_id": paper_id,
                "dataset": dataset,
                "source_files": [],
                "llm_extraction_status": "not_started",
            },
        )
        props["source_files"] = merge_unique(props.get("source_files", []), [str(source_file)])
        props.setdefault("abstract_present", False)
        if normalize(row.get("abstract", "")):
            props["abstract_present"] = True
        elif "abstract_present" in row:
            props["abstract_present"] = boolish(row.get("abstract_present")) or boolish(props.get("abstract_present"))
        elif "has_abstract" in row:
            props["abstract_present"] = boolish(row.get("has_abstract")) or boolish(props.get("abstract_present"))

        for field in PIPELINE_IDENTITY_FIELDS:
            value = row.get(field, "")
            if normalize(value) != "" and not normalize(props.get(field, "")):
                props[field] = json_value(value)

        self.merge_screening_metadata(props, row, dataset, paper_id, source_file)
        self.merge_retrieval_metadata(props, row, dataset, paper_id, source_file)
        doi = normalize_doi(props.get("study_doi", "") or row.get("study_doi", ""))
        if doi and doi in self.fulltext_by_doi:
            props.update(self.fulltext_by_doi[doi])
        props.setdefault("fulltext_status", "not_converted")

    def load_fulltext_status(self) -> None:
        for dataset, cfg in DATASETS.items():
            fulltext_dir = cfg["fulltext_dir"]
            if not fulltext_dir.exists():
                continue
            self.input_files.append(str(fulltext_dir))
            for path in sorted(fulltext_dir.glob("*.json")):
                try:
                    artifact = read_json_object(path)
                except Exception as err:
                    self.warnings.append(f"Could not read full-text artifact {path}: {err}")
                    continue
                doi = normalize_doi(artifact.get("study_doi", ""))
                if not doi:
                    continue
                best_backend = normalize(artifact.get("best_backend", ""))
                best_char_count = int(artifact.get("best_char_count", 0) or 0)
                self.fulltext_by_doi[doi] = {
                    "fulltext_status": "converted" if best_backend and best_char_count else "artifact_present",
                    "fulltext_dataset": dataset,
                    "fulltext_artifact_path": str(path),
                    "fulltext_backend": best_backend,
                    "fulltext_char_count": best_char_count,
                    "fulltext_section_count": int(artifact.get("best_section_count", 0) or 0),
                }

    def load_paper_libraries(self) -> None:
        for dataset, cfg in DATASETS.items():
            path = cfg["paper_library"]
            self.input_files.append(str(path))
            for row in read_json_array(path):
                paper_id = self.merge_paper(row, dataset, path)
                self.merge_pipeline_row(row, dataset, paper_id, path)

    def load_triage_reports(self) -> None:
        for dataset, cfg in DATASETS.items():
            if dataset in self.datasets_with_corpus_screening:
                continue
            path = cfg["triage_report"]
            report = read_json_object(path)
            self.input_files.append(str(path))
            for row in report.get("rows", []):
                if not isinstance(row, dict):
                    continue
                paper_id = self.merge_paper(row, dataset, path)
                self.merge_pipeline_row(row, dataset, paper_id, path)
                paper_props = self.papers[paper_id]["properties"]
                for field in (
                    "source_type_suggested",
                    "paper_type_suggested",
                    "relevance_suggested",
                    "relevance_score",
                    "screening_status",
                    "matched_context_count",
                    "synthesized_context_count",
                    "protected_context_count",
                    "needs_metadata_or_manual_screen",
                ):
                    value = row.get(field, "")
                    if normalize(value) != "":
                        paper_props[field] = value

    def load_corpus_screening_reports(self) -> None:
        if not CORPUS_MANIFEST.exists():
            return
        manifest = read_json_object(CORPUS_MANIFEST)
        self.input_files.append(str(CORPUS_MANIFEST))
        datasets = manifest.get("datasets", {})
        if not isinstance(datasets, dict):
            self.warnings.append(f"Corpus manifest has no datasets object: {CORPUS_MANIFEST}")
            return
        for dataset in DATASETS:
            dataset_manifest = datasets.get(dataset, {})
            if not isinstance(dataset_manifest, dict):
                continue
            reports = dataset_manifest.get("screening_reports", [])
            if not isinstance(reports, list):
                self.warnings.append(f"Corpus manifest screening_reports is not a list for {dataset}")
                continue
            loaded_any = False
            for report_entry in reports:
                if not isinstance(report_entry, dict) or report_entry.get("include", True) is False:
                    continue
                report_value = normalize(report_entry.get("path", ""))
                if not report_value:
                    self.warnings.append(f"Corpus manifest screening report entry has no path for {dataset}")
                    continue
                report_path = resolve_project_path(report_value)
                if not report_path.exists():
                    self.warnings.append(f"Manifest-listed screening report is missing: {report_path}")
                    continue
                prescreen_path = inferred_prescreen_report_path(report_path, dataset)
                if prescreen_path.exists():
                    self.load_deterministic_prescreen_report(dataset, prescreen_path)
                self.load_llm_screening_report(dataset, report_path, normalize(report_entry.get("run_id", "")))
                loaded_any = True
            if loaded_any:
                self.datasets_with_corpus_screening.add(dataset)

    def load_deterministic_prescreen_report(self, dataset: str, path: Path) -> None:
        report = read_json_object(path)
        self.input_files.append(str(path))
        for row in report.get("rows", []):
            if not isinstance(row, dict):
                continue
            normalized_row = deterministic_prescreen_pipeline_row(row)
            if not normalize(normalized_row.get("study_doi", "")):
                continue
            paper_id = self.merge_paper(normalized_row, dataset, path)
            self.merge_pipeline_row(normalized_row, dataset, paper_id, path)

    def load_llm_screening_report(self, dataset: str, path: Path, run_id: str) -> None:
        report = read_json_object(path)
        self.input_files.append(str(path))
        for row in report.get("rows", []):
            if not isinstance(row, dict):
                continue
            normalized_row = llm_screening_pipeline_row(dataset, row)
            if not normalize(normalized_row.get("study_doi", "")):
                continue
            paper_id = self.merge_paper(normalized_row, dataset, path)
            self.merge_pipeline_row(normalized_row, dataset, paper_id, path)

    def finalize_paper_nodes(self) -> None:
        for paper_id, node in self.papers.items():
            props = node["properties"]
            for key in list(props):
                if key.startswith("_kg_"):
                    props.pop(key, None)
            props.setdefault("fulltext_status", "not_converted")
            props.setdefault("abstract_present", False)
            props.setdefault("llm_extraction_status", "not_started")
            if not node.get("label"):
                node["label"] = props.get("study_doi", "") or props.get("openalex_id", "") or paper_id
            self.nodes[paper_id] = node

    def load_kg_claim_status(
        self,
        claims_table: Path = KG_CLAIMS_TABLE,
        table_manifest: Path = KG_TABLE_MANIFEST,
    ) -> None:
        if table_manifest.exists():
            self.input_files.append(str(table_manifest))
        if not claims_table.exists():
            self.warnings.append(
                f"Normalized KG claims table is missing: {claims_table}. "
                "Run python pipeline/kg/build_evidence_tables.py before rebuilding methods flow."
            )
            return

        self.input_files.append(str(claims_table))
        try:
            import pandas as pd
        except ModuleNotFoundError as exc:  # pragma: no cover - dependency failure path
            self.warnings.append(f"Could not load normalized KG claims table because pandas is unavailable: {exc}")
            return

        try:
            claims = pd.read_parquet(claims_table)
        except Exception as exc:
            self.warnings.append(f"Could not read normalized KG claims table {claims_table}: {exc}")
            return

        required = {"dataset", "paper_id"}
        missing = required - set(claims.columns)
        if missing:
            self.warnings.append(f"Normalized KG claims table is missing required columns: {sorted(missing)}")
            return

        claim_counts: Counter = Counter()
        claim_access_counts: dict[tuple[str, str], Counter] = defaultdict(Counter)
        dataset_papers: dict[str, set[str]] = defaultdict(set)
        columns = [column for column in ("dataset", "paper_id", "study_doi", "access_level") if column in claims.columns]
        for record in claims[columns].to_dict(orient="records"):
            dataset = normalize(record.get("dataset", ""))
            if dataset not in DATASETS:
                continue
            paper_id = normalize(record.get("paper_id", ""))
            if not paper_id:
                doi = normalize_doi(record.get("study_doi", ""))
                paper_id = f"paper:{doi}" if doi else ""
            if not paper_id:
                continue
            claim_counts[(dataset, paper_id)] += 1
            self.kg_claim_rows_by_dataset[dataset] += 1
            dataset_papers[dataset].add(paper_id)
            access_level = normalize(record.get("access_level", "")) or "unknown"
            claim_access_counts[(dataset, paper_id)][access_level] += 1
            self.kg_claim_access_rows_by_dataset[dataset][access_level] += 1

        for dataset, paper_ids in dataset_papers.items():
            self.kg_claim_papers_by_dataset[dataset] = len(paper_ids)

        for dataset, rows_by_paper in self.pipeline_rows.items():
            for paper_id, props in rows_by_paper.items():
                claim_key = (dataset, paper_id)
                claim_count = claim_counts.get(claim_key, 0)
                if not claim_count:
                    doi = normalize_doi(props.get("study_doi", ""))
                    if doi:
                        fallback_key = (dataset, f"paper:{doi}")
                        claim_count = claim_counts.get(fallback_key, 0)
                        if claim_count:
                            claim_key = fallback_key
                if not claim_count:
                    continue
                props["llm_extraction_status"] = "claim_available"
                props["kg_claim_count"] = claim_count
                props["kg_claim_access_levels"] = dict(sorted(claim_access_counts[claim_key].items()))
                props["kg_claim_source"] = str(claims_table)
                self.kg_claim_matched_pipeline_rows_by_dataset[dataset] += 1

                paper_node = self.nodes.get(paper_id, {})
                paper_props = paper_node.get("properties", {})
                if isinstance(paper_props, dict):
                    paper_props["llm_extraction_status"] = "claim_available"
                    paper_props["kg_claim_count"] = claim_count
                    paper_props["kg_claim_access_levels"] = props["kg_claim_access_levels"]
                    paper_props["kg_claim_source"] = str(claims_table)

    def load_extraction_outcomes(self, report_path: Path = EXTRACTION_PROJECTION_REPORT) -> None:
        if not report_path.exists():
            self.warnings.append(f"Extraction projection report is missing: {report_path}")
            return

        self.input_files.append(str(report_path))
        try:
            report = read_json_object(report_path)
        except Exception as exc:
            self.warnings.append(f"Could not read extraction projection report {report_path}: {exc}")
            return

        raw_path = normalize(report.get("inputs", {}).get("input_jsonl", ""))
        if not raw_path:
            self.warnings.append(f"Extraction projection report does not name an input_jsonl: {report_path}")
            return
        results_path = resolve_project_path(raw_path)
        if not results_path.exists():
            self.warnings.append(f"Extraction result JSONL is missing: {results_path}")
            return

        self.input_files.append(str(results_path))
        try:
            rows = read_jsonl(results_path)
        except Exception as exc:
            self.warnings.append(f"Could not read extraction result JSONL {results_path}: {exc}")
            return

        matched: dict[str, set[str]] = defaultdict(set)
        for row in rows:
            dataset = normalize(row.get("dataset", ""))
            if dataset not in DATASETS:
                continue
            paper_id = paper_id_for(row)
            props = self.pipeline_rows.get(dataset, {}).get(paper_id)
            if props is None:
                doi = normalize_doi(row.get("study_doi", ""))
                props = self.pipeline_rows.get(dataset, {}).get(f"paper:{doi}") if doi else None
            assessment = row.get("paper_assessment") if isinstance(row.get("paper_assessment"), dict) else {}
            route = normalize(assessment.get("route", "")) or "unknown"
            access_level = normalize(row.get("access_level", "")) or "unknown"
            self.extraction_output_rows_by_dataset[dataset] += 1
            self.extraction_output_routes_by_dataset[dataset][route] += 1
            if props is None:
                continue
            record = {
                "access_level": access_level,
                "route": route,
                "relevance": normalize(assessment.get("relevance", "")),
                "has_extractable_claims": boolish(assessment.get("has_extractable_claims", False)),
                "claims": len(row.get("claims", []) if isinstance(row.get("claims", []), list) else []),
                "coverage_mentions": len(
                    row.get("coverage_mentions", []) if isinstance(row.get("coverage_mentions", []), list) else []
                ),
                "source": str(results_path),
            }
            if normalize(assessment.get("exclusion_reason", "")):
                record["exclusion_reason"] = normalize(assessment.get("exclusion_reason", ""))
            props.setdefault("extraction_records", []).append(record)
            matched[dataset].add(props["paper_id"])

        for dataset, paper_ids in matched.items():
            self.extraction_matched_pipeline_rows_by_dataset[dataset] = len(paper_ids)

    def kg_claim_status_summary(self) -> dict:
        return {
            "claims_table": str(KG_CLAIMS_TABLE),
            "claim_rows_by_dataset": dict(sorted(self.kg_claim_rows_by_dataset.items())),
            "claim_papers_by_dataset": dict(sorted(self.kg_claim_papers_by_dataset.items())),
            "claim_access_rows_by_dataset": {
                dataset: dict(sorted(counter.items()))
                for dataset, counter in sorted(self.kg_claim_access_rows_by_dataset.items())
            },
            "matched_pipeline_rows_by_dataset": dict(sorted(self.kg_claim_matched_pipeline_rows_by_dataset.items())),
        }

    def extraction_status_summary(self) -> dict:
        return {
            "projection_report": str(EXTRACTION_PROJECTION_REPORT),
            "output_rows_by_dataset": dict(sorted(self.extraction_output_rows_by_dataset.items())),
            "output_routes_by_dataset": {
                dataset: dict(sorted(counter.items()))
                for dataset, counter in sorted(self.extraction_output_routes_by_dataset.items())
            },
            "matched_pipeline_rows_by_dataset": dict(sorted(self.extraction_matched_pipeline_rows_by_dataset.items())),
        }

    def candidate_pipeline_status_view(self) -> dict:
        flow = prisma_flow_for_candidate_papers(
            self.candidate_rows,
            kg_status_by_doi=self.kg_graph_status_by_doi,
        )
        return {
            "contract_version": KG_VERSION,
            "view": "pipeline_status",
            "generated_at": now_utc(),
            "current_stage": "kg_inclusion_summary",
            "counts": public_candidate_pipeline_counts(flow),
            "prisma_flow_order": ["overall"],
            "prisma_flow": {
                "overall": flow,
            },
        }

    def pipeline_status_view(self) -> dict:
        if self.candidate_rows:
            return self.candidate_pipeline_status_view()

        counters: dict[str, Counter] = defaultdict(Counter)
        prisma_rows: dict[str, list[dict]] = defaultdict(list)
        for dataset, rows_by_paper in sorted(self.pipeline_rows.items()):
            for row_props in rows_by_paper.values():
                paper_props = self.nodes.get(row_props.get("paper_id", ""), {}).get("properties", {})
                props = pipeline_row_with_paper_artifacts(
                    row_props,
                    paper_props,
                )
                if not paper_has_screening_record(props):
                    props["relevance_suggested"] = "unknown"
                    props["screening_status"] = (
                        "not_screened_no_abstract" if not boolish(props.get("abstract_present", False)) else "not_screened"
                    )
                counters[f"{dataset}:relevance"][normalize(props.get("relevance_suggested", "")) or "unknown"] += 1
                counters[f"{dataset}:screening"][normalize(props.get("screening_status", "")) or "unknown"] += 1
                counters[f"{dataset}:pdf"][normalize(props.get("pdf_status", "")) or "unknown"] += 1
                counters[f"{dataset}:fulltext"][normalize(props.get("fulltext_status", "")) or "unknown"] += 1
                counters[f"{dataset}:llm_extraction"][normalize(props.get("llm_extraction_status", "")) or "unknown"] += 1
                prisma_rows[dataset].append(props)
        return {
            "contract_version": KG_VERSION,
            "view": "pipeline_status",
            "generated_at": now_utc(),
            "current_stage": "kg_inclusion_summary",
            "counts": {key: dict(counter) for key, counter in sorted(counters.items())},
            "kg_claim_status": self.kg_claim_status_summary(),
            "extraction_status": self.extraction_status_summary(),
            "metadata_quality": self.metadata_quality_summary(),
            "prisma_flow_order": sorted(prisma_rows),
            "prisma_flow": {
                dataset: prisma_flow_for_dataset(dataset, rows)
                for dataset, rows in sorted(prisma_rows.items())
            },
        }

    def metadata_quality_summary(self) -> dict:
        conflicts = []
        for key, count in self.metadata_conflicts.most_common():
            conflicts.append(
                {
                    "key": key,
                    "count": count,
                    "examples": self.metadata_conflict_examples.get(key, []),
                }
            )
        return {
            "reconciliation_rules": {
                "screening": "Dataset-specific triage rows are authoritative for screening/relevance fields.",
                "retrieval": "Paper-library rows are authoritative for retrieval/access fields; triage retrieval fields are fallback only.",
                "paper_artifacts": "Valid downloaded PDFs and converted full-text artifacts may be reused across dataset views; negative failure labels are reused only for unattempted rows.",
            },
            "conflicts": conflicts,
        }

    def payloads(self) -> dict:
        bibliography_rows = self.candidate_rows if self.candidate_rows else []
        return {
            "pipeline_status": self.pipeline_status_view(),
            "methods_bibliography": candidate_bibliography_payload(
                bibliography_rows,
                kg_status_by_doi=self.kg_graph_status_by_doi,
            ),
            "manifest": {
                "contract_version": KG_VERSION,
                "generated_at": now_utc(),
                "input_files": sorted(set(self.input_files)),
                "warnings": self.warnings,
                "counts": {
                    "papers_found_by_search": len(self.candidate_rows),
                    "pipeline_rows": {
                        dataset: len(rows_by_paper)
                        for dataset, rows_by_paper in sorted(self.pipeline_rows.items())
                    },
                    "kg_claim_rows_by_dataset": dict(sorted(self.kg_claim_rows_by_dataset.items())),
                    "kg_claim_papers_by_dataset": dict(sorted(self.kg_claim_papers_by_dataset.items())),
                    "kg_claim_access_rows_by_dataset": {
                        dataset: dict(sorted(counter.items()))
                        for dataset, counter in sorted(self.kg_claim_access_rows_by_dataset.items())
                    },
                    "kg_claim_matched_pipeline_rows_by_dataset": dict(
                        sorted(self.kg_claim_matched_pipeline_rows_by_dataset.items())
                    ),
                    "extraction_output_rows_by_dataset": dict(
                        sorted(self.extraction_output_rows_by_dataset.items())
                    ),
                    "extraction_matched_pipeline_rows_by_dataset": dict(
                        sorted(self.extraction_matched_pipeline_rows_by_dataset.items())
                    ),
                },
            },
        }


def candidate_field(row: dict, field: str, fallback: str = "unknown") -> str:
    value = normalize(row.get(field, ""))
    return value or fallback


def candidate_number(row: dict, field: str) -> int:
    value = row.get(field, 0)
    try:
        return int(float(value))
    except Exception:
        return 0


def candidate_screened(row: dict) -> bool:
    return any(
        field in row and normalize(row.get(field, "")) != ""
        for field in (
            "prescreen_actions",
            "prescreen_decisions",
            "prescreen_reasons",
            "prescreen_retained_for_extraction_candidate",
        )
    )


def candidate_prescreen_retained(row: dict) -> bool:
    decision = normalize(row.get("prescreen_decisions", "")).lower()
    if decision:
        return decision == "retain"
    return boolish(row.get("prescreen_retained_for_extraction_candidate", False))


def candidate_label_for(mapping: dict[str, str], key: str, fallback: str = "unknown") -> str:
    return mapping.get(key, status_label(key or fallback))


def candidate_bibliography_stage(row: dict) -> tuple[str, str]:
    screened = candidate_screened(row)
    prescreen_retained = candidate_prescreen_retained(row)
    selected = boolish(row.get("retained_for_extraction_candidate", False))
    route_status = normalize(row.get("extraction_route_status", "")).lower()

    if selected:
        key = "selected_for_extraction"
        label = METHODS_BIBLIOGRAPHY_STAGE_LABELS[key]
        return key, label

    if not screened:
        key = "identified_not_screened"
        label = METHODS_BIBLIOGRAPHY_STAGE_LABELS[key]
        return key, label

    if not prescreen_retained:
        key = "excluded_during_initial_screening"
        label = METHODS_BIBLIOGRAPHY_STAGE_LABELS[key]
        return key, label

    if route_status == "excluded_after_domain_screen":
        key = "excluded_during_llm_screening"
    elif route_status == "context_only_or_skip":
        key = "background_context_only"
    else:
        key = "not_selected_for_extraction"
    label = METHODS_BIBLIOGRAPHY_STAGE_LABELS[key]
    return key, label


def extraction_detail_for_candidate(row: dict) -> str:
    details = []
    route_count = candidate_number(row, "retained_extraction_route_count")
    if route_count:
        details.append(f"{route_count:,} evidence-extraction assignment{'s' if route_count != 1 else ''}")
    access_tier = normalize(row.get("best_extraction_access_tier", ""))
    if access_tier:
        details.append(status_label(access_tier))
    profiles = public_profile_labels(row.get("extraction_schema_profiles", ""))
    if profiles:
        details.append(profiles)
    return "; ".join(details)


def public_profile_labels(value: object) -> str:
    text = strip_markup(value)
    if not text:
        return ""
    parts = [
        part.strip()
        for part in re.split(r"\s*\|\s*", text)
        if part.strip()
    ]
    labels = [
        METHODS_BIBLIOGRAPHY_PROFILE_LABELS.get(part, status_label(part))
        for part in parts
    ]
    return " | ".join(labels)


def public_llm_screening_reason(row: dict) -> str:
    route_status = normalize(row.get("extraction_route_status", "")).lower()
    if route_status == "ready_for_article_text_extraction":
        return "The paper was selected for evidence extraction."
    if route_status == "ready_for_abstract_extraction":
        return "The paper was selected for evidence extraction."
    if route_status == "excluded_after_domain_screen":
        return "LLM-based screening did not identify an in-scope evidence area for extraction."
    if route_status == "context_only_or_skip":
        return "The paper may be useful as background, but it is not part of the extracted evidence set."
    if not candidate_prescreen_retained(row):
        return "The paper did not pass initial screening."
    return "No current evidence extraction assignment is stored for this paper."


def public_screening_reason(row: dict, action: str = "") -> str:
    action = action or normalize(row.get("prescreen_actions", "")).lower() or "unknown"
    mapped = METHODS_BIBLIOGRAPHY_SCREENING_REASONS.get(action)
    if mapped:
        return mapped
    return strip_markup(row.get("prescreen_reasons", "")) or candidate_label_for(
        PRISMA_CANDIDATE_PRESCREEN_LABELS,
        action,
    )


def candidate_screening_cell(row: dict) -> tuple[str, str, str]:
    if not candidate_screened(row):
        return "not_reached", "Not screened", "No screening status"
    action = normalize(row.get("prescreen_actions", "")).lower() or "unknown"
    if candidate_prescreen_retained(row):
        return "pass", "Passed", ""
    return "fail", "Did not pass", public_screening_reason(row, action)


def candidate_llm_screening_cell(row: dict) -> tuple[str, str, str]:
    if not candidate_prescreen_retained(row):
        return "not_reached", "Not reached", ""
    route_status = normalize(row.get("extraction_route_status", "")).lower() or "unknown"
    if boolish(row.get("retained_for_extraction_candidate", False)):
        return "pass", "Passed", ""
    if route_status == "context_only_or_skip":
        return "fail", "Background/context only", ""
    if route_status == "excluded_after_domain_screen":
        return "fail", "Did not pass", "No in-scope evidence area"
    return "fail", "Did not pass", ""


def candidate_extraction_cell(row: dict) -> tuple[str, str, str]:
    if not candidate_prescreen_retained(row):
        return "not_reached", "Not reached", ""
    if not boolish(row.get("retained_for_extraction_candidate", False)):
        return "fail", "Not selected", ""
    return "pass", "Selected", ""


def kg_audit_reason_label(statuses: Iterable[str]) -> str:
    normalized_statuses = {normalize(status).lower() for status in statuses if normalize(status)}
    for status in KG_AUDIT_REASON_ORDER:
        if status in normalized_statuses:
            return KG_AUDIT_REASON_LABELS[status]
    if normalized_statuses:
        return status_label(sorted(normalized_statuses)[0])
    return "No normalized graph finding"


def kg_public_status_for_audit(statuses: Iterable[str]) -> tuple[str, str]:
    normalized_statuses = {normalize(status).lower() for status in statuses if normalize(status)}
    if any(status.endswith("_not_graphable") for status in normalized_statuses):
        return "fail", "Not graphable"
    if any(status.endswith("_unmapped") for status in normalized_statuses):
        return "fail", "Not normalized"
    return "fail", "No graph finding"


def kg_status_from_audit(info: dict) -> dict:
    statuses = info.get("statuses", set())
    status, label = kg_public_status_for_audit(statuses)
    note = kg_audit_reason_label(statuses)
    compounds = unique_public_labels(info.get("compounds", []))
    if compounds and any(normalize(status).lower().startswith("compound_") for status in statuses):
        note = f"{note}: {compounds}"
    return {"status": status, "label": label, "note": note}


def routed_kg_graph_status_by_doi(
    root: Path = ROOT,
    *,
    kg_dir_override: Path | None = None,
) -> tuple[dict[str, dict], list[str], list[str]]:
    input_files: list[str] = []
    warnings: list[str] = []
    active_pointer = root / GRAPH_PAYLOAD_ACTIVE_POINTER.relative_to(ROOT)
    kg_dirs = (
        [Path(kg_dir_override).resolve()]
        if kg_dir_override is not None
        else active_routed_kg_dirs(root, active_pointer)
    )
    if not kg_dirs:
        warnings.append(
            "Active graph payload pointer is missing; methods bibliography cannot mark final KG graph status."
        )
        return {}, input_files, warnings

    if kg_dir_override is None:
        input_files.append(str(active_pointer))

    try:
        import pandas as pd
    except ModuleNotFoundError as exc:  # pragma: no cover - dependency failure path
        warnings.append(f"Could not load routed KG graph status because pandas is unavailable: {exc}")
        return {}, input_files, warnings

    included_dois: set[str] = set()
    loaded_active_sources = 0
    if kg_dir_override is None:
        included_dois, detail_inputs, detail_warnings, loaded_active_sources = active_detail_study_dois(
            root,
            active_pointer,
        )
        input_files.extend(detail_inputs)
        warnings.extend(detail_warnings)

    audit_by_doi: dict[str, dict] = defaultdict(lambda: {"statuses": set(), "compounds": []})
    for kg_dir in kg_dirs:
        input_files.append(str(kg_dir))
        findings_table = kg_dir / "findings.parquet"
        audit_table = kg_dir / "normalization_audit.parquet"

        if kg_dir_override is not None or loaded_active_sources == 0:
            if not findings_table.exists():
                warnings.append(f"Routed KG findings table is missing: {findings_table}")
            else:
                input_files.append(str(findings_table))
                try:
                    findings = pd.read_parquet(findings_table, columns=["study_doi"])
                    included_dois.update(
                        doi
                        for doi in (normalize_doi(value) for value in findings["study_doi"].tolist())
                        if doi
                    )
                except Exception as exc:
                    warnings.append(f"Could not read routed KG findings table {findings_table}: {exc}")

        if audit_table.exists():
            input_files.append(str(audit_table))
            try:
                audit = pd.read_parquet(audit_table)
                wanted_columns = [
                    column
                    for column in (
                        "study_doi",
                        "normalization_status",
                        "canonical_compound",
                        "compound",
                        "compound_original",
                    )
                    if column in audit.columns
                ]
                for record in audit[wanted_columns].where(pd.notna(audit[wanted_columns]), "").to_dict(orient="records"):
                    doi = normalize_doi(record.get("study_doi", ""))
                    status = normalize(record.get("normalization_status", "")).lower()
                    if not doi or not status:
                        continue
                    info = audit_by_doi[doi]
                    info["statuses"].add(status)
                    compound = first_nonempty(
                        record.get("canonical_compound", ""),
                        record.get("compound", ""),
                        record.get("compound_original", ""),
                    )
                    if normalize(compound):
                        info["compounds"].append(compound)
            except Exception as exc:
                warnings.append(f"Could not read routed KG normalization audit table {audit_table}: {exc}")
        else:
            warnings.append(f"Routed KG normalization audit table is missing: {audit_table}")

    lookup = {
        doi: {"status": "pass", "label": "In graph", "note": ""}
        for doi in included_dois
    }
    for doi, info in audit_by_doi.items():
        if doi in lookup:
            continue
        lookup[doi] = kg_status_from_audit(info)
    return lookup, input_files, warnings


def candidate_kg_cell(row: dict, kg_status_by_doi: dict[str, dict] | None = None) -> tuple[str, str, str]:
    if not boolish(row.get("retained_for_extraction_candidate", False)):
        return "not_reached", "Not reached", ""
    doi = normalize_doi(first_nonempty(row.get("doi", ""), row.get("study_doi", "")))
    if not doi:
        return "fail", "No graph finding", "No DOI available for graph matching"
    status = (kg_status_by_doi or {}).get(doi)
    if status:
        return (
            normalize(status.get("status", "")) or "fail",
            normalize(status.get("label", "")) or "No graph finding",
            strip_markup(status.get("note", "")),
        )
    return "fail", "No graph finding", "No normalized graph finding"


def candidate_audit_decision(row: dict, kg_status_by_doi: dict[str, dict] | None = None) -> dict:
    screening_status, screening_label, screening_note = candidate_screening_cell(row)
    llm_screening_status, llm_screening_label, llm_screening_note = candidate_llm_screening_cell(row)
    extraction_status, extraction_label, extraction_note = candidate_extraction_cell(row)
    kg_status, kg_label, kg_note = candidate_kg_cell(row, kg_status_by_doi)
    stage_key, stage_label = candidate_bibliography_stage(row)
    return {
        "initial_screening_status": screening_status,
        "initial_screening_label": screening_label,
        "initial_screening_note": screening_note,
        "llm_screening_status": llm_screening_status,
        "llm_screening_label": llm_screening_label,
        "llm_screening_note": llm_screening_note,
        "extraction_status": extraction_status,
        "extraction_label": extraction_label,
        "extraction_note": extraction_note,
        "kg_status": kg_status,
        "kg_label": kg_label,
        "kg_note": kg_note,
        "stage_key": stage_key,
        "stage_label": stage_label,
        "selected_for_extraction": boolish(row.get("retained_for_extraction_candidate", False)),
        "screened": candidate_screened(row),
        "prescreen_retained": candidate_prescreen_retained(row),
    }


def candidate_kg_reason_key(decision: dict) -> str:
    label = normalize(decision.get("kg_label", ""))
    if label == "Not graphable":
        return "not_graphable"
    if label == "Not normalized":
        return "not_normalized"
    if label == "No graph finding":
        return "no_graph_finding"
    return "unknown"


def candidate_bibliography_row(row: dict, kg_status_by_doi: dict[str, dict] | None = None) -> list:
    decision = candidate_audit_decision(row, kg_status_by_doi)
    doi = normalize_doi(first_nonempty(row.get("doi", ""), row.get("study_doi", "")))
    metadata_row = {
        "study_doi": doi,
        "openalex_id": row.get("openalex_id", ""),
        "study_title": row.get("study_title", ""),
        "study_year": row.get("study_year", ""),
    }
    return [
        paper_id_for(metadata_row),
        doi,
        strip_markup(row.get("study_title", "")),
        strip_markup(row.get("authors", "")),
        as_int(row.get("study_year", "")),
        strip_markup(row.get("study_journal", "")),
        decision["initial_screening_status"],
        decision["initial_screening_label"],
        decision["initial_screening_note"],
        decision["llm_screening_status"],
        decision["llm_screening_label"],
        decision["llm_screening_note"],
        decision["extraction_status"],
        decision["extraction_label"],
        decision["extraction_note"],
        decision["kg_status"],
        decision["kg_label"],
        decision["kg_note"],
        decision["stage_key"],
        decision["stage_label"],
        decision["selected_for_extraction"],
    ]


def candidate_bibliography_sort_key(row: list) -> tuple[str, str, str, str]:
    by_name = dict(zip(METHODS_BIBLIOGRAPHY_COLUMNS, row))
    return (
        compact_key(by_name.get("authors", "")),
        compact_key(by_name.get("title", "")),
        normalize(by_name.get("year", "")),
        normalize(by_name.get("doi", "")),
    )


def intern_bibliography_rows(rows: list[list]) -> tuple[list[list], list[str]]:
    string_table: list[str] = []
    string_indexes: dict[str, int] = {}
    column_indexes = [
        METHODS_BIBLIOGRAPHY_COLUMNS.index(column)
        for column in METHODS_BIBLIOGRAPHY_INTERNED_COLUMNS
    ]

    def intern(value: object) -> int:
        text = normalize(value)
        if text not in string_indexes:
            string_indexes[text] = len(string_table)
            string_table.append(text)
        return string_indexes[text]

    out = []
    for row in rows:
        encoded = list(row)
        for index in column_indexes:
            encoded[index] = intern(encoded[index])
        out.append(encoded)
    return out, string_table


def candidate_bibliography_payload(
    rows: Iterable[dict],
    kg_status_by_doi: dict[str, dict] | None = None,
) -> dict:
    bibliography_rows = sorted(
        (candidate_bibliography_row(row, kg_status_by_doi=kg_status_by_doi) for row in rows),
        key=candidate_bibliography_sort_key,
    )
    stage_index = METHODS_BIBLIOGRAPHY_COLUMNS.index("stage_key")
    stage_counts = Counter(row[stage_index] for row in bibliography_rows)
    kg_label_index = METHODS_BIBLIOGRAPHY_COLUMNS.index("kg_label")
    kg_label_counts = Counter(row[kg_label_index] for row in bibliography_rows)
    stage_options = [
        {
            "key": key,
            "label": METHODS_BIBLIOGRAPHY_STAGE_LABELS[key],
            "count": stage_counts[key],
        }
        for key in METHODS_BIBLIOGRAPHY_STAGE_ORDER
        if stage_counts.get(key)
    ]
    stage_options.extend(
        {
            "key": key,
            "label": METHODS_BIBLIOGRAPHY_STAGE_LABELS.get(key, status_label(key)),
            "count": stage_counts[key],
        }
        for key in sorted(stage_counts)
        if key not in METHODS_BIBLIOGRAPHY_STAGE_ORDER
    )
    kg_options = [
        {
            "key": slug(label),
            "label": label,
            "count": kg_label_counts[label],
        }
        for label in METHODS_BIBLIOGRAPHY_KG_LABEL_ORDER
        if kg_label_counts.get(label)
    ]
    kg_options.extend(
        {
            "key": slug(label),
            "label": label,
            "count": kg_label_counts[label],
        }
        for label in sorted(kg_label_counts)
        if label not in METHODS_BIBLIOGRAPHY_KG_LABEL_ORDER
    )
    encoded_rows, string_table = intern_bibliography_rows(bibliography_rows)
    return {
        "contract_version": KG_VERSION,
        "view": "methods_bibliography",
        "generated_at": now_utc(),
        "unit": "papers",
        "columns": list(METHODS_BIBLIOGRAPHY_COLUMNS),
        "interned_columns": list(METHODS_BIBLIOGRAPHY_INTERNED_COLUMNS),
        "string_table": string_table,
        "stage_options": stage_options,
        "kg_options": kg_options,
        "counts": {
            "papers": len(bibliography_rows),
            "by_stage": {item["key"]: item["count"] for item in stage_options},
            "by_kg_status": {item["label"]: item["count"] for item in kg_options},
        },
        "rows": encoded_rows,
    }


def public_candidate_pipeline_counts(flow: dict) -> dict:
    steps = flow.get("steps", {})
    side_boxes = flow.get("side_boxes", {})
    return {
        "papers_found_by_search": int(steps.get("records_identified", {}).get("count", 0) or 0),
        "screened_for_relevance": int(steps.get("records_screened", {}).get("count", 0) or 0),
        "kept_after_initial_screening": int(steps.get("prescreen_retained", {}).get("count", 0) or 0),
        "selected_for_evidence_extraction": int(steps.get("evidence_extraction_selected", {}).get("count", 0) or 0),
        "represented_in_knowledge_graph": int(steps.get("kg_included", {}).get("count", 0) or 0),
        "not_screened": int(side_boxes.get("removed_before_screening", {}).get("count", 0) or 0),
        "excluded_during_initial_screening": int(side_boxes.get("records_excluded", {}).get("count", 0) or 0),
        "not_selected_for_evidence_extraction": int(side_boxes.get("route_not_selected", {}).get("count", 0) or 0),
        "not_represented_in_knowledge_graph": int(side_boxes.get("kg_not_included", {}).get("count", 0) or 0),
    }


def public_llm_screening_reason_key(row: dict) -> str:
    route_status = normalize(row.get("extraction_route_status", "")).lower()
    if route_status == "excluded_after_domain_screen":
        return "excluded_during_llm_screening"
    if route_status == "context_only_or_skip":
        return "background_context_only"
    if route_status:
        return "not_selected_for_extraction"
    return "unknown"


def prisma_flow_for_candidate_papers(
    props_rows: Iterable[dict],
    kg_status_by_doi: dict[str, dict] | None = None,
) -> dict:
    rows = list(props_rows)
    decisions = [
        (row, candidate_audit_decision(row, kg_status_by_doi))
        for row in rows
    ]
    screened_rows = [row for row, decision in decisions if decision["screened"]]
    not_screened_rows = [row for row, decision in decisions if not decision["screened"]]
    prescreen_retained_rows = [
        row for row, decision in decisions if decision["screened"] and decision["prescreen_retained"]
    ]
    prescreen_excluded_rows = [
        row for row, decision in decisions if decision["screened"] and not decision["prescreen_retained"]
    ]
    extraction_selected = [
        (row, decision) for row, decision in decisions if decision["selected_for_extraction"]
    ]
    route_not_selected_rows = [
        row
        for row, decision in decisions
        if decision["screened"] and decision["prescreen_retained"] and not decision["selected_for_extraction"]
    ]
    kg_included_rows = [
        row for row, decision in extraction_selected if decision["kg_status"] == "pass"
    ]
    kg_not_included = [
        (row, decision) for row, decision in extraction_selected if decision["kg_status"] != "pass"
    ]
    prescreen_reasons = Counter(candidate_field(row, "prescreen_actions") for row in prescreen_excluded_rows)
    route_not_selected_reasons = Counter(public_llm_screening_reason_key(row) for row in route_not_selected_rows)
    kg_not_included_reasons = Counter(candidate_kg_reason_key(decision) for _, decision in kg_not_included)
    not_screened_reasons = Counter({"no_prescreen_status": len(not_screened_rows)}) if not_screened_rows else Counter()

    return {
        "dataset": "overall",
        "label": "Paper search and graph-inclusion flow",
        "unit": "papers",
        "current_stage": "kg_inclusion_summary",
        "metrics": {
            "selected_papers": len(extraction_selected),
            "represented_in_knowledge_graph": len(kg_included_rows),
            "not_represented_in_knowledge_graph": len(kg_not_included),
            "finding_counts_available": True,
        },
        "steps": {
            "records_identified": {
                "label": "Papers found by the search",
                "count": len(rows),
            },
            "records_screened": {
                "label": "Papers screened for relevance",
                "count": len(screened_rows),
            },
            "prescreen_retained": {
                "label": "Papers kept after initial screening",
                "count": len(prescreen_retained_rows),
            },
            "evidence_extraction_selected": {
                "label": "Papers selected for evidence extraction",
                "count": len(extraction_selected),
            },
            "kg_included": {
                "label": "Papers represented in the knowledge graph",
                "count": len(kg_included_rows),
            },
        },
        "side_boxes": {
            "removed_before_screening": {
                "label": "Records not screened",
                "count": len(not_screened_rows),
                "reasons": labeled_reason_counts(
                    not_screened_reasons,
                    {"no_prescreen_status": "No screening status"},
                    ("no_prescreen_status",),
                ),
            },
            "records_excluded": {
                "label": "Excluded during initial screening",
                "count": len(prescreen_excluded_rows),
                "reasons": labeled_reason_counts(
                    prescreen_reasons,
                    PRISMA_CANDIDATE_PRESCREEN_LABELS,
                    (
                        "exclude_obvious_irrelevant",
                        "exclude_missing_abstract",
                        "exclude_non_evidence_artifact",
                        "exclude_non_paper_container",
                        "exclude_preprint_or_unpublished",
                        "unknown",
                    ),
                ),
            },
            "route_not_selected": {
                "label": "Not selected for evidence extraction",
                "count": len(route_not_selected_rows),
                "reasons": labeled_reason_counts(
                    route_not_selected_reasons,
                    PRISMA_PUBLIC_LLM_SCREENING_LABELS,
                    (
                        "excluded_during_llm_screening",
                        "background_context_only",
                        "not_selected_for_extraction",
                        "unknown",
                    ),
                ),
            },
            "kg_not_included": {
                "label": "Selected papers not represented in graph",
                "count": len(kg_not_included),
                "reasons": labeled_reason_counts(
                    kg_not_included_reasons,
                    PRISMA_CANDIDATE_KG_LABELS,
                    (
                        "not_graphable",
                        "not_normalized",
                        "no_graph_finding",
                        "unknown",
                    ),
                ),
            },
        },
        "rows": [
            {"step": "records_identified", "side_box": "removed_before_screening"},
            {"step": "records_screened", "side_box": "records_excluded"},
            {"step": "prescreen_retained", "side_box": "route_not_selected"},
            {
                "step": "evidence_extraction_selected",
                "side_box": "kg_not_included",
            },
            {
                "step": "kg_included",
                "last": True,
            },
        ],
    }


def strongest_pdf_status(left: str, right: str) -> str:
    rank = {
        "": 0,
        "not_downloaded": 1,
        "needs_download": 1,
        "failed": 1,
        "missing_local_pdf": 1,
        "pdf_url_known": 2,
        "not_open_access": 2,
        "no_pdf_url": 2,
        "unusable_pdf_image_only": 4,
        "download_failed": 4,
        "invalid_pdf_existing": 5,
        "invalid_pdf_content": 5,
        "already_present": 5,
        "downloaded": 6,
    }
    return right if rank.get(right, 1) > rank.get(left, 1) else left


def paper_has_screening_record(props: dict) -> bool:
    return bool(normalize(props.get("relevance_suggested", "")) or normalize(props.get("screening_status", "")))


def pipeline_row_with_paper_artifacts(row_props: dict, paper_props: dict) -> dict:
    props = dict(row_props)
    row_pdf_status = normalize(props.get("pdf_status", ""))
    paper_pdf_status = normalize(paper_props.get("pdf_status", ""))
    if paper_pdf_status == "downloaded":
        props["pdf_status"] = "downloaded"
    elif row_pdf_status in {"", "not_downloaded", "skipped"} and paper_pdf_status in {
        "download_failed",
        "unusable_pdf_image_only",
        "no_pdf_url",
        "not_open_access",
        "invalid_pdf_existing",
        "invalid_pdf_content",
    }:
        props["pdf_status"] = paper_pdf_status
    if normalize(paper_props.get("fulltext_status", "")) == "converted":
        props["fulltext_status"] = "converted"
    for field in (
        "fulltext_artifact_path",
        "fulltext_backend",
        "fulltext_char_count",
        "fulltext_section_count",
    ):
        paper_value = paper_props.get(field, "")
        if normalize(paper_value) and not normalize(props.get(field, "")):
            props[field] = paper_value
    return props


def status_label(value: str) -> str:
    text = normalize(value).replace("_", " ")
    return text[:1].upper() + text[1:] if text else "Unknown"


def labeled_reason_counts(counter: Counter, labels: dict[str, str], order: tuple[str, ...]) -> list[dict]:
    ordered_keys = [key for key in order if counter.get(key)]
    ordered_keys.extend(sorted(key for key in counter if key not in set(ordered_keys) and counter[key]))
    return [
        {
            "key": key,
            "label": labels.get(key, status_label(key)),
            "count": counter[key],
        }
        for key in ordered_keys
    ]


def kg_inclusion_route(props: dict) -> str:
    levels = props.get("kg_claim_access_levels") if isinstance(props.get("kg_claim_access_levels"), dict) else {}
    has_full_text = int(levels.get("full_text_seen", 0) or 0) > 0
    has_abstract = int(levels.get("abstract_only", 0) or 0) > 0
    has_secondary = int(levels.get("secondary_summary", 0) or 0) > 0
    fulltext_converted = normalize(props.get("fulltext_status", "")) == "converted"
    if fulltext_converted and has_full_text:
        return "included_full_text"
    if fulltext_converted and has_secondary:
        return "included_secondary_full_text"
    if has_abstract:
        return "included_abstract_only"
    if has_secondary:
        return "included_secondary_without_full_text"
    if has_full_text:
        return "included_full_text"
    return ""


def extraction_records_for(props: dict, access_levels: set[str]) -> list[dict]:
    records = props.get("extraction_records")
    if not isinstance(records, list):
        return []
    return [
        record
        for record in records
        if isinstance(record, dict) and normalize(record.get("access_level", "")) in access_levels
    ]


def extraction_outcome_for(props: dict, *, access_levels: set[str], included_routes: set[str]) -> str:
    inclusion_route = kg_inclusion_route(props)
    if inclusion_route in included_routes:
        return inclusion_route
    records = extraction_records_for(props, access_levels)
    routes = {normalize(record.get("route", "")) for record in records}
    if "exclude" in routes:
        return "gemini_excluded"
    if "human_review" in routes:
        return "needs_human_review"
    if records:
        return "assessed_no_kg_record"
    return "not_yet_extracted"


def prisma_flow_for_dataset(dataset: str, props_rows: Iterable[dict]) -> dict:
    rows = list(props_rows)
    screened_rows = [
        props
        for props in rows
        if normalize(props.get("screening_status", "")) not in {"not_screened", "not_screened_no_abstract"}
    ]
    not_screened_rows = [
        props
        for props in rows
        if normalize(props.get("screening_status", "")) in {"not_screened", "not_screened_no_abstract"}
    ]
    advanced_rows = [
        props
        for props in screened_rows
        if normalize(props.get("relevance_suggested", "")) in RELEVANT_RELEVANCE
        or normalize(props.get("screening_status", "")) in INCLUDED_SCREENING
    ]
    not_advanced_rows = [
        props
        for props in screened_rows
        if normalize(props.get("relevance_suggested", "")) not in RELEVANT_RELEVANCE
        and normalize(props.get("screening_status", "")) not in INCLUDED_SCREENING
    ]
    retrieved_rows = [
        props
        for props in advanced_rows
        if normalize(props.get("pdf_status", "")) == "downloaded"
    ]
    converted_rows = [
        props
        for props in retrieved_rows
        if normalize(props.get("fulltext_status", "")) == "converted"
    ]
    extracted_rows = [
        props
        for props in advanced_rows
        if normalize(props.get("llm_extraction_status", "")) == "claim_available"
    ]
    non_fulltext_candidate_rows = [
        props
        for props in advanced_rows
        if normalize(props.get("fulltext_status", "")) != "converted"
    ]
    inclusion_route_counts = Counter(kg_inclusion_route(props) for props in extracted_rows)
    if "" in inclusion_route_counts:
        del inclusion_route_counts[""]
    fulltext_outcome_reasons = Counter(
        extraction_outcome_for(
            props,
            access_levels={"full_text_seen"},
            included_routes={"included_full_text", "included_secondary_full_text"},
        )
        for props in converted_rows
    )
    non_fulltext_outcome_reasons = Counter(
        extraction_outcome_for(
            props,
            access_levels={"abstract_only"},
            included_routes={"included_abstract_only", "included_secondary_without_full_text"},
        )
        for props in non_fulltext_candidate_rows
    )
    non_fulltext_extracted_count = sum(
        non_fulltext_outcome_reasons.get(key, 0)
        for key in ("included_abstract_only", "included_secondary_without_full_text")
    )
    fulltext_included_count = sum(
        fulltext_outcome_reasons.get(key, 0)
        for key in ("included_full_text", "included_secondary_full_text")
    )
    fulltext_not_yet_count = fulltext_outcome_reasons.get("not_yet_extracted", 0)
    fulltext_assessed_by_gemini_count = len(converted_rows) - fulltext_not_yet_count
    fulltext_excluded_reasons = Counter(
        {
            key: fulltext_outcome_reasons.get(key, 0)
            for key in ("gemini_excluded", "needs_human_review", "assessed_no_kg_record")
            if fulltext_outcome_reasons.get(key, 0)
        }
    )
    non_fulltext_not_yet_count = non_fulltext_outcome_reasons.get("not_yet_extracted", 0)
    non_fulltext_assessed_by_gemini_count = len(non_fulltext_candidate_rows) - non_fulltext_not_yet_count
    non_fulltext_excluded_reasons = Counter(
        {
            key: non_fulltext_outcome_reasons.get(key, 0)
            for key in ("gemini_excluded", "needs_human_review", "assessed_no_kg_record")
            if non_fulltext_outcome_reasons.get(key, 0)
        }
    )
    not_screened_reasons = Counter(normalize(props.get("screening_status", "")) or "unknown" for props in not_screened_rows)
    screening_reasons = Counter(normalize(props.get("screening_status", "")) or "unknown" for props in not_advanced_rows)
    retrieval_reasons = Counter(
        prisma_retrieval_reason(props)
        for props in advanced_rows
        if normalize(props.get("pdf_status", "")) != "downloaded"
    )
    conversion_reasons = Counter(
        normalize(props.get("fulltext_status", "")) or "unknown"
        for props in retrieved_rows
        if normalize(props.get("fulltext_status", "")) != "converted"
    )
    fulltext_not_yet_reasons = Counter({"not_started": fulltext_not_yet_count}) if fulltext_not_yet_count else Counter()

    return {
        "dataset": dataset,
        "unit": "paper-context records",
        "steps": {
            "records_identified": {"label": "Records identified", "count": len(rows)},
            "records_screened": {"label": "Records screened", "count": len(screened_rows)},
            "reports_sought": {"label": "Reports sought for retrieval", "count": len(advanced_rows)},
            "reports_retrieved": {"label": "Full-text reports retrieved", "count": len(retrieved_rows)},
            "reports_assessed": {"label": "Full-text reports assessed", "count": len(converted_rows)},
            "fulltext_gemini_assessed": {
                "label": "Full-text records assessed by Gemini",
                "count": fulltext_assessed_by_gemini_count,
            },
            "fulltext_included": {"label": "Included from full-text path", "count": fulltext_included_count},
            "included": {"label": "Records included in KG evidence layer", "count": len(extracted_rows)},
        },
        "side_boxes": {
            "removed_before_screening": {
                "label": "Records not screened",
                "count": len(not_screened_rows),
                "reasons": labeled_reason_counts(
                    not_screened_reasons,
                    PRISMA_SCREENING_REASON_LABELS,
                    ("not_screened_no_abstract", "not_screened", "unknown"),
                ),
                "note": "No records are pending before screening.",
            },
            "records_excluded": {
                "label": "Records not advanced to retrieval",
                "count": len(not_advanced_rows),
                "reasons": labeled_reason_counts(
                    screening_reasons,
                    PRISMA_SCREENING_REASON_LABELS,
                    (
                        "excluded_deterministic_prescreen",
                        "excluded_llm_irrelevant",
                        "excluded_low_signal",
                        "llm_screening_error",
                        "needs_context_review",
                        "included_synthesized_context",
                        "needs_metadata_or_manual_screen",
                        "unknown",
                    ),
                ),
            },
            "reports_not_retrieved": {
                "label": "No full-text report available",
                "count": len(advanced_rows) - len(retrieved_rows),
                "non_fulltext_flow": {
                    "candidates": {
                        "label": "Abstract-only records",
                        "count": len(non_fulltext_candidate_rows),
                    },
                    "not_extracted": {
                        "label": "Abstracts not yet extracted",
                        "count": non_fulltext_not_yet_count,
                    },
                    "assessed": {
                        "label": "Abstracts assessed by Gemini",
                        "count": non_fulltext_assessed_by_gemini_count,
                    },
                    "excluded": {
                        "label": "Excluded after abstract extraction",
                        "count": sum(non_fulltext_excluded_reasons.values()),
                        "reasons": labeled_reason_counts(
                            non_fulltext_excluded_reasons,
                            PRISMA_EXTRACTION_OUTCOME_LABELS,
                            ("gemini_excluded", "needs_human_review", "assessed_no_kg_record"),
                        ),
                    },
                    "included_abstract_only": {
                        "label": "Included from abstracts",
                        "count": inclusion_route_counts.get("included_abstract_only", 0),
                    },
                    "included_secondary_without_full_text": {
                        "label": "Included from review summaries",
                        "count": inclusion_route_counts.get("included_secondary_without_full_text", 0),
                    },
                    "included_total": {
                        "label": "Included in KG from abstracts",
                        "count": non_fulltext_extracted_count,
                    },
                },
                "reasons": labeled_reason_counts(
                    retrieval_reasons,
                    PRISMA_RETRIEVAL_REASON_LABELS,
                    (
                        "not_open_access",
                        "no_pdf_url",
                        "download_failed",
                        "unusable_pdf_image_only",
                        "skipped",
                        "missing_local_pdf",
                        "pdf_validation_failed",
                        "invalid_pdf_existing",
                        "invalid_pdf_content",
                        "not_downloaded",
                        "pdf_url_known",
                        "unknown",
                    ),
                ),
            },
            "reports_not_converted": {
                "label": "Reports not converted",
                "count": len(retrieved_rows) - len(converted_rows),
                "reasons": labeled_reason_counts(
                    conversion_reasons,
                    PRISMA_CONVERSION_REASON_LABELS,
                    ("not_converted", "artifact_present", "unknown"),
                ),
            },
            "reports_not_extracted": {
                "label": "Full-text records not yet extracted",
                "count": fulltext_not_yet_count,
                "reasons": labeled_reason_counts(
                    fulltext_not_yet_reasons,
                    PRISMA_EXTRACTION_REASON_LABELS,
                    ("not_started",),
                ),
            },
            "fulltext_excluded_after_extraction": {
                "label": "Excluded/no KG after full-text extraction",
                "count": sum(fulltext_excluded_reasons.values()),
                "reasons": labeled_reason_counts(
                    fulltext_excluded_reasons,
                    PRISMA_EXTRACTION_OUTCOME_LABELS,
                    ("gemini_excluded", "needs_human_review", "assessed_no_kg_record"),
                ),
            },
        },
    }


def schema_payload() -> dict:
    return {
        "contract_version": KG_VERSION,
        "views": {
            "pipeline_status": {
                "required": [
                    "contract_version",
                    "view",
                    "generated_at",
                    "current_stage",
                    "counts",
                    "prisma_flow_order",
                    "prisma_flow",
                ],
                "description": "Methods-page PRISMA-style paper search and screening flow with public status summary.",
            },
            "methods_bibliography": {
                "required": [
                    "contract_version",
                    "view",
                    "generated_at",
                    "unit",
                    "columns",
                    "interned_columns",
                    "string_table",
                    "stage_options",
                    "kg_options",
                    "counts",
                    "rows",
                ],
                "description": "Complete paper bibliography with sequential initial-screening, LLM-based screening, evidence-extraction, and final KG graph-projection labels.",
            },
        },
    }


def write_outputs(payloads: dict, out_dir: Path) -> dict:
    outputs = {}
    outputs["schema"] = str(out_dir / "schema" / "methods_flow.schema.json")
    write_json(Path(outputs["schema"]), schema_payload())

    outputs["pipeline_status_graph"] = str(out_dir / "views" / "pipeline_status_graph.json")
    write_json(Path(outputs["pipeline_status_graph"]), payloads["pipeline_status"])

    outputs["methods_bibliography"] = str(out_dir / "views" / "methods_bibliography.json")
    write_compact_json(Path(outputs["methods_bibliography"]), payloads["methods_bibliography"])

    manifest = dict(payloads["manifest"])
    manifest["outputs"] = outputs
    outputs["manifest"] = str(out_dir / "manifests" / "build_manifest.json")
    write_json(Path(outputs["manifest"]), manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the methods-page paper-flow projection")
    parser.add_argument("--out-dir", default=str(ROOT / "data" / "kg"), help="Output directory for generated methods flow files")
    parser.add_argument(
        "--kg-dir",
        default="",
        help="Explicit routed KG directory for staged builds; otherwise use graph_payload_active.json.",
    )
    parser.add_argument(
        "--refresh-kg-tables",
        action="store_true",
        help="Regenerate normalized KG evidence tables before building the methods flow.",
    )
    args = parser.parse_args()

    if args.refresh_kg_tables:
        try:
            from pipeline.kg.build_evidence_tables import build_tables
        except ModuleNotFoundError:  # pragma: no cover - direct script execution path
            sys.path.insert(0, str(ROOT))
            from pipeline.kg.build_evidence_tables import build_tables
        build_tables()

    out_dir = Path(args.out_dir).resolve()
    builder = MethodsFlowBuilder(ROOT, routed_kg_dir=Path(args.kg_dir) if args.kg_dir else None)
    payloads = builder.build()
    manifest = write_outputs(payloads, out_dir)

    print(f"Methods flow outputs: {out_dir}")
    for key, value in manifest["counts"].items():
        print(f"- {key}: {value}")
    print(f"Manifest: {out_dir / 'manifests' / 'build_manifest.json'}")
    if manifest["warnings"]:
        print(f"Warnings: {len(manifest['warnings'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
