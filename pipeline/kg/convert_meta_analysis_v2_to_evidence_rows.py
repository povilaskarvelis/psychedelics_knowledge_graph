#!/usr/bin/env python3
"""Convert paper-level meta-analysis v2 outputs into graph normalization rows."""

from __future__ import annotations

import argparse
from collections import Counter
import datetime as dt
import json
from pathlib import Path
import re
import sys

try:
    from pipeline.extract.io_utils import normalize, read_jsonl, write_json
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from pipeline.extract.io_utils import normalize, read_jsonl, write_json


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RUN_ID = "meta_analysis_v2_pilot_100"
DEFAULT_RUN_ROOT = ROOT / "data" / "processed" / "extraction" / "meta_analysis_v2_runs"
DEFAULT_TASKS = (
    ROOT
    / "data"
    / "processed"
    / "extraction"
    / "meta_analysis_v2_tasks"
    / "meta_analysis_v2_tasks.jsonl"
)
ROW_SCHEMA_VERSION = "meta_analysis_v2_evidence_rows_v1"

DOMAIN_ENTITY_KIND = {
    "clinical_outcome": "symptom_problem",
    "safety_tolerability": "safety_adverse_event",
    "molecular_target": "target",
    "molecular_pathway_readout": "biomarker_readout",
    "brain_system": "brain_measure",
    "cognitive_behavioral": "cognitive_behavioral_construct",
    "subjective_experience": "subjective_experience_construct",
    "pharmacokinetics_exposure": "pharmacokinetic_parameter",
    "intervention_context": "intervention_component",
    "real_world_public_health": "public_health_measure",
}

SAFETY_RE = re.compile(
    r"\b(adverse|side effect|safety|tolerab|risk|harm|serious event|headache|nausea|dizz|"
    r"dissociat|hallucinat|psychotomimetic|suicid|mortality|discontinuation due to)\b",
    re.IGNORECASE,
)
MOLECULAR_RE = re.compile(
    r"\b(bdnf|protein|gene|expression|serum|plasma|peripheral|biomarker|neuroplastic|"
    r"dopamine efflux|receptor|transporter|density|glutamate|glx|metabolite)\b",
    re.IGNORECASE,
)
BRAIN_RE = re.compile(
    r"\b(brain|cortex|cortical|gyrus|amygdala|hippocamp|cerebell|network|connectiv|"
    r"activation|blood flow|imaging|fmri|pet|eeg|mmn|amplitude|latency)\b",
    re.IGNORECASE,
)
INTERVENTION_CONTEXT_RE = re.compile(
    r"\b(session|psychotherapy|therapy quantity|control group|waitlist|moderator|setting|"
    r"preparation|integration|therapist|support protocol)\b",
    re.IGNORECASE,
)
PUBLIC_HEALTH_RE = re.compile(
    r"\b(prevalence|population|community|adolescent use|hallucinogen use|survey|"
    r"real.world|public health|use pattern|exposure prevalence)\b",
    re.IGNORECASE,
)
CONDITION_RE = re.compile(
    r"\b(disorder|depress|ptsd|post.traumatic|anxiety|pain|psychosis|schizophren|"
    r"addiction|substance use|alcohol use|bipolar|suicid|cancer|palliative|migraine|headache)\b",
    re.IGNORECASE,
)
CLINICAL_POPULATION_CONDITION_RE = re.compile(
    r"\b(patient|patients|participant|participants|adults? with|children with|adolescents? with|"
    r"diagnos|disorder|depress|ptsd|post.traumatic|anxiety|obsessive|\bocd\b|pain patients?|"
    r"chronic pain|neuropathic pain|cancer pain|psychosis|schizophren|addiction|dependence|"
    r"substance use|alcohol use disorder|bipolar|suicid|palliative|migraine|cluster headache)\b",
    re.IGNORECASE,
)
BROAD_CLINICAL_POPULATION_RE = re.compile(
    r"\b(?:mental health|psychiatric|psychological) (?:conditions?|disorders?|problems?)\b|"
    r"\btransdiagnostic\b|\bmixed (?:clinical|psychiatric|mental health) populations?\b",
    re.IGNORECASE,
)
GENERIC_CLINICAL_OUTCOME_RE = re.compile(
    r"^(?:(?:study[- ]defined|overall|pooled|clinical|treatment|antidepressant|therapeutic) )?"
    r"(?:response|remission|relapse|efficacy|effectiveness|acceptability|tolerability|"
    r"response and remission|response/remission|treatment outcomes?|clinical outcomes?|"
    r"symptom improvement|symptom reduction|symptom severity|psychiatric symptom severity|"
    r"depressive symptom reduction|depressive symptom severity|depression severity)"
    r"(?: rates?| scores?| changes?| improvement)?(?: and depressive scores)?$",
    re.IGNORECASE,
)
MOLECULAR_READOUT_RE = re.compile(
    r"\b(level|levels|density|expression|concentration|activation|activity|efflux|"
    r"readout|biomarker|amplitude|latency|blood flow)\b",
    re.IGNORECASE,
)
BRAIN_MEASURE_RE = re.compile(
    r"\b(functional connectiv\w*|within.network connectiv\w*|between.network connectiv\w*|subcortical.cortical connectiv\w*|"
    r"mismatch negativity|\bmmn\b|p300|event.related potential|\berp\b|bold|blood flow|perfusion|"
    r"glucose metabolism|oscillat|spectral power|alpha power|theta power|delta power|gamma power|"
    r"amplitude|latency|brain volume|grey matter|gray matter|white matter|cortical thickness|"
    r"receptor occupancy|binding potential|signal complexity|lempel.ziv|\blzc\b)\b",
    re.IGNORECASE,
)
COGNITIVE_RE = re.compile(
    r"\b(cognit|memory|attention|executive|inhibitory control|impulsiv|neuropsych|intelligence|\biq\b|"
    r"learning|empathy|social cognition|emotion recognition|mindfulness)\b",
    re.IGNORECASE,
)
INTERVENTION_CONTEXT_FACTOR_RE = re.compile(
    r"\b(infusion method|bolus|route of administration|administration route|comparator type|control group|"
    r"waitlist|session count|session frequency|number of sessions|therapy hours|integration hours|"
    r"treatment duration|preparation|integration|psychotherapy|support protocol|setting)\b",
    re.IGNORECASE,
)
CLINICAL_CONTEXT_RULES = (
    (re.compile(r"\b(depress\w*|major depressive disorder|mdd|treatment.resistant depression|trd)\b", re.IGNORECASE), "Depressive symptoms"),
    (re.compile(r"\b(post.traumatic stress disorder|ptsd)\b", re.IGNORECASE), "PTSD symptoms"),
    (re.compile(r"\b(anxiety|panic)\b", re.IGNORECASE), "Anxiety symptoms"),
    (re.compile(r"\b(pain|migraine|headache)\b", re.IGNORECASE), "Pain intensity"),
    (re.compile(r"\b(substance use|alcohol use|drug use|addiction)\b", re.IGNORECASE), "Substance use symptoms"),
)


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def task_index(path: Path) -> dict[str, dict]:
    return {normalize(row.get("task_id", "")): row for row in read_jsonl(path) if normalize(row.get("task_id", ""))}


