# Search Strategy

This document records the literature-search vocabulary and source-specific
query structure. It is intended as a methods appendix for readers who want to
audit what the search could and could not retrieve.

The search is documented in `docs/comprehensive_search_protocol_v2.md` and in
the generated search artifacts under `data/raw/search_strategies/`. The strategy
is described as one integrated first-build discovery pipeline; generated
artifacts are preserved for provenance and auditability. Additional
domain-module details are recorded in `docs/brain_cognition_search_strategy.md`
and `docs/evidence_domain_search_modules.md`.

## Main Search Layer

The search uses provider-specific query modules in PubMed for curated
biomedical indexing and OpenAlex for broader scholarly coverage. Modules are
organized by evidence domain and built from three concept blocks:

```text
(compound or drug-class synonyms)
AND (domain-specific entity, endpoint, or outcome synonyms)
AND (evidence-context terms)
```

Terms inside each concept block are joined with OR. PubMed queries use
`[Title/Abstract]` fields. Clinical population and outcome modules apply
`NOT (animals[MeSH Terms] NOT humans[MeSH Terms])`; molecular, brain-system,
cognitive-behavioral, and preclinical/translational modules retain animal, in
vitro, assay, and neurophysiology records when those records are in scope.
OpenAlex modules submit the generated query text through the works search API.
No publication-date or language restriction is applied at discovery.

Generated artifact families:

- `data/raw/search_strategies/comprehensive_baseline_v1/boolean_modules/`
- `data/raw/search_strategies/comprehensive_baseline_v1/direct_pairs/`
- `data/raw/search_strategies/systems_neuroscience_2026_05/grouped_modules/`
- `data/raw/search_strategies/systems_neuroscience_2026_05/direct_pairs/`
- `data/raw/search_strategies/evidence_domain_modules_2026_05/grouped_modules/`
- `data/raw/search_strategies/extraction_gap_domains_2026_05/grouped_modules/`
- `data/raw/search_strategies/extraction_gap_domains_keyword_closure_2026_05/grouped_modules/`

Some artifact filenames preserve earlier processing names. In the methods
framing, those files are treated as domain-specific search instruments within
the same discovery pipeline.

The code sources of truth are
`pipeline/ingest/build_boolean_search_modules.py`,
`pipeline/ingest/discover_literature.py`, and
`pipeline/ingest/add_new_dois.py`. The validation allowlists are in
`pipeline/config.example.yaml`.

## Search Modules

Module counts below are conceptual grouped modules. Each module is generated in
provider-specific syntax for PubMed and OpenAlex when supported by the run.

| Evidence domain | Query modules | Broad modules | Focused modules | Broad cap | Focused cap |
|---|---:|---:|---:|---:|---:|
| Molecular targets | 10 | 5 | 5 | 500 | 1,000 |
| Molecular pathways and cellular readouts | 5 | 3 | 2 | 500 | 1,000 |
| Brain systems, circuits, and neurophysiology | 10 | 4 | 6 | 500 | 1,000 |
| Cognitive and behavioral function | 4 | 2 | 2 | 500 | 1,000 |
| Subjective experience and acute effects | 2 | 1 | 1 | 500 | 1,000 |
| Pharmacokinetics and exposure | 2 | 1 | 1 | 500 | 1,000 |
| Intervention delivery context | 2 | 1 | 1 | 500 | 1,000 |
| Real-world use and public health | 2 | 1 | 1 | 500 | 1,000 |
| Clinical outcomes, symptoms, functioning, and safety | 17 | 9 | 8 | 500 | 1,000 |
| Clinical studies with biological and behavioral endpoints | 6 | 2 | 4 | 500 | 1,000 |

Molecular target modules:

| Type | Modules | Query block pattern |
|---|---|---|
| Broad | serotonin receptors; monoamine transporters; glutamate/NMDA/AMPA/mGluR2 targets; opioid, sigma, and TAAR targets; plasticity, TrkB, and BDNF target evidence | compound/class terms AND target-family terms AND assay/signaling evidence terms |
| Focused | LSD-5-HT2A; psilocin/psilocybin-5-HT2A; MDMA transporters; ketamine-NMDA; salvinorin A-kappa opioid receptor | narrower compound terms AND narrower target terms AND assay/signaling evidence terms |

