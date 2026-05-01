import argparse
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pipeline.review.run_local_llm_abstract_screening import (
    ABSTRACT_SCREENING_SCHEMA,
    FAST_SCREENING_SCHEMA,
    append_checkpoint_result,
    build_fast_screening_prompt,
    build_prompt,
    checkpoint_result_is_compatible,
    default_checkpoint_jsonl_path,
    deterministic_irrelevant_adjudication,
    deterministic_prescreen_decision,
    download_queue_eligible,
    enforce_validation_flags,
    fast_screen_excludes,
    fast_screen_irrelevant_adjudication,
    filter_indexed_rows,
    load_checkpoint_results,
    load_reprocess_doi_set,
    print_screening_row_followup,
    queue_rows_from_results,
    read_doi_file,
    revalidate_checkpoint_result,
    screen_row,
    semantic_auto_eligible,
    truncate_checkpoint,
    validation_flags,
    verified_supported_contexts,
)


def fake_args(**overrides) -> argparse.Namespace:
    defaults = {
        "dry_run": True,
        "model": "qwen3:14b",
        "fast_screen_model": "",
        "ollama_url": "http://localhost:11434",
        "timeout_sec": 1,
        "temperature": 0.0,
        "num_ctx": 2048,
        "deterministic_prescreen": False,
        "deterministic_prescreen_only": False,
        "doi_file": "",
        "use_heuristic_audit": False,
        "fast_screen_timeout_sec": 1,
        "fast_screen_temperature": 0.0,
        "fast_screen_num_ctx": 2048,
        "fast_screen_confidence": 0.9,
        "max_contexts": 16,
        "auto_confidence": 0.85,
        "context_confidence": 0.75,
        "checkpoint_jsonl": "",
        "resume_from_checkpoint": False,
        "materialize_checkpoint_only": False,
        "no_checkpoint": False,
        "quiet_progress": False,
        "show_checkpoint_progress": False,
        "reprocess_dois_file": "",
        "reprocess_all_checkpoint_dois": False,
        "only_with_abstract": False,
        "only_undownloaded": False,
        "only_heuristic_possible": False,
    }
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


