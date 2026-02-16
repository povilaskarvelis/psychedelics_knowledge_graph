# Pipeline

Deterministic ETL for building the KG.

## Stages
1. Ingest: gather papers (manual or API export)
2. Extract: create structured claims in CSV/JSON
3. Validate: schema checks + field normalization
4. Publish: push contributions to ORKG

## Taxonomy config
- Disorder canonicalization aliases are configured in:
  `schema/disorder_canonicalization.json`
- Update this file to merge/split overlapping disorder labels without changing
  pipeline code.

## Ingest from DOI queue
- Discover literature first (default Semantic Scholar):
  `python pipeline/ingest/discover_literature.py --dataset mechanistic`
- Use provider options:
  `--provider semantic_scholar` (default), `--provider openalex`, `--provider hybrid`
- Generate mechanistic stubs:
  `python pipeline/ingest/seed_from_dois.py --dataset mechanistic --doi-file data/raw/doi_queue.mechanistic.template.txt --replace`
- Generate disorder stubs:
  `python pipeline/ingest/seed_from_dois.py --dataset disorder --doi-file data/raw/doi_queue.disorder.template.txt --replace`
- From discovered queues:
  `data/raw/doi_queue.mechanistic.discovered.txt`, `data/raw/doi_queue.disorder.discovered.txt`
- Ingest docs:
  `pipeline/ingest/README.md`
- Sync paper library (abstracts + OA + PDF download status):
  `python pipeline/ingest/sync_paper_library.py --dataset mechanistic --skip-download`
  `python pipeline/ingest/sync_paper_library.py --dataset disorder --skip-download`
- Generate triage queue before download:
  `python pipeline/review/triage_paper_library.py --dataset mechanistic`
  `python pipeline/review/triage_paper_library.py --dataset disorder`
- Filtered triage queues include only matched `(compound, entity)` contexts to
  prevent DOI-level cross-mapping noise.
- Download only triaged-relevant rows:
  `python pipeline/ingest/sync_paper_library.py --dataset mechanistic --doi-file data/raw/doi_queue.mechanistic.triage_relevant.txt`
  `python pipeline/ingest/sync_paper_library.py --dataset disorder --doi-file data/raw/doi_queue.disorder.triage_relevant.txt`
- Extensive run helper (discovery + triage-first sync):
  `python pipeline/ingest/run_extensive_search.py --dataset all --provider hybrid --max-results-per-seed 100 --max-results 600`
- High-recall seed expansion run:
  `python pipeline/ingest/run_extensive_search.py --dataset all --provider hybrid --expand-seeds-from-config --auto-template-mode broad --auto-max-pairs 1200 --auto-max-seeds 3000 --max-results-per-seed 120 --max-results 5000`
- Recommended staged strategy (faster + reproducible):
  see `pipeline/ingest/README.md` section "Recommended principled search strategy"
- Recall benchmark audit:
  `python pipeline/ingest/recall_audit.py --dataset mechanistic --known-doi-file data/raw/benchmark_known_dois.mechanistic.txt`
  `python pipeline/ingest/recall_audit.py --dataset disorder --known-doi-file data/raw/benchmark_known_dois.disorder.txt`
- Retry failed/no-URL downloads:
  `python pipeline/ingest/retry_pdf_downloads.py --dataset mechanistic`
  `python pipeline/ingest/retry_pdf_downloads.py --dataset disorder`
- Import manual PDFs into paper DB:
  `python pipeline/ingest/import_manual_pdfs.py --dataset mechanistic --source-dir /absolute/path/to/manual_pdfs --apply`
  `python pipeline/ingest/import_manual_pdfs.py --dataset disorder --source-dir /absolute/path/to/manual_pdfs --apply`
- Ingest outputs:
  `data/raw/doi_queue.<dataset>.discovered.txt`
  `data/raw/doi_queue.<dataset>.triage_relevant.txt`
  `data/raw/doi_queue.<dataset>.retry_pdf.txt`
  `data/processed/discovery_report_<dataset>.json`
  `data/processed/paper_library_<dataset>.json`
  `data/processed/paper_library_<dataset>.csv`
  `data/processed/paper_inventory_<dataset>.json`
  `data/processed/paper_inventory_<dataset>.md`
  `data/processed/manual_pdf_import_report_<dataset>.json`
  `data/raw/papers/<dataset>/pdfs/`

