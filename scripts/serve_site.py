#!/usr/bin/env python3
"""Serve the code-only site with optional, allowlisted local release data."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIST = ROOT / "dist"
LOCAL_POINTER_SCHEMA = "psychedelics_kg_local_preview_active_v1"
PUBLIC_POINTER_SCHEMA = "psychedelics_kg_browser_r2_active_v1"
PUBLIC_POINTER_URL = "https://data.psychedelicskg.com/browser/active.json"
PUBLIC_DATA_ORIGIN = "https://data.psychedelicskg.com"
GRAPH_MANIFEST_SCHEMA = "route_native_evidence_manifest_v1"
SOURCE_KEYS = {"primary", "meta_analyses", "reviews"}
METHODS_FILES = {
    "pipeline_status": "data/kg/views/pipeline_status_graph.json",
    "bibliography": "data/kg/views/methods_bibliography.json",
    "graph_inclusion_dispositions": "data/kg/views/graph_inclusion_dispositions.json",
}
LOCAL_PAGE_PATHS = {"/", "/about/", "/api/", "/feedback/", "/methods/"}
RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


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
    pointer_mappings: dict[str, dict[str, str]] = {}
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
            remote_files[logical_name] = {
                "key": public_path,
                "path": path.name,
                "bytes": size,
                "sha256": digest,
            }
    if set(manifest.get("files") or {}) != expected_logical_names:
        raise ValueError("Graph manifest contains an unexpected file set")

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
        **kwargs,
    ) -> None:
        self.local_pointer = local_pointer
        self.local_files = local_files
        self.published_pointer = published_pointer
        self.published_files = published_files
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

    handler = partial(
        PreviewRequestHandler,
        directory=str(directory),
        local_pointer=pointer_bytes,
        local_files=local_files,
        published_pointer=published_pointer,
        published_files=published_files,
    )
    server = ThreadingHTTPServer((args.bind, args.port), handler)
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
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
