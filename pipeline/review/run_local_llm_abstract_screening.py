#!/usr/bin/env python3
"""Run local Ollama-based semantic screening over paper-library abstracts.

This is the upstream semantic screening layer. It reads the paper library after
metadata sync, asks a local LLM to classify relevance/source family using only
title/abstract/metadata, verifies exact supporting quotes, and writes
non-destructive reports plus DOI queues for later PDF acquisition.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.error
from collections import Counter
from functools import lru_cache
from pathlib import Path
from typing import Iterable, List

try:
    from pipeline.fulltext.run_local_llm_evidence_adjudication import (
        call_ollama,
        model_is_installed,
        ollama_request_timeout,
        quote_found_in_context,
    )
    from pipeline.review.triage_paper_library import (
        COMPOUND_SYNONYMS,
        DATASET_CONFIG,
        DISORDER_SYNONYMS,
        FILE_DISORDER_SYNONYMS,
        TARGET_SYNONYMS,
        load_json_array,
        normalize,
        normalize_doi,
        parse_allowlists,
    )
    from pipeline.ingest.build_boolean_search_modules import (
        CLINICAL_BRIDGE_TERMS,
        CLINICAL_FUNCTION_SYMPTOM_TERMS,
        CLINICAL_SAFETY_TERMS,
        COGNITIVE_AFFECTIVE_TASK_TERMS,
        INTERVENTION_CONTEXT_TERMS,
        MOLECULAR_PATHWAY_TERMS,
        PET_OCCUPANCY_TERMS,
        PHARMACOKINETICS_EXPOSURE_TERMS,
        REAL_WORLD_PUBLIC_HEALTH_TERMS,
        SUBJECTIVE_EXPERIENCE_MEASURE_TERMS,
        SUBJECTIVE_EXPERIENCE_TERMS,
        SYSTEMS_CIRCUIT_TERMS,
        SYSTEMS_NETWORK_TERMS,
        SYSTEMS_NEUROIMAGING_TERMS,
        SYSTEMS_REGION_TERMS,
        TRANSLATIONAL_BEHAVIOR_TERMS,
        EEG_MEG_NEUROPHYS_TERMS,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from pipeline.fulltext.run_local_llm_evidence_adjudication import (
        call_ollama,
        model_is_installed,
        ollama_request_timeout,
        quote_found_in_context,
    )
    from pipeline.review.triage_paper_library import (
        COMPOUND_SYNONYMS,
        DATASET_CONFIG,
        DISORDER_SYNONYMS,
        FILE_DISORDER_SYNONYMS,
        TARGET_SYNONYMS,
        load_json_array,
        normalize,
        normalize_doi,
        parse_allowlists,
    )
    from pipeline.ingest.build_boolean_search_modules import (
        CLINICAL_BRIDGE_TERMS,
        CLINICAL_FUNCTION_SYMPTOM_TERMS,
        CLINICAL_SAFETY_TERMS,
        COGNITIVE_AFFECTIVE_TASK_TERMS,
        INTERVENTION_CONTEXT_TERMS,
        MOLECULAR_PATHWAY_TERMS,
        PET_OCCUPANCY_TERMS,
        PHARMACOKINETICS_EXPOSURE_TERMS,
        REAL_WORLD_PUBLIC_HEALTH_TERMS,
        SUBJECTIVE_EXPERIENCE_MEASURE_TERMS,
        SUBJECTIVE_EXPERIENCE_TERMS,
        SYSTEMS_CIRCUIT_TERMS,
        SYSTEMS_NETWORK_TERMS,
        SYSTEMS_NEUROIMAGING_TERMS,
        SYSTEMS_REGION_TERMS,
        TRANSLATIONAL_BEHAVIOR_TERMS,
        EEG_MEG_NEUROPHYS_TERMS,
    )

ROOT = Path(__file__).resolve().parents[2]
PIPELINE_CONFIG_PATH = ROOT / "pipeline" / "config.example.yaml"
DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_MODEL = "qwen3:14b"
DATASETS = ("disorder", "mechanistic")
PAPER_METADATA_FIELDS = [
    "study_journal",
    "publication_type",
    "trial_registry_ids",
    "publication_date",
    "journal_issn",
    "journal_eissn",
    "publisher",
    "mesh_terms",
    "keywords",
    "funders",
    "grant_ids",
    "related_dois",
    "publication_relations",
    "is_retracted",
    "has_correction",
    "language",
    "semantic_scholar_id",
]

RELEVANCE_VALUES = ["relevant", "irrelevant", "uncertain"]
SUPPORT_VALUES = ["supported", "not_supported", "uncertain"]
ROUTING_TAGS = [
    "clinical_outcome",
    "molecular_target",
    "molecular_pathway",
    "brain_system",
    "cognitive_behavioral",
    "safety",
    "subjective_experience",
    "pharmacokinetics_exposure",
    "intervention_context",
    "real_world_use_public_health",
    "bridge_clinical_mechanism",
    "uncertain",
]
ROUTING_TAG_ALIASES = {
    "pathway_biomarker": "molecular_pathway",
}

FAST_SCREENING_ACTIONS = ["exclude_obvious_irrelevant", "escalate"]
FAST_SCREENING_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "screening_action": {"type": "string", "enum": FAST_SCREENING_ACTIONS},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "supporting_quote": {"type": "string"},
        "reason": {"type": "string"},
    },
    "required": ["screening_action", "confidence", "supporting_quote", "reason"],
}

IN_SCOPE_INTERVENTION_CLASS_TERMS = {
    "atypical psychedelic",
    "atypical psychedelics",
    "classic hallucinogen",
    "classic hallucinogens",
    "classic psychedelic",
    "classic psychedelics",
    "classical hallucinogen",
    "classical hallucinogens",
    "classical psychedelic",
    "classical psychedelics",
    "dissociative",
    "dissociative anaesthetic",
    "dissociative anaesthetics",
    "dissociative anesthetic",
    "dissociative anesthetics",
    "dissociative compound",
    "dissociative compounds",
    "dissociative drug",
    "dissociative drugs",
    "dissociatives",
    "empathogen",
    "empathogenic",
    "empathogenic drug",
    "empathogenic drugs",
    "empathogens",
    "entactogen",
    "entactogenic",
    "entactogenic drug",
    "entactogenic drugs",
    "entactogens",
    "entheogen",
    "entheogenic",
    "entheogenic drug",
    "entheogenic drugs",
    "entheogenic medicine",
    "entheogenic medicines",
    "entheogens",
    "hallucinogenic",
    "hallucinogenic agent",
    "hallucinogenic agents",
    "hallucinogenic compound",
    "hallucinogenic compounds",
    "hallucinogenic drug",
    "hallucinogenic drug state",
    "hallucinogenic drug states",
    "hallucinogenic drugs",
    "hallucinogenic medicine",
    "hallucinogenic medicines",
    "hallucinogenic medication",
    "hallucinogenic medications",
    "hallucinogenic substance",
    "hallucinogenic substances",
    "hallucinogenic therapy",
    "hallucinogenic therapies",
    "hallucinogen-assisted",
    "hallucinogen",
    "hallucinogens",
    "ketamine-assisted",
    "ketamine assisted psychotherapy",
    "ketamine assisted therapy",
    "ketamine assisted treatment",
    "ketamine-assisted psychotherapy",
    "ketamine-assisted therapy",
    "ketamine-assisted treatment",
    "ketamina",
    "kétamine",
    "mdma-assisted",
    "mdma assisted psychotherapy",
    "mdma assisted therapy",
    "mdma assisted treatment",
    "mdma-assisted psychotherapy",
    "mdma-assisted therapy",
    "mdma-assisted treatment",
    "microdosing psychedelics",
    "microdosing with psychedelics",
    "non classic psychedelic",
    "non classic psychedelics",
    "non-classic psychedelic",
    "non-classic psychedelics",
    "non-classical psychedelic",
    "non-classical psychedelics",
    "non-hallucinogenic psychoplastogen",
    "non-hallucinogenic psychoplastogens",
    "nonhallucinogenic psychoplastogen",
    "nonhallucinogenic psychoplastogens",
    "psychoplastogenic",
    "psychoplastogen",
    "psychoplastogens",
    "psychedelic",
    "psychedelic agent",
    "psychedelic agents",
    "psychedelic assisted psychotherapy",
    "psychedelic assisted therapy",
    "psychedelic assisted treatment",
    "psychedelic-assisted",
    "psychedelic-assisted intervention",
    "psychedelic-assisted interventions",
    "psychedelic-assisted medicine",
    "psychedelic-assisted medicines",
    "psychedelic-assisted psychotherapy",
    "psychedelic-assisted therapy",
    "psychedelic-assisted treatment",
    "psychedelic-assisted treatments",
    "psychedelic compound",
    "psychedelic compounds",
    "psychedelic drug",
    "psychedelic drug effects",
    "psychedelic drug response",
    "psychedelic drug responses",
    "psychedelic drug state",
    "psychedelic drug states",
    "psychedelic drugs",
    "psychedelic experience",
    "psychedelic experiences",
    "psychedelic intervention",
    "psychedelic interventions",
    "psychedelic medicine",
    "psychedelic medicines",
    "psychedelic microdose",
    "psychedelic microdoses",
    "psychedelic microdosing",
    "psychedelic psychotherapy",
    "psychedelic session",
    "psychedelic sessions",
    "psychedelic substance",
    "psychedelic substances",
    "psychedelic therapist",
    "psychedelic therapists",
    "psychedelic treatment",
    "psychedelic treatments",
    "psychedelic-like",
    "psychedelic-like compound",
    "psychedelic-like compounds",
    "psychedelic-like drug",
    "psychedelic-like drugs",
    "psychedelic-like effects",
    "psychedelics",
    "psychedeilc assisted therapy",
    "serotonergic hallucinogen",
    "serotonergic hallucinogens",
    "serotonergic psychoplastogen",
    "serotonergic psychoplastogens",
    "serotonergic psychedelic",
    "serotonergic psychedelics",
}
IN_SCOPE_INTERVENTION_ADDITIONAL_TERMS = {
    "salvinorin",
}

AMBIGUOUS_PSYCHIATRIC_TREATMENT_TERMS = {
    "experimental therapeutics",
    "new treatments for psychiatric disorders",
    "novel agents",
    "psychiatric drugs",
    "psychotropic drugs",
}
AMBIGUOUS_INTERVENTION_ACRONYMS = {"dmt", "dob", "doc", "doet", "doi", "dom", "dipt", "dpt", "lsa", "mda", "stp", "tma"}
AMBIGUOUS_INTERVENTION_CLASS_TERMS = {"dissociative", "dissociatives"}
AMBIGUOUS_ACRONYM_SUPPORT_TERMS = {
    "classic hallucinogen",
    "classic hallucinogens",
    "classic psychedelic",
    "classic psychedelics",
    "classical hallucinogen",
    "classical hallucinogens",
    "classical psychedelic",
    "classical psychedelics",
    "empathogenic",
    "entheogen",
    "entheogenic",
    "entheogens",
    "entactogenic",
    "hallucinogen",
    "hallucinogenic",
    "hallucinogenic drug",
    "hallucinogenic drugs",
    "hallucinogens",
    "5 ht2",
    "5 ht2a",
    "5 ht2c",
    "5-ht2",
    "5-ht2a",
    "5-ht2c",
    "5-hydroxytryptamine 2a",
    "5-hydroxytryptamine 2c",
    "discriminative stimulus",
    "drug discrimination",
    "head twitch",
    "head-twitch",
    "lysergamide",
    "lysergamides",
    "nbome",
    "nboh",
    "phenethylamine",
    "phenethylamines",
    "psychoplastogen",
    "psychoplastogens",
    "psychedelic-like",
    "psychedelic drug",
    "psychedelic drugs",
    "psychedelic",
    "psychedelics",
    "psychoactive substance",
    "psychoactive substances",
    "psychotomimetic",
    "psychotomimetics",
    "serotonergic psychedelic",
    "serotonergic psychedelics",
    "serotonin 5-ht2a",
    "serotonin 5-ht2c",
    "serotonin receptor agonist",
    "tryptamine",
    "tryptamines",
}
AMBIGUOUS_CLASS_SUPPORT_TERMS = AMBIGUOUS_ACRONYM_SUPPORT_TERMS | {
    "anesthetic",
    "anesthetics",
    "anaesthetic",
    "anaesthetics",
    "drug",
    "drugs",
}
IN_SCOPE_INTERVENTION_CLASS_TERMS = frozenset(IN_SCOPE_INTERVENTION_CLASS_TERMS)
IN_SCOPE_INTERVENTION_ADDITIONAL_TERMS = frozenset(IN_SCOPE_INTERVENTION_ADDITIONAL_TERMS)
AMBIGUOUS_INTERVENTION_ACRONYMS = frozenset(AMBIGUOUS_INTERVENTION_ACRONYMS)
AMBIGUOUS_INTERVENTION_CLASS_TERMS = frozenset(AMBIGUOUS_INTERVENTION_CLASS_TERMS)
AMBIGUOUS_ACRONYM_SUPPORT_TERMS = frozenset(AMBIGUOUS_ACRONYM_SUPPORT_TERMS)
AMBIGUOUS_CLASS_SUPPORT_TERMS = frozenset(AMBIGUOUS_CLASS_SUPPORT_TERMS)
PSYCHEDELIC_CLASS_CHEMISTRY_RE = re.compile(
    r"\b(?:tryptamines?|phenethylamines?|phenylisopropylamines?|phenylalkylamines?|indolylalkylamines?|"
    r"lysergamides?|ergolines?|ergot\s+alkaloids?|NBOMe|NBOH|alpha[-\s]?methyltryptamine)\b",
    re.IGNORECASE,
)
PSYCHEDELIC_CLASS_QUALIFIER_RE = re.compile(
    r"\b(?:hallucinogenic?|psychedelic(?:-like)?|serotonergic|entheogenic|entactogenic|empathogenic|"
    r"psychoplastogenic|psychoplastogens?|psychotomimetic)\b",
    re.IGNORECASE,
)
PSYCHEDELIC_CLASS_TARGET_RE = re.compile(
    r"\b(?:5[-\s]?HT\s*2[AC]?|5[-\s]?hydroxytryptamine\s*(?:\(?5[-\s]?HT\)?)?\s*2[AC]?|"
    r"serotonin\s+5[-\s]?HT\s*2[AC]?|5[-\s]?HT2A|5[-\s]?HT2C)\b",
    re.IGNORECASE,
)
PSYCHEDELIC_CLASS_ASSAY_RE = re.compile(
    r"\b(?:binding|affinity|selectivity|agonis[mt]|antagonis[mt]|functional|efficacy|"
    r"structure[-\s]?activity|radioligand)\b",
    re.IGNORECASE,
)
LSD_NON_PSYCH_ACRONYM_RE = re.compile(
    r"\b(?:lysosomal\s+storage\s+(?:disorders?|diseases?)|least\s+significant\s+differences?|"
    r"low\s+sodium\s+diet|laparoscopic\s+splenectomy\s+(?:and\s+)?azygoportal\s+disconnection|"
    r"LSD\s+test)\b",
    re.IGNORECASE,
)
LSD_PSYCH_SUPPORT_RE = re.compile(
    r"\b(?:lysergic|lysergide|d[-\s]?LSD|psychedelic|hallucinogen|hallucinogenic|microdos(?:e|ing)|"
    r"5[-\s]?HT\s*2A)\b",
    re.IGNORECASE,
)
MDA_NON_PSYCH_ACRONYM_RE = re.compile(
    r"\b(?:malondialdehyde|maximal\s+dentate\s+activation|minimal\s+disease\s+activity|"
    r"MDA[-\s]?MB|multiple\s+discriminant\s+analysis|oxidative\s+stress|anti[-\s]?oxidative|"
    r"antioxidant|lipid\s+peroxidation|SOD|CAT|GSH|GPx|GST|TNF[-\s]?α?|IL[-\s]?1β?|IL[-\s]?6)\b",
    re.IGNORECASE,
)
MDA_PSYCH_SUPPORT_RE = re.compile(
    r"\b(?:methylenedioxy(?:amphetamine|methamphetamine)?|MDMA|ecstasy|entactogen|entactogenic|"
    r"empathogen|empathogenic|psychedelic|hallucinogen|hallucinogenic|phenethylamine)\b",
    re.IGNORECASE,
)
KETAMINE_ONLY_INTERVENTION_TERMS = {
    "arketamine",
    "esketamine",
    "ketamina",
    "ketamine",
    "kétamine",
    "racemic ketamine",
    "r-ketamine",
    "s-ketamine",
}
KETAMINE_ACUTE_CARE_ALLOWED_CLASS_TERMS = {
    "dissociative",
    "dissociative anaesthetic",
    "dissociative anaesthetics",
    "dissociative anesthetic",
    "dissociative anesthetics",
    "dissociative compound",
    "dissociative compounds",
    "dissociative drug",
    "dissociative drugs",
    "dissociatives",
}
KETAMINE_ACUTE_CARE_ANESTHESIA_RE = re.compile(
    r"\b(?:sedation|sedative|procedural\s+sedation|anaesthesia|anesthesia|general\s+anaesthesia|"
    r"general\s+anesthesia|intubat\w*|rapid\s+sequence|premedication|perioperative|intraoperative|postoperative|"
    r"post-operative|propofol|endoscop\w*|ERCP|wound\s+repair|bone\s+marrow\s+biopsy|"
    r"obstetric|general\s+surgery|mechanical\s+ventilation|emergency\s+department)\b",
    re.IGNORECASE,
)
KETAMINE_TITLE_TERM_RE = re.compile(r"\b(?:arketamine|esketamine|ketamine|kétamine|ketamina|[RS]-ketamine)\b", re.IGNORECASE)
KETAMINE_ACUTE_CARE_TITLE_RE = re.compile(
    r"\b(?:sedation|sedative|procedural\s+sedation|anaesthesia|anesthesia|general\s+anaesthesia|"
    r"general\s+anesthesia|intubat\w*|rapid\s+sequence|premedication|perioperative|intraoperative|postoperative|"
    r"post-operative|propofol|endoscop\w*|ERCP|wound\s+repair|bone\s+marrow\s+biopsy|"
    r"obstetric|general\s+surgery|mechanical\s+ventilation|emergency\s+department)\b",
    re.IGNORECASE,
)
KETAMINE_ACUTE_CARE_TITLE_PROTECTOR_RE = re.compile(
    r"\b(?:pain|painful|analgesi\w*|analgésie|douleurs?|smerte|hyperalgesi\w*|hypersensitivity|"
    r"chronic|neuropath\w*|neuralgia|migraine|headache|"
    r"depression|depressive|depressed|MDD|PTSD|suicid\w*|substance\s+use|addiction|alcohol|"
    r"obsessive|compulsive|OCD|"
    r"post[-\s]?traumatic\s+stress|depress[aã]o|opioid\w*|bipolar|anxiety|anorexia|autism|sleep|"
    r"delirium|psychiatr\w*|cognit\w*|memory|emotion|mood|"
    r"brain|neuro\w*|neural|cortex|cortical|cerebrocortical|cingulate|retrosplenial|hippocamp\w*|damage|injur\w*|"
    r"receptor|NMDA|glutamate|GABA|aminobutyric|dopamine|norepinephrine|transporter|"
    r"N[-\s]?methyl[-\s]?D[-\s]?aspartate|BDNF|c[-\s]?fos|seizure|calcium|Ca2|signaling|"
    r"attention|behaviou?r|impulsive|dreams?|visual|unconsciousness|phMRI|PET/CT|primate|"
    r"Huntington|nociception|antitussive|methylphenidate|electroencephalogram|EEG|"
    r"pharmacolog\w*|serotonin|5[-\s]?HT|5[-\s]?HT7|affinity|antagonist|binding|assay|"
    r"antidepressant|remission|electroconvulsive|ECT|sub[-\s]?(?:anaesth|anesth)\w*|"
    r"inflamm\w*|immune|oxidative|cancer|tumou?r|asthma|COPD|dependen\w*|"
    r"abhängig\w*|cochlear|hearing|visceral|metabol\w*|hydroxynorketamine\w*|toxicit\w*|poison|"
    r"overdose|adverse|veterans?|narcotic|trauma|evoked\s+potential|electroencephalographic|"
    r"psychological|sequelae|chronische|schmerzen|cough|throat)\b",
    re.IGNORECASE,
)
FIVE_MEO_DMT_VARIANT_RE = re.compile(
    r"\b(?:5[-\s]?MeO[-\s]?DMT|MeODMT|5[-\s]?MeOMT|"
    r"5[-\s]?methoxy[-\s]?(?:N,?\s*N[-\s]?)?dimethyl[-\s]?tryptamine)\b",
    re.IGNORECASE,
)
DOI_FULL_NAME_RE = re.compile(
    r"\b(?:1[-\s]?\(?2,5[-\s]?dimethoxy[-\s]?4[-\s]?iodophenyl\)?[-\s]?2[-\s]?aminopropane|"
    r"2,5[-\s]?dimethoxy[-\s]?4[-\s]?iodo(?:phenyl|amphetamine))\b",
    re.IGNORECASE,
)
DOI_IDENTIFIER_RE = re.compile(
    r"\b(?:article\s+DOI|corrects?\s+the\s+article\s+DOI|retracts?\s+the\s+article\s+DOI|"
    r"DOI\s*:|dx\.doi\.org|OSF\s+Registries,\s*DOI|depth[-\s]?of[-\s]?interaction\s*\(?DOI\)?)\b",
    re.IGNORECASE,
)
DOI_COMPOUND_CONTEXT_RE = re.compile(
    r"\b(?:5[-\s]?HT\s*2[AC]?|5[-\s]?hydroxytryptamine|serotonin|receptor|agonis[mt]|"
    r"antagonis[mt]|head[-\s]?twitch|head[-\s]?shake|wet[-\s]?dog|ketanserin|"
    r"phospholipase|inositol|arachidonic|cortical\s+5[-\s]?HT|behavioral\s+response)\b",
    re.IGNORECASE,
)
MOLECULAR_TARGET_SIGNAL_TERMS = {
    "affinity",
    "agonist",
    "antagonist",
    "binding",
    "ec50",
    "functional assay",
    "ic50",
    "ki",
    "kd",
    "pharmacology",
    "radioligand",
    "receptor",
    "serotonin receptor",
    "transporter",
}
MOLECULAR_PATHWAY_SIGNAL_TERMS = {
    *MOLECULAR_PATHWAY_TERMS,
    "arc",
    "bdnf",
    "biomarker",
    "c-fos",
    "cfos",
    "cytokine",
    "dendritic spine",
    "erk",
    "gene expression",
    "inflammation",
    "inflammatory",
    "mtor",
    "neuroplasticity",
    "plasticity",
    "synaptic plasticity",
    "synaptogenesis",
    "transcriptomic",
    "trkb",
}
BRAIN_SYSTEM_SIGNAL_TERMS = {
    *SYSTEMS_NEUROIMAGING_TERMS,
    *SYSTEMS_NETWORK_TERMS,
    *SYSTEMS_REGION_TERMS,
    *SYSTEMS_CIRCUIT_TERMS,
    *PET_OCCUPANCY_TERMS,
    *EEG_MEG_NEUROPHYS_TERMS,
    "amygdala",
    "anterior cingulate",
    "bold",
    "brain circuit",
    "brain connectivity",
    "brain network",
    "brain region",
    "central executive network",
    "circuit",
    "connectivity",
    "default mode network",
    "dmn",
    "eeg",
    "fmri",
    "frontoparietal network",
    "functional connectivity",
    "hippocampus",
    "limbic network",
    "meg",
    "neural dynamics",
    "neuroimaging",
    "neurophysiology",
    "pet",
    "prefrontal cortex",
    "salience network",
    "striatum",
    "thalamocortical",
    "thalamus",
}
COGNITIVE_BEHAVIORAL_SIGNAL_TERMS = {
    *COGNITIVE_AFFECTIVE_TASK_TERMS,
    *TRANSLATIONAL_BEHAVIOR_TERMS,
    "attention",
    "behavior",
    "behaviour",
    "behavioral assay",
    "behavioural assay",
    "cognitive flexibility",
    "cognitive task",
    "emotion recognition",
    "emotional processing",
    "empathy",
    "extinction learning",
    "fear conditioning",
    "fear extinction",
    "forced swim",
    "learning",
    "prepulse inhibition",
    "reversal learning",
    "reward learning",
    "social cognition",
    "social reward",
    "tail suspension",
    "task",
    "working memory",
}
CLINICAL_OUTCOME_SIGNAL_TERMS = {
    *CLINICAL_BRIDGE_TERMS,
    *CLINICAL_FUNCTION_SYMPTOM_TERMS,
    "clinical outcome",
    "clinical trial",
    "depression",
    "efficacy",
    "functioning",
    "patient",
    "patients",
    "ptsd",
    "quality of life",
    "randomized",
    "randomised",
    "symptom",
    "symptoms",
    "treatment",
    "therapeutic",
}
CLINICAL_BRIDGE_SIGNAL_TERMS = {
    *CLINICAL_BRIDGE_TERMS,
    "clinical outcome",
    "depression",
    "functioning",
    "patient",
    "patients",
    "ptsd",
    "quality of life",
    "symptom",
    "symptoms",
    "treatment",
    "therapeutic",
}
SAFETY_SIGNAL_TERMS = {
    *CLINICAL_SAFETY_TERMS,
    "adverse event",
    "adverse events",
    "safety",
    "side effect",
    "side effects",
    "tolerability",
    "tolerated",
}
SUBJECTIVE_EXPERIENCE_SIGNAL_TERMS = {
    *SUBJECTIVE_EXPERIENCE_TERMS,
    *SUBJECTIVE_EXPERIENCE_MEASURE_TERMS,
    "5d-asc",
    "5d-oav",
    "11d-asc",
    "apz",
    "altered state",
    "altered states of consciousness",
    "challenging experience",
    "connectedness",
    "drug effects questionnaire",
    "emotional breakthrough inventory",
    "ego dissolution",
    "ego loss",
    "ego-dissolution inventory",
    "emotional breakthrough",
    "hallucinogen rating scale",
    "meq-30",
    "mystical experience",
    "mystical-type experience",
    "mystical experience questionnaire",
    "oceanic boundlessness",
    "peak experience",
    "persisting effects questionnaire",
    "phenomenology",
    "phenomenological",
    "perceptual effects",
    "psychological insight questionnaire",
    "psychedelic experience",
    "self-dissolution",
    "self-transcendence",
    "subjective drug effects",
    "subjective effects",
    "visual effects",
}
PHARMACOKINETICS_EXPOSURE_SIGNAL_TERMS = {
    *PHARMACOKINETICS_EXPOSURE_TERMS,
    "adme",
    "absorption",
    "auc",
    "bioavailability",
    "blood concentration",
    "blood level",
    "clearance",
    "cmax",
    "concentration-time",
    "cytochrome p450",
    "distribution",
    "dose-response",
    "elimination",
    "excretion",
    "exposure-response",
    "glucuronidation",
    "glucuronide",
    "half-life",
    "lc-ms",
    "mao-a",
    "metabolism",
    "metabolite",
    "monoamine oxidase",
    "pk/pd",
    "pharmacodynamic",
    "pharmacodynamics",
    "pharmacokinetic",
    "pharmacokinetic-pharmacodynamic",
    "pharmacokinetics",
    "plasma concentration",
    "plasma level",
    "protein binding",
    "route of administration",
    "serum concentration",
    "serum level",
    "tmax",
    "ugt",
    "urinary excretion",
}
INTERVENTION_CONTEXT_SIGNAL_TERMS = {
    *INTERVENTION_CONTEXT_TERMS,
    "acceptability",
    "aftercare",
    "blinding",
    "dosing session",
    "eye shades",
    "eyeshades",
    "facilitator",
    "facilitator training",
    "inner-directed",
    "integration",
    "integration session",
    "integration therapy",
    "manualized therapy",
    "music",
    "music playlist",
    "non-directive support",
    "nondirective support",
    "preparation",
    "preparation and integration",
    "preparation session",
    "psychological support",
    "psychotherapy",
    "set and setting",
    "supportive therapy",
    "therapeutic alliance",
    "therapeutic relationship",
    "therapist",
    "therapist training",
    "treatment manual",
}
REAL_WORLD_PUBLIC_HEALTH_SIGNAL_TERMS = {
    *REAL_WORLD_PUBLIC_HEALTH_TERMS,
    "adverse experiences",
    "community",
    "diversion",
    "drug checking",
    "ed visit",
    "emergency department",
    "emergency room",
    "epidemiology",
    "harm reduction",
    "hospitalization",
    "lifetime use",
    "microdosing",
    "misuse",
    "non-medical use",
    "naturalistic",
    "nonmedical use",
    "past-year use",
    "poison center",
    "poison control",
    "population",
    "prevalence",
    "public health",
    "real world",
    "real-world",
    "recreational use",
    "retreat",
    "self-medication",
    "survey",
    "toxicity",
    "use patterns",
}

MOLECULAR_TARGET_SIGNAL_TERMS = frozenset(MOLECULAR_TARGET_SIGNAL_TERMS)
MOLECULAR_PATHWAY_SIGNAL_TERMS = frozenset(MOLECULAR_PATHWAY_SIGNAL_TERMS)
BRAIN_SYSTEM_SIGNAL_TERMS = frozenset(BRAIN_SYSTEM_SIGNAL_TERMS)
COGNITIVE_BEHAVIORAL_SIGNAL_TERMS = frozenset(COGNITIVE_BEHAVIORAL_SIGNAL_TERMS)
CLINICAL_OUTCOME_SIGNAL_TERMS = frozenset(CLINICAL_OUTCOME_SIGNAL_TERMS)
CLINICAL_BRIDGE_SIGNAL_TERMS = frozenset(CLINICAL_BRIDGE_SIGNAL_TERMS)
SAFETY_SIGNAL_TERMS = frozenset(SAFETY_SIGNAL_TERMS)
SUBJECTIVE_EXPERIENCE_SIGNAL_TERMS = frozenset(SUBJECTIVE_EXPERIENCE_SIGNAL_TERMS)
PHARMACOKINETICS_EXPOSURE_SIGNAL_TERMS = frozenset(PHARMACOKINETICS_EXPOSURE_SIGNAL_TERMS)
INTERVENTION_CONTEXT_SIGNAL_TERMS = frozenset(INTERVENTION_CONTEXT_SIGNAL_TERMS)
REAL_WORLD_PUBLIC_HEALTH_SIGNAL_TERMS = frozenset(REAL_WORLD_PUBLIC_HEALTH_SIGNAL_TERMS)

ABSTRACT_SCREENING_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "relevance": {"type": "string", "enum": RELEVANCE_VALUES},
        "supporting_abstract_quote": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "needs_targeted_qa": {"type": "boolean"},
        "routing_tags": {
            "type": "array",
            "items": {"type": "string", "enum": ROUTING_TAGS},
            "uniqueItems": True,
        },
        "reasoning_summary": {"type": "string"},
        "supported_contexts": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "compound": {"type": "string"},
                    "entity": {"type": "string"},
                    "support": {"type": "string", "enum": SUPPORT_VALUES},
                    "supporting_quote": {"type": "string"},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "reason": {"type": "string"},
                },
                "required": ["compound", "entity", "support", "supporting_quote", "confidence", "reason"],
            },
        },
    },
    "required": [
        "relevance",
        "supporting_abstract_quote",
        "confidence",
        "needs_targeted_qa",
        "routing_tags",
        "reasoning_summary",
        "supported_contexts",
    ],
}


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def print_screening_row_followup(
    flat: dict,
    elapsed_sec: float | None,
    *,
    source: str = "llm",
) -> None:
    """One-line summary after each paper (or after loading from checkpoint)."""
    status = normalize(str(flat.get("status", ""))) or "?"
    relevance = normalize(str(flat.get("llm_relevance", ""))) or "—"
    quote_ok = "yes" if flat.get("quote_verified") is True else "no"
    ctx_count = flat.get("verified_supported_context_count", "")
    ctx_part = f" | ctx={ctx_count}" if ctx_count != "" else ""
    dl = flat.get("download_queue_eligible")
    dl_s = "yes" if dl is True else "no" if dl is False else "?"
    qa = flat.get("llm_needs_targeted_qa")
    qa_s = "yes" if qa is True else "no" if qa is False else "?"
    flags = normalize(str(flat.get("validation_flags", "")))
    flags_part = f" | flags={flags}" if flags else ""
    path = normalize(str(flat.get("screening_path", "")))
    path_part = f" | path={path}" if path else ""
    timing = f"{elapsed_sec:.1f}s" if elapsed_sec is not None else ""
    timing_part = f" | {timing}" if timing else ""

    if source == "checkpoint":
        print(
            f"     -> checkpoint | llm={relevance} | "
            f"quote_ok={quote_ok}{ctx_part} | qa={qa_s} | dl_eligible={dl_s}{path_part}{flags_part}",
            flush=True,
        )
        return

    err = normalize(str(flat.get("error", "")))
    if status == "failed" and err:
        err_short = err.replace("\n", " ").strip()[:120]
        print(f"     -> failed{timing_part} | {err_short}", flush=True)
        return

    print(
        f"     -> {status} | llm={relevance} | "
        f"quote_ok={quote_ok}{ctx_part} | qa={qa_s} | dl_eligible={dl_s}{path_part}{flags_part}{timing_part}",
        flush=True,
    )


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: Iterable[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "status",
        "dataset",
        "row_index",
        "study_doi",
        "study_title",
        "study_year",
        "authors",
        *PAPER_METADATA_FIELDS,
        "library_status",
        "pdf_download_status",
        "has_abstract",
        "quote_verified",
        "verified_supported_context_count",
        "semantic_auto_eligible",
        "download_queue_eligible",
        "screening_path",
        "deterministic_prescreen_action",
        "deterministic_prescreen_reason",
        "fast_screening_action",
        "fast_screening_confidence",
        "fast_screening_quote_verified",
        "llm_relevance",
        "llm_confidence",
        "llm_needs_targeted_qa",
        "llm_routing_tags",
        "llm_supported_contexts",
        "llm_supporting_abstract_quote",
        "llm_reasoning_summary",
        "heuristic_relevance",
        "heuristic_screening_status",
        "heuristic_matched_context_count",
        "heuristic_llm_relevance_disagreement",
        "validation_flags",
        "error",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def safe_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def abstract_context(row: dict) -> str:
    title = normalize(row.get("study_title", ""))
    abstract = normalize(row.get("abstract", ""))
    parts = []
    if title:
        parts.append(f"Title: {title}")
    if abstract:
        parts.append(f"Abstract: {abstract}")
    return "\n".join(parts)


def compact_candidate_contexts(row: dict, max_contexts: int = 16) -> List[dict]:
    contexts = row.get("contexts", [])
    if not isinstance(contexts, list):
        return []
    out: List[dict] = []
    seen = set()
    for index, ctx in enumerate(contexts, start=1):
        if not isinstance(ctx, dict):
            continue
        compound = normalize(ctx.get("compound", ""))
        entity = normalize(ctx.get("entity", ""))
        if not compound and not entity:
            continue
        key = (compound.lower(), entity.lower())
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "id": f"CTX{index:03d}",
                "compound": compound,
                "entity": entity,
                "source": normalize(ctx.get("triage_match_source", "")) or "paper_library_context",
            }
        )
        if len(out) >= max_contexts:
            break
    return out


def dataset_scope(dataset: str) -> str:
    if dataset == "disorder":
        return (
            "Disorder KG scope: papers are relevant when the title/abstract supports a relationship between a "
            "psychedelic, dissociative, entactogen, or closely related compound and a disorder, symptom domain, "
            "functional outcome, safety/tolerability outcome, clinical condition, or patient population. Clinical "
            "population papers with brain, circuit, network, molecular, cognitive, or behavioral endpoints should "
            "not be excluded solely because the endpoint is mechanistic; mark them relevant or uncertain and assign "
            "the appropriate routing tags."
        )
    return (
        "Mechanistic KG scope: papers are relevant when the title/abstract supports a relationship between a "
        "psychedelic, dissociative, entactogen, or closely related compound and a biological target, receptor, "
        "transporter, molecular pathway, brain region, circuit, network, neuroimaging/neurophysiology endpoint, "
        "cognitive task, behavioral assay, pharmacodynamic mechanism, animal mechanism, or in-vitro mechanism. "
        "Clinical studies with brain, circuit, network, molecular, cognitive, or behavioral endpoints are in scope "
        "for mechanistic screening even when they also report therapeutic outcomes."
    )


def paper_metadata_from_row(row: dict) -> dict:
    return {field: normalize(row.get(field, "")) for field in PAPER_METADATA_FIELDS}


def screening_input_row(row_index: int, row: dict) -> dict:
    return {
        "row_index": row_index,
        "study_doi": normalize_doi(row.get("study_doi", "")),
        "study_title": normalize(row.get("study_title", "")),
        "study_year": normalize(row.get("study_year", "")),
        "authors": normalize(row.get("authors", "")),
        **paper_metadata_from_row(row),
        "library_status": normalize(row.get("library_status", "")),
        "pdf_download_status": normalize(row.get("pdf_download_status", "")),
        "abstract": normalize(row.get("abstract", "")),
    }


def build_prompt(dataset: str, row: dict, candidate_contexts: List[dict]) -> list[dict]:
    metadata = {
        "dataset": dataset,
        "study_doi": normalize_doi(row.get("study_doi", "")),
        "study_title": normalize(row.get("study_title", "")),
        "study_year": normalize(row.get("study_year", "")),
        "authors": normalize(row.get("authors", "")),
        **paper_metadata_from_row(row),
        "abstract": normalize(row.get("abstract", "")),
        "pmid": normalize(row.get("pmid", "")),
        "pmcid": normalize(row.get("pmcid", "")),
        "library_status": normalize(row.get("library_status", "")),
        "open_access_status": normalize(row.get("open_access_status", "")),
        "best_pdf_url_present": bool(normalize(row.get("best_pdf_url", ""))),
    }
    user_payload = {
        "task": "Decide abstract-level relevance before PDF download for a psychedelics knowledge graph.",
        "dataset_scope": dataset_scope(dataset),
        "candidate_metadata": metadata,
        "candidate_contexts": candidate_contexts,
        "instructions": [
            "Use only the supplied title, abstract, and metadata. Do not use outside knowledge.",
            "Your only job is relevance, routing tags, and quote-supported compound/entity contexts; do not classify source type, paper type, study design, or evidence strength.",
            "Prefer high recall: choose uncertain instead of irrelevant when the abstract is thin but the paper plausibly belongs in scope.",
            "Choose relevant only when the title/abstract supports at least one in-scope compound plus target, molecular/pathway, brain system, cognitive/behavioral, safety, symptom, disorder, or clinical outcome context.",
            "Choose irrelevant only when the title/abstract gives enough evidence that the paper is out of scope.",
            "Set routing_tags to all domains supported by the title/abstract: clinical_outcome, molecular_target, molecular_pathway, brain_system, cognitive_behavioral, safety, subjective_experience, pharmacokinetics_exposure, intervention_context, real_world_use_public_health, bridge_clinical_mechanism, or uncertain.",
            "Use bridge_clinical_mechanism when a clinical population/outcome is linked in the abstract to a mechanistic endpoint such as imaging, connectivity, molecular readouts, cognition, behavior, or receptor occupancy.",
            "For mechanistic screening, brain regions, circuits, networks, fMRI/PET/EEG/MEG, neurophysiology, cognitive tasks, and behavioral assays count as mechanistic/system-level evidence.",
            "For disorder screening, symptom/function/safety endpoints and clinical-population brain or cognitive endpoints should be retained when tied to an in-scope compound.",
            "For supported_contexts, include only contexts supported by the title/abstract. You may use supplied candidate contexts or add a context if the title/abstract explicitly supports it.",
            "supporting_abstract_quote must be an exact verbatim quote supporting the overall screening decision, including irrelevant decisions.",
            "If a paper is irrelevant because it is about a different intervention/topic, quote the title or abstract phrase showing that topic when possible.",
            "Every supported_context supporting_quote must be an exact verbatim quote from the supplied title or abstract. If no exact quote is available, use not_found and set needs_targeted_qa=true.",
        ],
    }
    system = (
        "You are a careful scientific screening reviewer for a psychedelics evidence database. "
        "Your job is not to extract final claims or classify study quality; your job is to decide whether a paper is relevant enough to inspect further. "
        "Be conservative about unsupported claims, but preserve recall by marking plausible-but-underspecified papers as uncertain. "
        "Return only JSON matching the requested schema."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
    ]


def build_fast_screening_prompt(dataset: str, row: dict, candidate_contexts: List[dict] | None = None) -> list[dict]:
    if candidate_contexts is None:
        candidate_contexts = compact_candidate_contexts(row)
    metadata = {
        "dataset": dataset,
        "study_doi": normalize_doi(row.get("study_doi", "")),
        "study_title": normalize(row.get("study_title", "")),
        "study_year": normalize(row.get("study_year", "")),
        "abstract": normalize(row.get("abstract", "")),
    }
    user_payload = {
        "task": "Cheap high-recall pre-screen before expensive abstract adjudication.",
        "dataset_scope": dataset_scope(dataset),
        "candidate_metadata": metadata,
        "candidate_contexts": candidate_contexts,
        "instructions": [
            "Use only the supplied title and abstract.",
            "Return escalate for any paper that might plausibly be in scope, even weakly or indirectly.",
            "Return escalate if the title/abstract mentions any supplied candidate_contexts compound or entity term, even if the relationship is unclear, incidental, background-only, or an exclusion criterion.",
            "Do not exclude papers containing seed-like intervention, disorder, symptom, population, target, molecular pathway, brain, circuit, network, cognition, behavior, safety, or mechanism terms; escalate them to the full model.",
            "Return escalate if the paper mentions any psychedelic or named psychedelic, ketamine/esketamine/arketamine, MDMA/MDA, ayahuasca, ibogaine, mescaline, DMT/tryptamine, LSD/lysergamide, NBOMe/NBOH, salvinorin, entactogen, empathogen, entheogen, hallucinogen, psychoplastogen, dissociative anesthetic, or assisted-therapy intervention.",
            "Return escalate if the paper mentions a disorder, symptom, patient population, clinical outcome, safety outcome, biological target, receptor, transporter, molecular pathway, brain region, circuit, network, neuroimaging, neurophysiology, cognitive task, behavioral assay, animal model, or mechanistic assay that could fit either KG dataset.",
            "Clinical-population brain/cognition papers should escalate; they are not obvious irrelevant just because they mix clinical and mechanistic endpoints.",
            "Return exclude_obvious_irrelevant only when the title/abstract clearly shows a different topic and there is no plausible psychedelic KG relevance.",
            "supporting_quote must be an exact verbatim quote from the title or abstract. Use not_found and escalate if no exact quote supports exclusion.",
        ],
    }
    system = (
        "You are a conservative first-pass screening assistant. "
        "Your only safe exclusion is an obvious out-of-scope paper. "
        "When in doubt, escalate. Return only JSON matching the schema."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
    ]


def synonym_map_terms(*mappings: dict) -> set[str]:
    terms: set[str] = set()
    for mapping in mappings:
        for label, aliases in mapping.items():
            label_norm = normalize(label)
            if label_norm:
                terms.add(label_norm)
            if isinstance(aliases, (list, set, tuple)):
                for alias in aliases:
                    alias_norm = normalize(alias)
                    if alias_norm:
                        terms.add(alias_norm)
    return {term for term in terms if len(term) >= 3}


@lru_cache(maxsize=1)
def target_synonym_terms() -> frozenset[str]:
    return frozenset(synonym_map_terms(TARGET_SYNONYMS))


@lru_cache(maxsize=1)
def disorder_synonym_terms() -> frozenset[str]:
    return frozenset(synonym_map_terms(DISORDER_SYNONYMS, FILE_DISORDER_SYNONYMS))


@lru_cache(maxsize=1)
def molecular_target_terms() -> frozenset[str]:
    return frozenset(set(target_synonym_terms()) | MOLECULAR_TARGET_SIGNAL_TERMS)


@lru_cache(maxsize=1)
def clinical_outcome_terms() -> frozenset[str]:
    return frozenset(set(disorder_synonym_terms()) | CLINICAL_OUTCOME_SIGNAL_TERMS)


@lru_cache(maxsize=1)
def clinical_bridge_terms() -> frozenset[str]:
    return frozenset(set(disorder_synonym_terms()) | CLINICAL_BRIDGE_SIGNAL_TERMS)


@lru_cache(maxsize=1)
def mechanistic_entity_terms() -> frozenset[str]:
    return frozenset(
        set(target_synonym_terms())
        | MOLECULAR_TARGET_SIGNAL_TERMS
        | MOLECULAR_PATHWAY_SIGNAL_TERMS
        | BRAIN_SYSTEM_SIGNAL_TERMS
        | COGNITIVE_BEHAVIORAL_SIGNAL_TERMS
        | SUBJECTIVE_EXPERIENCE_SIGNAL_TERMS
        | PHARMACOKINETICS_EXPOSURE_SIGNAL_TERMS
        | INTERVENTION_CONTEXT_SIGNAL_TERMS
        | REAL_WORLD_PUBLIC_HEALTH_SIGNAL_TERMS
    )


@lru_cache(maxsize=1)
def disorder_entity_terms() -> frozenset[str]:
    return frozenset(
        set(disorder_synonym_terms())
        | CLINICAL_OUTCOME_SIGNAL_TERMS
        | SAFETY_SIGNAL_TERMS
        | BRAIN_SYSTEM_SIGNAL_TERMS
        | COGNITIVE_BEHAVIORAL_SIGNAL_TERMS
        | SUBJECTIVE_EXPERIENCE_SIGNAL_TERMS
        | PHARMACOKINETICS_EXPOSURE_SIGNAL_TERMS
        | INTERVENTION_CONTEXT_SIGNAL_TERMS
        | REAL_WORLD_PUBLIC_HEALTH_SIGNAL_TERMS
    )


def configured_allowed_compound_terms(config_path: Path = PIPELINE_CONFIG_PATH) -> set[str]:
    terms: set[str] = set()
    for compound in parse_allowlists(config_path).get("allowed_compounds", []):
        compound_norm = normalize(compound)
        if not compound_norm:
            continue
        terms.add(compound_norm)
        if "-" in compound_norm:
            terms.add(compound_norm.replace("-", " "))
    return {term for term in terms if len(term) >= 3}


CONFIG_ALLOWED_COMPOUND_TERMS = configured_allowed_compound_terms()
IN_SCOPE_INTERVENTION_TERMS = (
    synonym_map_terms(COMPOUND_SYNONYMS)
    | CONFIG_ALLOWED_COMPOUND_TERMS
    | IN_SCOPE_INTERVENTION_CLASS_TERMS
    | IN_SCOPE_INTERVENTION_ADDITIONAL_TERMS
)
SORTED_IN_SCOPE_INTERVENTION_TERMS = tuple(
    sorted(IN_SCOPE_INTERVENTION_TERMS, key=lambda value: (len(value), value.lower()))
)
IN_SCOPE_INTERVENTION_TERM_BY_LOWER = {term.lower(): term for term in SORTED_IN_SCOPE_INTERVENTION_TERMS}
IN_SCOPE_INTERVENTION_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:"
    + "|".join(re.escape(term) for term in sorted(IN_SCOPE_INTERVENTION_TERMS, key=len, reverse=True))
    + r")(?![A-Za-z0-9])",
    re.IGNORECASE,
)


def term_found_in_context(term: str, context: str) -> bool:
    term = normalize(term)
    if len(term) < 3:
        return False
    normalized_context = normalize(context)
    return term_found_in_normalized_context(term, normalized_context)


def term_found_in_normalized_context(term: str, normalized_context: str) -> bool:
    term = normalize(term)
    if len(term) < 3:
        return False
    return re.search(rf"(?<![A-Za-z0-9]){re.escape(term)}(?![A-Za-z0-9])", normalized_context, re.IGNORECASE) is not None


TERM_PATTERN_CACHE: dict[frozenset[str], re.Pattern] = {}


def term_pattern_for_terms(terms: Iterable[str]) -> re.Pattern | None:
    key = terms if isinstance(terms, frozenset) else frozenset(normalize(term) for term in terms if len(normalize(term)) >= 3)
    if not key:
        return None
    if key not in TERM_PATTERN_CACHE:
        TERM_PATTERN_CACHE[key] = re.compile(
            r"(?<![A-Za-z0-9])(?:"
            + "|".join(re.escape(term) for term in sorted(key, key=len, reverse=True))
            + r")(?![A-Za-z0-9])",
            re.IGNORECASE,
        )
    return TERM_PATTERN_CACHE[key]


def any_term_found_in_context(terms: Iterable[str], context: str) -> bool:
    normalized_context = normalize(context)
    pattern = term_pattern_for_terms(terms)
    return bool(pattern and pattern.search(normalized_context))


def candidate_term_found_in_context(candidate_contexts: List[dict] | None, context: str) -> bool:
    if not candidate_contexts:
        return False
    for candidate in candidate_contexts:
        if not isinstance(candidate, dict):
            continue
        if term_found_in_context(candidate.get("compound", ""), context) or term_found_in_context(
            candidate.get("entity", ""),
            context,
        ):
            return True
    return False


def normalize_routing_tags(value: object) -> List[str]:
    if isinstance(value, str):
        raw_values = re.split(r"[|,;]\s*", value)
    elif isinstance(value, list):
        raw_values = value
    else:
        raw_values = []
    allowed = set(ROUTING_TAGS)
    out: List[str] = []
    seen: set[str] = set()
    for raw in raw_values:
        tag = normalize(raw).lower().replace("-", "_").replace(" ", "_")
        tag = ROUTING_TAG_ALIASES.get(tag, tag)
        if tag not in allowed or tag in seen:
            continue
        seen.add(tag)
        out.append(tag)
    return out


def entity_terms_for_dataset(dataset: str) -> set[str]:
    if dataset == "disorder":
        return set(disorder_entity_terms())
    return set(mechanistic_entity_terms())


def evidence_domain_tags_for_context(dataset: str, context: str) -> List[str]:
    tags: List[str] = []
    if any_term_found_in_context(molecular_target_terms(), context):
        tags.append("molecular_target")
    if any_term_found_in_context(MOLECULAR_PATHWAY_SIGNAL_TERMS, context):
        tags.append("molecular_pathway")
    if any_term_found_in_context(BRAIN_SYSTEM_SIGNAL_TERMS, context):
        tags.append("brain_system")
    if any_term_found_in_context(COGNITIVE_BEHAVIORAL_SIGNAL_TERMS, context):
        tags.append("cognitive_behavioral")
    if any_term_found_in_context(clinical_outcome_terms(), context):
        tags.append("clinical_outcome")
    if any_term_found_in_context(SAFETY_SIGNAL_TERMS, context):
        tags.append("safety")
    if any_term_found_in_context(SUBJECTIVE_EXPERIENCE_SIGNAL_TERMS, context):
        tags.append("subjective_experience")
    if any_term_found_in_context(PHARMACOKINETICS_EXPOSURE_SIGNAL_TERMS, context):
        tags.append("pharmacokinetics_exposure")
    if any_term_found_in_context(INTERVENTION_CONTEXT_SIGNAL_TERMS, context):
        tags.append("intervention_context")
    if any_term_found_in_context(REAL_WORLD_PUBLIC_HEALTH_SIGNAL_TERMS, context):
        tags.append("real_world_use_public_health")
    has_clinical = dataset == "disorder" or any_term_found_in_context(
        clinical_bridge_terms(),
        context,
    )
    has_mechanistic = any(
        tag in tags
        for tag in {
            "molecular_target",
            "molecular_pathway",
            "brain_system",
            "cognitive_behavioral",
            "subjective_experience",
            "pharmacokinetics_exposure",
        }
    )
    if has_clinical and has_mechanistic:
        tags.append("bridge_clinical_mechanism")
    return normalize_routing_tags(tags)


def routing_tag_counts(flat_rows: Iterable[dict]) -> dict[str, int]:
    counts: Counter = Counter()
    for row in flat_rows:
        for tag in normalize_routing_tags(row.get("llm_routing_tags", "")):
            counts[tag] += 1
    return dict(counts)


def in_scope_intervention_term_found(context: str) -> bool:
    return bool(matched_in_scope_intervention_terms(context))


def ambiguous_intervention_acronym_supported(context: str) -> bool:
    return any_term_found_in_context(AMBIGUOUS_ACRONYM_SUPPORT_TERMS, context)


def ambiguous_intervention_class_supported(context: str) -> bool:
    return any_term_found_in_context(AMBIGUOUS_CLASS_SUPPORT_TERMS, context)


def class_chemistry_intervention_supported(context: str) -> bool:
    normalized_context = normalize(context)
    if not PSYCHEDELIC_CLASS_CHEMISTRY_RE.search(normalized_context):
        return False
    if PSYCHEDELIC_CLASS_QUALIFIER_RE.search(normalized_context):
        return True
    return bool(
        PSYCHEDELIC_CLASS_TARGET_RE.search(normalized_context)
        and PSYCHEDELIC_CLASS_ASSAY_RE.search(normalized_context)
    )


def doi_compound_context_supported(context: str) -> bool:
    normalized_context = normalize(context)
    if not normalized_context:
        return False
    if DOI_FULL_NAME_RE.search(normalized_context):
        return True
    for match in re.finditer(r"\bDOI\b", normalized_context):
        start = max(0, match.start() - 120)
        end = min(len(normalized_context), match.end() + 120)
        window = normalized_context[start:end]
        if DOI_IDENTIFIER_RE.search(window):
            continue
        if DOI_COMPOUND_CONTEXT_RE.search(window):
            return True
    return False


def matched_targeted_intervention_terms(context: str) -> List[str]:
    out: List[str] = []
    if doi_compound_context_supported(context):
        out.append("DOI")
    if FIVE_MEO_DMT_VARIANT_RE.search(normalize(context)):
        out.append("5-MeO-DMT")
    if class_chemistry_intervention_supported(context):
        out.append("psychedelic class chemistry")
    return out


def matched_in_scope_intervention_terms(context: str) -> List[str]:
    normalized_context = normalize(context)
    out: List[str] = []
    seen: set[str] = set()
    acronym_supported = ambiguous_intervention_acronym_supported(normalized_context)
    class_supported = ambiguous_intervention_class_supported(normalized_context)
    for match in IN_SCOPE_INTERVENTION_RE.finditer(normalized_context):
        term = IN_SCOPE_INTERVENTION_TERM_BY_LOWER.get(match.group(0).lower(), match.group(0))
        term_lower = term.lower()
        if (
            term_lower == "lsd"
            and LSD_NON_PSYCH_ACRONYM_RE.search(normalized_context)
            and not LSD_PSYCH_SUPPORT_RE.search(normalized_context)
        ):
            continue
        if (
            term_lower == "mda"
            and MDA_NON_PSYCH_ACRONYM_RE.search(normalized_context)
            and not MDA_PSYCH_SUPPORT_RE.search(normalized_context)
        ):
            continue
        if term_lower in AMBIGUOUS_INTERVENTION_ACRONYMS and not acronym_supported:
            continue
        if term_lower in AMBIGUOUS_INTERVENTION_CLASS_TERMS and not class_supported:
            continue
        key = term_lower
        if key in seen:
            continue
        seen.add(key)
        out.append("DOI" if key == "doi" else term)
    for term in IN_SCOPE_INTERVENTION_CLASS_TERMS:
        if not term_found_in_normalized_context(term, normalized_context):
            continue
        term_lower = term.lower()
        if term_lower in AMBIGUOUS_INTERVENTION_CLASS_TERMS and not class_supported:
            continue
        key = term_lower
        if key in seen:
            continue
        seen.add(key)
        out.append(term)
    for term in matched_targeted_intervention_terms(context):
        key = term.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(term)
    return out


def is_ketamine_only_acute_care_anesthesia_context(
    context: str,
    matched_intervention_terms: List[str],
    title: str = "",
) -> bool:
    if not matched_intervention_terms:
        return False

    normalized_context = normalize(context)
    normalized_terms = {normalize(term).lower() for term in matched_intervention_terms if normalize(term)}
    if not normalized_terms:
        return False

    allowed_terms = KETAMINE_ONLY_INTERVENTION_TERMS | KETAMINE_ACUTE_CARE_ALLOWED_CLASS_TERMS
    if any(term not in allowed_terms for term in normalized_terms):
        return False
    if not any(term in KETAMINE_ONLY_INTERVENTION_TERMS for term in normalized_terms):
        return False
    if not KETAMINE_ACUTE_CARE_ANESTHESIA_RE.search(normalized_context):
        return False

    title_text = normalize(title) or normalized_context.split("\n", 1)[0]
    if KETAMINE_ACUTE_CARE_TITLE_PROTECTOR_RE.search(title_text):
        return False

    title_has_ketamine = bool(KETAMINE_TITLE_TERM_RE.search(title_text))
    title_has_acute_care = bool(KETAMINE_ACUTE_CARE_TITLE_RE.search(title_text))
    if title_has_ketamine:
        return title_has_acute_care
    return True


def heuristic_blocks_deterministic_exclusion(heuristic: dict) -> bool:
    relevance = normalize(heuristic.get("relevance_suggested", ""))
    if relevance in {"likely_relevant", "possible_relevant"}:
        return True
    status = normalize(heuristic.get("screening_status", ""))
    if status.startswith("included_") or status.startswith("needs_"):
        return True
    return safe_float(heuristic.get("matched_context_count", 0)) > 0 or safe_float(
        heuristic.get("protected_context_count", 0)
    ) > 0


def deterministic_prescreen_decision(
    dataset: str,
    row: dict,
    heuristic: dict,
    candidate_contexts: List[dict],
) -> dict:
    context = abstract_context(row)
    matched_intervention_terms = matched_in_scope_intervention_terms(context)
    matched_domain_tags = evidence_domain_tags_for_context(dataset, context)
    if matched_intervention_terms:
        if is_ketamine_only_acute_care_anesthesia_context(
            context,
            matched_intervention_terms,
            title=normalize(row.get("study_title", "")),
        ):
            return {
                "action": "exclude_obvious_irrelevant",
                "confidence": 1.0,
                "supporting_quote": deterministic_supporting_quote(row),
                "reason": (
                    "Ketamine/esketamine/arketamine appears only in an acute procedural anesthesia or sedation "
                    "context, without psychiatric, chronic pain, brain/cognition, safety, or mechanistic KG signals."
                ),
                "matched_terms": matched_intervention_terms[:20],
                "routing_tags": matched_domain_tags,
            }
        return {
            "action": "escalate",
            "reason": "in-scope compound/intervention term appears in title or abstract",
            "matched_terms": matched_intervention_terms[:20],
            "routing_tags": matched_domain_tags,
        }
    if any_term_found_in_context(AMBIGUOUS_PSYCHIATRIC_TREATMENT_TERMS, context):
        return {
            "action": "escalate",
            "reason": "broad psychiatric treatment language needs LLM review",
            "routing_tags": matched_domain_tags or ["uncertain"],
        }

    entity_terms = entity_terms_for_dataset(dataset)
    entity_reason = "dataset entity terms present" if any_term_found_in_context(entity_terms, context) else "no dataset entity terms found"
    return {
        "action": "exclude_obvious_irrelevant",
        "confidence": 1.0,
        "supporting_quote": deterministic_supporting_quote(row),
        "reason": (
            "No in-scope psychedelic/ketamine/entactogen/dissociative compound or intervention term appears "
            f"in the title/abstract; {entity_reason}."
        ),
        "routing_tags": matched_domain_tags,
    }


def deterministic_supporting_quote(row: dict) -> str:
    title = normalize(row.get("study_title", ""))
    if title:
        return title
    abstract = normalize(row.get("abstract", ""))
    return abstract[:300] if abstract else "not_found"


def deterministic_irrelevant_adjudication(decision: dict) -> dict:
    return {
        "relevance": "irrelevant",
        "supporting_abstract_quote": normalize(decision.get("supporting_quote", "")),
        "confidence": safe_float(decision.get("confidence", 1.0)),
        "needs_targeted_qa": False,
        "routing_tags": [],
        "reasoning_summary": "deterministic prescreen excluded as obvious irrelevant: "
        + normalize(decision.get("reason", "")),
        "supported_contexts": [],
    }


def fast_screen_excludes(
    fast_screening: dict,
    context: str,
    min_confidence: float,
    candidate_contexts: List[dict] | None = None,
) -> bool:
    if normalize(fast_screening.get("screening_action", "")) != "exclude_obvious_irrelevant":
        return False
    if safe_float(fast_screening.get("confidence", 0)) < min_confidence:
        return False
    if candidate_term_found_in_context(candidate_contexts, context):
        return False
    quote = normalize(fast_screening.get("supporting_quote", ""))
    if quote.lower() == "not_found":
        return False
    return quote_found_in_context(quote, context)


def fast_screen_irrelevant_adjudication(fast_screening: dict) -> dict:
    return {
        "relevance": "irrelevant",
        "supporting_abstract_quote": normalize(fast_screening.get("supporting_quote", "")),
        "confidence": safe_float(fast_screening.get("confidence", 0)),
        "needs_targeted_qa": False,
        "routing_tags": [],
        "reasoning_summary": "fast-screen excluded as obvious irrelevant: "
        + normalize(fast_screening.get("reason", "")),
        "supported_contexts": [],
    }


def load_triage_by_doi(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("rows", []) if isinstance(payload, dict) else []
    out = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        doi = normalize_doi(row.get("study_doi", "")).lower()
        if doi:
            out[doi] = row
    return out


def heuristic_relevance_disagreement(heuristic: dict, adjudication: dict) -> bool:
    heuristic_relevance = normalize(heuristic.get("relevance_suggested", ""))
    llm_relevance = normalize(adjudication.get("relevance", ""))
    return (heuristic_relevance == "likely_irrelevant" and llm_relevance == "relevant") or (
        heuristic_relevance == "likely_relevant" and llm_relevance == "irrelevant"
    )


def verified_supported_contexts(adjudication: dict, context: str, min_confidence: float) -> List[dict]:
    out: List[dict] = []
    contexts = adjudication.get("supported_contexts", [])
    if not isinstance(contexts, list):
        return out
    for ctx in contexts:
        if not isinstance(ctx, dict):
            continue
        compound = normalize(ctx.get("compound", ""))
        entity = normalize(ctx.get("entity", ""))
        if not compound or not entity:
            continue
        if normalize(ctx.get("support", "")) != "supported":
            continue
        confidence = safe_float(ctx.get("confidence", 0))
        if confidence < min_confidence:
            continue
        quote = normalize(ctx.get("supporting_quote", "")) or normalize(adjudication.get("supporting_abstract_quote", ""))
        if not quote_found_in_context(quote, context):
            continue
        out.append(
            {
                "compound": compound,
                "entity": entity,
                "supporting_quote": quote,
                "confidence": confidence,
                "reason": normalize(ctx.get("reason", "")),
            }
        )
    return out


def validation_flags(adjudication: dict, quote_verified: bool, verified_context_count: int) -> List[str]:
    flags: List[str] = []
    relevance = normalize(adjudication.get("relevance", ""))
    if not quote_verified:
        flags.append("decision_quote_not_verified")
    if relevance == "relevant" and verified_context_count <= 0:
        flags.append("relevant_without_verified_context")
    if relevance == "irrelevant" and verified_context_count > 0:
        flags.append("irrelevant_with_supported_context")
    return flags


def semantic_auto_eligible(adjudication: dict, quote_verified: bool, verified_context_count: int, min_confidence: float) -> bool:
    return (
        quote_verified
        and verified_context_count > 0
        and safe_float(adjudication.get("confidence", 0)) >= min_confidence
        and adjudication.get("needs_targeted_qa") is False
        and normalize(adjudication.get("relevance", "")) == "relevant"
    )


def enforce_validation_flags(adjudication: dict, quote_verified: bool, verified_context_count: int) -> dict:
    """Force unsafe model outputs into targeted QA instead of trusting them."""
    out = dict(adjudication)
    out["routing_tags"] = normalize_routing_tags(out.get("routing_tags", []))
    if validation_flags(out, quote_verified=quote_verified, verified_context_count=verified_context_count):
        out["needs_targeted_qa"] = True
    return out


def download_queue_eligible(
    adjudication: dict,
    verified_context_count: int = 0,
) -> bool:
    relevance = normalize(adjudication.get("relevance", ""))
    return relevance in {"relevant", "uncertain"}


def dry_run_adjudication() -> dict:
    return {
        "relevance": "uncertain",
        "supporting_abstract_quote": "not_found",
        "confidence": 0,
        "needs_targeted_qa": True,
        "routing_tags": ["uncertain"],
        "reasoning_summary": "dry run; model was not called",
        "supported_contexts": [],
    }


def selected_rows(rows: List[dict], limit: int, offset: int) -> List[dict]:
    start = max(0, offset)
    end = None if limit <= 0 else start + limit
    return rows[start:end]


def filter_indexed_rows(
    indexed_rows: List[tuple[int, dict]],
    triage_by_doi: dict[str, dict],
    args: argparse.Namespace,
    doi_filter: set[str] | None = None,
) -> List[tuple[int, dict]]:
    filtered = []
    for row_index, row in indexed_rows:
        doi = normalize_doi(row.get("study_doi", "")).lower()
        if doi_filter is not None and doi not in doi_filter:
            continue
        if args.only_with_abstract and not normalize(row.get("abstract", "")):
            continue
        if args.only_undownloaded and normalize(row.get("pdf_local_path", "")):
            continue
        if args.only_heuristic_possible:
            heuristic = triage_by_doi.get(doi, {})
            if heuristic.get("relevance_suggested") != "possible_relevant":
                continue
        filtered.append((row_index, row))
    return filtered


def flatten_supported_contexts(contexts: List[dict]) -> str:
    return " | ".join(f"{ctx.get('compound', '')}->{ctx.get('entity', '')}" for ctx in contexts)


def flatten_result(
    dataset: str,
    row_index: int,
    row: dict,
    adjudication: dict,
    status: str,
    quote_verified: bool,
    verified_contexts: List[dict],
    heuristic: dict,
    args: argparse.Namespace,
    error: str = "",
    screening_path: str = "full_model",
    deterministic_prescreen: dict | None = None,
    fast_screening: dict | None = None,
    fast_quote_verified: bool | str = "",
) -> dict:
    deterministic_prescreen = deterministic_prescreen or {}
    fast_screening = fast_screening or {}
    return {
        "status": status,
        "dataset": dataset,
        "row_index": row_index,
        "study_doi": normalize_doi(row.get("study_doi", "")),
        "study_title": normalize(row.get("study_title", "")),
        "study_year": normalize(row.get("study_year", "")),
        "authors": normalize(row.get("authors", "")),
        **paper_metadata_from_row(row),
        "library_status": normalize(row.get("library_status", "")),
        "pdf_download_status": normalize(row.get("pdf_download_status", "")),
        "has_abstract": bool(normalize(row.get("abstract", ""))),
        "quote_verified": quote_verified,
        "verified_supported_context_count": len(verified_contexts),
        "semantic_auto_eligible": semantic_auto_eligible(
            adjudication,
            quote_verified=quote_verified,
            verified_context_count=len(verified_contexts),
            min_confidence=args.auto_confidence,
        ),
        "download_queue_eligible": download_queue_eligible(
            adjudication,
            verified_context_count=len(verified_contexts),
        ),
        "screening_path": screening_path,
        "deterministic_prescreen_action": deterministic_prescreen.get("action", ""),
        "deterministic_prescreen_reason": deterministic_prescreen.get("reason", ""),
        "fast_screening_action": fast_screening.get("screening_action", ""),
        "fast_screening_confidence": fast_screening.get("confidence", ""),
        "fast_screening_quote_verified": fast_quote_verified,
        "llm_relevance": adjudication.get("relevance", ""),
        "llm_confidence": adjudication.get("confidence", ""),
        "llm_needs_targeted_qa": adjudication.get("needs_targeted_qa", ""),
        "llm_routing_tags": "|".join(normalize_routing_tags(adjudication.get("routing_tags", []))),
        "llm_supported_contexts": flatten_supported_contexts(verified_contexts),
        "llm_supporting_abstract_quote": adjudication.get("supporting_abstract_quote", ""),
        "llm_reasoning_summary": adjudication.get("reasoning_summary", ""),
        "heuristic_relevance": heuristic.get("relevance_suggested", ""),
        "heuristic_screening_status": heuristic.get("screening_status", ""),
        "heuristic_matched_context_count": heuristic.get("matched_context_count", ""),
        "heuristic_llm_relevance_disagreement": heuristic_relevance_disagreement(heuristic, adjudication) if heuristic else "",
        "validation_flags": " | ".join(
            validation_flags(
                adjudication,
                quote_verified=quote_verified,
                verified_context_count=len(verified_contexts),
            )
        ),
        "error": error,
    }


def screen_row(dataset: str, row_index: int, row: dict, heuristic: dict, args: argparse.Namespace) -> dict:
    candidate_contexts = compact_candidate_contexts(row, max_contexts=max(1, args.max_contexts))
    context = abstract_context(row)
    fast_screening: dict | None = None
    fast_quote_verified: bool | str = ""
    deterministic_prescreen: dict | None = None
    screening_path = "full_model"
    if args.dry_run:
        adjudication = dry_run_adjudication()
    else:
        if getattr(args, "deterministic_prescreen", False):
            deterministic_prescreen = deterministic_prescreen_decision(dataset, row, heuristic, candidate_contexts)
        if deterministic_prescreen and deterministic_prescreen.get("action") == "exclude_obvious_irrelevant":
            adjudication = deterministic_irrelevant_adjudication(deterministic_prescreen)
            screening_path = "deterministic_excluded"
        else:
            fast_model = normalize(getattr(args, "fast_screen_model", ""))
            if fast_model:
                try:
                    fast_screening = call_ollama(
                        model=fast_model,
                        messages=build_fast_screening_prompt(dataset, row, candidate_contexts),
                        schema=FAST_SCREENING_SCHEMA,
                        ollama_url=args.ollama_url,
                        timeout_sec=ollama_request_timeout(max(0, args.fast_screen_timeout_sec)),
                        temperature=max(0.0, args.fast_screen_temperature),
                        num_ctx=max(2048, args.fast_screen_num_ctx),
                    )
                    fast_quote_verified = quote_found_in_context(fast_screening.get("supporting_quote", ""), context)
                except Exception as err:
                    fast_screening = {
                        "screening_action": "escalate",
                        "confidence": 0,
                        "supporting_quote": "not_found",
                        "reason": f"fast screen failed; escalated to full model: {type(err).__name__}: {err}",
                    }
                    fast_quote_verified = False
            if fast_screening and fast_screen_excludes(
                fast_screening,
                context=context,
                min_confidence=max(0.0, args.fast_screen_confidence),
                candidate_contexts=candidate_contexts,
            ):
                adjudication = fast_screen_irrelevant_adjudication(fast_screening)
                screening_path = "fast_excluded"
            else:
                if fast_model:
                    screening_path = "fast_escalated"
                adjudication = call_ollama(
                    model=args.model,
                    messages=build_prompt(dataset, row, candidate_contexts),
                    schema=ABSTRACT_SCREENING_SCHEMA,
                    ollama_url=args.ollama_url,
                    timeout_sec=ollama_request_timeout(args.timeout_sec),
                    temperature=max(0.0, args.temperature),
                    num_ctx=max(2048, args.num_ctx),
                )
    quote_verified = quote_found_in_context(adjudication.get("supporting_abstract_quote", ""), context)
    verified_contexts = verified_supported_contexts(
        adjudication,
        context=context,
        min_confidence=max(0.0, args.context_confidence),
    )
    adjudication = enforce_validation_flags(
        adjudication,
        quote_verified=quote_verified,
        verified_context_count=len(verified_contexts),
    )
    flat = flatten_result(
        dataset=dataset,
        row_index=row_index,
        row=row,
        adjudication=adjudication,
        status="ok",
        quote_verified=quote_verified,
        verified_contexts=verified_contexts,
        heuristic=heuristic,
        args=args,
        screening_path=screening_path,
        deterministic_prescreen=deterministic_prescreen,
        fast_screening=fast_screening,
        fast_quote_verified=fast_quote_verified,
    )
    return {
        "input_row": screening_input_row(row_index, row),
        "candidate_contexts": candidate_contexts,
        "deterministic_prescreen": deterministic_prescreen or {},
        "fast_screening": fast_screening or {},
        "adjudication": adjudication,
        "verification": {
            "quote_verified": quote_verified,
            "verified_supported_context_count": len(verified_contexts),
            "verified_supported_contexts": verified_contexts,
            "routing_tags": normalize_routing_tags(adjudication.get("routing_tags", [])),
            "semantic_auto_eligible": flat["semantic_auto_eligible"],
            "download_queue_eligible": flat["download_queue_eligible"],
        },
        "heuristic_comparison": {
            "relevance": heuristic.get("relevance_suggested", ""),
            "screening_status": heuristic.get("screening_status", ""),
            "matched_context_count": heuristic.get("matched_context_count", ""),
            "relevance_disagreement": flat["heuristic_llm_relevance_disagreement"],
        },
        "flat": flat,
    }


def revalidate_checkpoint_result(
    dataset: str,
    row_index: int,
    row: dict,
    heuristic: dict,
    result: dict,
    args: argparse.Namespace,
) -> dict:
    """Recompute validation/queue fields for a checkpointed model response.

    Checkpoints store expensive LLM output. They should not freeze downstream
    validation logic because we often tighten gates during calibration.
    """
    if result.get("flat", {}).get("status") != "ok":
        return result

    adjudication = result.get("adjudication", {})
    if not isinstance(adjudication, dict):
        return result

    context = abstract_context(row)
    quote_verified = quote_found_in_context(adjudication.get("supporting_abstract_quote", ""), context)
    verified_contexts = verified_supported_contexts(
        adjudication,
        context=context,
        min_confidence=max(0.0, args.context_confidence),
    )
    adjudication = enforce_validation_flags(
        adjudication,
        quote_verified=quote_verified,
        verified_context_count=len(verified_contexts),
    )
    flat = flatten_result(
        dataset=dataset,
        row_index=row_index,
        row=row,
        adjudication=adjudication,
        status="ok",
        quote_verified=quote_verified,
        verified_contexts=verified_contexts,
        heuristic=heuristic,
        args=args,
        screening_path=result.get("flat", {}).get("screening_path", "checkpoint"),
        deterministic_prescreen=result.get("deterministic_prescreen", {}),
        fast_screening=result.get("fast_screening", {}),
        fast_quote_verified=result.get("flat", {}).get("fast_screening_quote_verified", ""),
    )

    updated = dict(result)
    updated["input_row"] = screening_input_row(row_index, row)
    updated["candidate_contexts"] = result.get("candidate_contexts", compact_candidate_contexts(row, max_contexts=max(1, args.max_contexts)))
    updated["deterministic_prescreen"] = result.get("deterministic_prescreen", {})
    updated["fast_screening"] = result.get("fast_screening", {})
    updated["adjudication"] = adjudication
    updated["verification"] = {
        "quote_verified": quote_verified,
        "verified_supported_context_count": len(verified_contexts),
        "verified_supported_contexts": verified_contexts,
        "routing_tags": normalize_routing_tags(adjudication.get("routing_tags", [])),
        "semantic_auto_eligible": flat["semantic_auto_eligible"],
        "download_queue_eligible": flat["download_queue_eligible"],
    }
    updated["heuristic_comparison"] = {
        "relevance": heuristic.get("relevance_suggested", ""),
        "screening_status": heuristic.get("screening_status", ""),
        "matched_context_count": heuristic.get("matched_context_count", ""),
        "relevance_disagreement": flat["heuristic_llm_relevance_disagreement"],
    }
    updated["flat"] = flat
    return updated


def queue_rows_from_results(results: List[dict], relevance_filter: set[str], require_verified_context: bool) -> List[dict]:
    rows = []
    seen = set()
    for result in results:
        flat = result.get("flat", {})
        if flat.get("status") != "ok":
            continue
        adjudication = result.get("adjudication", {})
        if normalize(adjudication.get("relevance", "")) not in relevance_filter:
            continue
        if not flat.get("download_queue_eligible") and not require_verified_context:
            continue
        input_row = result.get("input_row", {})
        contexts = result.get("verification", {}).get("verified_supported_contexts", [])
        if require_verified_context and not contexts:
            continue
        if contexts:
            for ctx in contexts:
                key = (
                    normalize(input_row.get("study_doi", "")).lower(),
                    normalize(ctx.get("compound", "")).lower(),
                    normalize(ctx.get("entity", "")).lower(),
                )
                if key in seen:
                    continue
                seen.add(key)
                rows.append(
                    {
                        "study_doi": normalize(input_row.get("study_doi", "")),
                        "compound": normalize(ctx.get("compound", "")),
                        "entity": normalize(ctx.get("entity", "")),
                        "study_title": normalize(input_row.get("study_title", "")),
                        "study_year": normalize(input_row.get("study_year", "")),
                        "authors": normalize(input_row.get("authors", "")),
                        **paper_metadata_from_row(input_row),
                    }
                )
            continue
        key = (normalize(input_row.get("study_doi", "")).lower(), "", "")
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            {
                "study_doi": normalize(input_row.get("study_doi", "")),
                "compound": "",
                "entity": "",
                "study_title": normalize(input_row.get("study_title", "")),
                "study_year": normalize(input_row.get("study_year", "")),
                "authors": normalize(input_row.get("authors", "")),
                **paper_metadata_from_row(input_row),
            }
        )
    return rows


def default_checkpoint_jsonl_path(out_json: Path) -> Path:
    return out_json.parent / f"{out_json.stem}.checkpoint.jsonl"


def truncate_checkpoint(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")


def append_checkpoint_result(path: Path, result: dict) -> None:
    """Append one completed screening row (full `result` dict) for crash-safe runs."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(result, ensure_ascii=False) + "\n")
        handle.flush()
        try:
            os.fsync(handle.fileno())
        except OSError:
            pass