def stable_task_fallback(output: dict, tasks: dict[str, dict]) -> dict:
    """Return one scientifically stable current task for an old task ID.

    Corpus metadata corrections can regenerate a task ID even when the paper
    DOI and selected source depth are unchanged. The fallback is intentionally
    narrow: exactly one current task must match both values.
    """
    doi = normalize(output.get("study_doi", "")).lower()
    source_depth = normalize(output.get("source_depth", ""))
    candidates = [
        task
        for task in tasks.values()
        if normalize(task.get("study_doi", "")).lower() == doi
        and normalize(task.get("text_depth", "")) == source_depth
    ]
    return candidates[0] if len(candidates) == 1 else {}


def joined_text(*values: object) -> str:
    return " ".join(normalize(value) for value in values if normalize(value))


def primary_domain_for(item: dict) -> tuple[str, str]:
    areas = [normalize(value) for value in item.get("subject_areas", []) if normalize(value)]
    explicit = normalize(item.get("primary_subject_area", ""))
    context = joined_text(
        item.get("outcome_or_entity", ""),
        item.get("relationship_statement", ""),
        item.get("outcome_measure", ""),
        item.get("analysis_context", {}).get("subgroup_or_moderator", "")
        if isinstance(item.get("analysis_context"), dict)
        else "",
    )
    if explicit and explicit in areas:
        # Preserve the model's primary area except when the result-specific
        # outcome is an unambiguous readout from another area the model also
        # selected. This keeps therapeutic context from turning BDNF or brain
        # connectivity results into clinical symptom nodes.
        semantic_overrides = (
            ("safety_tolerability", SAFETY_RE),
            ("molecular_pathway_readout", MOLECULAR_RE),
            ("brain_system", BRAIN_RE),
            ("cognitive_behavioral", COGNITIVE_RE),
        )
        if explicit == "clinical_outcome":
            for domain, pattern in semantic_overrides:
                if domain in areas and pattern.search(context):
                    return domain, f"result_semantic_override:{explicit}_to_{domain}"
        return explicit, "explicit_primary_subject_area"
    if len(areas) == 1:
        return areas[0], "single_subject_area"
    if not areas:
        return "", "missing_subject_area"

    rules = (
        ("molecular_target", MOLECULAR_RE),
        ("molecular_pathway_readout", MOLECULAR_RE),
        ("brain_system", BRAIN_RE),
        ("intervention_context", INTERVENTION_CONTEXT_RE),
        ("real_world_public_health", PUBLIC_HEALTH_RE),
        ("safety_tolerability", SAFETY_RE),
    )
    for domain, pattern in rules:
        if domain in areas and pattern.search(context):
            return domain, f"context_rule:{domain}"
    if "clinical_outcome" in areas:
        return "clinical_outcome", "clinical_fallback"
    return areas[0], "first_subject_area_fallback"


