#!/usr/bin/env python3
"""Run the grouped search-module discovery layer with batch-safe outputs."""

from __future__ import annotations

import argparse
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
PROVIDERS = ["openalex", "pubmed"]
MODULE_TYPES = ["primary_boolean", "dense_topic"]


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
    print(f"[{label}] COMMAND")
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


def parse_datasets(raw: str) -> list[str]:
    if raw.strip().lower() == "all":
        return list(DATASETS)
    datasets = [item.strip().lower() for item in raw.split(",") if item.strip()]
    invalid = [item for item in datasets if item not in DATASETS]
    if invalid:
        raise ValueError(f"Invalid dataset(s): {', '.join(invalid)}")
    return datasets


def parse_providers(raw: str) -> list[str]:
    if raw.strip().lower() == "all":
        return list(PROVIDERS)
    providers = [item.strip().lower() for item in raw.split(",") if item.strip()]
    invalid = [item for item in providers if item not in PROVIDERS]
    if invalid:
        raise ValueError(f"Invalid provider(s): {', '.join(invalid)}")
    return providers


def parse_module_types(raw: str) -> list[str]:
    if raw.strip().lower() == "all":
        return list(MODULE_TYPES)
    module_types = [item.strip().lower() for item in raw.split(",") if item.strip()]
    invalid = [item for item in module_types if item not in MODULE_TYPES]
    if invalid:
        raise ValueError(f"Invalid module type(s): {', '.join(invalid)}")
    return module_types


def iter_manifest_batches(manifest: dict, datasets: Iterable[str], providers: Iterable[str], module_types: Iterable[str]) -> Iterable[dict]:
    for dataset in datasets:
        dataset_info = manifest["datasets"][dataset]
        for provider in providers:
            provider_info = dataset_info["outputs"][provider]
            for module_type in module_types:
                module_info = provider_info["module_type_outputs"][module_type]
                yield {
                    "dataset": dataset,
                    "provider": provider,
                    "module_type": module_type,
                    "seed_csv": Path(module_info["seed_csv"]),
                    "seed_count": int(module_info["seed_count"]),
                    "cap": int(module_info["recommended_max_results_per_seed"]),
                }


def discovery_cmd(batch: dict, out_dir: Path, args: argparse.Namespace) -> list[str]:
    cmd = [
        sys.executable,
        str(ROOT / "pipeline" / "ingest" / "discover_literature.py"),
        "--dataset",
        batch["dataset"],
        "--provider",
        batch["provider"],
        "--seed-file",
        str(batch["seed_csv"]),
        "--max-results-per-seed",
        str(batch["cap"]),
        "--max-results",
        "0",
        "--disable-ledger",
        "--disable-protected-retention",
        "--skip-unpaywall-enrichment",
        "--queue-out",
        str(out_dir / f"{batch['dataset']}_discovered.txt"),
        "--report-out",
        str(out_dir / f"{batch['dataset']}_discovery_report.json"),
        "--progress",
    ]
    if batch["provider"] == "openalex":
        cmd.extend(["--openalex-search-field", args.openalex_search_field])
    if args.max_retries is not None:
        cmd.extend(["--max-retries", str(args.max_retries)])
    if args.max_retry_after_sec is not None:
        cmd.extend(["--max-retry-after-sec", str(args.max_retry_after_sec)])
    if args.http_hard_timeout_sec is not None:
        cmd.extend(["--http-hard-timeout-sec", str(args.http_hard_timeout_sec)])
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
    with path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.reader(handle):
            if not row:
                continue
            first = normalize(row[0])
            if not first or first.startswith("#") or first.lower() in {"doi", "study_doi"}:
                continue
            rows.append([normalize(value) for value in row])
    return rows


def write_combined_discovered_queue(path: Path, dataset: str, queue_paths: list[Path]) -> int:
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


