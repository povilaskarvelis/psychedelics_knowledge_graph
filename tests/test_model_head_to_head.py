import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pipeline.validate.model_head_to_head import analyze_response, atomic_json, cost, main, restore, strip_descriptions, usage_fields


class DurableModelEvaluationTests(unittest.TestCase):
    def test_gemini_null_optional_usage(self):
        raw = {"usage_metadata": {"prompt_token_count": 100, "candidates_token_count": 25,
                                  "thoughts_token_count": None, "cached_content_token_count": None}}
        fields = usage_fields(raw, "gemini")
        self.assertEqual(fields["output_tokens"], 25)
        self.assertEqual(fields["reasoning_tokens"], 0)
        self.assertEqual(fields["cached_tokens"], 0)

    def test_missing_mandatory_usage_is_unknown_not_free(self):
        for raw, arm in [({}, "gemini"), ({"usage_metadata": {"prompt_token_count": 4}}, "gemini"), ({}, "luna")]:
            with self.assertRaises(ValueError):
                usage_fields(raw, arm)

    def test_openai_null_cache_details(self):
        raw = {"usage": {"input_tokens": 100, "output_tokens": 25,
                         "input_tokens_details": None, "output_tokens_details": None}}
        fields = usage_fields(raw, "luna")
        self.assertEqual(fields["cache_write_tokens"], 0)
        self.assertEqual(fields["reasoning_tokens"], 0)

    def test_parse_failure_keeps_usage_text_and_cost(self):
        case = dict(case_id="screening:example", input_sha256="frozen", family="screening",
                    study_doi="example", text_depth="title_abstract", original_schema={"type": "object"})
        raw = {"usage_metadata": {"prompt_token_count": 100, "candidates_token_count": 25},
               "candidates": [{"finish_reason": "STOP", "content": {"parts": [{"text": "invalid json"}]}}]}
        result = analyze_response(case, "gemini", {"response": raw, "latency_seconds": 1})
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["raw_text"], "invalid json")
        self.assertAlmostEqual(result["estimated_cost_usd"], .000125)

    def test_invalid_cache_counter_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "cache reads plus writes"):
            cost(dict(arm="luna", input_tokens=100, output_tokens=2, cached_tokens=90, cache_write_tokens=30))

    def test_long_context_boundary(self):
        self.assertAlmostEqual(cost(dict(arm="luna", input_tokens=272000, output_tokens=1000)), .0277)
        self.assertAlmostEqual(cost(dict(arm="luna", input_tokens=272001, output_tokens=1000)), .0551502)

    def test_saved_response_survives_usage_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "response.json"
            raw = {"candidates": [{"content": {"parts": [{"text": "{invalid"}]}}]}
            atomic_json(path, raw)
            with self.assertRaises(ValueError):
                usage_fields(raw, "gemini")
            self.assertEqual(json.loads(path.read_text()), raw)
            self.assertFalse(path.with_suffix(".json.tmp").exists())

    def test_long_context_cache_write_price(self):
        row = dict(arm="luna", input_tokens=300000, output_tokens=1000,
                   cached_tokens=100000, cache_write_tokens=100000)
        self.assertAlmostEqual(cost(row), .04775)
        self.assertAlmostEqual(cost(row, uncached=True), .06075)

    def test_adapter_preserves_scientific_null_and_required_objects(self):
        schema = {"type": "object", "required": ["required_object", "estimate"], "properties": {
            "optional_object": {"type": "object", "properties": {"n": {"type": "integer"}}},
            "required_object": {"type": "object", "properties": {"n": {"type": "integer"}}},
            "estimate": {"type": ["number", "null"]}}}
        value = {"optional_object": {"n": None}, "required_object": {"n": None}, "estimate": None}
        self.assertEqual(restore(value, schema), {"required_object": {}, "estimate": None})

    def test_schema_metadata_strip_preserves_description_field(self):
        schema = {"description": "metadata", "properties": {"description": {"type": "string", "description": "field metadata"}}}
        self.assertEqual(strip_descriptions(schema), {"properties": {"description": {"type": "string"}}})

    def test_restart_stops_before_clients_for_unresolved_paid_request(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder)
            (out / "cases.jsonl").write_text("")
            atomic_json(out / "requests" / "pending.json", {"reservation_usd": 1})
            with patch("sys.argv", ["benchmark", "--run-dir", folder, "--reprocess-only"]):
                with self.assertRaisesRegex(RuntimeError, "Unknown billed request"):
                    main()

    def test_unknown_error_does_not_release_reservation_on_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder)
            (out / "cases.jsonl").write_text("")
            atomic_json(out / "requests" / "pending.json", {"reservation_usd": 1})
            atomic_json(out / "errors" / "pending.json", {"known_unbilled": False})
            with patch("sys.argv", ["benchmark", "--run-dir", folder, "--reprocess-only"]):
                with self.assertRaisesRegex(RuntimeError, "Unresolved billed attempt"):
                    main()

    def test_luna_only_run_never_constructs_or_calls_gemini(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder)
            cases = [dict(case_id=f"screening:{index}", family="screening", input_sha256=str(index),
                          system_instruction="Classify", content="Paper", openai_schema={})
                     for index in range(2)]
            (out / "cases.jsonl").write_text("".join(json.dumps(c) + "\n" for c in cases))
            with patch("sys.argv", ["benchmark", "--run-dir", folder, "--arms", "luna"]), \
                    patch("pipeline.extract.run_route_extraction.load_dotenv", return_value={"OPENAI_API_KEY": "test"}), \
                    patch("openai.OpenAI") as openai_client, \
                    patch("google.genai.Client") as gemini_client, \
                    patch("pipeline.validate.model_head_to_head.analyze_response",
                          return_value={"estimated_cost_usd": .001, "status": "ok"}):
                openai_client.return_value.responses.create.return_value.model_dump.return_value = {"status": "completed"}
                main()
                self.assertEqual(openai_client.return_value.responses.create.call_count, 2)
                self.assertTrue(all(c.kwargs["model"] == "gpt-6-luna"
                                    for c in openai_client.return_value.responses.create.call_args_list))
                gemini_client.assert_not_called()
            self.assertEqual(len(list((out / "responses").glob("*.json"))), 2)


if __name__ == "__main__":
    unittest.main()
