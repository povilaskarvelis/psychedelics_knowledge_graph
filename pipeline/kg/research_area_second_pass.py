"""Second-pass semantic adjudication for unresolved main-graph projections.

This pass is deliberately separate from the routing rules. It classifies the
remaining visible projections into confirmed, corrected, or source-review
required using the saved support statement and current graph role. It makes no
model calls and does not attempt to invent a replacement entity when the
endpoint is not represented safely by the current row.
"""

from __future__ import annotations

import json
import re
from collections import Counter

import pandas as pd


VERSION = "research_area_adjudication_v3"


def _text(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip()


def _matches(pattern: str, value: str) -> bool:
    return bool(re.search(pattern, value or "", re.I))


def _reasons(row: dict) -> set[str]:
    try:
        values = json.loads(_text(row.get("research_area_review_reasons_json")) or "[]")
    except json.JSONDecodeError:
        values = []
    return {str(value) for value in values if value}


def _statement_signals(row: dict) -> dict[str, bool]:
    support = _text(row.get("support"))
    label = _text(row.get("entity_label"))
    return {
        "benefit": _matches(
            r"\b(?:treat\w*|therap\w*|therapeutic|improv\w*|reduc\w*|decreas\w*|lower\w*|ameliorat\w*|remiss\w*|resolv\w*|resolution|disappear\w*|attenuat\w*|alleviat\w*|reliev\w*|analges\w*|suppress\w*|response|efficacy|benefit|helpful|promis\w*|protect\w*|effective|relief|reversed|revers\w*|restor\w*|prevent\w*|non.inferior|outperform\w*|superior|antidepress\w*|anti.?suicid\w*|enhanc\w*|cessation|abstinence|recovery|success\w*|utility|facilitat\w*|effect size|used for|utili[sz]ed for|able to|fewer)\b",
            support,
        ),
        "harm": _matches(
            r"\b(?:adverse event\w*|adverse effect\w*|side.effect\w*|safety|tolerab|toxic|toxicity|risk|worsen\w*|deteriorat\w*|return of|induc\w*|developed|precipitat\w*|exacerbat\w*|aggravat\w*|psychos\w*|psychotic|psychomimetic|manic|mania|hospital\w*|fatal|death|cystitis|uropathy|withdrawal|abuse|recreational|chronic use|exposure|use was associated|associated with|following use|after use|frightening|delusion\w*|paranoi\w*|blood pressure|heart rate|nausea|vomit|impair\w*|injur\w*|attempt\w*|suicidal ideation|suicide attempt|distress|persistent|negative effects?|sleep problems?|TEAEs?|higher|increased|more|greater|elevated)\b",
            support,
        ),
        "absence_or_tolerability": _matches(
            r"\b(?:no (?:participants? reported )?(?:a )?(?:significant )?(?:adverse|side.effect|safety|worsening|decline|decrease|impairment|cognitive|motor|change|difference|association|evidence)|no (?:independent )?association|without (?:adverse|impairment|worsening)|did not impair|did not induce|did not result in|well.tolerated|safe|remained stable|no changes? in (?:blood pressure|heart rate)|no significant change in|no significant difference in|no evidence of|\babsent\b)\b",
            support,
        ),
        "model": _matches(
            r"\b(?:model psychosis|model(?:ing|led)? (?:schizophren|psychos)|(?:schizophren|psychos).{0,50}model|mimic\w*|replicat\w*|resembl\w*|healthy (?:volunteer|control|subject)s?|used to model|experimental model|disease model|animal model|preclinical|psychotomimetic|phenomenolog\w*|pathophysiolog\w*|diathesis.stress|vulnerability factors|model explains|hallucinat\w*|double bookkeeping|psychosis.like|schizophrenia.like)\b",
            support,
        ) and not _matches(
            r"linear mixed model|facilitation model|model estimated|model suggests",
            support,
        ),
        "policy": _matches(
            r"cost.effectiv|willing|acceptab|barrier|preference|reschedul|schedule [iv]+|schedule \d+|TGA|guideline|recommend(?:ed|ation)|research (?:hotspot|trend|field|gap)|lack of research|thematic cluster|set and setting|preparation and integration",
            support,
        ),
        "exposure": _matches(
            r"\b(?:users?|consumers?|abusers?|recreational|past.year|lifetime|chronic use|exposure|use was associated|among \d+ .*users|following use|after use)\b",
            support,
        ),
        "measured": _matches(
            r"\b(?:MMSE|PANSS|BPRS|CADSS|functional connectivity|connectivity|brain|cortical|amygdala|glutamate|gamma|neurocog|cognitive function|memory|attention|executive|working memory|neural|fMRI|PET|EEG|biomarker|gene|receptor|pathway|psychosocial function|quality of life|functional status|phosphorylat\w*|molecular|metabolite|enzyme|marker|alpha rhythm|frequency|level\w*|concentration|urinary|bufotenine|hormone|oxytocin|cortisol|ACTH|HPA axis|prolactin|poten\w*|dose|pathophysiolog\w*|neuropatholog\w*)\b",
            support,
        ),
        "condition_endpoint": _matches(
            r"\b(?:depress\w*|anx\w*|pain|analges\w*|mood|PHQ|craving|suicid\w*|symptom|anhedonia|withdrawal|alcohol|opioid|cocaine|tobacco|PTSD|OCD|TRD|MDD|bipolar|schizophren\w*)\b",
            support,
        ),
        "neutral_condition_outcome": _matches(
            r"\b(?:no significant difference|no significant association|did not change|did not improve|failed to|not improve|no effect|lack of evidence|insufficient evidence|unproven|requires? further confirmation|limited evidence|\babsent\b)\b",
            support,
        ) or _matches(r"no statistically significant difference", support),
        "label_safety_endpoint": _matches(
            r"psychosis|psychotomimetic|mania|suicid|dissociat|sedation|cognitive|motor|toxicity|adverse|side.effect|tolerab|cardio|blood pressure|temperature|urinary|hepatic|liver|seizure|nausea|vomit|pain|abuse|dependence",
            label,
        ),
    }


def _safety_endpoint_is_present(row: dict, signals: dict[str, bool]) -> bool:
    support = _text(row.get("support"))
    label = _text(row.get("entity_label")).casefold()
    if label in {"suicidality", "suicidality risk"}:
        if signals["benefit"] and not _matches(
            r"attempt|adverse|serious|hospital|fatal|increased risk|increased suicidal|worsen|developed",
            support,
        ):
            return False
        return _matches(
            r"risk|attempt|serious|hospital|increased|worsen|occurred|adverse|fatal|self.harm",
            support,
        )
    if label in {"psychosis risk", "mania/hypomania", "mania/hypomania risk"}:
        if signals["model"] and not _matches(
            r"developed|case report|patient|participants?|users?|following (?:use|consumption)|"
            r"after (?:use|consumption)|persistent|adverse|higher (?:risk|incidence|prevalence)",
            support,
        ):
            return False
        return _matches(
            r"risk|induc|develop|psychos|psychotic|psychomimetic|hallucinat|paranoid|delusion|mania|manic|worsen|increase|occurred|persistent|no significant change|no change",
            support,
        )
    if label in {"anxiety/panic"}:
        return _matches(
            r"panic attack|anxiety (?:increased|worsen)|acute anxiety|adverse|risk|suicid|distress|higher|increased|persistent",
            support,
        )
    if label in {"overall tolerability", "adverse events", "serious adverse events"}:
        if _matches(r"tolerab(?:ility|le) of (?:trauma|material|memory|emotion)", support):
            return False
        return _matches(r"adverse|side.effect|safety|tolerab|safe|well.tolerated|serious|event|impair|toxicity|injur|risk|cardiovascular", support)
    if _direct_safety_language(support):
        return True
    if signals["absence_or_tolerability"]:
        return True
    return signals["harm"] or signals["absence_or_tolerability"]


def _direct_safety_language(support: str) -> bool:
    """Strong adverse-event language, excluding generic comparison words."""
    return _matches(
        r"\b(?:adverse\w*|side.effect\w*|TEAEs?|\bAE\b|safety|tolerab\w*|tox\w*|hepatotoxic\w*|neurotoxic\w*|cytotoxic\w*|risk|worsen\w*|deteriorat\w*|exacerbat\w*|aggravat\w*|psychos\w*|psychotic|psychomimetic|manic|mania|hospital\w*|fatal|death|cystitis|uropathy|withdrawal|abuse|frightening|delusion\w*|paranoi\w*|blood pressure|heart rate|nausea|vomit|impair\w*|injur\w*|attempt\w*|suicidal ideation|suicide attempt|distress|negative effects?|sleep problems?|seizure|rigidity|CPK|infection|survival)\b",
        support,
    )


def _therapeutic_endpoint_is_present(signals: dict[str, bool]) -> bool:
    """Whether the sentence describes a condition or symptom outcome.

    Null results and evidence gaps are still clinical findings when the
    sentence names the condition. They should not be pushed into Safety merely
    because the result is negative.
    """
    return bool(
        signals["benefit"]
        or (signals["neutral_condition_outcome"] and signals["condition_endpoint"])
    )


def second_pass_decide(row: dict) -> tuple[str, str, str]:
    """Return ``(status, action, rationale)`` for one visible unresolved row."""
    kind = _text(row.get("kg_entity_kind_override"))
    domain = _text(row.get("domain"))
    signals = _statement_signals(row)
    reasons = _reasons(row)

    if domain == "real_world_public_health" and kind == "public_health_measure":
        return (
            "confirmed_current",
            "confirm_real_world_public_health_projection",
            "The finding is an exposure, population, or healthcare-use result and is already in the real-world public-health area.",
        )

    if domain == "cognitive_behavioral" and kind == "cognitive_behavioral_construct":
        return (
            "confirmed_current",
            "confirm_cognitive_behavioral_projection",
            "The graph entity is a cognitive or behavioral construct and the finding is already in the matching area.",
        )

    if kind in {"condition_indication", "symptom_problem"}:
        therapeutic_endpoint = _therapeutic_endpoint_is_present(signals)
        if signals["policy"] and not therapeutic_endpoint:
            return (
                "corrected",
                "hold_policy_or_context_projection",
                "The statement concerns policy, prescribing guidance, research context, preparation, or set and setting rather than the condition outcome itself.",
            )
        if signals["model"] and _matches(
            r"preclinical|animal model|pathophysiolog|phenomenolog|psychotomimetic|potential utility|utility for",
            _text(row.get("support")),
        ) and not therapeutic_endpoint:
            return (
                "corrected",
                "hold_model_or_comparison_projection",
                "The condition is used as a model, mechanistic reference, or proposed application rather than as the directly measured treatment endpoint.",
            )
        if signals["model"] and not (signals["benefit"] and signals["condition_endpoint"]):
            return (
                "corrected",
                "hold_model_or_comparison_projection",
                "The statement uses the condition as a model, comparator, or phenomenological reference rather than as the treated endpoint.",
            )
        if signals["policy"] and not signals["benefit"]:
            return (
                "corrected",
                "hold_policy_or_context_projection",
                "The statement concerns policy, acceptability, preparation, research context, or health economics rather than the condition outcome.",
            )
        if (signals["exposure"] or signals["harm"]) and not therapeutic_endpoint:
            return (
                "corrected",
                "hold_safety_or_exposure_in_condition_projection",
                "The statement describes exposure, adverse effects, risk, or harm rather than treatment of the condition.",
            )
        if therapeutic_endpoint:
            if signals["measured"] and not signals["condition_endpoint"] and not signals["harm"]:
                return (
                    "corrected",
                    "hold_measured_endpoint_from_condition_projection",
                    "The statement reports a cognitive, neural, or biomarker endpoint without establishing that the condition itself is the outcome.",
                )
            return (
                "confirmed_current",
                "confirm_therapeutic_condition_outcome_projection",
                "The statement reports treatment response, symptom change, efficacy, or remission for the current condition or symptom endpoint.",
            )
        if signals["measured"] and not signals["benefit"]:
            return (
                "corrected",
                "hold_measured_endpoint_from_condition_projection",
                "The statement reports a measured cognitive, neural, or biological endpoint rather than a condition outcome.",
            )

    if kind == "safety_adverse_event":
        if _safety_endpoint_is_present(row, signals):
            return (
                "confirmed_current",
                "confirm_safety_endpoint_projection",
                "The support text contains an adverse-event, tolerability, risk, impairment, or absence-of-harm endpoint matching the safety entity.",
            )
        direct_safety = _direct_safety_language(_text(row.get("support")))
        if signals["model"]:
            return (
                "corrected",
                "hold_model_or_comparison_projection",
                "The statement uses the safety label as an experimental model or comparison without reporting a corresponding adverse event or risk endpoint.",
            )
        if signals["policy"] and not direct_safety:
            return (
                "corrected",
                "hold_policy_or_context_projection",
                "The statement concerns policy, research activity, acceptability, or treatment context rather than the current safety endpoint.",
            )
        if _therapeutic_endpoint_is_present(signals) and not direct_safety:
            return (
                "corrected",
                "hold_therapeutic_text_in_safety_projection",
                "The support text reports therapeutic improvement without a corresponding safety endpoint for the current safety label.",
            )
        if signals["measured"] and not direct_safety:
            return (
                "corrected",
                "hold_measured_endpoint_from_safety_projection",
                "The support text reports a cognitive, neural, or biological measurement without a safety endpoint.",
            )

    if domain == "safety_tolerability" and kind == "safety_adverse_event":
        return (
            "unresolved",
            "needs_source_level_review",
            "The safety-area row has mixed or insufficient endpoint language for a safe automatic decision.",
        )

    return (
        "unresolved",
        "needs_source_level_review",
        "The saved structured evidence does not establish a safe automatic correction or confirmation.",
    )


def review_second_pass(findings: pd.DataFrame, first_adjudications: pd.DataFrame, reviewed_at: str) -> pd.DataFrame:
    """Review unresolved main-graph findings and return one decision per row."""
    eligible_ids = set(
        first_adjudications.loc[
            first_adjudications["adjudication_status"].eq("unresolved"), "finding_id"
        ].astype(str)
    )
    rows = findings[findings["finding_id"].astype(str).isin(eligible_ids)].copy()
    rows = rows[rows["graph_admission_status"].eq("main_graph")]
    records = []
    for row in rows.fillna("").to_dict("records"):
        status, action, rationale = second_pass_decide(row)
        group_key = "|".join(
            _text(row.get(key))
            for key in (
                "study_doi",
                "compound",
                "support",
                "domain",
                "entity_label",
                "kg_entity_kind_override",
            )
        )
        records.append(
            {
                "finding_id": _text(row.get("finding_id")),
                "study_doi": _text(row.get("study_doi")),
                "compound": _text(row.get("compound")),
                "support": _text(row.get("support")),
                "domain": _text(row.get("domain")),
                "entity_label": _text(row.get("entity_label")),
                "kg_entity_kind_override": _text(row.get("kg_entity_kind_override")),
                "second_pass_group_key": group_key,
                "second_pass_version": VERSION,
                "second_pass_status": status,
                "second_pass_action": action,
                "second_pass_rationale": rationale,
                "second_pass_reviewed_at": reviewed_at,
                "second_pass_reviewer": "deterministic_semantic_review_v2",
            }
        )
    return pd.DataFrame(records)


def summary(decisions: pd.DataFrame) -> dict:
    if decisions.empty:
        return {"status": "ok", "rows": 0, "unique_statement_projections": 0}
    return {
        "status": "ok",
        "rows": int(len(decisions)),
        "unique_statement_projections": int(decisions.second_pass_group_key.nunique()),
        "status_counts": decisions.second_pass_status.value_counts().to_dict(),
        "action_counts": decisions.second_pass_action.value_counts().to_dict(),
    }
