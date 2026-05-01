#!/usr/bin/env python3
"""Run local Ollama-based full-text evidence assessment over a QA sample.

This is a non-destructive semantic layer. It reads sampled triage rows, supplies
the local model with claim metadata plus bounded full-text evidence chunks, asks
for strict JSON, and verifies that the returned quote appears in the supplied
evidence context.

By default (non-dry), each finished row appends JSON to *.checkpoint.jsonl next
to --out-json; use --resume-from-checkpoint to skip keys already checkpointed,
mirroring screening durability.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from typing import Iterable, List

try:
    from pipeline.fulltext.build_provenance_repair_report import best_extraction
    from pipeline.fulltext.convert_pdfs import compact_text, load_json_object, normalize, normalize_doi
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from pipeline.fulltext.build_provenance_repair_report import best_extraction
    from pipeline.fulltext.convert_pdfs import compact_text, load_json_object, normalize, normalize_doi

ROOT = Path(__file__).resolve().parents[2]
FULLTEXT_DIR = ROOT / "data" / "processed" / "fulltext"
DEFAULT_INPUT = FULLTEXT_DIR / "evidence_triage_qa_sample.json"
DEFAULT_OUT_JSON = FULLTEXT_DIR / "local_llm_evidence_adjudication.json"
DEFAULT_OUT_CSV = FULLTEXT_DIR / "local_llm_evidence_adjudication.csv"
DEFAULT_ASSESSMENT_OUT_JSON = FULLTEXT_DIR / "local_llm_evidence_assessment.json"
DEFAULT_ASSESSMENT_OUT_CSV = FULLTEXT_DIR / "local_llm_evidence_assessment.csv"
DEFAULT_ABSTRACT_ONLY_OUT_JSON = FULLTEXT_DIR / "local_llm_abstract_only_adjudication.json"
DEFAULT_ABSTRACT_ONLY_OUT_CSV = FULLTEXT_DIR / "local_llm_abstract_only_adjudication.csv"
DEFAULT_ABSTRACT_ONLY_ASSESSMENT_OUT_JSON = FULLTEXT_DIR / "local_llm_abstract_only_assessment.json"
DEFAULT_ABSTRACT_ONLY_ASSESSMENT_OUT_CSV = FULLTEXT_DIR / "local_llm_abstract_only_assessment.csv"
DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_MODEL = "qwen3:14b"
EVIDENCE_MODES = ("full_text", "abstract_only", "auto")
ASSESSMENT_STAGE = "full_text_evidence_assessment"
ASSESSMENT_SCHEMA_VERSION = "full_text_evidence_assessment_v1"

SOURCE_TYPES = [
    "primary_study",
    "secondary_evidence",
    "commentary",
    "study_protocol",
    "correction",
    "conference_abstract",
    "case_report",
    "uncertain",
]
SOURCE_FAMILIES = [
    "original_empirical",
    "evidence_synthesis",
    "opinion_or_commentary",
    "protocol",
    "correction",
    "conference_abstract",
    "uncertain",
]
PAPER_TYPES = [
    "primary_results",
    "systematic_review",
    "meta_analysis",
    "review",
    "commentary",
    "protocol",
    "correction",
    "conference_abstract",
    "case_report",
    "uncertain",
]
EVIDENCE_STRENGTHS = ["high", "medium", "low", "very_low", "not_applicable", "uncertain"]
SUPPORT_VALUES = ["supported", "not_supported", "insufficient_evidence", "not_applicable"]
IN_SCOPE_VALUES = ["yes", "no", "uncertain"]
BEST_EVIDENCE_LOCATIONS = ["abstract", "methods", "results", "discussion", "table", "figure", "supplement", "full_text", "none"]
DATA_EXTRACTION_FIELDS = [
    "sample_size_total",
    "sample_size_by_arm",
    "included_study_count",
    "included_participant_count",
    "search_databases",
    "synthesis_method",
    "heterogeneity",
    "publication_bias_assessment",
    "population_or_condition",
    "participant_age",
    "participant_sex_gender",
    "study_setting",
    "country_or_region",
    "comparator",
    "intervention_or_exposure",
    "dose",
    "route",
    "session_count_or_duration",
    "trial_phase",
    "randomization",
    "blinding",
    "follow_up_duration",
    "primary_outcome",
    "outcome_measure",
    "timepoint",
    "effect_size",
    "effect_direction",
    "p_value",
    "confidence_interval",
    "adverse_events",
    "serious_adverse_events",
    "trial_registry_ids",
    "funding",
    "conflicts_of_interest",
    "risk_of_bias_notes",
]
PRIMARY_SOURCE_TYPES = {"primary_study"}
PRIMARY_SOURCE_FAMILIES = {"original_empirical"}
PRIMARY_PAPER_TYPES = {"primary_results", "case_report"}
SECONDARY_LITERATURE_SOURCE_FAMILIES = {"evidence_synthesis"}
SECONDARY_LITERATURE_SOURCE_TYPES = {"secondary_evidence", "review", "meta_analysis"}
SECONDARY_LITERATURE_PAPER_TYPES = {"systematic_review", "meta_analysis", "review"}
NON_PRIMARY_CONTEXT_SOURCE_FAMILIES = {"opinion_or_commentary", "protocol", "correction", "conference_abstract"}
NON_PRIMARY_CONTEXT_SOURCE_TYPES = {"commentary", "study_protocol", "correction", "conference_abstract"}
NON_PRIMARY_CONTEXT_PAPER_TYPES = {"commentary", "protocol", "correction", "conference_abstract"}
EVIDENCE_ROUTES = ("primary_evidence", "secondary_literature", "non_primary_context", "human_review")

DATA_EXTRACTION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {field: {"type": "string"} for field in DATA_EXTRACTION_FIELDS},
    "required": DATA_EXTRACTION_FIELDS,
}

SOURCE_CLASSIFICATION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "source_family": {"type": "string", "enum": SOURCE_FAMILIES},
        "source_type": {"type": "string", "enum": SOURCE_TYPES},
        "paper_type": {"type": "string", "enum": PAPER_TYPES},
        "study_design": {"type": "string"},
        "evidence_strength": {"type": "string", "enum": EVIDENCE_STRENGTHS},
    },
    "required": [
        "source_family",
        "source_type",
        "paper_type",
        "study_design",
        "evidence_strength",
    ],
}

ELIGIBILITY_ASSESSMENT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "is_in_scope": {"type": "string", "enum": IN_SCOPE_VALUES},
        "supports_current_claim": {"type": "string", "enum": SUPPORT_VALUES},
        "best_evidence_location": {"type": "string", "enum": BEST_EVIDENCE_LOCATIONS},
        "best_evidence_locator": {"type": "string"},
        "supporting_quote": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "needs_human_check": {"type": "boolean"},
        "reasoning_summary": {"type": "string"},
    },
    "required": [
        "is_in_scope",
        "supports_current_claim",
        "best_evidence_location",
        "best_evidence_locator",
        "supporting_quote",
        "confidence",
        "needs_human_check",
        "reasoning_summary",
    ],
}

ASSESSMENT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "assessment_stage": {"type": "string", "enum": [ASSESSMENT_STAGE]},
        "schema_version": {"type": "string", "enum": [ASSESSMENT_SCHEMA_VERSION]},
        "eligibility_assessment": ELIGIBILITY_ASSESSMENT_SCHEMA,
        "source_classification": SOURCE_CLASSIFICATION_SCHEMA,
        "data_extraction": DATA_EXTRACTION_SCHEMA,
    },
    "required": [
        "assessment_stage",
        "schema_version",
        "eligibility_assessment",
        "source_classification",
        "data_extraction",
    ],
}

LEGACY_ADJUDICATION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "source_family": {"type": "string", "enum": SOURCE_FAMILIES},
        "source_type": {"type": "string", "enum": SOURCE_TYPES},
        "paper_type": {"type": "string", "enum": PAPER_TYPES},
        "study_design": {"type": "string"},
        "evidence_strength": {"type": "string", "enum": EVIDENCE_STRENGTHS},
        "supports_current_claim": {"type": "string", "enum": SUPPORT_VALUES},
        "best_evidence_location": {"type": "string", "enum": BEST_EVIDENCE_LOCATIONS},
        "best_evidence_locator": {"type": "string"},
        "supporting_quote": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "needs_human_check": {"type": "boolean"},
        "reasoning_summary": {"type": "string"},
        "extracted_variables": DATA_EXTRACTION_SCHEMA,
    },
    "required": [
        "source_family",
        "source_type",
        "paper_type",
        "study_design",
        "evidence_strength",
        "supports_current_claim",
        "best_evidence_location",
        "best_evidence_locator",
        "supporting_quote",
        "confidence",
        "needs_human_check",
        "reasoning_summary",
        "extracted_variables",
    ],
}

# Backward-compatible export for older callers. New model calls use
# ASSESSMENT_SCHEMA and return an "assessment" object plus a legacy
# "adjudication" mirror.
ADJUDICATION_SCHEMA = LEGACY_ADJUDICATION_SCHEMA


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def load_sample_rows(path: Path) -> List[dict]:
    data = load_json(path)
    if isinstance(data, dict) and isinstance(data.get("rows"), list):
        rows = [row for row in data["rows"] if isinstance(row, dict)]
        if rows and any(is_abstract_screening_result(row) for row in rows):
            return abstract_screening_rows_to_assessment_rows(rows)
        return rows
    if isinstance(data, list):
        rows = [row for row in data if isinstance(row, dict)]
        if rows and any(is_abstract_screening_result(row) for row in rows):
            return abstract_screening_rows_to_assessment_rows(rows)
        return rows
    raise ValueError(f"Expected JSON array or object with rows at {path}")


def is_abstract_screening_result(row: dict) -> bool:
    adjudication = row.get("adjudication", {})
    return (
        isinstance(row.get("input_row"), dict)
        and isinstance(adjudication, dict)
        and "supporting_abstract_quote" in adjudication
        and "relevance" in adjudication
    )


def abstract_screening_rows_to_assessment_rows(results: List[dict]) -> List[dict]:
    """Expand abstract-screening results into evidence-assessment rows.

    Verified compound/entity contexts become claim-level rows. Relevant or
    uncertain papers without verified contexts still get one DOI-level row so
    abstract-only source/provenance details can be assessed without inventing a
    compound/entity claim.
    """
    rows: List[dict] = []
    seen: set[tuple[str, str, str]] = set()
    for result in results:
        if not is_abstract_screening_result(result):
            continue
        flat = result.get("flat", {}) if isinstance(result.get("flat"), dict) else {}
        if flat.get("status") and flat.get("status") != "ok":
            continue
        adjudication = result.get("adjudication", {})
        relevance = normalize(adjudication.get("relevance", ""))
        if relevance not in {"relevant", "uncertain"}:
            continue
        input_row = result.get("input_row", {})
        abstract = normalize(input_row.get("abstract", ""))
        if not abstract:
            continue
        dataset = normalize(flat.get("dataset", "")) or normalize(input_row.get("dataset", ""))
        contexts = result.get("verification", {}).get("verified_supported_contexts", [])
        if not isinstance(contexts, list):
            contexts = []
        if not contexts:
            contexts = [{"compound": "", "entity": "", "confidence": "", "supporting_quote": ""}]
        for ctx in contexts:
            if not isinstance(ctx, dict):
                continue
            doi = normalize(input_row.get("study_doi", ""))
            compound = normalize(ctx.get("compound", ""))
            entity = normalize(ctx.get("entity", ""))
            key = (doi.lower(), compound.lower(), entity.lower())
            if key in seen:
                continue
            seen.add(key)
            rows.append(
                {
                    "dataset": dataset,
                    "sample_group": "abstract_only_fallback",
                    "row_index": input_row.get("row_index", ""),
                    "study_doi": doi,
                    "study_title": normalize(input_row.get("study_title", "")),
                    "study_year": normalize(input_row.get("study_year", "")),
                    "authors": normalize(input_row.get("authors", "")),
                    "abstract": abstract,
                    "compound": compound,
                    "entity": entity,
                    "classification": f"abstract_screening_{relevance}",
                    "abstract_screening_relevance": relevance,
                    "abstract_context_quote": normalize(ctx.get("supporting_quote", "")),
                    "pdf_download_status": normalize(input_row.get("pdf_download_status", "")),
                    "artifact_path": "",
                    "evidence_mode_hint": "abstract_only",
                }
            )
    return rows


def abstract_screening_rows_to_adjudication_rows(results: List[dict]) -> List[dict]:
    """Backward-compatible alias for older evidence-adjudication callers."""
    return abstract_screening_rows_to_assessment_rows(results)


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: Iterable[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "status",
        "assessment_stage",
        "assessment_schema_version",
        "evidence_mode",
        "evidence_route",
        "primary_graph_eligible",
        "secondary_graph_eligible",
        "retain_in_database",
        "retain_in_secondary_view",
        "routing_reason",
        "quote_verified",
        "ollama_wall_sec",
        "dataset",
        "sample_group",
        "row_index",
        "study_doi",
        "study_title",
        "classification",
        "llm_source_family",
        "llm_source_type",
        "llm_paper_type",
        "llm_study_design",
        "llm_evidence_strength",
        "llm_is_in_scope",
        "llm_supports_current_claim",
        "llm_confidence",
        "llm_needs_human_check",
        "llm_best_evidence_location",
        "llm_best_evidence_locator",
        "llm_supporting_quote",
        "llm_reasoning_summary",
        *[f"llm_{field}" for field in DATA_EXTRACTION_FIELDS],
        "semantic_auto_eligible",
        "error",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def default_checkpoint_jsonl_path(out_json: Path) -> Path:
    return out_json.parent / f"{out_json.stem}.checkpoint.jsonl"


def truncate_checkpoint(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")


def append_checkpoint_result(path: Path, result: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(result, ensure_ascii=False) + "\n")
        handle.flush()
        try:
            os.fsync(handle.fileno())
        except OSError:
            pass


def input_row_dict_for_checkpoint_key(record: dict) -> dict | None:
    """Best-effort input row for stable resume keys; prefers input_row."""
    ir = record.get("input_row")
    if isinstance(ir, dict):
        return ir
    flat = record.get("flat")
    if isinstance(flat, dict):
        return {
            "dataset": flat.get("dataset", ""),
            "study_doi": flat.get("study_doi", ""),
            "compound": "",
            "entity": "",
            "row_index": flat.get("row_index", ""),
            "sample_group": flat.get("sample_group", ""),
        }
    return None


def checkpoint_row_key(row: dict) -> str:
    """Stable key across multiple claim rows sharing the same DOI."""
    dataset = normalize_for_match(row.get("dataset", ""))
    doi = normalize_doi(row.get("study_doi", ""))
    compound = normalize_for_match(row.get("compound", ""))
    entity = normalize_for_match(row.get("entity", ""))
    row_idx = normalize(row.get("row_index", ""))
    sample_group = normalize_for_match(row.get("sample_group", ""))
    return f"{dataset}|{doi}|{compound}|{entity}|{row_idx}|{sample_group}"


def load_checkpoint_results(path: Path) -> dict[str, dict]:
    """Last line per checkpoint_row_key wins (same semantics as screening JSONL)."""
    if not path.exists():
        return {}
    out: dict[str, dict] = {}
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if not isinstance(rec, dict):
                continue
            keyed = input_row_dict_for_checkpoint_key(rec)
            if keyed is None:
                continue
            key = checkpoint_row_key(keyed)
            if key:
                out[key] = rec
    return out


def checkpoint_removes_for_dois(checkpoint_map: dict[str, dict], doi_set: set[str]) -> int:
    """Drop checkpoint rows whose normalized DOI is in doi_set."""
    removed = 0
    for key in list(checkpoint_map.keys()):
        keyed = input_row_dict_for_checkpoint_key(checkpoint_map[key])
        if keyed is None:
            continue
        if normalize_doi(keyed.get("study_doi", "")).lower() in doi_set:
            del checkpoint_map[key]
            removed += 1
    return removed


def load_reprocess_doi_set(path: Path) -> set[str]:
    if not path.is_file():
        raise SystemExit(f"--reprocess-dois-file not found: {path}")
    out: set[str] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        doi = normalize_doi(line.split(",", 1)[0]).lower()
        if doi:
            out.add(doi)
    return out


def checkpoint_writes_enabled(args: argparse.Namespace) -> bool:
    return not bool(getattr(args, "no_checkpoint", False)) and not bool(getattr(args, "dry_run", False))


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def element_text(element: ET.Element) -> str:
    return compact_text(" ".join(text for text in element.itertext() if normalize(text)))


def chunks_from_tei(tei_xml: str, max_chunk_chars: int = 1400) -> List[dict]:
    try:
        root = ET.fromstring(tei_xml)
    except ET.ParseError:
        return []

    chunks: List[dict] = []
    for parent in root.iter():
        parent_name = local_name(parent.tag)
        if parent_name not in {"front", "body"}:
            continue
        for element in parent.iter():
            name = local_name(element.tag)
            if name == "abstract":
                text = element_text(element)
                if text:
                    chunks.append({"heading": "Abstract", "text": text[:max_chunk_chars]})
                continue
            if name != "div":
                continue
            heading = "Section"
            paragraphs = []
            for child in element.iter():
                child_name = local_name(child.tag)
                if child_name == "head" and heading == "Section":
                    heading = element_text(child) or "Section"
                elif child_name == "p":
                    text = element_text(child)
                    if text:
                        paragraphs.append(text)
            text = compact_text(" ".join(paragraphs))
            if text:
                chunks.append({"heading": heading, "text": text[:max_chunk_chars]})
    return chunks


def chunks_from_sections(sections: List[dict], max_chunk_chars: int = 1400) -> List[dict]:
    chunks = []
    for section in sections:
        if not isinstance(section, dict):
            continue
        text = normalize(section.get("snippet", ""))
        if not text:
            continue
        chunks.append({"heading": normalize(section.get("heading", "")) or "Section", "text": text[:max_chunk_chars]})
    return chunks


def chunks_from_abstract_row(row: dict, max_chunk_chars: int = 4000) -> List[dict]:
    title = normalize(row.get("study_title", ""))
    abstract = normalize(row.get("abstract", ""))
    if not abstract:
        return []
    text = compact_text(f"Title: {title}\nAbstract: {abstract}" if title else f"Abstract: {abstract}")
    return [{"id": "A001", "heading": "Abstract", "text": text[:max_chunk_chars]}]


def row_terms(row: dict) -> set[str]:
    terms = set()
    for key in [
        "compound",
        "entity",
        "study_title",
        "classification",
        "current_source_type",
        "target_source_type",
        "current_paper_type",
        "target_paper_type",
        "current_study_design",
        "target_study_design",
        "signals",
    ]:
        for token in re.findall(r"[a-zA-Z][a-zA-Z0-9-]{2,}", normalize(row.get(key, "")).lower()):
            terms.add(token)
    terms.update(
        {
            "randomized",
            "participants",
            "patients",
            "methods",
            "results",
            "outcome",
            "sample",
            "placebo",
            "review",
            "protocol",
            "case",
            "erratum",
            "correction",
            "commentary",
            "meta-analysis",
        }
    )
    return terms


def score_chunk(chunk: dict, terms: set[str]) -> int:
    haystack = f"{chunk.get('heading', '')} {chunk.get('text', '')}".lower()
    score = sum(1 for term in terms if term in haystack)
    heading = normalize(chunk.get("heading", "")).lower()
    if any(marker in heading for marker in ["abstract", "method", "result", "outcome", "table", "figure"]):
        score += 4
    return score


def select_evidence_chunks(row: dict, artifact: dict, max_chunks: int, max_chars: int) -> List[dict]:
    extraction = best_extraction(artifact)
    if not extraction:
        return []
    raw_text = normalize(extraction.get("text", ""))
    chunks = chunks_from_tei(raw_text) if raw_text.lstrip().startswith("<") else []
    if not chunks:
        chunks = chunks_from_sections(extraction.get("sections", []))

    terms = row_terms(row)
    first_chunks = chunks[:4]
    ranked = sorted(chunks[4:], key=lambda chunk: score_chunk(chunk, terms), reverse=True)
    selected = []
    seen = set()
    total_chars = 0
    for chunk in [*first_chunks, *ranked]:
        key = (chunk.get("heading", ""), chunk.get("text", "")[:80])
        if key in seen:
            continue
        seen.add(key)
        text = normalize(chunk.get("text", ""))
        if not text:
            continue
        if total_chars + len(text) > max_chars and selected:
            continue
        selected.append({"id": f"C{len(selected) + 1:03d}", "heading": chunk.get("heading", "Section"), "text": text})
        total_chars += len(text)
        if len(selected) >= max_chunks:
            break
    return selected


def evidence_context(chunks: List[dict]) -> str:
    return "\n\n".join(f"[{chunk['id']}] {chunk['heading']}\n{chunk['text']}" for chunk in chunks)


def artifact_path_from_row(row: dict) -> Path | None:
    raw = normalize(row.get("artifact_path", ""))
    return Path(raw).expanduser() if raw else None


def row_has_full_text(row: dict) -> bool:
    artifact_path = artifact_path_from_row(row)
    return (
        normalize(row.get("pdf_local_path", "")) != ""
        or normalize(row.get("pdf_download_status", "")).lower() == "downloaded"
        or (artifact_path is not None and artifact_path.exists())
    )


def normalize_for_match(value: object) -> str:
    text = re.sub(r"\s+", " ", normalize(value).lower()).strip()
    return text.strip("\"'“”‘’ ")


def quote_fragments_for_match(quote: object, min_chars: int = 6) -> list[str]:
    """Split LLM quotes that use ellipses while ignoring tiny boundary fragments."""
    text = normalize_for_match(quote)
    if not text:
        return []
    if not re.search(r"\[\s*\.\s*\.\s*\.\s*\]|\.{3,}|…", text):
        return [text]
    fragments = [normalize_for_match(part) for part in re.split(r"\[\s*\.\s*\.\s*\.\s*\]|\.{3,}|…", text)]
    return [fragment for fragment in fragments if len(fragment) >= min_chars]


def quote_found_in_context(quote: object, context: str) -> bool:
    quote_norm = normalize_for_match(quote)
    if not quote_norm or quote_norm in {"not_found", "not reported", "none", "n/a"}:
        return False
    context_norm = normalize_for_match(context)
    if quote_norm in context_norm:
        return True
    fragments = quote_fragments_for_match(quote_norm)
    return len(fragments) > 1 and all(fragment in context_norm for fragment in fragments)


def ollama_request_timeout(timeout_sec: int | None) -> int | None:
    """Return urllib timeout; <=0 means wait indefinitely for local inference."""
    if timeout_sec is None:
        return None
    return None if timeout_sec <= 0 else timeout_sec


def build_prompt(row: dict, chunks: List[dict], evidence_mode: str = "full_text") -> list[dict]:
    claim_fields = {
        "dataset": row.get("dataset", ""),
        "sample_group": row.get("sample_group", ""),
        "study_doi": row.get("study_doi", ""),
        "study_title": row.get("study_title", ""),
        "compound": row.get("compound", ""),
        "entity": row.get("entity", ""),
        "current_source_type": row.get("current_source_type", ""),
        "current_paper_type": row.get("current_paper_type", ""),
        "current_study_design": row.get("current_study_design", ""),
        "rule_classification": row.get("classification", ""),
        "rule_source_family": row.get("source_family", ""),
        "rule_evidence_strength": row.get("evidence_strength", ""),
        "rule_confidence": row.get("confidence", ""),
        "rule_signals": row.get("signals", ""),
        "evidence_mode": evidence_mode,
    }
    abstract_only = evidence_mode == "abstract_only"
    user_payload = {
        "task": (
            "Assess paper eligibility, classify the evidence source, and extract key study variables using only the supplied abstract."
            if abstract_only
            else "Assess paper eligibility, classify the evidence source, and extract key study variables using only the supplied evidence chunks."
        ),
        "assessment_stage": ASSESSMENT_STAGE,
        "schema_version": ASSESSMENT_SCHEMA_VERSION,
        "claim_or_row": claim_fields,
        "evidence_chunks": chunks,
        "required_output_sections": [
            "eligibility_assessment",
            "source_classification",
            "data_extraction",
        ],
        "data_extraction_fields": DATA_EXTRACTION_FIELDS,
        "instructions": [
            "Set assessment_stage and schema_version exactly to the provided values.",
            "Use eligibility_assessment for in-scope/relevance and claim support decisions.",
            "Use source_classification for source_family, source_type, paper_type, study_design, and evidence_strength.",
            "Use data_extraction for explicit study variables; use not_reported when a variable is absent from the supplied evidence.",
            "This is an abstract-only fallback for a paper without available full text; all extracted details are provisional and limited to the supplied abstract."
            if abstract_only
            else "This is a full-text evidence assessment pass using bounded full-text evidence chunks.",
            "source_family=original_empirical means original data, including clinical trials, observational studies, case reports, case series, preclinical animal studies, in vitro assays, and binding/uptake experiments.",
            "source_family=evidence_synthesis means systematic review, meta-analysis, or narrative review.",
            "source_family=opinion_or_commentary means editorial, letter, perspective, critique, or viewpoint.",
            "source_family=protocol means planned study/protocol without outcome results.",
            "source_family=correction means a correction-like publishing artifact, with source_type=correction and paper_type=correction.",
            "Correction labels describe publication status, not scientific content: do not use them for ordinary research articles, reviews, surveys, or analyses that discuss correcting, updating, or improving evidence or practice.",
            "Case reports and case series are original_empirical but usually low evidence_strength.",
            "Systematic reviews, meta-analyses, and narrative reviews are secondary literature: set source_family=evidence_synthesis, source_type=secondary_evidence, and paper_type to systematic_review, meta_analysis, or review as appropriate.",
            "Do not force secondary literature into primary_study or primary_results; it will be retained for a secondary-source graph view rather than treated as failed primary evidence.",
            "Protocols, commentaries, conference abstracts, corrections, and errata are non-primary context records; label them explicitly and do not extract primary-effect details unless the detail is directly stated.",
            "For is_in_scope, judge whether the paper belongs in this knowledge-graph scope based only on supplied evidence.",
            "For supports_current_claim, judge whether the supplied chunks support the row's compound plus entity relationship.",
            "If compound or entity is blank, set supports_current_claim to not_applicable and extract only paper-level details that are explicit in the abstract."
            if abstract_only
            else "If compound or entity is blank, set supports_current_claim to not_applicable.",
            "For abstract-only evidence assessment, best_evidence_location must be abstract or none; never imply that methods/results/table/figure/full_text were inspected."
            if abstract_only
            else "Use the most specific best_evidence_location supported by the supplied chunks.",
            "Extract quantitative variables only when explicitly present in the supplied chunks; otherwise use not_reported.",
            "Capture sample size, population, study setting, comparator/intervention details, trial design details, outcome/timepoint, effect direction and statistics, and adverse-event details when present.",
            "For reviews and meta-analyses, also capture included study count, included participant count, databases searched, synthesis method, heterogeneity, and publication-bias assessment when present.",
            "Extract trial registry identifiers such as NCT IDs, funding, conflicts of interest, and explicit risk-of-bias limitations when present; otherwise use not_reported.",
            "supporting_quote must be an exact verbatim quote from one supplied chunk. If no exact quote supports the decision, set supporting_quote to not_found and needs_human_check to true.",
            "Do not infer from outside knowledge.",
        ],
    }
    system = (
        "You are a careful scientific evidence assessor for a psychedelics knowledge graph. "
        "Use only the provided chunks. Prefer uncertainty over overclaiming. "
        + ("Keep abstract-only outputs explicitly limited and provisional. " if abstract_only else "")
        + "Return only JSON matching the requested schema."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
    ]


def ollama_tags(ollama_url: str, timeout_sec: int) -> list[str]:
    request = urllib.request.Request(f"{ollama_url.rstrip('/')}/api/tags", method="GET")
    with urllib.request.urlopen(request, timeout=timeout_sec) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return [model.get("name", "") for model in payload.get("models", []) if isinstance(model, dict)]


def model_is_installed(model: str, ollama_url: str, timeout_sec: int) -> bool:
    try:
        names = ollama_tags(ollama_url, timeout_sec=timeout_sec)
    except Exception:
        return False
    return model in names or any(name.split(":", 1)[0] == model for name in names)


def call_ollama(
    model: str,
    messages: list[dict],
    schema: dict,
    ollama_url: str,
    timeout_sec: int | None,
    temperature: float,
    num_ctx: int,
) -> dict:
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "format": schema,
        "options": {
            "temperature": temperature,
            "num_ctx": num_ctx,
        },
    }
    request = urllib.request.Request(
        f"{ollama_url.rstrip('/')}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=ollama_request_timeout(timeout_sec)) as response:
        data = json.loads(response.read().decode("utf-8"))
    content = data.get("message", {}).get("content", "")
    if not content:
        raise ValueError("Ollama response did not include message.content")
    parsed = json.loads(content)
    if not isinstance(parsed, dict):
        raise ValueError("Ollama structured output was not a JSON object")
    return parsed


def enum_value(value: object, allowed: list[str], default: str) -> str:
    text = normalize(value)
    return text if text in allowed else default


def bounded_confidence(value: object) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return 0.0
    return min(1.0, max(0.0, confidence))


def bool_value(value: object, default: bool = True) -> bool:
    if isinstance(value, bool):
        return value
    text = normalize(value).lower()
    if text in {"true", "yes", "1"}:
        return True
    if text in {"false", "no", "0"}:
        return False
    return default


def default_extracted_variables() -> dict:
    return {key: "not_reported" for key in DATA_EXTRACTION_FIELDS}


def default_source_classification() -> dict:
    return {
        "source_family": "uncertain",
        "source_type": "uncertain",
        "paper_type": "uncertain",
        "study_design": "not_reported",
        "evidence_strength": "uncertain",
    }


def default_eligibility_assessment(evidence_mode: str = "full_text") -> dict:
    abstract_only = evidence_mode == "abstract_only"
    return {
        "is_in_scope": "uncertain",
        "supports_current_claim": "insufficient_evidence",
        "best_evidence_location": "abstract" if abstract_only else "none",
        "best_evidence_locator": "abstract" if abstract_only else "not_reported",
        "supporting_quote": "not_found",
        "confidence": 0.0,
        "needs_human_check": True,
        "reasoning_summary": "not_reported",
    }


def default_assessment(evidence_mode: str = "full_text") -> dict:
    return {
        "assessment_stage": ASSESSMENT_STAGE,
        "schema_version": ASSESSMENT_SCHEMA_VERSION,
        "eligibility_assessment": default_eligibility_assessment(evidence_mode=evidence_mode),
        "source_classification": default_source_classification(),
        "data_extraction": default_extracted_variables(),
    }


def infer_scope_from_support(supports_current_claim: str) -> str:
    if supports_current_claim == "supported":
        return "yes"
    if supports_current_claim == "not_supported":
        return "no"
    return "uncertain"


def normalize_source_classification(payload: dict) -> dict:
    source = payload.get("source_classification", payload)
    if not isinstance(source, dict):
        source = {}
    return {
        "source_family": enum_value(source.get("source_family"), SOURCE_FAMILIES, "uncertain"),
        "source_type": enum_value(source.get("source_type"), SOURCE_TYPES, "uncertain"),
        "paper_type": enum_value(source.get("paper_type"), PAPER_TYPES, "uncertain"),
        "study_design": normalize(source.get("study_design", "")) or "not_reported",
        "evidence_strength": enum_value(source.get("evidence_strength"), EVIDENCE_STRENGTHS, "uncertain"),
    }


def normalize_eligibility_assessment(payload: dict, evidence_mode: str = "full_text") -> dict:
    eligibility = payload.get("eligibility_assessment", payload)
    if not isinstance(eligibility, dict):
        eligibility = {}
    defaults = default_eligibility_assessment(evidence_mode=evidence_mode)
    supports_current_claim = enum_value(
        eligibility.get("supports_current_claim"),
        SUPPORT_VALUES,
        defaults["supports_current_claim"],
    )
    return {
        "is_in_scope": enum_value(
            eligibility.get("is_in_scope"),
            IN_SCOPE_VALUES,
            infer_scope_from_support(supports_current_claim),
        ),
        "supports_current_claim": supports_current_claim,
        "best_evidence_location": enum_value(
            eligibility.get("best_evidence_location"),
            BEST_EVIDENCE_LOCATIONS,
            defaults["best_evidence_location"],
        ),
        "best_evidence_locator": normalize(eligibility.get("best_evidence_locator", "")) or defaults["best_evidence_locator"],
        "supporting_quote": normalize(eligibility.get("supporting_quote", "")) or defaults["supporting_quote"],
        "confidence": bounded_confidence(eligibility.get("confidence", defaults["confidence"])),
        "needs_human_check": bool_value(eligibility.get("needs_human_check", defaults["needs_human_check"])),
        "reasoning_summary": normalize(eligibility.get("reasoning_summary", "")) or defaults["reasoning_summary"],
    }


def normalize_data_extraction(payload: dict) -> dict:
    variables = payload.get("data_extraction")
    if not isinstance(variables, dict):
        variables = payload.get("extracted_variables", {})
    if not isinstance(variables, dict):
        variables = {}
    defaults = default_extracted_variables()
    return {field: normalize(variables.get(field, "")) or defaults[field] for field in DATA_EXTRACTION_FIELDS}


def normalize_assessment_payload(payload: dict, evidence_mode: str = "full_text") -> dict:
    if not isinstance(payload, dict):
        payload = {}
    assessment = default_assessment(evidence_mode=evidence_mode)
    assessment["eligibility_assessment"] = normalize_eligibility_assessment(payload, evidence_mode=evidence_mode)
    assessment["source_classification"] = normalize_source_classification(payload)
    assessment["data_extraction"] = normalize_data_extraction(payload)
    return assessment


def assessment_to_legacy_adjudication(assessment: dict) -> dict:
    assessment = normalize_assessment_payload(assessment)
    eligibility = assessment["eligibility_assessment"]
    source = assessment["source_classification"]
    return {
        "source_family": source["source_family"],
        "source_type": source["source_type"],
        "paper_type": source["paper_type"],
        "study_design": source["study_design"],
        "evidence_strength": source["evidence_strength"],
        "supports_current_claim": eligibility["supports_current_claim"],
        "best_evidence_location": eligibility["best_evidence_location"],
        "best_evidence_locator": eligibility["best_evidence_locator"],
        "supporting_quote": eligibility["supporting_quote"],
        "confidence": eligibility["confidence"],
        "needs_human_check": eligibility["needs_human_check"],
        "reasoning_summary": eligibility["reasoning_summary"],
        "extracted_variables": dict(assessment["data_extraction"]),
    }


def labels_are_consistent(adjudication_or_assessment: dict) -> bool:
    source = normalize_source_classification(adjudication_or_assessment)
    source_family = source.get("source_family")
    source_type = source.get("source_type")
    paper_type = source.get("paper_type")
    if source_family == "original_empirical":
        return source_type == "primary_study" and paper_type not in {
            "systematic_review",
            "meta_analysis",
            "review",
            "commentary",
            "protocol",
            "correction",
        }
    if source_family == "evidence_synthesis":
        return source_type == "secondary_evidence" and paper_type in {"systematic_review", "meta_analysis", "review"}
    if source_family == "opinion_or_commentary":
        return source_type == "commentary" and paper_type == "commentary"
    if source_family == "protocol":
        return source_type == "study_protocol" and paper_type == "protocol"
    if source_family == "correction":
        return source_type == "correction" and paper_type == "correction"
    if source_family == "conference_abstract":
        return source_type == "conference_abstract" and paper_type == "conference_abstract"
    return False


def is_primary_evidence_source(adjudication_or_assessment: dict) -> bool:
    source = normalize_source_classification(adjudication_or_assessment)
    return (
        source.get("source_family") in PRIMARY_SOURCE_FAMILIES
        or source.get("source_type") in PRIMARY_SOURCE_TYPES
    ) and source.get("paper_type") in PRIMARY_PAPER_TYPES


def is_secondary_literature_source(adjudication_or_assessment: dict) -> bool:
    source = normalize_source_classification(adjudication_or_assessment)
    return (
        source.get("source_family") in SECONDARY_LITERATURE_SOURCE_FAMILIES
        or source.get("source_type") in SECONDARY_LITERATURE_SOURCE_TYPES
        or source.get("paper_type") in SECONDARY_LITERATURE_PAPER_TYPES
    )


def is_non_primary_context_source(adjudication_or_assessment: dict) -> bool:
    source = normalize_source_classification(adjudication_or_assessment)
    return (
        source.get("source_family") in NON_PRIMARY_CONTEXT_SOURCE_FAMILIES
        or source.get("source_type") in NON_PRIMARY_CONTEXT_SOURCE_TYPES
        or source.get("paper_type") in NON_PRIMARY_CONTEXT_PAPER_TYPES
    )


def semantic_auto_eligible(adjudication_or_assessment: dict, quote_verified: bool, min_confidence: float) -> bool:
    eligibility = normalize_eligibility_assessment(adjudication_or_assessment)
    confidence = bounded_confidence(eligibility.get("confidence", 0))
    return (
        quote_verified
        and confidence >= min_confidence
        and eligibility.get("needs_human_check") is False
        and labels_are_consistent(adjudication_or_assessment)
    )


def routing_for_assessment(assessment: dict, quote_verified: bool, min_confidence: float) -> dict:
    semantic_ok = semantic_auto_eligible(assessment, quote_verified, min_confidence=min_confidence)
    if is_primary_evidence_source(assessment):
        return {
            "evidence_route": "primary_evidence",
            "primary_graph_eligible": semantic_ok,
            "secondary_graph_eligible": False,
            "retain_in_database": True,
            "retain_in_secondary_view": False,
            "routing_reason": "original empirical paper eligible for the primary graph when semantic QA passes",
        }
    if is_secondary_literature_source(assessment):
        return {
            "evidence_route": "secondary_literature",
            "primary_graph_eligible": False,
            "secondary_graph_eligible": semantic_ok,
            "retain_in_database": True,
            "retain_in_secondary_view": True,
            "routing_reason": "review/meta-analysis retained for the secondary-source graph view",
        }
    if is_non_primary_context_source(assessment):
        return {
            "evidence_route": "non_primary_context",
            "primary_graph_eligible": False,
            "secondary_graph_eligible": False,
            "retain_in_database": True,
            "retain_in_secondary_view": False,
            "routing_reason": "non-primary publication type retained as context but excluded from default evidence views",
        }
    return {
        "evidence_route": "human_review",
        "primary_graph_eligible": False,
        "secondary_graph_eligible": False,
        "retain_in_database": True,
        "retain_in_secondary_view": False,
        "routing_reason": "uncertain source classification requires curator review",
    }


def dry_run_assessment(evidence_mode: str) -> dict:
    assessment = default_assessment(evidence_mode=evidence_mode)
    assessment["source_classification"]["study_design"] = "not_run"
    assessment["eligibility_assessment"]["best_evidence_locator"] = "abstract" if evidence_mode == "abstract_only" else "not_run"
    assessment["eligibility_assessment"]["reasoning_summary"] = "dry run; model was not called"
    return assessment


def dry_run_adjudication(evidence_mode: str) -> dict:
    """Backward-compatible legacy mirror for dry-run callers."""
    return assessment_to_legacy_adjudication(dry_run_assessment(evidence_mode))


def flatten_result(
    row: dict,
    adjudication_or_assessment: dict,
    status: str,
    quote_verified: bool,
    min_confidence: float,
    evidence_mode: str,
    error: str = "",
    ollama_wall_sec: float | str | None = None,
) -> dict:
    wall: float | str = ""
    if isinstance(ollama_wall_sec, (int, float)):
        wall = round(float(ollama_wall_sec), 3)
    elif ollama_wall_sec is not None and ollama_wall_sec != "":
        wall = ollama_wall_sec
    assessment = normalize_assessment_payload(adjudication_or_assessment, evidence_mode=evidence_mode)
    eligibility = assessment["eligibility_assessment"]
    source = assessment["source_classification"]
    variables = assessment["data_extraction"]
    routing = routing_for_assessment(assessment, quote_verified=quote_verified, min_confidence=min_confidence)
    flat = {
        "status": status,
        "assessment_stage": assessment["assessment_stage"],
        "assessment_schema_version": assessment["schema_version"],
        "evidence_mode": evidence_mode,
        **routing,
        "quote_verified": quote_verified,
        "ollama_wall_sec": wall,
        "dataset": row.get("dataset", ""),
        "sample_group": row.get("sample_group", ""),
        "row_index": row.get("row_index", ""),
        "study_doi": row.get("study_doi", ""),
        "study_title": row.get("study_title", ""),
        "classification": row.get("classification", ""),
        "llm_source_family": source.get("source_family", ""),
        "llm_source_type": source.get("source_type", ""),
        "llm_paper_type": source.get("paper_type", ""),
        "llm_study_design": source.get("study_design", ""),
        "llm_evidence_strength": source.get("evidence_strength", ""),
        "llm_is_in_scope": eligibility.get("is_in_scope", ""),
        "llm_supports_current_claim": eligibility.get("supports_current_claim", ""),
        "llm_confidence": eligibility.get("confidence", ""),
        "llm_needs_human_check": eligibility.get("needs_human_check", ""),
        "llm_best_evidence_location": eligibility.get("best_evidence_location", ""),
        "llm_best_evidence_locator": eligibility.get("best_evidence_locator", ""),
        "llm_supporting_quote": eligibility.get("supporting_quote", ""),
        "llm_reasoning_summary": eligibility.get("reasoning_summary", ""),
        "semantic_auto_eligible": semantic_auto_eligible(
            assessment,
            quote_verified,
            min_confidence=min_confidence,
        ),
        "error": error,
    }
    for field in DATA_EXTRACTION_FIELDS:
        flat[f"llm_{field}"] = variables.get(field, "")
    return flat


def evidence_chunks_for_row(row: dict, args: argparse.Namespace) -> tuple[str, List[dict]]:
    requested_mode = normalize(args.evidence_mode) or "full_text"
    artifact_path = artifact_path_from_row(row)
    if requested_mode in {"full_text", "auto"} and artifact_path is not None and artifact_path.exists():
        artifact = load_json_object(artifact_path)
        chunks = select_evidence_chunks(
            row,
            artifact,
            max_chunks=max(1, args.max_chunks),
            max_chars=max(1000, args.max_context_chars),
        )
        if chunks:
            return "full_text", chunks
        if requested_mode == "full_text":
            raise ValueError("no evidence chunks available")
    if requested_mode in {"abstract_only", "auto"}:
        chunks = chunks_from_abstract_row(row, max_chunk_chars=max(1000, min(args.max_context_chars, 6000)))
        if chunks:
            return "abstract_only", chunks
        if requested_mode == "abstract_only":
            raise ValueError("no abstract available for abstract-only evidence assessment")
    if artifact_path is None:
        raise FileNotFoundError("artifact_path is empty")
    raise FileNotFoundError(f"artifact not found: {artifact_path}")


def assess_row(row: dict, args: argparse.Namespace) -> dict:
    evidence_mode, chunks = evidence_chunks_for_row(row, args)
    messages = build_prompt(row, chunks, evidence_mode=evidence_mode)
    context = evidence_context(chunks)
    if args.dry_run:
        assessment = dry_run_assessment(evidence_mode)
    else:
        assessment = call_ollama(
            model=args.model,
            messages=messages,
            schema=ASSESSMENT_SCHEMA,
            ollama_url=args.ollama_url,
            timeout_sec=ollama_request_timeout(args.timeout_sec),
            temperature=max(0.0, args.temperature),
            num_ctx=max(2048, args.num_ctx),
        )
    assessment = normalize_assessment_payload(assessment, evidence_mode=evidence_mode)
    adjudication = assessment_to_legacy_adjudication(assessment)
    quote_verified = quote_found_in_context(assessment["eligibility_assessment"].get("supporting_quote", ""), context)
    routing = routing_for_assessment(assessment, quote_verified=quote_verified, min_confidence=args.auto_confidence)
    return {
        "input_row": row,
        "evidence_mode": evidence_mode,
        "evidence_chunks": chunks,
        "assessment": assessment,
        "adjudication": adjudication,
        "routing": routing,
        "verification": {
            "quote_verified": quote_verified,
            "chunk_count": len(chunks),
            "context_char_count": len(context),
            "semantic_auto_eligible": semantic_auto_eligible(
                assessment,
                quote_verified,
                min_confidence=args.auto_confidence,
            ),
        },
        "flat": flatten_result(
            row,
            assessment,
            status="ok",
            quote_verified=quote_verified,
            min_confidence=args.auto_confidence,
            evidence_mode=evidence_mode,
        ),
    }


def adjudicate_row(row: dict, args: argparse.Namespace) -> dict:
    """Backward-compatible alias for the renamed evidence assessment step."""
    return assess_row(row, args)


def normalize_existing_result_for_current_schema(
    result: dict,
    min_confidence: float,
    fallback_evidence_mode: str = "full_text",
) -> dict:
    """Upgrade checkpointed legacy rows to the current assessment shape."""
    if not isinstance(result, dict):
        return result
    flat = result.get("flat") if isinstance(result.get("flat"), dict) else {}
    verification = result.get("verification") if isinstance(result.get("verification"), dict) else {}
    evidence_mode = normalize(result.get("evidence_mode", "")) or normalize(flat.get("evidence_mode", "")) or fallback_evidence_mode
    row = input_row_dict_for_checkpoint_key(result) or {}
    payload = result.get("assessment") if isinstance(result.get("assessment"), dict) else result.get("adjudication", {})
    assessment = normalize_assessment_payload(payload, evidence_mode=evidence_mode)
    adjudication = assessment_to_legacy_adjudication(assessment)
    quote_verified = bool_value(
        verification.get("quote_verified", flat.get("quote_verified", False)),
        default=False,
    )
    status = normalize(flat.get("status", "")) or ("failed" if result.get("error") else "ok")
    error = normalize(result.get("error", "")) or normalize(flat.get("error", ""))
    wall = result.get("ollama_wall_sec", flat.get("ollama_wall_sec", ""))
    result["evidence_mode"] = evidence_mode
    result["assessment"] = assessment
    result["adjudication"] = adjudication
    result["routing"] = routing_for_assessment(assessment, quote_verified=quote_verified, min_confidence=min_confidence)
    result["verification"] = {
        **verification,
        "quote_verified": quote_verified,
        "semantic_auto_eligible": semantic_auto_eligible(
            assessment,
            quote_verified,
            min_confidence=min_confidence,
        ),
    }
    result["flat"] = flatten_result(
        row,
        assessment,
        status=status,
        quote_verified=quote_verified,
        min_confidence=min_confidence,
        evidence_mode=evidence_mode,
        error=error,
        ollama_wall_sec=wall,
    )
    return result


def selected_rows(rows: List[dict], limit: int, offset: int) -> List[dict]:
    start = max(0, offset)
    end = None if limit <= 0 else start + limit
    return rows[start:end]


def filter_rows(rows: List[dict], args: argparse.Namespace) -> List[dict]:
    out = []
    for row in rows:
        if args.only_without_fulltext and row_has_full_text(row):
            continue
        if args.only_with_abstract and not normalize(row.get("abstract", "")):
            continue
        out.append(row)
    return out


def invoked_as_assessment_entrypoint() -> bool:
    return Path(sys.argv[0]).name == "run_local_llm_evidence_assessment.py"


def default_output_paths() -> tuple[Path, Path, Path, Path]:
    if invoked_as_assessment_entrypoint():
        return (
            DEFAULT_ASSESSMENT_OUT_JSON,
            DEFAULT_ASSESSMENT_OUT_CSV,
            DEFAULT_ABSTRACT_ONLY_ASSESSMENT_OUT_JSON,
            DEFAULT_ABSTRACT_ONLY_ASSESSMENT_OUT_CSV,
        )
    return (
        DEFAULT_OUT_JSON,
        DEFAULT_OUT_CSV,
        DEFAULT_ABSTRACT_ONLY_OUT_JSON,
        DEFAULT_ABSTRACT_ONLY_OUT_CSV,
    )


def parse_args() -> argparse.Namespace:
    default_out_json, default_out_csv, default_abstract_json, default_abstract_csv = default_output_paths()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default=str(DEFAULT_INPUT), help="QA sample JSON path")
    parser.add_argument("--out-json", default=str(default_out_json))
    parser.add_argument("--out-csv", default=str(default_out_csv))
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--ollama-url", default=DEFAULT_OLLAMA_URL)
    parser.add_argument(
        "--evidence-mode",
        choices=EVIDENCE_MODES,
        default="full_text",
        help="Use full-text artifacts, abstract-only fallback, or auto-select full text then abstract",
    )
    parser.add_argument(
        "--only-without-fulltext",
        action="store_true",
        help="Skip rows that already have a downloaded PDF/full-text artifact",
    )
    parser.add_argument("--only-with-abstract", action="store_true", help="Skip rows without abstract text")
    parser.add_argument("--limit", type=int, default=0, help="Rows to process; 0 means all")
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--timeout-sec", type=int, default=240, help="Per-row Ollama timeout; 0 means wait indefinitely")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--num-ctx", type=int, default=32768)
    parser.add_argument("--max-chunks", type=int, default=18)
    parser.add_argument("--max-context-chars", type=int, default=22000)
    parser.add_argument("--auto-confidence", type=float, default=0.85)
    parser.add_argument("--dry-run", action="store_true", help="Build evidence contexts without calling Ollama")
    parser.add_argument("--skip-model-check", action="store_true")
    parser.add_argument("--continue-on-error", action="store_true")
    parser.add_argument(
        "--checkpoint-jsonl",
        default="",
        help=(
            "Append one full JSON result per completed row next to defaults; "
            "default is <out-json stem>.checkpoint.jsonl beside --out-json"
        ),
    )
    parser.add_argument(
        "--resume-from-checkpoint",
        action="store_true",
        help="Skip row keys already present in the checkpoint JSONL (last line wins for each key)",
    )
    parser.add_argument("--no-checkpoint", action="store_true", help="Disable per-row checkpoint JSONL durability")
    parser.add_argument(
        "--reprocess-dois-file",
        default="",
        help=(
            "With --resume-from-checkpoint: newline-separated DOIs (CSV first column OK); matching checkpoint entries are dropped "
            "so those rows rerun"
        ),
    )
    parser.add_argument(
        "--reprocess-all-checkpoint-rows",
        action="store_true",
        help="With --resume-from-checkpoint: ignore all checkpoint skips and rerun evidence assessment for every filtered row",
    )
    parser.add_argument(
        "--show-checkpoint-progress",
        action="store_true",
        help="Echo checkpoint skips verbosely (default still prints one line per skipped row)",
    )
    args = parser.parse_args()
    if args.resume_from_checkpoint and args.no_checkpoint:
        raise SystemExit("--resume-from-checkpoint and --no-checkpoint cannot be used together")
    if args.evidence_mode == "abstract_only":
        if args.out_json == str(default_out_json):
            args.out_json = str(default_abstract_json)
        if args.out_csv == str(default_out_csv):
            args.out_csv = str(default_abstract_csv)
    return args


def main() -> int:
    args = parse_args()
    input_path = Path(args.input).resolve()
    out_json = Path(args.out_json).resolve()
    out_csv = Path(args.out_csv).resolve()
    ckpt_path = (
        Path(args.checkpoint_jsonl).resolve()
        if normalize(args.checkpoint_jsonl)
        else default_checkpoint_jsonl_path(out_json)
    )
    rows = selected_rows(
        filter_rows(load_sample_rows(input_path), args),
        limit=max(0, args.limit),
        offset=max(0, args.offset),
    )

    if not args.dry_run and not args.skip_model_check:
        if not model_is_installed(args.model, args.ollama_url, timeout_sec=10):
            raise SystemExit(
                f"Ollama model `{args.model}` is not installed or Ollama is unavailable. "
                f"Install it with: ollama pull {args.model}"
            )

    checkpoint_map: dict[str, dict] = {}
    checkpoint_rows_reused = 0
    if args.resume_from_checkpoint:
        checkpoint_map = load_checkpoint_results(ckpt_path)
        n_loaded = len(checkpoint_map)
        print(f"Checkpoint resume: {n_loaded} row key(s) loaded from {ckpt_path}", flush=True)
        if args.reprocess_all_checkpoint_rows:
            checkpoint_map.clear()
            print(
                f"Reprocess all checkpoint rows: cleared {n_loaded} resume skip(s); LLM will run for each filtered row.",
                flush=True,
            )
        elif normalize(args.reprocess_dois_file):
            rpath = Path(args.reprocess_dois_file).resolve()
            rset = load_reprocess_doi_set(rpath)
            removed = checkpoint_removes_for_dois(checkpoint_map, rset)
            print(
                f"Reprocess DOI list {rpath}: {len(rset)} listed, {removed} checkpoint row(s) removed for rerun.",
                flush=True,
            )
    elif checkpoint_writes_enabled(args):
        truncate_checkpoint(ckpt_path)
        print(f"Checkpoint file (fresh truncate): {ckpt_path}", flush=True)

    results = []
    flat_rows = []
    status = "ok"
    for index, row in enumerate(rows, start=1):
        line_header = f"[{index}/{len(rows)}] {row.get('dataset')} row {row.get('row_index')} {row.get('study_doi')}"
        ck = checkpoint_row_key(row)
        if ck and ck in checkpoint_map and args.resume_from_checkpoint:
            result = normalize_existing_result_for_current_schema(
                checkpoint_map[ck],
                min_confidence=args.auto_confidence,
                fallback_evidence_mode=normalize(args.evidence_mode) or "full_text",
            )
            checkpoint_rows_reused += 1
            print(f"{line_header} (checkpoint)", flush=True)
            flat_cp = result["flat"] if isinstance(result.get("flat"), dict) else {}
            ver_cp = result.get("verification") if isinstance(result.get("verification"), dict) else {}
            wall = flat_cp.get("ollama_wall_sec", "")
            wall_s = f"{float(wall):.1f}s (saved)" if isinstance(wall, (int, float)) else "—"
            if args.show_checkpoint_progress:
                print(
                    f"     -> checkpoint | status={flat_cp.get('status')} | mode={flat_cp.get('evidence_mode')} | "
                    f"quote_ok={flat_cp.get('quote_verified')} | chunks={ver_cp.get('chunk_count', '')} | wall={wall_s}",
                    flush=True,
                )
            else:
                print(
                    f"     -> checkpoint | status={flat_cp.get('status')} | mode={flat_cp.get('evidence_mode')} | wall={wall_s}",
                    flush=True,
                )
            results.append(result)
            flat_rows.append(result["flat"])
            continue

        print(line_header, flush=True)
        t_row = time.perf_counter()
        try:
            result = assess_row(row, args)
            elapsed = time.perf_counter() - t_row
            result["ollama_wall_sec"] = round(elapsed, 3)
            result["flat"]["ollama_wall_sec"] = result["ollama_wall_sec"]
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, Exception) as err:
            elapsed = time.perf_counter() - t_row
            status = "failed"
            assessment = default_assessment(evidence_mode=normalize(args.evidence_mode) or "full_text")
            adjudication = assessment_to_legacy_adjudication(assessment)
            routing = routing_for_assessment(
                assessment,
                quote_verified=False,
                min_confidence=args.auto_confidence,
            )
            result = {
                "input_row": row,
                "evidence_chunks": [],
                "assessment": assessment,
                "adjudication": adjudication,
                "routing": routing,
                "verification": {"quote_verified": False, "chunk_count": 0, "context_char_count": 0},
                "error": f"{type(err).__name__}: {err}",
                "ollama_wall_sec": round(elapsed, 3),
                "flat": flatten_result(
                    row,
                    assessment,
                    status="failed",
                    quote_verified=False,
                    min_confidence=args.auto_confidence,
                    evidence_mode=normalize(args.evidence_mode) or "full_text",
                    error=f"{type(err).__name__}: {err}",
                    ollama_wall_sec=elapsed,
                ),
            }
            if not args.continue_on_error:
                results.append(result)
                flat_rows.append(result["flat"])
                if checkpoint_writes_enabled(args):
                    append_checkpoint_result(ckpt_path, result)
                flat = result["flat"]
                print(
                    f"     -> {flat.get('status')} | mode={flat.get('evidence_mode')} | "
                    f"quote_ok={flat.get('quote_verified')} | chunks=0 | {elapsed:.1f}s",
                    flush=True,
                )
                break
        results.append(result)
        flat_rows.append(result["flat"])
        if checkpoint_writes_enabled(args):
            append_checkpoint_result(ckpt_path, result)
        flat = result["flat"]
        ver = result.get("verification") if isinstance(result.get("verification"), dict) else {}
        chunk_n = ver.get("chunk_count", "")
        print(
            f"     -> {flat.get('status')} | mode={flat.get('evidence_mode')} | "
            f"quote_ok={flat.get('quote_verified')} | chunks={chunk_n} | {elapsed:.1f}s",
            flush=True,
        )

    summary = {
        "rows_requested": len(rows),
        "rows_completed": len([row for row in flat_rows if row.get("status") == "ok"]),
        "rows_failed": len([row for row in flat_rows if row.get("status") != "ok"]),
        "checkpoint_rows_reused": checkpoint_rows_reused,
        "quote_verified": len([row for row in flat_rows if row.get("quote_verified") is True]),
        "semantic_auto_eligible": len([row for row in flat_rows if row.get("semantic_auto_eligible") is True]),
        "by_status": dict(Counter(row.get("status", "") for row in flat_rows)),
        "by_llm_source_family": dict(Counter(row.get("llm_source_family", "") for row in flat_rows)),
    }
    timing_vals = [
        float(row["ollama_wall_sec"])
        for row in flat_rows
        if isinstance(row.get("ollama_wall_sec"), (int, float))
    ]
    if timing_vals:
        summary["ollama_wall_sec_mean"] = round(sum(timing_vals) / len(timing_vals), 3)
        summary["ollama_wall_sec_min"] = round(min(timing_vals), 3)
        summary["ollama_wall_sec_max"] = round(max(timing_vals), 3)
    payload = {
        "generated_at_utc": now_utc(),
        "stage": ASSESSMENT_STAGE,
        "schema_version": ASSESSMENT_SCHEMA_VERSION,
        "status": status,
        "inputs": {
            "input": str(input_path),
            "model": args.model,
            "ollama_url": args.ollama_url,
            "evidence_mode": args.evidence_mode,
            "only_without_fulltext": bool(args.only_without_fulltext),
            "only_with_abstract": bool(args.only_with_abstract),
            "limit": args.limit,
            "offset": args.offset,
            "dry_run": args.dry_run,
            "max_chunks": args.max_chunks,
            "max_context_chars": args.max_context_chars,
            "auto_confidence": args.auto_confidence,
            "checkpoint_jsonl": str(ckpt_path),
            "resume_from_checkpoint": bool(args.resume_from_checkpoint),
            "no_checkpoint": bool(args.no_checkpoint),
        },
        "summary": summary,
        "rows": results,
    }

    write_json(out_json, payload)
    write_csv(out_csv, flat_rows)

    print(f"Status: {status}")
    print(f"Rows completed: {summary['rows_completed']}")
    print(f"Rows failed: {summary['rows_failed']}")
    if checkpoint_rows_reused:
        print(f"Checkpoint rows reused: {checkpoint_rows_reused}")
    print(f"Quote verified: {summary['quote_verified']}")
    print(f"Semantic auto-eligible: {summary['semantic_auto_eligible']}")
    if timing_vals:
        print(
            "Ollama wall time sec (mean / min / max): "
            f"{summary['ollama_wall_sec_mean']} / {summary['ollama_wall_sec_min']} / {summary['ollama_wall_sec_max']}",
        )
    print(f"JSON: {out_json}")
    print(f"CSV: {out_csv}")
    if checkpoint_writes_enabled(args) or ckpt_path.exists():
        print(f"Checkpoint JSONL: {ckpt_path}")
    return 0 if status == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
