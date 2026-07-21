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


def test_doi_article_recovery_excludes_untrusted_and_nonarticle_records() -> None:
    df = pd.DataFrame(
        [
            {
                "doi": "10.7454/jpdi.v9i4.1025",
                "study_title": "A journal case report",
                "study_journal": "Jurnal Penyakit Dalam Indonesia",
                "publication_type": "article",
                "best_pdf_url": "https://scholarhub.ui.ac.id/cgi/viewcontent.cgi?article=1025&context=jpdi",
                "pdf_download_failure_category": "forbidden",
                "route_count": 1,
            },
            {
                "doi": "10.26021/7388",
                "study_title": "Adolescent exposure study",
                "study_journal": "UC Research Repository (University of Canterbury)",
                "publication_type": "article",
                "best_pdf_url": "https://example.org/thesis3.pdf",
                "pdf_download_failure_category": "forbidden",
                "route_count": 1,
            },
            {
                "doi": "10.1002/example.123",
                "study_title": "A journal systematic review",
                "study_journal": "Example Journal",
                "publication_type": "article",
                "best_pdf_url": "https://publisher.example/article.pdf",
                "pdf_download_failure_category": "forbidden",
                "route_count": 1,
            },
            {
                "doi": "10.1093/example/qdad060.055",
                "study_title": "(058) A numbered conference abstract",
                "study_journal": "Example Journal",
                "publication_type": "review",
                "best_pdf_url": "https://publisher.example/supplement.pdf",
                "pdf_download_failure_category": "forbidden",
                "route_count": 1,
            },
        ]
    )

    ranked = rank_rows(df).set_index("doi")

    assert not bool(ranked.loc["10.7454/jpdi.v9i4.1025", "manual_doi_article_recovery_candidate"])
    assert "untrusted" in ranked.loc["10.7454/jpdi.v9i4.1025", "manual_doi_article_recovery_hint"]
    assert not bool(ranked.loc["10.26021/7388", "manual_doi_article_recovery_candidate"])
    assert "repository" in ranked.loc["10.26021/7388", "manual_doi_article_recovery_hint"]
    assert bool(ranked.loc["10.1002/example.123", "manual_doi_article_recovery_candidate"])
    assert ranked.loc["10.1002/example.123", "manual_doi_landing_url"] == "https://doi.org/10.1002/example.123"
    assert not bool(ranked.loc["10.1093/example/qdad060.055", "manual_doi_article_recovery_candidate"])
    assert "conference" in ranked.loc[
        "10.1093/example/qdad060.055", "manual_doi_article_recovery_hint"
    ]
