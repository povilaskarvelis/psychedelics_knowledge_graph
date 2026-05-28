#!/usr/bin/env python3
"""Compile reproducible direct-search seed files from project registries."""

from __future__ import annotations

import argparse
from collections import Counter
import csv
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.ingest.discover_literature import (  # noqa: E402
    DEFAULT_SEEDS,
    Seed,
    allowed_entities_for_dataset,
    clean_query_text,
    dedupe_values,
    parse_allowlists,
    parse_seed,
    query_safe_label,
)

VERSION = "0.1"
DEFAULT_RUN_ID = "literature_search"
SEARCH_STRATEGY_ROOT = ROOT / "data" / "raw" / "search_strategies"

COMPOUND_BROAD_TEMPLATES = {
    "mechanistic": [
        "{compound} pharmacology receptor binding affinity",
        "{compound} receptor transporter target profile",
        "{compound} mechanism signaling neuroplasticity pharmacology",
    ],
    "disorder": [
        "{compound} clinical trial treatment efficacy safety",
        "{compound} therapy psychiatric neurological disorder outcome",
        "{compound} randomized placebo open label follow-up",
    ],
}

ENTITY_BROAD_TEMPLATES = {
    "mechanistic": [
        "psychedelic {entity} pharmacology binding affinity",
        "hallucinogen {entity} receptor transporter assay",
        "{entity} serotonergic psychedelic binding assay",
    ],
    "disorder": [
        "psychedelic {entity} clinical trial treatment",
        "psilocybin LSD MDMA ketamine {entity} therapy",
        "{entity} psychedelic-assisted therapy outcome safety",
    ],
}

SYSTEMS_ENTITY_BROAD_TEMPLATES = {
    "brain_region_or_network": [
        "psychedelic {entity} functional connectivity neuroimaging",
        "hallucinogen {entity} brain circuit activity",
        "{entity} psychedelic EEG fMRI PET",
    ],
    "cognitive_behavioral_task": [
        "psychedelic {entity} cognitive behavioral task",
        "hallucinogen {entity} learning behavior paradigm",
        "{entity} psychedelic rodent human task performance",
    ],
}

PAIR_CORE_TEMPLATES = {
    "mechanistic": [
        "{compound} {entity} binding affinity Ki",
        "{compound} {entity} receptor pharmacology assay",
        "{compound} {entity} functional assay agonist antagonist",
    ],
    "disorder": [
        "{compound} {entity} clinical trial",
        "{compound} {entity} randomized placebo",
        "{compound} {entity} treatment outcome",
    ],
}

SYSTEMS_PAIR_CORE_TEMPLATES = {
    "brain_region_or_network": [
        "{compound} {entity} functional connectivity neuroimaging",
        "{compound} {entity} fMRI BOLD activation",
        "{compound} {entity} EEG MEG neural oscillations",
    ],
    "cognitive_behavioral_task": [
        "{compound} {entity} cognitive task",
        "{compound} {entity} behavioral task",
        "{compound} {entity} learning conditioning",
    ],
}

PAIR_EXPANDED_TEMPLATES = {
    "mechanistic": [
        "{compound} {entity} radioligand binding",
        "{compound} {entity} Kd IC50 EC50",
        "{compound} {entity} signaling beta arrestin cAMP calcium",
        "{compound} {entity} uptake release transporter",
        "{compound} {entity} in vitro in vivo assay",
    ],
    "disorder": [
        "{compound} {entity} open label trial",
        "{compound} {entity} safety tolerability adverse events",
        "{compound} {entity} response remission follow-up",
        "{compound} {entity} phase 2 phase 3",
        "{compound} {entity} observational cohort case series",
    ],
}

SYSTEMS_PAIR_EXPANDED_TEMPLATES = {
    "brain_region_or_network": [
        "{compound} {entity} PET receptor occupancy",
        "{compound} {entity} neuronal activity c-Fos",
        "{compound} {entity} circuit behavior",
    ],
    "cognitive_behavioral_task": [
        "{compound} {entity} performance paradigm",
        "{compound} {entity} rodent behavior",
        "{compound} {entity} neural circuit",
    ],
}

