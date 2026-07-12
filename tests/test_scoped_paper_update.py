import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd

from pipeline.update import run_scoped_paper_update as updater


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def task(doi: str = "10.1000/update", suffix: str = "update") -> dict:
    return {
        "schema_version": "route_extraction_task_v2",
        "generated_at_utc": "2026-01-01T00:00:00+00:00",
        "task_id": f"task-{suffix}",
        "route_id": f"route-{suffix}",
        "input_fingerprint": (suffix[0] if suffix else "a") * 64,
        "study_doi": doi,
        "task_status": "ready_for_model",
        "paper_metadata": {
            "doi": doi,
            "study_title": f"Paper {suffix}",
            "abstract": "A public abstract.",
        },
        "route_context": {"domain_route": "clinical_outcome"},
        "extraction_contract": {
            "domain_route": "clinical_outcome",
            "output_family": "primary_evidence",
        },
        "text_source": {"mode": "abstract", "status": "ready_for_model"},
        "content": {"title": f"Paper {suffix}", "abstract": "A public abstract."},
    }


def successful_output(current_task: dict) -> dict:
    return {
        "task_id": current_task["task_id"],
        "route_id": current_task["route_id"],
        "input_fingerprint": current_task["input_fingerprint"],
        "study_doi": current_task["study_doi"],
        "status": "ok",
        "result": {
            "task_id": current_task["task_id"],
            "route_id": current_task["route_id"],
            "study_doi": current_task["study_doi"],
            "domain_route": "clinical_outcome",
            "text_depth": "abstract_only",
            "paper_type": "primary_study",
            "extraction_status": "extracted",
            "items": [
                {
                    "compound": "psilocybin",
                    "entity": "depressive symptoms",
                    "entity_type": "symptom_or_outcome",
                    "finding_summary": "Symptoms improved in the intervention group.",
                }
            ],
        },
    }


def old_output(doi: str, suffix: str) -> dict:
    return {
        "task_id": f"legacy-{suffix}",
        "route_id": f"route-{suffix}",
        "status": "ok",
        "result": {"study_doi": doi, "task_id": f"legacy-{suffix}", "route_id": f"route-{suffix}"},
    }


class ScopedPaperUpdateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.update_root = self.root / "updates"
        self.runs_root = self.root / "runs"
        self.scope_file = self.root / "scope.txt"
        self.scope_file.write_text("10.1000/update\n10.1000/excluded\n", encoding="utf-8")
        self.tasks_path = self.root / "tasks.jsonl"
        self.current_task = task()
        write_jsonl(self.tasks_path, [self.current_task])
        self.routes_path = self.root / "routes.parquet"
        pd.DataFrame([{"route_id": self.current_task["route_id"]}]).to_parquet(
            self.routes_path,
            index=False,
        )
        self.unaffected_output = old_output("10.1000/keep", "keep")
        self.base_outputs = self.root / "base_outputs.jsonl"
        write_jsonl(
            self.base_outputs,
            [
                self.unaffected_output,
                old_output("10.1000/update", "update-old"),
                old_output("10.1000/excluded", "excluded-old"),
            ],
        )
        self.unaffected_evidence = {
            "study_doi": "10.1000/keep",
            "compound": "ketamine",
            "graph_entity_label": "depression",
        }
        self.base_evidence = self.root / "base_evidence.json"
        self.base_evidence.write_text(
            json.dumps(
                [
                    self.unaffected_evidence,
                    {"study_doi": "10.1000/update", "compound": "old"},
                    {"study_doi": "10.1000/excluded", "compound": "old"},
                ]
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def prepare_args(self, **overrides: object) -> SimpleNamespace:
        values = {
            "update_id": "test_update",
            "doi_file": str(self.scope_file),
            "update_dir": "",
            "tasks_jsonl": str(self.tasks_path),
            "route_table": str(self.routes_path),
            "base_outputs": str(self.base_outputs),
            "base_evidence": str(self.base_evidence),
            "refresh_derived": False,
            "only_task_group": "",
            "include_no_runnable": False,
            "overwrite": False,
        }
        values.update(overrides)
        return SimpleNamespace(**values)

    def finalize_args(self, patch_output: Path | None, **overrides: object) -> SimpleNamespace:
        values = {
            "update_id": "test_update",
            "update_dir": "",
            "patch_outputs": [str(patch_output)] if patch_output else [],
            "overwrite": False,
        }
        values.update(overrides)
        return SimpleNamespace(**values)

    def test_prepare_identifies_replacement_and_tombstone_scope(self) -> None:
        with patch.object(updater, "UPDATE_ROOT", self.update_root):
            updater.prepare(self.prepare_args())

        manifest = json.loads(
            (self.update_root / "test_update" / "update_manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["scope"]["doi_count"], 2)
        self.assertEqual(manifest["current_scope"]["ready_tasks"], 1)
        self.assertEqual(manifest["current_scope"]["no_current_task_dois"], 1)
        self.assertEqual(manifest["base"]["scope_output_rows_to_replace"], 2)
        self.assertEqual(manifest["base"]["scope_evidence_rows_to_replace"], 2)
        no_task = (self.update_root / "test_update" / "no_current_task_dois.txt").read_text()
        self.assertEqual(no_task.strip(), "10.1000/excluded")
        status_rows = pd.read_csv(self.update_root / "test_update" / "scope_status.csv").set_index("doi")
        self.assertEqual(status_rows.loc["10.1000/update", "disposition"], "replace_with_current_extraction")
        self.assertEqual(status_rows.loc["10.1000/excluded", "disposition"], "remove_without_replacement")

    def test_prepare_can_select_primary_plus_deletion_only_scope(self) -> None:
        review_task = task("10.1000/review", "review")
        review_task["extraction_contract"]["output_family"] = "review_coverage"
        write_jsonl(self.tasks_path, [self.current_task, review_task])
        self.scope_file.write_text(
            "10.1000/update\n10.1000/review\n10.1000/excluded\n",
            encoding="utf-8",
        )
        with patch.object(updater, "UPDATE_ROOT", self.update_root):
            updater.prepare(
                self.prepare_args(only_task_group="primary", include_no_runnable=True)
            )

        manifest = json.loads(
            (self.update_root / "test_update" / "update_manifest.json").read_text(encoding="utf-8")
        )
        scope = set(
            (self.update_root / "test_update" / "scope_dois.txt").read_text(encoding="utf-8").splitlines()
        )
        self.assertEqual(scope, {"10.1000/update", "10.1000/excluded"})
        self.assertEqual(manifest["scope"]["requested_doi_count"], 3)
        self.assertEqual(manifest["scope"]["only_task_group"], "primary")

    def test_finalize_replaces_updated_doi_removes_excluded_and_preserves_other_rows(self) -> None:
        patch_output = self.root / "patch.jsonl"
        write_jsonl(patch_output, [successful_output(self.current_task)])
        with (
            patch.object(updater, "UPDATE_ROOT", self.update_root),
            patch.object(updater, "ROUTED_RUNS_DIR", self.runs_root),
        ):
            updater.prepare(self.prepare_args())
            updater.finalize(self.finalize_args(patch_output))

        candidate_outputs = list(updater.read_jsonl(self.runs_root / "test_update" / "route_extraction_outputs.jsonl"))
        self.assertEqual(len(candidate_outputs), 2)
        self.assertEqual(candidate_outputs[0], self.unaffected_output)
        self.assertEqual(candidate_outputs[1]["task_id"], self.current_task["task_id"])
        self.assertNotIn("10.1000/excluded", {updater.doi_for_output(row) for row in candidate_outputs})

        candidate_evidence = json.loads(
            (self.runs_root / "test_update" / "routed_evidence_rows.json").read_text(encoding="utf-8")
        )
        self.assertEqual(candidate_evidence[0], self.unaffected_evidence)
        self.assertEqual({row["study_doi"] for row in candidate_evidence}, {"10.1000/keep", "10.1000/update"})
        self.assertEqual(candidate_evidence[1]["task_id"], self.current_task["task_id"])

    def test_finalize_refuses_incomplete_patch(self) -> None:
        patch_output = self.root / "patch.jsonl"
        write_jsonl(
            patch_output,
            [
                {
                    "task_id": self.current_task["task_id"],
                    "route_id": self.current_task["route_id"],
                    "status": "error",
                }
            ],
        )
        with (
            patch.object(updater, "UPDATE_ROOT", self.update_root),
            patch.object(updater, "ROUTED_RUNS_DIR", self.runs_root),
        ):
            updater.prepare(self.prepare_args())
            with self.assertRaisesRegex(RuntimeError, "Patch is incomplete"):
                updater.finalize(self.finalize_args(patch_output))
        self.assertFalse((self.runs_root / "test_update").exists())

    def test_exclusion_only_update_needs_no_patch_output(self) -> None:
        self.scope_file.write_text("10.1000/excluded\n", encoding="utf-8")
        write_jsonl(self.tasks_path, [])
        with (
            patch.object(updater, "UPDATE_ROOT", self.update_root),
            patch.object(updater, "ROUTED_RUNS_DIR", self.runs_root),
        ):
            updater.prepare(self.prepare_args())
            updater.finalize(self.finalize_args(None))

        candidate_outputs = list(
            updater.read_jsonl(self.runs_root / "test_update" / "route_extraction_outputs.jsonl")
        )
        candidate_evidence = json.loads(
            (self.runs_root / "test_update" / "routed_evidence_rows.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            {updater.doi_for_output(row) for row in candidate_outputs},
            {"10.1000/keep", "10.1000/update"},
        )
        self.assertEqual(
            {row["study_doi"] for row in candidate_evidence},
            {"10.1000/keep", "10.1000/update"},
        )

    def test_finalize_refuses_changed_base_after_prepare(self) -> None:
        patch_output = self.root / "patch.jsonl"
        write_jsonl(patch_output, [successful_output(self.current_task)])
        with (
            patch.object(updater, "UPDATE_ROOT", self.update_root),
            patch.object(updater, "ROUTED_RUNS_DIR", self.runs_root),
        ):
            updater.prepare(self.prepare_args())
            with self.base_outputs.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(old_output("10.1000/new", "new")) + "\n")
            with self.assertRaisesRegex(RuntimeError, "changed after prepare"):
                updater.finalize(self.finalize_args(patch_output))

    def test_prepare_refuses_duplicate_current_task_ids(self) -> None:
        write_jsonl(self.tasks_path, [self.current_task, self.current_task])
        with patch.object(updater, "UPDATE_ROOT", self.update_root):
            with self.assertRaisesRegex(ValueError, "Duplicate current task_id"):
                updater.prepare(self.prepare_args())


if __name__ == "__main__":
    unittest.main()
