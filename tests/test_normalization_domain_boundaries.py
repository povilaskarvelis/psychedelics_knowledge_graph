import tempfile
from pathlib import Path

import pandas as pd

from pipeline.extract.io_utils import write_json
from pipeline.kg.build_evidence_tables import INTERVENTION_NON_NODE_RE, build_tables, intervention_parent_label
from pipeline.kg.pk_relationships import (
    add_pk_relationship_fields,
    pk_edge_relation_type,
    pk_graph_entity_kind,
    pk_graph_entity_label,
    pk_pharmacodynamic_target,
)


def test_pk_relationship_object_controls_edge_kind_and_label() -> None:
    metabolite = add_pk_relationship_fields(
        {
            "domain": "pharmacokinetics_exposure",
            "compound_or_analyte": "Ketamine",
            "metabolite_or_analyte": "Norketamine",
            "finding_summary": "Ketamine was metabolized to norketamine.",
        }
    )
    assert pk_edge_relation_type(metabolite) == "metabolized_to"
    assert pk_graph_entity_kind(metabolite) == "compound"
    assert pk_graph_entity_label(metabolite) == "Norketamine"

    parent_exposure = add_pk_relationship_fields(
        {
            "domain": "pharmacokinetics_exposure",
            "compound_or_analyte": "Ketamine",
            "metabolite_or_analyte": "Ketamine",
            "pk_or_exposure_parameter": "AUC 0-12h",
            "matrix": "plasma",
            "finding_summary": "Ketamine plasma exposure was characterized.",
        }
    )
    assert pk_graph_entity_kind(parent_exposure) == "pharmacokinetic_parameter"
    assert pk_graph_entity_label(parent_exposure) == "AUC"


def test_pharmacodynamic_target_without_measured_exposure_leaves_pk() -> None:
    row = {
        "domain": "pharmacokinetics_exposure",
        "pk_or_exposure_parameter": "receptor occupancy",
        "metabolic_or_transport_target": "NMDA receptor",
        "finding_summary": "Ketamine produced measurable NMDA receptor occupancy.",
    }
    assert pk_pharmacodynamic_target(row) == "NMDA receptor"

    row["finding_summary"] = "NMDA receptor occupancy increased with measured plasma concentration."
    assert pk_pharmacodynamic_target(row) == ""


def test_intervention_topics_use_recognizable_researcher_facing_labels() -> None:
    cases = {
        "Preparation and Integration meetings": "Preparation–integration protocols",
        "Preparatory and integration psychotherapy": "Preparation–integration protocols",
        "Preparation and setting": "Preparation",
        "Curated music playlist during dosing": "Music",
        "Group-based psychotherapy format": "Group therapy",
        "Facilitator guidance and support": "Facilitator role",
        "Patient-therapist rapport": "Therapeutic alliance",
        "Mindfulness-based cognitive therapy": "Mindfulness-based intervention",
        "At-home telehealth-supported administration": "Remote & at-home delivery",
        "Traditional Mazatec ritual structure": "Ceremonial & ritual context",
        "EMDR somatic resourcing": "Other psychotherapy models",
        "Brief patient psychoeducation": "Other session supports",
    }
    for raw_label, expected in cases.items():
        assert intervention_parent_label({"context_component": raw_label}, raw_label) == expected

    assert (
        intervention_parent_label(
            {
                "context_component": "Set and Setting (Clinical Environment)",
                "component_type": "set and setting",
                "delivery_format": "Private room with low lighting, relaxing music, and nature-themed décor",
            },
            "Set and setting",
        )
        == "Set & setting"
    )
    assert (
        intervention_parent_label(
            {
                "context_component": "Psychotherapy",
                "intervention_model_or_orientation": "Mindfulness-based cognitive therapy",
            },
            "Psychotherapy",
        )
        == "Mindfulness-based intervention"
    )
    for metadata_label in (
        "2-hour session",
        "Ketamine Adjuvant Treatment session frequency/intensity",
        "Prophylactic premedication before buprenorphine",
    ):
        assert INTERVENTION_NON_NODE_RE.search(metadata_label)


