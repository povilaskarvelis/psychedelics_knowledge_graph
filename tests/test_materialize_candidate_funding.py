from __future__ import annotations

import pandas as pd

from pipeline.ingest.materialize_candidate_funding import (
    funding_summary_by_doi,
    materialize_funding,
    subset_assertions_for_papers,
)


def test_provider_funding_projection_is_compact_and_preserves_complementarity():
    assertions = pd.DataFrame(
        [
            {"doi": "10.1/a", "provider": "pubmed", "funder_name": "NIH", "award_id": "R01-1", "assertion_key": "3"},
            {"doi": "10.1/a", "provider": "openalex", "funder_name": "National Institutes of Health", "award_id": "", "assertion_key": "1"},
            {"doi": "10.1/a", "provider": "crossref", "funder_name": "Wellcome", "award_id": "WT-2", "assertion_key": "2"},
        ]
    )
    attempts = pd.DataFrame(
        [
            {"doi": "10.1/a", "provider": "openalex", "retrieved_at_utc": "2026-01-01", "result_status": "funding_found"},
            {"doi": "10.1/b", "provider": "openalex", "retrieved_at_utc": "2026-01-01", "result_status": "no_funding_metadata"},
        ]
    )

    summaries = funding_summary_by_doi(assertions, attempts)

    assert summaries["10.1/a"]["funding_metadata_status"] == "reported"
    assert summaries["10.1/a"]["funders"] == "National Institutes of Health | Wellcome | NIH"
    assert summaries["10.1/a"]["grant_ids"] == "WT-2 | R01-1"
    assert summaries["10.1/a"]["funding_providers"] == "openalex | crossref | pubmed"
    assert summaries["10.1/b"]["funding_metadata_status"] == "not_reported_by_queried_providers"


def test_materialization_overwrites_only_enriched_scope_and_subsets_assertions():
    papers = pd.DataFrame(
        [
            {"doi": "10.1/a", "funders": "stale"},
            {"doi": "10.1/b", "funders": "legacy outside scope"},
        ]
    )
    assertions = pd.DataFrame(
        [{"doi": "10.1/a", "provider": "openalex", "funder_name": "Funder A", "award_id": "A-1", "assertion_key": "1"}]
    )
    attempts = pd.DataFrame(
        [{"doi": "10.1/a", "provider": "openalex", "retrieved_at_utc": "2026-01-01", "result_status": "funding_found"}]
    )

    out, report = materialize_funding(papers, assertions, attempts)

    assert out.loc[0, "funders"] == "Funder A"
    assert out.loc[0, "grant_ids"] == "A-1"
    assert out.loc[1, "funders"] == "legacy outside scope"
    assert out.loc[1, "funding_metadata_status"] == "not_enriched"
    assert report["papers_with_reported_funding"] == 1
    assert len(subset_assertions_for_papers(assertions, papers.iloc[[0]])) == 1


def test_registered_alias_funding_attaches_to_canonical_paper_identity():
    papers = pd.DataFrame([{"doi": "10.1/article"}])
    assertions = pd.DataFrame(
        [
            {
                "doi": "10.1/repository",
                "provider": "openalex",
                "source_field": "funders",
                "funder_name": "Funder A",
                "award_id": "",
                "assertion_key": "old-key",
            }
        ]
    )
    attempts = pd.DataFrame(
        [
            {
                "doi": "10.1/repository",
                "provider": "openalex",
                "retrieved_at_utc": "2026-01-01",
                "result_status": "funding_found",
            }
        ]
    )
    aliases = {"10.1/repository": "10.1/article"}

    out, report = materialize_funding(papers, assertions, attempts, aliases)
    scoped = subset_assertions_for_papers(assertions, papers, aliases)

    assert out.loc[0, "funding_metadata_status"] == "reported"
    assert out.loc[0, "funders"] == "Funder A"
    assert report["papers_not_enriched"] == 0
    assert scoped.loc[0, "doi"] == "10.1/article"
    assert scoped.loc[0, "assertion_key"] != "old-key"