Molecular pathway and cellular-readout modules:

| Type | Modules | Query block pattern |
|---|---|---|
| Broad | molecular pathway plasticity; gene expression and transcriptomics; inflammatory and neuroendocrine molecular readouts | compound/class terms AND pathway/readout terms AND molecular evidence terms |
| Focused | ketamine/psychedelic mTOR-synaptogenesis; psychedelic immediate early genes | narrower compound-pathway combinations AND gene/protein expression, signaling, and plasticity evidence terms |

Brain-system and cognitive-behavioral modules:

| Type | Modules | Query block pattern |
|---|---|---|
| Broad | systems neuroimaging and connectivity; brain regions and named circuits; PET, receptor occupancy, and metabolism; EEG, MEG, and neurophysiology; cognitive and affective task domains; translational behavioral assays | compound/class terms AND brain/circuit/network/task terms AND imaging, neurophysiology, task, or behavior evidence terms |
| Focused | psilocybin-default mode connectivity; LSD-thalamocortical connectivity; DMT EEG/fMRI dynamics; ayahuasca-default mode connectivity; psilocybin PET/5-HT2A occupancy; ketamine prefrontal-hippocampal circuitry; MDMA social reward and cognition; psychedelic fear extinction and flexibility | narrower compound-entity combinations AND domain-specific evidence terms |

Subjective experience and exposure modules:

| Type | Modules | Query block pattern |
|---|---|---|
| Broad | acute subjective effects and phenomenology; pharmacokinetics and exposure | compound/class terms AND subjective-effect, phenomenology, exposure, or ADME terms AND questionnaire, concentration, dosing, sampling, or analytical measurement terms |
| Focused | subjective-effect measures; metabolite and exposure measurement | narrower compound-measure combinations AND psychometric, acute-effect, metabolite, plasma/serum/blood-level, dose, route, excretion, protein-binding, and mass-spectrometry terms |

Intervention-context and real-world/public-health modules:

| Type | Modules | Query block pattern |
|---|---|---|
| Broad | psychotherapy, preparation, integration, set and setting, session structure, psychological support, aftercare, blinding, training/manual terms; epidemiology, surveys, naturalistic use, lifetime or past-year use, drug checking, poison-control/emergency records, toxicity, and harm reduction | therapeutic psychedelic terms AND delivery-context or public-health terms AND clinical, feasibility, acceptability, observational, population, risk, adverse-event, or outcome terms |
| Focused | set/setting and therapeutic-support details; naturalistic, community, retreat, and microdosing use | narrower compound-context combinations AND qualitative, clinical, observational, survey, wellbeing, mental-health, adverse-experience, toxicity, and harm-reduction terms |

Clinical evidence modules:

| Type | Modules | Query block pattern |
|---|---|---|
| Broad | clinical class core; depression spectrum; PTSD and trauma; substance use and addiction; anxiety, distress, and palliative care; pain, headache, and migraine; OCD, eating disorders, and autism; symptoms, functioning, and quality of life; safety, tolerability, and adverse events | therapeutic psychedelic terms AND condition/outcome/safety terms AND clinical evidence terms |
| Focused | psilocybin-depression; MDMA-PTSD; ketamine-depression-suicidality; ibogaine-opioid/substance use disorder; LSD-alcohol/anxiety; suicidality, anhedonia, sleep, and function; craving, relapse, and functioning; cardiovascular, mania, psychosis, and HPPD safety | narrower compound-condition or compound-outcome combinations AND clinical evidence terms |

Clinical biological and behavioral endpoint modules:

