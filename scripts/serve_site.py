#!/usr/bin/env python3
"""Serve the code-only site with optional, allowlisted local release data."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.kg.graph_view_contract import graph_view_ids
from scripts.build_analysis_index import build_index, load_columnar


DEFAULT_DIST = ROOT / "dist"
SITE_WATCH_POLL_SECONDS = 0.2
SITE_WATCH_DEBOUNCE_SECONDS = 0.35
LOCAL_POINTER_SCHEMA = "psychedelics_kg_local_preview_active_v1"
PUBLIC_POINTER_SCHEMA = "psychedelics_kg_browser_r2_active_v1"
PUBLIC_POINTER_URL = "https://data.psychedelicskg.com/browser/active.json"
PUBLIC_DATA_ORIGIN = "https://data.psychedelicskg.com"
GRAPH_MANIFEST_SCHEMA = "route_native_evidence_manifest_v1"
SOURCE_KEYS = {"primary", "meta_analyses", "reviews"}
DETAIL_VIEW_KEYS = set(graph_view_ids())
METHODS_FILES = {
    "pipeline_status": "data/kg/views/pipeline_status_graph.json",
    "bibliography": "data/kg/views/methods_bibliography.json",
    "graph_inclusion_dispositions": "data/kg/views/graph_inclusion_dispositions.json",
}
LOCAL_PAGE_PATHS = {"/", "/about/", "/api/", "/feedback/", "/methods/"}
RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def public_site_manifest_entries(repository_root: Path = ROOT) -> tuple[Path, ...]:
    manifest = repository_root / "scripts/public_site_files.txt"
    entries: list[Path] = []
    for raw_line in manifest.read_text(encoding="utf-8").splitlines():
        item = raw_line.split("#", 1)[0].strip()
        if item:
            entries.append(repository_root / item)
    return tuple(entries)


def public_site_watch_paths(repository_root: Path = ROOT) -> tuple[Path, ...]:
    build_inputs = (
        repository_root / "release-metadata.json",
        repository_root / "scripts/build_site.sh",
        repository_root / "scripts/public_site_files.txt",
        repository_root / "scripts/render_release_metadata.py",
        repository_root / "scripts/sanitize_public_json.py",
    )
    return tuple(
        dict.fromkeys((*public_site_manifest_entries(repository_root), *build_inputs))
    )


def public_site_source_snapshot(
    repository_root: Path = ROOT,
) -> tuple[tuple[str, str, int, int], ...]:
    """Return a cheap, deterministic signature for files copied into the site build."""
    entries: list[tuple[str, str, int, int]] = []
    for watched_path in public_site_watch_paths(repository_root):
        if not watched_path.exists():
            entries.append((str(watched_path), "missing", 0, 0))
            continue
        paths = (
            (watched_path,)
            if watched_path.is_file()
            else (watched_path, *watched_path.rglob("*"))
        )
        for path in paths:
            if path.name == ".DS_Store" or "__pycache__" in path.parts:
                continue
            try:
                stat = path.stat()
            except FileNotFoundError:
                continue
            kind = "directory" if path.is_dir() else "file"
            entries.append((str(path), kind, stat.st_mtime_ns, stat.st_size))
    return tuple(sorted(entries))


def build_public_site(
    site_directory: Path = DEFAULT_DIST,
    repository_root: Path = ROOT,
) -> None:
    environment = os.environ.copy()
    environment["DIST_DIR"] = str(site_directory)
    subprocess.run(
        ["bash", str(repository_root / "scripts/build_site.sh")],
        cwd=repository_root,
        env=environment,
        check=True,
    )


class SiteBuildWatcher:
    """Rebuild the local site after a short quiet period following source edits."""

    def __init__(
        self,
        site_directory: Path,
        repository_root: Path = ROOT,
        *,
        build: Callable[[], None] | None = None,
        build_lock: threading.RLock | None = None,
        poll_seconds: float = SITE_WATCH_POLL_SECONDS,
        debounce_seconds: float = SITE_WATCH_DEBOUNCE_SECONDS,
    ) -> None:
        self.site_directory = site_directory
        self.repository_root = repository_root
        self.build = build or partial(build_public_site, site_directory, repository_root)
        self.build_lock = build_lock or threading.RLock()
        self.poll_seconds = poll_seconds
        self.debounce_seconds = debounce_seconds
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None
        self.snapshot: tuple[tuple[str, str, int, int], ...] = ()

    def start(self) -> None:
        self.snapshot = public_site_source_snapshot(self.repository_root)
        self.thread = threading.Thread(
            target=self._watch,
            name="local-site-build-watcher",
            daemon=True,
        )
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        if self.thread is not None:
            self.thread.join(timeout=max(1.0, self.poll_seconds * 3))

    def _watch(self) -> None:
        changed_at: float | None = None
        pending_snapshot = self.snapshot
        while not self.stop_event.wait(self.poll_seconds):
            current_snapshot = public_site_source_snapshot(self.repository_root)
            if current_snapshot != pending_snapshot:
                pending_snapshot = current_snapshot
                changed_at = time.monotonic()
                continue
            if changed_at is None or time.monotonic() - changed_at < self.debounce_seconds:
                continue

            print("Website files changed; rebuilding the local preview...", flush=True)
            build_input_snapshot = pending_snapshot
            try:
                with self.build_lock:
                    self.build()
            except (OSError, subprocess.CalledProcessError) as error:
                print(
                    f"Local preview rebuild failed: {error}",
                    file=sys.stderr,
                    flush=True,
                )
            else:
                print("Local preview updated. Refresh the page to see the change.", flush=True)
            self.snapshot = public_site_source_snapshot(self.repository_root)
            pending_snapshot = self.snapshot
            changed_at = time.monotonic() if self.snapshot != build_input_snapshot else None


def read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise FileNotFoundError(f"Missing local preview file: {path}") from None
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_run_id(value: object) -> str:
    run_id = str(value or "").strip()
    if not RUN_ID_PATTERN.fullmatch(run_id):
        raise ValueError(f"Invalid or missing local preview run ID: {run_id!r}")
    return run_id


def safe_release_path(repository_root: Path, run_root: Path, relative_path: object) -> Path:
    relative = Path(str(relative_path or ""))
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"Unsafe local preview path: {relative_path}")
    path = (repository_root / relative).resolve()
    if run_root not in path.parents or not path.is_file():
        raise FileNotFoundError(f"Missing or out-of-run preview file: {relative_path}")
    return path


def build_local_preview(
    repository_root: Path = ROOT,
    *,
    requested_run_id: str = "",
) -> tuple[dict, dict[str, Path]]:
    """Build and verify a local-only pointer for one generated public release."""
    repository_root = repository_root.resolve()
    if requested_run_id:
        run_id = safe_run_id(requested_run_id)
    else:
        active = read_json(repository_root / "data/processed/graph_payload_active.json")
        run_id = safe_run_id(active.get("run_id"))

    run_root = (
        repository_root / "data/processed/graph_payload_runs" / run_id
    ).resolve()
    manifest_path = run_root / "graph_payload_manifest.json"
    manifest = read_json(manifest_path)
    if manifest.get("schema_version") != GRAPH_MANIFEST_SCHEMA:
        raise ValueError(f"Unexpected graph manifest schema: {manifest_path}")

    release_id = str(
        manifest.get("release_id") or manifest.get("evidence_release_id") or ""
    ).strip()
    if not release_id:
        raise ValueError(f"Graph manifest lacks a release ID: {manifest_path}")

    allowed_files: dict[str, Path] = {}
    remote_files: dict[str, dict] = {}
    expected_logical_names: set[str] = set()
    pointer_mappings: dict[str, object] = {}
    detail_source_paths: dict[str, Path] = {}
    for manifest_key, pointer_key, logical_prefix in (
        ("graph_bootstraps", "active_graph_bootstraps", "graph"),
        ("dashboard_bootstraps", "active_dashboard_bootstraps", "dashboard"),
        ("detail_bootstraps", "active_detail_bootstraps", "detail"),
    ):
        mapping = manifest.get(manifest_key) or {}
        if not isinstance(mapping, dict) or set(mapping) != SOURCE_KEYS:
            raise ValueError(
                f"Graph manifest {manifest_key} must contain {sorted(SOURCE_KEYS)}"
            )
        pointer_mappings[pointer_key] = {}
        for source_key, relative_path in mapping.items():
            logical_name = f"{logical_prefix}:{source_key}"
            expected_logical_names.add(logical_name)
            entry = (manifest.get("files") or {}).get(logical_name) or {}
            if entry.get("path") != relative_path:
                raise ValueError(f"Manifest path mismatch for {logical_name}")
            path = safe_release_path(repository_root, run_root, relative_path)
            size = path.stat().st_size
            digest = sha256_file(path)
            if int(entry.get("bytes", -1)) != size:
                raise ValueError(f"Manifest size mismatch for {logical_name}")
            if str(entry.get("sha256") or "").casefold() != digest:
                raise ValueError(f"Manifest checksum mismatch for {logical_name}")
            public_path = str(relative_path).lstrip("/")
            allowed_files[f"/{public_path}"] = path
            pointer_mappings[pointer_key][str(source_key)] = public_path
            if logical_prefix == "detail":
                detail_source_paths[str(source_key)] = path
            remote_files[logical_name] = {
                "key": public_path,
                "path": path.name,
                "bytes": size,
                "sha256": digest,
            }
    detail_view_mapping = manifest.get("detail_bootstraps_by_view")
    if detail_view_mapping is not None:
        if not isinstance(detail_view_mapping, dict) or set(detail_view_mapping) != SOURCE_KEYS:
            raise ValueError(
                f"Graph manifest detail_bootstraps_by_view must contain {sorted(SOURCE_KEYS)}"
            )
        pointer_mappings["active_detail_bootstraps_by_view"] = {}
        for source_key, source_views in detail_view_mapping.items():
            if not isinstance(source_views, dict) or set(source_views) != DETAIL_VIEW_KEYS:
                raise ValueError(
                    "Graph manifest detail_bootstraps_by_view."
                    f"{source_key} must contain {sorted(DETAIL_VIEW_KEYS)}"
                )
            pointer_mappings["active_detail_bootstraps_by_view"][source_key] = {}
            for view_key, relative_path in source_views.items():
                logical_name = f"detail_view:{source_key}:{view_key}"
                expected_logical_names.add(logical_name)
                entry = (manifest.get("files") or {}).get(logical_name) or {}
                if entry.get("path") != relative_path:
                    raise ValueError(f"Manifest path mismatch for {logical_name}")
                path = safe_release_path(repository_root, run_root, relative_path)
                size = path.stat().st_size
                digest = sha256_file(path)
                if int(entry.get("bytes", -1)) != size:
                    raise ValueError(f"Manifest size mismatch for {logical_name}")
                if str(entry.get("sha256") or "").casefold() != digest:
                    raise ValueError(f"Manifest checksum mismatch for {logical_name}")
                public_path = str(relative_path).lstrip("/")
                allowed_files[f"/{public_path}"] = path
                pointer_mappings["active_detail_bootstraps_by_view"][source_key][view_key] = public_path
                remote_files[logical_name] = {
                    "key": public_path,
                    "path": path.name,
                    "bytes": size,
                    "sha256": digest,
                }
    if set(manifest.get("files") or {}) != expected_logical_names:
        raise ValueError("Graph manifest contains an unexpected file set")

    analysis_index_path = run_root / "analysis_index_v1.json"
    analysis_builder_path = repository_root / "scripts" / "build_analysis_index.py"
    if not analysis_builder_path.is_file():
        analysis_builder_path = ROOT / "scripts" / "build_analysis_index.py"
    newest_analysis_input_mtime = max(
        max(path.stat().st_mtime for path in detail_source_paths.values()),
        analysis_builder_path.stat().st_mtime,
    )
    if not analysis_index_path.is_file() or analysis_index_path.stat().st_mtime < newest_analysis_input_mtime:
        analysis_payload = build_index(
            {
                source_key: load_columnar(detail_source_paths[source_key])
                for source_key in sorted(SOURCE_KEYS)
            },
            str(manifest.get("generated_at") or ""),
        )
        analysis_index_path.write_text(
            json.dumps(analysis_payload, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
    analysis_public_path = analysis_index_path.relative_to(repository_root).as_posix()
    allowed_files[f"/{analysis_public_path}"] = analysis_index_path
    pointer_mappings["active_analysis_index"] = analysis_public_path
    remote_files["analysis:index"] = {
        "key": analysis_public_path,
        "path": analysis_index_path.name,
        "bytes": analysis_index_path.stat().st_size,
        "sha256": sha256_file(analysis_index_path),
    }

    manifest_relative = manifest_path.relative_to(repository_root).as_posix()
    allowed_files[f"/{manifest_relative}"] = manifest_path
    methods: dict[str, str] = {}
    expected_methods_release_id = str(
        manifest.get("evidence_release_id") or release_id
    ).strip()
    for public_name, relative_path in METHODS_FILES.items():
        path = (repository_root / relative_path).resolve()
        if path.parent != (repository_root / "data/kg/views").resolve() or not path.is_file():
            raise FileNotFoundError(f"Missing required local Methods data: {path}")
        payload = read_json(path)
        methods_run_id = str(payload.get("run_id") or "").strip()
        methods_release_id = str(payload.get("release_id") or "").strip()
        if methods_run_id != run_id:
            raise ValueError(
                f"Methods data run ID mismatch in {path.name}: "
                f"expected {run_id!r}, found {methods_run_id or '<missing>'!r}"
            )
        if methods_release_id != expected_methods_release_id:
            raise ValueError(
                f"Methods data release ID mismatch in {path.name}: "
                f"expected {expected_methods_release_id!r}, "
                f"found {methods_release_id or '<missing>'!r}"
            )
        allowed_files[f"/{relative_path}"] = path
        methods[public_name] = relative_path
        remote_files[f"methods:{public_name}"] = {
            "key": relative_path,
            "path": path.name,
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }

    pointer = {
        "schema_version": LOCAL_POINTER_SCHEMA,
        "data_source": "local",
        "run_id": run_id,
        "release_id": release_id,
        "evidence_release_id": expected_methods_release_id,
        "active_manifest": manifest_relative,
        **pointer_mappings,
        "methods": methods,
        "files": remote_files,
    }
    return pointer, allowed_files


def validated_published_preview(pointer: dict) -> dict[str, str]:
    """Allow only immutable R2 objects named by the active public pointer."""
    if pointer.get("schema_version") != PUBLIC_POINTER_SCHEMA:
        raise ValueError("Unexpected published preview pointer schema")
    object_prefix = str(pointer.get("object_prefix") or "").strip("/")
    if not object_prefix.startswith("browser/releases/"):
        raise ValueError("Published preview pointer has an invalid object prefix")

    keys: set[str] = set()
    active_manifest = str(pointer.get("active_manifest") or "").strip("/")
    if active_manifest:
        keys.add(active_manifest)
    for mapping_name in (
        "active_graph_bootstraps",
        "active_dashboard_bootstraps",
        "active_detail_bootstraps",
        "methods",
    ):
        mapping = pointer.get(mapping_name) or {}
        if not isinstance(mapping, dict) or not mapping:
            raise ValueError(f"Published preview pointer is missing {mapping_name}")
        keys.update(str(value or "").strip("/") for value in mapping.values())
    analysis_index = str(pointer.get("active_analysis_index") or "").strip("/")
    if analysis_index:
        keys.add(analysis_index)
    detail_view_mapping = pointer.get("active_detail_bootstraps_by_view")
    if detail_view_mapping is not None:
        if not isinstance(detail_view_mapping, dict) or not detail_view_mapping:
            raise ValueError(
                "Published preview pointer has an invalid active_detail_bootstraps_by_view mapping"
            )
        for source_views in detail_view_mapping.values():
            if not isinstance(source_views, dict) or not source_views:
                raise ValueError(
                    "Published preview pointer has an invalid detail-view source mapping"
                )
            keys.update(str(value or "").strip("/") for value in source_views.values())
    files = pointer.get("files") or {}
    if not isinstance(files, dict) or not files:
        raise ValueError("Published preview pointer is missing its file catalogue")
    keys.update(
        str(entry.get("key") or "").strip("/")
        for entry in files.values()
        if isinstance(entry, dict)
    )

    allowed: dict[str, str] = {}
    for key in keys:
        if not key or ".." in Path(key).parts or not key.startswith(f"{object_prefix}/"):
            raise ValueError(f"Unsafe published preview object key: {key!r}")
        allowed[f"/{key}"] = f"{PUBLIC_DATA_ORIGIN}/{key}"
    return allowed


def load_published_preview() -> tuple[bytes, dict[str, str]]:
    request = Request(
        PUBLIC_POINTER_URL,
        headers={"User-Agent": "Mozilla/5.0 PsychedelicsKG local preview"},
    )
    with urlopen(request, timeout=60) as response:
        pointer_bytes = response.read()
    pointer = json.loads(pointer_bytes)
    if not isinstance(pointer, dict):
        raise ValueError("Published preview pointer must be a JSON object")
    return pointer_bytes, validated_published_preview(pointer)


class PreviewRequestHandler(SimpleHTTPRequestHandler):
    def __init__(
        self,
        *args,
        directory: str,
        local_pointer: bytes | None,
        local_files: dict[str, Path],
        published_pointer: bytes | None,
        published_files: dict[str, str],
        build_lock: threading.RLock | None = None,
        **kwargs,
    ) -> None:
        self.local_pointer = local_pointer
        self.local_files = local_files
        self.published_pointer = published_pointer
        self.published_files = published_files
        self.build_lock = build_lock or threading.RLock()
        super().__init__(*args, directory=directory, **kwargs)

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def redirect_local_page(self) -> bool:
        if self.local_pointer is None:
            return False
        parsed = urlsplit(self.path)
        if parsed.path not in LOCAL_PAGE_PATHS:
            return False
        query = parse_qs(parsed.query, keep_blank_values=True)
        if query.get("data-source") == ["local"]:
            return False
        query["data-source"] = ["local"]
        location = urlunsplit(("", "", parsed.path, urlencode(query, doseq=True), parsed.fragment))
        self.send_response(302)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.end_headers()
        return True

    def reject_preview_mode_mismatch(self) -> bool:
        parsed = urlsplit(self.path)
        if parsed.path not in LOCAL_PAGE_PATHS:
            return False
        query = parse_qs(parsed.query, keep_blank_values=True)
        local_requested = query.get("data-source") == ["local"]
        if not local_requested or self.local_pointer is not None:
            return False
        self.send_error(
            409,
            "Local release requested, but this server is running in public mode. "
            "Restart with: bash scripts/preview_site.sh local",
        )
        return True

    def send_preview_bytes(self, payload: bytes, *, head_only: bool) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        if not head_only:
            self.wfile.write(payload)

    def send_preview_file(self, path: Path, *, head_only: bool) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(path.stat().st_size))
        self.end_headers()
        if not head_only:
            with path.open("rb") as handle:
                self.copyfile(handle, self.wfile)

    def proxy_published_file(self, url: str, *, head_only: bool) -> None:
        headers = {"User-Agent": "Mozilla/5.0 PsychedelicsKG local preview"}
        accepted_encoding = self.headers.get("Accept-Encoding", "")
        if accepted_encoding:
            headers["Accept-Encoding"] = accepted_encoding
        request = Request(url, headers=headers, method="HEAD" if head_only else "GET")
        try:
            with urlopen(request, timeout=120) as response:
                self.send_response(response.status)
                for header in (
                    "Content-Type",
                    "Content-Length",
                    "Content-Encoding",
                    "ETag",
                    "Last-Modified",
                ):
                    value = response.headers.get(header)
                    if value:
                        self.send_header(header, value)
                self.end_headers()
                if not head_only:
                    self.copyfile(response, self.wfile)
        except Exception as error:
            self.send_error(502, f"Published R2 preview failed: {error}")

    def handle_request(self, *, head_only: bool) -> None:
        with self.build_lock:
            self._handle_request(head_only=head_only)

    def _handle_request(self, *, head_only: bool) -> None:
        if self.reject_preview_mode_mismatch():
            return
        if self.redirect_local_page():
            return
        request_path = urlsplit(self.path).path
        if (
            request_path == "/__preview__/published.json"
            and self.published_pointer is not None
        ):
            self.send_preview_bytes(self.published_pointer, head_only=head_only)
            return
        if request_path == "/__preview__/active.json" and self.local_pointer is not None:
            self.send_preview_bytes(self.local_pointer, head_only=head_only)
            return
        if request_path in self.local_files:
            self.send_preview_file(self.local_files[request_path], head_only=head_only)
            return
        if request_path in self.published_files:
            self.proxy_published_file(
                self.published_files[request_path],
                head_only=head_only,
            )
            return
        if request_path.startswith("/__preview__/") or request_path.startswith("/data/"):
            self.send_error(404, "Local preview data is not available")
            return
        if request_path.startswith("/browser/releases/"):
            self.send_error(404, "R2 object is not in the active public release")
            return
        if head_only:
            super().do_HEAD()
        else:
            super().do_GET()

    def do_GET(self) -> None:  # noqa: N802 - standard-library handler API
        self.handle_request(head_only=False)

    def do_HEAD(self) -> None:  # noqa: N802 - standard-library handler API
        self.handle_request(head_only=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("public", "local"), required=True)
    parser.add_argument("--run-id", default="")
    parser.add_argument("--directory", type=Path, default=DEFAULT_DIST)
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8011)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.bind not in {"127.0.0.1", "::1", "localhost"}:
        raise SystemExit("The preview server may bind only to the local machine.")
    directory = args.directory.resolve()
    manages_local_build = args.mode == "local" and directory == DEFAULT_DIST.resolve()
    if manages_local_build:
        try:
            build_public_site(directory, ROOT)
        except (OSError, subprocess.CalledProcessError) as error:
            raise SystemExit(
                f"Could not build the local website preview: {error}"
            ) from None
    if not directory.is_dir():
        raise SystemExit(f"Missing site build directory: {directory}")

    pointer_bytes: bytes | None = None
    local_files: dict[str, Path] = {}
    published_pointer: bytes | None = None
    published_files: dict[str, str] = {}
    run_id = ""
    if args.mode == "local":
        try:
            pointer, local_files = build_local_preview(
                ROOT,
                requested_run_id=args.run_id,
            )
        except (OSError, ValueError) as error:
            raise SystemExit(
                "Local candidate preview refused to start because its generated "
                f"artifacts do not form one release:\n{error}\n"
                "Build and promote the candidate locally again, without enabling "
                "R2 publication, then retry."
            ) from None
        run_id = str(pointer["run_id"])
        pointer_bytes = (
            json.dumps(pointer, indent=2, ensure_ascii=False) + "\n"
        ).encode("utf-8")
    else:
        try:
            published_pointer, published_files = load_published_preview()
        except (OSError, ValueError) as error:
            raise SystemExit(
                f"Could not prepare the published R2 preview: {error}"
            ) from None
        published = json.loads(published_pointer)
        run_id = str(published.get("run_id") or "").strip()

    site_build_lock = threading.RLock()
    handler = partial(
        PreviewRequestHandler,
        directory=str(directory),
        local_pointer=pointer_bytes,
        local_files=local_files,
        published_pointer=published_pointer,
        published_files=published_files,
        build_lock=site_build_lock,
    )
    server = ThreadingHTTPServer((args.bind, args.port), handler)
    site_watcher: SiteBuildWatcher | None = None
    if manages_local_build:
        site_watcher = SiteBuildWatcher(
            directory,
            ROOT,
            build_lock=site_build_lock,
        )
        site_watcher.start()
    if args.mode == "local":
        print(f"Local candidate release: {run_id}", flush=True)
        print(
            f"Open http://{args.bind}:{args.port}/?data-source=local",
            flush=True,
        )
    else:
        print("Data source: published R2 release", flush=True)
        print(f"Published release: {run_id}", flush=True)
        print(f"Open http://{args.bind}:{args.port}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if site_watcher is not None:
            site_watcher.stop()
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
