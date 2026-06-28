import copy
import json
from pathlib import Path

from jsonschema import Draft7Validator


ROOT = Path(__file__).resolve().parents[1]
REVIEW_SCHEMA_DIR = ROOT / "schema" / "extraction_profiles" / "review"


def load_schema(domain: str) -> dict:
    return json.loads((REVIEW_SCHEMA_DIR / f"{domain}.schema.json").read_text(encoding="utf-8"))


def valid_clinical_payload() -> dict:
    quote = (
        "Data suggest that ketamine has a rapid albeit transient effect in "
        "reducing suicidal ideation."
    )
    return {
        "schema_version": "review_coverage_v1",
        "task_id": "route-review-clinical",
        "route_id": "route-review-clinical",
        "study_doi": "10.1000/review",
        "domain_route": "clinical_outcome",
        "source_type": "review",
        "text_depth": "article_text",
        "source_text_provenance": {
            "text_depth": "article_text",
            "source_text_kind": "article_text",
            "source_text_scope": "article text supplied to the model",
        },
        "extraction_status": "extracted",
        "review_assessment": {
            "is_in_scope": True,
            "review_type": "narrative review",
            "has_extractable_scoped_coverage": True,
            "relationship_domain": "clinical_outcome",
            "population_or_system": "Adults with depression",
            "primary_compounds_or_classes": "ketamine",
            "primary_entities": "suicidal ideation",
            "needs_human_review": False,
            "reasoning_summary": "The review discusses clinical outcomes in the selected domain.",
            "evidence_location": "abstract",
            "evidence_locator": "Abstract",
        },
        "coverage_items": [
            {
                "item_id": "C1",
                "relationship_domain": "clinical_outcome",
                "coverage_type": "reviews",
                "coverage_focus": "substantial_topic",
                "compound_or_class": "ketamine",
                "entity_type": "symptom_or_outcome",
                "entity": "suicidal ideation",
                "population_or_system": "Patients at risk for suicide",
                "reviewed_evidence_type": "open-label and randomized controlled trials",
                "summary_statement": "The review describes ketamine as having a rapid but transient effect on suicidal ideation.",
                "direction_or_tone": "supports",
                "participant_or_sample_summary": "not_reported",
                "key_limitations": "small samples, mixed timepoint results, and possible functional unblinding",
                "evidence_location": "text",
                "evidence_locator": "Abstract",
                "confidence": 0.85,
                "needs_human_review": False,
                "domain_result": {
                    "condition_or_population": "Patients deemed at risk for suicide",
                    "compound_or_intervention": "ketamine",
                    "clinical_topic": "anti-suicidal effect",
                    "clinical_endpoint": "suicidal ideation",
                    "clinical_endpoint_category": "suicidality",
                    "outcome_measure_or_instrument": "suicidal ideation assessments",
                    "comparator_or_context": "open-label and randomized controlled trials",
                    "dose_or_regimen": "not_reported",
                    "time_window": "rapid but transient effect across reviewed timepoints",
                    "response_or_remission_metric": "not_applicable",
                    "clinical_effect_or_statistic": "rapid but transient reduction in suicidal ideation; mixed results at different timepoints or assessments",
                    "certainty_or_evidence_quality": "limited evidence",
                    "review_interpretation": "The review coverage is about rapid clinical effects on suicidal ideation.",
                },
            }
        ],
        "extraction_warnings": [],
    }


def test_domain_specific_clinical_review_schema_accepts_valid_payload() -> None:
    schema = load_schema("clinical_outcome")
    errors = sorted(Draft7Validator(schema).iter_errors(valid_clinical_payload()), key=lambda error: list(error.path))

    assert errors == [], [error.message for error in errors]