def summarize_batch(batch: dict, out_dir: Path, discovery_info: dict[str, str], gate_info: dict[str, str]) -> dict:
    discovery_report = read_json(out_dir / f"{batch['dataset']}_discovery_report.json")
    gate_report = read_json(out_dir / f"{batch['dataset']}_add_new_dois_report.json")
    discovery_counts = discovery_report.get("counts", {})
    gate_counts = gate_report.get("counts", {})
    return {
        **batch,
        "seed_csv": str(batch["seed_csv"]),
        "out_dir": str(out_dir),
        "raw_rows": int(discovery_counts.get("raw_rows") or discovery_info.get("raw rows") or 0),
        "merged_rows": int(discovery_counts.get("merged_rows") or discovery_info.get("merged rows") or 0),
        "new_dois": int(gate_counts.get("new_dois") or gate_info.get("new dois") or 0),
        "rediscovered_existing_dois": int(gate_counts.get("rediscovered_existing_dois") or 0),
        "missing_or_invalid_dois": int(gate_counts.get("missing_or_invalid_dois") or 0),
    }


def write_summary(run_root: Path, manifest_path: Path, batches: list[dict], combined: dict, run_id: str) -> None:
    summary = {
        "version": VERSION,
        "run_id": run_id,
        "protocol_id": run_id,
        "generated_at_utc": now_utc(),
        "manifest": str(manifest_path),
        "run_root": str(run_root),
        "search_modules": batches,
        "combined": combined,
    }
    json_path = run_root / "grouped_search_run_summary.json"
    json_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    lines = [
        "# Grouped Search Run Summary",
        "",
        f"- Generated: {summary['generated_at_utc']}",
        f"- Run: `{run_id}`",
        "",
        "## Search Modules",
        "",
        "| Dataset | Provider | Module type | Seeds | Cap | Raw rows | Merged rows | New DOIs | Rediscovered | Invalid |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for batch in batches:
        lines.append(
            f"| {batch['dataset']} | {batch['provider']} | {batch['module_type']} | {batch['seed_count']} | "
            f"{batch['cap']} | {batch['raw_rows']} | {batch['merged_rows']} | {batch['new_dois']} | "
            f"{batch['rediscovered_existing_dois']} | {batch['missing_or_invalid_dois']} |"
        )
    lines.extend(["", "## Combined DOI Gate", ""])
    lines.append("| Dataset | Combined discovered DOIs | Final new DOIs | Rediscovered existing | Invalid |")
    lines.append("| --- | ---: | ---: | ---: | ---: |")
    for dataset, item in combined.items():
        lines.append(
            f"| {dataset} | {item['combined_discovered_dois']} | {item['new_dois']} | "
            f"{item['rediscovered_existing_dois']} | {item['missing_or_invalid_dois']} |"
        )
    md_path = run_root / "grouped_search_run_summary.md"
    md_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    print(f"Summary JSON: {json_path}")
    print(f"Summary Markdown: {md_path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run grouped search-module discovery with safe per-batch outputs")
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID, help="Run label used when --manifest/--run-root are not supplied")
    parser.add_argument("--search-root", default=str(SEARCH_STRATEGY_ROOT), help="Root directory for search artifacts")
    parser.add_argument(
        "--manifest",
        default="",
        help="Grouped search-module manifest. Defaults to <search-root>/<run-id>/grouped_modules/grouped_search_modules_manifest.json.",
    )
    parser.add_argument(
        "--run-root",
        default="",
        help="Output directory for grouped search results. Defaults to <search-root>/<run-id>/grouped_module_run.",
    )
    parser.add_argument("--dataset", default="all", help="mechanistic, disorder, comma-separated list, or all")
    parser.add_argument("--provider", default="all", help="openalex, pubmed, comma-separated list, or all")
    parser.add_argument("--module-type", default="all", help="primary_boolean, dense_topic, comma-separated list, or all")
    parser.add_argument("--openalex-search-field", choices=["default", "title", "abstract", "title_and_abstract", "fulltext"], default="default")
    parser.add_argument("--existing-scope", choices=["global", "dataset"], default="global")
    parser.add_argument("--max-retries", type=int, default=2)
    parser.add_argument("--max-retry-after-sec", type=int, default=30)
    parser.add_argument("--http-hard-timeout-sec", type=int, default=180)
    parser.add_argument("--skip-existing", action="store_true", help="Reuse existing discovery/add-new reports when present")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    search_root = Path(args.search_root).resolve()
    manifest_path = (
        Path(args.manifest).resolve()
        if args.manifest
        else search_root / args.run_id / "grouped_modules" / "grouped_search_modules_manifest.json"
    )
    manifest = read_json(manifest_path)
    run_root = Path(args.run_root).resolve() if args.run_root else search_root / args.run_id / "grouped_module_run"
    run_root.mkdir(parents=True, exist_ok=True)

    try:
        datasets = parse_datasets(args.dataset)
        providers = parse_providers(args.provider)
        module_types = parse_module_types(args.module_type)
    except ValueError as err:
        raise SystemExit(str(err))

    batch_summaries = []
    discovered_by_dataset: dict[str, list[Path]] = {dataset: [] for dataset in datasets}
    for batch in iter_manifest_batches(manifest, datasets, providers, module_types):
        out_dir = run_root / f"{batch['provider']}_{batch['module_type']}_{batch['cap']}"
        out_dir.mkdir(parents=True, exist_ok=True)
        label_base = f"{batch['dataset']} / {batch['provider']} / {batch['module_type']} / cap {batch['cap']}"
        discovery_report = out_dir / f"{batch['dataset']}_discovery_report.json"
        add_new_report = out_dir / f"{batch['dataset']}_add_new_dois_report.json"

        if args.skip_existing and discovery_report.exists():
            discovery_info = {}
            print(f"[{label_base}] Discovery exists; reusing {discovery_report}", flush=True)
        else:
            discovery_info = run_step(discovery_cmd(batch, out_dir, args), label=f"{label_base} discovery", dry_run=args.dry_run)

        if not args.dry_run:
            discovered_by_dataset[batch["dataset"]].append(out_dir / f"{batch['dataset']}_discovered.txt")

        if args.skip_existing and add_new_report.exists():
            gate_info = {}
            print(f"[{label_base}] DOI gate exists; reusing {add_new_report}", flush=True)
        else:
            gate_info = run_step(add_new_cmd(batch["dataset"], out_dir, args), label=f"{label_base} DOI gate", dry_run=args.dry_run)

        if not args.dry_run:
            batch_summaries.append(summarize_batch(batch, out_dir, discovery_info, gate_info))

    if args.dry_run:
        return 0

    combined = {}
    combined_dir = run_root / "combined"
    combined_dir.mkdir(parents=True, exist_ok=True)
    for dataset, queue_paths in discovered_by_dataset.items():
        combined_discovered = combined_dir / f"{dataset}_discovered.txt"
        combined_count = write_combined_discovered_queue(combined_discovered, dataset, queue_paths)
        gate_info = run_step(
            [
                sys.executable,
                str(ROOT / "pipeline" / "ingest" / "add_new_dois.py"),
                "--dataset",
                dataset,
                "--input",
                str(combined_discovered),
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
            label=f"{dataset} / combined DOI gate",
        )
        report = read_json(combined_dir / f"{dataset}_add_new_dois_report.json")
        counts = report.get("counts", {})
        combined[dataset] = {
            "combined_discovered_dois": combined_count,
            "new_dois": int(counts.get("new_dois") or gate_info.get("new dois") or 0),
            "rediscovered_existing_dois": int(counts.get("rediscovered_existing_dois") or 0),
            "missing_or_invalid_dois": int(counts.get("missing_or_invalid_dois") or 0),
            "new_doi_queue": str(combined_dir / f"{dataset}_new_dois.txt"),
            "report_json": str(combined_dir / f"{dataset}_add_new_dois_report.json"),
        }

    write_summary(run_root, manifest_path, batch_summaries, combined, run_id=args.run_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