def load_checkpoint_results(path: Path) -> dict[str, dict]:
    """Map normalized DOI (lower) -> last parsed result object from JSONL."""
    if not path.exists():
        return {}
    out: dict[str, dict] = {}
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if not isinstance(rec, dict):
                continue
            input_row = rec.get("input_row", {})
            if not isinstance(input_row, dict):
                continue
            doi = normalize_doi(input_row.get("study_doi", "")).lower()
            if doi:
                out[doi] = rec
    return out


def load_report_rows(path: Path) -> list[dict]:
    """Load result rows from an existing screening report while preserving order."""
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    rows = payload.get("rows", []) if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        return []
    return [rec for rec in rows if isinstance(rec, dict)]


def result_doi(result: dict) -> str:
    input_row = result.get("input_row", {}) if isinstance(result, dict) else {}
    flat = result.get("flat", {}) if isinstance(result, dict) else {}
    doi = ""
    if isinstance(input_row, dict):
        doi = normalize_doi(input_row.get("study_doi", "")).lower()
    if not doi and isinstance(flat, dict):
        doi = normalize_doi(flat.get("study_doi", "")).lower()
    return doi


def load_report_results(path: Path) -> dict[str, dict]:
    """Map normalized DOI (lower) -> result object from an existing screening report."""
    rows = load_report_rows(path)
    if not rows:
        return {}

    out: dict[str, dict] = {}
    for rec in rows:
        doi = result_doi(rec)
        if doi:
            out[doi] = rec
    return out