def test_domain_specific_clinical_review_schema_excludes_removed_low_value_fields() -> None:
    schema = load_schema("clinical_outcome")
    coverage_item = schema["definitions"]["coverage_item"]
    domain_result = schema["definitions"]["coverage_item"]["properties"]["domain_result"]["properties"]

    assert "evidence_gaps" not in schema["properties"]
    assert "study_count" not in coverage_item["required"]
    assert "study_count" not in coverage_item["properties"]
    for field in (
        "response_definition",
        "remission_definition",
        "moderator_or_predictor",
        "score_direction_or_benefit_basis",
        "treatment_role_or_claim",
    ):
        assert field not in domain_result


def test_review_domain_schemas_exclude_pilot_low_yield_fields() -> None:
    removed_domain_fields = {
        "safety_tolerability": {"event_count_or_numerator_denominator", "discontinuation_or_withdrawal"},
        "brain_system": {"connectivity_or_circuit_relationship", "statistic_or_value"},
        "molecular_pathway_readout": {"quantitative_value", "unit"},
        "molecular_target": {"metric_or_value"},
        "pharmacokinetics_exposure": {"sampling_time_or_window"},
    }

    for domain, fields in removed_domain_fields.items():
        schema = load_schema(domain)
        domain_result = schema["definitions"]["coverage_item"]["properties"]["domain_result"]
        for field in fields:
            assert field not in domain_result["required"]
            assert field not in domain_result["properties"]


def test_domain_specific_safety_review_schema_requires_safety_domain_result() -> None:
    schema = load_schema("safety_tolerability")
    payload = copy.deepcopy(valid_clinical_payload())
    quote = (
        "Chronic abuse of ketamine can lead to significant urinary system "
        "complications including ketamine-induced cystitis."
    )
    payload["domain_route"] = "safety_tolerability"
    payload["review_assessment"].update(
        {
            "relationship_domain": "safety_tolerability",
            "population_or_system": "recreational ketamine users",
            "primary_compounds_or_classes": "ketamine",
            "primary_entities": "ketamine-induced cystitis",
            "reasoning_summary": "The review discusses urinary safety risks from chronic ketamine exposure.",
        }
    )
    payload["coverage_items"][0].update(
        {
            "relationship_domain": "safety_tolerability",
            "entity_type": "safety_event",
            "entity": "ketamine-induced cystitis",
            "population_or_system": "recreational ketamine users",
            "summary_statement": "The review describes chronic ketamine abuse as a cause of urinary complications including cystitis.",
            "direction_or_tone": "does_not_support",
            "evidence_locator": "Abstract",
            "domain_result": {
                "compound_or_exposure": "ketamine",
                "population_or_context": "chronic recreational ketamine users",
                "safety_event_or_risk": "ketamine-induced cystitis and urinary pain",
                "safety_category": "urinary toxicity",
                "severity_or_seriousness": "significant urinary system complications",
                "frequency_or_rate": "not_reported",
                "comparator_or_reference": "not_reported",
                "exposure_or_session_context": "chronic recreational ketamine exposure",
                "time_window": "long-term chronic exposure",
                "review_interpretation": "The review coverage is about urinary toxicity from chronic ketamine exposure.",
            },
        }
    )
    errors = sorted(Draft7Validator(schema).iter_errors(payload), key=lambda error: list(error.path))

    assert errors == [], [error.message for error in errors]


