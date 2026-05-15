# Comprehensive Search Protocol V2

This protocol defines the reportable baseline search for the v2 psychedelic
knowledge graph. Earlier searches are treated as scoping and QA material. They
can help reveal missed terms, but the final methods should describe this
baseline search once it is accepted.

## Goal

Find literature and source-database records that may support either:

- psychedelic compound -> molecular target evidence
- psychedelic compound -> indication evidence

The search is deliberately broad. Relevance is decided later by screening and
v2 extraction, not by assuming that every retrieved DOI belongs in the KG.

## Source Of Truth

The baseline search is generated from the current registries in
`pipeline/config.example.yaml`:

- `validation.allowed_compounds`
- `validation.allowed_targets`
- `validation.allowed_disorders`

If the scope changes, update those registries first and regenerate the baseline
search files. Do not hand-edit generated seed files.

## Generated Files

The exact baseline seeds and manifests are:

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

## Seed Families

The baseline plan uses layered seed families:

- `sentinel_default`: previous hand-written seed pairs retained as sentinel
  queries and compatibility checks.
- `class_level`: broad psychedelic-class queries without a preassigned
  compound or entity.
- `compound_broad`: compound-level searches that can recover papers where the
  target or indication is not in the title or abstract.
- `entity_broad`: target- or indication-level searches tied to psychedelic
  class terms.
- `pair_core`: all compound-target or compound-indication pairs from the
  registries, with core evidence templates.

Current baseline counts:

| Dataset | Total seeds | Sentinel | Class | Compound broad | Entity broad | Pair core |
|---|---:|---:|---:|---:|---:|---:|
| Mechanistic | 5,806 | 24 | 4 | 120 | 138 | 5,520 |
| Indication | 3,974 | 41 | 3 | 120 | 93 | 3,717 |

An `expanded` profile exists for later targeted follow-up. It adds additional
pair-level evidence templates and should be used only after the baseline search
is inspected, because it greatly increases search volume.

## Literature Databases

The baseline literature run should use the comprehensive provider profile:

- Semantic Scholar
- OpenAlex
- PubMed
- PMC
- Crossref
- Unpaywall enrichment for open-access PDF metadata

The primary reportable searches should start with the Boolean module files:

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

The pair-grid files remain the audit/gap-check layer. Use them after the
Boolean modules to find rare corners of the compound-target and
compound-indication space. The new-DOI gate remains enabled in the wrapper by
default, so rediscovered DOI records are reported but not re-added as new
papers.

For the full baseline, Boolean modules should run deeper than pair-grid audit
seeds:

| Search layer | Recommended cap |
|---|---:|
| Boolean primary modules | 500 |
| Boolean dense-topic modules | 1,000 |
| Pair-grid audit, mechanistic | 20-50 |
| Pair-grid audit, indication | 10-20 |

The generated Boolean CSV files include `recommended_max_results_per_seed` so
dense topics can be run deeper than broad primary modules if we split execution
by module type.

The Boolean module builder also writes module-type-specific seed files, for
example:

- `mechanistic_boolean_openalex_primary_boolean_seeds.csv` at cap 500
- `mechanistic_boolean_openalex_dense_topic_seeds.csv` at cap 1,000
- `disorder_boolean_pubmed_primary_boolean_seeds.csv` at cap 500
- `disorder_boolean_pubmed_dense_topic_seeds.csv` at cap 1,000

## Calibration Before Full Execution

The generated seed files are the comprehensive search instrument, not a
requirement to run every seed at maximum depth immediately. Before executing
the full baseline, build and run a small stratified calibration batch:

```bash
python pipeline/ingest/build_search_calibration_batches.py --dataset all
```

Fast OpenAlex calibration:

```bash
python pipeline/ingest/discover_literature.py \
  --dataset mechanistic \
  --provider openalex \
  --seed-file data/raw/search_strategies/comprehensive_baseline_v1/calibration/mechanistic_calibration_seeds.csv \
  --query-variant-mode conservative \
  --max-results-per-seed 10 \
  --max-results 0 \
  --disable-ledger \
  --disable-protected-retention \
  --skip-unpaywall-enrichment \
  --queue-out data/raw/search_strategies/comprehensive_baseline_v1/calibration/openalex/mechanistic_discovered.txt \
  --report-out data/raw/search_strategies/comprehensive_baseline_v1/calibration/openalex/mechanistic_discovery_report.json
```

Run the same command for disorder, then pass the calibration queues through
`add_new_dois.py` with calibration-specific output paths and summarize:

```bash
python pipeline/ingest/summarize_search_calibration.py --dataset all
```

The current OpenAlex calibration found:

| Dataset | Sample seeds | Raw rows | Merged DOI rows | New DOIs after global gate |
|---|---:|---:|---:|---:|
| Mechanistic | 46 | 299 | 200 | 36 |
| Indication | 45 | 444 | 259 | 47 |

This shows two important things. First, the existing DOI universe already
captures many records found by the new strategy. Second, broad indication and
rare compound-indication pair searches can retrieve substantial noise, so the
full baseline should be run in batches and inspected by seed family.

Calibration output lives under:

`data/raw/search_strategies/comprehensive_baseline_v1/calibration/openalex/`

The first Boolean-module cap-100 smoke calibration found:

| Provider | Dataset | Module seeds | Raw rows | Merged DOI rows | New DOIs after global gate |
|---|---|---:|---:|---:|---:|
| OpenAlex | Mechanistic | 10 | 1,000 | 736 | 246 |
| OpenAlex | Indication | 12 | 1,200 | 785 | 186 |
| PubMed | Mechanistic | 10 | 995 | 723 | 159 |
| PubMed | Indication | 12 | 1,164 | 738 | 116 |

This was only a smoke calibration. The reportable Boolean run should use higher
caps as described above. Boolean calibration output lives under:

`data/raw/search_strategies/comprehensive_baseline_v1/boolean_modules/`

## Source-Specific Supplements

Some sources are not ordinary literature-search engines and should be handled as
source-specific supplements:

- ChEMBL for assay-level compound-target activity
- BindingDB for binding-affinity cross-checks
- ClinicalTrials.gov for registered clinical studies and linked publications

These supplement outputs should be linked to papers and evidence records, but
not treated as ordinary DOI search seeds.

## Quality Checks

Use earlier searches, legacy curated DOI sets, and the known-study manifest as
QA checks, not as proof that a paper is relevant. A missed old DOI can mean:

- the baseline search strategy needs another synonym or source,
- the old DOI is outside the intended v2 scope,
- the DOI was found through a supplement such as citation chasing or a registry,
- the old heuristic claim was not actually relevant.

The v2 extraction step remains responsible for final relevance and claim
extraction.

## Search Design Caveat

This strategy follows core high-recall literature discovery principles: explicit
scope, documented sources, reproducible query generation, DOI deduplication,
known-study checks, and citation/supplement layers. It is not yet a perfect
database-specific systematic-search strategy. A fully reportable final protocol
should also harden the broad seed families into source-specific Boolean blocks
with controlled vocabulary where available, especially PubMed MeSH terms and
Title/Abstract synonym blocks.

The all-pairs grid is useful for machine-assisted coverage auditing because it
tests every compound-target or compound-indication combination in the registry.
It should be treated as a gap-finding layer. The final execution plan should
combine:

- broad source-specific Boolean searches for recall,
- compound/entity/pair seeds for coverage auditing and gap filling,
- citation chasing from known relevant studies,
- source-specific supplements such as ChEMBL, BindingDB, and trial registries,
- family-level calibration reports before full-scale execution.

## V2 Search Strategy Direction

The current generated seed grid is a coverage scaffold. It uses free-text query
templates such as `{compound} {indication} clinical trial` and
`{compound} {target} binding affinity Ki`. That makes the pair universe
auditable, but it is too loose to serve as the final primary search strategy by
itself.

The improved strategy should separate three roles:

1. **Primary systematic searches**: source-specific Boolean blocks that combine
   compound/class synonyms, target/indication synonyms, and evidence terms.
   These are the main reportable searches.
2. **Pair-grid audit searches**: all compound-target and compound-indication
   pairs, run to check coverage gaps. These should be interpreted as audit/gap
   signals, not as the whole search method.
3. **Source-specific supplements**: ChEMBL, BindingDB, ClinicalTrials.gov, and
   citation chasing, because those sources are not ordinary ranked DOI search
   results.

For OpenAlex, noisy calibration runs should prefer a stricter title/abstract
surface instead of broad title/abstract/full-text search:

```bash
python pipeline/ingest/discover_literature.py \
  --dataset disorder \
  --provider openalex \
  --seed-file data/raw/search_strategies/comprehensive_baseline_v1/disorder_seeds.csv \
  --openalex-search-field title_and_abstract \
  --max-results-per-seed 20 \
  --max-results 0
```

The broad OpenAlex `default` search remains useful as a recall-oriented
supplement, but it should not be the only basis for pair-level precision.

## Updates

After the baseline is accepted, later literature updates should be documented as
date-bounded update searches using the same protocol version. If we discover a
major missing entity family, update the registries, regenerate the baseline
search files, and record that as a protocol revision.
