import pandas as pd

from pipeline.fulltext.rank_manual_pdf_queue import rank_rows


def test_rank_rows_preserves_columns_for_empty_queue() -> None:
    df = pd.DataFrame(columns=["doi", "study_title", "pdf_download_failure_category"])

    ranked = rank_rows(df)

    assert ranked.empty
    assert "manual_priority_tier" in ranked.columns
    assert "doi" in ranked.columns


def test_rank_rows_prioritizes_recoverable_high_value_records() -> None:
    df = pd.DataFrame(
        [
            {
                "doi": "10.1000/low",
                "study_title": "Closed publisher landing page",
                "open_access_status": "closed",
                "pdf_download_failure_category": "not_found",
                "best_pdf_url": "https://publisher.example/missing.pdf",
                "pdf_url_candidates": "",
                "open_access_url": "",
                "route_count": 1,
                "domain_routes": "clinical_outcome",
                "prompt_profiles": "primary_clinical",
                "source_types": "primary_or_unclear",
                "pdf_download_retry_recommended": False,
            },
            {
                "doi": "10.1000/high",
                "study_title": "Systematic review of psilocybin clinical outcomes",
                "open_access_status": "gold",
                "pdf_download_failure_category": "non_pdf_response",
                "best_pdf_url": "https://osf.io/example",
                "pdf_url_candidates": "https://osf.io/example|https://biorxiv.org/content/example",
                "open_access_url": "https://osf.io/example",
                "route_count": 4,
                "domain_routes": "clinical_outcome|safety_tolerability",
                "prompt_profiles": "secondary_meta_analysis|primary_clinical",
                "source_types": "meta_analysis",
                "pdf_download_retry_recommended": False,
            },
        ]
    )

    ranked = rank_rows(df)

    assert ranked.iloc[0]["doi"] == "10.1000/high"
    assert ranked.iloc[0]["manual_priority_tier"] in {"A", "B"}
    assert ranked.iloc[0]["manual_host_class"] == "repository_or_preprint"
    assert bool(ranked.iloc[0]["manual_browser_recovery_candidate"]) is True
    assert bool(ranked.iloc[0]["manual_preprint_like"]) is True
    assert ranked.iloc[-1]["doi"] == "10.1000/low"
    assert ranked.iloc[-1]["manual_priority_tier"] in {"C", "D"}
