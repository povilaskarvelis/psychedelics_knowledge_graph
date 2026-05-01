#!/usr/bin/env python3
"""Run local Ollama-based semantic screening over paper-library abstracts.

This is the upstream semantic screening layer. It reads the paper library after
metadata sync, asks a local LLM to classify relevance/source family using only
title/abstract/metadata, verifies exact supporting quotes, and writes
non-destructive reports plus DOI queues for later PDF acquisition.
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
from collections import Counter
from pathlib import Path
from typing import Iterable, List

try:
    from pipeline.fulltext.run_local_llm_evidence_adjudication import (
        call_ollama,
        model_is_installed,
        ollama_request_timeout,
        quote_found_in_context,
    )
    from pipeline.review.triage_paper_library import (
        COMPOUND_SYNONYMS,
        DATASET_CONFIG,
        DISORDER_SYNONYMS,
        FILE_DISORDER_SYNONYMS,
        TARGET_SYNONYMS,
        load_json_array,
        normalize,
        normalize_doi,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from pipeline.fulltext.run_local_llm_evidence_adjudication import (
        call_ollama,
        model_is_installed,
        ollama_request_timeout,
        quote_found_in_context,
    )
    from pipeline.review.triage_paper_library import (
        COMPOUND_SYNONYMS,
        DATASET_CONFIG,
        DISORDER_SYNONYMS,
        FILE_DISORDER_SYNONYMS,
        TARGET_SYNONYMS,
        load_json_array,
        normalize,
        normalize_doi,
    )

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_MODEL = "qwen3:14b"
DATASETS = ("disorder", "mechanistic")
PAPER_METADATA_FIELDS = [
    "study_journal",
    "publication_type",
    "trial_registry_ids",
    "publication_date",
    "journal_issn",
    "journal_eissn",
    "publisher",
    "mesh_terms",
    "keywords",
    "funders",
    "grant_ids",
    "related_dois",
    "publication_relations",
    "is_retracted",
    "has_correction",
    "language",
    "semantic_scholar_id",
]

RELEVANCE_VALUES = ["relevant", "irrelevant", "uncertain"]
SUPPORT_VALUES = ["supported", "not_supported", "uncertain"]

FAST_SCREENING_ACTIONS = ["exclude_obvious_irrelevant", "escalate"]
FAST_SCREENING_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "screening_action": {"type": "string", "enum": FAST_SCREENING_ACTIONS},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "supporting_quote": {"type": "string"},
        "reason": {"type": "string"},
    },
    "required": ["screening_action", "confidence", "supporting_quote", "reason"],
}

IN_SCOPE_INTERVENTION_CLASS_TERMS = {
    "classic hallucinogen",
    "classic hallucinogens",
    "classic psychedelic",
    "classic psychedelics",
    "dissociative",
    "dissociatives",
    "empathogen",
    "empathogens",
    "entactogen",
    "entactogens",
    "entheogen",
    "entheogens",
    "hallucinogen",
    "hallucinogens",
    "ketamine-assisted",
    "ketamina",
    "kétamine",
    "mdma-assisted",
    "psychoplastogen",
    "psychoplastogens",
    "psychedelic",
    "psychedelic-assisted",
    "psychedelics",
    "serotonergic hallucinogen",
    "serotonergic hallucinogens",
    "serotonergic psychedelic",
    "serotonergic psychedelics",
}

AMBIGUOUS_PSYCHIATRIC_TREATMENT_TERMS = {
    "experimental therapeutics",
    "new treatments for psychiatric disorders",
    "novel agents",
    "psychiatric drugs",
    "psychotropic drugs",
}

ABSTRACT_SCREENING_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "relevance": {"type": "string", "enum": RELEVANCE_VALUES},
        "supporting_abstract_quote": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "needs_targeted_qa": {"type": "boolean"},
        "reasoning_summary": {"type": "string"},
        "supported_contexts": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "compound": {"type": "string"},
                    "entity": {"type": "string"},
                    "support": {"type": "string", "enum": SUPPORT_VALUES},
                    "supporting_quote": {"type": "string"},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "reason": {"type": "string"},
                },
                "required": ["compound", "entity", "support", "supporting_quote", "confidence", "reason"],
            },
        },
    },
    "required": [
        "relevance",
        "supporting_abstract_quote",
        "confidence",
        "needs_targeted_qa",
        "reasoning_summary",
        "supported_contexts",
    ],
}


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def print_screening_row_followup(
    flat: dict,
    elapsed_sec: float | None,
    *,
    source: str = "llm",
) -> None:
    """One-line summary after each paper (or after loading from checkpoint)."""
    status = normalize(str(flat.get("status", ""))) or "?"
    relevance = normalize(str(flat.get("llm_relevance", ""))) or "—"
    quote_ok = "yes" if flat.get("quote_verified") is True else "no"
    ctx_count = flat.get("verified_supported_context_count", "")
    ctx_part = f" | ctx={ctx_count}" if ctx_count != "" else ""
    dl = flat.get("download_queue_eligible")
    dl_s = "yes" if dl is True else "no" if dl is False else "?"
    qa = flat.get("llm_needs_targeted_qa")
    qa_s = "yes" if qa is True else "no" if qa is False else "?"
    flags = normalize(str(flat.get("validation_flags", "")))
    flags_part = f" | flags={flags}" if flags else ""
    path = normalize(str(flat.get("screening_path", "")))
    path_part = f" | path={path}" if path else ""
    timing = f"{elapsed_sec:.1f}s" if elapsed_sec is not None else ""
    timing_part = f" | {timing}" if timing else ""

    if source == "checkpoint":
        print(
            f"     -> checkpoint | llm={relevance} | "
            f"quote_ok={quote_ok}{ctx_part} | qa={qa_s} | dl_eligible={dl_s}{path_part}{flags_part}",
            flush=True,
        )
        return

    err = normalize(str(flat.get("error", "")))
    if status == "failed" and err:
        err_short = err.replace("\n", " ").strip()[:120]
        print(f"     -> failed{timing_part} | {err_short}", flush=True)
        return

    print(
        f"     -> {status} | llm={relevance} | "
        f"quote_ok={quote_ok}{ctx_part} | qa={qa_s} | dl_eligible={dl_s}{path_part}{flags_part}{timing_part}",
        flush=True,
    )


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: Iterable[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "status",
        "dataset",
        "row_index",
        "study_doi",
        "study_title",
        "study_year",
        "library_status",
        "pdf_download_status",
        "has_abstract",
        "quote_verified",
        "verified_supported_context_count",
        "semantic_auto_eligible",
        "download_queue_eligible",
        "screening_path",
        "deterministic_prescreen_action",
        "deterministic_prescreen_reason",
        "fast_screening_action",
        "fast_screening_confidence",
        "fast_screening_quote_verified",
        "llm_relevance",
        "llm_confidence",
        "llm_needs_targeted_qa",
        "llm_supported_contexts",
        "llm_supporting_abstract_quote",
        "llm_reasoning_summary",
        "heuristic_relevance",
        "heuristic_screening_status",
        "heuristic_matched_context_count",
        "heuristic_llm_relevance_disagreement",
        "validation_flags",
        "error",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def safe_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def abstract_context(row: dict) -> str:
    title = normalize(row.get("study_title", ""))
    abstract = normalize(row.get("abstract", ""))
    parts = []
    if title:
        parts.append(f"Title: {title}")
    if abstract:
        parts.append(f"Abstract: {abstract}")
    return "\n".join(parts)


def compact_candidate_contexts(row: dict, max_contexts: int = 16) -> List[dict]:
    contexts = row.get("contexts", [])
    if not isinstance(contexts, list):
        return []
    out: List[dict] = []
    seen = set()
    for index, ctx in enumerate(contexts, start=1):
        if not isinstance(ctx, dict):
            continue
        compound = normalize(ctx.get("compound", ""))
        entity = normalize(ctx.get("entity", ""))
        if not compound and not entity:
            continue
        key = (compound.lower(), entity.lower())
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "id": f"CTX{index:03d}",
                "compound": compound,
                "entity": entity,
                "source": normalize(ctx.get("triage_match_source", "")) or "paper_library_context",
            }
        )
        if len(out) >= max_contexts:
            break
    return out


def dataset_scope(dataset: str) -> str:
    if dataset == "disorder":
        return (
            "Disorder KG scope: papers are relevant when the title/abstract supports a relationship between a "
            "psychedelic, dissociative, entactogen, or closely related compound and a disorder, symptom domain, "
            "clinical condition, or patient population. Healthy-volunteer pharmacology without a disorder/condition "
            "outcome is usually irrelevant for this dataset."
        )
    return (
        "Mechanistic KG scope: papers are relevant when the title/abstract supports a relationship between a "
        "psychedelic, dissociative, entactogen, or closely related compound and a biological target, receptor, "
        "transporter, pathway, assay, pharmacodynamic mechanism, animal mechanism, or in-vitro mechanism. Pure "
        "clinical efficacy without a mechanistic target is usually irrelevant or uncertain for this dataset."
    )


def paper_metadata_from_row(row: dict) -> dict:
    return {field: normalize(row.get(field, "")) for field in PAPER_METADATA_FIELDS}


def screening_input_row(row_index: int, row: dict) -> dict:
    return {
        "row_index": row_index,
        "study_doi": normalize_doi(row.get("study_doi", "")),
        "study_title": normalize(row.get("study_title", "")),
        "study_year": normalize(row.get("study_year", "")),
        "authors": normalize(row.get("authors", "")),
        **paper_metadata_from_row(row),
        "library_status": normalize(row.get("library_status", "")),
        "pdf_download_status": normalize(row.get("pdf_download_status", "")),
        "abstract": normalize(row.get("abstract", "")),
    }


def build_prompt(dataset: str, row: dict, candidate_contexts: List[dict]) -> list[dict]:
    metadata = {
        "dataset": dataset,
        "study_doi": normalize_doi(row.get("study_doi", "")),
        "study_title": normalize(row.get("study_title", "")),
        "study_year": normalize(row.get("study_year", "")),
        "authors": normalize(row.get("authors", "")),
        **paper_metadata_from_row(row),
        "abstract": normalize(row.get("abstract", "")),
        "pmid": normalize(row.get("pmid", "")),
        "pmcid": normalize(row.get("pmcid", "")),
        "library_status": normalize(row.get("library_status", "")),
        "open_access_status": normalize(row.get("open_access_status", "")),
        "best_pdf_url_present": bool(normalize(row.get("best_pdf_url", ""))),
    }
    user_payload = {
        "task": "Decide abstract-level relevance before PDF download for a psychedelics knowledge graph.",
        "dataset_scope": dataset_scope(dataset),
        "candidate_metadata": metadata,
        "candidate_contexts": candidate_contexts,
        "instructions": [
            "Use only the supplied title, abstract, and metadata. Do not use outside knowledge.",
            "Your only job is relevance and quote-supported compound/entity contexts; do not classify source type, paper type, study design, or evidence strength.",
            "Prefer high recall: choose uncertain instead of irrelevant when the abstract is thin but the paper plausibly belongs in scope.",
            "Choose relevant only when the title/abstract supports at least one in-scope compound plus target/disorder context.",
            "Choose irrelevant only when the title/abstract gives enough evidence that the paper is out of scope.",
            "For supported_contexts, include only contexts supported by the title/abstract. You may use supplied candidate contexts or add a context if the title/abstract explicitly supports it.",
            "supporting_abstract_quote must be an exact verbatim quote supporting the overall screening decision, including irrelevant decisions.",
            "If a paper is irrelevant because it is about a different intervention/topic, quote the title or abstract phrase showing that topic when possible.",
            "Every supported_context supporting_quote must be an exact verbatim quote from the supplied title or abstract. If no exact quote is available, use not_found and set needs_targeted_qa=true.",
        ],
    }
    system = (
        "You are a careful scientific screening reviewer for a psychedelics evidence database. "
        "Your job is not to extract final claims or classify study quality; your job is to decide whether a paper is relevant enough to inspect further. "
        "Be conservative about unsupported claims, but preserve recall by marking plausible-but-underspecified papers as uncertain. "
        "Return only JSON matching the requested schema."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
    ]


def build_fast_screening_prompt(dataset: str, row: dict, candidate_contexts: List[dict] | None = None) -> list[dict]:
    if candidate_contexts is None:
        candidate_contexts = compact_candidate_contexts(row)
    metadata = {
        "dataset": dataset,
        "study_doi": normalize_doi(row.get("study_doi", "")),
        "study_title": normalize(row.get("study_title", "")),
        "study_year": normalize(row.get("study_year", "")),
        "abstract": normalize(row.get("abstract", "")),
    }
    user_payload = {
        "task": "Cheap high-recall pre-screen before expensive abstract adjudication.",
        "dataset_scope": dataset_scope(dataset),
        "candidate_metadata": metadata,
        "candidate_contexts": candidate_contexts,
        "instructions": [
            "Use only the supplied title and abstract.",
            "Return escalate for any paper that might plausibly be in scope, even weakly or indirectly.",
            "Return escalate if the title/abstract mentions any supplied candidate_contexts compound or entity term, even if the relationship is unclear, incidental, background-only, or an exclusion criterion.",
            "Do not exclude papers containing seed-like intervention, disorder, symptom, population, target, or mechanism terms; escalate them to the full model.",
            "Return escalate if the paper mentions any psychedelic, ketamine/esketamine/arketamine, MDMA/MDA, ayahuasca, ibogaine, mescaline, DMT, 5-MeO-DMT, salvinorin, or a related intervention.",
            "Return escalate if the paper mentions a disorder, symptom, patient population, clinical outcome, biological target, receptor, transporter, pharmacology, animal model, or mechanistic assay that could fit either KG dataset.",
            "Return exclude_obvious_irrelevant only when the title/abstract clearly shows a different topic and there is no plausible psychedelic KG relevance.",
            "supporting_quote must be an exact verbatim quote from the title or abstract. Use not_found and escalate if no exact quote supports exclusion.",
        ],
    }
    system = (
        "You are a conservative first-pass screening assistant. "
        "Your only safe exclusion is an obvious out-of-scope paper. "
        "When in doubt, escalate. Return only JSON matching the schema."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
    ]


def synonym_map_terms(*mappings: dict) -> set[str]:
    terms: set[str] = set()
    for mapping in mappings:
        for label, aliases in mapping.items():
            label_norm = normalize(label)
            if label_norm:
                terms.add(label_norm)
            if isinstance(aliases, (list, set, tuple)):
                for alias in aliases:
                    alias_norm = normalize(alias)
                    if alias_norm:
                        terms.add(alias_norm)
    return {term for term in terms if len(term) >= 3}


def term_found_in_context(term: str, context: str) -> bool:
    term = normalize(term)
    if len(term) < 3:
        return False
    normalized_context = normalize(context)
    return term_found_in_normalized_context(term, normalized_context)


def term_found_in_normalized_context(term: str, normalized_context: str) -> bool:
    term = normalize(term)
    if len(term) < 3:
        return False
    return re.search(rf"(?<![A-Za-z0-9]){re.escape(term)}(?![A-Za-z0-9])", normalized_context, re.IGNORECASE) is not None


def any_term_found_in_context(terms: Iterable[str], context: str) -> bool:
    normalized_context = normalize(context)
    return any(term_found_in_normalized_context(term, normalized_context) for term in terms)


def candidate_term_found_in_context(candidate_contexts: List[dict] | None, context: str) -> bool:
    if not candidate_contexts:
        return False
    for candidate in candidate_contexts:
        if not isinstance(candidate, dict):
            continue
        if term_found_in_context(candidate.get("compound", ""), context) or term_found_in_context(
            candidate.get("entity", ""),
            context,
        ):
            return True
    return False


def in_scope_intervention_term_found(context: str) -> bool:
    terms = synonym_map_terms(COMPOUND_SYNONYMS) | IN_SCOPE_INTERVENTION_CLASS_TERMS
    return any_term_found_in_context(terms, context)


def heuristic_blocks_deterministic_exclusion(heuristic: dict) -> bool:
    relevance = normalize(heuristic.get("relevance_suggested", ""))
    if relevance in {"likely_relevant", "possible_relevant"}:
        return True
    status = normalize(heuristic.get("screening_status", ""))
    if status.startswith("included_") or status.startswith("needs_"):
        return True
    return safe_float(heuristic.get("matched_context_count", 0)) > 0 or safe_float(
        heuristic.get("protected_context_count", 0)
    ) > 0


def deterministic_prescreen_decision(
    dataset: str,
    row: dict,
    heuristic: dict,
    candidate_contexts: List[dict],
) -> dict:
    context = abstract_context(row)
    abstract = normalize(row.get("abstract", ""))
    if len(abstract) < 80:
        return {"action": "escalate", "reason": "abstract too short for deterministic exclusion"}
    if normalize(row.get("pdf_local_path", "")) or normalize(row.get("pdf_download_status", "")) == "downloaded":
        return {"action": "escalate", "reason": "paper already has downloaded full text"}
    if heuristic_blocks_deterministic_exclusion(heuristic):
        return {"action": "escalate", "reason": "heuristic triage retained this paper"}
    if candidate_term_found_in_context(candidate_contexts, context):
        return {"action": "escalate", "reason": "candidate compound/entity term appears in title or abstract"}
    if in_scope_intervention_term_found(context):
        return {"action": "escalate", "reason": "in-scope compound/intervention term appears in title or abstract"}
    if any_term_found_in_context(AMBIGUOUS_PSYCHIATRIC_TREATMENT_TERMS, context):
        return {"action": "escalate", "reason": "broad psychiatric treatment language needs LLM review"}

    entity_terms = (
        synonym_map_terms(DISORDER_SYNONYMS, FILE_DISORDER_SYNONYMS)
        if dataset == "disorder"
        else synonym_map_terms(TARGET_SYNONYMS)
    )
    entity_reason = "dataset entity terms present" if any_term_found_in_context(entity_terms, context) else "no dataset entity terms found"
    return {
        "action": "exclude_obvious_irrelevant",
        "confidence": 1.0,
        "supporting_quote": deterministic_supporting_quote(row),
        "reason": (
            "No in-scope psychedelic/ketamine/entactogen/dissociative compound or intervention term appears "
            f"in the title/abstract; {entity_reason}; no candidate context term was text-supported."
        ),
    }


def deterministic_supporting_quote(row: dict) -> str:
    title = normalize(row.get("study_title", ""))
    if title:
        return title
    abstract = normalize(row.get("abstract", ""))
    return abstract[:300] if abstract else "not_found"


def deterministic_irrelevant_adjudication(decision: dict) -> dict:
    return {
        "relevance": "irrelevant",
        "supporting_abstract_quote": normalize(decision.get("supporting_quote", "")),
        "confidence": safe_float(decision.get("confidence", 1.0)),
        "needs_targeted_qa": False,
        "reasoning_summary": "deterministic prescreen excluded as obvious irrelevant: "
        + normalize(decision.get("reason", "")),
        "supported_contexts": [],
    }


def fast_screen_excludes(
    fast_screening: dict,
    context: str,
    min_confidence: float,
    candidate_contexts: List[dict] | None = None,
) -> bool:
    if normalize(fast_screening.get("screening_action", "")) != "exclude_obvious_irrelevant":
        return False
    if safe_float(fast_screening.get("confidence", 0)) < min_confidence:
        return False
    if candidate_term_found_in_context(candidate_contexts, context):
        return False
    quote = normalize(fast_screening.get("supporting_quote", ""))
    if quote.lower() == "not_found":
        return False
    return quote_found_in_context(quote, context)


def fast_screen_irrelevant_adjudication(fast_screening: dict) -> dict:
    return {
        "relevance": "irrelevant",
        "supporting_abstract_quote": normalize(fast_screening.get("supporting_quote", "")),
        "confidence": safe_float(fast_screening.get("confidence", 0)),
        "needs_targeted_qa": False,
        "reasoning_summary": "fast-screen excluded as obvious irrelevant: "
        + normalize(fast_screening.get("reason", "")),
        "supported_contexts": [],
    }


def load_triage_by_doi(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("rows", []) if isinstance(payload, dict) else []
    out = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        doi = normalize_doi(row.get("study_doi", "")).lower()
        if doi:
            out[doi] = row
    return out


def heuristic_relevance_disagreement(heuristic: dict, adjudication: dict) -> bool:
    heuristic_relevance = normalize(heuristic.get("relevance_suggested", ""))
    llm_relevance = normalize(adjudication.get("relevance", ""))
    return (heuristic_relevance == "likely_irrelevant" and llm_relevance == "relevant") or (
        heuristic_relevance == "likely_relevant" and llm_relevance == "irrelevant"
    )


def verified_supported_contexts(adjudication: dict, context: str, min_confidence: float) -> List[dict]:
    out: List[dict] = []
    contexts = adjudication.get("supported_contexts", [])
    if not isinstance(contexts, list):
        return out
    for ctx in contexts:
        if not isinstance(ctx, dict):
            continue
        compound = normalize(ctx.get("compound", ""))
        entity = normalize(ctx.get("entity", ""))
        if not compound or not entity:
            continue
        if normalize(ctx.get("support", "")) != "supported":
            continue
        confidence = safe_float(ctx.get("confidence", 0))
        if confidence < min_confidence:
            continue
        quote = normalize(ctx.get("supporting_quote", "")) or normalize(adjudication.get("supporting_abstract_quote", ""))
        if not quote_found_in_context(quote, context):
            continue
        out.append(
            {
                "compound": compound,
                "entity": entity,
                "supporting_quote": quote,
                "confidence": confidence,
                "reason": normalize(ctx.get("reason", "")),
            }
        )
    return out


def validation_flags(adjudication: dict, quote_verified: bool, verified_context_count: int) -> List[str]:
    flags: List[str] = []
    relevance = normalize(adjudication.get("relevance", ""))
    if not quote_verified:
        flags.append("decision_quote_not_verified")
    if relevance == "relevant" and verified_context_count <= 0:
        flags.append("relevant_without_verified_context")
    if relevance == "irrelevant" and verified_context_count > 0:
        flags.append("irrelevant_with_supported_context")
    return flags


def semantic_auto_eligible(adjudication: dict, quote_verified: bool, verified_context_count: int, min_confidence: float) -> bool:
    return (
        quote_verified
        and verified_context_count > 0
        and safe_float(adjudication.get("confidence", 0)) >= min_confidence
        and adjudication.get("needs_targeted_qa") is False
        and normalize(adjudication.get("relevance", "")) == "relevant"
    )


def enforce_validation_flags(adjudication: dict, quote_verified: bool, verified_context_count: int) -> dict:
    """Force unsafe model outputs into targeted QA instead of trusting them."""
    out = dict(adjudication)
    if validation_flags(out, quote_verified=quote_verified, verified_context_count=verified_context_count):
        out["needs_targeted_qa"] = True
    return out


def download_queue_eligible(
    adjudication: dict,
    verified_context_count: int = 0,
) -> bool:
    relevance = normalize(adjudication.get("relevance", ""))
    return relevance in {"relevant", "uncertain"}


def dry_run_adjudication() -> dict:
    return {
        "relevance": "uncertain",
        "supporting_abstract_quote": "not_found",
        "confidence": 0,
        "needs_targeted_qa": True,
        "reasoning_summary": "dry run; model was not called",
        "supported_contexts": [],
    }


def selected_rows(rows: List[dict], limit: int, offset: int) -> List[dict]:
    start = max(0, offset)
    end = None if limit <= 0 else start + limit
    return rows[start:end]


def filter_indexed_rows(
    indexed_rows: List[tuple[int, dict]],
    triage_by_doi: dict[str, dict],
    args: argparse.Namespace,
    doi_filter: set[str] | None = None,
) -> List[tuple[int, dict]]:
    filtered = []
    for row_index, row in indexed_rows:
        doi = normalize_doi(row.get("study_doi", "")).lower()
        if doi_filter is not None and doi not in doi_filter:
            continue
        if args.only_with_abstract and not normalize(row.get("abstract", "")):
            continue
        if args.only_undownloaded and normalize(row.get("pdf_local_path", "")):
            continue
        if args.only_heuristic_possible:
            heuristic = triage_by_doi.get(doi, {})
            if heuristic.get("relevance_suggested") != "possible_relevant":
                continue
        filtered.append((row_index, row))
    return filtered


def flatten_supported_contexts(contexts: List[dict]) -> str:
    return " | ".join(f"{ctx.get('compound', '')}->{ctx.get('entity', '')}" for ctx in contexts)


def flatten_result(
    dataset: str,
    row_index: int,
    row: dict,
    adjudication: dict,
    status: str,
    quote_verified: bool,
    verified_contexts: List[dict],
    heuristic: dict,
    args: argparse.Namespace,
    error: str = "",
    screening_path: str = "full_model",
    deterministic_prescreen: dict | None = None,
    fast_screening: dict | None = None,
    fast_quote_verified: bool | str = "",
) -> dict:
    deterministic_prescreen = deterministic_prescreen or {}
    fast_screening = fast_screening or {}
    return {
        "status": status,
        "dataset": dataset,
        "row_index": row_index,
        "study_doi": normalize_doi(row.get("study_doi", "")),
        "study_title": normalize(row.get("study_title", "")),
        "study_year": normalize(row.get("study_year", "")),
        **paper_metadata_from_row(row),
        "library_status": normalize(row.get("library_status", "")),
        "pdf_download_status": normalize(row.get("pdf_download_status", "")),
        "has_abstract": bool(normalize(row.get("abstract", ""))),
        "quote_verified": quote_verified,
        "verified_supported_context_count": len(verified_contexts),
        "semantic_auto_eligible": semantic_auto_eligible(
            adjudication,
            quote_verified=quote_verified,
            verified_context_count=len(verified_contexts),
            min_confidence=args.auto_confidence,
        ),
        "download_queue_eligible": download_queue_eligible(
            adjudication,
            verified_context_count=len(verified_contexts),
        ),
        "screening_path": screening_path,
        "deterministic_prescreen_action": deterministic_prescreen.get("action", ""),
        "deterministic_prescreen_reason": deterministic_prescreen.get("reason", ""),
        "fast_screening_action": fast_screening.get("screening_action", ""),
        "fast_screening_confidence": fast_screening.get("confidence", ""),
        "fast_screening_quote_verified": fast_quote_verified,
        "llm_relevance": adjudication.get("relevance", ""),
        "llm_confidence": adjudication.get("confidence", ""),
        "llm_needs_targeted_qa": adjudication.get("needs_targeted_qa", ""),
        "llm_supported_contexts": flatten_supported_contexts(verified_contexts),
        "llm_supporting_abstract_quote": adjudication.get("supporting_abstract_quote", ""),
        "llm_reasoning_summary": adjudication.get("reasoning_summary", ""),
        "heuristic_relevance": heuristic.get("relevance_suggested", ""),
        "heuristic_screening_status": heuristic.get("screening_status", ""),
        "heuristic_matched_context_count": heuristic.get("matched_context_count", ""),
        "heuristic_llm_relevance_disagreement": heuristic_relevance_disagreement(heuristic, adjudication) if heuristic else "",
        "validation_flags": " | ".join(
            validation_flags(
                adjudication,
                quote_verified=quote_verified,
                verified_context_count=len(verified_contexts),
            )
        ),
        "error": error,
    }


def screen_row(dataset: str, row_index: int, row: dict, heuristic: dict, args: argparse.Namespace) -> dict:
    candidate_contexts = compact_candidate_contexts(row, max_contexts=max(1, args.max_contexts))
    context = abstract_context(row)
    fast_screening: dict | None = None
    fast_quote_verified: bool | str = ""
    deterministic_prescreen: dict | None = None
    screening_path = "full_model"
    if args.dry_run:
        adjudication = dry_run_adjudication()
    else:
        if getattr(args, "deterministic_prescreen", False):
            deterministic_prescreen = deterministic_prescreen_decision(dataset, row, heuristic, candidate_contexts)
        if deterministic_prescreen and deterministic_prescreen.get("action") == "exclude_obvious_irrelevant":
            adjudication = deterministic_irrelevant_adjudication(deterministic_prescreen)
            screening_path = "deterministic_excluded"
        else:
            fast_model = normalize(getattr(args, "fast_screen_model", ""))
            if fast_model:
                try:
                    fast_screening = call_ollama(
                        model=fast_model,
                        messages=build_fast_screening_prompt(dataset, row, candidate_contexts),
                        schema=FAST_SCREENING_SCHEMA,
                        ollama_url=args.ollama_url,
                        timeout_sec=ollama_request_timeout(max(0, args.fast_screen_timeout_sec)),
                        temperature=max(0.0, args.fast_screen_temperature),
                        num_ctx=max(2048, args.fast_screen_num_ctx),
                    )
                    fast_quote_verified = quote_found_in_context(fast_screening.get("supporting_quote", ""), context)
                except Exception as err:
                    fast_screening = {
                        "screening_action": "escalate",
                        "confidence": 0,
                        "supporting_quote": "not_found",
                        "reason": f"fast screen failed; escalated to full model: {type(err).__name__}: {err}",
                    }
                    fast_quote_verified = False
            if fast_screening and fast_screen_excludes(
                fast_screening,
                context=context,
                min_confidence=max(0.0, args.fast_screen_confidence),
                candidate_contexts=candidate_contexts,
            ):
                adjudication = fast_screen_irrelevant_adjudication(fast_screening)
                screening_path = "fast_excluded"
            else:
                if fast_model:
                    screening_path = "fast_escalated"
                adjudication = call_ollama(
                    model=args.model,
                    messages=build_prompt(dataset, row, candidate_contexts),
                    schema=ABSTRACT_SCREENING_SCHEMA,
                    ollama_url=args.ollama_url,
                    timeout_sec=ollama_request_timeout(args.timeout_sec),
                    temperature=max(0.0, args.temperature),
                    num_ctx=max(2048, args.num_ctx),
                )
    quote_verified = quote_found_in_context(adjudication.get("supporting_abstract_quote", ""), context)
    verified_contexts = verified_supported_contexts(
        adjudication,
        context=context,
        min_confidence=max(0.0, args.context_confidence),
    )
    adjudication = enforce_validation_flags(
        adjudication,
        quote_verified=quote_verified,
        verified_context_count=len(verified_contexts),
    )
    flat = flatten_result(
        dataset=dataset,
        row_index=row_index,
        row=row,
        adjudication=adjudication,
        status="ok",
        quote_verified=quote_verified,
        verified_contexts=verified_contexts,
        heuristic=heuristic,
        args=args,
        screening_path=screening_path,
        deterministic_prescreen=deterministic_prescreen,
        fast_screening=fast_screening,
        fast_quote_verified=fast_quote_verified,
    )
    return {
        "input_row": screening_input_row(row_index, row),
        "candidate_contexts": candidate_contexts,
        "deterministic_prescreen": deterministic_prescreen or {},
        "fast_screening": fast_screening or {},
        "adjudication": adjudication,
        "verification": {
            "quote_verified": quote_verified,
            "verified_supported_context_count": len(verified_contexts),
            "verified_supported_contexts": verified_contexts,
            "semantic_auto_eligible": flat["semantic_auto_eligible"],
            "download_queue_eligible": flat["download_queue_eligible"],
        },
        "heuristic_comparison": {
            "relevance": heuristic.get("relevance_suggested", ""),
            "screening_status": heuristic.get("screening_status", ""),
            "matched_context_count": heuristic.get("matched_context_count", ""),
            "relevance_disagreement": flat["heuristic_llm_relevance_disagreement"],
        },
        "flat": flat,
    }


def revalidate_checkpoint_result(
    dataset: str,
    row_index: int,
    row: dict,
    heuristic: dict,
    result: dict,
    args: argparse.Namespace,
) -> dict:
    """Recompute validation/queue fields for a checkpointed model response.

    Checkpoints store expensive LLM output. They should not freeze downstream
    validation logic because we often tighten gates during calibration.
    """
    if result.get("flat", {}).get("status") != "ok":
        return result

    adjudication = result.get("adjudication", {})
    if not isinstance(adjudication, dict):
        return result

    context = abstract_context(row)
    quote_verified = quote_found_in_context(adjudication.get("supporting_abstract_quote", ""), context)
    verified_contexts = verified_supported_contexts(
        adjudication,
        context=context,
        min_confidence=max(0.0, args.context_confidence),
    )
    adjudication = enforce_validation_flags(
        adjudication,
        quote_verified=quote_verified,
        verified_context_count=len(verified_contexts),
    )
    flat = flatten_result(
        dataset=dataset,
        row_index=row_index,
        row=row,
        adjudication=adjudication,
        status="ok",
        quote_verified=quote_verified,
        verified_contexts=verified_contexts,
        heuristic=heuristic,
        args=args,
        screening_path=result.get("flat", {}).get("screening_path", "checkpoint"),
        deterministic_prescreen=result.get("deterministic_prescreen", {}),
        fast_screening=result.get("fast_screening", {}),
        fast_quote_verified=result.get("flat", {}).get("fast_screening_quote_verified", ""),
    )

    updated = dict(result)
    updated["input_row"] = screening_input_row(row_index, row)
    updated["candidate_contexts"] = result.get("candidate_contexts", compact_candidate_contexts(row, max_contexts=max(1, args.max_contexts)))
    updated["deterministic_prescreen"] = result.get("deterministic_prescreen", {})
    updated["fast_screening"] = result.get("fast_screening", {})
    updated["adjudication"] = adjudication
    updated["verification"] = {
        "quote_verified": quote_verified,
        "verified_supported_context_count": len(verified_contexts),
        "verified_supported_contexts": verified_contexts,
        "semantic_auto_eligible": flat["semantic_auto_eligible"],
        "download_queue_eligible": flat["download_queue_eligible"],
    }
    updated["heuristic_comparison"] = {
        "relevance": heuristic.get("relevance_suggested", ""),
        "screening_status": heuristic.get("screening_status", ""),
        "matched_context_count": heuristic.get("matched_context_count", ""),
        "relevance_disagreement": flat["heuristic_llm_relevance_disagreement"],
    }
    updated["flat"] = flat
    return updated


def queue_rows_from_results(results: List[dict], relevance_filter: set[str], require_verified_context: bool) -> List[dict]:
    rows = []
    seen = set()
    for result in results:
        flat = result.get("flat", {})
        if flat.get("status") != "ok":
            continue
        adjudication = result.get("adjudication", {})
        if normalize(adjudication.get("relevance", "")) not in relevance_filter:
            continue
        if not flat.get("download_queue_eligible") and not require_verified_context:
            continue
        input_row = result.get("input_row", {})
        contexts = result.get("verification", {}).get("verified_supported_contexts", [])
        if require_verified_context and not contexts:
            continue
        if contexts:
            for ctx in contexts:
                key = (
                    normalize(input_row.get("study_doi", "")).lower(),
                    normalize(ctx.get("compound", "")).lower(),
                    normalize(ctx.get("entity", "")).lower(),
                )
                if key in seen:
                    continue
                seen.add(key)
                rows.append(
                    {
                        "study_doi": normalize(input_row.get("study_doi", "")),
                        "compound": normalize(ctx.get("compound", "")),
                        "entity": normalize(ctx.get("entity", "")),
                        "study_title": normalize(input_row.get("study_title", "")),
                        "study_year": normalize(input_row.get("study_year", "")),
                        "authors": normalize(input_row.get("authors", "")),
                        **paper_metadata_from_row(input_row),
                    }
                )
            continue
        key = (normalize(input_row.get("study_doi", "")).lower(), "", "")
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            {
                "study_doi": normalize(input_row.get("study_doi", "")),
                "compound": "",
                "entity": "",
                "study_title": normalize(input_row.get("study_title", "")),
                "study_year": normalize(input_row.get("study_year", "")),
                "authors": normalize(input_row.get("authors", "")),
                **paper_metadata_from_row(input_row),
            }
        )
    return rows


def default_checkpoint_jsonl_path(out_json: Path) -> Path:
    return out_json.parent / f"{out_json.stem}.checkpoint.jsonl"


def truncate_checkpoint(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")


def append_checkpoint_result(path: Path, result: dict) -> None:
    """Append one completed screening row (full `result` dict) for crash-safe runs."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(result, ensure_ascii=False) + "\n")
        handle.flush()
        try:
            os.fsync(handle.fileno())
        except OSError:
            pass


