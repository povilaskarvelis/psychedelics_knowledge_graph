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


def test_reviewed_profiles_merge_and_keep_review_provenance():
    overrides = author_tables.load_identity_overrides(author_tables.DEFAULT_IDENTITY_OVERRIDES)
    profile_ids = [
        'A5138024465', 'A5121018397', 'A5120966307',
        'A5140218191', 'A5137807234', 'A5139833133',
    ]
    rows = [{
        'author_id': f'openalex:{profile}',
        'openalex_author_id': f'https://openalex.org/{profile}',
        'orcid': '', 'canonical_name': 'robin l. carhart‐harris',
        'identity_confidence': 'openalex_author_id',
    } for profile in profile_ids]
    rows.append({
        'author_id': author_tables.local_author_id('Robin Carhart-Harris'),
        'openalex_author_id': '', 'orcid': '',
        'canonical_name': 'robin carhart-harris', 'identity_confidence': 'name_only',
    })
    resolved, _ = apply_orcid_identities(pd.DataFrame(rows), overrides)
    assert set(resolved.author_id) == {'orcid:0000-0002-6062-7150'}
    assert set(resolved.iloc[:6].identity_confidence) == {'curated_openalex_to_orcid'}
    assert resolved.iloc[6].identity_confidence == 'curated_name_to_orcid'


def test_middle_initial_similarity_does_not_merge_structured_profiles():
    rows = pd.DataFrame([{
        'author_id': f'openalex:A{i}', 'openalex_author_id': f'https://openalex.org/A{i}',
        'orcid': '', 'canonical_name': name, 'identity_confidence': 'openalex_author_id',
    } for i, name in enumerate(['ada example', 'ada b. example'], 1)])
    resolved, _ = apply_orcid_identities(rows)
    assert resolved.author_id.nunique() == 2


def test_reviewed_profile_cannot_silently_replace_conflicting_orcid():
    rows = pd.DataFrame([{
        'author_id': 'openalex:A1', 'openalex_author_id': 'https://openalex.org/A1',
        'orcid': '0000-0001-2345-6789', 'canonical_name': 'ada example',
        'identity_confidence': 'openalex_author_id',
    }])
    with pytest.raises(ValueError, match='conflicts with observed ORCID'):
        apply_orcid_identities(rows, {
            'openalex_to_orcid': {'https://openalex.org/A1': '0000-0002-2345-6789'},
        })


def reviewed_collision_fixture():
    papers = pd.DataFrame([{'paper_id': 'p', 'doi': '10.1000/collision', 'authors': ''}])
    rows = [
        {'display_name': 'Ada Example', 'openalex_author_id': 'https://openalex.org/A1', 'orcid': '0000-0001-2345-6789'},
        {'display_name': 'Different Person', 'openalex_author_id': 'https://openalex.org/A2', 'orcid': '0000-0001-2345-6789'},
    ]
    cache = {'works_by_doi': {'10.1000/collision': {'status': 'ok', 'authorships': rows}}}
    overrides = {'authorship_overrides': [{
        'review_id': 'review-1', 'doi': '10.1000/collision', 'author_position': 2,
        'expected': dict(rows[1]),
        'replacement': {'openalex_author_id': 'https://openalex.org/A2', 'orcid': ''},
        'reason': 'ORCID belongs to Ada, not the second author.', 'sources': ['https://example.org/review'],
        'reviewed_at': '2026-09-06', 'reviewed_by': 'test',
    }]}
    return papers, cache, overrides


def test_scoped_correction_prevents_false_merge_and_preserves_source():
    papers, cache, overrides = reviewed_collision_fixture()
    authors, links, report = build_tables(papers, cache, overrides)
    assert set(links.author_id) == {'orcid:0000-0001-2345-6789', 'openalex:A2'}
    assert len(authors) == 2
    corrected = links[links.display_name.eq('Different Person')].iloc[0]
    assert corrected.source_orcid == '0000-0001-2345-6789'
    assert corrected.orcid == ''
    assert corrected.identity_review_id == 'review-1'
    assert report['authorship_review_counts']['applied_review_ids'] == ['review-1']
    assert cache['works_by_doi']['10.1000/collision']['authorships'][1]['orcid'] == '0000-0001-2345-6789'


