import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from pipeline.ingest.recall_audit import build_gate_report, read_known_study_manifest


class RecallGateTest(unittest.TestCase):
    def test_gate_fails_when_threshold_is_missed(self) -> None:
        gate = build_gate_report(
            known_total=10,
            coverage_percent={
                "discovered": 90.0,
                "triage": 0.0,
                "paper_library": 0.0,
                "with_local_pdf": 0.0,
                "curated": 0.0,
            },
            thresholds={
                "discovered": 95.0,
                "triage": 0.0,
                "paper_library": 0.0,
                "with_local_pdf": 0.0,
                "curated": 0.0,
            },
            fail_under_threshold=True,
        )
        self.assertEqual(gate["status"], "failed")
        self.assertEqual(gate["failed_stages"][0]["stage"], "discovered")

    def test_gate_passes_when_enabled_threshold_is_met(self) -> None:
        gate = build_gate_report(
            known_total=10,
            coverage_percent={
                "discovered": 100.0,
                "triage": 0.0,
                "paper_library": 0.0,
                "with_local_pdf": 0.0,
                "curated": 0.0,
            },
            thresholds={
                "discovered": 95.0,
                "triage": 0.0,
                "paper_library": 0.0,
                "with_local_pdf": 0.0,
                "curated": 0.0,
            },
            fail_under_threshold=True,
        )
        self.assertEqual(gate["status"], "passed")
        self.assertFalse(gate["failed"])

    def test_enabled_gate_fails_empty_known_study_set(self) -> None:
        gate = build_gate_report(
            known_total=0,
            coverage_percent={
                "discovered": 0.0,
                "triage": 0.0,
                "paper_library": 0.0,
                "with_local_pdf": 0.0,
                "curated": 0.0,
            },
            thresholds={
                "discovered": 95.0,
                "triage": 0.0,
                "paper_library": 0.0,
                "with_local_pdf": 0.0,
                "curated": 0.0,
            },
            fail_under_threshold=True,
        )
        self.assertEqual(gate["status"], "failed")
        self.assertEqual(gate["failed_stages"][0]["reason"], "known_doi_file_empty")

    def test_reads_dataset_dois_from_known_study_manifest(self) -> None:
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "benchmark_manifest.json"
            path.write_text(
                """
{
  "entries": [
    {"doi": "https://doi.org/10.example/mech", "dataset": "mechanistic"},
    {"doi": "10.example/disorder", "dataset": "disorder"},
    {"doi": "10.example/mech", "dataset": "mechanistic"}
  ]
}
""".strip()
                + "\n",
                encoding="utf-8",
            )

            self.assertEqual(read_known_study_manifest(path, "mechanistic"), ["10.example/mech"])


if __name__ == "__main__":
    unittest.main()
