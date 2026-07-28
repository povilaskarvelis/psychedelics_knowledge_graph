#!/usr/bin/env python3
"""Build the normalized evidence-table backbone for the knowledge graph.

This stage keeps the extraction JSON/JSONL files as the raw audit trail, but
materializes normalized finding rows as columnar tables that can power multiple
UI projections.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Iterable

import pandas as pd

try:
    from pipeline.extract.clinical_comparator import normalize_clinical_comparator
    from pipeline.extract.clinical_followup_window import normalize_clinical_followup_window
    from pipeline.extract.assay_family import normalize_assay_family
    from pipeline.extract.io_utils import SYSTEM_NORMALIZATION, normalize, write_json
    from pipeline.ingest.materialize_candidate_funding import (
        DEFAULT_DOI_ALIAS_REGISTRY,
        load_doi_aliases,
        materialize_funding,
        source_sha256,
        subset_assertions_for_papers,
    )
    from pipeline.ingest.materialize_paper_open_science import (
        materialize_open_science,
        subset_open_science_assertions,
    )
    from pipeline.kg.compound_combinations import (
        aliases_for_components,
        canonical_components,
        named_combination_for_components,
        named_combination_from_text,
    )
    from pipeline.kg.convert_routed_extractions_to_evidence_rows import apply_graph_subject, evidence_design_for, normalized_result_direction
    from pipeline.kg.pk_relationships import add_pk_relationship_fields, pk_edge_relation_type, pk_graph_entity_kind, pk_graph_entity_label, pk_pharmacodynamic_target
    from pipeline.kg.use_contexts import (
        use_context_definition,
        use_context_label_from_text,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from pipeline.extract.clinical_comparator import normalize_clinical_comparator
    from pipeline.extract.clinical_followup_window import normalize_clinical_followup_window
    from pipeline.extract.assay_family import normalize_assay_family
    from pipeline.extract.io_utils import SYSTEM_NORMALIZATION, normalize, write_json
    from pipeline.ingest.materialize_candidate_funding import (
        DEFAULT_DOI_ALIAS_REGISTRY,
        load_doi_aliases,
        materialize_funding,
        source_sha256,
        subset_assertions_for_papers,
    )
    from pipeline.ingest.materialize_paper_open_science import (
        materialize_open_science,
        subset_open_science_assertions,
    )
    from pipeline.kg.compound_combinations import (
        aliases_for_components,
        canonical_components,
        named_combination_for_components,
        named_combination_from_text,
    )
    from pipeline.kg.convert_routed_extractions_to_evidence_rows import apply_graph_subject, evidence_design_for, normalized_result_direction
    from pipeline.kg.pk_relationships import add_pk_relationship_fields, pk_edge_relation_type, pk_graph_entity_kind, pk_graph_entity_label, pk_pharmacodynamic_target
    from pipeline.kg.use_contexts import (
        use_context_definition,
        use_context_label_from_text,
    )


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EXTRACTION_DIR = ROOT / "data" / "processed" / "extraction"
DEFAULT_OUT_DIR = ROOT / "data" / "processed" / "kg"
DEFAULT_ROUTED_KG_RUN_ROOT = ROOT / "data" / "processed" / "kg_routed_runs"
DEFAULT_REGISTRY_PATH = ROOT / "data" / "curated" / "entity_registry.json"
DEFAULT_DISORDER_ALIASES_PATH = ROOT / "schema" / "disorder_canonicalization.json"
DEFAULT_NODE_VOCABULARY_PATH = ROOT / "schema" / "kg_node_vocabularies.json"
DEFAULT_FUNDING_ASSERTIONS_PATH = ROOT / "data" / "processed" / "corpus" / "paper_funding.parquet"
DEFAULT_FUNDING_ATTEMPTS_PATH = (
    ROOT / "data" / "processed" / "corpus" / "paper_funding_provider_attempts.parquet"
)
DEFAULT_OPEN_SCIENCE_FEATURES_PATH = (
    ROOT / "data" / "processed" / "corpus" / "paper_open_science_features.parquet"
)
DEFAULT_OPEN_SCIENCE_ASSERTIONS_PATH = (
    ROOT / "data" / "processed" / "corpus" / "paper_open_science_assertions.parquet"
)
KG_TABLE_VERSION = "0.2"
MOLECULAR_SUBTOPIC_TAXONOMY_VERSION = "molecular_subtopics_v3_20260722"

ROUTED_GRAPH_SOURCES = {
    "routed_extractions": {
        "path": DEFAULT_EXTRACTION_DIR / "routed_evidence_rows.json",
        "domain": "routed",
        "dataset": "routed",
        "default_evidence_type": "primary_evidence",
        "skip_audit": True,
    },
    "routed_clinical_endpoints": {
        "path": DEFAULT_EXTRACTION_DIR / "routed_evidence_rows.json",
        "domain": "routed",
        "dataset": "routed",
        "default_evidence_type": "primary_evidence",
        "transform": "clinical_endpoints",
        "skip_audit": True,
    },
}

GRAPH_SOURCE_PRESETS = {
    "routed": ROUTED_GRAPH_SOURCES,
}
GRAPH_SOURCES = ROUTED_GRAPH_SOURCES
ROUTED_SOURCE_NAMES = {"routed_extractions", "routed_clinical_endpoints"}

OUTCOME_MEASURE_PATTERNS = [
    ("MADRS-SI", [r"\bmadrs\s*[- ]?\s*si\b"]),
    ("MADRS", [r"\bmadrs\b", r"montgomery\s+asberg"]),
    ("HAM-D", [r"\bham\s*[- ]?\s*d\b", r"\bhdrs\b", r"hamilton\s+depression"]),
    ("PHQ-9", [r"\bphq\s*[- ]?\s*9\b", r"patient\s+health\s+questionnaire\s*[- ]?\s*9"]),
    ("BDI", [r"\bbdi\b", r"beck\s+depression\s+inventory"]),
    ("QIDS", [r"\bqids\b", r"quick\s+inventory\s+of\s+depressive"]),
    ("C-SSRS", [r"\bc\s*[- ]?\s*ssrs\b", r"columbia\s+suicide\s+severity"]),
    ("BSS", [r"\bbss\b", r"beck\s+scale\s+for\s+suicidal"]),
    ("SSI", [r"\bssi\b", r"scale\s+for\s+suicidal\s+ideation"]),
    ("PCL-5", [r"\bpcl\s*[- ]?\s*5\b"]),
    ("CAPS-5", [r"\bcaps\s*[- ]?\s*5\b", r"clinician\s+administered\s+ptsd"]),
    ("IES-R", [r"\bies\s*[- ]?\s*r\b", r"impact\s+of\s+events?\s+scale\s*[- ]?\s*revised"]),
    ("DASS-21", [r"\bdass\s*[- ]?\s*21\b", r"depression\s+anxiety\s+stress\s+scales?\s*[- ]?\s*21"]),
    ("BSI-18", [r"\bbsi\s*[- ]?\s*18\b", r"brief\s+symptom\s+inventory\s*[- ]?\s*18"]),
    ("HADS-A", [r"\bhads\s*[- ]?\s*a\b", r"hospital\s+anxiety\s+and\s+depression\s+scale\s*[- ]?\s*anxiety"]),
    ("HADS-D", [r"\bhads\s*[- ]?\s*d\b", r"hospital\s+anxiety\s+and\s+depression\s+scale\s*[- ]?\s*depression"]),
    ("HADS", [r"\bhads\b", r"hospital\s+anxiety\s+and\s+depression\s+scale"]),
    ("WEMWBS", [r"\bwemwbs\b", r"warwick\s+edinburgh\s+mental\s+well\s+being"]),
    ("DPES", [r"\bdpes\b", r"dispositional\s+positive\s+emotion"]),
    ("SHAPS", [r"\bshaps\b", r"snaith\s+hamilton\s+pleasure\s+scale"]),
    ("TEPS", [r"\bteps\b", r"temporal\s+experience\s+of\s+pleasure\s+scale"]),
    ("SDS", [r"\bsds\b", r"sheehan\s+disability\s+scale"]),
    ("GAD-7", [r"\bgad\s*[- ]?\s*7\b", r"generalized\s+anxiety\s+disorder\s*[- ]?\s*7"]),
    ("HAM-A", [r"\bham\s*[- ]?\s*a\b", r"hamilton\s+anxiety"]),
    ("STAI", [r"\bstai\b", r"state\s+trait\s+anxiety\s+inventory"]),
    ("LSAS", [r"\blsas\b", r"liebowitz\s+social\s+anxiety\s+scale"]),
    ("ISI", [r"\bisi\b", r"insomnia\s+severity\s+index"]),
    ("EPDS", [r"\bepds\b", r"edinburgh\s+postnatal\s+depression\s+scale", r"edinburgh\s+postpartum\s+depression\s+scale"]),
    ("AUDIT", [r"\baudit\b", r"alcohol\s+use\s+disorders?\s+identification\s+test"]),
    ("TLFB", [r"\btlfb\b", r"timeline\s+follow\s*back"]),
    ("VAS", [r"\bvas\b", r"visual\s+analog(?:ue|ical)?\s+scale"]),
    ("NRS", [r"\bnrs\b", r"numeric(?:al)?\s+rating\s+scale"]),
    ("BPI", [r"\bbpi\b", r"brief\s+pain\s+inventory"]),
    ("FLACC", [r"\bflacc\b", r"face\s+legs\s+activity\s+cry\s+(?:and\s+)?consolability"]),
    ("Y-BOCS", [r"\by\s*[- ]?\s*bocs\b", r"yale\s+brown\s+obsessive\s+compulsive"]),
    ("CADSS", [r"\bcadss\b", r"clinician\s+administered\s+dissociative\s+states?\s+scale"]),
    ("CGI-S", [r"\bcgi\s*[- ]?\s*s\b", r"clinical\s+global\s+impression\s*[- ]?\s*severity"]),
    ("CGI-I", [r"\bcgi\s*[- ]?\s*i\b", r"clinical\s+global\s+impression\s*[- ]?\s*improvement"]),
    ("CGI", [r"\bcgi\b", r"clinical\s+global\s+impression"]),
    ("YMRS", [r"\bymrs\b", r"young\s+mania\s+rating\s+scale"]),
    ("PANSS", [r"\bpanss\b", r"positive\s+and\s+negative\s+syndrome\s+scale"]),
    ("BPRS", [r"\bbprs\b", r"brief\s+psychiatric\s+rating\s+scale"]),
    ("IDS-SR", [r"\bids\s*[- ]?\s*sr\b", r"inventory\s+(?:of|for)\s+depressive\s+symptomatology\s*[- ]?\s*self\s+report"]),
]

PAPER_FIELDS = (
    "study_doi",
    "openalex_id",
    "study_title",
    "authors",
    "study_year",
    "study_journal",
    "publication_type",
    "publication_date",
    "publisher",
    "journal_issn",
    "journal_eissn",
    "language",
    "mesh_terms",
    "keywords",
    "funders",
    "grant_ids",
    "funding_metadata_status",
    "funding_providers",
    "funding_assertion_count",
    "funding_funder_count",
    "funding_award_count",
    "has_registered_trial",
    "registered_trial_ids",
    "registered_trial_urls",
    "registered_trial_count",
    "has_open_data",
    "open_data_resource_ids",
    "open_data_urls",
    "open_data_repositories",
    "open_data_resource_count",
    "has_shared_code",
    "shared_code_resource_ids",
    "shared_code_urls",
    "shared_code_repositories",
    "shared_code_resource_count",
    "has_preregistered",
    "preregistration_ids",
    "preregistration_urls",
    "preregistration_repositories",
    "preregistration_count",
    "open_science_features",
    "open_science_feature_count",
    "open_science_assertion_count",
    "open_science_evidence_providers",
    "open_science_evidence_source_types",
    "open_science_has_fulltext_evidence_source",
    "open_science_enrichment_status",
    "open_science_retrieval_run_id",
    "open_science_retrieved_at_utc",
    "trial_registry_ids",
    "study_design",
    "funding",
    "conflicts_of_interest",
    "risk_of_bias_summary",
    "source_access_level",
    "open_access_is_oa",
    "open_access_status",
    "open_access_url",
    "unpaywall_is_oa",
    "unpaywall_oa_status",
    "unpaywall_license",
)

CLAIM_FIELDS = (
    "claim_type",
    "graph_subject_label",
    "graph_subject_kind",
    "graph_subject_source_field",
    "atomic_compound_candidate",
    "graph_overview_subject_label",
    "graph_overview_subject_kind",
    "graph_overview_subject_reason",
    "graph_overview_subjects_json",
    "graph_use_context_projections_json",
    "extraction_warnings",
    "raw_entity_label",
    "entity_role",
    "clinical_context_condition",
    "graph_entity_label",
    "graph_entity_type",
    "graph_parent_label",
    "graph_parent_kind",
    "graph_parent_entity_id",
    "graph_exclusion_reason",
    "mechanism_type",
    "assay_type",
    "assay_family",
    "assay_family_normalized",
    "modality",
    "modality_or_evidence_type",
    "readout",
    "readout_or_measure",
    "action_type",
    "affinity_type",
    "affinity_value",
    "affinity_unit",
    "species",
    "model_or_system",
    "system",
    "outcome_type",
    "outcome_domain",
    "result_direction",
    "result_direction_normalized",
    "outcome_measure",
    "outcome_measure_normalized",
    "population",
    "sample_size_total",
    "sample_size_by_arm",
    "comparator",
    "comparator_normalized",
    "follow_up_duration",
    "follow_up_window_normalized",
    "intervention_or_exposure",
    "condition_or_indication",
    "population_or_subgroup",
    "population_model_category",
    "study_design_category",
    "evidence_design",
    "administration_route",
    "dosing_schedule",
    "session_context",
    "graph_construct_label",
    "construct_family",
    "raw_task_or_measure",
    "cognitive_behavioral_graph_label",
    "subjective_experience_graph_label",
    "public_health_graph_label",
    "molecular_effect_label",
    "molecular_effect_category",
    "molecular_finding_subtopic",
    "specific_readout_or_marker",
    "mechanistic_relationship_type",
    "public_health_topic_category",
    "public_health_measure",
    "real_world_use_context",
    "data_source_type",
    "exposure_or_policy",
    "exposure_or_intervention",
    "setting",
    "estimate_value",
    "estimate_unit",
    "association_or_trend",
    "time_window",
    "data_source_or_study_design",
    "comparison_or_reference_group",
    "policy_or_practice_implication",
    "compound_or_analyte",
    "primary_graph_anchor_kind",
    "pharmacokinetic_display_label",
    "pk_relationship_type",
    "pk_relationship_label",
    "pk_graph_object_kind",
    "pk_graph_object_label",
    "analyte_type",
    "metabolite_or_analyte",
    "matrix",
    "matrix_or_sample_type",
    "pk_or_exposure_parameter",
    "value",
    "unit",
    "route_of_administration",
    "sampling_time_or_window",
    "study_design",
    "dose_standardization_or_equivalence",
    "comparator_or_reference",
    "co_exposure_or_modifier",
    "metabolic_or_transport_target",
    "metabolic_or_transport_pathway",
    "experimental_system_category",
    "model_or_method",
    "interaction_or_potentiation_context",
    "exposure_response_or_pk_effect",
    "exposure_response_implication",
    "synthesis_interpretation",
    "dose",
    "route",
    "session_count_or_duration",
    "primary_outcome",
    "assessment_timepoint",
    "effect_size",
    "p_value",
    "confidence_interval",
    "meta_analysis_result_role",
    "meta_analysis_primary_subject_area",
    "meta_analysis_subject_areas",
    "meta_analysis_study_count",
    "meta_analysis_effect_or_experiment_count",
    "meta_analysis_dataset_or_comparison_count",
    "meta_analysis_overall_study_count",
    "meta_analysis_overall_effect_or_experiment_count",
    "meta_analysis_overall_dataset_or_comparison_count",
    "meta_analysis_evidence_design_summary",
    "meta_analysis_search_end_date",
    "meta_analysis_effect_metric",
    "meta_analysis_interval_type",
    "meta_analysis_interval_lower",
    "meta_analysis_interval_upper",
    "meta_analysis_standard_error",
    "heterogeneity_i_squared",
    "heterogeneity_tau_squared",
    "heterogeneity_q_statistic",
    "heterogeneity_q_p_value",
    "heterogeneity_prediction_interval",
    "heterogeneity_interpretation",
    "meta_analysis_analysis_type",
    "meta_analysis_subgroup_or_moderator",
    "meta_analysis_regression_coefficient",
    "meta_analysis_sensitivity_method",
    "network_treatment_a",
    "network_treatment_b",
    "network_reference_treatment",
    "network_evidence_type",
    "network_ranking_metric",
    "network_ranking_value",
    "network_inconsistency_assessment",
    "network_transitivity_assessment",
    "adverse_events",
    "risk_of_bias_summary",
    "evidence_level",
    "support",
    "confidence",
    "needs_human_review",
    "supporting_quote",
    "evidence_location",
    "evidence_locator",
    "paper_assessment_route",
    "source_item_type",
    "source_item_index",
    "coverage_type",
    "coverage_focus",
    "coverage_focus_normalized",
    "source_type",
    "source_family",
    "paper_type",
    "review_contribution_type",
    "review_design_category",
    "access_level",
    "evidence_strength",
    "notes",
    "normalization_status",
    "normalization_notes",
    "compound_original",
    "target_original",
    "disorder_original",
    "graph_entity_original",
    "compound_match_type",
    "entity_match_type",
    "compound_registry_status",
    "entity_registry_status",
    "kg_entity_kind_override",
    "endpoint_label_source",
    "graph_admission_status",
    "graph_admission_reason",
    "proposition_group_id",
    "proposition_conflict_group_id",
    "direction_consistency",
    "proposition_duplicate_count",
)
EXPERIMENTAL_SYSTEM_METADATA_DOMAINS = {
    "molecular_target",
    "molecular_pathway_readout",
    "brain_system",
    "pharmacokinetics_exposure",
}
CLINICAL_METADATA_DOMAINS = {"clinical_outcome"}
EXPERIMENTAL_SYSTEM_TEXT_FIELDS = (
    "experimental_system_category",
    "population_model_category",
    "system",
    "model_or_system",
    "model_system",
    "species",
    "species_or_cell_line",
    "population",
    "assay_type",
    "assay_or_method",
    "assay_family",
)
SYSTEM_IN_VITRO_RE = re.compile(
    r"\b(in[- ]?vitro|cell culture|cultures?|cell line|hek[- ]?\d*|cho cells?|recombinant|transfected|"
    r"expressing recombinant|cultured (?:neurons?|cells?))\b",
    re.IGNORECASE,
)
SYSTEM_EX_VIVO_RE = re.compile(
    r"\b(ex[- ]?vivo|slice(?:s)?|brain tissue|tissue homogenate|homogenate|synaptosome\w*|"
    r"membrane(?:s)?|particulate preparation\w*|postmortem|dissected)\b",
    re.IGNORECASE,
)
SYSTEM_CLINICAL_RE = re.compile(
    r"\b(clinical trial|clinical study|patients?|participants?|volunteers?|healthy subjects?|healthy adults?|"
    r"human subjects?|humans?)\b",
    re.IGNORECASE,
)
SYSTEM_IN_VIVO_RE = re.compile(
    r"\b(in[- ]?vivo|animal model|mouse|mice|rat|rats|rodent\w*|zebrafish|pig|pigs|porcine|"
    r"primate\w*|monkey\w*|drosophila|maternal deprivation|social defeat|freely moving|awake rats?)\b",
    re.IGNORECASE,
)
PUBLIC_HEALTH_CONTEXT_FIELDS = (
    "data_source_type",
    "study_design_category",
    "public_health_topic_category",
    "public_health_measure",
    "graph_entity_label",
    "raw_entity_label",
    "entity_label",
    "exposure_or_policy",
    "exposure_or_intervention",
    "population",
    "population_or_setting",
    "setting",
    "study_design",
    "data_source_or_study_design",
    "effect_or_statistic",
    "estimate_unit",
    "association_or_trend",
    "time_window",
    "finding_summary",
    "study_title",
    "dose",
    "support",
    "supporting_quote",
)
PUBLIC_HEALTH_TOPIC_CONTEXT_FIELDS = (
    "public_health_measure",
    "exposure_or_policy",
    "exposure_or_intervention",
    "population",
    "population_or_setting",
    "setting",
    "study_design",
    "data_source_or_study_design",
    "effect_or_statistic",
    "estimate_unit",
    "association_or_trend",
    "time_window",
    "finding_summary",
    "study_title",
    "support",
    "supporting_quote",
)
PUBLIC_HEALTH_TOPIC_MEASURE_FIELDS = (
    "public_health_measure",
    "effect_or_statistic",
    "estimate_unit",
    "association_or_trend",
)
PUBLIC_HEALTH_USE_CONTEXT_FIELDS = (
    "real_world_use_context",
    "compound",
    "compound_original",
    "compound_or_exposure",
    "public_health_measure",
    "exposure_or_policy",
    "exposure_or_intervention",
    "population",
    "population_or_setting",
    "setting",
    "study_design",
    "data_source_or_study_design",
    "finding_summary",
    "study_title",
    "support",
    "supporting_quote",
)
PUBLIC_HEALTH_STRICT_PROBLEMATIC_USE_RE = re.compile(
    r"\b(misuse|abuse liability|abuse potential|dependen\w*|addict\w*|diversion|nonmedical|non[- ]medical|"
    r"substance use disorder|use disorder|sud\b|drug abuse|drug dependence|alcohol abuse|"
    r"problematic use patterns?|compulsive use|obsessive relationship|over[- ]?eager use|"
    r"tolerance escalation|withdrawal syndrome|use despite harm)\b",
    re.IGNORECASE,
)
PUBLIC_HEALTH_TOPIC_RULES = (
    (
        "Drug composition & adulteration",
        re.compile(
            r"\b(adulter\w*|substitut\w*|mislabel\w*|unexpected (?:drug|substance|detection)|"
            r"substance composition|product composition|chemical composition|purity|potency|"
            r"native alkaloid concentration|seized samples?|amnesty bins?|counterfeit|"
            r"drug checking accuracy|concordance between expected and detected)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Acute harms & healthcare use",
        re.compile(
            r"\b(poison[- ]?cent(?:er|re)s?|poison control|emergency|ed visit|emergency presentation|"
            r"emergency medical treatment|hospitali[sz]|intensive care|icu|acute intoxication|intoxication|"
            r"overdose|acute toxic\w*|adverse events?|serious adverse|fatalit\w*|fatal poisoning|"
            r"all[- ]cause mortality|completed suicide|suicidal ideation|suicidality|"
            r"healthcare utilization|healthcare use|medical treatment for adverse)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Problematic use & dependence",
        PUBLIC_HEALTH_STRICT_PROBLEMATIC_USE_RE,
    ),
    (
        "Treatment effectiveness & care outcomes",
        re.compile(
            r"\b(real[- ]world (?:clinical )?(?:treatment|effectiveness)|treatment response|response rate|"
            r"response and remission|remission rate|clinical improvement|treatment completion|"
            r"treatment continuation|treatment discontinuation|discontinued treatment|"
            r"treatment persistence|treatment adherence|care outcome|line of therapy|"
            r"physician[- ]reported reason for discontinuation)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Economic & resource impacts",
        re.compile(
            r"\b(cost[- ]effectiveness|cost effectiveness|incremental cost[- ]effectiveness ratio|icer\b|"
            r"cost per remitter|cost per qaly|qalys?|quality[- ]adjusted life years?|cost savings?|"
            r"healthcare costs?|economic impact|economic burden|resource use|resource utilization|"
            r"budget impact|payer perspective|workforce efficiency|disability days?|productivity|"
            r"treatment costs?|cost per session)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Access & equity",
        re.compile(
            r"\b(access barriers?|barriers? to (?:care|treatment|services?)|treatment access|service access|"
            r"treatment availability|service availability|geographic access|early[- ]access|insurance coverage|"
            r"health equity|equity|inequit\w*|disparit\w*|ethnoracial|racial inclusion|representation|"
            r"socioeconomic(?:ally)? advantaged|"
            r"social determinants|underserved|affordability|claim approval|prior authorization|"
            r"reimbursement|coverage approval|right to health|upward mobility)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Implementation & acceptability",
        re.compile(
            r"\b(implementation|service delivery|care delivery|delivery model|acceptability|appropriate(?:ness)?|"
            r"feasibility|provider attitudes?|clinician attitudes?|stakeholder attitudes?|willingness to (?:offer|"
            r"provide|participate)|prescrib\w*|certified treatment centers?|provider training|workforce training|"
            r"social workers?|psychiatrists?|practice readiness|implementation barrier|clinical adoption|"
            r"widespread adoption|therapeutic acceptance|treatment algorithms?|clinical guidelines?|"
            r"standards? of care|healthcare integration)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Ethics & governance",
        re.compile(
            r"\b(ethic\w*|governance|informed consent|research consent|autonomy|cultural appropriation|"
            r"indigenous|distributive justice|conflicts? of interest|research subject protections?|"
            r"participant protections?|exploitation|misconduct|sexual violations?|cognitive liberty|"
            r"human rights?|power dynamics?)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Commercialization & public communication",
        re.compile(
            r"\b(commerciali[sz]\w*|commodification|venture capital|for[- ]profit|patents?|"
            r"psychedelic industry|wellness (?:industry|market|sector|products?)|marketing|media hype|public hype|"
            r"public misinterpretation|public advocacy|social media|mislead(?:ing)? (?:patients?|public|"
            r"health professionals?)|online information|controversy|controversial|stigma|de[- ]?stigmat\w*|"
            r"public perception|public acceptance|news media|mass media|social reaction|internet)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Environmental sustainability",
        re.compile(
            r"\b(conservation|over[- ]?harvest\w*|wild populations?|poaching|habitat loss|climate change|"
            r"anthropogenic pressures?|endangered|threatened species|harvesting pressure|ecological|"
            r"environmental sustainability|biodiversity|environmental pollution|chemical waste|"
            r"river systems?)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Policy & legal outcomes",
        re.compile(
            r"\b(policy|regulat\w*|legal status|legalization|legalisation|decriminal\w*|criminal\w*|"
            r"legal aspects?|legal controls?|legal precedent|legal implications?|legal ambiguity|laws?|"
            r"court|judicial|legislative|sentenc\w*|crime|arrest\w*|prison|incarcerat\w*|"
            r"scheduling|drug classification|politic\w*|"
            r"prohibition|international ban|un conventions?|controlled substances? act|schedule i|dea\b|"
            r"fda approval|tga\b|rems\b|off[- ]label|legislative reform|treaty obligations?|rulemaking|"
            r"hybrid psychedelic laws?|government agencies?|religious freedom|ministerial authorization|"
            r"workplace drug testing|drug testing guidelines?|civil liability|malpractice|war on drugs|"
            r"licensed supervised use|medical treatment status|public approval of legal)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Culture, religion & social context",
        re.compile(
            r"\b(cultural transformation|cultural history|counterculture|psychedelic subculture|"
            r"rave culture|club culture|religious use|religious practice|ayahuasca religions?|"
            r"entheogen use|social movement|social institutions?|social tolerance|"
            r"social and ideological processes|societal (?:health|cohesion|effects?)|"
            r"sociological consequences?|civilizational pedigree|historical and cultural shift|"
            r"psychedelic renaissance|psychedelic scene)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Harm reduction practices",
        re.compile(
            r"\b(harm[- ]?reduction|safer use|risk reduction|trip[- ]?sitter|sober sitter|babysitter|"
            r"drug information source|information seeking|checking before use|behavior change after (?:testing|"
            r"drug checking)|intended use behavior change|integration support|peer support|overdose prevention|"
            r"risk assessments?|control measures?|substance testing services?|drug screen\w*|urine drug tests?|"
            r"urine drug screen\w*|detection devices?|confirmatory testing)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Availability & market trends",
        re.compile(
            r"\b(cryptomarket|darknet|market availability|market trend|market share|purchase|purchasing|"
            r"easy to obtain|availability of (?:drugs?|substances?)|perceived availability|street price|"
            r"price trend|drug supply|drug seizures?|seized by law enforcement|online market|"
            r"recreational drug market|illicit drug market|clandestine distribution|retail availability)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Perceived benefits & harms",
        re.compile(
            r"\b(perceived benefit|perceived efficacy|perceived effect|perceived harm|perceived risk|"
            r"perceived unpleasant side effects|self[- ]reported (?:benefit|improvement|worsening)|"
            r"rated as (?:beneficial|helpful|harmful)|subjective appraisal|therapeutic benefit|"
            r"psychotherapeutic benefit|preventive efficacy|abortive efficacy)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Motivations & intentions",
        re.compile(
            r"\b(motivation(?:s)? for use|use motivation|reasons? for use|reason for use|purpose of use|"
            r"primary reason|intention(?:s)? to use|willingness to use|willingness to participate|"
            r"future use|desire to use|preference for use|likelihood of (?:recreational )?use|expectations? of use)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Predictors & correlates",
        re.compile(
            r"\b(predictors? of (?:psychedelic |drug )?use|correlates? of (?:psychedelic |drug )?use|"
            r"factors associated with (?:psychedelic |drug )?use|odds of (?:lifetime |past[- ]year )?use|"
            r"demographic differences? in use|risk factors? for (?:initiation|use)|determinants? of use)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Population use & trends",
        re.compile(
            r"\b(epidemiology|prevalence|incidence of (?:drug |psychedelic |substance )?use|lifetime use|"
            r"past[- ]year use|past 12[- ]month use|"
            r"past[- ]month use|use prevalence|population trend|drug use trends?|substance abuse trends?|"
            r"temporal trend|geographical distribution of use|"
            r"population[- ]normalised|population[- ]normalized|mass load|drug load|daily consumption per capita|"
            r"per inhabitant consumption|estimated daily consumption|population consumption|pndl|pnl|"
            r"wastewater[- ]based epidemiology|age of initiation)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Health & functioning outcomes",
        re.compile(
            r"\b(mental health|psychiatric|psychological distress|depression|anxiety|well[- ]?being|"
            r"quality of life|functioning|disability|cognitive (?:risk|outcome|function)|sleep quality|"
            r"urinary|urolog\w*|renal|morbidity|infectious complications?|health status|"
            r"infectious disease risk|health behavior|work[- ]related outcomes?|"
            r"symptom improvement|symptom worsening|mood change|nature relatedness|social functioning|"
            r"relationship quality|violence|intimate partner violence|sexual assault|public health (?:risk|harm)|"
            r"preventive medicine|long[- ]term health)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Use patterns & practices",
        re.compile(
            r"\b(use patterns?|pattern of use|frequency of use|use frequency|route of administration|"
            r"administration route|dose pattern|dosing pattern|first[- ]time use|regular use|chronic use|"
            r"co[- ]?use|polysubstance|poly[- ]?drug|polydrug|co[- ]ingest\w*|concomitant use|"
            r"number of substances|user profiles?|duration of use|use practices?|consumption pattern|"
            r"conventional illicit drug use|recreational drug use|drug sequencing|other substances)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Research landscape",
        re.compile(
            r"\b(research landscape|bibliometric|publication patterns?|publication bias|reporting bias|"
            r"publication volume|psychedelic (?:research|science|clinical trials?)|"
            r"(?:psilocybin|ketamine|ayahuasca) (?:clinical )?research|preclinical psychedelic research|"
            r"evidence base|quality of evidence|methodological (?:quality|limitations?|concerns?|weaknesses?)|"
            r"research funding|funding patterns?|research grants?|zero grants?|national institutes of health|nih\b|"
            r"research agenda|research priorit\w*|study design|"
            r"clinical trial design|underreporting|research bias|scientific evidence|"
            r"molecular dynamics simulations?|chemometric procedures?|drug education curricula?|"
            r"field research methodolog\w*)\b",
            re.IGNORECASE,
        ),
    ),
)
PUBLIC_HEALTH_TOPIC_LABELS = {label for label, _pattern in PUBLIC_HEALTH_TOPIC_RULES}
PUBLIC_HEALTH_LEGACY_AXIS_LABEL_KEYS = {
    "microdosing",
    "recreational use",
    "self treatment",
    "ceremonial retreat use",
    "polysubstance use",
    "clinical treatment",
    "prevalence and trends",
    "problematic use",
    "drug checking and adulteration",
    "emergency toxicology reports",
    "wastewater and market signals",
    "access to services",
    "legal criminal justice",
    "other naturalistic topic",
}
PUBLIC_HEALTH_LEGACY_TOPIC_FALLBACKS = {
    "microdosing": "Use patterns & practices",
    "recreational use": "Use patterns & practices",
    "self treatment": "Perceived benefits & harms",
    "ceremonial retreat use": "Use patterns & practices",
    "polysubstance use": "Use patterns & practices",
    "clinical treatment": "Treatment effectiveness & care outcomes",
    "prevalence and trends": "Population use & trends",
    "problematic use": "Problematic use & dependence",
    "drug checking and adulteration": "Drug composition & adulteration",
    "emergency toxicology reports": "Acute harms & healthcare use",
    "wastewater and market signals": "Population use & trends",
    "access to services": "Access & equity",
    "legal criminal justice": "Policy & legal outcomes",
    "other naturalistic topic": "Other real-world topics",
}
PUBLIC_HEALTH_RAW_TOPIC_FALLBACKS = {
    "epidemiology": "Population use & trends",
    "epidemiology and surveillance": "Population use & trends",
    "epidemiology and mental health": "Health & functioning outcomes",
    "epidemiology and risk factors": "Predictors & correlates",
    "use pattern": "Use patterns & practices",
    "use patterns": "Use patterns & practices",
    "use patterns and administration routes": "Use patterns & practices",
    "use patterns and drug sequencing": "Use patterns & practices",
    "use patterns and substance use reduction": "Use patterns & practices",
    "exposure pattern": "Use patterns & practices",
    "use patterns and motivations": "Motivations & intentions",
    "use patterns and subjective risk benefit": "Perceived benefits & harms",
    "use patterns and outcomes": "Health & functioning outcomes",
    "use patterns and treatment outcomes": "Health & functioning outcomes",
    "use patterns and neurobehavioral traits": "Health & functioning outcomes",
    "use patterns and work related outcomes": "Health & functioning outcomes",
    "use patterns and population level risk": "Health & functioning outcomes",
    "harm reduction": "Harm reduction practices",
    "harm reduction and service delivery": "Harm reduction practices",
    "harm reduction and use patterns": "Harm reduction practices",
    "use patterns and detection": "Harm reduction practices",
    "substance abuse detection": "Harm reduction practices",
    "access": "Access & equity",
    "access and equity": "Access & equity",
    "equity and access": "Access & equity",
    "equity": "Access & equity",
    "service delivery": "Implementation & acceptability",
    "service delivery and access": "Implementation & acceptability",
    "implementation and service delivery": "Implementation & acceptability",
    "service delivery and healthcare integration": "Implementation & acceptability",
    "service delivery and care preferences": "Implementation & acceptability",
    "workforce and training": "Implementation & acceptability",
    "policy": "Policy & legal outcomes",
    "policy and regulation": "Policy & legal outcomes",
    "abuse potential": "Problematic use & dependence",
    "abuse liability and misuse": "Problematic use & dependence",
    "population level safety": "Health & functioning outcomes",
    "population level risk benefit": "Health & functioning outcomes",
    "mental health and well being": "Health & functioning outcomes",
    "cognitive and behavioral impact": "Health & functioning outcomes",
    "health behavior": "Health & functioning outcomes",
    "public health impact and well being": "Health & functioning outcomes",
    "risk factors": "Predictors & correlates",
    "public perception and health communication": "Commercialization & public communication",
    "patient preferences and research priorities": "Motivations & intentions",
    "risk assessment": "Drug composition & adulteration",
}
PUBLIC_HEALTH_USE_CONTEXT_RULES = (
    ("Microdosing", re.compile(r"\bmicrodos\w*\b", re.IGNORECASE)),
    (
        "Recreational/nightlife",
        re.compile(r"\b(recreational|club[- ]going|nightlife|dance event|festival|rave|party)\b", re.IGNORECASE),
    ),
    (
        "Self-treatment",
        re.compile(
            r"\b(self[- ]?treat\w*|self[- ]?medicat\w*|medical reasons? for use|cluster headache|"
            r"busting method|healing intention|therapeutic intention)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Ceremonial/retreat",
        re.compile(r"\b(ceremon\w*|ritual\w*|retreat|shamanic|ayahuasca church|sacramental)\b", re.IGNORECASE),
    ),
    (
        "Polysubstance",
        re.compile(
            r"\b(polysubstance|poly[- ]?drug|polydrug|co[- ]?use|co[- ]ingest\w*|concomitant use|"
            r"additional substances?|combined use)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Clinical care",
        re.compile(
            r"\b(real[- ]world clinical|clinical practice|clinical treatment|outpatients?|inpatients?|"
            r"treatment centers?|treatment centres?|certified treatment centers?|medical ketamine|"
            r"intranasal esketamine|spravato|psychedelic[- ]assisted therap\w*)\b",
            re.IGNORECASE,
        ),
    ),
)
PUBLIC_HEALTH_LEGACY_USE_CONTEXT_BY_KEY = {
    "microdosing": "Microdosing",
    "recreational use": "Recreational/nightlife",
    "self treatment": "Self-treatment",
    "ceremonial retreat use": "Ceremonial/retreat",
    "polysubstance use": "Polysubstance",
    "clinical treatment": "Clinical care",
}
PUBLIC_HEALTH_DATA_SOURCE_TYPES = {
    "survey",
    "poison_center_toxicology",
    "wastewater",
    "drug_checking",
    "administrative_registry",
    "qualitative_interview",
    "observational_cohort",
    "other_or_unclear",
    "not_reported",
}
COGNITIVE_BEHAVIORAL_CONTEXT_FIELDS = (
    "graph_construct_label",
    "construct_family",
    "raw_task_or_measure",
    "graph_entity_label",
    "raw_entity_label",
    "entity_label",
    "construct_or_behavior",
    "behavior_or_task",
    "task_or_measure",
    "model_or_measure",
    "behavioral_context",
    "outcome_measure",
    "primary_outcome",
    "effect_or_statistic",
    "finding_summary",
    "study_title",
    "support",
    "supporting_quote",
)
COGNITIVE_BEHAVIORAL_MEASURE_FIELDS = (
    "raw_task_or_measure",
    "task_or_measure",
    "model_or_measure",
    "outcome_measure",
    "primary_outcome",
    "behavior_or_task",
    "construct_or_behavior",
)
WITHDRAWAL_CONDITION_CONTEXT_FIELDS = (
    "raw_task_or_measure",
    "task_or_measure",
    "model_or_measure",
    "outcome_measure",
    "primary_outcome",
    "behavior_or_task",
    "construct_or_behavior",
    "graph_entity_label",
    "raw_entity_label",
    "entity_label",
    "clinical_context_condition",
    "finding_summary",
    "study_title",
    "support",
    "supporting_quote",
)
WITHDRAWAL_ENDPOINT_RE = re.compile(
    r"\b(naloxone[- ]precipitated withdrawal|withdrawal signs?|withdrawal symptoms?|"
    r"withdrawal syndrome|withdrawal[- ]induced|abstinence syndrome|global withdrawal score|"
    r"somatic signs?|drug withdrawal|substance withdrawal|alcohol withdrawal|ethanol withdrawal|"
    r"opioid withdrawal|opiate withdrawal|nicotine withdrawal|cocaine withdrawal|"
    r"methamphetamine withdrawal|fentanyl withdrawal)\b",
    re.IGNORECASE,
)
OPIOID_WITHDRAWAL_CONTEXT_RE = re.compile(
    r"\b(opioid(?! receptor)|opiate|oxycodone|morphine|heroin|naloxone|fentanyl|buprenorphine)\b",
    re.IGNORECASE,
)
POLYSUBSTANCE_WITHDRAWAL_CONTEXT_RE = re.compile(r"\b(polysubstance|poly[- ]?substance|polydrug|poly[- ]?drug)\b", re.IGNORECASE)
COCAINE_WITHDRAWAL_CONTEXT_RE = re.compile(r"\bcocaine\b", re.IGNORECASE)
ALCOHOL_WITHDRAWAL_CONTEXT_RE = re.compile(r"\b(alcohol|ethanol)\b", re.IGNORECASE)
NICOTINE_WITHDRAWAL_CONTEXT_RE = re.compile(r"\b(nicotine|tobacco|smoking)\b", re.IGNORECASE)
METHAMPHETAMINE_WITHDRAWAL_CONTEXT_RE = re.compile(r"\bmethamphetamine\b", re.IGNORECASE)
GENERIC_SUBSTANCE_WITHDRAWAL_CONTEXT_RE = re.compile(r"\b(substance withdrawal|drug withdrawal)\b", re.IGNORECASE)
COGNITIVE_BEHAVIORAL_LABEL_FIELDS = (
    "graph_entity_label",
    "raw_entity_label",
    "entity_label",
    "construct_or_behavior",
    "behavior_or_task",
    "task_or_measure",
)
GENERIC_LOCOMOTOR_CONTEXT_RE = re.compile(
    r"\b(open[- ]field|locomotor|locomotion|distance traveled|distance moved|ambulatory|ambulation|rearing|"
    r"total activity|horizontal activity|photobeam)\b",
    re.IGNORECASE,
)
GENERIC_BEHAVIOR_NOT_GRAPHABLE_KEYS = {
    "exploratory behavior",
    "feeding behavior",
    "hyperactivity",
    "hyperlocomotion",
    "locomotion",
    "locomotor activity",
    "locomotor behavior",
    "motor activity",
    "motor behavior",
    "open field locomotor activity",
    "open field locomotion scores",
    "open field test",
    "open field",
    "psychomotor stimulation",
    "serotonin syndrome behavior",
    "sexual behavior",
    "stereotyped behavior",
    "stereotypy",
    "thermoregulation",
}
CONTROLLED_BEHAVIORAL_DETAIL_LABELS = {
    "arousal": "Arousal",
    "exploratory behavior": "Exploratory behavior",
    "feeding behavior": "Feeding behavior",
    "hyperactivity": "Locomotor activity",
    "hyperlocomotion": "Locomotor activity",
    "locomotion": "Locomotor activity",
    "locomotor activity": "Locomotor activity",
    "locomotor behavior": "Locomotor activity",
    "motor activity": "Motor activity",
    "motor behavior": "Motor activity",
    "open field locomotor activity": "Locomotor activity",
    "open field locomotion scores": "Locomotor activity",
    "open field test": "Locomotor activity",
    "open field": "Locomotor activity",
    "psychomotor stimulation": "Motor activity",
    "sleep wake behavior": "Sleep-wake behavior",
    "sleep-wake behavior": "Sleep-wake behavior",
    "stereotyped behavior": "Stereotyped behavior",
    "stereotypy": "Stereotyped behavior",
}
CONTROLLED_BEHAVIORAL_DETAIL_NODE_LABELS = set(CONTROLLED_BEHAVIORAL_DETAIL_LABELS.values())
BRAIN_MEASURE_NOT_GRAPHABLE_RE = re.compile(
    r"\b("
    r"mismatch negativity|mmn|p300|alpha power|delta power|theta power|gamma power|"
    r"bold response|lempel[- ]ziv|lzc|cbf|cerebral blood flow|"
    r"functional connectivity|glucose metabolism|grey matter volume|gray matter volume|"
    r"seizure duration|electric quantity|rem sleep latency|white matter bundle|"
    r"serotonin transporter binding|5[- ]?ht transporter density|receptor binding"
    r")\b",
    re.IGNORECASE,
)
BRAIN_MEASURE_GRAPH_RULES = (
    (
        re.compile(
            r"\b(functional connectivity|connectivity|coupling|coherence|connectome|within.network|between.network)\b",
            re.I,
        ),
        "Functional connectivity",
    ),
    (re.compile(r"\b(mismatch negativity|mmn)\b", re.I), "MMN"),
    (re.compile(r"\b(p300|p3a|p3b|novelty p3)\b", re.I), "P300"),
    (
        re.compile(
            r"\b(event.related potentials?|evoked potentials?|erp|p20|n40|p80|transcallosally evoked)\b",
            re.I,
        ),
        "ERP",
    ),
    (re.compile(r"\b(bold|blood oxygen.level dependent)\b", re.I), "BOLD response"),
    (re.compile(r"\b(cbf|blood flow|perfusion|arterial spin labell?ing|asl|pcasl)\b", re.I), "Cerebral blood flow"),
    (re.compile(r"\b(fdg|glucose metabolism|deoxyglucose|metabolic activity)\b", re.I), "Glucose metabolism"),
    (
        re.compile(
            r"\b(oscillat\w*|spectral power|power spectra|alpha (?:band )?power|alpha rhythm|"
            r"beta power|theta power|delta power|gamma power|eeg desynchronization|electrical energy)\b",
            re.I,
        ),
        "Oscillatory power",
    ),
    (re.compile(r"\b(receptor occupancy|binding potential|receptor availability|receptor binding|receptor density)\b", re.I), "Receptor occupancy"),
    (re.compile(r"\b(white matter|fractional anisotropy|diffusion tensor|dti|tract integrity)\b", re.I), "White matter integrity"),
    (re.compile(r"\b(grey matter|gray matter|brain volume|regional volume|cortical thickness|morphometry)\b", re.I), "Brain structure"),
    (re.compile(r"\b(signal complexity|lempel.ziv|lzc|entropy)\b", re.I), "Neural signal complexity"),
    (
        re.compile(
            r"\b(metastability|mutual information|information parity|pair correlation|hierarchical integration|"
            r"harmonic mode energy|structure.function coupling)\b",
            re.I,
        ),
        "Network dynamics",
    ),
    (
        re.compile(r"\b(functional gradient|cortical gradient|graph measures?|network topology)\b", re.I),
        "Network topology",
    ),
    (re.compile(r"\b(sleep architecture|sleep.wake|rem sleep|slow.wave sleep|sw sleep)\b", re.I), "Sleep architecture"),
)
BRAIN_MEASURE_COMPATIBLE_ENTITY_KINDS = {
    "biomarker_readout",
    "brain_measure",
    "brain_network",
    "neural_circuit",
}


def brain_measure_graph_label(value: object) -> str:
    text = normalize(value)
    return next((label for pattern, label in BRAIN_MEASURE_GRAPH_RULES if pattern.search(text)), "")
BROAD_BRAIN_SYSTEM_NOT_GRAPHABLE_KEYS = {
    "cerebral cortex",
    "cortex",
    "functional brain network",
    "neocortex",
}
COGNITIVE_BEHAVIORAL_RULES = (
    (
        "Global cognition",
        re.compile(
            r"\b(global cognitive|general cognitive|cognition \(all domains\)|cognitive outcome \(various\)|"
            r"neurocognitive functions?|neuropsychological (?:abilities|performance)|all cognitive domains)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Psychotomimetic effects",
        re.compile(
            r"\b(psychotomimetic|psychosis[- ]like|psychotic[- ]like|model psychosis|psychosis model|"
            r"schizophrenia[- ]like symptoms?|positive symptoms?|thought disorder|bprs|panss)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Fear extinction",
        re.compile(r"\b(fear extinction|extinction learning|extinction recall|extinction retrieval)\b", re.IGNORECASE),
    ),
    (
        "Drug discrimination",
        re.compile(
            r"\b(drug discrimination|discriminative stimulus|drug[- ]appropriate lever|drug[- ]lever|"
            r"substitution for|interoception)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Conditioned place preference",
        re.compile(r"\b(conditioned place preference|\bcpp\b|place preference)\b", re.IGNORECASE),
    ),
    (
        "Drug self-administration",
        re.compile(
            r"\b(self[- ]administration|two[- ]bottle|2bc|free[- ]choice|drug intake|alcohol intake|"
            r"ethanol intake|cocaine intake|morphine intake|opioid intake|consumption|drinking)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Craving",
        re.compile(
            r"\b(craving|craving[- ]like|drug craving|alcohol craving|cue[- ]induced craving|"
            r"urge to smoke|urge to use|urge to drink)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Drug cue reactivity",
        re.compile(
            r"\b((?:alcohol|cocaine|drug|ethanol|heroin|ketamine|methamphetamine|nicotine|opioid|smoking)"
            r"[- ]cue reactivity|reactivity to (?:alcohol|drug|smoking)[- ]related cues)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Drug reinstatement",
        re.compile(
            r"\b(reinstatement|reinstatement session|cue[- ]induced reinstatement|"
            r"priming[- ]induced reinstatement|drug[- ]induced reinstatement|"
            r"stress[- ](?:primed|induced) reinstatement)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Relapse",
        re.compile(
            r"\b(relapse|relapse[- ]like|anti[- ]relapse|alcohol deprivation effect|"
            r"return to (?:drug )?use|return to drinking|resumption of (?:drug )?use)\b|\bADE model\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Drug motivation",
        re.compile(
            r"\b(motivation for (?:alcohol|cocaine|drug|ethanol|fentanyl|heroin|methamphetamine|"
            r"nicotine|opioid)|drug motivation|motivation for drug reinforcement|"
            r"demand elasticity|economic demand for (?:alcohol|drugs?|opioids?))\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Drug seeking",
        re.compile(
            r"\b(drug[- ]seeking|alcohol seeking|ethanol seeking|cocaine seeking|"
            r"reconsolidation of alcohol[- ]related memories|abstinence self[- ]efficacy)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Head-twitch response",
        re.compile(
            r"\b(head[- ]?twitch|htr\b|hallucinogen[- ]like|hallucinogenic[- ]like|psychedelic[- ]like)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Sensorimotor gating",
        re.compile(r"\b(sensorimotor gating|prepulse inhibition|\bppi\b|startle response)\b", re.IGNORECASE),
    ),
    (
        "Motor coordination",
        re.compile(r"\b(motor coordination|rotarod|ataxia|dystaxia|gait|tremor|tremorigenic|balance)\b", re.IGNORECASE),
    ),
    (
        "Psychomotor sensitization",
        re.compile(r"\b(psychomotor sensitization|locomotor sensitization|sensitization)\b", re.IGNORECASE),
    ),
    (
        "Anhedonia",
        re.compile(
            r"\b(anhedonia|anhedonic|anti[- ]anhedonia|sucrose preference|hedonic capacity|"
            r"hedonic responsiveness|hedonic behavior|pleasure capacity|snaith[- ]hamilton|shaps)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Reward responsiveness",
        re.compile(
            r"\b(reward responsiveness|reward sensitivity|reward threshold|"
            r"intracranial self[- ]stimulation|icss|probabilistic reward task|reward response bias)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Reward learning",
        re.compile(
            r"\b(reward learning|appetitive learning|reward feedback learning|sign[- ]tracking|goal[- ]tracking|"
            r"reinforcement learning from reward|reward prediction learning)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Motivation",
        re.compile(
            r"\b(motivation|motivational processing|goal[- ]directed motivation|incentive motivation|"
            r"effort[- ]based motivation|progressive[- ]ratio break ?point|readiness to change)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Reward processing",
        re.compile(r"\b(reward processing|reward function|reward valuation|reward seeking|reinforcement processing)\b", re.IGNORECASE),
    ),
    (
        "Stress-coping behavior",
        re.compile(
            r"\b(forced swim|forced swimming|tail suspension|behavioral despair|antidepressant[- ]like|"
            r"depression[- ]like|depressive[- ]like|depression[- ]related|learned helplessness|"
            r"futility[- ]induced passivity|passivity assay|splash test)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Compulsivity",
        re.compile(
            r"\b(compulsivity|compulsive[- ]like behavior|obsessive[- ]compulsive[- ]like behavior|"
            r"anticompulsive[- ]like behavior|marble[- ]burying|marble burying|perseverative behavior)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Avoidance learning",
        re.compile(
            r"\b(active avoidance|passive avoidance|avoidance learning|one[- ]trial passive avoidance|"
            r"step[- ]down passive avoidance|step[- ]through(?: latency)?|shuttle[- ]?box)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Anxiety-like behavior",
        re.compile(
            r"\b(anxiety|anxiety[- ]like|anxiety behavior|anxiogenic|anxiolytic|elevated plus[- ]maze|"
            r"elevated plus maze|plus[- ]maze|\bepm\b|"
            r"elevated zero maze|\bezm\b|zero maze|open arms?|novelty[- ]suppressed feeding|\bnsft\b|"
            r"light[- ]dark|marble burying|bottom dwelling|center zone|center time|thigmotaxis|"
            r"defensive burying|neophagia|separation anxiety)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Threat avoidance",
        re.compile(r"\b(threat avoidance|approach[- ]avoidance|avoidance behavior|avoidance task)\b", re.IGNORECASE),
    ),
    (
        "Fear memory",
        re.compile(
            r"\b(fear memory|fear conditioning|conditioned fear|learned fear|contextual fear|"
            r"contextual fear conditioning|cued fear|cued fear conditioning|tone fear conditioning|"
            r"trace fear conditioning|conditioned freezing|freezing time|percentage time spent freezing|"
            r"freezing behavior|cfc|tfc)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Recognition memory",
        re.compile(r"\b(recognition memory|object recognition|novel object)\b", re.IGNORECASE),
    ),
    (
        "Spatial memory",
        re.compile(r"\b(spatial memory|spatial learning|morris water|cincinnati water|water maze|radial arm)\b", re.IGNORECASE),
    ),
    (
        "Working memory",
        re.compile(r"\b(working memory|spatial working memory|n[- ]back)\b", re.IGNORECASE),
    ),
    (
        "Autobiographical memory",
        re.compile(r"\b(autobiographical memory|autobiographical recollection|personal event memory)\b", re.IGNORECASE),
    ),
    (
        "Episodic memory",
        re.compile(r"\b(episodic memory|episodic recollection|episodic recall)\b", re.IGNORECASE),
    ),
    (
        "Verbal memory",
        re.compile(
            r"\b(verbal memory|verbal learning(?: and memory)?|word[- ]learning|word list (?:learning|recall)|"
            r"rey auditory verbal learning|california verbal learning|hopkins verbal learning|verbal recall)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Visuospatial memory",
        re.compile(r"\b(visuospatial memory|visual[- ]spatial memory|object[- ]location memory)\b", re.IGNORECASE),
    ),
    (
        "Visual memory",
        re.compile(r"\b(visual memory|visual learning and memory|visual paired[- ]association memory)\b", re.IGNORECASE),
    ),
    (
        "Semantic memory",
        re.compile(r"\b(semantic memory|semantic retrieval)\b", re.IGNORECASE),
    ),
    (
        "Prospective memory",
        re.compile(r"\b(prospective memory|prospective remembering)\b", re.IGNORECASE),
    ),
    (
        "Sensory memory",
        re.compile(r"\b(sensory memory|auditory sensory memory|sensory[- ]auditory memory)\b", re.IGNORECASE),
    ),
    (
        "Declarative memory",
        re.compile(r"\b(declarative memory|declarative learning)\b", re.IGNORECASE),
    ),
    (
        "Short-term memory",
        re.compile(r"\b(short[- ]term memory|immediate memory span)\b", re.IGNORECASE),
    ),
    (
        "Associative memory",
        re.compile(
            r"\b(associative memory|associative learning|paired[- ]associate memory|paired associative learning)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Conditioned taste aversion",
        re.compile(r"\b(conditioned taste aversion|taste aversion learning)\b", re.IGNORECASE),
    ),
    (
        "Self-related processing",
        re.compile(r"\b(self[- ]compassion|self[- ]criticism|self[- ]acceptance)\b", re.IGNORECASE),
    ),
    (
        "Memory consolidation",
        re.compile(r"\b(memory consolidation|consolidation of memory|overnight memory consolidation)\b", re.IGNORECASE),
    ),
    (
        "Memory retrieval",
        re.compile(r"\b(memory retrieval|retrieval of memory|memory recall)\b", re.IGNORECASE),
    ),
    (
        "Memory",
        re.compile(r"\b(memory|retrieval|consolidation|reconsolidation|autoshaping)\b", re.IGNORECASE),
    ),
    (
        "Creativity",
        re.compile(r"\b(creativity|creative thinking|divergent thinking|divergent association)\b", re.IGNORECASE),
    ),
    (
        "Decentering",
        re.compile(r"\b(decentering|decentring|cognitive defusion)\b", re.IGNORECASE),
    ),
    (
        "Mindfulness",
        re.compile(
            r"\b(mindfulness|mindful awareness|five facet mindfulness|FFMQ|"
            r"mindful attention awareness|MAAS|kentucky inventory of mindfulness|KIMS)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Psychological flexibility",
        re.compile(
            r"\b(psychological flexibility|psychological inflexibility|acceptance and action questionnaire|"
            r"AAQ[- ]?II|values[- ]congruent living|experiential avoidance)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Reversal learning",
        re.compile(
            r"\b(reversal learning|discrimination reversal|transition reversal|serial reversals?|"
            r"choice reversal|reversal phase)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Set shifting",
        re.compile(
            r"\b(set[- ]shifting|set shifting|attentional set[- ]shifting|extra[- ]?dimensional shift|"
            r"wisconsin card sorting|WCST|penn conditional exclusion|PCET)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Cognitive flexibility",
        re.compile(r"\b(cognitive flexibility|behavioral flexibility|cognitive rigidity|perseveration)\b", re.IGNORECASE),
    ),
    (
        "Inhibitory control",
        re.compile(r"\b(inhibitory control|inhibitory deficits?|response inhibition|impulsivity|impulsive action)\b", re.IGNORECASE),
    ),
    (
        "Attention",
        re.compile(r"\b(attention|attentional|5[- ]choice|5[- ]csrt|continuous performance|vigilance)\b", re.IGNORECASE),
    ),
    (
        "Executive function",
        re.compile(r"\b(executive function|executive functioning|decision[- ]making|planning|cognitive function)\b", re.IGNORECASE),
    ),
    (
        "Emotional processing",
        re.compile(r"\b(emotion recognition|emotion processing|emotional processing|emotional face|negative emotional)\b", re.IGNORECASE),
    ),
    (
        "Social cognition",
        re.compile(
            r"\b(social cognition|empathy|cognitive empathy|emotional empathy|theory of mind|"
            r"reading the mind|multifaceted empathy|movie for the assessment of social cognition|\bmasc\b)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Social interaction",
        re.compile(
            r"\b(social interaction|social behavior|sociability|social preference|social approach|"
            r"three[- ]chamber|prosocial|aggression|aggressive behavior|maternal aggression|"
            r"resident[- ]intruder|attack latency|social ultrasonic vocalizations|partner preference)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Pain behavior",
        re.compile(
            r"\b(pain behavior|nocicep|antinocicep|allodynia|hyperalgesia|analgesic|hot plate|"
            r"tail flick|tail[- ]flick|von frey|paw withdrawal|mechanical withdrawal|thermal withdrawal|"
            r"withdrawal threshold|withdrawal latency)\b",
            re.IGNORECASE,
        ),
    ),
)
COGNITIVE_BEHAVIORAL_LABEL_FALLBACKS = {
    "addiction behavior": "Drug seeking",
    "anhedonia": "Anhedonia",
    "anxiety": "Anxiety-like behavior",
    "anxiety like behavior": "Anxiety-like behavior",
    "anxiety behavior": "Anxiety-like behavior",
    "depression like behavior": "Stress-coping behavior",
    "depressive like behavior": "Stress-coping behavior",
    "antidepressant like behavior": "Stress-coping behavior",
    "drug seeking and reinstatement": "Drug reinstatement",
    "social behavior": "Social interaction",
    "social cognition and interaction": "Social cognition",
    "pain behavior": "Pain behavior",
    "nociception and pain behavior": "Pain behavior",
    "hallucinogen like behavior": "Head-twitch response",
    "hallucinogenic like behavior": "Head-twitch response",
    "learning": "Memory",
    "psychedelic like behavior": "Head-twitch response",
    "time perception": "Time perception",
    "temporal perception": "Time perception",
    "interval timing": "Time perception",
}
COGNITIVE_BEHAVIORAL_BROAD_LABEL_KEYS = {
    "cognitive flexibility",
    "cognitive function",
    "drug seeking",
    "memory",
    "memory consolidation",
    "memory retrieval",
    "reward processing",
    "threat avoidance",
}
COGNITIVE_BEHAVIORAL_ALLOWED_REFINEMENTS = {
    "reward processing": {
        "anhedonia",
        "motivation",
        "reward learning",
        "reward processing",
        "reward responsiveness",
    },
    "drug seeking": {
        "conditioned place preference",
        "craving",
        "drug discrimination",
        "drug cue reactivity",
        "drug motivation",
        "drug reinstatement",
        "drug seeking",
        "drug self administration",
        "relapse",
    },
    "threat avoidance": {
        "anxiety like behavior",
        "avoidance learning",
        "compulsivity",
        "fear memory",
        "threat avoidance",
    },
    "cognitive flexibility": {
        "cognitive flexibility",
        "compulsivity",
        "creativity",
        "decentering",
        "mindfulness",
        "psychological flexibility",
        "reversal learning",
        "set shifting",
    },
    "memory": {
        "associative memory",
        "autobiographical memory",
        "avoidance learning",
        "declarative memory",
        "episodic memory",
        "fear memory",
        "memory",
        "memory consolidation",
        "memory retrieval",
        "prospective memory",
        "recognition memory",
        "semantic memory",
        "sensory memory",
        "short term memory",
        "spatial memory",
        "verbal memory",
        "visual memory",
        "visuospatial memory",
        "working memory",
    },
}
COGNITIVE_BEHAVIORAL_ALLOWED_REFINEMENTS["memory consolidation"] = COGNITIVE_BEHAVIORAL_ALLOWED_REFINEMENTS["memory"]
COGNITIVE_BEHAVIORAL_ALLOWED_REFINEMENTS["memory retrieval"] = COGNITIVE_BEHAVIORAL_ALLOWED_REFINEMENTS["memory"]
OBJECTIVE_TIME_TASK_RE = re.compile(
    r"\b("
    r"temporal (?:bisection|reproduction|discrimination|production)|"
    r"time (?:bisection|reproduction|discrimination|estimation|production)|"
    r"interval timing|bisection procedure|psychophysical procedure|"
    r"\bt50\b|weber fraction|just noticeable difference|indifference point|difference limen"
    r")\b",
    re.IGNORECASE,
)
SUBJECTIVE_TIME_DISTORTION_RE = re.compile(
    r"\b("
    r"altered time perception|time perception|time distortion|time dilation|time compression|"
    r"time sped up|time slowed down|timelessness|loss of temporal awareness|"
    r"space[- ]time distortion|sense of time|subjective sense of time"
    r")\b",
    re.IGNORECASE,
)
SELF_REPORT_TIME_CONTEXT_RE = re.compile(
    r"\b(v(?:isual)?\s*analog(?:ue)?\s*scale|vas|self[- ]report|subjective report|"
    r"interview|qualitative|phenomenolog|cadss|5d[- ]?asc|11d[- ]?asc|3d[- ]?asc|awe[- ]?s)\b",
    re.IGNORECASE,
)
SUBJECTIVE_EXPERIENCE_LABEL_FIELDS = (
    "graph_entity_label",
    "raw_entity_label",
    "entity_label",
    "subjective_construct",
    "subjective_construct_category",
)
SUBJECTIVE_EXPERIENCE_CONTEXT_FIELDS = (
    *SUBJECTIVE_EXPERIENCE_LABEL_FIELDS,
    "instrument_or_measure",
    "outcome_measure",
    "setting_or_context",
    "relationship_to_outcome",
    "effect_or_statistic",
    "finding_summary",
    "study_title",
    "support",
    "supporting_quote",
)
SUBJECTIVE_EXPERIENCE_RULES = (
    (
        "Mystical-type experience",
        re.compile(
            r"\b(mystical|complete mystical|meq(?:[- ]?30)?|hood mysticism|oceanic boundlessness|"
            r"\bobn\b|experience of unity|unitive|self[- ]transcendence|transcendence|noetic sense|ineffability)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Near-death-like experience",
        re.compile(r"\b(near[- ]death|nde\b|greyson)\b", re.IGNORECASE),
    ),
    (
        "Ego dissolution",
        re.compile(r"\b(ego[- ]?dissolution|ego boundary dissolution|ego loss|ego death|ego disintegration|ego[- ]dissolution inventory|\bedi\b)\b", re.IGNORECASE),
    ),
    (
        "Emotional breakthrough",
        re.compile(r"\b(emotional breakthrough|emotional release|emotional catharsis|\beb[is]\b)\b", re.IGNORECASE),
    ),
    (
        "Psychological insight",
        re.compile(
            r"\b(psychological insight|personal insight|acute insight|insightful|self[- ]acceptance|"
            r"identity transformation|negative thought patterns|self[- ]critical|barriers)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Dissociation",
        re.compile(
            r"\b(dissociation|dissociative|derealization|depersonalization|depersonalisation|"
            r"depersonalization[- ]derealization|\bdp/dr\b|\bddd\b|cadss|self[- ]alienation|"
            r"disembodiment)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Challenging experience",
        re.compile(
            r"\b(challenging experience|difficult experience|bad trip|ceq\b|psychological distress|"
            r"adverse mental states?|acute anxiety|somatic challenges?|dread|fear|grief)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Time distortion",
        re.compile(
            r"\b(altered time perception|time distortion|time dilation|time compression|"
            r"time sped up|time slowed down|timelessness|loss of temporal awareness|"
            r"space[- ]time distortion|sense of time|subjective sense of time)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Perceptual alterations",
        re.compile(
            r"\b(perceptual alteration|perceptual changes?|perception|"
            r"visual (?:alterations?|changes?|effects?|phenomena|hallucinations?|imagery|perception)|"
            r"auditory|hallucinations?|hallucinogenic|"
            r"hallucinogen rating|hrs\b|imagery|elementary imagery|complex imagery|syna?esth|sensory changes?|"
            r"changed meaning of percepts|meaning of percepts|phosphenic|perceptual rivalry|visionary)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Subjective intensity",
        re.compile(
            r"\b(subjective (?:drug )?intensity|drug effect intensity|global subjective intensity|highness|"
            r"intensity of (?:the )?(?:psychedelic )?experience|strength of effect|peak experience|comedown)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Empathy",
        re.compile(r"\b(empathy|empathogenic|entactogenic|multifaceted empathy|emotional empathy)\b", re.IGNORECASE),
    ),
    (
        "Connectedness",
        re.compile(
            r"\b(connectedness|social connection|connection|connected|closeness|close to others|trust|"
            r"affiliation|communitas|togetherness|community|intimacy|love|pro[- ]?social|prosocial|"
            r"social attractiveness|friendliness)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Spiritual significance",
        re.compile(
            r"\b(spiritual|spirituality|religious|sacred|divine|supernatural|numinous|"
            r"spiritual significance|spiritual outlook|spiritual cleansing)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Personal significance",
        re.compile(
            r"\b(meaning in life|presence of meaning|meaningfulness|personally meaningful|personal meaningfulness|"
            r"meaningful experiences?|purpose in life|important experiences?|significant experiences?|"
            r"personal significance|life satisfaction)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Euphoria",
        re.compile(
            r"\b(euphoria|euphoric|liking|good effects|feel(?:ing)? high|drug high|bliss|amazing|drug liking)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Negative affect",
        re.compile(r"\b(dysphoria|negative mood|negative effects|tension|worry|anxiety|paranoia|confusion|drunken)\b", re.IGNORECASE),
    ),
    (
        "Positive affect",
        re.compile(
            r"\b(well[- ]?being|wellbeing|positive mood|positive affect|contentedness|calmness|"
            r"alertness|happiness|peacefulness|serenity|joy|awe|satisfaction|affective valence)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Somatic sensations",
        re.compile(
            r"\b(embodiment|somatic|bodily|body sensation|body feelings?|physical effects?|"
            r"unusual bodily sensations|nausea|vomiting|zapping|scrubbing)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Altered state profile",
        re.compile(r"\b(altered states?|altered state of consciousness|psychedelic experience|subjective effects?|asc\b|5d[- ]?asc|11d[- ]?asc|3d[- ]?asc|continuous subjective experience|primary process thinking|apz\b)\b", re.IGNORECASE),
    ),
)
SUBJECTIVE_EXPERIENCE_LABEL_FALLBACKS = {
    "altered state of consciousness": "Altered state profile",
    "altered states of consciousness": "Altered state profile",
    "challenging experience": "Challenging experience",
    "connectedness empathy": "Connectedness",
    "derealization": "Dissociation",
    "depersonalization": "Dissociation",
    "depersonalization derealization": "Dissociation",
    "dissociation": "Dissociation",
    "dissociation derealization": "Dissociation",
    "dissociative symptoms": "Dissociation",
    "dissociative state": "Dissociation",
    "drug induced synaesthesia": "Perceptual alterations",
    "ego dissolution": "Ego dissolution",
    "ego disintegration": "Ego dissolution",
    "emotional breakthrough": "Emotional breakthrough",
    "embodiment bodily sensations": "Somatic sensations",
    "experience intensity": "Subjective intensity",
    "hallucinations": "Perceptual alterations",
    "hallucinogenic effects": "Perceptual alterations",
    "meaning spirituality": "Spiritual significance",
    "mood euphoria": "Euphoria",
    "mystical experience": "Mystical-type experience",
    "time perception": "Time distortion",
    "altered time perception": "Time distortion",
    "time distortion": "Time distortion",
    "mystical type experience": "Mystical-type experience",
    "near death experience phenomenology": "Near-death-like experience",
    "oceanic boundlessness": "Mystical-type experience",
    "psychological insight": "Psychological insight",
    "subjective drug intensity": "Subjective intensity",
}
SUBJECTIVE_EXPERIENCE_SAFETY_CONTEXT_FIELDS = (
    "graph_entity_label",
    "raw_entity_label",
    "entity_label",
    "subjective_construct",
    "subjective_construct_category",
    "instrument_or_measure",
    "outcome_measure",
    "finding_summary",
    "support",
    "supporting_quote",
)
SUBJECTIVE_EXPERIENCE_SAFETY_RE = re.compile(
    r"\b(daily panic|panic attacks?|visual snow|tinnitus|ear ringing|depersonalization[- ]derealization disorder|"
    r"depersonalisation[- ]derealisation disorder|\bdp/dr\b|\bddd\b|clinically significant|"
    r"adverse events?|adverse effects?|adverse mental states?|"
    r"medical attention|psychotic symptoms?|full[- ]blown psychotic|manic symptoms?|mania|hypomania)\b",
    re.IGNORECASE,
)
SUBJECTIVE_EXPERIENCE_NONADVERSE_RE = re.compile(
    r"\b(no (?:clinically significant |serious |persisting )?adverse (?:events?|effects?)|"
    r"not associated with adverse|without adverse)\b",
    re.IGNORECASE,
)
PERSISTENT_PSYCHIATRIC_OR_PERCEPTUAL_SYMPTOMS_LABEL = "Persistent psychiatric or perceptual symptoms"
LEGACY_NEUROPSYCHIATRIC_LABEL_KEYS = {
    "neuropsychiatric sequelae",
    "neuropsychiatric syndrome",
    "neuropsychiatric syndromes",
}
PERSISTENT_POST_ACUTE_RE = re.compile(
    r"\b(persist(?:s|ed|ent|ently|ing)?|lasting|prolonged|enduring|not reversed)\b|"
    r"\b(?:weeks?|months?|years?)\b.{0,45}\b(?:after|following|post|abstinence)\b|"
    r"\b(?:after|following|post|follow[- ]?up|abstinence)\b.{0,45}\b(?:weeks?|months?|years?)\b",
    re.IGNORECASE,
)
ADVERSE_PERSISTENT_PSYCHIATRIC_OR_PERCEPTUAL_RE = re.compile(
    r"\b(neuropsychiatric syndromes?|psychopathology|psychiatric symptoms?|psychotic symptoms?|psychosis|"
    r"negative symptoms?|affective flattening|visual snow|palinopsia|photopsias?|"
    r"perceptual (?:aberrations?|disturbances?)|body image distortion|impaired visual[- ]perceptual|"
    r"hearing or seeing things|visual(?:/| and )auditory images?|cognitive and sensory material|"
    r"obsessive (?:philosophical )?rumination)\b",
    re.IGNORECASE,
)

PRIMARY_MARKERS = {"primary_evidence", "primary_study", "primary_results"}
SECONDARY_MARKERS = {"secondary_literature", "secondary_evidence", "review", "meta_analysis", "systematic_review"}
ROUTE_NATIVE_ENTITY_KINDS = {
    "brain_region",
    "brain_network",
    "neural_circuit",
    "brain_measure",
    "cognitive_behavioral_construct",
    "subjective_experience_construct",
    "pharmacokinetic_parameter",
    "intervention_component",
    "public_health_measure",
}
REGISTRY_BACKED_ENTITY_KINDS = {
    "condition_indication",
    "symptom_problem",
    "target",
    "pathway_process",
    "biomarker_readout",
    "system_family",
}
VOCABULARY_BACKED_ENTITY_KINDS = {
    "brain_region",
    "brain_network",
    "neural_circuit",
    "brain_measure",
    "cognitive_behavioral_construct",
    "subjective_experience_construct",
    "pharmacokinetic_parameter",
    "intervention_component",
    "public_health_measure",
}
GRAPH_ENTITY_KINDS = {
    "compound",
    "exposure_context",
    "condition_indication",
    "symptom_problem",
    "safety_adverse_event",
    "outcome_scale",
    "target",
    "pathway_process",
    "biomarker_readout",
    "system_family",
    *ROUTE_NATIVE_ENTITY_KINDS,
}
ENTITY_TYPE_BY_KIND = {
    "compound": "compound",
    "exposure_context": "exposure_unit",
    "condition_indication": "clinical_entity",
    "symptom_problem": "clinical_entity",
    "safety_adverse_event": "clinical_entity",
    "outcome_scale": "clinical_entity",
    "target": "mechanistic_entity",
    "pathway_process": "mechanistic_entity",
    "biomarker_readout": "mechanistic_entity",
    "system_family": "mechanistic_entity",
    "brain_region": "brain_system_entity",
    "brain_network": "brain_system_entity",
    "neural_circuit": "brain_system_entity",
    "brain_measure": "brain_system_entity",
    "cognitive_behavioral_construct": "behavioral_entity",
    "subjective_experience_construct": "subjective_experience_entity",
    "pharmacokinetic_parameter": "exposure_entity",
    "intervention_component": "intervention_entity",
    "public_health_measure": "public_health_entity",
}
ENTITY_KIND_ALIASES = {
    "molecular_readout": "biomarker_readout",
    "brain_readout": "biomarker_readout",
    "neural_readout": "biomarker_readout",
    "pk_parameter": "pharmacokinetic_parameter",
    "pk_or_exposure_parameter": "pharmacokinetic_parameter",
}
DOMAIN_DEFAULT_ENTITY_KIND = {
    "clinical_outcome": "condition_indication",
    "safety_tolerability": "safety_adverse_event",
    "molecular_target": "target",
    "molecular_pathway_readout": "pathway_process",
    "brain_system": "brain_network",
    "cognitive_behavioral": "cognitive_behavioral_construct",
    "behavioral": "cognitive_behavioral_construct",
    "subjective_experience": "subjective_experience_construct",
    "pharmacokinetics_exposure": "pharmacokinetic_parameter",
    "exposure": "pharmacokinetic_parameter",
    "intervention_context": "intervention_component",
    "intervention": "intervention_component",
    "real_world_public_health": "public_health_measure",
    "public_health": "public_health_measure",
}
COMPOUND_LABEL_FIELDS = (
    "compound",
    "canonical_compound",
    "compound_or_class",
    "compound_or_exposure",
    "compound_or_intervention",
    "compound_or_analyte",
    "intervention_or_exposure",
    "exposure_or_intervention",
    "exposure_or_policy",
)
ENTITY_LABEL_FIELDS_BY_KIND = {
    "condition_indication": (
        "condition_or_indication",
        "condition_or_population",
        "disorder",
        "condition",
        "population",
        "graph_entity_label",
        "entity_label",
        "entity",
    ),
    "symptom_problem": (
        "symptom_or_outcome",
        "clinical_endpoint",
        "clinical_endpoint_category",
        "outcome_or_endpoint",
        "symptom_or_problem",
        "graph_entity_label",
        "entity_label",
        "entity",
    ),
    "safety_adverse_event": (
        "safety_event_or_measure",
        "outcome_or_endpoint",
        "outcome_measure",
        "graph_entity_label",
        "entity_label",
        "entity",
    ),
    "outcome_scale": (
        "outcome_measure",
        "outcome_measure_or_instrument",
        "instrument_or_measure",
        "clinical_endpoint",
        "graph_entity_label",
        "entity_label",
        "entity",
    ),
    "target": ("target", "metabolic_or_transport_target", "graph_entity_label", "entity_label", "entity"),
    "pathway_process": (
        "pathway_or_process",
        "pathway_or_readout",
        "specific_readout_or_marker",
        "readout_or_biomarker",
        "readout_or_measure",
        "metabolic_or_transport_pathway",
        "molecular_effect_category",
        "graph_entity_label",
        "entity_label",
        "entity",
    ),
    "biomarker_readout": (
        "specific_readout_or_marker",
        "readout_or_biomarker",
        "readout_or_measure",
        "readout",
        "outcome_measure",
        "pathway_or_readout",
        "graph_entity_label",
        "entity_label",
        "entity",
    ),
    "brain_region": ("brain_region", "graph_entity_label", "entity_label", "entity"),
    "brain_network": ("brain_network", "graph_entity_label", "entity_label", "entity"),
    "neural_circuit": ("neural_circuit", "connectivity_or_circuit_relationship", "graph_entity_label", "entity_label", "entity"),
    "brain_measure": (
        "brain_measure",
        "readout_or_measure",
        "outcome_measure",
        "graph_entity_label",
        "entity_label",
        "entity",
    ),
    "cognitive_behavioral_construct": (
        "graph_construct_label",
        "construct_or_behavior",
        "behavior_or_task",
        "task_or_measure",
        "raw_task_or_measure",
        "graph_entity_label",
        "entity_label",
        "entity",
    ),
    "subjective_experience_construct": (
        "subjective_construct",
        "subjective_construct_category",
        "instrument_or_measure",
        "graph_entity_label",
        "entity_label",
        "entity",
    ),
    "pharmacokinetic_parameter": (
        "pk_or_exposure_parameter",
        "pharmacokinetic_parameter",
        "outcome_or_endpoint",
        "outcome_measure",
        "graph_entity_label",
        "entity_label",
        "entity",
    ),
    "compound": ("metabolite_or_analyte", "compound_or_analyte", "graph_entity_label", "entity_label", "entity"),
    "intervention_component": (
        "context_component",
        "component_type",
        "intervention_model_or_orientation",
        "graph_entity_label",
        "entity_label",
        "entity",
    ),
    "public_health_measure": (
        "public_health_measure",
        "public_health_topic_category",
        "graph_entity_label",
        "entity_label",
        "entity",
    ),
}
GREEK_FOLD_REPLACEMENTS = {
    "α": "alpha",
    "Α": "Alpha",
    "β": "beta",
    "Β": "Beta",
    "γ": "gamma",
    "Γ": "Gamma",
    "δ": "delta",
    "Δ": "Delta",
    "κ": "kappa",
    "Κ": "Kappa",
    "μ": "mu",
    "µ": "mu",
    "Μ": "Mu",
}
CLASS_LEVEL_COMPOUND_RE = re.compile(
    r"\b("
    r"classic(?:al)?\s+psychedelics?|"
    r"serotonergic\s+psychedelics?|"
    r"psychedelic(?:[- ]assisted)?\s+(?:medicines?|drugs?|substances?|compounds?|therap(?:y|ies))|"
    r"psychedelics?|"
    r"hallucinogenic\s+drugs?|"
    r"hallucinogens?|"
    r"arylcyclohexylamines?|"
    r"synthetic\s+cathinones?|"
    r"iboga\s+alkaloids?|"
    r"nbome\s+drugs?|"
    r"5[-\s]*ht2a?r?\s+agonists?"
    r")\b",
    re.IGNORECASE,
)
IN_SCOPE_NON_ATOMIC_SUBJECT_RE = re.compile(
    r"\b("
    r"classic(?:al)?\s+psychedelics?|"
    r"serotonergic\s+psychedelics?|"
    r"psychedelic(?:[- ]assisted)?\s+(?:medicines?|drugs?|substances?|compounds?|therap(?:y|ies))|"
    r"psychedelics?|"
    r"hallucinogenic\s+drugs?|"
    r"hallucinogens?|"
    r"arylcyclohexylamines?|"
    r"dissociatives?|"
    r"entheogens?|"
    r"tryptamines?|"
    r"phenethylamines?|"
    r"iboga\s+alkaloids?|"
    r"nbome\s+drugs?|"
    r"5[-\s]*ht\s*\(?2a?r?\)?\s+(?:receptor\s+)?(?:partial\s+)?agon(?:ists?|istic)"
    r")\b",
    re.IGNORECASE,
)
OUT_OF_SCOPE_NON_ATOMIC_SUBJECT_HEAD_RE = re.compile(
    r"^\s*"
    r"(?:(?:illicit\s+(?:use\s+of\s+(?:prescription\s+)?)?)|"
    r"(?:open[- ]label|traditional|conventional|rapid[- ]acting|second[- ]generation|atypical|"
    r"serotoninergic|serotonergic|recreational|daily|crystal|substituted|para[- ]substituted|"
    r"crushed|ritual)\s+)*"
    r"(?:(?:[drs](?:-\s*)?(?:\([+-]\))?|[+-])[- ]*)?"
    r"(stimulants?|psychostimulants?|amphetamines?|methamphetamines?|cocaine|"
    r"opioids?|opiates?|heroin|fentanyl|morphine|"
    r"cannabis|cannabinoids?|marijuana|nicotine|tobacco|"
    r"benzodiazepines?|antiepileptics?|antidepressants?|antipsychotics?|mood\s+stabilizers?|"
    r"ssris?|snris?|sedatives?|cathinones?|synthetic\s+cathinones?|mephedrone|mdpv|"
    r"ghb|gbl|gamma\s+hydroxybutyrate|"
    r"designer\s+drugs?)\b",
    re.IGNORECASE,
)
OUT_OF_SCOPE_GENERIC_DRUG_USE_SUBJECT_RE = re.compile(
    r"^\s*(?:psychoactive\s+substance\s+microdosing|substance\s+use)\s*\(",
    re.IGNORECASE,
)
NON_ATOMIC_SUBJECT_HEAD_SPLIT_RE = re.compile(
    r"\s*(?:\+|,|/|\band\b|\bor\b|\bplus\b|\bcombined\s+with\b|\bfollowed\s+by\b)\s*|[([]",
    re.IGNORECASE,
)
OUT_OF_SCOPE_NON_ATOMIC_TERM_RE = re.compile(
    r"\b(?:stimulants?|psychostimulants?|amphetamines?|methamphetamines?|cocaine|"
    r"opioids?|opiates?|heroin|fentanyl|morphine|alcohol|"
    r"cannabis|cannabinoids?|marijuana|nicotine|tobacco|"
    r"benzodiazepines?|antiepileptics?|antidepressants?|antipsychotics?|mood\s+stabilizers?|"
    r"ssris?|snris?|sedatives?|cathinones?|mephedrone|mdpv|ghb|gbl)\b",
    re.IGNORECASE,
)
OUT_OF_SCOPE_EXPLICIT_DESCRIPTION_RE = re.compile(
    r"\b(?:synthetic\s+cannabinoid\s+receptor\s+agonists?|amphetamine[- ]like\s+substances?)\b",
    re.IGNORECASE,
)
FINDING_LEVEL_SCOPE_FIELDS = (
    "dose_or_exposure",
    "dose",
    "finding_summary",
    "summary_statement",
    "support",
    "supporting_quote",
    "comparator",
    "session_context",
)
FINDING_LEVEL_PSYCHEDELIC_CLASS_RE = re.compile(
    r"\b(?:classic(?:al)?(?:\s+serotonergic)?\s+psychedelics?|"
    r"serotonergic\s+psychedelics?|psychedelics?|psychedelic\s+(?:medicines?|drugs?|substances?|compounds?|therap(?:y|ies))|"
    r"hallucinogenic\s+drugs?|hallucinogens?|entheogens?|dissociatives?)\b",
    re.IGNORECASE,
)
RECOVERED_FINDING_SCOPE_REASON = "in_scope_subject_recovered_from_finding_evidence_detail_only"
REFERENCE_CONTROL_COMPOUND_KEYS = {
    "5 ht",
    "5 hydroxytryptamine",
    "5 hydroxytryptophan",
    "8 oh dpat",
    "amphetamine",
    "azd6765",
    "cocaine",
    "cp 93129",
    "clozapine",
    "d serine",
    "d amphetamine",
    "efavirenz",
    "escitalopram",
    "fluoxetine",
    "glycine",
    "gr 127935",
    "ifenprodil",
    "ketanserin",
    "ly341495",
    "m100907",
    "mcpp",
    "memantine",
    "methysergide",
    "methamphetamine",
    "midazolam",
    "mdl 100 907",
    "mdl100907",
    "mk 801",
    "nmda",
    "p chloroamphetamine",
    "p chloroamphetamine pca",
    "pca",
    "pcp",
    "phencyclidine",
    "phencyclidine pcp",
    "pnu 142633",
    "quipazine",
    "ritanserin",
    "ro 25 6981",
    "ro25 6981",
    "saline",
    "scopolamine",
    "sb 216641",
    "sb271046",
    "serotonin",
    "serotonin 5 ht",
    "way100635",
}
GRAPH_EXCLUDED_COMPOUND_SCOPES = {
    "out_of_scope",
    "out_of_scope_comparator",
    "out_of_scope_nonpsychedelic",
    "reference_control",
}
GRAPH_EXCLUDED_COMPOUND_LABEL_SCOPES = {
    "Cannabidiol": "out_of_scope_nonpsychedelic",
    "Cannabis": "out_of_scope_nonpsychedelic",
    "D-cycloserine": "out_of_scope_comparator",
    "Kratom": "out_of_scope_nonpsychedelic",
    "Lanicemine": "out_of_scope_comparator",
    "Lisuride": "out_of_scope_comparator",
    "MIJ821": "out_of_scope_comparator",
    "Mitragynine": "out_of_scope_nonpsychedelic",
    "Rapastinel": "out_of_scope_comparator",
}
RAW_GRAPH_EXCLUDED_COMPOUND_LABEL_SCOPES = {
    "4 chlorokynurenine": "out_of_scope_comparator",
    "4 cl kyn": "out_of_scope_comparator",
    "cathodal transcranial direct current stimulation tdcs": "out_of_scope_comparator",
    "electroconvulsive therapy": "out_of_scope_comparator",
    "ect": "out_of_scope_comparator",
    "kambo": "out_of_scope_nonpsychedelic",
    "kambo phyllomedusa bicolor secretion": "out_of_scope_nonpsychedelic",
    "major depressive disorder": "out_of_scope",
    "mdd": "out_of_scope",
    "nicotiana rustica": "out_of_scope_nonpsychedelic",
    "nicotiana rustica l tobacco": "out_of_scope_nonpsychedelic",
    "nicotine": "out_of_scope_nonpsychedelic",
    "placebo": "out_of_scope_comparator",
    "tobacco": "out_of_scope_nonpsychedelic",
    "thc": "out_of_scope_nonpsychedelic",
}


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def default_run_id(prefix: str = "routed") -> str:
    return f"{prefix}_{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"


def safe_run_id(value: object) -> str:
    text = normalize(value)
    text = re.sub(r"[^A-Za-z0-9._-]+", "_", text).strip("._-")
    return text


def routed_evidence_rows_path_for_run(run_id: str) -> Path:
    return DEFAULT_EXTRACTION_DIR / "routed_runs" / safe_run_id(run_id) / "routed_evidence_rows.json"


def graph_sources_for_preset(source_preset: str, run_id: str = "") -> dict[str, dict]:
    try:
        sources = GRAPH_SOURCE_PRESETS[source_preset]
    except KeyError as exc:
        choices = ", ".join(sorted(GRAPH_SOURCE_PRESETS))
        raise ValueError(f"Unknown source preset {source_preset!r}; expected one of: {choices}") from exc
    out = {name: dict(cfg) for name, cfg in sources.items()}
    if safe_run_id(run_id):
        for source_name in ROUTED_SOURCE_NAMES & set(out):
            out[source_name]["path"] = routed_evidence_rows_path_for_run(run_id)
    return out


def resolve_kg_output_dir(
    *,
    source_preset: str,
    out_dir: Path | None,
    run_id: str,
) -> tuple[Path, str]:
    resolved_run_id = safe_run_id(run_id)
    if out_dir is not None:
        return out_dir, resolved_run_id
    if not resolved_run_id:
        resolved_run_id = default_run_id(source_preset)
    return DEFAULT_ROUTED_KG_RUN_ROOT / resolved_run_id, resolved_run_id


def load_json_array(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, list):
        raise ValueError(f"Expected JSON array at {path}")
    return [row for row in data if isinstance(row, dict)]


def load_json_object(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object at {path}")
    return data


def normalize_doi(value: object) -> str:
    text = normalize(value)
    lowered = text.lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/", "http://dx.doi.org/", "doi:"):
        if lowered.startswith(prefix):
            text = text[len(prefix) :]
            break
    return text.strip().lower()


def slug(value: object, fallback: str = "id") -> str:
    text = normalize(value).casefold()
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    if text:
        return text[:140]
    digest = hashlib.sha1(normalize(value).encode("utf-8")).hexdigest()[:12]
    return f"{fallback}_{digest}"


def stable_id(prefix: str, *parts: object, length: int = 18) -> str:
    canonical = "|".join(normalize(part) for part in parts)
    digest = hashlib.sha1(canonical.encode("utf-8")).hexdigest()[:length]
    return f"{prefix}:{digest}"


def json_dumps(value: object) -> str:
    if value in (None, ""):
        return ""
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return normalize(value).casefold() in {"true", "1", "yes", "y"}


def as_int_or_none(value: object) -> int | None:
    text = normalize(value)
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def as_float_or_none(value: object) -> float | None:
    text = normalize(value)
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def paper_id_for(row: dict) -> str:
    doi = normalize_doi(row.get("study_doi", ""))
    if doi:
        return f"paper:{doi}"
    openalex_id = normalize(row.get("openalex_id", ""))
    if openalex_id:
        return f"paper:openalex:{slug(openalex_id)}"
    return stable_id("paper", row.get("study_title", ""), row.get("study_year", ""), row.get("study_journal", ""))


def entity_id_for(entity_type: str, label: object) -> str:
    return f"{entity_type}:{slug(label, entity_type)}"


def ascii_fold(value: object) -> str:
    text = normalize(value)
    text = "".join(GREEK_FOLD_REPLACEMENTS.get(char, char) for char in text)
    text = unicodedata.normalize("NFKD", text)
    return text.encode("ascii", "ignore").decode("ascii")


def normalize_outcome_measure(value: object) -> str:
    text = ascii_fold(value).casefold()
    if not text or text in {"not_reported", "not reported", "not_applicable", "not applicable", "unknown"}:
        return ""
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    labels: list[str] = []
    for label, patterns in OUTCOME_MEASURE_PATTERNS:
        if any(re.search(pattern, text) for pattern in patterns):
            if label == "MADRS" and "MADRS-SI" in labels:
                continue
            if label == "HADS" and ({"HADS-A", "HADS-D"} & set(labels)):
                continue
            if label == "CGI" and ({"CGI-S", "CGI-I"} & set(labels)):
                continue
            labels.append(label)

    seen: set[str] = set()
    out: list[str] = []
    for label in labels:
        if label in seen:
            continue
        seen.add(label)
        out.append(label)
    return "; ".join(out)


def label_key(value: object) -> str:
    text = ascii_fold(value).casefold()
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


COGNITIVE_BEHAVIORAL_RULE_LABEL_BY_KEY = {label_key(label): label for label, _pattern in COGNITIVE_BEHAVIORAL_RULES}
SUBJECTIVE_EXPERIENCE_RULE_LABEL_BY_KEY = {label_key(label): label for label, _pattern in SUBJECTIVE_EXPERIENCE_RULES}
PUBLIC_HEALTH_TOPIC_LABEL_BY_KEY = {label_key(label): label for label in PUBLIC_HEALTH_TOPIC_LABELS}
PUBLIC_HEALTH_USE_CONTEXT_LABEL_BY_KEY = {label_key(label): label for label, _pattern in PUBLIC_HEALTH_USE_CONTEXT_RULES}


def compact_key(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", label_key(value))


CANONICAL_ENTITY_FORMAT_GROUPS = (
    ("biomarker_readout", "TNF-α levels", ("TNF-alpha levels",)),
    ("biomarker_readout", "TNF-α mRNA expression", ("TNF-alpha mRNA expression",)),
    ("biomarker_readout", "TNF-α expression", ("TNF-alpha expression",)),
    ("biomarker_readout", "TNF-α gene expression mRNA expression", ("TNF-alpha gene expression mRNA expression",)),
    ("biomarker_readout", "TNF-α protein levels", ("TNF-alpha protein levels",)),
    ("biomarker_readout", "TNF-α production levels", ("TNF-alpha production levels",)),
    ("biomarker_readout", "serum TNF-α levels", ("Serum TNF-α levels", "serum TNF-alpha levels")),
    ("biomarker_readout", "plasma TNF-α levels", ("plasma TNF-alpha levels",)),
    (
        "biomarker_readout",
        "Plasma TNF-α concentration levels",
        ("Plasma TNF-alpha concentration levels",),
    ),
    (
        "biomarker_readout",
        "tumor necrosis factor-α levels",
        ("Tumor necrosis factor alpha levels",),
    ),
    (
        "biomarker_readout",
        "tumor necrosis factor-α (TNF-α) expression",
        ("Tumor necrosis factor-alpha (TNF-alpha) expression",),
    ),
    ("biomarker_readout", "IL-1β levels", ("IL-1beta levels", "IL-1 beta levels")),
    ("biomarker_readout", "IL-1β mRNA expression", ("IL-1beta mRNA expression",)),
    ("biomarker_readout", "IL-1β protein levels", ("IL-1beta protein levels",)),
    ("biomarker_readout", "TGF-β1 expression", ("TGF-beta1 expression",)),
    ("biomarker_readout", "serotonin (5-HT) levels", ("serotonin (5HT) levels",)),
    (
        "biomarker_readout",
        "extracellular serotonin (5-HT) levels",
        ("extracellular serotonin (5HT) levels",),
    ),
    (
        "biomarker_readout",
        "serotonin (5-HT) depletion release",
        ("Serotonin (5HT) depletion release",),
    ),
    (
        "biomarker_readout",
        "dopamine D2/D3 receptors",
        ("dopamine D 2 /D 3 receptors",),
    ),
    (
        "biomarker_readout",
        "TPH2 gene expression mRNA expression",
        ("Tph2 gene expression mRNA expression", "TPH-2 gene expression mRNA expression"),
    ),
    ("biomarker_readout", "p47phox phosphorylation", ("P47(phox) phosphorylation",)),
    ("biomarker_readout", "IBA-1 activation", ("Iba1 activation",)),
    (
        "biomarker_readout",
        "5-hydroxyindoleacetic acid (5-HIAA) levels",
        ("5-hydroxyindoleacetic acid (5HIAA) levels",),
    ),
    (
        "biomarker_readout",
        "3-methoxytyramine (3-MT) levels",
        ("3-methoxytyramine (3MT) levels",),
    ),
    (
        "pathway_process",
        "[35S]GTPγS binding activation",
        ("[35S]GTPgammaS binding activation",),
    ),
    (
        "biomarker_readout",
        "[35S]GTPγS binding activation",
        ("[35S]GTPgammaS binding activation",),
    ),
    ("pathway_process", "[3H]-paroxetine binding", ("[(3)H]paroxetine binding",)),
    ("pathway_process", "EGR1 mRNA expression", ("Egr-1 mRNA expression",)),
    ("pathway_process", "EGR2 mRNA expression", ("Egr2 mRNA expression", "Egr-2 mRNA expression")),
    ("pathway_process", "EGR1", ("Egr1", "Egr-1")),
    (
        "pathway_process",
        "β-arrestin-2 recruitment",
        ("Β-arrestin2 recruitment", "Beta-arrestin2 recruitment", "Beta-arrestin 2 recruitment", "Β-arrestin-2 recruitment"),
    ),
    ("pathway_process", "p-Akt/Akt ratio phosphorylation", ("pAkt/Akt ratio phosphorylation",)),
    ("pathway_process", "p-ERK phosphorylation", ("pERK phosphorylation",)),
    (
        "pathway_process",
        "Spontaneous excitatory postsynaptic currents (sEPSCs) frequency",
        ("Spontaneous excitatory post-synaptic currents (sEPSCs) frequency",),
    ),
    ("pathway_process", "BCL2 gene expression", ("Bcl2 gene expression", "Bcl-2 gene expression")),
    ("pathway_process", "MiniGαq recruitment", ("MiniGalpha q recruitment", "MiniGq recruitment")),
    (
        "pathway_process",
        "Gαq/11 protein phosphorylation",
        ("Galphaq/11 protein phosphorylation", "Galpha q/11 protein phosphorylation"),
    ),
    (
        "pathway_process",
        "Immediate early gene expression (EGR1)",
        ("Immediate early gene expression (Egr1)", "Immediate early gene expression (egr-1)"),
    ),
    (
        "pathway_process",
        "Phosphatidylinositol (PI) hydrolysis",
        ("Phosphatidyl inositol (PI) hydrolysis",),
    ),
    (
        "pathway_process",
        "Pro-inflammatory cytokine levels",
        ("Proinflammatory cytokine levels",),
    ),
    (
        "pathway_process",
        "Pro-inflammatory cytokine production",
        ("Proinflammatory cytokine production",),
    ),
    ("pathway_process", "GSK3β phosphorylation", ("GSK3beta phosphorylation",)),
    ("pathway_process", "Metaplasticity", ("Meta-plasticity",)),
    (
        "intervention_component",
        "Set & setting",
        ("Set and setting",),
    ),
    (
        "intervention_component",
        "Non-directive, supportive approach",
        ("Nondirective, supportive approach",),
    ),
)
CANONICAL_ENTITY_FORMAT_BY_KEY = {
    (kind, compact_key(candidate)): canonical
    for kind, canonical, aliases in CANONICAL_ENTITY_FORMAT_GROUPS
    for candidate in (canonical, *aliases)
}


def canonical_entity_format_label(label: object, entity_kind: str) -> str:
    text = normalize(label)
    return CANONICAL_ENTITY_FORMAT_BY_KEY.get((entity_kind, compact_key(text)), text)


def target_variants(label: str) -> list[str]:
    text = normalize(label)
    variants = []
    if re.fullmatch(r"5-HT\d[A-Z]?", text, flags=re.IGNORECASE):
        variants.append(f"{text} receptor")
    match = re.match(r"^(.+?)\s*\((.+?)\)$", text)
    if match:
        variants.extend([match.group(1), match.group(2), f"{match.group(1)} {match.group(2)}"])
    return variants


def entity_key_variants(value: object, entity_type: str = "") -> list[tuple[str, str]]:
    text = normalize(value)
    if not text:
        return []
    variants: list[tuple[str, str]] = [(text, "label")]
    no_parenthetical = re.sub(r"\([^)]*\)", " ", text)
    if normalize(no_parenthetical) and label_key(no_parenthetical) != label_key(text):
        variants.append((no_parenthetical, "without_parenthetical"))
    for inside in re.findall(r"\(([^)]*)\)", text):
        if normalize(inside):
            variants.append((inside, "parenthetical"))
    if entity_type == "mechanistic_entity":
        variants.extend((variant, "target_variant") for variant in target_variants(text))

    out: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for variant, variant_type in variants:
        for candidate_key, key_type in (
            (label_key(variant), variant_type),
            (compact_key(variant), f"{variant_type}_compact"),
        ):
            if candidate_key and (candidate_key, key_type) not in seen:
                seen.add((candidate_key, key_type))
                out.append((candidate_key, key_type))
    return out


def normalized_entity_kind(value: object) -> str:
    key = normalize(value).casefold().replace("-", "_").replace(" ", "_")
    return ENTITY_KIND_ALIASES.get(key, key)


def first_normalized_value(row: dict, fields: Iterable[str]) -> str:
    for field in fields:
        value = normalize(row.get(field, ""))
        if value:
            return value
    return ""


def first_endpoint_value(row: dict, fields: Iterable[str]) -> str:
    for field in fields:
        value = endpoint_value(row.get(field, ""))
        if value:
            return value
    return ""


def compound_label_for(row: dict) -> str:
    return first_normalized_value(row, COMPOUND_LABEL_FIELDS)


def node_vocabulary_lookup(path: Path = DEFAULT_NODE_VOCABULARY_PATH) -> dict[tuple[str, str], dict]:
    data = load_json_object(path)
    out: dict[tuple[str, str], dict] = {}
    node_kinds = data.get("node_kinds", {})
    if not isinstance(node_kinds, dict):
        return out
    for kind, entries in node_kinds.items():
        normalized_kind = normalized_entity_kind(kind)
        if normalized_kind not in GRAPH_ENTITY_KINDS or not isinstance(entries, list):
            continue
        for item in entries:
            if not isinstance(item, dict):
                continue
            label = normalize(item.get("label", ""))
            if not label:
                continue
            labels = [label]
            labels.extend(normalize(alias) for alias in item.get("aliases", []) if normalize(alias))
            for candidate in labels:
                for key, _variant_type in entity_key_variants(candidate):
                    out[(normalized_kind, key)] = item
    return out


def canonicalize_node_label(entity_kind: str, label: str, node_vocabulary: dict[tuple[str, str], dict]) -> tuple[str, dict | None]:
    item = None
    for key, _variant_type in entity_key_variants(label):
        item = node_vocabulary.get((entity_kind, key))
        if item:
            break
    if not item:
        return label, None
    canonical = normalize(item.get("label", "")) or label
    return canonical, item


def compound_key_variants(value: object) -> list[tuple[str, str]]:
    text = normalize(value)
    if not text:
        return []
    variants: list[tuple[str, str]] = [(text, "label")]
    no_parenthetical = re.sub(r"\([^)]*\)", " ", text)
    if normalize(no_parenthetical) and label_key(no_parenthetical) != label_key(text):
        variants.append((no_parenthetical, "without_parenthetical"))
    for inside in re.findall(r"\(([^)]*)\)", text):
        if normalize(inside):
            variants.append((inside, "parenthetical"))

    stripped = text
    stripped = re.sub(r"\b(?:intravenous|intranasal|sublingual|oral|subcutaneous|nasal spray|infusion)\b", " ", stripped, flags=re.IGNORECASE)
    stripped = re.sub(r"\b(?:iv|i\.v\.|in|s\.c\.|sc)\b", " ", stripped, flags=re.IGNORECASE)
    stripped = re.sub(r"\b(?:hydrochloride|hcl)\b", " ", stripped, flags=re.IGNORECASE)
    stripped = re.sub(r"\buse(?:rs?)?\b", " ", stripped, flags=re.IGNORECASE)
    stripped = re.sub(r"\b(?:lifetime|naturalistic|microdosing|weekly|synthetic|extracted)\b", " ", stripped, flags=re.IGNORECASE)
    stripped = re.sub(r"\b(?:therapy|treatment|assisted|psychotherapy|psychotherapeutic|support|program)\b", " ", stripped, flags=re.IGNORECASE)
    stripped = re.sub(r"\b(?:mushrooms?|truffles?)\b", " ", stripped, flags=re.IGNORECASE)
    if normalize(stripped) and label_key(stripped) != label_key(text):
        variants.append((stripped, "stripped_context"))

    out: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for variant, variant_type in variants:
        for candidate_key, key_type in (
            (label_key(variant), variant_type),
            (compact_key(variant), f"{variant_type}_compact"),
        ):
            if candidate_key and (candidate_key, key_type) not in seen:
                seen.add((candidate_key, key_type))
                out.append((candidate_key, key_type))
    return out


def registry_lookup(
    registry_path: Path,
    disorder_aliases_path: Path = DEFAULT_DISORDER_ALIASES_PATH,
) -> dict[tuple[str, str], dict]:
    registry = load_json_object(registry_path)
    disorder_aliases = load_json_object(disorder_aliases_path)
    out: dict[tuple[str, str], dict] = {}
    priorities: dict[tuple[str, str], int] = {}

    def variant_priority(variant_type: str) -> int:
        if variant_type == "label":
            return 0
        if variant_type in {"label_compact", "target_variant"}:
            return 1
        if variant_type in {"parenthetical", "parenthetical_compact"}:
            return 2
        if variant_type.startswith("without_parenthetical"):
            return 3
        if variant_type.startswith("stripped_context"):
            return 4
        return 5

    for category, entity_type in (("compounds", "compound"), ("targets", "mechanistic_entity"), ("disorders", "clinical_entity")):
        for item in registry.get(category, []):
            if not isinstance(item, dict):
                continue
            label = normalize(item.get("label", ""))
            if not label:
                continue
            labels = [label]
            labels.extend(normalize(alias) for alias in item.get("aliases", []) if normalize(alias))
            if category == "disorders":
                labels.extend(normalize(alias) for alias in disorder_aliases.get(label, []) if normalize(alias))
            for candidate in labels:
                if entity_type == "compound":
                    variants = compound_key_variants(candidate)
                else:
                    variants = entity_key_variants(candidate, entity_type)
                for key, variant_type in variants:
                    registry_key = (entity_type, key)
                    priority = variant_priority(variant_type)
                    existing_priority = priorities.get(registry_key)
                    if existing_priority is not None and existing_priority <= priority:
                        continue
                    out[registry_key] = item
                    priorities[registry_key] = priority
    return out


def canonicalize_registry_label(
    entity_type: str,
    label: str,
    registry: dict[tuple[str, str], dict],
) -> tuple[str, dict | None]:
    if entity_type == "compound":
        keys = compound_key_variants(label)
    else:
        keys = entity_key_variants(label, entity_type)
    item = None
    for key, _variant_type in keys:
        item = registry.get((entity_type, key))
        if item:
            break
    if not item:
        return label, None
    canonical = normalize(item.get("label", "")) or label
    return canonical, item


def registry_match_type(entity_type: str, label: str, canonical: str, registry: dict[tuple[str, str], dict]) -> str:
    variants = compound_key_variants(label) if entity_type == "compound" else entity_key_variants(label, entity_type)
    for key, variant_type in variants:
        item = registry.get((entity_type, key))
        if item and normalize(item.get("label", "")) == canonical:
            return variant_type
    return ""


def class_level_compound_label(value: object) -> bool:
    return bool(CLASS_LEVEL_COMPOUND_RE.search(ascii_fold(value)))


def reference_control_compound_label(value: object) -> bool:
    keys = {label_key(value)}
    compacts = {compact_key(value)}
    for variant, _variant_type in compound_key_variants(value):
        keys.add(label_key(variant))
        compacts.add(compact_key(variant))
    reference_compacts = {compact_key(item) for item in REFERENCE_CONTROL_COMPOUND_KEYS}
    return bool((keys & REFERENCE_CONTROL_COMPOUND_KEYS) or (compacts & reference_compacts))


def compound_graph_scope_block(label: object, item: dict | None) -> str:
    canonical_label = normalize(label)
    registry_scope = normalize((item or {}).get("graph_scope", "")).casefold()
    if registry_scope in GRAPH_EXCLUDED_COMPOUND_SCOPES:
        return registry_scope
    return GRAPH_EXCLUDED_COMPOUND_LABEL_SCOPES.get(canonical_label, "")


def graph_scope_blocked_compound_result(label: str, item: dict | None) -> dict | None:
    scope = compound_graph_scope_block(label, item)
    if not scope:
        return None
    return {
        "matched": False,
        "label": "",
        "item": None,
        "status": "compound_graph_scope_not_graphable",
        "match_type": "",
        "notes": f"compound `{label}` is registered as {scope}; graph compound nodes focus on focal psychedelic compounds",
    }


def raw_graph_scope_blocked_compound_result(label: str) -> dict | None:
    keys = {label_key(label)}
    for variant, _variant_type in compound_key_variants(label):
        keys.add(label_key(variant))
    scope = next((RAW_GRAPH_EXCLUDED_COMPOUND_LABEL_SCOPES[key] for key in keys if key in RAW_GRAPH_EXCLUDED_COMPOUND_LABEL_SCOPES), "")
    if not scope:
        return None
    return {
        "matched": False,
        "label": "",
        "item": None,
        "status": "compound_graph_scope_not_graphable",
        "match_type": "",
        "notes": f"compound `{label}` is classified as {scope}; graph compound nodes focus on focal psychedelic compounds",
    }


_REGISTRY_COMPOUND_TEXT_CACHE: dict[tuple[int, str], frozenset[str]] = {}
_REGISTRY_ENTITY_TEXT_CACHE: dict[tuple[int, str, str], frozenset[str]] = {}


def registry_compound_labels_in_text(value: object, registry: dict[tuple[str, str], dict]) -> set[str]:
    text_key = label_key(value)
    if not text_key:
        return set()
    cache_key = (id(registry), text_key)
    cached = _REGISTRY_COMPOUND_TEXT_CACHE.get(cache_key)
    if cached is not None:
        return set(cached)
    labels: set[str] = set()
    for entity_type, key in registry:
        if entity_type != "compound" or len(key) < 3:
            continue
        if re.search(rf"\b{re.escape(key)}\b", text_key):
            labels.add(normalize(registry[(entity_type, key)].get("label", "")))
    result = {label for label in labels if label}
    _REGISTRY_COMPOUND_TEXT_CACHE[cache_key] = frozenset(result)
    return result


COMPOUND_TEXT_LABEL_SUPERSEDES = {
    "S-ketamine": {"Ketamine"},
    "R-ketamine": {"Ketamine"},
    "5-MeO-DMT": {"DMT"},
}
COMPOUND_COMBO_TEXT_RE = re.compile(
    r"\b(and|or|plus|followed by|combined with|coadministered|co-administered|sequential)\b|\s\+\s|\s/\s",
    re.IGNORECASE,
)
EXPLICIT_COMPOUND_COADMIN_RE = re.compile(
    r"\b(?:coadministered|co-administered|coadministration|co-administration|"
    r"administered (?:together|concurrently|simultaneously)|concomitant(?:ly)?|"
    r"combined (?:administration|formulation|treatment|dose)|combined with|"
    r"combination (?:of|containing)|dose combinations?|formulation (?:of|containing|with)|"
    r"fixed[- ]dose combination|mixed (?:with|together))\b|\s\+\s",
    re.IGNORECASE,
)
EXPLICIT_COMPOUND_SEQUENCE_RE = re.compile(
    r"\b(?:followed by|then (?:received|administered|given)|sequential(?:ly)?(?: administered)?|"
    r"staged (?:administration|treatment|regimen))\b",
    re.IGNORECASE,
)
COMBINATION_EVIDENCE_FIELDS = (
    "graph_subject_label",
    "compound_or_exposure",
    "compound_or_intervention",
    "intervention_or_exposure",
    "exposure_or_intervention",
    "dose_or_exposure",
    "dose",
    "administration_route",
    "route_of_administration",
    "finding_summary",
    "summary_statement",
    "support",
    "supporting_quote",
    "study_title",
)
COMBINATION_ALIAS_EVIDENCE_FIELDS = tuple(
    field for field in COMBINATION_EVIDENCE_FIELDS if field != "study_title"
)
PRIMARY_COMPOUND_CUE_RE = re.compile(r"\b(?:primarily|predominantly|mainly|mostly)\b", re.I)
PRIMARY_COMPOUND_REVERSE_CUE_RE = re.compile(
    r"\b(?:was|is|as)\s+(?:the\s+)?(?:primary|predominant|main|most common)\s+"
    r"(?:compound|psychedelic|substance|drug)\b",
    re.I,
)
COMPOUND_CONTEXT_TEXT_RE = re.compile(
    r"\b(chemsex|sexuali[sz]ed drug use|sexual setting|poly[- ]?(?:substance|drug)|multi[- ]?drug|"
    r"mixed drug|as part of)\b",
    re.IGNORECASE,
)
CHEMICAL_LOCANT_COMMA_RE = re.compile(r"\b(?:N|O|S|R)(?:,\s*(?:N|O|S|R))+\s*[-(]", re.IGNORECASE)
COMPOUND_LIST_METADATA_RE = re.compile(
    r"\b(?:oral|intravenous|intranasal|subcutaneous|intramuscular|sublingual|infusion|injection|"
    r"tablet|capsule|spray|dose|mg|mcg|ug|µg|g|kg|ml|placebo|vehicle)\b",
    re.IGNORECASE,
)
NON_ATOMIC_GRAPH_SUBJECT_KINDS = {
    "compound_class",
    "compound_combination",
    "exposure_context",
    "paper_topic",
    "treatment_regimen",
}

OVERVIEW_SUBJECT_CLASS_RULES = (
    (
        re.compile(
            r"\b(?:classic(?:al)?(?:\s+serotonergic)?|serotonergic)\s+"
            r"(?:psychedelics?|hallucinogens?)\b",
            re.I,
        ),
        "Classic psychedelics",
    ),
    (re.compile(r"\bhallucinogens?\b", re.I), "Hallucinogens"),
    (re.compile(r"\bnmda(?: receptor)? antagonists?\b", re.I), "NMDA receptor antagonists"),
    (re.compile(r"\bdissociatives?\b", re.I), "Dissociatives"),
    (re.compile(r"\btryptamines?\b", re.I), "Tryptamines"),
    (re.compile(r"\bphenethylamines?\b", re.I), "Phenethylamines"),
    (re.compile(r"\bentheogens?\b", re.I), "Entheogens"),
)
UNRESOLVED_PSYCHEDELIC_SUBJECT_LABEL = "Psychedelics (unspecified compounds)"
BROAD_PSYCHEDELIC_CLASS_LABEL = "Psychedelics (broad or mixed)"
DETAIL_ONLY_OVERVIEW_SUBJECT_REASONS = {
    "controlled_unresolved_psychedelic_class_detail_only",
    RECOVERED_FINDING_SCOPE_REASON,
}
GENERIC_PSYCHEDELIC_CLASS_RE = re.compile(r"\bpsychedelics?\b", re.I)
PSYCHEDELIC_THERAPY_RE = re.compile(
    r"\bpsychedelic[- ]assisted (?:therap(?:y|ies)|psychotherap(?:y|ies)|treatments?)\b|"
    r"\bpsychedelic therapy\b",
    re.I,
)
PSYCHEDELIC_SEROTONERGIC_CONTEXT_RE = re.compile(
    r"\bserotonergic\b|\bclassic(?:al)? psychedelics?\b|5[- ]?ht2a|serotonin[- ]?2a",
    re.I,
)
PSYCHEDELIC_MIXED_CONTEXT_RE = re.compile(
    r"\b(?:(?:mixed|various) (?:psychedelic|compound|substance|drug)|multiple psychedelics?|"
    r"multi[- ]compound|compound panel|group including)\b",
    re.I,
)
PSYCHEDELIC_OVERVIEW_CONTEXT_FIELDS = (
    "primary_compounds_or_classes",
    "compound_or_class",
    "compound_or_exposure",
    "compound_or_intervention",
    "intervention_or_exposure",
    "exposure_or_intervention",
    "study_title",
    "finding_summary",
    "summary_statement",
    "support",
    "target",
    "graph_entity_label",
    "graph_entity_original",
    "keywords",
)
PSYCHEDELIC_SUBJECT_CONTEXT_FIELDS = (
    "primary_compounds_or_classes",
    "compound_or_class",
    "compound_or_exposure",
    "compound_or_intervention",
    "intervention_or_exposure",
    "exposure_or_intervention",
    "atomic_compound_candidate",
)
OVERVIEW_SUBJECT_CONTEXT_RULES = (
    (re.compile(r"\bchemsex\b", re.I), "Chemsex"),
    (re.compile(r"\bsexuali[sz]ed drug use\b|\bSDU\b", re.I), "Sexualized drug use"),
    (re.compile(r"\bpoly[- ]?(?:substance|drug)\b|\bmulti[- ]?drug\b|\bmixed drug\b", re.I), "Polysubstance use"),
)
SPECIFIC_COMPOUND_WITH_CLASS_PARENTHETICAL_RE = re.compile(
    r"^\s*[A-Za-z0-9][A-Za-z0-9+_.-]*\s*\([^)]*\b(?:antagonist|agonist|psychedelic|hallucinogen)\b[^)]*\)\s*$",
    re.I,
)


def looks_like_compound_list(value: object) -> bool:
    raw = normalize(value)
    if raw.count(",") < 1 or CHEMICAL_LOCANT_COMMA_RE.search(raw):
        return False
    parts = [part.strip() for part in raw.split(",") if part.strip()]
    if len(parts) < 2:
        return False
    drug_like_parts = 0
    for part in parts:
        if COMPOUND_LIST_METADATA_RE.search(part):
            continue
        if re.search(r"[A-Za-z][A-Za-z0-9-]{2,}", part):
            drug_like_parts += 1
    return drug_like_parts >= 2


def prune_compound_text_labels(raw: object, labels: set[str]) -> set[str]:
    if len(labels) <= 1:
        return labels
    pruned = set(labels)
    for specific, broad_labels in COMPOUND_TEXT_LABEL_SUPERSEDES.items():
        if specific in pruned:
            raw_key = label_key(raw)
            masked = raw_key
            if specific == "S-ketamine":
                masked = re.sub(r"\b(?:s ketamine|esketamine)\b", " ", masked)
            elif specific == "R-ketamine":
                masked = re.sub(r"\b(?:r ketamine|arketamine)\b", " ", masked)
            elif specific == "5-MeO-DMT":
                masked = re.sub(r"\b(?:5 meo dmt|5 methoxy n n dimethyltryptamine|5 methoxy dmt)\b", " ", masked)
            for broad in broad_labels:
                if not re.search(rf"\b{re.escape(label_key(broad))}\b", masked):
                    pruned.discard(broad)
    return pruned


def graphable_compound_match(raw_compound: object, registry: dict[tuple[str, str], dict]) -> dict:
    raw = normalize(raw_compound)
    if not raw:
        return {
            "matched": False,
            "label": "",
            "item": None,
            "status": "compound_missing",
            "match_type": "",
            "notes": "compound field is empty",
        }
    if class_level_compound_label(raw):
        return {
            "matched": False,
            "label": "",
            "item": None,
            "status": "compound_class_not_graphable",
            "match_type": "",
            "notes": "compound is a broad class label; graph compound nodes use specific registered compounds",
        }
    if reference_control_compound_label(raw):
        return {
            "matched": False,
            "label": "",
            "item": None,
            "status": "compound_reference_not_graphable",
            "match_type": "",
            "notes": "compound is a reference/control compound; graph compound nodes focus on in-scope compounds",
        }
    raw_scope_block = raw_graph_scope_blocked_compound_result(raw)
    if raw_scope_block:
        return raw_scope_block

    label, item = canonicalize_registry_label("compound", raw, registry)
    if item:
        scope_block = graph_scope_blocked_compound_result(label, item)
        if scope_block:
            return scope_block
        return {
            "matched": True,
            "label": label,
            "item": item,
            "status": "compound_normalized",
            "match_type": registry_match_type("compound", raw, label, registry),
            "notes": "compound matched local registry",
        }

    matched_labels = prune_compound_text_labels(raw, registry_compound_labels_in_text(raw, registry))
    if len(matched_labels) > 1:
        return {
            "matched": False,
            "label": "",
            "item": None,
            "status": "compound_combo_not_graphable",
            "match_type": "",
            "notes": "compound is a multi-compound label; graph compound nodes use one registered compound per edge",
        }
    if len(matched_labels) == 1:
        label = next(iter(matched_labels))
        _, item = canonicalize_registry_label("compound", label, registry)
        scope_block = graph_scope_blocked_compound_result(label, item)
        if scope_block:
            return scope_block
        return {
            "matched": True,
            "label": label,
            "item": item,
            "status": "compound_normalized",
            "match_type": "text_contains_registry_label",
            "notes": "compound text contained one local registry compound label",
        }
    return {
        "matched": False,
        "label": "",
        "item": None,
        "status": "compound_unmapped",
        "match_type": "",
        "notes": f"compound `{raw}` did not match local registry",
    }


def subject_label_is_explicitly_out_of_scope(
    raw_label: object,
    registry: dict[tuple[str, str], dict],
) -> bool:
    raw = normalize(raw_label)
    if not raw or IN_SCOPE_NON_ATOMIC_SUBJECT_RE.search(raw):
        return False

    for label in registry_compound_labels_in_text(raw, registry):
        if graphable_compound_match(label, registry).get("matched"):
            return False

    head = normalize(NON_ATOMIC_SUBJECT_HEAD_SPLIT_RE.split(raw, maxsplit=1)[0])
    head_match = graphable_compound_match(head, registry) if head else {}
    return (
        bool(OUT_OF_SCOPE_NON_ATOMIC_SUBJECT_HEAD_RE.search(raw))
        or bool(OUT_OF_SCOPE_EXPLICIT_DESCRIPTION_RE.search(raw))
        or normalize(head_match.get("status", ""))
        in {"compound_reference_not_graphable", "compound_graph_scope_not_graphable"}
        or (
            bool(OUT_OF_SCOPE_GENERIC_DRUG_USE_SUBJECT_RE.search(raw))
            and bool(OUT_OF_SCOPE_NON_ATOMIC_TERM_RE.search(raw))
        )
    )


def finding_level_scope_text(row: dict) -> str:
    return " ".join(
        normalize(row.get(field, ""))
        for field in FINDING_LEVEL_SCOPE_FIELDS
        if normalize(row.get(field, ""))
    )


def finding_level_in_scope_subjects(
    row: dict,
    registry: dict[tuple[str, str], dict],
) -> list[dict]:
    """Recover psychedelic subjects from the finding itself, never from its title."""

    context = finding_level_scope_text(row)
    if not context:
        return []
    labels = ordered_graphable_compound_labels(context, registry)
    if labels:
        return [
            {
                "label": label,
                "kind": "atomic_compound",
                "reason": RECOVERED_FINDING_SCOPE_REASON,
            }
            for label in labels
        ]
    if not FINDING_LEVEL_PSYCHEDELIC_CLASS_RE.search(context):
        return []

    if re.search(
        r"\b(?:classic(?:al)?(?:\s+serotonergic)?|serotonergic)\s+"
        r"(?:psychedelics?|hallucinogens?)\b",
        context,
        re.I,
    ):
        label = "Classic psychedelics"
    elif re.search(r"\bhallucinogenic\s+drugs?\b|\bhallucinogens?\b", context, re.I):
        label = "Hallucinogens"
    elif re.search(r"\bdissociatives?\b", context, re.I):
        label = "Dissociatives"
    elif re.search(r"\bentheogens?\b", context, re.I):
        label = "Entheogens"
    else:
        label = UNRESOLVED_PSYCHEDELIC_SUBJECT_LABEL
    return [{"label": label, "kind": "compound_class", "reason": RECOVERED_FINDING_SCOPE_REASON}]


def explicitly_out_of_scope_subject(
    row: dict,
    raw_label: object,
    registry: dict[tuple[str, str], dict],
) -> dict | None:
    """Exclude only rows whose subject and finding-level evidence are out of scope."""

    raw = normalize(raw_label)
    if not subject_label_is_explicitly_out_of_scope(raw, registry):
        return None
    if finding_level_in_scope_subjects(row, registry):
        return None

    return {
        "matched": False,
        "label": "",
        "item": None,
        "status": "compound_out_of_scope_nonpsychedelic",
        "match_type": "",
        "notes": (
            f"exposure `{raw}` is explicitly nonpsychedelic/reference-only; "
            "excluded from normalized findings"
        ),
    }


VALIDATED_UNREGISTERED_COMPOUND_BLOCK_RE = re.compile(
    r"\b("
    r"ablation|activation|adults?|animals?|baseline|breathing|cancer|care|class|clinical|"
    r"condition|control|deletion|diagnos\w*|disorder|dose|dosing|exposure|group|identifying|"
    r"intervention|knockdown|knockout|model|overexpression|participants?|"
    r"patients?|placebo|population|procedure|psychotherap\w*|regimen|session|stress|"
    r"sirna|stimulation|stimuli|substances?|surgery|symptoms?|task|therap\w*|treatment|users?|volunteers?"
    r")\b",
    re.IGNORECASE,
)


def validated_unregistered_compound_detail_subject(
    row: dict,
    raw_label: object,
    registry: dict[tuple[str, str], dict],
) -> bool:
    """Accept a structured atomic compound label as searchable detail, never as an overview node."""

    raw = normalize(raw_label)
    candidate = normalize(row.get("atomic_compound_candidate", ""))
    kind = normalize(row.get("graph_subject_kind", "")).casefold().replace("-", "_").replace(" ", "_")
    source_field = normalize(row.get("graph_subject_source_field", "")).casefold()
    if not raw or not candidate or label_key(raw) != label_key(candidate):
        return False
    if kind not in {"", "atomic_compound"}:
        return False
    if source_field not in {"", "compound", "graph_subject_label", "anchors"}:
        return False
    if len(raw) > 120 or len(raw.split()) > 10 or not re.search(r"[A-Za-z]", raw):
        return False
    if (
        class_level_compound_label(raw)
        or looks_like_compound_list(raw)
        or COMPOUND_CONTEXT_TEXT_RE.search(raw)
        or VALIDATED_UNREGISTERED_COMPOUND_BLOCK_RE.search(raw)
    ):
        return False
    if any(canonicalize_registry_label(entity_type, raw, registry)[1] for entity_type in ("clinical_entity", "mechanistic_entity")):
        return False
    return True


def validated_unregistered_compound_match(row: dict, raw_label: object) -> dict:
    raw = normalize(raw_label)
    return {
        "matched": True,
        "label": raw,
        "item": {
            "label": raw,
            "aliases": [],
            "ids": {},
            "status": "validated_unregistered_compound_detail_only",
        },
        "status": "validated_unregistered_compound_detail_only",
        "match_type": "validated_unregistered_compound_detail_only",
        "notes": "structured atomic compound retained for paper detail without overview projection",
        "subject_kind": "atomic_compound",
    }


def graphable_subject_match(row: dict, registry: dict[tuple[str, str], dict]) -> dict:
    """Normalize an atomic compound or preserve a complete non-atomic exposure.

    Non-atomic subjects are valid graph nodes.  Treating them as synthetic
    exposure units prevents a class, regimen, or multi-drug definition from
    being reduced to whichever registered compound happens to occur first.
    """

    raw = compound_label_for(row)
    explicit_kind = normalized_entity_kind(row.get("graph_subject_kind", ""))
    if explicit_kind == "atomic_compound" and looks_like_compound_list(raw):
        explicit_kind = "compound_combination"
    if explicit_kind == "atomic_compound":
        match = graphable_compound_match(raw, registry)
        if match["matched"]:
            match["subject_kind"] = "atomic_compound"
            return match
        if match["status"] == "compound_combo_not_graphable":
            explicit_kind = "compound_combination"
        elif match["status"] == "compound_class_not_graphable":
            explicit_kind = "compound_class"
        else:
            if match["status"] == "compound_unmapped":
                scope_exclusion = explicitly_out_of_scope_subject(row, raw, registry)
                if scope_exclusion:
                    return scope_exclusion
            if (
                match["status"] == "compound_unmapped"
                and validated_unregistered_compound_detail_subject(row, raw, registry)
            ):
                return validated_unregistered_compound_match(row, raw)
            match["subject_kind"] = "atomic_compound"
            return match
    inferred_kind = explicit_kind
    if inferred_kind not in NON_ATOMIC_GRAPH_SUBJECT_KINDS:
        if class_level_compound_label(raw):
            inferred_kind = "compound_class"
        elif COMPOUND_CONTEXT_TEXT_RE.search(raw):
            inferred_kind = "exposure_context"
        else:
            labels = prune_compound_text_labels(raw, registry_compound_labels_in_text(raw, registry))
            if len(labels) > 1 or (COMPOUND_COMBO_TEXT_RE.search(raw) and labels):
                inferred_kind = "compound_combination"

    if inferred_kind in NON_ATOMIC_GRAPH_SUBJECT_KINDS:
        scope_exclusion = explicitly_out_of_scope_subject(row, raw, registry)
        if scope_exclusion:
            return scope_exclusion
        return {
            "matched": True,
            "label": raw,
            "item": {
                "label": raw,
                "aliases": [],
                "ids": {},
                "status": "preserved_non_atomic_exposure",
            },
            "status": "non_atomic_subject_preserved",
            "match_type": "preserved_non_atomic_exposure",
            "notes": f"{inferred_kind} preserved as one exposure unit; no atomic compound projection was made",
            "subject_kind": inferred_kind,
        }

    match = graphable_compound_match(raw, registry)
    if (
        not match["matched"]
        and match["status"] == "compound_unmapped"
        and validated_unregistered_compound_detail_subject(row, raw, registry)
    ):
        return validated_unregistered_compound_match(row, raw)
    match["subject_kind"] = "atomic_compound"
    return match


def ordered_graphable_compound_labels(
    value: object,
    registry: dict[tuple[str, str], dict],
) -> list[str]:
    """Return distinct in-scope compounds in textual order where possible."""

    raw_key = label_key(value)
    candidates = prune_compound_text_labels(value, registry_compound_labels_in_text(value, registry))
    labels: list[str] = []
    for candidate in candidates:
        candidate_match = graphable_compound_match(candidate, registry)
        label = normalize(candidate_match.get("label", "")) if candidate_match.get("matched") else ""
        if label and label not in labels:
            labels.append(label)

    positions: dict[str, int] = {label: len(raw_key) + 1 for label in labels}
    for (entity_type, key), item in registry.items():
        if entity_type != "compound" or not key:
            continue
        canonical = normalize(item.get("label", ""))
        if canonical not in positions:
            continue
        match = re.search(rf"\b{re.escape(key)}\b", raw_key)
        if match:
            positions[canonical] = min(positions[canonical], match.start())
    return sorted(labels, key=lambda label: (positions[label], label.casefold()))


def affirmatively_named_compound_labels(
    value: object,
    registry: dict[tuple[str, str], dict],
) -> list[str]:
    """Return named compounds while excluding negated names and prefixed analogs."""

    raw = normalize(value)
    raw_key = label_key(raw)
    labels = ordered_graphable_compound_labels(raw, registry)
    affirmative: list[str] = []
    for label in labels:
        matched_affirmatively = False
        for key in registry_keys_for_compound_label(label, registry):
            matches = list(re.finditer(rf"\b{re.escape(key)}\b", raw_key))
            if not matches:
                continue
            if " " not in key and not re.search(
                rf"(?<![A-Za-z0-9]-)\b{re.escape(key)}\b",
                raw,
                re.IGNORECASE,
            ):
                # Do not treat names such as 1P-LSD as affirmative mentions of LSD.
                continue
            if " " not in key and re.search(
                rf"\bnon[- ]?[A-Za-z0-9-]+/\s*{re.escape(key)}\b",
                raw,
                re.IGNORECASE,
            ):
                # A shared negation in labels such as non-psilocybin/LSD applies to both names.
                continue
            for match in matches:
                prefix = raw_key[max(0, match.start() - 40) : match.start()]
                suffix = raw_key[match.end() : match.end() + 32]
                if re.search(
                    r"\b(?:other than|except(?: for)?|excluding|without|not|non)\s*$",
                    prefix,
                    re.IGNORECASE,
                ):
                    continue
                if re.match(r"\s+equivalents?\b", suffix, re.IGNORECASE):
                    continue
                matched_affirmatively = True
                break
            if matched_affirmatively:
                break
        if matched_affirmatively:
            affirmative.append(label)
    return affirmative


def controlled_combination_labels(labels: list[str]) -> list[str]:
    by_key = {label_key(label): label for label in labels}
    definition = named_combination_for_components(labels)
    if definition:
        preferred = canonical_components(definition, labels)
        if all(label_key(label) in by_key for label in preferred):
            return [by_key[label_key(label)] for label in preferred]
    return sorted(labels, key=str.casefold)


def registry_keys_for_compound_label(
    label: str,
    registry: dict[tuple[str, str], dict],
) -> list[str]:
    keys = {
        key
        for (entity_type, key), item in registry.items()
        if entity_type == "compound" and normalize(item.get("label", "")) == label
    }
    return sorted(keys, key=lambda key: (-len(key), key))


def primary_named_compound_labels(
    raw: str,
    labels: list[str],
    registry: dict[tuple[str, str], dict],
) -> list[str]:
    """Resolve an explicitly predominant compound from otherwise broad exposure text."""

    raw_key = label_key(raw)
    cue = PRIMARY_COMPOUND_CUE_RE.search(raw_key)
    candidates: list[tuple[int, str]] = []
    if cue:
        cue_text = raw_key[cue.end() : cue.end() + 120]
        stop = re.search(r"\b(?:also|but|rather than|with practitioner|during|among)\b", cue_text, re.I)
        stop_at = stop.start() if stop else len(cue_text)
        for label in labels:
            for key in registry_keys_for_compound_label(label, registry):
                match = re.search(rf"\b{re.escape(key)}\b", cue_text)
                if match and match.start() < stop_at:
                    candidates.append((match.start(), label))
                    break
    if candidates and min(position for position, _label in candidates) <= 30:
        return list(dict.fromkeys(label for _position, label in sorted(candidates, key=lambda item: (item[0], item[1].casefold()))))

    for label in labels:
        for key in registry_keys_for_compound_label(label, registry):
            match = re.search(
                rf"\b{re.escape(key)}\b.{{0,40}}{PRIMARY_COMPOUND_REVERSE_CUE_RE.pattern}",
                raw_key,
                re.I,
            )
            if match:
                return [label]
    return []


def specific_assisted_therapy_compound_label(
    raw: str,
    labels: list[str],
    registry: dict[tuple[str, str], dict],
) -> str:
    """Recover the drug from a specifically named drug-assisted therapy or paradigm."""

    raw_key = label_key(raw)
    for label in labels:
        for key in registry_keys_for_compound_label(label, registry):
            assisted = re.search(
                rf"\b{re.escape(key)}\b\s+(?:assisted|facilitated)\s+"
                r"(?:psychotherapy|therapy|treatment)\b",
                raw_key,
                re.I,
            )
            route_paradigm = re.search(
                rf"\b(?:intravenous|intranasal|oral|sublingual|injected)\s+{re.escape(key)}\b.{{0,80}}"
                r"\bpsychedelic\s+(?:paradigm|approach|model)\b",
                raw_key,
                re.I,
            )
            if assisted or route_paradigm:
                return label
    return ""


def is_secondary_literature_row(row: dict) -> bool:
    if normalize(row.get("paper_assessment_route", "")).casefold() == "primary_evidence":
        return False
    markers = {
        normalize(row.get(field, "")).casefold()
        for field in ("paper_assessment_route", "source_type", "source_family", "paper_type", "access_level")
    }
    return bool(markers & SECONDARY_MARKERS or "secondary_summary" in markers)


def explicit_combination_projection(
    row: dict,
    raw: str,
    labels: list[str],
) -> dict | None:
    """Create a combination/regimen node only when the saved row says drugs were used together."""

    exact_text = normalize(raw)
    exact_evidence_text = " ".join(
        normalize(value)
        for value in (
            exact_text,
            row.get("dose_or_exposure", ""),
            row.get("dose", ""),
            row.get("administration_route", ""),
            row.get("route_of_administration", ""),
        )
        if normalize(value)
    )
    evidence_text = " ".join(
        normalize(row.get(field, ""))
        for field in COMBINATION_EVIDENCE_FIELDS
        if normalize(row.get(field, ""))
    )
    alias_evidence_text = " ".join(
        normalize(row.get(field, ""))
        for field in COMBINATION_ALIAS_EVIDENCE_FIELDS
        if normalize(row.get(field, ""))
    )
    named_definition = named_combination_from_text(f"{exact_text} {alias_evidence_text}".strip())
    if named_definition and len(named_definition["component_sets"]) == 1:
        labels = list(canonical_components(named_definition))
    sequential = bool(EXPLICIT_COMPOUND_SEQUENCE_RE.search(exact_evidence_text))
    if not sequential and len(labels) == 2:
        sequential = bool(
            re.search(r"\b(?:sequential|consecutive)\b", normalize(row.get("study_title", "")), re.I)
        )
    simultaneous = bool(named_definition) or bool(EXPLICIT_COMPOUND_COADMIN_RE.search(exact_evidence_text))
    if not simultaneous:
        linked_support_cue = re.search(
            r"\b(?:coadministered|co-administered|coadministration|co-administration|"
            r"administered (?:together|concurrently|simultaneously)|combined with|"
            r"formulation (?:containing|with)|concomitantly administered)\b",
            evidence_text,
            re.I,
        )
        simultaneous = bool(linked_support_cue)
    if re.search(r"\bor\b", exact_text, re.I) and "+" not in exact_text:
        simultaneous = False
        sequential = False
    label_keys = {label_key(label) for label in labels}
    dmt_harmala_formulation = "dmt" in label_keys and bool(label_keys & {"harmine", "harmaline"}) and bool(
        re.search(r"\b(?:dmt|n n dmt)[-/+ ]+(?:and )?harm(?:ine|aline)\b|\b(?:formulation|ayahuasca-inspired)\b", evidence_text, re.I)
    )
    if not (sequential or simultaneous or dmt_harmala_formulation):
        return None

    ordered = controlled_combination_labels(labels) if simultaneous else labels
    sequential_only = sequential and not simultaneous
    label = " + ".join(ordered)
    inferred_definition = named_combination_for_components(labels, infer_only=True)
    alias_definition = named_definition or inferred_definition
    alias = "" if sequential_only or not alias_definition else alias_definition["canonical_alias"]
    aliases = [] if sequential_only else aliases_for_components(labels)
    if named_definition:
        aliases = list(dict.fromkeys([*aliases, *named_definition["aliases"]]))
    if sequential_only:
        label = f"{label} (sequential)"
    elif alias:
        label = f"{label} ({alias})"
    return {
        "label": label,
        "kind": "treatment_regimen" if sequential_only else "compound_combination",
        "reason": (
            "specific_sequential_regimen"
            if sequential_only
            else "specific_named_combination_alias"
            if named_definition
            else "specific_combined_administration"
        ),
        "aliases": aliases,
    }


def registered_compound_overview_subject(
    compound_match: dict,
    registry: dict[tuple[str, str], dict],
) -> dict:
    """Return the controlled overview subject for one registered source label."""

    raw = normalize(compound_match.get("label", ""))
    source_item = compound_match.get("item") or {}
    overview_kind = normalized_entity_kind(source_item.get("graph_overview_subject_kind", ""))
    if overview_kind in NON_ATOMIC_GRAPH_SUBJECT_KINDS:
        return {
            "label": raw,
            "kind": overview_kind,
            "reason": "controlled_registered_exposure_kind",
            "aliases": [
                normalize(alias)
                for alias in source_item.get("aliases", [])
                if normalize(alias)
            ],
        }

    overview_compound = normalize(source_item.get("graph_overview_compound", ""))
    if overview_compound:
        overview_match = graphable_compound_match(overview_compound, registry)
        if overview_match.get("matched"):
            return {
                "label": normalize(overview_match.get("label", "")),
                "kind": "atomic_compound",
                "reason": "controlled_source_active_compound",
                "aliases": list(
                    dict.fromkeys(
                        [
                            raw,
                            *[
                                normalize(alias)
                                for alias in source_item.get("aliases", [])
                                if normalize(alias)
                            ],
                        ]
                    )
                ),
            }

    return {"label": raw, "kind": "atomic_compound", "reason": "controlled_atomic_compound"}


def explicit_overview_compound_class_subject(
    value: object,
    registry: dict[tuple[str, str], dict],
) -> dict | None:
    """Preserve an explicitly pooled class instead of assigning its examples to each drug."""

    raw = normalize(value)
    if not raw:
        return None
    named_labels = ordered_graphable_compound_labels(raw, registry)
    for pattern, label in OVERVIEW_SUBJECT_CLASS_RULES:
        class_match = pattern.search(raw)
        if not class_match:
            continue
        class_prefix = raw[max(0, class_match.start() - 12) : class_match.start()]
        if re.search(r"\b(?:non|not)[- ]?$", class_prefix, re.IGNORECASE):
            continue
        suffix = raw[class_match.end() :].lstrip()
        if named_labels and re.match(
            r"^(?:and\b|or\b|with\b|plus\b|versus\b|vs\.?\b|\+|/|&)",
            suffix,
            re.I,
        ):
            # This is a mixed class + named-compound exposure, not a pooled
            # class whose parenthetical merely lists examples or composition.
            continue
        return {
            "label": label,
            "kind": "compound_class",
            "reason": "controlled_compound_class",
        }
    return None


def _overview_graph_subjects(
    row: dict,
    compound_match: dict,
    registry: dict[tuple[str, str], dict],
) -> list[dict]:
    """Project an exact extracted exposure onto a small overview vocabulary.

    The exact exposure remains on the finding.  This projection is deliberately
    lossy: arbitrary mixtures, doses, and prose labels must not become unique
    overview nodes merely because they were extractable.
    """

    raw = normalize(compound_match.get("label", ""))
    kind = normalize(compound_match.get("subject_kind", "")) or "atomic_compound"
    secondary_literature = is_secondary_literature_row(row)
    if subject_label_is_explicitly_out_of_scope(raw, registry):
        recovered_subjects = finding_level_in_scope_subjects(row, registry)
        if recovered_subjects:
            return recovered_subjects
    if normalize(compound_match.get("match_type", "")) == "validated_unregistered_compound_detail_only":
        return []
    if kind == "atomic_compound":
        return [registered_compound_overview_subject(compound_match, registry)]

    focal = normalize(row.get("atomic_compound_candidate", ""))

    if kind == "exposure_context":
        context_text = f"{raw} {focal}".strip()
        for pattern, label in OVERVIEW_SUBJECT_CONTEXT_RULES:
            if pattern.search(context_text):
                return [{"label": label, "kind": "exposure_context", "reason": "controlled_exposure_context"}]
        return []

    focal_match = graphable_compound_match(focal, registry) if focal else {"matched": False}

    if kind == "compound_class":
        subject_context = " ".join(
            [raw, focal]
            + [
                normalize(row.get(field, ""))
                for field in PSYCHEDELIC_SUBJECT_CONTEXT_FIELDS
                if normalize(row.get(field, ""))
            ]
        )
        explicit_class_subject = explicit_overview_compound_class_subject(
            subject_context,
            registry,
        )
        if explicit_class_subject:
            if explicit_class_subject["label"] == "Entheogens":
                return [{
                    "label": BROAD_PSYCHEDELIC_CLASS_LABEL
                    if secondary_literature
                    else UNRESOLVED_PSYCHEDELIC_SUBJECT_LABEL,
                    "kind": "compound_class",
                    "reason": "controlled_broad_psychedelic_class"
                    if secondary_literature
                    else "controlled_unresolved_psychedelic_class_detail_only",
                }]
            return [explicit_class_subject]
        if focal_match.get("matched"):
            return [{
                "label": normalize(focal_match.get("label", "")),
                "kind": "atomic_compound",
                "reason": "specific_compound_recovered_from_class_text",
            }]
        named_labels = ordered_graphable_compound_labels(raw, registry)
        concrete_labels: list[str] = []
        if not secondary_literature:
            concrete_labels = primary_named_compound_labels(raw, named_labels, registry)
            therapy_label = specific_assisted_therapy_compound_label(raw, named_labels, registry)
            if therapy_label:
                concrete_labels = [therapy_label]
        if concrete_labels:
            return [
                {
                    "label": concrete_label,
                    "kind": "atomic_compound",
                    "reason": "predominant_or_specific_therapy_compound_recovered_from_class_text",
                }
                for concrete_label in concrete_labels
            ]
        if len(named_labels) > 1 and not secondary_literature:
            projected_labels = named_labels
            if GENERIC_PSYCHEDELIC_CLASS_RE.search(raw):
                projected_labels = affirmatively_named_compound_labels(raw, registry)
            if projected_labels:
                return [
                    {
                        "label": label,
                        "kind": "atomic_compound",
                        "reason": "specific_compounds_recovered_from_class_text",
                    }
                    for label in projected_labels
                ]
        if len(named_labels) == 1 and not secondary_literature and GENERIC_PSYCHEDELIC_CLASS_RE.search(raw):
            affirmative_labels = affirmatively_named_compound_labels(raw, registry)
            if affirmative_labels:
                return [
                    {
                        "label": label,
                        "kind": "atomic_compound",
                        "reason": "specific_compounds_recovered_from_class_text",
                    }
                    for label in affirmative_labels
                ]
        if SPECIFIC_COMPOUND_WITH_CLASS_PARENTHETICAL_RE.search(raw):
            return []
        if GENERIC_PSYCHEDELIC_CLASS_RE.search(raw):
            context = " ".join(
                normalize(row.get(field, ""))
                for field in PSYCHEDELIC_OVERVIEW_CONTEXT_FIELDS
                if normalize(row.get(field, ""))
            )
            context_with_raw = f"{raw} {context}".strip()
            if PSYCHEDELIC_THERAPY_RE.search(raw):
                return [{
                    "label": "Psychedelic-assisted therapy",
                    "kind": "treatment_regimen",
                    "reason": "controlled_broad_psychedelic_therapy",
                }]
            mentioned_compounds = registry_compound_labels_in_text(context, registry)
            if len(mentioned_compounds) > 1 or PSYCHEDELIC_MIXED_CONTEXT_RE.search(context_with_raw):
                return [{
                    "label": BROAD_PSYCHEDELIC_CLASS_LABEL
                    if secondary_literature
                    else UNRESOLVED_PSYCHEDELIC_SUBJECT_LABEL,
                    "kind": "compound_class",
                    "reason": "controlled_multiple_psychedelic_class"
                    if secondary_literature
                    else "controlled_unresolved_psychedelic_class_detail_only",
                }]
            if PSYCHEDELIC_SEROTONERGIC_CONTEXT_RE.search(context_with_raw):
                return [{
                    "label": "Classic psychedelics",
                    "kind": "compound_class",
                    "reason": "controlled_serotonergic_psychedelic_class",
                }]
            return [{
                "label": BROAD_PSYCHEDELIC_CLASS_LABEL
                if secondary_literature
                else UNRESOLVED_PSYCHEDELIC_SUBJECT_LABEL,
                "kind": "compound_class",
                "reason": "controlled_broad_psychedelic_class"
                if secondary_literature
                else "controlled_unresolved_psychedelic_class_detail_only",
            }]
        return []

    if kind in {"compound_combination", "treatment_regimen"}:
        if focal_match.get("matched"):
            return [{
                "label": normalize(focal_match.get("label", "")),
                "kind": "atomic_compound",
                "reason": "focal_compound_with_exposure_detail",
            }]
        labels = ordered_graphable_compound_labels(raw, registry)
        named_context = " ".join(
            [raw]
            + [
                normalize(row.get(field, ""))
                for field in COMBINATION_ALIAS_EVIDENCE_FIELDS
                if normalize(row.get(field, ""))
            ]
        )
        named_definition = named_combination_from_text(named_context)
        if named_definition and len(named_definition["component_sets"]) == 1:
            labels = list(canonical_components(named_definition))
        if len(labels) == 1:
            return [{
                "label": labels[0],
                "kind": "atomic_compound",
                "reason": "single_in_scope_compound_with_exposure_detail",
            }]
        if len(labels) > 1:
            combination = explicit_combination_projection(row, raw, labels)
            if combination:
                if re.search(r"\bor\b", raw, re.I) and "+" in raw:
                    atomic_subjects = [
                        {
                            "label": label,
                            "kind": "atomic_compound",
                            "reason": "specific_compound_arm_alongside_combination",
                        }
                        for label in labels
                    ]
                    return [*atomic_subjects, combination]
                return [combination]
            return [
                {
                    "label": label,
                    "kind": "atomic_compound",
                    "reason": "specific_compounds_separated_from_multi_compound_text",
                }
                for label in labels
            ]
        return []

    return []


def overview_graph_subjects(
    row: dict,
    compound_match: dict,
    registry: dict[tuple[str, str], dict],
) -> list[dict]:
    """Normalize every final atomic overview subject, including list projections."""

    subjects = _overview_graph_subjects(row, compound_match, registry)
    normalized_subjects: list[dict] = []
    by_key: dict[tuple[str, str], dict] = {}
    for subject in subjects:
        normalized_subject = dict(subject)
        if normalize(subject.get("kind", "")).casefold() == "atomic_compound":
            subject_match = graphable_compound_match(subject.get("label", ""), registry)
            if subject_match.get("matched"):
                registered_subject = registered_compound_overview_subject(subject_match, registry)
                if registered_subject.get("reason") != "controlled_atomic_compound":
                    normalized_subject = registered_subject
                    normalized_subject["aliases"] = list(
                        dict.fromkeys(
                            [
                                *[
                                    normalize(alias)
                                    for alias in subject.get("aliases", [])
                                    if normalize(alias)
                                ],
                                *[
                                    normalize(alias)
                                    for alias in registered_subject.get("aliases", [])
                                    if normalize(alias)
                                ],
                            ]
                        )
                    )

        key = (
            normalize(normalized_subject.get("label", "")).casefold(),
            normalize(normalized_subject.get("kind", "")).casefold(),
        )
        if not key[0]:
            continue
        existing = by_key.get(key)
        if existing is None:
            by_key[key] = normalized_subject
            normalized_subjects.append(normalized_subject)
            continue
        aliases = list(
            dict.fromkeys(
                [
                    *[
                        normalize(alias)
                        for alias in existing.get("aliases", [])
                        if normalize(alias)
                    ],
                    *[
                        normalize(alias)
                        for alias in normalized_subject.get("aliases", [])
                        if normalize(alias)
                    ],
                ]
            )
        )
        if aliases:
            existing["aliases"] = aliases
        if normalized_subject.get("reason") in {
            "controlled_source_active_compound",
            "controlled_registered_exposure_kind",
        }:
            existing["reason"] = normalized_subject["reason"]

    return normalized_subjects


USE_CONTEXT_EVIDENCE_FIELDS = (
    "graph_subject_label",
    "compound_or_exposure",
    "compound_or_intervention",
    "intervention_or_exposure",
    "exposure_or_intervention",
    "exposure_or_policy",
    "co_exposure_or_modifier",
    "atomic_compound_candidate",
    "finding_summary",
    "summary_statement",
    "support",
    "supporting_quote",
)
USE_CONTEXT_COMPONENT_FIELDS = (
    "graph_subject_label",
    "compound_or_exposure",
    "compound_or_intervention",
    "intervention_or_exposure",
    "exposure_or_intervention",
    "exposure_or_policy",
    "co_exposure_or_modifier",
    "atomic_compound_candidate",
)


def graph_use_context_projections(
    row: dict,
    domain: str,
    overview_subjects: list[dict],
    registry: dict[tuple[str, str], dict],
) -> list[dict]:
    """Create explicit substance -> real-world use-context projections.

    Context evidence is limited to finding-level fields; titles and paper-wide
    keywords are deliberately excluded so unrelated findings are not projected
    merely because a paper discusses chemsex somewhere.
    """

    if normalize(domain).casefold() != "real_world_public_health":
        return []

    controlled_contexts = [
        normalize(subject.get("label", ""))
        for subject in overview_subjects
        if normalize(subject.get("kind", "")).casefold() == "exposure_context"
        and use_context_definition(subject.get("label", ""))
    ]
    evidence_text = " ".join(
        normalize(row.get(field, ""))
        for field in USE_CONTEXT_EVIDENCE_FIELDS
        if normalize(row.get(field, ""))
    )
    context_label = controlled_contexts[0] if controlled_contexts else use_context_label_from_text(evidence_text)
    definition = use_context_definition(context_label)
    if definition is None:
        return []

    component_text = " ".join(
        normalize(row.get(field, ""))
        for field in USE_CONTEXT_COMPONENT_FIELDS
        if normalize(row.get(field, ""))
    )
    components: list[dict] = []
    seen: set[str] = set()

    # If the finding already has an atomic subject, the source-level context
    # statement applies directly to it even when the exposure field is terse.
    for subject in overview_subjects:
        label = normalize(subject.get("label", ""))
        if normalize(subject.get("kind", "")).casefold() != "atomic_compound" or not label or label in seen:
            continue
        seen.add(label)
        components.append(
            {
                "label": label,
                "kind": "atomic_compound",
                "aliases": [normalize(alias) for alias in subject.get("aliases", []) if normalize(alias)],
            }
        )

    for label in sorted(registry_compound_labels_in_text(component_text, registry), key=str.casefold):
        if not label or label in seen:
            continue
        seen.add(label)
        item = registry.get(("compound", label_key(label)), {})
        components.append(
            {
                "label": label,
                "kind": "atomic_compound",
                "aliases": [normalize(alias) for alias in item.get("aliases", []) if normalize(alias)],
            }
        )

    scoped_components: list[dict] = []
    scoped_seen: set[str] = set()
    for component in components:
        scope_match = graphable_compound_match(component.get("label", ""), registry)
        if not scope_match.get("matched"):
            continue
        registered_subject = registered_compound_overview_subject(scope_match, registry)
        label = normalize(registered_subject.get("label", ""))
        subject_kind = normalize(registered_subject.get("kind", "")) or "atomic_compound"
        if not label or label in scoped_seen:
            continue
        scoped_seen.add(label)
        item = scope_match.get("item") or {}
        scoped_components.append(
            {
                "label": label,
                "kind": subject_kind,
                "aliases": list(
                    dict.fromkeys(
                        [
                            *[
                                normalize(alias)
                                for alias in item.get("aliases", [])
                                if normalize(alias)
                            ],
                            *[
                                normalize(alias)
                                for alias in component.get("aliases", [])
                                if normalize(alias)
                            ],
                            *[
                                normalize(alias)
                                for alias in registered_subject.get("aliases", [])
                                if normalize(alias)
                            ],
                        ]
                    )
                ),
            }
        )

    return [
        {
            "projection_type": "use_context",
            "subject_label": component["label"],
            "subject_kind": component.get("kind", "atomic_compound"),
            "subject_aliases": component.get("aliases", []),
            "context_label": definition.label,
            "context_kind": "exposure_context",
            "context_aliases": list(definition.aliases),
            "context_parent_label": definition.parent,
            "context_parent_kind": "exposure_context" if definition.parent else "",
            "context_parent_entity_id": entity_id_for("compound", definition.parent) if definition.parent else "",
            "relation_type": "reported_in_use_context",
            "reason": "explicit_finding_level_substance_use_context",
        }
        for component in scoped_components
    ]


def overview_graph_subject(
    row: dict,
    compound_match: dict,
    registry: dict[tuple[str, str], dict],
) -> dict:
    """Compatibility wrapper for singular table fields; JSON carries all projections."""

    subjects = overview_graph_subjects(row, compound_match, registry)
    return subjects[0] if subjects else {"label": "", "kind": "", "reason": "uncontrolled_subject_detail_only"}


def registry_entity_labels_in_text(value: object, entity_type: str, registry: dict[tuple[str, str], dict]) -> set[str]:
    text_key = label_key(value)
    if not text_key:
        return set()
    cache_key = (id(registry), entity_type, text_key)
    cached = _REGISTRY_ENTITY_TEXT_CACHE.get(cache_key)
    if cached is not None:
        return set(cached)
    labels: set[str] = set()
    for candidate_entity_type, key in registry:
        if candidate_entity_type != entity_type or len(key) < 3:
            continue
        if key == "net" and re.search(r"\bperineuronal net\b", text_key):
            continue
        if re.search(rf"\b{re.escape(key)}\b", text_key):
            labels.add(normalize(registry[(candidate_entity_type, key)].get("label", "")))
    result = {label for label in labels if label}
    _REGISTRY_ENTITY_TEXT_CACHE[cache_key] = frozenset(result)
    return result


CONDITION_LABEL_SUPERSEDES = {
    "Alcohol use disorder": {"Substance use disorder"},
    "Anorexia nervosa": {"Eating disorders"},
    "Bipolar depression": {"Bipolar disorder", "Depressive disorders", "Mood disorders"},
    "Bipolar I disorder": {"Bipolar disorder", "Mood disorders"},
    "Bipolar II disorder": {"Bipolar disorder", "Mood disorders"},
    "Bipolar disorder": {"Mood disorders"},
    "Cannabis use disorder": {"Substance use disorder"},
    "Chronic pain": {"Pain conditions"},
    "Cluster headache": {"Headache disorders", "Pain conditions"},
    "Cocaine use disorder": {"Substance use disorder"},
    "Complex regional pain syndrome": {"Pain conditions"},
    "Distress associated with life-threatening disease": {"Anxiety disorders"},
    "Fibromyalgia": {"Pain conditions"},
    "Generalized anxiety disorder": {"Anxiety disorders"},
    "Headache disorders": {"Pain conditions"},
    "Major depressive disorder": {"Depressive disorders", "Mood disorders"},
    "Methamphetamine use disorder": {"Stimulant use disorder", "Substance use disorder"},
    "Migraine": {"Headache disorders", "Pain conditions"},
    "Neuropathic pain": {"Pain conditions"},
    "Opioid use disorder": {"Substance use disorder"},
    "Persistent depressive disorder": {"Depressive disorders", "Mood disorders"},
    "Social anxiety disorder": {"Anxiety disorders"},
    "Stimulant use disorder": {"Substance use disorder"},
    "Tobacco use disorder": {"Substance use disorder"},
    "Treatment-resistant depression": {"Depressive disorders", "Major depressive disorder", "Mood disorders"},
}
NON_GRAPHABLE_BROAD_CONDITION_LABELS = {
    "Anxiety disorders",
    "Depressive disorders",
    "Pain conditions",
}
BROAD_CONDITION_CONTEXT_FIELDS = (
    "clinical_context_condition",
    "population",
    "population_or_subgroup",
    "condition_or_population",
    "finding_summary",
    "support",
    "study_title",
)
CONDITION_ANALOG_CONTEXT_RE = re.compile(
    r"\b("
    r"\w+(?:[- ]like)\s+(?:symptoms?|effects?|behavio(?:u)?rs?|phenotypes?|states?|responses?|profiles?)|"
    r"(?:psychosis|psychotic|schizophrenia|depression|anxiety|mania|ptsd|autism)[- ]like|"
    r"psychotomimetic|"
    r"(?:model|models|modeling|modelling|paradigm)\s+(?:of|for|relevant to)\s+"
    r"(?:schizophrenia|psychosis|depression|anxiety|mania|ptsd|autism)|"
    r"(?:ketamine|phencyclidine|pcp|nmda antagonist)[- ](?:model|challenge)|"
    r"induc(?:e|ed|es|ing)\s+.{0,80}(?:[- ]like\s+)?(?:symptoms?|effects?|behavio(?:u)?rs?)"
    r")\b",
    re.IGNORECASE,
)
SUBJECTIVE_EFFECT_CONTEXT_RE = re.compile(
    r"\b("
    r"psychotomimetic|psychosis[- ]like|psychotic[- ]like|schizophrenia[- ]like|"
    r"dissociation|dissociative|depersonalization|depersonalisation|derealization|derealisation|"
    r"perceptual alterations?|perceptual changes?|hallucinations?|hallucinogenic|"
    r"subjective (?:drug )?effects?|altered states?|cadss|panss|bprs"
    r")\b",
    re.IGNORECASE,
)
NON_CLINICAL_MODEL_POPULATION_RE = re.compile(
    r"\b("
    r"healthy\s+(?:human\s+)?(?:volunteers?|participants?|controls?|subjects?)|"
    r"human\s+volunteers?|"
    r"drug\s+challenge|ketamine\s+challenge|experimental\s+challenge|"
    r"healthy_volunteers|mouse|mice|rat|rats|rodent|animal\s+model|preclinical|"
    r"in\s+vitro|ex\s+vivo|cell\s+model"
    r")\b",
    re.IGNORECASE,
)
CONDITION_NON_INDICATION_CONTEXT_RE = re.compile(
    r"\b(?:family history of|familial risk (?:of|for))\b",
    re.IGNORECASE,
)


def prune_condition_labels(labels: set[str]) -> list[str]:
    pruned = set(labels)
    for specific, broad_labels in CONDITION_LABEL_SUPERSEDES.items():
        if specific in pruned:
            pruned -= broad_labels
    pruned -= NON_GRAPHABLE_BROAD_CONDITION_LABELS
    return sorted(pruned, key=lambda label: (-len(label), label.casefold()))


def condition_labels_in_text(value: object, registry: dict[tuple[str, str], dict]) -> list[str]:
    if condition_analog_text(value):
        return []
    return prune_condition_labels(registry_entity_labels_in_text(value, "clinical_entity", registry))


def specific_condition_from_unambiguous_context(
    row: dict | None,
    raw_label: object,
    broad_label: str,
    registry: dict[tuple[str, str], dict],
) -> str:
    """Resolve a broad condition only when context names one subtype from the same family."""

    row = row or {}
    raw_key = label_key(raw_label)
    allowed_labels = {
        specific_label
        for specific_label, superseded_labels in CONDITION_LABEL_SUPERSEDES.items()
        if broad_label in superseded_labels
    }
    if not allowed_labels:
        return ""
    candidates: set[str] = set()
    for field in BROAD_CONDITION_CONTEXT_FIELDS:
        value = normalize(row.get(field, ""))
        if not value or label_key(value) == raw_key:
            continue
        candidates.update(
            label
            for label in condition_labels_in_text(value, registry)
            if label in allowed_labels
        )
    labels = prune_condition_labels(candidates)
    return labels[0] if len(labels) == 1 else ""


def condition_analog_text(value: object) -> bool:
    text = normalize(value)
    return bool(text and CONDITION_ANALOG_CONTEXT_RE.search(text))


def condition_analog_context(row: dict | None, raw_label: object = "") -> bool:
    row = row or {}
    focal_text = " ".join(
        normalize(value)
        for value in (
            raw_label,
            row.get("condition_or_indication", ""),
            row.get("condition_or_population", ""),
            row.get("clinical_context_condition", ""),
            row.get("clinical_endpoint", ""),
            row.get("outcome_domain", ""),
        )
        if normalize(value)
    )
    if condition_analog_text(focal_text):
        return True

    context_text = " ".join(
        normalize(value)
        for value in (
            focal_text,
            row.get("finding_summary", ""),
            row.get("support", ""),
            row.get("study_title", ""),
            row.get("keywords", ""),
        )
        if normalize(value)
    )
    population_text = " ".join(
        normalize(value)
        for value in (
            row.get("population", ""),
            row.get("population_or_subgroup", ""),
            row.get("population_model_category", ""),
            row.get("model_or_system", ""),
            row.get("species", ""),
        )
        if normalize(value)
    )
    return bool(
        context_text
        and CONDITION_ANALOG_CONTEXT_RE.search(context_text)
        and population_text
        and NON_CLINICAL_MODEL_POPULATION_RE.search(population_text)
    )


def clinical_subjective_effect_context(row: dict | None) -> bool:
    row = row or {}
    context_text = " ".join(
        normalize(value)
        for value in (
            row.get("condition_or_indication", ""),
            row.get("condition_or_population", ""),
            row.get("clinical_context_condition", ""),
            row.get("clinical_endpoint", ""),
            row.get("outcome_measure", ""),
            row.get("outcome_measure_normalized", ""),
            row.get("finding_summary", ""),
            row.get("support", ""),
            row.get("study_title", ""),
            row.get("keywords", ""),
        )
        if normalize(value)
    )
    population_text = " ".join(
        normalize(value)
        for value in (
            row.get("population", ""),
            row.get("population_or_subgroup", ""),
            row.get("population_model_category", ""),
            row.get("model_or_system", ""),
            row.get("species", ""),
        )
        if normalize(value)
    )
    return bool(
        context_text
        and SUBJECTIVE_EFFECT_CONTEXT_RE.search(context_text)
        and population_text
        and NON_CLINICAL_MODEL_POPULATION_RE.search(population_text)
    )


BRAIN_SYSTEM_ENTITY_KINDS = ("brain_region", "brain_network", "neural_circuit")
BRAIN_TEXT_MATCH_SHORT_KEYS = {"dmn", "pcc", "drn", "fpn", "dan", "cen", "sal", "pag", "rsp"}
BRAIN_RELATIONAL_LABEL_RE = re.compile(
    r"\b(connectivity|coupling|projection|pathway|circuit|between|from|to)\b|[-–—]",
    re.IGNORECASE,
)
BRAIN_LIST_SEPARATOR_RE = re.compile(r"[;,/+]")


def node_vocabulary_key_allowed_in_text(entity_kind: str, key: str) -> bool:
    if len(key) >= 4:
        return True
    return entity_kind in BRAIN_SYSTEM_ENTITY_KINDS and key in BRAIN_TEXT_MATCH_SHORT_KEYS


def node_vocabulary_labels_in_text(value: object, entity_kind: str, node_vocabulary: dict[tuple[str, str], dict]) -> set[str]:
    text_key = label_key(value)
    if not text_key:
        return set()
    labels: set[str] = set()
    for candidate_kind, key in node_vocabulary:
        if candidate_kind != entity_kind or not node_vocabulary_key_allowed_in_text(candidate_kind, key):
            continue
        if re.search(rf"\b{re.escape(key)}\b", text_key):
            labels.add(normalize(node_vocabulary[(candidate_kind, key)].get("label", "")))
    return {label for label in labels if label}


def node_vocabulary_hits_in_text(
    value: object,
    entity_kinds: Iterable[str],
    node_vocabulary: dict[tuple[str, str], dict],
) -> list[tuple[str, str]]:
    text_key = label_key(value)
    if not text_key:
        return []
    allowed_kinds = set(entity_kinds)
    hits: dict[tuple[str, str], tuple[int, int]] = {}
    for candidate_kind, key in node_vocabulary:
        if candidate_kind not in allowed_kinds or not node_vocabulary_key_allowed_in_text(candidate_kind, key):
            continue
        match = re.search(rf"\b{re.escape(key)}\b", text_key)
        if not match:
            continue
        label = normalize(node_vocabulary[(candidate_kind, key)].get("label", ""))
        if not label:
            continue
        hit_key = (candidate_kind, label)
        score = (match.start(), -len(key))
        if hit_key not in hits or score < hits[hit_key]:
            hits[hit_key] = score
    return [hit for hit, _score in sorted(hits.items(), key=lambda item: item[1])]


def exact_node_vocabulary_matches(
    value: object,
    entity_kinds: Iterable[str],
    node_vocabulary: dict[tuple[str, str], dict],
) -> list[tuple[str, str]]:
    matches: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for entity_kind in entity_kinds:
        label, item = canonicalize_node_label(entity_kind, normalize(value), node_vocabulary)
        if not item:
            continue
        match = (entity_kind, label)
        if match in seen:
            continue
        seen.add(match)
        matches.append(match)
    return matches


def literal_node_vocabulary_hits_in_text(
    value: object,
    entity_kinds: Iterable[str],
    node_vocabulary: dict[tuple[str, str], dict],
) -> list[tuple[str, str]]:
    """Match only explicit vocabulary labels or aliases in evidence text.

    The broader node-vocabulary matcher intentionally supports normalized key
    variants for entity labels. Evidence-text projection is more conservative:
    it must not turn a generated abbreviation or ontology normalization into a
    brain region that the evidence did not actually name.
    """

    text_key = label_key(value)
    if not text_key:
        return []
    allowed_kinds = set(entity_kinds)
    candidates: dict[tuple[str, str], dict] = {}
    for (entity_kind, _key), item in node_vocabulary.items():
        if entity_kind not in allowed_kinds:
            continue
        label = normalize(item.get("label", ""))
        if label:
            candidates[(entity_kind, label)] = item

    hits: dict[tuple[str, str], tuple[int, int]] = {}
    for (entity_kind, label), item in candidates.items():
        literals = [label, *item.get("aliases", [])]
        for literal in literals:
            literal_key = label_key(literal)
            if not literal_key or not node_vocabulary_key_allowed_in_text(entity_kind, literal_key):
                continue
            match = re.search(rf"\b{re.escape(literal_key)}\b", text_key)
            if not match:
                continue
            hit_key = (entity_kind, label)
            score = (match.start(), -len(literal_key))
            if hit_key not in hits or score < hits[hit_key]:
                hits[hit_key] = score

    parent_by_hit = {
        (entity_kind, label): normalize(candidates[(entity_kind, label)].get("parent", ""))
        for entity_kind, label in hits
    }

    def has_descendant_in_hits(entity_kind: str, label: str) -> bool:
        for descendant_kind, descendant_label in hits:
            if descendant_kind != entity_kind or descendant_label == label:
                continue
            parent = parent_by_hit.get((descendant_kind, descendant_label), "")
            seen: set[str] = set()
            while parent and parent not in seen:
                if parent == label:
                    return True
                seen.add(parent)
                parent = normalize(candidates.get((entity_kind, parent), {}).get("parent", ""))
        return False

    specific_hits = {
        hit: score
        for hit, score in hits.items()
        if not has_descendant_in_hits(*hit)
    }
    return [hit for hit, _score in sorted(specific_hits.items(), key=lambda item: item[1])]


META_ANALYSIS_BRAIN_PROJECTION_MAX_ENTITIES = 12
META_ANALYSIS_TARGET_PROJECTION_MAX_ENTITIES = 12
BRAIN_ENTITY_SPLIT_MAX_PARTS = 24


def meta_analysis_brain_support_matches(
    row: dict,
    domain: str,
    entity_kind: str,
    node_vocabulary: dict[tuple[str, str], dict],
) -> list[tuple[str, str]]:
    source_type = normalize(row.get("source_type", "") or row.get("paper_type", "")).casefold()
    if (
        normalize(domain).casefold() != "brain_system"
        or source_type not in {"meta_analysis", "network_meta_analysis"}
    ):
        return []
    raw_label = entity_label_for(row, domain, entity_kind)
    if exact_node_vocabulary_matches(raw_label, BRAIN_SYSTEM_ENTITY_KINDS, node_vocabulary):
        return []
    evidence_text = " ".join(
        normalize(row.get(field, ""))
        for field in ("support", "finding_summary", "supporting_quote")
        if normalize(row.get(field, ""))
    )
    matches = literal_node_vocabulary_hits_in_text(
        evidence_text,
        BRAIN_SYSTEM_ENTITY_KINDS,
        node_vocabulary,
    )
    return matches if 1 <= len(matches) <= META_ANALYSIS_BRAIN_PROJECTION_MAX_ENTITIES else []


def registry_item_for_label(
    label: str,
    registry: dict[tuple[str, str], dict],
) -> dict | None:
    _canonical, item = canonicalize_registry_label("mechanistic_entity", label, registry)
    return item


def target_label_ancestors(
    label: str,
    registry: dict[tuple[str, str], dict],
) -> set[str]:
    ancestors: set[str] = set()
    current = registry_item_for_label(label, registry)
    while current:
        parent = normalize(current.get("parent", ""))
        if not parent or parent in ancestors:
            break
        ancestors.add(parent)
        current = registry_item_for_label(parent, registry)
    return ancestors


def explicit_target_labels_in_text(
    value: object,
    registry: dict[tuple[str, str], dict],
) -> list[tuple[str, str]]:
    text = normalize(value)
    text_key = label_key(text)
    if not text_key:
        return []

    labels = set(registry_entity_labels_in_text(text, "mechanistic_entity", registry))
    short_target_alias_re = re.compile(
        r"^(?:d[1-5]|htr\d[a-z]?|5 ht\d[a-z]?|sert|dat|net|vmat\d?|oprm\d|oprd\d|oprk\d)$",
        re.IGNORECASE,
    )
    seen_items: set[int] = set()
    for (entity_type, _key), item in registry.items():
        if entity_type != "mechanistic_entity" or id(item) in seen_items:
            continue
        seen_items.add(id(item))
        candidates = [
            normalize(item.get("label", "")),
            *[normalize(alias) for alias in item.get("aliases", []) if normalize(alias)],
        ]
        if any(
            short_target_alias_re.fullmatch(label_key(candidate))
            and re.search(rf"\b{re.escape(label_key(candidate))}\b", text_key)
            for candidate in candidates
        ):
            labels.add(normalize(item.get("label", "")))

    typed: dict[str, str] = {}
    for label in labels:
        item = registry_item_for_label(label, registry)
        kind = registry_kind_for_item("target", item, text, label)
        if kind in {"target", "system_family"}:
            typed[label] = kind

    ancestor_labels = {
        ancestor
        for label in typed
        for ancestor in target_label_ancestors(label, registry)
        if ancestor in typed
    }
    retained = [(kind, label) for label, kind in typed.items() if label not in ancestor_labels]
    return sorted(retained, key=lambda item: text_key.find(label_key(item[1])))


def structured_target_entity_matches(
    row: dict,
) -> list[tuple[str, str]]:
    raw = row.get("molecular_target_entities_json", "") or row.get("molecular_target_entities", [])
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            return []
    if not isinstance(raw, list):
        return []
    matches: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        kind = normalized_entity_kind(item.get("entity_type", ""))
        label = normalize(item.get("label", ""))
        match = (kind, label)
        if kind not in {"target", "system_family"} or not label or match in seen:
            continue
        seen.add(match)
        matches.append(match)
    return matches


def meta_analysis_target_support_matches(
    row: dict,
    domain: str,
    entity_kind: str,
    registry: dict[tuple[str, str], dict],
) -> list[tuple[str, str]]:
    source_type = normalize(row.get("source_type", "") or row.get("paper_type", "")).casefold()
    if (
        normalize(domain).casefold() != "molecular_target"
        or entity_kind not in {"target", "system_family"}
        or source_type not in {"meta_analysis", "network_meta_analysis"}
    ):
        return []
    raw_label = entity_label_for(row, domain, entity_kind)
    if match_registry_entity(raw_label, entity_kind, registry, row=row)["matched"]:
        return []
    evidence_text = " ".join(
        normalize(row.get(field, ""))
        for field in ("support", "finding_summary", "supporting_quote")
        if normalize(row.get(field, ""))
    )
    matches = explicit_target_labels_in_text(evidence_text, registry)
    return matches if 1 <= len(matches) <= META_ANALYSIS_TARGET_PROJECTION_MAX_ENTITIES else []


def brain_entity_list_parts(value: object) -> list[str]:
    text = normalize(value)
    if not text or not BRAIN_LIST_SEPARATOR_RE.search(text):
        return []
    working = text.replace("；", ";")
    working = re.sub(r"\s+and/or\s+", ";", working, flags=re.IGNORECASE)
    working = re.sub(r"\s*[;,/+]\s*", ";", working)
    working = re.sub(r";\s+(?:and|or)\s+", ";", working, flags=re.IGNORECASE)
    working = re.sub(r"\s+", " ", working).strip("; ")
    parts = [re.sub(r"^(?:and|or)\s+", "", normalize(part).strip(" ."), flags=re.IGNORECASE) for part in working.split(";")]
    return [part for part in parts if part]


def brain_entity_split_matches(
    raw_label: object,
    node_vocabulary: dict[tuple[str, str], dict],
) -> list[tuple[str, str]]:
    raw = normalize(raw_label)
    if not raw:
        return []

    parts = brain_entity_list_parts(raw)
    if parts:
        if len(parts) > BRAIN_ENTITY_SPLIT_MAX_PARTS:
            return []
        matches: list[tuple[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for part in parts:
            part_matches = exact_node_vocabulary_matches(part, BRAIN_SYSTEM_ENTITY_KINDS, node_vocabulary)
            if not part_matches:
                contained_matches = node_vocabulary_hits_in_text(part, BRAIN_SYSTEM_ENTITY_KINDS, node_vocabulary)
                if len(contained_matches) == 1 or BRAIN_RELATIONAL_LABEL_RE.search(part):
                    part_matches = contained_matches
            if not part_matches:
                continue
            for match in part_matches:
                if match in seen:
                    continue
                seen.add(match)
                matches.append(match)
        if len(matches) <= BRAIN_ENTITY_SPLIT_MAX_PARTS:
            return matches
        return []

    if not BRAIN_RELATIONAL_LABEL_RE.search(raw):
        return []
    matches = node_vocabulary_hits_in_text(raw, BRAIN_SYSTEM_ENTITY_KINDS, node_vocabulary)
    return matches if 1 < len(matches) <= BRAIN_ENTITY_SPLIT_MAX_PARTS else []


def match_brain_vocabulary_entity(
    raw_label: str,
    preferred_kind: str,
    node_vocabulary: dict[tuple[str, str], dict],
) -> dict:
    exact_matches = exact_node_vocabulary_matches(raw_label, BRAIN_SYSTEM_ENTITY_KINDS, node_vocabulary)
    if len(exact_matches) == 1:
        kind, label = exact_matches[0]
        _, item = canonicalize_node_label(kind, label, node_vocabulary)
        return {
            "matched": True,
            "label": label,
            "kind": kind,
            "item": item,
            "status": "entity_normalized",
            "match_type": "node_vocabulary",
            "notes": "brain-system entity matched route-native node vocabulary",
        }
    if len(exact_matches) > 1:
        return {
            "matched": False,
            "label": "",
            "kind": preferred_kind,
            "item": None,
            "status": "entity_combo_not_graphable",
            "match_type": "",
            "notes": "brain-system entity text contains multiple graph entities; graph rows need one entity per edge",
        }

    if brain_entity_list_parts(raw_label):
        split_matches = brain_entity_split_matches(raw_label, node_vocabulary)
        if len(split_matches) > 1:
            return {
                "matched": False,
                "label": "",
                "kind": preferred_kind,
                "item": None,
                "status": "entity_combo_not_graphable",
                "match_type": "",
                "notes": "brain-system entity text contains multiple graph entities; graph rows need one entity per edge",
            }
        if len(split_matches) == 1:
            kind, label = split_matches[0]
            _, item = canonicalize_node_label(kind, label, node_vocabulary)
            return {
                "matched": True,
                "label": label,
                "kind": kind,
                "item": item,
                "status": "entity_normalized",
                "match_type": "brain_list_collapsed_to_node_vocabulary_label",
                "notes": "brain-system entity list safely collapsed to one route-native vocabulary label",
            }
        return {
            "matched": False,
            "label": "",
            "kind": preferred_kind,
            "item": None,
            "status": "entity_unmapped",
            "match_type": "",
            "notes": f"brain-system entity `{raw_label}` did not safely split into known graph nodes",
        }

    matches = node_vocabulary_hits_in_text(raw_label, BRAIN_SYSTEM_ENTITY_KINDS, node_vocabulary)
    if len(matches) == 1:
        kind, label = matches[0]
        _, item = canonicalize_node_label(kind, label, node_vocabulary)
        return {
            "matched": True,
            "label": label,
            "kind": kind,
            "item": item,
            "status": "entity_normalized",
            "match_type": "text_contains_node_vocabulary_label",
            "notes": "brain-system entity text contained one route-native vocabulary label",
        }
    if len(matches) > 1:
        return {
            "matched": False,
            "label": "",
            "kind": preferred_kind,
            "item": None,
            "status": "entity_combo_not_graphable",
            "match_type": "",
            "notes": "brain-system entity text contains multiple graph entities; graph rows need one entity per edge",
        }
    return {
        "matched": False,
        "label": "",
        "kind": preferred_kind,
        "item": None,
        "status": "entity_unmapped",
        "match_type": "",
        "notes": f"brain-system entity `{raw_label}` did not match route-native node vocabulary",
    }


DIRECT_TARGET_REGISTRY_STATUSES = {
    "needs_external_id_lookup",
    "complex_target_needs_subunit_mapping",
}
TARGET_FAMILY_REGISTRY_STATUSES = {
    "broad_target_family",
    "composite_target_needs_split",
    "family_target_needs_subtype_mapping",
}
TARGET_FAMILY_LABEL_OVERRIDES = {
    "5-HT2A/2C receptor": "5-HT2 receptor family",
}
PATHWAY_REGISTRY_STATUS_TERMS = ("pathway", "process")
READOUT_REGISTRY_STATUS_TERMS = ("marker", "readout", "ligand", "neurotransmitter")
SYSTEM_REGISTRY_STATUS_TERMS = ("system",)
DIRECT_TARGET_EVIDENCE_RE = re.compile(
    r"\b("
    r"binding|affinity|potency|selectivity|target engagement|occupancy|radioligand|displacement|"
    r"ki|kd|ic50|ec50|ec90|emax|pki|agonis\w*|antagonis\w*|inhibit\w*|block\w*|"
    r"partial agonist|full agonist|inverse agonist|allosteric|reuptake|uptake inhibition|"
    r"transporter reversal|g[- ]?protein|gq|camp|calcium flux|beta[- ]?arrestin|"
    r"functional activation|functional activity|coupling efficiency|uptake|efflux|influx|vmax|"
    r"transporter function|receptor function|channel function|dat function|sert function|"
    r"desensitization"
    r")\b",
    re.IGNORECASE,
)
READOUT_EVIDENCE_RE = re.compile(
    r"\b("
    r"expression|levels?|concentration|content|density|availability|immunoreactivity|"
    r"protein|mrna|rna|transcript|western blot|immunoblot|qpcr|rt[- ]?pcr|elisa|"
    r"surface levels?|trafficking|glycosylation|maturation|ratio|phosphorylation|"
    r"metabolite|tissue levels?|plasma|serum|csf|pet|spect|autoradiography|"
    r"readout|proxy|polymorphism|genotype|variant|positive fibers?|currents?|epsc|ipsc|"
    r"mep?sc|mip?sc|postsynaptic|neurotransmission|responsiveness|increase in .*receptors?"
    r")\b",
    re.IGNORECASE,
)
PATHWAY_EVIDENCE_RE = re.compile(
    r"\b("
    r"pathway|signaling|cascade|neuroplasticity|synaptogenesis|inflammation|inflammasome|"
    r"microbiota|transduction|activation readout|mediated|mechanism|mechanistic"
    r")\b",
    re.IGNORECASE,
)
READOUT_MRNA_RE = re.compile(r"\b(mrna|rna|transcript|gene expression|qpcr|rt[- ]?pcr)\b", re.IGNORECASE)
READOUT_EXPRESSION_RE = re.compile(r"\b(expression|immunoreactivity|immunostaining|positive fibers?|positive cells?)\b", re.IGNORECASE)
READOUT_LEVEL_RE = re.compile(r"\b(levels?|concentration|content|abundance|plasma|serum|csf|tissue)\b", re.IGNORECASE)
READOUT_RELEASE_RE = re.compile(r"\b(release|efflux|overflow|exocytosis|neurotransmission|depletion)\b", re.IGNORECASE)
READOUT_UPTAKE_RE = re.compile(r"\b(uptake|reuptake|transport-associated|transporter function|transport function)\b", re.IGNORECASE)
READOUT_AVAILABILITY_RE = re.compile(
    r"\b(availability|binding potential|uptake site|densities|density|fiber density|receptor density|deficiency)\b",
    re.IGNORECASE,
)
READOUT_PHOSPHORYLATION_RE = re.compile(
    r"\b(phosphorylation|phosphorylated|phospho|p[- ]?(?:akt|erk|creb|trkb|gsk|mtor|s6k|stat|jnk|mapk|psd))\w*\b",
    re.IGNORECASE,
)
READOUT_ACTIVATION_RE = re.compile(r"\b(activation|activated|activity|functional coupling|coupling|agonis\w* response)\b", re.IGNORECASE)
READOUT_ELECTROPHYSIOLOGY_RE = re.compile(
    r"\b(current|currents|epsc|ipsc|mepsc|mipsc|spesc|responsiveness|firing rate|"
    r"postsynaptic current|synaptic current|paired[- ]pulse|ltp|long[- ]term potentiation)\b",
    re.IGNORECASE,
)
READOUT_TRAFFICKING_RE = re.compile(
    r"\b(surface|cell surface|trafficking|internalization|maturation|glycosylation|subcellular distribution)\b",
    re.IGNORECASE,
)
READOUT_GENETIC_RE = re.compile(r"\b(polymorphism|genotype|variant|rs\d+|methylation|cpg)\b", re.IGNORECASE)
PATHWAY_NODE_LABELS = {
    "akt",
    "erk",
    "gsk3b",
    "mtor",
    "mtorc1",
    "p70s6k",
    "stat3",
}
MOLECULAR_EFFECT_ENTITY_KINDS = {"pathway_process", "biomarker_readout"}
MOLECULAR_EFFECT_CONTEXT_FIELDS = (
    "molecular_effect_category",
    "specific_readout_or_marker",
    "mechanistic_relationship_type",
    "graph_entity_label",
    "graph_entity_original",
    "raw_entity_label",
    "canonical_entity",
    "pathway_or_readout",
    "pathway_or_process",
    "readout_or_biomarker",
    "readout_or_measure",
    "target",
    "mechanism_type",
    "action_type",
    "assay_type",
    "assay_family",
    "experimental_system_category",
    "outcome_measure",
    "finding_summary",
    "support",
    "effect_or_statistic",
)
MOLECULAR_EFFECT_LABEL_FIELDS = (
    "molecular_effect_category",
    "graph_entity_label",
    "graph_entity_original",
    "raw_entity_label",
    "canonical_entity",
    "pathway_or_readout",
    "pathway_or_process",
    "readout_or_biomarker",
    "readout_or_measure",
    "specific_readout_or_marker",
    "target",
)
MOLECULAR_EFFECT_RULES = (
    (
        "Gut microbiome",
        re.compile(
            r"\b(gut[- ]brain|gut|microbiome|microbiota|microbial|bacteri\w*|fecal|faecal|"
            r"short chain fatty acids?|scfa)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Neuroinflammation & immune signaling",
        re.compile(
            r"\b(neuroinflamm\w*|inflamm\w*|cytokine\w*|interleukin\w*|il[- ]?\d+|tnf|"
            r"nf[- ]?kappa[- ]?b|nf[- ]?kb|cox[- ]?2|prostaglandin\w*|microglia\w*|"
            r"astrocyt\w*|glial|gfap|iba[- ]?1|complement|crp|hmgb1|tlr[- ]?4|"
            r"il[- ]?\d+\w*|tgf[- ]?beta)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Cell injury & survival",
        re.compile(
            r"\b(cell injury|cell survival|cell viability|cell death|neuronal (?:injury|damage|loss|survival)|"
            r"neuroprotection|neuroaxonal injury|apoptosis|caspase|necrosis|cytotox\w*|neurotox\w*|"
            r"toxicity|toxic marker|neurofilament|\bnfl\b|s100b)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Cellular stress & mitochondrial function",
        re.compile(
            r"\b(cellular stress|oxidative stress|reactive oxygen|\bros\b|lipid peroxidation|malondialdehyde|"
            r"glutathione|\bgsh\b|\bsod\b|catalase|redox|hsp[- ]?70|heat shock|"
            r"mitochondri\w*|mitophagy|protein folding|endoplasmic reticulum|er stress|dna damage)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Neurogenesis",
        re.compile(r"\b(neurogenesis|doublecortin|\bdcx\b|newborn neurons?|granule cell proliferation)\b", re.IGNORECASE),
    ),
    (
        "Neuroplasticity",
        re.compile(
            r"\b(neuroplasticity|bdnf|trkb|trk b|ngf|gdnf|vegf|igf[- ]?1|insulin[- ]like growth factor|"
            r"neurotroph\w*|growth factor\w*|plasticity|"
            r"synaptic (?:plasticity|protein|density|remodeling)|synapse (?:formation|density)|dendritic|spine|neurite|synaptogenesis|"
            r"paired[- ]pulse facilitation|\bppf\b|long[- ]?term potentiation|\bltp\b|long[- ]?term depression|\bltd\b|psd[- ]?95|"
            r"synaptophysin|\barc\b|sv2a|synaptic vesicle|perineuronal net|"
            r"gap[- ]?43|growth associated protein|myelin basic protein|myelination)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Intracellular signal transduction",
        re.compile(
            r"\b(intracellular signaling|erk|mapk|mtor|mtorc1|akt|camp|creb|pka|pkc|plc|pi3k|gsk[- ]?3|p70s6k|"
            r"stat3|jnk|rac1|phosphorylation|phosphorylated|phospho|second messenger\w*|"
            r"kinase\w*|phosphoinositide)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Genetic moderators",
        re.compile(r"\b(polymorphism\w*|genotype\w*|phenotype interaction|allele\w*|rs\d+)\b", re.IGNORECASE),
    ),
    (
        "Epigenetic regulation",
        re.compile(r"\b(epigen\w*|dna methylation|methylation|histone\w*|chromatin|cpg)\b", re.IGNORECASE),
    ),
    (
        "Gene expression & activity markers",
        re.compile(
            r"\b(c[- ]?fos|fosb|egr[- ]?1|immediate early|neuronal activation|neural activation|"
            r"neural activity|neuronal activity|gene expression|transcript\w*|transcriptom\w*|mrna|rna|mirna|microrna)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Receptor regulation & trafficking",
        re.compile(
            r"\b(receptor\w*|5[- ]?ht\d?[a-z]?|sert|slc6a4|\bdat\b|slc6a3|slc6a2|"
            r"d[1-5][ -]?receptor|ampa|nmda|nmdar|ampar|mglur\d?[a-z]?|mglu\d?|glua\d?[a-z]?|glun\d?[a-z]?|"
            r"gabr|transport(?:er|ers)|availability|binding potential|densit(?:y|ies)|occupancy|trafficking|"
            r"surface expression|internalization|uptake site|p[- ]?glycoprotein|abcb1|pmat|slc29a4|vmat\d?)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Drug metabolism",
        re.compile(r"\b(drug metabolism|cyp\d+\w*|cytochrome p450|ugt\d*\w*|monoamine oxidase|mao[- ]?[ab]?|comt|metabolic enzyme\w*|in vitro metabolism)\b", re.IGNORECASE),
    ),
    (
        "Endocrine response",
        re.compile(r"\b(endocrine response|cortisol|corticosterone|acth|prolactin|hormone\w*|endocrine|melatonin|oxytocin|vasopressin)\b", re.IGNORECASE),
    ),
    (
        "Neuronal excitability & synaptic transmission",
        re.compile(
            r"\b(neuronal excitability|excitability|firing rate|spik(?:e|ing)|calcium imaging|calcium flux|electrophysiolog\w*|"
            r"oscillation\w*|gamma|theta|field potential\w*|currents?|\bepscs?\b|\bipscs?\b|"
            r"\bmepscs?\b|\bmipscs?\b|action potential|membrane potential|ion channel modulation|"
            r"synaptic transmission|neurotransmission)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Neurotransmitter release, uptake & turnover",
        re.compile(
            r"\b(serotonin signaling|serotonin|5[- ]?hydroxytryptamine|5[- ]?hiaa|dopamine signaling|dopamine|"
            r"\bdopa\b|dopac|\bhva\b|glutamate signaling|glutamate|glutamatergic|gaba signaling|gaba|gabaergic|"
            r"norepinephrine signaling|norepinephrine|noradrenaline|acetylcholine|"
            r"monoamine releas\w*|monoamine neurotransmission|modulat\w* monoamine|"
            r"neurotransmitter\w*|transmitter releas\w*|releas\w*|uptake|reuptake|turnover|metabolite levels?|"
            r"vesicular monoamine transporter|tph[- ]?2|tryptophan hydroxylase|dopaminergic system marker|"
            r"choline acetyltransferase|\bchat\b|cholinergic system marker)\b",
            re.IGNORECASE,
        ),
    ),
)
MOLECULAR_EFFECT_RULE_LABELS = tuple(label for label, _pattern in MOLECULAR_EFFECT_RULES)
MOLECULAR_EFFECT_CATEGORY_ALIASES = {
    "inflammation": "Neuroinflammation & immune signaling",
    "cellular stress": "Cellular stress & mitochondrial function",
    "oxidative stress": "Cellular stress & mitochondrial function",
    "neurotoxicity": "Cell injury & survival",
    "neuroaxonal injury": "Cell injury & survival",
    "neuroprotection": "Cell injury & survival",
    "intracellular signaling": "Intracellular signal transduction",
    "immediate early gene activation": "Gene expression & activity markers",
    "gene expression": "Gene expression & activity markers",
    "serotonin signaling": "Neurotransmitter release, uptake & turnover",
    "dopamine signaling": "Neurotransmitter release, uptake & turnover",
    "glutamate signaling": "Neurotransmitter release, uptake & turnover",
    "gaba signaling": "Neurotransmitter release, uptake & turnover",
    "norepinephrine signaling": "Neurotransmitter release, uptake & turnover",
    "electrophysiology": "Neuronal excitability & synaptic transmission",
    "receptor regulation": "Receptor regulation & trafficking",
    "gut-brain axis": "Gut microbiome",
    "mitophagy": "Cellular stress & mitochondrial function",
    "mitochondrial biogenesis": "Cellular stress & mitochondrial function",
    "protein folding and trafficking": "Cellular stress & mitochondrial function",
    "ion channel modulation": "Neuronal excitability & synaptic transmission",
    "ion channel trafficking": "Receptor regulation & trafficking",
    "astrocyte function": "Neuroinflammation & immune signaling",
    "cell-cell communication": "Intracellular signal transduction",
}
MOLECULAR_EFFECT_RULE_LABEL_BY_KEY = {
    **{label_key(label): label for label in MOLECULAR_EFFECT_RULE_LABELS},
    **{label_key(alias): label for alias, label in MOLECULAR_EFFECT_CATEGORY_ALIASES.items()},
}
GENERIC_MOLECULAR_EFFECT_PLACEHOLDER_KEYS = {
    "neurotransmitter signaling",
    "monoaminergic system",
    "serotonergic system",
    "dopaminergic system",
    "cholinergic system",
    "metabolism",
    "cellular metabolism",
    "energy metabolism",
    "other molecular effects",
}

# Researcher-facing second-level topics. These sit between the broad molecular
# process shown in the graph and the exact measurement retained in finding cards.
MOLECULAR_SUBTOPIC_RULES_BY_PARENT: dict[str, tuple[tuple[str, re.Pattern[str]], ...]] = {
    "Neuroplasticity": (
        ("BDNF–TrkB signaling", re.compile(r"\b(?:m|pro)?bdnf\b|\btrkb\b|\bntrk2\b|\bptrkb\b", re.I)),
        ("Dendritic & spine remodeling", re.compile(r"dendrit|spine|spinogenesis|dendritogenesis|neurite|arbori[sz]|growth cone|cytoskeletal|f-actin|pruning|mossy fiber sprouting", re.I)),
        ("Synaptic potentiation & depression", re.compile(r"long[- ]?term potentiation|\bltp\b|long[- ]?term depression|\bltd\b|short[- ]?term potentiation|\bstp\b|paired[- ]?pulse|\bppf\b|synaptic potentiation|synaptic depression|fepsp|synaptic efficacy|postsynaptic efficacy|synaptic scaling|ocular dominance|reconsolidation", re.I)),
        ("Synaptic proteins & vesicle remodeling", re.compile(r"psd[- ]?95|dlg4|sv2a|synaptophysin|synapsin|synaptotagmin|synaptophluorin|\bsyt\d|\bsyn1\b|synaptic (?:protein|marker|vesicle|density|remodel|ultrastructure|defect|activity)|synapse (?:formation|density|number)|synaptogenesis|synaptogenic|vesicle recycling|drebrin|homer1|shank3|rims1|narp|neuronal pentraxin|presynaptic|readily releasable pool|synaptozip", re.I)),
        ("Glutamatergic receptor plasticity", re.compile(r"ampa|nmda|glua|glur|gria|glun|nmdar|ampar|glutamate receptor", re.I)),
        ("Activity-dependent plasticity genes", re.compile(r"\barc\b|c[- ]?fos|fosb|egr\d?|zif268|immediate early|cebp|npas4|fra1|neurod1", re.I)),
        ("Neurotrophic growth factors", re.compile(r"\bngf\b|\bgdnf\b|\bvegf\w*\b|vascular endothelial growth factor|\bigf[- ]?1\b|insulin[- ]like growth factor|neurotrophin|\bnt[- ]?[34]\b|\bntf3\b|\btrkc?\b|fgf[- ]?2|neurotrophic factor|\bp75\b", re.I)),
        ("Plasticity-related intracellular signaling", re.compile(r"\bmtor|\berk\b|\bcreb\b|\bakt\b|gsk[- ]?3|p70s6k|rps6|mapk|rac1|camkii|pi3k|kinase|phosphoinositide|intracellular signaling", re.I)),
        ("Myelination & extracellular plasticity", re.compile(r"myelin|\bmbp\b|perineuronal|extracellular matrix|chondroitin|mmp[- ]?9|nogo", re.I)),
        ("Neurogenesis & cell proliferation", re.compile(r"cell(?:ular)? proliferation|progenitor proliferation|cell growth|neural progenitor|neural stem|new neurons?|neuronal maturation|\bbrdu\b|\bpcna\b|ki[- ]?67", re.I)),
        ("Structural imaging markers", re.compile(r"cortical thickness|\bvolume\b|dti|diffusivity|white matter|gr[ae]y matter|neuronal volume|neuronal density", re.I)),
        ("Functional synaptic transmission", re.compile(r"epsc|ipsc|fipsp|\blfp\b|field potential|membrane potential|excitability|electrophysiolog|synaptic transmission|synaptic current|synaptic strength|action potential|calcium event|calcium response|calcium transient|gamma oscillation", re.I)),
        ("General neuroplasticity measures", re.compile(r"neuroplastic|synaptic plasticity|plasticity marker|functional cellular plasticity|structural plasticity|protein synthesis|gap[- ]?43|\bmap2\b|axon development", re.I)),
        ("Interneuron & circuit remodeling", re.compile(r"parvalbumin|\bpv\b|interneuron|fiber density|fiber connectivity|laminar connectivity|engram|projection density|synaptic input", re.I)),
        ("Circuit connectivity & plasticity", re.compile(r"functional connectivity|\bdfc\b|coherence|pathway plasticity|circuit connectivity|connection strength", re.I)),
    ),
    "Receptor regulation & trafficking": (
        ("Serotonin receptors", re.compile(r"5[- ]?ht\s*[1-7]|serotonin.*receptor|htr\d|serotonin autoreceptor|\bs2 receptor|(?:serotonin|5[- ]?ht).*(?:agonis|antagonis|binding|response|action|sensitivity)|(?:agonis|antagonis|binding|response|action|sensitivity).*(?:serotonin|5[- ]?ht)", re.I)),
        ("Monoamine transporters", re.compile(r"\bsert\b|slc6a4|\bdat\b|slc6a3|\bnet\b|slc6a2|vmat|slc18a|paroxetine binding|imipramine binding", re.I)),
        ("Glutamate receptors", re.compile(r"ampa|nmda|nma receptor|mglur|mglu\d|glua|glur|gria|glun|grin|glutamate receptor|kainate receptor", re.I)),
        ("Dopamine receptors", re.compile(r"dopamine [dD]?[1-5] receptor|\bd[1-5][ -]?receptor|\bdrd[1-5]\b", re.I)),
        ("GABA receptors", re.compile(r"gaba[a-b]? receptor|gabr|gabaa|gabab", re.I)),
        ("Adrenergic receptors", re.compile(r"adrenergic receptor|adrenoceptor|adra\d|adrb\d", re.I)),
        ("Opioid receptors", re.compile(r"opioid receptor|\bmu\b.*receptor|\bkappa\b.*receptor|\bdelta\b.*receptor|oprm|oprk|oprd", re.I)),
        ("Cannabinoid receptors", re.compile(r"cannabinoid receptor|\bcb[12]\b|cnr[12]", re.I)),
        ("Cholinergic receptors", re.compile(r"muscarinic|nicotinic|acetylcholine receptor|nachr|mchr", re.I)),
        ("Sigma receptors", re.compile(r"sigma[- ]?[12]? receptor|sigmar", re.I)),
        ("Purinergic & ion-channel receptors", re.compile(r"p2x\d|p2y\d|trpv\d|purinergic|ionotropic channel", re.I)),
        ("Receptor trafficking & internalization", re.compile(r"trafficking|internalization|endocytosis|vesicle mobility|surface (?:expression|density)|membrane localization|membrane redistribution|receptor recycling|desensiti[sz]", re.I)),
        ("Neuropeptide & hormone receptors", re.compile(r"oxytocin receptor|vasopressin receptor|glucocorticoid receptor|mineralocorticoid receptor|neuropeptide receptor|trk receptor", re.I)),
        ("Receptor binding & availability", re.compile(r"receptor binding|binding potential|binding kinetics|receptor availability|receptor occupancy", re.I)),
        ("Glutamate transporters", re.compile(r"eaat\d|glt[- ]?1|slc1a\d|glutamate transporter", re.I)),
        ("Drug-efflux transporters", re.compile(r"p[- ]?glycoprotein|abcb1|bcrp|abc transport", re.I)),
        ("Non-monoamine membrane transporters", re.compile(r"\bmct[1-4]\b|monocarboxylate transporter|\baqp\d\b|aquaporin|\bcd36\b|fatty acid translocase|\bnhe\d\b", re.I)),
        ("Additional GPCR & growth-factor receptors", re.compile(r"\bgpr\d+\b|\bffar\d\b|\bchrm\d\b|\bngfr\b|p75ntr|p75 neurotrophin|tgf[- ]?beta.*receptor|receptor tyrosine kinase", re.I)),
        ("Other", re.compile(r"receptor|transporter|availability|occupancy|slc\d|s1r", re.I)),
    ),
    "Intracellular signal transduction": (
        ("PI3K–Akt–mTOR signaling", re.compile(r"pi3k|\bakt\b|\bmtor|mtorc|p70s6k|\bs6k\b|\brps6\b|eif4e|eef2", re.I)),
        ("ERK–MAPK signaling", re.compile(r"\berk\b|erk1|erk2|mapk|mek1|mek2|mkp[- ]?1|raf", re.I)),
        ("cAMP–PKA–CREB signaling", re.compile(r"\bcamp\b|adenylyl cyclase|\bpka\b|\bcreb\b|camp response", re.I)),
        ("PLC–PKC–calcium signaling", re.compile(r"\bplc\b|\bpkc\b|calcium|ca2\+|gq-mediated|inositol|ip3|dag|camk|calcineurin", re.I)),
        ("GSK3 signaling", re.compile(r"gsk[- ]?3", re.I)),
        ("β-arrestin signaling", re.compile(r"arrestin", re.I)),
        ("JNK & stress-kinase signaling", re.compile(r"\bjnk\b|p38 mapk|stress kinase", re.I)),
        ("JAK–STAT signaling", re.compile(r"\bjak\d*|\bstat\d*|pstat", re.I)),
        ("Rho-family GTPase signaling", re.compile(r"\brac1\b|\brhoa\b|\bcdc42\b|\btiam1\b|rho[- ]family", re.I)),
        ("Nitric oxide–cGMP signaling", re.compile(r"nitric oxide|\bnos\b|cnos|nnos|\bcgmp\b|guanylate cyclase|pde\d", re.I)),
        ("AMPK & metabolic signaling", re.compile(r"\bampk\b|pampk|pgc[- ]?1|sirt1|metabolic signaling", re.I)),
        ("G-protein signaling", re.compile(r"g[- ]?protein|\bgq\b|\bgi\b|\bgs\b|gα|galpha|\bgaq\b|\bgao\b|\bgz\b|guanine nucleotide|heterotrimer", re.I)),
        ("Protein phosphorylation & kinase activity", re.compile(r"phosphorylation|phospho|kinase activity|protein kinase", re.I)),
        ("STING–TBK signaling", re.compile(r"\bsting\b|\btbk\d*\b", re.I)),
        ("Other", re.compile(r"intracellular signaling|signal transduction|second messenger|pathway activation", re.I)),
    ),
    "Gene expression & activity markers": (
        ("Immediate-early genes", re.compile(r"c[- ]?fos|fosb|\barc\b|egr[- ]?\d|zif268|homer1|npas4|immediate early", re.I)),
        ("Transcriptome-wide expression", re.compile(r"transcriptom|rna[- ]?seq|gene expression profile|transcriptional profile|differentially expressed|gene-set|pathway enrichment", re.I)),
        ("MicroRNA & non-coding RNA", re.compile(r"mirna|\bmir[- ]?\d|micro[- ]?rna|non[- ]?coding rna|lncrna|malat1|xist", re.I)),
        ("Neuroplasticity-related genes", re.compile(r"bdnf|ntrk2|gdnf|ngf|vegf|igf|homer|shank|synaps|psd[- ]?95|dlg4|neurod|gap[- ]?43", re.I)),
        ("Immune & inflammatory genes", re.compile(r"il[- ]?\d|tnf|nf[- ]?kb|cox[- ]?2|ptgs2|inos|nos2|gfap|iba[- ]?1|tlr|cytokine", re.I)),
        ("Cell-stress & survival genes", re.compile(r"bax|bcl[- ]?2|caspase|hsp|sod|catalase|nrf2|keap1|autophag|lc3|beclin", re.I)),
        ("Circadian & endocrine genes", re.compile(r"clock|bmal|per[123]|cry[12]|nr3c1|crhr|hpa|circadian", re.I)),
        ("Synaptic & interneuron genes", re.compile(r"gabra|gad1|gad67|parvalbumin|\bpv\b|reelin|nrgn|cbln|neuregulin|nrg1|lingo|myelin|cnpase|\bcnp\b", re.I)),
        ("Neuropeptide & transmitter genes", re.compile(r"preprotachykinin|tachykinin|enkephalin|dynorphin|neurotensin|neuromedin|\bpomc\b|cartpt|cholecystokinin|\bcck\b|prodynorphin|\bpdyn\b|\bpenk\b|\bvip\b|histaminergic|\bhdc\b|tyrosine hydroxylase|\bth\b.*mrna|\btph2\b|serine racemase|daao", re.I)),
        ("Ion-channel & excitability genes", re.compile(r"kcnq|hcn\d|calcium channel|trpv\d|p2x\d|ion channel|gabaa|gabab", re.I)),
        ("Extracellular-matrix & barrier genes", re.compile(r"collagen|extracellular matrix|chondroitin|tight junction|occludin|zo[- ]?1|fibrosis|adhesion molecule|integrin", re.I)),
        ("Transcription-factor regulation", re.compile(r"transcription factor|transcriptional entropy|\bsp4\b|\bror|nfat|klf\d|c/ebp|icer|gene transcription", re.I)),
        ("Developmental & differentiation genes", re.compile(r"wnt|beta[- ]?catenin|notch|shh|stemness|pax\d|foxo|phox2b|lmx1b|cell differentiation", re.I)),
        ("Metabolism-related genes", re.compile(r"glycol|glucose|lipid|fatty acid|tryptophan|kynuren|urea cycle|heme biosynthesis|ucp\d|pgc[- ]?1|ppar|metabolic gene", re.I)),
        ("Protein synthesis & processing", re.compile(r"protein synthesis|translation|translatome|ribosome|rna processing|protein maturation|er export", re.I)),
        ("Neural activity markers", re.compile(r"neuronal activity|neural activity|activity marker|activation marker", re.I)),
        ("Targeted gene-expression markers", re.compile(r"mrna|gene expression|protein expression|transcript|rna expression", re.I)),
    ),
    "Neuroinflammation & immune signaling": (
        ("IL-6 & related cytokines", re.compile(r"il[- ]?6|interleukin[- ]?6", re.I)),
        ("TNF signaling", re.compile(r"tnf", re.I)),
        ("IL-1 signaling", re.compile(r"il[- ]?1|interleukin[- ]?1", re.I)),
        ("Anti-inflammatory cytokines", re.compile(r"il[- ]?10|tgf[- ]?beta|anti[- ]inflammatory cytokine", re.I)),
        ("Cytokines & chemokines", re.compile(r"interleukin|il[- ]?\d|cytokine|chemokine|ccl\d|cxcl\d", re.I)),
        ("Microglial activation", re.compile(r"microglia|iba[- ]?1|cd68", re.I)),
        ("Astrocyte & glial activation", re.compile(r"astrocy|\bgfap\b|glial activation", re.I)),
        ("NF-κB & TLR signaling", re.compile(r"nf[- ]?(?:kappa[- ]?b|kb)|tlr[- ]?\d|hmgb1|inflammasome|nlrp3", re.I)),
        ("COX & prostaglandin signaling", re.compile(r"cox[- ]?[12]|ptgs|prostaglandin", re.I)),
        ("CRP & systemic inflammation", re.compile(r"c[- ]?reactive protein|\bcrp\b|systemic inflammation", re.I)),
        ("Nitric oxide & iNOS signaling", re.compile(r"inducible nitric oxide|\binos\b|nitric oxide|nitrite|nitrosative", re.I)),
        ("Innate immune-cell function", re.compile(r"macrophage|neutrophil|myeloperoxidase|\bmpo\b|phagocyt|procalcitonin|acyloxyacyl hydrolase|\baoah\b", re.I)),
        ("Adaptive immune cells & immunoglobulins", re.compile(r"\b(?:cd3|cd4|cd8)\+?\b|t[- ]?cell|b[- ]?cell|natural killer|nk[- ]?cell|immunoglobulin|\big[agem]\b|antibody[- ]forming", re.I)),
        ("Mast-cell, eosinophil & allergic signaling", re.compile(r"mast cell|tryptase|eosinophil|allerg|\bige\b", re.I)),
        ("Eicosanoid & lipoxygenase signaling", re.compile(r"pge\d|prostaglandin|lipoxygenase|5[- ]?lox|leukotriene", re.I)),
        ("Glial inflammatory spectroscopy markers", re.compile(r"myo[- ]?inositol|myoinositol|\bmi/cr\b", re.I)),
        ("Kynurenine immune metabolism", re.compile(r"kynuren|kyn/trp", re.I)),
        ("General neuroinflammation", re.compile(r"neuroinflamm|inflammat|immune activation|immune signaling", re.I)),
    ),
    "Neurotransmitter release, uptake & turnover": (
        ("Serotonin release & turnover", re.compile(r"serotonin|5[- ]?hydroxytryptamine|5[- ]?ht\b|5[- ]?hiaa", re.I)),
        ("Dopamine release & turnover", re.compile(r"dopamine|\bdopa\b|dopac|homovanillic|\bhva\b", re.I)),
        ("Glutamate release & levels", re.compile(r"glutamate|glutamatergic|\bglx\b", re.I)),
        ("GABA release & levels", re.compile(r"\bgaba\b|gabaergic", re.I)),
        ("Norepinephrine release & turnover", re.compile(r"norepinephrine|noradrenaline|normetanephrine|\bmhp[g]?\b", re.I)),
        ("Acetylcholine release & turnover", re.compile(r"acetylcholine|choline|cholinergic", re.I)),
        ("Histamine release & turnover", re.compile(r"histamine|histaminergic", re.I)),
        ("Epinephrine release & levels", re.compile(r"epinephrine|adrenaline", re.I)),
        ("Neuropeptide release", re.compile(r"isotocin|neuropeptide release|peptide release", re.I)),
        ("Purinergic & ATP release", re.compile(r"atp release|purinergic release", re.I)),
        ("General monoamine dynamics", re.compile(r"monoamine|catecholamine.*(?:release|uptake|turnover|levels?)|(?:release|uptake|turnover|levels?).*catecholamine", re.I)),
        ("Other", re.compile(r"neurotransmitter|metabolite|turnover|release|uptake", re.I)),
    ),
    "Neuronal excitability & synaptic transmission": (
        ("Excitatory postsynaptic currents", re.compile(r"epsc|excitatory post|glutamatergic synaptic|excitatory synaptic", re.I)),
        ("Inhibitory postsynaptic currents", re.compile(r"ipsc|inhibitory post|gabaergic synaptic|inhibitory synaptic", re.I)),
        ("Action potentials & neuronal firing", re.compile(r"action potential|firing rate|spik|burst firing|neuronal firing|cellular activity", re.I)),
        ("Calcium activity", re.compile(r"calcium|ca2\+|calcium imaging|calcium flux|calcium transient", re.I)),
        ("Field potentials & synaptic strength", re.compile(r"field potential|fepsp|population spike|synaptic strength|synaptic response|evoked potential", re.I)),
        ("Neural oscillations", re.compile(r"oscillation|gamma|theta|delta|alpha power|beta power|aperiodic|cross[- ]frequency|sample entropy", re.I)),
        ("Membrane potential & ion channels", re.compile(r"membrane potential|membrane current|ion channel|conductance|depolarization|hyperpolarization|afterhyperpolarization", re.I)),
        ("Excitation–inhibition balance", re.compile(r"excitation.?inhibition|e/?i balance|excitatory/inhibitory|e-i balance", re.I)),
        ("Resting-state & spontaneous neural activity", re.compile(r"\bfalff\b|fractional amplitude|spontaneous (?:brain|neural|neuronal) activity|resting[- ]state activity|neural variability|rhythmic slow activity", re.I)),
        ("Excitatory–inhibitory synaptic markers", re.compile(r"\bvglut\d*\b|\bvgat\b|parvalbumin|\bpv\+?\b|synaptic puncta|synaptic junction", re.I)),
        ("Reflexes & motor-circuit excitability", re.compile(r"ventral root potential|dorsal root potential|monosynaptic reflex|motor response|motor transmission|convulsion|seizure|raphe unit activity|unit activity", re.I)),
        ("Peripheral neuroeffector transmission", re.compile(r"uterine contraction|detrusor contraction|smooth muscle|organ bath|nerve stimulation|pharyngeal pumping|intracavernosal pressure|neuromuscular|neuroeffector|adrenergic nerve|cholinergic contraction", re.I)),
        ("Membrane pumps & transmitter enzymes", re.compile(r"na\+?,?k\+?[- ]?atpase|sodium[- ]potassium atpase|acetylcholinesterase|cholinesterase|transmitter reuptake", re.I)),
        ("Retinal & evoked electrophysiology", re.compile(r"electroretinogram|\berg\b|retinal activity|evoked response|evoked activity", re.I)),
        ("Gap-junction & electrical coupling", re.compile(r"gap junction|electrical coupling|connexin", re.I)),
        ("General synaptic transmission", re.compile(r"synaptic transmission|neurotransmission|neuronal excitability|electrophysiolog", re.I)),
    ),
    "Cellular stress & mitochondrial function": (
        ("Oxidative damage & lipid peroxidation", re.compile(r"oxidative|reactive oxygen|\bros\b|lipid peroxidation|malondialdehyde|\bmda\b|tbars|nitrotyrosine|8[- ]?ohdg|free radical|nitrite|superoxide|hydrogen peroxide|protein carbonyl|thiol|nadph oxidase|\bnox\d|xanthine oxidase", re.I)),
        ("Antioxidant defenses", re.compile(r"glutathione|\bgsh\b|superoxide dismutase|\bsod\d*\b|\bcat\b|catalase|antioxidant|nrf2|keap1|frap", re.I)),
        ("Mitochondrial bioenergetics", re.compile(r"mitochond|atp|respiration|electron transport|membrane potential|cytochrome c|bioenergetic|\bndii\b|\bcoxi\b|oxphos|nad\+|nadp|phosphocreatine", re.I)),
        ("ER stress & protein folding", re.compile(r"endoplasmic reticulum|er stress|chop|grp78|grp94|\bbip\b|hsp|heat shock|chaperone|protein folding|proteostasis|er exodosis|eif2|ddit3|ern1|creb3l1|ubiquitin|proteasome", re.I)),
        ("Autophagy & mitophagy", re.compile(r"autophag|mitophag|\blc3\b|beclin|p62|sqstm1", re.I)),
        ("DNA damage", re.compile(r"dna damage|dna oxidation|comet assay|tail moment", re.I)),
        ("Cellular energy metabolism", re.compile(r"glucose metabolism|glycolysis|tca cycle|citrate cycle|metabolic rate|lactate|energy metabolism", re.I)),
        ("General cellular stress", re.compile(r"cellular stress|stress response|redox|protein damage", re.I)),
    ),
    "Drug metabolism": (
        ("CYP-mediated metabolism", re.compile(r"cyp\d|cytochrome p[- ]?450|\bp[- ]?450\b|o[- ]?dealkylation", re.I)),
        ("MAO & COMT metabolism", re.compile(r"monoamine oxidase|mao[- ]?[ab]?|\bcomt\b", re.I)),
        ("Glucuronidation & conjugation", re.compile(r"glucuron|\bugt\d|sulfation|conjugat|glutathione s[- ]transferase|\bgst\b", re.I)),
        ("Hydrolysis & dephosphorylation", re.compile(r"hydrolys|dephosphoryl|phosphatase|esterase", re.I)),
        ("Hydrolase & dehydrogenase metabolism", re.compile(r"fatty acid amide hydrolase|\bfaah\b|mag lipase|monoacylglycerol lipase|aldehyde dehydrogenase|\baldh\d*\b", re.I)),
        ("Demethylation & oxidation", re.compile(r"demethyl|hydroxylat|oxidation|deaminat", re.I)),
        ("Metabolite formation", re.compile(r"metabolite|biotransformation|metabolic conversion|enzymatic conversion|metabolism to|bufotenine formation|metabolic product", re.I)),
        ("Drug biosynthesis & production", re.compile(r"biosynth|heterologous .* production|drug production|alkaloid production|product titer|metabolic engineering|gene cluster|methyltransferase|\bsynthase\b|enzymatic synthesis|conversion of .* to", re.I)),
        ("Compound content & natural occurrence", re.compile(r"(?:psilocybin|psilocin|baeocystin|norbaeocystin|aeruginascin|dmt|dimethyltryptamine|ergot alkaloid|tryptamine|salvinorin|lysergic acid).*(?:content|concentration|level|composition|chemotype|detected|enrichment)|(?:content|concentration|level|composition|chemotype|detected|enrichment).*(?:psilocybin|psilocin|baeocystin|norbaeocystin|aeruginascin|dmt|dimethyltryptamine|ergot alkaloid|tryptamine|salvinorin|lysergic acid)", re.I)),
        ("Elimination, excretion & disposition", re.compile(r"elimination half[- ]?life|urinary excretion|renal excretion|clearance|excretion|drug disposition", re.I)),
        ("Tracer uptake & distribution", re.compile(r"\b(?:c|carbon)[- ]?1?[34]\b|\[1?[34]c\]|radiolabel|rate of appearance|brain uptake|tissue distribution|isotopic enrichment", re.I)),
        ("Metabolic-enzyme activity", re.compile(r"enzyme activity|catalytic activity|n[- ]?methyltransferase|methyltransferase activity|decarboxylase|reductase activity", re.I)),
        ("Reactive metabolic intermediates", re.compile(r"radical anion|reactive intermediate|electrochemical reduction|redox metabol", re.I)),
        ("Drug transport & barrier permeability", re.compile(r"blood[- ]brain barrier|\bbbb\b|permeability|bcrp|p[- ]?glycoprotein|abcb1|drug transport|accumulation", re.I)),
        ("Tryptophan–kynurenine metabolism", re.compile(r"kynuren|tryptophan|quinolinic acid|indoleamine[- ]?2,3|\bido\b", re.I)),
        ("Drug exposure & tissue concentrations", re.compile(r"pharmacokinetic|\bauc\b|(?:plasma|serum|brain|tissue|csf|striatal|extracellular) .*?(?:concentration|levels?|content)|drug content|protein binding|subcellular binding|metabolite ratio|norketamine:ketamine ratio", re.I)),
        ("Metabolomics & endogenous metabolism", re.compile(r"metabolom|fatty acid metabolism|amino acid metabolism|leucine metabolism|endogenous metabolism|lactate|cholesterol|carbohydrate metabolism|tca cycle|pyrimidine metabolism|glycerophospholipid|homocysteine|cobalamin|sdha|metabolic markers", re.I)),
        ("General drug biotransformation", re.compile(r"hepatic (?:metabolism|metabolic)|peripheral metabolism|first[- ]pass metabolism|phase ii metabolism|oxidative (?:and non[- ]oxidative )?metabolism|metabolic stability|metabolic pathways|enzyme activity|metabolism of", re.I)),
        ("Other", re.compile(r"metabolism|metabolic pathway", re.I)),
    ),
    "Endocrine response": (
        ("HPA-axis hormones", re.compile(r"cortisol|corticosterone|\bacth\b|adrenocorticotropic|corticotropin|\bcrh\b|hpa axis|glucocorticoid", re.I)),
        ("Oxytocin & vasopressin", re.compile(r"oxytocin|vasopressin|copeptin|neurophysin", re.I)),
        ("Prolactin & growth hormone", re.compile(r"prolactin|growth hormone|\bgh\b", re.I)),
        ("Metabolic hormones", re.compile(r"leptin|insulin|irisin|adiponectin|ghrelin", re.I)),
        ("Catecholamine stress hormones", re.compile(r"epinephrine|adrenaline|alpha amylase|sam axis", re.I)),
        ("Gonadal hormones", re.compile(r"estradiol|estrogen|testosterone|progesterone", re.I)),
        ("Melatonin & circadian hormones", re.compile(r"melatonin|pineal|circadian hormone", re.I)),
        ("Renin–angiotensin–aldosterone & natriuretic peptides", re.compile(r"\brenin\b|aldosterone|angiotensin|natriuretic peptide|\banp\b", re.I)),
        ("Thyroid hormones", re.compile(r"triiodothyronine|thyroxine|thyroid|\bft?[34]\b", re.I)),
        ("Gonadotropins & reproductive steroids", re.compile(r"\blh\b|\bfsh\b|gonadotrop|ovulation|androsterone|dehydroepiandrosterone|\bdhea\b|pregnenolone|17[- ]?(?:keto|hydroxy)corticoid|gonadal function", re.I)),
        ("Glucose, lipid & thermogenic homeostasis", re.compile(r"blood (?:sugar|glucose)|serum glucose|plasma glucose|cholesterol|triglyceride|non[- ]?esterified fatty|\bnefa\b|thermogenesis|brown adipose", re.I)),
        ("Electrolyte & osmoregulatory response", re.compile(r"serum sodium|urine sodium|osmolality|osmolarity|electrolyte|fluid balance", re.I)),
        ("Neurosecretory response", re.compile(r"neurosecretory|melanophore", re.I)),
        ("Adrenal steroid output", re.compile(r"cortisone|adrenal (?:weight|steroid|secretion)", re.I)),
        ("General endocrine response", re.compile(r"hormone|endocrine|neuroendocrine", re.I)),
    ),
    "Cell injury & survival": (
        ("Apoptosis & caspase signaling", re.compile(r"apopt|caspase|\bcasp\d|\bbax\b|bcl[- ]?[2x]|smac|diablo|apoptosis[- ]inducing factor|\baif\b|cytochrome c release|tunel|annexin", re.I)),
        ("Cell viability & cytotoxicity", re.compile(r"cell viability|cytotox|mtt|ldh release|excitotoxic", re.I)),
        ("Neuroprotection", re.compile(r"neuroprotect|protection against|rescue from injury", re.I)),
        ("Axonal & neurofilament injury", re.compile(r"neurofilament|\bnfl\b|nf200|axonal injury|neuroaxonal", re.I)),
        ("Necrosis & cell death", re.compile(r"necros|cell death|neuronal death|dark neurons?", re.I)),
        ("Neuronal survival & loss", re.compile(r"neuronal survival|neuron survival|neuronal loss|neuron loss|neu[nN]\+", re.I)),
        ("Genotoxicity & chromosomal damage", re.compile(r"chromosom|genotox|dna fragment|dna integrity|dna binding|micronucle|8[- ]?(?:oxo|oh)dg|p53|\bparp\b", re.I)),
        ("Neural structural integrity & degeneration", re.compile(r"neuronal cell bod|nerve cell bod|healthy neuron|neuron(?:al)? count|neuronal degeneration|degenerated neuron|neural crest cell|purkinje cell|pyramidal cell|cortical cell|serotonergic (?:nerve|axon|fiber|terminal)|dopaminergic (?:nerve|axon|fiber|terminal|injury|neurotox)|demyelin|myelin sheath|nissl|outer nuclear layer|retinal (?:layer|thickness)|ventricular enlargement|atrophy|terminal damage|n[- ]?acetylaspartate|\bnaa(?:/cr)?\b|s100|tyrosine hydroxylase.*(?:loss|count|immuno)|th[- ]immunoreactive|parvalbumin.*(?:loss|count)|neuronal preservation", re.I)),
        ("Protein aggregation & cytoskeletal pathology", re.compile(r"amyloid|\bapp\b|bace1|tau|microtubule|cytoskeleton|ubiquitin.*inclusion|intracellular inclusion|endosom|lysosom|cathepsin|calpain|spectrin|parkin|pink1", re.I)),
        ("Barrier & tissue structural integrity", re.compile(r"tight junction|\bzo[- ]?1\b|occludin|e[- ]?cadherin|basement membrane|endothelial cell|blood[- ]brain barrier|\bbbb\b|urothel|uroplakin|\bupiii\b|\bmuc[- ]?2\b|villi|mucosal thickness|fibronectin|collagen|laminin|\bmmp[- ]?9\b|fibrosis|tissue integrity|structural integrity|membrane integrity|histopath|microcirculation|organ damage|infarction|edema", re.I)),
        ("Organ-injury biomarkers", re.compile(r"\b(?:alt|ast|alp|ggt|ck|bun)\b|creatine kinase|blood urea nitrogen|bilirubin|ammonia|liver (?:weight|enzyme|function)|hepatic injury|hepatitis|renal injury|kidney injury", re.I)),
        ("Autophagy & regulated cell injury", re.compile(r"\blc3\b|beclin|\bp62\b|sqstm1|autophag|\bmlkl\b|necropt|ferropt|gsdmd|pyropt", re.I)),
        ("Cell proliferation, senescence & repair", re.compile(r"brdu incorporation|cell proliferation|cellular proliferation|cell cycle|g2/m|cell doubling|cellular life extension|senesc|\bp21\b|tissue repair|regeneration", re.I)),
        ("Survival, lethality & general toxicity", re.compile(r"\bld50\b|lethality|survival rate|organismal survival|mortality|general toxicity|toxic dose", re.I)),
        ("General cell injury", re.compile(r"cell injury|neuronal injury|neural injury|neuronal damage|neural damage|neurotox|cell survival|tissue damage|cellular damage|degenerat|morphological abnormal|pyknotic|pyknosis", re.I)),
    ),
    "Epigenetic regulation": (
        ("DNA methylation", re.compile(r"dna methylation|dnam|cpg|dnmt", re.I)),
        ("Histone acetylation", re.compile(r"histone acetyl|h3k27ac|acetylated lysine", re.I)),
        ("Histone methylation", re.compile(r"histone methyl|h3k\d+me", re.I)),
        ("HDAC & sirtuin regulation", re.compile(r"\bhdac\d*|sirt\d|deacetylase", re.I)),
        ("Chromatin regulation", re.compile(r"chromatin|histone|hmgn|rest protein", re.I)),
        ("RNA methylation", re.compile(r"m6a|rna methyl|mettl", re.I)),
        ("Epigenetic aging & telomeres", re.compile(r"epigenetic aging|epigenetic age|omicmage|telomere", re.I)),
        ("General epigenetic regulation", re.compile(r"epigen|methylation", re.I)),
    ),
    "Genetic moderators": (
        ("Serotonin-system variants", re.compile(r"5[- ]?httlpr|slc6a4|sert genotype|htr\d|5[- ]?ht\d.*genotype|serotonin.*(?:variant|genotype)", re.I)),
        ("Dopamine & monoamine variants", re.compile(r"\bcomt\b|mao[- ]?a|drd\d|slc6a3|\bhdat\b|(?:dopamine|\bdat\b).*(?:variant|genotype|polymorphism)|taar1", re.I)),
        ("Norepinephrine-transporter variants", re.compile(r"slc6a2|norepinephrine transporter|\bnet\b.*(?:variant|genotype|polymorphism|rs\d+)", re.I)),
        ("Glutamate-receptor variants", re.compile(r"grin\d|gria\d|grm\d|glutamate receptor.*(?:variant|genotype|polymorphism)", re.I)),
        ("Nitric-oxide signaling variants", re.compile(r"\bnos[123]\b|nitric oxide synthase.*(?:variant|genotype|polymorphism)", re.I)),
        ("Drug-metabolism variants", re.compile(r"cyp\d|ugt\d|metabolizer|activity score|metabolism phenotype", re.I)),
        ("Neuroplasticity-related variants", re.compile(r"bdnf|ntrk2|robo2|sec11a|plasticity.*(?:variant|genotype)", re.I)),
        ("Stress & HPA-axis variants", re.compile(r"fkbp5|nr3c1|crhr1|stress.*(?:variant|genotype)", re.I)),
        ("Opioid-system variants", re.compile(r"opioid|oprm\d|oprk\d|oprd\d", re.I)),
        ("Oxytocin & vasopressin variants", re.compile(r"oxytocin|oxtr|vasopressin|avpr\d", re.I)),
        ("Genome-wide & polygenic markers", re.compile(r"genome[- ]?wide|\bgwas\b|polygenic|\bsnps?\b|genotyping information", re.I)),
        ("Biosynthetic & taxonomic variation", re.compile(r"gene cluster|biosynthetic pathway|mating[- ]?type|\bpr locus\b|\bhd\d?\b.*locus|ka/ks|selection pressure|rrna gene sequence|allopolyploid|allelic diversity|inbreeding|selfing", re.I)),
        ("Other", re.compile(r"genotype|polymorphism|allele|variant|rs\d+|gene interaction|phenotype interaction", re.I)),
    ),
    "Gut microbiome": (
        ("Microbiome composition & taxa", re.compile(r"composition|species abundance|genus|class level|taxa|lactobac|ruminococc|bacteroid|mucispir|sarcina|turicibacter", re.I)),
        ("Alpha diversity", re.compile(r"alpha[- ]?diversity|chao|shannon|simpson", re.I)),
        ("Beta diversity", re.compile(r"beta[- ]?diversity", re.I)),
        ("Microbial metabolites & SCFAs", re.compile(r"short chain fatty|\bscfa\b|butyr|acetate|propionate|microbial metabolite", re.I)),
        ("Oral microbiome", re.compile(r"oral microbi", re.I)),
        ("Gut barrier & permeability", re.compile(r"gut barrier|intestinal permeability|leaky gut", re.I)),
        ("General gut–brain microbiome", re.compile(r"gut microbi|microbiome|microbiota|microbial density|dysbiosis", re.I)),
    ),
    "Neurogenesis": (
        ("Neural progenitor proliferation", re.compile(r"proliferation|\bbrdu\b|\bpcna\b|ki[- ]?67|progenitor", re.I)),
        ("Neuronal differentiation & maturation", re.compile(r"differentiation|maturation|new neurons?", re.I)),
        ("Neuronal survival & integration", re.compile(r"surviv|integration", re.I)),
        ("DCX & neuroblast markers", re.compile(r"doublecortin|\bdcx\b|neuroblast", re.I)),
        ("General neurogenesis", re.compile(r"neurogenesis|neogenic", re.I)),
    ),
}


MOLECULAR_SUBTOPIC_RESIDUAL_LABELS = {"", "other", "other findings"}


def molecular_subtopic_context(row: dict, entity_label: str, *, extended: bool = False) -> str:
    values = [
        entity_label,
        row.get("specific_readout_or_marker", ""),
        row.get("pathway_or_readout", ""),
        row.get("pathway_or_process", ""),
        row.get("readout_or_biomarker", ""),
        row.get("mechanistic_relationship_type", ""),
    ]
    if extended:
        values.extend(
            [
                row.get("support", ""),
                row.get("finding_summary", ""),
                row.get("assay_type", ""),
                row.get("tissue_or_sample", ""),
                row.get("model_or_system", ""),
                row.get("system", ""),
                row.get("readout", ""),
                row.get("outcome_measure", ""),
            ]
        )
    return ascii_fold(
        " ".join(
            normalize(value)
            for value in values
            if normalize(value)
        )
    )


def molecular_subtopic_match(parent_label: str, context: str, *, allow_residual: bool) -> str:
    for subtopic, pattern in MOLECULAR_SUBTOPIC_RULES_BY_PARENT.get(normalize(parent_label), ()):
        subtopic_key = normalize(subtopic).casefold()
        fallback_label = subtopic_key in MOLECULAR_SUBTOPIC_RESIDUAL_LABELS or subtopic_key.startswith("general ")
        if pattern.search(context) and (
            allow_residual or not fallback_label
        ):
            return subtopic
    return ""


def molecular_finding_subtopic(row: dict, parent_label: str, entity_label: str) -> str:
    primary_context = molecular_subtopic_context(row, entity_label)
    specific = molecular_subtopic_match(parent_label, primary_context, allow_residual=False)
    if specific:
        return specific
    extended_context = molecular_subtopic_context(row, entity_label, extended=True)
    specific = molecular_subtopic_match(parent_label, extended_context, allow_residual=False)
    if specific:
        return specific
    return molecular_subtopic_match(parent_label, extended_context, allow_residual=True)


MOLECULAR_SPECIFIC_PARENT_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("Gut microbiome", re.compile(r"microbiome|microbiota|microbial|alpha[- ]?diversity|beta[- ]?diversity|short chain fatty|\bscfa\b", re.I)),
    ("Neuroinflammation & immune signaling", re.compile(r"neuroinflamm|cytokine|interleukin|il[- ]?\d|tnf|microglia|astrocy|\bgfap\b|iba[- ]?1|nf[- ]?(?:kappa[- ]?b|kb)|\bcrp\b|cox[- ]?2|\btspo\b", re.I)),
    ("Cell injury & survival", re.compile(r"apoptos|caspase|cell viability|cytotox|necros|neurofilament|axonal injury|neuronal (?:injury|loss|survival)|neuroprotect", re.I)),
    ("Cellular stress & mitochondrial function", re.compile(r"oxidative|reactive oxygen|lipid peroxidation|malondialdehyde|glutathione|superoxide dismutase|catalase|mitochond|autophag|er stress|dna damage|cerebral glucose|glucose (?:metabolism|utilization)|2[- ]?deoxyglucose|fdg uptake", re.I)),
    ("Neurogenesis", re.compile(r"neurogenesis|doublecortin|\bdcx\b|neuroblast", re.I)),
    ("Neuroplasticity", re.compile(r"bdnf|trkb|dendrit|spine|neurite|synaptogenesis|long[- ]?term potentiation|\bltp\b|long[- ]?term depression|\bltd\b|paired[- ]?pulse|perineuronal", re.I)),
    ("Neuronal excitability & synaptic transmission", re.compile(r"electrophysiolog|action potential|firing rate|spik|epsc|ipsc|field potential|membrane potential|oscillation|gamma power|theta power|conductance|synaptic transmission|e/?i ratio|event[- ]related potential", re.I)),
    ("Receptor regulation & trafficking", re.compile(r"(?:(?:receptor|5[- ]?ht[1-7]|htr\d|\bd[1-5]r\b|drd\d|\bsert\b|\bdat\b|\bnet\b|vmat|slc6a[234]|ampa|nmda|mglur|glua|glun|gabra|eaat|p2x\d|trpv\d).*(?:expression|density|availability|occupancy|trafficking|internalization|surface|binding potential|protein levels?|mrna)|(?:expression|density|availability|occupancy|trafficking|internalization|surface|protein levels?|mrna).*(?:receptor|5[- ]?ht[1-7]|htr\d|\bd[1-5]r\b|drd\d|\bsert\b|\bdat\b|\bnet\b|vmat|slc6a[234]|ampa|nmda|mglur|glua|glun|gabra|eaat|p2x\d|trpv\d))", re.I)),
    ("Neurotransmitter release, uptake & turnover", re.compile(r"^(?:serotonin|dopamine|glutamate|gaba|norepinephrine|noradrenaline|acetylcholine)$|(?:serotonin|dopamine|glutamate|\bgaba\b|norepinephrine|noradrenaline|acetylcholine|5[- ]?hiaa|dopac|\bhva\b).*(?:levels?|concentration|release|uptake|turnover|metabolite|clearance|tone|signaling)|(?:levels?|concentration|release|uptake|turnover|metabolite|clearance|tone).*(?:serotonin|dopamine|glutamate|\bgaba\b|norepinephrine|noradrenaline|acetylcholine|5[- ]?hiaa|dopac|\bhva\b)", re.I)),
    ("Intracellular signal transduction", re.compile(r"\berk\b|erk1|mapk|pi3k|\bakt\b|\bmtor|mtorc|\bcreb\b|gsk[- ]?3|p70s6k|\bcamp\b|cyclic amp|\bcgmp\b|\bpka\b|\bpkc\b|\bplc\b|arrestin|g[- ]?protein activation|calcium (?:mobili[sz]ation|release|flux)|inositol phosphate|phospholipase a2|\bpla2\b|arachidonic acid release|jak[- /]?stat|camk|calcineurin|rac1|rhoa|cdc42|\bsting\b|\btbk\d*\b", re.I)),
    ("Epigenetic regulation", re.compile(r"dna methylation|dnam|cpg|histone|chromatin|h3k27ac|\bhdac|m6a|epigen", re.I)),
    ("Genetic moderators", re.compile(r"genotype|polymorphism|allele|gene variant|rs\d+|metabolizer status|activity score", re.I)),
    ("Drug metabolism", re.compile(r"cyp\d|cytochrome p450|monoamine oxidase|mao[- ]?[ab]?|\bcomt\b|ugt\d|glucuron|biotransformation|enzymatic conversion", re.I)),
    ("Endocrine response", re.compile(r"cortisol|corticosterone|\bacth\b|prolactin|oxytocin|vasopressin|copeptin|leptin|melatonin|growth hormone", re.I)),
    ("Gene expression & activity markers", re.compile(r"c[- ]?fos|fosb|\barc\b|egr[- ]?\d|immediate early|transcriptom|rna[- ]?seq|mirna|micro[- ]?rna|gene expression profile", re.I)),
)


def molecular_parent_from_specific(row: dict, current_parent: str, entity_label: str) -> str:
    context = molecular_subtopic_context(row, entity_label)
    if normalize(current_parent) in {"Genetic moderators", "Epigenetic regulation"}:
        return normalize(current_parent)
    if re.search(r"\b(genotype|polymorphism|allele|gene variant|rs\d+|metabolizer status|activity score)\b", context, re.I):
        return "Genetic moderators"
    if re.search(r"\b(dna methylation|dnam|cpg|histone|chromatin|h3k27ac|hdac\d*|m6a|epigen\w*)\b", context, re.I):
        return "Epigenetic regulation"
    for parent_label, pattern in MOLECULAR_SPECIFIC_PARENT_RULES:
        if pattern.search(context):
            return parent_label
    return normalize(current_parent)


MOLECULAR_SUBTOPIC_MIN_AUDIT_ROWS = 50
MOLECULAR_SUBTOPIC_MAX_RESIDUAL_RATE = 0.20


def molecular_subtopic_coverage_summary(findings: pd.DataFrame) -> dict:
    if findings.empty or "domain" not in findings.columns:
        return {"status": "ok", "threshold": MOLECULAR_SUBTOPIC_MAX_RESIDUAL_RATE, "parents": []}
    molecular = findings[findings["domain"] == "molecular_pathway_readout"].copy()
    kind_column = (
        "entity_kind"
        if "entity_kind" in molecular.columns
        else "kg_entity_kind_override"
        if "kg_entity_kind_override" in molecular.columns
        else ""
    )
    if kind_column:
        molecular = molecular[molecular[kind_column].isin(MOLECULAR_EFFECT_ENTITY_KINDS)].copy()
    # This gate protects the detailed molecular categorization extracted from
    # primary studies. Review relationships use a coarser paper-level contract
    # and should be audited separately rather than changing this gate's result.
    if "evidence_type" in molecular.columns:
        primary_molecular = molecular[molecular["evidence_type"] == "primary_evidence"].copy()
        if not primary_molecular.empty:
            molecular = primary_molecular
    if molecular.empty:
        return {"status": "ok", "threshold": MOLECULAR_SUBTOPIC_MAX_RESIDUAL_RATE, "parents": []}
    parent_rows: list[dict] = []
    failed: list[str] = []
    for parent_label, group in molecular.groupby("graph_parent_label", dropna=False):
        parent = normalize(parent_label)
        if not parent:
            continue
        total = int(len(group))
        normalized_subtopics = group["molecular_finding_subtopic"].fillna("").astype(str).str.strip().str.casefold()
        mapped = int((~normalized_subtopics.isin({"", "other", "other findings"})).sum())
        residual = total - mapped
        residual_rate = residual / total if total else 0.0
        audited = total >= MOLECULAR_SUBTOPIC_MIN_AUDIT_ROWS
        if audited and residual_rate > MOLECULAR_SUBTOPIC_MAX_RESIDUAL_RATE:
            failed.append(parent)
        parent_rows.append(
            {
                "parent_label": parent,
                "row_count": total,
                "mapped_count": mapped,
                "residual_count": residual,
                "residual_rate": round(residual_rate, 4),
                "audited": audited,
            }
        )
    return {
        "status": "failed" if failed else "ok",
        "evidence_scope": "primary_evidence" if "evidence_type" in findings.columns else "all",
        "threshold": MOLECULAR_SUBTOPIC_MAX_RESIDUAL_RATE,
        "min_rows": MOLECULAR_SUBTOPIC_MIN_AUDIT_ROWS,
        "failed_parents": failed,
        "parents": sorted(parent_rows, key=lambda item: item["parent_label"]),
    }


def canonical_molecular_effect_rule_label(value: object) -> str:
    return MOLECULAR_EFFECT_RULE_LABEL_BY_KEY.get(label_key(value), "")


def generic_molecular_effect_placeholder(value: object) -> bool:
    return label_key(value) in GENERIC_MOLECULAR_EFFECT_PLACEHOLDER_KEYS


def molecular_effect_context(row: dict, entity_label: object, fields: tuple[str, ...]) -> str:
    values: list[str] = []
    if not generic_molecular_effect_placeholder(entity_label):
        values.append(normalize(entity_label))
    for field in fields:
        value = row.get(field, "")
        if generic_molecular_effect_placeholder(value):
            continue
        values.append(normalize(value))
    return ascii_fold(" ".join(value for value in values if value))


def molecular_kind_context(row: dict | None, raw_label: object) -> str:
    row = row or {}
    fields = (
        "target",
        "target_type",
        "pathway_or_readout",
        "pathway_or_process",
        "readout_or_biomarker",
        "readout_or_measure",
        "assay_type",
        "assay_or_method",
        "action_type",
        "affinity_type",
        "metric",
        "effect_or_statistic",
        "finding_summary",
        "support",
        "outcome_measure",
    )
    return " ".join(endpoint_value(value) for value in (raw_label, *(row.get(field, "") for field in fields)))


def registry_kind_for_item(default_kind: str, item: dict | None, context_text: object = "", raw_label: object = "") -> str:
    status = normalize((item or {}).get("status", "")).casefold()
    if default_kind in {"condition_indication", "symptom_problem"}:
        if default_kind == "symptom_problem":
            return "symptom_problem"
        if "symptom_or_problem" in status:
            return "symptom_problem"
        return "condition_indication"
    if any(term in status for term in READOUT_REGISTRY_STATUS_TERMS):
        return "biomarker_readout"
    if any(term in status for term in PATHWAY_REGISTRY_STATUS_TERMS):
        return "pathway_process"
    if status in TARGET_FAMILY_REGISTRY_STATUSES or any(term in status for term in SYSTEM_REGISTRY_STATUS_TERMS):
        return "system_family"
    if status in DIRECT_TARGET_REGISTRY_STATUSES:
        text = ascii_fold(context_text)
        label_text = ascii_fold(raw_label)
        if READOUT_EVIDENCE_RE.search(label_text) and not DIRECT_TARGET_EVIDENCE_RE.search(label_text):
            return "biomarker_readout"
        if DIRECT_TARGET_EVIDENCE_RE.search(text):
            return "target"
        if READOUT_EVIDENCE_RE.search(text):
            return "biomarker_readout"
        return "target" if default_kind == "target" else default_kind
    return default_kind


def target_family_display_label(label: str, entity_kind: str) -> str:
    if entity_kind != "system_family":
        return label
    return TARGET_FAMILY_LABEL_OVERRIDES.get(label, label)


def match_registry_entity(
    raw_label: str,
    entity_kind: str,
    registry: dict[tuple[str, str], dict],
    row: dict | None = None,
) -> dict:
    entity_type = ENTITY_TYPE_BY_KIND.get(entity_kind, "")
    context_text = molecular_kind_context(row, raw_label)
    if entity_kind == "condition_indication" and CONDITION_NON_INDICATION_CONTEXT_RE.search(normalize(raw_label)):
        return {
            "matched": False,
            "label": "",
            "kind": entity_kind,
            "item": None,
            "status": "condition_context_not_graphable",
            "match_type": "",
            "notes": "family-history risk context is not promoted to a visible condition node",
        }
    if entity_kind == "condition_indication" and condition_analog_context(row, raw_label):
        return {
            "matched": False,
            "label": "",
            "kind": entity_kind,
            "item": None,
            "status": "condition_analog_not_graphable",
            "match_type": "",
            "notes": "condition-like or model-like wording is not promoted to a visible condition node",
        }
    contained_condition_labels = (
        set(condition_labels_in_text(raw_label, registry))
        if entity_kind == "condition_indication"
        else set()
    )
    canonical, item = canonicalize_registry_label(entity_type, raw_label, registry)
    if item:
        if entity_kind == "condition_indication" and contained_condition_labels and canonical not in contained_condition_labels:
            if len(contained_condition_labels) == 1:
                label = next(iter(contained_condition_labels))
                _, specific_item = canonicalize_registry_label(entity_type, label, registry)
                canonical_kind = registry_kind_for_item(entity_kind, specific_item, context_text, raw_label)
                return {
                    "matched": True,
                    "label": label,
                    "kind": canonical_kind,
                    "item": specific_item,
                    "status": "entity_normalized",
                    "match_type": "text_contains_registry_label",
                    "notes": "entity text contained a more specific local registry label",
                }
            return {
                "matched": False,
                "label": "",
                "kind": entity_kind,
                "item": None,
                "status": "entity_combo_not_graphable",
                "match_type": "",
                "notes": "entity text contains multiple graph entities; graph rows need one entity per edge",
            }
        if entity_kind == "condition_indication" and canonical in NON_GRAPHABLE_BROAD_CONDITION_LABELS:
            contextual_label = specific_condition_from_unambiguous_context(row, raw_label, canonical, registry)
            if contextual_label:
                _, contextual_item = canonicalize_registry_label(entity_type, contextual_label, registry)
                contextual_kind = registry_kind_for_item(
                    entity_kind,
                    contextual_item,
                    context_text,
                    contextual_label,
                )
                return {
                    "matched": True,
                    "label": contextual_label,
                    "kind": contextual_kind,
                    "item": contextual_item,
                    "status": "entity_normalized",
                    "match_type": "unambiguous_condition_context",
                    "notes": (
                        f"broad condition placeholder `{canonical}` resolved because the paper context names "
                        f"exactly one specific condition: `{contextual_label}`"
                    ),
                }
            return {
                "matched": False,
                "label": "",
                "kind": entity_kind,
                "item": item,
                "status": "condition_broad_placeholder_not_graphable",
                "match_type": registry_match_type(entity_type, raw_label, canonical, registry),
                "notes": f"broad condition placeholder `{canonical}` is not promoted to a visible condition node",
            }
        canonical_kind = registry_kind_for_item(entity_kind, item, context_text, raw_label)
        return {
            "matched": True,
            "label": canonical,
            "kind": canonical_kind,
            "item": item,
            "status": "entity_normalized",
            "match_type": registry_match_type(entity_type, raw_label, canonical, registry),
            "notes": "entity matched local registry",
        }
    matched_labels = (
        contained_condition_labels
        if entity_kind == "condition_indication"
        else registry_entity_labels_in_text(raw_label, entity_type, registry)
    )
    if len(matched_labels) == 1:
        label = next(iter(matched_labels))
        _, item = canonicalize_registry_label(entity_type, label, registry)
        canonical_kind = registry_kind_for_item(entity_kind, item, context_text, raw_label)
        return {
            "matched": True,
            "label": label,
            "kind": canonical_kind,
            "item": item,
            "status": "entity_normalized",
            "match_type": "text_contains_registry_label",
            "notes": "entity text contained one local registry label",
        }
    if len(matched_labels) > 1:
        return {
            "matched": False,
            "label": "",
            "kind": entity_kind,
            "item": None,
            "status": "entity_combo_not_graphable",
            "match_type": "",
            "notes": "entity text contains multiple graph entities; graph rows need one entity per edge",
        }
    return {
        "matched": False,
        "label": "",
        "kind": entity_kind,
        "item": None,
        "status": "entity_unmapped",
        "match_type": "",
        "notes": f"entity `{raw_label}` did not match local registry",
    }


def match_vocabulary_entity(
    raw_label: str,
    entity_kind: str,
    node_vocabulary: dict[tuple[str, str], dict],
) -> dict:
    canonical, item = canonicalize_node_label(entity_kind, raw_label, node_vocabulary)
    if item:
        return {
            "matched": True,
            "label": canonical,
            "kind": entity_kind,
            "item": item,
            "status": "entity_normalized",
            "match_type": "node_vocabulary",
            "notes": "entity matched route-native node vocabulary",
        }
    matched_labels = node_vocabulary_labels_in_text(raw_label, entity_kind, node_vocabulary)
    if len(matched_labels) == 1:
        label = next(iter(matched_labels))
        _, item = canonicalize_node_label(entity_kind, label, node_vocabulary)
        return {
            "matched": True,
            "label": label,
            "kind": entity_kind,
            "item": item,
            "status": "entity_normalized",
            "match_type": "text_contains_node_vocabulary_label",
            "notes": "entity text contained one route-native vocabulary label",
        }
    if len(matched_labels) > 1:
        return {
            "matched": False,
            "label": "",
            "kind": entity_kind,
            "item": None,
            "status": "entity_combo_not_graphable",
            "match_type": "",
            "notes": "entity text contains multiple graph entities; graph rows need one entity per edge",
        }
    return {
        "matched": False,
        "label": "",
        "kind": entity_kind,
        "item": None,
        "status": "entity_unmapped",
        "match_type": "",
        "notes": f"entity `{raw_label}` did not match route-native node vocabulary",
    }


PK_PARAMETER_DISPLAY_OVERRIDES = {
    "alkaloid concentration": "Concentration",
    "blood brain barrier penetration": "Blood-brain barrier penetration",
    "concentration": "Concentration",
    "concentration level": "Concentration",
    "concentration levels": "Concentration",
    "concentration_level": "Concentration",
    "consumption estimate": "Consumption estimate",
    "consumption_estimate": "Consumption estimate",
    "detection rate": "Detection rate",
    "dose": "Dose",
    "dose response": "Dose-response relationship",
    "dose response survival": "Dose-response relationship",
    "dose-response": "Dose-response relationship",
    "dose-response (survival)": "Dose-response relationship",
    "drug drug interaction": "Drug-drug interaction",
    "drug-drug interaction": "Drug-drug interaction",
    "ec50": "EC50",
    "excretion": "Excretion",
    "exposure response": "Exposure-response relationship",
    "exposure-response": "Exposure-response relationship",
    "limit of detection": "Limit of detection",
    "metabolic profile": "Metabolic profile",
    "metabolism": "Metabolism",
    "metabolite levels": "Concentration",
    "net influx rate ki": "Blood-brain barrier penetration",
    "presence": "Detected presence",
    "presence absence": "Detected presence",
    "presence/absence": "Detected presence",
    "route of administration efficacy": "Route/formulation effect",
    "route_of_administration_efficacy": "Route/formulation effect",
    "tissue concentration": "Concentration",
}


def canonical_pk_parameter_display_label(value: object, node_vocabulary: dict[tuple[str, str], dict]) -> str:
    text = normalize(value)
    if not text:
        return ""
    match = match_vocabulary_entity(text, "pharmacokinetic_parameter", node_vocabulary)
    if match["matched"]:
        return match["label"]
    override = PK_PARAMETER_DISPLAY_OVERRIDES.get(label_key(text))
    if override:
        return override
    return title_endpoint_label(text)


def is_pharmacokinetic_mechanism_target(label: object, row: dict) -> bool:
    text = ascii_fold(
        " ".join(
            endpoint_value(value)
            for value in (
                label,
                row.get("metabolic_or_transport_target", ""),
                row.get("metabolic_or_transport_pathway", ""),
                row.get("pk_or_exposure_parameter", ""),
                row.get("finding_summary", ""),
                row.get("support", ""),
            )
        )
    )
    return bool(
        re.search(
            r"\b(cyp\d|cytochrome|ugt|mao|monoamine oxidase|comt|aldehyde dehydrogenase|"
            r"alkaline phosphatase|transporter|p-glycoprotein|p glycoprotein|p-gp|"
            r"enzyme|metabolic|metabolism|demethylation|glucuronidation|deamination|"
            r"hydroxylation|dephosphorylation)\b",
            text,
            re.IGNORECASE,
        )
    )


def pharmacokinetic_display_label(
    row: dict,
    domain: str,
    entity_kind: str,
    entity_label: str,
    node_vocabulary: dict[tuple[str, str], dict],
) -> str:
    if domain != "pharmacokinetics_exposure":
        return ""

    graph_object_label = normalize(row.get("pk_graph_object_label", ""))
    if graph_object_label:
        return graph_object_label

    anchor_kind = normalized_entity_kind(row.get("primary_graph_anchor_kind", "")) or entity_kind
    parameter_label = canonical_pk_parameter_display_label(row.get("pk_or_exposure_parameter", ""), node_vocabulary)

    if anchor_kind == "compound":
        return parameter_label or "Metabolite/analyte measurement"
    if anchor_kind == "pharmacokinetic_parameter":
        return parameter_label or entity_label
    if anchor_kind in {"target", "system_family"} and not is_pharmacokinetic_mechanism_target(entity_label, row):
        return parameter_label or entity_label
    return entity_label or parameter_label


INTERVENTION_NON_NODE_RE = re.compile(
    r"\b(route of administration|intramuscular|intravenous|sublingual|infusion interval|booster dose|"
    r"ascending dose|dose sequence|dosing frequency|dosing regimen|dose concentration|dose escalation|boosters?|"
    r"session structure|session frequency|session duration|session timing|number of sessions|\d+[- ]hour sessions?|"
    r"treatment phase|therapy-free interval|premedication|co-administration|simultaneous administration|"
    r"sequential dosing|traditional dosing|"
    r"infusion rate|infusion duration|infusion frequency|number of infusions|single dose administration|"
    r"multiple doses|weak doses|supplemental dosing|concomitant medication|concomitant ssri|"
    r"concomitant dopaminergic|pharmacological action|polysubstance use|compound type|current alcohol use|comorbid|"
    r"mystical experience|ego dissolution|subjective experience|acute psychedelic experience|"
    r"vomit|vomiting|emesis|purging|biomarker|scale|score|baseline (?:trait|attachment)|"
    r"neuroticism|trait anxiety|race/ethnicity|patient clinical status|contraindication|"
    r"mri scanner|positron emission tomography|pet measurement|questionnaire|automated (?:cognitive|self-association) training|"
    r"blinding|palliative care (?:day centers?|trajectory)|perceived therapeutic benefit)\b",
    re.IGNORECASE,
)
INTERVENTION_TOPIC_RULES = (
    (
        "Dosing & administration",
        re.compile(r"\b(infusion method|bolus|administration route|route of administration|dose schedule|dosing method)\b", re.IGNORECASE),
    ),
    (
        "Control conditions",
        re.compile(r"\b(comparator type|control group|control condition|active placebo|inactive placebo|waitlist|waiting list)\b", re.IGNORECASE),
    ),
    (
        "Treatment intensity & duration",
        re.compile(r"\b(session count|session frequency|number of sessions|therapy hours|integration hours|treatment duration)\b", re.IGNORECASE),
    ),
    (
        "Preparation–integration protocols",
        re.compile(r"(?=.*\bprepar\w*\b)(?=.*\bintegrat\w*\b)", re.IGNORECASE),
    ),
    (
        "Cognitive behavioral therapy",
        re.compile(r"\b(cognitive behavio\w+ therapy|cbt|cbct|exposure and response prevention|erp)\b", re.IGNORECASE),
    ),
    (
        "Acceptance and commitment therapy",
        re.compile(r"\b(acceptance and commitment therapy|act therapy|act-based|act model|act)\b", re.IGNORECASE),
    ),
    (
        "Mindfulness-based intervention",
        re.compile(r"\b(mindful\w*|mbct|timber psychotherapy)\b", re.IGNORECASE),
    ),
    (
        "Motivational enhancement therapy",
        re.compile(r"\b(motivational enhancement therapy|met therapy|met program|met)\b", re.IGNORECASE),
    ),
    (
        "Other psychotherapy models",
        re.compile(
            r"\b(prolonged exposure|written exposure|exposure therapy|pet therapy|wet therapy|"
            r"psychoanalytic therapy|posthypnotic suggestion)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Other psychotherapy models",
        re.compile(r"\b(dialectical behavio\w+ therapy|dbt)\b", re.IGNORECASE),
    ),
    (
        "Other psychotherapy models",
        re.compile(r"\b(emdr|eye movement desensiti[sz]ation and reprocessing)\b", re.IGNORECASE),
    ),
    (
        "Cultural adaptation",
        re.compile(
            r"\b(culturally|cultural competen\w*|cultural humilit\w*|cultural adaptation|cultural tailoring|"
            r"racial sensitivity|racial themes|same-race practitioner|shared identity|inclusiv\w*|diversity)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Ceremonial & ritual context",
        re.compile(
            r"\b(ceremon\w*|ritual\w*|shaman\w*|shipibo|mazatec|santo daime|icaros|rite of passage|"
            r"traditional healing|indigenous tradition)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Therapist training",
        re.compile(
            r"\b(therapist training|facilitator training|provider training|practitioner training|speciali[sz]ed training|"
            r"certified training|accredited training|continuing education|training and education|provider education|"
            r"clinical education|multicultural competence|mentorship|practicum|workforce capacity)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Therapeutic alliance",
        re.compile(
            r"\b(therapeutic alliance|working alliance|patient[- ]therapist rapport|therapeutic rapport|"
            r"therapeutic relationship|relational safety|therapeutic connection)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Therapeutic touch",
        re.compile(r"\b(therapeutic touch|supportive touch|physical touch|consent process for touch|touch protocol)\b", re.IGNORECASE),
    ),
    (
        "Facilitator role",
        re.compile(
            r"\b(facilitator\w*|session facilitators|guide(?:'s)? role|sitter role|companion role|therapist presence|"
            r"provider role|practitioner role|clinician presence|attendant support|healthcare professional presence|"
            r"therapist[- ]to[- ]participant ratio|therapist dyad|dual-clinician|co-therapist|chaperone|therapist attitude)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Group therapy",
        re.compile(
            r"\b(group therapy|group psychotherapy|group treatment|group therapeutic|group-oriented|group-facilitated|"
            r"group psilocybin|group format|group delivery|group session|group-based|dyadic group)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Remote & at-home delivery",
        re.compile(r"\b(at[- ]home|home[- ]based|telehealth|remote delivery|remote monitoring|virtual care)\b", re.IGNORECASE),
    ),
    (
        "Outpatient delivery",
        re.compile(r"\b(outpatient|out-patient|ambulatory|in[- ]office care|office[- ]based care)\b", re.IGNORECASE),
    ),
    (
        "Residential & retreat delivery",
        re.compile(
            r"\b(residential|inpatient|retreat|treatment center|speciali[sz]ed clinic|hospital setting|"
            r"correctional facilit\w*|institutional setting)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Palliative & end-of-life care",
        re.compile(r"\b(palliative care|hospice care|end[- ]of[- ]life care|care of the dying|dying care)\b", re.IGNORECASE),
    ),
    (
        "Emergency & acute care delivery",
        re.compile(r"\b(emergency department|emergency care|acute care|critical care|intensive care)\b", re.IGNORECASE),
    ),
    (
        "Clinical supervision & monitoring",
        re.compile(
            r"\b(medical supervision|clinical supervision|provider supervision|supervised sessions?|"
            r"psychiatric supervision|clinical monitoring|medical monitoring|close supervision|monitor supervision)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Family & caregiver involvement",
        re.compile(
            r"\b(family involvement|family therapy|family support|caregiver|support partner|dyadic relationship|parenting skills)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Peer & community support",
        re.compile(
            r"\b(peer support|peer[- ]led|trusted friends|community support|community belonging|community of practice|"
            r"therapeutic community|social support|support system involvement|communitas)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Non-directive support",
        re.compile(r"\b(non[- ]?directive|nondirective|inner[- ]directed|minimalist facilitator)\b", re.IGNORECASE),
    ),
    (
        "Psychological support",
        re.compile(
            r"\b(psychological support|psychosocial support|therapeutic support|emotional support|mental health professional support|"
            r"supportive conditions|supportive environment|support and safety|in-session support|grounding technique|"
            r"therapist support level|physical presence and emotional support)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Music",
        re.compile(r"\b(music\w*|playlist\w*|song\w*|soundscape\w*|musical expression|hymns?)\b", re.IGNORECASE),
    ),
    (
        "Sensory environment",
        re.compile(
            r"\b(eye ?shades?|eyes[- ]closed|sensory environment|sensory stimuli|sensory intervention|"
            r"naturalistic stimuli|guided meditation|movie watching|visual healing|nature-themed video|room environment|"
            r"physical care environment|lighting|image induction)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Preparation",
        re.compile(r"\b(prepar\w*|readiness|pre-session)\b", re.IGNORECASE),
    ),
    (
        "Integration",
        re.compile(r"\b(integrat\w*|aftercare|post-session processing|debrief\w*)\b", re.IGNORECASE),
    ),
    (
        "Set & setting",
        re.compile(
            r"\b(set and setting|set/setting|setting and environment|environmental setting|dosing room|physical setting|"
            r"social environment|natural settings?|clinical setting|laboratory versus therapeutic settings?|"
            r"supportive setting|environmental safety|privacy and noise)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Expectations & intentions",
        re.compile(
            r"\b(expectation\w*|expectancy|intention\w*|mindset|belief in efficacy|treatment preference|"
            r"pre-dose well-being|pre-dose mental state|treatment credibility|preference-matching)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Prior psychedelic experience",
        re.compile(
            r"\b(prior psychedelic|previous psychedelic|past psychedelic|first-hand experience|personal experience with psilocybin|"
            r"therapist self-experience)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Screening & consent",
        re.compile(r"\b(screening|informed consent|consent document|exclusion criteria|baseline diagnostic|cooling[- ]off period)\b", re.IGNORECASE),
    ),
    (
        "Session components",
        re.compile(
            r"\b(safety monitoring|clinical monitoring|safety practice|support-seeking|close supervision|monitoring and observation)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Session components",
        re.compile(r"\b(psychoeducation|educational material|educational information|patient education)\b", re.IGNORECASE),
    ),
    (
        "Somatic & experiential practices",
        re.compile(
            r"\b(breathing|body-focused|somatic|dance|chanting|yoga|massage|journaling|experiential practice|"
            r"internal exploration|catharsis|emotional release)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Treatment access & equity",
        re.compile(
            r"\b(access|equity|financial barrier|geographic proximity|special access program|affordab\w*|availability|"
            r"public healthcare|underserved|treatment barrier)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Implementation & feasibility",
        re.compile(
            r"\b(implementation|feasib\w*|acceptab\w*|fidelity|standardization|logistics|service establishment|"
            r"protocol development|practical barrier|therapist compensation|staff attitudes|provider attitudes|"
            r"scalab\w*|resource[- ]intensive|resource requirements?|therapist time|monitoring requirements?|"
            r"treatment infrastructure|quality management system|care model|clinical guidance)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Clinical implementation",
        re.compile(
            r"\b(clinical practice|routine clinical practice|established psychiatric practice|practice integration|"
            r"clinical workflow|routine care)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Regulation & service delivery",
        re.compile(
            r"\b(regulat\w*|policy|service oversight|drug supply|national monitoring system|public hospital|"
            r"controlled substance scheduling|healthcare system|service delivery)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Collaborative & multidisciplinary care",
        re.compile(
            r"\b(collaborative care|multidisciplinary|interdisciplinary|treatment team|team-based|co-produced|"
            r"person-centred care|person-centered care|shared decision-making)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Spiritual support",
        re.compile(
            r"\b(spiritual support|spiritual counselling|religious counselling|spiritual framework|religious framework|"
            r"spiritual practice|psychospiritual|psycho-spiritual|sacred sensemaking)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Other psychotherapy models",
        re.compile(r"\b(compassion\w* imagery|compassion-focused|compassionate imagery)\b", re.IGNORECASE),
    ),
    (
        "Other psychotherapy models",
        re.compile(r"\b(inner heal\w+ intelligence|inner healer|intrinsic healing mechanism)\b", re.IGNORECASE),
    ),
    (
        "Psychotherapy",
        re.compile(
            r"\b(psychotherap\w*|therapy model|therapeutic model|manuali[sz]ed therapy|talking therap\w*|"
            r"psychological intervention|therapeutic framework|treatment model|assisted therapy|bridge therapy|"
            r"induced anxiety therapy|contextual therapy variables)\b",
            re.IGNORECASE,
        ),
    ),
)
INTERVENTION_TOPIC_LABELS = {label for label, _pattern in INTERVENTION_TOPIC_RULES}
INTERVENTION_REFINABLE_TOPIC_LABELS = {"Psychotherapy", "Psychological support"}

GENERAL_TOPIC_COVERAGE_LABELS = {
    "evidence gap": "Evidence gaps",
    "research landscape": "Research landscape",
    "methodological contribution": "Methods & frameworks",
    "review synthesis": "Review synthesis",
    "reviewed relationship": "Reviewed relationship",
}


def general_topic_coverage_label(row: dict) -> str:
    key = label_key(row.get("coverage_type", "") or row.get("claim_type", ""))
    controlled = GENERAL_TOPIC_COVERAGE_LABELS.get(key, "")
    if controlled:
        return controlled
    raw = ascii_fold(
        " ".join(
            normalize(row.get(field, ""))
            for field in ("graph_entity_label", "public_health_measure", "research_topic")
        )
    )
    if re.search(r"\b(research|publication|evidence) landscape\b|\bpsychedelic research\b", raw, re.IGNORECASE):
        return "Research landscape"
    if re.search(r"\b(method|methodology|framework)\w*\b", raw, re.IGNORECASE):
        return "Methods & frameworks"
    if re.search(r"\b(evidence|research|knowledge) gaps?\b", raw, re.IGNORECASE):
        return "Evidence gaps"
    return "General topic coverage"


def intervention_topic_from_context(context: object) -> str:
    text = ascii_fold(context)
    if not text:
        return ""
    for label, pattern in INTERVENTION_TOPIC_RULES:
        if pattern.search(text):
            return label
    return ""


def intervention_parent_label(row: dict, raw_label: object) -> str:
    anchor_context = " ".join(
        normalize(value)
        for value in (
            raw_label,
            row.get("context_component", ""),
        )
    )
    anchor_topic = intervention_topic_from_context(anchor_context)
    if anchor_topic and anchor_topic not in INTERVENTION_REFINABLE_TOPIC_LABELS:
        return anchor_topic

    refinement_contexts = (
        " ".join(
            normalize(value)
            for value in (
                row.get("intervention_model_or_orientation", ""),
                row.get("component_type", ""),
            )
        ),
        normalize(row.get("delivery_format", "")),
    )
    for context in refinement_contexts:
        topic = intervention_topic_from_context(context)
        if topic and topic not in INTERVENTION_REFINABLE_TOPIC_LABELS:
            return topic
    return anchor_topic or next(
        (topic for context in refinement_contexts if (topic := intervention_topic_from_context(context))),
        "",
    )


def intervention_specific_label(raw_label: object) -> str:
    label = title_endpoint_label(raw_label)
    if not label or len(label) > 120:
        return ""
    return label


def graphable_entity_match(
    row: dict,
    domain: str,
    entity_kind: str,
    raw_label: str,
    registry: dict[tuple[str, str], dict],
    node_vocabulary: dict[tuple[str, str], dict],
) -> dict:
    raw = normalize(raw_label)
    if not raw:
        return {
            "matched": False,
            "label": "",
            "kind": entity_kind,
            "item": None,
            "status": "entity_missing",
            "match_type": "",
            "notes": "entity label is empty",
        }
    if domain == "molecular_target" and entity_kind == "compound" and is_review_row(row):
        return {
            "matched": False,
            "label": "",
            "kind": entity_kind,
            "item": None,
            "status": "review_compound_object_not_target",
            "match_type": "",
            "notes": (
                "a review's compound object is retained in the evidence audit but cannot be "
                "projected as a molecular target"
            ),
        }
    if entity_kind in MOLECULAR_EFFECT_ENTITY_KINDS and generic_molecular_effect_placeholder(raw):
        specific_raw = molecular_specific_anchor_label(row, entity_kind)
        if not specific_raw or label_key(specific_raw) == label_key(raw):
            return {
                "matched": False,
                "label": "",
                "kind": entity_kind,
                "item": None,
                "status": "molecular_effect_placeholder_not_graphable",
                "match_type": "",
                "notes": "broad molecular system label needs a specific process or readout before graphing",
            }
        raw = specific_raw
    if (
        entity_kind == "cognitive_behavioral_construct"
        and normalize(row.get("endpoint_label_source", "")) == "controlled_behavioral_detail"
    ):
        vocabulary_match = match_vocabulary_entity(raw, entity_kind, node_vocabulary)
        if vocabulary_match["matched"]:
            vocabulary_match["match_type"] = "controlled_behavioral_vocabulary"
            vocabulary_match["notes"] = (
                "controlled behavioral label matched the route-native cognitive vocabulary"
            )
            return vocabulary_match
        return {
            "matched": raw in CONTROLLED_BEHAVIORAL_DETAIL_NODE_LABELS,
            "label": raw if raw in CONTROLLED_BEHAVIORAL_DETAIL_NODE_LABELS else "",
            "kind": entity_kind,
            "item": {"status": "controlled_behavioral_detail"},
            "status": "entity_normalized" if raw in CONTROLLED_BEHAVIORAL_DETAIL_NODE_LABELS else "entity_unmapped",
            "match_type": "controlled_behavioral_detail" if raw in CONTROLLED_BEHAVIORAL_DETAIL_NODE_LABELS else "",
            "notes": "generic behavioral measure retained as a controlled paper-detail node",
        }
    if entity_kind == "cognitive_behavioral_construct" and label_key(raw) in GENERIC_BEHAVIOR_NOT_GRAPHABLE_KEYS:
        return {
            "matched": False,
            "label": "",
            "kind": entity_kind,
            "item": None,
            "status": "generic_behavior_not_graphable",
            "match_type": "",
            "notes": "generic activity or behavior label is too broad for the cognition graph",
        }
    brain_measure_label = brain_measure_graph_label(raw)
    brain_measure_kind_compatible = (
        entity_kind in BRAIN_MEASURE_COMPATIBLE_ENTITY_KINDS
        or (entity_kind == "pathway_process" and brain_measure_label == "Brain structure")
    )
    if brain_measure_label and brain_measure_kind_compatible:
        return {
            "matched": True,
            "label": brain_measure_label,
            "kind": "brain_measure",
            "item": None,
            "status": "entity_normalized",
            "match_type": "brain_measure_pattern",
            "notes": "brain readout rerouted from a compatible entity kind to a stable detail-only measure family",
        }
    if entity_kind == "brain_measure":
        label = brain_measure_graph_label(raw)
        return {
            "matched": bool(label),
            "label": label,
            "kind": entity_kind,
            "item": None,
            "status": "entity_normalized" if label else "brain_measure_not_graphable",
            "match_type": "brain_measure_pattern" if label else "",
            "notes": (
                "brain readout normalized to a stable measure family"
                if label
                else "brain measure/readout did not match a stable measure family"
            ),
        }
    if (domain == "brain_system" or entity_kind in {"brain_region", "brain_network", "neural_circuit"}) and BRAIN_MEASURE_NOT_GRAPHABLE_RE.search(raw):
        return {
            "matched": False,
            "label": "",
            "kind": entity_kind,
            "item": None,
            "status": "brain_measure_not_graphable",
            "match_type": "",
            "notes": "brain measure/readout is kept as metadata rather than promoted to a brain-region graph node",
        }
    if entity_kind in {"brain_region", "brain_network", "neural_circuit"} and label_key(raw) in BROAD_BRAIN_SYSTEM_NOT_GRAPHABLE_KEYS:
        return {
            "matched": False,
            "label": "",
            "kind": entity_kind,
            "item": None,
            "status": "broad_brain_system_not_graphable",
            "match_type": "",
            "notes": "brain-system label is too broad to promote to a visible graph node",
        }
    if entity_kind == "condition_indication" and NON_CLINICAL_MODEL_POPULATION_RE.search(raw):
        return {
            "matched": False,
            "label": "",
            "kind": entity_kind,
            "item": None,
            "status": "population_not_graphable",
            "match_type": "",
            "notes": "population/model label is not a condition node",
        }
    if entity_kind == "safety_adverse_event":
        parent_label = (
            safety_category_for_text(raw)
            if normalize(row.get("endpoint_label_source", "")) == "entity_text_split"
            else safety_endpoint_label(row)
        )
        label = safety_specific_endpoint_label(row, parent_label)
        return {
            "matched": bool(label),
            "label": label,
            "kind": entity_kind,
            "item": None,
            "status": "entity_normalized" if label else "entity_unmapped",
            "match_type": "safety_endpoint_pattern" if label else "",
            "notes": "specific safety event retained beneath a stable safety category"
            if label
            else "safety/adverse-event entity did not match a displayable safety bucket",
        }
    if entity_kind == "outcome_scale":
        label = title_endpoint_label(raw)
        return {
            "matched": bool(label),
            "label": label,
            "kind": entity_kind,
            "item": None,
            "status": "entity_normalized" if label else "entity_unmapped",
            "match_type": "outcome_scale_label",
            "notes": "outcome scale label normalized" if label else f"entity `{raw}` did not produce an outcome scale label",
        }
    if entity_kind == "intervention_component":
        context = ascii_fold(
            " ".join(
                normalize(value)
                for value in (raw, row.get("context_component", ""), row.get("component_type", ""))
            )
        )
        meta_analysis_context = (
            normalize(row.get("paper_type", "")) in {"meta_analysis", "network_meta_analysis"}
            and normalize(row.get("meta_analysis_result_role", ""))
            in {"subgroup_analysis", "meta_regression", "dose_response", "sensitivity_analysis"}
            and bool(intervention_topic_from_context(context))
        )
        if INTERVENTION_NON_NODE_RE.search(context) and not meta_analysis_context:
            return {
                "matched": False,
                "label": "",
                "kind": entity_kind,
                "item": None,
                "status": "intervention_context_metadata_not_graphable",
                "match_type": "",
                "notes": "dose, route, participant trait, subjective effect, or outcome belongs in metadata or another domain",
            }
        vocabulary_match = match_vocabulary_entity(raw, entity_kind, node_vocabulary)
        specific_label = (
            normalize(vocabulary_match.get("label", ""))
            if vocabulary_match["matched"]
            else intervention_specific_label(raw)
        )
        parent_label = intervention_parent_label(row, specific_label or raw)
        if parent_label and specific_label:
            item = {"status": "specific_intervention_context"}
            if label_key(specific_label) == label_key(parent_label):
                specific_label = parent_label
            else:
                item["parent"] = parent_label
            return {
                "matched": True,
                "label": specific_label,
                "kind": entity_kind,
                "item": item,
                "status": "entity_normalized",
                "match_type": "intervention_specific_with_topic",
                "notes": "specific treatment context wording retained beneath a recognizable researcher-facing topic",
            }
        return {
            "matched": False,
            "label": "",
            "kind": entity_kind,
            "item": None,
            "status": "intervention_context_topic_unmapped",
            "match_type": "",
            "notes": "treatment context wording did not match a recognizable graph topic",
        }
    if domain == "general_topic_coverage" and entity_kind == "public_health_measure":
        label = general_topic_coverage_label(row)
        return {
            "matched": True,
            "label": label,
            "kind": entity_kind,
            "item": None,
            "status": "entity_normalized",
            "match_type": "review_coverage_type",
            "notes": "general review coverage normalized from the controlled relationship type",
        }
    if entity_kind == "public_health_measure":
        topic_row = dict(row)
        topic_row["public_health_measure"] = raw
        label = public_health_graph_label(topic_row)
        if label and label != "Other real-world topics":
            return {
                "matched": True,
                "label": label,
                "kind": entity_kind,
                "item": None,
                "status": "entity_normalized",
                "match_type": "public_health_topic_rule",
                "notes": "research or public-health topic normalized to a controlled graph parent",
            }
    if entity_kind == "symptom_problem" and normalize(row.get("endpoint_label_source", "")) == "clinical_symptom_endpoint":
        label = normalize(raw)
        return {
            "matched": label in SYMPTOM_ENDPOINT_LABELS,
            "label": label if label in SYMPTOM_ENDPOINT_LABELS else "",
            "kind": entity_kind,
            "item": None,
            "status": "entity_normalized" if label in SYMPTOM_ENDPOINT_LABELS else "entity_unmapped",
            "match_type": "clinical_symptom_endpoint_pattern" if label in SYMPTOM_ENDPOINT_LABELS else "",
            "notes": (
                "clinical endpoint normalized to symptom/problem bucket"
                if label in SYMPTOM_ENDPOINT_LABELS
                else f"entity `{raw}` did not match a symptom/problem endpoint bucket"
            ),
        }
    if entity_kind == "compound":
        match = graphable_compound_match(raw, registry)
        return {
            "matched": match["matched"],
            "label": match["label"],
            "kind": entity_kind,
            "item": match["item"],
            "status": "entity_normalized" if match["matched"] else match["status"].replace("compound", "entity"),
            "match_type": match["match_type"],
            "notes": match["notes"],
        }
    if entity_kind in REGISTRY_BACKED_ENTITY_KINDS:
        match = match_registry_entity(raw, entity_kind, registry, row)
        if (
            not match["matched"]
            and entity_kind == "condition_indication"
            and normalize(row.get("source_type", "") or row.get("paper_type", "")).casefold()
            in {"meta_analysis", "network_meta_analysis"}
            and META_ANALYSIS_POPULATION_ENTITY_RE.search(raw)
        ):
            endpoint_label = meta_analysis_fallback_endpoint_label(row)
            if endpoint_label:
                return {
                    "matched": True,
                    "label": endpoint_label,
                    "kind": (
                        "condition_indication"
                        if endpoint_label in SYMPTOM_ENDPOINTS_AS_CONDITIONS
                        else "symptom_problem"
                    ),
                    "item": None,
                    "status": "entity_normalized",
                    "match_type": "meta_analysis_population_endpoint_fallback",
                    "notes": (
                        "meta-analysis population wording did not identify one condition; "
                        "the controlled reported outcome was retained as paper detail"
                    ),
                }
        if (
            match["matched"]
            and entity_kind in MOLECULAR_EFFECT_ENTITY_KINDS
            and generic_molecular_effect_placeholder(match["label"])
        ):
            specific_raw = molecular_specific_anchor_label(row, entity_kind)
            if specific_raw and label_key(specific_raw) != label_key(match["label"]):
                specific_label = pathway_readout_display_label(
                    row,
                    entity_kind,
                    title_endpoint_label(specific_raw),
                    specific_raw,
                    None,
                )
                if specific_label:
                    return {
                        "matched": True,
                        "label": specific_label,
                        "kind": entity_kind,
                        "item": None,
                        "status": "entity_normalized",
                        "match_type": "molecular_specific_from_broad_system",
                        "notes": "specific molecular readout retained instead of a broad transmitter-system label",
                    }
            return {
                "matched": False,
                "label": "",
                "kind": entity_kind,
                "item": None,
                "status": "molecular_effect_placeholder_not_graphable",
                "match_type": "",
                "notes": "broad molecular system label needs a specific process or readout before graphing",
            }
        if match["matched"] and entity_kind in MOLECULAR_EFFECT_ENTITY_KINDS:
            parent_label = molecular_effect_graph_label(row, entity_kind, raw)
            specific_raw = molecular_specific_anchor_label(row, entity_kind) or raw
            if (
                parent_label
                and label_key(match["label"]) == label_key(parent_label)
                and label_key(specific_raw) != label_key(parent_label)
            ):
                specific_label = pathway_readout_display_label(
                    row,
                    entity_kind,
                    title_endpoint_label(specific_raw),
                    specific_raw,
                    None,
                )
                if specific_label:
                    return {
                        "matched": True,
                        "label": specific_label,
                        "kind": entity_kind,
                        "item": None,
                        "status": "entity_normalized",
                        "match_type": "molecular_specific_with_parent",
                        "notes": "specific molecular entity retained beneath its normalized parent category",
                    }
        if match["matched"] or entity_kind not in MOLECULAR_EFFECT_ENTITY_KINDS or match["status"] != "entity_unmapped":
            return match
        specific_raw = molecular_specific_anchor_label(row, entity_kind) or raw
        if generic_molecular_effect_placeholder(raw) and label_key(specific_raw) == label_key(raw):
            return {
                "matched": False,
                "label": "",
                "kind": entity_kind,
                "item": None,
                "status": "molecular_effect_placeholder_not_graphable",
                "match_type": "",
                "notes": "generic molecular-effect placeholder needs a specific pathway or marker before graphing",
            }
        parent_label = molecular_effect_graph_label(row, entity_kind, raw)
        specific_label = pathway_readout_display_label(
            row,
            entity_kind,
            title_endpoint_label(specific_raw),
            specific_raw,
            None,
        )
        if parent_label and specific_label and label_key(specific_label) != label_key(parent_label):
            return {
                "matched": True,
                "label": specific_label,
                "kind": entity_kind,
                "item": None,
                "status": "entity_normalized",
                "match_type": "molecular_specific_with_parent",
                "notes": "specific molecular entity retained beneath its normalized parent category",
            }
        if parent_label and parent_label != "Other molecular effects":
            return {
                "matched": True,
                "label": parent_label,
                "kind": "pathway_process",
                "item": None,
                "status": "entity_normalized",
                "match_type": "molecular_parent_rule",
                "notes": "broad molecular category used because no more specific entity was available",
            }
        if generic_molecular_effect_placeholder(raw):
            return {
                "matched": False,
                "label": "",
                "kind": entity_kind,
                "item": None,
                "status": "molecular_effect_placeholder_not_graphable",
                "match_type": "",
                "notes": "generic molecular-effect placeholder needs a specific pathway or marker before graphing",
            }
        return match
    if domain == "brain_system" or entity_kind in BRAIN_SYSTEM_ENTITY_KINDS:
        return match_brain_vocabulary_entity(raw, entity_kind, node_vocabulary)
    if entity_kind in VOCABULARY_BACKED_ENTITY_KINDS:
        return match_vocabulary_entity(raw, entity_kind, node_vocabulary)
    return {
        "matched": False,
        "label": "",
        "kind": entity_kind,
        "item": None,
        "status": "entity_unmapped",
        "match_type": "",
        "notes": f"entity kind `{entity_kind}` has no normalization rule",
    }


COMPOUND_BLOCK_STATUSES = {
    "compound_class_not_graphable",
    "compound_combo_not_graphable",
    "compound_graph_scope_not_graphable",
    "compound_reference_not_graphable",
    "compound_unmapped",
}
EMPTY_ENDPOINT_VALUES = {"", "none", "not_applicable", "not applicable", "not_reported", "not reported", "unknown", "uncertain"}
SAFETY_ENDPOINT_ROLES = {"safety_or_adverse_event"}
SAFETY_WORSENED_RISK_RE = re.compile(
    r"\b("
    r"increas(?:ed|es|ing)|higher|greater|elevated|worsen(?:ed|ing|s)?|"
    r"more likely|greater likelihood|higher odds|new[- ]?onset|emerg(?:ed|ent)|treatment[- ]emergent|"
    r"induc(?:ed|es|ing)"
    r")\b",
    re.IGNORECASE,
)
SAFETY_NON_WORSENED_RE = re.compile(
    r"\b("
    r"decreas(?:ed|es|ing)|lower|reduc(?:ed|es|ing)|less likely|"
    r"not significantly associated|not associated|no significant|no detected|no meaningful"
    r")\b",
    re.IGNORECASE,
)
SAFETY_PHYSIOLOGY_TERMS = {
    "safety",
    "adverse",
    "tolerability",
    "cardiovascular",
    "respiratory",
    "vital",
    "toxicity",
    "toxic",
}
SYMPTOM_ROLE_VALUES = {"symptom_or_problem"}
ALWAYS_SYMPTOM_LABELS = {
    "Anxiety",
    "Depression",
    "Pain",
    "Demoralization",
    "Anhedonia",
    "Psychosis",
    "Complicated grief",
}
BROAD_SYMPTOM_OUTCOME_LABELS = {
    "Anxiety",
    "Depression",
    "Pain",
    "Somatization",
    "Stress",
}

SAFETY_ENDPOINT_PATTERNS = (
    (
        re.compile(r"\b(serotonin(?:[- ]like)? syndrome)\b", re.IGNORECASE),
        "Serotonin syndrome",
    ),
    (
        re.compile(r"\b(seizure|convulsion|epilep|grand mal|proconvulsive)\b", re.IGNORECASE),
        "Seizure/convulsion",
    ),
    (re.compile(r"\b(suicid\w*|c[- ]?ssrs)\b", re.IGNORECASE), "Suicidality risk"),
    (re.compile(r"\b(mania|manic|hypomania|manic episode|switch|ymrs|young mania)\b", re.IGNORECASE), "Mania/hypomania risk"),
    (
        re.compile(
            r"\b(psychosis|psychotic|psychotomimetic|hallucinat\w*|delusion|paranoia|"
            r"bprs|brief psychiatric rating|panss|positive symptoms?|negative symptoms?|"
            r"affective flattening|schizophrenia[- ]like)\b",
            re.IGNORECASE,
        ),
        "Psychosis risk",
    ),
    (re.compile(r"\b(tinnitus|ear ringing)\b", re.IGNORECASE), "Tinnitus/auditory symptoms"),
    (re.compile(r"\b(flashbacks?|hppd|persisting perceptual)\b", re.IGNORECASE), "Flashbacks/HPPD"),
    (
        re.compile(
            r"\b(blood pressure|heart rate|cardiovascular|hypertension|hypotension|qt|qtc|torsade|arrhythm|"
            r"pro[- ]?arrhythm|hERG|electrocardi|ecg|tachycardia|bradycardia|hemodynamic|valvulopathy|"
            r"cardiac|myocard|cardiotox\w*|contractile|atrium|atrial|hemorrhage|haemorrhage|vasculitis|stroke|"
            r"mean arterial pressure|pulse rate|vital signs?|ekg|qtcf|hemodynamics?|inotropic)\b",
            re.IGNORECASE,
        ),
        "Cardiovascular safety",
    ),
    (
        re.compile(r"\b(oxygen saturation|spo2|hypoxia|hypoxemia|respiratory|breathing|respiration|tidal volume)\b", re.IGNORECASE),
        "Respiratory safety",
    ),
    (re.compile(r"\b(?:nausea|vomit|emesis|diarrhea|gastrointestinal|gi)\b", re.IGNORECASE), "Nausea/vomiting"),
    (re.compile(r"\b(headache|migraine)\b", re.IGNORECASE), "Headache"),
    (
        re.compile(
            r"\b(dissociation|dissociative|derealization|derealisation|depersonalization|depersonalisation|"
            r"\bdp/dr\b|\bddd\b|cadss|clinician-administered dissociative)\b",
            re.IGNORECASE,
        ),
        "Dissociation",
    ),
    (
        re.compile(
            r"\b(bad drug effect|bad trip|challenging experience|difficult experience|negative subjective|adverse mental states?|"
            r"emergence reactions?|psychedelic effects?|psychedelic manifestations?)\b",
            re.IGNORECASE,
        ),
        "Challenging subjective effects",
    ),
    (
        re.compile(r"\b(visual impairment|reduced vision|blurred vision|vision changes?)\b", re.IGNORECASE),
        "Visual impairment",
    ),
    (
        re.compile(r"\b(confusion|disorientation|delirium|thought disorder|spaced out|disconnected)\b", re.IGNORECASE),
        "Confusion/cognitive disturbance",
    ),
    (
        re.compile(r"\b(muscle pain|myalgia|musculoskeletal pain)\b", re.IGNORECASE),
        "Musculoskeletal effects",
    ),
    (re.compile(r"\b(muscle spasms?)\b", re.IGNORECASE), "Musculoskeletal effects"),
    (re.compile(r"\b(dry mouth|xerostomia)\b", re.IGNORECASE), "Dry mouth"),
    (
        re.compile(r"\b(symptom worsening|clinical worsening|worsening symptoms?)\b", re.IGNORECASE),
        "Symptom worsening",
    ),
    (re.compile(r"\b(anxiety|panic|distress|fear)\b", re.IGNORECASE), "Anxiety/panic"),
    (
        re.compile(r"\b(poisoning|poisoned|intoxication|overdose|toxic exposure|poison control)\b", re.IGNORECASE),
        "Acute intoxication/poisoning",
    ),
    (
        re.compile(
            r"\b(hyperthermia|hypothermia|body temperature|core temperature|oral temperature|tympanic temperature|"
            r"thermoregul\w*|thermogenic|temperature rise)\b",
            re.IGNORECASE,
        ),
        "Body temperature effects",
    ),
    (
        re.compile(
            r"\b(cortisol|corticosterone|prolactin|acth|adrenal|growth hormone|pituitary|"
            r"endocrine|neuroendocrine|hpa axis)\b",
            re.IGNORECASE,
        ),
        "Endocrine effects",
    ),
    (
        re.compile(r"\b(drug[- ]?drug interactions?|drug interactions?|adverse interactions?|cyp2d6|maoi|mao-a inhibitor|moclobemide|paroxetine)\b", re.IGNORECASE),
        "Drug interaction risk",
    ),
    (
        re.compile(r"\b(placenta|placental|fetal|foetal|pregnancy|pregnant)\b", re.IGNORECASE),
        "Pregnancy/fetal exposure",
    ),
    (
        re.compile(r"\b(driving|traffic safety|accident|risk taking|self[- ]motion|heading perception)\b", re.IGNORECASE),
        "Driving/accident risk",
    ),
    (
        re.compile(r"\b(sexual dysfunction|erectile|sexual desire|seminal|reproductive)\b", re.IGNORECASE),
        "Sexual/reproductive effects",
    ),
    (
        re.compile(r"\b(immune|immunosuppress\w*|host resistance|neutrophil|myelosuppression|infection)\b", re.IGNORECASE),
        "Immune effects",
    ),
    (
        re.compile(r"\b(adulterat\w*|substitution|mislabel\w*|contaminat\w*|toxicosurveillance|risk register)\b", re.IGNORECASE),
        "Adulteration/substitution risk",
    ),
    (
        re.compile(r"\b(food intake|appetite|hypophagia)\b", re.IGNORECASE),
        "Eating/appetite effects",
    ),
    (
        re.compile(
            r"\b(developmental anomal\w*|embryonic development|developmental tox\w*|cephalic disorders?|"
            r"tail/spine deformit\w*|mortality)\b",
            re.IGNORECASE,
        ),
        "Developmental toxicity",
    ),
    (
        re.compile(r"\b(urinary|cystitis|bladder|lower urinary tract|urologic|urological)\b", re.IGNORECASE),
        "Urinary toxicity",
    ),
    (
        re.compile(r"\b(liver|hepatic|hepatotoxic|transaminase|cirrhosis|fatty infiltration|biliary|jaundice|cholangitis|cholangiopathy)\b", re.IGNORECASE),
        "Hepatic toxicity",
    ),
    (
        re.compile(r"\b(kidney|renal|acute kidney injury|\baki\b|rhabdomyolysis|creatinine)\b", re.IGNORECASE),
        "Renal/muscle toxicity",
    ),
    (
        re.compile(
            r"\b(neurotox\w*|cytotox\w*|cell viability|cell death|apoptosis|oxidative stress|ros|"
            r"dopaminergic (injury|damage|toxicity|lesions?|loss|depletion)|"
            r"serotonergic (injury|damage|toxicity|lesions?|loss|depletion|axons?)|"
            r"neurodegener\w*|serotonin depletion|5[- ]?ht depletion|5[- ]?ht loss|5[- ]?ht neurotoxicity|"
            r"5[- ]?ht markers?|sert|nerve terminal|axon\w*|denervation|gray matter|grey matter|brain metabolites?|"
            r"neuronal damage|blood[- ]brain barrier|bbb permeability|neuroinflammation|microglia|microglial|"
            r"interleukin[- ]?1|il[- ]?1|glial expression|purkinje|glial activation|calpain|caspase|"
            r"serotonin .{0,40}depletion|5[- ]?ht .{0,40}depletion|dopamine metabolism|dopamine nerve endings?|"
            r"dopaminergic terminal|dopamine uptake|dopamine reuptake|th-positive|dat|dopac|mitochondri\w*|"
            r"mitochondrial membrane potential|endoplasmic reticulum|er stress|dna damage|redox reactivity|hsp70|"
            r"heat shock protein|neuronal injury|neuronal loss)\b",
            re.IGNORECASE,
        ),
        "Neurotoxicity/cytotoxicity",
    ),
    (
        re.compile(
            r"\b(sedation|sedative|sleepiness|somnolence|drowsiness|eye.opening time|recovery time|"
            r"cognitive impairment|memory impairment|"
            r"impaired attention|attention impairment|attention deficits?|impaired concentration|"
            r"concentration impairment|motor coordination|motor functioning|ataxia|rotarod|falls?|concussion|dizziness|vertigo|gait|"
            r"tremors?|tremorigenic|impaired memory|memory impairment|"
            r"cognitive function|working memory|executive function|processing speed|moca)\b",
            re.IGNORECASE,
        ),
        "Sedation/cognitive or motor impairment",
    ),
    (
        re.compile(
            r"\b(sleep disturbances?|insomnia|night terrors?|sleep impairments?|hyperarousal)\b",
            re.IGNORECASE,
        ),
        "Sleep disturbance",
    ),
    (
        re.compile(
            r"\b(abuse liability|dependence liability|dependence risk|dependency risk|dependency|addiction liability|"
            r"self[- ]administration|conditioned place preference|cpp|rewarding effects?|misuse|craving|"
            r"drug liking|withdrawal syndrome|dependence threshold|intracranial self[- ]stimulation|icss|"
            r"reward[- ]related behavior|positive(?:ly)? reinforcing|abuse potential)\b",
            re.IGNORECASE,
        ),
        "Abuse/dependence liability",
    ),
    (
        re.compile(r"\b(body weight|weight gain|weight loss|metabolic|hypoglycemia|glucose tolerance|fasting glucose)\b", re.IGNORECASE),
        "Weight/metabolic safety",
    ),
    (
        re.compile(
            r"\b(all[- ]cause discontinuation|all[- ]cause dropout|drop[- ]?out rates?|dropout rates?|"
            r"proportion .{0,30} dropped out|leaving the study early|study withdrawal|retention in treatment|"
            r"discontinuation due to any reason|discontinuation due to inefficacy|acceptability)\b",
            re.IGNORECASE,
        ),
        "All-cause discontinuation",
    ),
    (
        re.compile(
            r"\b(discontinuation|discontinued|dropout|dropped out|withdrawal|withdrew)\b.{0,60}\b"
            r"(adverse|side effects?|tolerab|safety|ae|aes)\b|"
            r"\b(adverse|side effects?|tolerab|safety|ae|aes)\b.{0,60}\b"
            r"(discontinuation|discontinued|dropout|dropped out|withdrawal|withdrew)\b",
            re.IGNORECASE,
        ),
        "Discontinuation due to adverse events",
    ),
    (
        re.compile(
            r"\b(serious adverse|serious adverse events?|sae|saes|death|fatal|fatalit|life[- ]threat|"
            r"hospitali[sz]ation|emergency department|emergency medical treatment|medical attention|medical intervention|psychiatric attention|"
            r"critical care|intensive care|icu|intubation|endotracheal|coma)\b",
            re.IGNORECASE,
        ),
        "Serious adverse events",
    ),
    (
        re.compile(
            r"\b(well[- ]?tolerated|tolerab\w*|safe and tolerable|safe and well tolerated|"
            r"safety$|safety profile|safety/tolerability|safety and tolerability|acceptable safety|no safety concerns?|"
            r"medical screening|safety during)\b",
            re.IGNORECASE,
        ),
        "Overall tolerability",
    ),
    (
        re.compile(
            r"\b(adverse events?|adverse effects?|side effects?|\bae\b|\baes\b|negative effects?|unwanted effects?|"
            r"adverse reactions?|harmful effects?|harm experiences?|harm following use)\b",
            re.IGNORECASE,
        ),
        "Adverse events",
    ),
)
SAFETY_SUMMARY_LABELS = {
    "Overall tolerability",
    "Serious adverse events",
    "Discontinuation due to adverse events",
    "Adverse events",
    "All-cause discontinuation",
}
SAFETY_SPECIFIC_ENDPOINT_PATTERNS = (
    (re.compile(r"\b(pro[- ]?arrhythm|arrhythm|torsade)\b", re.IGNORECASE), "Arrhythmia risk"),
    (re.compile(r"\b(qt|qtc|qtcf)\b.{0,30}\b(prolong|increase|elevat)", re.IGNORECASE), "QT prolongation"),
    (re.compile(r"\b(hypertension|elevated blood pressure|blood pressure elevation|increased blood pressure)\b", re.IGNORECASE), "Blood pressure elevation"),
    (re.compile(r"\b(hypotension|decreased blood pressure|blood pressure reduction)\b", re.IGNORECASE), "Blood pressure reduction"),
    (re.compile(r"\b(tachycardia|elevated heart rate|heart[- ]rate elevation|increased heart rate)\b", re.IGNORECASE), "Heart-rate elevation"),
    (re.compile(r"\b(bradycardia|decreased heart rate)\b", re.IGNORECASE), "Heart-rate reduction"),
    (re.compile(r"\bnausea\b", re.IGNORECASE), "Nausea"),
    (re.compile(r"\b(vomit|vomiting|emesis)\b", re.IGNORECASE), "Vomiting"),
    (re.compile(r"\bheadache\b", re.IGNORECASE), "Headache"),
    (re.compile(r"\b(dizziness|vertigo)\b", re.IGNORECASE), "Dizziness/vertigo"),
    (re.compile(r"\b(sedation|sleepiness|somnolence|drowsiness)\b", re.IGNORECASE), "Sedation/somnolence"),
    (re.compile(r"\b(cognitive impairment|memory impairment|impaired memory|impaired attention)\b", re.IGNORECASE), "Cognitive impairment"),
    (re.compile(r"\b(ataxia|motor coordination|motor impairment|gait impairment)\b", re.IGNORECASE), "Motor impairment"),
    (re.compile(r"\b(anxiety|panic)\b", re.IGNORECASE), "Anxiety/panic"),
    (re.compile(r"\b(dissociation|derealization|depersonalization)\b", re.IGNORECASE), "Dissociation"),
    (re.compile(r"\b(hallucinat\w*)\b", re.IGNORECASE), "Perceptual disturbances"),
    (re.compile(r"\bpsychotomimetic\w*\b", re.IGNORECASE), "Psychotomimetic effects"),
    (
        re.compile(
            r"\b(psychosis|psychotic|delusion|paranoia|panss|positive symptoms?|negative symptoms?|"
            r"affective flattening|schizophrenia[- ]like)\b",
            re.IGNORECASE,
        ),
        "Psychosis risk",
    ),
    (re.compile(r"\b(tinnitus|ear ringing)\b", re.IGNORECASE), "Tinnitus/auditory symptoms"),
    (re.compile(r"\b(visual impairment|reduced vision|blurred vision)\b", re.IGNORECASE), "Visual impairment"),
    (re.compile(r"\b(confusion|disorientation|delirium|thought disorder|spaced out|disconnected)\b", re.IGNORECASE), "Confusion/cognitive disturbance"),
    (re.compile(r"\b(muscle pain|myalgia|musculoskeletal pain)\b", re.IGNORECASE), "Musculoskeletal effects"),
    (re.compile(r"\b(dry mouth|xerostomia)\b", re.IGNORECASE), "Dry mouth"),
    (re.compile(r"\b(symptom worsening|clinical worsening)\b", re.IGNORECASE), "Symptom worsening"),
    (re.compile(r"\b(psychedelic effects?|psychedelic manifestations?)\b", re.IGNORECASE), "Psychedelic subjective effects"),
    (re.compile(r"\b(mania|manic|hypomania)\b", re.IGNORECASE), "Mania/hypomania"),
    (re.compile(r"\b(suicidal ideation|suicidality|suicide attempt)\b", re.IGNORECASE), "Suicidality"),
    (re.compile(r"\b(seizure|convulsion)\b", re.IGNORECASE), "Seizure/convulsion"),
    (re.compile(r"\bserotonin syndrome\b", re.IGNORECASE), "Serotonin syndrome"),
)
SAFETY_SPECIFIC_PARENT_LABELS = {
    "Arrhythmia risk": "Cardiovascular safety",
    "QT prolongation": "Cardiovascular safety",
    "Blood pressure elevation": "Cardiovascular safety",
    "Blood pressure reduction": "Cardiovascular safety",
    "Heart-rate elevation": "Cardiovascular safety",
    "Heart-rate reduction": "Cardiovascular safety",
    "Nausea": "Nausea/vomiting",
    "Vomiting": "Nausea/vomiting",
    "Headache": "Headache",
    "Dizziness/vertigo": "Sedation/cognitive or motor impairment",
    "Sedation/somnolence": "Sedation/cognitive or motor impairment",
    "Cognitive impairment": "Sedation/cognitive or motor impairment",
    "Motor impairment": "Sedation/cognitive or motor impairment",
    "Anxiety/panic": "Anxiety/panic",
    "Dissociation": "Dissociation",
    "Perceptual disturbances": "Challenging subjective effects",
    "Psychotomimetic effects": "Psychosis risk",
    "Psychosis risk": "Psychosis risk",
    "Tinnitus/auditory symptoms": "Adverse events",
    PERSISTENT_PSYCHIATRIC_OR_PERCEPTUAL_SYMPTOMS_LABEL: "Adverse events",
    "Visual impairment": "Adverse events",
    "Confusion/cognitive disturbance": "Sedation/cognitive or motor impairment",
    "Musculoskeletal effects": "Adverse events",
    "Dry mouth": "Adverse events",
    "Symptom worsening": "Adverse events",
    "Psychedelic subjective effects": "Challenging subjective effects",
    "Mania/hypomania": "Mania/hypomania risk",
    "Suicidality": "Suicidality risk",
    "Seizure/convulsion": "Seizure/convulsion",
    "Serotonin syndrome": "Serotonin syndrome",
}
SYMPTOM_ENDPOINT_PATTERNS = (
    (
        re.compile(r"\b(study[- ]defined )?(clinical |treatment )?response(?: rates?)?\b", re.IGNORECASE),
        "Treatment response",
    ),
    (
        re.compile(r"\b(study[- ]defined )?(clinical |treatment )?remission(?: rates?)?\b", re.IGNORECASE),
        "Remission",
    ),
    (
        re.compile(r"\b(relapse|return to (?:drug )?use|resumption of (?:drug )?use)\b", re.IGNORECASE),
        "Relapse",
    ),
    (
        re.compile(
            r"\b(all[- ]cause discontinuation|all[- ]cause dropout|drop[- ]?out rates?|dropout rates?|"
            r"study withdrawal|leaving the study early|retention in treatment)\b",
            re.IGNORECASE,
        ),
        "Treatment discontinuation",
    ),
    (
        re.compile(r"\b(acceptability|treatment acceptability|treatment completion)\b", re.IGNORECASE),
        "Treatment acceptability",
    ),
    (
        re.compile(r"\b(symptom improvement|symptom reduction|clinical improvement|efficacy for symptom reduction)\b", re.IGNORECASE),
        "Symptom improvement",
    ),
    (
        re.compile(
            r"\b(suicid\w*|self[- ]injur\w*|sitb|c[- ]?ssrs|columbia suicide|beck scale for suicid|"
            r"madrs item 10|bdi item 9|hamd item 3|ham[- ]?d item 3|hdrs item 3)\b",
            re.IGNORECASE,
        ),
        "Suicidality",
    ),
    (
        re.compile(
            r"^(?:aggression|aggressive behavior|increased aggression|exacerbated aggression|"
            r"violent aggression|interpersonal violence|intimate partner violence|violence|"
            r"violence risk|violence prevention)$",
            re.IGNORECASE,
        ),
        "Aggression/violence",
    ),
    (
        re.compile(r"\b(psychological distress|mental distress|general distress|distress scores?)\b", re.IGNORECASE),
        "Psychological distress",
    ),
    (
        re.compile(
            r"\b(symptoms? of (?:mental|psychiatric) disorders?|psychiatric symptom severity|"
            r"mental health symptoms?(?: severity)?)\b",
            re.IGNORECASE,
        ),
        "Mental health symptoms",
    ),
    (
        re.compile(
            r"\b(clinical outcomes? and psychoactive effects?|psychoactive effects? and clinical outcomes?)\b",
            re.IGNORECASE,
        ),
        "Psychoactive effects-clinical outcome association",
    ),
    (
        re.compile(r"\b(anhedonia|shaps|snaith[- ]hamilton pleasure|teps|temporal experience of pleasure)\b", re.IGNORECASE),
        "Anhedonia",
    ),
    (
        re.compile(
            r"\b(trauma re[- ]?experienc\w*|re[- ]?experiencing|flashbacks?|nightmares?|"
            r"intrusive memories|intrusions?|hyperarousal)\b",
            re.IGNORECASE,
        ),
        "Trauma re-experiencing & avoidance",
    ),
    (
        re.compile(
            r"\b(eating disorder symptoms?|eating disorder psychopathology|eat[- ]?26|eating attitudes test|"
            r"eating concerns?|shape concerns?|weight concerns?|ybc[- ]?eds|yale[- ]brown[- ]cornell eating)\b",
            re.IGNORECASE,
        ),
        "Eating & body-image concerns",
    ),
    (
        re.compile(
            r"\b(obsessions?|compulsions?|obsession[- ]compulsion|obsessive[- ]compulsive symptoms?|"
            r"compulsive symptoms?|preoccupations?|somatic scanning|checking)\b",
            re.IGNORECASE,
        ),
        "Obsessions & compulsions",
    ),
    (
        re.compile(r"\b(sleep disturbance|sleep disturbances|sleep quality|insomnia|psqi|pittsburgh sleep|isi|insomnia severity)\b", re.IGNORECASE),
        "Sleep disturbance",
    ),
    (
        re.compile(r"\b(craving|withdrawal symptoms?|withdrawal syndrome|drug craving|alcohol craving|pacs)\b", re.IGNORECASE),
        "Craving & withdrawal",
    ),
    (
        re.compile(r"\b(pain intensity|pain reduction|pain relief|relief of allodynia|allodynia|pain interference|post[- ]?operative pain|postoperative pain|headache|migraine|bpi|brief pain)\b", re.IGNORECASE),
        "Pain",
    ),
    (
        re.compile(r"\b(existential distress|death and dying|fear of death|demoralization|dadds|terminal illness distress|cancer[- ]related distress)\b", re.IGNORECASE),
        "Existential distress",
    ),
    (
        re.compile(r"\b(mania|manic symptoms?|hypomania|hypomanic|ymrs)\b", re.IGNORECASE),
        "Mania/hypomania",
    ),
    (
        re.compile(r"\b(psychosis|psychotic|psychotomimetic|schizophrenia[- ]like symptoms?|panss|catatonia|delusion|paranoia)\b", re.IGNORECASE),
        "Psychotic-like symptoms",
    ),
    (
        re.compile(r"\b(gad[- ]?7|generalized anxiety disorder[- ]?7|ham[- ]?a|hamilton anxiety|stai|state[- ]trait anxiety|hads[- ]?a|anxiety symptoms?|trait anxiety|panic symptoms?)\b", re.IGNORECASE),
        "Anxiety & panic",
    ),
    (
        re.compile(r"\b(madrs|montgomery[- ](?:a|å)sberg|ham[- ]?d|hdrs|hamilton depression|phq[- ]?9|patient health questionnaire[- ]?9|bdi|beck depression|qids|quick inventory of depressive|hads[- ]?d|epds|edinburgh post(?:natal|partum) depression|depressive symptoms?|depressive symptomatology|depressive scores?|depression scores?|depression severity|depression symptoms?)\b", re.IGNORECASE),
        "Low mood & depressive symptoms",
    ),
)
SYMPTOM_ENDPOINT_LABELS = {label for _pattern, label in SYMPTOM_ENDPOINT_PATTERNS}
SYMPTOM_ENDPOINTS_AS_CONDITIONS = {
    "Suicidality",
}


def compact_spaces(value: object) -> str:
    return re.sub(r"\s+", " ", normalize(value)).strip()


def endpoint_value(value: object) -> str:
    text = compact_spaces(value)
    if normalize(text).casefold() in EMPTY_ENDPOINT_VALUES:
        return ""
    return text


def title_endpoint_label(value: object) -> str:
    text = endpoint_value(value)
    if not text:
        return ""
    if len(text) > 80:
        return ""
    if text.isupper() and len(text) <= 12:
        return text
    return text[:1].upper() + text[1:]


def display_anchor_label(label: object) -> str:
    text = endpoint_value(label)
    if not text:
        return ""
    no_parenthetical = re.sub(r"\s*\([^)]*\)\s*$", "", text).strip()
    if no_parenthetical and len(no_parenthetical) >= 3:
        return no_parenthetical
    return text


def label_with_suffix(base_label: str, suffix: str) -> str:
    base = display_anchor_label(base_label)
    if not base:
        return ""
    if label_key(base).endswith(label_key(suffix)):
        return base
    return f"{base} {suffix}"


def pathway_readout_context(row: dict, raw_label: object) -> str:
    fields = (
        "graph_entity_original",
        "raw_entity_label",
        "pathway_or_readout",
        "pathway_or_process",
        "readout_or_biomarker",
        "readout_or_measure",
        "assay_type",
        "assay_or_method",
        "outcome_measure",
        "finding_summary",
        "support",
        "effect_or_statistic",
    )
    return " ".join(endpoint_value(value) for value in (raw_label, *(row.get(field, "") for field in fields)))


def molecular_readout_display_label(row: dict, canonical_label: str, raw_label: object) -> str:
    context = pathway_readout_context(row, raw_label)
    folded = ascii_fold(context)
    raw_folded = ascii_fold(endpoint_value(raw_label))
    base = display_anchor_label(canonical_label)
    base_key = label_key(base)
    if not base:
        return canonical_label
    if base_key == "serotonin":
        receptor_match = re.search(r"\b5[- ]?ht\s*([0-9][a-z]?)\b", folded, flags=re.IGNORECASE)
        if receptor_match:
            base = f"5-HT{receptor_match.group(1).upper()}"
            base_key = label_key(base)
    # The extracted readout itself is more authoritative than incidental wording
    # elsewhere in the finding summary (for example, c-Fos expression described
    # as a marker of neuronal activation).
    if READOUT_PHOSPHORYLATION_RE.search(raw_folded):
        return label_with_suffix(base, "phosphorylation")
    if READOUT_ACTIVATION_RE.search(raw_folded):
        return label_with_suffix(base, "activation")
    if READOUT_MRNA_RE.search(raw_folded):
        return label_with_suffix(base, "mRNA expression")
    if re.search(r"\bprotein levels?\b|\bprotein abundance\b", raw_folded, flags=re.IGNORECASE):
        if re.search(r"\bprotein levels?\b", base, flags=re.IGNORECASE):
            return re.sub(r"\bprotein levels?\b", "protein levels", base, flags=re.IGNORECASE)
        return label_with_suffix(base, "protein levels")
    if READOUT_EXPRESSION_RE.search(raw_folded):
        return label_with_suffix(base, "expression")
    if READOUT_LEVEL_RE.search(raw_folded):
        if re.search(r"\blevels?\b", base, flags=re.IGNORECASE):
            return re.sub(r"\blevels?\b", "levels", base, flags=re.IGNORECASE)
        return label_with_suffix(base, "levels")
    if "methylation" in folded.casefold():
        return label_with_suffix(base, "methylation")
    if READOUT_GENETIC_RE.search(folded):
        return label_with_suffix(base, "genotype")
    if READOUT_RELEASE_RE.search(folded):
        return label_with_suffix(base, "release")
    if READOUT_UPTAKE_RE.search(folded):
        return label_with_suffix(base, "uptake")
    if READOUT_AVAILABILITY_RE.search(folded):
        if re.search(r"\bdensit(?:y|ies)\b", folded, flags=re.IGNORECASE):
            return label_with_suffix(base, "density")
        return label_with_suffix(base, "availability")
    if READOUT_PHOSPHORYLATION_RE.search(folded):
        return label_with_suffix(base, "phosphorylation")
    if READOUT_TRAFFICKING_RE.search(folded):
        if re.search(r"\bsurface\b", folded, flags=re.IGNORECASE):
            return label_with_suffix(base, "surface expression")
        return label_with_suffix(base, "trafficking")
    if READOUT_ELECTROPHYSIOLOGY_RE.search(folded):
        return label_with_suffix(base, "electrophysiology")
    if READOUT_ACTIVATION_RE.search(folded):
        return label_with_suffix(base, "activation")
    if READOUT_MRNA_RE.search(folded):
        return label_with_suffix(base, "mRNA expression")
    if re.search(r"\bprotein levels?\b|\bprotein abundance\b", folded, flags=re.IGNORECASE):
        if re.search(r"\bprotein levels?\b", base, flags=re.IGNORECASE):
            return re.sub(r"\bprotein levels?\b", "protein levels", base, flags=re.IGNORECASE)
        return label_with_suffix(base, "protein levels")
    if READOUT_EXPRESSION_RE.search(folded):
        return label_with_suffix(base, "expression")
    if READOUT_LEVEL_RE.search(folded):
        if re.search(r"\blevels?\b", base, flags=re.IGNORECASE):
            return re.sub(r"\blevels?\b", "levels", base, flags=re.IGNORECASE)
        return label_with_suffix(base, "levels")
    return canonical_label


def pathway_process_display_label(row: dict, canonical_label: str, raw_label: object, registry_item: dict | None) -> str:
    context = pathway_readout_context(row, raw_label)
    folded = ascii_fold(context)
    lowered = folded.casefold()
    base = display_anchor_label(canonical_label)
    base_key = label_key(base)
    status = normalize((registry_item or {}).get("status", "")).casefold()

    if base_key == "neuroplasticity":
        if re.search(r"\blong[- ]term potentiation\b|\bltp\b", lowered):
            return "Long-term potentiation"
        if re.search(r"\bpaired[- ]pulse facilitation\b|\bppf\b", lowered):
            return "Paired-pulse facilitation"
        if re.search(r"\bdendritic spine|spine density|mushroom spine|thin spine\b", lowered):
            return "Dendritic spine density"
        if re.search(r"\bneurogenesis|doublecortin|dcx|granule cell\b", lowered):
            return "Neurogenesis"
        if re.search(r"\bneurite|outgrowth\b", lowered):
            return "Neurite outgrowth"
        if re.search(r"\bsynaptogenesis|synapse formation|synaptic connections?\b", lowered):
            return "Synaptogenesis"
        if re.search(r"\bsynaptic plasticity\b", lowered):
            return "Synaptic plasticity"

    if base_key == "gut microbiota":
        if re.search(r"\bdiversity|shannon|simpson|chao\b", lowered):
            return "Gut microbiota diversity"
        if re.search(r"\bcomposition|beta[- ]diversity|taxa|bacteroides|escherichia\b", lowered):
            return "Gut microbiota composition"

    if "pathway_node" in status or base_key in PATHWAY_NODE_LABELS:
        if READOUT_PHOSPHORYLATION_RE.search(folded):
            return label_with_suffix(base, "phosphorylation")
        if READOUT_ACTIVATION_RE.search(folded):
            if "signaling" in base_key:
                return base
            return label_with_suffix(base, "activation")
        if READOUT_MRNA_RE.search(folded) or READOUT_EXPRESSION_RE.search(folded):
            return label_with_suffix(base, "expression")
        if re.search(r"\bsignaling|pathway\b", lowered):
            return label_with_suffix(base, "signaling")

    return canonical_label


def pathway_readout_display_label(
    row: dict,
    entity_kind: str,
    canonical_label: str,
    raw_label: object,
    registry_item: dict | None,
) -> str:
    raw_display_label = endpoint_value(raw_label)
    canonical_key = label_key(canonical_label)
    raw_key = label_key(raw_display_label)
    display_base = canonical_label
    if raw_display_label and canonical_key and canonical_key in raw_key and len(raw_key) > len(canonical_key):
        display_base = raw_display_label
    if entity_kind == "biomarker_readout":
        return molecular_readout_display_label(row, display_base, raw_label)
    if entity_kind == "pathway_process":
        return pathway_process_display_label(row, display_base, raw_label, registry_item)
    return canonical_label


SYMPTOM_DISPLAY_LABEL_OVERRIDES = {
    "Anxiety": "Anxiety & panic",
    "Anxiety disorders": "Anxiety & panic",
    "Depression": "Low mood & depressive symptoms",
    "Depressive disorders": "Low mood & depressive symptoms",
    "Pain conditions": "Pain",
    "Psychosis": "Psychotic-like symptoms",
}


def symptom_problem_display_label(label: str) -> str:
    return SYMPTOM_DISPLAY_LABEL_OVERRIDES.get(label, label)


def split_outcome_scales(value: object) -> list[str]:
    text = endpoint_value(value)
    if not text:
        return []
    parts = [endpoint_value(part) for part in re.split(r"\s*;\s*", text)]
    seen: set[str] = set()
    out: list[str] = []
    for part in parts:
        if not part:
            continue
        key = part.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(part)
    return out


def pattern_endpoint_label(row: dict, patterns: tuple[tuple[re.Pattern[str], str], ...], fallback: str) -> str:
    text = " ".join(
        endpoint_value(row.get(field, ""))
        for field in (
            "graph_entity_label",
            "entity_label",
            "raw_entity_label",
            "clinical_endpoint",
            "clinical_endpoint_category",
            "outcome_domain",
            "outcome_type",
            "outcome_measure",
            "outcome_measure_normalized",
            "adverse_events",
            "safety_event_or_measure",
            "safety_event_or_risk",
            "safety_category",
            "severity",
            "severity_or_seriousness",
            "seriousness",
            "frequency_or_rate",
            "discontinuation_or_withdrawal",
            "finding_summary",
            "support",
            "effect_or_statistic",
        )
    )
    for pattern, label in patterns:
        if pattern.search(text):
            return label
    return fallback


def is_legacy_neuropsychiatric_label(value: object) -> bool:
    return label_key(value) in LEGACY_NEUROPSYCHIATRIC_LABEL_KEYS


def without_legacy_neuropsychiatric_labels(row: dict) -> dict:
    out = dict(row)
    for field in (
        "graph_entity_label",
        "entity_label",
        "raw_entity_label",
        "clinical_endpoint",
        "clinical_endpoint_category",
        "safety_event_or_measure",
        "safety_event_or_risk",
        "safety_category",
    ):
        if is_legacy_neuropsychiatric_label(out.get(field, "")):
            out[field] = ""
    return out


def persistent_adverse_psychiatric_or_perceptual_symptoms(row: dict) -> bool:
    context = ascii_fold(
        " ".join(
            normalize(row.get(field, ""))
            for field in (
                "clinical_endpoint",
                "clinical_endpoint_category",
                "outcome_domain",
                "outcome_type",
                "outcome_measure",
                "outcome_measure_normalized",
                "adverse_events",
                "safety_event_or_measure",
                "safety_event_or_risk",
                "safety_category",
                "finding_summary",
                "support",
                "supporting_quote",
                "effect_or_statistic",
                "follow_up_duration",
                "follow_up_window_normalized",
                "assessment_timepoint",
                "timepoint",
            )
        )
    )
    return bool(
        PERSISTENT_POST_ACUTE_RE.search(context)
        and ADVERSE_PERSISTENT_PSYCHIATRIC_OR_PERCEPTUAL_RE.search(context)
    )


def safety_endpoint_label(row: dict) -> str:
    endpoint_row = without_legacy_neuropsychiatric_labels(row)
    explicit_endpoint = " ".join(
        endpoint_value(endpoint_row.get(field, ""))
        for field in (
            "graph_entity_label",
            "entity_label",
            "raw_entity_label",
            "clinical_endpoint",
            "clinical_endpoint_category",
            "safety_event_or_measure",
            "safety_event_or_risk",
            "safety_category",
        )
    )
    for pattern, label in SAFETY_ENDPOINT_PATTERNS:
        if pattern.search(explicit_endpoint):
            return label
    pattern_label = pattern_endpoint_label(endpoint_row, SAFETY_ENDPOINT_PATTERNS, "")
    if pattern_label:
        return pattern_label
    if persistent_adverse_psychiatric_or_perceptual_symptoms(endpoint_row):
        return PERSISTENT_PSYCHIATRIC_OR_PERCEPTUAL_SYMPTOMS_LABEL
    return ""


def safety_category_for_text(value: object) -> str:
    text = endpoint_value(value)
    for pattern, label in SAFETY_ENDPOINT_PATTERNS:
        if pattern.search(text):
            return label
    return ""


def safety_specific_endpoint_label(row: dict, parent_label: str) -> str:
    raw = first_endpoint_value(
        row,
        (
            "safety_event_or_measure",
            "safety_event_or_risk",
            "raw_entity_label",
            "entity_label",
            "graph_entity_original",
        ),
    )
    if not raw or parent_label in SAFETY_SUMMARY_LABELS:
        return parent_label
    for pattern, label in SAFETY_SPECIFIC_ENDPOINT_PATTERNS:
        if pattern.search(raw):
            return label
    return parent_label


def symptom_endpoint_label(row: dict) -> str:
    priority_text = " ".join(
        endpoint_value(row.get(field, ""))
        for field in ("clinical_endpoint", "graph_entity_original", "raw_entity_label")
    )
    for pattern, label in SYMPTOM_ENDPOINT_PATTERNS:
        if pattern.search(priority_text):
            return label
    if re.search(
        r"\b(cognitive|executive|attention|memory|quality of life|well[- ]?being|functioning|"
        r"satisfaction|treatment acceptability)\b",
        priority_text,
        re.IGNORECASE,
    ):
        return ""
    finding_text = " ".join(endpoint_value(row.get(field, "")) for field in ("finding_summary", "support"))
    for pattern, label in SYMPTOM_ENDPOINT_PATTERNS:
        if pattern.search(finding_text):
            return label
    return pattern_endpoint_label(row, SYMPTOM_ENDPOINT_PATTERNS, "")


def row_has_safety_physiology(row: dict) -> bool:
    role = normalize(row.get("entity_role", "")).casefold()
    if role != "physiological_measure":
        return False
    text = " ".join(normalize(row.get(field, "")).casefold() for field in ("outcome_type", "outcome_domain", "outcome_measure", "raw_entity_label"))
    return any(term in text for term in SAFETY_PHYSIOLOGY_TERMS)


def row_reports_worsened_safety_risk(row: dict) -> bool:
    outcome_orientation = normalize(
        row.get("outcome_type", "") or row.get("outcome_orientation", "")
    ).casefold()
    if outcome_orientation in {"beneficial", "neutral"}:
        return False
    if not safety_endpoint_label(row):
        return False
    direction = normalize(row.get("result_direction", "")).casefold()
    if direction in {"positive", "no_detected_effect", "not_applicable", "not reported", "not_reported"}:
        return False

    text = ascii_fold(
        " ".join(
            normalize(row.get(field, ""))
            for field in (
                "support",
                "finding_summary",
                "clinical_endpoint",
                "outcome_measure",
                "effect_or_statistic",
                "association_or_trend",
            )
        )
    )
    if SAFETY_NON_WORSENED_RE.search(text):
        return False
    return bool(SAFETY_WORSENED_RISK_RE.search(text))


def canonical_compound_from_audit(row: dict, audit: dict | None) -> str:
    audit = audit or {}
    if normalize(audit.get("normalization_status", "")) in COMPOUND_BLOCK_STATUSES:
        return ""
    return (
        normalize(audit.get("canonical_compound", ""))
        or normalize(row.get("canonical_compound", ""))
        or normalize(row.get("compound", ""))
    )


def endpoint_row(row: dict, audit: dict | None, label: str, kind: str, role: str, label_source: str) -> dict | None:
    compound = canonical_compound_from_audit(row, audit)
    label = endpoint_value(label)
    if not compound or not label:
        return None

    out = dict(row)
    out["compound_original"] = normalize(row.get("compound", ""))
    out["compound"] = compound
    out["disorder_original"] = normalize(row.get("disorder", ""))
    out["graph_entity_original"] = normalize(row.get("raw_entity_label", "")) or normalize(row.get("outcome_measure", ""))
    out["disorder"] = label
    out["raw_entity_label"] = normalize(row.get("raw_entity_label", "")) or label
    out["entity_role"] = role
    out["graph_entity_label"] = label
    out["graph_entity_type"] = "none"
    out["graph_include_candidate"] = True
    out["graph_exclusion_reason"] = "not_applicable"
    out["normalization_status"] = "endpoint_normalized"
    out["normalization_notes"] = f"Derived KG endpoint view row from {label_source}"
    out["canonical_compound"] = compound
    out["canonical_entity"] = label
    out["compound_match_type"] = normalize((audit or {}).get("compound_match_type", ""))
    out["compound_registry_status"] = normalize((audit or {}).get("compound_registry_status", ""))
    out["entity_match_type"] = "derived_endpoint"
    out["entity_registry_status"] = "derived_endpoint"
    out["kg_entity_kind_override"] = kind
    out["endpoint_label_source"] = label_source
    return out


def clinical_endpoint_rows(rows: list[dict], audit_rows: list[dict]) -> list[dict]:
    out: list[dict] = []
    for index, row in enumerate(rows):
        audit = audit_rows[index] if index < len(audit_rows) and isinstance(audit_rows[index], dict) else {}
        role = normalize(row.get("entity_role", "")).casefold()
        domain = normalize(row.get("domain", "")) or normalize(row.get("domain_route", ""))
        if domain in {"clinical", "clinical_outcome", ""} and clinical_subjective_effect_context(row):
            continue
        if (domain in CLINICAL_METADATA_DOMAINS or not domain) and not normalize(row.get("outcome_measure_normalized", "")):
            row = dict(row)
            row["outcome_measure_normalized"] = normalize_outcome_measure(row.get("outcome_measure", ""))

        if role in SAFETY_ENDPOINT_ROLES or row_has_safety_physiology(row):
            derived = endpoint_row(
                row,
                audit,
                safety_endpoint_label(row),
                "safety_adverse_event",
                normalize(row.get("entity_role", "")) or "safety_or_adverse_event",
                "safety_endpoint",
            )
            if derived:
                out.append(derived)

        if domain in {"clinical", "clinical_outcome", ""} and role not in SAFETY_ENDPOINT_ROLES and row_reports_worsened_safety_risk(row):
            derived = endpoint_row(
                row,
                audit,
                safety_endpoint_label(row),
                "safety_adverse_event",
                "safety_or_adverse_event",
                "clinical_worsened_safety_endpoint",
            )
            if derived:
                out.append(derived)

        if domain in {"clinical", "clinical_outcome", ""} and role not in SAFETY_ENDPOINT_ROLES and not row_has_safety_physiology(row):
            symptom_label = symptom_endpoint_label(row)
            if symptom_label:
                endpoint_kind = "condition_indication" if symptom_label in SYMPTOM_ENDPOINTS_AS_CONDITIONS else "symptom_problem"
                endpoint_role = "therapeutic_indication" if endpoint_kind == "condition_indication" else "symptom_or_problem"
                endpoint_source = "clinical_condition_endpoint" if endpoint_kind == "condition_indication" else "clinical_symptom_endpoint"
                derived = endpoint_row(
                    row,
                    audit,
                    symptom_label,
                    endpoint_kind,
                    endpoint_role,
                    endpoint_source,
                )
                if derived:
                    out.append(derived)

        explicit_kind = normalized_entity_kind(row.get("kg_entity_kind_override", ""))
        if role == "outcome_scale" or explicit_kind == "outcome_scale":
            for scale in split_outcome_scales(row.get("outcome_measure_normalized", "")):
                derived = endpoint_row(
                    row,
                    audit,
                    scale,
                    "outcome_scale",
                    "outcome_measure",
                    "explicit_outcome_scale",
                )
                if derived:
                    out.append(derived)
    return out


CONDITION_SPLIT_FIELDS = (
    "condition_or_population",
    "disorder",
    "condition",
    "graph_entity_label",
    "entity_label",
    "entity",
)


def condition_expanded_rows(row: dict, domain: str, registry: dict[tuple[str, str], dict]) -> list[dict]:
    if not graphable_subject_match(row, registry)["matched"]:
        return [row]

    entity_kind = entity_kind_for(row, domain)
    source_type = normalize(row.get("source_type", "") or row.get("paper_type", "")).casefold()
    if (
        domain == "clinical_outcome"
        and source_type in {"meta_analysis", "network_meta_analysis"}
        and entity_kind == "symptom_problem"
        and normalize(row.get("graph_admission_status", "")).casefold() != "paper_detail"
    ):
        population_context = " ".join(
            normalize(row.get(field, ""))
            for field in ("population", "population_or_subgroup", "condition_or_population", "clinical_context_condition")
            if normalize(row.get(field, ""))
        )
        population_labels = condition_labels_in_text(population_context, registry)
        if len(population_labels) == 1:
            condition_label = population_labels[0]
            condition_row = dict(row)
            condition_row["condition_or_population"] = condition_label
            condition_row["graph_entity_label"] = condition_label
            condition_row["entity_label"] = condition_label
            condition_row["entity"] = condition_label
            condition_row["kg_entity_kind_override"] = "condition_indication"
            condition_row["endpoint_label_source"] = "meta_analysis_population_condition_projection"
            condition_row["normalization_boundary_reason"] = "meta_analysis_outcome_linked_to_unambiguous_population_condition"
            return [row, condition_row]
    if entity_kind != "condition_indication":
        return [row]

    raw_entity_label = entity_label_for(row, domain, entity_kind)
    if condition_analog_context(row, raw_entity_label):
        return [row]
    labels = condition_labels_in_text(raw_entity_label, registry)
    if len(labels) <= 1:
        return [row]

    out: list[dict] = []
    for label in labels:
        split_row = dict(row)
        split_row["condition_or_population_original"] = raw_entity_label
        for field in CONDITION_SPLIT_FIELDS:
            if field in split_row or field in {"condition_or_population", "graph_entity_label", "entity_label"}:
                split_row[field] = label
        split_row["kg_entity_kind_override"] = "condition_indication"
        split_row["endpoint_label_source"] = "condition_text_split"
        out.append(split_row)
    return out


SAFE_ENTITY_SPLIT_KINDS = {
    "compound",
    "symptom_problem",
    "safety_adverse_event",
    "target",
    "pathway_process",
    "biomarker_readout",
    "brain_region",
    "brain_network",
    "neural_circuit",
    "intervention_component",
    "pharmacokinetic_parameter",
}
ENTITY_SPLIT_STATUS_CANDIDATES = {"entity_combo_not_graphable", "entity_unmapped"}
ENTITY_SPLIT_MAX_PARTS = 6
CONTROLLED_ENTITY_SPLIT_PARTS = {
    ("target", "mu and kappa opioid receptors"): ("mu opioid receptor", "kappa opioid receptor"),
    ("symptom_problem", "anxiety and depression symptoms"): ("anxiety symptoms", "depressive symptoms"),
    ("symptom_problem", "reduction in anxiety and depression"): ("anxiety symptoms", "depressive symptoms"),
}
ENTITY_SPLIT_SEMANTIC_UNIT_RE = re.compile(
    r"\b(complex|heterodimer|heteromer|homodimer|dimer|axis)\b",
    re.IGNORECASE,
)


def controlled_target_component_labels(value: object) -> list[str]:
    key = compact_key(value)
    word_key = label_key(value)
    if not key:
        return []

    if "5ht2a" in key:
        if "5ht2c" in key or re.search(r"5ht2a(?:and)?2c", key) or key.startswith("5ht2ac"):
            labels = ["5-HT2A", "5-HT2C"]
            for token, label in (
                ("5ht1a", "5-HT1A"),
                ("5ht1b", "5-HT1B"),
                ("5ht1d", "5-HT1D"),
                ("5ht1e", "5-HT1E"),
                ("5ht2b", "5-HT2B"),
            ):
                if token in key:
                    labels.append(label)
            return list(dict.fromkeys(labels))
    if "5ht2b" in key:
        if "5ht2c" in key or re.search(r"5ht2b(?:and)?2c", key) or key.startswith("5ht2bc"):
            return ["5-HT2B", "5-HT2C"]

    if "gabaa" in key or "gabatypea" in key:
        return ["GABA-A receptor family"]

    if "d1like" in key:
        return ["D1-like dopamine receptor family"]
    if "d2like" in key or "d23receptor" in key or key in {"dar2", "dar3"}:
        return ["D2-like dopamine receptor family"]

    if "alpha3beta4" in key and "alpha6" not in key:
        return ["alpha3beta4 nicotinic acetylcholine receptor"]
    if "alpha4beta2" in key:
        return ["alpha4beta2 nicotinic acetylcholine receptor"]
    if "alpha7" in key and ("nachr" in key or "nicotinic" in key):
        return ["alpha7 nicotinic acetylcholine receptor (CHRNA7)"]

    standalone_nr_subunit = re.search(r"\bnr(?:1|2[a-d]?)\b", word_key)
    if "nmda" in key or "nmdar" in key or "glun" in key or standalone_nr_subunit:
        labels: list[str] = []
        if "glun1" in key or re.search(r"\bnr1\b", word_key):
            labels.append("GluN1 (GRIN1)")
        for suffix, label in (
            ("a", "GluN2A (GRIN2A)"),
            ("b", "GluN2B (GRIN2B)"),
            ("c", "GluN2C (GRIN2C)"),
            ("d", "GluN2D (GRIN2D)"),
        ):
            if f"glun2{suffix}" in key or re.search(rf"\bnr2{suffix}\b", word_key):
                labels.append(label)
            elif "glun1" in key and re.search(rf"2{suffix}(?:2[a-d])*(?:nmda|nmdar|receptor|$)", key):
                labels.append(label)
            elif key.startswith(f"2{suffix}nmda"):
                labels.append(label)
        if labels:
            return list(dict.fromkeys(labels))

    return []


def entity_split_candidates(value: object) -> list[str]:
    text = normalize(value)
    if not text or not re.search(r"\s(?:and|or)\s|[;,/+]", text, flags=re.IGNORECASE):
        return []
    working = text.replace("；", ";")
    working = re.sub(r"\s+and/or\s+", ";", working, flags=re.IGNORECASE)
    working = re.sub(r"\s+(?:and|or)\s+", ";", working, flags=re.IGNORECASE)
    working = re.sub(r"\s*[;,/+]\s*", ";", working)
    working = re.sub(r"\s+", " ", working).strip("; ")
    parts = [normalize(part).strip(" .") for part in working.split(";")]
    parts = [part for part in parts if part]
    if len(parts) < 2 or len(parts) > ENTITY_SPLIT_MAX_PARTS:
        return []
    if any(len(label_key(part)) < 2 for part in parts):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for part in parts:
        key = label_key(part)
        if key in seen:
            continue
        seen.add(key)
        out.append(part)
    return out if len(out) > 1 else []


def entity_split_row(row: dict, entity_kind: str, label: str, source_label: str) -> dict:
    split_row = dict(row)
    fields = ENTITY_LABEL_FIELDS_BY_KIND.get(entity_kind, ())
    if fields:
        split_row[fields[0]] = label
    split_row["graph_entity_label"] = label
    split_row["entity_label"] = label
    split_row["entity"] = label
    split_row["graph_entity_original"] = source_label
    split_row["entity_split_source_label"] = source_label
    split_row["endpoint_label_source"] = "entity_text_split"
    split_row["kg_entity_kind_override"] = entity_kind
    if (
        entity_kind == "compound"
        and label_key(split_row.get("pk_graph_object_kind", "")) == "metabolite or analyte"
    ):
        split_row["pk_graph_object_label"] = label
    return split_row


def entity_expanded_rows(
    row: dict,
    domain: str,
    registry: dict[tuple[str, str], dict],
    node_vocabulary: dict[tuple[str, str], dict],
) -> list[dict]:
    if normalize(row.get("entity_split_source_label", "")):
        return [row]
    if not graphable_subject_match(row, registry)["matched"]:
        return [row]

    entity_kind = entity_kind_for(row, domain)
    structured_target_matches = structured_target_entity_matches(row)
    if domain == "molecular_target" and structured_target_matches:
        source_label = entity_label_for(row, domain, entity_kind)
        return [
            {
                **entity_split_row(row, target_kind, target_label, source_label),
                "endpoint_label_source": "meta_analysis_structured_target_entity",
                "normalization_boundary_reason": "explicit_target_entity_from_structured_result",
            }
            for target_kind, target_label in structured_target_matches
        ]
    support_target_matches = meta_analysis_target_support_matches(
        row,
        domain,
        entity_kind,
        registry,
    )
    if support_target_matches:
        source_label = entity_label_for(row, domain, entity_kind)
        projected_rows: list[dict] = []
        for projected_kind, projected_label in support_target_matches:
            projected = entity_split_row(
                row,
                projected_kind,
                projected_label,
                source_label,
            )
            projected["endpoint_label_source"] = "meta_analysis_support_target_entity_projection"
            projected["normalization_boundary_reason"] = (
                "explicit_target_entity_recovered_from_result_support"
            )
            projected_rows.append(projected)
        return projected_rows
    support_brain_matches = meta_analysis_brain_support_matches(
        row,
        domain,
        entity_kind,
        node_vocabulary,
    )
    if support_brain_matches:
        source_label = entity_label_for(row, domain, entity_kind)
        projected_rows: list[dict] = []
        for projected_kind, projected_label in support_brain_matches:
            projected = entity_split_row(
                row,
                projected_kind,
                projected_label,
                source_label,
            )
            projected["endpoint_label_source"] = "meta_analysis_support_brain_entity_projection"
            projected["normalization_boundary_reason"] = (
                "explicit_brain_entity_recovered_from_result_support"
            )
            projected_rows.append(projected)
        return projected_rows
    if entity_kind not in SAFE_ENTITY_SPLIT_KINDS:
        return [row]

    raw_entity_label = entity_label_for(row, domain, entity_kind)
    controlled_targets = controlled_target_component_labels(raw_entity_label)
    if controlled_targets and entity_kind in {"target", "system_family"}:
        split_rows: list[dict] = []
        normalized_targets: set[tuple[str, str]] = set()
        context = molecular_kind_context(row, raw_entity_label)
        for label in controlled_targets:
            canonical_label, item = canonicalize_registry_label("mechanistic_entity", label, registry)
            if not item:
                return [row]
            split_kind = registry_kind_for_item("target", item, context, raw_entity_label)
            target = (split_kind, canonical_label)
            if target in normalized_targets:
                continue
            normalized_targets.add(target)
            split_row = entity_split_row(row, split_kind, canonical_label, raw_entity_label)
            split_row["endpoint_label_source"] = "controlled_target_component_mapping"
            split_rows.append(split_row)
        if split_rows:
            return split_rows

    if entity_kind == "safety_adverse_event":
        parts = entity_split_candidates(raw_entity_label)
        if parts:
            split_rows: list[dict] = []
            normalized_labels: set[str] = set()
            for part in parts:
                split_row = entity_split_row(row, entity_kind, part, raw_entity_label)
                split_row["safety_event_or_measure"] = part
                parent_label = safety_category_for_text(part)
                if not parent_label:
                    continue
                specific_label = safety_specific_endpoint_label(split_row, parent_label)
                key = label_key(specific_label)
                if not key or key in normalized_labels:
                    continue
                normalized_labels.add(key)
                split_rows.append(split_row)
            if len(split_rows) > 1:
                return split_rows
    if domain == "brain_system" or entity_kind in BRAIN_SYSTEM_ENTITY_KINDS:
        brain_matches = brain_entity_split_matches(raw_entity_label, node_vocabulary)
        if brain_matches:
            split_rows: list[dict] = []
            for split_kind, split_label in brain_matches:
                split_rows.append(entity_split_row(row, split_kind, split_label, raw_entity_label))
            return split_rows

    initial_match = graphable_entity_match(row, domain, entity_kind, raw_entity_label, registry, node_vocabulary)
    if initial_match["matched"] or initial_match["status"] not in ENTITY_SPLIT_STATUS_CANDIDATES:
        return [row]

    controlled_parts = list(
        CONTROLLED_ENTITY_SPLIT_PARTS.get(
            (entity_kind, label_key(raw_entity_label)),
            (),
        )
    )
    if not controlled_parts and ENTITY_SPLIT_SEMANTIC_UNIT_RE.search(raw_entity_label):
        return [row]
    parts = controlled_parts or entity_split_candidates(raw_entity_label)
    if not parts:
        return [row]

    split_rows: list[dict] = []
    normalized_targets: set[tuple[str, str]] = set()
    for part in parts:
        split_row = entity_split_row(row, entity_kind, part, raw_entity_label)
        split_match = graphable_entity_match(split_row, domain, entity_kind, part, registry, node_vocabulary)
        if not split_match["matched"]:
            return [row]
        target = (split_match["kind"], target_family_display_label(split_match["label"], split_match["kind"]))
        if target in normalized_targets:
            continue
        normalized_targets.add(target)
        split_rows.append(split_row)

    return split_rows if len(split_rows) > 1 else [row]


def rows_for_source(cfg: dict) -> list[dict]:
    rows = load_json_array(Path(cfg["path"]))
    if cfg.get("transform") == "clinical_endpoints":
        audit_path = normalize(cfg.get("audit_path", ""))
        audit_rows = load_json_array(Path(audit_path)) if audit_path else []
        return clinical_endpoint_rows(rows, audit_rows)
    return rows


def evidence_type_for(row: dict, default: str) -> str:
    if normalize(row.get("paper_assessment_route", "")) == "primary_evidence" and normalize(row.get("access_level", "")) != "secondary_summary":
        return "primary_evidence"
    values = {
        normalize(row.get("paper_assessment_route", "")),
        normalize(row.get("source_type", "")),
        normalize(row.get("source_family", "")),
        normalize(row.get("paper_type", "")),
        normalize(row.get("access_level", "")),
    }
    if values & SECONDARY_MARKERS or "secondary_summary" in values:
        return "secondary_literature"
    if values & PRIMARY_MARKERS:
        return "primary_evidence"
    return default


def entity_kind_for(row: dict, domain: str) -> str:
    domain_key = normalize(domain).casefold()
    if domain_key == "pharmacokinetics_exposure":
        return pk_graph_entity_kind(row)
    override = normalized_entity_kind(row.get("kg_entity_kind_override", ""))
    if override in GRAPH_ENTITY_KINDS:
        return override
    for field in ("primary_graph_anchor_kind", "graph_candidate_type", "graph_entity_type", "entity_type"):
        kind = normalized_entity_kind(row.get(field, ""))
        if kind in GRAPH_ENTITY_KINDS:
            return kind
    if domain_key == "molecular_pathway_readout" and first_endpoint_value(row, ("specific_readout_or_marker",)):
        return "biomarker_readout"
    return DOMAIN_DEFAULT_ENTITY_KIND.get(domain_key, "condition_indication")


def entity_type_for_kind(entity_kind: str, domain: str) -> str:
    if entity_kind in ENTITY_TYPE_BY_KIND:
        return ENTITY_TYPE_BY_KIND[entity_kind]
    return f"{slug(domain, 'domain')}_entity"


def molecular_specific_anchor_label(row: dict, entity_kind: str) -> str:
    if normalize(entity_kind).casefold() not in MOLECULAR_EFFECT_ENTITY_KINDS:
        return ""
    category = first_endpoint_value(row, ("molecular_effect_label", "molecular_effect_category"))
    if normalize(entity_kind).casefold() == "pathway_process":
        candidate_fields = (
            "pathway_or_process",
            "pathway_or_readout",
            "specific_readout_or_marker",
            "readout_or_biomarker",
            "readout_or_measure",
            "readout",
            "metabolic_or_transport_pathway",
        )
    else:
        candidate_fields = (
            "specific_readout_or_marker",
            "readout_or_biomarker",
            "readout_or_measure",
            "readout",
            "pathway_or_readout",
            "pathway_or_process",
            "metabolic_or_transport_pathway",
        )
    candidates = [
        first_endpoint_value(row, (field,))
        for field in candidate_fields
    ]
    candidates = [value for value in candidates if value and not generic_molecular_effect_placeholder(value)]
    if normalize(entity_kind).casefold() == "biomarker_readout" and candidates:
        specific = first_endpoint_value(row, ("specific_readout_or_marker",))
        if specific and not generic_molecular_effect_placeholder(specific):
            generic_tokens = {
                "activation",
                "activity",
                "change",
                "density",
                "expression",
                "level",
                "levels",
                "marker",
                "mrna",
                "protein",
                "readout",
            }

            def anchor_tokens(value: str) -> set[str]:
                return {
                    token
                    for token in re.findall(r"[a-z0-9]+", normalize(value).casefold())
                    if len(token) > 1 and token not in generic_tokens
                }

            specific_tokens = anchor_tokens(specific)
            related = [
                value
                for value in candidates
                if value == specific or (specific_tokens and specific_tokens & anchor_tokens(value))
            ]
            if related:
                return max(related, key=lambda value: (len(normalize(value)), normalize(value)))
    for value in candidates:
        if not category or label_key(value) != label_key(category):
            return value
    return candidates[0] if candidates else ""


def entity_label_for(row: dict, domain: str, entity_kind: str) -> str:
    if normalize(domain).casefold() == "pharmacokinetics_exposure":
        return pk_graph_entity_label(row)
    if normalize(domain).casefold() == "molecular_pathway_readout":
        specific_label = molecular_specific_anchor_label(row, entity_kind)
        if specific_label:
            return specific_label
    if normalize(row.get("canonical_entity", "")):
        return first_normalized_value(row, ("graph_entity_label", "canonical_entity", "entity_label"))
    explicit_label = first_normalized_value(row, ("graph_entity_label", "entity_label"))
    if explicit_label:
        return explicit_label
    fields = ENTITY_LABEL_FIELDS_BY_KIND.get(entity_kind, ())
    label = first_normalized_value(row, fields)
    if label:
        return label
    return first_normalized_value(row, ("graph_entity_label", "entity_label", "entity", "target", "disorder"))


def relation_type_for(domain: str, entity_kind: str, evidence_type: str, row: dict | None = None) -> str:
    explicit = normalize((row or {}).get("kg_relation_type_override", ""))
    if explicit:
        return explicit
    if evidence_type == "secondary_literature":
        return "discusses_relationship"
    if entity_kind == "condition_indication":
        return "studied_for_condition"
    if entity_kind == "symptom_problem":
        return "studied_for_symptom"
    if entity_kind == "safety_adverse_event":
        return "reports_safety_signal"
    if entity_kind == "outcome_scale":
        return "reports_outcome_scale"
    if entity_kind in {"brain_region", "brain_network", "neural_circuit"} or domain == "brain_system":
        return "has_brain_system_effect"
    if entity_kind == "subjective_experience_construct" or domain == "subjective_experience":
        return "has_subjective_experience_effect"
    if entity_kind == "cognitive_behavioral_construct" or domain in {"cognitive_behavioral", "behavioral"}:
        return "has_cognitive_behavioral_effect"
    if domain in {"pharmacokinetics_exposure", "exposure"}:
        return pk_edge_relation_type(row or {})
    if entity_kind == "pharmacokinetic_parameter":
        return "exposure_characterized"
    if entity_kind == "intervention_component" or domain in {"intervention_context", "intervention"}:
        return "uses_intervention_component"
    if entity_kind == "public_health_measure" or domain in {"real_world_public_health", "public_health"}:
        return "has_public_health_evidence"
    if domain in {"molecular_target", "molecular_pathway_readout"}:
        if entity_kind == "target":
            return "has_mechanistic_target"
        if entity_kind == "pathway_process":
            return "has_mechanistic_pathway"
        if entity_kind == "biomarker_readout":
            return "has_biomarker_readout"
        if entity_kind == "system_family":
            return "has_mechanistic_system"
        if domain == "molecular_target":
            return "has_mechanistic_target"
        if domain == "molecular_pathway_readout":
            return "has_mechanistic_pathway"
        return "has_mechanistic_system"
    return "reports_outcome_scale"


def paper_row(row: dict, paper_id: str) -> dict:
    out = {
        "paper_id": paper_id,
        "doi": normalize_doi(row.get("study_doi", "")),
        "openalex_id": normalize(row.get("openalex_id", "")),
        "title": normalize(row.get("study_title", "")),
        "authors": normalize(row.get("authors", "")),
        "year": as_int_or_none(row.get("study_year", "")),
        "journal": normalize(row.get("study_journal", "")),
    }
    for field in PAPER_FIELDS:
        out[field] = normalize(row.get(field, ""))
    return out


def normalized_explicit_system(value: object) -> str:
    text = normalize(value)
    if not text:
        return ""
    key = ascii_fold(text).replace("_", " ").strip()
    return SYSTEM_NORMALIZATION.get(key, "")


def inferred_experimental_system(row: dict) -> str:
    explicit = normalized_explicit_system(row.get("system", ""))
    if explicit:
        return explicit

    text = ascii_fold(" ".join(normalize(row.get(field, "")) for field in EXPERIMENTAL_SYSTEM_TEXT_FIELDS))
    if not text:
        return ""
    if SYSTEM_IN_VITRO_RE.search(text):
        return "in_vitro"
    if SYSTEM_EX_VIVO_RE.search(text):
        return "ex_vivo"
    if SYSTEM_CLINICAL_RE.search(text):
        return "clinical"
    if SYSTEM_IN_VIVO_RE.search(text):
        return "in_vivo"
    return ""


def public_health_context(row: dict) -> str:
    return ascii_fold(" ".join(normalize(row.get(field, "")) for field in PUBLIC_HEALTH_CONTEXT_FIELDS))


def public_health_topic_context(row: dict) -> str:
    return ascii_fold(" ".join(normalize(row.get(field, "")) for field in PUBLIC_HEALTH_TOPIC_CONTEXT_FIELDS))


def public_health_rule_label(context: str, skip_labels: set[str] | None = None) -> str:
    if not normalize(context):
        return ""
    skip = skip_labels or set()
    for label, pattern in PUBLIC_HEALTH_TOPIC_RULES:
        if label in skip:
            continue
        if pattern.search(context):
            return label
    return ""


def real_world_use_context(row: dict) -> str:
    tags: list[str] = []
    explicit = normalize(row.get("real_world_use_context", ""))
    for part in re.split(r"\s*[;,|]\s*", explicit):
        canonical = PUBLIC_HEALTH_USE_CONTEXT_LABEL_BY_KEY.get(label_key(part))
        if canonical and canonical not in tags:
            tags.append(canonical)

    context = ascii_fold(" ".join(normalize(row.get(field, "")) for field in PUBLIC_HEALTH_USE_CONTEXT_FIELDS))
    for label, pattern in PUBLIC_HEALTH_USE_CONTEXT_RULES:
        if pattern.search(context) and label not in tags:
            tags.append(label)

    legacy_keys = {
        label_key(row.get("public_health_graph_label", "")),
        label_key(row.get("public_health_topic_category", "")),
    }
    for legacy_key in legacy_keys:
        label = PUBLIC_HEALTH_LEGACY_USE_CONTEXT_BY_KEY.get(legacy_key)
        if not label or label in tags:
            continue
        if label == "Self-treatment" and "Clinical care" in tags:
            continue
        tags.append(label)
    return "; ".join(tags)


def normalized_public_health_data_source_type(row: dict) -> str:
    explicit = normalize(row.get("data_source_type", "")).casefold()
    if explicit in PUBLIC_HEALTH_DATA_SOURCE_TYPES - {"not_reported", "other_or_unclear"}:
        return explicit

    context = public_health_context(row)
    if re.search(
        r"\b(wastewater|sewage|wbe\b|population[- ]normal(?:ised|ized)|mass load|daily loads?|pndl|pnl)\b",
        context,
        re.IGNORECASE,
    ):
        return "wastewater"
    if re.search(
        r"\b(drug checking|amnesty bins?|seized samples?|portable gc[- ]?ms|unexpected drug|"
        r"adulterat\w*|substitution|pill testing)\b",
        context,
        re.IGNORECASE,
    ):
        return "drug_checking"
    if re.search(
        r"\b(poison[- ]?cent(?:er|re)s?|poison control|toxicology|toxicosurveillance|intoxication|"
        r"fatal poisoning|overdose|emergency department|hair analysis|urine analysis|blood analysis|"
        r"serum concentration|drug concentration in hair|faers|pharmacovigilance)\b",
        context,
        re.IGNORECASE,
    ):
        return "poison_center_toxicology"
    if re.search(
        r"\b(survey|questionnaire|respondents?|online panel|global drug survey|gds\b|nsduh|"
        r"national survey|venue intercept|web[- ]based survey)\b",
        context,
        re.IGNORECASE,
    ):
        return "survey"
    if re.search(
        r"\b(qualitative|interview|ethnograph\w*|focus group|lived experience|narrative|self[- ]experiments?)\b",
        context,
        re.IGNORECASE,
    ):
        return "qualitative_interview"
    if re.search(
        r"\b(registry|administrative|medical records?|electronic health|claims data|hospital records?|"
        r"rems\b|crime records?|mortality records?|healthcare database)\b",
        context,
        re.IGNORECASE,
    ):
        return "administrative_registry"
    if re.search(
        r"\b(cohort|case[- ]control|longitudinal|follow[- ]up|retrospective|prospective|observational)\b",
        context,
        re.IGNORECASE,
    ):
        return "observational_cohort"
    return "other_or_unclear"


def public_health_graph_label(row: dict) -> str:
    explicit_labels = [
        first_endpoint_value(row, (field,))
        for field in (
            "public_health_graph_label",
            "public_health_topic_category",
            "graph_entity_label",
            "entity_label",
            "entity",
        )
    ]
    explicit_keys = [label_key(label) for label in explicit_labels if label]
    for explicit_key in explicit_keys:
        canonical_explicit = PUBLIC_HEALTH_TOPIC_LABEL_BY_KEY.get(explicit_key)
        if canonical_explicit and canonical_explicit not in {"Other real-world outcome", "Other real-world topics"}:
            return canonical_explicit

    measure_context = ascii_fold(
        " ".join(normalize(row.get(field, "")) for field in PUBLIC_HEALTH_TOPIC_MEASURE_FIELDS)
    )
    measure_label = public_health_rule_label(measure_context)
    if measure_label:
        return measure_label

    context = public_health_topic_context(row)
    rule_label = public_health_rule_label(context)
    if rule_label:
        return rule_label

    data_source_type = normalized_public_health_data_source_type(row)
    if data_source_type == "poison_center_toxicology":
        return "Acute harms & healthcare use"
    if data_source_type == "wastewater":
        return "Population use & trends"
    if data_source_type == "drug_checking":
        return "Drug composition & adulteration"

    raw_topic_key = label_key(row.get("public_health_topic_category", ""))
    legacy_explicit_key = explicit_keys[0] if explicit_keys else ""
    return (
        PUBLIC_HEALTH_RAW_TOPIC_FALLBACKS.get(raw_topic_key)
        or PUBLIC_HEALTH_LEGACY_TOPIC_FALLBACKS.get(legacy_explicit_key)
        or "Other real-world topics"
    )


def withdrawal_condition_label(row: dict) -> str:
    measure_context = ascii_fold(" ".join(normalize(row.get(field, "")) for field in COGNITIVE_BEHAVIORAL_MEASURE_FIELDS))
    context = ascii_fold(" ".join(normalize(row.get(field, "")) for field in WITHDRAWAL_CONDITION_CONTEXT_FIELDS))
    if not WITHDRAWAL_ENDPOINT_RE.search(context):
        return ""
    if GENERIC_LOCOMOTOR_CONTEXT_RE.search(measure_context) and not WITHDRAWAL_ENDPOINT_RE.search(measure_context):
        return ""
    if POLYSUBSTANCE_WITHDRAWAL_CONTEXT_RE.search(context):
        return "Substance use disorder"
    if COCAINE_WITHDRAWAL_CONTEXT_RE.search(context):
        return "Cocaine use disorder"
    if ALCOHOL_WITHDRAWAL_CONTEXT_RE.search(context):
        return "Alcohol use disorder"
    if OPIOID_WITHDRAWAL_CONTEXT_RE.search(context):
        return "Opioid use disorder"
    if NICOTINE_WITHDRAWAL_CONTEXT_RE.search(context):
        return "Nicotine dependence"
    if METHAMPHETAMINE_WITHDRAWAL_CONTEXT_RE.search(context):
        return "Methamphetamine use disorder"
    if GENERIC_SUBSTANCE_WITHDRAWAL_CONTEXT_RE.search(context):
        return "Substance use disorder"
    return ""


def subjective_time_distortion_from_cognitive_row(row: dict) -> bool:
    label_context = ascii_fold(" ".join(normalize(row.get(field, "")) for field in COGNITIVE_BEHAVIORAL_LABEL_FIELDS))
    measure_context = ascii_fold(" ".join(normalize(row.get(field, "")) for field in COGNITIVE_BEHAVIORAL_MEASURE_FIELDS))
    full_context = ascii_fold(
        " ".join(
            normalize(row.get(field, ""))
            for field in (
                *COGNITIVE_BEHAVIORAL_LABEL_FIELDS,
                *COGNITIVE_BEHAVIORAL_MEASURE_FIELDS,
                "finding_summary",
                "support",
            )
        )
    )
    if not SUBJECTIVE_TIME_DISTORTION_RE.search(full_context):
        return False
    if OBJECTIVE_TIME_TASK_RE.search(measure_context):
        return False
    return bool(
        SELF_REPORT_TIME_CONTEXT_RE.search(measure_context)
        or SELF_REPORT_TIME_CONTEXT_RE.search(full_context)
        or "sense of time" in label_context
    )


def canonical_cognitive_behavioral_label(value: object) -> tuple[str, bool]:
    label = normalize(value)
    if not label:
        return "", False
    key = label_key(label)
    if key in COGNITIVE_BEHAVIORAL_LABEL_FALLBACKS:
        return COGNITIVE_BEHAVIORAL_LABEL_FALLBACKS[key], True
    if key in COGNITIVE_BEHAVIORAL_RULE_LABEL_BY_KEY:
        return COGNITIVE_BEHAVIORAL_RULE_LABEL_BY_KEY[key], True
    return label, False


def cognitive_behavioral_rule_label(
    row: dict,
    fields: Iterable[str],
    allowed_label_keys: set[str] | None = None,
) -> str:
    context = ascii_fold(" ".join(normalize(row.get(field, "")) for field in fields))
    if not context:
        return ""
    for label, pattern in COGNITIVE_BEHAVIORAL_RULES:
        if allowed_label_keys is not None and label_key(label) not in allowed_label_keys:
            continue
        if pattern.search(context):
            return label
    return ""


def cognitive_behavioral_graph_label(row: dict) -> str:
    explicit_label = first_endpoint_value(row, ("cognitive_behavioral_graph_label", "graph_construct_label"))
    canonical_explicit, explicit_is_known = canonical_cognitive_behavioral_label(explicit_label)
    explicit_key = label_key(canonical_explicit)
    allowed_refinements = COGNITIVE_BEHAVIORAL_ALLOWED_REFINEMENTS.get(explicit_key)

    measure_label = cognitive_behavioral_rule_label(row, COGNITIVE_BEHAVIORAL_MEASURE_FIELDS, allowed_refinements)
    if canonical_explicit and measure_label and not explicit_is_known:
        return measure_label
    if measure_label and allowed_refinements is not None and label_key(measure_label) != explicit_key:
        return measure_label
    if canonical_explicit and explicit_is_known and explicit_key not in COGNITIVE_BEHAVIORAL_BROAD_LABEL_KEYS:
        return canonical_explicit
    if canonical_explicit and explicit_is_known and allowed_refinements is not None:
        context_label = cognitive_behavioral_rule_label(row, COGNITIVE_BEHAVIORAL_CONTEXT_FIELDS, allowed_refinements)
        return context_label or canonical_explicit

    explicit_label = first_normalized_value(row, COGNITIVE_BEHAVIORAL_LABEL_FIELDS)
    canonical_label, label_is_known = canonical_cognitive_behavioral_label(explicit_label)
    explicit_key = label_key(canonical_label)
    allowed_refinements = COGNITIVE_BEHAVIORAL_ALLOWED_REFINEMENTS.get(explicit_key)
    measure_label = cognitive_behavioral_rule_label(row, COGNITIVE_BEHAVIORAL_MEASURE_FIELDS, allowed_refinements)
    measure_context = ascii_fold(" ".join(normalize(row.get(field, "")) for field in COGNITIVE_BEHAVIORAL_MEASURE_FIELDS))
    if measure_context and GENERIC_LOCOMOTOR_CONTEXT_RE.search(measure_context):
        return first_normalized_value(row, COGNITIVE_BEHAVIORAL_MEASURE_FIELDS) or canonical_label
    if measure_label and not label_is_known:
        return measure_label
    if measure_label and allowed_refinements is not None and label_key(measure_label) != explicit_key:
        return measure_label
    if canonical_label and label_is_known and allowed_refinements is not None:
        context_label = cognitive_behavioral_rule_label(row, COGNITIVE_BEHAVIORAL_CONTEXT_FIELDS, allowed_refinements)
        return context_label or canonical_label

    label_context_label = cognitive_behavioral_rule_label(row, COGNITIVE_BEHAVIORAL_LABEL_FIELDS)
    if label_context_label:
        return label_context_label
    if canonical_label and label_is_known:
        return canonical_label

    context_label = cognitive_behavioral_rule_label(row, COGNITIVE_BEHAVIORAL_CONTEXT_FIELDS)
    if context_label:
        return context_label
    return canonical_label


def canonical_subjective_experience_label(value: object) -> tuple[str, bool]:
    label = normalize(value)
    if not label:
        return "", False
    key = label_key(label)
    if key in SUBJECTIVE_EXPERIENCE_LABEL_FALLBACKS:
        return SUBJECTIVE_EXPERIENCE_LABEL_FALLBACKS[key], True
    if key in SUBJECTIVE_EXPERIENCE_RULE_LABEL_BY_KEY:
        return SUBJECTIVE_EXPERIENCE_RULE_LABEL_BY_KEY[key], True
    return label, False


def subjective_experience_rule_label(row: dict, fields: Iterable[str]) -> str:
    context = ascii_fold(" ".join(normalize(row.get(field, "")) for field in fields))
    if not context:
        return ""
    for label, pattern in SUBJECTIVE_EXPERIENCE_RULES:
        if pattern.search(context):
            return label
    return ""


def subjective_experience_graph_label(row: dict) -> str:
    explicit_label = first_normalized_value(row, SUBJECTIVE_EXPERIENCE_LABEL_FIELDS)
    canonical_label, label_is_known = canonical_subjective_experience_label(explicit_label)
    if label_is_known:
        return canonical_label

    label_match = subjective_experience_rule_label(row, SUBJECTIVE_EXPERIENCE_LABEL_FIELDS)
    if label_match:
        return label_match

    context_match = subjective_experience_rule_label(row, SUBJECTIVE_EXPERIENCE_CONTEXT_FIELDS)
    if context_match:
        return context_match
    return canonical_label


def molecular_effect_label(row: dict, entity_kind: str, entity_label: str) -> str:
    if normalize(entity_kind).casefold() not in MOLECULAR_EFFECT_ENTITY_KINDS:
        return ""
    exact_entity_label = canonical_molecular_effect_rule_label(entity_label)
    if exact_entity_label:
        return exact_entity_label
    explicit_label = first_endpoint_value(row, ("molecular_effect_label", "molecular_effect_category"))

    def effect_from_context(fields: tuple[str, ...]) -> str:
        context = molecular_effect_context(row, entity_label, fields)
        if not normalize(context):
            return ""
        for label, pattern in MOLECULAR_EFFECT_RULES:
            if pattern.search(context):
                return label
        return ""

    label_match = effect_from_context(MOLECULAR_EFFECT_LABEL_FIELDS)
    if label_match:
        return label_match
    full_match = effect_from_context(MOLECULAR_EFFECT_CONTEXT_FIELDS)
    if full_match:
        return full_match
    return canonical_molecular_effect_rule_label(explicit_label)


def molecular_effect_graph_label(row: dict, entity_kind: str, entity_label: str) -> str:
    if normalize(entity_kind).casefold() not in MOLECULAR_EFFECT_ENTITY_KINDS:
        return ""
    exact_entity_label = canonical_molecular_effect_rule_label(entity_label)
    if exact_entity_label:
        return exact_entity_label
    explicit_label = first_endpoint_value(row, ("molecular_effect_label", "molecular_effect_category"))
    exact_explicit_label = canonical_molecular_effect_rule_label(explicit_label)
    if exact_explicit_label:
        return exact_explicit_label

    def effect_from_context(fields: tuple[str, ...]) -> str:
        context = molecular_effect_context(row, entity_label, fields)
        if not normalize(context):
            return ""
        for label, pattern in MOLECULAR_EFFECT_RULES:
            if pattern.search(context):
                return label
        return ""

    label_match = effect_from_context(MOLECULAR_EFFECT_LABEL_FIELDS)
    if label_match:
        return label_match
    return effect_from_context(MOLECULAR_EFFECT_CONTEXT_FIELDS)


def graph_parent_mapping(
    row: dict,
    domain: str,
    entity_kind: str,
    entity_label: str,
    registry_item: dict | None,
    registry: dict[tuple[str, str], dict],
    node_vocabulary: dict[tuple[str, str], dict],
) -> tuple[str, str, str, dict | None]:
    parent_label = ""
    parent_kind = ""
    parent_item = None
    if normalize(domain).casefold() == "brain_system" or entity_kind in BRAIN_SYSTEM_ENTITY_KINDS:
        parent_label = normalize((registry_item or {}).get("parent", ""))
        parent_kind = normalized_entity_kind((registry_item or {}).get("parent_kind", "")) or entity_kind
        if parent_label:
            parent_label, parent_item = canonicalize_node_label(parent_kind, parent_label, node_vocabulary)
    elif entity_kind == "cognitive_behavioral_construct":
        parent_label = normalize((registry_item or {}).get("parent", ""))
        parent_kind = entity_kind
        if parent_label:
            parent_label, parent_item = canonicalize_node_label(parent_kind, parent_label, node_vocabulary)
    elif entity_kind == "intervention_component":
        parent_label = intervention_parent_label(row, entity_label)
        parent_kind = entity_kind
    elif entity_kind == "safety_adverse_event":
        parent_label = SAFETY_SPECIFIC_PARENT_LABELS.get(entity_label) or safety_category_for_text(entity_label) or safety_endpoint_label(row)
        parent_kind = entity_kind
    elif entity_kind in {"target", "system_family"}:
        parent_label = normalize((registry_item or {}).get("parent", ""))
        parent_kind = normalized_entity_kind((registry_item or {}).get("parent_kind", "")) or "system_family"
        if parent_label:
            parent_label, parent_item = canonicalize_registry_label("mechanistic_entity", parent_label, registry)
    elif entity_kind in MOLECULAR_EFFECT_ENTITY_KINDS:
        parent_label = molecular_effect_label(row, entity_kind, entity_label)
        parent_kind = "pathway_process"

    if not parent_label or label_key(parent_label) == label_key(entity_label):
        return "", "", "", None
    parent_type = entity_type_for_kind(parent_kind, domain)
    return parent_label, parent_kind, entity_id_for(parent_type, parent_label), parent_item


def subjective_experience_safety_label(row: dict) -> str:
    context = ascii_fold(" ".join(normalize(row.get(field, "")) for field in SUBJECTIVE_EXPERIENCE_SAFETY_CONTEXT_FIELDS))
    if SUBJECTIVE_EXPERIENCE_NONADVERSE_RE.search(context):
        return ""
    safety_label = safety_endpoint_label(row)
    if SUBJECTIVE_EXPERIENCE_SAFETY_RE.search(context):
        return safety_label
    if persistent_adverse_psychiatric_or_perceptual_symptoms(row):
        return safety_label or PERSISTENT_PSYCHIATRIC_OR_PERCEPTUAL_SYMPTOMS_LABEL
    return ""


PSYCHOSIS_FAMILY_ENTITY_RE = re.compile(
    r"\b(psychotomimetic|psychosis(?:[- ]like)?|psychotic(?:[- ]like)? symptoms?|psychosis risk)\b",
    re.IGNORECASE,
)
PSYCHOTOMIMETIC_STATEMENT_RE = re.compile(
    r"\b(psychotomimetic|psychosis[- ]like|psychotic[- ]like|schizophrenia[- ]like symptoms?|"
    r"model psychosis|psychosis model|model(?:s|ing|led)? (?:of )?(?:acute )?psychosis|"
    r"mimic(?:s|king|ked)? (?:the )?(?:symptoms? of )?(?:acute )?psychosis|"
    r"psychotic states? (?:as|that|which) (?:a )?model|bprs|panss)\b",
    re.IGNORECASE,
)

REVIEW_DESIGN_CATEGORY_BY_PAPER_TYPE = {
    "systematic_review": "systematic_review",
    "scoping_review": "scoping_review",
    "umbrella_review": "umbrella_review",
    "narrative_review": "narrative_or_literature_review",
    "literature_review": "narrative_or_literature_review",
}
REVIEW_SOURCE_TYPES = {
    "review",
    "systematic_review",
    "narrative_review",
    "scoping_review",
    "umbrella_review",
    "literature_review",
}
REVIEW_SAFETY_ENTITY_ROLES = {"safety_event", "safety_or_adverse_event"}


def is_review_row(row: dict) -> bool:
    source_type = normalize(row.get("source_type", "") or row.get("paper_type", "")).casefold()
    return source_type in REVIEW_SOURCE_TYPES


def review_paper_frame(row: dict) -> dict:
    value = row.get("paper_frame_json", "")
    if isinstance(value, dict):
        return value
    text = normalize(value)
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def review_design_category(row: dict, frame: dict | None = None) -> str:
    paper_type = label_key(row.get("paper_type", "")).replace(" ", "_")
    if paper_type in REVIEW_DESIGN_CATEGORY_BY_PAPER_TYPE:
        return REVIEW_DESIGN_CATEGORY_BY_PAPER_TYPE[paper_type]

    frame = frame or review_paper_frame(row)
    text = ascii_fold(frame.get("review_design", "")).casefold()
    if not text:
        return "other_or_unclear"
    if re.search(r"\bumbrella review\b|\breview of (?:systematic )?reviews\b|\boverview of reviews\b", text):
        return "umbrella_review"
    if re.search(r"\bscoping review\b|\bprisma[- ]scr\b", text):
        return "scoping_review"
    if re.search(r"\brapid (?:systematic )?review\b|\brapid evidence review\b", text):
        return "rapid_review"
    if re.search(r"\bsystematic review\b|\bsystematic literature review\b|\bprisma\b", text):
        return "systematic_review"
    if re.search(
        r"\bbibliometric\w*\b|\bscientometric\w*\b|\bcitation analysis\b|\bco[- ]citation\b|"
        r"\bco[- ]word\b|\bpublication landscape\b",
        text,
    ):
        return "bibliometric_or_landscape_review"
    if re.search(r"\bcritical review\b|\bcritical synthesis\b|\bcritical analysis\b|\bcritically evaluat\w*\b", text):
        return "critical_review"
    if re.search(r"\bhistorical review\b|\bhistorical analysis\b|\bhistorical overview\b", text):
        return "historical_review"
    if re.search(
        r"\bconceptual\w*\b|\btheoretical\w*\b|\bphilosophical\w*\b|\bframework\b|\bperspective\b|"
        r"\bcommentary\b|\bviewpoint\b|\bethical analysis\b|\bargument\w*\b",
        text,
    ):
        return "conceptual_or_theoretical_review"
    if re.search(
        r"\bnarrative\b|\bliterature review\b|\breview of (?:the )?literature\b|\bcomprehensive review\b|"
        r"\bselective review\b|\btraditional review\b|\bclinical review\b|\bpharmacological review\b|"
        r"\bevidence review\b|\breview article\b|\bliterature overview\b",
        text,
    ):
        return "narrative_or_literature_review"
    return "other_or_unclear"


REVIEW_COVERAGE_FOCUS_LABELS = {
    "paper_defining": "Main focus",
    "major_supporting": "Major supporting topic",
    "secondary_context": "Context only",
}
REVIEW_CONSTRUCT_NORMALIZATION_RULES = (
    (
        re.compile(
            r"^(?:extinction of fear|fear extinction|fear extinction learning|fear memory extinction|"
            r"aversive memory extinction|fear extinction circuitry)$",
            re.IGNORECASE,
        ),
        "Fear extinction",
    ),
    (
        re.compile(r"^(?:creative ideation|creative task performance)$", re.IGNORECASE),
        "Creativity",
    ),
)
REVIEW_OUTCOME_NORMALIZATION_RULES = (
    (
        re.compile(
            r"\b(?:rapid[- ](?:acting )?)?antidepressant(?:[- ]like)?\s+"
            r"(?:effect|effects|response|responses|efficacy|action|activity|properties|outcome|outcomes)\b",
            re.IGNORECASE,
        ),
        "Low mood & depressive symptoms",
        "symptom_problem",
    ),
    (
        re.compile(
            r"\b(?:clinical improvement|clinical response|treatment response|treatment outcomes?|positive outcome|"
            r"enduring therapeutic gains?|therapeutic response|therapeutic resolution|cross[- ]diagnostic clinical benefits?)\b",
            re.IGNORECASE,
        ),
        "Treatment response",
        "symptom_problem",
    ),
    (
        re.compile(r"\b(?:therapeutic efficacy|therapeutic outcomes?|therapeutic effects?|therapeutic benefits?)\b", re.IGNORECASE),
        "Treatment response",
        "symptom_problem",
    ),
    (
        re.compile(r"\b(?:analgesia|analgesic effects?|pain relief)\b", re.IGNORECASE),
        "Pain",
        "symptom_problem",
    ),
    (
        re.compile(r"\b(?:suicidal ideation|suicidality)\b", re.IGNORECASE),
        "Suicidality",
        "condition_indication",
    ),
    (
        re.compile(r"^anxiolytic effects?$", re.IGNORECASE),
        "Anxiety & panic",
        "symptom_problem",
    ),
    (
        re.compile(
            r"^(?:aggression|aggressive behavior|increased aggression|exacerbated aggression|"
            r"violent aggression|interpersonal violence|intimate partner violence|violence|"
            r"violence risk|violence prevention)$",
            re.IGNORECASE,
        ),
        "Aggression/violence",
        "symptom_problem",
    ),
)


def repeated_review_outcome_normalization(row: dict) -> tuple[str, str]:
    raw = first_endpoint_value(
        row,
        ("graph_entity_label", "raw_entity_label", "outcome_measure", "clinical_endpoint"),
    )
    if not raw:
        return "", ""
    for pattern, label, kind in REVIEW_OUTCOME_NORMALIZATION_RULES:
        if pattern.search(raw):
            return label, kind
    return "", ""


def narrow_review_construct_normalization(row: dict) -> str:
    raw = first_endpoint_value(
        row,
        ("graph_entity_label", "raw_entity_label", "construct_or_behavior", "outcome_measure"),
    )
    if not raw:
        return ""
    for pattern, label in REVIEW_CONSTRUCT_NORMALIZATION_RULES:
        if pattern.search(raw):
            return label
    return ""


def apply_review_context_metadata(row: dict) -> dict:
    if normalize(row.get("review_extraction_method", "")) != "paper_centered_one_pass_v2":
        return row
    frame = review_paper_frame(row)
    row["review_contribution_type"] = normalize(frame.get("review_contribution_type", ""))
    row["review_design_category"] = review_design_category(row, frame)
    construct_label = narrow_review_construct_normalization(row)
    if construct_label:
        row["domain"] = "cognitive_behavioral"
        row["domain_route"] = "cognitive_behavioral"
        row["dataset"] = "cognitive_behavioral"
        row["kg_entity_kind_override"] = "cognitive_behavioral_construct"
        row["graph_entity_label"] = construct_label
        row["cognitive_behavioral_graph_label"] = construct_label
        row["endpoint_label_source"] = "narrow_review_construct"
        row["normalization_boundary_reason"] = "narrow_review_construct_normalized"
        return row
    if (
        normalize(row.get("evidence_level", "")).casefold() == "preclinical"
        and label_key(row.get("graph_entity_label", ""))
        in {"antidepressant effect", "antidepressant effects", "antidepressant like effect", "antidepressant like effects"}
    ):
        row["domain"] = "cognitive_behavioral"
        row["domain_route"] = "cognitive_behavioral"
        row["dataset"] = "cognitive_behavioral"
        row["kg_entity_kind_override"] = "cognitive_behavioral_construct"
        row["graph_entity_label"] = "Stress-coping behavior"
        row["normalization_boundary_reason"] = "preclinical_antidepressant_effect_routed_to_stress_coping_behavior"
        return row
    outcome_label, outcome_kind = repeated_review_outcome_normalization(row)
    if outcome_label and normalize(row.get("evidence_level", "")).casefold() != "preclinical":
        row["domain"] = "clinical_outcome"
        row["domain_route"] = "clinical_outcome"
        row["dataset"] = "clinical_outcome"
        row["kg_entity_kind_override"] = outcome_kind
        row["graph_entity_label"] = outcome_label
        row["clinical_endpoint"] = outcome_label
        row["endpoint_label_source"] = (
            "clinical_condition_endpoint" if outcome_kind == "condition_indication" else "clinical_symptom_endpoint"
        )
        row["normalization_boundary_reason"] = "repeated_review_outcome_family_normalized"
    return row


def apply_review_safety_role_boundary(row: dict) -> dict:
    if not is_review_row(row):
        return row
    entity_role = normalize(row.get("entity_role", "")).casefold()
    if entity_role not in REVIEW_SAFETY_ENTITY_ROLES:
        return row

    out = dict(row)
    raw_safety_label = first_endpoint_value(
        out,
        (
            "safety_event_or_measure",
            "safety_event_or_risk",
            "graph_entity_label",
            "raw_entity_label",
            "entity_label",
        ),
    )
    if raw_safety_label:
        out["safety_event_or_measure"] = raw_safety_label
    parent_label = safety_endpoint_label(out)
    specific_label = safety_specific_endpoint_label(out, parent_label) if parent_label else ""
    unresolved_legacy_label = is_legacy_neuropsychiatric_label(raw_safety_label) and not (
        specific_label or parent_label
    )
    out["domain"] = "safety_tolerability"
    out["domain_route"] = "safety_tolerability"
    out["dataset"] = "safety_tolerability"
    out["kg_entity_kind_override"] = "safety_adverse_event"
    out["graph_entity_label"] = (
        specific_label
        or parent_label
        or ("Adverse events" if unresolved_legacy_label else raw_safety_label)
    )
    out["endpoint_label_source"] = "review_explicit_safety_role"
    out["normalization_boundary_reason"] = "explicit_review_safety_role_routed_to_safety"
    return out


META_ANALYSIS_POPULATION_ENTITY_RE = re.compile(
    r"\b(adults?|patients?|participants?|people|persons?|individuals?|subjects?|volunteers?|"
    r"population|men|women|children|adolescents?|surgical patients?|cancer patients?)\b",
    re.IGNORECASE,
)
META_ANALYSIS_OUTCOME_ENTITY_RE = re.compile(
    r"\b(symptoms?|scores?|response|remission|incidence|relief|efficacy|effectiveness|"
    r"allodynia|hyperalgesia|distress|suicid\w*)\b",
    re.IGNORECASE,
)


def meta_analysis_fallback_endpoint_label(row: dict) -> str:
    endpoint_row = dict(row)
    endpoint_row["graph_entity_label"] = ""
    endpoint_row["raw_entity_label"] = ""
    endpoint_row["entity_label"] = ""
    endpoint_row["clinical_endpoint"] = first_endpoint_value(
        row,
        ("primary_outcome", "outcome_measure", "clinical_endpoint"),
    )
    return symptom_endpoint_label(endpoint_row)


def apply_meta_analysis_context_metadata(row: dict) -> dict:
    source_type = normalize(row.get("source_type", "") or row.get("paper_type", "")).casefold()
    if source_type not in {"meta_analysis", "network_meta_analysis"}:
        return row
    if normalize(row.get("domain", "") or row.get("domain_route", "")) != "clinical_outcome":
        return row

    raw_entity = first_endpoint_value(row, ("graph_entity_label", "raw_entity_label", "entity_label"))
    entity_kind = normalized_entity_kind(row.get("kg_entity_kind_override", ""))
    entity_source = normalize(row.get("normalization_entity_source", "")).casefold()
    population_selected = "population" in entity_source or bool(META_ANALYSIS_POPULATION_ENTITY_RE.search(raw_entity))
    outcome_selected = entity_kind == "symptom_problem" or bool(META_ANALYSIS_OUTCOME_ENTITY_RE.search(raw_entity))
    if not (population_selected or outcome_selected):
        return row
    if population_selected and entity_kind == "condition_indication":
        # Let registry matching recover a single condition from wording such as
        # "patients with depression". The outcome is only a fallback when that
        # condition match fails, handled in graphable_entity_match.
        return row

    endpoint_label = meta_analysis_fallback_endpoint_label(row)
    if not endpoint_label:
        return row

    row["kg_entity_kind_override"] = (
        "condition_indication" if endpoint_label in SYMPTOM_ENDPOINTS_AS_CONDITIONS else "symptom_problem"
    )
    row["graph_entity_label"] = endpoint_label
    row["clinical_endpoint"] = endpoint_label
    row["endpoint_label_source"] = (
        "clinical_condition_endpoint"
        if endpoint_label in SYMPTOM_ENDPOINTS_AS_CONDITIONS
        else "clinical_symptom_endpoint"
    )
    row["normalization_boundary_reason"] = "meta_analysis_population_or_outcome_resolved_to_endpoint"
    return row


def apply_psychosis_family_boundary(row: dict, domain: str) -> tuple[dict, str]:
    """Separate transient psychotomimetic effects from actual psychosis risk."""

    if (
        is_review_row(row)
        and normalize(row.get("entity_role", "")).casefold() in REVIEW_SAFETY_ENTITY_ROLES
        and normalize(domain).casefold() == "safety_tolerability"
    ):
        return row, domain

    anchor = " ".join(
        normalize(row.get(field, ""))
        for field in (
            "graph_entity_label",
            "raw_entity_label",
            "entity_label",
            "safety_event_or_measure",
            "subjective_construct",
            "graph_entity_original",
        )
    )
    if not PSYCHOSIS_FAMILY_ENTITY_RE.search(anchor):
        return row, domain

    statement = " ".join(
        normalize(row.get(field, ""))
        for field in ("finding_summary", "support", "supporting_quote", "effect_or_statistic")
    )
    if PSYCHOTOMIMETIC_STATEMENT_RE.search(statement):
        domain = "cognitive_behavioral"
        row["domain"] = domain
        row["domain_route"] = domain
        row["dataset"] = domain
        row["kg_entity_kind_override"] = "cognitive_behavioral_construct"
        row["cognitive_behavioral_graph_label"] = "Psychotomimetic effects"
        row["graph_entity_label"] = "Psychotomimetic effects"
        row["endpoint_label_source"] = "psychotomimetic_effect_boundary"
        row["normalization_boundary_reason"] = "transient_psychotomimetic_effect_routed_to_cognition"
        return row, domain

    domain = "safety_tolerability"
    row["domain"] = domain
    row["domain_route"] = domain
    row["dataset"] = domain
    row["kg_entity_kind_override"] = "safety_adverse_event"
    row["safety_event_or_measure"] = "Psychosis risk"
    row["graph_entity_label"] = "Psychosis risk"
    row["endpoint_label_source"] = "psychosis_risk_boundary"
    row["normalization_boundary_reason"] = "induced_or_exacerbated_psychosis_routed_to_safety"
    return row, domain


def entity_row(
    entity_id: str,
    entity_type: str,
    domain: str,
    label: str,
    kind: str,
    registry_item: dict | None,
    *,
    parent_label: str = "",
    parent_kind: str = "",
    parent_entity_id: str = "",
) -> dict:
    registry_item = registry_item or {}
    aliases: list[str] = []
    seen_aliases: set[str] = {label_key(label)}
    for value in registry_item.get("aliases", []):
        alias = normalize(value)
        key = label_key(alias)
        if not alias or not key or key in seen_aliases:
            continue
        seen_aliases.add(key)
        aliases.append(alias)
    return {
        "entity_id": entity_id,
        "entity_type": entity_type,
        "domain": domain,
        "entity_kind": kind,
        "label": label,
        "graph_parent_label": normalize(parent_label),
        "graph_parent_kind": normalize(parent_kind),
        "graph_parent_entity_id": normalize(parent_entity_id),
        "registry_status": normalize(registry_item.get("status", "")),
        "aliases_json": json_dumps(aliases),
        "ids_json": json_dumps(registry_item.get("ids", {})),
    }


def normalize_claim_metadata(row: dict, domain: str) -> dict:
    out = dict(row)
    out = apply_review_context_metadata(out)
    out = apply_meta_analysis_context_metadata(out)
    out = apply_review_safety_role_boundary(out)
    coverage_focus = normalize(out.get("coverage_focus", ""))
    if coverage_focus and not normalize(out.get("coverage_focus_normalized", "")):
        out["coverage_focus_normalized"] = REVIEW_COVERAGE_FOCUS_LABELS.get(coverage_focus, "")
    domain = normalize(out.get("domain", "")) or normalize(out.get("domain_route", "")) or domain
    apply_graph_subject(out)
    out["result_direction_normalized"] = normalized_result_direction(out.get("result_direction", ""))
    out["evidence_design"] = evidence_design_for(out)
    out, domain = apply_psychosis_family_boundary(out, domain)
    if domain == "molecular_pathway_readout":
        explicit_category = label_key(first_endpoint_value(out, ("molecular_effect_label", "molecular_effect_category")))
        boundary_context = ascii_fold(
            " ".join(
                normalize(out.get(field, ""))
                for field in (
                    "molecular_effect_category",
                    "specific_readout_or_marker",
                    "pathway_or_readout",
                    "model_or_system",
                    "tissue_or_cell_type",
                    "finding_summary",
                    "support",
                )
            )
        )
        neurotoxicity_category = explicit_category in {"neurotoxicity", "neuroaxonal injury"}
        cardiac_context = re.search(
            r"\b(cardiac|cardiomyocyte|ventricular|repolarization|apd\d*|qt|qtc|arrhythm|herg|kcnh2)\b",
            boundary_context,
            flags=re.IGNORECASE,
        )
        electrophysiology_context = explicit_category in {"electrophysiology", "ion channel activity"} or re.search(
            r"\b(electrophysiolog\w*|patch clamp|action potential|ion channel|herg|kcnh2)\b",
            boundary_context,
            flags=re.IGNORECASE,
        )
        cardiac_electrophysiology = bool(cardiac_context and electrophysiology_context)
        physiological_safety = re.search(
            r"\b(body temperature|core temperature|hypertherm\w*|hypotherm\w*|thermoregul\w*|"
            r"mean arterial pressure|blood pressure|heart rate|tachycard\w*|bradycard\w*|"
            r"positive inotropic|force of contraction)\b",
            boundary_context,
            flags=re.IGNORECASE,
        )
        if neurotoxicity_category or cardiac_electrophysiology or physiological_safety:
            domain = "safety_tolerability"
            out["domain"] = domain
            out["domain_route"] = domain
            out["dataset"] = domain
            out["kg_entity_kind_override"] = "safety_adverse_event"
            out["safety_event_or_measure"] = first_endpoint_value(
                out,
                ("specific_readout_or_marker", "pathway_or_readout", "graph_entity_label"),
            )
            out["graph_entity_label"] = safety_endpoint_label(out)
            out["endpoint_label_source"] = "molecular_safety_boundary"
            out["normalization_boundary_reason"] = (
                "cardiac_electrophysiology_routed_to_safety"
                if cardiac_electrophysiology
                else (
                    "molecular_physiology_routed_to_safety"
                    if physiological_safety
                    else "molecular_neurotoxicity_routed_to_safety"
                )
            )
    if domain == "molecular_target":
        explicit_kind = normalized_entity_kind(
            first_normalized_value(out, ("kg_entity_kind_override", "graph_candidate_type", "graph_entity_type", "entity_type"))
        )
        if explicit_kind in {"pathway_process", "biomarker_readout"}:
            domain = "molecular_pathway_readout"
            out["domain"] = domain
            out["domain_route"] = domain
            out["dataset"] = domain
            out["normalization_boundary_reason"] = "molecular_target_readout_routed_to_molecular_effects"
    if domain == "pharmacokinetics_exposure":
        out["domain"] = domain
        out = add_pk_relationship_fields(out)
        pd_target = pk_pharmacodynamic_target(out)
        if pd_target:
            domain = "molecular_target"
            out["domain"] = domain
            out["domain_route"] = domain
            out["dataset"] = domain
            out["target"] = pd_target
            out["primary_graph_anchor_kind"] = "target"
            out["kg_entity_kind_override"] = "target"
            out["graph_entity_label"] = pd_target
            out["normalization_boundary_reason"] = "pharmacodynamic_target_routed_from_pk"
    if domain == "real_world_public_health":
        out["domain"] = domain
        out["real_world_use_context"] = real_world_use_context(out)
        out["data_source_type"] = normalized_public_health_data_source_type(out)
        out["public_health_graph_label"] = public_health_graph_label(out)
        out["graph_entity_label"] = out["public_health_graph_label"]
    if domain == "cognitive_behavioral":
        out["domain"] = domain
        withdrawal_condition = withdrawal_condition_label(out)
        if withdrawal_condition:
            out["kg_entity_kind_override"] = "condition_indication"
            out["endpoint_label_source"] = "behavioral_withdrawal_condition_boundary"
            out["graph_entity_label"] = withdrawal_condition
        elif subjective_time_distortion_from_cognitive_row(out):
            out["domain"] = "subjective_experience"
            out["kg_entity_kind_override"] = "subjective_experience_construct"
            out["endpoint_label_source"] = "subjective_time_distortion_boundary"
            out["subjective_experience_graph_label"] = "Time distortion"
            out["graph_entity_label"] = "Time distortion"
        else:
            out["cognitive_behavioral_graph_label"] = cognitive_behavioral_graph_label(out)
            if out["cognitive_behavioral_graph_label"]:
                out["graph_entity_label"] = out["cognitive_behavioral_graph_label"]
                detail_label = CONTROLLED_BEHAVIORAL_DETAIL_LABELS.get(
                    label_key(out["cognitive_behavioral_graph_label"]),
                    "",
                )
                if not detail_label and GENERIC_LOCOMOTOR_CONTEXT_RE.search(
                    ascii_fold(out["cognitive_behavioral_graph_label"])
                ):
                    detail_label = "Locomotor activity"
                if detail_label:
                    out["cognitive_behavioral_graph_label"] = detail_label
                    out["graph_entity_label"] = detail_label
                    out["endpoint_label_source"] = "controlled_behavioral_detail"
    if domain == "subjective_experience":
        out["domain"] = domain
        safety_label = subjective_experience_safety_label(out)
        if safety_label:
            out["kg_entity_kind_override"] = "safety_adverse_event"
            out["endpoint_label_source"] = "subjective_experience_safety_boundary"
            out["graph_entity_label"] = safety_label
        else:
            out["subjective_experience_graph_label"] = subjective_experience_graph_label(out)
            if out["subjective_experience_graph_label"]:
                out["graph_entity_label"] = out["subjective_experience_graph_label"]
    if domain in EXPERIMENTAL_SYSTEM_METADATA_DOMAINS:
        out["assay_family_normalized"] = normalize_assay_family(
            out.get("assay_family_normalized", "") or out.get("assay_family", ""),
            out.get("assay_type", ""),
        )
    if domain in EXPERIMENTAL_SYSTEM_METADATA_DOMAINS:
        system = inferred_experimental_system(out)
        if system:
            out["system"] = system
    if domain in CLINICAL_METADATA_DOMAINS and not normalize(out.get("outcome_measure_normalized", "")):
        out["outcome_measure_normalized"] = normalize_outcome_measure(out.get("outcome_measure", ""))
    if domain in CLINICAL_METADATA_DOMAINS and not normalize(out.get("comparator_normalized", "")):
        out["comparator_normalized"] = normalize_clinical_comparator(out.get("comparator", ""))
    if domain in CLINICAL_METADATA_DOMAINS and not normalize(out.get("follow_up_window_normalized", "")):
        out["follow_up_window_normalized"] = normalize_clinical_followup_window(
            out.get("follow_up_duration", ""),
            out.get("assessment_timepoint", "") or out.get("timepoint", ""),
        )
    return out


def route_native_output(manifest_source_preset: str, graph_sources: dict[str, dict]) -> bool:
    source_names = set(graph_sources)
    return manifest_source_preset == "routed" or (
        bool(source_names)
        and source_names <= ROUTED_SOURCE_NAMES
        and "routed_extractions" in source_names
    )


def normalized_direction_for_row(row: dict) -> str:
    explicit = normalize(row.get("result_direction_normalized", ""))
    if explicit:
        return explicit
    raw = normalize(row.get("result_direction", "")).casefold().replace("-", " ").replace("_", " ")
    raw = re.sub(r"\s+", " ", raw).strip()
    aliases = {
        "positive association": "positive_association",
        "negative association": "negative_association",
        "no significant association": "no_association",
        "no association": "no_association",
        "no detected effect": "no_detected_effect",
        "no change": "no_change",
        "insufficient evidence": "insufficient_evidence",
        "descriptive only": "descriptive_only",
    }
    return aliases.get(raw, raw.replace(" ", "_"))


NONBLOCKING_PROVENANCE_WARNING_RE = re.compile(r"^nonverbatim_supporting_text:[^:|]+:\d+$")

NONTHERAPEUTIC_OBSERVATIONAL_DESIGN_RE = re.compile(
    r"\b(?:observational|cross[- ]sectional|cohort|case[- ]control|survey|retrospective|longitudinal)\b",
    re.IGNORECASE,
)
NONTHERAPEUTIC_EXPOSURE_STATUS_RE = re.compile(
    r"\b(?:lifetime|past[- ](?:year|month)|history\s+of|prior|previous|ever|current|recent|chronic|"
    r"illicit|recreational)\b.{0,100}\b(?:use|used|users?|abuse|misuse|exposure|experience|consumption)|"
    r"\b(?:lifetime|past[- ]year|current|recent|chronic|illicit|recreational)\s+"
    r"(?:psychedelic|hallucinogen|drug|substance|ketamine|lsd|mdma|psilocybin|ayahuasca|mescaline|ibogaine)\b|"
    r"\b(?:use|abuse|misuse|exposure|consumption)\s+history\b",
    re.IGNORECASE,
)
NONTHERAPEUTIC_EXPOSURE_GROUP_RE = re.compile(
    r"\b(?:non[- ]?(?:users?|abusers?|exposed)|never[- ]users?|"
    r"no\s+(?:lifetime|past[- ]year|history\s+of)|unexposed|"
    r"users?\s+vs\.?\s+non[- ]?users?|controls?|co[- ]twin)\b",
    re.IGNORECASE,
)
NONTHERAPEUTIC_ASSOCIATION_RE = re.compile(
    r"\b(?:associated|association|correlated|correlation|odds|risk|likelihood|prevalence|"
    r"rate(?:s)?\s+of|predicted|predictor|moderated|more likely|less likely|higher|lower|"
    r"difference(?:s)?\s+(?:in|between)|compared (?:with|to)|exhibited)\b",
    re.IGNORECASE,
)
NONTHERAPEUTIC_PLAIN_USE_RE = re.compile(
    r"\b(?:psychedelic|hallucinogen|lsd|mdma|psilocybin|dmt|ketamine|mescaline|ayahuasca|"
    r"ibogaine|salvia|salvinorin)\s+(?:drug\s+)?(?:use|users?)\b",
    re.IGNORECASE,
)
THERAPEUTIC_OBSERVATIONAL_INTENT_RE = re.compile(
    r"\b(?:treat(?:ment|ed|ing)|therap(?:y|eutic)|self[- ]?(?:treat|manage)|"
    r"manage(?:ment)?\s+(?:of|for)|prophyl(?:axis|actic)|abortive|healing intention|"
    r"quit(?:ting)?|cessation|recover(?:ed|y) using|used specifically (?:to|for))\b",
    re.IGNORECASE,
)
THERAPEUTIC_OBSERVATIONAL_TEMPORAL_RE = re.compile(
    r"\b(?:following|after|post[- ])(?:.{0,45}\b)?(?:psychedelic|hallucinogen|compound|substance|drug|"
    r"ketamine|lsd|mdma|psilocybin|ayahuasca|mescaline|ibogaine|use|experience|exposure|dose|session|"
    r"administration|infusion|treatment|therapy)\b|"
    r"\b(?:as a result of|attributed .{0,50} to) (?:.{0,30}\b)?(?:use|experience|exposure|dose|treatment)\b|"
    r"\b(?:pre[- ]?to[- ]?post|before and after|from baseline|compared (?:with|to) baseline)\b",
    re.IGNORECASE,
)
THERAPEUTIC_OBSERVATIONAL_OUTCOME_RE = re.compile(
    r"\b(?:improv(?:e|ed|ements?|ing)|benefit(?:ed|s|cial)?|relief|reduc(?:e|ed|tions?)|"
    r"decreas(?:e|ed|es)|remissions?|responses?|cessation|abstinence|effective(?:ness)?|better|"
    r"(?:cravings?|withdrawal symptoms?).{0,40}less severe|less severe.{0,40}(?:cravings?|withdrawal symptoms?)|"
    r"no (?:significant )?(?:change|difference|improvement)|unchanged)\b",
    re.IGNORECASE,
)
THERAPEUTIC_OBSERVATIONAL_REGIMEN_RE = re.compile(
    r"\b(?:\d+(?:\.\d+)?\s*(?:mg|mcg|ug|µg)(?:/kg)?|infusions?|administrations?|once|twice)\b",
    re.IGNORECASE,
)
THERAPEUTIC_OBSERVATIONAL_NONUSER_COMPARATOR_RE = re.compile(
    r"\b(?:non[- ]?(?:users?|abusers?|exposed)|never[- ]users?|"
    r"no\s+(?:lifetime|past[- ]year|history\s+of)|unexposed|drug[- ]na[i#]ve|healthy controls?|co[- ]twin)\b",
    re.IGNORECASE,
)
THERAPEUTIC_OBSERVATIONAL_REGIMEN_EXCLUSION_RE = re.compile(
    r"\b(?:lifetime|past[- ]year|recreational|illicit|abuse|misuse)\b",
    re.IGNORECASE,
)
NONTHERAPEUTIC_DISEASE_MODEL_ENTITY_KEYS = {
    "psychosis",
    "psychotic disorders",
    "schizophrenia",
}
NONTHERAPEUTIC_DISEASE_MODEL_RE = re.compile(
    r"\b(?:model psychosis|psychosis model|serotonergic model of schizophrenia|"
    r"experimental model.{0,80}(?:psychosis|psychotic|schizophren\w*)|"
    r"(?:model|models|modeling|modelling|modelled).{0,100}(?:psychosis|psychotic states?|schizophren\w*|"
    r"deficits? (?:found|observed) in schizophren\w*)|"
    r"mimic(?:s|ked|king)?.{0,80}(?:psychosis|psychotic|schizophren\w*)|"
    r"produce(?:s|d|ing)?.{0,80}(?:psychosis|psychotic|schizophrenia[- ]like)|"
    r"similar to (?:those )?(?:found|observed) in schizophren\w*|"
    r"inadequate model.{0,80}schizophren\w*)\b",
    re.IGNORECASE,
)
NONTHERAPEUTIC_RESEARCH_HISTORY_RE = re.compile(
    r"\b(?:is|are|was|were|has been|have been|had been) investigated (?:for|as)\b",
    re.IGNORECASE,
)
NONTHERAPEUTIC_HPPD_RE = re.compile(
    r"\b(?:hppd|hallucinogen persisting perception disorder|persisting perceptual|flashbacks?)\b",
    re.IGNORECASE,
)

SUBSTANCE_USE_DISORDER_SUFFIXES = (
    " use disorder",
    " dependence",
    " dependency",
    " addiction",
)
SUBSTANCE_USE_SUBJECT_FAMILY_KEYS = {
    "arketamine": "ketamine",
    "esketamine": "ketamine",
    "hallucinogens": "hallucinogen",
    "r ketamine": "ketamine",
    "racemic ketamine": "ketamine",
    "s ketamine": "ketamine",
    "stimulants": "stimulant",
}
SUBSTANCE_USE_LIABILITY_RE = re.compile(
    r"\b(?:can|may|could) lead to (?:the )?development of .{0,60}\b(?:addiction|dependence|use disorder)\b|"
    r"\bdevelop(?:ed|s|ing)? (?:a |an )?(?:severe |psychological )?[^.;]{0,45}\b(?:addiction|dependence|use disorder)\b|"
    r"\b(?:risk of|vulnerab\w* to) develop(?:ing)? .{0,45}\b(?:addiction|dependence|use disorder)\b|"
    r"\bcompulsive patterns? of .{0,35}\buse\b|"
    r"\b(?:exposure|use) .{0,100}\b(?:explain|underlie|contribute to) (?:the )?development of "
    r"(?:a |an )?[^.;]{0,35}\b(?:addiction|dependence|use disorders?)\b|"
    r"\bneuroadaptive .{0,100}\bdevelopment of (?:a |an )?[^.;]{0,35}\b(?:addiction|dependence|use disorders?)\b",
    re.IGNORECASE,
)
SUBSTANCE_USE_EXPOSURE_COHORT_RE = re.compile(
    r"\b(?:past|prior|previous|early[- ]life|lifetime|chronic|frequent|illicit|recreational)\b.{0,70}\b(?:use|users?|exposure)\b|"
    r"\b(?:users?|people who use|initially used|index drug|drug history|use history|exposure group)\b|"
    r"\b(?:participants?|patients?|people|individuals?|adolescents?|youths?) (?:who )?(?:used|using)\b",
    re.IGNORECASE,
)
SUBSTANCE_USE_THERAPEUTIC_TEMPORAL_RE = re.compile(
    r"\b(?:following|after|post[- ])(?:.{0,55}\b)?(?:dose|administration|infusion|treatment|therapy|"
    r"session|experience|ceremony|retreat|psychedelic|ayahuasca|ibogaine|ketamine|lsd|mdma|psilocybin)\b|"
    r"\b(?:attributed|ascribed) .{0,80}\b(?:reduc\w*|improv\w*|cessation|abstinence)\b .{0,60}\b(?:use|experience|treatment)\b",
    re.IGNORECASE,
)
SUBSTANCE_USE_NONINTERVENTION_EXPOSURE_RE = re.compile(
    r"\b(?:naturalistic|illicit|recreational) use prior to\b|"
    r"\b(?:index drug|use history|drug history|exposure group)\b",
    re.IGNORECASE,
)
SUBSTANCE_USE_POPULATION_ONLY_OUTCOME_RE = re.compile(
    r"\bfamily history of .{0,180}\b(?:predict\w*|response)\b|"
    r"\bnimodipine .{0,140}\bketamine(?:[- ]induced|.{0,20}\binduc\w*)\b|"
    r"\bpretreatment .{0,110}\b(?:ketamine|mdma|psychedelic|hallucinogen)[- ]induced\b|"
    r"\bpre[- ]exposed to .{0,70}\b(?:induced|conditioned place preference)\b|"
    r"\binduced .{0,90}\bpre[- ]exposed\b",
    re.IGNORECASE,
)
SUBSTANCE_USE_CONDITION_ALIASES = {
    "alcohol": ("alcohol", "alcoholism", "ethanol"),
    "cannabis": ("cannabis", "marijuana"),
    "cocaine": ("cocaine",),
    "hallucinogen": ("hallucinogen", "psychedelic"),
    "ketamine": ("ketamine",),
    "methamphetamine": ("methamphetamine",),
    "nicotine": ("nicotine", "tobacco"),
    "opioid": ("opioid", "opiate", "heroin"),
    "stimulant": ("stimulant", "amphetamine", "methamphetamine", "cocaine"),
    "substance": ("substance", "drug"),
    "tobacco": ("tobacco", "nicotine"),
}


def substance_use_disorder_stem(value: object) -> str:
    key = label_key(value)
    for suffix in SUBSTANCE_USE_DISORDER_SUFFIXES:
        if key.endswith(suffix):
            return key[: -len(suffix)].strip()
    return ""


def substance_use_subject_stem(value: object) -> str:
    key = label_key(value)
    return SUBSTANCE_USE_SUBJECT_FAMILY_KEYS.get(key, key)


def nontherapeutic_substance_use_condition_reason(row: dict) -> str:
    """Keep substance-use context and abuse liability out of Conditions.

    Conditions is a treatment/outcome view. A disorder may still be present in
    the paper as the sampled population or disease model, and a finding may
    instead describe the displayed compound's own abuse/dependence liability.
    Those records remain available through paper detail, Safety, and Real-world
    projections rather than becoming compound-to-indication claims.
    """

    if normalized_entity_kind(row.get("kg_entity_kind_override", "")) != "condition_indication":
        return ""

    entity_label = normalize(row.get("graph_entity_label", "") or row.get("entity_label", ""))
    condition_stem = substance_use_disorder_stem(entity_label)
    if not condition_stem:
        return ""

    subject_label = normalize(
        row.get("graph_overview_subject_label", "")
        or row.get("graph_subject_label", "")
        or row.get("compound", "")
    )
    if substance_use_subject_stem(subject_label) == condition_stem:
        return "same_compound_use_disorder_context"

    statement = " ".join(
        normalize(row.get(field, ""))
        for field in ("support", "supporting_quote", "finding_summary")
        if normalize(row.get(field, ""))
    )
    if SUBSTANCE_USE_LIABILITY_RE.search(statement):
        return "substance_use_liability_not_therapeutic_outcome"
    if NONTHERAPEUTIC_HPPD_RE.search(statement):
        return "safety_or_adverse_condition_context"

    design_text = " ".join(
        normalize(row.get(field, ""))
        for field in ("evidence_design", "study_design_category", "study_design")
        if normalize(row.get(field, ""))
    )
    population_text = " ".join(
        normalize(row.get(field, ""))
        for field in ("population", "population_or_subgroup", "model_or_system")
        if normalize(row.get(field, ""))
    )
    intent_text = " ".join(
        normalize(row.get(field, ""))
        for field in (
            "intervention_or_exposure",
            "compound_or_intervention",
            "dose",
            "dose_or_regimen",
            "support",
            "supporting_quote",
            "finding_summary",
        )
        if normalize(row.get(field, ""))
    )

    observational_or_case = bool(
        NONTHERAPEUTIC_OBSERVATIONAL_DESIGN_RE.search(design_text)
        or re.search(r"\bcase[- _]report\b", design_text, flags=re.IGNORECASE)
    )
    if (
        observational_or_case
        and SUBSTANCE_USE_EXPOSURE_COHORT_RE.search(statement)
        and NONTHERAPEUTIC_ASSOCIATION_RE.search(statement)
        and (
            not THERAPEUTIC_OBSERVATIONAL_INTENT_RE.search(intent_text)
            or SUBSTANCE_USE_NONINTERVENTION_EXPOSURE_RE.search(intent_text)
        )
        and not SUBSTANCE_USE_THERAPEUTIC_TEMPORAL_RE.search(intent_text)
    ):
        return "nontherapeutic_substance_use_exposure_association"

    condition_aliases = SUBSTANCE_USE_CONDITION_ALIASES.get(condition_stem, (condition_stem,))
    population_context_text = " ".join((statement, population_text))
    condition_is_population_context = any(
        re.search(rf"\b{re.escape(alias)}\w*\b", population_context_text, flags=re.IGNORECASE)
        for alias in condition_aliases
    )
    if (
        condition_is_population_context
        and SUBSTANCE_USE_POPULATION_ONLY_OUTCOME_RE.search(statement)
    ):
        return "substance_use_condition_as_population_or_model_context"
    return ""


def nontherapeutic_clinical_context_reason(row: dict) -> str:
    """Identify clinical-looking rows that do not report therapeutic outcomes."""

    substance_use_reason = nontherapeutic_substance_use_condition_reason(row)
    if substance_use_reason:
        return substance_use_reason
    if normalize(row.get("domain", "")).casefold() != "clinical_outcome":
        return ""
    entity_kind = normalized_entity_kind(row.get("kg_entity_kind_override", ""))
    if entity_kind not in {"condition_indication", "symptom_problem"}:
        return ""

    entity_label = normalize(row.get("graph_entity_label", "") or row.get("entity_label", ""))
    statement = " ".join(
        normalize(row.get(field, ""))
        for field in ("support", "supporting_quote", "finding_summary")
        if normalize(row.get(field, ""))
    )
    if (
        label_key(entity_label) in NONTHERAPEUTIC_DISEASE_MODEL_ENTITY_KEYS
        and NONTHERAPEUTIC_DISEASE_MODEL_RE.search(statement)
    ):
        return "nontherapeutic_disease_model_context"

    if (
        NONTHERAPEUTIC_RESEARCH_HISTORY_RE.search(statement)
        and not THERAPEUTIC_OBSERVATIONAL_OUTCOME_RE.search(statement)
    ):
        return "research_history_without_therapeutic_outcome"

    entity_key = label_key(entity_label)
    if entity_kind == "condition_indication" and (
        entity_key == "hallucinogen persisting perception disorder"
        or (
            entity_key == "schizophrenia"
            and NONTHERAPEUTIC_HPPD_RE.search(statement)
            and NONTHERAPEUTIC_OBSERVATIONAL_DESIGN_RE.search(
                " ".join(
                    normalize(row.get(field, ""))
                    for field in ("evidence_design", "study_design_category", "study_design")
                    if normalize(row.get(field, ""))
                )
            )
        )
    ):
        return "safety_or_adverse_condition_context"
    return ""


def nontherapeutic_observational_exposure_association(row: dict) -> bool:
    """Keep exposure-status epidemiology out of therapeutic outcome views.

    Naturalistic outcome evidence remains admissible when the finding has a
    baseline, treatment intent, a delivered regimen, or an explicit within-user
    outcome after use. Historical/current-user comparisons and abuse cohorts
    instead remain available through paper detail and real-world projections.
    """

    if normalize(row.get("domain", "")).casefold() != "clinical_outcome":
        return False
    entity_kind = normalized_entity_kind(row.get("kg_entity_kind_override", ""))
    if entity_kind not in {"condition_indication", "symptom_problem"}:
        return False

    design_text = " ".join(
        normalize(row.get(field, ""))
        for field in ("evidence_design", "study_design_category", "study_design")
        if normalize(row.get(field, ""))
    )
    association_text = " ".join(
        normalize(row.get(field, ""))
        for field in ("comparator", "study_design", "support", "supporting_quote", "finding_summary")
        if normalize(row.get(field, ""))
    )
    plain_use_association = bool(
        NONTHERAPEUTIC_EXPOSURE_GROUP_RE.search(association_text)
        and NONTHERAPEUTIC_ASSOCIATION_RE.search(association_text)
        and NONTHERAPEUTIC_PLAIN_USE_RE.search(association_text)
    )
    if not NONTHERAPEUTIC_OBSERVATIONAL_DESIGN_RE.search(design_text) and not plain_use_association:
        return False

    comparator_normalized = normalize(row.get("comparator_normalized", "")).casefold()
    if comparator_normalized in {"baseline", "standard care", "placebo"}:
        return False
    if normalize(row.get("session_context", "")).casefold() in {
        "clinical_administration",
        "therapy_assisted_session",
    }:
        return False

    therapeutic_text = " ".join(
        normalize(row.get(field, ""))
        for field in (
            "dose",
            "dose_or_regimen",
            "intervention_or_exposure",
            "compound_or_intervention",
            "comparator",
            "support",
            "supporting_quote",
            "finding_summary",
            "assessment_timepoint",
            "timepoint",
            "session_context",
        )
        if normalize(row.get(field, ""))
    )
    support_text = " ".join(
        normalize(row.get(field, ""))
        for field in ("support", "supporting_quote", "finding_summary")
        if normalize(row.get(field, ""))
    )
    comparator_text = normalize(row.get("comparator", ""))
    dose_text = normalize(row.get("dose", "") or row.get("dose_or_regimen", ""))

    if THERAPEUTIC_OBSERVATIONAL_INTENT_RE.search(therapeutic_text):
        return False
    if (
        THERAPEUTIC_OBSERVATIONAL_TEMPORAL_RE.search(therapeutic_text)
        and THERAPEUTIC_OBSERVATIONAL_OUTCOME_RE.search(support_text)
    ):
        return False
    if (
        THERAPEUTIC_OBSERVATIONAL_REGIMEN_RE.search(dose_text)
        and not THERAPEUTIC_OBSERVATIONAL_REGIMEN_EXCLUSION_RE.search(dose_text)
    ):
        return False
    if (
        THERAPEUTIC_OBSERVATIONAL_OUTCOME_RE.search(support_text)
        and not THERAPEUTIC_OBSERVATIONAL_NONUSER_COMPARATOR_RE.search(comparator_text)
    ):
        return False

    exposure_text = " ".join(
        normalize(row.get(field, ""))
        for field in (
            "dose",
            "dose_or_regimen",
            "intervention_or_exposure",
            "compound_or_intervention",
            "graph_subject_label",
            "comparator",
            "study_design",
            "support",
            "supporting_quote",
            "finding_summary",
            "assessment_timepoint",
            "population",
        )
        if normalize(row.get(field, ""))
    )
    return plain_use_association or (
        bool(NONTHERAPEUTIC_EXPOSURE_STATUS_RE.search(exposure_text))
        and bool(
            NONTHERAPEUTIC_EXPOSURE_GROUP_RE.search(association_text)
            or NONTHERAPEUTIC_ASSOCIATION_RE.search(association_text)
        )
    )


def has_only_nonblocking_provenance_warnings(row: dict) -> bool:
    warnings = [
        warning.strip()
        for warning in normalize(row.get("extraction_warnings", "")).split("|")
        if warning.strip()
    ]
    return bool(warnings) and all(NONBLOCKING_PROVENANCE_WARNING_RE.fullmatch(warning) for warning in warnings)


def provenance_only_warning_is_graph_admissible(row: dict) -> bool:
    if not has_only_nonblocking_provenance_warnings(row):
        return False
    source_type = normalize(row.get("source_type", "") or row.get("paper_type", "")).casefold()
    return source_type in {"meta_analysis", "network_meta_analysis"}


def graph_admission_decision(row: dict) -> tuple[str, str]:
    explicit = normalize(row.get("graph_admission_status", "")).casefold()
    if explicit == "paper_detail":
        return "paper_detail", normalize(row.get("graph_admission_reason", "")) or "source_marked_paper_detail"
    domain = normalize(row.get("domain", "") or row.get("domain_route", "")).casefold()
    entity_kind = normalized_entity_kind(row.get("kg_entity_kind_override", "") or row.get("entity_type", ""))
    entity_label = first_normalized_value(
        row,
        ("graph_entity_label", "canonical_entity", "entity_label", "public_health_graph_label"),
    )
    secondary_literature = (
        normalize(row.get("evidence_type", "")).casefold() == "secondary_literature"
        or normalize(row.get("source_family", "")).casefold() == "secondary_literature"
        or normalize(row.get("paper_assessment_route", "")).casefold() == "secondary_literature"
    )
    if domain == "general_topic_coverage" and secondary_literature:
        return "paper_detail", "review_coverage_metadata_detail_only"
    if (
        entity_kind == "public_health_measure"
        and label_key(entity_label) in {"other real world outcome", "other real world topics"}
    ):
        return "paper_detail", "unresolved_real_world_topic_detail_only"
    if (
        normalize(row.get("endpoint_label_source", "")) == "controlled_behavioral_detail"
        and normalize(row.get("entity_match_type", "")) != "controlled_behavioral_vocabulary"
    ):
        return "paper_detail", "controlled_behavioral_measure_detail_only"
    provenance_warning_admissible = provenance_only_warning_is_graph_admissible(row)
    if as_bool(row.get("needs_human_review", False)) and not provenance_warning_admissible:
        return "paper_detail", "extraction_marked_for_human_review"
    nontherapeutic_context_reason = nontherapeutic_clinical_context_reason(row)
    if nontherapeutic_context_reason:
        return "paper_detail", nontherapeutic_context_reason
    if nontherapeutic_observational_exposure_association(row):
        return "paper_detail", "nontherapeutic_observational_exposure_association"

    item_type = normalize(row.get("source_item_type", "")).casefold()
    location = normalize(row.get("evidence_location", "")).casefold()
    background_only = bool(re.search(r"\b(background|introduction|references?)\b", location)) and not bool(
        re.search(r"\b(result|discussion|conclusion|abstract|table|figure)\b", location)
    )
    if item_type == "primary_item" and background_only:
        return "paper_detail", "primary_claim_supported_only_by_background_location"

    if provenance_warning_admissible:
        return "main_graph", "semantically_complete_with_unverified_quote"
    return "main_graph", "semantically_complete"


def proposition_identifiers(row: dict, subject_label: str, entity_kind: str, entity_label: str) -> tuple[str, str]:
    specific_anchor = first_normalized_value(
        row,
        (
            "raw_entity_label",
            "graph_entity_original",
            "public_health_measure",
            "safety_event_or_measure",
            "specific_readout_or_marker",
            "brain_region",
            "brain_network",
            "neural_circuit",
            "construct_or_behavior",
            "subjective_construct",
            "context_component",
            "pk_or_exposure_parameter",
        ),
    )
    core = (
        normalize_doi(row.get("study_doi", "")),
        label_key(subject_label),
        label_key(row.get("graph_subject_label", "") or row.get("intervention_or_exposure", "")),
        normalized_entity_kind(entity_kind),
        label_key(entity_label),
        label_key(specific_anchor),
        label_key(row.get("population", "") or row.get("population_or_subgroup", "")),
        label_key(row.get("sample_size_total", "") or row.get("sample_size", "")),
        label_key(row.get("comparator_normalized", "") or row.get("comparator", "")),
        label_key(row.get("comparator", "")),
        label_key(row.get("clinical_endpoint", "")),
        label_key(row.get("outcome_measure", "")),
        label_key(row.get("assessment_timepoint", "") or row.get("follow_up_duration", "") or row.get("time_window", "")),
        label_key(row.get("dose", "") or row.get("dose_or_regimen", "")),
        label_key(row.get("route", "") or row.get("administration_route", "")),
        label_key(row.get("meta_analysis_result_role", "")),
        label_key(row.get("meta_analysis_subgroup_or_moderator", "")),
        label_key(row.get("meta_analysis_sensitivity_method", "")),
        label_key(row.get("network_treatment_a", "")),
        label_key(row.get("network_treatment_b", "")),
        label_key(row.get("network_reference_treatment", "")),
        label_key(row.get("meta_analysis_effect_metric", "")),
    )
    direction = normalized_direction_for_row(row)
    conflict_locator = label_key(row.get("evidence_locator", "") or row.get("evidence_location", ""))
    return (
        stable_id("proposition", *core, direction),
        stable_id("proposition-conflict", *core, conflict_locator),
    )


def direction_family(value: object) -> str:
    key = normalize(value).casefold()
    if key in {"positive", "positive_association", "increase", "supports"}:
        return "positive"
    if key in {"negative", "negative_association", "decrease", "does_not_support"}:
        return "negative"
    if key in {"no_association", "no_detected_effect", "no_change", "stable"}:
        return "null"
    return ""


def finalize_proposition_groups(findings: list[dict], evidence_edges: list[dict], id_field: str) -> dict:
    duplicate_counts = Counter(normalize(row.get("proposition_group_id", "")) for row in findings)
    conflict_directions: dict[str, set[str]] = {}
    for row in findings:
        conflict_id = normalize(row.get("proposition_conflict_group_id", ""))
        family = direction_family(row.get("result_direction_normalized", ""))
        if conflict_id and family:
            conflict_directions.setdefault(conflict_id, set()).add(family)
    conflicts = {key for key, families in conflict_directions.items() if len(families) > 1}

    edges_by_finding: dict[str, list[dict]] = {}
    for edge in evidence_edges:
        edges_by_finding.setdefault(normalize(edge.get(id_field, "")), []).append(edge)
    for row in findings:
        proposition_id = normalize(row.get("proposition_group_id", ""))
        row["proposition_duplicate_count"] = duplicate_counts.get(proposition_id, 1)
        conflict_id = normalize(row.get("proposition_conflict_group_id", ""))
        row["direction_consistency"] = "conflict" if conflict_id in conflicts else "consistent_or_not_applicable"
        if conflict_id in conflicts:
            row["graph_admission_status"] = "paper_detail"
            row["graph_admission_reason"] = "direction_conflict_within_same_structural_proposition"
        for edge in edges_by_finding.get(normalize(row.get(id_field, "")), []):
            shared_fields = (
                "proposition_duplicate_count",
                "direction_consistency",
                "graph_admission_status",
                "graph_admission_reason",
            )
            for field in shared_fields:
                edge[field] = row.get(field, "")
            if normalize(edge.get("projection_type", "")) != "use_context":
                edge["proposition_group_id"] = row.get("proposition_group_id", "")
                edge["proposition_conflict_group_id"] = row.get("proposition_conflict_group_id", "")

    return {
        "unique_proposition_groups": len({key for key in duplicate_counts if key}),
        "duplicate_finding_rows": sum(max(count - 1, 0) for key, count in duplicate_counts.items() if key),
        "direction_conflict_groups": len(conflicts),
    }


def finding_row(
    row: dict,
    source_name: str,
    domain: str,
    dataset: str,
    evidence_type: str,
    finding_id: str,
    paper_id: str,
    *,
    id_field: str,
) -> dict:
    row = normalize_claim_metadata(row, domain)
    domain = normalize(row.get("domain", "")) or normalize(row.get("domain_route", "")) or domain
    dataset = normalize(row.get("dataset", "")) or domain or dataset
    entity_kind = entity_kind_for(row, domain)
    entity_label = first_normalized_value(row, ("graph_entity_label", "canonical_entity")) or entity_label_for(
        row,
        domain,
        entity_kind,
    )
    out = {
        id_field: finding_id,
        "source_name": source_name,
        "domain": domain,
        "dataset": dataset,
        "evidence_type": evidence_type,
        "paper_id": paper_id,
        "study_doi": normalize_doi(row.get("study_doi", "")),
        "study_year": as_int_or_none(row.get("study_year", "")),
        "compound": compound_label_for(row),
        "entity_label": entity_label,
        "raw_row_json": json_dumps(row),
    }
    for field in CLAIM_FIELDS:
        value = row.get(field, "")
        if field in {"confidence", "affinity_value"}:
            out[field] = as_float_or_none(value)
        elif field == "needs_human_review":
            out[field] = as_bool(value)
        else:
            out[field] = normalize(value)
    return out


def evidence_edge_row(
    row: dict,
    source_name: str,
    domain: str,
    dataset: str,
    evidence_type: str,
    entity_kind: str,
    finding_id: str,
    evidence_id: str,
    paper_id: str,
    compound_id: str,
    entity_id: str,
    *,
    id_field: str,
) -> dict:
    entity_label = first_normalized_value(row, ("graph_entity_label", "canonical_entity")) or entity_label_for(
        row,
        domain,
        entity_kind,
    )
    relation_type = relation_type_for(domain, entity_kind, evidence_type, row)
    return {
        "evidence_id": evidence_id,
        id_field: finding_id,
        "projection_type": normalize(row.get("projection_type", "")) or "outcome",
        "source_name": source_name,
        "domain": domain,
        "dataset": dataset,
        "entity_kind": entity_kind,
        "evidence_type": evidence_type,
        "relation_type": relation_type,
        "compound_id": compound_id,
        "compound": compound_label_for(row),
        "graph_subject_kind": normalize(row.get("graph_overview_subject_kind", ""))
        or normalize(row.get("graph_subject_kind", ""))
        or "atomic_compound",
        "graph_overview_subject_label": normalize(row.get("graph_overview_subject_label", "")),
        "graph_overview_subject_kind": normalize(row.get("graph_overview_subject_kind", "")),
        "graph_overview_subject_reason": normalize(row.get("graph_overview_subject_reason", "")),
        "graph_overview_subjects_json": normalize(row.get("graph_overview_subjects_json", "")),
        "graph_use_context_projections_json": normalize(row.get("graph_use_context_projections_json", "")),
        "entity_id": entity_id,
        "entity_label": entity_label,
        "graph_parent_label": normalize(row.get("graph_parent_label", "")),
        "graph_parent_kind": normalize(row.get("graph_parent_kind", "")),
        "graph_parent_entity_id": normalize(row.get("graph_parent_entity_id", "")),
        "paper_id": paper_id,
        "study_doi": normalize_doi(row.get("study_doi", "")),
        "study_year": as_int_or_none(row.get("study_year", "")),
        "direction": normalize(row.get("result_direction", "")),
        "direction_normalized": normalize(row.get("result_direction_normalized", "")),
        "evidence_design": normalize(row.get("evidence_design", "")),
        "graph_admission_status": normalize(row.get("graph_admission_status", "")) or "main_graph",
        "graph_admission_reason": normalize(row.get("graph_admission_reason", "")),
        "proposition_group_id": normalize(row.get("proposition_group_id", "")),
        "proposition_conflict_group_id": normalize(row.get("proposition_conflict_group_id", "")),
        "support": normalize(row.get("support", "")),
        "confidence": as_float_or_none(row.get("confidence", "")),
        "evidence_level": normalize(row.get("evidence_level", "")),
        "source_type": normalize(row.get("source_type", "")),
        "source_family": normalize(row.get("source_family", "")),
        "paper_type": normalize(row.get("paper_type", "")),
        "access_level": normalize(row.get("access_level", "")),
        "sample_size_total": normalize(row.get("sample_size_total", "")),
        "outcome_measure": normalize(row.get("outcome_measure", "")),
        "outcome_measure_normalized": normalize(row.get("outcome_measure_normalized", "")),
        "effect_size": normalize(row.get("effect_size", "")),
        "p_value": normalize(row.get("p_value", "")),
        "confidence_interval": normalize(row.get("confidence_interval", "")),
        "evidence_location": normalize(row.get("evidence_location", "")),
        "evidence_locator": normalize(row.get("evidence_locator", "")),
        "supporting_quote": normalize(row.get("supporting_quote", "")),
    }


def audit_row(row: dict, source_name: str, domain: str, dataset: str) -> dict:
    entity_kind = entity_kind_for(row, domain)
    return {
        "source_name": source_name,
        "domain": domain,
        "dataset": dataset,
        "normalization_status": normalize(row.get("normalization_status", "")),
        "normalization_notes": normalize(row.get("normalization_notes", "")),
        "compound": compound_label_for(row),
        "canonical_compound": normalize(row.get("canonical_compound", "")),
        "compound_original": normalize(row.get("compound_original", "")),
        "compound_match_type": normalize(row.get("compound_match_type", "")),
        "entity_label": entity_label_for(row, domain, entity_kind),
        "canonical_entity": normalize(row.get("canonical_entity", "")),
        "graph_entity_original": normalize(row.get("graph_entity_original", "")),
        "entity_match_type": normalize(row.get("entity_match_type", "")),
        "kg_entity_kind_override": normalize(row.get("kg_entity_kind_override", "")),
        "entity_role": normalize(row.get("entity_role", "")),
        "graph_entity_type": normalize(row.get("graph_entity_type", "")),
        "graph_include_candidate": as_bool(row.get("graph_include_candidate", "")),
        "study_doi": normalize_doi(row.get("study_doi", "")),
        "study_title": normalize(row.get("study_title", "")),
        "raw_row_json": json_dumps(row),
    }


def dataframe(rows: list[dict], columns: Iterable[str] | None = None) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    if columns:
        for column in columns:
            if column not in df.columns:
                df[column] = None
        df = df[list(columns)]
    return df


def write_parquet(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, engine="pyarrow", index=False)


def build_tables(
    *,
    graph_sources: dict[str, dict] | None = None,
    source_preset: str = "routed",
    run_id: str = "",
    evidence_run_id: str = "",
    registry_path: Path = DEFAULT_REGISTRY_PATH,
    node_vocabulary_path: Path = DEFAULT_NODE_VOCABULARY_PATH,
    funding_assertions_path: Path | None = None,
    funding_attempts_path: Path | None = None,
    open_science_features_path: Path | None = None,
    open_science_assertions_path: Path | None = None,
    doi_alias_registry_path: Path | None = DEFAULT_DOI_ALIAS_REGISTRY,
    out_dir: Path = DEFAULT_OUT_DIR,
    write_duckdb: bool = True,
) -> dict:
    _REGISTRY_COMPOUND_TEXT_CACHE.clear()
    _REGISTRY_ENTITY_TEXT_CACHE.clear()
    if graph_sources is None:
        graph_sources = graph_sources_for_preset(source_preset, run_id=evidence_run_id or run_id)
        manifest_source_preset = source_preset
    else:
        manifest_source_preset = "custom"
    registry = registry_lookup(registry_path)
    node_vocabulary = node_vocabulary_lookup(node_vocabulary_path)
    route_native = route_native_output(manifest_source_preset, graph_sources)
    finding_table_name = "findings" if route_native else "claims"
    finding_id_field = "finding_id" if route_native else "claim_id"
    finding_id_prefix = "finding" if route_native else "claim"
    papers: dict[str, dict] = {}
    entities: dict[str, dict] = {}
    findings: list[dict] = []
    evidence_edges: list[dict] = []
    audits: list[dict] = []
    source_counts: dict[str, int] = {}

    for source_name, cfg in graph_sources.items():
        source_rows = rows_for_source(cfg)
        source_counts[source_name] = len(source_rows)
        source_domain = cfg["domain"]
        source_dataset = cfg["dataset"]
        default_evidence_type = cfg["default_evidence_type"]
        rows: list[dict] = []
        for source_row in source_rows:
            source_row_domain = normalize(source_row.get("domain", "")) or normalize(source_row.get("domain_route", "")) or source_domain
            normalized_source_row = normalize_claim_metadata(source_row, source_row_domain)
            normalized_source_domain = (
                normalize(normalized_source_row.get("domain", ""))
                or normalize(normalized_source_row.get("domain_route", ""))
                or source_row_domain
            )
            for condition_row in condition_expanded_rows(normalized_source_row, normalized_source_domain, registry):
                rows.extend(entity_expanded_rows(condition_row, normalized_source_domain, registry, node_vocabulary))

        for index, row in enumerate(rows):
            domain = normalize(row.get("domain", "")) or normalize(row.get("domain_route", "")) or source_domain
            dataset = normalize(row.get("dataset", "")) or domain or source_dataset
            row = normalize_claim_metadata(row, domain)
            domain = normalize(row.get("domain", "")) or normalize(row.get("domain_route", "")) or domain
            dataset = normalize(row.get("dataset", "")) or domain or source_dataset
            if normalize(row.get("review_scope_status", "")).casefold() == "psychedelics_peripheral_or_absent":
                audit_source_row = dict(row)
                audit_source_row["normalization_status"] = "paper_scope_not_graphable"
                audit_source_row["normalization_notes"] = (
                    normalize(row.get("review_scope_reason", ""))
                    or "the review title and relationship subject contain no recognized in-scope subject"
                )
                audits.append(audit_row(audit_source_row, source_name, domain, dataset))
                continue

            compound_label_raw = compound_label_for(row)
            compound_match = graphable_subject_match(row, registry)
            if not compound_match["matched"]:
                audit_source_row = dict(row)
                audit_source_row["normalization_status"] = compound_match["status"]
                audit_source_row["normalization_notes"] = compound_match["notes"]
                audit_source_row["compound_original"] = compound_label_raw
                audits.append(audit_row(audit_source_row, source_name, domain, dataset))
                continue

            paper_id = paper_id_for(row)
            papers.setdefault(paper_id, paper_row(row, paper_id))

            exact_subject_label = normalize(compound_match["label"])
            exact_subject_kind = normalize(compound_match.get("subject_kind", "")) or "atomic_compound"
            compound_registry = compound_match["item"]
            overview_subjects = overview_graph_subjects(row, compound_match, registry)
            use_context_projections = graph_use_context_projections(row, domain, overview_subjects, registry)
            overview_subject = (
                overview_subjects[0]
                if overview_subjects
                else {"label": "", "kind": "", "reason": "uncontrolled_subject_detail_only"}
            )
            compound_label = overview_subject["label"] or "Detail-only exposure"
            graph_subject_kind = overview_subject["kind"] or "exposure_context"
            compound_id = entity_id_for("compound", compound_label)
            entity_subjects = overview_subjects or [
                {"label": compound_label, "kind": graph_subject_kind, "reason": overview_subject["reason"]}
            ]
            for entity_subject in entity_subjects:
                subject_label = entity_subject["label"]
                subject_kind = entity_subject["kind"]
                subject_id = entity_id_for("compound", subject_label)
                subject_registry_item = compound_registry
                if subject_kind == "atomic_compound":
                    _, projected_registry_item = canonicalize_registry_label("compound", subject_label, registry)
                    if projected_registry_item:
                        subject_registry_item = projected_registry_item
                projection_aliases = [
                    normalize(alias)
                    for alias in entity_subject.get("aliases", [])
                    if normalize(alias)
                ]
                if projection_aliases:
                    subject_registry_item = dict(compound_registry or {})
                    subject_registry_item["aliases"] = list(
                        dict.fromkeys(
                            [
                                *[
                                    normalize(alias)
                                    for alias in subject_registry_item.get("aliases", [])
                                    if normalize(alias)
                                ],
                                *projection_aliases,
                            ]
                        )
                    )
                    subject_registry_item["status"] = (
                        normalize(subject_registry_item.get("status", ""))
                        or "controlled_combination_alias"
                    )
                context_definition = use_context_definition(subject_label) if subject_kind == "exposure_context" else None
                parent_label = context_definition.parent if context_definition else ""
                parent_kind = "exposure_context" if parent_label else ""
                parent_entity_id = entity_id_for("compound", parent_label) if parent_label else ""
                if context_definition:
                    subject_registry_item = dict(subject_registry_item or {})
                    subject_registry_item["aliases"] = list(
                        dict.fromkeys(
                            [
                                *[
                                    normalize(alias)
                                    for alias in subject_registry_item.get("aliases", [])
                                    if normalize(alias)
                                ],
                                *context_definition.aliases,
                            ]
                        )
                    )
                    subject_registry_item["status"] = "controlled_use_context"
                subject_record = entity_row(
                    subject_id,
                    "compound" if subject_kind == "atomic_compound" else "exposure_unit",
                    "compound" if subject_kind == "atomic_compound" else "exposure",
                    subject_label,
                    subject_kind,
                    subject_registry_item,
                    parent_label=parent_label,
                    parent_kind=parent_kind,
                    parent_entity_id=parent_entity_id,
                )
                if subject_id not in entities or (parent_entity_id and not entities[subject_id].get("graph_parent_entity_id")):
                    entities[subject_id] = subject_record
                if parent_entity_id:
                    parent_definition = use_context_definition(parent_label)
                    entities.setdefault(
                        parent_entity_id,
                        entity_row(
                            parent_entity_id,
                            "exposure_unit",
                            "exposure",
                            parent_label,
                            "exposure_context",
                            {
                                "aliases": list(parent_definition.aliases) if parent_definition else [],
                                "status": "controlled_use_context",
                            },
                        ),
                    )

            entity_kind = entity_kind_for(row, domain)
            raw_entity_label = entity_label_for(row, domain, entity_kind)
            entity_match = graphable_entity_match(
                row=row,
                domain=domain,
                entity_kind=entity_kind,
                raw_label=raw_entity_label,
                registry=registry,
                node_vocabulary=node_vocabulary,
            )
            if not entity_match["matched"]:
                audit_source_row = dict(row)
                audit_source_row["compound"] = compound_label
                audit_source_row["canonical_compound"] = compound_label
                audit_source_row["compound_original"] = compound_label_raw
                audit_source_row["graph_entity_label"] = raw_entity_label
                audit_source_row["canonical_entity"] = entity_match["label"]
                audit_source_row["kg_entity_kind_override"] = entity_kind
                audit_source_row["normalization_status"] = entity_match["status"]
                audit_source_row["normalization_notes"] = entity_match["notes"]
                audit_source_row["entity_match_type"] = entity_match["match_type"]
                audits.append(audit_row(audit_source_row, source_name, domain, dataset))
                continue

            entity_kind = entity_match["kind"]
            canonical_entity_label = entity_match["label"]
            registry_item = entity_match["item"]
            if domain == "molecular_target" and entity_kind in {"pathway_process", "biomarker_readout"}:
                domain = "molecular_pathway_readout"
                dataset = domain
                row = dict(row)
                row["domain"] = domain
                row["domain_route"] = domain
                row["dataset"] = domain
                row["normalization_boundary_reason"] = "molecular_target_readout_routed_to_molecular_effects"
            if (
                domain == "pharmacokinetics_exposure"
                and entity_kind == "compound"
                and label_key(canonical_entity_label) == label_key(compound_label)
            ):
                audit_source_row = dict(row)
                audit_source_row["compound"] = compound_label
                audit_source_row["canonical_compound"] = compound_label
                audit_source_row["compound_original"] = compound_label_raw
                audit_source_row["graph_entity_label"] = raw_entity_label
                audit_source_row["canonical_entity"] = canonical_entity_label
                audit_source_row["kg_entity_kind_override"] = entity_kind
                audit_source_row["normalization_status"] = "pk_self_reference_not_graphable"
                audit_source_row["normalization_notes"] = "PK source compound and graph object resolve to the same compound"
                audit_source_row["entity_match_type"] = entity_match["match_type"]
                audits.append(audit_row(audit_source_row, source_name, domain, dataset))
                continue
            canonical_entity_label = target_family_display_label(canonical_entity_label, entity_kind)
            if canonical_entity_label != entity_match["label"]:
                _, display_registry_item = canonicalize_registry_label("mechanistic_entity", canonical_entity_label, registry)
                if display_registry_item:
                    registry_item = display_registry_item
            entity_label = pathway_readout_display_label(
                row,
                entity_kind,
                canonical_entity_label,
                raw_entity_label,
                registry_item,
            )
            entity_label = canonical_entity_format_label(entity_label, entity_kind)
            if entity_kind == "symptom_problem":
                entity_label = symptom_problem_display_label(entity_label)
            display_label_note = ""
            if entity_label != canonical_entity_label:
                display_label_note = f"; display label refined from `{canonical_entity_label}`"
            pk_display_label = pharmacokinetic_display_label(row, domain, entity_kind, entity_label, node_vocabulary)
            entity_type = entity_type_for_kind(entity_kind, domain)
            entity_id = entity_id_for(entity_type, entity_label)
            table_row = dict(row)
            table_row["compound_original"] = compound_label_raw
            table_row["compound"] = compound_label
            table_row["canonical_compound"] = compound_label
            table_row["compound_match_type"] = compound_match["match_type"]
            table_row["compound_registry_status"] = normalize((compound_registry or {}).get("status", ""))
            table_row["graph_subject_label"] = exact_subject_label
            table_row["graph_subject_kind"] = exact_subject_kind
            table_row["graph_overview_subject_label"] = overview_subject["label"]
            table_row["graph_overview_subject_kind"] = overview_subject["kind"]
            table_row["graph_overview_subject_reason"] = overview_subject["reason"]
            table_row["graph_overview_subjects_json"] = json_dumps(overview_subjects)
            table_row["graph_use_context_projections_json"] = json_dumps(use_context_projections)
            table_row["normalization_status"] = "normalized"
            table_row["normalization_notes"] = f"{compound_match['notes']}; {entity_match['notes']}{display_label_note}"
            table_row["graph_entity_original"] = raw_entity_label
            table_row["graph_entity_label"] = entity_label
            table_row["canonical_entity"] = entity_label
            table_row["molecular_effect_label"] = molecular_effect_label(table_row, entity_kind, entity_label)
            parent_label, parent_kind, parent_entity_id, parent_item = graph_parent_mapping(
                table_row,
                domain,
                entity_kind,
                entity_label,
                registry_item,
                registry,
                node_vocabulary,
            )
            if (
                domain == "molecular_pathway_readout"
                and entity_kind in MOLECULAR_EFFECT_ENTITY_KINDS
                and parent_label
            ):
                corrected_parent = molecular_parent_from_specific(table_row, parent_label, entity_label)
                if corrected_parent and label_key(corrected_parent) != label_key(parent_label):
                    parent_label = corrected_parent
                    parent_kind = "pathway_process"
                    parent_type = entity_type_for_kind(parent_kind, domain)
                    parent_entity_id = entity_id_for(parent_type, parent_label)
                    parent_item = None
                    table_row["molecular_effect_label"] = parent_label
            table_row["graph_parent_label"] = parent_label
            table_row["graph_parent_kind"] = parent_kind
            table_row["graph_parent_entity_id"] = parent_entity_id
            table_row["molecular_finding_subtopic"] = molecular_finding_subtopic(
                table_row,
                parent_label,
                entity_label,
            )
            table_row["pharmacokinetic_display_label"] = pk_display_label
            table_row["entity_match_type"] = entity_match["match_type"]
            table_row["entity_registry_status"] = normalize((registry_item or {}).get("status", ""))
            table_row["kg_entity_kind_override"] = entity_kind
            table_row["result_direction_normalized"] = normalized_direction_for_row(table_row)
            admission_status, admission_reason = graph_admission_decision(table_row)
            if admission_status == "main_graph" and not overview_subject["label"]:
                admission_status = "paper_detail"
                admission_reason = overview_subject["reason"] or "uncontrolled_subject_detail_only"
            detail_only_subject_reasons = {
                normalize(subject.get("reason", ""))
                for subject in overview_subjects
                if normalize(subject.get("reason", "")) in DETAIL_ONLY_OVERVIEW_SUBJECT_REASONS
            }
            if admission_status == "main_graph" and detail_only_subject_reasons:
                admission_status = "paper_detail"
                admission_reason = (
                    RECOVERED_FINDING_SCOPE_REASON
                    if RECOVERED_FINDING_SCOPE_REASON in detail_only_subject_reasons
                    else "unresolved_psychedelic_class_detail_only"
                )
            table_row["graph_admission_status"] = admission_status
            table_row["graph_admission_reason"] = admission_reason
            proposition_group_id, proposition_conflict_group_id = proposition_identifiers(
                table_row,
                compound_label,
                entity_kind,
                entity_label,
            )
            table_row["proposition_group_id"] = proposition_group_id
            table_row["proposition_conflict_group_id"] = proposition_conflict_group_id

            entity_record = entity_row(
                entity_id,
                entity_type,
                domain,
                entity_label,
                entity_kind,
                registry_item,
                parent_label=parent_label,
                parent_kind=parent_kind,
                parent_entity_id=parent_entity_id,
            )
            if entity_id not in entities or (parent_entity_id and not entities[entity_id].get("graph_parent_entity_id")):
                entities[entity_id] = entity_record
            if parent_entity_id:
                parent_type = entity_type_for_kind(parent_kind, domain)
                if parent_item is None and parent_kind in MOLECULAR_EFFECT_ENTITY_KINDS:
                    _, parent_item = canonicalize_registry_label("mechanistic_entity", parent_label, registry)
                entities.setdefault(
                    parent_entity_id,
                    entity_row(
                        parent_entity_id,
                        parent_type,
                        domain,
                        parent_label,
                        parent_kind,
                        parent_item,
                    ),
                )

            evidence_type = evidence_type_for(row, default_evidence_type)
            finding_id = stable_id(
                finding_id_prefix,
                source_name,
                index,
                row.get("study_doi", ""),
                compound_label,
                entity_label,
                table_row.get("evidence_locator", ""),
                table_row.get("supporting_quote", ""),
            )
            evidence_id = stable_id("evidence", finding_id, evidence_type, entity_kind)
            findings.append(
                finding_row(
                    table_row,
                    source_name,
                    domain,
                    dataset,
                    evidence_type,
                    finding_id,
                    paper_id,
                    id_field=finding_id_field,
                )
            )
            evidence_edges.append(
                evidence_edge_row(
                    table_row,
                    source_name,
                    domain,
                    dataset,
                    evidence_type,
                    entity_kind,
                    finding_id,
                    evidence_id,
                    paper_id,
                    compound_id,
                    entity_id,
                    id_field=finding_id_field,
                )
            )
            for projection in use_context_projections:
                component_label = normalize(projection.get("subject_label", ""))
                context_label = normalize(projection.get("context_label", ""))
                if not component_label or not context_label:
                    continue
                component_id = entity_id_for("compound", component_label)
                component_item = dict(registry.get(("compound", label_key(component_label)), {}) or {})
                component_item["aliases"] = list(
                    dict.fromkeys(
                        [
                            *[
                                normalize(alias)
                                for alias in component_item.get("aliases", [])
                                if normalize(alias)
                            ],
                            *[
                                normalize(alias)
                                for alias in projection.get("subject_aliases", [])
                                if normalize(alias)
                            ],
                        ]
                    )
                )
                component_item["status"] = normalize(component_item.get("status", "")) or "controlled_use_context_component"
                entities.setdefault(
                    component_id,
                    entity_row(
                        component_id,
                        "compound",
                        "compound",
                        component_label,
                        "atomic_compound",
                        component_item,
                    ),
                )

                context_definition = use_context_definition(context_label)
                context_parent_label = normalize(projection.get("context_parent_label", ""))
                context_parent_kind = normalize(projection.get("context_parent_kind", ""))
                context_id = entity_id_for("compound", context_label)
                context_parent_id = entity_id_for("compound", context_parent_label) if context_parent_label else ""
                context_record = entity_row(
                    context_id,
                    "exposure_unit",
                    "exposure",
                    context_label,
                    "exposure_context",
                    {
                        "aliases": list(context_definition.aliases) if context_definition else [],
                        "status": "controlled_use_context",
                    },
                    parent_label=context_parent_label,
                    parent_kind=context_parent_kind,
                    parent_entity_id=context_parent_id,
                )
                if context_id not in entities or (context_parent_id and not entities[context_id].get("graph_parent_entity_id")):
                    entities[context_id] = context_record
                if context_parent_id:
                    parent_definition = use_context_definition(context_parent_label)
                    entities.setdefault(
                        context_parent_id,
                        entity_row(
                            context_parent_id,
                            "exposure_unit",
                            "exposure",
                            context_parent_label,
                            "exposure_context",
                            {
                                "aliases": list(parent_definition.aliases) if parent_definition else [],
                                "status": "controlled_use_context",
                            },
                        ),
                    )

                context_edge_row = dict(table_row)
                context_edge_row.update(
                    {
                        "projection_type": "use_context",
                        "compound": component_label,
                        "canonical_compound": component_label,
                        "graph_subject_label": component_label,
                        "graph_subject_kind": normalize(projection.get("subject_kind", "")) or "atomic_compound",
                        "graph_overview_subject_label": component_label,
                        "graph_overview_subject_kind": normalize(projection.get("subject_kind", "")) or "atomic_compound",
                        "graph_overview_subject_reason": normalize(projection.get("reason", "")),
                        "graph_overview_subjects_json": json_dumps(
                            [
                                {
                                    "label": component_label,
                                    "kind": normalize(projection.get("subject_kind", "")) or "atomic_compound",
                                    "reason": normalize(projection.get("reason", "")),
                                    "aliases": projection.get("subject_aliases", []),
                                }
                            ]
                        ),
                        "graph_entity_label": context_label,
                        "canonical_entity": context_label,
                        "kg_entity_kind_override": "exposure_context",
                        "graph_parent_label": context_parent_label,
                        "graph_parent_kind": context_parent_kind,
                        "graph_parent_entity_id": context_parent_id,
                        "kg_relation_type_override": normalize(projection.get("relation_type", ""))
                        or "reported_in_use_context",
                        "proposition_group_id": stable_id(
                            "proposition-use-context",
                            row.get("study_doi", ""),
                            component_label,
                            context_label,
                        ),
                        "proposition_conflict_group_id": "",
                    }
                )
                context_evidence_id = stable_id(
                    "evidence-use-context",
                    finding_id,
                    component_label,
                    context_label,
                )
                evidence_edges.append(
                    evidence_edge_row(
                        context_edge_row,
                        source_name,
                        domain,
                        dataset,
                        evidence_type,
                        "exposure_context",
                        finding_id,
                        context_evidence_id,
                        paper_id,
                        component_id,
                        context_id,
                        id_field=finding_id_field,
                    )
                )

        if not cfg.get("skip_audit", False):
            audit_path = Path(cfg.get("audit_path", ""))
            for row in load_json_array(audit_path):
                audits.append(audit_row(row, source_name, domain, dataset))

    proposition_summary = finalize_proposition_groups(findings, evidence_edges, finding_id_field)
    papers_df = dataframe(list(papers.values()))
    doi_aliases = load_doi_aliases(doi_alias_registry_path)
    funding_assertions = pd.DataFrame()
    funding_attempts = pd.DataFrame()
    funding_report = {
        "status": "not_available",
        "assertions_path": str(funding_assertions_path) if funding_assertions_path else "",
        "attempts_path": str(funding_attempts_path) if funding_attempts_path else "",
    }
    if funding_assertions_path is not None and funding_assertions_path.is_file():
        funding_assertions = pd.read_parquet(funding_assertions_path)
        if funding_attempts_path is not None and funding_attempts_path.is_file():
            funding_attempts = pd.read_parquet(funding_attempts_path)
        papers_df, projection_report = materialize_funding(
            papers_df,
            funding_assertions,
            funding_attempts,
            doi_aliases,
        )
        funding_assertions = subset_assertions_for_papers(
            funding_assertions, papers_df, doi_aliases
        )
        funding_report = {
            "status": "ok",
            "assertions_path": str(funding_assertions_path.resolve()),
            "assertions_sha256": source_sha256(funding_assertions_path),
            "attempts_path": (
                str(funding_attempts_path.resolve())
                if funding_attempts_path is not None and funding_attempts_path.is_file()
                else ""
            ),
            "doi_alias_registry_path": (
                str(doi_alias_registry_path.resolve())
                if doi_alias_registry_path is not None and doi_alias_registry_path.is_file()
                else ""
            ),
            "attempts_sha256": (
                source_sha256(funding_attempts_path)
                if funding_attempts_path is not None and funding_attempts_path.is_file()
                else ""
            ),
            **projection_report,
            "kg_funding_assertion_rows": len(funding_assertions),
        }
    open_science_assertions = pd.DataFrame()
    open_science_report = {
        "status": "not_available",
        "features_path": (
            str(open_science_features_path) if open_science_features_path else ""
        ),
        "assertions_path": (
            str(open_science_assertions_path)
            if open_science_assertions_path
            else ""
        ),
    }
    if (
        open_science_features_path is not None
        and open_science_features_path.is_file()
    ):
        open_science_features = pd.read_parquet(open_science_features_path)
        papers_df, projection_report = materialize_open_science(
            papers_df,
            open_science_features,
            doi_aliases,
        )
        if (
            open_science_assertions_path is not None
            and open_science_assertions_path.is_file()
        ):
            open_science_assertions = pd.read_parquet(
                open_science_assertions_path
            )
        open_science_assertions = subset_open_science_assertions(
            open_science_assertions,
            papers_df,
            doi_aliases,
        )
        open_science_report = {
            "status": "ok",
            "features_path": str(open_science_features_path.resolve()),
            "features_sha256": source_sha256(open_science_features_path),
            "assertions_path": (
                str(open_science_assertions_path.resolve())
                if open_science_assertions_path is not None
                and open_science_assertions_path.is_file()
                else ""
            ),
            "assertions_sha256": (
                source_sha256(open_science_assertions_path)
                if open_science_assertions_path is not None
                and open_science_assertions_path.is_file()
                else ""
            ),
            "doi_alias_registry_path": (
                str(doi_alias_registry_path.resolve())
                if doi_alias_registry_path is not None
                and doi_alias_registry_path.is_file()
                else ""
            ),
            **projection_report,
            "kg_open_science_assertion_rows": len(open_science_assertions),
        }
    tables = {
        "papers": papers_df,
        "paper_funding": funding_assertions,
        "paper_open_science_assertions": open_science_assertions,
        "entities": dataframe(list(entities.values())),
        finding_table_name: dataframe(findings),
        "evidence_edges": dataframe(evidence_edges),
        "normalization_audit": dataframe(audits),
    }
    molecular_subtopic_coverage = molecular_subtopic_coverage_summary(tables[finding_table_name])
    if route_native and molecular_subtopic_coverage["status"] != "ok":
        failed_parents = ", ".join(molecular_subtopic_coverage.get("failed_parents", []))
        raise ValueError(
            "molecular subtopic coverage exceeded the "
            f"{MOLECULAR_SUBTOPIC_MAX_RESIDUAL_RATE:.0%} residual threshold for: {failed_parents}"
        )

    if out_dir.exists():
        for table_name in tables:
            existing = out_dir / f"{table_name}.parquet"
            if existing.exists():
                existing.unlink()
        stale_table = "claims" if route_native else "findings"
        stale_path = out_dir / f"{stale_table}.parquet"
        if stale_path.exists():
            stale_path.unlink()
    out_dir.mkdir(parents=True, exist_ok=True)
    for table_name, df in tables.items():
        write_parquet(df, out_dir / f"{table_name}.parquet")

    duckdb_status = write_duckdb_database(out_dir, tables.keys()) if write_duckdb else {"status": "skipped"}

    edge_df = tables["evidence_edges"]
    entity_df = tables["entities"]
    manifest = {
        "kg_table_version": KG_TABLE_VERSION,
        "molecular_subtopic_taxonomy_version": MOLECULAR_SUBTOPIC_TAXONOMY_VERSION,
        "generated_at": now_utc(),
        "out_dir": str(out_dir),
        "source_preset": manifest_source_preset,
        "run_id": safe_run_id(run_id),
        "evidence_run_id": safe_run_id(evidence_run_id or run_id),
        "registry_path": str(registry_path),
        "node_vocabulary_path": str(node_vocabulary_path),
        "source_counts": source_counts,
        "tables": {
            table_name: {
                "path": str(out_dir / f"{table_name}.parquet"),
                "rows": int(len(df)),
                "columns": list(df.columns),
            }
            for table_name, df in tables.items()
        },
        "edge_counts_by_domain_kind_evidence": edge_counts(edge_df),
        "entity_counts_by_type_kind": entity_counts(entity_df),
        "molecular_subtopic_coverage": molecular_subtopic_coverage,
        "proposition_summary": proposition_summary,
        "funding_metadata": funding_report,
        "open_science_metadata": open_science_report,
        "graph_admission_counts": dict(Counter(normalize(row.get("graph_admission_status", "")) for row in findings)),
        "graph_subject_kind_counts": dict(Counter(normalize(row.get("graph_subject_kind", "")) for row in findings)),
        "duckdb": duckdb_status,
    }
    write_json(out_dir / "manifest.json", manifest)
    return manifest


def edge_counts(df: pd.DataFrame) -> list[dict]:
    if df.empty:
        return []
    counts = (
        df.groupby(["domain", "entity_kind", "evidence_type"], dropna=False)
        .size()
        .reset_index(name="count")
        .sort_values(["domain", "entity_kind", "evidence_type"])
    )
    return counts.to_dict(orient="records")


def entity_counts(df: pd.DataFrame) -> list[dict]:
    if df.empty:
        return []
    counts = (
        df.groupby(["entity_type", "entity_kind"], dropna=False)
        .size()
        .reset_index(name="count")
        .sort_values(["entity_type", "entity_kind"])
    )
    return counts.to_dict(orient="records")


def write_duckdb_database(out_dir: Path, table_names: Iterable[str]) -> dict:
    try:
        import duckdb
    except ModuleNotFoundError:
        return {
            "status": "missing_dependency",
            "message": "Install duckdb to materialize kg.duckdb; Parquet tables were written.",
        }

    db_path = out_dir / "kg.duckdb"
    if db_path.exists():
        db_path.unlink()
    con = duckdb.connect(str(db_path))
    skipped_empty_tables: list[str] = []
    try:
        for table_name in table_names:
            parquet_path = (out_dir / f"{table_name}.parquet").as_posix()
            if len(pd.read_parquet(parquet_path).columns) == 0:
                skipped_empty_tables.append(table_name)
                continue
            con.execute(f"CREATE TABLE {table_name} AS SELECT * FROM read_parquet(?)", [parquet_path])
        con.execute("CHECKPOINT")
    finally:
        con.close()
    return {"status": "ok", "path": str(db_path), "skipped_empty_tables": skipped_empty_tables}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY_PATH)
    parser.add_argument(
        "--source-preset",
        choices=sorted(GRAPH_SOURCE_PRESETS),
        default="routed",
        help="Evidence source set to materialize. Routed extraction rows are the only built-in preset.",
    )
    parser.add_argument(
        "--run-id",
        default="",
        help="Version label for routed KG runs. Used in the default output path for --source-preset routed.",
    )
    parser.add_argument(
        "--evidence-run-id",
        default="",
        help="Read routed evidence from a different versioned extraction run while writing this release under --run-id.",
    )
    parser.add_argument("--out-dir", type=Path, default=None)
    parser.add_argument(
        "--funding-assertions",
        type=Path,
        default=DEFAULT_FUNDING_ASSERTIONS_PATH,
        help="Provider-backed normalized funding assertions to project onto paper rows.",
    )
    parser.add_argument(
        "--funding-attempts",
        type=Path,
        default=DEFAULT_FUNDING_ATTEMPTS_PATH,
        help="Provider-attempt ledger used to distinguish no reported funding from not enriched.",
    )
    parser.add_argument(
        "--open-science-features",
        type=Path,
        default=DEFAULT_OPEN_SCIENCE_FEATURES_PATH,
        help="DOI-keyed open-science feature summaries to project onto paper rows.",
    )
    parser.add_argument(
        "--open-science-assertions",
        type=Path,
        default=DEFAULT_OPEN_SCIENCE_ASSERTIONS_PATH,
        help="Normalized open-science assertions retained with the KG release.",
    )
    parser.add_argument(
        "--doi-alias-registry",
        type=Path,
        default=DEFAULT_DOI_ALIAS_REGISTRY,
        help="Registered DOI aliases applied to paper and funding identities.",
    )
    parser.add_argument(
        "--allow-current-overwrite",
        action="store_true",
        help="Allow a routed KG build to write directly to data/processed/kg.",
    )
    parser.add_argument("--skip-duckdb", action="store_true", help="Only write Parquet tables and manifest.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    out_dir, run_id = resolve_kg_output_dir(
        source_preset=args.source_preset,
        out_dir=args.out_dir,
        run_id=args.run_id,
    )
    promoting_to_current = out_dir.resolve() == DEFAULT_OUT_DIR.resolve()
    if promoting_to_current and not args.allow_current_overwrite:
        raise SystemExit(
            "Refusing to write routed sources directly to data/processed/kg. "
            "Use --run-id for a versioned build, or add --allow-current-overwrite if this is an intentional promotion."
        )
    if promoting_to_current and not run_id:
        raise SystemExit("Promoting routed sources to data/processed/kg requires --run-id.")
    manifest = build_tables(
        source_preset=args.source_preset,
        run_id=run_id,
        evidence_run_id=args.evidence_run_id,
        registry_path=args.registry,
        funding_assertions_path=args.funding_assertions,
        funding_attempts_path=args.funding_attempts,
        open_science_features_path=args.open_science_features,
        open_science_assertions_path=args.open_science_assertions,
        doi_alias_registry_path=args.doi_alias_registry,
        out_dir=out_dir,
        write_duckdb=not args.skip_duckdb,
    )
    print(f"wrote KG tables to {out_dir}")
    print(f"source preset: {manifest['source_preset']}")
    if manifest.get("run_id"):
        print(f"run id: {manifest['run_id']}")
    for table_name, info in manifest["tables"].items():
        print(f"{table_name}: {info['rows']} rows -> {info['path']}")
    print(f"duckdb: {manifest['duckdb']['status']}")


if __name__ == "__main__":
    main()
