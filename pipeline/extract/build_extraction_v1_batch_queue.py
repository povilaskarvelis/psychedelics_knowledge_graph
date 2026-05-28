#!/usr/bin/env python3
"""Split extraction-v1 inputs into Gemini Batch API queue parts."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

try:
    from pipeline.extract.extraction_v1_utils import normalize, read_jsonl, write_json
    from pipeline.extract.run_gemini_extraction_v1_batch import (
        DEFAULT_DISORDER_PROMPT,
        DEFAULT_ENV,
        DEFAULT_MECHANISTIC_PROMPT,
        DEFAULT_OUTPUT_DIR,
        DEFAULT_PROMPT,
        DEFAULT_SCHEMA,
        write_batch_requests,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from pipeline.extract.extraction_v1_utils import normalize, read_jsonl, write_json
    from pipeline.extract.run_gemini_extraction_v1_batch import (
        DEFAULT_DISORDER_PROMPT,
        DEFAULT_ENV,
        DEFAULT_MECHANISTIC_PROMPT,
        DEFAULT_OUTPUT_DIR,
        DEFAULT_PROMPT,
        DEFAULT_SCHEMA,
        write_batch_requests,
    )


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PYTHON = "/opt/homebrew/Caskroom/miniconda/base/bin/python3"


def approx_input_tokens_char4(record: dict) -> int:
    return max(1, len(json.dumps(record, ensure_ascii=False)) // 4)


def split_records(records: list[dict], *, max_requests: int, max_approx_input_tokens: int) -> list[tuple[int, int, list[dict]]]:
    parts: list[tuple[int, int, list[dict]]] = []
    start_index = 1
    current: list[dict] = []
    current_tokens = 0
    current_start = start_index
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
    part_tag = f"{tag}_part{part_number}"
    return {
        "batch_requests_jsonl": str(out_dir / f"extraction_v1_batch_requests.{part_tag}.jsonl"),
        "manifest_json": str(out_dir / f"extraction_v1_batch_manifest.{part_tag}.json"),
        "job_json": str(out_dir / f"extraction_v1_batch_job.{part_tag}.json"),
        "batch_results_jsonl": str(out_dir / f"extraction_v1_batch_results.{part_tag}.jsonl"),
        "out_jsonl": str(out_dir / f"extraction_v1_results.{part_tag}.jsonl"),
        "raw_jsonl": str(out_dir / f"extraction_v1_raw.{part_tag}.jsonl"),
        "report_json": str(out_dir / f"extraction_v1_report.{part_tag}.json"),
        "malformed_retry_jsonl": str(out_dir / f"extraction_v1_pilot_inputs.{part_tag}_malformed_retry.jsonl"),
        "malformed_report_json": str(out_dir / f"extraction_v1_malformed_retry.{part_tag}.report.json"),
    }


def prepare_part(
    *,
    source_input_jsonl: Path,
    start_index: int,
    limit: int,
    paths: dict[str, str],
    args: argparse.Namespace,
) -> dict:
    prepare_args = argparse.Namespace(
        input_jsonl=str(source_input_jsonl),
        raw_jsonl=paths["raw_jsonl"],
        prompt=str(Path(args.prompt).resolve()),
        mechanistic_prompt=str(Path(args.mechanistic_prompt).resolve()),
        disorder_prompt=str(Path(args.disorder_prompt).resolve()),
        schema=str(Path(args.schema).resolve()),
        env_file=str(Path(args.env_file).resolve()),
        model=args.model,
        schema_mode=args.schema_mode,
        limit=limit,
        start_index=start_index,
        temperature=args.temperature,
        max_output_tokens=args.max_output_tokens,
        mechanistic_max_output_tokens=args.mechanistic_max_output_tokens,
        disorder_max_output_tokens=args.disorder_max_output_tokens,
        thinking_budget=args.thinking_budget,
        resume=False,
        batch_input_jsonl=paths["batch_requests_jsonl"],
        manifest_json=paths["manifest_json"],
    )
    return write_batch_requests(prepare_args)


def build_queue(args: argparse.Namespace) -> dict:
    source_input_jsonl = Path(args.input_jsonl).resolve()
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    records = read_jsonl(source_input_jsonl)
    split = split_records(
        records,
        max_requests=max(1, args.max_requests),
        max_approx_input_tokens=max(1, args.max_approx_input_tokens),
    )
    parts = []
    for part_number, (start_index, limit, rows) in enumerate(split, start=1):
        paths = part_paths(args.tag, part_number, out_dir)
        by_dataset = dict(Counter(normalize(row.get("dataset", "")) for row in rows))
        by_bucket = dict(Counter(normalize(row.get("bucket", "")) for row in rows))
        part = {
            "part": part_number,
            "requests": limit,
            "start_index": start_index,
            "limit": limit,
            "by_dataset": by_dataset,
            "by_bucket": by_bucket,
            "approx_input_tokens_char4": sum(approx_input_tokens_char4(row) for row in rows),
            **paths,
        }
        if args.prepare:
            manifest = prepare_part(
                source_input_jsonl=source_input_jsonl,
                start_index=start_index,
                limit=limit,
                paths=paths,
                args=args,
            )
            part["prepared_requests"] = manifest.get("summary", {}).get("prepared_requests", 0)
        parts.append(part)

    queue = {
        "schema_version": "extraction_v1_batch_queue",
        "name": args.tag,
        "python": args.python,
        "source_input_jsonl": str(source_input_jsonl),
        "source_report_json": str(Path(args.source_report_json).resolve()) if normalize(args.source_report_json) else "",
        "excluded_meta_analyses_jsonl": str(Path(args.excluded_jsonl).resolve()) if normalize(args.excluded_jsonl) else "",
        "notes": args.notes,
        "summary": {
            "records": len(records),
            "parts": len(parts),
            "max_requests": max(1, args.max_requests),
            "max_approx_input_tokens": max(1, args.max_approx_input_tokens),
            "prepared": bool(args.prepare),
            "by_dataset": dict(Counter(normalize(row.get("dataset", "")) for row in records)),
            "by_bucket": dict(Counter(normalize(row.get("bucket", "")) for row in records)),
        },
        "parts": parts,
    }
    write_json(Path(args.queue_json).resolve(), queue)
    return queue


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-jsonl", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--queue-json", required=True)
    parser.add_argument("--out-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--source-report-json", default="")
    parser.add_argument("--excluded-jsonl", default="")
    parser.add_argument("--python", default=DEFAULT_PYTHON)
    parser.add_argument("--max-requests", type=int, default=64)
    parser.add_argument("--max-approx-input-tokens", type=int, default=1_400_000)
    parser.add_argument("--notes", default="")
    parser.add_argument("--prepare", action="store_true", help="Also write Gemini Batch API request JSONLs/manifests")
    parser.add_argument("--prompt", default=str(DEFAULT_PROMPT))
    parser.add_argument("--mechanistic-prompt", default=str(DEFAULT_MECHANISTIC_PROMPT))
    parser.add_argument("--disorder-prompt", default=str(DEFAULT_DISORDER_PROMPT))
    parser.add_argument("--schema", default=str(DEFAULT_SCHEMA))
    parser.add_argument("--env-file", default=str(DEFAULT_ENV))
    parser.add_argument("--model", default="")
    parser.add_argument("--schema-mode", choices=["prompt", "native", "both"], default="native")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--max-output-tokens", type=int, default=8192)
    parser.add_argument("--mechanistic-max-output-tokens", type=int, default=16384)
    parser.add_argument("--disorder-max-output-tokens", type=int, default=0)
    parser.add_argument("--thinking-budget", type=int, default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    queue = build_queue(args)
    print(f"Queue: {Path(args.queue_json).resolve()}")
    print(f"Records: {queue['summary']['records']}")
    print(f"Parts: {queue['summary']['parts']}")
    print(f"Prepared: {queue['summary']['prepared']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
