#!/usr/bin/env python3
"""Split Gemini domain-routing requests into Batch API queue parts."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys

try:
    from pipeline.review.run_gemini_domain_routing import clean, prompt_for_record, split_values, write_json
    from pipeline.review.run_gemini_domain_routing_batch import (
        DEFAULT_ENV,
        DEFAULT_METADATA_TABLE,
        DEFAULT_PRESCREEN_TABLE,
        DEFAULT_RAW_JSONL,
        selected_routing_records,
        write_batch_requests,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from pipeline.review.run_gemini_domain_routing import clean, prompt_for_record, split_values, write_json
    from pipeline.review.run_gemini_domain_routing_batch import (
        DEFAULT_ENV,
        DEFAULT_METADATA_TABLE,
        DEFAULT_PRESCREEN_TABLE,
        DEFAULT_RAW_JSONL,
        selected_routing_records,
        write_batch_requests,
    )


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT_DIR = ROOT / "data" / "processed" / "corpus"
DEFAULT_QUEUE_JSON = DEFAULT_OUT_DIR / "paper_domain_routing_gemini_batch_queue.json"
DEFAULT_PYTHON = "/opt/homebrew/Caskroom/miniconda/base/bin/python3"


def approx_input_tokens_char4(record: dict) -> int:
    return max(1, len(prompt_for_record(record)) // 4)


def split_records(records: list[dict], *, max_requests: int, max_approx_input_tokens: int) -> list[tuple[int, int, list[dict]]]:
    parts: list[tuple[int, int, list[dict]]] = []
    current: list[dict] = []
    current_tokens = 0
    current_start = 1
    for index, record in enumerate(records, start=1):
        tokens = approx_input_tokens_char4(record)
        would_exceed_requests = len(current) >= max_requests
        would_exceed_tokens = bool(current) and current_tokens + tokens > max_approx_input_tokens
        if would_exceed_requests or would_exceed_tokens:
            parts.append((current_start, len(current), current))
            current = []
            current_tokens = 0
            current_start = index
        current.append(record)
        current_tokens += tokens
    if current:
        parts.append((current_start, len(current), current))
    return parts


def part_paths(tag: str, part_number: int, out_dir: Path) -> dict[str, str]:
    part_tag = f"{tag}_part{part_number:03d}"
    return {
        "batch_requests_jsonl": str(out_dir / f"paper_domain_routing_gemini_batch_requests.{part_tag}.jsonl"),
        "manifest_json": str(out_dir / f"paper_domain_routing_gemini_batch_manifest.{part_tag}.json"),
        "job_json": str(out_dir / f"paper_domain_routing_gemini_batch_job.{part_tag}.json"),
        "batch_results_jsonl": str(out_dir / f"paper_domain_routing_gemini_batch_results.{part_tag}.jsonl"),
        "raw_jsonl": str(out_dir / f"paper_domain_routing_gemini_raw.{part_tag}.jsonl"),
        "report_json": str(out_dir / f"paper_domain_routing_gemini_batch_parse_report.{part_tag}.json"),
    }


def prepare_part(*, start_index: int, limit: int, paths: dict[str, str], args: argparse.Namespace) -> dict:
    prepare_args = argparse.Namespace(
        metadata_table=str(Path(args.metadata_table).resolve()),
        prescreen_decisions_table=str(Path(args.prescreen_decisions_table).resolve()),
        raw_jsonl=paths["raw_jsonl"],
        doi_file=args.doi_file,
        env_file=str(Path(args.env_file).resolve()),
        model=args.model,
        limit=limit,
        start_index=start_index,
        temperature=args.temperature,
        max_output_tokens=args.max_output_tokens,
        thinking_budget=args.thinking_budget,
        resume=False,
        batch_input_jsonl=paths["batch_requests_jsonl"],
        manifest_json=paths["manifest_json"],
    )
    return write_batch_requests(prepare_args)


def build_queue(args: argparse.Namespace) -> dict:
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    records = selected_routing_records(args)
    split = split_records(
        records,
        max_requests=max(1, args.max_requests),
        max_approx_input_tokens=max(1, args.max_approx_input_tokens),
    )
    parts = []
    for part_number, (start_index, limit, rows) in enumerate(split, start=1):
        paths = part_paths(args.tag, part_number, out_dir)
        part = {
            "part": part_number,
            "requests": limit,
            "start_index": start_index,
            "limit": limit,
            "approx_input_tokens_char4": sum(approx_input_tokens_char4(row) for row in rows),
            "by_dataset": dict(Counter(tag for row in rows for tag in split_values(row.get("datasets", "")))),
            **paths,
        }
        if args.prepare:
            manifest = prepare_part(start_index=start_index, limit=limit, paths=paths, args=args)
            part["prepared_requests"] = manifest.get("summary", {}).get("prepared_requests", 0)
        parts.append(part)

    queue = {
        "schema_version": "domain_routing_gemini_batch_queue",
        "name": args.tag,
        "python": args.python,
        "notes": args.notes,
        "summary": {
            "records": len(records),
            "parts": len(parts),
            "max_requests": max(1, args.max_requests),
            "max_approx_input_tokens": max(1, args.max_approx_input_tokens),
            "prepared": bool(args.prepare),
            "by_dataset": dict(Counter(tag for row in records for tag in split_values(row.get("datasets", "")))),
        },
        "inputs": {
            "metadata_table": str(Path(args.metadata_table).resolve()),
            "prescreen_decisions_table": str(Path(args.prescreen_decisions_table).resolve()),
            "doi_file": str(Path(args.doi_file).resolve()) if clean(args.doi_file) else "",
            "model": args.model,
            "temperature": args.temperature,
            "max_output_tokens": args.max_output_tokens,
            "thinking_budget": args.thinking_budget,
        },
        "parts": parts,
    }
    write_json(Path(args.queue_json).resolve(), queue)
    return queue


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata-table", default=str(DEFAULT_METADATA_TABLE))
    parser.add_argument("--prescreen-decisions-table", default=str(DEFAULT_PRESCREEN_TABLE))
    parser.add_argument("--doi-file", default="")
    parser.add_argument("--env-file", default=str(DEFAULT_ENV))
    parser.add_argument("--model", default="gemini-3-flash-preview")
    parser.add_argument("--tag", default="domain_routing")
    parser.add_argument("--queue-json", default=str(DEFAULT_QUEUE_JSON))
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--python", default=DEFAULT_PYTHON)
    parser.add_argument("--max-requests", type=int, default=1000)
    parser.add_argument("--max-approx-input-tokens", type=int, default=2_500_000)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--max-output-tokens", type=int, default=512)
    parser.add_argument("--thinking-budget", type=int, default=0)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--start-index", type=int, default=1)
    parser.add_argument("--raw-jsonl", default=str(DEFAULT_RAW_JSONL))
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--notes", default="")
    parser.add_argument("--prepare", action="store_true", help="Also write Batch API request JSONLs/manifests.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    queue = build_queue(args)
    print(f"Queue: {Path(args.queue_json).resolve()}")
    print(f"Records: {queue['summary']['records']:,}")
    print(f"Parts: {queue['summary']['parts']:,}")
    print(f"Prepared: {queue['summary']['prepared']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