def load_checkpoint_results(path: Path) -> dict[str, dict]:
    """Map normalized DOI (lower) -> last parsed result object from JSONL."""
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
            input_row = rec.get("input_row", {})
            if not isinstance(input_row, dict):
                continue
            doi = normalize_doi(input_row.get("study_doi", "")).lower()
            if doi:
                out[doi] = rec
    return out


def checkpoint_result_is_compatible(result: dict) -> bool:
    """Return false for checkpoint rows that use labels outside the current schema."""
    if result.get("flat", {}).get("status") != "ok":
        return True
    adjudication = result.get("adjudication", {})
    if not isinstance(adjudication, dict):
        return False
    enum_fields = {"relevance": set(RELEVANCE_VALUES)}
    return all(normalize(adjudication.get(field, "")) in allowed for field, allowed in enum_fields.items())


def load_reprocess_doi_set(path: Path) -> set[str]:
    """One DOI per line (comments with # and blank lines ignored). Values normalized to lower DOI."""
    if not path.is_file():
        raise SystemExit(f"--reprocess-dois-file not found: {path}")
    out: set[str] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        doi = normalize_doi(line).lower()
        if doi:
            out.add(doi)
    return out


def read_doi_file(path: Path) -> set[str]:
    """Read DOI queues where the DOI is the first CSV/text column."""
    if not path.is_file():
        raise SystemExit(f"DOI file not found: {path}")
    out: set[str] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        doi = normalize_doi(line.split(",", 1)[0]).lower()
        if doi:
            out.add(doi)
    return out


