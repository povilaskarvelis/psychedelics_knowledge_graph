import json
from pathlib import Path

import pandas as pd

from pipeline.kg.build_evidence_tables import DEFAULT_REGISTRY_PATH, build_tables


def build_rows(tmp_path: Path, rows: list[dict]) -> tuple[pd.DataFrame, pd.DataFrame]:
    source = tmp_path / "rows.json"
    out_dir = tmp_path / "kg"
    source.write_text(json.dumps(rows), encoding="utf-8")
    build_tables(
        registry_path=DEFAULT_REGISTRY_PATH,
        out_dir=out_dir,
        write_duckdb=False,
        graph_sources={
            "routed_extractions": {
                "path": source,
                "domain": "routed",
                "dataset": "routed",
                "default_evidence_type": "secondary_literature",
                "skip_audit": True,
            }
        },
    )
    return (
        pd.read_parquet(out_dir / "evidence_edges.parquet"),
        pd.read_parquet(out_dir / "normalization_audit.parquet"),
    )


def meta_row(**overrides: object) -> dict:
    row = {
        "study_doi": "10.1000/meta-normalization",
        "study_title": "Meta-analysis",
        "study_year": "2025",
        "compound": "Psilocybin",
        "paper_type": "meta_analysis",
        "source_type": "meta_analysis",
        "source_family": "secondary_literature",
        "paper_assessment_route": "secondary_literature",
        "source_item_type": "synthesis_result",
        "source_item_id": "R1",
        "meta_analysis_result_role": "primary_synthesis",
        "result_direction": "supports",
        "support": "The pooled result supported the stated relationship.",
    }
    row.update(overrides)
    return row


def test_brain_measure_is_normalized_to_a_stable_measure_family(tmp_path: Path) -> None:
    edges, audit = build_rows(
        tmp_path,
        [
            meta_row(
                domain="brain_system",
                graph_entity_label="Between-network functional connectivity",
                readout_or_measure="Between-network functional connectivity",
                kg_entity_kind_override="brain_measure",
            )
        ],
    )

    assert audit.empty
    assert set(edges["entity_kind"]) == {"brain_measure"}
    assert set(edges["entity_label"]) == {"Functional connectivity"}


def test_meta_analysis_safety_events_cover_perceptual_and_discontinuation_outcomes(tmp_path: Path) -> None:
    edges, audit = build_rows(
        tmp_path,
        [
            meta_row(
                source_item_id="R1",
                domain="safety_tolerability",
                graph_entity_label="Hallucinations",
                safety_event_or_measure="Hallucinations",
                kg_entity_kind_override="safety_adverse_event",
            ),
            meta_row(
                source_item_id="R2",
                domain="safety_tolerability",
                graph_entity_label="All-cause discontinuation",
                safety_event_or_measure="All-cause discontinuation",
                kg_entity_kind_override="safety_adverse_event",
            ),
        ],
    )

    assert audit.empty
    assert set(edges["entity_label"]) == {"Perceptual disturbances", "All-cause discontinuation"}


def test_meta_analysis_subgroups_are_not_false_direction_conflicts(tmp_path: Path) -> None:
    base = {
        "domain": "clinical_outcome",
        "graph_entity_label": "Major depressive disorder",
        "condition_or_indication": "Major depressive disorder",
        "kg_entity_kind_override": "condition_indication",
        "population": "Adults with major depressive disorder",
        "comparator": "Active placebo",
        "comparator_normalized": "Active treatment",
        "meta_analysis_result_role": "subgroup_analysis",
    }
    edges, audit = build_rows(
        tmp_path,
        [
            meta_row(
                **base,
                source_item_id="R1",
                meta_analysis_subgroup_or_moderator="active-placebo design",
                result_direction="no_detected_effect",
            ),
            meta_row(
                **{
                    **base,
                    "source_item_id": "R2",
                    "comparator": "Inactive placebo",
                    "meta_analysis_subgroup_or_moderator": "inactive-placebo design",
                    "result_direction": "supports",
                }
            ),
        ],
    )

    assert audit.empty
    assert len(edges) == 2
    assert set(edges["direction_consistency"]) == {"consistent_or_not_applicable"}
    assert set(edges["graph_admission_status"]) == {"main_graph"}


