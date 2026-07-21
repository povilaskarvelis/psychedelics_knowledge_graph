import unittest

import pandas as pd

from pipeline.review.run_gemini_domain_routing import (
    DOMAIN_RESPONSE_SCHEMA,
    METHODOLOGICAL_VALIDITY_TAGS,
    SCREENING_PROMPT_PATH,
    SCREENING_DECISIONS,
    SYSTEM_INSTRUCTION,
    normalize_payload,
    parse_response_text,
    prompt_for_record,
    route_rows_from_parsed,
    selected_records,
)


class GeminiDomainRoutingTests(unittest.TestCase):
    def test_system_instruction_is_loaded_from_standalone_prompt(self) -> None:
        self.assertTrue(SCREENING_PROMPT_PATH.is_file())
        self.assertEqual(
            SYSTEM_INSTRUCTION,
            SCREENING_PROMPT_PATH.read_text(encoding="utf-8").strip(),
        )

    def test_prompt_includes_compact_context_metadata(self) -> None:
        prompt = prompt_for_record(
            {
                "doi": "10.example/review",
                "study_title": "Psilocybin therapy: a systematic review",
                "study_year": "2026",
                "publication_type": "Journal Article | Systematic Review",
                "source_family": "secondary_literature",
                "literature_route": "secondary_literature_extraction",
                "primary_secondary_source_type": "systematic_review",
                "secondary_source_types": "systematic_review|review",
                "metadata_secondary_types": "systematic_review",
                "title_abstract_secondary_types": "systematic_review",
                "non_primary_flags": "",
                "literature_type_confidence": "high",
                "mesh_terms": "Psilocybin | Humans | Treatment Outcome",
                "keywords": "psychedelic therapy",
                "abstract": "This systematic review synthesizes clinical outcomes.",
            }
        )

        self.assertIn("Context metadata:", prompt)
        self.assertNotIn("Likely paper type:", prompt)
        self.assertIn("Publication labels: Journal Article | Systematic Review", prompt)
        self.assertNotIn("Corpus literature route:", prompt)
        self.assertNotIn("Derived paper-type label:", prompt)
        self.assertNotIn("Derived secondary type:", prompt)
        self.assertNotIn("All secondary type labels:", prompt)
        self.assertNotIn("Secondary labels from publication metadata:", prompt)
        self.assertNotIn("Secondary labels from title/abstract rules:", prompt)
        self.assertNotIn("Non-primary publication flags:", prompt)
        self.assertIn("MeSH terms: Psilocybin | Humans | Treatment Outcome", prompt)
        self.assertTrue(prompt.startswith("Paper record:\n"))
        self.assertNotIn("Evidence domain options:", prompt)
        self.assertNotIn("Scope and screening:", prompt)
        self.assertNotIn("Return only compact JSON", prompt)
        self.assertIn("Evidence domain options:", SYSTEM_INSTRUCTION)
        self.assertIn("Classify a scientific paper record by scope, evidence domain, and paper type", SYSTEM_INSTRUCTION)
        self.assertIn("Base the classification on the supplied title and abstract", SYSTEM_INSTRUCTION)
        self.assertIn("these metadata can\nbe incomplete or misleading", SYSTEM_INSTRUCTION)
        self.assertIn("Set paper_type_group, paper_type, and paper_type_labels as follows:", SYSTEM_INSTRUCTION)
        self.assertIn("Set screening_decision after domain and paper-type assignment:", SYSTEM_INSTRUCTION)
        self.assertNotIn("First decide whether", SYSTEM_INSTRUCTION)
        self.assertNotIn("title and abstract as the primary", SYSTEM_INSTRUCTION)
        self.assertNotIn("Scope and screening:", SYSTEM_INSTRUCTION)
        self.assertNotIn("Treat substances, interventions, or exposures as in scope", SYSTEM_INSTRUCTION)
        self.assertNotIn("evidence extraction", SYSTEM_INSTRUCTION)
        self.assertNotIn("for extraction", SYSTEM_INSTRUCTION)
        self.assertNotIn("routing label", SYSTEM_INSTRUCTION)
        self.assertNotIn("corpus evidence", SYSTEM_INSTRUCTION)
        self.assertNotIn("closed compound list", SYSTEM_INSTRUCTION)
        self.assertNotIn("Set confidence", SYSTEM_INSTRUCTION)
        self.assertNotIn("needs_human_review", SYSTEM_INSTRUCTION)
        self.assertIn('"general_topic" is not a catch-all for out-of-scope records', SYSTEM_INSTRUCTION)
        self.assertNotIn("Set screening_decision to one of:", SYSTEM_INSTRUCTION)
        self.assertIn("Set domain_tags and primary_domain as follows:", SYSTEM_INSTRUCTION)
        self.assertNotIn("one paper at a time", SYSTEM_INSTRUCTION)
        self.assertNotIn("You receive one paper record", SYSTEM_INSTRUCTION)
        self.assertNotIn("KG", SYSTEM_INSTRUCTION)
        self.assertNotIn("routing tags", SYSTEM_INSTRUCTION)
        self.assertIn("Bibliometric, scientometric, citation-network", SYSTEM_INSTRUCTION)
        self.assertIn('usually as paper_type\n  "review"', SYSTEM_INSTRUCTION)

    def test_methodological_validity_tags_are_valid_modifiers(self) -> None:
        self.assertIn("blinding_expectancy_validity", METHODOLOGICAL_VALIDITY_TAGS)
        self.assertIn("include_in_scope", SCREENING_DECISIONS)
        self.assertNotIn("include_for_extraction", SCREENING_DECISIONS)
        self.assertIn("exclude_out_of_scope", SCREENING_DECISIONS)
        self.assertIn("screening_decision", DOMAIN_RESPONSE_SCHEMA["properties"])
        self.assertIn("paper_type_group", DOMAIN_RESPONSE_SCHEMA["properties"])
        self.assertIn("paper_type", DOMAIN_RESPONSE_SCHEMA["properties"])
        self.assertIn("paper_type_labels", DOMAIN_RESPONSE_SCHEMA["properties"])
        self.assertIn("paper_type_reason", DOMAIN_RESPONSE_SCHEMA["properties"])
        self.assertNotIn("confidence", DOMAIN_RESPONSE_SCHEMA["properties"])
        self.assertNotIn("needs_human_review", DOMAIN_RESPONSE_SCHEMA["properties"])
        self.assertNotIn("confidence", DOMAIN_RESPONSE_SCHEMA["required"])
        self.assertNotIn("needs_human_review", DOMAIN_RESPONSE_SCHEMA["required"])
        self.assertIn(
            "blinding_expectancy_validity",
            DOMAIN_RESPONSE_SCHEMA["properties"]["methodological_validity_tags"]["items"]["enum"],
        )

    def test_general_topic_primary_is_normalized_when_specific_tags_exist(self) -> None:
        parsed = normalize_payload(
            {
                "domain_tags": ["clinical_outcome", "intervention_context"],
                "primary_domain": "general_topic",
                "screening_decision": "include_in_scope",
                "screening_reason": "Psychedelic-assisted therapy overview.",
                "paper_type_group": "secondary_literature",
                "paper_type": "review",
                "paper_type_labels": ["review"],
                "paper_type_reason": "The record synthesizes evidence.",
                "methodological_validity_tags": [],
                "rationale": "Clinical and intervention content are central.",
            }
        )

        self.assertEqual(parsed["primary_domain"], "clinical_outcome")
        self.assertEqual(parsed["domain_tags"], ["clinical_outcome", "intervention_context"])

    def test_parse_response_text_rejects_truncated_json(self) -> None:
        with self.assertRaises(ValueError):
            parse_response_text(
                '{"domain_tags":["molecular_pathway_readout","brain_system"],'
                '"primary_domain":"brain_system",'
                '"screening_decision":"include_in_scope",'
                '"screening_reason":"The abstract reports neural and molecular readouts.",'
                '"paper_type_group":"primary",'
                '"paper_type":"primary",'
                '"paper_type_labels":["primary"],'
                '"paper_type_reason":"The abstract reports original readouts.",'
                '"methodological_validity_tags":[],'
                '"rationale":"The model started repeating and was truncated'
            )

    def test_parse_response_text_rejects_missing_required_fields(self) -> None:
        with self.assertRaisesRegex(ValueError, "missing required fields"):
            parse_response_text('{"domain_tags": [], "primary_domain": "general_topic"}')

    def test_prompt_preserves_complete_validated_abstract(self) -> None:
        abstract = "BEGINNING " + ("middle " * 1000) + " FINAL CONCLUSION"
        prompt = prompt_for_record(
            {
                "doi": "10.example/long",
                "study_title": "A long structured abstract",
                "study_year": "2026",
                "publication_type": "Journal Article",
                "mesh_terms": "",
                "keywords": "",
                "abstract": abstract,
            }
        )

        self.assertIn("Abstract: BEGINNING", prompt)
        self.assertNotIn("[middle truncated]", prompt)
        self.assertIn("middle middle middle", prompt)
        self.assertIn("FINAL CONCLUSION", prompt)

    def test_invalid_screening_decision_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unsupported screening decision"):
            normalize_payload(
                {
                    "domain_tags": ["clinical_outcome"],
                    "primary_domain": "clinical_outcome",
                    "screening_decision": "",
                    "paper_type_group": "primary",
                    "paper_type": "primary",
                }
            )

    def test_route_rows_preserve_model_routing_metadata(self) -> None:
        rows = route_rows_from_parsed(
            [
                {
                    "doi": "10.example/methods",
                    "study_title": "Blinding in psychedelic trials",
                    "study_year": "2025",
                    "domain_tags": ["clinical_outcome"],
                    "primary_domain": "clinical_outcome",
                    "screening_decision": "include_in_scope",
                    "screening_reason": "The title and abstract are about psychedelic clinical evidence.",
                    "paper_type_group": "primary",
                    "paper_type": "primary",
                    "paper_type_labels": ["primary"],
                    "paper_type_reason": "Original clinical evidence.",
                    "methodological_validity_tags": ["blinding_expectancy_validity"],
                    "rationale": "The abstract evaluates blinding validity.",
                    "model": "gemini-3-flash-preview",
                }
            ],
            generated_at_utc="2026-05-29T00:00:00+00:00",
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["domain_route"], "clinical_outcome")
        self.assertEqual(rows[0]["primary_domain"], "clinical_outcome")
        self.assertEqual(rows[0]["paper_type_group"], "primary")
        self.assertEqual(rows[0]["paper_type"], "primary")
        self.assertEqual(rows[0]["source_family"], "primary")
        self.assertEqual(rows[0]["screening_decision"], "include_in_scope")
        self.assertEqual(rows[0]["screening_reason"], "The title and abstract are about psychedelic clinical evidence.")
        self.assertEqual(rows[0]["methodological_validity_tags"], "blinding_expectancy_validity")
        self.assertEqual(rows[0]["model"], "gemini-3-flash-preview")
        self.assertNotIn("domain_route_confidence", rows[0])
        self.assertNotIn("needs_human_review", rows[0])

    def test_legacy_include_for_extraction_maps_to_scope_decision(self) -> None:
        rows = route_rows_from_parsed(
            [
                {
                    "doi": "10.example/legacy",
                    "study_title": "Psilocybin clinical outcomes",
                    "study_year": "2025",
                    "domain_tags": ["clinical_outcome"],
                    "primary_domain": "clinical_outcome",
                    "screening_decision": "include_for_extraction",
                    "screening_reason": "Legacy model output.",
                    "paper_type_group": "secondary_literature",
                    "paper_type": "systematic_review",
                    "paper_type_labels": ["systematic_review"],
                    "paper_type_reason": "Systematic review label.",
                    "methodological_validity_tags": [],
                    "rationale": "Clinical outcome evidence is central.",
                    "model": "gemini-3-flash-preview",
                }
            ],
            generated_at_utc="2026-05-29T00:00:00+00:00",
        )

        self.assertEqual(rows[0]["screening_decision"], "include_in_scope")
        self.assertEqual(rows[0]["source_family"], "secondary_literature")
        self.assertEqual(rows[0]["primary_secondary_source_type"], "systematic_review")

    def test_meta_analysis_can_keep_systematic_review_label(self) -> None:
        rows = route_rows_from_parsed(
            [
                {
                    "doi": "10.example/meta",
                    "study_title": "Psilocybin for depression: systematic review and meta-analysis",
                    "study_year": "2025",
                    "domain_tags": ["clinical_outcome"],
                    "primary_domain": "clinical_outcome",
                    "screening_decision": "include_in_scope",
                    "screening_reason": "The abstract synthesizes clinical outcome evidence.",
                    "paper_type_group": "secondary_literature",
                    "paper_type": "meta_analysis",
                    "paper_type_labels": ["systematic_review", "meta_analysis"],
                    "paper_type_reason": "The title states systematic review and meta-analysis.",
                    "methodological_validity_tags": [],
                    "rationale": "Clinical synthesis.",
                    "model": "gemini-3-flash-preview",
                }
            ],
            generated_at_utc="2026-05-29T00:00:00+00:00",
        )

        self.assertEqual(rows[0]["paper_type"], "meta_analysis")
        self.assertEqual(rows[0]["paper_type_labels"], "systematic_review|meta_analysis")
        self.assertEqual(rows[0]["primary_secondary_source_type"], "meta_analysis")
        self.assertEqual(rows[0]["secondary_source_types"], "systematic_review|meta_analysis|review")

    def test_route_rows_preserve_exclusion_screening_decision(self) -> None:
        rows = route_rows_from_parsed(
            [
                {
                    "doi": "10.example/out",
                    "study_title": "Non-psychedelic paper",
                    "study_year": "2025",
                    "domain_tags": [],
                    "primary_domain": "general_topic",
                    "screening_decision": "exclude_out_of_scope",
                    "screening_reason": "No in-scope psychedelic evidence in the abstract.",
                    "paper_type_group": "non_primary_publication",
                    "paper_type": "protocol",
                    "paper_type_labels": ["protocol"],
                    "paper_type_reason": "Protocol without results.",
                    "methodological_validity_tags": [],
                    "rationale": "Out of scope.",
                    "model": "gemini-3-flash-preview",
                }
            ],
            generated_at_utc="2026-05-29T00:00:00+00:00",
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["domain_route"], "general_topic")
        self.assertFalse(rows[0]["retained_for_extraction_candidate"])
        self.assertEqual(rows[0]["screening_decision"], "exclude_out_of_scope")
        self.assertEqual(rows[0]["screening_reason"], "No in-scope psychedelic evidence in the abstract.")
        self.assertEqual(rows[0]["source_family"], "non_primary_publication")
        self.assertEqual(rows[0]["non_primary_flags"], "protocol")

    def test_selected_records_uses_extraction_candidate_flag_over_prescreen_retention(self) -> None:
        metadata = pd.DataFrame(
            [
                {
                    "doi": "10.example/provenance-only",
                    "study_title": "",
                    "abstract": "Psilocybin appears in an attached abstract.",
                },
                {
                    "doi": "10.example/extract",
                    "study_title": "Psilocybin paper",
                    "abstract": "Psilocybin was studied.",
                },
            ]
        )
        prescreen = pd.DataFrame(
            [
                {
                    "doi": "10.example/provenance-only",
                    "prescreen_decision": "retain",
                    "retained_for_extraction_candidate": False,
                },
                {
                    "doi": "10.example/extract",
                    "prescreen_decision": "retain",
                    "retained_for_extraction_candidate": True,
                },
            ]
        )

        records = selected_records(
            metadata,
            prescreen,
            scoped_dois=set(),
            limit=0,
            completed=set(),
        )

        self.assertEqual([record["doi"] for record in records], ["10.example/extract"])

    def test_selected_records_trusts_prescreen_retention(self) -> None:
        metadata = pd.DataFrame(
            [
                {
                    "doi": "10.example/keep",
                    "study_title": "Psilocybin paper",
                    "abstract": "Psilocybin was studied.",
                    "publication_type": "Journal Article",
                },
                {
                    "doi": "10.31219/osf.io/dy5cu_v1",
                    "study_title": "Legal and Regulatory Barriers to Medical Psilocybin Use",
                    "abstract": "This overview discusses medical psilocybin regulation.",
                    "publication_type": "article",
                },
                {
                    "doi": "10.3389/fnins.2025.1554049.s002",
                    "study_title": "Table 2_Dose-dependent changes in brain activity following psilocybin.xlsx",
                    "abstract": "Dose-dependent brain activity and connectivity are reported.",
                    "publication_type": "dataset",
                },
                {
                    "doi": "10.64898/2026.04.16.718915",
                    "study_title": "Serotonergic Polypharmacology of 2-Halogenated Tryptamines",
                    "abstract": "Novel tryptamines were tested.",
                    "publication_type": "Journal Article | Preprint",
                },
            ]
        )
        prescreen = pd.DataFrame(
            [
                {
                    "doi": "10.example/keep",
                    "prescreen_decision": "retain",
                    "retained_for_extraction_candidate": True,
                },
                {
                    "doi": "10.31219/osf.io/dy5cu_v1",
                    "prescreen_decision": "exclude",
                    "retained_for_extraction_candidate": False,
                    "prescreen_action": "exclude_preprint_or_unpublished",
                },
                {
                    "doi": "10.3389/fnins.2025.1554049.s002",
                    "prescreen_decision": "exclude",
                    "retained_for_extraction_candidate": False,
                    "prescreen_action": "exclude_non_evidence_artifact",
                },
                {
                    "doi": "10.64898/2026.04.16.718915",
                    "prescreen_decision": "exclude",
                    "retained_for_extraction_candidate": False,
                    "prescreen_action": "exclude_preprint_or_unpublished",
                },
            ]
        )

        records = selected_records(
            metadata,
            prescreen,
            scoped_dois=set(),
            limit=0,
            completed=set(),
        )

        self.assertEqual([record["doi"] for record in records], ["10.example/keep"])


if __name__ == "__main__":
    unittest.main()