def test_domain_specific_molecular_target_review_schema_captures_target_method_and_values() -> None:
    schema = load_schema("molecular_target")
    payload = copy.deepcopy(valid_clinical_payload())
    quote = (
        "Using agonist radiolabelling, the Ki values of DOI for human 5-HT2A, "
        "5-HT2B, and 5-HT2C receptors were 0.7, 20, and 2.4 nM."
    )
    payload["domain_route"] = "molecular_target"
    payload["review_assessment"].update(
        {
            "relationship_domain": "molecular_target",
            "population_or_system": "human recombinant receptor systems",
            "primary_compounds_or_classes": "DOI",
            "primary_entities": "5-HT2 receptor subtypes",
            "reasoning_summary": "The review discusses direct receptor affinity and agonism.",
        }
    )
    payload["coverage_items"][0].update(
        {
            "relationship_domain": "molecular_target",
            "coverage_type": "reviews",
            "compound_or_class": "DOI",
            "entity_type": "target",
            "entity": "5-HT2 receptor subtypes",
            "population_or_system": "human recombinant receptor systems",
            "reviewed_evidence_type": "radioligand binding and receptor pharmacology review",
            "summary_statement": "The review describes DOI as a high-affinity potent agonist at 5-HT2 receptor subtypes.",
            "direction_or_tone": "descriptive_only",
            "participant_or_sample_summary": "not_applicable",
            "key_limitations": "reviewed values vary by subtype and assay context",
            "evidence_location": "text",
            "evidence_locator": "Pharmacology of DOI",
            "domain_result": {
                "compound_or_class": "DOI",
                "target": "5-HT2A, 5-HT2B, and 5-HT2C receptors",
                "target_type": "serotonin receptor subtype",
                "assay_or_method": "agonist radiolabelling",
                "comparator_or_reference": "human 5-HT2 receptor subtypes",
                "action_or_interaction": "potent agonist",
                "target_effect_or_change": "high affinity at 5-HT2 receptor subtypes",
                "system_or_species": "human receptor systems",
                "review_interpretation": "The review coverage characterizes DOI's direct serotonin receptor pharmacology.",
            },
        }
    )
    errors = sorted(Draft7Validator(schema).iter_errors(payload), key=lambda error: list(error.path))

    assert errors == [], [error.message for error in errors]


def test_domain_specific_molecular_pathway_review_schema_captures_readout_context_and_change() -> None:
    schema = load_schema("molecular_pathway_readout")
    payload = copy.deepcopy(valid_clinical_payload())
    quote = (
        "Ketamine rapidly increases synaptic connections in the prefrontal cortex "
        "by increasing glutamate signaling and activation of pathways that control "
        "the synthesis of synaptic proteins."
    )
    payload["domain_route"] = "molecular_pathway_readout"
    payload["review_assessment"].update(
        {
            "relationship_domain": "molecular_pathway_readout",
            "population_or_system": "rodent stress models and treatment-resistant depression literature",
            "primary_compounds_or_classes": "ketamine",
            "primary_entities": "glutamate signaling and synaptic protein synthesis",
            "reasoning_summary": "The review discusses molecular pathway/readout mechanisms linked to ketamine response.",
        }
    )
    payload["coverage_items"][0].update(
        {
            "relationship_domain": "molecular_pathway_readout",
            "coverage_type": "reviews",
            "compound_or_class": "ketamine",
            "entity_type": "pathway_process",
            "entity": "glutamate signaling and synaptogenesis",
            "population_or_system": "prefrontal cortex in depression and stress models",
            "reviewed_evidence_type": "preclinical and clinical mechanism review",
            "summary_statement": "The review links ketamine's rapid antidepressant mechanism to glutamate signaling and synaptic protein synthesis pathways.",
            "direction_or_tone": "descriptive_only",
            "participant_or_sample_summary": "not_reported",
            "key_limitations": "mechanistic evidence is reviewed across preclinical and clinical contexts",
            "evidence_location": "abstract",
            "evidence_locator": "Abstract",
            "domain_result": {
                "compound_or_exposure": "ketamine",
                "pathway_or_process": "glutamate signaling and synaptic protein synthesis pathways",
                "readout_or_biomarker": "synaptic connections",
                "readout_category": "synaptic plasticity and neurotrophic signaling",
                "biological_system": "brain and prefrontal-cortex pathway review",
                "model_or_species": "rodent stress models and treatment-resistant depression literature",
                "tissue_cell_or_sample": "brain tissue",
                "comparator_or_reference": "chronic stress or depression-related synaptic deficits",
                "timepoint_or_window": "rapid after ketamine exposure",
                "dose_or_exposure_context": "single subanesthetic ketamine exposure",
                "direction_or_change": "increased synaptic connections and activated synaptic protein synthesis pathways",
                "review_interpretation": "The review coverage is about ketamine-linked molecular plasticity mechanisms.",
            },
        }
    )
    errors = sorted(Draft7Validator(schema).iter_errors(payload), key=lambda error: list(error.path))

    assert errors == [], [error.message for error in errors]


