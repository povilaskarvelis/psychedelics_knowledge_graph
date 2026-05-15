# Provider Overlap And Title-Signal Audit

- Generated: 2026-05-15T06:28:21.655580+00:00
- Protocol: `comprehensive_baseline_v1`
- OpenAlex run: `openalex_100`
- PubMed run: `pubmed_100`

This is a title-level proxy audit, not final relevance screening. It is useful for comparing provider behavior and surfacing obvious noise patterns.

## mechanistic

| Metric | Count |
| --- | ---: |
| all_discovered_overlap | 212 |
| openalex_only_discovered | 524 |
| pubmed_only_discovered | 511 |
| new_doi_overlap | 21 |
| openalex_only_new_dois | 225 |
| pubmed_only_new_dois | 138 |
| combined_new_dois | 384 |

| Provider | Discovered DOIs | New DOIs | Title proxy among new DOIs |
| --- | ---: | ---: | --- |
| openalex | 736 | 246 | 85/246 both (34.6%), 19/246 neither (7.7%), 0/246 secondary-ish (0.0%) |
| pubmed | 723 | 159 | 28/159 both (17.6%), 22/159 neither (13.8%), 5/159 secondary-ish (3.1%) |

| Exclusive-new set | Title proxy |
| --- | --- |
| openalex_only | 78/225 both (34.7%), 19/225 neither (8.4%), 0/225 secondary-ish (0.0%) |
| pubmed_only | 21/138 both (15.2%), 22/138 neither (15.9%), 5/138 secondary-ish (3.6%) |

| Module | OpenAlex new | PubMed new | New overlap | OpenAlex only | PubMed only |
| --- | ---: | ---: | ---: | ---: | ---: |
| glutamate_nmda | 41 | 14 | 0 | 41 | 14 |
| ketamine_nmda | 42 | 12 | 1 | 41 | 11 |
| lsd_5ht2a | 21 | 1 | 0 | 21 | 1 |
| mdma_transporters | 10 | 6 | 0 | 10 | 6 |
| monoamine_transporters | 64 | 58 | 10 | 54 | 48 |
| opioid_sigma_taar | 11 | 20 | 1 | 10 | 19 |
| plasticity_trkb_bdnf | 61 | 50 | 9 | 52 | 41 |
| psilocin_5ht2a | 12 | 2 | 0 | 12 | 2 |
| salvinorin_kor | 4 | 2 | 1 | 3 | 1 |
| serotonin_receptors | 25 | 12 | 1 | 24 | 11 |

### mechanistic / openalex_only_high_signal

- `10.1002/ajmg.b.30197` (2005) - Evidence for a common biological basis of the absorption trait, hallucinogen effects, and positive symptoms: Epistasis between 5-HT2a and COMT polymorphisms
- `10.1002/vms3.936` (2022) - Optimisation of ketamine‐xylazine anaesthetic dose and its association with changes in the dendritic spine of CA1 hippocampus in the young and old male and female Wistar rats
- `10.1007/s00213-004-1982-8` (2004) - Preliminary evidence of attenuation of the disruptive effects of the NMDA glutamate receptor antagonist, ketamine, on working memory by pretreatment with the group II metabotropic glutamate receptor agonist, LY354740, in healthy human subjects
- `10.1007/s00213-011-2277-5` (2011) - A comparison of the effects of ketamine and phencyclidine with other antagonists of the NMDA receptor in rodent assays of attention and working memory
- `10.1007/s00213-015-4128-2` (2015) - Regulation of glutamate transporter 1 via BDNF-TrkB signaling plays a role in the anti-apoptotic and antidepressant effects of ketamine in chronic unpredictable stress model of depression
- `10.1007/s00213-018-4877-9` (2018) - Group II metabotropic glutamate receptor agonist prodrugs LY2979165 and LY2140023 attenuate the functional imaging response to ketamine in healthy subjects
- `10.1007/s00406-020-01208-w` (2020) - Rapid-acting and long-lasting antidepressant-like action of (R)-ketamine in Nrf2 knock-out mice: a role of TrkB signaling
- `10.1007/s12035-019-1613-3` (2019) - S-Ketamine Reverses Hippocampal Dendritic Spine Deficits in Flinders Sensitive Line Rats Within 1 h of Administration

### mechanistic / openalex_only_possible_noise

