#!/usr/bin/env python3
"""Build a small sentinel direct-pair search set for closure auditing.

This is intentionally not a full pair grid. It samples high-priority
compound/domain pairs added after the first baseline search so the team can
estimate whether a larger pairwise layer is worth running.
"""

from __future__ import annotations

from collections import Counter
import csv
import datetime as dt
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SEARCH_STRATEGY_ROOT = ROOT / "data" / "raw" / "search_strategies"
DEFAULT_RUN_ID = "closure_pairwise_audit_2026_05"
VERSION = "0.1"

FIELDNAMES = ["seed_id", "dataset", "family", "query", "compound", "entity", "entity_type", "template"]

MECHANISTIC_SEEDS = [
    ("Psilocybin", "Default mode network", "brain_region_or_network", "{compound} {entity} functional connectivity"),
    ("Psilocybin", "Medial prefrontal cortex", "brain_region_or_network", "{compound} {entity} fMRI BOLD"),
    ("Psilocybin", "Amygdala", "brain_region_or_network", "{compound} {entity} emotional processing fMRI"),
    ("Psilocybin", "Thalamus", "brain_region_or_network", "{compound} {entity} connectivity"),
    ("LSD", "Default mode network", "brain_region_or_network", "{compound} {entity} functional connectivity"),
    ("LSD", "Thalamo-cortical circuit", "brain_region_or_network", "{compound} {entity} connectivity fMRI"),
    ("LSD", "Visual cortex", "brain_region_or_network", "{compound} {entity} fMRI BOLD"),
    ("DMT", "EEG signal diversity", "brain_region_or_network", "{compound} {entity}"),
    ("DMT", "Visual cortex", "brain_region_or_network", "{compound} {entity} neuroimaging"),
    ("Ayahuasca", "Default mode network", "brain_region_or_network", "{compound} {entity} connectivity"),
    ("MDMA", "Amygdala-prefrontal circuit", "brain_region_or_network", "{compound} {entity} social emotion fMRI"),
    ("Ketamine", "Prefrontal-hippocampal circuit", "brain_region_or_network", "{compound} {entity}"),
    ("Ketamine", "Default mode network", "brain_region_or_network", "{compound} {entity} connectivity"),
    ("5-MeO-DMT", "Functional connectivity", "brain_region_or_network", "{compound} {entity} neuroimaging"),
    ("Mescaline", "Brain connectivity", "brain_region_or_network", "{compound} {entity}"),
    ("Psilocybin", "Cognitive flexibility", "cognitive_behavioral_task", "{compound} {entity} task"),
    ("Psilocybin", "Emotional processing", "cognitive_behavioral_task", "{compound} {entity} task"),
    ("Psilocybin", "Fear extinction", "cognitive_behavioral_task", "{compound} {entity}"),
    ("LSD", "Reversal learning", "cognitive_behavioral_task", "{compound} {entity}"),
    ("LSD", "Emotional processing", "cognitive_behavioral_task", "{compound} {entity} task"),
    ("MDMA", "Social cognition", "cognitive_behavioral_task", "{compound} {entity}"),
    ("MDMA", "Emotion recognition", "cognitive_behavioral_task", "{compound} {entity}"),
    ("Ketamine", "Reward learning", "cognitive_behavioral_task", "{compound} {entity}"),
    ("DMT", "Attention", "cognitive_behavioral_task", "{compound} {entity} task"),
    ("Ayahuasca", "Empathy", "cognitive_behavioral_task", "{compound} {entity}"),
    ("Psilocybin", "BDNF TrkB neuroplasticity", "molecular_pathway", "{compound} {entity}"),
    ("Psilocybin", "mTOR synaptogenesis", "molecular_pathway", "{compound} {entity}"),
    ("Psilocybin", "immediate early genes c-Fos", "molecular_pathway", "{compound} {entity}"),
    ("LSD", "cortical plasticity dendritic spine", "molecular_pathway", "{compound} {entity}"),
    ("LSD", "BDNF signaling", "molecular_pathway", "{compound} {entity}"),
    ("DMT", "sigma-1 neuroplasticity", "molecular_pathway", "{compound} {entity}"),
    ("Ayahuasca", "inflammation cytokines", "molecular_pathway", "{compound} {entity}"),
    ("MDMA", "oxytocin social reward", "molecular_pathway", "{compound} {entity}"),
    ("Ketamine", "mTOR synaptogenesis", "molecular_pathway", "{compound} {entity}"),
    ("Ketamine", "BDNF TrkB", "molecular_pathway", "{compound} {entity}"),
    ("5-MeO-DMT", "inflammatory cytokines", "molecular_pathway", "{compound} {entity}"),
    ("Mescaline", "gene expression signaling", "molecular_pathway", "{compound} {entity}"),
    ("Psilocybin", "5-HT2A receptor occupancy PET", "molecular_target", "{compound} {entity}"),
    ("LSD", "5-HT2A receptor occupancy PET", "molecular_target", "{compound} {entity}"),
    ("MDMA", "SERT occupancy PET", "molecular_target", "{compound} {entity}"),
    ("Ketamine", "glutamate metabolism magnetic resonance spectroscopy", "molecular_pathway", "{compound} {entity}"),
]

