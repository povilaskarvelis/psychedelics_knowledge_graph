import json
from types import SimpleNamespace

import pandas as pd
import pytest

from pipeline.fulltext.run_local_pdf_conversion_pipeline import (
    failed_dois_from_artifacts,
    failed_dois_from_report,
    local_pdf_conversion_queue,
)
from pipeline.identity.bindings import verdict_table
from pipeline.identity.intake import KEPT_USABLE_TEXT, NO_EXTRACTION, STORED_FOR_REVIEW, STORED_VERIFIED


def test_a_converted_text_is_a_failure_only_when_it_was_not_converted(tmp_path) -> None:
    report = tmp_path / "conversion.json"
    report.write_text(json.dumps({"records": [
        {"study_doi": "10.1000/verified", "write_status": STORED_VERIFIED},
        # Stored for review: converting it again would give the same text.
        {"study_doi": "10.1000/mismatch", "write_status": STORED_FOR_REVIEW},
        {"study_doi": "10.1000/kept", "write_status": KEPT_USABLE_TEXT},
        {"study_doi": "10.1000/parser-failure", "write_status": NO_EXTRACTION},
    ]}), encoding="utf-8")

    assert failed_dois_from_report(report) == ["10.1000/parser-failure"]


def test_final_reconciliation_reads_the_verdict_table(tmp_path) -> None:
    article_dir = tmp_path / "articles"
    article_dir.mkdir()
    for slug in ("10_1000_verified", "10_1000_mismatch"):
        (article_dir / f"{slug}.json").write_text('{"best_backend":"grobid"}\n', encoding="utf-8")
    table = tmp_path / "verdicts.parquet"
    verdict_table([
        {"doi": doi, "target_kind": "fulltext", "artifact": f"{doi.replace('.', '_').replace('/', '_')}.json",
         "verdict": verdict, "usable": usable}
        for doi, verdict, usable in (("10.1000/verified", "verified", True), ("10.1000/mismatch", "conflict", False))
    ]).to_parquet(table, index=False)

    assert failed_dois_from_artifacts(
        ["10.1000/verified", "10.1000/mismatch", "10.1000/missing"], article_dir, table
    ) == (["10.1000/missing"], ["10.1000/mismatch"])

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
