# Full-Text Conversion

This stage converts locally available PDFs into structured full-text artifacts
that downstream extraction and provenance checks can reuse.

The first goal is provenance repair: rows marked `full_text_seen` should point
to durable paper locations such as sections, tables, figures, pages, or TEI
elements rather than stale abstract snippets.

## PDF Retrieval

Use the table-native retrieval runner for retained papers that still need local
PDFs:

```bash
python pipeline/fulltext/run_pdf_retrieval_pipeline.py \
  --alternate-pdf-sources pmc,openalex,semantic_scholar \
  --progress-every 25 \
  --write-every 25
```

The runner first downloads probable PDF endpoints from the routed corpus, then
optionally queries alternate open-access sources for rows that still fail, and
runs the standard repository-source pass for OSF/PsyArXiv, Figshare-style
records, and known repository redirects into Figshare (for example Sussex SRO
handles). It validates both PDF bytes and document identity before saving:
the expected title must match the bounded top region of page one. A title that
appears later on page one or elsewhere in the document is not sufficient,
because proceedings and supplement PDFs can contain many valid paper titles.
The only exception is an explicit DOI-plus-SHA-256 decision in
`source_identity_pdf_hash_registry.json`; that decision applies only to the
reviewed byte-identical PDF. The runner updates
`candidate_papers.parquet`, rebuilds `paper_extraction_routes.parquet`, and
exports the remaining manual-download queue to
`data/processed/corpus/audits/manual_pdf_download_dois.csv/.txt`.

For lower-level retry runs, `download_routed_pdfs.py` can also query alternate
open-access sources before giving up on a DOI:

```bash
python pipeline/fulltext/download_routed_pdfs.py \
  --only-failure-categories forbidden,non_pdf_response,provider_error,timeout \
  --alternate-pdf-sources pmc,openalex,semantic_scholar \
  --progress-every 25
```

The alternate-source layer currently supports PMC ID conversion plus PMC viewer
PDF downloads, OpenAlex repository locations, and Semantic Scholar
`openAccessPdf` links. Successful files are written as ordinary local PDFs and
candidate rows keep the standard `downloaded` status; report records include
the alternate source that supplied the winning URL.

Use targeted repository recovery diagnostics when needed:

```bash
python pipeline/fulltext/recover_pdf_landing_pages.py \
  --standard-recovery-only \
  --categories forbidden,non_pdf_response,provider_error,timeout,other_download_failure,not_found
```

Broader host probing should stay as an explicit rescue pass rather than the
default retrieval path. Browser-only publisher flows such as SAGE reader
downloads or LWW "Download > PDF" menus are intentionally not part of the
unattended HTTP recovery stage unless a deterministic non-browser endpoint is
identified; keep those in the browser-manual workflow or a future supervised
browser helper.

The Akjournals landing-page pattern recovered enough PDFs to keep as a named
rescue preset. Run it only as an explicit post-direct cleanup:

```bash
python pipeline/fulltext/recover_pdf_landing_pages.py \
  --rescue-preset akjournals \
  --apply \
  --rebuild-routes-after
python pipeline/fulltext/export_manual_pdf_queue.py
python pipeline/fulltext/rank_manual_pdf_queue.py
```

## Browser Manual Recovery

For normal-browser click-through recovery, save browser downloads into:

```text
data/raw/papers/manual_pdf_inbox/
```

or into a temporary staging folder under that directory. Do not use the
browser's general `Downloads` folder for corpus recovery runs.

Use the browser as a short click-through ladder, not only as a direct PDF
viewer. From a DOI or landing page, first look for article-entry controls such
as "Article", "Full text", "View article", or "Read article"; after opening
that view, look again for "PDF", "Download PDF", "View PDF", or the browser PDF
viewer download control. Stop and record the page state when the visible page
says access is unavailable, login/subscription is required, or the paper must
be purchased. Do not save those HTML pages as PDF attempts.

Before importing manually saved files, triage the browser output:

```bash
python pipeline/fulltext/browser_download_triage.py \
  --download-dir data/raw/papers/manual_pdf_inbox \
  --quarantine-non-pdf \
  --apply
```

This keeps files whose bytes start with a PDF magic header and moves HTML or
other non-PDF saves into `data/raw/papers/manual_pdf_rejected_downloads/`.
HTML pages are classified as `no_access_or_paywalled`,
`cookie_or_interstitial_block`, or `html_saved_non_pdf` based on the visible
page text. Use these statuses in browser-recovery reports instead of repeatedly
retrying pages that visibly say "Get access", "Log in", or "you do not have
access".

