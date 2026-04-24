import tempfile
import unittest
from pathlib import Path

from pipeline.fulltext.convert_pdfs import (
    backend_sequence,
    build_artifact,
    doi_to_slug,
    grobid_alive_url,
    iter_pdf_rows,
    multipart_body,
    should_write_artifact,
    stale_fulltext_locator_dois,
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

    def test_auto_backend_prefers_grobid_with_docling_fallback(self) -> None:
        self.assertEqual(backend_sequence("auto"), ["grobid", "docling", "pdftotext"])
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

    def test_iter_pdf_rows_skips_missing_and_existing_artifacts_when_requested(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            pdf = root / "paper.pdf"
            pdf.write_bytes(b"%PDF-1.4")
            out_dir = root / "out"
            out_dir.mkdir()
            existing = out_dir / "10_1000_existing.json"
            existing.write_text("{}\n", encoding="utf-8")
            rows = [
                {"study_doi": "10.1000/existing", "pdf_local_path": str(pdf)},
                {"study_doi": "10.1000/new", "pdf_local_path": str(pdf)},
                {"study_doi": "10.1000/missing", "pdf_local_path": str(root / "missing.pdf")},
            ]

            found = list(iter_pdf_rows(rows, only_missing_artifacts=True, out_dir=out_dir))

        self.assertEqual(len(found), 1)
        self.assertEqual(found[0][0]["study_doi"], "10.1000/new")

    def test_iter_pdf_rows_can_filter_to_target_dois(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            pdf = root / "paper.pdf"
            pdf.write_bytes(b"%PDF-1.4")
            rows = [
                {"study_doi": "10.1000/keep", "pdf_local_path": str(pdf)},
                {"study_doi": "10.1000/skip", "pdf_local_path": str(pdf)},
            ]

            found = list(
                iter_pdf_rows(
                    rows,
                    only_missing_artifacts=False,
                    out_dir=root / "out",
                    doi_filter={"10.1000/keep"},
                )
            )

        self.assertEqual(len(found), 1)
        self.assertEqual(found[0][0]["study_doi"], "10.1000/keep")

    def test_stale_fulltext_locator_dois_selects_only_fulltext_abstract_snippets(self) -> None:
        dois = stale_fulltext_locator_dois(
            [
                {
                    "study_doi": "10.1000/stale",
                    "access_level": "full_text_seen",
                    "evidence_locator": "Abstract snippet: result",
                },
                {
                    "study_doi": "10.1000/abstract-only",
                    "access_level": "abstract_only",
                    "evidence_locator": "Abstract snippet: result",
                },
                {
                    "study_doi": "10.1000/section",
                    "access_level": "full_text_seen",
                    "evidence_locator": "Results section",
                },
            ]
        )

        self.assertEqual(dois, {"10.1000/stale"})

    def test_build_artifact_records_best_backend(self) -> None:
        artifact = build_artifact(
            "disorder",
            {"study_doi": "10.1000/test", "study_title": "Example"},
            Path("/tmp/example.pdf"),
            [{"backend": "docling", "status": "ok", "section_count": 2, "char_count": 120, "sections": []}],
        )

        self.assertEqual(artifact["best_backend"], "docling")
        self.assertEqual(artifact["best_char_count"], 120)

    def test_failed_artifact_does_not_overwrite_successful_existing_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "artifact.json"
            path.write_text('{"best_backend": "docling"}\n', encoding="utf-8")

            write, reason = should_write_artifact(path, {"best_backend": ""}, write_failed_artifacts=False)

        self.assertFalse(write)
        self.assertIn("preserved existing successful", reason)

    def test_successful_artifact_is_written(self) -> None:
        write, reason = should_write_artifact(Path("/tmp/missing-artifact.json"), {"best_backend": "grobid"}, False)

        self.assertTrue(write)
        self.assertIn("successful", reason)


if __name__ == "__main__":
    unittest.main()
