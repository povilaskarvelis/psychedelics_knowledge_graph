import argparse
import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from pipeline.review.run_gemini_domain_routing_batch import (
    batch_line_key,
    parse_batch_results,
    response_text,
    write_batch_requests,
)
from pipeline.review.advance_gemini_domain_routing_batch_queue import (
    parse_args as parse_advance_queue_args,
    rebuild_combined_outputs,
)


def write_test_tables(root: Path) -> tuple[Path, Path]:
    metadata_table = root / "metadata.parquet"
    prescreen_table = root / "prescreen.parquet"
    pd.DataFrame(
        [
            {
                "doi": "10.1000/domain",
                "study_title": "Psilocybin therapy and depression outcomes",
                "study_year": "2025",
                "abstract": "Psilocybin therapy reduced depression symptoms in adults.",
                "publication_type": "Journal Article | Randomized Controlled Trial",
                "mesh_terms": "Psilocybin | Depression",
                "keywords": "psychedelic therapy",
            }
        ]
    ).to_parquet(metadata_table, index=False)
    pd.DataFrame(
        [
            {
                "doi": "10.1000/domain",
                "run_id": "test_prescreen",
                "prescreen_decision": "retain",
                "retained_for_extraction_candidate": True,
            }
        ]
    ).to_parquet(prescreen_table, index=False)
    return metadata_table, prescreen_table


