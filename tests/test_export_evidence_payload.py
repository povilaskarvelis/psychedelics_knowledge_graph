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
                        "entity_label": "Default mode network",
                        "raw_row_json": json.dumps(
                            {
                                "compound": "Psilocybin",
                                "graph_entity_label": "Default mode network",
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


if __name__ == "__main__":
    unittest.main()
