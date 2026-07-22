#!/usr/bin/env python3
"""Extract one paper-centered relationship bundle from each review.

Every review is read once. Full-text reviews and abstract-only reviews use
separate prompts but the same final schema. Domain labels are assigned inside
the extracted relationships, after the paper's main contribution is identified.
"""

from __future__ import annotations

import argparse
from collections import Counter
import datetime as dt
import hashlib
import json
from pathlib import Path
import shutil
import sys

from jsonschema import Draft7Validator

try:
    from pipeline.extract.io_utils import normalize, read_jsonl, text_parts_from_packet, write_json
    from pipeline.extract.route_extraction_profiles import schema_for_native
    from pipeline.extract.run_route_extraction import (
        DEFAULT_ENV,
        DEFAULT_GEMINI_MODEL,
        api_key_from_env,
        build_generation_config,
        load_dotenv,
        parse_json_response,
        reject_corrupt_output_text,
        usage_dict,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from pipeline.extract.io_utils import normalize, read_jsonl, text_parts_from_packet, write_json
    from pipeline.extract.route_extraction_profiles import schema_for_native
    from pipeline.extract.run_route_extraction import (
        DEFAULT_ENV,
        DEFAULT_GEMINI_MODEL,
        api_key_from_env,
        build_generation_config,
        load_dotenv,
        parse_json_response,
        reject_corrupt_output_text,
        usage_dict,
    )


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TASKS = (
    ROOT
    / "data"
    / "processed"
    / "extraction"
    / "review_relationship_tasks"
    / "review_relationship_tasks.jsonl"
)
DEFAULT_RUN_ROOT = ROOT / "data" / "processed" / "extraction" / "review_relationship_runs"
FULL_TEXT_PROMPT = ROOT / "docs" / "extraction_profiles" / "review_relationships_v2" / "full_text_extraction.md"
ABSTRACT_PROMPT = ROOT / "docs" / "extraction_profiles" / "review_relationships_v2" / "abstract_extraction.md"
BUNDLE_SCHEMA = ROOT / "schema" / "review_relationships_v2.bundle.schema.json"


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def archive_run_inputs(run_dir: Path, tasks_path: Path, args: argparse.Namespace) -> dict:
    """Save the exact prompts, schema, task list, and model settings for a run."""
    snapshot_dir = run_dir / "input_snapshot"
    artifact_groups = {
        "prompts": [Path(args.full_text_prompt), Path(args.abstract_prompt)],
        "schemas": [Path(args.bundle_schema)],
        "tasks": [tasks_path],
    }
    archived: list[dict] = []
    for group, sources in artifact_groups.items():
        for source in sources:
            source = source.resolve()
            destination = snapshot_dir / group / source.name
            source_hash = file_sha256(source)
            if destination.exists() and file_sha256(destination) != source_hash and not args.overwrite:
                raise ValueError(
                    f"Run input changed since this run started: {source}. "
                    "Use a new run ID or --overwrite."
                )
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            archived.append(
                {
                    "group": group,
                    "source_path": str(source),
                    "archived_path": str(destination),
                    "sha256": source_hash,
                }
            )

    manifest = {
        "schema_version": "review_relationship_input_snapshot_v2",
        "created_at_utc": now_utc(),
        "run_id": args.run_id,
        "model": args.model,
        "thinking_budget": args.thinking_budget,
        "max_output_tokens": args.max_output_tokens,
        "artifacts": archived,
    }
    write_json(snapshot_dir / "manifest.json", manifest)
    return manifest


def load_schema(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


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


def metadata_block(task: dict) -> str:
    metadata = task.get("paper_metadata", {}) if isinstance(task.get("paper_metadata"), dict) else {}
    return json.dumps(metadata, ensure_ascii=False, indent=2)


def source_text_for_task(task: dict, packet: dict | None) -> str:
    depth = normalize(task.get("text_depth", ""))
    metadata = task.get("paper_metadata", {}) if isinstance(task.get("paper_metadata"), dict) else {}
    if depth == "article_text":
        if not packet:
            raise ValueError(f"Missing article packet for {task.get('study_doi')}")
        return "\n\n".join(text_parts_from_packet(packet)).strip()
    title = normalize(metadata.get("study_title", ""))
    abstract = normalize(metadata.get("abstract", ""))
    return f"Title: {title}\n\nAbstract: {abstract}".strip()


def model_contents(task: dict, packet: dict | None) -> str:
    depth = normalize(task.get("text_depth", ""))
    source_label = "ARTICLE_TEXT" if depth == "article_text" else "ABSTRACT_TEXT"
    return (
        "PAPER_METADATA_JSON:\n"
        + metadata_block(task)
        + f"\n\n{source_label}:\n"
        + source_text_for_task(task, packet)
    )


def schema_errors(schema: dict, result: dict) -> list[str]:
    validator = Draft7Validator(schema)
    return [
        error.message
        for error in sorted(validator.iter_errors(result), key=lambda error: list(error.path))
    ]


def bundle_semantic_errors(bundle: dict) -> list[str]:
    """Flag internal inconsistencies without making another model call."""
    errors: list[str] = []
    frame = bundle.get("paper_frame", {}) if isinstance(bundle.get("paper_frame"), dict) else {}
    aspects = [item for item in frame.get("major_aspects", []) if isinstance(item, dict)]
    relationships = [item for item in bundle.get("relationships", []) if isinstance(item, dict)]

    aspect_ids = [normalize(item.get("aspect_id", "")) for item in aspects]
    relationship_ids = [normalize(item.get("item_id", "")) for item in relationships]
    if len(aspect_ids) != len(set(aspect_ids)):
        errors.append("duplicate_major_aspect_ids")
    if len(relationship_ids) != len(set(relationship_ids)):
        errors.append("duplicate_relationship_item_ids")

    importance_by_aspect = {
        normalize(item.get("aspect_id", "")): normalize(item.get("importance", ""))
        for item in aspects
        if normalize(item.get("aspect_id", ""))
    }
    strong_basis = {
        "title_scope",
        "stated_objective",
        "abstract_result",
        "repeated_synthesis",
        "discussion_emphasis",
        "review_conclusion",
    }
    for item in relationships:
        item_id = normalize(item.get("item_id", ""))
        prominence = normalize(item.get("paper_prominence", ""))
        eligibility = normalize(item.get("graph_eligibility", ""))
        covered = {normalize(value) for value in item.get("covers_major_aspect_ids", []) if normalize(value)}
        unknown = sorted(covered - set(importance_by_aspect))
        if unknown:
            errors.append(f"relationship_covers_unknown_aspects:{item_id}:{'|'.join(unknown)}")
        if item.get("source_item_ids") != [item_id]:
            errors.append(f"source_item_ids_do_not_match_item_id:{item_id}")
        if eligibility == "main_graph" and prominence not in {"paper_defining", "major_supporting"}:
            errors.append(f"main_graph_not_central:{item_id}")
        if prominence in {"paper_defining", "major_supporting"}:
            if eligibility != "main_graph":
                errors.append(f"central_relationship_not_main_graph:{item_id}")
            if not covered:
                errors.append(f"central_relationship_without_major_aspect:{item_id}")
        elif covered:
            errors.append(f"major_aspect_covered_by_noncentral_relationship:{item_id}")
        for aspect_id in sorted(covered):
            importance = importance_by_aspect.get(aspect_id, "")
            if importance == "paper_defining" and prominence != "paper_defining":
                errors.append(f"relationship_aspect_importance_mismatch:{item_id}:{importance}")
            if importance == "major_supporting" and prominence not in {"paper_defining", "major_supporting"}:
                errors.append(f"relationship_aspect_importance_mismatch:{item_id}:{importance}")
        basis = {normalize(value) for value in item.get("centrality_basis", []) if normalize(value)}
        if prominence == "paper_defining" and not basis.intersection(strong_basis):
            errors.append(f"paper_defining_without_paper_level_basis:{item_id}")

    for aspect_id, importance in sorted(importance_by_aspect.items()):
        covering = [
            item
            for item in relationships
            if aspect_id in {normalize(value) for value in item.get("covers_major_aspect_ids", []) if normalize(value)}
            and (
                normalize(item.get("paper_prominence", "")) == "paper_defining"
                or normalize(item.get("paper_prominence", "")) == importance
            )
        ]
        if not covering:
            errors.append(f"major_aspect_without_matching_relationship:{aspect_id}:{importance}")
    if not any(normalize(item.get("paper_prominence", "")) == "paper_defining" for item in relationships):
        errors.append("bundle_without_paper_defining_relationship")
    return errors


def inject_fixed_fields(result: dict, task: dict) -> dict:
    out = dict(result)
    out["schema_version"] = "review_relationship_bundle_v2"
    out["source_depth"] = normalize(task.get("text_depth", ""))
    frame = out.get("paper_frame")
    if isinstance(frame, dict):
        frame["source_completeness"] = out["source_depth"]
    for relationship in out.get("relationships", []) if isinstance(out.get("relationships"), list) else []:
        if isinstance(relationship, dict) and normalize(relationship.get("item_id", "")):
            relationship["source_item_ids"] = [normalize(relationship["item_id"])]
    return out


def append_jsonl(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def call_structured_model(
    *,
    client: object,
    model: str,
    prompt_path: Path,
    schema_path: Path,
    contents: str,
    max_output_tokens: int,
    thinking_budget: int,
) -> tuple[dict, dict, str]:
    schema = load_schema(schema_path)
    prompt = prompt_path.read_text(encoding="utf-8").strip()
    response = client.models.generate_content(
        model=model,
        contents=contents,
        config=build_generation_config(
            system_instruction=prompt,
            schema=schema_for_native(schema),
            schema_mode="native",
            temperature=0.0,
            max_output_tokens=max_output_tokens,
            thinking_budget=thinking_budget,
        ),
    )
    parsed, parse_method = parse_json_response(response.text or "")
    reject_corrupt_output_text(parsed)
    return parsed, usage_dict(response), parse_method


def selected_tasks(tasks: list[dict], args: argparse.Namespace) -> list[dict]:
    selected = [task for task in tasks if normalize(task.get("task_status", "")) == "ready_for_model"]
    if args.doi:
        wanted = {normalize(doi).lower() for doi in args.doi}
        selected = [task for task in selected if normalize(task.get("study_doi", "")).lower() in wanted]
    if args.limit > 0:
        selected = selected[: args.limit]
    return selected


def existing_bundle_dois(path: Path) -> set[str]:
    return {
        normalize(row.get("study_doi", "")).lower()
        for row in read_jsonl(path)
        if normalize(row.get("status", "")) == "ok"
    }


def run(args: argparse.Namespace) -> dict:
    tasks_path = Path(args.tasks_jsonl).resolve()
    run_dir = (Path(args.run_dir) if args.run_dir else DEFAULT_RUN_ROOT / args.run_id).resolve()
    paths = {
        "bundles": run_dir / "paper_relationship_bundles.jsonl",
        "model_log": run_dir / "model_call_log.jsonl",
        "report": run_dir / "run_report.json",
    }
    if args.overwrite:
        for path in paths.values():
            if path.exists():
                path.unlink()

    input_snapshot = archive_run_inputs(run_dir, tasks_path, args)
    archived_inputs = {
        str(Path(item["source_path"]).resolve()): Path(item["archived_path"])
        for item in input_snapshot["artifacts"]
    }
    archived = lambda value: archived_inputs[str(Path(value).resolve())]
    full_text_prompt = archived(args.full_text_prompt)
    abstract_prompt = archived(args.abstract_prompt)
    bundle_schema = archived(args.bundle_schema)

    tasks = read_jsonl(tasks_path)
    selected = selected_tasks(tasks, args)
    completed = existing_bundle_dois(paths["bundles"])
    selected = [task for task in selected if normalize(task.get("study_doi", "")).lower() not in completed]
    packets = packet_lookup(selected)

    report = {
        "schema_version": "review_relationship_run_report_v3",
        "generated_at_utc": now_utc(),
        "status": "dry_run" if args.dry_run else "running",
        "inputs": {
            "tasks_jsonl": str(tasks_path),
            "run_id": args.run_id,
            "model": args.model,
            "input_snapshot_manifest": str(run_dir / "input_snapshot" / "manifest.json"),
            "input_artifact_sha256": {
                Path(item["archived_path"]).name: item["sha256"] for item in input_snapshot["artifacts"]
            },
        },
        "tasks_selected": len(selected),
        "by_text_depth": dict(Counter(task["text_depth"] for task in selected)),
        "estimated_model_calls": len(selected),
        "outputs": {key: str(value) for key, value in paths.items()},
    }
    if args.dry_run:
        write_json(paths["report"], report)
        return report

    from google import genai

    env_values = load_dotenv(Path(args.env_file).resolve())
    client = genai.Client(api_key=api_key_from_env(args, env_values))
    status_counts: Counter = Counter()
    usage_totals: Counter = Counter()
    errors: list[dict] = []
    calls = 0

    for position, task in enumerate(selected, start=1):
        doi = normalize(task.get("study_doi", "")).lower()
        depth = normalize(task.get("text_depth", ""))
        packet = packet_for_task(task, packets)
        prompt_path = full_text_prompt if depth == "article_text" else abstract_prompt
        print(f"[{position}/{len(selected)}] {depth} {doi}", flush=True)
        try:
            bundle, usage, parse_method = call_structured_model(
                client=client,
                model=args.model,
                prompt_path=prompt_path,
                schema_path=bundle_schema,
                contents=model_contents(task, packet),
                max_output_tokens=args.max_output_tokens,
                thinking_budget=args.thinking_budget,
            )
            calls += 1
            for key, value in usage.items():
                if isinstance(value, (int, float)):
                    usage_totals[key] += value
            append_jsonl(
                paths["model_log"],
                {
                    "task_id": task["task_id"],
                    "study_doi": doi,
                    "text_depth": depth,
                    "parse_method": parse_method,
                    "usage": usage,
                },
            )

            bundle = inject_fixed_fields(bundle, task)
            validation_errors = schema_errors(load_schema(bundle_schema), bundle)
            qa_flags = bundle_semantic_errors(bundle) if not validation_errors else []
            status = "schema_error" if validation_errors else "ok"
            append_jsonl(
                paths["bundles"],
                {
                    "task_id": task["task_id"],
                    "study_doi": doi,
                    "study_title": task.get("paper_metadata", {}).get("study_title", ""),
                    "text_depth": depth,
                    "status": status,
                    "result": bundle,
                    "schema_errors": validation_errors,
                    "qa_flags": qa_flags,
                },
            )
            status_counts[status] += 1
        except Exception as exc:  # pragma: no cover - live API failures
            status_counts["error"] += 1
            errors.append({"study_doi": doi, "error": str(exc)})
            append_jsonl(
                paths["bundles"],
                {"task_id": task["task_id"], "study_doi": doi, "text_depth": depth, "status": "error", "error": str(exc)},
            )

    report.update(
        {
            "generated_at_utc": now_utc(),
            "status": "complete",
            "model_calls": calls,
            "by_status": dict(status_counts),
            "usage_totals": dict(usage_totals),
            "errors": errors,
        }
    )
    write_json(paths["report"], report)
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tasks-jsonl", type=Path, default=DEFAULT_TASKS)
    parser.add_argument("--run-id", default="review_relationships_v2")
    parser.add_argument("--run-dir", default="")
    parser.add_argument("--model", default=DEFAULT_GEMINI_MODEL)
    parser.add_argument("--env-file", default=str(DEFAULT_ENV))
    parser.add_argument("--full-text-prompt", type=Path, default=FULL_TEXT_PROMPT)
    parser.add_argument("--abstract-prompt", type=Path, default=ABSTRACT_PROMPT)
    parser.add_argument("--bundle-schema", type=Path, default=BUNDLE_SCHEMA)
    parser.add_argument("--doi", action="append", default=[])
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--max-output-tokens", type=int, default=16384)
    parser.add_argument("--thinking-budget", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = run(args)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
