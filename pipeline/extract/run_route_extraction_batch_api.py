#!/usr/bin/env python3
"""Run routed extraction through the Gemini Batch API.

This prepares one JSONL request file for the asynchronous Batch API, submits it,
and later parses the completed results back into the same accumulating routed
extraction run layout used by the synchronous runner.
"""

from __future__ import annotations

import argparse
from collections import Counter
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import sys

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

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from pipeline.extract.extraction_v1_utils import normalize, read_jsonl, write_json
    from pipeline.extract.route_extraction_profiles import (
        build_system_instruction,
        load_schema_for_profile,
        profile_for_task,
        profile_key_for_task,
        schema_for_assigned_domain,
        schema_for_native,
        schema_in_native_config,
    )
    from pipeline.extract.run_route_extraction import (
        DEFAULT_ENV,
        DEFAULT_GEMINI_MODEL,
        build_contents,
        build_generation_config,
        domain_route_for_task,
        inject_route_identity_fields,
        max_output_tokens_for_task,
        model_for_task,
        parse_json_response,
        safe_run_id,
        schema_error_messages,
        text_depth_for_task,
    )
    from pipeline.extract.run_routed_extraction_batch import (
        appendable_output_paths,
        attempted_task_keys,
        route_key,
        select_next_tasks,
        source_type,
        write_jsonl,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    sys.path.insert(0, str(ROOT))
    from pipeline.extract.extraction_v1_utils import normalize, read_jsonl, write_json
    from pipeline.extract.route_extraction_profiles import (
        build_system_instruction,
        load_schema_for_profile,
        profile_for_task,
        profile_key_for_task,
        schema_for_assigned_domain,
        schema_for_native,
        schema_in_native_config,
    )
    from pipeline.extract.run_route_extraction import (
        DEFAULT_ENV,
        DEFAULT_GEMINI_MODEL,
        build_contents,
        build_generation_config,
        domain_route_for_task,
        inject_route_identity_fields,
        max_output_tokens_for_task,
        model_for_task,
        parse_json_response,
        safe_run_id,
        schema_error_messages,
        text_depth_for_task,
    )
    from pipeline.extract.run_routed_extraction_batch import (
        appendable_output_paths,
        attempted_task_keys,
        route_key,
        select_next_tasks,
        source_type,
        write_jsonl,
    )


DEFAULT_TASKS_JSONL = ROOT / "data" / "processed" / "extraction" / "route_extraction_tasks.jsonl"
TERMINAL_STATES = {"JOB_STATE_SUCCEEDED", "JOB_STATE_FAILED", "JOB_STATE_CANCELLED", "JOB_STATE_EXPIRED"}
ACTIVE_STATES = {"JOB_STATE_PENDING", "JOB_STATE_RUNNING", "JOB_STATE_QUEUED"}
REPORT_SCHEMA_VERSION = "route_extraction_batch_api_report_v1"


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def load_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text or text.startswith("#") or "=" not in text:
            continue
        key, value = text.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def api_key_from_env(args: argparse.Namespace, *, required: bool) -> str:
    env_values = load_dotenv(Path(args.env_file).resolve())
    api_key = env_values.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY", "")
    if required and not api_key:
        raise SystemExit("GEMINI_API_KEY is missing. Add it to project .env or the environment.")
    return api_key or "DUMMY"


def jsonable(value: object) -> object:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", exclude_none=True, by_alias=True)
    if isinstance(value, dict):
        return {key: jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [jsonable(item) for item in value]
    return value


def run_batch_dir(args: argparse.Namespace) -> Path:
    return appendable_output_paths(args.run_id)["run_dir"] / "async_batches"


def batch_paths(args: argparse.Namespace) -> dict[str, Path]:
    batch_dir = run_batch_dir(args)
    batch_id = normalize(args.batch_id) or "batch_001"
    return {
        "batch_dir": batch_dir,
        "manifest_json": batch_dir / f"{batch_id}_manifest.json",
        "requests_jsonl": batch_dir / f"{batch_id}_requests.jsonl",
        "job_json": batch_dir / f"{batch_id}_job.json",
        "results_jsonl": batch_dir / f"{batch_id}_results.jsonl",
        "batch_outputs_jsonl": batch_dir / f"{batch_id}_outputs.jsonl",
        "batch_raw_jsonl": batch_dir / f"{batch_id}_raw.jsonl",
        "parse_report_json": batch_dir / f"{batch_id}_parse_report.json",
    }


def task_by_route_key(tasks: list[dict]) -> dict[str, dict]:
    return {route_key(task): task for task in tasks if route_key(task)}


def selected_for_batch(args: argparse.Namespace) -> list[tuple[int, dict]]:
    tasks = read_jsonl(Path(args.input_jsonl).resolve())
    attempted = attempted_task_keys(appendable_output_paths(args.run_id)["run_dir"], retry_errors=args.retry_errors)
    return select_next_tasks(tasks, attempted, args)


def request_for_task(*, api_client: object, task: dict, args: argparse.Namespace, env_values: dict[str, str]) -> tuple[dict, dict]:
    profile = profile_for_task(task)
    assigned_domain = domain_route_for_task(task)
    assigned_text_depth = text_depth_for_task(task)
    schema = load_schema_for_profile(profile, assigned_domain)
    model_schema = schema_for_assigned_domain(schema, assigned_domain)
    native_schema = schema_for_native(model_schema)
    system_instruction = build_system_instruction(
        profile,
        schema,
        args.schema_mode,
        domain_route=assigned_domain,
        text_depth=assigned_text_depth,
    )
    content = build_contents(task)
    max_tokens = max_output_tokens_for_task(task, profile, args)
    generation_config = build_generation_config(
        system_instruction=system_instruction,
        schema=native_schema,
        schema_mode=args.schema_mode,
        temperature=args.temperature,
        max_output_tokens=max_tokens,
        thinking_budget=args.thinking_budget,
    )
    request = genai_models._GenerateContentParameters_to_mldev(  # noqa: SLF001 - SDK has no public Batch serializer.
        api_client,
        {
            "contents": content,
            "config": generation_config,
        },
    )
    request.pop("_url", None)
    metadata = {
        "prompt_profile": profile.prompt_profile,
        "schema_profile": profile.schema_profile,
        "domain_route": assigned_domain,
        "text_depth": assigned_text_depth,
        "source_type": source_type(task),
        "content_chars": len(content),
        "approx_input_tokens_char4": max(1, len(content) // 4),
        "max_output_tokens": max_tokens,
        "model": model_for_task(args, task, env_values),
        "native_schema": schema_in_native_config(args.schema_mode),
    }
    return jsonable(request), metadata


def write_batch_requests(args: argparse.Namespace) -> dict:
    paths = batch_paths(args)
    paths["batch_dir"].mkdir(parents=True, exist_ok=True)
    client = genai.Client(api_key=api_key_from_env(args, required=False))
    env_values = load_dotenv(Path(args.env_file).resolve())
    selected = selected_for_batch(args)

    records: list[dict] = []
    with paths["requests_jsonl"].open("w", encoding="utf-8") as handle:
        for position, (input_row_index, task) in enumerate(selected, start=1):
            key = f"{safe_run_id(args.run_id)}-{normalize(args.batch_id)}-{position:06d}"
            request, request_metadata = request_for_task(
                api_client=client._api_client,  # noqa: SLF001
                task=task,
                args=args,
                env_values=env_values,
            )
            handle.write(json.dumps({"key": key, "request": request}, ensure_ascii=False) + "\n")
            prompt_profile, schema_profile = profile_key_for_task(task)
            records.append(
                {
                    "key": key,
                    "input_row_index": input_row_index,
                    "task_id": normalize(task.get("task_id", "")),
                    "route_id": normalize(task.get("route_id", "")),
                    "study_doi": normalize(task.get("study_doi", "")),
                    "prompt_profile": prompt_profile,
                    "schema_profile": schema_profile,
                    **request_metadata,
                }
            )

    manifest = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "generated_at_utc": now_utc(),
        "status": "prepared",
        "run_id": safe_run_id(args.run_id),
        "batch_id": normalize(args.batch_id),
        "inputs": {
            "input_jsonl": str(Path(args.input_jsonl).resolve()),
            "model": normalize(args.model) or "task_depth_defaults",
            "schema_mode": args.schema_mode,
            "batch_size": args.batch_size,
            "shuffle": args.shuffle,
            "seed": args.seed,
            "temperature": args.temperature,
            "thinking_budget": args.thinking_budget,
            "max_output_tokens_override": args.max_output_tokens,
            "filters": {
                "prompt_profile": args.prompt_profile,
                "schema_profile": args.schema_profile,
                "domain_route": args.domain_route,
                "text_depth": args.text_depth,
                "source_type": args.source_type,
            },
        },
        "outputs": {name: str(path) for name, path in paths.items() if name != "batch_dir"},
        "summary": {
            "prepared_requests": len(records),
            "approx_input_tokens_char4": sum(row["approx_input_tokens_char4"] for row in records),
            "content_chars": sum(row["content_chars"] for row in records),
            "request_jsonl_bytes": paths["requests_jsonl"].stat().st_size if paths["requests_jsonl"].exists() else 0,
            "by_prompt_profile": dict(Counter(row["prompt_profile"] for row in records)),
            "by_schema_profile": dict(Counter(row["schema_profile"] for row in records)),
            "by_domain_route": dict(Counter(row["domain_route"] for row in records)),
            "by_text_depth": dict(Counter(row["text_depth"] for row in records)),
            "by_source_type": dict(Counter(row["source_type"] for row in records)),
            "by_model": dict(Counter(row["model"] for row in records)),
        },
        "records": records,
    }
    write_json(paths["manifest_json"], manifest)
    return manifest


def job_to_dict(job: types.BatchJob) -> dict:
    return job.model_dump(mode="json", exclude_none=True)


def update_job_record(job_json: Path, payload: dict) -> dict:
    existing = {}
    if job_json.exists():
        existing = json.loads(job_json.read_text(encoding="utf-8"))
    existing.update(payload)
    existing["updated_at_utc"] = now_utc()
    write_json(job_json, existing)
    return existing


def submit_batch(args: argparse.Namespace) -> dict:
    paths = batch_paths(args)
    if not paths["requests_jsonl"].exists():
        raise SystemExit(f"Batch request JSONL does not exist: {paths['requests_jsonl']}")
    if not paths["manifest_json"].exists():
        raise SystemExit(f"Batch manifest does not exist: {paths['manifest_json']}")
    client = genai.Client(api_key=api_key_from_env(args, required=True))
    display_name = normalize(args.display_name) or f"psychedelics-kg-{safe_run_id(args.run_id)}-{normalize(args.batch_id)}"
    model = normalize(args.model) or DEFAULT_GEMINI_MODEL
    uploaded_file = client.files.upload(
        file=paths["requests_jsonl"],
        config=types.UploadFileConfig(display_name=display_name, mime_type="jsonl"),
    )
    batch_job = client.batches.create(
        model=model,
        src=uploaded_file.name,
        config=types.CreateBatchJobConfig(display_name=display_name),
    )
    payload = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "generated_at_utc": now_utc(),
        "status": "submitted",
        "run_id": safe_run_id(args.run_id),
        "batch_id": normalize(args.batch_id),
        "display_name": display_name,
        "model": model,
        "uploaded_file": uploaded_file.model_dump(mode="json", exclude_none=True),
        "batch_job": job_to_dict(batch_job),
        "job_name": batch_job.name,
        "inputs": {
            "requests_jsonl": str(paths["requests_jsonl"]),
            "manifest_json": str(paths["manifest_json"]),
        },
    }
    write_json(paths["job_json"], payload)
    return payload


def job_name_from_args(args: argparse.Namespace) -> str:
    if normalize(args.job_name):
        return normalize(args.job_name)
    job_json = batch_paths(args)["job_json"]
    if not job_json.exists():
        raise SystemExit(f"Job JSON does not exist and --job-name was not supplied: {job_json}")
    payload = json.loads(job_json.read_text(encoding="utf-8"))
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
    update_job_record(batch_paths(args)["job_json"], payload)
    return payload


def download_results(args: argparse.Namespace) -> dict:
    client = genai.Client(api_key=api_key_from_env(args, required=True))
    job_name = job_name_from_args(args)
    job = client.batches.get(name=job_name)
    state = batch_state_name(job)
    if state != "JOB_STATE_SUCCEEDED":
        raise SystemExit(f"Batch job is not succeeded; current state is {state}")
    if not job.dest or not job.dest.file_name:
        raise SystemExit("Batch job succeeded but did not expose a result file")
    paths = batch_paths(args)
    file_content = client.files.download(file=job.dest.file_name)
    paths["results_jsonl"].parent.mkdir(parents=True, exist_ok=True)
    paths["results_jsonl"].write_bytes(file_content)
    payload = {
        "status": "downloaded",
        "job_name": job_name,
        "state": state,
        "result_file_name": job.dest.file_name,
        "results_jsonl": str(paths["results_jsonl"]),
        "batch_job": job_to_dict(job),
    }
    update_job_record(paths["job_json"], payload)
    return payload


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


def records_by_key(manifest: dict) -> dict[str, dict]:
    return {
        normalize(record.get("key", "")): record
        for record in manifest.get("records", [])
        if normalize(record.get("key", ""))
    }


def existing_route_keys(path: Path) -> set[str]:
    return {route_key(row) for row in read_jsonl(path) if route_key(row)} if path.exists() else set()


def append_unique_jsonl(path: Path, rows: list[dict]) -> int:
    existing = existing_route_keys(path)
    new_rows = [row for row in rows if route_key(row) and route_key(row) not in existing]
    if not new_rows:
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for row in new_rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    return len(new_rows)


def run_command(cmd: list[str]) -> dict:
    print(" ".join(cmd), flush=True)
    completed = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)
    if completed.stdout:
        print(completed.stdout, end="", flush=True)
    if completed.stderr:
        print(completed.stderr, end="", file=sys.stderr, flush=True)
    return {"cmd": cmd, "returncode": completed.returncode, "stdout": completed.stdout, "stderr": completed.stderr}


