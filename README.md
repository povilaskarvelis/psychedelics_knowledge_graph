# psychedelics_knowledge_graph

Knowledge Graph Pipeline (Paper-First)

This repository is a deterministic pipeline for building a provenance-aware
knowledge graph from scientific papers.

It supports:
- literature discovery from APIs
- open-access detection + PDF download
- claim stub generation
- curator review + promotion
- strict validation
- ORKG-ready payload export

The current example domain is psychedelics, but the workflow is reusable for
other domains with configuration updates.

## What You Need To Provide

Before running the pipeline, prepare these inputs:

1. Domain scope:
   - define your entities and inclusion rules in `docs/domain_scope.md`
   - define graph entities/relations in `schema/kg_schema.yaml`
2. Allowed vocabularies:
   - set `allowed_compounds`, `allowed_targets`, `allowed_disorders` in
     `pipeline/config.example.yaml` (or your own config file)
3. Claim schemas:
   - update required fields/enums in `schema/claims.schema.json` and
     `schema/disorder_claims.schema.json`
   - update disorder canonicalization/alias rules in
     `schema/disorder_canonicalization.json`
4. Seed papers or search seeds:
   - queue templates:
     - `data/raw/doi_queue.mechanistic.template.txt`
     - `data/raw/doi_queue.disorder.template.txt`
   - line format:
     - `doi,compound,target_or_disorder,optional_study_title,optional_study_year,optional_authors`
5. Optional API config:
   - OpenAlex email and rate limits in `pipeline/config.example.yaml`
   - Semantic Scholar API key/rate limits in `pipeline/config.example.yaml`

## Repo Structure

- `data/raw/`: source inputs and local PDFs
- `data/curated/`: curated claims (CSV/JSON)
- `data/processed/`: reports, stubs, validation, and payload outputs
- `schema/`: JSON schemas and KG model
- `pipeline/`: ingest, review, extract, validate, publish scripts
- `docs/`: policies and design notes
- `ui/`: local demo UI

Local PDF downloads are intentionally ignored by git:
- `data/raw/papers/`

## End-to-End Workflow

### 0. Prerequisite

- Python 3.10+ (all scripts are standard library only).

### 1. Discover literature

Generate DOI queues from web APIs:

```bash
python pipeline/ingest/discover_literature.py --dataset mechanistic
python pipeline/ingest/discover_literature.py --dataset disorder
```

Extensive retrieval example (hundreds of papers):

```bash
python pipeline/ingest/discover_literature.py --dataset mechanistic --provider hybrid --max-results-per-seed 100 --max-results 600
python pipeline/ingest/discover_literature.py --dataset disorder --provider hybrid --max-results-per-seed 100 --max-results 600
```

High-recall retrieval with config-driven seed expansion:

```bash
python pipeline/ingest/discover_literature.py --dataset mechanistic --provider hybrid --expand-seeds-from-config --auto-template-mode broad --auto-max-pairs 1200 --auto-max-seeds 3000 --max-results-per-seed 120 --max-results 5000
python pipeline/ingest/discover_literature.py --dataset disorder --provider hybrid --expand-seeds-from-config --auto-template-mode broad --auto-max-pairs 1200 --auto-max-seeds 3000 --max-results-per-seed 120 --max-results 5000
```

Outputs:
- `data/raw/doi_queue.mechanistic.discovered.txt`
- `data/raw/doi_queue.disorder.discovered.txt`
- `data/processed/discovery_report_mechanistic.json`
- `data/processed/discovery_report_disorder.json`

### 2. Sync paper library (abstracts + OA + PDFs)

Fetch abstract metadata, detect open access, and download OA PDFs:

```bash
python pipeline/ingest/sync_paper_library.py --dataset mechanistic
python pipeline/ingest/sync_paper_library.py --dataset disorder
```

Metadata-only (no download):

```bash
python pipeline/ingest/sync_paper_library.py --dataset mechanistic --skip-download
```

Recommended high-precision flow:
1. run metadata-only sync first (`--skip-download`)
2. run triage (`pipeline/review/triage_paper_library.py`)
3. download only triaged-relevant papers using:
`--doi-file data/raw/doi_queue.<dataset>.triage_relevant.txt`

