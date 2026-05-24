import copy
import unittest

from pipeline.extract.project_extraction_v1_claims import (
    extraction_schema_errors_for_results,
    is_in_scope_projected_compound,
    is_non_article_artifact,
    normalize_outcome_measure,
    output_stem,
    project_secondary_coverage,
    project_results,
    report_filename,
    schema_errors_for_rows,
)


def assessment(system: str = "clinical") -> dict:
    return {
        "relevance": "relevant",
        "route": "primary_evidence",
        "source_family": "original_empirical",
        "source_type": "primary_study",
        "paper_type": "primary_results",
        "study_design": "randomized_controlled_trial" if system == "clinical" else "radioligand_binding_assay",
        "system": system,
        "has_original_results": True,
        "has_extractable_claims": True,
        "evidence_location": "text",
        "evidence_locator": "Results",
        "supporting_quote": "A directly supported result was reported.",
        "confidence": 0.9,
        "needs_human_review": False,
        "reasoning_summary": "Original empirical evidence.",
    }


def disorder_result() -> dict:
    return {
        "schema_version": "extraction_v1",
        "dataset": "disorder",
        "study_doi": "10.1000/disorder",
        "access_level": "full_text_seen",
        "paper_assessment": assessment(),
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
                "outcome_type": "depressive symptom change",
                "outcome_measure": "MADRS",
                "result_direction": "positive",
                "sample_size_total": "59",
                "population": "Adults with major depressive disorder",
                "comparator": "Escitalopram",
                "intervention_or_exposure": "Psilocybin-assisted therapy",
                "evidence_location": "text",
                "evidence_locator": "Results",
                "supporting_quote": "A directly supported result was reported.",
                "confidence": 0.9,
                "needs_human_review": False,
            }
        ],
        "coverage_mentions": [],
    }


def mechanistic_result() -> dict:
    return {
        "schema_version": "extraction_v1",
        "dataset": "mechanistic",
        "study_doi": "10.1000/mech",
        "access_level": "full_text_seen",
        "paper_assessment": assessment(system="in_vitro"),
        "claims": [
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
                "study_design": "radioligand_binding_assay",
                "system": "in_vitro",
                "assay_type": "radioligand binding",
                "affinity_type": "Ki",
                "affinity_value": "2.1",
                "affinity_unit": "nM",
                "result_direction": "not_applicable",
                "species": "human",
                "evidence_location": "table",
                "evidence_locator": "Table 1",
                "supporting_quote": "A directly supported result was reported.",
                "confidence": 0.9,
                "needs_human_review": False,
            }
        ],
        "coverage_mentions": [],
    }


def paper_libraries() -> dict:
    return {
        "disorder": {
            "10.1000/disorder": {
                "study_doi": "10.1000/disorder",
                "study_title": "A psilocybin depression trial",
                "authors": "Smith et al.",
                "study_year": 2024,
                "study_journal": "Journal of Clinical Psychedelic Research",
            }
        },
        "mechanistic": {
            "10.1000/mech": {
                "study_doi": "10.1000/mech",
                "study_title": "LSD receptor binding",
                "authors": "Garcia et al.",
                "study_year": 2023,
                "study_journal": "Neuropharmacology",
            }
        },
    }


