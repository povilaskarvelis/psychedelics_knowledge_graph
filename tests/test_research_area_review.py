import json

import pandas as pd
import pytest

from pipeline.kg.build_evidence_tables import (
    apply_psychosis_family_boundary,
    build_tables,
    graph_admission_decision,
    normalize_claim_metadata,
)
from pipeline.kg.research_area_review import (
    annotate_findings,
    apply_boundaries,
    review_reasons,
)
from pipeline.kg.research_area_adjudication import (
    apply_adjudications,
    adjudicate_queue,
)
from pipeline.kg.research_area_second_pass import second_pass_decide
from pipeline.validate.apply_research_area_release_qa import (
    _expanded_group_ids,
    _stable_sample,
)


def test_negated_population_does_not_turn_remission_into_psychosis_risk():
    row = {
        "domain": "clinical_outcome",
        "graph_entity_label": "40-year-old male with severe depressive episode without psychotic symptoms",
        "support": "The patient achieved near-complete remission of depressive symptoms.",
    }
    result = normalize_claim_metadata(row, "clinical_outcome")
    assert result["domain"] == "clinical_outcome"
    assert result.get("kg_entity_kind_override") != "safety_adverse_event"
    assert "psychosis_population_or_negation_not_safety" in json.loads(
        result["research_area_rule_actions_json"]
    )
    assert (
        json.loads(result["research_area_input_json"])["graph_entity_label"]
        == row["graph_entity_label"]
    )
    assert "research_area_input_json" not in row
    twice = normalize_claim_metadata(result, "clinical_outcome")
    assert twice["research_area_input_json"] == result["research_area_input_json"]
    assert (
        twice["research_area_rule_actions_json"]
        == result["research_area_rule_actions_json"]
    )


def test_baseline_negation_does_not_hide_new_psychosis():
    row, domain = apply_psychosis_family_boundary(
        {
            "graph_entity_label": "Patient without psychotic symptoms at baseline",
            "support": "The patient developed psychosis after administration.",
        },
        "clinical_outcome",
    )
    assert domain == "safety_tolerability"
    assert row["graph_entity_label"] == "Psychosis risk"


@pytest.mark.parametrize(
    "support,expected",
    [
        (
            "Transient psychotomimetic symptoms were measured using PANSS.",
            "cognitive_behavioral",
        ),
        (
            "New psychotic symptoms measured using PANSS required hospitalization.",
            "safety_tolerability",
        ),
        (
            "Persistent psychosis-like symptoms required hospitalization.",
            "safety_tolerability",
        ),
    ],
)
def test_model_measure_alone_does_not_override_serious_psychosis(support, expected):
    _, domain = apply_psychosis_family_boundary(
        {
            "graph_entity_label": "Psychosis-like effects",
            "support": support,
        },
        "safety_tolerability",
    )
    assert domain == expected


@pytest.mark.parametrize(
    "support",
    [
        "Depressive symptoms worsened during treatment.",
        "Ketamine did not improve depression.",
        "Mania scores decreased in patients being treated for mania.",
        "Ketamine improved depression without inducing mania.",
    ],
)
def test_negative_or_mixed_therapeutic_results_are_not_forced_into_safety(support):
    out = apply_boundaries(
        {
            "domain": "clinical_outcome",
            "support": support,
            "graph_entity_label": "Major depressive disorder",
        }
    )
    assert out["domain"] == "clinical_outcome"


def test_explicit_safety_measure_routes_and_preserves_null_result():
    row = {
        "domain": "clinical_outcome",
        "graph_entity_label": "Treatment-resistant depression",
        "clinical_endpoint": "Adverse events",
        "support": "No adverse events occurred.",
        "result_direction": "no_detected_effect",
    }
    out = normalize_claim_metadata(row, row["domain"])
    assert out["domain"] == "safety_tolerability"
    assert out["kg_entity_kind_override"] == "safety_adverse_event"
    assert out["result_direction"] == "no_detected_effect"


def test_parkinsons_precipitation_is_safety_but_retracted_statement_is_review_only():
    source = {
        "domain": "clinical_outcome",
        "graph_entity_label": "Parkinson's disease",
        "support": "Chronic MDMA use was identified as a likely precipitating factor for the development of early onset Parkinson's disease.",
    }
    assert apply_boundaries(source)["domain"] == "safety_tolerability"
    source["support"] = "Claims that MDMA causes Parkinson's disease were retracted."
    out = apply_boundaries(source)
    assert out["domain"] == "clinical_outcome"
    assert "retracted_claim_context" in review_reasons(out)