def write_doi_queue(path: Path, rows: List[dict], description: str) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(f"# {description} generated at {now_utc()}\n")
        handle.write(
            "# doi,compound,target_or_disorder,optional_study_title,optional_study_year,"
            "optional_authors,"
            + ",".join(f"optional_{field}" for field in PAPER_METADATA_FIELDS)
            + "\n"
        )
        writer = csv.writer(handle)
        for row in rows:
            doi = normalize_doi(row.get("study_doi", ""))
            if not doi:
                continue
            writer.writerow(
                [
                    doi,
                    normalize(row.get("compound", "")),
                    normalize(row.get("entity", "")),
                    normalize(row.get("study_title", "")),
                    normalize(row.get("study_year", "")),
                    normalize(row.get("authors", "")),
                    *[normalize(row.get(field, "")) for field in PAPER_METADATA_FIELDS],
                ]
            )
    return len(rows)


PRESCREEN_CSV_FIELDS = [
    "dataset",
    "row_index",
    "study_doi",
    "study_title",
    "study_year",
    "has_abstract",
    "pdf_download_status",
    "deterministic_prescreen_action",
    "deterministic_prescreen_reason",
    "retained_for_llm",
    "candidate_context_count",
    "heuristic_relevance",
    "heuristic_screening_status",
    "heuristic_matched_context_count",
]


