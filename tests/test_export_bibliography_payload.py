import json
import tempfile
import unittest
from pathlib import Path

from pipeline.publish.export_bibliography_payload import export_dataset, papers_from_reports


class ExportBibliographyPayloadTest(unittest.TestCase):
    def test_exports_relevant_screened_papers_with_citation_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            report = root / "screening.json"
            report.write_text(
                json.dumps(
                    {
                        "rows": [
                            {
                                "input_row": {
                                    "study_doi": "https://doi.org/10.1000/relevant",
                                    "study_title": "A <i>Relevant</i> Study",
                                    "study_year": "2024",
                                    "authors": "Ada Lovelace; Grace Hopper; Katherine Johnson; Dorothy Vaughan",
                                    "study_journal": "Journal of Careful Tests",
                                    "publication_type": "journal-article",
                                    "publication_date": "2024-03-05",
                                    "publisher": "Example Press",
                                },
                                "flat": {
                                    "status": "ok",
                                    "llm_relevance": "relevant",
                                    "llm_supported_contexts": "Psilocybin->Major depressive disorder",
                                },
                                "verification": {
                                    "quote_verified": True,
                                    "verified_supported_contexts": [
                                        {
                                            "compound": "Psilocybin",
                                            "entity": "Major depressive disorder",
                                        }
                                    ],
                                },
                            },
                            {
                                "input_row": {
                                    "study_doi": "10.1000/irrelevant",
                                    "study_title": "Out of scope",
                                },
                                "flat": {"status": "ok", "llm_relevance": "irrelevant"},
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )

            papers = papers_from_reports("disorder", [report])

            self.assertEqual(len(papers), 1)
            paper = papers[0]
            self.assertEqual(paper["doi"], "10.1000/relevant")
            self.assertEqual(paper["title"], "A Relevant Study")
            self.assertEqual(paper["year"], 2024)
            self.assertEqual(paper["journal"], "Journal of Careful Tests")
            self.assertEqual(paper["publication_type"], "journal-article")
            self.assertEqual(paper["contexts"], [{"compound": "Psilocybin", "entity": "Major depressive disorder"}])

    def test_export_dataset_writes_stable_payload_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            report = root / "screening.json"
            out_dir = root / "out"
            report.write_text(
                json.dumps(
                    {
                        "rows": [
                            {
                                "input_row": {
                                    "study_doi": "10.1000/example",
                                    "study_title": "Example Study",
                                    "study_year": "2023",
                                    "study_journal": "Example Journal",
                                },
                                "adjudication": {"relevance": "relevant"},
                                "flat": {"status": "ok"},
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            summary = export_dataset("mechanistic", out_dir=out_dir, report_paths=[report])
            payload = json.loads((out_dir / "bibliography_payload_mechanistic.json").read_text())

            self.assertEqual(summary["paper_count"], 1)
            self.assertEqual(payload["source"], "abstract_screening_relevant")
            self.assertEqual(payload["paper_count"], 1)
            self.assertEqual(payload["papers"][0]["journal"], "Example Journal")


if __name__ == "__main__":
    unittest.main()
