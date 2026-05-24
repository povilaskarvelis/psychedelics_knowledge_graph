#!/usr/bin/env python3
"""Prepare, submit, and parse Gemini Batch API extraction-v1 jobs."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path

try:
    from google import genai
    from google.genai import models as genai_models
    from google.genai import types
except ModuleNotFoundError as err:  # pragma: no cover - environment guard
    raise SystemExit("google-genai is required for Gemini batch extraction") from err

try:
    from jsonschema import Draft7Validator
except ModuleNotFoundError as err:  # pragma: no cover - environment guard
    raise SystemExit("jsonschema is required for Gemini batch extraction validation") from err

try:
    from pipeline.extract.extraction_v1_utils import normalize, normalize_extraction_v1_result, read_jsonl, write_json
    from pipeline.extract.run_gemini_extraction_v1 import (
        DEFAULT_DISORDER_PROMPT,
        DEFAULT_ENV,
        DEFAULT_INPUT,
        DEFAULT_MECHANISTIC_PROMPT,
        DEFAULT_OUTPUT_DIR,
        DEFAULT_PROMPT,
        DEFAULT_SCHEMA,
        SCHEMA_MODES,
        build_contents,
        build_generation_config,
        build_system_instruction,
        completed_input_ids,
        compact_schema_for_prompt,
        inject_identity_fields,
        load_dotenv,
        load_schema,
        max_output_tokens_for_record,
        parse_json_response_with_method,
        schema_error_messages,
        schema_in_prompt,
        schema_view_for_native,
        schema_view_for_prompt,
        system_instruction_for_record,
        usage_dict,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from pipeline.extract.extraction_v1_utils import normalize, normalize_extraction_v1_result, read_jsonl, write_json
    from pipeline.extract.run_gemini_extraction_v1 import (
        DEFAULT_DISORDER_PROMPT,
        DEFAULT_ENV,
        DEFAULT_INPUT,
        DEFAULT_MECHANISTIC_PROMPT,
        DEFAULT_OUTPUT_DIR,
        DEFAULT_PROMPT,
        DEFAULT_SCHEMA,
        SCHEMA_MODES,
        build_contents,
        build_generation_config,
        build_system_instruction,
        completed_input_ids,
        compact_schema_for_prompt,
        inject_identity_fields,
        load_dotenv,
        load_schema,
        max_output_tokens_for_record,
        parse_json_response_with_method,
        schema_error_messages,
        schema_in_prompt,
        schema_view_for_native,
        schema_view_for_prompt,
        system_instruction_for_record,
        usage_dict,
    )


ROOT = Path(__file__).resolve().parents[2]
TERMINAL_STATES = {"JOB_STATE_SUCCEEDED", "JOB_STATE_FAILED", "JOB_STATE_CANCELLED", "JOB_STATE_EXPIRED"}


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def default_batch_input_jsonl() -> Path:
    return DEFAULT_OUTPUT_DIR / "extraction_v1_batch_requests.jsonl"


def default_batch_manifest_json() -> Path:
    return DEFAULT_OUTPUT_DIR / "extraction_v1_batch_manifest.json"


def default_batch_job_json() -> Path:
    return DEFAULT_OUTPUT_DIR / "extraction_v1_batch_job.json"


def default_batch_output_jsonl() -> Path:
    return DEFAULT_OUTPUT_DIR / "extraction_v1_batch_results.jsonl"


def api_key_from_env(args: argparse.Namespace, *, required: bool) -> str:
    env_values = load_dotenv(Path(args.env_file).resolve())
    api_key = env_values.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY", "")
    if required and not api_key:
        raise SystemExit("GEMINI_API_KEY is missing. Add it to project .env or the environment.")
    return api_key or "DUMMY"


def model_from_env(args: argparse.Namespace) -> str:
    env_values = load_dotenv(Path(args.env_file).resolve())
    return normalize(args.model) or env_values.get("GEMINI_MODEL") or os.environ.get("GEMINI_MODEL", "") or "gemini-2.5-flash"


def selected_records(args: argparse.Namespace) -> list[tuple[int, dict]]:
    records = read_jsonl(Path(args.input_jsonl).resolve())
    completed_ids = completed_input_ids(Path(args.raw_jsonl).resolve()) if getattr(args, "resume", False) else set()
    start_index = max(1, int(args.start_index))
    selected = [
        (idx, record)
        for idx, record in enumerate(records, start=1)
        if idx >= start_index and normalize(record.get("pilot_record_id", "")) not in completed_ids
    ]
    if args.limit > 0:
        selected = selected[: args.limit]
    return selected


def schema_views(schema: dict) -> tuple[dict[str, dict], dict[str, dict]]:
    prompt_views = {
        "mechanistic": schema_view_for_prompt(schema, "mechanistic"),
        "disorder": schema_view_for_prompt(schema, "disorder"),
    }
    native_views = {
        "mechanistic": schema_view_for_native(schema, "mechanistic"),
        "disorder": schema_view_for_native(schema, "disorder"),
    }
    return prompt_views, native_views


def system_instructions_for_args(args: argparse.Namespace, prompt_views: dict[str, dict]) -> dict[str, str]:
    shared_prompt_text = Path(args.prompt).resolve().read_text(encoding="utf-8")
    return {
        "mechanistic": build_system_instruction(
            shared_prompt_text,
            prompt_views["mechanistic"],
            Path(args.mechanistic_prompt).resolve().read_text(encoding="utf-8"),
            include_schema=schema_in_prompt(args.schema_mode),
        ),
        "disorder": build_system_instruction(
            shared_prompt_text,
            prompt_views["disorder"],
            Path(args.disorder_prompt).resolve().read_text(encoding="utf-8"),
            include_schema=schema_in_prompt(args.schema_mode),
        ),
    }


def batch_request_for_record(
    *,
    api_client: object,
    record: dict,
    system_instructions: dict[str, str],
    native_views: dict[str, dict],
    args: argparse.Namespace,
) -> dict:
    dataset = normalize(record.get("dataset", ""))
    config = build_generation_config(
        system_instruction=system_instruction_for_record(record, system_instructions),
        schema=native_views[dataset],
        schema_mode=args.schema_mode,
        temperature=args.temperature,
        max_output_tokens=max_output_tokens_for_record(record, args),
        thinking_budget=args.thinking_budget,
    )
    request = genai_models._GenerateContentParameters_to_mldev(  # noqa: SLF001 - SDK has no public file-request serializer.
        api_client,
        {
            "contents": build_contents(record),
            "config": config,
        },
    )
    request.pop("_url", None)
    return request


def write_batch_requests(args: argparse.Namespace) -> dict:
    input_jsonl = Path(args.input_jsonl).resolve()
    batch_input_jsonl = Path(args.batch_input_jsonl).resolve()
    manifest_json = Path(args.manifest_json).resolve()
    schema_path = Path(args.schema).resolve()
    schema = load_schema(schema_path)
    prompt_views, native_views = schema_views(schema)
    system_instructions = system_instructions_for_args(args, prompt_views)
    client = genai.Client(api_key=api_key_from_env(args, required=False))
    model = model_from_env(args)
    selected = selected_records(args)

    records = []
    batch_input_jsonl.parent.mkdir(parents=True, exist_ok=True)
    with batch_input_jsonl.open("w", encoding="utf-8") as handle:
        for input_row_index, record in selected:
            record_id = normalize(record.get("pilot_record_id", "")) or f"row-{input_row_index}"
            request = batch_request_for_record(
                api_client=client._api_client,  # noqa: SLF001 - needed for SDK wire-format conversion.
                record=record,
                system_instructions=system_instructions,
                native_views=native_views,
                args=args,
            )
            handle.write(json.dumps({"key": record_id, "request": request}, ensure_ascii=False) + "\n")
            records.append(
                {
                    "key": record_id,
                    "input_row_index": input_row_index,
                    "dataset": normalize(record.get("dataset", "")),
                    "study_doi": normalize(record.get("study_doi", "")),
                    "max_output_tokens": max_output_tokens_for_record(record, args),
                }
            )

    manifest = {
        "generated_at_utc": now_utc(),
        "schema_version": "extraction_v1_batch_manifest",
        "status": "prepared",
        "inputs": {
            "input_jsonl": str(input_jsonl),
            "schema": str(schema_path),
            "prompts": {
                "shared": str(Path(args.prompt).resolve()),
                "mechanistic": str(Path(args.mechanistic_prompt).resolve()),
                "disorder": str(Path(args.disorder_prompt).resolve()),
            },
            "schema_mode": args.schema_mode,
            "schema_prompt_view_compact_chars": {
                "mechanistic": len(compact_schema_for_prompt(prompt_views["mechanistic"])),
                "disorder": len(compact_schema_for_prompt(prompt_views["disorder"])),
                "canonical": len(compact_schema_for_prompt(schema)),
            },
            "schema_native_view_compact_chars": {
                "mechanistic": len(compact_schema_for_prompt(native_views["mechanistic"])),
                "disorder": len(compact_schema_for_prompt(native_views["disorder"])),
            },
            "model": model,
            "start_index": max(1, int(args.start_index)),
            "limit": args.limit,
            "max_output_tokens": args.max_output_tokens,
            "mechanistic_max_output_tokens": args.mechanistic_max_output_tokens,
            "disorder_max_output_tokens": args.disorder_max_output_tokens,
            "thinking_budget": args.thinking_budget,
            "resume": getattr(args, "resume", False),
        },
        "outputs": {
            "batch_input_jsonl": str(batch_input_jsonl),
            "manifest_json": str(manifest_json),
        },
        "summary": {
            "prepared_requests": len(records),
            "by_dataset": dict(Counter(record["dataset"] for record in records)),
        },
        "records": records,
    }
    write_json(manifest_json, manifest)
    return manifest


def job_to_dict(job: types.BatchJob) -> dict:
    return job.model_dump(mode="json", exclude_none=True)


def update_job_record(job_json: Path, payload: dict) -> dict:
    existing = {}
    if job_json.exists():
        with job_json.open("r", encoding="utf-8") as handle:
            existing = json.load(handle)
    existing.update(payload)
    existing["updated_at_utc"] = now_utc()
    write_json(job_json, existing)
    return existing


def submit_batch(args: argparse.Namespace) -> dict:
    batch_input_jsonl = Path(args.batch_input_jsonl).resolve()
    manifest_json = Path(args.manifest_json).resolve()
    job_json = Path(args.job_json).resolve()
    if not batch_input_jsonl.exists():
        raise SystemExit(f"Batch input JSONL does not exist: {batch_input_jsonl}")
    if not manifest_json.exists():
        raise SystemExit(f"Batch manifest JSON does not exist: {manifest_json}")
    client = genai.Client(api_key=api_key_from_env(args, required=True))
    model = model_from_env(args)
    display_name = normalize(args.display_name) or f"psychedelics-kg-extraction-{dt.datetime.now().strftime('%Y%m%d-%H%M%S')}"

    uploaded_file = client.files.upload(
        file=batch_input_jsonl,
        config=types.UploadFileConfig(display_name=display_name, mime_type="jsonl"),
    )
    batch_job = client.batches.create(
        model=model,
        src=uploaded_file.name,
        config=types.CreateBatchJobConfig(display_name=display_name),
    )
    payload = {
        "generated_at_utc": now_utc(),
        "schema_version": "extraction_v1_batch_job",
        "status": "submitted",
        "display_name": display_name,
        "model": model,
        "uploaded_file": uploaded_file.model_dump(mode="json", exclude_none=True),
        "batch_job": job_to_dict(batch_job),
        "job_name": batch_job.name,
        "inputs": {
            "batch_input_jsonl": str(batch_input_jsonl),
            "manifest_json": str(manifest_json),
        },
    }
    write_json(job_json, payload)
    return payload


def job_name_from_args(args: argparse.Namespace) -> str:
    if normalize(args.job_name):
        return normalize(args.job_name)
    job_json = Path(args.job_json).resolve()
    if not job_json.exists():
        raise SystemExit(f"Job JSON does not exist and --job-name was not supplied: {job_json}")
    with job_json.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    job_name = normalize(payload.get("job_name", ""))
    if not job_name:
        raise SystemExit(f"No job_name found in {job_json}")
    return job_name


def batch_state_name(job: types.BatchJob) -> str:
    state = getattr(job, "state", None)
    if state is None:
        return ""
    return getattr(state, "name", str(state))


def check_status(args: argparse.Namespace) -> dict:
    client = genai.Client(api_key=api_key_from_env(args, required=True))
    job_name = job_name_from_args(args)
    job = client.batches.get(name=job_name)
    payload = {
        "status": "checked",
        "job_name": job_name,
        "state": batch_state_name(job),
        "batch_job": job_to_dict(job),
    }
    update_job_record(Path(args.job_json).resolve(), payload)
    return payload


def wait_for_completion(args: argparse.Namespace) -> dict:
    client = genai.Client(api_key=api_key_from_env(args, required=True))
    job_name = job_name_from_args(args)
    deadline = time.time() + max(0, args.timeout_sec)
    job = client.batches.get(name=job_name)
    while batch_state_name(job) not in TERMINAL_STATES:
        if args.timeout_sec > 0 and time.time() >= deadline:
            break
        print(f"Current state: {batch_state_name(job)}; waiting {args.poll_interval_sec:.0f}s", flush=True)
        time.sleep(max(1, args.poll_interval_sec))
        job = client.batches.get(name=job_name)
    payload = {
        "status": "checked",
        "job_name": job_name,
        "state": batch_state_name(job),
        "batch_job": job_to_dict(job),
    }
    update_job_record(Path(args.job_json).resolve(), payload)
    return payload


def download_results(args: argparse.Namespace) -> dict:
    client = genai.Client(api_key=api_key_from_env(args, required=True))
    job_name = job_name_from_args(args)
    output_jsonl = Path(args.batch_output_jsonl).resolve()
    job = client.batches.get(name=job_name)
    state = batch_state_name(job)
    if state != "JOB_STATE_SUCCEEDED":
        raise SystemExit(f"Batch job is not succeeded; current state is {state}")
    if not job.dest or not job.dest.file_name:
        raise SystemExit("Batch job succeeded but did not expose a result file")
    file_content = client.files.download(file=job.dest.file_name)
    output_jsonl.parent.mkdir(parents=True, exist_ok=True)
    output_jsonl.write_bytes(file_content)
    payload = {
        "status": "downloaded",
        "job_name": job_name,
        "state": state,
        "result_file_name": job.dest.file_name,
        "batch_output_jsonl": str(output_jsonl),
        "batch_job": job_to_dict(job),
    }
    update_job_record(Path(args.job_json).resolve(), payload)
    return payload


def load_records_by_id(input_jsonl: Path) -> dict[str, dict]:
    out = {}
    for index, record in enumerate(read_jsonl(input_jsonl), start=1):
        record_id = normalize(record.get("pilot_record_id", "")) or f"row-{index}"
        out[record_id] = record
    return out


def response_text(response: dict) -> str:
    if not isinstance(response, dict):
        return ""
    if isinstance(response.get("text"), str):
        return response["text"]
    parts = []
    for candidate in response.get("candidates", []) or []:
        content = candidate.get("content", {}) if isinstance(candidate, dict) else {}
        for part in content.get("parts", []) or []:
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                parts.append(part["text"])
    return "".join(parts)


def batch_line_key(row: dict, fallback_index: int) -> str:
    for path in (("key",), ("metadata", "key"), ("response", "metadata", "key")):
        value: object = row
        for key in path:
            value = value.get(key, "") if isinstance(value, dict) else ""
        text = normalize(value)
        if text:
            return text
    return f"row-{fallback_index}"


def batch_line_response(row: dict) -> dict:
    for key in ("response", "inlineResponse"):
        value = row.get(key)
        if isinstance(value, dict):
            if isinstance(value.get("response"), dict):
                return value["response"]
            return value
    return row if "candidates" in row else {}


def batch_line_error(row: dict) -> str:
    for key in ("error", "status"):
        value = row.get(key)
        if value:
            return json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else normalize(value)
    return ""


def parse_batch_results(args: argparse.Namespace) -> dict:
    batch_output_jsonl = Path(args.batch_output_jsonl).resolve()
    manifest_json = Path(args.manifest_json).resolve()
    out_jsonl = Path(args.out_jsonl).resolve()
    raw_jsonl = Path(args.raw_jsonl).resolve()
    report_json = Path(args.report_json).resolve()
    schema = load_schema(Path(args.schema).resolve())
    validator = Draft7Validator(schema)
    with manifest_json.open("r", encoding="utf-8") as handle:
        manifest = json.load(handle)
    records_by_id = load_records_by_id(Path(manifest["inputs"]["input_jsonl"]).resolve())
    input_row_indexes = {record["key"]: record["input_row_index"] for record in manifest.get("records", [])}

    status_counts: Counter = Counter()
    route_counts: Counter = Counter()
    repair_counts: Counter = Counter()
    total_usage: Counter = Counter()
    raw_rows = []
    parsed_rows = []

    for line_index, row in enumerate(read_jsonl(batch_output_jsonl), start=1):
        key = batch_line_key(row, line_index)
        record = records_by_id.get(key, {})
        response = batch_line_response(row)
        text = response_text(response)
        error = batch_line_error(row)
        raw_row = {
            "generated_at_utc": now_utc(),
            "input_row_index": input_row_indexes.get(key, line_index),
            "input_record_id": key,
            "dataset": normalize(record.get("dataset", "")),
            "study_doi": normalize(record.get("study_doi", "")),
            "status": "error",
            "batch_line_index": line_index,
            "batch_error": error,
            "response_text": text,
            "usage": response.get("usageMetadata") or response.get("usage_metadata") or {},
        }
        try:
            if error:
                raise RuntimeError(error)
            if not record:
                raise RuntimeError(f"No input record found for batch key `{key}`")
            parsed_payload, repair_method = parse_json_response_with_method(text)
            parsed, normalization_changes = normalize_extraction_v1_result(inject_identity_fields(parsed_payload, record))
            errors = schema_error_messages(validator, parsed)
            route = normalize((parsed.get("paper_assessment") or {}).get("route", "")) if isinstance(parsed.get("paper_assessment"), dict) else ""
            status = "ok" if not errors else "schema_error"
            status_counts[status] += 1
            if route:
                route_counts[route] += 1
            repair_counts[repair_method] += 1
            usage = raw_row["usage"]
            for usage_key, value in usage.items():
                if isinstance(value, int):
                    total_usage[usage_key] += value
            raw_row.update(
                {
                    "status": status,
                    "schema_errors": errors,
                    "route": route,
                    "json_repair_method": repair_method,
                    "normalization_changes": normalization_changes,
                    "parsed": parsed,
                }
            )
            parsed_rows.append(parsed)
        except Exception as exc:
            status_counts["error"] += 1
            raw_row.update({"error_type": type(exc).__name__, "error": str(exc)})
        raw_rows.append(raw_row)

    out_jsonl.parent.mkdir(parents=True, exist_ok=True)
    raw_jsonl.parent.mkdir(parents=True, exist_ok=True)
    out_jsonl.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in parsed_rows), encoding="utf-8")
    raw_jsonl.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in raw_rows), encoding="utf-8")

    report = {
        "generated_at_utc": now_utc(),
        "schema_version": "extraction_v1_batch_parse_report",
        "status": "ok" if not status_counts.get("error") and not status_counts.get("schema_error") else "issues_found",
        "inputs": {
            "batch_output_jsonl": str(batch_output_jsonl),
            "manifest_json": str(manifest_json),
            "schema": str(Path(args.schema).resolve()),
        },
        "outputs": {
            "out_jsonl": str(out_jsonl),
            "raw_jsonl": str(raw_jsonl),
            "report_json": str(report_json),
        },
        "summary": {
            "status_counts": dict(status_counts),
            "route_counts": dict(route_counts),
            "json_repair_counts": dict(repair_counts),
            "usage": dict(total_usage),
            "parsed_outputs": len(parsed_rows),
            "raw_outputs": len(raw_rows),
        },
    }
    write_json(report_json, report)
    return report


def add_common_generation_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--input-jsonl", default=str(DEFAULT_INPUT))
    parser.add_argument("--raw-jsonl", default=str(DEFAULT_OUTPUT_DIR / "extraction_v1_batch_raw.jsonl"))
    parser.add_argument("--prompt", default=str(DEFAULT_PROMPT))
    parser.add_argument("--mechanistic-prompt", default=str(DEFAULT_MECHANISTIC_PROMPT))
    parser.add_argument("--disorder-prompt", default=str(DEFAULT_DISORDER_PROMPT))
    parser.add_argument("--schema", default=str(DEFAULT_SCHEMA))
    parser.add_argument("--env-file", default=str(DEFAULT_ENV))
    parser.add_argument("--model", default="", help="Override GEMINI_MODEL from .env")
    parser.add_argument("--schema-mode", choices=SCHEMA_MODES, default="native")
    parser.add_argument("--limit", type=int, default=0, help="Maximum records to prepare; 0 means all")
    parser.add_argument("--start-index", type=int, default=1, help="1-based input row index to start from")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--max-output-tokens", type=int, default=8192)
    parser.add_argument("--mechanistic-max-output-tokens", type=int, default=16384)
    parser.add_argument("--disorder-max-output-tokens", type=int, default=0)
    parser.add_argument(
        "--thinking-budget",
        type=int,
        default=None,
        help="Optional Gemini thinking budget. Omit for model/API default dynamic thinking.",
    )
    parser.add_argument("--resume", action="store_true", help="Skip rows already completed in --raw-jsonl")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run extraction-v1 records through Gemini Batch API")
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare", help="Write Batch API request JSONL")
    add_common_generation_args(prepare)
    prepare.add_argument("--batch-input-jsonl", default=str(default_batch_input_jsonl()))
    prepare.add_argument("--manifest-json", default=str(default_batch_manifest_json()))

    submit = subparsers.add_parser("submit", help="Upload prepared request JSONL and create a batch job")
    submit.add_argument("--batch-input-jsonl", default=str(default_batch_input_jsonl()))
    submit.add_argument("--manifest-json", default=str(default_batch_manifest_json()))
    submit.add_argument("--job-json", default=str(default_batch_job_json()))
    submit.add_argument("--env-file", default=str(DEFAULT_ENV))
    submit.add_argument("--model", default="", help="Override GEMINI_MODEL from .env")
    submit.add_argument("--display-name", default="")

    status = subparsers.add_parser("status", help="Check batch job status")
    status.add_argument("--job-json", default=str(default_batch_job_json()))
    status.add_argument("--job-name", default="")
    status.add_argument("--env-file", default=str(DEFAULT_ENV))

    wait = subparsers.add_parser("wait", help="Poll batch job until terminal state or timeout")
    wait.add_argument("--job-json", default=str(default_batch_job_json()))
    wait.add_argument("--job-name", default="")
    wait.add_argument("--env-file", default=str(DEFAULT_ENV))
    wait.add_argument("--poll-interval-sec", type=float, default=30.0)
    wait.add_argument("--timeout-sec", type=float, default=0.0, help="0 means no timeout")

    download = subparsers.add_parser("download", help="Download completed batch result JSONL")
    download.add_argument("--job-json", default=str(default_batch_job_json()))
    download.add_argument("--job-name", default="")
    download.add_argument("--env-file", default=str(DEFAULT_ENV))
    download.add_argument("--batch-output-jsonl", default=str(default_batch_output_jsonl()))

    parse = subparsers.add_parser("parse", help="Parse batch result JSONL into extraction-v1 outputs")
    parse.add_argument("--batch-output-jsonl", default=str(default_batch_output_jsonl()))
    parse.add_argument("--manifest-json", default=str(default_batch_manifest_json()))
    parse.add_argument("--out-jsonl", default=str(DEFAULT_OUTPUT_DIR / "extraction_v1_batch_outputs.jsonl"))
    parse.add_argument("--raw-jsonl", default=str(DEFAULT_OUTPUT_DIR / "extraction_v1_batch_raw.jsonl"))
    parse.add_argument("--report-json", default=str(DEFAULT_OUTPUT_DIR / "extraction_v1_batch_parse_report.json"))
    parse.add_argument("--schema", default=str(DEFAULT_SCHEMA))

    args = parser.parse_args()
    if args.command == "prepare":
        manifest = write_batch_requests(args)
        print(f"Prepared requests: {manifest['summary']['prepared_requests']}")
        print(f"Batch input JSONL: {manifest['outputs']['batch_input_jsonl']}")
        print(f"Manifest: {manifest['outputs']['manifest_json']}")
        return 0
    if args.command == "submit":
        payload = submit_batch(args)
        print(f"Created batch job: {payload['job_name']}")
        print(f"Uploaded file: {payload['uploaded_file'].get('name', '')}")
        print(f"Job JSON: {Path(args.job_json).resolve()}")
        return 0
    if args.command == "status":
        payload = check_status(args)
        print(f"{payload['job_name']}: {payload['state']}")
        return 0
    if args.command == "wait":
        payload = wait_for_completion(args)
        print(f"{payload['job_name']}: {payload['state']}")
        return 0 if payload["state"] in TERMINAL_STATES else 1
    if args.command == "download":
        payload = download_results(args)
        print(f"Downloaded: {payload['batch_output_jsonl']}")
        return 0
    if args.command == "parse":
        report = parse_batch_results(args)
        print(f"Status counts: {report['summary']['status_counts']}")
        print(f"Route counts: {report['summary']['route_counts']}")
        print(f"Output: {report['outputs']['out_jsonl']}")
        print(f"Raw: {report['outputs']['raw_jsonl']}")
        print(f"Report: {report['outputs']['report_json']}")
        return 1 if report["status"] != "ok" else 0
    raise AssertionError(f"Unhandled command {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
