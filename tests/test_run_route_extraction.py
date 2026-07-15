import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from jsonschema import Draft7Validator

from pipeline.extract.route_extraction_profiles import (
    build_system_instruction,
    load_schema_for_profile,
    profile_for_key,
    schema_path_for_profile,
    schema_for_assigned_domain,
    schema_for_native,
    supported_profile_keys,
)
from pipeline.extract.run_route_extraction import (
    DEFAULT_GEMINI_MODEL,
    DEFAULT_ROUTED_RUN_ROOT,
    build_contents,
    dry_run_report,
    inject_route_identity_fields,
    model_for_task,
    parse_json_response,
    resolve_output_paths,
    selected_tasks,
    text_depth_for_task,
)


ROOT = Path(__file__).resolve().parents[1]


def make_task(
    *,
    route_id: str = "route-meta",
    prompt_profile: str = "secondary_meta_analysis",
    schema_profile: str = "meta_analysis_evidence_schema",
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
            "output_family": "meta_analysis_evidence",
            "source_family": "secondary_literature",
            "source_type": source_type,
            "access_level": "full_text_seen",
        },
        "text_source": {
            "mode": "full_text_packet",
            "status": task_status,
            "access_level": "full_text_seen",
            "route_action": "extract_from_full_text",
            "packet_id": "article:10.1000/meta",
            "packet_source_path": "/tmp/packets.jsonl",
            "packet_selection_basis": "matched_doi_and_packet_profile",
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
        "text_depth": "abstract_only",
        "source_text_provenance": {
            "text_depth": "abstract_only",
            "source_text_kind": "abstract_only",
            "source_text_scope": "title and abstract supplied to the model",
        },
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
        },
        "included_evidence_summary": {
            "included_study_count": "5",
            "included_participant_count": "238",
            "included_experiment_or_assay_count": "not_applicable",
            "included_evidence_type_summary": "randomized clinical trials",
            "study_year_range": "not_reported",
            "country_or_region_summary": "not_reported",
            "evidence_location": "abstract",
            "evidence_locator": "Abstract",
        },
        "synthesis_results": [],
        "extraction_warnings": [],
    }


def minimal_primary_result() -> dict:
    return {
        "schema_version": "wrong_version_to_be_overwritten",
        "task_id": "",
        "route_id": "",
        "study_doi": "",
        "domain_route": "uncertain",
        "extraction_status": "extracted",
        "items": [
            {
                "condition_or_population": "Adults with depression",
                "study_design": "randomized clinical trial",
                "compound_or_intervention": "psilocybin",
                "comparator": "placebo",
                "dose_or_regimen": "single dose",
                "sample_size": "not_reported",
                "outcome_measure": "MADRS",
                "clinical_endpoint": "depressive symptoms",
                "assessment_timepoint": "primary endpoint",
                "result_direction": "positive",
                "effect_or_statistic": "not_reported",
                "finding_summary": "Psilocybin improved depressive symptoms versus placebo.",
                "evidence_location": "abstract",
                "evidence_locator": "Abstract",
            }
        ],
        "warnings": [],
    }


