import json
import tempfile
import unittest
import pytest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from pipeline.extract.io_utils import read_jsonl
from pipeline.extract.run_route_extraction_batch_api import (
    append_unique_jsonl,
    materialize_run_projection_from_batch_files,
    request_for_task,
    reconciled_batch_results,
    reserved_manifest_task_keys,
    selected_for_batch,
    submit_batch,
)


@pytest.mark.parametrize("domain,prompt_profile,optional_field", [
    ("cognitive_behavioral", "primary_cognitive_behavioral", "construct_family"),
    ("molecular_pathway_readout", "primary_molecular_pathway", "molecular_effect_category"),
    ("real_world_public_health", "primary_real_world_public_health", "real_world_use_context"),
])
@pytest.mark.parametrize("required_null", [False, True])
def test_batch_parser_restores_referenced_optional_nulls_without_accepting_required_nulls(
    tmp_path, monkeypatch, domain, prompt_profile, optional_field, required_null,
):
    from pipeline import llm
    from pipeline.extract import run_route_extraction_batch_api as runner
    from pipeline.extract.route_extraction_profiles import (
        profile_for_task, load_schema_for_profile, schema_for_native,
    )

    task = {"task_id": "task-one", "route_id": "route-one", "study_doi": "10.example/one",
            "extraction_contract": {"prompt_profile": prompt_profile,
                "schema_profile": "primary_evidence_schema", "domain_route": domain}}
    profile = profile_for_task(task)
    schema = schema_for_native(load_schema_for_profile(profile, domain))
    item_schema = schema["properties"]["items"]["items"]
    # Required evidence stays present; only an API-added optional null is absent.
    item = {key: "not_reported" for key in item_schema["required"]}
    for key in item_schema["required"]:
        prop = item_schema["properties"][key]
        if prop.get("enum"):
            item[key] = prop["enum"][0]
    item[optional_field] = None
    required_key = item_schema["required"][0]
    if required_null:
        item[required_key] = None
    result = {"schema_version": profile.output_schema_version, "task_id": "task-one",
              "route_id": "route-one", "study_doi": task["study_doi"],
              "domain_route": domain, "paper_type": "primary_study", "text_depth": "abstract_only",
              "extraction_status": "extracted", "items": [item], "warnings": []}
    paths = {k: tmp_path / (k + ".jsonl") for k in ["manifest_json", "results_jsonl",
             "batch_raw_jsonl", "batch_outputs_jsonl", "parse_report_json"]}
    paths["manifest_json"].write_text(json.dumps({"records": [{"key": "request-one",
        "task_id": "task-one", "route_id": "route-one", "study_doi": task["study_doi"]}]}))
    response = {"status": "completed", "model": "gpt-6-luna",
                "usage": {"input_tokens": 10, "output_tokens": 10},
                "output_text": json.dumps(result)}
    paths["results_jsonl"].write_text(json.dumps({"custom_id": "request-one",
        "response": {"status_code": 200, "body": response}}) + "\n")
    tasks_path = tmp_path / "tasks.jsonl"
    tasks_path.write_text(json.dumps(task) + "\n")
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    monkeypatch.setattr(runner, "batch_paths", lambda args: paths)
    monkeypatch.setattr(runner, "appendable_output_paths", lambda run_id: {
        "run_dir": run_dir, "raw_jsonl": run_dir / "raw.jsonl", "outputs_jsonl": run_dir / "out.jsonl"})
    monkeypatch.setattr(runner, "materialize_run_projection_from_batch_files", lambda path: {})
    report = runner.parse_batch_results(SimpleNamespace(input_jsonl=tasks_path, env_file=tmp_path / "absent.env",
        run_id="test", batch_id="batch_001", skip_rebuild=True, model="gpt-6-luna"))
    expected = "schema_error" if required_null else "ok"
    assert report["summary"]["status_counts"] == {expected: 1}
    parsed = read_jsonl(paths["batch_outputs_jsonl"])[0]["result"]["items"][0]
    assert optional_field not in parsed
    if required_null:
        assert parsed[required_key] is None
    else:
        assert parsed[required_key] == item[required_key]
    assert json.loads(llm.response_text(response))["items"][0][optional_field] is None


