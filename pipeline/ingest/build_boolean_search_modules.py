#!/usr/bin/env python3
"""Build provider-specific grouped search modules for literature discovery."""

from __future__ import annotations

import argparse
from collections import Counter
import csv
import datetime as dt
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RUN_ID = "literature_search"
SEARCH_STRATEGY_ROOT = ROOT / "data" / "raw" / "search_strategies"
VERSION = "0.1"

RECOMMENDED_CAPS = {
    "openalex": {
        "primary_boolean": 500,
        "dense_topic": 1000,
    },
    "pubmed": {
        "primary_boolean": 500,
        "dense_topic": 1000,
    },
}


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def quote_term(term: str) -> str:
    text = term.strip()
    if not text:
        return ""
    if any(char.isspace() for char in text) or any(char in text for char in "-,/"):
        escaped = text.replace('"', '\\"')
        return f'"{escaped}"'
    return text


def boolean_block(terms: list[str]) -> str:
    values = [quote_term(term) for term in terms if term.strip()]
    values = list(dict.fromkeys(values))
    if not values:
        return ""
    if len(values) == 1:
        return values[0]
    return "(" + " OR ".join(values) + ")"


def openalex_query(*blocks: list[str]) -> str:
    rendered = [boolean_block(block) for block in blocks if block]
    return " AND ".join(block for block in rendered if block)


def pubmed_term(term: str) -> str:
    quoted = quote_term(term)
    return f"{quoted}[Title/Abstract]" if quoted else ""


def pubmed_block(terms: list[str]) -> str:
    values = [pubmed_term(term) for term in terms if term.strip()]
    values = list(dict.fromkeys(values))
    if not values:
        return ""
    if len(values) == 1:
        return values[0]
    return "(" + " OR ".join(values) + ")"


def pubmed_query(*blocks: list[str], human_filter: bool = False) -> str:
    rendered = [pubmed_block(block) for block in blocks if block]
    query = " AND ".join(block for block in rendered if block)
    if human_filter:
        query = f"{query} NOT (animals[MeSH Terms] NOT humans[MeSH Terms])"
    return query


THERAPEUTIC_CORE = [
    "psychedelic",
    "psychedelics",
    "psychedelic-assisted therapy",
    "hallucinogen",
    "psychoplastogen",
    "psilocybin",
    "psilocin",
    "LSD",
    "lysergic acid diethylamide",
    "MDMA",
    "3,4-methylenedioxymethamphetamine",
    "ketamine",
    "esketamine",
    "ayahuasca",
    "DMT",
    "5-MeO-DMT",
    "mescaline",
    "ibogaine",
]

CLASSIC_PSYCH_CORE = [
    "psychedelic",
    "psychedelics",
    "serotonergic psychedelic",
    "hallucinogen",
    "psychoplastogen",
    "LSD",
    "lysergic acid diethylamide",
    "psilocybin",
    "psilocin",
    "DMT",
    "5-MeO-DMT",
    "mescaline",
    "DOI",
    "2C-B",
    "NBOMe",
]

CLINICAL_EVIDENCE = [
    "clinical trial",
    "randomized",
    "randomised",
    "placebo",
    "open-label",
    "open label",
    "phase 2",
    "phase 3",
    "treatment",
    "therapy",
    "efficacy",
    "safety",
    "tolerability",
    "outcome",
    "follow-up",
]

MECHANISTIC_EVIDENCE = [
    "binding",
    "affinity",
    "Ki",
    "Kd",
    "IC50",
    "EC50",
    "radioligand",
    "functional assay",
    "agonist",
    "antagonist",
    "partial agonist",
    "signaling",
]

SYSTEMS_NEUROIMAGING_TERMS = [
    "fMRI",
    "functional MRI",
    "BOLD",
    "resting-state",
    "resting state",
    "neuroimaging",
    "functional connectivity",
    "effective connectivity",
    "dynamic connectivity",
    "connectome",
]

SYSTEMS_NETWORK_TERMS = [
    "default mode network",
    "DMN",
    "salience network",
    "frontoparietal network",
    "central executive network",
    "limbic network",
    "visual network",
    "sensorimotor network",
    "global brain connectivity",
    "network integrity",
    "network modularity",
    "desynchronization",
    "desynchronisation",
]

SYSTEMS_REGION_TERMS = [
    "prefrontal cortex",
    "medial prefrontal cortex",
    "mPFC",
    "orbitofrontal cortex",
    "anterior cingulate cortex",
    "posterior cingulate cortex",
    "hippocampus",
    "amygdala",
    "thalamus",
    "claustrum",
    "striatum",
    "nucleus accumbens",
    "dorsal raphe nucleus",
    "insula",
]

SYSTEMS_CIRCUIT_TERMS = [
    "brain region",
    "brain circuit",
    "circuit",
    "thalamo-cortical",
    "thalamocortical",
    "cortico-striatal",
    "corticostriatal",
    "cortical-subcortical",
    "fronto-limbic",
    "corticolimbic",
    "hippocampal-prefrontal",
    "amygdala-prefrontal",
    "mesolimbic",
    "reward circuit",
]

PET_OCCUPANCY_TERMS = [
    "PET",
    "positron emission tomography",
    "receptor occupancy",
    "occupancy",
    "radioligand",
    "FDG",
    "glucose metabolism",
    "cerebral blood flow",
    "arterial spin labeling",
    "CBF",
]

EEG_MEG_NEUROPHYS_TERMS = [
    "EEG",
    "MEG",
    "electroencephalography",
    "magnetoencephalography",
    "neural oscillations",
    "oscillatory",
    "event-related potential",
    "ERP",
    "gamma",
    "theta",
    "alpha",
    "signal diversity",
    "entropy",
    "Lempel-Ziv",
    "electrophysiology",
]

COGNITIVE_AFFECTIVE_TASK_TERMS = [
    "cognitive flexibility",
    "reversal learning",
    "probabilistic reversal learning",
    "set shifting",
    "attentional set shifting",
    "fear conditioning",
    "fear extinction",
    "extinction learning",
    "reward learning",
    "reinforcement learning",
    "emotional processing",
    "emotion recognition",
    "social cognition",
    "social reward learning",
    "attention",
    "impulsivity",
    "prepulse inhibition",
]

TRANSLATIONAL_BEHAVIOR_TERMS = [
    "forced swim test",
    "tail suspension test",
    "learned helplessness",
    "chronic social defeat",
    "open field",
    "elevated plus maze",
    "sucrose preference",
    "conditioned place preference",
    "self-administration",
    "drug seeking",
    "conditioned freezing",
]

