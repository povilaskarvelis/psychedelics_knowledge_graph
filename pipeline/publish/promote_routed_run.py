#!/usr/bin/env python3
"""Promote one already-built routed release as a single guarded operation.

The extraction and public graph pointers serve different consumers, but they
must describe the same release. This command validates the versioned KG and
payload, refreshes Methods and the static site in staging directories, and
updates both compatibility pointers under one promotion lock.
"""

from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.extract.route_extraction_profiles import is_legacy_v1_secondary_profile
from pipeline.kg.graph_view_contract import graph_view_ids


PROCESSED_DIR = ROOT / "data" / "processed"
EXTRACTION_DIR = PROCESSED_DIR / "extraction"
ROUTED_RUNS_DIR = EXTRACTION_DIR / "routed_runs"
KG_RUNS_DIR = PROCESSED_DIR / "kg_routed_runs"
PAYLOAD_RUNS_DIR = PROCESSED_DIR / "graph_payload_runs"
QUERY_RUNS_DIR = PROCESSED_DIR / "query_api_runs"
ACTIVE_EXTRACTION_POINTER = EXTRACTION_DIR / "active_routed_run.json"
ACTIVE_GRAPH_POINTER = PROCESSED_DIR / "graph_payload_active.json"
CANDIDATE_PAPERS_TABLE = PROCESSED_DIR / "corpus" / "candidate_papers.parquet"
PAPER_FUNDING_TABLE = PROCESSED_DIR / "corpus" / "paper_funding.parquet"
PAPER_FUNDING_ATTEMPTS_TABLE = PROCESSED_DIR / "corpus" / "paper_funding_provider_attempts.parquet"
GRAPH_DISPOSITION_OVERRIDES = ROOT / "data" / "curated" / "graph_inclusion_disposition_overrides.json"
DOI_ALIAS_REGISTRY = ROOT / "pipeline" / "validate" / "doi_alias_registry.json"
PROMOTION_LOCK = PROCESSED_DIR / ".routed_release_promotion.lock"

RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
EXTRACTION_POINTER_SCHEMA = "active_routed_extraction_run_v1"
GRAPH_POINTER_SCHEMA = "route_native_evidence_payload_active_v1"
PAYLOAD_MANIFEST_SCHEMA = "route_native_evidence_manifest_v1"
PUBLIC_QUERY_MANIFEST_SCHEMA = "psychedelics_kg_public_catalogue_manifest_v2"
PUBLIC_QUERY_TABLES = {
    "papers",
    "concepts",
    "authors",
    "paper_authors",
    "relationships",
}
DETAIL_VIEW_KEYS = graph_view_ids()


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def normalize(value: object) -> str:
    return " ".join(str(value or "").split())


def safe_run_id(value: object) -> str:
    run_id = normalize(value)
    if not RUN_ID_RE.fullmatch(run_id):
        raise ValueError(
            "Run ID must start with a letter or number and contain only "
            "letters, numbers, dots, underscores, or hyphens."
        )
    return run_id


