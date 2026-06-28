#!/usr/bin/env python3
"""Build the normalized evidence-table backbone for the knowledge graph.

This stage keeps the extraction JSON/JSONL files as the raw audit trail, but
materializes normalized claim rows as columnar tables that can power multiple
UI projections.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Iterable

import pandas as pd

try:
    from pipeline.extract.clinical_comparator import normalize_clinical_comparator
    from pipeline.extract.clinical_followup_window import normalize_clinical_followup_window
    from pipeline.extract.mechanistic_assay_family import normalize_mechanistic_assay_family
    from pipeline.extract.extraction_v1_utils import normalize, write_json
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from pipeline.extract.clinical_comparator import normalize_clinical_comparator
    from pipeline.extract.clinical_followup_window import normalize_clinical_followup_window
    from pipeline.extract.mechanistic_assay_family import normalize_mechanistic_assay_family
    from pipeline.extract.extraction_v1_utils import normalize, write_json


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EXTRACTION_DIR = ROOT / "data" / "processed" / "extraction"
DEFAULT_OUT_DIR = ROOT / "data" / "processed" / "kg"
DEFAULT_REGISTRY_PATH = ROOT / "data" / "curated" / "entity_registry.json"
DEFAULT_NODE_VOCABULARY_PATH = ROOT / "schema" / "kg_node_vocabularies.json"
DEFAULT_PAPER_LIBRARY_PATHS = {
    "disorder": ROOT / "data" / "processed" / "paper_library_disorder.csv",
    "mechanistic": ROOT / "data" / "processed" / "paper_library_mechanistic.csv",
}
KG_TABLE_VERSION = "0.1"

GRAPH_SOURCES = {
    "routed_extractions": {
        "path": DEFAULT_EXTRACTION_DIR / "routed_evidence_rows.json",
        "domain": "routed",
        "dataset": "routed",
        "default_evidence_type": "primary_evidence",
        "skip_audit": True,
    },
    "mechanistic_primary": {
        "path": DEFAULT_EXTRACTION_DIR / "mechanistic_graph_claims.json",
        "audit_path": DEFAULT_EXTRACTION_DIR / "mechanistic_normalization_audit.json",
        "domain": "mechanistic",
        "dataset": "mechanistic",
        "default_evidence_type": "primary_evidence",
    },
    "mechanistic_secondary": {
        "path": DEFAULT_EXTRACTION_DIR / "mechanistic_secondary_graph_claims.json",
        "audit_path": DEFAULT_EXTRACTION_DIR / "mechanistic_secondary_normalization_audit.json",
        "domain": "mechanistic",
        "dataset": "mechanistic",
        "default_evidence_type": "secondary_literature",
    },
    "clinical_primary": {
        "path": DEFAULT_EXTRACTION_DIR / "disorder_graph_claims.json",
        "audit_path": DEFAULT_EXTRACTION_DIR / "disorder_normalization_audit.json",
        "domain": "clinical",
        "dataset": "disorder",
        "default_evidence_type": "primary_evidence",
    },
    "clinical_primary_endpoints": {
        "path": DEFAULT_EXTRACTION_DIR / "disorder_claims.json",
        "audit_path": DEFAULT_EXTRACTION_DIR / "disorder_normalization_audit.json",
        "domain": "clinical",
        "dataset": "disorder",
        "default_evidence_type": "primary_evidence",
        "transform": "clinical_endpoints",
        "skip_audit": True,
    },
    "clinical_secondary": {
        "path": DEFAULT_EXTRACTION_DIR / "disorder_secondary_graph_claims.json",
        "audit_path": DEFAULT_EXTRACTION_DIR / "disorder_secondary_normalization_audit.json",
        "domain": "clinical",
        "dataset": "disorder",
        "default_evidence_type": "secondary_literature",
    },
}

PAPER_FIELDS = (
    "study_doi",
    "openalex_id",
    "study_title",
    "authors",
    "study_year",
    "study_journal",
    "publication_type",
    "publication_date",
    "publisher",
    "journal_issn",
    "journal_eissn",
    "language",
    "mesh_terms",
    "keywords",
    "funders",
    "grant_ids",
    "trial_registry_ids",
    "study_design",
    "funding",
    "conflicts_of_interest",
    "risk_of_bias_summary",
    "source_access_level",
    "open_access_is_oa",
    "open_access_status",
    "open_access_url",
    "unpaywall_is_oa",
    "unpaywall_oa_status",
    "unpaywall_license",
)

CLAIM_FIELDS = (
    "claim_type",
    "raw_entity_label",
    "entity_role",
    "clinical_context_condition",
    "graph_entity_label",
    "graph_entity_type",
    "graph_exclusion_reason",
    "mechanism_type",
    "assay_type",
    "assay_family",
    "assay_family_normalized",
    "action_type",
    "affinity_type",
    "affinity_value",
    "affinity_unit",
    "species",
    "model_or_system",
    "system",
    "outcome_type",
    "outcome_domain",
    "result_direction",
    "outcome_measure",
    "outcome_measure_normalized",
    "population",
    "sample_size_total",
    "sample_size_by_arm",
    "comparator",
    "comparator_normalized",
    "follow_up_duration",
    "follow_up_window_normalized",
    "intervention_or_exposure",
    "dose",
    "route",
    "session_count_or_duration",
    "primary_outcome",
    "assessment_timepoint",
    "effect_size",
    "p_value",
    "confidence_interval",
    "adverse_events",
    "evidence_level",
    "support",
    "confidence",
    "needs_human_review",
    "supporting_quote",
    "evidence_location",
    "evidence_locator",
    "paper_assessment_route",
    "source_type",
    "source_family",
    "paper_type",
    "access_level",
    "evidence_strength",
    "notes",
    "normalization_status",
    "normalization_notes",
    "compound_original",
    "target_original",
    "disorder_original",
    "graph_entity_original",
    "compound_match_type",
    "entity_match_type",
    "compound_registry_status",
    "entity_registry_status",
    "kg_entity_kind_override",
    "endpoint_label_source",
)

PRIMARY_MARKERS = {"primary_evidence", "primary_study", "primary_results"}
SECONDARY_MARKERS = {"secondary_literature", "secondary_evidence", "review", "meta_analysis", "systematic_review"}
MECHANISTIC_ENTITY_KIND_OVERRIDES = {"target", "pathway_process", "biomarker_readout", "system_family"}
ROUTE_NATIVE_ENTITY_KINDS = {
    "brain_region",
    "brain_network",
    "neural_circuit",
    "cognitive_behavioral_construct",
    "subjective_experience_construct",
    "pharmacokinetic_parameter",
    "intervention_component",
    "public_health_measure",
}
GRAPH_ENTITY_KINDS = {
    "compound",
    "condition_indication",
    "symptom_problem",
    "safety_adverse_event",
    "outcome_scale",
    "target",
    "pathway_process",
    "biomarker_readout",
    "system_family",
    *ROUTE_NATIVE_ENTITY_KINDS,
}
ENTITY_TYPE_BY_KIND = {
    "compound": "compound",
    "condition_indication": "clinical_entity",
    "symptom_problem": "clinical_entity",
    "safety_adverse_event": "clinical_entity",
    "outcome_scale": "clinical_entity",
    "target": "mechanistic_entity",
    "pathway_process": "mechanistic_entity",
    "biomarker_readout": "mechanistic_entity",
    "system_family": "mechanistic_entity",
    "brain_region": "brain_system_entity",
    "brain_network": "brain_system_entity",
    "neural_circuit": "brain_system_entity",
    "cognitive_behavioral_construct": "behavioral_entity",
    "subjective_experience_construct": "subjective_experience_entity",
    "pharmacokinetic_parameter": "exposure_entity",
    "intervention_component": "intervention_entity",
    "public_health_measure": "public_health_entity",
}
ENTITY_KIND_ALIASES = {
    "molecular_readout": "biomarker_readout",
    "brain_readout": "biomarker_readout",
    "neural_readout": "biomarker_readout",
    "pk_parameter": "pharmacokinetic_parameter",
    "pk_or_exposure_parameter": "pharmacokinetic_parameter",
}
DOMAIN_DEFAULT_ENTITY_KIND = {
    "clinical_outcome": "condition_indication",
    "safety_tolerability": "safety_adverse_event",
    "molecular_target": "target",
    "molecular_pathway_readout": "pathway_process",
    "brain_system": "brain_network",
    "cognitive_behavioral": "cognitive_behavioral_construct",
    "behavioral": "cognitive_behavioral_construct",
    "subjective_experience": "subjective_experience_construct",
    "pharmacokinetics_exposure": "pharmacokinetic_parameter",
    "exposure": "pharmacokinetic_parameter",
    "intervention_context": "intervention_component",
    "intervention": "intervention_component",
    "real_world_public_health": "public_health_measure",
    "public_health": "public_health_measure",
}
COMPOUND_LABEL_FIELDS = (
    "compound",
    "canonical_compound",
    "compound_or_class",
    "compound_or_exposure",
    "compound_or_intervention",
    "compound_or_analyte",
    "intervention_or_exposure",
    "exposure_or_intervention",
    "exposure_or_policy",
)
ENTITY_LABEL_FIELDS_BY_KIND = {
    "target": ("target", "metabolic_or_transport_target", "graph_entity_label", "entity_label", "entity"),
    "pathway_process": (
        "pathway_or_process",
        "pathway_or_readout",
        "metabolic_or_transport_pathway",
        "graph_entity_label",
        "entity_label",
        "entity",
    ),
    "biomarker_readout": (
        "readout_or_biomarker",
        "readout_or_measure",
        "readout",
        "outcome_measure",
        "graph_entity_label",
        "entity_label",
        "entity",
    ),
    "brain_region": ("brain_region", "graph_entity_label", "entity_label", "entity"),
    "brain_network": ("brain_network", "graph_entity_label", "entity_label", "entity"),
    "neural_circuit": ("neural_circuit", "connectivity_or_circuit_relationship", "graph_entity_label", "entity_label", "entity"),
    "cognitive_behavioral_construct": (
        "construct_or_behavior",
        "behavior_or_task",
        "task_or_measure",
        "graph_entity_label",
        "entity_label",
        "entity",
    ),
    "subjective_experience_construct": (
        "subjective_construct",
        "subjective_construct_category",
        "graph_entity_label",
        "entity_label",
        "entity",
    ),
    "pharmacokinetic_parameter": ("pk_or_exposure_parameter", "graph_entity_label", "entity_label", "entity"),
    "compound": ("metabolite_or_analyte", "compound_or_analyte", "graph_entity_label", "entity_label", "entity"),
    "intervention_component": (
        "context_component",
        "component_type",
        "intervention_model_or_orientation",
        "graph_entity_label",
        "entity_label",
        "entity",
    ),
    "public_health_measure": (
        "public_health_measure",
        "public_health_topic_category",
        "graph_entity_label",
        "entity_label",
        "entity",
    ),
}
MECHANISTIC_BIOMARKER_LABELS = {
    "Arc",
    "BDNF",
    "c-Fos",
    "DOPAC",
    "Dopamine",
    "GDNF",
    "GFAP",
    "Glutamate",
    "HSP70",
    "HVA",
    "IGF1",
    "IL-1beta",
    "IL-6",
    "IL-8",
    "Myelin basic protein",
    "Neurofilament light chain",
    "NGF",
    "Norepinephrine",
    "Prolactin",
    "PSD-95 (DLG4)",
    "Serotonin",
    "TGF-beta",
    "TNF-alpha",
}


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def load_json_array(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, list):
        raise ValueError(f"Expected JSON array at {path}")
    return [row for row in data if isinstance(row, dict)]


def load_json_object(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object at {path}")
    return data


def normalize_doi(value: object) -> str:
    text = normalize(value)
    lowered = text.lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/", "http://dx.doi.org/", "doi:"):
        if lowered.startswith(prefix):
            text = text[len(prefix) :]
            break
    return text.strip().lower()


def slug(value: object, fallback: str = "id") -> str:
    text = normalize(value).casefold()
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    if text:
        return text[:140]
    digest = hashlib.sha1(normalize(value).encode("utf-8")).hexdigest()[:12]
    return f"{fallback}_{digest}"


def stable_id(prefix: str, *parts: object, length: int = 18) -> str:
    canonical = "|".join(normalize(part) for part in parts)
    digest = hashlib.sha1(canonical.encode("utf-8")).hexdigest()[:length]
    return f"{prefix}:{digest}"


def json_dumps(value: object) -> str:
    if value in (None, ""):
        return ""
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return normalize(value).casefold() in {"true", "1", "yes", "y"}


def as_int_or_none(value: object) -> int | None:
    text = normalize(value)
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def as_float_or_none(value: object) -> float | None:
    text = normalize(value)
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def paper_id_for(row: dict) -> str:
    doi = normalize_doi(row.get("study_doi", ""))
    if doi:
        return f"paper:{doi}"
    openalex_id = normalize(row.get("openalex_id", ""))
    if openalex_id:
        return f"paper:openalex:{slug(openalex_id)}"
    return stable_id("paper", row.get("study_title", ""), row.get("study_year", ""), row.get("study_journal", ""))


def entity_id_for(entity_type: str, label: object) -> str:
    return f"{entity_type}:{slug(label, entity_type)}"


def label_key(value: object) -> str:
    text = normalize(value).casefold()
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def normalized_entity_kind(value: object) -> str:
    key = normalize(value).casefold().replace("-", "_").replace(" ", "_")
    return ENTITY_KIND_ALIASES.get(key, key)


def first_normalized_value(row: dict, fields: Iterable[str]) -> str:
    for field in fields:
        value = normalize(row.get(field, ""))
        if value:
            return value
    return ""


def compound_label_for(row: dict) -> str:
    return first_normalized_value(row, COMPOUND_LABEL_FIELDS)


def node_vocabulary_lookup(path: Path = DEFAULT_NODE_VOCABULARY_PATH) -> dict[tuple[str, str], dict]:
    data = load_json_object(path)
    out: dict[tuple[str, str], dict] = {}
    node_kinds = data.get("node_kinds", {})
    if not isinstance(node_kinds, dict):
        return out
    for kind, entries in node_kinds.items():
        normalized_kind = normalized_entity_kind(kind)
        if normalized_kind not in GRAPH_ENTITY_KINDS or not isinstance(entries, list):
            continue
        for item in entries:
            if not isinstance(item, dict):
                continue
            label = normalize(item.get("label", ""))
            if not label:
                continue
            labels = [label]
            labels.extend(normalize(alias) for alias in item.get("aliases", []) if normalize(alias))
            for candidate in labels:
                out[(normalized_kind, label_key(candidate))] = item
    return out


def canonicalize_node_label(entity_kind: str, label: str, node_vocabulary: dict[tuple[str, str], dict]) -> tuple[str, dict | None]:
    item = node_vocabulary.get((entity_kind, label_key(label)))
    if not item:
        return label, None
    canonical = normalize(item.get("label", "")) or label
    return canonical, item


def registry_lookup(registry_path: Path) -> dict[tuple[str, str], dict]:
    registry = load_json_object(registry_path)
    out: dict[tuple[str, str], dict] = {}
    for category, entity_type in (("compounds", "compound"), ("targets", "mechanistic_entity"), ("disorders", "clinical_entity")):
        for item in registry.get(category, []):
            if not isinstance(item, dict):
                continue
            label = normalize(item.get("label", ""))
            if not label:
                continue
            out[(entity_type, label)] = item
    return out


OPEN_ACCESS_FIELDS = (
    "open_access_is_oa",
    "open_access_status",
    "open_access_url",
    "unpaywall_is_oa",
    "unpaywall_oa_status",
    "unpaywall_license",
)


def paper_library_lookup(path: Path) -> dict[tuple[str, str], dict]:
    if not path.exists():
        return {}
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    out: dict[tuple[str, str], dict] = {}
    for record in df.to_dict(orient="records"):
        metadata = {field: normalize(record.get(field, "")) for field in OPEN_ACCESS_FIELDS}
        if not any(metadata.values()):
            continue
        doi = normalize_doi(record.get("study_doi", ""))
        if doi:
            out.setdefault(("doi", doi), metadata)
        openalex_id = normalize(record.get("openalex_id", ""))
        if openalex_id:
            out.setdefault(("openalex", openalex_id), metadata)
    return out


def paper_library_lookups(paths: dict[str, Path] | None = None) -> dict[str, dict[tuple[str, str], dict]]:
    paths = paths or DEFAULT_PAPER_LIBRARY_PATHS
    return {dataset: paper_library_lookup(path) for dataset, path in paths.items()}


def enrich_open_access_metadata(row: dict, lookup: dict[tuple[str, str], dict]) -> dict:
    doi = normalize_doi(row.get("study_doi", ""))
    openalex_id = normalize(row.get("openalex_id", ""))
    metadata = lookup.get(("doi", doi)) if doi else None
    if not metadata and openalex_id:
        metadata = lookup.get(("openalex", openalex_id))
    if not metadata:
        return row
    out = dict(row)
    for field, value in metadata.items():
        if value and not normalize(out.get(field, "")):
            out[field] = value
    return out


COMPOUND_BLOCK_STATUSES = {
    "compound_class_not_graphable",
    "compound_combo_not_graphable",
    "compound_reference_not_graphable",
    "compound_unmapped",
}
EMPTY_ENDPOINT_VALUES = {"", "none", "not_applicable", "not applicable", "not_reported", "not reported", "unknown", "uncertain"}
SKIPPED_CLINICAL_GRAPH_ROLES = {"functional_outcome", "patient_reported_outcome"}
SAFETY_ENDPOINT_ROLES = {"safety_or_adverse_event"}
SAFETY_PHYSIOLOGY_TERMS = {"safety", "adverse", "tolerability", "cardiovascular", "respiratory", "vital"}
SYMPTOM_ROLE_VALUES = {"symptom_or_problem"}
ALWAYS_SYMPTOM_LABELS = {
    "Anxiety",
    "Depression",
    "Pain",
    "Demoralization",
    "Anhedonia",
    "Psychosis",
    "Suicidal ideation",
    "Complicated grief",
}
BROAD_SYMPTOM_OUTCOME_LABELS = {
    "Anxiety",
    "Depression",
    "Pain",
    "Somatization",
    "Stress",
}

SAFETY_ENDPOINT_PATTERNS = (
    (re.compile(r"\b(suicid|c[- ]?ssrs)\b", re.IGNORECASE), "Suicidality"),
    (re.compile(r"\b(mania|manic|hypomania|switch)\b", re.IGNORECASE), "Mania switch"),
    (re.compile(r"\b(flashback|hppd|persisting perceptual)\b", re.IGNORECASE), "Flashbacks/HPPD"),
    (re.compile(r"\b(blood pressure|heart rate|cardiovascular|hypertension|hypotension|qt|vital signs?)\b", re.IGNORECASE), "Cardiovascular safety"),
    (re.compile(r"\b(oxygen saturation|spo2|respiratory|breathing|respiration)\b", re.IGNORECASE), "Respiratory safety"),
    (re.compile(r"\b(nausea|vomit|emesis)\b", re.IGNORECASE), "Nausea/vomiting"),
    (re.compile(r"\b(headache|migraine)\b", re.IGNORECASE), "Headache"),
    (re.compile(r"\b(dissociation|dissociative)\b", re.IGNORECASE), "Dissociation"),
    (re.compile(r"\b(anxiety|panic)\b", re.IGNORECASE), "Anxiety/panic adverse effects"),
    (re.compile(r"\b(adverse|side effects?|serious adverse|tolerab|well tolerated|safety)\b", re.IGNORECASE), "Tolerability/adverse events"),
)


def compact_spaces(value: object) -> str:
    return re.sub(r"\s+", " ", normalize(value)).strip()


def endpoint_value(value: object) -> str:
    text = compact_spaces(value)
    if normalize(text).casefold() in EMPTY_ENDPOINT_VALUES:
        return ""
    return text


def title_endpoint_label(value: object) -> str:
    text = endpoint_value(value)
    if not text:
        return ""
    if len(text) > 80:
        return ""
    if text.isupper() and len(text) <= 12:
        return text
    return text[:1].upper() + text[1:]


def split_outcome_scales(value: object) -> list[str]:
    text = endpoint_value(value)
    if not text:
        return []
    parts = [endpoint_value(part) for part in re.split(r"\s*;\s*", text)]
    seen: set[str] = set()
    out: list[str] = []
    for part in parts:
        if not part:
            continue
        key = part.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(part)
    return out


def pattern_endpoint_label(row: dict, patterns: tuple[tuple[re.Pattern[str], str], ...], fallback: str) -> str:
    text = " ".join(
        endpoint_value(row.get(field, ""))
        for field in (
            "raw_entity_label",
            "outcome_domain",
            "outcome_type",
            "outcome_measure",
            "outcome_measure_normalized",
            "adverse_events",
        )
    )
    for pattern, label in patterns:
        if pattern.search(text):
            return label
    return fallback


def safety_endpoint_label(row: dict) -> str:
    return pattern_endpoint_label(row, SAFETY_ENDPOINT_PATTERNS, "Tolerability/adverse events")


def row_has_safety_physiology(row: dict) -> bool:
    role = normalize(row.get("entity_role", "")).casefold()
    if role != "physiological_measure":
        return False
    text = " ".join(normalize(row.get(field, "")).casefold() for field in ("outcome_type", "outcome_domain", "outcome_measure", "raw_entity_label"))
    return any(term in text for term in SAFETY_PHYSIOLOGY_TERMS)


def canonical_compound_from_audit(row: dict, audit: dict | None) -> str:
    audit = audit or {}
    if normalize(audit.get("normalization_status", "")) in COMPOUND_BLOCK_STATUSES:
        return ""
    return normalize(audit.get("canonical_compound", "")) or normalize(row.get("canonical_compound", ""))


def endpoint_row(row: dict, audit: dict | None, label: str, kind: str, role: str, label_source: str) -> dict | None:
    compound = canonical_compound_from_audit(row, audit)
    label = endpoint_value(label)
    if not compound or not label:
        return None

    out = dict(row)
    out["compound_original"] = normalize(row.get("compound", ""))
    out["compound"] = compound
    out["disorder_original"] = normalize(row.get("disorder", ""))
    out["graph_entity_original"] = normalize(row.get("raw_entity_label", "")) or normalize(row.get("outcome_measure", ""))
    out["disorder"] = label
    out["raw_entity_label"] = normalize(row.get("raw_entity_label", "")) or label
    out["entity_role"] = role
    out["graph_entity_label"] = label
    out["graph_entity_type"] = "none"
    out["graph_include_candidate"] = True
    out["graph_exclusion_reason"] = "not_applicable"
    out["normalization_status"] = "endpoint_normalized"
    out["normalization_notes"] = f"Derived KG endpoint view row from {label_source}"
    out["canonical_compound"] = compound
    out["canonical_entity"] = label
    out["compound_match_type"] = normalize((audit or {}).get("compound_match_type", ""))
    out["compound_registry_status"] = normalize((audit or {}).get("compound_registry_status", ""))
    out["entity_match_type"] = "derived_endpoint"
    out["entity_registry_status"] = "derived_endpoint"
    out["kg_entity_kind_override"] = kind
    out["endpoint_label_source"] = label_source
    return out


def clinical_endpoint_rows(rows: list[dict], audit_rows: list[dict]) -> list[dict]:
    out: list[dict] = []
    for index, row in enumerate(rows):
        audit = audit_rows[index] if index < len(audit_rows) and isinstance(audit_rows[index], dict) else {}
        role = normalize(row.get("entity_role", "")).casefold()

        if role in SAFETY_ENDPOINT_ROLES or row_has_safety_physiology(row):
            derived = endpoint_row(
                row,
                audit,
                safety_endpoint_label(row),
                "safety_adverse_event",
                normalize(row.get("entity_role", "")) or "safety_or_adverse_event",
                "safety_endpoint",
            )
            if derived:
                out.append(derived)

        for scale in split_outcome_scales(row.get("outcome_measure_normalized", "")):
            derived = endpoint_row(
                row,
                audit,
                scale,
                "outcome_scale",
                normalize(row.get("entity_role", "")) or "outcome_measure",
                "outcome_measure_normalized",
            )
            if derived:
                out.append(derived)
    return out


def rows_for_source(cfg: dict) -> list[dict]:
    rows = load_json_array(Path(cfg["path"]))
    if cfg.get("transform") == "clinical_endpoints":
        return clinical_endpoint_rows(rows, load_json_array(Path(cfg.get("audit_path", ""))))
    return rows


def should_skip_evidence_row(domain: str, row: dict) -> bool:
    if domain != "clinical":
        return False
    override = normalize(row.get("kg_entity_kind_override", "")).casefold()
    if override:
        return override == "functional_outcome"
    role = normalize(row.get("entity_role", "")).casefold()
    return role in SKIPPED_CLINICAL_GRAPH_ROLES or "functional" in role


def evidence_type_for(row: dict, default: str) -> str:
    if normalize(row.get("paper_assessment_route", "")) == "primary_evidence" and normalize(row.get("access_level", "")) != "secondary_summary":
        return "primary_evidence"
    values = {
        normalize(row.get("paper_assessment_route", "")),
        normalize(row.get("source_type", "")),
        normalize(row.get("source_family", "")),
        normalize(row.get("paper_type", "")),
        normalize(row.get("access_level", "")),
    }
    if values & SECONDARY_MARKERS or "secondary_summary" in values:
        return "secondary_literature"
    if values & PRIMARY_MARKERS:
        return "primary_evidence"
    return default


def mechanistic_entity_kind(row: dict, registry_item: dict | None = None) -> str:
    override = normalize(row.get("kg_entity_kind_override", "")).casefold()
    if override in MECHANISTIC_ENTITY_KIND_OVERRIDES:
        return override
    role = normalize(row.get("entity_role", "")).casefold()
    status = normalize((registry_item or {}).get("status", "")).casefold()
    label = normalize(row.get("target", ""))
    if "family" in status or "system" in status:
        return "system_family"
    if "pathway" in status or "process" in status:
        return "pathway_process"
    if "marker" in status or "readout" in status or "ligand" in status:
        return "biomarker_readout"
    if role == "pathway_or_process":
        return "pathway_process"
    if role == "biomarker":
        return "biomarker_readout"
    if label in MECHANISTIC_BIOMARKER_LABELS:
        return "biomarker_readout"
    return "target"


def clinical_entity_kind(row: dict, registry_item: dict | None = None) -> str:
    override = normalize(row.get("kg_entity_kind_override", "")).casefold()
    if override in {"condition_indication", "symptom_problem", "safety_adverse_event", "outcome_scale"}:
        return override
    role = normalize(row.get("entity_role", "")).casefold()
    status = normalize((registry_item or {}).get("status", "")).casefold()
    label = normalize(row.get("disorder", ""))
    if "safety" in role or "adverse" in role:
        return "safety_adverse_event"
    if "symptom" in status:
        return "symptom_problem"
    if label in ALWAYS_SYMPTOM_LABELS:
        return "symptom_problem"
    if registry_item and status:
        return "condition_indication"
    if role in SYMPTOM_ROLE_VALUES:
        return "symptom_problem"
    if role == "outcome_measure" and label in BROAD_SYMPTOM_OUTCOME_LABELS:
        return "symptom_problem"
    if role == "outcome_scale":
        return "outcome_scale"
    return "condition_indication"


def entity_kind_for(row: dict, domain: str, registry_item: dict | None = None) -> str:
    for field in ("kg_entity_kind_override", "primary_graph_anchor_kind", "graph_candidate_type", "graph_entity_type", "entity_type"):
        kind = normalized_entity_kind(row.get(field, ""))
        if kind in GRAPH_ENTITY_KINDS:
            return kind
    if domain == "mechanistic":
        return mechanistic_entity_kind(row, registry_item)
    if domain == "clinical":
        return clinical_entity_kind(row, registry_item)
    domain_key = normalize(domain).casefold()
    return DOMAIN_DEFAULT_ENTITY_KIND.get(domain_key, "condition_indication")


def entity_type_for_kind(entity_kind: str, domain: str) -> str:
    if entity_kind in ENTITY_TYPE_BY_KIND:
        return ENTITY_TYPE_BY_KIND[entity_kind]
    if domain == "mechanistic":
        return "mechanistic_entity"
    if domain == "clinical":
        return "clinical_entity"
    return f"{slug(domain, 'domain')}_entity"


def entity_label_for(row: dict, domain: str, entity_kind: str) -> str:
    explicit_label = first_normalized_value(row, ("graph_entity_label", "entity_label"))
    if explicit_label:
        return explicit_label
    fields = ENTITY_LABEL_FIELDS_BY_KIND.get(entity_kind, ())
    label = first_normalized_value(row, fields)
    if label:
        return label
    if domain == "mechanistic":
        return normalize(row.get("target", ""))
    if domain == "clinical":
        return normalize(row.get("disorder", ""))
    return first_normalized_value(row, ("graph_entity_label", "entity_label", "entity", "target", "disorder"))


def relation_type_for(domain: str, entity_kind: str, evidence_type: str) -> str:
    if evidence_type == "secondary_literature":
        return "discusses_relationship"
    if entity_kind in {"brain_region", "brain_network", "neural_circuit"} or domain == "brain_system":
        return "has_brain_system_effect"
    if entity_kind == "cognitive_behavioral_construct" or domain in {"cognitive_behavioral", "behavioral"}:
        return "has_cognitive_behavioral_effect"
    if entity_kind == "subjective_experience_construct" or domain == "subjective_experience":
        return "has_subjective_experience_effect"
    if entity_kind == "pharmacokinetic_parameter" or domain in {"pharmacokinetics_exposure", "exposure"}:
        return "has_pharmacokinetic_exposure"
    if entity_kind == "intervention_component" or domain in {"intervention_context", "intervention"}:
        return "uses_intervention_component"
    if entity_kind == "public_health_measure" or domain in {"real_world_public_health", "public_health"}:
        return "has_public_health_evidence"
    if entity_kind == "target" or domain == "molecular_target":
        return "has_mechanistic_target"
    if entity_kind == "pathway_process" or domain == "molecular_pathway_readout":
        return "has_mechanistic_pathway"
    if entity_kind == "biomarker_readout":
        return "has_biomarker_readout"
    if domain == "mechanistic":
        if entity_kind == "target":
            return "has_mechanistic_target"
        if entity_kind == "pathway_process":
            return "has_mechanistic_pathway"
        if entity_kind == "biomarker_readout":
            return "has_biomarker_readout"
        return "has_mechanistic_system"
    if entity_kind == "condition_indication":
        return "studied_for_condition"
    if entity_kind == "symptom_problem":
        return "studied_for_symptom"
    if entity_kind == "safety_adverse_event":
        return "reports_safety_signal"
    return "reports_outcome_scale"


def paper_row(row: dict, paper_id: str) -> dict:
    out = {
        "paper_id": paper_id,
        "doi": normalize_doi(row.get("study_doi", "")),
        "openalex_id": normalize(row.get("openalex_id", "")),
        "title": normalize(row.get("study_title", "")),
        "authors": normalize(row.get("authors", "")),
        "year": as_int_or_none(row.get("study_year", "")),
        "journal": normalize(row.get("study_journal", "")),
    }
    for field in PAPER_FIELDS:
        out[field] = normalize(row.get(field, ""))
    return out


def entity_row(entity_id: str, entity_type: str, domain: str, label: str, kind: str, registry_item: dict | None) -> dict:
    registry_item = registry_item or {}
    return {
        "entity_id": entity_id,
        "entity_type": entity_type,
        "domain": domain,
        "entity_kind": kind,
        "label": label,
        "registry_status": normalize(registry_item.get("status", "")),
        "aliases_json": json_dumps(registry_item.get("aliases", [])),
        "ids_json": json_dumps(registry_item.get("ids", {})),
    }


def normalize_claim_metadata(row: dict, domain: str) -> dict:
    out = dict(row)
    if domain == "mechanistic" and not normalize(out.get("assay_family_normalized", "")):
        out["assay_family_normalized"] = normalize_mechanistic_assay_family(
            out.get("assay_family", ""),
            out.get("assay_type", ""),
        )
    if domain == "clinical" and not normalize(out.get("comparator_normalized", "")):
        out["comparator_normalized"] = normalize_clinical_comparator(out.get("comparator", ""))
    if domain == "clinical" and not normalize(out.get("follow_up_window_normalized", "")):
        out["follow_up_window_normalized"] = normalize_clinical_followup_window(
            out.get("follow_up_duration", ""),
            out.get("assessment_timepoint", "") or out.get("timepoint", ""),
        )
    return out


def claim_row(row: dict, source_name: str, domain: str, dataset: str, evidence_type: str, claim_id: str, paper_id: str) -> dict:
    row = normalize_claim_metadata(row, domain)
    entity_kind = entity_kind_for(row, domain)
    entity_label = entity_label_for(row, domain, entity_kind)
    out = {
        "claim_id": claim_id,
        "source_name": source_name,
        "domain": domain,
        "dataset": dataset,
        "evidence_type": evidence_type,
        "paper_id": paper_id,
        "study_doi": normalize_doi(row.get("study_doi", "")),
        "study_year": as_int_or_none(row.get("study_year", "")),
        "compound": compound_label_for(row),
        "entity_label": entity_label,
        "raw_row_json": json_dumps(row),
    }
    for field in CLAIM_FIELDS:
        value = row.get(field, "")
        if field in {"confidence", "affinity_value"}:
            out[field] = as_float_or_none(value)
        elif field == "needs_human_review":
            out[field] = as_bool(value)
        else:
            out[field] = normalize(value)
    return out


def evidence_edge_row(
    row: dict,
    source_name: str,
    domain: str,
    dataset: str,
    evidence_type: str,
    entity_kind: str,
    claim_id: str,
    evidence_id: str,
    paper_id: str,
    compound_id: str,
    entity_id: str,
) -> dict:
    entity_label = entity_label_for(row, domain, entity_kind)
    relation_type = relation_type_for(domain, entity_kind, evidence_type)
    return {
        "evidence_id": evidence_id,
        "claim_id": claim_id,
        "source_name": source_name,
        "domain": domain,
        "dataset": dataset,
        "entity_kind": entity_kind,
        "evidence_type": evidence_type,
        "relation_type": relation_type,
        "compound_id": compound_id,
        "compound": compound_label_for(row),
        "entity_id": entity_id,
        "entity_label": entity_label,
        "paper_id": paper_id,
        "study_doi": normalize_doi(row.get("study_doi", "")),
        "study_year": as_int_or_none(row.get("study_year", "")),
        "direction": normalize(row.get("result_direction", "")),
        "support": normalize(row.get("support", "")),
        "confidence": as_float_or_none(row.get("confidence", "")),
        "evidence_level": normalize(row.get("evidence_level", "")),
        "source_type": normalize(row.get("source_type", "")),
        "source_family": normalize(row.get("source_family", "")),
        "paper_type": normalize(row.get("paper_type", "")),
        "access_level": normalize(row.get("access_level", "")),
        "sample_size_total": normalize(row.get("sample_size_total", "")),
        "outcome_measure": normalize(row.get("outcome_measure", "")),
        "outcome_measure_normalized": normalize(row.get("outcome_measure_normalized", "")),
        "effect_size": normalize(row.get("effect_size", "")),
        "p_value": normalize(row.get("p_value", "")),
        "confidence_interval": normalize(row.get("confidence_interval", "")),
        "evidence_location": normalize(row.get("evidence_location", "")),
        "evidence_locator": normalize(row.get("evidence_locator", "")),
        "supporting_quote": normalize(row.get("supporting_quote", "")),
    }


def audit_row(row: dict, source_name: str, domain: str, dataset: str) -> dict:
    entity_kind = entity_kind_for(row, domain)
    return {
        "source_name": source_name,
        "domain": domain,
        "dataset": dataset,
        "normalization_status": normalize(row.get("normalization_status", "")),
        "normalization_notes": normalize(row.get("normalization_notes", "")),
        "compound": compound_label_for(row),
        "canonical_compound": normalize(row.get("canonical_compound", "")),
        "entity_label": entity_label_for(row, domain, entity_kind),
        "canonical_entity": normalize(row.get("canonical_entity", "")),
        "entity_role": normalize(row.get("entity_role", "")),
        "graph_entity_type": normalize(row.get("graph_entity_type", "")),
        "graph_include_candidate": as_bool(row.get("graph_include_candidate", "")),
        "study_doi": normalize_doi(row.get("study_doi", "")),
        "study_title": normalize(row.get("study_title", "")),
        "raw_row_json": json_dumps(row),
    }


def dataframe(rows: list[dict], columns: Iterable[str] | None = None) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    if columns:
        for column in columns:
            if column not in df.columns:
                df[column] = None
        df = df[list(columns)]
    return df


def write_parquet(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, engine="pyarrow", index=False)


def build_tables(
    *,
    graph_sources: dict[str, dict] | None = None,
    registry_path: Path = DEFAULT_REGISTRY_PATH,
    node_vocabulary_path: Path = DEFAULT_NODE_VOCABULARY_PATH,
    out_dir: Path = DEFAULT_OUT_DIR,
    write_duckdb: bool = True,
) -> dict:
    graph_sources = graph_sources or GRAPH_SOURCES
    registry = registry_lookup(registry_path)
    node_vocabulary = node_vocabulary_lookup(node_vocabulary_path)
    access_lookups = paper_library_lookups()
    papers: dict[str, dict] = {}
    entities: dict[str, dict] = {}
    claims: list[dict] = []
    evidence_edges: list[dict] = []
    audits: list[dict] = []
    source_counts: dict[str, int] = {}

    for source_name, cfg in graph_sources.items():
        rows = rows_for_source(cfg)
        source_counts[source_name] = len(rows)
        source_domain = cfg["domain"]
        source_dataset = cfg["dataset"]
        default_evidence_type = cfg["default_evidence_type"]

        for index, row in enumerate(rows):
            domain = normalize(row.get("domain", "")) or normalize(row.get("domain_route", "")) or source_domain
            dataset = normalize(row.get("dataset", "")) or domain or source_dataset
            access_lookup = access_lookups.get(dataset, {})
            row = enrich_open_access_metadata(row, access_lookup)
            if should_skip_evidence_row(domain, row):
                continue

            paper_id = paper_id_for(row)
            papers.setdefault(paper_id, paper_row(row, paper_id))

            compound_label = compound_label_for(row)
            compound_id = entity_id_for("compound", compound_label)
            compound_registry = registry.get(("compound", compound_label))
            entities.setdefault(
                compound_id,
                entity_row(compound_id, "compound", "compound", compound_label, "compound", compound_registry),
            )

            legacy_entity_label = normalize(row.get("target" if domain == "mechanistic" else "disorder", ""))
            legacy_entity_type = "mechanistic_entity" if domain == "mechanistic" else "clinical_entity"
            legacy_registry_item = registry.get((legacy_entity_type, legacy_entity_label))
            entity_kind = entity_kind_for(row, domain, legacy_registry_item)
            entity_label = entity_label_for(row, domain, entity_kind)
            entity_label, vocabulary_item = canonicalize_node_label(entity_kind, entity_label, node_vocabulary)
            entity_type = entity_type_for_kind(entity_kind, domain)
            registry_item = registry.get((entity_type, entity_label)) or vocabulary_item
            entity_id = entity_id_for(entity_type, entity_label)
            entities.setdefault(entity_id, entity_row(entity_id, entity_type, domain, entity_label, entity_kind, registry_item))
            table_row = dict(row)
            table_row["compound"] = compound_label
            table_row["graph_entity_label"] = entity_label
            table_row["kg_entity_kind_override"] = entity_kind

            evidence_type = evidence_type_for(row, default_evidence_type)
            claim_id = stable_id(
                "claim",
                source_name,
                index,
                row.get("study_doi", ""),
                compound_label,
                entity_label,
                table_row.get("evidence_locator", ""),
                table_row.get("supporting_quote", ""),
            )
            evidence_id = stable_id("evidence", claim_id, evidence_type, entity_kind)
            claims.append(claim_row(table_row, source_name, domain, dataset, evidence_type, claim_id, paper_id))
            evidence_edges.append(
                evidence_edge_row(
                    table_row,
                    source_name,
                    domain,
                    dataset,
                    evidence_type,
                    entity_kind,
                    claim_id,
                    evidence_id,
                    paper_id,
                    compound_id,
                    entity_id,
                )
            )

        if not cfg.get("skip_audit", False):
            audit_path = Path(cfg.get("audit_path", ""))
            for row in load_json_array(audit_path):
                audits.append(audit_row(row, source_name, domain, dataset))

    tables = {
        "papers": dataframe(list(papers.values())),
        "entities": dataframe(list(entities.values())),
        "claims": dataframe(claims),
        "evidence_edges": dataframe(evidence_edges),
        "normalization_audit": dataframe(audits),
    }

    if out_dir.exists():
        for table_name in tables:
            existing = out_dir / f"{table_name}.parquet"
            if existing.exists():
                existing.unlink()
    out_dir.mkdir(parents=True, exist_ok=True)
    for table_name, df in tables.items():
        write_parquet(df, out_dir / f"{table_name}.parquet")

    duckdb_status = write_duckdb_database(out_dir, tables.keys()) if write_duckdb else {"status": "skipped"}

    edge_df = tables["evidence_edges"]
    entity_df = tables["entities"]
    manifest = {
        "kg_table_version": KG_TABLE_VERSION,
        "generated_at": now_utc(),
        "out_dir": str(out_dir),
        "registry_path": str(registry_path),
        "node_vocabulary_path": str(node_vocabulary_path),
        "source_counts": source_counts,
        "tables": {
            table_name: {
                "path": str(out_dir / f"{table_name}.parquet"),
                "rows": int(len(df)),
                "columns": list(df.columns),
            }
            for table_name, df in tables.items()
        },
        "edge_counts_by_domain_kind_evidence": edge_counts(edge_df),
        "entity_counts_by_type_kind": entity_counts(entity_df),
        "duckdb": duckdb_status,
    }
    write_json(out_dir / "manifest.json", manifest)
    return manifest


def edge_counts(df: pd.DataFrame) -> list[dict]:
    if df.empty:
        return []
    counts = (
        df.groupby(["domain", "entity_kind", "evidence_type"], dropna=False)
        .size()
        .reset_index(name="count")
        .sort_values(["domain", "entity_kind", "evidence_type"])
    )
    return counts.to_dict(orient="records")


def entity_counts(df: pd.DataFrame) -> list[dict]:
    if df.empty:
        return []
    counts = (
        df.groupby(["entity_type", "entity_kind"], dropna=False)
        .size()
        .reset_index(name="count")
        .sort_values(["entity_type", "entity_kind"])
    )
    return counts.to_dict(orient="records")


def write_duckdb_database(out_dir: Path, table_names: Iterable[str]) -> dict:
    try:
        import duckdb
    except ModuleNotFoundError:
        return {
            "status": "missing_dependency",
            "message": "Install duckdb to materialize kg.duckdb; Parquet tables were written.",
        }

    db_path = out_dir / "kg.duckdb"
    if db_path.exists():
        db_path.unlink()
    con = duckdb.connect(str(db_path))
    try:
        for table_name in table_names:
            parquet_path = (out_dir / f"{table_name}.parquet").as_posix()
            con.execute(f"CREATE TABLE {table_name} AS SELECT * FROM read_parquet(?)", [parquet_path])
        con.execute("CHECKPOINT")
    finally:
        con.close()
    return {"status": "ok", "path": str(db_path)}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY_PATH)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--skip-duckdb", action="store_true", help="Only write Parquet tables and manifest.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manifest = build_tables(registry_path=args.registry, out_dir=args.out_dir, write_duckdb=not args.skip_duckdb)
    print(f"wrote KG tables to {args.out_dir}")
    for table_name, info in manifest["tables"].items():
        print(f"{table_name}: {info['rows']} rows -> {info['path']}")
    print(f"duckdb: {manifest['duckdb']['status']}")


if __name__ == "__main__":
    main()
