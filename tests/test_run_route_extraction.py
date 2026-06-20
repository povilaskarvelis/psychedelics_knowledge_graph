import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from jsonschema import Draft7Validator

from pipeline.extract.route_extraction_profiles import (
    build_system_instruction,
    load_schema,
    profile_for_key,
    schema_for_native,
    supported_profile_keys,
)
from pipeline.extract.run_route_extraction import (
    build_contents,
    dry_run_report,
    inject_route_identity_fields,
    parse_json_response,
    selected_tasks,
    text_depth_for_task,
)


ROOT = Path(__file__).resolve().parents[1]


def make_task(
    *,
    route_id: str = "route-meta",
    prompt_profile: str = "secondary_meta_analysis",
    schema_profile: str = "synthesis_evidence_schema",
    task_status: str = "ready_for_model",
    source_type: str = "meta_analysis",
) -> dict:
    return {
        "schema_version": "route_extraction_task_v1",
        "task_id": route_id,
        "route_id": route_id,
        "study_doi": "10.1000/meta",
        "task_status": task_status,
        "paper_metadata": {
            "doi": "10.1000/meta",
            "study_title": "A meta-analysis of psilocybin trials",
            "study_year": "2025",
            "publication_type": "Journal Article | Meta-Analysis",
            "abstract": "Five trials were included.",
        },
        "route_context": {
            "route_id": route_id,
            "doi": "10.1000/meta",
            "datasets": "disorder",
            "source_family": "secondary_literature",
            "source_type": source_type,
            "primary_secondary_source_type": source_type,
            "domain_route": "clinical_outcome",
            "domain_tags": "clinical_outcome",
            "access_tier": "full_text_available",
            "route_action": "extract_from_full_text",
            "prompt_profile": prompt_profile,
            "schema_profile": schema_profile,
        },
        "extraction_contract": {
            "contract_version": "route_extraction_task_v1",
            "route_id": route_id,
            "prompt_profile": prompt_profile,
            "schema_profile": schema_profile,
            "domain_route": "clinical_outcome",
            "output_family": "evidence_synthesis",
            "source_family": "secondary_literature",
            "source_type": source_type,
            "access_level": "full_text_seen",
        },
        "text_source": {
            "mode": "full_text_packet",
            "status": task_status,
            "access_level": "full_text_seen",
            "route_action": "extract_from_full_text",
            "packet_id": "disorder:10.1000/meta",
            "packet_source_path": "/tmp/packets.jsonl",
            "packet_selection_basis": "matched_route_dataset:disorder",
            "fulltext_artifact_paths": ["/tmp/meta.json"],
            "local_pdf_paths": [],
            "abstract_available": True,
        },
        "content": {
            "title": "A meta-analysis of psilocybin trials",
            "abstract": "Five trials were included.",
        },
    }


def minimal_synthesis_result() -> dict:
    quote = "Five randomized trials involving 238 participants were included."
    return {
        "schema_version": "wrong_version_to_be_overwritten",
        "task_id": "",
        "route_id": "",
        "study_doi": "",
        "domain_route": "uncertain",
        "source_type": "uncertain",
        "extraction_status": "no_extractable_synthesis_result",
        "synthesis_assessment": {
            "is_in_scope": True,
            "is_meta_analysis": True,
            "is_network_meta_analysis": False,
            "has_extractable_quantitative_results": False,
            "relationship_domain": "clinical_outcome",
            "population_or_system": "Adults with depression",
            "primary_compounds_or_classes": "psilocybin",
            "primary_entities": "depression",
            "needs_human_review": False,
            "reasoning_summary": "The supplied text identifies an in-scope meta-analysis.",
            "evidence_location": "abstract",
            "evidence_locator": "Abstract",
            "supporting_quote": quote,
        },
        "search_methods": {
            "databases_searched": "not_reported",
            "search_start_date": "not_reported",
            "search_end_date": "not_reported",
            "last_search_date": "not_reported",
            "search_strategy_summary": "not_reported",
            "registration_id": "not_reported",
            "protocol_doi": "not_reported",
            "evidence_location": "not_reported",
            "evidence_locator": "not_reported",
            "supporting_quote": "not_reported",
        },
        "eligibility_criteria": {
            "population_or_system": "not_reported",
            "intervention_or_exposure": "not_reported",
            "comparators": "not_reported",
            "eligible_outcomes_or_entities": "not_reported",
            "eligible_study_designs": "not_reported",
            "date_or_language_limits": "not_reported",
            "exclusion_criteria": "not_reported",
            "evidence_location": "not_reported",
            "evidence_locator": "not_reported",
            "supporting_quote": "not_reported",
        },
        "included_evidence_summary": {
            "included_study_count": "5",
            "included_participant_count": "238",
            "included_experiment_or_assay_count": "not_applicable",
            "included_studies_completeness": "not_enumerated",
            "included_studies_not_enumerated_reason": "Study list is not present in supplied text.",
            "study_year_range": "not_reported",
            "country_or_region_summary": "not_reported",
            "evidence_location": "abstract",
            "evidence_locator": "Abstract",
            "supporting_quote": quote,
        },
        "included_studies": [],
        "synthesis_results": [],
        "risk_of_bias_assessments": [],
        "certainty_assessments": [],
        "authors_conclusions": [],
        "coverage_gaps": [],
        "extraction_warnings": [],
    }


