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
]


FIELDNAMES = [
    "seed_id",
    "dataset",
    "provider_profile",
    "module_id",
    "module_type",
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
            provider_outputs[provider_profile] = {
                "seed_csv": str(csv_path),
                "seed_count": len(rows),
                "module_type_counts": dict(sorted(Counter(row["module_type"] for row in rows).items())),
                "recommended_max_results_per_seed": RECOMMENDED_CAPS[provider_profile],
                "module_type_outputs": type_outputs,
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
