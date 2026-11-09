import json
from collections import Counter

import pandas as pd
import pytest

import pipeline.kg.author_identity_evidence as evidence_lib
from pipeline.kg.author_identity_evidence import (
    StaticAuthorEvidence,
    clean_person_name,
    is_non_person_byline,
    names_compatible,
    parse_orcid_record,
)
from pipeline.kg.build_author_tables import (
    apply_coauthor_profile_aliases,
    apply_display_names,
    apply_openalex_profile_merges,
    apply_orcid_record_evidence,
    build_tables,
    choose_display_name,
)

BARRETT = "0000-0001-7443-3237"


def _row(paper, position, name, *, openalex="", orcid="", doi=None, **extra):
    author_id = f"orcid:{orcid}" if orcid else (f"openalex:{openalex}" if openalex else f"local_author:{name}")
    return {
        "paper_id": f"paper:{paper}", "doi": doi or paper, "author_position": position,
        "author_id": author_id, "display_name": name, "canonical_name": name.casefold(),
        "raw_author_name": name, "openalex_author_id": f"https://openalex.org/{openalex}" if openalex else "",
        "orcid": orcid, "identity_confidence": "orcid" if orcid else "openalex_author_id",
        "identity_review_id": "", "author_list_review_id": "", **extra,
    }


def _record(given, family, dois=(), other_names=()):
    return {"status": "ok", "queried_at": "2026-11-09T00:00:00+00:00", "given_names": given,
            "family_name": family, "credit_name": "", "other_names": list(other_names), "dois": list(dois)}


@pytest.mark.parametrize("left,right,expected", [
    ("Frederick S. Barrett", "Frederick Barrett", True),
    ("Peacock, Amy", "Amy Peacock", True),
    ("Su Min", "Min Su", True),
    ("Wieslaw J. Cubala", "Wiesław Jerzy Cubała", True),
    ("J. Camí", "Jordi Camı́", True),
    ("Jake Payne", "Richard Chambers", False),
    ("Changsu Han", "Hans-Jürgen Möller", False),
])
def test_names_compatible(left, right, expected):
    assert names_compatible(left, right) is expected


@pytest.mark.parametrize("raw,clean", [
    ("Prof. Dr. Matthias E. Liechti", "Matthias E. Liechti"),
    ("DavidE. Nichols", "David E. Nichols"),
    ("D. E. NICHOLS", "D. E. Nichols"),
    ("RAFAEL TEIXEIRA DE SOUSA", "Rafael Teixeira de Sousa"),
    ("Albert Garcia‐Romeu", "Albert Garcia-Romeu"),
    ("Νikolaos S. Τhomaidis", "Nikolaos S. Thomaidis"),
    ("Jordi Camı́", "Jordi Camí"),
    ("Feyza Arıcıoğlu", "Feyza Arıcıoğlu"),
    ("Jordi Riba A", "Jordi Riba"),
    ("Peacock, Amy", "Amy Peacock"),
    ("James David Adams Jr.", "James David Adams Jr."),
    ("id_orcid 0000-0001-8558-3396 Juruena", "Juruena"),
    ("Αλεξάνδρα Κορδά", "Αλεξάνδρα Κορδά"),
])
def test_clean_person_name(raw, clean):
    assert clean_person_name(raw) == clean


def test_non_person_bylines_are_detected_conservatively():
    assert is_non_person_byline("on behalf of the Euro-DEN Research Group")
    assert is_non_person_byline("7450 Summit Cir, Davison, MI 48423")
    assert is_non_person_byline("Swiss Psychedelic Research Network")
    assert not is_non_person_byline("Ann Network")
    assert not is_non_person_byline("Mario F.")


