#!/usr/bin/env python3
"""Delete superseded local and R2 release artifacts.

The command is dry-run by default. It refuses to prune unless the active
browser, API, extraction, KG, and local payload artifacts form one coherent
release. Only objects and directories outside the active release are eligible.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
import json
import os
from pathlib import Path
import shutil
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.query_api.config import R2Settings, normalize_r2_prefix  # noqa: E402
from services.query_api.r2_store import R2ObjectStore  # noqa: E402


ACTIVE_GRAPH_POINTER = ROOT / "data/processed/graph_payload_active.json"
ACTIVE_EXTRACTION_POINTER = (
    ROOT / "data/processed/extraction/active_routed_run.json"
)
LOCAL_RELEASE_ROOTS = {
    "graph": ROOT / "data/processed/graph_payload_runs",
    "kg": ROOT / "data/processed/kg_routed_runs",
    "query_api": ROOT / "data/processed/query_api_runs",
    "extraction": ROOT / "data/processed/extraction/routed_runs",
}
LOCAL_RELEASE_STAGING = ROOT / "data/processed/release_staging"


@dataclass(frozen=True)
class PruneResult:
    label: str
    active_run_id: str
    removed_count: int
    removed_bytes: int
    kept_count: int
    executed: bool


def read_json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def object_prefix_identity(pointer: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(pointer.get("run_id") or "").strip(),
        str(pointer.get("release_id") or "").strip(),
        str(pointer.get("evidence_release_id") or "").strip(),
    )


def require_matching_remote_releases(
    browser_pointer: dict[str, Any],
    query_pointer: dict[str, Any],
) -> tuple[str, str, str]:
    browser_identity = object_prefix_identity(browser_pointer)
    query_identity = object_prefix_identity(query_pointer)
    if not all(browser_identity):
        raise ValueError("Browser R2 active pointer lacks release identity")
    if browser_identity != query_identity:
        raise ValueError(
            "Browser and API R2 active pointers do not identify the same release"
        )
    return browser_identity


def referenced_remote_keys(pointer: dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    active_manifest = pointer.get("active_manifest")
    if isinstance(active_manifest, str) and active_manifest:
        keys.add(active_manifest)
    manifest = pointer.get("manifest")
    if isinstance(manifest, dict) and manifest.get("key"):
        keys.add(str(manifest["key"]))
    for mapping_name in (
        "active_graph_bootstraps",
        "active_dashboard_bootstraps",
        "active_detail_bootstraps",
        "methods",
        "files",
    ):
        mapping = pointer.get(mapping_name)
        if not isinstance(mapping, dict):
            continue
        for value in mapping.values():
            if isinstance(value, str) and value:
                keys.add(value)
            elif isinstance(value, dict) and value.get("key"):
                keys.add(str(value["key"]))
    return keys


def list_remote_keys(client: Any, *, bucket: str, prefix: str) -> list[dict]:
    rows: list[dict] = []
    token = ""
    while True:
        arguments: dict[str, Any] = {"Bucket": bucket, "Prefix": prefix}
        if token:
            arguments["ContinuationToken"] = token
        response = client.list_objects_v2(**arguments)
        rows.extend(response.get("Contents") or [])
        if not response.get("IsTruncated"):
            return rows
        token = str(response.get("NextContinuationToken") or "")
        if not token:
            raise RuntimeError("R2 object listing was truncated without a token")


def verify_remote_active_release(
    store: R2ObjectStore,
    pointer: dict[str, Any],
    *,
    releases_prefix: str,
) -> str:
    active_prefix = str(pointer.get("object_prefix") or "").strip().rstrip("/")
    if not active_prefix.startswith(releases_prefix):
        raise ValueError(f"Unsafe active R2 release prefix: {active_prefix!r}")
    referenced = referenced_remote_keys(pointer)
    if not referenced:
        raise ValueError("R2 active pointer contains no referenced release objects")
    outside = sorted(
        key for key in referenced if not key.startswith(f"{active_prefix}/")
    )
    if outside:
        raise ValueError(
            "R2 active pointer references objects outside its release: "
            + ", ".join(outside)
        )
    missing = sorted(key for key in referenced if store.head(key) is None)
    if missing:
        raise FileNotFoundError(
            "R2 active release is incomplete: " + ", ".join(missing)
        )
    return active_prefix


def prune_remote_release_history(
    *,
    label: str,
    store: R2ObjectStore,
    settings: R2Settings,
    active_key: str,
    releases_prefix: str,
    execute: bool,
) -> tuple[PruneResult, dict[str, Any]]:
    active_bytes = store.get_bytes(active_key)
    active = json.loads(active_bytes)
    if not isinstance(active, dict):
        raise ValueError(f"{label} R2 active pointer must be an object")
    active_prefix = verify_remote_active_release(
        store,
        active,
        releases_prefix=releases_prefix,
    )
    objects = list_remote_keys(
        store.client,
        bucket=settings.bucket,
        prefix=releases_prefix,
    )
    stale = [
        row
        for row in objects
        if not str(row.get("Key") or "").startswith(f"{active_prefix}/")
    ]
    if execute:
        for start in range(0, len(stale), 1000):
            batch = stale[start : start + 1000]
            if not batch:
                continue
            response = store.client.delete_objects(
                Bucket=settings.bucket,
                Delete={
                    "Objects": [{"Key": str(row["Key"])} for row in batch],
                    "Quiet": False,
                },
            )
            if response.get("Errors"):
                raise RuntimeError(
                    f"{label} R2 deletion failed: {response['Errors']}"
                )
        remaining = list_remote_keys(
            store.client,
            bucket=settings.bucket,
            prefix=releases_prefix,
        )
        unexpected = [
            str(row.get("Key") or "")
            for row in remaining
            if not str(row.get("Key") or "").startswith(f"{active_prefix}/")
        ]
        if unexpected:
            raise RuntimeError(
                f"{label} R2 stale release objects remain: {unexpected}"
            )
        if store.get_bytes(active_key) != active_bytes:
            raise RuntimeError(
                f"{label} R2 active pointer changed during history pruning"
            )
        verify_remote_active_release(
            store,
            active,
            releases_prefix=releases_prefix,
        )
    return (
        PruneResult(
            label=label,
            active_run_id=str(active.get("run_id") or ""),
            removed_count=len(stale),
            removed_bytes=sum(int(row.get("Size") or 0) for row in stale),
            kept_count=len(objects) - len(stale),
            executed=execute,
        ),
        active,
    )


def path_size(path: Path) -> int:
    if path.is_symlink() or path.is_file():
        return path.lstat().st_size
    return sum(
        child.stat().st_size
        for child in path.rglob("*")
        if child.is_file() and not child.is_symlink()
    )


def require_active_run_path(
    value: object,
    *,
    release_root: Path,
    run_id: str,
    label: str,
    file_required: bool,
) -> Path:
    path = Path(str(value or ""))
    if not path.is_absolute():
        path = ROOT / path
    path = path.resolve()
    active_root = (release_root / run_id).resolve()
    if path != active_root and active_root not in path.parents:
        raise ValueError(
            f"{label} is not self-contained under the active run: {path}"
        )
    exists = path.is_file() if file_required else path.is_dir()
    if not exists:
        kind = "file" if file_required else "directory"
        raise FileNotFoundError(f"Missing active {label} {kind}: {path}")
    return path


def validate_local_active_release() -> tuple[str, str]:
    graph = read_json_object(ACTIVE_GRAPH_POINTER)
    extraction = read_json_object(ACTIVE_EXTRACTION_POINTER)
    run_id = str(graph.get("run_id") or "").strip()
    evidence_release_id = str(graph.get("release_id") or "").strip()
    if not run_id or not evidence_release_id:
        raise ValueError("Local graph pointer lacks release identity")
    if (
        str(extraction.get("run_id") or "").strip() != run_id
        or str(extraction.get("release_id") or "").strip()
        != evidence_release_id
    ):
        raise ValueError(
            "Local graph and extraction pointers do not identify the same release"
        )

    require_active_run_path(
        graph.get("active_manifest"),
        release_root=LOCAL_RELEASE_ROOTS["graph"],
        run_id=run_id,
        label="graph manifest",
        file_required=True,
    )
    require_active_run_path(
        graph.get("kg_dir"),
        release_root=LOCAL_RELEASE_ROOTS["kg"],
        run_id=run_id,
        label="KG",
        file_required=False,
    )
    require_active_run_path(
        extraction.get("outputs_jsonl"),
        release_root=LOCAL_RELEASE_ROOTS["extraction"],
        run_id=run_id,
        label="combined extraction outputs",
        file_required=True,
    )
    require_active_run_path(
        extraction.get("evidence_rows_json"),
        release_root=LOCAL_RELEASE_ROOTS["extraction"],
        run_id=run_id,
        label="combined evidence rows",
        file_required=True,
    )
    query_manifest_path = require_active_run_path(
        LOCAL_RELEASE_ROOTS["query_api"] / run_id / "manifest.json",
        release_root=LOCAL_RELEASE_ROOTS["query_api"],
        run_id=run_id,
        label="query API manifest",
        file_required=True,
    )
    query_manifest = read_json_object(query_manifest_path)
    expected_public_release_id = str(
        graph.get("public_release_id") or evidence_release_id
    ).strip()
    if (
        str(query_manifest.get("run_id") or "").strip() != run_id
        or str(query_manifest.get("release_id") or "").strip()
        != expected_public_release_id
        or str(query_manifest.get("evidence_release_id") or "").strip()
        != evidence_release_id
    ):
        raise ValueError(
            "Local query API manifest does not match the active graph release"
        )
    return run_id, evidence_release_id


def remove_local_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    else:
        shutil.rmtree(path)


def prune_local_release_history(*, execute: bool) -> PruneResult:
    run_id, _release_id = validate_local_active_release()
    stale: list[Path] = []
    kept_count = 0
    for root in LOCAL_RELEASE_ROOTS.values():
        root.mkdir(parents=True, exist_ok=True)
        for child in root.iterdir():
            if child.name == run_id:
                kept_count += 1
            else:
                stale.append(child)
    LOCAL_RELEASE_STAGING.mkdir(parents=True, exist_ok=True)
    stale.extend(LOCAL_RELEASE_STAGING.iterdir())
    removed_bytes = sum(path_size(path) for path in stale)
    if execute:
        for path in stale:
            remove_local_path(path)
        validate_local_active_release()
    return PruneResult(
        label="local",
        active_run_id=run_id,
        removed_count=len(stale),
        removed_bytes=removed_bytes,
        kept_count=kept_count,
        executed=execute,
    )


def format_bytes(value: int) -> str:
    amount = float(value)
    for suffix in ("B", "KiB", "MiB", "GiB", "TiB"):
        if amount < 1024 or suffix == "TiB":
            return f"{amount:.2f} {suffix}"
        amount /= 1024
    return f"{amount:.2f} TiB"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--local", action="store_true")
    parser.add_argument("--remote", action="store_true")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Perform deletions. Without this flag the command only reports.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.local and not args.remote:
        raise SystemExit("Choose --local, --remote, or both.")

    results: list[PruneResult] = []
    if args.remote:
        browser_settings = R2Settings.from_env(
            required=True,
            env_prefix="PKG_R2",
            default_object_prefix="browser",
        )
        query_settings = R2Settings.from_env(
            required=True,
            env_prefix="PKG_API_R2",
            default_object_prefix="query-api",
        )
        assert browser_settings is not None and query_settings is not None
        browser_settings = replace(
            browser_settings,
            prefix=normalize_r2_prefix(
                os.environ.get("PKG_R2_BROWSER_PREFIX", "browser"),
                variable_name="PKG_R2_BROWSER_PREFIX",
            ),
        )
        browser_store = R2ObjectStore(browser_settings)
        query_store = R2ObjectStore(query_settings)
        browser_active_bytes = browser_store.get_bytes(
            f"{browser_settings.prefix}/active.json"
        )
        query_active_bytes = query_store.get_bytes(query_settings.active_key)
        browser_active = json.loads(browser_active_bytes)
        query_active = json.loads(query_active_bytes)
        require_matching_remote_releases(browser_active, query_active)

        browser_result, _ = prune_remote_release_history(
            label="browser_r2",
            store=browser_store,
            settings=browser_settings,
            active_key=f"{browser_settings.prefix}/active.json",
            releases_prefix=f"{browser_settings.prefix}/releases/",
            execute=args.execute,
        )
        query_result, _ = prune_remote_release_history(
            label="query_api_r2",
            store=query_store,
            settings=query_settings,
            active_key=query_settings.active_key,
            releases_prefix=f"{query_settings.prefix}/releases/",
            execute=args.execute,
        )
        results.extend((browser_result, query_result))
    if args.local:
        results.append(prune_local_release_history(execute=args.execute))

    mode = "deleted" if args.execute else "would delete"
    for result in results:
        print(
            f"{result.label}: {mode} {result.removed_count} inactive artifacts "
            f"({format_bytes(result.removed_bytes)}); kept "
            f"{result.kept_count} artifacts for {result.active_run_id}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
