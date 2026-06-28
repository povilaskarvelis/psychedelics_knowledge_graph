import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from pipeline.extract.extraction_v1_utils import write_json
from pipeline.kg.build_evidence_tables import build_tables


class BuildEvidenceTablesTest(unittest.TestCase):
    def test_builds_unified_parquet_tables_with_entity_kinds(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            registry_path = root / "registry.json"
            write_json(
                registry_path,
                {
                    "compounds": [
                        {"label": "Psilocybin", "aliases": [], "ids": {"pubchem_cid": "10624"}, "status": "seeded"},
                        {"label": "Ketamine", "aliases": [], "ids": {}, "status": "seeded"},
                    ],
                    "targets": [
                        {
                            "label": "5-HT2A",
                            "aliases": ["5-HT2A receptor"],
                            "ids": {"gene_symbol": "HTR2A"},
                            "status": "needs_external_id_lookup",
                        },
                        {
                            "label": "Neuroplasticity",
                            "aliases": [],
                            "ids": {},
                            "status": "pathway_or_process",
                        },
                    ],
                    "disorders": [
                        {
                            "label": "Depression",
                            "aliases": [],
                            "ids": {},
                            "status": "broad_category_needs_external_id_lookup",
                        },
                        {
                            "label": "Major depressive disorder",
                            "aliases": [],
                            "ids": {},
                            "status": "needs_external_id_lookup",
                        },
                        {
                            "label": "Post-traumatic stress disorder",
                            "aliases": ["PTSD"],
                            "ids": {},
                            "status": "needs_external_id_lookup",
                        },
                    ],
                },
            )
            mechanistic_path = root / "mechanistic.json"
            clinical_path = root / "clinical.json"
            brain_path = root / "brain.json"
            pk_path = root / "pk.json"
            public_health_path = root / "public_health.json"
            clinical_endpoint_path = root / "clinical_endpoint_raw.json"
            audit_path = root / "audit.json"
            endpoint_audit_path = root / "endpoint_audit.json"
            write_json(
                mechanistic_path,
                [
                    {
                        "study_doi": "https://doi.org/10.1000/MECH",
                        "study_title": "Mechanistic paper",
                        "study_year": 2024,
                        "compound": "Psilocybin",
                        "target": "5-HT2A",
                        "entity_role": "molecular_target",
                        "paper_assessment_route": "primary_evidence",
                        "source_type": "primary_study",
                        "paper_type": "primary_results",
                        "access_level": "full_text_seen",
                        "result_direction": "positive",
                    },
                    {
                        "study_doi": "10.1000/pathway",
                        "study_title": "Pathway paper",
                        "study_year": 2025,
                        "compound": "Ketamine",
                        "target": "Neuroplasticity",
                        "entity_role": "pathway_or_process",
                        "paper_assessment_route": "primary_evidence",
                        "source_type": "primary_study",
                        "paper_type": "primary_results",
                    },
                ],
            )
            write_json(
                clinical_path,
                [
                    {
                        "study_doi": "10.1000/clin",
                        "study_title": "Clinical paper",
                        "study_year": 2023,
                        "compound": "Psilocybin",
                        "disorder": "Major depressive disorder",
                        "entity_role": "therapeutic_indication",
                        "paper_assessment_route": "secondary_literature",
                        "source_type": "review",
                        "paper_type": "review",
                        "access_level": "secondary_summary",
                    },
                    {
                        "study_doi": "10.1000/symptom",
                        "study_title": "Symptom paper",
                        "study_year": 2023,
                        "compound": "Psilocybin",
                        "disorder": "Depression",
                        "entity_role": "symptom_or_problem",
                        "paper_assessment_route": "primary_evidence",
                        "source_type": "primary_study",
                        "paper_type": "primary_results",
                        "access_level": "full_text_seen",
                    },
                    {
                        "study_doi": "10.1000/outcome-symptom",
                        "study_title": "Outcome symptom paper",
                        "study_year": 2023,
                        "compound": "Ketamine",
                        "disorder": "Depression",
                        "entity_role": "outcome_measure",
                        "paper_assessment_route": "primary_evidence",
                        "source_type": "primary_study",
                        "paper_type": "primary_results",
                        "access_level": "full_text_seen",
                    },
                    {
                        "study_doi": "10.1000/ptsd-symptoms",
                        "study_title": "PTSD symptom outcome paper",
                        "study_year": 2023,
                        "compound": "Ketamine",
                        "disorder": "Post-traumatic stress disorder",
                        "entity_role": "symptom_or_problem",
                        "paper_assessment_route": "primary_evidence",
                        "source_type": "primary_study",
                        "paper_type": "primary_results",
                        "access_level": "full_text_seen",
                    },
                ],
            )
            write_json(
                brain_path,
                [
                    {
                        "study_doi": "10.1000/brain",
                        "study_title": "Brain network paper",
                        "study_year": 2025,
                        "compound_or_exposure": "Psilocybin",
                        "primary_graph_anchor_kind": "brain_network",
                        "brain_network": "DMN",
                        "readout_or_measure": "functional connectivity",
                        "paper_assessment_route": "primary_evidence",
                        "source_type": "primary_study",
                        "paper_type": "primary_results",
                        "access_level": "full_text_seen",
                    }
                ],
            )
            write_json(
                pk_path,
                [
                    {
                        "study_doi": "10.1000/pk",
                        "study_title": "Exposure target paper",
                        "study_year": 2025,
                        "compound_or_analyte": "DMT",
                        "primary_graph_anchor_kind": "target",
                        "metabolic_or_transport_target": "MAO-A",
                        "pk_or_exposure_parameter": "metabolism",
                        "paper_assessment_route": "primary_evidence",
                        "source_type": "primary_study",
                        "paper_type": "primary_results",
                        "access_level": "full_text_seen",
                    }
                ],
            )
            write_json(
                public_health_path,
                [
                    {
                        "study_doi": "10.1000/public-health",
                        "study_title": "Public health paper",
                        "study_year": 2025,
                        "exposure_or_intervention": "Psychedelic therapy",
                        "public_health_measure": "ethnoracial inclusion",
                        "public_health_topic_category": "access and equity",
                        "paper_assessment_route": "primary_evidence",
                        "source_type": "primary_study",
                        "paper_type": "primary_results",
                        "access_level": "full_text_seen",
                    }
                ],
            )
            write_json(
                clinical_endpoint_path,
                [
                    {
                        "study_doi": "10.1000/function",
                        "study_title": "Functional endpoint paper",
                        "study_year": 2022,
                        "compound": "psilocybin",
                        "disorder": "not_applicable",
                        "raw_entity_label": "well-being",
                        "entity_role": "functional_outcome",
                        "outcome_domain": "well-being",
                        "outcome_measure": "Warwick-Edinburgh Mental Well-Being Scale",
                        "outcome_measure_normalized": "WEMWBS",
                        "paper_assessment_route": "primary_evidence",
                        "source_type": "primary_study",
                        "paper_type": "primary_results",
                        "access_level": "full_text_seen",
                    },
                    {
                        "study_doi": "10.1000/noisy-function",
                        "study_title": "Noisy endpoint paper",
                        "study_year": 2022,
                        "compound": "psilocybin",
                        "disorder": "not_applicable",
                        "raw_entity_label": "patient satisfaction",
                        "entity_role": "functional_outcome",
                        "outcome_domain": "patient experience",
                        "outcome_measure": "Client Satisfaction Questionnaire",
                        "outcome_measure_normalized": "",
                        "paper_assessment_route": "primary_evidence",
                        "source_type": "primary_study",
                        "paper_type": "primary_results",
                        "access_level": "full_text_seen",
                    }
                ],
            )
            write_json(audit_path, [{"normalization_status": "normalized", "compound": "Psilocybin", "target": "5-HT2A"}])
            write_json(
                endpoint_audit_path,
                [
                    {
                        "normalization_status": "not_graph_candidate",
                        "compound": "psilocybin",
                        "canonical_compound": "Psilocybin",
                        "entity_role": "functional_outcome",
                    },
                    {
                        "normalization_status": "not_graph_candidate",
                        "compound": "psilocybin",
                        "canonical_compound": "Psilocybin",
                        "entity_role": "functional_outcome",
                    }
                ],
            )

            out_dir = root / "kg"
            manifest = build_tables(
                registry_path=registry_path,
                out_dir=out_dir,
                write_duckdb=False,
                graph_sources={
                    "mechanistic_primary": {
                        "path": mechanistic_path,
                        "audit_path": audit_path,
                        "domain": "mechanistic",
                        "dataset": "mechanistic",
                        "default_evidence_type": "primary_evidence",
                    },
                    "clinical_secondary": {
                        "path": clinical_path,
                        "audit_path": audit_path,
                        "domain": "clinical",
                        "dataset": "disorder",
                        "default_evidence_type": "secondary_literature",
                    },
                    "brain_primary": {
                        "path": brain_path,
                        "audit_path": audit_path,
                        "domain": "brain_system",
                        "dataset": "brain_system",
                        "default_evidence_type": "primary_evidence",
                    },
                    "pk_primary": {
                        "path": pk_path,
                        "audit_path": audit_path,
                        "domain": "pharmacokinetics_exposure",
                        "dataset": "pharmacokinetics_exposure",
                        "default_evidence_type": "primary_evidence",
                    },
                    "public_health_primary": {
                        "path": public_health_path,
                        "audit_path": audit_path,
                        "domain": "real_world_public_health",
                        "dataset": "real_world_public_health",
                        "default_evidence_type": "primary_evidence",
                    },
                    "clinical_primary_endpoints": {
                        "path": clinical_endpoint_path,
                        "audit_path": endpoint_audit_path,
                        "domain": "clinical",
                        "dataset": "disorder",
                        "default_evidence_type": "primary_evidence",
                        "transform": "clinical_endpoints",
                        "skip_audit": True,
                    },
                },
            )

            self.assertEqual(manifest["tables"]["evidence_edges"]["rows"], 10)
            edges = pd.read_parquet(out_dir / "evidence_edges.parquet")
            self.assertEqual(
                set(edges["domain"]),
                {"mechanistic", "clinical", "brain_system", "pharmacokinetics_exposure", "real_world_public_health"},
            )
            self.assertEqual(
                set(edges["entity_kind"]),
                {
                    "target",
                    "pathway_process",
                    "condition_indication",
                    "symptom_problem",
                    "outcome_scale",
                    "brain_network",
                    "public_health_measure",
                },
            )
            self.assertIn("secondary_literature", set(edges["evidence_type"]))
            self.assertNotIn("functional_outcome", set(edges["entity_kind"]))
            scale = edges[edges["entity_kind"] == "outcome_scale"].iloc[0]
            self.assertEqual(scale["entity_label"], "WEMWBS")
            self.assertEqual(scale["compound"], "Psilocybin")
            self.assertNotIn("Wellbeing", set(edges["entity_label"]))
            self.assertNotIn("Patient experience", set(edges["entity_label"]))
            condition_edges = edges[edges["entity_kind"] == "condition_indication"]
            self.assertEqual(set(condition_edges["entity_label"]), {"Major depressive disorder", "Post-traumatic stress disorder"})
            symptom_edges = edges[edges["entity_kind"] == "symptom_problem"]
            self.assertEqual(set(symptom_edges["entity_label"]), {"Depression"})
            self.assertEqual(len(symptom_edges), 2)
            brain_edge = edges[edges["domain"] == "brain_system"].iloc[0]
            self.assertEqual(brain_edge["entity_kind"], "brain_network")
            self.assertEqual(brain_edge["entity_label"], "Default mode network")
            self.assertEqual(brain_edge["relation_type"], "has_brain_system_effect")
            pk_edge = edges[edges["domain"] == "pharmacokinetics_exposure"].iloc[0]
            self.assertEqual(pk_edge["entity_kind"], "target")
            self.assertEqual(pk_edge["entity_label"], "MAO-A")
            self.assertEqual(pk_edge["relation_type"], "has_pharmacokinetic_exposure")
            public_health_edge = edges[edges["domain"] == "real_world_public_health"].iloc[0]
            self.assertEqual(public_health_edge["entity_kind"], "public_health_measure")
            self.assertEqual(public_health_edge["entity_label"], "Equity")
            self.assertEqual(public_health_edge["relation_type"], "has_public_health_evidence")

            papers = pd.read_parquet(out_dir / "papers.parquet")
            self.assertEqual(
                set(papers["paper_id"]),
                {
                    "paper:10.1000/mech",
                    "paper:10.1000/pathway",
                    "paper:10.1000/brain",
                    "paper:10.1000/pk",
                    "paper:10.1000/public-health",
                    "paper:10.1000/clin",
                    "paper:10.1000/symptom",
                    "paper:10.1000/outcome-symptom",
                    "paper:10.1000/ptsd-symptoms",
                    "paper:10.1000/function",
                },
            )

            entities = pd.read_parquet(out_dir / "entities.parquet")
            neuroplasticity = entities[entities["label"] == "Neuroplasticity"].iloc[0]
            self.assertEqual(neuroplasticity["entity_kind"], "pathway_process")

            self.assertTrue((out_dir / "claims.parquet").exists())
            self.assertTrue((out_dir / "normalization_audit.parquet").exists())
            self.assertEqual(json.loads((out_dir / "manifest.json").read_text())["duckdb"]["status"], "skipped")


if __name__ == "__main__":
    unittest.main()
