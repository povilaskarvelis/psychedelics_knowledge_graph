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
from pathlib import Path
from typing import Iterable

import pandas as pd

try:
    from pipeline.extract.clinical_comparator import normalize_clinical_comparator
    from pipeline.extract.clinical_followup_window import normalize_clinical_followup_window
    from pipeline.extract.mechanistic_assay_family import normalize_mechanistic_assay_family
    from pipeline.extract.io_utils import SYSTEM_NORMALIZATION, normalize, write_json
    from pipeline.kg.pk_relationships import add_pk_relationship_fields
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from pipeline.extract.clinical_comparator import normalize_clinical_comparator
    from pipeline.extract.clinical_followup_window import normalize_clinical_followup_window
    from pipeline.extract.mechanistic_assay_family import normalize_mechanistic_assay_family
    from pipeline.extract.io_utils import SYSTEM_NORMALIZATION, normalize, write_json
    from pipeline.kg.pk_relationships import add_pk_relationship_fields


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EXTRACTION_DIR = ROOT / "data" / "processed" / "extraction"
DEFAULT_OUT_DIR = ROOT / "data" / "processed" / "kg"
DEFAULT_ROUTED_KG_RUN_ROOT = ROOT / "data" / "processed" / "kg_routed_runs"
DEFAULT_REGISTRY_PATH = ROOT / "data" / "curated" / "entity_registry.json"
DEFAULT_DISORDER_ALIASES_PATH = ROOT / "schema" / "disorder_canonicalization.json"
DEFAULT_NODE_VOCABULARY_PATH = ROOT / "schema" / "kg_node_vocabularies.json"
DEFAULT_PAPER_LIBRARY_PATHS = {
    "disorder": ROOT / "data" / "processed" / "paper_library_disorder.csv",
    "mechanistic": ROOT / "data" / "processed" / "paper_library_mechanistic.csv",
}
KG_TABLE_VERSION = "0.1"

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
    "raw_entity_label",
    "entity_role",
    "clinical_context_condition",
    "graph_entity_label",
    "graph_entity_type",
    "graph_exclusion_reason",
    "mechanism_type",
    "assay_type",
    "assay_family",
    "assay_family_normalized",
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
    "specific_readout_or_marker",
    "mechanistic_relationship_type",
    "public_health_topic_category",
    "public_health_measure",
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
    "adverse_events",
    "evidence_level",
    "support",
    "confidence",
    "needs_human_review",
    "supporting_quote",
    "evidence_location",
    "evidence_locator",
    "paper_assessment_route",
    "source_type",
    "source_family",
    "paper_type",
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
)
MECHANISTIC_METADATA_DOMAINS = {
    "mechanistic",
    "molecular_target",
    "molecular_pathway_readout",
    "brain_system",
    "pharmacokinetics_exposure",
}
CLINICAL_METADATA_DOMAINS = {"clinical", "clinical_outcome"}
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
PUBLIC_HEALTH_TOPIC_RULES = (
    (
        "Microdosing",
        re.compile(r"\bmicrodos\w*\b", re.IGNORECASE),
    ),
    (
        "Drug checking & adulteration",
        re.compile(
            r"\b(drug checking|amnesty bins?|seized samples?|adulter\w*|substitution|unexpected drug|"
            r"unexpected detection|portable gc|gc[- ]?ms|festival testing|harm[- ]?reduction information|"
            r"information source|trip[- ]?sitter|sitter|babysitter)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Wastewater & market signals",
        re.compile(
            r"\b(wastewater|drug load|mass load|population[- ]normalised|population[- ]normalized|"
            r"sewage|pndl|pnl|"
            r"population consumption|per inhabitant consumption|estimated daily consumption|"
            r"consumption based on metabolic rate|cryptomarket|darknet|market|purchase|availability|"
            r"easy to obtain|obtain|price)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Emergency/toxicology reports",
        re.compile(
            r"\b(poison[- ]?cent(?:er|re)s?|poison control|emergency|ed visit|emergency medical treatment|emt|"
            r"hospitali[sz]|intensive care|icu|fatalit\w*|fatal|death|mortality|coronial|forensic|"
            r"postmortem|post mortem|toxicology|toxicological|toxicosurveillance|intoxication|overdose|"
            r"adverse event reports?|faers|reporting odds ratio|serum concentration|blood analysis|urine analysis|"
            r"hair analysis|drug concentration in hair|suspected dfsa|suicid\w*)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Ceremonial/retreat use",
        re.compile(
            r"\b(ceremon\w*|ritual\w*|retreat|ayahuasca shamanisms?|shamanic|intention[- ]setting|"
            r"sacralization|naturalistic ceremonial)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Polysubstance use",
        re.compile(
            r"\b(polysubstance|poly[- ]?drug|polydrug|co[- ]?use|co use|concomitant|combined with|"
            r"combination|cannabis taken alongside|additional substances?|one or more additional substances|"
            r"mdma/mda|mdma/methamphetamine)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Self-treatment",
        re.compile(
            r"\b(self[- ]?treat\w*|self[- ]?medicat\w*|perceived benefit|therapeutic benefit|"
            r"psychotherapeutic benefit|medical reasons?|psychiatric improvement|symptom improvement|"
            r"treatment outcomes?|cluster headache|busting|preventive efficacy|abortive efficacy|healing|"
            r"trauma|cravings?|life changes|quality of life|wellbeing|well-being)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Access to services",
        re.compile(
            r"\b(access|service delivery|care delivery|implementation|early[- ]access|prescrib\w*|"
            r"prescription|treatment availability|certified treatment centers?|provider|social workers?|"
            r"psychiatrists?|attitudes|acceptability|appropriateness|feasibility|patient characteristics|"
            r"social determinants|atu[cC])\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Legal/criminal justice",
        re.compile(
            r"\b(policy|regulat\w*|legal|criminal\w*|crime|arrest\w*|prison|incarcerat\w*|"
            r"violence|intimate partner violence|classification|drug harms?|scheduling)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Problematic use",
        re.compile(
            r"\b(misuse|abuse liability|dependen\w*|addict\w*|diversion|nonmedical|non[- ]medical|"
            r"substance use disorder|use disorder|sud\b|drug abuse|drug dependence|alcohol abuse|"
            r"problematic|compulsive|obsessive|over[- ]?eager|tolerance|withdrawal|craving)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Recreational use",
        re.compile(
            r"\b(recreational|first[- ]time use|club|club[- ]going|nightlife|dance event|festival|rave|"
            r"party|naturalistic|pattern of use|use patterns?|route of administration|administration route|"
            r"frequency|user profiles?|future use|preference|intentions to use|novelty|"
            r"subjective experience themes|motivations for use|primary reason for use)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Prevalence & trends",
        re.compile(
            r"\b(epidemiology|prevalence|incidence|lifetime use|past[- ]year|past 12[- ]month|"
            r"use prevalence|trend|demographic|risk factors?|age of initiation|population[- ]based|"
            r"survey|odds of past year|quality of life score|correlates?)\b",
            re.IGNORECASE,
        ),
    ),
)
PUBLIC_HEALTH_TOPIC_LABELS = {label for label, _pattern in PUBLIC_HEALTH_TOPIC_RULES}
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
COGNITIVE_BEHAVIORAL_RULES = (
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
        "Drug seeking",
        re.compile(
            r"\b(drug[- ]seeking|alcohol seeking|ethanol seeking|cocaine seeking|reinstatement|relapse|"
            r"cue[- ]induced|priming[- ]induced|reconsolidation of alcohol[- ]related memories|"
            r"craving|urge to smoke|abstinence self[- ]efficacy)\b",
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
        "Reward processing",
        re.compile(
            r"\b(reward processing|reward function|sucrose preference|anhedonia|hedonic|pleasure|motivation|"
            r"intracranial self[- ]stimulation|\bicss\b|reward threshold)\b",
            re.IGNORECASE,
        ),
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
        "Threat avoidance",
        re.compile(
            r"\b(anxiety[- ]like|anxiety behavior|anxiogenic|anxiolytic|elevated plus[- ]maze|"
            r"elevated plus maze|plus[- ]maze|\bepm\b|"
            r"elevated zero maze|\bezm\b|zero maze|open arms?|novelty[- ]suppressed feeding|\bnsft\b|"
            r"light[- ]dark|marble burying|bottom dwelling|center zone|center time|thigmotaxis|"
            r"defensive burying|threat avoidance)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Fear memory",
        re.compile(r"\b(fear memory|fear conditioning|conditioned fear|learned fear|contextual fear|cued fear)\b", re.IGNORECASE),
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
        "Memory",
        re.compile(r"\b(memory|retrieval|consolidation|reconsolidation|passive avoidance|autoshaping)\b", re.IGNORECASE),
    ),
    (
        "Cognitive flexibility",
        re.compile(r"\b(cognitive flexibility|psychological flexibility|reversal learning|set[- ]shifting)\b", re.IGNORECASE),
    ),
    (
        "Inhibitory control",
        re.compile(r"\b(inhibitory control|response inhibition|impulsivity|impulsive action)\b", re.IGNORECASE),
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
    "anhedonia": "Reward processing",
    "anxiety": "Threat avoidance",
    "anxiety like behavior": "Threat avoidance",
    "anxiety behavior": "Threat avoidance",
    "depression like behavior": "Stress-coping behavior",
    "depressive like behavior": "Stress-coping behavior",
    "antidepressant like behavior": "Stress-coping behavior",
    "drug seeking and reinstatement": "Drug seeking",
    "social behavior": "Social interaction",
    "social cognition and interaction": "Social cognition",
    "pain behavior": "Pain behavior",
    "nociception and pain behavior": "Pain behavior",
    "hallucinogen like behavior": "Head-twitch response",
    "hallucinogenic like behavior": "Head-twitch response",
    "psychedelic like behavior": "Head-twitch response",
}
SUBJECTIVE_EXPERIENCE_CONTEXT_FIELDS = (
    "graph_entity_label",
    "raw_entity_label",
    "entity_label",
    "subjective_construct",
    "subjective_construct_category",
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
            r"\bobn\b|experience of unity|unitive|self[- ]transcendence|ineffability)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Near-death-like experience",
        re.compile(r"\b(near[- ]death|nde\b|greyson)\b", re.IGNORECASE),
    ),
    (
        "Ego dissolution",
        re.compile(r"\b(ego[- ]?dissolution|ego loss|ego death|ego disintegration|ego[- ]dissolution inventory|\bedi\b)\b", re.IGNORECASE),
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
        "Psychosis-like effects",
        re.compile(r"\b(psychotomimetic|psychosis[- ]like|psychotic[- ]like|psychotic symptoms?|positive symptoms?|bprs|panss)\b", re.IGNORECASE),
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
        "Perceptual alterations",
        re.compile(
            r"\b(perceptual alteration|perceptual changes?|perception|visual|auditory|hallucination|hallucinogenic|"
            r"hallucinogen rating|hrs\b|imagery|elementary imagery|complex imagery|syna?esth|sensory changes?|"
            r"phosphenic|perceptual rivalry|visionary)\b",
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
        "Personal meaning",
        re.compile(
            r"\b(meaning|meaningful|meaningfulness|presence of meaning|purpose in life|important experiences?|"
            r"significant experiences?|personal significance|life satisfaction)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Euphoria",
        re.compile(r"\b(euphoria|euphoric|liking|good effects|high\b|bliss|amazing|drug liking)\b", re.IGNORECASE),
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
        re.compile(r"\b(altered states?|altered state of consciousness|asc\b|5d[- ]?asc|11d[- ]?asc|3d[- ]?asc|continuous subjective experience|primary process thinking|apz\b)\b", re.IGNORECASE),
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
    "meaning spirituality": "Personal meaning",
    "mood euphoria": "Euphoria",
    "mystical experience": "Mystical-type experience",
    "mystical type experience": "Mystical-type experience",
    "near death experience phenomenology": "Near-death-like experience",
    "oceanic boundlessness": "Mystical-type experience",
    "psychological insight": "Psychological insight",
    "psychosis like experience": "Psychosis-like effects",
    "psychotomimetic symptoms": "Psychosis-like effects",
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
    "study_title",
    "support",
    "supporting_quote",
)
SUBJECTIVE_EXPERIENCE_SAFETY_RE = re.compile(
    r"\b(persistent|persisting|daily panic|panic attacks?|visual snow|depersonalization[- ]derealization disorder|"
    r"depersonalisation[- ]derealisation disorder|\bdp/dr\b|\bddd\b|clinically significant|"
    r"adverse events?|adverse effects?|adverse mental states?|dropout|dropped out|discontinuation|"
    r"medical attention|psychotic symptoms?|full[- ]blown psychotic|manic symptoms?|mania|hypomania)\b",
    re.IGNORECASE,
)
SUBJECTIVE_EXPERIENCE_NONADVERSE_RE = re.compile(r"\b(no adverse events?|not associated with adverse|without adverse)\b", re.IGNORECASE)

PRIMARY_MARKERS = {"primary_evidence", "primary_study", "primary_results"}
SECONDARY_MARKERS = {"secondary_literature", "secondary_evidence", "review", "meta_analysis", "systematic_review"}
MECHANISTIC_ENTITY_KIND_OVERRIDES = {"target", "pathway_process", "biomarker_readout", "system_family"}
ROUTE_NATIVE_ENTITY_KINDS = {
    "brain_region",
    "brain_network",
    "neural_circuit",
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
    "cognitive_behavioral_construct",
    "subjective_experience_construct",
    "pharmacokinetic_parameter",
    "intervention_component",
    "public_health_measure",
}
GRAPH_ENTITY_KINDS = {
    "compound",
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
        "molecular_effect_category",
        "pathway_or_process",
        "pathway_or_readout",
        "metabolic_or_transport_pathway",
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
        "graph_entity_label",
        "entity_label",
        "entity",
    ),
    "brain_region": ("brain_region", "graph_entity_label", "entity_label", "entity"),
    "brain_network": ("brain_network", "graph_entity_label", "entity_label", "entity"),
    "neural_circuit": ("neural_circuit", "connectivity_or_circuit_relationship", "graph_entity_label", "entity_label", "entity"),
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
MECHANISTIC_BIOMARKER_LABELS = {
    "Arc",
    "BDNF",
    "c-Fos",
    "DOPAC",
    "Dopamine",
    "GDNF",
    "GFAP",
    "Glutamate",
    "HSP70",
    "HVA",
    "IGF1",
    "IL-1beta",
    "IL-6",
    "IL-8",
    "Myelin basic protein",
    "Neurofilament light chain",
    "NGF",
    "Norepinephrine",
    "Prolactin",
    "PSD-95 (DLG4)",
    "Serotonin",
    "TGF-beta",
    "TNF-alpha",
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
REFERENCE_CONTROL_COMPOUND_KEYS = {
    "5 ht",
    "5 hydroxytryptamine",
    "5 hydroxytryptophan",
    "8 oh dpat",
    "cp 93129",
    "clozapine",
    "d serine",
    "glycine",
    "gr 127935",
    "ifenprodil",
    "ketanserin",
    "m100907",
    "memantine",
    "methysergide",
    "mk 801",
    "nmda",
    "pcp",
    "phencyclidine",
    "phencyclidine pcp",
    "pnu 142633",
    "ritanserin",
    "sb 216641",
    "sb271046",
    "serotonin",
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


def compact_key(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", label_key(value))


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
    key = label_key(value)
    compact = compact_key(value)
    reference_compacts = {compact_key(item) for item in REFERENCE_CONTROL_COMPOUND_KEYS}
    return key in REFERENCE_CONTROL_COMPOUND_KEYS or compact in reference_compacts


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


def registry_compound_labels_in_text(value: object, registry: dict[tuple[str, str], dict]) -> set[str]:
    text_key = label_key(value)
    if not text_key:
        return set()
    labels: set[str] = set()
    for entity_type, key in registry:
        if entity_type != "compound" or len(key) < 3:
            continue
        if re.search(rf"\b{re.escape(key)}\b", text_key):
            labels.add(normalize(registry[(entity_type, key)].get("label", "")))
    return {label for label in labels if label}


COMPOUND_TEXT_LABEL_SUPERSEDES = {
    "S-ketamine": {"Ketamine"},
    "R-ketamine": {"Ketamine"},
    "5-MeO-DMT": {"DMT"},
}
COMPOUND_COMBO_TEXT_RE = re.compile(r"\b(and|or|plus|followed by|combined with|coadministered|co-administered|sequential)\b|[+/]", re.IGNORECASE)


def prune_compound_text_labels(raw: object, labels: set[str]) -> set[str]:
    if len(labels) <= 1:
        return labels
    pruned = set(labels)
    for specific, broad_labels in COMPOUND_TEXT_LABEL_SUPERSEDES.items():
        if specific in pruned:
            pruned -= broad_labels
    if len(pruned) == 1 and not COMPOUND_COMBO_TEXT_RE.search(ascii_fold(raw)):
        return pruned
    return labels


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


def registry_entity_labels_in_text(value: object, entity_type: str, registry: dict[tuple[str, str], dict]) -> set[str]:
    text_key = label_key(value)
    if not text_key:
        return set()
    labels: set[str] = set()
    for candidate_entity_type, key in registry:
        if candidate_entity_type != entity_type or len(key) < 3:
            continue
        if key == "net" and re.search(r"\bperineuronal net\b", text_key):
            continue
        if re.search(rf"\b{re.escape(key)}\b", text_key):
            labels.add(normalize(registry[(candidate_entity_type, key)].get("label", "")))
    return {label for label in labels if label}


CONDITION_LABEL_SUPERSEDES = {
    "Alcohol use disorder": {"Substance use disorder"},
    "Anorexia nervosa": {"Eating disorders"},
    "Bipolar depression": {"Depressive disorders", "Mood disorders"},
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
    "Nicotine dependence": {"Substance use disorder"},
    "Opioid use disorder": {"Substance use disorder"},
    "Persistent depressive disorder": {"Depressive disorders", "Mood disorders"},
    "Social anxiety disorder": {"Anxiety disorders"},
    "Stimulant use disorder": {"Substance use disorder"},
    "Tobacco use disorder": {"Nicotine dependence", "Substance use disorder"},
    "Treatment-resistant depression": {"Depressive disorders", "Major depressive disorder", "Mood disorders"},
}
NON_GRAPHABLE_BROAD_CONDITION_LABELS = {
    "Anxiety disorders",
    "Depressive disorders",
    "Pain conditions",
}


def prune_condition_labels(labels: set[str]) -> list[str]:
    pruned = set(labels)
    for specific, broad_labels in CONDITION_LABEL_SUPERSEDES.items():
        if specific in pruned:
            pruned -= broad_labels
    pruned -= NON_GRAPHABLE_BROAD_CONDITION_LABELS
    return sorted(pruned, key=lambda label: (-len(label), label.casefold()))


def condition_labels_in_text(value: object, registry: dict[tuple[str, str], dict]) -> list[str]:
    return prune_condition_labels(registry_entity_labels_in_text(value, "clinical_entity", registry))


def node_vocabulary_labels_in_text(value: object, entity_kind: str, node_vocabulary: dict[tuple[str, str], dict]) -> set[str]:
    text_key = label_key(value)
    if not text_key:
        return set()
    labels: set[str] = set()
    for candidate_kind, key in node_vocabulary:
        if candidate_kind != entity_kind or len(key) < 4:
            continue
        if re.search(rf"\b{re.escape(key)}\b", text_key):
            labels.add(normalize(node_vocabulary[(candidate_kind, key)].get("label", "")))
    return {label for label in labels if label}


DIRECT_TARGET_REGISTRY_STATUSES = {
    "needs_external_id_lookup",
    "complex_target_needs_subunit_mapping",
}
TARGET_FAMILY_REGISTRY_STATUSES = {"broad_target_family", "composite_target_needs_split"}
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
        re.compile(r"\b(gut|microbiome|microbiota|microbial|bacteri\w*|fecal|faecal|short chain fatty acids?|scfa)\b", re.IGNORECASE),
    ),
    (
        "Inflammation",
        re.compile(
            r"\b(neuroinflamm\w*|inflamm\w*|cytokine\w*|interleukin\w*|il[- ]?\d+|tnf|"
            r"nf[- ]?kappa[- ]?b|nf[- ]?kb|cox[- ]?2|prostaglandin\w*|microglia\w*|"
            r"astrocyt\w*|glial|gfap|iba[- ]?1|complement|crp|hmgb1|tlr[- ]?4|"
            r"il[- ]?\d+\w*|tgf[- ]?beta)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Cellular stress",
        re.compile(
            r"\b(oxidative stress|reactive oxygen|\bros\b|lipid peroxidation|malondialdehyde|\bmda\b|"
            r"glutathione|\bgsh\b|\bsod\b|catalase|apoptosis|caspase|cell death|necrosis|"
            r"hsp[- ]?70|heat shock|neurotox\w*|toxicity|toxic marker|neurofilament|\bnfl\b|s100b)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Neuroplasticity",
        re.compile(
            r"\b(bdnf|trkb|trk b|ngf|gdnf|vegf|igf[- ]?1|insulin[- ]like growth factor|"
            r"neurotroph\w*|growth factor\w*|plasticity|"
            r"synaptic|synapse|dendritic|spine|neurogenesis|neurite|synaptogenesis|"
            r"long[- ]?term potentiation|\bltp\b|long[- ]?term depression|\bltd\b|psd[- ]?95|"
            r"synaptophysin|\barc\b|sv2a|synaptic vesicle|perineuronal net)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Intracellular signaling",
        re.compile(
            r"\b(erk|mapk|mtor|mtorc1|akt|camp|creb|pka|pkc|plc|pi3k|gsk[- ]?3|p70s6k|"
            r"stat3|jnk|phosphorylation|phosphorylated|phospho|second messenger\w*|"
            r"kinase\w*|signal(?:ing|ling)|phosphoinositide)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Immediate early gene activation",
        re.compile(
            r"\b(c[- ]?fos|fosb|egr[- ]?1|immediate early|neuronal activation|neural activation|"
            r"neural activity|neuronal activity)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Serotonin signaling",
        re.compile(r"\b(serotonin|5[- ]?hydroxytryptamine|5[- ]?hiaa|5[- ]?ht\d?[a-z]?|sert|slc6a4)\b", re.IGNORECASE),
    ),
    (
        "Dopamine signaling",
        re.compile(r"\b(dopamine|\bdopa\b|dopac|\bhva\b|\bdat\b|slc6a3|d[1-5][ -]?receptor)\b", re.IGNORECASE),
    ),
    (
        "Glutamate signaling",
        re.compile(r"\b(glutamate|glutamatergic|ampa|nmda|nmdar|ampar|mglur|mglu\d?|glua\d?|glun\d?|vglut)\b", re.IGNORECASE),
    ),
    (
        "GABA signaling",
        re.compile(r"\b(gaba|gabaergic|gabr|gad[- ]?65|gad[- ]?67)\b", re.IGNORECASE),
    ),
    (
        "Epigenetic regulation",
        re.compile(r"\b(epigen\w*|dna methylation|methylation|histone\w*|chromatin)\b", re.IGNORECASE),
    ),
    (
        "Genetic moderators",
        re.compile(r"\b(polymorphism\w*|genotype\w*|phenotype interaction|allele\w*|rs\d+)\b", re.IGNORECASE),
    ),
    (
        "Gene expression",
        re.compile(r"\b(gene expression|transcript\w*|transcriptom\w*|mrna|rna|mirna|microrna)\b", re.IGNORECASE),
    ),
    (
        "Drug metabolism",
        re.compile(r"\b(cyp\d+\w*|cytochrome p450|ugt\d*\w*|monoamine oxidase|mao[- ]?[ab]?|comt|metabolic enzyme\w*|in vitro metabolism)\b", re.IGNORECASE),
    ),
    (
        "Endocrine response",
        re.compile(r"\b(cortisol|corticosterone|acth|prolactin|hormone\w*|endocrine|melatonin|oxytocin|vasopressin)\b", re.IGNORECASE),
    ),
    (
        "Norepinephrine signaling",
        re.compile(r"\b(norepinephrine|noradrenaline|\bne\b|\bna\b|slc6a2|net\b)\b", re.IGNORECASE),
    ),
    (
        "Neuronal excitability",
        re.compile(
            r"\b(firing rate|spik(?:e|ing)|calcium imaging|calcium flux|electrophysiolog\w*|"
            r"oscillation\w*|gamma|theta|field potential\w*|currents?|\bepscs?\b|\bipscs?\b|"
            r"\bmepscs?\b|\bmipscs?\b)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Receptor regulation",
        re.compile(
            r"\b(receptor\w*|transport(?:er|ers)|availability|binding potential|densit(?:y|ies)|"
            r"occupancy|trafficking|surface expression|internalization|uptake site)\b",
            re.IGNORECASE,
        ),
    ),
)


def mechanistic_kind_context(row: dict | None, raw_label: object) -> str:
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
    context_text = mechanistic_kind_context(row, raw_label)
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
    if entity_kind == "safety_adverse_event":
        label = safety_endpoint_label(row)
        return {
            "matched": bool(label),
            "label": label,
            "kind": entity_kind,
            "item": None,
            "status": "entity_normalized" if label else "entity_unmapped",
            "match_type": "safety_endpoint_pattern" if label else "",
            "notes": "safety/adverse-event entity normalized to safety endpoint bucket"
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
        return match_registry_entity(raw, entity_kind, registry, row)
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


OPEN_ACCESS_FIELDS = (
    "open_access_is_oa",
    "open_access_status",
    "open_access_url",
    "unpaywall_is_oa",
    "unpaywall_oa_status",
    "unpaywall_license",
)


def paper_library_lookup(path: Path) -> dict[tuple[str, str], dict]:
    if not path.exists():
        return {}
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    out: dict[tuple[str, str], dict] = {}
    for record in df.to_dict(orient="records"):
        metadata = {field: normalize(record.get(field, "")) for field in OPEN_ACCESS_FIELDS}
        if not any(metadata.values()):
            continue
        doi = normalize_doi(record.get("study_doi", ""))
        if doi:
            out.setdefault(("doi", doi), metadata)
        openalex_id = normalize(record.get("openalex_id", ""))
        if openalex_id:
            out.setdefault(("openalex", openalex_id), metadata)
    return out


def paper_library_lookups(paths: dict[str, Path] | None = None) -> dict[str, dict[tuple[str, str], dict]]:
    paths = paths or DEFAULT_PAPER_LIBRARY_PATHS
    return {dataset: paper_library_lookup(path) for dataset, path in paths.items()}


def enrich_open_access_metadata(row: dict, lookup: dict[tuple[str, str], dict]) -> dict:
    doi = normalize_doi(row.get("study_doi", ""))
    openalex_id = normalize(row.get("openalex_id", ""))
    metadata = lookup.get(("doi", doi)) if doi else None
    if not metadata and openalex_id:
        metadata = lookup.get(("openalex", openalex_id))
    if not metadata:
        return row
    out = dict(row)
    for field, value in metadata.items():
        if value and not normalize(out.get(field, "")):
            out[field] = value
    return out


COMPOUND_BLOCK_STATUSES = {
    "compound_class_not_graphable",
    "compound_combo_not_graphable",
    "compound_graph_scope_not_graphable",
    "compound_reference_not_graphable",
    "compound_unmapped",
}
EMPTY_ENDPOINT_VALUES = {"", "none", "not_applicable", "not applicable", "not_reported", "not reported", "unknown", "uncertain"}
SKIPPED_CLINICAL_GRAPH_ROLES = {"functional_outcome", "patient_reported_outcome"}
SAFETY_ENDPOINT_ROLES = {"safety_or_adverse_event"}
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
        re.compile(r"\b(serotonin syndrome)\b", re.IGNORECASE),
        "Serotonin syndrome",
    ),
    (
        re.compile(r"\b(seizure|convulsion|epilep|grand mal|proconvulsive)\b", re.IGNORECASE),
        "Seizure/convulsion",
    ),
    (re.compile(r"\b(suicid\w*|c[- ]?ssrs)\b", re.IGNORECASE), "Suicidality safety signals"),
    (re.compile(r"\b(mania|manic|hypomania|manic episode|switch|ymrs|young mania)\b", re.IGNORECASE), "Mania/hypomania switch"),
    (
        re.compile(
            r"\b(psychosis|psychotic|psychotomimetic|hallucination|delusion|paranoia|"
            r"bprs|brief psychiatric rating)\b",
            re.IGNORECASE,
        ),
        "Psychosis-like adverse effects",
    ),
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
    (re.compile(r"\b(headache|migraine)\b", re.IGNORECASE), "Headache adverse effects"),
    (
        re.compile(
            r"\b(dissociation|dissociative|derealization|derealisation|depersonalization|depersonalisation|"
            r"\bdp/dr\b|\bddd\b|cadss|clinician-administered dissociative)\b",
            re.IGNORECASE,
        ),
        "Dissociation adverse effects",
    ),
    (
        re.compile(
            r"\b(bad drug effect|bad trip|challenging experience|difficult experience|negative subjective|adverse mental states?|emergence reactions?)\b",
            re.IGNORECASE,
        ),
        "Challenging subjective effects",
    ),
    (re.compile(r"\b(anxiety|panic|distress|fear)\b", re.IGNORECASE), "Anxiety/panic adverse effects"),
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
            r"\b(neuropsychiatric sequelae|neuropsychiatric syndromes?|psychopathology|negative symptoms?|affective flattening)\b",
            re.IGNORECASE,
        ),
        "Neuropsychiatric sequelae",
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
            r"heat shock protein|neuronal injury|synaptic activity|synaptic dysfunction|long[- ]term potentiation|"
            r"psd-95|gamma power|theta power|p20 amplitude|growth cones?|neuronal loss|hippocampal volume|"
            r"spine morphology|prefrontal cortex development|radiotracer accumulation)\b",
            re.IGNORECASE,
        ),
        "Neurotoxicity/cytotoxicity",
    ),
    (
        re.compile(
            r"\b(sedation|sedative|sleepiness|somnolence|drowsiness|cognitive impairment|memory impairment|"
            r"impaired attention|attention impairment|attention deficits?|impaired concentration|"
            r"concentration impairment|motor coordination|ataxia|rotarod|falls?|concussion|dizziness|vertigo|gait|"
            r"tremors?|tremorigenic|locomotor activity|motor activity|impaired memory|memory impairment|"
            r"cognitive function|working memory|executive function|processing speed|moca|hyperactivity|hyperlocomotion|"
            r"locomotion|rearing behavior|rearing events|immobility|exploratory cylinder|response inhibition)\b",
            re.IGNORECASE,
        ),
        "Sedation/cognitive or motor impairment",
    ),
    (
        re.compile(
            r"\b(sleep disturbance|insomnia|night terrors?|sleep quality|sleep impairments?|total sleep time|"
            r"rem sleep|slow[- ]wave sleep|stage 3/4 sleep|sleep architecture|hyperarousal)\b",
            re.IGNORECASE,
        ),
        "Sleep disturbance adverse effects",
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
            r"safety profile|safety/tolerability|safety and tolerability|acceptable safety|no safety concerns?|"
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
        "Unspecified adverse events",
    ),
)
SYMPTOM_ENDPOINT_PATTERNS = (
    (
        re.compile(
            r"\b(suicid|c[- ]?ssrs|columbia suicide|beck scale for suicid|"
            r"madrs item 10|bdi item 9|hamd item 3|ham[- ]?d item 3|hdrs item 3)\b",
            re.IGNORECASE,
        ),
        "Suicidality",
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
        re.compile(r"\b(pain intensity|pain reduction|pain relief|pain interference|post[- ]?operative pain|postoperative pain|headache|migraine|bpi|brief pain|vas|nrs|numeric(?:al)? rating scale|visual analog(?:ue)? scale)\b", re.IGNORECASE),
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
        re.compile(r"\b(psychosis|psychotic|psychotomimetic|schizophrenia[- ]like symptoms?|panss|bprs|catatonia|delusion|paranoia)\b", re.IGNORECASE),
        "Psychotic-like symptoms",
    ),
    (
        re.compile(r"\b(gad[- ]?7|generalized anxiety disorder[- ]?7|ham[- ]?a|hamilton anxiety|stai|state[- ]trait anxiety|hads[- ]?a|anxiety symptoms?|trait anxiety|panic symptoms?)\b", re.IGNORECASE),
        "Anxiety & panic",
    ),
    (
        re.compile(r"\b(madrs|montgomery[- ](?:a|å)sberg|ham[- ]?d|hdrs|hamilton depression|phq[- ]?9|patient health questionnaire[- ]?9|bdi|beck depression|qids|quick inventory of depressive|hads[- ]?d|epds|edinburgh post(?:natal|partum) depression|depressive symptoms?|depression severity|depression symptom)\b", re.IGNORECASE),
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
    base = display_anchor_label(canonical_label)
    base_key = label_key(base)
    if not base:
        return canonical_label
    if base_key == "serotonin":
        receptor_match = re.search(r"\b5[- ]?ht\s*([0-9][a-z]?)\b", folded, flags=re.IGNORECASE)
        if receptor_match:
            base = f"5-HT{receptor_match.group(1).upper()}"
            base_key = label_key(base)
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
        return label_with_suffix(base, "protein levels")
    if READOUT_EXPRESSION_RE.search(folded):
        return label_with_suffix(base, "expression")
    if READOUT_LEVEL_RE.search(folded):
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
    if entity_kind == "biomarker_readout":
        return molecular_readout_display_label(row, canonical_label, raw_label)
    if entity_kind == "pathway_process":
        return pathway_process_display_label(row, canonical_label, raw_label, registry_item)
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


def safety_endpoint_label(row: dict) -> str:
    return pattern_endpoint_label(row, SAFETY_ENDPOINT_PATTERNS, "")


def symptom_endpoint_label(row: dict) -> str:
    return pattern_endpoint_label(row, SYMPTOM_ENDPOINT_PATTERNS, "")


def row_has_safety_physiology(row: dict) -> bool:
    role = normalize(row.get("entity_role", "")).casefold()
    if role != "physiological_measure":
        return False
    text = " ".join(normalize(row.get(field, "")).casefold() for field in ("outcome_type", "outcome_domain", "outcome_measure", "raw_entity_label"))
    return any(term in text for term in SAFETY_PHYSIOLOGY_TERMS)


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

        for scale in split_outcome_scales(row.get("outcome_measure_normalized", "")):
            derived = endpoint_row(
                row,
                audit,
                scale,
                "outcome_scale",
                normalize(row.get("entity_role", "")) or "outcome_measure",
                "outcome_measure_normalized",
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
    if not graphable_compound_match(compound_label_for(row), registry)["matched"]:
        return [row]

    legacy_entity_label = normalize(row.get("target" if domain == "mechanistic" else "disorder", ""))
    legacy_entity_type = "mechanistic_entity" if domain == "mechanistic" else "clinical_entity"
    _, legacy_registry_item = canonicalize_registry_label(legacy_entity_type, legacy_entity_label, registry)
    entity_kind = entity_kind_for(row, domain, legacy_registry_item)
    if entity_kind != "condition_indication":
        return [row]

    raw_entity_label = entity_label_for(row, domain, entity_kind)
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


def rows_for_source(cfg: dict) -> list[dict]:
    rows = load_json_array(Path(cfg["path"]))
    if cfg.get("transform") == "clinical_endpoints":
        audit_path = normalize(cfg.get("audit_path", ""))
        audit_rows = load_json_array(Path(audit_path)) if audit_path else []
        return clinical_endpoint_rows(rows, audit_rows)
    return rows


def should_skip_evidence_row(domain: str, row: dict) -> bool:
    if domain != "clinical":
        return False
    override = normalize(row.get("kg_entity_kind_override", "")).casefold()
    if override:
        return override == "functional_outcome"
    role = normalize(row.get("entity_role", "")).casefold()
    return role in SKIPPED_CLINICAL_GRAPH_ROLES or "functional" in role


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


def mechanistic_entity_kind(row: dict, registry_item: dict | None = None) -> str:
    override = normalize(row.get("kg_entity_kind_override", "")).casefold()
    if override in MECHANISTIC_ENTITY_KIND_OVERRIDES:
        return override
    role = normalize(row.get("entity_role", "")).casefold()
    status = normalize((registry_item or {}).get("status", "")).casefold()
    label = normalize(row.get("target", ""))
    if "family" in status or "system" in status:
        return "system_family"
    if "pathway" in status or "process" in status:
        return "pathway_process"
    if "marker" in status or "readout" in status or "ligand" in status:
        return "biomarker_readout"
    if role == "pathway_or_process":
        return "pathway_process"
    if role == "biomarker":
        return "biomarker_readout"
    if label in MECHANISTIC_BIOMARKER_LABELS:
        return "biomarker_readout"
    return "target"


def clinical_entity_kind(row: dict, registry_item: dict | None = None) -> str:
    override = normalize(row.get("kg_entity_kind_override", "")).casefold()
    if override in {"condition_indication", "symptom_problem", "safety_adverse_event", "outcome_scale"}:
        return override
    role = normalize(row.get("entity_role", "")).casefold()
    status = normalize((registry_item or {}).get("status", "")).casefold()
    label = normalize(row.get("disorder", ""))
    if "safety" in role or "adverse" in role:
        return "safety_adverse_event"
    if "symptom" in status:
        return "symptom_problem"
    if label in ALWAYS_SYMPTOM_LABELS:
        return "symptom_problem"
    if registry_item and status:
        return "condition_indication"
    if role in SYMPTOM_ROLE_VALUES:
        return "symptom_problem"
    if role == "outcome_measure" and label in BROAD_SYMPTOM_OUTCOME_LABELS:
        return "symptom_problem"
    if role == "outcome_scale":
        return "outcome_scale"
    return "condition_indication"


def entity_kind_for(row: dict, domain: str, registry_item: dict | None = None) -> str:
    for field in ("kg_entity_kind_override", "primary_graph_anchor_kind", "graph_candidate_type", "graph_entity_type", "entity_type"):
        kind = normalized_entity_kind(row.get(field, ""))
        if kind in GRAPH_ENTITY_KINDS:
            return kind
    if domain == "mechanistic":
        return mechanistic_entity_kind(row, registry_item)
    if domain == "clinical":
        return clinical_entity_kind(row, registry_item)
    domain_key = normalize(domain).casefold()
    return DOMAIN_DEFAULT_ENTITY_KIND.get(domain_key, "condition_indication")


def entity_type_for_kind(entity_kind: str, domain: str) -> str:
    if entity_kind in ENTITY_TYPE_BY_KIND:
        return ENTITY_TYPE_BY_KIND[entity_kind]
    if domain == "mechanistic":
        return "mechanistic_entity"
    if domain == "clinical":
        return "clinical_entity"
    return f"{slug(domain, 'domain')}_entity"


def entity_label_for(row: dict, domain: str, entity_kind: str) -> str:
    explicit_label = first_normalized_value(row, ("graph_entity_label", "entity_label"))
    if explicit_label:
        return explicit_label
    fields = ENTITY_LABEL_FIELDS_BY_KIND.get(entity_kind, ())
    label = first_normalized_value(row, fields)
    if label:
        return label
    if domain == "mechanistic":
        return normalize(row.get("target", ""))
    if domain == "clinical":
        return normalize(row.get("disorder", ""))
    return first_normalized_value(row, ("graph_entity_label", "entity_label", "entity", "target", "disorder"))


def relation_type_for(domain: str, entity_kind: str, evidence_type: str) -> str:
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
    if entity_kind == "cognitive_behavioral_construct" or domain in {"cognitive_behavioral", "behavioral"}:
        return "has_cognitive_behavioral_effect"
    if entity_kind == "subjective_experience_construct" or domain == "subjective_experience":
        return "has_subjective_experience_effect"
    if entity_kind == "pharmacokinetic_parameter" or domain in {"pharmacokinetics_exposure", "exposure"}:
        return "has_pharmacokinetic_exposure"
    if entity_kind == "intervention_component" or domain in {"intervention_context", "intervention"}:
        return "uses_intervention_component"
    if entity_kind == "public_health_measure" or domain in {"real_world_public_health", "public_health"}:
        return "has_public_health_evidence"
    if domain in {"mechanistic", "molecular_target", "molecular_pathway_readout"}:
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


def public_health_graph_label(row: dict) -> str:
    explicit_label = first_endpoint_value(row, ("public_health_graph_label", "public_health_topic_category"))
    if explicit_label in PUBLIC_HEALTH_TOPIC_LABELS:
        return explicit_label
    context = ascii_fold(" ".join(normalize(row.get(field, "")) for field in PUBLIC_HEALTH_CONTEXT_FIELDS))
    if not normalize(context):
        return "Prevalence & trends"
    for label, pattern in PUBLIC_HEALTH_TOPIC_RULES:
        if pattern.search(context):
            return label
    return "Prevalence & trends"


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


def cognitive_behavioral_graph_label(row: dict) -> str:
    explicit_label = first_endpoint_value(row, ("cognitive_behavioral_graph_label", "graph_construct_label"))
    explicit_key = label_key(explicit_label)
    if explicit_key in COGNITIVE_BEHAVIORAL_LABEL_FALLBACKS:
        return COGNITIVE_BEHAVIORAL_LABEL_FALLBACKS[explicit_key]
    if explicit_label:
        return explicit_label

    measure_context = ascii_fold(" ".join(normalize(row.get(field, "")) for field in COGNITIVE_BEHAVIORAL_MEASURE_FIELDS))
    for label, pattern in COGNITIVE_BEHAVIORAL_RULES:
        if pattern.search(measure_context):
            return label

    explicit_label = first_normalized_value(row, COGNITIVE_BEHAVIORAL_LABEL_FIELDS)
    explicit_key = label_key(explicit_label)
    if measure_context and GENERIC_LOCOMOTOR_CONTEXT_RE.search(measure_context):
        return first_normalized_value(row, COGNITIVE_BEHAVIORAL_MEASURE_FIELDS) or explicit_label
    if explicit_key in COGNITIVE_BEHAVIORAL_LABEL_FALLBACKS:
        return COGNITIVE_BEHAVIORAL_LABEL_FALLBACKS[explicit_key]

    label_context = ascii_fold(" ".join(normalize(row.get(field, "")) for field in COGNITIVE_BEHAVIORAL_LABEL_FIELDS))
    for label, pattern in COGNITIVE_BEHAVIORAL_RULES:
        if pattern.search(label_context):
            return label

    context = ascii_fold(" ".join(normalize(row.get(field, "")) for field in COGNITIVE_BEHAVIORAL_CONTEXT_FIELDS))
    for label, pattern in COGNITIVE_BEHAVIORAL_RULES:
        if pattern.search(context):
            return label
    return explicit_label


def subjective_experience_graph_label(row: dict) -> str:
    context = ascii_fold(" ".join(normalize(row.get(field, "")) for field in SUBJECTIVE_EXPERIENCE_CONTEXT_FIELDS))
    for label, pattern in SUBJECTIVE_EXPERIENCE_RULES:
        if pattern.search(context):
            return label

    explicit_label = first_normalized_value(row, ("graph_entity_label", "entity_label", "subjective_construct", "subjective_construct_category", "instrument_or_measure"))
    explicit_key = label_key(explicit_label)
    if explicit_key in SUBJECTIVE_EXPERIENCE_LABEL_FALLBACKS:
        return SUBJECTIVE_EXPERIENCE_LABEL_FALLBACKS[explicit_key]
    return explicit_label


def molecular_effect_label(row: dict, entity_kind: str, entity_label: str) -> str:
    if normalize(entity_kind).casefold() not in MOLECULAR_EFFECT_ENTITY_KINDS:
        return ""
    explicit_label = first_endpoint_value(row, ("molecular_effect_label", "molecular_effect_category"))
    if explicit_label:
        return explicit_label

    def effect_from_context(fields: tuple[str, ...]) -> str:
        context = ascii_fold(
            " ".join(
                normalize(value)
                for value in (
                    entity_label,
                    *(row.get(field, "") for field in fields),
                )
            )
        )
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
    return "Other molecular effects"


def subjective_experience_safety_label(row: dict) -> str:
    context = ascii_fold(" ".join(normalize(row.get(field, "")) for field in SUBJECTIVE_EXPERIENCE_SAFETY_CONTEXT_FIELDS))
    if SUBJECTIVE_EXPERIENCE_NONADVERSE_RE.search(context):
        return ""
    if not SUBJECTIVE_EXPERIENCE_SAFETY_RE.search(context):
        return ""
    return safety_endpoint_label(row) or "Neuropsychiatric sequelae"


def entity_row(entity_id: str, entity_type: str, domain: str, label: str, kind: str, registry_item: dict | None) -> dict:
    registry_item = registry_item or {}
    return {
        "entity_id": entity_id,
        "entity_type": entity_type,
        "domain": domain,
        "entity_kind": kind,
        "label": label,
        "registry_status": normalize(registry_item.get("status", "")),
        "aliases_json": json_dumps(registry_item.get("aliases", [])),
        "ids_json": json_dumps(registry_item.get("ids", {})),
    }


def normalize_claim_metadata(row: dict, domain: str) -> dict:
    out = dict(row)
    if domain == "pharmacokinetics_exposure":
        out["domain"] = domain
        out = add_pk_relationship_fields(out)
    if domain == "real_world_public_health":
        out["domain"] = domain
        out["public_health_graph_label"] = public_health_graph_label(out)
        out["graph_entity_label"] = out["public_health_graph_label"]
    if domain == "cognitive_behavioral":
        out["domain"] = domain
        withdrawal_condition = withdrawal_condition_label(out)
        if withdrawal_condition:
            out["kg_entity_kind_override"] = "condition_indication"
            out["endpoint_label_source"] = "behavioral_withdrawal_condition_boundary"
            out["graph_entity_label"] = withdrawal_condition
        else:
            out["cognitive_behavioral_graph_label"] = first_endpoint_value(
                out,
                ("cognitive_behavioral_graph_label", "graph_construct_label"),
            ) or cognitive_behavioral_graph_label(out)
            if out["cognitive_behavioral_graph_label"]:
                out["graph_entity_label"] = out["cognitive_behavioral_graph_label"]
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
    if domain in MECHANISTIC_METADATA_DOMAINS and not normalize(out.get("assay_family_normalized", "")):
        out["assay_family_normalized"] = normalize_mechanistic_assay_family(
            out.get("assay_family", ""),
            out.get("assay_type", ""),
        )
    if domain in MECHANISTIC_METADATA_DOMAINS:
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
    entity_kind = entity_kind_for(row, domain)
    entity_label = entity_label_for(row, domain, entity_kind)
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
    entity_label = entity_label_for(row, domain, entity_kind)
    relation_type = relation_type_for(domain, entity_kind, evidence_type)
    return {
        "evidence_id": evidence_id,
        id_field: finding_id,
        "source_name": source_name,
        "domain": domain,
        "dataset": dataset,
        "entity_kind": entity_kind,
        "evidence_type": evidence_type,
        "relation_type": relation_type,
        "compound_id": compound_id,
        "compound": compound_label_for(row),
        "entity_id": entity_id,
        "entity_label": entity_label,
        "paper_id": paper_id,
        "study_doi": normalize_doi(row.get("study_doi", "")),
        "study_year": as_int_or_none(row.get("study_year", "")),
        "direction": normalize(row.get("result_direction", "")),
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
    source_preset: str = "current",
    run_id: str = "",
    registry_path: Path = DEFAULT_REGISTRY_PATH,
    node_vocabulary_path: Path = DEFAULT_NODE_VOCABULARY_PATH,
    out_dir: Path = DEFAULT_OUT_DIR,
    write_duckdb: bool = True,
) -> dict:
    if graph_sources is None:
        graph_sources = graph_sources_for_preset(source_preset, run_id=run_id)
        manifest_source_preset = source_preset
    else:
        manifest_source_preset = "custom"
    registry = registry_lookup(registry_path)
    node_vocabulary = node_vocabulary_lookup(node_vocabulary_path)
    access_lookups = paper_library_lookups()
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
            rows.extend(condition_expanded_rows(normalized_source_row, source_row_domain, registry))

        for index, row in enumerate(rows):
            domain = normalize(row.get("domain", "")) or normalize(row.get("domain_route", "")) or source_domain
            dataset = normalize(row.get("dataset", "")) or domain or source_dataset
            access_lookup = access_lookups.get(dataset, {})
            row = enrich_open_access_metadata(row, access_lookup)
            row = normalize_claim_metadata(row, domain)
            if should_skip_evidence_row(domain, row):
                continue

            compound_label_raw = compound_label_for(row)
            compound_match = graphable_compound_match(compound_label_raw, registry)
            if not compound_match["matched"]:
                audit_source_row = dict(row)
                audit_source_row["normalization_status"] = compound_match["status"]
                audit_source_row["normalization_notes"] = compound_match["notes"]
                audit_source_row["compound_original"] = compound_label_raw
                audits.append(audit_row(audit_source_row, source_name, domain, dataset))
                continue

            paper_id = paper_id_for(row)
            papers.setdefault(paper_id, paper_row(row, paper_id))

            compound_label = compound_match["label"]
            compound_registry = compound_match["item"]
            compound_id = entity_id_for("compound", compound_label)
            entities.setdefault(
                compound_id,
                entity_row(compound_id, "compound", "compound", compound_label, "compound", compound_registry),
            )

            legacy_entity_label = normalize(row.get("target" if domain == "mechanistic" else "disorder", ""))
            legacy_entity_type = "mechanistic_entity" if domain == "mechanistic" else "clinical_entity"
            _, legacy_registry_item = canonicalize_registry_label(legacy_entity_type, legacy_entity_label, registry)
            entity_kind = entity_kind_for(row, domain, legacy_registry_item)
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
            if entity_kind == "symptom_problem":
                entity_label = symptom_problem_display_label(entity_label)
            display_label_note = ""
            if entity_label != canonical_entity_label:
                display_label_note = f"; display label refined from `{canonical_entity_label}`"
            pk_display_label = pharmacokinetic_display_label(row, domain, entity_kind, entity_label, node_vocabulary)
            entity_type = entity_type_for_kind(entity_kind, domain)
            entity_id = entity_id_for(entity_type, entity_label)
            entities.setdefault(entity_id, entity_row(entity_id, entity_type, domain, entity_label, entity_kind, registry_item))
            table_row = dict(row)
            table_row["compound_original"] = compound_label_raw
            table_row["compound"] = compound_label
            table_row["canonical_compound"] = compound_label
            table_row["compound_match_type"] = compound_match["match_type"]
            table_row["compound_registry_status"] = normalize((compound_registry or {}).get("status", ""))
            table_row["normalization_status"] = "normalized"
            table_row["normalization_notes"] = f"{compound_match['notes']}; {entity_match['notes']}{display_label_note}"
            table_row["graph_entity_original"] = raw_entity_label
            table_row["graph_entity_label"] = entity_label
            table_row["canonical_entity"] = entity_label
            table_row["molecular_effect_label"] = molecular_effect_label(table_row, entity_kind, entity_label)
            table_row["pharmacokinetic_display_label"] = pk_display_label
            table_row["entity_match_type"] = entity_match["match_type"]
            table_row["entity_registry_status"] = normalize((registry_item or {}).get("status", ""))
            table_row["kg_entity_kind_override"] = entity_kind

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

        if not cfg.get("skip_audit", False):
            audit_path = Path(cfg.get("audit_path", ""))
            for row in load_json_array(audit_path):
                audits.append(audit_row(row, source_name, domain, dataset))

    tables = {
        "papers": dataframe(list(papers.values())),
        "entities": dataframe(list(entities.values())),
        finding_table_name: dataframe(findings),
        "evidence_edges": dataframe(evidence_edges),
        "normalization_audit": dataframe(audits),
    }

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
        "generated_at": now_utc(),
        "out_dir": str(out_dir),
        "source_preset": manifest_source_preset,
        "run_id": safe_run_id(run_id),
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
    parser.add_argument("--out-dir", type=Path, default=None)
    parser.add_argument(
        "--allow-current-overwrite",
        action="store_true",
        help="Allow non-current source presets to write directly to data/processed/kg.",
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
    if (
        args.source_preset != "current"
        and out_dir.resolve() == DEFAULT_OUT_DIR.resolve()
        and not args.allow_current_overwrite
    ):
        raise SystemExit(
            "Refusing to write routed/combined sources directly to data/processed/kg. "
            "Use --run-id for a versioned build, or add --allow-current-overwrite if this is an intentional promotion."
        )
    if (
        args.source_preset != "current"
        and out_dir.resolve() == DEFAULT_OUT_DIR.resolve()
        and not run_id
    ):
        raise SystemExit("Promoting routed/combined sources to data/processed/kg requires --run-id.")
    manifest = build_tables(
        source_preset=args.source_preset,
        run_id=run_id,
        registry_path=args.registry,
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