def overview_subjects(overview: dict) -> list[str]:
    return [normalize(value) for value in overview.get("primary_subjects", []) if normalize(value)]


def unique_overview_value(overview: dict, field: str) -> str:
    values = [normalize(value) for value in overview.get(field, []) if normalize(value)]
    question = overview.get("review_question", {}) if isinstance(overview.get("review_question"), dict) else {}
    values.extend(normalize(value) for value in question.get(field, []) if normalize(value))
    unique: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = value.casefold()
        if key not in seen:
            seen.add(key)
            unique.append(value)
    return unique[0] if len(unique) == 1 else ""


def clinical_context_endpoint(overview: dict) -> str:
    objective = normalize(overview.get("objective_and_scope", ""))
    matches = [label for pattern, label in CLINICAL_CONTEXT_RULES if pattern.search(objective)]
    return matches[0] if len(set(matches)) == 1 else ""


def subject_for_result(item: dict, overview: dict, domain: str = "") -> tuple[str, str]:
    network = item.get("network_meta_analysis", {}) if isinstance(item.get("network_meta_analysis"), dict) else {}
    treatment_a = normalize(network.get("treatment_a", ""))
    role = normalize(item.get("result_role", ""))
    if role in {"network_comparison", "network_ranking"} and treatment_a:
        return treatment_a, "network_treatment_a"
    explicit = normalize(item.get("intervention_or_exposure", ""))
    subjects = overview_subjects(overview)
    if (
        domain == "intervention_context"
        and explicit
        and INTERVENTION_CONTEXT_FACTOR_RE.search(explicit)
        and len(subjects) == 1
    ):
        return subjects[0], "single_overview_subject_for_context_analysis"
    if explicit:
        return explicit, "result_intervention_or_exposure"
    if treatment_a:
        return treatment_a, "network_treatment_a"

    statement = normalize(item.get("relationship_statement", ""))
    mentioned = [subject for subject in subjects if subject.casefold() in statement.casefold()]
    if role in {"network_comparison", "network_ranking"} and len(mentioned) > 1:
        return "", "ambiguous_network_subject"
    if len(mentioned) == 1:
        return mentioned[0], "single_overview_subject_mentioned_in_result"
    if len(subjects) == 1:
        return subjects[0], "single_paper_subject"
    favors = normalize(item.get("interpretation", {}).get("favors", "")) if isinstance(item.get("interpretation"), dict) else ""
    matching_favors = [subject for subject in subjects if subject.casefold() in favors.casefold() or favors.casefold() in subject.casefold()]
    if len(matching_favors) == 1:
        return matching_favors[0], "favors_matches_overview_subject"
    if len(mentioned) > 1:
        return " and ".join(mentioned), "multiple_overview_subjects_mentioned"
    return "", "missing_result_subject"