def test_scoped_correction_rejects_changed_source_or_duplicate_decision():
    papers, cache, overrides = reviewed_collision_fixture()
    cache['works_by_doi']['10.1000/collision']['authorships'][1]['display_name'] = 'Someone Else'
    with pytest.raises(ValueError, match='source changed'):
        build_tables(papers, cache, overrides)
    papers, cache, overrides = reviewed_collision_fixture()
    overrides['authorship_overrides'] *= 2
    with pytest.raises(ValueError, match='duplicate authorship review'):
        build_tables(papers, cache, overrides)


def test_scoped_correction_reports_absent_papers_without_applying():
    papers, cache, overrides = reviewed_collision_fixture()
    overrides['authorship_overrides'][0]['doi'] = '10.1000/absent'
    _, links, report = build_tables(papers, cache, overrides)
    assert not links.identity_review_id.ne('').any()
    assert report['authorship_review_counts']['absent_paper_review_ids'] == ['review-1']


def test_other_paper_cannot_reintroduce_a_reviewed_rejected_orcid():
    papers, cache, overrides = reviewed_collision_fixture()
    papers = pd.concat([papers, pd.DataFrame([{'paper_id': 'q', 'doi': '10.1000/other', 'authors': ''}])])
    cache['works_by_doi']['10.1000/other'] = {
        'status': 'ok', 'authorships': [dict(cache['works_by_doi']['10.1000/collision']['authorships'][1])],
    }
    with pytest.raises(ValueError, match='propagation conflicts with review'):
        build_tables(papers, cache, overrides)


def list_review_fixture():
    papers = pd.DataFrame([{'paper_id': 'p', 'doi': '10.1000/list', 'authors': ''}])
    rows = [
        {'display_name': 'Ada Example', 'raw_author_name': 'Ada Example', 'openalex_author_id': 'A1', 'orcid': ''},
        {'display_name': 'Ben Example', 'raw_author_name': 'Ada Example', 'openalex_author_id': 'A2', 'orcid': ''},
        {'display_name': 'Ben Example', 'raw_author_name': 'Ben Example', 'openalex_author_id': 'A2', 'orcid': ''},
    ]
    cache = {'works_by_doi': {'10.1000/list': {'status': 'ok', 'authorships': rows}}}
    review = {
        'doi': '10.1000/list', 'review_id': 'list-1',
        'expected_source_sha256': author_tables.author_list_fingerprint(rows),
        'authors': [{'source_position': 1}, {'source_position': 3, 'identity_source_position': 2}],
        'reason': 'Published author list has Ada and Ben once each.',
        'sources': ['https://example.org/article'], 'reviewed_at': '2026-09-06', 'reviewed_by': 'test',
    }
    return papers, cache, {'author_list_reviews': [review]}


def test_reviewed_author_list_removes_source_duplicates_and_preserves_positions():
    papers, cache, overrides = list_review_fixture()
    _, links, report = build_tables(papers, cache, overrides)
    assert list(links.author_id) == ['openalex:A1', 'openalex:A2']
    assert list(links.author_position) == [1, 2]
    assert list(links.source_author_position) == [1, 3]
    assert list(links.raw_author_name) == ['Ada Example', 'Ben Example']
    assert list(links.is_last_author) == [False, True]
    assert report['author_list_reviews'][0]['removed_source_positions'] == [2]
    assert len(cache['works_by_doi']['10.1000/list']['authorships']) == 3


def test_author_list_review_rejects_changed_source_and_reused_positions():
    papers, cache, overrides = list_review_fixture()
    cache['works_by_doi']['10.1000/list']['authorships'][0]['raw_author_name'] = 'Other Person'
    with pytest.raises(ValueError, match='Author list source changed'):
        build_tables(papers, cache, overrides)
    papers, cache, overrides = list_review_fixture()
    overrides['author_list_reviews'][0]['authors'] = [{'source_position': 1}, {'source_position': 1}]
    with pytest.raises(ValueError, match='Invalid source position'):
        build_tables(papers, cache, overrides)


def test_unreviewed_repeated_authors_are_not_deduplicated():
    papers, cache, _ = list_review_fixture()
    _, links, _ = build_tables(papers, cache)
    assert len(links) == 3


def test_review_can_separate_names_with_no_verified_profile():
    papers, cache, overrides = list_review_fixture()
    overrides['author_list_reviews'][0]['authors'][1].update(identity_source_position=None, display_name='Different Person')
    _, links, _ = build_tables(papers, cache, overrides)
    assert links.iloc[1].author_id == author_tables.local_author_id('Different Person')
    assert links.iloc[1].source_openalex_author_id == 'https://openalex.org/A2'
    assert links.iloc[1].source_display_name == 'Ben Example'


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
