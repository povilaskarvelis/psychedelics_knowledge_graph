import pandas as pd

from pipeline.fulltext.audit_deterministic_repository_formats import build_audit, current_retained_scope


def test_operational_scope_ignores_inactive_and_already_excluded_rows() -> None:
    candidate = pd.DataFrame(
        [
            {"doi": "10.example/active", "retained_for_extraction_candidate": True},
            {"doi": "10.example/inactive", "retained_for_extraction_candidate": False},
            {
                "doi": "10.example/already-excluded",
                "retained_for_extraction_candidate": True,
                "post_retrieval_decision": "exclude",
            },
        ]
    ).fillna("")

    assert list(current_retained_scope(candidate)["doi"]) == ["10.example/active"]


def test_high_precision_repository_and_identifier_rules() -> None:
    candidate = pd.DataFrame(
        [
            {
                "doi": "10.25772/example",
                "study_title": "A VCU dissertation",
                "study_journal": "VCU Scholars Compass",
                "publication_type": "article",
            },
            {
                "doi": "10.14288/example",
                "study_title": "A UBC dissertation",
                "study_journal": "cIRcle",
                "publication_type": "article",
                "best_pdf_url": "https://open.library.ubc.ca/media/download/pdf/831/example/1",
            },
            {
                "doi": "10.14288/1.0379503",
                "study_title": "A UBC thesis with incomplete route metadata",
                "study_journal": "cIRcle (University of British Columbia)",
                "publication_type": "article",
            },
            {
                "doi": "10.17632/data.1",
                "study_title": "Data for a study",
                "study_journal": "Mendeley Data",
                "publication_type": "other",
            },
            {
                "doi": "10.6027/book",
                "study_title": "A Nordic report",
                "study_journal": "TemaNord",
                "publication_type": "book",
            },
            {
                "doi": "10.1136/sextrans-2015-052270.508",
                "study_title": "P13.10 Club drug use",
                "study_journal": "Sexually Transmitted Infections",
                "publication_type": "article",
            },
            {
                "doi": "10.1136/ejhpharm-2023-eahp.154",
                "study_title": "4CPS-153 Off-label use of ketamine",
                "study_journal": "European Journal of Hospital Pharmacy",
                "publication_type": "article",
                "best_pdf_url": "https://ejhp.bmj.com/content/ejhpharm/30/Suppl_1/A73.1.full.pdf",
            },
            {
                "doi": "10.1093/clinchem/hvad097.333",
                "study_title": "A-377 The selection of toxicology testing",
                "study_journal": "Clinical Chemistry",
                "publication_type": "article",
                "best_pdf_url": "https://academic.oup.com/clinchem/article-pdf/69/Supplement_1/hvad097.333/abstract.pdf",
            },
            {
                "doi": "10.1016/j.jalz.2014.07.017",
                "study_title": "P4‐246: A conference poster abstract",
                "study_journal": "Alzheimer's & Dementia",
                "publication_type": "article",
            },
            {
                "doi": "10.26226/morressier.example",
                "study_title": "A deposited conference presentation",
                "study_journal": "Morressier",
                "publication_type": "article",
            },
            {
                "doi": "10.7205/milmed-d-13-00481",
                "study_title": "The intraoperative administration of ketamine to burned service members",
                "study_journal": "Military Medicine",
                "publication_type": "article",
                "best_pdf_url": "https://academic.oup.com/milmed/article-pdf/179/suppl_8/41/article.pdf",
            },
            {
                "doi": "10.14288/cjur.v6i2.194515",
                "study_title": "A genuine journal article",
                "study_journal": "Canadian Journal of Undergraduate Research",
                "publication_type": "article",
            },
            {
                "doi": "10.31235/osf.io/fv6wj_v1",
                "study_title": "An OSF preprint",
                "study_journal": "",
                "publication_type": "article",
            },
            {
                "doi": "10.1056/nejmc0804248",
                "study_title": "A case communicated by letter",
                "study_journal": "New England Journal of Medicine",
                "publication_type": "Case Reports | Letter",
            },
            {
                "doi": "10.example/poster",
                "study_title": "A repository poster",
                "study_journal": "Institutional Repository",
                "publication_type": "Poster",
            },
        ]
    )

    audit = build_audit(candidate.fillna(""))
    formats = dict(zip(audit["doi"], audit["publication_format"]))

    assert formats == {
        "10.25772/example": "dissertation_or_thesis",
        "10.14288/example": "dissertation_or_thesis",
        "10.14288/1.0379503": "dissertation_or_thesis",
        "10.17632/data.1": "dataset_or_data_deposit",
        "10.6027/book": "book_or_monograph",
        "10.1136/sextrans-2015-052270.508": "conference_abstract",
        "10.1136/ejhpharm-2023-eahp.154": "conference_abstract",
        "10.1093/clinchem/hvad097.333": "conference_abstract",
        "10.1016/j.jalz.2014.07.017": "conference_abstract",
        "10.26226/morressier.example": "conference_abstract",
        "10.31235/osf.io/fv6wj_v1": "preprint_or_unpublished",
        "10.1056/nejmc0804248": "correspondence_or_letter",
        "10.example/poster": "conference_poster",
    }
