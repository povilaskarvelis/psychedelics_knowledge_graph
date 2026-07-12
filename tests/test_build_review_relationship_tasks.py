from pathlib import Path

from pipeline.extract.build_review_relationship_tasks import build_tasks, production_cohort


def test_builds_one_paper_centered_task_per_review() -> None:
    cohort = [
        {"doi": "10.1/full", "study_title": "Full", "study_year": "2025", "review_type": "review", "text_depth": "article_text"},
        {"doi": "10.1/abstract", "study_title": "Abstract", "study_year": "2024", "review_type": "systematic_review", "text_depth": "abstract_only"},
    ]
    candidates = [
        {"doi": "10.1/full", "study_title": "Full", "abstract": "Full abstract"},
        {"doi": "10.1/abstract", "study_title": "Abstract", "abstract": "Visible result"},
    ]
    packets = [
        {
            "study_doi": "10.1/full",
            "packet_id": "article:10.1/full",
            "paper_metadata": {"study_title": "Full", "abstract": "Full abstract"},
            "llm_chunks": [{"chunk_id": "C001", "heading": "Conclusion", "text": "Main conclusion"}],
        }
    ]
    tasks, report = build_tasks(cohort, candidates, packets, packets_path=Path("packets.jsonl"))

    assert len(tasks) == 2
    assert report["counts"]["ready_for_model"] == 2
    assert report["by_text_depth"] == {"article_text": 1, "abstract_only": 1}
    assert tasks[0]["source"]["packet_id"] == "article:10.1/full"
    assert tasks[1]["source"]["kind"] == "abstract_only"


def test_missing_required_source_is_not_model_ready() -> None:
    cohort = [{"doi": "10.1/missing", "study_title": "Missing", "text_depth": "article_text"}]
    tasks, report = build_tasks(cohort, [], [], packets_path=Path("packets.jsonl"))

    assert tasks[0]["task_status"] == "source_not_ready"
    assert report["by_source_status"] == {"missing_article_packet": 1}


def test_production_cohort_selects_ready_reviews_without_domain_routes() -> None:
    candidates = [
        {
            "doi": "10.1/full",
            "retained_for_extraction_candidate": True,
            "primary_secondary_source_type": "systematic_review",
            "extraction_route_status": "ready_for_article_text_extraction",
        },
        {
            "doi": "10.1/abstract",
            "retained_for_extraction_candidate": True,
            "primary_secondary_source_type": "review",
            "extraction_route_status": "ready_for_abstract_extraction",
        },
        {
            "doi": "10.1/meta",
            "retained_for_extraction_candidate": True,
            "primary_secondary_source_type": "meta_analysis",
            "extraction_route_status": "ready_for_article_text_extraction",
        },
        {
            "doi": "10.1/pending",
            "retained_for_extraction_candidate": True,
            "primary_secondary_source_type": "narrative_review",
            "extraction_route_status": "needs_pdf_download",
        },
    ]

    cohort, report = production_cohort(candidates)

    assert [(row["doi"], row["text_depth"]) for row in cohort] == [
        ("10.1/abstract", "abstract_only"),
        ("10.1/full", "article_text"),
    ]
    assert report["skipped"] == {"needs_pdf_download": 1}