def test_domain_specific_brain_system_review_schema_captures_network_context_and_change() -> None:
    schema = load_schema("brain_system")
    payload = copy.deepcopy(valid_clinical_payload())
    quote = (
        "Subjective effects are associated with increased delta and theta "
        "oscillations in amygdala and hippocampal regions, decreased alpha "
        "wave activity in the default mode network, and stimulations of "
        "vision-related brain regions."
    )
    payload["domain_route"] = "brain_system"
    payload["review_assessment"].update(
        {
            "relationship_domain": "brain_system",
            "population_or_system": "human ayahuasca and DMT literature",
            "primary_compounds_or_classes": "ayahuasca and DMT",
            "primary_entities": "oscillations and brain networks",
            "reasoning_summary": "The review discusses brain-system effects tied to subjective psychedelic effects.",
        }
    )
    payload["coverage_items"][0].update(
        {
            "relationship_domain": "brain_system",
            "coverage_type": "reviews",
            "compound_or_class": "ayahuasca and DMT",
            "entity_type": "brain_network",
            "entity": "amygdala, hippocampus, default mode network, and visual association cortex",
            "population_or_system": "human psychedelic experience literature",
            "reviewed_evidence_type": "narrative review of neurophysiology and neuroimaging evidence",
            "summary_statement": "The review links ayahuasca and DMT subjective effects to oscillatory and network-level brain changes.",
            "direction_or_tone": "descriptive_only",
            "participant_or_sample_summary": "not_reported",
            "key_limitations": "evidence is not sufficient to make confident conclusions about the proposed models",
            "evidence_location": "abstract",
            "evidence_locator": "Abstract",
            "domain_result": {
                "compound_or_exposure": "ayahuasca and DMT",
                "primary_graph_anchor_kind": "brain_network",
                "brain_region": "amygdala, hippocampus, and visual association cortex",
                "brain_network": "default mode network",
                "neural_circuit": "limbic and visual-region effects",
                "modality_or_evidence_type": "EEG oscillation and neuroimaging evidence",
                "readout_or_measure": "delta and theta oscillations, alpha wave activity, and visual-region stimulation",
                "neural_effect_or_alteration": "increased delta/theta oscillations, decreased alpha wave activity, and stimulation of vision-related regions",
                "task_or_state": "acute subjective psychedelic state",
                "system_or_species": "human",
                "comparator_or_reference": "not_reported",
                "timepoint_or_window": "acute subjective effects",
                "dose_or_exposure_context": "ayahuasca or DMT exposure",
                "direction_or_change": "increased delta/theta, decreased alpha, and stimulated visual-region activity",
                "review_interpretation": "The review coverage is about brain-system correlates of ayahuasca and DMT experiences.",
            },
        }
    )
    errors = sorted(Draft7Validator(schema).iter_errors(payload), key=lambda error: list(error.path))

    assert errors == [], [error.message for error in errors]