def merge_report_rows(base_rows: list[dict], merge_paths: List[Path]) -> tuple[list[dict], dict[str, int]]:
    rows = list(base_rows)
    index_by_doi = {doi: idx for idx, row in enumerate(rows) if (doi := result_doi(row))}
    summary = {
        "merge_reports_loaded": 0,
        "merge_report_rows_loaded": 0,
        "merge_report_rows_added": 0,
        "merge_report_rows_replaced": 0,
        "merge_report_rows_without_doi": 0,
    }

    for path in merge_paths:
        merge_rows = load_report_rows(path)
        summary["merge_reports_loaded"] += 1
        summary["merge_report_rows_loaded"] += len(merge_rows)
        for row in merge_rows:
            doi = result_doi(row)
            if not doi:
                rows.append(row)
                summary["merge_report_rows_without_doi"] += 1
                continue
            existing_idx = index_by_doi.get(doi)
            if existing_idx is None:
                index_by_doi[doi] = len(rows)
                rows.append(row)
                summary["merge_report_rows_added"] += 1
            else:
                rows[existing_idx] = row
                summary["merge_report_rows_replaced"] += 1
    return rows, summary


def checkpoint_result_is_compatible(result: dict) -> bool:
    """Return false for checkpoint rows that use labels outside the current schema."""
    if result.get("flat", {}).get("status") != "ok":
        return True
    adjudication = result.get("adjudication", {})
    if not isinstance(adjudication, dict):
        return False
    enum_fields = {"relevance": set(RELEVANCE_VALUES)}
    if not all(normalize(adjudication.get(field, "")) in allowed for field, allowed in enum_fields.items()):
        return False
    raw_tags = adjudication.get("routing_tags", [])
    if raw_tags in ("", None):
        return True
    if not isinstance(raw_tags, list):
        return False
    return len(normalize_routing_tags(raw_tags)) == len(raw_tags)


