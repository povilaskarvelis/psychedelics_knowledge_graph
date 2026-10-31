import json
from pathlib import Path

import pandas as pd
import pytest

from pipeline.kg import build_evidence_tables as b
from pipeline.kg.target_identity import (
    predicted_target_detail_reason, recovered_target_detail_reason, target_subject_detail_reason,
    single_registered_target,
)


@pytest.fixture(scope="module")
def registry():
    return b.registry_lookup(b.DEFAULT_REGISTRY_PATH)


@pytest.mark.parametrize("text,expected", [
    ("Nicotinic acetylcholine receptor", "Nicotinic acetylcholine receptor family"),
    ("Ionic channel of the nicotinic acetylcholine receptor", "Nicotinic acetylcholine receptor family"),
    ("Nicotinic acetylcholine receptor-associated ion channel", "Nicotinic acetylcholine receptor family"),
    ("Muscarinic cholinergic receptor binding site", "Muscarinic receptor family"),
    ("Voltage-sensitive Na+ channel", "Voltage-gated sodium channel family"),
    ("human vesicular monoamine transporter 1 (hVMAT1)", "VMAT1 (SLC18A1)"),
    ("human vesicular monoamine transporter 2 (hVMAT2)", "VMAT2 (SLC18A2)"),
    ("rat m1 muscarinic acetylcholine receptor", "M1 muscarinic receptor (CHRM1)"),
    ("Histamine H1 receptor", "Histamine H1 receptor (HRH1)"),
    ("β3-adrenergic receptor (β3-AR)", "beta3 adrenoceptor (ADRB3)"),
    ("mGlu3 metabotropic glutamate receptor", "mGluR3 (GRM3)"),
    ("H3 histamine receptor", "Histamine H3 receptor (HRH3)"),
    ("D5 dopamine receptor", "Dopamine D5 receptor (DRD5)"),
    ("α2B-adrenoceptor binding site", "alpha2B adrenoceptor (ADRA2B)"),
])
def test_complete_names_resolve_without_changing_subtypes(text, expected, registry):
    match = b.match_registry_entity(text, "target", registry)
    assert match["matched"]
    assert match["label"] == expected


@pytest.mark.parametrize("text", [
    "PCP binding sites", "Phencyclidine (PCP) binding sites", "PCP receptor",
    "Histamine H1 receptor mutant Y108A", "Histamine H1 receptor and H3 receptor",
    "Human vesicular monoamine transporter 3 (hVMAT3)",
    "M1 muscarinic receptor (CHRM2)", "α2D-adrenoceptor",
    "Nicotinic acetylcholine receptor unknown alpha9beta7 subtype",
    "Nicotinic acetylcholine receptor alpha subunit",
    "Nicotinic acetylcholine receptor heteromer", "Non-NMDA receptor",
    "Human dopamine transporter (hDAT; mutant T356M)",
])
def test_complete_parser_preserves_unresolved_identity(text, registry):
    assert single_registered_target(b.label_key(text), registry,
        b.DIRECT_TARGET_REGISTRY_STATUSES | b.TARGET_FAMILY_REGISTRY_STATUSES) is None
    if text.startswith(("Histamine", "M1", "α2D")):
        assert not b.match_registry_entity(text, "target", registry)["matched"]


@pytest.mark.parametrize("assay", [
    "Radioligand competition; no detectable affinity", "Whole-cell patch-clamp",
    "Ca2+-activated Cl- current response to acetyl-beta-methylcholine measured by two-electrode voltage clamp",
    "TRUPATH Gq BRET concentration-response assay", "IP1 accumulation assay",
    "In vitro enzyme inhibition assay", "Cellular thermal shift assay (CETSA)",
    "Single-channel current recording", "Endplate current recording",
    "Inhibition of carbamylcholine-elicited 22Na flux",
])
def test_direct_assay_methods_are_not_limited_to_binding_word(assay):
    assert not recovered_target_detail_reason({"source_item_type":"primary_item", "assay_type":assay})


@pytest.mark.parametrize("assay", [
    "Antagonist pretreatment followed by locomotor behavior",
    "Receptor knockdown followed by radioligand binding",
    "Molecular docking and predicted binding", "not_reported",
])
def test_identity_recovery_does_not_establish_direct_evidence(assay):
    assert recovered_target_detail_reason({"source_item_type":"primary_item", "assay_type":assay})


def test_prediction_gate_uses_this_observation_not_other_paper_methods():
    base = {"source_item_type":"primary_item", "assay_type":"Radioligand binding", "study_title":"Docking and binding"}
    assert not predicted_target_detail_reason(base)
    assert not predicted_target_detail_reason({**base,"experimental_system_category":"mixed_or_unclear"})
    assert predicted_target_detail_reason({**base,"experimental_system_category":"computational"})
    assert not predicted_target_detail_reason({**base,"source_item_type":"review_relationship","experimental_system_category":"computational"})