class LocalLlmAbstractScreeningTest(unittest.TestCase):
    def test_schema_requires_quote_and_contexts(self) -> None:
        self.assertIn("supporting_abstract_quote", ABSTRACT_SCREENING_SCHEMA["required"])
        self.assertIn("supported_contexts", ABSTRACT_SCREENING_SCHEMA["required"])
        context_schema = ABSTRACT_SCREENING_SCHEMA["properties"]["supported_contexts"]["items"]
        self.assertIn("compound", context_schema["required"])
        self.assertIn("supporting_quote", context_schema["required"])
        self.assertNotIn("evidence_strength", ABSTRACT_SCREENING_SCHEMA["properties"])
        self.assertNotIn("paper_type", ABSTRACT_SCREENING_SCHEMA["properties"])

    def test_fast_screening_schema_is_minimal(self) -> None:
        self.assertEqual(
            FAST_SCREENING_SCHEMA["properties"]["screening_action"]["enum"],
            ["exclude_obvious_irrelevant", "escalate"],
        )
        self.assertEqual(
            set(FAST_SCREENING_SCHEMA["required"]),
            {"screening_action", "confidence", "supporting_quote", "reason"},
        )

    def test_prompt_uses_metadata_without_heuristic_labels(self) -> None:
        row = {
            "study_doi": "10.example/test",
            "study_title": "Psilocybin therapy for depression",
            "abstract": "Psilocybin therapy reduced depression scores.",
            "relevance_suggested": "likely_irrelevant",
            "screening_status": "excluded_low_signal",
        }

        messages = build_prompt(
            "disorder",
            row,
            [{"compound": "Psilocybin", "entity": "Major depressive disorder"}],
        )
        payload = json.loads(messages[1]["content"])

        self.assertEqual(payload["candidate_metadata"]["study_doi"], "10.example/test")
        self.assertEqual(payload["candidate_contexts"][0]["compound"], "Psilocybin")
        self.assertNotIn("relevance_suggested", payload["candidate_metadata"])
        self.assertNotIn("likely_irrelevant", messages[1]["content"])
        self.assertIn("do not classify source type", messages[1]["content"])

    def test_fast_prompt_is_conservative_about_escalation(self) -> None:
        row = {
            "study_doi": "10.example/test",
            "study_title": "Hemodialysis intervention for quality of life",
            "abstract": "Exercise improved quality of life in hemodialysis patients.",
        }

        messages = build_fast_screening_prompt(
            "disorder",
            row,
            [{"compound": "Psilocybin", "entity": "Depression"}],
        )
        payload = json.loads(messages[1]["content"])

        self.assertIn("When in doubt, escalate", messages[0]["content"])
        self.assertIn("Return escalate if the paper mentions any psychedelic", messages[1]["content"])
        self.assertIn("candidate_contexts", payload)
        self.assertIn("supplied candidate_contexts compound or entity term", messages[1]["content"])

    def test_fast_screen_excludes_only_high_confidence_verified_quote(self) -> None:
        context = "Title: Hemodialysis intervention\nAbstract: Exercise improved quality of life."
        screen = {
            "screening_action": "exclude_obvious_irrelevant",
            "confidence": 0.95,
            "supporting_quote": "Exercise improved quality of life.",
            "reason": "different intervention",
        }

        self.assertTrue(fast_screen_excludes(screen, context=context, min_confidence=0.9))
        self.assertFalse(fast_screen_excludes({**screen, "confidence": 0.8}, context=context, min_confidence=0.9))
        self.assertFalse(
            fast_screen_excludes(
                {**screen, "supporting_quote": "invented quote"},
                context=context,
                min_confidence=0.9,
            )
        )

    def test_fast_screen_exclusion_is_vetoed_by_candidate_terms(self) -> None:
        context = "Title: Depression outcomes\nAbstract: Exercise improved quality of life."
        screen = {
            "screening_action": "exclude_obvious_irrelevant",
            "confidence": 0.95,
            "supporting_quote": "Exercise improved quality of life.",
            "reason": "different intervention",
        }

        self.assertFalse(
            fast_screen_excludes(
                screen,
                context=context,
                min_confidence=0.9,
                candidate_contexts=[{"compound": "Psilocybin", "entity": "Depression"}],
            )
        )

    def test_fast_screen_irrelevant_adjudication_is_non_downloadable(self) -> None:
        adjudication = fast_screen_irrelevant_adjudication(
            {
                "confidence": 0.94,
                "supporting_quote": "Exercise improved quality of life.",
                "reason": "no in-scope intervention",
            }
        )

        self.assertEqual(adjudication["relevance"], "irrelevant")
        self.assertNotIn("evidence_strength", adjudication)
        self.assertNotIn("download_priority", adjudication)

    def test_deterministic_prescreen_excludes_rows_without_intervention_signal(self) -> None:
        row = {
            "study_title": "Exercise intervention for depression",
            "abstract": "This randomized trial tested an exercise program for depression symptoms in adults receiving standard outpatient mental health care.",
            "contexts": [],
        }

        decision = deterministic_prescreen_decision("disorder", row, heuristic={}, candidate_contexts=[])

        self.assertEqual(decision["action"], "exclude_obvious_irrelevant")
        adjudication = deterministic_irrelevant_adjudication(decision)
        self.assertEqual(adjudication["relevance"], "irrelevant")
        self.assertNotIn("should_download_fulltext", adjudication)

    def test_deterministic_prescreen_escalates_intervention_and_heuristic_signals(self) -> None:
        psychedelic_row = {
            "study_title": "Psilocybin therapy for depression",
            "abstract": "Psilocybin therapy reduced depression symptoms in adults with major depression.",
            "contexts": [{"compound": "Psilocybin", "entity": "Depression"}],
        }
        accented_ketamine_row = {
            "study_title": "Intérêt de la kétamine dans le traitement des douleurs chroniques",
            "abstract": "La kétamine est utilisée dans la prise en charge de la douleur chronique réfractaire aux traitements classiques.",
            "contexts": [],
        }
        retained_row = {
            "study_title": "Novel intervention for depression",
            "abstract": "This report discusses a novel intervention for depression symptoms in adults.",
            "contexts": [],
        }

        self.assertEqual(
            deterministic_prescreen_decision(
                "disorder",
                psychedelic_row,
                heuristic={},
                candidate_contexts=[{"compound": "Psilocybin", "entity": "Depression"}],
            )["action"],
            "escalate",
        )
        self.assertEqual(
            deterministic_prescreen_decision(
                "disorder",
                accented_ketamine_row,
                heuristic={},
                candidate_contexts=[],
            )["action"],
            "escalate",
        )
        self.assertEqual(
            deterministic_prescreen_decision(
                "disorder",
                retained_row,
                heuristic={"relevance_suggested": "possible_relevant"},
                candidate_contexts=[],
            )["action"],
            "escalate",
        )

    def test_verified_supported_contexts_requires_quote_and_confidence(self) -> None:
        adjudication = {
            "supporting_abstract_quote": "Psilocybin therapy reduced depression scores.",
            "supported_contexts": [
                {
                    "compound": "Psilocybin",
                    "entity": "Depression",
                    "support": "supported",
                    "supporting_quote": "Psilocybin therapy reduced depression scores.",
                    "confidence": 0.9,
                    "reason": "direct title/abstract support",
                },
                {
                    "compound": "MDMA",
                    "entity": "PTSD",
                    "support": "supported",
                    "supporting_quote": "not_found",
                    "confidence": 0.95,
                    "reason": "missing quote",
                },
                {
                    "compound": "LSD",
                    "entity": "Depression",
                    "support": "supported",
                    "supporting_quote": "LSD reduced depression.",
                    "confidence": 0.4,
                    "reason": "low confidence",
                },
            ],
        }
        context = "Title: Trial\nAbstract: Psilocybin therapy reduced depression scores."

        verified = verified_supported_contexts(adjudication, context=context, min_confidence=0.75)

        self.assertEqual(len(verified), 1)
        self.assertEqual(verified[0]["compound"], "Psilocybin")

    def test_semantic_auto_eligible_requires_relevant_verified_context(self) -> None:
        adjudication = {
            "relevance": "relevant",
            "confidence": 0.9,
            "needs_targeted_qa": False,
        }

        self.assertTrue(
            semantic_auto_eligible(adjudication, quote_verified=True, verified_context_count=1, min_confidence=0.85)
        )
        self.assertFalse(
            semantic_auto_eligible(adjudication, quote_verified=True, verified_context_count=0, min_confidence=0.85)
        )

    def test_download_queue_eligible_uses_relevance_only(self) -> None:
        self.assertTrue(download_queue_eligible({"relevance": "relevant"}, verified_context_count=1))
        self.assertTrue(download_queue_eligible({"relevance": "uncertain"}))
        self.assertFalse(download_queue_eligible({"relevance": "irrelevant"}))

    def test_validation_flags_force_unquoted_decision_to_targeted_qa(self) -> None:
        adjudication = {
            "relevance": "irrelevant",
            "needs_targeted_qa": False,
        }

        updated = enforce_validation_flags(adjudication, quote_verified=False, verified_context_count=0)

        self.assertTrue(updated["needs_targeted_qa"])

    def test_queue_rows_require_verified_context_for_relevant_context_queue(self) -> None:
        result = {
            "flat": {"status": "ok", "download_queue_eligible": True},
            "input_row": {
                "study_doi": "10.example/test",
                "study_title": "Example",
                "study_year": "2025",
                "authors": "A. Author",
                "publication_date": "2025-01-02",
                "journal_issn": "1234-5678",
                "funders": "Test Funder",
            },
            "adjudication": {"relevance": "relevant"},
            "verification": {
                "verified_supported_contexts": [
                    {"compound": "Psilocybin", "entity": "Depression"},
                ]
            },
        }
        no_context = {
            "flat": {"status": "ok", "download_queue_eligible": True},
            "input_row": {"study_doi": "10.example/unclear", "study_title": "Unclear"},
            "adjudication": {"relevance": "relevant"},
            "verification": {"verified_supported_contexts": []},
        }

        relevant_rows = queue_rows_from_results([result, no_context], {"relevant"}, require_verified_context=True)
        download_rows = queue_rows_from_results([result, no_context], {"relevant"}, require_verified_context=False)

        self.assertEqual(len(relevant_rows), 1)
        self.assertEqual(relevant_rows[0]["compound"], "Psilocybin")
        self.assertEqual(relevant_rows[0]["publication_date"], "2025-01-02")
        self.assertEqual(relevant_rows[0]["journal_issn"], "1234-5678")
        self.assertEqual(relevant_rows[0]["funders"], "Test Funder")
        self.assertEqual(len(download_rows), 2)
        self.assertEqual(download_rows[1]["compound"], "")

    def test_print_screening_row_followup_smoke(self) -> None:
        flat = {
            "status": "ok",
            "llm_relevance": "relevant",
            "quote_verified": True,
            "download_queue_eligible": True,
        }
        print_screening_row_followup(flat, 1.25, source="llm")
        print_screening_row_followup(flat, None, source="checkpoint")
        print_screening_row_followup(
            {"status": "failed", "error": "TimeoutError: x", "llm_relevance": ""},
            0.5,
            source="llm",
        )

    def test_load_reprocess_doi_set(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as tmp:
            tmp.write("# comment\n")
            tmp.write("10.1000/alpha\n")
            tmp.write("HTTPS://doi.org/10.1000/Beta \n")
            path = Path(tmp.name)
        try:
            s = load_reprocess_doi_set(path)
            self.assertEqual(s, {"10.1000/alpha", "10.1000/beta"})
        finally:
            path.unlink(missing_ok=True)

    def test_read_doi_file_accepts_queue_csv_rows(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as tmp:
            tmp.write("# doi,compound,target\n")
            tmp.write("10.1000/alpha,Psilocybin,Depression\n")
            tmp.write("https://doi.org/10.1000/Beta\n")
            path = Path(tmp.name)
        try:
            self.assertEqual(read_doi_file(path), {"10.1000/alpha", "10.1000/beta"})
        finally:
            path.unlink(missing_ok=True)

    def test_filter_indexed_rows_can_use_doi_file_filter(self) -> None:
        rows = [
            (1, {"study_doi": "10.example/keep", "abstract": "A" * 100}),
            (2, {"study_doi": "10.example/drop", "abstract": "A" * 100}),
        ]

        filtered = filter_indexed_rows(
            rows,
            triage_by_doi={},
            args=fake_args(only_with_abstract=True),
            doi_filter={"10.example/keep"},
        )

        self.assertEqual([row_index for row_index, _row in filtered], [1])

    def test_checkpoint_jsonl_append_and_load_last_wins(self) -> None:
        out = Path(tempfile.gettempdir()) / "psychkg_fake_report.json"
        ck = default_checkpoint_jsonl_path(out)
        truncate_checkpoint(ck)
        try:
            append_checkpoint_result(ck, {"input_row": {"study_doi": "10.1/a"}, "flat": {"x": 1}})
            append_checkpoint_result(ck, {"input_row": {"study_doi": "10.1/B"}, "flat": {"x": 2}})
            loaded = load_checkpoint_results(ck)
            self.assertEqual(loaded["10.1/a"]["flat"]["x"], 1)
            self.assertEqual(loaded["10.1/b"]["flat"]["x"], 2)
            append_checkpoint_result(ck, {"input_row": {"study_doi": "10.1/b"}, "flat": {"x": 3}})
            loaded2 = load_checkpoint_results(ck)
            self.assertEqual(loaded2["10.1/b"]["flat"]["x"], 3)
        finally:
            ck.unlink(missing_ok=True)

    def test_checkpoint_result_is_incompatible_with_unknown_schema_label(self) -> None:
        compatible = {
            "flat": {"status": "ok"},
            "adjudication": {"relevance": "relevant"},
        }
        incompatible = {
            "flat": {"status": "ok"},
            "adjudication": {"relevance": "maybe"},
        }

        self.assertTrue(checkpoint_result_is_compatible(compatible))
        self.assertFalse(checkpoint_result_is_compatible(incompatible))

    def test_screen_row_dry_run_does_not_call_model(self) -> None:
        row = {
            "study_doi": "10.example/test",
            "study_title": "Psilocybin therapy for depression",
            "abstract": "Psilocybin therapy reduced depression scores.",
            "contexts": [{"compound": "Psilocybin", "entity": "Depression"}],
        }

        result = screen_row("disorder", row_index=1, row=row, heuristic={}, args=fake_args())

        self.assertEqual(result["adjudication"]["reasoning_summary"], "dry run; model was not called")
        self.assertEqual(result["flat"]["llm_relevance"], "uncertain")

    def test_screen_row_fast_exclusion_skips_full_model(self) -> None:
        row = {
            "study_doi": "10.example/test",
            "study_title": "Hemodialysis intervention for quality of life",
            "abstract": "Exercise improved quality of life in hemodialysis patients.",
            "contexts": [],
        }
        args = fake_args(dry_run=False, fast_screen_model="llama3.1:8b")

        with patch(
            "pipeline.review.run_local_llm_abstract_screening.call_ollama",
            return_value={
                "screening_action": "exclude_obvious_irrelevant",
                "confidence": 0.95,
                "supporting_quote": "Exercise improved quality of life in hemodialysis patients.",
                "reason": "different intervention and no in-scope compound",
            },
        ) as mocked:
            result = screen_row("disorder", row_index=1, row=row, heuristic={}, args=args)

        self.assertEqual(mocked.call_count, 1)
        self.assertEqual(result["flat"]["screening_path"], "fast_excluded")
        self.assertEqual(result["flat"]["llm_relevance"], "irrelevant")
        self.assertFalse(result["flat"]["download_queue_eligible"])

    def test_screen_row_deterministic_prescreen_skips_model(self) -> None:
        row = {
            "study_doi": "10.example/test",
            "study_title": "Exercise intervention for depression",
            "abstract": "This randomized trial tested an exercise program for depression symptoms in adults receiving standard outpatient mental health care.",
            "contexts": [],
        }
        args = fake_args(dry_run=False, deterministic_prescreen=True)

        with patch("pipeline.review.run_local_llm_abstract_screening.call_ollama") as mocked:
            result = screen_row("disorder", row_index=1, row=row, heuristic={}, args=args)

        mocked.assert_not_called()
        self.assertEqual(result["flat"]["screening_path"], "deterministic_excluded")
        self.assertEqual(result["flat"]["llm_relevance"], "irrelevant")
        self.assertEqual(result["flat"]["deterministic_prescreen_action"], "exclude_obvious_irrelevant")

    def test_screen_row_fast_escalation_calls_full_model(self) -> None:
        row = {
            "study_doi": "10.example/test",
            "study_title": "Psilocybin therapy for depression",
            "abstract": "Psilocybin therapy reduced depression scores.",
            "contexts": [{"compound": "Psilocybin", "entity": "Depression"}],
        }
        args = fake_args(dry_run=False, fast_screen_model="llama3.1:8b")
        responses = [
            {
                "screening_action": "escalate",
                "confidence": 0.6,
                "supporting_quote": "Psilocybin therapy for depression",
                "reason": "mentions in-scope intervention and disorder",
            },
            {
                "relevance": "relevant",
                "supporting_abstract_quote": "Psilocybin therapy reduced depression scores.",
                "confidence": 0.9,
                "needs_targeted_qa": False,
                "reasoning_summary": "in scope",
                "supported_contexts": [
                    {
                        "compound": "Psilocybin",
                        "entity": "Depression",
                        "support": "supported",
                        "supporting_quote": "Psilocybin therapy reduced depression scores.",
                        "confidence": 0.9,
                        "reason": "direct abstract support",
                    }
                ],
            },
        ]

        with patch(
            "pipeline.review.run_local_llm_abstract_screening.call_ollama",
            side_effect=responses,
        ) as mocked:
            result = screen_row("disorder", row_index=1, row=row, heuristic={}, args=args)

        self.assertEqual(mocked.call_count, 2)
        self.assertEqual(result["flat"]["screening_path"], "fast_escalated")
        self.assertEqual(result["flat"]["llm_relevance"], "relevant")


if __name__ == "__main__":
    unittest.main()
