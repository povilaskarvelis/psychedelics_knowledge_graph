import json

import pandas as pd

from pipeline.fulltext.reconcile_quarantined_candidate_state import (
    reconcile_candidate_rows,
    reconciliation_target_dois,
)


def test_restored_active_doi_is_excluded_from_reconciliation(tmp_path):
    artifact_dir = tmp_path / "articles"
    artifact_dir.mkdir()
    (artifact_dir / "restored.json").write_text(
        json.dumps({"study_doi": "10.1000/restored", "best_char_count": 1234}),
        encoding="utf-8",
    )
    payload = {
        "records": [
            {"doi": "10.1000/restored", "status": "quarantined"},
            {"doi": "10.1000/still-missing", "status": "quarantined"},
        ]
    }

    targets, restored = reconciliation_target_dois(payload, artifact_dir)

    assert targets == {"10.1000/still-missing"}
    assert restored == {"10.1000/restored"}


def test_reconciliation_clears_stale_access_tier_and_fulltext_fields():
    frame = pd.DataFrame(
        [
            {
                "doi": "10.1000/quarantined",
                "pdf_local_path": "/tmp/wrong.pdf",
                "local_pdf_paths": "/tmp/wrong.pdf",
                "local_pdf_count": 1,
                "pdf_sha256": "bad-hash",
                "pdf_download_status": "downloaded",
                "flag_has_local_pdf": True,
                "best_extraction_access_tier": "full_text_available",
                "has_converted_full_text": True,
                "fulltext_artifact_paths": "/tmp/wrong.json",
                "fulltext_char_count": 999,
                "unrelated_field": "preserve",
            },
            {
                "doi": "10.1000/unrelated",
                "pdf_local_path": "/tmp/keep.pdf",
                "local_pdf_paths": "/tmp/keep.pdf",
                "local_pdf_count": 1,
                "pdf_sha256": "keep-hash",
                "pdf_download_status": "downloaded",
                "flag_has_local_pdf": True,
                "best_extraction_access_tier": "full_text_available",
                "has_converted_full_text": True,
                "fulltext_artifact_paths": "/tmp/keep.json",
                "fulltext_char_count": 100,
                "unrelated_field": "untouched",
            },
        ]
    )

    updated, report = reconcile_candidate_rows(frame, {"10.1000/quarantined"})

    quarantined = updated.set_index("doi").loc["10.1000/quarantined"]
    assert quarantined.best_extraction_access_tier == ""
    assert bool(quarantined.has_converted_full_text) is False
    assert quarantined.fulltext_artifact_paths == ""
    assert quarantined.fulltext_char_count == 0
    assert quarantined.pdf_local_path == ""
    assert quarantined.pdf_download_status == "source_identity_quarantined"
    assert bool(quarantined.flag_has_local_pdf) is False
    assert quarantined.unrelated_field == "preserve"

    unrelated = updated.set_index("doi").loc["10.1000/unrelated"]
    assert unrelated.to_dict() == frame.set_index("doi").loc["10.1000/unrelated"].to_dict()
    assert report["rows_changed"] == 1
    assert report["matched_target_dois"] == ["10.1000/quarantined"]


def test_reconciliation_reports_missing_candidate_doi():
    frame = pd.DataFrame([{"doi": "10.1000/present", "best_extraction_access_tier": "abstract_only"}])

    updated, report = reconcile_candidate_rows(frame, {"10.1000/missing"})

    pd.testing.assert_frame_equal(updated, frame)
    assert report["rows_changed"] == 0
    assert report["missing_target_dois"] == ["10.1000/missing"]
