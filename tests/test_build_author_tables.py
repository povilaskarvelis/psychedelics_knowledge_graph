import pandas as pd
import pytest
from pathlib import Path

import pipeline.kg.build_author_tables as author_tables

from pipeline.kg.build_author_tables import (
    apply_orcid_identities,
    build_tables,
    require_offline_cache_coverage,
    refresh_cache_for_papers,
    require_structured_authorship_coverage,
)


def test_cache_refresh_retries_errors_but_preserves_terminal_entries(tmp_path, monkeypatch) -> None:
    papers = pd.DataFrame(
        [
            {"doi": "10.1000/error"},
            {"doi": "10.1000/ok"},
            {"doi": "10.1000/not-found"},
            {"doi": "10.1000/missing"},
        ]
    )
    cache = {
        "works_by_doi": {
            "10.1000/error": {"status": "error"},
            "10.1000/ok": {"status": "ok", "authorships": [{"display_name": "A"}]},
            "10.1000/not-found": {"status": "not_found"},
        }
    }
    requested = []

    def fake_fetch(_client, dois):
        requested.extend(dois)
        return {
            doi: {"status": "ok", "doi": doi, "authorships": [{"display_name": "A"}]}
            for doi in dois
        }

    monkeypatch.setattr(author_tables, "fetch_openalex_batch", fake_fetch)
    refreshed = refresh_cache_for_papers(
        papers,
        cache,
        client=object(),
        cache_path=tmp_path / "cache.json",
        batch_size=10,
        refresh=False,
        checkpoint_every=0,
    )

    assert requested == ["10.1000/error", "10.1000/missing"]
    assert refreshed["works_by_doi"]["10.1000/not-found"]["status"] == "not_found"


def test_exact_name_local_author_aliases_to_single_structured_identity() -> None:
    papers = pd.DataFrame(
        [
            {
                "paper_id": "paper:openalex",
                "doi": "10.1000/openalex",
                "openalex_id": "",
                "authors": "",
            },
            {
                "paper_id": "paper:fallback",
                "doi": "10.1000/fallback",
                "openalex_id": "",
                "authors": "Ada Example; Ben Fallback",
            },
        ]
    )
    cache = {
        "works_by_doi": {
            "10.1000/openalex": {
                "status": "ok",
                "work_openalex_id": "https://openalex.org/W1",
                "authorships": [
                    {
                        "position": 1,
                        "author_position": "first",
                        "display_name": "Ada Example",
                        "openalex_author_id": "https://openalex.org/A1",
                        "orcid": "",
                    }
                ],
            },
            "10.1000/fallback": {"status": "not_found", "doi": "10.1000/fallback"},
        }
    }

    authors, paper_authors, report = build_tables(papers, cache)

    ada_rows = paper_authors[paper_authors["display_name"].eq("Ada Example")]
    assert set(ada_rows["author_id"]) == {"openalex:A1"}
    assert "name_alias_to_openalex_author_id" in set(ada_rows["identity_confidence"])
    assert len(authors[authors["display_name"].eq("Ada Example")]) == 1
    assert report["name_alias_resolution_counts"] == {
        "name_alias_authorship_rows": 1,
        "name_alias_author_ids": 1,
        "name_alias_names": 1,
    }


def test_exact_name_local_author_does_not_alias_when_structured_name_is_ambiguous() -> None:
    papers = pd.DataFrame(
        [
            {"paper_id": "paper:a", "doi": "10.1000/a", "openalex_id": "", "authors": ""},
            {"paper_id": "paper:b", "doi": "10.1000/b", "openalex_id": "", "authors": ""},
            {
                "paper_id": "paper:fallback",
                "doi": "10.1000/fallback",
                "openalex_id": "",
                "authors": "Common Name",
            },
        ]
    )
    cache = {
        "works_by_doi": {
            "10.1000/a": {
                "status": "ok",
                "work_openalex_id": "https://openalex.org/W1",
                "authorships": [
                    {
                        "position": 1,
                        "author_position": "first",
                        "display_name": "Common Name",
                        "openalex_author_id": "https://openalex.org/A1",
                        "orcid": "",
                    }
                ],
            },
            "10.1000/b": {
                "status": "ok",
                "work_openalex_id": "https://openalex.org/W2",
                "authorships": [
                    {
                        "position": 1,
                        "author_position": "first",
                        "display_name": "Common Name",
                        "openalex_author_id": "https://openalex.org/A2",
                        "orcid": "",
                    }
                ],
            },
            "10.1000/fallback": {"status": "not_found", "doi": "10.1000/fallback"},
        }
    }

    authors, paper_authors, report = build_tables(papers, cache)

    common_rows = paper_authors[paper_authors["display_name"].eq("Common Name")]
    author_ids = set(common_rows["author_id"])
    assert {"openalex:A1", "openalex:A2"}.issubset(author_ids)
    assert len([author_id for author_id in author_ids if author_id.startswith("local_author:")]) == 1
    assert len(authors[authors["canonical_name"].eq("common name")]) == 3
    assert report["name_alias_resolution_counts"] == {
        "name_alias_authorship_rows": 0,
        "name_alias_author_ids": 0,
        "name_alias_names": 0,
    }