- `10.1001/jamapsychiatry.2017.0135` (2017) - Association of Stimulant Use With Dopaminergic Alterations in Users of Cocaine, Amphetamine, or Methamphetamine
- `10.1016/0006-8993(72)90208-9` (1972) - Reduced cataleptogenic effects of some neuroleptics in rats with lesioned midbrain raphe and treated with p-chlorophenylalanine
- `10.1016/j.neulet.2015.01.022` (2015) - Spine synapse remodeling in the pathophysiology and treatment of depression
- `10.1016/j.pnpbp.2015.06.001` (2015) - Antidepressant drug action — From rapid changes on network function to network rewiring
- `10.1016/s0149-7634(98)00024-4` (1998) - The elevated T-maze as an experimental model of anxiety
- `10.1016/s0272-5231(21)01108-4` (1986) - Anticholinergic Agents
- `10.1038/mp.2013.66` (2013) - Reelin, an extracellular matrix protein linked to early onset psychiatric diseases, drives postnatal development of the prefrontal cortex via GluN2B-NMDARs and the mTOR pathway
- `10.1038/s41380-019-0414-4` (2019) - The kynurenine pathway: a finger in every pie

### mechanistic / pubmed_only_high_signal

- `10.1007/s00406-020-01095-1` (2020) - Brain-derived neurotrophic factor-TrkB signaling and the mechanism of antidepressant activity by ketamine in mood disorders.
- `10.1016/j.bbrc.2022.01.024` (2022) - Glutamatergic receptor and neuroplasticity in depression: Implications for ketamine and rapastinel as the rapid-acting antidepressants.
- `10.1016/j.isci.2025.112485` (2025) - MeCP2 prevents against sustained ketamine-induced synaptic depression at inhibitory synapses.
- `10.1016/j.jpsychires.2013.02.015` (2013) - Ketamine, magnesium and major depression--from pharmacology to pathophysiology and back.
- `10.1016/j.jpsychires.2024.08.019` (2024) - Ketamine alleviates PTSD-like effect and improves hippocampal synaptic plasticity via regulation of GSK-3β/GR signaling of rats.
- `10.1016/j.neubiorev.2025.106132` (2025) - Neuroplasticity and psychedelics: A comprehensive examination of classic and non-classic compounds in pre and clinical models.
- `10.1016/j.peptides.2017.11.020` (2018) - Cyclopeptide Dmt-[D-Lys-p-CF(3)-Phe-Phe-Asp]NH(2), a novel G protein-biased agonist of the mu opioid receptor.
- `10.1016/j.tins.2024.08.011` (2024) - Rethinking the role of TRKB in the action of antidepressants and psychedelics.

### mechanistic / pubmed_only_possible_noise

- `10.1007/164_2019_251` (2020) - Molecular Mechanisms of Amphetamines.
- `10.1007/7854_2023_443` (2023) - Enhancing Fear Extinction: Pharmacological Approaches.
- `10.1016/j.biopsych.2021.05.008` (2021) - Brain-Derived Neurotrophic Factor Signaling in Depression and Antidepressant Action.
- `10.1016/j.neuron.2021.07.017` (2021) - The cranial windows of perception.
- `10.1016/j.neuropharm.2015.10.025` (2016) - Social isolation rearing increases dopamine uptake and psychostimulant potency in the striatum.
- `10.1016/j.neuropharm.2022.109187` (2022) - Age-related changes in peripheral nociceptor function.
- `10.1021/acschemneuro.4c00139` (2024) - (+)-Borneol Protects Dopaminergic Neuronal Loss in Methyl-4-phenyl-1,2,3,6-tetrahydropyridine-Induced Parkinson's Disease Mice: A Study of Dopamine Level using In Vivo Brain Microdialysis.
- `10.1021/acsmedchemlett.3c00168` (2023) - Microbiome-Gut-Brain Axis Modulation: New Approaches in Treatment of Neuropsychological and Gastrointestinal Functional Disorders.

### mechanistic / pubmed_only_secondary

- `10.1016/j.phrs.2025.107894` (2025) - Effect of ketamine and esketamine on RNA expression and its relevance for depression: A systematic review.
- `10.1021/acsptsci.5c00440` (2025) - Hypoxia, Psychedelics, and Terminal Lucidity: A Perspective on Neuroplasticity and Neuropsychiatric Disorders.
- `10.1080/10408444.2023.2194907` (2023) - 25X-NBOMe compounds - chemistry, pharmacology and toxicology. A comprehensive review.
- `10.1080/14737175.2024.2445016` (2025) - Evaluating the value and risks of psychedelics for psychiatric medicine: a clinical perspective.
- `10.3892/etm.2021.10565` (2021) - Neuroplasticity and depression: Rewiring the brain's networks through pharmacological therapy (Review).

## disorder

| Metric | Count |
| --- | ---: |
| all_discovered_overlap | 266 |
| openalex_only_discovered | 519 |
| pubmed_only_discovered | 472 |
| new_doi_overlap | 37 |
| openalex_only_new_dois | 149 |
| pubmed_only_new_dois | 79 |
| combined_new_dois | 265 |

