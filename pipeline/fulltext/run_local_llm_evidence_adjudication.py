#!/usr/bin/env python3
"""Run local Ollama-based evidence adjudication over a QA sample.

This is a non-destructive semantic layer. It reads sampled triage rows, supplies
the local model with claim metadata plus bounded full-text evidence chunks, asks
for strict JSON, and verifies that the returned quote appears in the supplied
evidence context.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import re
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from typing import Iterable, List

try:
    from pipeline.fulltext.build_provenance_repair_report import best_extraction
    from pipeline.fulltext.convert_pdfs import compact_text, load_json_object, normalize
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from pipeline.fulltext.build_provenance_repair_report import best_extraction
    from pipeline.fulltext.convert_pdfs import compact_text, load_json_object, normalize

ROOT = Path(__file__).resolve().parents[2]
FULLTEXT_DIR = ROOT / "data" / "processed" / "fulltext"
DEFAULT_INPUT = FULLTEXT_DIR / "evidence_triage_qa_sample.json"
DEFAULT_OUT_JSON = FULLTEXT_DIR / "local_llm_evidence_adjudication.json"
DEFAULT_OUT_CSV = FULLTEXT_DIR / "local_llm_evidence_adjudication.csv"
DEFAULT_ABSTRACT_ONLY_OUT_JSON = FULLTEXT_DIR / "local_llm_abstract_only_adjudication.json"
DEFAULT_ABSTRACT_ONLY_OUT_CSV = FULLTEXT_DIR / "local_llm_abstract_only_adjudication.csv"
DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_MODEL = "qwen3:14b"
EVIDENCE_MODES = ("full_text", "abstract_only", "auto")

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

ADJUDICATION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "source_family": {"type": "string", "enum": SOURCE_FAMILIES},
        "source_type": {"type": "string", "enum": SOURCE_TYPES},
        "paper_type": {"type": "string", "enum": PAPER_TYPES},
        "study_design": {"type": "string"},
        "evidence_strength": {"type": "string", "enum": EVIDENCE_STRENGTHS},
        "supports_current_claim": {"type": "string", "enum": SUPPORT_VALUES},
        "best_evidence_location": {
            "type": "string",
            "enum": ["abstract", "methods", "results", "discussion", "table", "figure", "supplement", "full_text", "none"],
        },
        "best_evidence_locator": {"type": "string"},
        "supporting_quote": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "needs_human_check": {"type": "boolean"},
        "reasoning_summary": {"type": "string"},
        "extracted_variables": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "sample_size_total": {"type": "string"},
                "sample_size_by_arm": {"type": "string"},
                "comparator": {"type": "string"},
                "intervention_or_exposure": {"type": "string"},
                "dose": {"type": "string"},
                "route": {"type": "string"},
                "session_count_or_duration": {"type": "string"},
                "primary_outcome": {"type": "string"},
                "outcome_measure": {"type": "string"},
                "timepoint": {"type": "string"},
                "effect_size": {"type": "string"},
                "p_value": {"type": "string"},
                "confidence_interval": {"type": "string"},
                "adverse_events": {"type": "string"},
            },
            "required": [
                "sample_size_total",
                "sample_size_by_arm",
                "comparator",
                "intervention_or_exposure",
                "dose",
                "route",
                "session_count_or_duration",
                "primary_outcome",
                "outcome_measure",
                "timepoint",
                "effect_size",
                "p_value",
                "confidence_interval",
                "adverse_events",
            ],
        },
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


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def load_sample_rows(path: Path) -> List[dict]:
    data = load_json(path)
    if isinstance(data, dict) and isinstance(data.get("rows"), list):
        rows = [row for row in data["rows"] if isinstance(row, dict)]
        if rows and any(is_abstract_screening_result(row) for row in rows):
            return abstract_screening_rows_to_adjudication_rows(rows)
        return rows
    if isinstance(data, list):
        rows = [row for row in data if isinstance(row, dict)]
        if rows and any(is_abstract_screening_result(row) for row in rows):
            return abstract_screening_rows_to_adjudication_rows(rows)
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


def abstract_screening_rows_to_adjudication_rows(results: List[dict]) -> List[dict]:
    """Expand abstract-screening results into evidence-adjudication rows.

    Verified compound/entity contexts become claim-level rows. Relevant or
    uncertain papers without verified contexts still get one DOI-level row so
    abstract-only source/provenance details can be proposed without inventing a
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


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: Iterable[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "status",
        "evidence_mode",
        "quote_verified",
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
        "llm_supports_current_claim",
        "llm_confidence",
        "llm_needs_human_check",
        "llm_best_evidence_location",
        "llm_best_evidence_locator",
        "llm_supporting_quote",
        "llm_reasoning_summary",
        "llm_sample_size_total",
        "llm_effect_size",
        "llm_p_value",
        "semantic_auto_eligible",
        "error",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


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
            "Classify the evidence source and extract key study variables using only the supplied abstract."
            if abstract_only
            else "Classify the evidence source and extract key study variables using only the supplied evidence chunks."
        ),
        "claim_or_row": claim_fields,
        "evidence_chunks": chunks,
        "instructions": [
            "Classify the paper into a source_family, source_type, paper_type, study_design, and evidence_strength.",
            "This is an abstract-only fallback for a paper without available full text; all extracted details are provisional and limited to the supplied abstract."
            if abstract_only
            else "This is a full-text adjudication pass using bounded full-text evidence chunks.",
            "source_family=original_empirical means original data, including clinical trials, observational studies, case reports, case series, preclinical animal studies, in vitro assays, and binding/uptake experiments.",
            "source_family=evidence_synthesis means systematic review, meta-analysis, or narrative review.",
            "source_family=opinion_or_commentary means editorial, letter, perspective, critique, or viewpoint.",
            "source_family=protocol means planned study/protocol without outcome results.",
            "source_family=correction means a correction-like publishing artifact, with source_type=correction and paper_type=correction.",
            "Correction labels describe publication status, not scientific content: do not use them for ordinary research articles, reviews, surveys, or analyses that discuss correcting, updating, or improving evidence or practice.",
            "Case reports and case series are original_empirical but usually low evidence_strength.",
            "For supports_current_claim, judge whether the supplied chunks support the row's compound plus entity relationship.",
            "If compound or entity is blank, set supports_current_claim to not_applicable and extract only paper-level details that are explicit in the abstract."
            if abstract_only
            else "If compound or entity is blank, set supports_current_claim to not_applicable.",
            "For abstract-only adjudication, best_evidence_location must be abstract or none; never imply that methods/results/table/figure/full_text were inspected."
            if abstract_only
            else "Use the most specific best_evidence_location supported by the supplied chunks.",
            "Extract quantitative variables only when explicitly present in the supplied chunks; otherwise use not_reported.",
            "supporting_quote must be an exact verbatim quote from one supplied chunk. If no exact quote supports the decision, set supporting_quote to not_found and needs_human_check to true.",
            "Do not infer from outside knowledge.",
        ],
    }
    system = (
        "You are a careful scientific evidence adjudicator for a psychedelics knowledge graph. "
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


def labels_are_consistent(adjudication: dict) -> bool:
    source_family = adjudication.get("source_family")
    source_type = adjudication.get("source_type")
    paper_type = adjudication.get("paper_type")
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


def semantic_auto_eligible(adjudication: dict, quote_verified: bool, min_confidence: float) -> bool:
    try:
        confidence = float(adjudication.get("confidence", 0) or 0)
    except (TypeError, ValueError):
        confidence = 0.0
    return (
        quote_verified
        and confidence >= min_confidence
        and adjudication.get("needs_human_check") is False
        and labels_are_consistent(adjudication)
    )


def default_extracted_variables() -> dict:
    return {key: "not_reported" for key in ADJUDICATION_SCHEMA["properties"]["extracted_variables"]["required"]}


def dry_run_adjudication(evidence_mode: str) -> dict:
    return {
        "source_family": "uncertain",
        "source_type": "uncertain",
        "paper_type": "uncertain",
        "study_design": "not_run",
        "evidence_strength": "uncertain",
        "supports_current_claim": "insufficient_evidence",
        "best_evidence_location": "abstract" if evidence_mode == "abstract_only" else "none",
        "best_evidence_locator": "abstract" if evidence_mode == "abstract_only" else "not_run",
        "supporting_quote": "not_found",
        "confidence": 0,
        "needs_human_check": True,
        "reasoning_summary": "dry run; model was not called",
        "extracted_variables": default_extracted_variables(),
    }


def flatten_result(
    row: dict,
    adjudication: dict,
    status: str,
    quote_verified: bool,
    min_confidence: float,
    evidence_mode: str,
    error: str = "",
) -> dict:
    variables = adjudication.get("extracted_variables", {}) if isinstance(adjudication, dict) else {}
    return {
        "status": status,
        "evidence_mode": evidence_mode,
        "quote_verified": quote_verified,
        "dataset": row.get("dataset", ""),
        "sample_group": row.get("sample_group", ""),
        "row_index": row.get("row_index", ""),
        "study_doi": row.get("study_doi", ""),
        "study_title": row.get("study_title", ""),
        "classification": row.get("classification", ""),
        "llm_source_family": adjudication.get("source_family", ""),
        "llm_source_type": adjudication.get("source_type", ""),
        "llm_paper_type": adjudication.get("paper_type", ""),
        "llm_study_design": adjudication.get("study_design", ""),
        "llm_evidence_strength": adjudication.get("evidence_strength", ""),
        "llm_supports_current_claim": adjudication.get("supports_current_claim", ""),
        "llm_confidence": adjudication.get("confidence", ""),
        "llm_needs_human_check": adjudication.get("needs_human_check", ""),
        "llm_best_evidence_location": adjudication.get("best_evidence_location", ""),
        "llm_best_evidence_locator": adjudication.get("best_evidence_locator", ""),
        "llm_supporting_quote": adjudication.get("supporting_quote", ""),
        "llm_reasoning_summary": adjudication.get("reasoning_summary", ""),
        "llm_sample_size_total": variables.get("sample_size_total", ""),
        "llm_effect_size": variables.get("effect_size", ""),
        "llm_p_value": variables.get("p_value", ""),
        "semantic_auto_eligible": semantic_auto_eligible(adjudication, quote_verified, min_confidence=min_confidence),
        "error": error,
    }


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
            raise ValueError("no abstract available for abstract-only adjudication")
    if artifact_path is None:
        raise FileNotFoundError("artifact_path is empty")
    raise FileNotFoundError(f"artifact not found: {artifact_path}")


def adjudicate_row(row: dict, args: argparse.Namespace) -> dict:
    evidence_mode, chunks = evidence_chunks_for_row(row, args)
    messages = build_prompt(row, chunks, evidence_mode=evidence_mode)
    context = evidence_context(chunks)
    if args.dry_run:
        adjudication = dry_run_adjudication(evidence_mode)
    else:
        adjudication = call_ollama(
            model=args.model,
            messages=messages,
            schema=ADJUDICATION_SCHEMA,
            ollama_url=args.ollama_url,
            timeout_sec=ollama_request_timeout(args.timeout_sec),
            temperature=max(0.0, args.temperature),
            num_ctx=max(2048, args.num_ctx),
        )
    quote_verified = quote_found_in_context(adjudication.get("supporting_quote", ""), context)
    return {
        "input_row": row,
        "evidence_mode": evidence_mode,
        "evidence_chunks": chunks,
        "adjudication": adjudication,
        "verification": {
            "quote_verified": quote_verified,
            "chunk_count": len(chunks),
            "context_char_count": len(context),
            "semantic_auto_eligible": semantic_auto_eligible(
                adjudication,
                quote_verified,
                min_confidence=args.auto_confidence,
            ),
        },
        "flat": flatten_result(
            row,
            adjudication,
            status="ok",
            quote_verified=quote_verified,
            min_confidence=args.auto_confidence,
            evidence_mode=evidence_mode,
        ),
    }


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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default=str(DEFAULT_INPUT), help="QA sample JSON path")
    parser.add_argument("--out-json", default=str(DEFAULT_OUT_JSON))
    parser.add_argument("--out-csv", default=str(DEFAULT_OUT_CSV))
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
    args = parser.parse_args()
    if args.evidence_mode == "abstract_only":
        if args.out_json == str(DEFAULT_OUT_JSON):
            args.out_json = str(DEFAULT_ABSTRACT_ONLY_OUT_JSON)
        if args.out_csv == str(DEFAULT_OUT_CSV):
            args.out_csv = str(DEFAULT_ABSTRACT_ONLY_OUT_CSV)
    return args


