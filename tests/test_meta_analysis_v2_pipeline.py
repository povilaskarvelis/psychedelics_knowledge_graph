import argparse
import json
from pathlib import Path

from pipeline.extract.build_meta_analysis_v2_tasks import build_tasks, production_cohort
from pipeline.extract import run_meta_analysis_v2_batch_api as batch_api


def article_packet(doi: str) -> dict:
    return {
        "study_doi": doi,
        "packet_id": f"article:{doi}",
        "paper_metadata": {"study_title": "Full meta-analysis", "abstract": "A pooled estimate was reported."},
        "llm_chunks": [
            {
                "chunk_id": "C001",
                "heading": "Results",
                "text": "The pooled standardized mean difference was -0.82.",
            }
        ],
    }


def test_builds_one_task_per_retained_meta_analysis() -> None:
    candidates = [
        {
            "doi": "10.1/full",
            "study_title": "Full",
            "abstract": "Full abstract",
            "retained_for_extraction_candidate": True,
            "primary_secondary_source_type": "meta_analysis",
            "extraction_route_status": "ready_for_article_text_extraction",
        },
        {
            "doi": "10.1/abstract",
            "study_title": "Abstract",
            "abstract": "Visible pooled result",
            "retained_for_extraction_candidate": True,
            "primary_secondary_source_type": "network_meta_analysis",
            "extraction_route_status": "ready_for_abstract_extraction",
        },
        {
            "doi": "10.1/review",
            "retained_for_extraction_candidate": True,
            "primary_secondary_source_type": "systematic_review",
            "extraction_route_status": "ready_for_article_text_extraction",
        },
    ]
    cohort, selection = production_cohort(candidates)
    tasks, report = build_tasks(
        cohort,
        candidates,
        [article_packet("10.1/full")],
        packets_path=Path("packets.jsonl"),
    )

    assert selection["selected"] == 2
    assert [(row["study_doi"], row["text_depth"]) for row in tasks] == [
        ("10.1/abstract", "abstract_only"),
        ("10.1/full", "article_text"),
    ]
    assert report["counts"]["ready_for_model"] == 2
    assert report["by_text_depth"] == {"abstract_only": 1, "article_text": 1}


def test_missing_required_source_is_not_ready() -> None:
    cohort = [{"doi": "10.1/missing", "meta_analysis_type": "meta_analysis", "text_depth": "article_text"}]
    tasks, report = build_tasks(cohort, [], [], packets_path=Path("packets.jsonl"))

    assert tasks[0]["task_status"] == "source_not_ready"
    assert report["by_source_status"] == {"missing_article_packet": 1}


def task(doi: str, text_depth: str, packet_path: Path | None = None) -> dict:
    source = {
        "status": "ready",
        "source_fingerprint": f"fingerprint-{doi}",
        "packet_id": f"article:{doi}" if text_depth == "article_text" else "",
        "packet_path": str(packet_path) if packet_path else "",
    }
    return {
        "task_id": f"task-{doi}",
        "study_doi": doi,
        "text_depth": text_depth,
        "task_status": "ready_for_model",
        "paper_metadata": {
            "study_title": f"Title {doi}",
            "abstract": "The pooled SMD was -0.82. The pooled estimate favored treatment.",
        },
        "source": source,
    }


def prepare_args(tmp_path: Path, tasks_path: Path) -> argparse.Namespace:
    return argparse.Namespace(
        run_id="pilot",
        batch_id="batch_001",
        env_file=str(tmp_path / ".env"),
        model="gemini-3-flash-preview",
        tasks_jsonl=tasks_path,
        batch_size=2,
        full_text_count=1,
        shuffle=True,
        seed=7,
        exclude_output_jsonl=[],
        retry_attempted=False,
        full_text_prompt=batch_api.FULL_TEXT_PROMPT,
        abstract_prompt=batch_api.ABSTRACT_PROMPT,
        output_schema=batch_api.OUTPUT_SCHEMA,
        max_output_tokens=32768,
        thinking_budget=0,
        overwrite=False,
    )


