import json
from pathlib import Path

import pandas as pd

from pipeline.kg.audit_saved_extraction_coverage import audit, output_objects, paper_disposition
from pipeline.kg.graph_view_contract import record_matches_graph_view


def test_explicit_behavioral_constructs_have_a_view_without_becoming_cognition():
    for label in ("Sexual behavior", "Stereotyped behavior"):
        row = {"entity_kind": "cognitive_behavioral_construct", "entity_label": label}
        assert record_matches_graph_view(row, "behavioral_effect")
        assert not record_matches_graph_view(row, "cognitive_behavioral_construct")
    assert not record_matches_graph_view({"entity_kind": "subjective_experience_construct", "entity_label": "Sexual behavior"}, "behavioral_effect")


def test_guidelines_and_review_relationships_count_as_objects():
    assert len(output_objects({"result": {"recommendation_items": [{"recommendation": "X"}]}})) == 1
    assert len(output_objects({"result": {"relationships": [{"item_id": "R1"}]}})) == 1
    assert len(output_objects({"result": {"synthesis_results": [{"result_id": "R1"}]}})) == 1
    assert output_objects({"result": {"extraction_status": "not_relevant"}}) == []


def test_paper_dispositions_do_not_confuse_empty_tasks_with_absent_papers():
    assert paper_disposition(2, 1, 3) == "main_graph"
    assert paper_disposition(2, 0, 3) == "detail_only"
    assert paper_disposition(0, 0, 3) == "audit_only"
    assert paper_disposition(0, 0, 0) == "no_converted_rows"


def test_full_audit_preserves_task_paper_area_and_hold_denominators(tmp_path: Path):
    release = tmp_path / "release"
    inp = release / "inputs"
    inp.mkdir(parents=True)
    kg = tmp_path / "kg"
    kg.mkdir()
    (inp / "doi_alias_registry.json").write_text('{"aliases": []}')
    (release / "selected_dois.txt").write_text("10.1/a\n10.1/b\n10.1/c\n10.1/d\n")
    outputs = {
        "primary": [
            {"study_doi": "10.1/a", "task_id": "a1", "prompt_profile": "primary_target", "status": "ok", "result": {"items": [], "extraction_status": "not_relevant"}},
            {"study_doi": "10.1/a", "task_id": "a2", "prompt_profile": "primary_readout", "status": "ok", "result": {"items": [{"x": 1}], "extraction_status": "extracted"}},
            {"study_doi": "10.1/b", "task_id": "b", "status": "ok", "result": {"recommendation_items": [{"x": 1}]}},
        ],
        "review": [{"study_doi": "10.1/c", "task_id": "c", "status": "ok", "result": {"relationships": [{"x": 1}]}}],
        "meta": [{"study_doi": "10.1/d", "task_id": "d", "status": "ok", "result": {"synthesis_results": [], "extraction_status": "no_extractable_synthesis_result"}}],
    }
    for family, rows in outputs.items():
        for kind, records in [("outputs", rows), ("tasks", [{"study_doi": r["study_doi"], "task_id": r["task_id"]} for r in rows])]:
            (inp / f"{family}_{kind}.jsonl").write_text("".join(json.dumps(r) + "\n" for r in records))
    pd.DataFrame([
        {"study_doi": "10.1/a", "domain": "molecular_pathway_readout", "graph_admission_status": "main_graph", "graph_admission_reason": "complete"},
        {"study_doi": "10.1/b", "domain": "general", "graph_admission_status": "paper_detail", "graph_admission_reason": "generic"},
    ]).to_parquet(kg / "findings.parquet")
    pd.DataFrame([{"study_doi": "10.1/c", "domain": "brain_system", "normalization_status": "entity_unmapped"}]).to_parquet(kg / "normalization_audit.parquet")
    pd.DataFrame([
        {"study_doi": "10.1/a", "domain": "molecular_pathway_readout", "entity_kind": "biomarker_readout", "entity_label": "Expression", "graph_admission_status": "main_graph", "access_level": "abstract_only"},
        {"study_doi": "10.1/b", "domain": "general", "entity_kind": "generic_measurement", "entity_label": "Unspecified", "graph_admission_status": "paper_detail", "access_level": "article_text"},
    ]).to_parquet(kg / "evidence_edges.parquet")
    out = tmp_path / "audit"
    result = audit(release, kg, out)
    assert result["reports"] == 4 and result["tasks"] == 5 and result["objects"] == 3
    assert result["paper_dispositions"] == {"main_graph": 1, "detail_only": 1, "audit_only": 1, "no_converted_rows": 1}
    assert result["task_join_issues"] == {"missing": [], "duplicates": [], "identity_conflicts": []}
    areas = json.loads((out / "area_family_counts.json").read_text())
    assert len(areas) == 30
    assert next(x for x in areas if x["area"] == "pathway_readout" and x["response_family"] == "primary")["reports_with_area_evidence"] == 1
    assert next(x for x in areas if x["area"] == "target_system" and x["response_family"] == "primary")["reports_with_area_evidence"] == 0
    papers = [json.loads(x) for x in (out / "papers.jsonl").read_text().splitlines()]
    assert papers[0]["empty_tasks"] == 1 and papers[0]["disposition"] == "main_graph"
