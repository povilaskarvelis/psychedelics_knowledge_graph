import pytest

from pipeline.kg.combine_meta_analysis_v2_evidence_rows import combine_rows


def row(doi: str, result_id: str, value: str) -> dict:
    return {
        "study_doi": doi,
        "source_item_id": result_id,
        "estimate_value": value,
    }


def test_combines_disjoint_sources_and_applies_paper_override() -> None:
    combined, report = combine_rows(
        [
            ("pilot-default", [row("10.1/a", "R1", "default")]),
            ("remaining", [row("10.1/b", "R1", "remaining")]),
        ],
        [
            (
                "10.1/a",
                "pilot-source-checked",
                [row("10.1/a", "R1", "checked"), row("10.1/a", "R2", "checked")],
                "Source-checked fallback.",
            )
        ],
    )

    assert [(item["study_doi"], item["source_item_id"]) for item in combined] == [
        ("10.1/a", "R1"),
        ("10.1/a", "R2"),
        ("10.1/b", "R1"),
    ]
    assert combined[0]["estimate_value"] == "checked"
    assert report["counts"] == {"rows": 3, "papers": 2, "paper_overrides": 1}


def test_rejects_silent_overlap_between_base_sources() -> None:
    with pytest.raises(ValueError, match="Base sources overlap"):
        combine_rows(
            [
                ("first", [row("10.1/a", "R1", "one")]),
                ("second", [row("10.1/a", "R1", "two")]),
            ],
            [],
        )
