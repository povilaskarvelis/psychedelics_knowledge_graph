import unittest

from pipeline.review.autofill_disorder_from_pdfs import (
    detect_paper_type as detect_disorder_pdf_type,
    infer_population as infer_pdf_population,
    infer_result_direction as infer_from_pdf,
    infer_system as infer_disorder_system,
)
from pipeline.review.autofill_mechanistic_from_pdfs import detect_paper_type as detect_mechanistic_pdf_type
from pipeline.review.autofill_stubs_from_abstracts import (
    infer_population as infer_abstract_population,
    infer_result_direction as infer_from_abstract,
)


class ResultDirectionInferenceTest(unittest.TestCase):
    def test_unclear_current_value_is_fillable(self) -> None:
        text = "randomized trial showed a significant reduction and remission"
        for infer in [infer_from_abstract, infer_from_pdf]:
            self.assertEqual(infer(text, "reduces depressive symptoms", "unclear"), "positive")

    def test_curated_non_unclear_value_is_preserved(self) -> None:
        text = "randomized trial showed a significant reduction and remission"
        for infer in [infer_from_abstract, infer_from_pdf]:
            self.assertEqual(infer(text, "reduces depressive symptoms", "mixed"), "mixed")

    def test_null_signal_is_detected_when_current_is_unclear(self) -> None:
        text = "there was no significant difference and did not improve symptoms"
        for infer in [infer_from_abstract, infer_from_pdf]:
            self.assertEqual(infer(text, "no significant clinical change", "unclear"), "null")


class MechanisticPdfTypeDetectionTest(unittest.TestCase):
    def test_supplement_and_study_design_do_not_override_primary_affinity_evidence(self) -> None:
        title = "Synthesis, characterization, and monoamine transporter activity of a test compound"
        body = (
            "The study design included in vitro radioligand binding assay methods. "
            "Supplementary material reports Ki and IC50 values for receptor and transporter targets."
        )

        self.assertEqual(
            detect_mechanistic_pdf_type(body, title_norm=title.lower()),
            "primary_results",
        )

    def test_title_level_conference_signal_is_still_preserved(self) -> None:
        title = "Conference abstract: receptor binding profile of a test compound"
        body = "The abstract reports Ki values from an assay."

        self.assertEqual(
            detect_mechanistic_pdf_type(body, title_norm=title.lower()),
            "conference_or_poster_abstract",
        )


class DisorderPdfInferenceTest(unittest.TestCase):
    def test_supplement_and_study_design_do_not_override_clinical_trial_signal(self) -> None:
        title = "Ketamine vs Electroconvulsive Therapy for Treatment-Resistant Depression"
        body = (
            "The study design was a randomized clinical trial with patients and placebo controls. "
            "Supplementary tables include MADRS response and remission outcomes."
        )

        self.assertEqual(
            detect_disorder_pdf_type(body, title=title.lower()),
            "primary_results",
        )

    def test_clear_clinical_signal_can_correct_preclinical_system(self) -> None:
        text = "randomized clinical trial in adult patients with depression"

        self.assertEqual(infer_disorder_system(text, "preclinical"), "clinical")

    def test_healthy_volunteer_only_population_is_not_mapped_to_disorder(self) -> None:
        text = "phase 1 study administered DMT harmala in 9 healthy volunteers and assessed subjective effects"

        for infer in [infer_abstract_population, infer_pdf_population]:
            self.assertEqual(infer("Major depressive disorder", text, ""), "healthy volunteers")

    def test_patient_and_healthy_control_population_stays_disorder_relevant(self) -> None:
        text = "randomized trial in patients with major depressive disorder and healthy volunteers"

        for infer in [infer_abstract_population, infer_pdf_population]:
            self.assertEqual(
                infer("Major depressive disorder", text, ""),
                "adults with major depressive disorder",
            )


if __name__ == "__main__":
    unittest.main()
