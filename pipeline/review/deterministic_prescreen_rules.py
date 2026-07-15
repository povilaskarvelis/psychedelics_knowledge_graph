#!/usr/bin/env python3
"""Deterministic title/abstract pre-screen rules for the canonical corpus pipeline."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, Iterable, List, Set

from pipeline.review.prescreen_term_sets import (
    CLINICAL_BRIDGE_TERMS,
    CLINICAL_FUNCTION_SYMPTOM_TERMS,
    CLINICAL_SAFETY_TERMS,
    COGNITIVE_AFFECTIVE_TASK_TERMS,
    EEG_MEG_NEUROPHYS_TERMS,
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
)

ROOT = Path(__file__).resolve().parents[2]
PIPELINE_CONFIG_PATH = ROOT / "pipeline" / "config.example.yaml"
CLINICAL_OUTCOME_CANON_PATH = ROOT / "schema" / "disorder_canonicalization.json"

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

TARGET_SYNONYMS = {
    "5-ht2a": {"5-ht2a", "5ht2a", "serotonin 2a", "htr2a", "5 hydroxytryptamine 2a"},
    "5-ht2b": {"5-ht2b", "5ht2b", "serotonin 2b", "htr2b", "5 hydroxytryptamine 2b"},
    "5-ht2c": {"5-ht2c", "5ht2c", "serotonin 2c", "htr2c", "5 hydroxytryptamine 2c"},
    "5-ht1a": {"5-ht1a", "5ht1a", "serotonin 1a", "htr1a", "5 hydroxytryptamine 1a"},
    "5-ht1b": {"5-ht1b", "5ht1b", "serotonin 1b", "htr1b", "5 hydroxytryptamine 1b"},
    "5-ht1d": {"5-ht1d", "5ht1d", "serotonin 1d", "htr1d", "5 hydroxytryptamine 1d"},
    "5-ht1e": {"5-ht1e", "5ht1e", "serotonin 1e", "htr1e", "5 hydroxytryptamine 1e"},
    "5-ht1f": {"5-ht1f", "5ht1f", "serotonin 1f", "htr1f", "5 hydroxytryptamine 1f"},
    "5-ht5a": {"5-ht5a", "5ht5a", "serotonin 5a", "htr5a", "5 hydroxytryptamine 5a"},
    "5-ht6": {"5-ht6", "5ht6", "serotonin 6", "htr6", "5 hydroxytryptamine 6"},
    "5-ht7": {"5-ht7", "5ht7", "serotonin 7", "htr7", "5 hydroxytryptamine 7"},
    "mglur2 (grm2)": {"mglur2", "grm2", "metabotropic glutamate receptor 2"},
    "taar1": {"taar1", "trace amine associated receptor 1"},
    "sert (slc6a4)": {"sert", "slc6a4", "serotonin transporter", "5-htt", "5htt"},
    "net (slc6a2)": {"net", "slc6a2", "norepinephrine transporter", "noradrenaline transporter"},
    "dat (slc6a3)": {"dat", "slc6a3", "dopamine transporter"},
    "vmat2 (slc18a2)": {"vmat2", "slc18a2", "vesicular monoamine transporter 2"},
    "d1 receptor (drd1)": {"d1 receptor", "drd1", "dopamine d1 receptor"},
    "d2 receptor (drd2)": {"d2 receptor", "drd2", "dopamine d2 receptor"},
    "d3 receptor (drd3)": {"d3 receptor", "drd3", "dopamine d3 receptor"},
    "d4 receptor (drd4)": {"d4 receptor", "drd4", "dopamine d4 receptor"},
    "d5 receptor (drd5)": {"d5 receptor", "drd5", "dopamine d5 receptor"},
    "alpha1a adrenergic receptor (adra1a)": {
        "alpha1a adrenergic receptor",
        "alpha 1a adrenergic receptor",
        "alpha1a adrenoceptor",
        "adra1a",
    },
    "alpha1b adrenergic receptor (adra1b)": {
        "alpha1b adrenergic receptor",
        "alpha 1b adrenergic receptor",
        "alpha1b adrenoceptor",
        "adra1b",
    },
    "alpha2a adrenergic receptor (adra2a)": {
        "alpha2a adrenergic receptor",
        "alpha 2a adrenergic receptor",
        "alpha2a adrenoceptor",
        "adra2a",
    },
    "alpha2b adrenergic receptor (adra2b)": {
        "alpha2b adrenergic receptor",
        "alpha 2b adrenergic receptor",
        "alpha2b adrenoceptor",
        "adra2b",
    },
    "alpha2c adrenergic receptor (adra2c)": {
        "alpha2c adrenergic receptor",
        "alpha 2c adrenergic receptor",
        "alpha2c adrenoceptor",
        "adra2c",
    },
    "beta1 adrenergic receptor (adrb1)": {
        "beta1 adrenergic receptor",
        "beta 1 adrenergic receptor",
        "beta1 adrenoceptor",
        "adrb1",
    },
    "beta2 adrenergic receptor (adrb2)": {
        "beta2 adrenergic receptor",
        "beta 2 adrenergic receptor",
        "beta2 adrenoceptor",
        "adrb2",
    },
    "m1 muscarinic receptor (chrm1)": {"m1 muscarinic receptor", "m1 receptor", "chrm1"},
    "m2 muscarinic receptor (chrm2)": {"m2 muscarinic receptor", "m2 receptor", "chrm2"},
    "m3 muscarinic receptor (chrm3)": {"m3 muscarinic receptor", "m3 receptor", "chrm3"},
    "m4 muscarinic receptor (chrm4)": {"m4 muscarinic receptor", "m4 receptor", "chrm4"},
    "m5 muscarinic receptor (chrm5)": {"m5 muscarinic receptor", "m5 receptor", "chrm5"},
    "h1 receptor (hrh1)": {"h1 receptor", "histamine h1 receptor", "hrh1"},
    "h2 receptor (hrh2)": {"h2 receptor", "histamine h2 receptor", "hrh2"},
    "sigma-1 receptor (sigmar1)": {"sigma-1", "sigma 1", "sigmar1", "sigma-1 receptor"},
    "sigma-2 receptor (tmem97)": {"sigma-2", "sigma 2", "tmem97", "sigma-2 receptor"},
    "kappa opioid receptor (oprk1)": {"kappa opioid receptor", "kor", "oprk1"},
    "mu opioid receptor (oprm1)": {"mu opioid receptor", "mor", "oprm1"},
    "delta opioid receptor (oprd1)": {"delta opioid receptor", "dor", "oprd1"},
    "nmda receptor": {"nmda receptor", "nmda", "n-methyl-d-aspartate receptor", "nmdar"},
    "ampa receptor": {"ampa receptor", "ampa", "ampar"},
    "cb1 receptor (cnr1)": {"cb1 receptor", "cb1", "cnr1", "cannabinoid receptor 1"},
    "cb2 receptor (cnr2)": {"cb2 receptor", "cb2", "cnr2", "cannabinoid receptor 2"},
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

def load_clinical_outcome_synonyms(path: Path = CLINICAL_OUTCOME_CANON_PATH) -> Dict[str, Set[str]]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        return {}

    out: Dict[str, Set[str]] = {}
    for canonical, aliases in data.items():
        key = normalize(canonical).lower()
        if not key:
            continue
        bucket: Set[str] = set()
        bucket.add(normalize(canonical))
        if isinstance(aliases, list):
            for alias in aliases:
                value = normalize(alias)
                if value:
                    bucket.add(value)
        out[key] = bucket
    return out

FILE_CLINICAL_OUTCOME_SYNONYMS = load_clinical_outcome_synonyms()

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

def abstract_context(row: dict) -> str:
    title = normalize(row.get("study_title", ""))
    abstract = normalize(row.get("abstract", ""))
    parts = []
    if title:
        parts.append(f"Title: {title}")
    if abstract:
        parts.append(f"Abstract: {abstract}")
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

def target_synonym_terms() -> frozenset[str]:
    return frozenset(synonym_map_terms(TARGET_SYNONYMS))

def clinical_outcome_synonym_terms() -> frozenset[str]:
    return frozenset(
        synonym_map_terms(CLINICAL_OUTCOME_SYNONYMS, FILE_CLINICAL_OUTCOME_SYNONYMS)
    )

def molecular_target_terms() -> frozenset[str]:
    return frozenset(set(target_synonym_terms()) | MOLECULAR_TARGET_SIGNAL_TERMS)

def clinical_outcome_terms() -> frozenset[str]:
    return frozenset(set(clinical_outcome_synonym_terms()) | CLINICAL_OUTCOME_SIGNAL_TERMS)

def clinical_bridge_terms() -> frozenset[str]:
    return frozenset(set(clinical_outcome_synonym_terms()) | CLINICAL_BRIDGE_SIGNAL_TERMS)

def all_entity_terms() -> frozenset[str]:
    return frozenset(
        set(target_synonym_terms())
        | set(clinical_outcome_synonym_terms())
        | MOLECULAR_TARGET_SIGNAL_TERMS
        | MOLECULAR_PATHWAY_SIGNAL_TERMS
        | BRAIN_SYSTEM_SIGNAL_TERMS
        | COGNITIVE_BEHAVIORAL_SIGNAL_TERMS
        | CLINICAL_OUTCOME_SIGNAL_TERMS
        | SAFETY_SIGNAL_TERMS
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

def evidence_domain_tags_for_context(context: str) -> List[str]:
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
    has_clinical = "clinical_outcome" in tags or any_term_found_in_context(
        clinical_bridge_terms(), context
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

def deterministic_prescreen_decision(row: dict) -> dict:
    context = abstract_context(row)
    matched_intervention_terms = matched_in_scope_intervention_terms(context)
    matched_domain_tags = evidence_domain_tags_for_context(context)
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

    entity_terms = all_entity_terms()
    entity_reason = "context entity terms present" if any_term_found_in_context(entity_terms, context) else "no context entity terms found"
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
