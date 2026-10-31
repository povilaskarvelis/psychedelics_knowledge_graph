"""Bounded repairs of explicit, saved primary-study measurement fields.

These rules do not recover information from titles, other results or source
papers. They preserve original measurements and source locators and do not
infer causal effects, diagnoses, chemical identities or individual estimates
from aggregates. Call before ordinary entity matching. Brain fallback metadata
must be resolved against the normal vocabulary by the caller.
"""
from __future__ import annotations

import json
import re
from typing import Any

VERSION = "measured_endpoint_repairs_v2"
MISSING = {"", "none", "not_reported", "not reported", "not_applicable", "not applicable", "n/a"}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _join(row: dict, *keys: str) -> str:
    return " ".join(_text(row.get(k)) for k in keys if _text(row.get(k)).lower() not in MISSING)


def _has(pattern: str, value: str) -> bool:
    return bool(re.search(pattern, value, re.I))


def _record(row: dict, before: dict, domain: str, rule: str, fields: tuple[str, ...]) -> tuple[dict, str]:
    """Keep exact source values and field changes, including old graph objects."""
    row["domain"] = row["domain_route"] = row["dataset"] = domain
    row["measured_endpoint_repair_version"] = VERSION
    row["measured_endpoint_repair_rule"] = rule
    row["measured_endpoint_repair_source_fields_json"] = json.dumps(
        {k: before.get(k) for k in fields}, ensure_ascii=False, sort_keys=True,
    )
    row["measured_endpoint_repair_original_fields_json"] = json.dumps(
        {k: before.get(k) for k in row if row.get(k) != before.get(k) and not k.startswith("measured_endpoint_")},
        ensure_ascii=False, sort_keys=True,
    )
    return row, domain


def _primary(row: dict) -> bool:
    return _text(row.get("source_item_type")) == "primary_item" or (
        _text(row.get("paper_type")) == "primary_study"
        and _text(row.get("source_family")) not in {"review", "meta_analysis"}
    )


