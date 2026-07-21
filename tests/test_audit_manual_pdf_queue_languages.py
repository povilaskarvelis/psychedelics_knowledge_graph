import unittest

from pipeline.fulltext.audit_manual_pdf_queue_languages import assess_language


class ManualPdfQueueLanguageAuditTests(unittest.TestCase):
    def test_strong_german_title_is_excluded_even_with_missing_metadata(self):
        result = assess_language(
            title="Der Rote Keulenkopf und seine Verwendung",
            metadata_language="",
            detected_language="de",
            confidence=0.99,
        )
        self.assertEqual(result["language_audit_decision"], "exclude_non_english")

    def test_metadata_conflict_is_reviewed_when_title_is_confidently_english(self):
        result = assess_language(
            title="Alkaloids of the Australian Leguminosae",
            metadata_language="es",
            detected_language="en",
            confidence=0.99,
        )
        self.assertEqual(result["language_audit_decision"], "review_language_signal")

    def test_short_ambiguous_non_english_title_is_reviewed(self):
        result = assess_language(
            title="Santo Daime",
            metadata_language="pt",
            detected_language="pt",
            confidence=0.80,
        )
        self.assertEqual(result["language_audit_decision"], "review_language_signal")

    def test_confident_english_is_retained(self):
        result = assess_language(
            title="Ketamine treatment for refractory depression",
            metadata_language="en",
            detected_language="en",
            confidence=0.99,
        )
        self.assertEqual(result["language_audit_decision"], "retain_language_eligible")

    def test_translated_title_with_english_abstract_marker_is_excluded(self):
        result = assess_language(
            title="[The acute effects of MDMA on oxidative stress in rat brain].",
            metadata_language="en",
            detected_language="en",
            confidence=0.99,
            publication_type="English Abstract | Journal Article",
        )
        self.assertEqual(result["language_audit_decision"], "exclude_non_english")


if __name__ == "__main__":
    unittest.main()
