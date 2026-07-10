import pytest

from pipeline.fulltext.classify_proceedings_search_records import classify_record, doi_pattern


@pytest.mark.parametrize(
    ("doi", "family"),
    [
        ("10.1192/j.eurpsy.2025.14", "cambridge_european_psychiatry_item"),
        ("10.1093/ijnp/pyae059.031", "oxford_ijnp_item"),
        ("10.1093/schbul/sby015.230", "oxford_schizophrenia_bulletin_item"),
        ("10.1093/sleep/32.11.1513", "oxford_sleep_item"),
        ("10.1017/cts.2024.274", "cambridge_cts_item"),
        ("10.1136/rapm-2023-esra.669", "bmj_esra_item"),
        ("10.1210/jendso/bvaf149.1527", "endocrine_society_item"),
        ("10.17579/abstractbookdualdisorders-p-278", "dual_disorders_abstract_item"),
        (
            "10.31986/issn.2689-0690_rdw.stratford_research_day.149_2024",
            "rowan_research_day_item",
        ),
        ("10.56126/75.s1.22", "acta_supplement_article"),
        ("10.1016/j.eurpsy.2016.01.2143", "elsevier_european_psychiatry_item"),
        ("10.1016/s0924-9338(09)70667-4", "elsevier_pii_item"),
    ],
)
def test_proceedings_doi_families_have_individual_item_locators(doi: str, family: str) -> None:
    assert doi_pattern(doi)[0] == family


def test_container_record_requires_positive_container_title_and_no_item_locator() -> None:
    source = {"doi": "10.1000/meeting", "requested_title": "Annual meeting proceedings"}
    candidate = {
        "doi": "10.1000/meeting",
        "study_title": "Annual meeting proceedings",
        "abstract": "",
        "publication_type": "proceedings",
    }

    result = classify_record(source, candidate, {})

    assert result["search_record_class"] == "B"
    assert result["remove_as_container"]


def test_item_record_is_retained_when_artifact_header_points_to_neighbor() -> None:
    source = {
        "doi": "10.1093/ijnp/pyae059.031",
        "requested_title": "Specific ketamine abstract",
        "identity_status": "identity_mismatch",
        "document_doi": "10.1093/ijnp/pyae059.030",
        "document_title": "Neighboring abstract",
        "target_title_exact_in_artifact": "true",
    }
    candidate = {
        "doi": source["doi"],
        "study_title": source["requested_title"],
        "abstract": "Methods and results for this individual scientific contribution.",
        "publication_type": "article",
    }

    result = classify_record(source, candidate, {})

    assert result["search_record_class"] == "A"
    assert not result["remove_as_container"]
    assert "whole-proceedings problem" in result["decision_reason"]
