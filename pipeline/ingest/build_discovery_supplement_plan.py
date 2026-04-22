#!/usr/bin/env python3
"""Generate source-specific discovery supplement plans.

These sources are not plain DOI search engines. The plan records what should be
queried next for registry and assay databases before their outputs are merged
into downstream evidence tables.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.ingest.discover_literature import (
    COMPOUND_ALIASES,
    DISORDER_ALIASES,
    TARGET_ALIASES,
    alias_values,
    dedupe_values,
    parse_allowlists,
)


def limited_pairs(left: List[str], right: List[str], max_pairs: int) -> List[tuple[str, str]]:
    out: List[tuple[str, str]] = []
    for left_value in left:
        for right_value in right:
            out.append((left_value, right_value))
            if max_pairs > 0 and len(out) >= max_pairs:
                return out
    return out


def build_supplement_plan(dataset: str, allowlists: Dict[str, List[str]], max_pairs: int) -> dict:
    compounds = dedupe_values(allowlists.get("allowed_compounds", []))
    entity_key = "allowed_targets" if dataset == "mechanistic" else "allowed_disorders"
    entities = dedupe_values(allowlists.get(entity_key, []))
    pairs = limited_pairs(compounds, entities, max_pairs=max_pairs)

    supplements: List[dict] = []
    if dataset == "mechanistic":
        for compound, target in pairs:
            supplements.append(
                {
                    "source": "ChEMBL",
                    "role": "bioactivity assay supplement",
                    "compound": compound,
                    "target": target,
                    "compound_aliases": alias_values(compound, COMPOUND_ALIASES),
                    "target_aliases": alias_values(target, TARGET_ALIASES),
                    "planned_lookup": {
                        "molecule_lookup": "molecule/search",
                        "target_lookup": "target/search",
                        "activity_lookup": "activity/search filtered by molecule_chembl_id and target_chembl_id",
                    },
                    "output_expected": "assay/activity evidence rows, not DOI queue rows",
                }
            )
            supplements.append(
                {
                    "source": "BindingDB",
                    "role": "binding affinity cross-check supplement",
                    "compound": compound,
                    "target": target,
                    "compound_aliases": alias_values(compound, COMPOUND_ALIASES),
                    "target_aliases": alias_values(target, TARGET_ALIASES),
                    "planned_lookup": {
                        "compound_query": "Ligand name/synonym or structure lookup",
                        "target_query": "UniProt/gene/protein alias lookup",
                    },
                    "output_expected": "Ki/Kd/IC50/EC50 evidence rows, not DOI queue rows",
                }
            )
    else:
        for compound, disorder in pairs:
            supplements.append(
                {
                    "source": "ClinicalTrials.gov",
                    "role": "registered trial supplement",
                    "compound": compound,
                    "disorder": disorder,
                    "compound_aliases": alias_values(compound, COMPOUND_ALIASES),
                    "disorder_aliases": alias_values(disorder, DISORDER_ALIASES),
                    "planned_lookup": {
                        "query.intr": compound,
                        "query.cond": disorder,
                        "fields": [
                            "NCTId",
                            "BriefTitle",
                            "OverallStatus",
                            "Phases",
                            "Conditions",
                            "Interventions",
                            "PrimaryOutcomes",
                            "References",
                        ],
                    },
                    "output_expected": "trial registry evidence rows and linked publications",
                }
            )

    return {
        "version": "0.1",
        "dataset": dataset,
        "max_pairs": max_pairs,
        "pair_count": len(pairs),
        "supplement_count": len(supplements),
        "notes": [
            "This plan intentionally does not add papers to the DOI queue.",
            "ChEMBL/BindingDB/ClinicalTrials.gov outputs should be modeled as source-specific evidence.",
            "Use this alongside DOI literature discovery and cite it in the run manifest.",
        ],
        "supplements": supplements,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate source-specific discovery supplement plan")
    parser.add_argument("--dataset", choices=["mechanistic", "disorder"], required=True)
    parser.add_argument("--config", default=str(ROOT / "pipeline" / "config.example.yaml"))
    parser.add_argument("--max-pairs", type=int, default=200)
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    out_path = (
        Path(args.out).resolve()
        if args.out
        else ROOT / "data" / "processed" / f"discovery_supplement_plan_{args.dataset}.json"
    )
    plan = build_supplement_plan(
        dataset=args.dataset,
        allowlists=parse_allowlists(config_path),
        max_pairs=max(0, args.max_pairs),
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"Dataset: {args.dataset}")
    print(f"Pairs: {plan['pair_count']}")
    print(f"Supplements: {plan['supplement_count']}")
    print(f"Plan: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
