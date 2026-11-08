"""An abstract fills a record only when its provider record passes the identity check (decision D5)."""
import pandas as pd

from pipeline.identity.abstracts import AbstractChecker, read_provider_records, write_provider_records
from pipeline.identity.verify import Paper


TITLE = "Psilocybin therapy for treatment-resistant depression"
ABSTRACT = " ".join(f"word{index}" for index in range(60))


def record(**fields: str) -> dict:
    return {"record_doi": "10.1016/j.jad.2020.01.001", "record_title": TITLE, "abstract": ABSTRACT, **fields}


def checker(ledger_abstracts: dict | None = None, relations: dict | None = None) -> AbstractChecker:
    papers = {"10.1016/j.jad.2020.01.001": Paper("10.1016/j.jad.2020.01.001", TITLE), "10.1016/j.jad.2020.02.002": Paper("10.1016/j.jad.2020.02.002", "Another work")}
    return AbstractChecker(papers, ledger_abstracts or {}, relations or {})


def test_an_abstract_passes_when_its_record_is_the_paper() -> None:
    result = checker().check("10.1016/j.jad.2020.01.001", record())
    assert (result.passes, result.rule) == (True, "record_identifier_and_title")


def test_an_abstract_of_a_record_for_another_work_does_not_pass() -> None:
    result = checker().check("10.1016/j.jad.2020.01.001", record(record_title="Cost of CAR-T therapy in multiple myeloma"))
    assert (result.passes, result.verdict, result.rule) == (False, "conflict", "record_identifier_matches_title_differs")


def test_an_abstract_held_by_an_unlinked_record_does_not_pass() -> None:
    shared = checker({"10.1016/j.jad.2020.02.002": ABSTRACT})
    assert shared.check("10.1016/j.jad.2020.01.001", record()).rule == "abstract_on_unlinked_doi"
    linked = checker({"10.1016/j.jad.2020.02.002": ABSTRACT}, {frozenset({"10.1016/j.jad.2020.01.001", "10.1016/j.jad.2020.02.002"}): "preprint"})
    assert linked.check("10.1016/j.jad.2020.01.001", record()).passes
    # Short texts recur on unrelated records and are not compared.
    assert checker({"10.1016/j.jad.2020.02.002": "No abstract available."}).check("10.1016/j.jad.2020.01.001", record(abstract="No abstract available.")).passes
    # An abstract accepted in the same run counts as held.
    within_run = checker()
    within_run.add("10.1016/j.jad.2020.02.002", ABSTRACT)
    assert not within_run.check("10.1016/j.jad.2020.01.001", record()).passes


def test_web_page_text_is_not_an_abstract() -> None:
    page = "Our website uses cookies. By continuing to use our site, you agree. Log in or register."
    assert checker().check("10.1016/j.jad.2020.01.001", record(abstract=page)).rule == "abstract_is_web_page_text"


def test_provider_records_are_kept_and_read_with_discovery_records(tmp_path) -> None:
    write_provider_records([{"doi": "10.1016/j.jad.2020.01.001", "provider": "pubmed", "abstract": ABSTRACT}], "run1", tmp_path / "kept")
    discovery = tmp_path / "runs" / "search1"
    discovery.mkdir(parents=True)
    pd.DataFrame([{
        "provider": "openalex", "provider_record_id": "W1", "doi": "10.1016/J.JAD.2020.02.002", "pmid": "", "pmcid": "",
        "title": "Another work", "abstract": "",
    }]).to_parquet(discovery / "retrieved_records.parquet", index=False)
    records = read_provider_records(tmp_path / "kept", tmp_path / "runs")
    assert sorted(zip(records["doi"], records["provider"], records["run_id"])) == [
        ("10.1016/j.jad.2020.01.001", "pubmed", ""), ("10.1016/j.jad.2020.02.002", "openalex", "search1"),
    ]


def ledger_of(rows: list[dict]) -> pd.DataFrame:
    frame = pd.DataFrame([{"study_journal": "", "pmid": "", "pmcid": "", **row} for row in rows])
    return frame.set_index("doi", drop=False)


def test_audit_queues_ledger_abstracts_whose_record_is_another_work_and_unused_abstracts() -> None:
    from pipeline.identity.audit import provider_abstract_items

    traced, conflicting, empty, cleared = (f"10.1016/j.jad.2020.0{n}.00{n}" for n in range(1, 5))
    ledger = ledger_of([
        {"doi": traced, "study_title": TITLE, "abstract": ABSTRACT},
        {"doi": conflicting, "study_title": TITLE, "abstract": ABSTRACT + " two"},
        {"doi": empty, "study_title": TITLE, "abstract": ""},
        {"doi": cleared, "study_title": TITLE, "abstract": ""},
    ])
    records = pd.DataFrame([
        {"doi": traced, "provider": "openalex", "provider_record_id": "W1", "record_doi": traced, "record_title": TITLE,
         "abstract": ABSTRACT, "record_pmid": "", "record_pmcid": "", "run_id": "r"},
        {"doi": conflicting, "provider": "openalex", "provider_record_id": "W2", "record_doi": conflicting,
         "record_title": "Cost of CAR-T therapy in multiple myeloma", "abstract": ABSTRACT + " two",
         "record_pmid": "", "record_pmcid": "", "run_id": "r"},
        {"doi": empty, "provider": "crossref", "provider_record_id": empty, "record_doi": "", "record_title": "Other",
         "abstract": "Another text " + ABSTRACT, "record_pmid": "", "record_pmcid": "", "run_id": "r"},
        {"doi": cleared, "provider": "openalex", "provider_record_id": "W4", "record_doi": "", "record_title": "Other",
         "abstract": "Cleared " + ABSTRACT, "record_pmid": "", "record_pmcid": "", "run_id": "r"},
    ])
    decisions = {cleared: [{"clear_fields": ["abstract"]}]}
    items, counts = provider_abstract_items(ledger, records, {}, decisions)
    assert [(item["doi"], item["rule"]) for item in items] == [
        (conflicting, "record_identifier_matches_title_differs"),
        (empty, "not_used:record_no_identity_evidence"),
    ]
    assert counts["ledger_abstract_record_verified"] == 1


def test_an_accepted_kept_abstract_fills_a_record_without_one() -> None:
    from pipeline.identity.apply import curated_changes
    from pipeline.identity.evidence import text_sha256

    doi = "10.1016/j.jad.2020.01.001"
    ledger = ledger_of([{"doi": doi, "study_title": TITLE, "abstract": ""}])
    decision = {"decision_id": "sid-1", "basis": "reviewed", "verdict": "verified",
                "target": {"kind": "abstract", "sha256": text_sha256(ABSTRACT)}}
    changes = curated_changes({doi: [decision]}, ledger, {doi: {text_sha256(ABSTRACT): ABSTRACT}})
    assert changes[doi]["fields"] == {"abstract": ABSTRACT}
    # A record that has an abstract keeps it (decision D5).
    filled = ledger_of([{"doi": doi, "study_title": TITLE, "abstract": "Its own abstract."}])
    assert doi not in curated_changes({doi: [decision]}, filled, {doi: {text_sha256(ABSTRACT): ABSTRACT}})
