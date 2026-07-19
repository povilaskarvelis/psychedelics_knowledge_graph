#!/usr/bin/env python3
"""Remove machine-local absolute paths from JSON files published with the site."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable


def manifest_items(path: Path) -> list[str]:
    items: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        item = raw_line.split("#", 1)[0].strip()
        if item:
            items.append(item)
    return items


def json_files_from_manifest(manifest: Path, base_dir: Path) -> list[Path]:
    files: list[Path] = []
    for item in manifest_items(manifest):
        path = base_dir / item
        if path.is_dir():
            files.extend(sorted(path.rglob("*.json")))
        elif path.suffix == ".json":
            files.append(path)
    return files


def scrub_string(value: str, root: Path) -> str:
    root_text = root.as_posix().rstrip("/")
    for prefix in (root_text + "/", str(root).rstrip("/") + "/"):
        if value.startswith(prefix):
            return value[len(prefix) :]
        if prefix in value:
            return value.replace(prefix, "")
    return value


def scrub_paths(value: object, root: Path) -> tuple[object, bool]:
    changed = False
    if isinstance(value, dict):
        out = {}
        for key, nested in value.items():
            scrubbed, nested_changed = scrub_paths(nested, root)
            out[key] = scrubbed
            changed = changed or nested_changed
        return out, changed
    if isinstance(value, list):
        out = []
        for nested in value:
            scrubbed, nested_changed = scrub_paths(nested, root)
            out.append(scrubbed)
            changed = changed or nested_changed
        return out, changed
    if isinstance(value, str):
        scrubbed = scrub_string(value, root)
        return scrubbed, scrubbed != value
    return value, False


def write_json_preserving_style(path: Path, payload: object, original_text: str) -> None:
    is_pretty = "\n" in original_text.strip()
    if is_pretty:
        text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    else:
        text = json.dumps(payload, separators=(",", ":"), ensure_ascii=False) + "\n"
    path.write_text(text, encoding="utf-8")


def sanitize_files(files: Iterable[Path], root: Path) -> list[Path]:
    changed_files: list[Path] = []
    root_markers = {
        root.as_posix().rstrip("/").encode("utf-8"),
        str(root).rstrip("/").encode("utf-8"),
    }
    for path in files:
        if not path.exists():
            continue
        original_bytes = path.read_bytes()
        # Generated graph payloads can be tens of megabytes. Avoid expanding
        # them into a second recursive object tree unless the machine-local
        # project root is actually present in the file.
        if not any(marker and marker in original_bytes for marker in root_markers):
            continue
        original_text = original_bytes.decode("utf-8")
        payload = json.loads(original_text)
        scrubbed, changed = scrub_paths(payload, root)
        if changed:
            write_json_preserving_style(path, scrubbed, original_text)
            changed_files.append(path)
    return changed_files


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", help="Specific JSON files or directories to sanitize")
    parser.add_argument("--manifest", default="scripts/public_site_files.txt", help="Public-site manifest to scan")
    parser.add_argument("--base-dir", default=".", help="Base directory for manifest entries")
    parser.add_argument("--root", default=".", help="Project root prefix to strip from JSON string values")
    args = parser.parse_args()

    manifest = Path(args.manifest).resolve()
    base_dir = Path(args.base_dir).resolve()
    root = Path(args.root).resolve()
    if args.paths:
        files: list[Path] = []
        for item in args.paths:
            path = Path(item)
            if path.is_dir():
                files.extend(sorted(path.rglob("*.json")))
            else:
                files.append(path)
    else:
        files = json_files_from_manifest(manifest, base_dir)
    changed_files = sanitize_files(files, root)
    for path in changed_files:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