def test_intervention_clinical_safety_and_molecular_boundaries() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        registry_path = root / "registry.json"
        routed_path = root / "routed.json"
        out_dir = root / "kg"
        write_json(
            registry_path,
            {
                "compounds": [
                    {"label": "Ketamine", "aliases": [], "ids": {}, "status": "seeded"},
                    {"label": "MDMA", "aliases": [], "ids": {}, "status": "seeded"},
                ],
                "targets": [
                    {
                        "label": "5-HT2A",
                        "aliases": ["5-HT2A mRNA expression"],
                        "ids": {},
                        "status": "biomarker_readout",
                    }
                ],
                "disorders": [
                    {"label": "Major depressive disorder", "aliases": ["MDD"], "ids": {}, "status": "seeded"},
                    {"label": "Suicidality", "aliases": ["suicidal ideation"], "ids": {}, "status": "seeded"},
                ],
            },
        )
        write_json(
            routed_path,
            [
                {
                    "study_doi": "10.1000/intervention",
                    "domain": "intervention_context",
                    "compound": "Ketamine",
                    "context_component": "Motivational Enhancement Therapy (MET)",
                    "component_type": "manualized therapy",
                },
                {
                    "study_doi": "10.1000/intervention-route",
                    "domain": "intervention_context",
                    "compound": "Ketamine",
                    "context_component": "Route of administration (SL vs IM)",
                    "component_type": "dosing-session structure",
                },
                {
                    "study_doi": "10.1000/intervention-preparation",
                    "domain": "intervention_context",
                    "compound": "Ketamine",
                    "context_component": "Preparatory and integration psychotherapy",
                    "component_type": "therapy protocol",
                },
                {
                    "study_doi": "10.1000/intervention-preparation-setting",
                    "domain": "intervention_context",
                    "compound": "Ketamine",
                    "context_component": "Preparation and setting",
                    "component_type": "set and setting",
                    "finding_summary": "Preparation and a supportive setting shaped the session.",
                },
                {
                    "study_doi": "10.1000/intervention-setting-alias",
                    "domain": "intervention_context",
                    "compound": "Ketamine",
                    "context_component": "Set and setting",
                    "component_type": "set and setting",
                },
                {
                    "study_doi": "10.1000/safety",
                    "domain": "safety_tolerability",
                    "compound": "MDMA",
                    "safety_event_or_measure": "elevated blood pressure, headache, and dizziness",
                    "finding_summary": "Elevated blood pressure, headache, and dizziness were reported.",
                },
                {
                    "study_doi": "10.1000/clinical",
                    "domain": "clinical_outcome",
                    "compound": "Ketamine",
                    "condition_or_population": "MDD",
                    "clinical_endpoint": "suicidal ideation",
                    "outcome_measure": "MADRS item 10",
                },
                {
                    "study_doi": "10.1000/readout",
                    "domain": "molecular_target",
                    "compound": "MDMA",
                    "primary_graph_anchor_kind": "biomarker_readout",
                    "target": "5-HT2A mRNA expression",
                    "graph_entity_label": "5-HT2A mRNA expression",
                },
            ],
        )

        build_tables(
            registry_path=registry_path,
            out_dir=out_dir,
            write_duckdb=False,
            graph_sources={
                "routed": {
                    "path": routed_path,
                    "domain": "routed",
                    "dataset": "routed",
                    "default_evidence_type": "primary_evidence",
                    "skip_audit": True,
                },
                "clinical_endpoints": {
                    "path": routed_path,
                    "domain": "routed",
                    "dataset": "routed",
                    "default_evidence_type": "primary_evidence",
                    "transform": "clinical_endpoints",
                    "skip_audit": True,
                },
            },
        )

        edges = pd.read_parquet(out_dir / "evidence_edges.parquet")
        audit = pd.read_parquet(out_dir / "normalization_audit.parquet")

        intervention = edges[edges["domain"] == "intervention_context"]
        intervention_by_doi = intervention.set_index("study_doi")
        assert intervention_by_doi.loc["10.1000/intervention", "entity_label"] == "Motivational Enhancement Therapy (MET)"
        assert (
            intervention_by_doi.loc["10.1000/intervention", "graph_parent_label"]
            == "Motivational enhancement therapy"
        )
        assert (
            intervention_by_doi.loc["10.1000/intervention-preparation", "graph_parent_label"]
            == "Preparation–integration protocols"
        )
        assert (
            intervention_by_doi.loc["10.1000/intervention-preparation-setting", "graph_parent_label"]
            == "Preparation"
        )
        assert intervention_by_doi.loc["10.1000/intervention-setting-alias", "entity_label"] == "Set & setting"
        assert "intervention_context_metadata_not_graphable" in set(audit["normalization_status"])

        safety = edges[edges["domain"] == "safety_tolerability"]
        assert {"Blood pressure elevation", "Headache", "Dizziness/vertigo"}.issubset(set(safety["entity_label"]))
        assert "Cardiovascular safety" in set(safety["graph_parent_label"])

        clinical = edges[edges["domain"] == "clinical_outcome"]
        assert "Suicidality" in set(clinical["entity_label"])
        assert "outcome_scale" not in set(clinical["entity_kind"])

        readout = edges[edges["study_doi"] == "10.1000/readout"]
        assert set(readout["domain"]) == {"molecular_pathway_readout"}
        assert set(readout["entity_kind"]) == {"biomarker_readout"}
