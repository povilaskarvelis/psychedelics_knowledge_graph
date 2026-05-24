import tempfile
import unittest
from pathlib import Path

from pipeline.extract.extraction_v1_utils import write_json
from pipeline.extract.normalize_extraction_claims import (
    DEFAULT_DISORDER_ALIASES_PATH,
    DEFAULT_REGISTRY_PATH,
    normalize_claims,
)


def registry(path: Path) -> Path:
    data = {
        "compounds": [
            {
                "label": "Psilocybin",
                "aliases": ["psilocybin-assisted therapy"],
                "ids": {"pubchem_cid": "10624"},
                "status": "seeded",
            },
            {
                "label": "Ketamine",
                "aliases": ["racemic ketamine"],
                "ids": {"pubchem_cid": "3821"},
                "status": "seeded",
            },
            {
                "label": "MDMA",
                "aliases": ["3,4-methylenedioxymethamphetamine"],
                "ids": {"pubchem_cid": "1615"},
                "status": "seeded",
            },
        ],
        "targets": [
            {
                "label": "NET (SLC6A2)",
                "aliases": ["NET", "norepinephrine transporter", "SLC6A2"],
                "ids": {"gene_symbol": "SLC6A2"},
                "status": "seeded",
            }
        ],
        "disorders": [
            {
                "label": "Major depressive disorder",
                "aliases": ["MDD", "major depression"],
                "ids": {"mondo_id": "MONDO:0002050"},
                "status": "seeded",
            }
        ],
    }
    write_json(path, data)
    return path


def disorder_aliases(path: Path) -> Path:
    write_json(path, {"Major depressive disorder": ["depressive disorder in adults"]})
    return path


