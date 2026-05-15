# Ingest: Web Discovery + DOI Queue to Claim Stubs

This stage has five steps:
1. Discover literature from web APIs and write DOI queue files.
2. Add only genuinely new DOI rows to the next queue.
3. Sync the local paper library for metadata/abstracts.
4. Run deterministic + LLM abstract screening and write relevant/uncertain
   DOI-context queues.
5. Download legal OA PDFs only for screened relevant/uncertain rows.

Claim stubs should normally be generated from
`data/raw/doi_queue.<dataset>.llm_relevant.txt`, not directly from the full
discovered queue. The old triage-relevant queue is retained for legacy audits.

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

V2 comprehensive baseline search:

`python pipeline/ingest/build_boolean_search_modules.py --dataset all`

`python pipeline/ingest/build_comprehensive_search_plan.py --dataset all --profile baseline`

These write exact seed files under
`data/raw/search_strategies/comprehensive_baseline_v1/`. The Boolean module
files are the primary systematic-search layer; the generated pair-grid files
are the audit/gap-check layer.

Run Boolean module discovery examples:

`python pipeline/ingest/discover_literature.py --dataset mechanistic --provider openalex --seed-file data/raw/search_strategies/comprehensive_baseline_v1/boolean_modules/mechanistic_boolean_openalex_seeds.csv --max-results-per-seed 500 --max-results 0 --disable-ledger --disable-protected-retention --skip-unpaywall-enrichment`

`python pipeline/ingest/discover_literature.py --dataset disorder --provider pubmed --seed-file data/raw/search_strategies/comprehensive_baseline_v1/boolean_modules/disorder_boolean_pubmed_seeds.csv --max-results-per-seed 500 --max-results 0`

Recommended baseline caps:
- Boolean primary modules: `500`
- Boolean dense-topic modules: `1000`
- Mechanistic pair-grid audit: `20-50`
- Indication pair-grid audit: `10-20`

The Boolean module builder writes combined files plus module-type-specific files
such as `*_primary_boolean_seeds.csv` and `*_dense_topic_seeds.csv`, so primary
and dense-topic modules can be run with different caps.

Summarize Boolean module runs after discovery and the new-DOI gate:

`python pipeline/ingest/summarize_boolean_module_runs.py`

Calibration before a full baseline run:

`python pipeline/ingest/build_search_calibration_batches.py --dataset all`

Fast OpenAlex calibration for one dataset:

`python pipeline/ingest/discover_literature.py --dataset mechanistic --provider openalex --seed-file data/raw/search_strategies/comprehensive_baseline_v1/calibration/mechanistic_calibration_seeds.csv --query-variant-mode conservative --max-results-per-seed 10 --max-results 0 --disable-ledger --disable-protected-retention --skip-unpaywall-enrichment --queue-out data/raw/search_strategies/comprehensive_baseline_v1/calibration/openalex/mechanistic_discovered.txt --report-out data/raw/search_strategies/comprehensive_baseline_v1/calibration/openalex/mechanistic_discovery_report.json`

For noisy OpenAlex pair searches, prefer title/abstract matching over broad
title/abstract/full-text search:

`python pipeline/ingest/discover_literature.py --dataset disorder --provider openalex --seed-file data/raw/search_strategies/comprehensive_baseline_v1/disorder_seeds.csv --openalex-search-field title_and_abstract --max-results-per-seed 20 --max-results 0`

Summarize calibration outputs after running discovery and the new-DOI gate:

`python pipeline/ingest/summarize_search_calibration.py --dataset all`

The calibration files are intentionally separate from the live discovery queues
so exploratory runs do not overwrite corpus state.

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
- `--citation-chase known-study-set`: follow references/citations from known
  relevant studies already in `data/raw/benchmark_manifest.json`.
- `--citation-chase benchmark`: compatibility alias for older commands.
- `--citation-chase query-results`: follow references/citations from the first
  merged query results.
- `--citation-chase-directions references|citations|both`: choose edge direction.
- Keep `--citation-chase-max-source-dois` and
  `--citation-chase-max-results-per-doi` small until Semantic Scholar API limits
  are stable.