| Provider | Discovered DOIs | New DOIs | Title proxy among new DOIs |
| --- | ---: | ---: | --- |
| openalex | 785 | 186 | 115/186 both (61.8%), 14/186 neither (7.5%), 17/186 secondary-ish (9.1%) |
| pubmed | 738 | 116 | 49/116 both (42.2%), 14/116 neither (12.1%), 16/116 secondary-ish (13.8%) |

| Exclusive-new set | Title proxy |
| --- | --- |
| openalex_only | 99/149 both (66.4%), 11/149 neither (7.4%), 13/149 secondary-ish (8.7%) |
| pubmed_only | 33/79 both (41.8%), 11/79 neither (13.9%), 12/79 secondary-ish (15.2%) |

| Module | OpenAlex new | PubMed new | New overlap | OpenAlex only | PubMed only |
| --- | ---: | ---: | ---: | ---: | ---: |
| anxiety_distress_palliative | 23 | 7 | 0 | 23 | 7 |
| clinical_class_core | 10 | 7 | 0 | 10 | 7 |
| depression_spectrum | 13 | 4 | 0 | 13 | 4 |
| ibogaine_opioid_sud | 52 | 29 | 21 | 31 | 8 |
| ketamine_depression_suicidality | 15 | 4 | 0 | 15 | 4 |
| lsd_alcohol_anxiety | 21 | 11 | 3 | 18 | 8 |
| mdma_ptsd | 13 | 10 | 2 | 11 | 8 |
| ocd_eating_autism | 30 | 21 | 4 | 26 | 17 |
| pain_headache | 14 | 18 | 3 | 11 | 15 |
| psilocybin_depression | 4 | 2 | 1 | 3 | 1 |
| substance_use_addiction | 18 | 13 | 4 | 14 | 9 |
| trauma_ptsd | 21 | 15 | 1 | 20 | 14 |

### disorder / openalex_only_high_signal

- `10.1001/jamapsychiatry.2014.62` (2014) - Efficacy of Intravenous Ketamine for Treatment of Chronic Posttraumatic Stress Disorder
- `10.1002/ccr3.3869` (2021) - A longitudinal case series of IM ketamine for patients with severe and enduring eating disorders and comorbid treatment‐resistant depression
- `10.1002/ejp.624` (2014) - Efficacy and safety of oral ketamine for the relief of intractable chronic pain: A retrospective 5‐year study of 51 patients
- `10.1002/hup.2824` (2021) - Potential processes of change in MDMA‐Assisted therapy for social anxiety disorder: Enhanced memory reconsolidation, self‐transcendence, and therapeutic relationships
- `10.1002/vms3.70486` (2025) - Evaluating the Potential of Microdosing 1cp‐LSD for the Treatment of Canine Anxiety: A One‐Month Case Study
- `10.1007/7854_2017_34` (2018) - Subanesthetic Dose Ketamine in Posttraumatic Stress Disorder: A Role for Reconsolidation During Trauma-Focused Psychotherapy?
- `10.1007/978-1-4614-4866-2_17` (2012) - Use of the Classic Hallucinogen Psilocybin for Treatment of Existential Distress Associated with Cancer
- `10.1007/s00213-003-1452-8` (2003) - Increased anxiety and "depressive" symptoms months after MDMA ("ecstasy") in rats: drug-induced hyperthermia does not predict long-term outcomes

### disorder / openalex_only_possible_noise

- `10.1002/ddr.430080124` (1986) - Thymosthenic effects of ritanserin (R 55667), a centrally acting serotonin‐S<sub>2</sub> receptor blocker
- `10.1007/s00213-010-1911-y` (2010) - Determining the subjective effects of TFMPP in human males
- `10.1007/s12012-015-9311-5` (2015) - hERG Blockade by Iboga Alkaloids
- `10.1016/0005-7967(73)90080-6` (1973) - Biofeedback and self-control
- `10.1016/0006-8993(78)90124-5` (1978) - Increased dopamine metabolism in rat striatum after infusions of substance P into the substantia nigra
- `10.1016/0163-7258(89)90006-5` (1989) - Clinical pharmacology of anxiolytics and antidepressants: A psychopharmacological perspective
- `10.1016/0166-2236(90)90047-e` (1990) - Cortical circuits: Synaptic organization of the cerebral cortex. Structure, function and theory
- `10.1016/j.bpa.2014.02.003` (2014) - Perioperative analgesia and challenges in the drug-addicted and drug-dependent patient

### disorder / openalex_only_secondary