def make_args(**overrides: object) -> SimpleNamespace:
    args = {
        "input_jsonl": "/tmp/tasks.jsonl",
        "schema_mode": "native",
        "only_ready": True,
        "include_unsupported": False,
        "prompt_profile": [],
        "schema_profile": [],
        "route_id": [],
        "doi": [],
        "start_index": 1,
        "limit": 0,
        "include_scaffold_profiles": False,
    }
    args.update(overrides)
    return SimpleNamespace(**args)


class RouteExtractionRunnerTest(unittest.TestCase):
    def test_profile_registry_resolves_meta_analysis_profile(self) -> None:
        profile = profile_for_key("secondary_meta_analysis", "synthesis_evidence_schema")

        self.assertEqual(profile.output_schema_version, "synthesis_evidence_v1")
        self.assertTrue(profile.prompt_path.exists())
        self.assertTrue(profile.schema_path.exists())
        self.assertTrue(
            any(
                row["prompt_profile"] == "secondary_meta_analysis"
                and row["schema_profile"] == "synthesis_evidence_schema"
                for row in supported_profile_keys()
            )
        )

    def test_system_instruction_can_use_prompt_or_native_schema_mode(self) -> None:
        profile = profile_for_key("secondary_meta_analysis", "synthesis_evidence_schema")
        schema = load_schema(profile.schema_path)

        prompt_mode = build_system_instruction(profile, schema, "prompt")
        native_mode = build_system_instruction(profile, schema, "native")
        native_schema = schema_for_native(schema)

        self.assertIn("Secondary Meta-Analysis Article-Text Extraction", prompt_mode)
        self.assertIn("synthesis_evidence_v1", prompt_mode)
        self.assertIn("response_json_schema", native_mode)
        self.assertNotIn("definitions", native_schema)
        self.assertIn("properties", native_schema)

    def test_task_text_depth_maps_full_text_access_to_article_text(self) -> None:
        self.assertEqual(text_depth_for_task(make_task()), "article_text")

    def test_model_payload_uses_plain_extraction_task_language(self) -> None:
        contents = build_contents(make_task())

        self.assertIn("OUTPUT_FIELDS_TO_COPY", contents)
        self.assertIn("PAPER_METADATA_JSON", contents)
        self.assertIn("ABSTRACT_TEXT", contents)
        self.assertNotIn("EXTRACTION_TASK_JSON", contents)
        self.assertNotIn("route_context", contents)
        self.assertNotIn("extraction_contract", contents)
        self.assertNotIn("prompt_profile", contents)
        self.assertNotIn("schema_profile", contents)
        self.assertNotIn("routed paper task", contents)

    def test_model_payload_loads_selected_fulltext_packet_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            packet_path = Path(tmpdir) / "packets.jsonl"
            packet_path.write_text(
                json.dumps(
                    {
                        "packet_id": "disorder:10.1000/meta",
                        "dataset": "disorder",
                        "study_doi": "10.1000/meta",
                        "paper_metadata": {
                            "study_title": "A meta-analysis of psilocybin trials",
                            "abstract": "Five trials were included.",
                        },
                        "llm_chunks": [
                            {
                                "chunk_id": "C001",
                                "heading": "Results",
                                "text": "The article text reports a pooled estimate for psilocybin.",
                            }
                        ],
                        "tables": [],
                        "figures": [],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            task = make_task()
            task["text_source"]["packet_source_path"] = str(packet_path)
            task["text_source"]["packet_id"] = "disorder:10.1000/meta"

            contents = build_contents(task)

        self.assertIn("ARTICLE_TEXT", contents)
        self.assertIn("The article text reports a pooled estimate for psilocybin.", contents)

    def test_selected_tasks_defaults_to_ready_supported_profiles(self) -> None:
        tasks = [
            make_task(route_id="route-meta"),
            make_task(route_id="route-primary", prompt_profile="primary_clinical", schema_profile="primary_evidence_schema"),
            make_task(route_id="route-not-ready", task_status="needs_fulltext_packet"),
        ]

        selected = selected_tasks(tasks, make_args())

        self.assertEqual([task["route_id"] for _index, task in selected], ["route-meta", "route-primary"])

    def test_dry_run_report_lists_selected_supported_tasks(self) -> None:
        tasks = [
            make_task(route_id="route-meta"),
            make_task(route_id="route-primary", prompt_profile="primary_clinical", schema_profile="primary_evidence_schema"),
        ]
        selected = selected_tasks(tasks, make_args())
        report = dry_run_report(tasks, selected, make_args())

        self.assertEqual(report["status"], "dry_run")
        self.assertEqual(report["tasks_selected"], 2)
        self.assertEqual(report["unregistered_tasks_skipped"], 0)
        self.assertEqual(report["registered_non_model_tasks_skipped"], 0)
        self.assertEqual(report["selected_tasks"][0]["route_id"], "route-meta")
        self.assertEqual(report["selected_tasks"][1]["route_id"], "route-primary")

    def test_inject_identity_fields_makes_minimal_result_schema_valid(self) -> None:
        profile = profile_for_key("secondary_meta_analysis", "synthesis_evidence_schema")
        schema = load_schema(profile.schema_path)
        result = inject_route_identity_fields(minimal_synthesis_result(), make_task(), profile)
        errors = sorted(Draft7Validator(schema).iter_errors(result), key=lambda error: list(error.path))

        self.assertEqual(errors, [], [error.message for error in errors])
        self.assertEqual(result["schema_version"], "synthesis_evidence_v1")
        self.assertEqual(result["task_id"], "route-meta")
        self.assertEqual(result["study_doi"], "10.1000/meta")
        self.assertEqual(result["domain_route"], "clinical_outcome")
        self.assertEqual(result["source_type"], "meta_analysis")

    def test_parse_json_response_handles_fenced_json(self) -> None:
        parsed, method = parse_json_response('```json\\n{"ok": true,}\\n```')

        self.assertEqual(parsed, {"ok": True})
        self.assertEqual(method, "local_cleanup")

    def test_dry_run_cli_does_not_require_api_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            input_jsonl = root / "tasks.jsonl"
            report_json = root / "report.json"
            input_jsonl.write_text(json.dumps(make_task()) + "\n", encoding="utf-8")

            from pipeline.extract.run_route_extraction import run_tasks

            report = run_tasks(
                SimpleNamespace(
                    input_jsonl=str(input_jsonl),
                    out_jsonl=str(root / "out.jsonl"),
                    raw_jsonl=str(root / "raw.jsonl"),
                    report_json=str(report_json),
                    env_file=str(root / "missing.env"),
                    model="",
                    schema_mode="native",
                    prompt_profile=[],
                    schema_profile=[],
                    route_id=[],
                    doi=[],
                    start_index=1,
                    limit=0,
                    only_ready=True,
                    include_scaffold_profiles=False,
                    include_unsupported=False,
                    dry_run=True,
                    overwrite=False,
                    temperature=0.0,
                    max_output_tokens=0,
                    thinking_budget=None,
                    sleep_sec=0.0,
                )
            )
            report_exists = report_json.exists()

        self.assertEqual(report["status"], "dry_run")
        self.assertEqual(report["tasks_selected"], 1)
        self.assertTrue(report_exists)


if __name__ == "__main__":
    unittest.main()
