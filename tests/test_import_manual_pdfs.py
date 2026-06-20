import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from pipeline.ingest.sync_paper_library import pdf_filename_for_doi
from pipeline.fulltext.import_manual_pdfs import (
    build_pii_lookup,
    build_source_filename_lookup,
    extract_dois_from_text,
    extract_pii_candidates,
    import_manual_pdfs,
    parse_doi_from_filename,
    select_match,
    title_match_score,
)


class ImportManualPdfsTest(unittest.TestCase):
    def test_extract_dois_from_text_normalizes_common_forms(self) -> None:
        text = "Available at https://doi.org/10.1001/jama.2024.12345. Also DOI:10.1101/2024.05.12.593597"

        self.assertEqual(
            extract_dois_from_text(text),
            ["10.1001/jama.2024.12345", "10.1101/2024.05.12.593597"],
        )

    def test_parse_doi_from_filename_accepts_underscore_separator(self) -> None:
        path = Path("10.1001_jamapsychiatry.2019.1189.pdf")

        self.assertEqual(parse_doi_from_filename(path), ["10.1001/jamapsychiatry.2019.1189"])

    def test_parse_doi_from_filename_ignores_hash_suffix(self) -> None:
        path = Path("10.1001_jamapsychiatry.2019.1189__abc123def4.pdf")

        self.assertEqual(parse_doi_from_filename(path), ["10.1001/jamapsychiatry.2019.1189"])

    def test_select_match_uses_source_url_filename(self) -> None:
        known = {
            "10.1016/example": {
                "doi": "10.1016/example",
                "study_title": "Example title",
                "best_pdf_url": "https://www.nature.com/articles/1395607.pdf",
            }
        }

        doi, basis, candidates = select_match(
            file_path=Path("1395607.pdf"),
            known_records=known,
            text="",
            metadata_text="",
            enable_title_match=True,
            min_title_score=0.86,
            min_title_margin=0.12,
            source_filename_lookup=build_source_filename_lookup(known),
        )

        self.assertEqual(doi, "10.1016/example")
        self.assertEqual(basis, "source_url_filename")
        self.assertEqual(candidates, [])

    def test_select_match_uses_embedded_pii(self) -> None:
        known = {
            "10.1016/s0006-3223(99)00097-9": {
                "doi": "10.1016/s0006-3223(99)00097-9",
                "study_title": "Example title",
            }
        }

        doi, basis, candidates = select_match(
            file_path=Path("PIIS0006322399000979.pdf"),
            known_records=known,
            text="",
            metadata_text="PII: S0006-3223(99)00097-9",
            enable_title_match=True,
            min_title_score=0.86,
            min_title_margin=0.12,
            pii_lookup=build_pii_lookup(known),
        )

        self.assertEqual(doi, "10.1016/s0006-3223(99)00097-9")
        self.assertEqual(basis, "pii")
        self.assertEqual(candidates, [])

    def test_extract_pii_candidates_normalizes_compact_pii_filename(self) -> None:
        self.assertEqual(extract_pii_candidates("PIIS0006322399000979.pdf"), ["s0006322399000979"])

    def test_select_match_prefers_known_doi_in_text(self) -> None:
        known = {
            "10.1001/example": {"doi": "10.1001/example", "study_title": "Example title"},
            "10.1001/other": {"doi": "10.1001/other", "study_title": "Other title"},
        }

        doi, basis, candidates = select_match(
            file_path=Path("download.pdf"),
            known_records=known,
            text="This paper has DOI 10.1001/example in the first page.",
            metadata_text="",
            enable_title_match=True,
            min_title_score=0.86,
            min_title_margin=0.12,
        )

        self.assertEqual(doi, "10.1001/example")
        self.assertEqual(basis, "pdf_text_doi")
        self.assertEqual(candidates, [])

    def test_title_match_score_accepts_high_overlap_title(self) -> None:
        title = "Psilocybin-assisted therapy for treatment-resistant depression"
        text = "Psilocybin assisted therapy for treatment resistant depression was evaluated in this article."

        self.assertGreaterEqual(title_match_score(title, text), 0.86)

    def test_import_updates_candidate_pdf_status_for_manual_import(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            inbox = root / "manual_pdf_inbox"
            pdf_dir = root / "pdfs"
            candidate_table = root / "candidate_papers.parquet"
            report = root / "report.json"
            review = root / "review.csv"
            inbox.mkdir()

            doi = "10.1234/example"
            source_pdf = inbox / "10.1234_example.pdf"
            source_pdf.write_bytes(b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n")
            pd.DataFrame(
                [
                    {
                        "doi": doi,
                        "study_title": "Example manual PDF import",
                        "pdf_download_status": "download_failed",
                        "pdf_download_failure_category": "forbidden",
                        "pdf_download_failure_categories": "forbidden",
                        "pdf_download_error": "403",
                        "pdf_download_retry_recommended": True,
                        "pdf_local_path": "",
                        "local_pdf_paths": "",
                        "local_pdf_count": 0,
                        "pdf_sha256": "",
                        "flag_has_local_pdf": False,
                        "library_status": "",
                    }
                ]
            ).to_parquet(candidate_table, engine="pyarrow", index=False)

            result = import_manual_pdfs(
                inbox_dir=inbox,
                pdf_dir=pdf_dir,
                conflict_dir=root / "conflicts",
                invalid_dir=root / "invalid",
                manual_csv=root / "missing_manual_queue.csv",
                candidate_table=candidate_table,
                metadata_table=root / "missing_metadata.parquet",
                report_path=report,
                review_csv=review,
                apply=True,
                move=True,
            )

            canonical_pdf = pdf_dir / pdf_filename_for_doi(doi)
            updated = pd.read_parquet(candidate_table).iloc[0].to_dict()
            self.assertTrue(canonical_pdf.exists())
            self.assertEqual(result["counts"]["new_imports"], 1)
            self.assertEqual(result["counts"]["candidate_rows_updated"], 1)
            self.assertEqual(updated["pdf_download_status"], "manual_import")
            self.assertEqual(updated["pdf_local_path"], str(canonical_pdf.resolve()))
            self.assertEqual(updated["local_pdf_paths"], str(canonical_pdf.resolve()))
            self.assertEqual(updated["local_pdf_count"], 1)
            self.assertTrue(updated["flag_has_local_pdf"])
            self.assertEqual(updated["library_status"], "in_database")
            self.assertEqual(updated["pdf_download_error"], "")
            self.assertEqual(updated["pdf_download_failure_category"], "")
            self.assertEqual(updated["pdf_download_failure_categories"], "")
            self.assertFalse(updated["pdf_download_retry_recommended"])
            self.assertTrue(updated["pdf_sha256"])

    def test_import_can_replace_known_bad_canonical_pdf_with_backup(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            inbox = root / "manual_pdf_inbox"
            pdf_dir = root / "pdfs"
            conflict_dir = root / "conflicts"
            candidate_table = root / "candidate_papers.parquet"
            report = root / "report.json"
            review = root / "review.csv"
            inbox.mkdir()
            pdf_dir.mkdir()

            doi = "10.1234/example"
            canonical_pdf = pdf_dir / pdf_filename_for_doi(doi)
            canonical_pdf.write_bytes(b"%PDF-1.4\nold wrong pdf\n%%EOF\n")
            source_pdf = inbox / "10.1234_example.pdf"
            source_pdf.write_bytes(b"%PDF-1.4\ncorrect pdf\n%%EOF\n")
            pd.DataFrame(
                [
                    {
                        "doi": doi,
                        "study_title": "Example manual PDF import",
                        "pdf_download_status": "already_present",
                        "pdf_local_path": str(canonical_pdf),
                        "local_pdf_paths": str(canonical_pdf),
                        "local_pdf_count": 1,
                        "pdf_sha256": "",
                        "flag_has_local_pdf": True,
                        "library_status": "needs_download",
                    }
                ]
            ).to_parquet(candidate_table, engine="pyarrow", index=False)

            result = import_manual_pdfs(
                inbox_dir=inbox,
                pdf_dir=pdf_dir,
                conflict_dir=conflict_dir,
                invalid_dir=root / "invalid",
                manual_csv=root / "missing_manual_queue.csv",
                candidate_table=candidate_table,
                metadata_table=root / "missing_metadata.parquet",
                report_path=report,
                review_csv=review,
                apply=True,
                move=True,
                replace_existing=True,
            )

            updated = pd.read_parquet(candidate_table).iloc[0].to_dict()
            self.assertEqual(result["counts"]["replaced_existing"], 1)
            self.assertEqual(result["counts"]["conflicts"], 0)
            self.assertFalse(source_pdf.exists())
            self.assertEqual(canonical_pdf.read_bytes(), b"%PDF-1.4\ncorrect pdf\n%%EOF\n")
            self.assertEqual(len(list(conflict_dir.glob("*__replaced_prior_*.pdf"))), 1)
            self.assertEqual(updated["pdf_download_status"], "manual_import")
            self.assertEqual(updated["library_status"], "in_database")


if __name__ == "__main__":
    unittest.main()
