import unittest

from pipeline.ingest.seed_from_dois import dedupe_by_context


class SeedFromDoisTest(unittest.TestCase):
    def test_dedupes_mechanistic_rows_by_doi_compound_and_target(self) -> None:
        rows = [
            {"study_doi": "10.1000/EXAMPLE", "compound": "Psilocybin", "target": "5-HT2A"},
            {"study_doi": "https://doi.org/10.1000/example", "compound": "psilocybin", "target": "5 HT2A"},
            {"study_doi": "10.1000/example", "compound": "Psilocybin", "target": "5-HT1A"},
        ]

        deduped, duplicate_count = dedupe_by_context(rows, "mechanistic")

        self.assertEqual(duplicate_count, 1)
        self.assertEqual(len(deduped), 2)
        self.assertEqual(deduped[0]["target"], "5-HT2A")
        self.assertEqual(deduped[1]["target"], "5-HT1A")

    def test_dedupes_disorder_rows_after_canonicalization(self) -> None:
        rows = [
            {
                "study_doi": "10.1000/example",
                "compound": "Psilocybin",
                "disorder": "End-of-life anxiety",
            },
            {
                "study_doi": "10.1000/example",
                "compound": "psilocybin",
                "disorder": "Distress associated with life-threatening disease",
            },
            {
                "study_doi": "10.1000/example",
                "compound": "Psilocybin",
                "disorder": "Depression",
            },
        ]

        deduped, duplicate_count = dedupe_by_context(rows, "disorder")

        self.assertEqual(duplicate_count, 1)
        self.assertEqual(len(deduped), 2)
        self.assertEqual(deduped[0]["disorder"], "End-of-life anxiety")
        self.assertEqual(deduped[1]["disorder"], "Depression")


if __name__ == "__main__":
    unittest.main()
