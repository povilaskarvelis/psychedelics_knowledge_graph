from pathlib import Path

from pipeline.fulltext.browser_download_triage import (
    COOKIE_STATUS,
    HTML_STATUS,
    NO_ACCESS_STATUS,
    PDF_STATUS,
    classify_download_artifact,
    classify_html_text,
    triage_download_dir,
)


def test_classify_download_artifact_accepts_pdf_magic_header(tmp_path: Path) -> None:
    path = tmp_path / "paper.pdf"
    path.write_bytes(b"%PDF-1.7\n1 0 obj\n")

    record = classify_download_artifact(path)

    assert record["status"] == PDF_STATUS
    assert record["reason"] == "pdf_magic_header"


def test_classify_html_text_marks_no_access_pages() -> None:
    status, matches = classify_html_text(
        """
        <html><body>
        Unfortunately you do not have access to this content, please use the
        Get access link below.
        </body></html>
        """
    )

    assert status == NO_ACCESS_STATUS
    assert "you do not have access" in matches


def test_classify_html_text_marks_cookie_interstitials() -> None:
    status, matches = classify_html_text(
        """
        <html><body>
        We use cookies to enhance your browsing experience. Read our Cookie Policy.
        </body></html>
        """
    )

    assert status == COOKIE_STATUS
    assert "we use cookies" in matches


def test_classify_html_text_marks_generic_html_non_pdf() -> None:
    status, matches = classify_html_text("<html><body>Article landing page</body></html>")

    assert status == HTML_STATUS
    assert matches == []


def test_triage_download_dir_quarantines_non_pdf_and_leaves_pdf(tmp_path: Path) -> None:
    download_dir = tmp_path / "manual_pdf_inbox"
    quarantine_dir = tmp_path / "manual_pdf_rejected_downloads"
    download_dir.mkdir()
    pdf = download_dir / "article.pdf"
    html = download_dir / "Cambridge Core.html"
    companion = download_dir / "Cambridge Core_files"
    pdf.write_bytes(b"%PDF-1.4\n")
    html.write_text("Get access to this content through Institution Login.", encoding="utf-8")
    companion.mkdir()
    (companion / "style.css").write_text("body {}", encoding="utf-8")

    records = triage_download_dir(
        download_dir,
        quarantine_dir=quarantine_dir,
        apply=True,
        quarantine_non_pdf=True,
        max_text_bytes=20_000,
    )

    statuses = {record["filename"]: record["status"] for record in records}
    assert statuses == {
        "article.pdf": PDF_STATUS,
        "Cambridge Core.html": NO_ACCESS_STATUS,
    }
    assert pdf.exists()
    assert not html.exists()
    assert not companion.exists()
    assert (quarantine_dir / NO_ACCESS_STATUS / "Cambridge Core.html").exists()
    assert (quarantine_dir / NO_ACCESS_STATUS / "Cambridge Core_files" / "style.css").exists()


def test_triage_download_dir_quarantines_orphan_html_companion_dir(tmp_path: Path) -> None:
    download_dir = tmp_path / "manual_pdf_inbox"
    quarantine_dir = tmp_path / "manual_pdf_rejected_downloads"
    companion = download_dir / "Informatics Journals_files"
    companion.mkdir(parents=True)
    (companion / "index.css").write_text("body {}", encoding="utf-8")

    records = triage_download_dir(
        download_dir,
        quarantine_dir=quarantine_dir,
        apply=True,
        quarantine_non_pdf=True,
        max_text_bytes=20_000,
    )

    assert records[0]["status"] == HTML_STATUS
    assert records[0]["reason"] == "orphan_html_companion_dir"
    assert not companion.exists()
    assert (quarantine_dir / HTML_STATUS / "Informatics Journals_files" / "index.css").exists()
