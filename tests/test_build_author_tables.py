import pandas as pd

from pipeline.kg.build_author_tables import build_tables


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
