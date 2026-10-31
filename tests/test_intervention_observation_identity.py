"""Detailed treatment context is evidence, not a component-specific effect."""
from copy import deepcopy
import json
from pathlib import Path

import pandas as pd
import pytest

from pipeline.kg import build_evidence_tables as b
from pipeline.kg.intervention_observation_identity import (
    intervention_source_contract, intervention_source_signature, intervention_observation_recovery,
)


def observation(**changes):
    return {"domain": "intervention_context", "source_item_type": "primary_item", "source_type": "primary",
            "context_component": "Music and structured preparation accompanying the full treatment package",
            "component_type": "music; preparation", "study_design": "Randomized trial",
            "relationship_to_outcome_or_safety": "The package improved symptoms; components were not isolated.",
            "finding_summary": "The combined treatment differed from the comparator.", **changes}


@pytest.mark.parametrize("length", [79, 81, 300])
def test_complete_primary_descriptions_do_not_depend_on_display_length(length):
    label = "Music " + "x" * (length - len("Music "))
    row = observation(context_component=label)
    original = deepcopy(row)
    recovered = intervention_observation_recovery(row, label, "Music")
    assert recovered["label"] == label
    assert recovered["reason"] == "complete_context_observation_not_individual_component_effect"
    assert row == original


@pytest.mark.parametrize("field", ["context_component", "component_type", "study_design",
                                   "relationship_to_outcome_or_safety", "finding_summary"])
def test_missing_required_primary_fields_remain_held(field):
    assert not intervention_source_contract(observation(**{field: "not_reported"}))


@pytest.mark.parametrize("changes", [
    {"domain": "clinical_outcome"}, {"source_type": "review"},
    {"source_item_type": "synthesis_result"}, {"source_item_type": "review_relationship"},
])
def test_other_contracts_cannot_be_treated_as_primary_context(changes):
    assert not intervention_source_contract(observation(**changes))


def test_reviews_require_the_explicit_coverage_contract_and_a_known_length_block():
    row = observation(source_item_type="review_relationship", source_type="narrative_review",
                      context_component="Preparation " + "x" * 100,
                      coverage_type="methodological_contribution", evidence_locator="Discussion, paragraph 2")
    assert intervention_source_contract(row) == "long_review_coverage"
    result = intervention_observation_recovery(row, row["context_component"], "Preparation")
    assert result["reason"] == "review_context_coverage_not_observed_component_effect"
    assert intervention_observation_recovery(row, row["context_component"], "") is None
    assert not intervention_source_contract({**row, "context_component": "Psychedelic therapy"})
    assert not intervention_source_contract({**row, "coverage_type": "uncertain"})
    assert not intervention_source_contract({**row, "evidence_locator": "not_reported"})


def test_source_identity_and_split_contexts_cannot_share_eligibility():
    row = observation(task_id="task", source_item_index=1)
    for field, value in [("task_id", "other"), ("source_item_index", 2), ("context_component", "Music")]:
        assert intervention_source_signature(row) != intervention_source_signature({**row, field: value})
    assert intervention_observation_recovery(row, "Music", "Music") is None


def build_source(rows, tmp_path):
    path = tmp_path / "source.json"
    path.write_text(json.dumps(rows))
    b.build_tables(out_dir=tmp_path / "tables", write_duckdb=False, graph_sources={
        "routed_extractions": {"path": path, "domain": "routed", "dataset": "routed",
                               "default_evidence_type": "primary_evidence", "skip_audit": True},
    })
    return (pd.read_parquet(tmp_path / "tables/findings.parquet").fillna(""),
            pd.read_parquet(tmp_path / "tables/normalization_audit.parquet").fillna(""))


def saved_rows():
    return json.loads((Path(__file__).parent / "fixtures/intervention_observation_saved_rows.json").read_text())


def test_saved_observations_keep_complete_packages_statistics_and_source_roles(tmp_path):
    originals = saved_rows()
    key = lambda r: (r["study_doi"], str(r["source_item_index"]), r["source_item_type"])
    sources = {key(r): r for r in originals}
    findings, audit = build_source(originals, tmp_path)
    assert len(findings) == 9 and len(audit) == 1
    assert findings.graph_admission_status.eq("paper_detail").all()
    assert findings.graph_parent_label.eq("").all()
    keys = []
    for finding in findings.to_dict("records"):
        raw = json.loads(finding["raw_row_json"])
        keys.append(key(raw))
        source = sources[key(raw)]
        for field in ["context_component", "component_type", "relationship_to_outcome_or_safety",
                      "study_design", "delivery_format", "dose_or_session_context", "timepoint_or_phase",
                      "finding_summary", "effect_or_statistic", "population_or_setting", "sample_size",
                      "evidence_location", "evidence_locator", "coverage_type", "source_item_type", "source_type"]:
            assert raw.get(field) == source.get(field), field
        assert not raw.get("entity_split_source_label")
        assert finding["entity_label"] == source["context_component"]
    assert len(keys) == len(set(keys))
    review = findings[findings.entity_match_type.eq("long_review_context_coverage_detail_only")]
    assert len(review) == 1
    assert review.iloc[0].graph_admission_reason != "semantically_complete"


def test_missing_saved_primary_type_is_not_recovered_from_result_prose(tmp_path):
    row = next(r for r in saved_rows() if r["study_doi"] == "10.1001/jamapsychiatry.2020.3285")
    row.pop("component_type")
    findings, audit = build_source([row], tmp_path)
    assert findings.empty and len(audit) == 1


def test_explicit_metadata_exclusions_are_not_bypassed(tmp_path):
    row = next(r for r in saved_rows() if r["study_doi"] == "10.1001/jamapsychiatry.2020.3285")
    row.update(context_component="Intravenous infusion rate and infusion duration", component_type="Dosing regimen",
               graph_entity_label="Intravenous infusion rate and infusion duration")
    findings, audit = build_source([row], tmp_path)
    assert findings.empty
    assert audit.normalization_status.eq("intervention_context_metadata_not_graphable").all()