CLASS_LEVEL_TEMPLATES = {
    "mechanistic": [
        "psychedelic receptor binding affinity pharmacology",
        "serotonergic psychedelic 5-HT receptor binding",
        "hallucinogen receptor affinity assay",
        "psychoplastogen receptor target mechanism",
    ],
    "disorder": [
        "psychedelic therapy clinical trial psychiatric disorder",
        "psychedelic-assisted therapy safety efficacy",
        "psilocybin LSD MDMA ketamine clinical trial",
    ],
}

MECHANISTIC_ENTITY_GROUPS = [
    ("allowed_targets", "target"),
    ("allowed_brain_regions_and_networks", "brain_region_or_network"),
    ("allowed_cognitive_behavioral_tasks", "cognitive_behavioral_task"),
]


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def limited(values: list[str], max_items: int) -> list[str]:
    if max_items > 0:
        return values[:max_items]
    return values


def limited_pairs(left: list[str], right: list[str], max_pairs: int) -> Iterable[tuple[str, str]]:
    count = 0
    for left_value in left:
        for right_value in right:
            if max_pairs > 0 and count >= max_pairs:
                return
            count += 1
            yield left_value, right_value


def entity_groups_for_dataset(dataset: str, allowlists: dict[str, list[str]], max_entities: int) -> list[dict]:
    if dataset == "disorder":
        return [
            {
                "entity_type": "indication",
                "allowlist_key": "allowed_disorders",
                "entities": limited(allowed_entities_for_dataset(dataset, allowlists), max_entities),
            }
        ]

    groups = []
    remaining = max(0, max_entities)
    for allowlist_key, entity_type in MECHANISTIC_ENTITY_GROUPS:
        values = dedupe_values(allowlists.get(allowlist_key, []))
        if max_entities > 0:
            values = values[:remaining]
            remaining = max(0, remaining - len(values))
        groups.append(
            {
                "entity_type": entity_type,
                "allowlist_key": allowlist_key,
                "entities": values,
            }
        )
    return groups


def entity_broad_templates(dataset: str, entity_type: str) -> list[str]:
    if dataset == "mechanistic" and entity_type in SYSTEMS_ENTITY_BROAD_TEMPLATES:
        return SYSTEMS_ENTITY_BROAD_TEMPLATES[entity_type]
    return ENTITY_BROAD_TEMPLATES[dataset]


def pair_core_templates(dataset: str, entity_type: str) -> list[str]:
    if dataset == "mechanistic" and entity_type in SYSTEMS_PAIR_CORE_TEMPLATES:
        return SYSTEMS_PAIR_CORE_TEMPLATES[entity_type]
    return PAIR_CORE_TEMPLATES[dataset]


def pair_expanded_templates(dataset: str, entity_type: str) -> list[str]:
    if dataset == "mechanistic" and entity_type in SYSTEMS_PAIR_EXPANDED_TEMPLATES:
        return SYSTEMS_PAIR_EXPANDED_TEMPLATES[entity_type]
    return PAIR_EXPANDED_TEMPLATES[dataset]


def add_seed(
    rows: list[dict],
    seen: set[tuple[str, str, str]],
    dataset: str,
    family: str,
    query: str,
    compound: str,
    entity: str,
    template: str,
    entity_type: str,
) -> None:
    query = clean_query_text(query)
    if not query:
        return
    key = (query.lower(), compound.lower(), entity.lower())
    if key in seen:
        return
    seen.add(key)
    rows.append(
        {
            "seed_id": f"{dataset}_{len(rows) + 1:05d}",
            "dataset": dataset,
            "family": family,
            "query": query,
            "compound": compound,
            "entity": entity,
            "entity_type": entity_type,
            "template": template,
        }
    )


def default_seed_rows(dataset: str) -> list[Seed]:
    return [parse_seed(value) for value in DEFAULT_SEEDS[dataset]]


