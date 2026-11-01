#!/usr/bin/env python3
"""Delete superseded local and R2 release artifacts under a retention policy.

Kept in the public browser bucket: the live release, the release published just
before it (pages opened before an update keep loading), and the last release of
every evidence release, each with its archived site copy (release_archive.py).
Kept in the private API bucket: the live release and the one before it.

Kept locally: the active run, the run published before it, runs that contain a
``.keep`` file, and runs that were never published unless they were last changed
before the active run was promoted and more than ``--candidate-grace-days`` ago.
Release history (release_history.py) tells published runs from unpublished ones.

The command is dry-run by default and prints every artifact it keeps or deletes
with the reason. It refuses to prune unless the active browser, API, extraction,
KG, and local payload artifacts form one coherent release.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
import json
import os
from pathlib import Path
import shutil
import sys
import time
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.publish.release_archive import (  # noqa: E402
    RetentionPlan,
    archive_root,
    archive_slug_of_key,
    parse_timestamp,
    plan_archive_retention,
    read_archive_index,
    release_prefix_of_key,
    write_archive_index,
)
from pipeline.publish.release_history import (  # noqa: E402
    RELEASE_HISTORY,
    previous_run_id,
    promotion_time,
    read_release_history,
)
from services.query_api.config import R2Settings, normalize_r2_prefix  # noqa: E402
from services.query_api.r2_store import R2ObjectStore, release_object_prefix  # noqa: E402


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
KEEP_MARKER = ".keep"
DEFAULT_CANDIDATE_GRACE_DAYS = 7


@dataclass(frozen=True)
class PruneResult:
    label: str
    active_run_id: str
    removed_count: int
    removed_bytes: int
    kept_count: int
    executed: bool


@dataclass(frozen=True)
class LocalDecision:
    name: str
    paths: tuple[Path, ...]
    reason: str
    size: int


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


def delete_remote_objects(store: R2ObjectStore, *, bucket: str, rows: list[dict], label: str) -> None:
    for start in range(0, len(rows), 1000):
        batch = rows[start : start + 1000]
        if not batch:
            continue
        response = store.client.delete_objects(
            Bucket=bucket,
            Delete={
                "Objects": [{"Key": str(row["Key"])} for row in batch],
                "Quiet": False,
            },
        )
        if response.get("Errors"):
            raise RuntimeError(f"{label} R2 deletion failed: {response['Errors']}")


def prune_remote_releases(
    *,
    label: str,
    store: R2ObjectStore,
    settings: R2Settings,
    active_key: str,
    releases_prefix: str,
    keep_prefixes: set[str],
    execute: bool,
) -> tuple[PruneResult, dict[str, Any], list[dict]]:
    """Delete release prefixes that are neither active nor in ``keep_prefixes``."""
    active_bytes = store.get_bytes(active_key)
    active = json.loads(active_bytes)
    if not isinstance(active, dict):
        raise ValueError(f"{label} R2 active pointer must be an object")
    active_prefix = verify_remote_active_release(
        store,
        active,
        releases_prefix=releases_prefix,
    )
    keep = {active_prefix, *keep_prefixes}
    objects = list_remote_keys(
        store.client,
        bucket=settings.bucket,
        prefix=releases_prefix,
    )
    stale = [
        row
        for row in objects
        if release_prefix_of_key(str(row.get("Key") or ""), releases_prefix) not in keep
    ]
    if execute:
        delete_remote_objects(store, bucket=settings.bucket, rows=stale, label=label)
        remaining = list_remote_keys(
            store.client,
            bucket=settings.bucket,
            prefix=releases_prefix,
        )
        unexpected = [
            str(row.get("Key") or "")
            for row in remaining
            if release_prefix_of_key(str(row.get("Key") or ""), releases_prefix) not in keep
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
        stale,
    )


def list_archived_objects(store: R2ObjectStore, *, settings: R2Settings, browser_prefix: str) -> list[dict]:
    objects = list_remote_keys(
        store.client,
        bucket=settings.bucket,
        prefix=f"{archive_root(browser_prefix)}/",
    )
    return [row for row in objects if archive_slug_of_key(str(row["Key"]), browser_prefix)]


def require_archive_index(archived: list[dict], index: dict[str, Any]) -> None:
    if archived and not index["releases"]:
        raise RuntimeError(
            "Archived release copies exist but the archive index is empty or missing; "
            "restore browser/archive/index.json before pruning."
        )


def prune_browser_archive(
    *,
    store: R2ObjectStore,
    settings: R2Settings,
    browser_prefix: str,
    active: dict[str, Any],
    plan: RetentionPlan,
    index: dict[str, Any],
    execute: bool,
) -> PruneResult:
    """Delete archived site copies of releases that are no longer kept."""
    keep_slugs = {str(entry.get("slug") or "") for entry in plan.kept} - {""}
    active_slug = str((active.get("archive") or {}).get("slug") or "")
    if active_slug:
        keep_slugs.add(active_slug)
    archived = list_archived_objects(store, settings=settings, browser_prefix=browser_prefix)
    require_archive_index(archived, index)
    stale = [
        row for row in archived if archive_slug_of_key(str(row["Key"]), browser_prefix) not in keep_slugs
    ]
    if execute:
        delete_remote_objects(store, bucket=settings.bucket, rows=stale, label="browser_archive")
        if plan.dropped or index.get("current_release_id") != plan.active_release_id:
            write_archive_index(
                store,
                browser_prefix,
                entries=plan.kept,
                current_release_id=plan.active_release_id,
            )
    return PruneResult(
        label="browser_archive",
        active_run_id=str(active.get("run_id") or ""),
        removed_count=len(stale),
        removed_bytes=sum(int(row.get("Size") or 0) for row in stale),
        kept_count=len(archived) - len(stale),
        executed=execute,
    )


def path_size(path: Path) -> int:
    if path.is_symlink() or path.is_file():
        return path.lstat().st_size
    return sum(
        child.stat().st_size
        for child in path.rglob("*")
        if child.is_file() and not child.is_symlink()
    )


def newest_mtime(paths: tuple[Path, ...]) -> float:
    newest = 0.0
    for path in paths:
        if path.is_symlink() or path.is_file():
            newest = max(newest, path.lstat().st_mtime)
            continue
        newest = max(newest, path.stat().st_mtime)
        for child in path.rglob("*"):
            if not child.is_symlink():
                newest = max(newest, child.stat().st_mtime)
    return newest


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


def active_promotion_timestamp(run_id: str, history: list[dict]) -> float | None:
    """When the active run was promoted, from history or the extraction pointer."""
    value = promotion_time(history, run_id)
    if not value:
        extraction = read_json_object(ACTIVE_EXTRACTION_POINTER)
        if str(extraction.get("run_id") or "").strip() == run_id:
            value = str(extraction.get("updated_at_utc") or "").strip()
    if not value:
        return None
    try:
        return parse_timestamp(value).timestamp()
    except ValueError:
        return None


def plan_local_retention(
    *,
    history_path: Path = RELEASE_HISTORY,
    candidate_grace_days: int = DEFAULT_CANDIDATE_GRACE_DAYS,
    extra_keep: dict[str, str] | None = None,
    now: float | None = None,
) -> tuple[str, list[LocalDecision], list[LocalDecision]]:
    """Return the active run and the run folders to keep and to delete."""
    run_id, _release_id = validate_local_active_release()
    history = read_release_history(history_path)
    published = {str(record.get("run_id") or "") for record in history}
    previous = previous_run_id(history, run_id)
    promoted_at = active_promotion_timestamp(run_id, history)
    current_time = time.time() if now is None else now
    grace_seconds = max(candidate_grace_days, 0) * 86400
    extra_keep = dict(extra_keep or {})

    paths_by_name: dict[str, list[Path]] = {}
    for root in LOCAL_RELEASE_ROOTS.values():
        root.mkdir(parents=True, exist_ok=True)
        for child in sorted(root.iterdir()):
            paths_by_name.setdefault(child.name, []).append(child)

    kept: list[LocalDecision] = []
    removed: list[LocalDecision] = []
    for name, path_list in sorted(paths_by_name.items()):
        paths = tuple(path_list)
        keep_reason = ""
        remove_reason = ""
        if name == run_id:
            keep_reason = "active release"
        elif name == previous:
            keep_reason = "release published before the active one"
        elif name in extra_keep:
            keep_reason = extra_keep[name]
        elif any(path.is_dir() and (path / KEEP_MARKER).exists() for path in paths):
            keep_reason = f"protected by a {KEEP_MARKER} file"
        elif name in published:
            remove_reason = "published earlier and since replaced"
        else:
            changed = newest_mtime(paths)
            if promoted_at is None:
                keep_reason = "never published; the active release has no recorded promotion time"
            elif changed >= promoted_at:
                keep_reason = "never published; changed after the active release was promoted"
            elif current_time - changed < grace_seconds:
                keep_reason = f"never published; changed in the last {candidate_grace_days} days"
            else:
                remove_reason = "never published; last changed before the active release was promoted"
        decision = LocalDecision(
            name=name,
            paths=paths,
            reason=keep_reason or remove_reason,
            size=sum(path_size(path) for path in paths),
        )
        (kept if keep_reason else removed).append(decision)

    LOCAL_RELEASE_STAGING.mkdir(parents=True, exist_ok=True)
    for child in sorted(LOCAL_RELEASE_STAGING.iterdir()):
        removed.append(
            LocalDecision(
                name=f"release_staging/{child.name}",
                paths=(child,),
                reason="left over in release staging",
                size=path_size(child),
            )
        )
    return run_id, kept, removed


def prune_local_release_history(
    *,
    execute: bool,
    candidate_grace_days: int = DEFAULT_CANDIDATE_GRACE_DAYS,
    extra_keep: dict[str, str] | None = None,
    history_path: Path = RELEASE_HISTORY,
    now: float | None = None,
    report: bool = False,
) -> PruneResult:
    run_id, kept, removed = plan_local_retention(
        history_path=history_path,
        candidate_grace_days=candidate_grace_days,
        extra_keep=extra_keep,
        now=now,
    )
    if report:
        verb = "delete" if execute else "would delete"
        for decision in removed:
            print(f"local: {verb} {decision.name} ({format_bytes(decision.size)}): {decision.reason}")
        for decision in kept:
            print(f"local: keep {decision.name} ({format_bytes(decision.size)}): {decision.reason}")
    if execute:
        for decision in removed:
            for path in decision.paths:
                remove_local_path(path)
        validate_local_active_release()
    return PruneResult(
        label="local",
        active_run_id=run_id,
        removed_count=sum(len(decision.paths) for decision in removed),
        removed_bytes=sum(decision.size for decision in removed),
        kept_count=sum(len(decision.paths) for decision in kept),
        executed=execute,
    )


def format_bytes(value: int) -> str:
    amount = float(value)
    for suffix in ("B", "KiB", "MiB", "GiB", "TiB"):
        if amount < 1024 or suffix == "TiB":
            return f"{amount:.2f} {suffix}"
        amount /= 1024
    return f"{amount:.2f} TiB"


def prune_remote_release_history(*, execute: bool) -> tuple[list[PruneResult], RetentionPlan]:
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
    browser_prefix = normalize_r2_prefix(
        os.environ.get("PKG_R2_BROWSER_PREFIX", "browser"),
        variable_name="PKG_R2_BROWSER_PREFIX",
    )
    browser_settings = replace(browser_settings, prefix=browser_prefix)
    browser_store = R2ObjectStore(browser_settings)
    query_store = R2ObjectStore(query_settings)
    browser_active = json.loads(browser_store.get_bytes(f"{browser_prefix}/active.json"))
    query_active = json.loads(query_store.get_bytes(query_settings.active_key))
    require_matching_remote_releases(browser_active, query_active)

    index = read_archive_index(browser_store, browser_prefix)
    # Check the archive before deleting anything, so a missing index cannot
    # leave archived site copies without their release data.
    require_archive_index(
        list_archived_objects(browser_store, settings=browser_settings, browser_prefix=browser_prefix),
        index,
    )
    plan = plan_archive_retention(index["releases"], str(browser_active.get("release_id") or ""))
    browser_result, browser_pointer, _ = prune_remote_releases(
        label="browser_r2",
        store=browser_store,
        settings=browser_settings,
        active_key=f"{browser_prefix}/active.json",
        releases_prefix=f"{browser_prefix}/releases/",
        keep_prefixes={str(entry.get("object_prefix") or "") for entry in plan.kept} - {""},
        execute=execute,
    )
    archive_result = prune_browser_archive(
        store=browser_store,
        settings=browser_settings,
        browser_prefix=browser_prefix,
        active=browser_pointer,
        plan=plan,
        index=index,
        execute=execute,
    )
    query_keep: set[str] = set()
    if plan.previous is not None:
        query_keep.add(
            release_object_prefix(
                query_settings,
                run_id=str(plan.previous.get("run_id") or ""),
                release_id=str(plan.previous.get("release_id") or ""),
            )
        )
    query_result, _, _ = prune_remote_releases(
        label="query_api_r2",
        store=query_store,
        settings=query_settings,
        active_key=query_settings.active_key,
        releases_prefix=f"{query_settings.prefix}/releases/",
        keep_prefixes=query_keep,
        execute=execute,
    )
    return [browser_result, archive_result, query_result], plan


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--local", action="store_true")
    parser.add_argument("--remote", action="store_true")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Perform deletions. Without this flag the command only reports.",
    )
    parser.add_argument(
        "--candidate-grace-days",
        type=int,
        default=DEFAULT_CANDIDATE_GRACE_DAYS,
        help="Keep never-published runs changed within this many days.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.local and not args.remote:
        raise SystemExit("Choose --local, --remote, or both.")
    from pipeline.publish.promote_routed_run import promotion_lock

    results: list[PruneResult] = []
    extra_keep: dict[str, str] = {}
    with promotion_lock():
        if args.remote:
            remote_results, plan = prune_remote_release_history(execute=args.execute)
            results.extend(remote_results)
            if plan.previous is not None and plan.previous.get("run_id"):
                extra_keep[str(plan.previous["run_id"])] = "previous release in the R2 archive"
        if args.local:
            results.append(
                prune_local_release_history(
                    execute=args.execute,
                    candidate_grace_days=args.candidate_grace_days,
                    extra_keep=extra_keep,
                    report=True,
                )
            )

    mode = "deleted" if args.execute else "would delete"
    for result in results:
        print(
            f"{result.label}: {mode} {result.removed_count} inactive artifacts "
            f"({format_bytes(result.removed_bytes)}); kept "
            f"{result.kept_count} artifacts; active run {result.active_run_id}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