- `10.1016/0163-7258(89)90006-5` (1989) - Clinical pharmacology of anxiolytics and antidepressants: A psychopharmacological perspective
- `10.1016/j.addicn.2022.100025` (2022) - Classic and non‐classic psychedelics for substance use disorder: A review of their historic, past and current research
- `10.1016/j.ajp.2024.104242` (2024) - Exploring the regulatory framework of psychedelics in the US &amp; Europe
- `10.1016/j.jad.2020.09.007` (2020) - A systematic review and meta-analysis of the efficacy of intravenous ketamine infusion for treatment resistant depression: January 2009 – January 2019
- `10.1080/02791072.2020.1817639` (2020) - Efficacy of Psychoactive Drugs for the Treatment of Posttraumatic Stress Disorder: A Systematic Review of MDMA, Ketamine, LSD and Psilocybin
- `10.1097/hrp.0000000000000198` (2018) - Pain and Depression: A Systematic Review
- `10.1111/bcp.15374` (2022) - Ketamine treatment for refractory anxiety: A systematic review
- `10.1111/j.1360-0443.2011.03576.x` (2011) - Ketamine use: a review

### disorder / pubmed_only_high_signal

- `10.1001/jama.2018.8168` (2018) - MDMA-Assisted Psychotherapy for PTSD.
- `10.1001/jamanetworkopen.2024.45278` (2024) - Oxytocin and the Role of Fluid Restriction in MDMA-Induced Hyponatremia: A Secondary Analysis of 4 Randomized Clinical Trials.
- `10.1002/bcp.70579` (2026) - Exploring new avenues: Psychedelic-assisted therapy for young people.
- `10.1002/da.23065` (2020) - Historic psychedelic drug trials and the treatment of anxiety disorders.
- `10.1007/s11916-025-01360-9` (2025) - Ketamine Infusion for Complex Regional Pain Syndrome Treatment: A Narrative Review.
- `10.1007/s11920-026-01679-z` (2026) - Psilocybin-Assisted Therapy for Adolescent Anorexia Nervosa: Clinical Considerations and Emerging Models of Care.
- `10.1016/j.drugalcdep.2025.112861` (2025) - The effects of ketamine on methamphetamine withdrawal-induced anxiety and drug-seeking behaviors in the rat.
- `10.1016/j.jpsychires.2023.06.028` (2023) - Arketamine for bipolar depression: Open-label, dose-escalation, pilot study.

### disorder / pubmed_only_possible_noise

- `10.1007/7854_2023_443` (2023) - Enhancing Fear Extinction: Pharmacological Approaches.
- `10.1007/s40263-022-00929-x` (2022) - Pharmacological Management of Nightmares Associated with Posttraumatic Stress Disorder.
- `10.1016/j.bpa.2017.01.003` (2017) - Postcesarean delivery analgesia.
- `10.1016/j.neubiorev.2025.106209` (2025) - Demyelination in psychiatric and neurological disorders: Mechanisms, clinical impact, and novel therapeutic strategies.
- `10.1016/s0041-0101(00)00158-6` (2001) - Iboga interactions with psychomotor stimulants: panacea in the paradox?
- `10.1021/acsptsci.5c00301` (2026) - Development of Bioisosteres of Iboga Alkaloids: A Step-Economical Synthesis to Enhance the Antinociceptive and Anxiolytic Activity with Neuroprotective Effects.
- `10.1055/s-0030-1267531` (2010) - [Addicted anaesthetists].
- `10.1080/14737175.2024.2365946` (2024) - An update on pharmacotherapy for trigeminal neuralgia.

### disorder / pubmed_only_secondary

- `10.1007/s00406-024-01945-2` (2025) - Arketamine: a scoping review of its use in humans.
- `10.1007/s00415-022-11436-w` (2023) - Preventive treatment of refractory chronic cluster headache: systematic review and meta-analysis.
- `10.1007/s11916-025-01360-9` (2025) - Ketamine Infusion for Complex Regional Pain Syndrome Treatment: A Narrative Review.
- `10.1016/j.psychres.2024.115880` (2024) - Safety and risk assessment of psychedelic psychotherapy: A meta-analysis and systematic review.
- `10.1016/j.tmaid.2021.102206` (2021) - Ayahuasca and the traveller: A scoping review of risks and possible benefits.
- `10.1080/14656566.2022.2159373` (2023) - New frontiers in the pharmacological treatment of social anxiety disorder in adults: an up-to-date comprehensive overview.
- `10.1080/14656566.2026.2654682` (2026) - Psychedelic-assisted pharmacotherapy: clinical applications and regulatory considerations.
- `10.1097/aln.0000000000004673` (2023) - Use of Psychedelics for Pain: A Scoping Review.
