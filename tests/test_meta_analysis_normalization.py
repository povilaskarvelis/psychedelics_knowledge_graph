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


def test_meta_analysis_brain_measure_projects_explicit_supported_networks(tmp_path: Path) -> None:
    edges, audit = build_rows(
        tmp_path,
        [
            meta_row(
                study_doi="10.1038/s41398-024-03187-1",
                domain="brain_system",
                compound="Classic psychedelics",
                graph_entity_label="Functional connectivity (FC) between Yeo networks",
                readout_or_measure="Functional connectivity (FC) between Yeo networks",
                brain_measure="Functional connectivity (FC) between Yeo networks",
                kg_entity_kind_override="brain_measure",
                supporting_quote=(
                    "Within-network connectivity significantly decreased in the visual network, "
                    "ventral attention network (VAN), and default mode network (DMN)."
                ),
                needs_human_review=True,
                extraction_warnings="nonverbatim_supporting_text:R1:1",
            )
        ],
    )

    assert audit.empty
    assert set(edges["entity_kind"]) == {"brain_network"}
    assert set(edges["entity_label"]) == {
        "Default mode network",
        "Salience network",
        "Visual network",
    }
    assert set(edges["graph_admission_status"]) == {"main_graph"}
    assert set(edges["graph_admission_reason"]) == {
        "semantically_complete_with_unverified_quote"
    }


def test_meta_analysis_target_measure_projects_explicit_supported_targets(tmp_path: Path) -> None:
    edges, audit = build_rows(
        tmp_path,
        [
            meta_row(
                study_doi="10.1038/s41398-024-03187-1",
                domain="molecular_target",
                compound="Classic psychedelics",
                graph_entity_label="Binding selectivity (Ki ratio)",
                target="Binding selectivity (Ki ratio)",
                kg_entity_kind_override="target",
                support=(
                    "Binding profiles included 5-HT2A, 5-HT2C, D2, and 5-HT1A receptors."
                ),
            ),
            meta_row(
                study_doi="10.1016/j.csbj.2025.12.023",
                source_item_id="R2",
                domain="molecular_target",
                compound="Ketamine",
                graph_entity_label="Network Degree Centrality",
                target="Network Degree Centrality",
                kg_entity_kind_override="target",
                support=(
                    "Network analysis identified OPRM1 (opioid receptor mu 1) as the explicit "
                    "molecular target."
                ),
            ),
        ],
    )

    assert audit.empty
    labels_by_doi = edges.groupby("study_doi")["entity_label"].apply(set).to_dict()
    assert labels_by_doi["10.1038/s41398-024-03187-1"] == {
        "5-HT1A",
        "5-HT2A",
        "5-HT2C",
        "Dopamine D2 receptor (DRD2)",
    }
    assert labels_by_doi["10.1016/j.csbj.2025.12.023"] == {
        "mu opioid receptor (OPRM1)"
    }


def test_meta_analysis_brain_measure_recovers_regions_from_support_when_measure_is_generic(
    tmp_path: Path,
) -> None:
    edges, audit = build_rows(
        tmp_path,
        [
            meta_row(
                domain="brain_system",
                graph_entity_label="Neural activation overlap (ALE conjunction)",
                brain_measure="Neural activation overlap (ALE conjunction)",
                kg_entity_kind_override="brain_measure",
                support=(
                    "The conjunction identified convergent activation in the anterior cingulate "
                    "cortex and supramarginal gyrus."
                ),
            )
        ],
    )

    assert audit.empty
    assert set(edges["entity_label"]) == {
        "Anterior cingulate cortex",
        "Supramarginal gyrus",
    }
    assert set(edges["entity_kind"]) == {"brain_region"}


def test_broad_meta_analysis_endpoints_are_retained_as_searchable_detail(tmp_path: Path) -> None:
    edges, audit = build_rows(
        tmp_path,
        [
            meta_row(
                study_doi="10.1016/j.psychres.2024.115886",
                source_item_id="R1",
                domain="clinical_outcome",
                graph_entity_label="symptoms of mental disorders",
                clinical_endpoint="symptoms of mental disorders",
                primary_outcome="symptoms of mental disorders",
                kg_entity_kind_override="symptom_problem",
            ),
            meta_row(
                study_doi="10.1038/s44220-023-00048-6",
                source_item_id="R2",
                domain="clinical_outcome",
                graph_entity_label="Adults with mental health disorders",
                condition_or_indication="Adults with mental health disorders",
                population="Adults with mental health disorders",
                clinical_endpoint="Psychiatric symptom severity",
                primary_outcome="Psychiatric symptom severity",
                normalization_entity_source="population_for_generic_clinical_outcome",
                kg_entity_kind_override="condition_indication",
            ),
            meta_row(
                study_doi="10.1097/jcp.0000000000001946",
                source_item_id="R3",
                domain="clinical_outcome",
                graph_entity_label="Clinical outcomes and psychoactive effects",
                clinical_endpoint="Clinical outcomes and psychoactive effects",
                primary_outcome="Clinical outcomes and psychoactive effects",
                kg_entity_kind_override="symptom_problem",
            ),
        ],
    )

    assert audit.empty
    by_doi = edges.set_index("study_doi")
    assert by_doi.loc["10.1016/j.psychres.2024.115886", "entity_label"] == "Mental health symptoms"
    assert by_doi.loc["10.1038/s44220-023-00048-6", "entity_label"] == "Mental health symptoms"
    assert (
        by_doi.loc["10.1097/jcp.0000000000001946", "entity_label"]
        == "Psychoactive effects-clinical outcome association"
    )


