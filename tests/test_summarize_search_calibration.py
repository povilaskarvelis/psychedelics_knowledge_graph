import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from pipeline.ingest.summarize_search_calibration import summarize_dataset


class SummarizeSearchCalibrationTest(unittest.TestCase):
    def test_summarizes_family_level_discovery_and_new_dois(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            protocol_dir = root / "protocol"
            calibration_dir = protocol_dir / "calibration" / "openalex"
            protocol_dir.mkdir(parents=True)
            (protocol_dir / "calibration").mkdir(parents=True)
            calibration_dir.mkdir(parents=True)

            full_header = "seed_id,dataset,family,query,compound,entity,entity_type,template\n"
            (protocol_dir / "mechanistic_seeds.csv").write_text(
                full_header
                + "s1,mechanistic,class_level,psychedelic binding,,,target,t\n"
                + "s2,mechanistic,pair_core,LSD 5-HT2A binding,LSD,5-HT2A,target,t\n",
                encoding="utf-8",
            )
            (protocol_dir / "calibration" / "mechanistic_calibration_seeds.csv").write_text(
                full_header
                + "s1,mechanistic,class_level,psychedelic binding,,,target,t\n"
                + "s2,mechanistic,pair_core,LSD 5-HT2A binding,LSD,5-HT2A,target,t\n",
                encoding="utf-8",
            )
            discovery = {
                "provider": "openalex",
                "settings": {"max_results_per_seed": 10},
                "counts": {"seed_count": 2, "raw_rows": 3, "merged_rows": 2, "provider_errors": 0},
                "per_seed": [
                    {"query": "psychedelic binding", "compound": "", "entity": "", "rows_retrieved": 1},
                    {"query": "LSD 5-HT2A binding", "compound": "LSD", "entity": "5-HT2A", "rows_retrieved": 2},
                ],
                "rows": [
                    {"doi": "10.1/a", "queries": ["psychedelic binding"]},
                    {"doi": "10.1/b", "queries": ["LSD 5-HT2A binding"]},
                ],
            }
            (calibration_dir / "mechanistic_discovery_report.json").write_text(
                json.dumps(discovery),
                encoding="utf-8",
            )
            add_new = {
                "counts": {"new_dois": 1, "rediscovered_existing_dois": 1},
                "new_doi_samples": [{"doi": "10.1/b", "title": "New paper"}],
            }
            (calibration_dir / "mechanistic_add_new_dois_report.json").write_text(
                json.dumps(add_new),
                encoding="utf-8",
            )
            (calibration_dir / "mechanistic_new_dois.txt").write_text(
                "# header\n10.1/b,LSD,5-HT2A,New paper,2024,\n",
                encoding="utf-8",
            )

            summary = summarize_dataset(
                dataset="mechanistic",
                protocol_dir=protocol_dir,
                calibration_dir=calibration_dir,
            )

        self.assertEqual(summary["raw_rows"], 3)
        self.assertEqual(summary["new_dois"], 1)
        self.assertEqual(summary["family_stats"]["pair_core"]["new_unique_dois_mentioned"], 1)
        self.assertEqual(summary["family_stats"]["class_level"]["merged_unique_dois_mentioned"], 1)


if __name__ == "__main__":
    unittest.main()
