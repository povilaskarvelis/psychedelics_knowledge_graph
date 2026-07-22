from __future__ import annotations

import json
from pathlib import Path
import xml.etree.ElementTree as ET

import pandas as pd

from pipeline.ingest.audit_paper_funding import latest_attempts
import pipeline.ingest.enrich_paper_funding as funding_enrichment
from pipeline.ingest.enrich_paper_funding import (
    append_attempt,
    build_scope,
    lookup_crossref_funding,
    replace_provider_assertions,
    terminal_provider_pairs,
    terminal_provider_pairs_for_run,
)
from pipeline.ingest.funding_metadata import (
    ASSERTION_COLUMNS,
    ATTEMPT_COLUMNS,
    FUNDING_ATTEMPT_SCHEMA_VERSION,
    finalize_assertions,
    funding_rows_from_crossref,
    funding_rows_from_openalex,
    funding_rows_from_pubmed,
    payload_sha256,
)


def test_openalex_uses_current_awards_and_funders_and_preserves_relationships():
    work = {
        "funders": [
            {
                "id": "https://openalex.org/F1",
                "display_name": "Example Council",
                "ror": "https://ror.org/012345678",
            },
            {
                "id": "https://openalex.org/F2",
                "display_name": "Funder Without Award",
                "ror": "https://ror.org/087654321",
            },
        ],
        "awards": [
            {
                "id": "https://openalex.org/A1",
                "display_name": "Example programme",
                "funder_award_id": "R01-123",
                "funder_id": "https://openalex.org/F1",
                "funder_display_name": "Example Council",
                "doi": "https://doi.org/10.9999/grant.1",
            }
        ],
        # The dedicated backfill must not consume OpenAlex's deprecated field.
        "grants": [{"funder_display_name": "Legacy Funder", "award_id": "OLD-1"}],
    }

    rows = funding_rows_from_openalex(work)

    assert rows == [
        {
            "source_field": "awards",
            "funder_name": "Example Council",
            "funder_openalex_id": "F1",
            "funder_ror_id": "https://ror.org/012345678",
            "award_id": "R01-123",
            "award_name": "Example programme",
            "award_openalex_id": "A1",
            "award_doi": "10.9999/grant.1",
        },
        {
            "source_field": "funders",
            "funder_name": "Funder Without Award",
            "funder_openalex_id": "F2",
            "funder_ror_id": "https://ror.org/087654321",
        },
    ]


def test_pubmed_preserves_each_grant_funder_pair():
    article = ET.fromstring(
        """
        <PubmedArticle>
          <GrantList>
            <Grant>
              <GrantID>R01 MH123456</GrantID>
              <Acronym>NIMH</Acronym>
              <Agency>NIMH NIH HHS</Agency>
              <Country>United States</Country>
            </Grant>
            <Grant>
              <GrantID>WT-42</GrantID>
              <Agency>Wellcome Trust</Agency>
              <Country>United Kingdom</Country>
            </Grant>
          </GrantList>
        </PubmedArticle>
        """
    )

    assert funding_rows_from_pubmed(article) == [
        {
            "source_field": "GrantList/Grant",
            "funder_name": "NIMH NIH HHS",
            "funder_acronym": "NIMH",
            "funder_country": "United States",
            "award_id": "R01 MH123456",
        },
        {
            "source_field": "GrantList/Grant",
            "funder_name": "Wellcome Trust",
            "funder_acronym": "",
            "funder_country": "United Kingdom",
            "award_id": "WT-42",
        },
    ]


def test_crossref_keeps_awards_nested_under_their_funder():
    item = {
        "funder": [
            {
                "DOI": "10.13039/100000001",
                "name": "National Science Foundation",
                "award": ["ABC-1", "ABC-2"],
                "doi-asserted-by": "publisher",
            },
            {
                "ROR": "https://ror.org/00abcd123",
                "name": "Foundation Without Award",
                "award": [],
            },
        ]
    }

    rows = funding_rows_from_crossref(item)

    assert [row["award_id"] for row in rows] == ["ABC-1", "ABC-2", ""]
    assert rows[0]["funder_crossref_id"] == "10.13039/100000001"
    assert rows[0]["provider_asserted_by"] == "publisher"
    assert rows[2]["funder_ror_id"] == "https://ror.org/00abcd123"


