#!/usr/bin/env python3
"""Run the generated direct-pair search layer with resumable chunks."""

from __future__ import annotations

import argparse
from collections import Counter
import csv
import datetime as dt
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RUN_ID = "literature_search"
SEARCH_STRATEGY_ROOT = ROOT / "data" / "raw" / "search_strategies"
VERSION = "0.1"
DATASETS = ["mechanistic", "disorder"]
DEFAULT_FAMILIES = ["sentinel_default", "class_level", "compound_broad", "entity_broad", "pair_core"]


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


def parse_key_values(stdout: str) -> dict[str, str]:
    out = {}
    for raw in stdout.splitlines():
        line = raw.strip()
        if not line or ":" not in line:
            continue
        key, value = line.split(":", 1)
        out[key.strip().lower()] = value.strip()
    return out


def run_step(cmd: list[str], label: str, dry_run: bool = False) -> dict[str, str]:
    print(f"[{label}] Running...", flush=True)
    print("  " + " ".join(cmd), flush=True)
    if dry_run:
        return {}

    start = time.monotonic()
    proc = subprocess.Popen(
        cmd,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=1,
    )
    output_lines = []
    assert proc.stdout is not None
    for raw_line in proc.stdout:
        line = raw_line.rstrip("\n")
        output_lines.append(line)
        if line.startswith("PROGRESS:"):
            print(f"[{label}] {line[len('PROGRESS:'):].strip()}", flush=True)
    return_code = proc.wait()
    stdout = "\n".join(output_lines)
    if return_code != 0:
        print(f"[{label}] FAILED (exit {return_code})", flush=True)
        if stdout.strip():
            print(stdout, flush=True)
        raise SystemExit(return_code)
    print(f"[{label}] Done in {time.monotonic() - start:.1f}s", flush=True)
    return parse_key_values(stdout)


def parse_csv_list(raw: str, allowed: list[str], label: str) -> list[str]:
    if raw.strip().lower() == "all":
        return list(allowed)
    items = [item.strip().lower() for item in raw.split(",") if item.strip()]
    invalid = [item for item in items if item not in allowed]
    if invalid:
        raise ValueError(f"Invalid {label}(s): {', '.join(invalid)}")
    if not items:
        raise ValueError(f"At least one {label} is required")
    return items


def read_seed_rows(path: Path) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(f"Missing seed file: {path}")
    with path.open("r", encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def write_seed_chunk(path: Path, rows: list[dict]) -> None:
    if not rows:
        raise ValueError("Cannot write empty seed chunk")
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0])
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def chunked(rows: list[dict], size: int) -> Iterable[list[dict]]:
    for index in range(0, len(rows), size):
        yield rows[index : index + size]


def build_chunks(seed_root: Path, run_root: Path, dataset: str, families: list[str], chunk_size: int) -> list[dict]:
    rows = read_seed_rows(seed_root / f"{dataset}_seeds.csv")
    selected = [row for row in rows if normalize(row.get("family")) in families]
    chunks = []
    chunk_root = run_root / "seed_chunks" / dataset
    for family in families:
        family_rows = [row for row in selected if normalize(row.get("family")) == family]
        for chunk_number, chunk_rows in enumerate(chunked(family_rows, chunk_size), start=1):
            chunk_path = chunk_root / f"{family}_chunk_{chunk_number:03d}.csv"
            write_seed_chunk(chunk_path, chunk_rows)
            chunks.append(
                {
                    "dataset": dataset,
                    "family": family,
                    "chunk_number": chunk_number,
                    "seed_count": len(chunk_rows),
                    "seed_csv": chunk_path,
                }
            )
    return chunks


def providers_for_arg(provider: str) -> list[str]:
    return ["openalex", "pubmed"] if provider == "both" else [provider]


