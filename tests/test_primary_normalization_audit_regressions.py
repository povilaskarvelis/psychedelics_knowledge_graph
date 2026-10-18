"""Scientific invariants from the source audit, with affirmative/null controls.

Fixtures are self-contained minimal observations, not copies of expected builder
output. They exercise the expansion and matching sequence used by build_tables.
"""

import copy
import json

import pytest

from pipeline.kg import build_evidence_tables as b
from pipeline.kg import convert_routed_extractions_to_evidence_rows as c


@pytest.fixture(scope="module")
def dictionaries():
    return b.registry_lookup(b.DEFAULT_REGISTRY_PATH), b.node_vocabulary_lookup()


def projected(row, dictionaries):
    registry, vocabulary = dictionaries
    normalized = b.normalize_claim_metadata(copy.deepcopy(row), row["domain"])
    observations = []
    for expanded in b.entity_expanded_rows(normalized, normalized["domain"], registry, vocabulary):
        final = b.normalize_claim_metadata(expanded, expanded["domain"])
        kind = b.entity_kind_for(final, final["domain"])
        anchor = b.entity_label_for(final, final["domain"], kind)
        match = b.graphable_entity_match(final, final["domain"], kind, anchor, registry, vocabulary)
        observations.append((final, anchor, match))
    return observations


@pytest.mark.parametrize("text,expected", [
    ("bufotenine", {"Bufotenin"}),
    ("5-hydroxy-N,N-dimethyltryptamine (bufotenine, 5-HODMT)", {"Bufotenin"}),
    ("5-hydroxy-N,N-dimethyltryptamine (bufotenine) and DMT", {"Bufotenin", "DMT"}),
    ("5-MeO-DMT and DMT", {"5-MeO-DMT", "DMT"}),
    ("LSD; psilocybin was not administered", {"LSD"}),
    ("Psilocybin, excluding LSD", {"Psilocybin"}),
    ("LSD (not psilocybin)", {"LSD"}),
    ("LSD did not change outcome", {"LSD"}),
    ("LSD and psilocybin", {"LSD", "Psilocybin"}),
    ("Psilocybin and LSD", {"LSD", "Psilocybin"}),
])
def test_compound_identity_and_absence_do_not_depend_on_name_surface(text, expected, dictionaries):
    registry, _ = dictionaries
    row = {"compound": text, "domain": "molecular_target"}
    c.apply_graph_subject(row)
    matched = b.graphable_subject_match(row, registry)
    assert matched["matched"]
    assert {x["label"] for x in b.overview_graph_subjects(row, matched, registry)} == expected


@pytest.mark.parametrize("text,label,kind", [
    ("human 5-HT2A (5-hydroxytryptamine 2A) receptor", "5-HT2A", "target"),
    ("5-hydroxytryptamine 2A receptor", "5-HT2A", "target"),
    ("5-hydroxytryptamine (5-HT) receptor", "5-HT receptor family", "system_family"),
    ("Serotonin", "Serotonin", "biomarker_readout"),
    ("5-hydroxytryptamine (5-HT)", "Serotonin", "biomarker_readout"),
    ("5-HT-2 receptor", "5-HT2 receptor family", "system_family"),
    ("5-HT-1c receptor", "5-HT2C", "target"),
    ("5-HT_2A receptor", "5-HT2A", "target"),
    ("5-HT1A serotonin receptor subtype", "5-HT1A", "target"),
])
def test_receptor_is_not_its_parent_ligand(text, label, kind, dictionaries):
    registry, _ = dictionaries
    match = b.match_registry_entity(text, "target", registry)
    assert (match["label"], match["kind"]) == (label, kind)


@pytest.mark.parametrize("text,expected", [
    ("5-HT2A receptor, not 5-HT2C", {"5-HT2A"}),
    ("5-HT2A and 5-HT2C receptors", {"5-HT2A", "5-HT2C"}),
    ("5-HT2A/2C receptors", {"5-HT2A", "5-HT2C"}),
])
def test_target_exclusion_and_positive_multitarget_control(text, expected, dictionaries):
    row = {"domain": "molecular_target", "compound": "Psilocybin", "graph_entity_label": text,
           "primary_graph_anchor_kind": "target", "finding_summary": "Binding was assessed."}
    observations = projected(row, dictionaries)
    assert all(match["matched"] for _, _, match in observations)
    assert {match["label"] for _, _, match in observations} == expected


