import itertools
import json
from pathlib import Path

from pipeline.kg import convert_review_relationship_bundles_to_evidence_rows as review


REGISTRY = {"compounds": [{"label": "Ketamine", "aliases": ["(R,S)-ketamine", "ket"]},
                          {"label": "LSD", "aliases": []},
                          {"label": "Salvinorin A", "aliases": ["salvinorin A"]}],
            "targets": [{"label": "NMDA receptor", "aliases": ["NMDAR"]}], "disorders": []}


def convert(anchors, **changes):
    rel = {"item_id": "R1", "anchors": anchors, "relationship_statement": "The review discusses a qualified mechanism.",
           "relationship_kind": "review_synthesis", "graph_form": "atomic", "graph_eligibility": "main_graph",
           "paper_prominence": "major_supporting", "evidence_stratum": "human_and_preclinical",
           "domain_labels": ["molecular_target", "brain_system", "clinical_outcome"],
           "limitations": ["This is a hypothesis, not established causality."],
           "evidence_locators": [{"location": "text", "locator": "Section 2", "supporting_text": "Mechanism remains debated."}]}
    rel.update(changes)
    bundle = {"study_doi": "10.1/review", "study_title": "Ketamine review", "status": "ok", "result": {
        "paper_frame": {"primary_subjects": ["Ketamine"]}, "relationships": [rel]}}
    return review.convert_bundles([bundle], [{"study_doi": "10.1/review", "paper_metadata": {"review_type": "review"}}],
                                  REGISTRY, active_candidate_dois={"10.1/review"})


def anchor(role, label, kind="named_entity"):
    return {"role": role, "label": label, "anchor_type": kind}


def test_named_domain_object_wins_over_generic_outcome_context():
    rows, _ = convert([anchor("compound", "Ketamine"), anchor("outcome", "antidepressant effects", "context"),
                       anchor("target", "NMDAR")])
    assert len(rows) == 1
    assert rows[0]["domain"] == "molecular_target"
    assert rows[0]["graph_entity_label"] == "NMDAR"


def test_explicit_named_views_preserve_one_qualified_source_relationship():
    rows, report = convert([anchor("compound", "Salvinorin A"), anchor("target", "κ-opioid receptor"),
                            anchor("brain_system", "Claustrum"), anchor("comparator", "LSD"),
                            anchor("population", "Healthy volunteers"), anchor("outcome", "Consciousness", "context")])
    assert {r["graph_entity_label"] for r in rows} == {"κ-opioid receptor", "Claustrum"}
    assert len({r["relationship_source_group_key"] for r in rows}) == 1
    assert {r["source_item_id"] for r in rows} == {"R1"}
    assert len({r["support"] for r in rows}) == 1
    assert all(r["notes"] == "This is a hypothesis, not established causality." for r in rows)
    assert all(r["supporting_quote"] == "Mechanism remains debated." for r in rows)
    assert report["counts"]["source_relationships"] == 1
    assert report["counts"]["additional_named_object_views"] == 1


def test_downstream_target_anchor_without_target_domain_is_not_promoted():
    rows, _ = convert([anchor("compound", "Ketamine"), anchor("target", "AMPAR"),
                       anchor("outcome", "Antidepressant effects", "context")],
                      domain_labels=["molecular_pathway_readout", "clinical_outcome"])
    assert len(rows) == 1
    assert rows[0]["domain"] == "clinical_outcome"
    assert rows[0]["graph_entity_label"] != "AMPAR"


def test_generic_cellular_outcome_does_not_create_additional_cognitive_view():
    rows, _ = convert([anchor("compound", "Ketamine"), anchor("pathway_or_process", "Intracellular cAMP signaling"),
                       anchor("outcome", "Gliosignaling-molecule release, including BDNF")],
                      evidence_stratum="preclinical", domain_labels=["molecular_pathway_readout", "cognitive_behavioral"])
    assert len(rows) == 1
    assert rows[0]["domain"] == "molecular_pathway_readout"


def test_target_aliases_do_not_create_duplicate_views():
    rows, _ = convert([anchor("compound", "Ketamine"), anchor("target", "NMDAR"), anchor("target", "NMDA receptor")])
    assert len(rows) == 1


