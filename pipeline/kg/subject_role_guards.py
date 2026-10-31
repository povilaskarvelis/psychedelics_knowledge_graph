"""Conservative admission guards for explicitly distinct actors in saved items.

These checks use the extraction's structured exposure and same-item evidence,
never article titles. They preserve the complete item in paper detail when a
named comparator, sold-as identity, or other manipulation would otherwise be
silently selected as the drug that produced the result.
"""
from __future__ import annotations

import re
from pipeline.extract.io_utils import normalize
from pipeline.kg.real_world_subjects import _identities, DEFAULT_REGISTRY

VERSION = "structured_subject_roles_v5"
EXPOSURE_FIELDS = ("compound_or_exposure", "compound_or_intervention", "compound_or_class", "compound_or_analyte", "exposure_or_policy", "intervention_or_exposure", "compound")
BIOLOGICAL_DOMAINS = {"safety_tolerability", "subjective_experience", "clinical_outcome", "cognitive_behavioral"}
COMPARISON_RE = re.compile(r"[;,]\s*compared (?:with|to)\s+", re.I)
SOLD_RE = re.compile(r"\b(?:sold as|thought to be|believed to be)\b", re.I)
CONFIRMED_RE = re.compile(r"\b(?:detected|identified|confirmed|containing|contain)\b", re.I)


def _atomic_labels(text: str) -> set[str]:
    return {h["label"] for h in _identities(text, DEFAULT_REGISTRY) if h["kind"] == "atomic_compound" and h["allowed"]}


def _source(row: dict) -> tuple[str, str]:
    for field in EXPOSURE_FIELDS:
        value = normalize(row.get(field, ""))
        if value and value.casefold() not in {"not_reported", "not_applicable", "none"}:
            return field, value
    return "", ""