@pytest.mark.parametrize("label,expected", [
    ("Left subgenual anterior cingulate cortex", {"Subgenual anterior cingulate cortex"}),
    ("Right subgenual anterior cingulate cortex", {"Subgenual anterior cingulate cortex"}),
    ("Left anterior cingulate cortex", {"Anterior cingulate cortex"}),
    ("Subgenual anterior cingulate cortex; anterior cingulate cortex", {"Subgenual anterior cingulate cortex", "Anterior cingulate cortex"}),
    ("Amygdala and Hippocampus", {"Amygdala", "Hippocampus"}),
])
def test_nested_anatomical_alias_is_one_region_but_separate_mentions_survive(label, expected, dictionaries):
    row = {"domain": "brain_system", "compound": "Psilocybin", "graph_entity_label": label,
           "primary_graph_anchor_kind": "brain_region"}
    observations = projected(row, dictionaries)
    assert all(match["matched"] for _, _, match in observations)
    assert {match["label"] for _, _, match in observations} == expected


def test_partial_brain_list_explicitly_accounts_for_unknown_member(dictionaries):
    row = {"domain": "brain_system", "compound": "Psilocybin",
           "graph_entity_label": "Amygdala; unregistered brain region",
           "primary_graph_anchor_kind": "brain_region"}
    observations = projected(row, dictionaries)
    assert {m["label"] for _, _, m in observations} == {"Amygdala"}
    assert all(json.loads(r["entity_split_unmapped_parts_json"]) == ["unregistered brain region"] for r, _, _ in observations)


@pytest.mark.parametrize("category,system,expected", [
    ("ex_vivo", "Rat cerebral cortex", "ex_vivo"),
    ("in_vitro", "Human recombinant receptors", "in_vitro"),
    ("computational", "Simulated binding to human CB1", "computational"),
    ("computational", "Simulated binding to rat CB1", "computational"),
    ("in_vivo", "Mouse", "in_vivo"),
    ("clinical", "Human volunteers", "clinical"),
])
def test_explicit_system_precedes_species_and_descriptive_context(category, system, expected):
    assert b.inferred_experimental_system({"experimental_system_category": category, "system": system}) == expected


@pytest.mark.parametrize("support", [
    "EEG microstate occurrence changed; conventional power spectral density did not change.",
    "EEG microstate occurrence changed. No receptor assay was performed.",
    "EEG microstate occurrence changed.",
])
def test_neural_microstates_never_become_receptor_regulation_from_incidental_prose(support, dictionaries):
    row = {"domain": "brain_system", "compound": "S-ketamine", "primary_graph_anchor_kind": "biomarker_readout",
           "graph_entity_label": "EEG microstate parameters", "support": support, "finding_summary": support}
    observations = projected(row, dictionaries)
    assert {(m["kind"], m["label"]) for _, _, m in observations} == {("brain_measure", "Network dynamics")}
    assert b.molecular_effect_label({}, "biomarker_readout", "5-HT2A receptor density") == "Receptor regulation & trafficking"


def test_explicit_head_twitch_model_stays_behavioral_but_serious_psychosis_stays_safety():
    row = {"domain": "cognitive_behavioral", "compound": "DOI", "graph_entity_label": "Psychotomimetic effects",
           "primary_graph_anchor_kind": "cognitive_behavioral_construct",
           "support": "DOI increased head-twitch response in mice relative to saline."}
    assert b.normalize_claim_metadata(row, row["domain"])["domain"] == "cognitive_behavioral"
    serious = {**row, "support": "A patient developed persistent psychosis requiring hospitalization after dosing."}
    assert b.normalize_claim_metadata(serious, serious["domain"])["domain"] == "safety_tolerability"


