from pathlib import Path

import pandas as pd

from pipeline.ingest.enrich_paper_metadata import read_table, write_table
from pipeline.ingest.repair_abstract_contamination import (
    apply_repairs,
    build_contamination_scope,
    valid_recovered_rows,
)


def contaminated_text() -> str:
    return "Introduction Methods Results Discussion References " + ("article body " * 500)


def test_scope_finds_openalex_contamination_and_uses_valid_metadata_replacement(tmp_path: Path) -> None:
    candidates = tmp_path / "candidate.parquet"
    metadata = tmp_path / "metadata.parquet"
    pd.DataFrame(
        [
            {
                "doi": "10.1000/one",
                "study_title": "Paper",
                "abstract": contaminated_text(),
                "discovery_providers": "pubmed | openalex",
                "pmid": "1",
            }
        ]
    ).to_parquet(candidates, index=False)
    write_table(
        metadata,
        [
            {
                "doi": "10.1000/one",
                "study_title": "Paper",
                "abstract": "Valid PubMed abstract.",
                "metadata_provider": "pubmed",
            }
        ],
    )

    scope = build_contamination_scope(candidates, metadata, allowed_dois=None)

    assert scope["doi"].tolist() == ["10.1000/one"]
    assert scope.iloc[0]["candidate_quality"] == "contaminated"
    assert scope.iloc[0]["local_replacement_abstract"] == "Valid PubMed abstract."
    assert not bool(scope.iloc[0]["recovery_required"])


def test_scope_is_idempotent_after_candidate_matches_trusted_metadata(tmp_path: Path) -> None:
    candidates = tmp_path / "candidate.parquet"
    metadata = tmp_path / "metadata.parquet"
    long_pubmed_abstract = "BACKGROUND " + ("Long structured abstract finding. " * 220)
    pd.DataFrame(
        [
            {
                "doi": "10.1000/one",
                "study_title": "Paper",
                "abstract": long_pubmed_abstract,
                "discovery_providers": "pubmed | openalex",
            }
        ]
    ).to_parquet(candidates, index=False)
    write_table(
        metadata,
        [
            {
                "doi": "10.1000/one",
                "study_title": "Paper",
                "abstract": long_pubmed_abstract,
                "metadata_provider": "pubmed",
            }
        ],
    )

    scope = build_contamination_scope(candidates, metadata, allowed_dois=None)

    assert scope.empty


def test_recovered_openalex_fulltext_is_rejected_but_pubmed_is_accepted() -> None:
    scope = pd.DataFrame([{"doi": "10.1000/one", "study_title": "Paper"}])

    selected, rejected = valid_recovered_rows(
        [
            {
                "doi": "10.1000/one",
                "provider": "openalex",
                "status": "recovered",
                "abstract": contaminated_text(),
            },
            {
                "doi": "10.1000/one",
                "provider": "pubmed",
                "status": "recovered",
                "abstract": "Valid abstract.",
            },
        ],
        scope,
    )

    assert selected["10.1000/one"]["provider"] == "pubmed"
    assert len(rejected) == 1


def test_apply_repairs_replaces_recovered_and_blanks_unresolved(tmp_path: Path) -> None:
    candidates = tmp_path / "candidate.parquet"
    metadata = tmp_path / "metadata.parquet"
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    pd.DataFrame(
        [
            {
                "doi": "10.1000/recovered",
                "study_title": "Recovered",
                "abstract": contaminated_text(),
                "discovery_providers": "openalex",
                "metadata_provider": "",
                "metadata_provider_chain": "",
                "metadata_providers_queried": "",
                "metadata_lookup_error": "",
                "metadata_missing_reason": "",
                "metadata_enrichment_status": "",
                "metadata_enrichment_run_id": "",
                "metadata_enriched_at_utc": "",
            },
            {
                "doi": "10.1000/unresolved",
                "study_title": "Unresolved",
                "abstract": contaminated_text(),
                "discovery_providers": "openalex",
                "metadata_provider": "",
                "metadata_provider_chain": "",
                "metadata_providers_queried": "",
                "metadata_lookup_error": "",
                "metadata_missing_reason": "",
                "metadata_enrichment_status": "",
                "metadata_enrichment_run_id": "",
                "metadata_enriched_at_utc": "",
            },
        ]
    ).to_parquet(candidates, index=False)
    write_table(metadata, [])
    scope = build_contamination_scope(candidates, metadata, allowed_dois=None)

    report = apply_repairs(
        candidates_path=candidates,
        metadata_path=metadata,
        scope=scope,
        recovered_by_doi={
            "10.1000/recovered": {
                "doi": "10.1000/recovered",
                "provider": "pubmed",
                "abstract": "Recovered abstract.",
            }
        },
        run_id="repair_test",
        run_dir=run_dir,
    )

    candidate_rows = pd.read_parquet(candidates).set_index("doi")
    metadata_rows = {row["doi"]: row for row in read_table(metadata)}
    assert candidate_rows.loc["10.1000/recovered", "abstract"] == "Recovered abstract."
    assert candidate_rows.loc["10.1000/unresolved", "abstract"] == ""
    assert metadata_rows["10.1000/recovered"]["abstract"] == "Recovered abstract."
    assert report["action_counts"]["recovered_from_provider"] == 1
    assert report["action_counts"]["invalidated_unresolved_contamination"] == 1


def test_apply_repairs_extracts_bounded_abstract_before_blanking(tmp_path: Path) -> None:
    candidates = tmp_path / "candidate.parquet"
    metadata = tmp_path / "metadata.parquet"
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    fulltext = ("This abstract reports a result and conclusion. " * 15) + " Introduction " + ("Article body. " * 500)
    pd.DataFrame(
        [
            {
                "doi": "10.1000/salvage",
                "study_title": "A study",
                "abstract": fulltext,
                "discovery_providers": "openalex",
                "metadata_provider": "",
                "metadata_provider_chain": "",
                "metadata_providers_queried": "",
                "metadata_lookup_error": "",
                "metadata_missing_reason": "",
                "metadata_enrichment_status": "",
                "metadata_enrichment_run_id": "",
                "metadata_enriched_at_utc": "",
            }
        ]
    ).to_parquet(candidates, index=False)
    write_table(metadata, [])
    scope = build_contamination_scope(candidates, metadata, allowed_dois=None)

    report = apply_repairs(
        candidates_path=candidates,
        metadata_path=metadata,
        scope=scope,
        recovered_by_doi={},
        run_id="repair_test",
        run_dir=run_dir,
    )

    repaired = pd.read_parquet(candidates).iloc[0]["abstract"]
    assert "Introduction" not in repaired
    assert "abstract reports a result" in repaired
    assert report["action_counts"]["extracted_identifiable_abstract_section"] == 1
