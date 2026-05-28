import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from pipeline.validate.build_context_provenance_audit import build_audit, write_corpus_tables


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


class BuildContextProvenanceAuditTest(unittest.TestCase):
    def test_merges_paper_sources_and_context_provenance(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            raw = root / "data" / "raw"
            processed = root / "data" / "processed"
            curated = root / "data" / "curated"
            raw.mkdir(parents=True)

            (raw / "doi_queue.disorder.discovered.txt").write_text(
                "10.example/dmt,DMT,Major depressive disorder,DMT depression trial,2024,A. Author\n",
                encoding="utf-8",
            )
            write_json(
                processed / "paper_library_disorder.json",
                [
                    {
                        "study_doi": "https://doi.org/10.example/dmt",
                        "study_title": "The antidepressant effects of N,N-Dimethyltryptamine",
                        "study_year": "2024",
                        "contexts": [
                            {
                                "compound": "DMT",
                                "entity": "Major depressive disorder",
                            }
                        ],
                    }
                ],
            )
            write_json(
                curated / "disorder_claims.json",
                [
                    {
                        "study_doi": "10.example/dmt",
                        "compound": "DMT",
                        "disorder": "Major depressive disorder",
                        "study_title": "The antidepressant effects of N,N-Dimethyltryptamine",
                        "paper_type": "primary_results",
                        "source_type": "primary_study",
                        "access_level": "abstract_only",
                    }
                ],
            )

            audit = build_audit(root=root, datasets=["disorder"])

            self.assertEqual(audit["summary"]["paper_count"], 1)
            paper = audit["papers"][0]
            self.assertEqual(paper["doi"], "10.example/dmt")
            self.assertIn("discovery_queue", paper["source_types"])
            self.assertIn("paper_library", paper["source_types"])
            self.assertIn("curated_claim", paper["source_types"])

            context = audit["contexts"][0]
            self.assertEqual(context["verification_layer"], "verified_evidence")
            self.assertEqual(context["revalidation_status"], "verified_existing")
            self.assertFalse(context["flags"]["needs_revalidation"])
            self.assertIn("queue_discovered_context", context["context_sources"])
            self.assertIn("paper_library_context", context["context_sources"])
            self.assertIn("curated_claim", context["context_sources"])

    def test_flags_short_acronym_contexts_without_disambiguating_text(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            curated = root / "data" / "curated"
            write_json(
                curated / "disorder_claims.json",
                [
                    {
                        "study_doi": "10.example/noisy",
                        "compound": "DMT",
                        "disorder": "Major depressive disorder",
                        "study_title": "A 2-year observational study of disease-modifying therapies",
                        "paper_type": "primary_results",
                        "source_type": "primary_study",
                    }
                ],
            )

            audit = build_audit(root=root, datasets=["disorder"])

            context = audit["contexts"][0]
            self.assertTrue(context["flags"]["possible_acronym_collision"])
            self.assertTrue(context["flags"]["needs_revalidation"])
            self.assertEqual(context["revalidation_status"], "possible_noise")

    def test_includes_nested_search_strategy_queues(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            combined = (
                root
                / "data"
                / "raw"
                / "search_strategies"
                / "closure_pairwise_audit_2026_05"
                / "direct_pair_run"
                / "combined"
            )
            combined.mkdir(parents=True)
            row = "10.example/closure,Psilocybin,Default mode network,Closure audit paper,2026,A. Author\n"
            (combined / "mechanistic_discovered.txt").write_text(row, encoding="utf-8")
            (combined / "mechanistic_new_dois.txt").write_text(row, encoding="utf-8")

            audit = build_audit(root=root, datasets=["mechanistic"])

            self.assertEqual(audit["summary"]["paper_count"], 1)
            paper = audit["papers"][0]
            self.assertEqual(paper["doi"], "10.example/closure")
            self.assertIn("discovery_queue", paper["source_types"])

            context = audit["contexts"][0]
            self.assertIn("search_strategy_discovered_context", context["context_sources"])
            self.assertIn("search_strategy_new_doi_context", context["context_sources"])
            self.assertTrue(context["flags"]["has_seed_or_discovery_context"])
            self.assertTrue(
                any(
                    item.get("selected_for_downstream") is True
                    and item.get("context_source") == "search_strategy_new_doi_context"
                    for item in context["provenance"]
                )
            )

    def test_includes_metadata_enrichment_table(self) -> None:
        import pandas as pd

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            raw = root / "data" / "raw"
            processed = root / "data" / "processed"
            raw.mkdir(parents=True)
            (raw / "doi_queue.mechanistic.discovered.txt").write_text(
                "10.example/corpus,Psilocybin,Default mode network,Corpus metadata paper,2026,A. Author\n",
                encoding="utf-8",
            )
            metadata_table = processed / "corpus" / "paper_metadata_enrichment.parquet"
            metadata_table.parent.mkdir(parents=True)
            pd.DataFrame(
                [
                    {
                        "doi": "10.example/corpus",
                        "datasets": "mechanistic",
                        "study_title": "Corpus metadata paper",
                        "study_year": "2026",
                        "abstract": "Psilocybin altered default mode network connectivity.",
                        "metadata_enrichment_status": "enriched",
                        "metadata_enrichment_run_id": "test_run",
                    }
                ],
            ).to_parquet(metadata_table, index=False)

            audit = build_audit(root=root, datasets=["mechanistic"])

            self.assertEqual(audit["summary"]["paper_count"], 1)
            paper = audit["papers"][0]
            self.assertEqual(paper["doi"], "10.example/corpus")
            self.assertIn("metadata_enrichment", paper["source_types"])
            self.assertEqual(paper["metadata"]["abstract"], "Psilocybin altered default mode network connectivity.")
            self.assertTrue(paper["flags"]["in_metadata_enrichment"])
            self.assertEqual(audit["contexts"][0]["dataset"], "mechanistic")
            self.assertIn("queue_discovered_context", audit["contexts"][0]["context_sources"])

    def test_writes_normalized_corpus_parquet_tables(self) -> None:
        import pandas as pd

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            raw = root / "data" / "raw"
            processed = root / "data" / "processed"
            raw.mkdir(parents=True)
            (raw / "doi_queue.mechanistic.discovered.txt").write_text(
                "10.example/paper,Psilocybin,Default mode network,Network paper,2026,A. Author\n",
                encoding="utf-8",
            )
            write_json(
                processed / "paper_library_mechanistic.json",
                [
                    {
                        "study_doi": "10.example/paper",
                        "study_title": "Network paper",
                        "study_year": "2026",
                        "abstract": "Psilocybin altered default mode network connectivity.",
                        "contexts": [{"compound": "Psilocybin", "entity": "Default mode network"}],
                    }
                ],
            )

            audit = build_audit(root=root, datasets=["mechanistic"])
            manifest = write_corpus_tables(audit, processed / "corpus")

            self.assertEqual(manifest["tables"]["candidate_papers"]["rows"], 1)
            self.assertEqual(manifest["tables"]["candidate_contexts"]["rows"], 1)
            self.assertGreaterEqual(manifest["tables"]["candidate_sources"]["rows"], 2)

            papers = pd.read_parquet(processed / "corpus" / "candidate_papers.parquet")
            contexts = pd.read_parquet(processed / "corpus" / "candidate_contexts.parquet")
            sources = pd.read_parquet(processed / "corpus" / "candidate_sources.parquet")

            self.assertEqual(papers.loc[0, "doi"], "10.example/paper")
            self.assertEqual(papers.loc[0, "abstract"], "Psilocybin altered default mode network connectivity.")
            self.assertEqual(contexts.loc[0, "compound"], "Psilocybin")
            self.assertIn("paper_library_context", contexts.loc[0, "context_sources"])
            self.assertIn("paper_source", set(sources["event_scope"]))
            self.assertIn("context_provenance", set(sources["event_scope"]))


if __name__ == "__main__":
    unittest.main()