def write_prescreen_csv(path: Path, rows: List[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=PRESCREEN_CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in PRESCREEN_CSV_FIELDS})


def prescreen_queue_row(row: dict) -> dict:
    return {
        "study_doi": normalize_doi(row.get("study_doi", "")),
        "compound": "",
        "entity": "",
        "study_title": normalize(row.get("study_title", "")),
        "study_year": normalize(row.get("study_year", "")),
        "authors": normalize(row.get("authors", "")),
        **paper_metadata_from_row(row),
    }


def run_deterministic_prescreen_only_dataset(
    dataset: str,
    args: argparse.Namespace,
    paper_db_json: Path,
    triage_report: Path | None,
    paths: dict[str, Path],
    papers_all: List[dict],
    papers_filtered: List[tuple[int, dict]],
    selected: List[tuple[int, dict]],
    triage_by_doi: dict[str, dict],
    doi_filter: set[str] | None,
) -> dict:
    rows = []
    retained_queue = []
    excluded_queue = []
    for row_index, row in selected:
        doi = normalize_doi(row.get("study_doi", ""))
        heuristic = triage_by_doi.get(doi.lower(), {}) if doi else {}
        candidate_contexts = compact_candidate_contexts(row, max_contexts=max(1, args.max_contexts))
        decision = deterministic_prescreen_decision(dataset, row, heuristic, candidate_contexts)
        retained = decision.get("action") != "exclude_obvious_irrelevant"
        queue_row = prescreen_queue_row(row)
        if retained:
            retained_queue.append(queue_row)
        else:
            excluded_queue.append(queue_row)
        rows.append(
            {
                "dataset": dataset,
                "row_index": row_index,
                "study_doi": doi,
                "study_title": normalize(row.get("study_title", "")),
                "study_year": normalize(row.get("study_year", "")),
                "authors": normalize(row.get("authors", "")),
                "has_abstract": bool(normalize(row.get("abstract", ""))),
                "pdf_download_status": normalize(row.get("pdf_download_status", "")),
                "deterministic_prescreen_action": decision.get("action", ""),
                "deterministic_prescreen_reason": decision.get("reason", ""),
                "deterministic_prescreen_supporting_quote": decision.get("supporting_quote", ""),
                "retained_for_llm": retained,
                "candidate_context_count": len(candidate_contexts),
                "heuristic_relevance": heuristic.get("relevance_suggested", ""),
                "heuristic_screening_status": heuristic.get("screening_status", ""),
                "heuristic_matched_context_count": heuristic.get("matched_context_count", ""),
            }
        )

    retained_written = write_doi_queue(
        paths["prescreen_retained_queue"],
        retained_queue,
        f"Deterministic prescreen retained queue for {dataset}",
    )
    excluded_written = write_doi_queue(
        paths["prescreen_excluded_queue"],
        excluded_queue,
        f"Deterministic prescreen excluded queue for {dataset}",
    )
    write_prescreen_csv(paths["prescreen_csv"], rows)
    summary = {
        "papers_total": len(papers_all),
        "rows_after_filters": len(papers_filtered),
        "rows_requested": len(selected),
        "retained_for_llm": retained_written,
        "deterministic_excluded": excluded_written,
        "by_action": dict(Counter(row.get("deterministic_prescreen_action", "") for row in rows)),
    }
    payload = {
        "generated_at_utc": now_utc(),
        "status": "ok",
        "dataset": dataset,
        "mode": "deterministic_prescreen_only",
        "inputs": {
            "paper_db_json": str(paper_db_json),
            "doi_file": normalize(args.doi_file) or None,
            "doi_filter_count": len(doi_filter) if doi_filter is not None else None,
            "triage_report_json": str(triage_report) if triage_report else None,
            "use_heuristic_audit": bool(args.use_heuristic_audit or args.triage_report_json),
            "limit": args.limit,
            "offset": args.offset,
            "only_with_abstract": args.only_with_abstract,
            "only_undownloaded": args.only_undownloaded,
        },
        "outputs": {
            "report_json": str(paths["prescreen_json"]),
            "report_csv": str(paths["prescreen_csv"]),
            "retained_queue": str(paths["prescreen_retained_queue"]),
            "excluded_queue": str(paths["prescreen_excluded_queue"]),
        },
        "summary": summary,
        "rows": rows,
    }
    write_json(paths["prescreen_json"], payload)
    print(f"Dataset: {dataset}")
    print("Mode: deterministic prescreen only")
    print(f"Rows requested: {summary['rows_requested']}")
    print(f"Retained for LLM: {retained_written}")
    print(f"Deterministic excluded: {excluded_written}")
    print(f"Actions: {summary['by_action']}")
    print(f"Report JSON: {paths['prescreen_json']}")
    print(f"Report CSV: {paths['prescreen_csv']}")
    print(f"Retained queue: {paths['prescreen_retained_queue']}")
    print(f"Excluded queue: {paths['prescreen_excluded_queue']}")
    return payload


