import tempfile
import unittest
from pathlib import Path

from pipeline.fulltext.convert_pdfs import (
    backend_sequence,
    build_artifact,
    doi_to_slug,
    grobid_alive_url,
    multipart_body,
    pdf_filename_prefix_for_doi,
    should_write_artifact,
    sections_from_markdown,
    sections_from_tei,
    select_best_extraction,
)


class FulltextConversionTest(unittest.TestCase):
    def test_doi_to_slug_normalizes_url_prefix_and_punctuation(self) -> None:
        self.assertEqual(
            doi_to_slug("https://doi.org/10.1001/JAMA.2023.14530"),
            "10_1001_jama_2023_14530",
        )

    def test_pdf_filename_prefix_matches_downloaded_pdf_naming(self) -> None:
        self.assertEqual(
            pdf_filename_prefix_for_doi("10.1016/S0893-133X(98)00060-8"),
            "10.1016_s0893-133x_98_00060-8",
        )

    def test_sections_from_markdown_uses_headings(self) -> None:
        sections = sections_from_markdown("# Abstract\nA short abstract.\n\n## Results\nThe primary outcome improved.")

        self.assertEqual([section["heading"] for section in sections], ["Abstract", "Results"])
        self.assertGreater(sections[1]["char_count"], 10)

    def test_sections_from_tei_reads_abstract_and_body_divs(self) -> None:
        tei = """
        <TEI xmlns="http://www.tei-c.org/ns/1.0">
          <text>
            <front><abstract><p>Abstract text.</p></abstract></front>
            <body><div><head>Results</head><p>Result text here.</p></div></body>
          </text>
        </TEI>
        """

        sections = sections_from_tei(tei)

        self.assertEqual([section["heading"] for section in sections], ["Abstract", "Results"])

    def test_select_best_extraction_prefers_more_sections_then_chars(self) -> None:
        best = select_best_extraction(
            [
                {"backend": "docling", "status": "ok", "section_count": 1, "char_count": 1000},
                {"backend": "grobid", "status": "ok", "section_count": 3, "char_count": 600},
                {"backend": "pdftotext", "status": "failed", "section_count": 0, "char_count": 0},
            ]
        )

        self.assertEqual(best["backend"], "grobid")

    def test_auto_backend_uses_grobid_without_plain_text_fallback(self) -> None:
        self.assertEqual(backend_sequence("auto"), ["grobid"])
        self.assertEqual(backend_sequence("all"), ["grobid", "docling", "pdftotext"])

    def test_grobid_alive_url_uses_same_api_base(self) -> None:
        self.assertEqual(
            grobid_alive_url("http://localhost:8070/api/processFulltextDocument"),
            "http://localhost:8070/api/isalive",
        )

    def test_multipart_body_can_include_grobid_options(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            pdf = Path(tmpdir) / "paper.pdf"
            pdf.write_bytes(b"%PDF-1.4")

            body, boundary = multipart_body(
                pdf,
                filename="paper.pdf",
                fields={"consolidateHeader": "0", "consolidateCitations": "0"},
            )

        self.assertIn(boundary.encode("utf-8"), body)
        self.assertIn(b'name="input"; filename="paper.pdf"', body)
        self.assertIn(b'name="consolidateHeader"', body)
        self.assertIn(b"\r\n\r\n0\r\n", body)

    def test_build_artifact_records_best_backend(self) -> None:
        tei = """
        <TEI xmlns="http://www.tei-c.org/ns/1.0"><teiHeader><fileDesc>
          <titleStmt><title>Example</title></titleStmt>
          <sourceDesc><biblStruct><analytic><idno type="DOI">10.1000/test</idno></analytic></biblStruct></sourceDesc>
        </fileDesc></teiHeader><text><body><p>Result.</p></body></text></TEI>
        """
        artifact = build_artifact(
            "articles",
            {"study_doi": "10.1000/test", "study_title": "Example"},
            Path("/tmp/example.pdf"),
            [{
                "backend": "grobid",
                "status": "ok",
                "section_count": 2,
                "char_count": len(tei),
                "sections": [],
                "text": tei,
                "metadata": {"format": "tei_xml"},
            }],
        )

        self.assertEqual(artifact["best_backend"], "grobid")
        self.assertEqual(artifact["best_char_count"], len(tei))
        self.assertEqual(artifact["source_identity"]["status"], "verified_exact_doi")

    def test_failed_artifact_does_not_overwrite_successful_existing_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "artifact.json"
            path.write_text('{"best_backend": "docling"}\n', encoding="utf-8")

            write, reason = should_write_artifact(path, {"best_backend": ""}, write_failed_artifacts=False)

        self.assertFalse(write)
        self.assertIn("preserved existing successful", reason)

    def test_successful_artifact_is_written(self) -> None:
        write, reason = should_write_artifact(
            Path("/tmp/missing-artifact.json"),
            {"best_backend": "grobid", "source_identity": {"status": "verified_exact_doi"}},
            False,
        )

        self.assertTrue(write)
        self.assertIn("successful", reason)

    def test_successful_extraction_with_wrong_identity_is_not_written(self) -> None:
        write, reason = should_write_artifact(
            Path("/tmp/wrong-artifact.json"),
            {"best_backend": "grobid", "source_identity": {"status": "identity_mismatch"}},
            False,
        )

        self.assertFalse(write)
        self.assertIn("identity", reason)

if __name__ == "__main__":
    unittest.main()
