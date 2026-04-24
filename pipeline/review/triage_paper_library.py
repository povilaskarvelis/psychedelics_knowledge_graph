#!/usr/bin/env python3
"""Rule-based paper triage for relevance and source-type suggestions."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import re
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Set, Tuple

ROOT = Path(__file__).resolve().parents[2]
DISORDER_CANON_PATH = ROOT / "schema" / "disorder_canonicalization.json"

DATASET_CONFIG = {
    "mechanistic": {
        "paper_db_json": ROOT / "data" / "processed" / "paper_library_mechanistic.json",
        "stubs_json": ROOT / "data" / "processed" / "mechanistic_claim_stubs.json",
        "stubs_csv": ROOT / "data" / "processed" / "mechanistic_claim_stubs.csv",
        "curated_json": ROOT / "data" / "curated" / "claims.json",
        "entity_key": "target",
        "allowlist_key": "allowed_targets",
    },
    "disorder": {
        "paper_db_json": ROOT / "data" / "processed" / "paper_library_disorder.json",
        "stubs_json": ROOT / "data" / "processed" / "disorder_claim_stubs.json",
        "stubs_csv": ROOT / "data" / "processed" / "disorder_claim_stubs.csv",
        "curated_json": ROOT / "data" / "curated" / "disorder_claims.json",
        "entity_key": "disorder",
        "allowlist_key": "allowed_disorders",
    },
}

META_ANALYSIS_KEYWORDS = {
    "meta analysis",
    "meta-analysis",
    "pooled analysis",
    "network meta analysis",
    "network meta-analysis",
}

REVIEW_KEYWORDS = {
    "systematic review",
    "narrative review",
    "scoping review",
    "umbrella review",
    "literature review",
    "review article",
    "rapid review",
    "review paper",
    "review of literature",
    "current state",
    "consensus",
    "viewpoint",
    "approaches to treatment",
    "role of",
    "regulatory perspectives",
}

PROTOCOL_KEYWORDS = {
    "study protocol",
    "trial protocol",
    "protocol for",
    "protocol:",
    "study design",
}

CONFERENCE_OR_POSTER_KEYWORDS = {
    "poster abstract",
    "poster abstracts",
    "meeting abstract",
    "meeting abstracts",
    "annual meeting",
    "scientific meeting",
    "conference abstract",
    "conference proceedings",
    "psychopharmacology congress",
    "supplement",
}

OTHER_NONCOUNTABLE_KEYWORDS = {
    "cost effectiveness",
    "cost-effectiveness",
    "cost utility",
    "cost-utility",
    "commentary",
    "editorial",
    "future directions",
    "highlight research directions",
    "is there a place for",
    "model based",
    "model-based",
    "medical malpractice risk",
    "physicians concerns",
    "physicians' concerns",
    "research directions",
    "we aim to explore this topic",
    "who will staff",
    "where do we go from here",
}

PRIMARY_KEYWORDS_DISORDER = {
    "randomized",
    "placebo",
    "double blind",
    "double-blind",
    "phase 2",
    "phase 3",
    "clinical trial",
    "open label",
    "open-label",
    "participants",
    "patients",
}

PRIMARY_HINT_KEYWORDS_DISORDER = {
    "case report",
    "case series",
    "single-case",
    "qualitative study",
    "phenomenological analysis",
    "real world",
    "real-world",
    "retrospective",
    "cohort",
    "pilot study",
    "pilot randomized controlled trial",
    "use patterns",
    "resource use",
    "expanded use",
    "single-arm",
}

PRIMARY_KEYWORDS_MECHANISTIC = {
    "binding",
    "affinity",
    "radioligand",
    "assay",
    "ic50",
    "ec50",
    "ki",
    "kd",
    "agonist",
    "antagonist",
    "receptor",
    "transporter",
    "in vitro",
    "in vivo",
}

COMPOUND_SYNONYMS = {
    "psilocybin": {"psilocybin", "psilocibin", "psilocin", "comp360"},
    "psilocin": {"psilocin", "4-ho-dmt", "4 hydroxy dmt"},
    "lsd": {"lsd", "lysergic acid diethylamide", "d-lysergic acid diethylamide"},
    "dmt": {"dmt", "n,n-dmt", "n n dmt", "dimethyltryptamine"},
    "5-meo-dmt": {"5-meo-dmt", "5 meo dmt", "5meodmt", "5-methoxy-dmt"},
    "ayahuasca": {"ayahuasca", "hoasca", "yage"},
    "mdma": {"mdma", "3,4-methylenedioxymethamphetamine", "ecstasy"},
    "mda": {"mda", "3,4-methylenedioxyamphetamine"},
    "ketamine": {"ketamine", "esketamine", "arketamine", "s-ketamine", "r-ketamine"},
    "s-ketamine": {"s-ketamine", "esketamine", "ketamine"},
    "r-ketamine": {"r-ketamine", "arketamine", "ketamine"},
    "ibogaine": {"ibogaine", "18-mc", "18 mc"},
    "noribogaine": {"noribogaine", "o-desmethylibogaine"},
    "salvinorin a": {"salvinorin a", "divinorin a"},
    "lsa": {"lsa", "ergine", "lysergic acid amide"},
    "doi": {"doi", "2,5-dimethoxy-4-iodoamphetamine"},
    "dob": {"dob", "2,5-dimethoxy-4-bromoamphetamine"},
    "dom": {"dom", "2,5-dimethoxy-4-methylamphetamine", "stp"},
    "25i-nbome": {"25i-nbome", "25i nbome"},
    "25b-nbome": {"25b-nbome", "25b nbome"},
    "25c-nbome": {"25c-nbome", "25c nbome"},
}

DISORDER_SYNONYMS = {
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

SOURCE_TYPE_ALLOWED = {"primary_study", "review", "meta_analysis", "registry", "other"}
PAPER_TYPE_ALLOWED = {
    "primary_results",
    "review",
    "protocol",
    "conference_or_poster_abstract",
    "other",
}


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


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


def normalize_text(raw: str) -> str:
    lowered = normalize(raw).lower()
    lowered = re.sub(r"[^a-z0-9]+", " ", lowered)
    return re.sub(r"\s+", " ", lowered).strip()


def explode_label_terms(label: str) -> Set[str]:
    terms: Set[str] = set()
    norm = normalize_text(label)
    if norm:
        terms.add(norm)

    raw = normalize(label)
    match = re.match(r"^(.*?)\s*\(([^)]+)\)\s*$", raw)
    if match:
        base = normalize_text(match.group(1))
        inside = normalize_text(match.group(2))
        if base:
            terms.add(base)
        if inside:
            terms.add(inside)
        if base and inside:
            terms.add(f"{base} {inside}")
    return {term for term in terms if term}


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
        elif current and line.startswith("    - "):
            item = stripped[2:].strip().strip('"').strip("'")
            out[current].setdefault("__list__", []).append(item)
    return out


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


def load_disorder_synonyms(path: Path = DISORDER_CANON_PATH) -> Dict[str, Set[str]]:
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


FILE_DISORDER_SYNONYMS = load_disorder_synonyms()


def load_json_array(path: Path) -> List[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, list):
        raise ValueError(f"Expected JSON array at {path}")
    return data


def context_identity(ctx: dict) -> Tuple[str, str]:
    return (
        normalize(ctx.get("compound", "")).lower(),
        normalize(ctx.get("entity", "")).lower(),
    )


def normalize_context(ctx: dict, source: str = "") -> dict:
    out = {
        "compound": normalize(ctx.get("compound", "")),
        "entity": normalize(ctx.get("entity", "")),
    }
    if normalize(ctx.get("compound_match", "")):
        out["compound_match"] = normalize(ctx.get("compound_match", ""))
    if normalize(ctx.get("entity_match", "")):
        out["entity_match"] = normalize(ctx.get("entity_match", ""))
    match_source = normalize(ctx.get("triage_match_source", "")) or source
    if match_source:
        out["triage_match_source"] = match_source
    return out


def dedupe_contexts(contexts: Iterable[dict]) -> List[dict]:
    out: List[dict] = []
    seen = set()
    for ctx in contexts:
        if not isinstance(ctx, dict):
            continue
        normalized = normalize_context(ctx)
        compound, entity = context_identity(normalized)
        if not compound or not entity:
            continue
        key = (
            compound,
            entity,
            normalize(normalized.get("triage_match_source", "")).lower(),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(normalized)
    return out


def merge_context_maps(*maps: Dict[str, List[dict]]) -> Dict[str, List[dict]]:
    merged: Dict[str, List[dict]] = {}
    for mapping in maps:
        for doi, contexts in mapping.items():
            if not doi:
                continue
            merged[doi] = dedupe_contexts(merged.get(doi, []) + contexts)
    return merged


def load_benchmark_contexts(path: Path, dataset: str, entity_key: str) -> Dict[str, List[dict]]:
    if not path.exists():
        return {}

    payload = json.loads(path.read_text(encoding="utf-8"))
    entries = payload.get("entries", []) if isinstance(payload, dict) else []
    if not isinstance(entries, list):
        return {}

    out: Dict[str, List[dict]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if normalize(entry.get("dataset", "")) != dataset:
            continue
        doi = normalize_doi(entry.get("doi", "")).lower()
        compound = normalize(entry.get("compound", ""))
        entity = normalize(entry.get(entity_key, ""))
        if not doi or not compound or not entity:
            continue
        out.setdefault(doi, []).append(
            {
                "compound": compound,
                "entity": entity,
                "triage_match_source": "protected_known_study",
            }
        )
    return {doi: dedupe_contexts(contexts) for doi, contexts in out.items()}


def load_curated_contexts(path: Path, entity_key: str) -> Dict[str, List[dict]]:
    out: Dict[str, List[dict]] = {}
    for row in load_json_array(path):
        doi = normalize_doi(row.get("study_doi", "")).lower()
        compound = normalize(row.get("compound", ""))
        entity = normalize(row.get(entity_key, ""))
        if not doi or not compound or not entity:
            continue
        out.setdefault(doi, []).append(
            {
                "compound": compound,
                "entity": entity,
                "triage_match_source": "protected_curated",
            }
        )
    return {doi: dedupe_contexts(contexts) for doi, contexts in out.items()}


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: List[dict]) -> None:
    fieldnames = sorted({k for row in rows for k in row.keys()}) if rows else []
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def expand_compound_terms(compound: str) -> Set[str]:
    key = normalize(compound).lower()
    terms = set(explode_label_terms(compound))
    if key in COMPOUND_SYNONYMS:
        for value in COMPOUND_SYNONYMS[key]:
            terms.update(explode_label_terms(value))
    return {t for t in terms if t}


def expand_entity_terms(dataset: str, entity: str) -> Set[str]:
    key = normalize(entity).lower()
    terms = set(explode_label_terms(entity))
    if dataset == "disorder":
        if key in FILE_DISORDER_SYNONYMS:
            for value in FILE_DISORDER_SYNONYMS[key]:
                terms.update(explode_label_terms(value))
        if key in DISORDER_SYNONYMS:
            for value in DISORDER_SYNONYMS[key]:
                terms.update(explode_label_terms(value))
    else:
        if key in TARGET_SYNONYMS:
            for value in TARGET_SYNONYMS[key]:
                terms.update(explode_label_terms(value))
    return {t for t in terms if t}


def contains_any(text_norm: str, terms: Iterable[str]) -> Tuple[bool, str]:
    padded = f" {text_norm} "
    tokens = set(text_norm.split())
    for term in terms:
        token = normalize_text(term)
        if not token:
            continue
        if " " in token:
            if f" {token} " in padded:
                return True, term
            continue
        if token in tokens:
            return True, term
    return False, ""


def matched_allowed_terms(text_norm: str, labels: Iterable[str], expander) -> List[dict]:
    matches: List[dict] = []
    seen = set()
    for label in labels:
        normalized_label = normalize(label)
        if not normalized_label:
            continue
        hit, term = contains_any(text_norm, expander(normalized_label))
        key = normalized_label.lower()
        if hit and key not in seen:
            seen.add(key)
            matches.append({"label": normalized_label, "match": normalize(term)})
    return matches


def detect_source_type(text_norm: str, dataset: str) -> Tuple[str, List[str]]:
    reasons: List[str] = []
    if any(normalize_text(kw) in text_norm for kw in META_ANALYSIS_KEYWORDS):
        reasons.append("contains meta-analysis keyword")
        return "meta_analysis", reasons
    if any(normalize_text(kw) in text_norm for kw in REVIEW_KEYWORDS):
        reasons.append("contains review keyword")
        return "review", reasons
    if any(normalize_text(kw) in text_norm for kw in OTHER_NONCOUNTABLE_KEYWORDS):
        reasons.append("contains non-countable analysis/editorial keyword")
        return "other", reasons
    if dataset == "disorder" and any(normalize_text(kw) in text_norm for kw in PRIMARY_HINT_KEYWORDS_DISORDER):
        reasons.append("contains primary-study title hint")
        return "primary_study", reasons

    primary_keywords = PRIMARY_KEYWORDS_DISORDER if dataset == "disorder" else PRIMARY_KEYWORDS_MECHANISTIC
    hits = [kw for kw in primary_keywords if normalize_text(kw) in text_norm]
    if len(hits) >= 2:
        reasons.append(f"contains primary-study signals ({', '.join(sorted(hits)[:4])})")
        return "primary_study", reasons

    reasons.append("no strong source-type signal")
    return "other", reasons


def detect_paper_type(text_norm: str, dataset: str) -> Tuple[str, List[str]]:
    reasons: List[str] = []
    if any(normalize_text(kw) in text_norm for kw in CONFERENCE_OR_POSTER_KEYWORDS):
        reasons.append("contains conference/poster keyword")
        return "conference_or_poster_abstract", reasons
    if any(normalize_text(kw) in text_norm for kw in PROTOCOL_KEYWORDS):
        reasons.append("contains protocol keyword")
        return "protocol", reasons
    if any(normalize_text(kw) in text_norm for kw in META_ANALYSIS_KEYWORDS | REVIEW_KEYWORDS):
        reasons.append("contains review keyword")
        return "review", reasons
    if any(normalize_text(kw) in text_norm for kw in OTHER_NONCOUNTABLE_KEYWORDS):
        reasons.append("contains non-countable analysis/editorial keyword")
        return "other", reasons
    if dataset == "disorder" and any(normalize_text(kw) in text_norm for kw in PRIMARY_HINT_KEYWORDS_DISORDER):
        reasons.append("contains primary-results title hint")
        return "primary_results", reasons

    primary_keywords = PRIMARY_KEYWORDS_DISORDER if dataset == "disorder" else PRIMARY_KEYWORDS_MECHANISTIC
    hits = [kw for kw in primary_keywords if normalize_text(kw) in text_norm]
    if len(hits) >= 2:
        reasons.append(f"contains primary-results signals ({', '.join(sorted(hits)[:4])})")
        return "primary_results", reasons

    reasons.append("no strong paper-type signal")
    return "other", reasons


def relevance_score_for_row(
    dataset: str,
    text_norm: str,
    contexts: List[dict],
    allowlists: Dict[str, List[str]],
    source_type: str,
    metadata_lookup_error: str,
    protected_contexts: List[dict] | None = None,
    synthesize_global_contexts: bool = True,
    max_synthesized_contexts: int = 12,
) -> Tuple[int, List[str], List[dict], dict]:
    score = 0
    reasons: List[str] = []
    context_compound_hit = False
    context_entity_hit = False
    context_pair_hit = False
    matched_contexts: List[dict] = []
    rescue_reasons: List[str] = []
    synthesized_context_count = 0
    protected_context_count = 0

    protected_contexts = protected_contexts or []

    for ctx in contexts:
        if not isinstance(ctx, dict):
            continue
        compound = normalize(ctx.get("compound", ""))
        entity = normalize(ctx.get("entity", ""))
        compound_terms = expand_compound_terms(compound) if compound else set()
        entity_terms = expand_entity_terms(dataset, entity) if entity else set()
        c_hit, c_term = contains_any(text_norm, compound_terms)
        e_hit, e_term = contains_any(text_norm, entity_terms)
        if c_hit:
            context_compound_hit = True
            reasons.append(f"context compound match ({compound or c_term})")
        if e_hit:
            context_entity_hit = True
            reasons.append(f"context entity match ({entity or e_term})")
        if c_hit and e_hit:
            context_pair_hit = True
            matched_contexts.append(
                {
                    "compound": compound,
                    "entity": entity,
                    "compound_match": c_term,
                    "entity_match": e_term,
                    "triage_match_source": "discovery_context",
                }
            )

    if context_compound_hit:
        score += 2
    if context_entity_hit:
        score += 2
    if context_pair_hit:
        score += 2
        reasons.append("compound+entity pair matched")

    compound_matches = matched_allowed_terms(
        text_norm,
        allowlists.get("allowed_compounds", []),
        expand_compound_terms,
    )
    global_compound_hit = bool(compound_matches)
    global_compound_term = compound_matches[0]["match"] if compound_matches else ""
    if global_compound_hit and not context_compound_hit:
        score += 1
        reasons.append(f"allowed compound mention ({global_compound_term})")

    key = "allowed_disorders" if dataset == "disorder" else "allowed_targets"
    entity_matches = matched_allowed_terms(
        text_norm,
        allowlists.get(key, []),
        lambda entity: expand_entity_terms(dataset, entity),
    )
    global_entity_hit = bool(entity_matches)
    global_entity_term = entity_matches[0]["match"] if entity_matches else ""
    if global_entity_hit and not context_entity_hit:
        score += 1
        reasons.append(f"allowed entity mention ({global_entity_term})")

    if synthesize_global_contexts and not context_pair_hit and compound_matches and entity_matches:
        max_contexts = max(0, max_synthesized_contexts)
        for compound_match in compound_matches:
            for entity_match in entity_matches:
                if max_contexts and synthesized_context_count >= max_contexts:
                    break
                matched_contexts.append(
                    {
                        "compound": compound_match["label"],
                        "entity": entity_match["label"],
                        "compound_match": compound_match["match"],
                        "entity_match": entity_match["match"],
                        "triage_match_source": "synthesized_text",
                    }
                )
                synthesized_context_count += 1
            if max_contexts and synthesized_context_count >= max_contexts:
                break
        if synthesized_context_count:
            score += 2
            context_pair_hit = True
            rescue_reasons.append("synthesized compound+entity context from title/abstract")
            reasons.append("compound+entity pair synthesized from title/abstract")

    for ctx in protected_contexts:
        normalized = normalize_context(ctx)
        compound = normalize(normalized.get("compound", ""))
        entity = normalize(normalized.get("entity", ""))
        if not compound or not entity:
            continue
        normalized.setdefault("triage_match_source", "protected")
        matched_contexts.append(normalized)
        protected_context_count += 1
    if protected_context_count:
        score = max(score, 5)
        rescue_reasons.append("protected known-study/curated context retained")
        reasons.append("protected known-study/curated DOI retained")

    if dataset == "disorder":
        keyword_hits = [kw for kw in PRIMARY_KEYWORDS_DISORDER if normalize_text(kw) in text_norm]
    else:
        keyword_hits = [kw for kw in PRIMARY_KEYWORDS_MECHANISTIC if normalize_text(kw) in text_norm]
    if keyword_hits:
        score += 1
        reasons.append("contains study-method keywords")

    if source_type in {"review", "meta_analysis"} and not (context_compound_hit or context_entity_hit):
        score -= 1
        reasons.append("review/meta-analysis without domain match")

    if normalize(metadata_lookup_error):
        score -= 1
        reasons.append("metadata lookup failed")

    if not text_norm:
        score -= 2
        reasons.append("missing title/abstract text")

    audit = {
        "context_pair_matched": context_pair_hit,
        "synthesized_context_count": synthesized_context_count,
        "protected_context_count": protected_context_count,
        "needs_metadata_or_manual_screen": bool(normalize(metadata_lookup_error) or not text_norm),
        "triage_rescue_reasons": rescue_reasons,
    }
    return score, reasons, dedupe_contexts(matched_contexts), audit


def relevance_label(score: int) -> str:
    if score >= 5:
        return "likely_relevant"
    if score >= 3:
        return "possible_relevant"
    return "likely_irrelevant"


def screening_status_for_row(relevance: str, contexts: List[dict], audit: dict) -> str:
    if audit.get("protected_context_count", 0):
        return "included_protected"
    if audit.get("synthesized_context_count", 0):
        return "included_synthesized_context"
    if contexts:
        return "included_context_match"
    if relevance in {"likely_relevant", "possible_relevant"}:
        return "needs_context_review"
    if audit.get("needs_metadata_or_manual_screen"):
        return "needs_metadata_or_manual_screen"
    return "excluded_low_signal"


def flatten_triage_row(row: dict) -> dict:
    out = dict(row)
    for key in ("source_type_reasons", "paper_type_reasons", "relevance_reasons", "triage_rescue_reasons"):
        value = out.get(key, [])
        out[key] = " | ".join(value) if isinstance(value, list) else normalize(value)
    for key in ("contexts", "contexts_all"):
        contexts = out.get(key, [])
        if isinstance(contexts, list):
            labels = []
            for ctx in contexts:
                if not isinstance(ctx, dict):
                    continue
                compound = normalize(ctx.get("compound", ""))
                entity = normalize(ctx.get("entity", ""))
                if compound or entity:
                    labels.append(f"{compound}->{entity}".strip("->"))
            out[key] = " | ".join(labels)
        else:
            out[key] = normalize(contexts)
    return out


def write_stub_csv(path: Path, rows: List[dict]) -> None:
    fieldnames = sorted({k for row in rows for k in row.keys()}) if rows else []
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def parse_csv_set(raw: str) -> Set[str]:
    return {normalize(item) for item in raw.split(",") if normalize(item)}


def write_filtered_queue(path: Path, rows: List[dict], relevance_set: Set[str]) -> Dict[str, int]:
    path.parent.mkdir(parents=True, exist_ok=True)
    seen = set()
    written = 0
    skipped_no_context = 0
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(f"# triage-filtered queue generated at {now_utc()}\n")
        handle.write("# doi,compound,target_or_disorder,optional_study_title,optional_study_year,optional_authors\n")
        writer = csv.writer(handle)

        for row in rows:
            relevance = normalize(row.get("relevance_suggested", ""))
            if relevance_set and relevance not in relevance_set:
                continue

            doi = normalize_doi(row.get("study_doi", ""))
            title = normalize(row.get("study_title", ""))
            year = normalize(row.get("study_year", ""))
            contexts = row.get("contexts", [])
            if not isinstance(contexts, list) or not contexts:
                skipped_no_context += 1
                continue

            wrote_for_row = False
            for ctx in contexts:
                if not isinstance(ctx, dict):
                    continue
                compound = normalize(ctx.get("compound", ""))
                entity = normalize(ctx.get("entity", ""))
                if not compound or not entity:
                    continue
                key = (doi, compound, entity, title, year)
                if key in seen:
                    continue
                seen.add(key)
                writer.writerow([doi, compound, entity, title, year, ""])
                written += 1
                wrote_for_row = True

            if not wrote_for_row:
                skipped_no_context += 1

    return {
        "written": written,
        "skipped_no_context": skipped_no_context,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Triage paper library for relevance/source type")
    parser.add_argument("--dataset", choices=["mechanistic", "disorder"], required=True)
    parser.add_argument("--config", default=str(ROOT / "pipeline" / "config.example.yaml"))
    parser.add_argument("--paper-db-json", default="", help="Paper library JSON path")
    parser.add_argument("--report-json", default="", help="Triage report JSON path")
    parser.add_argument("--report-csv", default="", help="Flat triage CSV path")
    parser.add_argument(
        "--benchmark-manifest",
        "--known-study-manifest",
        dest="benchmark_manifest",
        default=str(ROOT / "data" / "raw" / "benchmark_manifest.json"),
        help=(
            "Structured known relevant study set used for protected triage rescue. "
            "The older flag name is retained for compatibility."
        ),
    )
    parser.add_argument("--curated-json", default="", help="Curated claims JSON used for protected triage rescue")
    parser.add_argument(
        "--no-protected-rescue",
        action="store_true",
        help="Do not force known-study/curated contexts into the triage queue",
    )
    parser.add_argument(
        "--no-synthesize-contexts",
        action="store_true",
        help="Do not synthesize text-supported compound/entity contexts when discovery contexts are stale",
    )
    parser.add_argument(
        "--max-synthesized-contexts-per-paper",
        type=int,
        default=12,
        help="Maximum text-synthesized compound/entity contexts to add per paper (0 = unlimited)",
    )
    parser.add_argument(
        "--apply-to-stubs",
        action="store_true",
        help="Apply source type/relevance suggestions to claim stubs by DOI",
    )
    parser.add_argument("--stubs-json", default="", help="Override stubs JSON path")
    parser.add_argument("--stubs-csv", default="", help="Override stubs CSV path")
    parser.add_argument(
        "--apply-statuses",
        default="pending_curation",
        help="Comma-separated stub statuses eligible for auto-updates",
    )
    parser.add_argument(
        "--irrelevant-status",
        default="excluded_not_relevant",
        help="stub_status to assign when triage marks likely_irrelevant",
    )
    parser.add_argument("--no-set-source-type", action="store_true", help="Do not update source_type on stubs")
    parser.add_argument("--queue-out", default="", help="Optional triage-filtered DOI queue output path")
    parser.add_argument(
        "--queue-relevance",
        default="likely_relevant,possible_relevant",
        help="Comma-separated relevance labels to include in queue-out",
    )
    args = parser.parse_args()

    cfg = DATASET_CONFIG[args.dataset]
    paper_db_json = Path(args.paper_db_json).resolve() if args.paper_db_json else cfg["paper_db_json"]
    report_json = (
        Path(args.report_json).resolve()
        if args.report_json
        else ROOT / "data" / "processed" / f"triage_report_{args.dataset}.json"
    )
    report_csv = (
        Path(args.report_csv).resolve()
        if args.report_csv
        else ROOT / "data" / "processed" / f"triage_report_{args.dataset}.csv"
    )
    queue_out = (
        Path(args.queue_out).resolve()
        if args.queue_out
        else ROOT / "data" / "raw" / f"doi_queue.{args.dataset}.triage_relevant.txt"
    )
    stubs_json = Path(args.stubs_json).resolve() if args.stubs_json else cfg["stubs_json"]
    stubs_csv = Path(args.stubs_csv).resolve() if args.stubs_csv else cfg["stubs_csv"]
    curated_json = Path(args.curated_json).resolve() if args.curated_json else cfg["curated_json"]
    benchmark_manifest = Path(args.benchmark_manifest).resolve()

    if not paper_db_json.exists():
        raise SystemExit(f"Paper library JSON not found: {paper_db_json}")

    should_set_source_type = not args.no_set_source_type
    apply_statuses = {normalize(v) for v in args.apply_statuses.split(",") if normalize(v)}
    allowlists = parse_allowlists(Path(args.config).resolve())
    papers = load_json_array(paper_db_json)
    protected_contexts_by_doi: Dict[str, List[dict]] = {}
    if not args.no_protected_rescue:
        protected_contexts_by_doi = merge_context_maps(
            load_benchmark_contexts(benchmark_manifest, args.dataset, cfg["entity_key"]),
            load_curated_contexts(curated_json, cfg["entity_key"]),
        )

    triage_rows: List[dict] = []
    counts = {
        "likely_relevant": 0,
        "possible_relevant": 0,
        "likely_irrelevant": 0,
        "source_primary_study": 0,
        "source_review": 0,
        "source_meta_analysis": 0,
        "source_other": 0,
        "paper_primary_results": 0,
        "paper_review": 0,
        "paper_protocol": 0,
        "paper_conference_or_poster_abstract": 0,
        "paper_other": 0,
        "screening_included_context_match": 0,
        "screening_included_synthesized_context": 0,
        "screening_included_protected": 0,
        "screening_needs_context_review": 0,
        "screening_needs_metadata_or_manual_screen": 0,
        "screening_excluded_low_signal": 0,
        "rescued_by_protected_context": 0,
        "rescued_by_synthesized_context": 0,
        "needs_metadata_or_manual_screen": 0,
    }

    for paper in papers:
        doi = normalize_doi(paper.get("study_doi", ""))
        title = normalize(paper.get("study_title", ""))
        abstract = normalize(paper.get("abstract", ""))
        text_norm = normalize_text(f"{title} {abstract}")
        source_type, source_type_reasons = detect_source_type(text_norm, args.dataset)
        paper_type, paper_type_reasons = detect_paper_type(text_norm, args.dataset)
        score, relevance_reasons, matched_contexts, triage_audit = relevance_score_for_row(
            dataset=args.dataset,
            text_norm=text_norm,
            contexts=paper.get("contexts", []) if isinstance(paper.get("contexts", []), list) else [],
            allowlists=allowlists,
            source_type=source_type,
            metadata_lookup_error=normalize(paper.get("metadata_lookup_error", "")),
            protected_contexts=protected_contexts_by_doi.get(doi.lower(), []),
            synthesize_global_contexts=not args.no_synthesize_contexts,
            max_synthesized_contexts=max(0, args.max_synthesized_contexts_per_paper),
        )
        relevance = relevance_label(score)
        screening_status = screening_status_for_row(relevance, matched_contexts, triage_audit)

        counts[relevance] += 1
        counts[f"source_{source_type}" if f"source_{source_type}" in counts else "source_other"] += 1
        counts[f"paper_{paper_type}" if f"paper_{paper_type}" in counts else "paper_other"] += 1
        counts[f"screening_{screening_status}"] += 1
        if triage_audit.get("protected_context_count", 0):
            counts["rescued_by_protected_context"] += 1
        if triage_audit.get("synthesized_context_count", 0):
            counts["rescued_by_synthesized_context"] += 1
        if triage_audit.get("needs_metadata_or_manual_screen"):
            counts["needs_metadata_or_manual_screen"] += 1

        triage_rows.append(
            {
                "study_doi": doi,
                "study_title": title,
                "study_year": normalize(paper.get("study_year", "")),
                "library_status": normalize(paper.get("library_status", "")),
                "source_type_suggested": source_type,
                "source_type_reasons": source_type_reasons,
                "paper_type_suggested": paper_type,
                "paper_type_reasons": paper_type_reasons,
                "relevance_suggested": relevance,
                "relevance_score": score,
                "relevance_reasons": relevance_reasons,
                "screening_status": screening_status,
                "triage_rescue_reasons": triage_audit.get("triage_rescue_reasons", []),
                "synthesized_context_count": triage_audit.get("synthesized_context_count", 0),
                "protected_context_count": triage_audit.get("protected_context_count", 0),
                "needs_metadata_or_manual_screen": triage_audit.get("needs_metadata_or_manual_screen", False),
                "contexts": matched_contexts,
                "contexts_all": paper.get("contexts", []),
                "matched_context_count": len(matched_contexts),
                "pdf_local_path": normalize(paper.get("pdf_local_path", "")),
                "action_reason": normalize(paper.get("action_reason", "")),
            }
        )

    triage_by_doi = {normalize_doi(row["study_doi"]).lower(): row for row in triage_rows if normalize_doi(row["study_doi"])}
    entity_key = cfg["entity_key"]
    triage_by_context: Dict[Tuple[str, str, str], dict] = {}
    for row in triage_rows:
        doi = normalize_doi(row.get("study_doi", "")).lower()
        if not doi:
            continue
        contexts = row.get("contexts", [])
        if not isinstance(contexts, list):
            continue
        for ctx in contexts:
            if not isinstance(ctx, dict):
                continue
            compound = normalize(ctx.get("compound", "")).lower()
            entity = normalize(ctx.get("entity", "")).lower()
            if not compound or not entity:
                continue
            triage_by_context[(doi, compound, entity)] = row

    stub_updates = {
        "considered": 0,
        "updated": 0,
        "status_updates": 0,
        "source_type_updates": 0,
        "paper_type_updates": 0,
        "missing_triage_match": 0,
    }

    stub_update_rows = []
    if args.apply_to_stubs:
        if not stubs_json.exists():
            raise SystemExit(f"Stub JSON not found for apply mode: {stubs_json}")
        stubs = load_json_array(stubs_json)
        updated_stubs = []
        for idx, stub in enumerate(stubs, start=1):
            status = normalize(stub.get("stub_status", ""))
            if apply_statuses and status not in apply_statuses:
                updated_stubs.append(stub)
                continue

            stub_updates["considered"] += 1
            doi = normalize_doi(stub.get("study_doi", "")).lower()
            compound = normalize(stub.get("compound", "")).lower()
            entity = normalize(stub.get(entity_key, "")).lower()
            triage = None
            if doi and compound and entity:
                triage = triage_by_context.get((doi, compound, entity))
            elif doi and (not compound or not entity):
                triage = triage_by_doi.get(doi)
            if not triage:
                stub_updates["missing_triage_match"] += 1
                updated_stubs.append(stub)
                continue

            new_row = dict(stub)
            changed_fields: List[str] = []

            suggested_source_type = normalize(triage.get("source_type_suggested", ""))
            if (
                should_set_source_type
                and suggested_source_type in SOURCE_TYPE_ALLOWED
                and normalize(new_row.get("source_type", "")) != suggested_source_type
            ):
                new_row["source_type"] = suggested_source_type
                changed_fields.append("source_type")
                stub_updates["source_type_updates"] += 1

            suggested_paper_type = normalize(triage.get("paper_type_suggested", ""))
            if (
                suggested_paper_type in PAPER_TYPE_ALLOWED
                and normalize(new_row.get("paper_type", "")) != suggested_paper_type
            ):
                new_row["paper_type"] = suggested_paper_type
                changed_fields.append("paper_type")
                stub_updates["paper_type_updates"] += 1

            suggested_relevance = normalize(triage.get("relevance_suggested", ""))
            if suggested_relevance == "likely_irrelevant":
                if normalize(new_row.get("stub_status", "")) != args.irrelevant_status:
                    new_row["stub_status"] = args.irrelevant_status
                    changed_fields.append("stub_status")
                    stub_updates["status_updates"] += 1

            # Non-schema fields used for triage traceability in review files.
            new_row["triage_relevance"] = suggested_relevance
            new_row["triage_relevance_score"] = triage.get("relevance_score", "")
            new_row["triage_source_type_suggested"] = suggested_source_type
            new_row["triage_paper_type_suggested"] = suggested_paper_type
            new_row["triage_checked_at_utc"] = now_utc()
            for key in (
                "triage_relevance",
                "triage_relevance_score",
                "triage_source_type_suggested",
                "triage_paper_type_suggested",
                "triage_checked_at_utc",
            ):
                if key not in changed_fields:
                    changed_fields.append(key)

            if changed_fields:
                stub_updates["updated"] += 1
            stub_update_rows.append(
                {
                    "stub_index": idx,
                    "study_doi": normalize(stub.get("study_doi", "")),
                    "status_before": status,
                    "status_after": normalize(new_row.get("stub_status", "")),
                    "source_type_before": normalize(stub.get("source_type", "")),
                    "source_type_after": normalize(new_row.get("source_type", "")),
                    "paper_type_before": normalize(stub.get("paper_type", "")),
                    "paper_type_after": normalize(new_row.get("paper_type", "")),
                    "changed_fields": changed_fields,
                }
            )
            updated_stubs.append(new_row)

        write_json(stubs_json, updated_stubs)
        write_stub_csv(stubs_csv, updated_stubs)

    triage_rows_sorted = sorted(
        triage_rows,
        key=lambda r: (normalize(r.get("relevance_suggested", "")), -int(r.get("relevance_score", 0)), normalize(r.get("study_doi", ""))),
    )
    queue_relevance = parse_csv_set(args.queue_relevance)
    queue_stats = write_filtered_queue(
        path=queue_out,
        rows=triage_rows_sorted,
        relevance_set=queue_relevance,
    )
    queue_rows_written = queue_stats["written"]
    flat_rows = [flatten_triage_row(row) for row in triage_rows_sorted]
    write_csv(report_csv, flat_rows)

    report = {
        "generated_at": now_utc(),
        "dataset": args.dataset,
        "paper_db_json": str(paper_db_json),
        "report_csv": str(report_csv),
        "queue_out": str(queue_out),
        "queue_relevance": sorted(queue_relevance),
        "queue_rows_written": queue_rows_written,
        "queue_rows_skipped_no_context": queue_stats["skipped_no_context"],
        "known_study_manifest": str(benchmark_manifest),
        "benchmark_manifest": str(benchmark_manifest),
        "curated_json": str(curated_json),
        "protected_rescue_enabled": not args.no_protected_rescue,
        "synthesize_contexts_enabled": not args.no_synthesize_contexts,
        "max_synthesized_contexts_per_paper": max(0, args.max_synthesized_contexts_per_paper),
        "protected_doi_count": len(protected_contexts_by_doi),
        "apply_to_stubs": args.apply_to_stubs,
        "apply_statuses": sorted(apply_statuses),
        "irrelevant_status": args.irrelevant_status,
        "counts": {
            "papers_total": len(triage_rows),
            **counts,
        },
        "stub_updates": stub_updates,
        "rows": triage_rows_sorted,
        "stub_update_rows": stub_update_rows,
    }
    write_json(report_json, report)

    print(f"Dataset: {args.dataset}")
    print(f"Papers triaged: {len(triage_rows)}")
    print(
        "Relevance counts: "
        f"likely_relevant={counts['likely_relevant']} "
        f"possible_relevant={counts['possible_relevant']} "
        f"likely_irrelevant={counts['likely_irrelevant']}"
    )
    print(
        "Source-type suggestions: "
        f"primary={counts['source_primary_study']} "
        f"review={counts['source_review']} "
        f"meta_analysis={counts['source_meta_analysis']} "
        f"other={counts['source_other']}"
    )
    print(
        "Paper-type suggestions: "
        f"primary_results={counts['paper_primary_results']} "
        f"review={counts['paper_review']} "
        f"protocol={counts['paper_protocol']} "
        f"conference_or_poster_abstract={counts['paper_conference_or_poster_abstract']} "
        f"other={counts['paper_other']}"
    )
    print(
        "Screening statuses: "
        f"context_match={counts['screening_included_context_match']} "
        f"synthesized_context={counts['screening_included_synthesized_context']} "
        f"protected={counts['screening_included_protected']} "
        f"needs_context_review={counts['screening_needs_context_review']} "
        f"needs_metadata_or_manual={counts['screening_needs_metadata_or_manual_screen']} "
        f"excluded_low_signal={counts['screening_excluded_low_signal']}"
    )
    print(
        "Recall-safety rescues: "
        f"protected={counts['rescued_by_protected_context']} "
        f"synthesized={counts['rescued_by_synthesized_context']} "
        f"metadata_or_manual_screen={counts['needs_metadata_or_manual_screen']}"
    )
    if args.apply_to_stubs:
        print(
            "Stub updates: "
            f"considered={stub_updates['considered']} "
            f"updated={stub_updates['updated']} "
            f"status_updates={stub_updates['status_updates']} "
            f"source_type_updates={stub_updates['source_type_updates']} "
            f"paper_type_updates={stub_updates['paper_type_updates']} "
            f"missing_triage_match={stub_updates['missing_triage_match']}"
        )
        print(f"Stubs JSON: {stubs_json}")
        print(f"Stubs CSV: {stubs_csv}")
    print(f"Report JSON: {report_json}")
    print(f"Report CSV: {report_csv}")
    print(f"Filtered queue: {queue_out}")
    print(f"Filtered queue rows: {queue_rows_written}")
    print(f"Filtered queue skipped (no matched context): {queue_stats['skipped_no_context']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
