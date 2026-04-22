#!/usr/bin/env python3
"""Audit discovery seed coverage before running literature retrieval."""

from __future__ import annotations

import argparse
from collections import Counter
import json
import sys
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.ingest.discover_literature import (  # noqa: E402
    DEFAULT_SEEDS,
    Seed,
    allowed_entities_for_dataset,
    build_seed_list,
    dedupe_values,
    generate_balanced_seeds,
    normalize,
    normalize_text,
    now_utc,
    parse_allowlists,
    parse_seed,
)


EVIDENCE_MARKERS = {
    "mechanistic": {
        "binding_affinity": ["binding", "affinity", "ki", "kd", "ic50"],
        "functional_assay": ["functional", "agonist", "antagonist", "ec50"],
        "radioligand": ["radioligand"],
        "signaling": ["signaling", "beta arrestin", "calcium", "camp"],
        "transporter": ["transporter", "uptake", "release"],
    },
    "disorder": {
        "randomized_trial": ["randomized", "randomised", "rct"],
        "open_label": ["open label"],
        "safety": ["safety", "tolerability", "adverse"],
        "outcome": ["outcome", "response", "remission"],
        "follow_up": ["follow-up", "follow up"],
    },
}


def covered_values(seeds: List[Seed], attr: str) -> Counter[str]:
    counts: Counter[str] = Counter()
    for seed in seeds:
        value = normalize(getattr(seed, attr))
        if value:
            counts[value] += 1
    return counts


def missing_values(allowed: List[str], covered: Counter[str]) -> List[str]:
    covered_keys = {normalize_text(value) for value in covered}
    return [value for value in allowed if normalize_text(value) not in covered_keys]


def top_counts(counts: Counter[str], limit: int = 15) -> List[dict]:
    return [{"label": label, "seed_count": count} for label, count in counts.most_common(limit)]


def evidence_marker_counts(seeds: List[Seed], dataset: str) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for label, markers in EVIDENCE_MARKERS[dataset].items():
        count = 0
        for seed in seeds:
            query = normalize(seed.query).lower()
            if any(marker in query for marker in markers):
                count += 1
        counts[label] = count
    return counts


def seed_sample(seeds: List[Seed], limit: int = 20) -> List[dict]:
    return [
        {
            "query": seed.query,
            "compound": seed.compound,
            "entity": seed.entity,
        }
        for seed in seeds[:limit]
    ]


def coverage_block(seeds: List[Seed], allowed_compounds: List[str], allowed_entities: List[str]) -> dict:
    compound_counts = covered_values(seeds, "compound")
    entity_counts = covered_values(seeds, "entity")
    missing_compounds = missing_values(allowed_compounds, compound_counts)
    missing_entities = missing_values(allowed_entities, entity_counts)
    return {
        "compound_coverage": len(allowed_compounds) - len(missing_compounds),
        "compound_total": len(allowed_compounds),
        "compound_missing_count": len(missing_compounds),
        "compound_missing": missing_compounds,
        "entity_coverage": len(allowed_entities) - len(missing_entities),
        "entity_total": len(allowed_entities),
        "entity_missing_count": len(missing_entities),
        "entity_missing": missing_entities,
        "top_compounds_by_seed_count": top_counts(compound_counts),
        "top_entities_by_seed_count": top_counts(entity_counts),
    }


