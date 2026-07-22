import json
from pathlib import Path

import pytest

from pipeline.fulltext.build_historical_fulltext_backfill import (
    active_abstract_only_outputs,
    classify_action,
    local_pdf_available,
    refreshed_open_access_evidence_from_report,
)


def test_active_outputs_select_abstract_only_and_canonicalize_alias(tmp_path: Path) -> None:
    outputs = tmp_path / "outputs.jsonl"
    rows = [
        {
            "status": "ok",
            "route_id": "a",
            "result": {"study_doi": "10.1/alias", "text_depth": "abstract_only", "items": [{}, {}]},
        },
        {
            "status": "ok",
            "route_id": "b",
            "result": {"study_doi": "10.1/full", "text_depth": "article_text", "items": [{}]},
        },
    ]
    outputs.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    pointer = tmp_path / "pointer.json"
    pointer.write_text(json.dumps({"outputs_jsonl": str(outputs)}), encoding="utf-8")

    selected, selected_path = active_abstract_only_outputs(pointer, {"10.1/alias": "10.1/canonical"})

    assert selected_path == outputs
    assert selected == {
        "10.1/canonical": {"task_count": 1, "item_count": 2, "route_ids": ["a"]}
    }


def test_backfill_action_requires_fresh_positive_oa_status() -> None:
    base = {"retained_for_extraction_candidate": True}
    assert classify_action(base, refreshed=False, access_override={})[0] == "refresh_oa_status"
    assert classify_action(base, refreshed=True, access_override={})[0] == "no_accessible_fulltext"
    assert (
        classify_action(
            {**base, "open_access_is_oa": "true", "best_pdf_url": "https://example.org/paper.pdf"},
            refreshed=True,
            access_override={},
        )[0]
        == "download_known_pdf"
    )
    assert (
        classify_action(
            {**base, "open_access_status": "green", "open_access_url": "https://example.org/article"},
            refreshed=True,
            access_override={},
        )[0]
        == "resolve_oa_landing_page"
    )
    assert (
        classify_action(
            {
                **base,
                "open_access_is_oa": "true",
                "best_pdf_url": "https://example.org/article/landing",
            },
            refreshed=True,
            access_override={},
        )[0]
        == "resolve_oa_landing_page"
    )


def test_manual_no_pdf_override_prevents_repeated_backfill() -> None:
    action = classify_action(
        {"retained_for_extraction_candidate": True, "open_access_is_oa": "true"},
        refreshed=True,
        access_override={"manual_access_action": "suppress_pdf_download"},
    )
    assert action[0] == "no_accessible_fulltext"
    assert action[1] is False


def test_incomplete_oa_refresh_cannot_define_retrieval_cohort(tmp_path: Path) -> None:
    report = tmp_path / "oa_refresh.json"
    report.write_text(
        json.dumps({"complete": False, "records": [{"doi": "10.1/partial"}]}),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="OA refresh report is incomplete"):
        refreshed_open_access_evidence_from_report(report)

    report.write_text(
        json.dumps(
            {
                "complete": True,
                "records": [
                    {"doi": "10.1/open", "fresh_open_access_positive": True},
                    {"doi": "10.1/closed", "fresh_open_access_positive": False},
                ],
            }
        ),
        encoding="utf-8",
    )
    assert refreshed_open_access_evidence_from_report(report) == {
        "10.1/open": True,
        "10.1/closed": False,
    }


def test_old_oa_label_cannot_override_fresh_negative_evidence() -> None:
    action = classify_action(
        {
            "retained_for_extraction_candidate": True,
            "open_access_is_oa": "true",
            "best_pdf_url": "https://example.org/stale.pdf",
        },
        refreshed=True,
        fresh_oa_positive=False,
        access_override={},
    )
    assert action[0] == "no_accessible_fulltext"


def test_stale_local_pdf_flag_is_not_a_usable_file(tmp_path: Path) -> None:
    missing = tmp_path / "moved_to_quarantine.pdf"
    assert not local_pdf_available(
        {"flag_has_local_pdf": True, "pdf_local_path": str(missing)}
    )
    missing.write_bytes(b"%PDF-1.7\n")
    assert local_pdf_available(
        {"flag_has_local_pdf": False, "pdf_local_path": str(missing)}
    )