TASK_EVIDENCE_TERMS = [
    "task",
    "behavior",
    "behaviour",
    "behavioral",
    "behavioural",
    "performance",
    "learning",
    "conditioning",
    "response",
    "paradigm",
]

PRECLINICAL_EVIDENCE_TERMS = [
    "mouse",
    "mice",
    "rat",
    "rodent",
    "animal model",
    "behavioral assay",
    "behavioural assay",
    "in vivo",
    "neuronal activity",
    "c-Fos",
]

MOLECULAR_PATHWAY_TERMS = [
    "BDNF",
    "TrkB",
    "NTRK2",
    "mTOR",
    "ERK",
    "MAPK",
    "CREB",
    "Akt",
    "synaptogenesis",
    "synaptic plasticity",
    "dendritic spine",
    "spine density",
    "neuritogenesis",
    "neuroplasticity",
    "c-Fos",
    "Fos",
    "Arc",
    "immediate early gene",
    "gene expression",
    "transcriptomic",
    "transcriptome",
    "epigenetic",
    "cytokine",
    "inflammation",
    "inflammatory",
    "cortisol",
    "HPA axis",
    "neuroendocrine",
]

PATHWAY_EVIDENCE_TERMS = [
    "signaling",
    "phosphorylation",
    "expression",
    "protein expression",
    "gene expression",
    "transcriptomics",
    "western blot",
    "qPCR",
    "RNA-seq",
    "immunohistochemistry",
    "ELISA",
    "biomarker",
    "plasticity",
    "synaptic",
    "neuronal",
]

CLINICAL_FUNCTION_SYMPTOM_TERMS = [
    "suicidal ideation",
    "suicidality",
    "anhedonia",
    "craving",
    "withdrawal",
    "relapse",
    "sleep",
    "insomnia",
    "pain intensity",
    "quality of life",
    "wellbeing",
    "well-being",
    "social functioning",
    "occupational functioning",
    "functional impairment",
    "emotional functioning",
    "distress",
]

CLINICAL_FUNCTION_EVIDENCE_TERMS = [
    "clinical trial",
    "randomized",
    "randomised",
    "placebo",
    "open-label",
    "open label",
    "treatment",
    "therapy",
    "outcome",
    "scale",
    "score",
    "follow-up",
    "response",
    "remission",
]

CLINICAL_SAFETY_TERMS = [
    "safety",
    "tolerability",
    "adverse event",
    "adverse events",
    "serious adverse event",
    "side effect",
    "cardiovascular",
    "blood pressure",
    "heart rate",
    "hypertension",
    "mania",
    "psychosis",
    "dissociation",
    "HPPD",
    "hallucinogen persisting perception disorder",
    "flashback",
]

CLINICAL_BRIDGE_TERMS = [
    "depression",
    "major depressive disorder",
    "treatment-resistant depression",
    "PTSD",
    "post-traumatic stress disorder",
    "anxiety",
    "substance use disorder",
    "addiction",
    "alcohol use disorder",
    "opioid use disorder",
    "craving",
    "suicidal ideation",
    "anhedonia",
    "quality of life",
    "patient",
    "patients",
    "clinical outcome",
]

MECHANISM_BRIDGE_TERMS = [
    "fMRI",
    "BOLD",
    "functional connectivity",
    "default mode network",
    "DMN",
    "amygdala",
    "prefrontal cortex",
    "PET",
    "receptor occupancy",
    "EEG",
    "neural oscillations",
    "cognitive task",
    "cognitive flexibility",
    "emotional processing",
    "BDNF",
    "cortisol",
    "cytokine",
    "biomarker",
]

SUBJECTIVE_EXPERIENCE_TERMS = [
    "subjective effects",
    "acute subjective effects",
    "psychedelic experience",
    "subjective drug effects",
    "phenomenology",
    "phenomenological",
    "mystical experience",
    "mystical-type experience",
    "ego dissolution",
    "ego loss",
    "altered state",
    "altered states of consciousness",
    "oceanic boundlessness",
    "visual effects",
    "perceptual effects",
    "hallucinations",
    "hallucinatory effects",
    "emotional breakthrough",
    "challenging experience",
    "anxiety during session",
    "peak experience",
    "psychological insight",
    "self-dissolution",
    "self-transcendence",
    "connectedness",
    "awe",
]

SUBJECTIVE_EXPERIENCE_MEASURE_TERMS = [
    "questionnaire",
    "scale",
    "rating",
    "psychometric",
    "5D-ASC",
    "11D-ASC",
    "5D-OAV",
    "OAV",
    "APZ",
    "ASC",
    "MEQ",
    "MEQ-30",
    "MEQ30",
    "Mystical Experience Questionnaire",
    "Drug Effects Questionnaire",
    "DEQ",
    "Ego-Dissolution Inventory",
    "EDI",
    "Emotional Breakthrough Inventory",
    "EBI",
    "Hallucinogen Rating Scale",
    "HRS",
    "Challenging Experience Questionnaire",
    "CEQ",
    "Psychological Insight Questionnaire",
    "PIQ",
    "Persisting Effects Questionnaire",
    "PEQ",
    "visual analog scale",
    "VAS",
    "acute effects",
]

PHARMACOKINETICS_EXPOSURE_TERMS = [
    "pharmacokinetics",
    "pharmacokinetic",
    "pharmacodynamics",
    "pharmacodynamic",
    "PK/PD",
    "pharmacokinetic-pharmacodynamic",
    "metabolism",
    "metabolite",
    "plasma concentration",
    "serum concentration",
    "blood concentration",
    "plasma level",
    "serum level",
    "blood level",
    "concentration-time",
    "ADME",
    "absorption",
    "distribution",
    "elimination",
    "excretion",
    "urinary excretion",
    "Cmax",
    "Tmax",
    "AUC",
    "half-life",
    "bioavailability",
    "clearance",
    "exposure-response",
    "dose-response",
    "route of administration",
]

PHARMACOKINETICS_EVIDENCE_TERMS = [
    "dose",
    "dosing",
    "administration",
    "concentration",
    "time course",
    "sampling",
    "LC-MS",
    "LC-MS/MS",
    "mass spectrometry",
    "CYP2D6",
    "cytochrome P450",
    "UGT",
    "glucuronidation",
    "glucuronide",
    "MAO-A",
    "monoamine oxidase",
    "protein binding",
    "clinical",
    "human",
    "animal",
]

