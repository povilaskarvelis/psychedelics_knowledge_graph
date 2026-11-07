"""Mappable findings reach the overview without changing what they state.

Each rule here came from the 1 November normalization review
(docs/normalization_review_2026-11-01.md): a registered condition named by a
symptom-typed outcome, review statements typed by role rather than by the
domain Luna declared, outcomes dropped when their label did not match, primary
and review class subjects treated differently, and dashes, plurals, spellings
and abbreviations that hid an existing node.
"""
import json

import pandas as pd
import pytest

from pipeline.kg import build_evidence_tables as b
from pipeline.kg.review_statement_attribution import statement_contrasts_drugs


@pytest.fixture(scope="module")
def registry():
    return b.registry_lookup(b.DEFAULT_REGISTRY_PATH)


@pytest.fixture(scope="module")
def vocabulary():
    return b.node_vocabulary_lookup()


REVIEW = {"source_item_type": "review_relationship", "evidence_type": "secondary_literature",
          "paper_assessment_route": "secondary_literature"}


@pytest.mark.parametrize("label,condition", [
    ("PTSD symptoms", "Post-traumatic stress disorder"),
    ("Symptoms of OCD", "Obsessive-compulsive disorder"),
    ("Tobacco use disorder", "Tobacco use disorder"),
    ("Post-traumatic stress symptoms", "Post-traumatic stress disorder"),
])
def test_symptom_outcome_naming_a_registered_condition_reaches_the_condition(label, condition, registry):
    match = b.match_registry_entity(label, "symptom_problem", registry, REVIEW)
    assert (match["kind"], match["label"]) == ("condition_indication", condition)


@pytest.mark.parametrize("label", [
    "depressive symptoms", "Anxiety symptoms", "Fatigue", "Depression-like behavior",
    "family history of alcohol use disorder",
])
def test_broad_symptom_or_contextual_wording_stays_a_symptom(label, registry):
    assert b.match_registry_entity(label, "symptom_problem", registry, REVIEW)["kind"] == "symptom_problem"


@pytest.mark.parametrize("label,condition", [
    ("Alcohol use disorders", "Alcohol use disorder"),
    ("Opioid use disorders", "Opioid use disorder"),
    ("generalised anxiety disorder", "Generalized anxiety disorder"),
    ("Hallucinogen persisting perceptual disorder", "Hallucinogen persisting perception disorder"),
])
def test_plural_and_british_condition_names_resolve(label, condition, registry):
    match = b.match_registry_entity(label, "condition_indication", registry, {})
    assert match["matched"] and match["label"] == condition


@pytest.mark.parametrize("domain,kind,label,expected_kind,expected", [
    ("cognitive_behavioral", "cognitive_behavioral_construct", "Ego dissolution", "subjective_experience_construct", "Ego dissolution"),
    ("cognitive_behavioral", "cognitive_behavioral_construct", "Mystical experience", "subjective_experience_construct", "Mystical-type experience"),
    ("clinical_outcome", "symptom_problem", "Anhedonia", "cognitive_behavioral_construct", "Anhedonia"),
])
def test_construct_named_exactly_in_the_other_vocabulary_is_used(domain, kind, label, expected_kind, expected, registry, vocabulary):
    match = b.graphable_entity_match(row={"domain": domain}, domain=domain, entity_kind=kind, raw_label=label,
                                     registry=registry, node_vocabulary=vocabulary)
    assert (match["kind"], match["label"], match["match_type"]) == (expected_kind, expected, "peer_construct_vocabulary")


def class_subjects(row, label, registry):
    match = {"label": label, "subject_kind": "compound_class", "matched": True, "match_type": ""}
    return [(subject["label"], subject["reason"]) for subject in b.overview_graph_subjects(row, match, registry)]


def test_review_drug_list_is_split_like_a_primary_list(registry):
    row = {**REVIEW, "support": "Ketamine and esketamine produce rapid antidepressant effects."}
    assert [label for label, _ in class_subjects(row, "Ketamine and esketamine", registry)] == ["Ketamine", "S-ketamine"]


