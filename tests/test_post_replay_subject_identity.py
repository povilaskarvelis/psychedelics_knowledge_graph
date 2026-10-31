"""Release-loss controls for explicit identities, source units and class estimates."""
import pytest
from pipeline.kg import build_evidence_tables as b


@pytest.fixture(scope='module')
def registry():
    return b.registry_lookup(b.DEFAULT_REGISTRY_PATH)


def projections(label, registry, **extra):
    row = {'compound': label, 'graph_subject_label': label,
           'graph_subject_kind': 'atomic_compound', 'atomic_compound_candidate': label, **extra}
    match = b.graphable_subject_match(row, registry)
    return {x['label'] for x in b.overview_graph_subjects(row, match, registry)}


@pytest.mark.parametrize('label,expected', [
    ('5-Methoxy-N,N-di(iso)propyltryptamine hydrochloride (5-MeO-DIPT; Foxy)', '5-MeO-DiPT'),
    ('5-methoxy-diisopropyltryptamine (5-MEO-DIPT; foxy), 20 mg/kg', '5-MeO-DiPT'),
    ('5-methoxy-N,N-dimethyl tryptamine (5MeO-DMT)', '5-MeO-DMT'),
    ('5-methoxy dimethyltryptamine', '5-MeO-DMT'),
    ('5-methoxy-N-methyl-N-isopropyltryptamine (5-MeO-MiPT)', '5-MeO-MiPT'),
    ('2,5-dimethoxy-4-methyl-amphetamine (STP)', 'DOM'),
    ('2-bromo-D lysergic acid diethylamide (BOL)', '2-bromo-LSD'),
    ('(2 R,6 R)-hydroxynorketamine (RANK)', '(2R,6R)-hydroxynorketamine'),
    ('(R)-DOI·HCl, continuous subcutaneous infusion (0.15 μg/hr) during high-fat diet feeding', 'DOI'),
    ('BNN27 (synthetic dehydroepiandrosterone analogue) with anesthetic ketamine', 'Ketamine'),
    ('N,N-dimethyltryptamine (DMT), measured as a naturally occurring plant metabolite', 'DMT'),
    ('Daily wastewater mass loads of MDMA compared with mobile-phone-derived population estimates', 'MDMA'),
    ('Wastewater-derived estimate of ketamine consumption', 'Ketamine'),
    ('Psilocin (PSI) derived from compound 4e', 'Psilocin'),
    ('Psilocin (PSI) derived from psilocybin (PSY)', 'Psilocin'),
    ('DOI (5-HT2 agonist) following dopamine lesions', 'DOI'),
    ('DOI (5-HT2 agonist); effects on Arc expression were blocked by the antagonist MDL 100,907', 'DOI'),
])
def test_verified_identity_and_source_role_are_preserved(label, expected, registry):
    assert projections(label, registry) == {expected}


@pytest.mark.parametrize('label', [
    '4-fluoro-5-methoxy-N,N-dimethyltryptamine',
    '5-methoxy-N,N-dimethyltryptamine analogue 20453',
    'Psilocin (analogue 4e)',
    'Compound 4e (a psilocin derivative) with ketamine',
    'N-MDMA', 'PCP-iminium',
    'cis- and trans-3-phenyl-3-piperidinylbicyclo[3.1.0]hexane (analogues 1 and 2), compared with phencyclidine (PCP)',
    'Endogenous porcine brain factor with PCP-like activity, proposed to be a small peptide and endogenous ligand for the PCP receptor',
    'N,N-dimethyltryptamine (DMT) metabolites',
    '3,4-methylenedioxymethamphetamine (MDMA, Ecstasy) and related amphetamine derivatives',
    '5-MeO-DiPT and 5-OH-DiPT',
    '5-Methoxy-N,N-diisopropyltryptamine (5-MeO-DIPT), 5-hydroxy-N,N-diisopropyltryptamine (5-OH-DIPT), and 5-methoxy-N,N-isopropyltryptamine (5-MeO-IPT)',
])
def test_modified_identity_does_not_acquire_the_parent(label, registry):
    assert projections(label, registry) == set()


def test_spaced_other_stereoisomer_does_not_become_rr(registry):
    assert '(2R,6R)-hydroxynorketamine' not in projections('(2 S,6 S)-hydroxynorketamine (SHANK)', registry)
    assert '(2R,6R)-hydroxynorketamine' not in projections('hydroxynorketamine (HNK)', registry)


def test_separate_dipt_remains_separate_from_5_meo_dipt(registry):
    assert projections('5-MeO-DiPT and DiPT', registry) == {'5-MeO-DiPT', 'DiPT'}


def test_unrelated_prefixed_comparator_does_not_modify_later_drug(registry):
    assert not b.compound_name_is_only_a_reference('Lisuride (0.03 mg/kg s.c.) or 8-OH-DPAT (1 mg/kg s.c.) before LSD (0.1 mg/kg s.c.)', registry)


def test_registered_parent_and_named_registered_derivative_remain_distinct(registry):
    assert projections('Lysergic acid diethylamide (LSD) and 2-bromo-lysergic acid diethylamide (BOL)', registry) == {'LSD', '2-bromo-LSD'}


@pytest.mark.parametrize('label', [
    'DOI as comparator; effects on memory were measured after ketamine',
    'Effects on memory following lesions; DOI was discussed as background',
    'DOI (5-HT2 agonist) and ketamine following dopamine lesions',
    'DOI (5-HT2 agonist); effects on memory were measured after ketamine',
    'DOI (5-HT2 agonist); effects on memory were discussed as background, not administered',
])
def test_descriptor_does_not_claim_context_or_another_actor(label, registry):
    assert b.specific_compound_descriptor(label, registry) == ''


def test_pooled_therapy_is_preserved_as_existing_therapy_class(registry):
    assert projections('Psychedelic treatment or psychedelic-assisted therapy', registry,
                       meta_analysis_subject_scope='pooled_multiple_interventions') == {'Psychedelic-assisted therapy'}


@pytest.mark.parametrize('label', [
    'Psychedelic treatment or antidepressant therapy',
    'Ketamine or psychedelic-assisted therapy',
])
def test_therapy_class_does_not_absorb_other_treatment_categories(label, registry):
    assert projections(label, registry, meta_analysis_subject_scope='pooled_multiple_interventions') == set()