def test_domain_specific_cognitive_behavioral_review_schema_captures_task_metric_and_change() -> None:
    schema = load_schema("cognitive_behavioral")
    payload = copy.deepcopy(valid_clinical_payload())
    quote = (
        "SERT availability positively correlated with time of abstinence, "
        "whereas memory performance did not show this correlation, but "
        "remained impaired in MDMA users."
    )
    payload["domain_route"] = "cognitive_behavioral"
    payload["review_assessment"].update(
        {
            "relationship_domain": "cognitive_behavioral",
            "population_or_system": "abstinent MDMA users",
            "primary_compounds_or_classes": "MDMA",
            "primary_entities": "memory, attention, and executive function",
            "reasoning_summary": "The review discusses cognitive outcomes in abstinent MDMA users.",
        }
    )
    payload["coverage_items"][0].update(
        {
            "relationship_domain": "cognitive_behavioral",
            "coverage_type": "reviews",
            "compound_or_class": "MDMA",
            "entity_type": "cognitive_behavioral_construct",
            "entity": "memory and neurocognitive function",
            "population_or_system": "abstinent MDMA users",
            "reviewed_evidence_type": "review of SERT availability and cognitive performance studies",
            "summary_statement": "The review describes memory impairment in abstinent MDMA users and no clear recovery correlation with SERT availability.",
            "direction_or_tone": "mixed",
            "participant_or_sample_summary": "abstinent MDMA users",
            "key_limitations": "long-term neurocognitive effects and reversibility remain debated",
            "evidence_location": "abstract",
            "evidence_locator": "Abstract",
            "domain_result": {
                "compound_or_exposure": "MDMA",
                "construct_category": "memory, attention, and executive function",
                "behavior_or_task": "neurocognitive performance in abstinent MDMA users",
                "model_or_measure": "memory, attention, and executive-function performance measures",
                "behavioral_context": "long-term neurocognitive outcomes after recreational MDMA exposure",
                "population_or_species": "abstinent MDMA users",
                "dose_or_regimen": "not_reported",
                "comparator_or_reference": "time of abstinence and SERT availability",
                "timepoint_or_window": "abstinence and recovery over time",
                "outcome_metric": "memory performance and other cognitive performance measures",
                "behavioral_effect_or_change": "memory performance remained impaired and did not correlate with SERT recovery",
                "statistic_or_value": "no significant correlation between SERT availability and memory function",
                "review_interpretation": "The review coverage is about long-term cognitive outcomes after MDMA exposure.",
            },
        }
    )
    errors = sorted(Draft7Validator(schema).iter_errors(payload), key=lambda error: list(error.path))

    assert errors == [], [error.message for error in errors]


def test_domain_specific_subjective_experience_review_schema_captures_measure_context_and_outcome_link() -> None:
    schema = load_schema("subjective_experience")
    payload = copy.deepcopy(valid_clinical_payload())
    quote = (
        "Controlled laboratory studies show that under double-blind conditions "
        "psilocybin can occasion complete mystical experiences in the majority "
        "of people studied. These effects are dose-dependent, specific to "
        "psilocybin compared to placebo or a psychoactive control substance, "
        "and have enduring impact on moods, attitudes, and behaviors."
    )
    payload["domain_route"] = "subjective_experience"
    payload["review_assessment"].update(
        {
            "relationship_domain": "subjective_experience",
            "population_or_system": "healthy volunteers and clinical psychedelic research participants",
            "primary_compounds_or_classes": "psilocybin",
            "primary_entities": "mystical-type experience",
            "reasoning_summary": "The review discusses psilocybin-occasioned mystical-type experiences and their outcome links.",
        }
    )
    payload["coverage_items"][0].update(
        {
            "relationship_domain": "subjective_experience",
            "coverage_type": "reviews",
            "compound_or_class": "psilocybin",
            "entity_type": "subjective_experience_construct",
            "entity": "mystical-type experience",
            "population_or_system": "healthy volunteers and clinical psychedelic research participants",
            "reviewed_evidence_type": "narrative review of laboratory and clinical psychedelic studies",
            "summary_statement": "The review describes dose-dependent psilocybin-occasioned mystical-type experiences and links them to enduring mood, attitude, and behavior changes.",
            "direction_or_tone": "supports",
            "participant_or_sample_summary": "healthy volunteers and patients in psychedelic studies",
            "key_limitations": "more work is needed to define mechanisms and clinical applicability",
            "evidence_location": "abstract",
            "evidence_locator": "Abstract",
            "domain_result": {
                "compound_or_exposure": "psilocybin",
                "population_or_system": "healthy volunteers and clinical psychedelic research participants",
                "subjective_construct_category": "mystical-type experience",
                "subjective_construct": "complete mystical experience occasioned by psilocybin",
                "instrument_or_phenomenological_frame": "psychometrically validated mystical-type experience questionnaire",
                "dose_or_regimen": "dose-dependent psilocybin administration",
                "comparator_or_reference": "placebo or psychoactive control substance",
                "timepoint_or_window": "acute session with enduring follow-up impact",
                "subjective_effect_or_change": "psilocybin can occasion complete mystical experiences in many participants",
                "relationship_to_outcome": "enduring impact on moods, attitudes, and behaviors",
                "statistic_or_value": "majority of people studied; exact percentage not reported in the source text",
                "review_interpretation": "The review coverage is about measured mystical-type experiences as a subjective mechanism candidate.",
            },
        }
    )
    errors = sorted(Draft7Validator(schema).iter_errors(payload), key=lambda error: list(error.path))

    assert errors == [], [error.message for error in errors]