def test_review_contrast_or_class_with_examples_is_not_split(registry):
    contrast = {**REVIEW, "support": "Esketamine was less effective than racemic ketamine."}
    assert class_subjects(contrast, "Ketamine and esketamine", registry) == []
    examples = class_subjects(REVIEW, "Psychedelics (psilocybin, LSD, DMT)", registry)
    assert [label for label, _ in examples] == ["Psychedelics (broad or mixed)"]


@pytest.mark.parametrize("label,expected", [
    ("PCP or other hallucinogens", "Phencyclidine"),
    ("Ketamine or other dissociatives", "Ketamine"),
])
def test_named_drug_is_recovered_after_any_class_word(label, expected, registry):
    assert [subject for subject, _ in class_subjects({}, label, registry)] == [expected]


def test_unspecified_psychedelic_primary_subject_is_admitted_but_analogue_class_is_not(registry):
    assert class_subjects({}, "Psychedelic microdosing", registry) == [
        ("Psychedelics (unspecified compounds)", "controlled_unspecified_psychedelic_class")]
    assert "controlled_unspecified_psychedelic_class" not in b.DETAIL_ONLY_OVERVIEW_SUBJECT_REASONS
    assert b.UNREGISTERED_ANALOG_CLASS_REASON in b.DETAIL_ONLY_OVERVIEW_SUBJECT_REASONS


@pytest.mark.parametrize("statement,drugs,contrasts", [
    ("Psilocybin, LSD and ketamine have shown promise for chronic pain.", ["psilocybin", "lsd", "ketamine"], False),
    ("MDMA-assisted therapy and psilocybin are described as promising for PTSD.", ["mdma", "psilocybin"], False),
    ("Psilocybin/LSD microdosing was studied for mood.", ["psilocybin", "lsd"], False),
    ("MDMA for PTSD and psilocybin for depression showed large effects.", ["mdma", "psilocybin"], True),
    ("Ketamine blocks NMDA receptors whereas LSD does not.", ["ketamine", "lsd"], True),
    ("Psilocybin is converted to psilocin, which acts at 5-HT2A.", ["psilocybin", "psilocin"], True),
    ("The article considers why MDMA/PTSD, LSD/end-of-life-anxiety, and ibogaine/addiction studies were conducted.",
     ["mdma", "lsd", "ibogaine"], True),
    ("There is no compelling evidence that ketamine benefits PTSD and no compelling evidence that LSD "
     "produces enduring benefit for alcohol use disorder.", ["ketamine", "lsd"], True),
    ("Benefits of ketamine and ibogaine are qualified by specific risks: ketamine may produce dissociation, "
     "ibogaine is associated with QT prolongation.", ["ketamine", "ibogaine"], True),
    ("Esketamine nasal spray improved depressive symptoms.", ["ketamine", "esketamine"], True),
    ("The review found rapid effects.", ["ketamine", "esketamine"], False),
])
def test_statement_must_name_the_drugs_as_one_list(statement, drugs, contrasts):
    names = {"esketamine": ["esketamine", "s ketamine"]}
    keys = [names.get(drug, [drug]) for drug in drugs]
    assert statement_contrasts_drugs(b.label_key(statement), keys, statement) is contrasts


@pytest.mark.parametrize("label", ["Racemic ketamine and its isomers", "Ketamine and its enantiomers"])
def test_parent_with_its_isomers_keeps_the_parent(label, registry):
    match = b.graphable_compound_match(label, registry)
    assert match["matched"] and match["label"] == "Ketamine"


@pytest.mark.parametrize("label", ["Ketamine metabolites", "Ketamine and its metabolites"])
def test_metabolites_are_not_the_parent(label, registry):
    assert b.graphable_compound_match(label, registry)["label"] != "Ketamine"


