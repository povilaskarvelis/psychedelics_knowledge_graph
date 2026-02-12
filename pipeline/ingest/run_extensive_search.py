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
    print(f"[{dataset}] Discovery complete")
    print(f"  Seeds: {seeds} | Raw rows: {raw_rows} | Merged rows: {merged_rows}")
    if seed_sources:
        print(f"  Seed sources: {seed_sources}")
    if queue:
        print(f"  Queue: {queue}")
    if report:
        print(f"  Report: {report}")
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


def print_final_summary(datasets: List[str]) -> None:
    print("=== Run Complete ===")
    for dataset in datasets:
        print(f"[{dataset}]")
        print(f"  Queue: data/raw/doi_queue.{dataset}.discovered.txt")
        print(f"  Triage queue: data/raw/doi_queue.{dataset}.triage_relevant.txt")
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
        choices=["semantic_scholar", "openalex", "hybrid"],
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
    parser.add_argument("--config", default=str(ROOT / "pipeline" / "config.example.yaml"))
    parser.add_argument("--openalex-email", default="")
    parser.add_argument("--semantic-scholar-api-key", default="")
    parser.add_argument("--skip-download", action="store_true", help="Do not download PDFs")
    parser.add_argument("--replace-library", action="store_true", help="Replace existing paper library outputs")
    parser.add_argument("--discover-only", action="store_true", help="Run discovery without paper sync")
    parser.add_argument("--sync-only", action="store_true", help="Run paper sync from existing discovered queues")
    parser.add_argument("--verbose", action="store_true", help="Print raw command output for debugging")
    args = parser.parse_args()

    if args.discover_only and args.sync_only:
        raise SystemExit("Use either --discover-only or --sync-only, not both")

    try:
        datasets = parse_datasets(args.dataset)
    except ValueError as err:
        raise SystemExit(str(err))

    python_exe = sys.executable

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
    )

    for dataset in datasets:
        print(f"--- Dataset: {dataset} ---")
        if not args.sync_only:
            discovery_details = [
                f"provider={args.provider}",
                f"max-results-per-seed={args.max_results_per_seed}",
                f"max-results={args.max_results}",
                f"outputs: data/raw/doi_queue.{dataset}.discovered.txt, data/processed/discovery_report_{dataset}.json",
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
            ]
            if args.expand_seeds_from_config:
                discover_cmd.append("--expand-seeds-from-config")
            if args.auto_seeds_only:
                discover_cmd.append("--auto-seeds-only")
            discover_cmd.extend(["--auto-template-mode", args.auto_template_mode])
            discover_cmd.extend(["--auto-max-compounds", str(max(0, args.auto_max_compounds))])
            discover_cmd.extend(["--auto-max-entities", str(max(0, args.auto_max_entities))])
            discover_cmd.extend(["--auto-max-pairs", str(max(0, args.auto_max_pairs))])
            discover_cmd.extend(["--auto-max-seeds", str(max(0, args.auto_max_seeds))])
            if args.openalex_email:
                discover_cmd.extend(["--openalex-email", args.openalex_email])
            if args.semantic_scholar_api_key:
                discover_cmd.extend(["--semantic-scholar-api-key", args.semantic_scholar_api_key])
            discover_cmd.append("--progress")
            discovery_info = run_step(
                discover_cmd,
                label=f"{dataset} / discover",
                verbose=args.verbose,
            )
            print_discovery_summary(dataset=dataset, info=discovery_info)

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
            ]
            if args.openalex_email:
                sync_cmd.extend(["--openalex-email", args.openalex_email])
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
            ]
            triage_info = run_step(
                triage_cmd,
                label=f"{dataset} / triage",
                verbose=args.verbose,
            )
            print_triage_summary(dataset=dataset, info=triage_info)

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
