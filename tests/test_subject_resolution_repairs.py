"""Absent, negated and context-only compound mentions are not finding subjects.

A compound that a finding names only to deny it ("no psilocybin"), or only as
the parent trial of a placebo or baseline result, did not produce that result.
Null results for a tested compound, and tested comparator arms, keep their
compound links.
"""
import pytest

from pipeline.kg import build_evidence_tables as b
from pipeline.kg import convert_routed_extractions_to_evidence_rows as c


@pytest.fixture(scope="module")
def registry():
    return b.registry_lookup(b.DEFAULT_REGISTRY_PATH)


def overview_labels(row: dict, registry) -> list[str]:
    c.apply_graph_subject(row)
    match = b.graphable_subject_match(row, registry)
    if not match["matched"]:
        return []
    return [subject["label"] for subject in b.overview_graph_subjects(row, match, registry)]


@pytest.mark.parametrize("exposure", [
    "SAPAP3 knockout genotype (HOM vs WT); vehicle-treated, no psilocybin",
    "No ketamine exposure; sex comparison in embryonic mice from unexposed pregnancies",
    "Acute inescapable footshock stress; no ketamine",
    "P2X7R genetic deficiency (no acute PCP challenge during recording)",
    "Postpartum reproductive state; no psilocybin treatment was reported for this expression comparison",
    "Naturally occurring depression in cynomolgus macaques; compared with healthy monkeys. "
    "The abstract does not report a ketamine-related change in this readout.",
    "Intravenous racemic ketamine trial context; saline placebo",
    "Ketamine trial context: 0.5 mg/kg IV ketamine versus saline placebo in a double-blind, placebo-controlled "
    "crossover trial; imaging findings reported here are primarily baseline findings.",
    "Eugenol alone, with psilocybin/eugenol combinations as context",
    # The parent name inside a denied longer name is denied with it.
    "Saline vehicle; no 5-MeO-DMT",
    # An exclusion that opens a list covers every listed name.
    "Glutamatergic modulators other than racemic ketamine and esketamine",
])
def test_absent_or_context_only_compound_is_not_a_subject(exposure, registry):
    assert b.registry_compound_labels_in_text(exposure, registry) == set()
    assert overview_labels({"compound": exposure}, registry) == []


@pytest.mark.parametrize("text,label", [
    ("There was no psilocybin effect on BDNF", "Psilocybin"),
    ("No ketamine-induced increase in locomotion was observed", "Ketamine"),
    ("Perioperative esketamine (0.5 mg/kg), compared with no perioperative esketamine", "S-ketamine"),
    ("Ketamine, 1 mg/kg intravenously daily for 13 weeks; no ketamine administered during the 24 hours before DTI scanning", "Ketamine"),
    ("Psilocybin-assisted therapy (PAT) and trial context", "Psilocybin"),
    # Both conditions were studied, so the compound was given.
    ("Acute desipramine, amitriptyline, iprindole, or alaproclate, with or without "
     "5-methoxy-N,N-dimethyltryptamine (5-MeODMT)", "5-MeO-DMT"),
    ("NMDA receptor currents in the presence or absence of ketamine", "Ketamine"),
    # A real-world study of not using a drug is a study of that drug.
    ("Non-use of ecstasy despite practical opportunity", "MDMA"),
    # "Non-" negates the route; results not split by drug still include the drug.
    ("Non-intranasal esketamine", "S-ketamine"),
    ("Cumulative stimulant use (smoked or inhaled cocaine, methamphetamine, and ecstasy; "
     "not reported separately by substance)", "MDMA"),
])
def test_null_result_or_affirmative_mention_keeps_the_compound(text, label, registry):
    assert label in b.registry_compound_labels_in_text(text, registry)


def test_both_conditions_keep_the_specific_compound_and_not_its_parent(registry):
    exposure = ("Acute desipramine, amitriptyline, iprindole, or alaproclate, with or without "
                "5-methoxy-N,N-dimethyltryptamine (5-MeODMT)")
    labels = b.prune_compound_text_labels(
        b.chemical_identity_surface(exposure), b.registry_compound_labels_in_text(exposure, registry))
    assert labels == {"5-MeO-DMT"}


