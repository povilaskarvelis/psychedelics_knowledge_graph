"""Retraction check: a registry notice counts only on the paper's own record.

Crossref is queried by DOI and PubMed by PMID. A retraction found on a record
whose DOI or title belongs to another paper is reported for review and does not
mark the paper retracted; a later reinstatement reverses a retraction; and the
status file is replaced only by a check that reached both registries.
"""
import json
from urllib.error import HTTPError
from urllib.parse import unquote

import pandas as pd

from pipeline.ingest import check_retractions as c


PAPER = {"doi": "10.1000/retracted", "pmid": "111", "title": "Psilocybin for major depressive disorder: a randomized trial"}


def crossref_item(doi=PAPER["doi"], title=PAPER["title"], updated_by=(), update_to=()):
    return {"DOI": doi.upper(), "title": [title], "updated-by": list(updated_by), "update-to": list(update_to)}


def notice(update_type, date, doi="10.1000/notice", source="retraction-watch"):
    return {"DOI": doi, "type": update_type, "source": source, "updated": {"date-time": f"{date}T00:00:00Z"}}


def pubmed_record(doi=PAPER["doi"], title=PAPER["title"], pubtypes=("Journal Article",), references=()):
    return {
        "uid": PAPER["pmid"],
        "title": title,
        "articleids": [{"idtype": "doi", "value": doi}] if doi else [],
        "pubtype": list(pubtypes),
        "references": list(references),
    }


def test_crossref_retraction_on_the_papers_doi_marks_it_retracted():
    item = crossref_item(title="RETRACTED: " + PAPER["title"], updated_by=[notice("retraction", "2021-05-01")])
    record = c.classify_paper(PAPER, item, None, {})
    assert record["status"] == "retracted"
    assert record["reason"] == "Retracted: Crossref (Retraction Watch): retraction, notice 10.1000/notice, 2021-05-01."


def test_pubmed_retraction_needs_the_papers_doi_or_title():
    retracted = pubmed_record(
        pubtypes=("Journal Article", "Retracted Publication"),
        references=[{"reftype": "Retraction in", "pmid": 222, "refsource": "J Psychiatr Res. 2021"}],
    )
    assert c.classify_paper(PAPER, None, retracted, {})["status"] == "retracted"
    # A wrong PMID in the ledger points at another paper's record.
    other = {**retracted, "articleids": [{"idtype": "doi", "value": "10.1000/other"}]}
    assert c.classify_paper(PAPER, None, other, {})["status"] == "identity_conflict"
    # Without a DOI on the PubMed record, the title decides.
    no_doi = {**retracted, "articleids": []}
    assert c.classify_paper(PAPER, None, no_doi, {})["status"] == "retracted"
    assert c.classify_paper(PAPER, None, {**no_doi, "title": "Ketamine in rats"}, {})["status"] == "identity_conflict"
    # An alias of the paper's DOI names the same paper.
    alias = {**retracted, "articleids": [{"idtype": "doi", "value": "10.1000/retracted-alias"}]}
    assert c.classify_paper(PAPER, None, alias, {"10.1000/retracted-alias": "10.1000/retracted"})["status"] == "retracted"


def test_crossref_record_with_another_title_marks_nothing_retracted():
    item = crossref_item(title="Ketamine in rats", updated_by=[notice("retraction", "2021-05-01")])
    record = c.classify_paper(PAPER, item, None, {})
    assert record["status"] == "identity_conflict"
    assert record["sources"]["crossref"]["identity"] == "title_conflict"


def test_publisher_withdrawal_alone_is_listed_for_review():
    # Elsevier registered the withdrawal of a duplicate corrigendum against the article.
    withdrawn = crossref_item(updated_by=[notice("withdrawal", "2023-12-23", source="publisher")])
    assert c.classify_paper(PAPER, withdrawn, None, {})["status"] == "withdrawn"
    retracted = pubmed_record(pubtypes=("Journal Article", "Retracted Publication"))
    assert c.classify_paper(PAPER, withdrawn, retracted, {})["status"] == "retracted"


