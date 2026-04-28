import unittest

from pipeline.fulltext.export_evidence_triage_qa_sample import sample_report, summarize


class ExportEvidenceTriageQaSampleTest(unittest.TestCase):
    def test_sample_report_stratifies_targeted_audit_and_controls(self) -> None:
        rows = []
        for idx in range(1, 8):
            rows.append(
                {
                    "row_index": idx,
                    "study_doi": f"10.1000/review-{idx}",
                    "action": "propose_source_reclassification",
                    "automation_status": "needs_targeted_qa",
                    "classification": "review",
                    "confidence": 0.7 + idx / 100,
                }
            )
        for idx in range(8, 15):
            rows.append(
                {
                    "row_index": idx,
                    "study_doi": f"10.1000/commentary-{idx}",
                    "action": "propose_source_reclassification",
                    "automation_status": "needs_targeted_qa",
                    "classification": "commentary",
                    "confidence": 0.6 + idx / 100,
                }
            )
        rows.append(
            {
                "row_index": 20,
                "study_doi": "10.1000/audit",
                "action": "keep_non_empirical",
                "automation_status": "already_classified",
                "classification": "systematic_review",
                "confidence": 0.9,
            }
        )
        rows.append(
            {
                "row_index": 21,
                "study_doi": "10.1000/primary",
                "action": "keep_original_empirical",
                "automation_status": "no_change",
                "classification": "primary_study",
                "confidence": 0.8,
            }
        )

        sample = sample_report(
            "disorder",
            {"rows": rows},
            per_class_targeted=2,
            per_class_audit=1,
            primary_controls=1,
            salt="test",
        )
        summary = summarize(sample)

        self.assertEqual(summary["by_sample_group"]["targeted_rule_qa"], 4)
        self.assertEqual(summary["by_sample_group"]["auto_triage_audit"], 1)
        self.assertEqual(summary["by_sample_group"]["primary_control"], 1)
        self.assertTrue(all("qa_decision" in row for row in sample))
        self.assertTrue(all(row["dataset"] == "disorder" for row in sample))

    def test_sample_report_is_reproducible_for_same_salt(self) -> None:
        rows = [
            {
                "row_index": idx,
                "study_doi": f"10.1000/{idx}",
                "action": "propose_source_reclassification",
                "automation_status": "needs_targeted_qa",
                "classification": "review",
                "confidence": 0.8,
            }
            for idx in range(1, 20)
        ]

        first = sample_report("mechanistic", {"rows": rows}, 3, 0, 0, salt="fixed")
        second = sample_report("mechanistic", {"rows": rows}, 3, 0, 0, salt="fixed")

        self.assertEqual(
            [(row["row_index"], row["study_doi"]) for row in first],
            [(row["row_index"], row["study_doi"]) for row in second],
        )


if __name__ == "__main__":
    unittest.main()