def build_search_plan(
    dataset: str,
    allowlists: dict[str, list[str]],
    profile: str,
    include_default_seeds: bool,
    max_compounds: int,
    max_entities: int,
    max_pairs: int,
    run_id: str = DEFAULT_RUN_ID,
) -> dict:
    compounds = limited(dedupe_values(allowlists.get("allowed_compounds", [])), max_compounds)
    entity_groups = entity_groups_for_dataset(dataset, allowlists, max_entities=max_entities)
    entity_type = "target" if dataset == "mechanistic" else "indication"
    rows: list[dict] = []
    seen: set[tuple[str, str, str]] = set()

    if include_default_seeds:
        for seed in default_seed_rows(dataset):
            add_seed(
                rows,
                seen,
                dataset,
                "sentinel_default",
                seed.query,
                seed.compound,
                seed.entity,
                "DEFAULT_SEEDS",
                entity_type,
            )

    for template in CLASS_LEVEL_TEMPLATES[dataset]:
        add_seed(rows, seen, dataset, "class_level", template, "", "", template, entity_type)

    for compound in compounds:
        for template in COMPOUND_BROAD_TEMPLATES[dataset]:
            add_seed(
                rows,
                seen,
                dataset,
                "compound_broad",
                template.format(compound=compound),
                compound,
                "",
                template,
                entity_type,
            )

    pair_count = 0
    entity_type_counts = {}
    for group in entity_groups:
        group_entity_type = group["entity_type"]
        entities = group["entities"]
        entity_type_counts[group_entity_type] = len(entities)

        for entity in entities:
            entity_query = query_safe_label(entity)
            for template in entity_broad_templates(dataset, group_entity_type):
                add_seed(
                    rows,
                    seen,
                    dataset,
                    "entity_broad",
                    template.format(entity=entity_query),
                    "",
                    entity,
                    template,
                    group_entity_type,
                )

        core_templates = list(pair_core_templates(dataset, group_entity_type))
        expanded_templates = pair_expanded_templates(dataset, group_entity_type)
        pair_templates = list(core_templates)
        if profile == "expanded":
            pair_templates.extend(expanded_templates)

        if max_pairs > 0 and pair_count >= max_pairs:
            continue
        group_pair_limit = max_pairs - pair_count if max_pairs > 0 else 0
        for compound, entity in limited_pairs(compounds, entities, max_pairs=group_pair_limit):
            pair_count += 1
            entity_query = query_safe_label(entity)
            for template in pair_templates:
                add_seed(
                    rows,
                    seen,
                    dataset,
                    "pair_core" if template in core_templates else "pair_expanded",
                    template.format(compound=compound, entity=entity_query),
                    compound,
                    entity,
                    template,
                    group_entity_type,
                )

    family_counts = Counter(row["family"] for row in rows)
    type_counts = Counter(row["entity_type"] for row in rows)
    return {
        "version": VERSION,
        "run_id": run_id,
        "protocol_id": run_id,
        "generated_at_utc": now_utc(),
        "dataset": dataset,
        "profile": profile,
        "include_default_seeds": include_default_seeds,
        "scope": {
            "compound_count": len(compounds),
            "entity_count": sum(entity_type_counts.values()),
            "pair_count": pair_count,
            "entity_type": entity_type,
            "entity_type_counts": dict(sorted(entity_type_counts.items())),
        },
        "counts": {
            "seed_count": len(rows),
            "seed_family_counts": dict(sorted(family_counts.items())),
            "seed_entity_type_counts": dict(sorted(type_counts.items())),
        },
        "recommended_discovery_settings": {
            "provider": "comprehensive",
            "query_variant_mode": "expanded",
            "max_results_per_seed": 100,
            "max_results": 0,
            "citation_chase": "known-study-set",
            "citation_chase_directions": "both",
            "skip_unpaywall_enrichment": False,
            "run_new_doi_gate": True,
        },
        "notes": [
            "This is a search instrument, not a claim that every retrieved paper is relevant.",
            "Update the compound, target, or indication registries first, then regenerate this plan instead of hand-editing seed outputs.",
        ],
        "seeds": rows,
    }


