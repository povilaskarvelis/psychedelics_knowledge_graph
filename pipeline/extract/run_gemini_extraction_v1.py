#!/usr/bin/env python3
"""Run extraction-v1 pilot records through Gemini."""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import json
import os
import re
import sys
import time
from collections import Counter
from pathlib import Path

try:
    from google import genai
    from google.genai import types
except ModuleNotFoundError as err:  # pragma: no cover - environment guard
    raise SystemExit("google-genai is required for Gemini extraction") from err

try:
    from jsonschema import Draft7Validator
except ModuleNotFoundError as err:  # pragma: no cover - environment guard
    raise SystemExit("jsonschema is required for Gemini extraction validation") from err

try:
    from pipeline.extract.extraction_v1_utils import normalize, normalize_extraction_v1_result, read_jsonl, write_json
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from pipeline.extract.extraction_v1_utils import normalize, normalize_extraction_v1_result, read_jsonl, write_json


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = ROOT / "data" / "processed" / "extraction" / "extraction_v1_pilot_inputs.jsonl"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "processed" / "extraction"
DEFAULT_PROMPT = ROOT / "docs" / "extraction_v1_prompt.md"
DEFAULT_MECHANISTIC_PROMPT = ROOT / "docs" / "extraction_v1_mechanistic_prompt.md"
DEFAULT_DISORDER_PROMPT = ROOT / "docs" / "extraction_v1_disorder_prompt.md"
DEFAULT_SCHEMA = ROOT / "schema" / "extraction_v1.schema.json"
DEFAULT_ENV = ROOT / ".env"
SCHEMA_MODES = ("native", "prompt", "both")


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


