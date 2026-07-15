import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch
from tempfile import TemporaryDirectory

import pandas as pd

from pipeline.ingest.enrich_paper_metadata import (
    candidate_metadata_row,
    main,
    merged_output_rows,
    read_doi_file,
    read_table,
    write_table,
)


class EnrichPaperMetadataTest(unittest.TestCase):
    def test_candidate_metadata_row_uses_plain_doi_and_metadata_fields(self) -> None:
        row = candidate_metadata_row(
            {
                "doi": "https://doi.org/10.1000/example",
                "study_title": "Example paper",
                "abstract": "Example abstract.",
                "publication_type": "journal-article",
                "metadata_provider": "pubmed",
                "metadata_providers_queried": "pubmed|openalex",
                "metadata_missing_reason": "providers_returned_no_abstract",
                "best_pdf_url": "https://example.org/paper.pdf",
            }
        )

        self.assertEqual(row["doi"], "10.1000/example")
        self.assertEqual(row["study_title"], "Example paper")
        self.assertEqual(row["abstract"], "Example abstract.")
        self.assertEqual(row["publication_type"], "journal-article")
        self.assertEqual(row["metadata_provider"], "pubmed")
        self.assertEqual(row["metadata_providers_queried"], "pubmed|openalex")
        self.assertEqual(row["metadata_missing_reason"], "providers_returned_no_abstract")
        self.assertEqual(row["best_pdf_url"], "https://example.org/paper.pdf")

    def test_write_table_writes_parquet_only(self) -> None:
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "paper_metadata_enrichment.parquet"
            write_table(
                path,
                [
                    {
                        "doi": "10.1000/example",
                        "study_title": "Example paper",
                    }
                ],
            )

            rows = read_table(path)
            json_siblings = list(path.parent.glob("*.json"))

        self.assertEqual(rows[0]["doi"], "10.1000/example")
        self.assertEqual(rows[0]["study_title"], "Example paper")
        self.assertEqual(json_siblings, [])

    def test_read_doi_file_normalizes_plain_and_url_dois(self) -> None:
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "dois.txt"
            path.write_text(
                "# comment\nhttps://doi.org/10.1000/Example\n10.1000/other\n",
                encoding="utf-8",
            )

            dois = read_doi_file(path)

        self.assertEqual(dois, {"10.1000/example", "10.1000/other"})

    def test_checkpoint_rows_preserve_unprocessed_existing_rows(self) -> None:
        rows = merged_output_rows(
            {
                "10.1000/scoped": {
                    "doi": "10.1000/scoped",
                    "study_title": "Updated scoped paper",
                    "abstract": "New abstract.",
                }
            },
            {
                "10.1000/scoped": {
                    "doi": "10.1000/scoped",
                    "study_title": "Old scoped paper",
                    "abstract": "",
                },
                "10.1000/unprocessed": {
                    "doi": "10.1000/unprocessed",
                    "study_title": "Unprocessed existing paper",
                    "abstract": "Keep me.",
                },
            },
        )

        rows_by_doi = {row["doi"]: row for row in rows}
        self.assertEqual(set(rows_by_doi), {"10.1000/scoped", "10.1000/unprocessed"})
        self.assertEqual(rows_by_doi["10.1000/scoped"]["study_title"], "Updated scoped paper")
        self.assertEqual(rows_by_doi["10.1000/unprocessed"]["abstract"], "Keep me.")

    def test_doi_file_and_only_missing_abstract_limit_processed_rows(self) -> None:
        with TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            papers = tmp / "candidate_papers.parquet"
            output = tmp / "paper_metadata_enrichment.parquet"
            doi_file = tmp / "dois.txt"
            pd.DataFrame(
                [
                    {
                        "doi": "10.1000/complete",
                        "study_title": "Complete paper",
                        "abstract": "Already has an abstract.",
                    },
                    {
                        "doi": "10.1000/missing",
                        "study_title": "Missing abstract paper",
                        "abstract": "",
                    },
                    {
                        "doi": "10.1000/not-listed",
                        "study_title": "Not listed paper",
                        "abstract": "",
                    },
                ]
            ).to_parquet(papers, engine="pyarrow", index=False)
            write_table(
                output,
                [
                    {"doi": "10.1000/complete", "study_title": "Complete paper", "abstract": "Existing abstract."},
                    {"doi": "10.1000/missing", "study_title": "Missing abstract paper", "abstract": ""},
                    {"doi": "10.1000/not-listed", "study_title": "Not listed paper", "abstract": ""},
                ],
            )
            doi_file.write_text("10.1000/complete\n10.1000/missing\n", encoding="utf-8")

            argv = [
                "enrich_paper_metadata.py",
                "--papers-table",
                str(papers),
                "--output-table",
                str(output),
                "--metadata-provider-order",
                "none",
                "--doi-file",
                str(doi_file),
                "--only-missing-abstract",
                "--progress-every",
                "0",
            ]
            with patch("sys.argv", argv), redirect_stdout(StringIO()):
                exit_code = main()

            rows = {row["doi"]: row for row in read_table(output)}

        self.assertEqual(exit_code, 0)
        self.assertEqual(set(rows), {"10.1000/complete", "10.1000/missing", "10.1000/not-listed"})
        self.assertEqual(rows["10.1000/complete"]["abstract"], "Existing abstract.")
        self.assertEqual(rows["10.1000/missing"]["metadata_enrichment_status"], "existing")


if __name__ == "__main__":
    unittest.main()