def test_crossref_provider_redirect_preserves_returned_record_id():
    class FakeClient:
        def get_json(self, url, params, headers):
            return {
                "message": {
                    "DOI": "10.1001/jama.canonical",
                    "funder": [{"name": "Example Funder", "award": ["A-1"]}],
                }
            }

    record_id, _fragment, rows = lookup_crossref_funding(
        FakeClient(), doi="10.1001/jama.legacy", email=""
    )

    assert record_id == "10.1001/jama.canonical"
    assert rows[0]["funder_name"] == "Example Funder"


def test_finalize_assertions_deduplicates_and_adds_retrieval_provenance():
    source = {
        "source_field": "funder",
        "funder_name": "Example Funder",
        "award_id": "A-1",
    }
    payload_hash = payload_sha256({"funder": [source]})

    rows = finalize_assertions(
        [source, source],
        doi="https://doi.org/10.1000/XYZ",
        provider="Crossref",
        provider_record_id="10.1000/xyz",
        retrieval_run_id="funding_test",
        retrieved_at_utc="2026-07-22T12:00:00+00:00",
        source_payload_sha256=payload_hash,
    )

    assert len(rows) == 1
    assert rows[0]["doi"] == "10.1000/xyz"
    assert rows[0]["provider"] == "crossref"
    assert rows[0]["retrieval_run_id"] == "funding_test"
    assert rows[0]["source_payload_sha256"] == payload_hash
    assert len(rows[0]["assertion_key"]) == 64

    assert (
        finalize_assertions(
            [{"source_field": "awards"}],
            doi="10.1000/xyz",
            provider="openalex",
            provider_record_id="W1",
            retrieval_run_id="funding_test",
            retrieved_at_utc="2026-07-22T12:00:00+00:00",
            source_payload_sha256=payload_hash,
        )
        == []
    )


def test_screened_scope_applies_curated_exclusions_aliases_and_never_reads_kg_fields(tmp_path: Path):
    candidate_path = tmp_path / "candidate.parquet"
    screening_path = tmp_path / "screening.parquet"
    overrides_path = tmp_path / "overrides.json"
    pd.DataFrame(
        [
            {
                "doi": "10.1/keep",
                "pmid": "1",
                "openalex_id": "W1",
                "funders": "Untrusted historical text",
                "grant_ids": "LLM-1",
                "retained_for_extraction_candidate": True,
            },
            {
                "doi": "10.1/excluded",
                "pmid": "2",
                "openalex_id": "W2",
                "funders": "Also ignored",
                "retained_for_extraction_candidate": True,
            },
            {
                "doi": "10.1/alias",
                "pmid": "3",
                "openalex_id": "W3",
                "doi_alias_of": "10.1/keep",
                "retained_for_extraction_candidate": True,
            },
            {
                "doi": "10.1/screened-out",
                "retained_for_extraction_candidate": False,
            },
        ]
    ).to_parquet(candidate_path, index=False)
    pd.DataFrame(
        [
            {"doi": "10.1/keep", "screening_decision": "include_in_scope"},
            {"doi": "10.1/excluded", "screening_decision": "include_in_scope"},
            {"doi": "10.1/alias", "screening_decision": "include_in_scope"},
            {"doi": "10.1/screened-out", "screening_decision": "exclude_out_of_scope"},
        ]
    ).to_parquet(screening_path, index=False)
    overrides_path.write_text(
        json.dumps(
            {
                "overrides": [
                    {"dois": ["10.1/excluded"], "decision": "exclude_out_of_scope"}
                ]
            }
        ),
        encoding="utf-8",
    )

    scope, report = build_scope(
        candidate_table=candidate_path,
        screening_table=screening_path,
        screening_overrides=overrides_path,
        scope_mode="screened-in",
    )

    assert scope.to_dict("records") == [{"doi": "10.1/keep", "pmid": "1", "openalex_id": "W1"}]
    assert list(scope.columns) == ["doi", "pmid", "openalex_id"]
    assert report["curated_screening_exclusions"] == 1
    assert report["duplicate_aliases_suppressed"] == 1