| Type | Modules | Query block pattern |
|---|---|---|
| Broad | clinical population modules with brain, molecular, cognitive, and behavioral endpoints; clinical outcome endpoint modules | compound/class terms AND clinical population/outcome terms AND biological, cognitive, behavioral, imaging, neurophysiology, or molecular endpoint terms |
| Focused | psilocybin depression brain and molecular endpoints; ketamine depression molecular endpoints; psilocybin depression brain/molecular endpoints; MDMA PTSD social-brain endpoints | narrower compound-condition combinations AND endpoint terms |

Clinical evidence terms include clinical trial, randomized/randomised, placebo,
open-label/open label, phase 2, phase 3, treatment, therapy, efficacy, safety,
tolerability, outcome, and follow-up. Molecular target terms include binding,
affinity, Ki, Kd, IC50, EC50, radioligand, functional assay, agonist,
antagonist, partial agonist, and signaling. Brain, cognitive, behavioral,
molecular-pathway, and clinical endpoint modules use endpoint-specific imaging,
neurophysiology, task, behavior, gene/protein expression, pathway, safety, and
functioning terms.

## Pairwise Search Layer

The canonical registries also support direct searches for compound-entity and
compound-outcome combinations. These searches are supplementary to the grouped
domain modules. They are used most densely where the pair space is bounded, such
as molecular targets and clinical conditions, symptoms, functioning outcomes,
and safety outcomes, and as targeted checks for later domain additions where
sparse records may not be well represented by family-level queries.

The generated pairwise materials include:

- 1,840 compound-target pairs searched with binding-affinity,
  receptor-pharmacology, and functional-assay query forms. These are included
  in the target/brain/task pair layer.
- 5,440 compound-entity pairs across molecular targets, brain regions/networks,
  and cognitive-behavioral tasks, producing 16,320 pair-core search strings and
  16,876 total generated strings when sentinel, class-level, compound-broad,
  and entity-broad searches are included.
- 1,240 compound-clinical evidence pairs searched with randomized-placebo,
  treatment-outcome, and clinical-trial query forms, producing 3,717 generated
  search strings.

After the additional domain searches, a targeted direct-pair check was run for
selected compound/entity/outcome combinations in PubMed and OpenAlex. Records
found through that check enter the same candidate corpus as the grouped search
modules and retain their pair-search provenance.

## Canonical Compound Allowlist

LSD; Psilocybin; Psilocin; Mescaline; DMT; 5-MeO-DMT; Bufotenin; Ayahuasca;
Ibogaine; Noribogaine; MDMA; MDA; Ketamine; S-ketamine; R-ketamine; DOI; DOB;
DOM; DOET; 2C-B; 2C-E; 2C-I; 2C-T-2; 2C-T-7; 5-MeO-DiPT; DiPT; DPT; LSA;
AL-LAD; ETH-LAD; PRO-LAD; 1P-LSD; Salvinorin A; Lisuride; Bromo-DragonFLY;
25I-NBOMe; 25B-NBOMe; 25C-NBOMe; TMA; TMA-2.

## Canonical Target Allowlist

5-HT2A; 5-HT2B; 5-HT2C; 5-HT1A; 5-HT1B; 5-HT1D; 5-HT1E; 5-HT1F; 5-HT5A;
5-HT6; 5-HT7; mGluR2 (GRM2); TAAR1; SERT (SLC6A4); NET (SLC6A2); DAT
(SLC6A3); VMAT2 (SLC18A2); D1 receptor (DRD1); D2 receptor (DRD2); D3
receptor (DRD3); D4 receptor (DRD4); D5 receptor (DRD5); Alpha1A adrenergic
receptor (ADRA1A); Alpha1B adrenergic receptor (ADRA1B); Alpha2A adrenergic
receptor (ADRA2A); Alpha2B adrenergic receptor (ADRA2B); Alpha2C adrenergic
receptor (ADRA2C); Beta1 adrenergic receptor (ADRB1); Beta2 adrenergic receptor
(ADRB2); M1 muscarinic receptor (CHRM1); M2 muscarinic receptor (CHRM2); M3
muscarinic receptor (CHRM3); M4 muscarinic receptor (CHRM4); M5 muscarinic
receptor (CHRM5); H1 receptor (HRH1); H2 receptor (HRH2); Sigma-1 receptor
(SIGMAR1); Sigma-2 receptor (TMEM97); kappa opioid receptor (OPRK1); mu opioid
receptor (OPRM1); delta opioid receptor (OPRD1); NMDA receptor; AMPA receptor;
TrkB (NTRK2); CB1 receptor (CNR1); CB2 receptor (CNR2).

