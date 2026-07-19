#!/usr/bin/env python3
"""Publish the active sanitized query release to Cloudflare R2.

Release objects are immutable and content-verified. The small active pointer is
written only after every object is present, so a failed upload leaves the
previous remote release active.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import mimetypes
import os
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.query_api.config import (  # noqa: E402
    PUBLIC_QUERY_CONTRACT_KEY,
    R2Settings,
)
from services.query_api.r2_store import (  # noqa: E402
    R2_ACTIVE_SCHEMA_VERSION,
    ObjectStore,
    R2ObjectStore,
    canonical_json_bytes,
    release_object_prefix,
    sha256_bytes,
    sha256_file,
)


DEFAULT_ACTIVE_POINTER = ROOT / "data" / "processed" / "graph_payload_active.json"
DEFAULT_QUERY_RUNS_DIR = ROOT / "data" / "processed" / "query_api_runs"
QUERY_MANIFEST_SCHEMA = "psychedelics_kg_public_catalogue_manifest_v2"
IMMUTABLE_CACHE_CONTROL = "public, max-age=31536000, immutable"
ACTIVE_CACHE_CONTROL = "no-cache, max-age=0, must-revalidate"


@dataclass(frozen=True)
class LocalReleaseFile:
    logical_name: str
    path: Path
    relative_path: str
    sha256: str
    size: int


class ImmutableObjectConflict(RuntimeError):
    pass


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def read_json_object(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def safe_artifact_path(artifact_dir: Path, relative_path: str) -> Path:
    relative = Path(relative_path)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"Unsafe public artifact path: {relative_path}")
    path = (artifact_dir / relative).resolve()
    if artifact_dir.resolve() not in path.parents:
        raise ValueError(
            f"Public artifact path escapes its release directory: {relative_path}"
        )
    return path


def collect_release_files(artifact_dir: Path, manifest: dict) -> list[LocalReleaseFile]:
    artifact_dir = artifact_dir.resolve()
    values: list[tuple[str, str, int | None, str | None]] = [
        ("manifest", "manifest.json", None, None)
    ]
    entries = manifest.get("files") or {}
    if not isinstance(entries, dict):
        raise ValueError("Public query manifest files must be an object")
    for logical_name, entry in entries.items():
        if not isinstance(entry, dict):
            raise ValueError(f"Invalid public artifact entry: {logical_name}")
        values.append(
            (
                str(logical_name),
                str(entry.get("path") or ""),
                int(entry["bytes"]) if entry.get("bytes") is not None else None,
                str(entry.get("sha256") or "") or None,
            )
        )

    release_files: list[LocalReleaseFile] = []
    seen_paths: set[str] = set()
    for logical_name, relative_path, expected_size, expected_sha in values:
        if not relative_path:
            raise ValueError(f"Public artifact entry lacks a path: {logical_name}")
        if relative_path in seen_paths:
            raise ValueError(f"Duplicate public artifact path: {relative_path}")
        seen_paths.add(relative_path)
        path = safe_artifact_path(artifact_dir, relative_path)
        if not path.is_file():
            raise FileNotFoundError(f"Missing public release file: {path}")
        size = path.stat().st_size
        digest = sha256_file(path)
        if expected_size is not None and size != expected_size:
            raise ValueError(
                f"Public release size mismatch for {relative_path}: {size} != {expected_size}"
            )
        if expected_sha is not None and digest != expected_sha:
            raise ValueError(f"Public release checksum mismatch for {relative_path}")
        release_files.append(
            LocalReleaseFile(
                logical_name=logical_name,
                path=path,
                relative_path=relative_path,
                sha256=digest,
                size=size,
            )
        )
    return release_files


def content_type_for(path: Path) -> str:
    if path.suffix == ".duckdb":
        return "application/vnd.duckdb"
    if path.suffix == ".parquet":
        return "application/vnd.apache.parquet"
    return mimetypes.guess_type(path.name)[0] or "application/octet-stream"


def upload_immutable_file(
    store: ObjectStore,
    *,
    key: str,
    release_file: LocalReleaseFile,
) -> str:
    existing = store.head(key)
    if existing is not None:
        if (
            existing.size == release_file.size
            and existing.metadata.get("sha256") == release_file.sha256
        ):
            return "existing"
        raise ImmutableObjectConflict(
            f"Remote immutable object differs from this release: {key}"
        )

    downloadable = (
        release_file.logical_name == "database"
        or release_file.logical_name.startswith("table:")
    )
    disposition = (
        f'attachment; filename="{release_file.path.name}"' if downloadable else ""
    )
    store.upload_file(
        key,
        release_file.path,
        sha256=release_file.sha256,
        content_type=content_type_for(release_file.path),
        cache_control=IMMUTABLE_CACHE_CONTROL,
        content_disposition=disposition,
    )
    uploaded = store.head(key)
    if uploaded is None:
        raise RuntimeError(f"Uploaded R2 object is not readable: {key}")
    if (
        uploaded.size != release_file.size
        or uploaded.metadata.get("sha256") != release_file.sha256
    ):
        raise RuntimeError(f"Uploaded R2 object failed verification: {key}")
    return "uploaded"


def publish_active_query_release(
    *,
    store: ObjectStore,
    settings: R2Settings,
    active_pointer_path: Path = DEFAULT_ACTIVE_POINTER,
    query_runs_dir: Path = DEFAULT_QUERY_RUNS_DIR,
    expected_run_id: str = "",
    published_at: str | None = None,
    write_legacy_active_alias: bool = False,
) -> dict:
    pointer = read_json_object(active_pointer_path)
    run_id = str(pointer.get("run_id") or "").strip()
    evidence_release_id = str(pointer.get("release_id") or "").strip()
    release_id = str(pointer.get("public_release_id") or evidence_release_id).strip()
    if not run_id or not release_id or not evidence_release_id:
        raise ValueError(
            f"Active graph pointer lacks run_id or release_id: {active_pointer_path}"
        )
    if expected_run_id and run_id != expected_run_id:
        raise ValueError(f"Active run is {run_id}, not requested run {expected_run_id}")

    artifact_dir = (query_runs_dir / run_id).resolve()
    manifest = read_json_object(artifact_dir / "manifest.json")
    if manifest.get("schema_version") != QUERY_MANIFEST_SCHEMA:
        raise ValueError(f"Unexpected public query manifest schema: {artifact_dir}")
    if manifest.get("run_id") != run_id:
        raise ValueError("Active graph and public query artifact run IDs differ")
    if manifest.get("release_id") != release_id:
        raise ValueError(
            "Active graph pointer and public query manifest release IDs differ. "
            "Promote the complete release before publishing to R2."
        )
    if manifest.get("evidence_release_id") != evidence_release_id:
        raise ValueError(
            "Active graph pointer and public query manifest evidence release IDs differ."
        )

    release_files = collect_release_files(artifact_dir, manifest)
    object_prefix = release_object_prefix(
        settings, run_id=run_id, release_id=release_id
    )
    remote_files: dict[str, dict] = {}
    remote_manifest: dict | None = None
    uploaded_count = 0
    existing_count = 0
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

    if (
        remote_manifest is None
    ):  # pragma: no cover - collect_release_files always adds it
        raise RuntimeError("Public query release has no manifest")

    active = {
        "schema_version": R2_ACTIVE_SCHEMA_VERSION,
        "contract_key": PUBLIC_QUERY_CONTRACT_KEY,
        "query_manifest_schema": QUERY_MANIFEST_SCHEMA,
        "published_at": published_at or now_utc(),
        "run_id": run_id,
        "release_id": release_id,
        "evidence_release_id": evidence_release_id,
        "object_prefix": object_prefix,
        "manifest": remote_manifest,
        "files": remote_files,
        "row_counts": manifest.get("row_counts") or {},
        "public_schema_version": manifest.get("public_schema_version") or "",
    }
    active_bytes = canonical_json_bytes(active)
    active_sha = sha256_bytes(active_bytes)
    store.put_bytes(
        settings.active_key,
        active_bytes,
        sha256=active_sha,
        content_type="application/json",
        cache_control=ACTIVE_CACHE_CONTROL,
    )
    if store.get_bytes(settings.active_key) != active_bytes:
        raise RuntimeError(
            "R2 active release pointer failed read-after-write verification"
        )
    if write_legacy_active_alias:
        store.put_bytes(
            settings.legacy_active_key,
            active_bytes,
            sha256=active_sha,
            content_type="application/json",
            cache_control=ACTIVE_CACHE_CONTROL,
        )
        if store.get_bytes(settings.legacy_active_key) != active_bytes:
            raise RuntimeError("Legacy R2 active release alias failed verification")
    return {
        **active,
        "active_key": settings.active_key,
        "uploaded_count": uploaded_count,
        "existing_count": existing_count,
    }


def trigger_deploy_hook(url: str) -> None:
    request = urllib.request.Request(url, data=b"", method="POST")
    with urllib.request.urlopen(request, timeout=30) as response:
        if int(response.status) >= 300:
            raise RuntimeError(f"Deployment hook returned HTTP {response.status}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--active-pointer", type=Path, default=DEFAULT_ACTIVE_POINTER)
    parser.add_argument("--query-runs-dir", type=Path, default=DEFAULT_QUERY_RUNS_DIR)
    parser.add_argument("--run-id", default="", help="Require this run to be active")
    parser.add_argument(
        "--deploy-hook-url",
        default=os.environ.get("PKG_DEPLOY_HOOK_URL", ""),
        help="Optional container-platform deploy hook called after activation",
    )
    parser.add_argument("--no-deploy-hook", action="store_true")
    parser.add_argument(
        "--write-legacy-active-alias",
        action="store_true",
        help="Also update query-api/active.json during the catalogue-v2 migration.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    settings = R2Settings.from_env(required=True)
    assert settings is not None
    result = publish_active_query_release(
        store=R2ObjectStore(settings),
        settings=settings,
        active_pointer_path=args.active_pointer.resolve(),
        query_runs_dir=args.query_runs_dir.resolve(),
        expected_run_id=args.run_id.strip(),
        write_legacy_active_alias=args.write_legacy_active_alias,
    )
    print(f"Published R2 query release: {result['release_id']}")
    print(f"Active object: {result['active_key']}")
    print(
        f"Release files: {result['uploaded_count']} uploaded, "
        f"{result['existing_count']} already present"
    )
    if args.deploy_hook_url and not args.no_deploy_hook:
        trigger_deploy_hook(args.deploy_hook_url)
        print("Triggered API deployment hook")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
