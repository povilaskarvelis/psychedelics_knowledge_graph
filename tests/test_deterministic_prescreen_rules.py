import unittest
from pipeline.review.deterministic_prescreen_rules import configured_allowed_compound_terms, deterministic_prescreen_decision, evidence_domain_tags_for_context, matched_in_scope_intervention_terms, normalize_routing_tags

class DeterministicPrescreenRulesTest(unittest.TestCase):

    def test_deterministic_prescreen_escalates_intervention_signals(self) -> None:
        psychedelic_row = {'study_title': 'Psilocybin therapy for depression', 'abstract': 'Psilocybin therapy reduced depression symptoms in adults with major depression.', 'contexts': [{'compound': 'Psilocybin', 'entity': 'Depression'}]}
        accented_ketamine_row = {'study_title': 'Intérêt de la kétamine dans le traitement des douleurs chroniques', 'abstract': 'La kétamine est utilisée dans la prise en charge de la douleur chronique réfractaire aux traitements classiques.', 'contexts': []}
        retained_row = {'study_title': 'Novel intervention for depression', 'abstract': 'This report discusses a novel intervention for depression symptoms in adults.', 'contexts': []}
        self.assertEqual(deterministic_prescreen_decision(psychedelic_row)['action'], 'escalate')
        self.assertEqual(deterministic_prescreen_decision(accented_ketamine_row)['action'], 'escalate')
        self.assertEqual(deterministic_prescreen_decision(retained_row)['action'], 'exclude_obvious_irrelevant')

    def test_deterministic_prescreen_excludes_ketamine_only_procedural_sedation(self) -> None:
        rows = [{'study_title': 'Ketamine as a dissociative anesthetic for procedural sedation during endoscopy', 'abstract': 'This study evaluated ketamine dosing for emergency department procedural sedation.', 'contexts': []}, {'study_title': 'Clinical and pharmacokinetic evaluation of S-ketamine for intravenous general anaesthesia', 'abstract': 'Racemic ketamine and S-ketamine were evaluated during field castration.', 'contexts': []}]
        for row in rows:
            with self.subTest(row=row['study_title']):
                decision = deterministic_prescreen_decision(row)
                self.assertEqual(decision['action'], 'exclude_obvious_irrelevant')
                self.assertIn('acute procedural anesthesia or sedation', decision['reason'])

    def test_deterministic_prescreen_tags_brain_cognition_and_bridge_scope(self) -> None:
        row = {'study_title': 'Psilocybin therapy and default mode network connectivity in depression', 'abstract': 'Patients with depression received psilocybin and completed fMRI and cognitive flexibility tasks.', 'contexts': []}
        decision = deterministic_prescreen_decision(row)
        self.assertEqual(decision['action'], 'escalate')
        self.assertIn('brain_system', decision['routing_tags'])
        self.assertIn('cognitive_behavioral', decision['routing_tags'])
        self.assertIn('clinical_outcome', decision['routing_tags'])
        self.assertIn('bridge_clinical_mechanism', decision['routing_tags'])

    def test_evidence_domain_tags_cover_new_systems_scope(self) -> None:
        context = 'Title: MDMA social reward and amygdala-prefrontal circuit function\nAbstract: The study measured BDNF, fMRI connectivity, empathy, safety, and PTSD symptoms.'
        tags = evidence_domain_tags_for_context(context)
        self.assertEqual(tags, ['molecular_pathway', 'brain_system', 'cognitive_behavioral', 'clinical_outcome', 'safety', 'bridge_clinical_mechanism'])

    def test_evidence_domain_tags_cover_gap_domain_scope(self) -> None:
        context = 'Title: Psilocybin pharmacokinetics and mystical experience in a retreat setting\nAbstract: Plasma concentration, depression symptoms, preparation, integration, and naturalistic survey outcomes were measured.'
        tags = evidence_domain_tags_for_context(context)
        self.assertEqual(tags, ['clinical_outcome', 'subjective_experience', 'pharmacokinetics_exposure', 'intervention_context', 'real_world_use_public_health', 'bridge_clinical_mechanism'])

    def test_evidence_domain_tags_cover_expanded_search_terms(self) -> None:
        context = 'Title: Ayahuasca retreat, subjective effects, and global brain connectivity\nAbstract: The cohort survey measured Challenging Experience Questionnaire scores, visual analog scale ratings, psilocin glucuronide, AUC, CYP2D6, set setting, group therapy, ceremonial use, microdose patterns, and arterial spin labeling.'
        tags = evidence_domain_tags_for_context(context)
        self.assertIn('brain_system', tags)
        self.assertIn('subjective_experience', tags)
        self.assertIn('pharmacokinetics_exposure', tags)
        self.assertIn('intervention_context', tags)
        self.assertIn('real_world_use_public_health', tags)

    def test_normalize_routing_tags_filters_unknown_values(self) -> None:
        self.assertEqual(normalize_routing_tags('brain-system|clinical outcome|not_a_tag|brain_system'), ['brain_system', 'clinical_outcome'])

    def test_normalize_routing_tags_maps_old_pathway_biomarker_alias(self) -> None:
        self.assertEqual(normalize_routing_tags('pathway-biomarker|molecular_pathway'), ['molecular_pathway'])

    def test_deterministic_prescreen_uses_config_allowed_compounds(self) -> None:
        self.assertIn('Mescaline', configured_allowed_compound_terms())
        row = {'study_title': 'Mescaline treatment and perception', 'abstract': 'This paper discusses mescaline administration and long-term changes in perception among adult participants.', 'contexts': []}
        decision = deterministic_prescreen_decision(row)
        self.assertEqual(decision['action'], 'escalate')
        self.assertEqual(decision['reason'], 'in-scope compound/intervention term appears in title or abstract')

    def test_deterministic_prescreen_retains_disorder_variant_intervention_terms(self) -> None:
        rows = [{'study_title': 'Efeitos do uso de psilocibina em pacientes adultos com ansiedade e depressão', 'abstract': 'Tratamento: uso da psilocibina para ansiedade e depressão.', 'contexts': []}, {'study_title': 'Plant based assisted therapy for substance use disorders', 'abstract': 'Natural medicines are described including psychoactive derivatives of Tabernanthe iboga and Bufo alvarius.', 'contexts': []}, {'study_title': 'Dreams, Hallucinogenic Drug States, and Schizophrenia', 'abstract': 'This review compares dreams, hallucinogenic drug states, and schizophrenia.', 'contexts': []}, {'study_title': 'The Supreme Court versus Peyote', 'abstract': 'Peyote is discussed as a culturally relevant therapeutic modality.', 'contexts': []}, {'study_title': 'Metabolism of the tryptamine 5-MeO-MiPT', 'abstract': '5-methoxy-N-methyl-N-isopropyltryptamine was detected after intoxication.', 'contexts': []}, {'study_title': 'Psychedeilc Assisted Therapy for post-traumatic stress', 'abstract': 'This article discusses MDMA, psilocybin, and ketamine-assisted approaches.', 'contexts': []}]
        for row in rows:
            with self.subTest(row=row['study_title']):
                decision = deterministic_prescreen_decision(row)
                self.assertEqual(decision['action'], 'escalate')

    def test_deterministic_prescreen_ignores_ambiguous_bare_acronyms(self) -> None:
        disease_modifying_row = {'study_title': 'Disease-Modifying Treatments and Ambulatory Function in Multiple Sclerosis', 'abstract': 'This cohort study compared DMT exposure and disease progression in patients with multiple sclerosis.', 'contexts': []}
        thrombotic_microangiopathy_row = {'study_title': 'Outcomes in pediatric patients with HSCT-TMA', 'abstract': 'This retrospective study evaluated thrombotic microangiopathy outcomes after transplant.', 'contexts': []}
        dutch_doet_row = {'study_title': 'Preventie van kindermishandeling: Wie doet wat?', 'abstract': 'Dit boek geeft inzicht in preventie en zorg.', 'contexts': []}
        dissociative_symptom_row = {'study_title': 'Early EMDR therapy for dissociative symptoms after trauma', 'abstract': 'This trial measured dissociative symptoms and post-traumatic stress.', 'contexts': []}
        minimal_disease_activity_row = {'study_title': 'Minimal Disease Activity and drug resistance in arthritis', 'abstract': 'MDA was measured as an outcome in patients receiving standard anti-inflammatory drugs.', 'contexts': []}
        self.assertEqual(deterministic_prescreen_decision(disease_modifying_row)['action'], 'exclude_obvious_irrelevant')
        self.assertEqual(deterministic_prescreen_decision(dutch_doet_row)['action'], 'exclude_obvious_irrelevant')
        self.assertEqual(deterministic_prescreen_decision(dissociative_symptom_row)['action'], 'exclude_obvious_irrelevant')
        self.assertEqual(deterministic_prescreen_decision(minimal_disease_activity_row)['action'], 'exclude_obvious_irrelevant')
        self.assertEqual(deterministic_prescreen_decision(thrombotic_microangiopathy_row)['action'], 'exclude_obvious_irrelevant')

    def test_ambiguous_acronym_is_retained_with_chemical_support(self) -> None:
        row = {'study_title': 'N,N-Dimethyltryptamine and cortical dynamics', 'abstract': 'This study tested DMT, a psychedelic tryptamine, in a controlled human experiment.', 'contexts': []}
        decision = deterministic_prescreen_decision(row)
        self.assertEqual(decision['action'], 'escalate')
        matched = {term.lower() for term in matched_in_scope_intervention_terms(row['study_title'] + '\n' + row['abstract'])}
        self.assertIn('dmt', matched)

    def test_deterministic_prescreen_retains_doi_compound_context(self) -> None:
        row = {'study_title': 'Effects of repeated DOI treatment on 5-HT neuronal firing', 'abstract': 'The 5-HT2 receptor agonist 1-(2,5-dimethoxy-4-iodophenyl)-2-aminopropane (DOI) changed cortical 5-HT release and head-twitch responses.', 'contexts': []}
        decision = deterministic_prescreen_decision(row)
        self.assertEqual(decision['action'], 'escalate')
        self.assertIn('DOI', matched_in_scope_intervention_terms(row['study_title'] + '\n' + row['abstract']))

    def test_deterministic_prescreen_ignores_doi_identifier_context(self) -> None:
        row = {'study_title': 'Corrigendum: AMPA receptor density in cortical circuits', 'abstract': 'This corrects the article DOI: 10.1000/example.', 'contexts': []}
        decision = deterministic_prescreen_decision(row)
        self.assertEqual(decision['action'], 'exclude_obvious_irrelevant')

    def test_deterministic_prescreen_retains_psychedelic_class_chemistry(self) -> None:
        row = {'study_title': 'Binding of indolylalkylamines at 5-HT2 serotonin receptors', 'abstract': 'This medicinal chemistry study evaluated alpha-methyltryptamine derivatives for 5-HT2A receptor binding affinity and selectivity.', 'contexts': []}
        decision = deterministic_prescreen_decision(row)
        self.assertEqual(decision['action'], 'escalate')
        self.assertIn('psychedelic class chemistry', matched_in_scope_intervention_terms(row['study_title'] + '\n' + row['abstract']))

    def test_deterministic_prescreen_ignores_dmt_nonpsychedelic_acronym_context(self) -> None:
        row = {'study_title': 'Dimethyltin effects on neuronal ion channels', 'abstract': 'Dimethyltin (DMT) altered AMPA and NMDA receptor currents in oocytes.', 'contexts': []}
        decision = deterministic_prescreen_decision(row)
        self.assertEqual(decision['action'], 'exclude_obvious_irrelevant')

    def test_deterministic_prescreen_ignores_nonpsychedelic_lsd_acronym_context(self) -> None:
        rows = [{'study_title': 'Low sodium diet and blood pressure in diabetic patients', 'abstract': 'This meta-analysis compared low sodium diet (LSD) with high sodium diet.', 'contexts': []}, {'study_title': 'Soft drink effects on salivary calcium', 'abstract': 'Data were analyzed with ANOVA and continued with LSD test.', 'contexts': []}]
        for row in rows:
            with self.subTest(row=row['study_title']):
                decision = deterministic_prescreen_decision(row)
                self.assertEqual(decision['action'], 'exclude_obvious_irrelevant')

    def test_deterministic_prescreen_ignores_nonpsychedelic_mda_acronym_context(self) -> None:
        rows = [{'study_title': 'Oxidative stress markers after cerebral ischemia', 'abstract': 'The study measured malondialdehyde (MDA), cytokines, and receptor expression.', 'contexts': []}, {'study_title': '5-HT2C receptors and maximal dentate activation', 'abstract': 'Maximal dentate activation (MDA) was measured in anesthetized rats.', 'contexts': []}, {'study_title': 'Oxidative stress after cerebral injury', 'abstract': 'SOD, CAT, GSH, and MDA parameters were measured after treatment.', 'contexts': []}]
        for row in rows:
            with self.subTest(row=row['study_title']):
                decision = deterministic_prescreen_decision(row)
                self.assertEqual(decision['action'], 'exclude_obvious_irrelevant')

    def test_dissociative_class_is_retained_with_drug_support(self) -> None:
        row = {'study_title': 'Dissociative anesthetics and synaptic plasticity', 'abstract': 'This review discusses dissociative drugs and glutamate signaling.', 'contexts': []}
        decision = deterministic_prescreen_decision(row)
        self.assertEqual(decision['action'], 'escalate')
        self.assertIn('dissociative', matched_in_scope_intervention_terms(row['study_title'] + '\n' + row['abstract']))

    def test_generic_safety_language_does_not_rescue_procedural_ketamine(self) -> None:
        row = {'study_title': 'Safety and effectiveness of ketamine as a sedative agent for pediatric GI endoscopy', 'abstract': 'This study evaluated ketamine sedation during endoscopy.', 'contexts': []}
        decision = deterministic_prescreen_decision(row)
        self.assertEqual(decision['action'], 'exclude_obvious_irrelevant')

    def test_salvinorin_derivatives_are_retained(self) -> None:
        row = {'study_title': 'Salvinorin-based antagonists and kappa opioid receptor interactions', 'abstract': 'The study measured affinity and signaling for salvinorin analogues at KOR.', 'contexts': []}
        decision = deterministic_prescreen_decision(row)
        self.assertEqual(decision['action'], 'escalate')
        self.assertIn('salvinorin', matched_in_scope_intervention_terms(row['study_title'] + '\n' + row['abstract']))

    def test_deterministic_prescreen_does_not_use_candidate_contexts_as_safety_hints(self) -> None:
        row = {'study_title': 'Exercise intervention for depression', 'abstract': 'This randomized trial tested an exercise program for depression symptoms in adults receiving standard outpatient mental health care.', 'contexts': [{'compound': 'Psilocybin', 'entity': 'Depression'}]}
        decision = deterministic_prescreen_decision(row)
        self.assertEqual(decision['action'], 'exclude_obvious_irrelevant')
        self.assertNotIn('candidate', decision['reason'].lower())
