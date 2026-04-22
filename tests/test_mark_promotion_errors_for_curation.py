import unittest

from pipeline.review.mark_promotion_errors_for_curation import index_report_errors_by_ready_row


class MarkPromotionErrorsForCurationTest(unittest.TestCase):
    def test_indexes_promotion_errors_by_ready_row(self) -> None:
        report = {
            "errors": [
                {"row_index": 3, "study_doi": "10.1000/a", "messages": ["blocked"]},
                {"row_index": "5", "study_doi": "10.1000/b", "messages": ["blocked"]},
                {"row_index": 0, "study_doi": "ignored", "messages": ["ignored"]},
            ]
        }

        indexed = index_report_errors_by_ready_row(report)

        self.assertEqual(sorted(indexed), [3, 5])
        self.assertEqual(indexed[3]["study_doi"], "10.1000/a")
        self.assertEqual(indexed[5]["study_doi"], "10.1000/b")


if __name__ == "__main__":
    unittest.main()
