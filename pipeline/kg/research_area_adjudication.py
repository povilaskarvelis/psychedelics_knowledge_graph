"""Persist and apply conservative adjudications for research-area review flags.

The routing pass remains deterministic.  This module records a decision for
every row in the review queue, applies only high-confidence graph holds, and
keeps unresolved rows visible for a later human decision.  It deliberately
does not call an extraction or classification model.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


VERSION = "research_area_adjudication_v1"
ADJUDICATION_FIELDS = (
    "research_area_adjudication_version",
    "research_area_adjudication_id",
    "research_area_adjudication_status",
    "research_area_adjudication_action",
    "research_area_adjudication_rationale",
    "research_area_adjudication_reviewed_at",
    "research_area_adjudication_reviewer",
)


def _text(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip()


def _matches(pattern: str, value: str) -> bool:
    return bool(re.search(pattern, value or "", re.I))


def _reasons(row) -> set[str]:
    raw = _text(row.get("research_area_review_reasons_json", "[]"))
    try:
        parsed = json.loads(raw or "[]")
    except json.JSONDecodeError:
        parsed = []
    return {str(value) for value in parsed if value}


def _key(row) -> tuple[str, str, str]:
    return (
        _text(row.get("study_doi")),
        _text(row.get("compound")),
        _text(row.get("support")),
    )


def _fingerprint(row) -> str:
    existing = _text(row.get("research_area_evidence_fingerprint"))
    if existing:
        return existing
    payload = {
        key: _text(row.get(key))
        for key in (
            "study_doi",
            "compound",
            "support",
            "supporting_quote",
            "evidence_location",
            "evidence_locator",
        )
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def _audit_index(audit_df: pd.DataFrame | None) -> dict[tuple[str, str, str], list[dict]]:
    index: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    if audit_df is None or audit_df.empty:
        return index
    for row in audit_df.fillna("").to_dict("records"):
        index[_key(row)].append(row)
    return index


def _high_confidence_action(row: dict, audit_rows: list[dict]) -> tuple[str, str, dict | None] | None:
    """Use the saved semantic audit only as a precise override.

    If deterministic routing already produced a replacement safety/cognition
    projection, keep that replacement.  If the old condition/safety projection
    is still present, hold its graph edge rather than inventing a new node.
    """
    if not audit_rows:
        return None
    current_kind = _text(row.get("kg_entity_kind_override"))
    current_label = _text(row.get("entity_label"))
    # Prefer an exact old projection match when duplicate saved audit rows
    # share the same source statement but name different condition anchors.
    for audit in audit_rows:
        old_kind = _text(audit.get("kg_entity_kind_override"))
        old_label = _text(audit.get("entity_label"))
        if current_kind == old_kind and current_label.casefold() == old_label.casefold():
            return (
                "corrected",
                "hold_legacy_high_confidence_projection",
                audit,
            )
    audit = audit_rows[0]
    return (
        "corrected",
        "route_to_existing_replacement_projection",
        audit,
    )
    return None


def _decide(row: dict, audit_rows: list[dict]) -> tuple[str, str, str, dict | None]:
    record_type = _text(row.get("record_type"))
    if record_type != "finding":
        return (
            "unresolved",
            "normalization_record_requires_source_review",
            "This is a rejected or incomplete normalization record; the correct graph subject cannot be inferred safely from the routing row alone.",
            None,
        )

    high_confidence = _high_confidence_action(row, audit_rows)
    if high_confidence is not None:
        status, action, audit = high_confidence
        return (
            status,
            action,
            _text(audit.get("rationale"))
            or "The saved semantic audit identified a high-confidence research-area mismatch.",
            audit,
        )

    reasons = _reasons(row)
    kind = _text(row.get("kg_entity_kind_override"))
    label = _text(row.get("entity_label"))
    compound = _text(row.get("compound")).casefold()
    support = _text(row.get("support"))

    treatment_language = _matches(
        r"\b(?:treat\w*|therap\w*|therapeutic|improv\w*|reduc\w*|decreas\w*|ameliorat\w*|remiss\w*|resolv\w*|disappear\w*|attenuat\w*|alleviat\w*|response|efficacy|benefit|promis\w*|protect\w*|absent|antidepress\w*|anti[- ]?suicid)\b",
        support,
    )
    exposure_harm_language = _matches(
        r"\b(?:develop\w*|induc\w*|precipitat\w*|exacerbat\w*|worsen\w*|aggravat\w*|risk|abuse|recreational|chronic use|exposure|following use|after use|associated with|caus\w*|psychos\w*|psychotic|mania|manic|catatoni|parkinson|cystitis|uropathy|hospitali[sz]|fatal|suicid\w*)\b",
        support,
    )

    if _matches(r"retract\w*", support):
        return (
            "corrected",
            "hold_retracted_claim",
            "The statement describes a retracted claim or an experimental substitution error, so it should remain paper detail rather than a graph projection.",
            None,
        )

    if kind in {"condition_indication", "symptom_problem"}:
        if (
            compound in {"ketamine", "s-ketamine"}
            and _matches(r"ketamine[- ]?(?:associated|induced|related)?\s*(?:uropathy|cystitis)", label)
            and _matches(r"\b(?:abuse|recreational|chronic|induc\w*|associated|caus\w*|damage|symptom)", support)
        ):
            return (
                "corrected",
                "hold_exposure_consequence_projection",
                "The finding describes ketamine-related urinary harm or its exposure context; it is not evidence that ketamine treats the condition.",
                None,
            )
        if "disease_model_versus_indication" in reasons:
            return (
                "corrected",
                "hold_disease_model_projection",
                "The condition label is being used as a disease model or comparison target, not as the treated indication.",
                None,
            )
        if "possible_exposure_related_harm" in reasons and exposure_harm_language and not treatment_language:
            return (
                "corrected",
                "hold_exposure_harm_projection",
                "The finding describes harm or risk following exposure, so the condition should not be exported as a treatment indication.",
                None,
            )
        if "observational_exposure_versus_treatment" in reasons and _matches(
            r"\b(?:users|consumers|abusers|recreational|use|exposure)\b", support
        ) and not treatment_language:
            return (
                "corrected",
                "hold_observational_exposure_projection",
                "The finding is an observational exposure or use association rather than a treatment outcome.",
                None,
            )
        if "context_policy_or_preferences_versus_outcome" in reasons and _matches(
            r"cost.effectiv|willing|acceptab|barrier|preference|policy|model(?:ed|ing)?|scheduling|recommendation",
            support,
        ) and not _matches(r"patient.*(?:treated|received)|treatment.*(?:improv|reduc)", support):
            return (
                "corrected",
                "hold_context_or_policy_projection",
                "The finding concerns policy, health economics, preferences, acceptability, or treatment context rather than the condition outcome itself.",
                None,
            )
        if "extracted_role_disagrees_with_clinical_projection" in reasons and _matches(
            r"\b(?:users|population|participants|healthy|model|compar\w*)\b", support
        ) and not treatment_language:
            return (
                "corrected",
                "hold_non_treatment_role_projection",
                "The extracted relationship describes a population, comparator, or model role rather than a treatment indication.",
                None,
            )

    if kind == "safety_adverse_event" and (
        "therapeutic_response_in_safety" in reasons
        or "same_statement_in_clinical_and_safety" in reasons
    ):
        if _text(row.get("entity_label")).casefold() in {
            "psychosis risk",
            "suicidality",
            "anxiety/panic",
        } and treatment_language and not exposure_harm_language:
            return (
                "corrected",
                "hold_therapeutic_outcome_safety_projection",
                "The saved statement reports therapeutic improvement, not a safety endpoint for this safety label.",
                None,
            )

    if kind in {"cognitive_behavioral_construct", "subjective_experience_construct"} and "serious_psychosis_in_transient_effect_view" in reasons:
        return (
            "corrected",
            "hold_serious_psychosis_transient_effect_projection",
            "A psychotic episode requiring hospitalization is a serious safety outcome and should not remain only under a transient subjective-effect projection.",
            None,
        )

    return (
        "unresolved",
        "manual_semantic_review_required",
        "The routing flag is meaningful, but the available structured fields do not establish a safe automatic correction.",
        None,
    )


def adjudicate_queue(
    queue_df: pd.DataFrame,
    *,
    audit_df: pd.DataFrame | None = None,
    reviewed_at: str | None = None,
    reviewer: str = "deterministic_adjudication_v1",
) -> pd.DataFrame:
    """Return one persistent adjudication for every queued record."""
    reviewed_at = reviewed_at or datetime.now(timezone.utc).isoformat()
    audit_index = _audit_index(audit_df)
    records: list[dict] = []
    for queue_ordinal, row in enumerate(queue_df.fillna("").to_dict("records")):
        status, action, rationale, audit = _decide(row, audit_index.get(_key(row), []))
        fingerprint = _fingerprint(row)
        # The queue can contain repeated projections of the same statement and
        # repeated normalization attempts.  Keep IDs unique while retaining
        # the evidence fingerprint as the stable source anchor.
        adjudication_id = f"research-area-adjudication:{fingerprint[:20]}:{queue_ordinal:05d}"
        record = {
            "adjudication_id": adjudication_id,
            "adjudication_key": _text(row.get("finding_id")) or fingerprint,
            "queue_ordinal": queue_ordinal,
            "finding_id": _text(row.get("finding_id")),
            "claim_id": _text(row.get("claim_id")),
            "record_type": _text(row.get("record_type")),
            "study_doi": _text(row.get("study_doi")),
            "compound": _text(row.get("compound")),
            "domain": _text(row.get("domain")),
            "entity_label": _text(row.get("entity_label")),
            "kg_entity_kind_override": _text(row.get("kg_entity_kind_override")),
            "graph_admission_status_before": _text(row.get("graph_admission_status")),
            "support": _text(row.get("support")),
            "research_area_evidence_fingerprint": fingerprint,
            "research_area_review_reasons_json": _text(row.get("research_area_review_reasons_json")) or "[]",
            "adjudication_version": VERSION,
            "adjudication_status": status,
            "adjudication_action": action,
            "adjudication_rationale": rationale,
            "reviewed_at": reviewed_at,
            "reviewer": reviewer,
            "legacy_audit_category": _text(audit.get("category")) if audit else "",
            "legacy_audit_finding_id": _text(audit.get("finding_id")) if audit else "",
            "legacy_audit_proposed_destination": _text(audit.get("proposed_destination")) if audit else "",
        }
        records.append(record)
    return pd.DataFrame(records)


def apply_adjudications(
    findings_df: pd.DataFrame,
    edges_df: pd.DataFrame,
    adjudications_df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Apply only corrected ``hold_*`` actions to materialized graph tables."""
    findings = findings_df.copy()
    edges = edges_df.copy()
    for field in ADJUDICATION_FIELDS:
        if field not in findings.columns:
            findings[field] = ""
    if "finding_id" not in findings.columns:
        return findings, edges, {"status": "no_finding_id", "corrected_rows": 0, "held_edges": 0}

    by_id = {
        _text(row.get("finding_id")): row
        for row in adjudications_df.fillna("").to_dict("records")
        if _text(row.get("finding_id"))
    }
    changed_ids: set[str] = set()
    status_counts: Counter[str] = Counter()
    action_counts: Counter[str] = Counter()
    for index, row in findings.iterrows():
        finding_id = _text(row.get("finding_id"))
        adjudication = by_id.get(finding_id)
        if not adjudication:
            continue
        status = _text(adjudication.get("adjudication_status"))
        action = _text(adjudication.get("adjudication_action"))
        findings.at[index, "research_area_adjudication_version"] = VERSION
        findings.at[index, "research_area_adjudication_id"] = _text(adjudication.get("adjudication_id"))
        findings.at[index, "research_area_adjudication_status"] = status
        findings.at[index, "research_area_adjudication_action"] = action
        findings.at[index, "research_area_adjudication_rationale"] = _text(adjudication.get("adjudication_rationale"))
        findings.at[index, "research_area_adjudication_reviewed_at"] = _text(adjudication.get("reviewed_at"))
        findings.at[index, "research_area_adjudication_reviewer"] = _text(adjudication.get("reviewer"))
        status_counts[status] += 1
        action_counts[action] += 1
        if status == "corrected":
            findings.at[index, "research_area_classification_origin"] = "agent_reviewed"
        if status == "corrected" and action.startswith("hold_"):
            changed_ids.add(finding_id)
            findings.at[index, "graph_admission_status"] = "paper_detail"
            findings.at[index, "graph_admission_reason"] = "research_area_adjudication_hold_graph_edge"

    if "finding_id" in edges.columns and changed_ids:
        before = len(edges)
        edges = edges.loc[~edges["finding_id"].isin(changed_ids)].copy()
        held_edges = before - len(edges)
    else:
        held_edges = 0
    return findings, edges, {
        "status": "ok",
        "adjudicated_finding_rows": int(sum(status_counts.values())),
        "corrected_rows": int(status_counts.get("corrected", 0)),
        "confirmed_current_rows": int(status_counts.get("confirmed_current", 0)),
        "unresolved_rows": int(status_counts.get("unresolved", 0)),
        "held_finding_ids": len(changed_ids),
        "held_edges": int(held_edges),
        "status_counts": dict(status_counts),
        "action_counts": dict(action_counts),
    }