@pytest.mark.parametrize("rows", [[], [{"key": "a"}],
    [{"key": "a"}, {"key": "a"}, {"key": "b"}],
    [{"key": "a"}, {"key": "b"}, {"key": "unknown"}]])
def test_batch_result_reconciliation_rejects_incomplete_or_ambiguous_results(tmp_path, rows):
    path = tmp_path / "results.jsonl"
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    with pytest.raises(ValueError, match="reconciliation failed"):
        reconciled_batch_results({"records": [{"key": "a"}, {"key": "b"}]}, path)


def test_batch_result_reconciliation_requires_file_and_accepts_keyed_errors(tmp_path):
    path = tmp_path / "results.jsonl"
    manifest = {"records": [{"key": "a"}, {"key": "b"}]}
    with pytest.raises(FileNotFoundError):
        reconciled_batch_results(manifest, path)
    rows = [{"key": "b", "error": {"message": "provider failure"}},
            {"key": "a", "response": {}}]
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    assert reconciled_batch_results(manifest, path) == rows


class RouteExtractionBatchApiTest(unittest.TestCase):
    def test_reparse_materializes_latest_batch_projection_and_drops_rejected_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            batch_dir = run_dir / "async_batches"
            batch_dir.mkdir()
            (run_dir / "route_extraction_raw.jsonl").write_text(
                "\n".join(
                    [
                        json.dumps({"route_id": "sync-route", "status": "ok"}),
                        json.dumps({"route_id": "batch-route", "status": "ok"}),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            (run_dir / "route_extraction_outputs.jsonl").write_text(
                "\n".join(
                    [
                        json.dumps({"route_id": "sync-route", "status": "ok"}),
                        json.dumps({"route_id": "batch-route", "status": "ok"}),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            (batch_dir / "batch_001_raw.jsonl").write_text(
                json.dumps({"route_id": "batch-route", "status": "quality_error"}) + "\n",
                encoding="utf-8",
            )
            (batch_dir / "batch_001_outputs.jsonl").write_text("", encoding="utf-8")

            report = materialize_run_projection_from_batch_files(run_dir)
            raw_rows = read_jsonl(run_dir / "route_extraction_raw.jsonl")
            output_rows = read_jsonl(run_dir / "route_extraction_outputs.jsonl")

        self.assertEqual(report["materialized_raw_rows"], 2)
        self.assertEqual(report["materialized_output_rows"], 1)
        self.assertEqual(
            {row["route_id"]: row["status"] for row in raw_rows},
            {"sync-route": "ok", "batch-route": "quality_error"},
        )
        self.assertEqual([row["route_id"] for row in output_rows], ["sync-route"])

    def test_later_retry_batch_replaces_earlier_error_projection(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            batch_dir = run_dir / "async_batches"
            batch_dir.mkdir()
            (batch_dir / "batch_001_raw.jsonl").write_text(
                json.dumps({"route_id": "retry-route", "status": "quality_error"}) + "\n",
                encoding="utf-8",
            )
            (batch_dir / "batch_001_outputs.jsonl").write_text("", encoding="utf-8")
            (batch_dir / "batch_002_raw.jsonl").write_text(
                json.dumps({"route_id": "retry-route", "status": "ok"}) + "\n",
                encoding="utf-8",
            )
            (batch_dir / "batch_002_outputs.jsonl").write_text(
                json.dumps({"route_id": "retry-route", "status": "ok"}) + "\n",
                encoding="utf-8",
            )

            report = materialize_run_projection_from_batch_files(run_dir)
            raw_rows = read_jsonl(run_dir / "route_extraction_raw.jsonl")
            output_rows = read_jsonl(run_dir / "route_extraction_outputs.jsonl")

        self.assertEqual(report["owned_async_routes"], 1)
        self.assertEqual([row["status"] for row in raw_rows], ["ok"])
        self.assertEqual([row["status"] for row in output_rows], ["ok"])

    def test_prepared_manifests_reserve_routes_for_later_batches(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            batch_dir = Path(tmpdir)
            (batch_dir / "batch_001_manifest.json").write_text(
                json.dumps(
                    {
                        "records": [
                            {"route_id": "route-one", "task_id": "task-one"},
                            {"route_id": "route-two", "task_id": "task-two"},
                        ]
                    }
                ),
                encoding="utf-8",
            )
            (batch_dir / "batch_002_manifest.json").write_text(
                json.dumps({"records": [{"route_id": "route-three", "task_id": "task-three"}]}),
                encoding="utf-8",
            )

            self.assertEqual(
                reserved_manifest_task_keys(batch_dir),
                {"route-one", "route-two", "route-three"},
            )
            self.assertEqual(
                reserved_manifest_task_keys(batch_dir, exclude_batch_id="batch_002"),
                {"route-one", "route-two"},
            )
            self.assertEqual(
                reserved_manifest_task_keys(
                    batch_dir,
                    ignore_recorded_keys={"route-two"},
                ),
                {"route-one", "route-two", "route-three"},
            )
            (batch_dir / "batch_001_raw.jsonl").write_text("{}\n", encoding="utf-8")
            self.assertEqual(
                reserved_manifest_task_keys(
                    batch_dir,
                    ignore_recorded_keys={"route-two"},
                ),
                {"route-one", "route-three"},
            )

    def test_prepare_rejects_legacy_v1_meta_analysis_and_review_tasks(self) -> None:
        legacy_profiles = [
            ("secondary_meta_analysis", "meta_analysis_evidence_schema"),
            ("secondary_review_coverage", "review_coverage_schema"),
        ]
        for prompt_profile, schema_profile in legacy_profiles:
            with self.subTest(prompt_profile=prompt_profile), tempfile.TemporaryDirectory() as tmpdir:
                path = Path(tmpdir) / "tasks.jsonl"
                path.write_text(
                    json.dumps(
                        {
                            "task_id": "legacy-task",
                            "route_id": "legacy-route",
                            "study_doi": "10.1000/legacy",
                            "task_status": "ready_for_model",
                            "extraction_contract": {
                                "prompt_profile": prompt_profile,
                                "schema_profile": schema_profile,
                            },
                        }
                    )
                    + "\n",
                    encoding="utf-8",
                )

                with self.assertRaisesRegex(SystemExit, "Legacy v1 secondary extraction is permanently disabled"):
                    selected_for_batch(SimpleNamespace(input_jsonl=path))

    def test_submit_rejects_an_already_prepared_legacy_v1_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            requests_jsonl = root / "requests.jsonl"
            manifest_json = root / "manifest.json"
            requests_jsonl.write_text("{}\n", encoding="utf-8")
            manifest_json.write_text(
                json.dumps(
                    {
                        "records": [
                            {
                                "prompt_profile": "secondary_meta_analysis",
                                "schema_profile": "meta_analysis_evidence_schema",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            paths = {
                "requests_jsonl": requests_jsonl,
                "manifest_json": manifest_json,
            }

            with patch("pipeline.extract.run_route_extraction_batch_api.batch_paths", return_value=paths):
                with self.assertRaisesRegex(SystemExit, "Legacy v1 secondary extraction is permanently disabled"):
                    submit_batch(SimpleNamespace())

    def test_request_serialization_cannot_bypass_legacy_v1_guard(self) -> None:
        task = {
            "extraction_contract": {
                "prompt_profile": "secondary_review_coverage",
                "schema_profile": "review_coverage_schema",
            }
        }

        with self.assertRaisesRegex(SystemExit, "Legacy v1 secondary extraction is permanently disabled"):
            request_for_task(api_client=None, task=task, args=SimpleNamespace(), env_values={})

    def test_error_to_success_retry_is_appended_but_reparse_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "outputs.jsonl"
            schema_error = {
                "task_id": "task-one",
                "route_id": "route-one",
                "status": "schema_error",
            }
            success = {
                "task_id": "task-one",
                "route_id": "route-one",
                "input_fingerprint": "a" * 64,
                "status": "ok",
            }

            self.assertEqual(append_unique_jsonl(path, [schema_error]), 1)
            self.assertEqual(append_unique_jsonl(path, [success]), 1)
            self.assertEqual(append_unique_jsonl(path, [success]), 0)
            rows = read_jsonl(path)

        self.assertEqual([row["status"] for row in rows], ["schema_error", "ok"])


if __name__ == "__main__":
    unittest.main()
