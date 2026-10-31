"""Preserve independently affirmed registered actors without aliasing analogues."""
import pytest
from pipeline.kg import build_evidence_tables as b


@pytest.fixture(scope='module')
def registry():
    return b.registry_lookup(b.DEFAULT_REGISTRY_PATH)


def row(exposure, statement, **extra):
    return {'source_type': 'primary', 'paper_assessment_route': 'primary_evidence',
            'domain': 'molecular_pathway_readout', 'compound': exposure,
            'graph_subject_kind': 'compound_combination', 'finding_summary': statement, **extra}


def labels(record, registry):
    match = b.graphable_subject_match(record, registry)
    return {s['label'] for s in b.overview_graph_subjects(record, match, registry)}


def test_independently_named_dmt_result_is_not_lost_with_analogues(registry):
    r = row('DMT (1), 1-Me-DMT (27), and isoDMT (2)',
            'DMT, 1-Me-DMT, and isoDMT increased dendritic arbor complexity relative to vehicle. '
            '1-Me-DMT and isoDMT produced effects comparable to DMT, indicating that an indole N–H bond was not required for this structural plasticity readout.')
    assert labels(r, registry) == {'DMT'}
    assert r['compound'] == 'DMT (1), 1-Me-DMT (27), and isoDMT (2)'


def test_affirmative_shared_null_is_not_discarded(registry):
    assert labels(row('DMT, 1-Me-DMT, and isoDMT', 'DMT, 1-Me-DMT, and isoDMT did not increase dendritic complexity.'), registry) == {'DMT'}


@pytest.mark.parametrize('exposure,statement', [
    ('1-Me-DMT and isoDMT', '1-Me-DMT and isoDMT increased complexity compared with DMT.'),
    ('DMT (1), 1-Me-DMT (27), and isoDMT (2)', '1-Me-DMT and isoDMT increased complexity compared with DMT.'),
    ('DMT, 1-Me-DMT, and isoDMT', 'Some compounds increased dendritic complexity.'),
    ('DMT, 1-Me-DMT, and isoDMT', 'DMT, 1-Me-DMT, and isoDMT increased complexity, except DMT.'),
    ('DMT, 1-Me-DMT, and isoDMT', 'DMT, 1-Me-DMT, and isoDMT increased complexity, but only isoDMT reached significance.'),
    ('DMT, 1-Me-DMT, and isoDMT', 'DMT, 1-Me-DMT, and isoDMT increased complexity as a combined mixture.'),
    ('DMT versus isoDMT', 'DMT versus isoDMT increased complexity.'),
    ('Compound 4e (a psilocin derivative) and 1-Me-DMT', 'Compound 4e and 1-Me-DMT increased complexity.'),
    ('5-MeO-DMT (28) versus 5-MeO-isoDMT (6), and 6-F-DMT (29) versus the analogous isoDMT (13)',
     'The isoDMT analogues 6 and 13 produced dendritic-arbor-complexity effects comparable to their DMT isosteres 28 and 29, respectively.'),
])
def test_no_parent_inference_from_unknown_comparator_subset_or_mixture(exposure, statement, registry):
    assert b.explicit_parallel_registered_subjects(row(exposure, statement), registry) == []


@pytest.mark.parametrize('extra', [
    {'source_type': 'review', 'paper_assessment_route': 'review'},
    {'meta_analysis_subject_scope': 'pooled_multiple_interventions'},
    {'graph_admission_status': 'paper_detail', 'graph_admission_reason': 'parallel_compound_result_has_exceptions'},
])
def test_existing_scope_and_detail_limits_are_preserved(extra, registry):
    assert b.explicit_parallel_registered_subjects(row('DMT, 1-Me-DMT, and isoDMT',
             'DMT, 1-Me-DMT, and isoDMT increased dendritic complexity.', **extra), registry) == []
