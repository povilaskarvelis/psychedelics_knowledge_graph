import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from pipeline.extract.run_routed_extraction_batch import (
    attempted_task_keys,
    select_next_tasks,
    task_matches_filters,
    write_jsonl,
)


def make_task(route_id: str, *, domain: str = "clinical_outcome", text_depth: str = "full_text_seen") -> dict:
    return {
        "schema_version": "route_extraction_task_v1",
        "task_id": route_id,
        "route_id": route_id,
        "study_doi": f"10.1000/{route_id}",
        "task_status": "ready_for_model",
        "paper_metadata": {
            "doi": f"10.1000/{route_id}",
            "study_title": "A clinical outcome paper",
            "abstract": "A trial reports clinical outcomes.",
        },
        "route_context": {
            "route_id": route_id,
            "source_type": "primary",
            "domain_route": domain,
            "prompt_profile": "primary_clinical",
            "schema_profile": "primary_evidence_schema",
        },
        "extraction_contract": {
            "route_id": route_id,
            "prompt_profile": "primary_clinical",
            "schema_profile": "primary_evidence_schema",
            "domain_route": domain,
            "source_type": "primary",
            "access_level": text_depth,
        },
        "text_source": {
            "access_level": text_depth,
        },
        "content": {
            "title": "A clinical outcome paper",
            "abstract": "A trial reports clinical outcomes.",
        },
    }


def make_args(**overrides: object) -> SimpleNamespace:
    args = {
        "include_not_ready": False,
        "include_scaffold_profiles": False,
        "prompt_profile": [],
        "schema_profile": [],
        "domain_route": [],
        "text_depth": [],
        "source_type": [],
        "route_id": [],
        "doi": [],
        "shuffle": False,
        "seed": 1,
        "batch_size": 100,
    }
    args.update(overrides)
    return SimpleNamespace(**args)


class RunRoutedExtractionBatchTest(unittest.TestCase):
    def test_task_matches_supported_ready_profile(self) -> None:
        self.assertTrue(task_matches_filters(make_task("route-1"), make_args()))

    def test_task_filters_by_domain_and_text_depth(self) -> None:
        article_task = make_task("route-1", domain="clinical_outcome", text_depth="full_text_seen")
        abstract_task = make_task("route-2", domain="brain_system", text_depth="abstract_only")

        args = make_args(domain_route=["clinical_outcome"], text_depth=["article_text"])

        self.assertTrue(task_matches_filters(article_task, args))
        self.assertFalse(task_matches_filters(abstract_task, args))

    def test_attempted_task_keys_skip_prior_outputs_and_raw_errors_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            write_jsonl(run_dir / "route_extraction_outputs.jsonl", [{"route_id": "route-done", "status": "ok"}])
            write_jsonl(run_dir / "route_extraction_raw.jsonl", [{"route_id": "route-error", "status": "error"}])

            self.assertEqual(attempted_task_keys(run_dir), {"route-done", "route-error"})
            self.assertEqual(attempted_task_keys(run_dir, retry_errors=True), {"route-done"})

    def test_select_next_tasks_omits_attempted_routes(self) -> None:
        tasks = [make_task("route-1"), make_task("route-2"), make_task("route-3")]

        selected = select_next_tasks(tasks, {"route-1"}, make_args(batch_size=2))

        self.assertEqual([task["route_id"] for _, task in selected], ["route-2", "route-3"])

    def test_write_jsonl_writes_json_lines(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "rows.jsonl"
            write_jsonl(path, [{"a": 1}, {"b": 2}])

            rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

        self.assertEqual(rows, [{"a": 1}, {"b": 2}])


if __name__ == "__main__":
    unittest.main()
