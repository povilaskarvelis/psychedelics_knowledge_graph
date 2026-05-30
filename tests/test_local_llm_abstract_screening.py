import argparse
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pipeline.review.run_local_llm_abstract_screening import (
    ABSTRACT_SCREENING_SCHEMA,
    FAST_SCREENING_SCHEMA,
    append_checkpoint_result,
    build_fast_screening_prompt,
    build_prompt,
    checkpoint_result_is_compatible,
    configured_allowed_compound_terms,
    dataset_paths,
    default_checkpoint_jsonl_path,
    deterministic_irrelevant_adjudication,
    deterministic_prescreen_decision,
    download_queue_eligible,
    enforce_validation_flags,
    evidence_domain_tags_for_context,
    fast_screen_excludes,
    fast_screen_irrelevant_adjudication,
    filter_indexed_rows,
    flatten_result,
    load_checkpoint_results,
    load_report_results,
    load_reprocess_doi_set,
    matched_in_scope_intervention_terms,
    normalize_routing_tags,
    merge_report_rows,
    print_screening_row_followup,
    queue_rows_from_results,
    read_doi_file,
    refresh_result_metadata,
    revalidate_checkpoint_result,
    screen_row,
    semantic_auto_eligible,
    truncate_checkpoint,
    validation_flags,
    verified_supported_contexts,
    write_csv,
)


def fake_args(**overrides) -> argparse.Namespace:
    defaults = {
        "dry_run": True,
        "model": "qwen3:14b",
        "fast_screen_model": "",
        "ollama_url": "http://localhost:11434",
        "timeout_sec": 1,
        "temperature": 0.0,
        "num_ctx": 2048,
        "deterministic_prescreen": False,
        "deterministic_prescreen_only": False,
        "out_json": "",
        "out_csv": "",
        "doi_file": "",
        "use_heuristic_audit": False,
        "fast_screen_timeout_sec": 1,
        "fast_screen_temperature": 0.0,
        "fast_screen_num_ctx": 2048,
        "fast_screen_confidence": 0.9,
        "max_contexts": 16,
        "auto_confidence": 0.85,
        "context_confidence": 0.75,
        "checkpoint_jsonl": "",
        "resume_from_checkpoint": False,
        "materialize_checkpoint_only": False,
        "refresh_report_metadata_only": False,
        "report_fallback_json": "",
        "merge_report_json": [],
        "no_checkpoint": False,
        "quiet_progress": False,
        "show_checkpoint_progress": False,
        "reprocess_dois_file": "",
        "reprocess_all_checkpoint_dois": False,
        "only_with_abstract": False,
        "only_undownloaded": False,
        "only_heuristic_possible": False,
        "download_queue_out": "",
        "relevant_queue_out": "",
        "uncertain_queue_out": "",
        "prescreen_output_label": "",
        "prescreen_json_out": "",
        "prescreen_csv_out": "",
        "prescreen_retained_queue_out": "",
        "prescreen_excluded_queue_out": "",
    }
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


