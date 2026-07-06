import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from pipeline.extract.io_utils import write_json
from pipeline.kg.build_evidence_tables import (
    DEFAULT_ROUTED_KG_RUN_ROOT,
    build_tables,
    canonicalize_registry_label,
    clinical_endpoint_rows,
    graphable_compound_match,
    graph_sources_for_preset,
    match_vocabulary_entity,
    molecular_effect_label,
    node_vocabulary_lookup,
    normalize_claim_metadata,
    registry_lookup,
    resolve_kg_output_dir,
    safety_endpoint_label,
    symptom_endpoint_label,
    write_duckdb_database,
)


class BuildEvidenceTablesTest(unittest.TestCase):
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

    def test_final_registry_and_vocabulary_aliases_cover_common_leftovers(self) -> None:
        root = Path(__file__).resolve().parents[1]
        registry = registry_lookup(root / "data" / "curated" / "entity_registry.json")
        vocabulary = node_vocabulary_lookup(root / "schema" / "kg_node_vocabularies.json")

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

        brain_cases = [
            ("ventral medial prefrontal cortex (vmPFC)", "Medial prefrontal cortex"),
            ("primary visual area (V1)", "Occipital cortex"),
            ("ventral tegmental area (VTA)", "Ventral tegmental area"),
            ("caudate nucleus", "Striatum"),
            ("primary somatosensory cortex (S1)", "Somatosensory cortex"),
            ("lateral habenula (LHb)", "Lateral habenula"),
            ("periaqueductal grey (PAG)", "Periaqueductal gray"),
            ("piriform cortex (PirC)", "Piriform cortex"),
            ("locus coeruleus", "Locus coeruleus"),
            ("left precuneus", "Precuneus"),
            ("posterior parahippocampal cortex", "Parahippocampal cortex"),
            ("auditory cortex", "Auditory cortex"),
        ]
        for raw_label, expected in brain_cases:
            with self.subTest(raw_label=raw_label):
                self.assertEqual(match_vocabulary_entity(raw_label, "brain_region", vocabulary)["label"], expected)
        self.assertEqual(
            match_vocabulary_entity("thalamocortical", "neural_circuit", vocabulary)["label"],
            "Thalamocortical circuit",
        )

    def test_safety_endpoint_label_uses_specific_route_native_fields(self) -> None:
        cases = [
            ({"safety_event_or_measure": "QTc prolongation"}, "Cardiovascular safety"),
            ({"finding_summary": "No serious adverse events occurred during treatment."}, "Serious adverse events"),
            (
                {
                    "safety_event_or_measure": "psychotomimetic symptoms",
                    "outcome_measure": "BPRS positive subscale",
                },
                "Psychosis-like adverse effects",
            ),
            ({"safety_event_or_measure": "headache after dosing"}, "Headache adverse effects"),
            ({"safety_event_or_measure": "sleep disturbance after dosing"}, "Sleep disturbance adverse effects"),
            ({"safety_event_or_measure": "no suicidal ideation occurred"}, "Suicidality safety signals"),
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
            ({"safety_event_or_measure": "mild adverse events"}, "Unspecified adverse events"),
            ({"support": "A case of intoxication required poison control consultation."}, "Acute intoxication/poisoning"),
            ({"outcome_measure": "Clinician-Administered Dissociative States Scale (CADSS)"}, "Dissociation adverse effects"),
            ({"outcome_measure": "Young Mania Rating Scale (YMRS)"}, "Mania/hypomania switch"),
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
        self.assertEqual(safety_rows[0]["graph_entity_label"], "Suicidality safety signals")
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
                "Immediate early gene activation",
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
                "Gene expression",
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
                "Norepinephrine signaling",
            ),
            (
                {
                    "graph_entity_label": "TNF-alpha levels",
                    "support": "Treatment decreased the pro-inflammatory cytokine TNF-alpha.",
                },
                "Inflammation",
            ),
        ]

        for row, expected in cases:
            with self.subTest(expected=expected, row=row):
                self.assertEqual(
                    molecular_effect_label(dict(row), "biomarker_readout", row["graph_entity_label"]),
                    expected,
                )

    def test_real_world_public_health_metadata_uses_naturalistic_use_graph_nodes(self) -> None:
        cases = [
            (
                {
                    "public_health_measure": "lifetime prevalence",
                    "public_health_topic_category": "epidemiology",
                    "finding_summary": "Lifetime LSD use was reported by 1.2% of the general population.",
                },
                "Prevalence & trends",
            ),
            (
                {
                    "public_health_measure": "Lifetime prevalence",
                    "public_health_topic_category": "Epidemiology",
                    "study_title": "Prevalence and Reasons for Microdosing Cannabis, Psilocybin, LSD, and MDMA Among US Adults",
                    "finding_summary": "The lifetime prevalence of LSD microdosing was estimated at 4.8%.",
                },
                "Microdosing",
            ),
            (
                {
                    "public_health_measure": "route of administration",
                    "public_health_topic_category": "use patterns and administration routes",
                    "finding_summary": "Smoking was the most prevalent route among recreational DMT users.",
                },
                "Recreational use",
            ),
            (
                {
                    "public_health_measure": "Reporting Odds Ratio for substance-related adverse events",
                    "public_health_topic_category": "Abuse liability and misuse",
                },
                "Emergency/toxicology reports",
            ),
            (
                {
                    "public_health_measure": "Suicidal ideation, planning, and attempts",
                    "public_health_topic_category": "Population-level safety",
                },
                "Emergency/toxicology reports",
            ),
            (
                {
                    "public_health_measure": "Population-normalised daily loads in wastewater",
                    "study_design": "Wastewater-based epidemiology surveillance",
                },
                "Wastewater & market signals",
            ),
            (
                {
                    "public_health_measure": "ethnoracial inclusion",
                    "public_health_topic_category": "access and equity",
                },
                "Access to services",
            ),
            (
                {
                    "public_health_measure": "Early access programme utilization and patient characteristics",
                    "public_health_topic_category": "Service delivery and access",
                },
                "Access to services",
            ),
            (
                {
                    "public_health_measure": "Prevalence of drug type in amnesty bins",
                    "public_health_topic_category": "Harm reduction and drug adulteration",
                },
                "Drug checking & adulteration",
            ),
            (
                {
                    "public_health_measure": "Past year crime arrests",
                    "public_health_topic_category": "Criminality and Public Safety",
                },
                "Legal/criminal justice",
            ),
            (
                {
                    "exposure_or_policy": "Psilocybin (Busting method)",
                    "public_health_measure": "Prevalence of use and preventive efficacy",
                    "population": "patients with cluster headache",
                },
                "Self-treatment",
            ),
            (
                {
                    "public_health_measure": "Rate of problematic use patterns",
                    "support": "A retreat center owner estimated that 1 in 10 participants develop a temporary obsessive relationship with ayahuasca.",
                },
                "Ceremonial/retreat use",
            ),
            (
                {
                    "public_health_measure": "Polysubstance use prevalence",
                    "finding_summary": "Most first-time LSD users reported co-use with cannabis or alcohol.",
                },
                "Polysubstance use",
            ),
            (
                {
                    "public_health_measure": "Hallucinogen use disorder prevalence",
                    "public_health_topic_category": "Abuse liability and misuse",
                },
                "Problematic use",
            ),
        ]

        for row, expected in cases:
            with self.subTest(expected=expected, row=row):
                normalized = normalize_claim_metadata(dict(row), "real_world_public_health")
                self.assertEqual(normalized["public_health_graph_label"], expected)
                self.assertEqual(normalized["graph_entity_label"], expected)

    def test_cognitive_behavioral_metadata_uses_construct_graph_nodes(self) -> None:
        cases = [
            (
                {
                    "graph_entity_label": "Anhedonia",
                    "task_or_measure": "Sucrose preference test",
                    "support": "Treatment reversed stress-induced anhedonia.",
                },
                "Reward processing",
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
                "Threat avoidance",
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
                "Drug seeking",
            ),
            (
                {
                    "graph_entity_label": "Addiction behavior",
                    "outcome_measure": "Opioid Craving Scale",
                },
                "Drug seeking",
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

    def test_generic_locomotor_activity_is_not_a_cognition_graph_node(self) -> None:
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
            self.assertTrue(findings.empty)
            self.assertEqual(audit.iloc[0]["normalization_status"], "generic_behavior_not_graphable")

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
                    "graph_entity_label": "Psychotomimetic symptoms",
                    "instrument_or_measure": "Brief Psychiatric Rating Scale (BPRS)",
                },
                "Psychosis-like effects",
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
                "Personal meaning",
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
                    "support": "Participants reported euphoria, drug liking, and good effects.",
                },
                "Euphoria",
            ),
            (
                {
                    "graph_entity_label": "Contentedness",
                    "support": "The scale measured calmness, alertness, and contentedness.",
                },
                "Positive affect",
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
                "Dissociation adverse effects",
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
            self.assertEqual(by_doi["10.1000/pk-analyte"]["entity_label"], "Ketamine")
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
            self.assertEqual(by_doi["10.1000/pk-receptor"]["primary_graph_anchor_kind"], "target")
            self.assertEqual(by_doi["10.1000/pk-receptor"]["pk_relationship_type"], "exposure_linked_to_effect")
            self.assertEqual(by_doi["10.1000/pk-receptor"]["pk_graph_object_kind"], "effect_or_response")
            self.assertEqual(by_doi["10.1000/pk-receptor"]["pk_graph_object_label"], "NMDA receptor occupancy")
            self.assertEqual(by_doi["10.1000/pk-receptor"]["pharmacokinetic_display_label"], "NMDA receptor occupancy")

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
            self.assertEqual(by_doi["10.1000/direct-target"]["entity_kind"], "target")
            self.assertEqual(by_doi["10.1000/direct-target"]["relation_type"], "has_mechanistic_target")
            self.assertEqual(by_doi["10.1000/target-readout"]["entity_kind"], "biomarker_readout")
            self.assertEqual(by_doi["10.1000/target-readout"]["entity_label"], "SERT protein levels")
            self.assertEqual(by_doi["10.1000/target-readout"]["relation_type"], "has_biomarker_readout")
            self.assertEqual(finding_by_doi["10.1000/target-readout"]["molecular_effect_label"], "Serotonin signaling")
            self.assertEqual(by_doi["10.1000/direct-target-signaling-context"]["entity_kind"], "target")
            self.assertEqual(by_doi["10.1000/direct-target-signaling-context"]["entity_label"], "SERT (SLC6A4)")
            self.assertEqual(by_doi["10.1000/biomarker"]["entity_kind"], "biomarker_readout")
            self.assertEqual(by_doi["10.1000/biomarker"]["entity_label"], "BDNF expression")
            self.assertEqual(by_doi["10.1000/biomarker"]["relation_type"], "has_biomarker_readout")
            self.assertEqual(finding_by_doi["10.1000/biomarker"]["molecular_effect_label"], "Neuroplasticity")
            self.assertEqual(by_doi["10.1000/c-fos"]["entity_kind"], "biomarker_readout")
            self.assertEqual(by_doi["10.1000/c-fos"]["entity_label"], "c-Fos activation")
            self.assertEqual(
                finding_by_doi["10.1000/c-fos"]["molecular_effect_label"],
                "Immediate early gene activation",
            )
            self.assertEqual(by_doi["10.1000/pathway"]["entity_kind"], "pathway_process")
            self.assertEqual(by_doi["10.1000/pathway"]["entity_label"], "mTORC1 activation")
            self.assertEqual(by_doi["10.1000/pathway"]["relation_type"], "has_mechanistic_pathway")
            self.assertEqual(finding_by_doi["10.1000/pathway"]["molecular_effect_label"], "Intracellular signaling")
            self.assertEqual(by_doi["10.1000/pathway-phosphorylation"]["entity_kind"], "pathway_process")
            self.assertEqual(by_doi["10.1000/pathway-phosphorylation"]["entity_label"], "ERK phosphorylation")
            self.assertEqual(finding_by_doi["10.1000/pathway-phosphorylation"]["molecular_effect_label"], "Intracellular signaling")
            self.assertEqual(by_doi["10.1000/neuroplasticity-sublabel"]["entity_kind"], "pathway_process")
            self.assertEqual(by_doi["10.1000/neuroplasticity-sublabel"]["entity_label"], "Dendritic spine density")
            self.assertEqual(finding_by_doi["10.1000/neuroplasticity-sublabel"]["molecular_effect_label"], "Neuroplasticity")
            self.assertEqual(by_doi["10.1000/dopamine-uptake"]["entity_kind"], "biomarker_readout")
            self.assertEqual(by_doi["10.1000/dopamine-uptake"]["entity_label"], "Dopamine uptake")
            self.assertEqual(finding_by_doi["10.1000/dopamine-uptake"]["molecular_effect_label"], "Dopamine signaling")
            self.assertEqual(by_doi["10.1000/perineuronal-net"]["entity_kind"], "pathway_process")
            self.assertEqual(by_doi["10.1000/perineuronal-net"]["entity_label"], "Neuroplasticity")
            self.assertEqual(finding_by_doi["10.1000/perineuronal-net"]["molecular_effect_label"], "Neuroplasticity")
            self.assertEqual(by_doi["10.1000/generic-neurotransmitter-specific-readout"]["entity_kind"], "pathway_process")
            self.assertEqual(by_doi["10.1000/generic-neurotransmitter-specific-readout"]["entity_label"], "Serotonin signaling")
            self.assertEqual(
                finding_by_doi["10.1000/generic-neurotransmitter-specific-readout"]["molecular_effect_label"],
                "Serotonin signaling",
            )
            self.assertNotIn("10.1000/generic-neurotransmitter-unspecified", by_doi)
            self.assertEqual(by_doi["10.1000/explicit-inflammation"]["entity_kind"], "pathway_process")
            self.assertEqual(by_doi["10.1000/explicit-inflammation"]["entity_label"], "Inflammation")
            self.assertEqual(finding_by_doi["10.1000/explicit-inflammation"]["molecular_effect_label"], "Inflammation")
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
            self.assertEqual(by_doi["10.1000/collapsed-brain-subregions"]["entity_kind"], "brain_region")
            self.assertEqual(by_doi["10.1000/collapsed-brain-subregions"]["entity_label"], "Occipital cortex")
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
        self.assertIn("MADRS", set(scale_edges["entity_label"]))
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
            for doi_suffix, condition in (
                ("broad-depression", "depression"),
                ("mdd", "major depressive disorder with depression"),
                ("mood-parenthetical-mdd", "mood disorders (predominantly major depressive disorder)"),
                ("trd", "treatment-resistant depression"),
                ("bipolar-depression", "treatment-resistant bipolar I/II depression"),
                ("broad-anxiety", "anxiety"),
                ("gad", "generalized anxiety disorder with anxiety symptoms"),
                ("life-threatening-anxiety", "anxiety related to life-threatening illnesses"),
                ("broad-pain", "pain"),
                ("chronic-pain", "chronic pain with pain interference"),
                ("neuropathic-pain", "chronic neuropathic orofacial pain"),
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
                    "outcome_scale",
                    "brain_network",
                    "public_health_measure",
                },
            )
            self.assertIn("secondary_literature", set(edges["evidence_type"]))
            self.assertNotIn("functional_outcome", set(edges["entity_kind"]))
            scale = edges[edges["entity_kind"] == "outcome_scale"].iloc[0]
            self.assertEqual(scale["entity_label"], "WEMWBS")
            self.assertEqual(scale["compound"], "Psilocybin")
            self.assertNotIn("Wellbeing", set(edges["entity_label"]))
            self.assertNotIn("Patient experience", set(edges["entity_label"]))
            self.assertNotIn("Psilocybin and MDMA", set(edges["compound"]))
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
            self.assertEqual(pk_edge["relation_type"], "has_pharmacokinetic_exposure")
            public_health_edge = edges[edges["domain"] == "real_world_public_health"].iloc[0]
            self.assertEqual(public_health_edge["entity_kind"], "public_health_measure")
            self.assertEqual(public_health_edge["entity_label"], "Access to services")
            self.assertEqual(public_health_edge["relation_type"], "has_public_health_evidence")
            audit = pd.read_parquet(out_dir / "normalization_audit.parquet")
            self.assertIn("compound_combo_not_graphable", set(audit["normalization_status"]))
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
                    "paper:10.1000/function",
                },
            )

            entities = pd.read_parquet(out_dir / "entities.parquet")
            neuroplasticity = entities[entities["label"] == "Neuroplasticity"].iloc[0]
            self.assertEqual(neuroplasticity["entity_kind"], "pathway_process")

            self.assertTrue((out_dir / "claims.parquet").exists())
            self.assertTrue((out_dir / "normalization_audit.parquet").exists())
            self.assertEqual(json.loads((out_dir / "manifest.json").read_text())["duckdb"]["status"], "skipped")


if __name__ == "__main__":
    unittest.main()