def test_safety_list_quantitative_annotations_preserve_events_without_unit_fragments(dictionaries):
    anchors = [
        "Acute kidney injury; rhabdomyolysis; coagulopathy",
        "Acute kidney injury (creatinine 1.6 mg/dl), rhabdomyolysis (creatine kinase 16,600 U/L at peak on ICU day 2), and coagulopathy (INR 2.57 at peak)",
    ]
    results = []
    for anchor in anchors:
        row = {"domain": "safety_tolerability", "compound": "Psilocybin", "graph_entity_label": anchor,
               "safety_event_or_measure": anchor, "primary_graph_anchor_kind": "safety_adverse_event"}
        observations = projected(row, dictionaries)
        assert all(not a.startswith("L at ") for _, a, _ in observations)
        results.append({m["label"] for _, _, m in observations})
    assert results[0] == results[1]
    parts = b.scientific_list_parts(anchors[1])
    assert len(parts) == 3
    assert "16,600 U/L" in parts[1]
    assert b.scientific_list_parts("N,N-dimethyltryptamine") == []


@pytest.mark.parametrize("label", ["seizure", "seizures", "continuous seizures", "convulsion", "convulsions"])
def test_seizure_number_preserves_event_identity(label):
    assert b.safety_category_for_text(label) == "Seizure/convulsion"


def test_plural_seizures_remain_in_multievent_projection(dictionaries):
    row = {"domain": "safety_tolerability", "compound": "Psilocybin", "primary_graph_anchor_kind": "safety_adverse_event",
           "graph_entity_label": "Coma, continuous seizures, and hyperthermia", "safety_event_or_measure": "Coma, continuous seizures, and hyperthermia"}
    assert "Seizure/convulsion" in {m["label"] for _, _, m in projected(row, dictionaries)}


@pytest.mark.parametrize("legacy", ["Plasma prolactin", "Plasma prolactin increased after MDMA", "MDMA did not alter plasma prolactin"])
def test_explicit_marker_identity_is_not_overwritten_by_longer_result_prose(legacy):
    row = {"specific_readout_or_marker": "Plasma prolactin", "pathway_or_readout": legacy}
    assert b.molecular_specific_anchor_label(row, "biomarker_readout") == "Plasma prolactin"


@pytest.mark.parametrize("marker,category,summary", [
    ("Total p66ShcA", "Intracellular signal transduction", "Phosphorylated p66ShcA increased but total p66ShcA was unchanged."),
    ("5-HT2A receptor protein", "Receptor regulation & trafficking", "Protein levels were similar between genotypes."),
    ("miRNA 1264-3p", "Gene expression & activity markers", "The 5HTR2C cluster miRNA differed by genotype."),
    ("5-HT-immunoreactive axon-terminal density and morphology", "Cell injury & survival", "Serotonergic axon terminals were lost, without loss of cell bodies."),
    ("Calcium-dependent GCaMP6f photometry signal in CRH-expressing PVN neurons", "Neuronal excitability & synaptic transmission", "5-HT2A and 5-HT2C receptor antagonists attenuated calcium activity."),
])
def test_explicit_readout_and_category_survive_conflicting_incidental_context(marker, category, summary, dictionaries):
    row = {"domain": "molecular_pathway_readout", "compound": "Psilocybin",
           "specific_readout_or_marker": marker, "pathway_or_readout": summary,
           "molecular_effect_category": category, "finding_summary": summary,
           "primary_graph_anchor_kind": "biomarker_readout"}
    observations = projected(row, dictionaries)
    assert len(observations) == 1
    final, _, match = observations[0]
    label = b.pathway_readout_display_label(final, match['kind'], match['label'], marker, match['item'])
    assert label == marker
    assert b.molecular_effect_label(final, match['kind'], label) == category
    assert b.molecular_parent_from_specific(final, category, label) == category


