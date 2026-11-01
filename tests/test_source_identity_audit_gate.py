import json
import os
from pathlib import Path

import pytest

import pipeline.fulltext.source_identity_audit_gate as gate_module
from pipeline.fulltext.source_identity import file_sha256
from pipeline.fulltext.source_identity_audit_gate import (
    GATE_ARTIFACT_CHANGED,
    GATE_IDENTITY_UNVERIFIED,
    GATE_NOT_AUDITED,
    GATE_REGISTRY_CHANGED,
    GATE_VERIFIED,
    SourceIdentityAuditGate,
    refresh_source_identity_audit,
)


def write_audit_fixture(
    root: Path,
    *,
    doi: str = "10.1234/example",
    verified: bool = True,
    rows: list[dict] | None = None,
) -> tuple[Path, Path, Path, Path]:
    artifact = root / "article.json"
    artifact.write_text('{"best_char_count": 100}\n', encoding="utf-8")
    identity_registry = root / "source_identity_registry.json"
    hash_registry = root / "source_identity_pdf_hash_registry.json"
    identity_registry.write_text("{}\n", encoding="utf-8")
    hash_registry.write_text("{}\n", encoding="utf-8")
    audit = root / "source_identity_audit.json"
    audit.write_text(
        json.dumps(
            {
                "identity_registry": {"path": str(identity_registry)},
                "pdf_hash_attestation_registry": {"path": str(hash_registry)},
                "rows": rows
                if rows is not None
                else [
                    {
                        "requested_doi": doi,
                        "artifact_path": str(artifact.resolve()),
                        "identity_verified": verified,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return audit, artifact, identity_registry, hash_registry


def make_newer_than(path: Path, reference: Path) -> None:
    newer = reference.stat().st_mtime_ns + 1_000_000_000
    os.utime(path, ns=(newer, newer))


def test_gate_requires_exact_doi_and_resolved_artifact_path(tmp_path: Path) -> None:
    audit, artifact, _identity_registry, _hash_registry = write_audit_fixture(tmp_path)
    gate = SourceIdentityAuditGate(audit)

    assert gate.is_verified("10.1234/example", artifact)
    assert not gate.is_verified("10.1234/other", artifact)
    other = tmp_path / "other.json"
    other.write_text(artifact.read_text(encoding="utf-8"), encoding="utf-8")
    older = audit.stat().st_mtime_ns - 1_000_000
    os.utime(other, ns=(older, older))
    assert not gate.is_verified("10.1234/example", other)
    assert gate.status("10.1234/example", other) == GATE_NOT_AUDITED


def test_changed_artifact_is_rejected_alone_without_stopping_the_gate(tmp_path: Path) -> None:
    second = tmp_path / "second.json"
    second.write_text('{"best_char_count": 200}\n', encoding="utf-8")
    first = tmp_path / "article.json"
    audit, artifact, _identity_registry, _hash_registry = write_audit_fixture(
        tmp_path,
        rows=[
            {"requested_doi": "10.1234/first", "artifact_path": str(first.resolve()), "identity_verified": True},
            {"requested_doi": "10.1234/second", "artifact_path": str(second.resolve()), "identity_verified": True},
        ],
    )
    gate = SourceIdentityAuditGate(audit)
    artifact.write_text('{"best_char_count": 999}\n', encoding="utf-8")
    make_newer_than(artifact, audit)

    assert gate.status("10.1234/first", artifact) == GATE_ARTIFACT_CHANGED
    assert gate.status("10.1234/second", second) == GATE_VERIFIED
    assert gate.rejection_counts() == {GATE_ARTIFACT_CHANGED: 1}


def test_newer_file_time_with_unchanged_content_hash_stays_verified(tmp_path: Path) -> None:
    artifact = tmp_path / "article.json"
    artifact.write_text('{"best_char_count": 100}\n', encoding="utf-8")
    audit, artifact, _identity_registry, _hash_registry = write_audit_fixture(
        tmp_path,
        rows=[
            {
                "requested_doi": "10.1234/example",
                "artifact_path": str(artifact.resolve()),
                "identity_verified": True,
                "artifact_sha256": file_sha256(artifact),
            }
        ],
    )
    gate = SourceIdentityAuditGate(audit)
    make_newer_than(artifact, audit)

    assert gate.is_verified("10.1234/example", artifact)

    artifact.write_text('{"best_char_count": 101}\n', encoding="utf-8")
    make_newer_than(artifact, audit)
    assert gate.status("10.1234/example", artifact) == GATE_ARTIFACT_CHANGED


def test_registry_change_rejects_only_the_dois_it_names(tmp_path: Path) -> None:
    second = tmp_path / "second.json"
    second.write_text('{"best_char_count": 200}\n', encoding="utf-8")
    first = tmp_path / "article.json"
    audit, artifact, identity_registry, _hash_registry = write_audit_fixture(
        tmp_path,
        rows=[
            {"requested_doi": "10.1234/listed", "artifact_path": str(first.resolve()), "identity_verified": True},
            {"requested_doi": "10.1234/unlisted", "artifact_path": str(second.resolve()), "identity_verified": True},
        ],
    )
    identity_registry.write_text(
        json.dumps({"records": [{"requested_doi": "10.1234/LISTED"}]}),
        encoding="utf-8",
    )
    make_newer_than(identity_registry, audit)

    gate = SourceIdentityAuditGate(audit)

    assert gate.status("10.1234/listed", artifact) == GATE_REGISTRY_CHANGED
    assert gate.is_verified("10.1234/unlisted", second)


def test_registry_change_rejects_dois_that_used_the_registry_when_audited(tmp_path: Path) -> None:
    artifact = tmp_path / "article.json"
    audit, artifact, _identity_registry, hash_registry = write_audit_fixture(
        tmp_path,
        rows=[
            {
                "requested_doi": "10.1234/attested",
                "artifact_path": str(artifact.resolve()),
                "identity_verified": True,
                "pdf_hash_attestation_present": True,
            }
        ],
    )
    # The attestation was removed after the audit; the old verdict cannot stand.
    hash_registry.write_text(json.dumps({"records": []}), encoding="utf-8")
    make_newer_than(hash_registry, audit)

    gate = SourceIdentityAuditGate(audit)

    assert gate.status("10.1234/attested", artifact) == GATE_REGISTRY_CHANGED


def test_unverified_artifact_is_rejected_with_its_reason(tmp_path: Path) -> None:
    audit, artifact, _identity_registry, _hash_registry = write_audit_fixture(tmp_path, verified=False)
    gate = SourceIdentityAuditGate(audit)

    assert gate.status("10.1234/example", artifact) == GATE_IDENTITY_UNVERIFIED
    assert not gate.is_verified("10.1234/example", artifact)


def test_require_passing_still_refuses_an_audit_with_unverified_rows(tmp_path: Path) -> None:
    audit, _artifact, _identity_registry, _hash_registry = write_audit_fixture(tmp_path, verified=False)

    with pytest.raises(RuntimeError, match="not passing"):
        SourceIdentityAuditGate(audit, require_passing=True)


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
