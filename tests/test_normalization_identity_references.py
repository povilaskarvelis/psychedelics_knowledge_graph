"""Identity regressions from saved-output quality review, including negatives."""
import json
import pandas as pd
import pytest
from pipeline.kg import build_evidence_tables as b


@pytest.fixture(scope="module")
def registry():
    return b.registry_lookup(b.DEFAULT_REGISTRY_PATH)


@pytest.mark.parametrize("label", [
    "5-MeO-DMT analogue 20453",
    "5-MeO-DMT (analogue 20453)",
    "C-2-α-fluoro salvinorin A analog (3a)",
    "Salvinorin A derivative 4 (C-2 methyl malonyl)",
    "6a (direct 1H-indazole analog of 5-MeO-DMT)",
    "Compound 4e (fluorinated reversible N-alkyl carbamate derivative of psilocin)",
    "Tropane-based ibogaine analog 9b",
    "4-MeO-DMT", "4-MeO-DiPT",
    "Endogenous porcine brain factor proposed to be a small peptide and ligand for the phencyclidine (PCP) receptor",
    "Endogenous porcine brain factor with PCP-like activity, proposed to be a small peptide",
    "Sertraline; ketamine-derived connectome and nodal fingerprint connectivity assessed as predictors",
    "Scopolamine; polygenic risk scores derived from ketamine-response GWAS results",
    "Ketamine and its metabolites",
    "5-MeO-DMT and its tested analogs",
])
@pytest.mark.parametrize("kind", ["atomic_compound", "compound_combination", "compound_class"])
def test_reference_parent_does_not_become_identity(label, kind, registry):
    row = {"compound": label, "graph_subject_label": label, "graph_subject_kind": kind}
    match = b.graphable_subject_match(row, registry)
    assert match["label"] == label
    assert b.overview_graph_subjects(row, match, registry) == []


@pytest.mark.parametrize("label,canonical", [
    ("Ketamine", "Ketamine"),
    ("Ketamine (a PCP analogue)", "Ketamine"),
    ("Norketamine (ketamine metabolite)", "Norketamine"),
    ("LSD (ergoline derivative)", "LSD"),
    ("5-MeO-DMT", "5-MeO-DMT"),
    ("2-bromo-LSD", "2-bromo-LSD"),
    ("Inhaled synthetic mebufotenin (GH001)", "5-MeO-DMT"),
    ("Ketamine hydrochloride", "Ketamine"),
    ("Phencyclidine (PCP)", "Phencyclidine"),
])
def test_registered_drug_and_descriptive_parent_reference_remain(label, canonical, registry):
    row = {"compound": label, "graph_subject_kind": "atomic_compound"}
    match = b.graphable_subject_match(row, registry)
    assert match["matched"]
    assert match["label"] == canonical
    assert [s["label"] for s in b.overview_graph_subjects(row, match, registry)] == [canonical]


def test_review_projection_provenance_survives_table_contract(tmp_path):
    provenance = {"source_item_id": "R4", "relationship_source_group_key": "10.1/review:R4",
                  "relationship_projection_basis": "explicit_named_anchor_with_domain_support",
                  "relationship_projection_anchor_index": "2",
                  "relationship_anchors_json": '[{"role":"target","label":"NMDA receptor"}]',
                  "relationship_domain_labels_json": '["molecular_target"]'}
    row = {"study_doi": "10.1/review", "study_title": "Ketamine mechanism review", "domain": "molecular_target",
           "compound": "Ketamine", "target": "NMDA receptor", "graph_entity_label": "NMDA receptor",
           "source_type": "review", "source_item_type": "review_relationship", "support": "Ketamine antagonizes NMDAR.",
           "evidence_location": "Mechanism section", **provenance}
    source = tmp_path / "rows.json"
    source.write_text(json.dumps([row]))
    b.build_tables(graph_sources={"routed_extractions": {"path": source, "domain": "routed", "dataset": "routed",
                   "default_evidence_type": "review_evidence", "skip_audit": True}},
                   registry_path=b.DEFAULT_REGISTRY_PATH, out_dir=tmp_path / "kg", write_duckdb=False)
    findings = pd.read_parquet(tmp_path / "kg/findings.parquet")
    assert len(findings) == 1
    for field, value in provenance.items():
        assert str(findings.iloc[0][field]) == value
