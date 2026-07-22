from types import SimpleNamespace

import pandas as pd
import pytest

from pipeline.fulltext.run_local_pdf_conversion_pipeline import (
    failed_dois_from_artifacts,
    failed_dois_from_report,
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


def test_failed_dois_include_identity_rejected_extractions(tmp_path) -> None:
    report = tmp_path / "conversion.json"
    report.write_text(
        """{
          "records": [
            {
              "study_doi": "10.1000/verified",
              "best_backend": "grobid",
              "write_status": "successful extraction with verified source identity"
            },
            {
              "study_doi": "10.1000/mismatch",
              "best_backend": "grobid",
              "write_status": "successful extraction rejected because source identity was not verified"
            },
            {
              "study_doi": "10.1000/parser-failure",
              "best_backend": "",
              "write_status": "no successful extraction; artifact not written"
            },
            {
              "study_doi": "10.1000/existing",
              "best_backend": "",
              "write_status": "preserved existing successful artifact"
            }
          ]
        }""",
        encoding="utf-8",
    )

    assert failed_dois_from_report(report) == [
        "10.1000/mismatch",
        "10.1000/parser-failure",
    ]


def test_final_failure_reconciliation_requires_verified_artifact(tmp_path) -> None:
    article_dir = tmp_path / "articles"
    article_dir.mkdir()
    (article_dir / "10_1000_verified.json").write_text(
        '{"best_backend":"grobid","source_identity":{"status":"verified_exact_doi"}}\n',
        encoding="utf-8",
    )
    (article_dir / "10_1000_mismatch.json").write_text(
        '{"best_backend":"grobid","source_identity":{"status":"identity_mismatch"}}\n',
        encoding="utf-8",
    )

    assert failed_dois_from_artifacts(
        ["10.1000/verified", "10.1000/mismatch", "10.1000/missing"],
        article_dir,
    ) == ["10.1000/mismatch", "10.1000/missing"]

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
    prescreen = tmp_path / "prescreen.parquet"
    pd.DataFrame(
        [{"doi": "10.1000/historical", "prescreen_decision": "retain"}]
    ).to_parquet(prescreen, index=False)
    args = SimpleNamespace(
        route_table=str(tmp_path / "unused_routes.parquet"),
        selection_table=str(selection),
        metadata_table=str(metadata),
        prescreen_table=str(prescreen),
        out_dir=str(tmp_path / "articles"),
        doi_file="",
        route_action="convert_local_pdf_then_extract",
        include_existing_artifacts=False,
        limit=0,
    )

    assert local_pdf_conversion_queue(args) == ["10.1000/historical"]


def test_managed_conversion_queue_rejects_stale_prescreen_exclusion(tmp_path) -> None:
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.7\n")
    selection = tmp_path / "stale_worklist.parquet"
    pd.DataFrame(
        [
            {
                "doi": "10.1000/excluded",
                "selected_for_downstream": True,
                "fulltext_enrichment_needed": True,
                "fulltext_enrichment_action": "convert_local_pdf",
                "local_pdf_paths": str(pdf),
            }
        ]
    ).to_parquet(selection, index=False)
    metadata = tmp_path / "metadata.parquet"
    pd.DataFrame([{"doi": "10.1000/excluded"}]).to_parquet(metadata, index=False)
    prescreen = tmp_path / "prescreen.parquet"
    pd.DataFrame(
        [{"doi": "10.1000/excluded", "prescreen_decision": "exclude"}]
    ).to_parquet(prescreen, index=False)
    args = SimpleNamespace(
        route_table=str(tmp_path / "unused_routes.parquet"),
        selection_table=str(selection),
        metadata_table=str(metadata),
        prescreen_table=str(prescreen),
        out_dir=str(tmp_path / "articles"),
        doi_file="",
        route_action="convert_local_pdf_then_extract",
        include_existing_artifacts=False,
        exclude_doi=[],
        limit=0,
    )

    with pytest.raises(ValueError, match="Rebuild the selection table"):
        local_pdf_conversion_queue(args)
