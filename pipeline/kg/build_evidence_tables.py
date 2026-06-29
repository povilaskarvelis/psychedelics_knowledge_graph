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
import unicodedata
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
DEFAULT_ROUTED_KG_RUN_ROOT = ROOT / "data" / "processed" / "kg_routed_runs"
DEFAULT_REGISTRY_PATH = ROOT / "data" / "curated" / "entity_registry.json"
DEFAULT_NODE_VOCABULARY_PATH = ROOT / "schema" / "kg_node_vocabularies.json"
DEFAULT_PAPER_LIBRARY_PATHS = {
    "disorder": ROOT / "data" / "processed" / "paper_library_disorder.csv",
    "mechanistic": ROOT / "data" / "processed" / "paper_library_mechanistic.csv",
}
KG_TABLE_VERSION = "0.1"

ROUTED_GRAPH_SOURCES = {
    "routed_extractions": {
        "path": DEFAULT_EXTRACTION_DIR / "routed_evidence_rows.json",
        "domain": "routed",
        "dataset": "routed",
        "default_evidence_type": "primary_evidence",
        "skip_audit": True,
    },
}

CURRENT_GRAPH_SOURCES = {
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
COMBINED_GRAPH_SOURCES = {**CURRENT_GRAPH_SOURCES, **ROUTED_GRAPH_SOURCES}
GRAPH_SOURCE_PRESETS = {
    "current": CURRENT_GRAPH_SOURCES,
    "routed": ROUTED_GRAPH_SOURCES,
    "combined": COMBINED_GRAPH_SOURCES,
}
# Backwards-compatible module name. The default remains the current KG sources,
# so routed extraction outputs cannot be mixed in by accident.
GRAPH_SOURCES = CURRENT_GRAPH_SOURCES

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
REGISTRY_BACKED_ENTITY_KINDS = {
    "condition_indication",
    "symptom_problem",
    "target",
    "pathway_process",
    "biomarker_readout",
    "system_family",
}
VOCABULARY_BACKED_ENTITY_KINDS = {
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
GREEK_FOLD_REPLACEMENTS = {
    "α": "alpha",
    "Α": "Alpha",
    "β": "beta",
    "Β": "Beta",
    "γ": "gamma",
    "Γ": "Gamma",
    "δ": "delta",
    "Δ": "Delta",
    "κ": "kappa",
    "Κ": "Kappa",
    "μ": "mu",
    "µ": "mu",
    "Μ": "Mu",
}
CLASS_LEVEL_COMPOUND_RE = re.compile(
    r"\b("
    r"classic(?:al)?\s+psychedelics?|"
    r"serotonergic\s+psychedelics?|"
    r"psychedelic(?:[- ]assisted)?\s+(?:medicines?|drugs?|substances?|compounds?|therap(?:y|ies))|"
    r"psychedelics?|"
    r"hallucinogenic\s+drugs?|"
    r"hallucinogens?|"
    r"arylcyclohexylamines?|"
    r"synthetic\s+cathinones?|"
    r"iboga\s+alkaloids?|"
    r"nbome\s+drugs?|"
    r"5[-\s]*ht2a?r?\s+agonists?"
    r")\b",
    re.IGNORECASE,
)
REFERENCE_CONTROL_COMPOUND_KEYS = {
    "5 ht",
    "5 hydroxytryptamine",
    "5 hydroxytryptophan",
    "8 oh dpat",
    "cp 93129",
    "clozapine",
    "d serine",
    "glycine",
    "gr 127935",
    "ifenprodil",
    "ketanserin",
    "m100907",
    "memantine",
    "methysergide",
    "mk 801",
    "nmda",
    "pcp",
    "phencyclidine",
    "phencyclidine pcp",
    "pnu 142633",
    "ritanserin",
    "sb 216641",
    "sb271046",
    "serotonin",
    "way100635",
}


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def default_run_id(prefix: str = "routed") -> str:
    return f"{prefix}_{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"


def safe_run_id(value: object) -> str:
    text = normalize(value)
    text = re.sub(r"[^A-Za-z0-9._-]+", "_", text).strip("._-")
    return text


def routed_evidence_rows_path_for_run(run_id: str) -> Path:
    return DEFAULT_EXTRACTION_DIR / "routed_runs" / safe_run_id(run_id) / "routed_evidence_rows.json"


def graph_sources_for_preset(source_preset: str, run_id: str = "") -> dict[str, dict]:
    try:
        sources = GRAPH_SOURCE_PRESETS[source_preset]
    except KeyError as exc:
        choices = ", ".join(sorted(GRAPH_SOURCE_PRESETS))
        raise ValueError(f"Unknown source preset {source_preset!r}; expected one of: {choices}") from exc
    out = {name: dict(cfg) for name, cfg in sources.items()}
    if safe_run_id(run_id) and "routed_extractions" in out:
        out["routed_extractions"]["path"] = routed_evidence_rows_path_for_run(run_id)
    return out


def resolve_kg_output_dir(
    *,
    source_preset: str,
    out_dir: Path | None,
    run_id: str,
) -> tuple[Path, str]:
    resolved_run_id = safe_run_id(run_id)
    if out_dir is not None:
        return out_dir, resolved_run_id
    if source_preset != "current":
        if not resolved_run_id:
            resolved_run_id = default_run_id(source_preset)
        return DEFAULT_ROUTED_KG_RUN_ROOT / resolved_run_id, resolved_run_id
    return DEFAULT_OUT_DIR, resolved_run_id


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


def ascii_fold(value: object) -> str:
    text = normalize(value)
    text = "".join(GREEK_FOLD_REPLACEMENTS.get(char, char) for char in text)
    text = unicodedata.normalize("NFKD", text)
    return text.encode("ascii", "ignore").decode("ascii")


def label_key(value: object) -> str:
    text = ascii_fold(value).casefold()
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def compact_key(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", label_key(value))


def target_variants(label: str) -> list[str]:
    text = normalize(label)
    variants = []
    if re.fullmatch(r"5-HT\d[A-Z]?", text, flags=re.IGNORECASE):
        variants.append(f"{text} receptor")
    match = re.match(r"^(.+?)\s*\((.+?)\)$", text)
    if match:
        variants.extend([match.group(1), match.group(2), f"{match.group(1)} {match.group(2)}"])
    return variants


def entity_key_variants(value: object, entity_type: str = "") -> list[tuple[str, str]]:
    text = normalize(value)
    if not text:
        return []
    variants: list[tuple[str, str]] = [(text, "label")]
    no_parenthetical = re.sub(r"\([^)]*\)", " ", text)
    if normalize(no_parenthetical) and label_key(no_parenthetical) != label_key(text):
        variants.append((no_parenthetical, "without_parenthetical"))
    for inside in re.findall(r"\(([^)]*)\)", text):
        if normalize(inside):
            variants.append((inside, "parenthetical"))
    if entity_type == "mechanistic_entity":
        variants.extend((variant, "target_variant") for variant in target_variants(text))

    out: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for variant, variant_type in variants:
        for candidate_key, key_type in (
            (label_key(variant), variant_type),
            (compact_key(variant), f"{variant_type}_compact"),
        ):
            if candidate_key and (candidate_key, key_type) not in seen:
                seen.add((candidate_key, key_type))
                out.append((candidate_key, key_type))
    return out


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
                for key, _variant_type in entity_key_variants(candidate):
                    out[(normalized_kind, key)] = item
    return out


def canonicalize_node_label(entity_kind: str, label: str, node_vocabulary: dict[tuple[str, str], dict]) -> tuple[str, dict | None]:
    item = None
    for key, _variant_type in entity_key_variants(label):
        item = node_vocabulary.get((entity_kind, key))
        if item:
            break
    if not item:
        return label, None
    canonical = normalize(item.get("label", "")) or label
    return canonical, item


def compound_key_variants(value: object) -> list[tuple[str, str]]:
    text = normalize(value)
    if not text:
        return []
    variants: list[tuple[str, str]] = [(text, "label")]
    no_parenthetical = re.sub(r"\([^)]*\)", " ", text)
    if normalize(no_parenthetical) and label_key(no_parenthetical) != label_key(text):
        variants.append((no_parenthetical, "without_parenthetical"))
    for inside in re.findall(r"\(([^)]*)\)", text):
        if normalize(inside):
            variants.append((inside, "parenthetical"))

    stripped = text
    stripped = re.sub(r"\b(?:intravenous|intranasal|sublingual|oral|subcutaneous|nasal spray|infusion)\b", " ", stripped, flags=re.IGNORECASE)
    stripped = re.sub(r"\b(?:iv|i\.v\.|in|s\.c\.|sc)\b", " ", stripped, flags=re.IGNORECASE)
    stripped = re.sub(r"\b(?:hydrochloride|hcl)\b", " ", stripped, flags=re.IGNORECASE)
    stripped = re.sub(r"\buse(?:rs?)?\b", " ", stripped, flags=re.IGNORECASE)
    stripped = re.sub(r"\b(?:lifetime|naturalistic|microdosing|weekly|synthetic|extracted)\b", " ", stripped, flags=re.IGNORECASE)
    stripped = re.sub(r"\b(?:therapy|treatment|assisted|psychotherapy|psychotherapeutic|support|program)\b", " ", stripped, flags=re.IGNORECASE)
    stripped = re.sub(r"\b(?:mushrooms?|truffles?)\b", " ", stripped, flags=re.IGNORECASE)
    if normalize(stripped) and label_key(stripped) != label_key(text):
        variants.append((stripped, "stripped_context"))

    out: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for variant, variant_type in variants:
        for candidate_key, key_type in (
            (label_key(variant), variant_type),
            (compact_key(variant), f"{variant_type}_compact"),
        ):
            if candidate_key and (candidate_key, key_type) not in seen:
                seen.add((candidate_key, key_type))
                out.append((candidate_key, key_type))
    return out


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
            labels = [label]
            labels.extend(normalize(alias) for alias in item.get("aliases", []) if normalize(alias))
            for candidate in labels:
                if entity_type == "compound":
                    variants = compound_key_variants(candidate)
                else:
                    variants = entity_key_variants(candidate, entity_type)
                for key, _variant_type in variants:
                    out[(entity_type, key)] = item
    return out


def canonicalize_registry_label(
    entity_type: str,
    label: str,
    registry: dict[tuple[str, str], dict],
) -> tuple[str, dict | None]:
    if entity_type == "compound":
        keys = compound_key_variants(label)
    else:
        keys = entity_key_variants(label, entity_type)
    item = None
    for key, _variant_type in keys:
        item = registry.get((entity_type, key))
        if item:
            break
    if not item:
        return label, None
    canonical = normalize(item.get("label", "")) or label
    return canonical, item


def registry_match_type(entity_type: str, label: str, canonical: str, registry: dict[tuple[str, str], dict]) -> str:
    variants = compound_key_variants(label) if entity_type == "compound" else entity_key_variants(label, entity_type)
    for key, variant_type in variants:
        item = registry.get((entity_type, key))
        if item and normalize(item.get("label", "")) == canonical:
            return variant_type
    return ""


def class_level_compound_label(value: object) -> bool:
    return bool(CLASS_LEVEL_COMPOUND_RE.search(ascii_fold(value)))


def reference_control_compound_label(value: object) -> bool:
    key = label_key(value)
    compact = compact_key(value)
    reference_compacts = {compact_key(item) for item in REFERENCE_CONTROL_COMPOUND_KEYS}
    return key in REFERENCE_CONTROL_COMPOUND_KEYS or compact in reference_compacts


def registry_compound_labels_in_text(value: object, registry: dict[tuple[str, str], dict]) -> set[str]:
    text_key = label_key(value)
    if not text_key:
        return set()
    labels: set[str] = set()
    for entity_type, key in registry:
        if entity_type != "compound" or len(key) < 4:
            continue
        if re.search(rf"\b{re.escape(key)}\b", text_key):
            labels.add(normalize(registry[(entity_type, key)].get("label", "")))
    return {label for label in labels if label}


def graphable_compound_match(raw_compound: object, registry: dict[tuple[str, str], dict]) -> dict:
    raw = normalize(raw_compound)
    if not raw:
        return {
            "matched": False,
            "label": "",
            "item": None,
            "status": "compound_missing",
            "match_type": "",
            "notes": "compound field is empty",
        }
    if class_level_compound_label(raw):
        return {
            "matched": False,
            "label": "",
            "item": None,
            "status": "compound_class_not_graphable",
            "match_type": "",
            "notes": "compound is a broad class label; graph compound nodes use specific registered compounds",
        }
    if reference_control_compound_label(raw):
        return {
            "matched": False,
            "label": "",
            "item": None,
            "status": "compound_reference_not_graphable",
            "match_type": "",
            "notes": "compound is a reference/control compound; graph compound nodes focus on in-scope compounds",
        }

    label, item = canonicalize_registry_label("compound", raw, registry)
    if item:
        return {
            "matched": True,
            "label": label,
            "item": item,
            "status": "compound_normalized",
            "match_type": registry_match_type("compound", raw, label, registry),
            "notes": "compound matched local registry",
        }

    matched_labels = registry_compound_labels_in_text(raw, registry)
    if len(matched_labels) > 1:
        return {
            "matched": False,
            "label": "",
            "item": None,
            "status": "compound_combo_not_graphable",
            "match_type": "",
            "notes": "compound is a multi-compound label; graph compound nodes use one registered compound per edge",
        }
    return {
        "matched": False,
        "label": "",
        "item": None,
        "status": "compound_unmapped",
        "match_type": "",
        "notes": f"compound `{raw}` did not match local registry",
    }


def registry_entity_labels_in_text(value: object, entity_type: str, registry: dict[tuple[str, str], dict]) -> set[str]:
    text_key = label_key(value)
    if not text_key:
        return set()
    labels: set[str] = set()
    for candidate_entity_type, key in registry:
        if candidate_entity_type != entity_type or len(key) < 3:
            continue
        if re.search(rf"\b{re.escape(key)}\b", text_key):
            labels.add(normalize(registry[(candidate_entity_type, key)].get("label", "")))
    return {label for label in labels if label}


def node_vocabulary_labels_in_text(value: object, entity_kind: str, node_vocabulary: dict[tuple[str, str], dict]) -> set[str]:
    text_key = label_key(value)
    if not text_key:
        return set()
    labels: set[str] = set()
    for candidate_kind, key in node_vocabulary:
        if candidate_kind != entity_kind or len(key) < 4:
            continue
        if re.search(rf"\b{re.escape(key)}\b", text_key):
            labels.add(normalize(node_vocabulary[(candidate_kind, key)].get("label", "")))
    return {label for label in labels if label}


def registry_kind_for_item(default_kind: str, item: dict | None) -> str:
    status = normalize((item or {}).get("status", "")).casefold()
    if default_kind in {"condition_indication", "symptom_problem"}:
        if default_kind == "symptom_problem":
            return "symptom_problem"
        if "symptom" in status or "generic_symptom" in status:
            return "symptom_problem"
        return "condition_indication"
    if "family" in status or "system" in status:
        return "system_family"
    if "pathway" in status or "process" in status:
        return "pathway_process"
    if "marker" in status or "readout" in status or "ligand" in status or "neurotransmitter" in status:
        return "biomarker_readout"
    return default_kind


def match_registry_entity(
    raw_label: str,
    entity_kind: str,
    registry: dict[tuple[str, str], dict],
) -> dict:
    entity_type = ENTITY_TYPE_BY_KIND.get(entity_kind, "")
    canonical, item = canonicalize_registry_label(entity_type, raw_label, registry)
    if item:
        canonical_kind = registry_kind_for_item(entity_kind, item)
        return {
            "matched": True,
            "label": canonical,
            "kind": canonical_kind,
            "item": item,
            "status": "entity_normalized",
            "match_type": registry_match_type(entity_type, raw_label, canonical, registry),
            "notes": "entity matched local registry",
        }
    matched_labels = registry_entity_labels_in_text(raw_label, entity_type, registry)
    if len(matched_labels) == 1:
        label = next(iter(matched_labels))
        _, item = canonicalize_registry_label(entity_type, label, registry)
        canonical_kind = registry_kind_for_item(entity_kind, item)
        return {
            "matched": True,
            "label": label,
            "kind": canonical_kind,
            "item": item,
            "status": "entity_normalized",
            "match_type": "text_contains_registry_label",
            "notes": "entity text contained one local registry label",
        }
    if len(matched_labels) > 1:
        return {
            "matched": False,
            "label": "",
            "kind": entity_kind,
            "item": None,
            "status": "entity_combo_not_graphable",
            "match_type": "",
            "notes": "entity text contains multiple graph entities; graph rows need one entity per edge",
        }
    return {
        "matched": False,
        "label": "",
        "kind": entity_kind,
        "item": None,
        "status": "entity_unmapped",
        "match_type": "",
        "notes": f"entity `{raw_label}` did not match local registry",
    }


def match_vocabulary_entity(
    raw_label: str,
    entity_kind: str,
    node_vocabulary: dict[tuple[str, str], dict],
) -> dict:
    canonical, item = canonicalize_node_label(entity_kind, raw_label, node_vocabulary)
    if item:
        return {
            "matched": True,
            "label": canonical,
            "kind": entity_kind,
            "item": item,
            "status": "entity_normalized",
            "match_type": "node_vocabulary",
            "notes": "entity matched route-native node vocabulary",
        }
    matched_labels = node_vocabulary_labels_in_text(raw_label, entity_kind, node_vocabulary)
    if len(matched_labels) == 1:
        label = next(iter(matched_labels))
        _, item = canonicalize_node_label(entity_kind, label, node_vocabulary)
        return {
            "matched": True,
            "label": label,
            "kind": entity_kind,
            "item": item,
            "status": "entity_normalized",
            "match_type": "text_contains_node_vocabulary_label",
            "notes": "entity text contained one route-native vocabulary label",
        }
    if len(matched_labels) > 1:
        return {
            "matched": False,
            "label": "",
            "kind": entity_kind,
            "item": None,
            "status": "entity_combo_not_graphable",
            "match_type": "",
            "notes": "entity text contains multiple graph entities; graph rows need one entity per edge",
        }
    return {
        "matched": False,
        "label": "",
        "kind": entity_kind,
        "item": None,
        "status": "entity_unmapped",
        "match_type": "",
        "notes": f"entity `{raw_label}` did not match route-native node vocabulary",
    }


def graphable_entity_match(
    row: dict,
    domain: str,
    entity_kind: str,
    raw_label: str,
    registry: dict[tuple[str, str], dict],
    node_vocabulary: dict[tuple[str, str], dict],
) -> dict:
    raw = normalize(raw_label)
    if not raw:
        return {
            "matched": False,
            "label": "",
            "kind": entity_kind,
            "item": None,
            "status": "entity_missing",
            "match_type": "",
            "notes": "entity label is empty",
        }
    if entity_kind == "safety_adverse_event":
        return {
            "matched": True,
            "label": safety_endpoint_label(row),
            "kind": entity_kind,
            "item": None,
            "status": "entity_normalized",
            "match_type": "safety_endpoint_pattern",
            "notes": "safety/adverse-event entity normalized to safety endpoint bucket",
        }
    if entity_kind == "outcome_scale":
        label = title_endpoint_label(raw)
        return {
            "matched": bool(label),
            "label": label,
            "kind": entity_kind,
            "item": None,
            "status": "entity_normalized" if label else "entity_unmapped",
            "match_type": "outcome_scale_label",
            "notes": "outcome scale label normalized" if label else f"entity `{raw}` did not produce an outcome scale label",
        }
    if entity_kind == "compound":
        match = graphable_compound_match(raw, registry)
        return {
            "matched": match["matched"],
            "label": match["label"],
            "kind": entity_kind,
            "item": match["item"],
            "status": "entity_normalized" if match["matched"] else match["status"].replace("compound", "entity"),
            "match_type": match["match_type"],
            "notes": match["notes"],
        }
    if entity_kind in REGISTRY_BACKED_ENTITY_KINDS:
        return match_registry_entity(raw, entity_kind, registry)
    if entity_kind in VOCABULARY_BACKED_ENTITY_KINDS:
        return match_vocabulary_entity(raw, entity_kind, node_vocabulary)
    return {
        "matched": False,
        "label": "",
        "kind": entity_kind,
        "item": None,
        "status": "entity_unmapped",
        "match_type": "",
        "notes": f"entity kind `{entity_kind}` has no normalization rule",
    }


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


def route_native_output(manifest_source_preset: str, graph_sources: dict[str, dict]) -> bool:
    return manifest_source_preset == "routed" or set(graph_sources) == {"routed_extractions"}


def finding_row(
    row: dict,
    source_name: str,
    domain: str,
    dataset: str,
    evidence_type: str,
    finding_id: str,
    paper_id: str,
    *,
    id_field: str,
) -> dict:
    row = normalize_claim_metadata(row, domain)
    entity_kind = entity_kind_for(row, domain)
    entity_label = entity_label_for(row, domain, entity_kind)
    out = {
        id_field: finding_id,
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
    finding_id: str,
    evidence_id: str,
    paper_id: str,
    compound_id: str,
    entity_id: str,
    *,
    id_field: str,
) -> dict:
    entity_label = entity_label_for(row, domain, entity_kind)
    relation_type = relation_type_for(domain, entity_kind, evidence_type)
    return {
        "evidence_id": evidence_id,
        id_field: finding_id,
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
        "compound_original": normalize(row.get("compound_original", "")),
        "compound_match_type": normalize(row.get("compound_match_type", "")),
        "entity_label": entity_label_for(row, domain, entity_kind),
        "canonical_entity": normalize(row.get("canonical_entity", "")),
        "graph_entity_original": normalize(row.get("graph_entity_original", "")),
        "entity_match_type": normalize(row.get("entity_match_type", "")),
        "kg_entity_kind_override": normalize(row.get("kg_entity_kind_override", "")),
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
    source_preset: str = "current",
    run_id: str = "",
    registry_path: Path = DEFAULT_REGISTRY_PATH,
    node_vocabulary_path: Path = DEFAULT_NODE_VOCABULARY_PATH,
    out_dir: Path = DEFAULT_OUT_DIR,
    write_duckdb: bool = True,
) -> dict:
    if graph_sources is None:
        graph_sources = graph_sources_for_preset(source_preset, run_id=run_id)
        manifest_source_preset = source_preset
    else:
        manifest_source_preset = "custom"
    registry = registry_lookup(registry_path)
    node_vocabulary = node_vocabulary_lookup(node_vocabulary_path)
    access_lookups = paper_library_lookups()
    route_native = route_native_output(manifest_source_preset, graph_sources)
    finding_table_name = "findings" if route_native else "claims"
    finding_id_field = "finding_id" if route_native else "claim_id"
    finding_id_prefix = "finding" if route_native else "claim"
    papers: dict[str, dict] = {}
    entities: dict[str, dict] = {}
    findings: list[dict] = []
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

            compound_label_raw = compound_label_for(row)
            compound_match = graphable_compound_match(compound_label_raw, registry)
            if not compound_match["matched"]:
                audit_source_row = dict(row)
                audit_source_row["normalization_status"] = compound_match["status"]
                audit_source_row["normalization_notes"] = compound_match["notes"]
                audit_source_row["compound_original"] = compound_label_raw
                audits.append(audit_row(audit_source_row, source_name, domain, dataset))
                continue

            paper_id = paper_id_for(row)
            papers.setdefault(paper_id, paper_row(row, paper_id))

            compound_label = compound_match["label"]
            compound_registry = compound_match["item"]
            compound_id = entity_id_for("compound", compound_label)
            entities.setdefault(
                compound_id,
                entity_row(compound_id, "compound", "compound", compound_label, "compound", compound_registry),
            )

            legacy_entity_label = normalize(row.get("target" if domain == "mechanistic" else "disorder", ""))
            legacy_entity_type = "mechanistic_entity" if domain == "mechanistic" else "clinical_entity"
            _, legacy_registry_item = canonicalize_registry_label(legacy_entity_type, legacy_entity_label, registry)
            entity_kind = entity_kind_for(row, domain, legacy_registry_item)
            raw_entity_label = entity_label_for(row, domain, entity_kind)
            entity_match = graphable_entity_match(
                row=row,
                domain=domain,
                entity_kind=entity_kind,
                raw_label=raw_entity_label,
                registry=registry,
                node_vocabulary=node_vocabulary,
            )
            if not entity_match["matched"]:
                audit_source_row = dict(row)
                audit_source_row["compound"] = compound_label
                audit_source_row["canonical_compound"] = compound_label
                audit_source_row["compound_original"] = compound_label_raw
                audit_source_row["graph_entity_label"] = raw_entity_label
                audit_source_row["canonical_entity"] = entity_match["label"]
                audit_source_row["kg_entity_kind_override"] = entity_kind
                audit_source_row["normalization_status"] = entity_match["status"]
                audit_source_row["normalization_notes"] = entity_match["notes"]
                audit_source_row["entity_match_type"] = entity_match["match_type"]
                audits.append(audit_row(audit_source_row, source_name, domain, dataset))
                continue

            entity_kind = entity_match["kind"]
            entity_label = entity_match["label"]
            entity_type = entity_type_for_kind(entity_kind, domain)
            registry_item = entity_match["item"]
            entity_id = entity_id_for(entity_type, entity_label)
            entities.setdefault(entity_id, entity_row(entity_id, entity_type, domain, entity_label, entity_kind, registry_item))
            table_row = dict(row)
            table_row["compound_original"] = compound_label_raw
            table_row["compound"] = compound_label
            table_row["canonical_compound"] = compound_label
            table_row["compound_match_type"] = compound_match["match_type"]
            table_row["compound_registry_status"] = normalize((compound_registry or {}).get("status", ""))
            table_row["normalization_status"] = "normalized"
            table_row["normalization_notes"] = f"{compound_match['notes']}; {entity_match['notes']}"
            table_row["graph_entity_original"] = raw_entity_label
            table_row["graph_entity_label"] = entity_label
            table_row["canonical_entity"] = entity_label
            table_row["entity_match_type"] = entity_match["match_type"]
            table_row["entity_registry_status"] = normalize((registry_item or {}).get("status", ""))
            table_row["kg_entity_kind_override"] = entity_kind

            evidence_type = evidence_type_for(row, default_evidence_type)
            finding_id = stable_id(
                finding_id_prefix,
                source_name,
                index,
                row.get("study_doi", ""),
                compound_label,
                entity_label,
                table_row.get("evidence_locator", ""),
                table_row.get("supporting_quote", ""),
            )
            evidence_id = stable_id("evidence", finding_id, evidence_type, entity_kind)
            findings.append(
                finding_row(
                    table_row,
                    source_name,
                    domain,
                    dataset,
                    evidence_type,
                    finding_id,
                    paper_id,
                    id_field=finding_id_field,
                )
            )
            evidence_edges.append(
                evidence_edge_row(
                    table_row,
                    source_name,
                    domain,
                    dataset,
                    evidence_type,
                    entity_kind,
                    finding_id,
                    evidence_id,
                    paper_id,
                    compound_id,
                    entity_id,
                    id_field=finding_id_field,
                )
            )

        if not cfg.get("skip_audit", False):
            audit_path = Path(cfg.get("audit_path", ""))
            for row in load_json_array(audit_path):
                audits.append(audit_row(row, source_name, domain, dataset))

    tables = {
        "papers": dataframe(list(papers.values())),
        "entities": dataframe(list(entities.values())),
        finding_table_name: dataframe(findings),
        "evidence_edges": dataframe(evidence_edges),
        "normalization_audit": dataframe(audits),
    }

    if out_dir.exists():
        for table_name in tables:
            existing = out_dir / f"{table_name}.parquet"
            if existing.exists():
                existing.unlink()
        stale_table = "claims" if route_native else "findings"
        stale_path = out_dir / f"{stale_table}.parquet"
        if stale_path.exists():
            stale_path.unlink()
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
        "source_preset": manifest_source_preset,
        "run_id": safe_run_id(run_id),
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
    skipped_empty_tables: list[str] = []
    try:
        for table_name in table_names:
            parquet_path = (out_dir / f"{table_name}.parquet").as_posix()
            if len(pd.read_parquet(parquet_path).columns) == 0:
                skipped_empty_tables.append(table_name)
                continue
            con.execute(f"CREATE TABLE {table_name} AS SELECT * FROM read_parquet(?)", [parquet_path])
        con.execute("CHECKPOINT")
    finally:
        con.close()
    return {"status": "ok", "path": str(db_path), "skipped_empty_tables": skipped_empty_tables}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY_PATH)
    parser.add_argument(
        "--source-preset",
        choices=sorted(GRAPH_SOURCE_PRESETS),
        default="current",
        help="Evidence source set to materialize. Use routed with --run-id for new routed extraction builds.",
    )
    parser.add_argument(
        "--run-id",
        default="",
        help="Version label for routed KG runs. Used in the default output path for --source-preset routed.",
    )
    parser.add_argument("--out-dir", type=Path, default=None)
    parser.add_argument(
        "--allow-current-overwrite",
        action="store_true",
        help="Allow non-current source presets to write directly to data/processed/kg.",
    )
    parser.add_argument("--skip-duckdb", action="store_true", help="Only write Parquet tables and manifest.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    out_dir, run_id = resolve_kg_output_dir(
        source_preset=args.source_preset,
        out_dir=args.out_dir,
        run_id=args.run_id,
    )
    if (
        args.source_preset != "current"
        and out_dir.resolve() == DEFAULT_OUT_DIR.resolve()
        and not args.allow_current_overwrite
    ):
        raise SystemExit(
            "Refusing to write routed/combined sources directly to data/processed/kg. "
            "Use --run-id for a versioned build, or add --allow-current-overwrite if this is an intentional promotion."
        )
    if (
        args.source_preset != "current"
        and out_dir.resolve() == DEFAULT_OUT_DIR.resolve()
        and not run_id
    ):
        raise SystemExit("Promoting routed/combined sources to data/processed/kg requires --run-id.")
    manifest = build_tables(
        source_preset=args.source_preset,
        run_id=run_id,
        registry_path=args.registry,
        out_dir=out_dir,
        write_duckdb=not args.skip_duckdb,
    )
    print(f"wrote KG tables to {out_dir}")
    print(f"source preset: {manifest['source_preset']}")
    if manifest.get("run_id"):
        print(f"run id: {manifest['run_id']}")
    for table_name, info in manifest["tables"].items():
        print(f"{table_name}: {info['rows']} rows -> {info['path']}")
    print(f"duckdb: {manifest['duckdb']['status']}")


if __name__ == "__main__":
    main()
