#!/usr/bin/env python3
"""Summarize Boolean-module discovery runs by provider, dataset, and module."""

from __future__ import annotations

import argparse
from collections import defaultdict
import csv
import datetime as dt
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROTOCOL_ID = "comprehensive_baseline_v1"
VERSION = "0.1"


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def normalize(value: object) -> str:
    return "" if value is None else str(value).strip()


def normalize_doi(value: object) -> str:
    text = normalize(value).lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/", "http://dx.doi.org/", "doi:"):
        if text.startswith(prefix):
            return text[len(prefix) :].strip()
    return text


def read_json(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Missing JSON file: {path}")
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


def read_seed_rows(path: Path) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(f"Missing seed file: {path}")
    with path.open("r", encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def read_queue_dois(path: Path) -> set[str]:
    if not path.exists():
        return set()
    dois = set()
    with path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.reader(handle):
            if not row:
                continue
            first = normalize(row[0])
            if not first or first.startswith("#") or first.lower() in {"doi", "study_doi"}:
                continue
            doi = normalize_doi(first)
            if doi:
                dois.add(doi)
    return dois


def query_module_maps(seed_rows: list[dict]) -> tuple[dict[str, str], dict[str, str]]:
    query_to_module = {}
    query_to_type = {}
    for row in seed_rows:
        query = normalize(row.get("query"))
        if not query:
            continue
        query_to_module[query] = normalize(row.get("module_id")) or "unknown"
        query_to_type[query] = normalize(row.get("module_type")) or "unknown"
    return query_to_module, query_to_type


def summarize_run(seed_dir: Path, run_dir: Path, dataset: str, provider_profile: str) -> dict:
    seed_rows = read_seed_rows(seed_dir / f"{dataset}_boolean_{provider_profile}_seeds.csv")
    query_to_module, query_to_type = query_module_maps(seed_rows)
    discovery = read_json(run_dir / f"{dataset}_discovery_report.json")
    add_new = read_json(run_dir / f"{dataset}_add_new_dois_report.json")
    new_dois = read_queue_dois(run_dir / f"{dataset}_new_dois.txt")

    module_raw_rows = {}
    for row in discovery.get("per_seed", []):
        query = normalize(row.get("query"))
        module_id = query_to_module.get(query, "unknown")
        module_raw_rows[module_id] = int(row.get("rows_retrieved") or 0)

    module_dois: dict[str, set[str]] = defaultdict(set)
    module_new_dois: dict[str, set[str]] = defaultdict(set)
    for row in discovery.get("rows", []):
        doi = normalize_doi(row.get("doi"))
        if not doi:
            continue
        queries = row.get("queries") or [row.get("query")]
        for query in queries:
            module_id = query_to_module.get(normalize(query), "unknown")
            module_dois[module_id].add(doi)
            if doi in new_dois:
                module_new_dois[module_id].add(doi)

    modules = []
    for seed in seed_rows:
        module_id = normalize(seed.get("module_id")) or "unknown"
        modules.append(
            {
                "module_id": module_id,
                "module_type": query_to_type.get(normalize(seed.get("query")), normalize(seed.get("module_type"))),
                "raw_rows": module_raw_rows.get(module_id, 0),
                "merged_unique_dois_mentioned": len(module_dois.get(module_id, set())),
                "new_unique_dois_mentioned": len(module_new_dois.get(module_id, set())),
            }
        )

    counts = discovery.get("counts", {})
    gate_counts = add_new.get("counts", {})
    return {
        "dataset": dataset,
        "provider_profile": provider_profile,
        "run_dir": str(run_dir),
        "seed_count": int(counts.get("seed_count") or 0),
        "raw_rows": int(counts.get("raw_rows") or 0),
        "merged_rows": int(counts.get("merged_rows") or 0),
        "new_dois": int(gate_counts.get("new_dois") or 0),
        "rediscovered_existing_dois": int(gate_counts.get("rediscovered_existing_dois") or 0),
        "missing_or_invalid_dois": int(gate_counts.get("missing_or_invalid_dois") or 0),
        "modules": modules,
        "new_doi_samples": add_new.get("new_doi_samples", [])[:10],
    }


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_markdown(path: Path, summary: dict) -> None:
    lines = [
        "# Boolean Module Discovery Summary",
        "",
        f"- Generated: {summary['generated_at_utc']}",
        f"- Protocol: `{summary['protocol_id']}`",
        "",
    ]
    for provider, provider_summary in summary["providers"].items():
        lines.extend([f"## {provider}", ""])
        lines.append("| Dataset | Seeds | Raw rows | Merged DOI rows | New DOIs | Rediscovered |")
        lines.append("| --- | ---: | ---: | ---: | ---: | ---: |")
        for dataset, item in provider_summary["datasets"].items():
            lines.append(
                f"| {dataset} | {item['seed_count']} | {item['raw_rows']} | "
                f"{item['merged_rows']} | {item['new_dois']} | {item['rediscovered_existing_dois']} |"
            )
        lines.append("")
        for dataset, item in provider_summary["datasets"].items():
            lines.extend([f"### {provider} / {dataset}", ""])
            lines.append("| Module | Type | Raw rows | Merged DOI mentions | New DOI mentions |")
            lines.append("| --- | --- | ---: | ---: | ---: |")
            for module in item["modules"]:
                lines.append(
                    f"| {module['module_id']} | {module['module_type']} | {module['raw_rows']} | "
                    f"{module['merged_unique_dois_mentioned']} | {module['new_unique_dois_mentioned']} |"
                )
            lines.extend(["", "Representative new DOI samples:", ""])
            for sample in item["new_doi_samples"][:5]:
                lines.append(f"- `{sample.get('doi', '')}` - {sample.get('title', '')}")
            lines.append("")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def parse_providers(raw: str) -> list[str]:
    providers = [item.strip() for item in raw.split(",") if item.strip()]
    invalid = [item for item in providers if item not in {"openalex", "pubmed"}]
    if invalid:
        raise ValueError(f"Invalid provider profile(s): {', '.join(invalid)}")
    return providers or ["openalex", "pubmed"]


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize Boolean module discovery runs")
    parser.add_argument(
        "--seed-dir",
        default=str(ROOT / "data" / "raw" / "search_strategies" / PROTOCOL_ID / "boolean_modules"),
    )
    parser.add_argument(
        "--run-root",
        default=str(ROOT / "data" / "raw" / "search_strategies" / PROTOCOL_ID / "boolean_modules"),
    )
    parser.add_argument("--providers", default="openalex,pubmed")
    parser.add_argument("--summary-json", default="")
    parser.add_argument("--summary-md", default="")
    args = parser.parse_args()

    seed_dir = Path(args.seed_dir).resolve()
    run_root = Path(args.run_root).resolve()
    try:
        providers = parse_providers(args.providers)
    except ValueError as err:
        raise SystemExit(str(err))

    run_dirs = {
        "openalex": run_root / "openalex_100",
        "pubmed": run_root / "pubmed_100",
    }
    summary = {
        "version": VERSION,
        "protocol_id": PROTOCOL_ID,
        "generated_at_utc": now_utc(),
        "seed_dir": str(seed_dir),
        "providers": {},
    }
    for provider in providers:
        summary["providers"][provider] = {
            "run_dir": str(run_dirs[provider]),
            "datasets": {
                dataset: summarize_run(seed_dir, run_dirs[provider], dataset, provider)
                for dataset in ["mechanistic", "disorder"]
            },
        }

    summary_json = Path(args.summary_json).resolve() if args.summary_json else run_root / "boolean_module_run_summary.json"
    summary_md = Path(args.summary_md).resolve() if args.summary_md else run_root / "boolean_module_run_summary.md"
    write_json(summary_json, summary)
    write_markdown(summary_md, summary)

    print(f"Summary JSON: {summary_json}")
    print(f"Summary Markdown: {summary_md}")
    for provider, provider_summary in summary["providers"].items():
        for dataset, item in provider_summary["datasets"].items():
            print(
                f"{provider}/{dataset}: seeds={item['seed_count']} raw={item['raw_rows']} "
                f"merged={item['merged_rows']} new={item['new_dois']}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
