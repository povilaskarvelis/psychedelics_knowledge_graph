import argparse
import json
import tempfile
import unittest
from pathlib import Path

from pipeline.fulltext.run_local_llm_evidence_adjudication import (
    ADJUDICATION_SCHEMA,
    ASSESSMENT_SCHEMA,
    ASSESSMENT_SCHEMA_VERSION,
    ASSESSMENT_STAGE,
    abstract_screening_rows_to_adjudication_rows,
    assess_row,
    adjudicate_row,
    build_prompt,
    checkpoint_removes_for_dois,
    checkpoint_row_key,
    chunks_from_abstract_row,
    chunks_from_tei,
    default_checkpoint_jsonl_path,
    load_checkpoint_results,
    quote_found_in_context,
    select_evidence_chunks,
    selected_rows,
    semantic_auto_eligible,
    labels_are_consistent,
    normalize_existing_result_for_current_schema,
    ollama_request_timeout,
)


def fake_args(**overrides) -> argparse.Namespace:
    defaults = {
        "evidence_mode": "abstract_only",
        "max_chunks": 18,
        "max_context_chars": 22000,
        "dry_run": True,
        "model": "qwen3:14b",
        "ollama_url": "http://localhost:11434",
        "timeout_sec": 1,
        "temperature": 0.0,
        "num_ctx": 2048,
        "auto_confidence": 0.85,
    }
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


