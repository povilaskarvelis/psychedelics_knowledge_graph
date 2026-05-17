# Comprehensive Search Protocol

This protocol defines the literature search for the psychedelic knowledge
graph.

## Goal

Find literature and source-database records that may support either:

- psychedelic compound -> molecular target evidence
- psychedelic compound -> indication evidence

The search is deliberately broad. Relevance is decided later by screening and
extraction, not by assuming that every retrieved DOI belongs in the KG.

## Source Of Truth

The search is generated from the current registries in
`pipeline/config.example.yaml`:

- `validation.allowed_compounds`
- `validation.allowed_targets`
- `validation.allowed_disorders`

If the scope changes, update those registries first and regenerate the search
files. Do not hand-edit generated seed files.

## Generated Files

The exact search files and manifests are:

- `data/raw/search_strategies/comprehensive_baseline_v1/boolean_modules/mechanistic_boolean_openalex_seeds.csv`
- `data/raw/search_strategies/comprehensive_baseline_v1/boolean_modules/mechanistic_boolean_pubmed_seeds.csv`
- `data/raw/search_strategies/comprehensive_baseline_v1/boolean_modules/disorder_boolean_openalex_seeds.csv`
- `data/raw/search_strategies/comprehensive_baseline_v1/boolean_modules/disorder_boolean_pubmed_seeds.csv`
- `data/raw/search_strategies/comprehensive_baseline_v1/boolean_modules/boolean_search_modules_manifest.json`
- `data/raw/search_strategies/comprehensive_baseline_v1/mechanistic_seeds.csv`
- `data/raw/search_strategies/comprehensive_baseline_v1/mechanistic_search_manifest.json`
- `data/raw/search_strategies/comprehensive_baseline_v1/disorder_seeds.csv`
- `data/raw/search_strategies/comprehensive_baseline_v1/disorder_search_manifest.json`
- `data/raw/search_strategies/comprehensive_baseline_v1/search_strategy_summary.json`

Regenerate them with:

```bash
python pipeline/ingest/build_boolean_search_modules.py --dataset all
python pipeline/ingest/build_comprehensive_search_plan.py --dataset all --profile baseline
```

## Query Construction

Searches are run in PubMed for curated biomedical indexing and OpenAlex for
broader scholarly coverage.

Each query module is generated from three concept blocks:

```text
(compound or drug-class synonyms)
AND (target-family or indication-family synonyms)
AND (evidence-context terms)
```

Terms inside each block are joined with OR. PubMed queries use
`[Title/Abstract]` fields; clinical-indication PubMed queries also apply
`NOT (animals[MeSH Terms] NOT humans[MeSH Terms])`. Mechanistic target
searches do not use that exclusion; animal, in vitro, and assay records are
retained for mechanistic evidence. OpenAlex modules submit the generated query
text through the OpenAlex works API. No publication-date or language
restriction is applied during discovery.

Clinical indication evidence terms include clinical trial,
randomized/randomised, placebo, open-label/open label, phase 2, phase 3,
treatment, therapy, efficacy, safety, tolerability, outcome, and follow-up.
Mechanistic evidence terms include binding, affinity, Ki, Kd, IC50, EC50,
radioligand, functional assay, agonist, antagonist, partial agonist, and
signaling.

## Search Module Families

| Dataset | Module type | Modules | Cap per source/module |
|---|---|---|---:|
| Indication | Primary broad | clinical class core; depression spectrum; trauma/PTSD; substance use and addiction; anxiety, distress, and palliative care; pain and headache; OCD, eating disorders, and autism | 500 |
| Indication | Dense topic | psilocybin-depression; MDMA-PTSD; ketamine-depression-suicidality; ibogaine-opioid/substance use disorder; LSD-alcohol/anxiety | 1,000 |
| Mechanistic | Primary broad | serotonin receptors; monoamine transporters; glutamate/NMDA; opioid, sigma, and TAAR targets; plasticity, TrkB, and BDNF pathways | 500 |
| Mechanistic | Dense topic | LSD-5-HT2A; psilocin/psilocybin-5-HT2A; MDMA transporters; ketamine-NMDA; salvinorin A-kappa opioid receptor | 1,000 |

## Pairwise Search Scope

The search plan also includes generated pairwise search files. These files
search the compound-target and compound-indication registry space directly
alongside the query modules.

