#!/usr/bin/env python3
"""Prepare, submit, monitor, download, and parse Gemini meta-analysis v2 batches."""

from __future__ import annotations

import argparse
from collections import Counter
import copy
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import random
import re
import shutil
import sys
import unicodedata

from jsonschema import Draft7Validator

try:
    from google import genai
    from google.genai import models as genai_models
    from google.genai import types
except ModuleNotFoundError as err:  # pragma: no cover - environment guard
    raise SystemExit("google-genai is required for Gemini batch extraction") from err

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.extract.io_utils import normalize, read_jsonl, text_parts_from_packet, write_json
from pipeline.extract.route_extraction_profiles import schema_for_native
from pipeline.extract.run_route_extraction import (
    DEFAULT_ENV,
    DEFAULT_GEMINI_MODEL,
    build_generation_config,
    parse_json_response,
    safe_run_id,
)


DEFAULT_TASKS = (
    ROOT
    / "data"
    / "processed"
    / "extraction"
    / "meta_analysis_v2_tasks"
    / "meta_analysis_v2_tasks.jsonl"
)
DEFAULT_RUN_ROOT = ROOT / "data" / "processed" / "extraction" / "meta_analysis_v2_runs"
FULL_TEXT_PROMPT = ROOT / "docs" / "extraction_profiles" / "meta_analysis_v2" / "full_text_extraction.md"
ABSTRACT_PROMPT = ROOT / "docs" / "extraction_profiles" / "meta_analysis_v2" / "abstract_extraction.md"
OUTPUT_SCHEMA = ROOT / "schema" / "meta_analysis_evidence_v2.schema.json"
REPORT_SCHEMA_VERSION = "meta_analysis_v2_batch_api_report_v1"
RECORD_SCHEMA_VERSION = "meta_analysis_evidence_v2"


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


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_schema(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


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
        "parsed_jsonl": batch_dir / f"{batch_id}_extractions.jsonl",
        "raw_jsonl": batch_dir / f"{batch_id}_raw.jsonl",
        "parse_report_json": batch_dir / f"{batch_id}_parse_report.json",
        "run_extractions_jsonl": run_dir(args) / "meta_analysis_extractions.jsonl",
        "run_model_log_jsonl": run_dir(args) / "model_call_log.jsonl",
    }


def successful_dois(path: Path) -> set[str]:
    return {
        normalize(row.get("study_doi", "")).lower()
        for row in read_jsonl(path)
        if normalize(row.get("status", "")) == "ok"
    }


def previously_attempted_dois(args: argparse.Namespace) -> set[str]:
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
    excluded = successful_dois(batch_paths(args)["run_extractions_jsonl"])
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
    rng = random.Random(args.seed)
    if args.full_text_count >= 0:
        if args.full_text_count > args.batch_size:
            raise SystemExit("--full-text-count cannot exceed --batch-size")
        abstract_count = args.batch_size - args.full_text_count
        full_text = [item for item in candidates if normalize(item[1].get("text_depth", "")) == "article_text"]
        abstracts = [item for item in candidates if normalize(item[1].get("text_depth", "")) == "abstract_only"]
        if args.shuffle:
            rng.shuffle(full_text)
            rng.shuffle(abstracts)
        if len(full_text) < args.full_text_count or len(abstracts) < abstract_count:
            raise SystemExit(
                "Not enough tasks for the requested depth mix: "
                f"requested {args.full_text_count} article_text and {abstract_count} abstract_only; "
                f"available {len(full_text)} and {len(abstracts)}"
            )
        selected = full_text[: args.full_text_count] + abstracts[:abstract_count]
        if args.shuffle:
            rng.shuffle(selected)
        return selected
    if args.shuffle:
        rng.shuffle(candidates)
    return candidates[: max(0, args.batch_size)]


