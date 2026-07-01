import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from pipeline.publish.export_evidence_payload import export_evidence_payload


class ExportEvidencePayloadTest(unittest.TestCase):
    def test_exports_route_native_findings_without_legacy_split_or_claim_type(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            kg_dir = root / "kg"
            out_dir = root / "payload"
            active_json = root / "graph_payload_active.json"
            kg_dir.mkdir()

            pd.DataFrame(
                [
                    {
                        "finding_id": "finding-1",
                        "paper_id": "paper-1",
                        "source_name": "routed_extractions",
                        "domain": "brain_system",
                        "evidence_type": "primary_evidence",
                        "study_doi": "10.1000/example",
                        "study_year": 2024,
                        "compound": "Psilocybin",
                        "entity_label": "Raw DMN label",
                        "raw_row_json": json.dumps(
                            {
                                "compound": "Psilocybin",
                                "graph_entity_label": "Raw DMN label",
                                "access_level": "article_text",
                                "paper_type": "primary_study",
                                "source_type": "primary",
                                "source_family": "primary_study",
                                "assessment_timepoint": "2 hours post-dose",
                                "needs_human_review": False,
                                "open_access_is_oa": True,
                            }
                        ),
                    },
                    {
                        "finding_id": "legacy-1",
                        "paper_id": "paper-2",
                        "source_name": "mechanistic_primary",
                        "domain": "mechanistic",
                        "evidence_type": "primary_evidence",
                        "raw_row_json": "{}",
                    },
                ]
            ).to_parquet(kg_dir / "findings.parquet", index=False)
            pd.DataFrame(
                [
                    {
                        "finding_id": "finding-1",
                        "evidence_id": "evidence-1",
                        "domain": "brain_system",
                        "entity_kind": "brain_network",
                        "entity_label": "Default mode network",
                        "evidence_type": "primary_evidence",
                        "relation_type": "modulates_brain_system",
                    }
                ]
            ).to_parquet(kg_dir / "evidence_edges.parquet", index=False)

            result = export_evidence_payload(
                kg_dir=kg_dir,
                out_dir=out_dir,
                active_json=active_json,
            )

            payload = json.loads(result["payload_path"].read_text())
            preview = json.loads(result["preview_path"].read_text())
            active = json.loads(active_json.read_text())

        self.assertEqual(payload["schema_version"], "route_native_evidence_payload_v1")
        self.assertEqual(payload["row_count"], 1)
        self.assertIn("findings", payload)
        self.assertNotIn("datasets", payload)
        finding = payload["findings"][0]
        self.assertEqual(finding["finding_id"], "finding-1")
        self.assertEqual(finding["domain"], "brain_system")
        self.assertEqual(finding["finding_type"], "brain_system")
        self.assertEqual(finding["entity_label"], "Default mode network")
        self.assertEqual(finding["entity_kind"], "brain_network")
        self.assertEqual(finding["text_depth"], "article_text")
        self.assertEqual(finding["assessment_timepoint"], "2 hours post-dose")
        self.assertIs(finding["needs_human_review"], False)
        self.assertIs(finding["open_access_is_oa"], True)
        self.assertNotIn("claim_type", finding)
        self.assertNotIn("target", finding)
        self.assertNotIn("disorder", finding)
        self.assertEqual(preview["findings"][0]["entity_label"], "Default mode network")
        self.assertEqual(active["schema_version"], "route_native_evidence_payload_active_v1")
        self.assertIn("active_evidence_payload", active)
        self.assertIn("active_evidence_preview", active)
        self.assertNotIn("active_payload_dir", active)
        self.assertNotIn("claim_source", active)

    def test_exports_pharmacokinetics_specific_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            kg_dir = root / "kg"
            out_dir = root / "payload"
            kg_dir.mkdir()

            pd.DataFrame(
                [
                    {
                        "finding_id": "finding-pk",
                        "paper_id": "paper-pk",
                        "source_name": "routed_extractions",
                        "domain": "pharmacokinetics_exposure",
                        "evidence_type": "primary_evidence",
                        "study_doi": "10.1000/pk",
                        "study_year": 2025,
                        "compound": "Ketamine",
                        "entity_label": "Cmax",
                        "raw_row_json": json.dumps(
                            {
                                "compound": "Ketamine",
                                "graph_entity_label": "Cmax",
                                "access_level": "article_text",
                                "primary_graph_anchor_kind": "pharmacokinetic_parameter",
                                "pharmacokinetic_display_label": "Ketamine plasma exposure",
                                "pk_relationship_type": "exposure_characterized",
                                "pk_relationship_label": "exposure characterized",
                                "pk_graph_object_kind": "parent_or_analyte_exposure",
                                "pk_graph_object_label": "Ketamine plasma exposure",
                                "pk_or_exposure_parameter": "Cmax",
                                "analyte_type": "parent",
                                "metabolite_or_analyte": "ketamine",
                                "matrix": "plasma",
                                "value": "123",
                                "unit": "ng/mL",
                                "dose": "0.5 mg/kg",
                                "route_of_administration": "intravenous",
                                "sampling_time_or_window": "40 minutes post-dose",
                                "model_or_method": "noncompartmental analysis",
                                "exposure_response_or_pk_effect": "higher peak exposure",
                            }
                        ),
                    }
                ]
            ).to_parquet(kg_dir / "findings.parquet", index=False)
            pd.DataFrame(
                [
                    {
                        "finding_id": "finding-pk",
                        "evidence_id": "evidence-pk",
                        "domain": "pharmacokinetics_exposure",
                        "entity_kind": "pharmacokinetic_parameter",
                        "entity_label": "Cmax",
                        "evidence_type": "primary_evidence",
                        "relation_type": "has_pharmacokinetic_exposure",
                    }
                ]
            ).to_parquet(kg_dir / "evidence_edges.parquet", index=False)

            result = export_evidence_payload(kg_dir=kg_dir, out_dir=out_dir)
            payload = json.loads(result["payload_path"].read_text())
            preview = json.loads(result["preview_path"].read_text())

        finding = payload["findings"][0]
        self.assertEqual(finding["domain"], "pharmacokinetics_exposure")
        self.assertEqual(finding["entity_kind"], "pharmacokinetic_parameter")
        self.assertEqual(finding["primary_graph_anchor_kind"], "pharmacokinetic_parameter")
        self.assertEqual(finding["pharmacokinetic_display_label"], "Ketamine plasma exposure")
        self.assertEqual(finding["pk_relationship_type"], "exposure_characterized")
        self.assertEqual(finding["pk_relationship_label"], "exposure characterized")
        self.assertEqual(finding["pk_graph_object_kind"], "parent_or_analyte_exposure")
        self.assertEqual(finding["pk_graph_object_label"], "Ketamine plasma exposure")
        self.assertEqual(finding["pk_or_exposure_parameter"], "Cmax")
        self.assertEqual(finding["metabolite_or_analyte"], "ketamine")
        self.assertEqual(finding["matrix"], "plasma")
        self.assertEqual(finding["route_of_administration"], "intravenous")
        self.assertEqual(finding["sampling_time_or_window"], "40 minutes post-dose")
        self.assertEqual(finding["model_or_method"], "noncompartmental analysis")
        self.assertEqual(finding["exposure_response_or_pk_effect"], "higher peak exposure")
        self.assertEqual(preview["findings"][0]["pharmacokinetic_display_label"], "Ketamine plasma exposure")
        self.assertEqual(preview["findings"][0]["pk_graph_object_label"], "Ketamine plasma exposure")
        self.assertEqual(preview["findings"][0]["matrix"], "plasma")

    def test_exports_graph_study_coverage_from_candidate_papers(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            kg_dir = root / "kg"
            out_dir = root / "payload"
            kg_dir.mkdir()

            pd.DataFrame(
                [
                    {
                        "finding_id": "finding-a",
                        "paper_id": "paper-a",
                        "source_name": "routed_extractions",
                        "domain": "clinical_outcome",
                        "evidence_type": "primary_evidence",
                        "study_doi": "10.1000/included-a",
                        "compound": "Psilocybin",
                        "entity_label": "Major depressive disorder",
                        "raw_row_json": "{}",
                    },
                    {
                        "finding_id": "finding-b",
                        "paper_id": "paper-b",
                        "source_name": "routed_extractions",
                        "domain": "clinical_outcome",
                        "evidence_type": "primary_evidence",
                        "study_doi": "10.1000/included-b",
                        "compound": "Ketamine",
                        "entity_label": "Treatment-resistant depression",
                        "raw_row_json": "{}",
                    },
                ]
            ).to_parquet(kg_dir / "findings.parquet", index=False)
            pd.DataFrame(
                [
                    {
                        "finding_id": "finding-a",
                        "evidence_id": "evidence-a",
                        "domain": "clinical_outcome",
                        "entity_kind": "condition_indication",
                        "entity_label": "Major depressive disorder",
                        "evidence_type": "primary_evidence",
                        "relation_type": "studied_for_condition",
                    },
                    {
                        "finding_id": "finding-b",
                        "evidence_id": "evidence-b",
                        "domain": "clinical_outcome",
                        "entity_kind": "condition_indication",
                        "entity_label": "Treatment-resistant depression",
                        "evidence_type": "primary_evidence",
                        "relation_type": "studied_for_condition",
                    },
                ]
            ).to_parquet(kg_dir / "evidence_edges.parquet", index=False)
            pd.DataFrame(
                [
                    {"paper_id": "paper-a", "study_doi": "10.1000/included-a", "study_title": "Included A"},
                    {"paper_id": "paper-b", "study_doi": "10.1000/included-b", "study_title": "Included B"},
                    {"paper_id": "paper-c", "study_doi": "10.1000/not-in-graph", "study_title": "Not in graph"},
                ]
            ).to_parquet(kg_dir / "papers.parquet", index=False)

            result = export_evidence_payload(kg_dir=kg_dir, out_dir=out_dir)
            payload = json.loads(result["payload_path"].read_text())
            manifest = json.loads(result["manifest_path"].read_text())

        self.assertEqual(payload["summary_stats"]["study_count"], 2)
        self.assertEqual(
            payload["summary_stats"]["graph_study_coverage"],
            {"included_count": 2, "candidate_count": 3, "not_in_graph_count": 1},
        )
        self.assertEqual(payload["summary_stats"]["graph_candidate_study_count"], 3)
        self.assertEqual(payload["summary_stats"]["graph_excluded_study_count"], 1)
        self.assertEqual(manifest["summary_stats"]["default"]["graph_study_coverage"]["not_in_graph_count"], 1)

    def test_exports_routed_clinical_endpoint_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            kg_dir = root / "kg"
            out_dir = root / "payload"
            kg_dir.mkdir()

            pd.DataFrame(
                [
                    {
                        "finding_id": "finding-condition",
                        "paper_id": "paper-1",
                        "source_name": "routed_extractions",
                        "domain": "clinical_outcome",
                        "evidence_type": "primary_evidence",
                        "study_doi": "10.1000/condition",
                        "compound": "Psilocybin",
                        "entity_label": "Major depressive disorder",
                        "raw_row_json": json.dumps(
                            {
                                "compound": "Psilocybin",
                                "graph_entity_label": "Major depressive disorder",
                                "access_level": "article_text",
                            }
                        ),
                    },
                    {
                        "finding_id": "finding-symptom",
                        "paper_id": "paper-1",
                        "source_name": "routed_clinical_endpoints",
                        "domain": "clinical_outcome",
                        "evidence_type": "primary_evidence",
                        "study_doi": "10.1000/symptom",
                        "compound": "Psilocybin",
                        "entity_label": "Depression",
                        "raw_row_json": json.dumps(
                            {
                                "compound": "Psilocybin",
                                "graph_entity_label": "Depression",
                                "kg_entity_kind_override": "symptom_problem",
                                "endpoint_label_source": "clinical_symptom_endpoint",
                                "access_level": "article_text",
                            }
                        ),
                    },
                    {
                        "finding_id": "legacy-1",
                        "paper_id": "paper-2",
                        "source_name": "mechanistic_primary",
                        "domain": "mechanistic",
                        "evidence_type": "primary_evidence",
                        "raw_row_json": "{}",
                    },
                ]
            ).to_parquet(kg_dir / "findings.parquet", index=False)
            pd.DataFrame(
                [
                    {
                        "finding_id": "finding-condition",
                        "evidence_id": "evidence-condition",
                        "domain": "clinical_outcome",
                        "entity_kind": "condition_indication",
                        "entity_label": "Major depressive disorder",
                        "evidence_type": "primary_evidence",
                        "relation_type": "studied_for_condition",
                    },
                    {
                        "finding_id": "finding-symptom",
                        "evidence_id": "evidence-symptom",
                        "domain": "clinical_outcome",
                        "entity_kind": "symptom_problem",
                        "entity_label": "Depression",
                        "evidence_type": "primary_evidence",
                        "relation_type": "studied_for_symptom",
                    },
                ]
            ).to_parquet(kg_dir / "evidence_edges.parquet", index=False)

            result = export_evidence_payload(kg_dir=kg_dir, out_dir=out_dir)
            payload = json.loads(result["payload_path"].read_text())

        self.assertEqual(payload["row_count"], 2)
        labels = {finding["entity_label"] for finding in payload["findings"]}
        self.assertEqual(labels, {"Major depressive disorder", "Depression"})
        symptom = next(finding for finding in payload["findings"] if finding["entity_label"] == "Depression")
        self.assertEqual(symptom["entity_kind"], "symptom_problem")
        self.assertEqual(symptom["relation_type"], "studied_for_symptom")


if __name__ == "__main__":
    unittest.main()
