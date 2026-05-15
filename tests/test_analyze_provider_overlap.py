import csv
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from pipeline.ingest.analyze_provider_overlap import analyze_dataset


class AnalyzeProviderOverlapTest(unittest.TestCase):
    def write_seed_file(self, path: Path, query: str, module_id: str) -> None:
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=["seed_id", "dataset", "provider_profile", "module_id", "module_type", "query"],
            )
            writer.writeheader()
            writer.writerow(
                {
                    "seed_id": "s1",
                    "dataset": "disorder",
                    "provider_profile": "openalex",
                    "module_id": module_id,
                    "module_type": "primary_boolean",
                    "query": query,
                }
            )

    def write_run(self, run_dir: Path, dataset: str, query: str, rows: list[dict], new_dois: list[str]) -> None:
        run_dir.mkdir()
        discovery = {
            "rows": [
                {
                    "doi": row["doi"],
                    "title": row["title"],
                    "year": row.get("year", ""),
                    "authors": "",
                    "query": query,
                    "queries": [query],
                    "provider": row.get("provider", ""),
                }
                for row in rows
            ]
        }
        (run_dir / f"{dataset}_discovery_report.json").write_text(json.dumps(discovery), encoding="utf-8")
        (run_dir / f"{dataset}_new_dois.txt").write_text(
            "# header\n" + "".join(f"{doi},,,\n" for doi in new_dois),
            encoding="utf-8",
        )

    def test_analyzes_overlap_and_title_proxy(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self.write_seed_file(root / "disorder_boolean_openalex_seeds.csv", "psilocybin depression", "depression")
            self.write_seed_file(root / "disorder_boolean_pubmed_seeds.csv", "psilocybin[Title/Abstract]", "depression")
            self.write_run(
                root / "openalex_100",
                "disorder",
                "psilocybin depression",
                [
                    {"doi": "10.1/a", "title": "Psilocybin therapy for depression", "provider": "openalex"},
                    {"doi": "10.1/b", "title": "Biofeedback and self-control", "provider": "openalex"},
                ],
                ["10.1/a", "10.1/b"],
            )
            self.write_run(
                root / "pubmed_100",
                "disorder",
                "psilocybin[Title/Abstract]",
                [
                    {"doi": "10.1/a", "title": "Psilocybin therapy for depression", "provider": "pubmed"},
                    {"doi": "10.1/c", "title": "MDMA-assisted psychotherapy for PTSD", "provider": "pubmed"},
                ],
                ["10.1/a", "10.1/c"],
            )

            summary = analyze_dataset(root, "disorder", "openalex_100", "pubmed_100")

        self.assertEqual(summary["overlap"]["new_doi_overlap"], 1)
        self.assertEqual(summary["overlap"]["openalex_only_new_dois"], 1)
        self.assertEqual(summary["overlap"]["pubmed_only_new_dois"], 1)
        self.assertEqual(summary["exclusive_new_title_proxy"]["openalex_only"]["title_has_neither"], 1)
        self.assertEqual(summary["exclusive_new_title_proxy"]["pubmed_only"]["title_has_both"], 1)
        self.assertEqual(summary["module_new_overlap"][0]["module_id"], "depression")


if __name__ == "__main__":
    unittest.main()