def paper_lookup_by_doi(papers: List[dict]) -> dict[str, tuple[int, dict]]:
    out: dict[str, tuple[int, dict]] = {}
    for row_index, row in enumerate(papers, start=1):
        doi = normalize_doi(row.get("study_doi", "")).lower()
        if doi and doi not in out:
            out[doi] = (row_index, row)
    return out


def refresh_result_metadata(result: dict, dataset: str, row_index: int | None, paper_row: dict | None) -> dict:
    """Refresh bibliographic metadata without changing LLM decisions or eligibility gates."""
    updated = dict(result)
    input_row = dict(result.get("input_row", {}) if isinstance(result.get("input_row", {}), dict) else {})
    flat = dict(result.get("flat", {}) if isinstance(result.get("flat", {}), dict) else {})
    source = paper_row or input_row

    if paper_row is not None:
        input_row = screening_input_row(row_index or int(flat.get("row_index") or 0), paper_row)
        updated["input_row"] = input_row

    preferred_row_index = row_index if row_index is not None else flat.get("row_index", input_row.get("row_index", ""))
    base_fields = {
        "dataset": dataset or flat.get("dataset", ""),
        "row_index": preferred_row_index,
        "study_doi": normalize_doi(source.get("study_doi", flat.get("study_doi", ""))),
        "study_title": normalize(source.get("study_title", flat.get("study_title", ""))),
        "study_year": normalize(source.get("study_year", flat.get("study_year", ""))),
        "authors": normalize(source.get("authors", flat.get("authors", ""))),
        "library_status": normalize(source.get("library_status", flat.get("library_status", ""))),
        "pdf_download_status": normalize(source.get("pdf_download_status", flat.get("pdf_download_status", ""))),
    }
    if paper_row is not None or "abstract" in source:
        base_fields["has_abstract"] = bool(normalize(source.get("abstract", "")))

    for field, value in base_fields.items():
        if value != "" or field not in flat:
            flat[field] = value

    for field in PAPER_METADATA_FIELDS:
        value = normalize(source.get(field, ""))
        if value or field not in flat:
            flat[field] = value
        if value or field not in input_row:
            input_row[field] = value

    if "authors" not in input_row or normalize(source.get("authors", "")):
        input_row["authors"] = normalize(source.get("authors", input_row.get("authors", "")))

    updated["input_row"] = input_row
    updated["flat"] = flat
    return updated


