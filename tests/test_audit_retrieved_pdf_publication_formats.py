from pathlib import Path
from unittest.mock import patch

from pipeline.fulltext.audit_retrieved_pdf_publication_formats import audit_file


def test_short_case_report_with_cited_dois_is_not_a_conference_abstract() -> None:
    text = """case report
Case report of S-ketamine for treatment-resistant depression
Summary
We present the case of one adolescent patient.
References
https://doi.org/10.1001/example.1
https://doi.org/10.1001/example.2
"""

    with patch(
        "pipeline.fulltext.audit_retrieved_pdf_publication_formats.extract_front_text",
        return_value=(3, text, " ".join(text.split())),
    ):
        result = audit_file(
            Path("case-report.pdf"),
            identity={"identity_status": "matched", "doi": "10.1007/case-report"},
            browser_doi="10.1007/case-report",
            metadata={"language": "en", "study_title": "Case report of S-ketamine"},
        )

    assert result["recommended_action"] == "import_validated_article_pdf"
    assert result["publication_format"] == "eligible_article_or_review"
    assert "short_multiple_dois" in result["format_evidence"]


def test_explicit_meeting_abstract_remains_excluded() -> None:
    text = """Meeting Abstract
Annual Meeting poster session
Multimodal synaptomics for mapping synaptic regulation
https://doi.org/10.1001/example.1
https://doi.org/10.1001/example.2
"""

    with patch(
        "pipeline.fulltext.audit_retrieved_pdf_publication_formats.extract_front_text",
        return_value=(2, text, " ".join(text.split())),
    ):
        result = audit_file(
            Path("meeting-abstract.pdf"),
            identity={"identity_status": "matched", "doi": "10.1007/abstract"},
            browser_doi="10.1007/abstract",
            metadata={"language": "en", "study_title": "Multimodal synaptomics"},
        )

    assert result["recommended_action"] == "exclude_publication_format"
    assert result["publication_format"] == "conference_abstract"


def test_wrong_thesis_or_meeting_file_never_excludes_the_intended_article() -> None:
    for text in ["A thesis submitted in partial fulfilment of the requirements for the degree of PhD",
                 "Meeting Abstract\nAnnual Meeting poster session"]:
        with patch("pipeline.fulltext.audit_retrieved_pdf_publication_formats.extract_front_text",
                   return_value=(2, text, text)):
            result = audit_file(Path("wrong-source.pdf"), identity={"identity_status": "needs_review"},
                                browser_doi="10.example/intended-article", metadata={"language": "en"})
        assert result["recommended_action"] == "quarantine_identity_review"


def test_mixed_english_language_codes_are_not_foreign_language_exclusions() -> None:
    text = "Original research article with methods, results and discussion."
    with patch("pipeline.fulltext.audit_retrieved_pdf_publication_formats.extract_front_text",
               return_value=(8, text, text)):
        result = audit_file(Path("english-version.pdf"), identity={"identity_status": "matched"},
                            browser_doi="10.example/paper", metadata={"language": "eng | fre"})
    assert result["recommended_action"] == "import_validated_article_pdf"


def test_script_heuristic_is_review_only_but_explicit_language_can_exclude() -> None:
    text = "研究方法结果讨论" * 200
    for language, expected in [("", "review_publication_format"), ("zh", "exclude_publication_format")]:
        with patch("pipeline.fulltext.audit_retrieved_pdf_publication_formats.extract_front_text",
                   return_value=(8, text, text)):
            result = audit_file(Path("source.pdf"), identity={"identity_status": "matched"},
                                browser_doi="10.example/paper", metadata={"language": language})
        assert result["recommended_action"] == expected
