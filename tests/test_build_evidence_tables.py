import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from pipeline.extract.io_utils import write_json
from pipeline.kg.convert_routed_extractions_to_evidence_rows import graph_subject_kind
from pipeline.kg.build_evidence_tables import (
    DEFAULT_REGISTRY_PATH,
    DEFAULT_ROUTED_KG_RUN_ROOT,
    MOLECULAR_SUBTOPIC_RULES_BY_PARENT,
    build_tables,
    canonicalize_registry_label,
    clinical_endpoint_rows,
    condition_expanded_rows,
    graph_admission_decision,
    graphable_compound_match,
    looks_like_compound_list,
    graph_sources_for_preset,
    graphable_subject_match,
    graphable_entity_match,
    graph_use_context_projections,
    match_vocabulary_entity,
    molecular_effect_label,
    molecular_finding_subtopic,
    molecular_parent_from_specific,
    molecular_subtopic_coverage_summary,
    node_vocabulary_lookup,
    nontherapeutic_clinical_context_reason,
    nontherapeutic_observational_exposure_association,
    nontherapeutic_substance_use_condition_reason,
    normalize_claim_metadata,
    overview_graph_subject,
    overview_graph_subjects,
    review_design_category,
    registry_lookup,
    resolve_kg_output_dir,
    safety_endpoint_label,
    symptom_endpoint_label,
    write_duckdb_database,
)