def safe_output_label(label: str) -> str:
    text = normalize(label)
    if not text:
        return ""
    text = re.sub(r"[^A-Za-z0-9_.-]+", "_", text)
    return text.strip("._-")


def load_reprocess_doi_set(path: Path) -> set[str]:
    """One DOI per line (comments with # and blank lines ignored). Values normalized to lower DOI."""
    if not path.is_file():
        raise SystemExit(f"--reprocess-dois-file not found: {path}")
    out: set[str] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        doi = normalize_doi(line).lower()
        if doi:
            out.add(doi)
    return out


def read_doi_file(path: Path) -> set[str]:
    """Read DOI queues where the DOI is the first CSV/text column."""
    if not path.is_file():
        raise SystemExit(f"DOI file not found: {path}")
    out: set[str] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        doi = normalize_doi(line.split(",", 1)[0]).lower()
        if doi:
            out.add(doi)
    return out


def write_doi_queue(path: Path, rows: List[dict], description: str) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(f"# {description} generated at {now_utc()}\n")
        handle.write(
            "# doi,compound,target_or_disorder,optional_study_title,optional_study_year,"
            "optional_authors,"
            + ",".join(f"optional_{field}" for field in PAPER_METADATA_FIELDS)
            + "\n"
        )
        writer = csv.writer(handle)
        for row in rows:
            doi = normalize_doi(row.get("study_doi", ""))
            if not doi:
                continue
            writer.writerow(
                [
                    doi,
                    normalize(row.get("compound", "")),
                    normalize(row.get("entity", "")),
                    normalize(row.get("study_title", "")),
                    normalize(row.get("study_year", "")),
                    normalize(row.get("authors", "")),
                    *[normalize(row.get(field, "")) for field in PAPER_METADATA_FIELDS],
                ]
            )
    return len(rows)