INTERVENTION_CONTEXT_TERMS = [
    "psychotherapy",
    "preparation",
    "preparation session",
    "integration",
    "integration session",
    "preparation and integration",
    "aftercare",
    "set and setting",
    "set setting",
    "therapeutic alliance",
    "therapeutic relationship",
    "therapist",
    "psychological support",
    "music",
    "music playlist",
    "dosing session",
    "facilitator",
    "manualized therapy",
    "treatment manual",
    "therapist training",
    "facilitator training",
    "supportive therapy",
    "integration therapy",
    "group therapy",
    "expectancy",
    "intention",
    "inner-directed",
    "nondirective support",
    "non-directive support",
    "eyeshades",
    "eye shades",
    "blinding",
]

INTERVENTION_CONTEXT_EVIDENCE_TERMS = [
    "clinical trial",
    "treatment",
    "therapy",
    "protocol",
    "session",
    "outcome",
    "acceptability",
    "feasibility",
    "qualitative",
    "participant",
    "patient",
    "clinical",
]

REAL_WORLD_PUBLIC_HEALTH_TERMS = [
    "epidemiology",
    "prevalence",
    "survey",
    "population",
    "naturalistic",
    "real-world",
    "real world",
    "recreational use",
    "nonmedical use",
    "drug checking",
    "poison center",
    "poison control",
    "emergency department",
    "emergency room",
    "ED visit",
    "harm reduction",
    "public health",
    "community",
    "ceremonial",
    "retreat",
    "microdosing",
    "microdose",
    "self-medication",
    "lifetime use",
    "past-year use",
    "use patterns",
    "non-medical use",
    "adverse experiences",
    "toxicity",
    "hospitalization",
    "misuse",
    "diversion",
]

REAL_WORLD_PUBLIC_HEALTH_EVIDENCE_TERMS = [
    "use",
    "users",
    "risk",
    "adverse",
    "patterns",
    "correlates",
    "longitudinal",
    "cohort",
    "survey",
    "population",
    "outcomes",
    "wellbeing",
    "mental health",
    "harm reduction",
    "observational",
]

