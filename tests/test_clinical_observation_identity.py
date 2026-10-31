"""A clinical measurement is retained independently of condition identity."""
from copy import deepcopy
import json
from pathlib import Path

import pandas as pd
import pytest

from pipeline.kg import build_evidence_tables as b
from pipeline.kg.clinical_observation_identity import (
    explicit_clinical_observation, clinical_observation_signature, clinical_observation_recovery,
)

MATCH = "explicit_primary_clinical_measurement_detail_only"


def observation(**changes):
    return {"domain": "clinical_outcome", "source_type": "primary", "source_item_type": "primary_item",
            "extraction_schema_version": "primary_clinical_outcome_v1", "task_id": "task", "source_item_index": 1,
            "clinical_endpoint": "Change in functional disability at follow-up",
            "outcome_measure": "Disability score", "study_design": "Prospective cohort study",
            "finding_summary": "Disability changed from baseline; no causal effect was isolated.", **changes}


@pytest.mark.parametrize("field", ["clinical_endpoint", "outcome_measure", "study_design", "finding_summary"])
@pytest.mark.parametrize("value", ["", "not_reported"])
def test_missing_source_fields_are_not_inferred(field, value):
    row = observation(**{field: value})
    assert not explicit_clinical_observation(row)
    assert clinical_observation_recovery(row) is None


@pytest.mark.parametrize("changes", [
    {"domain": "safety_tolerability"}, {"source_type": "narrative_review"},
    {"source_item_type": "synthesis_result"}, {"extraction_schema_version": "legacy"},
    {"endpoint_label_source": "clinical_symptom_endpoint"}, {"endpoint_label_source": "condition_text_split"},
])
def test_other_source_contracts_and_derived_projections_do_not_qualify(changes):
    assert not explicit_clinical_observation(observation(**changes))


def test_literal_endpoint_is_independent_of_population_diagnosis_and_length():
    row = observation(condition_or_population="Participants without a specified diagnosis",
                      clinical_endpoint="Measured functioning across several domains: " + "x" * 200)
    original = deepcopy(row)
    result = clinical_observation_recovery(row)
    assert result["label"] == row["clinical_endpoint"]
    assert result["kind"] == "reported_measurement"
    assert result["reason"] == "clinical_measurement_without_resolved_condition"
    assert row == original


def test_inferred_and_split_fields_cannot_borrow_native_eligibility():
    row = observation(condition_or_population="Pooled clinical population")
    for field in ["task_id", "source_item_index", "clinical_endpoint", "outcome_measure", "condition_or_population"]:
        assert clinical_observation_signature(row) != clinical_observation_signature({**row, field: "changed"})


def saved_rows():
    return json.loads((Path(__file__).parent / "fixtures/clinical_observation_saved_rows.json").read_text())


def build_source(rows, tmp_path, projections=True):
    path = tmp_path / "source.json"
    path.write_text(json.dumps(rows))
    source = {"path": path, "domain": "routed", "dataset": "routed",
              "default_evidence_type": "primary_evidence", "skip_audit": True}
    sources = {"routed_extractions": source}
    if projections:
        sources["routed_clinical_endpoints"] = {**source, "transform": "clinical_endpoints"}
    b.build_tables(out_dir=tmp_path / "tables", write_duckdb=False, graph_sources=sources)
    return tuple(pd.read_parquet(tmp_path / f"tables/{name}.parquet").fillna("")
                 for name in ["findings", "evidence_edges", "normalization_audit"])


def test_saved_observations_preserve_endpoints_statistics_and_population_roles(tmp_path):
    originals = saved_rows()
    key = lambda r: (r["task_id"], str(r["source_item_index"]))
    sources = {key(r): r for r in originals}
    findings, edges, audit = build_source(originals, tmp_path)
    recovered = findings[findings.entity_match_type.eq(MATCH)]
    assert len(recovered) == 8
    assert recovered.graph_admission_status.eq("paper_detail").all()
    assert recovered.kg_entity_kind_override.eq("reported_measurement").all()
    assert recovered.graph_parent_label.eq("").all()
    new_edges = edges[edges.finding_id.isin(recovered.finding_id)]
    assert len(new_edges) == 8
    assert new_edges.relation_type.eq("reports_measurement").all()
    keys = []
    for finding in recovered.to_dict("records"):
        raw = json.loads(finding["raw_row_json"])
        keys.append(key(raw))
        source = sources[key(raw)]
        for field in ["clinical_endpoint", "outcome_measure", "condition_or_indication", "condition_or_population",
                      "population_or_subgroup", "population_model_category", "study_design", "study_design_category",
                      "assessment_timepoint", "comparator", "sample_size", "dose_or_regimen", "result_direction",
                      "effect_or_statistic", "finding_summary", "evidence_location", "evidence_locator"]:
            assert raw.get(field) == source.get(field), field
        assert finding["entity_label"] == source["clinical_endpoint"]
        assert not raw.get("entity_split_source_label")
    assert len(keys) == len(set(keys))
    # The controlled Pain projection already retains the final source row.
    assert not recovered.study_doi.eq(originals[-1]["study_doi"]).any()
    assert len(audit) == 1


@pytest.mark.parametrize("projections", [True, False])
def test_existing_endpoint_projection_is_not_duplicated_when_configured(tmp_path, projections):
    row = saved_rows()[-1]
    findings, edges, audit = build_source([row], tmp_path, projections=projections)
    if projections:
        assert not findings.entity_match_type.eq(MATCH).any()
        assert len(findings) == 1 and findings.iloc[0].entity_label == "Pain"
    else:
        assert len(findings) == 1 and findings.iloc[0].entity_match_type == MATCH
        assert findings.iloc[0].entity_label == row["clinical_endpoint"]


def test_normalization_cannot_supply_a_missing_native_measure(tmp_path, monkeypatch):
    row = saved_rows()[0]
    row["outcome_measure"] = ""
    original_normalizer = b.normalize_claim_metadata

    def infer_measure(value, domain):
        out = original_normalizer(value, domain)
        out["outcome_measure"] = "Inferred disability measure"
        return out

    monkeypatch.setattr(b, "normalize_claim_metadata", infer_measure)
    findings, _, audit = build_source([row], tmp_path)
    assert findings.empty
    assert len(audit) == 1


def test_family_history_exclusion_is_not_bypassed(tmp_path):
    row = saved_rows()[0]
    row.update(condition_or_indication="Family history of schizophrenia",
               graph_entity_label="Family history of schizophrenia")
    findings, _, audit = build_source([row], tmp_path)
    assert findings.empty
    assert "condition_context_not_graphable" in set(audit.normalization_status)


def test_mapping_contract_distinguishes_reported_measurement_from_scale():
    mapping = json.loads((Path(__file__).resolve().parents[1] / "schema/extraction_to_kg_mapping.json").read_text())
    assert mapping["relation_types"]["reports_measurement"]["to"] == "reported_measurement"
    assert mapping["relation_types"]["reports_outcome_scale"]["to"] == "outcome_scale"