def build_seed_audit(
    dataset: str,
    config_path: Path,
    balanced_seed_profile: str,
    balanced_max_compounds: int,
    balanced_max_entities: int,
    balanced_max_seeds: int,
) -> dict:
    allowlists = parse_allowlists(config_path)
    allowed_compounds = dedupe_values(allowlists.get("allowed_compounds", []))
    allowed_entities = allowed_entities_for_dataset(dataset, allowlists)
    if balanced_max_compounds > 0:
        balanced_allowed_compounds = allowed_compounds[:balanced_max_compounds]
    else:
        balanced_allowed_compounds = allowed_compounds
    if balanced_max_entities > 0:
        balanced_allowed_entities = allowed_entities[:balanced_max_entities]
    else:
        balanced_allowed_entities = allowed_entities

    default_seeds = [parse_seed(value) for value in DEFAULT_SEEDS[dataset]]
    final_seeds, seed_source_counts = build_seed_list(
        dataset=dataset,
        seed_values=[],
        query_values=[],
        allowlists=allowlists,
        expand_from_config=False,
        auto_seeds_only=False,
        auto_template_mode="focused",
        auto_max_compounds=0,
        auto_max_entities=0,
        auto_max_pairs=400,
        auto_max_seeds=1200,
        balanced_seed_profile=balanced_seed_profile,
        balanced_max_compounds=balanced_max_compounds,
        balanced_max_entities=balanced_max_entities,
        balanced_max_seeds=balanced_max_seeds,
    )
    balanced_seeds, balanced_counts = generate_balanced_seeds(
        dataset=dataset,
        allowlists=allowlists,
        base_seeds=default_seeds,
        profile=balanced_seed_profile,
        max_compounds=max(0, balanced_max_compounds),
        max_entities=max(0, balanced_max_entities),
        max_seeds=max(0, balanced_max_seeds),
    )

    return {
        "generated_at": now_utc(),
        "dataset": dataset,
        "config": str(config_path),
        "settings": {
            "balanced_seed_profile": balanced_seed_profile,
            "balanced_max_compounds": balanced_max_compounds,
            "balanced_max_entities": balanced_max_entities,
            "balanced_max_seeds": balanced_max_seeds,
        },
        "counts": {
            "allowed_compounds": len(allowed_compounds),
            "allowed_entities": len(allowed_entities),
            "balanced_allowed_compounds": len(balanced_allowed_compounds),
            "balanced_allowed_entities": len(balanced_allowed_entities),
            **seed_source_counts,
            "balanced_compound_gap": balanced_counts["compound_gap"],
            "balanced_entity_gap": balanced_counts["entity_gap"],
            "balanced_evidence": balanced_counts["evidence"],
        },
        "default_seed_coverage": coverage_block(default_seeds, allowed_compounds, allowed_entities),
        "final_seed_coverage": coverage_block(final_seeds, allowed_compounds, allowed_entities),
        "balanced_scope_coverage": coverage_block(
            final_seeds,
            balanced_allowed_compounds,
            balanced_allowed_entities,
        ),
        "evidence_marker_counts": evidence_marker_counts(final_seeds, dataset),
        "balanced_seed_sample": seed_sample(balanced_seeds),
        "final_seed_sample": seed_sample(final_seeds),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit discovery seed coverage")
    parser.add_argument("--dataset", choices=["mechanistic", "disorder"], required=True)
    parser.add_argument("--config", default=str(ROOT / "pipeline" / "config.example.yaml"))
    parser.add_argument(
        "--balanced-seed-profile",
        choices=["off", "coverage", "evidence"],
        default="off",
    )
    parser.add_argument("--balanced-max-compounds", type=int, default=20)
    parser.add_argument("--balanced-max-entities", type=int, default=50)
    parser.add_argument("--balanced-max-seeds", type=int, default=250)
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    out_path = (
        Path(args.out).resolve()
        if args.out
        else ROOT / "data" / "processed" / f"seed_audit_{args.dataset}.json"
    )
    audit = build_seed_audit(
        dataset=args.dataset,
        config_path=config_path,
        balanced_seed_profile=args.balanced_seed_profile,
        balanced_max_compounds=max(0, args.balanced_max_compounds),
        balanced_max_entities=max(0, args.balanced_max_entities),
        balanced_max_seeds=max(0, args.balanced_max_seeds),
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(audit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    counts = audit["counts"]
    default_cov = audit["default_seed_coverage"]
    final_cov = audit["final_seed_coverage"]
    print(f"Dataset: {args.dataset}")
    print(f"Balanced seed profile: {args.balanced_seed_profile}")
    print(f"Seeds: {counts['final']}")
    print(
        "Seed sources: "
        f"default={counts['default']} "
        f"balanced={counts['balanced']} "
        f"compound_gap={counts['balanced_compound_gap']} "
        f"entity_gap={counts['balanced_entity_gap']} "
        f"evidence={counts['balanced_evidence']}"
    )
    print(
        "Default coverage: "
        f"compounds={default_cov['compound_coverage']}/{default_cov['compound_total']} "
        f"entities={default_cov['entity_coverage']}/{default_cov['entity_total']}"
    )
    print(
        "Final coverage: "
        f"compounds={final_cov['compound_coverage']}/{final_cov['compound_total']} "
        f"entities={final_cov['entity_coverage']}/{final_cov['entity_total']}"
    )
    print(f"Audit: {out_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
