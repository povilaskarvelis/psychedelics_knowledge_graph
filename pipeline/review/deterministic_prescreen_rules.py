#!/usr/bin/env python3
"""Deterministic title/abstract pre-screen rules for the canonical corpus pipeline."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, Iterable, List

ROOT = Path(__file__).resolve().parents[2]
PIPELINE_CONFIG_PATH = ROOT / "pipeline" / "config.example.yaml"

COMPOUND_SYNONYMS = {
    "psilocybin": {
        "psilocybin",
        "psilocibin",
        "psilocibina",
        "psilocybina",
        "psilocibine",
        "psilocybine",
        "psilocin",
        "comp360",
        "magic mushroom",
        "magic mushrooms",
        "psilocybin mushroom",
        "psilocybin mushrooms",
        "psilocybe cubensis",
        "psilocybe semilanceata",
        "4-po-dmt",
        "4 po dmt",
        "4-phosphoryloxy-dmt",
        "4 phosphoryloxy dmt",
        "4-phosphoryloxy-n,n-dimethyltryptamine",
    },
    "psilocin": {
        "psilocin",
        "4-ho-dmt",
        "4 hydroxy dmt",
        "4-hydroxy-dmt",
        "4-hydroxy-n,n-dimethyltryptamine",
    },
    "lsd": {"lsd", "lsd-25", "lysergide", "lysergic acid diethylamide", "d-lysergic acid diethylamide"},
    "dmt": {"dmt", "n,n-dmt", "n n dmt", "nn-dmt", "dimethyltryptamine", "n,n-dimethyltryptamine"},
    "5-meo-dmt": {
        "5-meo-dmt",
        "5 meo dmt",
        "5meodmt",
        "meodmt",
        "5-methoxy-dmt",
        "5 methoxy dmt",
        "5-methoxy-n,n-dimethyltryptamine",
        "5 methoxy n,n dimethyltryptamine",
        "5-methoxy-n,n-dimethyl tryptamine",
        "o-methylbufotenin",
    },
    "bufotenin": {"bufotenin", "bufotenine", "5-ho-dmt", "5 ho dmt", "5-hydroxy-dmt", "5 hydroxy dmt"},
    "5-meo-mipt": {
        "5-meo-mipt",
        "5 meo mipt",
        "5-methoxy-n-methyl-n-isopropyltryptamine",
        "moxy",
    },
    "5-meo-dipt": {"5-meo-dipt", "5 meo dipt", "foxy methoxy"},
    "dipt": {"dipt", "diisopropyltryptamine", "n,n-diisopropyltryptamine"},
    "dpt": {"dpt", "dipropyltryptamine", "n,n-dipropyltryptamine"},
    "ayahuasca": {"ayahuasca", "hoasca", "yage", "ayahuasca brew", "ayahuasca tea", "santo daime", "daime"},
    "mdma": {
        "mdma",
        "3,4-methylenedioxymethamphetamine",
        "3,4-methylenedioxy-methamphetamine",
        "methylenedioxymethamphetamine",
        "midomafetamine",
        "ecstasy",
    },
    "mda": {"mda", "3,4-methylenedioxyamphetamine", "methylenedioxyamphetamine"},
    "ketamine": {
        "ketamine",
        "ketamin",
        "esketamine",
        "arketamine",
        "s-ketamine",
        "r-ketamine",
        "racemic ketamine",
        "rs-ketamine",
        "r,s-ketamine",
    },
    "s-ketamine": {"s-ketamine", "esketamine", "ketamine"},
    "r-ketamine": {"r-ketamine", "arketamine", "ketamine"},
    "ibogaine": {
        "ibogaine",
        "iboga",
        "tabernanthe iboga",
        "18-mc",
        "18 mc",
        "18-methoxycoronaridine",
        "18 methoxycoronaridine",
    },
    "noribogaine": {"noribogaine", "o-desmethylibogaine"},
    "mescaline": {
        "mescaline",
        "peyote",
        "san pedro",
        "wachuma",
        "huachuma",
        "lophophora williamsii",
        "echinopsis pachanoi",
    },
    "salvinorin a": {"salvinorin a", "divinorin a", "salvia divinorum"},
    "lsa": {
        "lsa",
        "ergine",
        "lysergic acid amide",
        "hawaiian baby woodrose",
        "argyreia nervosa",
        "ipomoea tricolor",
    },
    "4-aco-dmt": {"4-aco-dmt", "4 aco dmt", "4-acetoxy-dmt", "4 acetoxy dmt", "o-acetylpsilocin", "psilacetin"},
    "4-ho-met": {"4-ho-met", "4 ho met", "metocin", "4-hydroxy-met", "4 hydroxy met"},
    "4-ho-mipt": {"4-ho-mipt", "4 ho mipt", "miprocin", "4-hydroxy-mipt", "4 hydroxy mipt"},
    "alpha-methyltryptamine": {"alpha-methyltryptamine", "alpha methyltryptamine", "a-methyltryptamine"},
    "25cn-nboh": {"25-cn-nboh", "25cn-nboh", "25 cn nboh"},
    "2c-b": {"2c-b", "2c b", "4-bromo-2,5-dimethoxyphenethylamine"},
    "2c-c": {"2c-c", "2c c", "4-chloro-2,5-dimethoxyphenethylamine"},
    "2c-d": {"2c-d", "2c d", "2,5-dimethoxy-4-methylphenethylamine"},
    "2c-e": {"2c-e", "2c e", "4-ethyl-2,5-dimethoxyphenethylamine"},
    "2c-i": {"2c-i", "2c i", "4-iodo-2,5-dimethoxyphenethylamine"},
    "2c-p": {"2c-p", "2c p", "4-propyl-2,5-dimethoxyphenethylamine"},
    "2c-t-2": {"2c-t-2", "2c t 2", "2,5-dimethoxy-4-ethylthiophenethylamine"},
    "2c-t-7": {"2c-t-7", "2c t 7", "2,5-dimethoxy-4-propylthiophenethylamine"},
    "doi": {"doi", "2,5-dimethoxy-4-iodoamphetamine"},
    "dob": {"dob", "2,5-dimethoxy-4-bromoamphetamine"},
    "dom": {
        "dom",
        "2,5-dimethoxy-4-methylamphetamine",
        "1-(2,5-dimethoxy-4-methylphenyl)-2-aminopropane",
        "1 (2,5 dimethoxy 4 methylphenyl) 2 aminopropane",
        "stp",
    },
    "doc": {"doc", "2,5-dimethoxy-4-chloroamphetamine"},
    "doet": {"doet", "2,5-dimethoxy-4-ethylamphetamine"},
    "25i-nbome": {"25i-nbome", "25i nbome", "25-i-nbome", "25 i nbome"},
    "25b-nbome": {"25b-nbome", "25b nbome", "25-b-nbome", "25 b nbome"},
    "25c-nbome": {"25c-nbome", "25c nbome", "25-c-nbome", "25 c nbome"},
    "25i-nboh": {"25i-nboh", "25i nboh", "25-i-nboh", "25 i nboh"},
    "25b-nboh": {"25b-nboh", "25b nboh", "25-b-nboh", "25 b nboh"},
    "25c-nboh": {"25c-nboh", "25c nboh", "25-c-nboh", "25 c nboh"},
    "al-lad": {"al-lad", "al lad"},
    "eth-lad": {"eth-lad", "eth lad"},
    "pro-lad": {"pro-lad", "pro lad"},
    "1p-lsd": {"1p-lsd", "1p lsd"},
    "bromo-dragonfly": {"bromo-dragonfly", "bromo dragonfly"},
}

CLINICAL_OUTCOME_SYNONYMS = {
    "post-traumatic stress disorder": {"post-traumatic stress disorder", "posttraumatic stress disorder", "ptsd"},
    "complex post-traumatic stress disorder": {
        "complex post-traumatic stress disorder",
        "complex posttraumatic stress disorder",
        "c-ptsd",
    },
    "major depressive disorder": {"major depressive disorder", "depression", "mdd"},
    "treatment-resistant depression": {"treatment-resistant depression", "treatment resistant depression", "trd"},
    "bipolar depression": {"bipolar depression", "bipolar ii depression"},
    "persistent depressive disorder": {"persistent depressive disorder", "dysthymia"},
    "alcohol use disorder": {"alcohol use disorder", "alcohol dependence", "aud"},
    "tobacco use disorder": {"tobacco use disorder", "nicotine dependence"},
    "nicotine dependence": {"nicotine dependence", "tobacco dependence"},
    "opioid use disorder": {"opioid use disorder", "opiate dependence", "oud"},
    "cannabis use disorder": {"cannabis use disorder", "marijuana use disorder"},
    "cocaine use disorder": {"cocaine use disorder", "cocaine dependence"},
    "methamphetamine use disorder": {"methamphetamine use disorder", "methamphetamine dependence"},
    "stimulant use disorder": {"stimulant use disorder", "psychostimulant use disorder"},
    "substance use disorder": {"substance use disorder", "drug dependence"},
    "generalized anxiety disorder": {"generalized anxiety disorder", "gad"},
    "social anxiety disorder": {"social anxiety disorder", "social phobia", "sad"},
    "distress associated with life-threatening disease": {
        "distress associated with life-threatening disease",
    },
    "obsessive-compulsive disorder": {"obsessive-compulsive disorder", "obsessive compulsive disorder", "ocd"},
    "eating disorders": {"eating disorders", "feeding and eating disorders"},
    "anorexia nervosa": {"anorexia nervosa", "anorexia"},
    "autism spectrum disorder": {"autism spectrum disorder", "asd"},
    "demoralization": {"demoralization", "demoralisation"},
    "suicidal ideation": {"suicidal ideation", "suicidality"},
    "cluster headache": {"cluster headache", "cluster headaches"},
    "chronic pain": {"chronic pain", "neuropathic pain"},
}

def normalize(value) -> str:
    if value is None:
        return ""
    return str(value).strip()

def normalize_doi(raw: str) -> str:
    text = normalize(raw)
    if not text:
        return ""
    if text.lower().startswith("doi:"):
        text = text[4:]
    for prefix in (
        "https://doi.org/",
        "http://doi.org/",
        "https://dx.doi.org/",
        "http://dx.doi.org/",
    ):
        if text.lower().startswith(prefix):
            text = text[len(prefix) :]
            break
    return text.strip()

def parse_allowlists(path: Path) -> Dict[str, List[str]]:
    if not path.exists():
        return {}

    keys = {"allowed_compounds", "allowed_targets", "allowed_disorders"}
    allowlists = {key: [] for key in keys}
    current_key = None

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        if line.endswith(":"):
            key = line[:-1]
            current_key = key if key in keys else None
            continue

        if current_key and line.startswith("- "):
            value = line[2:].strip().strip('"').strip("'")
            allowlists[current_key].append(value)
            continue

        current_key = None

    return allowlists

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

SAN_PEDRO_SUPPORT_RE = re.compile(
    r"\b(?:cact(?:us|i)|mescaline|echinopsis|trichocereus|pachanoi|peruvianus|"
    r"huachuma|wachuma|peyote|psychedelic|hallucinogen|entheogen|ceremon\w*|alkaloid)\b",
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

def abstract_context(row: dict) -> str:
    parts = []
    for field, label in (
        ("study_title", "Title"),
        ("abstract", "Abstract"),
        ("keywords", "Keywords"),
        ("mesh_terms", "MeSH"),
    ):
        value = normalize(row.get(field, ""))
        if value:
            parts.append(f"{label}: {value}")
    return "\n".join(parts)

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

def ambiguous_intervention_acronym_supported(context: str) -> bool:
    return any_term_found_in_context(AMBIGUOUS_ACRONYM_SUPPORT_TERMS, context)

def ambiguous_intervention_class_supported(context: str) -> bool:
    return any_term_found_in_context(AMBIGUOUS_CLASS_SUPPORT_TERMS, context)

def san_pedro_intervention_supported(context: str) -> bool:
    return bool(SAN_PEDRO_SUPPORT_RE.search(normalize(context)))

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
    san_pedro_supported = san_pedro_intervention_supported(normalized_context)
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
        if term_lower == "san pedro" and not san_pedro_supported:
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
    return title_has_ketamine and title_has_acute_care

def deterministic_prescreen_decision(row: dict) -> dict:
    context = abstract_context(row)
    matched_intervention_terms = matched_in_scope_intervention_terms(context)
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
                    "context, without psychiatric, chronic pain, brain/cognition, safety, or biological evidence signals."
                ),
                "matched_terms": matched_intervention_terms[:20],
            }
        return {
            "action": "escalate",
            "reason": "in-scope compound/intervention term appears in title, abstract, keywords, or MeSH terms",
            "matched_terms": matched_intervention_terms[:20],
        }
    if any_term_found_in_context(AMBIGUOUS_PSYCHIATRIC_TREATMENT_TERMS, context):
        return {
            "action": "escalate",
            "reason": "broad psychiatric treatment language needs LLM review",
        }

    return {
        "action": "exclude_obvious_irrelevant",
        "confidence": 1.0,
        "supporting_quote": deterministic_supporting_quote(row),
        "reason": (
            "No in-scope psychedelic/ketamine/entactogen/dissociative compound or intervention term appears "
            "in the title, abstract, keywords, or MeSH terms."
        ),
    }

def deterministic_supporting_quote(row: dict) -> str:
    title = normalize(row.get("study_title", ""))
    if title:
        return title
    abstract = normalize(row.get("abstract", ""))
    return abstract[:300] if abstract else "not_found"