def rebuild_run_tables(args: argparse.Namespace) -> list[dict]:
    paths = appendable_output_paths(args.run_id)
    commands = [
        [
            sys.executable,
            "pipeline/kg/convert_routed_extractions_to_evidence_rows.py",
            "--run-id",
            safe_run_id(args.run_id),
            "--input-jsonl",
            str(paths["outputs_jsonl"]),
            "--tasks-jsonl",
            str(Path(args.input_jsonl).resolve()),
        ],
        [
            sys.executable,
            "pipeline/kg/build_evidence_tables.py",
            "--source-preset",
            "routed",
            "--run-id",
            safe_run_id(args.run_id),
        ],
    ]
    results = []
    for cmd in commands:
        result = run_command(cmd)
        results.append(result)
        if result["returncode"] != 0:
            raise SystemExit(result["returncode"])
    return results


def parse_batch_results(args: argparse.Namespace) -> dict:
    paths = batch_paths(args)
    manifest = json.loads(paths["manifest_json"].read_text(encoding="utf-8"))
    manifest_by_key = records_by_key(manifest)
    tasks = task_by_route_key(read_jsonl(Path(args.input_jsonl).resolve()))
    env_values = load_dotenv(Path(args.env_file).resolve())

    raw_rows: list[dict] = []
    parsed_rows: list[dict] = []
    status_counts: Counter = Counter()
    usage_totals: Counter = Counter()
    for line_index, row in enumerate(read_jsonl(paths["results_jsonl"]), start=1):
        key = batch_line_key(row, line_index)
        manifest_record = manifest_by_key.get(key, {})
        task = tasks.get(normalize(manifest_record.get("route_id", "")), {})
        response = batch_line_response(row)
        text = response_text(response)
        usage = response.get("usageMetadata") or response.get("usage_metadata") or {}
        error = batch_line_error(row)
        raw_row = {
            "generated_at_utc": now_utc(),
            "input_row_index": manifest_record.get("input_row_index", line_index),
            "task_id": normalize(manifest_record.get("task_id", "")),
            "route_id": normalize(manifest_record.get("route_id", "")),
            "study_doi": normalize(manifest_record.get("study_doi", "")),
            "prompt_profile": normalize(manifest_record.get("prompt_profile", "")),
            "schema_profile": normalize(manifest_record.get("schema_profile", "")),
            "model": normalize(manifest_record.get("model", "")) or (model_for_task(args, task, env_values) if task else ""),
            "status": "error",
            "raw_text": text,
            "usage": usage,
            "batch_key": key,
            "batch_line_index": line_index,
            "batch_error": error,
        }
        output_row: dict | None = None
        try:
            if error:
                raise RuntimeError(error)
            if not manifest_record:
                raise RuntimeError(f"No manifest record found for batch key `{key}`")
            if not task:
                raise RuntimeError(f"No task found for route_id `{manifest_record.get('route_id', '')}`")
            profile = profile_for_task(task)
            schema = load_schema_for_profile(profile, domain_route_for_task(task))
            model_schema = schema_for_assigned_domain(schema, domain_route_for_task(task))
            validator = Draft7Validator(model_schema)
            parsed, parse_method = parse_json_response(text)
            result = inject_route_identity_fields(parsed, task, profile)
            schema_errors = schema_error_messages(validator, result)
            raw_row.update(
                {
                    "status": "schema_error" if schema_errors else "ok",
                    "parse_method": parse_method,
                    "schema_errors": schema_errors,
                }
            )
            output_row = {
                "task_id": raw_row["task_id"],
                "route_id": raw_row["route_id"],
                "prompt_profile": raw_row["prompt_profile"],
                "schema_profile": raw_row["schema_profile"],
                "status": raw_row["status"],
                "result": result,
                "schema_errors": schema_errors,
            }
            for usage_key, value in usage.items():
                if isinstance(value, int):
                    usage_totals[usage_key] += value
        except Exception as exc:
            raw_row.update({"status": "error", "error": str(exc), "error_type": type(exc).__name__})
        status_counts[raw_row["status"]] += 1
        raw_rows.append(raw_row)
        if output_row is not None:
            parsed_rows.append(output_row)

    write_jsonl(paths["batch_raw_jsonl"], raw_rows)
    write_jsonl(paths["batch_outputs_jsonl"], parsed_rows)
    run_paths = appendable_output_paths(args.run_id)
    appended_raw = append_unique_jsonl(run_paths["raw_jsonl"], raw_rows)
    appended_outputs = append_unique_jsonl(run_paths["outputs_jsonl"], parsed_rows)
    commands = [] if args.skip_rebuild else rebuild_run_tables(args)
    report = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "generated_at_utc": now_utc(),
        "status": "ok" if not status_counts.get("error") else "issues_found",
        "run_id": safe_run_id(args.run_id),
        "batch_id": normalize(args.batch_id),
        "inputs": {
            "results_jsonl": str(paths["results_jsonl"]),
            "manifest_json": str(paths["manifest_json"]),
            "input_jsonl": str(Path(args.input_jsonl).resolve()),
        },
        "outputs": {
            "batch_raw_jsonl": str(paths["batch_raw_jsonl"]),
            "batch_outputs_jsonl": str(paths["batch_outputs_jsonl"]),
            "run_raw_jsonl": str(run_paths["raw_jsonl"]),
            "run_outputs_jsonl": str(run_paths["outputs_jsonl"]),
            "parse_report_json": str(paths["parse_report_json"]),
        },
        "summary": {
            "batch_result_rows": len(raw_rows),
            "parsed_output_rows": len(parsed_rows),
            "appended_raw_rows": appended_raw,
            "appended_output_rows": appended_outputs,
            "status_counts": dict(status_counts),
            "usage": dict(usage_totals),
        },
        "commands": commands,
    }
    write_json(paths["parse_report_json"], report)
    return report