def main() -> int:
    args = parse_args()
    input_path = Path(args.input).resolve()
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

    results = []
    flat_rows = []
    status = "ok"
    for index, row in enumerate(rows, start=1):
        print(f"[{index}/{len(rows)}] {row.get('dataset')} row {row.get('row_index')} {row.get('study_doi')}", flush=True)
        try:
            result = adjudicate_row(row, args)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, Exception) as err:
            status = "failed"
            adjudication = {}
            result = {
                "input_row": row,
                "evidence_chunks": [],
                "adjudication": adjudication,
                "verification": {"quote_verified": False, "chunk_count": 0, "context_char_count": 0},
                "error": f"{type(err).__name__}: {err}",
                "flat": flatten_result(
                    row,
                    adjudication,
                    status="failed",
                    quote_verified=False,
                    min_confidence=args.auto_confidence,
                    evidence_mode=normalize(args.evidence_mode) or "full_text",
                    error=f"{type(err).__name__}: {err}",
                ),
            }
            if not args.continue_on_error:
                results.append(result)
                flat_rows.append(result["flat"])
                break
        results.append(result)
        flat_rows.append(result["flat"])

    summary = {
        "rows_requested": len(rows),
        "rows_completed": len([row for row in flat_rows if row.get("status") == "ok"]),
        "rows_failed": len([row for row in flat_rows if row.get("status") != "ok"]),
        "quote_verified": len([row for row in flat_rows if row.get("quote_verified") is True]),
        "semantic_auto_eligible": len([row for row in flat_rows if row.get("semantic_auto_eligible") is True]),
        "by_status": dict(Counter(row.get("status", "") for row in flat_rows)),
        "by_llm_source_family": dict(Counter(row.get("llm_source_family", "") for row in flat_rows)),
    }
    payload = {
        "generated_at_utc": now_utc(),
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
        },
        "summary": summary,
        "rows": results,
    }

    out_json = Path(args.out_json).resolve()
    out_csv = Path(args.out_csv).resolve()
    write_json(out_json, payload)
    write_csv(out_csv, flat_rows)

    print(f"Status: {status}")
    print(f"Rows completed: {summary['rows_completed']}")
    print(f"Rows failed: {summary['rows_failed']}")
    print(f"Quote verified: {summary['quote_verified']}")
    print(f"Semantic auto-eligible: {summary['semantic_auto_eligible']}")
    print(f"JSON: {out_json}")
    print(f"CSV: {out_csv}")
    return 0 if status == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