def test_bolus_then_infusion_is_a_dosing_schedule_not_a_drug_sequence(registry):
    row = {"compound": "(S)-ketamine and racemic (R/S)-ketamine",
           "dose": "(S)-ketamine: 0.1 mg/kg IV bolus over 5 minutes followed by 0.006 mg/kg/min infusion for 60 minutes. "
                   "(R/S)-ketamine: 0.2 mg/kg IV bolus over 5 minutes followed by 0.012 mg/kg/min infusion for 60 minutes."}
    assert sorted(overview_labels(row, registry)) == ["Ketamine", "S-ketamine"]
    for exposure in (
        "Intravenous ketamine followed by psilocybin",
        "Subchronic phencyclidine (PCP; 10 mg/kg for 10 days), followed by a 5-day washout and a single "
        "2,5-dimethoxy-4-iodoamphetamine (DOI) challenge",
        "Harmaline (15 mg/kg) followed by 5-MeO-DMT (2 mg/kg)",
    ):
        sequence = {"compound": exposure}
        c.apply_graph_subject(sequence)
        match = b.graphable_subject_match(sequence, registry)
        subjects = b.overview_graph_subjects(sequence, match, registry)
        assert [s["kind"] for s in subjects] == ["treatment_regimen"], exposure
        assert subjects[0]["label"].endswith("(sequential)"), exposure


@pytest.mark.parametrize("text,expected", [
    ("Seized illegal ATS tablets containing active ingredients other than MDMA, MDA, or MDEA.", set()),
    ("Psychoactive tryptamines other than psilocybin and ibogaine", set()),
    ("Esketamine and racemic ketamine", {"S-ketamine", "Ketamine"}),
    ("Antidepressants other than ketamine; psilocybin 25 mg", {"Psilocybin"}),
    ("Use of psychedelics other than LSD and LSD", {"LSD"}),
    ("Glutamate-system modulators other than ketamine / Ketamine", {"Ketamine"}),
])
def test_exclusion_list_covers_listed_names_only(text, expected, registry):
    assert b.registry_compound_labels_in_text(text, registry) == expected


def test_named_enantiomers_do_not_add_racemic_ketamine(registry):
    exposure = ("S-ketamine (10 mg/kg, intraperitoneal) with LPS (0.83 mg/kg, intraperitoneal); "
                "R-ketamine (10 mg/kg) comparison")
    labels = b.prune_compound_text_labels(
        b.chemical_identity_surface(exposure), b.registry_compound_labels_in_text(exposure, registry))
    assert labels == {"S-ketamine", "R-ketamine"}
    row = {"compound": exposure,
           "finding_summary": "LPS increased serum TNF-alpha. S-ketamine reduced this increase, "
                              "whereas R-ketamine at the same dose did not."}
    # Both tested enantiomers keep their links; racemic ketamine was not tested.
    assert sorted(overview_labels(row, registry)) == ["R-ketamine", "S-ketamine"]


@pytest.mark.parametrize("exposure,expected", [
    ("S-ketamine and ketamine", {"S-ketamine", "Ketamine"}),
    ("(R,S)-ketamine", {"Ketamine"}),
    ("5-MeO-DMT and DMT", {"5-MeO-DMT", "DMT"}),
])
def test_parent_compound_needs_its_own_mention(exposure, expected, registry):
    labels = b.prune_compound_text_labels(
        b.chemical_identity_surface(exposure), b.registry_compound_labels_in_text(exposure, registry))
    assert labels == expected


def test_focal_compound_from_negated_text_is_not_a_subject(registry):
    exposure = "5-HTT deficiency (+/− and −/− genotypes); no DOI treatment in these assays"
    row = {"compound": exposure, "graph_subject_kind": "compound_combination", "atomic_compound_candidate": "DOI"}
    match = b.graphable_subject_match(row, registry)
    assert match["matched"]
    assert b.overview_graph_subjects(row, match, registry) == []


@pytest.mark.parametrize("exposure", [
    "Postmortem MDD status; no psychedelic exposure",
    "5-HT2A receptor localization; no drug administration or psychedelic exposure",
])
def test_negated_class_is_not_a_class_subject(exposure, registry):
    row = {"compound": exposure, "graph_subject_kind": "compound_class", "atomic_compound_candidate": exposure}
    match = b.graphable_subject_match(row, registry)
    assert match["matched"]
    assert b.overview_graph_subjects(row, match, registry) == []


def test_affirmative_class_with_unexposed_comparison_keeps_the_class(registry):
    exposure = "Lifetime naturalistic classic psychedelic use, compared with no lifetime psychedelic use"
    row = {"compound": exposure, "graph_subject_kind": "compound_class", "atomic_compound_candidate": exposure}
    match = b.graphable_subject_match(row, registry)
    assert [s["label"] for s in b.overview_graph_subjects(row, match, registry)] == ["Classic psychedelics"]


@pytest.mark.parametrize("exposure,label", [
    ("Repetitive transcranial magnetic stimulation (rTMS) versus esketamine", "S-ketamine"),
    ("ECT compared with parenteral racemic ketamine", "Ketamine"),
])
def test_tested_comparator_arm_keeps_its_link(exposure, label, registry):
    assert overview_labels({"compound": exposure}, registry) == [label]