class ProjectExtractionV1ClaimsTest(unittest.TestCase):
    def test_default_projection_output_names_are_canonical_extraction_claims(self) -> None:
        self.assertEqual(output_stem("mechanistic", ""), "mechanistic_claims")
        self.assertEqual(output_stem("disorder", ""), "disorder_claims")
        self.assertEqual(output_stem("mechanistic", "calibration"), "calibration_mechanistic_claims")
        self.assertEqual(report_filename(""), "projection_report.json")

    def test_projected_compound_scope_filter_keeps_psychedelics_and_excludes_generic_substances(self) -> None:
        self.assertTrue(is_in_scope_projected_compound("MDMA"))
        self.assertTrue(is_in_scope_projected_compound("(±)-DOI"))
        self.assertTrue(is_in_scope_projected_compound("(+/-)-2,5-dimethoxy-4-iodoamphetamine"))
        self.assertTrue(is_in_scope_projected_compound("S-ketamine"))
        self.assertFalse(is_in_scope_projected_compound("Alcohol"))
        self.assertFalse(is_in_scope_projected_compound("memantine"))

    def test_projects_supported_disorder_claims_into_curated_schema_rows(self) -> None:
        projected, skipped = project_results([disorder_result()], paper_libraries(), {})

        self.assertEqual(skipped, [])
        self.assertEqual(projected["mechanistic"], [])
        self.assertEqual(len(projected["disorder"]), 1)
        row = projected["disorder"][0]
        self.assertEqual(row["compound"], "Psilocybin")
        self.assertEqual(row["disorder"], "Major depressive disorder")
        self.assertEqual(row["raw_entity_label"], "Major depressive disorder")
        self.assertTrue(row["graph_include_candidate"])
        self.assertEqual(row["result_direction"], "positive")
        self.assertEqual(row["sample_size_total"], "59")
        self.assertEqual(row["outcome_measure_normalized"], "MADRS")
        self.assertEqual(row["authors"], "Smith et al.")
        self.assertEqual(schema_errors_for_rows("disorder", projected["disorder"]), [])

    def test_normalizes_outcome_measure_to_scale_without_replacing_raw_measure(self) -> None:
        result = disorder_result()
        result["claims"][0]["outcome_measure"] = (
            "response (decrease of at least 50% in the Montgomery-Åsberg Depression Rating Scale)"
        )

        projected, _skipped = project_results([result], paper_libraries(), {})
        row = projected["disorder"][0]

        self.assertEqual(row["outcome_measure"], result["claims"][0]["outcome_measure"])
        self.assertEqual(row["outcome_measure_normalized"], "MADRS")

    def test_normalizes_multiple_outcome_scales(self) -> None:
        self.assertEqual(
            normalize_outcome_measure("DASS-21 depression subscale, BSI-18 depression subscale"),
            "DASS-21; BSI-18",
        )

    def test_preserves_therapeutic_positive_direction_for_reduced_pathological_behavior(self) -> None:
        result = disorder_result()
        result["claims"][0].update(
            {
                "compound": "Ibogaine",
                "disorder": "Alcohol use disorder",
                "outcome_type": "reduced alcohol seeking",
                "outcome_measure": "ethanol CPP reinstatement",
                "result_direction": "positive",
            }
        )

        projected, skipped = project_results([result], paper_libraries(), {})

        self.assertEqual(skipped, [])
        self.assertEqual(projected["disorder"][0]["result_direction"], "positive")

    def test_projection_removes_placeholder_metadata_values(self) -> None:
        result = disorder_result()
        result["paper_assessment"]["trial_registry_ids"] = "not_reported"
        result["paper_assessment"]["funding"] = "not_applicable"
        result["claims"][0]["study_design"] = "not_reported"
        libraries = paper_libraries()
        libraries["disorder"]["10.1000/disorder"]["trial_registry_ids"] = "not_reported"
        libraries["disorder"]["10.1000/disorder"]["publisher"] = "unknown"

        projected, skipped = project_results([result], libraries, {})

        self.assertEqual(skipped, [])
        row = projected["disorder"][0]
        self.assertNotIn("trial_registry_ids", row)
        self.assertNotIn("publisher", row)
        self.assertEqual(row["funding"], "")
        self.assertEqual(row["study_design"], "randomized_controlled_trial")

    def test_projects_supported_mechanistic_claims_into_curated_schema_rows(self) -> None:
        projected, skipped = project_results([mechanistic_result()], paper_libraries(), {})

        self.assertEqual(skipped, [])
        self.assertEqual(projected["disorder"], [])
        self.assertEqual(len(projected["mechanistic"]), 1)
        row = projected["mechanistic"][0]
        self.assertEqual(row["compound"], "LSD")
        self.assertEqual(row["target"], "5-HT2A")
        self.assertEqual(row["entity_role"], "molecular_target")
        self.assertTrue(row["graph_include_candidate"])
        self.assertEqual(row["affinity_value"], 2.1)
        self.assertEqual(row["affinity_unit"], "nM")
        self.assertEqual(row["authors"], "Garcia et al.")
        self.assertEqual(schema_errors_for_rows("mechanistic", projected["mechanistic"]), [])

    def test_mechanistic_projection_maps_unreported_numeric_function_type_to_other(self) -> None:
        result = mechanistic_result()
        result["claims"][0]["affinity_type"] = "not_reported"
        result["claims"][0]["affinity_value"] = "66.4"
        result["claims"][0]["affinity_unit"] = "percentage inhibition"

        projected, skipped = project_results([result], paper_libraries(), {})

        self.assertEqual(skipped, [])
        self.assertEqual(projected["mechanistic"][0]["affinity_type"], "Other")
        self.assertEqual(schema_errors_for_rows("mechanistic", projected["mechanistic"]), [])

    def test_projects_review_needed_and_non_affinity_mechanistic_claims_for_inspection(self) -> None:
        needs_review = copy.deepcopy(disorder_result())
        needs_review["claims"][0]["needs_human_review"] = True
        no_affinity_value = copy.deepcopy(mechanistic_result())
        no_affinity_value["claims"][0]["affinity_value"] = "not_reported"
        no_affinity_value["claims"][0]["affinity_unit"] = "not_reported"

        projected, skipped = project_results([needs_review, no_affinity_value], paper_libraries(), {})

        self.assertEqual(skipped, [])
        self.assertEqual(len(projected["disorder"]), 1)
        self.assertEqual(len(projected["mechanistic"]), 1)
        self.assertTrue(projected["disorder"][0]["needs_human_review"])
        self.assertEqual(projected["mechanistic"][0]["affinity_value"], "")
        self.assertEqual(projected["mechanistic"][0]["mechanism_type"], "radioligand binding")
        self.assertEqual(schema_errors_for_rows("mechanistic", projected["mechanistic"]), [])

    def test_projects_out_of_scope_compounds_for_inspection(self) -> None:
        result = disorder_result()
        result["claims"][0]["compound"] = "Alcohol"

        projected, skipped = project_results([result], paper_libraries(), {})

        self.assertEqual(skipped, [])
        self.assertEqual(projected["disorder"][0]["compound"], "Alcohol")
        self.assertEqual(schema_errors_for_rows("disorder", projected["disorder"]), [])

    def test_skips_prior_irrelevant_pilot_controls_by_default(self) -> None:
        result = disorder_result()
        result["input_record_id"] = "pilot-old-negative"
        contexts = {
            ("input_record_id", "pilot-old-negative"): {
                "pilot_record": {
                    "bucket": "abstract_irrelevant",
                    "expected_screening_relevance": "irrelevant",
                }
            }
        }

        projected, skipped = project_results([result], paper_libraries(), contexts)

        self.assertEqual(projected["disorder"], [])
        self.assertEqual(skipped, [{"row_index": 1, "reason": "prior irrelevant screening control is not projected"}])

        included, included_skipped = project_results(
            [result],
            paper_libraries(),
            contexts,
            include_irrelevant_controls=True,
        )
        self.assertEqual(included_skipped, [])
        self.assertEqual(len(included["disorder"]), 1)

    def test_non_article_artifacts_are_not_projected_even_if_model_marks_primary(self) -> None:
        result = mechanistic_result()
        result["study_doi"] = "10.7554/elife.35082.027"
        libraries = paper_libraries()
        libraries["mechanistic"]["10.7554/elife.35082.027"] = {
            "study_doi": "10.7554/elife.35082.027",
            "study_title": "Decision letter: Changes in global and thalamic brain connectivity",
            "authors": "",
            "study_year": 2018,
            "publication_type": "peer-review",
        }

        projected, skipped = project_results([result], libraries, {})

        self.assertEqual(projected["mechanistic"], [])
        self.assertEqual(projected["disorder"], [])
        self.assertEqual(skipped, [{"row_index": 1, "reason": "non-article artifact is not projected"}])
        self.assertTrue(is_non_article_artifact(libraries["mechanistic"]["10.7554/elife.35082.027"]))

    def test_reports_invalid_extraction_results_before_projection(self) -> None:
        invalid = copy.deepcopy(disorder_result())
        invalid["paper_assessment"]["relevance"] = "not_relevant"

        errors = extraction_schema_errors_for_results([invalid])

        self.assertTrue(errors)
        self.assertEqual(errors[0]["row_index"], 1)
        self.assertTrue(any("exclude" in error["message"] for error in errors))

    def test_secondary_literature_route_is_not_projected(self) -> None:
        review = copy.deepcopy(disorder_result())
        review["paper_assessment"].update(
            {
                "route": "secondary_literature",
                "source_family": "evidence_synthesis",
                "source_type": "review",
                "paper_type": "systematic_review",
                "has_original_results": False,
                "has_extractable_claims": False,
            }
        )
        review["claims"] = []
        review["coverage_mentions"] = [
            {
                "coverage_type": "reviews",
                "relationship_domain": "compound_disorder",
                "compound": "Psilocybin",
                "entity_type": "disorder",
                "entity": "Major depressive disorder",
                "evidence_location": "text",
                "evidence_locator": "Abstract",
                "supporting_quote": "A directly supported result was reported.",
                "confidence": 0.8,
                "needs_human_review": False,
            }
        ]

        projected, skipped = project_results([review], paper_libraries(), {})

        self.assertEqual(projected["disorder"], [])
        self.assertEqual(projected["mechanistic"], [])
        self.assertEqual(skipped, [{"row_index": 1, "reason": "route secondary_literature is not projected"}])

    def test_secondary_coverage_mentions_project_to_separate_rows(self) -> None:
        review = copy.deepcopy(disorder_result())
        review["paper_assessment"].update(
            {
                "route": "secondary_literature",
                "source_family": "evidence_synthesis",
                "source_type": "review",
                "paper_type": "review",
                "study_design": "narrative review",
                "has_original_results": False,
                "has_extractable_claims": False,
            }
        )
        review["claims"] = []
        review["coverage_mentions"] = [
            {
                "coverage_type": "reviews",
                "relationship_domain": "compound_disorder",
                "compound": "Psilocybin",
                "entity_type": "disorder",
                "entity": "Major depressive disorder",
                "evidence_location": "abstract",
                "evidence_locator": "Abstract",
                "supporting_quote": "A directly supported result was reported.",
                "confidence": 0.8,
                "needs_human_review": False,
            },
            {
                "coverage_type": "reviews",
                "relationship_domain": "compound_target",
                "compound": "LSD",
                "entity_type": "target",
                "entity": "5-HT2A",
                "evidence_location": "abstract",
                "evidence_locator": "Abstract",
                "supporting_quote": "A directly supported result was reported.",
                "confidence": 0.7,
                "needs_human_review": False,
            },
        ]

        projected, skipped = project_secondary_coverage([review], paper_libraries(), {})

        self.assertEqual(skipped, [])
        self.assertEqual(len(projected["disorder"]), 1)
        self.assertEqual(len(projected["mechanistic"]), 1)
        disorder_row = projected["disorder"][0]
        self.assertEqual(disorder_row["paper_assessment_route"], "secondary_literature")
        self.assertEqual(disorder_row["access_level"], "secondary_summary")
        self.assertEqual(disorder_row["source_access_level"], "full_text_seen")
        self.assertEqual(disorder_row["compound"], "Psilocybin")
        self.assertEqual(disorder_row["disorder"], "Major depressive disorder")
        self.assertEqual(schema_errors_for_rows("disorder", projected["disorder"]), [])
        self.assertEqual(schema_errors_for_rows("mechanistic", projected["mechanistic"]), [])


if __name__ == "__main__":
    unittest.main()
