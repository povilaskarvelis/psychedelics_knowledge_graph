"""Real-world observations keep predictors, pooled estimates and source scope."""
from copy import deepcopy
import json
from pathlib import Path

import pandas as pd
import pytest

from pipeline.kg import build_evidence_tables as b
from pipeline.kg.real_world_observation_identity import (
    explicit_real_world_observation, real_world_observation_signature,
    real_world_observation_recovery, MATCH_TYPE, DETAIL_REASON,
)


def observation(**changes):
    return {"domain": "real_world_public_health", "source_type": "primary", "source_item_type": "primary_item",
            "extraction_schema_version": "primary_real_world_public_health_v1", "task_id": "task", "source_item_index": 1,
            "exposure_or_policy": "Festival attendance", "compound": "Festival attendance",
            "public_health_measure": "Hair toxicology positivity for MDMA, ketamine and cocaine",
            "public_health_topic_category": "Population use & trends", "study_design": "Cross-sectional survey",
            "finding_summary": "Hair samples tested positive for MDMA, ketamine and cocaine.", **changes}


@pytest.mark.parametrize("field", ["exposure_or_policy", "public_health_measure", "public_health_topic_category", "study_design", "finding_summary"])
def test_missing_native_fields_cannot_be_filled_from_context(field):
    row = observation(**{field: "not_reported"})
    assert not explicit_real_world_observation(row)
    assert real_world_observation_recovery(row) is None


@pytest.mark.parametrize("changes", [
    {"domain": "safety_tolerability"}, {"source_type": "narrative_review"},
    {"source_item_type": "synthesis_result"}, {"extraction_schema_version": "legacy"},
    {"entity_split_source_label": "Derived endpoint"}, {"compound": "LSD"},
    {"graph_subject_label": "Unrelated predictor"}, {"evidence_location": "Introduction"},
])
def test_other_contracts_explicit_drugs_and_background_do_not_qualify(changes):
    assert real_world_observation_recovery(observation(**changes)) is None


@pytest.mark.parametrize("measure, finding", [
    ("Cocaine intake", "Cocaine use increased."),
    ("Drug use", "Use increased without MDMA."),
    ("Drug use", "An unregistered 8-MeO-DMT derivative was detected."),
    ("Drug use", "DMT receptor binding was assayed."),
    ("Drug use", "No drug-specific result was reported."),
    ("Motives for illicit drug use", "Reasons were reported for illicit drug use generally, not specifically for psychedelic substances."),
    ("Fluorofentanyl detection", "The fluorofentanyl classifier showed more limited performance than the MDA model."),
    ("Anxiety severity", "Groups differed in anxiety. These data do not establish that psychedelic use caused the difference."),
])
def test_titles_populations_parent_substrings_and_out_of_scope_drugs_cannot_supply_scope(measure, finding):
    row = observation(public_health_measure=measure, finding_summary=finding,
                      study_title="MDMA use", population="People using ketamine", support="MDMA increased")
    assert real_world_observation_recovery(row) is None


def test_mixed_observation_has_one_literal_subject_and_scope_is_only_provenance():
    row = observation(estimate_value="50% positive for any tested drug")
    original = deepcopy(row)
    proposal = real_world_observation_recovery(row)
    assert proposal["label"] == "Festival attendance"
    assert proposal["kind"] == "exposure_context"
    assert proposal["scope_labels"] == ["Ketamine", "MDMA"]
    assert proposal["reason"] == DETAIL_REASON
    assert row == original


def test_null_results_and_multi_substance_predictors_remain_complete_observations():
    row = observation(exposure_or_policy="Daily methamphetamine use", compound="Daily methamphetamine use",
                      public_health_measure="Interest in psychedelic-assisted therapy",
                      finding_summary="Daily methamphetamine use was not associated with interest in psychedelic-assisted therapy.")
    assert real_world_observation_recovery(row)["label"] == row["exposure_or_policy"]


def test_inferred_fields_cannot_borrow_original_eligibility():
    row = observation()
    for field in ["study_doi", "task_id", "source_item_index", "exposure_or_policy", "public_health_measure", "study_design"]:
        assert real_world_observation_signature(row) != real_world_observation_signature({**row, field: "changed"})


