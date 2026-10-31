"""PCP is a focal compound, not a reference-only reagent.

Synthetic observations exercise actual normalization outputs; no model calls or
production screening/graph artifacts are used or written.
"""
import json

import pandas as pd
import pytest

from pipeline.kg import build_evidence_tables as b
from pipeline.kg.pk_relationships import distinct_analyte
from pipeline.kg.convert_review_relationship_bundles_to_evidence_rows import (
    in_scope_compound_keys,
    review_scope_for_relationship,
)
from pipeline.review.deterministic_prescreen_rules import (
    COMPOUND_SYNONYMS,
    configured_allowed_compound_terms,
    matched_in_scope_intervention_terms,
)


@pytest.fixture(scope="module")
def registry():
    return b.registry_lookup(b.DEFAULT_REGISTRY_PATH)


@pytest.mark.parametrize("label", [
    "PCP", "phencyclidine", "Phencyclidine (PCP)",
    "phencyclidine hydrochloride", "PCP HCl",
])
def test_parent_aliases_normalize_to_one_graph_compound(label, registry):
    row = {"compound": label, "graph_subject_kind": "atomic_compound"}
    match = b.graphable_subject_match(row, registry)
    assert match["matched"]
    assert match["label"] == "Phencyclidine"
    assert match["status"] == "compound_normalized"
    assert [s["label"] for s in b.overview_graph_subjects(row, match, registry)] == ["Phencyclidine"]


@pytest.mark.parametrize("label", [
    "3-MeO-PCP", "4-MeO-PCP", "3-HO-PCP", "3-methoxyphencyclidine",
])
def test_substituted_analogues_do_not_become_parent_pcp(label, registry):
    row = {"compound": label, "graph_subject_kind": "atomic_compound"}
    match = b.graphable_subject_match(row, registry)
    assert match["label"] == label
    assert match["status"] == "unregistered_chemical_identity_detail_only"
    assert b.overview_graph_subjects(row, match, registry) == []


def test_pcp_binding_site_remains_a_target_not_a_compound(registry):
    original = "phencyclidine (PCP) binding sites"
    label, _ = b.canonicalize_registry_label(
        "mechanistic_entity", original, registry
    )
    # A historical site name alone establishes neither a parent-drug result
    # nor a particular receptor identity. Preserve it as a literal target.
    assert label == original
    match = b.match_registry_entity(original, "target", registry)
    assert match["matched"] and match["label"] == original
    assert match["match_type"] == "historical_target_site_detail_only"


@pytest.mark.parametrize("label", ["PCP", "phencyclidine (PCP)", "PCP HCl", "phencyclidine hydrochloride"])
def test_parent_alias_does_not_become_a_different_pk_analyte(label):
    assert not distinct_analyte("Phencyclidine", label)
    assert not distinct_analyte(label, "Phencyclidine")
    assert distinct_analyte("Phencyclidine", "3-MeO-PCP")


def test_allowlist_and_review_scope_use_registered_parent_and_acronym():
    assert "Phencyclidine" in configured_allowed_compound_terms()
    assert "pcp" in COMPOUND_SYNONYMS["phencyclidine"]
    payload = json.loads(b.DEFAULT_REGISTRY_PATH.read_text())
    keys = in_scope_compound_keys(payload)
    for label in ["PCP", "Phencyclidine"]:
        status, _ = review_scope_for_relationship(
            {"study_title": f"{label} pharmacology review"}, "Cognitive impairment", keys
        )
        assert status == "in_scope"


@pytest.mark.parametrize("text,expected", [
    ("Phencyclidine effects on behavior", True),
    ("PCP-induced hyperlocomotion in rats", True),
    ("PCP is a dissociative NMDA receptor antagonist", True),
    ("PCP referrals to primary care physicians", False),
    ("Treatment of Pneumocystis pneumonia (PCP) with antimicrobial drugs", False),
])
def test_drug_acronym_matching_does_not_reopen_unrelated_pcp_records(text, expected):
    hits = {s.lower() for s in matched_in_scope_intervention_terms(text)}
    assert bool(hits & {"phencyclidine", "pcp"}) is expected


def test_pcp_findings_survive_actual_table_build_with_one_compound_node(tmp_path):
    source = tmp_path / "synthetic_routed_findings.json"
    rows = [
        {
            "study_doi": "10.1000/pcp-target-fixture",
            "domain": "molecular_target", "compound": "PCP",
            "graph_subject_kind": "atomic_compound", "target": "NMDA receptor",
            "finding_summary": "Phencyclidine inhibited the NMDA receptor in an in-vitro experiment.",
            "support": "Phencyclidine inhibited the NMDA receptor.",
        },
        {
            "study_doi": "10.1000/pcp-brain-fixture",
            "domain": "brain_system", "compound": "phencyclidine (PCP)",
            "graph_subject_kind": "atomic_compound", "primary_graph_anchor_kind": "brain_region",
            "brain_region": "Prefrontal cortex",
            "finding_summary": "PCP changed prefrontal cortical activity in rats.",
            "support": "PCP changed prefrontal cortical activity.",
        },
        {
            "study_doi": "10.1000/pcp-pk-fixture",
            "domain": "pharmacokinetics_exposure", "compound_or_analyte": "Phencyclidine",
            "primary_graph_anchor_kind": "pharmacokinetic_parameter",
            "pk_or_exposure_parameter": "Cmax", "metabolite_or_analyte": "PCP",
            "analyte_type": "parent", "matrix": "plasma", "value": "20", "unit": "ng/mL",
            "finding_summary": "Phencyclidine plasma concentration was measured after administration.",
            "support": "PCP peak plasma concentration was 20 ng/mL.",
        },
        {
            "study_doi": "10.1000/memantine-control-fixture",
            "domain": "molecular_target", "compound": "Memantine",
            "graph_subject_kind": "atomic_compound", "target": "NMDA receptor",
            "finding_summary": "Memantine inhibited the NMDA receptor.",
            "support": "Memantine inhibited the NMDA receptor.",
        },
    ]
    source.write_text(json.dumps(rows))
    out = tmp_path / "kg"
    b.build_tables(
        registry_path=b.DEFAULT_REGISTRY_PATH, out_dir=out, write_duckdb=False,
        graph_sources={"routed_extractions": {
            "path": source, "domain": "routed", "dataset": "routed",
            "default_evidence_type": "primary_evidence", "skip_audit": True,
        }},
    )
    findings = pd.read_parquet(out / "findings.parquet")
    edges = pd.read_parquet(out / "evidence_edges.parquet")
    assert set(findings["study_doi"]) == {r["study_doi"] for r in rows[:3]}
    assert set(findings["compound"]) == {"Phencyclidine"}
    assert set(edges["compound"]) == {"Phencyclidine"}
    assert set(findings["domain"]) == {"molecular_target", "brain_system", "pharmacokinetics_exposure"}
