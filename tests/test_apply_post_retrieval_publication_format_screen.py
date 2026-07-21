from __future__ import annotations

import argparse
import json

import pandas as pd

from pipeline.fulltext.apply_post_retrieval_publication_format_screen import (
    format_counts,
    run,
    select_format_screen_scope,
)


def test_selects_confirmed_post_retrieval_decisions_independently_of_prescreen() -> None:
    candidates = pd.DataFrame(
        [
            {"doi": "10.example/abstract", "prescreen_decisions": "retain", "post_retrieval_decision": ""},
            {"doi": "10.example/thesis", "prescreen_decisions": "exclude", "post_retrieval_decision": "exclude"},
            {"doi": "10.example/article", "prescreen_decisions": "retain", "post_retrieval_decision": ""},
        ]
    )
    curated = {
        "10.example/abstract": {"decision": "exclude", "publication_format": "conference_abstract"},
        "10.example/thesis": {"decision": "exclude", "publication_format": "dissertation"},
        "10.example/missing": {"decision": "exclude", "publication_format": "magazine_feature"},
    }

    scope = select_format_screen_scope(candidates, curated)

    assert scope["pending_dois"] == ["10.example/abstract"]
    assert scope["already_applied_dois"] == ["10.example/thesis"]
    assert scope["missing_candidate_dois"] == ["10.example/missing"]
    assert format_counts(scope["pending_dois"], curated) == {"conference_abstract": 1}


def test_requested_scope_rejects_dois_without_authoritative_evidence() -> None:
    candidates = pd.DataFrame(
        [
            {"doi": "10.example/abstract", "prescreen_decisions": "retain"},
            {"doi": "10.example/article", "prescreen_decisions": "retain"},
        ]
    )
    curated = {
        "10.example/abstract": {"decision": "exclude", "publication_format": "conference_abstract"},
    }

    scope = select_format_screen_scope(
        candidates,
        curated,
        requested_dois={"10.example/abstract", "10.example/article"},
    )

    assert scope["pending_dois"] == ["10.example/abstract"]
    assert scope["unconfirmed_dois"] == ["10.example/article"]


def test_scoped_apply_preserves_complete_materialized_decision_table(tmp_path) -> None:
    candidate_path = tmp_path / "candidate.parquet"
    ledger_path = tmp_path / "ledger.json"
    decisions_path = tmp_path / "decisions.parquet"
    report_path = tmp_path / "report.json"
    pd.DataFrame(
        [
            {
                "doi": "10.example/one",
                "retained_for_extraction_candidate": True,
                "post_retrieval_decision": "",
            },
            {
                "doi": "10.example/two",
                "retained_for_extraction_candidate": True,
                "post_retrieval_decision": "exclude",
            },
        ]
    ).to_parquet(candidate_path, index=False)
    ledger_path.write_text(
        json.dumps(
            {
                "records": [
                    {
                        "doi": "10.example/one",
                        "decision": "exclude",
                        "publication_format": "conference_abstract",
                    },
                    {
                        "doi": "10.example/two",
                        "decision": "exclude",
                        "publication_format": "dissertation_or_thesis",
                    },
                ]
            }
        )
    )

    run(
        argparse.Namespace(
            ledger=str(ledger_path),
            candidate_table=str(candidate_path),
            decisions_table=str(decisions_path),
            domain_routing_table="",
            extraction_routes_table="",
            extraction_tasks_jsonl="",
            report=str(report_path),
            run_id="test_scoped_apply",
            doi=["10.example/one"],
            apply=True,
        )
    )

    materialized = pd.read_parquet(decisions_path)
    assert set(materialized["doi"]) == {"10.example/one", "10.example/two"}
