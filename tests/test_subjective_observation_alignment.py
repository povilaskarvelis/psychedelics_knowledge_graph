import json
from pathlib import Path

import pandas as pd
import pytest

from pipeline.kg import build_evidence_tables as b
from pipeline.publish.export_evidence_payload import (
    load_findings, detail_bootstrap_payload, OPTIONAL_SUBJECTIVE_OBSERVATION_FIELDS,
)


def observation(**changes):
    return {
        "domain": "subjective_experience", "source_type": "primary",
        "source_item_type": "primary_item", "extraction_schema_version": "primary_subjective_experience_v1",
        "compound_or_exposure": "N,N-dimethyltryptamine (DMT) versus placebo (saline)",
        "subjective_construct": "Positive affect; Negative affect",
        "instrument_or_measure": "Positive and Negative Affect Schedule (PANAS)",
        "finding_summary": "Positive affect increased; negative affect did not change.",
        **changes,
    }


@pytest.mark.parametrize("construct", [
    "Positive affect; Negative affect", "Perceptual alterations and psychological insight",
    "Mystical-type experience / Ego dissolution", "Positive affect & Negative affect",
    "Altered state profile; Mystical-type experience; Mood effects",
])
def test_joint_construct_is_not_reduced_to_one_component(construct):
    row = observation(subjective_construct=construct)
    normalized = b.normalize_claim_metadata(row, "subjective_experience")
    assert normalized["graph_entity_label"] == construct
    assert normalized["graph_admission_status"] == "paper_detail"
    assert b.normalize_claim_metadata(normalized, "subjective_experience") == normalized
    match = b.graphable_entity_match(normalized, "subjective_experience", "subjective_experience_construct",
                                    construct, {}, {})
    assert match["label"] == construct
    assert match["match_type"] == "explicit_subjective_composite_detail_only"


@pytest.mark.parametrize("changes", [
    {"subjective_construct": "Dissociation / Depersonalization"},
    {"subjective_construct": "Positive affect"},
    {"subjective_construct": ""},
    {"subjective_construct": "Positive affect", "instrument_or_measure": "Positive affect; Negative affect"},
    {"source_type": "review"}, {"source_item_type": "review_relationship"},
    {"extraction_schema_version": "legacy"}, {"domain": "cognitive_behavioral"},
    {"entity_split_source_label": "parent"}, {"endpoint_label_source": "subjective_experience_safety_boundary"},
])
def test_composite_requires_distinct_native_constructs(changes):
    assert b.subjective_composite_label(observation(**changes)) == ""


@pytest.mark.parametrize("exposure", [
    "N,N-dimethyltryptamine (DMT) versus placebo (saline)",
    "N,N-dimethyltryptamine (DMT); placebo (saline) comparator",
    "Lysergic acid diethylamide (LSD) compared with placebo",
])
def test_agreeing_identity_and_synonym_precede_the_control(exposure):
    registry = b.registry_lookup(b.DEFAULT_REGISTRY_PATH)
    result = b.subjective_comparison_subject(observation(compound_or_exposure=exposure), registry)
    assert result == ("LSD" if exposure.startswith("Lysergic") else "DMT")


@pytest.mark.parametrize("exposure", [
    "Unknown analogue (DMT) versus placebo (saline)",
    "N,N-dimethyltryptamine (5-MeO-DMT) versus placebo",
    "Cocaine (DMT) versus placebo", "Placebo (saline) versus DMT",
    "N,N-dimethyltryptamine (DMT) versus ketamine",
    "N,N-dimethyltryptamine (DMT) with saline",
    "History of N,N-dimethyltryptamine (DMT) versus placebo",
    "DMT analogue (DMT) versus placebo", "Cocaine (cocaine) versus placebo",
])
def test_comparison_does_not_borrow_a_parenthetical_or_background_identity(exposure):
    registry = b.registry_lookup(b.DEFAULT_REGISTRY_PATH)
    assert not b.subjective_comparison_subject(observation(compound_or_exposure=exposure), registry)


def test_incomplete_or_secondary_comparison_does_not_qualify():
    registry = b.registry_lookup(b.DEFAULT_REGISTRY_PATH)
    for changes in [{"instrument_or_measure": "not_reported"}, {"finding_summary": ""}, {"source_type": "review"}]:
        assert not b.subjective_comparison_subject(observation(**changes), registry)


def saved_rows():
    return json.loads((Path(__file__).parent / "fixtures/subjective_observation_saved_rows.json").read_text())


def test_saved_luna_rows_keep_joint_results_and_recover_dmt_comparisons(tmp_path):
    rows = saved_rows()
    source = tmp_path / "rows.json"
    source.write_text(json.dumps(rows))
    b.build_tables(graph_sources={"routed_extractions": {"path": source, "domain": "routed", "dataset": "routed",
                   "default_evidence_type": "primary_evidence", "skip_audit": True}}, out_dir=tmp_path / "tables", write_duckdb=False)
    findings = pd.read_parquet(tmp_path / "tables/findings.parquet").fillna("")
    recovered = findings[findings.compound_match_type.eq("explicit_subjective_active_control_comparison")]
    assert len(recovered) == 3
    assert set(recovered.compound) == {"DMT"}
    composites = findings[findings.entity_match_type.eq("explicit_subjective_composite_detail_only")]
    assert len(composites) == 4
    assert composites.graph_admission_status.eq("paper_detail").all()
    for result in composites.to_dict("records"):
        raw = json.loads(result["raw_row_json"])
        assert result["entity_label"] == raw["subjective_construct"]
        original = next(r for r in rows if (r["task_id"], r["source_item_index"]) == (raw["task_id"], raw["source_item_index"]))
        for field in ["subjective_construct", "instrument_or_measure", "statistic_or_value", "finding_summary", "relationship_to_outcome", "evidence_locator"]:
            assert raw.get(field) == original.get(field)


def test_subjective_source_details_survive_public_export(tmp_path):
    native = next(r for r in saved_rows() if r["study_doi"] == "10.1002/cpt.2958")
    pd.DataFrame([{"finding_id": "subjective", "paper_id": "paper", "source_name": "routed_extractions",
                   "study_doi": native["study_doi"], "domain": "subjective_experience", "compound": "2C-B",
                   "entity_label": native["subjective_construct"], "raw_row_json": json.dumps(native)}]).to_parquet(tmp_path / "findings.parquet", index=False)
    payload = detail_bootstrap_payload(load_findings(tmp_path, require_author_identities=False), "2026-10-31", tmp_path, "primary")
    row = {k: payload["values"][v] for k, v in zip(payload["fields"], payload["rows"][0])}
    for field in [*OPTIONAL_SUBJECTIVE_OBSERVATION_FIELDS, "statistic_or_value"]:
        assert row[field] == native[field]
    assert "raw_row_json" not in row