def minimal_review_result() -> dict:
    quote = "The review summarized clinical outcomes after psilocybin-assisted therapy."
    return {
        "schema_version": "wrong_version_to_be_overwritten",
        "task_id": "",
        "route_id": "",
        "study_doi": "",
        "domain_route": "uncertain",
        "source_type": "uncertain",
        "extraction_status": "extracted",
        "review_assessment": {
            "is_in_scope": True,
            "review_type": "narrative review",
            "has_extractable_scoped_coverage": True,
            "relationship_domain": "clinical_outcome",
            "population_or_system": "Adults with depression",
            "primary_compounds_or_classes": "psilocybin",
            "primary_entities": "depressive symptoms",
            "substantive_coverage_inventory": [
                {
                    "inventory_id": "I1",
                    "compound_or_class": "psilocybin",
                    "entity_type": "not_applicable",
                    "entity": "depressive symptoms",
                    "coverage_focus": "substantial_topic",
                    "evidence_basis": "review_level_conclusion",
                    "has_coverage_item": True,
                    "coverage_item_ids": ["C1"],
                    "reason_if_no_coverage_item": "not_applicable",
                }
            ],
            "needs_human_review": False,
            "reasoning_summary": "The review discusses clinical outcomes in the selected domain.",
            "evidence_location": "abstract",
            "evidence_locator": "Abstract",
        },
        "coverage_items": [
            {
                "item_id": "C1",
                "relationship_domain": "clinical_outcome",
                "coverage_type": "reviews",
                "coverage_focus": "substantial_topic",
                "compound_or_class": "psilocybin",
                "entity_type": "disorder",
                "entity": "depression",
                "population_or_system": "Adults with depression",
                "reviewed_evidence_type": "clinical studies",
                "summary_statement": "The review describes psilocybin-assisted therapy for depressive symptoms.",
                "direction_or_tone": "supports",
                "participant_or_sample_summary": "not_reported",
                "key_limitations": "small studies",
                "evidence_location": "abstract",
                "evidence_locator": "Abstract",
                "confidence": 0.8,
                "needs_human_review": False,
                "domain_result": {
                    "condition_or_population": "Adults with depression",
                    "condition_or_indication": "Depression",
                    "population_or_subgroup": "Adults with depression",
                    "compound_or_intervention": "psilocybin-assisted therapy",
                    "clinical_topic": "efficacy",
                    "clinical_endpoint": "depressive symptoms",
                    "clinical_endpoint_category": "depressive symptom severity",
                    "outcome_measure_or_instrument": "depression symptom scale",
                    "comparator_or_context": "not_reported",
                    "dose_or_regimen": "not_reported",
                    "time_window": "not_reported",
                    "response_or_remission_metric": "not_reported",
                    "clinical_effect_or_statistic": "not_reported",
                    "certainty_or_evidence_quality": "limited evidence",
                    "review_interpretation": "The review coverage is about clinical outcomes.",
                },
            }
        ],
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
        "model": "",
        "env_file": "/tmp/missing.env",
        "thinking_budget": 0,
    }
    args.update(overrides)
    return SimpleNamespace(**args)


