#!/usr/bin/env python3
"""Run paper-centered review extraction through the Gemini Batch API."""

from __future__ import annotations

import argparse
from collections import Counter
import datetime as dt
import json
import os
from pathlib import Path
import random
import sys

try:
    from google import genai
    from google.genai import models as genai_models
    from google.genai import types
except ModuleNotFoundError as err:  # pragma: no cover - environment guard
    raise SystemExit("google-genai is required for Gemini batch extraction") from err

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.extract.io_utils import normalize, read_jsonl, write_json
from pipeline.extract.route_extraction_profiles import schema_for_native
from pipeline.extract.run_review_relationship_extraction import (
    ABSTRACT_PROMPT,
    BUNDLE_SCHEMA,
    DEFAULT_RUN_ROOT,
    DEFAULT_TASKS,
    FULL_TEXT_PROMPT,
    archive_run_inputs,
    bundle_semantic_errors,
    inject_fixed_fields,
    load_schema,
    model_contents,
    packet_for_task,
    packet_lookup,
    schema_errors,
)
from pipeline.extract.run_route_extraction import (
    DEFAULT_ENV,
    DEFAULT_GEMINI_MODEL,
    build_generation_config,
    parse_json_response,
    safe_run_id,
)


REPORT_SCHEMA_VERSION = "review_relationship_batch_api_report_v1"


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


def run_dir(args: argparse.Namespace) -> Path:
    return DEFAULT_RUN_ROOT / safe_run_id(args.run_id)