After triage, import valid PDFs through the canonical inbox importer:

```bash
python pipeline/fulltext/import_manual_pdfs.py \
  --inbox-dir data/raw/papers/manual_pdf_inbox \
  --apply \
  --move
```

The importer does not trust the DOI-like filename by itself. It requires an
exact DOI in document-front evidence, a strong title match at the top of page
one, or an exact DOI-plus-SHA-256 registry decision. Ambiguous and conflicting
files stay out of the canonical PDF store.

When a curator has confirmed that an existing canonical PDF is the wrong file
for a DOI, rerun the importer with `--replace-existing`. The old canonical PDF
is moved to `data/raw/papers/pdf_conflicts/` and the candidate row is refreshed
with the replacement checksum.

After importing manual PDFs, rebuild routes and convert any newly local PDFs:

```bash
python pipeline/extract/build_extraction_routes.py
python pipeline/fulltext/run_local_pdf_conversion_pipeline.py --batch-size 25
```

Successful conversion writes canonical artifacts under
`data/processed/fulltext/articles/` and the final route rebuild moves those
papers from `needs_pdf_conversion` to `ready_for_article_text_extraction`.
Refresh manual queue outputs after route changes:

```bash
python pipeline/fulltext/export_manual_pdf_queue.py
python pipeline/fulltext/rank_manual_pdf_queue.py
```

If browser/manual review confirms that a DOI has no usable open article PDF,
record that durable decision in
`pipeline/fulltext/manual_fulltext_access_overrides.json` with
`manual_access_action=suppress_pdf_download`, then rebuild routes. If the record
is not an extractable article, such as a conference abstract, correction,
poster abstract, book review, or nonstandard source, record
`manual_action=context_only` in
`pipeline/extract/manual_extraction_route_overrides.json` instead.

## Source-Identity Audit

Audit the canonical article store without changing artifacts:

```bash
python pipeline/fulltext/audit_fulltext_source_identity.py --fail-on-unverified
```

The audit reads curated DOI relationships and parser-identifier overrides from
`pipeline/fulltext/source_identity_registry.json`. A registry entry is not an
unconditional alias: the recorded document DOI must be observed in the
artifact and the requested paper title must independently match the extracted
front-matter title (or occur as a normalized title phrase in front matter).
Token coverage elsewhere in the article is not sufficient. Exact artifact DOI
matches always take precedence over older registry relationships. Correction
relationships are accepted only when the requested record's own title says it
is a correction, corrigendum, or erratum; a main-article DOI whose artifact is
only the correction remains unverified. Uncurated metadata relations such as
`CommentOn` are reported as candidates but cannot verify an artifact.
Title-only verification is likewise limited to parsed header/front-matter
evidence; a target title found in the article body, references, or a neighbouring
conference contribution is not accepted. The audit also rechecks any PDF hash
attestation against the current file bytes.

This audit is part of the normal conversion path, not only a repair utility.
`run_local_pdf_conversion_pipeline.py` runs it before rebuilding extraction
routes and stops if any canonical artifact is unverified. Article-text packet
building also requires a fresh passing audit. It rejects an audit older than a
routed artifact, the DOI relationship registry, or the PDF hash-attestation
registry, and writes no packets when a routed artifact is absent from the
verified audit.

PMC/Europe PMC XML acquisition is DOI-selective as well. For JATS collections
containing multiple `<article>` or `<sub-article>` records, the fetcher requires
exactly one requested-DOI match and serializes only that node. Whole proceedings
containers and adjacent abstracts cannot be stored under an item DOI.

## Canonical Article Text Store

New full-text artifacts should be written to
`data/processed/fulltext/articles/`. This neutral directory replaces the old
`fulltext/disorder/` and `fulltext/mechanistic/` split for the route-table-based
pipeline. Existing artifacts can be copied into the canonical store without
re-extracting PDFs:

```bash
python pipeline/fulltext/consolidate_fulltext_artifacts.py
```

The consolidation keeps one best artifact per DOI, preferring the artifact with
the largest successful text extraction, but an artifact without verified
source identity is never copied into the canonical store. The old directories are migration
sources for this explicit consolidation command only; route building reads
converted article text only from `fulltext/articles/`.

Convert local PDFs that are currently routed as
`convert_local_pdf_then_extract`:

```bash
python pipeline/fulltext/convert_routed_local_pdfs.py \
  --backend grobid
```

The converter reads `paper_extraction_routes.parquet`, writes artifacts into
`fulltext/articles/`, and rebuilds the route table after successful conversion.
For larger conversion backlogs, use the managed local-PDF runner. It still calls
the same converter, but writes batch reports and can restart GROBID between
batches:

