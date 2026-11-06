import json
from pathlib import Path

import pytest

import pipeline.fulltext.source_identity_audit_gate as gate_module
from pipeline.fulltext.source_identity_audit_gate import refresh_source_identity_audit


def test_refresh_records_unverified_artifacts_without_stopping(tmp_path: Path, monkeypatch) -> None:
    written_bad = tmp_path / "articles" / "bad.json"
    written_good = tmp_path / "articles" / "good.json"
    report = {
        "counts": {"artifacts": 2, "verified": 1, "not_verified": 1},
        "rows": [
            {"requested_doi": "10.1234/bad", "artifact_path": str(written_bad), "identity_verified": False},
            {"requested_doi": "10.1234/good", "artifact_path": str(written_good), "identity_verified": True},
        ],
    }
    monkeypatch.setattr(gate_module, "audit_artifacts", lambda *args, **kwargs: dict(report))
    monkeypatch.setattr(gate_module, "source_identity_metadata_map", lambda *args: {})
    monkeypatch.setattr(gate_module, "load_identity_registry", lambda path: {"records": {}})
    monkeypatch.setattr(gate_module, "load_pdf_hash_attestation_registry", lambda path: {"records": {}})
    kwargs = dict(
        artifact_dir=tmp_path / "articles",
        candidate_table=tmp_path / "candidates.parquet",
        metadata_table=tmp_path / "metadata.parquet",
        report_json=tmp_path / "audit.json",
        report_csv=tmp_path / "audit.csv",
        unverified_doi_file=tmp_path / "unverified.txt",
        identity_registry_path=tmp_path / "registry.json",
        pdf_hash_attestation_registry_path=tmp_path / "hash_registry.json",
    )

    result = refresh_source_identity_audit(written_artifacts=[written_bad, written_good], **kwargs)

    assert result["written_unverified_artifacts"] == [str(written_bad.resolve())]
    assert (tmp_path / "unverified.txt").read_text(encoding="utf-8") == "10.1234/bad\n"
    assert "written_unverified_artifacts" not in json.loads((tmp_path / "audit.json").read_text(encoding="utf-8"))

    with pytest.raises(RuntimeError, match="unverified full-text artifacts"):
        refresh_source_identity_audit(fail_on_unverified=True, **kwargs)
