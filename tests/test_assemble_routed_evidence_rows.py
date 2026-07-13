import pytest

from pipeline.kg.assemble_routed_evidence_rows import assemble_rows


def row(doi: str, source_type: str, item: int = 1) -> dict:
    return {
        "study_doi": doi,
        "source_type": source_type,
        "task_id": f"{source_type}:{doi}",
        "source_item_type": "synthesis_result" if source_type == "meta_analysis" else "primary_item",
        "source_item_index": item,
    }


def test_assembly_overlays_only_selected_primary_papers_and_replaces_meta_layer():
    base = [
        row("10.1/keep", "primary"),
        row("10.1/retry", "primary"),
        row("10.1/review", "systematic_review"),
        row("10.1/old-meta", "meta_analysis"),
    ]
    retry_file = [
        row("10.1/unselected", "primary"),
        row("10.1/retry", "primary", 2),
        row("10.1/retry", "primary", 3),
    ]
    meta = [row("10.1/new-meta", "meta_analysis")]

    combined, report = assemble_rows(base, retry_file, {"10.1/retry"}, meta)

    assert [item["study_doi"] for item in combined] == [
        "10.1/keep",
        "10.1/review",
        "10.1/retry",
        "10.1/retry",
        "10.1/new-meta",
    ]
    assert report["counts"]["primary_retry_rows_removed"] == 1
    assert report["counts"]["primary_retry_rows_added"] == 2
    assert report["counts"]["meta_analysis_rows_removed"] == 1


def test_assembly_fails_when_selected_retry_doi_has_no_rows():
    with pytest.raises(ValueError, match="No primary retry rows found"):
        assemble_rows([], [], {"10.1/missing"}, [])


def test_assembly_rejects_non_meta_rows_in_meta_input():
    with pytest.raises(ValueError, match="non-meta-analysis"):
        assemble_rows([], [], set(), [row("10.1/not-meta", "primary")])


def test_assembly_can_replace_complete_primary_layer_without_touching_reviews():
    base = [
        row("10.1/old-primary", "primary"),
        row("10.1/review", "systematic_review"),
        row("10.1/old-meta", "meta_analysis"),
    ]
    complete_primary = [
        row("10.1/new-primary", "primary"),
        row("10.1/new-primary-2", "primary"),
        row("10.1/legacy-review", "review"),
    ]
    meta = [row("10.1/new-meta", "meta_analysis")]

    combined, report = assemble_rows(
        base,
        complete_primary,
        {"10.1/new-primary"},
        meta,
        replace_primary_layer=True,
    )

    assert [item["study_doi"] for item in combined] == [
        "10.1/review",
        "10.1/new-primary",
        "10.1/new-primary-2",
        "10.1/new-meta",
    ]
    assert report["primary_replacement_mode"] == "complete_layer"
    assert report["counts"]["primary_retry_rows_removed"] == 1
    assert report["counts"]["primary_retry_rows_added"] == 2


def test_assembly_replaces_legacy_doi_aliases_with_one_selected_retry_paper():
    base = [
        row("10.1/paper", "primary"),
        row("10.1/paper_alias", "primary", 2),
        row("10.1/keep", "primary"),
    ]
    retry_file = [row("10.1/paper", "primary", 3)]

    combined, report = assemble_rows(
        base,
        retry_file,
        {"10.1/paper"},
        [],
        doi_aliases={"10.1/paper_alias": "10.1/paper"},
    )

    assert [item["study_doi"] for item in combined] == ["10.1/keep", "10.1/paper"]
    assert report["counts"]["primary_retry_rows_removed"] == 2
    assert report["counts"]["primary_retry_rows_added"] == 1