def test_later_reinstatement_reverses_a_retraction():
    reinstated = crossref_item(updated_by=[notice("retraction", "2020-01-01"), notice("reinstatement", "2022-01-01")])
    assert c.classify_paper(PAPER, reinstated, None, {})["status"] == "reinstated"
    retracted_again = crossref_item(updated_by=[notice("reinstatement", "2019-01-01"), notice("retraction", "2020-01-01")])
    assert c.classify_paper(PAPER, retracted_again, None, {})["status"] == "retracted"


def test_concerns_and_notices_are_recorded_and_corrections_ignored():
    concern = crossref_item(updated_by=[notice("expression_of_concern", "2023-03-03"), notice("correction", "2023-04-04")])
    assert c.classify_paper(PAPER, concern, None, {})["status"] == "expression_of_concern"
    assert c.classify_paper(PAPER, crossref_item(updated_by=[notice("correction", "2023-04-04")]), None, {}) is None
    notice_paper = {**PAPER, "title": "Retraction notice"}
    item = crossref_item(title="Retraction notice", update_to=[{"DOI": "10.1000/original", "type": "retraction"}])
    assert c.classify_paper(notice_paper, item, None, {})["status"] == "notice"


class FakeClient:
    """Crossref as seen through the batch filter and single-DOI lookups."""

    def __init__(self, registered, aliases, failing=(), flaky=()):
        self.registered = registered
        self.aliases = aliases
        self.failing = set(failing)
        # DOIs whose first single lookup is reset by the server.
        self.flaky = set(flaky)
        self.batch_filters = []

    def get_json(self, url, params=None, headers=None):
        if url == c.CROSSREF_WORKS_URL:
            self.batch_filters.append(params["filter"])
            queried = [part.removeprefix("doi:") for part in params["filter"].split(",")]
            # The filter returns works registered under the queried DOI only.
            return {"message": {"items": [crossref_item(doi=doi) for doi in queried if doi in self.registered]}}
        doi = unquote(url.removeprefix(c.CROSSREF_WORKS_URL + "/"))
        if doi in self.failing:
            raise HTTPError(url, 500, "server error", {}, None)
        if doi in self.flaky:
            self.flaky.discard(doi)
            raise ConnectionResetError(54, "Connection reset by peer")
        if doi in self.aliases:
            return {"message": crossref_item(doi=self.aliases[doi])}
        if doi in self.registered:
            return {"message": crossref_item(doi=doi)}
        raise HTTPError(url, 404, "not found", {}, None)


def test_crossref_lookup_covers_alias_escaped_and_comma_dois():
    client = FakeClient(
        registered={"10.1000/a", "10.1000/b<c>", "10.1000/with,comma"},
        aliases={"10.1000/old-alias": "10.1000/primary"},
    )
    dois = ["10.1000/a", "10.1000/b%3cc%3e", "10.1000/old-alias", "10.5281/zenodo.1", "10.1000/with,comma", "pii: s0001"]
    records, errors = c.fetch_crossref_works(client, dois, email="", batch_size=100, progress_every=0)
    assert set(records) == {"10.1000/a", "10.1000/b%3cc%3e", "10.1000/old-alias", "10.1000/with,comma"}
    assert errors == {}
    assert all("with,comma" not in value and "pii" not in value for value in client.batch_filters)
    alias = c.crossref_evidence({"doi": "10.1000/old-alias", "title": PAPER["title"]}, records["10.1000/old-alias"])
    assert alias["registered_doi"] == "10.1000/primary"


def test_failed_lookups_are_repeated_once_then_reported(monkeypatch):
    monkeypatch.setattr(c, "RETRY_DELAY_SEC", 0)
    client = FakeClient(
        registered=set(), aliases={"10.1000/flaky": "10.1000/flaky-primary"},
        failing={"10.1000/down"}, flaky={"10.1000/flaky"},
    )
    records, errors = c.fetch_crossref_works(
        client, ["10.1000/down", "10.1000/flaky"], email="", batch_size=100, progress_every=0
    )
    assert set(records) == {"10.1000/flaky"}
    assert errors == {"10.1000/down": "HTTP 500"}

    class PubMed:
        def __init__(self, failures):
            self.failures = failures

        def get_json(self, url, params=None, headers=None):
            if self.failures > 0:
                self.failures -= 1
                raise TimeoutError("timed out")
            return {"result": {"uids": ["111"], "111": pubmed_record(), "999": {"uid": "999", "error": "cannot get document summary"}}}

    records, errors = c.fetch_pubmed_summaries(PubMed(1), ["111", "999"], email="", api_key="", batch_size=200, progress_every=0)
    assert set(records) == {"111"} and errors == {}
    _, errors = c.fetch_pubmed_summaries(PubMed(2), ["111"], email="", api_key="", batch_size=200, progress_every=0)
    assert errors == {"111": "TimeoutError: timed out"}


