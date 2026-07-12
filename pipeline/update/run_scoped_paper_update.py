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

try:
    from pipeline.kg.convert_routed_extractions_to_evidence_rows import convert_outputs
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from pipeline.kg.convert_routed_extractions_to_evidence_rows import convert_outputs


ROOT = Path(__file__).resolve().parents[2]
PROCESSED_DIR = ROOT / "data" / "processed"
EXTRACTION_DIR = PROCESSED_DIR / "extraction"
ROUTED_RUNS_DIR = EXTRACTION_DIR / "routed_runs"
UPDATE_ROOT = PROCESSED_DIR / "paper_updates"
ACTIVE_EXTRACTION_POINTER = EXTRACTION_DIR / "active_routed_run.json"
ACTIVE_GRAPH_POINTER = PROCESSED_DIR / "graph_payload_active.json"
DEFAULT_TASKS = EXTRACTION_DIR / "route_extraction_tasks.jsonl"
DEFAULT_ROUTES = PROCESSED_DIR / "corpus" / "paper_extraction_routes.parquet"

DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$", re.IGNORECASE)
RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
READY_STATUS = "ready_for_model"
POINTER_SCHEMA_VERSION = "active_routed_extraction_run_v1"
UPDATE_SCHEMA_VERSION = "scoped_paper_update_v1"


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
    output_family = normalize(task_contract(row).get("output_family")).lower()
    return {
        "primary_evidence": "primary",
        "review_coverage": "reviews",
        "meta_analysis_evidence": "meta_analyses",
    }.get(output_family, "other")


def task_id(row: dict) -> str:
    return normalize(row.get("task_id"))


def route_id(row: dict) -> str:
    return normalize(row.get("route_id"))


def fingerprint(row: dict) -> str:
    return normalize(row.get("input_fingerprint"))


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
    run_checked([python, str(ROOT / "pipeline" / "extract" / "build_extraction_routes.py")])
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