def test_merged_openalex_fragment_joins_orcid_identity():
    rows = pd.DataFrame([
        _row("p1", 1, "Frederick S. Barrett", openalex="A5005540871", orcid=BARRETT),
        _row("p2", 2, "Frederick S. Barrett", openalex="A5137283236"),
    ])
    profiles = {"A5137283236": {"status": "ok", "resolved_id": "A5005540871", "orcid": BARRETT,
                                   "display_name": "Frederick Streeter Barrett"}}
    merged, stats = apply_openalex_profile_merges(rows, profiles)
    assert merged.loc[1, "openalex_author_id"] == "https://openalex.org/A5005540871"
    assert merged.loc[1, "orcid"] == BARRETT
    assert stats["openalex_profiles_merged"] == 1


def test_profile_merge_leaves_reviewed_rows_and_unchecked_profiles():
    rows = pd.DataFrame([
        _row("p1", 1, "Ada Example", openalex="A1", identity_review_id="review-1"),
        _row("p2", 1, "Ada Example", openalex="A2"),
    ])
    profiles = {"A1": {"status": "ok", "resolved_id": "A9"}}
    merged, stats = apply_openalex_profile_merges(rows, profiles)
    assert list(merged.openalex_author_id) == ["https://openalex.org/A1", "https://openalex.org/A2"]
    assert stats["openalex_profiles_unchecked"] == 1


def test_profile_merge_skips_profiles_with_reviewed_decisions():
    rows = pd.DataFrame([_row("p1", 1, "Ada Example", openalex="A1")])
    overrides = {"openalex_to_orcid": {"https://openalex.org/A1": "0000-0000-0000-0001"}}
    merged, _ = apply_openalex_profile_merges(rows, {"A1": {"status": "ok", "resolved_id": "A9"}}, overrides)
    assert merged.loc[0, "openalex_author_id"] == "https://openalex.org/A1"


def test_orcid_record_removes_orcid_from_mismatched_byline():
    chambers = "0000-0003-0151-2270"
    rows = pd.DataFrame([
        _row(f"c{i}", 1, "Richard Chambers", openalex="A5069708182", orcid=chambers) for i in range(3)
    ] + [_row("payne", 1, "Jake Payne", orcid=chambers)])
    evidence = StaticAuthorEvidence(records={chambers: _record("Richard", "Chambers")})
    out, stats, _ = apply_orcid_record_evidence(rows, evidence)
    assert out.loc[3, "orcid"] == ""
    assert out.loc[3, "identity_confidence"] == "orcid_removed_name_mismatch"
    assert out.loc[3, "author_id"].startswith("local_author:")
    assert set(out.loc[:2, "author_id"]) == {f"orcid:{chambers}"}
    assert stats["authorship_rows_orcid_removed"] == 1


def test_orcid_record_keeps_mismatched_byline_when_doi_is_listed():
    orcid = "0000-0002-4729-7601"
    rows = pd.DataFrame([
        _row("a", 1, "Ellen M. Leslie", orcid=orcid), _row("b", 1, "Ellen M. Leslie", orcid=orcid),
        _row("c", 2, "Ellen Wessel", orcid=orcid),
    ])
    evidence = StaticAuthorEvidence(records={orcid: _record("Ellen", "Leslie", dois=["c"])})
    out, stats, _ = apply_orcid_record_evidence(rows, evidence)
    assert out.loc[2, "orcid"] == orcid
    assert stats["authorship_rows_orcid_removed"] == 0


def test_orcid_record_assigns_listed_doi_to_single_matching_orcid():
    rows = pd.DataFrame([
        _row("p1", 1, "David J. Nutt", orcid="0000-0002-1286-1401"),
        _row("p2", 3, "D.J. Nutt", openalex="A5113636502"),
        _row("p3", 3, "D.J. Nutt", openalex="A5113636502"),
    ])
    evidence = StaticAuthorEvidence(records={"0000-0002-1286-1401": _record("David", "Nutt", dois=["p2"])})
    out, stats, _ = apply_orcid_record_evidence(rows, evidence)
    assert out.loc[1, "author_id"] == "orcid:0000-0002-1286-1401"
    assert out.loc[1, "identity_confidence"] == "orcid_record_lists_doi"
    assert out.loc[2, "author_id"] == "openalex:A5113636502"
    assert stats["authorship_rows_assigned_by_orcid_record"] == 1