def test_multiple_drug_subjects_are_order_invariant_and_detail_only():
    anchors = [anchor("compound", "Ketamine"), anchor("compound", "LSD"), anchor("target", "NMDAR")]
    for permutation in itertools.permutations(anchors):
        rows, _ = convert(list(permutation))
        assert len(rows) == 1
        assert rows[0]["graph_subject_label"] == "Ketamine / LSD"
        assert rows[0]["graph_admission_status"] == "paper_detail"
        assert rows[0]["graph_admission_reason"] == "review_multiple_drug_subjects_requires_attribution"


def test_subject_aliases_are_one_identity_and_combination_is_preserved():
    rows, _ = convert([anchor("compound", "Ketamine"), anchor("compound", "ket"), anchor("target", "NMDAR")])
    assert rows[0]["graph_subject_label"] == "Ketamine"
    assert rows[0]["graph_admission_status"] == "main_graph"
    rows, _ = convert([anchor("compound", "Ketamine"), anchor("compound", "LSD"), anchor("target", "NMDAR")], graph_form="combination")
    assert rows[0]["graph_subject_label"] == "Ketamine + LSD"
    assert rows[0]["graph_subject_kind"] == "compound_combination"


def test_same_drug_administration_descriptors_do_not_create_ambiguity():
    for descriptor in ["Ketamine treatment", "Intranasal ketamine", "Ketamine-assisted psychotherapy", "Ketamine (ket)"]:
        rows, _ = convert([anchor("compound", "Ketamine"), anchor("intervention", descriptor), anchor("target", "NMDAR")])
        assert rows[0]["graph_subject_label"] == "Ketamine"
        assert rows[0]["graph_admission_status"] == "main_graph"
        assert descriptor in rows[0]["relationship_anchors_json"]


def test_different_chemical_and_cessation_identity_are_not_stripped():
    registry = review.registry_index(REGISTRY)
    for different in ["Ketamine metabolite", "Ketamine analogue", "Ketamine cessation", "Ketamine plus music", "R-ketamine"]:
        assert not review.registered_subject_identity(different, registry)


def test_self_administration_is_same_drug_but_not_a_comparative_or_cessation_protocol():
    for descriptor in ["Ketamine self-administration", "Ketamine self administration paradigms"]:
        rows, _ = convert([anchor("compound", "Ketamine"), anchor("intervention", descriptor, "context"),
                           anchor("outcome", "Reinforcing efficacy")], graph_form="context",
                          evidence_stratum="preclinical", domain_labels=["cognitive_behavioral"])
        assert rows[0]["graph_subject_label"] == "Ketamine"
        assert rows[0]["graph_admission_status"] == "main_graph"
        assert rows[0]["domain"] == "cognitive_behavioral"
    registry = review.registry_index(REGISTRY)
    for descriptor in ["Ketamine self-administration cessation", "Ketamine and LSD self-administration",
                       "Ketamine self-administration versus LSD", "Ketamine self-administration withdrawal"]:
        assert not review.registered_subject_identity(descriptor, registry)


def test_single_drug_typed_context_preserves_context_actor_and_regimen():
    for label, typed, kind in [("Religious framing by ketamine communities", "context", "exposure_context"),
                              ("Psychotherapy added to ketamine", "combination_or_regimen", "treatment_regimen")]:
        anchors = [anchor("compound", "Ketamine"), anchor("intervention", label, typed), anchor("outcome", "Qualified outcome")]
        for permutation in itertools.permutations(anchors):
            rows, _ = convert(list(permutation), graph_form="context")
            row = rows[0]
            assert row["graph_subject_label"] == label
            assert row["graph_subject_kind"] == kind
            assert row["atomic_compound_candidate"] == ""
            assert row["graph_subject_source_field"] == "anchors_typed_context"
            assert row["graph_admission_status"] == "main_graph"
            assert label in row["relationship_anchors_json"]


def test_context_does_not_disguise_multiple_chemicals_classes_or_cessation():
    for label in ["Psychotherapy combined with ketamine and LSD", "Ketamine versus LSD therapy",
                  "Ketamine and classic psychedelics", "Ketamine metabolite treatment", "Ketamine cessation",
                  "Medicines based on the ketamine model"]:
        rows, _ = convert([anchor("compound", "Ketamine"), anchor("intervention", label, "context"),
                           anchor("outcome", "Qualified outcome")], graph_form="context")
        assert rows[0]["graph_admission_reason"] == "review_multiple_drug_subjects_requires_attribution"
    rows, _ = convert([anchor("compound", "Ketamine"), anchor("compound", "LSD"),
                       anchor("intervention", "Psychotherapy added to ketamine", "combination_or_regimen"),
                       anchor("outcome", "Qualified outcome")], graph_form="context")
    assert rows[0]["graph_admission_status"] == "paper_detail"


