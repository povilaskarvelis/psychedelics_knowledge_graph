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

        self.assertEqual(rows[0]["seed_id"], "disorder_boolean_pubmed_001")
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
            self.assertEqual(output["seed_count"], manifest["datasets"]["mechanistic"]["module_count"])
            self.assertEqual(output["recommended_max_results_per_seed"]["dense_topic"], 1000)
            self.assertTrue(Path(output["module_type_outputs"]["primary_boolean"]["seed_csv"]).exists())
            self.assertTrue(Path(output["module_type_outputs"]["dense_topic"]["seed_csv"]).exists())
            self.assertEqual(
                output["module_type_outputs"]["dense_topic"]["recommended_max_results_per_seed"],
                1000,
            )
            self.assertTrue(Path(manifest["outputs"]["manifest_json"]).exists())


if __name__ == "__main__":
    unittest.main()
