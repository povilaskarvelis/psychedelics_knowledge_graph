import json

import pandas as pd

from pipeline.fulltext.build_browser_recovery_pilot import (
    build_candidates,
    host_balanced_pilot,
    independent_browser_urls,
    load_latest_scoped_results,
)


def test_independent_browser_urls_excludes_resolvers_indexes_and_untrusted_hosts() -> None:
    row = {
        "open_access_url": "https://doi.org/10.1000/example",
        "best_pdf_url": "https://pubmed.ncbi.nlm.nih.gov/123/",
        "pdf_url_candidates": (
            "https://doi.org/10.1000/example|https://repository.example/article/1|"
            "https://scholarhub.ui.ac.id/suspicious.pdf"
        ),
    }

    assert independent_browser_urls(row) == ["https://repository.example/article/1"]


def test_retry_report_overrides_main_report(tmp_path) -> None:
    first = tmp_path / "first.json"
    retry = tmp_path / "retry.json"
    first.write_text(json.dumps({"records": [{"doi": "10.1/a", "status": "download_failed"}]}))
    retry.write_text(json.dumps({"records": [{"doi": "10.1/a", "status": "downloaded"}]}))

    latest = load_latest_scoped_results([first, retry])

    assert latest["10.1/a"]["status"] == "downloaded"
    assert latest["10.1/a"]["scope_report"] == str(retry.resolve())


def test_build_candidates_requires_active_failed_browser_candidate_and_independent_url() -> None:
    ranked = pd.DataFrame(
        [
            {
                "doi": "10.1/include",
                "manual_browser_recovery_candidate": True,
                "manual_priority_tier": "C",
                "manual_priority_score": 80,
                "manual_recoverability_score": 50,
                "open_access_url": "https://repository.example/include",
            },
            {
                "doi": "10.1/doi-only",
                "manual_browser_recovery_candidate": True,
                "manual_priority_tier": "C",
                "manual_priority_score": 80,
                "manual_recoverability_score": 50,
                "open_access_url": "https://doi.org/10.1/doi-only",
            },
            {
                "doi": "10.1/downloaded",
                "manual_browser_recovery_candidate": True,
                "manual_priority_tier": "B",
                "manual_priority_score": 100,
                "manual_recoverability_score": 70,
                "open_access_url": "https://repository.example/downloaded",
            },
        ]
    )
    scoped = {
        "10.1/include": {"status": "download_failed", "failure_category": "forbidden"},
        "10.1/doi-only": {"status": "download_failed", "failure_category": "forbidden"},
        "10.1/downloaded": {"status": "downloaded"},
    }

    candidates = build_candidates(ranked, scoped)

    assert candidates["doi"].tolist() == ["10.1/include"]
    assert candidates.iloc[0]["browser_preferred_url"] == "https://doi.org/10.1/include"
    assert candidates.iloc[0]["browser_primary_strategy"] == "doi_landing_only_stop_on_closed_access"
    assert candidates.iloc[0]["browser_doi_prefix"] == "10.1"
    assert candidates.iloc[0]["browser_oa_evidence_urls"] == "https://repository.example/include"


def test_host_balanced_pilot_uses_high_priority_phase_and_interleaves_hosts() -> None:
    candidates = pd.DataFrame(
        [
            {"doi": "10.1/a1", "manual_priority_tier": "B", "browser_doi_prefix": "10.1"},
            {"doi": "10.1/a2", "manual_priority_tier": "C", "browser_doi_prefix": "10.1"},
            {"doi": "10.2/b1", "manual_priority_tier": "C", "browser_doi_prefix": "10.2"},
            {"doi": "10.3/d1", "manual_priority_tier": "D", "browser_doi_prefix": "10.3"},
        ]
    )

    pilot = host_balanced_pilot(candidates, 3)

    assert pilot["doi"].tolist() == ["10.1/a1", "10.2/b1", "10.1/a2"]
    assert pilot["browser_pilot_index"].tolist() == [1, 2, 3]
