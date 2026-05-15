# Search Seed Strategy

This document records the seed vocabulary used for literature discovery. It is
intended as a methods appendix for readers who want to audit what the search
could and could not retrieve. The current checked-in discovery reports are
starter-pair searches, not exhaustive searches over every possible
compound-indication or compound-target combination.

For the v2 baseline search, use `docs/comprehensive_search_protocol_v2.md` and
the generated seed manifests under
`data/raw/search_strategies/comprehensive_baseline_v1/`. The older 24/41 seed
reports below should be interpreted as scoping runs and search-development
evidence, not as the final comprehensive strategy.

The current implementation uses three layers:

1. Default hand-written seeds for each dataset.
2. Canonical compound, target, and disorder allowlists used for validation and
   optional generated seed expansion.
3. Alias and query-template rules used for provider-specific query variants and
   broader coverage runs.

Only the first layer, plus provider-specific query variants for those default
pairs, was used in the current checked-in reports. The canonical allowlists and
generated-seed modes define what broader searches can use, but their presence in
the repository does not mean every listed term was submitted to the literature
APIs in the current run.

Exact seeds used in a discovery run are recorded in the discovery report under
`per_seed`, with seed counts and provider query counts under `counts`. The
current checked-in reports are:

- `data/processed/discovery_report_mechanistic.json`
- `data/processed/discovery_report_disorder.json`

The code source of truth is `pipeline/ingest/discover_literature.py`. The
validation allowlists are in `pipeline/config.example.yaml`.

## Current Discovery Report Seed Counts

| Dataset | Seed count | Manual | Default | Auto-expanded | Balanced |
|---|---:|---:|---:|---:|---:|
| Mechanistic | 24 | 0 | 24 | 0 | 0 |
| Disorder | 41 | 0 | 41 | 0 | 0 |

These counts mean the current reports did not use the all-pair generated search
space. To search all canonical compound-disorder or compound-target pairs, the
pipeline must be run with generated seeds enabled, for example
`--expand-seeds-from-config --auto-max-pairs 0 --auto-max-seeds 0`. With the
current canonical allowlists, focused all-pair generation would create 1,240
clinical compound-disorder seeds and 1,840 mechanistic compound-target seeds;
broad template mode would create 3,720 and 5,520 seeds, respectively. If the
default `--auto-max-pairs 400` cap is left in place, only the first 400
compound-entity pairs are searched.

## Default Mechanistic Seeds

| Query | Compound | Target |
|---|---|---|
| LSD 5-HT2A receptor binding affinity Ki radioligand | LSD | 5-HT2A |
| LSD 5-HT2C receptor binding affinity | LSD | 5-HT2C |
| psilocin 5-HT2A receptor binding affinity | Psilocin | 5-HT2A |
| psilocin 5-HT1A receptor binding affinity | Psilocin | 5-HT1A |
| psilocybin psilocin 5-HT2A agonist receptor | Psilocybin | 5-HT2A |
| DMT 5-HT2A receptor binding affinity | DMT | 5-HT2A |
| DMT sigma-1 receptor binding affinity | DMT | Sigma-1 receptor (SIGMAR1) |
| psychedelic TAAR1 trace amine receptor 1 binding | DMT | TAAR1 |
| 5-MeO-DMT 5-HT1A receptor binding affinity | 5-MeO-DMT | 5-HT1A |
| mescaline 5-HT2A receptor binding affinity | Mescaline | 5-HT2A |
| MDMA SERT DAT NET transporter affinity | MDMA | SERT (SLC6A4) |
| MDMA dopamine transporter DAT affinity | MDMA | DAT (SLC6A3) |
| MDMA norepinephrine transporter NET affinity | MDMA | NET (SLC6A2) |
| MDMA SERT amphetamine serotonin transporter CaMKII | MDMA | SERT (SLC6A4) |
| MDMA enantiomers MPTP-lesioned primate SERT in vitro | MDMA | SERT (SLC6A4) |
| ibogaine noribogaine kappa opioid receptor binding | Ibogaine | kappa opioid receptor (OPRK1) |
| ibogaine NMDA receptor binding affinity | Ibogaine | NMDA receptor |
| ketamine NMDA receptor affinity binding Ki | Ketamine | NMDA receptor |
| esketamine NMDA receptor affinity binding | S-ketamine | NMDA receptor |
| arketamine NMDA receptor affinity binding | R-ketamine | NMDA receptor |
| salvinorin A kappa opioid receptor affinity | Salvinorin A | kappa opioid receptor (OPRK1) |
| 2C-B 5-HT2A receptor binding affinity | 2C-B | 5-HT2A |
| DOI 5-HT2A receptor binding affinity | DOI | 5-HT2A |
| psychedelic mGluR2 GRM2 receptor interaction | LSD | mGluR2 (GRM2) |

## Default Disorder Seeds