## Canonical Brain Region And Network Allowlist

Prefrontal cortex; Medial prefrontal cortex; Orbitofrontal cortex; Anterior
cingulate cortex; Posterior cingulate cortex; Cingulate cortex; Visual cortex;
Somatosensory cortex; Insula; Hippocampus; Ventral hippocampus; Dorsal
hippocampus; Amygdala; Basolateral amygdala; Central amygdala; Striatum;
Ventral striatum; Dorsal striatum; Nucleus accumbens; Caudate; Putamen;
Thalamus; Mediodorsal thalamus; Reticular thalamus; Claustrum; Habenula;
Lateral habenula; Dorsal raphe nucleus; Raphe nucleus; Ventral tegmental area;
Locus coeruleus; Periaqueductal gray; Default mode network; Salience network;
Frontoparietal network; Central executive network; Limbic network; Visual
network; Sensorimotor network; Thalamo-cortical circuit; Cortico-striatal
circuit; Cortical-subcortical circuit; Fronto-limbic circuit;
Hippocampal-prefrontal circuit; Amygdala-prefrontal circuit; Mesolimbic reward
circuit.

## Canonical Cognitive And Behavioral Task Allowlist

Cognitive flexibility; Reversal learning; Probabilistic reversal learning; Set
shifting; Attentional set shifting; Wisconsin Card Sorting Test; Go/no-go task;
Stop-signal task; Delay discounting; Fear conditioning; Fear extinction;
Extinction learning; Threat processing; Startle response; Prepulse inhibition;
Conditioned freezing; Reward learning; Reinforcement learning; Social reward
learning; Monetary incentive delay task; Sucrose preference; Conditioned place
preference; Self-administration; Drug seeking; Relapse behavior; Emotional
processing; Emotion recognition; Facial emotion recognition; Social cognition;
Empathy; Theory of mind; Social behavior; Social interaction; Attention;
Continuous performance task; Working memory; Novel object recognition; Spatial
memory; Forced swim test; Tail suspension test; Learned helplessness; Chronic
social defeat; Open field test; Elevated plus maze.

## Canonical Clinical Evidence Concept Allowlist

Treatment-resistant depression; Major depressive disorder; Bipolar depression;
Persistent depressive disorder; Post-traumatic stress disorder; Complex
post-traumatic stress disorder; Alcohol use disorder; Tobacco use disorder;
Nicotine dependence; Opioid use disorder; Cannabis use disorder; Cocaine use
disorder; Methamphetamine use disorder; Stimulant use disorder; Substance use
disorder; Generalized anxiety disorder; Social anxiety disorder; Distress
associated with life-threatening disease; Obsessive-compulsive disorder; Eating
disorders; Anorexia nervosa; Bulimia nervosa; Binge-eating disorder; Autism
spectrum disorder; Demoralization; Suicidal ideation; Cluster headache;
Headache disorders; Migraine; Chronic pain; Fibromyalgia.

## Alias Rules Used For Query Variants

### Compound Aliases

- LSD: LSD; lysergic acid diethylamide
- Psilocybin: psilocybin
- Psilocin: psilocin; psilocyn
- DMT: DMT; N,N-dimethyltryptamine; dimethyltryptamine
- 5-MeO-DMT: 5-MeO-DMT; 5-methoxy-N,N-dimethyltryptamine
- Mescaline: mescaline
- MDMA: MDMA; 3,4-methylenedioxymethamphetamine; ecstasy
- MDA: MDA; 3,4-methylenedioxyamphetamine
- Ketamine: ketamine; norketamine
- S-ketamine: esketamine; S-ketamine
- R-ketamine: arketamine; R-ketamine
- Ayahuasca: ayahuasca
- Ibogaine: ibogaine
- Noribogaine: noribogaine
- Salvinorin A: salvinorin A

