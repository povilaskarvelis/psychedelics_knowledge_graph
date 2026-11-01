"""Every compound searched as in scope must resolve to its own registry identity."""
import pytest

from pipeline.kg import build_evidence_tables as b
from pipeline.kg import convert_routed_extractions_to_evidence_rows as c
from pipeline.review.deterministic_prescreen_rules import PIPELINE_CONFIG_PATH, parse_allowlists

SCOPE_COMPOUNDS = parse_allowlists(PIPELINE_CONFIG_PATH)["allowed_compounds"]
# Searched for completeness, but registered as a non-hallucinogenic comparator.
COMPARATOR_SCOPE_COMPOUNDS = {"Lisuride"}


@pytest.fixture(scope="module")
def registry():
    return b.registry_lookup(b.DEFAULT_REGISTRY_PATH)


def test_scope_list_is_loaded():
    assert len(SCOPE_COMPOUNDS) >= 54


@pytest.mark.parametrize("name", SCOPE_COMPOUNDS)
def test_scope_compound_resolves_to_a_graph_node(name, registry):
    label, item = b.canonicalize_registry_label("compound", name, registry)
    assert item, f"{name} is in allowed_compounds but missing from the entity registry"
    if name not in COMPARATOR_SCOPE_COMPOUNDS:
        assert b.graph_scope_blocked_compound_result(label, item) is None


@pytest.mark.parametrize("raw,label", [
    ("1P-LSD", "1P-LSD"),
    ("AL-LAD (6-allyl-6-nor-LSD)", "AL-LAD"),
    ("ETH-LAD (6-ethyl-6-nor-lysergic acid diethylamide)", "ETH-LAD"),
    ("PRO-LAD", "PRO-LAD"),
    ("2,5-dimethoxy-4-chloroamphetamine (DOC)", "DOC"),
    ("DOET (4-ethyl-2,5-dimethoxyamphetamine)", "DOET"),
    ("AMT", "Alpha-methyltryptamine"),
    ("α-methyltryptamine (AMT)", "Alpha-methyltryptamine"),
    ("5-Methoxy-α-methyltryptamine (5-MeO-AMT)", "5-MeO-AMT"),
    ("miprocin (4-HO-MiPT)", "4-HO-MiPT"),
    ("2C-T-7", "2C-T-7"),
    ("25B-NBOH", "25B-NBOH"),
])
def test_registered_compound_keeps_its_own_node(raw, label, registry):
    row = {"compound": raw}
    c.apply_graph_subject(row)
    match = b.graphable_subject_match(row, registry)
    assert [x["label"] for x in b.overview_graph_subjects(row, match, registry)] == [label]


@pytest.mark.parametrize("raw", ["1P-AL-LAD", "1cP-LSD", "2C-T-7-FLY", "5-Hydroxy-α-methyltryptamine"])
def test_prodrug_or_analogue_is_not_its_registered_parent(raw, registry):
    row = {"compound": raw}
    c.apply_graph_subject(row)
    match = b.graphable_subject_match(row, registry)
    assert b.overview_graph_subjects(row, match, registry) == []


@pytest.mark.parametrize("raw,expected", [
    ("1P-LSD", {"1P-LSD"}),
    ("LSD/1P-LSD", {"LSD", "1P-LSD"}),
    ("5-MeO-AMT", {"5-MeO-AMT"}),
    ("AMT and 5-MeO-AMT", {"Alpha-methyltryptamine", "5-MeO-AMT"}),
])
def test_registered_name_does_not_add_the_name_it_contains(raw, expected, registry):
    assert b.prune_compound_text_labels(raw, b.registry_compound_labels_in_text(raw, registry)) == expected


@pytest.mark.parametrize("raw,expected", [
    ("25B-NBOH exposure; powder sold as powdered LSD", {"25B-NBOH"}),
    ("2,5-dimethoxy-4-chloroamphetamine (DOC), in powder presented as LSD", {"DOC"}),
    ("2C-P, detected after ingestion of a substance reportedly sold as 2C-B", {"2C-P"}),
    # Without a named actual substance before the cue, every listed name stays.
    ("Samples advertised as ketamine, alprazolam, or 2C-B", {"Ketamine", "2C-B"}),
    ("LSD and 1P-LSD sold as LSD", {"LSD", "1P-LSD"}),
])
def test_marketed_identity_is_not_the_exposure(raw, expected, registry):
    assert b.registry_compound_labels_in_text(raw, registry) == expected


@pytest.mark.parametrize("raw,label", [
    ("recurrent depressive disorder", "Major depressive disorder"),
    ("difficult-to-treat depression", "Major depressive disorder"),
    ("methamphetamine use disorder", "Methamphetamine use disorder"),
])
def test_condition_alias_names_the_same_condition(raw, label, registry):
    assert b.canonicalize_registry_label("clinical_entity", raw, registry)[0] == label


def test_substance_use_is_not_a_use_disorder(registry):
    assert b.canonicalize_registry_label("clinical_entity", "methamphetamine use", registry)[1] is None
