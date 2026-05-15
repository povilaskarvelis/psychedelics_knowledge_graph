import csv
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from pipeline.ingest.summarize_boolean_module_runs import summarize_run


class SummarizeBooleanModuleRunsTest(unittest.TestCase):
    def test_summarizes_modules_and_new_dois(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            seed_dir = root / "seeds"
            run_dir = root / "run"
            seed_dir.mkdir()
            run_dir.mkdir()
            with (seed_dir / "disorder_boolean_openalex_seeds.csv").open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=[
                        "seed_id",
                        "dataset",
                        "provider_profile",
                        "module_id",
                        "module_type",
                        "query",
                        "compound",
                        "entity",
                        "compound_terms",
                        "entity_terms",
                        "evidence_terms",
                    ],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "seed_id": "s1",
                        "dataset": "disorder",
                        "provider_profile": "openalex",
                        "module_id": "depression",
                        "module_type": "primary_boolean",
                        "query": "psilocybin AND depression",
                    }
                )
            discovery = {
                "counts": {"seed_count": 1, "raw_rows": 2, "merged_rows": 2},
                "per_seed": [{"query": "psilocybin AND depression", "rows_retrieved": 2}],
                "rows": [
                    {"doi": "10.1/a", "queries": ["psilocybin AND depression"]},
                    {"doi": "10.1/b", "queries": ["psilocybin AND depression"]},
                ],
            }
            (run_dir / "disorder_discovery_report.json").write_text(json.dumps(discovery), encoding="utf-8")
            add_new = {
                "counts": {"new_dois": 1, "rediscovered_existing_dois": 1, "missing_or_invalid_dois": 0},
                "new_doi_samples": [{"doi": "10.1/b", "title": "New"}],
            }
            (run_dir / "disorder_add_new_dois_report.json").write_text(json.dumps(add_new), encoding="utf-8")
            (run_dir / "disorder_new_dois.txt").write_text("# header\n10.1/b,,,\n", encoding="utf-8")

            summary = summarize_run(seed_dir, run_dir, "disorder", "openalex")

        self.assertEqual(summary["new_dois"], 1)
        self.assertEqual(summary["modules"][0]["module_id"], "depression")
        self.assertEqual(summary["modules"][0]["merged_unique_dois_mentioned"], 2)
        self.assertEqual(summary["modules"][0]["new_unique_dois_mentioned"], 1)


if __name__ == "__main__":
    unittest.main()