def test_domain_specific_pharmacokinetics_review_schema_captures_parameter_value_route_and_modifier() -> None:
    schema = load_schema("pharmacokinetics_exposure")
    payload = copy.deepcopy(valid_clinical_payload())
    quote = (
        "All studies administered DMT intravenously in various infusion schemes, "
        "except for one intramuscular administration. High variability in "
        "dose-normalized exposure parameters and differences in exposure for "
        "bolus versus infusion administration were observed."
    )
    payload["domain_route"] = "pharmacokinetics_exposure"
    payload["review_assessment"].update(
        {
            "relationship_domain": "pharmacokinetics_exposure",
            "population_or_system": "human DMT clinical pharmacokinetic datasets",
            "primary_compounds_or_classes": "DMT",
            "primary_entities": "dose-normalized exposure parameters",
            "reasoning_summary": "The review synthesizes human pharmacokinetic parameters for DMT administration.",
        }
    )
    payload["coverage_items"][0].update(
        {
            "relationship_domain": "pharmacokinetics_exposure",
            "coverage_type": "reviews",
            "compound_or_class": "DMT",
            "entity_type": "pharmacokinetic_parameter",
            "entity": "dose-normalized exposure",
            "population_or_system": "humans receiving known DMT doses",
            "reviewed_evidence_type": "systematic review and post-hoc analysis of clinical PK datasets",
            "summary_statement": "The review describes route- and scheme-dependent variability in DMT exposure parameters.",
            "direction_or_tone": "descriptive_only",
            "participant_or_sample_summary": "human clinical studies administering known DMT amounts",
            "key_limitations": "heterogeneous infusion schemes and variability in dose-normalized exposure",
            "evidence_location": "abstract",
            "evidence_locator": "Abstract",
            "domain_result": {
                "compound_or_analyte": "DMT",
                "primary_graph_anchor_kind": "pharmacokinetic_parameter",
                "exposure_evidence_category": "clinical pharmacokinetics and dose-normalized exposure",
                "analyte_type": "parent compound",
                "metabolic_or_transport_target": "not_reported",
                "metabolic_or_transport_pathway": "not_reported",
                "metabolite_or_analyte": "DMT",
                "pk_or_exposure_parameter": "dose-normalized exposure parameters and volume of distribution",
                "value": "high variability; terminal volume of distribution reported elsewhere in the review as 123-1084",
                "unit": "L for volume of distribution; not reported for dose-normalized exposure in the source text",
                "dose_route_or_formulation": "known DMT doses administered mostly intravenously in bolus or infusion schemes",
                "route_of_administration": "intravenous bolus or infusion; one intramuscular study",
                "population_or_system": "human clinical DMT studies",
                "comparator_or_reference": "bolus versus infusion administration and intravenous versus intramuscular administration",
                "matrix_or_sample": "not_reported",
                "review_interpretation": "The review coverage is about human DMT pharmacokinetics and route-dependent exposure variability.",
            },
        }
    )
    errors = sorted(Draft7Validator(schema).iter_errors(payload), key=lambda error: list(error.path))

    assert errors == [], [error.message for error in errors]


