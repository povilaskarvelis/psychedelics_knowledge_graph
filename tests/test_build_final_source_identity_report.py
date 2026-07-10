from pathlib import Path

from pipeline.fulltext.build_final_source_identity_report import (
    acceptance_guidance,
    artifact_set_fingerprint,
    fulltext_repair_requirement,
    manual_action_category,
    priority_fields,
    reconcile_original_doi,
    safe_candidate_urls,
)


def test_abstract_only_retained_record_does_not_require_fulltext_repair() -> None:
    required, reason = fulltext_repair_requirement(
        {"extraction_route_status": "ready_for_abstract_extraction"},
        {"route_actions": "extract_from_abstract_only"},
    )

    assert not required
    assert "public abstract" in reason


def test_download_route_requires_public_fulltext_repair() -> None:
    required, reason = fulltext_repair_requirement(
        {"extraction_route_status": "needs_pdf_download"},
        {"route_actions": "download_pdf_then_extract"},
    )

    assert required
    assert "public full-text" in reason


def test_reconcile_sici_prefers_unique_current_artifact_among_title_duplicates() -> None:
    truncated = "10.1002/(sici)1521-3838(199912)18:6"
    current = truncated + "<548::aid-qsar548>3.0.co;2-b"
    alternate = truncated + "<548::aid-qsar548>3.3.co;2-2"
    title = "Quasi-atomistic Receptor Surrogates for the 5-HT2A Receptor"
    candidates = {
        current: {"study_title": title},
        alternate: {"study_title": title},
    }

    assert reconcile_original_doi(truncated, title, {current}, candidates) == current


def test_safe_candidate_urls_excludes_failed_ancillary_and_stale_pmc_urls() -> None:
    good = "https://publisher.example/article.pdf"
    failed = "https://publisher.example/failed.pdf"
    supplement = "https://publisher.example/supporting_information.pdf"
    verified_pmc = "https://pmc.ncbi.nlm.nih.gov/articles/PMC123/pdf/main.pdf"
    stale_pmc = "https://pmc.ncbi.nlm.nih.gov/articles/PMC999/pdf/main.pdf"
    rows = [
        (
            "candidate",
            {
                "best_pdf_url": good,
                "pdf_url_candidates": " | ".join(
                    [failed, supplement, verified_pmc, stale_pmc, "ftp://example.org/article.pdf"]
                ),
            },
        )
    ]

    accepted, excluded = safe_candidate_urls(
        "10.1000/example",
        "PMC123",
        rows,
        {failed: "download_failed"},
    )

    assert [item["url"] for item in accepted] == [good, verified_pmc]
    assert excluded["known_attempt:download_failed"] == 1
    assert excluded["ancillary_url_pattern"] == 1
    assert excluded["unverified_or_stale_pmcid"] == 1
    assert excluded["not_http"] == 1


def test_manual_category_uses_identity_reason_when_no_special_class() -> None:
    assert manual_action_category("", ["identity_mismatch"]) == "manual_identity_mismatch"
    assert manual_action_category("", ["identity_unverified"]) == "manual_identity_unverified"


def test_priority_never_overrides_current_non_retention() -> None:
    eligible, tier, score, reason, flags = priority_fields(
        {
            "retained_for_extraction_candidate": False,
            "flag_in_claim_stubs": True,
        },
        0,
    )

    assert not eligible
    assert tier == "not_in_priority_queue"
    assert score == 0
    assert "not currently retained" in reason
    assert flags == "flag_in_claim_stubs"


def test_retained_record_with_curated_signal_is_prioritized() -> None:
    eligible, tier, score, reason, flags = priority_fields(
        {
            "retained_for_extraction_candidate": True,
            "flag_in_claim_stubs": True,
        },
        0,
    )

    assert eligible
    assert tier == "P1_existing_kg_or_curated_signal"
    assert score == 380
    assert reason == "retained_for_extraction_candidate | flag_in_claim_stubs"
    assert flags == "flag_in_claim_stubs"


def test_acceptance_guidance_requires_both_doi_and_title_for_short_titles() -> None:
    guidance = acceptance_guidance("manual_identity_unverified", "Short title")

    assert "require both an exact DOI and a front-page title match" in guidance
    assert "identity_verified=true" in guidance


def test_artifact_set_fingerprint_changes_with_content(tmp_path: Path) -> None:
    artifact = tmp_path / "one.json"
    artifact.write_text('{"value": 1}\n', encoding="utf-8")
    before = artifact_set_fingerprint(tmp_path)
    artifact.write_text('{"value": 2}\n', encoding="utf-8")
    after = artifact_set_fingerprint(tmp_path)

    assert before["file_count"] == after["file_count"] == 1
    assert before["sha256"] != after["sha256"]
