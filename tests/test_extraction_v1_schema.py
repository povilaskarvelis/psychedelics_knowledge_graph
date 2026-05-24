import copy
import json
import unittest
from pathlib import Path

from jsonschema import Draft7Validator


ROOT = Path(__file__).resolve().parents[1]


def load_schema() -> dict:
    return json.loads((ROOT / "schema" / "extraction_v1.schema.json").read_text(encoding="utf-8"))


def base_result() -> dict:
    return {
        "schema_version": "extraction_v1",
        "dataset": "disorder",
        "study_doi": "10.1000/test",
        "access_level": "full_text_seen",
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
            "evidence_location": "text",
            "evidence_locator": "Results",
            "supporting_quote": "Participants receiving psilocybin improved on depression measures.",
            "confidence": 0.9,
            "needs_human_review": False,
            "reasoning_summary": "Direct clinical outcome evidence.",
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
                "outcome_domain": "depression",
                "outcome_type": "depressive symptom change",
                "outcome_measure": "MADRS",
                "result_direction": "positive",
                "evidence_location": "text",
                "evidence_locator": "Results",
                "supporting_quote": "Participants receiving psilocybin improved on depression measures.",
                "confidence": 0.9,
                "needs_human_review": False,
            }
        ],
        "coverage_mentions": [],
    }