PRESCREEN_CSV_FIELDS = [
    "dataset",
    "row_index",
    "study_doi",
    "study_title",
    "study_year",
    "has_abstract",
    "pdf_download_status",
    "deterministic_prescreen_action",
    "deterministic_prescreen_reason",
    "deterministic_prescreen_routing_tags",
    "retained_for_llm",
    "candidate_context_count",
    "heuristic_relevance",
    "heuristic_screening_status",
    "heuristic_matched_context_count",
]


def write_prescreen_csv(path: Path, rows: List[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=PRESCREEN_CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in PRESCREEN_CSV_FIELDS})


def prescreen_queue_row(row: dict) -> dict:
    return {
        "study_doi": normalize_doi(row.get("study_doi", "")),
        "compound": "",
        "entity": "",
        "study_title": normalize(row.get("study_title", "")),
        "study_year": normalize(row.get("study_year", "")),
        "authors": normalize(row.get("authors", "")),
        **paper_metadata_from_row(row),
    }


def run_deterministic_prescreen_only_dataset(
    dataset: str,
    args: argparse.Namespace,
    paper_db_json: Path,
    triage_report: Path | None,
    paths: dict[str, Path],
    papers_all: List[dict],
    papers_filtered: List[tuple[int, dict]],
    selected: List[tuple[int, dict]],
    triage_by_doi: dict[str, dict],
    doi_filter: set[str] | None,
) -> dict:
    rows = []
    retained_queue = []
    excluded_queue = []
    for row_index, row in selected:
        doi = normalize_doi(row.get("study_doi", ""))
        heuristic = triage_by_doi.get(doi.lower(), {}) if doi else {}
        candidate_contexts = compact_candidate_contexts(row, max_contexts=max(1, args.max_contexts))
        decision = deterministic_prescreen_decision(dataset, row, heuristic, candidate_contexts)
        retained = decision.get("action") != "exclude_obvious_irrelevant"
        queue_row = prescreen_queue_row(row)
        if retained:
            retained_queue.append(queue_row)
        else:
            excluded_queue.append(queue_row)
        rows.append(
            {
                "dataset": dataset,
                "row_index": row_index,
                "study_doi": doi,
                "study_title": normalize(row.get("study_title", "")),
                "study_year": normalize(row.get("study_year", "")),
                "authors": normalize(row.get("authors", "")),
                "has_abstract": bool(normalize(row.get("abstract", ""))),
                "pdf_download_status": normalize(row.get("pdf_download_status", "")),
                "deterministic_prescreen_action": decision.get("action", ""),
                "deterministic_prescreen_reason": decision.get("reason", ""),
                "deterministic_prescreen_routing_tags": "|".join(normalize_routing_tags(decision.get("routing_tags", []))),
                "deterministic_prescreen_supporting_quote": decision.get("supporting_quote", ""),
                "retained_for_llm": retained,
                "candidate_context_count": len(candidate_contexts),
                "heuristic_relevance": heuristic.get("relevance_suggested", ""),
                "heuristic_screening_status": heuristic.get("screening_status", ""),
                "heuristic_matched_context_count": heuristic.get("matched_context_count", ""),
            }
        )

    retained_written = write_doi_queue(
        paths["prescreen_retained_queue"],
        retained_queue,
        f"Deterministic prescreen retained queue for {dataset}",
    )
    excluded_written = write_doi_queue(
        paths["prescreen_excluded_queue"],
        excluded_queue,
        f"Deterministic prescreen excluded queue for {dataset}",
    )
    write_prescreen_csv(paths["prescreen_csv"], rows)
    summary = {
        "papers_total": len(papers_all),
        "rows_after_filters": len(papers_filtered),
        "rows_requested": len(selected),
        "retained_for_llm": retained_written,
        "deterministic_excluded": excluded_written,
        "by_action": dict(Counter(row.get("deterministic_prescreen_action", "") for row in rows)),
    }
    payload = {
        "generated_at_utc": now_utc(),
        "status": "ok",
        "dataset": dataset,
        "mode": "deterministic_prescreen_only",
        "inputs": {
            "paper_db_json": str(paper_db_json),
            "doi_file": normalize(args.doi_file) or None,
            "doi_filter_count": len(doi_filter) if doi_filter is not None else None,
            "triage_report_json": str(triage_report) if triage_report else None,
            "use_heuristic_audit": bool(args.use_heuristic_audit or args.triage_report_json),
            "limit": args.limit,
            "offset": args.offset,
            "only_with_abstract": args.only_with_abstract,
            "only_undownloaded": args.only_undownloaded,
        },
        "outputs": {
            "report_json": str(paths["prescreen_json"]),
            "report_csv": str(paths["prescreen_csv"]),
            "retained_queue": str(paths["prescreen_retained_queue"]),
            "excluded_queue": str(paths["prescreen_excluded_queue"]),
        },
        "summary": summary,
        "rows": rows,
    }
    write_json(paths["prescreen_json"], payload)
    print(f"Dataset: {dataset}")
    print("Mode: deterministic prescreen only")
    print(f"Rows requested: {summary['rows_requested']}")
    print(f"Retained for LLM: {retained_written}")
    print(f"Deterministic excluded: {excluded_written}")
    print(f"Actions: {summary['by_action']}")
    print(f"Report JSON: {paths['prescreen_json']}")
    print(f"Report CSV: {paths['prescreen_csv']}")
    print(f"Retained queue: {paths['prescreen_retained_queue']}")
    print(f"Excluded queue: {paths['prescreen_excluded_queue']}")
    return payload


def run_checkpoint_materialization_dataset(
    dataset: str,
    args: argparse.Namespace,
    paper_db_json: Path,
    triage_report: Path | None,
    paths: dict[str, Path],
    papers_all: List[dict],
    papers_filtered: List[tuple[int, dict]],
    selected: List[tuple[int, dict]],
    triage_by_doi: dict[str, dict],
    doi_filter: set[str] | None,
    ckpt_path: Path,
) -> dict:
    checkpoint_by_doi = load_checkpoint_results(ckpt_path)
    report_fallback_json = (
        Path(args.report_fallback_json).resolve()
        if normalize(args.report_fallback_json)
        else paths["out_json"]
    )
    report_fallback_by_doi = load_report_results(report_fallback_json)
    results = []
    flat_rows = []
    missing_checkpoint = []
    incompatible_checkpoint = []
    checkpoint_materialized = 0
    report_fallback_materialized = 0

    for row_index, row in selected:
        doi = normalize_doi(row.get("study_doi", ""))
        doi_key = doi.lower()
        checkpoint_result = checkpoint_by_doi.get(doi_key) if doi_key else None
        result_source = "checkpoint"
        if not checkpoint_result:
            checkpoint_result = report_fallback_by_doi.get(doi_key) if doi_key else None
            result_source = "report_fallback"
            if not checkpoint_result:
                missing_checkpoint.append(doi)
                continue
        if not checkpoint_result_is_compatible(checkpoint_result):
            incompatible_checkpoint.append(doi)
            continue
        heuristic = triage_by_doi.get(doi_key, {}) if doi_key else {}
        result = revalidate_checkpoint_result(
            dataset=dataset,
            row_index=row_index,
            row=row,
            heuristic=heuristic,
            result=checkpoint_result,
            args=args,
        )
        results.append(result)
        flat_rows.append(result["flat"])
        if result_source == "report_fallback":
            report_fallback_materialized += 1
        else:
            checkpoint_materialized += 1

    download_rows = queue_rows_from_results(results, relevance_filter={"relevant", "uncertain"}, require_verified_context=False)
    relevant_rows = queue_rows_from_results(results, relevance_filter={"relevant"}, require_verified_context=True)
    uncertain_rows = queue_rows_from_results(results, relevance_filter={"uncertain"}, require_verified_context=False)
    download_written = write_doi_queue(paths["download_queue"], download_rows, f"LLM full-text candidate queue for {dataset}")
    relevant_written = write_doi_queue(paths["relevant_queue"], relevant_rows, f"LLM verified relevant context queue for {dataset}")
    uncertain_written = write_doi_queue(paths["uncertain_queue"], uncertain_rows, f"LLM uncertain full-text candidate queue for {dataset}")

    status = "ok" if not missing_checkpoint and not incompatible_checkpoint else "completed_with_missing_checkpoint_rows"
    summary = {
        "papers_total": len(papers_all),
        "rows_after_filters": len(papers_filtered),
        "rows_requested": len(selected),
        "rows_completed": len([row for row in flat_rows if row.get("status") == "ok"]),
        "rows_failed": len([row for row in flat_rows if row.get("status") != "ok"]),
        "checkpoint_rows_loaded": len(checkpoint_by_doi),
        "report_fallback_rows_loaded": len(report_fallback_by_doi),
        "rows_materialized": len(results),
        "checkpoint_rows_materialized": checkpoint_materialized,
        "report_fallback_rows_materialized": report_fallback_materialized,
        "checkpoint_rows_missing_for_selection": len(missing_checkpoint),
        "checkpoint_rows_incompatible": len(incompatible_checkpoint),
        "quote_verified": len([row for row in flat_rows if row.get("quote_verified") is True]),
        "semantic_auto_eligible": len([row for row in flat_rows if row.get("semantic_auto_eligible") is True]),
        "download_queue_eligible": len([row for row in flat_rows if row.get("download_queue_eligible") is True]),
        "download_queue_rows_written": download_written,
        "relevant_context_queue_rows_written": relevant_written,
        "uncertain_queue_rows_written": uncertain_written,
        "deterministic_prescreen_excluded": len(
            [row for row in flat_rows if row.get("screening_path") == "deterministic_excluded"]
        ),
        "fast_screen_excluded": len([row for row in flat_rows if row.get("screening_path") == "fast_excluded"]),
        "fast_screen_escalated": len([row for row in flat_rows if row.get("screening_path") == "fast_escalated"]),
        "by_status": dict(Counter(row.get("status", "") for row in flat_rows)),
        "by_llm_relevance": dict(Counter(row.get("llm_relevance", "") for row in flat_rows)),
        "by_routing_tag": routing_tag_counts(flat_rows),
        "by_screening_path": dict(Counter(row.get("screening_path", "") for row in flat_rows)),
        "heuristic_llm_relevance_disagreements": len(
            [row for row in flat_rows if row.get("heuristic_llm_relevance_disagreement") is True]
        ),
    }
    payload = {
        "generated_at_utc": now_utc(),
        "status": status,
        "dataset": dataset,
        "mode": "materialize_checkpoint_only",
        "inputs": {
            "paper_db_json": str(paper_db_json),
            "triage_report_json": str(triage_report) if triage_report else None,
            "use_heuristic_audit": bool(args.use_heuristic_audit or args.triage_report_json),
            "model": args.model,
            "deterministic_prescreen": bool(args.deterministic_prescreen),
            "fast_screen_model": normalize(args.fast_screen_model) or None,
            "limit": args.limit,
            "offset": args.offset,
            "doi_file": normalize(args.doi_file) or None,
            "doi_filter_count": len(doi_filter) if doi_filter is not None else None,
            "only_with_abstract": args.only_with_abstract,
            "only_undownloaded": args.only_undownloaded,
            "only_heuristic_possible": args.only_heuristic_possible,
            "auto_confidence": args.auto_confidence,
            "context_confidence": args.context_confidence,
            "fast_screen_confidence": args.fast_screen_confidence,
        },
        "outputs": {
            "report_json": str(paths["out_json"]),
            "report_csv": str(paths["out_csv"]),
            "checkpoint_jsonl": str(ckpt_path),
            "report_fallback_json": str(report_fallback_json),
            "download_queue": str(paths["download_queue"]),
            "relevant_queue": str(paths["relevant_queue"]),
            "uncertain_queue": str(paths["uncertain_queue"]),
        },
        "summary": summary,
        "missing_checkpoint_dois": missing_checkpoint[:1000],
        "incompatible_checkpoint_dois": incompatible_checkpoint[:1000],
        "rows": results,
    }
    write_json(paths["out_json"], payload)
    write_csv(paths["out_csv"], flat_rows)

    print(f"Dataset: {dataset}")
    print("Mode: materialize checkpoint only")
    print(f"Status: {status}")
    print(f"Checkpoint rows loaded: {len(checkpoint_by_doi)}")
    print(f"Report fallback rows loaded: {len(report_fallback_by_doi)}")
    print(f"Rows materialized: {len(results)}")
    print(f"Rows materialized from report fallback: {report_fallback_materialized}")
    print(f"Rows missing from checkpoint for this selection: {len(missing_checkpoint)}")
    print(f"Checkpoint rows incompatible: {len(incompatible_checkpoint)}")
    print(f"LLM relevance: {summary['by_llm_relevance']}")
    print(f"Routing tags: {summary['by_routing_tag']}")
    print(f"Download queue rows: {download_written}")
    print(f"Relevant context queue rows: {relevant_written}")
    print(f"Uncertain queue rows: {uncertain_written}")
    print(f"Report JSON: {paths['out_json']}")
    print(f"Report CSV: {paths['out_csv']}")
    print(f"Checkpoint JSONL: {ckpt_path}")
    return payload