def entity_for_result(item: dict, domain: str, overview: dict) -> tuple[str, str, str]:
    outcome = normalize(item.get("outcome_or_entity", ""))
    population = normalize(item.get("population_or_system", "")) or unique_overview_value(
        overview, "populations_or_systems"
    )
    statement = normalize(item.get("relationship_statement", ""))
    analysis_context = item.get("analysis_context", {}) if isinstance(item.get("analysis_context"), dict) else {}

    if domain == "intervention_context":
        moderator = normalize(analysis_context.get("subgroup_or_moderator", ""))
        if moderator:
            return moderator, "intervention_component", "analysis_moderator"
        explicit_context = normalize(item.get("intervention_or_exposure", ""))
        if explicit_context and INTERVENTION_CONTEXT_FACTOR_RE.search(explicit_context):
            return explicit_context, "intervention_component", "result_context_factor"
    if outcome:
        if (
            domain == "clinical_outcome"
            and population
            and CLINICAL_POPULATION_CONDITION_RE.search(population)
            and not BROAD_CLINICAL_POPULATION_RE.search(population)
        ):
            source = (
                "population_for_generic_clinical_outcome"
                if GENERIC_CLINICAL_OUTCOME_RE.match(outcome)
                else "population_condition_with_result_outcome"
            )
            return population, "condition_indication", source
        kind = DOMAIN_ENTITY_KIND.get(domain, "")
        if domain == "molecular_pathway_readout" and not MOLECULAR_READOUT_RE.search(outcome):
            kind = "pathway_process"
        if domain == "brain_system":
            kind = "brain_measure" if BRAIN_MEASURE_RE.search(outcome) else "brain_network"
        return outcome, kind, "result_outcome_or_entity"
    if domain == "clinical_outcome" and population and CLINICAL_POPULATION_CONDITION_RE.search(population):
        return population, "condition_indication", "result_population_condition"
    return "", DOMAIN_ENTITY_KIND.get(domain, ""), "missing_result_entity"


def format_effect_estimate(estimate: dict) -> str:
    if not isinstance(estimate, dict):
        return ""
    metric = normalize(estimate.get("metric", ""))
    value = normalize(estimate.get("estimate", ""))
    interval = normalize(estimate.get("interval_reported", ""))
    if not interval:
        lower = normalize(estimate.get("interval_lower", ""))
        upper = normalize(estimate.get("interval_upper", ""))
        interval_type = normalize(estimate.get("interval_type", ""))
        if lower and upper:
            interval_label = {
                "confidence_interval": "CI",
                "credible_interval": "CrI",
                "prediction_interval": "PI",
            }.get(interval_type.casefold(), interval_type)
            interval = f"{interval_label + ' ' if interval_label else ''}{lower} to {upper}"
    parts = []
    if metric and value:
        parts.append(f"{metric} {value}")
    elif value:
        parts.append(value)
    elif metric:
        parts.append(metric)
    if interval:
        parts.append(interval)
    return "; ".join(parts)


def reported_interval(estimate: dict) -> str:
    if not isinstance(estimate, dict):
        return ""
    explicit = normalize(estimate.get("interval_reported", ""))
    if explicit:
        return explicit
    lower = normalize(estimate.get("interval_lower", ""))
    upper = normalize(estimate.get("interval_upper", ""))
    if not lower or not upper:
        return ""
    interval_type = normalize(estimate.get("interval_type", ""))
    interval_label = {
        "confidence_interval": "CI",
        "credible_interval": "CrI",
        "prediction_interval": "PI",
    }.get(interval_type.casefold(), interval_type)
    return f"{interval_label + ' ' if interval_label else ''}{lower} to {upper}"


def dose_from_result_statement(item: dict) -> str:
    statement = normalize(item.get("relationship_statement", ""))
    matches = re.findall(
        r"(?<![\w.])\d+(?:\.\d+)?\s*(?:mg|µg|ug|mcg|g)(?:\s*/\s*kg)?\b",
        statement,
        flags=re.IGNORECASE,
    )
    unique = list(dict.fromkeys(normalize(value) for value in matches if normalize(value)))
    return unique[0] if len(unique) == 1 else ""


def result_bundles_multiple_estimates(item: dict) -> bool:
    statement = normalize(item.get("relationship_statement", ""))
    ci_count = len(re.findall(r"95\s*%?\s*(?:ci|credible interval)", statement, flags=re.IGNORECASE))
    assignment_count = len(
        re.findall(
            r"\b(?:hedges'?\s*g|g|smd|md|rr|or|hr|risk ratio|odds ratio|hazard ratio)\s*[=:]\s*[-+]?\d",
            statement,
            flags=re.IGNORECASE,
        )
    )
    percentages = [
        value
        for value in re.findall(r"(?<!\d)(\d+(?:\.\d+)?)\s*%", statement)
        if value not in {"95", "90", "99"}
    ]
    estimate = item.get("effect_estimate", {}) if isinstance(item.get("effect_estimate"), dict) else {}
    return ci_count > 1 or assignment_count > 1 or (bool(estimate.get("estimate")) and len(percentages) > 1)


