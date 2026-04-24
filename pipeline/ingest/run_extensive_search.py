#!/usr/bin/env python3
"""Run high-volume literature discovery and paper-library sync."""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parents[2]


def parse_key_values(stdout: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for raw in stdout.splitlines():
        line = raw.strip()
        if not line or ":" not in line:
            continue
        key, value = line.split(":", 1)
        out[key.strip().lower()] = value.strip()
    return out


def as_rel_path(value: str) -> str:
    text = value.strip()
    if not text:
        return text
    try:
        path = Path(text)
    except Exception:
        return text

    if not path.is_absolute():
        return text
    try:
        return str(path.resolve().relative_to(ROOT))
    except Exception:
        return text


def print_header(
    datasets: List[str],
    provider: str,
    max_results_per_seed: int,
    max_results: int,
    discover_only: bool,
    sync_only: bool,
    skip_download: bool,
    expand_seeds_from_config: bool,
    auto_seeds_only: bool,
    auto_template_mode: str,
    auto_max_compounds: int,
    auto_max_entities: int,
    auto_max_pairs: int,
    auto_max_seeds: int,
    balanced_seed_profile: str,
    balanced_max_compounds: int,
    balanced_max_entities: int,
    balanced_max_seeds: int,
    query_variant_mode: str,
    citation_chase: str,
    citation_chase_directions: str,
    citation_chase_max_source_dois: int,
    citation_chase_max_results_per_doi: int,
    semantic_scholar_rps: float | None,
    openalex_rps: float | None,
    max_retries: int | None,
    recall_gate: bool,
    min_discovered_recall: float,
    min_triage_recall: float,
    benchmark_manifest: Path,
    disable_protected_retention: bool,
    disable_ledger: bool,
) -> None:
    print("=== Extensive Literature Run ===")
    print(f"Datasets: {', '.join(datasets)}")
    print(f"Provider: {provider}")
    print(f"Max results per seed: {max_results_per_seed}")
    print(f"Max merged results per dataset: {max_results}")
    if expand_seeds_from_config or auto_seeds_only:
        print(
            "Seed expansion: "
            f"auto={'on' if expand_seeds_from_config else 'off'} "
            f"auto-only={'yes' if auto_seeds_only else 'no'} "
            f"template={auto_template_mode} "
            f"max-compounds={auto_max_compounds} "
            f"max-entities={auto_max_entities} "
            f"max-pairs={auto_max_pairs} "
            f"max-seeds={auto_max_seeds}"
        )
    else:
        print("Seed expansion: off (default seeds unless explicit --seed/--query)")
    if balanced_seed_profile != "off":
        print(
            "Balanced seeds: "
            f"profile={balanced_seed_profile} "
            f"max-compounds={balanced_max_compounds} "
            f"max-entities={balanced_max_entities} "
            f"max-seeds={balanced_max_seeds}"
        )
    else:
        print("Balanced seeds: off")
    print(f"Query variants: {query_variant_mode}")
    if citation_chase != "off":
        print(
            "Citation chasing: "
            f"source={citation_chase} directions={citation_chase_directions} "
            f"source-dois={citation_chase_max_source_dois} "
            f"results-per-doi={citation_chase_max_results_per_doi}"
        )
    else:
        print("Citation chasing: off")
    if semantic_scholar_rps is not None or openalex_rps is not None or max_retries is not None:
        print(
            "Rate/retry overrides: "
            f"s2-rps={semantic_scholar_rps if semantic_scholar_rps is not None else 'config/default'} "
            f"oa-rps={openalex_rps if openalex_rps is not None else 'config/default'} "
            f"max-retries={max_retries if max_retries is not None else 'config/default'}"
        )
    if discover_only:
        print("Mode: discovery only")
    elif sync_only:
        print("Mode: paper sync only")
    else:
        print("Mode: discovery + paper sync")
    if discover_only:
        print("PDF download: n/a (discovery only)")
    else:
        print(f"PDF download: {'disabled (--skip-download)' if skip_download else 'enabled'}")
    if not discover_only:
        print(
            "Download strategy: "
            + ("triage-first (metadata sync -> triage -> download sync)" if not skip_download else "metadata-only (no downloads)")
        )
    if recall_gate:
        print(
            "Recall gate: "
            f"enabled (discovered>={min_discovered_recall}%, triage>={min_triage_recall}%)"
        )
    print(f"Known relevant study set: {as_rel_path(str(benchmark_manifest))}")
    print(f"Protected retention: {'disabled' if disable_protected_retention else 'enabled'}")
    print(f"Discovery ledger: {'disabled' if disable_ledger else 'enabled'}")
    print("")


def run_step(
    cmd: List[str],
    label: str,
    verbose: bool,
) -> Dict[str, str]:
    start = time.monotonic()
    print(f"[{label}] Running...", flush=True)
    if verbose:
        print(f"[{label}] COMMAND")
        print("  " + " ".join(cmd))

    proc = subprocess.Popen(
        cmd,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=1,
    )

    output_lines: List[str] = []
    assert proc.stdout is not None
    for raw_line in proc.stdout:
        line = raw_line.rstrip("\n")
        output_lines.append(line)
        if line.startswith("PROGRESS:"):
            print(f"[{label}] {line[len('PROGRESS:'):].strip()}", flush=True)
        elif verbose:
            print(f"[{label}] {line}", flush=True)
    return_code = proc.wait()
    stdout = "\n".join(output_lines)

    if return_code != 0:
        print(f"[{label}] FAILED (exit {return_code})")
        if stdout.strip():
            print("  stdout:")
            for line in stdout.splitlines():
                print(f"    {line}")
        raise SystemExit(return_code)

    elapsed_sec = time.monotonic() - start
    print(f"[{label}] Done in {elapsed_sec:.1f}s", flush=True)
    return parse_key_values(stdout)


def parse_datasets(raw: str) -> List[str]:
    value = raw.strip().lower()
    if value == "all":
        return ["mechanistic", "disorder"]
    items = [token.strip() for token in value.split(",") if token.strip()]
    allowed = {"mechanistic", "disorder"}
    invalid = [item for item in items if item not in allowed]
    if invalid:
        raise ValueError(f"Invalid dataset(s): {invalid}; allowed: mechanistic, disorder, all")
    if not items:
        raise ValueError("At least one dataset is required")
    return items


def print_discovery_summary(dataset: str, info: Dict[str, str]) -> None:
    seeds = info.get("seeds", "?")
    seed_sources = info.get("seed sources", "")
    raw_rows = info.get("raw rows", "?")
    merged_rows = info.get("merged rows", "?")
    queue = as_rel_path(info.get("queue", ""))
    report = as_rel_path(info.get("report", ""))
    ledger = as_rel_path(info.get("ledger", ""))
    print(f"[{dataset}] Discovery complete")
    print(f"  Seeds: {seeds} | Raw rows: {raw_rows} | Merged rows: {merged_rows}")
    if seed_sources:
        print(f"  Seed sources: {seed_sources}")
    if queue:
        print(f"  Queue: {queue}")
    if report:
        print(f"  Report: {report}")
    if ledger:
        print(f"  Ledger: {ledger}")
    print("")


def print_sync_summary(dataset: str, info: Dict[str, str], phase: str = "paper sync") -> None:
    doi_rows = info.get("doi queue rows read", "?")
    unique = info.get("unique papers", "?")
    in_db = info.get("in database", "?")
    needs_download = info.get("needs download", "?")
    needs_manual = info.get("needs manual access", "?")
    downloaded_now = info.get("downloaded now", "?")
    already_present = info.get("already present", "?")
    failures = info.get("download failures", "?")

    paper_db = as_rel_path(info.get("paper db json", ""))
    inventory_json = as_rel_path(info.get("inventory report json", ""))
    inventory_md = as_rel_path(info.get("inventory markdown", ""))

    print(f"[{dataset}] {phase} complete")
    print(f"  DOI rows: {doi_rows} | Unique papers: {unique}")
    print(
        "  PDF status: "
        f"in DB={in_db}, needs download={needs_download}, needs manual access={needs_manual}"
    )
    print(
        "  This run: "
        f"downloaded={downloaded_now}, already present={already_present}, failures={failures}"
    )
    if paper_db:
        print(f"  Library DB: {paper_db}")
    if inventory_json:
        print(f"  Inventory (JSON): {inventory_json}")
    if inventory_md:
        print(f"  Inventory (Markdown): {inventory_md}")
    print("")


def print_triage_summary(dataset: str, info: Dict[str, str]) -> None:
    triaged = info.get("papers triaged", "?")
    relevance = info.get("relevance counts", "?")
    sources = info.get("source-type suggestions", "?")
    queue_rows = info.get("filtered queue rows", "?")
    queue = as_rel_path(info.get("filtered queue", ""))
    report_json = as_rel_path(info.get("report json", ""))
    print(f"[{dataset}] Triage complete")
    print(f"  Papers triaged: {triaged}")
    print(f"  Relevance: {relevance}")
    print(f"  Source type suggestions: {sources}")
    print(f"  Filtered queue rows: {queue_rows}")
    if queue:
        print(f"  Triage queue: {queue}")
    if report_json:
        print(f"  Report: {report_json}")
    print("")


def run_recall_gate(
    dataset: str,
    python_exe: str,
    benchmark_manifest: Path,
    min_discovered_recall: float,
    min_triage_recall: float,
    verbose: bool,
    phase: str,
) -> None:
    cmd = [
        python_exe,
        str(ROOT / "pipeline" / "ingest" / "recall_audit.py"),
        "--dataset",
        dataset,
        "--known-study-manifest",
        str(benchmark_manifest),
        "--min-discovered",
        str(min_discovered_recall),
        "--fail-under-threshold",
    ]
    if min_triage_recall > 0:
        cmd.extend(["--min-triage", str(min_triage_recall)])

    run_step(
        cmd,
        label=f"{dataset} / recall-gate-{phase}",
        verbose=verbose,
    )


def print_final_summary(datasets: List[str]) -> None:
    print("=== Run Complete ===")
    for dataset in datasets:
        print(f"[{dataset}]")
        print(f"  Queue: data/raw/doi_queue.{dataset}.discovered.txt")
        print(f"  Triage queue: data/raw/doi_queue.{dataset}.triage_relevant.txt")
        print(f"  Ledger: data/processed/discovery_ledger_{dataset}.json")
        print(f"  PDFs: data/raw/papers/{dataset}/pdfs/")
        print(f"  Inventory: data/processed/paper_inventory_{dataset}.md")
    print("")


def print_step_intro(dataset: str, step_number: str, title: str, details: List[str]) -> None:
    print(f"[{dataset}] {step_number}: {title}")
    for detail in details:
        print(f"  - {detail}")
    print("  - status: starting now...")
    print("")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run extensive discovery and paper-library sync for one or both datasets",
    )
    parser.add_argument(
        "--dataset",
        default="all",
        help="mechanistic, disorder, comma-separated list, or all (default)",
    )
    parser.add_argument(
        "--provider",
        choices=[
            "semantic_scholar",
            "openalex",
            "hybrid",
            "pubmed",
            "pmc",
            "crossref",
            "biomedical",
            "comprehensive",
        ],
        default="hybrid",
        help="Discovery provider (default: hybrid)",
    )
    parser.add_argument("--max-results-per-seed", type=int, default=100)
    parser.add_argument("--max-results", type=int, default=600)
    parser.add_argument(
        "--expand-seeds-from-config",
        action="store_true",
        help="Generate extra discovery seeds from allowlists in config",
    )
    parser.add_argument(
        "--auto-seeds-only",
        action="store_true",
        help="Use only auto-generated seeds (skip defaults unless manual --seed/--query used)",
    )
    parser.add_argument(
        "--auto-template-mode",
        choices=["focused", "broad"],
        default="focused",
        help="Template breadth for auto-generated seeds",
    )
    parser.add_argument("--auto-max-compounds", type=int, default=0, help="Auto seed compound cap (0 = all)")
    parser.add_argument("--auto-max-entities", type=int, default=0, help="Auto seed entity cap (0 = all)")
    parser.add_argument("--auto-max-pairs", type=int, default=400, help="Auto seed pair cap (0 = all)")
    parser.add_argument("--auto-max-seeds", type=int, default=1200, help="Auto seed total cap (0 = all)")
    parser.add_argument(
        "--balanced-seed-profile",
        choices=["off", "coverage", "evidence"],
        default="off",
        help="Add bounded allowlist coverage/evidence seed variants without full pair expansion",
    )
    parser.add_argument("--balanced-max-compounds", type=int, default=20, help="Balanced seed compound cap (0 = all)")
    parser.add_argument("--balanced-max-entities", type=int, default=50, help="Balanced seed target/disorder cap (0 = all)")
    parser.add_argument("--balanced-max-seeds", type=int, default=250, help="Balanced seed total cap (0 = all)")
    parser.add_argument(
        "--query-variant-mode",
        choices=["off", "conservative", "expanded"],
        default="off",
        help="Generate provider-specific query variants during discovery",
    )
    parser.add_argument(
        "--citation-chase",
        choices=["off", "known-study-set", "benchmark", "query-results"],
        default="off",
        help=(
            "Optionally expand discovery with Semantic Scholar references/citations. "
            "The older 'benchmark' value is retained as a compatibility alias."
        ),
    )
    parser.add_argument(
        "--citation-chase-directions",
        choices=["references", "citations", "both"],
        default="references",
    )
    parser.add_argument("--citation-chase-max-source-dois", type=int, default=25)
    parser.add_argument("--citation-chase-max-results-per-doi", type=int, default=20)
    parser.add_argument("--config", default=str(ROOT / "pipeline" / "config.example.yaml"))
    parser.add_argument("--openalex-email", default="")
    parser.add_argument("--openalex-api-key", default="")
    parser.add_argument("--ncbi-email", default="")
    parser.add_argument("--crossref-email", default="")
    parser.add_argument("--unpaywall-email", default="")
    parser.add_argument(
        "--metadata-provider-order",
        default="",
        help="Optional provider order to pass to paper-library sync",
    )
    parser.add_argument("--semantic-scholar-api-key", default="")
    parser.add_argument("--semantic-scholar-rps", type=float, default=None)
    parser.add_argument("--openalex-rps", type=float, default=None)
    parser.add_argument("--pubmed-rps", type=float, default=None)
    parser.add_argument("--pmc-rps", type=float, default=None)
    parser.add_argument("--crossref-rps", type=float, default=None)
    parser.add_argument("--unpaywall-rps", type=float, default=None)
    parser.add_argument("--enrich-unpaywall", action="store_true")
    parser.add_argument(
        "--skip-unpaywall-enrichment",
        action="store_true",
        help="Skip Unpaywall enrichment during discovery; useful for recall-only runs",
    )
    parser.add_argument("--max-retries", type=int, default=None)
    parser.add_argument("--skip-download", action="store_true", help="Do not download PDFs")
    parser.add_argument("--replace-library", action="store_true", help="Replace existing paper library outputs")
    parser.add_argument("--discover-only", action="store_true", help="Run discovery without paper sync")
    parser.add_argument("--sync-only", action="store_true", help="Run paper sync from existing discovered queues")
    parser.add_argument(
        "--recall-gate",
        action="store_true",
        help="Fail the run when known relevant study retrieval misses thresholds",
    )
    parser.add_argument("--min-discovered-recall", type=float, default=95.0)
    parser.add_argument("--min-triage-recall", type=float, default=90.0)
    parser.add_argument(
        "--benchmark-manifest",
        "--known-study-manifest",
        dest="benchmark_manifest",
        default=str(ROOT / "data" / "raw" / "benchmark_manifest.json"),
        help=(
            "Structured known relevant study set used for search completeness checks "
            "and protected retention. The older flag name is retained for compatibility."
        ),
    )
    parser.add_argument(
        "--disable-protected-retention",
        action="store_true",
        help="Do not pin known-study/curated/library DOIs before discovery caps",
    )
    parser.add_argument(
        "--disable-ledger",
        action="store_true",
        help="Do not write cumulative discovery ledgers",
    )
    parser.add_argument("--verbose", action="store_true", help="Print raw command output for debugging")
    args = parser.parse_args()

    if args.discover_only and args.sync_only:
        raise SystemExit("Use either --discover-only or --sync-only, not both")
    for name, value in {
        "min-discovered-recall": args.min_discovered_recall,
        "min-triage-recall": args.min_triage_recall,
    }.items():
        if value < 0 or value > 100:
            raise SystemExit(f"{name} must be between 0 and 100")

    try:
        datasets = parse_datasets(args.dataset)
    except ValueError as err:
        raise SystemExit(str(err))

    python_exe = sys.executable
    benchmark_manifest = Path(args.benchmark_manifest).resolve()

    print_header(
        datasets=datasets,
        provider=args.provider,
        max_results_per_seed=args.max_results_per_seed,
        max_results=args.max_results,
        discover_only=args.discover_only,
        sync_only=args.sync_only,
        skip_download=args.skip_download,
        expand_seeds_from_config=args.expand_seeds_from_config,
        auto_seeds_only=args.auto_seeds_only,
        auto_template_mode=args.auto_template_mode,
        auto_max_compounds=args.auto_max_compounds,
        auto_max_entities=args.auto_max_entities,
        auto_max_pairs=args.auto_max_pairs,
        auto_max_seeds=args.auto_max_seeds,
        balanced_seed_profile=args.balanced_seed_profile,
        balanced_max_compounds=args.balanced_max_compounds,
        balanced_max_entities=args.balanced_max_entities,
        balanced_max_seeds=args.balanced_max_seeds,
        query_variant_mode=args.query_variant_mode,
        citation_chase=args.citation_chase,
        citation_chase_directions=args.citation_chase_directions,
        citation_chase_max_source_dois=args.citation_chase_max_source_dois,
        citation_chase_max_results_per_doi=args.citation_chase_max_results_per_doi,
        semantic_scholar_rps=args.semantic_scholar_rps,
        openalex_rps=args.openalex_rps,
        max_retries=args.max_retries,
        recall_gate=args.recall_gate,
        min_discovered_recall=args.min_discovered_recall,
        min_triage_recall=args.min_triage_recall,
        benchmark_manifest=benchmark_manifest,
        disable_protected_retention=args.disable_protected_retention,
        disable_ledger=args.disable_ledger,
    )

    for dataset in datasets:
        print(f"--- Dataset: {dataset} ---")
        if not args.sync_only:
            discovery_details = [
                f"provider={args.provider}",
                f"max-results-per-seed={args.max_results_per_seed}",
                f"max-results={args.max_results}",
                f"outputs: data/raw/doi_queue.{dataset}.discovered.txt, data/processed/discovery_report_{dataset}.json, data/processed/discovery_ledger_{dataset}.json",
            ]
            if args.expand_seeds_from_config or args.auto_seeds_only:
                discovery_details.extend(
                    [
                        f"seed-expansion={'on' if args.expand_seeds_from_config else 'off'}",
                        f"auto-seeds-only={'yes' if args.auto_seeds_only else 'no'}",
                        f"auto-template-mode={args.auto_template_mode}",
                        f"auto-max-pairs={args.auto_max_pairs}, auto-max-seeds={args.auto_max_seeds}",
                    ]
                )
            if args.query_variant_mode != "off":
                discovery_details.append(f"query-variant-mode={args.query_variant_mode}")
            if args.balanced_seed_profile != "off":
                discovery_details.append(
                    "balanced-seed-profile="
                    f"{args.balanced_seed_profile} "
                    f"max-compounds={args.balanced_max_compounds} "
                    f"max-entities={args.balanced_max_entities} "
                    f"max-seeds={args.balanced_max_seeds}"
                )
            if args.citation_chase != "off":
                discovery_details.append(
                    f"citation-chase={args.citation_chase} directions={args.citation_chase_directions}"
                )
            print_step_intro(
                dataset=dataset,
                step_number="Step 1",
                title="discover literature",
                details=discovery_details,
            )
            discover_cmd = [
                python_exe,
                str(ROOT / "pipeline" / "ingest" / "discover_literature.py"),
                "--dataset",
                dataset,
                "--provider",
                args.provider,
                "--max-results-per-seed",
                str(args.max_results_per_seed),
                "--max-results",
                str(args.max_results),
                "--config",
                str(Path(args.config).resolve()),
                "--known-study-manifest",
                str(benchmark_manifest),
            ]
            if args.disable_protected_retention:
                discover_cmd.append("--disable-protected-retention")
            if args.disable_ledger:
                discover_cmd.append("--disable-ledger")
            if args.expand_seeds_from_config:
                discover_cmd.append("--expand-seeds-from-config")
            if args.auto_seeds_only:
                discover_cmd.append("--auto-seeds-only")
            discover_cmd.extend(["--auto-template-mode", args.auto_template_mode])
            discover_cmd.extend(["--auto-max-compounds", str(max(0, args.auto_max_compounds))])
            discover_cmd.extend(["--auto-max-entities", str(max(0, args.auto_max_entities))])
            discover_cmd.extend(["--auto-max-pairs", str(max(0, args.auto_max_pairs))])
            discover_cmd.extend(["--auto-max-seeds", str(max(0, args.auto_max_seeds))])
            discover_cmd.extend(["--balanced-seed-profile", args.balanced_seed_profile])
            discover_cmd.extend(["--balanced-max-compounds", str(max(0, args.balanced_max_compounds))])
            discover_cmd.extend(["--balanced-max-entities", str(max(0, args.balanced_max_entities))])
            discover_cmd.extend(["--balanced-max-seeds", str(max(0, args.balanced_max_seeds))])
            discover_cmd.extend(["--query-variant-mode", args.query_variant_mode])
            if args.citation_chase != "off":
                discover_cmd.extend(["--citation-chase", args.citation_chase])
                discover_cmd.extend(["--citation-chase-directions", args.citation_chase_directions])
                discover_cmd.extend(["--citation-chase-max-source-dois", str(max(0, args.citation_chase_max_source_dois))])
                discover_cmd.extend(["--citation-chase-max-results-per-doi", str(max(0, args.citation_chase_max_results_per_doi))])
            if args.openalex_email:
                discover_cmd.extend(["--openalex-email", args.openalex_email])
            if args.openalex_api_key:
                discover_cmd.extend(["--openalex-api-key", args.openalex_api_key])
            if args.ncbi_email:
                discover_cmd.extend(["--ncbi-email", args.ncbi_email])
            if args.crossref_email:
                discover_cmd.extend(["--crossref-email", args.crossref_email])
            if args.unpaywall_email:
                discover_cmd.extend(["--unpaywall-email", args.unpaywall_email])
            if args.semantic_scholar_api_key:
                discover_cmd.extend(["--semantic-scholar-api-key", args.semantic_scholar_api_key])
            if args.semantic_scholar_rps is not None:
                discover_cmd.extend(["--semantic-scholar-rps", str(args.semantic_scholar_rps)])
            if args.openalex_rps is not None:
                discover_cmd.extend(["--openalex-rps", str(args.openalex_rps)])
            if args.pubmed_rps is not None:
                discover_cmd.extend(["--pubmed-rps", str(args.pubmed_rps)])
            if args.pmc_rps is not None:
                discover_cmd.extend(["--pmc-rps", str(args.pmc_rps)])
            if args.crossref_rps is not None:
                discover_cmd.extend(["--crossref-rps", str(args.crossref_rps)])
            if args.unpaywall_rps is not None:
                discover_cmd.extend(["--unpaywall-rps", str(args.unpaywall_rps)])
            if args.enrich_unpaywall:
                discover_cmd.append("--enrich-unpaywall")
            if args.skip_unpaywall_enrichment:
                discover_cmd.append("--skip-unpaywall-enrichment")
            if args.max_retries is not None:
                discover_cmd.extend(["--max-retries", str(args.max_retries)])
            discover_cmd.append("--progress")
            discovery_info = run_step(
                discover_cmd,
                label=f"{dataset} / discover",
                verbose=args.verbose,
            )
            print_discovery_summary(dataset=dataset, info=discovery_info)
            if args.recall_gate:
                run_recall_gate(
                    dataset=dataset,
                    python_exe=python_exe,
                    benchmark_manifest=benchmark_manifest,
                    min_discovered_recall=args.min_discovered_recall,
                    min_triage_recall=0.0,
                    verbose=args.verbose,
                    phase="discovery",
                )

        if not args.discover_only:
            step_label = "Step 1" if args.sync_only else "Step 2"
            print_step_intro(
                dataset=dataset,
                step_number=step_label,
                title="sync paper library (metadata first)",
                details=[
                    "download-pdfs=no (metadata pass before triage)",
                    f"replace-library={'yes' if args.replace_library else 'no'}",
                    f"outputs: data/processed/paper_inventory_{dataset}.json, data/processed/paper_inventory_{dataset}.md",
                    f"pdf-dir: data/raw/papers/{dataset}/pdfs/",
                ],
            )
            sync_cmd = [
                python_exe,
                str(ROOT / "pipeline" / "ingest" / "sync_paper_library.py"),
                "--dataset",
                dataset,
                "--config",
                str(Path(args.config).resolve()),
                "--known-study-manifest",
                str(benchmark_manifest),
            ]
            if args.openalex_email:
                sync_cmd.extend(["--openalex-email", args.openalex_email])
            if args.openalex_api_key:
                sync_cmd.extend(["--openalex-api-key", args.openalex_api_key])
            if args.ncbi_email:
                sync_cmd.extend(["--ncbi-email", args.ncbi_email])
            if args.crossref_email:
                sync_cmd.extend(["--crossref-email", args.crossref_email])
            if args.unpaywall_email:
                sync_cmd.extend(["--unpaywall-email", args.unpaywall_email])
            if args.metadata_provider_order:
                sync_cmd.extend(["--metadata-provider-order", args.metadata_provider_order])
            if args.openalex_rps is not None:
                sync_cmd.extend(["--openalex-rps", str(args.openalex_rps)])
            if args.pubmed_rps is not None:
                sync_cmd.extend(["--pubmed-rps", str(args.pubmed_rps)])
            if args.pmc_rps is not None:
                sync_cmd.extend(["--pmc-rps", str(args.pmc_rps)])
            if args.crossref_rps is not None:
                sync_cmd.extend(["--crossref-rps", str(args.crossref_rps)])
            if args.unpaywall_rps is not None:
                sync_cmd.extend(["--unpaywall-rps", str(args.unpaywall_rps)])
            if args.max_retries is not None:
                sync_cmd.extend(["--max-retries", str(args.max_retries)])
            sync_cmd.append("--skip-download")
            if args.replace_library:
                sync_cmd.append("--replace")
            sync_info = run_step(
                sync_cmd,
                label=f"{dataset} / sync-metadata",
                verbose=args.verbose,
            )
            print_sync_summary(dataset=dataset, info=sync_info, phase="Metadata sync")

            triage_step_label = "Step 2" if args.sync_only else "Step 3"
            print_step_intro(
                dataset=dataset,
                step_number=triage_step_label,
                title="triage paper library",
                details=[
                    "classify likely relevant vs likely irrelevant",
                    f"output queue: data/raw/doi_queue.{dataset}.triage_relevant.txt",
                    f"output report: data/processed/triage_report_{dataset}.json",
                ],
            )
            triage_cmd = [
                python_exe,
                str(ROOT / "pipeline" / "review" / "triage_paper_library.py"),
                "--dataset",
                dataset,
                "--config",
                str(Path(args.config).resolve()),
                "--known-study-manifest",
                str(benchmark_manifest),
            ]
            triage_info = run_step(
                triage_cmd,
                label=f"{dataset} / triage",
                verbose=args.verbose,
            )
            print_triage_summary(dataset=dataset, info=triage_info)
            if args.recall_gate:
                run_recall_gate(
                    dataset=dataset,
                    python_exe=python_exe,
                    benchmark_manifest=benchmark_manifest,
                    min_discovered_recall=args.min_discovered_recall,
                    min_triage_recall=args.min_triage_recall,
                    verbose=args.verbose,
                    phase="triage",
                )

            if not args.skip_download:
                download_step_label = "Step 3" if args.sync_only else "Step 4"
                print_step_intro(
                    dataset=dataset,
                    step_number=download_step_label,
                    title="sync triage queue (download PDFs)",
                    details=[
                        f"doi-file=data/raw/doi_queue.{dataset}.triage_relevant.txt",
                        "download-pdfs=yes (triage-filtered)",
                        "replace-library=no (merge into metadata pass output)",
                    ],
                )
                triage_queue_path = ROOT / "data" / "raw" / f"doi_queue.{dataset}.triage_relevant.txt"
                sync_triage_cmd = [
                    python_exe,
                    str(ROOT / "pipeline" / "ingest" / "sync_paper_library.py"),
                    "--dataset",
                    dataset,
                    "--config",
                    str(Path(args.config).resolve()),
                    "--doi-file",
                    str(triage_queue_path),
                ]
                if args.openalex_email:
                    sync_triage_cmd.extend(["--openalex-email", args.openalex_email])
                if args.openalex_api_key:
                    sync_triage_cmd.extend(["--openalex-api-key", args.openalex_api_key])
                if args.ncbi_email:
                    sync_triage_cmd.extend(["--ncbi-email", args.ncbi_email])
                if args.crossref_email:
                    sync_triage_cmd.extend(["--crossref-email", args.crossref_email])
                if args.unpaywall_email:
                    sync_triage_cmd.extend(["--unpaywall-email", args.unpaywall_email])
                if args.metadata_provider_order:
                    sync_triage_cmd.extend(["--metadata-provider-order", args.metadata_provider_order])
                if args.openalex_rps is not None:
                    sync_triage_cmd.extend(["--openalex-rps", str(args.openalex_rps)])
                if args.pubmed_rps is not None:
                    sync_triage_cmd.extend(["--pubmed-rps", str(args.pubmed_rps)])
                if args.pmc_rps is not None:
                    sync_triage_cmd.extend(["--pmc-rps", str(args.pmc_rps)])
                if args.crossref_rps is not None:
                    sync_triage_cmd.extend(["--crossref-rps", str(args.crossref_rps)])
                if args.unpaywall_rps is not None:
                    sync_triage_cmd.extend(["--unpaywall-rps", str(args.unpaywall_rps)])
                if args.max_retries is not None:
                    sync_triage_cmd.extend(["--max-retries", str(args.max_retries)])
                sync_triage_info = run_step(
                    sync_triage_cmd,
                    label=f"{dataset} / sync-download",
                    verbose=args.verbose,
                )
                print_sync_summary(dataset=dataset, info=sync_triage_info, phase="Triage queue download sync")

    print_final_summary(datasets=datasets)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
