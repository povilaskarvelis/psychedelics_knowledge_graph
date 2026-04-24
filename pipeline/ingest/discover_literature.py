#!/usr/bin/env python3
"""Discover literature from web APIs and generate DOI queues for KG ingest.

Default provider is Semantic Scholar because it is better for relevance ranking.
OpenAlex is available for metadata-heavy search, and hybrid merges both.
"""

from __future__ import annotations

import argparse
from collections import Counter
import csv
import datetime as dt
import json
import os
import random
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
DISORDER_CANON_PATH = ROOT / "schema" / "disorder_canonicalization.json"
PROVIDER_BACKENDS = {
    "semantic_scholar": ("semantic_scholar",),
    "openalex": ("openalex",),
    "hybrid": ("semantic_scholar", "openalex"),
    "pubmed": ("pubmed",),
    "pmc": ("pmc",),
    "crossref": ("crossref",),
    "biomedical": ("pubmed", "pmc", "crossref"),
    "comprehensive": ("semantic_scholar", "openalex", "pubmed", "pmc", "crossref"),
}

DEFAULT_SEEDS = {
    "mechanistic": [
        "LSD 5-HT2A receptor binding affinity Ki radioligand|LSD|5-HT2A",
        "LSD 5-HT2C receptor binding affinity|LSD|5-HT2C",
        "psilocin 5-HT2A receptor binding affinity|Psilocin|5-HT2A",
        "psilocin 5-HT1A receptor binding affinity|Psilocin|5-HT1A",
        "psilocybin psilocin 5-HT2A agonist receptor|Psilocybin|5-HT2A",
        "DMT 5-HT2A receptor binding affinity|DMT|5-HT2A",
        "DMT sigma-1 receptor binding affinity|DMT|Sigma-1 receptor (SIGMAR1)",
        "psychedelic TAAR1 trace amine receptor 1 binding|DMT|TAAR1",
        "5-MeO-DMT 5-HT1A receptor binding affinity|5-MeO-DMT|5-HT1A",
        "mescaline 5-HT2A receptor binding affinity|Mescaline|5-HT2A",
        "MDMA SERT DAT NET transporter affinity|MDMA|SERT (SLC6A4)",
        "MDMA dopamine transporter DAT affinity|MDMA|DAT (SLC6A3)",
        "MDMA norepinephrine transporter NET affinity|MDMA|NET (SLC6A2)",
        "MDMA SERT amphetamine serotonin transporter CaMKII|MDMA|SERT (SLC6A4)",
        "MDMA enantiomers MPTP-lesioned primate SERT in vitro|MDMA|SERT (SLC6A4)",
        "ibogaine noribogaine kappa opioid receptor binding|Ibogaine|kappa opioid receptor (OPRK1)",
        "ibogaine NMDA receptor binding affinity|Ibogaine|NMDA receptor",
        "ketamine NMDA receptor affinity binding Ki|Ketamine|NMDA receptor",
        "esketamine NMDA receptor affinity binding|S-ketamine|NMDA receptor",
        "arketamine NMDA receptor affinity binding|R-ketamine|NMDA receptor",
        "salvinorin A kappa opioid receptor affinity|Salvinorin A|kappa opioid receptor (OPRK1)",
        "2C-B 5-HT2A receptor binding affinity|2C-B|5-HT2A",
        "DOI 5-HT2A receptor binding affinity|DOI|5-HT2A",
        "psychedelic mGluR2 GRM2 receptor interaction|LSD|mGluR2 (GRM2)",
    ],
    "disorder": [
        "psilocybin treatment-resistant depression randomized trial|Psilocybin|Treatment-resistant depression",
        "psilocybin major depressive disorder randomized trial|Psilocybin|Major depressive disorder",
        "ayahuasca major depressive disorder trial|Ayahuasca|Major depressive disorder",
        "ketamine treatment-resistant depression trial|Ketamine|Treatment-resistant depression",
        "esketamine treatment-resistant depression phase 3|S-ketamine|Treatment-resistant depression",
        "ketamine suicidal ideation randomized trial|Ketamine|Suicidal ideation",
        "MDMA post-traumatic stress disorder randomized trial|MDMA|Post-traumatic stress disorder",
        "LSD anxiety life-threatening disease trial|LSD|distress associated with life-threatening disease",
        "psilocybin cancer anxiety depression trial|Psilocybin|distress associated with life-threatening disease",
        "psilocybin generalized anxiety disorder trial|Psilocybin|Generalized anxiety disorder",
        "MDMA autism spectrum disorder social anxiety trial|MDMA|Autism spectrum disorder",
        "psilocybin obsessive-compulsive disorder trial|Psilocybin|Obsessive-compulsive disorder",
        "psilocybin anorexia nervosa trial|Psilocybin|Anorexia nervosa",
        "psilocybin eating disorders trial|Psilocybin|Eating disorders",
        "psilocybin alcohol use disorder randomized trial|Psilocybin|Alcohol use disorder",
        "psilocybin tobacco use disorder trial|Psilocybin|Tobacco use disorder",
        "ibogaine opioid use disorder trial|Ibogaine|Opioid use disorder",
        "ketamine alcohol use disorder trial|Ketamine|Alcohol use disorder",
        "psilocybin cocaine use disorder trial|Psilocybin|Cocaine use disorder",
        "psilocybin methamphetamine use disorder trial|Psilocybin|Methamphetamine use disorder",
        "psilocybin substance use disorder trial|Psilocybin|Substance use disorder",
        "psilocybin end-of-life anxiety trial|Psilocybin|distress associated with life-threatening disease",
        "LSD cluster headache trial|LSD|Cluster headache",
        "ketamine chronic pain trial|Ketamine|Chronic pain",
    ],
}

AUTO_SEED_TEMPLATES = {
    "mechanistic": {
        "focused": [
            "{compound} {entity} receptor binding affinity Ki",
        ],
        "broad": [
            "{compound} {entity} receptor binding affinity Ki",
            "{compound} {entity} radioligand binding affinity",
            "{compound} {entity} pharmacology assay affinity",
        ],
    },
    "disorder": {
        "focused": [
            "{compound} {entity} randomized clinical trial",
        ],
        "broad": [
            "{compound} {entity} randomized clinical trial",
            "{compound} {entity} phase 2 phase 3 trial",
            "{compound} {entity} therapeutic outcome study",
        ],
    },
}

BALANCED_SEED_TEMPLATES = {
    "mechanistic": {
        "compound_coverage": [
            "{compound} pharmacology binding affinity receptor transporter",
            "{compound} mechanism target receptor transporter",
        ],
        "entity_coverage": [
            "{entity} psychedelic pharmacology binding affinity",
            "{entity} receptor transporter psychedelic assay",
        ],
        "evidence": [
            "{compound} {entity} binding affinity Ki",
            "{compound} {entity} radioligand binding",
            "{compound} {entity} functional assay agonist antagonist",
            "{compound} {entity} signaling beta arrestin calcium cAMP",
            "{compound} {entity} transporter uptake release",
        ],
    },
    "disorder": {
        "compound_coverage": [
            "{compound} clinical trial treatment safety",
            "{compound} therapeutic outcome psychedelic",
        ],
        "entity_coverage": [
            "{entity} psychedelic clinical trial treatment",
            "{entity} psychedelic therapy outcome safety",
        ],
        "evidence": [
            "{compound} {entity} randomized clinical trial",
            "{compound} {entity} open label trial",
            "{compound} {entity} safety tolerability",
            "{compound} {entity} follow-up outcome",
            "{compound} {entity} remission response adverse events",
        ],
    },
}

COMPOUND_ALIASES = {
    "LSD": ["LSD", "lysergic acid diethylamide"],
    "Psilocybin": ["psilocybin"],
    "Psilocin": ["psilocin", "psilocyn"],
    "DMT": ["DMT", "N,N-dimethyltryptamine", "dimethyltryptamine"],
    "5-MeO-DMT": ["5-MeO-DMT", "5-methoxy-N,N-dimethyltryptamine"],
    "Mescaline": ["mescaline"],
    "MDMA": ["MDMA", "3,4-methylenedioxymethamphetamine", "ecstasy"],
    "MDA": ["MDA", "3,4-methylenedioxyamphetamine"],
    "Ketamine": ["ketamine", "norketamine"],
    "S-ketamine": ["esketamine", "S-ketamine"],
    "R-ketamine": ["arketamine", "R-ketamine"],
    "Ayahuasca": ["ayahuasca"],
    "Ibogaine": ["ibogaine"],
    "Noribogaine": ["noribogaine"],
    "Salvinorin A": ["salvinorin A"],
}

TARGET_ALIASES = {
    "5-HT2A": ["5-HT2A", "HTR2A", "serotonin 2A receptor", "5-hydroxytryptamine 2A receptor"],
    "5-HT2B": ["5-HT2B", "HTR2B", "serotonin 2B receptor"],
    "5-HT2C": ["5-HT2C", "HTR2C", "serotonin 2C receptor"],
    "5-HT1A": ["5-HT1A", "HTR1A", "serotonin 1A receptor"],
    "SERT (SLC6A4)": ["SERT", "SLC6A4", "serotonin transporter", "5-HTT"],
    "DAT (SLC6A3)": ["DAT", "SLC6A3", "dopamine transporter"],
    "NET (SLC6A2)": ["NET", "SLC6A2", "norepinephrine transporter", "noradrenaline transporter"],
    "NMDA receptor": ["NMDA receptor", "NMDAR", "glutamate receptor"],
    "Sigma-1 receptor (SIGMAR1)": ["sigma-1 receptor", "SIGMAR1", "sigma 1 receptor"],
    "TAAR1": ["TAAR1", "trace amine-associated receptor 1", "trace amine receptor 1"],
    "kappa opioid receptor (OPRK1)": ["kappa opioid receptor", "OPRK1", "KOR"],
    "mGluR2 (GRM2)": ["mGluR2", "GRM2", "metabotropic glutamate receptor 2"],
    "TrkB": ["TrkB", "NTRK2", "BDNF receptor"],
}

DISORDER_ALIASES = {
    "Treatment-resistant depression": ["treatment-resistant depression", "TRD", "resistant depression"],
    "Major depressive disorder": ["major depressive disorder", "MDD", "depression"],
    "Post-traumatic stress disorder": ["post-traumatic stress disorder", "PTSD"],
    "Alcohol use disorder": ["alcohol use disorder", "AUD", "alcohol dependence"],
    "Tobacco use disorder": ["tobacco use disorder", "smoking cessation", "nicotine dependence"],
    "Opioid use disorder": ["opioid use disorder", "opioid dependence"],
    "Cocaine use disorder": ["cocaine use disorder", "cocaine dependence"],
    "Methamphetamine use disorder": ["methamphetamine use disorder", "methamphetamine dependence"],
    "Substance use disorder": ["substance use disorder", "drug dependence"],
    "Generalized anxiety disorder": ["generalized anxiety disorder", "GAD"],
    "Social anxiety disorder": ["social anxiety disorder", "social anxiety"],
    "distress associated with life-threatening disease": [
        "life-threatening cancer",
        "cancer anxiety",
        "cancer depression",
        "end-of-life anxiety",
        "existential distress",
    ],
    "Obsessive-compulsive disorder": ["obsessive-compulsive disorder", "OCD"],
    "Anorexia nervosa": ["anorexia nervosa"],
    "Eating disorders": ["eating disorder", "eating disorders"],
    "Autism spectrum disorder": ["autism spectrum disorder", "autism", "ASD"],
    "Suicidal ideation": ["suicidal ideation", "suicidality"],
    "Cluster headache": ["cluster headache"],
    "Chronic pain": ["chronic pain"],
}