def run_checkpoint_materialization_dataset(
    dataset: str,
    args: argparse.Namespace,
    paper_db_json: Path,
    triage_report: Path | None,
    paths: dict[str, Path],
    papers_all: List[dict],
    papers_filtered: List[tuple[int, dict]],
    selected: List[tuple[int, dict]],
    triage_by_doi: dict[str, dict],
    doi_filter: set[str] | None,
    ckpt_path: Path,
) -> dict:
    checkpoint_by_doi = load_checkpoint_results(ckpt_path)
    results = []
    flat_rows = []
    missing_checkpoint = []
    incompatible_checkpoint = []

    for row_index, row in selected:
        doi = normalize_doi(row.get("study_doi", ""))
        doi_key = doi.lower()
        checkpoint_result = checkpoint_by_doi.get(doi_key) if doi_key else None
        if not checkpoint_result:
            missing_checkpoint.append(doi)
            continue
        if not checkpoint_result_is_compatible(checkpoint_result):
            incompatible_checkpoint.append(doi)
            continue
        heuristic = triage_by_doi.get(doi_key, {}) if doi_key else {}
        result = revalidate_checkpoint_result(
            dataset=dataset,
            row_index=row_index,
            row=row,
            heuristic=heuristic,
            result=checkpoint_result,
            args=args,
        )
        results.append(result)
        flat_rows.append(result["flat"])

    download_rows = queue_rows_from_results(results, relevance_filter={"relevant", "uncertain"}, require_verified_context=False)
    relevant_rows = queue_rows_from_results(results, relevance_filter={"relevant"}, require_verified_context=True)
    uncertain_rows = queue_rows_from_results(results, relevance_filter={"uncertain"}, require_verified_context=False)
    download_written = write_doi_queue(paths["download_queue"], download_rows, f"LLM full-text candidate queue for {dataset}")
    relevant_written = write_doi_queue(paths["relevant_queue"], relevant_rows, f"LLM verified relevant context queue for {dataset}")
    uncertain_written = write_doi_queue(paths["uncertain_queue"], uncertain_rows, f"LLM uncertain full-text candidate queue for {dataset}")

    status = "ok" if not missing_checkpoint and not incompatible_checkpoint else "completed_with_missing_checkpoint_rows"
    summary = {
        "papers_total": len(papers_all),
        "rows_after_filters": len(papers_filtered),
        "rows_requested": len(selected),
        "rows_completed": len([row for row in flat_rows if row.get("status") == "ok"]),
        "rows_failed": len([row for row in flat_rows if row.get("status") != "ok"]),
        "checkpoint_rows_loaded": len(checkpoint_by_doi),
        "checkpoint_rows_materialized": len(results),
        "checkpoint_rows_missing_for_selection": len(missing_checkpoint),
        "checkpoint_rows_incompatible": len(incompatible_checkpoint),
        "quote_verified": len([row for row in flat_rows if row.get("quote_verified") is True]),
        "semantic_auto_eligible": len([row for row in flat_rows if row.get("semantic_auto_eligible") is True]),
        "download_queue_eligible": len([row for row in flat_rows if row.get("download_queue_eligible") is True]),
        "download_queue_rows_written": download_written,
        "relevant_context_queue_rows_written": relevant_written,
        "uncertain_queue_rows_written": uncertain_written,
        "deterministic_prescreen_excluded": len(
            [row for row in flat_rows if row.get("screening_path") == "deterministic_excluded"]
        ),
        "fast_screen_excluded": len([row for row in flat_rows if row.get("screening_path") == "fast_excluded"]),
        "fast_screen_escalated": len([row for row in flat_rows if row.get("screening_path") == "fast_escalated"]),
        "by_status": dict(Counter(row.get("status", "") for row in flat_rows)),
        "by_llm_relevance": dict(Counter(row.get("llm_relevance", "") for row in flat_rows)),
        "by_screening_path": dict(Counter(row.get("screening_path", "") for row in flat_rows)),
        "heuristic_llm_relevance_disagreements": len(
            [row for row in flat_rows if row.get("heuristic_llm_relevance_disagreement") is True]
        ),
    }
    payload = {
        "generated_at_utc": now_utc(),
        "status": status,
        "dataset": dataset,
        "mode": "materialize_checkpoint_only",
        "inputs": {
            "paper_db_json": str(paper_db_json),
            "triage_report_json": str(triage_report) if triage_report else None,
            "use_heuristic_audit": bool(args.use_heuristic_audit or args.triage_report_json),
            "model": args.model,
            "deterministic_prescreen": bool(args.deterministic_prescreen),
            "fast_screen_model": normalize(args.fast_screen_model) or None,
            "limit": args.limit,
            "offset": args.offset,
            "doi_file": normalize(args.doi_file) or None,
            "doi_filter_count": len(doi_filter) if doi_filter is not None else None,
            "only_with_abstract": args.only_with_abstract,
            "only_undownloaded": args.only_undownloaded,
            "only_heuristic_possible": args.only_heuristic_possible,
            "auto_confidence": args.auto_confidence,
            "context_confidence": args.context_confidence,
            "fast_screen_confidence": args.fast_screen_confidence,
        },
        "outputs": {
            "report_json": str(paths["out_json"]),
            "report_csv": str(paths["out_csv"]),
            "checkpoint_jsonl": str(ckpt_path),
            "download_queue": str(paths["download_queue"]),
            "relevant_queue": str(paths["relevant_queue"]),
            "uncertain_queue": str(paths["uncertain_queue"]),
        },
        "summary": summary,
        "missing_checkpoint_dois": missing_checkpoint[:1000],
        "incompatible_checkpoint_dois": incompatible_checkpoint[:1000],
        "rows": results,
    }
    write_json(paths["out_json"], payload)
    write_csv(paths["out_csv"], flat_rows)

    print(f"Dataset: {dataset}")
    print("Mode: materialize checkpoint only")
    print(f"Status: {status}")
    print(f"Checkpoint rows loaded: {len(checkpoint_by_doi)}")
    print(f"Rows materialized: {len(results)}")
    print(f"Rows missing from checkpoint for this selection: {len(missing_checkpoint)}")
    print(f"Checkpoint rows incompatible: {len(incompatible_checkpoint)}")
    print(f"LLM relevance: {summary['by_llm_relevance']}")
    print(f"Download queue rows: {download_written}")
    print(f"Relevant context queue rows: {relevant_written}")
    print(f"Uncertain queue rows: {uncertain_written}")
    print(f"Report JSON: {paths['out_json']}")
    print(f"Report CSV: {paths['out_csv']}")
    print(f"Checkpoint JSONL: {ckpt_path}")
    return payload


