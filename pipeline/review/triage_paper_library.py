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
        "entity_key": "target",
        "allowlist_key": "allowed_targets",
    },
    "disorder": {
        "paper_db_json": ROOT / "data" / "processed" / "paper_library_disorder.json",
        "stubs_json": ROOT / "data" / "processed" / "disorder_claim_stubs.json",
        "stubs_csv": ROOT / "data" / "processed" / "disorder_claim_stubs.csv",
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


def detect_source_type(text_norm: str, dataset: str) -> Tuple[str, List[str]]:
    reasons: List[str] = []
    if any(normalize_text(kw) in text_norm for kw in META_ANALYSIS_KEYWORDS):
        reasons.append("contains meta-analysis keyword")
        return "meta_analysis", reasons
    if any(normalize_text(kw) in text_norm for kw in REVIEW_KEYWORDS):
        reasons.append("contains review keyword")
        return "review", reasons

    primary_keywords = PRIMARY_KEYWORDS_DISORDER if dataset == "disorder" else PRIMARY_KEYWORDS_MECHANISTIC
    hits = [kw for kw in primary_keywords if normalize_text(kw) in text_norm]
    if len(hits) >= 2:
        reasons.append(f"contains primary-study signals ({', '.join(sorted(hits)[:4])})")
        return "primary_study", reasons

    reasons.append("no strong source-type signal")
    return "other", reasons


def relevance_score_for_row(
    dataset: str,
    text_norm: str,
    contexts: List[dict],
    allowlists: Dict[str, List[str]],
    source_type: str,
    metadata_lookup_error: str,
) -> Tuple[int, List[str], List[dict]]:
    score = 0
    reasons: List[str] = []
    context_compound_hit = False
    context_entity_hit = False
    context_pair_hit = False
    matched_contexts: List[dict] = []

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
                }
            )

    if context_compound_hit:
        score += 2
    if context_entity_hit:
        score += 2
    if context_pair_hit:
        score += 2
        reasons.append("compound+entity pair matched")

    compound_terms_global = set()
    for compound in allowlists.get("allowed_compounds", []):
        compound_terms_global.update(expand_compound_terms(compound))
    global_compound_hit, global_compound_term = contains_any(text_norm, compound_terms_global)
    if global_compound_hit and not context_compound_hit:
        score += 1
        reasons.append(f"allowed compound mention ({global_compound_term})")

    entity_terms_global = set()
    key = "allowed_disorders" if dataset == "disorder" else "allowed_targets"
    for entity in allowlists.get(key, []):
        entity_terms_global.update(expand_entity_terms(dataset, entity))
    global_entity_hit, global_entity_term = contains_any(text_norm, entity_terms_global)
    if global_entity_hit and not context_entity_hit:
        score += 1
        reasons.append(f"allowed entity mention ({global_entity_term})")

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

    deduped_contexts = []
    seen_contexts = set()
    for ctx in matched_contexts:
        key = (normalize(ctx.get("compound", "")).lower(), normalize(ctx.get("entity", "")).lower())
        if key in seen_contexts:
            continue
        seen_contexts.add(key)
        deduped_contexts.append(
            {
                "compound": normalize(ctx.get("compound", "")),
                "entity": normalize(ctx.get("entity", "")),
                "compound_match": normalize(ctx.get("compound_match", "")),
                "entity_match": normalize(ctx.get("entity_match", "")),
            }
        )

    return score, reasons, deduped_contexts


def relevance_label(score: int) -> str:
    if score >= 5:
        return "likely_relevant"
    if score >= 3:
        return "possible_relevant"
    return "likely_irrelevant"


def flatten_triage_row(row: dict) -> dict:
    out = dict(row)
    for key in ("source_type_reasons", "relevance_reasons"):
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

    if not paper_db_json.exists():
        raise SystemExit(f"Paper library JSON not found: {paper_db_json}")

    should_set_source_type = not args.no_set_source_type
    apply_statuses = {normalize(v) for v in args.apply_statuses.split(",") if normalize(v)}
    allowlists = parse_allowlists(Path(args.config).resolve())
    papers = load_json_array(paper_db_json)

    triage_rows: List[dict] = []
    counts = {
        "likely_relevant": 0,
        "possible_relevant": 0,
        "likely_irrelevant": 0,
        "source_primary_study": 0,
        "source_review": 0,
        "source_meta_analysis": 0,
        "source_other": 0,
    }

    for paper in papers:
        title = normalize(paper.get("study_title", ""))
        abstract = normalize(paper.get("abstract", ""))
        text_norm = normalize_text(f"{title} {abstract}")
        source_type, source_type_reasons = detect_source_type(text_norm, args.dataset)
        score, relevance_reasons, matched_contexts = relevance_score_for_row(
            dataset=args.dataset,
            text_norm=text_norm,
            contexts=paper.get("contexts", []) if isinstance(paper.get("contexts", []), list) else [],
            allowlists=allowlists,
            source_type=source_type,
            metadata_lookup_error=normalize(paper.get("metadata_lookup_error", "")),
        )
        relevance = relevance_label(score)

        counts[relevance] += 1
        counts[f"source_{source_type}" if f"source_{source_type}" in counts else "source_other"] += 1

        triage_rows.append(
            {
                "study_doi": normalize_doi(paper.get("study_doi", "")),
                "study_title": title,
                "study_year": normalize(paper.get("study_year", "")),
                "library_status": normalize(paper.get("library_status", "")),
                "source_type_suggested": source_type,
                "source_type_reasons": source_type_reasons,
                "relevance_suggested": relevance,
                "relevance_score": score,
                "relevance_reasons": relevance_reasons,
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
            new_row["triage_checked_at_utc"] = now_utc()
            for key in ("triage_relevance", "triage_relevance_score", "triage_source_type_suggested", "triage_checked_at_utc"):
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
    if args.apply_to_stubs:
        print(
            "Stub updates: "
            f"considered={stub_updates['considered']} "
            f"updated={stub_updates['updated']} "
            f"status_updates={stub_updates['status_updates']} "
            f"source_type_updates={stub_updates['source_type_updates']} "
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