def discovery_cmd(chunk: dict, out_dir: Path, cap: int, args: argparse.Namespace, provider: str) -> list[str]:
    cmd = [
        sys.executable,
        str(ROOT / "pipeline" / "ingest" / "discover_literature.py"),
        "--dataset",
        chunk["dataset"],
        "--provider",
        provider,
        "--seed-file",
        str(chunk["seed_csv"]),
        "--max-results-per-seed",
        str(cap),
        "--max-results",
        "0",
        "--disable-ledger",
        "--disable-protected-retention",
        "--skip-unpaywall-enrichment",
        "--queue-out",
        str(out_dir / f"{chunk['dataset']}_discovered.txt"),
        "--report-out",
        str(out_dir / f"{chunk['dataset']}_discovery_report.json"),
        "--max-retries",
        str(args.max_retries),
        "--max-retry-after-sec",
        str(args.max_retry_after_sec),
        "--http-hard-timeout-sec",
        str(args.http_hard_timeout_sec),
        "--query-variant-mode",
        args.query_variant_mode,
    ]
    if provider == "openalex":
        cmd.extend(["--openalex-search-field", args.openalex_search_field])
    if args.progress:
        cmd.append("--progress")
    if provider == "openalex" and args.openalex_rps is not None:
        cmd.extend(["--openalex-rps", str(args.openalex_rps)])
    if provider == "pubmed" and args.pubmed_rps is not None:
        cmd.extend(["--pubmed-rps", str(args.pubmed_rps)])
    return cmd


def add_new_cmd(dataset: str, out_dir: Path, args: argparse.Namespace) -> list[str]:
    return [
        sys.executable,
        str(ROOT / "pipeline" / "ingest" / "add_new_dois.py"),
        "--dataset",
        dataset,
        "--input",
        str(out_dir / f"{dataset}_discovered.txt"),
        "--queue-out",
        str(out_dir / f"{dataset}_new_dois.txt"),
        "--rediscovered-out",
        str(out_dir / f"{dataset}_rediscovered_dois.csv"),
        "--invalid-out",
        str(out_dir / f"{dataset}_missing_or_invalid_dois.csv"),
        "--duplicates-out",
        str(out_dir / f"{dataset}_input_duplicate_dois.csv"),
        "--report-out",
        str(out_dir / f"{dataset}_add_new_dois_report.json"),
        "--existing-scope",
        args.existing_scope,
    ]


def read_queue_rows(path: Path) -> list[list[str]]:
    rows = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.reader(handle):
            if not row:
                continue
            first = normalize(row[0])
            if not first or first.startswith("#") or first.lower() in {"doi", "study_doi"}:
                continue
            rows.append([normalize(value) for value in row])
    return rows


def read_queue_dois(path: Path) -> set[str]:
    return {normalize_doi(row[0]) for row in read_queue_rows(path) if normalize_doi(row[0])}


def write_combined_queue(path: Path, dataset: str, queue_paths: list[Path]) -> int:
    seen = set()
    rows = []
    for queue_path in queue_paths:
        for row in read_queue_rows(queue_path):
            doi = normalize_doi(row[0])
            if not doi or doi in seen:
                continue
            seen.add(doi)
            rows.append(row + [""] * (6 - len(row)))

    entity_name = "target" if dataset == "mechanistic" else "disorder"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(f"# combined discovered DOI queue ({dataset}) generated at {now_utc()}\n")
        handle.write(f"# doi,compound,{entity_name},optional_study_title,optional_study_year,optional_authors\n")
        writer = csv.writer(handle)
        for row in rows:
            writer.writerow(row[:6])
    return len(rows)


def summarize_chunk(chunk: dict, out_dir: Path, cap: int) -> dict:
    discovery = read_json(out_dir / f"{chunk['dataset']}_discovery_report.json")
    gate = read_json(out_dir / f"{chunk['dataset']}_add_new_dois_report.json")
    discovery_counts = discovery.get("counts", {})
    gate_counts = gate.get("counts", {})
    provider_errors = len(discovery.get("provider_errors", []))
    seed_count = int(discovery_counts.get("seed_count") or chunk["seed_count"] or 0)
    return {
        "provider": chunk["provider"],
        "dataset": chunk["dataset"],
        "family": chunk["family"],
        "chunk_number": chunk["chunk_number"],
        "seed_count": seed_count,
        "cap": cap,
        "out_dir": str(out_dir),
        "raw_rows": int(discovery_counts.get("raw_rows") or 0),
        "merged_rows": int(discovery_counts.get("merged_rows") or 0),
        "provider_errors": provider_errors,
        "provider_error_rate": round(provider_errors / seed_count, 4) if seed_count else 0.0,
        "new_dois_vs_existing_corpus": int(gate_counts.get("new_dois") or 0),
        "rediscovered_existing_dois": int(gate_counts.get("rediscovered_existing_dois") or 0),
        "missing_or_invalid_dois": int(gate_counts.get("missing_or_invalid_dois") or 0),
    }


