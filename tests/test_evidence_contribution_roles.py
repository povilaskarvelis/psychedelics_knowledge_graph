import pytest
from pipeline.kg.evidence_contribution_roles import admission_boundary, contribution_role, economic_projection_fields

@pytest.mark.parametrize("text,role", [
 ("Experts rated psychological flexibility as the most important proposed mechanism.", "expert_judgment"),
 ("MARRRS showed high internal consistency and significant convergent validity with QIDS scores. The abstract does not report symptom improvement.", "method_validation"),
 ("A reduction of 3.5 points on the QIDS score represented meaningful improvement anchored to a 1-point PGI change.", "measurement_definition"),
 ("In the decision-analytic model, expanded access was projected to gain 3 million QALYs while costing less.", "model_projection"),
])
def test_positive_same_item_roles(text, role):
 r={"finding_summary":text,"source_family":"primary"}
 assert contribution_role(r,"clinical_outcome")[0] == role
 assert admission_boundary(r,"clinical_outcome")["graph_admission_status"]=="paper_detail"

def test_template_comparison_is_not_administered_drug_effect():
 r={"compound_or_intervention":"Ketamine-induced thalamic dysconnectivity pattern (ketamine similarity coefficient)","finding_summary":"Greater pattern similarity was associated with hallucinations in schizophrenia."}
 assert admission_boundary(r,"clinical_outcome")["evidence_role"]=="reference_pattern_comparison"

@pytest.mark.parametrize("text",[
 "Ketamine reduced MADRS scores by 12 points compared with placebo.",
 "Depressive symptoms significantly decreased during treatment; the scale also showed high internal consistency.",
 "No significant reduction in symptoms was detected compared with placebo.",
 "Patients rated dissociation after ketamine as mild.",
 "Experts participated in a trial in which psilocybin reduced depressive symptoms.",
 "The study used a validated reliable depression scale to measure symptoms.",
 "Ketamine produced thalamic hyperconnectivity compared with placebo.",
])
def test_real_results_and_absence_of_metadata_do_not_imply_non_effect(text):
 assert admission_boundary({"finding_summary":text},"clinical_outcome")=={}

def test_explicit_roles_work_without_reparsing_prose():
 assert admission_boundary({"evidence_role":"expert_judgment"},"brain_system")["graph_admission_reason"]=="expert_judgment_not_measured_drug_effect"

def test_review_legitimately_synthesizes_previously_reported_results():
 assert admission_boundary({"source_family":"secondary_literature","source_contribution":"previously_reported"},"clinical_outcome")=={}

def test_title_alone_never_establishes_role():
 assert admission_boundary({"study_title":"Scale validation expert opinion and ketamine template"},"clinical_outcome")=={}

def test_cost_model_is_representable_as_a_model_in_real_world():
    r={'finding_summary':'In the decision-analytic model, MDMA was projected to gain 3 million QALYs while costing less.','outcome_measure':'Costs and QALYs'}
    f=economic_projection_fields(r,'clinical_outcome')
    assert f['domain']=='real_world_public_health'
    assert f['evidence_role']=='model_projection'
    assert admission_boundary({**r,**f},'real_world_public_health')=={}

def test_computational_neural_model_is_not_misread_as_patient_efficacy():
    assert admission_boundary({'evidence_role':'model_projection'},'brain_system')=={}
def test_null_treatment_contrast_in_validation_paper_is_preserved():
    from pipeline.kg.evidence_contribution_roles import admission_boundary
    row = {'finding_summary': 'By Day 28, the symptom-improvement structure was represented by a single factor in both treatment groups, with no detected difference in factor structure or significant treatment-arm effect on MADRS total or subscale outcomes.'}
    assert admission_boundary(row, 'clinical_outcome') == {}

def test_item_delphi_design_covers_passive_rating_wording():
    row={'study_design':'Two-round modified Delphi study using expert responses and importance ratings',
         'finding_summary':'Psychological flexibility received the highest mean importance rating among the proposed mechanisms.'}
    assert admission_boundary(row,'subjective_experience')['graph_admission_reason']=='expert_judgment_not_measured_drug_effect'

def test_expert_views_and_recommended_context_are_valid_in_their_own_domains():
    for domain in ['real_world_public_health','intervention_context']:
        assert admission_boundary({'evidence_role':'expert_judgment','finding_summary':'Experts recommended supportive preparation.'},domain)=={}

def test_mixed_original_trial_and_delphi_design_does_not_demote_actual_clinical_result():
    row={'study_design':'Randomized clinical trial with an expert Delphi substudy',
         'finding_summary':'Depression scores were reduced in the ketamine group compared with placebo.'}
    assert admission_boundary(row,'clinical_outcome')=={}
