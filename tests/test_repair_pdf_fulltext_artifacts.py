from __future__ import annotations

from pipeline.fulltext.repair_pdf_fulltext_artifacts import (
    candidate_urls,
    target_is_repair_candidate,
    url_is_eligible,
    validate_pdf_front_page,
)


def test_candidate_urls_put_manual_urls_first_and_deduplicate():
    rows = candidate_urls(
        {"best_pdf_url": "https://example.org/a.pdf", "pdf_url_candidates": "https://example.org/b.pdf"},
        {"open_access_url": "https://example.org/a.pdf"},
        manual_urls=["https://publisher.test/right.pdf"],
    )
    assert rows == [
        "https://publisher.test/right.pdf",
        "https://example.org/a.pdf",
        "https://example.org/b.pdf",
    ]


def test_stale_pmc_and_ancillary_urls_are_rejected():
    assert url_is_eligible("https://europepmc.org/api/getPdf?pmcid=PMC123", {"PMC123"}) == (
        False,
        "stale_unverified_pmcid",
    )
    assert url_is_eligible("https://example.org/supplementary-figure-2.pdf", set()) == (
        False,
        "ancillary_url",
    )


def test_pdf_front_page_requires_title_and_usable_text(monkeypatch):
    monkeypatch.setattr(
        "pipeline.fulltext.repair_pdf_fulltext_artifacts.extract_pdf_text_from_bytes",
        lambda body, max_pages=1: (
            "A sufficiently long publisher page. The Effects of Psilocybin on Emotional Processing "
            "in Healthy Adults. doi:10.1234/example.1 " + "Methods and results. " * 30
        ),
    )
    result = validate_pdf_front_page(
        doi="10.1234/example.1",
        title="The Effects of Psilocybin on Emotional Processing in Healthy Adults",
        body=b"%PDF-test",
    )
    assert result["accepted"] is True
    assert result["doi_match"] is True


def test_pdf_front_page_rejects_supplement(monkeypatch):
    monkeypatch.setattr(
        "pipeline.fulltext.repair_pdf_fulltext_artifacts.extract_pdf_text_from_bytes",
        lambda body, max_pages=1: (
            "Supplementary material. The Effects of Psilocybin on Emotional Processing in Healthy Adults. "
            + "Supplemental table. " * 30
        ),
    )
    result = validate_pdf_front_page(
        doi="10.1234/example.1",
        title="The Effects of Psilocybin on Emotional Processing in Healthy Adults",
        body=b"%PDF-test",
    )
    assert result["accepted"] is False
    assert result["reason"] == "ancillary_document"


def test_dedicated_identity_paths_are_not_pdf_repair_candidates():
    audit = {"identity_verified": False, "requested_title": "A paper"}
    assert target_is_repair_candidate(audit, {"classification": "proceedings_container"}, {}) == (
        False,
        "dedicated_proceedings_container_path",
    )
    assert target_is_repair_candidate(audit, {}, {"identity_class": "valid_known_alias"}) == (
        False,
        "dedicated_valid_known_alias_identity_path",
    )


def test_main_article_with_correction_artifact_remains_candidate():
    audit = {"identity_verified": False, "requested_title": "Main randomized trial"}
    assert target_is_repair_candidate(audit, {"classification": "correction_or_erratum"}, {}) == (True, "")