def test_paper_drug_does_not_inherit_receptor_or_enzyme_background_findings():
    for anchors, statement in [
        ([anchor("target", "Adenosine A1 receptor"), anchor("safety_event", "Bradycardia")],
         "Direct systemic A1 receptor stimulation may cause bradycardia."),
        ([anchor("target", "INMT, the DMT-synthesizing enzyme"), anchor("condition", "Carcinogenesis")],
         "The review considers INMT expression in carcinogenesis."),
        ([anchor("target", "Sigma-1 receptor"), anchor("pathway_or_process", "Cellular bioenergetics")],
         "Sigma-1 receptor supports mitochondrial respiration."),
        ([anchor("target", "NMDA receptor")],
         "Astrocyte atrophy is background for considering ketamine action."),
        ([anchor("target", "NMDA receptor")],
         "Another receptor agonist, compared with ketamine, reduced symptoms."),
    ]:
        rows, _ = convert(anchors, graph_form="context", relationship_statement=statement)
        assert len(rows) == 1
        assert rows[0]["graph_admission_status"] == "paper_detail"
        assert rows[0]["graph_admission_reason"] == "review_target_background_without_drug_actor"
        assert rows[0]["support"] == statement
    rows, _ = convert([anchor("compound", "Ketamine"), anchor("target", "Adenosine A1 receptor")],
                      graph_form="context", relationship_statement="A1 deletion counteracted ketamine effects.")
    assert rows[0]["graph_admission_status"] == "main_graph"
    for statement in ["Ketamine may inhibit NMDA receptors.", "Ketamine does not activate NMDA receptors.",
                      "Opioid receptors may be necessary for ketamine's antidepressant effect."]:
        rows, _ = convert([anchor("target", "NMDA receptor")], graph_form="context", relationship_statement=statement)
        assert rows[0]["graph_admission_status"] == "main_graph"
    rows, _ = convert([anchor("public_health_topic", "Clinical trial reporting")], graph_form="context")
    assert rows[0]["graph_admission_status"] == "main_graph"
    assert not review.inherited_drug_target_background(
        {"source_field": "paper_frame.primary_subjects", "label": "Classic psychedelics"},
        {"anchors": [anchor("target", "5-HT2A")], "relationship_statement": "The review discusses receptor signaling."},
        review.registry_index(REGISTRY))
    rows, _ = convert([anchor("compound", "Ketamine"), anchor("compound", "Fluoxetine"),
                       anchor("intervention", "Psychotherapy added to ketamine", "combination_or_regimen"),
                       anchor("outcome", "Qualified outcome")], graph_form="context")
    assert rows[0]["graph_admission_status"] == "paper_detail"
    # Two different regimens are not one contextual actor, even with one drug.
    rows, _ = convert([anchor("compound", "Ketamine"), anchor("intervention", "Psychotherapy added to ketamine", "context"),
                       anchor("intervention", "Ketamine paired with music", "context"),
                       anchor("outcome", "Qualified outcome")], graph_form="context")
    assert rows[0]["graph_admission_status"] == "paper_detail"


def test_frozen_subject_controls_keep_examples_but_not_contrasting_drug_claims():
    data = json.loads((Path(__file__).parent / "fixtures/review_subject_identity_cases.json").read_text())
    tasks = [{"study_doi": b["study_doi"], "paper_metadata": {"review_type": "review"}} for b in data["bundles"]]
    rows, _ = review.convert_bundles(data["bundles"], tasks, data["registry"], active_candidate_dois={b["study_doi"] for b in data["bundles"]})
    by = {}
    for r in rows:
        by.setdefault(r["study_doi"], r)
    same = by["10.1080/02791072.1985.10524331"]
    assert same["graph_subject_label"] == "LSD"
    assert same["graph_admission_status"] == "main_graph"
    examples = by["10.1523/jneurosci.1659-20.2020"]
    assert examples["graph_subject_label"] == "Classic psychedelics"
    assert examples["graph_admission_status"] == "main_graph"
    # Parent/metabolite effects and MDMA-versus-psychedelic effects are distinct.
    for doi in ["10.1002/hup.70063", "10.1001/jamapsychiatry.2022.0665"]:
        assert by[doi]["graph_admission_reason"] == "review_multiple_drug_subjects_requires_attribution"