Example hardened discovery smoke run:

`python pipeline/ingest/run_extensive_search.py --dataset all --provider comprehensive --query-variant-mode conservative --citation-chase known-study-set --citation-chase-directions references --citation-chase-max-source-dois 20 --citation-chase-max-results-per-doi 20 --max-results-per-seed 80 --max-results 8000 --skip-unpaywall-enrichment --discover-only`

Custom seeds:
`python pipeline/ingest/discover_literature.py --dataset disorder --seed \"MDMA PTSD randomized trial|MDMA|Post-traumatic stress disorder\"`

Custom seed file:
`python pipeline/ingest/discover_literature.py --dataset disorder --seed-file data/raw/search_strategies/comprehensive_baseline_v1/disorder_seeds.csv --provider comprehensive`

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
3. search completeness check against known relevant studies, with an optional failing gate
4. only then run metadata sync, triage, and PDF download

Before a major run, copy `data/raw/search_manifest.template.json` to a
dataset/run-specific manifest and record the exact databases, query blocks,
entity sets, inclusion/exclusion rules, and completeness thresholds. The manifest is
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

For registry enrichment tied to papers already found by literature search, use
the standalone post-screening stage instead:

`python pipeline/enrich/enrich_trial_registries.py --dataset disorder`

This reads screened disorder candidates with captured `trial_registry_ids` and
writes separate registry cache/report files without modifying the paper library.

The known relevant study set lives in `data/raw/benchmark_manifest.json`.
The filename is retained for compatibility, but the file should be described as
a known-study set or search completeness set in project methodology. It records
why each DOI is in scope, which dataset it belongs to, how it was selected, and
how it should be used during iterative search strategy development. The legacy
plain-text DOI lists are kept for compatibility, but new completeness checks
should use the structured manifest.

Every discovery run also writes a cumulative ledger:
- `data/processed/discovery_ledger_mechanistic.json`
- `data/processed/discovery_ledger_disorder.json`

The ledger preserves DOIs seen in previous runs, marks whether each DOI was seen
and retained in the latest run, and records known-study/triage/library/curated
contexts. This prevents a capped queue from being mistaken for the full
discovery history.

If a discovery run used `--max-results` and you later want the full latest-run
queue without rerunning APIs, export it from the ledger:

`python pipeline/ingest/export_discovery_queue_from_ledger.py --dataset mechanistic --max-results 0`

`python pipeline/ingest/export_discovery_queue_from_ledger.py --dataset disorder --max-results 0`

This rewrites `data/raw/doi_queue.<dataset>.discovered.txt` from latest-run
ledger entries and writes `data/processed/discovery_queue_export_<dataset>.json`
as provenance.

Before metadata sync, remove papers already known to the corpus. The
`run_extensive_search.py` wrapper does this automatically after discovery; run
the command directly when you are checking an existing DOI queue:

`python pipeline/ingest/add_new_dois.py --dataset mechanistic --input data/raw/doi_queue.mechanistic.discovered.txt`

`python pipeline/ingest/add_new_dois.py --dataset disorder --input data/raw/doi_queue.disorder.discovered.txt`

This writes:
- `data/raw/doi_queue.<dataset>.new.txt`
- `data/processed/add_new_dois_report_<dataset>.json`
- `data/processed/rediscovered_dois_<dataset>.csv`
- `data/processed/missing_or_invalid_dois_<dataset>.csv`
- `data/processed/input_duplicate_dois_<dataset>.csv`

The gate is DOI-level. If a DOI is already known anywhere in the paper corpus,
it is not added as a new paper. Rediscoveries are logged for provenance, but
they do not continue through metadata/PDF processing as new papers.

By default, the gate does not treat the discovery ledger itself as the existing
paper corpus, because the ledger is updated during the current discovery run.
Use `--include-discovery-ledger` only when you explicitly want to block DOI rows
that have merely been discovered before.

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

Use `--provider comprehensive` for the defensible search-completeness pass after
seed and synonym development:

