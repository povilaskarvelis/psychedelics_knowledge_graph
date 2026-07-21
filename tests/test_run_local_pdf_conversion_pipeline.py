from types import SimpleNamespace

import pandas as pd

from pipeline.fulltext.run_local_pdf_conversion_pipeline import (
    local_pdf_conversion_queue,
    source_identity_audit_command,
)


def test_source_identity_audit_command_is_fail_closed(tmp_path) -> None:
    args = SimpleNamespace(
        python="python3",
        out_dir=str(tmp_path / "articles"),
        candidate_table=str(tmp_path / "candidate.parquet"),
        metadata_table=str(tmp_path / "metadata.parquet"),
        source_identity_audit_json=str(tmp_path / "audit.json"),
        source_identity_audit_csv=str(tmp_path / "audit.csv"),
        source_identity_unverified_dois=str(tmp_path / "unverified.txt"),
    )

    command = source_identity_audit_command(args)

    assert command[-1] == "--fail-on-unverified"
    assert "--artifact-dir" in command
    assert str(tmp_path / "articles") in command


def test_managed_conversion_queue_accepts_route_independent_worklist(tmp_path) -> None:
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.7\n")
    selection = tmp_path / "historical_backfill.parquet"
    pd.DataFrame(
        [
            {
                "doi": "10.1000/historical",
                "selected_for_downstream": True,
                "fulltext_enrichment_needed": True,
                "fulltext_enrichment_action": "convert_local_pdf",
                "local_pdf_paths": str(pdf),
                "study_title": "Historical paper",
            }
        ]
    ).to_parquet(selection, index=False)
    metadata = tmp_path / "metadata.parquet"
    pd.DataFrame([{"doi": "10.1000/historical"}]).to_parquet(metadata, index=False)
    args = SimpleNamespace(
        route_table=str(tmp_path / "unused_routes.parquet"),
        selection_table=str(selection),
        metadata_table=str(metadata),
        out_dir=str(tmp_path / "articles"),
        doi_file="",
        route_action="convert_local_pdf_then_extract",
        include_existing_artifacts=False,
        limit=0,
    )

    assert local_pdf_conversion_queue(args) == ["10.1000/historical"]