def test_orcid_record_does_not_assign_when_orcid_is_already_on_paper_or_ambiguous():
    rows = pd.DataFrame([
        _row("p1", 1, "Wei Wang", orcid="0000-0000-0000-0001"),
        _row("p2", 1, "Wei Wang", orcid="0000-0000-0000-0002"),
        _row("p3", 1, "Wei Wang", openalex="A1"),
        _row("p1", 2, "W. Wang", openalex="A2"),
    ])
    records = {
        "0000-0000-0000-0001": _record("Wei", "Wang", dois=["p1", "p3"]),
        "0000-0000-0000-0002": _record("Wei", "Wang", dois=["p3"]),
    }
    out, stats, _ = apply_orcid_record_evidence(rows, StaticAuthorEvidence(records=records))
    assert out.loc[2, "author_id"] == "openalex:A1"
    assert out.loc[3, "author_id"] == "openalex:A2"
    assert stats["authorship_rows_assigned_by_orcid_record"] == 0


def test_display_name_prefers_full_latin_byline():
    names = Counter({"A. Roig": 3, "Antoni F. Roig-Navarro": 1})
    assert choose_display_name(names) == "Antoni F. Roig-Navarro"
    names = Counter({"Αλεξάνδρα Κορδά": 2, "Alexandra Korda": 1})
    assert choose_display_name(names) == "Alexandra Korda"
    names = Counter({"Frederick S. Barrett": 40, "Frederick Streeter Barrett": 1})
    assert choose_display_name(names) == "Frederick S. Barrett"
    record = _record("Vadim", "Shevyrin")
    assert choose_display_name(Counter({"V. A. Shevyrin": 2}), record) == "Vadim Shevyrin"


def test_display_names_separate_group_bylines():
    rows = pd.DataFrame([
        _row("p1", 1, "Albert Garcia‐Romeu", openalex="A1"),
        _row("p1", 2, "on behalf of the Euro-DEN Research Group"),
    ])
    out, stats = apply_display_names(rows)
    assert out.loc[0, "display_name"] == "Albert Garcia-Romeu"
    assert out.loc[0, "raw_author_name"] == "Albert Garcia‐Romeu"
    assert out.loc[1, "author_id"].startswith("group:")
    assert stats["non_person_bylines"] == 1


def test_build_tables_with_evidence_joins_fragment_to_orcid():
    papers = pd.DataFrame([
        {"paper_id": "paper:10.1/a", "doi": "10.1/a", "title": "A"},
        {"paper_id": "paper:10.1/b", "doi": "10.1/b", "title": "B"},
    ])

    def work(doi, title, openalex, orcid):
        return {"status": "ok", "doi": doi, "title": title, "work_openalex_id": "", "authorships": [{
            "position": 1, "author_position": "first", "display_name": "Frederick S. Barrett",
            "raw_author_name": "Frederick S. Barrett", "openalex_author_id": f"https://openalex.org/{openalex}",
            "orcid": orcid}]}

    cache = {"works_by_doi": {
        "10.1/a": work("10.1/a", "A", "A5005540871", BARRETT),
        "10.1/b": work("10.1/b", "B", "A5137283236", ""),
    }}
    evidence = StaticAuthorEvidence(profiles={
        "A5005540871": {"status": "ok", "resolved_id": "A5005540871", "orcid": BARRETT,
                                   "display_name": "Frederick Streeter Barrett"},
        "A5137283236": {"status": "ok", "resolved_id": "A5005540871", "orcid": BARRETT,
                                   "display_name": "Frederick Streeter Barrett"},
    })
    authors, links, report = build_tables(papers, cache, {}, evidence)
    assert list(authors.author_id) == [f"orcid:{BARRETT}"]
    assert report["openalex_profile_merge_counts"]["openalex_profiles_merged"] == 1
    without_evidence, _, _ = build_tables(papers, cache, {}, None)
    assert len(without_evidence) == 2


