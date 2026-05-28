import unittest

from pipeline.extract.build_extraction_v1_batch_queue import split_records


class BuildExtractionV1BatchQueueTests(unittest.TestCase):
    def test_split_records_respects_request_limit(self) -> None:
        records = [{"dataset": "mechanistic", "payload": "x"} for _ in range(5)]

        parts = split_records(records, max_requests=2, max_approx_input_tokens=10_000)

        self.assertEqual([(start, limit) for start, limit, _ in parts], [(1, 2), (3, 2), (5, 1)])

    def test_split_records_respects_token_budget(self) -> None:
        records = [
            {"dataset": "mechanistic", "payload": "x" * 100},
            {"dataset": "mechanistic", "payload": "y" * 100},
            {"dataset": "mechanistic", "payload": "z" * 100},
        ]

        parts = split_records(records, max_requests=10, max_approx_input_tokens=40)

        self.assertEqual([(start, limit) for start, limit, _ in parts], [(1, 1), (2, 1), (3, 1)])


if __name__ == "__main__":
    unittest.main()
