"""Shared DOI-alias helpers for publication-level deduplication."""

from __future__ import annotations

import json
from pathlib import Path

from pipeline.ingest.metadata_utils import normalize_doi


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DOI_ALIAS_REGISTRY = ROOT / "pipeline" / "validate" / "doi_alias_registry.json"


def load_doi_aliases(path: Path | None = DEFAULT_DOI_ALIAS_REGISTRY) -> dict[str, str]:
    """Return normalized alias -> canonical DOI mappings from the registry."""
    if path is None or not Path(path).is_file():
        return {}
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    aliases: dict[str, str] = {}
    for record in payload.get("records", []):
        alias = normalize_doi(record.get("alias_doi", ""))
        canonical = normalize_doi(record.get("canonical_doi", ""))
        if alias and canonical and alias != canonical:
            aliases[alias] = canonical
    return aliases


def active_doi_aliases(
    aliases: dict[str, str],
    available_dois: set[str],
) -> dict[str, str]:
    """Keep mappings whose alias and canonical publication are both present."""
    available = {normalize_doi(doi) for doi in available_dois if normalize_doi(doi)}
    return {
        alias: canonical
        for alias, canonical in aliases.items()
        if alias in available and canonical in available
    }
