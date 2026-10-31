import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd
from pipeline.kg.build_evidence_tables import (
    DEFAULT_REGISTRY_PATH, brain_measure_graph_label, build_tables,
    explicit_active_reference_comparison, graphable_subject_match,
    graphable_entity_match, graph_admission_decision, node_vocabulary_lookup,
    overview_graph_subjects, registry_lookup, normalize_claim_metadata, primary_uncorrected_brain_activation, reported_psychedelic_class_identity_conflict, molecular_finding_subtopic, molecular_subtopic_coverage_summary, unregistered_named_agent_class_descriptor, entity_expanded_rows, entity_kind_for, entity_label_for, primary_baseline_or_control_only_brain_result,
)


class CrossDomainNormalizationRepairTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = registry_lookup(DEFAULT_REGISTRY_PATH)
        cls.vocab = node_vocabulary_lookup()

    def match(self, raw, kind='biomarker_readout', domain='brain_system', **row):
        return graphable_entity_match(row, domain, kind, raw, self.registry, self.vocab)

    def test_receptor_measurements_are_not_occupancy_synonyms(self):
        for raw, expected in [('receptor occupancy', 'Receptor occupancy'),
                              ('5-HT2A binding potential', 'Binding potential'),
                              ('5-HT2A receptor availability', 'Receptor availability'),
                              ('cortical receptor density', 'Receptor density'),
                              ('receptor binding', 'Receptor binding')]:
            with self.subTest(raw=raw):
                self.assertEqual(brain_measure_graph_label(raw), expected)

    def test_explicit_active_reference_comparison_keeps_exposure_role(self):
        for text, expected in [('Ketamine versus placebo (saline)', 'Ketamine'),
                               ('LSD (75 μg intravenous) versus placebo (saline)', 'LSD'),
                               ('Intravenous DMT fumarate compared with placebo (saline)', 'DMT'),
                               ('Ketamine versus midazolam', 'Ketamine')]:
            with self.subTest(text=text):
                row = {'compound': text, 'graph_subject_label': text, 'graph_subject_kind': 'atomic_compound'}
                match = graphable_subject_match(row, self.registry)
                self.assertEqual(match['label'], expected)
                self.assertEqual(match['match_type'], 'explicit_active_reference_comparison')
        for text in ['Placebo versus ketamine']:
            with self.subTest(text=text):
                self.assertFalse(explicit_active_reference_comparison(text, self.registry))
                row = {'compound': text, 'graph_subject_label': text, 'graph_subject_kind': 'atomic_compound'}
                match = graphable_subject_match(row, self.registry)
                self.assertEqual(match['label'], text)
                self.assertEqual(match['subject_kind'], 'exposure_context')
                self.assertEqual(overview_graph_subjects(row, match, self.registry), [])
        self.assertFalse(explicit_active_reference_comparison('Naloxone versus placebo (saline)', self.registry))
        for raw in ['Past-year ecstasy use; self-report compared with adjusted prevalence incorporating positive hair detection for synthetic cathinones',
                    'Past-year ecstasy users compared with placebo',
                    'Ecstasy use history compared with self-reported drug use']:
            self.assertFalse(explicit_active_reference_comparison(raw, self.registry))

    def test_anatomical_aliases_preserve_specific_location(self):
        for raw, expected in [('Subthalamic nucleus (STN)', 'Subthalamic nucleus'),
                              ('Rostroventromedial medulla (RVM)', 'Rostroventromedial medulla'),
                              ('Dorsal lateral geniculate nucleus', 'Dorsal lateral geniculate nucleus'),
                              ('Mesencephalon', 'Midbrain'),
                              ('Olfactory bulb', 'Olfactory bulb')]:
            with self.subTest(raw=raw):
                match = self.match(raw, 'brain_region')
                self.assertTrue(match['matched'])
                self.assertEqual(match['label'], expected)
                self.assertEqual(match['kind'], 'brain_region')

    def test_synaptic_circuit_alias_does_not_reverse_direction(self):
        match = self.match('Schaffer collateral→CA1 (SC→CA1)', 'neural_circuit')
        self.assertEqual(match['label'], 'Schaffer collateral-CA1 circuit')
        reverse = self.match('CA1-to-CA3 feedback projection', 'neural_circuit')
        self.assertFalse(reverse['matched'])

    def test_neural_readouts_keep_measured_construct(self):
        for raw, expected in [('ASSR phase locking factor (PLF; trial-to-trial phase consistency)', 'Auditory steady-state phase locking'),
                              ('ASSR mean trial power (MTP; response magnitude)', 'Auditory steady-state response power'),
                              ('Dynamic range of AEP components P21 and N85', 'ERP'),
                              ('NREM delta EEG intensity (amplitude and incidence)', 'EEG signal intensity'),
                              ('Spreading depolarizations and ECoG background activity', 'Spreading depolarization')]:
            with self.subTest(raw=raw):
                match = self.match(raw)
                self.assertEqual(match['label'], expected)
                self.assertEqual(match['kind'], 'brain_measure')
        self.assertFalse(self.match('Tonic genioglossus muscle activity (GGemg)')['matched'])
        self.assertFalse(self.match('Cerebral blood volume (CBV)')['matched'])

    def test_unresolved_anatomy_retains_only_explicit_neural_measure(self):
        row = {'readout': 'Dopamine-neuron firing rate', 'support': 'The measured rate increased.'}
        match = self.match('Serotonergic regulation of nigrostriatal neurons', 'neural_circuit', **row)
        self.assertEqual(match['label'], row['readout'])
        self.assertEqual(graph_admission_decision({'domain': 'brain_system', 'entity_match_type': match['match_type']}),
                         ('paper_detail', 'explicit_neural_readout_without_resolved_anatomy'))
        self.assertFalse(self.match('Unknown neural circuit', 'neural_circuit', support='Background mentions firing rate')['matched'])
        self.assertFalse(self.match('Unknown muscle', 'brain_region', readout='Muscle contraction amplitude')['matched'])
        self.assertFalse(self.match('Unknown pathway', 'pathway_process', 'molecular_pathway_readout', readout='Neuronal firing rate')['matched'])

    def test_detail_readout_preserves_literal_measurement_not_keyword_family(self):
        for readout in [
            'Single-unit firing rate and stimulus-dependent build-up slope; sensitivity to motion coherence and binocular correlation',
            'Fraction of neurons phase-entrained to 3–6 Hz oscillations',
            'Structural connectivity tract length',
            'Geodesic entropy of neural trajectories',
            'Retinal oscillatory potential amplitude and timing',
            'Degree centrality derived from BOLD signals',
            'Phase-locking factor for transient speech deviants',
        ]:
            with self.subTest(readout=readout):
                match = self.match('Unresolved neural circuit', 'neural_circuit', readout=readout)
                self.assertEqual(match['label'], readout)
                self.assertEqual(match['match_type'], 'explicit_neural_readout_detail_only')

    def test_known_multi_anatomy_precedes_readout_detail_fallback(self):
        for raw, readout, expected in [
            ('Posterior cingulate and anterior cingulate', 'BOLD signal', {'Posterior cingulate cortex', 'Anterior cingulate cortex'}),
            ('Primary auditory cortex and somatosensory cortex', 'Oscillatory power', {'Auditory cortex', 'Somatosensory cortex'}),
            ('Hippocampus and prefrontal cortex', 'Synaptic plasticity; long-term potentiation (LTP)', {'Hippocampus', 'Prefrontal cortex'}),
        ]:
            row = {'domain': 'brain_system', 'compound': 'Ketamine', 'graph_subject_kind': 'atomic_compound',
                   'kg_entity_kind_override': 'brain_region', 'graph_entity_label': raw, 'readout': readout}
            expanded = entity_expanded_rows(row, 'brain_system', self.registry, self.vocab)
            matches = [self.match(entity_label_for(x, 'brain_system', entity_kind_for(x, 'brain_system')),
                                  entity_kind_for(x, 'brain_system'), **x) for x in expanded]
            self.assertEqual({x['label'] for x in matches}, expected)
            self.assertTrue(all(x['kind'] == 'brain_region' for x in matches))
        # A nested region or an incomplete list must not disappear, or produce
        # a pseudo-region derived from the readout for its unresolved fragment.
        for raw in ['Ventral dentate gyrus of the hippocampus',
                    'Dorsal and medial anterior striatum and thalamus (ventral lateral nucleus)',
                    'Thalamus and frontoparietal white matter']:
            row = {'domain': 'brain_system', 'compound': 'Ketamine', 'graph_subject_kind': 'atomic_compound',
                   'kg_entity_kind_override': 'brain_region', 'graph_entity_label': raw, 'readout': 'Regional functional connectivity'}
            expanded = entity_expanded_rows(row, 'brain_system', self.registry, self.vocab)
            self.assertEqual(len(expanded), 1)
            match = self.match(raw, 'brain_region', **row)
            self.assertEqual(match['label'], row['readout'])
            self.assertEqual(match['match_type'], 'explicit_neural_readout_detail_only')

    def test_molecular_annotation_is_not_measured_neural_plasticity(self):
        for raw, assay in [
            ('Long-term potentiation', 'mRNA microarray profiling; differential-expression and gene ontology analysis'),
            ('Long-term depression pathway', 'Computational KEGG pathway enrichment'),
            ('Phosphorylation of proteins annotated to LTP signaling', 'Quantitative phosphoproteomics; pathway enrichment analysis'),
            ('Overall gene co-expression network connectivity', 'Weighted Gene Co-expression Network Analysis'),
        ]:
            match = self.match(raw, 'biomarker_readout', 'molecular_pathway_readout',
                               specific_readout_or_marker=raw, assay_type=assay, molecular_effect_category='Neuroplasticity')
            self.assertNotEqual(match['kind'], 'brain_measure')
        measured = self.match('Long-term potentiation', 'biomarker_readout', 'molecular_pathway_readout',
                              assay_type='Hippocampal-slice field electrophysiology after protein-synthesis inhibition')
        self.assertEqual(measured['label'], 'Synaptic plasticity')
        self.assertEqual(self.match('Long-term potentiation')['label'], 'Synaptic plasticity')
        self.assertEqual(brain_measure_graph_label('ASSR phase-locking factor'), 'Auditory steady-state phase locking')
        self.assertEqual(brain_measure_graph_label('Theta phase-locking factor for transient speech deviants'), '')

    def test_specific_sexual_assay_is_behavior_not_subjective_desire(self):
        match = self.match('Sexual behavior', 'cognitive_behavioral_construct', 'cognitive_behavioral', task_or_measure='Lordosis-to-mount ratio')
        self.assertTrue(match['matched'])
        self.assertEqual(match['label'], 'Sexual behavior')
        for task in ['Sexual desire motivated use', 'Subjective pleasure in interviews', 'Sexual experience ratings']:
            self.assertFalse(self.match('Sexual behavior', 'cognitive_behavioral_construct', 'cognitive_behavioral', task_or_measure=task)['matched'])

    def test_reference_treatment_low_dose_probe_not_atomic_efficacy(self):
        row = {'graph_subject_label': 'Escitalopram treatment with low-dose psilocybin and psychological support',
               'graph_subject_kind': 'compound_combination', 'atomic_compound_candidate': '',
               'support': 'Within the escitalopram arm, pessimism scores decreased.'}
        row['compound'] = row['graph_subject_label']
        match = graphable_subject_match(row, self.registry)
        self.assertTrue(match['matched'])
        self.assertEqual(match['label'], row['graph_subject_label'])
        self.assertEqual(overview_graph_subjects(row, match, self.registry), [])
        active = {'graph_subject_label': 'Psilocybin treatment with psychological support', 'graph_subject_kind': 'treatment_regimen'}
        active['compound'] = active['graph_subject_label']
        active_match = graphable_subject_match(active, self.registry)
        self.assertEqual(overview_graph_subjects(active, active_match, self.registry)[0]['label'], 'Psilocybin')

    def test_pooled_alternative_exposures_are_not_separate_drug_results(self):
        row = {'compound': 'Psilocybin mushrooms or LSD; transformative experiences.',
               'graph_subject_kind': 'compound_combination',
               'atomic_compound_candidate': 'Psilocybin mushrooms or LSD; transformative experiences.',
               'source_item_type': 'primary_item', 'paper_assessment_route': 'primary_evidence',
               'study_design': 'Qualitative interview and survey',
               'support': 'Participants described lasting changes.'}
        match = graphable_subject_match(row, self.registry)
        self.assertTrue(match['matched'])
        self.assertEqual(overview_graph_subjects(row, match, self.registry), [])

    def test_pooled_observations_preserve_explicit_class_and_context_units(self):
        for raw, kind, expected in [
            ('Classic psychedelics (DMT, LSD, psilocybin, or mescaline; compound-specific results not reported)', 'compound_class', 'Classic psychedelics'),
            ('Lifetime classic tryptamine use (psilocybin, DMT, or ayahuasca)', 'compound_class', 'Tryptamines'),
            ('Chemsex involving ketamine or MDMA', 'exposure_context', 'Chemsex')]:
            row = {'compound': raw, 'graph_subject_kind': kind,
                   'source_item_type': 'primary_item', 'study_design': 'Cross-sectional survey',
                   'support': 'The grouped exposure was associated with the endpoint.'}
            match = graphable_subject_match(row, self.registry)
            overview = overview_graph_subjects(row, match, self.registry)
            self.assertEqual([x['label'] for x in overview], [expected])
            self.assertTrue(all(x['kind'] != 'atomic_compound' for x in overview))

    def test_predictor_class_is_not_the_administered_drug(self):
        row = {'compound': 'LSD; prior hallucinogen experience as a predictor',
               'graph_subject_kind': 'compound_class'}
        match = graphable_subject_match(row, self.registry)
        self.assertEqual(match['label'], 'LSD')
        self.assertEqual(overview_graph_subjects(row, match, self.registry)[0]['label'], 'LSD')

    def test_uncorrected_activation_does_not_demote_corrected_connectivity(self):
        row = {'domain': 'brain_system', 'source_item_type': 'primary_item',
               'readout': 'BOLD activation during cue processing',
               'statistic_or_value': 'cluster p=0.007',
               'extraction_warnings': 'Activation analyses used an uncorrected whole-brain threshold (p<0.005).'}
        self.assertTrue(primary_uncorrected_brain_activation(row))
        self.assertEqual(graph_admission_decision(row)[0], 'paper_detail')
        corrected = {**row, 'readout': 'Condition-specific functional connectivity', 'statistic_or_value': 'p-FWE=0.040'}
        self.assertFalse(primary_uncorrected_brain_activation(corrected))
        self.assertEqual(graph_admission_decision(corrected)[0], 'main_graph')
        unspecified = {**row, 'extraction_warnings': ''}
        self.assertFalse(primary_uncorrected_brain_activation(unspecified))
        mixed = {**row, 'statistic_or_value': 'cluster FDR p=.04; uncorrected cluster-forming p=.001'}
        self.assertFalse(primary_uncorrected_brain_activation(mixed))
        null = {**row, 'readout': 'Receptor availability', 'statistic_or_value': 'null result p>.05 uncorrected'}
        self.assertFalse(primary_uncorrected_brain_activation(null))

    def test_explicit_failed_correction_is_not_positive_corrected_inference(self):
        base = {'domain': 'brain_system', 'source_item_type': 'primary_item'}
        for readout, stats in [
            ('BOLD activation', 'Increased activation at p<.005 uncorrected; not significant at p<.05 FWE'),
            ('Regional cerebral blood flow (rCBF)', 'Decrease at p<.01 uncorrected; clusters did not survive TFCE FWE correction'),
        ]:
            self.assertTrue(primary_uncorrected_brain_activation({**base, 'readout': readout, 'statistic_or_value': stats}))
        for stats in [
            'Cluster-level FDR p=.04; uncorrected cluster-forming p=.001',
            'Increased activation at p<.005 uncorrected; not significant at p<.05 FWE; a separate cluster survived FDR p=.02',
            'Null result p>.05 uncorrected; not significant after FWE correction',
            'No significant difference at p<.05 uncorrected; did not survive FWE correction',
        ]:
            self.assertFalse(primary_uncorrected_brain_activation({**base, 'readout': 'BOLD activation', 'statistic_or_value': stats}))

    def test_baseline_and_control_roles_do_not_remove_response_predictions(self):
        base = {'domain': 'brain_system', 'source_item_type': 'primary_item', 'canonical_compound': 'Ketamine'}
        baseline = {**base, 'compound_original': 'Treatment-resistant depression; subsequent ketamine treatment',
                    'support': 'TRD participants had lower prefrontal connectivity than healthy controls.'}
        self.assertTrue(primary_baseline_or_control_only_brain_result(baseline))
        control = {**base, 'support': 'Drug-naive controls showed increased frontal activation during the task.'}
        self.assertTrue(primary_baseline_or_control_only_brain_result(control))
        for row in [
            {**baseline, 'support': 'Baseline connectivity predicted subsequent ketamine response.'},
            {**baseline, 'support': 'Baseline connectivity predicted clinical response.'},
            {**control, 'support': 'Drug-naive controls showed lower activation than the ketamine group.'},
            {**control, 'support': 'Drug-naive controls showed lower activation than the treated group.'},
            {**base, 'support': 'Healthy volunteers showed lower activation after ketamine.'},
        ]:
            self.assertFalse(primary_baseline_or_control_only_brain_result(row))

    def test_finalized_neural_detail_is_not_retyped_from_symptom_association(self):
        raw = 'Functional connectivity change associated with psychosis-like and dissociative symptom change'
        row = {'domain': 'brain_system', 'graph_entity_label': raw, 'readout': raw,
               'kg_entity_kind_override': 'brain_measure', 'entity_match_type': 'explicit_neural_readout_detail_only',
               'support': 'Ketamine-related connectivity changes were associated with psychosis-like and dissociative symptoms.'}
        result = normalize_claim_metadata(row, 'brain_system')
        self.assertEqual(result['domain'], 'brain_system')
        self.assertEqual(result['graph_entity_label'], raw)
        self.assertEqual(result['kg_entity_kind_override'], 'brain_measure')

    def test_withdrawal_context_preserves_explicit_behavior_task(self):
        row = {'domain': 'cognitive_behavioral', 'compound': 'Ayahuasca',
               'kg_entity_kind_override': 'cognitive_behavioral_construct',
               'graph_entity_label': 'Anxiety-like behavior',
               'construct_or_behavior': 'Anxiety-like behavior associated with ethanol withdrawal',
               'task_or_measure': 'Elevated plus maze',
               'support': 'Ayahuasca reduced anxiety-like behavior during ethanol withdrawal.'}
        result = normalize_claim_metadata(row, 'cognitive_behavioral')
        self.assertEqual(result['kg_entity_kind_override'], 'cognitive_behavioral_construct')
        self.assertEqual(result['graph_entity_label'], 'Anxiety-like behavior')

    def test_metabolic_transform_is_not_an_inferred_target(self):
        match = self.match('Aromatic hydroxylation', 'pathway_process', 'pharmacokinetics_exposure')
        self.assertTrue(match['matched'])
        self.assertEqual(match['kind'], 'pathway_process')
        self.assertFalse(self.match('Aromatic hydroxylation', 'target', 'molecular_target')['matched'])

    def test_dose_comparisons_and_separate_experiment_arms_remain_supported(self):
        for raw in ['One versus two intravenous DMT doses',
                    'Ketamine, 0.5 mg/kg or 0.2 mg/kg, versus normal saline placebo',
                    'Oral psilocybin, 0.26 mg/kg, compared with placebo; delta scores',
                    '2C-B (20 mg) and psilocybin (15 mg), each compared with placebo',
                    'LSD 100 or 200 µg and psilocybin 15 or 30 mg, compared with placebo',
                    'R-ketamine or S-ketamine versus saline']:
            row = {'compound': raw, 'graph_subject_kind': 'atomic_compound', 'atomic_compound_candidate': raw}
            match = graphable_subject_match(row, self.registry)
            self.assertTrue(match['matched'])
            self.assertTrue(overview_graph_subjects(row, match, self.registry))

    def test_explicit_reported_class_identity_conflict_keeps_literal_detail(self):
        raw = 'Maternal opioids/hallucinogens (hallucinogen exposure coded as methamphetamine) or cocaine'
        self.assertTrue(reported_psychedelic_class_identity_conflict(raw, self.registry))
        row = {'compound': raw, 'graph_subject_kind': 'compound_class'}
        match = graphable_subject_match(row, self.registry)
        self.assertTrue(match['matched'])
        self.assertEqual(match['label'], raw)
        self.assertEqual(overview_graph_subjects(row, match, self.registry), [])
        for valid in ['Hallucinogens compared with methamphetamine',
                      'Hallucinogens (hallucinogen exposure coded as LSD)',
                      'Hallucinogens; reference drug methamphetamine']:
            self.assertFalse(reported_psychedelic_class_identity_conflict(valid, self.registry))

    def test_explicit_electrophysiology_subtopics_preserve_measurement_identity(self):
        parent = 'Neuronal excitability & synaptic transmission'
        cases = [
            ('NMDAR-mediated field EPSP slope', 'Field potentials & synaptic strength'),
            ('NMDAR-mediated 2PLU-evoked current amplitude', 'Membrane potential & ion channels'),
            ('GABA_A current reversal potential', 'Membrane potential & ion channels'),
            ('Tonic GABA current (picrotoxin-sensitive holding-current change)', 'Membrane potential & ion channels'),
            ('Late sodium current (INaL) density', 'Membrane potential & ion channels'),
            ('KCNQ2/3 M-current density', 'Membrane potential & ion channels'),
            ('Channel open probability and mean channel open time', 'Membrane potential & ion channels'),
            ('Striatal neuron input resistance', 'Membrane potential & ion channels'),
            ('ECoG normalized absolute power, 3–6 Hz frequency band', 'Neural oscillations'),
        ]
        for raw, expected in cases:
            with self.subTest(raw=raw):
                self.assertEqual(molecular_finding_subtopic({}, parent, raw), expected)
        # Protein abundance, transport-linked amperometric signals and peripheral
        # muscle physiology do not become an inferred neuronal current result.
        for raw in ['GABA-B receptor subunit 1 protein abundance', 'MDMA-induced current',
                    'SCA exocytotic transient peak current', 'Human SERT-mediated inward current', 'Electrically evoked muscle contraction',
                    'Short-circuit current; transepithelial sodium transport', 'Alpha band label without an electrical power measure']:
            self.assertEqual(molecular_finding_subtopic({}, parent, raw), '')
        row = {'specific_readout_or_marker': 'Spontaneous IPSC frequency',
               'support': 'The assay also measured NMDAR-mediated current amplitude and EEG power.'}
        self.assertEqual(molecular_finding_subtopic(row, parent, 'Spontaneous IPSC frequency'), 'Inhibitory postsynaptic currents')
        epsc = {'assay_type': 'Whole-cell patch-clamp recording of NMDA receptor-mediated EPSCs'}
        self.assertEqual(molecular_finding_subtopic(epsc, parent, 'NMDA receptor-mediated synaptic current electrophysiology'), 'Excitatory postsynaptic currents')
        # The existing coverage gate still fails, rather than relaxing its limit.
        frame = pd.DataFrame([{'domain': 'molecular_pathway_readout', 'graph_parent_label': parent,
                               'molecular_finding_subtopic': '' if i < 11 else 'Mapped'} for i in range(50)])
        self.assertEqual(molecular_subtopic_coverage_summary(frame)['status'], 'failed')

    def test_named_unknown_agent_is_not_a_whole_pharmacological_class(self):
        for raw in ['APV (competitive NMDA receptor antagonist)',
                    'NEW-123 (NMDA antagonist)', 'Novelagent (hallucinogen)']:
            row = {'compound': raw, 'graph_subject_kind': 'compound_class',
                   'atomic_compound_candidate': raw, 'source_item_type': 'primary_item'}
            self.assertTrue(unregistered_named_agent_class_descriptor(raw, self.registry))
            match = graphable_subject_match(row, self.registry)
            self.assertTrue(match['matched'])
            self.assertEqual(overview_graph_subjects(row, match, self.registry), [])
        for raw in ['Hallucinogens (LSD and PCP)', 'NMDA receptor antagonists (ketamine and PCP)',
                    'Compounds (NMDA receptor antagonists)', 'APV and ketamine (NMDA receptor antagonists)',
                    'Ketamine (NMDA receptor antagonist)', 'LSD (hallucinogenic 5-HT2A receptor agonist)',
                    'Daath (the Hungarian Psychedelic Community)']:
            self.assertFalse(unregistered_named_agent_class_descriptor(raw, self.registry))
        for raw, expected in [('Hallucinogens (LSD and PCP)', 'Hallucinogens'),
                              ('NMDA receptor antagonists (ketamine and PCP)', 'NMDA receptor antagonists'),
                              ('Ketamine (NMDA receptor antagonist)', 'Ketamine')]:
            row = {'compound': raw, 'graph_subject_kind': 'compound_class', 'source_item_type': 'primary_item'}
            match = graphable_subject_match(row, self.registry)
            self.assertEqual(overview_graph_subjects(row, match, self.registry)[0]['label'], expected)

    def test_saved_fields_survive_real_table_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); source = root/'rows.json'
            rows = [
                {'study_doi': '10.1/neural', 'domain': 'brain_system', 'graph_subject_label': 'Ketamine',
                 'graph_subject_kind': 'atomic_compound', 'kg_entity_kind_override': 'neural_circuit',
                 'graph_entity_label': 'Layer VI corticothalamic pathway; prethalamic inputs',
                 'readout': 'Gamma oscillation power (30–80 Hz)', 'support': 'Spontaneous gamma increased but evoked gamma decreased.',
                 'effect_size': 'Opposite directions by endpoint', 'evidence_location': 'Results'},
                {'study_doi': '10.1/placebo', 'domain': 'subjective_experience', 'graph_subject_label': 'Ketamine versus placebo (saline)',
                 'graph_subject_kind': 'atomic_compound', 'kg_entity_kind_override': 'subjective_experience_construct',
                 'graph_entity_label': 'Somatic sensations', 'comparator': 'Saline placebo',
                 'support': 'Ketamine reduced intensity and unpleasantness.', 'evidence_location': 'Results'},
                {'study_doi': '10.1/agent', 'domain': 'brain_system',
                 'graph_subject_label': 'APV (competitive NMDA receptor antagonist)',
                 'atomic_compound_candidate': 'APV (competitive NMDA receptor antagonist)',
                 'graph_subject_kind': 'compound_class', 'source_item_type': 'primary_item',
                 'kg_entity_kind_override': 'brain_region', 'graph_entity_label': 'Inferior olivary nucleus',
                 'support': 'APV did not significantly alter spontaneous subthreshold oscillations.',
                 'evidence_location': 'Results'},
            ]
            for row in rows:
                row['compound'] = row['graph_subject_label']
            source.write_text(json.dumps(rows))
            build_tables(graph_sources={'routed_extractions': {'path': source, 'domain': 'routed', 'dataset': 'routed', 'default_evidence_type': 'primary_evidence', 'skip_audit': True}},
                         out_dir=root/'out', write_duckdb=False)
            f = pd.read_parquet(root/'out/findings.parquet').set_index('study_doi')
            self.assertEqual(set(f.index), {'10.1/neural', '10.1/placebo', '10.1/agent'})
            self.assertEqual(f.loc['10.1/neural','graph_admission_status'], 'paper_detail')
            self.assertEqual(f.loc['10.1/neural','graph_entity_original'], rows[0]['graph_entity_label'])
            self.assertEqual(f.loc['10.1/neural','readout'], rows[0]['readout'])
            self.assertEqual(f.loc['10.1/placebo','compound_original'], rows[1]['graph_subject_label'])
            self.assertEqual(f.loc['10.1/placebo','graph_overview_subject_label'], 'Ketamine')
            self.assertEqual(f.loc['10.1/placebo','comparator'], 'Saline placebo')
            self.assertEqual(f.loc['10.1/agent','graph_admission_status'], 'paper_detail')
            self.assertEqual(json.loads(f.loc['10.1/agent','graph_overview_subjects_json']), [])
            self.assertEqual(f.loc['10.1/agent','compound_original'], rows[2]['graph_subject_label'])
            edges = pd.read_parquet(root/'out/evidence_edges.parquet')
            self.assertFalse(((edges.study_doi == '10.1/agent') & (edges.graph_admission_status == 'main_graph')).any())

    def test_anatomy_and_molecular_measurement_precedence_in_actual_tables(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            molecular = '1028-gene transcriptional signature; MAPK signaling pathway, Wnt signaling pathway, neuroactive ligand-receptor interaction, long-term potentiation, and long-term depression pathway gene categories'
            rows = [
                {'study_doi': '10.1/anatomy', 'domain': 'brain_system', 'kg_entity_kind_override': 'brain_region',
                 'graph_entity_label': 'Posterior cingulate and anterior cingulate', 'readout': 'BOLD signal'},
                {'study_doi': '10.1/expression', 'domain': 'molecular_pathway_readout', 'kg_entity_kind_override': 'biomarker_readout',
                 'graph_entity_label': molecular, 'specific_readout_or_marker': molecular,
                 'molecular_effect_category': 'Gene expression & activity markers', 'assay_type': 'Transcriptomic gene-expression analysis'},
                {'study_doi': '10.1/literal', 'domain': 'brain_system', 'kg_entity_kind_override': 'neural_circuit',
                 'graph_entity_label': 'Unresolved neural circuit', 'readout': 'Fraction of neurons phase-entrained to 3–6 Hz oscillations'},
            ]
            for row in rows:
                row.update(compound='Ketamine', graph_subject_kind='atomic_compound', support='Endpoint-specific result remained unchanged.',
                           comparator='Saline', statistic_or_value='p=0.018', extraction_warnings='Reported endpoint-specific limitation')
            source = root/'rows.json'; source.write_text(json.dumps(rows))
            build_tables(graph_sources={'routed_extractions': {'path': source, 'domain': 'routed', 'dataset': 'routed', 'default_evidence_type': 'primary_evidence', 'skip_audit': True}},
                         out_dir=root/'out', write_duckdb=False)
            f = pd.read_parquet(root/'out/findings.parquet')
            anatomy = f[f.study_doi == '10.1/anatomy']
            self.assertEqual(set(anatomy.entity_label), {'Posterior cingulate cortex', 'Anterior cingulate cortex'})
            molecular_findings = f[f.study_doi == '10.1/expression']
            self.assertGreater(len(molecular_findings), 1)
            self.assertEqual(set(molecular_findings.domain), {'molecular_pathway_readout'})
            self.assertFalse((molecular_findings.kg_entity_kind_override == 'brain_measure').any())
            literal = f[f.study_doi == '10.1/literal'].iloc[0]
            self.assertEqual(literal.entity_label, rows[2]['readout'])
            self.assertEqual(literal.graph_admission_status, 'paper_detail')
            for field in ('support', 'comparator', 'statistic_or_value', 'extraction_warnings'):
                self.assertEqual({json.loads(raw)[field] for raw in f.raw_row_json}, {rows[0][field]})

if __name__ == '__main__':
    unittest.main()
