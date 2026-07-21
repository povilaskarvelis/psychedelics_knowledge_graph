import unittest

from pipeline.ingest.preprint_detection import classify_publication_stage


class PreprintDetectionTest(unittest.TestCase):
    def test_preprint_doi_and_posted_content_are_strong_preprint_signals(self) -> None:
        classification = classify_publication_stage(
            {
                "doi": "10.1101/2025.04.16.649217",
                "publication_type": "posted-content",
                "study_journal": "bioRxiv",
                "publisher": "openRxiv",
            }
        )

        self.assertEqual(classification["publication_stage"], "preprint")
        self.assertTrue(classification["is_preprint_like"])
        self.assertEqual(classification["preprint_signal_strength"], "strong")
        self.assertIn("doi:bioRxiv/medRxiv", classification["preprint_detection_basis"])
        self.assertIn("publication_type:posted-content", classification["preprint_detection_basis"])

    def test_published_doi_with_preprint_pdf_url_is_not_a_preprint_record(self) -> None:
        classification = classify_publication_stage(
            {
                "doi": "10.1021/acschemneuro.2c00123",
                "publication_type": "Journal Article | Research Support, Non-U.S. Gov't",
                "study_journal": "ACS Chemical Neuroscience",
                "publisher": "American Chemical Society (ACS)",
                "best_pdf_url": "https://www.biorxiv.org/content/10.1101/2022.01.19.476767.full.pdf",
            }
        )

        self.assertEqual(classification["publication_stage"], "published")
        self.assertTrue(classification["is_preprint_like"])
        self.assertEqual(classification["preprint_signal_strength"], "weak")
        self.assertIn("url:biorxiv.org", classification["preprint_detection_basis"])

    def test_osf_preprint_doi_and_mixed_preprint_metadata_are_strong_signals(self) -> None:
        osf = classify_publication_stage(
            {
                "doi": "10.31219/osf.io/dy5cu_v1",
                "publication_type": "article",
            }
        )
        osf_current_prefix = classify_publication_stage(
            {
                "doi": "10.31235/osf.io/fv6wj_v1",
                "publication_type": "article",
            }
        )
        mixed = classify_publication_stage(
            {
                "doi": "10.64898/2026.04.16.718915",
                "publication_type": "Journal Article | Preprint",
            }
        )

        self.assertEqual(osf["publication_stage"], "preprint")
        self.assertEqual(osf["preprint_signal_strength"], "strong")
        self.assertIn("doi:OSF preprint", osf["preprint_detection_basis"])
        self.assertEqual(osf_current_prefix["publication_stage"], "preprint")
        self.assertIn("doi:OSF preprint", osf_current_prefix["preprint_detection_basis"])
        self.assertEqual(mixed["publication_stage"], "preprint")
        self.assertEqual(mixed["preprint_signal_strength"], "strong")
        self.assertIn("publication_type:preprint", mixed["preprint_detection_basis"])


if __name__ == "__main__":
    unittest.main()
