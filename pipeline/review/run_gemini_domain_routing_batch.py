#!/usr/bin/env python3
"""Prepare, submit, and parse Gemini Batch API domain-routing jobs."""

from __future__ import annotations

import argparse
from collections import Counter
import datetime as dt
import json
import os
from pathlib import Path
import sys
import time

try:
    from google import genai
    from google.genai import models as genai_models
    from google.genai import types
except ModuleNotFoundError as err:  # pragma: no cover - environment guard
    raise SystemExit("google-genai is required for Gemini batch domain routing") from err

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from pipeline.review.run_gemini_domain_routing import (
        DEFAULT_COUNTS_CSV,
        DEFAULT_ENV,
        DEFAULT_METADATA_TABLE,
        DEFAULT_OUTPUT_TABLE,
        DEFAULT_PRESCREEN_TABLE,
        DEFAULT_RAW_JSONL,
        DEFAULT_SUMMARY_JSON,
        build_summary,
        clean,
        completed_dois,
        generation_config,
        load_dotenv,
        normalize_payload,
        parse_response_text,
        parsed_rows_from_raw,
        prompt_for_record,
        prescreen_row_is_extraction_candidate,
        read_doi_file,
        read_table,
        route_rows_from_parsed,
        selected_records,
        split_values,
        write_counts_csv,
        write_json,
        write_table,
    )
    from pipeline.fulltext.convert_pdfs import normalize_doi
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    sys.path.insert(0, str(ROOT))
    from pipeline.review.run_gemini_domain_routing import (
        DEFAULT_COUNTS_CSV,
        DEFAULT_ENV,
        DEFAULT_METADATA_TABLE,
        DEFAULT_OUTPUT_TABLE,
        DEFAULT_PRESCREEN_TABLE,
        DEFAULT_RAW_JSONL,
        DEFAULT_SUMMARY_JSON,
        build_summary,
        clean,
        completed_dois,
        generation_config,
        load_dotenv,
        normalize_payload,
        parse_response_text,
        parsed_rows_from_raw,
        prompt_for_record,
        prescreen_row_is_extraction_candidate,
        read_doi_file,
        read_table,
        route_rows_from_parsed,
        selected_records,
        split_values,
        write_counts_csv,
        write_json,
        write_table,
    )
    from pipeline.fulltext.convert_pdfs import normalize_doi


DEFAULT_MODEL = "gemini-3-flash-preview"
TERMINAL_STATES = {"JOB_STATE_SUCCEEDED", "JOB_STATE_FAILED", "JOB_STATE_CANCELLED", "JOB_STATE_EXPIRED"}


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def default_batch_input_jsonl() -> Path:
    return DEFAULT_METADATA_TABLE.parent / "paper_domain_routing_gemini_batch_requests.jsonl"


def default_batch_manifest_json() -> Path:
    return DEFAULT_METADATA_TABLE.parent / "paper_domain_routing_gemini_batch_manifest.json"


def default_batch_job_json() -> Path:
    return DEFAULT_METADATA_TABLE.parent / "paper_domain_routing_gemini_batch_job.json"


def default_batch_output_jsonl() -> Path:
    return DEFAULT_METADATA_TABLE.parent / "paper_domain_routing_gemini_batch_results.jsonl"


def default_batch_parse_report_json() -> Path:
    return DEFAULT_METADATA_TABLE.parent / "paper_domain_routing_gemini_batch_parse_report.json"


def read_jsonl(path: Path) -> list[dict]:
    rows = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            rows.append(json.loads(line))
    return rows


def api_key_from_env(args: argparse.Namespace, *, required: bool) -> str:
    env_values = load_dotenv(Path(args.env_file).resolve())
    api_key = env_values.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY", "")
    if required and not api_key:
        raise SystemExit("GEMINI_API_KEY is missing. Add it to project .env or the environment.")
    return api_key or "DUMMY"


def model_from_env(args: argparse.Namespace) -> str:
    env_values = load_dotenv(Path(args.env_file).resolve())
    return (
        clean(getattr(args, "model", ""))
        or env_values.get("GEMINI_DOMAIN_ROUTING_MODEL")
        or os.environ.get("GEMINI_DOMAIN_ROUTING_MODEL", "")
        or DEFAULT_MODEL
    )


def selected_routing_records(args: argparse.Namespace) -> list[dict]:
    scoped_dois = read_doi_file(Path(args.doi_file).resolve()) if clean(args.doi_file) else set()
    completed = completed_dois(Path(args.raw_jsonl).resolve()) if getattr(args, "resume", False) else set()
    records = selected_records(
        read_table(Path(args.metadata_table).resolve()),
        read_table(Path(args.prescreen_decisions_table).resolve()),
        scoped_dois=scoped_dois,
        limit=0,
        completed=completed,
    )
    start_index = max(1, int(args.start_index))
    selected = records[start_index - 1 :]
    if args.limit > 0:
        selected = selected[: args.limit]
    return selected


