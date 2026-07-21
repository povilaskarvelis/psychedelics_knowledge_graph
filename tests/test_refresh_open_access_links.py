import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pandas as pd

from pipeline.ingest.refresh_open_access_links import (
    apply_open_access_fields,
    candidate_rows,
    fresh_open_access_observation,
    materialize_scoped_metadata,
    parse_csv_values,
    parse_provider_order,
    pdf_url_hosts_for_row,
    pmcid_hint_from_row,
    refresh_row,
    row_has_probable_pdf_url,
)


class RefreshOpenAccessLinksTest(unittest.TestCase):
    def test_fresh_oa_observation_does_not_depend_on_stored_row(self) -> None:
        self.assertTrue(
            fresh_open_access_observation(
                {"is_oa": "true", "oa_status": "green", "oa_url": "https://example.org/article"}
            )["positive"]
        )
        self.assertFalse(
            fresh_open_access_observation({"is_oa": "false", "oa_status": "closed"})["positive"]
        )
        self.assertFalse(fresh_open_access_observation({})["positive"])

    def test_parse_provider_order_rejects_metadata_providers(self) -> None:
        with self.assertRaises(ValueError):
            parse_provider_order("unpaywall,crossref")

    def test_refresh_row_returns_current_run_oa_evidence_separately(self) -> None:
        row = pd.Series(
            {
                "doi": "10.1000/current",
                "open_access_is_oa": "false",
                "open_access_status": "closed",
                "open_access_url": "",
                "best_pdf_url": "",
                "pdf_url_candidates": "",
            }
        )
        with patch(
            "pipeline.ingest.refresh_open_access_links.lookup_unpaywall_metadata",
            return_value={
                "is_oa": "true",
                "oa_status": "green",
                "oa_url": "https://example.org/article",
            },
        ):
            updates, queried, errors, skipped, observations = refresh_row(
                row,
                provider_order=["unpaywall"],
                clients={"unpaywall": object()},
                settings={"unpaywall_email": "researcher@example.org"},
                expand_existing_pdf_candidates=True,
            )

        self.assertEqual(queried, ["unpaywall"])
        self.assertEqual(errors, [])
        self.assertEqual(skipped, [])
        self.assertTrue(observations["unpaywall"]["positive"])
        self.assertEqual(updates["open_access_status"], "green")

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
                "best_pdf_url": "https://ftp.ncbi.nlm.nih.gov/pub/pmc/deprecated/oa_pdf/aa/bb/article.PMC123.pdf",
                "pdf_url_candidates": "https://example.org/new.pdf",
            },
            authoritative_status=True,
        )

        self.assertTrue(changed)
        self.assertEqual(updates["open_access_is_oa"], "true")
        self.assertEqual(updates["open_access_status"], "gold")
        self.assertEqual(updates["open_access_url"], "https://example.org/article")
        self.assertEqual(
            updates["best_pdf_url"],
            "https://ftp.ncbi.nlm.nih.gov/pub/pmc/deprecated/oa_pdf/aa/bb/article.PMC123.pdf",
        )
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
            only_pdf_url_hosts=None,
            limit=0,
        )

        self.assertEqual(selected["doi"].tolist(), ["10.example/a", "10.example/c"])

    def test_missing_pdf_selection_does_not_treat_landing_page_as_pdf(self) -> None:
        df = pd.DataFrame(
            [
                {
                    "doi": "10.1000/landing",
                    "best_pdf_url": "https://example.org/article/landing",
                    "pdf_url_candidates": "https://example.org/article/landing",
                },
                {
                    "doi": "10.1000/pdf",
                    "best_pdf_url": "https://example.org/article.pdf",
                    "pdf_url_candidates": "https://example.org/article.pdf",
                },
            ]
        )

        selected = candidate_rows(
            df,
            doi_file="",
            routing_table="",
            only_retained_secondary=False,
            only_missing_pdf_url=True,
            only_pdf_url_hosts=None,
            limit=0,
        )

        self.assertEqual(selected["doi"].tolist(), ["10.1000/landing"])
        self.assertFalse(row_has_probable_pdf_url(df.iloc[0]))
        self.assertTrue(row_has_probable_pdf_url(df.iloc[1]))

    def test_materialize_scoped_metadata_adds_missing_candidate_rows(self) -> None:
        metadata = pd.DataFrame([{"doi": "10.1000/existing", "study_title": "Existing"}])
        candidates = pd.DataFrame(
            [
                {"doi": "10.1000/existing", "study_title": "Fallback", "pmcid": "PMC1"},
                {"doi": "10.1000/new", "study_title": "New", "pmcid": "PMC2"},
            ]
        )
        with TemporaryDirectory() as tmp:
            papers = Path(tmp) / "candidate.parquet"
            candidates.to_parquet(papers, index=False)
            materialized, added = materialize_scoped_metadata(
                metadata,
                papers,
                {"10.1000/existing", "10.1000/new"},
            )

        selected = materialized[materialized["doi"].isin({"10.1000/existing", "10.1000/new"})]
        self.assertEqual(added, 1)
        self.assertEqual(set(selected["doi"]), {"10.1000/existing", "10.1000/new"})
        self.assertEqual(selected.set_index("doi").at["10.1000/existing", "study_title"], "Existing")
        self.assertEqual(selected.set_index("doi").at["10.1000/existing", "pmcid"], "PMC1")

    def test_candidate_rows_can_select_existing_pdf_url_hosts(self) -> None:
        df = pd.DataFrame(
            [
                {"doi": "10.example/a", "best_pdf_url": "https://europepmc.org/api/getPdf?pmcid=PMC1"},
                {"doi": "10.example/b", "best_pdf_url": "https://example.org/b.pdf"},
                {
                    "doi": "10.example/c",
                    "best_pdf_url": "https://publisher.example/c.pdf",
                    "pdf_url_candidates": "https://pmc.ncbi.nlm.nih.gov/articles/PMC2/pdf/article.pdf",
                },
            ]
        )

        selected = candidate_rows(
            df,
            doi_file="",
            routing_table="",
            only_retained_secondary=False,
            only_missing_pdf_url=False,
            only_pdf_url_hosts=parse_csv_values("europepmc.org,pmc.ncbi.nlm.nih.gov"),
            limit=0,
        )

        self.assertEqual(selected["doi"].tolist(), ["10.example/a", "10.example/c"])

    def test_pdf_url_hosts_and_pmcid_hint_read_candidate_urls(self) -> None:
        row = pd.Series(
            {
                "best_pdf_url": "https://europepmc.org/api/getPdf?pmcid=PMC123",
                "pdf_url_candidates": "https://pmc.ncbi.nlm.nih.gov/articles/PMC123/pdf/article.pdf",
                "open_access_url": "",
            }
        )

        self.assertEqual(pdf_url_hosts_for_row(row), {"europepmc.org", "pmc.ncbi.nlm.nih.gov"})
        self.assertEqual(pmcid_hint_from_row(row), "PMC123")


if __name__ == "__main__":
    unittest.main()
