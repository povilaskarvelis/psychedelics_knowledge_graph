import unittest

import pandas as pd

from pipeline.ingest.refresh_open_access_links import (
    apply_open_access_fields,
    candidate_rows,
    parse_provider_order,
)


class RefreshOpenAccessLinksTest(unittest.TestCase):
    def test_parse_provider_order_rejects_metadata_providers(self) -> None:
        with self.assertRaises(ValueError):
            parse_provider_order("unpaywall,crossref")

    def test_apply_open_access_fields_combines_pdf_candidates_only(self) -> None:
        row = pd.Series(
            {
                "open_access_is_oa": "",
                "open_access_status": "",
                "open_access_url": "",
                "best_pdf_url": "",
                "pdf_url_candidates": "https://example.org/old.pdf",
            }
        )

        updates, changed = apply_open_access_fields(
            row,
            {
                "is_oa": "true",
                "oa_status": "gold",
                "oa_url": "https://example.org/article",
                "best_pdf_url": "https://europepmc.org/api/getPdf?pmcid=PMC123",
                "pdf_url_candidates": "https://example.org/new.pdf",
            },
            authoritative_status=True,
        )

        self.assertTrue(changed)
        self.assertEqual(updates["open_access_is_oa"], "true")
        self.assertEqual(updates["open_access_status"], "gold")
        self.assertEqual(updates["open_access_url"], "https://example.org/article")
        self.assertEqual(updates["best_pdf_url"], "https://europepmc.org/api/getPdf?pmcid=PMC123")
        self.assertIn("https://example.org/old.pdf", updates["pdf_url_candidates"])
        self.assertIn("https://example.org/new.pdf", updates["pdf_url_candidates"])

    def test_candidate_rows_can_select_missing_secondary_pdf_urls(self) -> None:
        df = pd.DataFrame(
            [
                {"doi": "10.example/a", "best_pdf_url": ""},
                {"doi": "10.example/b", "best_pdf_url": "https://example.org/b.pdf"},
                {"doi": "10.example/c", "best_pdf_url": ""},
            ]
        )

        selected = candidate_rows(
            df,
            doi_file="",
            routing_table="",
            only_retained_secondary=False,
            only_missing_pdf_url=True,
            limit=0,
        )

        self.assertEqual(selected["doi"].tolist(), ["10.example/a", "10.example/c"])


if __name__ == "__main__":
    unittest.main()