def load_schema(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def compact_schema_for_prompt(schema: dict) -> str:
    return json.dumps(schema, ensure_ascii=False, separators=(",", ":"))


COMMON_PROMPT_CLAIM_FIELDS = (
    "claim_type",
    "compound",
    "target",
    "disorder",
    "raw_entity_label",
    "entity_role",
    "clinical_context_condition",
    "graph_entity_label",
    "graph_entity_type",
    "graph_include_candidate",
    "graph_exclusion_reason",
    "support",
    "study_design",
    "system",
    "evidence_location",
    "evidence_locator",
    "supporting_quote",
    "confidence",
    "needs_human_review",
    "notes",
)

MECHANISTIC_PROMPT_CLAIM_FIELDS = COMMON_PROMPT_CLAIM_FIELDS + (
    "assay_type",
    "assay_family",
    "affinity_type",
    "affinity_value",
    "affinity_unit",
    "action_type",
    "species",
    "model_or_system",
    "result_direction",
)

DISORDER_PROMPT_CLAIM_FIELDS = COMMON_PROMPT_CLAIM_FIELDS + (
    "outcome_type",
    "outcome_domain",
    "outcome_measure",
    "result_direction",
    "sample_size_total",
    "population",
    "intervention_or_exposure",
    "comparator",
    "dose",
    "route",
    "session_count_or_duration",
    "timepoint",
    "adverse_events",
)

MECHANISTIC_ENTITY_ROLES = (
    "molecular_target",
    "gene_or_variant",
    "pathway_or_process",
    "brain_region_or_circuit",
    "assay_readout",
    "physiological_measure",
    "biomarker",
    "functional_outcome",
    "compound_or_class",
    "not_applicable",
    "uncertain",
)

DISORDER_ENTITY_ROLES = (
    "therapeutic_indication",
    "symptom_or_problem",
    "outcome_measure",
    "physiological_measure",
    "safety_or_adverse_event",
    "biomarker",
    "functional_outcome",
    "patient_reported_outcome",
    "population_or_context",
    "compound_or_class",
    "not_applicable",
    "uncertain",
)


def prompt_claim_schema(schema: dict, dataset: str) -> dict:
    claim = copy.deepcopy(schema["definitions"]["claim"])
    if dataset == "mechanistic":
        fields = MECHANISTIC_PROMPT_CLAIM_FIELDS
        extra_required = ("assay_type", "affinity_type", "result_direction")
        claim["properties"]["claim_type"]["enum"] = ["compound_target"]
        claim["properties"]["disorder"] = {"type": "string", "enum": ["not_applicable"]}
        claim["properties"]["result_direction"]["enum"] = ["not_applicable"]
        claim["properties"]["entity_role"]["enum"] = list(MECHANISTIC_ENTITY_ROLES)
        claim["properties"]["graph_entity_type"]["enum"] = ["target", "none", "uncertain"]
    elif dataset == "disorder":
        fields = DISORDER_PROMPT_CLAIM_FIELDS
        extra_required = ("outcome_domain", "outcome_type", "outcome_measure", "result_direction")
        claim["properties"]["claim_type"]["enum"] = ["compound_disorder"]
        claim["properties"]["target"] = {"type": "string", "enum": ["not_applicable"]}
        claim["properties"]["result_direction"]["enum"] = ["positive", "null", "negative", "mixed", "unclear"]
        claim["properties"]["entity_role"]["enum"] = list(DISORDER_ENTITY_ROLES)
        claim["properties"]["graph_entity_type"]["enum"] = ["indication", "none", "uncertain"]
    else:
        raise ValueError(f"Unsupported extraction dataset `{dataset}`")

    claim["properties"] = {field: claim["properties"][field] for field in fields if field in claim["properties"]}
    required = list(claim["required"])
    for field in extra_required:
        if field not in required:
            required.append(field)
    claim["required"] = [field for field in required if field in claim["properties"]]
    claim.pop("allOf", None)
    return claim


def prompt_coverage_schema(schema: dict, dataset: str) -> dict:
    coverage = copy.deepcopy(schema["definitions"]["coverage_mention"])
    if dataset == "mechanistic":
        coverage["properties"]["relationship_domain"]["enum"] = [
            "compound_target",
            "compound_only",
            "target_only",
            "general_topic",
            "not_applicable",
        ]
        coverage["properties"]["entity_type"]["enum"] = ["target", "compound", "general_topic", "not_applicable"]
    elif dataset == "disorder":
        coverage["properties"]["relationship_domain"]["enum"] = [
            "compound_disorder",
            "compound_only",
            "disorder_only",
            "general_topic",
            "not_applicable",
        ]
        coverage["properties"]["entity_type"]["enum"] = ["disorder", "compound", "general_topic", "not_applicable"]
    else:
        raise ValueError(f"Unsupported extraction dataset `{dataset}`")
    coverage.pop("allOf", None)
    return coverage


def schema_view_for_prompt(schema: dict, dataset: str) -> dict:
    """Return a smaller model-facing schema; canonical validation still uses the full schema."""
    view = {
        "$schema": schema.get("$schema", ""),
        "title": f"{schema.get('title', 'Extraction V1 Result')} Prompt View ({dataset})",
        "type": "object",
        "additionalProperties": schema.get("additionalProperties", False),
        "required": list(schema["required"]),
        "properties": copy.deepcopy(schema["properties"]),
        "definitions": {
            "paper_assessment": copy.deepcopy(schema["definitions"]["paper_assessment"]),
            "claim": prompt_claim_schema(schema, dataset),
            "coverage_mention": prompt_coverage_schema(schema, dataset),
            "evidence_location": copy.deepcopy(schema["definitions"]["evidence_location"]),
        },
    }
    view["properties"]["dataset"]["enum"] = [dataset]
    return view


def resolve_schema_refs(value: object, definitions: dict) -> object:
    if isinstance(value, list):
        return [resolve_schema_refs(item, definitions) for item in value]
    if not isinstance(value, dict):
        return value
    if "$ref" in value:
        ref = normalize(value.get("$ref", ""))
        prefix = "#/definitions/"
        if not ref.startswith(prefix):
            raise ValueError(f"Unsupported schema reference `{ref}`")
        name = ref.removeprefix(prefix)
        if name not in definitions:
            raise ValueError(f"Unknown schema definition `{name}`")
        resolved = copy.deepcopy(definitions[name])
        for key, item in value.items():
            if key != "$ref":
                resolved[key] = item
        return resolve_schema_refs(resolved, definitions)
    return {key: resolve_schema_refs(item, definitions) for key, item in value.items()}


def schema_view_for_native(schema: dict, dataset: str) -> dict:
    """Return an inlined schema view for Gemini native structured output mode."""
    view = schema_view_for_prompt(schema, dataset)
    definitions = view.get("definitions", {})
    view = resolve_schema_refs(view, definitions)
    if isinstance(view, dict):
        view.pop("definitions", None)
        view.pop("$schema", None)
    return view


def packet_id_for_record(record: dict) -> str:
    content = record.get("content", {}) if isinstance(record.get("content"), dict) else {}
    packet = content.get("packet") if isinstance(content.get("packet"), dict) else None
    return normalize((packet or content).get("packet_id", ""))


def inject_identity_fields(result: dict, record: dict) -> dict:
    out = dict(result)
    out["schema_version"] = "extraction_v1"
    out["dataset"] = normalize(record.get("dataset", ""))
    out["study_doi"] = normalize(record.get("study_doi", ""))
    out["access_level"] = normalize(record.get("access_level", ""))
    out["input_record_id"] = normalize(record.get("pilot_record_id", ""))
    packet_id = packet_id_for_record(record)
    if packet_id:
        out["input_packet_id"] = packet_id
    metadata = record.get("paper_metadata", {}) if isinstance(record.get("paper_metadata"), dict) else {}
    openalex_id = normalize(metadata.get("openalex_id", ""))
    if openalex_id and not normalize(out.get("openalex_id", "")):
        out["openalex_id"] = openalex_id
    return out


def parse_json_response(text: str) -> dict:
    parsed, _method = parse_json_response_with_method(text)
    return parsed


def parse_json_response_with_method(text: str) -> tuple[dict, str]:
    stripped = clean_json_text(text)
    used_fence_cleanup = stripped != text.strip()
    last_error: json.JSONDecodeError | None = None
    for candidate in json_candidates(stripped):
        used_object_extraction = candidate != stripped
        for variant, used_trailing_cleanup in json_variants(candidate):
            try:
                parsed = json.loads(variant)
            except json.JSONDecodeError as err:
                last_error = err
                continue
            if not isinstance(parsed, dict):
                raise ValueError("Gemini response JSON was not an object")
            method = (
                "local_cleanup"
                if used_fence_cleanup or used_object_extraction or used_trailing_cleanup
                else "not_needed"
            )
            return parsed, method
    if last_error:
        raise last_error
    raise json.JSONDecodeError("Gemini response JSON was empty", stripped, 0)


def response_looks_truncated_json(text: str) -> bool:
    stripped = clean_json_text(text).strip()
    start = stripped.find("{")
    if start < 0:
        return False
    depth = 0
    in_string = False
    escape = False
    for char in stripped[start:]:
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
                return False
    return depth > 0 or in_string


def clean_json_text(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped, flags=re.I)
        stripped = re.sub(r"\s*```$", "", stripped)
    return stripped


def json_candidates(text: str) -> list[str]:
    candidates = [text]
    balanced = extract_first_json_object(text)
    if balanced and balanced not in candidates:
        candidates.append(balanced)
    return candidates


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


def json_variants(candidate: str) -> list[tuple[str, bool]]:
    variants = [(candidate, False)]
    repaired = remove_trailing_commas(candidate)
    if repaired != candidate:
        variants.append((repaired, True))
    return variants


def schema_in_prompt(schema_mode: str) -> bool:
    return schema_mode in {"prompt", "both"}


def schema_in_native_config(schema_mode: str) -> bool:
    return schema_mode in {"native", "both"}


def build_generation_config(
    *,
    system_instruction: str = "",
    schema: dict | None = None,
    schema_mode: str,
    temperature: float,
    max_output_tokens: int,
    thinking_budget: int | None = None,
) -> types.GenerateContentConfig:
    config = {
        "response_mime_type": "application/json",
        "temperature": temperature,
        "max_output_tokens": max_output_tokens,
    }
    if system_instruction:
        config["system_instruction"] = system_instruction
    if schema_in_native_config(schema_mode):
        if schema is None:
            raise ValueError("Native schema mode requires a schema")
        config["response_json_schema"] = schema
    if thinking_budget is not None:
        config["thinking_config"] = types.ThinkingConfig(thinking_budget=thinking_budget)
    return types.GenerateContentConfig(**config)


def max_output_tokens_for_record(record: dict, args: argparse.Namespace) -> int:
    dataset = normalize(record.get("dataset", ""))
    dataset_override = {
        "mechanistic": getattr(args, "mechanistic_max_output_tokens", 0),
        "disorder": getattr(args, "disorder_max_output_tokens", 0),
    }.get(dataset, 0)
    return int(dataset_override) if int(dataset_override or 0) > 0 else int(args.max_output_tokens)


def repair_json_with_model(
    *,
    client: genai.Client,
    model: str,
    malformed_text: str,
    schema: dict,
    max_output_tokens: int,
    schema_mode: str = "prompt",
    thinking_budget: int | None = 0,
) -> tuple[dict, str, dict]:
    prompt_parts = [
        "Repair the malformed JSON below. Return one valid JSON object only. "
        "Do not add prose, Markdown, comments, or code fences. Do not change "
        "the scientific meaning or invent missing facts; only fix JSON syntax "
        "and keep property names compatible with the schema."
    ]
    if schema_in_prompt(schema_mode):
        prompt_parts.append("JSON_SCHEMA:\n" + compact_schema_for_prompt(schema))
    else:
        prompt_parts.append("The API response_json_schema defines the required output shape.")
    prompt_parts.append("MALFORMED_JSON:\n" + malformed_text)
    response = client.models.generate_content(
        model=model,
        contents="\n\n".join(prompt_parts),
        config=build_generation_config(
            schema=schema,
            schema_mode=schema_mode,
            temperature=0,
            max_output_tokens=max_output_tokens,
            thinking_budget=thinking_budget,
        ),
    )
    repaired_text = response.text or ""
    return parse_json_response(repaired_text), repaired_text, usage_dict(response)


def build_contents(record: dict) -> str:
    return (
        "Extract this paper using the extraction-v1 contract. "
        "Return one JSON object only.\n\n"
        "INPUT_RECORD_JSON:\n"
        f"{json.dumps(record, ensure_ascii=False, indent=2)}"
    )


def build_system_instruction(
    prompt_text: str,
    schema: dict | None = None,
    dataset_prompt_text: str = "",
    *,
    include_schema: bool = True,
) -> str:
    parts = [prompt_text.strip()]
    if dataset_prompt_text.strip():
        parts.append(dataset_prompt_text.strip())
    if include_schema:
        if schema is None:
            raise ValueError("Prompt schema mode requires a schema")
        parts.append(
            "The output must validate against this JSON Schema. "
            "Use the exact property names and enum values.\n\n"
            + compact_schema_for_prompt(schema)
        )
    else:
        parts.append(
            "The API response_json_schema defines the required output shape. "
            "Use the exact property names and enum values."
        )
    return "\n\n".join(parts)


def system_instruction_for_record(record: dict, system_instructions: dict[str, str]) -> str:
    dataset = normalize(record.get("dataset", ""))
    if dataset not in system_instructions:
        raise ValueError(f"Unsupported extraction dataset `{dataset}`")
    return system_instructions[dataset]


def append_jsonl(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def schema_error_messages(validator: Draft7Validator, result: dict) -> list[str]:
    return [error.message for error in sorted(validator.iter_errors(result), key=lambda error: list(error.path))]


def usage_dict(response: object) -> dict:
    usage = getattr(response, "usage_metadata", None)
    if usage is None:
        return {}
    try:
        return usage.model_dump()
    except Exception:
        return {}


def completed_input_ids(raw_jsonl: Path) -> set[str]:
    completed = set()
    if not raw_jsonl.exists():
        return completed
    for row in read_jsonl(raw_jsonl):
        if row.get("status") in {"ok", "schema_error"}:
            record_id = normalize(row.get("input_record_id", ""))
            if record_id:
                completed.add(record_id)
    return completed


def retry_delay_for_error(exc: Exception, default_delay: float) -> float:
    text = str(exc)
    match = re.search(r"retry in ([0-9.]+)s", text, flags=re.I)
    if match:
        try:
            return max(default_delay, float(match.group(1)) + 2.0)
        except ValueError:
            return default_delay
    if "RESOURCE_EXHAUSTED" in text or "429" in text:
        return max(default_delay, 45.0)
    return default_delay


def main() -> int:
    parser = argparse.ArgumentParser(description="Run extraction-v1 records through Gemini")
    parser.add_argument("--input-jsonl", default=str(DEFAULT_INPUT))
    parser.add_argument("--out-jsonl", default=str(DEFAULT_OUTPUT_DIR / "extraction_v1_outputs.jsonl"))
    parser.add_argument("--raw-jsonl", default=str(DEFAULT_OUTPUT_DIR / "extraction_v1_gemini_raw.jsonl"))
    parser.add_argument("--report-json", default=str(DEFAULT_OUTPUT_DIR / "extraction_v1_gemini_report.json"))
    parser.add_argument("--prompt", default=str(DEFAULT_PROMPT))
    parser.add_argument("--mechanistic-prompt", default=str(DEFAULT_MECHANISTIC_PROMPT))
    parser.add_argument("--disorder-prompt", default=str(DEFAULT_DISORDER_PROMPT))
    parser.add_argument("--schema", default=str(DEFAULT_SCHEMA))
    parser.add_argument("--env-file", default=str(DEFAULT_ENV))
    parser.add_argument("--model", default="", help="Override GEMINI_MODEL from .env")
    parser.add_argument(
        "--schema-mode",
        choices=SCHEMA_MODES,
        default="native",
        help="Use Gemini native response_json_schema, prompt-embedded schema text, or both",
    )
    parser.add_argument("--limit", type=int, default=0, help="Maximum records to process; 0 means all")
    parser.add_argument("--start-index", type=int, default=1, help="1-based input row index to start from")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--max-output-tokens", type=int, default=8192)
    parser.add_argument(
        "--mechanistic-max-output-tokens",
        type=int,
        default=16384,
        help="Override max output tokens for mechanistic records; 0 uses --max-output-tokens",
    )
    parser.add_argument(
        "--disorder-max-output-tokens",
        type=int,
        default=0,
        help="Override max output tokens for disorder records; 0 uses --max-output-tokens",
    )
    parser.add_argument("--sleep-sec", type=float, default=0.0)
    parser.add_argument("--retry-sleep-sec", type=float, default=5.0)
    parser.add_argument("--max-retries", type=int, default=2)
    parser.add_argument(
        "--thinking-budget",
        type=int,
        default=None,
        help=(
            "Optional Gemini thinking budget. For Gemini 2.5 Flash, 0 disables thinking; "
            "-1 leaves dynamic thinking to the model. Omit to use the API/model default."
        ),
    )
    parser.add_argument("--disable-json-repair", action="store_true", help="Do not make a repair call for malformed JSON responses")
    parser.add_argument("--json-repair-max-output-tokens", type=int, default=8192)
    parser.add_argument(
        "--json-repair-thinking-budget",
        type=int,
        default=0,
        help="Thinking budget for JSON repair calls; repair is syntax-focused, so the default disables thinking.",
    )
    parser.add_argument("--resume", action="store_true", help="Skip rows already completed in raw JSONL")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite output/checkpoint files before running")
    args = parser.parse_args()

    input_jsonl = Path(args.input_jsonl).resolve()
    out_jsonl = Path(args.out_jsonl).resolve()
    raw_jsonl = Path(args.raw_jsonl).resolve()
    report_json = Path(args.report_json).resolve()
    schema_path = Path(args.schema).resolve()
    prompt_path = Path(args.prompt).resolve()
    mechanistic_prompt_path = Path(args.mechanistic_prompt).resolve()
    disorder_prompt_path = Path(args.disorder_prompt).resolve()
    env_values = load_dotenv(Path(args.env_file).resolve())
    api_key = env_values.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY", "")
    model = normalize(args.model) or env_values.get("GEMINI_MODEL") or os.environ.get("GEMINI_MODEL", "") or "gemini-2.5-flash"
    if not api_key:
        raise SystemExit("GEMINI_API_KEY is missing. Add it to project .env or the environment.")

    if args.overwrite:
        for path in (out_jsonl, raw_jsonl, report_json):
            if path.exists():
                path.unlink()

    records = read_jsonl(input_jsonl)
    completed_ids = completed_input_ids(raw_jsonl) if args.resume else set()
    start_index = max(1, args.start_index)
    selected = [
        (idx, record)
        for idx, record in enumerate(records, start=1)
        if idx >= start_index and normalize(record.get("pilot_record_id", "")) not in completed_ids
    ]
    if args.limit > 0:
        selected = selected[: args.limit]

    schema = load_schema(schema_path)
    validator = Draft7Validator(schema)
    shared_prompt_text = prompt_path.read_text(encoding="utf-8")
    prompt_schema_views = {
        "mechanistic": schema_view_for_prompt(schema, "mechanistic"),
        "disorder": schema_view_for_prompt(schema, "disorder"),
    }
    native_schema_views = {
        "mechanistic": schema_view_for_native(schema, "mechanistic"),
        "disorder": schema_view_for_native(schema, "disorder"),
    }
    system_instructions = {
        "mechanistic": build_system_instruction(
            shared_prompt_text,
            prompt_schema_views["mechanistic"],
            mechanistic_prompt_path.read_text(encoding="utf-8"),
            include_schema=schema_in_prompt(args.schema_mode),
        ),
        "disorder": build_system_instruction(
            shared_prompt_text,
            prompt_schema_views["disorder"],
            disorder_prompt_path.read_text(encoding="utf-8"),
            include_schema=schema_in_prompt(args.schema_mode),
        ),
    }
    client = genai.Client(api_key=api_key)
    status_counts: Counter = Counter()
    route_counts: Counter = Counter()
    repair_counts: Counter = Counter()
    total_usage: Counter = Counter()
    retry_error_counts: Counter = Counter()
    retry_attempt_count = 0

    for position, (row_index, record) in enumerate(selected, start=1):
        record_id = normalize(record.get("pilot_record_id", "")) or f"row-{row_index}"
        record_max_output_tokens = max_output_tokens_for_record(record, args)
        print(
            f"[{position}/{len(selected)}] {record.get('dataset')} {record.get('bucket')} "
            f"{record.get('study_doi')} {record.get('route_hint', {}).get('hint', '')}",
            flush=True,
        )
        raw_row = {
            "generated_at_utc": now_utc(),
            "input_row_index": row_index,
            "input_record_id": record_id,
            "dataset": normalize(record.get("dataset", "")),
            "study_doi": normalize(record.get("study_doi", "")),
            "model": model,
            "max_output_tokens": record_max_output_tokens,
            "status": "error",
        }
        try:
            response = None
            text = ""
            parsed = None
            repair_method = "not_needed"
            repair_text = ""
            repair_usage = {}
            normalization_changes: list[str] = []
            retry_errors: list[dict[str, object]] = []
            attempts_used = 0
            attempts = max(1, args.max_retries + 1)
            for attempt in range(1, attempts + 1):
                try:
                    attempts_used = attempt
                    response = client.models.generate_content(
                        model=model,
                        contents=build_contents(record),
                        config=build_generation_config(
                            system_instruction=system_instruction_for_record(record, system_instructions),
                            schema=native_schema_views[normalize(record.get("dataset", ""))],
                            schema_mode=args.schema_mode,
                            temperature=args.temperature,
                            max_output_tokens=record_max_output_tokens,
                            thinking_budget=args.thinking_budget,
                        ),
                    )
                    text = response.text or ""
                    try:
                        parsed_payload, repair_method = parse_json_response_with_method(text)
                        parsed, normalization_changes = normalize_extraction_v1_result(
                            inject_identity_fields(parsed_payload, record)
                        )
                    except Exception:
                        if args.disable_json_repair:
                            raise
                        if response_looks_truncated_json(text):
                            raise RuntimeError("Gemini response looked truncated before JSON repair")
                        repaired, repair_text, repair_usage = repair_json_with_model(
                            client=client,
                            model=model,
                            malformed_text=text,
                            schema=(
                                native_schema_views[normalize(record.get("dataset", ""))]
                                if schema_in_native_config(args.schema_mode)
                                else prompt_schema_views[normalize(record.get("dataset", ""))]
                            ),
                            max_output_tokens=args.json_repair_max_output_tokens,
                            schema_mode=args.schema_mode,
                            thinking_budget=args.json_repair_thinking_budget,
                        )
                        parsed, normalization_changes = normalize_extraction_v1_result(
                            inject_identity_fields(repaired, record)
                        )
                        repair_method = "model_repair"
                    break
                except Exception as attempt_exc:
                    if attempt >= attempts:
                        raise
                    delay = retry_delay_for_error(attempt_exc, args.retry_sleep_sec)
                    retry_attempt_count += 1
                    retry_error_counts[type(attempt_exc).__name__] += 1
                    retry_errors.append(
                        {
                            "attempt": attempt,
                            "error_type": type(attempt_exc).__name__,
                            "error": str(attempt_exc).replace(api_key, "[REDACTED]"),
                            "delay_sec": delay,
                        }
                    )
                    print(f"  retrying after {type(attempt_exc).__name__}: sleeping {delay:.1f}s")
                    time.sleep(delay)
            if response is None or parsed is None:
                raise RuntimeError("Gemini did not return a parseable response")
            errors = schema_error_messages(validator, parsed)
            route = normalize((parsed.get("paper_assessment") or {}).get("route", "")) if isinstance(parsed.get("paper_assessment"), dict) else ""
            status = "ok" if not errors else "schema_error"
            status_counts[status] += 1
            if route:
                route_counts[route] += 1
            repair_counts[repair_method] += 1
            usage = usage_dict(response)
            for key, value in usage.items():
                if isinstance(value, int):
                    total_usage[key] += value
            for key, value in repair_usage.items():
                if isinstance(value, int):
                    total_usage[f"repair_{key}"] += value
            raw_row.update(
                {
                    "status": status,
                    "schema_errors": errors,
                    "route": route,
                    "max_output_tokens": record_max_output_tokens,
                    "usage": usage,
                    "json_repair_method": repair_method,
                    "normalization_changes": normalization_changes,
                    "attempts_used": attempts_used,
                    "retry_errors": retry_errors,
                    "repair_usage": repair_usage,
                    "response_text": text,
                    "repair_response_text": repair_text,
                    "parsed": parsed,
                }
            )
            append_jsonl(raw_jsonl, raw_row)
            append_jsonl(out_jsonl, parsed)
        except Exception as exc:
            status_counts["error"] += 1
            raw_row.update(
                {
                    "status": "error",
                    "error_type": type(exc).__name__,
                    "error": str(exc).replace(api_key, "[REDACTED]"),
                    "attempts_used": locals().get("attempts_used", 0),
                    "retry_errors": locals().get("retry_errors", []),
                    "response_text": text if "text" in locals() else "",
                }
            )
            append_jsonl(raw_jsonl, raw_row)
        if args.sleep_sec > 0 and position < len(selected):
            time.sleep(args.sleep_sec)

    report = {
        "generated_at_utc": now_utc(),
        "schema_version": "extraction_v1_gemini_report",
        "status": "ok" if not status_counts.get("error") and not status_counts.get("schema_error") else "issues_found",
        "inputs": {
            "input_jsonl": str(input_jsonl),
            "prompt": str(prompt_path),
            "prompts": {
                "shared": str(prompt_path),
                "mechanistic": str(mechanistic_prompt_path),
                "disorder": str(disorder_prompt_path),
            },
            "schema": str(schema_path),
            "schema_mode": args.schema_mode,
            "schema_prompt_view": "dataset_specific",
            "schema_prompt_view_compact_chars": {
                "mechanistic": len(compact_schema_for_prompt(prompt_schema_views["mechanistic"])),
                "disorder": len(compact_schema_for_prompt(prompt_schema_views["disorder"])),
                "canonical": len(compact_schema_for_prompt(schema)),
            },
            "schema_native_view_compact_chars": {
                "mechanistic": len(compact_schema_for_prompt(native_schema_views["mechanistic"])),
                "disorder": len(compact_schema_for_prompt(native_schema_views["disorder"])),
            },
            "model": model,
            "start_index": start_index,
            "limit": args.limit,
            "max_output_tokens": args.max_output_tokens,
            "mechanistic_max_output_tokens": args.mechanistic_max_output_tokens,
            "disorder_max_output_tokens": args.disorder_max_output_tokens,
            "thinking_budget": args.thinking_budget,
            "json_repair_thinking_budget": args.json_repair_thinking_budget,
            "resume": args.resume,
            "skipped_completed_records": len(completed_ids),
            "processed_records": len(selected),
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
            "retry_attempt_count": retry_attempt_count,
            "retry_error_counts": dict(retry_error_counts),
            "usage": dict(total_usage),
        },
    }
    write_json(report_json, report)
    print(f"Status counts: {dict(status_counts)}")
    print(f"Route counts: {dict(route_counts)}")
    print(f"Output: {out_jsonl}")
    print(f"Raw: {raw_jsonl}")
    print(f"Report: {report_json}")
    return 1 if status_counts.get("error") or status_counts.get("schema_error") else 0


if __name__ == "__main__":
    raise SystemExit(main())