def test_parse_orcid_record_reads_names_and_dois():
    payload = {
        "person": {"name": {"given-names": {"value": "Frederick"}, "family-name": {"value": "Barrett"}},
                   "other-names": {"other-name": [{"content": "Fred Barrett"}]}},
        "activities-summary": {"works": {"group": [
            {"external-ids": {"external-id": [{"external-id-type": "doi", "external-id-value": "https://doi.org/10.1/ABC"}]}},
            {"external-ids": {"external-id": [{"external-id-type": "pmid", "external-id-value": "1"}]}},
        ]}},
    }
    record = parse_orcid_record(payload)
    assert record["dois"] == ["10.1/abc"]
    assert evidence_lib.orcid_record_names({**record, "status": "ok"}) == ["Frederick Barrett", "Fred Barrett"]


def test_cached_entries_are_requeried_only_when_stale_or_failed():
    entries = {
        "A1": {"status": "ok", "queried_at": "2099-01-01T00:00:00+00:00"},
        "A2": {"status": "ok", "queried_at": "2020-01-01T00:00:00+00:00"},
        "A3": {"status": "error", "queried_at": "2099-01-01T00:00:00+00:00"},
    }
    assert evidence_lib.keys_to_query(["A1", "A2", "A3", "A4"], entries, max_age_days=60) == ["A2", "A3", "A4"]


def test_cache_mode_never_queries(tmp_path, monkeypatch):
    monkeypatch.setattr(evidence_lib, "get_json", lambda *a, **k: pytest.fail("network used"))
    path = tmp_path / "profiles.json"
    path.write_text(json.dumps({"version": "1.0", "entries": {"A1": {"status": "ok", "resolved_id": "A2"}}}))
    result = evidence_lib.resolve_openalex_profiles(["https://openalex.org/A1", "A3"], path, offline=True)
    assert result == {"A1": {"status": "ok", "resolved_id": "A2"}}


def test_merge_into_differently_named_profile_is_rejected():
    rows = pd.DataFrame([_row("p1", 2, "Jan A. Vorster", openalex="A5112972291")])
    profiles = {"A5112972291": {"status": "ok", "resolved_id": "A5036328098", "display_name": "Sophie Geyrhofer",
                                "orcid": "0000-0002-7764-4053"}}
    merged, stats = apply_openalex_profile_merges(rows, profiles)
    assert merged.loc[0, "author_id"] == "openalex:A5112972291"
    assert merged.loc[0, "orcid"] == ""
    assert stats["authorship_rows_merge_rejected_name_mismatch"] == 1


def test_listed_doi_does_not_protect_a_coauthor_holding_the_owner_orcid():
    gaspar = "0000-0002-9616-0441"
    rows = pd.DataFrame([
        _row("p1", 2, "Tania Gaspar", orcid=gaspar), _row("p2", 1, "Tania Gaspar", orcid=gaspar),
        _row("p1", 6, "Fábio B. Guedes", orcid=gaspar),
    ])
    evidence = StaticAuthorEvidence(records={gaspar: _record("Tânia", "Gaspar", dois=["p1", "p2"])})
    out, stats, _ = apply_orcid_record_evidence(rows, evidence)
    assert out.loc[2, "orcid"] == ""
    assert stats["authorship_rows_orcid_removed"] == 1


def test_evidence_change_creating_same_paper_collision_is_reverted():
    from pipeline.kg.build_author_tables import revert_same_paper_collisions

    before = pd.DataFrame([
        _row("p1", 7, "E.N Andrade", openalex="A5057496943"),
        _row("p1", 8, "E.O Andrade", openalex="A5010570653"),
    ])
    after = before.copy()
    after.loc[0, ["author_id", "openalex_author_id", "identity_confidence"]] = [
        "openalex:A5010570653", "https://openalex.org/A5010570653", "openalex_merged_profile"]
    out, reverted = revert_same_paper_collisions(after, before)
    assert list(out.author_id) == ["openalex:A5057496943", "openalex:A5010570653"]
    assert len(reverted) == 1


