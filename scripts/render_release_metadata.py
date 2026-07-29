from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import re


EXPECTED_SCHEMA_VERSION = "site_release_metadata_v1"
DOI_PATTERN = re.compile(r"10\.5281/zenodo\.(\d+)")
VERSION_PATTERN = re.compile(r"\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?")
TARGET_FILES = ("index.html", "about/index.html")
TOKEN_PATTERN = re.compile(r"\{\{RELEASE_[A-Z_]+\}\}")
MONTHS = (
    "jan",
    "feb",
    "mar",
    "apr",
    "may",
    "jun",
    "jul",
    "aug",
    "sep",
    "oct",
    "nov",
    "dec",
)


def load_metadata(path: Path) -> dict[str, str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    required = (
        "schema_version",
        "version",
        "release_date",
        "literature_updated",
        "doi",
        "concept_doi",
    )

    for key in required:
        value = payload.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{path}: {key} must be a non-empty string")

    if payload["schema_version"] != EXPECTED_SCHEMA_VERSION:
        raise ValueError(
            f"{path}: unsupported schema_version {payload['schema_version']!r}; "
            f"expected {EXPECTED_SCHEMA_VERSION!r}"
        )
    if not VERSION_PATTERN.fullmatch(payload["version"]):
        raise ValueError(f"{path}: invalid semantic version {payload['version']!r}")

    release_date = date.fromisoformat(payload["release_date"])
    literature_updated = date.fromisoformat(payload["literature_updated"])
    if literature_updated > release_date:
        raise ValueError(f"{path}: literature_updated cannot be later than release_date")

    doi_match = DOI_PATTERN.fullmatch(payload["doi"])
    concept_doi_match = DOI_PATTERN.fullmatch(payload["concept_doi"])
    if not doi_match or not concept_doi_match:
        raise ValueError(f"{path}: doi and concept_doi must be Zenodo DOIs")
    if payload["doi"] == payload["concept_doi"]:
        raise ValueError(f"{path}: doi and concept_doi must identify different records")

    return payload


def release_replacements(metadata: dict[str, str]) -> dict[str, str]:
    released = date.fromisoformat(metadata["release_date"])

    return {
        "{{RELEASE_VERSION}}": metadata["version"],
        "{{RELEASE_DATE}}": metadata["release_date"],
        "{{RELEASE_YEAR}}": str(released.year),
        "{{RELEASE_MONTH_BIBTEX}}": MONTHS[released.month - 1],
        "{{RELEASE_LITERATURE_UPDATED}}": metadata["literature_updated"],
        "{{RELEASE_DOI}}": metadata["doi"],
        "{{RELEASE_CONCEPT_DOI}}": metadata["concept_doi"],
    }


def render_site(metadata_path: Path, site_dir: Path) -> None:
    replacements = release_replacements(load_metadata(metadata_path))

    for relative_path in TARGET_FILES:
        path = site_dir / relative_path
        source = path.read_text(encoding="utf-8")
        rendered = source
        for token, value in replacements.items():
            rendered = rendered.replace(token, value)

        unresolved = sorted(set(TOKEN_PATTERN.findall(rendered)))
        if unresolved:
            raise ValueError(f"{path}: unresolved release tokens: {', '.join(unresolved)}")
        path.write_text(rendered, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Render release metadata into the static site.")
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--site-dir", type=Path, required=True)
    args = parser.parse_args()

    render_site(args.metadata.resolve(), args.site_dir.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