def read_json_object(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def legacy_v1_secondary_counts(outputs_jsonl: Path) -> dict[str, int]:
    """Return legacy secondary contracts present in a routed output stream."""

    counts: dict[str, int] = {}
    with outputs_jsonl.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            contract = row.get("extraction_contract", {}) if isinstance(row.get("extraction_contract"), dict) else {}
            prompt_profile = normalize(row.get("prompt_profile") or contract.get("prompt_profile"))
            schema_profile = normalize(row.get("schema_profile") or contract.get("schema_profile"))
            if is_legacy_v1_secondary_profile(prompt_profile, schema_profile):
                key = f"{prompt_profile}/{schema_profile}"
                counts[key] = counts.get(key, 0) + 1
    return counts


def reject_legacy_v1_secondary_outputs(outputs_jsonl: Path) -> None:
    counts = legacy_v1_secondary_counts(outputs_jsonl)
    if not counts:
        return
    details = ", ".join(f"{key}={count}" for key, count in sorted(counts.items()))
    raise ValueError(
        "Promotion refused: routed outputs contain permanently disabled legacy v1 "
        f"meta-analysis/review extraction ({details}). Re-extract meta-analyses with "
        "the v2 pipeline and reviews with the paper-centered relationship pipeline."
    )


def write_json_atomic(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        temp_path = Path(handle.name)
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    try:
        os.replace(temp_path, path)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def root_relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError as exc:
        raise ValueError(f"Release inputs must be inside the repository: {path}") from exc


def resolve_repo_path(value: object) -> Path:
    text = normalize(value)
    if not text:
        raise ValueError("Expected a non-empty repository path")
    path = Path(text)
    return path.resolve() if path.is_absolute() else (ROOT / path).resolve()


def graph_pointer_for_run(
    run_id: str,
    release_id: str,
    *,
    public_release_id: str = "",
) -> dict:
    payload_rel = Path("data") / "processed" / "graph_payload_runs" / run_id
    return {
        "schema_version": GRAPH_POINTER_SCHEMA,
        "release_id": release_id,
        "public_release_id": public_release_id or release_id,
        "run_id": run_id,
        "active_graph_bootstraps": {
            "primary": (payload_rel / "graph_bootstrap_primary.json").as_posix(),
            "meta_analyses": (payload_rel / "graph_bootstrap_meta_analyses.json").as_posix(),
            "reviews": (payload_rel / "graph_bootstrap_reviews.json").as_posix(),
        },
        "active_dashboard_bootstraps": {
            "primary": (payload_rel / "dashboard_bootstrap_primary.json").as_posix(),
            "meta_analyses": (payload_rel / "dashboard_bootstrap_meta_analyses.json").as_posix(),
            "reviews": (payload_rel / "dashboard_bootstrap_reviews.json").as_posix(),
        },
        "active_detail_bootstraps": {
            "primary": (payload_rel / "detail_bootstrap_primary.json").as_posix(),
            "meta_analyses": (payload_rel / "detail_bootstrap_meta_analyses.json").as_posix(),
            "reviews": (payload_rel / "detail_bootstrap_reviews.json").as_posix(),
        },
        "active_detail_bootstraps_by_view": {
            source_key: {
                view_key: (
                    payload_rel / f"detail_bootstrap_{source_key}_{view_key}.json"
                ).as_posix()
                for view_key in DETAIL_VIEW_KEYS
            }
            for source_key in ("primary", "meta_analyses", "reviews")
        },
        "active_manifest": (payload_rel / "graph_payload_manifest.json").as_posix(),
        "evidence_source": "kg_tables",
        "kg_dir": (Path("data") / "processed" / "kg_routed_runs" / run_id).as_posix(),
    }


def extraction_pointer_for_run(
    *,
    run_id: str,
    release_id: str,
    graph_pointer: dict,
    outputs_jsonl: Path,
    evidence_rows_json: Path,
    source_update_manifest: Path | None,
) -> dict:
    pointer = {
        "schema_version": EXTRACTION_POINTER_SCHEMA,
        "release_id": release_id,
        "updated_at_utc": now_utc(),
        "run_id": run_id,
        "outputs_jsonl": root_relative(outputs_jsonl),
        "evidence_rows_json": root_relative(evidence_rows_json),
        "kg_dir": graph_pointer["kg_dir"],
        "graph_payload_manifest": graph_pointer["active_manifest"],
    }
    if source_update_manifest is not None:
        pointer["source_update_manifest"] = root_relative(source_update_manifest)
    return pointer


def resolve_extraction_inputs(args: argparse.Namespace, run_id: str) -> tuple[Path, Path, Path | None]:
    current: dict = {}
    if ACTIVE_EXTRACTION_POINTER.is_file():
        current = read_json_object(ACTIVE_EXTRACTION_POINTER)

    use_current = normalize(current.get("run_id")) == run_id
    default_run_dir = ROUTED_RUNS_DIR / run_id

    outputs = (
        resolve_repo_path(args.outputs_jsonl)
        if args.outputs_jsonl
        else resolve_repo_path(current["outputs_jsonl"])
        if use_current and current.get("outputs_jsonl")
        else default_run_dir / "route_extraction_outputs.jsonl"
    )
    evidence = (
        resolve_repo_path(args.evidence_rows_json)
        if args.evidence_rows_json
        else resolve_repo_path(current["evidence_rows_json"])
        if use_current and current.get("evidence_rows_json")
        else default_run_dir / "routed_evidence_rows.json"
    )

    source_manifest_value = args.source_update_manifest
    if not source_manifest_value and use_current:
        source_manifest_value = normalize(current.get("source_update_manifest"))
    source_manifest = resolve_repo_path(source_manifest_value) if source_manifest_value else None

    for label, path in (("combined extraction outputs", outputs), ("combined evidence rows", evidence)):
        if not path.is_file():
            raise FileNotFoundError(
                f"Missing {label}: {path}. Pass its path explicitly when promoting a combined run."
            )
    if source_manifest is not None and not source_manifest.is_file():
        raise FileNotFoundError(f"Missing source update manifest: {source_manifest}")
    return outputs.resolve(), evidence.resolve(), source_manifest.resolve() if source_manifest else None


def materialize_active_extraction_inputs(
    *,
    run_id: str,
    outputs_jsonl: Path,
    evidence_rows_json: Path,
    source_update_manifest: Path | None,
) -> tuple[Path, Path, Path | None]:
    """Make the promoted extraction snapshot self-contained under its run ID."""
    run_dir = (ROUTED_RUNS_DIR / safe_run_id(run_id)).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    values: list[tuple[Path, Path]] = [
        (
            outputs_jsonl.resolve(),
            run_dir / "route_extraction_outputs.jsonl",
        ),
        (
            evidence_rows_json.resolve(),
            run_dir / "routed_evidence_rows.json",
        ),
    ]
    if source_update_manifest is not None:
        values.append(
            (
                source_update_manifest.resolve(),
                run_dir / "source_update_manifest.json",
            )
        )

    materialized: list[Path] = []
    for source, target in values:
        if source == target.resolve():
            materialized.append(target)
            continue
        if not source.is_file():
            raise FileNotFoundError(f"Missing extraction release input: {source}")
        if (
            target.is_file()
            and target.stat().st_size == source.stat().st_size
            and sha256_file(target) == sha256_file(source)
        ):
            materialized.append(target)
            continue
        temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
        try:
            shutil.copy2(source, temporary)
            if (
                temporary.stat().st_size != source.stat().st_size
                or sha256_file(temporary) != sha256_file(source)
            ):
                raise RuntimeError(
                    f"Copied extraction input failed verification: {source}"
                )
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
        materialized.append(target)

    return (
        materialized[0],
        materialized[1],
        materialized[2] if len(materialized) == 3 else None,
    )


def validate_public_payload(
    run_id: str,
    graph_pointer: dict,
    *,
    require_release_binding: bool = True,
) -> dict:
    """Validate the committed files required to build and serve the public site."""
    evidence_release_id = normalize(graph_pointer.get("release_id"))
    public_release_id = normalize(
        graph_pointer.get("public_release_id") or evidence_release_id
    )
    if not evidence_release_id or not public_release_id:
        raise ValueError("Active public graph pointer is missing its release_id")

    expected_pointer = graph_pointer_for_run(
        run_id,
        evidence_release_id,
        public_release_id=public_release_id,
    )
    for key, expected in expected_pointer.items():
        if graph_pointer.get(key) != expected:
            raise ValueError(f"Active public graph pointer has an unexpected {key}")

    payload_manifest_path = ROOT / expected_pointer["active_manifest"]
    if not payload_manifest_path.is_file():
        raise FileNotFoundError(f"Missing versioned payload manifest: {payload_manifest_path}")
    payload_manifest = read_json_object(payload_manifest_path)
    if normalize(payload_manifest.get("schema_version")) != PAYLOAD_MANIFEST_SCHEMA:
        raise ValueError(f"Unexpected payload manifest schema: {payload_manifest_path}")
    if normalize(payload_manifest.get("kg_dir")) != graph_pointer["kg_dir"]:
        raise ValueError(f"Payload manifest points at a different KG: {payload_manifest_path}")
    if int(payload_manifest.get("row_count", -1)) < 0:
        raise ValueError(f"Payload manifest has an invalid row count: {payload_manifest_path}")
    if require_release_binding:
        if normalize(payload_manifest.get("release_id")) != public_release_id:
            raise ValueError("Payload manifest release_id does not match the public release")
        if normalize(payload_manifest.get("evidence_release_id")) != evidence_release_id:
            raise ValueError("Payload manifest evidence_release_id does not match the graph pointer")
    if normalize((payload_manifest.get("author_tables") or {}).get("status")) != "ok":
        raise ValueError(f"Author tables are missing or stale: {payload_manifest_path}")

    expected_file_keys: set[str] = set()
    for mapping_key, manifest_key, file_prefix in (
        ("active_graph_bootstraps", "graph_bootstraps", "graph"),
        ("active_dashboard_bootstraps", "dashboard_bootstraps", "dashboard"),
        ("active_detail_bootstraps", "detail_bootstraps", "detail"),
    ):
        expected = graph_pointer[mapping_key]
        actual = payload_manifest.get(manifest_key) or {}
        if actual != expected:
            raise ValueError(f"Payload manifest {manifest_key} does not match the expected run files")
        for source_key, path_value in expected.items():
            path = ROOT / path_value
            if not path.is_file():
                raise FileNotFoundError(f"Missing payload file: {path_value}")
            logical_name = f"{file_prefix}:{source_key}"
            expected_file_keys.add(logical_name)
            entry = (payload_manifest.get("files") or {}).get(logical_name) or {}
            if entry.get("path") != path_value:
                raise ValueError(f"Payload manifest file path mismatch for {logical_name}")
            if int(entry.get("bytes", -1)) != path.stat().st_size:
                raise ValueError(f"Payload manifest file size mismatch for {logical_name}")
            if normalize(entry.get("sha256")).casefold() != sha256_file(path):
                raise ValueError(f"Payload manifest checksum mismatch for {logical_name}")
    expected_detail_views = graph_pointer["active_detail_bootstraps_by_view"]
    actual_detail_views = payload_manifest.get("detail_bootstraps_by_view") or {}
    if actual_detail_views != expected_detail_views:
        raise ValueError(
            "Payload manifest detail_bootstraps_by_view does not match the expected run files"
        )
    for source_key, source_views in expected_detail_views.items():
        for view_key, path_value in source_views.items():
            path = ROOT / path_value
            if not path.is_file():
                raise FileNotFoundError(f"Missing payload file: {path_value}")
            logical_name = f"detail_view:{source_key}:{view_key}"
            expected_file_keys.add(logical_name)
            entry = (payload_manifest.get("files") or {}).get(logical_name) or {}
            if entry.get("path") != path_value:
                raise ValueError(f"Payload manifest file path mismatch for {logical_name}")
            if int(entry.get("bytes", -1)) != path.stat().st_size:
                raise ValueError(f"Payload manifest file size mismatch for {logical_name}")
            if normalize(entry.get("sha256")).casefold() != sha256_file(path):
                raise ValueError(f"Payload manifest checksum mismatch for {logical_name}")
    if set(payload_manifest.get("files") or {}) != expected_file_keys:
        raise ValueError("Payload manifest contains an unexpected file set")
    return payload_manifest


def validate_active_public_release() -> dict:
    """Validate only committed public-release artifacts; safe in a clean checkout."""
    graph_pointer = read_json_object(ACTIVE_GRAPH_POINTER)
    if normalize(graph_pointer.get("schema_version")) != GRAPH_POINTER_SCHEMA:
        raise ValueError(f"Unexpected active graph pointer schema: {ACTIVE_GRAPH_POINTER}")
    run_id = safe_run_id(graph_pointer.get("run_id"))
    payload_manifest = validate_public_payload(run_id, graph_pointer)
    return {
        "run_id": run_id,
        "release_id": normalize(
            graph_pointer.get("public_release_id") or graph_pointer.get("release_id")
        ),
        "evidence_release_id": normalize(graph_pointer.get("release_id")),
        "row_count": int(payload_manifest["row_count"]),
    }


def validate_built_release(run_id: str, graph_pointer: dict) -> dict:
    kg_dir = KG_RUNS_DIR / run_id
    kg_manifest_path = kg_dir / "manifest.json"
    if not kg_manifest_path.is_file():
        raise FileNotFoundError(f"Missing versioned KG manifest: {kg_manifest_path}")

    kg_manifest = read_json_object(kg_manifest_path)
    if normalize(kg_manifest.get("run_id")) != run_id:
        raise ValueError(f"KG manifest run_id does not match {run_id}: {kg_manifest_path}")
    if normalize(kg_manifest.get("source_preset")) != "routed":
        raise ValueError(f"KG manifest is not a routed build: {kg_manifest_path}")

    payload_manifest = validate_public_payload(
        run_id,
        graph_pointer,
        require_release_binding=False,
    )
    findings_rows = int(((kg_manifest.get("tables") or {}).get("findings") or {}).get("rows", -1))
    payload_rows = int(payload_manifest.get("row_count", -2))
    if findings_rows < 0 or payload_rows != findings_rows:
        raise ValueError(
            f"Payload/KG row-count mismatch for {run_id}: payload={payload_rows}, findings={findings_rows}"
        )
    paper_rows = int(((kg_manifest.get("tables") or {}).get("papers") or {}).get("rows", -1))
    validate_public_query_artifact(run_id, kg_dir, paper_rows)
    return payload_manifest


def validate_public_query_artifact(
    run_id: str,
    kg_dir: Path,
    paper_rows: int,
    *,
    expected_release_id: str = "",
    expected_evidence_release_id: str = "",
) -> dict:
    query_dir = QUERY_RUNS_DIR / run_id
    manifest_path = query_dir / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(
            f"Missing public query artifact for {run_id}: {manifest_path}. "
            "Re-run scripts/build_routed_kg_payload.sh before promotion."
        )
    manifest = read_json_object(manifest_path)
    if normalize(manifest.get("schema_version")) != PUBLIC_QUERY_MANIFEST_SCHEMA:
        raise ValueError(f"Unexpected public query manifest schema: {manifest_path}")
    if normalize(manifest.get("run_id")) != run_id:
        raise ValueError(f"Public query manifest run_id does not match {run_id}: {manifest_path}")
    if Path(normalize(manifest.get("kg_dir"))).name != kg_dir.name:
        raise ValueError(f"Public query manifest points at a different KG: {manifest_path}")
    if expected_release_id and normalize(manifest.get("release_id")) != expected_release_id:
        raise ValueError("Public query manifest release_id does not match the active graph release")
    if (
        expected_evidence_release_id
        and normalize(manifest.get("evidence_release_id")) != expected_evidence_release_id
    ):
        raise ValueError("Public query manifest evidence_release_id does not match the graph pointer")
    row_counts = manifest.get("row_counts") or {}
    if set(row_counts) != PUBLIC_QUERY_TABLES:
        raise ValueError(
            f"Unexpected public catalogue tables for {run_id}: {sorted(row_counts)}"
        )
    public_papers = int(row_counts.get("papers", -1))
    if paper_rows < 0 or public_papers != paper_rows:
        raise ValueError(
            f"Public catalogue/KG paper-count mismatch for {run_id}: "
            f"public={public_papers}, kg={paper_rows}"
        )
    for key in ("database", "schema"):
        relative_path = normalize(manifest.get(key))
        if not relative_path or not (query_dir / relative_path).is_file():
            raise FileNotFoundError(f"Public query artifact is missing {key}: {query_dir}")
    return manifest


def bind_public_release_manifests(
    run_id: str,
    *,
    evidence_release_id: str,
    public_release_id: str,
) -> tuple[Path, Path]:
    graph_manifest_path = PAYLOAD_RUNS_DIR / run_id / "graph_payload_manifest.json"
    query_manifest_path = QUERY_RUNS_DIR / run_id / "manifest.json"
    graph_manifest = read_json_object(graph_manifest_path)
    query_manifest = read_json_object(query_manifest_path)
    graph_manifest["release_id"] = public_release_id
    graph_manifest["evidence_release_id"] = evidence_release_id
    query_manifest["release_id"] = public_release_id
    query_manifest["evidence_release_id"] = evidence_release_id
    write_json_atomic(graph_manifest_path, graph_manifest)
    write_json_atomic(query_manifest_path, query_manifest)
    return graph_manifest_path, query_manifest_path


def validate_active_pointer_pair() -> dict:
    extraction_pointer = read_json_object(ACTIVE_EXTRACTION_POINTER)
    graph_pointer = read_json_object(ACTIVE_GRAPH_POINTER)
    extraction_run = safe_run_id(extraction_pointer.get("run_id"))
    graph_run = normalize(graph_pointer.get("run_id")) or Path(
        normalize(graph_pointer.get("kg_dir"))
    ).name
    if extraction_run != graph_run:
        raise ValueError(
            "Active release mismatch: extraction points to "
            f"{extraction_run!r}, while the public graph points to {graph_run!r}."
        )
    extraction_release = normalize(extraction_pointer.get("release_id"))
    graph_release = normalize(graph_pointer.get("release_id"))
    if extraction_release or graph_release:
        if not extraction_release or extraction_release != graph_release:
            raise ValueError("Active release mismatch: pointer release IDs differ")
    if not CANDIDATE_PAPERS_TABLE.is_file():
        raise FileNotFoundError(f"Canonical corpus table is missing: {CANDIDATE_PAPERS_TABLE}")
    import pandas as pd

    corpus_release = pd.read_parquet(
        CANDIDATE_PAPERS_TABLE,
        columns=["graph_inclusion_run_id", "graph_inclusion_release_id"],
    )
    corpus_runs = {normalize(value) for value in corpus_release["graph_inclusion_run_id"] if normalize(value)}
    corpus_releases = {
        normalize(value) for value in corpus_release["graph_inclusion_release_id"] if normalize(value)
    }
    if corpus_runs != {graph_run}:
        raise ValueError(f"Active release mismatch: canonical corpus run IDs are {sorted(corpus_runs)}")
    if graph_release and corpus_releases != {graph_release}:
        raise ValueError("Active release mismatch: canonical corpus release ID differs")
    return {"run_id": extraction_run, "release_id": extraction_release or "legacy"}


def run_checked(command: list[str], *, env: dict[str, str] | None = None) -> None:
    print("+ " + " ".join(command), flush=True)
    subprocess.run(command, cwd=ROOT, env=env, check=True)


def retarget_methods_manifest(
    staged_methods: Path,
    current_methods: Path,
    *,
    staged_candidate_table: Path,
    current_candidate_table: Path,
) -> None:
    """Replace staging-only output paths before the directory becomes live."""
    manifest_path = staged_methods / "manifests" / "build_manifest.json"
    manifest = read_json_object(manifest_path)
    manifest["outputs"] = {
        "schema": str((current_methods / "schema" / "methods_flow.schema.json").resolve()),
        "pipeline_status_graph": str(
            (current_methods / "views" / "pipeline_status_graph.json").resolve()
        ),
        "methods_bibliography": str(
            (current_methods / "views" / "methods_bibliography.json").resolve()
        ),
        "graph_inclusion_dispositions": str(
            (current_methods / "views" / "graph_inclusion_dispositions.json").resolve()
        ),
        "manifest": str((current_methods / "manifests" / "build_manifest.json").resolve()),
    }
    staged_candidate = str(staged_candidate_table.resolve())
    current_candidate = str(current_candidate_table.resolve())
    manifest["input_files"] = [
        current_candidate if path == staged_candidate else path
        for path in manifest.get("input_files", [])
    ]
    write_json_atomic(manifest_path, manifest)


def restore_file(path: Path, previous: bytes | None) -> None:
    if previous is None:
        path.unlink(missing_ok=True)
    else:
        path.write_bytes(previous)


def swap_directory(staged: Path, current: Path, backup: Path) -> None:
    shutil.rmtree(backup, ignore_errors=True)
    if current.exists():
        current.rename(backup)
    try:
        staged.rename(current)
    except Exception:
        if backup.exists():
            backup.rename(current)
        raise


def replace_file_atomic(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        dir=destination.parent,
        prefix=f".{destination.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        temp_path = Path(handle.name)
    try:
        shutil.copy2(source, temp_path)
        os.replace(temp_path, destination)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise


@contextmanager
def promotion_lock() -> Iterator[None]:
    PROMOTION_LOCK.parent.mkdir(parents=True, exist_ok=True)
    with PROMOTION_LOCK.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def refresh_public_artifacts(requested_run_id: str = "") -> dict:
    """Publish a new graph/API artifact revision without changing evidence decisions."""

    with promotion_lock():
        active = validate_active_pointer_pair()
        run_id = safe_run_id(requested_run_id or active["run_id"])
        if run_id != active["run_id"]:
            raise ValueError(
                f"Active evidence run is {active['run_id']}, not requested run {run_id}"
            )
        evidence_release_id = normalize(active["release_id"])
        if not evidence_release_id or evidence_release_id == "legacy":
            raise ValueError("A versioned evidence release is required for a public refresh")
        public_release_id = f"{run_id}:public:{uuid.uuid4().hex}"
        graph_pointer = graph_pointer_for_run(
            run_id,
            evidence_release_id,
            public_release_id=public_release_id,
        )
        validate_built_release(run_id, graph_pointer)

        graph_manifest_path = PAYLOAD_RUNS_DIR / run_id / "graph_payload_manifest.json"
        query_manifest_path = QUERY_RUNS_DIR / run_id / "manifest.json"
        old_graph_pointer = ACTIVE_GRAPH_POINTER.read_bytes()
        old_graph_manifest = graph_manifest_path.read_bytes()
        old_query_manifest = query_manifest_path.read_bytes()
        stage_root = Path(
            tempfile.mkdtemp(prefix=f".refresh-public-{run_id}.", dir=PROCESSED_DIR)
        )
        staged_dist = stage_root / "dist"
        previous_dist = stage_root / "previous_dist"
        current_dist = ROOT / "dist"
        dist_swapped = False
        try:
            bind_public_release_manifests(
                run_id,
                evidence_release_id=evidence_release_id,
                public_release_id=public_release_id,
            )
            validate_public_payload(run_id, graph_pointer)
            kg_manifest = read_json_object(KG_RUNS_DIR / run_id / "manifest.json")
            paper_rows = int(
                ((kg_manifest.get("tables") or {}).get("papers") or {}).get("rows", -1)
            )
            validate_public_query_artifact(
                run_id,
                KG_RUNS_DIR / run_id,
                paper_rows,
                expected_release_id=public_release_id,
                expected_evidence_release_id=evidence_release_id,
            )
            write_json_atomic(ACTIVE_GRAPH_POINTER, graph_pointer)
            validate_active_pointer_pair()
            site_env = dict(os.environ)
            site_env["DIST_DIR"] = str(staged_dist)
            run_checked([str(ROOT / "scripts" / "build_site.sh")], env=site_env)
            swap_directory(staged_dist, current_dist, previous_dist)
            dist_swapped = True
        except BaseException:
            if dist_swapped:
                shutil.rmtree(current_dist, ignore_errors=True)
                if previous_dist.exists():
                    previous_dist.rename(current_dist)
            restore_file(ACTIVE_GRAPH_POINTER, old_graph_pointer)
            restore_file(graph_manifest_path, old_graph_manifest)
            restore_file(query_manifest_path, old_query_manifest)
            raise
        finally:
            shutil.rmtree(stage_root, ignore_errors=True)
        return {
            "run_id": run_id,
            "release_id": public_release_id,
            "evidence_release_id": evidence_release_id,
            "query_artifact": str(QUERY_RUNS_DIR / run_id),
        }


def promote(args: argparse.Namespace) -> dict:
    run_id = safe_run_id(args.run_id)
    with promotion_lock():
        outputs, evidence, source_manifest = resolve_extraction_inputs(args, run_id)
        reject_legacy_v1_secondary_outputs(outputs)
        outputs, evidence, source_manifest = materialize_active_extraction_inputs(
            run_id=run_id,
            outputs_jsonl=outputs,
            evidence_rows_json=evidence,
            source_update_manifest=source_manifest,
        )
        release_id = f"{run_id}:{uuid.uuid4().hex}"
        graph_pointer = graph_pointer_for_run(run_id, release_id)
        payload_manifest = validate_built_release(run_id, graph_pointer)
        extraction_pointer = extraction_pointer_for_run(
            run_id=run_id,
            release_id=release_id,
            graph_pointer=graph_pointer,
            outputs_jsonl=outputs,
            evidence_rows_json=evidence,
            source_update_manifest=source_manifest,
        )

        stage_root = Path(tempfile.mkdtemp(prefix=f".promote-{run_id}.", dir=PROCESSED_DIR))
        staged_methods = stage_root / "data_kg"
        staged_dist = stage_root / "dist"
        staged_candidate = stage_root / "candidate_papers.parquet"
        previous_methods = stage_root / "previous_data_kg"
        previous_dist = stage_root / "previous_dist"
        current_methods = ROOT / "data" / "kg"
        current_dist = ROOT / "dist"

        graph_status_command = [
                sys.executable,
                str(ROOT / "pipeline" / "kg" / "update_corpus_graph_status.py"),
                "--candidate-table",
                str(CANDIDATE_PAPERS_TABLE),
                "--output-table",
                str(staged_candidate),
                "--kg-dir",
                str(KG_RUNS_DIR / run_id),
                "--disposition-overrides",
                str(GRAPH_DISPOSITION_OVERRIDES),
                "--doi-alias-registry",
                str(DOI_ALIAS_REGISTRY),
                "--run-id",
                run_id,
                "--release-id",
                release_id,
            ]
        extraction_results = [outputs]
        extraction_results.extend(resolve_repo_path(value) for value in args.extraction_results)
        for path in dict.fromkeys(extraction_results):
            graph_status_command.extend(["--extraction-results", str(path)])
        run_checked(graph_status_command)

        run_checked(
            [
                sys.executable,
                str(ROOT / "pipeline" / "ingest" / "materialize_candidate_funding.py"),
                "--candidate-table",
                str(staged_candidate),
                "--output-table",
                str(staged_candidate),
                "--assertions",
                str(PAPER_FUNDING_TABLE),
                "--attempts",
                str(PAPER_FUNDING_ATTEMPTS_TABLE),
                "--doi-alias-registry",
                str(DOI_ALIAS_REGISTRY),
            ]
        )

        run_checked(
            [
                sys.executable,
                str(ROOT / "pipeline" / "kg" / "build_methods_flow.py"),
                "--candidate-table",
                str(staged_candidate),
                "--out-dir",
                str(staged_methods),
            ]
        )
        retarget_methods_manifest(
            staged_methods,
            current_methods,
            staged_candidate_table=staged_candidate,
            current_candidate_table=CANDIDATE_PAPERS_TABLE,
        )

        old_extraction = (
            ACTIVE_EXTRACTION_POINTER.read_bytes() if ACTIVE_EXTRACTION_POINTER.exists() else None
        )
        old_graph = ACTIVE_GRAPH_POINTER.read_bytes() if ACTIVE_GRAPH_POINTER.exists() else None
        old_candidate = CANDIDATE_PAPERS_TABLE.read_bytes() if CANDIDATE_PAPERS_TABLE.exists() else None
        graph_manifest_path = PAYLOAD_RUNS_DIR / run_id / "graph_payload_manifest.json"
        query_manifest_path = QUERY_RUNS_DIR / run_id / "manifest.json"
        old_graph_manifest = graph_manifest_path.read_bytes()
        old_query_manifest = query_manifest_path.read_bytes()
        methods_swapped = False
        dist_swapped = False
        candidate_swapped = False
        try:
            public_release_id = normalize(graph_pointer.get("public_release_id"))
            bind_public_release_manifests(
                run_id,
                evidence_release_id=release_id,
                public_release_id=public_release_id,
            )
            validate_public_payload(run_id, graph_pointer)
            paper_rows = int(
                (
                    (read_json_object(KG_RUNS_DIR / run_id / "manifest.json").get("tables") or {})
                    .get("papers", {})
                    .get("rows", -1)
                )
            )
            validate_public_query_artifact(
                run_id,
                KG_RUNS_DIR / run_id,
                paper_rows,
                expected_release_id=public_release_id,
                expected_evidence_release_id=release_id,
            )
            replace_file_atomic(staged_candidate, CANDIDATE_PAPERS_TABLE)
            candidate_swapped = True
            swap_directory(staged_methods, current_methods, previous_methods)
            methods_swapped = True
            write_json_atomic(ACTIVE_EXTRACTION_POINTER, extraction_pointer)
            write_json_atomic(ACTIVE_GRAPH_POINTER, graph_pointer)

            # The full promotion contract depends on local extraction and corpus
            # state, so keep it here rather than imposing it on clean deploys.
            validate_active_pointer_pair()

            site_env = dict(os.environ)
            site_env["DIST_DIR"] = str(staged_dist)
            run_checked([str(ROOT / "scripts" / "build_site.sh")], env=site_env)
            swap_directory(staged_dist, current_dist, previous_dist)
            dist_swapped = True
        except BaseException:
            if dist_swapped:
                shutil.rmtree(current_dist, ignore_errors=True)
                if previous_dist.exists():
                    previous_dist.rename(current_dist)
            if methods_swapped:
                shutil.rmtree(current_methods, ignore_errors=True)
                if previous_methods.exists():
                    previous_methods.rename(current_methods)
            if candidate_swapped:
                restore_file(CANDIDATE_PAPERS_TABLE, old_candidate)
            restore_file(ACTIVE_EXTRACTION_POINTER, old_extraction)
            restore_file(ACTIVE_GRAPH_POINTER, old_graph)
            restore_file(graph_manifest_path, old_graph_manifest)
            restore_file(query_manifest_path, old_query_manifest)
            raise
        finally:
            if not dist_swapped:
                shutil.rmtree(staged_dist, ignore_errors=True)

        shutil.rmtree(previous_methods, ignore_errors=True)
        shutil.rmtree(previous_dist, ignore_errors=True)
        shutil.rmtree(stage_root, ignore_errors=True)
        return {
            "run_id": run_id,
            "release_id": release_id,
            "row_count": payload_manifest.get("row_count"),
            "query_artifact": str(QUERY_RUNS_DIR / run_id),
            "paper_counts": (payload_manifest.get("summary_stats") or {}).get("paper_counts", {}),
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", default="")
    parser.add_argument(
        "--refresh-public",
        action="store_true",
        help="Create a synchronized graph/API artifact revision without changing evidence decisions.",
    )
    checks = parser.add_mutually_exclusive_group()
    checks.add_argument("--check-active", action="store_true")
    checks.add_argument("--check-public", action="store_true")
    parser.add_argument("--outputs-jsonl", default="")
    parser.add_argument("--evidence-rows-json", default="")
    parser.add_argument("--source-update-manifest", default="")
    parser.add_argument(
        "--extraction-results",
        action="append",
        default=[],
        help=(
            "Additional completed extraction JSONL used to finalize selected reports with no "
            "graph finding (for example meta-analysis v2 outputs). The routed outputs are always included."
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.check_active:
        result = validate_active_pointer_pair()
        print(f"Active release pointers agree: {result['run_id']}")
        return 0
    if args.check_public:
        result = validate_active_public_release()
        print(f"Active public release is complete: {result['run_id']}")
        return 0
    if args.refresh_public:
        result = refresh_public_artifacts(args.run_id)
        print(f"Refreshed public artifacts: {result['run_id']}")
        print(f"Public release ID: {result['release_id']}")
        print(f"Evidence release ID: {result['evidence_release_id']}")
        print(f"Active graph pointer: {ACTIVE_GRAPH_POINTER}")
        print(f"Public query artifact: {result['query_artifact']}")
        print(f"Public site bundle refreshed: {ROOT / 'dist'}")
        return 0
    if not args.run_id:
        raise SystemExit("--run-id is required unless a check mode is used")
    result = promote(args)
    print(f"Promoted routed release: {result['run_id']}")
    print(f"Release ID: {result['release_id']}")
    print(f"Normalized findings: {result['row_count']}")
    print(f"Active extraction pointer: {ACTIVE_EXTRACTION_POINTER}")
    print(f"Active graph pointer: {ACTIVE_GRAPH_POINTER}")
    print(f"Public query artifact: {result['query_artifact']}")
    print(f"Public site bundle refreshed: {ROOT / 'dist'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
