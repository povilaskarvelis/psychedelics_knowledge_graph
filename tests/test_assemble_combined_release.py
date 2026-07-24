from __future__ import annotations

import json

import pandas as pd
import pytest

from pipeline.kg.assemble_combined_release import (
    apply_candidate_metadata,
    assemble_layers,
    candidate_metadata,
    explicit_metadata_clears,
    reject_non_v2_meta_analysis_evidence,
    remove_legacy_v1_secondary_outputs,
)


def evidence(doi: str, item: str, source_type: str = "primary") -> dict:
    return {
        "study_doi": doi,
        "task_id": f"task-{item}",
        "source_item_id": item,
        "source_item_type": "finding",
        "source_type": source_type,
    }


def test_overlay_replaces_whole_paper_and_filters_current_exclusions():
    rows, report = assemble_layers(
        [evidence("10.1/keep", "old"), evidence("10.1/drop", "stale")],
        [("update", [evidence("10.1/keep", "new")])],
        aliases={},
        eligible={"10.1/keep"},
    )

    assert [row["source_item_id"] for row in rows] == ["new"]
    assert report["base_rows_replaced"] == 1
    assert report["base_rows_removed_by_current_eligibility"] == 1


def test_declared_zero_row_outcome_replaces_old_paper_evidence():
    rows, report = assemble_layers(
        [evidence("10.1/no-result", "stale")],
        [("v2", [])],
        aliases={},
        eligible={"10.1/no-result"},
        replacement_dois_by_overlay={"v2": {"10.1/no-result"}},
    )

    assert rows == []
    assert report["base_rows_replaced"] == 1
    assert report["overlays"]["v2"]["replacement_papers_declared"] == 1
    assert report["overlays"]["v2"]["replacement_papers_without_rows"] == 1


def test_overlay_rows_must_be_in_declared_replacement_cohort():
    with pytest.raises(ValueError, match="absent from its replacement cohort"):
        assemble_layers(
            [],
            [("v2", [evidence("10.1/unexpected", "new")])],
            aliases={},
            eligible={"10.1/unexpected"},
            replacement_dois_by_overlay={"v2": {"10.1/expected"}},
        )


def test_alias_is_canonicalized_before_replacement_and_eligibility():
    rows, report = assemble_layers(
        [evidence("10.1/repository", "old")],
        [("update", [evidence("10.1/article", "new")])],
        aliases={"10.1/repository": "10.1/article"},
        eligible={"10.1/article"},
    )

    assert len(rows) == 1
    assert rows[0]["study_doi"] == "10.1/article"
    assert rows[0]["source_item_id"] == "new"
    assert report["base_doi_alias_rows_canonicalized"] == 1


def test_same_doi_in_two_overlays_fails_closed():
    with pytest.raises(ValueError, match="appears in both"):
        assemble_layers(
            [],
            [("primary", [evidence("10.1/a", "1")]), ("review", [evidence("10.1/a", "2")])],
            aliases={},
            eligible={"10.1/a"},
        )


def test_canonical_doi_rows_replace_alias_rows_inside_one_layer():
    rows, report = assemble_layers(
        [],
        [
            (
                "update",
                [
                    evidence("10.1/legacy", "legacy-result"),
                    evidence("10.1/article", "canonical-result"),
                ],
            )
        ],
        aliases={"10.1/legacy": "10.1/article"},
        eligible={"10.1/article"},
    )

    assert [row["source_item_id"] for row in rows] == ["canonical-result"]
    assert report["overlays"]["update"]["doi_alias_collision_rows_removed"] == 1
    assert report["overlays"]["update"]["doi_alias_collision_papers"] == 1


def test_multiple_aliases_without_canonical_row_fail_closed():
    with pytest.raises(ValueError, match="multiple DOI aliases"):
        assemble_layers(
            [],
            [
                (
                    "update",
                    [evidence("10.1/legacy-a", "a"), evidence("10.1/legacy-b", "b")],
                )
            ],
            aliases={
                "10.1/legacy-a": "10.1/article",
                "10.1/legacy-b": "10.1/article",
            },
            eligible={"10.1/article"},
        )


def test_candidate_metadata_replaces_stale_and_fills_blank_fields():
    rows, report = apply_candidate_metadata(
        [
            {
                **evidence("10.1/article", "a"),
                "study_title": "",
                "study_year": "2023",
            }
        ],
        {
            "10.1/article": {
                "study_title": "Canonical title",
                "study_year": "2024",
            }
        },
    )

    assert rows[0]["study_title"] == "Canonical title"
    assert rows[0]["study_year"] == "2024"
    assert report == {
        "papers_updated_from_candidate_metadata": 1,
        "row_fields_updated_from_candidate_metadata": 2,
        "blank_row_fields_filled_from_candidate_metadata": 1,
        "row_fields_cleared_from_candidate_metadata": 0,
    }


def test_explicit_candidate_metadata_clear_removes_stale_evidence_field(tmp_path):
    candidates = tmp_path / "candidate_papers.parquet"
    overrides = tmp_path / "paper_metadata_overrides.json"
    pd.DataFrame(
        [
            {
                "doi": "10.1/chimera",
                "study_title": "Canonical title",
                "openalex_id": "",
            }
        ]
    ).to_parquet(candidates, index=False)
    overrides.write_text(
        json.dumps(
            {
                "records": [
                    {
                        "doi": "10.1/chimera",
                        "clear_fields": ["openalex_id"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    clears = explicit_metadata_clears(overrides, {})
    metadata = candidate_metadata(candidates, {}, explicit_clears=clears)
    rows, report = apply_candidate_metadata(
        [
            {
                **evidence("10.1/chimera", "a"),
                "study_title": "Canonical title",
                "openalex_id": "W-corrupt",
            }
        ],
        metadata,
    )

    assert rows[0]["openalex_id"] == ""
    assert report["row_fields_cleared_from_candidate_metadata"] == 1


def test_legacy_v1_secondary_outputs_are_removed_with_audit_counts():
    current = {"study_doi": "10.1/current", "prompt_profile": "primary_clinical"}
    legacy_review = {
        "result": {"study_doi": "10.1/review"},
        "prompt_profile": "secondary_narrative_review",
        "schema_profile": "review_coverage_schema",
    }
    legacy_meta = {
        "study_doi": "10.1/meta",
        "extraction_contract": {
            "prompt_profile": "secondary_meta_analysis",
            "schema_profile": "meta_analysis_evidence_schema",
        },
    }

    rows, report = remove_legacy_v1_secondary_outputs(
        [current, legacy_review, legacy_meta]
    )

    assert rows == [current]
    assert report["legacy_v1_secondary_rows_removed"] == 2
    assert report["legacy_v1_secondary_papers_removed"] == 2
    assert report["legacy_v1_secondary_contract_counts"] == {
        "secondary_meta_analysis/meta_analysis_evidence_schema": 1,
        "secondary_narrative_review/review_coverage_schema": 1,
    }


def test_non_v2_meta_analysis_evidence_fails_closed():
    with pytest.raises(ValueError, match="non-V2 meta-analysis evidence"):
        reject_non_v2_meta_analysis_evidence(
            [
                {
                    **evidence("10.1/meta", "legacy", source_type="meta_analysis"),
                    "route_output_schema_version": "routed_evidence_rows_v1",
                }
            ]
        )


def test_v2_meta_analysis_evidence_is_accepted():
    reject_non_v2_meta_analysis_evidence(
        [
            {
                **evidence("10.1/meta", "current", source_type="meta_analysis"),
                "route_output_schema_version": "meta_analysis_v2_evidence_rows_v1",
            }
        ]
    )
