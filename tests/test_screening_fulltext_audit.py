import json
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pipeline.review import audit_screening_correction_fulltext as audit


class FulltextScreeningAuditTests(unittest.TestCase):
    def test_source_quote_repair_is_exact_and_cannot_bypass_other_issues(self):
        row = {"doi": "10.test/control", "status": "needs_review", "issues": ["finding_quote_not_in_record"],
               "record": {"study_title": "Intervention study", "abstract": "Only pooled other-drug use was measured."},
               "parsed": {"screening_decision": "exclude_out_of_scope", "domain_tags": [], "methodological_validity_tags": [], "primary_domain": "general_topic", "eligibility": {"basis": "peripheral_mention", "substances": [], "finding_quote": "invented quote", "input_integrity": "consistent"}}}
        judgment = {"doi": row["doi"], "unchanged_decision": "exclude_out_of_scope", "source_finding_quote": "Only pooled other-drug use was measured."}
        for field in ("record", "parsed"):
            judgment[field + "_sha256"] = hashlib.sha256(json.dumps(row[field], sort_keys=True).encode()).hexdigest()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            audit.correction.save(root / "control_quote_source_adjudications.json", {"records": [judgment]})
            repaired = audit.apply_control_quote_adjudications(root, {row["doi"]: row})[row["doi"]]
            self.assertEqual(repaired["status"], "ok")
            self.assertEqual(row["parsed"]["eligibility"]["finding_quote"], "invented quote")
            self.assertEqual(repaired["parsed"]["screening_decision"], row["parsed"]["screening_decision"])
            row["record"]["abstract"] += " Changed input."
            with self.assertRaisesRegex(ValueError, "frozen answer/input"):
                audit.apply_control_quote_adjudications(root, {row["doi"]: row})
            row["issues"].append("no_verified_eligible_substance")
            with self.assertRaisesRegex(ValueError, "restricted to finding-quote"):
                audit.apply_control_quote_adjudications(root, {row["doi"]: row})

    def test_body_includes_results_and_tables_but_not_reference_titles(self):
        raw = '<TEI xmlns="http://www.tei-c.org/ns/1.0"><teiHeader><title>Header</title></teiHeader><text><body><div><head>Results</head><p>Ketamine increased dopamine.</p><table><row><cell>n=4</cell></row></table></div></body><back><p>Psilocybin reference only.</p></back></text></TEI>'
        text = audit.article_body(raw)
        self.assertIn("Ketamine increased dopamine.", text)
        self.assertIn("n=4", text)
        self.assertNotIn("Psilocybin", text)

    def test_no_body_cannot_silently_become_a_fulltext_audit(self):
        with self.assertRaisesRegex(ValueError, "No separately identifiable"):
            audit.article_body('<article><front><p>Abstract only.</p></front></article>')

    def test_jats_floating_table_is_retained_without_bibliography_or_duplicates(self):
        raw = '<article xmlns="urn:jats"><body><p>Results</p><floats-group><table-wrap><p>Inside table</p></table-wrap></floats-group></body><back><ref-list><p>Psilocybin reference only.</p></ref-list></back><floats-group><table-wrap><p>MDMA confirmed: 2</p></table-wrap></floats-group></article>'
        text = audit.article_body(raw, backend="pmc_oai_xml")
        self.assertIn("MDMA confirmed: 2", text)
        self.assertEqual(text.count("Inside table"), 1)
        self.assertNotIn("Psilocybin", text)

    def test_saved_plain_exports_preserve_scientific_text_and_headings(self):
        source = "# Study\n## Results\nP < 0.05 and concentration > 2.\n| Drug | n |\n| MDMA | 11 |"
        for backend in audit.TEXT_BACKENDS:
            with self.subTest(backend=backend):
                self.assertEqual(audit.article_body(source, backend=backend), source)

    def test_invalid_xml_is_not_silently_reinterpreted_as_a_text_export(self):
        with self.assertRaises(audit.ET.ParseError):
            audit.article_body("<TEI><body>broken", backend="grobid")

    def test_truncation_is_explicit_and_within_input_bound(self):
        source = "Introduction. " + "filler " * 4000 + "PCP increased transmitter release." + " tail" * 4000
        selected, complete = audit.select_body(source, limit=12000)
        self.assertFalse(complete)
        self.assertLessEqual(len(selected), 12000)
        self.assertIn("[Body characters", selected)
        self.assertEqual(audit.select_body("Short complete body."), ("Short complete body.", True))

    def test_failed_source_control_blocks_the_larger_paid_audit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "inputs").mkdir()
            (root / "fulltext_pilot").mkdir()
            audit.correction.save(root / "run.json", {"records": 2, "hashes": {"validator": audit.correction.fingerprint(audit.contract.__file__)}})
            audit.correction.save(root / "inputs/pilot_gold.json", {"records": [{"doi": "10.test/control", "decision": "include_in_scope"}]})
            audit.correction.write_rows(root / "fulltext_pilot/results.jsonl", [{"doi": "10.test/control", "status": "ok", "issues": [], "record": {"study_title": "Nothing", "abstract": "Nothing"}, "parsed": {"screening_decision": "exclude_out_of_scope", "domain_tags": [], "methodological_validity_tags": [], "primary_domain": "general_topic", "eligibility": {"basis": "unrelated_substance", "substances": [], "finding_quote": "Nothing", "input_integrity": "consistent"}}}])
            with patch.object(audit.correction, "advance_stage", return_value={"status": "complete"}), patch.object(audit.correction, "prepare_stage") as prepare:
                self.assertTrue(audit.advance(root, submit=True))
                prepare.assert_not_called()
            self.assertEqual(json.loads((root / "run.json").read_text())["status"], "validation_requires_review")


if __name__ == "__main__":
    unittest.main()
