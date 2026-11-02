"""Source-backed controls for optional metadata and named-scale boundaries."""
import copy
import json
from pathlib import Path
from unittest.mock import patch
import pytest
from pipeline.kg import build_evidence_tables as b
from pipeline.kg.convert_meta_analysis_v2_to_evidence_rows import convert_outputs


def converted(optional_value, *, flags=None, uncertainties=None, **item_fields):
    item = {**item_fields, "result_id":"R1", "result_role":"primary_synthesis", "importance_in_paper":"main",
            "primary_subject_area":"molecular_pathway_readout", "subject_areas":["molecular_pathway_readout"],
            "relationship_statement":"Ketamine non-responders showed no detected change in blood BDNF.",
            "intervention_or_exposure":"Ketamine", "population_or_system":"Adults with depression",
            "outcome_or_entity":"Change in blood BDNF", "outcome_measure":"BDNF concentration",
            "effect_estimate":{"metric":"SMD", "estimate":"0.05", "interval_lower":"-0.19", "interval_upper":"0.28", "p_value":"0.70"},
            "interpretation":{"finding_direction":"no_detected_effect"}, "heterogeneity":optional_value,
            "evidence_locators":[{"location":"abstract","locator":"Abstract","supporting_text":"SMD 0.05 [-0.19, 0.28], p=0.70"}],
            "extraction_uncertainties":uncertainties or []}
    output={"task_id":"test", "study_doi":"10.1/test", "status":"ok", "source_depth":"article_text",
            "qa_flags":flags if flags is not None else ["empty_optional_object:R1:heterogeneity"],
            "result":{"extraction_status":"extracted", "meta_analysis_overview":{}, "synthesis_results":[item]}}
    rows,_=convert_outputs([output],{"test":{"task_id":"test","paper_metadata":{}}})
    assert len(rows)==1
    return rows[0]


def test_empty_optional_heterogeneity_preserves_null_and_flag_without_review_hold():
    row=converted({})
    assert not row.get("needs_human_review", False)
    assert row["result_direction"]=="no_detected_effect"
    assert row["estimate_value"]=="0.05"
    assert row["meta_analysis_interval_lower"]=="-0.19"
    assert row["meta_analysis_interval_upper"]=="0.28"
    assert row["extraction_warnings"]=="empty_optional_object:R1:heterogeneity"
    assert json.loads(row["statistical_validation_recheck_json"])["nonblocking_optional_metadata_flags"]==["empty_optional_object:R1:heterogeneity"]


@pytest.mark.parametrize("value", [None, {"i_squared":"30%"}, ""])
def test_flag_not_ignored_when_source_optional_field_is_not_empty_object(value):
    assert converted(value)["needs_human_review"] is True


@pytest.mark.parametrize("note", [
    "Outcome-specific sample size is unavailable.",
    "The abstract does not report the numerical effect estimate, time-specific results, or comparator for suicidality.",
    "The abstract reports the day-1 CI as -1.15 to -0.26, whereas the full-text results report -1.15 to -0.25; the full-text value is used here.",
])
def test_note_about_unreported_metadata_does_not_hold_the_result(note):
    row=converted({},uncertainties=[note])
    assert not row.get("needs_human_review", False)
    assert note in row["notes"]


@pytest.mark.parametrize("note", [
    "The interval upper endpoint conflicts between the prose (-0.042) and the table (0.042); it is not resolved here.",
    "The point estimate is 1.87, while the reported interval (-4.49 to 0.74) does not include the point estimate as written.",
    "The abstract's stated direction is not readily reconciled with the reported OR without information about outcome coding.",
    "The direction convention for the standardized mean difference is not explicitly defined.",
    "The abstract does not specify the RR reference-group direction or the adverse-event assessment window.",
    "Table 2 contains malformed point-estimate text, so subgroup estimates are not assigned.",
])
def test_note_reporting_a_conflict_or_unstated_direction_keeps_review_hold(note):
    assert converted({},uncertainties=[note])["needs_human_review"] is True


