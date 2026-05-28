import json
import tempfile
import unittest
from pathlib import Path

from pipeline.extract.extraction_v1_utils import read_jsonl
from pipeline.extract.promote_extraction_rerun import filter_inputs_for_successful_outputs, merge_rows, promote


def row(dataset: str, doi: str, marker: str) -> dict:
    return {"dataset": dataset, "study_doi": doi, "marker": marker}


class PromoteExtractionRerunTests(unittest.TestCase):
    def test_merge_replaces_by_dataset_and_normalized_doi(self) -> None:
        merged, summary = merge_rows(
            [
                row("mechanistic", "https://doi.org/10.1/a", "old-a"),
                row("mechanistic", "10.1/b", "old-b"),
                row("disorder", "10.1/b", "old-disorder-b"),
            ],
            [
                row("mechanistic", "10.1/B", "new-b"),
                row("mechanistic", "10.1/c", "new-c"),
            ],
        )

        self.assertEqual([item["marker"] for item in merged], ["old-a", "new-b", "old-disorder-b", "new-c"])
        self.assertEqual(summary["replaced_rows"], 1)
        self.assertEqual(summary["appended_rows"], 1)

    def test_filter_inputs_uses_only_successful_output_keys(self) -> None:
        filtered, summary = filter_inputs_for_successful_outputs(
            [
                row("mechanistic", "10.1/a", "input-a"),
                row("mechanistic", "10.1/b", "input-b"),
            ],
            [row("mechanistic", "10.1/b", "ok-b")],
        )

        self.assertEqual([item["marker"] for item in filtered], ["input-b"])
        self.assertEqual(summary["matching_input_rows"], 1)
        self.assertEqual(summary["missing_input_keys"], [])

    def test_promote_apply_backs_up_and_writes_merged_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            active_outputs = root / "active_outputs.jsonl"
            active_inputs = root / "active_inputs.jsonl"
            rerun_outputs = root / "rerun_outputs.jsonl"
            rerun_inputs = root / "rerun_inputs.jsonl"
            report_json = root / "report.json"
            backup_dir = root / "backups"

            active_outputs.write_text(json.dumps(row("mechanistic", "10.1/a", "old-a")) + "\n", encoding="utf-8")
            active_inputs.write_text(json.dumps(row("mechanistic", "10.1/a", "old-input-a")) + "\n", encoding="utf-8")
            rerun_outputs.write_text(json.dumps(row("mechanistic", "10.1/a", "new-a")) + "\n", encoding="utf-8")
            rerun_inputs.write_text(
                json.dumps(row("mechanistic", "10.1/a", "new-input-a"))
                + "\n"
                + json.dumps(row("mechanistic", "10.1/failed", "failed-input"))
                + "\n",
                encoding="utf-8",
            )

            report = promote(
                active_output_jsonl=active_outputs,
                active_pilot_input_jsonl=active_inputs,
                rerun_output_jsonl=rerun_outputs,
                rerun_pilot_input_jsonl=rerun_inputs,
                report_json=report_json,
                backup_dir=backup_dir,
                apply=True,
            )

            self.assertEqual(read_jsonl(active_outputs)[0]["marker"], "new-a")
            self.assertEqual(read_jsonl(active_inputs)[0]["marker"], "new-input-a")
            self.assertEqual(report["pilot_input_filter"]["matching_input_rows"], 1)
            self.assertTrue(list(backup_dir.glob("*.bak")))


if __name__ == "__main__":
    unittest.main()
