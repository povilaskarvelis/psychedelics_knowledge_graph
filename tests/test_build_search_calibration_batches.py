import unittest

from pipeline.ingest.build_search_calibration_batches import select_calibration_rows


def row(seed_id, family, compound="", entity=""):
    return {
        "seed_id": seed_id,
        "dataset": "mechanistic",
        "family": family,
        "query": f"{seed_id} query",
        "compound": compound,
        "entity": entity,
        "entity_type": "target",
        "template": "template",
    }


class BuildSearchCalibrationBatchesTest(unittest.TestCase):
    def test_selects_expected_family_mix_and_pair_templates(self) -> None:
        rows = [
            row("s001", "class_level"),
            row("s002", "sentinel_default", "LSD", "5-HT2A"),
            row("s003", "sentinel_default", "MDMA", "SERT"),
        ]
        for idx, compound in enumerate(["LSD", "MDMA", "DMT"], start=10):
            rows.extend(
                [
                    row(f"s{idx}a", "compound_broad", compound, ""),
                    row(f"s{idx}b", "compound_broad", compound, ""),
                    row(f"s{idx}c", "compound_broad", compound, ""),
                ]
            )
        for idx, entity in enumerate(["5-HT2A", "SERT", "NMDA"], start=20):
            rows.extend(
                [
                    row(f"s{idx}a", "entity_broad", "", entity),
                    row(f"s{idx}b", "entity_broad", "", entity),
                    row(f"s{idx}c", "entity_broad", "", entity),
                ]
            )
        for idx, (compound, entity) in enumerate(
            [("LSD", "5-HT2A"), ("MDMA", "SERT"), ("DMT", "NMDA")],
            start=30,
        ):
            rows.extend(
                [
                    row(f"s{idx}a", "pair_core", compound, entity),
                    row(f"s{idx}b", "pair_core", compound, entity),
                    row(f"s{idx}c", "pair_core", compound, entity),
                ]
            )

        selected, summary = select_calibration_rows(
            rows,
            random_seed=1,
            sentinel_count=1,
            compound_units=1,
            entity_units=1,
            pair_units=2,
            pair_expanded_units=0,
        )

        counts = summary["selected_family_counts"]
        self.assertEqual(counts["class_level"], 1)
        self.assertEqual(counts["sentinel_default"], 1)
        self.assertEqual(counts["compound_broad"], 3)
        self.assertEqual(counts["entity_broad"], 3)
        self.assertEqual(counts["pair_core"], 6)
        self.assertEqual(summary["selected_seed_count"], len(selected))

    def test_zero_count_skips_grouped_families(self) -> None:
        rows = [
            row("s001", "class_level"),
            row("s010a", "compound_broad", "LSD", ""),
            row("s010b", "compound_broad", "LSD", ""),
            row("s011a", "compound_broad", "MDMA", ""),
        ]

        selected, summary = select_calibration_rows(
            rows,
            random_seed=1,
            sentinel_count=0,
            compound_units=0,
            entity_units=0,
            pair_units=0,
            pair_expanded_units=0,
        )

        self.assertNotIn("compound_broad", summary["selected_family_counts"])
        self.assertEqual(len(selected), 1)


if __name__ == "__main__":
    unittest.main()