def batch_paths(args: argparse.Namespace) -> dict[str, Path]:
    batch_dir = run_dir(args) / "async_batches"
    batch_id = normalize(args.batch_id) or "batch_001"
    return {
        "batch_dir": batch_dir,
        "snapshot_owner": batch_dir / batch_id,
        "selected_tasks_jsonl": batch_dir / f"{batch_id}_tasks.jsonl",
        "manifest_json": batch_dir / f"{batch_id}_manifest.json",
        "requests_jsonl": batch_dir / f"{batch_id}_requests.jsonl",
        "job_json": batch_dir / f"{batch_id}_job.json",
        "results_jsonl": batch_dir / f"{batch_id}_results.jsonl",
        "parsed_jsonl": batch_dir / f"{batch_id}_paper_relationship_bundles.jsonl",
        "raw_jsonl": batch_dir / f"{batch_id}_raw.jsonl",
        "parse_report_json": batch_dir / f"{batch_id}_parse_report.json",
        "run_bundles_jsonl": run_dir(args) / "paper_relationship_bundles.jsonl",
        "run_model_log_jsonl": run_dir(args) / "model_call_log.jsonl",
    }


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def successful_dois(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return {
        normalize(row.get("study_doi", "")).lower()
        for row in read_jsonl(path)
        if normalize(row.get("status", "")) == "ok"
    }


def previously_attempted_dois(args: argparse.Namespace) -> set[str]:
    """Return papers already assigned to another async batch in this run."""

    paths = batch_paths(args)
    current_tasks = paths["selected_tasks_jsonl"].resolve()
    attempted: set[str] = set()
    for path in paths["batch_dir"].glob("*_tasks.jsonl"):
        if path.resolve() == current_tasks:
            continue
        attempted.update(
            normalize(row.get("study_doi", "")).lower()
            for row in read_jsonl(path)
            if normalize(row.get("study_doi", ""))
        )
    return attempted


def selected_tasks(args: argparse.Namespace) -> list[tuple[int, dict]]:
    tasks = read_jsonl(Path(args.tasks_jsonl).resolve())
    excluded = successful_dois(batch_paths(args)["run_bundles_jsonl"])
    if not args.retry_attempted:
        excluded.update(previously_attempted_dois(args))
    for path in args.exclude_output_jsonl:
        excluded.update(successful_dois(Path(path).resolve()))
    candidates = [
        (index, task)
        for index, task in enumerate(tasks, start=1)
        if normalize(task.get("task_status", "")) == "ready_for_model"
        and normalize(task.get("study_doi", "")).lower() not in excluded
    ]
    if args.shuffle:
        random.Random(args.seed).shuffle(candidates)
    return candidates[: max(0, args.batch_size)]


def archived_artifacts(snapshot: dict) -> dict[str, Path]:
    return {
        str(Path(item["source_path"]).resolve()): Path(item["archived_path"])
        for item in snapshot["artifacts"]
    }


def request_for_task(
    *,
    api_client: object,
    task: dict,
    packet: dict | None,
    prompt_path: Path,
    schema_path: Path,
    args: argparse.Namespace,
) -> tuple[dict, dict]:
    schema = load_schema(schema_path)
    prompt = prompt_path.read_text(encoding="utf-8").strip()
    contents = model_contents(task, packet)
    config = build_generation_config(
        system_instruction=prompt,
        schema=schema_for_native(schema),
        schema_mode="native",
        temperature=0.0,
        max_output_tokens=args.max_output_tokens,
        thinking_budget=args.thinking_budget,
    )
    request = genai_models._GenerateContentParameters_to_mldev(  # noqa: SLF001 - SDK has no public serializer.
        api_client,
        {"contents": contents, "config": config},
    )
    request.pop("_url", None)
    return jsonable(request), {
        "content_chars": len(contents),
        "approx_input_tokens_char4": max(1, len(contents) // 4),
    }


def prepare_batch(args: argparse.Namespace) -> dict:
    paths = batch_paths(args)
    if (paths["manifest_json"].exists() or paths["requests_jsonl"].exists()) and not args.overwrite:
        raise SystemExit("This batch ID already has prepared files. Use another batch ID or --overwrite.")
    paths["batch_dir"].mkdir(parents=True, exist_ok=True)
    selected = selected_tasks(args)
    if len(selected) != args.batch_size:
        raise SystemExit(f"Requested {args.batch_size} tasks but only {len(selected)} were available")
    selected_rows = [task for _, task in selected]
    write_jsonl(paths["selected_tasks_jsonl"], selected_rows)

    snapshot = archive_run_inputs(paths["snapshot_owner"], paths["selected_tasks_jsonl"].resolve(), args)
    archived = archived_artifacts(snapshot)
    full_text_prompt = archived[str(Path(args.full_text_prompt).resolve())]
    abstract_prompt = archived[str(Path(args.abstract_prompt).resolve())]
    bundle_schema = archived[str(Path(args.bundle_schema).resolve())]
    packets = packet_lookup(selected_rows)
    client = genai.Client(api_key=api_key_from_env(args, required=False))

    records: list[dict] = []
    with paths["requests_jsonl"].open("w", encoding="utf-8") as handle:
        for position, (input_row_index, task) in enumerate(selected, start=1):
            depth = normalize(task.get("text_depth", ""))
            prompt_path = full_text_prompt if depth == "article_text" else abstract_prompt
            request, request_metadata = request_for_task(
                api_client=client._api_client,  # noqa: SLF001
                task=task,
                packet=packet_for_task(task, packets),
                prompt_path=prompt_path,
                schema_path=bundle_schema,
                args=args,
            )
            key = f"{safe_run_id(args.run_id)}-{normalize(args.batch_id)}-{position:06d}"
            handle.write(json.dumps({"key": key, "request": request}, ensure_ascii=False) + "\n")
            records.append(
                {
                    "key": key,
                    "input_row_index": input_row_index,
                    "task_id": normalize(task.get("task_id", "")),
                    "study_doi": normalize(task.get("study_doi", "")).lower(),
                    "study_title": normalize(task.get("paper_metadata", {}).get("study_title", "")),
                    "text_depth": depth,
                    "source_fingerprint": normalize(task.get("source", {}).get("source_fingerprint", "")),
                    "model": args.model,
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
            "tasks_jsonl": str(Path(args.tasks_jsonl).resolve()),
            "selected_tasks_jsonl": str(paths["selected_tasks_jsonl"]),
            "input_snapshot_manifest": str(paths["snapshot_owner"] / "input_snapshot" / "manifest.json"),
            "model": args.model,
            "batch_size": args.batch_size,
            "shuffle": args.shuffle,
            "seed": args.seed,
            "excluded_output_jsonl": [str(Path(path).resolve()) for path in args.exclude_output_jsonl],
        },
        "outputs": {
            "requests_jsonl": str(paths["requests_jsonl"]),
            "manifest_json": str(paths["manifest_json"]),
        },
        "summary": {
            "prepared_requests": len(records),
            "request_jsonl_bytes": paths["requests_jsonl"].stat().st_size,
            "content_chars": sum(row["content_chars"] for row in records),
            "approx_input_tokens_char4": sum(row["approx_input_tokens_char4"] for row in records),
            "by_text_depth": dict(Counter(row["text_depth"] for row in records)),
        },
        "records": records,
    }
    write_json(paths["manifest_json"], manifest)
    return manifest


def job_to_dict(job: types.BatchJob) -> dict:
    return job.model_dump(mode="json", exclude_none=True)


def update_job_record(path: Path, payload: dict) -> dict:
    existing = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    existing.update(payload)
    existing["updated_at_utc"] = now_utc()
    write_json(path, existing)
    return existing


def submit_batch(args: argparse.Namespace) -> dict:
    paths = batch_paths(args)
    if not paths["requests_jsonl"].exists() or not paths["manifest_json"].exists():
        raise SystemExit("Prepare the batch before submitting it.")
    client = genai.Client(api_key=api_key_from_env(args, required=True))
    display_name = normalize(args.display_name) or f"psychedelics-kg-{safe_run_id(args.run_id)}-{normalize(args.batch_id)}"
    uploaded_file = client.files.upload(
        file=paths["requests_jsonl"],
        config=types.UploadFileConfig(display_name=display_name, mime_type="jsonl"),
    )
    batch_job = client.batches.create(
        model=args.model,
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
        "model": args.model,
        "uploaded_file": uploaded_file.model_dump(mode="json", exclude_none=True),
        "batch_job": job_to_dict(batch_job),
        "job_name": batch_job.name,
    }
    write_json(paths["job_json"], payload)
    return payload


def job_name_from_args(args: argparse.Namespace) -> str:
    if normalize(args.job_name):
        return normalize(args.job_name)
    path = batch_paths(args)["job_json"]
    if not path.exists():
        raise SystemExit(f"Job record does not exist: {path}")
    name = normalize(json.loads(path.read_text(encoding="utf-8")).get("job_name", ""))
    if not name:
        raise SystemExit(f"No job_name found in {path}")
    return name


def batch_state_name(job: types.BatchJob) -> str:
    state = getattr(job, "state", None)
    return getattr(state, "name", str(state)) if state is not None else ""


def check_status(args: argparse.Namespace) -> dict:
    client = genai.Client(api_key=api_key_from_env(args, required=True))
    name = job_name_from_args(args)
    job = client.batches.get(name=name)
    payload = {"status": "checked", "job_name": name, "state": batch_state_name(job), "batch_job": job_to_dict(job)}
    update_job_record(batch_paths(args)["job_json"], payload)
    return payload


def download_results(args: argparse.Namespace) -> dict:
    client = genai.Client(api_key=api_key_from_env(args, required=True))
    name = job_name_from_args(args)
    job = client.batches.get(name=name)
    state = batch_state_name(job)
    if state != "JOB_STATE_SUCCEEDED":
        raise SystemExit(f"Batch job is not complete; current state is {state}")
    if not job.dest or not job.dest.file_name:
        raise SystemExit("Completed batch did not expose a result file")
    paths = batch_paths(args)
    paths["results_jsonl"].write_bytes(client.files.download(file=job.dest.file_name))
    payload = {
        "status": "downloaded",
        "job_name": name,
        "state": state,
        "result_file_name": job.dest.file_name,
        "results_jsonl": str(paths["results_jsonl"]),
    }
    update_job_record(paths["job_json"], payload)
    return payload


def batch_line_key(row: dict, fallback_index: int) -> str:
    for path in (("key",), ("metadata", "key"), ("response", "metadata", "key")):
        value: object = row
        for key in path:
            value = value.get(key, "") if isinstance(value, dict) else ""
        if normalize(value):
            return normalize(value)
    return f"row-{fallback_index}"


def batch_line_response(row: dict) -> dict:
    for key in ("response", "inlineResponse"):
        value = row.get(key)
        if isinstance(value, dict):
            return value.get("response", value) if isinstance(value.get("response", value), dict) else {}
    return row if "candidates" in row else {}


def response_text(response: dict) -> str:
    if isinstance(response.get("text"), str):
        return response["text"]
    parts: list[str] = []
    for candidate in response.get("candidates", []) or []:
        content = candidate.get("content", {}) if isinstance(candidate, dict) else {}
        for part in content.get("parts", []) or []:
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                parts.append(part["text"])
    return "".join(parts)


def batch_line_error(row: dict) -> str:
    for key in ("error", "status"):
        value = row.get(key)
        if value:
            return json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else normalize(value)
    return ""


def upsert_rows(path: Path, rows: list[dict]) -> int:
    existing_rows = read_jsonl(path) if path.exists() else []
    incoming = {
        (normalize(row.get("task_id", "")), normalize(row.get("status", ""))): row
        for row in rows
        if normalize(row.get("task_id", ""))
    }
    merged: list[dict] = []
    used: set[tuple[str, str]] = set()
    for row in existing_rows:
        key = (normalize(row.get("task_id", "")), normalize(row.get("status", "")))
        if key in incoming:
            merged.append(incoming[key])
            used.add(key)
        else:
            merged.append(row)
    merged.extend(row for key, row in incoming.items() if key not in used)
    write_jsonl(path, merged)
    return len(incoming)


def parse_results(args: argparse.Namespace) -> dict:
    paths = batch_paths(args)
    manifest = json.loads(paths["manifest_json"].read_text(encoding="utf-8"))
    records = {normalize(row.get("key", "")): row for row in manifest.get("records", [])}
    tasks = {normalize(row.get("task_id", "")): row for row in read_jsonl(paths["selected_tasks_jsonl"])}
    snapshot_manifest = json.loads((paths["snapshot_owner"] / "input_snapshot" / "manifest.json").read_text(encoding="utf-8"))
    schema_path = next(
        Path(item["archived_path"])
        for item in snapshot_manifest["artifacts"]
        if item["group"] == "schemas"
    )
    schema = load_schema(schema_path)

    outputs: list[dict] = []
    raw_rows: list[dict] = []
    status_counts: Counter = Counter()
    usage_totals: Counter = Counter()
    for line_index, row in enumerate(read_jsonl(paths["results_jsonl"]), start=1):
        key = batch_line_key(row, line_index)
        record = records.get(key, {})
        task = tasks.get(normalize(record.get("task_id", "")), {})
        response = batch_line_response(row)
        text = response_text(response)
        error = batch_line_error(row)
        usage = response.get("usageMetadata") or response.get("usage_metadata") or {}
        raw = {
            "batch_key": key,
            "task_id": normalize(record.get("task_id", "")),
            "study_doi": normalize(record.get("study_doi", "")),
            "text_depth": normalize(record.get("text_depth", "")),
            "raw_text": text,
            "usage": usage,
            "status": "error",
        }
        try:
            if error:
                raise RuntimeError(error)
            if not record or not task:
                raise RuntimeError("Batch result could not be matched to its task")
            parsed, parse_method = parse_json_response(text)
            result = inject_fixed_fields(parsed, task)
            validation_errors = schema_errors(schema, result)
            qa_flags = bundle_semantic_errors(result) if not validation_errors else []
            status = "schema_error" if validation_errors else "ok"
            raw.update({"status": status, "parse_method": parse_method, "schema_errors": validation_errors})
            outputs.append(
                {
                    "task_id": raw["task_id"],
                    "study_doi": raw["study_doi"],
                    "study_title": normalize(record.get("study_title", "")),
                    "text_depth": raw["text_depth"],
                    "status": status,
                    "result": result,
                    "schema_errors": validation_errors,
                    "qa_flags": qa_flags,
                }
            )
        except Exception as exc:
            raw.update({"status": "error", "error": str(exc), "error_type": type(exc).__name__})
        status_counts[raw["status"]] += 1
        for usage_key, value in usage.items():
            if isinstance(value, (int, float)):
                usage_totals[usage_key] += value
        raw_rows.append(raw)

    write_jsonl(paths["parsed_jsonl"], outputs)
    write_jsonl(paths["raw_jsonl"], raw_rows)
    written_outputs = upsert_rows(paths["run_bundles_jsonl"], outputs)
    written_logs = upsert_rows(paths["run_model_log_jsonl"], raw_rows)
    report = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "generated_at_utc": now_utc(),
        "status": "ok" if not status_counts.get("error") and not status_counts.get("schema_error") else "issues_found",
        "run_id": safe_run_id(args.run_id),
        "batch_id": normalize(args.batch_id),
        "summary": {
            "result_rows": len(raw_rows),
            "parsed_rows": len(outputs),
            "written_outputs": written_outputs,
            "written_model_logs": written_logs,
            "by_status": dict(status_counts),
            "usage": dict(usage_totals),
        },
        "outputs": {key: str(value) for key, value in paths.items() if key.endswith("jsonl")},
    }
    write_json(paths["parse_report_json"], report)
    return report


def add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--batch-id", default="batch_001")
    parser.add_argument("--env-file", default=str(DEFAULT_ENV))
    parser.add_argument("--model", default=DEFAULT_GEMINI_MODEL)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare")
    add_common_args(prepare)
    prepare.add_argument("--tasks-jsonl", type=Path, default=DEFAULT_TASKS)
    prepare.add_argument("--batch-size", type=int, default=250)
    prepare.add_argument("--shuffle", action="store_true")
    prepare.add_argument("--seed", type=int, default=1)
    prepare.add_argument("--exclude-output-jsonl", type=Path, action="append", default=[])
    prepare.add_argument(
        "--retry-attempted",
        action="store_true",
        help="Allow previously attempted papers back into selection while still excluding successful papers.",
    )
    prepare.add_argument("--full-text-prompt", type=Path, default=FULL_TEXT_PROMPT)
    prepare.add_argument("--abstract-prompt", type=Path, default=ABSTRACT_PROMPT)
    prepare.add_argument("--bundle-schema", type=Path, default=BUNDLE_SCHEMA)
    prepare.add_argument("--max-output-tokens", type=int, default=16384)
    prepare.add_argument("--thinking-budget", type=int, default=0)
    prepare.add_argument("--overwrite", action="store_true")

    submit = subparsers.add_parser("submit")
    add_common_args(submit)
    submit.add_argument("--display-name", default="")

    status = subparsers.add_parser("status")
    add_common_args(status)
    status.add_argument("--job-name", default="")

    download = subparsers.add_parser("download")
    add_common_args(download)
    download.add_argument("--job-name", default="")

    parse = subparsers.add_parser("parse")
    add_common_args(parse)

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.command == "prepare":
        result = prepare_batch(args)
        print(json.dumps({"status": result["status"], "summary": result["summary"], "outputs": result["outputs"]}, indent=2))
    elif args.command == "submit":
        result = submit_batch(args)
        print(json.dumps({"status": result["status"], "job_name": result["job_name"], "model": result["model"]}, indent=2))
    elif args.command == "status":
        result = check_status(args)
        print(json.dumps({"status": result["status"], "job_name": result["job_name"], "state": result["state"]}, indent=2))
    elif args.command == "download":
        result = download_results(args)
        print(json.dumps(result, indent=2))
    else:
        result = parse_results(args)
        print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
