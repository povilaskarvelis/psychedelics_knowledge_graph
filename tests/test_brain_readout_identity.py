"""Saved neural measurements remain distinct from anatomical graph claims."""
import json
from pathlib import Path

import pandas as pd
import pytest

from pipeline.kg import build_evidence_tables as b
from pipeline.kg.brain_readout_identity import has_explicit_neural_assay, nested_registered_brain_region, recovered_anatomy_detail_reason


def observation(method, **fields):
    return {"source_item_type": "primary_item", "assay_type": method,
            "readout": "Literal measured endpoint, including its null contrast",
            "finding_summary": "No change was detected versus vehicle.", **fields}


@pytest.mark.parametrize("method", [
    "Scalp EEG", "Resting-state fMRI", "Whole-cell patch clamp", "Calcium imaging",
    "Fiber photometry", "TMS-EMG", "Multielectrode array (MEA)",
    "Polysomnography (PSG)", "TD-fNIRS", "Auditory brainstem response (ABR)",
    "Visual evoked potentials (VEP)", "Intracranial electrograms; FFT analysis",
    "Western blot; electrophysiology", "fMRI; whole-brain computational modeling",
])
def test_explicit_recording_methods_retain_one_literal_observation(method):
    row = observation(method)
    before = dict(row)
    assert has_explicit_neural_assay(row)
    assert row == before


@pytest.mark.parametrize("method", [
    "Western blot", "qRT-PCR", "Griess nitrite assay", "Immunostaining",
    "Behavioral testing", "Eye tracking", "Optogenetic manipulation",
    "Questionnaires", "ECG", "not_reported", "EEG not performed; behavioral testing",
])
def test_other_assays_and_incidental_modality_names_do_not_become_neural_recordings(method):
    row = observation(method, assay_family_normalized="EEG",
                      finding_summary="EEG and fMRI were discussed in the introduction.")
    assert not has_explicit_neural_assay(row)


@pytest.mark.parametrize("field", ["readout", "assay_type", "finding_summary"])
def test_missing_primary_evidence_stays_held(field):
    assert not has_explicit_neural_assay(observation("EEG", **{field: "not_reported"}))
    assert not has_explicit_neural_assay(observation("EEG", source_item_type="review_relationship"))


@pytest.mark.parametrize("label,expected", [
    ("Dentate gyrus of the hippocampus", "Dentate gyrus"),
    ("Adult dentate gyrus of the hippocampus", "Dentate gyrus"),
    ("Prelimbic (PL) cortex of the medial prefrontal cortex", "Prelimbic cortex"),
    ("DLPFC within the PFC", "Dorsolateral prefrontal cortex"),
    ("Prelimbic cortex in the prefrontal cortex", "Prelimbic cortex"),
])
def test_child_and_parent_must_resolve_through_existing_hierarchy(label, expected):
    item = nested_registered_brain_region(label, b.node_vocabulary_lookup(), b.label_key)
    assert item["label"] == expected


@pytest.mark.parametrize("label", [
    "Unknown subfield of the hippocampus", "Ventral CA1 of the hippocampus",
    "Hippocampal CA3c subfield", "Dentate gyrus of the amygdala",
    "Dentate gyrus and CA1 of the hippocampus", "Dentate gyrus of hippocampus and amygdala",
    "Prelimbic (DG) cortex of the medial prefrontal cortex",
    "Prelimbic cortex from hippocampus", "Dentate gyrus to hippocampus projection",
])
def test_unknown_subregions_wrong_parents_and_connections_are_not_collapsed(label):
    assert nested_registered_brain_region(label, b.node_vocabulary_lookup(), b.label_key) is None


def test_recovered_anatomy_does_not_change_the_experimental_subject_or_system():
    assert recovered_anatomy_detail_reason({"compound_or_exposure": "Alcohol and MDMA co-exposure"}, "atomic_compound") == "joint_exposure_not_single_drug_neural_result"
    assert recovered_anatomy_detail_reason({"compound_or_exposure": "MDMA, repeated exposure during adolescence"}, "atomic_compound") == ""
    assert recovered_anatomy_detail_reason({"compound_or_exposure": "Combined LSD and MDMA"}, "compound_combination") == ""
    assert recovered_anatomy_detail_reason({"system": "computational"}, "atomic_compound") == "computed_neural_anatomy_detail_only"


def test_saved_observations_preserve_measurements_localization_and_result_scope(tmp_path):
    fixtures = Path(__file__).parent / "fixtures/brain_readout_saved_rows.json"
    rows = json.loads(fixtures.read_text())
    originals = {(r.get("task_id"), str(r["source_item_index"])): r for r in rows}
    b.build_tables(out_dir=tmp_path, write_duckdb=False, graph_sources={
        "routed_extractions": {"path": fixtures, "domain": "routed", "dataset": "routed",
                               "default_evidence_type": "primary_evidence", "skip_audit": True},
    })
    findings = pd.read_parquet(tmp_path / "findings.parquet").fillna("")
    audit = pd.read_parquet(tmp_path / "normalization_audit.parquet")
    assert len(findings) == 13 and len(audit) == 1
    assert audit.normalization_status.eq("broad_brain_system_not_graphable").all()
    assert json.loads(audit.iloc[0].raw_row_json)["readout"] == "PV expression and Menin immunoreactivity"
    assert findings.finding_id.is_unique
    literal = findings[findings.entity_match_type.eq("native_neural_assay_readout_detail_only")]
    assert len(literal) == 10
    assert literal.graph_admission_status.eq("paper_detail").all()
    hierarchy = findings[findings.entity_match_type.eq("complete_registered_brain_hierarchy")]
    assert len(hierarchy) == 3
    assert hierarchy.graph_admission_status.eq("main_graph").sum() == 2
    joint = hierarchy[hierarchy.study_doi.eq("10.1159/000356820")].iloc[0]
    assert joint.graph_admission_reason == "joint_exposure_not_single_drug_neural_result"
    for finding in findings.to_dict("records"):
        raw = json.loads(finding["raw_row_json"])
        original = originals[(raw.get("task_id"), str(raw["source_item_index"]))]
        for field in ["brain_region", "brain_network", "neural_circuit", "readout", "assay_type",
                      "primary_graph_anchor_kind", "finding_summary", "support", "effect_or_statistic",
                      "value", "unit", "quantitative_value", "statistic_or_value", "p_value",
                      "evidence_location", "evidence_locator", "experimental_system_category"]:
            assert raw.get(field, "") == original.get(field, ""), field
        assert not raw.get("entity_split_source_label")
        if finding["entity_match_type"] == "native_neural_assay_readout_detail_only":
            assert finding["entity_label"] == original["readout"]
    modeled = findings[findings.study_doi.eq("10.1002/advs.202511780")].iloc[0]
    assert modeled.graph_admission_status == "paper_detail"
    assert "Simulated" in json.loads(modeled.raw_row_json)["finding_summary"]