def write_seed_csv(path: Path, rows: list[dict]) -> None:
    fieldnames = ["seed_id", "dataset", "family", "query", "compound", "entity", "entity_type", "template"]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_seed_txt(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        handle.write("# query|compound|entity\n")
        for row in rows:
            handle.write("|".join([row["query"], row["compound"], row["entity"]]) + "\n")


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build direct pair-search seed files")
    parser.add_argument("--dataset", choices=["mechanistic", "disorder", "all"], default="all")
    parser.add_argument("--config", default=str(ROOT / "pipeline" / "config.example.yaml"))
    parser.add_argument("--profile", choices=["standard", "expanded", "baseline"], default="standard")
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID, help="Run label used when --out-dir is not supplied")
    parser.add_argument("--search-root", default=str(SEARCH_STRATEGY_ROOT), help="Root directory for generated search files")
    parser.add_argument("--max-compounds", type=int, default=0, help="Compound cap for dry runs (0 = all)")
    parser.add_argument("--max-entities", type=int, default=0, help="Target/indication cap for dry runs (0 = all)")
    parser.add_argument("--max-pairs", type=int, default=0, help="Pair cap for dry runs (0 = all)")
    parser.add_argument("--exclude-default-seeds", action="store_true")
    parser.add_argument(
        "--out-dir",
        default="",
        help="Output directory for direct pair-search seed files. Defaults to <search-root>/<run-id>/direct_pairs.",
    )
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    search_root = Path(args.search_root).resolve()
    out_dir = Path(args.out_dir).resolve() if args.out_dir else search_root / args.run_id / "direct_pairs"
    profile = "standard" if args.profile == "baseline" else args.profile
    allowlists = parse_allowlists(config_path)
    datasets = ["mechanistic", "disorder"] if args.dataset == "all" else [args.dataset]
    generated = []

    for dataset in datasets:
        plan = build_search_plan(
            dataset=dataset,
            allowlists=allowlists,
            profile=profile,
            include_default_seeds=not args.exclude_default_seeds,
            max_compounds=max(0, args.max_compounds),
            max_entities=max(0, args.max_entities),
            max_pairs=max(0, args.max_pairs),
            run_id=args.run_id,
        )
        seed_csv = out_dir / f"{dataset}_seeds.csv"
        seed_txt = out_dir / f"{dataset}_seeds.txt"
        manifest = out_dir / f"{dataset}_search_manifest.json"
        write_seed_csv(seed_csv, plan["seeds"])
        write_seed_txt(seed_txt, plan["seeds"])

        entity_type_outputs = {}
        for entity_type, count in sorted(plan["counts"].get("seed_entity_type_counts", {}).items()):
            type_rows = [row for row in plan["seeds"] if row["entity_type"] == entity_type]
            type_seed_csv = out_dir / f"{dataset}_{entity_type}_seeds.csv"
            type_seed_txt = out_dir / f"{dataset}_{entity_type}_seeds.txt"
            write_seed_csv(type_seed_csv, type_rows)
            write_seed_txt(type_seed_txt, type_rows)
            entity_type_outputs[entity_type] = {
                "seed_csv": str(type_seed_csv),
                "seed_txt": str(type_seed_txt),
                "seed_count": count,
                "seed_family_counts": dict(sorted(Counter(row["family"] for row in type_rows).items())),
            }

        manifest_payload = dict(plan)
        manifest_payload["outputs"] = {
            "seed_csv": str(seed_csv),
            "seed_txt": str(seed_txt),
            "manifest_json": str(manifest),
            "entity_type_outputs": entity_type_outputs,
        }
        manifest_payload["run_command"] = (
            "python pipeline/ingest/run_pair_grid_audit.py "
            f"--dataset {dataset} --seed-root {out_dir} --provider both"
        )
        write_json(manifest, manifest_payload)
        generated.append(manifest_payload)

        print(f"Dataset: {dataset}")
        print(f"Seeds: {plan['counts']['seed_count']}")
        print("Families: " + ", ".join(f"{k}={v}" for k, v in plan["counts"]["seed_family_counts"].items()))
        print(f"Seed CSV: {seed_csv}")
        print(f"Manifest: {manifest}")

    summary = {
        "version": VERSION,
        "run_id": args.run_id,
        "protocol_id": args.run_id,
        "generated_at_utc": now_utc(),
        "profile": args.profile,
        "config": str(config_path),
        "datasets": {
            item["dataset"]: {
                "seed_count": item["counts"]["seed_count"],
                "seed_family_counts": item["counts"]["seed_family_counts"],
                "scope": item["scope"],
                "outputs": item["outputs"],
                "run_command": item["run_command"],
            }
            for item in generated
        },
    }
    summary_path = out_dir / "search_strategy_summary.json"
    write_json(summary_path, summary)
    print(f"Summary: {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
