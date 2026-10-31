"""PK measurements and bundled source observations survive identity misses."""
from copy import deepcopy
import json
from pathlib import Path

import pandas as pd
import pytest

from pipeline.kg import build_evidence_tables as b
from pipeline.kg.pk_observation_identity import (
    explicit_pk_observation, pk_observation_recovery, pk_observation_signature,
)


def observation(**changes):
    return {"domain": "pharmacokinetics_exposure", "source_item_type": "primary_item",
            "source_type": "primary", "pk_relationship_type": "exposure_characterized",
            "pk_graph_object_kind": "metabolite_or_analyte", "pk_graph_object_label": "LSD",
            "pk_or_exposure_parameter": "Plasma concentration", "model_or_method": "LC-MS/MS",
            "finding_summary": "Plasma LSD was measured after administration.", **changes}


@pytest.mark.parametrize("relation", ["exposure_characterized", "detected_or_monitored_in"])
def test_same_analyte_measurement_is_not_self_metabolism(relation):
    row = observation(pk_relationship_type=relation)
    before = deepcopy(row)
    result = pk_observation_recovery(row, self_reference=True)
    assert result["kind"] == "pharmacokinetic_parameter"
    assert "LSD" in result["label"] and "Plasma concentration" in result["label"]
    assert row == before


@pytest.mark.parametrize("relation", ["metabolized_to", "metabolized_via", "other_pk_relationship",
                                      "eliminated_by", "exposure_altered_by"])
def test_self_transformation_and_unspecified_relations_still_need_resolution(relation):
    assert pk_observation_recovery(observation(pk_relationship_type=relation), self_reference=True) is None


@pytest.mark.parametrize("changes", [
    {"source_item_type": "review_relationship"}, {"source_type": "review"},
    {"domain": "molecular_target"}, {"model_or_method": "not_reported"},
    {"finding_summary": ""}, {"pk_graph_object_label": "unknown"},
    {"pk_relationship_type": "uncertain"}, {"pk_graph_object_kind": "uncertain"},
    {"pk_relationship_type": ""},
])
def test_missing_or_other_source_contracts_do_not_get_a_recovery(changes):
    row = observation(**changes)
    assert not explicit_pk_observation(row)
    assert pk_observation_recovery(row) is None


def test_signature_does_not_confuse_different_sources_or_pk_objects():
    row = observation(task_id="task", source_item_index=1)
    for field, value in [("task_id", "other"), ("source_item_index", 2),
                         ("pk_graph_object_label", "Psilocin"), ("model_or_method", "GC-MS")]:
        assert pk_observation_signature(row) != pk_observation_signature({**row, field: value})


def test_saved_pk_results_keep_original_values_and_panels_once(tmp_path):
    fixture = Path(__file__).parent / "fixtures/pk_observation_saved_rows.json"
    originals = json.loads(fixture.read_text())
    by_key = {(r["task_id"], r["source_item_index"]): r for r in originals}
    b.build_tables(out_dir=tmp_path, write_duckdb=False, graph_sources={
        "routed_extractions": {"path": fixture, "domain": "routed", "dataset": "routed",
                               "default_evidence_type": "primary_evidence", "skip_audit": True},
    })
    findings = pd.read_parquet(tmp_path / "findings.parquet").fillna("")
    audits = pd.read_parquet(tmp_path / "normalization_audit.parquet").fillna("")
    assert len(findings) == 7 and len(audits) == 2
    assert findings.graph_admission_status.eq("paper_detail").all()
    assert set(audits.normalization_status) == {"entity_unmapped", "pk_self_reference_not_graphable"}
    keys = []
    for record in findings.to_dict("records"):
        raw = json.loads(record["raw_row_json"])
        key = (raw["task_id"], raw["source_item_index"])
        keys.append(key)
        source = by_key[key]
        for field in ["pk_relationship_type", "pk_graph_object_kind", "pk_graph_object_label",
                      "pk_or_exposure_parameter", "metabolite_or_analyte", "analyte_type",
                      "metabolic_or_transport_target", "metabolic_or_transport_pathway",
                      "matrix", "model_or_method", "finding_summary", "value", "unit",
                      "effect_or_statistic", "dose", "route_of_administration", "sampling_time_or_window",
                      "population_or_system", "sample_size", "evidence_location", "evidence_locator"]:
            assert raw.get(field) == source.get(field), field
        assert not raw.get("entity_split_source_label")
        assert raw.get("target") == source.get("target")
        assert raw.get("pathway_or_process") == source.get("pathway_or_process")
    assert len(keys) == len(set(keys))
    panel = findings[findings.study_doi.eq("10.1007/s00216-015-8828-6")]
    assert len(panel) == 1
    assert panel.iloc[0].entity_label == "CYP2C9, CYP2C19, CYP1A2, and CYP3A4"


def test_inferred_relationship_cannot_satisfy_the_saved_contract(tmp_path):
    fixture = Path(__file__).parent / "fixtures/pk_observation_saved_rows.json"
    row = next(r for r in json.loads(fixture.read_text()) if r['doi'] == '10.1007/s00216-015-8828-6')
    row.pop("pk_relationship_type")
    path = tmp_path / "input.json"
    path.write_text(json.dumps([row]))
    b.build_tables(out_dir=tmp_path / "out", write_duckdb=False, graph_sources={
        "routed_extractions": {"path": path, "domain": "routed", "dataset": "routed",
                               "default_evidence_type": "primary_evidence", "skip_audit": True},
    })
    findings = pd.read_parquet(tmp_path / "out/findings.parquet")
    assert findings.empty
