import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from pipeline.ingest.audit_discovery_seeds import build_seed_audit
from pipeline.ingest.discover_literature import (
    Seed,
    build_seed_list,
    generate_balanced_seeds,
)


class DiscoverySeedAuditTest(unittest.TestCase):
    def test_balanced_coverage_adds_missing_compound_and_entity_seeds(self) -> None:
        seeds, counts = generate_balanced_seeds(
            dataset="mechanistic",
            allowlists={
                "allowed_compounds": ["MDMA", "LSD"],
                "allowed_targets": ["SERT (SLC6A4)", "5-HT2A"],
            },
            base_seeds=[Seed("MDMA SERT binding", "MDMA", "SERT (SLC6A4)")],
            profile="coverage",
            max_compounds=0,
            max_entities=0,
            max_seeds=10,
        )

        self.assertEqual(counts["compound_gap"], 2)
        self.assertEqual(counts["entity_gap"], 2)
        self.assertTrue(any(seed.compound == "LSD" and seed.entity == "" for seed in seeds))
        self.assertTrue(any(seed.compound == "" and seed.entity == "5-HT2A" for seed in seeds))

    def test_build_seed_list_reports_balanced_counts(self) -> None:
        seeds, counts = build_seed_list(
            dataset="disorder",
            seed_values=[],
            query_values=[],
            allowlists={
                "allowed_compounds": ["Psilocybin", "Bufotenin"],
                "allowed_disorders": ["Major depressive disorder", "Bipolar depression"],
            },
            expand_from_config=False,
            auto_seeds_only=False,
            auto_template_mode="focused",
            auto_max_compounds=0,
            auto_max_entities=0,
            auto_max_pairs=400,
            auto_max_seeds=1200,
            balanced_seed_profile="coverage",
            balanced_max_compounds=0,
            balanced_max_entities=0,
            balanced_max_seeds=20,
        )

        self.assertGreater(counts["balanced"], 0)
        self.assertEqual(counts["final"], len(seeds))
        self.assertIn("balanced_compound_gap", counts)
        self.assertIn("balanced_entity_gap", counts)

    def test_seed_audit_reports_missing_defaults_and_balanced_sample(self) -> None:
        with TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.example.yaml"
            config_path.write_text(
                """
validation:
  allowed_targets:
    - "SERT (SLC6A4)"
    - "5-HT6"
  allowed_disorders:
    - "Major depressive disorder"
  allowed_compounds:
    - "MDMA"
    - "Bufotenin"
""".lstrip(),
                encoding="utf-8",
            )

            audit = build_seed_audit(
                dataset="mechanistic",
                config_path=config_path,
                balanced_seed_profile="coverage",
                balanced_max_compounds=0,
                balanced_max_entities=0,
                balanced_max_seeds=20,
            )

        self.assertEqual(audit["counts"]["allowed_compounds"], 2)
        self.assertEqual(audit["counts"]["allowed_entities"], 2)
        self.assertIn("balanced_seed_sample", audit)
        self.assertGreater(audit["counts"]["balanced"], 0)


if __name__ == "__main__":
    unittest.main()
