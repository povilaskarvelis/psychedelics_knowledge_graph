"""Preserve explicit treatment-context observations without component attribution.

Source descriptions can be longer than display labels and can describe several
parts of a treatment package. Retaining them does not establish an independent
effect of preparation, music, support or another individual component.
"""
from __future__ import annotations

import json

from pipeline.extract.review_source_types import REVIEW_PATH_TYPES

MISSING = {"", "none", "null", "n/a", "na", "unknown", "uncertain", "not_reported",
           "not reported", "not_applicable", "not applicable", "unspecified"}
REVIEW_COVERAGE_TYPES = {"reviewed_relationship", "review_synthesis", "methodological_contribution",
                         "research_landscape", "evidence_gap"}
DETAIL_STATUS = "explicit_intervention_observation_detail_only"


def text(value: object) -> str:
    return " ".join(str(value or "").split())


def present(value: object) -> bool:
    return text(value).casefold() not in MISSING


def anchored_review_context(row: dict) -> bool:
    """Require the v2 review's literal context anchor and native domain label.

    A generic topic, comparator, population, or keyword in the summary cannot
    supply the context identity. This contract retains coverage, not causality.
    """
    if not (
        (row.get("domain") or row.get("domain_route")) == "intervention_context"
        and row.get("source_item_type") == "review_relationship"
        and row.get("source_type") in REVIEW_PATH_TYPES
        and row.get("source_family") == "secondary_literature"
        and row.get("paper_assessment_route") == "secondary_literature"
        and row.get("review_extraction_method") == "paper_centered_one_pass_v2"
        and row.get("review_scope_status") == "in_scope"
        and row.get("entity_role") == "intervention_context"
        and row.get("coverage_type") in REVIEW_COVERAGE_TYPES
        and row.get("coverage_focus") in {"paper_defining", "major_supporting", "secondary_context"}
        and row.get("relationship_projection_basis") in {
            "principal_object", "explicit_named_domain_supported_anchor"}
        and all(present(row.get(k)) for k in (
            "context_component", "finding_summary", "evidence_locator", "source_item_id",
            "relationship_source_group_key", "graph_subject_label"))
        and not text(row.get("entity_split_source_label"))
    ):
        return False
    try:
        domains = json.loads(row.get("relationship_domain_labels_json", "[]"))
        anchors = json.loads(row.get("relationship_anchors_json", "[]"))
    except (TypeError, ValueError):
        return False
    if not isinstance(domains, list) or "intervention_context" not in domains or not isinstance(anchors, list):
        return False
    return any(isinstance(anchor, dict) and anchor.get("role") == "intervention_context"
               and text(anchor.get("label")) == text(row["context_component"])
               for anchor in anchors)


def intervention_source_contract(row: dict) -> str:
    """Identify the saved source contract before normalization can fill fields."""
    if (row.get("domain") or row.get("domain_route")) != "intervention_context":
        return ""
    if not all(present(row.get(k)) for k in ("context_component", "finding_summary")):
        return ""
    if row.get("source_item_type") == "primary_item" and row.get("source_type") == "primary":
        if all(present(row.get(k)) for k in (
            "component_type", "relationship_to_outcome_or_safety", "study_design",
        )):
            return "primary_observation"
    if (row.get("source_item_type") == "review_relationship"
            and row.get("coverage_type") in REVIEW_COVERAGE_TYPES
            and len(text(row.get("context_component"))) > 80
            and present(row.get("evidence_locator"))):
        # Preserve the accepted legacy length-repair path and its match type.
        return "long_review_coverage"
    if anchored_review_context(row):
        return "anchored_review_context"
    return ""


def intervention_source_signature(row: dict) -> tuple[str, ...]:
    return tuple(text(row.get(k)) for k in (
        "task_id", "source_item_id", "source_item_index", "study_doi", "doi", "source_item_type",
        "context_component", "component_type", "relationship_to_outcome_or_safety",
        "study_design", "coverage_type", "finding_summary",
    ))


def intervention_observation_recovery(row: dict, raw_label: str, recognized_parent: str) -> dict | None:
    contract = intervention_source_contract(row)
    literal = text(row.get("context_component"))
    if not contract or literal != text(raw_label):
        return None
    if contract == "long_review_coverage" and not recognized_parent:
        if not anchored_review_context(row):
            return None
        contract = "anchored_review_context"
    return {
        "label": literal,
        "match_type": ("explicit_primary_intervention_observation_detail_only"
                       if contract == "primary_observation" else
                       "anchored_review_context_detail_only" if contract == "anchored_review_context" else
                       "long_review_context_coverage_detail_only"),
        "reason": ("complete_context_observation_not_individual_component_effect"
                   if contract == "primary_observation" else "review_context_coverage_not_observed_component_effect"),
    }