def test_scope_evidence_respects_the_supplied_registry(tmp_path):
    path = tmp_path / "registry.json"
    path.write_text(json.dumps({"compounds": [{"label": "MDMA", "aliases": [], "graph_scope": "out_of_scope"}]}))
    assert real_world_observation_recovery(observation(), path) is None


def test_saved_rows_retain_whole_observations_without_atomic_or_use_context_projection(tmp_path):
    rows = json.loads((Path(__file__).parent / "fixtures/real_world_observation_saved_rows.json").read_text())
    source = tmp_path / "source.json"
    source.write_text(json.dumps(rows))
    b.build_tables(out_dir=tmp_path / "tables", write_duckdb=False, graph_sources={"routed_extractions": {
        "path": source, "domain": "routed", "dataset": "routed", "default_evidence_type": "primary_evidence", "skip_audit": True}})
    findings, edges, audit = [pd.read_parquet(tmp_path / f"tables/{name}.parquet").fillna("") for name in ["findings", "evidence_edges", "normalization_audit"]]
    recovered = findings[findings.compound_match_type.eq(MATCH_TYPE)]
    # A drug named only in the measured outcome, with a non-drug predictor, is
    # the subject (COVID-19 lockdown; wastewater MDMA loads). The predictor and
    # the complete measure stay on the finding.
    loads = [r for r in findings.to_dict("records")
             if json.loads(r["raw_row_json"]).get("public_health_measure") == "Wastewater-derived population-normalized MDMA loads."]
    assert len(loads) == 1 and loads[0]["graph_subject_label"] == "MDMA"
    assert json.loads(loads[0]["raw_row_json"])["real_world_subject_resolution_reason"] == "single_drug_named_only_in_measured_outcome"
    assert len(recovered) == 7
    assert recovered.graph_admission_status.eq("paper_detail").all()
    assert recovered.graph_overview_subject_label.eq("").all()
    assert recovered.graph_overview_subjects_json.eq("[]").all()
    assert recovered.graph_use_context_projections_json.eq("[]").all()
    assert edges[edges.finding_id.isin(recovered.finding_id)].graph_admission_status.eq("paper_detail").all()
    by_key = {(r["task_id"], str(r["source_item_index"])): r for r in rows}
    keys = []
    for result in recovered.to_dict("records"):
        raw = json.loads(result["raw_row_json"])
        key = (raw["task_id"], str(raw["source_item_index"]))
        keys.append(key)
        original = by_key[key]
        for field in ["exposure_or_policy", "public_health_measure", "public_health_topic_category", "finding_summary",
                      "estimate_value", "estimate_unit", "effect_or_statistic", "association_or_trend", "time_window",
                      "study_design", "sample_size", "population", "setting", "evidence_location", "evidence_locator"]:
            assert raw.get(field) == original.get(field), field
        assert result["graph_subject_label"] == original["exposure_or_policy"]
        assert raw["graph_subject_kind"] == "exposure_context"
    assert len(keys) == len(set(keys))
    # Non-psychedelic Ramadan findings remain subject to the existing scope rules.
    assert not recovered.study_doi.eq("10.1007/s11356-022-22016-w").any()


def test_detail_only_subject_cannot_project_a_drug_or_use_context():
    row = observation(exposure_or_policy="MDMA at a music festival", graph_admission_reason=DETAIL_REASON)
    match = {"label": "MDMA", "subject_kind": "atomic_compound"}
    registry = b.registry_lookup(b.DEFAULT_REGISTRY_PATH)
    assert b.overview_graph_subjects(row, match, registry) == []
    assert b.graph_use_context_projections(row, "real_world_public_health", [match], registry) == []


def test_measured_negative_detection_is_not_a_scope_caveat():
    row = observation(public_health_measure="Drug panel detection", finding_summary="MDMA was not detected in the tested samples.")
    assert real_world_observation_recovery(row)["scope_labels"] == ["MDMA"]
