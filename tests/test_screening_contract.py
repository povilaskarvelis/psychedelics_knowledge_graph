import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pipeline.review import screening_contract as c
from pipeline.review.run_domain_routing import parse_response_text
from pipeline.review.run_screening_correction import hard_precheck, prepare_stage


def record():
    return {"doi": "10.example/test", "study_title": "LSD and heart rate", "study_year": "2025", "abstract": "LSD increased heart rate in healthy volunteers.", "publication_type": "Journal Article", "language": "eng"}


def payload():
    return {"domain_tags": ["safety_tolerability"], "primary_domain": "safety_tolerability", "screening_decision": "include_in_scope", "screening_reason": "The study directly tests LSD effects in healthy volunteers.", "paper_type_group": "primary", "paper_type": "primary", "paper_type_labels": ["primary"], "paper_type_reason": "An original drug experiment.", "methodological_validity_tags": [], "rationale": "An eligible drug-specific result.", "eligibility": {"basis": "drug_effect_or_mechanism", "substances": [{"name": "LSD", "scope_class": "classic_psychedelic", "source_quote": "LSD increased heart rate"}], "finding_quote": "LSD increased heart rate in healthy volunteers.", "input_integrity": "consistent"}}


class ScreeningContractTests(unittest.TestCase):
    def test_quote_normalization_keeps_scientific_inequalities(self):
        source = "p < 0.05). Ketamine increased dopamine. F(1,3) > 6.8."
        self.assertIn("ketamine increased dopamine", c.text_key(source))
        self.assertEqual(c.text_key("a<b and c>d"), "a<b and c>d")
        self.assertIn("< 0.05", c.text_key(source))
        self.assertIn("> 6.8", c.text_key(source))

    def test_publisher_markup_is_removed_without_erasing_results(self):
        self.assertEqual(c.text_key('<h3 class="heading">Results</h3> <i>PCP</i> <sup>3</sup>'), "results pcp 3")
        self.assertEqual(c.text_key('<jats:p>p &lt; 0.05; <jats:italic>PCP</jats:italic> increased release.</jats:p>'), "p < 0.05; pcp increased release.")
        self.assertEqual(c.text_key("p &lt; 0.05 and F &gt; 6.8"), "p < 0.05 and f > 6.8")

    def test_valid_drug_result_has_locatable_evidence(self):
        p = payload()
        c.validate_schema(p, c.V6)
        self.assertEqual(c.validate_record(p, record()), [])

    def test_invented_scope_for_ordinary_drugs_is_quarantined(self):
        for drug in ["fluoxetine", "methamphetamine", "morphine", "THC", "CBD", "TS-121", "deutetrabenazine"]:
            with self.subTest(drug=drug):
                p, r = payload(), record()
                r["study_title"] = drug + " effects"
                r["abstract"] = drug + " increased heart rate in healthy volunteers."
                p["eligibility"]["substances"][0].update(name=drug, source_quote=r["study_title"])
                p["eligibility"]["finding_quote"] = r["abstract"]
                issues = c.validate_record(p, r)
                self.assertIn("out_of_scope_substance_claim", issues)
                self.assertIn("no_verified_eligible_substance", issues)

    def test_mixed_drug_result_is_not_rejected_by_cannabis_keyword(self):
        p, r = payload(), record()
        r["abstract"] += " Cannabis co-use was also recorded."
        self.assertEqual(c.validate_record(p, r), [])

    def test_excluded_co_drug_in_evidence_does_not_veto_valid_inclusion(self):
        p, r = payload(), record()
        r["abstract"] += " Cannabis co-use was recorded."
        p["eligibility"]["substances"].append({"name": "cannabis", "scope_class": "out_of_scope", "source_quote": "Cannabis co-use"})
        self.assertEqual(c.validate_record(p, r), [])

    def test_v6_parser_validates_evidence_and_keeps_review_out_of_binary_routes(self):
        self.assertEqual(parse_response_text(json.dumps(payload()), profile=c.V6, record=record()), payload())
        p = payload()
        p.update(screening_decision="needs_review", domain_tags=[], primary_domain="general_topic")
        p["eligibility"]["basis"] = "uncertain"
        with self.assertRaisesRegex(ValueError, "model_requested_review"):
            parse_response_text(json.dumps(p), profile=c.V6, record=record())

    def test_v6_batch_manifest_freezes_profile_and_source_for_later_validation(self):
        from argparse import Namespace
        from pipeline.review.run_domain_routing_batch import write_batch_requests_for_records
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            args = Namespace(batch_input_jsonl=str(root/"in.jsonl"), manifest_json=str(root/"manifest.json"), model="gpt-6-luna", env_file=str(root/"missing.env"), metadata_table=str(root/"meta.parquet"), prescreen_decisions_table=str(root/"pre.parquet"), raw_jsonl=str(root/"raw.jsonl"), doi_file="", start_index=1, limit=1, temperature=0, max_output_tokens=3072, thinking_budget=0, screening_profile=c.V6)
            manifest = write_batch_requests_for_records(args, [record()])
            body = json.loads((root/"in.jsonl").read_text())["body"]
            self.assertEqual(manifest["inputs"]["screening_profile"], c.V6)
            self.assertEqual(manifest["records"][0]["source_record"], record())
            self.assertIn("eligibility", body["text"]["format"]["schema"]["properties"])

    def test_later_review_hold_cannot_resurrect_older_inclusion(self):
        import pandas as pd
        from pipeline.review.run_domain_routing import parsed_rows_from_raw, completed_dois
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"raw.jsonl"
            old = payload(); old.pop("eligibility")
            raw = [{"doi":record()["doi"], "model":"gpt-6-luna", "status":"ok", "parsed":old}, {"doi":record()["doi"], "model":"gpt-6-luna", "status":"error", "screening_profile":c.V6, "error":"model_requested_review"}]
            path.write_text("".join(json.dumps(r)+"\n" for r in raw))
            self.assertEqual(parsed_rows_from_raw(path, pd.DataFrame([record()]), pd.DataFrame()), [])
            self.assertEqual(completed_dois(path, c.V6), set())
            raw[0]["screening_profile"] = c.V6
            path.write_text("".join(json.dumps(r)+"\n" for r in raw))
            self.assertEqual(completed_dois(path, c.V6), set())

    def test_future_generation_uses_validated_active_profile(self):
        from argparse import Namespace
        from pipeline.review.run_domain_routing import generation_config
        with patch.object(c, "active_profile", return_value=c.V6):
            config = generation_config(Namespace(max_output_tokens=3072))
        self.assertIn("eligibility", config["schema"]["properties"])

    def test_unfamiliar_compound_is_held_never_auto_excluded(self):
        p, r = payload(), record()
        p["eligibility"]["substances"][0]["name"] = "unfamiliar tryptamine"
        self.assertIn("unfamiliar_substance_requires_review", c.validate_record(p, r))
        self.assertEqual(p["screening_decision"], "include_in_scope")

    def test_documented_psychedelic_class_names_are_valid_but_generic_tryptamines_are_not(self):
        for name in ["Psychedelic phenethylamines", "Phencyclidine-like dissociatives"]:
            p, r = payload(), record()
            r.update(study_title=name, abstract=name + " are reviewed for their effects.")
            p["eligibility"]["substances"][0].update(name=name, source_quote=name)
            p["eligibility"]["finding_quote"] = r["abstract"]
            self.assertEqual(c.validate_record(p, r), [])
        p = payload()
        p["eligibility"]["substances"][0].update(name="Tryptamine derivatives", source_quote="LSD")
        self.assertIn("unfamiliar_substance_requires_review", c.validate_record(p, record()))

    def test_known_pcp_and_expanded_synonym_are_accepted(self):
        p, r = payload(), record()
        r.update(study_title="Phencyclidine effects", abstract="Phencyclidine increased immobility in mice.")
        p["eligibility"]["substances"][0].update(name="phencyclidine (PCP)", scope_class="dissociative_hallucinogen", source_quote="Phencyclidine effects")
        p["eligibility"]["finding_quote"] = r["abstract"]
        self.assertEqual(c.validate_record(p, r), [])

    def test_same_drug_alias_groups_and_salts_resolve_without_new_scope(self):
        cases = [("MDMA/ecstasy", "mdma"), ("Ecstasy/MDMA", "mdma"),
                 ("Ketamine hydrochloride", "ketamine"),
                 ("Ketamine/esketamine", "ketamine"),
                 ("Ketamine and esketamine", "ketamine")]
        for label, parent in cases:
            with self.subTest(label=label):
                key = c.substance_name_key(label)
                self.assertEqual(c.known_substances()[key], parent)
        for label in ["LSD/cannabis", "ketamine/novel analogue",
                      "dexoxadrol homologues", "hydroxyketamine", "ketamine-like hydrochloride"]:
            with self.subTest(label=label):
                self.assertNotIn(c.substance_name_key(label), c.known_substances())

    def test_alias_resolution_still_requires_locatable_substance_evidence(self):
        p, r = payload(), record()
        r.update(study_title="MDMA effects", abstract="MDMA increased heart rate.")
        p["eligibility"]["substances"][0].update(name="MDMA/ecstasy", source_quote="MDMA")
        p["eligibility"]["finding_quote"] = r["abstract"]
        self.assertEqual(c.validate_record(p, r), [])
        p["eligibility"]["substances"][0]["source_quote"] = "LSD"
        self.assertIn("substance_quote_not_in_record", c.validate_record(p, r))

    def test_explicit_prompt_class_aliases_are_not_unfamiliar_compounds(self):
        for label in ["Classic serotonergic psychedelics", "Hallucinogen use (class)",
                      "NBOMe compounds", "α-methyltryptamine", "MMDA"]:
            with self.subTest(label=label):
                self.assertIn(c.substance_name_key(label), c.known_substances())

    def test_pcp_primary_care_acronym_is_not_a_psychedelic(self):
        p, r = payload(), record()
        r.update(study_title="PCP referrals", abstract="PCP referrals improved follow-up in primary care.")
        p["eligibility"]["substances"][0].update(name="PCP", source_quote="PCP referrals")
        p["eligibility"]["finding_quote"] = r["abstract"]
        self.assertIn("ambiguous_pcp_acronym", c.validate_record(p, r))

    def test_lumpy_skin_disease_and_malondialdehyde_acronyms_are_held(self):
        for name, abstract, flag in [("LSD", "LSD means lumpy skin disease in cattle.", "ambiguous_lsd_acronym"), ("MDA", "MDA measures malondialdehyde in cells.", "ambiguous_mda_acronym")]:
            p, r = payload(), record()
            r.update(study_title=abstract, abstract=abstract)
            p["eligibility"]["substances"][0].update(name=name, source_quote=abstract)
            p["eligibility"]["finding_quote"] = abstract
            self.assertIn(flag, c.validate_record(p, r))

    def test_fabricated_or_paraphrased_quotes_are_rejected(self):
        p = payload()
        p["eligibility"]["finding_quote"] = "LSD cured depression."
        self.assertIn("finding_quote_not_in_record", c.validate_record(p, record()))

    def test_exclusion_basis_cannot_accompany_inclusion(self):
        p = payload()
        p["eligibility"]["basis"] = "analytical_detection_only"
        self.assertIn("decision_basis_contradiction", c.validate_record(p, record()))

    def test_ts121_style_contradiction_is_rejected_by_legacy_parser_too(self):
        p = payload()
        p.pop("eligibility")
        p["screening_reason"] = "TS-121 is not eligible, so this record is excluded from scope."
        with self.assertRaisesRegex(ValueError, "decision_rationale_contradiction"):
            parse_response_text(json.dumps(p))

    def test_reference_to_other_excluded_papers_is_not_a_contradiction(self):
        p = payload()
        p["screening_reason"] = "Unlike excluded anesthesia studies, this study directly tests LSD."
        self.assertEqual(c.validate_record(p, record()), [])

    def test_metadata_conflict_is_held(self):
        p = payload()
        p["eligibility"]["input_integrity"] = "conflicting"
        self.assertIn("metadata_identity_conflict", c.validate_record(p, record()))

    def test_sperm_motility_is_not_cognitive_behavior(self):
        p, r = payload(), record()
        r["abstract"] = "LSD modified sperm motility in vitro."
        p["domain_tags"] = ["cognitive_behavioral"]
        p["primary_domain"] = "cognitive_behavioral"
        p["eligibility"]["finding_quote"] = r["abstract"]
        self.assertIn("cell_motility_is_not_cognitive_behavior", c.validate_record(p, r))

    def test_explicit_publisher_format_overrides_generic_article_metadata(self):
        r = record()
        r["verified_observation"] = {"publication_format": "conference_abstract", "evidence": "Publisher says Conference abstract"}
        self.assertEqual(hard_precheck(r)["basis"], "ineligible_publication")

    def test_verified_english_full_article_is_not_a_cleanup_exclusion(self):
        r = record()
        r["verified_observation"] = {"publication_format":"full_article", "language":"en", "evidence":"Publisher metadata"}
        self.assertIsNone(hard_precheck(r))

    def test_verified_proceedings_and_digest_doi_families_are_excluded(self):
        for doi in ["10.1093/jsxmed/qdag002.118", "10.1093/pch/19.6.e35-20", "10.1056/jp201004160000003", "10.1097/01.aoa.0000542365.09825.47", "10.5860/choice.34-6310"]:
            r = {**record(), "doi":doi}
            self.assertEqual(hard_precheck(r)["basis"], "ineligible_publication")
        self.assertIsNone(hard_precheck({**record(), "doi":"10.1056/nejmoa000001"}))

    def test_german_source_with_translated_title_is_excluded(self):
        r = record()
        r["verified_observation"] = {"language": "de", "evidence": "Source article is German"}
        self.assertEqual(hard_precheck(r)["basis"], "non_english_source")

    def test_missing_language_alone_is_not_an_exclusion(self):
        r = record()
        r["language"] = ""
        self.assertIsNone(hard_precheck(r))

    def test_unresolved_identity_never_becomes_scope_exclusion(self):
        r = record()
        r["identity_hold"] = "Foreign abstract"
        self.assertEqual(hard_precheck(r)["status"], "metadata_hold")

    def test_batch_parts_obey_real_utf8_bytes_and_use_unique_ids(self):
        from pipeline import llm
        from pipeline.review.run_screening_correction import save, read, fingerprint
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prompt = c.ROOT / "docs/screening/title_abstract_screening_v6.md"
            save(root / "run.json", {"hashes": {"prompt": fingerprint(prompt)}, "stages": {}})
            records = [{**record(), "doi": "10.example/" + str(i), "abstract": "LSD changed mood. " + "é" * 80} for i in range(5)]
            one_size = len((json.dumps(llm.batch_line("pilot-" + __import__("hashlib").sha256(records[0]["doi"].encode()).hexdigest()[:20], __import__("pipeline.review.run_screening_correction", fromlist=["request"]).request(records[0])), ensure_ascii=False) + "\n").encode())
            stage = prepare_stage(root, "pilot", records, max_bytes=one_size * 2 + 10)
            self.assertEqual(stage["requests"], 5)
            self.assertEqual(len(stage["parts"]), 3)
            keys = []
            for part in stage["parts"]:
                self.assertLessEqual(Path(part["requests_path"]).stat().st_size, one_size * 2 + 10)
                keys.extend(a["key"] for a in read(part["manifest_path"])["records"])
            self.assertEqual(len(set(keys)), 5)

    def test_main_transport_refuses_submission_before_validation(self):
        from pipeline.review.run_screening_correction import advance_stage, save
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            save(root / "run.json", {"stages": {"main": {"parts": []}}, "validation": {"status": "requires_review"}})
            with self.assertRaisesRegex(ValueError, "requires a passed"):
                advance_stage(root, "main", submit=True)


if __name__ == "__main__":
    unittest.main()