def add_selection_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--batch-id", default="batch_001")
    parser.add_argument("--input-jsonl", type=Path, default=DEFAULT_TASKS_JSONL)
    parser.add_argument("--batch-size", type=int, default=5000)
    parser.add_argument("--shuffle", action="store_true")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--retry-errors", action="store_true")
    parser.add_argument("--include-not-ready", action="store_true")
    parser.add_argument("--include-scaffold-profiles", action="store_true")
    parser.add_argument("--prompt-profile", action="append", default=[])
    parser.add_argument("--schema-profile", action="append", default=[])
    parser.add_argument("--domain-route", action="append", default=[])
    parser.add_argument("--text-depth", action="append", default=[])
    parser.add_argument("--source-type", action="append", default=[])
    parser.add_argument("--route-id", action="append", default=[])
    parser.add_argument("--doi", action="append", default=[])
    parser.add_argument("--env-file", default=str(DEFAULT_ENV))
    parser.add_argument("--model", default="")
    parser.add_argument("--schema-mode", choices=["native", "prompt"], default="native")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--thinking-budget", type=int, default=0)
    parser.add_argument("--max-output-tokens", type=int, default=0)
    parser.add_argument("--sleep-sec", type=float, default=0.0)


def normalize_list(values: list[str]) -> list[str]:
    return [normalize(value) for value in values if normalize(value)]