### Target Aliases

- 5-HT2A: 5-HT2A; HTR2A; serotonin 2A receptor; 5-hydroxytryptamine 2A receptor
- 5-HT2B: 5-HT2B; HTR2B; serotonin 2B receptor
- 5-HT2C: 5-HT2C; HTR2C; serotonin 2C receptor
- 5-HT1A: 5-HT1A; HTR1A; serotonin 1A receptor
- SERT (SLC6A4): SERT; SLC6A4; serotonin transporter; 5-HTT
- DAT (SLC6A3): DAT; SLC6A3; dopamine transporter
- NET (SLC6A2): NET; SLC6A2; norepinephrine transporter; noradrenaline transporter
- NMDA receptor: NMDA receptor; NMDAR; glutamate receptor
- Sigma-1 receptor (SIGMAR1): sigma-1 receptor; SIGMAR1; sigma 1 receptor
- TAAR1: TAAR1; trace amine-associated receptor 1; trace amine receptor 1
- kappa opioid receptor (OPRK1): kappa opioid receptor; OPRK1; KOR
- mGluR2 (GRM2): mGluR2; GRM2; metabotropic glutamate receptor 2
- TrkB: TrkB; NTRK2; BDNF receptor

### Clinical Evidence Concept Aliases

- Treatment-resistant depression: treatment-resistant depression; TRD; resistant depression
- Major depressive disorder: major depressive disorder; MDD; depression
- Bipolar depression: bipolar depression; bipolar disorder; bipolar I; bipolar II
- Persistent depressive disorder: persistent depressive disorder; dysthymia
- Post-traumatic stress disorder: post-traumatic stress disorder; PTSD
- Alcohol use disorder: alcohol use disorder; AUD; alcohol dependence
- Tobacco use disorder: tobacco use disorder; smoking cessation; nicotine dependence
- Opioid use disorder: opioid use disorder; opioid dependence
- Cannabis use disorder: cannabis use disorder; cannabis dependence
- Cocaine use disorder: cocaine use disorder; cocaine dependence
- Methamphetamine use disorder: methamphetamine use disorder; methamphetamine dependence
- Stimulant use disorder: stimulant use disorder; stimulant dependence
- Substance use disorder: substance use disorder; drug dependence
- Generalized anxiety disorder: generalized anxiety disorder; GAD
- Social anxiety disorder: social anxiety disorder; social anxiety
- distress associated with life-threatening disease: life-threatening cancer; cancer anxiety; cancer depression; end-of-life anxiety; existential distress
- Obsessive-compulsive disorder: obsessive-compulsive disorder; OCD
- Anorexia nervosa: anorexia nervosa
- Bulimia nervosa: bulimia nervosa; bulimia
- Binge-eating disorder: binge-eating disorder; binge eating disorder
- Eating disorders: eating disorder; eating disorders; disordered eating
- Autism spectrum disorder: autism spectrum disorder; autism; ASD
- Demoralization: demoralization; demoralisation
- Suicidal ideation: suicidal ideation; suicidality
- Cluster headache: cluster headache
- Headache disorders: headache disorder; headache disorders; headache
- Migraine: migraine; migraine disorder
- Chronic pain: chronic pain
- Fibromyalgia: fibromyalgia

## Reproducibility Notes

The search is reproducible from the generated CSV and manifest files. For
publication-quality reporting, preserve:

- protocol ID and generated search-file hashes,
- database searched and date searched,
- exact source-specific query strings,
- field restrictions and clinical animal/human filters,
- per-module retrieval caps,
- module scope and evidence-domain labels,
- DOI-normalization and deduplication rules,
- record-flow outputs for PRISMA-style reporting.

Search results are not graph evidence. Retrieved records enter the screening,
retrieval, extraction, and validation pipeline before they can support a graph
edge.
