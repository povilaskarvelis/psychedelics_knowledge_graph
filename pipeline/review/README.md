# Review: Stub Curation Queue

Use this step to inspect pending stubs, identify blocking fields, and batch
update `stub_status` before promotion.

## Paper triage (relevance + source type)
Use rule-based triage to pre-label papers as likely relevant/irrelevant and
suggest `source_type` (e.g., `review`, `meta_analysis`, `primary_study`).

Dry run report from paper library:
`python pipeline/review/triage_paper_library.py --dataset mechanistic`

Apply suggestions to stubs:
`python pipeline/review/triage_paper_library.py --dataset mechanistic --apply-to-stubs`

When applied:
- likely irrelevant papers get `stub_status=excluded_not_relevant` (default)
- `source_type` can be updated from `primary_study` to `review`/`meta_analysis`

Triage also writes a filtered DOI queue (default):
- `data/raw/doi_queue.<dataset>.triage_relevant.txt`
- Includes `likely_relevant` and `possible_relevant` rows by default.
- Queue rows are emitted only when triage finds a matched `(compound, entity)`
  context in title/abstract text.
- The JSON report keeps both:
  - `contexts`: matched contexts used for downstream queue/stub mapping.
  - `contexts_all`: all original discovery contexts for traceability.

For disorder workflows, overlapping labels are normalized downstream during
stub creation/promotion so graph nodes stay canonical
(`End-of-life anxiety` -> `distress associated with life-threatening disease`).
Canonical alias rules live in `schema/disorder_canonicalization.json`.

Download PDFs only for triaged-relevant papers:
`python pipeline/ingest/sync_paper_library.py --dataset mechanistic --doi-file data/raw/doi_queue.mechanistic.triage_relevant.txt`

## Abstract-first autofill (claim fields)
Use paper title/abstract metadata to populate missing stub fields.

Dry run:
`python pipeline/review/autofill_stubs_from_abstracts.py --dataset disorder --mark-ready`

Apply updates:
`python pipeline/review/autofill_stubs_from_abstracts.py --dataset disorder --mark-ready --apply`

What it fills (when possible):
- provenance for abstract-first workflow (`access_level=abstract_only`,
  `evidence_location=abstract`, `evidence_locator=Abstract`)
- missing metadata (`study_title`, `authors`, `study_year`)
- disorder claim hints (e.g., `outcome_type`, `study_design`, `system`,
  `evidence_level`)

## Mechanistic full-PDF autofill (affinity fields)
Use local mechanistic PDFs to extract affinity evidence and fill schema-critical
fields (`affinity_value`, `affinity_unit`, and often `affinity_type`).

Dry run:
`python pipeline/review/autofill_mechanistic_from_pdfs.py --dataset mechanistic --mark-ready`

Apply updates:
`python pipeline/review/autofill_mechanistic_from_pdfs.py --dataset mechanistic --mark-ready --apply`

Notes:
- This step is intended for mechanistic rows that stay blocked after abstract
  autofill.
- It only uses locally available PDFs (from `sync_paper_library.py` output).
- It performs multi-pass extraction (typed patterns + table/header-aware parsing).
- If `pypdf` is not installed, it falls back to internal PDF stream decoding
  (literal + hex text extraction).
- For scanned/image PDFs, OCR fallback (`pdftoppm` + `tesseract`) is used when
  extraction text is sparse; disable with `--disable-ocr-fallback`.
- Tighten/loosen extraction confidence with `--min-score` (default `6`).

## Disorder full-PDF autofill (outcome + provenance fields)
Use local disorder PDFs to upgrade abstract-only rows to full-text evidence and
populate missing outcome/provenance fields.

Dry run:
`python pipeline/review/autofill_disorder_from_pdfs.py --dataset disorder --mark-ready`

Apply updates:
`python pipeline/review/autofill_disorder_from_pdfs.py --dataset disorder --mark-ready --apply`

## Author backfill (API fallback)
Use this when rows are still blocked only by missing `authors`.

Dry run:
`python pipeline/review/backfill_stub_authors.py --dataset disorder --mark-ready`

Apply updates:
`python pipeline/review/backfill_stub_authors.py --dataset disorder --mark-ready --apply`

Fallback mode (forces unresolved rows to `authors=Unknown`):
`python pipeline/review/backfill_stub_authors.py --dataset disorder --mark-ready --fallback-unknown --apply`

Optional cleanup for already-downloaded irrelevant PDFs:
- Dry run:
  `python pipeline/review/cleanup_irrelevant_pdfs.py --dataset mechanistic`
- Apply (moves files to archive by default):
  `python pipeline/review/cleanup_irrelevant_pdfs.py --dataset mechanistic --apply`

## Dry run queue report
Mechanistic:
`python pipeline/review/curation_queue.py --dataset mechanistic`

Disorder:
`python pipeline/review/curation_queue.py --dataset disorder`

Include all statuses:
`python pipeline/review/curation_queue.py --dataset mechanistic --all-statuses`

## Status updates
Mark clean rows as ready for promotion:
`python pipeline/review/curation_queue.py --dataset mechanistic --mark-ready --apply`

Set explicit status for row indices:
`python pipeline/review/curation_queue.py --dataset mechanistic --set-status blocked_needs_fulltext --row-indices 2,5 --apply`

Autofill missing fields from curated matches and mark ready:
`python pipeline/review/autofill_stubs_from_curated.py --dataset mechanistic --mark-ready --apply`

## Output
- `data/processed/triage_report_mechanistic.json`
- `data/processed/triage_report_mechanistic.csv`
- `data/processed/triage_report_disorder.json`
- `data/processed/triage_report_disorder.csv`
- `data/raw/doi_queue.mechanistic.triage_relevant.txt`
- `data/raw/doi_queue.disorder.triage_relevant.txt`
- `data/processed/abstract_autofill_report_mechanistic.json`
- `data/processed/abstract_autofill_report_disorder.json`
- `data/processed/pdf_autofill_report_mechanistic.json`
- `data/processed/pdf_autofill_report_disorder.json`
- `data/processed/authors_backfill_report_mechanistic.json`
- `data/processed/authors_backfill_report_disorder.json`
- `data/processed/pdf_cleanup_report_mechanistic.json`
- `data/processed/pdf_cleanup_report_disorder.json`
- `data/processed/review_queue_mechanistic.json`
- `data/processed/review_queue_disorder.json`
- `data/processed/autofill_report_mechanistic.json`
- `data/processed/autofill_report_disorder.json`

## Notes
- `stub_index` is 1-based and maps to row position in `*_claim_stubs.json`.
- Dry run is default; no files are modified unless `--apply` is passed.
- `excluded_not_relevant` rows are intentionally filtered out by default because
  queue scan defaults to `--status pending_curation`.