def archive_run_inputs(owner: Path, tasks_path: Path, args: argparse.Namespace) -> dict:
    snapshot_dir = owner / "input_snapshot"
    artifact_groups = {
        "prompts": [Path(args.full_text_prompt), Path(args.abstract_prompt)],
        "schemas": [Path(args.output_schema)],
        "tasks": [tasks_path],
    }
    artifacts: list[dict] = []
    for group, sources in artifact_groups.items():
        for source in sources:
            source = source.resolve()
            destination = snapshot_dir / group / source.name
            source_hash = file_sha256(source)
            if destination.exists() and file_sha256(destination) != source_hash and not args.overwrite:
                raise SystemExit(
                    f"Run input changed since this batch was prepared: {source}. "
                    "Use another batch ID or --overwrite."
                )
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            artifacts.append(
                {
                    "group": group,
                    "source_path": str(source),
                    "archived_path": str(destination),
                    "sha256": source_hash,
                }
            )
    manifest = {
        "schema_version": "meta_analysis_v2_input_snapshot_v1",
        "created_at_utc": now_utc(),
        "run_id": safe_run_id(args.run_id),
        "batch_id": normalize(args.batch_id),
        "model": args.model,
        "thinking_budget": args.thinking_budget,
        "max_output_tokens": args.max_output_tokens,
        "artifacts": artifacts,
    }
    write_json(snapshot_dir / "manifest.json", manifest)
    return manifest


def archived_artifacts(snapshot: dict) -> dict[str, Path]:
    return {
        str(Path(item["source_path"]).resolve()): Path(item["archived_path"])
        for item in snapshot["artifacts"]
    }


def packet_lookup(tasks: list[dict]) -> dict[str, dict]:
    paths = {
        normalize(task.get("source", {}).get("packet_path", ""))
        for task in tasks
        if isinstance(task.get("source"), dict) and normalize(task["source"].get("packet_path", ""))
    }
    out: dict[str, dict] = {}
    for path_text in paths:
        for packet in read_jsonl(Path(path_text)):
            packet_id = normalize(packet.get("packet_id", ""))
            doi = normalize(packet.get("study_doi", "")).lower()
            if packet_id:
                out[packet_id] = packet
            if doi:
                out.setdefault(doi, packet)
    return out


def packet_for_task(task: dict, packets: dict[str, dict]) -> dict | None:
    source = task.get("source", {}) if isinstance(task.get("source"), dict) else {}
    packet_id = normalize(source.get("packet_id", ""))
    if packet_id and packet_id in packets:
        return packets[packet_id]
    return packets.get(normalize(task.get("study_doi", "")).lower())


def model_contents(task: dict, packet: dict | None) -> str:
    metadata = task.get("paper_metadata", {}) if isinstance(task.get("paper_metadata"), dict) else {}
    metadata_text = json.dumps(metadata, ensure_ascii=False, indent=2)
    text_depth = normalize(task.get("text_depth", ""))
    if text_depth == "article_text":
        if packet is None:
            raise ValueError(f"Missing article packet for {task.get('study_doi')}")
        source_text = "\n\n".join(text_parts_from_packet(packet)).strip()
        source_label = "ARTICLE_TEXT"
    elif text_depth == "abstract_only":
        title = normalize(metadata.get("study_title", ""))
        abstract = normalize(metadata.get("abstract", ""))
        source_text = f"Title: {title}\n\nAbstract: {abstract}".strip()
        source_label = "ABSTRACT_TEXT"
    else:
        raise ValueError(f"Unsupported text depth `{text_depth}`")
    return f"PAPER_METADATA_JSON:\n{metadata_text}\n\n{source_label}:\n{source_text}"


def source_text_for_task(task: dict, packet: dict | None) -> str:
    metadata = task.get("paper_metadata", {}) if isinstance(task.get("paper_metadata"), dict) else {}
    text_depth = normalize(task.get("text_depth", ""))
    if text_depth == "article_text":
        if packet is None:
            raise ValueError(f"Missing article packet for {task.get('study_doi')}")
        return "\n\n".join(text_parts_from_packet(packet)).strip()
    return f"Title: {normalize(metadata.get('study_title', ''))}\n\nAbstract: {normalize(metadata.get('abstract', ''))}".strip()


