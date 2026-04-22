import unittest

from pipeline.ingest.export_discovery_queue_from_ledger import (
    build_export_rows,
    latest_rows_from_ledger,
    row_from_entry,
)


class ExportDiscoveryQueueFromLedgerTest(unittest.TestCase):
    def test_latest_rows_excludes_history_by_default(self) -> None:
        payload = {
            "dataset": "mechanistic",
            "entries": [
                {
                    "doi": "10.example/latest",
                    "title": "Latest",
                    "seen_in_latest_run": True,
                    "contexts": [{"compound": "MDMA", "entity": "SERT", "source": "discovery:pubmed"}],
                },
                {
                    "doi": "10.example/old",
                    "title": "Old",
                    "seen_in_latest_run": False,
                    "contexts": [{"compound": "LSD", "entity": "5-HT2A", "source": "discovery:openalex"}],
                },
            ],
        }

        rows = latest_rows_from_ledger(payload, include_history=False)

        self.assertEqual([row["doi"] for row in rows], ["10.example/latest"])

    def test_row_from_entry_prefers_discovery_context(self) -> None:
        row = row_from_entry(
            {
                "doi": "10.example/context",
                "title": "Context paper",
                "year": "2024",
                "contexts": [
                    {"compound": "", "entity": "", "source": "paper_library"},
                    {"compound": "Psilocybin", "entity": "MDD", "source": "discovery:pubmed"},
                ],
            }
        )

        self.assertEqual(row["compound"], "Psilocybin")
        self.assertEqual(row["entity"], "MDD")

    def test_build_export_rows_preserves_current_queue_then_appends_dropped(self) -> None:
        ledger_rows = [
            {
                "doi": "10.example/retained",
                "title": "Retained from ledger",
                "year": "2020",
                "retained_in_latest_queue": True,
            },
            {
                "doi": "10.example/dropped",
                "title": "Dropped from capped queue",
                "year": "2025",
                "retained_in_latest_queue": False,
            },
        ]
        current_queue_rows = [
            {
                "doi": "10.example/retained",
                "title": "Retained queue title",
                "year": "2020",
            }
        ]

        rows = build_export_rows(
            ledger_rows=ledger_rows,
            current_queue_rows=current_queue_rows,
            max_results=0,
            preserve_current_order=True,
        )

        self.assertEqual([row["doi"] for row in rows], ["10.example/retained", "10.example/dropped"])
        self.assertEqual(rows[0]["title"], "Retained queue title")


if __name__ == "__main__":
    unittest.main()
