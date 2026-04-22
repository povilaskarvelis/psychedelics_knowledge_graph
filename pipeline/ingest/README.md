# Ingest: Web Discovery + DOI Queue to Claim Stubs

This stage has three steps:
1. Discover literature from web APIs and write DOI queue files.
2. Convert DOI queues into normalized curation stubs.
3. Sync the local paper library (abstracts + OA metadata + PDF downloads).

## Discovery (web search)
Default provider is `semantic_scholar` (relevance-focused). Additional modes:
- `openalex`: broad metadata-heavy discovery
- `hybrid`: Semantic Scholar + OpenAlex
- `biomedical`: PubMed + PMC + Crossref
- `comprehensive`: Semantic Scholar + OpenAlex + PubMed + PMC + Crossref, with
  Unpaywall enrichment when an email is configured

Run discovery for mechanistic:
`python pipeline/ingest/discover_literature.py --dataset mechanistic`

Run discovery for disorder:
`python pipeline/ingest/discover_literature.py --dataset disorder`

Hybrid mode:
`python pipeline/ingest/discover_literature.py --dataset mechanistic --provider hybrid`

Comprehensive biomedical mode:
`python pipeline/ingest/discover_literature.py --dataset mechanistic --provider comprehensive`

Extensive retrieval (hundreds of papers):
`python pipeline/ingest/discover_literature.py --dataset mechanistic --provider hybrid --max-results-per-seed 100 --max-results 600`

High-recall seed expansion from allowlists in `pipeline/config.example.yaml`:
`python pipeline/ingest/discover_literature.py --dataset mechanistic --provider hybrid --expand-seeds-from-config --auto-template-mode broad --auto-max-pairs 1200 --auto-max-seeds 3000 --max-results-per-seed 120 --max-results 5000`

Notes for auto-seed controls:
- `--expand-seeds-from-config`: add generated seeds on top of defaults/manual seeds
- `--auto-seeds-only`: skip defaults and use only generated seeds
- `--auto-max-pairs 0` and `--auto-max-seeds 0`: remove generation caps (can be very large)

Balanced seed profiles:
- `--balanced-seed-profile coverage`: add bounded compound-only and entity-only
  seeds for allowlist items that are not covered by defaults/manual seeds.
- `--balanced-seed-profile evidence`: also add evidence-type variants for the
  selected compound-entity seeds, such as binding, functional assay, safety, and
  outcome queries.
- `--balanced-max-compounds`, `--balanced-max-entities`, and
  `--balanced-max-seeds` keep this from becoming a full Cartesian rerun.

Audit seeds before spending API budget:

`python pipeline/ingest/audit_discovery_seeds.py --dataset mechanistic --balanced-seed-profile coverage`

`python pipeline/ingest/audit_discovery_seeds.py --dataset disorder --balanced-seed-profile coverage`

Provider-specific query hardening:
- `--query-variant-mode conservative`: keeps the original query and adds
  PubMed/PMC Title/Abstract synonym queries for each seed.
- `--query-variant-mode expanded`: also adds alias phrase variants to broad
  providers. This increases runtime and should be used for focused comparison
  runs, not automatically for every large all-pairs sweep.

Bounded citation chasing:
- `--citation-chase benchmark`: follow references/citations from benchmark
  papers already in `data/raw/benchmark_manifest.json`.
- `--citation-chase query-results`: follow references/citations from the first
  merged query results.
- `--citation-chase-directions references|citations|both`: choose edge direction.
- Keep `--citation-chase-max-source-dois` and
  `--citation-chase-max-results-per-doi` small until Semantic Scholar API limits
  are stable.

Example hardened discovery smoke run:

`python pipeline/ingest/run_extensive_search.py --dataset all --provider comprehensive --query-variant-mode conservative --citation-chase benchmark --citation-chase-directions references --citation-chase-max-source-dois 20 --citation-chase-max-results-per-doi 20 --max-results-per-seed 80 --max-results 8000 --skip-unpaywall-enrichment --discover-only`

Custom seeds:
`python pipeline/ingest/discover_literature.py --dataset disorder --seed \"MDMA PTSD randomized trial|MDMA|Post-traumatic stress disorder\"`

### Rate limits
- Semantic Scholar is stricter, so default is conservative (`0.33 req/s`).
- OpenAlex requires a free API key for API access; default is `2.0 req/s`.
- PubMed/PMC default is `2.5 req/s`, below NCBI's no-key limit.
- Crossref default is `5.0 req/s`.
- Unpaywall default is `2.0 req/s`; it requires a real email for DOI lookups.
- Configure local credentials in `pipeline/config.local.yaml` or override with CLI flags.

