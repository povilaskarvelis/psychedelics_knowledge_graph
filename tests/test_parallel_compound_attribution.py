"""Universal wording must describe each actor, not a subset or aggregate."""
import copy

import pytest

from pipeline.kg.subject_role_guards import (
    VERSION, apply_structured_subject_roles, structured_subject_role_decision,
)


def row(summary, effect="", exposure="Ketamine, phencyclidine, DMT, and psilocin"):
    return {
        "domain": "molecular_pathway_readout",
        "compound_or_exposure": exposure,
        "compound": exposure,
        "finding_summary": summary,
        "effect_or_statistic": effect,
    }


@pytest.mark.parametrize("summary,effect", [
    ("All four compounds increased the marker.", ""),
    ("Each of the four compounds increased the marker.", ""),
    ("Each compound increased the marker.", ""),
    ("All four compounds showed no significant effect versus vehicle.", ""),
    ("All four compounds evoked release but did not reach the reference's efflux level.", ""),
    ("All four compounds reduced the marker, but not significantly.", ""),
    ("All four compounds suppressed convulsions.", "Across all compounds, potency correlated with affinity."),
    ("All tested compounds produced cytotoxicity in PC12 cells at high concentrations.",
     "No significant cytotoxic effects except in PC12 cells at high concentrations."),
    ("All tested compounds produced cytotoxicity except at low concentrations.", ""),
    ("All tested compounds produced cytotoxicity except PC12 cells at low concentrations.", ""),
])
def test_explicit_each_actor_results_survive_contextual_qualifications(summary, effect):
    assert structured_subject_role_decision(row(summary, effect))["action"] == "parallel_subjects"


@pytest.mark.parametrize("summary,effect,exposure", [
    ("All tested compounds except mescaline produced significant cytotoxicity.",
     "Mescaline had no significant effect in the resazurin assay.",
     "Mescaline, 2C-B, 2C-N, mescaline-NBOMe, 25B-NBOMe, and 25N-NBOMe"),
    ("Immunoblotting showed compound-dependent increases in mature DAT protein.",
     "For WT DAT, all tested compounds except tetrahydroharmine significantly increased mature DAT protein. For K590A DAT, all except RTI-20 had an effect.",
     "Noribogaine, tetrahydroharmine, PAL-594, bicifadine, and RTI-20"),
    ("All compounds except RO 25-6981 showed anxiolytic-like effects.",
     "RO 25-6981 affected none of the measured parameters.",
     "MK-801, ketamine, S-ketamine, RO 25-6981, and citalopram"),
    ("All compounds increased the marker except compound 3.", "",
     "Ketamine, PCP, DMT, and compound 3"),
    ("All compounds increased the marker, but not PCP.", "",
     "Ketamine, PCP, and DMT"),
    ("All compounds increased the marker except mescaline in PC12 cells.", "",
     "Ketamine, PCP, and mescaline"),
    ("All compounds increased the marker with the exception of mescaline.", "",
     "Ketamine, PCP, and mescaline"),
    ("Affinity decreased in all but one example; all compounds were agonists with reduced potency.", "",
     "LSD, DMT, and psilocin"),
])
def test_mixed_compound_results_stay_in_paper_detail(summary, effect, exposure):
    source = row(summary, effect, exposure)
    before = copy.deepcopy(source)
    assert not apply_structured_subject_roles(source)
    assert source["graph_admission_status"] == "paper_detail"
    assert source["graph_admission_reason"] == "parallel_compound_result_has_exceptions"
    for field in ("compound_or_exposure", "finding_summary", "effect_or_statistic"):
        assert source[field] == before[field]


@pytest.mark.parametrize("summary,effect", [
    ("Affinity differed between the compounds.",
     "Across all tested compounds, affinity was not significantly associated with potency (Rs=0.4, p>0.1)."),
    ("Among all compounds, LSD had the greatest affinity.", ""),
    ("Not all four compounds increased the marker.", ""),
    ("All four compounds increased the marker.", "Not all four compounds increased the marker."),
    ("All other compounds increased the marker.", ""),
    ("All responsive compounds increased the marker.", ""),
    ("All compounds producing EEG activation were psychotomimetic; other compounds did not produce EEG activation.", ""),
    ("All compounds that produced EEG activation were psychotomimetic.", ""),
])
def test_aggregate_or_subset_is_not_a_universal_drug_result(summary, effect):
    decision = structured_subject_role_decision(row(summary, effect))
    assert decision["action"] == "paper_detail"
    assert decision["reason"] == "parallel_compound_result_not_universal"


def test_previously_cached_parallel_decision_is_rechecked_and_idempotent():
    source = row("All compounds except PCP increased the marker.")
    source.update(subject_role_resolution_version="structured_subject_roles_v2",
                  subject_role_resolution_action="parallel_subjects",
                  subject_role_resolution_source_value=source["compound"])
    assert not apply_structured_subject_roles(source)
    assert source["subject_role_resolution_version"] == VERSION
    assert source["graph_admission_status"] == "paper_detail"
    once = copy.deepcopy(source)
    assert not apply_structured_subject_roles(source)
    assert source == once
