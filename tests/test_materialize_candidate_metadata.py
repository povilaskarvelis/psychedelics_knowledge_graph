import json
import tempfile
from pathlib import Path

import pandas as pd
import pytest

from pipeline.ingest.enrich_paper_metadata import write_table
from pipeline.ingest.materialize_candidate_metadata import materialize_candidate_metadata


def test_materialization_fills_blanks_without_overriding_canonical_candidate_values() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        candidates = root / "candidate_papers.parquet"
        metadata = root / "paper_metadata_enrichment.parquet"
        overrides = root / "overrides.json"
        pd.DataFrame(
            [
                {"doi": "10.1000/missing", "study_title": "", "abstract": ""},
                {
                    "doi": "10.1000/canonical",
                    "study_title": "Canonical title",
                    "abstract": "Canonical candidate abstract.",
                },
            ]
        ).to_parquet(candidates, index=False)
        write_table(
            metadata,
            [
                {
                    "doi": "10.1000/missing",
                    "study_title": "Recovered title",
                    "abstract": "Recovered abstract.",
                    "metadata_provider": "pmc",
                },
                {
                    "doi": "10.1000/canonical",
                    "study_title": "Stale cached title",
                    "abstract": "Stale cached abstract.",
                    "metadata_provider": "openalex",
                },
            ],
        )
        overrides.write_text('{"records": []}\n', encoding="utf-8")

        report = materialize_candidate_metadata(
            candidate_table=candidates,
            metadata_table=metadata,
            run_id="test_materialization",
            fields=("study_title", "abstract", "metadata_provider"),
            curated_overrides_path=overrides,
        )
        out = pd.read_parquet(candidates).set_index("doi")

    assert out.loc["10.1000/missing", "study_title"] == "Recovered title"
    assert out.loc["10.1000/missing", "abstract"] == "Recovered abstract."
    assert out.loc["10.1000/canonical", "study_title"] == "Canonical title"
    assert out.loc["10.1000/canonical", "abstract"] == "Canonical candidate abstract."
    assert out.loc["10.1000/canonical", "metadata_provider"] == "openalex"
    assert report["filled_cells"] == 4
    assert report["overwritten_cells"] == 0
    assert report["changed_candidate_rows"] == 2


def test_fresh_scoped_materialization_can_overwrite_and_curated_override_wins_last() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        candidates = root / "candidate_papers.parquet"
        metadata = root / "paper_metadata_enrichment.parquet"
        overrides = root / "overrides.json"
        pd.DataFrame(
            [
                {"doi": "10.1000/fresh", "abstract": "Old candidate abstract."},
                {"doi": "10.1000/curated", "abstract": "Old candidate abstract."},
                {"doi": "10.1000/outside", "abstract": "Do not touch."},
            ]
        ).to_parquet(candidates, index=False)
        write_table(
            metadata,
            [
                {"doi": "10.1000/fresh", "abstract": "Fresh provider abstract."},
                {"doi": "10.1000/curated", "abstract": "Wrong provider abstract."},
                {"doi": "10.1000/outside", "abstract": "Outside provider abstract."},
            ],
        )
        overrides.write_text(
            json.dumps(
                {
                    "records": [
                        {
                            "doi": "10.1000/curated",
                            "fields": {"abstract": "Verified curated abstract."},
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

        report = materialize_candidate_metadata(
            candidate_table=candidates,
            metadata_table=metadata,
            run_id="test_refresh",
            fields=("abstract",),
            scoped_dois={"10.1000/fresh", "10.1000/curated"},
            overwrite_existing=True,
            curated_overrides_path=overrides,
        )
        out = pd.read_parquet(candidates).set_index("doi")

    assert out.loc["10.1000/fresh", "abstract"] == "Fresh provider abstract."
    assert out.loc["10.1000/curated", "abstract"] == "Verified curated abstract."
    assert out.loc["10.1000/outside", "abstract"] == "Do not touch."
    assert report["overwritten_cells"] == 2
    assert report["curated_override_cells"] == 1


def test_scoped_identity_repair_can_clear_an_unverified_contaminated_field() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        candidates = root / "candidate_papers.parquet"
        metadata = root / "paper_metadata_enrichment.parquet"
        pd.DataFrame(
            [
                {
                    "doi": "10.1000/contaminated",
                    "study_title": "Verified title",
                    "abstract": "Abstract belonging to an adjacent paper.",
                },
                {
                    "doi": "10.1000/outside",
                    "study_title": "Outside title",
                    "abstract": "Do not clear this abstract.",
                },
            ]
        ).to_parquet(candidates, index=False)
        write_table(
            metadata,
            [
                {
                    "doi": "10.1000/contaminated",
                    "study_title": "Verified title",
                    "abstract": "",
                },
                {
                    "doi": "10.1000/outside",
                    "study_title": "Outside title",
                    "abstract": "",
                },
            ],
        )

        report = materialize_candidate_metadata(
            candidate_table=candidates,
            metadata_table=metadata,
            run_id="test_identity_repair",
            fields=("study_title", "abstract"),
            scoped_dois={"10.1000/contaminated"},
            overwrite_existing=True,
            clear_blank_fields=("abstract",),
            curated_overrides_path=None,
        )
        out = pd.read_parquet(candidates).set_index("doi")

    assert out.loc["10.1000/contaminated", "abstract"] == ""
    assert out.loc["10.1000/outside", "abstract"] == "Do not clear this abstract."
    assert report["cleared_cells"] == 1
    assert report["overwritten_cells"] == 0
    assert report["field_clears"] == {"abstract": 1}


def test_materialization_rejects_metadata_rows_missing_from_candidate_ledger() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        candidates = root / "candidate_papers.parquet"
        metadata = root / "paper_metadata_enrichment.parquet"
        pd.DataFrame([{"doi": "10.1000/known", "abstract": ""}]).to_parquet(
            candidates, index=False
        )
        write_table(metadata, [{"doi": "10.1000/orphan", "abstract": "Orphan abstract."}])

        try:
            materialize_candidate_metadata(
                candidate_table=candidates,
                metadata_table=metadata,
                run_id="test_orphan",
                fields=("abstract",),
                scoped_dois={"10.1000/orphan"},
                curated_overrides_path=None,
            )
        except ValueError as error:
            message = str(error)
        else:
            raise AssertionError("Expected orphan metadata DOI validation failure")

    assert "missing from the canonical candidate ledger" in message


def test_materialization_rejects_new_year_date_conflict_before_writing() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        candidates = root / "candidate_papers.parquet"
        metadata = root / "paper_metadata_enrichment.parquet"
        pd.DataFrame(
            [
                {
                    "doi": "10.1000/conflict",
                    "study_year": "2023",
                    "publication_date": "2023-01-01",
                }
            ]
        ).to_parquet(candidates, index=False)
        write_table(metadata, [{"doi": "10.1000/conflict", "study_year": "1885"}])

        with pytest.raises(ValueError, match="inconsistent bibliographic timing"):
            materialize_candidate_metadata(
                candidate_table=candidates,
                metadata_table=metadata,
                run_id="test_conflict",
                fields=("study_year",),
                scoped_dois={"10.1000/conflict"},
                overwrite_existing=True,
                curated_overrides_path=None,
            )

        out = pd.read_parquet(candidates).set_index("doi")

    assert out.loc["10.1000/conflict", "study_year"] == "2023"
