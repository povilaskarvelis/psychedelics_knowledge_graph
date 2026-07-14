import copy
import json
import unittest
from pathlib import Path

from jsonschema import Draft7Validator


ROOT = Path(__file__).resolve().parents[1]


def load_schema() -> dict:
    return json.loads(
        (ROOT / "schema" / "extraction_profiles" / "meta_analysis" / "clinical_outcome.schema.json").read_text(
            encoding="utf-8"
        )
    )


def valid_payload() -> dict:
    return {
        "schema_version": "meta_analysis_evidence_v1",
        "task_id": "route-meta-clinical",
        "route_id": "route-meta-clinical",
        "study_doi": "10.1000/meta",
        "domain_route": "clinical_outcome",
        "source_type": "meta_analysis",
        "text_depth": "article_text",
        "source_text_provenance": {
            "text_depth": "article_text",
            "source_text_kind": "article_text",
            "source_text_scope": "article text supplied to the model",
        },
        "extraction_status": "extracted",
        "synthesis_assessment": {
            "is_in_scope": True,
            "is_meta_analysis": True,
            "is_network_meta_analysis": False,
            "has_extractable_quantitative_results": True,
            "relationship_domain": "clinical_outcome",
            "population_or_system": "Adults with depressive symptoms",
            "primary_compounds_or_classes": "psilocybin",
            "primary_entities": "depressive symptoms",
            "needs_human_review": False,
            "reasoning_summary": "The paper reports a pooled clinical outcome estimate.",
            "evidence_location": "abstract",
            "evidence_locator": "Abstract",
        },
        "included_evidence_summary": {
            "included_study_count": "5",
            "included_participant_count": "238",
            "included_experiment_or_assay_count": "not_applicable",
            "included_evidence_type_summary": "randomized clinical trials",
            "study_year_range": "2016-2023",
            "country_or_region_summary": "United States and Europe",
            "evidence_location": "abstract",
            "evidence_locator": "Abstract",
        },
        "synthesis_results": [
            {
                "result_id": "R1",
                "result_role": "main_result",
                "relationship_domain": "clinical_outcome",
                "compound_or_class": "psilocybin",
                "entity_type": "disorder",
                "entity": "depressive symptoms",
                "population_or_system": "Adults with depressive symptoms",
                "intervention_or_exposure": "psilocybin-assisted therapy",
                "comparator": "placebo or active control",
                "outcome_or_endpoint": "depressive symptom severity",
                "outcome_measure": "standardized depression scales",
                "timepoint_or_window": "primary endpoint",
                "effect_metric": "standardized mean difference",
                "effect_size": "-0.82",
                "study_count": "5",
                "participant_count": "238",
                "result_direction": "positive",
                "authors_interpretation": "Psilocybin was associated with reduced depressive symptoms.",
                "evidence_location": "figure",
                "evidence_locator": "Figure 2",
                "confidence": 0.95,
                "needs_human_review": False,
                "domain_result": {
                    "condition_or_population": "Adults with depressive symptoms",
                    "compound_or_intervention": "psilocybin-assisted therapy",
                    "comparator": "placebo or active control",
                    "dose_or_regimen": "not_reported",
                    "outcome_measure": "standardized depression scales",
                    "clinical_endpoint": "depressive symptom severity",
                    "assessment_timepoint": "primary endpoint",
                    "clinical_endpoint_category": "depression severity",
                    "effect_or_statistic": "SMD -0.82",
                    "synthesis_interpretation": "Psilocybin was associated with reduced depressive symptoms.",
                },
            }
        ],
        "extraction_warnings": [],
    }


class MetaAnalysisEvidenceSchemaTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.validator = Draft7Validator(load_schema())

    def assert_valid(self, payload: dict) -> None:
        errors = sorted(self.validator.iter_errors(payload), key=lambda error: list(error.path))
        self.assertEqual(errors, [], [error.message for error in errors])

    def test_accepts_meta_analysis_payload_with_effect_and_aggregate_evidence_summary(self) -> None:
        self.assert_valid(valid_payload())

    def test_requires_effect_size_fields_for_synthesis_results(self) -> None:
        payload = copy.deepcopy(valid_payload())
        payload["synthesis_results"][0].pop("effect_size")

        errors = sorted(self.validator.iter_errors(payload), key=lambda error: list(error.path))

        self.assertTrue(any("'effect_size' is a required property" in error.message for error in errors))

    def test_synthesis_schema_excludes_removed_low_value_fields(self) -> None:
        schema = load_schema()
        top_level_props = schema["properties"]
        assessment_props = schema["definitions"]["synthesis_assessment"]["properties"]
        included_summary_props = schema["definitions"]["included_evidence_summary"]["properties"]
        result_props = schema["definitions"]["synthesis_result"]["properties"]

        for field in (
            "search_methods",
            "eligibility_criteria",
            "risk_of_bias_assessments",
            "certainty_assessments",
            "authors_conclusions",
            "coverage_gaps",
        ):
            self.assertNotIn(field, top_level_props)
        for props in (assessment_props, included_summary_props, result_props):
            self.assertNotIn("supporting_quote", props)
        for field in (
            "analysis_type",
            "contrast_type",
            "ci_lower",
            "ci_upper",
            "model_type",
            "heterogeneity_tau2",
            "heterogeneity_q",
            "prediction_interval",
            "network_comparison",
            "network_evidence_type",
            "network_rank_or_score",
            "network_inconsistency_or_transitivity",
            "subgroup_or_sensitivity",
            "confidence_interval",
            "p_value",
            "heterogeneity_i2",
        ):
            self.assertNotIn(field, result_props)

        domain_schema_dir = ROOT / "schema" / "extraction_profiles" / "meta_analysis"
        removed_domain_fields = {
            "clinical_outcome.schema.json": {"response_or_remission_metric"},
            "safety_tolerability.schema.json": {
                "event_count_or_numerator_denominator",
                "discontinuation_or_withdrawal",
                "seriousness",
            },
            "brain_system.schema.json": {"neural_circuit", "connectivity_or_circuit_relationship"},
            "molecular_target.schema.json": {"unit"},
            "pharmacokinetics_exposure.schema.json": {
                "metabolic_or_transport_target",
                "metabolic_or_transport_pathway",
            },
        }
        for schema_name, fields in removed_domain_fields.items():
            domain_schema = json.loads((domain_schema_dir / schema_name).read_text(encoding="utf-8"))
            domain_result_props = domain_schema["definitions"]["synthesis_result"]["properties"]["domain_result"][
                "properties"
            ]
            for field in fields:
                self.assertNotIn(field, domain_result_props)

    def test_result_direction_uses_no_detected_effect_not_null(self) -> None:
        schema = load_schema()
        enum = schema["definitions"]["result_direction"]["enum"]

        self.assertIn("no_detected_effect", enum)
        self.assertNotIn("null", enum)

    def test_accepts_network_meta_analysis_as_core_result_fields(self) -> None:
        payload = copy.deepcopy(valid_payload())
        payload["source_type"] = "network_meta_analysis"
        payload["synthesis_assessment"]["is_network_meta_analysis"] = True
        payload["synthesis_results"][0].update(
            {
                "result_role": "network_comparison",
                "comparator": "escitalopram",
                "effect_metric": "standardized mean difference",
                "effect_size": "-0.31",
                "authors_interpretation": "The network meta-analysis favored psilocybin over escitalopram for symptom reduction.",
            }
        )

        self.assert_valid(payload)

    def test_domain_specific_clinical_schema_requires_clinical_domain_result(self) -> None:
        schema = json.loads(
            (ROOT / "schema" / "extraction_profiles" / "meta_analysis" / "clinical_outcome.schema.json").read_text(
                encoding="utf-8"
            )
        )
        validator = Draft7Validator(schema)
        payload = copy.deepcopy(valid_payload())
        payload["synthesis_results"][0]["domain_result"] = {
            "condition_or_population": "Adults with depressive symptoms",
            "compound_or_intervention": "psilocybin-assisted therapy",
            "comparator": "placebo or active control",
            "dose_or_regimen": "not_reported",
            "outcome_measure": "standardized depression scales",
            "clinical_endpoint": "depressive symptom severity",
            "assessment_timepoint": "primary endpoint",
            "clinical_endpoint_category": "depression severity",
            "effect_or_statistic": "SMD -0.82",
            "synthesis_interpretation": "Psilocybin was associated with reduced depressive symptoms.",
        }

        errors = sorted(validator.iter_errors(payload), key=lambda error: list(error.path))

        self.assertEqual(errors, [], [error.message for error in errors])

    def test_domain_specific_clinical_schema_accepts_core_domain_result_without_optional_details(self) -> None:
        schema = json.loads(
            (ROOT / "schema" / "extraction_profiles" / "meta_analysis" / "clinical_outcome.schema.json").read_text(
                encoding="utf-8"
            )
        )
        validator = Draft7Validator(schema)
        payload = copy.deepcopy(valid_payload())
        payload["synthesis_results"][0]["domain_result"] = {
            "condition_or_population": "Adults with depressive symptoms",
            "compound_or_intervention": "psilocybin-assisted therapy",
            "comparator": "placebo or active control",
            "dose_or_regimen": "not_reported",
            "outcome_measure": "standardized depression scales",
            "clinical_endpoint": "depressive symptom severity",
            "assessment_timepoint": "primary endpoint",
            "clinical_endpoint_category": "depression severity",
            "effect_or_statistic": "SMD -0.82",
            "synthesis_interpretation": "Psilocybin was associated with reduced depressive symptoms.",
        }

        errors = sorted(validator.iter_errors(payload), key=lambda error: list(error.path))

        self.assertEqual(errors, [], [error.message for error in errors])

    def test_domain_specific_safety_schema_requires_safety_domain_result(self) -> None:
        schema = json.loads(
            (ROOT / "schema" / "extraction_profiles" / "meta_analysis" / "safety_tolerability.schema.json").read_text(
                encoding="utf-8"
            )
        )
        validator = Draft7Validator(schema)
        payload = copy.deepcopy(valid_payload())
        payload["domain_route"] = "safety_tolerability"
        payload["synthesis_assessment"]["relationship_domain"] = "safety_tolerability"
        payload["synthesis_results"][0].update(
            {
                "relationship_domain": "safety_tolerability",
                "entity_type": "safety_event",
                "entity": "nausea",
                "result_direction": "negative",
                "domain_result": {
                    "compound_or_exposure": "psilocybin",
                    "population_or_system": "Adults with depressive symptoms",
                    "safety_event_or_measure": "nausea",
                    "safety_category": "adverse event",
                    "severity": "not_reported",
                    "assessment_window": "acute dosing period",
                    "frequency_or_rate": "not_reported",
                    "comparator": "placebo or active control",
                    "synthesis_interpretation": "Safety event was more frequent with psilocybin.",
                },
            }
        )

        errors = sorted(validator.iter_errors(payload), key=lambda error: list(error.path))

        self.assertEqual(errors, [], [error.message for error in errors])

    def test_domain_specific_molecular_target_schema_captures_target_context(self) -> None:
        schema = json.loads(
            (ROOT / "schema" / "extraction_profiles" / "meta_analysis" / "molecular_target.schema.json").read_text(
                encoding="utf-8"
            )
        )
        validator = Draft7Validator(schema)
        payload = copy.deepcopy(valid_payload())
        payload["domain_route"] = "molecular_target"
        payload["synthesis_assessment"]["relationship_domain"] = "molecular_target"
        payload["synthesis_assessment"]["primary_compounds_or_classes"] = "MDMA/ecstasy exposure"
        payload["synthesis_assessment"]["primary_entities"] = "serotonin transporter availability"
        payload["synthesis_results"][0].update(
            {
                "relationship_domain": "molecular_target",
                "compound_or_class": "MDMA",
                "entity_type": "target",
                "entity": "serotonin transporter",
                "population_or_system": "Ecstasy/polydrug users and controls",
                "intervention_or_exposure": "ecstasy/MDMA exposure",
                "comparator": "polydrug-using controls",
                "outcome_or_endpoint": "SERT availability",
                "outcome_measure": "molecular imaging",
                "effect_metric": "standardized mean difference",
                "effect_size": "0.52",
                "result_direction": "not_applicable",
                "authors_interpretation": "MDMA exposure was associated with lower SERT availability.",
                "domain_result": {
                    "compound": "MDMA/ecstasy",
                    "target": "serotonin transporter",
                    "target_type": "transporter",
                    "assay_type": "molecular imaging",
                    "system": "human molecular imaging studies",
                    "species_or_cell_line": "human",
                    "comparator_or_reference": "polydrug-using controls",
                    "action_type": "availability reduction",
                    "metric": "SMD",
                    "value": "0.52",
                    "synthesis_interpretation": "The synthesis reported lower SERT availability in ecstasy users across brain regions.",
                },
            }
        )

        errors = sorted(validator.iter_errors(payload), key=lambda error: list(error.path))

        self.assertEqual(errors, [], [error.message for error in errors])

    def test_domain_specific_molecular_pathway_schema_captures_readout_context(self) -> None:
        schema = json.loads(
            (
                ROOT / "schema" / "extraction_profiles" / "meta_analysis" / "molecular_pathway_readout.schema.json"
            ).read_text(encoding="utf-8")
        )
        validator = Draft7Validator(schema)
        payload = copy.deepcopy(valid_payload())
        payload["domain_route"] = "molecular_pathway_readout"
        payload["synthesis_assessment"]["relationship_domain"] = "molecular_pathway_readout"
        payload["synthesis_assessment"]["primary_compounds_or_classes"] = "psychoplastogens"
        payload["synthesis_assessment"]["primary_entities"] = "peripheral BDNF levels"
        payload["synthesis_results"][0].update(
            {
                "relationship_domain": "molecular_pathway_readout",
                "compound_or_class": "ketamine, LSD, psilocybin, and other psychoplastogens",
                "entity_type": "molecular_readout",
                "entity": "brain-derived neurotrophic factor",
                "population_or_system": "adult human subjects",
                "intervention_or_exposure": "single-dose psychoplastogen administration",
                "comparator": "baseline or control condition",
                "outcome_or_endpoint": "peripheral BDNF level",
                "outcome_measure": "blood BDNF",
                "timepoint_or_window": "all available post-treatment timepoints",
                "effect_metric": "standardized mean difference",
                "effect_size": "0.024",
                "result_direction": "not_applicable",
                "authors_interpretation": "Psychoplastogens did not significantly increase peripheral BDNF levels.",
                "domain_result": {
                    "compound_or_exposure": "ketamine, LSD, psilocybin, and other psychoplastogens",
                    "pathway_or_readout": "peripheral BDNF",
                    "assay_or_method": "blood BDNF meta-analysis",
                    "model_system": "adult human subjects",
                    "species_or_cell_line": "human",
                    "comparator_or_reference": "baseline or control condition",
                    "timepoint_or_window": "all available post-treatment timepoints",
                    "dose_or_exposure_context": "single-dose psychoplastogen exposure",
                    "direction_or_change": "no significant increase",
                    "quantitative_value": "SMD 0.024; p = 0.64",
                    "unit": "standardized mean difference",
                    "synthesis_interpretation": "The synthesis found no evidence that psychoplastogens rapidly increase peripheral BDNF.",
                },
            }
        )

        errors = sorted(validator.iter_errors(payload), key=lambda error: list(error.path))

        self.assertEqual(errors, [], [error.message for error in errors])

    def test_domain_specific_brain_system_schema_captures_neural_context(self) -> None:
        schema = json.loads(
            (ROOT / "schema" / "extraction_profiles" / "meta_analysis" / "brain_system.schema.json").read_text(
                encoding="utf-8"
            )
        )
        validator = Draft7Validator(schema)
        payload = copy.deepcopy(valid_payload())
        payload["domain_route"] = "brain_system"
        payload["synthesis_assessment"]["relationship_domain"] = "brain_system"
        payload["synthesis_assessment"]["primary_compounds_or_classes"] = "classic psychedelics"
        payload["synthesis_assessment"]["primary_entities"] = "large-scale functional connectivity"
        payload["synthesis_results"][0].update(
            {
                "relationship_domain": "brain_system",
                "compound_or_class": "psilocybin, LSD, mescaline, DMT, and ayahuasca",
                "entity_type": "brain_network",
                "entity": "large-scale cortical and subcortical networks",
                "population_or_system": "human resting-state fMRI datasets",
                "intervention_or_exposure": "acute psychedelic administration",
                "comparator": "placebo",
                "outcome_or_endpoint": "functional connectivity",
                "outcome_measure": "resting-state fMRI connectivity",
                "timepoint_or_window": "acute drug session",
                "effect_metric": "Bayesian posterior evidence",
                "effect_size": "not_reported",
                "result_direction": "not_applicable",
                "authors_interpretation": "Psychedelics reconfigured large-scale brain organization.",
                "domain_result": {
                    "compound_or_exposure": "classic psychedelics",
                    "population_or_system": "human resting-state fMRI datasets",
                    "modality": "resting-state fMRI",
                    "primary_graph_anchor_kind": "brain_network",
                    "brain_region": "thalamus, caudate, putamen, and cerebellum",
                    "brain_network": "transmodal, unimodal, subcortical, and cerebellar networks",
                    "readout": "functional connectivity",
                    "neural_effect_or_change": "increased between-network connectivity and selective within-network reductions",
                    "task_or_state": "resting state during acute psychedelic effects",
                    "comparator": "drug-placebo comparison",
                    "assessment_timepoint": "acute scanning session",
                    "dose_or_exposure_context": "acute psychedelic exposure",
                    "statistic_or_value": "posterior evidence for large-scale functional-connectivity changes",
                    "synthesis_interpretation": "The synthesis mapped acute psychedelic effects on large-scale brain circuit function.",
                },
            }
        )

        errors = sorted(validator.iter_errors(payload), key=lambda error: list(error.path))

        self.assertEqual(errors, [], [error.message for error in errors])

    def test_domain_specific_cognitive_behavioral_schema_captures_task_context(self) -> None:
        schema = json.loads(
            (
                ROOT / "schema" / "extraction_profiles" / "meta_analysis" / "cognitive_behavioral.schema.json"
            ).read_text(encoding="utf-8")
        )
        validator = Draft7Validator(schema)
        payload = copy.deepcopy(valid_payload())
        payload["domain_route"] = "cognitive_behavioral"
        payload["synthesis_assessment"]["relationship_domain"] = "cognitive_behavioral"
        payload["synthesis_assessment"]["primary_compounds_or_classes"] = "psilocybin"
        payload["synthesis_assessment"]["primary_entities"] = "attention and executive functioning"
        payload["synthesis_results"][0].update(
            {
                "relationship_domain": "cognitive_behavioral",
                "compound_or_class": "psilocybin",
                "entity_type": "cognitive_behavioral_construct",
                "entity": "reaction time on attention and executive-function tasks",
                "population_or_system": "healthy volunteers",
                "intervention_or_exposure": "acute psilocybin administration",
                "comparator": "placebo or control condition",
                "outcome_or_endpoint": "cognitive task performance",
                "outcome_measure": "reaction time",
                "timepoint_or_window": "acute phase",
                "effect_metric": "Hedges g",
                "effect_size": "1.13",
                "result_direction": "not_applicable",
                "authors_interpretation": "Psilocybin increased reaction times without a clear accuracy effect.",
                "domain_result": {
                    "compound_or_exposure": "psilocybin",
                    "population_or_species": "healthy human volunteers",
                    "construct_or_behavior": "cognitive task performance",
                    "task_or_measure": "attention and executive-function tasks",
                    "behavioral_context": "acute drug challenge",
                    "comparator": "placebo or control condition",
                    "dose_or_regimen": "acute psilocybin dose; dose moderated reaction-time effects",
                    "assessment_timepoint": "acute phase after administration",
                    "outcome_metric": "reaction time",
                    "behavioral_effect_or_change": "slower reaction time; no clear accuracy effect",
                    "statistic_or_value": "Hedges g = 1.13 for reaction time; Hedges g = -0.45 for accuracy",
                    "synthesis_interpretation": "The synthesis found acute psilocybin slowed task responses, with weaker evidence for accuracy changes.",
                },
            }
        )

        errors = sorted(validator.iter_errors(payload), key=lambda error: list(error.path))

        self.assertEqual(errors, [], [error.message for error in errors])

    def test_domain_specific_subjective_experience_schema_captures_scale_context(self) -> None:
        schema = json.loads(
            (ROOT / "schema" / "extraction_profiles" / "meta_analysis" / "subjective_experience.schema.json").read_text(
                encoding="utf-8"
            )
        )
        validator = Draft7Validator(schema)
        payload = copy.deepcopy(valid_payload())
        payload["domain_route"] = "subjective_experience"
        payload["synthesis_assessment"]["relationship_domain"] = "subjective_experience"
        payload["synthesis_assessment"]["primary_compounds_or_classes"] = "psilocybin"
        payload["synthesis_assessment"]["primary_entities"] = "acute subjective experience"
        payload["synthesis_results"][0].update(
            {
                "relationship_domain": "subjective_experience",
                "compound_or_class": "psilocybin",
                "entity_type": "subjective_experience_construct",
                "entity": "altered states of consciousness",
                "population_or_system": "healthy human participants",
                "intervention_or_exposure": "oral psilocybin",
                "comparator": "dose level",
                "outcome_or_endpoint": "subjective-experience scale score",
                "outcome_measure": "5D-ASC, 11-ASC, MEQ30, or HRS subscale",
                "timepoint_or_window": "acute dosing session",
                "effect_metric": "linear dose-response coefficient",
                "effect_size": "not_reported",
                "result_direction": "not_applicable",
                "authors_interpretation": "Most subjective-experience dimensions increased with psilocybin dose.",
                "domain_result": {
                    "compound_or_exposure": "oral psilocybin",
                    "population_or_system": "healthy human participants",
                    "subjective_construct_category": "altered state and mystical-type experience",
                    "subjective_construct": "psilocybin-induced subjective experience",
                    "instrument_or_measure": "5D-ASC, 11-ASC, MEQ30, and HRS questionnaires",
                    "setting_or_context": "experimental dosing studies",
                    "comparator_or_reference": "psilocybin dose level",
                    "dose_or_regimen": "oral psilocybin dose standardized to micrograms per kilogram",
                    "assessment_timepoint": "acute subjective-experience assessment after dosing",
                    "subjective_effect_or_change": "most scale ratings increased with dose",
                    "relationship_to_outcome": "potential mediation of therapeutic outcomes was discussed but not directly tested in this result",
                    "statistic_or_value": "dose-response coefficients reported by questionnaire factor and scale",
                    "synthesis_interpretation": "The synthesis estimated dose-response relationships for psilocybin-induced subjective-experience dimensions.",
                },
            }
        )

        errors = sorted(validator.iter_errors(payload), key=lambda error: list(error.path))

        self.assertEqual(errors, [], [error.message for error in errors])

    def test_domain_specific_pharmacokinetics_schema_captures_exposure_modifiers(self) -> None:
        schema = json.loads(
            (
                ROOT / "schema" / "extraction_profiles" / "meta_analysis" / "pharmacokinetics_exposure.schema.json"
            ).read_text(encoding="utf-8")
        )
        validator = Draft7Validator(schema)
        payload = copy.deepcopy(valid_payload())
        payload["domain_route"] = "pharmacokinetics_exposure"
        payload["synthesis_assessment"]["relationship_domain"] = "pharmacokinetics_exposure"
        payload["synthesis_assessment"]["primary_compounds_or_classes"] = "psilocybin"
        payload["synthesis_assessment"]["primary_entities"] = "dose-response relationship"
        payload["synthesis_results"][0].update(
            {
                "relationship_domain": "pharmacokinetics_exposure",
                "compound_or_class": "psilocybin",
                "entity_type": "pharmacokinetic_parameter",
                "entity": "oral psilocybin dose",
                "population_or_system": "healthy human participants",
                "intervention_or_exposure": "oral psilocybin",
                "comparator": "dose level",
                "outcome_or_endpoint": "dose-response relationship",
                "outcome_measure": "questionnaire factor or scale score",
                "timepoint_or_window": "acute dosing session",
                "effect_metric": "linear meta-regression coefficient",
                "effect_size": "not_reported",
                "result_direction": "not_applicable",
                "authors_interpretation": "Most subjective-experience ratings increased with psilocybin dose.",
                "domain_result": {
                    "compound_or_analyte": "psilocybin dose",
                    "primary_graph_anchor_kind": "pharmacokinetic_parameter",
                    "exposure_evidence_category": "dose-response",
                    "analyte_type": "dose/exposure index",
                    "metabolite_or_analyte": "psilocybin",
                    "matrix": "not_applicable",
                    "pk_or_exposure_parameter": "dose-response slope",
                    "value": "positive relationship for most questionnaire factors and scales",
                    "unit": "not_reported",
                    "dose": "oral psilocybin across included dose range",
                    "route_of_administration": "oral",
                    "sampling_time_or_window": "acute subjective-experience assessment after dosing",
                    "population_or_system": "healthy human participants",
                    "comparator_or_reference": "psilocybin dose level",
                    "exposure_response_or_pk_effect": "most ratings increased with dose, with variability across scales",
                    "synthesis_interpretation": "The synthesis estimated exposure-response relationships between oral psilocybin dose and acute subjective effects.",
                },
            }
        )

        errors = sorted(validator.iter_errors(payload), key=lambda error: list(error.path))

        self.assertEqual(errors, [], [error.message for error in errors])

    def test_domain_specific_intervention_context_schema_captures_protocol_context(self) -> None:
        schema = json.loads(
            (ROOT / "schema" / "extraction_profiles" / "meta_analysis" / "intervention_context.schema.json").read_text(
                encoding="utf-8"
            )
        )
        validator = Draft7Validator(schema)
        payload = copy.deepcopy(valid_payload())
        payload["domain_route"] = "intervention_context"
        payload["synthesis_assessment"]["relationship_domain"] = "intervention_context"
        payload["synthesis_assessment"]["primary_compounds_or_classes"] = "psychedelic-assisted therapy"
        payload["synthesis_assessment"]["primary_entities"] = "psychological therapy quantity"
        payload["synthesis_results"][0].update(
            {
                "relationship_domain": "intervention_context",
                "compound_or_class": "psychedelic-assisted therapy",
                "entity_type": "intervention_component",
                "entity": "preparation therapy hours",
                "population_or_system": "participants with depressive symptoms",
                "intervention_or_exposure": "psychedelic-assisted therapy with psychological therapy",
                "comparator": "lower quantity of preparation therapy",
                "outcome_or_endpoint": "depressive symptom reduction",
                "outcome_measure": "standardized depression scales",
                "timepoint_or_window": "after final dosing session and follow-up",
                "effect_metric": "meta-regression coefficient",
                "effect_size": "beta = -0.13",
                "result_direction": "not_applicable",
                "authors_interpretation": "More preparation hours were associated with larger depressive symptom reduction.",
                "domain_result": {
                    "compound_or_intervention": "psychedelic-assisted therapy for depressive symptoms",
                    "context_component": "preparation therapy",
                    "component_type": "therapy quantity",
                    "population_or_setting": "controlled trials of participants with depressive symptoms",
                    "delivery_format": "psychological therapy sessions delivered alongside psychedelic dosing",
                    "comparator_or_control": "less preparation therapy or control-condition context across included trials",
                    "relationship_to_outcome_or_safety": "more preparation hours were associated with greater depressive symptom reduction",
                    "dose_or_session_context": "number and duration of psychological therapy sessions, number of dosing sessions, and total treatment duration",
                    "timepoint_or_phase": "preparation phase before psychedelic dosing",
                    "synthesis_interpretation": "The synthesis suggests preparation therapy quantity may be an intervention-context contributor to antidepressant outcomes.",
                },
            }
        )

        errors = sorted(validator.iter_errors(payload), key=lambda error: list(error.path))

        self.assertEqual(errors, [], [error.message for error in errors])

    def test_domain_specific_real_world_schema_captures_public_health_context(self) -> None:
        schema = json.loads(
            (ROOT / "schema" / "extraction_profiles" / "meta_analysis" / "real_world_public_health.schema.json").read_text(
                encoding="utf-8"
            )
        )
        validator = Draft7Validator(schema)
        payload = copy.deepcopy(valid_payload())
        payload["domain_route"] = "real_world_public_health"
        payload["synthesis_assessment"]["relationship_domain"] = "real_world_public_health"
        payload["synthesis_assessment"]["primary_compounds_or_classes"] = "psychedelic-assisted psychotherapy"
        payload["synthesis_assessment"]["primary_entities"] = "stakeholder attitudes"
        payload["synthesis_results"][0].update(
            {
                "relationship_domain": "real_world_public_health",
                "compound_or_class": "psychedelic-assisted psychotherapy",
                "entity_type": "public_health_measure",
                "entity": "stakeholder attitudes toward psychedelic-assisted psychotherapy",
                "population_or_system": "health professionals, patients, and public samples",
                "intervention_or_exposure": "psychedelic-assisted psychotherapy",
                "comparator": "stakeholder groups",
                "outcome_or_endpoint": "attitudes and implementation barriers",
                "outcome_measure": "survey-reported perceptions",
                "effect_metric": "qualitative synthesis",
                "effect_size": "not_reported",
                "result_direction": "not_applicable",
                "authors_interpretation": "Knowledge was low and attitudes were mixed to positive across stakeholder groups.",
                "domain_result": {
                    "exposure_or_policy": "psychedelic-assisted psychotherapy",
                    "population": "health professionals, patients, and the public",
                    "setting": "survey studies in public and clinical stakeholder groups",
                    "public_health_topic_category": "stakeholder attitudes and implementation",
                    "data_source_or_study_design": "cross-sectional, longitudinal, and quasi-experimental studies",
                    "public_health_measure": "knowledge, attitudes, perceived therapeutic potential, and implementation barriers",
                    "estimate_value": "mixed to positive belief in therapeutic potential; low knowledge",
                    "estimate_unit": "qualitative synthesis",
                    "comparison_or_reference_group": "health professionals vs patients vs public samples",
                    "association_or_trend": "personal psychedelic experience and knowledge were associated with more favorable views",
                    "time_window": "not_reported",
                    "synthesis_interpretation": "The synthesis identifies stakeholder knowledge and attitudes as implementation-relevant public-health evidence.",
                },
            }
        )

        errors = sorted(validator.iter_errors(payload), key=lambda error: list(error.path))

        self.assertEqual(errors, [], [error.message for error in errors])

    def test_domain_specific_synthesis_result_fields_have_descriptions(self) -> None:
        for path in (ROOT / "schema" / "extraction_profiles" / "meta_analysis").glob("*.schema.json"):
            with self.subTest(schema=path.name):
                schema = json.loads(path.read_text(encoding="utf-8"))
                domain_result = schema["definitions"]["synthesis_result"]["properties"]["domain_result"]
                missing = [
                    field
                    for field, field_schema in domain_result["properties"].items()
                    if not field_schema.get("description")
                ]

                self.assertEqual(missing, [])

    def test_prompt_profile_excludes_individual_included_study_extraction(self) -> None:
        prompt = (ROOT / "docs" / "extraction_profiles" / "paper_type" / "meta_analysis_article_text.md").read_text(encoding="utf-8")
        prompt_one_line = " ".join(prompt.split())

        self.assertIn("Do not extract individual included study records", prompt)
        self.assertIn("included-study DOIs", prompt)
        self.assertIn("effect size", prompt_one_line)
        self.assertIn("network meta-analyses", prompt)
        self.assertNotIn("included_studies", prompt)
        self.assertNotIn("Do not infer DOIs", prompt)
        self.assertIn("synthesis_results[]", prompt)
        self.assertNotIn("network_rank_or_score", prompt)
        self.assertNotIn("If the study list is long", prompt_one_line)


if __name__ == "__main__":
    unittest.main()
