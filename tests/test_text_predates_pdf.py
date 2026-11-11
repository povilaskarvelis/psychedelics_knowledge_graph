import json
import os

from pipeline.fulltext.convert_pdfs import pdf_sha256, text_predates_pdf


def test_text_from_a_replaced_pdf_is_out_of_date(tmp_path):
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.4 preprint")
    text = tmp_path / "paper.json"
    text.write_text(json.dumps({"pdf_local_path": str(pdf), "pdf_sha256": pdf_sha256(pdf)}))
    assert not text_predates_pdf(text, [str(pdf)])

    pdf.write_bytes(b"%PDF-1.4 published")
    assert text_predates_pdf(text, [str(pdf)])


def test_text_without_a_recorded_hash_is_compared_by_time(tmp_path):
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    text = tmp_path / "paper.json"
    text.write_text(json.dumps({"pdf_local_path": str(pdf)}))
    os.utime(pdf, (1_000, 1_000))
    os.utime(text, (2_000, 2_000))
    assert not text_predates_pdf(text, [str(pdf)])

    os.utime(pdf, (3_000, 3_000))
    assert text_predates_pdf(text, [str(pdf)])


def test_another_pdf_stored_for_the_paper_does_not_make_the_text_out_of_date(tmp_path):
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.4 article")
    text = tmp_path / "paper.json"
    text.write_text(json.dumps({"pdf_local_path": str(pdf)}))
    alternate = tmp_path / "paper__manual_alt.pdf"
    alternate.write_bytes(b"%PDF-1.4 alternate")
    os.utime(pdf, (1_000, 1_000))
    os.utime(text, (2_000, 2_000))
    os.utime(alternate, (3_000, 3_000))
    assert not text_predates_pdf(text, [str(pdf), str(alternate)])
    assert not text_predates_pdf(text, [str(alternate)])