def request_for_task(
    *,
    api_client: object,
    task: dict,
    packet: dict | None,
    prompt_path: Path,
    schema_path: Path,
    args: argparse.Namespace,
) -> tuple[dict, dict]:
    source_text = source_text_for_task(task, packet)
    contents = model_contents(task, packet)
    schema = load_schema(schema_path)
    if normalize(task.get("text_depth", "")) == "abstract_only":
        schema["definitions"]["evidence_locator"]["properties"]["location"]["enum"] = ["title", "abstract"]
    else:
        schema["definitions"]["evidence_locator"]["properties"]["location"].pop("enum", None)
    model_schema = schema_for_native(schema)

    def strip_schema_descriptions(value: object, *, property_map: bool = False) -> None:
        if isinstance(value, list):
            for item in value:
                strip_schema_descriptions(item)
            return
        if not isinstance(value, dict):
            return
        if not property_map:
            value.pop("description", None)
        for key, item in value.items():
            strip_schema_descriptions(item, property_map=key == "properties")

    strip_schema_descriptions(model_schema)
    config = build_generation_config(
        system_instruction=prompt_path.read_text(encoding="utf-8").strip(),
        schema=model_schema,
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
        "content_chars": len(source_text),
        "approx_input_tokens_char4": max(1, len(source_text) // 4),
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
    output_schema = archived[str(Path(args.output_schema).resolve())]
    packets = packet_lookup(selected_rows)
    client = genai.Client(api_key=api_key_from_env(args, required=False))

    records: list[dict] = []
    with paths["requests_jsonl"].open("w", encoding="utf-8") as handle:
        for position, (input_row_index, task) in enumerate(selected, start=1):
            text_depth = normalize(task.get("text_depth", ""))
            prompt_path = full_text_prompt if text_depth == "article_text" else abstract_prompt
            request, request_metadata = request_for_task(
                api_client=client._api_client,  # noqa: SLF001
                task=task,
                packet=packet_for_task(task, packets),
                prompt_path=prompt_path,
                schema_path=output_schema,
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
                    "text_depth": text_depth,
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
            "full_text_count": args.full_text_count,
            "shuffle": args.shuffle,
            "seed": args.seed,
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
    display_name = normalize(args.display_name) or (
        f"psychedelics-kg-meta-v2-{safe_run_id(args.run_id)}-{normalize(args.batch_id)}"
    )
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


def schema_errors(schema: dict, result: dict) -> list[str]:
    validator = Draft7Validator(schema)
    return [
        error.message
        for error in sorted(validator.iter_errors(result), key=lambda error: list(error.path))
    ]


def semantic_qa_flags(result: dict, text_depth: str) -> list[str]:
    flags: list[str] = []
    questions = [item for item in result.get("main_questions", []) if isinstance(item, dict)]
    results = [item for item in result.get("synthesis_results", []) if isinstance(item, dict)]
    question_ids = [normalize(item.get("question_id", "")) for item in questions]
    result_ids = [normalize(item.get("result_id", "")) for item in results]
    if len(question_ids) != len(set(question_ids)):
        flags.append("duplicate_question_ids")
    if len(result_ids) != len(set(result_ids)):
        flags.append("duplicate_result_ids")
    known_questions = set(question_ids)
    known_results = set(result_ids)
    for item in results:
        result_id = normalize(item.get("result_id", ""))
        unknown = sorted(set(item.get("addresses_question_ids", [])) - known_questions)
        if unknown:
            flags.append(f"result_links_unknown_questions:{result_id}:{'|'.join(unknown)}")
        for field in ("effect_estimate", "evidence_size", "heterogeneity", "analysis_context", "network_meta_analysis"):
            if field in item and item[field] == {}:
                flags.append(f"empty_optional_object:{result_id}:{field}")
        if text_depth == "abstract_only":
            for locator in item.get("evidence_locators", []):
                if isinstance(locator, dict) and normalize(locator.get("location", "")) not in {"title", "abstract"}:
                    flags.append(f"abstract_result_has_nonabstract_locator:{result_id}")
    for array_name in (
        "risk_of_bias_assessments",
        "certainty_assessments",
        "publication_bias_assessments",
        "paper_conclusions",
    ):
        identifiers: list[str] = []
        for item in result.get(array_name, []):
            if not isinstance(item, dict):
                continue
            identifier = normalize(
                item.get("assessment_id", "") or item.get("conclusion_id", "")
            )
            identifiers.append(identifier)
            unknown = sorted(set(item.get("applies_to_result_ids", [])) - known_results)
            if unknown:
                flags.append(f"{array_name}_links_unknown_results:{identifier}:{'|'.join(unknown)}")
        if len(identifiers) != len(set(identifiers)):
            flags.append(f"duplicate_ids:{array_name}")
    status = normalize(result.get("extraction_status", ""))
    if status == "extracted" and not results:
        flags.append("extracted_without_synthesis_results")
    if status != "extracted" and results:
        flags.append("nonextracted_status_with_synthesis_results")
    return flags


def source_comparison_text(value: object) -> str:
    text = unicodedata.normalize("NFKC", normalize(value)).casefold()
    text = text.replace("−", "-").replace("–", "-").replace("—", "-")
    text = text.replace("“", '"').replace("”", '"').replace("’", "'")
    return re.sub(r"\s+", " ", text).strip()


def source_number_text(value: object) -> str:
    text = unicodedata.normalize("NFKC", normalize(value)).casefold()
    text = text.replace("−", "-").replace("–", "-").replace("—", "-")
    # Several journal XML/PDF renderers use a middle dot as the decimal mark
    # (for example, 0·49). Treat it like comma/period only when it occurs
    # between digits, so source tracing does not reject a faithfully copied
    # estimate merely because the model returned the standard decimal form.
    text = re.sub(r"(?<=\d)\s*[,·•∙⋅]\s*(?=\d)", ".", text)
    return re.sub(r"\s+", "", text)


def numeric_tokens(value: object) -> list[str]:
    return re.findall(r"(?<![A-Za-z0-9])[-+]?\d+(?:[.,]\d+)?", normalize(value))


def source_contains_number(source_text: str, token: str) -> bool:
    source = source_number_text(source_text)
    token_text = source_number_text(token)
    variants = {token_text}
    variants.add(re.sub(r"^([+-]?)0\.", r"\1.", token_text))
    return any(variant and variant in source for variant in variants)


def result_bundles_multiple_estimates(item: dict) -> bool:
    statement = normalize(item.get("relationship_statement", ""))
    ci_count = len(re.findall(r"95\s*%?\s*(?:ci|credible interval)", statement, flags=re.IGNORECASE))
    assignment_count = len(
        re.findall(
            r"\b(?:hedges'?\s*g|g|smd|md|rr|or|hr|risk ratio|odds ratio|hazard ratio)\s*[=:]\s*[-+]?\d",
            statement,
            flags=re.IGNORECASE,
        )
    )
    percentages = [
        value
        for value in re.findall(r"(?<!\d)(\d+(?:\.\d+)?)\s*%", statement)
        if value not in {"95", "90", "99"}
    ]
    estimate = item.get("effect_estimate", {}) if isinstance(item.get("effect_estimate"), dict) else {}
    return ci_count > 1 or assignment_count > 1 or (bool(estimate.get("estimate")) and len(percentages) > 1)


def effect_estimate_is_range(item: dict) -> bool:
    estimate = item.get("effect_estimate", {}) if isinstance(item.get("effect_estimate"), dict) else {}
    value = normalize(estimate.get("estimate", ""))
    return bool(re.search(r"[-+]?\d+(?:\.\d+)?\s+(?:to|through)\s+[-+]?\d+(?:\.\d+)?", value, re.IGNORECASE))


def result_quality_flags(result: dict, source_text: str) -> list[str]:
    flags: list[str] = []
    normalized_source = source_comparison_text(source_text)

    def visit_locators(value: object, owner: str = "paper") -> None:
        if isinstance(value, list):
            for item in value:
                visit_locators(item, owner)
            return
        if not isinstance(value, dict):
            return
        current_owner = normalize(
            value.get("result_id", "")
            or value.get("assessment_id", "")
            or value.get("conclusion_id", "")
        ) or owner
        locators = value.get("evidence_locators")
        if isinstance(locators, list):
            for index, locator in enumerate(locators, start=1):
                if not isinstance(locator, dict):
                    continue
                supporting_text = source_comparison_text(locator.get("supporting_text", ""))
                if supporting_text and supporting_text not in normalized_source:
                    flags.append(f"nonverbatim_supporting_text:{current_owner}:{index}")
        for key, item in value.items():
            if key != "evidence_locators":
                visit_locators(item, current_owner)

    visit_locators(result)

    for item in result.get("synthesis_results", []):
        if not isinstance(item, dict):
            continue
        result_id = normalize(item.get("result_id", "")) or "unknown"
        subject_areas = {normalize(value) for value in item.get("subject_areas", []) if normalize(value)}
        primary_area = normalize(item.get("primary_subject_area", ""))
        if not primary_area:
            flags.append(f"missing_primary_subject_area:{result_id}")
        elif primary_area not in subject_areas:
            flags.append(f"primary_subject_area_not_in_subject_areas:{result_id}")
        if not normalize(item.get("intervention_or_exposure", "")):
            flags.append(f"missing_intervention_or_exposure:{result_id}")
        if not normalize(item.get("outcome_or_entity", "")):
            flags.append(f"missing_outcome_or_entity:{result_id}")
        role = normalize(item.get("result_role", ""))
        if role in {"network_comparison", "network_ranking"} and not item.get("network_meta_analysis"):
            flags.append(f"network_result_without_network_details:{result_id}")
        statement = normalize(item.get("relationship_statement", ""))
        if result_bundles_multiple_estimates(item):
            flags.append(f"multiple_estimates_in_one_result:{result_id}")
        if effect_estimate_is_range(item):
            flags.append(f"effect_estimate_is_range:{result_id}")

        interpretation = item.get("interpretation", {}) if isinstance(item.get("interpretation"), dict) else {}
        direction = normalize(interpretation.get("finding_direction", ""))
        estimate = item.get("effect_estimate", {}) if isinstance(item.get("effect_estimate"), dict) else {}
        for field in ("estimate", "interval_lower", "interval_upper", "standard_error", "p_value"):
            value = estimate.get(field)
            tokens = numeric_tokens(value) if value not in (None, "") else []
            if tokens and any(not source_contains_number(source_text, token) for token in tokens):
                flags.append(f"numeric_value_not_in_source:{result_id}:{field}")
        p_text = normalize(estimate.get("p_value", ""))
        p_match = re.search(
            r"^(?:p\s*=\s*)?(0?\.\d+|1(?:\.0+)?)$",
            p_text,
            flags=re.IGNORECASE,
        )
        if direction == "supports" and p_match:
            if float(p_match.group(1)) > 0.05:
                flags.append(f"supports_with_p_above_0_05:{result_id}")
        try:
            lower = float(normalize(estimate.get("interval_lower", "")).replace(",", ".").replace("%", ""))
            upper = float(normalize(estimate.get("interval_upper", "")).replace(",", ".").replace("%", ""))
        except ValueError:
            lower = upper = None
        if direction == "supports" and lower is not None and upper is not None:
            metric = normalize(estimate.get("metric", "")).casefold()
            null_value = 1.0 if re.search(r"\b(rr|or|hr|risk ratio|odds ratio|hazard ratio|rate ratio)\b", metric) else 0.0
            if min(lower, upper) <= null_value <= max(lower, upper):
                flags.append(f"supports_with_interval_including_null:{result_id}")
        negated_significance = re.search(
            r"\b(fail(?:ed|ing)? to reach(?: statistical)? significance|not statistically significant|non.?significant)\b",
            statement,
            flags=re.IGNORECASE,
        )
        remaining_statement = re.sub(
            r"\b(fail(?:ed|ing)? to reach(?: statistical)? significance|not statistically significant|non.?significant)\b",
            "",
            statement,
            flags=re.IGNORECASE,
        )
        if negated_significance and re.search(
            r"\b(?:statistically )?significant(?:ly)?\b", remaining_statement, flags=re.IGNORECASE
        ):
            flags.append(f"contradictory_significance_wording:{result_id}")
    return flags


def normalize_model_result(result: dict, text_depth: str) -> tuple[dict, dict[str, int]]:
    """Apply only transformations determined by the supplied source type."""
    normalized = copy.deepcopy(result)
    counts: Counter = Counter()
    missing_markers = {
        "not reported",
        "not_reported",
        "not applicable",
        "not_applicable",
        "n/a",
        "null",
        "none",
    }
    required_string_fields = {
        "question_id",
        "description",
        "result_id",
        "relationship_statement",
        "assessment_id",
        "conclusion_id",
        "statement",
        "finding_direction",
        "importance_in_paper",
        "evidence_source",
        "scope",
        "overall_judgment",
        "rating",
        "result",
        "location",
        "locator",
        "supporting_text",
    }
    nullable_result_fields = {
        "population_or_system",
        "intervention_or_exposure",
        "comparator",
        "outcome_or_entity",
        "timepoint_or_window",
    }

    def visit(value: object) -> None:
        if isinstance(value, list):
            for item in value:
                visit(item)
            return
        if not isinstance(value, dict):
            return
        for key in list(value):
            item = value[key]
            if (
                key in nullable_result_fields
                and isinstance(item, str)
                and item.strip().lower() in missing_markers
            ):
                value[key] = None
                counts["normalized_nullable_missing_marker"] += 1
            elif (
                key not in required_string_fields
                and isinstance(item, str)
                and item.strip().lower() in missing_markers
            ):
                del value[key]
                counts["omitted_missing_marker"] += 1
        estimate = value.get("effect_estimate")
        if isinstance(estimate, dict):
            metric = normalize(estimate.get("metric", ""))
            if re.search(r"\b(implied|inferred|assumed|presumed)\b", metric, flags=re.IGNORECASE):
                estimate.pop("metric", None)
                counts["omitted_inferred_effect_metric"] += 1
        if text_depth == "abstract_only":
            locators = value.get("evidence_locators")
            if isinstance(locators, list):
                for locator in locators:
                    if not isinstance(locator, dict):
                        continue
                    location = normalize(locator.get("location", ""))
                    if location and location != "title" and location != "abstract":
                        locator["location"] = "abstract"
                        counts["abstract_evidence_location"] += 1
        else:
            locators = value.get("evidence_locators")
            if isinstance(locators, list):
                allowed = {
                    "title",
                    "abstract",
                    "objective",
                    "methods",
                    "results",
                    "table",
                    "figure",
                    "supplement",
                    "discussion",
                    "conclusion",
                }
                location_rules = (
                    ("title", "title"),
                    ("abstract", "abstract"),
                    ("objective", "objective"),
                    ("method", "methods"),
                    ("table", "table"),
                    ("figure", "figure"),
                    ("supplement", "supplement"),
                    ("discussion", "discussion"),
                    ("conclusion", "conclusion"),
                    ("result", "results"),
                    ("effect", "results"),
                    ("analysis", "results"),
                    ("assessment", "results"),
                )
                for locator in locators:
                    if not isinstance(locator, dict):
                        continue
                    location = normalize(locator.get("location", ""))
                    location_key = location.casefold()
                    if location_key in allowed:
                        normalized_location = location_key
                    else:
                        normalized_location = next(
                            (target for marker, target in location_rules if marker in location_key),
                            "results",
                        )
                    if location and normalized_location != location:
                        locator["location"] = normalized_location
                        counts["full_text_evidence_location"] += 1
        for item in value.values():
            visit(item)

    visit(normalized)
    return normalized, dict(counts)


def upsert_rows(path: Path, rows: list[dict]) -> int:
    existing_rows = read_jsonl(path) if path.exists() else []
    incoming = {
        normalize(row.get("task_id", "")): row
        for row in rows
        if normalize(row.get("task_id", ""))
    }
    merged: list[dict] = []
    used: set[str] = set()
    for row in existing_rows:
        key = normalize(row.get("task_id", ""))
        if key in incoming:
            merged.append(incoming[key])
            used.add(key)
        elif key:
            merged.append(row)
    merged.extend(row for key, row in incoming.items() if key not in used)
    write_jsonl(path, merged)
    return len(incoming)


def parse_results(args: argparse.Namespace) -> dict:
    paths = batch_paths(args)
    manifest = json.loads(paths["manifest_json"].read_text(encoding="utf-8"))
    records = {normalize(row.get("key", "")): row for row in manifest.get("records", [])}
    tasks = {normalize(row.get("task_id", "")): row for row in read_jsonl(paths["selected_tasks_jsonl"])}
    packets = packet_lookup(list(tasks.values()))
    snapshot_manifest = json.loads(
        (paths["snapshot_owner"] / "input_snapshot" / "manifest.json").read_text(encoding="utf-8")
    )
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
            "source_depth": normalize(record.get("text_depth", "")),
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
            parsed, normalizations = normalize_model_result(parsed, raw["source_depth"])
            validation_errors = schema_errors(schema, parsed)
            qa_flags = semantic_qa_flags(parsed, raw["source_depth"]) if not validation_errors else []
            if not validation_errors:
                qa_flags.extend(
                    result_quality_flags(
                        parsed,
                        source_text_for_task(task, packet_for_task(task, packets)),
                    )
                )
            status = "schema_error" if validation_errors else "ok"
            raw.update(
                {
                    "status": status,
                    "parse_method": parse_method,
                    "schema_errors": validation_errors,
                    "normalizations": normalizations,
                }
            )
            outputs.append(
                {
                    "schema_version": RECORD_SCHEMA_VERSION,
                    "task_id": raw["task_id"],
                    "study_doi": raw["study_doi"],
                    "study_title": normalize(record.get("study_title", "")),
                    "source_depth": raw["source_depth"],
                    "source_fingerprint": normalize(record.get("source_fingerprint", "")),
                    "model": normalize(record.get("model", "")),
                    "status": status,
                    "result": parsed,
                    "schema_errors": validation_errors,
                    "qa_flags": qa_flags,
                    "normalizations": normalizations,
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
    written_outputs = upsert_rows(paths["run_extractions_jsonl"], outputs)
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
    prepare.add_argument("--batch-size", type=int, default=100)
    prepare.add_argument(
        "--full-text-count",
        type=int,
        default=-1,
        help="Exact number of article-text tasks; the remainder use abstracts. Omit for unstratified selection.",
    )
    prepare.add_argument("--shuffle", action="store_true")
    prepare.add_argument("--seed", type=int, default=1)
    prepare.add_argument("--exclude-output-jsonl", type=Path, action="append", default=[])
    prepare.add_argument("--retry-attempted", action="store_true")
    prepare.add_argument("--full-text-prompt", type=Path, default=FULL_TEXT_PROMPT)
    prepare.add_argument("--abstract-prompt", type=Path, default=ABSTRACT_PROMPT)
    prepare.add_argument("--output-schema", type=Path, default=OUTPUT_SCHEMA)
    prepare.add_argument("--max-output-tokens", type=int, default=32768)
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
