"""Admission boundaries for the contribution actually reported in one item.

Use explicit structured roles first. Historical fallbacks require positive
same-item descriptions; neither a paper title nor a missing treatment word is
evidence that a measured drug effect is absent. Preserve the complete item in
detail rather than changing its scientific values or discarding the paper.
"""
from __future__ import annotations
import re
from pipeline.extract.io_utils import normalize

VERSION = "evidence_contribution_roles_v1"
NON_EFFECT_ROLES = {
    "method_validation": "measurement_validation_not_drug_effect",
    "measurement_definition": "measurement_definition_not_drug_effect",
    "expert_judgment": "expert_judgment_not_measured_drug_effect",
    "model_projection": "model_projection_not_observed_drug_effect",
    "reference_pattern_comparison": "reference_pattern_not_exposure_effect",
    "previously_reported_result": "cited_result_not_original_primary_evidence",
}

def contribution_role(row: dict, domain: str) -> tuple[str, str]:
    explicit = normalize(row.get("evidence_role", ""))
    if explicit in NON_EFFECT_ROLES:
        return explicit, "structured_evidence_role"
    contribution = normalize(row.get("source_contribution", ""))
    if contribution == "previously_reported" and normalize(row.get("evidence_type", "")) != "review_evidence":
        return "previously_reported_result", "structured_source_contribution"
    statement = normalize(row.get("finding_summary", "")) or normalize(row.get("support", ""))
    if not statement:
        return "", ""
    if domain in {"clinical_outcome", "safety_tolerability", "cognitive_behavioral", "subjective_experience", "brain_system"}:
        if re.match(r"\s*(?:the )?(?:experts|panellists|panelists|Delphi participants)\s+(?:rated|ranked|identified|endorsed|described|recommended|considered)\b", statement, re.I):
            return "expert_judgment", "explicit_expert_ratings_in_finding"
        design = ' '.join(normalize(row.get(k,'')) for k in ('study_design','data_source_or_study_design'))
        if (re.search(r'\bDelphi\b',design,re.I)
                and re.search(r'\b(?:experts?|ratings?|importance|consensus|thematic)\b',design,re.I)
                and not re.search(r'\b(?:randomi[sz]ed|clinical trial|patient cohort)\b',design,re.I)):
            return 'expert_judgment','explicit_item_delphi_rating_design'
        exposure = " ".join(normalize(row.get(k, "")) for k in
                            ("compound_or_intervention", "intervention_or_exposure", "compound_or_exposure"))
        if re.search(r"(?:similarity coefficient|dysconnectivity pattern|connectivity template)", exposure, re.I) and re.search(r"\b(?:similarity|pattern|template)\b", statement, re.I):
            return "reference_pattern_comparison", "structured_template_exposure"
    if domain == "clinical_outcome":
        # Improvement in a validation cohort can be a real measured result.
        # Match an instrument-property statement, not a scale merely being used.
        validity = re.search(r"(?:showed|demonstrated|had)\s+(?:high |good |excellent |strong )?(?:internal consistency|reliability|convergent validity|criterion validity)|study validates a measure|factor structure|test[- ]retest reliability", statement, re.I)
        measured_change = re.search(r"(?:symptoms?|depression|MADRS|HAM[- ]?D|scores?)\s+(?:were |was |significantly )?(?:decreased|reduced|improved|lowered)|(?:decrease|reduction|improvement)\s+(?:in|of)\s+(?:depressive symptoms|depression severity)", statement, re.I)
        # A validation paper can also report a genuine null treatment contrast.
        # Keep that result; absence of improvement is still an observed outcome.
        measured_contrast = re.search(r"(?:treatment[- ]arm|between[- ]group|between treatment|placebo|control group).{0,70}(?:effect|difference|outcome)|(?:effect|difference).{0,70}(?:treatment[- ]arm|between[- ]group|placebo|control group)", statement, re.I)
        if validity and not measured_change and not measured_contrast:
            return "method_validation", "instrument_property_not_symptom_change"
        if re.search(r"represented meaningful improvement|meaningful change threshold|minim(?:um|ally) clinically important difference|meaningful improvement anchored", statement, re.I) and re.search(r"(?:scale|score|QIDS|MADRS|PGI)", statement, re.I):
            return "measurement_definition", "explicit_scale_threshold_definition"
        if re.search(r"\b(?:decision[- ]analytic model|model projections?|projected)\b", statement, re.I) and re.search(r"\b(?:QALYs?|quality[- ]adjusted life|costs?|costing)\b", statement, re.I):
            return "model_projection", "explicit_economic_model_projection"
    return "", ""

def admission_boundary(row: dict, domain: str) -> dict:
    role, basis = contribution_role(row, domain)
    if role not in NON_EFFECT_ROLES:
        return {}
    # Public/provider views and recommended delivery practices are legitimate
    # in these domains. Their graph meaning does not claim a patient drug effect.
    if role in {'expert_judgment','method_validation','measurement_definition'} and domain in {'real_world_public_health','intervention_context'}:
        return {}
    if role == "model_projection" and domain not in {"clinical_outcome", "safety_tolerability", "cognitive_behavioral", "subjective_experience"}:
        return {}
    # Review synthesis legitimately discusses prior findings; the rule targets
    # the primary effect projection, not the existence of a review relationship.
    if normalize(row.get("source_family", "")) == "secondary_literature" or normalize(row.get("evidence_type", "")) in {"review_evidence", "meta_analysis_evidence"}:
        return {}
    return {"evidence_role": role, "evidence_role_resolution_version": VERSION,
            "evidence_role_resolution_basis": basis,
            "graph_admission_status": "paper_detail", "graph_admission_reason": NON_EFFECT_ROLES[role]}

def economic_projection_fields(row: dict, domain: str) -> dict:
    role,basis=contribution_role(row,domain)
    if domain!="clinical_outcome" or role!="model_projection":return {}
    return {"domain":"real_world_public_health","domain_route":"real_world_public_health","dataset":"real_world_public_health",
            "kg_entity_kind_override":"public_health_measure","graph_entity_label":"Economic & resource impacts",
            "public_health_topic_category":"Economic & resource impacts",
            "public_health_measure":normalize(row.get("outcome_measure", "")) or "Projected costs and quality-adjusted life years",
            "evidence_role":"model_projection","evidence_role_resolution_version":VERSION,
            "evidence_role_resolution_basis":basis,"data_source_type":"other_or_unclear"}