class GeminiDomainRoutingBatchTests(unittest.TestCase):
    def test_queue_submission_requires_explicit_submit_flag(self) -> None:
        self.assertTrue(parse_advance_queue_args([]).no_submit)
        self.assertFalse(parse_advance_queue_args(["--submit"]).no_submit)
        self.assertTrue(parse_advance_queue_args(["--no-submit"]).no_submit)

    def test_batch_line_helpers_accept_common_result_shapes(self) -> None:
        self.assertEqual(batch_line_key({"metadata": {"key": "request-1"}}, 9), "request-1")
        self.assertEqual(batch_line_key({}, 9), "row-9")
        self.assertEqual(
            response_text({"candidates": [{"content": {"parts": [{"text": "hello"}, {"text": " world"}]}}]}),
            "hello world",
        )

    def test_write_batch_requests_uses_domain_prompt_and_native_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            metadata_table, prescreen_table = write_test_tables(tmp)
            batch_jsonl = tmp / "batch.jsonl"
            manifest_json = tmp / "manifest.json"
            args = argparse.Namespace(
                metadata_table=str(metadata_table),
                prescreen_decisions_table=str(prescreen_table),
                raw_jsonl=str(tmp / "raw.jsonl"),
                doi_file="",
                env_file=str(tmp / ".env"),
                model="gemini-3-flash-preview",
                limit=0,
                start_index=1,
                temperature=0.0,
                max_output_tokens=512,
                thinking_budget=0,
                resume=False,
                batch_input_jsonl=str(batch_jsonl),
                manifest_json=str(manifest_json),
            )

            manifest = write_batch_requests(args)
            request_line = json.loads(batch_jsonl.read_text(encoding="utf-8").splitlines()[0])

            self.assertEqual(manifest["summary"]["prepared_requests"], 1)
            self.assertEqual(request_line["key"], "domain-routing-000001")
            self.assertIn("systemInstruction", request_line["request"])
            self.assertIn("responseJsonSchema", request_line["request"]["generationConfig"])
            self.assertIn("Title: Psilocybin therapy and depression outcomes", request_line["request"]["contents"][0]["parts"][0]["text"])

    def test_parse_batch_results_writes_routing_table_and_raw_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            metadata_table, prescreen_table = write_test_tables(tmp)
            manifest_json = tmp / "manifest.json"
            batch_output_jsonl = tmp / "batch_output.jsonl"
            raw_jsonl = tmp / "raw.jsonl"
            output_table = tmp / "routes.parquet"
            summary_json = tmp / "summary.json"
            counts_csv = tmp / "counts.csv"
            report_json = tmp / "report.json"
            manifest_json.write_text(
                json.dumps(
                    {
                        "inputs": {"model": "gemini-3-flash-preview"},
                        "records": [{"key": "domain-routing-000001", "input_row_index": 1, "doi": "10.1000/domain"}],
                    }
                ),
                encoding="utf-8",
            )
            model_payload = {
                "domain_tags": ["clinical_outcome"],
                "primary_domain": "clinical_outcome",
                "screening_decision": "include_in_scope",
                "screening_reason": "The abstract reports a psychedelic clinical outcome.",
                "paper_type_group": "primary",
                "paper_type": "primary",
                "paper_type_labels": ["primary"],
                "paper_type_reason": "Original clinical outcome study.",
                "methodological_validity_tags": [],
                "rationale": "Clinical depression outcome is central.",
            }
            batch_output_jsonl.write_text(
                json.dumps(
                    {
                        "key": "domain-routing-000001",
                        "response": {
                            "candidates": [{"content": {"parts": [{"text": json.dumps(model_payload)}]}}],
                            "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 20},
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            args = argparse.Namespace(
                batch_output_jsonl=str(batch_output_jsonl),
                manifest_json=str(manifest_json),
                raw_jsonl=str(raw_jsonl),
                output_table=str(output_table),
                summary_json=str(summary_json),
                counts_csv=str(counts_csv),
                report_json=str(report_json),
                metadata_table=str(metadata_table),
                prescreen_decisions_table=str(prescreen_table),
                env_file=str(tmp / ".env"),
                model="",
            )

            report = parse_batch_results(args)
            routes = pd.read_parquet(output_table)

            self.assertEqual(report["summary"]["status_counts"], {"ok": 1})
            self.assertEqual(routes.loc[0, "domain_route"], "clinical_outcome")
            self.assertEqual(json.loads(raw_jsonl.read_text(encoding="utf-8").splitlines()[0])["status"], "ok")
            self.assertTrue(summary_json.exists())
            self.assertTrue(counts_csv.exists())

    def test_parse_batch_results_skips_error_for_prescreen_excluded_doi(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            metadata_table = tmp / "metadata.parquet"
            prescreen_table = tmp / "prescreen.parquet"
            manifest_json = tmp / "manifest.json"
            batch_output_jsonl = tmp / "batch_output.jsonl"
            raw_jsonl = tmp / "raw.jsonl"
            output_table = tmp / "routes.parquet"
            summary_json = tmp / "summary.json"
            counts_csv = tmp / "counts.csv"
            report_json = tmp / "report.json"
            pd.DataFrame(
                [
                    {
                        "doi": "10.3389/fvets.2026.1818746",
                        "study_title": "Clinical study and the diagnosis of lumpy skin disease in cattle",
                        "abstract": "Lumpy skin disease (LSD) is a cattle disease.",
                    }
                ]
            ).to_parquet(metadata_table, index=False)
            pd.DataFrame(
                [
                    {
                        "doi": "10.3389/fvets.2026.1818746",
                        "prescreen_decision": "exclude",
                        "retained_for_extraction_candidate": False,
                    }
                ]
            ).to_parquet(prescreen_table, index=False)
            manifest_json.write_text(
                json.dumps(
                    {
                        "inputs": {"model": "gemini-3-flash-preview"},
                        "records": [
                            {
                                "key": "domain-routing-016052",
                                "input_row_index": 16052,
                                "doi": "10.3389/fvets.2026.1818746",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            batch_output_jsonl.write_text(
                json.dumps({"key": "domain-routing-016052", "response": {"usageMetadata": {"promptTokenCount": 1}}})
                + "\n",
                encoding="utf-8",
            )
            args = argparse.Namespace(
                batch_output_jsonl=str(batch_output_jsonl),
                manifest_json=str(manifest_json),
                raw_jsonl=str(raw_jsonl),
                output_table=str(output_table),
                summary_json=str(summary_json),
                counts_csv=str(counts_csv),
                report_json=str(report_json),
                metadata_table=str(metadata_table),
                prescreen_decisions_table=str(prescreen_table),
                env_file=str(tmp / ".env"),
                model="",
            )

            report = parse_batch_results(args)
            raw_row = json.loads(raw_jsonl.read_text(encoding="utf-8").splitlines()[0])
            routes = pd.read_parquet(output_table)

            self.assertEqual(report["status"], "ok")
            self.assertEqual(report["summary"]["status_counts"], {"skipped_prescreen_excluded": 1})
            self.assertEqual(raw_row["status"], "skipped_prescreen_excluded")
            self.assertEqual(len(routes), 0)

    def test_parse_batch_results_reports_missing_manifest_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            metadata_table, prescreen_table = write_test_tables(tmp)
            manifest_json = tmp / "manifest.json"
            batch_output_jsonl = tmp / "batch_output.jsonl"
            raw_jsonl = tmp / "raw.jsonl"
            output_table = tmp / "routes.parquet"
            report_json = tmp / "report.json"
            manifest_json.write_text(
                json.dumps(
                    {
                        "inputs": {"model": "gemini-3-flash-preview"},
                        "records": [{"key": "domain-routing-000001", "doi": "10.1000/domain"}],
                    }
                ),
                encoding="utf-8",
            )
            batch_output_jsonl.write_text("", encoding="utf-8")
            args = argparse.Namespace(
                batch_output_jsonl=str(batch_output_jsonl),
                manifest_json=str(manifest_json),
                raw_jsonl=str(raw_jsonl),
                output_table=str(output_table),
                summary_json=str(tmp / "summary.json"),
                counts_csv=str(tmp / "counts.csv"),
                report_json=str(report_json),
                metadata_table=str(metadata_table),
                prescreen_decisions_table=str(prescreen_table),
                env_file=str(tmp / ".env"),
                model="",
            )

            report = parse_batch_results(args)
            raw_row = json.loads(raw_jsonl.read_text(encoding="utf-8").splitlines()[0])

            self.assertEqual(report["status"], "issues_found")
            self.assertEqual(report["summary"]["missing_result_keys"], 1)
            self.assertEqual(report["summary"]["status_counts"], {"error": 1})
            self.assertEqual(raw_row["error_type"], "MissingBatchResultError")

    def test_parse_batch_results_reports_duplicate_result_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            metadata_table, prescreen_table = write_test_tables(tmp)
            manifest_json = tmp / "manifest.json"
            batch_output_jsonl = tmp / "batch_output.jsonl"
            raw_jsonl = tmp / "raw.jsonl"
            output_table = tmp / "routes.parquet"
            report_json = tmp / "report.json"
            manifest_json.write_text(
                json.dumps(
                    {
                        "inputs": {"model": "gemini-3-flash-preview"},
                        "records": [{"key": "domain-routing-000001", "doi": "10.1000/domain"}],
                    }
                ),
                encoding="utf-8",
            )
            duplicate = {"key": "domain-routing-000001", "response": {}}
            batch_output_jsonl.write_text(
                json.dumps(duplicate) + "\n" + json.dumps(duplicate) + "\n",
                encoding="utf-8",
            )
            args = argparse.Namespace(
                batch_output_jsonl=str(batch_output_jsonl),
                manifest_json=str(manifest_json),
                raw_jsonl=str(raw_jsonl),
                output_table=str(output_table),
                summary_json=str(tmp / "summary.json"),
                counts_csv=str(tmp / "counts.csv"),
                report_json=str(report_json),
                metadata_table=str(metadata_table),
                prescreen_decisions_table=str(prescreen_table),
                env_file=str(tmp / ".env"),
                model="",
            )

            report = parse_batch_results(args)

            self.assertEqual(report["status"], "issues_found")
            self.assertEqual(report["summary"]["duplicate_result_keys"], 1)
            self.assertEqual(report["summary"]["status_counts"], {"error": 2})

    def test_rebuild_combined_outputs_waits_for_all_parts_before_canonical_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            part1_routes = tmp / "part1.parquet"
            part1_report = tmp / "part1_report.json"
            part1_raw = tmp / "part1_raw.jsonl"
            part2_routes = tmp / "part2.parquet"
            output_table = tmp / "canonical.parquet"
            summary_json = tmp / "canonical_summary.json"
            pd.DataFrame([{"doi": "10.1000/partial", "domain_route": "clinical_outcome"}]).to_parquet(
                part1_routes,
                index=False,
            )
            part1_report.write_text(json.dumps({"status": "ok"}), encoding="utf-8")
            queue = {
                "name": "test_queue",
                "parts": [
                    {
                        "part": 1,
                        "raw_jsonl": str(part1_raw),
                        "report_json": str(part1_report),
                    },
                    {
                        "part": 2,
                        "raw_jsonl": str(tmp / "part2_raw.jsonl"),
                        "report_json": str(tmp / "part2_report.json"),
                    },
                ],
            }
            args = argparse.Namespace(
                output_table=str(output_table),
                summary_json=str(summary_json),
                counts_csv=str(tmp / "counts.csv"),
                raw_jsonl=str(tmp / "raw.jsonl"),
                prescreen_decisions_table=str(tmp / "prescreen.parquet"),
                metadata_table=str(tmp / "metadata.parquet"),
                queue_json=str(tmp / "queue.json"),
                manual_review_json="",
            )
            part1_output = tmp / "paper_domain_routing_gemini.test_queue_part001.parquet"
            part2_output = tmp / "paper_domain_routing_gemini.test_queue_part002.parquet"
            part1_routes.replace(part1_output)
            self.assertFalse(part2_routes.exists())

            result = rebuild_combined_outputs(queue, args)

            self.assertFalse(output_table.exists())
            self.assertFalse(summary_json.exists())
            self.assertFalse(result["written"])
            self.assertEqual(result["parsed_parts"], 1)
            self.assertEqual(result["parts_total"], 2)
            self.assertEqual(result["write_policy"], "canonical_outputs_wait_for_all_parts")

    def test_rebuild_combined_outputs_merges_delta_with_reusable_canonical_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            output_table = tmp / "canonical.parquet"
            raw_jsonl = tmp / "canonical_raw.jsonl"
            prescreen = tmp / "prescreen.parquet"
            part_report = tmp / "part_report.json"
            part_raw = tmp / "part_raw.jsonl"
            part_output = tmp / "paper_domain_routing_gemini.test_delta_part001.parquet"
            base_row = {
                "doi": "10.1000/base",
                "domain_route": "clinical_outcome",
                "screening_decision": "include_in_scope",
                "retained_for_extraction_candidate": True,
            }
            new_row = {
                "doi": "10.1000/new",
                "domain_route": "molecular_target",
                "screening_decision": "include_in_scope",
                "retained_for_extraction_candidate": True,
            }
            pd.DataFrame([base_row]).to_parquet(output_table, index=False)
            pd.DataFrame([new_row]).to_parquet(part_output, index=False)
            pd.DataFrame(
                [
                    {"doi": "10.1000/base", "prescreen_decision": "retain"},
                    {"doi": "10.1000/new", "prescreen_decision": "retain"},
                ]
            ).to_parquet(prescreen, index=False)
            raw_jsonl.write_text(
                json.dumps({"doi": "10.1000/base", "status": "ok"}) + "\n",
                encoding="utf-8",
            )
            part_raw.write_text(
                json.dumps({"doi": "10.1000/new", "status": "ok"}) + "\n",
                encoding="utf-8",
            )
            part_report.write_text(json.dumps({"status": "ok"}), encoding="utf-8")
            queue = {
                "name": "test_delta",
                "inputs": {
                    "existing_routing_table": str(output_table),
                    "existing_raw_jsonl": str(raw_jsonl),
                },
                "parts": [
                    {
                        "part": 1,
                        "raw_jsonl": str(part_raw),
                        "report_json": str(part_report),
                    }
                ],
            }
            args = argparse.Namespace(
                output_table=str(output_table),
                summary_json=str(tmp / "summary.json"),
                counts_csv=str(tmp / "counts.csv"),
                raw_jsonl=str(raw_jsonl),
                prescreen_decisions_table=str(prescreen),
                metadata_table=str(tmp / "metadata.parquet"),
                queue_json=str(tmp / "queue.json"),
                manual_review_json="",
            )

            result = rebuild_combined_outputs(queue, args)
            combined = pd.read_parquet(output_table)
            combined_raw = [json.loads(line) for line in raw_jsonl.read_text(encoding="utf-8").splitlines()]

        self.assertTrue(result["written"])
        self.assertEqual(set(combined["doi"]), {"10.1000/base", "10.1000/new"})
        self.assertEqual({row["doi"] for row in combined_raw}, {"10.1000/base", "10.1000/new"})


if __name__ == "__main__":
    unittest.main()