def test_saved_assays_preserve_results_and_source_qualifiers(tmp_path):
    fixtures = Path(__file__).parent / "fixtures/target_followup_saved_rows.json"
    rows = json.loads(fixtures.read_text())
    b.build_tables(out_dir=tmp_path, write_duckdb=False,
        graph_sources={"routed_extractions":{"path":fixtures,"domain":"routed","dataset":"routed",
        "default_evidence_type":"primary_evidence","skip_audit":True}})
    findings = pd.read_parquet(tmp_path / "findings.parquet").fillna("")
    original = {(r["task_id"],str(r["source_item_index"])):r for r in rows}
    assert findings.finding_id.is_unique
    modified_subjects_checked = 0
    for row in findings.to_dict("records"):
        raw = json.loads(row["raw_row_json"])
        old = original[(raw["task_id"],str(raw["source_item_index"]))]
        if target_subject_detail_reason(raw):
            assert row["graph_admission_status"] == "paper_detail"
            assert row["graph_admission_reason"] == "target_subject_requires_exact_identity"
            modified_subjects_checked += 1
        for field in ["target","target_type","assay_type","finding_summary","support","metric","value","unit",
                      "effect_or_statistic","evidence_locator","evidence_location","comparator_or_reference","species_or_cell_line"]:
            assert raw.get(field) == old.get(field), (row["study_doi"],field)
    assert modified_subjects_checked >= 6
    direct = findings[findings.study_doi.isin(["10.1097/00000542-199706000-00014","10.1073/pnas.93.10.5166"])]
    assert len(direct) >= 6
    mixtures = direct[direct.raw_row_json.str.contains('ketamine mixture')]
    assert len(mixtures) == 2
    assert mixtures.graph_admission_reason.eq("target_subject_requires_exact_identity").all()
    single = direct[~direct.index.isin(mixtures.index)]
    assert single[single.graph_overview_subject_label.ne("")].graph_admission_status.eq("main_graph").all()
    expression = findings[findings.study_doi.eq("10.5213/inj.1632634.317")]
    assert len(expression) >= 2
    assert expression.domain.eq("molecular_pathway_readout").all()
    assert expression.graph_admission_status.eq("main_graph").all()
    predicted = findings[findings.study_doi.eq("10.1002/1873-3468.15099")]
    assert len(predicted)
    assert predicted.graph_admission_status.eq("paper_detail").all()
    assert predicted.graph_admission_reason.eq("predicted_target_requires_experimental_validation").all()


def test_historical_pcp_sites_are_literal_detail_not_nmda(registry):
    for target in ["PCP binding sites", "Phencyclidine (PCP) binding sites", "PCP receptor"]:
        result=b.match_registry_entity(target,"target",registry)
        assert result["matched"] and result["label"]==target
        assert result["match_type"]=="historical_target_site_detail_only"


def test_receptor_plus_unresolved_site_stays_one_observation(registry):
    target = "Glutamate NMDA receptor, MK-801 binding site (PCP site)"
    rows = json.loads((Path(__file__).parent / "fixtures/target_followup_saved_rows.json").read_text())
    row = next(row for row in rows if row.get("target") == target)
    assert b.graphable_subject_match(row, registry)["matched"]
    actual = b.entity_expanded_rows(row, "molecular_target", registry,
                                    b.node_vocabulary_lookup(b.DEFAULT_NODE_VOCABULARY_PATH))
    assert actual == [row]
    assert actual[0]["target"] == target


@pytest.mark.parametrize("subject,canonical", [
    ("α,α,β,β-tetradeutero-5-MeO-DMT", "5-MeO-DMT"),
    ("9i (D2-DMT) and 7 (DMT)", "DMT"),
    ("m-Amino-PCP", "Phencyclidine"),
    ("m-Nitro-PCP", "Phencyclidine"),
    ("R(-)/S(+) ketamine mixture", "S-ketamine"),
])
def test_modified_subject_cannot_become_parent_target_evidence(subject, canonical):
    row = {"source_item_type": "primary_item", "compound_original": subject,
           "compound": canonical, "graph_subject_kind": "atomic_compound"}
    assert target_subject_detail_reason(row) == "target_subject_requires_exact_identity"


def test_subject_qualifier_does_not_read_title_or_comparator():
    row = {"source_item_type": "primary_item", "compound_original": "5-MeO-DMT", "compound": "5-MeO-DMT",
           "study_title": "Deuterated 5-MeO-DMT", "comparator": "tetradeutero-5-MeO-DMT"}
    assert not target_subject_detail_reason(row)
    for subject, canonical in [("Psilocybin preceded by eticlopride (D2 antagonist)", "Psilocybin"),
                               ("Ketamine (R,S-ketamine mixture)", "Ketamine"),
                               ("APV (2-amino-5-phosphonovalerate); ketamine", "Ketamine")]:
        assert not target_subject_detail_reason({**row, "compound_original": subject, "compound": canonical,
                                                 "graph_subject_kind": "atomic_compound"})
    assert not target_subject_detail_reason({**row, "compound_original": "m-Nitro-PCP", "compound": "m-Nitro-PCP"})


def test_availability_binding_assay_is_not_direct_binding_of_drug():
    row = {"source_item_type": "primary_item", "target_type": "receptor binding-site availability",
           "assay_type": "Specific radioligand binding assay"}
    assert recovered_target_detail_reason(row) == "target_mechanism_without_direct_assay"


def test_target_action_phrase_survives_more_specific_registry_identity(registry):
    match = b.match_registry_entity("M1 muscarinic receptor antagonism", "target", registry)
    assert match["matched"]
    assert match["label"] == "M1 muscarinic receptor (CHRM1)"
    assert not single_registered_target(b.label_key("M1 muscarinic receptor mutant Y108A antagonism"),
        registry, b.DIRECT_TARGET_REGISTRY_STATUSES | b.TARGET_FAMILY_REGISTRY_STATUSES)
    assert recovered_target_detail_reason({"source_item_type": "primary_item", "assay_type": ""})
