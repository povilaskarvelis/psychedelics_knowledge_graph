#!/usr/bin/env python3
"""Build small, reproducible calibration seed batches from a baseline plan."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import datetime as dt
import json
import random
import sys
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[2]
PROTOCOL_ID = "comprehensive_baseline_v1"
VERSION = "0.1"


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def read_seed_csv(path: Path) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(f"Seed CSV not found: {path}")
    with path.open("r", encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def write_seed_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        raise ValueError(f"No rows selected for {path}")
    fieldnames = ["seed_id", "dataset", "family", "query", "compound", "entity", "entity_type", "template"]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def group_rows(rows: Iterable[dict], keys: tuple[str, ...]) -> dict[tuple[str, ...], list[dict]]:
    grouped: dict[tuple[str, ...], list[dict]] = defaultdict(list)
    for row in rows:
        key = tuple((row.get(field) or "").strip() for field in keys)
        grouped[key].append(row)
    return dict(grouped)


def sample_groups(
    grouped: dict[tuple[str, ...], list[dict]],
    count: int,
    rng: random.Random,
) -> list[tuple[tuple[str, ...], list[dict]]]:
    items = list(grouped.items())
    items.sort(key=lambda item: item[0])
    rng.shuffle(items)
    if count <= 0:
        return []
    if count >= len(items):
        return items
    return items[:count]


def sample_pair_groups(
    grouped: dict[tuple[str, str], list[dict]],
    count: int,
    rng: random.Random,
) -> list[tuple[tuple[str, str], list[dict]]]:
    items = list(grouped.items())
    items.sort(key=lambda item: item[0])
    rng.shuffle(items)
    if count <= 0:
        return []
    if count >= len(items):
        return items

    selected: list[tuple[tuple[str, str], list[dict]]] = []
    used_compounds: set[str] = set()
    used_entities: set[str] = set()
    remaining = items[:]

    while remaining and len(selected) < count:
        def score(item: tuple[tuple[str, str], list[dict]]) -> tuple[int, int]:
            compound, entity = item[0]
            novelty = int(compound not in used_compounds) + int(entity not in used_entities)
            return novelty, -len(selected)

        best_idx = max(range(len(remaining)), key=lambda idx: score(remaining[idx]))
        item = remaining.pop(best_idx)
        selected.append(item)
        compound, entity = item[0]
        if compound:
            used_compounds.add(compound)
        if entity:
            used_entities.add(entity)

    return selected


def flatten_group_selection(selection: Iterable[tuple[tuple[str, ...], list[dict]]]) -> list[dict]:
    rows: list[dict] = []
    for _, group in selection:
        rows.extend(group)
    rows.sort(key=lambda row: row.get("seed_id", ""))
    return rows


def family_rows(rows: list[dict], family: str) -> list[dict]:
    return [row for row in rows if row.get("family") == family]


def select_calibration_rows(
    rows: list[dict],
    *,
    random_seed: int,
    sentinel_count: int,
    compound_units: int,
    entity_units: int,
    pair_units: int,
    pair_expanded_units: int,
) -> tuple[list[dict], dict]:
    rng = random.Random(random_seed)

    selected: list[dict] = []
    selected.extend(family_rows(rows, "class_level"))

    sentinel = family_rows(rows, "sentinel_default")
    sentinel.sort(key=lambda row: row.get("seed_id", ""))
    rng.shuffle(sentinel)
    selected.extend(sorted(sentinel[: max(0, sentinel_count)], key=lambda row: row.get("seed_id", "")))

    compound_selection = sample_groups(
        group_rows(family_rows(rows, "compound_broad"), ("compound",)),
        max(0, compound_units),
        rng,
    )
    entity_selection = sample_groups(
        group_rows(family_rows(rows, "entity_broad"), ("entity",)),
        max(0, entity_units),
        rng,
    )
    pair_core_selection = sample_pair_groups(
        group_rows(family_rows(rows, "pair_core"), ("compound", "entity")),
        max(0, pair_units),
        rng,
    )
    pair_expanded_selection = sample_pair_groups(
        group_rows(family_rows(rows, "pair_expanded"), ("compound", "entity")),
        max(0, pair_expanded_units),
        rng,
    )

    selected.extend(flatten_group_selection(compound_selection))
    selected.extend(flatten_group_selection(entity_selection))
    selected.extend(flatten_group_selection(pair_core_selection))
    selected.extend(flatten_group_selection(pair_expanded_selection))

    seen: set[str] = set()
    deduped: list[dict] = []
    for row in sorted(selected, key=lambda item: item.get("seed_id", "")):
        seed_id = row.get("seed_id", "")
        if seed_id in seen:
            continue
        seen.add(seed_id)
        deduped.append(row)

    family_counts = Counter(row.get("family", "") for row in deduped)
    summary = {
        "selected_seed_count": len(deduped),
        "selected_family_counts": dict(sorted(family_counts.items())),
        "selected_units": {
            "sentinel_default_rows": min(max(0, sentinel_count), len(sentinel)),
            "compound_broad_compounds": [key[0] for key, _ in compound_selection],
            "entity_broad_entities": [key[0] for key, _ in entity_selection],
            "pair_core_pairs": [{"compound": key[0], "entity": key[1]} for key, _ in pair_core_selection],
            "pair_expanded_pairs": [{"compound": key[0], "entity": key[1]} for key, _ in pair_expanded_selection],
        },
    }
    return deduped, summary


def build_batches(
    *,
    protocol_dir: Path,
    out_dir: Path,
    datasets: list[str],
    random_seed: int,
    sentinel_count: int,
    compound_units: int,
    entity_units: int,
    pair_units: int,
    pair_expanded_units: int,
) -> dict:
    manifest = {
        "version": VERSION,
        "protocol_id": PROTOCOL_ID,
        "generated_at_utc": now_utc(),
        "protocol_dir": str(protocol_dir),
        "random_seed": random_seed,
        "selection_settings": {
            "sentinel_count": sentinel_count,
            "compound_units": compound_units,
            "entity_units": entity_units,
            "pair_units": pair_units,
            "pair_expanded_units": pair_expanded_units,
        },
        "datasets": {},
    }

    for dataset in datasets:
        source_csv = protocol_dir / f"{dataset}_seeds.csv"
        rows = read_seed_csv(source_csv)
        selected, summary = select_calibration_rows(
            rows,
            random_seed=random_seed,
            sentinel_count=sentinel_count,
            compound_units=compound_units,
            entity_units=entity_units,
            pair_units=pair_units,
            pair_expanded_units=pair_expanded_units,
        )
        out_csv = out_dir / f"{dataset}_calibration_seeds.csv"
        write_seed_csv(out_csv, selected)

        manifest["datasets"][dataset] = {
            "source_seed_csv": str(source_csv),
            "calibration_seed_csv": str(out_csv),
            "source_seed_count": len(rows),
            **summary,
            "suggested_fast_run": (
                "python pipeline/ingest/discover_literature.py "
                f"--dataset {dataset} --provider openalex "
                f"--seed-file {out_csv} --query-variant-mode conservative "
                "--max-results-per-seed 10 --max-results 0 "
                "--disable-ledger --disable-protected-retention --skip-unpaywall-enrichment"
            ),
        }

    manifest_path = out_dir / "calibration_manifest.json"
    write_json(manifest_path, manifest)
    manifest["manifest_json"] = str(manifest_path)
    write_json(manifest_path, manifest)
    return manifest


def parse_datasets(raw: str) -> list[str]:
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Build calibration seed batches from a comprehensive search plan")
    parser.add_argument("--dataset", default="all", help="mechanistic, disorder, comma-separated list, or all")
    parser.add_argument(
        "--protocol-dir",
        default=str(ROOT / "data" / "raw" / "search_strategies" / PROTOCOL_ID),
    )
    parser.add_argument(
        "--out-dir",
        default=str(ROOT / "data" / "raw" / "search_strategies" / PROTOCOL_ID / "calibration"),
    )
    parser.add_argument("--random-seed", type=int, default=20260515)
    parser.add_argument("--sentinel-count", type=int, default=6)
    parser.add_argument("--compound-units", type=int, default=4)
    parser.add_argument("--entity-units", type=int, default=4)
    parser.add_argument("--pair-units", type=int, default=4)
    parser.add_argument("--pair-expanded-units", type=int, default=0)
    args = parser.parse_args()

    try:
        datasets = parse_datasets(args.dataset)
    except ValueError as err:
        raise SystemExit(str(err))

    manifest = build_batches(
        protocol_dir=Path(args.protocol_dir).resolve(),
        out_dir=Path(args.out_dir).resolve(),
        datasets=datasets,
        random_seed=args.random_seed,
        sentinel_count=max(0, args.sentinel_count),
        compound_units=max(0, args.compound_units),
        entity_units=max(0, args.entity_units),
        pair_units=max(0, args.pair_units),
        pair_expanded_units=max(0, args.pair_expanded_units),
    )

    print(f"Manifest: {manifest['manifest_json']}")
    for dataset, info in manifest["datasets"].items():
        families = ", ".join(
            f"{family}={count}" for family, count in info["selected_family_counts"].items()
        )
        print(f"Dataset: {dataset}")
        print(f"  Source seeds: {info['source_seed_count']}")
        print(f"  Calibration seeds: {info['selected_seed_count']} ({families})")
        print(f"  Seed CSV: {info['calibration_seed_csv']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