def apply_measured_endpoint_repairs(row: dict, domain: str) -> tuple[dict, str]:
    """Return a copy and repaired domain; unchanged copies signal no repair.

    ``measured_endpoint_brain_region_candidates_json`` is a fallback proposal,
    not permission to invent new vocabulary entries or activation assertions.
    """
    out = dict(row)
    if not _primary(row) or row.get("measured_endpoint_repair_version") == VERSION:
        return out, domain

    if domain == "brain_system":
        circuit = _text(row.get("neural_circuit"))
        region = _text(row.get("brain_region"))
        # A two-region connectivity endpoint can have a detailed circuit label
        # that the vocabulary cannot parse, while both anatomical names are
        # explicitly present in the structured region field. These are two
        # projections of ONE connection result, never two local activations.
        # The caller must resolve every proposed name before using either.
        pair = [p.strip() for p in re.split(r"\s+and\s+|;\s*", region) if p.strip()]
        if (_text(row.get("primary_graph_anchor_kind")) == "neural_circuit"
                and len(pair) == 2
                and all(_has(r"\b(?:gyrus|cortex|sulcus|visual area)\b", p) for p in pair)
                and _has(r"\b(?:connectivity|RSFC|connections?)\b", _text(row.get("readout")))
                and not _has(r"\b(?:activation|deactivation|volume|thickness)\b", circuit)):
            out["measured_endpoint_brain_region_candidates_json"] = json.dumps(pair, ensure_ascii=False)
            out["measured_endpoint_brain_fallback_only"] = True
            out["measured_endpoint_brain_relationship"] = "pairwise_connectivity"
            return _record(out, row, domain, "explicit_region_pair_for_unmapped_connectivity",
                           ("brain_region", "neural_circuit", "readout", "primary_graph_anchor_kind"))
        # Generic self-connection labels contain no named anatomical relationship.
        # Require spelled-out definitions in the separate structured region field.
        if (_has(r"^(?:regional )?self[- ]connections?\b", circuit)
                and _text(row.get("primary_graph_anchor_kind")) == "neural_circuit"
                and _has(r"\b(?:gyrus|cortex|sulcus|visual area)\b", region)):
            parts = [p.strip() for p in region.split(";") if p.strip()]
            if len(parts) >= 2 and all(_has(r"\b(?:gyrus|cortex|sulcus|visual area)\b", p) for p in parts):
                out["measured_endpoint_brain_region_candidates_json"] = json.dumps(parts, ensure_ascii=False)
                out["measured_endpoint_brain_fallback_only"] = True
                out["measured_endpoint_brain_relationship"] = "regional_self_connectivity"
                return _record(out, row, domain, "explicit_regions_for_unmapped_self_connections",
                               ("brain_region", "neural_circuit", "readout", "primary_graph_anchor_kind"))

    if domain == "intervention_context":
        focal = _join(row, "context_component", "component_type")
        design = _join(row, "study_design", "delivery_format", "data_source_or_study_design")
        population = _join(row, "population_or_setting", "population_or_subgroup", "population")
        measured = _join(row, "finding_summary", "effect_or_statistic")
        provider = _has(r"\b(?:social workers?|clinicians?|healthcare professionals?|health professionals?|"
                        r"psychiatrists?|psychologists?|nurses?|pharmacists?|providers?|therapists?)\b", population)
        survey = _has(r"\b(?:vignette|survey|questionnaire)\b", design)
        attitude = _has(r"\b(?:stigma|knowledge|perceived (?:drug |MDMA )?risk|attitudes?|ratings?|judgments?)\b", focal)
        implementation = _has(r"\b(?:acceptability|appropriateness|feasibility|implementation)\b", focal)
        actual = _has(r"\b(?:rated|ratings?|correlat\w*|associated|scores?|respondents?|participants?)\b", measured)
        if provider and survey and actual and (attitude or implementation):
            perception_focal = _has(r"\b(?:stigma|perceived (?:drug |MDMA )?risk)\b", _text(row.get("context_component")))
            topic = "Perceived benefits & harms" if perception_focal else "Implementation & acceptability"
            out.update(kg_entity_kind_override="public_health_measure", graph_entity_label=topic,
                       public_health_graph_label=topic, public_health_topic_category=topic,
                       public_health_measure=_text(row.get("context_component")),
                       entity_role="public_health_measure")
            out["exposure_or_policy"] = _join(row, "compound_or_intervention") or _text(row.get("compound"))
            out["data_source_or_study_design"] = design
            out["measured_endpoint_observation_kind"] = "provider_perception_not_patient_drug_effect"
            return _record(out, row, "real_world_public_health", "provider_survey_attitude_measure",
                           ("context_component", "component_type", "study_design", "delivery_format", "population_or_setting"))

    if domain == "clinical_outcome":
        indication = _text(row.get("condition_or_indication"))
        endpoint = _join(row, "clinical_endpoint", "outcome_measure")
        finding = _join(row, "finding_summary", "effect_or_statistic")
        design = _join(row, "study_design", "study_design_category")
        if (_has(r"\bsubstance[- ]induced mental disorders?\b", indication)
                and _has(r"\b(?:incident|case counts?|cases)\b", endpoint)
                and _has(r"\b(?:administrative|population[- ]based|health.data|diagnostic codes|records)\b", endpoint + " " + design)
                and _has(r"\b\d+\s+(?:incident |hallucinogen-associated )?cases\b", finding)
                and _text(row.get("comparator")).lower() in MISSING | {"not_applicable"}
                and not _has(r"\b(?:treated|treatment response|randomi[sz]ed|assigned|intervention trial)\b", design + " " + finding)):
            topic = "Health & functioning outcomes"
            out.update(kg_entity_kind_override="public_health_measure", graph_entity_label=topic,
                       public_health_graph_label=topic, public_health_topic_category=topic,
                       public_health_measure=_text(row.get("clinical_endpoint")), entity_role="public_health_measure",
                       exposure_or_policy=_text(row.get("compound_or_intervention")) or _text(row.get("compound")))
            out["measured_endpoint_observation_kind"] = "descriptive_drug_associated_case_count"
            return _record(out, row, "real_world_public_health", "administrative_case_count_not_treatment_indication",
                           ("condition_or_indication", "clinical_endpoint", "outcome_measure", "study_design", "comparator"))
        # Explicit symptom endpoint, not a diagnosis inferred from PCL eligibility.
        if (_has(r"\b(?:post[- ]?traumatic stress|PTSD) symptoms?\b", indication)
                and _has(r"\b(?:PTSD symptom|PCL[- ]?5|post[- ]?traumatic stress symptom)\b", endpoint)
                and not _has(r"\b(?:complex|self[- ]organization|avoidance|hyperarousal|re[- ]experienc\w*|subscale|symptom cluster)\b", indication + " " + endpoint)):
            label = "Post-traumatic stress symptoms"
            out.update(kg_entity_kind_override="symptom_problem", graph_entity_label=label,
                       entity_role="symptom_or_problem", symptom_problem=label,
                       endpoint_label_source="clinical_symptom_endpoint")
            out["measured_endpoint_observation_kind"] = "symptom_severity_not_diagnostic_status"
            return _record(out, row, domain, "explicit_ptsd_symptom_measure",
                           ("condition_or_indication", "clinical_endpoint", "outcome_measure", "population_model_category"))

    if domain in {"molecular_pathway_readout", "pharmacokinetics_exposure"}:
        marker = _text(row.get("specific_readout_or_marker")) if domain == "molecular_pathway_readout" else _text(row.get("pk_or_exposure_parameter"))
        analytes = marker if domain == "molecular_pathway_readout" else _join(row, "metabolite_or_analyte", "compound_or_analyte")
        matrix = _text(row.get("matrix"))
        population = _join(row, "population_or_system", "population_or_species", "population", "system", "experimental_system_category")
        finding = _join(row, "finding_summary", "value", "effect_or_statistic")
        named = _has(r"\b(?:ketamine|norketamine|hydroxynorketamine|HNKs?|psilocin|psilocybin|MDMA|MDA|"
                     r"DMT|LSD|ibogaine|noribogaine|mescaline|phencyclidine|salvinorin A)\b", analytes)
        in_vivo = _has(r"\b(?:mice|mouse|rats?|rodents?|humans?|patients?|participants?|volunteers?|in.vivo)\b", population)
        compartment = _has(r"\b(?:plasma|serum|blood|brain|cerebrospinal|CSF|urine|liver)\b", marker + " " + matrix)
        observed = _has(r"\b(?:measured|detected|concentrations? (?:were|was|after|at)|levels? (?:were|was)|"
                        r"below (?:the )?(?:LLOQ|limit)|total (?:brain |plasma )?concentration)\b", finding)
        blocked = _has(r"\b(?:EC50|IC50|Ki|Kd|concentration[- ]response|dose[- ]response|genotyp\w*|"
                       r"receptor|binding|endogenous|glutamate|GABA|serotonin|dopamine|cortisol|"
                       r"storage|stability|spiked|in vitro|predicted|simulated)\b", marker)
        if not (named and in_vivo and compartment and observed and _has(r"\bconcentrations?\b", marker) and not blocked):
            return out, domain
        # No conversion of unrelated in-vitro or modeled concentration claims.
        if _has(r"\b(?:in vitro|microsom\w*|cell culture|simulated|predicted)\b", population):
            return out, domain
        aggregate = _has(r"\b(?:combined|total)\b", marker) and _has(r"\b(?:and|metabolites?|HNKs?)\b|,", analytes)
        if domain == "pharmacokinetics_exposure":
            # Existing PK relations (exposure-response, distribution, Cmax,
            # clearance, individual metabolite formation) have their own valid
            # semantics. Repair only an aggregate concentration incorrectly
            # labelled as a metabolic relationship, not every PK measurement.
            if not (aggregate and _has(r"^concentration\b", marker)
                    and row.get("pk_relationship_type") in {"metabolized_to", "metabolized_via"}):
                return out, domain
        elif _has(r";|\b(?:ratio|markers?|half[- ]?life|Cmax|Tmax|AUC|correlat\w*)\b", marker):
            # Mixed molecular+PK endpoints require more explicit granularity.
            return out, domain
        if _has(r"\b(?:predicted|simulated|modeled|modelled)\b", finding):
            return out, domain
        out.update(kg_entity_kind_override="pharmacokinetic_parameter", graph_entity_label="Concentration",
                   pk_relationship_type="exposure_characterized", pk_relationship_label="exposure characterized",
                   pk_graph_object_kind="parent_or_analyte_exposure", pk_graph_object_label=marker,
                   pk_or_exposure_parameter=marker, primary_graph_anchor_kind="pharmacokinetic_parameter")
        out["measured_endpoint_aggregate_analytes"] = aggregate
        out["measured_endpoint_observation_kind"] = "combined_analyte_concentration" if aggregate else "measured_drug_concentration"
        if aggregate:
            # A parent-drug exposure does not make the sum of parent and
            # metabolites an estimate for that parent alone.
            out["graph_admission_status"] = "paper_detail"
            out["graph_admission_reason"] = "combined_analyte_concentration_not_single_drug"
        return _record(out, row, "pharmacokinetics_exposure", "explicit_in_vivo_drug_concentration",
                       ("specific_readout_or_marker", "pk_or_exposure_parameter", "metabolite_or_analyte", "matrix", "population_or_system"))
    return out, domain