class ExtractionV1SchemaTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.validator = Draft7Validator(load_schema())

    def assert_valid(self, payload: dict) -> None:
        errors = sorted(self.validator.iter_errors(payload), key=lambda error: list(error.path))
        self.assertEqual(errors, [], [error.message for error in errors])

    def assert_invalid(self, payload: dict) -> list[str]:
        errors = sorted(self.validator.iter_errors(payload), key=lambda error: list(error.path))
        self.assertTrue(errors, "expected payload to be invalid")
        return [error.message for error in errors]

    def test_accepts_minimal_valid_disorder_claim(self) -> None:
        self.assert_valid(base_result())

    def test_accepts_mixed_system_and_preprint_paper_type(self) -> None:
        payload = base_result()
        payload["paper_assessment"]["system"] = "mixed"
        payload["paper_assessment"]["paper_type"] = "preprint"
        payload["claims"][0]["system"] = "mixed"

        self.assert_valid(payload)

    def test_not_relevant_requires_exclude_reason_and_zero_claims(self) -> None:
        payload = base_result()
        payload["paper_assessment"]["relevance"] = "not_relevant"
        payload["paper_assessment"]["has_extractable_claims"] = False

        messages = self.assert_invalid(payload)

        self.assertTrue(any("'exclude' was expected" in message for message in messages))
        self.assertTrue(any("'exclusion_reason' is a required property" in message for message in messages))
        self.assertTrue(any("is expected to be empty" in message for message in messages))

        valid = copy.deepcopy(payload)
        valid["paper_assessment"]["route"] = "exclude"
        valid["paper_assessment"]["exclusion_reason"] = "No in-scope psychedelic compound relationship is reported."
        valid["claims"] = []
        valid["coverage_mentions"] = []
        self.assert_valid(valid)

    def test_primary_evidence_requires_original_results_and_claims(self) -> None:
        payload = base_result()
        payload["paper_assessment"]["has_original_results"] = False
        payload["paper_assessment"]["has_extractable_claims"] = False
        payload["claims"] = []

        messages = self.assert_invalid(payload)

        self.assertTrue(any("True was expected" in message for message in messages))
        self.assertTrue(any("should be non-empty" in message for message in messages))

    def test_disorder_claim_requires_result_direction_and_outcome_fields(self) -> None:
        payload = base_result()
        claim = payload["claims"][0]
        claim.pop("result_direction")
        claim.pop("outcome_type")
        claim.pop("outcome_measure")

        messages = self.assert_invalid(payload)

        self.assertTrue(any("'result_direction' is a required property" in message for message in messages))
        self.assertTrue(any("'outcome_type' is a required property" in message for message in messages))
        self.assertTrue(any("'outcome_measure' is a required property" in message for message in messages))

    def test_disorder_claim_allows_positive_direction_for_reduced_pathological_behavior(self) -> None:
        payload = base_result()
        payload["claims"][0].update(
            {
                "compound": "Ibogaine",
                "disorder": "Alcohol use disorder",
                "outcome_type": "reduced alcohol seeking",
                "outcome_measure": "ethanol conditioned place preference reinstatement",
                "result_direction": "positive",
                "supporting_quote": "Ibogaine blocked cue- and drug-induced reinstatement of ethanol CPP.",
            }
        )
        payload["paper_assessment"]["supporting_quote"] = "Ibogaine blocked cue- and drug-induced reinstatement of ethanol CPP."

        self.assert_valid(payload)

    def test_disorder_claim_allows_not_applicable_affinity_slots(self) -> None:
        payload = base_result()
        payload["claims"][0].update(
            {
                "affinity_type": "not_applicable",
                "affinity_value": "not_applicable",
                "affinity_unit": "not_applicable",
            }
        )

        self.assert_valid(payload)

    def test_disorder_claim_allows_non_graph_endpoint_role_fields(self) -> None:
        payload = base_result()
        payload["claims"][0].update(
            {
                "disorder": "not_applicable",
                "raw_entity_label": "Heart Rate",
                "entity_role": "physiological_measure",
                "clinical_context_condition": "Post-traumatic stress disorder patients undergoing laparoscopy",
                "outcome_domain": "cardiovascular_safety",
                "outcome_measure": "Heart rate (HR)",
                "graph_entity_label": "not_applicable",
                "graph_entity_type": "none",
                "graph_include_candidate": False,
                "graph_exclusion_reason": "Raw endpoint is a physiological safety measure, not a therapeutic indication.",
            }
        )

        self.assert_valid(payload)

    def test_mechanistic_claim_allows_gene_variant_role_fields(self) -> None:
        payload = base_result()
        payload["dataset"] = "mechanistic"
        payload["claims"] = [
            {
                "claim_type": "compound_target",
                "compound": "MDMA",
                "target": "SLC6A2",
                "disorder": "not_applicable",
                "raw_entity_label": "SLC6A2 rs1861647 GG genotype",
                "entity_role": "gene_or_variant",
                "clinical_context_condition": "healthy subjects",
                "graph_entity_label": "not_applicable",
                "graph_entity_type": "none",
                "graph_include_candidate": False,
                "graph_exclusion_reason": "Genotype is a pharmacogenetic moderator rather than a clean compound-target edge.",
                "support": "supported",
                "study_design": "pooled analysis",
                "system": "clinical",
                "assay_type": "clinical measurement of heart rate",
                "affinity_type": "not_reported",
                "result_direction": "not_applicable",
                "evidence_location": "abstract",
                "evidence_locator": "Abstract",
                "supporting_quote": "Carriers of the GG genotype of the SLC6A2 rs1861647 SNP presented higher elevations of heart rate.",
                "confidence": 0.9,
                "needs_human_review": False,
            }
        ]

        self.assert_valid(payload)

    def test_non_graph_endpoint_roles_cannot_be_graph_candidates(self) -> None:
        payload = base_result()
        payload["claims"][0].update(
            {
                "raw_entity_label": "Heart rate",
                "entity_role": "physiological_measure",
                "disorder": "not_applicable",
                "graph_entity_label": "none",
                "graph_entity_type": "none",
                "graph_include_candidate": True,
            }
        )

        messages = self.assert_invalid(payload)

        self.assertTrue(any("False was expected" in message for message in messages))

    def test_mechanistic_claim_requires_assay_fields_and_not_applicable_disorder(self) -> None:
        payload = base_result()
        payload["dataset"] = "mechanistic"
        payload["claims"] = [
            {
                "claim_type": "compound_target",
                "compound": "LSD",
                "target": "5-HT2A",
                "disorder": "not_applicable",
                "raw_entity_label": "5-HT2A",
                "entity_role": "molecular_target",
                "clinical_context_condition": "not_applicable",
                "graph_entity_label": "5-HT2A",
                "graph_entity_type": "target",
                "graph_include_candidate": True,
                "graph_exclusion_reason": "not_applicable",
                "support": "supported",
                "study_design": "in_vitro_binding_assay",
                "system": "in_vitro",
                "assay_type": "radioligand binding",
                "affinity_type": "Ki",
                "result_direction": "not_applicable",
                "evidence_location": "table",
                "evidence_locator": "Table 1",
                "supporting_quote": "LSD bound 5-HT2A with Ki values in the nanomolar range.",
                "confidence": 0.9,
                "needs_human_review": False,
            }
        ]

        self.assert_valid(payload)

        invalid = copy.deepcopy(payload)
        invalid["claims"][0].pop("assay_type")
        invalid["claims"][0]["disorder"] = "Major depressive disorder"
        messages = self.assert_invalid(invalid)

        self.assertTrue(any("'assay_type' is a required property" in message for message in messages))
        self.assertTrue(any("'not_applicable' was expected" in message for message in messages))

    def test_mechanistic_claim_rejects_noncanonical_affinity_type(self) -> None:
        payload = base_result()
        payload["dataset"] = "mechanistic"
        payload["claims"] = [
            {
                "claim_type": "compound_target",
                "compound": "LSD",
                "target": "5-HT2A",
                "disorder": "not_applicable",
                "raw_entity_label": "5-HT2A",
                "entity_role": "molecular_target",
                "clinical_context_condition": "not_applicable",
                "graph_entity_label": "5-HT2A",
                "graph_entity_type": "target",
                "graph_include_candidate": True,
                "graph_exclusion_reason": "not_applicable",
                "support": "supported",
                "study_design": "in_vitro_binding_assay",
                "system": "in_vitro",
                "assay_type": "radioligand binding",
                "affinity_type": "KD",
                "result_direction": "not_applicable",
                "evidence_location": "table",
                "evidence_locator": "Table 1",
                "supporting_quote": "LSD bound 5-HT2A with Ki values in the nanomolar range.",
                "confidence": 0.9,
                "needs_human_review": False,
            }
        ]

        messages = self.assert_invalid(payload)

        self.assertTrue(any("'KD' is not one of" in message for message in messages))

    def test_abstract_only_disallows_table_or_figure_evidence_locations(self) -> None:
        payload = base_result()
        payload["access_level"] = "abstract_only"
        payload["paper_assessment"]["evidence_location"] = "abstract"
        payload["claims"][0]["evidence_location"] = "table"

        messages = self.assert_invalid(payload)

        self.assertTrue(any("'table' is not one of" in message for message in messages))

    def test_secondary_literature_is_paper_level_only(self) -> None:
        payload = base_result()
        payload["paper_assessment"].update(
            {
                "route": "secondary_literature",
                "source_family": "evidence_synthesis",
                "source_type": "systematic_review",
                "paper_type": "systematic_review",
                "has_original_results": False,
                "has_extractable_claims": False,
                "study_design": "systematic_review",
                "system": "not_applicable",
                "evidence_location": "abstract",
                "evidence_locator": "Abstract",
                "supporting_quote": "This systematic review summarizes clinical trials of psilocybin.",
                "reasoning_summary": "In-scope secondary literature only.",
            }
        )
        payload["claims"] = []
        payload["coverage_mentions"] = [
            {
                "coverage_type": "reviews",
                "relationship_domain": "compound_disorder",
                "compound": "Psilocybin",
                "entity_type": "disorder",
                "entity": "Major depressive disorder",
                "evidence_location": "abstract",
                "evidence_locator": "Abstract",
                "supporting_quote": "This systematic review summarizes clinical trials of psilocybin.",
                "confidence": 0.9,
                "needs_human_review": False,
            }
        ]
        self.assert_valid(payload)

        invalid = copy.deepcopy(payload)
        invalid["claims"] = [copy.deepcopy(base_result()["claims"][0])]
        messages = self.assert_invalid(invalid)
        self.assertTrue(any("is expected to be empty" in message for message in messages))

        invalid_source = copy.deepcopy(payload)
        invalid_source["paper_assessment"]["source_family"] = "original_empirical"
        messages = self.assert_invalid(invalid_source)
        self.assertTrue(any("'evidence_synthesis' was expected" in message for message in messages))

        invalid_empty_coverage = copy.deepcopy(payload)
        invalid_empty_coverage["coverage_mentions"] = []
        messages = self.assert_invalid(invalid_empty_coverage)
        self.assertTrue(any("should be non-empty" in message for message in messages))

    def test_context_only_is_paper_level_only(self) -> None:
        payload = base_result()
        payload["paper_assessment"].update(
            {
                "route": "context_only",
                "source_family": "opinion_or_commentary",
                "source_type": "commentary",
                "paper_type": "commentary",
                "has_original_results": False,
                "has_extractable_claims": False,
                "study_design": "not_applicable",
                "system": "not_applicable",
                "evidence_location": "abstract",
                "evidence_locator": "Abstract",
                "supporting_quote": "This commentary discusses psychedelic therapy.",
                "reasoning_summary": "In-scope context but not extractable evidence.",
            }
        )
        payload["claims"] = []
        payload["coverage_mentions"] = []
        self.assert_valid(payload)

        invalid = copy.deepcopy(payload)
        invalid["claims"] = [copy.deepcopy(base_result()["claims"][0])]
        messages = self.assert_invalid(invalid)
        self.assertTrue(any("is expected to be empty" in message for message in messages))

    def test_primary_evidence_disallows_coverage_mentions(self) -> None:
        payload = base_result()
        payload["coverage_mentions"] = [
            {
                "coverage_type": "discusses",
                "relationship_domain": "compound_disorder",
                "compound": "Psilocybin",
                "entity_type": "disorder",
                "entity": "Major depressive disorder",
                "evidence_location": "text",
                "evidence_locator": "Introduction",
                "supporting_quote": "The paper discusses psilocybin and depression.",
                "confidence": 0.7,
                "needs_human_review": False,
            }
        ]

        messages = self.assert_invalid(payload)
        self.assertTrue(any("is expected to be empty" in message for message in messages))

    def test_coverage_relationship_domain_requires_matching_entity_type(self) -> None:
        payload = base_result()
        payload["paper_assessment"].update(
            {
                "route": "secondary_literature",
                "source_family": "evidence_synthesis",
                "source_type": "review",
                "paper_type": "review",
                "has_original_results": False,
                "has_extractable_claims": False,
                "study_design": "narrative_review",
                "system": "not_applicable",
                "evidence_location": "abstract",
                "evidence_locator": "Abstract",
                "supporting_quote": "This review discusses psilocybin and depression.",
                "reasoning_summary": "In-scope secondary literature only.",
            }
        )
        payload["claims"] = []
        payload["coverage_mentions"] = [
            {
                "coverage_type": "reviews",
                "relationship_domain": "compound_disorder",
                "compound": "Psilocybin",
                "entity_type": "target",
                "entity": "Major depressive disorder",
                "evidence_location": "abstract",
                "evidence_locator": "Abstract",
                "supporting_quote": "This review discusses psilocybin and depression.",
                "confidence": 0.85,
                "needs_human_review": False,
            }
        ]

        messages = self.assert_invalid(payload)
        self.assertTrue(any("'disorder' was expected" in message for message in messages))


if __name__ == "__main__":
    unittest.main()
