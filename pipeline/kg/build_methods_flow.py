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
CANDIDATE_PAPERS_TABLE = ROOT / "data" / "processed" / "corpus" / "candidate_papers.parquet"

PRISMA_CANDIDATE_PRESCREEN_LABELS = {
    "exclude_obvious_irrelevant": "No in-scope title/abstract signal",
    "exclude_no_usable_abstract": "No usable abstract and title alone insufficient",
    "exclude_missing_abstract": "No abstract available",
    "exclude_non_evidence_artifact": "Non-evidence artifact",
    "exclude_non_paper_container": "Non-report container",
    "exclude_preprint_or_unpublished": "Preprint or unpublished posted content",
    "unknown": "Screening status not available",
}

PRISMA_PUBLIC_LLM_SCREENING_LABELS = {
    "excluded_during_llm_screening": "Excluded during title and abstract screening",
    "background_context_only": "Kept as background/context only",
    "not_selected_for_extraction": "Not selected for evidence extraction",
    "unknown": "Title and abstract screening status not available",
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

GRAPH_DISPOSITION_LABELS = {
    "represented": "Represented in the evidence graph",
    "adjudicated_outside_scope": "Outside the evidence scope",
    "no_extractable_finding": "No specific finding to represent",
    "insufficient_source_text": "Available text is too limited",
    "source_not_verified": "Source document could not be verified",
    "not_results_report": "Not a results report",
    "unsupported_finding_detail": "Finding too broad or ambiguous",
    # Transitional values remain readable for older override files, but a
    # completed release should not contain them.
    "extraction_needed": "Extraction needs correction",
    "normalization_needed": "Normalization or assembly needs correction",
    "source_recovery_needed": "Better source text needed",
    "manual_review_needed": "Manual evidence review needed",
}

FINAL_GRAPH_EXCLUSION_ORDER = (
    "adjudicated_outside_scope",
    "no_extractable_finding",
    "insufficient_source_text",
    "source_not_verified",
    "not_results_report",
    "unsupported_finding_detail",
)
TRANSITIONAL_GRAPH_DISPOSITIONS = {
    "extraction_needed",
    "normalization_needed",
    "source_recovery_needed",
    "manual_review_needed",
}

METHODS_BIBLIOGRAPHY_STAGE_LABELS = {
    "selected_for_extraction": "Selected for evidence extraction",
    "excluded_during_llm_screening": "Excluded during title and abstract screening",
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
    "Outside the evidence scope",
    "No specific finding to represent",
    "Available text is too limited",
    "Source document could not be verified",
    "Not a results report",
    "Finding too broad or ambiguous",
    "Not reached",
)

METHODS_BIBLIOGRAPHY_SCREENING_REASONS = {
    "exclude_obvious_irrelevant": "No in-scope signal",
    "exclude_no_usable_abstract": "No usable abstract; title insufficient",
    "exclude_missing_abstract": "No abstract",
    "exclude_non_evidence_artifact": "Not an evidence report",
    "exclude_non_paper_container": "Journal/container record",
    "exclude_preprint_or_unpublished": "Preprint/unpublished",
    "retain_for_screening": "",
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


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def write_compact_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, separators=(",", ":"), ensure_ascii=False) + "\n", encoding="utf-8")


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


def validate_canonical_candidate_rows(rows: list[dict]) -> None:
    try:
        from pipeline.kg.update_corpus_graph_status import validate_candidate_ledger
    except ModuleNotFoundError:  # pragma: no cover - direct script execution path
        sys.path.insert(0, str(ROOT))
        from pipeline.kg.update_corpus_graph_status import validate_candidate_ledger
    import pandas as pd

    validate_candidate_ledger(pd.DataFrame(rows))


