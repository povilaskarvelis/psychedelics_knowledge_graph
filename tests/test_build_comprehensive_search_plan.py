import unittest

from pipeline.ingest.build_comprehensive_search_plan import build_search_plan


class ComprehensiveSearchPlanTest(unittest.TestCase):
    def test_baseline_plan_covers_compounds_entities_and_pairs(self) -> None:
        plan = build_search_plan(
            dataset="mechanistic",
            allowlists={
                "allowed_compounds": ["LSD", "Psilocybin"],
                "allowed_targets": ["5-HT2A"],
            },
            profile="baseline",
            include_default_seeds=False,
            max_compounds=0,
            max_entities=0,
            max_pairs=0,
        )

        counts = plan["counts"]["seed_family_counts"]
        self.assertEqual(counts["class_level"], 4)
        self.assertEqual(counts["compound_broad"], 6)
        self.assertEqual(counts["entity_broad"], 3)
        self.assertEqual(counts["pair_core"], 6)
        self.assertNotIn("pair_expanded", counts)

    def test_expanded_plan_adds_pair_evidence_templates(self) -> None:
        plan = build_search_plan(
            dataset="disorder",
            allowlists={
                "allowed_compounds": ["MDMA"],
                "allowed_disorders": ["Post-traumatic stress disorder"],
            },
            profile="expanded",
            include_default_seeds=False,
            max_compounds=0,
            max_entities=0,
            max_pairs=0,
        )

        counts = plan["counts"]["seed_family_counts"]
        self.assertEqual(counts["pair_core"], 3)
        self.assertEqual(counts["pair_expanded"], 5)
        self.assertEqual(plan["scope"]["pair_count"], 1)

    def test_pair_cap_limits_pairwise_search_space(self) -> None:
        plan = build_search_plan(
            dataset="mechanistic",
            allowlists={
                "allowed_compounds": ["LSD", "Psilocybin"],
                "allowed_targets": ["5-HT2A", "5-HT2C"],
            },
            profile="baseline",
            include_default_seeds=False,
            max_compounds=0,
            max_entities=0,
            max_pairs=2,
        )

        self.assertEqual(plan["scope"]["pair_count"], 2)
        self.assertEqual(plan["counts"]["seed_family_counts"]["pair_core"], 6)


if __name__ == "__main__":
    unittest.main()
