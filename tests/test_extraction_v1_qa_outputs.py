import copy
import json
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft7Validator

from pipeline.extract.extraction_v1_utils import load_pilot_contexts, quote_found_in_context
from pipeline.extract.qa_extraction_v1_outputs import load_schema, qa_rows


ROOT = Path(__file__).resolve().parents[1]


def valid_disorder_result() -> dict:
    quote = "Participants receiving psilocybin improved on depression measures."
    return {
        "schema_version": "extraction_v1",
        "dataset": "disorder",
        "study_doi": "10.1000/qa",
        "input_record_id": "disorder:abstract_relevant:10.1000/qa",
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
            "supporting_quote": quote,
            "confidence": 0.91,
            "needs_human_review": False,
            "reasoning_summary": "The abstract reports original clinical outcome results.",
        },
        "claims": [
            {
                "claim_type": "compound_disorder",
                "compound": "Psilocybin",
                "target": "not_applicable",
                "disorder": "Major depressive disorder",
                "raw_entity_label": "Major depressive disorder",
                "entity_role": "therapeutic_indication",
                "clinical_context_condition": "Adults with major depressive disorder",
                "graph_entity_label": "Major depressive disorder",
                "graph_entity_type": "indication",
                "graph_include_candidate": True,
                "graph_exclusion_reason": "not_applicable",
                "support": "supported",
                "study_design": "randomized_controlled_trial",
                "system": "clinical",
                "outcome_type": "depressive symptom change",
                "outcome_domain": "depression",
                "outcome_measure": "MADRS",
                "result_direction": "positive",
                "sample_size_total": "59",
                "evidence_location": "abstract",
                "evidence_locator": "Abstract",
                "supporting_quote": quote,
                "confidence": 0.9,
                "needs_human_review": False,
            }
        ],
        "coverage_mentions": [],
    }


def pilot_context_path(tmpdir: str) -> Path:
    path = Path(tmpdir) / "pilot.jsonl"
    path.write_text(
        json.dumps(
            {
                "schema_version": "extraction_v1_pilot_input",
                "pilot_record_id": "disorder:abstract_relevant:10.1000/qa",
                "dataset": "disorder",
                "study_doi": "10.1000/qa",
                "bucket": "abstract_relevant",
                "access_level": "abstract_only",
                "paper_metadata": {
                    "study_doi": "10.1000/qa",
                    "study_title": "A small clinical trial",
                    "publication_type": "Journal Article | Clinical Trial",
                    "abstract": "Participants receiving psilocybin improved on depression measures.",
                },
                "content": {
                    "title": "A small clinical trial",
                    "abstract": "Participants receiving psilocybin improved on depression measures.",
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return path


class ExtractionV1QaOutputsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.validator = Draft7Validator(load_schema(ROOT / "schema" / "extraction_v1.schema.json"))

    def test_valid_output_with_matching_quotes_passes_qa(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            contexts = load_pilot_contexts(pilot_context_path(tmpdir))
            rows, details = qa_rows([valid_disorder_result()], self.validator, contexts)

        self.assertEqual(details, [])
        self.assertEqual(rows[0]["status"], "ok")
        self.assertEqual(rows[0]["context_status"], "found")
        self.assertEqual(rows[0]["quote_failure_count"], 0)

    def test_missing_quote_is_reported_as_quote_error(self) -> None:
        result = valid_disorder_result()
        result["claims"][0]["supporting_quote"] = "This sentence does not occur in the source context."

        with tempfile.TemporaryDirectory() as tmpdir:
            contexts = load_pilot_contexts(pilot_context_path(tmpdir))
            rows, details = qa_rows([result], self.validator, contexts)

        self.assertEqual(rows[0]["status"], "quote_error")
        self.assertEqual(rows[0]["quote_failure_count"], 1)
        self.assertTrue(any(detail["check_type"] == "quote" for detail in details))

    def test_metadata_quotes_are_available_for_qa(self) -> None:
        result = valid_disorder_result()
        result["paper_assessment"]["supporting_quote"] = "Journal Article | Clinical Trial"

        with tempfile.TemporaryDirectory() as tmpdir:
            contexts = load_pilot_contexts(pilot_context_path(tmpdir))
            rows, details = qa_rows([result], self.validator, contexts)

        self.assertEqual(details, [])
        self.assertEqual(rows[0]["status"], "ok")

    def test_schema_errors_take_precedence_over_quote_checks(self) -> None:
        result = copy.deepcopy(valid_disorder_result())
        result["paper_assessment"]["relevance"] = "not_relevant"

        with tempfile.TemporaryDirectory() as tmpdir:
            contexts = load_pilot_contexts(pilot_context_path(tmpdir))
            rows, details = qa_rows([result], self.validator, contexts)

        self.assertEqual(rows[0]["status"], "schema_error")
        self.assertGreater(rows[0]["schema_error_count"], 0)
        self.assertTrue(any(detail["check_type"] == "schema" for detail in details))

    def test_quote_matching_accepts_ellipsis_fragments(self) -> None:
        context = "The trial found rapid improvement after dosing and durable remission at follow-up."

        self.assertTrue(quote_found_in_context("rapid improvement ... durable remission", context))
        self.assertTrue(quote_found_in_context("rapid improvement [...] durable remission", context))

    def test_quote_matching_accepts_long_token_anchor_with_symbol_differences(self) -> None:
        context = (
            "Binding affinity at human serotonergic 5 HT2A receptors was measured "
            "in vitro and reported as Ki SD nM values in table 1."
        )

        self.assertTrue(
            quote_found_in_context(
                "Binding affinity at human serotonergic 5-HT2A receptors was measured in vitro and reported as Ki ± SD (nM) values",
                context,
            )
        )
        self.assertFalse(quote_found_in_context("Serotonin", context))

    def test_coverage_mentions_are_quote_checked(self) -> None:
        result = valid_disorder_result()
        result["paper_assessment"].update(
            {
                "route": "secondary_literature",
                "source_family": "evidence_synthesis",
                "source_type": "review",
                "paper_type": "review",
                "study_design": "narrative_review",
                "system": "not_applicable",
                "has_original_results": False,
                "has_extractable_claims": False,
            }
        )
        result["claims"] = []
        result["coverage_mentions"] = [
            {
                "coverage_type": "reviews",
                "relationship_domain": "compound_disorder",
                "compound": "Psilocybin",
                "entity_type": "disorder",
                "entity": "Major depressive disorder",
                "evidence_location": "abstract",
                "evidence_locator": "Abstract",
                "supporting_quote": "This quote is not in the context.",
                "confidence": 0.8,
                "needs_human_review": False,
            }
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            contexts = load_pilot_contexts(pilot_context_path(tmpdir))
            rows, details = qa_rows([result], self.validator, contexts)

        self.assertEqual(rows[0]["status"], "quote_error")
        self.assertEqual(rows[0]["coverage_mention_count"], 1)
        self.assertTrue(any(detail["scope"] == "coverage_mention" for detail in details))


if __name__ == "__main__":
    unittest.main()
