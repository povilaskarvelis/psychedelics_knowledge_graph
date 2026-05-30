import unittest

import pandas as pd

from pipeline.ingest.refresh_pubmed_publication_types import (
    unique_pmids,
    update_publication_types,
)


class RefreshPubmedPublicationTypesTest(unittest.TestCase):
    def test_unique_pmids_preserves_order_and_skips_blanks(self) -> None:
        pmids = unique_pmids(pd.Series(["123", "", "123", "456", None]))

        self.assertEqual(pmids, ["123", "456"])

    def test_update_publication_types_replaces_generic_labels(self) -> None:
        df = pd.DataFrame(
            [
                {"doi": "10.example/review", "pmid": "123", "publication_type": "journal-article"},
                {"doi": "10.example/primary", "pmid": "456", "publication_type": "Journal Article"},
                {"doi": "10.example/no-pmid", "pmid": "", "publication_type": "article"},
            ]
        )

        updated, updated_count = update_publication_types(
            df,
            {
                "123": "Journal Article | Systematic Review | Meta-Analysis",
                "456": "Journal Article",
            },
        )

        by_doi = {row["doi"]: row for row in updated.to_dict("records")}
        self.assertEqual(updated_count, 1)
        self.assertEqual(
            by_doi["10.example/review"]["publication_type"],
            "Journal Article | Systematic Review | Meta-Analysis",
        )
        self.assertEqual(by_doi["10.example/primary"]["publication_type"], "Journal Article")
        self.assertEqual(by_doi["10.example/no-pmid"]["publication_type"], "article")


if __name__ == "__main__":
    unittest.main()