`python pipeline/ingest/run_extensive_search.py --dataset disorder --provider comprehensive --expand-seeds-from-config --auto-template-mode broad --auto-max-pairs 1400 --auto-max-seeds 1800 --max-results-per-seed 80 --max-results 8000 --semantic-scholar-rps 0.5 --openalex-rps 3.0 --pubmed-rps 2.5 --pmc-rps 2.5 --crossref-rps 5.0 --max-retries 3 --skip-unpaywall-enrichment --discover-only`

Notes:
- The new `run_extensive_search.py` flags `--semantic-scholar-rps`, `--openalex-rps`,
  and `--max-retries` let you tune speed/retry policy without editing config.
- If you get 429/rate-limit errors, reduce RPS values.
- If retrieval quality drops, reduce speed and/or increase retries.
- For search-completeness discovery runs, use `--skip-unpaywall-enrichment` and defer
  OA/PDF enrichment to the paper-library sync stage.

### Step C: search completeness check
Maintain the structured known relevant study set:
- `data/raw/benchmark_manifest.json`

Run the completeness check:

`python pipeline/ingest/recall_audit.py --dataset mechanistic`

`python pipeline/ingest/recall_audit.py --dataset disorder`

Fail the audit when known-study retrieval misses the threshold:

`python pipeline/ingest/recall_audit.py --dataset mechanistic --min-discovered 95 --fail-under-threshold`

`python pipeline/ingest/recall_audit.py --dataset disorder --min-discovered 95 --fail-under-threshold`

Outputs:
- `data/processed/recall_audit_<dataset>.json`
- `data/processed/recall_audit_<dataset>.csv`

Suggested gate before sync/download:
- `in_discovered_queue` coverage >= 95% for known relevant study DOIs
- if below threshold: add synonyms/seeds or document scope/indexing rationale,
  then rerun discovery

`run_extensive_search.py` can enforce this directly:

`python pipeline/ingest/run_extensive_search.py --dataset mechanistic --provider hybrid --expand-seeds-from-config --auto-template-mode broad --max-results-per-seed 80 --max-results 8000 --recall-gate`

With `--recall-gate`, discovery must recover at least 95% of known relevant
study DOIs by default, and post-triage retention must retain at least 90%. Override with
`--min-discovered-recall` and `--min-triage-recall` when a protocol specifies a
different threshold.

Protected retention is enabled by default. Benchmark, triage, paper-library, and
curated DOIs found by the current run are retained before `--max-results` is
applied, so a known important paper does not disappear just because many newer or
higher-ranked candidates were also found. Use `--disable-protected-retention`
only for diagnostic comparisons.

### Step D: sync + triage + download
After passing the completeness check:

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
- `doi,compound,target_or_disorder,optional_study_title,optional_study_year,optional_authors,...optional_paper_metadata`
- Optional paper metadata columns are accepted after authors in this order:
  `study_journal`, `publication_type`, `trial_registry_ids`,
  `publication_date`, `journal_issn`, `journal_eissn`, `publisher`,
  `mesh_terms`, `keywords`, `funders`, `grant_ids`, `related_dois`,
  `publication_relations`, `is_retracted`, `has_correction`, `language`,
  `semantic_scholar_id`.
- Lines starting with `#` are ignored.

Stubs are deduplicated by `DOI + compound + target_or_disorder`, not by DOI
alone. This preserves multi-context papers that support more than one graph
edge.

## Run
Mechanistic stubs:
`python pipeline/ingest/seed_from_dois.py --dataset mechanistic --doi-file data/raw/doi_queue.mechanistic.template.txt --replace`

Disorder stubs:
`python pipeline/ingest/seed_from_dois.py --dataset disorder --doi-file data/raw/doi_queue.disorder.template.txt --replace`

Recommended stubs from LLM relevant queues:
`python pipeline/ingest/seed_from_dois.py --dataset mechanistic --doi-file data/raw/doi_queue.mechanistic.llm_relevant.txt --replace`

`python pipeline/ingest/seed_from_dois.py --dataset disorder --doi-file data/raw/doi_queue.disorder.llm_relevant.txt --replace`