class LocalLlmAbstractScreeningTest(unittest.TestCase):
    def test_schema_requires_quote_and_contexts(self) -> None:
        self.assertIn("supporting_abstract_quote", ABSTRACT_SCREENING_SCHEMA["required"])
        self.assertIn("supported_contexts", ABSTRACT_SCREENING_SCHEMA["required"])
        self.assertIn("routing_tags", ABSTRACT_SCREENING_SCHEMA["required"])
        self.assertIn("molecular_pathway", ABSTRACT_SCREENING_SCHEMA["properties"]["routing_tags"]["items"]["enum"])
        self.assertIn("brain_system", ABSTRACT_SCREENING_SCHEMA["properties"]["routing_tags"]["items"]["enum"])
        self.assertIn("subjective_experience", ABSTRACT_SCREENING_SCHEMA["properties"]["routing_tags"]["items"]["enum"])
        self.assertIn("pharmacokinetics_exposure", ABSTRACT_SCREENING_SCHEMA["properties"]["routing_tags"]["items"]["enum"])
        self.assertIn("intervention_context", ABSTRACT_SCREENING_SCHEMA["properties"]["routing_tags"]["items"]["enum"])
        self.assertIn("real_world_use_public_health", ABSTRACT_SCREENING_SCHEMA["properties"]["routing_tags"]["items"]["enum"])
        self.assertIn("bridge_clinical_mechanism", ABSTRACT_SCREENING_SCHEMA["properties"]["routing_tags"]["items"]["enum"])
        context_schema = ABSTRACT_SCREENING_SCHEMA["properties"]["supported_contexts"]["items"]
        self.assertIn("compound", context_schema["required"])
        self.assertIn("supporting_quote", context_schema["required"])
        self.assertNotIn("evidence_strength", ABSTRACT_SCREENING_SCHEMA["properties"])
        self.assertNotIn("paper_type", ABSTRACT_SCREENING_SCHEMA["properties"])

    def test_fast_screening_schema_is_minimal(self) -> None:
        self.assertEqual(
            FAST_SCREENING_SCHEMA["properties"]["screening_action"]["enum"],
            ["exclude_obvious_irrelevant", "escalate"],
        )
        self.assertEqual(
            set(FAST_SCREENING_SCHEMA["required"]),
            {"screening_action", "confidence", "supporting_quote", "reason"},
        )

    def test_prompt_uses_metadata_without_heuristic_labels(self) -> None:
        row = {
            "study_doi": "10.example/test",
            "study_title": "Psilocybin therapy for depression",
            "abstract": "Psilocybin therapy reduced depression scores.",
            "relevance_suggested": "likely_irrelevant",
            "screening_status": "excluded_low_signal",
        }

        messages = build_prompt(
            "disorder",
            row,
            [{"compound": "Psilocybin", "entity": "Major depressive disorder"}],
        )
        payload = json.loads(messages[1]["content"])

        self.assertEqual(payload["candidate_metadata"]["study_doi"], "10.example/test")
        self.assertEqual(payload["candidate_contexts"][0]["compound"], "Psilocybin")
        self.assertNotIn("relevance_suggested", payload["candidate_metadata"])
        self.assertNotIn("likely_irrelevant", messages[1]["content"])
        self.assertIn("do not classify source type", messages[1]["content"])
        self.assertIn("routing_tags", messages[1]["content"])
        self.assertIn("brain regions, circuits, networks", messages[1]["content"])

    def test_fast_prompt_is_conservative_about_escalation(self) -> None:
        row = {
            "study_doi": "10.example/test",
            "study_title": "Hemodialysis intervention for quality of life",
            "abstract": "Exercise improved quality of life in hemodialysis patients.",
        }

        messages = build_fast_screening_prompt(
            "disorder",
            row,
            [{"compound": "Psilocybin", "entity": "Depression"}],
        )
        payload = json.loads(messages[1]["content"])

        self.assertIn("When in doubt, escalate", messages[0]["content"])
        self.assertIn("Return escalate if the paper mentions any psychedelic", messages[1]["content"])
        self.assertIn("candidate_contexts", payload)
        self.assertIn("supplied candidate_contexts compound or entity term", messages[1]["content"])
        self.assertIn("Clinical-population brain/cognition papers should escalate", messages[1]["content"])

    def test_fast_screen_excludes_only_high_confidence_verified_quote(self) -> None:
        context = "Title: Hemodialysis intervention\nAbstract: Exercise improved quality of life."
        screen = {
            "screening_action": "exclude_obvious_irrelevant",
            "confidence": 0.95,
            "supporting_quote": "Exercise improved quality of life.",
            "reason": "different intervention",
        }

        self.assertTrue(fast_screen_excludes(screen, context=context, min_confidence=0.9))
        self.assertFalse(fast_screen_excludes({**screen, "confidence": 0.8}, context=context, min_confidence=0.9))
        self.assertFalse(
            fast_screen_excludes(
                {**screen, "supporting_quote": "invented quote"},
                context=context,
                min_confidence=0.9,
            )
        )

    def test_fast_screen_exclusion_is_vetoed_by_candidate_terms(self) -> None:
        context = "Title: Depression outcomes\nAbstract: Exercise improved quality of life."
        screen = {
            "screening_action": "exclude_obvious_irrelevant",
            "confidence": 0.95,
            "supporting_quote": "Exercise improved quality of life.",
            "reason": "different intervention",
        }

        self.assertFalse(
            fast_screen_excludes(
                screen,
                context=context,
                min_confidence=0.9,
                candidate_contexts=[{"compound": "Psilocybin", "entity": "Depression"}],
            )
        )

    def test_fast_screen_irrelevant_adjudication_is_non_downloadable(self) -> None:
        adjudication = fast_screen_irrelevant_adjudication(
            {
                "confidence": 0.94,
                "supporting_quote": "Exercise improved quality of life.",
                "reason": "no in-scope intervention",
            }
        )

        self.assertEqual(adjudication["relevance"], "irrelevant")
        self.assertNotIn("evidence_strength", adjudication)
        self.assertNotIn("download_priority", adjudication)

    def test_deterministic_prescreen_excludes_rows_without_intervention_signal(self) -> None:
        row = {
            "study_title": "Exercise intervention for depression",
            "abstract": "This randomized trial tested an exercise program for depression symptoms in adults receiving standard outpatient mental health care.",
            "contexts": [],
        }

        decision = deterministic_prescreen_decision("disorder", row, heuristic={}, candidate_contexts=[])

        self.assertEqual(decision["action"], "exclude_obvious_irrelevant")
        adjudication = deterministic_irrelevant_adjudication(decision)
        self.assertEqual(adjudication["relevance"], "irrelevant")
        self.assertNotIn("should_download_fulltext", adjudication)

    def test_deterministic_prescreen_escalates_intervention_signals(self) -> None:
        psychedelic_row = {
            "study_title": "Psilocybin therapy for depression",
            "abstract": "Psilocybin therapy reduced depression symptoms in adults with major depression.",
            "contexts": [{"compound": "Psilocybin", "entity": "Depression"}],
        }
        accented_ketamine_row = {
            "study_title": "Intérêt de la kétamine dans le traitement des douleurs chroniques",
            "abstract": "La kétamine est utilisée dans la prise en charge de la douleur chronique réfractaire aux traitements classiques.",
            "contexts": [],
        }
        retained_row = {
            "study_title": "Novel intervention for depression",
            "abstract": "This report discusses a novel intervention for depression symptoms in adults.",
            "contexts": [],
        }

        self.assertEqual(
            deterministic_prescreen_decision(
                "disorder",
                psychedelic_row,
                heuristic={},
                candidate_contexts=[{"compound": "Psilocybin", "entity": "Depression"}],
            )["action"],
            "escalate",
        )
        self.assertEqual(
            deterministic_prescreen_decision(
                "disorder",
                accented_ketamine_row,
                heuristic={},
                candidate_contexts=[],
            )["action"],
            "escalate",
        )
        self.assertEqual(
            deterministic_prescreen_decision(
                "disorder",
                retained_row,
                heuristic={"relevance_suggested": "possible_relevant"},
                candidate_contexts=[],
            )["action"],
            "exclude_obvious_irrelevant",
        )

    def test_deterministic_prescreen_excludes_ketamine_only_procedural_sedation(self) -> None:
        rows = [
            {
                "study_title": "Ketamine as a dissociative anesthetic for procedural sedation during endoscopy",
                "abstract": "This study evaluated ketamine dosing for emergency department procedural sedation.",
                "contexts": [],
            },
            {
                "study_title": "Clinical and pharmacokinetic evaluation of S-ketamine for intravenous general anaesthesia",
                "abstract": "Racemic ketamine and S-ketamine were evaluated during field castration.",
                "contexts": [],
            },
        ]

        for row in rows:
            with self.subTest(row=row["study_title"]):
                decision = deterministic_prescreen_decision("disorder", row, heuristic={}, candidate_contexts=[])

                self.assertEqual(decision["action"], "exclude_obvious_irrelevant")
                self.assertIn("acute procedural anesthesia or sedation", decision["reason"])

    def test_deterministic_prescreen_tags_brain_cognition_and_bridge_scope(self) -> None:
        row = {
            "study_title": "Psilocybin therapy and default mode network connectivity in depression",
            "abstract": "Patients with depression received psilocybin and completed fMRI and cognitive flexibility tasks.",
            "contexts": [],
        }

        decision = deterministic_prescreen_decision("mechanistic", row, heuristic={}, candidate_contexts=[])

        self.assertEqual(decision["action"], "escalate")
        self.assertIn("brain_system", decision["routing_tags"])
        self.assertIn("cognitive_behavioral", decision["routing_tags"])
        self.assertIn("clinical_outcome", decision["routing_tags"])
        self.assertIn("bridge_clinical_mechanism", decision["routing_tags"])

    def test_evidence_domain_tags_cover_new_systems_scope(self) -> None:
        context = (
            "Title: MDMA social reward and amygdala-prefrontal circuit function\n"
            "Abstract: The study measured BDNF, fMRI connectivity, empathy, safety, and PTSD symptoms."
        )

        tags = evidence_domain_tags_for_context("mechanistic", context)

        self.assertEqual(
            tags,
            [
                "molecular_pathway",
                "brain_system",
                "cognitive_behavioral",
                "clinical_outcome",
                "safety",
                "bridge_clinical_mechanism",
            ],
        )

    def test_evidence_domain_tags_cover_gap_domain_scope(self) -> None:
        context = (
            "Title: Psilocybin pharmacokinetics and mystical experience in a retreat setting\n"
            "Abstract: Plasma concentration, depression symptoms, preparation, integration, and naturalistic survey outcomes were measured."
        )

        tags = evidence_domain_tags_for_context("disorder", context)

        self.assertEqual(
            tags,
            [
                "clinical_outcome",
                "subjective_experience",
                "pharmacokinetics_exposure",
                "intervention_context",
                "real_world_use_public_health",
                "bridge_clinical_mechanism",
            ],
        )

    def test_evidence_domain_tags_cover_expanded_search_terms(self) -> None:
        context = (
            "Title: Ayahuasca retreat, subjective effects, and global brain connectivity\n"
            "Abstract: The cohort survey measured Challenging Experience Questionnaire scores, "
            "visual analog scale ratings, psilocin glucuronide, AUC, CYP2D6, set setting, "
            "group therapy, ceremonial use, microdose patterns, and arterial spin labeling."
        )

        tags = evidence_domain_tags_for_context("mechanistic", context)

        self.assertIn("brain_system", tags)
        self.assertIn("subjective_experience", tags)
        self.assertIn("pharmacokinetics_exposure", tags)
        self.assertIn("intervention_context", tags)
        self.assertIn("real_world_use_public_health", tags)

    def test_normalize_routing_tags_filters_unknown_values(self) -> None:
        self.assertEqual(
            normalize_routing_tags("brain-system|clinical outcome|not_a_tag|brain_system"),
            ["brain_system", "clinical_outcome"],
        )

    def test_normalize_routing_tags_maps_old_pathway_biomarker_alias(self) -> None:
        self.assertEqual(normalize_routing_tags("pathway-biomarker|molecular_pathway"), ["molecular_pathway"])

    def test_deterministic_prescreen_uses_config_allowed_compounds(self) -> None:
        self.assertIn("Mescaline", configured_allowed_compound_terms())
        row = {
            "study_title": "Mescaline treatment and perception",
            "abstract": "This paper discusses mescaline administration and long-term changes in perception among adult participants.",
            "contexts": [],
        }

        decision = deterministic_prescreen_decision("disorder", row, heuristic={}, candidate_contexts=[])

        self.assertEqual(decision["action"], "escalate")
        self.assertEqual(decision["reason"], "in-scope compound/intervention term appears in title or abstract")

    def test_deterministic_prescreen_retains_disorder_variant_intervention_terms(self) -> None:
        rows = [
            {
                "study_title": "Efeitos do uso de psilocibina em pacientes adultos com ansiedade e depressão",
                "abstract": "Tratamento: uso da psilocibina para ansiedade e depressão.",
                "contexts": [],
            },
            {
                "study_title": "Plant based assisted therapy for substance use disorders",
                "abstract": "Natural medicines are described including psychoactive derivatives of Tabernanthe iboga and Bufo alvarius.",
                "contexts": [],
            },
            {
                "study_title": "Dreams, Hallucinogenic Drug States, and Schizophrenia",
                "abstract": "This review compares dreams, hallucinogenic drug states, and schizophrenia.",
                "contexts": [],
            },
            {
                "study_title": "The Supreme Court versus Peyote",
                "abstract": "Peyote is discussed as a culturally relevant therapeutic modality.",
                "contexts": [],
            },
            {
                "study_title": "Metabolism of the tryptamine 5-MeO-MiPT",
                "abstract": "5-methoxy-N-methyl-N-isopropyltryptamine was detected after intoxication.",
                "contexts": [],
            },
            {
                "study_title": "Psychedeilc Assisted Therapy for post-traumatic stress",
                "abstract": "This article discusses MDMA, psilocybin, and ketamine-assisted approaches.",
                "contexts": [],
            },
        ]

        for row in rows:
            with self.subTest(row=row["study_title"]):
                decision = deterministic_prescreen_decision("disorder", row, heuristic={}, candidate_contexts=[])
                self.assertEqual(decision["action"], "escalate")

    def test_deterministic_prescreen_ignores_ambiguous_bare_acronyms(self) -> None:
        disease_modifying_row = {
            "study_title": "Disease-Modifying Treatments and Ambulatory Function in Multiple Sclerosis",
            "abstract": "This cohort study compared DMT exposure and disease progression in patients with multiple sclerosis.",
            "contexts": [],
        }
        thrombotic_microangiopathy_row = {
            "study_title": "Outcomes in pediatric patients with HSCT-TMA",
            "abstract": "This retrospective study evaluated thrombotic microangiopathy outcomes after transplant.",
            "contexts": [],
        }
        dutch_doet_row = {
            "study_title": "Preventie van kindermishandeling: Wie doet wat?",
            "abstract": "Dit boek geeft inzicht in preventie en zorg.",
            "contexts": [],
        }
        dissociative_symptom_row = {
            "study_title": "Early EMDR therapy for dissociative symptoms after trauma",
            "abstract": "This trial measured dissociative symptoms and post-traumatic stress.",
            "contexts": [],
        }
        minimal_disease_activity_row = {
            "study_title": "Minimal Disease Activity and drug resistance in arthritis",
            "abstract": "MDA was measured as an outcome in patients receiving standard anti-inflammatory drugs.",
            "contexts": [],
        }

        self.assertEqual(
            deterministic_prescreen_decision(
                "disorder",
                disease_modifying_row,
                heuristic={},
                candidate_contexts=[],
            )["action"],
            "exclude_obvious_irrelevant",
        )
        self.assertEqual(
            deterministic_prescreen_decision(
                "disorder",
                dutch_doet_row,
                heuristic={},
                candidate_contexts=[],
            )["action"],
            "exclude_obvious_irrelevant",
        )
        self.assertEqual(
            deterministic_prescreen_decision(
                "disorder",
                dissociative_symptom_row,
                heuristic={},
                candidate_contexts=[],
            )["action"],
            "exclude_obvious_irrelevant",
        )
        self.assertEqual(
            deterministic_prescreen_decision(
                "disorder",
                minimal_disease_activity_row,
                heuristic={},
                candidate_contexts=[],
            )["action"],
            "exclude_obvious_irrelevant",
        )
        self.assertEqual(
            deterministic_prescreen_decision(
                "disorder",
                thrombotic_microangiopathy_row,
                heuristic={},
                candidate_contexts=[],
            )["action"],
            "exclude_obvious_irrelevant",
        )

    def test_ambiguous_acronym_is_retained_with_chemical_support(self) -> None:
        row = {
            "study_title": "N,N-Dimethyltryptamine and cortical dynamics",
            "abstract": "This study tested DMT, a psychedelic tryptamine, in a controlled human experiment.",
            "contexts": [],
        }

        decision = deterministic_prescreen_decision("mechanistic", row, heuristic={}, candidate_contexts=[])

        self.assertEqual(decision["action"], "escalate")
        matched = {term.lower() for term in matched_in_scope_intervention_terms(row["study_title"] + "\n" + row["abstract"])}
        self.assertIn("dmt", matched)

    def test_deterministic_prescreen_retains_doi_compound_context(self) -> None:
        row = {
            "study_title": "Effects of repeated DOI treatment on 5-HT neuronal firing",
            "abstract": (
                "The 5-HT2 receptor agonist 1-(2,5-dimethoxy-4-iodophenyl)-2-aminopropane "
                "(DOI) changed cortical 5-HT release and head-twitch responses."
            ),
            "contexts": [],
        }

        decision = deterministic_prescreen_decision("mechanistic", row, heuristic={}, candidate_contexts=[])

        self.assertEqual(decision["action"], "escalate")
        self.assertIn("DOI", matched_in_scope_intervention_terms(row["study_title"] + "\n" + row["abstract"]))

    def test_deterministic_prescreen_ignores_doi_identifier_context(self) -> None:
        row = {
            "study_title": "Corrigendum: AMPA receptor density in cortical circuits",
            "abstract": "This corrects the article DOI: 10.1000/example.",
            "contexts": [],
        }

        decision = deterministic_prescreen_decision("mechanistic", row, heuristic={}, candidate_contexts=[])

        self.assertEqual(decision["action"], "exclude_obvious_irrelevant")

    def test_deterministic_prescreen_retains_psychedelic_class_chemistry(self) -> None:
        row = {
            "study_title": "Binding of indolylalkylamines at 5-HT2 serotonin receptors",
            "abstract": (
                "This medicinal chemistry study evaluated alpha-methyltryptamine derivatives "
                "for 5-HT2A receptor binding affinity and selectivity."
            ),
            "contexts": [],
        }

        decision = deterministic_prescreen_decision("mechanistic", row, heuristic={}, candidate_contexts=[])

        self.assertEqual(decision["action"], "escalate")
        self.assertIn(
            "psychedelic class chemistry",
            matched_in_scope_intervention_terms(row["study_title"] + "\n" + row["abstract"]),
        )

    def test_deterministic_prescreen_ignores_dmt_nonpsychedelic_acronym_context(self) -> None:
        row = {
            "study_title": "Dimethyltin effects on neuronal ion channels",
            "abstract": "Dimethyltin (DMT) altered AMPA and NMDA receptor currents in oocytes.",
            "contexts": [],
        }

        decision = deterministic_prescreen_decision("mechanistic", row, heuristic={}, candidate_contexts=[])

        self.assertEqual(decision["action"], "exclude_obvious_irrelevant")

    def test_deterministic_prescreen_ignores_nonpsychedelic_lsd_acronym_context(self) -> None:
        rows = [
            {
                "study_title": "Low sodium diet and blood pressure in diabetic patients",
                "abstract": "This meta-analysis compared low sodium diet (LSD) with high sodium diet.",
                "contexts": [],
            },
            {
                "study_title": "Soft drink effects on salivary calcium",
                "abstract": "Data were analyzed with ANOVA and continued with LSD test.",
                "contexts": [],
            },
        ]

        for row in rows:
            with self.subTest(row=row["study_title"]):
                decision = deterministic_prescreen_decision("disorder", row, heuristic={}, candidate_contexts=[])
                self.assertEqual(decision["action"], "exclude_obvious_irrelevant")

    def test_deterministic_prescreen_ignores_nonpsychedelic_mda_acronym_context(self) -> None:
        rows = [
            {
                "study_title": "Oxidative stress markers after cerebral ischemia",
                "abstract": "The study measured malondialdehyde (MDA), cytokines, and receptor expression.",
                "contexts": [],
            },
            {
                "study_title": "5-HT2C receptors and maximal dentate activation",
                "abstract": "Maximal dentate activation (MDA) was measured in anesthetized rats.",
                "contexts": [],
            },
            {
                "study_title": "Oxidative stress after cerebral injury",
                "abstract": "SOD, CAT, GSH, and MDA parameters were measured after treatment.",
                "contexts": [],
            },
        ]

        for row in rows:
            with self.subTest(row=row["study_title"]):
                decision = deterministic_prescreen_decision("mechanistic", row, heuristic={}, candidate_contexts=[])
                self.assertEqual(decision["action"], "exclude_obvious_irrelevant")

    def test_dissociative_class_is_retained_with_drug_support(self) -> None:
        row = {
            "study_title": "Dissociative anesthetics and synaptic plasticity",
            "abstract": "This review discusses dissociative drugs and glutamate signaling.",
            "contexts": [],
        }

        decision = deterministic_prescreen_decision("mechanistic", row, heuristic={}, candidate_contexts=[])

        self.assertEqual(decision["action"], "escalate")
        self.assertIn("dissociative", matched_in_scope_intervention_terms(row["study_title"] + "\n" + row["abstract"]))

    def test_generic_safety_language_does_not_rescue_procedural_ketamine(self) -> None:
        row = {
            "study_title": "Safety and effectiveness of ketamine as a sedative agent for pediatric GI endoscopy",
            "abstract": "This study evaluated ketamine sedation during endoscopy.",
            "contexts": [],
        }

        decision = deterministic_prescreen_decision("disorder", row, heuristic={}, candidate_contexts=[])

        self.assertEqual(decision["action"], "exclude_obvious_irrelevant")

    def test_salvinorin_derivatives_are_retained(self) -> None:
        row = {
            "study_title": "Salvinorin-based antagonists and kappa opioid receptor interactions",
            "abstract": "The study measured affinity and signaling for salvinorin analogues at KOR.",
            "contexts": [],
        }

        decision = deterministic_prescreen_decision("mechanistic", row, heuristic={}, candidate_contexts=[])

        self.assertEqual(decision["action"], "escalate")
        self.assertIn("salvinorin", matched_in_scope_intervention_terms(row["study_title"] + "\n" + row["abstract"]))

    def test_deterministic_prescreen_does_not_use_candidate_contexts_as_safety_hints(self) -> None:
        row = {
            "study_title": "Exercise intervention for depression",
            "abstract": "This randomized trial tested an exercise program for depression symptoms in adults receiving standard outpatient mental health care.",
            "contexts": [{"compound": "Psilocybin", "entity": "Depression"}],
        }

        decision = deterministic_prescreen_decision(
            "disorder",
            row,
            heuristic={},
            candidate_contexts=[{"compound": "Psilocybin", "entity": "Depression"}],
        )

        self.assertEqual(decision["action"], "exclude_obvious_irrelevant")
        self.assertNotIn("candidate", decision["reason"].lower())

    def test_prescreen_output_label_writes_batch_specific_paths(self) -> None:
        paths = dataset_paths("mechanistic", fake_args(dataset="mechanistic", prescreen_output_label="boolean full/v1"))

        self.assertEqual(paths["prescreen_json"].name, "deterministic_prescreen_report_mechanistic.boolean_full_v1.json")
        self.assertEqual(paths["prescreen_csv"].name, "deterministic_prescreen_report_mechanistic.boolean_full_v1.csv")
        self.assertEqual(
            paths["prescreen_retained_queue"].name,
            "doi_queue.mechanistic.deterministic_prescreen_retained.boolean_full_v1.txt",
        )
        self.assertEqual(
            paths["prescreen_excluded_queue"].name,
            "doi_queue.mechanistic.deterministic_prescreen_excluded.boolean_full_v1.txt",
        )

    def test_prescreen_explicit_paths_override_label_defaults(self) -> None:
        out_dir = Path(tempfile.gettempdir())
        paths = dataset_paths(
            "disorder",
            fake_args(
                dataset="disorder",
                prescreen_output_label="ignored",
                prescreen_json_out=str(out_dir / "prescreen.json"),
                prescreen_csv_out=str(out_dir / "prescreen.csv"),
                prescreen_retained_queue_out=str(out_dir / "retained.txt"),
                prescreen_excluded_queue_out=str(out_dir / "excluded.txt"),
            ),
        )

        self.assertEqual(paths["prescreen_json"], (out_dir / "prescreen.json").resolve())
        self.assertEqual(paths["prescreen_csv"], (out_dir / "prescreen.csv").resolve())
        self.assertEqual(paths["prescreen_retained_queue"], (out_dir / "retained.txt").resolve())
        self.assertEqual(paths["prescreen_excluded_queue"], (out_dir / "excluded.txt").resolve())

    def test_verified_supported_contexts_requires_quote_and_confidence(self) -> None:
        adjudication = {
            "supporting_abstract_quote": "Psilocybin therapy reduced depression scores.",
            "supported_contexts": [
                {
                    "compound": "Psilocybin",
                    "entity": "Depression",
                    "support": "supported",
                    "supporting_quote": "Psilocybin therapy reduced depression scores.",
                    "confidence": 0.9,
                    "reason": "direct title/abstract support",
                },
                {
                    "compound": "MDMA",
                    "entity": "PTSD",
                    "support": "supported",
                    "supporting_quote": "not_found",
                    "confidence": 0.95,
                    "reason": "missing quote",
                },
                {
                    "compound": "LSD",
                    "entity": "Depression",
                    "support": "supported",
                    "supporting_quote": "LSD reduced depression.",
                    "confidence": 0.4,
                    "reason": "low confidence",
                },
            ],
        }
        context = "Title: Trial\nAbstract: Psilocybin therapy reduced depression scores."

        verified = verified_supported_contexts(adjudication, context=context, min_confidence=0.75)

        self.assertEqual(len(verified), 1)
        self.assertEqual(verified[0]["compound"], "Psilocybin")

    def test_semantic_auto_eligible_requires_relevant_verified_context(self) -> None:
        adjudication = {
            "relevance": "relevant",
            "confidence": 0.9,
            "needs_targeted_qa": False,
        }

        self.assertTrue(
            semantic_auto_eligible(adjudication, quote_verified=True, verified_context_count=1, min_confidence=0.85)
        )
        self.assertFalse(
            semantic_auto_eligible(adjudication, quote_verified=True, verified_context_count=0, min_confidence=0.85)
        )

    def test_download_queue_eligible_uses_relevance_only(self) -> None:
        self.assertTrue(download_queue_eligible({"relevance": "relevant"}, verified_context_count=1))
        self.assertTrue(download_queue_eligible({"relevance": "uncertain"}))
        self.assertFalse(download_queue_eligible({"relevance": "irrelevant"}))

    def test_validation_flags_force_unquoted_decision_to_targeted_qa(self) -> None:
        adjudication = {
            "relevance": "irrelevant",
            "needs_targeted_qa": False,
        }

        updated = enforce_validation_flags(adjudication, quote_verified=False, verified_context_count=0)

        self.assertTrue(updated["needs_targeted_qa"])

    def test_queue_rows_require_verified_context_for_relevant_context_queue(self) -> None:
        result = {
            "flat": {"status": "ok", "download_queue_eligible": True},
            "input_row": {
                "study_doi": "10.example/test",
                "study_title": "Example",
                "study_year": "2025",
                "authors": "A. Author",
                "publication_date": "2025-01-02",
                "journal_issn": "1234-5678",
                "funders": "Test Funder",
            },
            "adjudication": {"relevance": "relevant"},
            "verification": {
                "verified_supported_contexts": [
                    {"compound": "Psilocybin", "entity": "Depression"},
                ]
            },
        }
        no_context = {
            "flat": {"status": "ok", "download_queue_eligible": True},
            "input_row": {"study_doi": "10.example/unclear", "study_title": "Unclear"},
            "adjudication": {"relevance": "relevant"},
            "verification": {"verified_supported_contexts": []},
        }

        relevant_rows = queue_rows_from_results([result, no_context], {"relevant"}, require_verified_context=True)
        download_rows = queue_rows_from_results([result, no_context], {"relevant"}, require_verified_context=False)

        self.assertEqual(len(relevant_rows), 1)
        self.assertEqual(relevant_rows[0]["compound"], "Psilocybin")
        self.assertEqual(relevant_rows[0]["publication_date"], "2025-01-02")
        self.assertEqual(relevant_rows[0]["journal_issn"], "1234-5678")
        self.assertEqual(relevant_rows[0]["funders"], "Test Funder")
        self.assertEqual(len(download_rows), 2)
        self.assertEqual(download_rows[1]["compound"], "")

    def test_flatten_result_carries_authors_and_metadata(self) -> None:
        flat = flatten_result(
            dataset="mechanistic",
            row_index=1,
            row={
                "study_doi": "10.example/test",
                "study_title": "Example",
                "study_year": "2025",
                "authors": "A. Author",
                "study_journal": "Journal",
                "publication_type": "Review",
                "publication_date": "2025-01-02",
                "abstract": "Psilocybin binds 5-HT2A.",
            },
            adjudication={
                "relevance": "relevant",
                "confidence": 0.9,
                "needs_targeted_qa": False,
                "routing_tags": ["molecular_target", "brain_system"],
            },
            status="ok",
            quote_verified=True,
            verified_contexts=[{"compound": "Psilocybin", "entity": "5-HT2A"}],
            heuristic={},
            args=fake_args(),
        )

        self.assertEqual(flat["authors"], "A. Author")
        self.assertEqual(flat["study_journal"], "Journal")
        self.assertEqual(flat["publication_type"], "Review")
        self.assertEqual(flat["publication_date"], "2025-01-02")
        self.assertEqual(flat["llm_routing_tags"], "molecular_target|brain_system")

    def test_write_csv_includes_authors_and_metadata_columns(self) -> None:
        out = Path(tempfile.gettempdir()) / "psychkg_abstract_screening_metadata.csv"
        try:
            write_csv(
                out,
                [
                    {
                        "status": "ok",
                        "dataset": "mechanistic",
                        "row_index": 1,
                        "study_doi": "10.example/test",
                        "study_title": "Example",
                        "study_year": "2025",
                        "authors": "A. Author",
                        "study_journal": "Journal",
                        "publication_type": "Review",
                    }
                ],
            )
            header = out.read_text(encoding="utf-8").splitlines()[0].split(",")
            self.assertIn("authors", header)
            self.assertIn("study_journal", header)
            self.assertIn("publication_type", header)
            self.assertIn("llm_routing_tags", header)
        finally:
            out.unlink(missing_ok=True)

    def test_print_screening_row_followup_smoke(self) -> None:
        flat = {
            "status": "ok",
            "llm_relevance": "relevant",
            "quote_verified": True,
            "download_queue_eligible": True,
        }
        print_screening_row_followup(flat, 1.25, source="llm")
        print_screening_row_followup(flat, None, source="checkpoint")
        print_screening_row_followup(
            {"status": "failed", "error": "TimeoutError: x", "llm_relevance": ""},
            0.5,
            source="llm",
        )

    def test_load_reprocess_doi_set(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as tmp:
            tmp.write("# comment\n")
            tmp.write("10.1000/alpha\n")
            tmp.write("HTTPS://doi.org/10.1000/Beta \n")
            path = Path(tmp.name)
        try:
            s = load_reprocess_doi_set(path)
            self.assertEqual(s, {"10.1000/alpha", "10.1000/beta"})
        finally:
            path.unlink(missing_ok=True)

    def test_read_doi_file_accepts_queue_csv_rows(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as tmp:
            tmp.write("# doi,compound,target\n")
            tmp.write("10.1000/alpha,Psilocybin,Depression\n")
            tmp.write("https://doi.org/10.1000/Beta\n")
            path = Path(tmp.name)
        try:
            self.assertEqual(read_doi_file(path), {"10.1000/alpha", "10.1000/beta"})
        finally:
            path.unlink(missing_ok=True)

    def test_filter_indexed_rows_can_use_doi_file_filter(self) -> None:
        rows = [
            (1, {"study_doi": "10.example/keep", "abstract": "A" * 100}),
            (2, {"study_doi": "10.example/drop", "abstract": "A" * 100}),
        ]

        filtered = filter_indexed_rows(
            rows,
            triage_by_doi={},
            args=fake_args(only_with_abstract=True),
            doi_filter={"10.example/keep"},
        )

        self.assertEqual([row_index for row_index, _row in filtered], [1])

    def test_checkpoint_jsonl_append_and_load_last_wins(self) -> None:
        out = Path(tempfile.gettempdir()) / "psychkg_fake_report.json"
        ck = default_checkpoint_jsonl_path(out)
        truncate_checkpoint(ck)
        try:
            append_checkpoint_result(ck, {"input_row": {"study_doi": "10.1/a"}, "flat": {"x": 1}})
            append_checkpoint_result(ck, {"input_row": {"study_doi": "10.1/B"}, "flat": {"x": 2}})
            loaded = load_checkpoint_results(ck)
            self.assertEqual(loaded["10.1/a"]["flat"]["x"], 1)
            self.assertEqual(loaded["10.1/b"]["flat"]["x"], 2)
            append_checkpoint_result(ck, {"input_row": {"study_doi": "10.1/b"}, "flat": {"x": 3}})
            loaded2 = load_checkpoint_results(ck)
            self.assertEqual(loaded2["10.1/b"]["flat"]["x"], 3)
        finally:
            ck.unlink(missing_ok=True)

    def test_checkpoint_result_is_incompatible_with_unknown_schema_label(self) -> None:
        compatible = {
            "flat": {"status": "ok"},
            "adjudication": {"relevance": "relevant"},
        }
        incompatible = {
            "flat": {"status": "ok"},
            "adjudication": {"relevance": "maybe"},
        }

        self.assertTrue(checkpoint_result_is_compatible(compatible))
        self.assertFalse(checkpoint_result_is_compatible(incompatible))

    def test_load_report_results_maps_existing_report_rows_by_doi(self) -> None:
        out = Path(tempfile.gettempdir()) / "psychkg_fake_screening_report.json"
        try:
            out.write_text(
                json.dumps(
                    {
                        "rows": [
                            {"input_row": {"study_doi": "10.1/A"}, "flat": {"status": "ok"}},
                            {"flat": {"study_doi": "10.1/B", "status": "ok"}},
                        ]
                    }
                ),
                encoding="utf-8",
            )

            loaded = load_report_results(out)

            self.assertEqual(set(loaded), {"10.1/a", "10.1/b"})
        finally:
            out.unlink(missing_ok=True)

    def test_merge_report_rows_adds_and_replaces_by_doi(self) -> None:
        merge = Path(tempfile.gettempdir()) / "psychkg_fake_screening_merge.json"
        try:
            merge.write_text(
                json.dumps(
                    {
                        "rows": [
                            {"input_row": {"study_doi": "10.1/B"}, "flat": {"study_doi": "10.1/B", "x": 2}},
                            {"input_row": {"study_doi": "10.1/C"}, "flat": {"study_doi": "10.1/C", "x": 3}},
                        ]
                    }
                ),
                encoding="utf-8",
            )

            rows, summary = merge_report_rows(
                [{"input_row": {"study_doi": "10.1/A"}}, {"input_row": {"study_doi": "10.1/B"}, "flat": {"x": 1}}],
                [merge],
            )

            self.assertEqual([row["input_row"]["study_doi"] for row in rows], ["10.1/A", "10.1/B", "10.1/C"])
            self.assertEqual(rows[1]["flat"]["x"], 2)
            self.assertEqual(summary["merge_report_rows_added"], 1)
            self.assertEqual(summary["merge_report_rows_replaced"], 1)
        finally:
            merge.unlink(missing_ok=True)

    def test_refresh_result_metadata_preserves_existing_screening_decision(self) -> None:
        result = {
            "input_row": {"study_doi": "10.example/test", "study_title": "Old title"},
            "flat": {
                "status": "ok",
                "study_doi": "10.example/test",
                "llm_relevance": "relevant",
                "download_queue_eligible": False,
            },
            "adjudication": {"relevance": "relevant"},
        }

        refreshed = refresh_result_metadata(
            result,
            dataset="mechanistic",
            row_index=9,
            paper_row={
                "study_doi": "10.example/test",
                "study_title": "New title",
                "study_year": "2025",
                "authors": "A. Author",
                "study_journal": "Journal",
                "publication_type": "Review",
                "abstract": "Updated abstract",
            },
        )

        self.assertEqual(refreshed["flat"]["llm_relevance"], "relevant")
        self.assertFalse(refreshed["flat"]["download_queue_eligible"])
        self.assertEqual(refreshed["flat"]["study_title"], "New title")
        self.assertEqual(refreshed["flat"]["authors"], "A. Author")
        self.assertEqual(refreshed["flat"]["study_journal"], "Journal")
        self.assertEqual(refreshed["input_row"]["publication_type"], "Review")

    def test_screen_row_dry_run_does_not_call_model(self) -> None:
        row = {
            "study_doi": "10.example/test",
            "study_title": "Psilocybin therapy for depression",
            "abstract": "Psilocybin therapy reduced depression scores.",
            "contexts": [{"compound": "Psilocybin", "entity": "Depression"}],
        }

        result = screen_row("disorder", row_index=1, row=row, heuristic={}, args=fake_args())

        self.assertEqual(result["adjudication"]["reasoning_summary"], "dry run; model was not called")
        self.assertEqual(result["flat"]["llm_relevance"], "uncertain")

    def test_screen_row_fast_exclusion_skips_full_model(self) -> None:
        row = {
            "study_doi": "10.example/test",
            "study_title": "Hemodialysis intervention for quality of life",
            "abstract": "Exercise improved quality of life in hemodialysis patients.",
            "contexts": [],
        }
        args = fake_args(dry_run=False, fast_screen_model="llama3.1:8b")

        with patch(
            "pipeline.review.run_local_llm_abstract_screening.call_ollama",
            return_value={
                "screening_action": "exclude_obvious_irrelevant",
                "confidence": 0.95,
                "supporting_quote": "Exercise improved quality of life in hemodialysis patients.",
                "reason": "different intervention and no in-scope compound",
            },
        ) as mocked:
            result = screen_row("disorder", row_index=1, row=row, heuristic={}, args=args)

        self.assertEqual(mocked.call_count, 1)
        self.assertEqual(result["flat"]["screening_path"], "fast_excluded")
        self.assertEqual(result["flat"]["llm_relevance"], "irrelevant")
        self.assertFalse(result["flat"]["download_queue_eligible"])

    def test_screen_row_deterministic_prescreen_skips_model(self) -> None:
        row = {
            "study_doi": "10.example/test",
            "study_title": "Exercise intervention for depression",
            "abstract": "This randomized trial tested an exercise program for depression symptoms in adults receiving standard outpatient mental health care.",
            "contexts": [],
        }
        args = fake_args(dry_run=False, deterministic_prescreen=True)

        with patch("pipeline.review.run_local_llm_abstract_screening.call_ollama") as mocked:
            result = screen_row("disorder", row_index=1, row=row, heuristic={}, args=args)

        mocked.assert_not_called()
        self.assertEqual(result["flat"]["screening_path"], "deterministic_excluded")
        self.assertEqual(result["flat"]["llm_relevance"], "irrelevant")
        self.assertEqual(result["flat"]["deterministic_prescreen_action"], "exclude_obvious_irrelevant")

    def test_screen_row_fast_escalation_calls_full_model(self) -> None:
        row = {
            "study_doi": "10.example/test",
            "study_title": "Psilocybin therapy for depression",
            "abstract": "Psilocybin therapy reduced depression scores.",
            "contexts": [{"compound": "Psilocybin", "entity": "Depression"}],
        }
        args = fake_args(dry_run=False, fast_screen_model="llama3.1:8b")
        responses = [
            {
                "screening_action": "escalate",
                "confidence": 0.6,
                "supporting_quote": "Psilocybin therapy for depression",
                "reason": "mentions in-scope intervention and disorder",
            },
            {
                "relevance": "relevant",
                "supporting_abstract_quote": "Psilocybin therapy reduced depression scores.",
                "confidence": 0.9,
                "needs_targeted_qa": False,
                "reasoning_summary": "in scope",
                "supported_contexts": [
                    {
                        "compound": "Psilocybin",
                        "entity": "Depression",
                        "support": "supported",
                        "supporting_quote": "Psilocybin therapy reduced depression scores.",
                        "confidence": 0.9,
                        "reason": "direct abstract support",
                    }
                ],
            },
        ]

        with patch(
            "pipeline.review.run_local_llm_abstract_screening.call_ollama",
            side_effect=responses,
        ) as mocked:
            result = screen_row("disorder", row_index=1, row=row, heuristic={}, args=args)

        self.assertEqual(mocked.call_count, 2)
        self.assertEqual(result["flat"]["screening_path"], "fast_escalated")
        self.assertEqual(result["flat"]["llm_relevance"], "relevant")


if __name__ == "__main__":
    unittest.main()