class NormalizeExtractionClaimsTest(unittest.TestCase):
    def test_normalizes_registry_backed_disorder_claim(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            graph_rows, audit_rows, report = normalize_claims(
                mechanistic_rows=[],
                disorder_rows=[
                    {
                        "claim_type": "compound_disorder",
                        "compound": "psilocybin-assisted therapy",
                        "disorder": "MDD",
                        "graph_entity_label": "major depression",
                        "graph_entity_type": "indication",
                        "graph_include_candidate": True,
                        "entity_role": "therapeutic_indication",
                    }
                ],
                registry_path=registry(Path(tmpdir) / "registry.json"),
                disorder_aliases_path=disorder_aliases(Path(tmpdir) / "aliases.json"),
            )

        self.assertEqual(report["summary"]["disorder"]["graph_rows"], 1)
        self.assertEqual(audit_rows["disorder"][0]["normalization_status"], "normalized")
        self.assertEqual(graph_rows["disorder"][0]["compound"], "Psilocybin")
        self.assertEqual(graph_rows["disorder"][0]["disorder"], "Major depressive disorder")
        self.assertEqual(graph_rows["disorder"][0]["entity_ids"]["mondo_id"], "MONDO:0002050")

    def test_non_graph_endpoint_is_audited_but_not_projected(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            graph_rows, audit_rows, _report = normalize_claims(
                mechanistic_rows=[],
                disorder_rows=[
                    {
                        "claim_type": "compound_disorder",
                        "compound": "Ketamine",
                        "disorder": "not_applicable",
                        "graph_entity_label": "none",
                        "graph_entity_type": "none",
                        "graph_include_candidate": False,
                        "entity_role": "physiological_measure",
                        "raw_entity_label": "heart rate",
                    }
                ],
                registry_path=registry(Path(tmpdir) / "registry.json"),
                disorder_aliases_path=disorder_aliases(Path(tmpdir) / "aliases.json"),
            )

        self.assertEqual(graph_rows["disorder"], [])
        self.assertEqual(audit_rows["disorder"][0]["normalization_status"], "not_graph_candidate")

    def test_exact_compound_label_wins_over_stereoisomer_alias_collision(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "registry.json"
            write_json(
                path,
                {
                    "compounds": [
                        {"label": "Ketamine", "aliases": ["racemic ketamine"], "ids": {}, "status": "seeded"},
                        {"label": "S-ketamine", "aliases": ["(S)-ketamine", "esketamine"], "ids": {}, "status": "seeded"},
                    ],
                    "targets": [],
                    "disorders": [
                        {
                            "label": "Major depressive disorder",
                            "aliases": ["MDD"],
                            "ids": {},
                            "status": "seeded",
                        }
                    ],
                },
            )
            graph_rows, audit_rows, _report = normalize_claims(
                mechanistic_rows=[],
                disorder_rows=[
                    {
                        "claim_type": "compound_disorder",
                        "compound": "Ketamine",
                        "disorder": "MDD",
                        "graph_entity_label": "MDD",
                        "graph_entity_type": "indication",
                        "graph_include_candidate": True,
                        "entity_role": "therapeutic_indication",
                    }
                ],
                registry_path=path,
                disorder_aliases_path=disorder_aliases(Path(tmpdir) / "aliases.json"),
            )

        self.assertEqual(audit_rows["disorder"][0]["normalization_status"], "normalized")
        self.assertEqual(graph_rows["disorder"][0]["compound"], "Ketamine")

    def test_parenthetical_target_label_maps_to_registry_entry(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            graph_rows, audit_rows, _report = normalize_claims(
                mechanistic_rows=[
                    {
                        "claim_type": "compound_target",
                        "compound": "MDMA",
                        "target": "Norepinephrine transporter (NET)",
                        "graph_entity_label": "Norepinephrine transporter (NET)",
                        "graph_entity_type": "target",
                        "graph_include_candidate": True,
                        "entity_role": "molecular_target",
                    }
                ],
                disorder_rows=[],
                registry_path=registry(Path(tmpdir) / "registry.json"),
                disorder_aliases_path=disorder_aliases(Path(tmpdir) / "aliases.json"),
            )

        self.assertEqual(audit_rows["mechanistic"][0]["normalization_status"], "normalized")
        self.assertEqual(graph_rows["mechanistic"][0]["target"], "NET (SLC6A2)")
        self.assertEqual(graph_rows["mechanistic"][0]["entity_ids"]["gene_symbol"], "SLC6A2")

    def test_curated_registry_maps_common_target_aliases(self) -> None:
        graph_rows, audit_rows, _report = normalize_claims(
            mechanistic_rows=[
                {
                    "claim_type": "compound_target",
                    "compound": "Ketamine",
                    "target": "NMDAR",
                    "graph_entity_label": "NMDAR",
                    "graph_entity_type": "target",
                    "graph_include_candidate": True,
                    "entity_role": "molecular_target",
                },
                {
                    "claim_type": "compound_target",
                    "compound": "Psilocybin",
                    "target": "5-HT2AR",
                    "graph_entity_label": "5-HT2AR",
                    "graph_entity_type": "target",
                    "graph_include_candidate": True,
                    "entity_role": "molecular_target",
                },
                {
                    "claim_type": "compound_target",
                    "compound": "LSD",
                    "target": "D2 receptor",
                    "graph_entity_label": "D2 receptor",
                    "graph_entity_type": "target",
                    "graph_include_candidate": True,
                    "entity_role": "molecular_target",
                },
            ],
            disorder_rows=[],
            registry_path=DEFAULT_REGISTRY_PATH,
            disorder_aliases_path=DEFAULT_DISORDER_ALIASES_PATH,
        )

        self.assertEqual(
            [row["normalization_status"] for row in audit_rows["mechanistic"]],
            ["normalized", "normalized", "normalized"],
        )
        self.assertEqual(
            [row["target"] for row in graph_rows["mechanistic"]],
            ["NMDA receptor", "5-HT2A", "Dopamine D2 receptor (DRD2)"],
        )

    def test_target_normalization_does_not_fuzzy_match_different_receptor_subtype(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            graph_rows, audit_rows, _report = normalize_claims(
                mechanistic_rows=[
                    {
                        "claim_type": "compound_target",
                        "compound": "Ketamine",
                        "target": "Metabotropic glutamate receptor 5",
                        "graph_entity_label": "mGluR5",
                        "graph_entity_type": "target",
                        "graph_include_candidate": True,
                        "entity_role": "molecular_target",
                    }
                ],
                disorder_rows=[],
                registry_path=registry(Path(tmpdir) / "registry.json"),
                disorder_aliases_path=disorder_aliases(Path(tmpdir) / "aliases.json"),
            )

        self.assertEqual(graph_rows["mechanistic"], [])
        self.assertEqual(audit_rows["mechanistic"][0]["normalization_status"], "entity_unmapped")

    def test_unmapped_graph_entity_is_held_for_review(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            graph_rows, audit_rows, _report = normalize_claims(
                mechanistic_rows=[],
                disorder_rows=[
                    {
                        "claim_type": "compound_disorder",
                        "compound": "Ketamine",
                        "disorder": "pain",
                        "graph_entity_label": "pain",
                        "graph_entity_type": "indication",
                        "graph_include_candidate": True,
                        "entity_role": "outcome_measure",
                    }
                ],
                registry_path=registry(Path(tmpdir) / "registry.json"),
                disorder_aliases_path=disorder_aliases(Path(tmpdir) / "aliases.json"),
            )

        self.assertEqual(graph_rows["disorder"], [])
        self.assertEqual(audit_rows["disorder"][0]["normalization_status"], "entity_unmapped")
        self.assertEqual(audit_rows["disorder"][0]["canonical_compound"], "Ketamine")

    def test_curated_registry_maps_high_confidence_disorder_aliases(self) -> None:
        graph_rows, audit_rows, _report = normalize_claims(
            mechanistic_rows=[],
            disorder_rows=[
                {
                    "claim_type": "compound_disorder",
                    "compound": "Ketamine",
                    "disorder": "cocaine dependence",
                    "graph_entity_label": "cocaine dependence",
                    "graph_entity_type": "indication",
                    "graph_include_candidate": True,
                    "entity_role": "therapeutic_indication",
                },
                {
                    "claim_type": "compound_disorder",
                    "compound": "Ketamine",
                    "disorder": "depression",
                    "graph_entity_label": "depression",
                    "graph_entity_type": "indication",
                    "graph_include_candidate": True,
                    "entity_role": "therapeutic_indication",
                },
                {
                    "claim_type": "compound_disorder",
                    "compound": "Ketamine",
                    "disorder": "neuropathic pain",
                    "graph_entity_label": "neuropathic pain",
                    "graph_entity_type": "indication",
                    "graph_include_candidate": True,
                    "entity_role": "therapeutic_indication",
                },
            ],
            registry_path=DEFAULT_REGISTRY_PATH,
            disorder_aliases_path=DEFAULT_DISORDER_ALIASES_PATH,
        )

        self.assertEqual([row["normalization_status"] for row in audit_rows["disorder"]], ["normalized", "normalized", "normalized"])
        self.assertEqual(
            [row["disorder"] for row in graph_rows["disorder"]],
            ["Cocaine use disorder", "Depression", "Neuropathic pain"],
        )

    def test_class_level_compound_label_is_not_a_graph_compound(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            graph_rows, audit_rows, _report = normalize_claims(
                mechanistic_rows=[],
                disorder_rows=[
                    {
                        "claim_type": "compound_disorder",
                        "compound": "classic psychedelics",
                        "disorder": "MDD",
                        "graph_entity_label": "MDD",
                        "graph_entity_type": "indication",
                        "graph_include_candidate": True,
                        "entity_role": "therapeutic_indication",
                    }
                ],
                registry_path=registry(Path(tmpdir) / "registry.json"),
                disorder_aliases_path=disorder_aliases(Path(tmpdir) / "aliases.json"),
            )

        self.assertEqual(graph_rows["disorder"], [])
        self.assertEqual(audit_rows["disorder"][0]["normalization_status"], "compound_class_not_graphable")

    def test_mixed_class_and_compound_label_is_not_reported_as_unmapped(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            graph_rows, audit_rows, _report = normalize_claims(
                mechanistic_rows=[],
                disorder_rows=[
                    {
                        "claim_type": "compound_disorder",
                        "compound": "classical psychedelics and MDMA",
                        "disorder": "MDD",
                        "graph_entity_label": "MDD",
                        "graph_entity_type": "indication",
                        "graph_include_candidate": True,
                        "entity_role": "therapeutic_indication",
                    }
                ],
                registry_path=registry(Path(tmpdir) / "registry.json"),
                disorder_aliases_path=disorder_aliases(Path(tmpdir) / "aliases.json"),
            )

        self.assertEqual(graph_rows["disorder"], [])
        self.assertEqual(audit_rows["disorder"][0]["normalization_status"], "compound_class_not_graphable")

    def test_multi_compound_label_is_not_a_single_graph_compound(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            graph_rows, audit_rows, _report = normalize_claims(
                mechanistic_rows=[],
                disorder_rows=[
                    {
                        "claim_type": "compound_disorder",
                        "compound": "Psilocybin and MDMA",
                        "disorder": "MDD",
                        "graph_entity_label": "MDD",
                        "graph_entity_type": "indication",
                        "graph_include_candidate": True,
                        "entity_role": "therapeutic_indication",
                    }
                ],
                registry_path=registry(Path(tmpdir) / "registry.json"),
                disorder_aliases_path=disorder_aliases(Path(tmpdir) / "aliases.json"),
            )

        self.assertEqual(graph_rows["disorder"], [])
        self.assertEqual(audit_rows["disorder"][0]["normalization_status"], "compound_combo_not_graphable")

    def test_reference_control_compound_label_is_not_a_graph_compound(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            graph_rows, audit_rows, _report = normalize_claims(
                mechanistic_rows=[
                    {
                        "claim_type": "compound_target",
                        "compound": "Ketanserin",
                        "target": "NET",
                        "graph_entity_label": "NET",
                        "graph_entity_type": "target",
                        "graph_include_candidate": True,
                        "entity_role": "molecular_target",
                    },
                    {
                        "claim_type": "compound_target",
                        "compound": "8-OH-DPAT",
                        "target": "NET",
                        "graph_entity_label": "NET",
                        "graph_entity_type": "target",
                        "graph_include_candidate": True,
                        "entity_role": "molecular_target",
                    },
                ],
                disorder_rows=[],
                registry_path=registry(Path(tmpdir) / "registry.json"),
                disorder_aliases_path=disorder_aliases(Path(tmpdir) / "aliases.json"),
            )

        self.assertEqual(graph_rows["mechanistic"], [])
        self.assertEqual(
            [row["normalization_status"] for row in audit_rows["mechanistic"]],
            ["compound_reference_not_graphable", "compound_reference_not_graphable"],
        )

    def test_comma_separated_multi_compound_label_is_not_a_single_graph_compound(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            graph_rows, audit_rows, _report = normalize_claims(
                mechanistic_rows=[],
                disorder_rows=[
                    {
                        "claim_type": "compound_disorder",
                        "compound": "LSD, psilocybin, MDMA",
                        "disorder": "MDD",
                        "graph_entity_label": "MDD",
                        "graph_entity_type": "indication",
                        "graph_include_candidate": True,
                        "entity_role": "therapeutic_indication",
                    }
                ],
                registry_path=registry(Path(tmpdir) / "registry.json"),
                disorder_aliases_path=disorder_aliases(Path(tmpdir) / "aliases.json"),
            )

        self.assertEqual(graph_rows["disorder"], [])
        self.assertEqual(audit_rows["disorder"][0]["normalization_status"], "compound_combo_not_graphable")

    def test_graph_entity_label_falls_back_to_structured_endpoint_slot(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            graph_rows, audit_rows, _report = normalize_claims(
                mechanistic_rows=[],
                disorder_rows=[
                    {
                        "claim_type": "compound_disorder",
                        "compound": "Ketamine",
                        "disorder": "MDD",
                        "graph_entity_label": "Depression",
                        "graph_entity_type": "indication",
                        "graph_include_candidate": True,
                        "entity_role": "therapeutic_indication",
                    }
                ],
                registry_path=registry(Path(tmpdir) / "registry.json"),
                disorder_aliases_path=disorder_aliases(Path(tmpdir) / "aliases.json"),
            )

        self.assertEqual(audit_rows["disorder"][0]["normalization_status"], "normalized")
        self.assertEqual(graph_rows["disorder"][0]["disorder"], "Major depressive disorder")


if __name__ == "__main__":
    unittest.main()