def test_detail_relationships_do_not_expand_into_main_graph_views():
    rows, _ = convert([anchor("compound", "Ketamine"), anchor("target", "NMDAR"), anchor("brain_system", "Claustrum")],
                      graph_eligibility="paper_detail_only", paper_prominence="secondary_context")
    assert len(rows) == 1
    assert rows[0]["graph_admission_status"] == "paper_detail"


def test_subject_only_interaction_does_not_become_a_molecular_target():
    rows, _ = convert([anchor("compound", "Ketamine"), anchor("compound", "LSD")], graph_form="interaction")
    assert rows[0]["graph_admission_status"] == "paper_detail"
    assert rows[0]["entity_role"] == "other"


def test_blinding_comparator_is_not_a_treatment_component():
    # Fresh review audit: 10.1080/02791072.1985.10524331, r3.
    # A placebo in a methods critique is a comparator, not an intervention
    # component the review recommends administering alongside LSD.
    rows, _ = convert([anchor("compound", "LSD"),
                       anchor("other", "Double-blind controlled studies", "paper_topic"),
                       anchor("comparator", "Active or inactive placebo", "other"),
                       anchor("other", "Effective blinding", "other")],
                      domain_labels=["intervention_context"])
    assert rows[0]["entity_role"] == "comparator"
    assert rows[0]["graph_admission_status"] == "paper_detail"
    assert rows[0]["graph_admission_reason"] == "review_comparator_or_population_is_context"


def test_saved_mechanistic_reviews_keep_named_views_and_indirect_qualifiers():
    data = json.loads((Path(__file__).parent / "fixtures/review_named_object_projection_cases.json").read_text())
    bundles = data["bundles"]
    tasks = [{"study_doi": b["study_doi"], "paper_metadata": {"review_type": "review"}} for b in bundles]
    rows, _ = review.convert_bundles(bundles, tasks, REGISTRY, active_candidate_dois={b["study_doi"] for b in bundles})
    ketamine = [r for r in rows if r["study_doi"] == "10.1016/j.bcp.2021.114892"]
    assert any(r["source_item_id"] == "R1" and r["graph_entity_label"] == "NMDAR" for r in ketamine)
    assert any(r["source_item_id"] == "R6" and r["graph_entity_label"] == "μ- and κ-opioid receptors" for r in ketamine)
    assert not any(r["source_item_id"] == "R2" and r["domain"] == "molecular_target" for r in ketamine)
    salvia = [r for r in rows if r["study_doi"] == "10.3389/fnint.2014.00020"]
    assert {r["entity_role"] for r in salvia} == {"target", "brain_system"}
    assert all("not a directly demonstrated causal effect" in r["notes"] for r in salvia)


def test_statement_naming_each_drug_for_one_relationship_is_attributable():
    anchors = [anchor("compound", "Ketamine"), anchor("compound", "LSD"), anchor("target", "NMDAR")]
    for permutation in itertools.permutations(anchors):
        rows, _ = convert(list(permutation), relationship_statement="Ketamine and LSD both act at the NMDA receptor.")
        assert rows[0]["graph_subject_label"] == "Ketamine / LSD"
        assert rows[0]["graph_admission_status"] == "main_graph"
        assert rows[0]["review_subject_attribution"] == "each_named_drug"


def test_statement_that_contrasts_the_drugs_is_not_attributed_to_each():
    anchors = [anchor("compound", "Ketamine"), anchor("compound", "LSD"), anchor("target", "NMDAR")]
    for statement in ["Ketamine blocks the NMDA receptor, whereas LSD does not.",
                      "Ketamine for depression and LSD for anxiety act through the NMDA receptor.",
                      "Ketamine binds the NMDA receptor more strongly than LSD."]:
        rows, _ = convert(anchors, relationship_statement=statement)
        assert rows[0]["graph_admission_status"] == "paper_detail"
        assert rows[0]["graph_admission_reason"] == "review_multiple_drug_subjects_requires_attribution"
        assert rows[0]["review_subject_attribution"] == ""


def test_nasal_spray_is_an_administration_descriptor():
    registry = review.registry_index(REGISTRY)
    assert review.registered_subject_identity("Nasal ketamine spray", registry) == "Ketamine"
