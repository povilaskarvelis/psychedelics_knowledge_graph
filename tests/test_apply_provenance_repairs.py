import csv
import json
import tempfile
import unittest
from pathlib import Path

from pipeline.fulltext.apply_provenance_repairs import (
    apply_repairs,
    export_review_template,
    load_decisions,
    validate_candidate,
)


def curated_row(locator: str = "Abstract snippet: old finding") -> dict:
    return {
        "study_doi": "10.1000/example",
        "compound": "Ketamine",
        "disorder": "Major depressive disorder",
        "access_level": "full_text_seen",
        "evidence_location": "abstract",
        "evidence_locator": locator,
        "notes": "Existing note",
    }


def report_row(action: str = "propose_locator_repair") -> dict:
    return {
        "row_index": 1,
        "study_doi": "10.1000/example",
        "compound": "Ketamine",
        "entity": "Major depressive disorder",
        "action": action,
        "current_evidence_location": "abstract",
        "current_evidence_locator": "Abstract snippet: old finding",
        "proposed_evidence_location": "text",
        "proposed_evidence_locator": "Full text section `Results` snippet: Ketamine improved depression ratings.",
        "reason": "heading is evidence-bearing",
        "score": 12,
    }


class ApplyProvenanceRepairsTest(unittest.TestCase):
    def test_load_decisions_accepts_only_explicit_accepted_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "decisions.csv"
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["decision", "row_index", "study_doi", "review_notes"])
                writer.writeheader()
                writer.writerow(
                    {
                        "decision": "accepted",
                        "row_index": "1",
                        "study_doi": "10.1000/example",
                        "review_notes": "looks good",
                    }
                )
                writer.writerow({"decision": "reject", "row_index": "2", "study_doi": "10.1000/skip"})
                writer.writerow({"decision": "", "row_index": "3", "study_doi": "10.1000/blank"})

            decisions = load_decisions(path)

        self.assertEqual(list(decisions), [(1, "10.1000/example")])
        self.assertEqual(decisions[(1, "10.1000/example")]["review_notes"], "looks good")

    def test_validate_candidate_requires_current_locator_match(self) -> None:
        ok, reason = validate_candidate(report_row(), curated_row(locator="Abstract snippet: changed"), 1)

        self.assertFalse(ok)
        self.assertIn("no longer matches", reason)

    def test_validate_candidate_rejects_non_proposed_rows(self) -> None:
        ok, reason = validate_candidate(report_row(action="needs_manual_review"), curated_row(), 1)

        self.assertFalse(ok)
        self.assertIn("not a proposed", reason)

    def test_apply_repairs_dry_run_does_not_mutate_curated_rows(self) -> None:
        rows = [curated_row()]
        report = {"rows": [report_row()]}
        accepted = {(1, "10.1000/example"): {"review_notes": "approved by curator"}}

        summary = apply_repairs(rows, report, accepted, mutate=False)

        self.assertEqual(summary["changes_ready"], 1)
        self.assertEqual(rows[0]["evidence_location"], "abstract")
        self.assertEqual(rows[0]["evidence_locator"], "Abstract snippet: old finding")
        self.assertEqual(summary["changes"][0]["reviewer_note"], "approved by curator")

    def test_apply_repairs_apply_mutates_only_accepted_rows(self) -> None:
        rows = [curated_row(), {**curated_row(), "study_doi": "10.1000/other"}]
        report = {"rows": [report_row()]}
        accepted = {(1, "10.1000/example"): {}}

        summary = apply_repairs(rows, report, accepted, mutate=True)

        self.assertEqual(summary["changes_ready"], 1)
        self.assertEqual(rows[0]["evidence_location"], "text")
        self.assertEqual(
            rows[0]["evidence_locator"],
            "Full text section `Results` snippet: Ketamine improved depression ratings.",
        )
        self.assertEqual(rows[1]["evidence_location"], "abstract")
        self.assertIn("Provenance locator repaired", rows[0]["notes"])

    def test_apply_repairs_skips_accepted_row_missing_from_report(self) -> None:
        summary = apply_repairs([curated_row()], {"rows": []}, {(1, "10.1000/example"): {}}, mutate=True)

        self.assertEqual(summary["changes_ready"], 0)
        self.assertEqual(summary["skipped"], 1)
        self.assertIn("not found", summary["skipped_rows"][0]["reason"])

    def test_export_review_template_only_exports_repair_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "review.csv"
            count = export_review_template(
                {"rows": [report_row(), report_row(action="needs_manual_review")]},
                path,
            )
            rows = list(csv.DictReader(path.open("r", encoding="utf-8", newline="")))

        self.assertEqual(count, 1)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["decision"], "")
        self.assertEqual(rows[0]["row_index"], "1")

    def test_json_decisions_object_with_rows_is_supported(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "decisions.json"
            path.write_text(
                json.dumps({"rows": [{"decision": "yes", "row_index": 1, "study_doi": "10.1000/example"}]}),
                encoding="utf-8",
            )

            decisions = load_decisions(path)

        self.assertEqual(list(decisions), [(1, "10.1000/example")])


if __name__ == "__main__":
    unittest.main()
