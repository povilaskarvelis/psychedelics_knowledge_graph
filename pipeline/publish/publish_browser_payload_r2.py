#!/usr/bin/env python3
"""Publish the active public website data release to Cloudflare R2.

Release objects are immutable and checksum-verified. The stable browser pointer
is replaced only after every file in the release is readable from R2.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import replace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.publish.publish_query_api_r2 import (  # noqa: E402
    ACTIVE_CACHE_CONTROL,
    IMMUTABLE_CACHE_CONTROL,
    LocalReleaseFile,
    now_utc,
    read_json_object,
    upload_immutable_file,
)
from pipeline.kg.graph_view_contract import graph_view_ids  # noqa: E402
from services.query_api.config import R2Settings, normalize_r2_prefix  # noqa: E402
from services.query_api.r2_store import (  # noqa: E402
    ObjectStore,
    R2ObjectStore,
    canonical_json_bytes,
    release_object_prefix,
    sha256_bytes,
    sha256_file,
)


DEFAULT_ACTIVE_POINTER = ROOT / "data" / "processed" / "graph_payload_active.json"
DEFAULT_BROWSER_RUNS_DIR = ROOT / "data" / "processed" / "graph_payload_runs"
DEFAULT_METHODS_VIEWS_DIR = ROOT / "data" / "kg" / "views"
BROWSER_ACTIVE_SCHEMA_VERSION = "psychedelics_kg_browser_r2_active_v1"
BROWSER_POINTER_SCHEMA_VERSION = "route_native_evidence_payload_active_v1"
BROWSER_MANIFEST_SCHEMA_VERSION = "route_native_evidence_manifest_v1"
METHODS_RELEASE_FILES = {
    "pipeline_status": "pipeline_status_graph.json",
    "bibliography": "methods_bibliography.json",
    "graph_inclusion_dispositions": "graph_inclusion_dispositions.json",
}
DETAIL_VIEW_KEYS = set(graph_view_ids())


def safe_payload_path(browser_runs_dir: Path, relative_path: str) -> Path:
    relative = Path(relative_path)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"Unsafe browser payload path: {relative_path}")
    runs_root = browser_runs_dir.resolve()
    repository_root = runs_root.parents[2]
    path = (repository_root / relative).resolve()
    if runs_root not in path.parents:
        raise ValueError(f"Browser payload path is outside its runs directory: {relative_path}")
    return path


def collect_browser_release_files(
    *,
    browser_runs_dir: Path,
    manifest_path: Path,
    manifest: dict,
) -> list[LocalReleaseFile]:
    entries = manifest.get("files") or {}
    if not isinstance(entries, dict) or not entries:
        raise ValueError("Browser payload manifest files must be a non-empty object")

    files = [
        LocalReleaseFile(
            logical_name="manifest",
            path=manifest_path,
            relative_path=manifest_path.name,
            sha256=sha256_file(manifest_path),
            size=manifest_path.stat().st_size,
        )
    ]
    seen_names = {manifest_path.name}
    for logical_name, entry in entries.items():
        if not isinstance(entry, dict):
            raise ValueError(f"Invalid browser payload entry: {logical_name}")
        relative_path = str(entry.get("path") or "")
        path = safe_payload_path(browser_runs_dir, relative_path)
        if not path.is_file():
            raise FileNotFoundError(f"Missing browser payload file: {path}")
        if path.name in seen_names:
            raise ValueError(f"Duplicate browser payload filename: {path.name}")
        seen_names.add(path.name)
        size = path.stat().st_size
        digest = sha256_file(path)
        if size != int(entry.get("bytes", -1)):
            raise ValueError(f"Browser payload size mismatch for {relative_path}")
        if digest != str(entry.get("sha256") or "").casefold():
            raise ValueError(f"Browser payload checksum mismatch for {relative_path}")
        files.append(
            LocalReleaseFile(
                logical_name=str(logical_name),
                path=path,
                relative_path=path.name,
                sha256=digest,
                size=size,
            )
        )
    return files


def collect_methods_release_files(
    methods_views_dir: Path,
    *,
    expected_run_id: str,
    expected_release_id: str,
) -> list[LocalReleaseFile]:
    """Collect every generated dataset used by, or published with, Methods."""
    views_root = methods_views_dir.resolve()
    files: list[LocalReleaseFile] = []
    for public_name, filename in METHODS_RELEASE_FILES.items():
        path = (views_root / filename).resolve()
        if path.parent != views_root:
            raise ValueError(f"Unsafe Methods data path: {filename}")
        if not path.is_file():
            raise FileNotFoundError(f"Missing required Methods data file: {path}")
        payload = read_json_object(path)
        if str(payload.get("run_id") or "").strip() != expected_run_id:
            raise ValueError(f"Methods data run ID mismatch: {path}")
        if str(payload.get("release_id") or "").strip() != expected_release_id:
            raise ValueError(f"Methods data release ID mismatch: {path}")
        files.append(
            LocalReleaseFile(
                logical_name=f"methods:{public_name}",
                path=path,
                relative_path=filename,
                sha256=sha256_file(path),
                size=path.stat().st_size,
            )
        )
    return files


def remote_path_map(pointer: dict, remote_files: dict[str, dict], prefix: str) -> dict:
    result: dict[str, str] = {}
    mapping = pointer.get(prefix) or {}
    expected_sources = {"primary", "meta_analyses", "reviews"}
    if not isinstance(mapping, dict) or set(mapping) != expected_sources:
        raise ValueError(f"Browser pointer {prefix} must contain {sorted(expected_sources)}")
    for source_key, local_path in mapping.items():
        filename = Path(str(local_path)).name
        logical_prefix = {
            "active_graph_bootstraps": "graph",
            "active_dashboard_bootstraps": "dashboard",
            "active_detail_bootstraps": "detail",
        }[prefix]
        logical_name = f"{logical_prefix}:{source_key}"
        entry = remote_files.get(logical_name) or {}
        if Path(str(entry.get("path") or "")).name != filename:
            raise ValueError(f"Browser manifest does not match {prefix}.{source_key}")
        result[str(source_key)] = str(entry["key"])
    return result


def remote_detail_view_path_map(pointer: dict, remote_files: dict[str, dict]) -> dict:
    prefix = "active_detail_bootstraps_by_view"
    mapping = pointer.get(prefix)
    if mapping is None:
        return {}
    expected_sources = {"primary", "meta_analyses", "reviews"}
    if not isinstance(mapping, dict) or set(mapping) != expected_sources:
        raise ValueError(f"Browser pointer {prefix} must contain {sorted(expected_sources)}")

    result: dict[str, dict[str, str]] = {}
    for source_key, source_views in mapping.items():
        if not isinstance(source_views, dict) or set(source_views) != DETAIL_VIEW_KEYS:
            raise ValueError(
                f"Browser pointer {prefix}.{source_key} must contain {sorted(DETAIL_VIEW_KEYS)}"
            )
        result[source_key] = {}
        for view_key, local_path in source_views.items():
            filename = Path(str(local_path)).name
            logical_name = f"detail_view:{source_key}:{view_key}"
            entry = remote_files.get(logical_name) or {}
            if Path(str(entry.get("path") or "")).name != filename:
                raise ValueError(f"Browser manifest does not match {prefix}.{source_key}.{view_key}")
            result[source_key][view_key] = str(entry["key"])
    return result


def remote_methods_map(remote_files: dict[str, dict]) -> dict[str, str]:
    result: dict[str, str] = {}
    for public_name, filename in METHODS_RELEASE_FILES.items():
        logical_name = f"methods:{public_name}"
        entry = remote_files.get(logical_name) or {}
        if Path(str(entry.get("path") or "")).name != filename:
            raise ValueError(f"Public data release is missing {logical_name}")
        result[public_name] = str(entry["key"])
    return result


def publish_active_browser_release(
    *,
    store: ObjectStore,
    settings: R2Settings,
    active_pointer_path: Path = DEFAULT_ACTIVE_POINTER,
    browser_runs_dir: Path = DEFAULT_BROWSER_RUNS_DIR,
    methods_views_dir: Path = DEFAULT_METHODS_VIEWS_DIR,
    browser_prefix: str = "browser",
    expected_run_id: str = "",
    published_at: str | None = None,
) -> dict:
    pointer = read_json_object(active_pointer_path)
    if pointer.get("schema_version") != BROWSER_POINTER_SCHEMA_VERSION:
        raise ValueError(f"Unexpected active browser pointer schema: {active_pointer_path}")
    run_id = str(pointer.get("run_id") or "").strip()
    evidence_release_id = str(pointer.get("release_id") or "").strip()
    release_id = str(pointer.get("public_release_id") or "").strip()
    if not run_id or not evidence_release_id or not release_id:
        raise ValueError("Active browser pointer lacks run_id or release identifiers")
    if expected_run_id and run_id != expected_run_id:
        raise ValueError(f"Active run is {run_id}, not requested run {expected_run_id}")

    manifest_path = (browser_runs_dir / run_id / "graph_payload_manifest.json").resolve()
    manifest = read_json_object(manifest_path)
    if manifest.get("schema_version") != BROWSER_MANIFEST_SCHEMA_VERSION:
        raise ValueError(f"Unexpected browser payload manifest schema: {manifest_path}")
    if manifest.get("release_id") != release_id:
        raise ValueError("Active browser pointer and manifest release IDs differ")
    if manifest.get("evidence_release_id") != evidence_release_id:
        raise ValueError("Active browser pointer and manifest evidence release IDs differ")
    repository_root = browser_runs_dir.resolve().parents[2]
    if (repository_root / str(pointer.get("active_manifest") or "")).resolve() != manifest_path:
        raise ValueError("Active browser pointer names a different manifest")

    prefix = normalize_r2_prefix(browser_prefix)
    browser_settings = replace(settings, prefix=prefix)
    object_prefix = release_object_prefix(
        browser_settings, run_id=run_id, release_id=release_id
    )
    release_files = collect_browser_release_files(
        browser_runs_dir=browser_runs_dir,
        manifest_path=manifest_path,
        manifest=manifest,
    )
    release_files.extend(
        collect_methods_release_files(
            methods_views_dir,
            expected_run_id=run_id,
            expected_release_id=evidence_release_id,
        )
    )
    relative_names = [release_file.relative_path for release_file in release_files]
    if len(relative_names) != len(set(relative_names)):
        raise ValueError("Public data release contains duplicate filenames")
    uploaded_count = 0
    existing_count = 0
    remote_files: dict[str, dict] = {}
    remote_manifest: dict | None = None
    for release_file in release_files:
        key = f"{object_prefix}/{release_file.relative_path}"
        status = upload_immutable_file(store, key=key, release_file=release_file)
        uploaded_count += status == "uploaded"
        existing_count += status == "existing"
        entry = {
            "key": key,
            "path": release_file.relative_path,
            "bytes": release_file.size,
            "sha256": release_file.sha256,
        }
        if release_file.logical_name == "manifest":
            remote_manifest = entry
        else:
            remote_files[release_file.logical_name] = entry
    if remote_manifest is None:  # pragma: no cover - always collected above
        raise RuntimeError("Browser release has no manifest")

    detail_view_paths = remote_detail_view_path_map(pointer, remote_files)
    active = {
        "schema_version": BROWSER_ACTIVE_SCHEMA_VERSION,
        "published_at": published_at or now_utc(),
        "run_id": run_id,
        "release_id": release_id,
        "evidence_release_id": evidence_release_id,
        "object_prefix": object_prefix,
        "active_manifest": remote_manifest["key"],
        "active_graph_bootstraps": remote_path_map(
            pointer, remote_files, "active_graph_bootstraps"
        ),
        "active_dashboard_bootstraps": remote_path_map(
            pointer, remote_files, "active_dashboard_bootstraps"
        ),
        "active_detail_bootstraps": remote_path_map(
            pointer, remote_files, "active_detail_bootstraps"
        ),
        "methods": remote_methods_map(remote_files),
        "files": remote_files,
    }
    if detail_view_paths:
        active["active_detail_bootstraps_by_view"] = detail_view_paths
    active_bytes = canonical_json_bytes(active)
    active_sha = sha256_bytes(active_bytes)
    active_key = f"{prefix}/active.json"
    store.put_bytes(
        active_key,
        active_bytes,
        sha256=active_sha,
        content_type="application/json",
        cache_control=ACTIVE_CACHE_CONTROL,
    )
    if store.get_bytes(active_key) != active_bytes:
        raise RuntimeError("R2 browser pointer failed read-after-write verification")
    return {
        **active,
        "active_key": active_key,
        "uploaded_count": uploaded_count,
        "existing_count": existing_count,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--active-pointer", type=Path, default=DEFAULT_ACTIVE_POINTER)
    parser.add_argument("--browser-runs-dir", type=Path, default=DEFAULT_BROWSER_RUNS_DIR)
    parser.add_argument("--methods-views-dir", type=Path, default=DEFAULT_METHODS_VIEWS_DIR)
    parser.add_argument("--browser-prefix", default=os.environ.get("PKG_R2_BROWSER_PREFIX", "browser"))
    parser.add_argument("--run-id", default="", help="Require this run to be active")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    # PKG_R2_* is reserved for the public browser bucket. The API runtime uses
    # the separate PKG_API_R2_* namespace and must never be published here.
    settings = R2Settings.from_env(
        required=True,
        env_prefix="PKG_R2",
        default_object_prefix="browser",
    )
    assert settings is not None
    result = publish_active_browser_release(
        store=R2ObjectStore(settings),
        settings=settings,
        active_pointer_path=args.active_pointer.resolve(),
        browser_runs_dir=args.browser_runs_dir.resolve(),
        methods_views_dir=args.methods_views_dir.resolve(),
        browser_prefix=args.browser_prefix,
        expected_run_id=args.run_id.strip(),
    )
    print(f"Published R2 browser release: {result['release_id']}")
    print(f"Active object: {result['active_key']}")
    print(
        f"Release files: {result['uploaded_count']} uploaded, "
        f"{result['existing_count']} already present"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