def batch_request_for_record(*, api_client: object, record: dict, args: argparse.Namespace) -> dict:
    request = genai_models._GenerateContentParameters_to_mldev(  # noqa: SLF001 - SDK has no public file-request serializer.
        api_client,
        {
            "contents": prompt_for_record(record),
            "config": generation_config(args),
        },
    )
    request.pop("_url", None)
    return jsonable(request)


def jsonable(value: object) -> object:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", exclude_none=True, by_alias=True)
    if isinstance(value, dict):
        return {key: jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [jsonable(item) for item in value]
    return value


def write_batch_requests(args: argparse.Namespace) -> dict:
    batch_input_jsonl = Path(args.batch_input_jsonl).resolve()
    manifest_json = Path(args.manifest_json).resolve()
    client = genai.Client(api_key=api_key_from_env(args, required=False))
    model = model_from_env(args)
    records = selected_routing_records(args)

    manifest_records = []
    batch_input_jsonl.parent.mkdir(parents=True, exist_ok=True)
    with batch_input_jsonl.open("w", encoding="utf-8") as handle:
        for input_row_index, record in enumerate(records, start=max(1, int(args.start_index))):
            key = f"domain-routing-{input_row_index:06d}"
            request = batch_request_for_record(api_client=client._api_client, record=record, args=args)  # noqa: SLF001
            handle.write(json.dumps({"key": key, "request": request}, ensure_ascii=False) + "\n")
            manifest_records.append(
                {
                    "key": key,
                    "input_row_index": input_row_index,
                    "doi": normalize_doi(record.get("doi", "")),
                    "datasets": clean(record.get("datasets", "")),
                    "study_title": clean(record.get("study_title", "")),
                    "prompt_chars": len(prompt_for_record(record)),
                }
            )

    manifest = {
        "generated_at_utc": now_utc(),
        "schema_version": "domain_routing_gemini_batch_manifest",
        "status": "prepared",
        "inputs": {
            "metadata_table": str(Path(args.metadata_table).resolve()),
            "prescreen_decisions_table": str(Path(args.prescreen_decisions_table).resolve()),
            "doi_file": str(Path(args.doi_file).resolve()) if clean(args.doi_file) else "",
            "raw_jsonl": str(Path(args.raw_jsonl).resolve()),
            "model": model,
            "start_index": max(1, int(args.start_index)),
            "limit": int(args.limit),
            "temperature": float(args.temperature),
            "max_output_tokens": int(args.max_output_tokens),
            "thinking_budget": args.thinking_budget,
            "resume": bool(getattr(args, "resume", False)),
        },
        "outputs": {
            "batch_input_jsonl": str(batch_input_jsonl),
            "manifest_json": str(manifest_json),
        },
        "summary": {
            "prepared_requests": len(manifest_records),
            "by_dataset": dict(Counter(tag for record in manifest_records for tag in split_values(record["datasets"]))),
        },
        "records": manifest_records,
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
    display_name = clean(args.display_name) or f"psychedelics-kg-domain-routing-{dt.datetime.now().strftime('%Y%m%d-%H%M%S')}"
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
        "schema_version": "domain_routing_gemini_batch_job",
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
    if clean(args.job_name):
        return clean(args.job_name)
    job_json = Path(args.job_json).resolve()
    if not job_json.exists():
        raise SystemExit(f"Job JSON does not exist and --job-name was not supplied: {job_json}")
    with job_json.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    job_name = clean(payload.get("job_name", ""))
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


def batch_line_key(row: dict, fallback_index: int) -> str:
    for path in (("key",), ("metadata", "key"), ("response", "metadata", "key")):
        value: object = row
        for key in path:
            value = value.get(key, "") if isinstance(value, dict) else ""
        text = clean(value)
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
            return json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else clean(value)
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
        clean(record.get("key", "")): record
        for record in manifest.get("records", [])
        if clean(record.get("key", ""))
    }


def retained_prescreen_dois(prescreen_df) -> set[str]:
    out: set[str] = set()
    if prescreen_df.empty or "doi" not in prescreen_df.columns:
        return out
    for row in prescreen_df.to_dict("records"):
        doi = normalize_doi(row.get("doi", ""))
        if doi and prescreen_row_is_extraction_candidate(row):
            out.add(doi)
    return out


def all_prescreen_dois(prescreen_df) -> set[str]:
    out: set[str] = set()
    if prescreen_df.empty or "doi" not in prescreen_df.columns:
        return out
    for row in prescreen_df.to_dict("records"):
        doi = normalize_doi(row.get("doi", ""))
        if doi:
            out.add(doi)
    return out


def parse_batch_results(args: argparse.Namespace) -> dict:
    batch_output_jsonl = Path(args.batch_output_jsonl).resolve()
    manifest_json = Path(args.manifest_json).resolve()
    raw_jsonl = Path(args.raw_jsonl).resolve()
    output_table = Path(args.output_table).resolve()
    summary_json = Path(args.summary_json).resolve()
    counts_csv = Path(args.counts_csv).resolve()
    report_json = Path(args.report_json).resolve()
    with manifest_json.open("r", encoding="utf-8") as handle:
        manifest = json.load(handle)
    manifest_by_key = records_by_key(manifest)
    model = clean(manifest.get("inputs", {}).get("model", "")) or model_from_env(args)
    metadata_table = Path(args.metadata_table).resolve()
    prescreen_table = Path(args.prescreen_decisions_table).resolve()
    metadata_df = read_table(metadata_table)
    prescreen_df = read_table(prescreen_table)
    retained_dois = retained_prescreen_dois(prescreen_df)
    prescreen_dois = all_prescreen_dois(prescreen_df)

    raw_rows = []
    status_counts: Counter = Counter()
    total_usage: Counter = Counter()
    for line_index, row in enumerate(read_jsonl(batch_output_jsonl), start=1):
        key = batch_line_key(row, line_index)
        manifest_record = manifest_by_key.get(key, {})
        doi = normalize_doi(manifest_record.get("doi", ""))
        response = batch_line_response(row)
        text = response_text(response)
        error = batch_line_error(row)
        raw_row = {
            "generated_at_utc": now_utc(),
            "doi": doi,
            "model": model,
            "status": "error",
            "response_text": text,
            "parsed": {},
            "usage": response.get("usageMetadata") or response.get("usage_metadata") or {},
            "batch_key": key,
            "batch_line_index": line_index,
            "batch_error": error,
            "error": "",
        }
        try:
            if error:
                raise RuntimeError(error)
            if not manifest_record:
                raise RuntimeError(f"No manifest record found for batch key `{key}`")
            if not doi:
                raise RuntimeError(f"No DOI found for batch key `{key}`")
            parsed = normalize_payload(parse_response_text(text))
            raw_row.update({"status": "ok", "parsed": parsed})
            for usage_key, value in raw_row["usage"].items():
                if isinstance(value, int):
                    total_usage[usage_key] += value
        except Exception as exc:
            status = "skipped_prescreen_excluded" if doi and doi in prescreen_dois and doi not in retained_dois else "error"
            raw_row.update({"status": status, "error_type": type(exc).__name__, "error": str(exc)})
        status_counts[raw_row["status"]] += 1
        raw_rows.append(raw_row)

    raw_jsonl.parent.mkdir(parents=True, exist_ok=True)
    raw_jsonl.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in raw_rows), encoding="utf-8")

    parsed_rows = parsed_rows_from_raw(raw_jsonl, metadata_df, prescreen_df)
    generated_at_utc = now_utc()
    route_rows = route_rows_from_parsed(parsed_rows, generated_at_utc)
    write_table(output_table, route_rows)
    summary, counts = build_summary(
        route_rows,
        inputs={
            "metadata_table": str(metadata_table),
            "prescreen_decisions_table": str(prescreen_table),
            "batch_output_jsonl": str(batch_output_jsonl),
            "manifest_json": str(manifest_json),
            "raw_jsonl": str(raw_jsonl),
            "model": model,
            "batch_parse": True,
        },
    )
    write_json(summary_json, summary)
    write_counts_csv(counts_csv, counts)
    report = {
        "generated_at_utc": now_utc(),
        "schema_version": "domain_routing_gemini_batch_parse_report",
        "status": "ok" if not status_counts.get("error") else "issues_found",
        "inputs": {
            "batch_output_jsonl": str(batch_output_jsonl),
            "manifest_json": str(manifest_json),
            "metadata_table": str(metadata_table),
            "prescreen_decisions_table": str(prescreen_table),
        },
        "outputs": {
            "raw_jsonl": str(raw_jsonl),
            "output_table": str(output_table),
            "summary_json": str(summary_json),
            "counts_csv": str(counts_csv),
            "report_json": str(report_json),
        },
        "summary": {
            "status_counts": dict(status_counts),
            "usage": dict(total_usage),
            "raw_outputs": len(raw_rows),
            "parsed_outputs": sum(1 for row in raw_rows if row.get("status") == "ok"),
            "route_rows": len(route_rows),
            "routed_dois": len({row["doi"] for row in route_rows}),
        },
    }
    write_json(report_json, report)
    return report


