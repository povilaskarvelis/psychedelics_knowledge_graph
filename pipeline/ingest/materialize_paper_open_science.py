#!/usr/bin/env python3
"""Project normalized open-science feature summaries onto paper tables.

The DOI-keyed enrichment tables remain the source of truth. This module adds a
compact, typed paper-metadata projection for KG and browser assembly without
turning the features into scientific graph nodes or edges.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from pipeline.ingest.materialize_candidate_funding import (
    DEFAULT_DOI_ALIAS_REGISTRY,
    load_doi_aliases,
    resolve_registered_doi,
)
from pipeline.ingest.metadata_utils import normalize
from pipeline.ingest.open_science_features import ASSERTION_COLUMNS


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PAPERS = ROOT / "data" / "processed" / "corpus" / "candidate_papers.parquet"
DEFAULT_FEATURES = (
    ROOT / "data" / "processed" / "corpus" / "paper_open_science_features.parquet"
)
DEFAULT_ASSERTIONS = (
    ROOT / "data" / "processed" / "corpus" / "paper_open_science_assertions.parquet"
)

SOURCE_TO_PAPER_FIELDS = {
    "has_registered_trial": "has_registered_trial",
    "registered_trial_ids": "registered_trial_ids",
    "registered_trial_urls": "registered_trial_urls",
    "registered_trial_count": "registered_trial_count",
    "has_open_data": "has_open_data",
    "open_data_resource_ids": "open_data_resource_ids",
    "open_data_urls": "open_data_urls",
    "open_data_repositories": "open_data_repositories",
    "open_data_resource_count": "open_data_resource_count",
    "has_shared_code": "has_shared_code",
    "shared_code_resource_ids": "shared_code_resource_ids",
    "shared_code_urls": "shared_code_urls",
    "shared_code_repositories": "shared_code_repositories",
    "shared_code_resource_count": "shared_code_resource_count",
    "has_preregistered": "has_preregistered",
    "preregistration_ids": "preregistration_ids",
    "preregistration_urls": "preregistration_urls",
    "preregistration_repositories": "preregistration_repositories",
    "preregistration_count": "preregistration_count",
    "open_science_features": "open_science_features",
    "feature_count": "open_science_feature_count",
    "assertion_count": "open_science_assertion_count",
    "evidence_providers": "open_science_evidence_providers",
    "evidence_source_types": "open_science_evidence_source_types",
    "has_fulltext_evidence_source": "open_science_has_fulltext_evidence_source",
    "open_science_enrichment_status": "open_science_enrichment_status",
    "retrieval_run_id": "open_science_retrieval_run_id",
    "retrieved_at_utc": "open_science_retrieved_at_utc",
}

BOOLEAN_PAPER_FIELDS = {
    "has_registered_trial",
    "has_open_data",
    "has_shared_code",
    "has_preregistered",
    "open_science_has_fulltext_evidence_source",
}
COUNT_PAPER_FIELDS = {
    "registered_trial_count",
    "open_data_resource_count",
    "shared_code_resource_count",
    "preregistration_count",
    "open_science_feature_count",
    "open_science_assertion_count",
}
PAPER_FIELDS = tuple(SOURCE_TO_PAPER_FIELDS.values())


def clean(value: object) -> str:
    return normalize(value)


def canonical_feature_rows(
    features: pd.DataFrame,
    doi_aliases: dict[str, str] | None = None,
) -> pd.DataFrame:
    if "doi" not in features.columns:
        raise ValueError("Open-science feature table must contain a doi column")
    missing = sorted(set(SOURCE_TO_PAPER_FIELDS) - set(features.columns))
    if missing:
        raise ValueError(
            "Open-science feature table is missing required columns: "
            + ", ".join(missing)
        )

    out = features.copy()
    out["doi"] = out["doi"].map(
        lambda value: resolve_registered_doi(value, doi_aliases)
    )
    out = out[out["doi"].ne("")].copy()
    if "retrieved_at_utc" not in out.columns:
        out["retrieved_at_utc"] = ""
    out["_source_order"] = range(len(out))
    out = out.sort_values(
        ["doi", "retrieved_at_utc", "_source_order"], kind="stable"
    )
    return (
        out.drop_duplicates("doi", keep="last")
        .drop(columns=["_source_order"])
        .reset_index(drop=True)
    )


def materialize_open_science(
    papers: pd.DataFrame,
    features: pd.DataFrame,
    doi_aliases: dict[str, str] | None = None,
) -> tuple[pd.DataFrame, dict]:
    if "doi" not in papers.columns:
        raise ValueError("Paper table must contain a doi column")

    out = papers.copy()
    for field in PAPER_FIELDS:
        if field in BOOLEAN_PAPER_FIELDS:
            out[field] = False
        elif field in COUNT_PAPER_FIELDS:
            out[field] = 0
        else:
            out[field] = ""
    out["open_science_enrichment_status"] = "not_enriched"

    canonical = canonical_feature_rows(features, doi_aliases)
    summaries = canonical.set_index("doi", drop=False).to_dict("index")
    covered = 0
    for index, value in out["doi"].items():
        doi = resolve_registered_doi(value, doi_aliases)
        summary = summaries.get(doi)
        if summary is None:
            continue
        covered += 1
        for source_field, paper_field in SOURCE_TO_PAPER_FIELDS.items():
            value = summary.get(source_field)
            if paper_field in BOOLEAN_PAPER_FIELDS:
                value = bool(value) if not pd.isna(value) else False
            elif paper_field in COUNT_PAPER_FIELDS:
                value = int(value) if not pd.isna(value) and clean(value) else 0
            else:
                value = clean(value)
            out.at[index, paper_field] = value

    feature_counts = {
        field: int(out[field].fillna(False).astype(bool).sum())
        for field in (
            "has_registered_trial",
            "has_open_data",
            "has_shared_code",
            "has_preregistered",
        )
    }
    report = {
        "paper_rows": len(out),
        "papers_in_open_science_scope": covered,
        "papers_not_enriched": len(out) - covered,
        "papers_with_any_open_science_feature": int(
            out[
                [
                    "has_registered_trial",
                    "has_open_data",
                    "has_shared_code",
                    "has_preregistered",
                ]
            ]
            .fillna(False)
            .astype(bool)
            .any(axis=1)
            .sum()
        ),
        "feature_counts": feature_counts,
    }
    return out, report


def subset_open_science_assertions(
    assertions: pd.DataFrame,
    papers: pd.DataFrame,
    doi_aliases: dict[str, str] | None = None,
) -> pd.DataFrame:
    if assertions.empty:
        return pd.DataFrame(columns=list(ASSERTION_COLUMNS))
    if "doi" not in assertions.columns:
        raise ValueError("Open-science assertion table must contain a doi column")
    paper_dois = {
        resolve_registered_doi(value, doi_aliases)
        for value in papers.get("doi", [])
        if resolve_registered_doi(value, doi_aliases)
    }
    out = assertions.copy()
    out["doi"] = out["doi"].map(
        lambda value: resolve_registered_doi(value, doi_aliases)
    )
    return out[out["doi"].isin(paper_dois)].reset_index(drop=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--papers", type=Path, default=DEFAULT_PAPERS)
    parser.add_argument("--features", type=Path, default=DEFAULT_FEATURES)
    parser.add_argument(
        "--doi-alias-registry", type=Path, default=DEFAULT_DOI_ALIAS_REGISTRY
    )
    parser.add_argument("--output-table", type=Path, default=DEFAULT_PAPERS)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    papers = pd.read_parquet(args.papers)
    features = pd.read_parquet(args.features)
    materialized, report = materialize_open_science(
        papers,
        features,
        load_doi_aliases(args.doi_alias_registry),
    )
    args.output_table.parent.mkdir(parents=True, exist_ok=True)
    materialized.to_parquet(args.output_table, index=False)
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