### Long-term local credential setup
Keep real keys out of tracked config. Copy the local template once:

`cp pipeline/config.local.example.yaml pipeline/config.local.yaml`

`chmod 600 pipeline/config.local.yaml`

Then edit `pipeline/config.local.yaml` with:
- OpenAlex free API key (`openalex.api_key`)
- NCBI email and optional API key (`pubmed.email`, `pubmed.api_key`)
- Crossref polite-pool email (`crossref.email`)
- Unpaywall email (`unpaywall.email`)
- optional Semantic Scholar API key (`semantic_scholar.api_key`)

`pipeline/config.local.yaml` is ignored by git. Scripts that use the default
`pipeline/config.example.yaml` automatically overlay the local file when it
exists, so day-to-day commands do not need credential flags.

## Recommended principled search strategy (high recall + efficient + reproducible)
Use this sequence for large runs:
1. broad/faster discovery pass (OpenAlex-focused)
2. targeted high-recall expansion pass (hybrid)
3. recall audit against a known DOI benchmark, with an optional failing gate
4. only then run metadata sync, triage, and PDF download

Before a major run, copy `data/raw/search_manifest.template.json` to a
dataset/run-specific manifest and record the exact databases, query blocks,
entity sets, inclusion/exclusion rules, and recall thresholds. The manifest is
the reproducibility record; the generated discovery report is the execution
record.

Generate a source-specific supplement plan before downstream evidence building:

`python pipeline/ingest/build_discovery_supplement_plan.py --dataset mechanistic`

`python pipeline/ingest/build_discovery_supplement_plan.py --dataset disorder`

This writes:
- `data/processed/discovery_supplement_plan_mechanistic.json`
- `data/processed/discovery_supplement_plan_disorder.json`

These plans cover non-DOI-search sources:
- mechanistic: ChEMBL and BindingDB assay/binding supplements
- disorder: ClinicalTrials.gov registry supplements

They are intentionally plans, not DOI queues. Their outputs should become
source-specific evidence rows, because registry records and assay databases are
not the same kind of object as papers.

The standing recall benchmark lives in `data/raw/benchmark_manifest.json`.
It records why each must-find DOI is in the benchmark, which dataset it belongs
to, and whether it is part of the tuning set. The legacy plain-text DOI lists are
kept for compatibility, but new recall gates should use the manifest.

Every discovery run also writes a cumulative ledger:
- `data/processed/discovery_ledger_mechanistic.json`
- `data/processed/discovery_ledger_disorder.json`

The ledger preserves DOIs seen in previous runs, marks whether each DOI was seen
and retained in the latest run, and records benchmark/triage/library/curated
contexts. This prevents a capped queue from being mistaken for the full
discovery history.

If a discovery run used `--max-results` and you later want the full latest-run
queue without rerunning APIs, export it from the ledger:

`python pipeline/ingest/export_discovery_queue_from_ledger.py --dataset mechanistic --max-results 0`

`python pipeline/ingest/export_discovery_queue_from_ledger.py --dataset disorder --max-results 0`

This rewrites `data/raw/doi_queue.<dataset>.discovered.txt` from latest-run
ledger entries and writes `data/processed/discovery_queue_export_<dataset>.json`
as provenance.

### Step A: broad/faster discovery pass
Run one dataset at a time first for easy monitoring:

`python pipeline/ingest/run_extensive_search.py --dataset mechanistic --provider openalex --expand-seeds-from-config --auto-template-mode focused --auto-max-pairs 800 --auto-max-seeds 1200 --max-results-per-seed 40 --max-results 5000 --discover-only`

`python pipeline/ingest/run_extensive_search.py --dataset disorder --provider openalex --expand-seeds-from-config --auto-template-mode focused --auto-max-pairs 800 --auto-max-seeds 1200 --max-results-per-seed 40 --max-results 5000 --discover-only`

Before Step B, check seed coverage:

`python pipeline/ingest/audit_discovery_seeds.py --dataset mechanistic --balanced-seed-profile coverage`

`python pipeline/ingest/audit_discovery_seeds.py --dataset disorder --balanced-seed-profile coverage`

### Step B: targeted high-recall expansion pass
Use hybrid provider with broader templates after Step A:

`python pipeline/ingest/run_extensive_search.py --dataset mechanistic --provider hybrid --expand-seeds-from-config --auto-template-mode broad --auto-max-pairs 1400 --auto-max-seeds 1800 --balanced-seed-profile coverage --max-results-per-seed 80 --max-results 8000 --semantic-scholar-rps 0.5 --openalex-rps 3.0 --max-retries 3 --discover-only`

