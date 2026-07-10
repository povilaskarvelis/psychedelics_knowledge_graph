from __future__ import annotations

import hashlib

from pipeline.fulltext.restore_validated_pdf_repairs import validated_repair_artifact


def test_validated_repair_artifact_requires_hash_and_front_page_evidence(tmp_path) -> None:
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-correct")
    artifact = {
        "repair_run_id": "source_identity_repair_20260710",
        "fulltext_source": "validated_pdf_source_identity_repair",
        "pdf_sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(),
        "source_identity": {
            "status": "verified_title_only",
            "verified": True,
            "pdf_front_page_validation": {
                "accepted": True,
                "reason": "verified_front_page",
                "title_score": 0.9,
                "front_page_char_count": 500,
            },
        },
    }

    assert validated_repair_artifact(artifact, pdf) == (True, "")
    pdf.write_bytes(b"%PDF-wrong")
    assert validated_repair_artifact(artifact, pdf) == (False, "pdf_hash_mismatch")