```bash
python pipeline/fulltext/run_local_pdf_conversion_pipeline.py \
  --batch-size 25
```

## Stage Runner

Run the full non-destructive maintenance stage:

```bash
python pipeline/fulltext/run_fulltext_provenance.py \
  --dataset all \
  --backend grobid \
  --limit 0 \
  --include-existing-artifacts
```

This performs three steps for each dataset:

1. Convert PDFs for stale `full_text_seen` abstract locators.
2. Rebuild `provenance_repair_report_<dataset>.json/.csv`.
3. Rebuild `evidence_triage_report_<dataset>.json/.csv`.
4. Export a blank `provenance_review_<dataset>.csv` for curator decisions.

With `--backend grobid`, the runner uses managed GROBID mode by default:

1. It builds a DOI queue for PDFs that do not already have a successful GROBID extraction.
2. It starts GROBID with the memory-safe Docker config from `start_grobid.py`.
3. It processes the queue in batches, restarting GROBID before each batch.
4. It runs the repair report only after conversion finishes.

The default batch size is 50. The client also retries transient GROBID failures
twice with a 5-second wait, and disables header/citation consolidation by
default for reproducible local parsing. Override these only if needed:

```bash
python pipeline/fulltext/run_fulltext_provenance.py \
  --dataset all \
  --backend grobid \
  --limit 0 \
  --include-existing-artifacts \
  --grobid-batch-size 25 \
  --grobid-retries 3 \
  --grobid-retry-wait-sec 10
```

Use `--grobid-batch-size 0` to disable managed batching and return to the old
single conversion call.

Preview the commands without running conversion:

```bash
python pipeline/fulltext/run_fulltext_provenance.py --dataset all --limit 50 --plan-only
```

Use per-dataset limits when clinical and mechanistic backlogs differ:

```bash
python pipeline/fulltext/run_fulltext_provenance.py \
  --dataset all \
  --disorder-limit 100 \
  --mechanistic-limit 0
```

The runner never applies curated-claim edits. Applying accepted repairs remains
a separate explicit step through `apply_provenance_repairs.py --apply`.

## Backends

- `grobid`: primary scholarly-article parser backed by a local GROBID service;
  preserves TEI XML with article sections, references, tables, and figure
  locators for downstream article text inputs.
- `docling`: fallback document conversion backend when the `docling` Python
  package is installed, especially for non-article PDFs or GROBID failures.
- `pdftotext`: lightweight plain-text converter using Poppler when explicitly
  requested for diagnostics or local inspection.

`auto` uses GROBID only. Use `all` for a comparison run across every configured
backend. Managed batching is currently only enabled for explicit
`--backend grobid` runs.

## Example

```bash
python pipeline/fulltext/convert_pdfs.py --dataset disorder --backend grobid --limit 25
```

## PMC XML Recovery

Some retained papers have reusable PMC full-text XML even when no local PDF has
been downloaded. Retrieve those XML records before finalizing abstract-only
routes:

```bash
python pipeline/fulltext/fetch_pmc_fulltext_xml.py \
  --progress-every 25 \
  --rps 1.5
```

By default, the script targets retained routed papers with a PMCID and skips
papers that already have a converted full-text artifact or a valid local PDF.
It tries the Europe PMC XML endpoint first and falls back to PMC OAI/JATS. Each
successful XML record is written to `data/processed/fulltext/articles/` with
the same artifact shape as PDF conversion, including section summaries and raw
XML for article text input building. After successful writes, the script
rebuilds `paper_extraction_routes.parquet` so those papers move to
`full_text_available` and are no longer treated as PDF-download candidates.

Target rows where the curated claim says `full_text_seen` but still points to an
abstract snippet:

```bash
python pipeline/fulltext/convert_pdfs.py --dataset disorder --stale-fulltext-locators --limit 25
```

Restrict to a hand-picked DOI queue:

```bash
python pipeline/fulltext/convert_pdfs.py --dataset mechanistic --doi-file data/raw/my_doi_list.txt
```

To include a local GROBID service:

```bash
python pipeline/fulltext/run_fulltext_provenance.py \
  --dataset disorder \
  --backend grobid \
  --limit 0 \
  --include-existing-artifacts
```

Outputs:

- `data/processed/fulltext/<dataset>/*.json`
- `data/processed/fulltext/fulltext_report_<dataset>.json`

These artifacts are intentionally separate from curated claims. No claim rows
are modified by this stage.

## Article Text Inputs For Extraction

