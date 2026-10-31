"""Retain native public-health observations independently of drug identity.

A predictor, policy comparison, or sampled drug panel is a valid observation
subject. Same-finding drug mentions establish scope only; they never establish
individual drug effects or justify component projections of pooled estimates.
"""
from __future__ import annotations

from pathlib import Path
import re

from pipeline.kg.real_world_subjects import (
    DEFAULT_REGISTRY, _identities, IDENTITY_MODIFIER_RE, BACKGROUND_ONLY_RE,
    EXPLICIT_DRUG_FIELDS,
)

MISSING = {"", "none", "null", "n/a", "na", "unknown", "uncertain", "not_reported",
           "not reported", "not_applicable", "not applicable", "unspecified"}
REQUIRED_FIELDS = ("exposure_or_policy", "public_health_measure", "public_health_topic_category",
                   "study_design", "finding_summary")
DETAIL_REASON = "complete_public_health_observation_without_atomic_subject"
MATCH_TYPE = "explicit_primary_public_health_observation_detail_only"
SCOPE_CAVEAT_RE = re.compile(
    r"\b(?:do(?:es)? not (?:establish|imply|prove)|cannot (?:establish|infer|attribute)|"
    r"no (?:psychedelic|drug)[- ]specific (?:result|effect|finding)|not specifically for (?:psychedelic|hallucinogen)s?)\b", re.I,
)


def text(value: object) -> str:
    return " ".join(str(value or "").split())


def explicit_real_world_observation(row: dict) -> bool:
    return (
        (row.get("domain") or row.get("domain_route")) == "real_world_public_health"
        and row.get("source_type") == "primary"
        and row.get("source_item_type") == "primary_item"
        and row.get("extraction_schema_version") == "primary_real_world_public_health_v1"
        and all(text(row.get(k)).casefold() not in MISSING for k in REQUIRED_FIELDS)
        and not text(row.get("entity_split_source_label"))
    )


def real_world_observation_signature(row: dict) -> tuple[str, ...]:
    # Normalization-inferred or split fields must not borrow source eligibility.
    return tuple(text(row.get(k)) for k in (
        "task_id", "source_item_id", "source_item_index", "study_doi", "source_item_type",
        *REQUIRED_FIELDS,
    ))


def real_world_observation_recovery(row: dict, registry_path: Path = DEFAULT_REGISTRY) -> dict | None:
    if not explicit_real_world_observation(row):
        return None
    exposure = text(row["exposure_or_policy"])
    # A legacy explicit chemical subject is a different contract. This fallback
    # only handles native exposure/predictor text copied into the compound slot.
    if any(text(row.get(k)).casefold() not in MISSING
           and text(row[k]).casefold() != exposure.casefold() for k in EXPLICIT_DRUG_FIELDS):
        return None
    if text(row.get("graph_subject_label")).casefold() not in {"", exposure.casefold()}:
        return None
    location = text(row.get("evidence_location"))
    if BACKGROUND_ONLY_RE.search(location) and not re.search(r"\b(?:results|abstract|table|figure)\b", location, re.I):
        return None
    native_scope_text = " ".join(text(row[k]) for k in ("public_health_measure", "finding_summary"))
    # A caution that these data cannot establish a psychedelic effect is not
    # evidence that the measured observation included psychedelic exposure.
    # Keep actual negative findings (e.g. MDMA was tested but not detected).
    finding_scope = " ".join(part for part in re.split(r"(?<=[.!?;])\s+", text(row["finding_summary"]))
                             if not SCOPE_CAVEAT_RE.search(part))
    # A named reference model is not a measured substance in this observation.
    finding_scope = re.sub(r"\b(?:than|compared (?:with|to)) (?:the )?[\w-]+ (?:model|classifier|assay|method)\b",
                           "", finding_scope, flags=re.I)
    scope_text = text(row["public_health_measure"]) + " " + finding_scope
    if IDENTITY_MODIFIER_RE.search(exposure + " " + native_scope_text):
        # Chemical derivatives, metabolites and receptor mentions need separate
        # identity handling; a parent name is insufficient to establish scope.
        return None
    # Reuse the alias matcher's longest-span, negation and registry-scope rules.
    # Titles, populations, other findings and broad inferred topics are excluded.
    scope_labels = sorted({hit["label"] for hit in _identities(scope_text, registry_path) if hit["allowed"]})
    if not scope_labels:
        return None
    return {"label": exposure, "kind": "exposure_context", "match_type": MATCH_TYPE,
            "reason": DETAIL_REASON, "scope_labels": scope_labels}
