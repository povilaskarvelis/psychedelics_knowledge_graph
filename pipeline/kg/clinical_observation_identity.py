"""Retain a saved clinical measurement without inventing a condition identity.

Clinical extraction separates the population/indication from the measured
endpoint. A failed condition lookup must not erase the complete observation.
Only primary source contracts qualify; review coverage is a different contract.
"""
from __future__ import annotations

MISSING = {"", "none", "null", "n/a", "na", "unknown", "uncertain", "not_reported",
           "not reported", "not_applicable", "not applicable", "unspecified"}
REQUIRED_FIELDS = ("clinical_endpoint", "outcome_measure", "study_design", "finding_summary")
HELD_CONDITION_STATUSES = {"entity_unmapped", "entity_combo_not_graphable",
                           "condition_broad_placeholder_not_graphable", "population_not_graphable"}


def text(value: object) -> str:
    return " ".join(str(value or "").split())


def explicit_clinical_observation(row: dict) -> bool:
    return (
        (row.get("domain") or row.get("domain_route")) == "clinical_outcome"
        and row.get("source_type") == "primary"
        and row.get("source_item_type") == "primary_item"
        and row.get("extraction_schema_version") == "primary_clinical_outcome_v1"
        and not text(row.get("endpoint_label_source"))
        and all(text(row.get(k)).casefold() not in MISSING for k in REQUIRED_FIELDS)
    )


def clinical_observation_signature(row: dict) -> tuple[str, ...]:
    # Include native condition and outcome fields: a split or inferred row
    # cannot borrow eligibility from the original complete observation.
    return tuple(text(row.get(k)) for k in (
        "task_id", "source_item_index", "study_doi", "source_item_type",
        "condition_or_population", "condition_or_indication", "population_or_subgroup",
        *REQUIRED_FIELDS,
    ))


def clinical_observation_recovery(row: dict) -> dict | None:
    if not explicit_clinical_observation(row):
        return None
    return {
        "label": text(row["clinical_endpoint"]),
        "kind": "reported_measurement",
        "match_type": "explicit_primary_clinical_measurement_detail_only",
        "reason": "clinical_measurement_without_resolved_condition",
    }
