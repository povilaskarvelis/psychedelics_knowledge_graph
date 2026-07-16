import unittest
from pathlib import Path
import tempfile

import pandas as pd

from pipeline.review.build_gemini_domain_routing_batch_queue import (
    previously_prescreen_retained_dois,
    split_records,
)


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

    def test_previously_prescreen_retained_dois_uses_previous_prescreen_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "previous_candidates.parquet"
            pd.DataFrame(
                [
                    {"doi": "https://doi.org/10.1000/retained", "prescreen_retained_for_extraction_candidate": True},
                    {"doi": "10.1000/excluded", "prescreen_retained_for_extraction_candidate": False},
                    {"doi": "10.1000/second-retained", "prescreen_retained_for_extraction_candidate": True},
                    {"doi": "", "prescreen_retained_for_extraction_candidate": True},
                ]
            ).to_parquet(path, index=False)

            reusable = previously_prescreen_retained_dois(path)

        self.assertEqual(reusable, {"10.1000/retained", "10.1000/second-retained"})


if __name__ == "__main__":
    unittest.main()
