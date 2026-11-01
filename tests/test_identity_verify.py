import pytest

from pipeline.identity.evidence import (
    doi_kind,
    doi_variant_relation,
    document_kind,
    is_cover_sheet,
    is_not_a_title,
    is_web_page_text,
    numbers_differ,
    printed_dois,
    set_aside_reason,
    title_abstract_agreement,
    title_printed_in,
    title_state,
)
from pipeline.identity.model_reports import classify
from pipeline.identity.verify import Paper, Source, verify


PAPER = Paper("10.1000/abc.2020.15", "Psilocybin therapy for treatment-resistant depression: a randomized trial")


def test_titles_with_different_years_do_not_agree() -> None:
    state, similarity = title_state(
        "South Australian Drug Trends 2020: Key findings from the EDRS interviews",
        "South Australian Drug Trends 2025: Key findings from the EDRS interviews",
    )
    assert similarity >= 0.9
    assert state == "differs"


@pytest.mark.parametrize(
    ("paper_title", "source_title", "expected"),
    [
        ("LSD Revisited", "LSD revisited. A ten-year follow-up of medical LSD use.", "agrees"),
        ("Ketamine en la depresión resistente", "[Ketamine in resistant depression].", "unclear"),
        ("Ketamine for depression", "", "missing"),
        ("Ketamine for depression", "Wastewater surveillance of cocaine in European cities", "differs"),
    ],
)
def test_title_state(paper_title: str, source_title: str, expected: str) -> None:
    assert title_state(paper_title, source_title)[0] == expected


@pytest.mark.parametrize(
    ("doi", "kind"),
    [
        ("10.21676/issn.1657-4923", "issn"),
        ("10.21676/16574923.5351", "article"),
        ("10.15537/1658-3175.8312", "article"),
        ("10.13039/501100000780", "funder"),
        ("10.1017/dep.2025.10001.pr1", "component"),
        ("10.1371/journal.pone.0123456.s001", "component"),
        ("10.1101/2020.05.01.20087999", "preprint"),
        ("10.5281/zenodo.5772449", "repository"),
        ("10.1016/j.jad.2026.121662", "article"),
    ],
)
def test_doi_kind(doi: str, kind: str) -> None:
    assert doi_kind(doi) == kind


@pytest.mark.parametrize(
    ("found", "reason"),
    [
        ("10.1007/s00259", "truncated_paper_doi"),
        ("10.1000/abc.2020.15/full", "extended_paper_doi"),
        ("10.1000/abc.2020.15.s001", "component_of_paper"),
        ("10.1007/s10787-019-", "malformed"),
        ("10.13039/501100000780", "funder_doi"),
        ("10.2000/other.1", ""),
    ],
)
def test_set_aside_reason(found: str, reason: str) -> None:
    paper = "10.1007/s00259-006-0262-8" if reason == "truncated_paper_doi" else PAPER.doi
    assert set_aside_reason(found, paper) == reason


def test_identifier_and_title_verify_a_text() -> None:
    verdict = verify(PAPER, Source(titles=(PAPER.title,), own_dois=(PAPER.doi,)))
    assert (verdict.verdict, verdict.rule) == ("verified", "identifier_and_title")


def test_paper_doi_run_on_into_a_link_counts_as_the_identifier() -> None:
    verdict = verify(PAPER, Source(titles=(PAPER.title,), own_dois=(PAPER.doi + ".supp",)))
    assert verdict.verdict == "verified"


@pytest.mark.parametrize(
    ("source", "rule"),
    [
        (Source(titles=(PAPER.title,)), "title_only"),
        (Source(own_dois=(PAPER.doi,)), "identifier_only"),
        (Source(), "no_identity_evidence"),
    ],
)
def test_one_kind_of_evidence_leaves_the_text_unconfirmed(source: Source, rule: str) -> None:
    verdict = verify(PAPER, source)
    assert (verdict.verdict, verdict.rule) == ("unconfirmed", rule)


def test_paper_doi_on_a_text_with_another_title_is_a_conflict() -> None:
    verdict = verify(PAPER, Source(titles=("Cost of CAR-T therapy in multiple myeloma",), own_dois=(PAPER.doi,)))
    assert (verdict.verdict, verdict.rule) == ("conflict", "identifier_matches_title_differs")


def test_preprint_doi_with_the_paper_title_is_a_conflict_until_registered() -> None:
    preprint = "10.1101/2020.05.01.20087999"
    source = Source(titles=(PAPER.title,), own_dois=(preprint,))

    unregistered = verify(PAPER, source)
    assert (unregistered.verdict, unregistered.rule, unregistered.related_doi) == (
        "conflict",
        "title_matches_identifier_differs",
        preprint,
    )

    registered = verify(PAPER, source, {frozenset((PAPER.doi, preprint)): "preprint"})
    assert (registered.verdict, registered.relation, registered.related_doi) == ("version_of", "preprint", preprint)


def test_printed_paper_doi_confirms_the_paper_when_the_parser_found_no_other_doi() -> None:
    assert verify(PAPER, Source(titles=(PAPER.title,), printed_dois=(PAPER.doi,))).verdict == "verified"


def test_printed_paper_doi_does_not_override_another_parsed_doi() -> None:
    # A cited article's DOI read as the document's own, or a cover sheet that
    # prints the paper's DOI above another attached text.
    source = Source(titles=(PAPER.title,), own_dois=("10.2000/cited.article",), printed_dois=(PAPER.doi,))
    verdict = verify(PAPER, source)
    assert (verdict.verdict, verdict.rule, verdict.related_doi) == (
        "unconfirmed",
        "printed_doi_matches_parsed_doi_differs",
        "10.2000/cited.article",
    )


