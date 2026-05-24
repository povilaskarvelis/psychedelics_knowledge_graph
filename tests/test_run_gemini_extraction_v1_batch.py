import argparse
import json
import tempfile
import unittest
from pathlib import Path

from pipeline.extract.run_gemini_extraction_v1 import (
    DEFAULT_DISORDER_PROMPT,
    DEFAULT_ENV,
    DEFAULT_MECHANISTIC_PROMPT,
    DEFAULT_PROMPT,
    DEFAULT_SCHEMA,
)
from pipeline.extract.run_gemini_extraction_v1_batch import (
    batch_line_key,
    parse_batch_results,
    response_text,
    write_batch_requests,
)


def disorder_model_payload() -> dict:
    return {
        "schema_version": "extraction_v1",
        "dataset": "disorder",
        "study_doi": "10.1000/batch",
        "access_level": "abstract_only",
        "paper_assessment": {
            "relevance": "relevant",
            "route": "primary_evidence",
            "source_family": "original_empirical",
            "source_type": "primary_study",
            "paper_type": "primary_results",
            "study_design": "randomized_controlled_trial",
            "system": "clinical",
            "has_original_results": True,
            "has_extractable_claims": True,
            "evidence_location": "abstract",
            "evidence_locator": "Abstract",
            "supporting_quote": "Psilocybin reduced depressive symptoms.",
            "confidence": 0.9,
            "needs_human_review": False,
            "reasoning_summary": "The abstract reports an original clinical result.",
        },
        "claims": [
            {
                "claim_type": "compound_disorder",
                "compound": "Psilocybin",
                "target": "not_applicable",
                "disorder": "Major depressive disorder",
                "raw_entity_label": "depressive symptoms",
                "entity_role": "therapeutic_indication",
                "clinical_context_condition": "Major depressive disorder",
                "graph_entity_label": "Major depressive disorder",
                "graph_entity_type": "indication",
                "graph_include_candidate": True,
                "graph_exclusion_reason": "not_applicable",
                "support": "supported",
                "study_design": "randomized_controlled_trial",
                "system": "clinical",
                "outcome_type": "symptom reduction",
                "outcome_domain": "depression",
                "outcome_measure": "MADRS",
                "result_direction": "positive",
                "sample_size_total": "59",
                "population": "Adults with major depressive disorder",
                "intervention_or_exposure": "Psilocybin-assisted therapy",
                "comparator": "Placebo",
                "dose": "not_reported",
                "route": "not_reported",
                "session_count_or_duration": "not_reported",
                "timepoint": "not_reported",
                "adverse_events": "not_reported",
                "evidence_location": "abstract",
                "evidence_locator": "Abstract",
                "supporting_quote": "Psilocybin reduced depressive symptoms.",
                "confidence": 0.9,
                "needs_human_review": False,
            }
        ],
        "coverage_mentions": [],
    }


class RunGeminiExtractionV1BatchTest(unittest.TestCase):
    def test_response_text_extracts_candidate_parts(self) -> None:
        response = {
            "candidates": [
                {"content": {"parts": [{"text": "hello "}, {"text": "world"}]}},
            ]
        }

        self.assertEqual(response_text(response), "hello world")

    def test_batch_line_key_accepts_common_shapes(self) -> None:
        self.assertEqual(batch_line_key({"key": "request-1"}, 9), "request-1")
        self.assertEqual(batch_line_key({"metadata": {"key": "request-2"}}, 9), "request-2")
        self.assertEqual(batch_line_key({}, 9), "row-9")

    def test_write_batch_requests_uses_native_schema_and_dynamic_thinking_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            input_jsonl = tmp / "input.jsonl"
            batch_jsonl = tmp / "batch.jsonl"
            manifest_json = tmp / "manifest.json"
            input_jsonl.write_text(
                json.dumps(
                    {
                        "pilot_record_id": "pilot-batch-1",
                        "dataset": "disorder",
                        "study_doi": "10.1000/batch",
                        "access_level": "abstract_only",
                        "paper_metadata": {"study_title": "A batch paper"},
                        "content": {
                            "title": "A batch paper",
                            "abstract": "Psilocybin reduced depressive symptoms.",
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            args = argparse.Namespace(
                input_jsonl=str(input_jsonl),
                raw_jsonl=str(tmp / "raw.jsonl"),
                prompt=str(DEFAULT_PROMPT),
                mechanistic_prompt=str(DEFAULT_MECHANISTIC_PROMPT),
                disorder_prompt=str(DEFAULT_DISORDER_PROMPT),
                schema=str(DEFAULT_SCHEMA),
                env_file=str(DEFAULT_ENV),
                model="gemini-2.5-flash",
                schema_mode="native",
                limit=0,
                start_index=1,
                temperature=0.0,
                max_output_tokens=8192,
                mechanistic_max_output_tokens=16384,
                disorder_max_output_tokens=0,
                thinking_budget=None,
                resume=False,
                batch_input_jsonl=str(batch_jsonl),
                manifest_json=str(manifest_json),
            )

            manifest = write_batch_requests(args)
            request_line = json.loads(batch_jsonl.read_text(encoding="utf-8").splitlines()[0])

            self.assertEqual(manifest["summary"]["prepared_requests"], 1)
            self.assertEqual(request_line["key"], "pilot-batch-1")
            self.assertIn("systemInstruction", request_line["request"])
            self.assertIn("responseJsonSchema", request_line["request"]["generationConfig"])
            self.assertNotIn("thinkingConfig", request_line["request"]["generationConfig"])

    def test_parse_batch_results_writes_extraction_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            input_jsonl = tmp / "input.jsonl"
            manifest_json = tmp / "manifest.json"
            batch_output_jsonl = tmp / "batch_output.jsonl"
            out_jsonl = tmp / "out.jsonl"
            raw_jsonl = tmp / "raw.jsonl"
            report_json = tmp / "report.json"
            input_jsonl.write_text(
                json.dumps(
                    {
                        "pilot_record_id": "pilot-batch-1",
                        "dataset": "disorder",
                        "study_doi": "10.1000/batch",
                        "access_level": "abstract_only",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            manifest_json.write_text(
                json.dumps(
                    {
                        "inputs": {"input_jsonl": str(input_jsonl)},
                        "records": [{"key": "pilot-batch-1", "input_row_index": 1}],
                    }
                ),
                encoding="utf-8",
            )
            batch_output_jsonl.write_text(
                json.dumps(
                    {
                        "key": "pilot-batch-1",
                        "response": {
                            "candidates": [
                                {
                                    "content": {
                                        "parts": [
                                            {"text": json.dumps(disorder_model_payload())},
                                        ]
                                    }
                                }
                            ],
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
                out_jsonl=str(out_jsonl),
                raw_jsonl=str(raw_jsonl),
                report_json=str(report_json),
                schema=str(DEFAULT_SCHEMA),
            )

            report = parse_batch_results(args)

            self.assertEqual(report["summary"]["status_counts"], {"ok": 1})
            self.assertEqual(len(out_jsonl.read_text(encoding="utf-8").splitlines()), 1)
            self.assertEqual(json.loads(raw_jsonl.read_text(encoding="utf-8").splitlines()[0])["route"], "primary_evidence")


if __name__ == "__main__":
    unittest.main()
