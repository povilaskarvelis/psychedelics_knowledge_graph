# Evidence-Domain Search Modules

This note defines grouped Boolean modules for evidence domains in the main
literature-discovery strategy. The modules use the same PubMed/OpenAlex
grouped-module machinery, DOI gate, metadata enrichment, routing-aware screening,
full-text retrieval, extraction, normalization, and graph build.

The generated artifacts are under:

```text
data/raw/search_strategies/evidence_domain_modules_2026_05/grouped_modules/
data/raw/search_strategies/extraction_gap_domains_2026_05/grouped_modules/
data/raw/search_strategies/extraction_gap_domains_keyword_closure_2026_05/grouped_modules/
```

The manifests are:

```text
data/raw/search_strategies/evidence_domain_modules_2026_05/grouped_modules/grouped_search_modules_manifest.json
data/raw/search_strategies/extraction_gap_domains_2026_05/grouped_modules/grouped_search_modules_manifest.json
data/raw/search_strategies/extraction_gap_domains_keyword_closure_2026_05/grouped_modules/grouped_search_modules_manifest.json
```

## Evidence Domains

These modules cover domains that complement the molecular-target, brain-system,
cognitive-behavioral, and clinical-outcome searches.

| Domain | Module scope | Modules |
|---|---|---|
| Molecular and pathway evidence | `molecular_pathway` | molecular plasticity pathways; gene-expression/transcriptomics; inflammatory and neuroendocrine molecular readouts; ketamine/psychedelic mTOR-synaptogenesis; immediate early genes |
| Subjective experience and acute effects | `subjective_experience` | acute subjective effects; phenomenology; mystical and mystical-type experience; ego dissolution/loss; altered states; emotional breakthrough; visual/perceptual effects; connectedness/awe; and common subjective-effect measures |
| Pharmacokinetics and exposure | `pharmacokinetics_exposure` | pharmacokinetics, pharmacodynamics, PK/PD, dose/exposure-response, ADME, metabolites, blood/plasma/serum concentrations or levels, clearance, half-life, route, excretion, protein binding, and analytical measurement terms |
| Clinical symptoms, functioning, and safety | `clinical_symptom_function`; `clinical_safety` | symptoms/functioning/quality of life; suicidality/anhedonia/sleep/function; craving/relapse/functioning; safety/tolerability/adverse events; cardiovascular/mania/psychosis/HPPD safety |
| Intervention delivery context | `intervention_context` | psychotherapy, preparation/integration sessions, aftercare, therapeutic alliance or relationship, set and setting, music/eyeshades, session structure, psychological support, facilitators, training/manual terms, blinding, and feasibility/acceptability |
| Real-world use and public health | `real_world_use_public_health` | epidemiology, prevalence, surveys, naturalistic use, lifetime or past-year use, microdosing, nonmedical/recreational use, harm reduction, poison-center/poison-control and emergency-department records, toxicity, hospitalization, misuse, and diversion |
| Clinical studies with biological and behavioral endpoints | `bridge_clinical_mechanism` | clinical outcome plus brain, molecular, cognitive, or behavioral endpoint modules for psilocybin, ketamine, MDMA, and broader psychedelic classes |

## Module Counts

| Implementation group | Scope | Primary broad | Dense topic | Total |
|---|---|---:|---:|---:|
| Molecular/pathway group | `molecular_pathway` | 3 | 2 | 5 |
| Subjective experience group | `subjective_experience` | 1 | 1 | 2 |
| Pharmacokinetics/exposure group | `pharmacokinetics_exposure` | 1 | 1 | 2 |
| Clinical endpoint group | `bridge_clinical_mechanism` | 1 | 2 | 3 |
| Clinical evidence | `clinical_symptom_function` | 1 | 2 | 3 |
| Clinical evidence | `clinical_safety` | 1 | 1 | 2 |
| Intervention context | `intervention_context` | 1 | 1 | 2 |
| Real-world/public-health use | `real_world_use_public_health` | 1 | 1 | 2 |
| Clinical evidence | `bridge_clinical_mechanism` | 1 | 2 | 3 |

Each module is generated once for PubMed syntax and once for OpenAlex syntax.
Primary broad modules use a cap of 500 records per provider seed; dense topic
modules use a cap of 1,000 records per provider seed.

## Operational Run

To run these evidence-domain scopes:

```bash
python pipeline/ingest/run_boolean_module_searches.py \
  --run-id evidence_domain_modules_2026_05 \
  --dataset mechanistic \
  --module-scope molecular_pathway,bridge_clinical_mechanism \
  --module-type all \
  --provider all

python pipeline/ingest/run_boolean_module_searches.py \
  --run-id evidence_domain_modules_2026_05 \
  --dataset disorder \
  --module-scope clinical_symptom_function,clinical_safety,bridge_clinical_mechanism \
  --module-type all \
  --provider all

python pipeline/ingest/run_boolean_module_searches.py \
  --run-id extraction_gap_domains_2026_05 \
  --dataset mechanistic \
  --module-scope subjective_experience,pharmacokinetics_exposure \
  --module-type all \
  --provider all

python pipeline/ingest/run_boolean_module_searches.py \
  --run-id extraction_gap_domains_2026_05 \
  --dataset disorder \
  --module-scope intervention_context,real_world_use_public_health \
  --module-type all \
  --provider all

python pipeline/ingest/run_boolean_module_searches.py \
  --run-id extraction_gap_domains_keyword_closure_2026_05 \
  --dataset mechanistic \
  --module-scope subjective_experience,pharmacokinetics_exposure \
  --module-type all \
  --provider all

python pipeline/ingest/run_boolean_module_searches.py \
  --run-id extraction_gap_domains_keyword_closure_2026_05 \
  --dataset disorder \
  --module-scope intervention_context,real_world_use_public_health \
  --module-type all \
  --provider all
```

After discovery and DOI gating, resulting DOI queues pass through metadata enrichment
and the routing-aware screening layer. The screening layer preserves routing
tags such as `molecular_pathway`,
`brain_system`, `cognitive_behavioral`, `clinical_outcome`, `safety`,
`subjective_experience`, `pharmacokinetics_exposure`, `intervention_context`,
`real_world_use_public_health`, and `bridge_clinical_mechanism`, so these
searches can feed later extraction tasks without forcing papers into a single
ontology bucket.
