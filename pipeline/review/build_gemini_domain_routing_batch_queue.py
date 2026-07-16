#!/usr/bin/env python3
"""Split Gemini domain-routing requests into Batch API queue parts."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile

import pandas as pd

try:
    from pipeline.review.run_gemini_domain_routing import (
        DEFAULT_OUTPUT_TABLE,
        clean,
        normalize_doi,
        prompt_for_record,
        write_json,
    )
    from pipeline.review.run_gemini_domain_routing_batch import (
        DEFAULT_ENV,
        DEFAULT_CANDIDATE_TABLE,
        DEFAULT_METADATA_TABLE,
        DEFAULT_PRESCREEN_TABLE,
        DEFAULT_RAW_JSONL,
        selected_routing_records,
        write_batch_requests_for_records,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from pipeline.review.run_gemini_domain_routing import (
        DEFAULT_OUTPUT_TABLE,
        clean,
        normalize_doi,
        prompt_for_record,
        write_json,
    )
    from pipeline.review.run_gemini_domain_routing_batch import (
        DEFAULT_ENV,
        DEFAULT_CANDIDATE_TABLE,
        DEFAULT_METADATA_TABLE,
        DEFAULT_PRESCREEN_TABLE,
        DEFAULT_RAW_JSONL,
        selected_routing_records,
        write_batch_requests_for_records,
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


def previously_prescreen_retained_dois(path: Path) -> set[str]:
    """Return the DOI set retained by the immediately preceding prescreen run."""
    if not path.is_file():
        raise FileNotFoundError(f"Previous candidate table not found: {path}")
    retained_column = "prescreen_retained_for_extraction_candidate"
    frame = pd.read_parquet(path, columns=["doi", retained_column])
    if frame.empty:
        return set()
    frame = frame.copy()
    frame["_doi"] = frame["doi"].map(normalize_doi)
    frame["_retained"] = frame[retained_column].map(
        lambda value: clean(value).lower() in {"true", "1", "yes"}
    )
    return set(frame.loc[frame["_doi"].astype(bool) & frame["_retained"], "_doi"])


def write_doi_file_atomic(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    os.close(file_descriptor)
    temporary_path = Path(temporary_name)
    try:
        temporary_path.write_text(
            "".join(f"{normalize_doi(record.get('doi', ''))}\n" for record in records),
            encoding="utf-8",
        )
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def prepare_part(
    *,
    start_index: int,
    limit: int,
    paths: dict[str, str],
    args: argparse.Namespace,
    effective_doi_file: Path,
    records: list[dict],
) -> dict:
    prepare_args = argparse.Namespace(
        metadata_table=str(Path(args.metadata_table).resolve()),
        candidate_table=str(Path(args.candidate_table).resolve()),
        prescreen_decisions_table=str(Path(args.prescreen_decisions_table).resolve()),
        raw_jsonl=paths["raw_jsonl"],
        doi_file=str(effective_doi_file),
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
    return write_batch_requests_for_records(prepare_args, records)


def build_queue(args: argparse.Namespace) -> dict:
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    eligible_records = selected_routing_records(args)
    existing_routing_table = Path(args.existing_routing_table).resolve()
    previous_candidate_table = Path(args.previous_candidate_table).resolve()
    previously_retained = previously_prescreen_retained_dois(previous_candidate_table)
    eligible_dois = {normalize_doi(record.get("doi", "")) for record in eligible_records}
    unchanged_both_retained = eligible_dois.intersection(previously_retained)
    records = [
        record
        for record in eligible_records
        if normalize_doi(record.get("doi", "")) not in previously_retained
    ]
    effective_doi_file = (
        Path(args.delta_doi_file).resolve()
        if clean(args.delta_doi_file)
        else out_dir / f"paper_domain_routing_gemini_delta_dois.{args.tag}.txt"
    )
    write_doi_file_atomic(effective_doi_file, records)
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
            **paths,
        }
        if args.prepare:
            manifest = prepare_part(
                start_index=start_index,
                limit=limit,
                paths=paths,
                args=args,
                effective_doi_file=effective_doi_file,
                records=rows,
            )
            part["prepared_requests"] = manifest.get("summary", {}).get("prepared_requests", 0)
        parts.append(part)

    queue = {
        "schema_version": "domain_routing_gemini_batch_queue",
        "name": args.tag,
        "python": args.python,
        "notes": args.notes,
        "summary": {
            "eligible_records": len(eligible_records),
            "previous_prescreen_retained_dois": len(previously_retained),
            "unchanged_both_prescreens_retained": len(unchanged_both_retained),
            "records": len(records),
            "parts": len(parts),
            "max_requests": max(1, args.max_requests),
            "max_approx_input_tokens": max(1, args.max_approx_input_tokens),
            "prepared": bool(args.prepare),
        },
        "inputs": {
            "candidate_table": str(Path(args.candidate_table).resolve()),
            "metadata_table": str(Path(args.metadata_table).resolve()),
            "prescreen_decisions_table": str(Path(args.prescreen_decisions_table).resolve()),
            "scope_doi_file": str(Path(args.doi_file).resolve()) if clean(args.doi_file) else "",
            "delta_doi_file": str(effective_doi_file),
            "previous_candidate_table": str(previous_candidate_table),
            "existing_routing_table": str(existing_routing_table),
            "existing_raw_jsonl": str(Path(args.raw_jsonl).resolve()),
            "queue_selection_rule": "current_prescreen_retain_except_previous_prescreen_retain",
            "model": args.model,
            "temperature": args.temperature,
            "max_output_tokens": args.max_output_tokens,
            "thinking_budget": args.thinking_budget,
        },
        "parts": parts,
    }
    write_json(Path(args.queue_json).resolve(), queue)
    return queue


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-table", default=str(DEFAULT_CANDIDATE_TABLE))
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
    parser.add_argument("--existing-routing-table", default=str(DEFAULT_OUTPUT_TABLE))
    parser.add_argument(
        "--previous-candidate-table",
        required=True,
        help=(
            "Candidate-table snapshot from the immediately preceding prescreen run. "
            "DOIs retained in both that snapshot and the current prescreen are left out of the queue."
        ),
    )
    parser.add_argument("--delta-doi-file", default="")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--notes", default="")
    parser.add_argument("--prepare", action="store_true", help="Also write Batch API request JSONLs/manifests.")
    return parser.parse_args(argv)


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