@pytest.mark.parametrize(
    "row,expected",
    [
        (
            {
                "domain": "clinical_outcome",
                "kg_entity_kind_override": "safety_adverse_event",
                "entity_label": "Parkinson's disease",
                "support": "Chronic MDMA use was associated with early-onset Parkinson's disease.",
            },
            ("confirmed_current", "confirm_safety_endpoint_projection"),
        ),
        (
            {
                "domain": "safety_tolerability",
                "kg_entity_kind_override": "safety_adverse_event",
                "entity_label": "Suicidality risk",
                "support": "Ketamine produced rapid improvement in depressive symptoms in treatment-refractory depression.",
            },
            ("corrected", "hold_therapeutic_text_in_safety_projection"),
        ),
        (
            {
                "domain": "clinical_outcome",
                "kg_entity_kind_override": "condition_indication",
                "entity_label": "Low mood and depressive symptoms",
                "support": "There were no statistically significant differences in PHQ-9 scores between groups.",
            },
            ("confirmed_current", "confirm_therapeutic_condition_outcome_projection"),
        ),
        (
            {
                "domain": "clinical_outcome",
                "kg_entity_kind_override": "condition_indication",
                "entity_label": "Distress associated with life-threatening disease",
                "support": "The review examines major research studies regarding psychedelic drugs in terminal cancer patients.",
            },
            ("unresolved", "needs_source_level_review"),
        ),
        (
            {
                "domain": "cognitive_behavioral",
                "kg_entity_kind_override": "condition_indication",
                "entity_label": "Opioid use disorder",
                "support": "Ketamine dose-dependently suppressed morphine withdrawal signs in dependent rats.",
            },
            ("confirmed_current", "confirm_therapeutic_condition_outcome_projection"),
        ),
        (
            {
                "domain": "safety_tolerability",
                "kg_entity_kind_override": "safety_adverse_event",
                "entity_label": "Psychosis risk",
                "support": "Hallucinogen-induced states are a useful experimental model for acute psychotic stages.",
            },
            ("corrected", "hold_model_or_comparison_projection"),
        ),
    ],
)
def test_second_pass_routes_area_mismatches_and_keeps_contextual_rows_unresolved(
    row, expected
):
    status, action, _ = second_pass_decide(row)
    assert (status, action) == expected


def test_release_qa_sample_is_stable_and_group_overrides_expand():
    decisions = pd.DataFrame(
        [
            {
                "finding_id": f"finding:{index}",
                "second_pass_status": "confirmed_current" if index < 4 else "corrected",
                "second_pass_action": "confirm" if index < 4 else "hold",
                "second_pass_group_key": "shared" if index >= 4 else f"group:{index}",
            }
            for index in range(6)
        ]
    )
    first = _stable_sample(decisions, {"confirm": 2})
    second = _stable_sample(decisions.sample(frac=1, random_state=7), {"confirm": 2})
    assert list(first["finding_id"]) == list(second["finding_id"])
    assert _expanded_group_ids(decisions, {"finding:4"}) == {
        "finding:4",
        "finding:5",
    }


def test_uropathy_management_is_held_not_invented_as_drug_efficacy():
    row = {
        "domain": "clinical_outcome",
        "kg_entity_kind_override": "condition_indication",
        "compound": "Ketamine",
        "graph_entity_label": "Ketamine-associated uropathy",
        "support": "Surgery improved bladder capacity.",
    }
    assert graph_admission_decision(row) == (
        "paper_detail",
        "exposure_caused_uropathy_not_ketamine_indication",
    )
    assert "disease_may_be_exposure_consequence" in review_reasons(row)
    row.update(compound="Psilocybin", graph_entity_label="Chronic pain")
    assert graph_admission_decision(row)[0] == "main_graph"


def test_flags_are_advisory_and_cross_area_duplicates_have_provenance():
    rows = [
        dict(
            finding_id=str(i),
            study_doi="10.1/example",
            compound="Ketamine",
            support="Suicidal ideation resolved.",
            graph_admission_status="main_graph",
            kg_entity_kind_override=kind,
        )
        for i, kind in enumerate(["condition_indication", "safety_adverse_event"])
    ]
    queue, summary = annotate_findings(rows)
    assert len(queue) == summary["flagged_rows"] == 2
    assert all(r["graph_admission_status"] == "main_graph" for r in rows)
    assert all(r["research_area_review_status"] == "pending" for r in rows)
    assert all(
        r["research_area_classification_origin"] == "deterministic" for r in rows
    )
    assert all(
        "same_statement_in_clinical_and_safety"
        in json.loads(r["research_area_review_reasons_json"])
        for r in rows
    )
    old_hash = rows[0]["research_area_evidence_fingerprint"]
    rows[0]["supporting_quote"] = "A changed source passage"
    annotate_findings(rows)
    assert rows[0]["research_area_evidence_fingerprint"] != old_hash