def add_common_generation_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--metadata-table", default=str(DEFAULT_METADATA_TABLE))
    parser.add_argument("--prescreen-decisions-table", default=str(DEFAULT_PRESCREEN_TABLE))
    parser.add_argument("--raw-jsonl", default=str(DEFAULT_RAW_JSONL))
    parser.add_argument("--doi-file", default="", help="Optional DOI list for a scoped routing batch.")
    parser.add_argument("--env-file", default=str(DEFAULT_ENV))
    parser.add_argument("--model", default="", help=f"Model override. Defaults to {DEFAULT_MODEL}.")
    parser.add_argument("--limit", type=int, default=0, help="Maximum records to prepare; 0 means all.")
    parser.add_argument("--start-index", type=int, default=1, help="1-based selected-record index to start from.")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--max-output-tokens", type=int, default=512)
    parser.add_argument("--thinking-budget", type=int, default=0)
    parser.add_argument("--resume", action="store_true", help="Skip DOIs already completed in --raw-jsonl.")


def add_parse_output_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--metadata-table", default=str(DEFAULT_METADATA_TABLE))
    parser.add_argument("--prescreen-decisions-table", default=str(DEFAULT_PRESCREEN_TABLE))
    parser.add_argument("--batch-output-jsonl", default=str(default_batch_output_jsonl()))
    parser.add_argument("--manifest-json", default=str(default_batch_manifest_json()))
    parser.add_argument("--raw-jsonl", default=str(DEFAULT_RAW_JSONL))
    parser.add_argument("--output-table", default=str(DEFAULT_OUTPUT_TABLE))
    parser.add_argument("--summary-json", default=str(DEFAULT_SUMMARY_JSON))
    parser.add_argument("--counts-csv", default=str(DEFAULT_COUNTS_CSV))
    parser.add_argument("--report-json", default=str(default_batch_parse_report_json()))
    parser.add_argument("--env-file", default=str(DEFAULT_ENV))
    parser.add_argument("--model", default="")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Gemini Batch API domain routing for the corpus.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare", help="Write Batch API request JSONL.")
    add_common_generation_args(prepare)
    prepare.add_argument("--batch-input-jsonl", default=str(default_batch_input_jsonl()))
    prepare.add_argument("--manifest-json", default=str(default_batch_manifest_json()))

    submit = subparsers.add_parser("submit", help="Upload prepared request JSONL and create a batch job.")
    submit.add_argument("--batch-input-jsonl", default=str(default_batch_input_jsonl()))
    submit.add_argument("--manifest-json", default=str(default_batch_manifest_json()))
    submit.add_argument("--job-json", default=str(default_batch_job_json()))
    submit.add_argument("--env-file", default=str(DEFAULT_ENV))
    submit.add_argument("--model", default="")
    submit.add_argument("--display-name", default="")

    status = subparsers.add_parser("status", help="Check batch job status.")
    status.add_argument("--job-json", default=str(default_batch_job_json()))
    status.add_argument("--job-name", default="")
    status.add_argument("--env-file", default=str(DEFAULT_ENV))

    wait = subparsers.add_parser("wait", help="Poll batch job until terminal state or timeout.")
    wait.add_argument("--job-json", default=str(default_batch_job_json()))
    wait.add_argument("--job-name", default="")
    wait.add_argument("--env-file", default=str(DEFAULT_ENV))
    wait.add_argument("--poll-interval-sec", type=float, default=60.0)
    wait.add_argument("--timeout-sec", type=float, default=0.0, help="0 means no timeout.")

    download = subparsers.add_parser("download", help="Download completed batch result JSONL.")
    download.add_argument("--job-json", default=str(default_batch_job_json()))
    download.add_argument("--job-name", default="")
    download.add_argument("--env-file", default=str(DEFAULT_ENV))
    download.add_argument("--batch-output-jsonl", default=str(default_batch_output_jsonl()))

    parse = subparsers.add_parser("parse", help="Parse batch result JSONL into domain-routing tables.")
    add_parse_output_args(parse)

    args = parser.parse_args()
    if args.command == "prepare":
        manifest = write_batch_requests(args)
        print(f"Prepared requests: {manifest['summary']['prepared_requests']:,}")
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
        print(f"Routed DOIs: {report['summary']['routed_dois']:,}")
        print(f"Domain routing table: {report['outputs']['output_table']}")
        print(f"Report: {report['outputs']['report_json']}")
        return 1 if report["status"] != "ok" else 0
    raise AssertionError(f"Unhandled command {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