def test_non_latin_byline_and_initial_surname_keep_their_orcid():
    su, jaya = "0000-0002-8286-9759", "0000-0002-3963-5383"
    rows = pd.DataFrame([
        _row("a", 1, "Ruibin Su", orcid=su), _row("b", 1, "Ruibin Su", orcid=su), _row("c", 5, "苏瑞斌", orcid=su),
        _row("d", 1, "A. Jayasudha", orcid=jaya), _row("e", 1, "A. Jayasudha", orcid=jaya),
        _row("f", 5, "Jayasudha A", orcid=jaya),
    ])
    records = {su: _record("Ruibin", "Su"), jaya: _record("Jayasudha", "A")}
    out, stats, _ = apply_orcid_record_evidence(rows, StaticAuthorEvidence(records=records))
    assert stats["authorship_rows_orcid_removed"] == 0


def test_repeated_identical_byline_is_not_reverted():
    from pipeline.kg.build_author_tables import revert_same_paper_collisions

    before = pd.DataFrame([
        _row("p1", 16, "Virendra Kumar Arya", openalex="A1"),
        _row("p1", 26, "Virendra Kumar Arya", openalex="A2"),
    ])
    after = before.copy()
    after["author_id"] = "orcid:0000-0002-6291-0187"
    out, reverted = revert_same_paper_collisions(after, before)
    assert reverted == []


def test_majority_rows_with_wrong_orcid_are_checked_too():
    han = "0000-0002-4021-8907"
    rows = pd.DataFrame([
        _row("a", 10, "Hans-Jürgen Möller", orcid=han), _row("b", 4, "Hans-Jürgen Möller", orcid=han),
        _row("c", 7, "Changsu Han", orcid=han),
    ])
    evidence = StaticAuthorEvidence(records={han: _record("Changsu", "Han", dois=["c"])})
    out, stats, _ = apply_orcid_record_evidence(rows, evidence)
    assert list(out.orcid) == ["", "", han]
    assert stats["authorship_rows_orcid_removed"] == 2


def test_surname_first_identity_name_is_compatible():
    assert names_compatible("E. Kervadec", "Kervadec Ewen")
    assert names_compatible("C. V. Priyatha", "Priyatha CV")


def test_shared_surname_with_other_given_name_is_left_for_review():
    orcid = "0000-0002-1983-0333"
    rows = pd.DataFrame([
        _row("a", 1, "Toni Karlsson", orcid=orcid), _row("b", 1, "Antonia Karlsson", orcid=orcid),
    ])
    evidence = StaticAuthorEvidence(records={orcid: _record("Toni", "Karlsson")})
    out, stats, _ = apply_orcid_record_evidence(rows, evidence)
    assert stats["authorship_rows_orcid_removed"] == 0


def test_person_names_with_record_numbers_or_the_prefix_are_people():
    assert clean_person_name("Xiuli Wang (151314)") == "Xiuli Wang"
    assert not is_non_person_byline(clean_person_name("Peng Liu (120506)"))
    assert not is_non_person_byline("The-Vinh Tran")
    assert is_non_person_byline("(on behalf of the Euro-DEN Plus Research Group)")


RICE = "0000-0002-0000-0001"


def _coauthor_case(name, profile_coauthors, orcid_coauthors, *, profile_name=None):
    """An ORCID identity and an OpenAlex-only profile, each with their own papers and coauthors."""
    rows = []
    for paper, others in [("o1", orcid_coauthors), ("f1", profile_coauthors)]:
        if paper == "o1":
            rows.append(_row(paper, 1, name, openalex="A1", orcid=RICE))
        else:
            rows.append(_row(paper, 1, profile_name or name, openalex="A2"))
        for position, coauthor in enumerate(others, start=2):
            rows.append(_row(paper, position, coauthor, openalex=f"C{coauthor[-1]}"))
    return pd.DataFrame(rows)