def test_postmortem_pk_is_not_flagged_just_for_fatality():
    rows = [
        {
            "kg_entity_kind_override": "pharmacokinetic_parameter",
            "support": "Postmortem MDMA concentration was measured in a fatal intoxication.",
        }
    ]
    queue, summary = annotate_findings(rows)
    assert not queue
    assert rows[0]["research_area_review_status"] == "not_flagged"
    assert summary["not_flagged_rows"] == 1


def test_build_persists_review_queue_and_original_automatic_input(tmp_path):
    source = tmp_path / "rows.json"
    source.write_text(
        json.dumps(
            [
                {
                    "study_doi": "10.1000/area-review",
                    "compound": "MDMA",
                    "domain": "clinical_outcome",
                    "graph_entity_label": "Parkinson's disease",
                    "support": "Claims that MDMA causes Parkinson's disease were retracted.",
                }
            ]
        )
    )
    out = tmp_path / "kg"
    manifest = build_tables(
        graph_sources={
            "routed_extractions": {
                "path": source,
                "domain": "routed",
                "dataset": "routed",
                "default_evidence_type": "primary_evidence",
                "skip_audit": True,
            }
        },
        out_dir=out,
        write_duckdb=False,
    )
    findings = pd.read_parquet(out / "findings.parquet")
    queue = pd.read_parquet(out / "research_area_review_queue.parquet")
    assert len(findings) == len(queue) == 1
    assert manifest["research_area_review"]["flagged_rows"] == 1
    assert queue.iloc[0]["finding_id"] == findings.iloc[0]["finding_id"]
    assert "retracted_claim_context" in json.loads(
        queue.iloc[0]["research_area_review_reasons_json"]
    )
    assert (
        json.loads(findings.iloc[0]["research_area_input_json"])["domain"]
        == "clinical_outcome"
    )


def test_unresolved_population_anchor_remains_in_review_queue_even_if_normalization_fails():
    from pipeline.kg.research_area_review import build_review_queue

    raw = normalize_claim_metadata(
        {
            "domain": "clinical_outcome",
            "graph_entity_label": "Patient with depression without psychotic symptoms",
            "support": "The patient experienced psychological improvement.",
        },
        "clinical_outcome",
    )
    assert raw["graph_admission_status"] == "paper_detail"
    queue, summary = build_review_queue(
        [],
        [
            {
                "study_doi": "10.1000/unmapped",
                "entity_label": raw["graph_entity_label"],
                "normalization_status": "entity_unmapped",
                "raw_row_json": json.dumps(raw),
            }
        ],
    )
    assert len(queue) == 1
    assert queue[0]["record_type"] == "normalization_audit"
    assert queue[0]["research_area_review_status"] == "pending"
    assert "psychosis_population_anchor_without_resolved_endpoint" in json.loads(
        queue[0]["research_area_review_reasons_json"]
    )
    assert summary["flagged_record_types"] == {"normalization_audit": 1}


def test_explicit_endpoint_prevents_patient_comorbidity_becoming_an_extra_condition():
    raw = {
        "domain": "clinical_outcome",
        "graph_entity_label": "Male with severe depression without psychotic symptoms and active suicidal ideation",
        "clinical_endpoint": "Depression severity",
        "support": "The patient achieved remission of depression.",
    }
    result = normalize_claim_metadata(raw, raw["domain"])
    assert result["graph_entity_label"] == "Low mood & depressive symptoms"
    assert result["kg_entity_kind_override"] == "symptom_problem"


def test_comparison_does_not_count_missing_or_held_rows_as_rerouting(tmp_path):
    from pipeline.validate.evaluate_research_area_routing import evaluate

    audit = pd.DataFrame(
        [
            {
                "finding_id": str(i),
                "study_doi": f"10.1000/{i}",
                "compound": "MDMA",
                "support": "A saved finding.",
                "entity_label": "Parkinson disease",
                "kg_entity_kind_override": "condition_indication",
                "category": "safety_in_conditions",
            }
            for i in range(3)
        ]
    )
    audit.to_csv(tmp_path / "audit.csv", index=False)
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    row = audit.iloc[0].to_dict()
    row.update(
        domain="clinical_outcome",
        graph_admission_status="paper_detail",
        graph_admission_reason="held",
        research_area_review_status="pending",
        research_area_review_reasons_json='["needs_context"]',
    )
    pd.DataFrame([row]).to_parquet(candidate / "findings.parquet", index=False)
    rejected = audit.iloc[1].to_dict()
    rejected.update(record_type="normalization_audit")
    pd.DataFrame([rejected]).to_parquet(
        candidate / "research_area_review_queue.parquet", index=False
    )
    summary = evaluate(tmp_path / "audit.csv", candidate, tmp_path / "result")
    assert summary["status_counts"] == {
        "old_projection_held_for_detail": 1,
        "normalization_review_pending": 1,
        "no_exact_evidence_match": 1,
    }


