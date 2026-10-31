import copy
import itertools
import json

import pandas as pd

from pipeline.kg import build_evidence_tables as b
from pipeline.kg import convert_routed_extractions_to_evidence_rows as primary
from pipeline.kg import convert_review_relationship_bundles_to_evidence_rows as review


def test_generic_measurement_survives_normalization_without_becoming_a_diagnosis(tmp_path):
    row = {
        "study_doi": "10.1/plant", "study_title": "Plant content measurement",
        "domain": "general_primary", "domain_route": "general_primary",
        "compound": "Salvinorin A", "source_type": "primary", "source_item_type": "primary_item",
        "entity_or_endpoint": "Salvinorin A content (mg/g dry weight)",
        "population_or_system": "20 leaf samples", "measure_or_method": "HPLC",
        "finding_summary": "Content ranged from 0.89 to 3.70 mg/g.",
        "effect_or_statistic": "0.89–3.70 mg/g", "evidence_location": "Table 1",
        "kg_entity_kind_override": "condition_indication", "graph_entity_label": "20 leaf samples",
    }
    assert primary.infer_entity_kind(row, "general_primary") == "reported_measurement"
    assert primary.infer_entity_label(row, "reported_measurement") == row['entity_or_endpoint']
    source = tmp_path / 'rows.json'; source.write_text(json.dumps([row]))
    registry = tmp_path / 'registry.json'
    registry.write_text(json.dumps({'compounds': [{'label': 'Salvinorin A', 'aliases': []}], 'disorders': [], 'targets': []}))
    out = tmp_path / 'kg'
    b.build_tables(graph_sources={'routed_extractions': {'path': source, 'domain': 'routed', 'dataset': 'routed',
                    'default_evidence_type': 'primary_evidence', 'skip_audit': True}},
                   registry_path=registry, out_dir=out, write_duckdb=False)
    findings = pd.read_parquet(out / 'findings.parquet')
    assert len(findings) == 1
    result = findings.iloc[0]
    assert result.graph_entity_label == row['entity_or_endpoint']
    assert result.kg_entity_kind_override == 'reported_measurement'
    assert result.graph_admission_status == 'paper_detail'
    assert result.entity_or_endpoint == row['entity_or_endpoint']
    assert result.population_or_system == '20 leaf samples'
    assert result.measure_or_method == 'HPLC'
    assert not (pd.read_parquet(out/'evidence_edges.parquet').graph_admission_status == 'main_graph').any()


def test_therapy_projection_does_not_depend_on_equivalent_subject_kind():
    registry = b.registry_lookup(b.DEFAULT_REGISTRY_PATH)
    for kind in ('compound_class', 'treatment_regimen', 'paper_topic', 'exposure_context'):
        row = {'graph_subject_label': 'Psychedelic-assisted therapy', 'compound': 'Psychedelic-assisted therapy',
               'graph_subject_kind': kind, 'source_family': 'secondary_literature'}
        match = b.graphable_subject_match(row, registry)
        subjects = b.overview_graph_subjects(row, match, registry)
        assert [x['label'] for x in subjects] == ['Psychedelic-assisted therapy']
        assert row['graph_subject_label'] == 'Psychedelic-assisted therapy'
    row = {'compound': 'Experimental 3-MeO-PCP derivative', 'graph_subject_kind': 'atomic_compound'}
    match = b.graphable_subject_match(row, registry)
    assert not any(s['label'] == 'Phencyclidine' for s in b.overview_graph_subjects(row, match, registry))


def test_verified_mebufotenin_names_use_existing_molecule_not_new_drugs():
    registry = b.registry_lookup(b.DEFAULT_REGISTRY_PATH)
    for label in ('GH001', 'mebufotenin', 'Inhaled synthetic mebufotenin (GH001)'):
        row = {'compound': label, 'graph_subject_kind': 'atomic_compound'}
        subjects = b.overview_graph_subjects(row, b.graphable_subject_match(row, registry), registry)
        assert [s['label'] for s in subjects] == ['5-MeO-DMT']


