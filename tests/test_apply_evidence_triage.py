import unittest

from pipeline.fulltext.apply_evidence_triage import apply_triage


class ApplyEvidenceTriageTest(unittest.TestCase):
    def test_apply_triage_updates_only_valid_eligible_rows(self) -> None:
        curated = [
            {
                "study_doi": "10.1000/review",
                "source_type": "primary_study",
                "paper_type": "primary_results",
                "study_design": "randomized_controlled_trial",
                "notes": "",
            }
        ]
        report = {
            "rows": [
                {
                    "row_index": 1,
                    "study_doi": "10.1000/review",
                    "action": "propose_source_reclassification",
                    "automation_status": "auto_apply_eligible",
                    "classification": "systematic_review",
                    "confidence": 0.92,
                    "current_source_type": "primary_study",
                    "target_source_type": "secondary_evidence",
                    "current_paper_type": "primary_results",
                    "target_paper_type": "systematic_review",
                    "current_study_design": "randomized_controlled_trial",
                    "target_study_design": "systematic_review",
                    "signals": "title matches systematic_review",
                }
            ]
        }

        summary = apply_triage(curated, report, min_confidence=0.85, mutate=True)

        self.assertEqual(summary["changes_ready"], 1)
        self.assertEqual(curated[0]["source_type"], "secondary_evidence")
        self.assertEqual(curated[0]["paper_type"], "systematic_review")
        self.assertEqual(curated[0]["study_design"], "systematic_review")
        self.assertIn("Automated evidence triage", curated[0]["notes"])

    def test_apply_triage_skips_stale_report_rows(self) -> None:
        curated = [
            {
                "study_doi": "10.1000/review",
                "source_type": "secondary_evidence",
                "paper_type": "primary_results",
                "study_design": "randomized_controlled_trial",
            }
        ]
        report = {
            "rows": [
                {
                    "row_index": 1,
                    "study_doi": "10.1000/review",
                    "action": "propose_source_reclassification",
                    "automation_status": "auto_apply_eligible",
                    "classification": "systematic_review",
                    "confidence": 0.92,
                    "current_source_type": "primary_study",
                    "target_source_type": "secondary_evidence",
                    "current_paper_type": "primary_results",
                    "target_paper_type": "systematic_review",
                    "current_study_design": "randomized_controlled_trial",
                    "target_study_design": "systematic_review",
                }
            ]
        }

        summary = apply_triage(curated, report, min_confidence=0.85, mutate=True)

        self.assertEqual(summary["changes_ready"], 0)
        self.assertEqual(summary["skipped"], 1)
        self.assertEqual(curated[0]["paper_type"], "primary_results")


if __name__ == "__main__":
    unittest.main()