| Query | Compound | Disorder |
|---|---|---|
| psilocybin treatment-resistant depression randomized trial | Psilocybin | Treatment-resistant depression |
| psilocybin major depressive disorder randomized trial | Psilocybin | Major depressive disorder |
| ayahuasca major depressive disorder trial | Ayahuasca | Major depressive disorder |
| ayahuasca social anxiety disorder randomized trial | Ayahuasca | Social anxiety disorder |
| ayahuasca obsessive-compulsive disorder trial | Ayahuasca | Obsessive-compulsive disorder |
| ayahuasca generalized anxiety disorder trial | Ayahuasca | Generalized anxiety disorder |
| ketamine treatment-resistant depression trial | Ketamine | Treatment-resistant depression |
| ketamine bipolar depression randomized trial | Ketamine | Bipolar depression |
| esketamine treatment-resistant depression phase 3 | S-ketamine | Treatment-resistant depression |
| ketamine suicidal ideation randomized trial | Ketamine | Suicidal ideation |
| MDMA post-traumatic stress disorder randomized trial | MDMA | Post-traumatic stress disorder |
| LSD anxiety life-threatening disease trial | LSD | distress associated with life-threatening disease |
| LSD major depressive disorder randomized trial | LSD | Major depressive disorder |
| LSD generalized anxiety disorder randomized trial | LSD | Generalized anxiety disorder |
| LSD alcohol use disorder trial | LSD | Alcohol use disorder |
| psilocybin cancer anxiety depression trial | Psilocybin | distress associated with life-threatening disease |
| psilocybin generalized anxiety disorder trial | Psilocybin | Generalized anxiety disorder |
| psilocybin bipolar depression trial | Psilocybin | Bipolar depression |
| mescaline major depressive disorder clinical trial | Mescaline | Major depressive disorder |
| 5-MeO-DMT major depressive disorder clinical trial | 5-MeO-DMT | Major depressive disorder |
| MDMA autism spectrum disorder social anxiety trial | MDMA | Autism spectrum disorder |
| psilocybin obsessive-compulsive disorder trial | Psilocybin | Obsessive-compulsive disorder |
| psilocybin anorexia nervosa trial | Psilocybin | Anorexia nervosa |
| psilocybin eating disorders trial | Psilocybin | Eating disorders |
| psilocybin bulimia nervosa trial | Psilocybin | Bulimia nervosa |
| psilocybin binge eating disorder trial | Psilocybin | Binge-eating disorder |
| psilocybin alcohol use disorder randomized trial | Psilocybin | Alcohol use disorder |
| psilocybin tobacco use disorder trial | Psilocybin | Tobacco use disorder |
| ibogaine opioid use disorder trial | Ibogaine | Opioid use disorder |
| ketamine alcohol use disorder trial | Ketamine | Alcohol use disorder |
| psilocybin cocaine use disorder trial | Psilocybin | Cocaine use disorder |
| psilocybin methamphetamine use disorder trial | Psilocybin | Methamphetamine use disorder |
| psilocybin substance use disorder trial | Psilocybin | Substance use disorder |
| psilocybin end-of-life anxiety trial | Psilocybin | distress associated with life-threatening disease |
| LSD cluster headache trial | LSD | Cluster headache |
| psilocybin cluster headache trial | Psilocybin | Cluster headache |
| psychedelic headache disorders migraine trial | Any in-scope compound | Headache disorders |
| psilocybin migraine headache trial | Psilocybin | Migraine |
| ketamine chronic pain trial | Ketamine | Chronic pain |
| ketamine fibromyalgia randomized trial | Ketamine | Fibromyalgia |
| psilocybin fibromyalgia clinical trial | Psilocybin | Fibromyalgia |

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

## Generated Seed Templates

Focused and broad auto-seed modes generate seed strings from the canonical
allowlists. These modes are used for higher-recall runs and should be reported
with their caps.

### Mechanistic

- Focused: `{compound} {entity} receptor binding affinity Ki`
- Broad:
  - `{compound} {entity} receptor binding affinity Ki`
  - `{compound} {entity} radioligand binding affinity`
  - `{compound} {entity} pharmacology assay affinity`

### Disorder

- Focused: `{compound} {entity} randomized clinical trial`
- Broad:
  - `{compound} {entity} randomized clinical trial`
  - `{compound} {entity} phase 2 phase 3 trial`
  - `{compound} {entity} therapeutic outcome study`

## Balanced Coverage Templates

Balanced seed profiles add bounded compound-only and entity-only searches to
avoid losing allowlist items that are not represented in the default hand-written
seeds.

### Mechanistic

- Compound coverage:
  - `{compound} pharmacology binding affinity receptor transporter`
  - `{compound} mechanism target receptor transporter`
- Entity coverage:
  - `{entity} psychedelic pharmacology binding affinity`
  - `{entity} receptor transporter psychedelic assay`
- Evidence-focused follow-up:
  - `{compound} {entity} binding affinity Ki`
  - `{compound} {entity} radioligand binding`
  - `{compound} {entity} functional assay agonist antagonist`
  - `{compound} {entity} signaling beta arrestin calcium cAMP`
  - `{compound} {entity} transporter uptake release`

### Disorder

- Compound coverage:
  - `{compound} clinical trial treatment safety`
  - `{compound} therapeutic outcome psychedelic`
- Entity coverage:
  - `{entity} psychedelic clinical trial treatment`
  - `{entity} psychedelic therapy outcome safety`
- Evidence-focused follow-up:
  - `{compound} {entity} randomized clinical trial`
  - `{compound} {entity} open label trial`
  - `{compound} {entity} safety tolerability`
  - `{compound} {entity} follow-up outcome`
  - `{compound} {entity} remission response adverse events`

## Interpretation

The seed list is not evidence. It is a search instrument. The key audit
questions are:

- Are important compound aliases missing?
- Are important indication or target terms missing?
- Are seed caps excluding large parts of the planned search space?
- Do known relevant studies appear in discovery outputs?
- Are missed known studies fixed by better seeds, citation chasing, source
  coverage, or documented as outside scope?

For publication-quality reporting, each major run should preserve the run date,
providers, query variant mode, auto-seed caps, generated seed counts, exact
`per_seed` entries, and search-completeness results.