## Promote curated-ready stubs
- Mechanistic dry run:
  `python pipeline/extract/promote_ready_stubs.py --dataset mechanistic`
- Disorder dry run:
  `python pipeline/extract/promote_ready_stubs.py --dataset disorder`
- Disorder promotion canonicalizes overlapping labels to reduce graph
  duplication (for example `End-of-life anxiety` is merged into
  `distress associated with life-threatening disease`)
- Promotion also prunes existing curated rows marked `likely_irrelevant` in the
  latest triage report (same DOI+compound+entity context).
- It also prunes existing curated rows for DOI-contexts that are missing from
  triage matched `contexts` (even if the DOI itself is relevant), which removes
  stale cross-mapped disorder/target edges from earlier runs.
- Apply writes:
  add `--apply` after confirming dry run has zero errors
- Extract docs:
  `pipeline/extract/README.md`
- Promotion outputs:
  `data/processed/promotion_report_<dataset>.json`
  `data/curated/claims.json`, `data/curated/claims.csv`
  `data/curated/disorder_claims.json`, `data/curated/disorder_claims.csv`

## Review queue
- Paper triage before queue review:
  `python pipeline/review/triage_paper_library.py --dataset mechanistic`
  `python pipeline/review/triage_paper_library.py --dataset disorder`
- Apply triage to stubs:
  add `--apply-to-stubs`
- Mechanistic queue report:
  `python pipeline/review/curation_queue.py --dataset mechanistic`
- Disorder queue report:
  `python pipeline/review/curation_queue.py --dataset disorder`
- Autofill stubs from curated matches:
  `python pipeline/review/autofill_stubs_from_curated.py --dataset mechanistic --mark-ready --apply`
- Full-PDF mechanistic autofill (affinity fields):
  `python pipeline/review/autofill_mechanistic_from_pdfs.py --dataset mechanistic --mark-ready --apply`
- Full-PDF disorder autofill (outcome/provenance fields):
  `python pipeline/review/autofill_disorder_from_pdfs.py --dataset disorder --mark-ready --apply`
- Mark clean rows ready:
  add `--mark-ready --apply`
- Review docs:
  `pipeline/review/README.md`
- Review outputs:
  `data/processed/triage_report_mechanistic.json`
  `data/processed/triage_report_disorder.json`
  `data/processed/review_queue_mechanistic.json`
  `data/processed/review_queue_disorder.json`
  `data/processed/pdf_autofill_report_mechanistic.json`
  `data/processed/pdf_autofill_report_disorder.json`
  `data/processed/autofill_report_mechanistic.json`
  `data/processed/autofill_report_disorder.json`

## Author backfill
- Backfill `authors` in curated datasets from DOI lookup:
  `python pipeline/enrich/backfill_authors_from_lookup.py --apply`
- Lookup file:
  `data/raw/doi_authors_lookup.json`

## Publish-prep export
- Export ORKG payload files:
  `python pipeline/publish/export_orkg_payload.py`
- Export one dataset:
  add `--dataset mechanistic` or `--dataset disorder`
- Export outputs:
  `data/processed/orkg_payload_mechanistic.json` (all evidence)
  `data/processed/orkg_payload_mechanistic_primary_only.json`
  `data/processed/orkg_payload_disorder.json` (all evidence)
  `data/processed/orkg_payload_disorder_primary_only.json`
  `data/processed/orkg_payload_manifest.json`
- Publish docs:
  `pipeline/publish/README.md`

## Inputs
- `data/curated/claims.csv`
- `data/curated/claims.json`
- `data/curated/disorder_claims.csv`
- `data/curated/disorder_claims.json`

## Outputs
- `data/processed/claims.normalized.json`
- `data/processed/disorder_claims.normalized.json`
- ORKG contributions (public)

## Minimum claim metadata
- Provenance fields are mandatory for both datasets:
  `source_type`, `access_level`, `evidence_location`, `evidence_locator`,
  `study_design` (see `docs/evidence_policy.md`).

## Validator
- Run strict validation and write a quality report:
  `python pipeline/validate/validate_claims.py`
- Report output:
  `data/processed/validation_report.json`
