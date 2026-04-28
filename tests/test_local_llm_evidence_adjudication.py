import argparse
import json
import unittest

from pipeline.fulltext.run_local_llm_evidence_adjudication import (
    ADJUDICATION_SCHEMA,
    abstract_screening_rows_to_adjudication_rows,
    adjudicate_row,
    build_prompt,
    chunks_from_abstract_row,
    chunks_from_tei,
    quote_found_in_context,
    select_evidence_chunks,
    selected_rows,
    semantic_auto_eligible,
    labels_are_consistent,
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
        self.assertEqual(result["adjudication"]["best_evidence_location"], "abstract")
        self.assertEqual(result["flat"]["evidence_mode"], "abstract_only")

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


if __name__ == "__main__":
    unittest.main()
