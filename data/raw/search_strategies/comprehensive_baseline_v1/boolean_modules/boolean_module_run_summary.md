# Boolean Module Discovery Summary

- Generated: 2026-05-15T06:07:38.142551+00:00
- Protocol: `comprehensive_baseline_v1`

## openalex

| Dataset | Seeds | Raw rows | Merged DOI rows | New DOIs | Rediscovered |
| --- | ---: | ---: | ---: | ---: | ---: |
| mechanistic | 10 | 1000 | 736 | 246 | 490 |
| disorder | 12 | 1200 | 785 | 186 | 599 |

### openalex / mechanistic

| Module | Type | Raw rows | Merged DOI mentions | New DOI mentions |
| --- | --- | ---: | ---: | ---: |
| serotonin_receptors | primary_boolean | 100 | 100 | 25 |
| monoamine_transporters | primary_boolean | 100 | 100 | 64 |
| glutamate_nmda | primary_boolean | 100 | 100 | 41 |
| opioid_sigma_taar | primary_boolean | 100 | 100 | 11 |
| plasticity_trkb_bdnf | primary_boolean | 100 | 100 | 61 |
| lsd_5ht2a | dense_topic | 100 | 100 | 21 |
| psilocin_5ht2a | dense_topic | 100 | 100 | 12 |
| mdma_transporters | dense_topic | 100 | 99 | 10 |
| ketamine_nmda | dense_topic | 100 | 100 | 42 |
| salvinorin_kor | dense_topic | 100 | 100 | 4 |

Representative new DOI samples:

- `10.1111/cns.14604` - Impaired synaptic plasticity and decreased excitability of hippocampal glutamatergic neurons mediated by <scp>BDNF</scp> downregulation contribute to cognitive dysfunction in mice induced by repeated neonatal exposure to ketamine
- `10.1016/j.neuropharm.2024.110156` - Ketamine reverses chronic corticosterone-induced behavioral deficits and hippocampal synaptic dysfunction by regulating eIF4E/BDNF signaling
- `10.1177/02698811241249436` - Psilocybin promotes neuroplasticity and induces rapid and sustained antidepressant-like effects in mice
- `10.1016/j.tibs.2024.02.001` - TrkB transmembrane domain: bridging structural understanding with therapeutic strategy
- `10.1016/j.biopsych.2023.02.587` - 347. Changes in Resting State Functional Connectivity After Psilocybin for Body Dysmorphic Disorder

### openalex / disorder

| Module | Type | Raw rows | Merged DOI mentions | New DOI mentions |
| --- | --- | ---: | ---: | ---: |
| clinical_class_core | primary_boolean | 100 | 100 | 10 |
| depression_spectrum | primary_boolean | 100 | 100 | 13 |
| trauma_ptsd | primary_boolean | 100 | 100 | 21 |
| substance_use_addiction | primary_boolean | 100 | 100 | 18 |
| anxiety_distress_palliative | primary_boolean | 100 | 100 | 23 |
| pain_headache | primary_boolean | 100 | 100 | 14 |
| ocd_eating_autism | primary_boolean | 100 | 100 | 30 |
| psilocybin_depression | dense_topic | 100 | 100 | 4 |
| mdma_ptsd | dense_topic | 100 | 100 | 13 |
| ketamine_depression_suicidality | dense_topic | 100 | 100 | 15 |
| ibogaine_opioid_sud | dense_topic | 100 | 100 | 52 |
| lsd_alcohol_anxiety | dense_topic | 100 | 100 | 21 |

Representative new DOI samples:

- `10.1002/vms3.70486` - Evaluating the Potential of Microdosing 1cp‐LSD for the Treatment of Canine Anxiety: A One‐Month Case Study
- `10.1016/j.glmedi.2025.100213` - Reconsidering Ibogaine for the treatment of severe mental illness and substance use disorders
- `10.1016/j.ajp.2024.104242` - Exploring the regulatory framework of psychedelics in the US &amp; Europe
- `10.1016/j.jad.2024.09.133` - Single-dose psilocybin for U.S. military Veterans with severe treatment-resistant depression – A first-in-kind open-label pilot study
- `10.1177/02698811231200882` - Main targets of ibogaine and noribogaine associated with its putative anti-addictive effects: A mechanistic overview

