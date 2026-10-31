import copy
import unittest
from pipeline.kg.convert_routed_extractions_to_evidence_rows import apply_graph_subject
from pipeline.kg.subject_role_guards import structured_subject_role_decision


def row(domain, exposure, summary="", **fields):
    return dict(domain=domain, compound=exposure, compound_or_exposure=exposure, finding_summary=summary, **fields)


class StructuredSubjectRolesTest(unittest.TestCase):
    def test_dexmedetomidine_effect_is_not_ketamine_safety(self):
        r=row("safety_tolerability", "Dexmedetomidine during cardiac ischemia/reperfusion; compared with ketamine and untreated I/R control", "Dexmedetomidine produced lower blood pressure.")
        apply_graph_subject(r)
        self.assertEqual(r['graph_admission_status'],'paper_detail')
        self.assertEqual(r['graph_admission_reason'],'eligible_drug_is_comparator_not_measured_actor')

    def test_cannabis_case_is_not_psilocybin_effect(self):
        r=row('subjective_experience','Vaporized cannabis containing 25 mg THC (case dose), compared with cannabis, psilocybin, dextromethorphan (DXM), and salvinorin A conditions in separate laboratory studies')
        apply_graph_subject(r)
        self.assertEqual(r['graph_admission_reason'],'eligible_drug_is_comparator_not_measured_actor')

    def test_confirmed_2cp_not_marketed_2cb(self):
        r=row('subjective_experience','2C-P, detected in serum after the patient reportedly ingested a substance sold as 2C-B','Toxicological analysis identified 2C-P instead.')
        apply_graph_subject(r)
        self.assertEqual(r['graph_admission_reason'],'confirmed_substance_differs_from_marketed_identity')

    def test_confirmed_tfmpp_bzp_not_ecstasy_toxicity(self):
        r=row('real_world_public_health','Ingestion of four tablets sold as Ecstasy, subsequently confirmed to contain TFMPP and BZP; all three patients ingested tablets from the same dealers.',public_health_measure='Acute clinical toxicity associated with confirmed TFMPP and BZP exposure.')
        r['exposure_or_policy']=r.pop('compound_or_exposure')
        apply_graph_subject(r)
        self.assertEqual(r['graph_admission_reason'],'confirmed_substance_differs_from_marketed_identity')

    def test_marketed_product_composition_still_allowed(self):
        r=row('real_world_public_health','Tablets sold as Ecstasy, subsequently confirmed to contain TFMPP and BZP',public_health_measure='Drug composition and adulteration of marketed ecstasy tablets')
        self.assertIsNone(structured_subject_role_decision(r))

    def test_late_negative_does_not_override_earlier_positive(self):
        r=row('safety_tolerability','Ecstasy ingestion; initial outside-hospital ecstasy positive, later admission MDA/MDMA negative','The earlier positive and later negative samples were collected at different times.')
        self.assertIsNone(structured_subject_role_decision(r))

    def test_unknown_identity_or_negative_screen_alone_not_substitution(self):
        for exposure in ['Tablets sold as Ecstasy; MDMA not detected in a late sample','Substance believed to be MDMA; toxicology not available']:
            self.assertIsNone(structured_subject_role_decision(row('safety_tolerability',exposure)))

    def test_no_study_drug_effect_for_lesion_endpoint(self):
        r=row('cognitive_behavioral','Neonatal mPFC lesion; pubertal phencyclidine treatment',behavioral_context='Neonatal mPFC lesions reduced anxiety; pubertal PCP treatment effects on this outcome were not specified.')
        apply_graph_subject(r)
        self.assertEqual(r['graph_admission_reason'],'eligible_drug_effect_explicitly_not_reported_for_endpoint')

    def test_challenge_rescue_result_is_preserved(self):
        for exposure,summary in [
            ('Ketamine-induced behavioral deficits with betaine co-treatment or post-treatment','Betaine reversed deficits caused by repeated ketamine exposure.'),
            ('MDMA exposure with resveratrol co-treatment','Resveratrol ameliorated MDMA-induced depressive-like behavior.'),
            ('PCP-induced social deficits; test compound rescue','The test compound reversed PCP-induced deficits.'),
        ]:
            self.assertIsNone(structured_subject_role_decision(row('cognitive_behavioral',exposure,summary)))

    def test_actual_eligible_drug_comparison_is_preserved(self):
        for exposure in ['MDMA compared with methamphetamine','Psilocybin compared with THC in a crossover trial','MDMA compared with ketamine']:
            self.assertIsNone(structured_subject_role_decision(row('subjective_experience',exposure)))

    def test_pooled_psychedelics_not_first_named_example(self):
        r=row('subjective_experience','Lifetime psychedelic use; substance varied, most commonly psilocybin (45.9%) and LSD (43.1%).','Pooled participants reported connectedness.')
        original=copy.deepcopy(r)
        apply_graph_subject(r)
        self.assertEqual(r['compound'],'Psychedelics (unspecified compounds)')
        self.assertEqual(r['compound_or_exposure'],original['compound_or_exposure'])
        self.assertEqual(r['finding_summary'],original['finding_summary'])
        once=copy.deepcopy(r);apply_graph_subject(r);self.assertEqual(r,once)

    def test_gene_selection_not_human_drug_treatment(self):
        r=row('clinical_outcome','Phencyclidine (PCP)-responsive genes, including PDE4A and PLAT','Human haplotype associations identify schizophrenia susceptibility genes.')
        apply_graph_subject(r)
        self.assertEqual(r['graph_admission_reason'],'drug_responsive_gene_selection_not_clinical_drug_exposure')

    def test_comparison_and_rescue_enantiomers_are_not_blanket_held(self):
        for exposure, summary in [
            ('(S)-ketamine and (R)-ketamine', 'R-ketamine effects were comparable to S-ketamine.'),
            ('(R)-(+)-AR-A008055 or (S)-(-)-AR-A008055 administered with MDMA', 'Pretreatment attenuated MDMA hyperthermia.'),
            ('Fasudil, compared with ketamine and saline', 'In adolescent mice, fasudil and ketamine reduced immobility.'),
            ('Hallucinogenic drug states; compared with mystical ecstasy', 'Computerized analysis distinguished lexical patterns.'),
            ('Trier Social Stress Test (TSST), compared with control across MDMA groups', 'The TSST increased subjective stress.'),
        ]:
            self.assertIsNone(structured_subject_role_decision(row('cognitive_behavioral', exposure, summary)))

    def test_single_enantiomer_with_nonchiral_comparator_not_held(self):
        self.assertIsNone(structured_subject_role_decision(row('cognitive_behavioral','(R)-ketamine compared with saline')))


if __name__=='__main__':unittest.main()