@pytest.mark.parametrize("dash", ["–", "—", "−", "‐"])
def test_dashes_in_anatomy_and_compound_names_act_as_hyphens(dash, registry, vocabulary):
    assert b.brain_entity_split_matches(f"Amygdala{dash}vmPFC connectivity", vocabulary) == [
        ("brain_region", "Amygdala"), ("brain_region", "Ventromedial prefrontal cortex")]
    assert b.graphable_compound_match(f"5{dash}MeO{dash}DMT", registry)["label"] == "5-MeO-DMT"


def test_symbol_naming_another_target_keeps_the_label_unresolved(registry):
    assert not b.match_registry_entity("M1 muscarinic receptor (CHRM2)", "target", registry, {})["matched"]


def test_location_abbreviation_and_mediated_readout_are_unchanged(registry):
    located = "Dopamine D2 receptor (D2R; DRD2) in the basolateral amygdala (BLA)"
    assert b.match_registry_entity(located, "target", registry, {"target": located})["label"] == "Dopamine D2 receptor (DRD2)"
    current = b.match_registry_entity("NMDA receptor-mediated synaptic current electrophysiology", "biomarker_readout", registry, {})
    assert current["kind"] == "biomarker_readout"


@pytest.mark.parametrize("label,target", [
    ("Human mu-opioid receptor (OPRM/MOR)", "mu opioid receptor (OPRM1)"),
    ("Human κ opioid receptor (hκOR)", "kappa opioid receptor (OPRK1)"),
    ("Dopamine D2Short receptor", "Dopamine D2 receptor (DRD2)"),
    ("5-HT7a receptor", "5-HT7"),
    ("NMDA-type ionotropic glutamate receptor", "NMDA receptor"),
])
def test_target_names_with_species_assay_or_variant_wording_resolve(label, target, registry):
    match = b.match_registry_entity(label, "target", registry, {"target": label})
    assert match["matched"] and match["label"] == target


def test_named_subtype_and_subunit_are_not_collapsed(registry):
    assert b.match_registry_entity("5-HT1A receptor", "target", registry, {})["label"] == "5-HT1A"
    assert b.match_registry_entity("NMDA receptor (GluN2B subunit)", "target", registry, {})["label"] == "GluN2B (GRIN2B)"


@pytest.mark.parametrize("location,background", [
    ("Article text, Introduction section, Results", False),
    ("Article text, Results: Radial arm maze reference memory test", False),
    ("Article text C004; Fig. 4 and caption references.", False),
    ("Introduction", True),
    ("Background; References", True),
])
def test_background_location_reads_results_and_figures(location, background):
    row = {"domain": "cognitive_behavioral", "kg_entity_kind_override": "cognitive_behavioral_construct",
           "graph_entity_label": "Spatial memory", "source_item_type": "primary_item", "evidence_location": location}
    assert (b.graph_admission_decision(row)[1] == "primary_claim_supported_only_by_background_location") is background


def test_unresolved_neural_readout_keeps_its_own_reason():
    row = {"domain": "brain_system", "kg_entity_kind_override": "brain_measure",
           "entity_match_type": "explicit_neural_readout_detail_only"}
    assert b.graph_admission_decision(row) == ("paper_detail", "explicit_neural_readout_without_resolved_anatomy")


def test_ketamine_uropathy_is_a_urinary_harm_of_ketamine(registry, vocabulary):
    row = {"domain": "clinical_outcome", "compound": "Ketamine", "graph_entity_label": "Ketamine-associated uropathy",
           "condition_or_indication": "Ketamine-associated uropathy", "kg_entity_kind_override": "condition_indication",
           "finding_summary": "Chronic ketamine use was associated with lower urinary tract symptoms."}
    out = b.normalize_claim_metadata(row, "clinical_outcome")
    assert out["domain"] == "safety_tolerability"
    match = b.graphable_entity_match(row=out, domain="safety_tolerability", entity_kind="safety_adverse_event",
                                     raw_label=b.entity_label_for(out, "safety_tolerability", "safety_adverse_event"),
                                     registry=registry, node_vocabulary=vocabulary)
    assert match["label"] == "Urinary toxicity" and match["match_type"] == "safety_endpoint_pattern"
    treatment = b.normalize_claim_metadata({**row, "compound": "Pentosan polysulfate"}, "clinical_outcome")
    assert treatment["domain"] == "clinical_outcome"


