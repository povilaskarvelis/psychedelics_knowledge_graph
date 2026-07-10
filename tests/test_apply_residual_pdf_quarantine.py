from pathlib import Path

import pandas as pd

from pipeline.fulltext.apply_residual_pdf_quarantine import (
    candidate_path_reference_map,
    clear_candidate_reference,
)


def test_clear_candidate_reference_removes_only_target_path(tmp_path: Path) -> None:
    target = tmp_path / "wrong.pdf"
    other = tmp_path / "other.pdf"
    frame = pd.DataFrame(
        [{
            "doi": "10.1000/example",
            "pdf_local_path": str(target),
            "local_pdf_paths": f"{target} | {other}",
            "local_pdf_count": 2,
            "pdf_sha256": "bad",
            "pdf_download_status": "downloaded",
            "flag_has_local_pdf": True,
            "best_extraction_access_tier": "full_text_available",
            "has_converted_full_text": True,
            "fulltext_artifact_paths": "/tmp/wrong.json",
            "fulltext_char_count": 100,
        }]
    )

    changes = clear_candidate_reference(frame, 0, target)

    assert frame.at[0, "pdf_local_path"] == ""
    assert frame.at[0, "local_pdf_paths"] == ""
    assert frame.at[0, "pdf_download_status"] == "source_identity_quarantined"
    assert bool(frame.at[0, "has_converted_full_text"]) is False
    assert "pdf_local_path" in changes
    assert candidate_path_reference_map(
        pd.DataFrame([{"pdf_local_path": str(target), "local_pdf_paths": str(target)}])
    ) == {str(target.resolve()): [0]}
