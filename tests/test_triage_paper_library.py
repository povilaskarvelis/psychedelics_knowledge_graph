import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from pipeline.review.triage_paper_library import (
    load_benchmark_contexts,
    relevance_label,
    relevance_score_for_row,
)


class TriagePaperLibraryTest(unittest.TestCase):
    def test_synthesizes_context_when_discovery_context_is_stale(self) -> None:
        allowlists = {
            "allowed_compounds": ["Psilocybin"],
            "allowed_disorders": ["Treatment-resistant depression", "Alcohol use disorder"],
        }
        score, reasons, contexts, audit = relevance_score_for_row(
            dataset="disorder",
            text_norm="psilocybin assisted psychotherapy for alcohol use disorder randomized placebo trial",
            contexts=[{"compound": "Psilocybin", "entity": "Treatment-resistant depression"}],
            allowlists=allowlists,
            source_type="primary_study",
            metadata_lookup_error="",
        )

        self.assertEqual(relevance_label(score), "likely_relevant")
        self.assertIn("compound+entity pair synthesized from title/abstract", reasons)
        self.assertEqual(audit["synthesized_context_count"], 1)
        self.assertTrue(
            any(
                ctx["compound"] == "Psilocybin"
                and ctx["entity"] == "Alcohol use disorder"
                and ctx["triage_match_source"] == "synthesized_text"
                for ctx in contexts
            )
        )

    def test_protected_benchmark_context_survives_without_entity_text_match(self) -> None:
        allowlists = {
            "allowed_compounds": ["5-MeO-DMT", "DMT"],
            "allowed_targets": ["5-HT1A", "5-HT2A"],
        }
        score, reasons, contexts, audit = relevance_score_for_row(
            dataset="mechanistic",
            text_norm="behavioral effects of tetradeutero 5 meo dmt in rats",
            contexts=[{"compound": "DMT", "entity": "5-HT2A"}],
            allowlists=allowlists,
            source_type="other",
            metadata_lookup_error="",
            protected_contexts=[
                {
                    "compound": "5-MeO-DMT",
                    "entity": "5-HT1A",
                    "triage_match_source": "protected_benchmark",
                }
            ],
        )

        self.assertEqual(relevance_label(score), "likely_relevant")
        self.assertIn("protected benchmark/curated DOI retained", reasons)
        self.assertEqual(audit["protected_context_count"], 1)
        self.assertTrue(
            any(
                ctx["compound"] == "5-MeO-DMT"
                and ctx["entity"] == "5-HT1A"
                and ctx["triage_match_source"] == "protected_benchmark"
                for ctx in contexts
            )
        )

    def test_loads_dataset_specific_benchmark_contexts(self) -> None:
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "benchmark_manifest.json"
            path.write_text(
                json.dumps(
                    {
                        "entries": [
                            {
                                "doi": "https://doi.org/10.example/mech",
                                "dataset": "mechanistic",
                                "compound": "LSD",
                                "target": "5-HT2A",
                            },
                            {
                                "doi": "10.example/disorder",
                                "dataset": "disorder",
                                "compound": "Psilocybin",
                                "disorder": "Major depressive disorder",
                            },
                        ]
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            contexts = load_benchmark_contexts(path, "mechanistic", "target")
            self.assertEqual(list(contexts), ["10.example/mech"])
            self.assertEqual(contexts["10.example/mech"][0]["compound"], "LSD")
            self.assertEqual(contexts["10.example/mech"][0]["entity"], "5-HT2A")


if __name__ == "__main__":
    unittest.main()