def test_meta_analysis_brain_activation_labels_resolve_to_precise_regions(tmp_path: Path) -> None:
    edges, audit = build_rows(
        tmp_path,
        [
            meta_row(
                source_item_id="R1",
                domain="brain_system",
                compound="Ketamine",
                graph_entity_label="Brain activation (dorsal ACC)",
                kg_entity_kind_override="brain_network",
            ),
            meta_row(
                source_item_id="R2",
                domain="brain_system",
                compound="Ketamine",
                graph_entity_label="Brain activation (right Heschl's gyrus)",
                kg_entity_kind_override="brain_network",
            ),
            meta_row(
                source_item_id="R3",
                domain="brain_system",
                compound="Ketamine",
                graph_entity_label="Brain activation (right insula, right-fusiform gyrus)",
                kg_entity_kind_override="brain_network",
            ),
            meta_row(
                source_item_id="R4",
                domain="brain_system",
                compound="Ketamine",
                graph_entity_label="Brain activation (rostral ACC)",
                kg_entity_kind_override="brain_network",
            ),
        ],
    )

    assert audit.empty
    assert set(edges["entity_label"]) == {
        "Anterior cingulate cortex",
        "Dorsal anterior cingulate cortex",
        "Fusiform gyrus",
        "Heschl's gyrus",
        "Insula",
    }


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


def test_straightforward_depression_and_sitb_meta_analyses_are_retained(tmp_path: Path) -> None:
    edges, audit = build_rows(
        tmp_path,
        [
            meta_row(
                study_doi="10.1007/s00213-025-06788-w",
                source_item_id="R1",
                domain="clinical_outcome",
                compound="Psilocybin",
                graph_entity_label="Patients with depression",
                condition_or_indication="Patients with depression",
                kg_entity_kind_override="condition_indication",
                normalization_entity_source="population_condition_with_result_outcome",
                population="Patients with depression",
                clinical_endpoint="Depression symptoms",
                primary_outcome="Depression symptoms",
            ),
            meta_row(
                study_doi="10.1038/s41398-022-02173-9",
                source_item_id="R2",
                domain="clinical_outcome",
                compound="Ketamine",
                graph_entity_label="Human participants",
                condition_or_indication="Human participants",
                kg_entity_kind_override="condition_indication",
                normalization_entity_source="population_condition_with_result_outcome",
                population="Human participants",
                clinical_endpoint="Aggregated binary SITB outcomes",
                primary_outcome="Aggregated binary SITB outcomes",
            ),
        ],
    )

    assert audit.empty
    assert set(edges["study_doi"]) == {
        "10.1007/s00213-025-06788-w",
        "10.1038/s41398-022-02173-9",
    }
    by_doi = edges.set_index("study_doi")
    assert by_doi.loc["10.1007/s00213-025-06788-w", "entity_label"] == "Low mood & depressive symptoms"
    assert by_doi.loc["10.1038/s41398-022-02173-9", "entity_label"] == "Suicidality"


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


def test_nonstatistical_provenance_only_warning_remains_graphable(tmp_path: Path) -> None:
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
    assert condition["graph_admission_status"] == "main_graph"
    assert condition["graph_admission_reason"] == "semantically_complete_with_unverified_quote"


def test_provenance_only_warning_is_nonblocking_across_meta_analysis_domains(tmp_path: Path) -> None:
    edges, audit = build_rows(
        tmp_path,
        [
            meta_row(
                domain="subjective_experience",
                graph_entity_label="Perceptual alterations",
                kg_entity_kind_override="subjective_experience_construct",
                needs_human_review=True,
                extraction_warnings="nonverbatim_supporting_text:R1:1",
            ),
                meta_row(
                    source_item_id="R2",
                    domain="molecular_pathway_readout",
                    graph_entity_label="Inositol phosphate (IP) formation at 5-HT2A",
                    specific_readout_or_marker="Inositol phosphate (IP) formation at 5-HT2A",
                    kg_entity_kind_override="pathway_process",
                    needs_human_review=True,
                    extraction_warnings="nonverbatim_supporting_text:R2:1",
                ),
        ],
    )

    assert audit.empty
    assert set(edges["graph_admission_status"]) == {"main_graph"}
    assert set(edges["graph_admission_reason"]) == {
        "semantically_complete_with_unverified_quote"
    }
