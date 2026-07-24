import pandas as pd

from pipeline.ingest.materialize_paper_open_science import (
    materialize_open_science,
    subset_open_science_assertions,
)


def feature_row(doi: str, **overrides) -> dict:
    row = {
        "doi": doi,
        "has_registered_trial": False,
        "registered_trial_ids": "",
        "registered_trial_urls": "",
        "registered_trial_count": 0,
        "has_open_data": False,
        "open_data_resource_ids": "",
        "open_data_urls": "",
        "open_data_repositories": "",
        "open_data_resource_count": 0,
        "has_shared_code": False,
        "shared_code_resource_ids": "",
        "shared_code_urls": "",
        "shared_code_repositories": "",
        "shared_code_resource_count": 0,
        "has_preregistered": False,
        "preregistration_ids": "",
        "preregistration_urls": "",
        "preregistration_repositories": "",
        "preregistration_count": 0,
        "open_science_features": "",
        "feature_count": 0,
        "assertion_count": 0,
        "evidence_providers": "",
        "evidence_source_types": "",
        "has_fulltext_evidence_source": False,
        "open_science_enrichment_status": "no_feature_asserted",
        "retrieval_run_id": "run-1",
        "retrieved_at_utc": "2026-07-23T00:00:00Z",
    }
    row.update(overrides)
    return row


def test_materializes_typed_open_science_fields_by_doi() -> None:
    papers = pd.DataFrame(
        [{"doi": "10.1/a"}, {"doi": "10.1/b"}, {"doi": "10.1/missing"}]
    )
    features = pd.DataFrame(
        [
            feature_row(
                "10.1/a",
                has_registered_trial=True,
                registered_trial_ids="NCT01234567",
                registered_trial_count=1,
                open_science_features="registered_trial",
                feature_count=1,
                assertion_count=2,
                open_science_enrichment_status="feature_asserted",
            ),
            feature_row(
                "10.1/b",
                has_open_data=True,
                open_data_resource_ids="10.5281/zenodo.123",
                open_data_repositories="zenodo",
                open_data_resource_count=1,
                open_science_features="open_data",
                feature_count=1,
                assertion_count=1,
                open_science_enrichment_status="feature_asserted",
            ),
        ]
    )

    out, report = materialize_open_science(papers, features)

    assert bool(out.loc[0, "has_registered_trial"]) is True
    assert out.loc[0, "registered_trial_ids"] == "NCT01234567"
    assert bool(out.loc[1, "has_open_data"]) is True
    assert out.loc[1, "open_data_repositories"] == "zenodo"
    assert bool(out.loc[2, "has_registered_trial"]) is False
    assert out.loc[2, "open_science_enrichment_status"] == "not_enriched"
    assert report["papers_in_open_science_scope"] == 2
    assert report["papers_with_any_open_science_feature"] == 2


def test_registered_doi_aliases_join_features_and_assertions() -> None:
    aliases = {"10.1/alias": "10.1/canonical"}
    papers = pd.DataFrame([{"doi": "10.1/alias"}])
    features = pd.DataFrame(
        [
            feature_row(
                "10.1/canonical",
                has_preregistered=True,
                preregistration_ids="https://osf.io/abcd1",
                preregistration_count=1,
                open_science_features="preregistered",
                feature_count=1,
                assertion_count=1,
                open_science_enrichment_status="feature_asserted",
            )
        ]
    )
    assertions = pd.DataFrame(
        [{"doi": "10.1/canonical", "feature": "preregistered"}]
    )

    out, _report = materialize_open_science(papers, features, aliases)
    subset = subset_open_science_assertions(assertions, papers, aliases)

    assert bool(out.loc[0, "has_preregistered"]) is True
    assert len(subset) == 1
    assert subset.loc[0, "doi"] == "10.1/canonical"
