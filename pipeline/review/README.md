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

Triage is recall-safe by default:
- Benchmark-manifest and curated-claim DOI contexts are protected so known
  relevant papers do not silently fall out of the PDF queue.
- When discovery context is stale, triage can synthesize a new context from
  title/abstract matches against allowed compounds and targets/disorders.
- The report records `screening_status`, `triage_rescue_reasons`,
  `synthesized_context_count`, and `protected_context_count`.
- Disable these safeguards only for audits:
  `--no-protected-rescue` or `--no-synthesize-contexts`.

For disorder workflows, overlapping labels are normalized downstream during
stub creation/promotion so graph nodes stay canonical
(`End-of-life anxiety` -> `distress associated with life-threatening disease`).
Canonical alias rules live in `schema/disorder_canonicalization.json`.

Download PDFs only for triaged-relevant papers:
`python pipeline/ingest/sync_paper_library.py --dataset mechanistic --doi-file data/raw/doi_queue.mechanistic.triage_relevant.txt`

## Abstract-first autofill (claim fields)
Use paper title/abstract metadata to populate missing stub fields for all
triaged stubs before PDF extraction.

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
- clean disorder rows can be marked `ready_for_promotion` from abstracts alone
- mechanistic rows usually remain blocked until quantitative affinity fields
  are extracted from full text

## Mechanistic full-PDF autofill (affinity fields)
Use local mechanistic PDFs to extract affinity evidence and fill schema-critical
fields (`affinity_value`, `affinity_unit`, and often `affinity_type`).

### PDF extraction environment
PDF-heavy review scripts automatically re-run themselves inside the conda
environment `psychkg-pdf` when it exists, so commands can be run normally from
the repo root without manually activating the environment first.

One-time setup:
```bash
conda create -n psychkg-pdf python=3.12 -y
conda activate psychkg-pdf

python -m pip install --upgrade pip setuptools wheel

brew install poppler tesseract tesseract-lang qpdf ghostscript ocrmypdf

python -m pip install \
  pypdf \
  pdfplumber \
  pymupdf \
  pdfminer.six \
  pytesseract \
  pdf2image \
  pillow \
  pandas \
  "markitdown[all]" \
  docling
```

Verification:
```bash
for tool in pdftotext pdftoppm tesseract qpdf ocrmypdf gs; do
  command -v "$tool" || echo "missing: $tool"
done

conda run -n psychkg-pdf python -c "import pypdf, pdfplumber, fitz, pytesseract, pandas; from markitdown import MarkItDown; from docling.document_converter import DocumentConverter; print('PDF stack OK')"
```

Runtime controls:
- Use a different conda env name:
  `PSYCHKG_PDF_CONDA_ENV=my-env python pipeline/review/autofill_mechanistic_from_pdfs.py ...`
- Disable auto-bootstrap:
  `PSYCHKG_DISABLE_PDF_ENV_BOOTSTRAP=1 python pipeline/review/autofill_mechanistic_from_pdfs.py ...`

Dry run:
`python pipeline/review/autofill_mechanistic_from_pdfs.py --dataset mechanistic --mark-ready`

Apply updates:
`python pipeline/review/autofill_mechanistic_from_pdfs.py --dataset mechanistic --mark-ready --apply`

Notes:
- This step is intended for mechanistic rows that stay blocked after abstract
  autofill.
- It only uses locally available PDFs (from `sync_paper_library.py` output).
- It performs multi-pass extraction (typed patterns + table/header-aware parsing).
- Current text extraction aggregates multiple local readers: Poppler
  `pdftotext -layout`, `pdfplumber` text/table extraction, PyMuPDF, `pypdf`,
  and internal PDF stream decoding (literal + hex text extraction).
- For scanned/image PDFs, OCR fallback (`pdftoppm` + `tesseract`) is used when
  extraction text is sparse; disable with `--disable-ocr-fallback`.
- The `psychkg-pdf` environment also installs MarkItDown, Docling, and OCRmyPDF.
  These are available for later conversion/cache upgrades, but the current
  mechanistic extractor focuses on local text/table readers.
- Tighten/loosen extraction confidence with `--min-score` (default `6`).

## Disorder full-PDF autofill (outcome + provenance fields)
Use local disorder PDFs to upgrade abstract-only rows to full-text evidence and
populate missing outcome/provenance fields. This is an upgrade/rescue pass after
abstract extraction, not the only source of disorder claims.

The disorder PDF extractor uses the same local reader stack as the mechanistic
extractor for text/table recovery. Paper type is inferred from title-level
source signals plus clinical-result language so incidental PDF words such as
supplementary material or study-design headings do not by themselves demote a
primary clinical trial.

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