def test_domain_specific_intervention_context_review_schema_captures_delivery_coordination_and_fidelity() -> None:
    schema = load_schema("intervention_context")
    payload = copy.deepcopy(valid_clinical_payload())
    quote = (
        "There is currently no cohesive framework to guide collaboration or "
        "care coordination between external therapists and PAT teams. The "
        "review suggests that PAT should not generally be conceptualized as a "
        "standalone treatment."
    )
    payload["domain_route"] = "intervention_context"
    payload["review_assessment"].update(
        {
            "relationship_domain": "intervention_context",
            "population_or_system": "patients receiving psychedelic-assisted therapy in clinical practice",
            "primary_compounds_or_classes": "psychedelic-assisted therapy",
            "primary_entities": "external therapist and PAT team collaboration",
            "reasoning_summary": "The review discusses delivery models and care coordination around psychedelic-assisted therapy.",
        }
    )
    payload["coverage_items"][0].update(
        {
            "relationship_domain": "intervention_context",
            "coverage_type": "reviews",
            "compound_or_class": "psychedelic-assisted therapy",
            "entity_type": "intervention_component",
            "entity": "external therapist collaboration",
            "population_or_system": "patients with treatment-resistant depression or PTSD receiving PAT",
            "reviewed_evidence_type": "literature review and multidisciplinary clinical guidance",
            "summary_statement": "The review argues that PAT should not be treated as standalone care and needs coordinated collaboration between external therapists and PAT teams.",
            "direction_or_tone": "supports",
            "participant_or_sample_summary": "patients entering PAT from routine clinical care",
            "key_limitations": "no cohesive framework currently guides collaboration or care coordination",
            "evidence_location": "abstract",
            "evidence_locator": "Abstract",
            "domain_result": {
                "compound_or_intervention": "psychedelic-assisted therapy",
                "context_component": "external therapist and PAT-team care coordination",
                "component_type": "care coordination and provider collaboration",
                "dose_or_session_context": "before, during, and after psychedelic-assisted therapy sessions",
                "timepoint_or_phase": "preparation, dosing-session support, integration, and follow-up",
                "population_or_setting": "routine clinical practice for treatment-resistant depression and PTSD",
                "delivery_format": "collaboration between external therapists, psychiatrists, and PAT teams",
                "comparator_or_control": "standalone treatment model",
                "relationship_to_outcome_or_safety": "coordination is framed as supporting safe, effective, and integrated delivery",
                "review_interpretation": "The review coverage is about how PAT should be delivered and coordinated in clinical practice.",
            },
        }
    )
    errors = sorted(Draft7Validator(schema).iter_errors(payload), key=lambda error: list(error.path))

    assert errors == [], [error.message for error in errors]