`python pipeline/ingest/run_extensive_search.py --dataset disorder --provider hybrid --expand-seeds-from-config --auto-template-mode broad --auto-max-pairs 1400 --auto-max-seeds 1800 --balanced-seed-profile coverage --max-results-per-seed 80 --max-results 8000 --semantic-scholar-rps 0.5 --openalex-rps 3.0 --max-retries 3 --discover-only`

Use `--provider comprehensive` for the defensible recall pass after tuning seeds:

`python pipeline/ingest/run_extensive_search.py --dataset disorder --provider comprehensive --expand-seeds-from-config --auto-template-mode broad --auto-max-pairs 1400 --auto-max-seeds 1800 --max-results-per-seed 80 --max-results 8000 --semantic-scholar-rps 0.5 --openalex-rps 3.0 --pubmed-rps 2.5 --pmc-rps 2.5 --crossref-rps 5.0 --max-retries 3 --skip-unpaywall-enrichment --discover-only`

Notes:
- The new `run_extensive_search.py` flags `--semantic-scholar-rps`, `--openalex-rps`,
  and `--max-retries` let you tune speed/retry policy without editing config.
- If you get 429/rate-limit errors, reduce RPS values.
- If retrieval quality drops, reduce speed and/or increase retries.
- For recall-only discovery runs, use `--skip-unpaywall-enrichment` and defer
  OA/PDF enrichment to the paper-library sync stage.

### Step C: recall audit (benchmark gate)
Maintain the structured benchmark manifest:
- `data/raw/benchmark_manifest.json`

Run the recall audit:

`python pipeline/ingest/recall_audit.py --dataset mechanistic`

`python pipeline/ingest/recall_audit.py --dataset disorder`

Fail the audit when benchmark recall misses the threshold:

`python pipeline/ingest/recall_audit.py --dataset mechanistic --min-discovered 95 --fail-under-threshold`

`python pipeline/ingest/recall_audit.py --dataset disorder --min-discovered 95 --fail-under-threshold`

Outputs:
- `data/processed/recall_audit_<dataset>.json`
- `data/processed/recall_audit_<dataset>.csv`

Suggested gate before sync/download:
- `in_discovered_queue` coverage >= 95% for benchmark DOIs
- if below threshold: add synonyms/seeds and rerun discovery

`run_extensive_search.py` can enforce this directly:

`python pipeline/ingest/run_extensive_search.py --dataset mechanistic --provider hybrid --expand-seeds-from-config --auto-template-mode broad --max-results-per-seed 80 --max-results 8000 --recall-gate`

With `--recall-gate`, discovery must recover at least 95% of benchmark DOIs by
default, and post-triage recall must retain at least 90%. Override with
`--min-discovered-recall` and `--min-triage-recall` when a protocol specifies a
different threshold.

Protected retention is enabled by default. Benchmark, triage, paper-library, and
curated DOIs found by the current run are retained before `--max-results` is
applied, so a known important paper does not disappear just because many newer or
higher-ranked candidates were also found. Use `--disable-protected-retention`
only for diagnostic comparisons.

### Step D: sync + triage + download
After passing recall gate:

`python pipeline/ingest/run_extensive_search.py --dataset mechanistic --provider hybrid --expand-seeds-from-config --auto-template-mode broad --auto-max-pairs 1400 --auto-max-seeds 1800 --max-results-per-seed 80 --max-results 8000 --semantic-scholar-rps 0.5 --openalex-rps 3.0 --max-retries 3`

`python pipeline/ingest/run_extensive_search.py --dataset disorder --provider hybrid --expand-seeds-from-config --auto-template-mode broad --auto-max-pairs 1400 --auto-max-seeds 1800 --max-results-per-seed 80 --max-results 8000 --semantic-scholar-rps 0.5 --openalex-rps 3.0 --max-retries 3`

Discovery outputs:
- `data/raw/doi_queue.<dataset>.discovered.txt`
- `data/processed/discovery_report_<dataset>.json`
- `data/processed/discovery_ledger_<dataset>.json`

## Input format
Queue templates:
- `data/raw/doi_queue.mechanistic.template.txt`
- `data/raw/doi_queue.disorder.template.txt`
- discovery queues:
  - `data/raw/doi_queue.mechanistic.discovered.txt`
  - `data/raw/doi_queue.disorder.discovered.txt`

Both use the same line format:
- `doi,compound,target_or_disorder,optional_study_title,optional_study_year,optional_authors`
- Lines starting with `#` are ignored.

## Run
Mechanistic stubs:
`python pipeline/ingest/seed_from_dois.py --dataset mechanistic --doi-file data/raw/doi_queue.mechanistic.template.txt --replace`

Disorder stubs:
`python pipeline/ingest/seed_from_dois.py --dataset disorder --doi-file data/raw/doi_queue.disorder.template.txt --replace`