MECHANISTIC_PUBMED_TERMS = [
    "binding",
    "affinity",
    "Ki",
    "Kd",
    "IC50",
    "EC50",
    "receptor",
    "transporter",
    "pharmacology",
    "radioligand",
    "assay",
]

DISORDER_PUBMED_TERMS = [
    "trial",
    "randomized",
    "clinical",
    "treatment",
    "therapy",
    "phase 2",
    "phase 3",
    "outcome",
]


@dataclass
class Seed:
    query: str
    compound: str
    entity: str


class RateLimitedHttpClient:
    def __init__(self, rps: float, max_retries: int, timeout_sec: int = 30, user_agent: str = "kg-pipeline/0.1"):
        self.rps = max(0.01, rps)
        self.min_interval = 1.0 / self.rps
        self.max_retries = max_retries
        self.timeout_sec = timeout_sec
        self.user_agent = user_agent
        self._last_request_ts = 0.0

    def _wait_for_slot(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_request_ts
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)

    def get_json(self, url: str, params: Optional[Dict[str, object]] = None, headers: Optional[Dict[str, str]] = None) -> dict:
        query = urlencode({k: v for k, v in (params or {}).items() if v is not None}, doseq=True)
        full_url = f"{url}?{query}" if query else url
        request_headers = {"User-Agent": self.user_agent}
        if headers:
            request_headers.update(headers)

        backoff = 2.5
        for attempt in range(self.max_retries + 1):
            self._wait_for_slot()
            try:
                req = Request(full_url, headers=request_headers)
                with urlopen(req, timeout=self.timeout_sec) as response:
                    self._last_request_ts = time.monotonic()
                    body = response.read().decode("utf-8")
                    return json.loads(body)
            except HTTPError as err:
                self._last_request_ts = time.monotonic()
                retryable = err.code in {429, 500, 502, 503, 504}
                if attempt >= self.max_retries or not retryable:
                    raise
                retry_after = err.headers.get("Retry-After") if err.headers else None
                if retry_after and retry_after.isdigit():
                    delay = max(backoff, float(retry_after))
                else:
                    delay = backoff
                time.sleep(delay + random.uniform(0.0, 0.35))
                backoff *= 1.7
            except URLError:
                self._last_request_ts = time.monotonic()
                if attempt >= self.max_retries:
                    raise
                time.sleep(backoff + random.uniform(0.0, 0.35))
                backoff *= 1.7

        raise RuntimeError("Unreachable retry state")


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def normalize(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def normalize_text(raw: str) -> str:
    lowered = normalize(raw).lower()
    lowered = re.sub(r"[^a-z0-9]+", " ", lowered)
    return re.sub(r"\s+", " ", lowered).strip()


def normalize_doi(raw: str) -> str:
    doi = normalize(raw)
    if not doi:
        return ""
    if doi.lower().startswith("doi:"):
        doi = doi[4:]
    for prefix in (
        "https://doi.org/",
        "http://doi.org/",
        "https://dx.doi.org/",
        "http://dx.doi.org/",
    ):
        if doi.lower().startswith(prefix):
            doi = doi[len(prefix) :]
            break
    return doi.strip()


def parse_simple_yaml(path: Path) -> dict:
    if not path.exists():
        return {}

    out: Dict[str, dict] = {}
    current = ""
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if not line.startswith(" ") and stripped.endswith(":"):
            current = stripped[:-1]
            out[current] = {}
            continue
        if current and line.startswith("  ") and ":" in stripped:
            key, value = stripped.split(":", 1)
            value = value.strip().strip('"').strip("'")
            parsed: object = value
            if value == "":
                parsed = ""
            else:
                try:
                    parsed = float(value) if "." in value else int(value)
                except ValueError:
                    parsed = value
            out[current][key.strip()] = parsed
    return out


def merge_simple_config(base: dict, override: dict) -> dict:
    merged: Dict[str, dict] = {
        section: values.copy() if isinstance(values, dict) else values
        for section, values in base.items()
    }
    for section, values in override.items():
        if not isinstance(values, dict):
            if values != "":
                merged[section] = values
            continue
        current = merged.setdefault(section, {})
        if not isinstance(current, dict):
            current = {}
            merged[section] = current
        for key, value in values.items():
            if value != "":
                current[key] = value
    return merged


def load_config(path: Path) -> dict:
    config = parse_simple_yaml(path)
    local_path = path.parent / "config.local.yaml"
    if path.name == "config.example.yaml" and local_path.exists():
        config = merge_simple_config(config, parse_simple_yaml(local_path))
    return config


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
            if value:
                allowlists[current_key].append(value)
            continue

        current_key = None

    return allowlists


def dedupe_values(values: List[str]) -> List[str]:
    out: List[str] = []
    seen = set()
    for raw in values:
        value = normalize(raw)
        if not value:
            continue
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(value)
    return out


def query_safe_label(label: str) -> str:
    raw = normalize(label)
    if not raw:
        return ""

    match = re.match(r"^(.*?)\s*\(([^)]+)\)\s*$", raw)
    if match:
        base = normalize(match.group(1))
        inside = normalize(match.group(2))
        if base and inside:
            return f"{base} {inside}"
        return base or inside

    return raw


def clean_query_text(text: str) -> str:
    tokens = [token for token in normalize(text).split() if token]
    out: List[str] = []
    for token in tokens:
        if out and token.lower() == out[-1].lower():
            continue
        out.append(token)
    return " ".join(out)


def alias_values(label: str, alias_map: Dict[str, List[str]]) -> List[str]:
    raw = normalize(label)
    values: List[str] = []
    if raw:
        values.append(raw)
    normalized = normalize_text(raw)
    for key, aliases in alias_map.items():
        if normalize_text(key) == normalized:
            values.extend(aliases)
            break
    return dedupe_values(values)


def pubmed_fielded_term(term: str) -> str:
    text = normalize(term)
    if not text:
        return ""
    escaped = text.replace('"', "")
    if re.search(r"[^A-Za-z0-9]", escaped):
        return f'"{escaped}"[Title/Abstract]'
    return f"{escaped}[Title/Abstract]"


def pubmed_or_block(terms: List[str], max_terms: int = 8) -> str:
    fielded = [pubmed_fielded_term(term) for term in dedupe_values(terms)[:max_terms]]
    fielded = [term for term in fielded if term]
    if not fielded:
        return ""
    if len(fielded) == 1:
        return fielded[0]
    return "(" + " OR ".join(fielded) + ")"


def build_pubmed_query(seed: Seed, dataset: str) -> str:
    if not normalize(seed.compound) or not normalize(seed.entity):
        return seed.query

    compound_terms = alias_values(seed.compound, COMPOUND_ALIASES)
    entity_map = TARGET_ALIASES if dataset == "mechanistic" else DISORDER_ALIASES
    entity_terms = alias_values(seed.entity, entity_map)
    concept_terms = MECHANISTIC_PUBMED_TERMS if dataset == "mechanistic" else DISORDER_PUBMED_TERMS

    blocks = [
        pubmed_or_block(compound_terms),
        pubmed_or_block(entity_terms),
        pubmed_or_block(concept_terms, max_terms=12),
    ]
    blocks = [block for block in blocks if block]
    return " AND ".join(blocks) if blocks else seed.query


def build_alias_phrase_query(seed: Seed, dataset: str) -> str:
    if not normalize(seed.compound) or not normalize(seed.entity):
        return seed.query

    compound_terms = alias_values(seed.compound, COMPOUND_ALIASES)
    entity_map = TARGET_ALIASES if dataset == "mechanistic" else DISORDER_ALIASES
    entity_terms = alias_values(seed.entity, entity_map)
    concept_terms = MECHANISTIC_PUBMED_TERMS[:5] if dataset == "mechanistic" else DISORDER_PUBMED_TERMS[:5]
    return clean_query_text(" ".join([compound_terms[0], entity_terms[0], " ".join(concept_terms)]))


def query_variants_for_backend(seed: Seed, dataset: str, backend: str, mode: str) -> List[Seed]:
    if mode == "off":
        return [seed]

    variants = [seed]
    if backend in {"pubmed", "pmc"}:
        variants.append(Seed(query=build_pubmed_query(seed, dataset), compound=seed.compound, entity=seed.entity))
    elif mode == "expanded":
        variants.append(
            Seed(
                query=build_alias_phrase_query(seed, dataset),
                compound=seed.compound,
                entity=seed.entity,
            )
        )

    return dedupe_seeds([variant for variant in variants if normalize(variant.query)])


def load_disorder_alias_map(path: Path = DISORDER_CANON_PATH) -> Dict[str, str]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        return {}

    alias_map: Dict[str, str] = {}
    for canonical, aliases in data.items():
        canonical_label = normalize(canonical)
        if not canonical_label:
            continue
        alias_map[normalize_text(canonical_label)] = canonical_label
        if not isinstance(aliases, list):
            continue
        for raw in aliases:
            alias = normalize(raw)
            if not alias:
                continue
            alias_map[normalize_text(alias)] = canonical_label
    return alias_map


DISORDER_ALIAS_MAP = load_disorder_alias_map()


def canonicalize_disorder_label(raw: str) -> str:
    text = normalize(raw)
    if not text:
        return ""
    normalized = normalize_text(text)
    return DISORDER_ALIAS_MAP.get(normalized, text)


def dedupe_seeds(seeds: List["Seed"]) -> List["Seed"]:
    out: List[Seed] = []
    seen = set()
    for seed in seeds:
        key = (
            normalize(seed.query).lower(),
            normalize(seed.compound).lower(),
            normalize(seed.entity).lower(),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(seed)
    return out


def parse_manual_seeds(seed_values: List[str], query_values: List[str]) -> List["Seed"]:
    seeds: List[Seed] = []
    for value in seed_values:
        seeds.append(parse_seed(value))

    for query in query_values:
        q = normalize(query)
        if q:
            seeds.append(Seed(query=q, compound="", entity=""))

    return dedupe_seeds(seeds)


def generate_auto_seeds(
    dataset: str,
    allowlists: Dict[str, List[str]],
    template_mode: str,
    max_compounds: int,
    max_entities: int,
    max_pairs: int,
    max_seeds: int,
) -> List["Seed"]:
    compounds = dedupe_values(allowlists.get("allowed_compounds", []))
    entity_key = "allowed_targets" if dataset == "mechanistic" else "allowed_disorders"
    entities = dedupe_values(allowlists.get(entity_key, []))
    if dataset == "disorder":
        entities = dedupe_values([canonicalize_disorder_label(value) for value in entities])
    templates = AUTO_SEED_TEMPLATES[dataset][template_mode]

    if max_compounds > 0:
        compounds = compounds[:max_compounds]
    if max_entities > 0:
        entities = entities[:max_entities]

    out: List[Seed] = []
    pair_count = 0
    stop = False
    for compound in compounds:
        if stop:
            break
        for entity in entities:
            if max_pairs > 0 and pair_count >= max_pairs:
                stop = True
                break
            pair_count += 1

            entity_query = query_safe_label(entity)
            for template in templates:
                query = clean_query_text(template.format(compound=compound, entity=entity_query))
                if not query:
                    continue
                out.append(Seed(query=query, compound=compound, entity=entity))
                if max_seeds > 0 and len(out) >= max_seeds:
                    stop = True
                    break
            if stop:
                break

    return dedupe_seeds(out)


def allowed_entities_for_dataset(dataset: str, allowlists: Dict[str, List[str]]) -> List[str]:
    entity_key = "allowed_targets" if dataset == "mechanistic" else "allowed_disorders"
    entities = dedupe_values(allowlists.get(entity_key, []))
    if dataset == "disorder":
        entities = dedupe_values([canonicalize_disorder_label(value) for value in entities])
    return entities


def seed_label_keys(seeds: List["Seed"], attr: str) -> Set[str]:
    values = []
    for seed in seeds:
        value = getattr(seed, attr)
        if normalize(value):
            values.append(value)
    return {normalize_text(value) for value in values}


def generate_balanced_seeds(
    dataset: str,
    allowlists: Dict[str, List[str]],
    base_seeds: List["Seed"],
    profile: str,
    max_compounds: int,
    max_entities: int,
    max_seeds: int,
) -> tuple[List["Seed"], Dict[str, int]]:
    counts = {"compound_gap": 0, "entity_gap": 0, "evidence": 0}
    if profile == "off":
        return [], counts
    if profile not in {"coverage", "evidence"}:
        raise ValueError(f"Unsupported balanced seed profile: {profile}")

    compounds = dedupe_values(allowlists.get("allowed_compounds", []))
    entities = allowed_entities_for_dataset(dataset, allowlists)
    if max_compounds > 0:
        compounds = compounds[:max_compounds]
    if max_entities > 0:
        entities = entities[:max_entities]

    templates = BALANCED_SEED_TEMPLATES[dataset]
    covered_compounds = seed_label_keys(base_seeds, "compound")
    covered_entities = seed_label_keys(base_seeds, "entity")
    allowed_compound_keys = {normalize_text(value) for value in compounds}
    allowed_entity_keys = {normalize_text(value) for value in entities}

    out: List[Seed] = []
    seen = set()

    def add_seed(category: str, query: str, compound: str, entity: str) -> bool:
        seed = Seed(query=clean_query_text(query), compound=compound, entity=entity)
        if not normalize(seed.query):
            return True
        key = (
            normalize(seed.query).lower(),
            normalize(seed.compound).lower(),
            normalize(seed.entity).lower(),
        )
        if key in seen:
            return True
        if max_seeds > 0 and len(out) >= max_seeds:
            return False
        seen.add(key)
        out.append(seed)
        counts[category] += 1
        return True

    for compound in compounds:
        if normalize_text(compound) in covered_compounds:
            continue
        for template in templates["compound_coverage"]:
            if not add_seed("compound_gap", template.format(compound=compound), compound, ""):
                return out, counts

    for entity in entities:
        if normalize_text(entity) in covered_entities:
            continue
        entity_query = query_safe_label(entity)
        for template in templates["entity_coverage"]:
            if not add_seed("entity_gap", template.format(entity=entity_query), "", entity):
                return out, counts

    if profile != "evidence":
        return out, counts

    concrete_pairs: List[tuple[str, str]] = []
    seen_pairs = set()
    for seed in base_seeds:
        compound = normalize(seed.compound)
        entity = normalize(seed.entity)
        if not compound or not entity:
            continue
        if allowed_compound_keys and normalize_text(compound) not in allowed_compound_keys:
            continue
        if allowed_entity_keys and normalize_text(entity) not in allowed_entity_keys:
            continue
        pair_key = (normalize_text(compound), normalize_text(entity))
        if pair_key in seen_pairs:
            continue
        seen_pairs.add(pair_key)
        concrete_pairs.append((compound, entity))

    for compound, entity in concrete_pairs:
        entity_query = query_safe_label(entity)
        for template in templates["evidence"]:
            query = template.format(compound=compound, entity=entity_query)
            if not add_seed("evidence", query, compound, entity):
                return out, counts

    return out, counts


def parse_seed(text: str) -> Seed:
    parts = [p.strip() for p in text.split("|", 2)]
    if len(parts) != 3:
        raise ValueError(f"Invalid --seed format: `{text}` expected `query|compound|entity`")
    if not parts[0]:
        raise ValueError(f"Invalid --seed format: `{text}` query cannot be empty")
    return Seed(query=parts[0], compound=parts[1], entity=parts[2])


def build_seed_list(
    dataset: str,
    seed_values: List[str],
    query_values: List[str],
    allowlists: Dict[str, List[str]],
    expand_from_config: bool,
    auto_seeds_only: bool,
    auto_template_mode: str,
    auto_max_compounds: int,
    auto_max_entities: int,
    auto_max_pairs: int,
    auto_max_seeds: int,
    balanced_seed_profile: str = "off",
    balanced_max_compounds: int = 20,
    balanced_max_entities: int = 50,
    balanced_max_seeds: int = 250,
) -> tuple[List[Seed], Dict[str, int]]:
    manual = parse_manual_seeds(seed_values=seed_values, query_values=query_values)
    default = [parse_seed(value) for value in DEFAULT_SEEDS[dataset]]
    auto = (
        generate_auto_seeds(
            dataset=dataset,
            allowlists=allowlists,
            template_mode=auto_template_mode,
            max_compounds=max(0, auto_max_compounds),
            max_entities=max(0, auto_max_entities),
            max_pairs=max(0, auto_max_pairs),
            max_seeds=max(0, auto_max_seeds),
        )
        if expand_from_config or auto_seeds_only
        else []
    )

    seeds: List[Seed] = []
    if manual:
        seeds.extend(manual)
    elif not auto_seeds_only:
        seeds.extend(default)
    if expand_from_config or auto_seeds_only:
        seeds.extend(auto)

    base = dedupe_seeds(seeds)
    balanced, balanced_counts = generate_balanced_seeds(
        dataset=dataset,
        allowlists=allowlists,
        base_seeds=base,
        profile=balanced_seed_profile,
        max_compounds=max(0, balanced_max_compounds),
        max_entities=max(0, balanced_max_entities),
        max_seeds=max(0, balanced_max_seeds),
    )
    seeds.extend(balanced)

    merged = dedupe_seeds(seeds)
    return merged, {
        "manual": len(manual),
        "default": 0 if manual or auto_seeds_only else len(default),
        "auto": len(auto),
        "balanced": len(balanced),
        "balanced_compound_gap": balanced_counts["compound_gap"],
        "balanced_entity_gap": balanced_counts["entity_gap"],
        "balanced_evidence": balanced_counts["evidence"],
        "final": len(merged),
    }


def authors_from_s2(authors: Iterable[dict], max_names: int = 10) -> str:
    names = []
    for author in authors:
        name = normalize(author.get("name", ""))
        if name:
            names.append(name)
        if len(names) >= max_names:
            break
    return "; ".join(names)


def authors_from_openalex(authorships: Iterable[dict], max_names: int = 10) -> str:
    names = []
    for authorship in authorships:
        author_obj = authorship.get("author") if isinstance(authorship, dict) else None
        if isinstance(author_obj, dict):
            name = normalize(author_obj.get("display_name", ""))
            if name:
                names.append(name)
        if len(names) >= max_names:
            break
    return "; ".join(names)


def authors_from_pubmed(authors: Iterable[dict], max_names: int = 10) -> str:
    names = []
    for author in authors:
        if not isinstance(author, dict):
            continue
        name = normalize(author.get("name", ""))
        if not name:
            last = normalize(author.get("lastname", ""))
            initials = normalize(author.get("initials", ""))
            name = f"{last} {initials}".strip()
        if name:
            names.append(name)
        if len(names) >= max_names:
            break
    return "; ".join(names)


def authors_from_crossref(authors: Iterable[dict], max_names: int = 10) -> str:
    names = []
    for author in authors:
        if not isinstance(author, dict):
            continue
        given = normalize(author.get("given", ""))
        family = normalize(author.get("family", ""))
        name = " ".join([part for part in [given, family] if part])
        if not name:
            name = normalize(author.get("name", ""))
        if name:
            names.append(name)
        if len(names) >= max_names:
            break
    return "; ".join(names)


def first_list_value(value: object) -> str:
    if isinstance(value, list):
        for item in value:
            text = normalize(item)
            if text:
                return text
        return ""
    return normalize(value)


def year_from_text(value: object) -> str:
    match = re.search(r"\b(18|19|20|21)\d{2}\b", normalize(value))
    return match.group(0) if match else ""


def year_from_crossref_date(*values: object) -> str:
    for value in values:
        if not isinstance(value, dict):
            continue
        date_parts = value.get("date-parts")
        if not isinstance(date_parts, list) or not date_parts:
            continue
        first = date_parts[0]
        if isinstance(first, list) and first:
            year = normalize(first[0])
            if re.match(r"^\d{4}$", year):
                return year
    return ""


def doi_from_articleids(articleids: Iterable[dict]) -> str:
    for item in articleids:
        if not isinstance(item, dict):
            continue
        id_type = normalize(item.get("idtype", "")).lower()
        value = normalize(item.get("value", ""))
        if id_type == "doi" and value:
            return normalize_doi(value)
    return ""


def pmcid_from_articleids(articleids: Iterable[dict]) -> str:
    for item in articleids:
        if not isinstance(item, dict):
            continue
        id_type = normalize(item.get("idtype", "")).lower()
        value = normalize(item.get("value", ""))
        if id_type in {"pmc", "pmcid"} and value:
            return value if value.upper().startswith("PMC") else f"PMC{value}"
    return ""


def search_semantic_scholar(
    client: RateLimitedHttpClient,
    api_key: str,
    seed: Seed,
    max_results: int,
    require_doi: bool,
) -> List[dict]:
    endpoint = "https://api.semanticscholar.org/graph/v1/paper/search"
    headers = {"x-api-key": api_key} if api_key else {}

    rows: List[dict] = []
    offset = 0
    while len(rows) < max_results:
        page_size = min(100, max_results - len(rows))
        params = {
            "query": seed.query,
            "limit": page_size,
            "offset": offset,
            "fields": "title,year,externalIds,authors,url",
        }
        payload = client.get_json(endpoint, params=params, headers=headers)
        items = payload.get("data", []) or []
        if not items:
            break

        for item in items:
            external_ids = item.get("externalIds", {}) if isinstance(item, dict) else {}
            doi = normalize_doi(external_ids.get("DOI", ""))
            if require_doi and not doi:
                continue

            row = {
                "doi": doi,
                "openalex_id": "",
                "title": normalize(item.get("title", "")),
                "year": item.get("year", ""),
                "authors": authors_from_s2(item.get("authors", []) or []),
                "compound": seed.compound,
                "entity": seed.entity,
                "query": seed.query,
                "provider": "semantic_scholar",
            }
            rows.append(row)
            if len(rows) >= max_results:
                break

        offset += len(items)
        total = payload.get("total")
        if isinstance(total, int) and offset >= total:
            break

    return rows


def semantic_scholar_paper_to_row(
    paper: dict,
    seed: Seed,
    provider: str,
    query: str,
    source_doi: str,
    direction: str,
    require_doi: bool,
) -> Optional[dict]:
    if not isinstance(paper, dict):
        return None
    external_ids = paper.get("externalIds", {}) if isinstance(paper, dict) else {}
    doi = normalize_doi(external_ids.get("DOI", ""))
    if require_doi and not doi:
        return None
    return {
        "doi": doi,
        "openalex_id": "",
        "title": normalize(paper.get("title", "")),
        "year": paper.get("year", ""),
        "authors": authors_from_s2(paper.get("authors", []) or []),
        "compound": seed.compound,
        "entity": seed.entity,
        "query": query,
        "provider": provider,
        "citation_source_doi": source_doi,
        "citation_direction": direction,
    }


def search_semantic_scholar_edges(
    client: RateLimitedHttpClient,
    api_key: str,
    source_doi: str,
    seed: Seed,
    direction: str,
    max_results: int,
    require_doi: bool,
) -> List[dict]:
    if direction not in {"references", "citations"}:
        raise ValueError(f"Unsupported Semantic Scholar edge direction: {direction}")

    paper_id = quote(f"DOI:{source_doi}", safe="")
    endpoint = f"https://api.semanticscholar.org/graph/v1/paper/{paper_id}/{direction}"
    headers = {"x-api-key": api_key} if api_key else {}
    item_key = "citedPaper" if direction == "references" else "citingPaper"
    provider = f"semantic_scholar_{direction}"
    rows: List[dict] = []
    offset = 0

    while len(rows) < max_results:
        page_size = min(100, max_results - len(rows))
        query = f"{direction}:DOI:{source_doi}"
        payload = client.get_json(
            endpoint,
            params={
                "fields": "title,year,externalIds,authors,url",
                "limit": page_size,
                "offset": offset,
            },
            headers=headers,
        )
        items = payload.get("data", []) if isinstance(payload, dict) else []
        if not items:
            break
        for item in items:
            paper = item.get(item_key, {}) if isinstance(item, dict) else {}
            row = semantic_scholar_paper_to_row(
                paper=paper,
                seed=seed,
                provider=provider,
                query=query,
                source_doi=source_doi,
                direction=direction,
                require_doi=require_doi,
            )
            if row:
                rows.append(row)
            if len(rows) >= max_results:
                break
        offset += len(items)
        if len(items) < page_size:
            break

    return rows


def search_openalex(
    client: RateLimitedHttpClient,
    email: str,
    api_key: str,
    seed: Seed,
    max_results: int,
    require_doi: bool,
) -> List[dict]:
    endpoint = "https://api.openalex.org/works"

    rows: List[dict] = []
    page = 1
    per_page = min(100, max_results)

    while len(rows) < max_results:
        params = {
            "search": seed.query,
            "per-page": per_page,
            "page": page,
            "select": "doi,display_name,publication_year,authorships,ids",
        }
        if api_key:
            params["api_key"] = api_key
        if email:
            params["mailto"] = email

        payload = client.get_json(endpoint, params=params, headers={})
        items = payload.get("results", []) or []
        if not items:
            break

        for item in items:
            doi = normalize_doi(item.get("doi", ""))
            if require_doi and not doi:
                continue

            ids = item.get("ids", {}) if isinstance(item, dict) else {}
            openalex_id = normalize(ids.get("openalex", ""))
            row = {
                "doi": doi,
                "openalex_id": openalex_id,
                "title": normalize(item.get("display_name", "")),
                "year": item.get("publication_year", ""),
                "authors": authors_from_openalex(item.get("authorships", []) or []),
                "compound": seed.compound,
                "entity": seed.entity,
                "query": seed.query,
                "provider": "openalex",
            }
            rows.append(row)
            if len(rows) >= max_results:
                break

        if len(items) < per_page:
            break
        page += 1

    return rows


def search_pubmed(
    client: RateLimitedHttpClient,
    email: str,
    api_key: str,
    seed: Seed,
    max_results: int,
    require_doi: bool,
) -> List[dict]:
    base = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
    common_params = {
        "tool": "psychedelics_kg",
        "email": email or None,
        "api_key": api_key or None,
    }
    search_payload = client.get_json(
        f"{base}/esearch.fcgi",
        params={
            **common_params,
            "db": "pubmed",
            "term": seed.query,
            "retmode": "json",
            "retmax": max_results,
            "sort": "relevance",
        },
        headers={},
    )
    ids = search_payload.get("esearchresult", {}).get("idlist", []) or []
    ids = [normalize(value) for value in ids if normalize(value)]
    if not ids:
        return []

    summary_payload = client.get_json(
        f"{base}/esummary.fcgi",
        params={
            **common_params,
            "db": "pubmed",
            "id": ",".join(ids),
            "retmode": "json",
        },
        headers={},
    )
    result = summary_payload.get("result", {}) if isinstance(summary_payload, dict) else {}

    rows: List[dict] = []
    for pmid in ids:
        item = result.get(pmid, {}) if isinstance(result, dict) else {}
        if not isinstance(item, dict):
            continue
        articleids = item.get("articleids", []) or []
        doi = doi_from_articleids(articleids) or normalize_doi(item.get("elocationid", ""))
        if require_doi and not doi:
            continue
        row = {
            "doi": doi,
            "openalex_id": "",
            "pmid": pmid,
            "pmcid": pmcid_from_articleids(articleids),
            "title": normalize(item.get("title", "")),
            "year": year_from_text(item.get("pubdate", "")),
            "authors": authors_from_pubmed(item.get("authors", []) or []),
            "compound": seed.compound,
            "entity": seed.entity,
            "query": seed.query,
            "provider": "pubmed",
        }
        rows.append(row)
    return rows


def search_pmc(
    client: RateLimitedHttpClient,
    email: str,
    api_key: str,
    seed: Seed,
    max_results: int,
    require_doi: bool,
) -> List[dict]:
    base = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
    common_params = {
        "tool": "psychedelics_kg",
        "email": email or None,
        "api_key": api_key or None,
    }
    search_payload = client.get_json(
        f"{base}/esearch.fcgi",
        params={
            **common_params,
            "db": "pmc",
            "term": seed.query,
            "retmode": "json",
            "retmax": max_results,
            "sort": "relevance",
        },
        headers={},
    )
    ids = search_payload.get("esearchresult", {}).get("idlist", []) or []
    ids = [normalize(value) for value in ids if normalize(value)]
    if not ids:
        return []

    summary_payload = client.get_json(
        f"{base}/esummary.fcgi",
        params={
            **common_params,
            "db": "pmc",
            "id": ",".join(ids),
            "retmode": "json",
        },
        headers={},
    )
    result = summary_payload.get("result", {}) if isinstance(summary_payload, dict) else {}

    pmcids = [f"PMC{value}" if not value.upper().startswith("PMC") else value for value in ids]
    idconv_by_pmcid: Dict[str, dict] = {}
    for start in range(0, len(pmcids), 200):
        batch = pmcids[start : start + 200]
        idconv_payload = client.get_json(
            "https://pmc.ncbi.nlm.nih.gov/tools/idconv/api/v1/articles/",
            params={
                "ids": ",".join(batch),
                "format": "json",
                "tool": "psychedelics_kg",
                "email": email or None,
            },
            headers={},
        )
        for record in idconv_payload.get("records", []) if isinstance(idconv_payload, dict) else []:
            if not isinstance(record, dict):
                continue
            pmcid = normalize(record.get("pmcid", ""))
            if pmcid:
                idconv_by_pmcid[pmcid.upper()] = record

    rows: List[dict] = []
    for raw_id in ids:
        pmcid = f"PMC{raw_id}" if not raw_id.upper().startswith("PMC") else raw_id
        idconv = idconv_by_pmcid.get(pmcid.upper(), {})
        item = result.get(raw_id, {}) if isinstance(result, dict) else {}
        if not isinstance(item, dict):
            item = {}
        articleids = item.get("articleids", []) or []
        doi = (
            normalize_doi(idconv.get("doi", ""))
            or doi_from_articleids(articleids)
            or normalize_doi(item.get("elocationid", ""))
        )
        if require_doi and not doi:
            continue
        row = {
            "doi": doi,
            "openalex_id": "",
            "pmid": normalize(idconv.get("pmid", "")),
            "pmcid": pmcid,
            "title": normalize(item.get("title", "")),
            "year": year_from_text(item.get("pubdate", "") or item.get("epubdate", "")),
            "authors": authors_from_pubmed(item.get("authors", []) or []),
            "compound": seed.compound,
            "entity": seed.entity,
            "query": seed.query,
            "provider": "pmc",
        }
        rows.append(row)
    return rows


def search_crossref(
    client: RateLimitedHttpClient,
    email: str,
    seed: Seed,
    max_results: int,
    require_doi: bool,
) -> List[dict]:
    params: Dict[str, object] = {
        "query.bibliographic": seed.query,
        "rows": min(1000, max_results),
        "sort": "score",
        "order": "desc",
        "select": "DOI,title,author,published,published-print,published-online,issued,type,URL",
    }
    if email:
        params["mailto"] = email

    payload = client.get_json("https://api.crossref.org/works", params=params, headers={})
    items = payload.get("message", {}).get("items", []) if isinstance(payload, dict) else []
    rows: List[dict] = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        doi = normalize_doi(item.get("DOI", ""))
        if require_doi and not doi:
            continue
        row = {
            "doi": doi,
            "openalex_id": "",
            "title": first_list_value(item.get("title", "")),
            "year": year_from_crossref_date(
                item.get("published", {}),
                item.get("published-online", {}),
                item.get("published-print", {}),
                item.get("issued", {}),
            ),
            "authors": authors_from_crossref(item.get("author", []) or []),
            "compound": seed.compound,
            "entity": seed.entity,
            "query": seed.query,
            "provider": "crossref",
            "crossref_type": normalize(item.get("type", "")),
        }
        rows.append(row)
    return rows


def usable_email(value: str) -> str:
    email = normalize(value)
    if "@" not in email:
        return ""
    lowered = email.lower()
    if lowered.endswith("@example.com") or lowered in {"test@test.com", "none@none.com"}:
        return ""
    return email


def enrich_rows_unpaywall(
    client: RateLimitedHttpClient,
    email: str,
    rows: List[dict],
) -> tuple[List[dict], List[dict]]:
    usable = usable_email(email)
    if not usable:
        return rows, [{"error": "unpaywall_email_missing_or_placeholder"}]

    cache: Dict[str, dict] = {}
    errors: List[dict] = []
    for row in rows:
        doi = normalize_doi(row.get("doi", ""))
        if not doi:
            continue
        key = doi.lower()
        if key not in cache:
            try:
                cache[key] = client.get_json(
                    f"https://api.unpaywall.org/v2/{quote(doi, safe='')}",
                    params={"email": usable},
                    headers={},
                )
            except HTTPError as err:
                cache[key] = {}
                errors.append({"doi": doi, "error": f"HTTPError {err.code}"})
            except Exception as err:
                cache[key] = {}
                errors.append({"doi": doi, "error": f"{type(err).__name__}: {err}"})

        payload = cache.get(key, {})
        best = payload.get("best_oa_location", {}) if isinstance(payload, dict) else {}
        row["unpaywall_is_oa"] = "true" if bool(payload.get("is_oa")) else "false"
        row["unpaywall_oa_status"] = normalize(payload.get("oa_status", ""))
        row["unpaywall_best_url"] = normalize(best.get("url", "")) if isinstance(best, dict) else ""
        row["unpaywall_best_pdf_url"] = normalize(best.get("url_for_pdf", "")) if isinstance(best, dict) else ""
        row["unpaywall_checked"] = "true"
    return rows, errors


def merge_rows(rows: List[dict]) -> List[dict]:
    merged: Dict[str, dict] = {}
    fill_forward_fields = [
        "pmid",
        "pmcid",
        "crossref_type",
        "unpaywall_is_oa",
        "unpaywall_oa_status",
        "unpaywall_best_url",
        "unpaywall_best_pdf_url",
        "unpaywall_checked",
    ]
    for row in rows:
        doi_key = normalize(row.get("doi", "")).lower()
        title_key = normalize(row.get("title", "")).lower()
        year_key = normalize(row.get("year", ""))
        key = f"doi:{doi_key}" if doi_key else f"title:{title_key}|year:{year_key}"

        existing = merged.get(key)
        if not existing:
            merged[key] = {
                **row,
                "providers": [row.get("provider", "")],
                "queries": [row.get("query", "")],
            }
            continue

        if not normalize(existing.get("authors", "")) and normalize(row.get("authors", "")):
            existing["authors"] = row.get("authors", "")
        if not normalize(existing.get("doi", "")) and normalize(row.get("doi", "")):
            existing["doi"] = row.get("doi", "")
        if not normalize(existing.get("openalex_id", "")) and normalize(row.get("openalex_id", "")):
            existing["openalex_id"] = row.get("openalex_id", "")
        if not normalize(existing.get("title", "")) and normalize(row.get("title", "")):
            existing["title"] = row.get("title", "")
        if not normalize(existing.get("year", "")) and normalize(row.get("year", "")):
            existing["year"] = row.get("year", "")
        for field in fill_forward_fields:
            if not normalize(existing.get(field, "")) and normalize(row.get(field, "")):
                existing[field] = row.get(field, "")
        if row.get("provider") and row.get("provider") not in existing["providers"]:
            existing["providers"].append(row.get("provider"))
        if row.get("query") and row.get("query") not in existing["queries"]:
            existing["queries"].append(row.get("query"))

    items = list(merged.values())
    items.sort(key=lambda r: (-(int(r.get("year") or 0)), normalize(r.get("title", ""))))
    return items


def write_queue(path: Path, rows: List[dict], dataset: str) -> None:
    entity_name = "target" if dataset == "mechanistic" else "disorder"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(f"# discovered queue ({dataset}) generated at {now_utc()}\n")
        handle.write(f"# doi,compound,{entity_name},optional_study_title,optional_study_year,optional_authors\n")
        writer = csv.writer(handle)
        for row in rows:
            writer.writerow(
                [
                    normalize(row.get("doi", "")),
                    normalize(row.get("compound", "")),
                    normalize(row.get("entity", "")),
                    normalize(row.get("title", "")),
                    normalize(row.get("year", "")),
                    normalize(row.get("authors", "")),
                ]
            )


def read_float(maybe_value: object, default: float) -> float:
    if maybe_value is None:
        return default
    try:
        return float(maybe_value)
    except Exception:
        return default


def read_int(maybe_value: object, default: int) -> int:
    if maybe_value is None:
        return default
    try:
        return int(maybe_value)
    except Exception:
        return default


def read_json(path: Path, default: object) -> object:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def doi_key(raw: object) -> str:
    return normalize_doi(raw).lower()


def context_from_values(compound: object, entity: object, title: object, year: object, source: str) -> dict:
    return {
        "compound": normalize(compound),
        "entity": normalize(entity),
        "study_title": normalize(title),
        "study_year": normalize(year),
        "source": source,
    }


def append_context(out: Dict[str, List[dict]], doi: str, context: dict) -> None:
    key = doi_key(doi)
    if not key:
        return
    values = out.setdefault(key, [])
    if context not in values:
        values.append(context)


def read_queue_contexts(path: Path, source_name: str) -> Dict[str, List[dict]]:
    out: Dict[str, List[dict]] = {}
    if not path.exists():
        return out
    with path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.reader(handle):
            if not row:
                continue
            first = normalize(row[0])
            if not first or first.startswith("#"):
                continue
            doi = normalize_doi(first)
            append_context(
                out,
                doi,
                context_from_values(
                    row[1] if len(row) > 1 else "",
                    row[2] if len(row) > 2 else "",
                    row[3] if len(row) > 3 else "",
                    row[4] if len(row) > 4 else "",
                    source_name,
                ),
            )
    return out


def read_curated_contexts(path: Path, dataset: str) -> Dict[str, List[dict]]:
    out: Dict[str, List[dict]] = {}
    payload = read_json(path, [])
    if not isinstance(payload, list):
        return out
    entity_field = "target" if dataset == "mechanistic" else "disorder"
    for row in payload:
        if not isinstance(row, dict):
            continue
        doi = normalize_doi(row.get("study_doi", ""))
        append_context(
            out,
            doi,
            context_from_values(
                row.get("compound", ""),
                row.get(entity_field, ""),
                row.get("study_title", ""),
                row.get("study_year", ""),
                "curated",
            ),
        )
    return out


def read_paper_library_contexts(path: Path) -> Dict[str, List[dict]]:
    out: Dict[str, List[dict]] = {}
    payload = read_json(path, [])
    if not isinstance(payload, list):
        return out
    for row in payload:
        if not isinstance(row, dict):
            continue
        doi = normalize_doi(row.get("study_doi", ""))
        contexts = row.get("contexts", [])
        if isinstance(contexts, list):
            for context in contexts:
                if not isinstance(context, dict):
                    continue
                append_context(
                    out,
                    doi,
                    context_from_values(
                        context.get("compound", ""),
                        context.get("entity", ""),
                        context.get("study_title", row.get("study_title", "")),
                        context.get("study_year", row.get("study_year", "")),
                        "paper_library",
                    ),
                )
        append_context(
            out,
            doi,
            context_from_values("", "", row.get("study_title", ""), row.get("study_year", ""), "paper_library"),
        )
    return out


def read_known_doi_file(path: Path, source_name: str) -> Dict[str, List[dict]]:
    out: Dict[str, List[dict]] = {}
    if not path.exists():
        return out
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        doi = normalize_doi(line.split(",", 1)[0])
        append_context(out, doi, context_from_values("", "", "", "", source_name))
    return out


def read_benchmark_manifest_contexts(path: Path, dataset: str) -> Dict[str, List[dict]]:
    out: Dict[str, List[dict]] = {}
    payload = read_json(path, {})
    if not isinstance(payload, dict):
        return out
    entries = payload.get("entries", [])
    if not isinstance(entries, list):
        return out
    for entry in entries:
        if not isinstance(entry, dict) or normalize(entry.get("dataset", "")) != dataset:
            continue
        doi = normalize_doi(entry.get("doi", ""))
        entity = entry.get("target", "") if dataset == "mechanistic" else entry.get("disorder", "")
        append_context(
            out,
            doi,
            context_from_values(
                entry.get("compound", ""),
                entity,
                entry.get("title", ""),
                entry.get("year", ""),
                f"known_study:{normalize(entry.get('tier', '')) or 'unspecified'}",
            ),
        )
    return out


def read_benchmark_manifest_seed_rows(path: Path, dataset: str, max_rows: int) -> List[dict]:
    payload = read_json(path, {})
    if not isinstance(payload, dict):
        return []
    entries = payload.get("entries", [])
    if not isinstance(entries, list):
        return []

    rows: List[dict] = []
    seen: Set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict) or normalize(entry.get("dataset", "")) != dataset:
            continue
        doi = normalize_doi(entry.get("doi", ""))
        key = doi.lower()
        if not key or key in seen:
            continue
        seen.add(key)
        entity = entry.get("target", "") if dataset == "mechanistic" else entry.get("disorder", "")
        rows.append(
            {
                "doi": doi,
                "compound": normalize(entry.get("compound", "")),
                "entity": normalize(entity),
                "title": normalize(entry.get("title", "")),
                "year": normalize(entry.get("year", "")),
            }
        )
        if max_rows > 0 and len(rows) >= max_rows:
            break
    return rows


def rows_to_citation_source_seeds(rows: List[dict], max_rows: int) -> List[tuple[str, Seed]]:
    out: List[tuple[str, Seed]] = []
    seen: Set[str] = set()
    for row in rows:
        doi = normalize_doi(row.get("doi", ""))
        key = doi.lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(
            (
                doi,
                Seed(
                    query=normalize(row.get("title", "")) or doi,
                    compound=normalize(row.get("compound", "")),
                    entity=normalize(row.get("entity", "")),
                ),
            )
        )
        if max_rows > 0 and len(out) >= max_rows:
            break
    return out


def merge_context_maps(*maps: Dict[str, List[dict]]) -> Dict[str, List[dict]]:
    merged: Dict[str, List[dict]] = {}
    for mapping in maps:
        for doi, contexts in mapping.items():
            for context in contexts:
                append_context(merged, doi, context)
    return merged


def protected_sources_for_dataset(dataset: str, benchmark_manifest: Path) -> Dict[str, List[dict]]:
    curated = (
        ROOT / "data" / "curated" / "claims.json"
        if dataset == "mechanistic"
        else ROOT / "data" / "curated" / "disorder_claims.json"
    )
    return merge_context_maps(
        read_benchmark_manifest_contexts(benchmark_manifest, dataset),
        read_known_doi_file(ROOT / "data" / "raw" / f"benchmark_known_dois.{dataset}.txt", "known_study_legacy_file"),
        read_queue_contexts(ROOT / "data" / "raw" / f"doi_queue.{dataset}.triage_relevant.txt", "triage_queue"),
        read_paper_library_contexts(ROOT / "data" / "processed" / f"paper_library_{dataset}.json"),
        read_curated_contexts(curated, dataset),
    )


def apply_protected_retention(
    rows: List[dict],
    max_results: int,
    protected_sources: Dict[str, List[dict]],
) -> tuple[List[dict], dict]:
    if max_results <= 0:
        return rows, {
            "enabled": False,
            "max_results": max_results,
            "protected_dois_available": 0,
            "protected_dois_retained": 0,
            "protected_over_cap": 0,
            "dropped_rows": 0,
        }

    protected_dois = set(protected_sources.keys())
    available_protected = {doi_key(row.get("doi", "")) for row in rows if doi_key(row.get("doi", "")) in protected_dois}

    selected: List[dict] = []
    seen: Set[str] = set()
    for row in rows:
        key = doi_key(row.get("doi", "")) or f"title:{normalize(row.get('title', '')).lower()}|{normalize(row.get('year', ''))}"
        if doi_key(row.get("doi", "")) not in protected_dois or key in seen:
            continue
        selected.append(row)
        seen.add(key)

    protected_over_cap = max(0, len(selected) - max_results)
    for row in rows:
        if len(selected) >= max_results:
            break
        key = doi_key(row.get("doi", "")) or f"title:{normalize(row.get('title', '')).lower()}|{normalize(row.get('year', ''))}"
        if key in seen:
            continue
        selected.append(row)
        seen.add(key)

    retained_protected = {doi_key(row.get("doi", "")) for row in selected if doi_key(row.get("doi", "")) in protected_dois}
    return selected, {
        "enabled": True,
        "max_results": max_results,
        "protected_dois_configured": len(protected_dois),
        "protected_dois_available": len(available_protected),
        "protected_dois_retained": len(retained_protected),
        "protected_over_cap": max(0, len(selected) - max_results),
        "dropped_rows": max(0, len(rows) - len(selected)),
    }


def context_from_discovery_row(row: dict) -> dict:
    return context_from_values(
        row.get("compound", ""),
        row.get("entity", ""),
        row.get("title", ""),
        row.get("year", ""),
        f"discovery:{normalize(row.get('provider', ''))}",
    )


def load_ledger(path: Path, dataset: str) -> Dict[str, dict]:
    payload = read_json(path, {})
    entries = payload.get("entries", []) if isinstance(payload, dict) else []
    out: Dict[str, dict] = {}
    if not isinstance(entries, list):
        return out
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        doi = doi_key(entry.get("doi", ""))
        if doi:
            out[doi] = entry
    return out


def update_ledger(
    existing: Dict[str, dict],
    dataset: str,
    run_id: str,
    run_meta: dict,
    all_rows: List[dict],
    retained_rows: List[dict],
    protected_sources: Dict[str, List[dict]],
) -> dict:
    now = normalize(run_meta.get("generated_at", "")) or now_utc()
    all_by_doi = {doi_key(row.get("doi", "")): row for row in all_rows if doi_key(row.get("doi", ""))}
    retained_by_doi = {doi_key(row.get("doi", "")): row for row in retained_rows if doi_key(row.get("doi", ""))}
    all_dois = sorted(set(existing.keys()) | set(all_by_doi.keys()) | set(protected_sources.keys()))
    entries: List[dict] = []

    for doi in all_dois:
        previous = existing.get(doi, {})
        row = all_by_doi.get(doi, retained_by_doi.get(doi, {}))
        providers = set(previous.get("providers", []) if isinstance(previous.get("providers", []), list) else [])
        queries = set(previous.get("queries", []) if isinstance(previous.get("queries", []), list) else [])
        contexts = previous.get("contexts", []) if isinstance(previous.get("contexts", []), list) else []

        if doi in all_by_doi:
            providers.update([normalize(p) for p in row.get("providers", []) if normalize(p)])
            if normalize(row.get("provider", "")):
                providers.add(normalize(row.get("provider", "")))
            queries.update([normalize(q) for q in row.get("queries", []) if normalize(q)])
            if normalize(row.get("query", "")):
                queries.add(normalize(row.get("query", "")))
            context = context_from_discovery_row(row)
            if context not in contexts:
                contexts.append(context)

        for protected_context in protected_sources.get(doi, []):
            if protected_context not in contexts:
                contexts.append(protected_context)

        protected_labels = sorted(
            {
                normalize(context.get("source", ""))
                for context in protected_sources.get(doi, [])
                if normalize(context.get("source", ""))
            }
        )
        first_seen = normalize(previous.get("first_seen_utc", "")) or (now if doi in all_by_doi else "")
        last_seen = now if doi in all_by_doi else normalize(previous.get("last_seen_utc", ""))
        title = normalize(row.get("title", "")) or normalize(previous.get("title", ""))
        year = normalize(row.get("year", "")) or normalize(previous.get("year", ""))
        authors = normalize(row.get("authors", "")) or normalize(previous.get("authors", ""))

        entries.append(
            {
                "doi": doi,
                "dataset": dataset,
                "title": title,
                "year": year,
                "authors": authors,
                "first_seen_utc": first_seen,
                "last_seen_utc": last_seen,
                "seen_in_latest_run": doi in all_by_doi,
                "retained_in_latest_queue": doi in retained_by_doi,
                "providers": sorted(providers),
                "queries": sorted(queries),
                "contexts": contexts,
                "protected_sources": protected_labels,
                "is_known_study": any(
                    label.startswith("known_study") or label.startswith("benchmark")
                    for label in protected_labels
                ),
                "is_benchmark": any(
                    label.startswith("known_study") or label.startswith("benchmark")
                    for label in protected_labels
                ),
                "is_curated": "curated" in protected_labels,
                "in_paper_library": "paper_library" in protected_labels,
                "in_triage_queue": "triage_queue" in protected_labels,
                "latest_run_id": run_id if doi in all_by_doi else normalize(previous.get("latest_run_id", "")),
            }
        )

    entries.sort(key=lambda item: (not item.get("seen_in_latest_run", False), normalize(item.get("doi", ""))))
    return {
        "version": "0.1",
        "dataset": dataset,
        "updated_at_utc": now,
        "latest_run": run_meta,
        "counts": {
            "entries": len(entries),
            "seen_in_latest_run": sum(1 for entry in entries if entry.get("seen_in_latest_run")),
            "retained_in_latest_queue": sum(1 for entry in entries if entry.get("retained_in_latest_queue")),
            "known_study_entries": sum(1 for entry in entries if entry.get("is_known_study")),
            "benchmark_entries": sum(1 for entry in entries if entry.get("is_benchmark")),
            "curated_entries": sum(1 for entry in entries if entry.get("is_curated")),
        },
        "entries": entries,
    }


def write_ledger(path: Path, ledger: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(ledger, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Discover literature and generate DOI queue")
    parser.add_argument("--dataset", choices=["mechanistic", "disorder"], required=True)
    parser.add_argument(
        "--provider",
        choices=sorted(PROVIDER_BACKENDS.keys()),
        default="semantic_scholar",
        help=(
            "Search backend. hybrid = Semantic Scholar + OpenAlex; "
            "biomedical = PubMed + PMC + Crossref; comprehensive = all supported search backends."
        ),
    )
    parser.add_argument("--seed", action="append", default=[], help="Seed as query|compound|entity")
    parser.add_argument("--query", action="append", default=[], help="Query only (compound/entity left blank)")
    parser.add_argument(
        "--expand-seeds-from-config",
        action="store_true",
        help="Generate extra seeds from allowlists in --config (high-recall mode)",
    )
    parser.add_argument(
        "--auto-seeds-only",
        action="store_true",
        help="Use only auto-generated seeds from allowlists (skip defaults unless manual --seed/--query provided)",
    )
    parser.add_argument(
        "--auto-template-mode",
        choices=["focused", "broad"],
        default="focused",
        help="Template breadth for auto-generated seeds (default: focused)",
    )
    parser.add_argument(
        "--auto-max-compounds",
        type=int,
        default=0,
        help="Max compounds used for auto seed generation (0 = all)",
    )
    parser.add_argument(
        "--auto-max-entities",
        type=int,
        default=0,
        help="Max targets/disorders used for auto seed generation (0 = all)",
    )
    parser.add_argument(
        "--auto-max-pairs",
        type=int,
        default=400,
        help="Max compound-entity pairs used for auto seeds (0 = all, default: 400)",
    )
    parser.add_argument(
        "--auto-max-seeds",
        type=int,
        default=1200,
        help="Max auto-generated seeds after templates (0 = all, default: 1200)",
    )
    parser.add_argument(
        "--balanced-seed-profile",
        choices=["off", "coverage", "evidence"],
        default="off",
        help=(
            "Add bounded, auditable seeds for allowlist coverage gaps. coverage adds "
            "compound-only/entity-only gap seeds; evidence also adds evidence-type variants "
            "for selected compound-entity seeds."
        ),
    )
    parser.add_argument(
        "--balanced-max-compounds",
        type=int,
        default=20,
        help="Max allowed compounds considered by balanced seed profiles (0 = all, default: 20)",
    )
    parser.add_argument(
        "--balanced-max-entities",
        type=int,
        default=50,
        help="Max allowed targets/disorders considered by balanced seed profiles (0 = all, default: 50)",
    )
    parser.add_argument(
        "--balanced-max-seeds",
        type=int,
        default=250,
        help="Max balanced seeds to add (0 = all, default: 250)",
    )
    parser.add_argument(
        "--query-variant-mode",
        choices=["off", "conservative", "expanded"],
        default="off",
        help=(
            "Generate provider-specific query variants. conservative adds PubMed/PMC "
            "fielded synonym queries; expanded also adds alias phrase variants to broad providers."
        ),
    )
    parser.add_argument(
        "--citation-chase",
        choices=["off", "known-study-set", "benchmark", "query-results"],
        default="off",
        help=(
            "Optionally expand discovery using Semantic Scholar references/citations. "
            "The older 'benchmark' value is retained as a compatibility alias."
        ),
    )
    parser.add_argument(
        "--citation-chase-directions",
        choices=["references", "citations", "both"],
        default="references",
        help="Citation edge directions to follow when --citation-chase is enabled.",
    )
    parser.add_argument("--citation-chase-max-source-dois", type=int, default=25)
    parser.add_argument("--citation-chase-max-results-per-doi", type=int, default=20)
    parser.add_argument("--max-results-per-seed", type=int, default=20)
    parser.add_argument("--max-results", type=int, default=120)
    parser.add_argument("--require-doi", action="store_true", default=True)
    parser.add_argument("--allow-missing-doi", action="store_true")
    parser.add_argument("--config", default=str(ROOT / "pipeline" / "config.example.yaml"))
    parser.add_argument("--semantic-scholar-api-key", default="")
    parser.add_argument("--semantic-scholar-rps", type=float, default=None)
    parser.add_argument("--openalex-email", default="")
    parser.add_argument("--openalex-api-key", default="")
    parser.add_argument("--openalex-rps", type=float, default=None)
    parser.add_argument("--ncbi-email", default="")
    parser.add_argument("--ncbi-api-key", default="")
    parser.add_argument("--pubmed-rps", type=float, default=None)
    parser.add_argument("--pmc-rps", type=float, default=None)
    parser.add_argument("--crossref-email", default="")
    parser.add_argument("--crossref-rps", type=float, default=None)
    parser.add_argument("--unpaywall-email", default="")
    parser.add_argument("--unpaywall-rps", type=float, default=None)
    parser.add_argument(
        "--enrich-unpaywall",
        action="store_true",
        help="Enrich final DOI rows with Unpaywall OA/PDF metadata; comprehensive provider enables this automatically when an email is available",
    )
    parser.add_argument(
        "--skip-unpaywall-enrichment",
        action="store_true",
        help="Skip Unpaywall enrichment even when --provider comprehensive is used",
    )
    parser.add_argument("--max-retries", type=int, default=None)
    parser.add_argument("--queue-out", default="")
    parser.add_argument("--report-out", default="")
    parser.add_argument(
        "--benchmark-manifest",
        "--known-study-manifest",
        dest="benchmark_manifest",
        default=str(ROOT / "data" / "raw" / "benchmark_manifest.json"),
        help=(
            "Known relevant study set used for protected retention and report provenance. "
            "The older flag name is retained for compatibility."
        ),
    )
    parser.add_argument(
        "--ledger-out",
        default="",
        help="Cumulative discovery ledger path (default: data/processed/discovery_ledger_<dataset>.json)",
    )
    parser.add_argument(
        "--disable-ledger",
        action="store_true",
        help="Skip writing the cumulative discovery ledger",
    )
    parser.add_argument(
        "--disable-protected-retention",
        action="store_true",
        help="Do not pin known-study/curated/library DOIs before applying --max-results",
    )
    parser.add_argument(
        "--progress",
        action="store_true",
        help="Print progress updates while processing seeds",
    )
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    config = load_config(config_path)
    s2_cfg = config.get("semantic_scholar", {}) if isinstance(config.get("semantic_scholar", {}), dict) else {}
    oa_cfg = config.get("openalex", {}) if isinstance(config.get("openalex", {}), dict) else {}
    pubmed_cfg = config.get("pubmed", {}) if isinstance(config.get("pubmed", {}), dict) else {}
    pmc_cfg = config.get("pmc", {}) if isinstance(config.get("pmc", {}), dict) else {}
    crossref_cfg = config.get("crossref", {}) if isinstance(config.get("crossref", {}), dict) else {}
    unpaywall_cfg = config.get("unpaywall", {}) if isinstance(config.get("unpaywall", {}), dict) else {}

    s2_api_key = args.semantic_scholar_api_key or str(s2_cfg.get("api_key", "")) or os.getenv("S2_API_KEY", "")
    oa_email = args.openalex_email or str(oa_cfg.get("email", "")) or os.getenv("OPENALEX_EMAIL", "")
    oa_api_key = args.openalex_api_key or str(oa_cfg.get("api_key", "")) or os.getenv("OPENALEX_API_KEY", "")
    ncbi_email = (
        args.ncbi_email
        or str(pubmed_cfg.get("email", ""))
        or os.getenv("NCBI_EMAIL", "")
        or oa_email
    )
    ncbi_api_key = (
        args.ncbi_api_key
        or str(pubmed_cfg.get("api_key", ""))
        or os.getenv("NCBI_API_KEY", "")
    )
    crossref_email = (
        args.crossref_email
        or str(crossref_cfg.get("email", ""))
        or os.getenv("CROSSREF_EMAIL", "")
        or oa_email
    )
    unpaywall_email = (
        args.unpaywall_email
        or str(unpaywall_cfg.get("email", ""))
        or os.getenv("UNPAYWALL_EMAIL", "")
        or crossref_email
        or oa_email
    )

    # Conservative defaults because Semantic Scholar has stricter limits.
    s2_rps = args.semantic_scholar_rps if args.semantic_scholar_rps is not None else read_float(s2_cfg.get("rate_limit_per_sec"), 0.33)
    oa_rps = args.openalex_rps if args.openalex_rps is not None else read_float(oa_cfg.get("rate_limit_per_sec"), 2.0)
    pubmed_rps = args.pubmed_rps if args.pubmed_rps is not None else read_float(pubmed_cfg.get("rate_limit_per_sec"), 2.5)
    pmc_rps = args.pmc_rps if args.pmc_rps is not None else read_float(pmc_cfg.get("rate_limit_per_sec"), pubmed_rps)
    crossref_rps = args.crossref_rps if args.crossref_rps is not None else read_float(crossref_cfg.get("rate_limit_per_sec"), 5.0)
    unpaywall_rps = args.unpaywall_rps if args.unpaywall_rps is not None else read_float(unpaywall_cfg.get("rate_limit_per_sec"), 2.0)
    max_retries = args.max_retries if args.max_retries is not None else read_int(s2_cfg.get("max_retries"), 4)

    allowlists = parse_allowlists(config_path)
    seeds, seed_source_counts = build_seed_list(
        dataset=args.dataset,
        seed_values=args.seed,
        query_values=args.query,
        allowlists=allowlists,
        expand_from_config=args.expand_seeds_from_config,
        auto_seeds_only=args.auto_seeds_only,
        auto_template_mode=args.auto_template_mode,
        auto_max_compounds=args.auto_max_compounds,
        auto_max_entities=args.auto_max_entities,
        auto_max_pairs=args.auto_max_pairs,
        auto_max_seeds=args.auto_max_seeds,
        balanced_seed_profile=args.balanced_seed_profile,
        balanced_max_compounds=args.balanced_max_compounds,
        balanced_max_entities=args.balanced_max_entities,
        balanced_max_seeds=args.balanced_max_seeds,
    )
    if not seeds:
        raise SystemExit("No seeds found. Add --seed/--query or enable --expand-seeds-from-config.")
    require_doi = args.require_doi and not args.allow_missing_doi

    queue_out = (
        Path(args.queue_out).resolve()
        if args.queue_out
        else ROOT / "data" / "raw" / f"doi_queue.{args.dataset}.discovered.txt"
    )
    report_out = (
        Path(args.report_out).resolve()
        if args.report_out
        else ROOT / "data" / "processed" / f"discovery_report_{args.dataset}.json"
    )
    benchmark_manifest = Path(args.benchmark_manifest).resolve()
    ledger_out = (
        Path(args.ledger_out).resolve()
        if args.ledger_out
        else ROOT / "data" / "processed" / f"discovery_ledger_{args.dataset}.json"
    )

    s2_client = RateLimitedHttpClient(rps=s2_rps, max_retries=max_retries, user_agent="kg-pipeline/semantic-scholar")
    oa_client = RateLimitedHttpClient(rps=oa_rps, max_retries=max_retries, user_agent="kg-pipeline/openalex")
    pubmed_client = RateLimitedHttpClient(rps=pubmed_rps, max_retries=max_retries, user_agent="kg-pipeline/pubmed")
    pmc_client = RateLimitedHttpClient(rps=pmc_rps, max_retries=max_retries, user_agent="kg-pipeline/pmc")
    crossref_client = RateLimitedHttpClient(rps=crossref_rps, max_retries=max_retries, user_agent="kg-pipeline/crossref")
    unpaywall_client = RateLimitedHttpClient(rps=unpaywall_rps, max_retries=max_retries, user_agent="kg-pipeline/unpaywall")

    all_rows: List[dict] = []
    per_seed = []
    provider_errors: List[dict] = []
    provider_query_counts: Counter[str] = Counter()
    backends = PROVIDER_BACKENDS[args.provider]

    seed_total = len(seeds)
    for seed_idx, seed in enumerate(seeds, start=1):
        seed_rows: List[dict] = []
        seed_errors: List[str] = []

        if args.progress:
            pct = (seed_idx - 1) / max(1, seed_total) * 100.0
            print(
                f"PROGRESS: discovery seed {seed_idx}/{seed_total} ({pct:.1f}%) "
                f"query={seed.query}",
                flush=True,
            )

        if "semantic_scholar" in backends:
            for provider_seed in query_variants_for_backend(seed, args.dataset, "semantic_scholar", args.query_variant_mode):
                provider_query_counts["semantic_scholar"] += 1
                try:
                    seed_rows.extend(
                        search_semantic_scholar(
                            client=s2_client,
                            api_key=s2_api_key,
                            seed=provider_seed,
                            max_results=args.max_results_per_seed,
                            require_doi=require_doi,
                        )
                    )
                except Exception as err:
                    seed_errors.append(f"semantic_scholar: {type(err).__name__}: {err}")
                    provider_errors.append({"provider": "semantic_scholar", "query": provider_seed.query, "error": f"{type(err).__name__}: {err}"})

        if "openalex" in backends:
            for provider_seed in query_variants_for_backend(seed, args.dataset, "openalex", args.query_variant_mode):
                provider_query_counts["openalex"] += 1
                try:
                    seed_rows.extend(
                        search_openalex(
                            client=oa_client,
                            email=oa_email,
                            api_key=oa_api_key,
                            seed=provider_seed,
                            max_results=args.max_results_per_seed,
                            require_doi=require_doi,
                        )
                    )
                except Exception as err:
                    seed_errors.append(f"openalex: {type(err).__name__}: {err}")
                    provider_errors.append({"provider": "openalex", "query": provider_seed.query, "error": f"{type(err).__name__}: {err}"})

        if "pubmed" in backends:
            for provider_seed in query_variants_for_backend(seed, args.dataset, "pubmed", args.query_variant_mode):
                provider_query_counts["pubmed"] += 1
                try:
                    seed_rows.extend(
                        search_pubmed(
                            client=pubmed_client,
                            email=ncbi_email,
                            api_key=ncbi_api_key,
                            seed=provider_seed,
                            max_results=args.max_results_per_seed,
                            require_doi=require_doi,
                        )
                    )
                except Exception as err:
                    seed_errors.append(f"pubmed: {type(err).__name__}: {err}")
                    provider_errors.append({"provider": "pubmed", "query": provider_seed.query, "error": f"{type(err).__name__}: {err}"})

        if "pmc" in backends:
            for provider_seed in query_variants_for_backend(seed, args.dataset, "pmc", args.query_variant_mode):
                provider_query_counts["pmc"] += 1
                try:
                    seed_rows.extend(
                        search_pmc(
                            client=pmc_client,
                            email=ncbi_email,
                            api_key=ncbi_api_key,
                            seed=provider_seed,
                            max_results=args.max_results_per_seed,
                            require_doi=require_doi,
                        )
                    )
                except Exception as err:
                    seed_errors.append(f"pmc: {type(err).__name__}: {err}")
                    provider_errors.append({"provider": "pmc", "query": provider_seed.query, "error": f"{type(err).__name__}: {err}"})

        if "crossref" in backends:
            for provider_seed in query_variants_for_backend(seed, args.dataset, "crossref", args.query_variant_mode):
                provider_query_counts["crossref"] += 1
                try:
                    seed_rows.extend(
                        search_crossref(
                            client=crossref_client,
                            email=crossref_email,
                            seed=provider_seed,
                            max_results=args.max_results_per_seed,
                            require_doi=require_doi,
                        )
                    )
                except Exception as err:
                    seed_errors.append(f"crossref: {type(err).__name__}: {err}")
                    provider_errors.append({"provider": "crossref", "query": provider_seed.query, "error": f"{type(err).__name__}: {err}"})

        all_rows.extend(seed_rows)
        per_seed.append(
            {
                "query": seed.query,
                "compound": seed.compound,
                "entity": seed.entity,
                "rows_retrieved": len(seed_rows),
                "errors": seed_errors,
            }
        )
        if args.progress:
            pct_done = seed_idx / max(1, seed_total) * 100.0
            print(
                f"PROGRESS: discovery seed {seed_idx}/{seed_total} ({pct_done:.1f}%) "
                f"rows_retrieved={len(seed_rows)} cumulative_raw_rows={len(all_rows)}",
                flush=True,
            )

    citation_chase_report = {
        "enabled": args.citation_chase != "off",
        "source": args.citation_chase,
        "directions": args.citation_chase_directions,
        "source_dois": 0,
        "raw_rows": 0,
        "errors": [],
    }
    if args.citation_chase != "off":
        source_rows = (
            read_benchmark_manifest_seed_rows(
                benchmark_manifest,
                args.dataset,
                max_rows=max(0, args.citation_chase_max_source_dois),
            )
            if args.citation_chase in {"benchmark", "known-study-set"}
            else merge_rows(all_rows)[: max(0, args.citation_chase_max_source_dois)]
        )
        directions = (
            ["references", "citations"]
            if args.citation_chase_directions == "both"
            else [args.citation_chase_directions]
        )
        source_seeds = rows_to_citation_source_seeds(source_rows, max_rows=max(0, args.citation_chase_max_source_dois))
        citation_chase_report["source_dois"] = len(source_seeds)
        for source_idx, (source_doi, source_seed) in enumerate(source_seeds, start=1):
            if args.progress:
                print(
                    f"PROGRESS: citation chase {source_idx}/{len(source_seeds)} doi={source_doi}",
                    flush=True,
                )
            for direction in directions:
                try:
                    rows = search_semantic_scholar_edges(
                        client=s2_client,
                        api_key=s2_api_key,
                        source_doi=source_doi,
                        seed=source_seed,
                        direction=direction,
                        max_results=max(0, args.citation_chase_max_results_per_doi),
                        require_doi=require_doi,
                    )
                    all_rows.extend(rows)
                    citation_chase_report["raw_rows"] += len(rows)
                except Exception as err:
                    error = {
                        "doi": source_doi,
                        "direction": direction,
                        "error": f"{type(err).__name__}: {err}",
                    }
                    citation_chase_report["errors"].append(error)
                    provider_errors.append({"provider": f"semantic_scholar_{direction}", "query": source_doi, "error": error["error"]})

    merged_all = merge_rows(all_rows)
    if args.disable_protected_retention:
        merged = merged_all[: args.max_results] if args.max_results > 0 else merged_all
        retention_report = {
            "enabled": False,
            "max_results": args.max_results,
            "protected_dois_configured": 0,
            "protected_dois_available": 0,
            "protected_dois_retained": 0,
            "protected_over_cap": 0,
            "dropped_rows": max(0, len(merged_all) - len(merged)),
        }
        protected_sources: Dict[str, List[dict]] = {}
    else:
        protected_sources = protected_sources_for_dataset(args.dataset, benchmark_manifest)
        merged, retention_report = apply_protected_retention(
            rows=merged_all,
            max_results=args.max_results,
            protected_sources=protected_sources,
        )

    enrich_unpaywall = (args.enrich_unpaywall or args.provider == "comprehensive") and not args.skip_unpaywall_enrichment
    unpaywall_errors: List[dict] = []
    if enrich_unpaywall:
        merged, unpaywall_errors = enrich_rows_unpaywall(
            client=unpaywall_client,
            email=unpaywall_email,
            rows=merged,
        )

    write_queue(queue_out, merged, args.dataset)
    provider_counts = Counter(normalize(row.get("provider", "")) for row in all_rows)
    merged_provider_counts = Counter(
        provider
        for row in merged
        for provider in row.get("providers", [])
        if normalize(provider)
    )

    generated_at = now_utc()
    run_id = f"{args.dataset}:{generated_at}"
    run_meta = {
        "run_id": run_id,
        "generated_at": generated_at,
        "dataset": args.dataset,
        "provider": args.provider,
        "backends": list(backends),
        "queue_out": str(queue_out),
        "report_out": str(report_out),
        "known_study_manifest": str(benchmark_manifest),
        "benchmark_manifest": str(benchmark_manifest),
        "settings": {
            "max_results_per_seed": args.max_results_per_seed,
            "max_results": args.max_results,
            "expand_seeds_from_config": args.expand_seeds_from_config,
            "auto_seeds_only": args.auto_seeds_only,
            "auto_template_mode": args.auto_template_mode,
            "auto_max_compounds": args.auto_max_compounds,
            "auto_max_entities": args.auto_max_entities,
            "auto_max_pairs": args.auto_max_pairs,
            "auto_max_seeds": args.auto_max_seeds,
            "balanced_seed_profile": args.balanced_seed_profile,
            "balanced_max_compounds": args.balanced_max_compounds,
            "balanced_max_entities": args.balanced_max_entities,
            "balanced_max_seeds": args.balanced_max_seeds,
            "query_variant_mode": args.query_variant_mode,
            "citation_chase": args.citation_chase,
            "citation_chase_directions": args.citation_chase_directions,
            "citation_chase_max_source_dois": args.citation_chase_max_source_dois,
            "citation_chase_max_results_per_doi": args.citation_chase_max_results_per_doi,
            "disable_protected_retention": args.disable_protected_retention,
        },
        "counts": {
            "seed_count": len(seeds),
            "raw_rows": len(all_rows),
            "merged_rows_before_retention": len(merged_all),
            "retained_rows": len(merged),
        },
    }
    if not args.disable_ledger:
        ledger = update_ledger(
            existing=load_ledger(ledger_out, args.dataset),
            dataset=args.dataset,
            run_id=run_id,
            run_meta=run_meta,
            all_rows=merged_all,
            retained_rows=merged,
            protected_sources=protected_sources,
        )
        write_ledger(ledger_out, ledger)

    report = {
        "generated_at": generated_at,
        "run_id": run_id,
        "dataset": args.dataset,
        "provider": args.provider,
        "backends": list(backends),
        "require_doi": require_doi,
        "settings": {
            "semantic_scholar_rps": s2_rps,
            "openalex_rps": oa_rps,
            "openalex_api_key_configured": bool(oa_api_key),
            "pubmed_rps": pubmed_rps,
            "pmc_rps": pmc_rps,
            "crossref_rps": crossref_rps,
            "unpaywall_rps": unpaywall_rps,
            "max_retries": max_retries,
            "max_results_per_seed": args.max_results_per_seed,
            "max_results": args.max_results,
            "expand_seeds_from_config": args.expand_seeds_from_config,
            "auto_seeds_only": args.auto_seeds_only,
            "auto_template_mode": args.auto_template_mode,
            "auto_max_compounds": args.auto_max_compounds,
            "auto_max_entities": args.auto_max_entities,
            "auto_max_pairs": args.auto_max_pairs,
            "auto_max_seeds": args.auto_max_seeds,
            "balanced_seed_profile": args.balanced_seed_profile,
            "balanced_max_compounds": args.balanced_max_compounds,
            "balanced_max_entities": args.balanced_max_entities,
            "balanced_max_seeds": args.balanced_max_seeds,
            "query_variant_mode": args.query_variant_mode,
            "citation_chase": args.citation_chase,
            "citation_chase_directions": args.citation_chase_directions,
            "citation_chase_max_source_dois": args.citation_chase_max_source_dois,
            "citation_chase_max_results_per_doi": args.citation_chase_max_results_per_doi,
            "enrich_unpaywall": enrich_unpaywall,
            "skip_unpaywall_enrichment": args.skip_unpaywall_enrichment,
            "unpaywall_email_configured": bool(usable_email(unpaywall_email)),
            "known_study_manifest": str(benchmark_manifest),
            "benchmark_manifest": str(benchmark_manifest),
            "ledger_out": "" if args.disable_ledger else str(ledger_out),
            "protected_retention_enabled": not args.disable_protected_retention,
        },
        "counts": {
            "seed_count": len(seeds),
            "seed_manual": seed_source_counts["manual"],
            "seed_default": seed_source_counts["default"],
            "seed_auto": seed_source_counts["auto"],
            "seed_balanced": seed_source_counts["balanced"],
            "seed_balanced_compound_gap": seed_source_counts["balanced_compound_gap"],
            "seed_balanced_entity_gap": seed_source_counts["balanced_entity_gap"],
            "seed_balanced_evidence": seed_source_counts["balanced_evidence"],
            "raw_rows": len(all_rows),
            "merged_rows_before_retention": len(merged_all),
            "merged_rows": len(merged),
            "provider_raw_rows": dict(provider_counts),
            "merged_provider_mentions": dict(merged_provider_counts),
            "provider_queries": dict(provider_query_counts),
            "provider_errors": len(provider_errors),
            "unpaywall_errors": len(unpaywall_errors),
        },
        "protected_retention": retention_report,
        "citation_chase": citation_chase_report,
        "queue_out": str(queue_out),
        "ledger_out": "" if args.disable_ledger else str(ledger_out),
        "per_seed": per_seed,
        "provider_errors": provider_errors,
        "unpaywall_errors": unpaywall_errors,
        "rows": merged,
    }

    report_out.parent.mkdir(parents=True, exist_ok=True)
    report_out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"Dataset: {args.dataset}")
    print(f"Provider: {args.provider}")
    print(f"Seeds: {len(seeds)}")
    print(
        "Seed sources: "
        f"manual={seed_source_counts['manual']} "
        f"default={seed_source_counts['default']} "
        f"auto={seed_source_counts['auto']} "
        f"balanced={seed_source_counts['balanced']} "
        f"balanced_compound_gap={seed_source_counts['balanced_compound_gap']} "
        f"balanced_entity_gap={seed_source_counts['balanced_entity_gap']} "
        f"balanced_evidence={seed_source_counts['balanced_evidence']}"
    )
    print(f"Raw rows: {len(all_rows)}")
    print(f"Merged rows: {len(merged)}")
    if provider_counts:
        print("Provider raw rows: " + ", ".join(f"{k}={v}" for k, v in sorted(provider_counts.items())))
    if provider_query_counts:
        print("Provider queries: " + ", ".join(f"{k}={v}" for k, v in sorted(provider_query_counts.items())))
    if citation_chase_report["enabled"]:
        print(
            "Citation chase: "
            f"source_dois={citation_chase_report['source_dois']} "
            f"raw_rows={citation_chase_report['raw_rows']} "
            f"errors={len(citation_chase_report['errors'])}"
        )
    print(f"Merged rows before retention: {len(merged_all)}")
    print(
        "Protected retention: "
        f"{'on' if retention_report.get('enabled') else 'off'} "
        f"retained={retention_report.get('protected_dois_retained', 0)}/"
        f"{retention_report.get('protected_dois_available', 0)} "
        f"over_cap={retention_report.get('protected_over_cap', 0)}"
    )
    if enrich_unpaywall:
        print(f"Unpaywall enrichment errors: {len(unpaywall_errors)}")
    print(f"Queue: {queue_out}")
    print(f"Report: {report_out}")
    if not args.disable_ledger:
        print(f"Ledger: {ledger_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