def effect_estimate_is_range(item: dict) -> bool:
    estimate = item.get("effect_estimate", {}) if isinstance(item.get("effect_estimate"), dict) else {}
    value = normalize(estimate.get("estimate", ""))
    return bool(re.search(r"[-+]?\d+(?:\.\d+)?\s+(?:to|through)\s+[-+]?\d+(?:\.\d+)?", value, re.IGNORECASE))


def linked_assessment_summary(result: dict, array_name: str, result_id: str, field: str) -> str:
    values: list[str] = []
    for assessment in result.get(array_name, []):
        if not isinstance(assessment, dict):
            continue
        linked_ids = [normalize(value) for value in assessment.get("applies_to_result_ids", []) if normalize(value)]
        if linked_ids and result_id not in linked_ids:
            continue
        value = normalize(assessment.get(field, ""))
        if value and value not in values:
            values.append(value)
    return " | ".join(values)


def evidence_row(
    output: dict,
    task: dict,
    result: dict,
    item: dict,
    item_index: int,
) -> tuple[dict | None, dict]:
    result_id = normalize(item.get("result_id", "")) or f"R{item_index}"
    overview = result.get("meta_analysis_overview", {}) if isinstance(result.get("meta_analysis_overview"), dict) else {}
    included_evidence = (
        overview.get("included_evidence", {})
        if isinstance(overview.get("included_evidence"), dict)
        else {}
    )
    domain, domain_source = primary_domain_for(item)
    subject, subject_source = subject_for_result(item, overview, domain)
    entity, entity_kind, entity_source = entity_for_result(item, domain, overview)
    item_population = normalize(item.get("population_or_system", ""))
    population = item_population or unique_overview_value(overview, "populations_or_systems")
    population_source = "result_population_or_system" if item_population else (
        "single_overview_population" if population else "missing_population"
    )
    item_comparator = normalize(item.get("comparator", ""))
    network = item.get("network_meta_analysis", {}) if isinstance(item.get("network_meta_analysis"), dict) else {}
    comparator = item_comparator or normalize(network.get("treatment_b", "")) or unique_overview_value(
        overview, "comparators"
    )
    comparator_source = "result_comparator" if item_comparator else (
        "network_treatment_b" if normalize(network.get("treatment_b", "")) else (
            "single_overview_comparator" if comparator else "missing_comparator"
        )
    )
    decision = {
        "task_id": normalize(output.get("task_id", "")),
        "study_doi": normalize(output.get("study_doi", "")),
        "result_id": result_id,
        "domain": domain,
        "domain_source": domain_source,
        "subject": subject,
        "subject_source": subject_source,
        "entity": entity,
        "entity_kind": entity_kind,
        "entity_source": entity_source,
        "population": population,
        "population_source": population_source,
        "comparator": comparator,
        "comparator_source": comparator_source,
    }
    missing = []
    if not domain or domain not in DOMAIN_ENTITY_KIND:
        missing.append("missing_graph_domain")
    if not subject:
        missing.append("missing_graph_subject")
    if not entity:
        missing.append("missing_graph_entity")
    role = normalize(item.get("result_role", ""))
    network = item.get("network_meta_analysis", {}) if isinstance(item.get("network_meta_analysis"), dict) else {}
    if role in {"network_comparison", "network_ranking"} and not network:
        missing.append("network_result_missing_structure")
    statement = normalize(item.get("relationship_statement", ""))
    if result_bundles_multiple_estimates(item):
        missing.append("multiple_estimates_in_one_result")
    if effect_estimate_is_range(item):
        missing.append("non_atomic_effect_estimate_range")
    output_flags = [normalize(value) for value in output.get("qa_flags", []) if normalize(value)]
    unsupported_numeric_prefixes = {
        f"numeric_value_not_in_source:{result_id}:estimate",
        f"numeric_value_not_in_source:{result_id}:interval_lower",
        f"numeric_value_not_in_source:{result_id}:interval_upper",
        f"numeric_value_not_in_source:{result_id}:standard_error",
    }
    if any(flag in unsupported_numeric_prefixes for flag in output_flags):
        missing.append("numeric_value_not_in_source")
    if f"supports_with_interval_including_null:{result_id}" in output_flags:
        missing.append("statistical_direction_conflict")
    if missing:
        decision["status"] = "held"
        decision["reasons"] = missing
        return None, decision

    metadata = task.get("paper_metadata", {}) if isinstance(task.get("paper_metadata"), dict) else {}
    estimate = item.get("effect_estimate", {}) if isinstance(item.get("effect_estimate"), dict) else {}
    evidence_size = item.get("evidence_size", {}) if isinstance(item.get("evidence_size"), dict) else {}
    heterogeneity = item.get("heterogeneity", {}) if isinstance(item.get("heterogeneity"), dict) else {}
    analysis_context = item.get("analysis_context", {}) if isinstance(item.get("analysis_context"), dict) else {}
    network = item.get("network_meta_analysis", {}) if isinstance(item.get("network_meta_analysis"), dict) else {}
    interpretation = item.get("interpretation", {}) if isinstance(item.get("interpretation"), dict) else {}
    locators = [value for value in item.get("evidence_locators", []) if isinstance(value, dict)]
    locator = locators[0] if locators else {}
    limitations = [normalize(value) for value in item.get("limitations", []) if normalize(value)]
    if not limitations:
        limitations = [normalize(value) for value in result.get("overall_limitations", []) if normalize(value)]
    uncertainty = [normalize(value) for value in item.get("extraction_uncertainties", []) if normalize(value)]
    warnings = [normalize(value) for value in result.get("warnings", []) if normalize(value)]
    result_qa_flags = [
        flag
        for flag in output_flags
        if f":{result_id}:" in flag or flag.endswith(f":{result_id}")
    ]

    row = {
        "route_output_schema_version": ROW_SCHEMA_VERSION,
        "task_id": normalize(output.get("task_id", "")),
        "study_doi": normalize(output.get("study_doi", "")),
        "study_title": normalize(output.get("study_title", "")) or normalize(metadata.get("study_title", "")),
        "study_year": normalize(metadata.get("study_year", "")),
        "study_journal": normalize(metadata.get("study_journal", "")),
        "publication_type": normalize(metadata.get("publication_type", "")),
        "domain": domain,
        "domain_route": domain,
        "dataset": domain,
        "source_type": "meta_analysis",
        "source_family": "secondary_literature",
        "paper_type": normalize(metadata.get("meta_analysis_type", "")) or "meta_analysis",
        "paper_assessment_route": "secondary_literature",
        "access_level": normalize(output.get("source_depth", "")),
        "text_depth": normalize(output.get("source_depth", "")),
        "source_item_type": "synthesis_result",
        "source_item_index": item_index,
        "source_item_id": result_id,
        "compound": subject,
        "intervention_or_exposure": subject,
        "graph_subject_label": subject,
        "graph_subject_source_field": subject_source,
        "graph_entity_label": entity,
        "raw_entity_label": entity,
        "kg_entity_kind_override": entity_kind,
        "finding_summary": normalize(item.get("relationship_statement", "")),
        "support": normalize(item.get("relationship_statement", "")),
        "synthesis_interpretation": normalize(interpretation.get("authors_interpretation", "")),
        "result_direction": normalize(interpretation.get("finding_direction", "")),
        "outcome_type": normalize(interpretation.get("outcome_orientation", "")),
        "population": population,
        "population_or_subgroup": population,
        "comparator": comparator,
        "outcome_measure": normalize(item.get("outcome_measure", "")),
        "primary_outcome": normalize(item.get("outcome_or_entity", "")),
        "assessment_timepoint": normalize(item.get("timepoint_or_window", "")),
        "follow_up_duration": normalize(item.get("timepoint_or_window", "")),
        "dose": dose_from_result_statement(item),
        "effect_size": format_effect_estimate(estimate),
        "estimate_value": normalize(estimate.get("estimate", "")),
        "meta_analysis_effect_metric": normalize(estimate.get("metric", "")),
        "meta_analysis_interval_type": normalize(estimate.get("interval_type", "")),
        "meta_analysis_interval_lower": normalize(estimate.get("interval_lower", "")),
        "meta_analysis_interval_upper": normalize(estimate.get("interval_upper", "")),
        "meta_analysis_standard_error": normalize(estimate.get("standard_error", "")),
        "p_value": normalize(estimate.get("p_value", "")),
        "confidence_interval": reported_interval(estimate),
        "sample_size_total": normalize(evidence_size.get("participant_count", "")),
        "meta_analysis_study_count": normalize(evidence_size.get("study_count", "")),
        "meta_analysis_effect_or_experiment_count": normalize(
            evidence_size.get("effect_or_experiment_count", "")
        ),
        "meta_analysis_dataset_or_comparison_count": normalize(
            evidence_size.get("dataset_or_comparison_count", "")
        ),
        "meta_analysis_overall_study_count": normalize(included_evidence.get("study_count", "")),
        "meta_analysis_overall_effect_or_experiment_count": normalize(
            included_evidence.get("effect_or_experiment_count", "")
        ),
        "meta_analysis_overall_dataset_or_comparison_count": normalize(
            included_evidence.get("dataset_or_comparison_count", "")
        ),
        "meta_analysis_evidence_design_summary": normalize(
            included_evidence.get("evidence_design_summary", "")
        ),
        "meta_analysis_search_end_date": normalize(included_evidence.get("search_end_date", "")),
        "heterogeneity_i_squared": normalize(heterogeneity.get("i_squared", "")),
        "heterogeneity_tau_squared": normalize(heterogeneity.get("tau_squared", "")),
        "heterogeneity_q_statistic": normalize(heterogeneity.get("q_statistic", "")),
        "heterogeneity_q_p_value": normalize(heterogeneity.get("q_p_value", "")),
        "heterogeneity_prediction_interval": normalize(heterogeneity.get("prediction_interval", "")),
        "heterogeneity_interpretation": normalize(heterogeneity.get("authors_interpretation", "")),
        "meta_analysis_analysis_type": normalize(analysis_context.get("analysis_type", "")),
        "meta_analysis_subgroup_or_moderator": normalize(
            analysis_context.get("subgroup_or_moderator", "")
        ),
        "meta_analysis_regression_coefficient": normalize(
            analysis_context.get("meta_regression_coefficient", "")
        ),
        "meta_analysis_sensitivity_method": normalize(analysis_context.get("sensitivity_method", "")),
        "network_treatment_a": normalize(network.get("treatment_a", "")),
        "network_treatment_b": normalize(network.get("treatment_b", "")),
        "network_reference_treatment": normalize(network.get("reference_treatment", "")),
        "network_evidence_type": normalize(network.get("evidence_type", "")),
        "network_ranking_metric": normalize(network.get("ranking_metric", "")),
        "network_ranking_value": normalize(network.get("ranking_value", "")),
        "network_inconsistency_assessment": normalize(network.get("inconsistency_assessment", "")),
        "network_transitivity_assessment": normalize(network.get("transitivity_assessment", "")),
        "study_design": "; ".join(
            normalize(value)
            for value in result.get("meta_analysis_overview", {}).get("synthesis_types", [])
            if normalize(value)
        ),
        "study_design_category": "meta_analysis",
        "evidence_design": "evidence_synthesis",
        "evidence_location": normalize(locator.get("location", "")),
        "evidence_locator": normalize(locator.get("locator", "")),
        "supporting_quote": normalize(locator.get("supporting_text", "")),
        "risk_of_bias_summary": linked_assessment_summary(
            result, "risk_of_bias_assessments", result_id, "overall_judgment"
        ),
        "evidence_strength": linked_assessment_summary(
            result, "certainty_assessments", result_id, "rating"
        ),
        "notes": " | ".join([*limitations, *uncertainty]),
        "extraction_warnings": " | ".join([*warnings, *result_qa_flags]),
        "needs_human_review": bool(uncertainty or result_qa_flags),
        "coverage_focus": normalize(item.get("importance_in_paper", "")),
        "graph_admission_status": "paper_detail"
        if normalize(item.get("importance_in_paper", "")) == "additional"
        else "main_graph",
        "graph_admission_reason": "additional_result"
        if normalize(item.get("importance_in_paper", "")) == "additional"
        else "main_or_supporting_meta_analysis_result",
        "meta_analysis_result_role": normalize(item.get("result_role", "")),
        "meta_analysis_primary_subject_area": normalize(item.get("primary_subject_area", "")) or domain,
        "meta_analysis_subject_areas": "; ".join(
            normalize(value) for value in item.get("subject_areas", []) if normalize(value)
        ),
        "normalization_domain_source": domain_source,
        "normalization_subject_source": subject_source,
        "normalization_entity_source": entity_source,
        "normalization_population_source": population_source,
        "normalization_comparator_source": comparator_source,
    }
    if domain == "clinical_outcome":
        raw_outcome = normalize(item.get("outcome_or_entity", ""))
        context_endpoint = clinical_context_endpoint(result.get("meta_analysis_overview", {}))
        row["clinical_endpoint"] = (
            context_endpoint
            if raw_outcome and GENERIC_CLINICAL_OUTCOME_RE.match(raw_outcome) and context_endpoint
            else raw_outcome
        )
        if context_endpoint:
            row["clinical_context_condition"] = context_endpoint
        if entity_kind == "condition_indication":
            row["condition_or_indication"] = entity
    elif domain == "safety_tolerability":
        row["safety_event_or_measure"] = entity
        row["adverse_events"] = entity
    elif domain == "molecular_target":
        row["target"] = entity
    elif domain == "molecular_pathway_readout":
        row["specific_readout_or_marker"] = entity
    elif domain == "brain_system":
        row["readout_or_measure"] = entity
        if entity_kind == "brain_measure":
            row["brain_measure"] = entity
    elif domain == "cognitive_behavioral":
        row["graph_construct_label"] = entity
    elif domain == "subjective_experience":
        row["subjective_construct"] = entity
    elif domain == "intervention_context":
        row["context_component"] = entity
    elif domain == "real_world_public_health":
        row["public_health_measure"] = entity
        row["exposure_or_intervention"] = subject

    decision["status"] = "written"
    return {key: value for key, value in row.items() if value not in {"", None, False}}, decision


