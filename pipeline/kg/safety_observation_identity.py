"""Literal Safety endpoint identities and the observed/predicted result boundary.

These patterns apply only to explicit Safety event fields. They must not infer
an adverse event from a therapeutic indication or another domain's context.
Neutral families describe the measurement; they do not assert harm or causality.
"""
from __future__ import annotations

import re


EXPLICIT_EVENT_PATTERNS = tuple((re.compile(pattern, re.I), family) for pattern, family in (
    (r"\b(?:blood[- ]pressure|heart[- ]rate|hypertensive (?:crisis|emergency|effects?|reaction)|rhythm disturbances?)\b", "Cardiovascular safety"),
    (r"\bserotonin toxicity\b", "Serotonin syndrome"),
    (r"\b(?:hearing (?:loss|deterioration|thresholds?)|ototoxicity|auditory injury)\b", "Tinnitus/auditory symptoms"),
    (r"\b(?:loss of vision|vision loss)\b", "Visual impairment"),
    (r"\b(?:muscle rigidity|acute dystonia|oculogyric crisis)\b", "Musculoskeletal effects"),
    (r"\b(?:gastrointestinal (?:toxicity|adverse (?:events?|effects?)|symptoms?|issues)|digestive[- ]system symptoms|"
     r"(?:abdominal|epigastric) pain|gastritis|gastroduodenitis|diarrh(?:ea|oea)|constipation|rectal ulcer)\b", "Gastrointestinal effects"),
    (r"\b(?:pruritus|urticaria|urticarial (?:rash|eruption)|hives|allergic reaction|hypersensitivity reaction)\b", "Skin/hypersensitivity effects"),
    (r"\b(?:intraocular[- ]pressure|retinal (?:damage|detachment)|ocular toxicity|ocular/retinal toxicity|optic disc swelling)\b", "Ocular effects"),
    (r"\b(?:aplastic an(?:a)?emia|thrombocyte levels?|platelet counts?|coagulation parameters?|disseminated intravascular coagulation)\b", "Hematologic effects"),
    (r"\bintracranial[- ]pressure\b", "Intracranial pressure effects"),
    (r"\b(?:bone mineral (?:density|content)|(?:trabecular bone|bone trabecular) (?:thickness|volume)|bone toxicity)\b", "Bone effects"),
))

# Whole-field aliases only: addiction treatment, opioid-dependence populations,
# and tolerance to therapeutic or assay effects are not abuse-liability results.
EXPLICIT_EVENT_ALIASES = {
    # Complete event-field vocabulary. These describe the measured endpoint,
    # not its direction, causality, severity or an unrelated treatment's role.
    "nightmare": "Sleep disturbance",
    "nightmares": "Sleep disturbance",
    "incidence of nightmares": "Sleep disturbance",
    "postoperative nightmare incidence": "Sleep disturbance",
    "all-cause treatment discontinuation": "All-cause discontinuation",
    "dropout for any cause": "All-cause discontinuation",
    "dropouts for any cause": "All-cause discontinuation",
    "dropouts for any cause.": "All-cause discontinuation",
    "cerebral edema": "Adverse events",
    "cerebral oedema": "Adverse events",
    "acute cerebral oedema": "Adverse events",
    "dysgeusia": "Adverse events",
    "paresthesia": "Adverse events",
    "paraesthesia": "Adverse events",
    "hypoesthesia": "Adverse events",
    "hypoaesthesia": "Adverse events",
    "dependence": "Abuse/dependence liability",
    "physical dependence": "Abuse/dependence liability",
    "mental dependence": "Abuse/dependence liability",
    "dependence or addiction": "Abuse/dependence liability",
    "dependence and addiction": "Abuse/dependence liability",
    "abuse and addiction": "Abuse/dependence liability",
    "addiction or abuse": "Abuse/dependence liability",
    "dependence and withdrawal": "Abuse/dependence liability",
    "physical dependence and withdrawal": "Abuse/dependence liability",
    "abuse and dependence risks": "Abuse/dependence liability",
    "potential dependence": "Abuse/dependence liability",
    "potential abuse and dependence": "Abuse/dependence liability",
    "psychological addiction and dependence": "Abuse/dependence liability",
}


def explicit_event_matches(text: str) -> list[tuple[int, int, str]]:
    exact = EXPLICIT_EVENT_ALIASES.get(text.strip().casefold())
    if exact:
        return [(0, -1, exact)]
    return [(match.start(), i, family) for i, (pattern, family) in enumerate(EXPLICIT_EVENT_PATTERNS)
            if (match := pattern.search(text))]


def is_predicted_safety_endpoint(event: str, design: str = "") -> bool:
    """A forecast endpoint is distinct from an observed regression outcome.

    Scope the test to what was measured, not mentions of prediction anywhere in
    a result paragraph. Observed values exceeding predictions and predictors of
    an observed outcome stay on the normal observation path.
    """
    if re.match(r"^(?:predicted and observed|observed and predicted)\b", event, re.I):
        return False
    if re.match(r"^(?:(?:model|computer|QSAR)[- ]+)?predicted\b|^in[- ]silico\b", event, re.I):
        return True
    computational_design = re.search(r"\b(?:model(?:ing|ling)|computational|in[- ]silico|QSAR)\b", design, re.I)
    if computational_design and re.search(
        r"\b(?:was|were|is|are)\s+(?:simulated|predicted\s+(?:as|to be))\b", event, re.I
    ):
        return True
    return bool(re.match(r"^model(?:ed|led)[- ](?:impact|risk|toxicity|effects?)\b", event, re.I)
                and re.search(r"\b(?:model(?:ing|ling)|computational|in[- ]silico|QSAR)\b", design, re.I))


def explicit_named_safety_regimen(row: dict) -> str:
    """Repair an atomic type only for a completely spelled-out saved regimen.

    A bare acronym, ingredient mention, uncertain product or treatment proposal
    is insufficient. This preserves the observation in detail, with no member-
    drug attribution and no new controlled overview subject.
    """
    if row.get("source_item_type") != "primary_item":
        return ""
    exposure = str(row.get("compound_or_exposure") or "").strip()
    if not re.fullmatch(r"Magnesium\s*[-–—]\s*ibogaine therapy\s*\(MISTIC\)", exposure, re.I):
        return ""
    if not row.get("safety_event_or_measure") or not (row.get("finding_summary") or row.get("support")):
        return ""
    if not (row.get("evidence_locator") or row.get("evidence_location") or row.get("supporting_quote")):
        return ""
    return exposure
