import json
from pathlib import Path
import tempfile
import unittest

import pandas as pd

from pipeline.fulltext.backfill_pdf_failure_categories import backfill_pdf_failure_categories


class TestBackfillPdfFailureCategories(unittest.TestCase):
    def test_backfills_failure_category_from_routed_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            candidate_table = root / "candidate_papers.parquet"
            report_path = root / "routed_report.json"
            out_report = root / "backfill_report.json"
            pd.DataFrame(
                [
                    {
                        "doi": "10.1000/rate",
                        "pdf_download_status": "download_failed",
                    }
                ]
            ).to_parquet(candidate_table, engine="pyarrow", index=False)
            report_path.write_text(
                json.dumps(
                    {
                        "records": [
                            {
                                "doi": "10.1000/rate",
                                "status": "download_failed",
                                "error": "HTTPError: HTTP Error 429: Too Many Requests",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            report = backfill_pdf_failure_categories(
                candidate_table=candidate_table,
                legacy_jsons=[],
                audit_report_paths=[report_path],
                report_json=out_report,
            )

            df = pd.read_parquet(candidate_table)
            self.assertEqual(report["counts"]["updated_rows"], 1)
            self.assertEqual(df.loc[0, "pdf_download_failure_category"], "rate_limited")
            self.assertTrue(bool(df.loc[0, "pdf_download_retry_recommended"]))

    def test_legacy_forbidden_failure_is_non_retryable(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            candidate_table = root / "candidate_papers.parquet"
            legacy_json = root / "paper_library.json"
            out_report = root / "backfill_report.json"
            pd.DataFrame(
                [
                    {
                        "doi": "10.1000/blocked",
                        "pdf_download_status": "download_failed",
                    }
                ]
            ).to_parquet(candidate_table, engine="pyarrow", index=False)
            legacy_json.write_text(
                json.dumps(
                    [
                        {
                            "study_doi": "10.1000/blocked",
                            "pdf_download_status": "download_failed",
                            "action_reason": "HTTPError: HTTP Error 403: Forbidden",
                        }
                    ]
                ),
                encoding="utf-8",
            )

            backfill_pdf_failure_categories(
                candidate_table=candidate_table,
                legacy_jsons=[legacy_json],
                audit_report_paths=[],
                report_json=out_report,
            )

            df = pd.read_parquet(candidate_table)
            self.assertEqual(df.loc[0, "pdf_download_failure_category"], "forbidden")
            self.assertFalse(bool(df.loc[0, "pdf_download_retry_recommended"]))


if __name__ == "__main__":
    unittest.main()