DISORDER_MODULES = [
    {
        "module_id": "clinical_class_core",
        "module_type": "primary_boolean",
        "compound_terms": THERAPEUTIC_CORE,
        "entity_terms": [
            "depression",
            "anxiety",
            "post-traumatic stress disorder",
            "PTSD",
            "substance use disorder",
            "addiction",
            "obsessive-compulsive disorder",
            "OCD",
            "eating disorder",
            "cluster headache",
            "migraine",
            "chronic pain",
        ],
        "evidence_terms": CLINICAL_EVIDENCE,
    },
    {
        "module_id": "depression_spectrum",
        "module_type": "primary_boolean",
        "compound_terms": THERAPEUTIC_CORE,
        "entity_terms": [
            "depression",
            "major depressive disorder",
            "MDD",
            "treatment-resistant depression",
            "TRD",
            "bipolar depression",
            "persistent depressive disorder",
            "dysthymia",
        ],
        "evidence_terms": CLINICAL_EVIDENCE,
    },
    {
        "module_id": "trauma_ptsd",
        "module_type": "primary_boolean",
        "compound_terms": ["MDMA", "3,4-methylenedioxymethamphetamine", "psilocybin", "ketamine", "psychedelic-assisted therapy"],
        "entity_terms": ["PTSD", "post-traumatic stress disorder", "posttraumatic stress disorder", "trauma"],
        "evidence_terms": ["clinical trial", "randomized", "placebo", "therapy", "psychotherapy", "safety", "follow-up", "outcome"],
    },
    {
        "module_id": "substance_use_addiction",
        "module_type": "primary_boolean",
        "compound_terms": ["psilocybin", "LSD", "ketamine", "ibogaine", "noribogaine", "ayahuasca", "psychedelic"],
        "entity_terms": [
            "substance use disorder",
            "addiction",
            "dependence",
            "alcohol use disorder",
            "tobacco use disorder",
            "smoking cessation",
            "opioid use disorder",
            "cocaine use disorder",
            "methamphetamine use disorder",
        ],
        "evidence_terms": ["clinical trial", "treatment", "abstinence", "cessation", "craving", "relapse", "safety", "outcome"],
    },
    {
        "module_id": "anxiety_distress_palliative",
        "module_type": "primary_boolean",
        "compound_terms": ["psilocybin", "LSD", "MDMA", "ketamine", "ayahuasca", "psychedelic-assisted therapy"],
        "entity_terms": [
            "anxiety",
            "generalized anxiety disorder",
            "social anxiety disorder",
            "cancer anxiety",
            "cancer depression",
            "life-threatening disease",
            "end-of-life",
            "existential distress",
            "demoralization",
            "palliative",
        ],
        "evidence_terms": CLINICAL_EVIDENCE,
    },
    {
        "module_id": "pain_headache",
        "module_type": "primary_boolean",
        "compound_terms": ["LSD", "psilocybin", "ketamine", "psychedelic"],
        "entity_terms": ["cluster headache", "migraine", "headache", "chronic pain", "fibromyalgia"],
        "evidence_terms": ["clinical trial", "treatment", "pain", "attack frequency", "analgesia", "efficacy", "safety", "outcome"],
    },
    {
        "module_id": "ocd_eating_autism",
        "module_type": "primary_boolean",
        "compound_terms": ["psilocybin", "LSD", "MDMA", "ketamine", "ayahuasca", "psychedelic"],
        "entity_terms": [
            "obsessive-compulsive disorder",
            "OCD",
            "eating disorder",
            "anorexia nervosa",
            "bulimia nervosa",
            "binge-eating disorder",
            "autism spectrum disorder",
            "autism",
        ],
        "evidence_terms": CLINICAL_EVIDENCE,
    },
    {
        "module_id": "symptoms_functioning_quality_of_life",
        "module_type": "primary_boolean",
        "module_scope": "clinical_symptom_function",
        "compound_terms": THERAPEUTIC_CORE,
        "entity_terms": CLINICAL_FUNCTION_SYMPTOM_TERMS,
        "evidence_terms": CLINICAL_FUNCTION_EVIDENCE_TERMS,
    },
    {
        "module_id": "safety_tolerability_adverse_events",
        "module_type": "primary_boolean",
        "module_scope": "clinical_safety",
        "compound_terms": THERAPEUTIC_CORE,
        "entity_terms": CLINICAL_SAFETY_TERMS,
        "evidence_terms": ["clinical", "trial", "observational", "case report", "adverse event", "tolerability", "safety", "follow-up"],
    },
    {
        "module_id": "clinical_outcome_mechanism_bridge",
        "module_type": "primary_boolean",
        "module_scope": "bridge_clinical_mechanism",
        "compound_terms": THERAPEUTIC_CORE,
        "entity_terms": CLINICAL_BRIDGE_TERMS,
        "evidence_terms": MECHANISM_BRIDGE_TERMS,
    },
    {
        "module_id": "intervention_context_psychotherapy",
        "module_type": "primary_boolean",
        "module_scope": "intervention_context",
        "compound_terms": THERAPEUTIC_CORE
        + ["psychedelic-assisted psychotherapy", "MDMA-assisted psychotherapy", "psilocybin-assisted therapy"],
        "entity_terms": INTERVENTION_CONTEXT_TERMS,
        "evidence_terms": INTERVENTION_CONTEXT_EVIDENCE_TERMS,
    },
    {
        "module_id": "real_world_use_public_health",
        "module_type": "primary_boolean",
        "module_scope": "real_world_use_public_health",
        "compound_terms": ["psychedelic", "psychedelics", "psilocybin", "LSD", "MDMA", "ketamine", "ayahuasca", "ibogaine", "DMT"],
        "entity_terms": REAL_WORLD_PUBLIC_HEALTH_TERMS,
        "evidence_terms": REAL_WORLD_PUBLIC_HEALTH_EVIDENCE_TERMS,
    },
    {
        "module_id": "psilocybin_depression",
        "module_type": "dense_topic",
        "compound_terms": ["psilocybin", "psilocin"],
        "entity_terms": ["depression", "major depressive disorder", "MDD", "treatment-resistant depression", "TRD"],
        "evidence_terms": CLINICAL_EVIDENCE,
    },
    {
        "module_id": "mdma_ptsd",
        "module_type": "dense_topic",
        "compound_terms": ["MDMA", "3,4-methylenedioxymethamphetamine"],
        "entity_terms": ["PTSD", "post-traumatic stress disorder", "posttraumatic stress disorder"],
        "evidence_terms": ["clinical trial", "randomized", "placebo", "psychotherapy", "assisted therapy", "safety", "follow-up"],
    },
    {
        "module_id": "ketamine_depression_suicidality",
        "module_type": "dense_topic",
        "compound_terms": ["ketamine", "esketamine", "arketamine", "S-ketamine", "R-ketamine"],
        "entity_terms": ["depression", "treatment-resistant depression", "TRD", "suicidal ideation", "suicidality", "bipolar depression"],
        "evidence_terms": CLINICAL_EVIDENCE,
    },
    {
        "module_id": "ibogaine_opioid_sud",
        "module_type": "dense_topic",
        "compound_terms": ["ibogaine", "noribogaine"],
        "entity_terms": ["opioid use disorder", "opioid dependence", "substance use disorder", "addiction"],
        "evidence_terms": ["treatment", "detoxification", "withdrawal", "craving", "abstinence", "safety", "clinical"],
    },
    {
        "module_id": "lsd_alcohol_anxiety",
        "module_type": "dense_topic",
        "compound_terms": ["LSD", "lysergic acid diethylamide"],
        "entity_terms": ["alcohol use disorder", "alcohol dependence", "anxiety", "life-threatening disease"],
        "evidence_terms": CLINICAL_EVIDENCE,
    },
    {
        "module_id": "suicidality_anhedonia_sleep_function",
        "module_type": "dense_topic",
        "module_scope": "clinical_symptom_function",
        "compound_terms": ["psilocybin", "ketamine", "esketamine", "MDMA", "ayahuasca", "psychedelic"],
        "entity_terms": ["suicidal ideation", "suicidality", "anhedonia", "sleep", "insomnia", "quality of life", "functioning"],
        "evidence_terms": CLINICAL_FUNCTION_EVIDENCE_TERMS,
    },
    {
        "module_id": "craving_relapse_functioning",
        "module_type": "dense_topic",
        "module_scope": "clinical_symptom_function",
        "compound_terms": ["psilocybin", "LSD", "ketamine", "ibogaine", "noribogaine", "ayahuasca", "psychedelic"],
        "entity_terms": ["craving", "withdrawal", "relapse", "abstinence", "drug seeking", "quality of life", "social functioning"],
        "evidence_terms": ["treatment", "outcome", "follow-up", "scale", "score", "response", "remission", "clinical"],
    },
    {
        "module_id": "cardiovascular_mania_psychosis_hppd_safety",
        "module_type": "dense_topic",
        "module_scope": "clinical_safety",
        "compound_terms": THERAPEUTIC_CORE,
        "entity_terms": ["cardiovascular", "blood pressure", "heart rate", "hypertension", "mania", "psychosis", "HPPD", "hallucinogen persisting perception disorder", "flashback"],
        "evidence_terms": ["safety", "adverse event", "case report", "clinical", "tolerability", "follow-up"],
    },
    {
        "module_id": "psilocybin_depression_brain_molecular_bridge",
        "module_type": "dense_topic",
        "module_scope": "bridge_clinical_mechanism",
        "compound_terms": ["psilocybin", "psilocin"],
        "entity_terms": ["depression", "major depressive disorder", "treatment-resistant depression", "depressive symptoms"],
        "evidence_terms": ["fMRI", "functional connectivity", "default mode network", "BDNF", "cognitive flexibility", "emotional processing", "biomarker"],
    },
    {
        "module_id": "mdma_ptsd_social_brain_bridge",
        "module_type": "dense_topic",
        "module_scope": "bridge_clinical_mechanism",
        "compound_terms": ["MDMA", "3,4-methylenedioxymethamphetamine"],
        "entity_terms": ["PTSD", "post-traumatic stress disorder", "trauma", "social functioning", "emotional processing"],
        "evidence_terms": ["fMRI", "amygdala", "prefrontal cortex", "social cognition", "emotion recognition", "cortisol", "biomarker"],
    },
    {
        "module_id": "intervention_context_set_setting",
        "module_type": "dense_topic",
        "module_scope": "intervention_context",
        "compound_terms": ["psilocybin", "MDMA", "ketamine", "ayahuasca", "psychedelic-assisted therapy", "psychedelic-assisted psychotherapy"],
        "entity_terms": ["preparation", "integration", "music", "set and setting", "therapeutic alliance", "group therapy", "psychological support", "therapist", "facilitator", "expectancy", "intention"],
        "evidence_terms": ["outcome", "participant", "patient", "qualitative", "acceptability", "feasibility", "clinical", "therapy"],
    },
    {
        "module_id": "naturalistic_community_use_microdosing",
        "module_type": "dense_topic",
        "module_scope": "real_world_use_public_health",
        "compound_terms": ["psilocybin", "LSD", "ayahuasca", "MDMA", "ketamine", "psychedelic", "microdosing", "microdose"],
        "entity_terms": ["naturalistic", "survey", "community", "ceremonial", "retreat", "Global Drug Survey", "microdosing", "nonmedical use", "recreational use", "self-medication"],
        "evidence_terms": ["population", "use", "users", "outcomes", "adverse", "wellbeing", "mental health", "harm reduction", "observational"],
    },
]

