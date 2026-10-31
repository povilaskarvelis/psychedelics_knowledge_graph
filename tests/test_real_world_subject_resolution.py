import copy
import unittest

from pipeline.kg.convert_routed_extractions_to_evidence_rows import apply_graph_subject, evidence_row_for_item
from pipeline.kg.real_world_subjects import resolve_real_world_measure_subject


def example(**updates):
    row = {
        "domain": "real_world_public_health",
        "compound": "Sexual minority status, compared with non-sexual minority status",
        "exposure_or_policy": "Sexual minority status, compared with non-sexual minority status",
        "public_health_measure": "Self-reported hallucinogen use",
        "finding_summary": "Sexual minority respondents were more likely than non-sexual minorities to report hallucinogen use.",
        "evidence_location": "Abstract",
    }
    row.update(updates)
    return row


class RealWorldSubjectResolutionTest(unittest.TestCase):
    def test_demographic_predictor_becomes_explicit_measured_class(self):
        row = example()
        original = copy.deepcopy(row)
        apply_graph_subject(row)
        self.assertEqual(row["compound"], "Hallucinogens")
        self.assertEqual(row["graph_subject_kind"], "compound_class")
        self.assertEqual(row["graph_subject_source_field"], "public_health_measure")
        for field in ("exposure_or_policy", "public_health_measure", "finding_summary"):
            self.assertEqual(row[field], original[field])
        self.assertEqual(row["real_world_original_graph_subject"], original["compound"])

    def test_availability_predictor_retains_ecstasy_price_result(self):
        row = example(
            compound="Drug availability category", exposure_or_policy="Drug availability category",
            public_health_measure="Reported retail price of an ecstasy pill in relation to drug availability",
            finding_summary="Higher reported availability was associated with 5% lower ecstasy pill prices.",
            estimate_value="5% lower price per higher availability category",
        )
        apply_graph_subject(row)
        self.assertEqual(row["compound"], "MDMA")
        self.assertEqual(row["estimate_value"], "5% lower price per higher availability category")
        self.assertEqual(row["graph_subject_kind"], "atomic_compound")

    def test_replay_is_idempotent_and_preserves_predictor_provenance(self):
        row = example()
        apply_graph_subject(row)
        once = copy.deepcopy(row)
        apply_graph_subject(row)
        self.assertEqual(row, once)

    def test_native_schema_without_compound_reaches_resolution(self):
        item = example()
        item.pop("compound")
        item.pop("domain")
        item.update(public_health_topic_category="Population use & trends", evidence_locator="Abstract")
        result = {"domain_route": "real_world_public_health", "paper_type": "primary_study", "text_depth": "abstract_only", "source_type": "primary", "extraction_status": "extracted", "study_doi": "10.example/role"}
        row = evidence_row_for_item(output_row={}, result=result, item=item, item_kind="primary_item", item_index=0, tasks={})
        self.assertIsNotNone(row)
        self.assertEqual(row["compound"], "Hallucinogens")
        self.assertEqual(row["graph_entity_label"], "Self-reported hallucinogen use")

    def test_existing_explicit_drug_subject_has_priority(self):
        row = example(compound="LSD", exposure_or_policy="Lifetime LSD use", public_health_measure="Past-year MDMA use", finding_summary="Lifetime LSD use was associated with past-year MDMA use.")
        self.assertIsNone(resolve_real_world_measure_subject(row))
        apply_graph_subject(row)
        self.assertEqual(row["compound"], "LSD")

    def test_mixed_and_noneligible_outcomes_do_not_become_drug_specific(self):
        for measure, summary in [
            ("Past-year MDMA and ketamine use", "Respondents reported MDMA and ketamine use."),
            ("Combined cannabis and hallucinogen use", "The combined cannabis and hallucinogen category increased."),
            ("Use of prescription drugs combined with psychedelics", "Prescription drugs combined with psychedelics were used."),
            ("NPS/MDMA hair-test detection", "NPS/MDMA hair-test detection was associated with attendance."),
            ("Past-year cannabis use", "Past-year cannabis use increased."),
            ("MDMA and 3-MMC use", "MDMA and 3-MMC use was reported."),
        ]:
            with self.subTest(measure=measure):
                self.assertIsNone(resolve_real_world_measure_subject(example(public_health_measure=measure, finding_summary=summary)))

    def test_pooled_exposure_is_not_reoriented_to_component(self):
        for exposure in ["Chemsex including ketamine and GHB", "Combined prescription drug and psychedelic use", "Polysubstance use", "Lifetime cannabis use"]:
            with self.subTest(exposure=exposure):
                row = example(compound=exposure, exposure_or_policy=exposure, public_health_measure="Ketamine use prevalence", finding_summary="Ketamine use prevalence was measured.")
                self.assertIsNone(resolve_real_world_measure_subject(row))

    def test_only_same_finding_can_corroborate_measure_identity(self):
        row = example(public_health_measure="MDMA use prevalence", finding_summary="Use prevalence was associated with age.", study_title="A study of MDMA use", population="MDMA users")
        self.assertIsNone(resolve_real_world_measure_subject(row))

    def test_source_location_guard_keeps_background_only_result_unresolved(self):
        self.assertIsNone(resolve_real_world_measure_subject(example(evidence_location="Introduction")))
        self.assertIsNotNone(resolve_real_world_measure_subject(example(evidence_location="Results; Table 2")))

    def test_null_association_is_still_a_measured_outcome(self):
        row = example(finding_summary="There was no association between minority status and hallucinogen use.")
        self.assertEqual(resolve_real_world_measure_subject(row)["label"], "Hallucinogens")

    def test_receptor_or_analogue_text_is_not_a_drug_outcome(self):
        for measure in ["MDMA analogue use", "Ketamine metabolite prevalence", "PCP receptor testing", "Endogenous LSD-like factor use"]:
            with self.subTest(measure=measure):
                self.assertIsNone(resolve_real_world_measure_subject(example(public_health_measure=measure, finding_summary=measure)))

    def test_policy_predictor_and_same_drug_outcome_preserve_policy(self):
        exposure = "LSD decriminalization policy"
        row = example(compound=exposure, exposure_or_policy=exposure, public_health_measure="Past-year LSD use", finding_summary="Past-year LSD use was higher after the policy change.")
        apply_graph_subject(row)
        self.assertEqual(row["compound"], "LSD")
        self.assertEqual(row["exposure_or_policy"], exposure)

    def test_non_realworld_row_is_untouched_by_resolver(self):
        self.assertIsNone(resolve_real_world_measure_subject(example(domain="clinical_outcome")))


if __name__ == "__main__":
    unittest.main()