def structured_subject_role_decision(row: dict) -> dict | None:
    """Propose only role corrections supported explicitly by the same item."""
    domain = normalize(row.get("domain", row.get("domain_route", "")))
    field, exposure = _source(row)
    if not exposure:
        return None
    finding = normalize(row.get("finding_summary", ""))
    result_text = " ".join(normalize(row.get(k, "")) for k in ("finding_summary", "effect_or_statistic", "behavioral_context"))
    if domain == "safety_tolerability":
        context = re.match(r"^(.+?)\s+(?:administered|given|applied)\s+to\s+"
                           r"(?:(?:the|a|an|adult|young|male|female)\s+)*(?:rats|mice|animals|patients|participants|volunteers|cells|tissue)\s+"
                           r"(?:treated|challenged|exposed)\s+with\s+(.+)$", exposure, re.I)
        if context and not _atomic_labels(context[1]) and _atomic_labels(context[2]) and not _atomic_labels(result_text):
            actor_parts = [context[1], *re.findall(r"\(([^)]+)\)", context[1])]
            actor_mentioned = any(len(p.strip()) >= 4 and re.search(re.escape(p.strip()), result_text, re.I) for p in actor_parts)
            if actor_mentioned and re.search(r"\b(?:toxic|toxicity|tolerability)\b", result_text, re.I):
                return {"action": "paper_detail", "reason": "eligible_drug_is_context_not_measured_actor", "field": field, "source": exposure}
    # A spontaneous disease state or explicitly drug-free manipulation is not
    # a drug class merely because its outcome resembles dissociation.
    spontaneous = bool(re.search(r"\bspontaneous\b.{0,35}\baura\b", exposure, re.I))
    mechanical = bool(re.search(r"\b(?:electrical|optogenetic)\s+(?:activation|inhibition|stimulation)\b", exposure, re.I))
    if spontaneous or mechanical:
        details = " ".join(normalize(row.get(k, "")) for k in ("dose_or_regimen", "finding_summary", "support"))
        no_drug = bool(re.search(r"\b(?:without ketamine|in the absence of ketamine|no (?:psychedelic (?:compound|drug)|drug) (?:was |were )?administered)\b", exposure + " " + details, re.I))
        active = re.sub(r"\b(?:without|in the absence of)\s+(?:ketamine|phencyclidine|PCP|psychedelic(?: compounds?| drugs?)?)\b", "", exposure, flags=re.I)
        active = re.sub(r"\bno (?:psychedelic (?:compound|drug)|drug) (?:was |were )?administered\b", "", active, flags=re.I)
        drug_class = r"(?:psychedelic|hallucinogen(?:ic)?|dissociative)s?"
        positive_class = bool(re.search(
            rf"\b{drug_class}(?:\s+(?:drugs?|compounds?))?\s+(?:use|treatment|administration|exposure|therapy|administered)\b|"
            rf"\b(?:use|treatment|administration|exposure)\s+(?:of|to|with)\s+{drug_class}\b|\b{drug_class}\s+drugs?\b", active, re.I))
        if (spontaneous or no_drug) and not positive_class and not _atomic_labels(active):
            return {"action": "non_drug_subject", "reason": "non_drug_intervention_or_spontaneous_state", "field": field, "source": exposure, "label": exposure}
    # These are explicit attribution limitations, not inferred from a missing
    # drug name in a paper or from a nonsignificant drug-control contrast.
    if re.search(r"(?:does not|do not|did not) (?:identify|specify|distinguish|assign).{0,65}(?:which (?:drugs|compounds)|particular compounds|MDMA from methamphetamine)", exposure + " " + result_text, re.I):
        return {"action": "paper_detail", "reason": "individual_drug_result_explicitly_unresolved", "field": field, "source": exposure}
    if re.search(r"\bbaseline\b", result_text, re.I) and re.search(r"\bnot (?:an? )?(?:(?:esketamine|ketamine|drug) )?(?:treatment )?(?:effect|response)\b", result_text, re.I):
        return {"action": "paper_detail", "reason": "baseline_disease_comparison_not_drug_effect", "field": field, "source": exposure}
    universal = list(re.finditer(r"\b(?:each compound|each of (?:the )?(?:\w+ )?compounds|all (?:\w+ )?compounds)\b", result_text, re.I))
    if (universal and len(_atomic_labels(exposure)) >= 2
            and not re.search(r"\b(?:pooled|combined group|mixture|co[- ]?administ\w*)\b", result_text, re.I)):
        # A compound exception makes this a mixed item: do not copy its single
        # direction/statistic to every named drug. Preserve the complete item in
        # detail rather than trying to infer separate endpoint-specific rows.
        # Exceptions to cells, doses or conditions do not change drug identity.
        compound_exception = bool(re.search(r"\ball but (?:one|two|\d+)\b", exposure + " " + result_text, re.I))
        for exception in re.finditer(r"\b(?:except(?: for)?|with the exception of|other than|excluding|but not)\s+([^.;]+)", result_text, re.I):
            tail = exception.group(1).strip(" ,")
            if re.match(r"(?:in|at|under|during|after|before|when|where|to|by|from)\b", tail, re.I):
                continue
            # E.g. 'except PC12 cells at high concentrations' is a condition,
            # whereas 'except mescaline in PC12 cells' is a compound exception.
            condition = re.match(r"(?:(?:the|a|an)\s+)?(?:[\w-]+\s+){0,3}(?:cells?|cell lines?|cultures?|tissues?|doses?|concentrations?|conditions?|timepoints?)\b", tail, re.I)
            if condition and not _atomic_labels(tail[:condition.end()]):
                continue
            if exception.group(0).lower().startswith("but not"):
                # 'all compounds evoked release but did not reach the reference'
                # and 'but not significantly' are not exceptions to the actors.
                if re.match(r"(?:significantly|consistently|uniformly|always|necessarily|statistically)\b", tail, re.I):
                    continue
                if not _atomic_labels(tail.split(",")[0]) and not re.match(r"(?:compound|drug|metabolite)\s+\w+", tail, re.I):
                    continue
            compound_exception = True
            break
        if compound_exception:
            return {"action": "paper_detail", "reason": "parallel_compound_result_has_exceptions", "field": field, "source": exposure}

        if re.search(r"\bnot\s+(?:all (?:\w+ )?compounds|each compound)\b", result_text, re.I):
            return {"action": "paper_detail", "reason": "parallel_compound_result_not_universal", "field": field, "source": exposure}
        affirmative = False
        for match in universal:
            before = result_text[:match.start()]
            after = result_text[match.end():]
            # 'Across all compounds, affinity correlated with potency' is a
            # relationship between compounds, not the effect of each compound.
            # 'All compounds producing X' only quantifies a selected subset.
            if re.search(r"\b(?:across|among|between|over|not)\s+$", before, re.I):
                continue
            modifier = re.match(r"all (\w+) compounds", match.group(0), re.I)
            if modifier and not re.fullmatch(r"(?:test|tested|listed|investigated|these|those|the|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|\d+)", modifier.group(1), re.I):
                # 'all other/active/responsive compounds' selects a subset.
                continue
            if re.match(r"\s+(?:that|which|producing|showing|exhibiting|causing|eliciting|having)\b", after, re.I):
                continue
            affirmative = True
        if not affirmative:
            return {"action": "paper_detail", "reason": "parallel_compound_result_not_universal", "field": field, "source": exposure}
        return {"action": "parallel_subjects", "reason": "explicit_result_for_each_named_compound", "field": field, "source": exposure, "label": exposure}
    # Pooled findings are not drug-specific just because the exposure supplies
    # examples or the most common drugs. Keep the full exposure as provenance.
    if (re.match(r"^(?:lifetime |regular-dose |typical )?psychedelic(?:s| use| experience|[- ]assisted)", exposure, re.I)
            and len(_atomic_labels(exposure)) >= 2):
        return {"action": "class_subject", "reason": "explicit_pooled_psychedelic_exposure", "field": field, "source": exposure,
                "label": "Psychedelics (unspecified compounds)"}

    reason = ""
    # A drug is only the comparator if it appears after an explicit comparison
    # delimiter and the tested exposure has no eligible drug of its own.
    comparison = COMPARISON_RE.search(exposure)
    if domain in BIOLOGICAL_DOMAINS and comparison:
        actor, comparator = exposure[:comparison.start()], exposure[comparison.end():]
        actor_hits = _identities(actor, DEFAULT_REGISTRY)
        # Preserve general classes, explicit chiral actors, challenge groups and
        # jointly measured comparisons. A comma is not evidence that every
        # subsequent drug is merely background. Require an actor-led result or
        # explicitly separate archival comparison studies.
        actor_key = re.sub(r"^(?:oral|intravenous|vaporized|recreational|lethal doses of)\s+", "", actor, flags=re.I).split()[0].strip("(),;")
        actor_led = len(actor_key) >= 4 and re.match(re.escape(actor_key) + r"\b", finding, re.I)
        archival = re.search(r"separate laboratory studies|historical comparator|archival compar", comparator, re.I)
        class_actor = any(h["kind"] == "compound_class" for h in actor_hits)
        chiral_actor = re.search(r"(?:\([RS]\)|\b[RS])[- ](?:MDMA|ketamine|norketamine)", actor, re.I)
        if (_atomic_labels(comparator) and not _atomic_labels(actor) and not class_actor
                and not chiral_actor and (actor_led or archival)):
            reason = "eligible_drug_is_comparator_not_measured_actor"

    # Require a positively identified alternative in the structured exposure.
    # A late negative screen alone never establishes an identity substitution.
    sold = SOLD_RE.search(exposure)
    health_measure = normalize(row.get("public_health_measure", ""))
    biological_result = domain in BIOLOGICAL_DOMAINS or (
        domain == "real_world_public_health" and re.search(r"\b(?:toxicity|clinical|poisoning|fatal|mortality|death)\b", health_measure, re.I)
        and not re.search(r"composition|adulter|content|purity", health_measure, re.I))
    if sold and biological_result:
        before, after = exposure[:sold.start()], exposure[sold.end():]
        purported = _atomic_labels(after.split(";")[0].split(",")[0])
        # Either actual contents precede the marketed identity, or a subsequent
        # explicit confirmation gives the actual contents (not merely a test).
        confirmation = re.search(r"(?:subsequently )?confirmed to contain\s+([^;.]+)", exposure, re.I)
        actual = confirmation.group(1) if confirmation else before
        if purported and CONFIRMED_RE.search(exposure) and not (purported & _atomic_labels(actual)):
            if re.search(r"\b(?:detected|identified|confirmed|containing|contain)\b", actual, re.I) or confirmation:
                reason = "confirmed_substance_differs_from_marketed_identity"

    context = normalize(row.get("behavioral_context", ""))
    unspecified = re.search(r"(?:treatment )?effects on this outcome (?:were|are) not (?:specified|reported)", context, re.I)
    if domain == "cognitive_behavioral" and unspecified and _atomic_labels(exposure) and _atomic_labels(context[:unspecified.start()]):
        reason = "eligible_drug_effect_explicitly_not_reported_for_endpoint"

    if (domain == "clinical_outcome" and re.search(r"responsive genes?", exposure, re.I)
            and re.search(r"(?:haplotype|single.snp|susceptibility genes?|case.control)", finding, re.I)):
        reason = "drug_responsive_gene_selection_not_clinical_drug_exposure"

    if reason:
        return {"action": "paper_detail", "reason": reason, "field": field, "source": exposure}
    return None