MECHANISTIC_MODULES = [
    {
        "module_id": "serotonin_receptors",
        "module_type": "primary_boolean",
        "compound_terms": CLASSIC_PSYCH_CORE,
        "entity_terms": [
            "5-HT2A",
            "HTR2A",
            "serotonin 2A receptor",
            "5-HT2B",
            "HTR2B",
            "5-HT2C",
            "HTR2C",
            "5-HT1A",
            "HTR1A",
            "serotonin receptor",
        ],
        "evidence_terms": MECHANISTIC_EVIDENCE,
    },
    {
        "module_id": "monoamine_transporters",
        "module_type": "primary_boolean",
        "compound_terms": ["MDMA", "MDA", "ibogaine", "noribogaine", "amphetamine", "psychedelic"],
        "entity_terms": ["SERT", "SLC6A4", "serotonin transporter", "DAT", "SLC6A3", "dopamine transporter", "NET", "SLC6A2", "norepinephrine transporter", "VMAT2"],
        "evidence_terms": ["binding", "affinity", "uptake", "release", "transporter", "IC50", "EC50", "Ki"],
    },
    {
        "module_id": "glutamate_nmda",
        "module_type": "primary_boolean",
        "compound_terms": ["ketamine", "esketamine", "arketamine", "R-ketamine", "S-ketamine", "psychedelic"],
        "entity_terms": ["NMDA receptor", "NMDAR", "AMPA receptor", "mGluR2", "GRM2", "glutamate receptor"],
        "evidence_terms": ["binding", "affinity", "antagonist", "agonist", "signaling", "functional assay", "neuroplasticity"],
    },
    {
        "module_id": "opioid_sigma_taar",
        "module_type": "primary_boolean",
        "compound_terms": ["salvinorin A", "ibogaine", "noribogaine", "DMT", "5-MeO-DMT", "psychedelic"],
        "entity_terms": ["kappa opioid receptor", "KOR", "OPRK1", "mu opioid receptor", "sigma-1 receptor", "SIGMAR1", "TAAR1", "trace amine-associated receptor 1"],
        "evidence_terms": MECHANISTIC_EVIDENCE,
    },
    {
        "module_id": "plasticity_trkb_bdnf",
        "module_type": "primary_boolean",
        "compound_terms": ["psychedelic", "psychoplastogen", "psilocybin", "LSD", "DMT", "ketamine"],
        "entity_terms": ["TrkB", "NTRK2", "BDNF", "neuroplasticity", "dendritic spine", "cortical plasticity"],
        "evidence_terms": ["signaling", "binding", "phosphorylation", "plasticity", "neuritogenesis", "dendritic", "synaptic"],
    },
    {
        "module_id": "molecular_pathway_plasticity",
        "module_type": "primary_boolean",
        "module_scope": "molecular_pathway",
        "compound_terms": THERAPEUTIC_CORE + ["psychoplastogen"],
        "entity_terms": MOLECULAR_PATHWAY_TERMS,
        "evidence_terms": PATHWAY_EVIDENCE_TERMS,
    },
    {
        "module_id": "gene_expression_transcriptomics",
        "module_type": "primary_boolean",
        "module_scope": "molecular_pathway",
        "compound_terms": CLASSIC_PSYCH_CORE + ["ketamine", "MDMA", "ayahuasca"],
        "entity_terms": ["gene expression", "transcriptomic", "transcriptome", "RNA-seq", "single-cell", "epigenetic", "immediate early gene", "c-Fos", "Arc"],
        "evidence_terms": ["expression", "transcription", "sequencing", "RNA-seq", "qPCR", "mRNA", "protein expression", "neuron", "brain"],
    },
    {
        "module_id": "inflammation_neuroendocrine_molecular",
        "module_type": "primary_boolean",
        "module_scope": "molecular_pathway",
        "compound_terms": THERAPEUTIC_CORE,
        "entity_terms": ["cytokine", "inflammation", "inflammatory", "IL-6", "IL-1beta", "TNF-alpha", "CRP", "cortisol", "HPA axis", "neuroendocrine", "immune"],
        "evidence_terms": ["biomarker", "plasma", "serum", "blood", "ELISA", "clinical", "preclinical", "response", "change"],
    },
    {
        "module_id": "systems_neuroimaging_connectivity",
        "module_type": "primary_boolean",
        "module_scope": "systems_neuroscience",
        "compound_terms": THERAPEUTIC_CORE + CLASSIC_PSYCH_CORE,
        "entity_terms": SYSTEMS_NETWORK_TERMS + SYSTEMS_CIRCUIT_TERMS,
        "evidence_terms": SYSTEMS_NEUROIMAGING_TERMS,
    },
    {
        "module_id": "brain_regions_circuits",
        "module_type": "primary_boolean",
        "module_scope": "systems_neuroscience",
        "compound_terms": THERAPEUTIC_CORE + CLASSIC_PSYCH_CORE,
        "entity_terms": SYSTEMS_REGION_TERMS + SYSTEMS_CIRCUIT_TERMS,
        "evidence_terms": ["brain region", "circuit", "activation", "c-Fos", "neuronal activity", "connectivity", "projection"],
    },
    {
        "module_id": "pet_receptor_occupancy_metabolism",
        "module_type": "primary_boolean",
        "module_scope": "systems_neuroscience",
        "compound_terms": ["psilocybin", "psilocin", "LSD", "lysergic acid diethylamide", "DMT", "ketamine", "MDMA", "psychedelic"],
        "entity_terms": ["5-HT2A", "serotonin 2A receptor", "receptor occupancy", "thalamus", "cortex"] + SYSTEMS_REGION_TERMS,
        "evidence_terms": PET_OCCUPANCY_TERMS,
    },
    {
        "module_id": "eeg_meg_neurophysiology",
        "module_type": "primary_boolean",
        "module_scope": "systems_neuroscience",
        "compound_terms": THERAPEUTIC_CORE + CLASSIC_PSYCH_CORE,
        "entity_terms": ["brain", "cortex", "network", "neural dynamics"] + SYSTEMS_NETWORK_TERMS,
        "evidence_terms": EEG_MEG_NEUROPHYS_TERMS,
    },
    {
        "module_id": "cognitive_affective_tasks",
        "module_type": "primary_boolean",
        "module_scope": "systems_neuroscience",
        "compound_terms": THERAPEUTIC_CORE + CLASSIC_PSYCH_CORE,
        "entity_terms": COGNITIVE_AFFECTIVE_TASK_TERMS,
        "evidence_terms": TASK_EVIDENCE_TERMS,
    },
    {
        "module_id": "translational_behavioral_assays",
        "module_type": "primary_boolean",
        "module_scope": "systems_neuroscience",
        "compound_terms": CLASSIC_PSYCH_CORE + ["ketamine", "MDMA", "MDA", "ibogaine"],
        "entity_terms": TRANSLATIONAL_BEHAVIOR_TERMS,
        "evidence_terms": PRECLINICAL_EVIDENCE_TERMS,
    },
    {
        "module_id": "subjective_experience_acute_effects",
        "module_type": "primary_boolean",
        "module_scope": "subjective_experience",
        "compound_terms": THERAPEUTIC_CORE + CLASSIC_PSYCH_CORE,
        "entity_terms": SUBJECTIVE_EXPERIENCE_TERMS,
        "evidence_terms": SUBJECTIVE_EXPERIENCE_MEASURE_TERMS,
    },
    {
        "module_id": "pharmacokinetics_exposure_core",
        "module_type": "primary_boolean",
        "module_scope": "pharmacokinetics_exposure",
        "compound_terms": THERAPEUTIC_CORE
        + ["psilocin", "noribogaine", "norketamine", "hydroxynorketamine", "MDA"],
        "entity_terms": PHARMACOKINETICS_EXPOSURE_TERMS,
        "evidence_terms": PHARMACOKINETICS_EVIDENCE_TERMS,
    },
    {
        "module_id": "lsd_5ht2a",
        "module_type": "dense_topic",
        "compound_terms": ["LSD", "lysergic acid diethylamide"],
        "entity_terms": ["5-HT2A", "HTR2A", "serotonin 2A receptor"],
        "evidence_terms": MECHANISTIC_EVIDENCE + ["beta arrestin", "G protein"],
    },
    {
        "module_id": "psilocin_5ht2a",
        "module_type": "dense_topic",
        "compound_terms": ["psilocin", "psilocybin"],
        "entity_terms": ["5-HT2A", "HTR2A", "serotonin 2A receptor"],
        "evidence_terms": MECHANISTIC_EVIDENCE,
    },
    {
        "module_id": "mdma_transporters",
        "module_type": "dense_topic",
        "compound_terms": ["MDMA", "3,4-methylenedioxymethamphetamine", "MDA"],
        "entity_terms": ["SERT", "DAT", "NET", "SLC6A4", "SLC6A3", "SLC6A2", "serotonin transporter", "dopamine transporter", "norepinephrine transporter"],
        "evidence_terms": ["transporter", "uptake", "release", "binding", "affinity", "IC50", "EC50"],
    },
    {
        "module_id": "ketamine_nmda",
        "module_type": "dense_topic",
        "compound_terms": ["ketamine", "esketamine", "arketamine", "S-ketamine", "R-ketamine"],
        "entity_terms": ["NMDA receptor", "NMDAR", "glutamate receptor"],
        "evidence_terms": ["binding", "affinity", "antagonist", "channel blocker", "functional assay"],
    },
    {
        "module_id": "salvinorin_kor",
        "module_type": "dense_topic",
        "compound_terms": ["salvinorin A"],
        "entity_terms": ["kappa opioid receptor", "KOR", "OPRK1"],
        "evidence_terms": MECHANISTIC_EVIDENCE,
    },
    {
        "module_id": "ketamine_psychedelic_mtor_synaptogenesis",
        "module_type": "dense_topic",
        "module_scope": "molecular_pathway",
        "compound_terms": ["ketamine", "esketamine", "arketamine", "psilocybin", "LSD", "DMT", "psychedelic", "psychoplastogen"],
        "entity_terms": ["mTOR", "BDNF", "TrkB", "ERK", "Akt", "synaptogenesis", "dendritic spine", "synaptic plasticity"],
        "evidence_terms": ["signaling", "phosphorylation", "plasticity", "protein expression", "neuritogenesis", "cortical neuron"],
    },
    {
        "module_id": "psychedelic_immediate_early_genes",
        "module_type": "dense_topic",
        "module_scope": "molecular_pathway",
        "compound_terms": ["psilocybin", "psilocin", "LSD", "DMT", "5-MeO-DMT", "DOI", "ketamine", "MDMA"],
        "entity_terms": ["c-Fos", "Fos", "Arc", "Egr1", "immediate early gene", "gene expression"],
        "evidence_terms": ["brain", "cortex", "neuronal activity", "expression", "immunohistochemistry", "qPCR", "RNA-seq"],
    },
    {
        "module_id": "clinical_mechanism_bridge_brain_molecular",
        "module_type": "primary_boolean",
        "module_scope": "bridge_clinical_mechanism",
        "compound_terms": THERAPEUTIC_CORE,
        "entity_terms": CLINICAL_BRIDGE_TERMS,
        "evidence_terms": MECHANISM_BRIDGE_TERMS,
    },
    {
        "module_id": "psilocybin_default_mode_connectivity",
        "module_type": "dense_topic",
        "module_scope": "systems_neuroscience",
        "compound_terms": ["psilocybin", "psilocin"],
        "entity_terms": ["default mode network", "DMN", "resting-state", "resting state", "functional connectivity"],
        "evidence_terms": ["fMRI", "BOLD", "neuroimaging", "connectivity"],
    },
    {
        "module_id": "lsd_thalamocortical_connectivity",
        "module_type": "dense_topic",
        "module_scope": "systems_neuroscience",
        "compound_terms": ["LSD", "lysergic acid diethylamide"],
        "entity_terms": ["thalamus", "thalamo-cortical", "thalamocortical", "global brain connectivity", "functional connectivity"],
        "evidence_terms": ["fMRI", "BOLD", "neuroimaging", "connectivity"],
    },
    {
        "module_id": "dmt_eeg_fmri_dynamics",
        "module_type": "dense_topic",
        "module_scope": "systems_neuroscience",
        "compound_terms": ["DMT", "N,N-dimethyltryptamine", "5-MeO-DMT", "5-methoxy-N,N-dimethyltryptamine"],
        "entity_terms": ["neural dynamics", "brain", "cortex", "network"],
        "evidence_terms": ["EEG", "fMRI", "EEG-fMRI", "signal diversity", "neural oscillations", "entropy"],
    },
    {
        "module_id": "ayahuasca_default_mode_connectivity",
        "module_type": "dense_topic",
        "module_scope": "systems_neuroscience",
        "compound_terms": ["ayahuasca", "DMT", "N,N-dimethyltryptamine"],
        "entity_terms": ["default mode network", "DMN", "functional connectivity", "resting-state", "resting state"],
        "evidence_terms": ["fMRI", "BOLD", "neuroimaging", "connectivity"],
    },
    {
        "module_id": "psilocybin_pet_5ht2a_occupancy",
        "module_type": "dense_topic",
        "module_scope": "systems_neuroscience",
        "compound_terms": ["psilocybin", "psilocin"],
        "entity_terms": ["5-HT2A", "serotonin 2A receptor", "receptor occupancy"],
        "evidence_terms": ["PET", "positron emission tomography", "radioligand", "occupancy"],
    },
    {
        "module_id": "mdma_social_reward_cognition",
        "module_type": "dense_topic",
        "module_scope": "systems_neuroscience",
        "compound_terms": ["MDMA", "3,4-methylenedioxymethamphetamine", "MDA"],
        "entity_terms": ["social reward", "social reward learning", "social cognition", "empathy", "emotion recognition"],
        "evidence_terms": ["task", "behavior", "behaviour", "learning", "performance", "paradigm"],
    },
    {
        "module_id": "ketamine_prefrontal_hippocampal_circuitry",
        "module_type": "dense_topic",
        "module_scope": "systems_neuroscience",
        "compound_terms": ["ketamine", "esketamine", "arketamine", "S-ketamine", "R-ketamine"],
        "entity_terms": [
            "prefrontal cortex",
            "medial prefrontal cortex",
            "mPFC",
            "hippocampus",
            "ventral hippocampus",
            "amygdala",
            "striatum",
            "hippocampal-prefrontal",
        ],
        "evidence_terms": ["circuit", "neuronal activity", "connectivity", "c-Fos", "electrophysiology", "behavior"],
    },
    {
        "module_id": "psychedelic_fear_extinction_flexibility",
        "module_type": "dense_topic",
        "module_scope": "systems_neuroscience",
        "compound_terms": ["psychedelic", "psilocybin", "LSD", "DMT", "ketamine", "MDMA", "DOI"],
        "entity_terms": ["fear extinction", "extinction learning", "fear conditioning", "cognitive flexibility", "reversal learning"],
        "evidence_terms": ["task", "behavior", "behaviour", "learning", "conditioning", "performance"],
    },
    {
        "module_id": "subjective_experience_measures",
        "module_type": "dense_topic",
        "module_scope": "subjective_experience",
        "compound_terms": ["psilocybin", "psilocin", "LSD", "DMT", "5-MeO-DMT", "ayahuasca", "mescaline", "MDMA", "ketamine", "psychedelic"],
        "entity_terms": [
            "Mystical Experience Questionnaire",
            "MEQ30",
            "MEQ-30",
            "5D-ASC",
            "11D-ASC",
            "5D-OAV",
            "OAV",
            "APZ",
            "Altered States of Consciousness Rating Scale",
            "Drug Effects Questionnaire",
            "DEQ",
            "Ego-Dissolution Inventory",
            "EDI",
            "Emotional Breakthrough Inventory",
            "EBI",
            "Hallucinogen Rating Scale",
            "HRS",
            "Challenging Experience Questionnaire",
            "Psychological Insight Questionnaire",
            "PIQ",
            "Persisting Effects Questionnaire",
            "PEQ",
            "Oceanic Boundlessness",
            "emotional breakthrough",
        ],
        "evidence_terms": ["subjective", "acute", "questionnaire", "rating", "scale", "psychometric", "experience"],
    },
    {
        "module_id": "pharmacokinetics_metabolite_exposure",
        "module_type": "dense_topic",
        "module_scope": "pharmacokinetics_exposure",
        "compound_terms": ["psilocin", "psilocybin", "psilocin glucuronide", "ketamine", "esketamine", "arketamine", "norketamine", "hydroxynorketamine", "dehydronorketamine", "MDMA", "MDA", "HMMA", "HMA", "ibogaine", "noribogaine", "DMT", "5-MeO-DMT"],
        "entity_terms": ["metabolite", "plasma", "serum", "pharmacokinetic", "PK/PD", "concentration", "concentration-time", "plasma level", "blood level", "exposure", "CYP2D6", "cytochrome P450", "UGT", "glucuronidation", "glucuronide", "MAO-A", "monoamine oxidase", "clearance", "half-life", "protein binding"],
        "evidence_terms": ["LC-MS", "LC-MS/MS", "mass spectrometry", "AUC", "Cmax", "Tmax", "dose", "route", "administration"],
    },
    {
        "module_id": "psilocybin_depression_mechanism_bridge",
        "module_type": "dense_topic",
        "module_scope": "bridge_clinical_mechanism",
        "compound_terms": ["psilocybin", "psilocin"],
        "entity_terms": ["depression", "major depressive disorder", "treatment-resistant depression", "depressive symptoms"],
        "evidence_terms": ["fMRI", "functional connectivity", "default mode network", "BDNF", "cognitive flexibility", "emotional processing", "biomarker"],
    },
    {
        "module_id": "ketamine_depression_molecular_bridge",
        "module_type": "dense_topic",
        "module_scope": "bridge_clinical_mechanism",
        "compound_terms": ["ketamine", "esketamine", "arketamine", "S-ketamine", "R-ketamine"],
        "entity_terms": ["depression", "treatment-resistant depression", "suicidal ideation", "anhedonia"],
        "evidence_terms": ["BDNF", "cortisol", "inflammation", "cytokine", "EEG", "functional connectivity", "cognitive function", "biomarker"],
    },
]