def prepare(args: argparse.Namespace) -> int:
    update_id = safe_update_id(args.update_id)
    doi_file = Path(args.doi_file).resolve()
    requested_scope = read_doi_file(doi_file)
    if args.refresh_derived:
        refresh_deterministic_layers(doi_file)

    tasks_path = Path(args.tasks_jsonl).resolve()
    routes_path = Path(args.route_table).resolve()
    all_tasks, _ = current_task_index(tasks_path)
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

    base_run_id, base_outputs, base_evidence, base_pointer = resolve_active_base(
        base_outputs=Path(args.base_outputs) if args.base_outputs else None,
        base_evidence=Path(args.base_evidence) if args.base_evidence else None,
    )
    base_output_snapshot = file_snapshot(base_outputs)
    base_evidence_snapshot = file_snapshot(base_evidence)
    tasks_snapshot = file_snapshot(tasks_path)
    routes_snapshot = file_snapshot(routes_path)

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
        task_files[group] = {"path": str(group_path.resolve()), "tasks": len(group_rows)}

    ready_dois = {normalize_doi(task.get("study_doi")) for task in ready_tasks}
    current_task_dois = {normalize_doi(task.get("study_doi")) for task in scoped_tasks}
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
                            normalize(task.get("text_source", {}).get("mode"))
                            for task in doi_ready
                            if isinstance(task.get("text_source"), dict)
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
                    normalize(task.get("text_source", {}).get("mode"))
                    for task in ready_tasks
                    if isinstance(task.get("text_source"), dict)
                )
            ),
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
    if manifest.get("phase") != "prepared" or manifest.get("update_id") != update_id:
        raise ValueError(f"Not a prepared manifest for update {update_id}: {manifest_path}")

    scope = read_doi_file(Path(manifest["scope"]["scope_dois_file"]))
    base_outputs = verify_snapshot(manifest["base"]["outputs"], "Base outputs")
    base_evidence = verify_snapshot(manifest["base"]["evidence"], "Base evidence")
    verify_snapshot(manifest["current_inputs"]["tasks"], "Current task manifest")
    verify_snapshot(manifest["current_inputs"]["routes"], "Current route table")

    ready_tasks_path = Path(manifest["files"]["ready_tasks"])
    ready_tasks, ready_by_id = current_task_index(ready_tasks_path)
    patch_paths = [Path(path).resolve() for path in args.patch_outputs]
    if ready_tasks and not patch_paths:
        raise RuntimeError(
            f"This update has {len(ready_tasks)} ready tasks; supply their extraction output files with --patch-outputs."
        )
    patch_rows, patch_report = selected_patch_outputs(patch_paths, ready_by_id)

    candidate_run_dir = ROUTED_RUNS_DIR / update_id
    if candidate_run_dir.exists() and any(candidate_run_dir.iterdir()):
        if not args.overwrite:
            raise FileExistsError(
                f"Candidate run directory is not empty: {candidate_run_dir}. Use --overwrite to regenerate it."
            )
        shutil.rmtree(candidate_run_dir)
    candidate_run_dir.mkdir(parents=True, exist_ok=True)
    candidate_outputs = candidate_run_dir / "route_extraction_outputs.jsonl"
    combined_output_count = write_jsonl_atomic(
        candidate_outputs,
        iter_merged_outputs(base_outputs, scope, patch_rows),
    )

    patch_tasks_path = candidate_run_dir / "scoped_route_extraction_tasks.jsonl"
    patch_outputs_path = candidate_run_dir / "scoped_route_extraction_outputs.jsonl"
    write_jsonl_atomic(patch_tasks_path, ready_tasks)
    write_jsonl_atomic(patch_outputs_path, patch_rows)
    patch_evidence, conversion_report = convert_outputs(
        input_jsonl=patch_outputs_path,
        tasks_jsonl=patch_tasks_path,
        active_route_table=Path(manifest["current_inputs"]["routes"]["path"]),
    )
    write_json_atomic(candidate_run_dir / "scoped_routed_evidence_rows.json", patch_evidence)
    write_json_atomic(candidate_run_dir / "scoped_routed_evidence_rows_report.json", conversion_report)

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

    final_report = {
        "schema_version": UPDATE_SCHEMA_VERSION,
        "phase": "finalized_candidate",
        "generated_at_utc": now_utc(),
        "update_id": update_id,
        "scope_dois": len(scope),
        "ready_tasks_required": len(ready_tasks),
        "patch": patch_report,
        "raw_outputs": {
            "base_rows": manifest["base"]["output_rows"],
            "base_scope_rows_removed": manifest["base"]["scope_output_rows_to_replace"],
            "patch_rows_added": len(patch_rows),
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
            "patch_conversion": conversion_report,
        },
        "candidate_run": {
            "run_dir": str(candidate_run_dir.resolve()),
            "outputs": file_snapshot(candidate_outputs),
            "evidence": file_snapshot(candidate_evidence),
            "scoped_tasks": file_snapshot(patch_tasks_path),
            "scoped_outputs": file_snapshot(patch_outputs_path),
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
    print(f"Successful current outputs added: {len(patch_rows)}")
    print(f"Candidate evidence rows: {len(candidate_evidence_rows)}")
    print("The active KG has not changed. Run the promote subcommand after reviewing this report.")
    return 0


def relative_to_root(path: Path) -> str:
    return str(path.resolve().relative_to(ROOT.resolve()))


def swap_staged_directory(staged: Path, current: Path, previous: Path) -> None:
    """Replace a generated directory while keeping a rollback directory."""
    previous.parent.mkdir(parents=True, exist_ok=True)
    moved_previous = False
    if current.exists():
        current.rename(previous)
        moved_previous = True
    try:
        staged.rename(current)
    except Exception:
        if moved_previous and previous.exists():
            previous.rename(current)
        raise


def expected_graph_pointer(update_id: str) -> dict:
    payload_rel = Path("data") / "processed" / "graph_payload_runs" / update_id
    return {
        "schema_version": "route_native_evidence_payload_active_v1",
        "active_graph_bootstraps": {
            "primary": str(payload_rel / "graph_bootstrap_primary.json"),
            "meta_analyses": str(payload_rel / "graph_bootstrap_meta_analyses.json"),
            "reviews": str(payload_rel / "graph_bootstrap_reviews.json"),
        },
        "active_detail_bootstraps": {
            "primary": str(payload_rel / "detail_bootstrap_primary.json"),
            "meta_analyses": str(payload_rel / "detail_bootstrap_meta_analyses.json"),
            "reviews": str(payload_rel / "detail_bootstrap_reviews.json"),
        },
        "active_manifest": str(payload_rel / "graph_payload_manifest.json"),
        "evidence_source": "kg_tables",
        "kg_dir": str(Path("data") / "processed" / "kg_routed_runs" / update_id),
    }


def promote(args: argparse.Namespace) -> int:
    update_id = safe_update_id(args.update_id)
    update_dir = Path(args.update_dir).resolve() if args.update_dir else UPDATE_ROOT / update_id
    manifest_path = update_dir / "update_manifest.json"
    manifest = read_json_object(manifest_path)
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
    if base_run_id and base_author_cache.is_file():
        env["AUTHOR_CACHE_SEED"] = str(base_author_cache.resolve())
    author_args = ["--offline"] if args.offline else []
    run_checked(
        [str(ROOT / "scripts" / "build_routed_kg_payload.sh"), update_id, *author_args],
        env=env,
    )

    new_graph_pointer = expected_graph_pointer(update_id)
    for path_value in (
        *new_graph_pointer["active_graph_bootstraps"].values(),
        *new_graph_pointer["active_detail_bootstraps"].values(),
        new_graph_pointer["active_manifest"],
        new_graph_pointer["kg_dir"],
    ):
        if not (ROOT / path_value).exists():
            raise RuntimeError(f"Downstream build did not create expected artifact: {path_value}")

    stage_root = update_dir / ".promotion_stage"
    if stage_root.exists():
        shutil.rmtree(stage_root)
    staged_methods = stage_root / "data_kg"
    staged_dist = stage_root / "dist"
    previous_methods = stage_root / "previous_data_kg"
    previous_dist = stage_root / "previous_dist"
    current_methods = ROOT / "data" / "kg"
    current_dist = ROOT / "dist"
    new_kg_dir = ROOT / new_graph_pointer["kg_dir"]
    run_checked(
        [
            sys.executable,
            str(ROOT / "pipeline" / "kg" / "build_methods_flow.py"),
            "--kg-dir",
            str(new_kg_dir),
            "--out-dir",
            str(staged_methods),
        ]
    )

    old_graph_pointer = ACTIVE_GRAPH_POINTER.read_bytes() if ACTIVE_GRAPH_POINTER.exists() else None
    methods_swapped = False
    dist_swapped = False
    try:
        stage_root.mkdir(parents=True, exist_ok=True)
        swap_staged_directory(staged_methods, current_methods, previous_methods)
        methods_swapped = True
        write_json_atomic(ACTIVE_GRAPH_POINTER, new_graph_pointer)
        site_env = dict(os.environ)
        site_env["DIST_DIR"] = str(staged_dist)
        run_checked([str(ROOT / "scripts" / "build_site.sh")], env=site_env)
        swap_staged_directory(staged_dist, current_dist, previous_dist)
        dist_swapped = True
    except Exception:
        if dist_swapped:
            shutil.rmtree(current_dist, ignore_errors=True)
            if previous_dist.exists():
                previous_dist.rename(current_dist)
        if methods_swapped:
            shutil.rmtree(current_methods, ignore_errors=True)
            if previous_methods.exists():
                previous_methods.rename(current_methods)
        if old_graph_pointer is None:
            ACTIVE_GRAPH_POINTER.unlink(missing_ok=True)
        else:
            ACTIVE_GRAPH_POINTER.write_bytes(old_graph_pointer)
        raise

    active_pointer = {
        "schema_version": POINTER_SCHEMA_VERSION,
        "updated_at_utc": now_utc(),
        "run_id": update_id,
        "outputs_jsonl": relative_to_root(Path(candidate["outputs"]["path"])),
        "evidence_rows_json": relative_to_root(Path(candidate["evidence"]["path"])),
        "kg_dir": new_graph_pointer["kg_dir"],
        "graph_payload_manifest": new_graph_pointer["active_manifest"],
        "source_update_manifest": relative_to_root(manifest_path),
    }
    write_json_atomic(ACTIVE_EXTRACTION_POINTER, active_pointer)
    manifest["phase"] = "promoted"
    manifest["promoted_at_utc"] = active_pointer["updated_at_utc"]
    manifest["active_pointer"] = str(ACTIVE_EXTRACTION_POINTER.resolve())
    write_json_atomic(manifest_path, manifest)
    shutil.rmtree(stage_root, ignore_errors=True)
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
        help="JSONL output from a scoped extraction batch; repeat for primary/review/meta batches.",
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
