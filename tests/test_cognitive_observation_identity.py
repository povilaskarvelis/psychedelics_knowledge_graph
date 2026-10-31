"""Complete measured behavior and full treatment comparisons retain their roles."""
from copy import deepcopy
import json
from pathlib import Path
import pandas as pd
import pytest
from pipeline.kg import build_evidence_tables as b
from pipeline.kg.cognitive_observation_identity import (
 explicit_cognitive_observation, cognitive_observation_signature, cognitive_measurement_recovery,
 cognitive_context_recovery, MEASUREMENT_MATCH, SUBJECT_MATCH, SUBJECT_REASON,
)


def observation(**changes):
 return {"domain":"cognitive_behavioral","source_type":"primary","source_item_type":"primary_item",
  "extraction_schema_version":"primary_cognitive_behavioral_v1","task_id":"task","source_item_index":1,
  "compound_or_exposure":"Ketamine versus electroconvulsive therapy (ECT)",
  "construct_or_behavior":"Delayed verbal recall","task_or_measure":"Delayed recall T-score",
  "construct_family":"cognition","study_design":"Randomized trial",
  "finding_summary":"Delayed recall decreased after ECT while the ketamine group changed little.",**changes}


@pytest.mark.parametrize("field",["compound_or_exposure","construct_or_behavior","task_or_measure","study_design","finding_summary"])
def test_missing_native_fields_do_not_qualify(field):
 row=observation(**{field:"not_reported"})
 assert not explicit_cognitive_observation(row)
 assert cognitive_measurement_recovery(row) is None
 assert cognitive_context_recovery(row) is None


@pytest.mark.parametrize("changes",[
 {"domain":"clinical_outcome"},{"source_type":"narrative_review"},{"source_item_type":"synthesis_result"},
 {"extraction_schema_version":"legacy"},{"entity_split_source_label":"Derived"},{"endpoint_label_source":"inferred"},
])
def test_only_intact_native_primary_observations_qualify(changes):
 assert not explicit_cognitive_observation(observation(**changes))


def test_generic_display_label_does_not_erase_a_measured_behavior():
 row=observation(construct_family="behavior",graph_construct_label="Sexual behavior",
  construct_or_behavior="Self-reported sexual encounter occurrence",task_or_measure="Interview questions about sexual encounters")
 original=deepcopy(row)
 proposal=cognitive_measurement_recovery(row)
 assert proposal["label"]=="Sexual behavior" and proposal["match_type"]==MEASUREMENT_MATCH
 assert row==original


def test_long_measurement_survives_without_inventing_a_short_construct():
 row=observation(construct_or_behavior="Postnatal motor activity following the drug challenge: "+"reported observation "*15,
                 graph_construct_label="",construct_family="behavior")
 assert cognitive_measurement_recovery(row)["label"]==row["construct_or_behavior"].strip()
 assert cognitive_measurement_recovery(observation(construct_family="not_reported")) is None


def test_comparison_is_kept_whole_without_atomic_attribution():
 row=observation();original=deepcopy(row)
 proposal=cognitive_context_recovery(row)
 assert proposal["label"]==row["compound_or_exposure"]
 assert proposal["focal_scope_label"]=="Ketamine"
 assert proposal["kind"]=="exposure_context"
 assert row==original


@pytest.mark.parametrize("exposure,finding",[
 ("Cannabidiol following repeated ketamine administration","Cannabidiol rescued ketamine-associated impairment."),
 ("Electroconvulsive therapy followed by ketamine","Ketamine was given after ECT."),
 ("MDD diagnosis compared with controls; ketamine was not administered","Ketamine was not administered."),
 ("Fluoxetine versus placebo","Unlike ketamine, fluoxetine improved performance."),
 ("Ketamine versus ECT","ECT impaired memory; no result for the other group was reported."),
])
def test_reference_or_absent_drug_cannot_supply_focal_scope(exposure,finding):
 assert cognitive_context_recovery(observation(compound_or_exposure=exposure,finding_summary=finding)) is None


def test_context_matching_uses_supplied_registry(tmp_path):
 path=tmp_path/"registry.json";path.write_text(json.dumps({"compounds":[{"label":"Ketamine","graph_scope":"out_of_scope"}]}))
 assert cognitive_context_recovery(observation(),path) is None


def test_source_signature_prevents_borrowing_eligibility_after_inference():
 row=observation()
 for field in ["task_id","source_item_index","compound_or_exposure","construct_or_behavior","task_or_measure","study_design","construct_family"]:
  assert cognitive_observation_signature(row)!=cognitive_observation_signature({**row,field:"changed"})


def saved_rows():
 return json.loads((Path(__file__).parent/"fixtures/cognitive_observation_saved_rows.json").read_text())


def test_saved_rows_keep_native_tasks_statistics_and_complete_exposures(tmp_path):
 rows=saved_rows();source=tmp_path/"rows.json";source.write_text(json.dumps(rows))
 b.build_tables(graph_sources={"routed_extractions":{"path":source,"domain":"routed","dataset":"routed","default_evidence_type":"primary_evidence","skip_audit":True}},out_dir=tmp_path/"tables",write_duckdb=False)
 f,e,a=[pd.read_parquet(tmp_path/f"tables/{n}.parquet").fillna("") for n in ["findings","evidence_edges","normalization_audit"]]
 recovered=f[f.compound_match_type.eq(SUBJECT_MATCH)|f.entity_match_type.eq(MEASUREMENT_MATCH)]
 assert len(recovered)==8
 assert recovered.graph_admission_status.eq("paper_detail").all()
 contexts=recovered[recovered.compound_match_type.eq(SUBJECT_MATCH)]
 assert contexts.graph_overview_subjects_json.eq("[]").all()
 assert contexts.graph_use_context_projections_json.eq("[]").all()
 key=lambda r:(r['task_id'],str(r['source_item_index']))
 sources={key(r):r for r in rows}
 for item in recovered.to_dict('records'):
  raw=json.loads(item['raw_row_json']);original=sources[key(raw)]
  for field in ["compound_or_exposure","construct_or_behavior","graph_construct_label","construct_family","task_or_measure",
    "behavioral_context","statistic_or_value","effect_or_statistic","finding_summary","comparator","assessment_timepoint",
    "population_or_species","sample_size","dose_or_regimen","evidence_location","evidence_locator"]:
   assert raw.get(field)==original.get(field),field
 assert e[e.finding_id.isin(recovered.finding_id)].graph_admission_status.eq("paper_detail").all()
 assert not recovered.study_doi.isin(["10.1038/npp.2008.227","10.1007/s12035-019-01831-2","10.1038/s41386-019-0591-5"]).any()


def test_recovered_context_never_produces_an_atomic_overview_subject():
 registry=b.registry_lookup(b.DEFAULT_REGISTRY_PATH)
 assert b.overview_graph_subjects(observation(graph_admission_reason=SUBJECT_REASON),{"label":"Ketamine","subject_kind":"atomic_compound"},registry)==[]