def test_merge_replaces_checked_records_and_keeps_the_rest():
    previous = [
        {"doi": "10.1000/outside", "status": "retracted", "first_recorded_at_utc": "2026-01-01T00:00:00+00:00"},
        {"doi": "10.1000/same", "status": "retracted", "first_recorded_at_utc": "2026-01-01T00:00:00+00:00"},
        {"doi": "10.1000/cleared", "status": "expression_of_concern", "first_recorded_at_utc": "2026-01-01T00:00:00+00:00"},
        {"doi": "10.1000/changed", "status": "expression_of_concern", "first_recorded_at_utc": "2026-01-01T00:00:00+00:00"},
    ]
    current = [{"doi": "10.1000/same", "status": "retracted"}, {"doi": "10.1000/changed", "status": "retracted"}]
    checked = {"10.1000/same", "10.1000/cleared", "10.1000/changed"}
    merged = {record["doi"]: record for record in c.merge_status_records(previous, current, checked, "2026-11-01T00:00:00+00:00")}
    assert set(merged) == {"10.1000/outside", "10.1000/same", "10.1000/changed"}
    assert merged["10.1000/same"]["first_recorded_at_utc"] == "2026-01-01T00:00:00+00:00"
    assert merged["10.1000/changed"]["first_recorded_at_utc"] == "2026-11-01T00:00:00+00:00"


def test_main_writes_the_status_only_after_a_complete_check(tmp_path, monkeypatch):
    run_dir = tmp_path / "routed_runs" / "run_1"
    run_dir.mkdir(parents=True)
    (run_dir / "route_extraction_outputs.jsonl").write_text(
        "\n".join(json.dumps({"study_doi": doi, "result": {}}) for doi in (PAPER["doi"], "10.1000/clean")) + "\n"
    )
    ledger = tmp_path / "candidate_papers.parquet"
    pd.DataFrame([
        {"doi": PAPER["doi"], "pmid": "111", "study_title": PAPER["title"]},
        {"doi": "10.1000/clean", "pmid": "", "study_title": "Ketamine for treatment-resistant depression"},
    ]).to_parquet(ledger)
    config = tmp_path / "config.yaml"
    config.write_text('crossref:\n  email: ""\n')
    status = tmp_path / "retraction_status.json"
    args = [
        "--evidence-run-id", "run_1",
        "--routed-runs-dir", str(tmp_path / "routed_runs"),
        "--candidate-table", str(ledger),
        "--paper-metadata-overrides", str(tmp_path / "missing.json"),
        "--doi-alias-registry", str(tmp_path / "missing.json"),
        "--status-out", str(status),
        "--report-root", str(tmp_path / "reports"),
        "--config", str(config),
    ]
    retracted = {PAPER["doi"]: crossref_item(updated_by=[notice("retraction", "2021-05-01")])}
    monkeypatch.setattr(c, "fetch_crossref_works", lambda client, dois, **kwargs: (retracted, {}))
    monkeypatch.setattr(c, "fetch_pubmed_summaries", lambda client, pmids, **kwargs: ({}, {}))
    assert c.main(args) == 0
    written = json.loads(status.read_text())
    assert [(record["doi"], record["status"]) for record in written["records"]] == [(PAPER["doi"], "retracted")]
    assert written["last_check"]["scope"] == {"kind": "evidence_run", "id": "run_1"}
    assert written["last_check"]["papers_checked"] == 2

    monkeypatch.setattr(c, "fetch_pubmed_summaries", lambda client, pmids, **kwargs: ({}, {"111": "TimeoutError"}))
    before = status.read_text()
    assert c.main(args) == 1
    assert status.read_text() == before


def test_recorded_status_file_is_readable():
    status = c.read_status(c.DEFAULT_STATUS_PATH)
    known = set(c.STATUS_ORDER) | {"identity_conflict"}
    assert all(record["status"] in known for record in status["records"])
