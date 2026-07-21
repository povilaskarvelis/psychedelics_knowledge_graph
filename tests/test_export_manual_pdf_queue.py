from pathlib import Path
import tempfile

import pandas as pd

from pipeline.fulltext.export_manual_pdf_queue import export_manual_pdf_queue
from pipeline.ingest.metadata_utils import pdf_filename_for_doi


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


def test_export_manual_pdf_queue_can_use_route_independent_worklist() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        selection_table = root / "worklist.parquet"
        metadata_table = root / "metadata.parquet"
        candidate_table = root / "candidate_papers.parquet"
        output_csv = root / "manual.csv"
        output_txt = root / "manual.txt"
        pd.DataFrame(
            [
                {
                    "doi": "10.1000/retry",
                    "selected_for_downstream": True,
                    "fulltext_enrichment_needed": True,
                    "fulltext_enrichment_action": "download_known_pdf",
                    "study_title": "Browser recovery target",
                    "best_pdf_url": "https://example.org/paper.pdf",
                },
                {
                    "doi": "10.1000/discover",
                    "selected_for_downstream": True,
                    "fulltext_enrichment_needed": True,
                    "fulltext_enrichment_action": "discover_fulltext",
                },
                {
                    "doi": "10.1000/oa-landing",
                    "selected_for_downstream": True,
                    "fulltext_enrichment_needed": True,
                    "fulltext_enrichment_action": "resolve_oa_landing_page",
                    "study_title": "OA landing target",
                },
            ]
        ).to_parquet(selection_table, engine="pyarrow", index=False)
        pd.DataFrame([{"doi": "10.1000/retry"}, {"doi": "10.1000/oa-landing"}]).to_parquet(
            metadata_table, engine="pyarrow", index=False
        )
        pd.DataFrame(
            [
                {
                    "doi": "10.1000/retry",
                    "pdf_download_status": "download_failed",
                    "pdf_download_failure_category": "other_download_failure",
                },
                {
                    "doi": "10.1000/oa-landing",
                    "pdf_download_status": "no_pdf_url",
                    "pdf_download_failure_category": "no_pdf_url",
                },
            ]
        ).to_parquet(candidate_table, engine="pyarrow", index=False)

        summary = export_manual_pdf_queue(
            selection_table=selection_table,
            metadata_table=metadata_table,
            candidate_table=candidate_table,
            pdf_dir=root / "pdfs",
            output_csv=output_csv,
            output_txt=output_txt,
        )

        exported = pd.read_csv(output_csv)
        assert summary["rows"] == 2
        assert summary["source_kind"] == "fulltext_enrichment_worklist"
        assert exported["doi"].tolist() == ["10.1000/oa-landing", "10.1000/retry"]


def test_export_manual_pdf_queue_omits_worklist_rows_with_a_local_pdf() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        selection_table = root / "worklist.parquet"
        metadata_table = root / "metadata.parquet"
        candidate_table = root / "candidate_papers.parquet"
        pdf_dir = root / "pdfs"
        pdf_dir.mkdir()
        doi = "10.1000/recovered"
        local_pdf = pdf_dir / pdf_filename_for_doi(doi)
        local_pdf.write_bytes(b"%PDF-1.4\n")
        pd.DataFrame(
            [
                {
                    "doi": doi,
                    "selected_for_downstream": True,
                    "fulltext_enrichment_needed": True,
                    "fulltext_enrichment_action": "download_known_pdf",
                }
            ]
        ).to_parquet(selection_table, engine="pyarrow", index=False)
        pd.DataFrame([{"doi": doi}]).to_parquet(metadata_table, engine="pyarrow", index=False)
        pd.DataFrame(
            [{"doi": doi, "pdf_download_status": "downloaded", "pdf_local_path": str(local_pdf)}]
        ).to_parquet(candidate_table, engine="pyarrow", index=False)

        summary = export_manual_pdf_queue(
            selection_table=selection_table,
            metadata_table=metadata_table,
            candidate_table=candidate_table,
            pdf_dir=pdf_dir,
            output_csv=root / "manual.csv",
            output_txt=root / "manual.txt",
        )

        assert summary["rows"] == 0


def test_export_manual_pdf_queue_applies_manual_progress_ledger() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        selection_table = root / "worklist.parquet"
        metadata_table = root / "metadata.parquet"
        candidate_table = root / "candidate_papers.parquet"
        progress_csv = root / "progress.csv"
        rows = []
        for doi in ("10.1000/closed", "10.1000/partial"):
            rows.append(
                {
                    "doi": doi,
                    "selected_for_downstream": True,
                    "fulltext_enrichment_needed": True,
                    "fulltext_enrichment_action": "resolve_oa_landing_page",
                }
            )
        pd.DataFrame(rows).to_parquet(selection_table, engine="pyarrow", index=False)
        pd.DataFrame([{"doi": row["doi"]} for row in rows]).to_parquet(
            metadata_table, engine="pyarrow", index=False
        )
        pd.DataFrame([{"doi": row["doi"]} for row in rows]).to_parquet(
            candidate_table, engine="pyarrow", index=False
        )
        pd.DataFrame(
            [
                {"doi": "10.1000/closed", "manual_status": "closed_access", "manual_notes": "Paywalled"},
                {
                    "doi": "10.1000/partial",
                    "manual_status": "partial_review_rate_limited",
                    "manual_notes": "Retry after cooldown",
                },
            ]
        ).to_csv(progress_csv, index=False)

        summary = export_manual_pdf_queue(
            selection_table=selection_table,
            metadata_table=metadata_table,
            candidate_table=candidate_table,
            pdf_dir=root / "pdfs",
            output_csv=root / "manual.csv",
            output_txt=root / "manual.txt",
            manual_progress_csv=progress_csv,
        )

        exported = pd.read_csv(root / "manual.csv").fillna("")
        assert summary["rows"] == 1
        assert summary["skipped_terminal_manual_status"] == 1
        assert exported.loc[0, "doi"] == "10.1000/partial"
        assert exported.loc[0, "manual_status"] == "partial_review_rate_limited"
        assert exported.loc[0, "manual_notes"] == "Retry after cooldown"
