import unittest

import pandas as pd

from pipeline.review.run_gemini_domain_routing import (
    DOMAIN_RESPONSE_SCHEMA,
    METHODOLOGICAL_VALIDITY_TAGS,
    SCREENING_DECISIONS,
    SYSTEM_INSTRUCTION,
    normalize_payload,
    parse_response_text,
    prompt_for_record,
    route_rows_from_parsed,
    selected_records,
)


class GeminiDomainRoutingTests(unittest.TestCase):
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
        self.assertIn("Likely paper type: systematic review", prompt)
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
        self.assertIn("Classify a scientific paper record into evidence domains", SYSTEM_INSTRUCTION)
        self.assertIn("Base the classification on the supplied title and abstract", SYSTEM_INSTRUCTION)
        self.assertIn("Set screening_decision after domain assignment:", SYSTEM_INSTRUCTION)
        self.assertNotIn("First decide whether", SYSTEM_INSTRUCTION)
        self.assertNotIn("title and abstract as the primary", SYSTEM_INSTRUCTION)
        self.assertNotIn("Scope and screening:", SYSTEM_INSTRUCTION)
        self.assertNotIn("Treat substances, interventions, or exposures as in scope", SYSTEM_INSTRUCTION)
        self.assertNotIn("evidence extraction", SYSTEM_INSTRUCTION)
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

    def test_methodological_validity_tags_are_valid_modifiers(self) -> None:
        self.assertIn("blinding_expectancy_validity", METHODOLOGICAL_VALIDITY_TAGS)
        self.assertIn("include_in_scope", SCREENING_DECISIONS)
        self.assertNotIn("include_for_extraction", SCREENING_DECISIONS)
        self.assertIn("exclude_out_of_scope", SCREENING_DECISIONS)
        self.assertIn("screening_decision", DOMAIN_RESPONSE_SCHEMA["properties"])
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
                "methodological_validity_tags": [],
                "rationale": "Clinical and intervention content are central.",
            }
        )

        self.assertEqual(parsed["primary_domain"], "clinical_outcome")
        self.assertEqual(parsed["domain_tags"], ["clinical_outcome", "intervention_context"])

    def test_parse_response_text_salvages_truncated_rationale_json(self) -> None:
        parsed = parse_response_text(
            '{"domain_tags":["molecular_pathway_readout","brain_system"],'
            '"primary_domain":"brain_system",'
            '"screening_decision":"include_in_scope",'
            '"screening_reason":"The abstract reports neural and molecular readouts.",'
            '"methodological_validity_tags":[],'
            '"rationale":"The model started repeating and was truncated'
        )

        self.assertEqual(parsed["domain_tags"], ["molecular_pathway_readout", "brain_system"])
        self.assertEqual(parsed["primary_domain"], "brain_system")
        self.assertEqual(parsed["screening_decision"], "include_in_scope")
        self.assertEqual(parsed["methodological_validity_tags"], [])
        self.assertEqual(parsed["rationale"], "")

    def test_route_rows_preserve_model_routing_metadata(self) -> None:
        rows = route_rows_from_parsed(
            [
                {
                    "doi": "10.example/methods",
                    "datasets": "clinical",
                    "study_title": "Blinding in psychedelic trials",
                    "study_year": "2025",
                    "source_family": "primary_or_unclear",
                    "literature_route": "primary_literature_extraction",
                    "secondary_source_types": "",
                    "primary_secondary_source_type": "",
                    "metadata_secondary_types": "",
                    "title_abstract_secondary_types": "",
                    "non_primary_flags": "",
                    "literature_type_confidence": "medium",
                    "domain_tags": ["clinical_outcome"],
                    "primary_domain": "clinical_outcome",
                    "screening_decision": "include_in_scope",
                    "screening_reason": "The title and abstract are about psychedelic clinical evidence.",
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
                    "datasets": "clinical",
                    "study_title": "Psilocybin clinical outcomes",
                    "study_year": "2025",
                    "source_family": "primary_or_unclear",
                    "literature_route": "primary_literature_extraction",
                    "secondary_source_types": "",
                    "primary_secondary_source_type": "",
                    "metadata_secondary_types": "",
                    "title_abstract_secondary_types": "",
                    "non_primary_flags": "",
                    "literature_type_confidence": "medium",
                    "domain_tags": ["clinical_outcome"],
                    "primary_domain": "clinical_outcome",
                    "screening_decision": "include_for_extraction",
                    "screening_reason": "Legacy model output.",
                    "methodological_validity_tags": [],
                    "rationale": "Clinical outcome evidence is central.",
                    "model": "gemini-3-flash-preview",
                }
            ],
            generated_at_utc="2026-05-29T00:00:00+00:00",
        )

        self.assertEqual(rows[0]["screening_decision"], "include_in_scope")

    def test_route_rows_preserve_exclusion_screening_decision(self) -> None:
        rows = route_rows_from_parsed(
            [
                {
                    "doi": "10.example/out",
                    "datasets": "clinical",
                    "study_title": "Non-psychedelic paper",
                    "study_year": "2025",
                    "source_family": "primary_or_unclear",
                    "literature_route": "primary_literature_extraction",
                    "secondary_source_types": "",
                    "primary_secondary_source_type": "",
                    "metadata_secondary_types": "",
                    "title_abstract_secondary_types": "",
                    "non_primary_flags": "",
                    "literature_type_confidence": "medium",
                    "domain_tags": [],
                    "primary_domain": "general_topic",
                    "screening_decision": "exclude_out_of_scope",
                    "screening_reason": "No in-scope psychedelic evidence in the abstract.",
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
                    "dataset": "mechanistic",
                    "prescreen_decision": "retain",
                    "retained_for_extraction_candidate": False,
                },
                {
                    "doi": "10.example/extract",
                    "dataset": "mechanistic",
                    "prescreen_decision": "retain",
                    "retained_for_extraction_candidate": True,
                },
            ]
        )

        records = selected_records(
            metadata,
            prescreen,
            pd.DataFrame(),
            scoped_dois=set(),
            limit=0,
            completed=set(),
        )

        self.assertEqual([record["doi"] for record in records], ["10.example/extract"])


if __name__ == "__main__":
    unittest.main()