Avoid generating production stubs directly from
`data/raw/doi_queue.<dataset>.discovered.txt`; that queue has not been screened
and can include context noise that abstract screening is designed to remove.
Use `pipeline/review/triage_paper_library.py` only for legacy audits or
targeted comparisons.

## Outputs
- `data/processed/mechanistic_claim_stubs.json`
- `data/processed/mechanistic_claim_stubs.csv`
- `data/processed/disorder_claim_stubs.json`
- `data/processed/disorder_claim_stubs.csv`

## Paper library sync (abstracts + OA + PDFs)
Run after discovery so the queue contains candidate DOIs.

Default provider order is
`pubmed,pmc,unpaywall,crossref,openalex,semantic_scholar`: PubMed/PMC first for
biomedical abstracts, publication dates, publication types, journals, ISSNs,
MeSH/keywords, trial identifiers, and PMCID/full-text signals; Unpaywall next
for legal OA/PDF resolution and venue metadata; then Crossref, OpenAlex, and
Semantic Scholar as broader metadata fallbacks. If `unpaywall.email` is missing
from local config, Unpaywall is skipped with a warning.

Mechanistic:
`python pipeline/ingest/sync_paper_library.py --dataset mechanistic`

Disorder:
`python pipeline/ingest/sync_paper_library.py --dataset disorder`

Metadata-only dry run (no downloads):
`python pipeline/ingest/sync_paper_library.py --dataset mechanistic --skip-download`

Recommended sequence to avoid downloading irrelevant PDFs:
1. run sync with `--skip-download` (metadata/abstracts only)
2. run deterministic pre-screen and LLM abstract screening:
   `python pipeline/review/run_local_llm_abstract_screening.py --dataset <dataset> --deterministic-prescreen --deterministic-prescreen-only --only-with-abstract --only-undownloaded`
   `python pipeline/review/run_local_llm_abstract_screening.py --dataset <dataset> --doi-file data/raw/doi_queue.<dataset>.deterministic_prescreen_retained.txt --model qwen3:14b --only-with-abstract --continue-on-error --timeout-sec 0 --resume-from-checkpoint --num-ctx 4096`
3. sync again using the LLM full-text candidate queue:
   `python pipeline/ingest/sync_paper_library.py --dataset <dataset> --doi-file data/raw/doi_queue.<dataset>.llm_fulltext_candidates.txt`

Run extensive discovery + sync for both datasets in one command:
`python pipeline/ingest/run_extensive_search.py --dataset all --provider hybrid --max-results-per-seed 100 --max-results 600`

High-recall extensive run with auto-seed expansion:
`python pipeline/ingest/run_extensive_search.py --dataset all --provider hybrid --expand-seeds-from-config --auto-template-mode broad --auto-max-pairs 1200 --auto-max-seeds 3000 --max-results-per-seed 120 --max-results 5000`

Use `--verbose` to print raw child script logs.

`run_extensive_search.py` still supports the legacy triage-first orchestration:
1. discovery
2. metadata sync (`--skip-download`)
3. triage (`triage_paper_library.py`)
4. triage-queue download sync

For the LLM-screening workflow, run discovery/sync/screen/download as separate
commands so checkpoint materialization and long-running model jobs remain
observable.

Retry failed/no-URL PDF rows from existing paper DB:
`python pipeline/ingest/retry_pdf_downloads.py --dataset mechanistic`
`python pipeline/ingest/retry_pdf_downloads.py --dataset disorder`

The retry helper builds a focused DOI queue from existing failed/no-URL rows
and calls `sync_paper_library.py` again. It is useful after downloader fixes or
provider-order changes because it avoids rerunning the full paper library sync.
Use `--doi-file data/raw/doi_queue.<dataset>.triage_relevant.txt` to constrain
retries to the current evidence-building set.

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
- `data/raw/doi_queue.<dataset>.llm_fulltext_candidates.txt` (from LLM abstract screening)
- `data/raw/doi_queue.<dataset>.llm_relevant.txt` (context-verified LLM relevant rows)
- `data/raw/doi_queue.<dataset>.triage_relevant.txt` (legacy triage step)
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
