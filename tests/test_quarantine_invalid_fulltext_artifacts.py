from __future__ import annotations

import json

import pandas as pd

from pipeline.fulltext.quarantine_invalid_fulltext_artifacts import (
    build_quarantine_plan,
    is_exact_article_repair,
    update_candidate_rows,
)


def write_artifact(path, doi, **extra):
    payload = {"study_doi": doi, "best_backend": "grobid", "best_char_count": 10000, **extra}
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_unverified_artifact_enters_plan(tmp_path):
    artifact_dir = tmp_path / "articles"
    artifact_dir.mkdir()
    path = artifact_dir / "10_1234_bad.json"
    write_artifact(path, "10.1234/bad")
    audit = {"rows": [{"requested_doi": "10.1234/bad", "identity_verified": False, "identity_status": "identity_mismatch"}]}
    plan = build_quarantine_plan(audit=audit, special={}, artifact_dir=artifact_dir)
    assert len(plan) == 1
    assert plan[0]["reasons"] == ["identity_mismatch"]


def test_verified_proceedings_container_is_still_quarantined(tmp_path):
    artifact_dir = tmp_path / "articles"
    artifact_dir.mkdir()
    path = artifact_dir / "10_1234_container.json"
    write_artifact(path, "10.1234/container")
    audit = {"rows": [{"requested_doi": "10.1234/container", "identity_verified": True}]}
    special = {"10.1234/container": {"classification": "proceedings_container"}}
    plan = build_quarantine_plan(audit=audit, special=special, artifact_dir=artifact_dir)
    assert plan[0]["reasons"] == ["unsegmented_proceedings_container"]


def test_exact_jats_proceedings_repair_is_kept(tmp_path):
    artifact = {
        "repair_run_id": "source_identity_repair_20260710",
        "best_backend": "europepmc_fulltext_xml",
        "source_identity": {"status": "verified_exact_doi"},
    }
    assert is_exact_article_repair(artifact) is True


def test_candidate_acquisition_fields_are_cleared():
    frame = pd.DataFrame(
        [{
            "doi": "10.1234/bad",
            "pdf_local_path": "/tmp/bad.pdf",
            "pdf_sha256": "abc",
            "local_pdf_paths": "/tmp/bad.pdf | /tmp/other.pdf",
            "pdf_download_status": "downloaded",
            "has_converted_full_text": True,
            "flag_has_local_pdf": True,
            "fulltext_artifact_paths": "/tmp/bad.json",
            "fulltext_char_count": 100,
        }]
    )
    updated, report = update_candidate_rows(
        frame,
        [{"doi": "10.1234/bad", "pdf_local_path": "/tmp/bad.pdf"}],
    )
    row = updated.iloc[0]
    assert row.pdf_local_path == ""
    assert row.local_pdf_paths == "/tmp/other.pdf"
    assert row.pdf_download_status == "source_identity_quarantined"
    assert bool(row.has_converted_full_text) is False
    assert report["rows_changed"] == 1