def test_coauthor_alias_joins_profile_with_same_full_name():
    rows = _coauthor_case("Kenner C. Rice", ["Coauthor 1", "Coauthor 2"], ["Coauthor 1", "Coauthor 2"])
    out, stats = apply_coauthor_profile_aliases(rows)
    profile_rows = out[out["paper_id"].eq("paper:f1") & out["author_position"].eq(1)]
    assert profile_rows["author_id"].tolist() == [f"orcid:{RICE}"]
    assert profile_rows["identity_confidence"].tolist() == ["coauthor_alias_to_orcid"]
    assert stats["coauthor_alias_profiles"] == 1


def test_coauthor_alias_requires_three_shared_coauthors_for_two_word_names():
    two = _coauthor_case("Tingting Lin", ["Coauthor 1", "Coauthor 2"], ["Coauthor 1", "Coauthor 2"])
    out, stats = apply_coauthor_profile_aliases(two)
    assert stats["coauthor_alias_profiles"] == 0
    assert stats["coauthor_alias_skipped_too_few_shared_coauthors"] == 1
    three = _coauthor_case("Tingting Lin", ["Coauthor 1", "Coauthor 2", "Coauthor 3"],
                           ["Coauthor 1", "Coauthor 2", "Coauthor 3"])
    assert apply_coauthor_profile_aliases(three)[1]["coauthor_alias_profiles"] == 1


@pytest.mark.parametrize("name", ["K. C. Rice", "KC Rice"])
def test_coauthor_alias_skips_initials(name):
    rows = _coauthor_case(name, ["Coauthor 1", "Coauthor 2", "Coauthor 3"], ["Coauthor 1", "Coauthor 2", "Coauthor 3"])
    assert apply_coauthor_profile_aliases(rows)[1]["coauthor_alias_profiles"] == 0


def test_coauthor_alias_skips_one_shared_coauthor_and_same_paper():
    one = _coauthor_case("Kenner C. Rice", ["Coauthor 1", "Coauthor 2"], ["Coauthor 1", "Coauthor 3"])
    assert apply_coauthor_profile_aliases(one)[1]["coauthor_alias_profiles"] == 0
    rows = _coauthor_case("Kenner C. Rice", ["Coauthor 1", "Coauthor 2"], ["Coauthor 1", "Coauthor 2"])
    rows = pd.concat([rows, pd.DataFrame([_row("o1", 9, "Kenner C. Rice", openalex="A2")])], ignore_index=True)
    assert apply_coauthor_profile_aliases(rows)[1]["coauthor_alias_profiles"] == 0


def test_coauthor_alias_skips_two_orcid_identities_and_reviewed_decisions():
    rows = _coauthor_case("Kenner C. Rice", ["Coauthor 1", "Coauthor 2"], ["Coauthor 1", "Coauthor 2"])
    other = pd.DataFrame([_row("x1", 1, "Kenner C. Rice", openalex="A9", orcid="0000-0002-0000-0009")])
    assert apply_coauthor_profile_aliases(pd.concat([rows, other], ignore_index=True))[1]["coauthor_alias_profiles"] == 0
    distinct = {"distinct_identity_reviews": [{"identity_ids": ["openalex:A2", f"orcid:{RICE}"]}]}
    assert apply_coauthor_profile_aliases(rows, distinct)[1]["coauthor_alias_profiles"] == 0
    reviewed_profile = {"openalex_to_orcid": {"https://openalex.org/A2": "0000-0002-0000-0009"}}
    assert apply_coauthor_profile_aliases(rows, reviewed_profile)[1]["coauthor_alias_profiles"] == 0