class MethodsFlowBuilder:
    def __init__(self, root: Path = ROOT, *, candidate_table: Path | None = None) -> None:
        self.candidate_table = (
            Path(candidate_table).resolve()
            if candidate_table is not None
            else (root / "data" / "processed" / "corpus" / "candidate_papers.parquet").resolve()
        )
        self.candidate_rows: list[dict] = []
        self.input_files: list[str] = []
        self.warnings: list[str] = []

    def build(self) -> dict:
        if not self.load_candidate_papers():
            raise FileNotFoundError(f"Canonical corpus table is required: {self.candidate_table}")
        validate_canonical_candidate_rows(self.candidate_rows)
        return self.payloads()

    def load_candidate_papers(self) -> bool:
        candidate_table = self.candidate_table
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

    def pipeline_status_view(self) -> dict:
        flow = prisma_flow_for_candidate_papers(self.candidate_rows)
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

    def payloads(self) -> dict:
        return {
            "pipeline_status": self.pipeline_status_view(),
            "methods_bibliography": candidate_bibliography_payload(self.candidate_rows),
            "graph_inclusion_dispositions": graph_inclusion_disposition_payload(self.candidate_rows),
            "manifest": {
                "contract_version": KG_VERSION,
                "generated_at": now_utc(),
                "input_files": sorted(set(self.input_files)),
                "warnings": self.warnings,
                "counts": {
                    "papers_found_by_search": len(self.candidate_rows),
                },
            },
        }


def candidate_field(row: dict, field: str, fallback: str = "unknown") -> str:
    value = normalize(row.get(field, ""))
    return value or fallback


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


def public_llm_screening_reason(row: dict) -> str:
    route_status = normalize(row.get("extraction_route_status", "")).lower()
    if route_status == "ready_for_article_text_extraction":
        return "The report was selected for evidence extraction."
    if route_status == "ready_for_abstract_extraction":
        return "The report was selected for evidence extraction."
    if route_status == "excluded_after_domain_screen":
        return strip_markup(row.get("extraction_domain_screening_reasons", "")) or (
            "Title and abstract screening did not identify an in-scope evidence topic for extraction."
        )
    if route_status == "context_only_or_skip":
        return "The report may be useful as background, but it is not part of the extracted evidence set."
    if not candidate_prescreen_retained(row):
        return "The record did not pass initial screening."
    return "No current evidence extraction assignment is stored for this record."


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
        return "fail", "Did not pass", public_llm_screening_reason(row)
    return "fail", "Did not pass", ""


def candidate_extraction_cell(row: dict) -> tuple[str, str, str]:
    if not candidate_prescreen_retained(row):
        return "not_reached", "Not reached", ""
    if not boolish(row.get("retained_for_extraction_candidate", False)):
        return "fail", "Not selected", ""
    return "pass", "Selected", ""


def candidate_kg_cell(row: dict) -> tuple[str, str, str]:
    if not boolish(row.get("retained_for_extraction_candidate", False)):
        return "not_reached", "Not reached", ""
    status = normalize(row.get("graph_inclusion_status", ""))
    disposition = normalize(row.get("graph_inclusion_disposition", ""))
    reason = strip_markup(row.get("graph_inclusion_reason", ""))
    if status == "represented" and disposition == "represented":
        return "pass", "In graph", reason
    if status == "not_represented" and disposition in GRAPH_DISPOSITION_LABELS:
        return "fail", GRAPH_DISPOSITION_LABELS[disposition], reason
    raise ValueError(
        "Canonical corpus has an invalid graph decision for "
        f"{normalize_doi(first_nonempty(row.get('doi', ''), row.get('study_doi', '')))}"
    )


def candidate_source_bucket(row: dict) -> str:
    source_type = normalize(
        first_nonempty(
            row.get("literature_source_type", ""),
            row.get("primary_secondary_source_type", ""),
        )
    ).lower()
    source_family = normalize(row.get("literature_source_family", "")).lower()
    if source_type in {"meta_analysis", "network_meta_analysis"} or "meta_analysis" in source_type:
        return "meta_analyses"
    if source_family == "secondary_literature" or (source_type and source_type != "primary"):
        return "reviews"
    return "primary_studies"


