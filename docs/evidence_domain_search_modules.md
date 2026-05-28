# Evidence-Domain Search Modules

This note defines grouped Boolean modules for evidence domains in the main
literature-discovery strategy. The modules use the same PubMed/OpenAlex
grouped-module machinery, DOI gate, metadata enrichment, routing-aware screening,
full-text retrieval, extraction, normalization, and graph build.

The generated artifacts are under:

```text
data/raw/search_strategies/evidence_domain_modules_2026_05/grouped_modules/
```

The manifest is:

```text
data/raw/search_strategies/evidence_domain_modules_2026_05/grouped_modules/grouped_search_modules_manifest.json
```

## Evidence Domains

These modules cover domains that complement the molecular-target, brain-system,
cognitive-behavioral, and clinical-outcome searches.

| Domain | Module scope | Modules |
|---|---|---|
| Molecular and pathway evidence | `molecular_pathway` | molecular plasticity pathways; gene-expression/transcriptomics; inflammatory and neuroendocrine molecular readouts; ketamine/psychedelic mTOR-synaptogenesis; immediate early genes |
| Clinical symptoms, functioning, and safety | `clinical_symptom_function`; `clinical_safety` | symptoms/functioning/quality of life; suicidality/anhedonia/sleep/function; craving/relapse/functioning; safety/tolerability/adverse events; cardiovascular/mania/psychosis/HPPD safety |
| Clinical studies with biological and behavioral endpoints | `bridge_clinical_mechanism` | clinical outcome plus brain, molecular, cognitive, or behavioral endpoint modules for psilocybin, ketamine, MDMA, and broader psychedelic classes |

## Module Counts

| Implementation group | Scope | Primary broad | Dense topic | Total |
|---|---|---:|---:|---:|
| Molecular/pathway group | `molecular_pathway` | 3 | 2 | 5 |
| Clinical endpoint group | `bridge_clinical_mechanism` | 1 | 2 | 3 |
| Clinical evidence | `clinical_symptom_function` | 1 | 2 | 3 |
| Clinical evidence | `clinical_safety` | 1 | 1 | 2 |
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
```

After discovery and DOI gating, resulting DOI queues pass through metadata enrichment
and the routing-aware screening layer. The screening layer preserves routing
tags such as `molecular_pathway`,
`brain_system`, `cognitive_behavioral`, `clinical_outcome`, `safety`, and
`bridge_clinical_mechanism`, so these searches can feed later extraction tasks
without forcing papers into a single ontology bucket.
