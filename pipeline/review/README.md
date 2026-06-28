# Review

This stage runs table-native pre-screening and paper routing after metadata
enrichment. It also contains older abstract-screening and stub-curation helpers
for maintaining or auditing the first-generation graph.

## Table-native deterministic pre-screen

The current corpus-first path reads the unified Parquet corpus tables and writes
screening decisions back as Parquet tables. It does not edit candidate papers,
delete older decisions, or create DOI queues.

Run:

```bash
python pipeline/review/run_deterministic_prescreen.py \
  --run-id deterministic_prescreen_2026_05_28
```

Outputs:
- `data/processed/corpus/paper_prescreen_decisions.parquet`
- `data/processed/corpus/paper_prescreen_summary.parquet`

The decision table has one row per DOI and dataset. Missing-abstract records are
excluded by default. Existing downstream claim or extraction provenance is not
used by this prescreen step.

For small updates, such as newly added papers or metadata fixes, update only the
affected DOIs instead of rerunning the whole corpus:

```bash
python pipeline/review/run_deterministic_prescreen.py \
  --doi-file /tmp/changed_dois.txt
```

Scoped updates require an existing decisions table. The script recomputes only
the requested DOIs, adds new DOI/dataset rows when they are not already present,
replaces existing rows for changed DOIs, and rebuilds the summary from the
merged table. If `--run-id` is omitted, the scoped update reuses the existing
decisions table's run ID.

## Gemini Screening, Domain Routing, and Paper-Type Routing

Scope, domain, and paper type for extraction should be model-assigned from
title/abstract metadata in one Gemini routing step. Do not use pre-screen
keyword tags as the production domain router; they are high-recall
discovery/screening signals, not reliable extraction routes.

`pipeline/review/run_domain_routing.py` is retained only as a disposable
baseline for audits while the Gemini domain-routing table is built.

## Older Local LLM abstract screening

This path is retained for audit and comparison. It is not the current
extraction gate. The older strategy was a high-recall cascade:

1. A deterministic pre-screen skips only obvious no-signal rows.
2. All retained rows go to the main local Ollama model (`qwen3:14b`) for
   title/abstract relevance and quote-supported compound/entity contexts only.

Abstract screening deliberately does not assign source family, paper type, study
design, evidence strength, claim-extraction hints, or download priority. Those
labels require more context and are handled during full-text evidence assessment, or
during the abstract-only evidence fallback when full text remains unavailable.
Operationally, treat this later stage as **full-text evidence assessment and
data extraction**. Reserve `adjudication` for final conflict resolution between
rules, model output, and curator review; some script names still use the older
term for compatibility.

The abstract-screening stage is non-destructive: it writes reports and queues,
but does not edit the paper library or claim stubs.

Recommended small validation run:
`python pipeline/review/run_local_llm_abstract_screening.py --dataset disorder --deterministic-prescreen --deterministic-prescreen-only --limit 25 --only-with-abstract`

For batch-specific screening, add `--prescreen-output-label <run_label>` so the
deterministic pre-screen writes label-suffixed reports and queues instead of
overwriting the global `deterministic_prescreen_report_<dataset>.*` files. The
label should describe the run, not the method. For example:

`python pipeline/review/run_local_llm_abstract_screening.py --dataset mechanistic --doi-file data/raw/search_strategies/search_2026_05/grouped_module_run/combined/mechanistic_new_dois.txt --deterministic-prescreen --deterministic-prescreen-only --only-with-abstract --prescreen-output-label grouped_search_2026_05`

Recommended full run for one dataset:

1. `python pipeline/review/run_local_llm_abstract_screening.py --dataset disorder --deterministic-prescreen --deterministic-prescreen-only --only-with-abstract --only-undownloaded`
2. `python pipeline/review/run_local_llm_abstract_screening.py --dataset disorder --doi-file data/raw/doi_queue.disorder.deterministic_prescreen_retained.txt --model qwen3:14b --only-with-abstract --continue-on-error --timeout-sec 0 --resume-from-checkpoint --num-ctx 4096`

Use `--dataset mechanistic` for the mechanistic library. Run datasets separately
when monitoring long local-model runs.

During multi-day local-model runs, periodically materialize the checkpoint into
the normal report and DOI queues without calling Ollama:
`python pipeline/review/run_local_llm_abstract_screening.py --dataset disorder --doi-file data/raw/doi_queue.disorder.deterministic_prescreen_retained.txt --materialize-checkpoint-only --only-with-abstract`

Outputs:
- `data/processed/deterministic_prescreen_report_<dataset>.json`
- `data/processed/deterministic_prescreen_report_<dataset>.csv`
- `data/raw/doi_queue.<dataset>.deterministic_prescreen_retained.txt`
- `data/raw/doi_queue.<dataset>.deterministic_prescreen_excluded.txt`
- `data/processed/llm_abstract_screening_report_<dataset>.json`
- `data/processed/llm_abstract_screening_report_<dataset>.csv`
- `data/raw/doi_queue.<dataset>.llm_fulltext_candidates.txt`
- `data/raw/doi_queue.<dataset>.llm_relevant.txt`
- `data/raw/doi_queue.<dataset>.llm_uncertain.txt`