## pubmed

| Dataset | Seeds | Raw rows | Merged DOI rows | New DOIs | Rediscovered |
| --- | ---: | ---: | ---: | ---: | ---: |
| mechanistic | 10 | 995 | 723 | 159 | 563 |
| disorder | 12 | 1164 | 738 | 116 | 617 |

### pubmed / mechanistic

| Module | Type | Raw rows | Merged DOI mentions | New DOI mentions |
| --- | --- | ---: | ---: | ---: |
| serotonin_receptors | primary_boolean | 99 | 99 | 12 |
| monoamine_transporters | primary_boolean | 100 | 100 | 58 |
| glutamate_nmda | primary_boolean | 100 | 100 | 14 |
| opioid_sigma_taar | primary_boolean | 99 | 99 | 20 |
| plasticity_trkb_bdnf | primary_boolean | 100 | 100 | 50 |
| lsd_5ht2a | dense_topic | 98 | 98 | 1 |
| psilocin_5ht2a | dense_topic | 100 | 100 | 2 |
| mdma_transporters | dense_topic | 100 | 100 | 6 |
| ketamine_nmda | dense_topic | 100 | 100 | 12 |
| salvinorin_kor | dense_topic | 99 | 99 | 2 |

Representative new DOI samples:

- `10.1021/jacs.5c06325` - Deciphering Ibogaine's Matrix Pharmacology: Multiple Transporter Modulation at Serotonin Synapses.
- `10.1038/s41380-025-03257-w` - Psychedelic neuroplasticity of cortical neurons lacking 5-HT2A receptors.
- `10.1021/acschemneuro.5c00707` - Zalsupindole: A Non-Hallucinogenic Psychoplastogen Advancing Psychedelic-Inspired Therapeutics.
- `10.1055/a-2742-4611` - [Ketamine and esketamine in treatment-resistant depression - Pharmacological effects and augmented psychotherapy].
- `10.1186/s13195-025-01804-9` - Combinatorial targeting of NMDARs and 5-HT(4)Rs exerts beneficial effects in a mouse model of Alzheimer's disease.

### pubmed / disorder

| Module | Type | Raw rows | Merged DOI mentions | New DOI mentions |
| --- | --- | ---: | ---: | ---: |
| clinical_class_core | primary_boolean | 99 | 99 | 7 |
| depression_spectrum | primary_boolean | 100 | 100 | 4 |
| trauma_ptsd | primary_boolean | 98 | 98 | 15 |
| substance_use_addiction | primary_boolean | 98 | 98 | 13 |
| anxiety_distress_palliative | primary_boolean | 99 | 99 | 7 |
| pain_headache | primary_boolean | 94 | 94 | 18 |
| ocd_eating_autism | primary_boolean | 98 | 98 | 21 |
| psilocybin_depression | dense_topic | 100 | 97 | 2 |
| mdma_ptsd | dense_topic | 98 | 98 | 10 |
| ketamine_depression_suicidality | dense_topic | 99 | 99 | 4 |
| ibogaine_opioid_sud | dense_topic | 84 | 84 | 29 |
| lsd_alcohol_anxiety | dense_topic | 97 | 97 | 11 |

Representative new DOI samples:

- `10.1111/head.70016` - 2025 guideline update to acute treatment of migraine for adults in the emergency department: The American Headache Society evidence assessment of parenteral pharmacotherapies.
- `10.1007/7854_2026_614` - Classifying Psychedelic-Related Complications.
- `10.1021/acsptsci.5c00301` - Development of Bioisosteres of Iboga Alkaloids: A Step-Economical Synthesis to Enhance the Antinociceptive and Anxiolytic Activity with Neuroprotective Effects.
- `10.1002/bcp.70579` - Exploring new avenues: Psychedelic-assisted therapy for young people.
- `10.1176/appi.ajp.20250554` - Inner-Directed Therapy in MDMA-Assisted Psychotherapy.