def convert_outputs(
    outputs: list[dict],
    tasks: dict[str, dict],
    *,
    allow_stable_task_fallback: bool = False,
) -> tuple[list[dict], dict]:
    rows: list[dict] = []
    decisions: list[dict] = []
    counts: Counter = Counter()
    for output in outputs:
        counts["output_records"] += 1
        if normalize(output.get("status", "")) != "ok":
            counts[f"runner_status:{normalize(output.get('status', '')) or 'missing'}"] += 1
            continue
        result = output.get("result", {}) if isinstance(output.get("result"), dict) else {}
        if normalize(result.get("extraction_status", "")) != "extracted":
            counts[f"extraction_status:{normalize(result.get('extraction_status', '')) or 'missing'}"] += 1
            continue
        task_id = normalize(output.get("task_id", ""))
        task = tasks.get(task_id, {})
        if not task and allow_stable_task_fallback:
            task = stable_task_fallback(output, tasks)
            if task:
                counts["stable_task_fallback"] += 1
        if not task:
            counts["missing_task"] += 1
            continue
        for item_index, item in enumerate(result.get("synthesis_results", []), start=1):
            if not isinstance(item, dict):
                continue
            counts["synthesis_results"] += 1
            row, decision = evidence_row(output, task, result, item, item_index)
            decisions.append(decision)
            if row is None:
                for reason in decision.get("reasons", []):
                    counts[f"held:{reason}"] += 1
                continue
            rows.append(row)
            counts["rows_written"] += 1

    report = {
        "schema_version": "meta_analysis_v2_evidence_rows_report_v1",
        "generated_at_utc": now_utc(),
        "counts": dict(counts),
        "rows_by_domain": dict(Counter(row.get("domain", "") for row in rows)),
        "domain_decisions": dict(Counter(row.get("normalization_domain_source", "") for row in rows)),
        "subject_sources": dict(Counter(row.get("normalization_subject_source", "") for row in rows)),
        "entity_sources": dict(Counter(row.get("normalization_entity_source", "") for row in rows)),
        "held_samples": [decision for decision in decisions if decision.get("status") == "held"][:100],
    }
    return rows, report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--input-jsonl", type=Path, default=None)
    parser.add_argument("--tasks-jsonl", type=Path, default=DEFAULT_TASKS)
    parser.add_argument("--out-json", type=Path, default=None)
    parser.add_argument("--report-json", type=Path, default=None)
    parser.add_argument(
        "--allow-stable-task-fallback",
        action="store_true",
        help=(
            "Allow an old task ID to use exactly one current task with the same DOI and text depth. "
            "Use only when corpus metadata changes regenerated otherwise stable tasks."
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    run_dir = DEFAULT_RUN_ROOT / args.run_id
    input_jsonl = args.input_jsonl or run_dir / "meta_analysis_extractions.jsonl"
    out_json = args.out_json or run_dir / "meta_analysis_v2_evidence_rows.json"
    report_json = args.report_json or run_dir / "meta_analysis_v2_evidence_rows_report.json"
    rows, report = convert_outputs(
        read_jsonl(input_jsonl),
        task_index(args.tasks_jsonl),
        allow_stable_task_fallback=args.allow_stable_task_fallback,
    )
    report["inputs"] = {
        "input_jsonl": str(input_jsonl.resolve()),
        "tasks_jsonl": str(args.tasks_jsonl.resolve()),
    }
    report["outputs"] = {
        "evidence_rows_json": str(out_json.resolve()),
        "report_json": str(report_json.resolve()),
    }
    write_json(out_json, rows)
    write_json(report_json, report)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