DISORDER_SEEDS = [
    ("Psilocybin", "Anhedonia", "clinical_symptom_function", "{compound} {entity} depression clinical trial"),
    ("Psilocybin", "Suicidal ideation", "clinical_symptom_function", "{compound} {entity} depression trial"),
    ("Psilocybin", "Rumination", "clinical_symptom_function", "{compound} {entity} depression"),
    ("Psilocybin", "Emotional processing", "clinical_symptom_function", "{compound} {entity} clinical"),
    ("Psilocybin", "Cognitive flexibility", "clinical_symptom_function", "{compound} {entity} clinical"),
    ("LSD", "Anxiety emotional processing", "clinical_symptom_function", "{compound} {entity} clinical trial"),
    ("LSD", "Alcohol craving", "clinical_symptom_function", "{compound} {entity} clinical trial"),
    ("MDMA", "Social functioning PTSD", "clinical_symptom_function", "{compound} {entity} trial"),
    ("MDMA", "Emotion recognition PTSD", "clinical_symptom_function", "{compound} {entity} trial"),
    ("Ketamine", "Anhedonia depression", "clinical_symptom_function", "{compound} {entity} trial"),
    ("Ketamine", "Suicidal ideation depression", "clinical_symptom_function", "{compound} {entity} trial"),
    ("Ketamine", "Cognitive function depression", "clinical_symptom_function", "{compound} {entity} trial"),
    ("Ayahuasca", "Depression anxiety symptoms", "clinical_symptom_function", "{compound} {entity} trial"),
    ("DMT", "Depression anxiety symptoms", "clinical_symptom_function", "{compound} {entity} clinical trial"),
    ("5-MeO-DMT", "Depression anxiety symptoms", "clinical_symptom_function", "{compound} {entity}"),
    ("Psilocybin", "Adverse events safety tolerability", "clinical_safety", "{compound} {entity} trial"),
    ("MDMA", "Adverse events safety tolerability", "clinical_safety", "{compound} {entity} trial"),
    ("Ketamine", "Dissociation adverse events tolerability", "clinical_safety", "{compound} {entity} trial"),
    ("Psilocybin", "Functional impairment quality of life", "clinical_symptom_function", "{compound} {entity} trial"),
    ("MDMA", "Fear extinction PTSD", "clinical_mechanism_overlap", "{compound} {entity} trial"),
    ("Ketamine", "Functional connectivity depression", "clinical_mechanism_overlap", "{compound} {entity} trial"),
]


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def clean_query(text: str) -> str:
    return " ".join(str(text).split())


def rows_for_dataset(dataset: str, specs: list[tuple[str, str, str, str]]) -> list[dict]:
    rows = []
    seen = set()
    for compound, entity, entity_type, template in specs:
        query = clean_query(template.format(compound=compound, entity=entity))
        key = (query.lower(), compound.lower(), entity.lower())
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            {
                "seed_id": f"{dataset}_{len(rows) + 1:05d}",
                "dataset": dataset,
                "family": "pair_core",
                "query": query,
                "compound": compound,
                "entity": entity,
                "entity_type": entity_type,
                "template": template,
            }
        )
    return rows


def write_seed_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
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


def summarize(rows: list[dict]) -> dict:
    return {
        "seed_count": len(rows),
        "seed_family_counts": dict(Counter(row["family"] for row in rows)),
        "seed_entity_type_counts": dict(sorted(Counter(row["entity_type"] for row in rows).items())),
        "compound_counts": dict(sorted(Counter(row["compound"] for row in rows).items())),
    }


def main() -> int:
    run_id = DEFAULT_RUN_ID
    out_dir = SEARCH_STRATEGY_ROOT / run_id / "direct_pairs"
    generated_at = now_utc()
    datasets = {
        "mechanistic": rows_for_dataset("mechanistic", MECHANISTIC_SEEDS),
        "disorder": rows_for_dataset("disorder", DISORDER_SEEDS),
    }

    summary = {
        "version": VERSION,
        "run_id": run_id,
        "protocol_id": run_id,
        "generated_at_utc": generated_at,
        "profile": "sentinel_closure_audit",
        "description": (
            "Small direct-pair audit for domains added after the first baseline search. "
            "This is a calibration layer, not an exhaustive pair grid."
        ),
        "recommended_run": {
            "command": (
                "python pipeline/ingest/run_pair_grid_audit.py "
                f"--run-id {run_id} --dataset all --families pair_core --provider both "
                "--mechanistic-cap 10 --disorder-cap 10 --chunk-size 100 "
                "--openalex-rps 0.5 --pubmed-rps 0.5"
            )
        },
        "datasets": {},
    }

    for dataset, rows in datasets.items():
        seed_csv = out_dir / f"{dataset}_seeds.csv"
        seed_txt = out_dir / f"{dataset}_seeds.txt"
        manifest_json = out_dir / f"{dataset}_search_manifest.json"
        write_seed_csv(seed_csv, rows)
        write_seed_txt(seed_txt, rows)
        manifest = {
            "version": VERSION,
            "run_id": run_id,
            "protocol_id": run_id,
            "generated_at_utc": generated_at,
            "dataset": dataset,
            "profile": "sentinel_closure_audit",
            "counts": summarize(rows),
            "outputs": {
                "seed_csv": str(seed_csv),
                "seed_txt": str(seed_txt),
                "manifest_json": str(manifest_json),
            },
            "seeds": rows,
        }
        write_json(manifest_json, manifest)
        summary["datasets"][dataset] = {
            **summarize(rows),
            "outputs": manifest["outputs"],
        }
        print(f"Dataset: {dataset}")
        print(f"Seeds: {len(rows)}")
        print(f"Seed CSV: {seed_csv}")

    summary_path = out_dir / "search_strategy_summary.json"
    write_json(summary_path, summary)
    print(f"Summary: {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
