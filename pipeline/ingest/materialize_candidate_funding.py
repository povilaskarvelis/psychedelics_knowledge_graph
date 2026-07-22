#!/usr/bin/env python3
"""Materialize provider-backed funding summaries onto DOI-keyed paper tables.

The normalized provider assertions remain the authoritative funding record.
This module produces a compact projection for candidate/KG paper rows without
using legacy funding strings as evidence and without collapsing provider
provenance into the scientific evidence graph.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path

import pandas as pd

from pipeline.ingest.funding_metadata import ASSERTION_COLUMNS, assertion_identity
from pipeline.ingest.metadata_utils import normalize, normalize_doi


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CANDIDATES = ROOT / "data" / "processed" / "corpus" / "candidate_papers.parquet"
DEFAULT_ASSERTIONS = ROOT / "data" / "processed" / "corpus" / "paper_funding.parquet"
DEFAULT_ATTEMPTS = (
    ROOT / "data" / "processed" / "corpus" / "paper_funding_provider_attempts.parquet"
)
DEFAULT_DOI_ALIAS_REGISTRY = ROOT / "pipeline" / "validate" / "doi_alias_registry.json"

PROVIDER_ORDER = {"openalex": 0, "crossref": 1, "pubmed": 2}
SUMMARY_COLUMNS = (
    "funders",
    "grant_ids",
    "funding_metadata_status",
    "funding_providers",
    "funding_assertion_count",
    "funding_funder_count",
    "funding_award_count",
)


def clean(value: object) -> str:
    return normalize(value)


def normalized_doi(value: object) -> str:
    return normalize_doi(value).lower()


def load_doi_aliases(path: Path | None) -> dict[str, str]:
    if path is None or not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    records = payload.get("records", []) if isinstance(payload, dict) else []
    if not isinstance(records, list):
        raise ValueError("DOI alias registry must contain a records list")
    return {
        normalized_doi(row.get("alias_doi", "")): normalized_doi(row.get("canonical_doi", ""))
        for row in records
        if isinstance(row, dict)
        and normalized_doi(row.get("alias_doi", ""))
        and normalized_doi(row.get("canonical_doi", ""))
    }


def resolve_registered_doi(value: object, aliases: dict[str, str] | None = None) -> str:
    doi = normalized_doi(value)
    aliases = aliases or {}
    seen: set[str] = set()
    while doi in aliases and doi not in seen:
        seen.add(doi)
        doi = aliases[doi]
    if doi in seen:
        raise ValueError(f"Cyclic DOI alias registry entry involving {doi}")
    return doi


def canonicalize_funding_inputs(
    assertions: pd.DataFrame,
    attempts: pd.DataFrame | None,
    aliases: dict[str, str] | None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    aliases = aliases or {}
    canonical_assertions = assertions.copy()
    if not canonical_assertions.empty and "doi" in canonical_assertions.columns:
        canonical_assertions["doi"] = canonical_assertions["doi"].map(
            lambda value: resolve_registered_doi(value, aliases)
        )
        if "assertion_key" in canonical_assertions.columns:
            canonical_assertions["assertion_key"] = [
                assertion_identity(row) for row in canonical_assertions.to_dict("records")
            ]
            canonical_assertions = canonical_assertions.drop_duplicates(
                "assertion_key", keep="last"
            ).reset_index(drop=True)

    canonical_attempts = attempts.copy() if attempts is not None else pd.DataFrame()
    if not canonical_attempts.empty and "doi" in canonical_attempts.columns:
        canonical_attempts["doi"] = canonical_attempts["doi"].map(
            lambda value: resolve_registered_doi(value, aliases)
        )
    return canonical_assertions, canonical_attempts


def ordered_unique(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = clean(value)
        key = text.casefold()
        if not text or key in seen:
            continue
        seen.add(key)
        out.append(text)
    return out


def source_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def latest_attempts(attempts: pd.DataFrame) -> pd.DataFrame:
    if attempts.empty:
        return attempts.copy()
    frame = attempts.copy()
    frame["doi"] = frame["doi"].map(normalized_doi)
    frame["provider"] = frame["provider"].map(lambda value: clean(value).lower())
    frame["retrieved_at_utc"] = frame["retrieved_at_utc"].map(clean)
    frame = frame.sort_values(
        ["doi", "provider", "retrieved_at_utc"], kind="stable"
    )
    return frame.drop_duplicates(["doi", "provider"], keep="last")


def funding_summary_by_doi(
    assertions: pd.DataFrame,
    attempts: pd.DataFrame | None = None,
    doi_aliases: dict[str, str] | None = None,
) -> dict[str, dict]:
    assertions, attempts = canonicalize_funding_inputs(assertions, attempts, doi_aliases)
    attempted_dois: set[str] = set()
    if not attempts.empty and "doi" in attempts.columns:
        attempted_dois = {
            normalized_doi(value) for value in latest_attempts(attempts)["doi"] if normalized_doi(value)
        }

    grouped: dict[str, list[dict]] = defaultdict(list)
    if not assertions.empty:
        for row in assertions.to_dict("records"):
            doi = normalized_doi(row.get("doi", ""))
            if doi:
                grouped[doi].append(row)

    summaries: dict[str, dict] = {}
    for doi in sorted(attempted_dois | set(grouped)):
        rows = sorted(
            grouped.get(doi, []),
            key=lambda row: (
                PROVIDER_ORDER.get(clean(row.get("provider", "")).lower(), 99),
                clean(row.get("funder_name", "")).casefold(),
                clean(row.get("award_id", "")).casefold(),
                clean(row.get("assertion_key", "")),
            ),
        )
        funders = ordered_unique([clean(row.get("funder_name", "")) for row in rows])
        awards = ordered_unique([clean(row.get("award_id", "")) for row in rows])
        providers = ordered_unique(
            [clean(row.get("provider", "")).lower() for row in rows]
        )
        summaries[doi] = {
            "funders": " | ".join(funders),
            "grant_ids": " | ".join(awards),
            "funding_metadata_status": (
                "reported" if rows else "not_reported_by_queried_providers"
            ),
            "funding_providers": " | ".join(providers),
            "funding_assertion_count": len(rows),
            "funding_funder_count": len(funders),
            "funding_award_count": len(awards),
        }
    return summaries


def materialize_funding(
    papers: pd.DataFrame,
    assertions: pd.DataFrame,
    attempts: pd.DataFrame | None = None,
    doi_aliases: dict[str, str] | None = None,
) -> tuple[pd.DataFrame, dict]:
    if papers.empty and "doi" not in papers.columns:
        papers = papers.copy()
        papers["doi"] = pd.Series(dtype=str)
    if "doi" not in papers.columns:
        raise ValueError("Paper table must contain a doi column")
    out = papers.copy()
    count_columns = {
        "funding_assertion_count", "funding_funder_count", "funding_award_count"
    }
    for column in SUMMARY_COLUMNS:
        if column not in out.columns:
            out[column] = "" if column not in count_columns else 0
    for column in count_columns:
        out[column] = pd.to_numeric(out[column], errors="coerce").fillna(0).astype(int)

    summaries = funding_summary_by_doi(assertions, attempts, doi_aliases)
    covered = 0
    reported = 0
    for index, value in out["doi"].items():
        doi = resolve_registered_doi(value, doi_aliases)
        summary = summaries.get(doi)
        if summary is None:
            out.at[index, "funding_metadata_status"] = "not_enriched"
            continue
        covered += 1
        reported += int(summary["funding_metadata_status"] == "reported")
        for column, field_value in summary.items():
            out.at[index, column] = field_value

    report = {
        "paper_rows": len(out),
        "paper_dois": out["doi"].map(normalized_doi).nunique(),
        "papers_in_funding_scope": covered,
        "papers_with_reported_funding": reported,
        "papers_not_enriched": len(out) - covered,
        "funding_assertion_rows": len(assertions),
    }
    return out, report


def subset_assertions_for_papers(
    assertions: pd.DataFrame,
    papers: pd.DataFrame,
    doi_aliases: dict[str, str] | None = None,
) -> pd.DataFrame:
    assertions, _attempts = canonicalize_funding_inputs(assertions, None, doi_aliases)
    paper_dois = {
        resolve_registered_doi(value, doi_aliases)
        for value in papers.get("doi", [])
        if normalized_doi(value)
    }
    if assertions.empty:
        return pd.DataFrame(columns=list(ASSERTION_COLUMNS))
    out = assertions.copy()
    return out[out["doi"].isin(paper_dois)].reset_index(drop=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-table", type=Path, default=DEFAULT_CANDIDATES)
    parser.add_argument("--assertions", type=Path, default=DEFAULT_ASSERTIONS)
    parser.add_argument("--attempts", type=Path, default=DEFAULT_ATTEMPTS)
    parser.add_argument(
        "--doi-alias-registry", type=Path, default=DEFAULT_DOI_ALIAS_REGISTRY
    )
    parser.add_argument("--output-table", type=Path, default=DEFAULT_CANDIDATES)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    papers = pd.read_parquet(args.candidate_table)
    assertions = pd.read_parquet(args.assertions)
    attempts = pd.read_parquet(args.attempts) if args.attempts.is_file() else pd.DataFrame()
    materialized, report = materialize_funding(
        papers,
        assertions,
        attempts,
        load_doi_aliases(args.doi_alias_registry),
    )
    args.output_table.parent.mkdir(parents=True, exist_ok=True)
    materialized.to_parquet(args.output_table, index=False)
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
