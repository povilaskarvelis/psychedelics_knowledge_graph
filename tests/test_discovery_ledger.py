import unittest

from pipeline.ingest.discover_literature import apply_protected_retention, update_ledger


class DiscoveryLedgerTest(unittest.TestCase):
    def test_protected_retention_keeps_available_protected_rows_over_cap(self) -> None:
        rows = [
            {"doi": "10.example/unprotected-1", "title": "A", "year": "2025"},
            {"doi": "10.example/protected-1", "title": "B", "year": "2024"},
            {"doi": "10.example/protected-2", "title": "C", "year": "2023"},
            {"doi": "10.example/unprotected-2", "title": "D", "year": "2022"},
        ]
        retained, report = apply_protected_retention(
            rows=rows,
            max_results=1,
            protected_sources={
                "10.example/protected-1": [{"source": "known_study:search_development_seed"}],
                "10.example/protected-2": [{"source": "curated"}],
            },
        )

        self.assertEqual([row["doi"] for row in retained], ["10.example/protected-1", "10.example/protected-2"])
        self.assertEqual(report["protected_dois_available"], 2)
        self.assertEqual(report["protected_dois_retained"], 2)
        self.assertEqual(report["protected_over_cap"], 1)

    def test_ledger_carries_previous_entries_and_marks_latest_run_state(self) -> None:
        existing = {
            "10.example/old": {
                "doi": "10.example/old",
                "dataset": "mechanistic",
                "title": "Previously found",
                "first_seen_utc": "2026-01-01T00:00:00+00:00",
                "last_seen_utc": "2026-01-01T00:00:00+00:00",
                "providers": ["openalex"],
                "queries": ["old query"],
                "contexts": [],
                "latest_run_id": "old-run",
            }
        }
        run_meta = {
            "run_id": "mechanistic:2026-04-19T00:00:00+00:00",
            "generated_at": "2026-04-19T00:00:00+00:00",
        }

        ledger = update_ledger(
            existing=existing,
            dataset="mechanistic",
            run_id=run_meta["run_id"],
            run_meta=run_meta,
            all_rows=[
                {
                    "doi": "10.example/new",
                    "title": "Newly found",
                    "year": "2026",
                    "provider": "pubmed",
                    "providers": ["pubmed"],
                    "query": "new query",
                    "queries": ["new query"],
                    "compound": "MDMA",
                    "entity": "SERT (SLC6A4)",
                }
            ],
            retained_rows=[],
            protected_sources={
                "10.example/old": [{"source": "paper_library", "study_title": "Previously found"}]
            },
        )

        by_doi = {entry["doi"]: entry for entry in ledger["entries"]}
        self.assertIn("10.example/old", by_doi)
        self.assertIn("10.example/new", by_doi)
        self.assertFalse(by_doi["10.example/old"]["seen_in_latest_run"])
        self.assertTrue(by_doi["10.example/old"]["in_paper_library"])
        self.assertTrue(by_doi["10.example/new"]["seen_in_latest_run"])
        self.assertFalse(by_doi["10.example/new"]["retained_in_latest_queue"])
        self.assertEqual(by_doi["10.example/new"]["providers"], ["pubmed"])


if __name__ == "__main__":
    unittest.main()