class LocalLlmEvidenceAdjudicationTest(unittest.TestCase):
    def test_chunks_from_tei_ignores_reference_back_matter(self) -> None:
        tei = """
        <TEI xmlns="http://www.tei-c.org/ns/1.0">
          <text>
            <front><abstract><p>This randomized trial enrolled 20 participants.</p></abstract></front>
            <body><div><head>Results</head><p>Psilocybin improved depression scores.</p></div></body>
            <back><listBibl><biblStruct><analytic><title>A systematic review</title></analytic></biblStruct></listBibl></back>
          </text>
        </TEI>
        """

        chunks = chunks_from_tei(tei)
        text = " ".join(chunk["text"] for chunk in chunks)

        self.assertIn("randomized trial", text)
        self.assertIn("improved depression", text)
        self.assertNotIn("systematic review", text)

    def test_quote_found_in_context_normalizes_whitespace(self) -> None:
        self.assertTrue(quote_found_in_context("Psilocybin improved depression scores.", "Psilocybin   improved\n depression scores."))
        self.assertFalse(quote_found_in_context("not_found", "Psilocybin improved depression scores."))

    def test_quote_found_in_context_accepts_ellipsis_fragments(self) -> None:
        context = (
            "BACKGROUND: Psilocybin therapy reduced depression scores in adults. "
            "RESULTS: Adverse events were transient and resolved without treatment."
        )

        self.assertTrue(
            quote_found_in_context(
                "Psilocybin therapy reduced depression scores [...] Adverse events were transient",
                context,
            )
        )
        self.assertTrue(
            quote_found_in_context(
                "BACKGROUND: Psilocybin therapy reduced depression scores ... resolved without treatment.",
                context,
            )
        )
        self.assertTrue(
            quote_found_in_context(
                "Psilocybin therapy reduced depression scores … adverse events were transient",
                context,
            )
        )

    def test_quote_found_in_context_rejects_missing_ellipsis_fragment(self) -> None:
        context = "Psilocybin therapy reduced depression scores in adults."

        self.assertFalse(
            quote_found_in_context(
                "Psilocybin therapy reduced depression scores [...] serious adverse events were common",
                context,
            )
        )

    def test_ollama_request_timeout_zero_means_wait_indefinitely(self) -> None:
        self.assertIsNone(ollama_request_timeout(0))
        self.assertIsNone(ollama_request_timeout(-1))
        self.assertEqual(ollama_request_timeout(240), 240)

    def test_build_prompt_contains_claim_and_evidence_chunks(self) -> None:
        messages = build_prompt(
            {
                "dataset": "disorder",
                "study_doi": "10.1000/test",
                "study_title": "Example trial",
                "compound": "Psilocybin",
                "entity": "Depression",
            },
            [{"id": "C001", "heading": "Results", "text": "Psilocybin improved depression scores."}],
        )

        payload = json.loads(messages[1]["content"])

        self.assertEqual(messages[0]["role"], "system")
        self.assertEqual(payload["claim_or_row"]["compound"], "Psilocybin")
        self.assertEqual(payload["evidence_chunks"][0]["id"], "C001")

    def test_build_prompt_marks_abstract_only_fallback(self) -> None:
        messages = build_prompt(
            {
                "dataset": "disorder",
                "study_title": "Example trial",
                "compound": "Psilocybin",
                "entity": "Depression",
            },
            [{"id": "A001", "heading": "Abstract", "text": "Psilocybin improved depression scores."}],
            evidence_mode="abstract_only",
        )
        payload = json.loads(messages[1]["content"])

        self.assertEqual(payload["claim_or_row"]["evidence_mode"], "abstract_only")
        self.assertIn("abstract-only fallback", " ".join(payload["instructions"]))

    def test_chunks_from_abstract_row_uses_title_and_abstract(self) -> None:
        chunks = chunks_from_abstract_row(
            {
                "study_title": "Psilocybin therapy for depression",
                "abstract": "Psilocybin improved depression scores.",
            }
        )

        self.assertEqual(chunks[0]["id"], "A001")
        self.assertIn("Title:", chunks[0]["text"])
        self.assertIn("Abstract:", chunks[0]["text"])

    def test_schema_requires_quote_and_variables(self) -> None:
        self.assertIn("supporting_quote", ADJUDICATION_SCHEMA["required"])
        self.assertIn("extracted_variables", ADJUDICATION_SCHEMA["required"])
        self.assertIn("sample_size_total", ADJUDICATION_SCHEMA["properties"]["extracted_variables"]["required"])
        paper_type_values = ADJUDICATION_SCHEMA["properties"]["paper_type"]["enum"]
        self.assertIn("correction", paper_type_values)

    def test_assessment_schema_separates_eligibility_classification_and_extraction(self) -> None:
        self.assertIn("eligibility_assessment", ASSESSMENT_SCHEMA["required"])
        self.assertIn("source_classification", ASSESSMENT_SCHEMA["required"])
        self.assertIn("data_extraction", ASSESSMENT_SCHEMA["required"])
        self.assertEqual(ASSESSMENT_SCHEMA["properties"]["assessment_stage"]["enum"], [ASSESSMENT_STAGE])
        self.assertEqual(ASSESSMENT_SCHEMA["properties"]["schema_version"]["enum"], [ASSESSMENT_SCHEMA_VERSION])
        self.assertIn(
            "is_in_scope",
            ASSESSMENT_SCHEMA["properties"]["eligibility_assessment"]["required"],
        )
        self.assertIn(
            "population_or_condition",
            ASSESSMENT_SCHEMA["properties"]["data_extraction"]["required"],
        )

    def test_abstract_screening_report_expands_verified_contexts(self) -> None:
        rows = abstract_screening_rows_to_adjudication_rows(
            [
                {
                    "input_row": {
                        "row_index": 7,
                        "study_doi": "10.example/test",
                        "study_title": "Psilocybin therapy for depression",
                        "abstract": "Psilocybin improved depression scores.",
                        "pdf_download_status": "not_found",
                    },
                    "adjudication": {
                        "relevance": "relevant",
                        "supporting_abstract_quote": "Psilocybin improved depression scores.",
                    },
                    "verification": {
                        "verified_supported_contexts": [
                            {
                                "compound": "Psilocybin",
                                "entity": "Depression",
                                "supporting_quote": "Psilocybin improved depression scores.",
                            }
                        ]
                    },
                    "flat": {"status": "ok", "dataset": "disorder"},
                }
            ]
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["sample_group"], "abstract_only_fallback")
        self.assertEqual(rows[0]["compound"], "Psilocybin")
        self.assertEqual(rows[0]["entity"], "Depression")

    def test_adjudicate_row_abstract_only_dry_run_without_artifact(self) -> None:
        result = adjudicate_row(
            {
                "dataset": "disorder",
                "study_doi": "10.example/test",
                "study_title": "Psilocybin therapy for depression",
                "abstract": "Psilocybin improved depression scores.",
                "compound": "Psilocybin",
                "entity": "Depression",
            },
            fake_args(),
        )

        self.assertEqual(result["evidence_mode"], "abstract_only")
        self.assertEqual(result["evidence_chunks"][0]["id"], "A001")
        self.assertEqual(result["assessment"]["eligibility_assessment"]["best_evidence_location"], "abstract")
        self.assertEqual(result["adjudication"]["best_evidence_location"], "abstract")
        self.assertEqual(result["flat"]["assessment_stage"], ASSESSMENT_STAGE)
        self.assertEqual(result["flat"]["evidence_mode"], "abstract_only")

    def test_assess_row_returns_assessment_and_legacy_adjudication(self) -> None:
        result = assess_row(
            {
                "dataset": "disorder",
                "study_doi": "10.example/test",
                "study_title": "Psilocybin therapy for depression",
                "abstract": "Psilocybin improved depression scores.",
                "compound": "Psilocybin",
                "entity": "Depression",
            },
            fake_args(),
        )

        self.assertIn("assessment", result)
        self.assertIn("adjudication", result)
        self.assertEqual(result["assessment"]["schema_version"], ASSESSMENT_SCHEMA_VERSION)
        self.assertEqual(
            result["adjudication"]["extracted_variables"]["population_or_condition"],
            "not_reported",
        )

    def test_select_evidence_chunks_prefers_relevant_text(self) -> None:
        artifact = {
            "best_backend": "grobid",
            "extractions": [
                {
                    "backend": "grobid",
                    "status": "ok",
                    "sections": [
                        {"heading": "Introduction", "snippet": "Background text."},
                        {"heading": "Results", "snippet": "Psilocybin improved MADRS depression scores."},
                    ],
                }
            ],
        }

        chunks = select_evidence_chunks(
            {"compound": "Psilocybin", "entity": "Depression", "study_title": "Trial"},
            artifact,
            max_chunks=2,
            max_chars=2000,
        )

        self.assertEqual(len(chunks), 2)
        self.assertTrue(any("MADRS" in chunk["text"] for chunk in chunks))

    def test_selected_rows_applies_offset_and_limit(self) -> None:
        rows = [{"row_index": idx} for idx in range(5)]

        self.assertEqual(selected_rows(rows, limit=2, offset=1), [{"row_index": 1}, {"row_index": 2}])
        self.assertEqual(selected_rows(rows, limit=0, offset=3), [{"row_index": 3}, {"row_index": 4}])

    def test_semantic_auto_eligible_requires_verified_quote(self) -> None:
        adjudication = {
            "confidence": 0.9,
            "needs_human_check": False,
            "source_family": "original_empirical",
            "source_type": "primary_study",
            "paper_type": "case_report",
        }

        self.assertTrue(semantic_auto_eligible(adjudication, quote_verified=True, min_confidence=0.85))
        self.assertFalse(semantic_auto_eligible(adjudication, quote_verified=False, min_confidence=0.85))

    def test_semantic_auto_eligible_rejects_inconsistent_labels(self) -> None:
        adjudication = {
            "confidence": 0.95,
            "needs_human_check": False,
            "source_family": "evidence_synthesis",
            "source_type": "primary_study",
            "paper_type": "systematic_review",
        }

        self.assertFalse(semantic_auto_eligible(adjudication, quote_verified=True, min_confidence=0.85))

    def test_semantic_auto_eligible_accepts_assessment_payload(self) -> None:
        assessment = {
            "eligibility_assessment": {
                "confidence": 0.9,
                "needs_human_check": False,
            },
            "source_classification": {
                "source_family": "original_empirical",
                "source_type": "primary_study",
                "paper_type": "primary_results",
            },
        }

        self.assertTrue(semantic_auto_eligible(assessment, quote_verified=True, min_confidence=0.85))

    def test_labels_are_consistent_for_source_families(self) -> None:
        self.assertTrue(
            labels_are_consistent(
                {
                    "source_family": "evidence_synthesis",
                    "source_type": "secondary_evidence",
                    "paper_type": "systematic_review",
                }
            )
        )
        self.assertTrue(
            labels_are_consistent(
                {
                    "source_family": "original_empirical",
                    "source_type": "primary_study",
                    "paper_type": "case_report",
                }
            )
        )
        self.assertTrue(
            labels_are_consistent(
                {
                    "source_family": "correction",
                    "source_type": "correction",
                    "paper_type": "correction",
                }
            )
        )
        self.assertFalse(
            labels_are_consistent(
                {
                    "source_family": "original_empirical",
                    "source_type": "case_report",
                    "paper_type": "case_report",
                }
            )
        )

    def test_checkpoint_row_key_splits_same_doi_claims(self) -> None:
        a = {
            "dataset": "mechanistic",
            "study_doi": "https://doi.org/10.1000/SHARED",
            "compound": "Psilocybin",
            "entity": "5-HT2A",
            "row_index": 10,
            "sample_group": "targeted_rule_qa",
        }
        b = {**a, "entity": "5-HT2B", "row_index": 10}
        self.assertNotEqual(checkpoint_row_key(a), checkpoint_row_key(b))

    def test_default_checkpoint_jsonl_path_stem(self) -> None:
        ck = default_checkpoint_jsonl_path(Path("/tmp/out/foo.json"))
        self.assertEqual(ck, Path("/tmp/out/foo.checkpoint.jsonl"))

    def test_load_checkpoint_results_last_line_wins(self) -> None:
        base = {
            "dataset": "mechanistic",
            "study_doi": "10.1000/example",
            "compound": "ketamine",
            "entity": "NMDA receptor",
            "row_index": 7,
            "sample_group": "auto_triage_audit",
        }
        key = checkpoint_row_key(base)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "run.checkpoint.jsonl"
            path.write_text(
                json.dumps({"input_row": base, "flat": {"status": "ok", "row_index": 7}}) + "\n"
                + json.dumps({"input_row": base, "flat": {"status": "failed", "row_index": 7}}) + "\n",
                encoding="utf-8",
            )
            mp = load_checkpoint_results(path)
            self.assertEqual(list(mp.keys()), [key])
            self.assertEqual(mp[key]["flat"]["status"], "failed")

    def test_legacy_checkpoint_result_is_upgraded_to_assessment_shape(self) -> None:
        base = {
            "dataset": "mechanistic",
            "study_doi": "10.1000/example",
            "compound": "ketamine",
            "entity": "NMDA receptor",
            "row_index": 7,
            "sample_group": "auto_triage_audit",
        }
        result = {
            "input_row": base,
            "adjudication": {
                "confidence": 0.9,
                "needs_human_check": False,
                "source_family": "original_empirical",
                "source_type": "primary_study",
                "paper_type": "primary_results",
                "study_design": "randomized trial",
                "evidence_strength": "medium",
                "supports_current_claim": "supported",
                "best_evidence_location": "results",
                "best_evidence_locator": "C001",
                "supporting_quote": "Ketamine blocked NMDA receptors.",
                "reasoning_summary": "legacy checkpoint",
                "extracted_variables": {"sample_size_total": "24"},
            },
            "verification": {"quote_verified": True},
            "flat": {"status": "ok", "evidence_mode": "full_text"},
        }

        upgraded = normalize_existing_result_for_current_schema(result, min_confidence=0.85)

        self.assertEqual(upgraded["assessment"]["schema_version"], ASSESSMENT_SCHEMA_VERSION)
        self.assertEqual(upgraded["assessment"]["data_extraction"]["sample_size_total"], "24")
        self.assertEqual(upgraded["assessment"]["data_extraction"]["population_or_condition"], "not_reported")
        self.assertEqual(upgraded["flat"]["assessment_stage"], ASSESSMENT_STAGE)
        self.assertTrue(upgraded["flat"]["semantic_auto_eligible"])

    def test_checkpoint_removes_for_dois_targets_all_rows(self) -> None:
        doi = "10.1000/multi"
        rows = [
            {"dataset": "mechanistic", "study_doi": doi, "compound": "a", "entity": "x", "row_index": 1},
            {"dataset": "mechanistic", "study_doi": doi, "compound": "b", "entity": "y", "row_index": 2},
        ]
        mp = {checkpoint_row_key(r): {"input_row": r} for r in rows}
        removed = checkpoint_removes_for_dois(mp, {doi.lower()})
        self.assertEqual(removed, 2)
        self.assertEqual(len(mp), 0)


if __name__ == "__main__":
    unittest.main()