def dataset_paths(dataset: str, args: argparse.Namespace) -> dict[str, Path]:
    if args.dataset != "all":
        return {
            "out_json": Path(args.out_json).resolve() if args.out_json else ROOT / "data" / "processed" / f"llm_abstract_screening_report_{dataset}.json",
            "out_csv": Path(args.out_csv).resolve() if args.out_csv else ROOT / "data" / "processed" / f"llm_abstract_screening_report_{dataset}.csv",
            "download_queue": Path(args.download_queue_out).resolve()
            if args.download_queue_out
            else ROOT / "data" / "raw" / f"doi_queue.{dataset}.llm_fulltext_candidates.txt",
            "relevant_queue": Path(args.relevant_queue_out).resolve()
            if args.relevant_queue_out
            else ROOT / "data" / "raw" / f"doi_queue.{dataset}.llm_relevant.txt",
            "uncertain_queue": Path(args.uncertain_queue_out).resolve()
            if args.uncertain_queue_out
            else ROOT / "data" / "raw" / f"doi_queue.{dataset}.llm_uncertain.txt",
            "prescreen_json": ROOT / "data" / "processed" / f"deterministic_prescreen_report_{dataset}.json",
            "prescreen_csv": ROOT / "data" / "processed" / f"deterministic_prescreen_report_{dataset}.csv",
            "prescreen_retained_queue": ROOT / "data" / "raw" / f"doi_queue.{dataset}.deterministic_prescreen_retained.txt",
            "prescreen_excluded_queue": ROOT / "data" / "raw" / f"doi_queue.{dataset}.deterministic_prescreen_excluded.txt",
        }
    return {
        "out_json": ROOT / "data" / "processed" / f"llm_abstract_screening_report_{dataset}.json",
        "out_csv": ROOT / "data" / "processed" / f"llm_abstract_screening_report_{dataset}.csv",
        "download_queue": ROOT / "data" / "raw" / f"doi_queue.{dataset}.llm_fulltext_candidates.txt",
        "relevant_queue": ROOT / "data" / "raw" / f"doi_queue.{dataset}.llm_relevant.txt",
        "uncertain_queue": ROOT / "data" / "raw" / f"doi_queue.{dataset}.llm_uncertain.txt",
        "prescreen_json": ROOT / "data" / "processed" / f"deterministic_prescreen_report_{dataset}.json",
        "prescreen_csv": ROOT / "data" / "processed" / f"deterministic_prescreen_report_{dataset}.csv",
        "prescreen_retained_queue": ROOT / "data" / "raw" / f"doi_queue.{dataset}.deterministic_prescreen_retained.txt",
        "prescreen_excluded_queue": ROOT / "data" / "raw" / f"doi_queue.{dataset}.deterministic_prescreen_excluded.txt",
    }


