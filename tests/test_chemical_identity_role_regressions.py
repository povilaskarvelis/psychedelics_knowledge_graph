"""Chemical actor roles and stereochemistry must survive identity normalization."""
import pytest
from pipeline.kg import build_evidence_tables as b


@pytest.fixture(scope='module')
def registry():
    return b.registry_lookup(b.DEFAULT_REGISTRY_PATH)


def projections(label, registry):
    row={'compound':label,'graph_subject_label':label,'graph_subject_kind':'atomic_compound','atomic_compound_candidate':label}
    match=b.graphable_subject_match(row, registry)
    return {x['label'] for x in b.overview_graph_subjects(row, match, registry)}


def test_administered_parent_is_not_replaced_by_explanatory_metabolite(registry):
    label='Oral psilocybin, 0.26 mg/kg (psilocin is its active metabolite); placebo comparator'
    assert projections(label, registry)=={'Psilocybin'}


def test_named_parent_and_named_metabolite_remain_distinct(registry):
    label='Ketamine and its active metabolite norketamine transferred into human milk after maternal ketamine infusions'
    assert projections(label, registry)=={'Ketamine','Norketamine'}


@pytest.mark.parametrize('label,expected',[
    ('NBI-98782 (active metabolite of valbenazine), administered with phencyclidine (PCP) or amphetamine (AMPH)', 'Phencyclidine'),
    ('2-methyl-6-(phenylethynyl)pyridine (mGluR5 antagonist) coadministered with phencyclidine (PCP)', 'Phencyclidine'),
    ('8-OH-DPAT coadministered with MDMA', 'MDMA'),
])
def test_other_chemical_modifier_does_not_erase_explicit_challenge(label, expected, registry):
    assert projections(label, registry)=={expected}


@pytest.mark.parametrize('label',[
    'Ketamine and its metabolites',
    'Ketamine analogue 2 coadministered with PCP',
    'Compound 2 (ketamine metabolite), administered with PCP',
    'N-MDMA', 'PCP-iminium', '4-MeO-DMT', '5-MeO-DMT analogue 20453',
    '5-MeO-DMT (analogue 20453)',
    'C-2-α-fluoro salvinorin A analog (3a)',
    '2-Br-4,5-MDMA', '2-Cl-4,5-MDMA',
    '1-(1-phenyl-4-hydroxycyclohexyl)piperidine (4-OH-cyclo PCP)',
    '[3H]FOH-PCP ([3H]-4-fluoro-1-[1-(3-hydroxyphenyl)cyclohexyl]piperidine)',
    'Methylone-derived 4-hydroxy-3-methoxy-N-methylcathinone (HMMC)',
    '5-B-2,4-DMA (DOB isomer; 5-bromo-2,4-dimethoxyamphetamine)',
    'ZC-B (3-(4-bromo-2,5-dimethoxyphenyl)azetidine; 2C-B-AZET)',
    'Seizure of a novel MDMA precursor',
])
def test_unknown_chemical_still_does_not_become_parent(label, registry):
    assert projections(label, registry)==set()


@pytest.mark.parametrize('label',['HNK','hydroxynorketamine','(2S,6S)-HNK','(2S,6S)-hydroxynorketamine'])
def test_generic_or_other_hnk_is_not_specific_registered_rr_stereoisomer(label, registry):
    assert '(2R,6R)-hydroxynorketamine' not in projections(label, registry)


@pytest.mark.parametrize('label,expected',[
    ('(2R,6R)-HNK','(2R,6R)-hydroxynorketamine'),
    ('(2R,6R)-hydroxynorketamine','(2R,6R)-hydroxynorketamine'),
    ('(R)-ketamine','R-ketamine'), ('(S)-ketamine','S-ketamine'),
    ('Phencyclidine (PCP)','Phencyclidine'),
])
def test_exact_stereo_and_nonstereo_synonyms_preserved(label, expected, registry):
    assert projections(label, registry)=={expected}


def test_stereochemical_parentheses_never_generate_generic_aliases():
    variants=b.compound_key_variants('(2R,6R)-HNK')
    assert not any(k in {'hnk','2r 6r','2r6r'} for k,_ in variants)
    assert any(k=='pcp' for k,_ in b.compound_key_variants('Phencyclidine (PCP)'))
