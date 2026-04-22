import unittest

from pipeline.review.autofill_disorder_from_pdfs import infer_result_direction as infer_from_pdf
from pipeline.review.autofill_stubs_from_abstracts import infer_result_direction as infer_from_abstract


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


if __name__ == "__main__":
    unittest.main()
