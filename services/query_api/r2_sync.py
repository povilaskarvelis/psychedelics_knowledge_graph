from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from pathlib import Path

from .config import R2Settings, Settings
from .r2_store import (
    R2_ACTIVE_SCHEMA_VERSION,
    R2_RELEASE_SIDECAR_NAME,
    ObjectStore,
    R2ObjectStore,
    canonical_json_bytes,
    sha256_file,
)


QUERY_MANIFEST_SCHEMA = "psychedelics_kg_public_query_manifest_v1"
LOCAL_POINTER_SCHEMA = "route_native_evidence_payload_active_v1"
RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def write_bytes_atomic(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="wb",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        temp_path = Path(handle.name)
        handle.write(value)
        handle.flush()
        os.fsync(handle.fileno())
    try:
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


def validate_remote_entry(value: object, *, label: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"R2 active release has no valid {label} entry")
    key = str(value.get("key") or "").strip()
    relative_path = str(value.get("path") or "").strip()
    digest = str(value.get("sha256") or "").strip().casefold()
    try:
        size = int(value.get("bytes"))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"R2 active release has an invalid size for {label}") from exc
    if not key or not relative_path or len(digest) != 64 or size < 0:
        raise ValueError(f"R2 active release has an invalid {label} entry")
    relative = Path(relative_path)
    if relative_path == "." or relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"R2 active release has an unsafe path for {label}")
    return {
        **value,
        "key": key,
        "path": relative.as_posix(),
        "sha256": digest,
        "bytes": size,
    }


def validate_remote_active(value: object) -> dict:
    if not isinstance(value, dict):
        raise ValueError("R2 active release pointer must be a JSON object")
    if value.get("schema_version") != R2_ACTIVE_SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported R2 active release schema: {value.get('schema_version')}"
        )
    run_id = str(value.get("run_id") or "").strip()
    release_id = str(value.get("release_id") or "").strip()
    if not run_id or not release_id:
        raise ValueError("R2 active release pointer lacks run_id or release_id")
    if not RUN_ID_RE.fullmatch(run_id):
        raise ValueError("R2 active release pointer has an unsafe run_id")
    manifest = validate_remote_entry(value.get("manifest"), label="manifest")
    files = value.get("files")
    if not isinstance(files, dict):
        raise ValueError("R2 active release files must be an object")
    validated_files = {
        str(logical_name): validate_remote_entry(entry, label=str(logical_name))
        for logical_name, entry in files.items()
    }
    for required in ("database", "schema"):
        if required not in validated_files:
            raise ValueError(f"R2 active release is missing {required}")
    return {
        **value,
        "run_id": run_id,
        "release_id": release_id,
        "manifest": manifest,
        "files": validated_files,
    }


def is_verified_file(path: Path, entry: dict) -> bool:
    return (
        path.is_file()
        and path.stat().st_size == int(entry["bytes"])
        and sha256_file(path) == entry["sha256"]
    )


def download_verified(store: ObjectStore, entry: dict, destination: Path) -> None:
    store.download_file(entry["key"], destination)
    if not is_verified_file(destination, entry):
        destination.unlink(missing_ok=True)
        raise RuntimeError(f"Downloaded R2 object failed verification: {entry['key']}")


def install_directory_atomic(stage: Path, target: Path) -> None:
    backup = target.with_name(f".{target.name}.previous")
    shutil.rmtree(backup, ignore_errors=True)
    if target.exists():
        target.rename(backup)
    try:
        os.replace(stage, target)
    except BaseException:
        if backup.exists() and not target.exists():
            backup.rename(target)
        raise
    shutil.rmtree(backup, ignore_errors=True)


class R2ReleaseSynchronizer:
    def __init__(
        self,
        *,
        service_settings: Settings,
        r2_settings: R2Settings,
        store: ObjectStore | None = None,
    ) -> None:
        self.service_settings = service_settings
        self.r2_settings = r2_settings
        self.store = store or R2ObjectStore(r2_settings)

    def sync(self) -> dict:
        active = validate_remote_active(
            json.loads(
                self.store.get_bytes(self.r2_settings.active_key).decode("utf-8")
            )
        )
        expected_key_prefix = f"{self.r2_settings.prefix}/releases/"
        remote_entries = [active["manifest"], *active["files"].values()]
        if any(
            not str(entry["key"]).startswith(expected_key_prefix)
            for entry in remote_entries
        ):
            raise ValueError(
                "R2 active release points outside the configured release prefix"
            )
        run_id = active["run_id"]
        release_id = active["release_id"]
        target = self.service_settings.query_runs_dir / run_id
        core_entries = {
            "manifest": active["manifest"],
            "database": active["files"]["database"],
            "schema": active["files"]["schema"],
        }

        existing_core_ok = all(
            is_verified_file(target / entry["path"], entry)
            for entry in core_entries.values()
        )
        if not existing_core_ok:
            self.service_settings.query_runs_dir.mkdir(parents=True, exist_ok=True)
            stage = Path(
                tempfile.mkdtemp(
                    prefix=f".{run_id}.r2-sync.",
                    dir=self.service_settings.query_runs_dir,
                )
            )
            try:
                for entry in core_entries.values():
                    download_verified(self.store, entry, stage / entry["path"])
                manifest = json.loads(
                    (stage / active["manifest"]["path"]).read_text("utf-8")
                )
                if manifest.get("schema_version") != QUERY_MANIFEST_SCHEMA:
                    raise ValueError(
                        "Downloaded query manifest has an unsupported schema"
                    )
                if manifest.get("run_id") != run_id:
                    raise ValueError("Downloaded query manifest belongs to another run")
                for logical_name in ("database", "schema"):
                    manifest_entry = (manifest.get("files") or {}).get(
                        logical_name
                    ) or {}
                    remote_entry = active["files"][logical_name]
                    if (
                        manifest_entry.get("path") != remote_entry["path"]
                        or manifest_entry.get("sha256") != remote_entry["sha256"]
                        or int(manifest_entry.get("bytes", -1)) != remote_entry["bytes"]
                    ):
                        raise ValueError(
                            f"R2 active pointer and query manifest disagree about {logical_name}"
                        )
                (stage / R2_RELEASE_SIDECAR_NAME).write_bytes(
                    canonical_json_bytes(active)
                )
                install_directory_atomic(stage, target)
            finally:
                shutil.rmtree(stage, ignore_errors=True)
        else:
            write_bytes_atomic(
                target / R2_RELEASE_SIDECAR_NAME, canonical_json_bytes(active)
            )

        local_pointer = {
            "schema_version": LOCAL_POINTER_SCHEMA,
            "run_id": run_id,
            "release_id": release_id,
            "query_api_r2": {
                "active_key": self.r2_settings.active_key,
                "object_prefix": active.get("object_prefix") or "",
                "published_at": active.get("published_at") or "",
            },
        }
        write_bytes_atomic(
            self.service_settings.active_pointer,
            canonical_json_bytes(local_pointer),
        )
        return {
            "run_id": run_id,
            "release_id": release_id,
            "artifact_dir": str(target),
            "downloaded": not existing_core_ok,
        }


def sync_from_settings(settings: Settings) -> dict | None:
    if settings.r2 is None:
        return None
    return R2ReleaseSynchronizer(
        service_settings=settings,
        r2_settings=settings.r2,
    ).sync()