Outputs:
- `data/raw/papers/<dataset>/pdfs/*.pdf`
- `data/processed/paper_library_<dataset>.json`
- `data/processed/paper_library_<dataset>.csv`
- `data/processed/paper_inventory_<dataset>.json`
- `data/processed/paper_inventory_<dataset>.csv`
- `data/processed/paper_inventory_<dataset>.md` (human-readable has-PDF vs missing-PDF report)
- `data/raw/doi_queue.<dataset>.retry_pdf.txt` (from retry helper)
- `data/processed/manual_pdf_import_report_<dataset>.json`

One-command extensive run (discovery + sync for both datasets):

```bash
python pipeline/ingest/run_extensive_search.py --dataset all --provider hybrid --max-results-per-seed 100 --max-results 600
```

High-recall one-command run (auto-seed expansion + broader query templates):

```bash
python pipeline/ingest/run_extensive_search.py --dataset all --provider hybrid --expand-seeds-from-config --auto-template-mode broad --auto-max-pairs 1200 --auto-max-seeds 3000 --max-results-per-seed 120 --max-results 5000
```

This command now runs a triage-first download strategy by default:
1. discovery
2. metadata-only sync (`--skip-download`)
3. triage queue generation
4. download sync from `doi_queue.<dataset>.triage_relevant.txt`

Add `--verbose` to show raw sub-command logs for debugging.

Retry failed/no-URL PDF rows:

```bash
python pipeline/ingest/retry_pdf_downloads.py --dataset mechanistic
python pipeline/ingest/retry_pdf_downloads.py --dataset disorder
```

Import manually acquired PDFs into the paper DB:

```bash
python pipeline/ingest/import_manual_pdfs.py --dataset mechanistic --source-dir /absolute/path/to/manual_pdfs --apply
python pipeline/ingest/import_manual_pdfs.py --dataset disorder --source-dir /absolute/path/to/manual_pdfs --apply
```

Inventory status buckets:
- `in_database`: PDF exists locally
- `needs_download`: OA/unknown paper not yet in local DB
- `needs_manual_access`: closed-access paper requiring manual acquisition

### 3. Generate claim stubs from DOI queues

```bash
python pipeline/ingest/seed_from_dois.py --dataset mechanistic --doi-file data/raw/doi_queue.mechanistic.discovered.txt --replace
python pipeline/ingest/seed_from_dois.py --dataset disorder --doi-file data/raw/doi_queue.disorder.discovered.txt --replace
```

Outputs:
- `data/processed/mechanistic_claim_stubs.json`
- `data/processed/disorder_claim_stubs.json`

### 4. Auto-triage paper relevance/source type

Run triage from paper library:

```bash
python pipeline/review/triage_paper_library.py --dataset mechanistic
python pipeline/review/triage_paper_library.py --dataset disorder
```

Apply triage suggestions to stubs:

```bash
python pipeline/review/triage_paper_library.py --dataset mechanistic --apply-to-stubs
python pipeline/review/triage_paper_library.py --dataset disorder --apply-to-stubs
```

Behavior:
- likely irrelevant papers -> `stub_status=excluded_not_relevant` (default)
- review/meta-analysis papers can be relabeled from `source_type=primary_study`
  to `source_type=review` or `source_type=meta_analysis`
- triage queues now include only contexts with matched `(compound, disorder/target)`
  evidence in title/abstract text, reducing false relation mapping
- overlapping disorder labels are canonicalized for graph consistency
  (e.g., `End-of-life anxiety` -> `distress associated with life-threatening disease`)
- writes a filtered queue for targeted PDF download:
  - `data/raw/doi_queue.mechanistic.triage_relevant.txt`
  - `data/raw/doi_queue.disorder.triage_relevant.txt`

Outputs:
- `data/processed/triage_report_mechanistic.json`
- `data/processed/triage_report_mechanistic.csv`
- `data/processed/triage_report_disorder.json`
- `data/processed/triage_report_disorder.csv`

### 5. Review and curate stubs

Abstract-first autofill before queue review:

```bash
python pipeline/review/autofill_stubs_from_abstracts.py --dataset mechanistic --mark-ready --apply
python pipeline/review/autofill_stubs_from_abstracts.py --dataset disorder --mark-ready --apply
```

Mechanistic full-PDF autofill (for affinity fields that abstracts usually miss):

```bash
python pipeline/review/autofill_mechanistic_from_pdfs.py --dataset mechanistic --mark-ready --apply
```