def test_offline_build_rejects_an_empty_cache() -> None:
    papers = pd.DataFrame([{"paper_id": "paper:a", "doi": "10.1000/a", "authors": "Ada Example"}])

    with pytest.raises(RuntimeError, match="Offline author resolution refused"):
        require_offline_cache_coverage(papers, {"works_by_doi": {}}, Path("missing-cache.json"))


def test_release_build_rejects_name_only_authorships() -> None:
    paper_authors = pd.DataFrame([{"author_id": "local_author:ada"}])

    with pytest.raises(RuntimeError, match="Author table build refused"):
        require_structured_authorship_coverage(paper_authors)


def test_release_build_accepts_structured_authorships_above_threshold() -> None:
    paper_authors = pd.DataFrame(
        [{"author_id": "openalex:A1"}] * 19 + [{"author_id": "local_author:unresolved"}]
    )

    assert require_structured_authorship_coverage(paper_authors) == (19, 20, 0.95)


def test_orcid_canonicalizes_and_merges_openalex_profiles() -> None:
    paper_authors = pd.DataFrame(
        [
            {
                "author_id": "openalex:A1",
                "openalex_author_id": "https://openalex.org/A1",
                "orcid": "0000-0001-2345-6789",
                "canonical_name": "ada example",
                "identity_confidence": "openalex_author_id",
            },
            {
                "author_id": "openalex:A1",
                "openalex_author_id": "https://openalex.org/A1",
                "orcid": "",
                "canonical_name": "a example",
                "identity_confidence": "openalex_author_id",
            },
            {
                "author_id": "openalex:A2",
                "openalex_author_id": "https://openalex.org/A2",
                "orcid": "0000-0001-2345-6789",
                "canonical_name": "ada example",
                "identity_confidence": "openalex_author_id",
            },
        ]
    )

    resolved, stats = apply_orcid_identities(paper_authors)

    assert set(resolved["author_id"]) == {"orcid:0000-0001-2345-6789"}
    assert stats["openalex_profiles_linked_to_orcid"] == 2
    assert stats["openalex_profiles_merged_by_shared_orcid"] == 1
    assert stats["authorship_rows_canonicalized_to_orcid"] == 3


def test_conflicting_orcids_do_not_canonicalize_an_openalex_profile() -> None:
    paper_authors = pd.DataFrame(
        [
            {
                "author_id": "openalex:A1",
                "openalex_author_id": "https://openalex.org/A1",
                "orcid": "0000-0001-2345-6789",
                "canonical_name": "ada example",
                "identity_confidence": "openalex_author_id",
            },
            {
                "author_id": "openalex:A1",
                "openalex_author_id": "https://openalex.org/A1",
                "orcid": "0000-0002-2345-6789",
                "canonical_name": "ada example",
                "identity_confidence": "openalex_author_id",
            },
        ]
    )

    resolved, stats = apply_orcid_identities(paper_authors)

    assert set(resolved["author_id"]) == {"openalex:A1"}
    assert set(resolved["orcid"]) == {""}
    assert set(resolved["identity_confidence"]) == {"openalex_author_id_orcid_conflict"}
    assert stats["openalex_profiles_with_conflicting_orcids"] == 1

    with pytest.raises(RuntimeError, match="Author table build refused"):
        require_structured_authorship_coverage(resolved)
