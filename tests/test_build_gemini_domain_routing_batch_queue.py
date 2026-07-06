import unittest

from pipeline.review.build_gemini_domain_routing_batch_queue import split_records


class BuildGeminiDomainRoutingBatchQueueTests(unittest.TestCase):
    def test_split_records_respects_request_and_token_limits(self) -> None:
        records = [
            {
                "doi": f"10.example/{index}",
                "study_title": "Psilocybin paper",
                "abstract": "Psilocybin " * 100,
                "study_year": "2025",
                "publication_type": "Journal Article",
                "source_family": "primary_or_unclear",
                "literature_route": "primary_literature_extraction",
                "primary_secondary_source_type": "",
                "secondary_source_types": "",
                "metadata_secondary_types": "",
                "title_abstract_secondary_types": "",
                "non_primary_flags": "",
                "literature_type_confidence": "high",
                "mesh_terms": "",
                "keywords": "",
            }
            for index in range(5)
        ]

        parts = split_records(records, max_requests=2, max_approx_input_tokens=10_000_000)

        self.assertEqual([(start, limit) for start, limit, _ in parts], [(1, 2), (3, 2), (5, 1)])


if __name__ == "__main__":
    unittest.main()