def test_terminal_attempts_resume_and_successful_refresh_replaces_provider_rows():
    attempts = pd.DataFrame(columns=list(ATTEMPT_COLUMNS))
    attempt = {column: "" for column in ATTEMPT_COLUMNS}
    attempt.update(
        {
            "schema_version": FUNDING_ATTEMPT_SCHEMA_VERSION,
            "doi": "10.1/test",
            "provider": "openalex",
            "result_status": "no_funding_metadata",
            "retrieval_run_id": "run-1",
        }
    )
    attempts = append_attempt(attempts, attempt)
    assert terminal_provider_pairs(attempts) == {("10.1/test", "openalex")}
    assert terminal_provider_pairs_for_run(attempts, "run-1") == {("10.1/test", "openalex")}
    assert terminal_provider_pairs_for_run(attempts, "run-2") == set()

    retried = append_attempt(attempts, dict(attempt, result_status="error"))
    assert len(retried) == 2

    old = {column: "" for column in ASSERTION_COLUMNS}
    old.update(
        {
            "assertion_key": "old",
            "doi": "10.1/test",
            "provider": "openalex",
            "funder_name": "Old Funder",
        }
    )
    other = dict(old, assertion_key="other", provider="pubmed", funder_name="PubMed Funder")
    assertions = pd.DataFrame([old, other], columns=list(ASSERTION_COLUMNS))
    new = dict(old, assertion_key="new", funder_name="New Funder")

    replaced = replace_provider_assertions(
        assertions, doi="10.1/test", provider="openalex", rows=[new]
    )

    assert set(replaced["assertion_key"]) == {"new", "other"}


def test_audit_latest_attempts_prefers_successful_retry_timestamp():
    attempts = pd.DataFrame(
        [
            {
                "doi": "10.1/test",
                "provider": "pubmed",
                "result_status": "error",
                "retrieval_run_id": "run-1",
                "retrieved_at_utc": "2026-07-22T10:00:00+00:00",
            },
            {
                "doi": "10.1/test",
                "provider": "pubmed",
                "result_status": "no_funding_metadata",
                "retrieval_run_id": "run-2",
                "retrieved_at_utc": "2026-07-22T10:05:00+00:00",
            },
        ]
    )

    latest = latest_attempts(attempts)

    assert latest[["result_status", "retrieval_run_id"]].to_dict("records") == [
        {"result_status": "no_funding_metadata", "retrieval_run_id": "run-2"}
    ]


def test_runner_checkpoints_and_resumes_without_repeating_terminal_pair(
    tmp_path: Path, monkeypatch
):
    candidate_path = tmp_path / "candidate.parquet"
    screening_path = tmp_path / "screening.parquet"
    output_path = tmp_path / "paper_funding.parquet"
    attempts_path = tmp_path / "attempts.parquet"
    pd.DataFrame(
        [
            {
                "doi": "10.1/keep",
                "pmid": "1",
                "openalex_id": "W1",
                "funders": "Historical value must not be read",
            }
        ]
    ).to_parquet(candidate_path, index=False)
    pd.DataFrame(
        [{"doi": "10.1/keep", "screening_decision": "include_in_scope"}]
    ).to_parquet(screening_path, index=False)

    calls = []

    def fake_fetch(paper):
        calls.append(paper["doi"])
        return (
            "W1",
            {"funders": [{"display_name": "Provider Funder"}]},
            [{"source_field": "funders", "funder_name": "Provider Funder"}],
        )

    monkeypatch.setattr(
        funding_enrichment, "load_provider_settings", lambda args: ({}, {})
    )
    monkeypatch.setattr(
        funding_enrichment,
        "build_fetchers",
        lambda clients, settings: {"openalex": fake_fetch},
    )
    args = funding_enrichment.build_arg_parser().parse_args(
        [
            "--run-id",
            "funding-test-run",
            "--candidate-table",
            str(candidate_path),
            "--screening-table",
            str(screening_path),
            "--screening-overrides",
            str(tmp_path / "missing-overrides.json"),
            "--output-table",
            str(output_path),
            "--attempts-table",
            str(attempts_path),
            "--runs-dir",
            str(tmp_path / "runs"),
            "--providers",
            "openalex",
            "--write-every",
            "1",
            "--progress-every",
            "0",
        ]
    )

    first = funding_enrichment.run(args)
    second = funding_enrichment.run(args)

    assert calls == ["10.1/keep"]
    assert first["counts"]["provider_lookups_completed"] == 1
    assert second["counts"]["provider_lookups_completed"] == 0
    assert second["counts"]["provider_lookups_reused"] == 1
    assertions = pd.read_parquet(output_path)
    assert assertions[["funder_name", "provider"]].to_dict("records") == [
        {"funder_name": "Provider Funder", "provider": "openalex"}
    ]
    assert len(pd.read_parquet(attempts_path)) == 1