def run_dataset(dataset: str, args: argparse.Namespace) -> dict:
    cfg = DATASET_CONFIG[dataset]
    paper_db_json = Path(args.paper_db_json).resolve() if args.paper_db_json and args.dataset != "all" else cfg["paper_db_json"]
    triage_report = None
    if args.triage_report_json and args.dataset != "all":
        triage_report = Path(args.triage_report_json).resolve()
    elif args.use_heuristic_audit:
        triage_report = ROOT / "data" / "processed" / f"triage_report_{dataset}.json"
    paths = dataset_paths(dataset, args)
    if args.resume_from_checkpoint and args.no_checkpoint:
        raise SystemExit("--resume-from-checkpoint and --no-checkpoint cannot be used together")
    if args.materialize_checkpoint_only and args.no_checkpoint:
        raise SystemExit("--materialize-checkpoint-only requires checkpointing to be enabled")
    if (normalize(args.reprocess_dois_file) or args.reprocess_all_checkpoint_dois) and not args.resume_from_checkpoint:
        raise SystemExit("--reprocess-dois-file / --reprocess-all-checkpoint-dois require --resume-from-checkpoint")
    if normalize(args.reprocess_dois_file) and args.reprocess_all_checkpoint_dois:
        raise SystemExit("Use only one of --reprocess-dois-file or --reprocess-all-checkpoint-dois")
    ckpt_path = (
        Path(args.checkpoint_jsonl).resolve()
        if normalize(args.checkpoint_jsonl)
        else default_checkpoint_jsonl_path(paths["out_json"])
    )
    papers_all = load_json_array(paper_db_json)
    triage_by_doi = load_triage_by_doi(triage_report) if triage_report else {}
    if args.only_heuristic_possible and not triage_by_doi:
        raise SystemExit("--only-heuristic-possible requires --use-heuristic-audit or --triage-report-json")
    doi_filter = read_doi_file(Path(args.doi_file).resolve()) if normalize(args.doi_file) else None
    papers_filtered = filter_indexed_rows(
        list(enumerate(papers_all, start=1)),
        triage_by_doi=triage_by_doi,
        args=args,
        doi_filter=doi_filter,
    )
    selected = selected_rows(papers_filtered, limit=max(0, args.limit), offset=max(0, args.offset))
    if args.deterministic_prescreen_only:
        return run_deterministic_prescreen_only_dataset(
            dataset=dataset,
            args=args,
            paper_db_json=paper_db_json,
            triage_report=triage_report,
            paths=paths,
            papers_all=papers_all,
            papers_filtered=papers_filtered,
            selected=selected,
            triage_by_doi=triage_by_doi,
            doi_filter=doi_filter,
        )
    if args.materialize_checkpoint_only:
        return run_checkpoint_materialization_dataset(
            dataset=dataset,
            args=args,
            paper_db_json=paper_db_json,
            triage_report=triage_report,
            paths=paths,
            papers_all=papers_all,
            papers_filtered=papers_filtered,
            selected=selected,
            triage_by_doi=triage_by_doi,
            doi_filter=doi_filter,
            ckpt_path=ckpt_path,
        )

    checkpoint_by_doi: dict[str, dict] = {}
    if args.resume_from_checkpoint:
        checkpoint_by_doi = load_checkpoint_results(ckpt_path)
        n_loaded = len(checkpoint_by_doi)
        print(f"Checkpoint resume: {n_loaded} row(s) from {ckpt_path}", flush=True)
        if args.reprocess_all_checkpoint_dois:
            checkpoint_by_doi = {}
            print(
                f"Reprocess all checkpointed DOIs: cleared {n_loaded} resume skip(s); LLM will run for every row in this batch.",
                flush=True,
            )
        elif normalize(args.reprocess_dois_file):
            rpath = Path(args.reprocess_dois_file).resolve()
            rset = load_reprocess_doi_set(rpath)
            removed = 0
            for k in rset:
                if checkpoint_by_doi.pop(k, None) is not None:
                    removed += 1
            print(
                f"Reprocess list {rpath}: {len(rset)} DOI(s) listed, {removed} were in checkpoint (those rows will call the LLM again).",
                flush=True,
            )
    elif not args.no_checkpoint and not args.dry_run:
        truncate_checkpoint(ckpt_path)
        print(f"Checkpoint file (fresh): {ckpt_path}", flush=True)

    results = []
    flat_rows = []
    status = "ok"
    checkpoint_rows_reused = 0
    checkpoint_rows_reprocessed = 0
    for local_index, (row_index, row) in enumerate(selected, start=1):
        doi = normalize_doi(row.get("study_doi", ""))
        doi_key = doi.lower()
        row_header_printed = False
        if (
            not args.no_checkpoint
            and not args.dry_run
            and doi_key
            and doi_key in checkpoint_by_doi
            and args.resume_from_checkpoint
        ):
            heuristic = triage_by_doi.get(doi.lower(), {}) if doi else {}
            checkpoint_result = checkpoint_by_doi[doi_key]
            if checkpoint_result_is_compatible(checkpoint_result):
                result = revalidate_checkpoint_result(
                    dataset=dataset,
                    row_index=row_index,
                    row=row,
                    heuristic=heuristic,
                    result=checkpoint_result,
                    args=args,
                )
                checkpoint_rows_reused += 1
                results.append(result)
                flat_rows.append(result["flat"])
                if args.show_checkpoint_progress:
                    print(f"[{dataset} {local_index}/{len(selected)}] {doi} (checkpoint)", flush=True)
                    if not args.quiet_progress:
                        print_screening_row_followup(result["flat"], None, source="checkpoint")
                continue
            checkpoint_rows_reprocessed += 1
            print(f"[{dataset} {local_index}/{len(selected)}] {doi} (checkpoint incompatible; reprocessing)", flush=True)
            row_header_printed = True

        if not row_header_printed:
            print(f"[{dataset} {local_index}/{len(selected)}] {doi}", flush=True)
        heuristic = triage_by_doi.get(doi.lower(), {}) if doi else {}
        t_row = time.perf_counter()
        try:
            result = screen_row(dataset, row_index=row_index, row=row, heuristic=heuristic, args=args)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, Exception) as err:
            elapsed = time.perf_counter() - t_row
            status = "failed"
            adjudication = {}
            context = abstract_context(row)
            quote_verified = False
            flat = flatten_result(
                dataset=dataset,
                row_index=row_index,
                row=row,
                adjudication=adjudication,
                status="failed",
                quote_verified=quote_verified,
                verified_contexts=[],
                heuristic=heuristic,
                args=args,
                error=f"{type(err).__name__}: {err}",
            )
            result = {
                "input_row": screening_input_row(row_index, row),
                "candidate_contexts": compact_candidate_contexts(row, max_contexts=max(1, args.max_contexts)),
                "adjudication": adjudication,
                "verification": {
                    "quote_verified": quote_verified,
                    "verified_supported_context_count": 0,
                    "verified_supported_contexts": [],
                    "semantic_auto_eligible": False,
                    "download_queue_eligible": False,
                    "context_char_count": len(context),
                },
                "heuristic_comparison": {},
                "error": f"{type(err).__name__}: {err}",
                "flat": flat,
            }
            if not args.continue_on_error:
                results.append(result)
                flat_rows.append(flat)
                if not args.no_checkpoint and not args.dry_run:
                    append_checkpoint_result(ckpt_path, result)
                if not args.quiet_progress:
                    print_screening_row_followup(flat, elapsed, source="llm")
                break
        else:
            elapsed = time.perf_counter() - t_row

        results.append(result)
        flat_rows.append(result["flat"])
        if not args.no_checkpoint and not args.dry_run:
            append_checkpoint_result(ckpt_path, result)
        if not args.quiet_progress:
            print_screening_row_followup(result["flat"], elapsed, source="llm")

    download_rows = queue_rows_from_results(results, relevance_filter={"relevant", "uncertain"}, require_verified_context=False)
    relevant_rows = queue_rows_from_results(results, relevance_filter={"relevant"}, require_verified_context=True)
    uncertain_rows = queue_rows_from_results(results, relevance_filter={"uncertain"}, require_verified_context=False)
    download_written = write_doi_queue(paths["download_queue"], download_rows, f"LLM full-text candidate queue for {dataset}")
    relevant_written = write_doi_queue(paths["relevant_queue"], relevant_rows, f"LLM verified relevant context queue for {dataset}")
    uncertain_written = write_doi_queue(paths["uncertain_queue"], uncertain_rows, f"LLM uncertain full-text candidate queue for {dataset}")

    summary = {
        "papers_total": len(papers_all),
        "rows_after_filters": len(papers_filtered),
        "rows_requested": len(selected),
        "rows_completed": len([row for row in flat_rows if row.get("status") == "ok"]),
        "rows_failed": len([row for row in flat_rows if row.get("status") != "ok"]),
        "checkpoint_rows_reused": checkpoint_rows_reused,
        "checkpoint_rows_reprocessed": checkpoint_rows_reprocessed,
        "quote_verified": len([row for row in flat_rows if row.get("quote_verified") is True]),
        "semantic_auto_eligible": len([row for row in flat_rows if row.get("semantic_auto_eligible") is True]),
        "download_queue_eligible": len([row for row in flat_rows if row.get("download_queue_eligible") is True]),
        "download_queue_rows_written": download_written,
        "relevant_context_queue_rows_written": relevant_written,
        "uncertain_queue_rows_written": uncertain_written,
        "deterministic_prescreen_excluded": len(
            [row for row in flat_rows if row.get("screening_path") == "deterministic_excluded"]
        ),
        "fast_screen_excluded": len([row for row in flat_rows if row.get("screening_path") == "fast_excluded"]),
        "fast_screen_escalated": len([row for row in flat_rows if row.get("screening_path") == "fast_escalated"]),
        "by_status": dict(Counter(row.get("status", "") for row in flat_rows)),
        "by_llm_relevance": dict(Counter(row.get("llm_relevance", "") for row in flat_rows)),
        "by_screening_path": dict(Counter(row.get("screening_path", "") for row in flat_rows)),
        "heuristic_llm_relevance_disagreements": len(
            [row for row in flat_rows if row.get("heuristic_llm_relevance_disagreement") is True]
        ),
    }
    if status == "failed" and args.continue_on_error and summary["rows_completed"] > 0:
        status = "completed_with_errors"
    payload = {
        "generated_at_utc": now_utc(),
        "status": status,
        "dataset": dataset,
        "inputs": {
            "paper_db_json": str(paper_db_json),
            "triage_report_json": str(triage_report) if triage_report else None,
            "use_heuristic_audit": bool(args.use_heuristic_audit or args.triage_report_json),
            "model": args.model,
            "deterministic_prescreen": bool(args.deterministic_prescreen),
            "fast_screen_model": normalize(args.fast_screen_model) or None,
            "ollama_url": args.ollama_url,
            "limit": args.limit,
            "offset": args.offset,
            "doi_file": normalize(args.doi_file) or None,
            "doi_filter_count": len(doi_filter) if doi_filter is not None else None,
            "dry_run": args.dry_run,
            "only_with_abstract": args.only_with_abstract,
            "only_undownloaded": args.only_undownloaded,
            "only_heuristic_possible": args.only_heuristic_possible,
            "auto_confidence": args.auto_confidence,
            "context_confidence": args.context_confidence,
            "fast_screen_confidence": args.fast_screen_confidence,
            "reprocess_dois_file": normalize(args.reprocess_dois_file) or None,
            "reprocess_all_checkpoint_dois": bool(args.reprocess_all_checkpoint_dois),
        },
        "outputs": {
            "report_json": str(paths["out_json"]),
            "report_csv": str(paths["out_csv"]),
            "checkpoint_jsonl": str(ckpt_path),
            "download_queue": str(paths["download_queue"]),
            "relevant_queue": str(paths["relevant_queue"]),
            "uncertain_queue": str(paths["uncertain_queue"]),
        },
        "summary": summary,
        "rows": results,
    }
    write_json(paths["out_json"], payload)
    write_csv(paths["out_csv"], flat_rows)

    print(f"Dataset: {dataset}")
    print(f"Status: {status}")
    print(f"Rows completed: {summary['rows_completed']}")
    print(f"Rows failed: {summary['rows_failed']}")
    if args.resume_from_checkpoint:
        print(f"Checkpoint rows reused: {checkpoint_rows_reused}")
        print(f"Checkpoint rows reprocessed: {checkpoint_rows_reprocessed}")
    print(f"LLM relevance: {summary['by_llm_relevance']}")
    if args.deterministic_prescreen or normalize(args.fast_screen_model):
        print(f"Screening paths: {summary['by_screening_path']}")
    print(f"Quote verified: {summary['quote_verified']}")
    print(f"Semantic auto-eligible: {summary['semantic_auto_eligible']}")
    print(f"Download queue rows: {download_written}")
    print(f"Relevant context queue rows: {relevant_written}")
    print(f"Uncertain queue rows: {uncertain_written}")
    print(f"Report JSON: {paths['out_json']}")
    print(f"Report CSV: {paths['out_csv']}")
    if not args.no_checkpoint:
        print(f"Checkpoint JSONL: {ckpt_path}")
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", choices=[*DATASETS, "all"], required=True)
    parser.add_argument("--paper-db-json", default="", help="Override paper library JSON path; only valid for one dataset")
    parser.add_argument("--triage-report-json", default="", help="Optional existing heuristic triage report for comparison")
    parser.add_argument(
        "--use-heuristic-audit",
        action="store_true",
        help="Opt in to loading the old heuristic triage report for audit/safety comparison",
    )
    parser.add_argument("--out-json", default="", help="Output JSON path; only valid for one dataset")
    parser.add_argument("--out-csv", default="", help="Output CSV path; only valid for one dataset")
    parser.add_argument("--download-queue-out", default="", help="DOI-level full-text candidate queue; only valid for one dataset")
    parser.add_argument("--relevant-queue-out", default="", help="Verified relevant context queue; only valid for one dataset")
    parser.add_argument("--uncertain-queue-out", default="", help="Uncertain candidate queue; only valid for one dataset")
    parser.add_argument("--doi-file", default="", help="Optional DOI queue limiting which paper-library rows are screened")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument(
        "--fast-screen-model",
        default="",
        help=(
            "Optional cheaper Ollama model for first-pass obvious-irrelevant exclusions. "
            "Rows not confidently excluded are escalated to --model."
        ),
    )
    parser.add_argument("--ollama-url", default=DEFAULT_OLLAMA_URL)
    parser.add_argument("--limit", type=int, default=0, help="Rows to process; 0 means all after filters")
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--timeout-sec", type=int, default=300, help="Per-row Ollama timeout; 0 means wait indefinitely")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--num-ctx", type=int, default=16384)
    parser.add_argument(
        "--deterministic-prescreen",
        action="store_true",
        help=(
            "Skip LLM calls for obvious no-signal rows with enough abstract text, no in-scope intervention term, "
            "and no text-supported candidate context term. If heuristic audit is enabled, heuristic retention also blocks exclusion."
        ),
    )
    parser.add_argument(
        "--deterministic-prescreen-only",
        action="store_true",
        help="Run only the fast deterministic pass and write retained/excluded DOI queues; do not call Ollama.",
    )
    parser.add_argument("--fast-screen-timeout-sec", type=int, default=300)
    parser.add_argument("--fast-screen-temperature", type=float, default=0.0)
    parser.add_argument("--fast-screen-num-ctx", type=int, default=4096)
    parser.add_argument(
        "--fast-screen-confidence",
        type=float,
        default=0.9,
        help="Minimum fast-screen confidence required to skip the full model.",
    )
    parser.add_argument("--max-contexts", type=int, default=16)
    parser.add_argument("--auto-confidence", type=float, default=0.85)
    parser.add_argument("--context-confidence", type=float, default=0.75)
    parser.add_argument("--only-with-abstract", action="store_true")
    parser.add_argument("--only-undownloaded", action="store_true")
    parser.add_argument(
        "--only-heuristic-possible",
        action="store_true",
        help="Screen only rows the old heuristic labeled possible_relevant",
    )
    parser.add_argument("--dry-run", action="store_true", help="Build prompts/reports without calling Ollama")
    parser.add_argument("--skip-model-check", action="store_true")
    parser.add_argument("--continue-on-error", action="store_true")
    parser.add_argument(
        "--checkpoint-jsonl",
        default="",
        help="Append one JSON result per completed row; default is <out-json stem>.checkpoint.jsonl next to report",
    )
    parser.add_argument(
        "--resume-from-checkpoint",
        action="store_true",
        help="Skip DOIs already present in the checkpoint JSONL; append new rows to the same file",
    )
    parser.add_argument(
        "--materialize-checkpoint-only",
        action="store_true",
        help=(
            "Read the checkpoint JSONL, revalidate completed rows, and write the normal JSON/CSV/DOI queues "
            "without calling Ollama. Useful while a long local-LLM run is still in progress."
        ),
    )
    parser.add_argument(
        "--reprocess-dois-file",
        default="",
        help="With --resume-from-checkpoint: path to newline-separated DOIs to remove from the skip set so the LLM runs again (checkpoint JSONL is unchanged until new rows append)",
    )
    parser.add_argument(
        "--reprocess-all-checkpoint-dois",
        action="store_true",
        help="With --resume-from-checkpoint: do not skip any DOI from checkpoint; re-run the LLM for the whole batch (still appends to the same JSONL; last line per DOI wins on next resume)",
    )
    parser.add_argument(
        "--no-checkpoint",
        action="store_true",
        help="Disable per-row checkpoint JSONL (original behavior for final outputs only)",
    )
    parser.add_argument(
        "--quiet-progress",
        action="store_true",
        help="Do not print per-row summary lines after each paper (DOI line only)",
    )
    parser.add_argument(
        "--show-checkpoint-progress",
        action="store_true",
        help="Print every row reused from checkpoint. By default resume mode summarizes reused rows instead of replaying them.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.dataset == "all" and any(
        normalize(value)
        for value in [
            args.paper_db_json,
            args.triage_report_json,
            args.out_json,
            args.out_csv,
            args.download_queue_out,
            args.relevant_queue_out,
            args.uncertain_queue_out,
            args.doi_file,
        ]
    ):
        raise SystemExit("Per-dataset path overrides are only supported when --dataset is mechanistic or disorder")

    if args.deterministic_prescreen_only:
        args.deterministic_prescreen = True
        args.no_checkpoint = True

    if not args.dry_run and not args.skip_model_check and not args.deterministic_prescreen_only and not args.materialize_checkpoint_only:
        if not model_is_installed(args.model, args.ollama_url, timeout_sec=10):
            raise SystemExit(
                f"Ollama model `{args.model}` is not installed or Ollama is unavailable. "
                f"Install it with: ollama pull {args.model}"
            )
        fast_model = normalize(args.fast_screen_model)
        if fast_model and not model_is_installed(fast_model, args.ollama_url, timeout_sec=10):
            raise SystemExit(
                f"Ollama fast-screen model `{fast_model}` is not installed or Ollama is unavailable. "
                f"Install it with: ollama pull {fast_model}"
            )

    datasets = DATASETS if args.dataset == "all" else (args.dataset,)
    payloads = [run_dataset(dataset, args) for dataset in datasets]
    failed = any(payload.get("status") == "failed" for payload in payloads)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
