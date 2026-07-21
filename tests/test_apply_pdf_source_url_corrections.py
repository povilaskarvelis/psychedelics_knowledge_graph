import pandas as pd

from pipeline.fulltext.apply_pdf_source_url_corrections import apply_corrections


def test_rejects_wrong_pdf_url_without_excluding_or_suppressing_doi() -> None:
    wrong = "https://repo.example/viewcontent?article=11"
    correct = "https://repo.example/viewcontent?article=12"
    candidate = pd.DataFrame(
        [
            {
                "doi": "10.example/article",
                "best_pdf_url": wrong,
                "open_access_url": wrong,
                "pdf_url_candidates": f"{wrong} | https://doi.org/10.example/article",
                "retained_for_extraction_candidate": True,
            }
        ]
    )

    updated, report = apply_corrections(
        candidate,
        [
            {
                "doi": "10.example/article",
                "rejected_url": wrong,
                "replacement_pdf_url": correct,
                "replacement_landing_url": "https://repo.example/article/12",
                "evidence": "Retrieved PDF carried a different DOI.",
            }
        ],
    )

    row = updated.iloc[0]
    assert row["best_pdf_url"] == correct
    assert wrong not in row["pdf_url_candidates"]
    assert row["pdf_download_failure_category"] == "source_identity_mismatch"
    assert bool(row["pdf_download_retry_recommended"]) is True
    assert bool(row["retained_for_extraction_candidate"]) is True
    assert report["changed_candidate_rows"] == 1
