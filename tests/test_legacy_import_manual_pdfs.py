import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pipeline.ingest.import_manual_pdfs import verify_manual_pdf_identity


class LegacyImportManualPdfsTests(unittest.TestCase):
    def test_filename_hint_without_document_evidence_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "10.1234_example.pdf"
            path.write_bytes(b"%PDF-1.4\nunrelated document\n%%EOF\n")
            known = {
                "10.1234/example": {
                    "study_doi": "10.1234/example",
                    "study_title": "Expected article title about psilocybin outcomes",
                }
            }
            with (
                patch(
                    "pipeline.ingest.import_manual_pdfs.extract_pdf_text",
                    return_value="Unrelated document without expected identity evidence",
                ),
                patch(
                    "pipeline.ingest.import_manual_pdfs.extract_pdf_metadata_text",
                    return_value="",
                ),
            ):
                accepted, basis, _candidates = verify_manual_pdf_identity(
                    path,
                    "10.1234/example",
                    known,
                )

        self.assertFalse(accepted)
        self.assertEqual(basis, "filename_doi_unverified")

    def test_embedded_document_doi_accepts_expected_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "10.1234_example.pdf"
            path.write_bytes(b"%PDF-1.4\nexpected document\n%%EOF\n")
            known = {
                "10.1234/example": {
                    "study_doi": "10.1234/example",
                    "study_title": "Expected article title about psilocybin outcomes",
                }
            }
            with (
                patch(
                    "pipeline.ingest.import_manual_pdfs.extract_pdf_text",
                    return_value="DOI: 10.1234/example\nExpected article title about psilocybin outcomes",
                ),
                patch(
                    "pipeline.ingest.import_manual_pdfs.extract_pdf_metadata_text",
                    return_value="",
                ),
            ):
                accepted, basis, _candidates = verify_manual_pdf_identity(
                    path,
                    "10.1234/example",
                    known,
                )

        self.assertTrue(accepted)
        self.assertEqual(basis, "filename_doi+document_doi")

    def test_exact_curated_pdf_hash_accepts_without_text_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "10.1234_example.pdf"
            body = b"%PDF-1.4\ncurator reviewed multilingual article\n%%EOF\n"
            path.write_bytes(body)
            known = {
                "10.1234/example": {
                    "study_doi": "10.1234/example",
                    "study_title": "English metadata title not printed in the PDF",
                }
            }
            registry = {
                "records": {
                    "10.1234/example": {
                        "requested_doi": "10.1234/example",
                        "pdf_sha256": hashlib.sha256(body).hexdigest(),
                    }
                }
            }
            with (
                patch(
                    "pipeline.ingest.import_manual_pdfs.extract_pdf_text",
                    return_value="Japanese title text only",
                ),
                patch(
                    "pipeline.ingest.import_manual_pdfs.extract_pdf_metadata_text",
                    return_value="",
                ),
                patch(
                    "pipeline.fulltext.import_manual_pdfs.load_pdf_hash_attestation_registry",
                    return_value=registry,
                ),
            ):
                accepted, basis, _candidates = verify_manual_pdf_identity(
                    path,
                    "10.1234/example",
                    known,
                )

        self.assertTrue(accepted)
        self.assertEqual(basis, "curated_pdf_hash")


if __name__ == "__main__":
    unittest.main()