After PDF conversion, build JSONL article text inputs from the route table and
the canonical `fulltext/articles/` artifacts:

```bash
python pipeline/fulltext/build_article_text_inputs.py
```

Outputs:

- `data/processed/extraction/fulltext_packets.jsonl`
- `data/processed/extraction/article_text_inputs_report.json`
- `data/processed/extraction/article_text_inputs_audit.csv`
- `data/processed/extraction/article_text_inputs_audit.md`

Each JSONL record includes DOI-level metadata, source-type hints from
publication metadata, selected reconstructed TEI sections, tables, figures,
references, and stable `llm_chunks` with section/document offsets. The builder
uses raw extracted TEI, not truncated section snippets, so it is the preferred
input layer for model extraction.

Article text does not mean the whole paper. It means the text we choose to give
the model for an article-text extraction task. The default route-table policy is:

- `primary_study`: for primary studies. Keeps title/abstract metadata,
  methods/results-like sections, tables, and marker-matched domain evidence
  while dropping most introduction, discussion, conclusion, references, and
  secondary-review body text.
- `all_sections`: for meta-analyses, structured reviews, and narrative reviews.
  This is intentionally broad because the relevant details can appear outside
  standardized methods/results headings in secondary literature.

For compatibility, the JSON output still stores the corresponding internal
`packet_profile` values: `primary_empirical` for primary studies and `full` for
secondary literature.

The older builder CLI still exposes `--dataset` for compatibility with
pre-route migration inputs. Do not use that split-source mode for new
route-table extraction runs; use `build_article_text_inputs.py` and the
canonical `fulltext/articles/` store instead.

For a small route-table section-selection audit:

```bash
python pipeline/fulltext/audit_article_text_inputs.py \
  --per-strategy 3
```

`lean_primary` remains accepted as a deprecated compatibility alias, but new
commands should use `primary_study`.

## Provenance Repair Report

After conversion, build a review report for stale full-text locators:

```bash
python pipeline/fulltext/build_provenance_repair_report.py --dataset disorder
```

Outputs:

- `data/processed/fulltext/provenance_repair_report_<dataset>.json`
- `data/processed/fulltext/provenance_repair_report_<dataset>.csv`

This report proposes section-level locators for human review. It does not edit
curated claims.

## Accepted Repair Gate

Export an explicit review template from the proposed repair rows:

```bash
python pipeline/fulltext/apply_provenance_repairs.py \
  --dataset disorder \
  --export-review-csv data/processed/fulltext/provenance_review_disorder.csv
```

A curator should mark only approved rows in the `decision` column, using values
such as `accepted`, `yes`, or `true`. Blank, rejected, or deferred rows are
ignored.

Dry-run the accepted decisions before editing curated claims:

```bash
python pipeline/fulltext/apply_provenance_repairs.py \
  --dataset disorder \
  --accepted-review data/processed/fulltext/provenance_review_disorder.csv
```

Apply only after the dry-run report looks correct:

```bash
python pipeline/fulltext/apply_provenance_repairs.py \
  --dataset disorder \
  --accepted-review data/processed/fulltext/provenance_review_disorder.csv \
  --apply
```

The apply gate verifies that each accepted row still matches the current
curated claim before writing. This prevents stale repair reports from silently
overwriting newer curation work.

## Evidence Triage

Evidence triage is separate from locator repair. A row can legitimately have
`access_level=full_text_seen` while still being the wrong source type for a
primary-study claim, such as a review, protocol, commentary, erratum, conference
abstract, or case report.

The triage taxonomy separates source family from evidence strength:

- `original_empirical`: original data, including trials, observational studies,
  preclinical assays, case reports, and case series.
- `evidence_synthesis`: systematic reviews, meta-analyses, and narrative reviews.
- `opinion_or_commentary`: editorials, letters, perspectives, critiques.
- `protocol`: planned study/protocol without outcome results.
- `correction`: errata/corrigenda/retractions.
- `conference_abstract`: abstract-only meeting reports.

Case reports are therefore not treated as synthesis/commentary. They are
`original_empirical` with low evidence strength.

Build the deterministic triage report:

```bash
python pipeline/fulltext/build_evidence_triage_report.py --dataset disorder
```

By default this only triages `full_text_seen` rows, because absence of a
full-text artifact for `abstract_only` rows is not a triage failure. Use
`--scope artifacts` or `--scope all` only for broader audits.

Outputs:

- `data/processed/fulltext/evidence_triage_report_<dataset>.json`
- `data/processed/fulltext/evidence_triage_report_<dataset>.csv`

