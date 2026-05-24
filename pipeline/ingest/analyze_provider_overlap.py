#!/usr/bin/env python3
"""Audit overlap and title-level signal between discovery providers."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import re
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RUN_ID = "literature_search"
SEARCH_STRATEGY_ROOT = ROOT / "data" / "raw" / "search_strategies"
VERSION = "0.1"

COMPOUND_PATTERNS = [
    r"\bpsychedelic(?:s)?\b",
    r"\bhallucinogen(?:s)?\b",
    r"\bpsychoplastogen(?:s)?\b",
    r"\bpsilocybin\b",
    r"\bpsilocin\b",
    r"\blsd\b",
    r"\blysergic acid diethylamide\b",
    r"\bmdma\b",
    r"\b3,4-methylenedioxymethamphetamine\b",
    r"\bmda\b",
    r"\bketamine\b",
    r"\besketamine\b",
    r"\barketamine\b",
    r"\bayahuasca\b",
    r"\bdmt\b",
    r"\b5-meo-dmt\b",
    r"\bmescaline\b",
    r"\bibogaine\b",
    r"\bnoribogaine\b",
    r"\bsalvinorin\b",
    r"\b2c-b\b",
    r"\bnbome\b",
]

MECHANISTIC_PATTERNS = [
    r"\b5-ht[0-9a-z]*\b",
    r"\bhtr[0-9a-z]*\b",
    r"\bserotonin\b",
    r"\breceptor(?:s)?\b",
    r"\btransporter(?:s)?\b",
    r"\bsert\b",
    r"\bdat\b",
    r"\bnet\b",
    r"\bslc6a[234]\b",
    r"\bnmda\b",
    r"\bnmdar\b",
    r"\bampa\b",
    r"\bglutamate\b",
    r"\bopioid\b",
    r"\bkappa\b",
    r"\bsigma-?1\b",
    r"\btaar1\b",
    r"\btrkb\b",
    r"\bbdnf\b",
    r"\bneuroplasticity\b",
    r"\bplasticity\b",
    r"\bdendritic\b",
    r"\bsynaptic\b",
    r"\bbinding\b",
    r"\baffinity\b",
    r"\bagonist(?:s)?\b",
    r"\bantagonist(?:s)?\b",
    r"\bpharmacology\b",
]

DISORDER_PATTERNS = [
    r"\bdepress(?:ion|ive)\b",
    r"\banxiety\b",
    r"\bptsd\b",
    r"\bpost[- ]traumatic stress\b",
    r"\btrauma\b",
    r"\bsubstance use\b",
    r"\baddiction\b",
    r"\bdependence\b",
    r"\balcohol\b",
    r"\btobacco\b",
    r"\bsmoking\b",
    r"\bopioid\b",
    r"\bcocaine\b",
    r"\bmethamphetamine\b",
    r"\bocd\b",
    r"\bobsessive[- ]compulsive\b",
    r"\beating disorder\b",
    r"\banorexia\b",
    r"\bbulimia\b",
    r"\bautism\b",
    r"\bmigraine\b",
    r"\bheadache\b",
    r"\bpain\b",
    r"\bfibromyalgia\b",
    r"\bpalliative\b",
    r"\bend-of-life\b",
    r"\bsuicid(?:al|ality)\b",
    r"\bbipolar\b",
    r"\bclinical trial\b",
    r"\brandomi[sz]ed\b",
    r"\btreatment\b",
    r"\btherapy\b",
    r"\befficacy\b",
    r"\bsafety\b",
]

SECONDARY_PATTERNS = [
    r"\breview\b",
    r"\boverview\b",
    r"\bperspective(?:s)?\b",
    r"\bcommentary\b",
    r"\beditorial\b",
    r"\bguideline(?:s)?\b",
    r"\bframework\b",
    r"\bregulatory\b",
    r"\bprotocol\b",
    r"\bmanual\b",
]


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


def compile_patterns(patterns: Iterable[str]) -> list[re.Pattern[str]]:
    return [re.compile(pattern, re.IGNORECASE) for pattern in patterns]


COMPOUND_REGEXES = compile_patterns(COMPOUND_PATTERNS)
MECHANISTIC_REGEXES = compile_patterns(MECHANISTIC_PATTERNS)
DISORDER_REGEXES = compile_patterns(DISORDER_PATTERNS)
SECONDARY_REGEXES = compile_patterns(SECONDARY_PATTERNS)


def read_json(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Missing JSON file: {path}")
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


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


def read_query_module_map(path: Path) -> dict[str, str]:
    if not path.exists():
        raise FileNotFoundError(f"Missing seed file: {path}")
    out = {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            query = normalize(row.get("query"))
            module_id = normalize(row.get("module_id")) or "unknown"
            if query:
                out[query] = module_id
    return out


def provider_seed_path(run_root: Path, dataset: str, provider: str) -> Path:
    grouped_path = run_root / f"{dataset}_grouped_{provider}_seeds.csv"
    if grouped_path.exists():
        return grouped_path
    return run_root / f"{dataset}_boolean_{provider}_seeds.csv"


def read_rows(path: Path) -> dict[str, dict]:
    report = read_json(path)
    rows: dict[str, dict] = {}
    for row in report.get("rows", []):
        doi = normalize_doi(row.get("doi"))
        if not doi or doi in rows:
            continue
        rows[doi] = {
            "doi": doi,
            "title": normalize(row.get("title")),
            "year": normalize(row.get("year")),
            "authors": normalize(row.get("authors")),
            "provider": normalize(row.get("provider")),
            "query": normalize(row.get("query")),
        }
    return rows


def read_module_new_dois(
    run_root: Path,
    seed_dir: Path,
    run_dir: str,
    dataset: str,
    provider: str,
    new_dois: set[str],
) -> dict[str, set[str]]:
    rows_report = read_json(run_root / run_dir / f"{dataset}_discovery_report.json")
    query_to_module = read_query_module_map(provider_seed_path(seed_dir, dataset, provider))
    out: dict[str, set[str]] = {}
    for row in rows_report.get("rows", []):
        doi = normalize_doi(row.get("doi"))
        if doi not in new_dois:
            continue
        queries = row.get("queries") or [row.get("query")]
        for query in queries:
            module_id = query_to_module.get(normalize(query), "unknown")
            out.setdefault(module_id, set()).add(doi)
    return out


def match_any(regexes: list[re.Pattern[str]], text: str) -> bool:
    return any(regex.search(text) for regex in regexes)


def classify_title(dataset: str, title: str) -> dict:
    entity_regexes = MECHANISTIC_REGEXES if dataset == "mechanistic" else DISORDER_REGEXES
    has_compound = match_any(COMPOUND_REGEXES, title)
    has_entity = match_any(entity_regexes, title)
    has_secondary = match_any(SECONDARY_REGEXES, title)
    return {
        "title_has_compound": has_compound,
        "title_has_entity_or_context": has_entity,
        "title_has_both": has_compound and has_entity,
        "title_has_neither": not has_compound and not has_entity,
        "title_looks_secondary": has_secondary,
    }


def title_proxy_counts(dataset: str, rows: dict[str, dict], dois: set[str]) -> dict:
    counts = {
        "doi_count": len(dois),
        "title_has_compound": 0,
        "title_has_entity_or_context": 0,
        "title_has_both": 0,
        "title_has_neither": 0,
        "title_looks_secondary": 0,
    }
    for doi in dois:
        title = rows.get(doi, {}).get("title", "")
        flags = classify_title(dataset, title)
        for key, value in flags.items():
            counts[key] += int(bool(value))
    return counts


def pct(value: int, total: int) -> float:
    return round((100.0 * value / total), 1) if total else 0.0


def sample_rows(dataset: str, rows: dict[str, dict], dois: set[str], mode: str, limit: int = 8) -> list[dict]:
    selected = []
    for doi in sorted(dois):
        row = rows.get(doi, {"doi": doi, "title": ""})
        flags = classify_title(dataset, row.get("title", ""))
        if mode == "high_signal" and not flags["title_has_both"]:
            continue
        if mode == "possible_noise" and not flags["title_has_neither"]:
            continue
        if mode == "secondary" and not flags["title_looks_secondary"]:
            continue
        selected.append(
            {
                "doi": doi,
                "title": row.get("title", ""),
                "year": row.get("year", ""),
                "flags": flags,
            }
        )
        if len(selected) >= limit:
            break
    return selected


def analyze_dataset(
    run_root: Path,
    dataset: str,
    openalex_dir: str,
    pubmed_dir: str,
    seed_dir: Path | None = None,
) -> dict:
    seed_dir = seed_dir or run_root
    provider_dirs = {"openalex": run_root / openalex_dir, "pubmed": run_root / pubmed_dir}
    rows = {
        provider: read_rows(provider_dir / f"{dataset}_discovery_report.json")
        for provider, provider_dir in provider_dirs.items()
    }
    discovered = {provider: set(provider_rows) for provider, provider_rows in rows.items()}
    new_dois = {
        provider: read_queue_dois(provider_dir / f"{dataset}_new_dois.txt")
        for provider, provider_dir in provider_dirs.items()
    }

    all_overlap = discovered["openalex"] & discovered["pubmed"]
    new_overlap = new_dois["openalex"] & new_dois["pubmed"]
    openalex_only_new = new_dois["openalex"] - new_dois["pubmed"]
    pubmed_only_new = new_dois["pubmed"] - new_dois["openalex"]
    module_new = {
        "openalex": read_module_new_dois(run_root, seed_dir, openalex_dir, dataset, "openalex", new_dois["openalex"]),
        "pubmed": read_module_new_dois(run_root, seed_dir, pubmed_dir, dataset, "pubmed", new_dois["pubmed"]),
    }

    provider_metrics = {}
    for provider in ["openalex", "pubmed"]:
        provider_metrics[provider] = {
            "discovered_unique_dois": len(discovered[provider]),
            "new_dois": len(new_dois[provider]),
            "title_proxy_all_discovered": title_proxy_counts(dataset, rows[provider], discovered[provider]),
            "title_proxy_new_dois": title_proxy_counts(dataset, rows[provider], new_dois[provider]),
        }

    return {
        "dataset": dataset,
        "providers": provider_metrics,
        "overlap": {
            "all_discovered_overlap": len(all_overlap),
            "openalex_only_discovered": len(discovered["openalex"] - discovered["pubmed"]),
            "pubmed_only_discovered": len(discovered["pubmed"] - discovered["openalex"]),
            "new_doi_overlap": len(new_overlap),
            "openalex_only_new_dois": len(openalex_only_new),
            "pubmed_only_new_dois": len(pubmed_only_new),
            "combined_new_dois": len(new_dois["openalex"] | new_dois["pubmed"]),
        },
        "exclusive_new_title_proxy": {
            "openalex_only": title_proxy_counts(dataset, rows["openalex"], openalex_only_new),
            "pubmed_only": title_proxy_counts(dataset, rows["pubmed"], pubmed_only_new),
        },
        "module_new_overlap": [
            {
                "module_id": module_id,
                "openalex_new_dois": len(module_new["openalex"].get(module_id, set())),
                "pubmed_new_dois": len(module_new["pubmed"].get(module_id, set())),
                "new_doi_overlap": len(
                    module_new["openalex"].get(module_id, set()) & module_new["pubmed"].get(module_id, set())
                ),
                "openalex_only_new_dois": len(
                    module_new["openalex"].get(module_id, set()) - module_new["pubmed"].get(module_id, set())
                ),
                "pubmed_only_new_dois": len(
                    module_new["pubmed"].get(module_id, set()) - module_new["openalex"].get(module_id, set())
                ),
            }
            for module_id in sorted(set(module_new["openalex"]) | set(module_new["pubmed"]))
        ],
        "samples": {
            "openalex_only_high_signal": sample_rows(dataset, rows["openalex"], openalex_only_new, "high_signal"),
            "openalex_only_possible_noise": sample_rows(dataset, rows["openalex"], openalex_only_new, "possible_noise"),
            "openalex_only_secondary": sample_rows(dataset, rows["openalex"], openalex_only_new, "secondary"),
            "pubmed_only_high_signal": sample_rows(dataset, rows["pubmed"], pubmed_only_new, "high_signal"),
            "pubmed_only_possible_noise": sample_rows(dataset, rows["pubmed"], pubmed_only_new, "possible_noise"),
            "pubmed_only_secondary": sample_rows(dataset, rows["pubmed"], pubmed_only_new, "secondary"),
        },
    }


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def format_proxy(counts: dict) -> str:
    total = int(counts.get("doi_count") or 0)
    return (
        f"{counts.get('title_has_both', 0)}/{total} both ({pct(int(counts.get('title_has_both', 0)), total)}%), "
        f"{counts.get('title_has_neither', 0)}/{total} neither ({pct(int(counts.get('title_has_neither', 0)), total)}%), "
        f"{counts.get('title_looks_secondary', 0)}/{total} secondary-ish "
        f"({pct(int(counts.get('title_looks_secondary', 0)), total)}%)"
    )


def write_markdown(path: Path, summary: dict) -> None:
    lines = [
        "# Provider Overlap And Title-Signal Audit",
        "",
        f"- Generated: {summary['generated_at_utc']}",
        f"- Run: `{summary['run_id']}`",
        f"- OpenAlex run: `{summary['openalex_dir']}`",
        f"- PubMed run: `{summary['pubmed_dir']}`",
        "",
        "This is a title-level proxy audit, not final relevance screening. It is useful for comparing provider behavior and surfacing obvious noise patterns.",
        "",
    ]
    for dataset, item in summary["datasets"].items():
        overlap = item["overlap"]
        lines.extend([f"## {dataset}", ""])
        lines.append("| Metric | Count |")
        lines.append("| --- | ---: |")
        for key in [
            "all_discovered_overlap",
            "openalex_only_discovered",
            "pubmed_only_discovered",
            "new_doi_overlap",
            "openalex_only_new_dois",
            "pubmed_only_new_dois",
            "combined_new_dois",
        ]:
            lines.append(f"| {key} | {overlap[key]} |")
        lines.append("")
        lines.append("| Provider | Discovered DOIs | New DOIs | Title proxy among new DOIs |")
        lines.append("| --- | ---: | ---: | --- |")
        for provider, provider_item in item["providers"].items():
            lines.append(
                f"| {provider} | {provider_item['discovered_unique_dois']} | {provider_item['new_dois']} | "
                f"{format_proxy(provider_item['title_proxy_new_dois'])} |"
            )
        lines.append("")
        lines.append("| Exclusive-new set | Title proxy |")
        lines.append("| --- | --- |")
        for provider_label, counts in item["exclusive_new_title_proxy"].items():
            lines.append(f"| {provider_label} | {format_proxy(counts)} |")
        lines.append("")
        lines.append("| Module | OpenAlex new | PubMed new | New overlap | OpenAlex only | PubMed only |")
        lines.append("| --- | ---: | ---: | ---: | ---: | ---: |")
        for module in item["module_new_overlap"]:
            lines.append(
                f"| {module['module_id']} | {module['openalex_new_dois']} | {module['pubmed_new_dois']} | "
                f"{module['new_doi_overlap']} | {module['openalex_only_new_dois']} | "
                f"{module['pubmed_only_new_dois']} |"
            )
        lines.append("")
        for sample_name, rows in item["samples"].items():
            if not rows:
                continue
            lines.extend([f"### {dataset} / {sample_name}", ""])
            for row in rows:
                year = f" ({row['year']})" if row.get("year") else ""
                lines.append(f"- `{row['doi']}`{year} - {row.get('title', '')}")
            lines.append("")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare OpenAlex and PubMed discovery outputs")
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID, help="Run label used when --run-root is not supplied")
    parser.add_argument("--search-root", default=str(SEARCH_STRATEGY_ROOT), help="Root directory for search artifacts")
    parser.add_argument(
        "--run-root",
        default="",
        help="Directory containing grouped search seeds and provider run outputs. Defaults to <search-root>/<run-id>/grouped_module_run.",
    )
    parser.add_argument(
        "--seed-dir",
        default="",
        help="Directory containing grouped search-module seed files. Defaults to <search-root>/<run-id>/grouped_modules.",
    )
    parser.add_argument("--openalex-dir", default="openalex_100")
    parser.add_argument("--pubmed-dir", default="pubmed_100")
    parser.add_argument("--summary-json", default="")
    parser.add_argument("--summary-md", default="")
    args = parser.parse_args()

    search_root = Path(args.search_root).resolve()
    run_root = Path(args.run_root).resolve() if args.run_root else search_root / args.run_id / "grouped_module_run"
    seed_dir = Path(args.seed_dir).resolve() if args.seed_dir else search_root / args.run_id / "grouped_modules"
    summary = {
        "version": VERSION,
        "run_id": args.run_id,
        "protocol_id": args.run_id,
        "generated_at_utc": now_utc(),
        "run_root": str(run_root),
        "seed_dir": str(seed_dir),
        "openalex_dir": args.openalex_dir,
        "pubmed_dir": args.pubmed_dir,
        "datasets": {
            dataset: analyze_dataset(run_root, dataset, args.openalex_dir, args.pubmed_dir, seed_dir=seed_dir)
            for dataset in ["mechanistic", "disorder"]
        },
    }

    summary_json = Path(args.summary_json).resolve() if args.summary_json else run_root / "provider_overlap_analysis.json"
    summary_md = Path(args.summary_md).resolve() if args.summary_md else run_root / "provider_overlap_analysis.md"
    write_json(summary_json, summary)
    write_markdown(summary_md, summary)

    print(f"Summary JSON: {summary_json}")
    print(f"Summary Markdown: {summary_md}")
    for dataset, item in summary["datasets"].items():
        overlap = item["overlap"]
        print(
            f"{dataset}: combined_new={overlap['combined_new_dois']} "
            f"openalex_only_new={overlap['openalex_only_new_dois']} "
            f"pubmed_only_new={overlap['pubmed_only_new_dois']} "
            f"new_overlap={overlap['new_doi_overlap']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