class RouteExtractionRunnerTest(unittest.TestCase):
    def test_run_id_resolves_runner_outputs_to_versioned_directory(self) -> None:
        args = resolve_output_paths(
            make_args(
                run_id="Gemini 3 Flash Batch",
                run_dir="",
                out_jsonl="",
                raw_jsonl="",
                report_json="",
            )
        )

        self.assertEqual(args.run_id, "Gemini_3_Flash_Batch")
        self.assertEqual(
            Path(args.out_jsonl),
            DEFAULT_ROUTED_RUN_ROOT / "Gemini_3_Flash_Batch" / "route_extraction_outputs.jsonl",
        )
        self.assertEqual(
            Path(args.raw_jsonl),
            DEFAULT_ROUTED_RUN_ROOT / "Gemini_3_Flash_Batch" / "route_extraction_raw.jsonl",
        )
        self.assertEqual(
            Path(args.report_json),
            DEFAULT_ROUTED_RUN_ROOT / "Gemini_3_Flash_Batch" / "route_extraction_report.json",
        )

    def test_profile_registry_resolves_meta_analysis_profile(self) -> None:
        profile = profile_for_key("secondary_meta_analysis", "meta_analysis_evidence_schema")

        self.assertEqual(profile.output_schema_version, "meta_analysis_evidence_v1")
        self.assertTrue(profile.prompt_path.exists())
        self.assertTrue(schema_path_for_profile(profile, "clinical_outcome").exists())
        self.assertTrue(
            any(
                row["prompt_profile"] == "secondary_meta_analysis"
                and row["schema_profile"] == "meta_analysis_evidence_schema"
                for row in supported_profile_keys()
            )
        )

    def test_system_instruction_can_use_prompt_or_native_schema_mode(self) -> None:
        profile = profile_for_key("secondary_meta_analysis", "meta_analysis_evidence_schema")
        schema = load_schema_for_profile(profile, "clinical_outcome")

        prompt_mode = build_system_instruction(profile, schema, "prompt", domain_route="clinical_outcome")
        native_mode = build_system_instruction(profile, schema, "native", domain_route="clinical_outcome")
        native_schema = schema_for_native(schema)

        self.assertIn("Secondary Meta-Analysis Article-Text Extraction", prompt_mode)
        self.assertIn("meta_analysis_evidence_v1", prompt_mode)
        self.assertIn("domain_result", prompt_mode)
        self.assertIn("response_json_schema", native_mode)
        self.assertNotIn("definitions", native_schema)
        self.assertIn("properties", native_schema)

    def test_task_text_depth_maps_full_text_access_to_article_text(self) -> None:
        self.assertEqual(text_depth_for_task(make_task()), "article_text")

    def test_model_for_task_uses_article_text_model_when_configured(self) -> None:
        task = make_task()

        model = model_for_task(
            make_args(),
            task,
            {
                "GEMINI_ARTICLE_TEXT_EXTRACTION_MODEL": "gemini-3-flash-preview",
                "GEMINI_ABSTRACT_EXTRACTION_MODEL": "gemini-3-flash-preview",
                "GEMINI_MODEL": "gemini-2.5-flash",
            },
        )

        self.assertEqual(model, "gemini-3-flash-preview")

    def test_model_for_task_uses_abstract_model_when_configured(self) -> None:
        task = make_task()
        task["text_source"]["access_level"] = "abstract_only"
        task["text_source"]["mode"] = "abstract"

        model = model_for_task(
            make_args(),
            task,
            {
                "GEMINI_ARTICLE_TEXT_EXTRACTION_MODEL": "gemini-3-flash-preview",
                "GEMINI_ABSTRACT_EXTRACTION_MODEL": "gemini-3-flash-preview",
                "GEMINI_MODEL": "gemini-2.5-flash",
            },
        )

        self.assertEqual(model, "gemini-3-flash-preview")

    def test_model_for_task_explicit_cli_model_overrides_text_depth_config(self) -> None:
        model = model_for_task(
            make_args(model="gemini-custom"),
            make_task(),
            {"GEMINI_ARTICLE_TEXT_EXTRACTION_MODEL": "gemini-3-flash-preview"},
        )

        self.assertEqual(model, "gemini-custom")

    def test_model_for_task_falls_back_to_generic_extraction_model(self) -> None:
        model = model_for_task(
            make_args(),
            make_task(),
            {"GEMINI_ROUTE_EXTRACTION_MODEL": "gemini-route-default"},
        )

        self.assertEqual(model, "gemini-route-default")

    def test_model_for_task_defaults_to_gemini_3_flash_preview(self) -> None:
        model = model_for_task(make_args(), make_task(), {})

        self.assertEqual(model, "gemini-3-flash-preview")
        self.assertEqual(DEFAULT_GEMINI_MODEL, "gemini-3-flash-preview")

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
                        "packet_id": "article:10.1000/meta",
                        "dataset": "article",
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
            task["text_source"]["packet_id"] = "article:10.1000/meta"

            contents = build_contents(task)

        self.assertIn("ARTICLE_TEXT", contents)
        self.assertIn("The article text reports a pooled estimate for psilocybin.", contents)

    def test_model_payload_collapses_table_layout_whitespace(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            packet_path = Path(tmpdir) / "packets.jsonl"
            packet_path.write_text(
                json.dumps(
                    {
                        "packet_id": "article:10.1000/meta",
                        "dataset": "article",
                        "study_doi": "10.1000/meta",
                        "llm_chunks": [
                            {
                                "chunk_id": "C001",
                                "heading": "Results",
                                "text": "p = 0.04\t\t\t\t\t\tlarge gap\n\n\n\nnext line",
                            }
                        ],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            task = make_task()
            task["text_source"]["packet_source_path"] = str(packet_path)
            task["text_source"]["packet_id"] = "article:10.1000/meta"

            contents = build_contents(task)

        self.assertIn("p = 0.04 large gap\n\nnext line", contents)
        self.assertNotIn("\t", contents)
        self.assertNotIn("\n\n\n", contents)

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
        profile = profile_for_key("secondary_meta_analysis", "meta_analysis_evidence_schema")
        schema = load_schema_for_profile(profile, "clinical_outcome")
        result = inject_route_identity_fields(minimal_synthesis_result(), make_task(), profile)
        errors = sorted(Draft7Validator(schema).iter_errors(result), key=lambda error: list(error.path))

        self.assertEqual(errors, [], [error.message for error in errors])
        self.assertEqual(result["schema_version"], "meta_analysis_evidence_v1")
        self.assertEqual(result["task_id"], "route-meta")
        self.assertEqual(result["study_doi"], "10.1000/meta")
        self.assertEqual(result["domain_route"], "clinical_outcome")
        self.assertEqual(result["source_type"], "meta_analysis")
        self.assertEqual(result["text_depth"], "article_text")
        self.assertEqual(result["source_text_provenance"]["source_text_kind"], "article_text")

    def test_inject_identity_fields_makes_primary_result_schema_valid(self) -> None:
        profile = profile_for_key("primary_clinical", "primary_evidence_schema")
        schema = load_schema_for_profile(profile, "clinical_outcome")
        task = make_task(
            route_id="route-primary",
            prompt_profile="primary_clinical",
            schema_profile="primary_evidence_schema",
            source_type="primary_or_unclear",
        )
        task["route_context"]["domain_route"] = "clinical_outcome"
        task["extraction_contract"]["domain_route"] = "clinical_outcome"
        result = inject_route_identity_fields(minimal_primary_result(), task, profile)
        errors = sorted(Draft7Validator(schema).iter_errors(result), key=lambda error: list(error.path))

        self.assertEqual(errors, [], [error.message for error in errors])
        self.assertEqual(result["schema_version"], "primary_clinical_outcome_v1")
        self.assertEqual(result["paper_type"], "primary_study")
        self.assertEqual(result["text_depth"], "article_text")
        self.assertEqual(result["source_type"], "primary_or_unclear")

    def test_inject_identity_fields_makes_review_result_schema_valid(self) -> None:
        profile = profile_for_key("secondary_review_coverage", "review_coverage_schema")
        schema = load_schema_for_profile(profile, "clinical_outcome")
        task = make_task(
            route_id="route-review",
            prompt_profile="secondary_review_coverage",
            schema_profile="review_coverage_schema",
            source_type="review",
        )
        result = inject_route_identity_fields(minimal_review_result(), task, profile)
        errors = sorted(Draft7Validator(schema).iter_errors(result), key=lambda error: list(error.path))

        self.assertEqual(errors, [], [error.message for error in errors])
        self.assertEqual(result["schema_version"], "review_coverage_v1")
        self.assertEqual(result["source_type"], "review")
        self.assertEqual(result["text_depth"], "article_text")
        self.assertEqual(result["source_text_provenance"]["source_text_kind"], "article_text")

    def test_inject_identity_fields_enforces_secondary_assigned_domain(self) -> None:
        profile = profile_for_key("secondary_review_coverage", "review_coverage_schema")
        schema = schema_for_assigned_domain(load_schema_for_profile(profile, "pharmacokinetics_exposure"), "pharmacokinetics_exposure")
        task = make_task(
            route_id="route-review",
            prompt_profile="secondary_review_coverage",
            schema_profile="review_coverage_schema",
            source_type="review",
        )
        task["route_context"]["domain_route"] = "pharmacokinetics_exposure"
        task["extraction_contract"]["domain_route"] = "pharmacokinetics_exposure"
        raw_result = minimal_review_result()
        raw_result["review_assessment"]["relationship_domain"] = "pharmacokinetics"
        raw_result["coverage_items"][0]["relationship_domain"] = "pharmacokinetics"
        raw_result["coverage_items"][0]["entity_type"] = "pharmacokinetic_parameter"
        raw_result["coverage_items"][0]["entity"] = "bioavailability"
        raw_result["coverage_items"][0]["domain_result"] = {
            "compound_or_analyte": "ketamine",
            "primary_graph_anchor_kind": "pharmacokinetic_parameter",
            "exposure_evidence_category": "bioavailability",
            "analyte_type": "parent compound",
            "metabolic_or_transport_target": "not_reported",
            "metabolic_or_transport_pathway": "not_reported",
            "metabolite_or_analyte": "not_reported",
            "pk_or_exposure_parameter": "bioavailability",
            "value": "16-24",
            "unit": "percent",
            "dose_route_or_formulation": "oral",
            "route_of_administration": "oral",
            "population_or_system": "human",
            "comparator_or_reference": "not_reported",
            "matrix_or_sample": "plasma",
            "review_interpretation": "The review discusses oral ketamine bioavailability.",
        }

        result = inject_route_identity_fields(raw_result, task, profile)
        errors = sorted(Draft7Validator(schema).iter_errors(result), key=lambda error: list(error.path))

        self.assertEqual(errors, [], [error.message for error in errors])
        self.assertEqual(result["review_assessment"]["relationship_domain"], "pharmacokinetics_exposure")
        self.assertEqual(result["coverage_items"][0]["relationship_domain"], "pharmacokinetics_exposure")

    def test_inject_identity_fields_coerces_non_directional_meta_analysis_result_direction(self) -> None:
        profile = profile_for_key("secondary_meta_analysis", "meta_analysis_evidence_schema")
        schema = schema_for_assigned_domain(load_schema_for_profile(profile, "molecular_target"), "molecular_target")
        task = make_task(route_id="route-meta")
        task["route_context"]["domain_route"] = "molecular_target"
        task["extraction_contract"]["domain_route"] = "molecular_target"
        raw_result = minimal_synthesis_result()
        raw_result["synthesis_assessment"]["relationship_domain"] = "target_binding"
        raw_result["synthesis_results"] = [
            {
                "result_id": "R1",
                "relationship_domain": "target_binding",
                "entity_type": "target",
                "entity": "5-HT2A receptor",
                "compound_or_class": "psilocybin",
                "population_or_system": "in vitro assays",
                "intervention_or_exposure": "psilocybin",
                "comparator": "not_reported",
                "outcome_or_endpoint": "target binding",
                "outcome_measure": "binding affinity",
                "timepoint_or_window": "not_applicable",
                "effect_metric": "not_reported",
                "effect_size": "not_reported",
                "study_count": "not_reported",
                "participant_count": "not_applicable",
                "result_direction": "positive",
                "result_role": "main_result",
                "authors_interpretation": "The review describes target binding.",
                "evidence_location": "abstract",
                "evidence_locator": "Abstract",
                "confidence": 0.8,
                "needs_human_review": False,
                "domain_result": {
                    "compound": "psilocybin",
                    "target": "5-HT2A receptor",
                    "target_type": "receptor",
                    "assay_type": "binding assay",
                    "system": "in vitro",
                    "species_or_cell_line": "not_reported",
                    "comparator_or_reference": "not_reported",
                    "action_type": "agonist",
                    "metric": "binding affinity",
                    "value": "not_reported",
                    "synthesis_interpretation": "The synthesis discusses 5-HT2A receptor binding.",
                },
            }
        ]

        result = inject_route_identity_fields(raw_result, task, profile)
        errors = sorted(Draft7Validator(schema).iter_errors(result), key=lambda error: list(error.path))

        self.assertEqual(errors, [], [error.message for error in errors])
        self.assertEqual(result["synthesis_assessment"]["relationship_domain"], "molecular_target")
        self.assertEqual(result["synthesis_results"][0]["relationship_domain"], "molecular_target")
        self.assertEqual(result["synthesis_results"][0]["result_direction"], "not_applicable")

    def test_parse_json_response_handles_fenced_json(self) -> None:
        parsed, method = parse_json_response('```json\\n{"ok": true,}\\n```')

        self.assertEqual(parsed, {"ok": True})
        self.assertEqual(method, "local_cleanup")

    def test_parse_json_response_repairs_literal_control_chars_inside_strings(self) -> None:
        parsed, method = parse_json_response('{"text": "line one\n\tline two"}')

        self.assertEqual(parsed, {"text": "line one\n\tline two"})
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
                    thinking_budget=0,
                    sleep_sec=0.0,
                )
            )
            report_exists = report_json.exists()

        self.assertEqual(report["status"], "dry_run")
        self.assertEqual(report["tasks_selected"], 1)
        self.assertTrue(report_exists)


if __name__ == "__main__":
    unittest.main()