def test_meta_analysis_context_moderator_is_graphable_when_it_is_the_analysis_focus(tmp_path: Path) -> None:
    edges, audit = build_rows(
        tmp_path,
        [
            meta_row(
                domain="intervention_context",
                compound="Psilocybin-assisted therapy",
                graph_entity_label="Session frequency",
                context_component="Session frequency",
                kg_entity_kind_override="intervention_component",
                meta_analysis_result_role="meta_regression",
            )
        ],
    )

    assert audit.empty
    assert set(edges["entity_kind"]) == {"intervention_component"}
    assert set(edges["graph_parent_label"]) == {"Treatment intensity & duration"}


def test_beneficial_social_anxiety_response_is_not_derived_as_a_safety_event(tmp_path: Path) -> None:
    edges, audit = build_rows(
        tmp_path,
        [
            meta_row(
                domain="clinical_outcome",
                compound="Ketamine",
                graph_entity_label="Social Anxiety Disorder (SAD)",
                condition_or_indication="Social Anxiety Disorder (SAD)",
                kg_entity_kind_override="condition_indication",
                clinical_endpoint="Treatment response",
                outcome_type="beneficial",
                population="Social Anxiety Disorder (SAD)",
                support=(
                    "In patients with Social Anxiety Disorder (SAD), ketamine was associated with a "
                    "significantly increased likelihood of treatment response compared with control."
                ),
                effect_size="OR 28.94; CI 3.45 to 242.57",
                confidence_interval="3.45 to 242.57",
                p_value="0.002",
                needs_human_review=True,
                extraction_warnings="nonverbatim_supporting_text:R1:1",
            )
        ],
    )

    assert audit.empty
    assert edges.loc[edges["entity_kind"] == "safety_adverse_event"].empty
    condition = edges.loc[edges["entity_kind"] == "condition_indication"].iloc[0]
    assert condition["entity_label"] == "Social anxiety disorder"
    assert condition["graph_admission_status"] == "main_graph"
    assert condition["graph_admission_reason"] == "semantically_complete_with_unverified_quote"


def test_substantive_human_review_warning_still_blocks_graph_admission(tmp_path: Path) -> None:
    edges, audit = build_rows(
        tmp_path,
        [
            meta_row(
                domain="clinical_outcome",
                graph_entity_label="Major depressive disorder",
                condition_or_indication="Major depressive disorder",
                kg_entity_kind_override="condition_indication",
                needs_human_review=True,
                extraction_warnings="numeric_value_not_in_source:R1:estimate",
            )
        ],
    )

    assert audit.empty
    condition = edges.loc[edges["entity_kind"] == "condition_indication"].iloc[0]
    assert condition["graph_admission_status"] == "paper_detail"
    assert condition["graph_admission_reason"] == "extraction_marked_for_human_review"


def test_nonstatistical_quote_only_warning_remains_paper_detail(tmp_path: Path) -> None:
    edges, audit = build_rows(
        tmp_path,
        [
            meta_row(
                domain="clinical_outcome",
                graph_entity_label="Major depressive disorder",
                condition_or_indication="Major depressive disorder",
                kg_entity_kind_override="condition_indication",
                needs_human_review=True,
                extraction_warnings="nonverbatim_supporting_text:R1:1",
            )
        ],
    )

    assert audit.empty
    condition = edges.loc[edges["entity_kind"] == "condition_indication"].iloc[0]
    assert condition["graph_admission_status"] == "paper_detail"
    assert condition["graph_admission_reason"] == "extraction_marked_for_human_review"
