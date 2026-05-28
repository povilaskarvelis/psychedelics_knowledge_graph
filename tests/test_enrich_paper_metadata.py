import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from pipeline.ingest.enrich_paper_metadata import (
    candidate_metadata_row,
    read_table,
    write_table,
)


class EnrichPaperMetadataTest(unittest.TestCase):
    def test_candidate_metadata_row_uses_plain_doi_and_metadata_fields(self) -> None:
        row = candidate_metadata_row(
            {
                "doi": "https://doi.org/10.1000/example",
                "datasets": "mechanistic | disorder",
                "study_title": "Example paper",
                "abstract": "Example abstract.",
                "publication_type": "journal-article",
            }
        )

        self.assertEqual(row["doi"], "10.1000/example")
        self.assertEqual(row["datasets"], "mechanistic | disorder")
        self.assertEqual(row["study_title"], "Example paper")
        self.assertEqual(row["abstract"], "Example abstract.")
        self.assertEqual(row["publication_type"], "journal-article")

    def test_write_table_writes_parquet_only(self) -> None:
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "paper_metadata_enrichment.parquet"
            write_table(
                path,
                [
                    {
                        "doi": "10.1000/example",
                        "datasets": "mechanistic",
                        "study_title": "Example paper",
                    }
                ],
            )

            rows = read_table(path)
            json_siblings = list(path.parent.glob("*.json"))

        self.assertEqual(rows[0]["doi"], "10.1000/example")
        self.assertEqual(rows[0]["study_title"], "Example paper")
        self.assertEqual(json_siblings, [])


if __name__ == "__main__":
    unittest.main()
