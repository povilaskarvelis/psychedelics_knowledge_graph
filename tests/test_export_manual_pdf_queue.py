from pathlib import Path
import tempfile

import pandas as pd

from pipeline.fulltext.export_manual_pdf_queue import export_manual_pdf_queue
from pipeline.ingest.sync_paper_library import pdf_filename_for_doi


def test_export_manual_pdf_queue_deduplicates_routed_download_dois() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        route_table = root / "routes.parquet"
        metadata_table = root / "metadata.parquet"
        candidate_table = root / "candidate_papers.parquet"
        pdf_dir = root / "pdfs"
        output_csv = root / "manual.csv"
        output_txt = root / "manual.txt"

        pd.DataFrame(
            [
                {
                    "doi": "10.1000/example",
                    "retained_for_extraction_candidate": True,
                    "route_action": "download_pdf_then_extract",
                    "study_title": "Route title",
                    "domain_route": "clinical_outcome",
                    "prompt_profile": "primary_clinical",
                    "source_type": "primary_or_unclear",
                    "best_pdf_url": "https://example.org/paper.pdf",
                },
                {
                    "doi": "10.1000/example",
                    "retained_for_extraction_candidate": True,
                    "route_action": "download_pdf_then_extract",
                    "domain_route": "safety_tolerability",
                    "prompt_profile": "primary_safety",
                    "source_type": "primary_or_unclear",
                    "pdf_url_candidates": "https://example.org/paper.pdf | https://repo.example/paper.pdf",
                },
                {
                    "doi": "10.1000/abstract",
                    "retained_for_extraction_candidate": True,
                    "route_action": "extract_from_abstract_only",
                },
            ]
        ).to_parquet(route_table, engine="pyarrow", index=False)
        pd.DataFrame(
            [
                {
                    "doi": "10.1000/example",
                    "study_journal": "Journal",
                    "pmid": "123",
                    "open_access_url": "https://example.org/landing",
                }
            ]
        ).to_parquet(metadata_table, engine="pyarrow", index=False)
        pd.DataFrame(
            [
                {
                    "doi": "10.1000/example",
                    "pdf_download_status": "download_failed",
                    "pdf_download_failure_category": "forbidden",
                    "pdf_download_retry_recommended": False,
                    "pdf_download_error": "HTTP Error 403",
                    "open_access_status": "bronze",
                }
            ]
        ).to_parquet(candidate_table, engine="pyarrow", index=False)

        summary = export_manual_pdf_queue(
            route_table=route_table,
            metadata_table=metadata_table,
            candidate_table=candidate_table,
            pdf_dir=pdf_dir,
            output_csv=output_csv,
            output_txt=output_txt,
        )

        exported = pd.read_csv(output_csv)
        exported_txt = output_txt.read_text(encoding="utf-8")

        assert summary["rows"] == 1
        assert exported.loc[0, "doi"] == "10.1000/example"
        assert exported.loc[0, "suggested_pdf_filename"] == pdf_filename_for_doi("10.1000/example")
        assert exported.loc[0, "route_count"] == 2
        assert exported.loc[0, "domain_routes"] == "clinical_outcome|safety_tolerability"
        assert exported_txt == "10.1000/example\n"
