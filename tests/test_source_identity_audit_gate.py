import json
import os
from pathlib import Path

import pytest

from pipeline.fulltext.source_identity_audit_gate import SourceIdentityAuditGate


def write_audit_fixture(
    root: Path,
    *,
    doi: str = "10.1234/example",
    verified: bool = True,
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
                "rows": [
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


def test_gate_rejects_audit_older_than_artifact(tmp_path: Path) -> None:
    audit, artifact, _identity_registry, _hash_registry = write_audit_fixture(tmp_path)
    gate = SourceIdentityAuditGate(audit)
    newer = audit.stat().st_mtime_ns + 1_000_000_000
    os.utime(artifact, ns=(newer, newer))

    with pytest.raises(RuntimeError, match="artifact changed after the audit"):
        gate.is_verified("10.1234/example", artifact)


def test_gate_rejects_audit_older_than_registry(tmp_path: Path) -> None:
    audit, _artifact, identity_registry, _hash_registry = write_audit_fixture(tmp_path)
    newer = audit.stat().st_mtime_ns + 1_000_000_000
    os.utime(identity_registry, ns=(newer, newer))

    with pytest.raises(RuntimeError, match="identity registry changed after the audit"):
        SourceIdentityAuditGate(audit)
