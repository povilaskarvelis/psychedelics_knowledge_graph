import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from pipeline.extract.io_utils import write_json
from pipeline.kg.build_evidence_tables import build_tables
from pipeline.kg.convert_routed_extractions_to_evidence_rows import (
    DEFAULT_ROUTED_RUN_ROOT,
    apply_graph_subject,
    convert_outputs,
    evidence_design_for,
    normalize_primary_controlled_categories,
    normalized_result_direction,
    resolve_output_paths,
)


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


class ConvertRoutedExtractionsToEvidenceRowsTest(unittest.TestCase):
    def test_normalizes_preclinical_session_context_for_human_evidence(self) -> None:
        row = {
            "population_model_category": "human_participants",
            "session_context": "preclinical_experiment",
        }

        normalize_primary_controlled_categories(row)

        self.assertEqual(row["session_context"], "other")
        self.assertIn("human evidence", row["normalization_notes"])

    def test_converts_guideline_recommendation_without_treating_care_component_as_compound(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            tasks_jsonl = root / "tasks.jsonl"
            outputs_jsonl = root / "outputs.jsonl"
            write_jsonl(
                tasks_jsonl,
                [
                    {
                        "task_id": "guideline-task",
                        "route_id": "guideline-route",
                        "study_doi": "10.1000/guideline",
                        "paper_metadata": {
                            "doi": "10.1000/guideline",
                            "study_title": "Guideline for psychedelic care",
                        },
                    }
                ],
            )
            write_jsonl(
                outputs_jsonl,
                [
                    {
                        "task_id": "guideline-task",
                        "route_id": "guideline-route",
                        "status": "ok",
                        "result": {
                            "task_id": "guideline-task",
                            "route_id": "guideline-route",
                            "study_doi": "10.1000/guideline",
                            "domain_route": "intervention_context",
                            "source_type": "guideline",
                            "text_depth": "article_text",
                            "extraction_status": "extracted",
                            "recommendation_assessment": {
                                "relationship_domain": "intervention_context",
                                "population_or_system": "clinical services",
                            },
                            "recommendation_items": [
                                {
                                    "compound_or_class": "Psilocybin",
                                    "entity_type": "intervention_component",
                                    "entity": "Adverse event monitoring",
                                    "recommendation_type": "monitoring",
                                    "recommendation_strength": "recommended",
                                    "recommendation_statement": "Services should monitor adverse events.",
                                    "direction_or_tone": "supports",
                                }
                            ],
                        },
                    }
                ],
            )

            rows, report = convert_outputs(input_jsonl=outputs_jsonl, tasks_jsonl=tasks_jsonl)

        self.assertEqual(report["rows_written"], 1)
        self.assertEqual(rows[0]["source_item_type"], "recommendation_item")
        self.assertEqual(rows[0]["paper_type"], "guideline")
        self.assertEqual(rows[0]["compound"], "Psilocybin")
        self.assertEqual(rows[0]["graph_entity_label"], "Adverse event monitoring")
        self.assertEqual(rows[0]["kg_entity_kind_override"], "intervention_component")

    def test_complete_non_atomic_exposure_supersedes_focal_compound(self) -> None:
        row = {
            "compound": "Ketamine (as part of chemsex substances)",
            "dose_or_regimen": "Use of methamphetamine, mephedrone, GHB/GBL, and/or ketamine in a sexual setting",
        }

        apply_graph_subject(row)

        self.assertEqual(
            row["compound"],
            "Use of methamphetamine, mephedrone, GHB/GBL, and/or ketamine in a sexual setting",
        )
        self.assertEqual(row["atomic_compound_candidate"], "Ketamine (as part of chemsex substances)")
        self.assertEqual(row["graph_subject_kind"], "exposure_context")
        self.assertEqual(row["graph_subject_source_field"], "dose_or_regimen")

    def test_atomic_compound_remains_atomic_when_regimen_is_ordinary_dosing(self) -> None:
        row = {"compound": "Ketamine", "dose_or_regimen": "0.5 mg/kg intravenous infusion"}

        apply_graph_subject(row)

        self.assertEqual(row["compound"], "Ketamine")
        self.assertEqual(row["graph_subject_kind"], "atomic_compound")

        stereochemical = {"compound": "S(+)-ketamine"}
        apply_graph_subject(stereochemical)
        self.assertEqual(stereochemical["graph_subject_kind"], "atomic_compound")

        chemical_name = {"compound": "N,N-dimethyltryptamine (DMT)"}
        apply_graph_subject(chemical_name)
        self.assertEqual(chemical_name["graph_subject_kind"], "atomic_compound")

        hyphenated_chemical_name = {"compound": "N,N-dimethyl-tryptamine (DMT)"}
        apply_graph_subject(hyphenated_chemical_name)
        self.assertEqual(hyphenated_chemical_name["graph_subject_kind"], "atomic_compound")

        substituted_chemical_name = {"compound": "5-methoxy-N,N-dimethyl tryptamine (5-MeO-DMT)"}
        apply_graph_subject(substituted_chemical_name)
        self.assertEqual(substituted_chemical_name["graph_subject_kind"], "atomic_compound")

        dose_regimen = {"compound": "MDMA (75 mg and 125 mg)"}
        apply_graph_subject(dose_regimen)
        self.assertEqual(dose_regimen["graph_subject_kind"], "treatment_regimen")

    def test_predictor_phrase_does_not_replace_extracted_atomic_compound(self) -> None:
        row = {
            "compound": "ecstasy",
            "exposure_or_policy": "Perceived control over obtaining and using ecstasy",
        }

        apply_graph_subject(row)

        self.assertEqual(row["compound"], "ecstasy")
        self.assertEqual(row["graph_subject_label"], "ecstasy")
        self.assertEqual(row["graph_subject_kind"], "atomic_compound")

    def test_graph_subject_normalization_is_idempotent(self) -> None:
        row = {
            "compound": "Ketamine (as part of chemsex substances)",
            "dose_or_regimen": "Use of methamphetamine, mephedrone, GHB/GBL, and/or ketamine in a sexual setting",
        }

        apply_graph_subject(row)
        apply_graph_subject(row)

        self.assertEqual(row["atomic_compound_candidate"], "Ketamine (as part of chemsex substances)")
        self.assertEqual(row["graph_subject_kind"], "exposure_context")
        self.assertEqual(
            row["compound"],
            "Use of methamphetamine, mephedrone, GHB/GBL, and/or ketamine in a sexual setting",
        )

    def test_explicit_review_subject_kind_is_preserved_when_label_has_no_regex_cue(self) -> None:
        row = {
            "compound": "Microdosing",
            "graph_subject_label": "Microdosing",
            "graph_subject_kind": "exposure_context",
            "graph_subject_source_field": "anchors",
        }

        apply_graph_subject(row)

        self.assertEqual(row["compound"], "Microdosing")
        self.assertEqual(row["graph_subject_kind"], "exposure_context")
        self.assertEqual(row["graph_subject_source_field"], "anchors")

        topic = {
            "compound": "Research landscape",
            "graph_subject_label": "Research landscape",
            "graph_subject_kind": "paper_topic",
        }
        apply_graph_subject(topic)
        self.assertEqual(topic["graph_subject_kind"], "paper_topic")

    def test_direction_and_design_are_normalized_without_rewriting_raw_text(self) -> None:
        self.assertEqual(normalized_result_direction("No significant association"), "no_association")
        self.assertEqual(
            evidence_design_for({"study_design": "Cross-sectional online survey"}),
            "observational",
        )

    def test_run_id_resolves_converter_outputs_to_versioned_directory(self) -> None:
        args = resolve_output_paths(
            SimpleNamespace(
                run_id="gemini 3 flash batch",
                run_dir="",
                out_json="",
                report_json="",
            )
        )

        self.assertEqual(args.run_id, "gemini_3_flash_batch")
        self.assertEqual(Path(args.out_json), DEFAULT_ROUTED_RUN_ROOT / "gemini_3_flash_batch" / "routed_evidence_rows.json")
        self.assertEqual(
            Path(args.report_json),
            DEFAULT_ROUTED_RUN_ROOT / "gemini_3_flash_batch" / "routed_evidence_rows_report.json",
        )

    def test_run_dir_resolves_versioned_extraction_inputs_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir) / "versioned_run"
            run_dir.mkdir()
            outputs = run_dir / "route_extraction_outputs.jsonl"
            tasks = run_dir / "route_extraction_tasks.jsonl"
            outputs.write_text("\n", encoding="utf-8")
            tasks.write_text("\n", encoding="utf-8")

            args = resolve_output_paths(
                SimpleNamespace(
                    run_id="versioned_run",
                    run_dir=str(run_dir),
                    input_jsonl=Path("data/processed/extraction/route_extraction_outputs.jsonl").resolve(),
                    tasks_jsonl=Path("data/processed/extraction/route_extraction_tasks.jsonl").resolve(),
                    out_json="",
                    report_json="",
                )
            )

        self.assertEqual(Path(args.input_jsonl), outputs)
        self.assertEqual(Path(args.tasks_jsonl), tasks)

    def test_active_route_table_filters_stale_extraction_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            tasks_jsonl = root / "tasks.jsonl"
            outputs_jsonl = root / "outputs.jsonl"
            active_routes = root / "paper_extraction_routes.parquet"
            write_jsonl(
                tasks_jsonl,
                [
                    {
                        "task_id": "active-task",
                        "route_id": "active-route",
                        "study_doi": "10.1000/active",
                        "paper_metadata": {"doi": "10.1000/active", "study_title": "Active paper"},
                    },
                    {
                        "task_id": "stale-task",
                        "route_id": "stale-route",
                        "study_doi": "10.1000/stale",
                        "paper_metadata": {"doi": "10.1000/stale", "study_title": "Stale paper"},
                    },
                ],
            )
            write_jsonl(
                outputs_jsonl,
                [
                    {
                        "task_id": "active-task",
                        "route_id": "active-route",
                        "status": "ok",
                        "result": {
                            "task_id": "active-task",
                            "route_id": "active-route",
                            "study_doi": "10.1000/active",
                            "domain_route": "clinical_outcome",
                            "source_type": "primary",
                            "paper_type": "primary",
                            "text_depth": "abstract_only",
                            "extraction_status": "extracted",
                            "items": [{"compound": "Psilocybin", "condition_or_indication": "Depression"}],
                        },
                    },
                    {
                        "task_id": "stale-task",
                        "route_id": "stale-route",
                        "status": "ok",
                        "result": {
                            "task_id": "stale-task",
                            "route_id": "stale-route",
                            "study_doi": "10.1000/stale",
                            "domain_route": "clinical_outcome",
                            "source_type": "primary",
                            "paper_type": "primary",
                            "text_depth": "abstract_only",
                            "extraction_status": "extracted",
                            "items": [{"compound": "Ketamine", "condition_or_indication": "Depression"}],
                        },
                    },
                ],
            )
            pd.DataFrame(
                [
                    {
                        "route_id": "active-route",
                        "doi": "10.1000/active",
                        "domain_route": "clinical_outcome",
                        "route_action": "extract_from_abstract_only",
                    }
                ]
            ).to_parquet(active_routes, index=False)

            rows, report = convert_outputs(
                input_jsonl=outputs_jsonl,
                tasks_jsonl=tasks_jsonl,
                active_route_table=active_routes,
            )

        self.assertEqual([row["study_doi"] for row in rows], ["10.1000/active"])
        self.assertEqual(report["rows_written"], 1)
        self.assertEqual(report["skipped"]["inactive_current_route"], 1)

    def test_same_doi_and_domain_do_not_rescue_changed_route_or_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            tasks_jsonl = root / "tasks.jsonl"
            outputs_jsonl = root / "outputs.jsonl"
            active_routes = root / "paper_extraction_routes.parquet"
            current_fingerprint = "a" * 64
            write_jsonl(
                tasks_jsonl,
                [
                    {
                        "task_id": "current-task",
                        "route_id": "current-abstract-route",
                        "input_fingerprint": current_fingerprint,
                        "study_doi": "10.1000/same-paper",
                        "paper_metadata": {"doi": "10.1000/same-paper"},
                        "route_context": {"domain_route": "clinical_outcome"},
                        "extraction_contract": {"domain_route": "clinical_outcome"},
                        "text_source": {"mode": "abstract"},
                    }
                ],
            )
            write_jsonl(
                outputs_jsonl,
                [
                    {
                        "task_id": "old-fulltext-task",
                        "route_id": "old-fulltext-route",
                        "input_fingerprint": "b" * 64,
                        "status": "ok",
                        "result": {
                            "task_id": "old-fulltext-task",
                            "route_id": "old-fulltext-route",
                            "input_fingerprint": "b" * 64,
                            "study_doi": "10.1000/same-paper",
                            "domain_route": "clinical_outcome",
                            "text_depth": "article_text",
                            "extraction_status": "extracted",
                            "items": [
                                {"compound": "Ketamine", "condition_or_indication": "Depression"}
                            ],
                        },
                    }
                ],
            )
            pd.DataFrame(
                [
                    {
                        "route_id": "current-abstract-route",
                        "doi": "10.1000/same-paper",
                        "domain_route": "clinical_outcome",
                        "route_action": "extract_from_abstract_only",
                    }
                ]
            ).to_parquet(active_routes, index=False)

            rows, report = convert_outputs(
                input_jsonl=outputs_jsonl,
                tasks_jsonl=tasks_jsonl,
                active_route_table=active_routes,
                allow_stable_task_fallback=True,
            )

        self.assertEqual(rows, [])
        self.assertEqual(
            report["skipped"]["current_task_mismatch:text_depth_mismatch"],
            1,
        )

    def test_stable_fallback_reuses_output_when_doi_domain_and_depth_are_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            tasks_jsonl = root / "tasks.jsonl"
            outputs_jsonl = root / "outputs.jsonl"
            active_routes = root / "paper_extraction_routes.parquet"
            write_jsonl(
                tasks_jsonl,
                [
                    {
                        "task_id": "current-task",
                        "route_id": "current-route",
                        "input_fingerprint": "a" * 64,
                        "study_doi": "10.1000/stable-paper",
                        "paper_metadata": {
                            "doi": "10.1000/stable-paper",
                            "study_title": "Current canonical title",
                        },
                        "route_context": {"domain_route": "clinical_outcome"},
                        "extraction_contract": {"domain_route": "clinical_outcome"},
                        "text_source": {"mode": "abstract"},
                    }
                ],
            )
            write_jsonl(
                outputs_jsonl,
                [
                    {
                        "task_id": "old-task",
                        "route_id": "old-route",
                        "input_fingerprint": "b" * 64,
                        "status": "ok",
                        "result": {
                            "task_id": "old-task",
                            "route_id": "old-route",
                            "study_doi": "10.1000/stable-paper",
                            "domain_route": "clinical_outcome",
                            "text_depth": "abstract_only",
                            "extraction_status": "extracted",
                            "items": [
                                {
                                    "compound": "Psilocybin",
                                    "condition_or_indication": "Depression",
                                }
                            ],
                        },
                    }
                ],
            )
            pd.DataFrame(
                [
                    {
                        "route_id": "current-route",
                        "doi": "10.1000/stable-paper",
                        "domain_route": "clinical_outcome",
                    }
                ]
            ).to_parquet(active_routes, index=False)

            rows, report = convert_outputs(
                input_jsonl=outputs_jsonl,
                tasks_jsonl=tasks_jsonl,
                active_route_table=active_routes,
                allow_stable_task_fallback=True,
            )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["study_title"], "Current canonical title")
        self.assertEqual(report["counts"]["outputs_matched_by_stable_doi_domain"], 1)

    def test_current_task_rejects_mismatched_text_depth_and_fingerprint(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            tasks_jsonl = root / "tasks.jsonl"
            outputs_jsonl = root / "outputs.jsonl"
            fingerprint = "a" * 64
            write_jsonl(
                tasks_jsonl,
                [
                    {
                        "task_id": "current-task",
                        "route_id": "current-route",
                        "input_fingerprint": fingerprint,
                        "study_doi": "10.1000/current",
                        "paper_metadata": {"doi": "10.1000/current"},
                        "route_context": {"domain_route": "clinical_outcome"},
                        "extraction_contract": {"domain_route": "clinical_outcome"},
                        "text_source": {"mode": "abstract"},
                    }
                ],
            )
            write_jsonl(
                outputs_jsonl,
                [
                    {
                        "task_id": "current-task",
                        "route_id": "current-route",
                        "input_fingerprint": "b" * 64,
                        "status": "ok",
                        "result": {
                            "task_id": "current-task",
                            "route_id": "current-route",
                            "input_fingerprint": "b" * 64,
                            "study_doi": "10.1000/current",
                            "domain_route": "clinical_outcome",
                            "text_depth": "article_text",
                            "extraction_status": "extracted",
                            "items": [
                                {"compound": "Ketamine", "condition_or_indication": "Depression"}
                            ],
                        },
                    }
                ],
            )

            rows, report = convert_outputs(
                input_jsonl=outputs_jsonl,
                tasks_jsonl=tasks_jsonl,
            )

        self.assertEqual(rows, [])
        self.assertEqual(
            report["skipped"]["current_task_mismatch:input_fingerprint_mismatch"],
            1,
        )

    def test_review_coverage_filters_peripheral_mentions(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            tasks_jsonl = root / "tasks.jsonl"
            outputs_jsonl = root / "outputs.jsonl"
            write_jsonl(
                tasks_jsonl,
                [
                    {
                        "task_id": "review-intervention",
                        "route_id": "review-intervention",
                        "study_doi": "10.1000/review-intervention",
                        "paper_metadata": {
                            "doi": "10.1000/review-intervention",
                            "study_title": "MDMA therapy model review",
                            "study_year": "2026",
                        },
                    }
                ],
            )
            write_jsonl(
                outputs_jsonl,
                [
                    {
                        "task_id": "review-intervention",
                        "route_id": "review-intervention",
                        "prompt_profile": "secondary_review_coverage",
                        "schema_profile": "review_coverage_schema",
                        "status": "ok",
                        "result": {
                            "schema_version": "review_coverage_v1",
                            "task_id": "review-intervention",
                            "route_id": "review-intervention",
                            "study_doi": "10.1000/review-intervention",
                            "domain_route": "intervention_context",
                            "source_type": "narrative_review",
                            "text_depth": "article_text",
                            "extraction_status": "extracted",
                            "coverage_items": [
                                {
                                    "item_id": "R1",
                                    "relationship_domain": "intervention_context",
                                    "coverage_type": "summarizes",
                                    "coverage_focus": "main_focus",
                                    "compound_or_class": "MDMA",
                                    "entity_type": "intervention_component",
                                    "entity": "Inner Healing Intelligence model",
                                    "summary_statement": "The review centers a participant-led healing model.",
                                    "direction_or_tone": "supports",
                                    "confidence": 0.95,
                                    "needs_human_review": False,
                                },
                                {
                                    "item_id": "R2",
                                    "relationship_domain": "intervention_context",
                                    "coverage_type": "discusses",
                                    "coverage_focus": "substantial_topic",
                                    "compound_or_class": "MDMA",
                                    "entity_type": "intervention_component",
                                    "entity": "Therapeutic Witnessing",
                                    "summary_statement": "The review discusses witnessing as a therapist stance.",
                                    "direction_or_tone": "supports",
                                    "confidence": 0.9,
                                    "needs_human_review": False,
                                },
                                {
                                    "item_id": "R3",
                                    "relationship_domain": "intervention_context",
                                    "coverage_type": "mentions",
                                    "coverage_focus": "brief_context",
                                    "compound_or_class": "MDMA",
                                    "entity_type": "intervention_component",
                                    "entity": "Music and eye shades",
                                    "summary_statement": "Music and eye shades are mentioned in one protocol sentence.",
                                    "direction_or_tone": "descriptive_only",
                                    "confidence": 0.85,
                                    "needs_human_review": False,
                                },
                                {
                                    "item_id": "R4",
                                    "relationship_domain": "intervention_context",
                                    "coverage_type": "methodological_context",
                                    "coverage_focus": "substantial_topic",
                                    "compound_or_class": "MDMA",
                                    "entity_type": "intervention_component",
                                    "entity": "manual description",
                                    "summary_statement": "The paper describes background manual procedures.",
                                    "direction_or_tone": "descriptive_only",
                                    "confidence": 0.75,
                                    "needs_human_review": False,
                                },
                            ],
                        },
                    }
                ],
            )

            rows, report = convert_outputs(input_jsonl=outputs_jsonl, tasks_jsonl=tasks_jsonl)

        self.assertEqual(report["rows_written"], 2)
        self.assertEqual(report["skipped"]["review_coverage_focus:brief_context"], 1)
        self.assertEqual(report["skipped"]["review_coverage_type:methodological_context"], 1)
        self.assertEqual(
            [(row["graph_entity_label"], row["coverage_focus"], row["coverage_type"]) for row in rows],
            [
                ("Inner Healing Intelligence model", "main_focus", "summarizes"),
                ("Therapeutic Witnessing", "substantial_topic", "discusses"),
            ],
        )

    def test_clinical_review_condition_context_wins_over_symptom_entity_type(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            tasks_jsonl = root / "tasks.jsonl"
            outputs_jsonl = root / "outputs.jsonl"
            write_jsonl(
                tasks_jsonl,
                [
                    {
                        "task_id": "review-clinical",
                        "route_id": "review-clinical",
                        "study_doi": "10.1000/review-clinical",
                        "paper_metadata": {
                            "doi": "10.1000/review-clinical",
                            "study_title": "Clinical review",
                            "study_year": "2026",
                        },
                    }
                ],
            )
            write_jsonl(
                outputs_jsonl,
                [
                    {
                        "task_id": "review-clinical",
                        "route_id": "review-clinical",
                        "prompt_profile": "secondary_review_coverage",
                        "schema_profile": "review_coverage_schema",
                        "status": "ok",
                        "result": {
                            "schema_version": "review_coverage_v1",
                            "task_id": "review-clinical",
                            "route_id": "review-clinical",
                            "study_doi": "10.1000/review-clinical",
                            "domain_route": "clinical_outcome",
                            "source_type": "systematic_review",
                            "text_depth": "article_text",
                            "extraction_status": "extracted",
                            "coverage_items": [
                                {
                                    "item_id": "C1",
                                    "relationship_domain": "clinical_outcome",
                                    "coverage_type": "reviews",
                                    "coverage_focus": "main_focus",
                                    "compound_or_class": "LSD",
                                    "entity_type": "symptom_or_outcome",
                                    "entity": "anxiety associated with life-threatening diseases",
                                    "population_or_system": "patients with life-threatening diseases",
                                    "summary_statement": "The review covers LSD-assisted psychotherapy for anxiety in life-threatening disease.",
                                    "direction_or_tone": "supports",
                                    "confidence": 0.9,
                                    "needs_human_review": False,
                                    "domain_result": {
                                        "condition_or_population": "life-threatening diseases with anxiety",
                                        "compound_or_intervention": "LSD",
                                        "clinical_endpoint": "anxiety",
                                    },
                                }
                            ],
                        },
                    }
                ],
            )

            rows, report = convert_outputs(input_jsonl=outputs_jsonl, tasks_jsonl=tasks_jsonl)

        self.assertEqual(report["rows_written"], 1)
        self.assertEqual(rows[0]["kg_entity_kind_override"], "condition_indication")
        self.assertEqual(rows[0]["graph_entity_label"], "anxiety associated with life-threatening diseases")

    def test_preserves_domain_specific_fields_as_ui_facing_aliases(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            tasks_jsonl = root / "tasks.jsonl"
            outputs_jsonl = root / "outputs.jsonl"
            write_jsonl(
                tasks_jsonl,
                [
                    {
                        "task_id": "clinical",
                        "route_id": "clinical",
                        "study_doi": "10.1000/clinical",
                        "paper_metadata": {
                            "doi": "10.1000/clinical",
                            "study_title": "Clinical trial",
                            "study_year": "2025",
                        },
                    },
                    {
                        "task_id": "target",
                        "route_id": "target",
                        "study_doi": "10.1000/target",
                        "paper_metadata": {
                            "doi": "10.1000/target",
                            "study_title": "Target study",
                            "study_year": "2025",
                        },
                    },
                    {
                        "task_id": "cognition",
                        "route_id": "cognition",
                        "study_doi": "10.1000/cognition",
                        "paper_metadata": {
                            "doi": "10.1000/cognition",
                            "study_title": "Cognitive flexibility study",
                            "study_year": "2025",
                        },
                    },
                    {
                        "task_id": "pathway",
                        "route_id": "pathway",
                        "study_doi": "10.1000/pathway",
                        "paper_metadata": {
                            "doi": "10.1000/pathway",
                            "study_title": "Neuroplasticity study",
                            "study_year": "2025",
                        },
                    },
                    {
                        "task_id": "meta",
                        "route_id": "meta",
                        "study_doi": "10.1000/meta",
                        "paper_metadata": {
                            "doi": "10.1000/meta",
                            "study_title": "Clinical meta-analysis",
                            "study_year": "2025",
                        },
                    },
                ],
            )
            write_jsonl(
                outputs_jsonl,
                [
                    {
                        "task_id": "clinical",
                        "route_id": "clinical",
                        "status": "ok",
                        "result": {
                            "task_id": "clinical",
                            "route_id": "clinical",
                            "study_doi": "10.1000/clinical",
                            "domain_route": "clinical_outcome",
                            "source_type": "primary",
                            "paper_type": "primary",
                            "text_depth": "article_text",
                            "extraction_status": "extracted",
                            "items": [
                                {
                                    "compound_or_intervention": "Psilocybin",
                                    "condition_or_population": "Adults with treatment-resistant depression",
                                    "condition_or_indication": "Treatment-resistant depression",
                                    "population_or_subgroup": "Adults",
                                    "population_model_category": "clinical_population",
                                    "study_design_category": "rct",
                                    "administration_route": "oral",
                                    "dosing_schedule": "single_dose",
                                    "session_context": "clinical_administration",
                                    "sample_size": "80",
                                    "comparator_or_context": "Placebo",
                                    "dose_or_regimen": "25 mg oral psilocybin",
                                    "outcome_measure_or_instrument": "MADRS",
                                    "time_window": "6 weeks",
                                    "effect_or_statistic": "mean difference -6.6",
                                    "primary_graph_anchor_kind": "condition_indication",
                                }
                            ],
                        },
                    },
                    {
                        "task_id": "target",
                        "route_id": "target",
                        "status": "ok",
                        "result": {
                            "task_id": "target",
                            "route_id": "target",
                            "study_doi": "10.1000/target",
                            "domain_route": "molecular_target",
                            "source_type": "primary",
                            "paper_type": "primary",
                            "text_depth": "article_text",
                            "extraction_status": "extracted",
                            "items": [
                                {
                                    "compound": "LSD",
                                    "target": "5-HT2A receptor",
                                    "metric": "Ki",
                                    "value": "2.9",
                                    "unit": "nM",
                                    "assay_or_method": "radioligand binding",
                                    "model_system": "HEK293 cells",
                                    "species_or_cell_line": "human cell line",
                                }
                            ],
                        },
                    },
                    {
                        "task_id": "cognition",
                        "route_id": "cognition",
                        "status": "ok",
                        "result": {
                            "task_id": "cognition",
                            "route_id": "cognition",
                            "study_doi": "10.1000/cognition",
                            "domain_route": "cognitive_behavioral",
                            "source_type": "primary",
                            "paper_type": "primary",
                            "text_depth": "article_text",
                            "extraction_status": "extracted",
                            "items": [
                                {
                                    "compound_or_exposure": "Psilocybin",
                                    "graph_construct_label": "Cognitive flexibility",
                                    "construct_family": "cognition",
                                    "raw_task_or_measure": "reversal learning task",
                                    "population_model_category": "human_participants",
                                    "study_design_category": "rct",
                                    "effect_or_statistic": "improved performance",
                                }
                            ],
                        },
                    },
                    {
                        "task_id": "pathway",
                        "route_id": "pathway",
                        "status": "ok",
                        "result": {
                            "task_id": "pathway",
                            "route_id": "pathway",
                            "study_doi": "10.1000/pathway",
                            "domain_route": "molecular_pathway_readout",
                            "source_type": "primary",
                            "paper_type": "primary",
                            "text_depth": "article_text",
                            "extraction_status": "extracted",
                            "items": [
                                {
                                    "compound_or_exposure": "Psilocybin",
                                    "pathway_or_readout": "BDNF protein level",
                                    "molecular_effect_category": "Neuroplasticity",
                                    "specific_readout_or_marker": "BDNF",
                                    "mechanistic_relationship_type": "plasticity_marker",
                                    "experimental_system_category": "clinical",
                                    "population_model_category": "healthy_volunteers",
                                    "study_design_category": "rct",
                                    "assay_or_method": "ELISA",
                                }
                            ],
                        },
                    },
                    {
                        "task_id": "meta",
                        "route_id": "meta",
                        "status": "ok",
                        "result": {
                            "task_id": "meta",
                            "route_id": "meta",
                            "study_doi": "10.1000/meta",
                            "domain_route": "clinical_outcome",
                            "source_type": "meta_analysis",
                            "text_depth": "article_text",
                            "extraction_status": "extracted",
                            "included_evidence_summary": {
                                "included_study_count": "7",
                                "included_participant_count": "512",
                            },
                            "synthesis_results": [
                                {
                                    "compound_or_class": "Ketamine",
                                    "entity": "depressive symptoms",
                                    "entity_type": "symptom_problem",
                                    "effect_size": "SMD -0.8",
                                    "domain_result": {
                                        "condition_or_population": "Adults with depression",
                                        "outcome_measure": "depression scales",
                                    },
                                }
                            ],
                        },
                    },
                ],
            )

            rows, report = convert_outputs(input_jsonl=outputs_jsonl, tasks_jsonl=tasks_jsonl)

        self.assertEqual(report["rows_written"], 5)
        clinical = next(row for row in rows if row["study_doi"] == "10.1000/clinical")
        self.assertEqual(clinical["graph_entity_label"], "Treatment-resistant depression")
        self.assertEqual(clinical["clinical_context_condition"], "Treatment-resistant depression")
        self.assertEqual(clinical["population"], "Adults")
        self.assertEqual(clinical["population_model_category"], "clinical_population")
        self.assertEqual(clinical["study_design_category"], "rct")
        self.assertEqual(clinical["administration_route"], "oral")
        self.assertEqual(clinical["dosing_schedule"], "single_dose")
        self.assertEqual(clinical["session_context"], "clinical_administration")
        self.assertEqual(clinical["route"], "oral")
        self.assertEqual(clinical["sample_size_total"], "80")
        self.assertEqual(clinical["comparator"], "Placebo")
        self.assertEqual(clinical["dose"], "25 mg oral psilocybin")
        self.assertEqual(clinical["outcome_measure"], "MADRS")
        self.assertEqual(clinical["follow_up_duration"], "6 weeks")
        self.assertEqual(clinical["effect_size"], "mean difference -6.6")

        target = next(row for row in rows if row["study_doi"] == "10.1000/target")
        self.assertEqual(target["affinity_type"], "Ki")
        self.assertEqual(target["affinity_value"], "2.9")
        self.assertEqual(target["affinity_unit"], "nM")
        self.assertEqual(target["assay_type"], "radioligand binding")
        self.assertEqual(target["model_or_system"], "HEK293 cells")
        self.assertEqual(target["species"], "human cell line")

        cognition = next(row for row in rows if row["study_doi"] == "10.1000/cognition")
        self.assertEqual(cognition["graph_entity_label"], "Cognitive flexibility")
        self.assertEqual(cognition["cognitive_behavioral_graph_label"], "Cognitive flexibility")
        self.assertEqual(cognition["outcome_measure"], "reversal learning task")
        self.assertEqual(cognition["construct_family"], "cognition")

        pathway = next(row for row in rows if row["study_doi"] == "10.1000/pathway")
        self.assertEqual(pathway["graph_entity_label"], "BDNF")
        self.assertEqual(pathway["kg_entity_kind_override"], "biomarker_readout")
        self.assertEqual(pathway["molecular_effect_label"], "Neuroplasticity")
        self.assertEqual(pathway["readout"], "BDNF")
        self.assertEqual(pathway["mechanistic_relationship_type"], "plasticity_marker")
        self.assertEqual(pathway["system"], "clinical")

        meta = next(row for row in rows if row["study_doi"] == "10.1000/meta")
        self.assertEqual(meta["included_study_count"], "7")
        self.assertEqual(meta["included_participant_count"], "512")
        self.assertEqual(meta["sample_size_total"], "512")

    def test_converts_routed_outputs_into_rows_consumed_by_kg_builder(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            tasks_jsonl = root / "tasks.jsonl"
            outputs_jsonl = root / "route_outputs.jsonl"
            evidence_rows_json = root / "routed_evidence_rows.json"
            registry_path = root / "registry.json"
            out_dir = root / "kg"

            write_jsonl(
                tasks_jsonl,
                [
                    {
                        "task_id": "route-brain",
                        "route_id": "route-brain",
                        "study_doi": "10.1000/brain-route",
                        "paper_metadata": {
                            "doi": "10.1000/brain-route",
                            "study_title": "Psilocybin and default mode network connectivity",
                            "study_year": "2025",
                            "study_journal": "Neuropsychopharmacology",
                        },
                    },
                    {
                        "task_id": "route-pk",
                        "route_id": "route-pk",
                        "study_doi": "10.1000/pk-route",
                        "paper_metadata": {
                            "doi": "10.1000/pk-route",
                            "study_title": "DMT pharmacokinetics meta-analysis",
                            "study_year": "2024",
                        },
                    },
                    {
                        "task_id": "route-public-health",
                        "route_id": "route-public-health",
                        "study_doi": "10.1000/public-health-route",
                        "paper_metadata": {
                            "doi": "10.1000/public-health-route",
                            "study_title": "Equity in psychedelic services",
                            "study_year": "2023",
                        },
                    },
                    {
                        "task_id": "route-pathway",
                        "route_id": "route-pathway",
                        "study_doi": "10.1000/pathway-route",
                        "paper_metadata": {
                            "doi": "10.1000/pathway-route",
                            "study_title": "Psilocybin and BDNF",
                            "study_year": "2025",
                        },
                    },
                ],
            )
            write_jsonl(
                outputs_jsonl,
                [
                    {
                        "task_id": "route-brain",
                        "route_id": "route-brain",
                        "prompt_profile": "primary_brain_system",
                        "schema_profile": "primary_evidence_schema",
                        "status": "ok",
                        "schema_errors": [],
                        "result": {
                            "schema_version": "primary_brain_system_v1",
                            "task_id": "route-brain",
                            "route_id": "route-brain",
                            "study_doi": "10.1000/brain-route",
                            "domain_route": "brain_system",
                            "source_type": "primary_or_unclear",
                            "paper_type": "primary_study",
                            "text_depth": "article_text",
                            "extraction_status": "extracted",
                            "items": [
                                {
                                    "compound_or_exposure": "Psilocybin",
                                    "population_or_system": "adults",
                                    "sample_size": "60",
                                    "study_design": "randomized trial",
                                    "primary_graph_anchor_kind": "brain_network",
                                    "brain_network": "DMN",
                                    "readout": "functional connectivity",
                                    "assessment_timepoint": "2 hours post-dose",
                                    "finding_summary": "Psilocybin altered default mode network connectivity.",
                                    "evidence_location": "text",
                                    "evidence_locator": "Results",
                                }
                            ],
                            "warnings": [],
                        },
                    },
                    {
                        "task_id": "route-pk",
                        "route_id": "route-pk",
                        "prompt_profile": "secondary_meta_analysis",
                        "schema_profile": "meta_analysis_evidence_schema",
                        "status": "ok",
                        "schema_errors": [],
                        "result": {
                            "schema_version": "meta_analysis_evidence_v1",
                            "task_id": "route-pk",
                            "route_id": "route-pk",
                            "study_doi": "10.1000/pk-route",
                            "domain_route": "pharmacokinetics_exposure",
                            "source_type": "meta_analysis",
                            "text_depth": "article_text",
                            "extraction_status": "extracted",
                            "synthesis_results": [
                                {
                                    "result_id": "PK1",
                                    "relationship_domain": "pharmacokinetics_exposure",
                                    "compound_or_class": "DMT",
                                    "entity_type": "target",
                                    "entity": "MAO-A",
                                    "effect_size": "qualitative",
                                    "confidence": 0.86,
                                    "needs_human_review": False,
                                    "domain_result": {
                                        "compound_or_analyte": "DMT",
                                        "primary_graph_anchor_kind": "target",
                                        "metabolic_or_transport_target": "MAO-A",
                                        "pk_or_exposure_parameter": "metabolism",
                                        "synthesis_interpretation": "MAO-A is central to DMT exposure.",
                                    },
                                }
                            ],
                        },
                    },
                    {
                        "task_id": "route-public-health",
                        "route_id": "route-public-health",
                        "prompt_profile": "secondary_review_coverage",
                        "schema_profile": "review_coverage_schema",
                        "status": "ok",
                        "schema_errors": [],
                        "result": {
                            "schema_version": "review_coverage_v1",
                            "task_id": "route-public-health",
                            "route_id": "route-public-health",
                            "study_doi": "10.1000/public-health-route",
                            "domain_route": "real_world_public_health",
                            "source_type": "review",
                            "text_depth": "abstract_only",
                            "extraction_status": "extracted",
                            "coverage_items": [
                                {
                                    "item_id": "PH1",
                                    "relationship_domain": "real_world_public_health",
                                    "coverage_type": "reviews",
                                    "coverage_focus": "main_focus",
                                    "compound_or_class": "Psilocybin",
                                    "entity_type": "public_health_measure",
                                    "entity": "ethnoracial inclusion",
                                    "summary_statement": "The review covers equity concerns in psychedelic services.",
                                    "direction_or_tone": "descriptive_only",
                                    "study_count": "not_reported",
                                    "confidence": 0.78,
                                    "needs_human_review": False,
                                    "domain_result": {
                                        "exposure_or_intervention": "Psilocybin",
                                        "public_health_measure": "ethnoracial inclusion",
                                        "public_health_topic_category": "access and equity",
                                        "review_interpretation": "Equity is a main public-health topic in the review.",
                                    },
                                }
                            ],
                        },
                    },
                    {
                        "task_id": "route-pathway",
                        "route_id": "route-pathway",
                        "prompt_profile": "primary_molecular_pathway_readout",
                        "schema_profile": "primary_evidence_schema",
                        "status": "ok",
                        "schema_errors": [],
                        "result": {
                            "schema_version": "primary_molecular_pathway_readout_v1",
                            "task_id": "route-pathway",
                            "route_id": "route-pathway",
                            "study_doi": "10.1000/pathway-route",
                            "domain_route": "molecular_pathway_readout",
                            "source_type": "primary_or_unclear",
                            "paper_type": "primary_study",
                            "text_depth": "article_text",
                            "extraction_status": "extracted",
                            "items": [
                                {
                                    "compound_or_exposure": "Psilocybin",
                                    "pathway_or_readout": "BDNF protein level",
                                    "molecular_effect_category": "Neuroplasticity",
                                    "specific_readout_or_marker": "BDNF",
                                    "mechanistic_relationship_type": "plasticity_marker",
                                    "experimental_system_category": "clinical",
                                    "population_model_category": "healthy_volunteers",
                                    "study_design_category": "rct",
                                    "assay_or_method": "ELISA",
                                    "finding_summary": "Psilocybin was associated with a BDNF change.",
                                    "evidence_location": "text",
                                    "evidence_locator": "Results",
                                }
                            ],
                            "warnings": [],
                        },
                    },
                    {
                        "task_id": "route-empty",
                        "route_id": "route-empty",
                        "status": "ok",
                        "result": {
                            "schema_version": "review_coverage_v1",
                            "task_id": "route-empty",
                            "route_id": "route-empty",
                            "study_doi": "10.1000/empty",
                            "domain_route": "clinical_outcome",
                            "source_type": "review",
                            "text_depth": "abstract_only",
                            "extraction_status": "no_extractable_scoped_coverage",
                            "coverage_items": [],
                        },
                    },
                ],
            )
            write_json(
                registry_path,
                {
                    "compounds": [
                        {"label": "Psilocybin", "aliases": [], "ids": {}, "status": "seeded"},
                        {"label": "DMT", "aliases": [], "ids": {}, "status": "seeded"},
                    ],
                    "targets": [
                        {
                            "label": "MAO-A",
                            "aliases": ["monoamine oxidase A"],
                            "ids": {},
                            "status": "needs_external_id_lookup",
                        },
                        {
                            "label": "Neuroplasticity",
                            "aliases": ["plasticity"],
                            "ids": {},
                            "status": "pathway_process",
                        },
                    ],
                    "disorders": [],
                },
            )

            rows, report = convert_outputs(input_jsonl=outputs_jsonl, tasks_jsonl=tasks_jsonl)
            write_json(evidence_rows_json, rows)

            self.assertEqual(report["rows_written"], 4)
            self.assertEqual(report["skipped"], {"extraction_status:no_extractable_scoped_coverage": 1})
            self.assertEqual({row["source_item_type"] for row in rows}, {"primary_item", "synthesis_result", "review_coverage_item"})
            brain_row = next(row for row in rows if row["domain_route"] == "brain_system")
            self.assertEqual(brain_row["study_title"], "Psilocybin and default mode network connectivity")
            self.assertEqual(brain_row["compound"], "Psilocybin")
            self.assertEqual(brain_row["graph_entity_label"], "DMN")
            self.assertEqual(brain_row["assessment_timepoint"], "2 hours post-dose")
            pk_row = next(row for row in rows if row["domain_route"] == "pharmacokinetics_exposure")
            self.assertEqual(pk_row["pk_relationship_type"], "metabolized_by")
            self.assertEqual(pk_row["pk_relationship_label"], "metabolized by")
            self.assertEqual(pk_row["pk_graph_object_kind"], "enzyme_or_transporter")
            self.assertEqual(pk_row["pk_graph_object_label"], "MAO-A")

            manifest = build_tables(
                graph_sources={
                    "routed_extractions": {
                        "path": evidence_rows_json,
                        "domain": "routed",
                        "dataset": "routed",
                        "default_evidence_type": "primary_evidence",
                        "skip_audit": True,
                    }
                },
                registry_path=registry_path,
                out_dir=out_dir,
                write_duckdb=False,
            )
            self.assertEqual(manifest["tables"]["evidence_edges"]["rows"], 4)
            findings = pd.read_parquet(out_dir / "findings.parquet")
            brain_claim = findings[findings["domain"] == "brain_system"].iloc[0]
            self.assertEqual(brain_claim["assessment_timepoint"], "2 hours post-dose")
            pathway_claim = findings[findings["domain"] == "molecular_pathway_readout"].iloc[0]
            self.assertEqual(pathway_claim["graph_entity_label"], "BDNF protein levels")
            self.assertEqual(pathway_claim["molecular_effect_label"], "Neuroplasticity")
            self.assertEqual(pathway_claim["graph_parent_label"], "Neuroplasticity")
            self.assertEqual(pathway_claim["graph_parent_kind"], "pathway_process")
            self.assertEqual(pathway_claim["specific_readout_or_marker"], "BDNF")
            self.assertEqual(pathway_claim["experimental_system_category"], "clinical")

            edges = pd.read_parquet(out_dir / "evidence_edges.parquet")
            self.assertEqual(
                set(edges["domain"]),
                {"brain_system", "pharmacokinetics_exposure", "real_world_public_health", "molecular_pathway_readout"},
            )
            brain_edge = edges[edges["domain"] == "brain_system"].iloc[0]
            self.assertEqual(brain_edge["entity_label"], "Default mode network")
            self.assertEqual(brain_edge["relation_type"], "has_brain_system_effect")
            pk_edge = edges[edges["domain"] == "pharmacokinetics_exposure"].iloc[0]
            self.assertEqual(pk_edge["entity_kind"], "target")
            self.assertEqual(pk_edge["relation_type"], "discusses_relationship")
            public_health_edge = edges[edges["domain"] == "real_world_public_health"].iloc[0]
            self.assertEqual(public_health_edge["entity_label"], "Access & equity")
            self.assertEqual(public_health_edge["relation_type"], "discusses_relationship")
            pathway_edge = edges[edges["domain"] == "molecular_pathway_readout"].iloc[0]
            self.assertEqual(pathway_edge["entity_label"], "BDNF protein levels")
            self.assertEqual(pathway_edge["graph_parent_label"], "Neuroplasticity")
            self.assertEqual(pathway_edge["graph_parent_kind"], "pathway_process")
            self.assertEqual(pathway_edge["relation_type"], "has_biomarker_readout")


if __name__ == "__main__":
    unittest.main()