def run_report_metadata_refresh_dataset(
    dataset: str,
    args: argparse.Namespace,
    paper_db_json: Path,
    paths: dict[str, Path],
    papers_all: List[dict],
) -> dict:
    source_report_json = (
        Path(args.report_fallback_json).resolve()
        if normalize(args.report_fallback_json)
        else paths["out_json"]
    )
    merge_report_paths = [Path(path).resolve() for path in args.merge_report_json if normalize(path)]
    source_rows = load_report_rows(source_report_json)
    rows, merge_summary = merge_report_rows(source_rows, merge_report_paths)
    paper_by_doi = paper_lookup_by_doi(papers_all)
    results = []
    missing_paper_rows = []
    refreshed = 0

    for result in rows:
        flat = result.get("flat", {}) if isinstance(result.get("flat", {}), dict) else {}
        input_row = result.get("input_row", {}) if isinstance(result.get("input_row", {}), dict) else {}
        doi = normalize_doi(input_row.get("study_doi", "") or flat.get("study_doi", ""))
        paper_match = paper_by_doi.get(doi.lower()) if doi else None
        if paper_match:
            row_index, paper_row = paper_match
            results.append(refresh_result_metadata(result, dataset=dataset, row_index=row_index, paper_row=paper_row))
            refreshed += 1
        else:
            if doi:
                missing_paper_rows.append(doi)
            results.append(refresh_result_metadata(result, dataset=dataset, row_index=None, paper_row=None))

    flat_rows = [result.get("flat", {}) for result in results]
    download_rows = queue_rows_from_results(results, relevance_filter={"relevant", "uncertain"}, require_verified_context=False)
    relevant_rows = queue_rows_from_results(results, relevance_filter={"relevant"}, require_verified_context=True)
    uncertain_rows = queue_rows_from_results(results, relevance_filter={"uncertain"}, require_verified_context=False)
    download_written = write_doi_queue(paths["download_queue"], download_rows, f"LLM full-text candidate queue for {dataset}")
    relevant_written = write_doi_queue(paths["relevant_queue"], relevant_rows, f"LLM verified relevant context queue for {dataset}")
    uncertain_written = write_doi_queue(paths["uncertain_queue"], uncertain_rows, f"LLM uncertain full-text candidate queue for {dataset}")

    status = "ok" if not missing_paper_rows else "completed_with_missing_paper_rows"
    summary = {
        "papers_total": len(papers_all),
        "source_report_rows": len(source_rows),
        "rows_after_merge": len(rows),
        "rows_materialized": len(results),
        "rows_metadata_refreshed": refreshed,
        "rows_missing_from_paper_library": len(missing_paper_rows),
        "rows_completed": len([row for row in flat_rows if row.get("status") == "ok"]),
        "rows_failed": len([row for row in flat_rows if row.get("status") != "ok"]),
        "download_queue_rows_written": download_written,
        "relevant_context_queue_rows_written": relevant_written,
        "uncertain_queue_rows_written": uncertain_written,
        "by_status": dict(Counter(row.get("status", "") for row in flat_rows)),
        "by_llm_relevance": dict(Counter(row.get("llm_relevance", "") for row in flat_rows)),
        "by_routing_tag": routing_tag_counts(flat_rows),
        **merge_summary,
    }
    payload = {
        "generated_at_utc": now_utc(),
        "status": status,
        "dataset": dataset,
        "mode": "refresh_report_metadata_only",
        "inputs": {
            "paper_db_json": str(paper_db_json),
            "source_report_json": str(source_report_json),
            "merge_report_json": [str(path) for path in merge_report_paths],
        },
        "outputs": {
            "report_json": str(paths["out_json"]),
            "report_csv": str(paths["out_csv"]),
            "download_queue": str(paths["download_queue"]),
            "relevant_queue": str(paths["relevant_queue"]),
            "uncertain_queue": str(paths["uncertain_queue"]),
        },
        "summary": summary,
        "missing_paper_row_dois": missing_paper_rows[:1000],
        "rows": results,
    }
    write_json(paths["out_json"], payload)
    write_csv(paths["out_csv"], flat_rows)

    print(f"Dataset: {dataset}")
    print("Mode: refresh report metadata only")
    print(f"Status: {status}")
    print(f"Source report rows: {len(source_rows)}")
    print(f"Rows after merge: {len(rows)}")
    print(f"Merge report rows added: {merge_summary['merge_report_rows_added']}")
    print(f"Merge report rows replaced: {merge_summary['merge_report_rows_replaced']}")
    print(f"Rows metadata-refreshed from paper library: {refreshed}")
    print(f"Rows missing from paper library: {len(missing_paper_rows)}")
    print(f"LLM relevance: {summary['by_llm_relevance']}")
    print(f"Routing tags: {summary['by_routing_tag']}")
    print(f"Download queue rows: {download_written}")
    print(f"Relevant context queue rows: {relevant_written}")
    print(f"Uncertain queue rows: {uncertain_written}")
    print(f"Report JSON: {paths['out_json']}")
    print(f"Report CSV: {paths['out_csv']}")
    return payload


def dataset_paths(dataset: str, args: argparse.Namespace) -> dict[str, Path]:
    label = safe_output_label(getattr(args, "prescreen_output_label", ""))
    prescreen_report_stem = f"deterministic_prescreen_report_{dataset}"
    prescreen_retained_name = f"doi_queue.{dataset}.deterministic_prescreen_retained"
    prescreen_excluded_name = f"doi_queue.{dataset}.deterministic_prescreen_excluded"
    if label:
        prescreen_report_stem = f"{prescreen_report_stem}.{label}"
        prescreen_retained_name = f"{prescreen_retained_name}.{label}"
        prescreen_excluded_name = f"{prescreen_excluded_name}.{label}"
    if args.dataset != "all":
        return {
            "out_json": Path(args.out_json).resolve() if args.out_json else ROOT / "data" / "processed" / f"llm_abstract_screening_report_{dataset}.json",
            "out_csv": Path(args.out_csv).resolve() if args.out_csv else ROOT / "data" / "processed" / f"llm_abstract_screening_report_{dataset}.csv",
            "download_queue": Path(args.download_queue_out).resolve()
            if args.download_queue_out
            else ROOT / "data" / "raw" / f"doi_queue.{dataset}.llm_fulltext_candidates.txt",
            "relevant_queue": Path(args.relevant_queue_out).resolve()
            if args.relevant_queue_out
            else ROOT / "data" / "raw" / f"doi_queue.{dataset}.llm_relevant.txt",
            "uncertain_queue": Path(args.uncertain_queue_out).resolve()
            if args.uncertain_queue_out
            else ROOT / "data" / "raw" / f"doi_queue.{dataset}.llm_uncertain.txt",
            "prescreen_json": Path(args.prescreen_json_out).resolve()
            if args.prescreen_json_out
            else ROOT / "data" / "processed" / f"{prescreen_report_stem}.json",
            "prescreen_csv": Path(args.prescreen_csv_out).resolve()
            if args.prescreen_csv_out
            else ROOT / "data" / "processed" / f"{prescreen_report_stem}.csv",
            "prescreen_retained_queue": Path(args.prescreen_retained_queue_out).resolve()
            if args.prescreen_retained_queue_out
            else ROOT / "data" / "raw" / f"{prescreen_retained_name}.txt",
            "prescreen_excluded_queue": Path(args.prescreen_excluded_queue_out).resolve()
            if args.prescreen_excluded_queue_out
            else ROOT / "data" / "raw" / f"{prescreen_excluded_name}.txt",
        }
    return {
        "out_json": ROOT / "data" / "processed" / f"llm_abstract_screening_report_{dataset}.json",
        "out_csv": ROOT / "data" / "processed" / f"llm_abstract_screening_report_{dataset}.csv",
        "download_queue": ROOT / "data" / "raw" / f"doi_queue.{dataset}.llm_fulltext_candidates.txt",
        "relevant_queue": ROOT / "data" / "raw" / f"doi_queue.{dataset}.llm_relevant.txt",
        "uncertain_queue": ROOT / "data" / "raw" / f"doi_queue.{dataset}.llm_uncertain.txt",
        "prescreen_json": ROOT / "data" / "processed" / f"{prescreen_report_stem}.json",
        "prescreen_csv": ROOT / "data" / "processed" / f"{prescreen_report_stem}.csv",
        "prescreen_retained_queue": ROOT / "data" / "raw" / f"{prescreen_retained_name}.txt",
        "prescreen_excluded_queue": ROOT / "data" / "raw" / f"{prescreen_excluded_name}.txt",
    }