def family_rollup(chunks: list[dict]) -> list[dict]:
    grouped: dict[tuple[str, str, str], Counter] = {}
    for chunk in chunks:
        key = (chunk["provider"], chunk["dataset"], chunk["family"])
        grouped.setdefault(key, Counter())
        grouped[key].update(
            {
                "chunks": 1,
                "seeds": chunk["seed_count"],
                "raw_rows": chunk["raw_rows"],
                "merged_rows": chunk["merged_rows"],
                "provider_errors": chunk["provider_errors"],
                "new_dois_vs_existing_corpus": chunk["new_dois_vs_existing_corpus"],
                "rediscovered_existing_dois": chunk["rediscovered_existing_dois"],
                "missing_or_invalid_dois": chunk["missing_or_invalid_dois"],
            }
        )
    return [
        {
            "provider": provider,
            "dataset": dataset,
            "family": family,
            **dict(counts),
        }
        for (provider, dataset, family), counts in sorted(grouped.items())
    ]


def write_summary(run_root: Path, summary: dict) -> None:
    json_path = run_root / "direct_pair_search_summary.json"
    json_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    lines = [
        "# Direct Pair Search Summary",
        "",
        f"- Generated: {summary['generated_at_utc']}",
        f"- Run: `{summary['run_id']}`",
        f"- Provider: `{summary['provider']}`",
        f"- Providers run: `{', '.join(summary.get('providers', [summary['provider']]))}`",
        f"- Query variant mode: `{summary['query_variant_mode']}`",
        f"- Status: `{summary.get('status', 'completed')}`",
        "",
        "## Final Queues",
        "",
        "| Dataset | Direct pair discovered DOIs | Direct pair new vs existing corpus | Grouped-search new DOIs | Final combined new DOIs | Direct pair incremental new beyond grouped search |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for dataset, item in summary["combined"].items():
        lines.append(
            f"| {dataset} | {item['direct_pair_discovered_dois']} | {item['direct_pair_new_vs_existing_corpus']} | "
            f"{item['grouped_search_new_dois']} | {item['combined_new_dois']} | "
            f"{item['direct_pair_incremental_new_beyond_grouped_search']} |"
        )
    lines.extend(["", "## Family Rollup", ""])
    lines.append("| Provider | Dataset | Family | Chunks | Seeds | Raw rows | Merged rows | Provider errors | New vs existing corpus | Rediscovered | Invalid |")
    lines.append("| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    for item in summary["family_rollup"]:
        lines.append(
            f"| {item['provider']} | {item['dataset']} | {item['family']} | {item['chunks']} | {item['seeds']} | "
            f"{item['raw_rows']} | {item['merged_rows']} | {item.get('provider_errors', 0)} | "
            f"{item['new_dois_vs_existing_corpus']} | {item['rediscovered_existing_dois']} | "
            f"{item['missing_or_invalid_dois']} |"
        )
    lines.extend(["", "## Outputs", ""])
    for dataset, item in summary["combined"].items():
        lines.append(f"- `{dataset}` direct pair new queue: `{item['direct_pair_new_queue']}`")
        lines.append(f"- `{dataset}` combined new queue: `{item['combined_new_queue']}`")
    md_path = run_root / "direct_pair_search_summary.md"
    md_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    print(f"Summary JSON: {json_path}")
    print(f"Summary Markdown: {md_path}")


def existing_report_exceeds_error_threshold(path: Path, max_error_rate: float) -> bool:
    if not path.exists():
        return False
    report = read_json(path)
    seed_count = int((report.get("counts") or {}).get("seed_count") or 0)
    if not seed_count:
        return False
    error_count = len(report.get("provider_errors", []))
    return (error_count / seed_count) > max_error_rate


def write_partial_summary(
    run_root: Path,
    args: argparse.Namespace,
    seed_root: Path,
    boolean_run_root: Path,
    chunk_summaries: list[dict],
    status: str,
) -> None:
    summary = {
        "version": VERSION,
        "run_id": args.run_id,
        "protocol_id": args.run_id,
        "generated_at_utc": now_utc(),
        "status": status,
        "provider": args.provider,
        "providers": providers_for_arg(args.provider),
        "openalex_search_field": args.openalex_search_field if "openalex" in providers_for_arg(args.provider) else None,
        "query_variant_mode": args.query_variant_mode,
        "caps": {"mechanistic": args.mechanistic_cap, "disorder": args.disorder_cap},
        "chunk_size": args.chunk_size,
        "seed_root": str(seed_root),
        "run_root": str(run_root),
        "grouped_run_root": str(boolean_run_root),
        "chunks": chunk_summaries,
        "family_rollup": family_rollup(chunk_summaries),
        "combined": {},
    }
    write_summary(run_root, summary)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run direct-pair search seed layer")
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID, help="Run label used when path arguments are not supplied")
    parser.add_argument("--search-root", default=str(SEARCH_STRATEGY_ROOT), help="Root directory for search artifacts")
    parser.add_argument("--seed-root", default="", help="Directory containing direct pair-search seeds. Defaults to <search-root>/<run-id>/direct_pairs.")
    parser.add_argument("--run-root", default="", help="Output directory for direct pair-search results. Defaults to <search-root>/<run-id>/direct_pair_run.")
    parser.add_argument("--dataset", default="all", help="mechanistic, disorder, comma-separated list, or all")
    parser.add_argument("--families", default=",".join(DEFAULT_FAMILIES), help="Seed families to run, comma-separated or all")
    parser.add_argument("--provider", choices=["openalex", "pubmed", "both"], default="both")
    parser.add_argument("--openalex-search-field", choices=["default", "title", "abstract", "title_and_abstract", "fulltext"], default="title_and_abstract")
    parser.add_argument("--query-variant-mode", choices=["off", "conservative", "expanded"], default="off")
    parser.add_argument("--mechanistic-cap", type=int, default=30)
    parser.add_argument("--disorder-cap", type=int, default=20)
    parser.add_argument("--chunk-size", type=int, default=500)
    parser.add_argument("--existing-scope", choices=["global", "dataset"], default="global")
    parser.add_argument(
        "--grouped-run-root",
        default="",
        help="Combined grouped-search output directory. Defaults to <search-root>/<run-id>/grouped_module_run/combined.",
    )
    parser.add_argument(
        "--boolean-run-root",
        default="",
        help=argparse.SUPPRESS,
    )
    parser.add_argument("--max-retries", type=int, default=2)
    parser.add_argument("--max-retry-after-sec", type=int, default=30)
    parser.add_argument("--http-hard-timeout-sec", type=int, default=180)
    parser.add_argument("--openalex-rps", type=float, default=None)
    parser.add_argument("--pubmed-rps", type=float, default=None)
    parser.add_argument("--skip-existing", action="store_true")
    parser.add_argument(
        "--max-provider-error-rate",
        type=float,
        default=0.25,
        help="Stop after a chunk if provider errors exceed this fraction of seeds.",
    )
    parser.add_argument("--progress", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    try:
        datasets = parse_csv_list(args.dataset, DATASETS, "dataset")
        families = parse_csv_list(args.families, DEFAULT_FAMILIES, "family")
    except ValueError as err:
        raise SystemExit(str(err))

    search_root = Path(args.search_root).resolve()
    seed_root = Path(args.seed_root).resolve() if args.seed_root else search_root / args.run_id / "direct_pairs"
    run_root = Path(args.run_root).resolve() if args.run_root else search_root / args.run_id / "direct_pair_run"
    grouped_run_root_arg = args.grouped_run_root or args.boolean_run_root
    boolean_run_root = (
        Path(grouped_run_root_arg).resolve()
        if grouped_run_root_arg
        else search_root / args.run_id / "grouped_module_run" / "combined"
    )
    run_root.mkdir(parents=True, exist_ok=True)
    providers = providers_for_arg(args.provider)

    chunk_summaries = []
    discovered_by_dataset: dict[str, list[Path]] = {dataset: [] for dataset in datasets}
    for provider in providers:
        for dataset in datasets:
            cap = args.mechanistic_cap if dataset == "mechanistic" else args.disorder_cap
            chunks = build_chunks(seed_root, run_root, dataset, families, args.chunk_size)
            print(
                f"[{provider} / {dataset}] Prepared {len(chunks)} chunks "
                f"from {sum(chunk['seed_count'] for chunk in chunks)} seeds",
                flush=True,
            )
            for chunk in chunks:
                chunk = {**chunk, "provider": provider}
                out_dir = (
                    run_root
                    / provider
                    / dataset
                    / chunk["family"]
                    / f"chunk_{chunk['chunk_number']:03d}"
                )
                out_dir.mkdir(parents=True, exist_ok=True)
                discovery_report = out_dir / f"{dataset}_discovery_report.json"
                gate_report = out_dir / f"{dataset}_add_new_dois_report.json"
                label = f"{provider} / {dataset} / {chunk['family']} / chunk {chunk['chunk_number']:03d}"

                reuse_existing_discovery = (
                    args.skip_existing
                    and discovery_report.exists()
                    and not existing_report_exceeds_error_threshold(discovery_report, args.max_provider_error_rate)
                )
                if args.skip_existing and discovery_report.exists() and not reuse_existing_discovery:
                    print(f"[{label}] Existing discovery has high provider-error rate; rerunning {discovery_report}", flush=True)

                if reuse_existing_discovery:
                    print(f"[{label}] Discovery exists; reusing {discovery_report}", flush=True)
                else:
                    run_step(discovery_cmd(chunk, out_dir, cap, args, provider), label=f"{label} discovery", dry_run=args.dry_run)

                if not args.dry_run:
                    discovered_by_dataset[dataset].append(out_dir / f"{dataset}_discovered.txt")

                if args.skip_existing and gate_report.exists():
                    print(f"[{label}] DOI gate exists; reusing {gate_report}", flush=True)
                else:
                    run_step(add_new_cmd(dataset, out_dir, args), label=f"{label} DOI gate", dry_run=args.dry_run)

                if not args.dry_run:
                    chunk_summary = summarize_chunk(chunk, out_dir, cap)
                    chunk_summaries.append(chunk_summary)
                    if chunk_summary["provider_error_rate"] > args.max_provider_error_rate:
                        status = (
                            f"stopped_provider_error_rate_{chunk_summary['provider_error_rate']}"
                        )
                        print(
                            f"[{label}] Stopping: provider error rate "
                            f"{chunk_summary['provider_error_rate']:.1%} exceeds "
                            f"{args.max_provider_error_rate:.1%}",
                            flush=True,
                        )
                        write_partial_summary(
                            run_root,
                            args,
                            seed_root,
                            boolean_run_root,
                            chunk_summaries,
                            status=status,
                        )
                        return 2

    if args.dry_run:
        return 0

    combined_dir = run_root / "combined"
    all_layer_dir = run_root / "all_layers_combined"
    combined = {}
    for dataset, queue_paths in discovered_by_dataset.items():
        pair_grid_discovered = combined_dir / f"{dataset}_discovered.txt"
        pair_grid_discovered_count = write_combined_queue(pair_grid_discovered, dataset, queue_paths)
        run_step(
            [
                sys.executable,
                str(ROOT / "pipeline" / "ingest" / "add_new_dois.py"),
                "--dataset",
                dataset,
                "--input",
                str(pair_grid_discovered),
                "--queue-out",
                str(combined_dir / f"{dataset}_new_dois.txt"),
                "--rediscovered-out",
                str(combined_dir / f"{dataset}_rediscovered_dois.csv"),
                "--invalid-out",
                str(combined_dir / f"{dataset}_missing_or_invalid_dois.csv"),
                "--duplicates-out",
                str(combined_dir / f"{dataset}_input_duplicate_dois.csv"),
                "--report-out",
                str(combined_dir / f"{dataset}_add_new_dois_report.json"),
                "--existing-scope",
                args.existing_scope,
            ],
            label=f"{dataset} / direct pair combined DOI gate",
        )

        boolean_discovered = boolean_run_root / f"{dataset}_discovered.txt"
        boolean_new = boolean_run_root / f"{dataset}_new_dois.txt"
        all_layer_discovered = all_layer_dir / f"{dataset}_discovered.txt"
        write_combined_queue(all_layer_discovered, dataset, [boolean_discovered, pair_grid_discovered])
        run_step(
            [
                sys.executable,
                str(ROOT / "pipeline" / "ingest" / "add_new_dois.py"),
                "--dataset",
                dataset,
                "--input",
                str(all_layer_discovered),
                "--queue-out",
                str(all_layer_dir / f"{dataset}_new_dois.txt"),
                "--rediscovered-out",
                str(all_layer_dir / f"{dataset}_rediscovered_dois.csv"),
                "--invalid-out",
                str(all_layer_dir / f"{dataset}_missing_or_invalid_dois.csv"),
                "--duplicates-out",
                str(all_layer_dir / f"{dataset}_input_duplicate_dois.csv"),
                "--report-out",
                str(all_layer_dir / f"{dataset}_add_new_dois_report.json"),
                "--existing-scope",
                args.existing_scope,
            ],
            label=f"{dataset} / all-layer combined DOI gate",
        )

        pair_grid_report = read_json(combined_dir / f"{dataset}_add_new_dois_report.json")
        all_layer_report = read_json(all_layer_dir / f"{dataset}_add_new_dois_report.json")
        pair_grid_new = read_queue_dois(combined_dir / f"{dataset}_new_dois.txt")
        boolean_new_dois = read_queue_dois(boolean_new)
        all_layer_new = read_queue_dois(all_layer_dir / f"{dataset}_new_dois.txt")
        combined[dataset] = {
            "direct_pair_discovered_dois": pair_grid_discovered_count,
            "direct_pair_new_vs_existing_corpus": int(pair_grid_report["counts"]["new_dois"]),
            "grouped_search_new_dois": len(boolean_new_dois),
            "combined_new_dois": int(all_layer_report["counts"]["new_dois"]),
            "direct_pair_incremental_new_beyond_grouped_search": len(all_layer_new - boolean_new_dois),
            "direct_pair_new_overlapping_grouped_search_new": len(pair_grid_new & boolean_new_dois),
            "direct_pair_new_queue": str(combined_dir / f"{dataset}_new_dois.txt"),
            "combined_new_queue": str(all_layer_dir / f"{dataset}_new_dois.txt"),
            "combined_report_json": str(all_layer_dir / f"{dataset}_add_new_dois_report.json"),
        }

    summary = {
        "version": VERSION,
        "run_id": args.run_id,
        "protocol_id": args.run_id,
        "generated_at_utc": now_utc(),
        "status": "completed",
        "provider": args.provider,
        "providers": providers,
        "openalex_search_field": args.openalex_search_field if "openalex" in providers else None,
        "query_variant_mode": args.query_variant_mode,
        "caps": {"mechanistic": args.mechanistic_cap, "disorder": args.disorder_cap},
        "chunk_size": args.chunk_size,
        "seed_root": str(seed_root),
        "run_root": str(run_root),
        "grouped_run_root": str(boolean_run_root),
        "chunks": chunk_summaries,
        "family_rollup": family_rollup(chunk_summaries),
        "combined": combined,
    }
    write_summary(run_root, summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