def apply_structured_subject_roles(row: dict) -> bool:
    """Apply a decision; True means the subject is fixed and must be preserved."""
    if row.get("subject_role_resolution_version") == VERSION:
        if row.get("subject_role_resolution_action") == "non_drug_subject":
            source = row.get("subject_role_resolution_source_value", "")
            row.update(compound=source, graph_subject_label=source, graph_subject_kind="exposure_context", atomic_compound_candidate="",
                       graph_admission_status="paper_detail", graph_admission_reason="non_drug_intervention_or_spontaneous_state")
            return True
        if row.get("subject_role_resolution_action") == "class_subject":
            row.update(compound="Psychedelics (unspecified compounds)", graph_subject_label="Psychedelics (unspecified compounds)",
                       graph_subject_kind="compound_class", atomic_compound_candidate="",
                       graph_subject_source_field=row.get("subject_role_resolution_source_field", ""))
            return True
        if row.get("subject_role_resolution_action") == "parallel_subjects":
            source = row.get("subject_role_resolution_source_value", "")
            row.update(compound=source, graph_subject_label=source, graph_subject_kind="compound_combination", atomic_compound_candidate="")
            return True
        return False
    decision = structured_subject_role_decision(row)
    if not decision:
        return False
    row["subject_role_resolution_version"] = VERSION
    row["subject_role_resolution_action"] = decision["action"]
    row["subject_role_resolution_reason"] = decision["reason"]
    row["subject_role_resolution_source_field"] = decision["field"]
    row["subject_role_resolution_source_value"] = decision["source"]
    row["subject_role_original_compound"] = normalize(row.get("compound", ""))
    if decision["action"] == "non_drug_subject":
        row.update(compound=decision["label"], graph_subject_label=decision["label"], graph_subject_kind="exposure_context",
                   atomic_compound_candidate="", graph_subject_source_field=decision["field"],
                   graph_admission_status="paper_detail", graph_admission_reason=decision["reason"])
        return True
    if decision["action"] == "class_subject":
        row.update(compound=decision["label"], graph_subject_label=decision["label"], graph_subject_kind="compound_class",
                   atomic_compound_candidate="", graph_subject_source_field=decision["field"])
        return True
    if decision["action"] == "parallel_subjects":
        row.update(compound=decision["label"], graph_subject_label=decision["label"], graph_subject_kind="compound_combination",
                   atomic_compound_candidate="", graph_subject_source_field=decision["field"])
        return True
    row["graph_admission_status"] = "paper_detail"
    row["graph_admission_reason"] = decision["reason"]
    return False
