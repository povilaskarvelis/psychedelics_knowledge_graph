# Ingest: Web Discovery + DOI Queue to Claim Stubs

This stage has three steps:
1. Discover literature from web APIs and write DOI queue files.
2. Convert DOI queues into normalized curation stubs.
3. Sync the local paper library (abstracts + OA metadata + PDF downloads).

## Discovery (web search)
Default provider is `semantic_scholar` (relevance-focused), with `openalex` and
`hybrid` also available.

Run discovery for mechanistic:
`python pipeline/ingest/discover_literature.py --dataset mechanistic`

Run discovery for disorder:
`python pipeline/ingest/discover_literature.py --dataset disorder`

Hybrid mode:
`python pipeline/ingest/discover_literature.py --dataset mechanistic --provider hybrid`

Extensive retrieval (hundreds of papers):
`python pipeline/ingest/discover_literature.py --dataset mechanistic --provider hybrid --max-results-per-seed 100 --max-results 600`

High-recall seed expansion from allowlists in `pipeline/config.example.yaml`:
`python pipeline/ingest/discover_literature.py --dataset mechanistic --provider hybrid --expand-seeds-from-config --auto-template-mode broad --auto-max-pairs 1200 --auto-max-seeds 3000 --max-results-per-seed 120 --max-results 5000`

Notes for auto-seed controls:
- `--expand-seeds-from-config`: add generated seeds on top of defaults/manual seeds
- `--auto-seeds-only`: skip defaults and use only generated seeds
- `--auto-max-pairs 0` and `--auto-max-seeds 0`: remove generation caps (can be very large)

Custom seeds:
`python pipeline/ingest/discover_literature.py --dataset disorder --seed \"MDMA PTSD randomized trial|MDMA|Post-traumatic stress disorder\"`

### Rate limits
- Semantic Scholar is stricter, so default is conservative (`0.33 req/s`).
- OpenAlex default is `2.0 req/s`.
- Configure in `pipeline/config.example.yaml` or override with CLI flags.

Discovery outputs:
- `data/raw/doi_queue.<dataset>.discovered.txt`
- `data/processed/discovery_report_<dataset>.json`

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