def test_prepare_batch_uses_exact_depth_mix_and_model_only_schema(tmp_path: Path, monkeypatch) -> None:
    packet_path = tmp_path / "packets.jsonl"
    packet_path.write_text(json.dumps(article_packet("10.1/full")) + "\n", encoding="utf-8")
    tasks_path = tmp_path / "tasks.jsonl"
    tasks_path.write_text(
        "\n".join(
            json.dumps(row)
            for row in [
                task("10.1/full", "article_text", packet_path),
                task("10.1/abstract", "abstract_only"),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(batch_api, "DEFAULT_RUN_ROOT", tmp_path / "runs")

    manifest = batch_api.prepare_batch(prepare_args(tmp_path, tasks_path))
    request_rows = [json.loads(line) for line in Path(manifest["outputs"]["requests_jsonl"]).read_text().splitlines()]

    assert manifest["summary"]["prepared_requests"] == 2
    assert manifest["summary"]["by_text_depth"] == {"abstract_only": 1, "article_text": 1}
    assert len(request_rows) == 2

    def schema_has_description_metadata(value: object, *, property_map: bool = False) -> bool:
        if isinstance(value, list):
            return any(schema_has_description_metadata(item) for item in value)
        if isinstance(value, dict):
            if not property_map and "description" in value:
                return True
            return any(
                schema_has_description_metadata(item, property_map=key == "properties")
                for key, item in value.items()
            )
        return False

    for row in request_rows:
        generation_config = row["request"]["generationConfig"]
        model_schema = generation_config["responseJsonSchema"]
        assert "schema_version" not in model_schema["properties"]
        assert "source_depth" not in model_schema["properties"]
        assert not schema_has_description_metadata(model_schema)
        question_properties = model_schema["properties"]["main_questions"]["items"]["properties"]
        assert "description" in question_properties
    abstract_request = next(
        row for row in request_rows if "ABSTRACT_TEXT:" in row["request"]["contents"][0]["parts"][0]["text"]
    )
    locator_enums = []

    def collect_location_enums(value: object) -> None:
        if isinstance(value, list):
            for item in value:
                collect_location_enums(item)
        elif isinstance(value, dict):
            if "location" in value and isinstance(value["location"], dict):
                locator_enums.append(value["location"].get("enum"))
            for item in value.values():
                collect_location_enums(item)

    collect_location_enums(abstract_request["request"]["generationConfig"]["responseJsonSchema"])
    assert locator_enums
    assert all(enum == ["title", "abstract"] for enum in locator_enums)


def test_semantic_qa_flags_invalid_links_and_abstract_locators() -> None:
    result = {
        "extraction_status": "extracted",
        "main_questions": [{"question_id": "Q1"}],
        "synthesis_results": [
            {
                "result_id": "R1",
                "addresses_question_ids": ["Q2"],
                "effect_estimate": {},
                "evidence_locators": [{"location": "results"}],
            }
        ],
        "risk_of_bias_assessments": [],
        "certainty_assessments": [],
        "publication_bias_assessments": [],
        "paper_conclusions": [],
    }

    flags = batch_api.semantic_qa_flags(result, "abstract_only")

    assert "result_links_unknown_questions:R1:Q2" in flags
    assert "empty_optional_object:R1:effect_estimate" in flags
    assert "abstract_result_has_nonabstract_locator:R1" in flags


def test_result_quality_flags_detect_nonverbatim_support_and_statistical_conflict() -> None:
    result = valid_model_result()
    item = result["synthesis_results"][0]
    item["evidence_locators"][0]["supporting_text"] = "Paraphrased evidence"
    item["effect_estimate"] = {
        "metric": "RR",
        "estimate": "1.20",
        "interval_lower": "0.80",
        "interval_upper": "1.80",
        "p_value": "0.20",
    }
    item["interpretation"] = {"finding_direction": "supports"}

    flags = batch_api.result_quality_flags(result, "The pooled RR was 1.20.")

    assert "nonverbatim_supporting_text:R1:1" in flags
    assert "supports_with_p_above_0_05:R1" in flags
    assert "supports_with_interval_including_null:R1" in flags


def test_result_quality_flags_detects_bundled_estimates_ranges_and_derived_numbers() -> None:
    result = valid_model_result()
    item = result["synthesis_results"][0]
    item["relationship_statement"] = "DMT had g = 1.35 for drug use and g = 0.65 for alcohol use."
    item["effect_estimate"] = {
        "metric": "g",
        "estimate": "-1.48 to -2.36",
        "interval_lower": "0.034",
        "interval_upper": "0.638",
    }

    flags = batch_api.result_quality_flags(
        result,
        "DMT had effects for drug and alcohol use. Hedges g was 0.336 ± 0.302.",
    )

    assert "multiple_estimates_in_one_result:R1" in flags
    assert "effect_estimate_is_range:R1" in flags
    assert "numeric_value_not_in_source:R1:estimate" in flags
    assert "numeric_value_not_in_source:R1:interval_lower" in flags
    assert "numeric_value_not_in_source:R1:interval_upper" in flags


def test_abstract_locator_normalization_is_deterministic() -> None:
    result = {
        "synthesis_results": [
            {
                "evidence_locators": [
                    {"location": "results"},
                    {"location": "title"},
                    {"location": "abstract"},
                ]
            }
        ]
    }

    normalized, counts = batch_api.normalize_model_result(result, "abstract_only")

    assert [
        locator["location"]
        for locator in normalized["synthesis_results"][0]["evidence_locators"]
    ] == ["abstract", "title", "abstract"]
    assert counts == {"abstract_evidence_location": 1}
    assert result["synthesis_results"][0]["evidence_locators"][0]["location"] == "results"


def test_full_text_locator_normalization_maps_free_text_to_schema_categories() -> None:
    result = {
        "synthesis_results": [
            {
                "evidence_locators": [
                    {"location": "Conclusions"},
                    {"location": "Assessment of small-study effects"},
                    {"location": "Table 2"},
                ]
            }
        ]
    }

    normalized, counts = batch_api.normalize_model_result(result, "article_text")

    assert [
        locator["location"]
        for locator in normalized["synthesis_results"][0]["evidence_locators"]
    ] == ["conclusion", "results", "table"]
    assert counts == {"full_text_evidence_location": 3}


def test_normalization_omits_missing_markers_and_explicitly_inferred_metrics() -> None:
    result = {
        "meta_analysis_overview": {
            "included_evidence": {
                "participant_count": "Not reported",
                "study_count": "5",
            }
        },
        "synthesis_results": [
            {
                "effect_estimate": {
                    "metric": "Mean difference (implied)",
                    "estimate": "-22.03",
                }
            }
        ],
    }

    normalized, counts = batch_api.normalize_model_result(result, "article_text")

    assert normalized["meta_analysis_overview"]["included_evidence"] == {"study_count": "5"}
    assert normalized["synthesis_results"][0]["effect_estimate"] == {"estimate": "-22.03"}
    assert counts == {
        "omitted_missing_marker": 1,
        "omitted_inferred_effect_metric": 1,
    }


def test_normalization_preserves_required_unreported_assessment_judgments() -> None:
    result = {
        "risk_of_bias_assessments": [
            {
                "scope": "included studies",
                "overall_judgment": "Not reported",
            }
        ],
        "certainty_assessments": [{"rating": "Not reported"}],
        "publication_bias_assessments": [{"result": "Not reported"}],
    }

    normalized, counts = batch_api.normalize_model_result(result, "abstract_only")

    assert normalized == result
    assert counts == {}


def test_normalization_converts_required_nullable_missing_markers_to_null() -> None:
    result = {
        "synthesis_results": [
            {
                "population_or_system": "null",
                "intervention_or_exposure": "Ketamine",
                "comparator": "None",
                "outcome_or_entity": "Depressive symptoms",
                "timepoint_or_window": "not reported",
            }
        ]
    }

    normalized, counts = batch_api.normalize_model_result(result, "abstract_only")

    item = normalized["synthesis_results"][0]
    assert item["population_or_system"] is None
    assert item["comparator"] is None
    assert item["timepoint_or_window"] is None
    assert item["intervention_or_exposure"] == "Ketamine"
    assert counts == {"normalized_nullable_missing_marker": 3}


def test_upsert_replaces_an_earlier_failed_attempt_for_the_same_task(tmp_path: Path) -> None:
    path = tmp_path / "outputs.jsonl"
    batch_api.write_jsonl(
        path,
        [{"task_id": "task-1", "status": "schema_error", "result": {}}],
    )

    batch_api.upsert_rows(
        path,
        [{"task_id": "task-1", "status": "ok", "result": {"value": 1}}],
    )

    assert batch_api.read_jsonl(path) == [
        {"task_id": "task-1", "status": "ok", "result": {"value": 1}}
    ]


def valid_model_result() -> dict:
    return {
        "extraction_status": "extracted",
        "meta_analysis_overview": {
            "synthesis_types": ["pairwise_meta_analysis"],
            "objective_and_scope": "Estimate the pooled treatment effect.",
        },
        "main_questions": [
            {
                "question_id": "Q1",
                "description": "Does the treatment improve the outcome?",
                "importance_in_paper": "main",
            }
        ],
        "synthesis_results": [
            {
                "result_id": "R1",
                "addresses_question_ids": ["Q1"],
                "result_role": "primary_synthesis",
                "importance_in_paper": "main",
                "relationship_statement": "The treatment improved the outcome compared with control.",
                "primary_subject_area": "clinical_outcome",
                "subject_areas": ["clinical_outcome"],
                "evidence_source": "human",
                "population_or_system": "Adults with depression",
                "intervention_or_exposure": "Treatment",
                "comparator": "Control",
                "outcome_or_entity": "Outcome",
                "timepoint_or_window": None,
                "effect_estimate": {"metric": "SMD", "estimate": "-0.82"},
                "interpretation": {"finding_direction": "supports"},
                "evidence_locators": [
                    {
                        "location": "abstract",
                        "locator": "Abstract results",
                        "supporting_text": "The pooled SMD was -0.82.",
                    }
                ],
            }
        ],
        "risk_of_bias_assessments": [],
        "certainty_assessments": [],
        "publication_bias_assessments": [],
        "paper_conclusions": [],
        "overall_limitations": [],
        "warnings": [],
    }


def test_parse_results_adds_deterministic_record_fields_outside_model_result(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(batch_api, "DEFAULT_RUN_ROOT", tmp_path / "runs")
    args = argparse.Namespace(
        run_id="pilot",
        batch_id="batch_001",
        env_file=str(tmp_path / ".env"),
        model="gemini-3-flash-preview",
    )
    paths = batch_api.batch_paths(args)
    paths["snapshot_owner"].mkdir(parents=True, exist_ok=True)
    selected_task = task("10.1/abstract", "abstract_only")
    batch_api.write_jsonl(paths["selected_tasks_jsonl"], [selected_task])
    batch_api.write_jsonl(
        paths["results_jsonl"],
        [
            {
                "key": "pilot-batch_001-000001",
                "response": {
                    "candidates": [
                        {"content": {"parts": [{"text": json.dumps(valid_model_result())}]}}
                    ],
                    "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 20},
                },
            }
        ],
    )
    paths["manifest_json"].write_text(
        json.dumps(
            {
                "records": [
                    {
                        "key": "pilot-batch_001-000001",
                        "task_id": selected_task["task_id"],
                        "study_doi": selected_task["study_doi"],
                        "study_title": selected_task["paper_metadata"]["study_title"],
                        "text_depth": "abstract_only",
                        "source_fingerprint": selected_task["source"]["source_fingerprint"],
                        "model": "gemini-3-flash-preview",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    snapshot_manifest = paths["snapshot_owner"] / "input_snapshot" / "manifest.json"
    snapshot_manifest.parent.mkdir(parents=True, exist_ok=True)
    snapshot_manifest.write_text(
        json.dumps(
            {
                "artifacts": [
                    {
                        "group": "schemas",
                        "archived_path": str(batch_api.OUTPUT_SCHEMA),
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    report = batch_api.parse_results(args)
    output = json.loads(paths["parsed_jsonl"].read_text(encoding="utf-8").splitlines()[0])

    assert report["summary"]["by_status"] == {"ok": 1}
    assert output["schema_version"] == "meta_analysis_evidence_v2"
    assert output["source_depth"] == "abstract_only"
    assert "source_depth" not in output["result"]
    assert output["qa_flags"] == []