def normalize_common_args(args: argparse.Namespace) -> argparse.Namespace:
    args.run_id = safe_run_id(args.run_id)
    args.batch_id = normalize(args.batch_id) or "batch_001"
    for field in ("prompt_profile", "schema_profile", "domain_route", "text_depth", "source_type", "route_id"):
        if hasattr(args, field):
            setattr(args, field, normalize_list(getattr(args, field)))
    if hasattr(args, "doi"):
        args.doi = [normalize(doi).lower() for doi in args.doi if normalize(doi)]
    args.only_ready = not getattr(args, "include_not_ready", False)
    return args


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare", help="Write Batch API request JSONL.")
    add_selection_args(prepare)

    submit = subparsers.add_parser("submit", help="Upload prepared JSONL and create a batch job.")
    submit.add_argument("--run-id", required=True)
    submit.add_argument("--batch-id", default="batch_001")
    submit.add_argument("--env-file", default=str(DEFAULT_ENV))
    submit.add_argument("--model", default=DEFAULT_GEMINI_MODEL)
    submit.add_argument("--display-name", default="")

    status = subparsers.add_parser("status", help="Check batch job status.")
    status.add_argument("--run-id", required=True)
    status.add_argument("--batch-id", default="batch_001")
    status.add_argument("--job-name", default="")
    status.add_argument("--env-file", default=str(DEFAULT_ENV))

    download = subparsers.add_parser("download", help="Download completed batch results.")
    download.add_argument("--run-id", required=True)
    download.add_argument("--batch-id", default="batch_001")
    download.add_argument("--job-name", default="")
    download.add_argument("--env-file", default=str(DEFAULT_ENV))

    parse = subparsers.add_parser("parse", help="Parse downloaded results and rebuild versioned KG tables.")
    parse.add_argument("--run-id", required=True)
    parse.add_argument("--batch-id", default="batch_001")
    parse.add_argument("--input-jsonl", type=Path, default=DEFAULT_TASKS_JSONL)
    parse.add_argument("--env-file", default=str(DEFAULT_ENV))
    parse.add_argument("--model", default="")
    parse.add_argument("--schema-mode", choices=["native", "prompt"], default="native")
    parse.add_argument("--temperature", type=float, default=0.0)
    parse.add_argument("--thinking-budget", type=int, default=0)
    parse.add_argument("--max-output-tokens", type=int, default=0)
    parse.add_argument("--sleep-sec", type=float, default=0.0)
    parse.add_argument("--skip-rebuild", action="store_true")

    return normalize_common_args(parser.parse_args())


def main() -> int:
    args = parse_args()
    if args.command == "prepare":
        report = write_batch_requests(args)
        print(f"Prepared: {report['summary']['prepared_requests']:,}")
        print(f"Request JSONL bytes: {report['summary']['request_jsonl_bytes']:,}")
        print(f"Approx input tokens: {report['summary']['approx_input_tokens_char4']:,}")
        print(f"Manifest: {report['outputs']['manifest_json']}")
    elif args.command == "submit":
        report = submit_batch(args)
        print(f"Submitted: {report['job_name']}")
        print(f"Job JSON: {batch_paths(args)['job_json']}")
    elif args.command == "status":
        report = check_status(args)
        print(f"State: {report['state']}")
    elif args.command == "download":
        report = download_results(args)
        print(f"Downloaded: {report['results_jsonl']}")
    elif args.command == "parse":
        report = parse_batch_results(args)
        print(f"Status: {report['status']}")
        print(f"Parsed outputs: {report['summary']['parsed_output_rows']:,}")
        print(f"Appended outputs: {report['summary']['appended_output_rows']:,}")
        print(f"Report: {report['outputs']['parse_report_json']}")
    else:  # pragma: no cover - argparse enforces commands.
        raise SystemExit(f"Unknown command: {args.command}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