def test_empty_optional_evidence_size_and_paraphrased_quote_do_not_hold_the_result():
    flags=["empty_optional_object:R1:evidence_size","nonverbatim_supporting_text:R1:1"]
    row=converted({"i_squared":"0%"},flags=flags,evidence_size={})
    assert not row.get("needs_human_review", False)
    assert row["extraction_warnings"]==" | ".join(flags)
    recheck=json.loads(row["statistical_validation_recheck_json"])
    assert recheck["nonblocking_optional_metadata_flags"]==["empty_optional_object:R1:evidence_size"]
    assert recheck["nonblocking_quote_flags"]==["nonverbatim_supporting_text:R1:1"]


@pytest.mark.parametrize("other", ["contradictory_significance_wording:R1", "supports_with_p_above_0_05:R1", "uncertain_effect_direction:R1"])
def test_other_result_qa_still_requires_review(other):
    row=converted({},flags=["empty_optional_object:R1:heterogeneity",other])
    assert row["needs_human_review"] is True
    assert other in row["extraction_warnings"]


def test_flagged_optional_object_that_is_not_empty_still_requires_review():
    assert converted({},flags=["empty_optional_object:R1:evidence_size"],evidence_size={"study_count":"4"})["needs_human_review"] is True


def source_scale_row():
    return json.loads((Path(__file__).parent/"fixtures/meta_named_scale_source_case.json").read_text())


def test_named_scale_actual_builder_path_preserves_literal_measurement_and_numbers():
    source=source_scale_row();original=copy.deepcopy(source);tables={}
    with patch.object(b,"rows_for_source",return_value=[source]), \
         patch.object(b,"write_parquet",side_effect=lambda df,path:tables.update({path.stem:df})), \
         patch.object(b,"write_json"),patch.object(Path,"mkdir"):
        b.build_tables(graph_sources={"routed_extractions":{"domain":"","dataset":"routed","default_evidence_type":"secondary_literature","skip_audit":True}},out_dir=Path("/__readonly_named_scale_test__"),write_duckdb=False)
    row=tables["findings"].iloc[0].to_dict()
    assert len(tables["findings"])==1
    assert row["graph_entity_label"]==source["primary_outcome"]
    assert row["kg_entity_kind_override"]=="reported_measurement"
    assert row["graph_admission_status"]=="paper_detail"
    assert row["graph_admission_reason"]=="named_scale_requires_faithful_construct_mapping"
    for field in ["effect_size","p_value","confidence_interval","support","outcome_measure"]:
        assert row[field]==source[field]
    assert source==original


@pytest.mark.parametrize("endpoint,measure",[("Mystical experience","MEQ30"),("Self-transcendence","MEQ"),("DTS","DTS")])
def test_background_scale_or_bare_abbreviation_does_not_change_measured_construct(endpoint,measure):
    row=source_scale_row();row.update(primary_outcome=endpoint,raw_entity_label=endpoint,graph_entity_label=endpoint,outcome_measure=measure,support="Background: Death Transcendence Scale was used by an earlier study.")
    assert b.literal_named_subjective_measure(row)==""
    normalized=b.normalize_claim_metadata(row,"subjective_experience")
    assert normalized.get("graph_admission_reason")!="named_scale_requires_faithful_construct_mapping"
    if measure.startswith("MEQ"):
        assert normalized["graph_entity_label"]=="Mystical-type experience"


def test_named_scale_in_measure_field_keeps_literal_scale():
    row=source_scale_row();row.update(primary_outcome="Death transcendence",raw_entity_label="Death transcendence",graph_entity_label="Death transcendence",outcome_measure="Death Transcendence Scale")
    normalized=b.normalize_claim_metadata(row,"subjective_experience")
    assert normalized["graph_entity_label"]=="Death Transcendence Scale"
    assert normalized["graph_admission_status"]=="paper_detail"
