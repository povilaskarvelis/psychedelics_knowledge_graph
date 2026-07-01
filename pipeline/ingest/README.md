# Ingest

This stage covers literature discovery, DOI deduplication, paper metadata
enrichment, and PDF retrieval. It should produce a transparent paper corpus before
claim extraction begins.

The ingest layer works at DOI/paper level. It does not decide final graph
claims.

## Stage Order

1. Generate or provide search files.
2. Run literature discovery against selected providers.
3. Normalize discovered DOIs into the unified corpus tables with provenance.
4. Enrich metadata and abstracts for corpus rows that do not yet have complete
   paper metadata.
5. Run deterministic screening/routing in `pipeline/review/`.
6. Retrieve PDFs for routed full-text candidates.

## Search Files

The current search design has two complementary parts:

- **Grouped search modules**: broad, structured searches that combine term
  blocks such as compound terms, target/indication terms, and evidence terms.
- **Direct pair searches**: targeted compound-target or compound-indication
  searches used to catch rare combinations that broad grouped searches may miss.

Build the generated search files:

```bash
python pipeline/ingest/build_boolean_search_modules.py --dataset all --run-id search_2026_05
python pipeline/ingest/build_comprehensive_search_plan.py --dataset all --profile standard --run-id search_2026_05
```

By default these write to `data/raw/search_strategies/literature_search/`.
Use `--run-id` to keep each search/update run separate. The script names still
contain some older implementation wording; in methods text, describe the
outputs as grouped search modules and direct pair searches.

## Discovery Providers

`discover_literature.py` supports:

- `openalex`: broad metadata-heavy discovery
- `pubmed`: biomedical title/abstract discovery
- `pmc`: PMC discovery
- `crossref`: broad DOI metadata fallback
- `semantic_scholar`: relevance-focused scholarly discovery
- `hybrid`: Semantic Scholar + OpenAlex
- `biomedical`: PubMed + PMC + Crossref
- `comprehensive`: Semantic Scholar + OpenAlex + PubMed + PMC + Crossref

Run discovery from a seed file:

```bash
python pipeline/ingest/discover_literature.py \
  --dataset mechanistic \
  --provider pubmed \
  --seed-file data/raw/search_strategies/search_2026_05/grouped_modules/mechanistic_grouped_pubmed_seeds.csv \
  --max-results-per-seed 500 \
  --max-results 0
```

OpenAlex searches should usually be restricted to title/abstract matching for
pair-style searches:

```bash
python pipeline/ingest/discover_literature.py \
  --dataset disorder \
  --provider openalex \
  --seed-file data/raw/search_strategies/search_2026_05/direct_pairs/disorder_seeds.csv \
  --openalex-search-field title_and_abstract \
  --max-results-per-seed 20 \
  --max-results 0
```

## Batch Runners

The batch runners execute generated search files in resumable chunks and write
provider/run-specific reports.

Grouped search modules:

```bash
python pipeline/ingest/run_boolean_module_searches.py \
  --run-id search_2026_05 \
  --provider all \
  --dataset all
```

Direct pair searches:

```bash
python pipeline/ingest/run_pair_grid_audit.py \
  --run-id search_2026_05 \
  --provider both
```

The batch runners use the same `--run-id` layout as the search-file generators,
unless explicit paths are supplied.

## Recommended Search Caps

Use high caps for grouped searches and lower caps for direct pair searches:

- Grouped primary modules: `500` per seed
- Dense topic modules: `1000` per seed
- Mechanistic direct pair searches: `20-50` per seed
- Indication direct pair searches: `10-20` per seed

The cap is a retrieval limit, not an inclusion rule. Screening and extraction
decide which papers are relevant.

## Calibration

Calibration is optional and should write to a separate run directory so it does
not overwrite live discovery state.

```bash
python pipeline/ingest/build_search_calibration_batches.py --dataset all
python pipeline/ingest/summarize_search_calibration.py --dataset all
```

Use calibration to estimate noise, provider overlap, and whether specific query
families are too broad before spending full API budget.

## DOI Add Gate

Older discovery runs used a dataset-specific DOI add gate before metadata enrichment:

```bash
python pipeline/ingest/add_new_dois.py \
  --dataset mechanistic \
  --input data/raw/doi_queue.mechanistic.discovered.txt
```

Outputs:

- `data/raw/doi_queue.<dataset>.new.txt`
- `data/processed/add_new_dois_report_<dataset>.json`
- `data/processed/rediscovered_dois_<dataset>.csv`
- `data/processed/missing_or_invalid_dois_<dataset>.csv`
- `data/processed/input_duplicate_dois_<dataset>.csv`

The gate is DOI-level. In the current table-based pipeline, rediscovered DOIs
remain useful provenance and the canonical "needs metadata" view is derived
from the unified corpus table instead of from a one-off new-DOI file.

## Metadata Enrichment

Materialize or enrich the paper metadata table:

```bash
python pipeline/ingest/enrich_paper_metadata.py \
  --papers-table data/processed/corpus/candidate_papers.parquet \
  --output-table data/processed/corpus/paper_metadata_enrichment.parquet \
  --metadata-provider-order openalex \
  --write-every 100 \
  --progress-every 100
```

Default metadata provider order:

```text
pubmed, pmc, unpaywall, crossref, openalex, semantic_scholar
```

This prioritizes biomedical metadata/abstracts first, then open-access and PDF
resolution, then broad metadata fallbacks.

The metadata-enrichment command writes `paper_metadata_enrichment.parquet`.
Rebuild the corpus tables afterward so enriched metadata is merged back into
`candidate_papers.parquet`.

To recover or confirm rows that still have no abstract, run a targeted metadata
enrichment pass instead of refreshing the whole corpus:

