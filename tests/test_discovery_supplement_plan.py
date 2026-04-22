import unittest

from pipeline.ingest.build_discovery_supplement_plan import build_supplement_plan


class DiscoverySupplementPlanTest(unittest.TestCase):
    def test_mechanistic_plan_contains_assay_sources(self) -> None:
        plan = build_supplement_plan(
            dataset="mechanistic",
            allowlists={
                "allowed_compounds": ["MDMA"],
                "allowed_targets": ["SERT (SLC6A4)"],
            },
            max_pairs=1,
        )

        sources = {item["source"] for item in plan["supplements"]}
        self.assertEqual(sources, {"ChEMBL", "BindingDB"})
        self.assertEqual(plan["supplement_count"], 2)

    def test_disorder_plan_contains_clinicaltrials_source(self) -> None:
        plan = build_supplement_plan(
            dataset="disorder",
            allowlists={
                "allowed_compounds": ["Psilocybin"],
                "allowed_disorders": ["Major depressive disorder"],
            },
            max_pairs=1,
        )

        self.assertEqual(plan["supplements"][0]["source"], "ClinicalTrials.gov")
        self.assertEqual(plan["supplements"][0]["planned_lookup"]["query.cond"], "Major depressive disorder")


if __name__ == "__main__":
    unittest.main()
