import unittest

from pipeline.ingest.build_boolean_search_modules import (
    build_boolean_modules,
    module_rows,
    openalex_query,
    pubmed_query,
)
from pathlib import Path
from tempfile import TemporaryDirectory


class BuildBooleanSearchModulesTest(unittest.TestCase):
    def test_openalex_query_uses_boolean_blocks(self) -> None:
        query = openalex_query(
            ["psilocybin", "psilocin"],
            ["major depressive disorder", "MDD"],
            ["randomized", "placebo"],
        )

        self.assertEqual(
            query,
            '(psilocybin OR psilocin) AND ("major depressive disorder" OR MDD) AND (randomized OR placebo)',
        )

    def test_pubmed_query_fields_terms_and_adds_human_filter(self) -> None:
        query = pubmed_query(
            ["MDMA"],
            ["post-traumatic stress disorder", "PTSD"],
            ["clinical trial"],
            human_filter=True,
        )

        self.assertIn("MDMA[Title/Abstract]", query)
        self.assertIn('"post-traumatic stress disorder"[Title/Abstract]', query)
        self.assertIn('"clinical trial"[Title/Abstract]', query)
        self.assertIn("NOT (animals[MeSH Terms] NOT humans[MeSH Terms])", query)

    def test_module_rows_create_provider_specific_seed_rows(self) -> None:
        modules = [
            {
                "module_id": "test_module",
                "module_type": "primary_boolean",
                "compound_terms": ["psilocybin"],
                "entity_terms": ["depression"],
                "evidence_terms": ["trial"],
            }
        ]

        rows = module_rows("disorder", modules, "pubmed")

        self.assertEqual(rows[0]["seed_id"], "disorder_grouped_pubmed_001")
        self.assertEqual(rows[0]["module_id"], "test_module")
        self.assertEqual(rows[0]["compound"], "")
        self.assertEqual(rows[0]["entity"], "")
        self.assertIn("psilocybin[Title/Abstract]", rows[0]["query"])
        self.assertEqual(rows[0]["recommended_max_results_per_seed"], 500)

    def test_build_boolean_modules_writes_manifest_and_csvs(self) -> None:
        with TemporaryDirectory() as tmpdir:
            manifest = build_boolean_modules(Path(tmpdir), ["mechanistic"])

            output = manifest["datasets"]["mechanistic"]["outputs"]["openalex"]
            self.assertTrue(Path(output["seed_csv"]).exists())
            self.assertIn("mechanistic_grouped_openalex_seeds.csv", output["seed_csv"])
            self.assertEqual(output["seed_count"], manifest["datasets"]["mechanistic"]["module_count"])
            self.assertEqual(output["recommended_max_results_per_seed"]["dense_topic"], 1000)
            self.assertTrue(Path(output["module_type_outputs"]["primary_boolean"]["seed_csv"]).exists())
            self.assertTrue(Path(output["module_type_outputs"]["dense_topic"]["seed_csv"]).exists())
            self.assertIn("grouped_search_modules_manifest.json", manifest["outputs"]["manifest_json"])
            self.assertEqual(
                output["module_type_outputs"]["dense_topic"]["recommended_max_results_per_seed"],
                1000,
            )
            self.assertTrue(Path(manifest["outputs"]["manifest_json"]).exists())

    def test_boolean_modules_include_supplemental_evidence_domain_scopes(self) -> None:
        with TemporaryDirectory() as tmpdir:
            manifest = build_boolean_modules(Path(tmpdir), ["mechanistic", "disorder"])

            mechanistic_counts = manifest["datasets"]["mechanistic"]["outputs"]["openalex"]["module_scope_counts"]
            disorder_counts = manifest["datasets"]["disorder"]["outputs"]["pubmed"]["module_scope_counts"]

            self.assertEqual(mechanistic_counts["molecular_pathway"], 5)
            self.assertEqual(mechanistic_counts["subjective_experience"], 2)
            self.assertEqual(mechanistic_counts["pharmacokinetics_exposure"], 2)
            self.assertEqual(mechanistic_counts["bridge_clinical_mechanism"], 3)
            self.assertEqual(disorder_counts["clinical_symptom_function"], 3)
            self.assertEqual(disorder_counts["clinical_safety"], 2)
            self.assertEqual(disorder_counts["intervention_context"], 2)
            self.assertEqual(disorder_counts["real_world_use_public_health"], 2)
            self.assertEqual(disorder_counts["bridge_clinical_mechanism"], 3)
            self.assertTrue(
                Path(
                    manifest["datasets"]["mechanistic"]["outputs"]["openalex"]["module_scope_outputs"]["molecular_pathway"]["seed_csv"]
                ).exists()
            )


if __name__ == "__main__":
    unittest.main()
