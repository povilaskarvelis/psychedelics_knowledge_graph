import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from pipeline.kg import build_evidence_tables as b
from pipeline.kg.target_identity import explicit_unresolved_target, single_registered_target, recovered_target_detail_reason


class TargetIdentityAlignmentTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = b.registry_lookup(b.DEFAULT_REGISTRY_PATH)

    def test_complete_target_phrase_uses_one_existing_identity(self):
        cases = {
            "Human kappa opioid receptor (KOP; OPRK1)": "kappa opioid receptor (OPRK1)",
            "D3 dopamine receptor": "Dopamine D3 receptor (DRD3)",
            "D4 dopamine receptor": "Dopamine D4 receptor (DRD4)",
            "Human dopamine D4.4 receptor": "Dopamine D4 receptor (DRD4)",
            "Glutamate NMDA receptor": "NMDA receptor",
            "Human dopamine transporter (hDAT; SLC6A3)": "DAT (SLC6A3)",
            "Rat serotonin transporter (rSERT; SERT)": "SERT (SLC6A4)",
            "Bovine serotonin transporter (bSERT)": "SERT (SLC6A4)",
            "Human norepinephrine transporter (hNET/NET)": "NET (SLC6A2)",
            "plasma membrane serotonin transporter": "SERT (SLC6A4)",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                match = b.match_registry_entity(raw, "target", self.registry, {"assay_type": "Binding assay"})
                self.assertTrue(match["matched"])
                self.assertEqual(match["label"], expected)
                self.assertEqual(match["kind"], "target")

    def test_phrase_parser_does_not_drop_unresolved_or_relational_tokens(self):
        for raw in [
            "D6 dopamine receptor", "Human dopamine D4.7 receptor",
            "Human dopamine transporter (hDAT; mutant T356M)",
            "KORD (D138N human kappa-opioid receptor DREADD)",
            "Human kappa opioid receptor and unknown receptor",
            "Human kappa opioid receptor and mu opioid receptor",
            "Dopamine and DAT", "DAT-mediated dopamine release",
            "Human dopamine transporter mRNA expression", "PCP receptor",
            "Anti-PCP antibody", "Human SERT and NET", "NMDA receptor heteromer",
            "Unknown subtype of dopamine receptor", "GABAergic NMDA-dependent signaling",
        ]:
            with self.subTest(raw=raw):
                self.assertIsNone(single_registered_target(
                    b.label_key(raw), self.registry,
                    b.DIRECT_TARGET_REGISTRY_STATUSES | b.TARGET_FAMILY_REGISTRY_STATUSES,
                ))

    def test_primary_detail_requires_saved_typed_assay(self):
        row = {"source_item_type": "primary_item", "source_type": "primary",
               "target": "Unregistered receptor X", "target_type": "receptor",
               "assay_type": "Radioligand competition", "finding_summary": "No binding was detected."}
        self.assertTrue(explicit_unresolved_target(row, row["target"]))
        for field in ["target_type", "assay_type", "finding_summary"]:
            self.assertFalse(explicit_unresolved_target({**row, field: "not_reported"}, row["target"]))
        self.assertFalse(explicit_unresolved_target({**row, "source_type": "review"}, row["target"]))
        self.assertFalse(explicit_unresolved_target(row, "Target from background"))
        for target in ["Target unknown", "Molecular target", "Mechanisms of action", "not_reported"]:
            self.assertFalse(explicit_unresolved_target({**row, "target": target}, target))

    def test_recovered_identity_does_not_infer_direct_target_evidence(self):
        base = {"source_item_type": "primary_item", "compound": "Ketamine"}
        for assay, reason in [
            ("Molecular docking and predicted binding", "predicted_target_requires_experimental_validation"),
            ("Antagonist pretreatment followed by locomotor behavior", "target_mechanism_without_direct_assay"),
            ("Knockdown followed by receptor binding", "target_mechanism_without_direct_assay"),
            ("", "target_mechanism_without_direct_assay"),
            ("Competition radioligand binding; no affinity detected", ""),
            ("Whole-cell patch-clamp electrophysiology", ""),
        ]:
            with self.subTest(assay=assay):
                self.assertEqual(recovered_target_detail_reason({**base, "assay_type": assay}), reason)
        self.assertEqual(recovered_target_detail_reason({**base, "source_item_type": "review_relationship"}), "")

    def test_preexisting_unambiguous_matches_keep_their_admission_path(self):
        # These real assay descriptions were valid before the identity repair.
        # A new phrase parser must not impose a narrower assay whitelist on
        # them merely because their target has a species/variant descriptor.
        for target, assay in [
            ("Human CYP2D6", "Substrate-induced absorbance spectral changes; high-spin CYP2D6 titration"),
            ("5-HT2A receptor, wild-type", "TRUPATH Gq BRET concentration-response assay"),
            ("Human 5-HT1A", "IP1 accumulation assay measured by homogeneous time-resolved fluorescence"),
        ]:
            with self.subTest(target=target):
                match = b.match_registry_entity(target, "target", self.registry, {"assay_type": assay})
                self.assertTrue(match["matched"])
                self.assertNotEqual(match["match_type"], "complete_registered_target_phrase")

    def test_complete_supported_target_lists_still_expand_before_detail_fallback(self):
        row = {"domain": "molecular_target", "compound": "MDMA", "graph_subject_kind": "atomic_compound",
               "target": "SERT and DAT", "target_type": "transporter", "assay_type": "Uptake inhibition",
               "source_item_type": "primary_item", "source_type": "primary", "finding_summary": "Uptake was inhibited."}
        expanded = b.entity_expanded_rows(row, row["domain"], self.registry, b.node_vocabulary_lookup())
        self.assertEqual(len(expanded), 2)
        for item in expanded:
            self.assertEqual(item["entity_split_source_label"], "SERT and DAT")
            self.assertEqual(item["finding_summary"], row["finding_summary"])

    def test_saved_findings_preserve_assay_values_identity_and_admission(self):
        fixtures = Path(__file__).parent / "fixtures/target_identity_saved_rows.json"
        source_rows = json.loads(fixtures.read_text())
        originals = {(r["task_id"], str(r["source_item_index"])): r for r in source_rows}
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            b.build_tables(
                out_dir=out, write_duckdb=False,
                graph_sources={"routed_extractions": {"path": fixtures, "domain": "routed",
                    "dataset": "routed", "default_evidence_type": "primary_evidence", "skip_audit": True}},
            )
            findings = pd.read_parquet(out / "findings.parquet").fillna("")
            audit = pd.read_parquet(out / "normalization_audit.parquet")
            self.assertEqual(len(findings) + len(audit), len(source_rows))
            self.assertEqual(len(audit), 2)
            self.assertTrue(audit.normalization_status.eq("compound_reference_not_graphable").all())
            self.assertTrue(findings.finding_id.is_unique)
            for row in findings.to_dict("records"):
                raw = json.loads(row["raw_row_json"])
                original = originals[(raw["task_id"], str(raw["source_item_index"]))]
                normalized_original = b.normalize_claim_metadata(original, original["domain"])
                self.assertEqual(raw.get("system"), normalized_original.get("system"))
                for field in ["target", "target_type", "assay_type", "species_or_cell_line",
                              "metric", "value", "unit", "effect_or_statistic", "finding_summary",
                              "support", "evidence_location", "evidence_locator", "comparator_or_reference"]:
                    self.assertEqual(raw.get(field), original.get(field), (row["study_doi"], field))
            by_doi = findings.set_index("study_doi")
            for doi in ["10.1016/j.bmc.2012.02.040", "10.1016/j.neuropharm.2018.01.020",
                        "10.1007/s00213-011-2616-6"]:
                self.assertEqual(by_doi.loc[doi, "graph_admission_status"], "main_graph")
            # A null affinity result is kept; a blocker/behavior experiment is
            # not upgraded to direct target pharmacology by fixing its name.
            for doi in ["10.1111/adb.12938", "10.1093/bja/74.1.79"]:
                self.assertEqual(by_doi.loc[doi, "graph_admission_status"], "paper_detail")
                self.assertEqual(by_doi.loc[doi, "graph_admission_reason"], "target_mechanism_without_direct_assay")
            self.assertEqual(by_doi.loc["10.1016/j.bmcl.2005.05.048", "graph_admission_status"], "paper_detail")
            unresolved = findings[findings.entity_match_type.isin(["unresolved_primary_target_detail_only", "historical_target_site_detail_only"])]
            self.assertEqual(len(unresolved), 3)
            self.assertTrue(unresolved.graph_admission_status.eq("paper_detail").all())
            self.assertTrue(unresolved.graph_admission_reason.isin(["explicit_target_requires_identity_resolution", "target_site_requires_identity_resolution"]).all())
            for row in unresolved.to_dict("records"):
                self.assertEqual(row["entity_label"], json.loads(row["raw_row_json"])["target"])


if __name__ == "__main__":
    unittest.main()