FIELDNAMES = [
    "seed_id",
    "dataset",
    "provider_profile",
    "module_id",
    "module_type",
    "module_scope",
    "query",
    "compound",
    "entity",
    "compound_terms",
    "entity_terms",
    "evidence_terms",
    "recommended_max_results_per_seed",
]


def module_rows(dataset: str, modules: list[dict], provider_profile: str) -> list[dict]:
    rows = []
    for index, module in enumerate(modules, start=1):
        module_scope = module.get("module_scope") or ("clinical_indication" if dataset == "disorder" else "molecular_target")
        if provider_profile == "pubmed":
            query = pubmed_query(
                module["compound_terms"],
                module["entity_terms"],
                module["evidence_terms"],
                human_filter=dataset == "disorder",
            )
        else:
            query = openalex_query(
                module["compound_terms"],
                module["entity_terms"],
                module["evidence_terms"],
            )
        rows.append(
            {
                "seed_id": f"{dataset}_grouped_{provider_profile}_{index:03d}",
                "dataset": dataset,
                "provider_profile": provider_profile,
                "module_id": module["module_id"],
                "module_type": module["module_type"],
                "module_scope": module_scope,
                "query": query,
                "compound": "",
                "entity": "",
                "compound_terms": " | ".join(module["compound_terms"]),
                "entity_terms": " | ".join(module["entity_terms"]),
                "evidence_terms": " | ".join(module["evidence_terms"]),
                "recommended_max_results_per_seed": RECOMMENDED_CAPS[provider_profile][module["module_type"]],
            }
        )
    return rows


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def datasets_from_arg(raw: str) -> list[str]:
    value = raw.strip().lower()
    if value == "all":
        return ["mechanistic", "disorder"]
    datasets = [item.strip() for item in value.split(",") if item.strip()]
    invalid = [item for item in datasets if item not in {"mechanistic", "disorder"}]
    if invalid:
        raise ValueError(f"Invalid dataset(s): {', '.join(invalid)}")
    if not datasets:
        raise ValueError("At least one dataset is required")
    return datasets