@pytest.mark.parametrize("marker,expected", [
    ("c-Fos-positive/5-HT2A receptor-negative cells", {"c-Fos-positive/5-HT2A receptor-negative cells"}),
    ("p38 MAP kinase and ERK 1/2 activation", {"p38 MAP kinase", "ERK 1/2 activation"}),
    ("IL-6, KC/GRO, and TNF-α", {"IL-6", "KC/GRO", "TNF-α"}),
])
def test_scientific_marker_units_do_not_become_fragments(marker, expected, dictionaries):
    category = "Gene expression & activity markers" if "cells" in marker else "Intracellular signal transduction" if "kinase" in marker else "Neuroinflammation & immune signaling"
    row = {"domain": "molecular_pathway_readout", "compound": "Psilocybin", "specific_readout_or_marker": marker,
           "pathway_or_readout": marker, "molecular_effect_category": category,
           "primary_graph_anchor_kind": "biomarker_readout"}
    observations = projected(row, dictionaries)
    assert all(m['matched'] for _, _, m in observations)
    assert {anchor for _, anchor, _ in observations} == expected


def test_marker_aliases_still_share_identity_and_brain_measure_remains_controlled(dictionaries):
    labels = []
    for marker in ("Serotonin", "5-HT"):
        row = {"domain": "molecular_pathway_readout", "compound": "Psilocybin",
               "specific_readout_or_marker": marker, "molecular_effect_category": "Neurotransmitter release, uptake & turnover",
               "primary_graph_anchor_kind": "biomarker_readout"}
        final, anchor, match = projected(row, dictionaries)[0]
        labels.append(b.pathway_readout_display_label(final, match['kind'], match['label'], anchor, match['item']))
    assert labels == ['Serotonin', 'Serotonin']
    marker = "Plasma oxytocin change covarying with BOLD activation"
    assert b.pathway_readout_display_label({'specific_readout_or_marker': marker}, 'brain_measure', 'BOLD response', marker, None) == 'BOLD response'


def test_phosphoinositide_hydrolysis_is_not_phosphorylation(dictionaries):
    row = {'domain': 'molecular_pathway_readout', 'compound': 'LSD',
           'specific_readout_or_marker': 'Phosphoinositide hydrolysis',
           'pathway_or_readout': 'Agonist-stimulated phosphoinositide hydrolysis',
           'molecular_effect_category': 'Intracellular signal transduction',
           'primary_graph_anchor_kind': 'biomarker_readout'}
    final, anchor, match = projected(row, dictionaries)[0]
    assert b.pathway_readout_display_label(final, match['kind'], match['label'], anchor, match['item']) == 'Phosphoinositide hydrolysis'
    assert not b.READOUT_PHOSPHORYLATION_RE.search('phosphoinositide hydrolysis')
    assert b.READOUT_PHOSPHORYLATION_RE.search('phosphorylated ERK')
    assert b.READOUT_PHOSPHORYLATION_RE.search('p-ERK')


@pytest.mark.parametrize("field,a,z", [
    ("dose_or_exposure", "1 mg/kg", "10 mg/kg"),
    ("tissue_or_sample", "hippocampus", "caudate"),
    ("matrix", "serum", "urine"),
    ("sampling_time_or_window", "1 hour", "8 hours"),
    ("timepoint_or_phase", "preparation", "integration"),
    ("compound_or_exposure", "R-MDMA", "S-MDMA"),
    ("compound_or_exposure", "S-MDMA", "(±)-MDMA"),
    ("compound_or_exposure", "(+)-MDMA", "(-)-MDMA"),
    ("compound_or_exposure", "(+)-MDMA", "(±)-MDMA"),
])
def test_distinct_scientific_observations_have_distinct_proposition_and_conflict_ids(field, a, z):
    base = {"study_doi": "10.audit/observation", "graph_subject_label": "MDMA", "specific_readout_or_marker": "Prolactin",
            "result_direction_normalized": "increase", "evidence_locator": "Results"}
    def ids(row):
        return b.proposition_identifiers(row, "MDMA", "biomarker_readout", "Prolactin")
    first = {**base, field: a}
    assert all(x != y for x, y in zip(ids(first), ids({**base, field: z})))
    assert ids(first) == ids(copy.deepcopy(first))
    # Opposing directions in the *same* observation still share a conflict ID.
    opposite = ids({**first, "result_direction_normalized": "decrease"})
    assert ids(first)[0] != opposite[0]
    assert ids(first)[1] == opposite[1]