| Dataset | Focused direct pairs | Pair-core search seeds |
|---|---:|---:|
| Mechanistic | 1,840 | 5,520 |
| Indication | 1,240 | 3,717 |

## Literature Databases

The literature discovery run uses OpenAlex and PubMed query modules.
PubMed/PMC, Crossref, Semantic Scholar, and open-access
metadata sources are used after DOI discovery to add bibliographic details,
check open-access status, and identify available full text.

The searches start with the query-module files:

```bash
python pipeline/ingest/discover_literature.py \
  --dataset mechanistic \
  --provider openalex \
  --seed-file data/raw/search_strategies/comprehensive_baseline_v1/boolean_modules/mechanistic_boolean_openalex_seeds.csv \
  --max-results-per-seed 500 \
  --max-results 0 \
  --disable-ledger \
  --disable-protected-retention \
  --skip-unpaywall-enrichment
```

```bash
python pipeline/ingest/discover_literature.py \
  --dataset disorder \
  --provider pubmed \
  --seed-file data/raw/search_strategies/comprehensive_baseline_v1/boolean_modules/disorder_boolean_pubmed_seeds.csv \
  --max-results-per-seed 500 \
  --max-results 0
```

The pair-grid files run direct searches for rare corners of the
compound-target and compound-indication space. Records already present in the
paper library are reported but not re-added as new papers.

For the full search, query modules should run deeper than pairwise search
seeds:

| Search layer | Recommended cap |
|---|---:|
| Primary query modules | 500 |
| Dense-topic query modules | 1,000 |
| Pairwise searches, mechanistic | 20-50 |
| Pairwise searches, indication | 10-20 |

The generated query CSV files include `recommended_max_results_per_seed` so
dense topics can be run deeper than broad primary modules if we split execution
by module type.

The query-module builder also writes module-type-specific seed files, for
example:

- `mechanistic_boolean_openalex_primary_boolean_seeds.csv` at cap 500
- `mechanistic_boolean_openalex_dense_topic_seeds.csv` at cap 1,000
- `disorder_boolean_pubmed_primary_boolean_seeds.csv` at cap 500
- `disorder_boolean_pubmed_dense_topic_seeds.csv` at cap 1,000

## Search Execution Outputs

Search execution outputs are stored under
`data/raw/search_strategies/comprehensive_baseline_v1/boolean_modules/full_boolean_v1/`.
The search run is timestamped May 15, 2026. Run summaries and
PRISMA-style flow outputs report records identified,
duplicate DOI records, invalid DOI records, screening outcomes, full-text
access status, and extraction status. These counts describe the flow of
records through the workflow; they do not define graph inclusion. A DOI becomes
graph evidence only after screening, full-text or abstract-only labeling,
structured extraction, and validation.

## Source-Specific Supplements

Some sources are not ordinary literature-search engines and should be handled as
source-specific supplements:

- ChEMBL for assay-level compound-target activity
- BindingDB for binding-affinity cross-checks
- ClinicalTrials.gov for registered clinical studies and linked publications

These supplement outputs should be linked to papers and evidence records, but
not treated as ordinary DOI search seeds.

## Quality Checks

Quality checks focus on reproducibility and downstream eligibility:

- generated search files are derived from the versioned registries,
- discovered records are normalized by DOI before insertion,
- duplicate DOI records are logged instead of re-added,
- relevance is decided by deterministic pre-screening, LLM abstract screening,
  full-text access status, structured extraction, and validation.

## Search Design Notes

This strategy follows core high-recall literature discovery principles:
explicit scope, documented sources, reproducible query generation, DOI
deduplication, and supplement layers. The search design separates three roles:

1. **Query-family searches**: source-specific query blocks that combine
   compound/class synonyms, target/indication synonyms, and evidence terms.
2. **Pairwise searches**: all compound-target and compound-indication pairs,
   run directly so rare combinations are represented in the search.
3. **Source-specific supplements**: ChEMBL, BindingDB, ClinicalTrials.gov, and
   citation chasing, because those sources are not ordinary ranked DOI search
   results.

The all-pairs grid is useful because it tests every compound-target or
compound-indication combination in the registry. Retrieved records still
require screening and extraction before they can support graph evidence.

## Updates

Later literature updates should be documented as date-bounded update searches
using the same protocol version. If a major missing entity family is added,
update the registries, regenerate the search files, and record that as a
protocol revision.