Disorder full-PDF autofill (for outcome/provenance upgrade from abstract-only):

```bash
python pipeline/review/autofill_disorder_from_pdfs.py --dataset disorder --mark-ready --apply
```

Optional (lower confidence threshold, for broader recall):

```bash
python pipeline/review/autofill_mechanistic_from_pdfs.py --dataset mechanistic --mark-ready --min-score 4 --apply
```

Backfill missing `authors` from paper DB/OpenAlex/Crossref before queue review:

```bash
python pipeline/review/backfill_stub_authors.py --dataset mechanistic --mark-ready --apply
python pipeline/review/backfill_stub_authors.py --dataset disorder --mark-ready --apply
```

If you want to force completion when metadata APIs return no author names:

```bash
python pipeline/review/backfill_stub_authors.py --dataset disorder --mark-ready --fallback-unknown --apply
```

Generate review queue:

```bash
python pipeline/review/curation_queue.py --dataset mechanistic
python pipeline/review/curation_queue.py --dataset disorder
```

Mark rows:
- ready: `--mark-ready --apply`
- blocked/manual full text: `--set-status blocked_needs_fulltext --row-indices 2,5 --apply`

Outputs:
- `data/processed/review_queue_mechanistic.json`
- `data/processed/review_queue_disorder.json`
- `data/processed/authors_backfill_report_mechanistic.json`
- `data/processed/authors_backfill_report_disorder.json`
- `data/processed/pdf_autofill_report_mechanistic.json`
- `data/processed/pdf_autofill_report_disorder.json`

### 6. Promote ready stubs into curated datasets

```bash
python pipeline/extract/promote_ready_stubs.py --dataset mechanistic
python pipeline/extract/promote_ready_stubs.py --dataset disorder
```

Apply writes after dry run is clean:

```bash
python pipeline/extract/promote_ready_stubs.py --dataset mechanistic --apply
python pipeline/extract/promote_ready_stubs.py --dataset disorder --apply
```

Outputs:
- `data/processed/promotion_report_mechanistic.json`
- `data/processed/promotion_report_disorder.json`
- applies cleanup of existing curated rows that latest triage marks
  `likely_irrelevant` (before adding new promotions)
- also prunes existing curated context rows that are not present in triage
  `contexts` matched pairs for the same DOI (prevents stale mis-mapped edges)
- updated curated datasets:
  - `data/curated/claims.json`
  - `data/curated/claims.csv`
  - `data/curated/disorder_claims.json`
  - `data/curated/disorder_claims.csv`

### 7. Validate curated datasets

```bash
python pipeline/validate/validate_claims.py
```

Output:
- `data/processed/validation_report.json`

### 8. Export ORKG payloads

```bash
python pipeline/publish/export_orkg_payload.py
```

Outputs:
- `data/processed/orkg_payload_mechanistic.json`
- `data/processed/orkg_payload_mechanistic_primary_only.json`
- `data/processed/orkg_payload_disorder.json`
- `data/processed/orkg_payload_disorder_primary_only.json`
- `data/processed/orkg_payload_manifest.json`

View semantics:
- `orkg_payload_mechanistic.json` and `orkg_payload_disorder.json`: all evidence (`primary_study`, `review`, `meta_analysis`, etc.)
- `orkg_payload_mechanistic_primary_only.json` and `orkg_payload_disorder_primary_only.json`: only rows with `source_type=primary_study`

## Porting This Repo To Another Domain

If someone else wants to build a KG in a different domain, use this sequence:

1. Replace the domain scope:
   - `docs/domain_scope.md`
   - `docs/seed_papers.md` and/or `docs/seed_disorder_papers.md`
2. Replace allowlists:
   - `pipeline/config.example.yaml`
3. Replace schema fields/enums:
   - `schema/claims.schema.json`
   - `schema/disorder_claims.schema.json`
   - optional docs: `schema/claims.schema.md`, `schema/disorder_claims.schema.md`
4. Replace KG model:
   - `schema/kg_schema.yaml`
5. Replace initial DOI queues/seeds:
   - `data/raw/doi_queue.mechanistic.template.txt`
   - `data/raw/doi_queue.disorder.template.txt`
   - default discovery seeds in `pipeline/ingest/discover_literature.py`
6. Run the workflow above and curate claims.

Important constraint:
- The pipeline currently has two built-in dataset tracks: `mechanistic` and
  `disorder`.