def candidate_graph_disposition(
    row: dict,
) -> dict:
    disposition = normalize(row.get("graph_inclusion_disposition", ""))
    if disposition not in GRAPH_DISPOSITION_LABELS:
        raise ValueError(f"Canonical corpus has invalid graph disposition {disposition!r}")
    _status, kg_label, kg_note = candidate_kg_cell(row)
    reason = strip_markup(row.get("graph_inclusion_reason", ""))
    next_action = strip_markup(row.get("graph_inclusion_next_action", ""))
    if not reason or not next_action:
        raise ValueError("Canonical corpus graph disposition lacks a reason or next action")
    return {
        "disposition": disposition,
        "disposition_label": GRAPH_DISPOSITION_LABELS[disposition],
        "reason": reason,
        "next_action": next_action,
        "kg_label": kg_label,
        "kg_note": kg_note,
    }


def graph_inclusion_disposition_payload(
    rows: Iterable[dict],
) -> dict:
    selected_rows = [row for row in rows if boolish(row.get("retained_for_extraction_candidate", False))]
    missing_rows: list[dict] = []
    disposition_counts: Counter = Counter()
    source_counts: Counter = Counter()
    source_disposition_counts: dict[str, Counter] = defaultdict(Counter)
    represented_count = 0
    for row in selected_rows:
        disposition = candidate_graph_disposition(row)
        source_bucket = candidate_source_bucket(row)
        source_counts[source_bucket] += 1
        disposition_counts[disposition["disposition"]] += 1
        source_disposition_counts[source_bucket][disposition["disposition"]] += 1
        if disposition["disposition"] == "represented":
            represented_count += 1
            continue
        doi = normalize_doi(first_nonempty(row.get("doi", ""), row.get("study_doi", "")))
        missing_rows.append(
            {
                "id": paper_id_for(
                    {
                        "study_doi": doi,
                        "openalex_id": row.get("openalex_id", ""),
                        "study_title": row.get("study_title", ""),
                        "study_year": row.get("study_year", ""),
                    }
                ),
                "doi": doi,
                "title": strip_markup(row.get("study_title", "")),
                "year": as_int(row.get("study_year", "")),
                "source_bucket": source_bucket,
                "source_type": normalize(row.get("literature_source_type", "")) or "primary",
                "source_text_state": normalize(row.get("source_text_state", "")),
                **disposition,
            }
        )
    missing_rows.sort(key=lambda row: (row["source_bucket"], row["disposition"], row["doi"], row["title"]))
    transitional_count = sum(disposition_counts[key] for key in TRANSITIONAL_GRAPH_DISPOSITIONS)
    return {
        "contract_version": KG_VERSION,
        "view": "graph_inclusion_dispositions",
        "generated_at": now_utc(),
        "unit": "selected reports",
        "scope": "underlying evidence graph",
        "counts": {
            "selected_papers": len(selected_rows),
            "represented_papers": represented_count,
            "not_represented_papers": len(missing_rows),
            "final_reasons_complete": transitional_count == 0,
            "transitional_reason_papers": transitional_count,
            "by_disposition": dict(sorted(disposition_counts.items())),
            "by_source": dict(sorted(source_counts.items())),
            "by_source_and_disposition": {
                source: dict(sorted(counts.items()))
                for source, counts in sorted(source_disposition_counts.items())
            },
        },
        "rows": missing_rows,
    }


def candidate_audit_decision(row: dict) -> dict:
    screening_status, screening_label, screening_note = candidate_screening_cell(row)
    llm_screening_status, llm_screening_label, llm_screening_note = candidate_llm_screening_cell(row)
    extraction_status, extraction_label, extraction_note = candidate_extraction_cell(row)
    kg_status, kg_label, kg_note = candidate_kg_cell(row)
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


