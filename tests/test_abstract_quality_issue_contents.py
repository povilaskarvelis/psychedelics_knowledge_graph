from pipeline.ingest.abstract_quality import contamination_reasons


def test_bmj_pointers_contents_block_is_not_an_article_abstract() -> None:
    text = (
        "Pointers Sodium Reabsorption: Lecture summary (p.611). "
        "Juvenile Diabetes: Diet comparison (p.616). "
        "Psychotropic Drugs and Chromosomes: Patients received lysergide (p.634)."
    )

    assert "journal_issue_contents_not_article_abstract" in contamination_reasons(
        text, provider="openalex", title="Holiday typhoid"
    )