```bash
python pipeline/ingest/enrich_paper_metadata.py \
  --papers-table data/processed/corpus/candidate_papers.parquet \
  --output-table data/processed/corpus/paper_metadata_enrichment.parquet \
  --only-missing-abstract \
  --retry-missing-metadata \
  --metadata-provider-order pubmed,openalex,pmc,crossref \
  --write-every 100 \
  --progress-every 100
```

This keeps complete rows unchanged and records provider-checked no-abstract
cases with `metadata_missing_reason=providers_returned_no_abstract`; rows where
metadata providers fail completely are marked `metadata_lookup_unresolved`.

To refresh only open-access status and PDF URL fields for a targeted set, use
the access-link refresh instead of full metadata enrichment:

```bash
python pipeline/ingest/refresh_open_access_links.py \
  --only-retained-secondary \
  --only-missing-pdf-url \
  --provider-order unpaywall,openalex,pmc
```

This updates only `open_access_is_oa`, `open_access_status`,
`open_access_url`, `best_pdf_url`, and `pdf_url_candidates`. Unpaywall is the
primary source; OpenAlex and PMC are fallback sources for rows that still lack a
PDF URL.

To materialize metadata already present in the candidate paper table without
querying external providers:

```bash
python pipeline/ingest/enrich_paper_metadata.py \
  --papers-table data/processed/corpus/candidate_papers.parquet \
  --output-table data/processed/corpus/paper_metadata_enrichment.parquet \
  --metadata-provider-order none
```

If a first-pass provider leaves lookup errors or missing titles, retry only
those core gaps instead of all abstract-only gaps:

```bash
python pipeline/ingest/enrich_paper_metadata.py \
  --papers-table data/processed/corpus/candidate_papers.parquet \
  --output-table data/processed/corpus/paper_metadata_enrichment.parquet \
  --retry-core-metadata \
  --metadata-provider-order pubmed
```

## PDF Retrieval

After abstract screening, download legal open-access PDFs only for papers in the
LLM full-text candidate queue:

```bash
python pipeline/ingest/sync_paper_library.py \
  --dataset mechanistic \
  --doi-file data/raw/doi_queue.mechanistic.llm_fulltext_candidates.txt \
  --metadata-provider-order pubmed,pmc,unpaywall,crossref,openalex,semantic_scholar \
  --checkpoint-every 100 \
  --progress-every 100
```

The downloader uses PMC/Europe PMC, Unpaywall, OpenAlex, and publisher or
repository URLs where available.

Retry failed/no-URL PDF rows from the existing paper library:

```bash
python pipeline/ingest/retry_pdf_downloads.py --dataset mechanistic
python pipeline/ingest/retry_pdf_downloads.py --dataset disorder
```

Import manually acquired PDFs by DOI-style filenames:

```bash
python pipeline/ingest/import_manual_pdfs.py \
  --dataset mechanistic \
  --source-dir /absolute/path/to/manual_pdfs \
  --apply
```

## Search Completeness Checks

The structured known-study set is stored at:

- `data/raw/benchmark_manifest.json`

Use it as a search-completeness aid, not as proof that every relevant paper is
known:

```bash
python pipeline/ingest/recall_audit.py --dataset mechanistic --min-discovered 95 --fail-under-threshold
python pipeline/ingest/recall_audit.py --dataset disorder --min-discovered 95 --fail-under-threshold
```

If coverage misses the threshold, revise search terms or document why the
missed study is out of scope or unavailable in the selected sources.

## Discovery Ledger

Every discovery run can write a cumulative ledger:

- `data/processed/discovery_ledger_mechanistic.json`
- `data/processed/discovery_ledger_disorder.json`

The ledger records which DOIs were seen in each run and prevents capped queues
from being mistaken for the full discovery history.

If a discovery run used `--max-results` and you later need the full latest-run
queue without rerunning APIs:

```bash
python pipeline/ingest/export_discovery_queue_from_ledger.py --dataset mechanistic --max-results 0
python pipeline/ingest/export_discovery_queue_from_ledger.py --dataset disorder --max-results 0
```

## Supplemental Non-Paper Sources

Some evidence sources are not paper DOI searches:

```bash
python pipeline/ingest/build_discovery_supplement_plan.py --dataset mechanistic
python pipeline/ingest/build_discovery_supplement_plan.py --dataset disorder
```

These plans cover sources such as ChEMBL, BindingDB, and ClinicalTrials.gov.
They should become source-specific evidence rows, not paper DOI queues.

For registry enrichment tied to already found papers:

```bash
python pipeline/enrich/enrich_trial_registries.py --dataset disorder
```

## Retired Stub Generation

The old DOI-to-claim-stub generator has been removed. The canonical path now
prepares DOI-level extraction inputs in `pipeline/extract/`.

## Main Outputs

- `data/raw/doi_queue.<dataset>.discovered.txt`
- `data/raw/doi_queue.<dataset>.new.txt`
- `data/processed/discovery_report_<dataset>.json`
- `data/processed/discovery_ledger_<dataset>.json`
- `data/processed/paper_library_<dataset>.json`
- `data/processed/paper_inventory_<dataset>.json`
- `data/processed/paper_inventory_<dataset>.md`
- `data/raw/papers/<dataset>/pdfs/*.pdf`

Grouped module runs also write a domain-aware rediscovery lane under
`grouped_module_run/combined/domain_reprocessing/` when rediscovered DOIs need
screening for newly added routing domains. Those queues let already-known
bibliographic records re-enter abstract screening without duplicating metadata.

After abstract screening finishes for a run, add the completed screening report
to `data/processed/corpus_manifest.json` if it should be included in the
current extraction corpus.