def test_page_printing_other_items_is_not_verified_by_the_printed_title_alone() -> None:
    source = Source(
        titles=("Dexamethasone for depression: the DEXA-PSYCH protocol",),
        own_dois=(PAPER.doi,),
        printed_dois=(PAPER.doi, "10.1000/abc.2020.13"),
        opening_text=f"Dexamethasone for depression: the DEXA-PSYCH protocol\n...\n{PAPER.title}",
    )
    assert verify(PAPER, source).rule == "identifier_only"
    untitled = Source(own_dois=(PAPER.doi,), printed_dois=(PAPER.doi, "10.1000/abc.2020.13"), opening_text=PAPER.title)
    assert verify(PAPER, untitled).rule == "possible_multi_item_page"


def test_preprint_header_doi_outweighs_a_printed_paper_doi() -> None:
    source = Source(titles=(PAPER.title,), own_dois=("10.1101/2020.05.01.20087999",), printed_dois=(PAPER.doi,))
    assert verify(PAPER, source).rule == "title_matches_identifier_differs"


def test_other_doi_and_other_title_name_another_work() -> None:
    source = Source(titles=("Integrative oncology for breast cancer survivors",), own_dois=("10.2000/other.1",))
    verdict = verify(PAPER, source)
    assert (verdict.verdict, verdict.rule) == ("conflict", "identifier_and_title_differ")


def test_supplement_and_non_work_dois_are_wrong_kind() -> None:
    supplement = Source(titles=(PAPER.title,), own_dois=(PAPER.doi,), document_kind="supplement")
    assert verify(PAPER, supplement).rule == "document_is_supplement"
    funder = Paper("10.13039/501100000780", "Ketamine and esketamine in depression")
    assert verify(funder, Source(titles=(funder.title,))).rule == "paper_doi_is_funder"


@pytest.mark.parametrize(
    "heading",
    [
        "INTERNATIONAL JOURNAL OF PHARMACEUTICAL SCIENCES",
        "King's Research Portal",
        "You are prohibited from making this PDF publicly available",
        "u n i v e r s i t y o f c o p e n h a g e n",
        "Abbreviations 5-HT 5-hydroxytryptamine ACh acetylcholine",
        "ORCID iDs",
        "78.e1",
        "Themed Section: Opioids: New Pathways to Functional Selectivity",
    ],
)
def test_heading_that_is_not_a_title_is_ignored_when_the_paper_title_is_printed(heading: str) -> None:
    source = Source(
        titles=(heading,),
        own_dois=(PAPER.doi,),
        opening_text=f"{heading}\n{PAPER.title}\nA. Author, B. Author",
    )
    verdict = verify(PAPER, source)
    assert verdict.verdict == "verified"
    assert verdict.evidence["ignored_titles"] == [heading]


def test_heading_that_agrees_with_the_paper_title_is_kept() -> None:
    upper = PAPER.title.upper()
    verdict = verify(PAPER, Source(titles=(upper,), own_dois=(PAPER.doi,)))
    assert verdict.verdict == "verified"
    assert verdict.evidence["ignored_titles"] == []


def test_printed_title_under_another_heading_stays_unconfirmed() -> None:
    source = Source(
        titles=("Gut microbiota and mood in older adults",),
        own_dois=(PAPER.doi,),
        opening_text=f"Gut microbiota and mood in older adults\n...\n{PAPER.title}",
    )
    assert verify(PAPER, source).rule == "identifier_only"


def test_evidence_helpers() -> None:
    assert is_not_a_title("Addictive Behaviors Reports", journal="Addictive behaviors reports")
    assert not is_not_a_title(PAPER.title)
    assert printed_dois("https://doi.org/10.1248/bpb.32.\n1576 Received") == {"10.1248/bpb.32.1576"}
    assert is_cover_sheet("Citation for published version (APA): ... General rights ... Take down policy")
    assert not numbers_differ("[H215O]-PET in healthy humans", "[H(2)(15)O]-PET in healthy humans")
    assert is_web_page_text("Our website uses cookies to enhance your experience. Log in or register to read more.")
    assert not is_web_page_text("Ketamine reduced depressive symptoms in adults.")
    assert not is_cover_sheet(PAPER.title)
    assert title_printed_in("Drug Trends 2020 key findings", "South Australian Drug Trends 2020: Key findings")
    assert not title_printed_in("Drug Trends 2020 key findings", "South Australian Drug Trends 2025: Key findings")
    assert document_kind("Supplementary Information", "", PAPER.title) == "supplement"
    assert document_kind("Correction: " + PAPER.title, "", PAPER.title) == "correction"
    assert document_kind(PAPER.title, "Li and Sun et al.\fSupplementary Figure 1. Genome size by flow cytometry", PAPER.title) == "supplement"
    assert document_kind(PAPER.title, "Mood improved (Supplementary Fig. 1). Effects lasted.", PAPER.title) == "article"
    assert title_abstract_agreement(
        "Psilocybin and depression",
        "Psilocybin reduced depression scores in adults with major depressive disorder.",
    ) == 1.0
    assert doi_variant_relation("10.5281/zenodo.19127718", "10.5281/zenodo.19127719") == "version_doi"
    assert doi_variant_relation("10.1590/abc-pt", "10.1590/abc-en") == "translation"


def test_model_statement_that_text_and_title_differ() -> None:
    assert "D" in classify("The title and 1917 publication metadata appear inconsistent with the modern ketamine abstract.")
    assert "D" not in classify("Effect sizes were not reported, and the sample was small.")
