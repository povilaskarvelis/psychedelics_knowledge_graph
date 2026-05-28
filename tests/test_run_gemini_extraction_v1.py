import unittest
import tempfile
import json
import argparse
from pathlib import Path

from pipeline.extract.run_gemini_extraction_v1 import (
    build_generation_config,
    build_system_instruction,
    completed_input_ids,
    inject_identity_fields,
    parse_json_response,
    parse_json_response_with_method,
    repair_json_with_model,
    retry_delay_for_error,
    response_looks_truncated_json,
    max_output_tokens_for_record,
    schema_view_for_native,
    schema_view_for_prompt,
    system_instruction_for_record,
)
from pipeline.extract.extraction_v1_utils import normalize_extraction_v1_result


class RunGeminiExtractionV1Test(unittest.TestCase):
    def test_parse_json_response_accepts_plain_json_and_fenced_json(self) -> None:
        self.assertEqual(parse_json_response('{"ok": true}'), {"ok": True})
        self.assertEqual(parse_json_response('```json\n{"ok": true}\n```'), {"ok": True})

    def test_parse_json_response_extracts_object_and_removes_trailing_commas(self) -> None:
        text = 'Here is the JSON:\n{"ok": true, "items": [1, 2,],}'

        self.assertEqual(parse_json_response(text), {"ok": True, "items": [1, 2]})
        self.assertEqual(parse_json_response_with_method(text), ({"ok": True, "items": [1, 2]}, "local_cleanup"))

    def test_response_looks_truncated_json_detects_incomplete_object(self) -> None:
        self.assertTrue(response_looks_truncated_json('{"paper_assessment": {"route": "primary_evidence",'))
        self.assertFalse(response_looks_truncated_json('{"paper_assessment": {"route": "primary_evidence"}}'))
        self.assertFalse(response_looks_truncated_json('prefix {"ok": true} suffix'))

    def test_inject_identity_fields_uses_pilot_record_metadata(self) -> None:
        result = {"paper_assessment": {}, "claims": [], "coverage_mentions": []}
        record = {
            "dataset": "disorder",
            "study_doi": "10.1000/test",
            "pilot_record_id": "pilot-1",
            "access_level": "full_text_seen",
            "paper_metadata": {"openalex_id": "W123"},
            "content": {"packet": {"packet_id": "packet-1"}},
        }

        out = inject_identity_fields(result, record)

        self.assertEqual(out["schema_version"], "extraction_v1")
        self.assertEqual(out["dataset"], "disorder")
        self.assertEqual(out["study_doi"], "10.1000/test")
        self.assertEqual(out["input_record_id"], "pilot-1")
        self.assertEqual(out["input_packet_id"], "packet-1")
        self.assertEqual(out["openalex_id"], "W123")

    def test_completed_input_ids_only_skips_successful_or_schema_checked_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "raw.jsonl"
            path.write_text(
                "\n".join(
                    json.dumps(row)
                    for row in [
                        {"input_record_id": "ok-1", "status": "ok"},
                        {"input_record_id": "bad-1", "status": "error"},
                        {"input_record_id": "schema-1", "status": "schema_error"},
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            self.assertEqual(completed_input_ids(path), {"ok-1", "schema-1"})

    def test_retry_delay_uses_quota_retry_hint(self) -> None:
        exc = RuntimeError("429 RESOURCE_EXHAUSTED. Please retry in 39.5s.")

        self.assertGreaterEqual(retry_delay_for_error(exc, 5), 41.5)

    def test_build_system_instruction_includes_dataset_addendum_before_schema(self) -> None:
        instruction = build_system_instruction(
            "shared rules",
            {"type": "object"},
            "mechanistic addendum",
        )

        self.assertIn("shared rules\n\nmechanistic addendum", instruction)
        self.assertIn("The output must validate against this JSON Schema.", instruction)

    def test_build_system_instruction_can_omit_prompt_schema_for_native_mode(self) -> None:
        instruction = build_system_instruction(
            "shared rules",
            dataset_prompt_text="disorder addendum",
            include_schema=False,
        )

        self.assertIn("shared rules\n\ndisorder addendum", instruction)
        self.assertIn("API response_json_schema", instruction)
        self.assertNotIn("JSON Schema.", instruction)

    def test_build_generation_config_uses_native_schema_when_requested(self) -> None:
        config = build_generation_config(
            system_instruction="rules",
            schema={"type": "object", "properties": {}},
            schema_mode="native",
            temperature=0,
            max_output_tokens=32,
        )
        dumped = config.model_dump(exclude_none=True)

        self.assertEqual(dumped["response_mime_type"], "application/json")
        self.assertIn("response_json_schema", dumped)

    def test_build_generation_config_omits_native_schema_in_prompt_mode(self) -> None:
        config = build_generation_config(
            system_instruction="rules",
            schema={"type": "object", "properties": {}},
            schema_mode="prompt",
            temperature=0,
            max_output_tokens=32,
        )

        self.assertNotIn("response_json_schema", config.model_dump(exclude_none=True))

    def test_build_generation_config_can_disable_thinking(self) -> None:
        config = build_generation_config(
            system_instruction="rules",
            schema={"type": "object", "properties": {}},
            schema_mode="native",
            temperature=0,
            max_output_tokens=32,
            thinking_budget=0,
        )

        dumped = config.model_dump(exclude_none=True)
        self.assertEqual(dumped["thinking_config"]["thinking_budget"], 0)

    def test_max_output_tokens_for_record_uses_dataset_override(self) -> None:
        args = argparse.Namespace(
            max_output_tokens=8192,
            mechanistic_max_output_tokens=16384,
            disorder_max_output_tokens=0,
        )

        self.assertEqual(max_output_tokens_for_record({"dataset": "mechanistic"}, args), 16384)
        self.assertEqual(max_output_tokens_for_record({"dataset": "disorder"}, args), 8192)

    def test_system_instruction_for_record_uses_dataset_specific_instruction(self) -> None:
        instructions = {"mechanistic": "target prompt", "disorder": "disorder prompt"}

        self.assertEqual(system_instruction_for_record({"dataset": "disorder"}, instructions), "disorder prompt")
        with self.assertRaises(ValueError):
            system_instruction_for_record({"dataset": "other"}, instructions)

    def test_schema_view_for_prompt_prunes_claim_fields_by_dataset(self) -> None:
        schema = json.loads((Path(__file__).resolve().parents[1] / "schema" / "extraction_v1.schema.json").read_text())

        mechanistic = schema_view_for_prompt(schema, "mechanistic")
        disorder = schema_view_for_prompt(schema, "disorder")
        mechanistic_claim = mechanistic["definitions"]["claim"]
        disorder_claim = disorder["definitions"]["claim"]

        self.assertEqual(mechanistic["properties"]["dataset"]["enum"], ["mechanistic"])
        self.assertEqual(disorder["properties"]["dataset"]["enum"], ["disorder"])
        self.assertEqual(mechanistic_claim["properties"]["claim_type"]["enum"], ["compound_target"])
        self.assertEqual(disorder_claim["properties"]["claim_type"]["enum"], ["compound_disorder"])
        self.assertEqual(
            mechanistic_claim["properties"]["graph_entity_type"]["enum"],
            ["target", "system_family", "pathway_process", "molecular_readout", "none", "uncertain"],
        )
        self.assertEqual(
            disorder_claim["properties"]["graph_entity_type"]["enum"],
            [
                "condition_indication",
                "symptom_problem",
                "safety_adverse_event",
                "outcome_scale",
                "none",
                "uncertain",
            ],
        )
        self.assertIn("affinity_type", mechanistic_claim["properties"])
        self.assertNotIn("outcome_measure", mechanistic_claim["properties"])
        self.assertIn("outcome_measure", disorder_claim["properties"])
        self.assertNotIn("affinity_type", disorder_claim["properties"])
        self.assertIn("assay_type", mechanistic_claim["required"])
        self.assertIn("outcome_measure", disorder_claim["required"])

    def test_schema_view_for_native_inlines_refs(self) -> None:
        schema = json.loads((Path(__file__).resolve().parents[1] / "schema" / "extraction_v1.schema.json").read_text())

        native = schema_view_for_native(schema, "disorder")
        serialized = json.dumps(native)

        self.assertNotIn("$ref", serialized)
        self.assertNotIn("definitions", native)
        self.assertEqual(native["properties"]["dataset"]["enum"], ["disorder"])
        self.assertIn("outcome_measure", native["properties"]["claims"]["items"]["properties"])

    def test_model_repair_path_parses_repaired_json(self) -> None:
        class FakeResponse:
            text = '{"ok": true}'
            usage_metadata = None

        class FakeModels:
            def generate_content(self, **kwargs):
                self.kwargs = kwargs
                return FakeResponse()

        class FakeClient:
            def __init__(self):
                self.models = FakeModels()

        fake_client = FakeClient()
        parsed, repaired_text, usage = repair_json_with_model(
            client=fake_client,
            model="gemini-test",
            malformed_text='{"ok": tru',
            schema={"type": "object"},
            max_output_tokens=32,
        )

        self.assertEqual(parsed, {"ok": True})
        self.assertEqual(repaired_text, '{"ok": true}')
        self.assertEqual(usage, {})
        self.assertEqual(
            fake_client.models.kwargs["config"].model_dump(exclude_none=True)["thinking_config"]["thinking_budget"],
            0,
        )

    def test_normalize_extraction_result_repairs_common_model_formatting_slips(self) -> None:
        payload = {
            "schema_version": "extraction_v1",
            "dataset": "mechanistic",
            "study_doi": "10.1000/test",
            "input_packet_id": None,
            "access_level": "abstract_only",
            "paper_assessment": {
                "relevance": "relevant",
                "route": "primary_evidence",
                "has_original_results": None,
                "has_extractable_claims": True,
                "needs_human_review": False,
                "evidence_location": "text",
            },
            "claims": [
                {
                    "claim_type": "compound_target",
                    "disorder": None,
                    "affinity_type": "KD",
                    "result_direction": "positive",
                    "evidence_location": "text",
                    "supporting_quote": "Ketamine changed serotonin clearance in mice.",
                }
            ],
            "coverage_mentions": [
                {
                    "relationship_domain": "compound_disorder",
                    "entity_type": "target",
                    "supporting_quote": "Ketamine is discussed for depression.",
                }
            ],
        }

        normalized, changes = normalize_extraction_v1_result(payload)

        self.assertEqual(normalized["input_packet_id"], "")
        self.assertEqual(normalized["paper_assessment"]["has_original_results"], True)
        self.assertEqual(normalized["paper_assessment"]["evidence_location"], "abstract")
        self.assertEqual(normalized["claims"][0]["disorder"], "not_applicable")
        self.assertEqual(normalized["claims"][0]["affinity_type"], "Kd")
        self.assertEqual(normalized["claims"][0]["result_direction"], "not_applicable")
        self.assertEqual(normalized["claims"][0]["evidence_location"], "abstract")
        self.assertEqual(normalized["coverage_mentions"], [])
        self.assertIn("json_null_to_empty_string", changes)
        self.assertIn("primary_coverage_mentions_removed", changes)
        self.assertIn("compound_target_slots_normalized", changes)
        self.assertIn("affinity_type_normalized", changes)

    def test_normalize_extraction_result_rewrites_not_applicable_target_affinity(self) -> None:
        payload = {
            "paper_assessment": {
                "relevance": "relevant",
                "route": "primary_evidence",
                "has_original_results": True,
                "has_extractable_claims": True,
                "needs_human_review": False,
            },
            "claims": [
                {
                    "claim_type": "compound_target",
                    "target": "SERT",
                    "disorder": "not_applicable",
                    "affinity_type": "not_applicable",
                    "result_direction": "not_applicable",
                    "supporting_quote": "Ketamine changed serotonin clearance in mice.",
                }
            ],
            "coverage_mentions": [],
        }

        normalized, changes = normalize_extraction_v1_result(payload)

        self.assertEqual(normalized["claims"][0]["affinity_type"], "not_reported")
        self.assertIn("compound_target_affinity_type_normalized", changes)

    def test_normalize_extraction_result_maps_unsupported_kinetic_affinity_type_to_other(self) -> None:
        payload = {
            "paper_assessment": {
                "relevance": "relevant",
                "route": "primary_evidence",
                "has_original_results": True,
                "has_extractable_claims": True,
                "needs_human_review": False,
            },
            "claims": [
                {
                    "claim_type": "compound_target",
                    "target": "SERT",
                    "disorder": "not_applicable",
                    "affinity_type": "Km",
                    "result_direction": "not_applicable",
                    "supporting_quote": "MDMA showed transporter kinetics.",
                }
            ],
            "coverage_mentions": [],
        }

        normalized, changes = normalize_extraction_v1_result(payload)

        self.assertEqual(normalized["claims"][0]["affinity_type"], "Other")
        self.assertIn("affinity_type_normalized", changes)

    def test_normalize_extraction_result_maps_unsupported_affinity_type_to_other(self) -> None:
        payload = {
            "paper_assessment": {
                "relevance": "relevant",
                "route": "primary_evidence",
                "has_original_results": True,
                "has_extractable_claims": True,
                "needs_human_review": False,
            },
            "claims": [
                {
                    "claim_type": "compound_target",
                    "target": "5-HT2A receptor",
                    "disorder": "not_applicable",
                    "affinity_type": "Emax",
                    "result_direction": "not_applicable",
                    "supporting_quote": "The compound had higher Emax at 5-HT2A receptors.",
                }
            ],
            "coverage_mentions": [],
        }

        normalized, changes = normalize_extraction_v1_result(payload)

        self.assertEqual(normalized["claims"][0]["affinity_type"], "Other")
        self.assertIn("affinity_type_normalized", changes)

    def test_normalize_extraction_result_maps_system_aliases(self) -> None:
        payload = {
            "paper_assessment": {
                "relevance": "relevant",
                "route": "primary_evidence",
                "system": "in vitro",
                "has_original_results": True,
                "has_extractable_claims": True,
                "needs_human_review": False,
            },
            "claims": [
                {
                    "claim_type": "compound_target",
                    "target": "SERT",
                    "disorder": "not_applicable",
                    "affinity_type": "Ki",
                    "result_direction": "not_applicable",
                    "system": "in vitro",
                    "supporting_quote": "MDMA inhibited SERT in vitro.",
                }
            ],
            "coverage_mentions": [],
        }

        normalized, changes = normalize_extraction_v1_result(payload)

        self.assertEqual(normalized["paper_assessment"]["system"], "in_vitro")
        self.assertEqual(normalized["claims"][0]["system"], "in_vitro")
        self.assertIn("system_normalized", changes)

    def test_normalize_extraction_result_removes_unquoted_claims(self) -> None:
        payload = {
            "paper_assessment": {
                "relevance": "relevant",
                "route": "primary_evidence",
                "has_original_results": True,
                "has_extractable_claims": True,
                "needs_human_review": False,
            },
            "claims": [
                {
                    "claim_type": "compound_disorder",
                    "target": "not_applicable",
                    "supporting_quote": "not_reported",
                },
                {
                    "claim_type": "compound_disorder",
                    "target": "not_applicable",
                    "supporting_quote": "Psilocybin improved depression outcomes.",
                },
            ],
            "coverage_mentions": [],
        }

        normalized, changes = normalize_extraction_v1_result(payload)

        self.assertEqual(len(normalized["claims"]), 1)
        self.assertEqual(
            normalized["claims"][0]["supporting_quote"],
            "Psilocybin improved depression outcomes.",
        )
        self.assertEqual(normalized["paper_assessment"]["route"], "primary_evidence")
        self.assertIn("unquoted_claims_removed", changes)

    def test_normalize_extraction_result_routes_all_unquoted_primary_to_review(self) -> None:
        payload = {
            "paper_assessment": {
                "relevance": "relevant",
                "route": "primary_evidence",
                "has_original_results": True,
                "has_extractable_claims": True,
                "needs_human_review": False,
            },
            "claims": [{"claim_type": "compound_disorder", "supporting_quote": ""}],
            "coverage_mentions": [],
        }

        normalized, changes = normalize_extraction_v1_result(payload)

        self.assertEqual(normalized["claims"], [])
        self.assertEqual(normalized["paper_assessment"]["route"], "human_review")
        self.assertTrue(normalized["paper_assessment"]["needs_human_review"])
        self.assertIn("unquoted_claims_removed", changes)
        self.assertIn("primary_without_claims_routed_human_review", changes)

    def test_normalize_extraction_result_routes_commentary_to_context_only(self) -> None:
        payload = {
            "paper_assessment": {
                "relevance": "relevant",
                "route": "secondary_literature",
                "source_type": "commentary",
                "paper_type": "commentary",
                "has_original_results": False,
                "has_extractable_claims": False,
                "needs_human_review": False,
            },
            "claims": [
                {
                    "claim_type": "compound_disorder",
                    "supporting_quote": "This commentary discusses psychedelic therapy.",
                }
            ],
            "coverage_mentions": [],
        }

        normalized, changes = normalize_extraction_v1_result(payload)

        self.assertEqual(normalized["paper_assessment"]["route"], "context_only")
        self.assertEqual(normalized["claims"], [])
        self.assertIn("context_source_routed_context_only", changes)
        self.assertIn("context_claims_removed", changes)

    def test_normalize_extraction_result_routes_non_review_secondary_to_context_only(self) -> None:
        payload = {
            "paper_assessment": {
                "relevance": "relevant",
                "route": "secondary_literature",
                "source_family": "original_empirical",
                "source_type": "primary_study",
                "paper_type": "primary_results",
                "has_original_results": False,
                "has_extractable_claims": False,
                "needs_human_review": False,
            },
            "claims": [],
            "coverage_mentions": [
                {
                    "coverage_type": "discusses",
                    "relationship_domain": "compound_target",
                    "compound": "psilocybin",
                    "entity_type": "target",
                    "entity": "5-HT2A",
                    "evidence_location": "abstract",
                    "evidence_locator": "Abstract",
                    "supporting_quote": "The paper discusses psilocybin receptor mechanisms.",
                    "confidence": 0.8,
                    "needs_human_review": False,
                }
            ],
        }

        normalized, changes = normalize_extraction_v1_result(payload)

        self.assertEqual(normalized["paper_assessment"]["route"], "context_only")
        self.assertFalse(normalized["paper_assessment"]["has_extractable_claims"])
        self.assertEqual(len(normalized["coverage_mentions"]), 1)
        self.assertIn("secondary_metadata_conflict_routed_context_only", changes)

    def test_normalize_extraction_result_adds_missing_assessment_required_defaults(self) -> None:
        payload = {
            "paper_assessment": {
                "relevance": "relevant",
                "route": "human_review",
                "has_original_results": False,
                "has_extractable_claims": False,
                "needs_human_review": False,
            },
            "claims": [],
            "coverage_mentions": [],
        }

        normalized, changes = normalize_extraction_v1_result(payload)

        self.assertEqual(normalized["paper_assessment"]["confidence"], 0.0)
        self.assertEqual(normalized["paper_assessment"]["reasoning_summary"], "not_reported")
        self.assertTrue(normalized["paper_assessment"]["needs_human_review"])
        self.assertIn("paper_assessment_required_defaults", changes)

    def test_normalize_extraction_result_removes_extra_coverage_mention_fields(self) -> None:
        payload = {
            "paper_assessment": {
                "relevance": "relevant",
                "route": "secondary_literature",
                "source_family": "evidence_synthesis",
                "has_original_results": False,
                "has_extractable_claims": False,
                "needs_human_review": False,
            },
            "claims": [],
            "coverage_mentions": [
                {
                    "coverage_type": "reviews",
                    "relationship_domain": "compound_disorder",
                    "compound": "Psilocybin",
                    "entity_type": "disorder",
                    "entity": "Major depressive disorder",
                    "evidence_location": "abstract",
                    "evidence_locator": "Abstract",
                    "supporting_quote": "Reviews discuss psilocybin for depression.",
                    "confidence": 0.8,
                    "needs_human_review": False,
                    "clinical_context_condition": "not allowed on coverage mentions",
                }
            ],
        }

        normalized, changes = normalize_extraction_v1_result(payload)

        self.assertNotIn("clinical_context_condition", normalized["coverage_mentions"][0])
        self.assertIn("coverage_extra_fields_removed", changes)

    def test_normalize_extraction_result_maps_known_entity_role_aliases(self) -> None:
        payload = {
            "paper_assessment": {
                "relevance": "relevant",
                "route": "primary_evidence",
                "has_original_results": True,
                "has_extractable_claims": True,
                "needs_human_review": False,
            },
            "claims": [
                {
                    "claim_type": "compound_disorder",
                    "target": "not_applicable",
                    "disorder": "Opioid use",
                    "entity_role": "drug_consumption_measure",
                    "graph_include_candidate": False,
                    "supporting_quote": "Morphine use was reduced.",
                }
            ],
            "coverage_mentions": [],
        }

        normalized, changes = normalize_extraction_v1_result(payload)

        self.assertEqual(normalized["claims"][0]["entity_role"], "outcome_measure")
        self.assertIn("entity_role_normalized", changes)

    def test_normalize_extraction_result_removes_non_graph_endpoint_candidate(self) -> None:
        payload = {
            "paper_assessment": {
                "relevance": "relevant",
                "route": "primary_evidence",
                "has_original_results": True,
                "has_extractable_claims": True,
                "needs_human_review": False,
            },
            "claims": [
                {
                    "claim_type": "compound_target",
                    "target": "NMDA receptor",
                    "disorder": "not_applicable",
                    "entity_role": "assay_readout",
                    "graph_include_candidate": True,
                    "graph_exclusion_reason": "not_applicable",
                    "supporting_quote": "Ketamine altered cell proliferation.",
                }
            ],
            "coverage_mentions": [],
        }

        normalized, changes = normalize_extraction_v1_result(payload)

        self.assertFalse(normalized["claims"][0]["graph_include_candidate"])
        self.assertIn("assay_readout", normalized["claims"][0]["graph_exclusion_reason"])
        self.assertIn("non_graph_endpoint_candidate_removed", changes)

    def test_normalize_extraction_result_keeps_mechanistic_readout_candidate(self) -> None:
        payload = {
            "paper_assessment": {
                "relevance": "relevant",
                "route": "primary_evidence",
                "has_original_results": True,
                "has_extractable_claims": True,
                "needs_human_review": False,
            },
            "claims": [
                {
                    "claim_type": "compound_target",
                    "compound": "Ketamine",
                    "target": "BDNF",
                    "disorder": "not_applicable",
                    "entity_role": "molecular_readout",
                    "graph_entity_type": "molecular_readout",
                    "graph_include_candidate": True,
                    "graph_exclusion_reason": "not_applicable",
                    "supporting_quote": "Ketamine increased BDNF expression.",
                }
            ],
            "coverage_mentions": [],
        }

        normalized, changes = normalize_extraction_v1_result(payload)

        self.assertEqual(normalized["claims"][0]["entity_role"], "biomarker")
        self.assertTrue(normalized["claims"][0]["graph_include_candidate"])
        self.assertNotIn("non_graph_endpoint_candidate_removed", changes)


if __name__ == "__main__":
    unittest.main()
