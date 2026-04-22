import unittest

from pipeline.extract.promote_ready_stubs import (
    DATASET_CONFIG,
    promotion_evidence_errors,
    row_diff,
    signature,
)
from pipeline.validate.validate_claims import warning_group


class PromotionIdentityTest(unittest.TestCase):
    def test_mechanistic_signature_distinguishes_affinity_values(self) -> None:
        id_fields = DATASET_CONFIG["mechanistic"]["id_fields"]
        base = {
            "compound": "Psilocybin",
            "target": "5-HT2A",
            "study_doi": "10.1000/example",
            "openalex_id": "",
            "assay_type": "radioligand binding",
            "affinity_type": "Ki",
            "affinity_unit": "nM",
        }

        low = {**base, "affinity_value": 10}
        high = {**base, "affinity_value": 100}

        self.assertNotEqual(signature(low, id_fields), signature(high, id_fields))

    def test_disorder_signature_distinguishes_outcome_measure(self) -> None:
        id_fields = DATASET_CONFIG["disorder"]["id_fields"]
        base = {
            "compound": "Psilocybin",
            "disorder": "Major depressive disorder",
            "study_doi": "10.1000/example",
            "openalex_id": "",
            "outcome_type": "reduces depressive symptoms",
        }

        madrs = {**base, "outcome_measure": "MADRS"}
        hamd = {**base, "outcome_measure": "HAM-D"}

        self.assertNotEqual(signature(madrs, id_fields), signature(hamd, id_fields))


class PromotionEvidenceGateTest(unittest.TestCase):
    def test_secondary_summary_metadata_title_is_blocked(self) -> None:
        row = {
            "source_type": "primary_study",
            "access_level": "secondary_summary",
            "evidence_location": "unknown",
            "evidence_locator": "Metadata/title snippet: Faculty Opinions recommendation of a trial",
            "study_title": "Faculty Opinions recommendation of Trial of Psilocybin versus Escitalopram for Depression.",
        }

        errors = promotion_evidence_errors(row)

        self.assertTrue(any("secondary_summary" in error for error in errors))
        self.assertTrue(any("metadata/title-only" in error for error in errors))
        self.assertTrue(any("recommendation record" in error for error in errors))

    def test_abstract_primary_study_is_allowed(self) -> None:
        row = {
            "source_type": "primary_study",
            "access_level": "abstract_only",
            "evidence_location": "abstract",
            "evidence_locator": "Abstract snippet: randomized trial reported remission outcomes",
            "study_title": "Trial of Psilocybin versus Escitalopram for Depression",
        }

        self.assertEqual(promotion_evidence_errors(row), [])

    def test_duplicate_diff_reports_changed_evidence_fields(self) -> None:
        existing = {
            "access_level": "abstract_only",
            "evidence_locator": "Abstract snippet: old",
            "outcome_measure": "MADRS",
        }
        candidate = {
            "access_level": "full_text_seen",
            "evidence_locator": "PDF snippet: new",
            "outcome_measure": "MADRS",
        }

        diff = row_diff(existing, candidate)

        self.assertEqual(diff["access_level"]["existing"], "abstract_only")
        self.assertEqual(diff["access_level"]["candidate"], "full_text_seen")
        self.assertIn("evidence_locator", diff)
        self.assertNotIn("outcome_measure", diff)


class ValidationWarningGroupTest(unittest.TestCase):
    def test_warning_group_classifies_primary_evidence_issues(self) -> None:
        self.assertEqual(
            warning_group("disorder row 1: metadata/title-only evidence locator"),
            "metadata_title_only",
        )
        self.assertEqual(
            warning_group("disorder row 1: secondary_summary row is weak evidence for the primary graph"),
            "secondary_summary",
        )


if __name__ == "__main__":
    unittest.main()
