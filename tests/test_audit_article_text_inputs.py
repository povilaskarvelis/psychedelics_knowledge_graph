import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from pipeline.fulltext.audit_article_text_inputs import audit_queue_row


TEI = """
<TEI xmlns="http://www.tei-c.org/ns/1.0">
  <text>
    <front>
      <abstract><p>This article reports a psilocybin experiment.</p></abstract>
    </front>
    <body>
      <div><head>Introduction</head><p>Background material.</p></div>
      <div><head>Methods</head><p>Participants received psilocybin.</p></div>
      <div><head>Results</head><p>Clinical outcomes improved.</p></div>
      <div><head>Comment</head><p>Commentary on the result.</p></div>
      <div><head>Discussion</head><p>Interpretation and speculation.</p></div>
      <figure type="table"><head>Table 1</head><figDesc>Outcome scores.</figDesc><table><row><cell>Score</cell></row></table></figure>
    </body>
  </text>
</TEI>
"""


class AuditArticleTextInputsTest(unittest.TestCase):
    def test_audit_queue_row_reports_selected_and_omitted_sections(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_path = Path(tmpdir) / "artifact.json"
            artifact_path.write_text(
                json.dumps(
                    {
                        "study_doi": "10.1000/audit",
                        "study_title": "Audit paper",
                        "best_backend": "grobid",
                        "best_char_count": len(TEI),
                        "best_section_count": 4,
                        "extractions": [
                            {"backend": "grobid", "status": "ok", "text": TEI, "metadata": {"format": "tei_xml"}}
                        ],
                    }
                ),
                encoding="utf-8",
            )
            row = {
                "packet_profile": "primary_empirical",
                "doi": "10.1000/audit",
                "artifact_path": str(artifact_path),
                "study_title": "Audit paper",
                "study_year": "2026",
                "source_types": "journal_article",
                "domain_routes": "clinical_outcome",
                "prompt_profiles": "primary_clinical",
                "schema_profiles": "primary_evidence_schema",
                "route_ids": "route-1",
            }
            args = SimpleNamespace(
                max_chunk_chars=500,
                chunk_overlap_chars=0,
                max_chunks_per_paper=0,
                max_references=50,
                large_token_threshold=25000,
            )

            audit_row, packet = audit_queue_row(
                row,
                args=args,
            )

        self.assertIsNotNone(packet)
        self.assertEqual(audit_row["status"], "ok")
        self.assertEqual(audit_row["section_selection_strategy"], "primary_study")
        self.assertIn("Methods", audit_row["selected_sections"])
        self.assertIn("Results", audit_row["selected_sections"])
        self.assertIn("Introduction", audit_row["omitted_sections"])
        self.assertIn("Comment", audit_row["omitted_sections"])
        self.assertIn("Discussion", audit_row["omitted_sections"])
        self.assertEqual(audit_row["selected_table_count"], 1)
        self.assertEqual(audit_row["issue_flags"], "")


if __name__ == "__main__":
    unittest.main()
