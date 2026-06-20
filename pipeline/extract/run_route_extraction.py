#!/usr/bin/env python3
"""Run route-aware extraction tasks through Gemini.

This runner reads `route_extraction_tasks.jsonl`, selects tasks with registered
route profiles, applies the matching prompt/schema, validates outputs, and
writes raw plus parsed JSONL audit files. Use `--dry-run` to inspect selection
without making API calls.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import time
from collections import Counter
from pathlib import Path

try:
    from jsonschema import Draft7Validator
except ModuleNotFoundError as err:  # pragma: no cover - environment guard
    raise SystemExit("jsonschema is required for route extraction validation") from err

try:
    from pipeline.extract.extraction_v1_utils import normalize, read_jsonl, text_parts_from_packet, write_json
    from pipeline.extract.extraction_profile_matrix import text_depth_from_access
    from pipeline.extract.route_extraction_profiles import (
        SCHEMA_MODES,
        RouteExtractionProfile,
        build_system_instruction,
        compact_schema,
        load_schema,
        profile_for_task,
        profile_key_for_task,
        schema_for_native,
        schema_for_assigned_domain,
        schema_in_native_config,
        supported_profile_keys,
        task_has_model_profile,
        task_has_registered_profile,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from pipeline.extract.extraction_v1_utils import normalize, read_jsonl, text_parts_from_packet, write_json
    from pipeline.extract.extraction_profile_matrix import text_depth_from_access
    from pipeline.extract.route_extraction_profiles import (
        SCHEMA_MODES,
        RouteExtractionProfile,
        build_system_instruction,
        compact_schema,
        load_schema,
        profile_for_task,
        profile_key_for_task,
        schema_for_native,
        schema_for_assigned_domain,
        schema_in_native_config,
        supported_profile_keys,
        task_has_model_profile,
        task_has_registered_profile,
    )


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = ROOT / "data" / "processed" / "extraction" / "route_extraction_tasks.jsonl"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "processed" / "extraction"
DEFAULT_ENV = ROOT / ".env"
PACKET_INDEX_CACHE: dict[str, dict[str, dict]] = {}


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def load_dotenv(path: Path) -> dict[str, str]:
    values = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text or text.startswith("#") or "=" not in text:
            continue
        key, value = text.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def append_jsonl(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def clean_json_text(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped, flags=re.I)
        stripped = re.sub(r"\s*```$", "", stripped)
    return stripped


def extract_first_json_object(text: str) -> str:
    start = text.find("{")
    if start < 0:
        return ""
    depth = 0
    in_string = False
    escape = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return text[start:]


def remove_trailing_commas(text: str) -> str:
    return re.sub(r",(\s*[}\]])", r"\1", text)


def parse_json_response(text: str) -> tuple[dict, str]:
    stripped = clean_json_text(text)
    candidates = [stripped]
    balanced = extract_first_json_object(stripped)
    if balanced and balanced not in candidates:
        candidates.append(balanced)
    last_error: json.JSONDecodeError | None = None
    for candidate in candidates:
        variants = [(candidate, False)]
        repaired = remove_trailing_commas(candidate)
        if repaired != candidate:
            variants.append((repaired, True))
        for variant, used_cleanup in variants:
            try:
                parsed = json.loads(variant)
            except json.JSONDecodeError as err:
                last_error = err
                continue
            if not isinstance(parsed, dict):
                raise ValueError("Gemini response JSON was not an object")
            method = "local_cleanup" if stripped != text.strip() or candidate != stripped or used_cleanup else "not_needed"
            return parsed, method
    if last_error:
        raise last_error
    raise json.JSONDecodeError("Gemini response JSON was empty", stripped, 0)


def compact_nonempty_dict(value: dict) -> dict:
    out = {}
    for key, item in value.items():
        if isinstance(item, str):
            text = normalize(item)
            if text:
                out[key] = text
        elif isinstance(item, (bool, int, float)):
            out[key] = item
        elif item:
            out[key] = item
    return out


def output_identity_for_task(task: dict) -> dict:
    route_context = task.get("route_context", {}) if isinstance(task.get("route_context"), dict) else {}
    contract = task.get("extraction_contract", {}) if isinstance(task.get("extraction_contract"), dict) else {}
    source_type = normalize(contract.get("source_type", "")) or normalize(route_context.get("source_type", "")) or "uncertain"
    out = {
        "task_id": normalize(task.get("task_id", "")) or normalize(task.get("route_id", "")),
        "route_id": normalize(task.get("route_id", "")) or normalize(route_context.get("route_id", "")),
        "study_doi": normalize(task.get("study_doi", "")) or normalize(route_context.get("doi", "")),
        "domain_route": normalize(contract.get("domain_route", "")) or normalize(route_context.get("domain_route", "")),
        "source_type": source_type,
    }
    if normalize(contract.get("schema_profile", "")) == "primary_evidence_schema":
        out["paper_type"] = "primary_study"
        out["text_depth"] = text_depth_for_task(task)
    return compact_nonempty_dict(out)


def metadata_for_model_input(task: dict) -> dict:
    metadata = task.get("paper_metadata", {}) if isinstance(task.get("paper_metadata"), dict) else {}
    keep_fields = (
        "doi",
        "pmid",
        "pmcid",
        "study_title",
        "study_year",
        "authors",
        "study_journal",
        "publication_type",
        "trial_registry_ids",
        "publication_date",
        "mesh_terms",
        "keywords",
        "language",
        "open_access_status",
    )
    return compact_nonempty_dict({field: metadata.get(field, "") for field in keep_fields})


def load_packet_index(path: str) -> dict[str, dict]:
    normalized_path = str(Path(path).resolve())
    if normalized_path in PACKET_INDEX_CACHE:
        return PACKET_INDEX_CACHE[normalized_path]
    packet_path = Path(normalized_path)
    index: dict[str, dict] = {}
    if packet_path.exists():
        for packet in read_jsonl(packet_path):
            if not isinstance(packet, dict):
                continue
            packet_id = normalize(packet.get("packet_id", ""))
            doi = normalize(packet.get("study_doi", "")) or normalize(packet.get("doi", ""))
            dataset = normalize(packet.get("dataset", ""))
            if packet_id:
                index[packet_id] = packet
            if dataset and doi:
                index.setdefault(f"{dataset}:{doi}", packet)
            if doi:
                index.setdefault(doi, packet)
    PACKET_INDEX_CACHE[normalized_path] = index
    return index


def packet_for_task(task: dict) -> dict | None:
    content = task.get("content", {}) if isinstance(task.get("content"), dict) else {}
    if isinstance(content.get("packet"), dict):
        return content["packet"]
    text_source = task.get("text_source", {}) if isinstance(task.get("text_source"), dict) else {}
    packet_source_path = normalize(text_source.get("packet_source_path", ""))
    if not packet_source_path:
        return None
    index = load_packet_index(packet_source_path)
    packet_id = normalize(text_source.get("packet_id", ""))
    if packet_id and packet_id in index:
        return index[packet_id]
    doi = normalize(task.get("study_doi", ""))
    return index.get(doi)


def article_or_abstract_text_for_task(task: dict) -> tuple[str, str]:
    content = task.get("content", {}) if isinstance(task.get("content"), dict) else {}
    depth = text_depth_for_task(task)
    if depth == "article_text":
        packet = packet_for_task(task)
        if packet:
            text = "\n\n".join(text_parts_from_packet(packet)).strip()
            if text:
                return "ARTICLE_TEXT", text
    title = normalize(content.get("title", ""))
    abstract = normalize(content.get("abstract", ""))
    parts = []
    if title:
        parts.append(f"Title: {title}")
    if abstract:
        parts.append(f"Abstract: {abstract}")
    return "ABSTRACT_TEXT", "\n\n".join(parts)


def build_contents(task: dict) -> str:
    text_label, evidence_text = article_or_abstract_text_for_task(task)
    return (
        "Extract structured evidence from the supplied paper information and text. "
        "Return one JSON object only.\n\n"
        "OUTPUT_FIELDS_TO_COPY:\n"
        f"{json.dumps(output_identity_for_task(task), ensure_ascii=False, indent=2)}\n\n"
        "PAPER_METADATA_JSON:\n"
        f"{json.dumps(metadata_for_model_input(task), ensure_ascii=False, indent=2)}\n\n"
        f"{text_label}:\n"
        f"{evidence_text}"
    )


def source_type_for_synthesis(task: dict) -> str:
    route_context = task.get("route_context", {}) if isinstance(task.get("route_context"), dict) else {}
    candidates = [
        normalize(route_context.get("source_type", "")),
        normalize(route_context.get("primary_secondary_source_type", "")),
    ]
    allowed = {
        "meta_analysis",
        "network_meta_analysis",
        "umbrella_review",
        "systematic_review",
        "secondary_evidence",
        "uncertain",
    }
    for candidate in candidates:
        if candidate in allowed:
            return candidate
    return "uncertain"


def inject_route_identity_fields(result: dict, task: dict, profile: RouteExtractionProfile) -> dict:
    out = dict(result)
    route_context = task.get("route_context", {}) if isinstance(task.get("route_context"), dict) else {}
    contract = task.get("extraction_contract", {}) if isinstance(task.get("extraction_contract"), dict) else {}
    out["schema_version"] = profile.output_schema_version
    out["task_id"] = normalize(task.get("task_id", "")) or normalize(task.get("route_id", ""))
    out["route_id"] = normalize(task.get("route_id", "")) or normalize(route_context.get("route_id", ""))
    out["study_doi"] = normalize(task.get("study_doi", "")) or normalize(route_context.get("doi", ""))
    out["domain_route"] = normalize(contract.get("domain_route", "")) or normalize(route_context.get("domain_route", ""))
    if profile.schema_profile == "synthesis_evidence_schema":
        out["source_type"] = source_type_for_synthesis(task)
    elif "source_type" not in out or not normalize(out.get("source_type", "")):
        out["source_type"] = normalize(route_context.get("source_type", "")) or "uncertain"
    return out


def schema_error_messages(validator: Draft7Validator, result: dict) -> list[str]:
    return [error.message for error in sorted(validator.iter_errors(result), key=lambda error: list(error.path))]


def task_is_ready(task: dict) -> bool:
    return normalize(task.get("task_status", "")) == "ready_for_model"


def task_matches_filters(task: dict, args: argparse.Namespace) -> bool:
    if args.only_ready and not task_is_ready(task):
        return False
    prompt_profile, schema_profile = profile_key_for_task(task)
    if args.prompt_profile and prompt_profile not in args.prompt_profile:
        return False
    if args.schema_profile and schema_profile not in args.schema_profile:
        return False
    if args.route_id and normalize(task.get("route_id", "")) not in args.route_id:
        return False
    if args.doi and normalize(task.get("study_doi", "")).lower() not in args.doi:
        return False
    registered = task_has_registered_profile(task)
    model_profile = task_has_model_profile(task, include_scaffold=args.include_scaffold_profiles)
    if not registered and args.include_unsupported:
        return True
    return model_profile


def selected_tasks(tasks: list[dict], args: argparse.Namespace) -> list[tuple[int, dict]]:
    start_index = max(1, int(args.start_index))
    selected = [
        (index, task)
        for index, task in enumerate(tasks, start=1)
        if index >= start_index and task_matches_filters(task, args)
    ]
    if args.limit > 0:
        selected = selected[: args.limit]
    return selected


def usage_dict(response: object) -> dict:
    usage = getattr(response, "usage_metadata", None)
    if usage is None:
        return {}
    try:
        return usage.model_dump()
    except Exception:
        return {}


def build_generation_config(
    *,
    system_instruction: str,
    schema: dict,
    schema_mode: str,
    temperature: float,
    max_output_tokens: int,
    thinking_budget: int | None = None,
) -> object:
    from google.genai import types

    config = {
        "response_mime_type": "application/json",
        "temperature": temperature,
        "max_output_tokens": max_output_tokens,
        "system_instruction": system_instruction,
    }
    if schema_in_native_config(schema_mode):
        config["response_json_schema"] = schema
    if thinking_budget is not None:
        config["thinking_config"] = types.ThinkingConfig(thinking_budget=thinking_budget)
    return types.GenerateContentConfig(**config)


def max_output_tokens_for_task(task: dict, profile: RouteExtractionProfile, args: argparse.Namespace) -> int:
    if int(args.max_output_tokens or 0) > 0:
        return int(args.max_output_tokens)
    return profile.default_max_output_tokens


def domain_route_for_task(task: dict) -> str:
    contract = task.get("extraction_contract", {}) if isinstance(task.get("extraction_contract"), dict) else {}
    route_context = task.get("route_context", {}) if isinstance(task.get("route_context"), dict) else {}
    return normalize(contract.get("domain_route", "")) or normalize(route_context.get("domain_route", ""))


def text_depth_for_task(task: dict) -> str:
    text_source = task.get("text_source", {}) if isinstance(task.get("text_source"), dict) else {}
    contract = task.get("extraction_contract", {}) if isinstance(task.get("extraction_contract"), dict) else {}
    access = normalize(text_source.get("access_level", "")) or normalize(contract.get("access_level", ""))
    return text_depth_from_access(access)


def model_from_env(args: argparse.Namespace) -> str:
    env_values = load_dotenv(Path(args.env_file).resolve())
    return normalize(args.model) or env_values.get("GEMINI_MODEL") or os.environ.get("GEMINI_MODEL", "") or "gemini-2.5-flash"


def api_key_from_env(args: argparse.Namespace) -> str:
    env_values = load_dotenv(Path(args.env_file).resolve())
    api_key = env_values.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        raise SystemExit("GEMINI_API_KEY is missing. Add it to project .env or the environment.")
    return api_key


def dry_run_report(tasks: list[dict], selected: list[tuple[int, dict]], args: argparse.Namespace) -> dict:
    ready_scope = [
        task
        for task in tasks
        if (not args.only_ready or task_is_ready(task))
    ]
    skipped_unregistered = [task for task in ready_scope if not task_has_registered_profile(task)]
    skipped_registered_non_model = [
        task
        for task in ready_scope
        if task_has_registered_profile(task) and not task_has_model_profile(task, include_scaffold=args.include_scaffold_profiles)
    ]
    return {
        "generated_at_utc": now_utc(),
        "schema_version": "route_extraction_run_report_v1",
        "status": "dry_run",
        "inputs": {
            "input_jsonl": str(Path(args.input_jsonl).resolve()),
            "schema_mode": args.schema_mode,
            "only_ready": bool(args.only_ready),
            "include_scaffold_profiles": bool(args.include_scaffold_profiles),
            "include_unsupported": bool(args.include_unsupported),
            "start_index": max(1, int(args.start_index)),
            "limit": int(args.limit),
        },
        "supported_profiles": supported_profile_keys(),
        "tasks_read": len(tasks),
        "tasks_selected": len(selected),
        "unregistered_tasks_skipped": len(skipped_unregistered),
        "registered_non_model_tasks_skipped": len(skipped_registered_non_model),
        "by_prompt_profile": dict(Counter(profile_key_for_task(task)[0] for _, task in selected)),
        "by_schema_profile": dict(Counter(profile_key_for_task(task)[1] for _, task in selected)),
        "by_task_status": dict(Counter(normalize(task.get("task_status", "")) for _, task in selected)),
        "by_profile_status": dict(Counter(profile_for_task(task).status for _, task in selected if task_has_registered_profile(task))),
        "selected_tasks": [
            {
                "input_row_index": index,
                "task_id": normalize(task.get("task_id", "")),
                "route_id": normalize(task.get("route_id", "")),
                "study_doi": normalize(task.get("study_doi", "")),
                "prompt_profile": profile_key_for_task(task)[0],
                "schema_profile": profile_key_for_task(task)[1],
                "task_status": normalize(task.get("task_status", "")),
            }
            for index, task in selected
        ],
    }


def run_tasks(args: argparse.Namespace) -> dict:
    input_jsonl = Path(args.input_jsonl).resolve()
    out_jsonl = Path(args.out_jsonl).resolve()
    raw_jsonl = Path(args.raw_jsonl).resolve()
    report_json = Path(args.report_json).resolve()
    if args.overwrite:
        for path in (out_jsonl, raw_jsonl, report_json):
            if path.exists():
                path.unlink()

    tasks = read_jsonl(input_jsonl)
    selected = selected_tasks(tasks, args)
    if args.dry_run:
        report = dry_run_report(tasks, selected, args)
        write_json(report_json, report)
        return report

    from google import genai

    client = genai.Client(api_key=api_key_from_env(args))
    model = model_from_env(args)
    status_counts: Counter = Counter()
    profile_counts: Counter = Counter()
    schema_counts: Counter = Counter()
    usage_totals: Counter = Counter()
    errors: list[dict] = []

    for position, (input_row_index, task) in enumerate(selected, start=1):
        profile = profile_for_task(task)
        schema = load_schema(profile.schema_path)
        assigned_domain = domain_route_for_task(task)
        model_schema = schema_for_assigned_domain(schema, assigned_domain)
        native_schema = schema_for_native(model_schema)
        validator = Draft7Validator(model_schema)
        system_instruction = build_system_instruction(
            profile,
            schema,
            args.schema_mode,
            domain_route=assigned_domain,
            text_depth=text_depth_for_task(task),
        )
        max_output_tokens = max_output_tokens_for_task(task, profile, args)
        raw_row = {
            "generated_at_utc": now_utc(),
            "input_row_index": input_row_index,
            "task_id": normalize(task.get("task_id", "")),
            "route_id": normalize(task.get("route_id", "")),
            "study_doi": normalize(task.get("study_doi", "")),
            "prompt_profile": profile.prompt_profile,
            "schema_profile": profile.schema_profile,
            "model": model,
            "status": "error",
        }
        print(
            f"[{position}/{len(selected)}] {profile.prompt_profile} {task.get('study_doi')} {task.get('route_id')}",
            flush=True,
        )
        try:
            response = client.models.generate_content(
                model=model,
                contents=build_contents(task),
                config=build_generation_config(
                    system_instruction=system_instruction,
                    schema=native_schema,
                    schema_mode=args.schema_mode,
                    temperature=args.temperature,
                    max_output_tokens=max_output_tokens,
                    thinking_budget=args.thinking_budget,
                ),
            )
            text = response.text or ""
            parsed, parse_method = parse_json_response(text)
            result = inject_route_identity_fields(parsed, task, profile)
            schema_errors = schema_error_messages(validator, result)
            usage = usage_dict(response)
            for key, value in usage.items():
                if isinstance(value, (int, float)):
                    usage_totals[key] += value
            raw_row.update(
                {
                    "status": "schema_error" if schema_errors else "ok",
                    "parse_method": parse_method,
                    "raw_text": text,
                    "schema_errors": schema_errors,
                    "usage": usage,
                    "max_output_tokens": max_output_tokens,
                }
            )
            append_jsonl(raw_jsonl, raw_row)
            append_jsonl(
                out_jsonl,
                {
                    "task_id": normalize(task.get("task_id", "")),
                    "route_id": normalize(task.get("route_id", "")),
                    "prompt_profile": profile.prompt_profile,
                    "schema_profile": profile.schema_profile,
                    "status": raw_row["status"],
                    "result": result,
                    "schema_errors": schema_errors,
                },
            )
            status_counts[raw_row["status"]] += 1
        except Exception as exc:  # pragma: no cover - exercised only during live API runs
            raw_row.update({"status": "error", "error": str(exc)})
            append_jsonl(raw_jsonl, raw_row)
            status_counts["error"] += 1
            errors.append(
                {
                    "task_id": normalize(task.get("task_id", "")),
                    "route_id": normalize(task.get("route_id", "")),
                    "error": str(exc),
                }
            )
        profile_counts[profile.prompt_profile] += 1
        schema_counts[profile.schema_profile] += 1
        if args.sleep_sec > 0:
            time.sleep(args.sleep_sec)

    report = {
        "generated_at_utc": now_utc(),
        "schema_version": "route_extraction_run_report_v1",
        "status": "complete",
        "inputs": {
            "input_jsonl": str(input_jsonl),
            "model": model,
            "schema_mode": args.schema_mode,
            "only_ready": bool(args.only_ready),
            "start_index": max(1, int(args.start_index)),
            "limit": int(args.limit),
        },
        "outputs": {
            "out_jsonl": str(out_jsonl),
            "raw_jsonl": str(raw_jsonl),
            "report_json": str(report_json),
        },
        "tasks_read": len(tasks),
        "tasks_selected": len(selected),
        "by_status": dict(status_counts),
        "by_prompt_profile": dict(profile_counts),
        "by_schema_profile": dict(schema_counts),
        "usage_totals": dict(usage_totals),
        "errors": errors[:50],
    }
    write_json(report_json, report)
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-jsonl", default=str(DEFAULT_INPUT))
    parser.add_argument("--out-jsonl", default=str(DEFAULT_OUTPUT_DIR / "route_extraction_outputs.jsonl"))
    parser.add_argument("--raw-jsonl", default=str(DEFAULT_OUTPUT_DIR / "route_extraction_raw.jsonl"))
    parser.add_argument("--report-json", default=str(DEFAULT_OUTPUT_DIR / "route_extraction_report.json"))
    parser.add_argument("--env-file", default=str(DEFAULT_ENV))
    parser.add_argument("--model", default="", help="Override GEMINI_MODEL from .env")
    parser.add_argument("--schema-mode", choices=SCHEMA_MODES, default="native")
    parser.add_argument("--prompt-profile", action="append", default=[])
    parser.add_argument("--schema-profile", action="append", default=[])
    parser.add_argument("--route-id", action="append", default=[])
    parser.add_argument("--doi", action="append", default=[])
    parser.add_argument("--start-index", type=int, default=1)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--include-not-ready", action="store_true")
    parser.add_argument(
        "--include-scaffold-profiles",
        action="store_true",
        help="Include scaffolded model profiles. Defaults to runnable profiles only.",
    )
    parser.add_argument(
        "--include-unsupported",
        action="store_true",
        help="Include unsupported profiles in dry-run reports; live runs still fail if selected.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Inspect selected tasks without making Gemini API calls")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--max-output-tokens", type=int, default=0, help="0 uses the route profile default")
    parser.add_argument("--thinking-budget", type=int, default=None)
    parser.add_argument("--sleep-sec", type=float, default=0.0)
    args = parser.parse_args()
    args.only_ready = not args.include_not_ready
    args.doi = [normalize(doi).lower() for doi in args.doi]
    return args


def main() -> int:
    args = parse_args()
    report = run_tasks(args)
    print(f"Report: {Path(args.report_json).resolve()}")
    print(f"Status: {report['status']}")
    print(f"Tasks selected: {report['tasks_selected']}")
    if "by_status" in report:
        print(f"By status: {report['by_status']}")
    else:
        print(f"By prompt profile: {report['by_prompt_profile']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