class BuildEvidenceTablesTest(unittest.TestCase):
    def test_nontherapeutic_observational_exposure_associations_stay_out_of_outcome_views(self) -> None:
        schizophrenia_history = {
            "domain": "clinical_outcome",
            "kg_entity_kind_override": "condition_indication",
            "evidence_design": "observational",
            "study_design": "Cross-sectional observational study",
            "dose": "Lifetime history of hallucinogen abuse",
            "compound_or_intervention": "Hallucinogens (LSD, MDA, mescaline, psilocybin)",
            "comparator": "Non-abusers within the same clinical population",
            "comparator_normalized": "Other",
            "session_context": "naturalistic_use",
            "support": (
                "There was a trend for patients who had abused hallucinogens to have lower "
                "Anxiety-Depression scores on the BPRS."
            ),
        }
        population_association = {
            "domain": "clinical_outcome",
            "kg_entity_kind_override": "condition_indication",
            "evidence_design": "observational",
            "study_design": "Cross-sectional comparative online survey",
            "dose": "At least one lifetime psychedelic experience",
            "comparator": "Sex and age-matched non-user control group",
            "support": (
                "Psychedelic users scored notably higher on the DUDIT compared to non-users."
            ),
        }
        hppd_comparison = {
            "domain": "clinical_outcome",
            "kg_entity_kind_override": "condition_indication",
            "evidence_design": "observational",
            "study_design": "Comparative cross-sectional clinical investigation",
            "dose": "Prior LSD use",
            "comparator": "Patients with prior LSD use without HPPD",
            "support": (
                "Patients who developed HPPD after LSD use had less severe psychopathology "
                "compared to those without HPPD."
            ),
        }
        retrospective_outcome = {
            "domain": "clinical_outcome",
            "kg_entity_kind_override": "condition_indication",
            "evidence_design": "observational",
            "study_design": "Retrospective online survey",
            "dose": "Naturalistic use; single significant experience",
            "comparator": "Baseline (pre-experience)",
            "comparator_normalized": "Baseline",
            "support": (
                "The proportion meeting criteria for severe AUD significantly decreased one month "
                "after the psychedelic experience."
            ),
        }
        prospective_microdosing = {
            "domain": "clinical_outcome",
            "kg_entity_kind_override": "condition_indication",
            "evidence_design": "observational",
            "study_design": "Naturalistic prospective comparison study",
            "dose": "Self-initiated microdosing for 4 weeks",
            "comparator": "Conventional ADHD medication",
            "comparator_normalized": "Standard care",
            "support": "Symptoms improved over four weeks of microdosing.",
        }
        self_reported_improvement = {
            "domain": "clinical_outcome",
            "kg_entity_kind_override": "symptom_problem",
            "evidence_design": "observational",
            "study_design": "Anonymous online survey",
            "dose": "Sub-hallucinogenic doses for at least 2 weeks",
            "support": "A majority of microdosers reported subjective improvement in depressive symptoms.",
        }
        model_psychosis = {
            "domain": "clinical_outcome",
            "kg_entity_kind_override": "condition_indication",
            "graph_entity_label": "Schizophrenia",
            "source_type": "review",
            "support": (
                "Serotonergic hallucinogens produce a model psychosis that resembles the "
                "positive symptoms of schizophrenia."
            ),
        }
        therapeutic_schizophrenia = {
            "domain": "clinical_outcome",
            "kg_entity_kind_override": "condition_indication",
            "graph_entity_label": "Schizophrenia",
            "source_type": "review",
            "support": "Low-dose LSD may improve negative symptoms of schizophrenia.",
        }
        research_history = {
            "domain": "clinical_outcome",
            "kg_entity_kind_override": "condition_indication",
            "graph_entity_label": "Alcohol use disorder",
            "source_type": "review",
            "support": "LSD was investigated as a potential treatment aid for alcoholism.",
        }
        hppd_condition = {
            "domain": "clinical_outcome",
            "kg_entity_kind_override": "condition_indication",
            "graph_entity_label": "Hallucinogen persisting perception disorder",
            "source_type": "review",
            "support": "LSD is the most common substance associated with HPPD.",
        }
        meta_analysis_use_association = {
            "domain": "clinical_outcome",
            "kg_entity_kind_override": "condition_indication",
            "graph_entity_label": "Schizophrenia",
            "evidence_design": "evidence_synthesis",
            "study_design": "Pairwise meta-analysis",
            "comparator": "Non-users",
            "support": "LSD use was associated with a history of suicide attempts.",
        }

        self.assertTrue(nontherapeutic_observational_exposure_association(schizophrenia_history))
        self.assertTrue(nontherapeutic_observational_exposure_association(population_association))
        self.assertTrue(nontherapeutic_observational_exposure_association(hppd_comparison))
        self.assertFalse(nontherapeutic_observational_exposure_association(retrospective_outcome))
        self.assertFalse(nontherapeutic_observational_exposure_association(prospective_microdosing))
        self.assertFalse(nontherapeutic_observational_exposure_association(self_reported_improvement))
        self.assertEqual(
            nontherapeutic_clinical_context_reason(model_psychosis),
            "nontherapeutic_disease_model_context",
        )
        self.assertEqual(nontherapeutic_clinical_context_reason(therapeutic_schizophrenia), "")
        self.assertEqual(
            nontherapeutic_clinical_context_reason(research_history),
            "research_history_without_therapeutic_outcome",
        )
        self.assertEqual(
            nontherapeutic_clinical_context_reason(hppd_condition),
            "safety_or_adverse_condition_context",
        )
        self.assertTrue(nontherapeutic_observational_exposure_association(meta_analysis_use_association))
        self.assertEqual(
            graph_admission_decision(schizophrenia_history),
            ("paper_detail", "nontherapeutic_observational_exposure_association"),
        )
        self.assertEqual(
            graph_admission_decision(retrospective_outcome),
            ("main_graph", "semantically_complete"),
        )

    def test_substance_use_conditions_require_a_therapeutic_relationship(self) -> None:
        same_compound_dependence = {
            "domain": "clinical_outcome",
            "kg_entity_kind_override": "condition_indication",
            "graph_overview_subject_label": "Ketamine",
            "graph_entity_label": "Ketamine use disorder",
            "evidence_design": "observational",
            "study_design": "Cross-sectional assessment during inpatient withdrawal treatment",
            "population": "Patients undergoing inpatient ketamine withdrawal treatment",
            "support": "High prevalence of depression was observed in ketamine-dependent patients.",
        }
        abuse_liability = {
            "domain": "clinical_outcome",
            "kg_entity_kind_override": "condition_indication",
            "graph_overview_subject_label": "MDMA",
            "graph_entity_label": "Substance use disorder",
            "source_type": "review",
            "support": "Repeated MDMA exposure may explain the development of substance use disorders.",
        }
        condition_as_population = {
            "domain": "clinical_outcome",
            "kg_entity_kind_override": "condition_indication",
            "graph_overview_subject_label": "Ketamine",
            "graph_entity_label": "Alcohol use disorder",
            "evidence_design": "randomized_controlled_trial",
            "population": "Ethanol-dependent inpatients",
            "support": "Nimodipine attenuated ketamine-induced euphoria and sedation.",
        }
        nonclinical_model_context = {
            "domain": "cognitive_behavioral",
            "kg_entity_kind_override": "condition_indication",
            "graph_overview_subject_label": "MDMA",
            "graph_entity_label": "Nicotine dependence",
            "evidence_design": "preclinical",
            "study_design": "Conditioned place preference following nicotine pre-exposure",
            "support": "MDMA induced conditioned place preference only in zebrafish pre-exposed to nicotine.",
        }
        unrelated_exposure_association = {
            "domain": "clinical_outcome",
            "kg_entity_kind_override": "condition_indication",
            "graph_overview_subject_label": "Hallucinogens",
            "graph_entity_label": "Opioid use disorder",
            "evidence_design": "case_report",
            "population": "Person with a history of early-life psychedelic use",
            "support": "Past early-life psychedelic use was associated with a less severe opioid use disorder later in life.",
        }
        index_drug_exposure_association = {
            "domain": "clinical_outcome",
            "kg_entity_kind_override": "condition_indication",
            "graph_overview_subject_label": "Ketamine",
            "graph_entity_label": "Substance use disorder",
            "evidence_design": "observational",
            "dose": "Naturalistic use prior to a family-oriented treatment program",
            "support": "Youths using ketamine had a lower relapse rate than youths using stimulants.",
        }
        therapeutic_outcome = {
            "domain": "clinical_outcome",
            "kg_entity_kind_override": "condition_indication",
            "graph_overview_subject_label": "Ketamine",
            "graph_entity_label": "Alcohol use disorder",
            "evidence_design": "randomized_controlled_trial",
            "population": "Adults receiving treatment for alcohol use disorder",
            "support": "Ketamine treatment significantly reduced drinking days and increased abstinence.",
        }

        self.assertEqual(
            nontherapeutic_substance_use_condition_reason(same_compound_dependence),
            "same_compound_use_disorder_context",
        )
        self.assertEqual(
            nontherapeutic_substance_use_condition_reason(abuse_liability),
            "substance_use_liability_not_therapeutic_outcome",
        )
        self.assertEqual(
            nontherapeutic_substance_use_condition_reason(condition_as_population),
            "substance_use_condition_as_population_or_model_context",
        )
        self.assertEqual(
            nontherapeutic_substance_use_condition_reason(nonclinical_model_context),
            "substance_use_condition_as_population_or_model_context",
        )
        self.assertEqual(
            nontherapeutic_substance_use_condition_reason(unrelated_exposure_association),
            "nontherapeutic_substance_use_exposure_association",
        )
        self.assertEqual(
            nontherapeutic_substance_use_condition_reason(index_drug_exposure_association),
            "nontherapeutic_substance_use_exposure_association",
        )
        self.assertEqual(nontherapeutic_substance_use_condition_reason(therapeutic_outcome), "")
        self.assertEqual(
            graph_admission_decision(same_compound_dependence),
            ("paper_detail", "same_compound_use_disorder_context"),
        )

    def test_brain_readout_is_preserved_as_detail_only_measure_instead_of_rejected(self) -> None:
        match = graphable_entity_match(
            row={"graph_entity_label": "theta power (4-8 Hz)"},
            domain="brain_system",
            entity_kind="biomarker_readout",
            raw_label="theta power (4-8 Hz)",
            registry={},
            node_vocabulary={},
        )

        self.assertTrue(match["matched"])
        self.assertEqual(match["kind"], "brain_measure")
        self.assertEqual(match["label"], "Oscillatory power")

    def test_brain_measure_routing_accepts_compatible_kinds_without_broadening_unrelated_entities(self) -> None:
        cases = (
            ("molecular_pathway_readout", "pathway_process", "Grey matter volume", "Brain structure"),
            ("brain_system", "brain_network", "brain entropy", "Neural signal complexity"),
            ("brain_system", "neural_circuit", "V1-V3 retinotopic coupling", "Functional connectivity"),
            ("brain_system", "biomarker_readout", "Phase lag entropy (PLE)", "Neural signal complexity"),
        )
        for domain, kind, raw, expected in cases:
            with self.subTest(raw=raw):
                match = graphable_entity_match(
                    row={"graph_entity_label": raw},
                    domain=domain,
                    entity_kind=kind,
                    raw_label=raw,
                    registry={},
                    node_vocabulary={},
                )
                self.assertTrue(match["matched"])
                self.assertEqual(match["kind"], "brain_measure")
                self.assertEqual(match["label"], expected)

        unrelated = graphable_entity_match(
            row={"graph_entity_label": "synaptic connectivity"},
            domain="molecular_pathway_readout",
            entity_kind="pathway_process",
            raw_label="synaptic connectivity",
            registry={},
            node_vocabulary={},
        )
        self.assertFalse(unrelated["matched"])

    def test_mde_names_resolve_to_mdea(self) -> None:
        registry = registry_lookup(DEFAULT_REGISTRY_PATH)
        for alias in (
            "MDE",
            "3,4-methylenedioxyethamphetamine",
            "3,4-methylenedioxyethylamphetamine",
            "N-ethyl-3,4-methylenedioxyamphetamine",
        ):
            with self.subTest(alias=alias):
                match = graphable_compound_match(alias, registry)
                self.assertTrue(match["matched"])
                self.assertEqual(match["label"], "MDEA")

        for raw, expected in (
            ("open-field locomotion scores", "Locomotor activity"),
            ("psychomotor stimulation", "Motor activity"),
        ):
            with self.subTest(raw=raw):
                row = normalize_claim_metadata(
                    {
                        "domain": "cognitive_behavioral",
                        "graph_entity_label": raw,
                        "construct_or_behavior": raw,
                        "task_or_measure": raw,
                        "kg_entity_kind_override": "cognitive_behavioral_construct",
                    },
                    "cognitive_behavioral",
                )
                self.assertEqual(row["graph_entity_label"], expected)
                self.assertEqual(row["endpoint_label_source"], "controlled_behavioral_detail")

    def test_narrow_review_construct_and_outcome_mappings(self) -> None:
        base = {
            "source_type": "review",
            "paper_type": "review",
            "review_extraction_method": "paper_centered_one_pass_v2",
            "evidence_level": "human",
        }
        cases = (
            ("Fear memory extinction", "clinical_outcome", "Fear extinction", "cognitive_behavioral_construct"),
            ("fear extinction circuitry", "brain_system", "Fear extinction", "cognitive_behavioral_construct"),
            ("creative ideation", "clinical_outcome", "Creativity", "cognitive_behavioral_construct"),
            ("Anxiolytic effect", "clinical_outcome", "Anxiety & panic", "symptom_problem"),
            ("Violent aggression", "clinical_outcome", "Aggression/violence", "symptom_problem"),
        )
        for raw, domain, expected_label, expected_kind in cases:
            with self.subTest(raw=raw):
                row = normalize_claim_metadata(
                    {
                        **base,
                        "domain": domain,
                        "graph_entity_label": raw,
                        "raw_entity_label": raw,
                        "kg_entity_kind_override": "condition_indication",
                    },
                    domain,
                )
                self.assertEqual(row["graph_entity_label"], expected_label)
                self.assertEqual(row["kg_entity_kind_override"], expected_kind)

        dying_care = graphable_entity_match(
            row={"context_component": "Dying Care"},
            domain="intervention_context",
            entity_kind="intervention_component",
            raw_label="Dying Care",
            registry={},
            node_vocabulary={},
        )
        self.assertTrue(dying_care["matched"])
        self.assertEqual(dying_care["item"]["parent"], "Palliative & end-of-life care")

        dying_anxiety = graphable_entity_match(
            row={},
            domain="clinical_outcome",
            entity_kind="condition_indication",
            raw_label="Anxiety associated with dying",
            registry=registry_lookup(DEFAULT_REGISTRY_PATH),
            node_vocabulary={},
        )
        self.assertTrue(dying_anxiety["matched"])
        self.assertEqual(dying_anxiety["label"], "Distress associated with life-threatening disease")

    def test_review_research_topic_uses_controlled_research_landscape_parent(self) -> None:
        match = graphable_entity_match(
            row={"graph_entity_label": "psychedelic research"},
            domain="general_topic_coverage",
            entity_kind="public_health_measure",
            raw_label="psychedelic research",
            registry={},
            node_vocabulary={},
        )

        self.assertTrue(match["matched"])
        self.assertEqual(match["label"], "Research landscape")

    def test_preclinical_review_antidepressant_effect_uses_behavioral_boundary(self) -> None:
        row = normalize_claim_metadata(
            {
                "review_extraction_method": "paper_centered_one_pass_v2",
                "evidence_level": "preclinical",
                "domain": "clinical_outcome",
                "graph_entity_label": "antidepressant effects",
                "kg_entity_kind_override": "symptom_problem",
            },
            "clinical_outcome",
        )

        self.assertEqual(row["domain"], "cognitive_behavioral")
        self.assertEqual(row["kg_entity_kind_override"], "cognitive_behavioral_construct")
        self.assertEqual(row["graph_entity_label"], "Stress-coping behavior")

    def test_real_world_use_context_projection_requires_finding_level_evidence(self) -> None:
        registry = {
            ("compound", "ketamine"): {"label": "Ketamine", "aliases": []},
            ("compound", "mdma"): {"label": "MDMA", "aliases": ["ecstasy"]},
            ("compound", "mephedrone"): {
                "label": "Mephedrone",
                "aliases": ["4-MMC"],
                "graph_scope": "out_of_scope_nonpsychedelic",
            },
        }
        chemsex_subjects = [
            {"label": "Chemsex", "kind": "exposure_context", "reason": "controlled_exposure_context"}
        ]
        projections = graph_use_context_projections(
            {
                "exposure_or_policy": "Chemsex (methamphetamine, mephedrone, GHB/GBL, ketamine, and MDMA)",
            },
            "real_world_public_health",
            chemsex_subjects,
            registry,
        )
        self.assertEqual(
            {item["subject_label"] for item in projections},
            {"Ketamine", "MDMA"},
        )
        self.assertTrue(all(item["context_label"] == "Chemsex" for item in projections))
        self.assertTrue(all(item["context_parent_label"] == "Sexualized drug use" for item in projections))
        self.assertTrue(all(item["relation_type"] == "reported_in_use_context" for item in projections))

        sexualized_use = graph_use_context_projections(
            {"support": "MDMA was among the drugs most commonly used in combination with sex."},
            "real_world_public_health",
            [{"label": "MDMA", "kind": "atomic_compound", "reason": "controlled_atomic_compound"}],
            registry,
        )
        self.assertEqual(len(sexualized_use), 1)
        self.assertEqual(sexualized_use[0]["subject_label"], "MDMA")
        self.assertEqual(sexualized_use[0]["context_label"], "Sexualized drug use")
        self.assertEqual(sexualized_use[0]["context_parent_label"], "")

        title_only = graph_use_context_projections(
            {"study_title": "Chemsex and mental health", "support": "MDMA use increased over time."},
            "real_world_public_health",
            [{"label": "MDMA", "kind": "atomic_compound", "reason": "controlled_atomic_compound"}],
            registry,
        )
        self.assertEqual(title_only, [])

        out_of_scope = graph_use_context_projections(
            {"exposure_or_policy": "Chemsex involving cocaine, methamphetamine, mephedrone, GHB, and GBL."},
            "real_world_public_health",
            chemsex_subjects,
            registry,
        )
        self.assertEqual(out_of_scope, [])

    def test_named_combinations_and_polydrug_are_typed_before_projection(self) -> None:
        for value in ("candyflip", "hippie flipping", "kitty-flip", "Nexus flip", "Jedi flipping", "soul bomb"):
            with self.subTest(value=value):
                self.assertEqual(graph_subject_kind(value), "compound_combination")
        self.assertEqual(graph_subject_kind("Polydrug use (5 or more drugs)"), "exposure_context")

    def test_specific_multi_compound_subjects_split_or_combine_from_saved_evidence(self) -> None:
        registry = {
            ("compound", "dmt"): {"label": "DMT"},
            ("compound", "n n dmt"): {"label": "DMT"},
            ("compound", "harmine"): {"label": "Harmine"},
            ("compound", "harmaline"): {"label": "Harmaline"},
            ("compound", "lsd"): {"label": "LSD"},
            ("compound", "psilocybin"): {"label": "Psilocybin"},
            ("compound", "mdma"): {"label": "MDMA"},
            ("compound", "ketamine"): {"label": "Ketamine"},
            ("compound", "2c b"): {"label": "2C-B"},
            ("compound", "mescaline"): {"label": "Mescaline"},
            ("compound", "ibogaine"): {"label": "Ibogaine"},
            ("compound", "5 meo dmt"): {"label": "5-MeO-DMT"},
        }

        separated = overview_graph_subjects(
            {"support": "Both substances were evaluated in separate study arms."},
            {"label": "LSD or psilocybin", "subject_kind": "compound_combination"},
            registry,
        )
        self.assertEqual([item["label"] for item in separated], ["LSD", "Psilocybin"])
        self.assertTrue(all(item["kind"] == "atomic_compound" for item in separated))

        secondary = overview_graph_subjects(
            {"paper_assessment_route": "secondary_literature"},
            {"label": "LSD or psilocybin", "subject_kind": "compound_combination"},
            registry,
        )
        self.assertEqual(secondary[0]["label"], "Multi-compound exposure")

        dmt_harmine = overview_graph_subjects(
            {"support": "The DMT/harmine formulation was administered during a retreat."},
            {"label": "N,N-DMT and harmine", "subject_kind": "compound_combination"},
            registry,
        )
        self.assertEqual(dmt_harmine[0]["label"], "DMT + Harmine (pharmahuasca)")
        self.assertEqual(dmt_harmine[0]["kind"], "compound_combination")

        coadministered = overview_graph_subjects(
            {"dose_or_exposure": "100 µg LSD + 100 mg MDMA", "support": "The drugs were co-administered."},
            {"label": "MDMA and LSD", "subject_kind": "compound_combination"},
            registry,
        )
        self.assertEqual(coadministered[0]["label"], "LSD + MDMA (candyflipping)")

        mixed_arms = overview_graph_subjects(
            {"dose_or_exposure": "100 µg LSD, 100 mg MDMA, or the combination"},
            {"label": "LSD, MDMA, or LSD + MDMA", "subject_kind": "compound_combination"},
            registry,
        )
        self.assertEqual(
            [item["label"] for item in mixed_arms],
            ["LSD", "MDMA", "LSD + MDMA (candyflipping)"],
        )

        nested_name = overview_graph_subjects(
            {"support": "5-MeO-DMT was co-administered with harmaline."},
            {"label": "5-MeO-DMT co-administered with harmaline", "subject_kind": "compound_combination"},
            registry,
        )
        self.assertEqual([item["label"] for item in nested_name], ["5-MeO-DMT + Harmaline"])

        named_alias = overview_graph_subjects(
            {"support": "Pharmahuasca was administered as one formulation."},
            {"label": "Pharmahuasca (DMT + Harmaline)", "subject_kind": "compound_combination"},
            registry,
        )
        self.assertEqual(named_alias[0]["label"], "DMT + Harmaline (pharmahuasca)")

        inferred_flipping_alias = overview_graph_subjects(
            {"support": "Psilocybin and MDMA were co-administered."},
            {"label": "Psilocybin + MDMA", "subject_kind": "compound_combination"},
            registry,
        )
        self.assertEqual(inferred_flipping_alias[0]["label"], "Psilocybin + MDMA (hippy flipping)")

        named_cases = [
            ("A kittyflip was reported.", "kitty flipping", "Ketamine + MDMA (kitty flipping)"),
            ("Participants described nexus flipping.", "Nexus flip", "2C-B + MDMA (nexus flipping)"),
            ("The session was described as a twilight flip.", "Jedi flipping", "LSD + Psilocybin + MDMA (Jedi flipping)"),
            ("The source called this soul bombing.", "Soul bomb", "LSD + Psilocybin (soul bombing)"),
            ("The sequence was called an Ali flip.", "Ali flipping", "LSD + MDMA + 2C-B (Ali flipping)"),
            ("The report used the term love trip.", "Love flip", "Mescaline + MDMA (love flipping)"),
            ("The source explicitly described Selma flipping.", "Selma flip", "Mescaline + MDMA + 2C-B (Selma flipping)"),
        ]
        for support, raw_label, expected in named_cases:
            with self.subTest(raw_label=raw_label):
                result = overview_graph_subjects(
                    {"support": support},
                    {"label": raw_label, "subject_kind": "compound_combination"},
                    registry,
                )
                self.assertEqual(result[0]["label"], expected)
                self.assertTrue(result[0]["aliases"])

        inferred_kitty = overview_graph_subjects(
            {"support": "Ketamine and MDMA were co-administered."},
            {"label": "MDMA + ketamine", "subject_kind": "compound_combination"},
            registry,
        )
        self.assertEqual(inferred_kitty[0]["label"], "Ketamine + MDMA (kitty flipping)")
        self.assertIn("kittyflip", inferred_kitty[0]["aliases"])

        explicit_only_alias_not_inferred = overview_graph_subjects(
            {"support": "LSD and psilocybin were co-administered."},
            {"label": "LSD + psilocybin", "subject_kind": "compound_combination"},
            registry,
        )
        self.assertEqual(explicit_only_alias_not_inferred[0]["label"], "LSD + Psilocybin")

        unrelated_finding_in_named_paper = overview_graph_subjects(
            {
                "study_title": "Candyflipping and Other Combinations",
                "finding_summary": "Cathinone co-mentions formed a separate cluster.",
            },
            {
                "label": "Novel Psychoactive Substances and Cathinones",
                "subject_kind": "compound_combination",
            },
            registry,
        )
        self.assertEqual(unrelated_finding_in_named_paper, [])

        sequential = overview_graph_subjects(
            {"support": "The substances were administered consecutively.", "study_title": "Consecutive treatment"},
            {"label": "Ibogaine and 5-MeO-DMT", "subject_kind": "treatment_regimen"},
            registry,
        )
        self.assertEqual(sequential[0]["label"], "Ibogaine + 5-MeO-DMT (sequential)")

        context = overview_graph_subjects(
            {"atomic_compound_candidate": "Ketamine (as part of chemsex substances)"},
            {
                "label": "Use of methamphetamine, MDMA, and ketamine in a sexual setting",
                "subject_kind": "exposure_context",
            },
            registry,
        )
        self.assertEqual(context, [{"label": "Chemsex", "kind": "exposure_context", "reason": "controlled_exposure_context"}])

        polydrug_context = overview_graph_subjects(
            {"atomic_compound_candidate": "Polydrug use (5 or more drugs)"},
            {"label": "Polydrug use (5 or more drugs)", "subject_kind": "exposure_context"},
            registry,
        )
        self.assertEqual(
            polydrug_context,
            [{"label": "Polysubstance use", "kind": "exposure_context", "reason": "controlled_exposure_context"}],
        )

    def test_generic_psychedelic_overview_subjects_are_context_specific(self) -> None:
        registry = {
            ("compound", "psilocybin"): {"label": "Psilocybin"},
            ("compound", "lsd"): {"label": "LSD"},
            ("compound", "dmt"): {"label": "DMT"},
            ("compound", "mdma"): {"label": "MDMA"},
            ("compound", "ketamine"): {"label": "Ketamine"},
        }
        generic_match = {
            "label": "Psychedelics",
            "subject_kind": "compound_class",
        }
        cases = [
            (
                {"graph_entity_label": "5-HT2A", "support": "5-HT2A receptor-mediated signalling"},
                "Classic psychedelics",
            ),
            (
                {"study_title": "Recreational use of psychedelics and brain serotonin markers"},
                "Psychedelics (unspecified compounds)",
            ),
            (
                {"compound_or_exposure": "Lifetime naturalistic psychedelic use"},
                "Psychedelics (unspecified compounds)",
            ),
            (
                {"primary_compounds_or_classes": "psilocybin, LSD, DMT, MDMA"},
                "Psychedelics (unspecified compounds)",
            ),
            (
                {"compound_or_intervention": "psychedelic-assisted psychotherapy"},
                "Psychedelic-assisted therapy (unspecified compounds)",
            ),
            (
                {"support": "Psychedelic compounds were examined."},
                "Psychedelics (unspecified compounds)",
            ),
            (
                {"support": "Studies reported mixed results for antidepressant effects."},
                "Psychedelics (unspecified compounds)",
            ),
        ]
        for row, expected in cases:
            with self.subTest(expected=expected):
                result = overview_graph_subject(row, generic_match, registry)
                self.assertEqual(result["label"], expected)
                self.assertNotEqual(result["label"], "Psychedelics")

        specified_therapy = overview_graph_subject(
            {"compound_or_intervention": "psilocybin-assisted psychotherapy"},
            {"label": "Psilocybin", "subject_kind": "atomic_compound"},
            registry,
        )
        self.assertEqual(specified_therapy["label"], "Psilocybin")

        classic = overview_graph_subject(
            {},
            {"label": "Classic psychedelics", "subject_kind": "compound_class"},
            registry,
        )
        self.assertEqual(classic["label"], "Classic psychedelics")

        primarily_psilocybin = overview_graph_subject(
            {},
            {"label": "Naturalistic psychedelic use (various, primarily psilocybin)", "subject_kind": "compound_class"},
            registry,
        )
        self.assertEqual(primarily_psilocybin["label"], "Psilocybin")

        primarily_two_compounds = overview_graph_subjects(
            {},
            {"label": "Classic psychedelics (primarily LSD and psilocybin)", "subject_kind": "compound_class"},
            registry,
        )
        self.assertEqual([item["label"] for item in primarily_two_compounds], ["Classic psychedelics"])

        pooled_class_with_examples = overview_graph_subjects(
            {},
            {
                "label": "Classical psychedelics (LSD, psilocybin, ayahuasca, DMT, mescaline)",
                "subject_kind": "compound_class",
            },
            registry,
        )
        self.assertEqual([item["label"] for item in pooled_class_with_examples], ["Classic psychedelics"])

        naturalistic_class = overview_graph_subject(
            {"compound_or_intervention": "Classical psychedelics"},
            {"label": "At least one lifetime psychedelic experience", "subject_kind": "compound_class"},
            registry,
        )
        self.assertEqual(naturalistic_class["label"], "Classic psychedelics")

        unspecified_microdosing = overview_graph_subject(
            {"session_context": "naturalistic_use"},
            {"label": "Psychedelic microdosing", "subject_kind": "compound_class"},
            registry,
        )
        self.assertEqual(unspecified_microdosing["label"], "Psychedelics (unspecified compounds)")
        self.assertEqual(
            unspecified_microdosing["reason"],
            "controlled_unresolved_psychedelic_class_detail_only",
        )

        ketamine_therapy = overview_graph_subject(
            {},
            {"label": "Ketamine-assisted psychotherapy (KAPT), psychedelic approach", "subject_kind": "compound_class"},
            registry,
        )
        self.assertEqual(ketamine_therapy["label"], "Ketamine")

        partly_specified = overview_graph_subject(
            {},
            {"label": "Psychedelics and ketamine", "subject_kind": "compound_class"},
            registry,
        )
        self.assertEqual(partly_specified["label"], "Ketamine")
        self.assertEqual(partly_specified["reason"], "specific_compounds_recovered_from_class_text")

        named_mixed_exposure = overview_graph_subjects(
            {},
            {"label": "Psychedelics and MDMA", "subject_kind": "compound_class"},
            registry,
        )
        self.assertEqual([item["label"] for item in named_mixed_exposure], ["MDMA"])

        hallucinogen_class = overview_graph_subject(
            {},
            {"label": "Hallucinogen use (e.g., LSD)", "subject_kind": "compound_class"},
            registry,
        )
        self.assertEqual(hallucinogen_class["label"], "Hallucinogens")

        for raw_label in (
            "Psychedelics other than LSD",
            "Self-treating with non-ketamine psychedelics only",
            "Non-phenethylamine psychedelics (e.g., AL-LAD, 1P-LSD, LSZ)",
            "Psychedelics (LSD equivalents)",
        ):
            with self.subTest(raw_label=raw_label):
                unresolved = overview_graph_subject(
                    {},
                    {"label": raw_label, "subject_kind": "compound_class"},
                    registry,
                )
                self.assertEqual(unresolved["label"], "Psychedelics (unspecified compounds)")
                self.assertEqual(unresolved["reason"], "controlled_unresolved_psychedelic_class_detail_only")

        self_treatment = overview_graph_subject(
            {"support": "The group reported lower recreational ketamine use."},
            {"label": "Self-treating with non-ketamine psychedelics only", "subject_kind": "compound_class"},
            registry,
        )
        self.assertEqual(self_treatment["label"], "Psychedelics (unspecified compounds)")

    def test_compound_list_gate_distinguishes_lists_from_chemical_locants_and_metadata(self) -> None:
        self.assertTrue(looks_like_compound_list("Ketamine, esketamine, arketamine"))
        self.assertTrue(looks_like_compound_list("LSD, psilocybin, mescaline, or ayahuasca"))
        self.assertFalse(looks_like_compound_list("N,N-dimethyltryptamine (DMT)"))
        self.assertFalse(looks_like_compound_list("Ketamine, intravenous infusion"))

    def test_unresolved_psychedelic_class_is_searchable_detail_not_main_graph(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            registry_path = root / "registry.json"
            source_path = root / "routed.json"
            out_dir = root / "kg"
            write_json(
                registry_path,
                {
                    "compounds": [
                        {"label": "Psilocybin", "aliases": [], "ids": {}, "status": "seeded"},
                        {"label": "LSD", "aliases": [], "ids": {}, "status": "seeded"},
                    ],
                    "targets": [],
                    "disorders": [
                        {"label": "Major depressive disorder", "aliases": ["MDD"], "ids": {}, "status": "seeded"}
                    ],
                },
            )
            write_json(
                source_path,
                [
                    {
                        "study_doi": "10.1000/unspecified",
                        "domain": "clinical_outcome",
                        "compound": "Psychedelics (various)",
                        "graph_subject_kind": "compound_class",
                        "condition_or_indication": "MDD",
                        "paper_assessment_route": "primary_evidence",
                    },
                    {
                        "study_doi": "10.1000/classic",
                        "domain": "clinical_outcome",
                        "compound": "Classic psychedelics",
                        "graph_subject_kind": "compound_class",
                        "condition_or_indication": "MDD",
                        "paper_assessment_route": "primary_evidence",
                    },
                    {
                        "study_doi": "10.1000/naturalistic-unspecified",
                        "domain": "clinical_outcome",
                        "compound": "Naturalistic psychedelic use",
                        "graph_subject_kind": "compound_class",
                        "condition_or_indication": "MDD",
                        "session_context": "naturalistic_use",
                        "paper_assessment_route": "primary_evidence",
                    },
                    {
                        "study_doi": "10.1000/naturalistic-class",
                        "domain": "clinical_outcome",
                        "compound": "At least one lifetime psychedelic experience",
                        "graph_subject_kind": "compound_class",
                        "compound_or_intervention": "Classical psychedelics",
                        "condition_or_indication": "MDD",
                        "session_context": "naturalistic_use",
                        "paper_assessment_route": "primary_evidence",
                    },
                    {
                        "study_doi": "10.1000/pooled-class",
                        "domain": "clinical_outcome",
                        "compound": "Classical psychedelics (primarily psilocybin and LSD)",
                        "graph_subject_kind": "compound_class",
                        "condition_or_indication": "MDD",
                        "session_context": "naturalistic_use",
                        "paper_assessment_route": "primary_evidence",
                    },
                ],
            )
            build_tables(
                registry_path=registry_path,
                out_dir=out_dir,
                write_duckdb=False,
                graph_sources={
                    "routed_extractions": {
                        "path": source_path,
                        "domain": "routed",
                        "dataset": "routed",
                        "default_evidence_type": "primary_evidence",
                        "skip_audit": True,
                    }
                },
            )
            findings = pd.read_parquet(out_dir / "findings.parquet").set_index("study_doi")
            unresolved = findings.loc["10.1000/unspecified"]
            self.assertEqual(unresolved["graph_overview_subject_label"], "Psychedelics (unspecified compounds)")
            self.assertEqual(unresolved["graph_admission_status"], "paper_detail")
            self.assertEqual(unresolved["graph_admission_reason"], "unresolved_psychedelic_class_detail_only")
            classic = findings.loc["10.1000/classic"]
            self.assertEqual(classic["graph_overview_subject_label"], "Classic psychedelics")
            self.assertEqual(classic["graph_admission_status"], "main_graph")
            naturalistic_unspecified = findings.loc["10.1000/naturalistic-unspecified"]
            self.assertEqual(
                naturalistic_unspecified["graph_overview_subject_label"],
                "Psychedelics (unspecified compounds)",
            )
            self.assertEqual(naturalistic_unspecified["graph_admission_status"], "paper_detail")
            naturalistic_class = findings.loc["10.1000/naturalistic-class"]
            self.assertEqual(naturalistic_class["graph_overview_subject_label"], "Classic psychedelics")
            self.assertEqual(naturalistic_class["graph_admission_status"], "main_graph")
            pooled_class = findings.loc["10.1000/pooled-class"]
            self.assertEqual(pooled_class["graph_overview_subject_label"], "Classic psychedelics")
            self.assertEqual(pooled_class["graph_admission_status"], "main_graph")
            self.assertNotIn("Naturalistic psychedelic exposure", set(findings["compound"]))

    def test_routed_source_preset_uses_route_native_sources(self) -> None:
        self.assertEqual(set(graph_sources_for_preset("routed")), {"routed_extractions", "routed_clinical_endpoints"})

    def test_routed_run_id_resolves_to_versioned_kg_directory(self) -> None:
        out_dir, run_id = resolve_kg_output_dir(
            source_preset="routed",
            out_dir=None,
            run_id="Gemini 3 Flash / first batch",
        )

        self.assertEqual(run_id, "Gemini_3_Flash_first_batch")
        self.assertEqual(out_dir, DEFAULT_ROUTED_KG_RUN_ROOT / "Gemini_3_Flash_first_batch")
        self.assertTrue(
            str(graph_sources_for_preset("routed", run_id=run_id)["routed_extractions"]["path"]).endswith(
                "data/processed/extraction/routed_runs/Gemini_3_Flash_first_batch/routed_evidence_rows.json"
            )
        )
        self.assertTrue(
            str(graph_sources_for_preset("routed", run_id=run_id)["routed_clinical_endpoints"]["path"]).endswith(
                "data/processed/extraction/routed_runs/Gemini_3_Flash_first_batch/routed_evidence_rows.json"
            )
        )

    def test_routed_release_can_reuse_an_existing_evidence_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "evidence.json"
            source.write_text("[]", encoding="utf-8")
            out_dir = Path(tmpdir) / "new-release"
            sources = graph_sources_for_preset("routed", run_id="existing-evidence")
            for config in sources.values():
                config["path"] = source
            manifest = build_tables(
                graph_sources=sources,
                run_id="new-release",
                evidence_run_id="existing-evidence",
                out_dir=out_dir,
                write_duckdb=False,
            )

        self.assertEqual(manifest["run_id"], "new-release")
        self.assertEqual(manifest["evidence_run_id"], "existing-evidence")

    def test_compound_normalization_uses_shared_registry_without_stereoisomer_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            registry_path = root / "registry.json"
            write_json(
                registry_path,
                {
                    "compounds": [
                        {"label": "Ketamine", "aliases": ["racemic ketamine"], "ids": {}, "status": "seeded"},
                        {"label": "S-ketamine", "aliases": ["esketamine", "(S)-ketamine"], "ids": {}, "status": "seeded"},
                        {"label": "LSD", "aliases": ["lysergide", "MM120", "MM120 (lysergide D-tartrate)"], "ids": {}, "status": "seeded"},
                        {"label": "5-MeO-DMT", "aliases": ["5-methoxy-N,N-dimethyltryptamine"], "ids": {}, "status": "seeded"},
                        {
                            "label": "Psilocybin",
                            "aliases": ["Psilocybe cubensis mushrooms", "magic mushrooms"],
                            "ids": {},
                            "status": "seeded",
                        },
                        {"label": "Mescaline", "aliases": ["San Pedro", "Huachuma"], "ids": {}, "status": "seeded"},
                        {"label": "25B-NBOMe", "aliases": [], "ids": {}, "status": "seeded"},
                        {"label": "DMT", "aliases": ["N,N-dimethyltryptamine"], "ids": {}, "status": "seeded"},
                        {"label": "Harmine", "aliases": [], "ids": {}, "status": "seeded"},
                        {
                            "label": "Rapastinel",
                            "aliases": ["GLYX-13"],
                            "ids": {},
                            "status": "seeded",
                            "graph_scope": "out_of_scope_comparator",
                        },
                        {"label": "D-cycloserine", "aliases": [], "ids": {}, "status": "seeded"},
                    ],
                    "targets": [],
                    "disorders": [],
                },
            )
            registry = registry_lookup(registry_path, disorder_aliases_path=root / "missing_aliases.json")

        self.assertEqual(canonicalize_registry_label("compound", "ketamine", registry)[0], "Ketamine")
        self.assertEqual(graphable_compound_match("Ketamine-assisted psychotherapy (KAP)", registry)["label"], "Ketamine")
        self.assertEqual(graphable_compound_match("Intramuscular (IM) ketamine", registry)["label"], "Ketamine")
        self.assertEqual(
            graphable_compound_match("Esketamine nasal spray + oral antidepressant", registry)["label"],
            "S-ketamine",
        )
        self.assertEqual(graphable_compound_match("S-ketamine intranasally", registry)["label"], "S-ketamine")
        self.assertEqual(
            graphable_compound_match("BPL-003 (intranasal 5-methoxy-N,N-dimethyltryptamine)", registry)["label"],
            "5-MeO-DMT",
        )
        self.assertEqual(
            graphable_compound_match("psilocybin with psychological support", registry)["label"],
            "Psilocybin",
        )
        self.assertEqual(graphable_compound_match("MM120 (lysergide D-tartrate)", registry)["label"], "LSD")
        self.assertEqual(graphable_compound_match("Psilocybe cubensis mushrooms", registry)["label"], "Psilocybin")
        self.assertEqual(graphable_compound_match("San Pedro (Huachuma)", registry)["label"], "Mescaline")
        self.assertEqual(graphable_compound_match("25B-NBOMe", registry)["label"], "25B-NBOMe")
        self.assertEqual(graphable_compound_match("Serotonin (5-HT)", registry)["status"], "compound_reference_not_graphable")
        self.assertEqual(
            graphable_compound_match("Kambô (Phyllomedusa bicolor secretion)", registry)["status"],
            "compound_graph_scope_not_graphable",
        )
        combo = graphable_compound_match("DMT and harmine (DMT-harmine)", registry)
        self.assertFalse(combo["matched"])
        self.assertEqual(combo["status"], "compound_combo_not_graphable")
        scoped_out = graphable_compound_match("Rapastinel", registry)
        self.assertFalse(scoped_out["matched"])
        self.assertEqual(scoped_out["status"], "compound_graph_scope_not_graphable")
        fallback_scoped_out = graphable_compound_match("D-cycloserine", registry)
        self.assertFalse(fallback_scoped_out["matched"])
        self.assertEqual(fallback_scoped_out["status"], "compound_graph_scope_not_graphable")

    def test_nonpsychedelic_non_atomic_exposure_is_excluded_from_normalized_findings(self) -> None:
        registry = {
            ("compound", "lsd"): {"label": "LSD", "aliases": []},
            ("compound", "psilocybin"): {"label": "Psilocybin", "aliases": []},
        }

        stimulant_only = graphable_subject_match(
            {
                "compound": "Stimulants (Amphetamines, Cocaine)",
                "graph_subject_kind": "compound_combination",
            },
            registry,
        )
        self.assertFalse(stimulant_only["matched"])
        self.assertEqual(stimulant_only["status"], "compound_out_of_scope_nonpsychedelic")

        mixed_with_psychedelic = graphable_subject_match(
            {
                "compound": "LSD + cocaine",
                "graph_subject_kind": "compound_combination",
            },
            registry,
        )
        self.assertTrue(mixed_with_psychedelic["matched"])

        psychedelic_class_with_comedication = graphable_subject_match(
            {
                "compound": "Psychedelics + antipsychotics",
                "graph_subject_kind": "treatment_regimen",
            },
            registry,
        )
        self.assertTrue(psychedelic_class_with_comedication["matched"])

        unregistered_candidate_with_control = graphable_subject_match(
            {
                "compound": "Catharanthine sulfate + nicotine",
                "graph_subject_kind": "compound_combination",
            },
            registry,
        )
        self.assertTrue(unregistered_candidate_with_control["matched"])

        receptor_language_only = graphable_subject_match(
            {
                "compound": "atypical antipsychotics",
                "graph_subject_kind": "compound_class",
                "support": "5-HT2A inverse agonists altered cortical signaling.",
            },
            registry,
        )
        self.assertFalse(receptor_language_only["matched"])
        self.assertEqual(receptor_language_only["status"], "compound_out_of_scope_nonpsychedelic")

    def test_nonpsychedelic_exposure_is_audited_without_creating_a_finding_row(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            registry_path = root / "registry.json"
            source_path = root / "routed.json"
            out_dir = root / "kg"
            write_json(
                registry_path,
                {
                    "compounds": [
                        {"label": "LSD", "aliases": [], "ids": {}, "status": "seeded"},
                        {"label": "Ketamine", "aliases": [], "ids": {}, "status": "seeded"},
                        {
                            "label": "Dextromethorphan",
                            "aliases": ["DXM"],
                            "ids": {},
                            "status": "seeded",
                        },
                    ],
                    "targets": [],
                    "disorders": [
                        {"label": "Schizophrenia", "aliases": [], "ids": {}, "status": "seeded"}
                    ],
                },
            )
            write_json(
                source_path,
                [
                    {
                        "study_doi": "10.1093/schbul/16.1.31",
                        "domain": "clinical_outcome",
                        "compound": "LSD",
                        "graph_subject_kind": "atomic_compound",
                        "condition_or_indication": "Schizophrenia",
                    },
                    {
                        "study_doi": "10.1093/schbul/16.1.31",
                        "domain": "clinical_outcome",
                        "compound": "Stimulants (Amphetamines, Cocaine)",
                        "graph_subject_kind": "compound_combination",
                        "condition_or_indication": "Schizophrenia",
                    },
                    {
                        "study_doi": "10.1000/ketamine-morphine",
                        "domain": "clinical_outcome",
                        "compound": "morphine",
                        "atomic_compound_candidate": "morphine",
                        "graph_subject_label": "morphine",
                        "graph_subject_kind": "atomic_compound",
                        "graph_subject_source_field": "compound",
                        "condition_or_indication": "Schizophrenia",
                        "support": "Ketamine significantly decreased the clearance of morphine.",
                    },
                    {
                        "study_doi": "10.1000/generic-psychedelic-interaction",
                        "domain": "clinical_outcome",
                        "compound": "antidepressants",
                        "graph_subject_kind": "compound_class",
                        "condition_or_indication": "Schizophrenia",
                        "support": "Antidepressants may attenuate the acute subjective effects of psychedelics.",
                    },
                    {
                        "study_doi": "10.1000/title-only-mdma",
                        "study_title": "MDMA and benzodiazepine interactions",
                        "domain": "clinical_outcome",
                        "compound": "Benzodiazepines",
                        "graph_subject_kind": "compound_class",
                        "condition_or_indication": "Schizophrenia",
                        "support": "Benzodiazepines reduced anxiety.",
                    },
                    {
                        "study_doi": "10.1000/dxm-interaction",
                        "study_title": "Management of dextromethorphan-induced psychosis",
                        "domain": "clinical_outcome",
                        "compound": "atypical antipsychotics",
                        "graph_subject_kind": "compound_class",
                        "condition_or_indication": "Schizophrenia",
                        "support": "Atypical antipsychotics improved DXM-induced psychosis.",
                    },
                ],
            )

            build_tables(
                registry_path=registry_path,
                out_dir=out_dir,
                write_duckdb=False,
                graph_sources={
                    "routed_extractions": {
                        "path": source_path,
                        "domain": "routed",
                        "dataset": "routed",
                        "default_evidence_type": "primary_evidence",
                        "skip_audit": True,
                    }
                },
            )

            findings = pd.read_parquet(out_dir / "findings.parquet")
            audit = pd.read_parquet(out_dir / "normalization_audit.parquet")
            self.assertEqual(
                set(findings["compound"]),
                {
                    "LSD",
                    "Ketamine",
                    "Dextromethorphan",
                    "Psychedelics (unspecified compounds)",
                },
            )
            recovered = findings.set_index("study_doi")
            ketamine = recovered.loc["10.1000/ketamine-morphine"]
            self.assertEqual(ketamine["graph_subject_label"], "morphine")
            self.assertEqual(ketamine["graph_overview_subject_label"], "Ketamine")
            self.assertEqual(ketamine["graph_admission_status"], "paper_detail")
            self.assertEqual(
                ketamine["graph_admission_reason"],
                "in_scope_subject_recovered_from_finding_evidence_detail_only",
            )
            generic = recovered.loc["10.1000/generic-psychedelic-interaction"]
            self.assertEqual(generic["graph_subject_label"], "antidepressants")
            self.assertEqual(generic["graph_overview_subject_label"], "Psychedelics (unspecified compounds)")
            self.assertEqual(generic["graph_admission_status"], "paper_detail")
            dxm = recovered.loc["10.1000/dxm-interaction"]
            self.assertEqual(dxm["graph_subject_label"], "atypical antipsychotics")
            self.assertEqual(dxm["graph_overview_subject_label"], "Dextromethorphan")
            self.assertEqual(dxm["graph_admission_status"], "paper_detail")
            self.assertEqual(len(audit), 2)
            self.assertEqual(
                set(audit["compound_original"]),
                {"Stimulants (Amphetamines, Cocaine)", "Benzodiazepines"},
            )
            self.assertEqual(set(audit["normalization_status"]), {"compound_out_of_scope_nonpsychedelic"})

    def test_final_registry_and_vocabulary_aliases_cover_common_leftovers(self) -> None:
        root = Path(__file__).resolve().parents[1]
        registry = registry_lookup(root / "data" / "curated" / "entity_registry.json")
        vocabulary = node_vocabulary_lookup(root / "schema" / "kg_node_vocabularies.json")

        dxm = graphable_compound_match("DXM", registry)
        self.assertTrue(dxm["matched"])
        self.assertEqual(dxm["label"], "Dextromethorphan")

        botanical_cases = [
            ("Argyreia nervosa (Hawaiian baby wood rose seed)", "Hawaiian baby woodrose", "LSA"),
            ("Iboga", "Iboga", "Ibogaine"),
            ("Tabernanthe iboga root bark extract", "Iboga", "Ibogaine"),
            ("Incilius alvarius secretions", "Incilius alvarius secretion", "5-MeO-DMT"),
            ("Sonoran Desert toad", "Incilius alvarius secretion", "5-MeO-DMT"),
            ("Peyote", "Peyote", "Mescaline"),
            ("Lophophora williamsii", "Peyote", "Mescaline"),
            ("Salvia divinorum", "Salvia divinorum", "Salvinorin A"),
            ("Salvia divinorum extract", "Salvia divinorum", "Salvinorin A"),
        ]
        for raw_label, exact_label, overview_label in botanical_cases:
            with self.subTest(raw_label=raw_label):
                match = graphable_compound_match(raw_label, registry)
                self.assertTrue(match["matched"])
                self.assertEqual(match["label"], exact_label)
                projection = overview_graph_subjects({}, match, registry)
                self.assertEqual(projection[0]["label"], overview_label)
                self.assertEqual(projection[0]["reason"], "controlled_source_active_compound")
                self.assertIn(exact_label, projection[0]["aliases"])

        ayahuasca = graphable_compound_match("Ayahuasca", registry)
        ayahuasca_projection = overview_graph_subjects({}, ayahuasca, registry)
        self.assertEqual(ayahuasca_projection[0]["label"], "Ayahuasca")
        self.assertEqual(ayahuasca_projection[0]["kind"], "compound_combination")
        self.assertEqual(ayahuasca_projection[0]["reason"], "controlled_registered_exposure_kind")
        peyote_or_mescaline = overview_graph_subjects(
            {},
            {"label": "Peyote or mescaline", "subject_kind": "compound_combination"},
            registry,
        )
        self.assertEqual([subject["label"] for subject in peyote_or_mescaline], ["Mescaline"])
        self.assertIn("Peyote", peyote_or_mescaline[0]["aliases"])
        salvia_or_salvinorin = overview_graph_subjects(
            {},
            {"label": "Salvia divinorum extract or Salvinorin A", "subject_kind": "compound_combination"},
            registry,
        )
        self.assertEqual([subject["label"] for subject in salvia_or_salvinorin], ["Salvinorin A"])
        negated_compounds = overview_graph_subjects(
            {},
            {
                "label": "Non-psilocybin/LSD psychedelics (e.g., DMT, mescaline, peyote, San Pedro)",
                "subject_kind": "compound_class",
            },
            registry,
        )
        self.assertEqual([subject["label"] for subject in negated_compounds], ["DMT", "Mescaline"])
        self.assertEqual(
            canonicalize_registry_label("compound", "O-desmethylibogaine", registry)[0],
            "Noribogaine",
        )
        self.assertEqual(canonicalize_registry_label("compound", "shrooms", registry)[0], "Psilocybin")

        target_cases = [
            ("h5-HT2A", "5-HT2A"),
            ("Sodium-dependent serotonin transporter (5HTT)", "SERT (SLC6A4)"),
            ("human serotonin transporter", "SERT (SLC6A4)"),
            ("platelet plasma membrane serotonin transporter", "SERT (SLC6A4)"),
            ("Sodium-dependent noradrenaline transporter", "NET (SLC6A2)"),
            ("D2 dopamine receptor", "Dopamine D2 receptor (DRD2)"),
            ("D2Short receptor", "Dopamine D2 receptor (DRD2)"),
            ("D1-like dopamine receptors", "Dopamine receptor family"),
            ("D2/3 receptors", "Dopamine receptor family"),
            ("DAR2", "Dopamine receptor family"),
            ("5-HT1C serotonin receptor", "5-HT2C"),
            ("h5-HT7 receptor", "5-HT7"),
            ("S2 serotonin receptor", "5-HT2 receptor family"),
            ("S-2 binding site", "5-HT2 receptor family"),
            ("hKOPR", "kappa opioid receptor (OPRK1)"),
            ("kappa-opiate receptor", "kappa opioid receptor (OPRK1)"),
            ("mGlu2", "mGluR2 (GRM2)"),
            ("Indolethylamine-N-methyltransferase", "INMT"),
            ("phencyclidine (PCP) binding sites", "NMDA receptor"),
            ("NMDA glutamate receptors", "NMDA receptor"),
            ("GluN2A N615K NMDA receptor", "GluN2A (GRIN2A)"),
            ("hα3β4 nicotinic acetylcholine receptor", "Nicotinic acetylcholine receptor family"),
            ("P-glycoprotein", "P-glycoprotein (ABCB1)"),
            ("hOCT1", "OCT1 (SLC22A1)"),
            ("hOCT2", "OCT2 (SLC22A2)"),
            ("hPMAT", "PMAT (SLC29A4)"),
            ("voltage-dependent sodium channel", "Voltage-gated sodium channel family"),
        ]
        for raw_label, expected in target_cases:
            with self.subTest(raw_label=raw_label):
                self.assertEqual(canonicalize_registry_label("mechanistic_entity", raw_label, registry)[0], expected)

        self.assertEqual(
            canonicalize_registry_label("clinical_entity", "autism", registry)[0],
            "Autism spectrum disorder",
        )

        brain_cases = [
            ("ventral medial prefrontal cortex (vmPFC)", "Ventromedial prefrontal cortex"),
            ("primary visual area (V1)", "Primary visual cortex"),
            ("ventral tegmental area (VTA)", "Ventral tegmental area"),
            ("caudate nucleus", "Caudate nucleus"),
            ("primary somatosensory cortex (S1)", "Primary somatosensory cortex"),
            ("lateral habenula (LHb)", "Lateral habenula"),
            ("periaqueductal grey (PAG)", "Periaqueductal gray"),
            ("piriform cortex (PirC)", "Piriform cortex"),
            ("locus coeruleus", "Locus coeruleus"),
            ("left precuneus", "Precuneus"),
            ("posterior parahippocampal cortex", "Posterior parahippocampal cortex"),
            ("auditory cortex", "Auditory cortex"),
        ]
        for raw_label, expected in brain_cases:
            with self.subTest(raw_label=raw_label):
                self.assertEqual(match_vocabulary_entity(raw_label, "brain_region", vocabulary)["label"], expected)
        self.assertEqual(
            match_vocabulary_entity("thalamocortical", "neural_circuit", vocabulary)["label"],
            "Thalamocortical circuit",
        )
        intervention_cases = [
            ("Inner Healing Intelligence model", "Non-directive support"),
            ("Therapeutic Witnessing", "Non-directive support"),
            ("Therapist attitude (Witnessing)", "Non-directive support"),
            ("non-directive, supportive therapeutic approach", "Non-directive support"),
        ]
        for raw_label, expected in intervention_cases:
            with self.subTest(raw_label=raw_label):
                self.assertEqual(match_vocabulary_entity(raw_label, "intervention_component", vocabulary)["label"], expected)

        for raw_label in ("MDPV", "Mephedrone"):
            with self.subTest(raw_label=raw_label):
                match = graphable_compound_match(raw_label, registry)
                self.assertFalse(match["matched"])
                self.assertEqual(match["status"], "compound_graph_scope_not_graphable")

    def test_safety_endpoint_label_uses_specific_route_native_fields(self) -> None:
        cases = [
            ({"safety_event_or_measure": "QTc prolongation"}, "Cardiovascular safety"),
            ({"finding_summary": "No serious adverse events occurred during treatment."}, "Serious adverse events"),
            (
                {
                    "safety_event_or_measure": "psychotomimetic symptoms",
                    "outcome_measure": "BPRS positive subscale",
                },
                "Psychosis risk",
            ),
            (
                {
                    "safety_event_or_measure": "Dissociative effects",
                    "support": "The treatment may cause reduced dissociative or psychotomimetic side effects.",
                },
                "Dissociation",
            ),
            ({"safety_event_or_measure": "headache after dosing"}, "Headache"),
            ({"safety_event_or_measure": "sleep disturbance after dosing"}, "Sleep disturbance"),
            ({"safety_event_or_measure": "no suicidal ideation occurred"}, "Suicidality risk"),
            (
                {"safety_event_or_measure": "ketamine-induced cystitis and urinary pain"},
                "Urinary toxicity",
            ),
            (
                {"support": "Ketamine significantly impaired motor coordination on the rotarod task."},
                "Sedation/cognitive or motor impairment",
            ),
            (
                {"safety_category": "cerebellar Purkinje cell degeneration and dopaminergic injury"},
                "Neurotoxicity/cytotoxicity",
            ),
            ({"safety_event_or_measure": "well tolerated with mild adverse events"}, "Overall tolerability"),
            ({"safety_event_or_measure": "mild adverse events"}, "Adverse events"),
            ({"support": "A case of intoxication required poison control consultation."}, "Acute intoxication/poisoning"),
            ({"outcome_measure": "Clinician-Administered Dissociative States Scale (CADSS)"}, "Dissociation"),
            ({"outcome_measure": "Young Mania Rating Scale (YMRS)"}, "Mania/hypomania risk"),
            ({"support": "MDMA produced significant hyperthermia and elevated core temperature."}, "Body temperature effects"),
            ({"support": "No adverse drug-drug interactions were observed."}, "Drug interaction risk"),
            ({"support": "The compound is predicted to cross the placenta, indicating fetal exposure."}, "Pregnancy/fetal exposure"),
            ({"support": "Driving under the influence increased accident risk."}, "Driving/accident risk"),
            ({"support": "Plasma cortisol and prolactin increased after dosing."}, "Endocrine effects"),
            ({"graph_entity_label": "Neuropsychiatric sequelae"}, "Neuropsychiatric sequelae"),
        ]

        for row, expected in cases:
            with self.subTest(row=row):
                self.assertEqual(safety_endpoint_label(row), expected)

        self.assertEqual(
            safety_endpoint_label({"support": "Ketamine increased REM and slow-wave sleep after treatment."}),
            "",
        )

    def test_symptom_endpoint_label_uses_clinical_endpoint_and_measure_fields(self) -> None:
        cases = [
            (
                {
                    "clinical_endpoint": "depressive symptom severity",
                    "outcome_measure": "Montgomery-Asberg Depression Rating Scale (MADRS)",
                },
                "Low mood & depressive symptoms",
            ),
            (
                {
                    "clinical_endpoint": "suicidal ideation",
                    "outcome_measure": "Columbia Suicide Severity Rating Scale (C-SSRS)",
                },
                "Suicidality",
            ),
            (
                {
                    "clinical_endpoint": "Anxiety symptoms",
                    "outcome_measure": "Hospital Anxiety and Depression Scale-Anxiety (HADS-A)",
                },
                "Anxiety & panic",
            ),
            (
                {
                    "clinical_endpoint": "PTSD symptom severity",
                    "outcome_measure": "PCL-5",
                },
                "",
            ),
            (
                {
                    "clinical_endpoint": "PTSD symptoms (nightmares, intrusive memories, avoidance)",
                    "outcome_measure": "clinical interview",
                },
                "Trauma re-experiencing & avoidance",
            ),
            (
                {
                    "clinical_endpoint": "Well-being",
                    "outcome_measure": "Warwick-Edinburgh Mental Well-Being Scale",
                },
                "",
            ),
        ]

        for row, expected in cases:
            with self.subTest(row=row):
                self.assertEqual(symptom_endpoint_label(row), expected)

    def test_clinical_worsened_suicidality_derives_safety_endpoint(self) -> None:
        rows = [
            {
                "domain": "clinical_outcome",
                "compound": "LSD",
                "clinical_endpoint": "Suicidal thinking",
                "condition_or_indication": "Suicidality",
                "outcome_measure": "Self-reported suicidal thinking",
                "support": "Past-year LSD use was associated with an increased likelihood of suicidal thinking.",
                "effect_or_statistic": "aPR = 1.21 (95% CI: 1.09-1.34)",
                "result_direction": "negative",
            },
            {
                "domain": "clinical_outcome",
                "compound": "MDMA",
                "clinical_endpoint": "Suicidal thinking",
                "condition_or_indication": "Suicidality",
                "outcome_measure": "Self-reported suicidal thinking",
                "support": "Past-year ecstasy use was associated with a decreased likelihood of suicidal thinking.",
                "effect_or_statistic": "aPR = 0.86 (95% CI: 0.75-0.99)",
                "result_direction": "positive",
            },
        ]

        derived = clinical_endpoint_rows(rows, [{}, {}])
        safety_rows = [row for row in derived if row.get("kg_entity_kind_override") == "safety_adverse_event"]

        self.assertEqual(len(safety_rows), 1)
        self.assertEqual(safety_rows[0]["compound"], "LSD")
        self.assertEqual(safety_rows[0]["graph_entity_label"], "Suicidality risk")
        self.assertEqual(safety_rows[0]["endpoint_label_source"], "clinical_worsened_safety_endpoint")
        self.assertNotIn("MDMA", {row["compound"] for row in safety_rows})

    def test_route_native_mechanistic_metadata_infers_experimental_system(self) -> None:
        cases = [
            ({"model_or_system": "In vivo", "species": "Rats"}, "in_vivo"),
            ({"model_or_system": "HEK-293 cells expressing recombinant human receptors"}, "in_vitro"),
            ({"model_or_system": "hippocampal slices", "species": "rats"}, "ex_vivo"),
            ({"model_or_system": "clinical trial", "species": "human"}, "clinical"),
        ]

        for row, expected in cases:
            with self.subTest(row=row):
                normalized = normalize_claim_metadata(dict(row), "molecular_pathway_readout")
                self.assertEqual(normalized["system"], expected)

    def test_molecular_effect_labels_use_specific_scientific_nodes(self) -> None:
        cases = [
            (
                {
                    "graph_entity_label": "c-Fos expression",
                    "support": "Treatment increased c-Fos expression, a marker of neuronal activation.",
                },
                "Gene expression & activity markers",
            ),
            (
                {
                    "graph_entity_label": "SLC6A2 rs2242446 genotype",
                    "support": "The NET genotype moderated the cardiovascular response to MDMA.",
                },
                "Genetic moderators",
            ),
            (
                {
                    "graph_entity_label": "SIGMAR1 DNA methylation",
                    "support": "Ayahuasca exposure changed methylation across promoter CpG sites.",
                },
                "Epigenetic regulation",
            ),
            (
                {
                    "graph_entity_label": "CB1 receptor mRNA expression",
                    "support": "Treatment decreased Cnr1 mRNA expression in hippocampus.",
                },
                "Gene expression & activity markers",
            ),
            (
                {
                    "graph_entity_label": "CYP2D6 levels",
                    "assay_type": "in vitro metabolism screening",
                    "support": "Salvinorin A was metabolized by CYP2D6.",
                },
                "Drug metabolism",
            ),
            (
                {
                    "graph_entity_label": "Norepinephrine release",
                    "support": "Treatment increased extracellular norepinephrine efflux.",
                },
                "Neurotransmitter release, uptake & turnover",
            ),
            (
                {
                    "graph_entity_label": "TNF-alpha levels",
                    "support": "Treatment decreased the pro-inflammatory cytokine TNF-alpha.",
                },
                "Neuroinflammation & immune signaling",
            ),
            (
                {
                    "graph_entity_label": "Neuroplasticity",
                    "support": "The review summarized neuroplasticity findings.",
                },
                "Neuroplasticity",
            ),
            (
                {
                    "graph_entity_label": "Cellular stress",
                    "support": "The finding concerned cellular stress markers.",
                },
                "Cellular stress & mitochondrial function",
            ),
            (
                {
                    "graph_entity_label": "Paired-pulse facilitation",
                    "support": "Treatment increased paired-pulse facilitation in slice recordings.",
                },
                "Neuroplasticity",
            ),
            (
                {
                    "graph_entity_label": "GluN2B levels",
                    "support": "Treatment altered GluN2B protein levels.",
                },
                "Receptor regulation & trafficking",
            ),
            (
                {
                    "graph_entity_label": "P-glycoprotein levels",
                    "support": "Treatment changed P-glycoprotein levels at the blood-brain barrier.",
                },
                "Receptor regulation & trafficking",
            ),
            (
                {
                    "graph_entity_label": "mGluR5 expression",
                    "support": "Treatment changed mGluR5 expression.",
                },
                "Receptor regulation & trafficking",
            ),
            (
                {
                    "graph_entity_label": "Rac1 activation",
                    "support": "Treatment increased Rac1 activation.",
                },
                "Intracellular signal transduction",
            ),
            (
                {
                    "graph_entity_label": "Myelin basic protein expression",
                    "support": "Treatment changed myelin basic protein expression.",
                },
                "Neuroplasticity",
            ),
            (
                {
                    "graph_entity_label": "Monoaminergic system",
                    "support": "The finding referred broadly to the monoaminergic system.",
                },
                "",
            ),
        ]

        for row, expected in cases:
            with self.subTest(expected=expected, row=row):
                self.assertEqual(
                    molecular_effect_label(dict(row), "biomarker_readout", row["graph_entity_label"]),
                    expected,
                )

    def test_molecular_effect_parents_are_process_categories_not_free_text(self) -> None:
        self.assertEqual(
            molecular_effect_label(
                {
                    "molecular_effect_category": "Electrophysiology",
                    "specific_readout_or_marker": "Spontaneous excitatory postsynaptic currents",
                },
                "biomarker_readout",
                "Spontaneous excitatory postsynaptic currents",
            ),
            "Neuronal excitability & synaptic transmission",
        )
        self.assertEqual(
            molecular_effect_label(
                {
                    "molecular_effect_category": "Serotonin signaling",
                    "specific_readout_or_marker": "5-HT2A receptor density",
                },
                "biomarker_readout",
                "5-HT2A receptor density",
            ),
            "Receptor regulation & trafficking",
        )
        self.assertEqual(
            molecular_effect_label(
                {
                    "molecular_effect_category": "Bone metabolism",
                    "specific_readout_or_marker": "Bone mineralization marker",
                },
                "biomarker_readout",
                "Bone mineralization marker",
            ),
            "",
        )

    def test_molecular_specific_readouts_correct_wrong_parent_categories(self) -> None:
        cases = [
            ("Receptor regulation & trafficking", "Serotonin release", "Neurotransmitter release, uptake & turnover"),
            ("Gene expression & activity markers", "5-HT2A receptor mRNA expression", "Receptor regulation & trafficking"),
            ("Receptor regulation & trafficking", "NMDA receptor electrophysiology", "Neuronal excitability & synaptic transmission"),
            ("Intracellular signal transduction", "ERK1/2 phosphorylation", "Intracellular signal transduction"),
            ("Genetic moderators", "5-HT2A receptor expression", "Genetic moderators"),
        ]
        for current_parent, entity_label, expected in cases:
            with self.subTest(entity_label=entity_label):
                self.assertEqual(molecular_parent_from_specific({}, current_parent, entity_label), expected)

    def test_molecular_subtopics_cover_researcher_facing_families(self) -> None:
        cases = [
            ("Receptor regulation & trafficking", "5-HT2A receptor density", "Serotonin receptors"),
            ("Intracellular signal transduction", "Akt/mTOR phosphorylation", "PI3K–Akt–mTOR signaling"),
            ("Neuroinflammation & immune signaling", "Microglial Iba1 expression", "Microglial activation"),
            ("Neurotransmitter release, uptake & turnover", "Extracellular dopamine levels", "Dopamine release & turnover"),
            ("Neuronal excitability & synaptic transmission", "Spontaneous IPSC frequency", "Inhibitory postsynaptic currents"),
            ("Cellular stress & mitochondrial function", "Malondialdehyde and lipid peroxidation", "Oxidative damage & lipid peroxidation"),
            ("Drug metabolism", "CYP2D6-mediated metabolism", "CYP-mediated metabolism"),
            ("Endocrine response", "Cortisol and ACTH levels", "HPA-axis hormones"),
            ("Cell injury & survival", "Cleaved caspase-3 expression", "Apoptosis & caspase signaling"),
            ("Epigenetic regulation", "H3K27ac histone modification", "Histone acetylation"),
            ("Genetic moderators", "CYP2D6 metabolizer genotype", "Drug-metabolism variants"),
            ("Gut microbiome", "Gut microbiome alpha diversity", "Alpha diversity"),
            ("Neurogenesis", "BrdU-positive progenitor proliferation", "Neural progenitor proliferation"),
            ("Neuroplasticity", "GDNF protein levels", "Neurotrophic growth factors"),
            ("Receptor regulation & trafficking", "Oxytocin receptor mRNA expression", "Neuropeptide & hormone receptors"),
            ("Intracellular signal transduction", "STING/TBK pathway activation", "STING–TBK signaling"),
            ("Neuroinflammation & immune signaling", "Serum CXCL10 levels", "Cytokines & chemokines"),
            ("Neurotransmitter release, uptake & turnover", "Extracellular histamine release", "Histamine release & turnover"),
            ("Drug metabolism", "CSF metabolome", "Metabolomics & endogenous metabolism"),
            ("Genetic moderators", "OXTR gene variant", "Oxytocin & vasopressin variants"),
            ("Receptor regulation & trafficking", "orphan receptor abundance", "Other findings"),
        ]
        for parent, entity_label, expected in cases:
            with self.subTest(parent=parent, entity_label=entity_label):
                self.assertEqual(molecular_finding_subtopic({}, parent, entity_label), expected)

        specific_other_labels = {
            subtopic
            for rules in MOLECULAR_SUBTOPIC_RULES_BY_PARENT.values()
            for subtopic, _ in rules
            if subtopic.casefold().startswith("other ") and subtopic != "Other findings"
        }
        self.assertEqual(specific_other_labels, set())

    def test_molecular_subtopic_coverage_audit_rejects_large_junk_drawers(self) -> None:
        failing = pd.DataFrame(
            [
                {
                    "domain": "molecular_pathway_readout",
                    "graph_parent_label": "Example parent",
                    "molecular_finding_subtopic": "Mapped" if index < 40 else "",
                }
                for index in range(60)
            ]
        )
        passing = failing.copy()
        passing.loc[:47, "molecular_finding_subtopic"] = "Mapped"
        self.assertEqual(molecular_subtopic_coverage_summary(failing)["status"], "failed")
        self.assertEqual(molecular_subtopic_coverage_summary(passing)["status"], "ok")

        explicit_other = passing.copy()
        explicit_other.loc[:15, "molecular_finding_subtopic"] = "Other findings"
        self.assertEqual(molecular_subtopic_coverage_summary(explicit_other)["status"], "failed")

        primary_plus_sparse_reviews = pd.concat(
            [
                passing.assign(evidence_type="primary_evidence"),
                failing.assign(evidence_type="secondary_literature"),
            ],
            ignore_index=True,
        )
        summary = molecular_subtopic_coverage_summary(primary_plus_sparse_reviews)
        self.assertEqual(summary["status"], "ok")
        self.assertEqual(summary["evidence_scope"], "primary_evidence")

    def test_molecular_safety_boundaries_route_adverse_endpoints(self) -> None:
        neurotoxicity = normalize_claim_metadata(
            {
                "molecular_effect_category": "Neurotoxicity",
                "specific_readout_or_marker": "Dopaminergic terminal loss",
                "support": "MDMA produced dopaminergic terminal damage and neuronal loss.",
            },
            "molecular_pathway_readout",
        )
        self.assertEqual(neurotoxicity["domain"], "safety_tolerability")
        self.assertEqual(neurotoxicity["kg_entity_kind_override"], "safety_adverse_event")
        self.assertEqual(neurotoxicity["graph_entity_label"], "Neurotoxicity/cytotoxicity")
        self.assertEqual(neurotoxicity["normalization_boundary_reason"], "molecular_neurotoxicity_routed_to_safety")

        cardiac = normalize_claim_metadata(
            {
                "molecular_effect_category": "Electrophysiology",
                "specific_readout_or_marker": "Action potential repolarization (APD90)",
                "model_or_system": "human ventricular cardiomyocytes",
                "support": "Ibogaine prolonged APD90 repolarization.",
            },
            "molecular_pathway_readout",
        )
        self.assertEqual(cardiac["domain"], "safety_tolerability")
        self.assertEqual(cardiac["kg_entity_kind_override"], "safety_adverse_event")
        self.assertEqual(cardiac["normalization_boundary_reason"], "cardiac_electrophysiology_routed_to_safety")

        herg = normalize_claim_metadata(
            {
                "molecular_effect_category": "Ion channel activity",
                "specific_readout_or_marker": "hERG (KCNH2) current",
                "assay_type": "patch clamp",
                "support": "The compound inhibited cardiac hERG currents.",
            },
            "molecular_pathway_readout",
        )
        self.assertEqual(herg["domain"], "safety_tolerability")
        self.assertEqual(herg["normalization_boundary_reason"], "cardiac_electrophysiology_routed_to_safety")

        neuronal = normalize_claim_metadata(
            {
                "molecular_effect_category": "Electrophysiology",
                "specific_readout_or_marker": "Spontaneous excitatory postsynaptic currents",
                "model_or_system": "hippocampal slices",
            },
            "molecular_pathway_readout",
        )
        self.assertEqual(neuronal.get("domain", "molecular_pathway_readout"), "molecular_pathway_readout")
        self.assertNotEqual(neuronal.get("kg_entity_kind_override"), "safety_adverse_event")

        temperature = normalize_claim_metadata(
            {
                "molecular_effect_category": "Endocrine response",
                "specific_readout_or_marker": "Core body temperature",
                "support": "The compound caused a sustained hypothermic response.",
            },
            "molecular_pathway_readout",
        )
        self.assertEqual(temperature["domain"], "safety_tolerability")
        self.assertEqual(temperature["graph_entity_label"], "Body temperature effects")
        self.assertEqual(temperature["normalization_boundary_reason"], "molecular_physiology_routed_to_safety")

    def test_real_world_public_health_metadata_uses_naturalistic_use_graph_nodes(self) -> None:
        cases = [
            (
                {
                    "public_health_measure": "lifetime prevalence",
                    "public_health_topic_category": "epidemiology",
                    "finding_summary": "Lifetime LSD use was reported by 1.2% of the general population.",
                },
                "Population use & trends",
            ),
            (
                {
                    "public_health_measure": "Lifetime prevalence",
                    "public_health_topic_category": "Epidemiology",
                    "study_title": "Prevalence and Reasons for Microdosing Cannabis, Psilocybin, LSD, and MDMA Among US Adults",
                    "finding_summary": "The lifetime prevalence of LSD microdosing was estimated at 4.8%.",
                },
                "Population use & trends",
            ),
            (
                {
                    "public_health_measure": "route of administration",
                    "public_health_topic_category": "use patterns and administration routes",
                    "finding_summary": "Smoking was the most prevalent route among recreational DMT users.",
                },
                "Use patterns & practices",
            ),
            (
                {
                    "public_health_measure": "Reporting Odds Ratio for substance-related adverse events",
                    "public_health_topic_category": "Abuse liability and misuse",
                },
                "Acute harms & healthcare use",
            ),
            (
                {
                    "public_health_measure": "Suicidal ideation, planning, and attempts",
                    "public_health_topic_category": "Population-level safety",
                },
                "Acute harms & healthcare use",
            ),
            (
                {
                    "public_health_measure": "Population-normalised daily loads in wastewater",
                    "study_design": "Wastewater-based epidemiology surveillance",
                },
                "Population use & trends",
            ),
            (
                {
                    "public_health_measure": "ethnoracial inclusion",
                    "public_health_topic_category": "access and equity",
                },
                "Access & equity",
            ),
            (
                {
                    "public_health_measure": "Early access programme utilization and patient characteristics",
                    "public_health_topic_category": "Service delivery and access",
                },
                "Access & equity",
            ),
            (
                {
                    "public_health_measure": "Prevalence of drug type in amnesty bins",
                    "public_health_topic_category": "Harm reduction and drug adulteration",
                },
                "Drug composition & adulteration",
            ),
            (
                {
                    "public_health_measure": "Past year crime arrests",
                    "public_health_topic_category": "Criminality and Public Safety",
                },
                "Policy & legal outcomes",
            ),
            (
                {
                    "exposure_or_policy": "Psilocybin (Busting method)",
                    "public_health_measure": "Prevalence of use and preventive efficacy",
                    "population": "patients with cluster headache",
                },
                "Perceived benefits & harms",
            ),
            (
                {
                    "public_health_measure": "Rate of problematic use patterns",
                    "support": "A retreat center owner estimated that 1 in 10 participants develop a temporary obsessive relationship with ayahuasca.",
                },
                "Problematic use & dependence",
            ),
            (
                {
                    "public_health_measure": "Polysubstance use prevalence",
                    "finding_summary": "Most first-time LSD users reported co-use with cannabis or alcohol.",
                },
                "Population use & trends",
            ),
            (
                {
                    "compound_original": "Intranasal esketamine (56 mg or 84 mg) plus oral antidepressant",
                    "population": "Outpatients with treatment-resistant depression (TRD)",
                    "public_health_measure": "Treatment discontinuation rate",
                    "public_health_topic_category": "Problematic use",
                    "support": "Seven out of 21 patients discontinued treatment because of clinical reasons, lack of benefit, or side effects.",
                },
                "Treatment effectiveness & care outcomes",
            ),
            (
                {
                    "compound_original": "Intranasal esketamine (28-84 mg)",
                    "population": "Inpatients with treatment-resistant depression (TRD)",
                    "public_health_measure": "Treatment response and remission rates",
                    "public_health_topic_category": "Self-treatment",
                    "support": "In a real-world inpatient cohort, patients achieved response and remission following esketamine induction.",
                },
                "Treatment effectiveness & care outcomes",
            ),
            (
                {
                    "compound_original": "Recreational ketamine use",
                    "public_health_measure": "Urinary symptoms",
                    "public_health_topic_category": "Problematic use",
                    "support": "Among recreational ketamine users, six individuals reported urinary frequency.",
                },
                "Health & functioning outcomes",
            ),
            (
                {
                    "population": "Adults with self-reported eating disorders or disordered eating",
                    "public_health_measure": "Perceived unpleasant side effects",
                    "public_health_topic_category": "Problematic use",
                    "support": "Psilocybin was rated as having low levels of unpleasant side effects compared to alcohol or nicotine.",
                },
                "Perceived benefits & harms",
            ),
            (
                {
                    "public_health_measure": "Hallucinogen use disorder prevalence",
                    "public_health_topic_category": "Abuse liability and misuse",
                },
                "Problematic use & dependence",
            ),
        ]

        for row, expected in cases:
            with self.subTest(expected=expected, row=row):
                normalized = normalize_claim_metadata(dict(row), "real_world_public_health")
                self.assertEqual(normalized["public_health_graph_label"], expected)
                self.assertEqual(normalized["graph_entity_label"], expected)

    def test_real_world_public_health_separates_topic_context_and_source_axes(self) -> None:
        cases = [
            (
                {
                    "exposure_or_policy": "Self-administered psilocybin microdosing for self-treatment",
                    "public_health_measure": "Lifetime prevalence",
                    "study_design": "Online survey",
                },
                "Population use & trends",
                "Microdosing; Self-treatment",
                "survey",
            ),
            (
                {
                    "exposure_or_policy": "Ceremonial ayahuasca with polysubstance co-use",
                    "public_health_measure": "Emergency presentation for acute intoxication",
                    "data_source_or_study_design": "Poison-center records",
                },
                "Acute harms & healthcare use",
                "Ceremonial/retreat; Polysubstance",
                "poison_center_toxicology",
            ),
            (
                {
                    "exposure_or_policy": "Recreational MDMA use at a festival",
                    "public_health_measure": "Product mislabeling and unexpected drug detection",
                    "study_design": "On-site drug checking",
                },
                "Drug composition & adulteration",
                "Recreational/nightlife",
                "drug_checking",
            ),
            (
                {
                    "compound_original": "Intranasal esketamine",
                    "population": "Outpatients with treatment-resistant depression",
                    "public_health_topic_category": "Self-treatment",
                    "public_health_measure": "Treatment response and remission rates",
                },
                "Treatment effectiveness & care outcomes",
                "Clinical care",
                "other_or_unclear",
            ),
        ]

        for row, expected_topic, expected_context, expected_source in cases:
            with self.subTest(expected_topic=expected_topic, row=row):
                normalized = normalize_claim_metadata(dict(row), "real_world_public_health")
                self.assertEqual(normalized["graph_entity_label"], expected_topic)
                self.assertEqual(normalized["real_world_use_context"], expected_context)
                self.assertEqual(normalized["data_source_type"], expected_source)

    def test_cognitive_behavioral_metadata_uses_construct_graph_nodes(self) -> None:
        cases = [
            (
                {
                    "graph_entity_label": "Anhedonia",
                    "task_or_measure": "Sucrose preference test",
                    "support": "Treatment reversed stress-induced anhedonia.",
                },
                "Anhedonia",
            ),
            (
                {
                    "graph_entity_label": "Motor behavior",
                    "task_or_measure": "Rotarod",
                    "support": "The compound did not impair motor coordination.",
                },
                "Motor coordination",
            ),
            (
                {
                    "graph_entity_label": "Motor behavior",
                    "task_or_measure": "Head-twitch response (HTR)",
                },
                "Head-twitch response",
            ),
            (
                {
                    "graph_entity_label": "Depression-like behavior",
                    "task_or_measure": "Forced swim test",
                    "support": "The drug reduced behavioral despair.",
                },
                "Stress-coping behavior",
            ),
            (
                {
                    "graph_entity_label": "Anxiety-like behavior",
                    "task_or_measure": "Elevated plus maze",
                },
                "Anxiety-like behavior",
            ),
            (
                {
                    "graph_entity_label": "Addiction behavior",
                    "task_or_measure": "Two-bottle free-choice paradigm",
                    "support": "The compound reduced alcohol intake.",
                },
                "Drug self-administration",
            ),
            (
                {
                    "graph_entity_label": "Addiction behavior",
                    "support": "The compound blocked reinstatement of ethanol seeking.",
                },
                "Drug reinstatement",
            ),
            (
                {
                    "graph_entity_label": "Addiction behavior",
                    "outcome_measure": "Opioid Craving Scale",
                },
                "Craving",
            ),
            (
                {
                    "graph_entity_label": "Withdrawal & craving-like behavior",
                    "outcome_measure": "Paw withdrawal threshold (von Frey filaments)",
                    "support": "The compound reversed mechanical allodynia.",
                },
                "Pain behavior",
            ),
            (
                {
                    "graph_entity_label": "Withdrawal & craving-like behavior",
                    "outcome_measure": "Novel object recognition task",
                },
                "Recognition memory",
            ),
            (
                {
                    "graph_entity_label": "Memory",
                    "task_or_measure": "Novel object recognition",
                },
                "Recognition memory",
            ),
            (
                {
                    "graph_construct_label": "memory",
                    "graph_entity_label": "memory",
                    "raw_task_or_measure": "contextual fear conditioning",
                    "outcome_measure": "contextual fear conditioning",
                },
                "Fear memory",
            ),
            (
                {
                    "graph_entity_label": "Memory",
                    "outcome_measure": "CFC, TFC, and PMDAT",
                },
                "Fear memory",
            ),
            (
                {
                    "graph_entity_label": "Memory",
                    "outcome_measure": "One-trial passive avoidance task",
                },
                "Avoidance learning",
            ),
            (
                {
                    "graph_construct_label": "memory consolidation",
                    "graph_entity_label": "Memory",
                    "raw_task_or_measure": "Percentage time spent freezing",
                    "support": "Ketamine altered retrieval of the original fear memory.",
                },
                "Fear memory",
            ),
            (
                {
                    "graph_entity_label": "fear extinction",
                    "task_or_measure": "Extinction recall",
                },
                "Fear extinction",
            ),
            (
                {
                    "graph_entity_label": "working memory",
                    "outcome_measure": "N-back accuracy",
                },
                "Working memory",
            ),
            (
                {
                    "graph_entity_label": "Memory",
                    "task_or_measure": "Rey Auditory Verbal Learning Test",
                },
                "Verbal memory",
            ),
            (
                {
                    "graph_entity_label": "Memory",
                    "construct_or_behavior": "episodic memory",
                },
                "Episodic memory",
            ),
            (
                {
                    "graph_entity_label": "Cognitive flexibility",
                    "task_or_measure": "Probabilistic reversal learning task",
                },
                "Reversal learning",
            ),
            (
                {
                    "graph_entity_label": "Cognitive flexibility",
                    "task_or_measure": "Wisconsin Card Sorting Test (WCST)",
                },
                "Set shifting",
            ),
            (
                {
                    "graph_entity_label": "Psychological flexibility",
                    "task_or_measure": "Acceptance and Action Questionnaire-II (AAQ-II)",
                },
                "Psychological flexibility",
            ),
            (
                {
                    "graph_entity_label": "Threat avoidance",
                    "construct_or_behavior": "compulsivity",
                    "task_or_measure": "Marble burying test",
                },
                "Compulsivity",
            ),
            (
                {
                    "graph_entity_label": "Reward processing",
                    "task_or_measure": "Intracranial self-stimulation (ICSS)",
                },
                "Reward responsiveness",
            ),
            (
                {
                    "graph_entity_label": "Drug seeking",
                    "outcome_measure": "Alcohol deprivation effect (ADE)",
                },
                "Relapse",
            ),
            (
                {
                    "graph_entity_label": "Drug seeking",
                    "construct_or_behavior": "Alcohol cue reactivity",
                    "task_or_measure": "Alcohol-cue fMRI task",
                },
                "Drug cue reactivity",
            ),
            (
                {
                    "graph_entity_label": "Cognitive flexibility",
                    "construct_or_behavior": "Mindfulness",
                    "task_or_measure": "Five Facet Mindfulness Questionnaire (FFMQ)",
                },
                "Mindfulness",
            ),
            (
                {
                    "graph_entity_label": "Cognitive flexibility",
                    "construct_or_behavior": "Decentering",
                    "task_or_measure": "Experiences Questionnaire",
                },
                "Decentering",
            ),
            (
                {
                    "graph_entity_label": "Threat avoidance",
                    "construct_or_behavior": "Anxiety",
                    "task_or_measure": "Hamilton Anxiety Rating Scale (HAM-A)",
                    "study_title": "Anxiety and opioid craving after treatment",
                },
                "Anxiety-like behavior",
            ),
            (
                {
                    "graph_entity_label": "Reward processing",
                    "construct_or_behavior": "Anhedonia",
                    "outcome_measure": "Sucrose consumption",
                },
                "Anhedonia",
            ),
            (
                {
                    "graph_entity_label": "Social behavior",
                    "task_or_measure": "Social interaction test",
                },
                "Social interaction",
            ),
            (
                {
                    "graph_entity_label": "Social cognition & interaction",
                    "task_or_measure": "Multifaceted Empathy Test",
                },
                "Social cognition",
            ),
            (
                {
                    "graph_entity_label": "Pain behavior",
                    "support": "The compound reversed mechanical allodynia.",
                },
                "Pain behavior",
            ),
            (
                {
                    "graph_entity_label": "time perception",
                    "task_or_measure": "Temporal Bisection Task",
                    "outcome_measure": "Just noticeable difference",
                },
                "Time perception",
            ),
        ]

        for row, expected in cases:
            with self.subTest(expected=expected, row=row):
                normalized = normalize_claim_metadata(dict(row), "cognitive_behavioral")
                self.assertEqual(normalized["cognitive_behavioral_graph_label"], expected)
                self.assertEqual(normalized["graph_entity_label"], expected)

    def test_self_report_time_distortion_routes_to_subjective_effects(self) -> None:
        subjective_time = normalize_claim_metadata(
            {
                "graph_entity_label": "time perception",
                "construct_or_behavior": "Sense of time",
                "task_or_measure": "Visual Analog Scale (VAS) Sense of time",
                "outcome_measure": "VAS Sense of time",
                "support": "Participants reported that time slowed down.",
            },
            "cognitive_behavioral",
        )

        self.assertEqual(subjective_time["domain"], "subjective_experience")
        self.assertEqual(subjective_time["kg_entity_kind_override"], "subjective_experience_construct")
        self.assertEqual(subjective_time["endpoint_label_source"], "subjective_time_distortion_boundary")
        self.assertEqual(subjective_time["graph_entity_label"], "Time distortion")

    def test_behavioral_withdrawal_endpoints_are_condition_nodes(self) -> None:
        cases = [
            (
                {
                    "graph_entity_label": "Withdrawal & craving-like behavior",
                    "outcome_measure": "naloxone-precipitated withdrawal (somatic signs)",
                    "study_title": "Effects on oxycodone withdrawal and reinstatement",
                },
                "Opioid use disorder",
            ),
            (
                {
                    "graph_entity_label": "Withdrawal & craving-like behavior",
                    "outcome_measure": "elevated plus-maze test",
                    "support": "The compound reversed withdrawal-induced aversions after cessation of cocaine.",
                },
                "Cocaine use disorder",
            ),
            (
                {
                    "graph_entity_label": "Withdrawal & craving-like behavior",
                    "outcome_measure": "Defensive burying behavior",
                    "study_title": "Kappa opioid receptor pharmacology during alcohol withdrawal syndrome",
                },
                "Alcohol use disorder",
            ),
        ]

        for row, expected in cases:
            with self.subTest(expected=expected, row=row):
                normalized = normalize_claim_metadata(dict(row), "cognitive_behavioral")
                self.assertEqual(normalized["graph_entity_label"], expected)
                self.assertEqual(normalized["kg_entity_kind_override"], "condition_indication")
                self.assertEqual(normalized["endpoint_label_source"], "behavioral_withdrawal_condition_boundary")

        locomotor_control = normalize_claim_metadata(
            {
                "graph_entity_label": "Withdrawal & craving-like behavior",
                "outcome_measure": "Open Field Locomotor Activity",
                "study_title": "Both Ketamine and NBQX Attenuate Alcohol-Withdrawal Induced Depression in Male Rats.",
            },
            "cognitive_behavioral",
        )
        self.assertNotEqual(locomotor_control.get("kg_entity_kind_override"), "condition_indication")

    def test_generic_locomotor_activity_is_retained_as_controlled_detail_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            registry_path = root / "registry.json"
            routed_path = root / "routed_evidence_rows.json"
            out_dir = root / "kg"
            write_json(
                registry_path,
                {
                    "compounds": [{"label": "Ketamine", "aliases": [], "ids": {}, "status": "seeded"}],
                    "targets": [],
                    "disorders": [],
                },
            )
            write_json(
                routed_path,
                [
                    {
                        "study_doi": "10.1000/generic-locomotor",
                        "domain": "cognitive_behavioral",
                        "compound_or_exposure": "Ketamine",
                        "kg_entity_kind_override": "cognitive_behavioral_construct",
                        "construct_or_behavior": "motor behavior",
                        "task_or_measure": "open field locomotor activity",
                        "finding_summary": "Ketamine reduced total distance traveled in an open-field test.",
                        "support": "Ketamine reduced total distance traveled in an open-field test.",
                    }
                ],
            )

            build_tables(
                registry_path=registry_path,
                out_dir=out_dir,
                write_duckdb=False,
                graph_sources={
                    "routed_extractions": {
                        "path": routed_path,
                        "domain": "routed",
                        "dataset": "routed",
                        "default_evidence_type": "primary_evidence",
                        "skip_audit": True,
                    }
                },
            )

            findings = pd.read_parquet(out_dir / "findings.parquet")
            audit = pd.read_parquet(out_dir / "normalization_audit.parquet")
            edges = pd.read_parquet(out_dir / "evidence_edges.parquet")
            self.assertEqual(len(findings), 1)
            self.assertTrue(audit.empty)
            self.assertEqual(edges.iloc[0]["entity_label"], "Locomotor activity")
            self.assertEqual(findings.iloc[0]["graph_admission_status"], "paper_detail")
            self.assertEqual(
                findings.iloc[0]["graph_admission_reason"],
                "controlled_behavioral_measure_detail_only",
            )

    def test_structured_unknown_compound_is_detail_only_but_context_prose_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            registry_path = root / "registry.json"
            routed_path = root / "routed_evidence_rows.json"
            out_dir = root / "kg"
            write_json(
                registry_path,
                {
                    "compounds": [],
                    "targets": [
                        {"label": "BDNF", "aliases": [], "ids": {}, "status": "seeded"}
                    ],
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
            write_json(
                routed_path,
                [
                    {
                        "study_doi": "10.1000/unknown-compound-detail",
                        "domain": "clinical_outcome",
                        "compound": "Lorcaserin",
                        "atomic_compound_candidate": "Lorcaserin",
                        "graph_subject_label": "Lorcaserin",
                        "graph_subject_kind": "atomic_compound",
                        "graph_subject_source_field": "compound",
                        "condition_or_indication": "MDD",
                        "support": "Lorcaserin was evaluated in participants with MDD.",
                    },
                    {
                        "study_doi": "10.1000/context-is-not-compound",
                        "domain": "clinical_outcome",
                        "compound": "Chronic social defeat stress",
                        "atomic_compound_candidate": "Chronic social defeat stress",
                        "graph_subject_label": "Chronic social defeat stress",
                        "graph_subject_kind": "atomic_compound",
                        "graph_subject_source_field": "compound",
                        "condition_or_indication": "MDD",
                        "support": "The chronic social defeat stress model was used.",
                    },
                    {
                        "study_doi": "10.1000/target-is-not-compound",
                        "domain": "clinical_outcome",
                        "compound": "BDNF",
                        "atomic_compound_candidate": "BDNF",
                        "graph_subject_label": "BDNF",
                        "graph_subject_kind": "atomic_compound",
                        "graph_subject_source_field": "compound",
                        "condition_or_indication": "MDD",
                        "support": "BDNF was measured as a biomarker.",
                    },
                ],
            )

            build_tables(
                registry_path=registry_path,
                out_dir=out_dir,
                write_duckdb=False,
                graph_sources={
                    "routed_extractions": {
                        "path": routed_path,
                        "domain": "routed",
                        "dataset": "routed",
                        "default_evidence_type": "primary_evidence",
                        "skip_audit": True,
                    }
                },
            )

            findings = pd.read_parquet(out_dir / "findings.parquet")
            audit = pd.read_parquet(out_dir / "normalization_audit.parquet")
            self.assertEqual(set(findings["study_doi"]), {"10.1000/unknown-compound-detail"})
            finding = findings.iloc[0]
            self.assertEqual(finding["graph_subject_label"], "Lorcaserin")
            self.assertEqual(finding["compound"], "Lorcaserin")
            self.assertEqual(finding["graph_overview_subject_label"], "")
            self.assertEqual(finding["compound_match_type"], "validated_unregistered_compound_detail_only")
            self.assertEqual(finding["graph_admission_status"], "paper_detail")
            self.assertEqual(len(audit), 2)
            self.assertEqual(set(audit["normalization_status"]), {"compound_unmapped"})

    def test_meta_analysis_preserves_population_condition_and_normalizes_outcome_entity(self) -> None:
        depression = normalize_claim_metadata(
            {
                "source_type": "meta_analysis",
                "paper_type": "meta_analysis",
                "domain": "clinical_outcome",
                "kg_entity_kind_override": "condition_indication",
                "graph_entity_label": "Patients with major depressive disorder",
                "normalization_entity_source": "population",
                "primary_outcome": "Depressive symptom scores",
            },
            "clinical_outcome",
        )
        self.assertEqual(depression["kg_entity_kind_override"], "condition_indication")
        self.assertEqual(depression["graph_entity_label"], "Patients with major depressive disorder")

        outcome = normalize_claim_metadata(
            {
                "source_type": "meta_analysis",
                "paper_type": "meta_analysis",
                "domain": "clinical_outcome",
                "kg_entity_kind_override": "symptom_problem",
                "graph_entity_label": "response rate",
                "primary_outcome": "Depressive symptom scores",
            },
            "clinical_outcome",
        )
        self.assertEqual(outcome["kg_entity_kind_override"], "symptom_problem")
        self.assertEqual(outcome["graph_entity_label"], "Low mood & depressive symptoms")
        self.assertEqual(
            outcome["normalization_boundary_reason"],
            "meta_analysis_population_or_outcome_resolved_to_endpoint",
        )

        primary = normalize_claim_metadata(
            {
                "source_type": "primary_study",
                "domain": "clinical_outcome",
                "kg_entity_kind_override": "condition_indication",
                "graph_entity_label": "Patients with depression",
                "primary_outcome": "Depressive symptom scores",
            },
            "clinical_outcome",
        )
        self.assertEqual(primary["graph_entity_label"], "Patients with depression")

        with tempfile.TemporaryDirectory() as tmpdir:
            registry_path = Path(tmpdir) / "registry.json"
            write_json(
                registry_path,
                {
                    "compounds": [],
                    "targets": [],
                    "disorders": [
                        {
                            "label": "Major depressive disorder",
                            "aliases": ["MDD", "major depression"],
                            "ids": {},
                            "status": "seeded",
                        }
                    ],
                },
            )
            registry = registry_lookup(registry_path)
            condition_match = graphable_entity_match(
                depression,
                "clinical_outcome",
                "condition_indication",
                depression["graph_entity_label"],
                registry,
                {},
            )
            self.assertTrue(condition_match["matched"])
            self.assertEqual(condition_match["label"], "Major depressive disorder")
            fallback_match = graphable_entity_match(
                {
                    "source_type": "meta_analysis",
                    "paper_type": "meta_analysis",
                    "domain": "clinical_outcome",
                    "kg_entity_kind_override": "condition_indication",
                    "graph_entity_label": "Cancer patients",
                    "normalization_entity_source": "population",
                    "primary_outcome": "Psychological distress",
                },
                "clinical_outcome",
                "condition_indication",
                "Cancer patients",
                registry,
                {},
            )
            self.assertTrue(fallback_match["matched"])
            self.assertEqual(fallback_match["kind"], "symptom_problem")
            self.assertEqual(fallback_match["label"], "Psychological distress")
            self.assertEqual(fallback_match["match_type"], "meta_analysis_population_endpoint_fallback")

            projection_registry_path = Path(tmpdir) / "projection_registry.json"
            write_json(
                projection_registry_path,
                {
                    "compounds": [
                        {"label": "Ketamine", "aliases": [], "ids": {}, "status": "seeded"}
                    ],
                    "targets": [],
                    "disorders": [
                        {
                            "label": "Major depressive disorder",
                            "aliases": ["MDD", "major depression"],
                            "ids": {},
                            "status": "seeded",
                        }
                    ],
                },
            )
            projection_rows = condition_expanded_rows(
                {
                    "source_type": "meta_analysis",
                    "paper_type": "meta_analysis",
                    "domain": "clinical_outcome",
                    "compound": "Ketamine",
                    "kg_entity_kind_override": "symptom_problem",
                    "graph_entity_label": "Low mood & depressive symptoms",
                    "population": "Adults with MDD",
                },
                "clinical_outcome",
                registry_lookup(projection_registry_path),
            )
            self.assertEqual(len(projection_rows), 2)
            self.assertEqual(projection_rows[1]["kg_entity_kind_override"], "condition_indication")
            self.assertEqual(projection_rows[1]["graph_entity_label"], "Major depressive disorder")

    def test_selective_entity_splitting_expands_lists_but_preserves_complexes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            registry_path = root / "registry.json"
            routed_path = root / "routed_evidence_rows.json"
            out_dir = root / "kg"
            write_json(
                registry_path,
                {
                    "compounds": [
                        {"label": "Psilocybin", "aliases": [], "ids": {}, "status": "seeded"},
                        {"label": "MDMA", "aliases": [], "ids": {}, "status": "seeded"},
                        {"label": "MDA", "aliases": [], "ids": {}, "status": "seeded"},
                        {"label": "HMMA", "aliases": [], "ids": {}, "status": "seeded"},
                        {"label": "HMA", "aliases": [], "ids": {}, "status": "seeded"},
                    ],
                    "targets": [
                        {
                            "label": "mu opioid receptor (OPRM1)",
                            "aliases": ["mu opioid receptor"],
                            "ids": {},
                            "status": "seeded",
                        },
                        {
                            "label": "kappa opioid receptor (OPRK1)",
                            "aliases": ["kappa opioid receptor"],
                            "ids": {},
                            "status": "seeded",
                        },
                        {
                            "label": "BDNF",
                            "aliases": [],
                            "ids": {},
                            "status": "biomarker_readout_needs_external_id_lookup",
                        },
                        {
                            "label": "mTOR",
                            "aliases": ["mTOR signaling complex"],
                            "ids": {},
                            "status": "pathway_node_needs_external_id_lookup",
                        },
                    ],
                    "disorders": [
                        {
                            "label": "Anxiety disorders",
                            "aliases": ["anxiety symptoms"],
                            "ids": {},
                            "status": "seeded",
                        },
                        {
                            "label": "Depressive disorders",
                            "aliases": ["depressive symptoms"],
                            "ids": {},
                            "status": "seeded",
                        },
                    ],
                },
            )
            write_json(
                routed_path,
                [
                    {
                        "study_doi": "10.1000/shared-target-name",
                        "domain": "molecular_target",
                        "compound": "Psilocybin",
                        "target": "mu and kappa opioid receptors",
                        "support": "Binding was measured at mu and kappa opioid receptors.",
                    },
                    {
                        "study_doi": "10.1000/pk-analyte-list",
                        "domain": "pharmacokinetics_exposure",
                        "compound_or_analyte": "MDMA",
                        "primary_graph_anchor_kind": "compound",
                        "metabolite_or_analyte": "MDA, HMMA, HMA",
                        "pk_graph_object_kind": "metabolite_or_analyte",
                        "pk_graph_object_label": "MDA, HMMA, HMA",
                        "pk_relationship_type": "metabolized_to",
                        "support": "The analysis quantified MDA, HMMA, and HMA.",
                    },
                    {
                        "study_doi": "10.1000/combined-symptoms",
                        "domain": "clinical_outcome",
                        "compound": "Psilocybin",
                        "kg_entity_kind_override": "symptom_problem",
                        "graph_entity_label": "anxiety and depression symptoms",
                        "support": "Anxiety and depression symptoms were measured separately.",
                    },
                    {
                        "study_doi": "10.1000/semantic-complex",
                        "domain": "molecular_pathway_readout",
                        "compound": "Psilocybin",
                        "kg_entity_kind_override": "pathway_process",
                        "graph_entity_label": "BDNF and mTOR signaling complex",
                        "support": "The paper described one BDNF and mTOR signaling complex.",
                    },
                ],
            )

            build_tables(
                registry_path=registry_path,
                out_dir=out_dir,
                write_duckdb=False,
                graph_sources={
                    "routed_extractions": {
                        "path": routed_path,
                        "domain": "routed",
                        "dataset": "routed",
                        "default_evidence_type": "primary_evidence",
                        "skip_audit": True,
                    }
                },
            )

            edges = pd.read_parquet(out_dir / "evidence_edges.parquet")
            labels_by_doi = edges.groupby("study_doi")["entity_label"].apply(set).to_dict()
            self.assertEqual(
                labels_by_doi["10.1000/shared-target-name"],
                {"mu opioid receptor (OPRM1)", "kappa opioid receptor (OPRK1)"},
            )
            self.assertEqual(
                labels_by_doi["10.1000/pk-analyte-list"],
                {"MDA", "HMMA", "HMA"},
            )
            self.assertEqual(
                labels_by_doi["10.1000/combined-symptoms"],
                {"Anxiety & panic", "Low mood & depressive symptoms"},
            )
            audit = pd.read_parquet(out_dir / "normalization_audit.parquet")
            complex_audit = audit[audit["study_doi"] == "10.1000/semantic-complex"]
            self.assertEqual(len(complex_audit), 1)
            self.assertNotIn("10.1000/semantic-complex", labels_by_doi)

    def test_cognitive_behavioral_specific_nodes_retain_parent_families(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            registry_path = root / "registry.json"
            routed_path = root / "routed_evidence_rows.json"
            out_dir = root / "kg"
            write_json(
                registry_path,
                {
                    "compounds": [{"label": "Ketamine", "aliases": [], "ids": {}, "status": "seeded"}],
                    "targets": [],
                    "disorders": [],
                },
            )
            write_json(
                routed_path,
                [
                    {
                        "study_doi": "10.1000/verbal-memory",
                        "domain": "cognitive_behavioral",
                        "compound_or_exposure": "Ketamine",
                        "graph_construct_label": "Memory",
                        "task_or_measure": "Rey Auditory Verbal Learning Test",
                        "support": "Verbal recall was reduced.",
                    },
                    {
                        "study_doi": "10.1000/reinstatement",
                        "domain": "cognitive_behavioral",
                        "compound_or_exposure": "Ketamine",
                        "graph_construct_label": "Drug seeking",
                        "task_or_measure": "Cue-induced reinstatement after extinction",
                        "support": "Ketamine reduced reinstatement of drug seeking.",
                    },
                ],
            )

            build_tables(
                registry_path=registry_path,
                out_dir=out_dir,
                write_duckdb=False,
                graph_sources={
                    "routed_extractions": {
                        "path": routed_path,
                        "domain": "routed",
                        "dataset": "routed",
                        "default_evidence_type": "primary_evidence",
                        "skip_audit": True,
                    }
                },
            )

            edges = pd.read_parquet(out_dir / "evidence_edges.parquet")
            by_doi = {row["study_doi"]: row for row in edges.to_dict(orient="records")}
            self.assertEqual(by_doi["10.1000/verbal-memory"]["entity_label"], "Verbal memory")
            self.assertEqual(by_doi["10.1000/verbal-memory"]["graph_parent_label"], "Memory")
            self.assertEqual(by_doi["10.1000/reinstatement"]["entity_label"], "Drug reinstatement")
            self.assertEqual(by_doi["10.1000/reinstatement"]["graph_parent_label"], "Drug seeking")

            entities = pd.read_parquet(out_dir / "entities.parquet")
            self.assertIn("Memory", set(entities["label"]))
            self.assertIn("Drug seeking", set(entities["label"]))

    def test_subjective_experience_metadata_uses_experience_graph_nodes(self) -> None:
        cases = [
            (
                {
                    "graph_entity_label": "Hallucinogenic effects",
                    "instrument_or_measure": "Hallucinogen Rating Scale (HRS)",
                    "support": "Participants reported visual hallucinations and synaesthesia.",
                },
                "Perceptual alterations",
            ),
            (
                {
                    "graph_entity_label": "Derealization",
                    "instrument_or_measure": "Clinician-Administered Dissociative States Scale (CADSS)",
                },
                "Dissociation",
            ),
            (
                {
                    "graph_entity_label": "Subjective drug intensity",
                    "support": "Participants rated global subjective intensity and highness.",
                },
                "Subjective intensity",
            ),
            (
                {
                    "graph_entity_label": "Oceanic boundlessness",
                    "instrument_or_measure": "5D-ASC OBN subscale",
                },
                "Mystical-type experience",
            ),
            (
                {
                    "graph_entity_label": "Near-death experience phenomenology",
                    "instrument_or_measure": "Greyson NDE scale",
                },
                "Near-death-like experience",
            ),
            (
                {
                    "graph_entity_label": "Presence of meaning in life",
                    "support": "Participants described greater meaningfulness and purpose in life.",
                },
                "Personal significance",
            ),
            (
                {
                    "graph_entity_label": "Changed meaning of percepts",
                    "instrument_or_measure": "5D-ASC subscale",
                },
                "Perceptual alterations",
            ),
            (
                {
                    "graph_entity_label": "Spiritual significance",
                    "support": "Participants described sacred meaning and a more spiritual outlook.",
                },
                "Spiritual significance",
            ),
            (
                {
                    "graph_entity_label": "Social connection",
                    "support": "Participants reported stronger connectedness, closeness, and emotional intimacy.",
                },
                "Connectedness",
            ),
            (
                {
                    "graph_entity_label": "Empathy",
                    "support": "Participants reported stronger emotional empathy.",
                },
                "Empathy",
            ),
            (
                {
                    "graph_entity_label": "Euphoria",
                    "instrument_or_measure": "Visual Analogue Scale (VAS)",
                    "support": "Participants reported euphoria, drug liking, and good effects.",
                },
                "Euphoria",
            ),
            (
                {
                    "graph_entity_label": "Euphoria",
                    "instrument_or_measure": "Hallucinogen Rating Scale (HRS)",
                    "support": "The HRS affect item captured the reported euphoria.",
                },
                "Euphoria",
            ),
            (
                {
                    "graph_entity_label": "Contentedness",
                    "instrument_or_measure": "Bond and Lader Visual Analogue Mood Rating Scale",
                    "support": "The scale measured calmness, alertness, and contentedness.",
                },
                "Positive affect",
            ),
            (
                {
                    "graph_entity_label": "Subjective intensity",
                    "instrument_or_measure": "100-mm visual analogue scale",
                    "support": "Participants rated the subjective intensity of the drug effect.",
                },
                "Subjective intensity",
            ),
            (
                {
                    "graph_entity_label": "Simple and complex visual hallucinations",
                    "instrument_or_measure": "Visual Analogue Scale (VAS)",
                    "support": "Participants reported visual hallucinations and complex imagery.",
                },
                "Perceptual alterations",
            ),
            (
                {
                    "graph_entity_label": "Disembodiment",
                    "support": "Participants reported altered bodily sensations.",
                },
                "Dissociation",
            ),
            (
                {
                    "graph_entity_label": "Bodily sensations",
                    "support": "Participants reported unusual bodily sensations.",
                },
                "Somatic sensations",
            ),
            (
                {
                    "graph_entity_label": "Altered states of consciousness",
                    "instrument_or_measure": "5D-ASC",
                },
                "Altered state profile",
            ),
            (
                {
                    "graph_entity_label": "altered time perception",
                    "instrument_or_measure": "semi-structured interview",
                    "support": "Participants described time dilation and loss of temporal awareness.",
                },
                "Time distortion",
            ),
        ]

        for row, expected in cases:
            with self.subTest(expected=expected, row=row):
                normalized = normalize_claim_metadata(dict(row), "subjective_experience")
                self.assertEqual(normalized["subjective_experience_graph_label"], expected)
                self.assertEqual(normalized["graph_entity_label"], expected)

    def test_subjective_experience_safety_boundary_routes_pathological_findings(self) -> None:
        safety_cases = [
            (
                {
                    "graph_entity_label": "Depersonalization-Derealization Disorder (DDD)",
                    "support": "The patient developed daily panic attacks and persistent DP/DR after use.",
                },
                "Dissociation",
            ),
            (
                {
                    "graph_entity_label": "Adverse mental states",
                    "support": "Participants reported adverse mental states following ayahuasca use.",
                },
                "Challenging subjective effects",
            ),
        ]

        for row, expected in safety_cases:
            with self.subTest(expected=expected, row=row):
                normalized = normalize_claim_metadata(dict(row), "subjective_experience")
                self.assertEqual(normalized["kg_entity_kind_override"], "safety_adverse_event")
                self.assertEqual(normalized["endpoint_label_source"], "subjective_experience_safety_boundary")
                self.assertEqual(normalized["graph_entity_label"], expected)
                self.assertNotIn("subjective_experience_graph_label", normalized)

        ordinary_experience = normalize_claim_metadata(
            {
                "graph_entity_label": "Dissociation",
                "instrument_or_measure": "Clinician-Administered Dissociative States Scale (CADSS)",
                "support": "Ketamine acutely increased CADSS dissociation scores compared with placebo.",
            },
            "subjective_experience",
        )
        self.assertEqual(ordinary_experience["graph_entity_label"], "Dissociation")
        self.assertNotEqual(ordinary_experience.get("kg_entity_kind_override"), "safety_adverse_event")

    def test_psychotomimetic_effects_are_separated_from_psychosis_risk(self) -> None:
        psychotomimetic = normalize_claim_metadata(
            {
                "graph_entity_label": "Psychosis-like adverse effects",
                "support": "Ketamine caused transient psychotomimetic effects measured with the BPRS.",
            },
            "safety_tolerability",
        )
        self.assertEqual(psychotomimetic["domain"], "cognitive_behavioral")
        self.assertEqual(psychotomimetic["kg_entity_kind_override"], "cognitive_behavioral_construct")
        self.assertEqual(psychotomimetic["graph_entity_label"], "Psychotomimetic effects")

        psychosis_risk = normalize_claim_metadata(
            {
                "graph_entity_label": "Psychosis-like effects",
                "support": "Psilocybin may induce or exacerbate psychosis in vulnerable individuals.",
            },
            "clinical_outcome",
        )
        self.assertEqual(psychosis_risk["domain"], "safety_tolerability")
        self.assertEqual(psychosis_risk["kg_entity_kind_override"], "safety_adverse_event")
        self.assertEqual(psychosis_risk["graph_entity_label"], "Psychosis risk")

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            registry_path = root / "registry.json"
            routed_path = root / "routed_evidence_rows.json"
            out_dir = root / "kg"
            write_json(
                registry_path,
                {
                    "compounds": [{"label": "Ketamine", "aliases": [], "ids": {}, "status": "seeded"}],
                    "targets": [],
                    "disorders": [],
                },
            )
            write_json(
                routed_path,
                [
                    {
                        "study_doi": "10.1000/psychotomimetic-boundary",
                        "domain": "safety_tolerability",
                        "compound_or_exposure": "Ketamine",
                        "graph_entity_label": "Psychosis-like adverse effects",
                        "support": "Ketamine caused transient psychotomimetic effects measured with the BPRS.",
                    }
                ],
            )
            build_tables(
                registry_path=registry_path,
                out_dir=out_dir,
                write_duckdb=False,
                graph_sources={
                    "routed_extractions": {
                        "path": routed_path,
                        "domain": "routed",
                        "dataset": "routed",
                        "default_evidence_type": "secondary_literature",
                        "skip_audit": True,
                    }
                },
            )
            finding = pd.read_parquet(out_dir / "findings.parquet").iloc[0]
            self.assertEqual(finding["domain"], "cognitive_behavioral")
            self.assertEqual(finding["graph_entity_label"], "Psychotomimetic effects")

    def test_review_context_metadata_is_normalized_for_sidebar_facets(self) -> None:
        frame = {
            "review_contribution_type": "evidence_synthesis",
            "review_design": "Systematic scoping review following PRISMA-ScR guidance.",
            "source_completeness": "article_text",
            "major_aspects": [
                {"aspect_type": "efficacy_or_effect", "importance": "paper_defining"},
                {"aspect_type": "safety", "importance": "major_supporting"},
                {"aspect_type": "mechanism", "importance": "paper_defining"},
            ],
        }
        normalized = normalize_claim_metadata(
            {
                "review_extraction_method": "paper_centered_one_pass_v2",
                "paper_type": "review",
                "paper_frame_json": json.dumps(frame),
                "graph_entity_label": "Major depressive disorder",
            },
            "clinical_outcome",
        )
        self.assertEqual(normalized["review_contribution_type"], "evidence_synthesis")
        self.assertEqual(normalized["review_design_category"], "scoping_review")
        self.assertEqual(
            review_design_category(
                {"paper_type": "narrative_review"},
                {"review_design": "A systematic search is discussed as background."},
            ),
            "narrative_or_literature_review",
        )

    def test_route_native_pharmacokinetics_fields_are_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            registry_path = root / "registry.json"
            routed_path = root / "routed_evidence_rows.json"
            out_dir = root / "kg"
            write_json(
                registry_path,
                {
                    "compounds": [
                        {"label": "Ketamine", "aliases": [], "ids": {}, "status": "seeded"},
                        {"label": "Norketamine", "aliases": [], "ids": {}, "status": "seeded"},
                    ],
                    "targets": [
                        {
                            "label": "NMDA receptor",
                            "aliases": ["NMDAR"],
                            "ids": {},
                            "status": "complex_target_needs_subunit_mapping",
                        }
                    ],
                    "disorders": [],
                },
            )
            write_json(
                routed_path,
                [
                    {
                        "study_doi": "10.1000/pk",
                        "domain": "pharmacokinetics_exposure",
                        "compound_or_analyte": "Ketamine",
                        "primary_graph_anchor_kind": "pharmacokinetic_parameter",
                        "pk_or_exposure_parameter": "Cmax",
                        "analyte_type": "parent",
                        "metabolite_or_analyte": "ketamine",
                        "matrix": "plasma",
                        "value": "123",
                        "unit": "ng/mL",
                        "dose": "0.5 mg/kg",
                        "route_of_administration": "intravenous",
                        "sampling_time_or_window": "40 minutes post-dose",
                        "population_or_system": "healthy volunteers",
                        "model_or_method": "noncompartmental analysis",
                        "exposure_response_or_pk_effect": "higher peak exposure",
                        "finding_summary": "Ketamine reached peak plasma concentration 40 minutes after dosing.",
                        "support": "Ketamine reached peak plasma concentration 40 minutes after dosing.",
                    },
                    {
                        "study_doi": "10.1000/pk-analyte",
                        "domain": "pharmacokinetics_exposure",
                        "compound_or_analyte": "Ketamine",
                        "primary_graph_anchor_kind": "compound",
                        "pk_or_exposure_parameter": "concentration level",
                        "analyte_type": "parent",
                        "metabolite_or_analyte": "Ketamine",
                        "matrix": "plasma",
                        "value": "higher",
                        "dose": "0.5 mg/kg",
                        "route_of_administration": "intravenous",
                        "sampling_time_or_window": "0-230 minutes postinfusion",
                        "population_or_system": "participants with depression",
                        "finding_summary": "Ketamine plasma concentrations were higher in one subgroup.",
                        "support": "Ketamine plasma concentrations were higher in one subgroup.",
                    },
                    {
                        "study_doi": "10.1000/pk-metabolite",
                        "domain": "pharmacokinetics_exposure",
                        "compound_or_analyte": "Ketamine",
                        "primary_graph_anchor_kind": "compound",
                        "pk_or_exposure_parameter": "metabolite concentration",
                        "analyte_type": "active metabolite",
                        "metabolite_or_analyte": "Norketamine",
                        "matrix": "plasma",
                        "value": "formed after dosing",
                        "dose": "0.5 mg/kg",
                        "route_of_administration": "intravenous",
                        "population_or_system": "participants with depression",
                        "finding_summary": "Ketamine was metabolized to norketamine after dosing.",
                        "support": "Ketamine was metabolized to norketamine after dosing.",
                    },
                    {
                        "study_doi": "10.1000/pk-receptor",
                        "domain": "pharmacokinetics_exposure",
                        "compound_or_analyte": "Ketamine",
                        "primary_graph_anchor_kind": "target",
                        "pk_or_exposure_parameter": "receptor occupancy",
                        "metabolic_or_transport_target": "NMDA receptor",
                        "finding_summary": "Ketamine produced measurable NMDA receptor occupancy.",
                        "support": "Ketamine produced measurable NMDA receptor occupancy.",
                    },
                ],
            )

            build_tables(
                registry_path=registry_path,
                out_dir=out_dir,
                write_duckdb=False,
                graph_sources={
                    "routed_extractions": {
                        "path": routed_path,
                        "domain": "routed",
                        "dataset": "routed",
                        "default_evidence_type": "primary_evidence",
                        "skip_audit": True,
                    }
                },
            )

            findings = pd.read_parquet(out_dir / "findings.parquet")
            by_doi = {row["study_doi"]: row for row in findings.to_dict(orient="records")}
            self.assertEqual(by_doi["10.1000/pk"]["entity_label"], "Cmax")
            self.assertEqual(by_doi["10.1000/pk"]["primary_graph_anchor_kind"], "pharmacokinetic_parameter")
            self.assertEqual(by_doi["10.1000/pk"]["pk_relationship_type"], "exposure_characterized")
            self.assertEqual(by_doi["10.1000/pk"]["pk_relationship_label"], "exposure characterized")
            self.assertEqual(by_doi["10.1000/pk"]["pk_graph_object_kind"], "parent_or_analyte_exposure")
            self.assertEqual(by_doi["10.1000/pk"]["pk_graph_object_label"], "Ketamine plasma exposure")
            self.assertEqual(by_doi["10.1000/pk"]["pharmacokinetic_display_label"], "Ketamine plasma exposure")
            self.assertEqual(by_doi["10.1000/pk"]["pk_or_exposure_parameter"], "Cmax")
            self.assertEqual(by_doi["10.1000/pk"]["metabolite_or_analyte"], "ketamine")
            self.assertEqual(by_doi["10.1000/pk"]["matrix"], "plasma")
            self.assertEqual(by_doi["10.1000/pk"]["route_of_administration"], "intravenous")
            self.assertEqual(by_doi["10.1000/pk"]["sampling_time_or_window"], "40 minutes post-dose")
            self.assertEqual(by_doi["10.1000/pk"]["model_or_method"], "noncompartmental analysis")
            self.assertEqual(by_doi["10.1000/pk"]["exposure_response_or_pk_effect"], "higher peak exposure")
            self.assertEqual(by_doi["10.1000/pk-analyte"]["entity_label"], "Concentration")
            self.assertEqual(by_doi["10.1000/pk-analyte"]["primary_graph_anchor_kind"], "compound")
            self.assertEqual(by_doi["10.1000/pk-analyte"]["pk_graph_object_label"], "Ketamine plasma exposure")
            self.assertEqual(by_doi["10.1000/pk-analyte"]["pharmacokinetic_display_label"], "Ketamine plasma exposure")
            self.assertEqual(by_doi["10.1000/pk-metabolite"]["entity_label"], "Norketamine")
            self.assertEqual(by_doi["10.1000/pk-metabolite"]["primary_graph_anchor_kind"], "compound")
            self.assertEqual(by_doi["10.1000/pk-metabolite"]["pk_relationship_type"], "metabolized_to")
            self.assertEqual(by_doi["10.1000/pk-metabolite"]["pk_graph_object_kind"], "metabolite_or_analyte")
            self.assertEqual(by_doi["10.1000/pk-metabolite"]["pk_graph_object_label"], "Norketamine")
            self.assertEqual(by_doi["10.1000/pk-metabolite"]["pharmacokinetic_display_label"], "Norketamine")
            self.assertEqual(by_doi["10.1000/pk-receptor"]["entity_label"], "NMDA receptor")
            self.assertEqual(by_doi["10.1000/pk-receptor"]["domain"], "molecular_target")
            self.assertEqual(by_doi["10.1000/pk-receptor"]["primary_graph_anchor_kind"], "target")
            self.assertEqual(by_doi["10.1000/pk-receptor"]["pk_relationship_type"], "exposure_linked_to_effect")
            self.assertEqual(by_doi["10.1000/pk-receptor"]["pk_graph_object_kind"], "effect_or_response")
            self.assertEqual(by_doi["10.1000/pk-receptor"]["pk_graph_object_label"], "NMDA receptor occupancy")
            self.assertEqual(by_doi["10.1000/pk-receptor"]["pharmacokinetic_display_label"], "")

    def test_mechanistic_postprocessing_resolves_target_pathway_and_readout_kinds(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            registry_path = root / "registry.json"
            routed_path = root / "routed_evidence_rows.json"
            out_dir = root / "kg"
            write_json(
                registry_path,
                {
                    "compounds": [{"label": "Psilocybin", "aliases": [], "ids": {}, "status": "seeded"}],
                    "targets": [
                        {
                            "label": "NMDA receptor",
                            "aliases": ["NMDAR", "NMDAR binding"],
                            "ids": {},
                            "status": "complex_target_needs_subunit_mapping",
                        },
                        {
                            "label": "SERT (SLC6A4)",
                            "aliases": ["SERT", "5-HT transporter", "serotonin transporter"],
                            "ids": {},
                            "status": "needs_external_id_lookup",
                        },
                        {
                            "label": "BDNF",
                            "aliases": ["brain-derived neurotrophic factor"],
                            "ids": {},
                            "status": "biomarker_readout_needs_external_id_lookup",
                        },
                        {
                            "label": "c-Fos",
                            "aliases": ["Fos", "cFos"],
                            "ids": {},
                            "status": "biomarker_readout_needs_external_id_lookup",
                        },
                        {
                            "label": "Dopamine",
                            "aliases": ["dopamine"],
                            "ids": {},
                            "status": "neurotransmitter_or_ligand",
                        },
                        {
                            "label": "mTORC1",
                            "aliases": ["mTOR signaling"],
                            "ids": {},
                            "status": "pathway_node_needs_external_id_lookup",
                        },
                        {
                            "label": "ERK",
                            "aliases": ["ERK1/2", "pERK"],
                            "ids": {},
                            "status": "pathway_node_needs_external_id_lookup",
                        },
                        {
                            "label": "Neuroplasticity",
                            "aliases": ["dendritic spine density", "long-term potentiation"],
                            "ids": {},
                            "status": "pathway_or_process",
                        },
                        {
                            "label": "5-HT receptor family",
                            "aliases": ["serotonin receptor family", "5-HT recognition sites"],
                            "ids": {},
                            "status": "broad_target_family",
                        },
                        {
                            "label": "5-HT1A",
                            "aliases": ["5-HT1A receptor"],
                            "ids": {},
                            "status": "needs_external_id_lookup",
                        },
                        {
                            "label": "5-HT1D",
                            "aliases": ["5-HT1D receptor"],
                            "ids": {},
                            "status": "needs_external_id_lookup",
                        },
                        {
                            "label": "5-HT2A",
                            "aliases": ["5-HT2A receptor"],
                            "ids": {},
                            "status": "needs_external_id_lookup",
                        },
                        {
                            "label": "5-HT2C",
                            "aliases": ["5-HT2C receptor"],
                            "ids": {},
                            "status": "needs_external_id_lookup",
                        },
                        {
                            "label": "5-HT2 receptor family",
                            "aliases": ["5-HT2 receptor", "5-HT2 receptors"],
                            "ids": {},
                            "status": "broad_target_family",
                        },
                        {
                            "label": "5-HT2A/2C receptor",
                            "aliases": ["5-HT2A/C receptor", "5-HT2B/2C receptor"],
                            "ids": {},
                            "status": "composite_target_needs_split",
                        },
                        {
                            "label": "Nicotinic acetylcholine receptor family",
                            "aliases": ["nicotinic receptors", "nAChR"],
                            "ids": {},
                            "status": "broad_target_family",
                        },
                        {
                            "label": "Adrenergic receptor family",
                            "aliases": ["alpha 2-adrenergic sites"],
                            "ids": {},
                            "status": "broad_target_family",
                        },
                        {
                            "label": "Dopamine receptor family",
                            "aliases": ["D2-like dopamine receptors"],
                            "ids": {},
                            "status": "broad_target_family",
                        },
                        {
                            "label": "alpha7 nicotinic acetylcholine receptor (CHRNA7)",
                            "aliases": ["alpha 7-nicotinic acetylcholine receptor", "alpha7 nAChR"],
                            "ids": {},
                            "status": "needs_external_id_lookup",
                        },
                        {
                            "label": "kappa opioid receptor (OPRK1)",
                            "aliases": ["KOR", "kappa 1-opioid receptor"],
                            "ids": {},
                            "status": "needs_external_id_lookup",
                        },
                        {
                            "label": "GluN1 (GRIN1)",
                            "aliases": ["GluN1-1a"],
                            "ids": {},
                            "status": "needs_external_id_lookup",
                        },
                        {
                            "label": "GluN2A (GRIN2A)",
                            "aliases": ["GluN2A NMDA receptor"],
                            "ids": {},
                            "status": "needs_external_id_lookup",
                        },
                        {
                            "label": "NET (SLC6A2)",
                            "aliases": ["NET", "norepinephrine transporter"],
                            "ids": {},
                            "status": "needs_external_id_lookup",
                        },
                        {
                            "label": "OCT2 (SLC22A2)",
                            "aliases": ["hOCT2"],
                            "ids": {},
                            "status": "needs_external_id_lookup",
                        },
                    ],
                    "disorders": [],
                },
            )
            write_json(
                routed_path,
                [
                    {
                        "study_doi": "10.1000/direct-target",
                        "domain": "molecular_pathway_readout",
                        "compound": "Psilocybin",
                        "pathway_or_readout": "NMDAR binding affinity (Ki)",
                        "assay_type": "radioligand binding",
                        "support": "Psilocybin competed for NMDAR binding sites with measurable Ki.",
                    },
                    {
                        "study_doi": "10.1000/target-readout",
                        "domain": "molecular_pathway_readout",
                        "compound": "Psilocybin",
                        "pathway_or_readout": "SERT protein levels",
                        "assay_type": "Western blot",
                        "support": "Treatment increased SERT protein levels in cortical tissue.",
                    },
                    {
                        "study_doi": "10.1000/direct-target-signaling-context",
                        "domain": "molecular_target",
                        "compound": "Psilocybin",
                        "target": "5-HT transporter",
                        "support": "Treatment enhanced serotonin signaling in a behavioral rescue assay.",
                    },
                    {
                        "study_doi": "10.1000/biomarker",
                        "domain": "molecular_target",
                        "compound": "Psilocybin",
                        "target": "BDNF",
                        "support": "BDNF expression increased after treatment.",
                    },
                    {
                        "study_doi": "10.1000/c-fos",
                        "domain": "molecular_pathway_readout",
                        "compound": "Psilocybin",
                        "pathway_or_readout": "c-Fos expression",
                        "assay_type": "immunohistochemistry",
                        "support": "Treatment increased c-Fos expression, a marker of neuronal activation.",
                    },
                    {
                        "study_doi": "10.1000/pathway",
                        "domain": "molecular_target",
                        "compound": "Psilocybin",
                        "target": "mTOR signaling",
                        "support": "mTOR signaling was activated after treatment.",
                    },
                    {
                        "study_doi": "10.1000/pathway-phosphorylation",
                        "domain": "molecular_pathway_readout",
                        "compound": "Psilocybin",
                        "pathway_or_readout": "ERK1/2 phosphorylation",
                        "assay_type": "Western blot",
                        "support": "ERK1/2 phosphorylation increased after treatment.",
                    },
                    {
                        "study_doi": "10.1000/neuroplasticity-sublabel",
                        "domain": "molecular_pathway_readout",
                        "compound": "Psilocybin",
                        "pathway_or_readout": "dendritic spine density",
                        "assay_type": "Golgi staining",
                        "support": "Dendritic spine density increased after treatment.",
                    },
                    {
                        "study_doi": "10.1000/dopamine-uptake",
                        "domain": "molecular_pathway_readout",
                        "compound": "Psilocybin",
                        "pathway_or_readout": "[3H]-dopamine uptake",
                        "assay_type": "synaptosomal P2 preparation uptake assay",
                        "support": "Treatment inhibited [3H]-dopamine uptake in synaptosomal preparations.",
                    },
                    {
                        "study_doi": "10.1000/perineuronal-net",
                        "domain": "molecular_pathway_readout",
                        "compound": "Psilocybin",
                        "pathway_or_readout": "Perineuronal net intensity around PV neurons",
                        "assay_type": "histological staining",
                        "support": "Treatment reduced perineuronal net intensity around PV neurons.",
                    },
                    {
                        "study_doi": "10.1000/generic-neurotransmitter-specific-readout",
                        "domain": "molecular_pathway_readout",
                        "compound": "Psilocybin",
                        "molecular_effect_category": "Neurotransmitter signaling",
                        "specific_readout_or_marker": "5-HT1A receptor expression",
                        "assay_type": "Western blot",
                        "support": "Treatment increased 5-HT1A receptor expression in cortical tissue.",
                    },
                    {
                        "study_doi": "10.1000/generic-neurotransmitter-unspecified",
                        "domain": "molecular_pathway_readout",
                        "compound": "Psilocybin",
                        "molecular_effect_category": "Neurotransmitter signaling",
                        "support": "Treatment altered neurotransmitter signaling.",
                    },
                    {
                        "study_doi": "10.1000/explicit-inflammation",
                        "domain": "molecular_pathway_readout",
                        "compound": "Psilocybin",
                        "molecular_effect_category": "Inflammation",
                        "specific_readout_or_marker": "TNF-alpha levels",
                        "assay_type": "ELISA",
                        "support": "Treatment reduced the inflammatory cytokine TNF-alpha.",
                    },
                    {
                        "study_doi": "10.1000/specific-readout-over-stale-canonical",
                        "domain": "molecular_pathway_readout",
                        "compound": "Psilocybin",
                        "canonical_entity": "Glutamate levels",
                        "graph_entity_label": "Glutamate levels",
                        "molecular_effect_category": "Neuroplasticity",
                        "specific_readout_or_marker": "Dendritic spinogenesis",
                        "support": "Treatment increased dendritic spinogenesis.",
                    },
                    {
                        "study_doi": "10.1000/family",
                        "domain": "molecular_target",
                        "compound": "Psilocybin",
                        "target": "serotonin receptor family",
                        "support": "The review discussed serotonin receptor family engagement.",
                    },
                    {
                        "study_doi": "10.1000/recognition-sites-family",
                        "domain": "molecular_target",
                        "compound": "Psilocybin",
                        "target": "5-HT recognition sites",
                        "assay_type": "radioligand binding",
                        "support": "The assay measured competition at serotonin recognition sites.",
                    },
                    {
                        "study_doi": "10.1000/split-targets",
                        "domain": "molecular_target",
                        "compound": "Psilocybin",
                        "target": "5-HT2A, 5-HT1A, 5-HT2C",
                        "support": "The screen reported activity at 5-HT2A, 5-HT1A, and 5-HT2C receptors.",
                    },
                    {
                        "study_doi": "10.1000/split-target-subunits",
                        "domain": "molecular_target",
                        "compound": "Psilocybin",
                        "target": "GluN1-1a/GluN2A NMDA receptor",
                        "support": "The assay reported activity at GluN1/GluN2A NMDA receptors.",
                    },
                    {
                        "study_doi": "10.1000/split-target-families",
                        "domain": "molecular_target",
                        "compound": "Psilocybin",
                        "target": "5-HT1A, 5-HT1D, and alpha 2-adrenergic sites",
                        "support": "Binding was reported at 5-HT1A, 5-HT1D, and alpha 2-adrenergic sites.",
                    },
                    {
                        "study_doi": "10.1000/serotonin-transporter-alias",
                        "domain": "molecular_target",
                        "compound": "Psilocybin",
                        "target": "human serotonin transporter",
                        "support": "The assay measured the human serotonin transporter.",
                    },
                    {
                        "study_doi": "10.1000/dopamine-family-alias",
                        "domain": "molecular_target",
                        "compound": "Psilocybin",
                        "target": "D2-like dopamine receptors",
                        "support": "The assay measured D2-like dopamine receptor binding.",
                    },
                    {
                        "study_doi": "10.1000/organic-cation-transporter",
                        "domain": "molecular_target",
                        "compound": "Psilocybin",
                        "target": "hOCT2",
                        "support": "The assay reported interaction with hOCT2.",
                    },
                    {
                        "study_doi": "10.1000/unsafe-split-targets",
                        "domain": "molecular_target",
                        "compound": "Psilocybin",
                        "target": "5-HT2A, 5-HT1A, not-a-real-target",
                        "support": "One listed target cannot be normalized.",
                    },
                    {
                        "study_doi": "10.1000/split-brain-regions",
                        "domain": "brain_system",
                        "compound": "Psilocybin",
                        "kg_entity_kind_override": "brain_region",
                        "brain_region": "Nucleus accumbens; Striatum",
                        "support": "Signal changed in nucleus accumbens and striatum.",
                    },
                    {
                        "study_doi": "10.1000/split-brain-networks",
                        "domain": "brain_system",
                        "compound": "Psilocybin",
                        "primary_graph_anchor_kind": "brain_network",
                        "brain_network": "Default Mode Network, Frontoparietal Network, Somatomotor Network",
                        "support": "The finding involved default mode, frontoparietal, and somatomotor networks.",
                    },
                    {
                        "study_doi": "10.1000/split-brain-connectivity",
                        "domain": "brain_system",
                        "compound": "Psilocybin",
                        "primary_graph_anchor_kind": "brain_network",
                        "brain_network": "insula-DMN connectivity",
                        "support": "Connectivity changed between the insula and DMN.",
                    },
                    {
                        "study_doi": "10.1000/cross-kind-brain-region",
                        "domain": "brain_system",
                        "compound": "Psilocybin",
                        "graph_entity_label": "occipital region",
                        "support": "The effect was localized to the occipital region.",
                    },
                    {
                        "study_doi": "10.1000/collapsed-brain-subregions",
                        "domain": "brain_system",
                        "compound": "Psilocybin",
                        "graph_entity_label": "occipital cortex, calcarine, cuneus, lingual gyrus",
                        "support": "The effect involved occipital cortical subregions.",
                    },
                    {
                        "study_doi": "10.1000/unsafe-brain-network-list",
                        "domain": "brain_system",
                        "compound": "Psilocybin",
                        "primary_graph_anchor_kind": "brain_network",
                        "brain_network": "Default Mode Network, unresolved network",
                        "support": "One listed network cannot be normalized.",
                    },
                    {
                        "study_doi": "10.1000/composite-family",
                        "domain": "molecular_target",
                        "compound": "Psilocybin",
                        "target": "5-HT2A/C receptor",
                        "support": "The assay did not separate 5-HT2A from 5-HT2C receptor activity.",
                    },
                    {
                        "study_doi": "10.1000/nicotinic-family",
                        "domain": "molecular_target",
                        "compound": "Psilocybin",
                        "target": "nicotinic receptors",
                        "support": "The screen reported binding at heteromeric nicotinic receptors.",
                    },
                    {
                        "study_doi": "10.1000/alpha7-direct",
                        "domain": "molecular_target",
                        "compound": "Psilocybin",
                        "target": "alpha 7-nicotinic acetylcholine receptor",
                        "support": "The assay reported alpha7 nAChR antagonism.",
                    },
                    {
                        "study_doi": "10.1000/kappa1",
                        "domain": "molecular_target",
                        "compound": "Psilocybin",
                        "target": "kappa 1-opioid receptor",
                        "support": "The assay reported kappa opioid receptor activation.",
                    },
                ],
            )

            build_tables(
                registry_path=registry_path,
                out_dir=out_dir,
                write_duckdb=False,
                graph_sources={
                    "routed_extractions": {
                        "path": routed_path,
                        "domain": "routed",
                        "dataset": "routed",
                        "default_evidence_type": "primary_evidence",
                        "skip_audit": True,
                    }
                },
            )

            edges = pd.read_parquet(out_dir / "evidence_edges.parquet")
            by_doi = {row["study_doi"]: row for row in edges.to_dict(orient="records")}
            labels_by_doi = edges.groupby("study_doi")["entity_label"].apply(set).to_dict()
            findings = pd.read_parquet(out_dir / "findings.parquet")
            finding_by_doi = {row["study_doi"]: row for row in findings.to_dict(orient="records")}
            entities = pd.read_parquet(out_dir / "entities.parquet")
            self.assertEqual(by_doi["10.1000/direct-target"]["entity_kind"], "target")
            self.assertEqual(by_doi["10.1000/direct-target"]["relation_type"], "has_mechanistic_target")
            self.assertEqual(by_doi["10.1000/target-readout"]["entity_kind"], "biomarker_readout")
            self.assertEqual(by_doi["10.1000/target-readout"]["entity_label"], "SERT protein levels")
            self.assertEqual(by_doi["10.1000/target-readout"]["relation_type"], "has_biomarker_readout")
            self.assertEqual(
                finding_by_doi["10.1000/target-readout"]["molecular_effect_label"],
                "Receptor regulation & trafficking",
            )
            self.assertEqual(by_doi["10.1000/direct-target-signaling-context"]["entity_kind"], "target")
            self.assertEqual(by_doi["10.1000/direct-target-signaling-context"]["entity_label"], "SERT (SLC6A4)")
            self.assertEqual(by_doi["10.1000/biomarker"]["entity_kind"], "biomarker_readout")
            self.assertEqual(by_doi["10.1000/biomarker"]["entity_label"], "BDNF expression")
            self.assertEqual(by_doi["10.1000/biomarker"]["relation_type"], "has_biomarker_readout")
            self.assertEqual(finding_by_doi["10.1000/biomarker"]["molecular_effect_label"], "Neuroplasticity")
            self.assertEqual(by_doi["10.1000/c-fos"]["entity_kind"], "biomarker_readout")
            self.assertEqual(by_doi["10.1000/c-fos"]["entity_label"], "c-Fos expression")
            self.assertEqual(
                finding_by_doi["10.1000/c-fos"]["molecular_effect_label"],
                "Gene expression & activity markers",
            )
            self.assertEqual(by_doi["10.1000/pathway"]["entity_kind"], "pathway_process")
            self.assertEqual(by_doi["10.1000/pathway"]["entity_label"], "mTORC1 activation")
            self.assertEqual(by_doi["10.1000/pathway"]["relation_type"], "has_mechanistic_pathway")
            self.assertEqual(
                finding_by_doi["10.1000/pathway"]["molecular_effect_label"],
                "Intracellular signal transduction",
            )
            self.assertEqual(by_doi["10.1000/pathway-phosphorylation"]["entity_kind"], "pathway_process")
            self.assertEqual(by_doi["10.1000/pathway-phosphorylation"]["entity_label"], "ERK1/2 phosphorylation")
            self.assertEqual(
                finding_by_doi["10.1000/pathway-phosphorylation"]["molecular_effect_label"],
                "Intracellular signal transduction",
            )
            self.assertEqual(
                finding_by_doi["10.1000/pathway-phosphorylation"]["graph_parent_label"],
                "Intracellular signal transduction",
            )
            self.assertEqual(by_doi["10.1000/neuroplasticity-sublabel"]["entity_kind"], "pathway_process")
            self.assertEqual(by_doi["10.1000/neuroplasticity-sublabel"]["entity_label"], "Dendritic spine density")
            self.assertEqual(finding_by_doi["10.1000/neuroplasticity-sublabel"]["molecular_effect_label"], "Neuroplasticity")
            self.assertEqual(by_doi["10.1000/dopamine-uptake"]["entity_kind"], "biomarker_readout")
            self.assertEqual(by_doi["10.1000/dopamine-uptake"]["entity_label"], "[3H]-dopamine uptake")
            self.assertEqual(
                finding_by_doi["10.1000/dopamine-uptake"]["molecular_effect_label"],
                "Neurotransmitter release, uptake & turnover",
            )
            self.assertEqual(by_doi["10.1000/perineuronal-net"]["entity_kind"], "pathway_process")
            self.assertEqual(
                by_doi["10.1000/perineuronal-net"]["entity_label"],
                "Perineuronal net intensity around PV neurons",
            )
            self.assertEqual(finding_by_doi["10.1000/perineuronal-net"]["molecular_effect_label"], "Neuroplasticity")
            self.assertEqual(finding_by_doi["10.1000/perineuronal-net"]["graph_parent_label"], "Neuroplasticity")
            self.assertEqual(by_doi["10.1000/generic-neurotransmitter-specific-readout"]["entity_kind"], "biomarker_readout")
            self.assertEqual(
                by_doi["10.1000/generic-neurotransmitter-specific-readout"]["entity_label"],
                "5-HT1A receptor expression",
            )
            self.assertEqual(
                finding_by_doi["10.1000/generic-neurotransmitter-specific-readout"]["molecular_effect_label"],
                "Receptor regulation & trafficking",
            )
            self.assertNotIn("10.1000/generic-neurotransmitter-unspecified", by_doi)
            self.assertEqual(by_doi["10.1000/explicit-inflammation"]["entity_kind"], "biomarker_readout")
            self.assertEqual(by_doi["10.1000/explicit-inflammation"]["entity_label"], "TNF-alpha levels")
            self.assertEqual(
                finding_by_doi["10.1000/explicit-inflammation"]["molecular_effect_label"],
                "Neuroinflammation & immune signaling",
            )
            self.assertEqual(
                finding_by_doi["10.1000/explicit-inflammation"]["graph_parent_label"],
                "Neuroinflammation & immune signaling",
            )
            self.assertEqual(
                by_doi["10.1000/specific-readout-over-stale-canonical"]["entity_label"],
                "Dendritic spinogenesis",
            )
            self.assertEqual(
                finding_by_doi["10.1000/specific-readout-over-stale-canonical"]["graph_parent_label"],
                "Neuroplasticity",
            )
            self.assertEqual(by_doi["10.1000/family"]["entity_kind"], "system_family")
            self.assertEqual(by_doi["10.1000/family"]["relation_type"], "has_mechanistic_system")
            self.assertEqual(by_doi["10.1000/recognition-sites-family"]["entity_kind"], "system_family")
            self.assertEqual(by_doi["10.1000/recognition-sites-family"]["entity_label"], "5-HT receptor family")
            self.assertEqual(labels_by_doi["10.1000/split-targets"], {"5-HT2A", "5-HT1A", "5-HT2C"})
            self.assertEqual(labels_by_doi["10.1000/split-target-subunits"], {"GluN1 (GRIN1)", "GluN2A (GRIN2A)"})
            self.assertEqual(
                labels_by_doi["10.1000/split-target-families"],
                {"5-HT1A", "5-HT1D", "Adrenergic receptor family"},
            )
            self.assertEqual(by_doi["10.1000/serotonin-transporter-alias"]["entity_kind"], "target")
            self.assertEqual(by_doi["10.1000/serotonin-transporter-alias"]["entity_label"], "SERT (SLC6A4)")
            self.assertEqual(by_doi["10.1000/dopamine-family-alias"]["entity_kind"], "system_family")
            self.assertEqual(by_doi["10.1000/dopamine-family-alias"]["entity_label"], "Dopamine receptor family")
            self.assertEqual(by_doi["10.1000/organic-cation-transporter"]["entity_kind"], "target")
            self.assertEqual(by_doi["10.1000/organic-cation-transporter"]["entity_label"], "OCT2 (SLC22A2)")
            self.assertEqual(labels_by_doi["10.1000/split-brain-regions"], {"Nucleus accumbens", "Striatum"})
            self.assertEqual(
                labels_by_doi["10.1000/split-brain-networks"],
                {"Default mode network", "Frontoparietal network", "Sensorimotor network"},
            )
            self.assertEqual(
                labels_by_doi["10.1000/split-brain-connectivity"],
                {"Insula", "Default mode network"},
            )
            self.assertEqual(by_doi["10.1000/cross-kind-brain-region"]["entity_kind"], "brain_region")
            self.assertEqual(by_doi["10.1000/cross-kind-brain-region"]["entity_label"], "Occipital cortex")
            self.assertEqual(
                labels_by_doi["10.1000/collapsed-brain-subregions"],
                {"Occipital cortex", "Calcarine cortex", "Cuneus", "Lingual gyrus"},
            )
            brain_subregion_parents = {
                row["entity_label"]: row["graph_parent_label"]
                for row in edges[edges["study_doi"] == "10.1000/collapsed-brain-subregions"].to_dict(orient="records")
            }
            self.assertEqual(brain_subregion_parents["Calcarine cortex"], "Occipital cortex")
            self.assertEqual(brain_subregion_parents["Cuneus"], "Occipital cortex")
            self.assertEqual(brain_subregion_parents["Lingual gyrus"], "Occipital cortex")
            perineuronal_entity = entities[entities["label"] == "Perineuronal net intensity around PV neurons"].iloc[0]
            self.assertEqual(perineuronal_entity["graph_parent_label"], "Neuroplasticity")
            self.assertIn("Neuroplasticity", set(entities["label"]))
            self.assertNotIn("10.1000/unsafe-split-targets", by_doi)
            self.assertNotIn("10.1000/unsafe-brain-network-list", by_doi)
            self.assertEqual(by_doi["10.1000/composite-family"]["entity_kind"], "system_family")
            self.assertEqual(by_doi["10.1000/composite-family"]["entity_label"], "5-HT2 receptor family")
            self.assertEqual(by_doi["10.1000/nicotinic-family"]["entity_kind"], "system_family")
            self.assertEqual(by_doi["10.1000/nicotinic-family"]["entity_label"], "Nicotinic acetylcholine receptor family")
            self.assertEqual(by_doi["10.1000/alpha7-direct"]["entity_kind"], "target")
            self.assertEqual(
                by_doi["10.1000/alpha7-direct"]["entity_label"],
                "alpha7 nicotinic acetylcholine receptor (CHRNA7)",
            )
            self.assertEqual(by_doi["10.1000/kappa1"]["entity_kind"], "target")
            self.assertEqual(by_doi["10.1000/kappa1"]["entity_label"], "kappa opioid receptor (OPRK1)")

    def test_routed_source_writes_findings_table_not_claims_table(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            registry_path = root / "registry.json"
            routed_path = root / "routed_evidence_rows.json"
            out_dir = root / "kg"
            write_json(
                registry_path,
                {
                    "compounds": [{"label": "Psilocybin", "aliases": ["psilocybin"], "ids": {}, "status": "seeded"}],
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
            write_json(
                routed_path,
                [
                    {
                        "study_doi": "10.1000/routed",
                        "study_title": "Routed finding paper",
                        "study_year": 2026,
                        "domain": "clinical_outcome",
                        "compound": "psilocybin",
                        "condition_or_population": "MDD",
                        "paper_assessment_route": "primary_evidence",
                        "source_type": "primary_study",
                        "paper_type": "primary_study",
                        "access_level": "article_text",
                    }
                ],
            )

            manifest = build_tables(
                registry_path=registry_path,
                out_dir=out_dir,
                write_duckdb=False,
                graph_sources={
                    "routed_extractions": {
                        "path": routed_path,
                        "domain": "routed",
                        "dataset": "routed",
                        "default_evidence_type": "primary_evidence",
                        "skip_audit": True,
                    }
                },
            )

            self.assertIn("findings", manifest["tables"])
            self.assertNotIn("claims", manifest["tables"])
            self.assertTrue((out_dir / "findings.parquet").exists())
            self.assertFalse((out_dir / "claims.parquet").exists())
            findings = pd.read_parquet(out_dir / "findings.parquet")
            edges = pd.read_parquet(out_dir / "evidence_edges.parquet")
            self.assertIn("finding_id", findings.columns)
            self.assertNotIn("claim_id", findings.columns)
            self.assertIn("finding_id", edges.columns)
            self.assertNotIn("claim_id", edges.columns)
            self.assertEqual(findings.iloc[0]["compound"], "Psilocybin")

    def test_routed_clinical_endpoint_source_derives_symptom_problem_edges(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            registry_path = root / "registry.json"
            routed_path = root / "routed_evidence_rows.json"
            out_dir = root / "kg"
            write_json(
                registry_path,
                {
                    "compounds": [
                        {"label": "Psilocybin", "aliases": ["psilocybin"], "ids": {}, "status": "seeded"},
                        {"label": "MDMA", "aliases": [], "ids": {}, "status": "seeded"},
                        {"label": "Ketamine", "aliases": [], "ids": {}, "status": "seeded"},
                    ],
                    "targets": [],
                    "disorders": [
                        {
                            "label": "Major depressive disorder",
                            "aliases": ["MDD"],
                            "ids": {},
                            "status": "seeded",
                        },
                        {
                            "label": "Post-traumatic stress disorder",
                            "aliases": ["PTSD"],
                            "ids": {},
                            "status": "seeded",
                        },
                        {
                            "label": "Suicidality",
                            "aliases": ["suicidal ideation"],
                            "ids": {},
                            "status": "seeded",
                        },
                    ],
                },
            )
            write_json(
                routed_path,
                [
                    {
                        "study_doi": "10.1000/depression-endpoint",
                        "domain": "clinical_outcome",
                        "compound": "psilocybin",
                        "condition_or_population": "MDD",
                        "clinical_endpoint": "depressive symptom severity",
                        "outcome_measure": "Montgomery-Asberg Depression Rating Scale (MADRS)",
                        "paper_assessment_route": "primary_evidence",
                        "source_type": "primary_study",
                        "paper_type": "primary_study",
                        "access_level": "article_text",
                    },
                    {
                        "study_doi": "10.1000/ptsd-endpoint",
                        "domain": "clinical_outcome",
                        "compound": "MDMA",
                        "condition_or_population": "PTSD",
                        "clinical_endpoint": "PTSD symptoms (nightmares, intrusive memories, avoidance)",
                        "outcome_measure": "clinical interview",
                        "paper_assessment_route": "primary_evidence",
                        "source_type": "primary_study",
                        "paper_type": "primary_study",
                        "access_level": "article_text",
                    },
                    {
                        "study_doi": "10.1000/suicidality-endpoint",
                        "domain": "clinical_outcome",
                        "compound": "Ketamine",
                        "condition_or_population": "Adults with acute suicidal ideation",
                        "clinical_endpoint": "suicidal ideation",
                        "outcome_measure": "Columbia Suicide Severity Rating Scale (C-SSRS)",
                        "paper_assessment_route": "primary_evidence",
                        "source_type": "primary_study",
                        "paper_type": "primary_study",
                        "access_level": "article_text",
                    },
                    {
                        "study_doi": "10.1000/wellbeing-endpoint",
                        "domain": "clinical_outcome",
                        "compound": "Ketamine",
                        "condition_or_population": "MDD",
                        "clinical_endpoint": "Well-being",
                        "outcome_measure": "Warwick-Edinburgh Mental Well-Being Scale",
                        "paper_assessment_route": "primary_evidence",
                        "source_type": "primary_study",
                        "paper_type": "primary_study",
                        "access_level": "article_text",
                    },
                ],
            )

            build_tables(
                registry_path=registry_path,
                out_dir=out_dir,
                write_duckdb=False,
                graph_sources={
                    "routed_extractions": {
                        "path": routed_path,
                        "domain": "routed",
                        "dataset": "routed",
                        "default_evidence_type": "primary_evidence",
                        "skip_audit": True,
                    },
                    "routed_clinical_endpoints": {
                        "path": routed_path,
                        "domain": "routed",
                        "dataset": "routed",
                        "default_evidence_type": "primary_evidence",
                        "transform": "clinical_endpoints",
                        "skip_audit": True,
                    },
                },
            )

            findings = pd.read_parquet(out_dir / "findings.parquet")
            edges = pd.read_parquet(out_dir / "evidence_edges.parquet")

        self.assertIn("finding_id", findings.columns)
        self.assertNotIn("claim_id", findings.columns)
        symptom_edges = edges[edges["entity_kind"] == "symptom_problem"]
        self.assertEqual(
            set(symptom_edges["entity_label"]),
            {"Low mood & depressive symptoms", "Trauma re-experiencing & avoidance"},
        )
        self.assertEqual(set(symptom_edges["relation_type"]), {"studied_for_symptom"})
        self.assertEqual(set(symptom_edges["source_name"]), {"routed_clinical_endpoints"})
        self.assertNotIn("Well-being", set(symptom_edges["entity_label"]))
        condition_edges = edges[edges["entity_kind"] == "condition_indication"]
        self.assertEqual(
            set(condition_edges["entity_label"]),
            {"Major depressive disorder", "Post-traumatic stress disorder", "Suicidality"},
        )
        scale_edges = edges[edges["entity_kind"] == "outcome_scale"]
        self.assertTrue(scale_edges.empty)
        madrs_findings = findings[findings["outcome_measure"].str.contains("Montgomery", na=False)]
        self.assertEqual(set(madrs_findings["outcome_measure_normalized"]), {"MADRS"})

    def test_disease_like_challenge_effects_are_not_condition_or_clinical_symptom_edges(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            registry_path = root / "registry.json"
            routed_path = root / "routed_evidence_rows.json"
            out_dir = root / "kg"
            write_json(
                registry_path,
                {
                    "compounds": [
                        {"label": "Ketamine", "aliases": [], "ids": {}, "status": "seeded"},
                        {"label": "Psilocybin", "aliases": [], "ids": {}, "status": "seeded"},
                    ],
                    "targets": [],
                    "disorders": [
                        {"label": "Schizophrenia", "aliases": ["schizophrenia"], "ids": {}, "status": "seeded"},
                        {"label": "Major depressive disorder", "aliases": ["MDD"], "ids": {}, "status": "seeded"},
                    ],
                },
            )
            write_json(
                routed_path,
                [
                    {
                        "study_doi": "10.1000/ketamine-challenge",
                        "study_title": "Effects of nicotine on the neurophysiological and behavioral effects of ketamine in humans",
                        "domain": "clinical_outcome",
                        "compound": "Ketamine",
                        "condition_or_indication": "Schizophrenia-like symptoms",
                        "condition_or_population": "Healthy human volunteers",
                        "clinical_endpoint": "Schizophrenia-like behavioral symptoms",
                        "outcome_measure": "Positive and Negative Syndrome Scale (PANSS)",
                        "population": "Healthy human volunteers",
                        "population_or_subgroup": "Healthy human volunteers",
                        "population_model_category": "healthy_volunteers",
                        "finding_summary": "Ketamine induced significant transient schizophrenia-like behavioral effects.",
                        "support": "Ketamine induced significant transient schizophrenia-like behavioral effects.",
                        "paper_assessment_route": "primary_evidence",
                        "source_type": "primary_study",
                        "paper_type": "primary_study",
                        "access_level": "article_text",
                    },
                    {
                        "study_doi": "10.1000/mdd",
                        "domain": "clinical_outcome",
                        "compound": "Psilocybin",
                        "condition_or_indication": "Major depressive disorder",
                        "condition_or_population": "Adults with MDD",
                        "clinical_endpoint": "depressive symptom severity",
                        "outcome_measure": "MADRS",
                        "population": "Adults with MDD",
                        "population_model_category": "clinical_population",
                        "paper_assessment_route": "primary_evidence",
                        "source_type": "primary_study",
                        "paper_type": "primary_study",
                        "access_level": "article_text",
                    },
                ],
            )

            build_tables(
                registry_path=registry_path,
                out_dir=out_dir,
                write_duckdb=False,
                graph_sources={
                    "routed_extractions": {
                        "path": routed_path,
                        "domain": "routed",
                        "dataset": "routed",
                        "default_evidence_type": "primary_evidence",
                        "skip_audit": True,
                    },
                    "routed_clinical_endpoints": {
                        "path": routed_path,
                        "domain": "routed",
                        "dataset": "routed",
                        "default_evidence_type": "primary_evidence",
                        "transform": "clinical_endpoints",
                        "skip_audit": True,
                    },
                },
            )

            edges = pd.read_parquet(out_dir / "evidence_edges.parquet")

        self.assertIn("Major depressive disorder", set(edges["entity_label"]))
        self.assertNotIn("Schizophrenia", set(edges["entity_label"]))
        self.assertNotIn("Psychotic-like symptoms", set(edges["entity_label"]))
        self.assertNotIn("PANSS", set(edges["entity_label"]))

    def test_condition_text_splits_distinct_conditions_and_prefers_specific_labels(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            registry_path = root / "registry.json"
            routed_path = root / "routed_evidence_rows.json"
            out_dir = root / "kg"
            write_json(
                registry_path,
                {
                    "compounds": [{"label": "Ketamine", "aliases": [], "ids": {}, "status": "seeded"}],
                    "targets": [],
                    "disorders": [
                        {"label": "Major depressive disorder", "aliases": ["MDD"], "ids": {}, "status": "seeded"},
                        {"label": "Suicidality", "aliases": ["suicidal ideation"], "ids": {}, "status": "seeded"},
                        {"label": "Complex regional pain syndrome", "aliases": ["CRPS"], "ids": {}, "status": "seeded"},
                        {
                            "label": "Pain conditions",
                            "aliases": ["pain"],
                            "ids": {},
                            "status": "broad_category_needs_external_id_lookup",
                        },
                    ],
                },
            )
            write_json(
                routed_path,
                [
                    {
                        "study_doi": "10.1000/mdd-suicidality",
                        "domain": "clinical_outcome",
                        "compound": "Ketamine",
                        "condition_or_population": "Major depressive disorder with suicidal ideation",
                        "clinical_endpoint": "clinical response",
                        "outcome_measure": "clinical interview",
                        "paper_assessment_route": "primary_evidence",
                        "source_type": "primary_study",
                        "paper_type": "primary_study",
                        "access_level": "article_text",
                    },
                    {
                        "study_doi": "10.1000/crps",
                        "domain": "clinical_outcome",
                        "compound": "Ketamine",
                        "condition_or_population": "Complex regional pain syndrome (CRPS) I or II",
                        "clinical_endpoint": "clinical response",
                        "outcome_measure": "clinical interview",
                        "paper_assessment_route": "primary_evidence",
                        "source_type": "primary_study",
                        "paper_type": "primary_study",
                        "access_level": "article_text",
                    },
                ],
            )

            build_tables(
                registry_path=registry_path,
                out_dir=out_dir,
                write_duckdb=False,
                graph_sources={
                    "routed_extractions": {
                        "path": routed_path,
                        "domain": "routed",
                        "dataset": "routed",
                        "default_evidence_type": "primary_evidence",
                        "skip_audit": True,
                    },
                },
            )

            edges = pd.read_parquet(out_dir / "evidence_edges.parquet")

        condition_edges = edges[edges["entity_kind"] == "condition_indication"]
        self.assertEqual(
            set(condition_edges["entity_label"]),
            {"Major depressive disorder", "Suicidality", "Complex regional pain syndrome"},
        )
        self.assertNotIn("Pain conditions", set(condition_edges["entity_label"]))

    def test_clinical_review_condition_aliases_and_vas_not_pain(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            registry_path = root / "registry.json"
            routed_path = root / "routed_evidence_rows.json"
            out_dir = root / "kg"
            write_json(
                registry_path,
                {
                    "compounds": [
                        {"label": "Psilocybin", "aliases": [], "ids": {}, "status": "seeded"},
                        {"label": "LSD", "aliases": [], "ids": {}, "status": "seeded"},
                        {"label": "Ayahuasca", "aliases": [], "ids": {}, "status": "seeded"},
                    ],
                    "targets": [],
                    "disorders": [
                        {"label": "Obsessive-compulsive disorder", "aliases": ["OCD"], "ids": {}, "status": "seeded"},
                        {
                            "label": "Distress associated with life-threatening disease",
                            "aliases": [
                                "psychological distress in terminal illness",
                                "anxiety associated with life-threatening diseases",
                                "advanced-stage cancer with anxiety/depression",
                                "life-threatening diseases with anxiety",
                            ],
                            "ids": {},
                            "status": "seeded",
                        },
                        {
                            "label": "Tobacco use disorder",
                            "aliases": ["tobacco dependence"],
                            "ids": {},
                            "status": "seeded",
                        },
                        {
                            "label": "Alcohol use disorder",
                            "aliases": ["alcohol dependence"],
                            "ids": {},
                            "status": "seeded",
                        },
                        {"label": "Major depressive disorder", "aliases": ["MDD"], "ids": {}, "status": "seeded"},
                    ],
                },
            )
            write_json(
                routed_path,
                [
                    {
                        "study_doi": "10.1177/2045125316638008",
                        "domain": "clinical_outcome",
                        "compound": "Psilocybin",
                        "kg_entity_kind_override": "condition_indication",
                        "graph_entity_label": "obsessive-compulsive disorder",
                        "condition_or_population": "obsessive-compulsive disorder (OCD)",
                        "clinical_endpoint": "OCD symptom severity",
                        "outcome_measure": "YBOCS; VAS",
                        "source_type": "systematic_review",
                        "paper_type": "systematic_review",
                        "access_level": "article_text",
                    },
                    {
                        "study_doi": "10.1177/2045125316638008",
                        "domain": "clinical_outcome",
                        "compound": "Psilocybin",
                        "kg_entity_kind_override": "condition_indication",
                        "graph_entity_label": "psychological distress in terminal illness",
                        "condition_or_population": "advanced-stage cancer with anxiety/depression",
                        "clinical_endpoint": "anxiety and depression",
                        "outcome_measure": "STAI; BDI; POMS",
                        "source_type": "systematic_review",
                        "paper_type": "systematic_review",
                        "access_level": "article_text",
                    },
                    {
                        "study_doi": "10.1177/2045125316638008",
                        "domain": "clinical_outcome",
                        "compound": "Psilocybin",
                        "kg_entity_kind_override": "condition_indication",
                        "graph_entity_label": "tobacco dependence",
                        "condition_or_population": "tobacco dependence",
                        "clinical_endpoint": "smoking abstinence",
                        "outcome_measure": "TLFB",
                        "source_type": "systematic_review",
                        "paper_type": "systematic_review",
                        "access_level": "article_text",
                    },
                    {
                        "study_doi": "10.1177/2045125316638008",
                        "domain": "clinical_outcome",
                        "compound": "LSD",
                        "kg_entity_kind_override": "condition_indication",
                        "graph_entity_label": "anxiety associated with life-threatening diseases",
                        "condition_or_population": "life-threatening diseases with anxiety",
                        "clinical_endpoint": "anxiety",
                        "outcome_measure": "STAI; HADS",
                        "source_type": "systematic_review",
                        "paper_type": "systematic_review",
                        "access_level": "article_text",
                    },
                    {
                        "study_doi": "10.1177/2045125316638008",
                        "domain": "clinical_outcome",
                        "compound": "Ayahuasca",
                        "kg_entity_kind_override": "condition_indication",
                        "graph_entity_label": "major depressive disorder",
                        "condition_or_population": "major depressive disorder (MDD)",
                        "clinical_endpoint": "depressive symptoms",
                        "outcome_measure": "HAM-D; MADRS; BPRS",
                        "source_type": "systematic_review",
                        "paper_type": "systematic_review",
                        "access_level": "article_text",
                    },
                ],
            )

            build_tables(
                registry_path=registry_path,
                out_dir=out_dir,
                write_duckdb=False,
                graph_sources={
                    "routed_extractions": {
                        "path": routed_path,
                        "domain": "routed",
                        "dataset": "routed",
                        "default_evidence_type": "secondary_literature",
                        "skip_audit": True,
                    },
                    "routed_clinical_endpoints": {
                        "path": routed_path,
                        "domain": "routed",
                        "dataset": "routed",
                        "default_evidence_type": "secondary_literature",
                        "transform": "clinical_endpoints",
                        "skip_audit": True,
                    },
                },
            )

            edges = pd.read_parquet(out_dir / "evidence_edges.parquet")
            audit = pd.read_parquet(out_dir / "normalization_audit.parquet")

        condition_edges = edges[edges["entity_kind"] == "condition_indication"]
        self.assertEqual(
            set(condition_edges["entity_label"]),
            {
                "Obsessive-compulsive disorder",
                "Distress associated with life-threatening disease",
                "Tobacco use disorder",
                "Major depressive disorder",
            },
        )
        self.assertNotIn("Pain", set(edges["entity_label"]))
        self.assertNotIn("Psychotic-like symptoms", set(edges["entity_label"]))
        if not audit.empty:
            self.assertNotIn("entity_unmapped", set(audit["normalization_status"]))

    def test_broad_condition_terms_are_not_graphable_but_specific_labels_win(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            registry_path = root / "registry.json"
            routed_path = root / "routed_evidence_rows.json"
            out_dir = root / "kg"
            write_json(
                registry_path,
                {
                    "compounds": [{"label": "Ketamine", "aliases": [], "ids": {}, "status": "seeded"}],
                    "targets": [],
                    "disorders": [
                        {
                            "label": "Depressive disorders",
                            "aliases": ["depression", "depressive symptoms"],
                            "ids": {},
                            "status": "broad_category_needs_external_id_lookup",
                        },
                        {
                            "label": "Major depressive disorder",
                            "aliases": ["MDD", "major depression"],
                            "ids": {},
                            "status": "seeded",
                        },
                        {
                            "label": "Mood disorders",
                            "aliases": ["mood disorders"],
                            "ids": {},
                            "status": "broad_category_needs_external_id_lookup",
                        },
                        {
                            "label": "Treatment-resistant depression",
                            "aliases": ["TRD", "treatment-resistant depression"],
                            "ids": {},
                            "status": "seeded",
                        },
                        {
                            "label": "Bipolar depression",
                            "aliases": ["treatment-resistant bipolar I/II depression"],
                            "ids": {},
                            "status": "seeded",
                        },
                        {
                            "label": "Anxiety disorders",
                            "aliases": ["anxiety", "anxiety symptoms", "anxiety disorder"],
                            "ids": {},
                            "status": "broad_category_needs_external_id_lookup",
                        },
                        {
                            "label": "Generalized anxiety disorder",
                            "aliases": ["GAD", "generalized anxiety"],
                            "ids": {},
                            "status": "seeded",
                        },
                        {
                            "label": "Distress associated with life-threatening disease",
                            "aliases": ["anxiety related to life-threatening illnesses"],
                            "ids": {},
                            "status": "seeded",
                        },
                        {
                            "label": "Pain conditions",
                            "aliases": ["pain"],
                            "ids": {},
                            "status": "broad_category_needs_external_id_lookup",
                        },
                        {
                            "label": "Chronic pain",
                            "aliases": [],
                            "ids": {},
                            "status": "seeded",
                        },
                        {
                            "label": "Neuropathic pain",
                            "aliases": ["chronic neuropathic orofacial pain"],
                            "ids": {},
                            "status": "seeded",
                        },
                    ],
                },
            )
            rows = []
            for doi_suffix, condition, context in (
                ("broad-depression", "depression", {}),
                ("broad-depression-context-mdd", "depression", {"clinical_context_condition": "MDD"}),
                (
                    "broad-depression-ambiguous",
                    "depression",
                    {"finding_summary": "The review covers MDD and bipolar depression."},
                ),
                (
                    "broad-depression-wrong-family",
                    "depression",
                    {"clinical_context_condition": "generalized anxiety disorder"},
                ),
                ("mdd", "major depressive disorder with depression", {}),
                ("mood-parenthetical-mdd", "mood disorders (predominantly major depressive disorder)", {}),
                ("trd", "treatment-resistant depression", {}),
                ("bipolar-depression", "treatment-resistant bipolar I/II depression", {}),
                ("broad-anxiety", "anxiety", {}),
                ("gad", "generalized anxiety disorder with anxiety symptoms", {}),
                ("life-threatening-anxiety", "anxiety related to life-threatening illnesses", {}),
                ("broad-pain", "pain", {}),
                ("chronic-pain", "chronic pain with pain interference", {}),
                ("neuropathic-pain", "chronic neuropathic orofacial pain", {}),
            ):
                rows.append(
                    {
                        "study_doi": f"10.1000/{doi_suffix}",
                        "domain": "clinical_outcome",
                        "compound": "Ketamine",
                        "condition_or_population": condition,
                        "clinical_endpoint": "clinical response",
                        "outcome_measure": "clinical interview",
                        "paper_assessment_route": "primary_evidence",
                        "source_type": "primary_study",
                        "paper_type": "primary_study",
                        "access_level": "article_text",
                        **context,
                    }
                )
            write_json(routed_path, rows)

            build_tables(
                registry_path=registry_path,
                out_dir=out_dir,
                write_duckdb=False,
                graph_sources={
                    "routed_extractions": {
                        "path": routed_path,
                        "domain": "routed",
                        "dataset": "routed",
                        "default_evidence_type": "primary_evidence",
                        "skip_audit": True,
                    },
                },
            )

            edges = pd.read_parquet(out_dir / "evidence_edges.parquet")
            audit = pd.read_parquet(out_dir / "normalization_audit.parquet")

        condition_labels = set(edges[edges["entity_kind"] == "condition_indication"]["entity_label"])
        self.assertEqual(
            condition_labels,
            {
                "Major depressive disorder",
                "Treatment-resistant depression",
                "Bipolar depression",
                "Generalized anxiety disorder",
                "Distress associated with life-threatening disease",
                "Chronic pain",
                "Neuropathic pain",
            },
        )
        self.assertFalse(
            {
                "Depression",
                "Anxiety",
                "Pain",
                "Depressive disorders",
                "Anxiety disorders",
                "Pain conditions",
                "Mood disorders",
            }
            & condition_labels
        )
        self.assertEqual(
            set(audit["normalization_status"]),
            {"condition_broad_placeholder_not_graphable"},
        )
        self.assertIn("10.1000/broad-depression-context-mdd", set(edges["study_doi"]))
        self.assertNotIn("10.1000/broad-depression-ambiguous", set(edges["study_doi"]))
        self.assertNotIn("10.1000/broad-depression-wrong-family", set(edges["study_doi"]))

    def test_condition_registry_keeps_bipolar_subtypes_and_removes_contextual_duplicates(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            routed_path = root / "routed_evidence_rows.json"
            out_dir = root / "kg"
            write_json(
                routed_path,
                [
                    {
                        "study_doi": "10.1000/bipolar-ii",
                        "domain": "clinical_outcome",
                        "compound": "Ketamine",
                        "condition_or_indication": "Bipolar II disorder",
                    },
                    {
                        "study_doi": "10.1000/nicotine",
                        "domain": "clinical_outcome",
                        "compound": "Psilocybin",
                        "condition_or_indication": "Nicotine dependence",
                    },
                    {
                        "study_doi": "10.1000/family-history",
                        "domain": "clinical_outcome",
                        "compound": "Psilocybin",
                        "condition_or_indication": "Family history of bipolar disorder",
                    },
                ],
            )

            build_tables(
                out_dir=out_dir,
                write_duckdb=False,
                graph_sources={
                    "routed_extractions": {
                        "path": routed_path,
                        "domain": "routed",
                        "dataset": "routed",
                        "default_evidence_type": "primary_evidence",
                        "skip_audit": True,
                    },
                },
            )

            edges = pd.read_parquet(out_dir / "evidence_edges.parquet")
            audit = pd.read_parquet(out_dir / "normalization_audit.parquet")

        condition_labels = set(edges[edges["entity_kind"] == "condition_indication"]["entity_label"])
        self.assertEqual(condition_labels, {"Bipolar II disorder", "Tobacco use disorder"})
        self.assertNotIn("Bipolar disorder", condition_labels)
        self.assertNotIn("Nicotine dependence", condition_labels)
        self.assertIn("condition_context_not_graphable", set(audit["normalization_status"]))

    def test_duckdb_writer_skips_zero_column_auxiliary_tables(self) -> None:
        try:
            import duckdb  # noqa: F401
        except ModuleNotFoundError:
            self.skipTest("duckdb is not installed")

        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir)
            pd.DataFrame([{"claim_id": "claim:1"}]).to_parquet(out_dir / "claims.parquet", index=False)
            pd.DataFrame().to_parquet(out_dir / "normalization_audit.parquet", index=False)

            status = write_duckdb_database(out_dir, ["claims", "normalization_audit"])

        self.assertEqual(status["status"], "ok")
        self.assertEqual(status["skipped_empty_tables"], ["normalization_audit"])

    def test_builds_unified_parquet_tables_with_entity_kinds(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            registry_path = root / "registry.json"
            write_json(
                registry_path,
                {
                    "compounds": [
                        {"label": "Psilocybin", "aliases": [], "ids": {"pubchem_cid": "10624"}, "status": "seeded"},
                        {"label": "Ketamine", "aliases": [], "ids": {}, "status": "seeded"},
                        {"label": "MDMA", "aliases": ["3,4-methylenedioxymethamphetamine"], "ids": {}, "status": "seeded"},
                        {"label": "DMT", "aliases": ["N,N-dimethyltryptamine"], "ids": {}, "status": "seeded"},
                    ],
                    "targets": [
                        {
                            "label": "5-HT2A",
                            "aliases": ["5-HT2A receptor"],
                            "ids": {"gene_symbol": "HTR2A"},
                            "status": "needs_external_id_lookup",
                        },
                        {
                            "label": "Neuroplasticity",
                            "aliases": [],
                            "ids": {},
                            "status": "pathway_or_process",
                        },
                        {
                            "label": "MAO-A",
                            "aliases": ["monoamine oxidase A"],
                            "ids": {},
                            "status": "needs_external_id_lookup",
                        },
                    ],
                    "disorders": [
                        {
                            "label": "Depressive disorders",
                            "aliases": ["Depression"],
                            "ids": {},
                            "status": "broad_category_needs_external_id_lookup",
                        },
                        {
                            "label": "Major depressive disorder",
                            "aliases": [],
                            "ids": {},
                            "status": "needs_external_id_lookup",
                        },
                        {
                            "label": "Post-traumatic stress disorder",
                            "aliases": ["PTSD"],
                            "ids": {},
                            "status": "needs_external_id_lookup",
                        },
                    ],
                },
            )
            mechanistic_path = root / "mechanistic.json"
            clinical_path = root / "clinical.json"
            brain_path = root / "brain.json"
            pk_path = root / "pk.json"
            public_health_path = root / "public_health.json"
            clinical_endpoint_path = root / "clinical_endpoint_raw.json"
            audit_path = root / "audit.json"
            endpoint_audit_path = root / "endpoint_audit.json"
            write_json(
                mechanistic_path,
                [
                    {
                        "study_doi": "https://doi.org/10.1000/MECH",
                        "study_title": "Mechanistic paper",
                        "study_year": 2024,
                        "compound": "psilocybin",
                        "target": "5-HT2A receptor",
                        "entity_role": "molecular_target",
                        "paper_assessment_route": "primary_evidence",
                        "source_type": "primary_study",
                        "paper_type": "primary_results",
                        "access_level": "full_text_seen",
                        "result_direction": "positive",
                    },
                    {
                        "study_doi": "10.1000/pathway",
                        "study_title": "Pathway paper",
                        "study_year": 2025,
                        "compound": "Ketamine",
                        "target": "Neuroplasticity",
                        "entity_role": "pathway_or_process",
                        "paper_assessment_route": "primary_evidence",
                        "source_type": "primary_study",
                        "paper_type": "primary_results",
                    },
                ],
            )
            write_json(
                clinical_path,
                [
                    {
                        "study_doi": "10.1000/clin",
                        "study_title": "Clinical paper",
                        "study_year": 2023,
                        "compound": "Psilocybin",
                        "disorder": "Major depressive disorder",
                        "entity_role": "therapeutic_indication",
                        "paper_assessment_route": "secondary_literature",
                        "source_type": "review",
                        "paper_type": "review",
                        "access_level": "secondary_summary",
                    },
                    {
                        "study_doi": "10.1000/symptom",
                        "study_title": "Symptom paper",
                        "study_year": 2023,
                        "compound": "Psilocybin",
                        "disorder": "Depression",
                        "entity_role": "symptom_or_problem",
                        "paper_assessment_route": "primary_evidence",
                        "source_type": "primary_study",
                        "paper_type": "primary_results",
                        "access_level": "full_text_seen",
                    },
                    {
                        "study_doi": "10.1000/outcome-symptom",
                        "study_title": "Outcome symptom paper",
                        "study_year": 2023,
                        "compound": "Ketamine",
                        "disorder": "Depression",
                        "entity_role": "outcome_measure",
                        "paper_assessment_route": "primary_evidence",
                        "source_type": "primary_study",
                        "paper_type": "primary_results",
                        "access_level": "full_text_seen",
                    },
                    {
                        "study_doi": "10.1000/ptsd-symptoms",
                        "study_title": "PTSD symptom outcome paper",
                        "study_year": 2023,
                        "compound": "Ketamine",
                        "disorder": "PTSD",
                        "entity_role": "symptom_or_problem",
                        "paper_assessment_route": "primary_evidence",
                        "source_type": "primary_study",
                        "paper_type": "primary_results",
                        "access_level": "full_text_seen",
                    },
                    {
                        "study_doi": "10.1000/combo-compound",
                        "study_title": "Combo compound paper",
                        "study_year": 2023,
                        "compound": "Psilocybin and MDMA",
                        "disorder": "Major depressive disorder",
                        "entity_role": "therapeutic_indication",
                        "paper_assessment_route": "primary_evidence",
                        "source_type": "primary_study",
                        "paper_type": "primary_results",
                        "access_level": "full_text_seen",
                    },
                    {
                        "study_doi": "10.1000/reference-compound",
                        "study_title": "Reference compound paper",
                        "study_year": 2023,
                        "compound": "Ketanserin",
                        "disorder": "Major depressive disorder",
                        "entity_role": "therapeutic_indication",
                        "paper_assessment_route": "primary_evidence",
                        "source_type": "primary_study",
                        "paper_type": "primary_results",
                        "access_level": "full_text_seen",
                    },
                ],
            )
            write_json(
                brain_path,
                [
                    {
                        "study_doi": "10.1000/brain",
                        "study_title": "Brain network paper",
                        "study_year": 2025,
                        "compound_or_exposure": "Psilocybin",
                        "primary_graph_anchor_kind": "brain_network",
                        "brain_network": "DMN",
                        "readout_or_measure": "functional connectivity",
                        "paper_assessment_route": "primary_evidence",
                        "source_type": "primary_study",
                        "paper_type": "primary_results",
                        "access_level": "full_text_seen",
                    }
                ],
            )
            write_json(
                pk_path,
                [
                    {
                        "study_doi": "10.1000/pk",
                        "study_title": "Exposure target paper",
                        "study_year": 2025,
                        "compound_or_analyte": "DMT",
                        "primary_graph_anchor_kind": "target",
                        "metabolic_or_transport_target": "MAO-A",
                        "pk_or_exposure_parameter": "metabolism",
                        "paper_assessment_route": "primary_evidence",
                        "source_type": "primary_study",
                        "paper_type": "primary_results",
                        "access_level": "full_text_seen",
                    }
                ],
            )
            write_json(
                public_health_path,
                [
                    {
                        "study_doi": "10.1000/public-health",
                        "study_title": "Public health paper",
                        "study_year": 2025,
                        "exposure_or_intervention": "Psilocybin",
                        "public_health_measure": "ethnoracial inclusion",
                        "public_health_topic_category": "access and equity",
                        "paper_assessment_route": "primary_evidence",
                        "source_type": "primary_study",
                        "paper_type": "primary_results",
                        "access_level": "full_text_seen",
                    }
                ],
            )
            write_json(
                clinical_endpoint_path,
                [
                    {
                        "study_doi": "10.1000/function",
                        "study_title": "Functional endpoint paper",
                        "study_year": 2022,
                        "compound": "psilocybin",
                        "disorder": "not_applicable",
                        "raw_entity_label": "well-being",
                        "entity_role": "functional_outcome",
                        "outcome_domain": "well-being",
                        "outcome_measure": "Warwick-Edinburgh Mental Well-Being Scale",
                        "outcome_measure_normalized": "WEMWBS",
                        "paper_assessment_route": "primary_evidence",
                        "source_type": "primary_study",
                        "paper_type": "primary_results",
                        "access_level": "full_text_seen",
                    },
                    {
                        "study_doi": "10.1000/noisy-function",
                        "study_title": "Noisy endpoint paper",
                        "study_year": 2022,
                        "compound": "psilocybin",
                        "disorder": "not_applicable",
                        "raw_entity_label": "patient satisfaction",
                        "entity_role": "functional_outcome",
                        "outcome_domain": "patient experience",
                        "outcome_measure": "Client Satisfaction Questionnaire",
                        "outcome_measure_normalized": "",
                        "paper_assessment_route": "primary_evidence",
                        "source_type": "primary_study",
                        "paper_type": "primary_results",
                        "access_level": "full_text_seen",
                    }
                ],
            )
            write_json(audit_path, [{"normalization_status": "normalized", "compound": "Psilocybin", "target": "5-HT2A"}])
            write_json(
                endpoint_audit_path,
                [
                    {
                        "normalization_status": "not_graph_candidate",
                        "compound": "psilocybin",
                        "canonical_compound": "Psilocybin",
                        "entity_role": "functional_outcome",
                    },
                    {
                        "normalization_status": "not_graph_candidate",
                        "compound": "psilocybin",
                        "canonical_compound": "Psilocybin",
                        "entity_role": "functional_outcome",
                    }
                ],
            )

            out_dir = root / "kg"
            manifest = build_tables(
                registry_path=registry_path,
                out_dir=out_dir,
                write_duckdb=False,
                graph_sources={
                    "mechanistic_primary": {
                        "path": mechanistic_path,
                        "audit_path": audit_path,
                        "domain": "mechanistic",
                        "dataset": "mechanistic",
                        "default_evidence_type": "primary_evidence",
                    },
                    "clinical_secondary": {
                        "path": clinical_path,
                        "audit_path": audit_path,
                        "domain": "clinical",
                        "dataset": "disorder",
                        "default_evidence_type": "secondary_literature",
                    },
                    "brain_primary": {
                        "path": brain_path,
                        "audit_path": audit_path,
                        "domain": "brain_system",
                        "dataset": "brain_system",
                        "default_evidence_type": "primary_evidence",
                    },
                    "pk_primary": {
                        "path": pk_path,
                        "audit_path": audit_path,
                        "domain": "pharmacokinetics_exposure",
                        "dataset": "pharmacokinetics_exposure",
                        "default_evidence_type": "primary_evidence",
                    },
                    "public_health_primary": {
                        "path": public_health_path,
                        "audit_path": audit_path,
                        "domain": "real_world_public_health",
                        "dataset": "real_world_public_health",
                        "default_evidence_type": "primary_evidence",
                    },
                    "clinical_primary_endpoints": {
                        "path": clinical_endpoint_path,
                        "audit_path": endpoint_audit_path,
                        "domain": "clinical",
                        "dataset": "disorder",
                        "default_evidence_type": "primary_evidence",
                        "transform": "clinical_endpoints",
                        "skip_audit": True,
                    },
                },
            )

            self.assertEqual(manifest["tables"]["evidence_edges"]["rows"], 10)
            edges = pd.read_parquet(out_dir / "evidence_edges.parquet")
            self.assertEqual(
                set(edges["domain"]),
                {"mechanistic", "clinical", "brain_system", "pharmacokinetics_exposure", "real_world_public_health"},
            )
            self.assertEqual(
                set(edges["entity_kind"]),
                {
                    "target",
                    "pathway_process",
                    "condition_indication",
                    "symptom_problem",
                    "brain_network",
                    "public_health_measure",
                },
            )
            self.assertIn("secondary_literature", set(edges["evidence_type"]))
            self.assertNotIn("functional_outcome", set(edges["entity_kind"]))
            self.assertNotIn("outcome_scale", set(edges["entity_kind"]))
            self.assertNotIn("Wellbeing", set(edges["entity_label"]))
            self.assertNotIn("Patient experience", set(edges["entity_label"]))
            self.assertIn("Psilocybin", set(edges["compound"]))
            combo_edge = edges[edges["study_doi"] == "10.1000/combo-compound"].iloc[0]
            self.assertEqual(combo_edge["graph_subject_kind"], "atomic_compound")
            self.assertEqual(
                [item["label"] for item in json.loads(combo_edge["graph_overview_subjects_json"])],
                ["Psilocybin", "MDMA"],
            )
            self.assertNotIn("Ketanserin", set(edges["compound"]))
            condition_edges = edges[edges["entity_kind"] == "condition_indication"]
            self.assertEqual(set(condition_edges["entity_label"]), {"Major depressive disorder", "Post-traumatic stress disorder"})
            symptom_edges = edges[edges["entity_kind"] == "symptom_problem"]
            self.assertEqual(set(symptom_edges["entity_label"]), {"Low mood & depressive symptoms"})
            self.assertEqual(len(symptom_edges), 2)
            target_edges = edges[edges["entity_kind"] == "target"]
            self.assertIn("5-HT2A", set(target_edges["entity_label"]))
            self.assertNotIn("5-HT2A receptor", set(target_edges["entity_label"]))
            brain_edge = edges[edges["domain"] == "brain_system"].iloc[0]
            self.assertEqual(brain_edge["entity_kind"], "brain_network")
            self.assertEqual(brain_edge["entity_label"], "Default mode network")
            self.assertEqual(brain_edge["relation_type"], "has_brain_system_effect")
            pk_edge = edges[edges["domain"] == "pharmacokinetics_exposure"].iloc[0]
            self.assertEqual(pk_edge["entity_kind"], "target")
            self.assertEqual(pk_edge["entity_label"], "MAO-A")
            self.assertEqual(pk_edge["relation_type"], "metabolized_by")
            public_health_edge = edges[edges["domain"] == "real_world_public_health"].iloc[0]
            self.assertEqual(public_health_edge["entity_kind"], "public_health_measure")
            self.assertEqual(public_health_edge["entity_label"], "Access & equity")
            self.assertEqual(public_health_edge["relation_type"], "has_public_health_evidence")
            audit = pd.read_parquet(out_dir / "normalization_audit.parquet")
            self.assertNotIn("compound_combo_not_graphable", set(audit["normalization_status"]))
            self.assertIn("compound_reference_not_graphable", set(audit["normalization_status"]))

            papers = pd.read_parquet(out_dir / "papers.parquet")
            self.assertEqual(
                set(papers["paper_id"]),
                {
                    "paper:10.1000/mech",
                    "paper:10.1000/pathway",
                    "paper:10.1000/brain",
                    "paper:10.1000/pk",
                    "paper:10.1000/public-health",
                    "paper:10.1000/clin",
                    "paper:10.1000/symptom",
                    "paper:10.1000/outcome-symptom",
                    "paper:10.1000/ptsd-symptoms",
                    "paper:10.1000/combo-compound",
                },
            )

            entities = pd.read_parquet(out_dir / "entities.parquet")
            neuroplasticity = entities[entities["label"] == "Neuroplasticity"].iloc[0]
            self.assertEqual(neuroplasticity["entity_kind"], "pathway_process")

            self.assertTrue((out_dir / "claims.parquet").exists())
            self.assertTrue((out_dir / "normalization_audit.parquet").exists())
            self.assertEqual(json.loads((out_dir / "manifest.json").read_text())["duckdb"]["status"], "skipped")

    def test_non_atomic_exposure_is_preserved_and_atomic_constituent_is_not_projected(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            registry_path = root / "registry.json"
            source_path = root / "routed.json"
            out_dir = root / "kg"
            write_json(
                registry_path,
                {
                    "compounds": [{"label": "Ketamine", "aliases": [], "ids": {}, "status": "seeded"}],
                    "targets": [],
                    "disorders": [
                        {
                            "label": "Post-traumatic stress disorder",
                            "aliases": ["PTSD"],
                            "ids": {},
                            "status": "seeded",
                        }
                    ],
                },
            )
            exposure = "Use of methamphetamine, mephedrone, GHB/GBL, and/or ketamine in a sexual setting"
            write_json(
                source_path,
                [
                    {
                        "study_doi": "10.3389/fpsyt.2020.542301",
                        "domain": "clinical_outcome",
                        "compound": exposure,
                        "atomic_compound_candidate": "Ketamine (as part of chemsex substances)",
                        "graph_subject_label": exposure,
                        "graph_subject_kind": "exposure_context",
                        "condition_or_indication": "PTSD",
                        "clinical_endpoint": "PTSD symptoms",
                        "study_design_category": "observational",
                        "evidence_design": "observational",
                        "result_direction": "negative",
                        "result_direction_normalized": "negative",
                        "support": "The chemsex group reported traumatic events more often.",
                        "evidence_location": "Results, Trauma",
                        "source_item_type": "primary_item",
                        "paper_assessment_route": "primary_evidence",
                    }
                ],
            )

            manifest = build_tables(
                registry_path=registry_path,
                out_dir=out_dir,
                write_duckdb=False,
                graph_sources={
                    "routed_extractions": {
                        "path": source_path,
                        "domain": "routed",
                        "dataset": "routed",
                        "default_evidence_type": "primary_evidence",
                        "skip_audit": True,
                    }
                },
            )

            edges = pd.read_parquet(out_dir / "evidence_edges.parquet")
            findings = pd.read_parquet(out_dir / "findings.parquet")
            self.assertEqual(len(edges), 1)
            self.assertEqual(edges.iloc[0]["compound"], "Chemsex")
            self.assertEqual(edges.iloc[0]["graph_subject_kind"], "exposure_context")
            self.assertEqual(edges.iloc[0]["graph_overview_subject_label"], "Chemsex")
            self.assertEqual(edges.iloc[0]["graph_overview_subject_kind"], "exposure_context")
            self.assertNotIn("Ketamine", set(edges["compound"]))
            self.assertEqual(findings.iloc[0]["graph_subject_label"], exposure)
            self.assertEqual(manifest["graph_subject_kind_counts"], {"exposure_context": 1})

    def test_chemsex_real_world_finding_adds_context_edges_without_duplicating_finding(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            registry_path = root / "registry.json"
            source_path = root / "routed.json"
            out_dir = root / "kg"
            write_json(
                registry_path,
                {
                    "compounds": [
                        {"label": "Ketamine", "aliases": [], "ids": {}, "status": "seeded"},
                        {
                            "label": "Mephedrone",
                            "aliases": ["4-MMC"],
                            "ids": {},
                            "status": "seeded",
                            "graph_scope": "out_of_scope_nonpsychedelic",
                        },
                    ],
                    "targets": [],
                    "disorders": [],
                },
            )
            exposure = "Chemsex (methamphetamine, mephedrone, GHB/GBL, and ketamine)"
            write_json(
                source_path,
                [
                    {
                        "study_doi": "10.1000/chemsex-context",
                        "domain": "real_world_public_health",
                        "compound": exposure,
                        "graph_subject_label": exposure,
                        "graph_subject_kind": "exposure_context",
                        "exposure_or_policy": exposure,
                        "public_health_topic_category": "Prevalence and trends",
                        "public_health_measure": "past-year prevalence",
                        "finding_summary": "The study reported the prevalence of chemsex.",
                        "support": "Chemsex prevalence was reported for the study population.",
                        "source_item_type": "primary_item",
                        "paper_assessment_route": "primary_evidence",
                    }
                ],
            )

            build_tables(
                registry_path=registry_path,
                out_dir=out_dir,
                write_duckdb=False,
                graph_sources={
                    "routed_extractions": {
                        "path": source_path,
                        "domain": "routed",
                        "dataset": "routed",
                        "default_evidence_type": "primary_evidence",
                        "skip_audit": True,
                    }
                },
            )

            findings = pd.read_parquet(out_dir / "findings.parquet")
            edges = pd.read_parquet(out_dir / "evidence_edges.parquet")
            entities = pd.read_parquet(out_dir / "entities.parquet")
            self.assertEqual(len(findings), 1)
            self.assertEqual((edges["projection_type"] == "outcome").sum(), 1)
            context_edges = edges[edges["projection_type"] == "use_context"]
            self.assertEqual(
                set(context_edges["compound"]),
                {"Ketamine"},
            )
            self.assertEqual(set(context_edges["entity_label"]), {"Chemsex"})
            self.assertEqual(set(context_edges["relation_type"]), {"reported_in_use_context"})
            chemsex = entities[entities["label"] == "Chemsex"].iloc[0]
            self.assertEqual(chemsex["entity_kind"], "exposure_context")
            self.assertEqual(chemsex["graph_parent_label"], "Sexualized drug use")
            self.assertIn("Sexualized drug use", set(entities["label"]))

    def test_background_only_primary_claim_is_retained_but_not_admitted(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            registry_path = root / "registry.json"
            source_path = root / "routed.json"
            out_dir = root / "kg"
            write_json(
                registry_path,
                {
                    "compounds": [{"label": "Ketamine", "aliases": [], "ids": {}, "status": "seeded"}],
                    "targets": [],
                    "disorders": [
                        {"label": "Major depressive disorder", "aliases": ["MDD"], "ids": {}, "status": "seeded"}
                    ],
                },
            )
            write_json(
                source_path,
                [
                    {
                        "study_doi": "10.1000/background",
                        "domain": "clinical_outcome",
                        "compound": "Ketamine",
                        "condition_or_indication": "MDD",
                        "source_item_type": "primary_item",
                        "evidence_location": "Introduction / Background",
                        "paper_assessment_route": "primary_evidence",
                    }
                ],
            )

            build_tables(
                registry_path=registry_path,
                out_dir=out_dir,
                write_duckdb=False,
                graph_sources={
                    "routed_extractions": {
                        "path": source_path,
                        "domain": "routed",
                        "dataset": "routed",
                        "default_evidence_type": "primary_evidence",
                        "skip_audit": True,
                    }
                },
            )

            findings = pd.read_parquet(out_dir / "findings.parquet")
            self.assertEqual(findings.iloc[0]["graph_admission_status"], "paper_detail")
            self.assertEqual(
                findings.iloc[0]["graph_admission_reason"],
                "primary_claim_supported_only_by_background_location",
            )


if __name__ == "__main__":
    unittest.main()