def candidate_bibliography_row(
    row: dict,
) -> list:
    decision = candidate_audit_decision(row)
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
) -> dict:
    bibliography_rows = sorted(
        (candidate_bibliography_row(row) for row in rows),
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
        "unit": "records",
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
) -> dict:
    rows = list(props_rows)
    decisions = [
        (row, candidate_audit_decision(row))
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
    kg_not_included_dispositions = [
        candidate_graph_disposition(row)
        for row, _decision in kg_not_included
    ]
    kg_not_included_reasons = Counter(item["disposition"] for item in kg_not_included_dispositions)
    not_screened_reasons = Counter({"no_prescreen_status": len(not_screened_rows)}) if not_screened_rows else Counter()

    return {
        "dataset": "overall",
        "label": "Search and graph-inclusion flow",
        "unit": "records and reports",
        "current_stage": "kg_inclusion_summary",
        "metrics": {
            "selected_papers": len(extraction_selected),
            "represented_in_knowledge_graph": len(kg_included_rows),
            "not_represented_in_knowledge_graph": len(kg_not_included),
            "finding_counts_available": True,
        },
        "steps": {
            "records_identified": {
                "label": "Records found by the search",
                "count": len(rows),
            },
            "records_screened": {
                "label": "Records screened for relevance",
                "count": len(screened_rows),
            },
            "prescreen_retained": {
                "label": "Records kept after initial screening",
                "count": len(prescreen_retained_rows),
            },
            "evidence_extraction_selected": {
                "label": "Reports selected for evidence extraction",
                "count": len(extraction_selected),
            },
            "kg_included": {
                "label": "Reports represented in the knowledge graph",
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
                "label": "Records excluded during initial screening",
                "count": len(prescreen_excluded_rows),
                "reasons": labeled_reason_counts(
                    prescreen_reasons,
                    PRISMA_CANDIDATE_PRESCREEN_LABELS,
                    (
                        "exclude_obvious_irrelevant",
                        "exclude_no_usable_abstract",
                        "exclude_missing_abstract",
                        "exclude_non_evidence_artifact",
                        "exclude_non_paper_container",
                        "exclude_preprint_or_unpublished",
                        "unknown",
                    ),
                ),
            },
            "route_not_selected": {
                "label": "Records not selected for evidence extraction",
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
                "label": "Selected reports not represented in graph",
                "count": len(kg_not_included),
                "reasons": labeled_reason_counts(
                    kg_not_included_reasons,
                    GRAPH_DISPOSITION_LABELS,
                    FINAL_GRAPH_EXCLUSION_ORDER,
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
                "description": "Methods-page PRISMA-style record search and report-selection flow with public status summary.",
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
                "description": "Complete record audit with sequential initial-screening, title-and-abstract-screening, report extraction, and knowledge-graph representation labels.",
            },
            "graph_inclusion_dispositions": {
                "required": [
                    "contract_version",
                    "view",
                    "generated_at",
                    "unit",
                    "scope",
                    "counts",
                    "rows",
                ],
                "description": "Final, plain-language reason for every selected report that is not represented in the underlying evidence graph.",
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

    outputs["graph_inclusion_dispositions"] = str(out_dir / "views" / "graph_inclusion_dispositions.json")
    write_json(Path(outputs["graph_inclusion_dispositions"]), payloads["graph_inclusion_dispositions"])

    manifest = dict(payloads["manifest"])
    manifest["outputs"] = outputs
    outputs["manifest"] = str(out_dir / "manifests" / "build_manifest.json")
    write_json(Path(outputs["manifest"]), manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the methods-page record-and-report flow projection")
    parser.add_argument("--out-dir", default=str(ROOT / "data" / "kg"), help="Output directory for generated methods flow files")
    parser.add_argument(
        "--candidate-table",
        default=str(CANDIDATE_PAPERS_TABLE),
        help="Canonical one-row-per-DOI corpus ledger. No alternate inputs are accepted.",
    )
    args = parser.parse_args()

    out_dir = Path(args.out_dir).resolve()
    builder = MethodsFlowBuilder(ROOT, candidate_table=Path(args.candidate_table))
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
