import unittest

from pipeline.extract.promote_ready_stubs import (
    DATASET_CONFIG,
    promotion_evidence_errors,
    row_diff,
    signature,
)
from pipeline.validate.validate_claims import warning_group
from pipeline.validate.build_cleanup_report import build_candidate


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

    def test_opinion_research_direction_title_is_blocked(self) -> None:
        row = {
            "source_type": "primary_study",
            "access_level": "full_text_seen",
            "evidence_location": "text",
            "evidence_locator": "PDF snippet: patients with substance use disorder were mentioned in background text",
            "study_title": "Is there a place for psychedelics in sports practice?",
        }

        errors = promotion_evidence_errors(row)

        self.assertTrue(any("opinion/research-direction article" in error for error in errors))

    def test_healthy_volunteer_only_disorder_claim_is_blocked(self) -> None:
        row = {
            "source_type": "primary_study",
            "access_level": "full_text_seen",
            "evidence_location": "text",
            "evidence_locator": "PDF snippet: psychological effects were measured after dosing",
            "study_title": "Acute experiences and persisting psychological effects associated with DMT-harmala",
            "population": "healthy volunteers",
            "disorder": "Major depressive disorder",
        }

        errors = promotion_evidence_errors(row)

        self.assertTrue(any("healthy-volunteer" in error for error in errors))

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


class CleanupCandidateTest(unittest.TestCase):
    def test_numbered_abstract_record_is_demoted(self) -> None:
        row = {
            "compound": "Psilocybin",
            "disorder": "Alcohol use disorder",
            "study_title": "300 Psilocybin-induced changes in neural reactivity to alcohol and emotional cues in patients with alcohol use disorder: An fMRI pilot study",
            "study_doi": "10.1017/cts.2024.274",
            "paper_type": "primary_results",
            "source_type": "primary_study",
            "evidence_level": "high",
            "access_level": "full_text_seen",
            "result_direction": "positive",
            "evidence_locator": "PDF snippet: METHODS/STUDY POPULATION: Participants were recruited from a phase II trial.",
        }

        candidate = build_candidate("disorder", row, 1)

        self.assertIsNotNone(candidate)
        self.assertEqual(candidate["recommended_action"], "demote_from_main_kg")
        self.assertIn("numbered or structured abstract record", candidate["issues"])

    def test_opinion_research_direction_article_is_demoted(self) -> None:
        row = {
            "compound": "Ayahuasca",
            "disorder": "Substance use disorder",
            "study_title": "Is there a place for psychedelics in sports practice?",
            "study_doi": "10.1017/neu.2025.13",
            "paper_type": "primary_results",
            "source_type": "primary_study",
            "evidence_level": "high",
            "access_level": "full_text_seen",
            "result_direction": "mixed",
            "evidence_locator": "Abstract snippet: We aim to explore this topic and highlight research directions.",
        }

        candidate = build_candidate("disorder", row, 1)

        self.assertIsNotNone(candidate)
        self.assertEqual(candidate["recommended_action"], "demote_from_main_kg")
        self.assertIn("non-countable opinion/research-direction article", candidate["issues"])

    def test_healthy_volunteer_only_disorder_claim_is_demoted_with_paper_context(self) -> None:
        row = {
            "compound": "Ayahuasca",
            "disorder": "Major depressive disorder",
            "study_title": "Acute experiences and persisting psychological effects associated with an encapsulated DMT-harmala alkaloid combination: results of a phase 1 study",
            "study_doi": "10.1038/s41598-025-25767-x",
            "paper_type": "primary_results",
            "source_type": "primary_study",
            "evidence_level": "high",
            "access_level": "full_text_seen",
            "result_direction": "mixed",
            "evidence_locator": "Abstract snippet: Mystical experiences were associated with persisting psychological effects.",
        }
        paper_context = {
            "10.1038/s41598-025-25767-x": "DMT harmala was administered in 17 dosing sessions to 9 healthy volunteers. Findings suggest further trials in relevant patient populations."
        }

        candidate = build_candidate("disorder", row, 1, paper_context_by_doi=paper_context)

        self.assertIsNotNone(candidate)
        self.assertEqual(candidate["recommended_action"], "demote_from_main_kg")
        self.assertIn("healthy-volunteer-only study used as disorder efficacy evidence", candidate["issues"])

    def test_patient_plus_healthy_control_disorder_claim_is_not_demoted_for_population(self) -> None:
        row = {
            "compound": "Ketamine",
            "disorder": "Major depressive disorder",
            "study_title": "Hippocampal volume changes after ketamine administration in patients with major depressive disorder and healthy volunteers",
            "study_doi": "10.1000/example",
            "paper_type": "primary_results",
            "source_type": "primary_study",
            "evidence_level": "high",
            "access_level": "full_text_seen",
            "result_direction": "mixed",
            "evidence_locator": "PDF snippet: patients with major depressive disorder and healthy volunteers were enrolled.",
        }

        candidate = build_candidate("disorder", row, 1)

        if candidate is not None:
            self.assertNotIn("healthy-volunteer-only study used as disorder efficacy evidence", candidate["issues"])


if __name__ == "__main__":
    unittest.main()