Rows marked `propose_source_reclassification` with
`automation_status=auto_apply_eligible` can be applied automatically through a
dry-run/apply gate:

```bash
python pipeline/fulltext/apply_evidence_triage.py --dataset disorder

python pipeline/fulltext/apply_evidence_triage.py --dataset disorder --apply
```

This does not demote `access_level`: if the full text was seen, it remains seen.
It updates source/evidence-type fields such as `source_type`, `paper_type`, and
`study_design`, preserving an audit note on the curated row.

## Evidence Triage QA Sample

After high-confidence triage proposals are applied, the remaining
`needs_targeted_qa` rows should not be reviewed exhaustively by hand. Export a
small stratified quality-check sample instead:

```bash
python pipeline/fulltext/export_evidence_triage_qa_sample.py --dataset all
```

Outputs:

- `data/processed/fulltext/evidence_triage_qa_sample.csv`
- `data/processed/fulltext/evidence_triage_qa_sample.json`

The sample includes:

- `targeted_rule_qa`: uncertain rows, stratified by predicted class.
- `auto_triage_audit`: already auto-triaged non-empirical rows, for false-positive checks.
- `primary_control`: rows kept as original empirical evidence, for false-negative checks.

The CSV has blank quality-check columns such as `correct_classification`,
`correct_primary_vs_non_primary`, and `review_notes`. Use this to estimate rule
accuracy and decide which deterministic rules can be safely tightened next.

## Local LLM Full-Text Evidence Assessment

Run a local Ollama model over the QA sample to get semantic source-type,
claim-support, locator, and variable-extraction proposals:

```bash
python pipeline/fulltext/run_local_llm_evidence_assessment.py \
  --model qwen3:14b \
  --limit 10
```

If the model is not installed yet:

```bash
ollama pull qwen3:14b
```

For a quick smoke test with an already installed smaller model:

```bash
python pipeline/fulltext/run_local_llm_evidence_assessment.py \
  --model llama3.1:8b \
  --limit 1
```

Outputs:

- `data/processed/fulltext/local_llm_evidence_assessment.json`
- `data/processed/fulltext/local_llm_evidence_assessment.csv`

The preferred script name is now `evidence_assessment`. The older
`run_local_llm_evidence_adjudication.py` entry point and legacy output names
remain available for compatibility with existing checkpoints and scripts. In
methodology text, call this stage **full-text eligibility/evidence assessment
and data extraction**. Reserve `adjudication` for final conflict resolution
between model proposals, deterministic rules, and curator decisions.

This stage is non-destructive. It supplies bounded GROBID evidence chunks to
the model, asks for JSON matching a fixed sectioned schema, and records whether
the model's `supporting_quote` is actually present in the supplied chunks. Each
row has `assessment.eligibility_assessment`,
`assessment.source_classification`, and `assessment.data_extraction`; a legacy
top-level `adjudication` mirror is also written during the migration. Treat LLM
results as proposals until quote verification and QA metrics are acceptable.
Rows are only marked `semantic_auto_eligible` when the quote verifies, model
confidence exceeds the configured threshold, labels are internally consistent,
and the model does not request a human check.

The assessment also writes explicit routing fields. Primary empirical papers
route to `primary_evidence`; reviews, systematic reviews, and meta-analyses
route to `secondary_literature`; protocols, commentaries, conference abstracts,
and corrections route to `non_primary_context`. Secondary literature is retained
for the secondary-source graph view rather than handled as failed primary
evidence.

### Abstract-Only Evidence Fallback

For relevant/uncertain papers whose full text cannot be downloaded or converted,
run the same evidence-assessment schema in abstract-only mode. This is separate from
abstract screening: screening only decides relevance, while this fallback
extracts source/provenance and study variables that are explicitly stated in the
abstract.

```bash
python pipeline/fulltext/run_local_llm_evidence_assessment.py \
  --input data/processed/llm_abstract_screening_report_disorder.json \
  --evidence-mode abstract_only \
  --only-without-fulltext \
  --only-with-abstract \
  --model qwen3:14b \
  --continue-on-error \
  --timeout-sec 0
```

Outputs default to:

- `data/processed/fulltext/local_llm_abstract_only_assessment.json`
- `data/processed/fulltext/local_llm_abstract_only_assessment.csv`

When the input is an abstract-screening report, verified compound/entity
contexts are expanded into claim-level assessment rows. Rows are marked with
`evidence_mode=abstract_only`; the prompt requires `best_evidence_location` to
be `abstract` or `none` and tells the model to use `not_reported` for details
not explicitly present in the abstract.
