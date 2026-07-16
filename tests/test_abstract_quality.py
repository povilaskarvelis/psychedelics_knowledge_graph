from pipeline.ingest.abstract_quality import assess_abstract, best_valid_abstract, extract_embedded_abstract


def test_openalex_overlong_text_is_contaminated() -> None:
    quality = assess_abstract("A plausible beginning. " + ("continued article text " * 300), provider="openalex")

    assert quality.status == "contaminated"
    assert "overlong_low_trust_provider_field" in quality.reasons


def test_long_pubmed_structured_abstract_is_not_rejected_for_length_alone() -> None:
    quality = assess_abstract(
        "BACKGROUND " + ("long structured abstract result " * 230),
        provider="pubmed",
    )

    assert quality.status == "valid"


def test_navigation_text_is_contaminated_at_shorter_length() -> None:
    quality = assess_abstract(
        "Back to table of contents Previous article Next article Abstract Useful text.",
        provider="candidate",
    )

    assert quality.status == "contaminated"
    assert "publisher_page_or_fulltext_navigation" in quality.reasons


def test_best_valid_abstract_uses_provider_priority_not_length() -> None:
    selected = best_valid_abstract(
        [
            {"provider": "semantic_scholar", "abstract": "Longer alternative abstract text."},
            {"provider": "pubmed", "abstract": "PubMed abstract."},
        ]
    )

    assert selected is not None
    assert selected["provider"] == "pubmed"


def test_extracts_explicit_abstract_from_publisher_fulltext() -> None:
    source = (
        "Full text Figures and data Side by side Abstract "
        + ("This sentence reports a substantive study result. " * 12)
        + " Introduction The article body continues here. "
        + ("Body text. " * 500)
    )

    extracted = extract_embedded_abstract(source)

    assert extracted is not None
    assert extracted.method == "explicit_abstract_section"
    assert "article body" not in extracted.text.lower()


def test_extracts_article_leading_summary_before_introduction() -> None:
    source = ("This summary reports methods, findings, and conclusions. " * 12) + " Introduction " + ("Body. " * 500)

    extracted = extract_embedded_abstract(source)

    assert extracted is not None
    assert extracted.method == "leading_summary_before_introduction"


def test_does_not_treat_arbitrary_first_five_thousand_characters_as_abstract() -> None:
    source = ("Article prose without an abstract boundary. " * 400) + " Introduction Too late."

    assert extract_embedded_abstract(source) is None


def test_does_not_extract_publisher_notes_before_introduction() -> None:
    source = "Click to increase image size Notes 1. Citation discussion. " + ("More notes. " * 80) + " Introduction"

    assert extract_embedded_abstract(source) is None


def test_does_not_extract_false_no_abstract_marker() -> None:
    source = "This Article does not have an abstract. Notes 1. " + ("Citation note. " * 80) + " Introduction"

    assert extract_embedded_abstract(source) is None
