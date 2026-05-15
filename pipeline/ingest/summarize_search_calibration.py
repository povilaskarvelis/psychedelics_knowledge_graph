#!/usr/bin/env python3
"""Summarize a discovery calibration run by dataset and seed family."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import datetime as dt
import json
import statistics
import sys
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[2]
PROTOCOL_ID = "comprehensive_baseline_v1"
VERSION = "0.1"


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def normalize(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def normalize_doi(value: object) -> str:
    text = normalize(value).lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/", "http://dx.doi.org/", "doi:"):
        if text.startswith(prefix):
            text = text[len(prefix) :]
            break
    return text


def read_json(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Missing JSON file: {path}")
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"Expected object JSON: {path}")
    return payload


def read_seed_csv(path: Path) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(f"Missing seed CSV: {path}")
    with path.open("r", encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def read_queue_dois(path: Path) -> set[str]:
    if not path.exists():
        return set()
    dois: set[str] = set()
    with path.open("r", encoding="utf-8", newline="") as handle:
        for parts in csv.reader(handle):
            if not parts:
                continue
            first = normalize(parts[0])
            if not first or first.startswith("#") or first.lower() in {"doi", "study_doi"}:
                continue
            doi = normalize_doi(first)
            if doi:
                dois.add(doi)
    return dois


def seed_key(row: dict) -> tuple[str, str, str]:
    return (normalize(row.get("query")), normalize(row.get("compound")), normalize(row.get("entity")))


def numeric_summary(values: Iterable[int]) -> dict:
    items = list(values)
    if not items:
        return {"min": 0, "median": 0, "mean": 0.0, "max": 0}
    return {
        "min": min(items),
        "median": statistics.median(items),
        "mean": round(statistics.mean(items), 3),
        "max": max(items),
    }


def summarize_dataset(
    *,
    dataset: str,
    protocol_dir: Path,
    calibration_dir: Path,
) -> dict:
    full_seeds = read_seed_csv(protocol_dir / f"{dataset}_seeds.csv")
    calibration_seeds = read_seed_csv(calibration_dir.parent / f"{dataset}_calibration_seeds.csv")
    discovery = read_json(calibration_dir / f"{dataset}_discovery_report.json")
    add_new = read_json(calibration_dir / f"{dataset}_add_new_dois_report.json")
    new_dois = read_queue_dois(calibration_dir / f"{dataset}_new_dois.txt")

    seed_to_family = {seed_key(row): normalize(row.get("family")) for row in calibration_seeds}
    query_to_family: dict[str, str] = {}
    for row in calibration_seeds:
        query_to_family[normalize(row.get("query"))] = normalize(row.get("family"))

    per_seed_by_family: dict[str, list[int]] = defaultdict(list)
    max_results_per_seed = int(discovery.get("settings", {}).get("max_results_per_seed") or 0)
    for row in discovery.get("per_seed", []):
        family = seed_to_family.get(seed_key(row), "unknown")
        per_seed_by_family[family].append(int(row.get("rows_retrieved") or 0))

    merged_family_dois: dict[str, set[str]] = defaultdict(set)
    new_family_dois: dict[str, set[str]] = defaultdict(set)
    for row in discovery.get("rows", []):
        doi = normalize_doi(row.get("doi"))
        if not doi:
            continue
        families = {
            query_to_family.get(normalize(query), "unknown")
            for query in row.get("queries", []) or [row.get("query")]
        }
        for family in families:
            merged_family_dois[family].add(doi)
            if doi in new_dois:
                new_family_dois[family].add(doi)

    calibration_family_counts = Counter(normalize(row.get("family")) for row in calibration_seeds)
    full_family_counts = Counter(normalize(row.get("family")) for row in full_seeds)

    family_stats = {}
    for family in sorted(set(full_family_counts) | set(calibration_family_counts) | set(per_seed_by_family)):
        raw_values = per_seed_by_family.get(family, [])
        sample_seed_count = calibration_family_counts.get(family, 0)
        full_seed_count = full_family_counts.get(family, 0)
        raw_sum = sum(raw_values)
        family_stats[family] = {
            "full_seed_count": full_seed_count,
            "sample_seed_count": sample_seed_count,
            "raw_rows": raw_sum,
            "raw_rows_per_seed": numeric_summary(raw_values),
            "seeds_with_zero_rows": sum(1 for value in raw_values if value == 0),
            "seeds_at_result_cap": (
                sum(1 for value in raw_values if max_results_per_seed > 0 and value >= max_results_per_seed)
            ),
            "merged_unique_dois_mentioned": len(merged_family_dois.get(family, set())),
            "new_unique_dois_mentioned": len(new_family_dois.get(family, set())),
            "rough_openalex_raw_rows_if_full_seed_count": (
                round((raw_sum / sample_seed_count) * full_seed_count)
                if sample_seed_count
                else 0
            ),
        }

    counts = discovery.get("counts", {})
    gate_counts = add_new.get("counts", {})
    merged = int(counts.get("merged_rows") or 0)
    new = int(gate_counts.get("new_dois") or 0)
    raw = int(counts.get("raw_rows") or 0)
    sample_seed_count = int(counts.get("seed_count") or 0)

    return {
        "dataset": dataset,
        "provider": discovery.get("provider"),
        "settings": discovery.get("settings", {}),
        "source_seed_count": len(full_seeds),
        "sample_seed_count": sample_seed_count,
        "raw_rows": raw,
        "merged_rows": merged,
        "new_dois": new,
        "rediscovered_existing_dois": int(gate_counts.get("rediscovered_existing_dois") or 0),
        "new_doi_rate_among_merged": round(new / merged, 4) if merged else 0.0,
        "raw_rows_per_sample_seed": round(raw / sample_seed_count, 3) if sample_seed_count else 0.0,
        "merged_rows_per_sample_seed": round(merged / sample_seed_count, 3) if sample_seed_count else 0.0,
        "provider_errors": int(counts.get("provider_errors") or 0),
        "family_stats": family_stats,
        "new_doi_samples": add_new.get("new_doi_samples", [])[:10],
        "outputs": {
            "discovery_report": str(calibration_dir / f"{dataset}_discovery_report.json"),
            "add_new_dois_report": str(calibration_dir / f"{dataset}_add_new_dois_report.json"),
            "new_doi_queue": str(calibration_dir / f"{dataset}_new_dois.txt"),
        },
    }


def write_markdown(path: Path, summary: dict) -> None:
    lines = [
        "# Search Calibration Summary",
        "",
        f"- Generated: {summary['generated_at_utc']}",
        f"- Protocol: `{summary['protocol_id']}`",
        f"- Calibration directory: `{summary['calibration_dir']}`",
        "",
        "This is a calibration run, not the final baseline search. It estimates yield and noise from a small, reproducible seed slice.",
        "",
    ]
    for dataset, item in summary["datasets"].items():
        lines.extend(
            [
                f"## {dataset.title()}",
                "",
                f"- Provider: `{item['provider']}`",
                f"- Seeds sampled: {item['sample_seed_count']} of {item['source_seed_count']}",
                f"- Raw rows: {item['raw_rows']}",
                f"- Merged DOI rows: {item['merged_rows']}",
                f"- New DOIs after global DOI gate: {item['new_dois']}",
                f"- Rediscovered existing DOIs: {item['rediscovered_existing_dois']}",
                f"- New DOI rate among merged rows: {item['new_doi_rate_among_merged']:.1%}",
                "",
                "| Family | Sample seeds | Full seeds | Raw rows | Zero seeds | At cap | Merged DOI mentions | New DOI mentions | Rough raw rows if full OpenAlex sample settings |",
                "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for family, stats in item["family_stats"].items():
            lines.append(
                "| "
                + " | ".join(
                    [
                        family,
                        str(stats["sample_seed_count"]),
                        str(stats["full_seed_count"]),
                        str(stats["raw_rows"]),
                        str(stats["seeds_with_zero_rows"]),
                        str(stats["seeds_at_result_cap"]),
                        str(stats["merged_unique_dois_mentioned"]),
                        str(stats["new_unique_dois_mentioned"]),
                        str(stats["rough_openalex_raw_rows_if_full_seed_count"]),
                    ]
                )
                + " |"
            )
        lines.extend(["", "Representative new DOI samples:", ""])
        for sample in item["new_doi_samples"][:5]:
            title = normalize(sample.get("title")) or "(untitled)"
            doi = normalize(sample.get("doi"))
            lines.append(f"- `{doi}` - {title}")
        lines.append("")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize search calibration discovery outputs")
    parser.add_argument("--dataset", default="all", help="mechanistic, disorder, comma-separated list, or all")
    parser.add_argument(
        "--protocol-dir",
        default=str(ROOT / "data" / "raw" / "search_strategies" / PROTOCOL_ID),
    )
    parser.add_argument(
        "--calibration-dir",
        default=str(ROOT / "data" / "raw" / "search_strategies" / PROTOCOL_ID / "calibration" / "openalex"),
    )
    parser.add_argument("--summary-json", default="")
    parser.add_argument("--summary-md", default="")
    args = parser.parse_args()

    if args.dataset == "all":
        datasets = ["mechanistic", "disorder"]
    else:
        datasets = [item.strip() for item in args.dataset.split(",") if item.strip()]
    invalid = [item for item in datasets if item not in {"mechanistic", "disorder"}]
    if invalid:
        raise SystemExit(f"Invalid dataset(s): {', '.join(invalid)}")

    protocol_dir = Path(args.protocol_dir).resolve()
    calibration_dir = Path(args.calibration_dir).resolve()
    summary = {
        "version": VERSION,
        "protocol_id": PROTOCOL_ID,
        "generated_at_utc": now_utc(),
        "protocol_dir": str(protocol_dir),
        "calibration_dir": str(calibration_dir),
        "datasets": {
            dataset: summarize_dataset(
                dataset=dataset,
                protocol_dir=protocol_dir,
                calibration_dir=calibration_dir,
            )
            for dataset in datasets
        },
    }

    summary_json = Path(args.summary_json).resolve() if args.summary_json else calibration_dir / "calibration_summary.json"
    summary_md = Path(args.summary_md).resolve() if args.summary_md else calibration_dir / "calibration_summary.md"
    write_json(summary_json, summary)
    write_markdown(summary_md, summary)

    print(f"Summary JSON: {summary_json}")
    print(f"Summary Markdown: {summary_md}")
    for dataset, item in summary["datasets"].items():
        print(
            f"{dataset}: seeds={item['sample_seed_count']} raw={item['raw_rows']} "
            f"merged={item['merged_rows']} new={item['new_dois']} "
            f"new_rate={item['new_doi_rate_among_merged']:.1%}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
