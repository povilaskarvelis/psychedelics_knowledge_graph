"""Conservative research-area boundaries and review triage, without model calls.

Flags are advisory: they do not certify an error or silently hold a finding.
The original extraction remains untouched. Review provenance is deliberately
separate from extraction's needs_human_review/admission gate.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict

VERSION = "research_area_routing_v1"
FIELDS = (
    "research_area_routing_version",
    "research_area_input_json",
    "research_area_rule_actions_json",
    "research_area_review_status",
    "research_area_review_reasons_json",
    "research_area_classification_origin",
    "research_area_evidence_fingerprint",
)


def text(row, *fields):
    return " ".join(
        dict.fromkeys(str(row.get(k) or "").strip() for k in fields if row.get(k))
    )


def matches(pattern, value):
    return bool(re.search(pattern, value, re.I))


def statement(row):
    # Do not turn a paper title, population or background quote into a result.
    return text(row, "support", "finding_summary")


def action(row, reason):
    actions = json.loads(row.get("research_area_rule_actions_json") or "[]")
    if reason not in actions:
        actions.append(reason)
    row["research_area_rule_actions_json"] = json.dumps(actions)


def initialize(row):
    out = dict(row)
    out.setdefault(
        "research_area_input_json",
        json.dumps(
            {
                k: out.get(k, "")
                for k in (
                    "domain",
                    "domain_route",
                    "kg_entity_kind_override",
                    "graph_entity_label",
                    "entity_role",
                    "condition_or_indication",
                    "population_or_subgroup",
                )
            },
            sort_keys=True,
        ),
    )
    out["research_area_routing_version"] = VERSION
    out.setdefault("research_area_rule_actions_json", "[]")
    out["research_area_classification_origin"] = "deterministic"
    return out


# Scope-aware guards used by the existing psychosis boundary.
def psychosis_anchor_is_context(anchor, result):
    negated = matches(
        r"\b(?:without|no|absence of)\s+(?:any\s+)?psychotic symptoms?\b", anchor
    )
    clinical_response = matches(
        r"remission|(?:reduc\w*|improv\w*|resolv\w*).{0,55}(?:depress|suicid)|(?:depress|suicid).{0,55}(?:improv|resolv|reduc)",
        result,
    )
    population_anchor = matches(
        r"patient|\byear.old\b|\bmale\b|\bfemale\b|depress", anchor
    )
    active_harm = matches(
        r"(?:develop|induc|precipitat|exacerbat)\w*.{0,50}(?:psychos|psychotic)", result
    )
    return not active_harm and (negated or (population_anchor and clinical_response))


def serious_psychosis(result):
    # Negated persistence must not override an explicitly transient model effect.
    positive = re.sub(
        r"\b(?:no|without|not)\s+(?:evidence of |reports? of |reported |any )*"
        r"(?:(?:persistent|prolonged)\s+(?:psychosis|psychotic symptoms?)|"
        r"(?:requiring |require )?hospitali[sz]ation)",
        "",
        result,
        flags=re.I,
    )
    return matches(r"psychos\w*|psychotic", positive) and matches(
        r"(?:requir\w*|led to|resulted in).{0,45}hospital|"
        r"(?<!not )hospitali[sz]ed|(?:persistent|prolonged)\s+(?:psychosis|psychotic)",
        positive,
    )


def apply_boundaries(row):
    """Only change placements with explicit finding-level safety endpoints."""
    out = initialize(row)
    domain = text(out, "domain") or text(out, "domain_route")
    if domain != "clinical_outcome":
        return out
    result = statement(out)
    # An explicit, narrow endpoint takes precedence over a patient's diagnosis.
    endpoint = text(out, "clinical_endpoint", "outcome_measure").strip()
    label = ""
    if matches(
        r"^(?:incidence of |rate of |number of |overall |serious |treatment.emergent )*(?:adverse events?|side effects?)(?: incidence| rate| frequency)?$",
        endpoint,
    ):
        label = (
            "Serious adverse events"
            if matches(r"serious", endpoint)
            else "Adverse events"
        )
    # Treat absence of manic switch as safety, but do not conflate treatment of
    # existing mania, mixed efficacy/safety statements, or generic worsening.
    if matches(
        r"^(?:no (?:affective switch|ketamine.treated patient)|(?:there was|there is) no significant difference.{0,45}manic switch|(?:ketamine|ayahuasca) administration did not (?:induce|result)|manic symptomatology remained stable)",
        result,
    ) and matches(r"mani[ac]|hypomani|affective switch", result):
        label = "Mania/hypomania"
    anchor = text(out, "graph_entity_label", "condition_or_indication")
    if (
        matches(r"parkinson", anchor)
        and matches(
            r"\b(?:use|exposure)\b.{0,90}precipitating factor.{0,100}parkinson", result
        )
        and not matches(r"\b(?:not|no|retract\w*)\b", result)
    ):
        label = "Neurotoxicity/cytotoxicity"
    if label:
        out.update(
            domain="safety_tolerability",
            domain_route="safety_tolerability",
            dataset="safety_tolerability",
            kg_entity_kind_override="safety_adverse_event",
            safety_event_or_measure=label,
            graph_entity_label=label,
            endpoint_label_source="explicit_safety_endpoint_boundary",
        )
        action(out, "explicit_safety_endpoint_routed_from_clinical")
    return out


def review_reasons(row):
    result = statement(row)
    label = text(row, "entity_label") or text(row, "graph_entity_label")
    kind = text(row, "kg_entity_kind_override")
    reasons = []
    if (
        row.get("graph_admission_reason")
        == "psychosis_population_anchor_without_resolved_endpoint"
    ):
        reasons.append("psychosis_population_anchor_without_resolved_endpoint")
    clinical = kind in {"condition_indication", "symptom_problem"}
    if clinical:
        if matches(
            r"adverse|side.effects?|tolerab|tolerated|safety|\bmania\b|manic|hypoman|psychos|psychotic|deliri|treatment.emergent|precipitat|retract|contraindicat|\binduced\b|cystitis|uropathy|fatal|hospitaliz|inpatient psychiatric",
            result,
        ):
            reasons.append("clinical_safety_role_ambiguity")
        if matches(
            r"\b(?:developed|triggered|induced|exacerbat\w*).{0,65}(?:psychos|psychotic|mania|manic|catatoni|parkinson)|(?:use|exposure).{0,65}(?:risk of|onset|suicid)|(?:suicid|psychos|manic).{0,65}(?:after|following)",
            result,
        ):
            reasons.append("possible_exposure_related_harm")
        if matches(r"schizophren", label):
            reasons.append("psychosis_model_risk_or_therapeutic_role")
        if matches(
            r"developed.{0,90}after|delayed.onset|use.{0,80}led to|drug withdrawal",
            result,
        ):
            reasons.append("temporal_harm_versus_therapeutic_outcome")
        if matches(
            r"ketamine.associated uropathy|hallucinogen persisting perception", label
        ):
            reasons.append("disease_may_be_exposure_consequence")
        if matches(
            r"\b(?:surg\w*|enterocystoplasty|hydrodistention|cessation|discontinuation|lamotrigine|haloperidol)\b",
            result,
        ):
            reasons.append("other_intervention_or_withdrawal_role")
        if matches(
            r"\b(?:model\w*|mimic\w*|replicat\w*|reproduc\w*|resemble\w*).{0,90}(?:schizophren|psychos)|(?:schizophren|psychos).{0,90}\bmodel",
            result,
        ):
            reasons.append("disease_model_versus_indication")
        if matches(
            r"\b(?:PANSS|BPRS|CADSS|MMSE|SPECT|connectivity|brain activation|blood flow|glutamate|DMT excretion|working memory|executive function|cognitive function|neurocognitive|amygdala|gamma power|gene products|genes)\b",
            result,
        ):
            reasons.append("measured_endpoint_versus_population")
        if matches(
            r"cost.effectiv|model.{0,140}(?:deaths|avert)|schedul(?:e [IV]+|ing)|reschedul|bibliometric|research.{0,25}(?:trend|cluster|transition)|willingness|willing to|acceptability|acceptable|preferences|prioritized|barriers to|preparation|pretreatment and posttreatment recommendations|expressed support|head.to.head comparisons",
            result,
        ):
            reasons.append("context_policy_or_preferences_versus_outcome")
        if matches(
            r"\b(?:users|consumers|abusers|attempters|abuse|recreational)\b", result
        ) and matches(
            r"compar|associat|incidence|risk|prevalence|reported using|criteria|among|following",
            result,
        ):
            reasons.append("observational_exposure_versus_treatment")
        if text(row, "entity_role") in {
            "population",
            "comparator",
            "subjective_construct",
            "cognitive_or_behavioral_construct",
        }:
            reasons.append("extracted_role_disagrees_with_clinical_projection")
    if kind == "safety_adverse_event" and matches(
        r"remission|antidepressant|improv|ameliorate|depress\w*.{0,45}(?:improv|reduc)|suicid\w*.{0,45}(?:resolv|reduc)",
        result,
    ):
        reasons.append("therapeutic_response_in_safety")
    if kind in {
        "cognitive_behavioral_construct",
        "subjective_experience_construct",
    } and serious_psychosis(result):
        reasons.append("serious_psychosis_in_transient_effect_view")
    if matches(r"\bretract\w*\b", result):
        reasons.append("retracted_claim_context")
    return sorted(set(reasons))


def annotate_findings(findings):
    """Attach advisory review flags after normalization/expansion has finished."""
    groups = defaultdict(list)
    for row in findings:
        # No fuzzy merging: identical statements flag competing projections only.
        key = (
            row.get("study_doi", ""),
            row.get("compound", ""),
            " ".join(statement(row).casefold().split()),
        )
        if key[2]:
            groups[key].append(row)
    competing = set()
    for group in groups.values():
        kinds = {r.get("kg_entity_kind_override") for r in group}
        if "safety_adverse_event" in kinds and kinds & {
            "condition_indication",
            "symptom_problem",
        }:
            competing.update(id(r) for r in group)
    queue = []
    for row in findings:
        reasons = review_reasons(row)
        if id(row) in competing:
            reasons.append("same_statement_in_clinical_and_safety")
        row["research_area_review_reasons_json"] = json.dumps(sorted(set(reasons)))
        row["research_area_review_status"] = "pending" if reasons else "not_flagged"
        row["research_area_classification_origin"] = "deterministic"
        # Bind a future adjudication to evidence, not just a potentially changing
        # generated finding ID. Source passage changes invalidate the fingerprint.
        payload = {
            k: row.get(k, "")
            for k in (
                "study_doi",
                "compound",
                "support",
                "supporting_quote",
                "evidence_location",
                "evidence_locator",
            )
        }
        row["research_area_evidence_fingerprint"] = hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode()
        ).hexdigest()
        if reasons:
            queue.append(
                {
                    k: row.get(k, "")
                    for k in (
                        "finding_id",
                        "claim_id",
                        "record_type",
                        "normalization_status",
                        "study_doi",
                        "compound",
                        "domain",
                        "entity_label",
                        "kg_entity_kind_override",
                        "graph_admission_status",
                        "support",
                        "supporting_quote",
                        "evidence_location",
                        "evidence_locator",
                        *FIELDS,
                    )
                }
            )
    return queue, {
        "version": VERSION,
        "flagged_rows": len(queue),
        "not_flagged_rows": len(findings) - len(queue),
        "reason_counts": dict(
            Counter(
                reason
                for row in queue
                for reason in json.loads(row["research_area_review_reasons_json"])
            )
        ),
        "rule_action_counts": dict(
            Counter(
                reason
                for row in findings
                for reason in json.loads(
                    row.get("research_area_rule_actions_json") or "[]"
                )
            )
        ),
        "flag_policy": "advisory; not_flagged does not mean reviewed or correct",
    }


def build_review_queue(findings, audits):
    """Include rejected normalization records so an unresolved anchor is reviewable."""
    rejected = []
    for audit in audits:
        raw = json.loads(audit.get("raw_row_json") or "{}")
        if not isinstance(raw, dict):
            continue
        raw.update(
            {
                k: audit.get(k, raw.get(k, ""))
                for k in (
                    "study_doi",
                    "compound",
                    "entity_label",
                    "normalization_status",
                )
            }
        )
        raw["record_type"] = "normalization_audit"
        raw["graph_admission_status"] = "normalization_audit"
        # An unsuccessful normalization can lack a resolved entity kind.
        if (
            not raw.get("kg_entity_kind_override")
            and raw.get("domain") == "clinical_outcome"
        ):
            raw["kg_entity_kind_override"] = "condition_indication"
        rejected.append(raw)
    for row in findings:
        row["record_type"] = "finding"
    queue, summary = annotate_findings([*findings, *rejected])
    summary["normalized_finding_rows"] = len(findings)
    summary["normalization_audit_rows_checked"] = len(rejected)
    summary["flagged_record_types"] = dict(Counter(r["record_type"] for r in queue))
    return queue, summary