def test_lithium_pilocarpine_seizure_model_is_not_a_lithium_adjunct():
    row = {"domain": "cognitive_behavioral", "compound_or_exposure": "Ketamine after lithium-pilocarpine status epilepticus",
           "finding_summary": "Ketamine reduced seizure behavior."}
    out = b.normalize_claim_metadata(row, "cognitive_behavioral")
    assert out.get("graph_admission_reason") != "adjunct_sequence_not_atomic_drug_result"


def source_rows(tmp_path, rows):
    path = tmp_path / "routed_evidence_rows.json"
    path.write_text(json.dumps(rows))
    out_dir = tmp_path / "kg"
    b.build_tables(out_dir=out_dir, write_duckdb=False, retraction_status_path=None,
                   identity_verdicts_path=None, paper_metadata_overrides_path=None,
                   graph_sources={"routed_extractions": {"path": path, "domain": "routed", "dataset": "routed",
                                                         "default_evidence_type": "primary_evidence", "skip_audit": True}})
    return pd.read_parquet(out_dir / "findings.parquet"), pd.read_parquet(out_dir / "normalization_audit.parquet")


def review_row(doi, role, label, domain, kind, declared, statement):
    anchors = [{"role": "compound", "label": "Ketamine", "anchor_type": "named_entity"},
               {"role": role, "label": label, "anchor_type": "named_entity"}]
    return {**REVIEW, "study_doi": doi, "study_title": "Ketamine review", "source_type": "review", "paper_type": "review",
            "domain": domain, "domain_route": domain, "dataset": domain, "compound": "Ketamine",
            "graph_subject_label": "Ketamine", "graph_subject_kind": "atomic_compound", "graph_entity_label": label,
            "kg_entity_kind_override": kind, "entity_role": role, "finding_summary": statement, "support": statement,
            "relationship_anchors_json": json.dumps(anchors), "relationship_domain_labels_json": json.dumps(declared),
            "graph_admission_status": "main_graph", "graph_admission_reason": "review_relationship_prominence",
            "review_scope_status": "in_scope", "coverage_focus": "major_supporting"}


def test_review_statement_falls_back_to_the_declared_domain_and_unmatched_outcomes_stay_in_detail(tmp_path):
    findings, audit = source_rows(tmp_path, [
        review_row("10.1000/bladder", "condition", "Ketamine-induced urological toxicity of the bladder",
                   "clinical_outcome", "condition_indication", ["safety_tolerability"],
                   "High-frequency ketamine use is associated with disruption of the bladder urothelial barrier."),
        review_row("10.1000/unmatched", "outcome", "Quality of sleep after the ceremony",
                   "clinical_outcome", "symptom_problem", ["clinical_outcome"],
                   "Ketamine users reported poorer sleep quality after the ceremony."),
    ])
    bladder = findings[findings.study_doi.eq("10.1000/bladder")].iloc[0]
    assert (bladder.domain, bladder.kg_entity_kind_override, bladder.graph_entity_label) == (
        "safety_tolerability", "safety_adverse_event", "Urinary toxicity")
    assert bladder.graph_admission_status == "main_graph"
    assert "review_statement_retyped_to_declared_domain" in bladder.normalization_repairs_json
    unmatched = findings[findings.study_doi.eq("10.1000/unmatched")].iloc[0]
    assert (unmatched.graph_admission_status, unmatched.graph_admission_reason) == (
        "paper_detail", "outcome_label_not_in_vocabulary")
    assert unmatched.graph_entity_label == "Quality of sleep after the ceremony"
    assert audit.empty or "10.1000/unmatched" not in set(audit.study_doi)
