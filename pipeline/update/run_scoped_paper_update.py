#!/usr/bin/env python3
"""Prepare, finalize, and promote DOI-scoped routed extraction updates.

The update contract is deliberately simple:

* every DOI in the update scope is removed from the previous active outputs
  and evidence rows;
* current, successfully validated extraction outputs for those DOIs are added
  back;
* DOIs that are now excluded or have no runnable task remain absent; and
* rows for DOIs outside the scope are preserved unchanged.

`prepare` never calls a model and never changes the active KG. `finalize`
requires complete successful outputs for every currently runnable scoped task
and writes a versioned candidate run. `promote` rebuilds downstream artifacts
and only then changes the active pointers.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import Iterable, Iterator

import pandas as pd

try:
    from pipeline.kg.convert_routed_extractions_to_evidence_rows import convert_outputs
    from pipeline.extract.build_meta_analysis_v2_tasks import (
        build_tasks as build_meta_analysis_tasks,
        production_cohort as meta_analysis_production_cohort,
    )
    from pipeline.extract.build_review_relationship_tasks import (
        build_tasks as build_review_tasks,
        production_cohort as review_production_cohort,
    )
    from pipeline.kg.convert_meta_analysis_v2_to_evidence_rows import (
        convert_outputs as convert_meta_analysis_outputs,
    )
    from pipeline.kg.convert_review_relationship_bundles_to_evidence_rows import (
        active_review_candidate_dois,
        convert_bundles as convert_review_bundles,
        enrich_canonical_metadata,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from pipeline.kg.convert_routed_extractions_to_evidence_rows import convert_outputs
    from pipeline.extract.build_meta_analysis_v2_tasks import (
        build_tasks as build_meta_analysis_tasks,
        production_cohort as meta_analysis_production_cohort,
    )
    from pipeline.extract.build_review_relationship_tasks import (
        build_tasks as build_review_tasks,
        production_cohort as review_production_cohort,
    )
    from pipeline.kg.convert_meta_analysis_v2_to_evidence_rows import (
        convert_outputs as convert_meta_analysis_outputs,
    )
    from pipeline.kg.convert_review_relationship_bundles_to_evidence_rows import (
        active_review_candidate_dois,
        convert_bundles as convert_review_bundles,
        enrich_canonical_metadata,
    )


ROOT = Path(__file__).resolve().parents[2]
PROCESSED_DIR = ROOT / "data" / "processed"
EXTRACTION_DIR = PROCESSED_DIR / "extraction"
ROUTED_RUNS_DIR = EXTRACTION_DIR / "routed_runs"
UPDATE_ROOT = PROCESSED_DIR / "paper_updates"
ACTIVE_EXTRACTION_POINTER = EXTRACTION_DIR / "active_routed_run.json"
ACTIVE_GRAPH_POINTER = PROCESSED_DIR / "graph_payload_active.json"
DEFAULT_TASKS = EXTRACTION_DIR / "route_extraction_tasks.jsonl"
DEFAULT_ROUTES = PROCESSED_DIR / "corpus" / "paper_extraction_routes.parquet"
DEFAULT_CANDIDATES = PROCESSED_DIR / "corpus" / "candidate_papers.parquet"
DEFAULT_PACKETS = EXTRACTION_DIR / "fulltext_packets.jsonl"
DEFAULT_ENTITY_REGISTRY = ROOT / "data" / "curated" / "entity_registry.json"

DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$", re.IGNORECASE)
RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
READY_STATUS = "ready_for_model"
READY_ROUTE_ACTIONS = {"extract_from_full_text", "extract_from_abstract_only"}
SCHEMA_PROFILE_TO_GROUP = {
    "review_coverage_schema": "reviews",
    "meta_analysis_evidence_schema": "meta_analyses",
}
UPDATE_SCHEMA_VERSION = "scoped_paper_update_v2"


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def normalize(value: object) -> str:
    return " ".join(str(value or "").split())


def normalize_doi(value: object) -> str:
    text = normalize(value).strip(" \t\r\n.,;()[]{}")
    text = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^doi:\s*", "", text, flags=re.IGNORECASE)
    text = text.lower()
    return text if DOI_RE.match(text) else ""


def safe_update_id(value: object) -> str:
    text = normalize(value)
    if not RUN_ID_RE.fullmatch(text):
        raise ValueError(
            "Update ID must start with a letter or number and contain only "
            "letters, numbers, dots, underscores, or hyphens."
        )
    return text


def read_json(path: Path) -> object:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def read_json_object(path: Path) -> dict:
    value = read_json(path)
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def read_json_array(path: Path) -> list[dict]:
    value = read_json(path)
    if not isinstance(value, list):
        raise ValueError(f"Expected a JSON array: {path}")
    return [row for row in value if isinstance(row, dict)]


def read_jsonl(path: Path) -> Iterator[dict]:
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            text = line.strip()
            if not text:
                continue
            try:
                value = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at {path}:{line_number}: {exc}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"Expected a JSON object at {path}:{line_number}")
            yield value


def _atomic_text_writer(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    return tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    )


def write_json_atomic(path: Path, value: object) -> None:
    handle = _atomic_text_writer(path)
    temp_path = Path(handle.name)
    try:
        with handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temp_path, path)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise


def write_jsonl_atomic(path: Path, rows: Iterable[dict]) -> int:
    handle = _atomic_text_writer(path)
    temp_path = Path(handle.name)
    count = 0
    try:
        with handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
                count += 1
        os.replace(temp_path, path)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise
    return count


def write_lines_atomic(path: Path, values: Iterable[str]) -> int:
    items = list(values)
    handle = _atomic_text_writer(path)
    temp_path = Path(handle.name)
    try:
        with handle:
            for value in items:
                handle.write(f"{value}\n")
        os.replace(temp_path, path)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise
    return len(items)


def write_csv_atomic(path: Path, rows: list[dict], fieldnames: list[str]) -> int:
    handle = _atomic_text_writer(path)
    temp_path = Path(handle.name)
    try:
        with handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        os.replace(temp_path, path)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise
    return len(rows)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_snapshot(path: Path) -> dict:
    resolved = path.resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"Required file does not exist: {resolved}")
    return {
        "path": str(resolved),
        "size_bytes": resolved.stat().st_size,
        "sha256": sha256_file(resolved),
    }


def read_doi_file(path: Path) -> set[str]:
    if not path.is_file():
        raise FileNotFoundError(f"DOI file does not exist: {path}")
    dois: set[str] = set()
    invalid: list[str] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.reader(handle):
            if not row:
                continue
            raw = row[0].strip()
            if not raw or raw.startswith("#") or raw.lower() == "doi":
                continue
            doi = normalize_doi(raw)
            if doi:
                dois.add(doi)
            else:
                invalid.append(raw)
    if invalid:
        examples = ", ".join(repr(value) for value in invalid[:5])
        raise ValueError(f"Invalid DOI values in {path}: {examples}")
    if not dois:
        raise ValueError(f"DOI file contains no valid DOI values: {path}")
    return dois


def doi_for_output(row: dict) -> str:
    result = row.get("result") if isinstance(row.get("result"), dict) else {}
    for value in (
        result.get("study_doi"),
        row.get("study_doi"),
        result.get("doi"),
        row.get("doi"),
    ):
        doi = normalize_doi(value)
        if doi:
            return doi
    return ""


def doi_for_evidence(row: dict) -> str:
    return normalize_doi(row.get("study_doi") or row.get("doi"))


def task_contract(row: dict) -> dict:
    value = row.get("extraction_contract")
    return value if isinstance(value, dict) else {}


def task_group(row: dict) -> str:
    schema_version = normalize(row.get("schema_version")).lower()
    key = task_id(row).lower()
    if schema_version == "review_relationship_task_v3" or key.startswith("reviewrel:"):
        return "reviews"
    if schema_version == "meta_analysis_v2_task_v1" or key.startswith("metav2:"):
        return "meta_analyses"
    output_family = normalize(task_contract(row).get("output_family")).lower()
    return {
        "primary_evidence": "primary",
        "recommendation_consensus": "primary",
        "review_coverage": "reviews",
        "meta_analysis_evidence": "meta_analyses",
    }.get(output_family, "other")


def task_id(row: dict) -> str:
    return normalize(row.get("task_id"))


def route_id(row: dict) -> str:
    return normalize(row.get("route_id"))


def fingerprint(row: dict) -> str:
    return normalize(row.get("input_fingerprint"))


def task_text_mode(row: dict) -> str:
    depth = normalize(row.get("text_depth"))
    if depth:
        return depth
    text_source = row.get("text_source") if isinstance(row.get("text_source"), dict) else {}
    mode = normalize(text_source.get("mode"))
    return {
        "abstract": "abstract_only",
        "full_text_packet": "article_text",
        "full_text_artifact": "article_text",
    }.get(mode, mode)


def current_task_index(tasks_path: Path) -> tuple[list[dict], dict[str, dict]]:
    tasks = list(read_jsonl(tasks_path))
    by_id: dict[str, dict] = {}
    for task in tasks:
        key = task_id(task)
        if not key:
            raise ValueError(f"Task without task_id in {tasks_path}")
        if key in by_id:
            raise ValueError(f"Duplicate current task_id {key!r} in {tasks_path}")
        by_id[key] = task
    return tasks, by_id


def active_run_from_graph_pointer(path: Path = ACTIVE_GRAPH_POINTER) -> str:
    pointer = read_json_object(path)
    kg_dir = normalize(pointer.get("kg_dir"))
    if not kg_dir:
        raise ValueError(f"Active graph pointer has no kg_dir: {path}")
    return Path(kg_dir).name


def resolve_active_base(
    *,
    base_outputs: Path | None,
    base_evidence: Path | None,
    active_pointer: Path = ACTIVE_EXTRACTION_POINTER,
) -> tuple[str, Path, Path, str]:
    if base_outputs is not None or base_evidence is not None:
        if base_outputs is None or base_evidence is None:
            raise ValueError("--base-outputs and --base-evidence must be supplied together")
        return "explicit", base_outputs.resolve(), base_evidence.resolve(), "explicit_arguments"

    if active_pointer.is_file():
        pointer = read_json_object(active_pointer)
        run_id = safe_update_id(pointer.get("run_id"))
        outputs = ROOT / normalize(pointer.get("outputs_jsonl"))
        evidence = ROOT / normalize(pointer.get("evidence_rows_json"))
        return run_id, outputs.resolve(), evidence.resolve(), str(active_pointer.resolve())

    run_id = active_run_from_graph_pointer()
    run_dir = ROUTED_RUNS_DIR / run_id
    return (
        run_id,
        (run_dir / "route_extraction_outputs.jsonl").resolve(),
        (run_dir / "routed_evidence_rows.json").resolve(),
        str(ACTIVE_GRAPH_POINTER.resolve()),
    )


def run_checked(command: list[str], *, env: dict[str, str] | None = None) -> None:
    print("+ " + " ".join(command), flush=True)
    subprocess.run(command, cwd=ROOT, env=env, check=True)


def refresh_deterministic_layers(doi_file: Path) -> None:
    """Refresh canonical, route, article-text, and task artifacts without a model."""
    python = sys.executable
    run_checked(
        [
            python,
            str(ROOT / "pipeline" / "review" / "run_deterministic_prescreen.py"),
            "--doi-file",
            str(doi_file.resolve()),
        ]
    )
    # Route-table scoped mode writes only the selected rows. A canonical refresh
    # must therefore rebuild the full (cheap, deterministic) table.
    run_checked(
        [
            python,
            str(ROOT / "pipeline" / "extract" / "build_extraction_routes.py"),
            "--preserve-selection-outside-doi-file",
            str(doi_file.resolve()),
        ]
    )
    run_checked([python, str(ROOT / "pipeline" / "fulltext" / "build_article_text_inputs.py")])
    run_checked([python, str(ROOT / "pipeline" / "extract" / "build_extraction_tasks.py")])


def count_scoped_outputs(path: Path, scope: set[str]) -> tuple[int, int, Counter, Counter]:
    total = 0
    scoped = 0
    scoped_by_status: Counter = Counter()
    scoped_by_doi: Counter = Counter()
    for row in read_jsonl(path):
        total += 1
        doi = doi_for_output(row)
        if doi in scope:
            scoped += 1
            scoped_by_doi[doi] += 1
            scoped_by_status[normalize(row.get("status")) or "missing"] += 1
    return total, scoped, scoped_by_status, scoped_by_doi


def count_scoped_evidence(path: Path, scope: set[str]) -> tuple[int, int, int, Counter]:
    rows = read_json_array(path)
    scoped_rows = [row for row in rows if doi_for_evidence(row) in scope]
    scoped_by_doi = Counter(doi_for_evidence(row) for row in scoped_rows)
    return (
        len(rows),
        len(scoped_rows),
        len({doi for doi in scoped_by_doi if doi}),
        scoped_by_doi,
    )


def route_family_dois(routes_path: Path, scope: set[str]) -> tuple[dict[str, set[str]], set[str]]:
    """Return ready routed DOI ownership for each extraction family."""

    route_frame = pd.read_parquet(routes_path)
    required = {"doi", "route_action", "schema_profile"}
    missing_columns = sorted(required - set(route_frame.columns))
    if missing_columns:
        raise ValueError(
            "Route table is missing columns required for safe family ownership: "
            + ", ".join(missing_columns)
        )
    if route_frame.empty:
        return {"reviews": set(), "meta_analyses": set()}, set()
    route_dois = route_frame["doi"].map(normalize_doi)
    ready = route_frame["route_action"].map(normalize).isin(READY_ROUTE_ACTIONS)
    in_scope = route_dois.isin(scope)
    ready_frame = route_frame.loc[ready & in_scope].copy()
    ready_frame["normalized_doi"] = route_dois[ready & in_scope]
    by_family = {
        group: set(
            ready_frame.loc[
                ready_frame["schema_profile"].map(normalize) == schema_profile,
                "normalized_doi",
            ]
        )
        for schema_profile, group in SCHEMA_PROFILE_TO_GROUP.items()
    }
    return by_family, set(ready_frame["normalized_doi"])


def build_dedicated_tasks(
    *,
    family_dois: dict[str, set[str]],
    candidate_path: Path,
    packets_path: Path,
) -> tuple[dict[str, list[dict]], dict[str, dict]]:
    """Build the dedicated review and meta-analysis tasks for one scoped update."""

    if not any(family_dois.values()):
        return {"reviews": [], "meta_analyses": []}, {"reviews": {}, "meta_analyses": {}}
    if not candidate_path.is_file():
        raise FileNotFoundError(f"Candidate table does not exist: {candidate_path}")
    if not packets_path.is_file():
        raise FileNotFoundError(f"Full-text packet file does not exist: {packets_path}")

    candidate_rows = pd.read_parquet(candidate_path).to_dict("records")
    packet_rows = list(read_jsonl(packets_path))
    review_cohort, review_selection = review_production_cohort(candidate_rows)
    meta_cohort, meta_selection = meta_analysis_production_cohort(candidate_rows)
    cohort_by_family = {
        "reviews": [row for row in review_cohort if normalize_doi(row.get("doi")) in family_dois["reviews"]],
        "meta_analyses": [
            row for row in meta_cohort if normalize_doi(row.get("doi")) in family_dois["meta_analyses"]
        ],
    }
    for group, expected_dois in family_dois.items():
        cohort_dois = {normalize_doi(row.get("doi")) for row in cohort_by_family[group]}
        missing = sorted(expected_dois - cohort_dois)
        if missing:
            raise RuntimeError(
                f"Ready {group} routes are absent from the canonical retained/ready cohort: "
                f"{len(missing)} DOI(s); examples={missing[:10]}"
            )

    review_tasks, review_report = build_review_tasks(
        cohort_by_family["reviews"], candidate_rows, packet_rows, packets_path=packets_path
    )
    meta_tasks, meta_report = build_meta_analysis_tasks(
        cohort_by_family["meta_analyses"], candidate_rows, packet_rows, packets_path=packets_path
    )
    reports = {
        "reviews": {**review_report, "selection": review_selection},
        "meta_analyses": {**meta_report, "selection": meta_selection},
    }
    return {"reviews": review_tasks, "meta_analyses": meta_tasks}, reports


def validate_family_ownership(tasks: list[dict]) -> None:
    owners: dict[str, str] = {}
    conflicts: list[str] = []
    for task in tasks:
        doi = normalize_doi(task.get("study_doi"))
        group = task_group(task)
        previous = owners.get(doi)
        if doi and previous and previous != group:
            conflicts.append(f"{doi} ({previous}, {group})")
        elif doi:
            owners[doi] = group
    if conflicts:
        raise ValueError(
            "A scoped DOI is owned by more than one extraction family: " + ", ".join(conflicts[:10])
        )


def prepare(args: argparse.Namespace) -> int:
    update_id = safe_update_id(args.update_id)
    doi_file = Path(args.doi_file).resolve()
    requested_scope = read_doi_file(doi_file)
    if args.refresh_derived:
        refresh_deterministic_layers(doi_file)

    tasks_path = Path(args.tasks_jsonl).resolve()
    routes_path = Path(args.route_table).resolve()
    candidate_path = Path(getattr(args, "candidate_table", DEFAULT_CANDIDATES)).resolve()
    packets_path = Path(getattr(args, "packets_jsonl", DEFAULT_PACKETS)).resolve()
    entity_registry_path = Path(
        getattr(args, "entity_registry", DEFAULT_ENTITY_REGISTRY)
    ).resolve()
    generic_tasks, _ = current_task_index(tasks_path)
    family_dois, requested_ready_route_dois = route_family_dois(routes_path, requested_scope)
    dedicated_tasks, dedicated_reports = build_dedicated_tasks(
        family_dois=family_dois,
        candidate_path=candidate_path,
        packets_path=packets_path,
    )
    all_tasks = [*generic_tasks, *dedicated_tasks["reviews"], *dedicated_tasks["meta_analyses"]]
    all_task_ids = [task_id(task) for task in all_tasks]
    duplicate_task_ids = sorted(key for key, count in Counter(all_task_ids).items() if key and count > 1)
    if duplicate_task_ids:
        raise ValueError(f"Duplicate current task_id across extraction families: {duplicate_task_ids[:5]}")
    validate_family_ownership(all_tasks)
    scope = set(requested_scope)
    only_task_group = normalize(getattr(args, "only_task_group", "")).lower()
    include_no_runnable = bool(getattr(args, "include_no_runnable", False))
    if only_task_group:
        requested_tasks = [task for task in all_tasks if normalize_doi(task.get("study_doi")) in requested_scope]
        requested_ready = [task for task in requested_tasks if normalize(task.get("task_status")) == READY_STATUS]
        selected_group_dois = {
            normalize_doi(task.get("study_doi"))
            for task in requested_ready
            if task_group(task) == only_task_group
        }
        any_ready_dois = {normalize_doi(task.get("study_doi")) for task in requested_ready}
        scope = set(selected_group_dois)
        if include_no_runnable:
            scope.update(requested_scope - any_ready_dois)
        mixed_group_dois = sorted(
            {
                normalize_doi(task.get("study_doi"))
                for task in requested_ready
                if normalize_doi(task.get("study_doi")) in selected_group_dois
                and task_group(task) != only_task_group
            }
        )
        if mixed_group_dois:
            raise ValueError(
                f"Cannot make a DOI-wide {only_task_group} update because these DOIs also have runnable tasks "
                f"in another group: {', '.join(mixed_group_dois[:10])}"
            )
        if not scope:
            raise ValueError(f"No DOIs remain after applying --only-task-group {only_task_group}")
    scoped_tasks = [task for task in all_tasks if normalize_doi(task.get("study_doi")) in scope]
    ready_tasks = [task for task in scoped_tasks if normalize(task.get("task_status")) == READY_STATUS]
    unsupported_ready_tasks = [task_id(task) for task in ready_tasks if task_group(task) == "other"]
    if unsupported_ready_tasks:
        raise RuntimeError(
            "Ready tasks use an unsupported extraction family: "
            + ", ".join(unsupported_ready_tasks[:10])
        )
    current_task_dois = {normalize_doi(task.get("study_doi")) for task in scoped_tasks}
    ready_dois = {normalize_doi(task.get("study_doi")) for task in ready_tasks}
    expected_ready_route_dois = requested_ready_route_dois & scope
    missing_ready_tasks = sorted(expected_ready_route_dois - ready_dois)
    if missing_ready_tasks:
        raise RuntimeError(
            "A ready extraction route has no current ready task. The update cannot classify these papers "
            "as deletion-only: "
            f"{len(missing_ready_tasks)} DOI(s); examples={missing_ready_tasks[:10]}"
        )

    base_run_id, base_outputs, base_evidence, base_pointer = resolve_active_base(
        base_outputs=Path(args.base_outputs) if args.base_outputs else None,
        base_evidence=Path(args.base_evidence) if args.base_evidence else None,
    )
    base_output_snapshot = file_snapshot(base_outputs)
    base_evidence_snapshot = file_snapshot(base_evidence)
    tasks_snapshot = file_snapshot(tasks_path)
    routes_snapshot = file_snapshot(routes_path)
    has_dedicated_ready_tasks = any(
        task_group(task) in {"reviews", "meta_analyses"} for task in ready_tasks
    )
    has_review_ready_tasks = any(task_group(task) == "reviews" for task in ready_tasks)
    candidate_snapshot = file_snapshot(candidate_path) if has_dedicated_ready_tasks else None
    packets_snapshot = file_snapshot(packets_path) if has_dedicated_ready_tasks else None
    entity_registry_snapshot = (
        file_snapshot(entity_registry_path) if has_review_ready_tasks else None
    )

    old_output_count, old_scope_output_count, scope_output_status, old_outputs_by_doi = count_scoped_outputs(
        base_outputs,
        scope,
    )
    old_evidence_count, old_scope_evidence_count, old_scope_evidence_dois, old_evidence_by_doi = (
        count_scoped_evidence(base_evidence, scope)
    )

    update_dir = (Path(args.update_dir).resolve() if args.update_dir else UPDATE_ROOT / update_id)
    if update_dir.exists() and any(update_dir.iterdir()):
        if not args.overwrite:
            raise FileExistsError(
                f"Update directory is not empty: {update_dir}. Use --overwrite to replace its prepared files."
            )
        shutil.rmtree(update_dir)
    update_dir.mkdir(parents=True, exist_ok=True)

    scope_path = update_dir / "scope_dois.txt"
    all_tasks_path = update_dir / "scoped_tasks.jsonl"
    ready_tasks_path = update_dir / "ready_tasks.jsonl"
    write_lines_atomic(scope_path, sorted(scope))
    write_jsonl_atomic(all_tasks_path, scoped_tasks)
    write_jsonl_atomic(ready_tasks_path, ready_tasks)

    task_files: dict[str, dict] = {}
    for group in ("primary", "reviews", "meta_analyses", "other"):
        group_rows = [task for task in ready_tasks if task_group(task) == group]
        group_path = update_dir / f"ready_tasks_{group}.jsonl"
        write_jsonl_atomic(group_path, group_rows)
        task_files[group] = {
            "path": str(group_path.resolve()),
            "tasks": len(group_rows),
            "snapshot": file_snapshot(group_path),
        }

    no_current_task = sorted(scope - current_task_dois)
    no_runnable_task = sorted(scope - ready_dois)
    write_lines_atomic(update_dir / "no_current_task_dois.txt", no_current_task)
    write_lines_atomic(update_dir / "no_runnable_task_dois.txt", no_runnable_task)

    tasks_by_doi: dict[str, list[dict]] = {}
    for task in scoped_tasks:
        tasks_by_doi.setdefault(normalize_doi(task.get("study_doi")), []).append(task)
    status_rows: list[dict] = []
    for doi in sorted(scope):
        doi_tasks = tasks_by_doi.get(doi, [])
        doi_ready = [task for task in doi_tasks if normalize(task.get("task_status")) == READY_STATUS]
        status_rows.append(
            {
                "doi": doi,
                "disposition": "replace_with_current_extraction" if doi_ready else "remove_without_replacement",
                "current_task_count": len(doi_tasks),
                "ready_task_count": len(doi_ready),
                "task_statuses": " | ".join(sorted({normalize(task.get("task_status")) for task in doi_tasks})),
                "task_groups": " | ".join(sorted({task_group(task) for task in doi_ready})),
                "text_modes": " | ".join(
                    sorted(
                        {
                            task_text_mode(task)
                            for task in doi_ready
                            if task_text_mode(task)
                        }
                    )
                ),
                "previous_output_rows_to_remove": old_outputs_by_doi.get(doi, 0),
                "previous_evidence_rows_to_remove": old_evidence_by_doi.get(doi, 0),
            }
        )
    scope_status_path = update_dir / "scope_status.csv"
    write_csv_atomic(
        scope_status_path,
        status_rows,
        [
            "doi",
            "disposition",
            "current_task_count",
            "ready_task_count",
            "task_statuses",
            "task_groups",
            "text_modes",
            "previous_output_rows_to_remove",
            "previous_evidence_rows_to_remove",
        ],
    )

    duplicate_routes = [
        key
        for key, count in Counter(route_id(task) for task in ready_tasks).items()
        if key and count > 1
    ]
    if duplicate_routes:
        raise ValueError(f"Current scoped tasks contain duplicate route IDs: {duplicate_routes[:5]}")

    manifest = {
        "schema_version": UPDATE_SCHEMA_VERSION,
        "phase": "prepared",
        "generated_at_utc": now_utc(),
        "update_id": update_id,
        "update_dir": str(update_dir.resolve()),
        "scope": {
            "source_doi_file": str(doi_file),
            "scope_dois_file": str(scope_path.resolve()),
            "doi_count": len(scope),
            "requested_doi_count": len(requested_scope),
            "only_task_group": only_task_group,
            "include_no_runnable": include_no_runnable,
            "doi_sha256": hashlib.sha256("\n".join(sorted(scope)).encode("utf-8")).hexdigest(),
        },
        "base": {
            "run_id": base_run_id,
            "resolved_from": base_pointer,
            "outputs": base_output_snapshot,
            "evidence": base_evidence_snapshot,
            "output_rows": old_output_count,
            "scope_output_rows_to_replace": old_scope_output_count,
            "scope_output_rows_by_status": dict(scope_output_status),
            "evidence_rows": old_evidence_count,
            "scope_evidence_rows_to_replace": old_scope_evidence_count,
            "scope_dois_with_evidence_to_replace": old_scope_evidence_dois,
        },
        "current_inputs": {
            "tasks": tasks_snapshot,
            "routes": routes_snapshot,
            "candidate_table": candidate_snapshot,
            "packets": packets_snapshot,
            "entity_registry": entity_registry_snapshot,
        },
        "current_scope": {
            "tasks": len(scoped_tasks),
            "ready_tasks": len(ready_tasks),
            "current_task_dois": len(current_task_dois),
            "ready_dois": len(ready_dois),
            "no_current_task_dois": len(no_current_task),
            "no_runnable_task_dois": len(no_runnable_task),
            "by_task_status": dict(Counter(normalize(task.get("task_status")) for task in scoped_tasks)),
            "by_group": dict(Counter(task_group(task) for task in ready_tasks)),
            "by_text_mode": dict(
                Counter(
                    task_text_mode(task)
                    for task in ready_tasks
                    if task_text_mode(task)
                )
            ),
            "ready_route_dois": len(expected_ready_route_dois),
            "dedicated_task_builds": dedicated_reports,
        },
        "task_files": task_files,
        "files": {
            "scoped_tasks": str(all_tasks_path.resolve()),
            "ready_tasks": str(ready_tasks_path.resolve()),
            "no_current_task_dois": str((update_dir / "no_current_task_dois.txt").resolve()),
            "no_runnable_task_dois": str((update_dir / "no_runnable_task_dois.txt").resolve()),
            "scope_status_csv": str(scope_status_path.resolve()),
        },
        "replacement_contract": {
            "remove_all_previous_outputs_and_evidence_for_every_scope_doi": True,
            "require_one_current_successful_output_per_ready_task": True,
            "add_no_replacement_for_dois_without_runnable_tasks": True,
            "preserve_every_out_of_scope_row": True,
        },
    }
    write_json_atomic(update_dir / "update_manifest.json", manifest)
    print(f"Prepared scoped update: {update_id}")
    print(f"Scope DOIs: {len(scope)}")
    print(f"Current ready tasks: {len(ready_tasks)} across {len(ready_dois)} DOIs")
    print(f"Previous output rows to replace: {old_scope_output_count}")
    print(f"Previous evidence rows to replace: {old_scope_evidence_count}")
    print(f"Update directory: {update_dir}")
    return 0


def verify_snapshot(snapshot: dict, label: str) -> Path:
    path = Path(snapshot["path"])
    current = file_snapshot(path)
    if current["sha256"] != snapshot.get("sha256") or current["size_bytes"] != snapshot.get("size_bytes"):
        raise RuntimeError(
            f"{label} changed after prepare: {path}. Rerun prepare before finalizing."
        )
    return path


def output_matches_task(row: dict, task: dict) -> tuple[bool, str]:
    result = row.get("result") if isinstance(row.get("result"), dict) else {}
    actual_task_ids = {normalize(row.get("task_id")), normalize(result.get("task_id"))} - {""}
    if actual_task_ids != {task_id(task)}:
        return False, "task_id_mismatch"
    actual_routes = {normalize(row.get("route_id")), normalize(result.get("route_id"))} - {""}
    if actual_routes != {route_id(task)}:
        return False, "route_id_mismatch"
    actual_fingerprints = {
        normalize(row.get("input_fingerprint")),
        normalize(result.get("input_fingerprint")),
    } - {""}
    expected_fingerprint = fingerprint(task)
    if expected_fingerprint and actual_fingerprints != {expected_fingerprint}:
        return False, "input_fingerprint_mismatch"
    if doi_for_output(row) != normalize_doi(task.get("study_doi")):
        return False, "study_doi_mismatch"
    result_domain = normalize(result.get("domain_route"))
    expected_domain = normalize(task_contract(task).get("domain_route"))
    if expected_domain and result_domain != expected_domain:
        return False, "domain_route_mismatch"
    text_source = task.get("text_source") if isinstance(task.get("text_source"), dict) else {}
    expected_depth = {
        "abstract": "abstract_only",
        "full_text_packet": "article_text",
        "full_text_artifact": "article_text",
    }.get(normalize(text_source.get("mode")), "")
    if expected_depth and normalize(result.get("text_depth")) != expected_depth:
        return False, "text_depth_mismatch"
    return True, ""


def selected_patch_outputs(paths: list[Path], ready_by_id: dict[str, dict]) -> tuple[list[dict], dict]:
    selected: dict[str, dict] = {}
    seen_rows = 0
    skipped_status: Counter = Counter()
    invalid: Counter = Counter()
    unexpected: list[str] = []
    superseded = 0
    for path in paths:
        if not path.is_file():
            raise FileNotFoundError(f"Patch output file does not exist: {path}")
        for row in read_jsonl(path):
            seen_rows += 1
            status = normalize(row.get("status"))
            if status != "ok":
                skipped_status[status or "missing"] += 1
                continue
            result = row.get("result") if isinstance(row.get("result"), dict) else {}
            key = normalize(row.get("task_id")) or normalize(result.get("task_id"))
            task = ready_by_id.get(key)
            if task is None:
                unexpected.append(key or "<missing>")
                continue
            matches, reason = output_matches_task(row, task)
            if not matches:
                invalid[reason] += 1
                continue
            if key in selected:
                superseded += 1
            selected[key] = row

    if unexpected:
        raise ValueError(
            "Patch contains successful outputs that are not current ready tasks in this update: "
            + ", ".join(unexpected[:10])
        )
    if invalid:
        raise ValueError(f"Patch contains outputs that do not match current tasks: {dict(invalid)}")
    missing = sorted(set(ready_by_id) - set(selected))
    if missing:
        raise RuntimeError(
            f"Patch is incomplete: {len(missing)} current ready tasks have no successful output. "
            f"Examples: {', '.join(missing[:10])}"
        )
    ordered = [selected[key] for key in sorted(selected)]
    return ordered, {
        "rows_read": seen_rows,
        "successful_current_outputs": len(ordered),
        "skipped_non_ok_status": dict(skipped_status),
        "superseded_successful_retries": superseded,
    }


def dedicated_output_matches_task(row: dict, task: dict, group: str) -> tuple[bool, str]:
    result = row.get("result") if isinstance(row.get("result"), dict) else {}
    if not result:
        return False, "missing_result"
    actual_task_ids = {normalize(row.get("task_id")), normalize(result.get("task_id"))} - {""}
    if actual_task_ids != {task_id(task)}:
        return False, "task_id_mismatch"
    if doi_for_output(row) != normalize_doi(task.get("study_doi")):
        return False, "study_doi_mismatch"
    expected_depth = normalize(task.get("text_depth"))
    actual_depths = {
        normalize(row.get("text_depth")),
        normalize(row.get("source_depth")),
        normalize(result.get("source_depth")),
        normalize(result.get("text_depth")),
    } - {""}
    if expected_depth and actual_depths != {expected_depth}:
        return False, "source_depth_mismatch"
    schema_errors = row.get("schema_errors")
    if not isinstance(schema_errors, list):
        return False, "schema_validation_missing"
    if schema_errors:
        return False, "schema_errors_present"
    if group == "reviews":
        if normalize(result.get("schema_version")) != "review_relationship_bundle_v2":
            return False, "review_schema_version_mismatch"
        if not isinstance(result.get("paper_frame"), dict) or not isinstance(
            result.get("relationships"), list
        ):
            return False, "review_result_structure_mismatch"
    elif group == "meta_analyses":
        if normalize(row.get("schema_version")) != "meta_analysis_evidence_v2":
            return False, "meta_schema_version_mismatch"
        if not normalize(result.get("extraction_status")) or not isinstance(
            result.get("synthesis_results"), list
        ):
            return False, "meta_result_structure_mismatch"
        source = task.get("source") if isinstance(task.get("source"), dict) else {}
        expected_fingerprint = normalize(source.get("source_fingerprint"))
        if expected_fingerprint and normalize(row.get("source_fingerprint")) != expected_fingerprint:
            return False, "source_fingerprint_mismatch"
    else:  # pragma: no cover - internal misuse guard
        return False, "unsupported_task_group"
    return True, ""


def selected_family_outputs(
    paths: list[Path], ready_by_id: dict[str, dict], group: str
) -> tuple[list[dict], dict]:
    selected: dict[str, dict] = {}
    seen_rows = 0
    skipped_status: Counter = Counter()
    invalid: Counter = Counter()
    unexpected: list[str] = []
    superseded = 0
    for path in paths:
        if not path.is_file():
            raise FileNotFoundError(f"{group} output file does not exist: {path}")
        for row in read_jsonl(path):
            seen_rows += 1
            status = normalize(row.get("status"))
            if status != "ok":
                skipped_status[status or "missing"] += 1
                continue
            result = row.get("result") if isinstance(row.get("result"), dict) else {}
            key = normalize(row.get("task_id")) or normalize(result.get("task_id"))
            task = ready_by_id.get(key)
            if task is None:
                unexpected.append(key or "<missing>")
                continue
            matches, reason = dedicated_output_matches_task(row, task, group)
            if not matches:
                invalid[reason] += 1
                continue
            if key in selected:
                superseded += 1
            selected[key] = row
    if unexpected:
        raise ValueError(
            f"{group} outputs contain successful records that are not current tasks: "
            + ", ".join(unexpected[:10])
        )
    if invalid:
        raise ValueError(f"{group} outputs do not match current tasks: {dict(invalid)}")
    missing = sorted(set(ready_by_id) - set(selected))
    if missing:
        raise RuntimeError(
            f"{group} output is incomplete: {len(missing)} current tasks have no successful output. "
            f"Examples: {', '.join(missing[:10])}"
        )
    ordered = [selected[key] for key in sorted(selected)]
    return ordered, {
        "rows_read": seen_rows,
        "successful_current_outputs": len(ordered),
        "skipped_non_ok_status": dict(skipped_status),
        "superseded_successful_retries": superseded,
    }


def task_index_from_rows(rows: list[dict]) -> dict[str, dict]:
    indexed: dict[str, dict] = {}
    for row in rows:
        key = task_id(row)
        if not key or key in indexed:
            raise ValueError(f"Missing or duplicate prepared task ID: {key!r}")
        indexed[key] = row
    return indexed


def iter_merged_outputs(base_path: Path, scope: set[str], patch_rows: list[dict]) -> Iterator[dict]:
    for row in read_jsonl(base_path):
        if doi_for_output(row) not in scope:
            yield row
    yield from patch_rows


def verify_out_of_scope_output_preservation(
    base_path: Path,
    candidate_path: Path,
    scope: set[str],
) -> tuple[int, int, str, str]:
    def digest_rows(path: Path) -> tuple[int, str]:
        count = 0
        digest = hashlib.sha256()
        for row in read_jsonl(path):
            if doi_for_output(row) in scope:
                continue
            digest.update(json.dumps(row, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
            digest.update(b"\n")
            count += 1
        return count, digest.hexdigest()

    base_count, base_digest = digest_rows(base_path)
    candidate_count, candidate_digest = digest_rows(candidate_path)
    if (base_count, base_digest) != (candidate_count, candidate_digest):
        raise RuntimeError("Out-of-scope raw extraction outputs were not preserved exactly")
    return base_count, candidate_count, base_digest, candidate_digest


def finalize(args: argparse.Namespace) -> int:
    update_id = safe_update_id(args.update_id)
    update_dir = Path(args.update_dir).resolve() if args.update_dir else UPDATE_ROOT / update_id
    manifest_path = update_dir / "update_manifest.json"
    manifest = read_json_object(manifest_path)
    if manifest.get("schema_version") != UPDATE_SCHEMA_VERSION:
        raise ValueError(
            f"Update manifest predates mixed-family orchestration; rerun prepare: {manifest_path}"
        )
    if manifest.get("phase") != "prepared" or manifest.get("update_id") != update_id:
        raise ValueError(f"Not a prepared manifest for update {update_id}: {manifest_path}")

    scope = read_doi_file(Path(manifest["scope"]["scope_dois_file"]))
    base_outputs = verify_snapshot(manifest["base"]["outputs"], "Base outputs")
    base_evidence = verify_snapshot(manifest["base"]["evidence"], "Base evidence")
    verify_snapshot(manifest["current_inputs"]["tasks"], "Current task manifest")
    verify_snapshot(manifest["current_inputs"]["routes"], "Current route table")
    family_tasks: dict[str, list[dict]] = {}
    for group in ("primary", "reviews", "meta_analyses"):
        task_file = manifest["task_files"][group]
        verify_snapshot(task_file["snapshot"], f"Prepared {group} tasks")
        family_tasks[group] = list(read_jsonl(Path(task_file["path"])))
    ready_tasks = [
        *family_tasks["primary"],
        *family_tasks["reviews"],
        *family_tasks["meta_analyses"],
    ]
    validate_family_ownership(ready_tasks)

    output_args = {
        "primary": getattr(args, "patch_outputs", []),
        "reviews": getattr(args, "review_outputs", []),
        "meta_analyses": getattr(args, "meta_analysis_outputs", []),
    }
    family_outputs: dict[str, list[dict]] = {}
    family_output_reports: dict[str, dict] = {}
    for group in ("primary", "reviews", "meta_analyses"):
        tasks = family_tasks[group]
        paths = [Path(path).resolve() for path in output_args[group]]
        if tasks and not paths:
            flag = {
                "primary": "--patch-outputs",
                "reviews": "--review-outputs",
                "meta_analyses": "--meta-analysis-outputs",
            }[group]
            raise RuntimeError(
                f"This update has {len(tasks)} ready {group} tasks; supply their outputs with {flag}."
            )
        indexed = task_index_from_rows(tasks)
        if group == "primary":
            rows, report = selected_patch_outputs(paths, indexed)
        else:
            rows, report = selected_family_outputs(paths, indexed, group)
        family_outputs[group] = rows
        family_output_reports[group] = report

    candidate_snapshot = manifest["current_inputs"].get("candidate_table")
    packets_snapshot = manifest["current_inputs"].get("packets")
    registry_snapshot = manifest["current_inputs"].get("entity_registry")
    candidate_path = verify_snapshot(candidate_snapshot, "Candidate table") if candidate_snapshot else None
    if packets_snapshot:
        verify_snapshot(packets_snapshot, "Full-text packets")
    entity_registry_path = (
        verify_snapshot(registry_snapshot, "Entity registry") if registry_snapshot else None
    )

    candidate_run_dir = ROUTED_RUNS_DIR / update_id
    if candidate_run_dir.exists() and any(candidate_run_dir.iterdir()):
        if not args.overwrite:
            raise FileExistsError(
                f"Candidate run directory is not empty: {candidate_run_dir}. Use --overwrite to regenerate it."
            )
        shutil.rmtree(candidate_run_dir)
    candidate_run_dir.mkdir(parents=True, exist_ok=True)
    candidate_outputs = candidate_run_dir / "route_extraction_outputs.jsonl"
    all_output_rows = [
        *family_outputs["primary"],
        *family_outputs["reviews"],
        *family_outputs["meta_analyses"],
    ]
    combined_output_count = write_jsonl_atomic(
        candidate_outputs,
        iter_merged_outputs(base_outputs, scope, all_output_rows),
    )

    family_artifacts: dict[str, dict] = {}
    family_evidence: dict[str, list[dict]] = {}
    conversion_reports: dict[str, dict] = {}
    artifact_names = {
        "primary": ("scoped_route_extraction_tasks.jsonl", "scoped_route_extraction_outputs.jsonl"),
        "reviews": ("scoped_review_relationship_tasks.jsonl", "scoped_review_relationship_outputs.jsonl"),
        "meta_analyses": ("scoped_meta_analysis_v2_tasks.jsonl", "scoped_meta_analysis_v2_outputs.jsonl"),
    }
    for group, (task_name, output_name) in artifact_names.items():
        task_path = candidate_run_dir / task_name
        output_path = candidate_run_dir / output_name
        write_jsonl_atomic(task_path, family_tasks[group])
        write_jsonl_atomic(output_path, family_outputs[group])
        family_artifacts[group] = {
            "tasks": file_snapshot(task_path),
            "outputs": file_snapshot(output_path),
        }

    primary_evidence, primary_report = convert_outputs(
        input_jsonl=Path(family_artifacts["primary"]["outputs"]["path"]),
        tasks_jsonl=Path(family_artifacts["primary"]["tasks"]["path"]),
        active_route_table=Path(manifest["current_inputs"]["routes"]["path"]),
    )
    family_evidence["primary"] = primary_evidence
    conversion_reports["primary"] = primary_report

    if family_tasks["reviews"]:
        assert candidate_path is not None and entity_registry_path is not None
        candidate_rows = pd.read_parquet(candidate_path).to_dict("records")
        review_evidence, review_report = convert_review_bundles(
            family_outputs["reviews"],
            family_tasks["reviews"],
            read_json_object(entity_registry_path),
            active_candidate_dois=active_review_candidate_dois(candidate_rows),
        )
        review_report["canonical_metadata_papers_enriched"] = enrich_canonical_metadata(
            review_evidence, candidate_rows
        )
        if review_report.get("skipped"):
            raise RuntimeError(
                "Validated review outputs were skipped during evidence conversion: "
                f"{review_report['skipped']}"
            )
    else:
        review_evidence, review_report = [], {"counts": {"bundle_rows": 0, "relationship_rows": 0}}
    family_evidence["reviews"] = review_evidence
    conversion_reports["reviews"] = review_report

    meta_evidence, meta_report = convert_meta_analysis_outputs(
        family_outputs["meta_analyses"],
        task_index_from_rows(family_tasks["meta_analyses"]),
    )
    if meta_report.get("counts", {}).get("missing_task"):
        raise RuntimeError("Validated meta-analysis outputs lost their prepared task during conversion")
    family_evidence["meta_analyses"] = meta_evidence
    conversion_reports["meta_analyses"] = meta_report

    patch_evidence = [
        *family_evidence["primary"],
        *family_evidence["reviews"],
        *family_evidence["meta_analyses"],
    ]
    for group in ("primary", "reviews", "meta_analyses"):
        evidence_path = candidate_run_dir / f"scoped_{group}_evidence_rows.json"
        report_path = candidate_run_dir / f"scoped_{group}_evidence_rows_report.json"
        write_json_atomic(evidence_path, family_evidence[group])
        write_json_atomic(report_path, conversion_reports[group])
        family_artifacts[group]["evidence"] = file_snapshot(evidence_path)
        family_artifacts[group]["conversion_report"] = file_snapshot(report_path)

    base_evidence_rows = read_json_array(base_evidence)
    unaffected_evidence = [row for row in base_evidence_rows if doi_for_evidence(row) not in scope]
    candidate_evidence_rows = [*unaffected_evidence, *patch_evidence]
    candidate_evidence = candidate_run_dir / "routed_evidence_rows.json"
    write_json_atomic(candidate_evidence, candidate_evidence_rows)

    out_scope = [row for row in candidate_evidence_rows if doi_for_evidence(row) in scope]
    unexpected_evidence_dois = sorted(
        {doi_for_evidence(row) for row in out_scope}
        - {normalize_doi(task.get("study_doi")) for task in ready_tasks}
    )
    if unexpected_evidence_dois:
        raise RuntimeError(
            "Candidate evidence contains scoped DOI rows without a current ready task: "
            + ", ".join(unexpected_evidence_dois[:10])
        )

    base_unaffected_count, candidate_unaffected_count, base_digest, candidate_digest = (
        verify_out_of_scope_output_preservation(base_outputs, candidate_outputs, scope)
    )
    candidate_output_scope = Counter(doi_for_output(row) for row in read_jsonl(candidate_outputs))
    stale_scope_dois = sorted(
        doi
        for doi in scope
        if candidate_output_scope.get(doi, 0)
        and doi not in {normalize_doi(task.get("study_doi")) for task in ready_tasks}
    )
    if stale_scope_dois:
        raise RuntimeError(
            "Candidate outputs retained stale rows for non-runnable scoped DOIs: "
            + ", ".join(stale_scope_dois[:10])
        )

    family_report = {
        group: {
            "ready_tasks": len(family_tasks[group]),
            "ready_dois": len({normalize_doi(row.get("study_doi")) for row in family_tasks[group]}),
            "validated_outputs": len(family_outputs[group]),
            "evidence_rows": len(family_evidence[group]),
            "output_validation": family_output_reports[group],
            "evidence_conversion": conversion_reports[group],
            "artifacts": family_artifacts[group],
        }
        for group in ("primary", "reviews", "meta_analyses")
    }
    final_report = {
        "schema_version": UPDATE_SCHEMA_VERSION,
        "phase": "finalized_candidate",
        "generated_at_utc": now_utc(),
        "update_id": update_id,
        "scope_dois": len(scope),
        "ready_tasks_required": len(ready_tasks),
        "families": family_report,
        "raw_outputs": {
            "base_rows": manifest["base"]["output_rows"],
            "base_scope_rows_removed": manifest["base"]["scope_output_rows_to_replace"],
            "patch_rows_added": len(all_output_rows),
            "candidate_rows": combined_output_count,
            "out_of_scope_rows_base": base_unaffected_count,
            "out_of_scope_rows_candidate": candidate_unaffected_count,
            "out_of_scope_digest_base": base_digest,
            "out_of_scope_digest_candidate": candidate_digest,
        },
        "evidence": {
            "base_rows": len(base_evidence_rows),
            "base_scope_rows_removed": len(base_evidence_rows) - len(unaffected_evidence),
            "patch_rows_added": len(patch_evidence),
            "candidate_rows": len(candidate_evidence_rows),
            "patch_conversion": conversion_reports,
        },
        "candidate_run": {
            "run_dir": str(candidate_run_dir.resolve()),
            "outputs": file_snapshot(candidate_outputs),
            "evidence": file_snapshot(candidate_evidence),
            "scoped_tasks": family_artifacts["primary"]["tasks"],
            "scoped_outputs": family_artifacts["primary"]["outputs"],
            "family_artifacts": family_artifacts,
        },
        "safety_checks": {
            "complete_successful_output_for_every_ready_task": True,
            "no_stale_output_for_non_runnable_scope_doi": True,
            "no_unexpected_scope_evidence_doi": True,
            "out_of_scope_outputs_preserved": True,
        },
    }
    report_path = update_dir / "finalize_report.json"
    write_json_atomic(report_path, final_report)
    manifest["phase"] = "finalized_candidate"
    manifest["finalized_at_utc"] = final_report["generated_at_utc"]
    manifest["finalize_report"] = str(report_path.resolve())
    manifest["candidate_run"] = final_report["candidate_run"]
    write_json_atomic(manifest_path, manifest)

    print(f"Finalized candidate run: {update_id}")
    print(f"Successful current outputs added: {len(all_output_rows)}")
    print(
        "Families: "
        + ", ".join(
            f"{group}={len(family_outputs[group])}"
            for group in ("primary", "reviews", "meta_analyses")
        )
    )
    print(f"Candidate evidence rows: {len(candidate_evidence_rows)}")
    print("The active KG has not changed. Run the promote subcommand after reviewing this report.")
    return 0


def promote(args: argparse.Namespace) -> int:
    update_id = safe_update_id(args.update_id)
    update_dir = Path(args.update_dir).resolve() if args.update_dir else UPDATE_ROOT / update_id
    manifest_path = update_dir / "update_manifest.json"
    manifest = read_json_object(manifest_path)
    if manifest.get("schema_version") != UPDATE_SCHEMA_VERSION:
        raise ValueError(
            f"Update manifest predates mixed-family orchestration; rerun prepare: {manifest_path}"
        )
    if manifest.get("phase") != "finalized_candidate" or manifest.get("update_id") != update_id:
        raise ValueError(f"Update must be finalized before promotion: {manifest_path}")
    report = read_json_object(Path(manifest["finalize_report"]))
    candidate = report["candidate_run"]
    verify_snapshot(candidate["outputs"], "Candidate outputs")
    verify_snapshot(candidate["evidence"], "Candidate evidence")

    env = dict(os.environ)
    env["ACTIVATE_DEFAULT"] = "0"
    base_run_id = normalize(manifest.get("base", {}).get("run_id", ""))
    base_author_cache = PROCESSED_DIR / "kg_routed_runs" / base_run_id / "openalex_author_cache.json"
    base_kg_dir = PROCESSED_DIR / "kg_routed_runs" / base_run_id
    if base_run_id and base_author_cache.is_file():
        env["AUTHOR_CACHE_SEED"] = str(base_author_cache.resolve())
    if base_run_id and base_kg_dir.is_dir():
        env["REVIEW_BASELINE_DIR"] = str(base_kg_dir.resolve())
    author_args = ["--offline"] if args.offline else []
    run_checked(
        [str(ROOT / "scripts" / "build_routed_kg_payload.sh"), update_id, *author_args],
        env=env,
    )

    run_checked(
        [
            sys.executable,
            str(ROOT / "pipeline" / "publish" / "promote_routed_run.py"),
            "--run-id",
            update_id,
            "--outputs-jsonl",
            str(Path(candidate["outputs"]["path"]).resolve()),
            "--evidence-rows-json",
            str(Path(candidate["evidence"]["path"]).resolve()),
            "--source-update-manifest",
            str(manifest_path.resolve()),
        ]
    )
    active_pointer = read_json_object(ACTIVE_EXTRACTION_POINTER)
    manifest["phase"] = "promoted"
    manifest["promoted_at_utc"] = active_pointer["updated_at_utc"]
    manifest["active_pointer"] = str(ACTIVE_EXTRACTION_POINTER.resolve())
    write_json_atomic(manifest_path, manifest)
    print(f"Promoted scoped update: {update_id}")
    print(f"Active extraction pointer: {ACTIVE_EXTRACTION_POINTER}")
    print(f"Active graph pointer: {ACTIVE_GRAPH_POINTER}")
    print(f"Public site bundle refreshed: {ROOT / 'dist'}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare_parser = subparsers.add_parser(
        "prepare",
        help="Refresh deterministic layers if requested and create scoped model task files.",
    )
    prepare_parser.add_argument("--update-id", required=True)
    prepare_parser.add_argument("--doi-file", required=True)
    prepare_parser.add_argument("--update-dir", default="")
    prepare_parser.add_argument("--tasks-jsonl", default=str(DEFAULT_TASKS))
    prepare_parser.add_argument("--route-table", default=str(DEFAULT_ROUTES))
    prepare_parser.add_argument("--candidate-table", default=str(DEFAULT_CANDIDATES))
    prepare_parser.add_argument("--packets-jsonl", default=str(DEFAULT_PACKETS))
    prepare_parser.add_argument("--entity-registry", default=str(DEFAULT_ENTITY_REGISTRY))
    prepare_parser.add_argument("--base-outputs", default="")
    prepare_parser.add_argument("--base-evidence", default="")
    prepare_parser.add_argument(
        "--refresh-derived",
        action="store_true",
        help="Run scoped prescreen plus full deterministic route/article-text/task refresh first.",
    )
    prepare_parser.add_argument(
        "--only-task-group",
        choices=("primary", "reviews", "meta_analyses"),
        default="",
        help="Limit the effective DOI scope to papers with ready tasks in one extraction family.",
    )
    prepare_parser.add_argument(
        "--include-no-runnable",
        action="store_true",
        help="With --only-task-group, also include requested DOIs that have no runnable task in any family.",
    )
    prepare_parser.add_argument("--overwrite", action="store_true")
    prepare_parser.set_defaults(func=prepare)

    finalize_parser = subparsers.add_parser(
        "finalize",
        help="Validate complete scoped extraction outputs and build a versioned replacement candidate.",
    )
    finalize_parser.add_argument("--update-id", required=True)
    finalize_parser.add_argument("--update-dir", default="")
    finalize_parser.add_argument(
        "--patch-outputs",
        action="append",
        default=[],
        help="Primary/consensus routed extraction JSONL; repeat for retries or multiple batches.",
    )
    finalize_parser.add_argument(
        "--review-outputs",
        action="append",
        default=[],
        help="Review relationship bundle JSONL; repeat for retries or multiple batches.",
    )
    finalize_parser.add_argument(
        "--meta-analysis-outputs",
        action="append",
        default=[],
        help="Meta-analysis v2 extraction JSONL; repeat for retries or multiple batches.",
    )
    finalize_parser.add_argument("--overwrite", action="store_true")
    finalize_parser.set_defaults(func=finalize)

    promote_parser = subparsers.add_parser(
        "promote",
        help="Build KG/payload/methods/site outputs and make the finalized candidate active.",
    )
    promote_parser.add_argument("--update-id", required=True)
    promote_parser.add_argument("--update-dir", default="")
    promote_parser.add_argument(
        "--offline",
        action="store_true",
        help="Do not query OpenAlex while rebuilding author tables.",
    )
    promote_parser.set_defaults(func=promote)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
