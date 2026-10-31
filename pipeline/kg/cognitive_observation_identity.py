"""Retain complete cognitive/behavioral observations without changing their unit.

A broad display label is not an absent measurement. Likewise, a comparison or
adjunct regimen led by an in-scope drug must not become its reference treatment.
Both recoveries stay in paper detail and preserve the native source statement.
"""
from __future__ import annotations
from pathlib import Path
import re
from pipeline.kg.real_world_subjects import DEFAULT_REGISTRY, _identities

MISSING = {"", "none", "null", "n/a", "na", "unknown", "uncertain", "not_reported",
           "not reported", "not_applicable", "not applicable", "unspecified"}
REQUIRED_FIELDS = ("compound_or_exposure", "construct_or_behavior", "task_or_measure", "study_design", "finding_summary")
MEASUREMENT_MATCH = "explicit_primary_cognitive_measurement_detail_only"
SUBJECT_MATCH = "explicit_primary_cognitive_context_detail_only"
SUBJECT_REASON = "cognitive_comparison_or_regimen_without_component_attribution"
HELD_SUBJECT_STATUSES = {"compound_unmapped", "compound_graph_scope_not_graphable",
                         "compound_reference_not_graphable", "compound_out_of_scope_nonpsychedelic"}
CONTEXT_RE = re.compile(r"\b(?:versus|vs\.?|compared|with|combined|co[- ]treatment|preceding|following|during|"
                        r"an[ae]*esthe\w*|ECT|electroconvulsive)\b", re.I)
NONADMINISTRATION_RE = re.compile(r"\b(?:not (?:administered|given)|without (?:actual )?(?:drug )?administration|"
                                  r"no (?:actual )?(?:drug )?(?:administration|exposure))\b", re.I)


def text(value: object) -> str:
    return " ".join(str(value or "").split())


def explicit_cognitive_observation(row: dict) -> bool:
    return (
        (row.get("domain") or row.get("domain_route")) == "cognitive_behavioral"
        and row.get("source_type") == "primary"
        and row.get("source_item_type") == "primary_item"
        and row.get("extraction_schema_version") == "primary_cognitive_behavioral_v1"
        and all(text(row.get(k)).casefold() not in MISSING for k in REQUIRED_FIELDS)
        and not text(row.get("entity_split_source_label"))
        and not text(row.get("endpoint_label_source"))
    )


def cognitive_observation_signature(row: dict) -> tuple[str, ...]:
    return tuple(text(row.get(k)) for k in (
        "task_id", "source_item_id", "source_item_index", "study_doi", "source_item_type",
        *REQUIRED_FIELDS, "construct_family", "graph_construct_label",
    ))


def cognitive_measurement_recovery(row: dict) -> dict | None:
    if (not explicit_cognitive_observation(row)
            or text(row.get("construct_family")) not in {"cognition", "behavior"}):
        return None
    # The source explicitly identifies a measured cognitive/behavioral unit.
    # Neural-only rows without this contract need their own domain repair.
    label = text(row.get("graph_construct_label"))
    if label.casefold() in MISSING:
        label = text(row["construct_or_behavior"])
    return {"label": label, "kind": "cognitive_behavioral_construct",
            "match_type": MEASUREMENT_MATCH,
            "reason": "complete_cognitive_measurement_without_controlled_construct"}


def cognitive_context_recovery(row: dict, registry_path: Path = DEFAULT_REGISTRY) -> dict | None:
    if not explicit_cognitive_observation(row):
        return None
    exposure = text(row["compound_or_exposure"])
    if not CONTEXT_RE.search(exposure) or NONADMINISTRATION_RE.search(exposure):
        return None
    if text(row.get("graph_subject_label")) not in {"", exposure}:
        return None
    hits = sorted(_identities(exposure, registry_path), key=lambda h: h["start"])
    # Do not rescue an out-of-scope focal treatment merely because ketamine
    # appears as a disease model, population history, or reference treatment.
    if not hits or not hits[0]["allowed"] or hits[0]["kind"] != "atomic_compound":
        return None
    # Recognizing the first registry hit is insufficient: ECT or an unknown
    # treatment may precede it. Require the actual leading exposure identity,
    # allowing only ordinary administration/dose descriptors before its name.
    prefix = exposure[:hits[0]["start"]].casefold()
    if not re.fullmatch(r"(?:(?:single(?:[- ]dose)?|repeated|chronic|adjunctive|intravenous|"
                        r"intranasal|oral|intramuscular|subcutaneous|racemic|suban[ae]*esthetic|"
                        r"sub[- ]an[ae]*esthetic|low[- ]dose|high[- ]dose)\s+)*", prefix):
        return None
    focal = hits[0]["label"]
    corroborating = {h["label"] for h in _identities(text(row["finding_summary"]), registry_path) if h["allowed"]}
    if focal not in corroborating:
        return None
    return {"label": exposure, "kind": "exposure_context", "match_type": SUBJECT_MATCH,
            "reason": SUBJECT_REASON, "focal_scope_label": focal}