def converted(anchors, **changes):
    relationship = {
        'item_id': 'R1', 'relationship_kind': 'review_synthesis', 'relationship_statement': 'A supported relationship.',
        'anchors': anchors, 'graph_form': 'atomic', 'graph_eligibility': 'main_graph',
        'paper_prominence': 'major_supporting', 'evidence_stratum': 'human', 'domain_labels': ['clinical_outcome'],
        'evidence_locators': [], 'limitations': [], 'covers_major_aspect_ids': [],
    }
    relationship.update(changes)
    bundle = {'study_doi': '10.1/review', 'study_title': 'Pharmacological approaches', 'status': 'ok',
              'result': {'paper_frame': {'primary_subjects': []}, 'relationships': [relationship]}}
    tasks = [{'study_doi': '10.1/review', 'paper_metadata': {'review_type': 'review'}}]
    registry = {'compounds': [{'label': 'Ketamine', 'aliases': []}, {'label': 'LSD', 'aliases': []}], 'targets': [], 'disorders': []}
    return review.convert_bundles([bundle], tasks, registry, active_candidate_dois={'10.1/review'})[0][0]


def test_unique_scoped_subject_is_invariant_to_anchor_order():
    anchors = [{'role': 'compound', 'label': 'Mirtazapine'}, {'role': 'compound', 'label': 'Ketamine'},
               {'role': 'condition', 'label': 'Depression'}]
    for permutation in itertools.permutations(anchors):
        row = converted(list(permutation))
        assert row['graph_subject_label'] == 'Ketamine'
        assert row['graph_entity_label'] == 'Depression'
        assert row['review_scope_status'] == 'in_scope'
        assert row['graph_admission_status'] == 'main_graph'


def test_comparator_alone_does_not_resurrect_review_scope():
    row = converted([{'role': 'compound', 'label': 'Mirtazapine'},
                     {'role': 'comparator', 'label': 'Ketamine'}, {'role': 'condition', 'label': 'Depression'}])
    assert row['review_scope_status'] == 'psychedelics_peripheral_or_absent'
    assert row['graph_admission_status'] == 'paper_detail'


def test_ambiguous_newly_recovered_subjects_are_not_split_into_drug_effects():
    row = converted([{'role': 'compound', 'label': 'Mirtazapine'}, {'role': 'compound', 'label': 'Ketamine'},
                     {'role': 'compound', 'label': 'LSD'}, {'role': 'outcome', 'label': 'Mood'}])
    assert row['graph_subject_label'] == 'Ketamine / LSD'
    assert row['graph_admission_status'] == 'paper_detail'
    assert row['graph_admission_reason'] == 'review_multiple_drug_subjects_requires_attribution'


def test_nonhuman_review_outcomes_do_not_become_patient_symptoms():
    row = converted([{'role': 'compound', 'label': 'Ketamine'}, {'role': 'outcome', 'label': 'Web-building behavior'}],
                    evidence_stratum='preclinical', domain_labels=['cognitive_behavioral'])
    assert row['domain'] == 'cognitive_behavioral'
    assert row['kg_entity_kind_override'] == 'cognitive_behavioral_construct'
    # Safety outcomes in animals must not be suppressed by a blanket rule.
    row = converted([{'role': 'compound', 'label': 'Ketamine'}, {'role': 'outcome', 'label': 'Hyperthermia'}],
                    evidence_stratum='preclinical', domain_labels=['safety_tolerability'])
    assert row['kg_entity_kind_override'] != 'reported_measurement'
    assert row['graph_admission_reason'] != 'generic_measurement_requires_domain_mapping'


def test_combination_and_explicit_detail_restrictions_remain():
    row = converted([{'role': 'compound', 'label': 'Ketamine'}, {'role': 'compound', 'label': 'LSD'},
                     {'role': 'condition', 'label': 'Depression'}], graph_form='combination')
    assert row['graph_subject_kind'] == 'compound_combination'
    assert row['graph_subject_label'] == 'Ketamine + LSD'
    row = converted([{'role': 'compound', 'label': 'Mirtazapine'}, {'role': 'compound', 'label': 'Ketamine'},
                     {'role': 'condition', 'label': 'Depression'}],
                    graph_eligibility='paper_detail_only', paper_prominence='secondary_context')
    assert row['graph_admission_status'] == 'paper_detail'