def run_dataset(dataset: str, args: argparse.Namespace) -> dict:
    cfg = DATASET_CONFIG[dataset]
    paper_db_json = Path(args.paper_db_json).resolve() if args.paper_db_json and args.dataset != "all" else cfg["paper_db_json"]
    triage_report = None
    if args.triage_report_json and args.dataset != "all":
        triage_report = Path(args.triage_report_json).resolve()
    elif args.use_heuristic_audit:
        triage_report = ROOT / "data" / "processed" / f"triage_report_{dataset}.json"
    paths = dataset_paths(dataset, args)
    if args.resume_from_checkpoint and args.no_checkpoint:
        raise SystemExit("--resume-from-checkpoint and --no-checkpoint cannot be used together")
    if args.refresh_report_metadata_only and args.materialize_checkpoint_only:
        raise SystemExit("Use only one of --refresh-report-metadata-only or --materialize-checkpoint-only")
    if args.materialize_checkpoint_only and args.no_checkpoint:
        raise SystemExit("--materialize-checkpoint-only requires checkpointing to be enabled")
    if (normalize(args.reprocess_dois_file) or args.reprocess_all_checkpoint_dois) and not args.resume_from_checkpoint:
        raise SystemExit("--reprocess-dois-file / --reprocess-all-checkpoint-dois require --resume-from-checkpoint")
    if normalize(args.reprocess_dois_file) and args.reprocess_all_checkpoint_dois:
        raise SystemExit("Use only one of --reprocess-dois-file or --reprocess-all-checkpoint-dois")
    ckpt_path = (
        Path(args.checkpoint_jsonl).resolve()
        if normalize(args.checkpoint_jsonl)
        else default_checkpoint_jsonl_path(paths["out_json"])
    )
    papers_all = load_json_array(paper_db_json)
    if args.refresh_report_metadata_only:
        return run_report_metadata_refresh_dataset(
            dataset=dataset,
            args=args,
            paper_db_json=paper_db_json,
            paths=paths,
            papers_all=papers_all,
        )
    triage_by_doi = load_triage_by_doi(triage_report) if triage_report else {}
    if args.only_heuristic_possible and not triage_by_doi:
        raise SystemExit("--only-heuristic-possible requires --use-heuristic-audit or --triage-report-json")
    doi_filter = read_doi_file(Path(args.doi_file).resolve()) if normalize(args.doi_file) else None
    papers_filtered = filter_indexed_rows(
        list(enumerate(papers_all, start=1)),
        triage_by_doi=triage_by_doi,
        args=args,
        doi_filter=doi_filter,
    )
    selected = selected_rows(papers_filtered, limit=max(0, args.limit), offset=max(0, args.offset))
    if args.deterministic_prescreen_only:
        return run_deterministic_prescreen_only_dataset(
            dataset=dataset,
            args=args,
            paper_db_json=paper_db_json,
            triage_report=triage_report,
            paths=paths,
            papers_all=papers_all,
            papers_filtered=papers_filtered,
            selected=selected,
            triage_by_doi=triage_by_doi,
            doi_filter=doi_filter,
        )
    if args.materialize_checkpoint_only:
        return run_checkpoint_materialization_dataset(
            dataset=dataset,
            args=args,
            paper_db_json=paper_db_json,
            triage_report=triage_report,
            paths=paths,
            papers_all=papers_all,
            papers_filtered=papers_filtered,
            selected=selected,
            triage_by_doi=triage_by_doi,
            doi_filter=doi_filter,
            ckpt_path=ckpt_path,
        )

    checkpoint_by_doi: dict[str, dict] = {}
    if args.resume_from_checkpoint:
        checkpoint_by_doi = load_checkpoint_results(ckpt_path)
        n_loaded = len(checkpoint_by_doi)
        print(f"Checkpoint resume: {n_loaded} row(s) from {ckpt_path}", flush=True)
        if args.reprocess_all_checkpoint_dois:
            checkpoint_by_doi = {}
            print(
                f"Reprocess all checkpointed DOIs: cleared {n_loaded} resume skip(s); LLM will run for every row in this batch.",
                flush=True,
            )
        elif normalize(args.reprocess_dois_file):
            rpath = Path(args.reprocess_dois_file).resolve()
            rset = load_reprocess_doi_set(rpath)
            removed = 0
            for k in rset:
                if checkpoint_by_doi.pop(k, None) is not None:
                    removed += 1
            print(
                f"Reprocess list {rpath}: {len(rset)} DOI(s) listed, {removed} were in checkpoint (those rows will call the LLM again).",
                flush=True,
            )
    elif not args.no_checkpoint and not args.dry_run:
        truncate_checkpoint(ckpt_path)
        print(f"Checkpoint file (fresh): {ckpt_path}", flush=True)

    results = []
    flat_rows = []
    status = "ok"
    checkpoint_rows_reused = 0
    checkpoint_rows_reprocessed = 0
    for local_index, (row_index, row) in enumerate(selected, start=1):
        doi = normalize_doi(row.get("study_doi", ""))
        doi_key = doi.lower()
        row_header_printed = False
        if (
            not args.no_checkpoint
            and not args.dry_run
            and doi_key
            and doi_key in checkpoint_by_doi
            and args.resume_from_checkpoint
        ):
            heuristic = triage_by_doi.get(doi.lower(), {}) if doi else {}
            checkpoint_result = checkpoint_by_doi[doi_key]
            if checkpoint_result_is_compatible(checkpoint_result):
                result = revalidate_checkpoint_result(
                    dataset=dataset,
                    row_index=row_index,
                    row=row,
                    heuristic=heuristic,
                    result=checkpoint_result,
                    args=args,
                )
                checkpoint_rows_reused += 1
                results.append(result)
                flat_rows.append(result["flat"])
                if args.show_checkpoint_progress:
                    print(f"[{dataset} {local_index}/{len(selected)}] {doi} (checkpoint)", flush=True)
                    if not args.quiet_progress:
                        print_screening_row_followup(result["flat"], None, source="checkpoint")
                continue
            checkpoint_rows_reprocessed += 1
            print(f"[{dataset} {local_index}/{len(selected)}] {doi} (checkpoint incompatible; reprocessing)", flush=True)
            row_header_printed = True

        if not row_header_printed:
            print(f"[{dataset} {local_index}/{len(selected)}] {doi}", flush=True)
        heuristic = triage_by_doi.get(doi.lower(), {}) if doi else {}
        t_row = time.perf_counter()
        try:
            result = screen_row(dataset, row_index=row_index, row=row, heuristic=heuristic, args=args)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, Exception) as err:
            elapsed = time.perf_counter() - t_row
            status = "failed"
            adjudication = {}
            context = abstract_context(row)
            quote_verified = False
            flat = flatten_result(
                dataset=dataset,
                row_index=row_index,
                row=row,
                adjudication=adjudication,
                status="failed",
                quote_verified=quote_verified,
                verified_contexts=[],
                heuristic=heuristic,
                args=args,
                error=f"{type(err).__name__}: {err}",
            )
            result = {
                "input_row": screening_input_row(row_index, row),
                "candidate_contexts": compact_candidate_contexts(row, max_contexts=max(1, args.max_contexts)),
                "adjudication": adjudication,
                "verification": {
                    "quote_verified": quote_verified,
                    "verified_supported_context_count": 0,
                    "verified_supported_contexts": [],
                    "routing_tags": [],
                    "semantic_auto_eligible": False,
                    "download_queue_eligible": False,
                    "context_char_count": len(context),
                },
                "heuristic_comparison": {},
                "error": f"{type(err).__name__}: {err}",
                "flat": flat,
            }
            if not args.continue_on_error:
                results.append(result)
                flat_rows.append(flat)
                if not args.no_checkpoint and not args.dry_run:
                    append_checkpoint_result(ckpt_path, result)
                if not args.quiet_progress:
                    print_screening_row_followup(flat, elapsed, source="llm")
                break
        else:
            elapsed = time.perf_counter() - t_row

        results.append(result)
        flat_rows.append(result["flat"])
        if not args.no_checkpoint and not args.dry_run:
            append_checkpoint_result(ckpt_path, result)
        if not args.quiet_progress:
            print_screening_row_followup(result["flat"], elapsed, source="llm")

    download_rows = queue_rows_from_results(results, relevance_filter={"relevant", "uncertain"}, require_verified_context=False)
    relevant_rows = queue_rows_from_results(results, relevance_filter={"relevant"}, require_verified_context=True)
    uncertain_rows = queue_rows_from_results(results, relevance_filter={"uncertain"}, require_verified_context=False)
    download_written = write_doi_queue(paths["download_queue"], download_rows, f"LLM full-text candidate queue for {dataset}")
    relevant_written = write_doi_queue(paths["relevant_queue"], relevant_rows, f"LLM verified relevant context queue for {dataset}")
    uncertain_written = write_doi_queue(paths["uncertain_queue"], uncertain_rows, f"LLM uncertain full-text candidate queue for {dataset}")

    summary = {
        "papers_total": len(papers_all),
        "rows_after_filters": len(papers_filtered),
        "rows_requested": len(selected),
        "rows_completed": len([row for row in flat_rows if row.get("status") == "ok"]),
        "rows_failed": len([row for row in flat_rows if row.get("status") != "ok"]),
        "checkpoint_rows_reused": checkpoint_rows_reused,
        "checkpoint_rows_reprocessed": checkpoint_rows_reprocessed,
        "quote_verified": len([row for row in flat_rows if row.get("quote_verified") is True]),
        "semantic_auto_eligible": len([row for row in flat_rows if row.get("semantic_auto_eligible") is True]),
        "download_queue_eligible": len([row for row in flat_rows if row.get("download_queue_eligible") is True]),
        "download_queue_rows_written": download_written,
        "relevant_context_queue_rows_written": relevant_written,
        "uncertain_queue_rows_written": uncertain_written,
        "deterministic_prescreen_excluded": len(
            [row for row in flat_rows if row.get("screening_path") == "deterministic_excluded"]
        ),
        "fast_screen_excluded": len([row for row in flat_rows if row.get("screening_path") == "fast_excluded"]),
        "fast_screen_escalated": len([row for row in flat_rows if row.get("screening_path") == "fast_escalated"]),
        "by_status": dict(Counter(row.get("status", "") for row in flat_rows)),
        "by_llm_relevance": dict(Counter(row.get("llm_relevance", "") for row in flat_rows)),
        "by_routing_tag": routing_tag_counts(flat_rows),
        "by_screening_path": dict(Counter(row.get("screening_path", "") for row in flat_rows)),
        "heuristic_llm_relevance_disagreements": len(
            [row for row in flat_rows if row.get("heuristic_llm_relevance_disagreement") is True]
        ),
    }
    if status == "failed" and args.continue_on_error and summary["rows_completed"] > 0:
        status = "completed_with_errors"
    payload = {
        "generated_at_utc": now_utc(),
        "status": status,
        "dataset": dataset,
        "inputs": {
            "paper_db_json": str(paper_db_json),
            "triage_report_json": str(triage_report) if triage_report else None,
            "use_heuristic_audit": bool(args.use_heuristic_audit or args.triage_report_json),
            "model": args.model,
            "deterministic_prescreen": bool(args.deterministic_prescreen),
            "fast_screen_model": normalize(args.fast_screen_model) or None,
            "ollama_url": args.ollama_url,
            "limit": args.limit,
            "offset": args.offset,
            "doi_file": normalize(args.doi_file) or None,
            "doi_filter_count": len(doi_filter) if doi_filter is not None else None,
            "dry_run": args.dry_run,
            "only_with_abstract": args.only_with_abstract,
            "only_undownloaded": args.only_undownloaded,
            "only_heuristic_possible": args.only_heuristic_possible,
            "auto_confidence": args.auto_confidence,
            "context_confidence": args.context_confidence,
            "fast_screen_confidence": args.fast_screen_confidence,
            "reprocess_dois_file": normalize(args.reprocess_dois_file) or None,
            "reprocess_all_checkpoint_dois": bool(args.reprocess_all_checkpoint_dois),
        },
        "outputs": {
            "report_json": str(paths["out_json"]),
            "report_csv": str(paths["out_csv"]),
            "checkpoint_jsonl": str(ckpt_path),
            "download_queue": str(paths["download_queue"]),
            "relevant_queue": str(paths["relevant_queue"]),
            "uncertain_queue": str(paths["uncertain_queue"]),
        },
        "summary": summary,
        "rows": results,
    }
    write_json(paths["out_json"], payload)
    write_csv(paths["out_csv"], flat_rows)

    print(f"Dataset: {dataset}")
    print(f"Status: {status}")
    print(f"Rows completed: {summary['rows_completed']}")
    print(f"Rows failed: {summary['rows_failed']}")
    if args.resume_from_checkpoint:
        print(f"Checkpoint rows reused: {checkpoint_rows_reused}")
        print(f"Checkpoint rows reprocessed: {checkpoint_rows_reprocessed}")
    print(f"LLM relevance: {summary['by_llm_relevance']}")
    print(f"Routing tags: {summary['by_routing_tag']}")
    if args.deterministic_prescreen or normalize(args.fast_screen_model):
        print(f"Screening paths: {summary['by_screening_path']}")
    print(f"Quote verified: {summary['quote_verified']}")
    print(f"Semantic auto-eligible: {summary['semantic_auto_eligible']}")
    print(f"Download queue rows: {download_written}")
    print(f"Relevant context queue rows: {relevant_written}")
    print(f"Uncertain queue rows: {uncertain_written}")
    print(f"Report JSON: {paths['out_json']}")
    print(f"Report CSV: {paths['out_csv']}")
    if not args.no_checkpoint:
        print(f"Checkpoint JSONL: {ckpt_path}")
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", choices=[*DATASETS, "all"], required=True)
    parser.add_argument("--paper-db-json", default="", help="Override paper library JSON path; only valid for one dataset")
    parser.add_argument("--triage-report-json", default="", help="Optional existing heuristic triage report for comparison")
    parser.add_argument(
        "--use-heuristic-audit",
        action="store_true",
        help="Opt in to loading the old heuristic triage report for audit/safety comparison",
    )
    parser.add_argument("--out-json", default="", help="Output JSON path; only valid for one dataset")
    parser.add_argument("--out-csv", default="", help="Output CSV path; only valid for one dataset")
    parser.add_argument("--download-queue-out", default="", help="DOI-level full-text candidate queue; only valid for one dataset")
    parser.add_argument("--relevant-queue-out", default="", help="Verified relevant context queue; only valid for one dataset")
    parser.add_argument("--uncertain-queue-out", default="", help="Uncertain candidate queue; only valid for one dataset")
    parser.add_argument(
        "--prescreen-output-label",
        default="",
        help=(
            "Optional label for deterministic prescreen outputs. For example, "
            "`boolean_full_v1` writes deterministic_prescreen_report_<dataset>.boolean_full_v1.* "
            "and label-suffixed retained/excluded queues instead of the global prescreen files."
        ),
    )
    parser.add_argument("--prescreen-json-out", default="", help="Deterministic prescreen JSON report path; only valid for one dataset")
    parser.add_argument("--prescreen-csv-out", default="", help="Deterministic prescreen CSV report path; only valid for one dataset")
    parser.add_argument(
        "--prescreen-retained-queue-out",
        default="",
        help="Deterministic prescreen retained DOI queue path; only valid for one dataset",
    )
    parser.add_argument(
        "--prescreen-excluded-queue-out",
        default="",
        help="Deterministic prescreen excluded DOI queue path; only valid for one dataset",
    )
    parser.add_argument("--doi-file", default="", help="Optional DOI queue limiting which paper-library rows are screened")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument(
        "--fast-screen-model",
        default="",
        help=(
            "Optional cheaper Ollama model for first-pass obvious-irrelevant exclusions. "
            "Rows not confidently excluded are escalated to --model."
        ),
    )
    parser.add_argument("--ollama-url", default=DEFAULT_OLLAMA_URL)
    parser.add_argument("--limit", type=int, default=0, help="Rows to process; 0 means all after filters")
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--timeout-sec", type=int, default=300, help="Per-row Ollama timeout; 0 means wait indefinitely")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--num-ctx", type=int, default=16384)
    parser.add_argument(
        "--deterministic-prescreen",
        action="store_true",
        help=(
            "Skip LLM calls for obvious no-signal rows with enough abstract text and no in-scope intervention term "
            "in the title/abstract. If heuristic audit is enabled, heuristic retention also blocks exclusion."
        ),
    )
    parser.add_argument(
        "--deterministic-prescreen-only",
        action="store_true",
        help="Run only the fast deterministic pass and write retained/excluded DOI queues; do not call Ollama.",
    )
    parser.add_argument("--fast-screen-timeout-sec", type=int, default=300)
    parser.add_argument("--fast-screen-temperature", type=float, default=0.0)
    parser.add_argument("--fast-screen-num-ctx", type=int, default=4096)
    parser.add_argument(
        "--fast-screen-confidence",
        type=float,
        default=0.9,
        help="Minimum fast-screen confidence required to skip the full model.",
    )
    parser.add_argument("--max-contexts", type=int, default=16)
    parser.add_argument("--auto-confidence", type=float, default=0.85)
    parser.add_argument("--context-confidence", type=float, default=0.75)
    parser.add_argument("--only-with-abstract", action="store_true")
    parser.add_argument("--only-undownloaded", action="store_true")
    parser.add_argument(
        "--only-heuristic-possible",
        action="store_true",
        help="Screen only rows the old heuristic labeled possible_relevant",
    )
    parser.add_argument("--dry-run", action="store_true", help="Build prompts/reports without calling Ollama")
    parser.add_argument("--skip-model-check", action="store_true")
    parser.add_argument("--continue-on-error", action="store_true")
    parser.add_argument(
        "--checkpoint-jsonl",
        default="",
        help="Append one JSON result per completed row; default is <out-json stem>.checkpoint.jsonl next to report",
    )
    parser.add_argument(
        "--resume-from-checkpoint",
        action="store_true",
        help="Skip DOIs already present in the checkpoint JSONL; append new rows to the same file",
    )
    parser.add_argument(
        "--materialize-checkpoint-only",
        action="store_true",
        help=(
            "Read the checkpoint JSONL, revalidate completed rows, and write the normal JSON/CSV/DOI queues "
            "without calling Ollama. Useful while a long local-LLM run is still in progress."
        ),
    )
    parser.add_argument(
        "--refresh-report-metadata-only",
        action="store_true",
        help=(
            "Read an existing screening report, refresh bibliographic metadata from the current paper library, "
            "and rewrite the report/CSV/DOI queues without calling Ollama or revalidating LLM decisions."
        ),
    )
    parser.add_argument(
        "--report-fallback-json",
        default="",
        help=(
            "With --materialize-checkpoint-only, use an existing screening report as fallback for rows missing "
            "from the checkpoint JSONL. With --refresh-report-metadata-only, use this report as the source. "
            "Defaults to --out-json when it exists."
        ),
    )
    parser.add_argument(
        "--merge-report-json",
        action="append",
        default=[],
        help=(
            "With --refresh-report-metadata-only, merge rows from another screening report before refreshing metadata. "
            "Can be supplied multiple times; later reports replace duplicate DOIs."
        ),
    )
    parser.add_argument(
        "--reprocess-dois-file",
        default="",
        help="With --resume-from-checkpoint: path to newline-separated DOIs to remove from the skip set so the LLM runs again (checkpoint JSONL is unchanged until new rows append)",
    )
    parser.add_argument(
        "--reprocess-all-checkpoint-dois",
        action="store_true",
        help="With --resume-from-checkpoint: do not skip any DOI from checkpoint; re-run the LLM for the whole batch (still appends to the same JSONL; last line per DOI wins on next resume)",
    )
    parser.add_argument(
        "--no-checkpoint",
        action="store_true",
        help="Disable per-row checkpoint JSONL (original behavior for final outputs only)",
    )
    parser.add_argument(
        "--quiet-progress",
        action="store_true",
        help="Do not print per-row summary lines after each paper (DOI line only)",
    )
    parser.add_argument(
        "--show-checkpoint-progress",
        action="store_true",
        help="Print every row reused from checkpoint. By default resume mode summarizes reused rows instead of replaying them.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.dataset == "all" and any(
        normalize(value)
        for value in [
            args.paper_db_json,
            args.triage_report_json,
            args.out_json,
            args.out_csv,
            args.download_queue_out,
            args.relevant_queue_out,
            args.uncertain_queue_out,
            args.prescreen_json_out,
            args.prescreen_csv_out,
            args.prescreen_retained_queue_out,
            args.prescreen_excluded_queue_out,
            args.doi_file,
            args.report_fallback_json,
            *args.merge_report_json,
        ]
    ):
        raise SystemExit("Per-dataset path overrides are only supported when --dataset is mechanistic or disorder")

    if args.deterministic_prescreen_only:
        args.deterministic_prescreen = True
        args.no_checkpoint = True

    if (
        not args.dry_run
        and not args.skip_model_check
        and not args.deterministic_prescreen_only
        and not args.materialize_checkpoint_only
        and not args.refresh_report_metadata_only
    ):
        if not model_is_installed(args.model, args.ollama_url, timeout_sec=10):
            raise SystemExit(
                f"Ollama model `{args.model}` is not installed or Ollama is unavailable. "
                f"Install it with: ollama pull {args.model}"
            )
        fast_model = normalize(args.fast_screen_model)
        if fast_model and not model_is_installed(fast_model, args.ollama_url, timeout_sec=10):
            raise SystemExit(
                f"Ollama fast-screen model `{fast_model}` is not installed or Ollama is unavailable. "
                f"Install it with: ollama pull {fast_model}"
            )

    datasets = DATASETS if args.dataset == "all" else (args.dataset,)
    payloads = [run_dataset(dataset, args) for dataset in datasets]
    failed = any(payload.get("status") == "failed" for payload in payloads)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