Queue meaning:
- `llm_fulltext_candidates` is the high-recall DOI-level queue for PDF download.
- `llm_relevant` contains only verified compound/entity contexts with exact
  title/abstract quote support. The extraction-prep stage should still decide
  the DOI-level extraction cohort.
- `llm_uncertain` keeps plausible papers that need full text before excluding.

The report replaces the old rule-based triage as the default screening output.
Old heuristic triage fields are blank unless you explicitly opt in with
`--use-heuristic-audit` or `--triage-report-json`; they are never shown to the
model prompt.

For relevant/uncertain papers with no available full text after acquisition
attempts, use the full-text evidence-assessment script in abstract-only mode:
`python pipeline/fulltext/run_local_llm_evidence_assessment.py --input data/processed/llm_abstract_screening_report_disorder.json --evidence-mode abstract_only --only-without-fulltext --only-with-abstract --model qwen3:14b --continue-on-error --timeout-sec 0`

This fallback consumes verified contexts from the abstract-screening report,
uses the same evidence-assessment schema, and marks outputs with
`evidence_mode=abstract_only`.

Deterministic pre-screen behavior:
- Enabled with `--deterministic-prescreen`.
- Marks skipped rows with `screening_path=deterministic_excluded`.
- Skips rows whose title/abstract has no in-scope compound/intervention term.
- In-scope compound/intervention detection combines the hardcoded synonym map,
  broad class terms, and `validation.allowed_compounds` from
  `pipeline/config.example.yaml`, so the pre-screen protects the broader
  configured compound universe.
- Ambiguous bare acronyms such as `DMT`, `MDA`, `DOI`, `DOET`, and `TMA`, plus
  bare `dissociative`, require additional chemical/class language in the title
  or abstract before they block deterministic exclusion.
- Escalates rows whose title/abstract mentions psychedelics, ketamine,
  entactogens, or another configured in-scope compound.
- Discovery/provenance contexts are not used as safety hints for deterministic
  exclusion.
- If `--use-heuristic-audit` is enabled, old heuristic retention also blocks
  deterministic exclusion, but this is an opt-in older behavior.
- This gate was calibrated against the existing `qwen3:14b` disorder checkpoint
  before use; any future tightening should be re-audited against checkpointed
  LLM decisions.

Do not use `--fast-screen-model qwen3:4b` as a universal pre-screen for now. In
testing, structured `qwen3:4b` calls were too slow to justify an extra model call
before `qwen3:14b`. The deterministic pre-screen is the preferred speedup.

## Optional rule-based paper triage (older path)
Use rule-based triage to pre-label papers as likely relevant/irrelevant and
suggest `source_type` (e.g., `review`, `meta_analysis`, `primary_study`).

This rule-based triage is no longer part of the default workflow. Use it only
for older graph maintenance or targeted comparisons. PDF acquisition should use the
`llm_fulltext_candidates` queue.

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

Triage is retrieval-safe by default:
- Known-study and curated-claim DOI contexts are protected so known
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

Older triage PDF queue:
`python pipeline/ingest/sync_paper_library.py --dataset mechanistic --doi-file data/raw/doi_queue.mechanistic.triage_relevant.txt`

## Older abstract-first autofill (claim fields)
Use paper title/abstract metadata to populate missing stub fields for all
screened stubs before PDF extraction.

Dry run:
`python pipeline/review/autofill_stubs_from_abstracts.py --dataset disorder --mark-ready`

Apply updates:
`python pipeline/review/autofill_stubs_from_abstracts.py --dataset disorder --mark-ready --apply`

What it fills (when possible):
- provenance for abstract-first workflow (`access_level=abstract_only`,
  `evidence_location=abstract`, `evidence_locator=Abstract`)
- missing metadata (`study_title`, `authors`, `study_year`, journal/type/date,
  ISSNs, publisher, trial registry IDs, MeSH/keywords, funders/grants,
  publication relations, language, Semantic Scholar ID)
- disorder claim hints (e.g., `outcome_type`, `study_design`, `system`,
  `evidence_level`)
- clean disorder rows can be marked `ready_for_promotion` from abstracts alone
- mechanistic rows usually remain blocked until quantitative affinity fields
  are extracted from full text

## Older mechanistic full-PDF autofill (affinity fields)
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
  pyarrow \
  "markitdown[all]" \
  docling
```

Verification:
```bash
for tool in pdftotext pdftoppm tesseract qpdf ocrmypdf gs; do
  command -v "$tool" || echo "missing: $tool"
done

conda run -n psychkg-pdf python -c "import pypdf, pdfplumber, fitz, pytesseract, pandas, pyarrow; from markitdown import MarkItDown; from docling.document_converter import DocumentConverter; print('PDF stack OK')"
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

## Older disorder full-PDF autofill (outcome + provenance fields)
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

## Older stub queue report
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
