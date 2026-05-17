# Search Strategy

This document records the literature-search vocabulary and source-specific
query structure. It is intended as a methods appendix for readers who want to
audit what the search could and could not retrieve.

The search is documented in `docs/comprehensive_search_protocol_v2.md` and
generated under `data/raw/search_strategies/comprehensive_baseline_v1/`. The
search run is timestamped May 15, 2026.

## Main Search Layer

The search uses provider-specific query modules in PubMed for curated
biomedical indexing and OpenAlex for broader scholarly coverage. Each module is
built from three concept blocks:

```text
(compound or drug-class synonyms)
AND (target-family or indication-family synonyms)
AND (evidence-context terms)
```

Terms inside each concept block are joined with OR. PubMed queries use
`[Title/Abstract]` fields; clinical-indication PubMed queries also apply
`NOT (animals[MeSH Terms] NOT humans[MeSH Terms])`. Mechanistic target
searches do not use that exclusion; animal, in vitro, and assay records are
retained for mechanistic evidence. OpenAlex modules submit the generated query
text through the works search API. No publication-date or language restriction
is applied at discovery.

Exact generated artifacts:

- `data/raw/search_strategies/comprehensive_baseline_v1/boolean_modules/mechanistic_boolean_openalex_seeds.csv`
- `data/raw/search_strategies/comprehensive_baseline_v1/boolean_modules/mechanistic_boolean_pubmed_seeds.csv`
- `data/raw/search_strategies/comprehensive_baseline_v1/boolean_modules/disorder_boolean_openalex_seeds.csv`
- `data/raw/search_strategies/comprehensive_baseline_v1/boolean_modules/disorder_boolean_pubmed_seeds.csv`
- `data/raw/search_strategies/comprehensive_baseline_v1/boolean_modules/boolean_search_modules_manifest.json`

The code sources of truth are
`pipeline/ingest/build_boolean_search_modules.py`,
`pipeline/ingest/discover_literature.py`, and
`pipeline/ingest/add_new_dois.py`. The validation allowlists are in
`pipeline/config.example.yaml`.

## Search Modules

Module counts below are conceptual modules; each module is run once in
OpenAlex syntax and once in PubMed syntax.

| Dataset | Query modules | Primary broad modules | Dense topic modules | Primary cap | Dense cap |
|---|---:|---:|---:|---:|---:|
| Mechanistic | 10 | 5 | 5 | 500 | 1,000 |
| Disorder | 12 | 7 | 5 | 500 | 1,000 |

Clinical indication modules:

| Type | Modules | Query block pattern |
|---|---|---|
| Primary broad | clinical class core; depression spectrum; trauma/PTSD; substance use and addiction; anxiety, distress, and palliative care; pain and headache; OCD, eating disorders, and autism | therapeutic psychedelic terms AND indication-family terms AND clinical evidence terms |
| Dense topic | psilocybin-depression; MDMA-PTSD; ketamine-depression-suicidality; ibogaine-opioid/substance use disorder; LSD-alcohol/anxiety | narrower compound terms AND narrower indication terms AND clinical evidence terms |

Mechanistic target modules:

| Type | Modules | Query block pattern |
|---|---|---|
| Primary broad | serotonin receptors; monoamine transporters; glutamate/NMDA; opioid, sigma, and TAAR targets; plasticity, TrkB, and BDNF pathways | psychedelic compound/class terms AND target-family terms AND assay/signaling evidence terms |
| Dense topic | LSD-5-HT2A; psilocin/psilocybin-5-HT2A; MDMA transporters; ketamine-NMDA; salvinorin A-kappa opioid receptor | narrower compound terms AND narrower target terms AND assay/signaling evidence terms |

Clinical evidence terms include clinical trial, randomized/randomised, placebo,
open-label/open label, phase 2, phase 3, treatment, therapy, efficacy, safety,
tolerability, outcome, and follow-up. Mechanistic evidence terms include
binding, affinity, Ki, Kd, IC50, EC50, radioligand, functional assay, agonist,
antagonist, partial agonist, and signaling.

## Pairwise Search Layer

The canonical registries also generate direct searches for compound-target and
compound-indication combinations. These searches use the same scope vocabulary
as the main query modules and include rare combinations that may not be well
represented by family-level queries.

With the current canonical allowlists, focused all-pair generation creates
1,840 mechanistic compound-target pairs and 1,240 clinical
compound-indication pairs. Broad template mode expands those to 5,520
mechanistic pair-core search seeds and 3,717 clinical pair-core search seeds.

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

## Canonical Disorder Allowlist

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

### Disorder Aliases

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
- DOI-normalization and deduplication rules,
- record-flow outputs for PRISMA-style reporting.

Search results are not graph evidence. Retrieved records enter the screening,
retrieval, extraction, and validation pipeline before they can support a graph
edge.