Mechanistic stubs from discovered queue:
`python pipeline/ingest/seed_from_dois.py --dataset mechanistic --doi-file data/raw/doi_queue.mechanistic.discovered.txt --replace`

Disorder stubs from discovered queue:
`python pipeline/ingest/seed_from_dois.py --dataset disorder --doi-file data/raw/doi_queue.disorder.discovered.txt --replace`

## Outputs
- `data/processed/mechanistic_claim_stubs.json`
- `data/processed/mechanistic_claim_stubs.csv`
- `data/processed/disorder_claim_stubs.json`
- `data/processed/disorder_claim_stubs.csv`

## Paper library sync (abstracts + OA + PDFs)
Run after discovery so the queue contains candidate DOIs.

Default provider order is `pubmed,pmc,unpaywall,crossref,openalex`: PubMed/PMC first for biomedical abstracts and PMCID/full-text signals, Unpaywall next for legal OA/PDF resolution, then Crossref/OpenAlex as broader metadata fallbacks. If `unpaywall.email` is missing from local config, Unpaywall is skipped with a warning.

Mechanistic:
`python pipeline/ingest/sync_paper_library.py --dataset mechanistic`

Disorder:
`python pipeline/ingest/sync_paper_library.py --dataset disorder`

Metadata-only dry run (no downloads):
`python pipeline/ingest/sync_paper_library.py --dataset mechanistic --skip-download`

Recommended sequence to avoid downloading irrelevant PDFs:
1. run sync with `--skip-download` (metadata/abstracts only)
2. run triage:
   `python pipeline/review/triage_paper_library.py --dataset <dataset>`
3. sync again using triage queue:
   `python pipeline/ingest/sync_paper_library.py --dataset <dataset> --doi-file data/raw/doi_queue.<dataset>.triage_relevant.txt`

Run extensive discovery + sync for both datasets in one command:
`python pipeline/ingest/run_extensive_search.py --dataset all --provider hybrid --max-results-per-seed 100 --max-results 600`

High-recall extensive run with auto-seed expansion:
`python pipeline/ingest/run_extensive_search.py --dataset all --provider hybrid --expand-seeds-from-config --auto-template-mode broad --auto-max-pairs 1200 --auto-max-seeds 3000 --max-results-per-seed 120 --max-results 5000`

Use `--verbose` to print raw child script logs.

`run_extensive_search.py` defaults to triage-first download:
1. discovery
2. metadata sync (`--skip-download`)
3. triage (`triage_paper_library.py`)
4. triage-queue download sync

Retry failed/no-URL PDF rows from existing paper DB:
`python pipeline/ingest/retry_pdf_downloads.py --dataset mechanistic`
`python pipeline/ingest/retry_pdf_downloads.py --dataset disorder`

Import manually acquired PDFs by DOI-style filenames:
`python pipeline/ingest/import_manual_pdfs.py --dataset mechanistic --source-dir /absolute/path/to/manual_pdfs --apply`
`python pipeline/ingest/import_manual_pdfs.py --dataset disorder --source-dir /absolute/path/to/manual_pdfs --apply`

Outputs:
- `data/raw/papers/<dataset>/pdfs/*.pdf`
- `data/processed/paper_library_<dataset>.json`
- `data/processed/paper_library_<dataset>.csv`
- `data/processed/paper_inventory_<dataset>.json`
- `data/processed/paper_inventory_<dataset>.csv`
- `data/processed/paper_inventory_<dataset>.md`
- `data/raw/doi_queue.<dataset>.triage_relevant.txt` (from triage step)
- `data/raw/doi_queue.<dataset>.retry_pdf.txt` (from retry helper)
- `data/processed/manual_pdf_import_report_<dataset>.json`

The inventory report explicitly separates papers into:
- `in_database`: PDF already present locally
- `needs_download`: OA paper missing a local PDF (e.g., failed/no direct PDF link)
- `needs_manual_access`: closed/unknown-access papers that need manual acquisition

The Markdown report (`paper_inventory_<dataset>.md`) is a human-readable paper
coverage document with two sections:
- papers with local PDF
- papers missing local PDF

## Notes
- Stubs are intentionally incomplete and tagged with `stub_status=pending_curation`.
- Do not run strict validation on stubs until they are curated into
  `data/curated/*.json` and `data/curated/*.csv`.
- `data/curated/entity_registry.json` is the warning-level registry for
  compound, target, and disorder labels. Keep it synchronized with curated rows,
  then enrich entries with PubChem, ChEMBL, BindingDB, UniProt, MONDO/EFO, and
  MeSH IDs before turning registry coverage into a hard validator.