- If your new domain needs different dataset names or additional tracks, update
  dataset mappings in:
  - `pipeline/ingest/seed_from_dois.py`
  - `pipeline/ingest/sync_paper_library.py`
  - `pipeline/review/curation_queue.py`
  - `pipeline/review/autofill_stubs_from_curated.py`
  - `pipeline/review/backfill_stub_authors.py`
  - `pipeline/extract/promote_ready_stubs.py`
  - `pipeline/publish/export_orkg_payload.py`

## Minimal Runbook (Copy/Paste)

```bash
# 1) discover papers
python pipeline/ingest/discover_literature.py --dataset mechanistic
python pipeline/ingest/discover_literature.py --dataset disorder

# 2) metadata sync first (no PDFs yet)
python pipeline/ingest/sync_paper_library.py --dataset mechanistic --skip-download
python pipeline/ingest/sync_paper_library.py --dataset disorder --skip-download

# 3) triage and generate filtered DOI queues
python pipeline/review/triage_paper_library.py --dataset mechanistic
python pipeline/review/triage_paper_library.py --dataset disorder

# 4) download PDFs only for triaged-relevant papers
python pipeline/ingest/sync_paper_library.py --dataset mechanistic --doi-file data/raw/doi_queue.mechanistic.triage_relevant.txt
python pipeline/ingest/sync_paper_library.py --dataset disorder --doi-file data/raw/doi_queue.disorder.triage_relevant.txt

# optional: one-command extensive run (discovery + triage-first sync)
python pipeline/ingest/run_extensive_search.py --dataset all --provider hybrid --max-results-per-seed 100 --max-results 600

# optional: high-recall one-command run (config-driven seed expansion)
python pipeline/ingest/run_extensive_search.py --dataset all --provider hybrid --expand-seeds-from-config --auto-template-mode broad --auto-max-pairs 1200 --auto-max-seeds 3000 --max-results-per-seed 120 --max-results 5000

# 5) build stubs from triaged-relevant queues
python pipeline/ingest/seed_from_dois.py --dataset mechanistic --doi-file data/raw/doi_queue.mechanistic.triage_relevant.txt --replace
python pipeline/ingest/seed_from_dois.py --dataset disorder --doi-file data/raw/doi_queue.disorder.triage_relevant.txt --replace

# 6) apply triage labels to stubs (optional but recommended)
python pipeline/review/triage_paper_library.py --dataset mechanistic --apply-to-stubs
python pipeline/review/triage_paper_library.py --dataset disorder --apply-to-stubs

# 7) autofill + curation assists
python pipeline/review/autofill_stubs_from_abstracts.py --dataset mechanistic --mark-ready --apply
python pipeline/review/autofill_stubs_from_abstracts.py --dataset disorder --mark-ready --apply
python pipeline/review/autofill_mechanistic_from_pdfs.py --dataset mechanistic --mark-ready --apply
python pipeline/review/autofill_disorder_from_pdfs.py --dataset disorder --mark-ready --apply
python pipeline/review/backfill_stub_authors.py --dataset mechanistic --mark-ready --apply
python pipeline/review/backfill_stub_authors.py --dataset disorder --mark-ready --apply
python pipeline/review/curation_queue.py --dataset mechanistic
python pipeline/review/curation_queue.py --dataset disorder

# optional: retry failed/no-url PDF downloads
python pipeline/ingest/retry_pdf_downloads.py --dataset mechanistic
python pipeline/ingest/retry_pdf_downloads.py --dataset disorder

# optional: import manual PDFs from a local folder
python pipeline/ingest/import_manual_pdfs.py --dataset mechanistic --source-dir /absolute/path/to/manual_pdfs --apply
python pipeline/ingest/import_manual_pdfs.py --dataset disorder --source-dir /absolute/path/to/manual_pdfs --apply

# 8) promote
python pipeline/extract/promote_ready_stubs.py --dataset mechanistic --apply
python pipeline/extract/promote_ready_stubs.py --dataset disorder --apply

# 9) validate + export
python pipeline/validate/validate_claims.py
python pipeline/publish/export_orkg_payload.py
```

## Governance

- Evidence/provenance policy: `docs/evidence_policy.md`
- ORKG mapping notes: `docs/orkg_mapping.md`
- Pipeline stage docs: `pipeline/README.md`
