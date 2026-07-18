#!/usr/bin/env python3
"""Bundle the active public query artifact for a read-only service deployment."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ACTIVE_POINTER = ROOT / "data" / "processed" / "graph_payload_active.json"
DEFAULT_QUERY_RUNS_DIR = ROOT / "data" / "processed" / "query_api_runs"
DEFAULT_OUT_DIR = ROOT / "dist" / "query-api-bundle"
MANIFEST_SCHEMA = "psychedelics_kg_query_api_deploy_bundle_v1"
QUERY_MANIFEST_SCHEMA = "psychedelics_kg_public_query_manifest_v1"


def read_json_object(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def build_bundle(*, active_pointer: Path, query_runs_dir: Path, out_dir: Path) -> dict:
    active_pointer = active_pointer.resolve()
    query_runs_dir = query_runs_dir.resolve()
    out_dir = out_dir.resolve()
    pointer = read_json_object(active_pointer)
    run_id = str(pointer.get("run_id") or "").strip()
    release_id = str(pointer.get("release_id") or "").strip()
    if not run_id or not release_id:
        raise ValueError(f"Active graph pointer lacks run_id or release_id: {active_pointer}")
    source_query_dir = query_runs_dir / run_id
    query_manifest = read_json_object(source_query_dir / "manifest.json")
    if query_manifest.get("schema_version") != QUERY_MANIFEST_SCHEMA:
        raise ValueError(f"Unexpected query artifact schema: {source_query_dir}")
    if query_manifest.get("run_id") != run_id:
        raise ValueError("Active graph and query artifact run IDs differ")
    for key in ("database", "schema"):
        if not (source_query_dir / str(query_manifest.get(key) or "")).is_file():
            raise FileNotFoundError(f"Query artifact is missing {key}: {source_query_dir}")

    out_dir.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{out_dir.name}.", dir=out_dir.parent))
    try:
        processed = stage / "data" / "processed"
        target_query_dir = processed / "query_api_runs" / run_id
        processed.mkdir(parents=True)
        shutil.copy2(active_pointer, processed / "graph_payload_active.json")
        shutil.copytree(source_query_dir, target_query_dir)
        manifest = {
            "schema_version": MANIFEST_SCHEMA,
            "run_id": run_id,
            "release_id": release_id,
            "data_dir": "data",
            "active_pointer": "data/processed/graph_payload_active.json",
            "query_artifact": f"data/processed/query_api_runs/{run_id}",
            "row_counts": query_manifest.get("row_counts") or {},
        }
        write_json(stage / "bundle_manifest.json", manifest)

        backup = out_dir.with_name(f".{out_dir.name}.previous")
        shutil.rmtree(backup, ignore_errors=True)
        if out_dir.exists():
            out_dir.rename(backup)
        try:
            os.replace(stage, out_dir)
        except BaseException:
            if backup.exists() and not out_dir.exists():
                backup.rename(out_dir)
            raise
        shutil.rmtree(backup, ignore_errors=True)
        return manifest
    finally:
        shutil.rmtree(stage, ignore_errors=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--active-pointer", type=Path, default=DEFAULT_ACTIVE_POINTER)
    parser.add_argument("--query-runs-dir", type=Path, default=DEFAULT_QUERY_RUNS_DIR)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = build_bundle(
        active_pointer=args.active_pointer,
        query_runs_dir=args.query_runs_dir,
        out_dir=args.out_dir,
    )
    print(f"Built query API deployment bundle: {args.out_dir.resolve()}")
    print(f"Release ID: {result['release_id']}")
    print(f"Findings: {result['row_counts'].get('findings', 0)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