def build_boolean_modules(out_dir: Path, datasets: list[str], run_id: str = DEFAULT_RUN_ID) -> dict:
    modules_by_dataset = {
        "mechanistic": MECHANISTIC_MODULES,
        "disorder": DISORDER_MODULES,
    }
    manifest = {
        "version": VERSION,
        "run_id": run_id,
        "protocol_id": run_id,
        "generated_at_utc": now_utc(),
        "description": (
            "Provider-specific grouped search modules. Direct pair-search seeds "
            "remain a separate discovery layer."
        ),
        "datasets": {},
    }

    for dataset in datasets:
        modules = modules_by_dataset[dataset]
        provider_outputs = {}
        for provider_profile in ["openalex", "pubmed"]:
            rows = module_rows(dataset, modules, provider_profile)
            csv_path = out_dir / f"{dataset}_grouped_{provider_profile}_seeds.csv"
            write_csv(csv_path, rows)
            type_outputs = {}
            for module_type, cap in RECOMMENDED_CAPS[provider_profile].items():
                type_rows = [row for row in rows if row["module_type"] == module_type]
                type_csv_path = out_dir / f"{dataset}_grouped_{provider_profile}_{module_type}_seeds.csv"
                write_csv(type_csv_path, type_rows)
                type_outputs[module_type] = {
                    "seed_csv": str(type_csv_path),
                    "seed_count": len(type_rows),
                    "recommended_max_results_per_seed": cap,
                }
            scope_outputs = {}
            for module_scope in sorted({row["module_scope"] for row in rows}):
                scope_rows = [row for row in rows if row["module_scope"] == module_scope]
                scope_csv_path = out_dir / f"{dataset}_grouped_{provider_profile}_{module_scope}_seeds.csv"
                write_csv(scope_csv_path, scope_rows)
                scope_type_outputs = {}
                for module_type, cap in RECOMMENDED_CAPS[provider_profile].items():
                    scope_type_rows = [row for row in scope_rows if row["module_type"] == module_type]
                    scope_type_csv_path = out_dir / f"{dataset}_grouped_{provider_profile}_{module_scope}_{module_type}_seeds.csv"
                    write_csv(scope_type_csv_path, scope_type_rows)
                    scope_type_outputs[module_type] = {
                        "seed_csv": str(scope_type_csv_path),
                        "seed_count": len(scope_type_rows),
                        "recommended_max_results_per_seed": cap,
                    }
                scope_outputs[module_scope] = {
                    "seed_csv": str(scope_csv_path),
                    "seed_count": len(scope_rows),
                    "module_type_counts": dict(sorted(Counter(row["module_type"] for row in scope_rows).items())),
                    "module_type_outputs": scope_type_outputs,
                }
            provider_outputs[provider_profile] = {
                "seed_csv": str(csv_path),
                "seed_count": len(rows),
                "module_type_counts": dict(sorted(Counter(row["module_type"] for row in rows).items())),
                "module_scope_counts": dict(sorted(Counter(row["module_scope"] for row in rows).items())),
                "recommended_max_results_per_seed": RECOMMENDED_CAPS[provider_profile],
                "module_type_outputs": type_outputs,
                "module_scope_outputs": scope_outputs,
            }
        manifest["datasets"][dataset] = {
            "module_count": len(modules),
            "module_ids": [module["module_id"] for module in modules],
            "outputs": provider_outputs,
        }

    manifest_path = out_dir / "grouped_search_modules_manifest.json"
    manifest["outputs"] = {"manifest_json": str(manifest_path)}
    write_json(manifest_path, manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Build grouped search modules for literature discovery")
    parser.add_argument("--dataset", default="all", help="mechanistic, disorder, comma-separated list, or all")
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID, help="Run label used when --out-dir is not supplied")
    parser.add_argument("--search-root", default=str(SEARCH_STRATEGY_ROOT), help="Root directory for generated search files")
    parser.add_argument(
        "--out-dir",
        default="",
        help="Output directory for grouped search-module seed files. Defaults to <search-root>/<run-id>/grouped_modules.",
    )
    args = parser.parse_args()

    try:
        datasets = datasets_from_arg(args.dataset)
    except ValueError as err:
        raise SystemExit(str(err))

    search_root = Path(args.search_root).resolve()
    out_dir = Path(args.out_dir).resolve() if args.out_dir else search_root / args.run_id / "grouped_modules"
    manifest = build_boolean_modules(out_dir, datasets, run_id=args.run_id)
    print(f"Manifest: {manifest['outputs']['manifest_json']}")
    for dataset, info in manifest["datasets"].items():
        print(f"Dataset: {dataset}")
        print(f"  Modules: {info['module_count']}")
        for provider, output in info["outputs"].items():
            print(f"  {provider}: {output['seed_count']} seeds -> {output['seed_csv']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