def test_absence_of_persistent_psychosis_does_not_override_transient_model_effect():
    _, domain = apply_psychosis_family_boundary(
        {
            "graph_entity_label": "Psychosis-like effects",
            "support": "Ketamine was associated with transient psychotomimetic effects, but no persistent psychosis or affective switches.",
        },
        "safety_tolerability",
    )
    assert domain == "cognitive_behavioral"


def test_adjudication_holds_only_high_confidence_exposure_projection():
    queue = pd.DataFrame(
        [
            {
                "finding_id": "finding:1",
                "record_type": "finding",
                "study_doi": "10.1000/example",
                "compound": "MDMA",
                "domain": "clinical_outcome",
                "entity_label": "Parkinson's disease",
                "kg_entity_kind_override": "condition_indication",
                "graph_admission_status": "main_graph",
                "support": "Chronic MDMA use was a likely precipitating factor for early-onset Parkinson's disease.",
                "research_area_evidence_fingerprint": "fp1",
                "research_area_review_reasons_json": '["clinical_safety_role_ambiguity"]',
            },
            {
                "finding_id": "",
                "record_type": "normalization_audit",
                "study_doi": "10.1000/unmapped",
                "compound": "MDMA",
                "domain": "clinical_outcome",
                "entity_label": "Parkinson's disease",
                "kg_entity_kind_override": "condition_indication",
                "graph_admission_status": "normalization_audit",
                "support": "The source relationship was not normalized.",
                "research_area_evidence_fingerprint": "fp2",
                "research_area_review_reasons_json": '["clinical_safety_role_ambiguity"]',
            },
        ]
    )
    adjudications = adjudicate_queue(queue, reviewed_at="2026-09-06")
    assert len(adjudications) == 2
    assert adjudications.iloc[0]["adjudication_status"] == "unresolved"
    assert adjudications.iloc[1]["adjudication_status"] == "unresolved"

    # The high-confidence audit is what authorizes the graph hold; the queue
    # flag alone remains unresolved.
    audit = pd.DataFrame(
        [
            {
                "finding_id": "finding:1",
                "study_doi": "10.1000/example",
                "compound": "MDMA",
                "entity_label": "Parkinson's disease",
                "kg_entity_kind_override": "condition_indication",
                "support": queue.iloc[0]["support"],
                "category": "safety_in_conditions",
                "rationale": "Exposure harm is not a treatment indication.",
            }
        ]
    )
    adjudications = adjudicate_queue(queue, audit_df=audit, reviewed_at="2026-09-06")
    assert adjudications.iloc[0]["adjudication_status"] == "corrected"
    assert adjudications.iloc[0]["adjudication_action"] == "hold_legacy_high_confidence_projection"


def test_apply_adjudications_removes_held_edge_and_preserves_unresolved_row():
    findings = pd.DataFrame(
        [
            {"finding_id": "finding:1", "graph_admission_status": "main_graph", "graph_admission_reason": "semantically_complete"},
            {"finding_id": "finding:2", "graph_admission_status": "main_graph", "graph_admission_reason": "semantically_complete"},
        ]
    )
    edges = pd.DataFrame(
        [
            {"finding_id": "finding:1", "evidence_id": "e1"},
            {"finding_id": "finding:2", "evidence_id": "e2"},
        ]
    )
    adjudications = pd.DataFrame(
        [
            {
                "finding_id": "finding:1",
                "adjudication_id": "a1",
                "adjudication_status": "corrected",
                "adjudication_action": "hold_disease_model_projection",
                "adjudication_rationale": "model context",
                "reviewed_at": "2026-09-06",
                "reviewer": "deterministic_adjudication_v1",
            },
            {
                "finding_id": "finding:2",
                "adjudication_id": "a2",
                "adjudication_status": "unresolved",
                "adjudication_action": "manual_semantic_review_required",
                "adjudication_rationale": "needs review",
                "reviewed_at": "2026-09-06",
                "reviewer": "deterministic_adjudication_v1",
            },
        ]
    )
    updated_findings, updated_edges, summary = apply_adjudications(findings, edges, adjudications)
    assert len(updated_edges) == 1
    assert updated_edges.iloc[0]["finding_id"] == "finding:2"
    held = updated_findings.iloc[0]
    assert held["graph_admission_status"] == "paper_detail"
    assert held["research_area_classification_origin"] == "agent_reviewed"
    assert updated_findings.iloc[1]["graph_admission_status"] == "main_graph"
    assert summary["held_edges"] == 1