def test_domain_specific_real_world_public_health_review_schema_captures_measure_estimate_and_bias_context() -> None:
    schema = load_schema("real_world_public_health")
    payload = copy.deepcopy(valid_clinical_payload())
    quote = (
        "Systematic review of Pubmed/MEDLINE, EMBASE, and Web of Science for "
        "studies of any design testing a psychedelic treatment for a psychiatric "
        "or substance use disorder published between January 1, 1994 and May 24, 2024."
    )
    payload["domain_route"] = "real_world_public_health"
    payload["review_assessment"].update(
        {
            "relationship_domain": "real_world_public_health",
            "population_or_system": "clinical studies of psychedelic treatment",
            "primary_compounds_or_classes": "serotonergic psychedelics and MDMA",
            "primary_entities": "ethnoracial inclusion in clinical psychedelic studies",
            "reasoning_summary": "The review discusses equity-relevant inclusion metrics in psychedelic studies.",
        }
    )
    payload["coverage_items"][0].update(
        {
            "relationship_domain": "real_world_public_health",
            "coverage_type": "reviews",
            "compound_or_class": "serotonergic psychedelics and MDMA",
            "entity_type": "public_health_measure",
            "entity": "ethnoracial inclusion rates",
            "population_or_system": "participants in clinical psychedelic treatment studies",
            "reviewed_evidence_type": "systematic review of clinical psychedelic studies",
            "summary_statement": "The review evaluates ethnoracial inclusion in clinical trials of psychedelic treatments.",
            "direction_or_tone": "descriptive_only",
            "participant_or_sample_summary": "psychedelic treatment studies for psychiatric or substance use disorders",
            "key_limitations": "study quality and reporting heterogeneity may affect interpretation of inclusion rates",
            "evidence_location": "abstract",
            "evidence_locator": "Abstract",
            "domain_result": {
                "exposure_or_intervention": "psychedelic treatment for psychiatric or substance use disorders",
                "population_or_setting": "clinical psychedelic studies and their enrolled participants",
                "public_health_topic_category": "access, equity, and ethnoracial inclusion",
                "data_source_or_study_design": "systematic review of PubMed/MEDLINE, EMBASE, and Web of Science",
                "public_health_measure": "racial and ethnic inclusion rates",
                "estimate_value": "limited ethnoracial diversity; exact estimate not reported in the source text",
                "estimate_unit": "qualitative synthesis",
                "comparison_or_reference_group": "studies published between January 1, 1994 and May 24, 2024",
                "association_or_trend": "clinical psychedelic studies have limited ethnoracial diversity",
                "time_window": "January 1, 1994 to May 24, 2024",
                "review_interpretation": "The review coverage is about whether psychedelic evidence is representative enough for equitable public-health implementation.",
            },
        }
    )
    errors = sorted(Draft7Validator(schema).iter_errors(payload), key=lambda error: list(error.path))

    assert errors == [], [error.message for error in errors]


def test_all_review_domain_schemas_are_domain_constrained_and_documented() -> None:
    paths = sorted(REVIEW_SCHEMA_DIR.glob("*.schema.json"))

    assert len(paths) == 12
    for path in paths:
        domain = path.name.removesuffix(".schema.json")
        schema = json.loads(path.read_text(encoding="utf-8"))
        coverage_item = schema["definitions"]["coverage_item"]
        domain_result = coverage_item["properties"]["domain_result"]
        missing_descriptions = [
            field
            for field, field_schema in domain_result["properties"].items()
            if not field_schema.get("description")
        ]

        assert schema["properties"]["domain_route"]["const"] == domain
        assert schema["definitions"]["domain_route"]["const"] == domain
        assert schema["definitions"]["review_assessment"]["properties"]["relationship_domain"]["const"] == domain
        assert "supporting_quote" not in schema["definitions"]["review_assessment"]["required"]
        assert "supporting_quote" not in schema["definitions"]["review_assessment"]["properties"]
        assert coverage_item["properties"]["relationship_domain"]["const"] == domain
        assert "supporting_quote" not in coverage_item["required"]
        assert "supporting_quote" not in coverage_item["properties"]
        assert "coverage_focus" in coverage_item["required"]
        assert coverage_item["properties"]["coverage_focus"]["enum"] == [
            "main_focus",
            "substantial_topic",
            "brief_context",
            "unclear",
        ]
        assert "domain_result" in coverage_item["required"]
        assert "text_depth" in schema["required"]
        assert "source_text_provenance" in schema["required"]
        assert missing_descriptions == []
