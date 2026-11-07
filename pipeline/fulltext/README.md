# Full-Text Conversion

This stage converts locally available PDFs into structured full-text artifacts
that downstream extraction and provenance checks can reuse.

Install the Python PDF-inspection dependency with:

```bash
python3 -m pip install -r pipeline/fulltext/requirements.txt
```

The current goal is a DOI-verified canonical article store feeding routed
article-text inputs. Conversion, source-identity checks, routing, and extraction
all operate on the unified corpus rather than dataset-specific claim files.

## PDF Retrieval

Immediately after screening, build the route-independent full-text worklist:

```bash
python pipeline/fulltext/build_fulltext_enrichment_worklist.py
```

The worklist is one row per newly selected, unprocessed DOI. It assigns only a
full-text handling action; it does not construct extraction domains, prompt
profiles, schemas, or model tasks. Records whose access status is not yet known
are assigned `refresh_access_metadata` and written to
`fulltext_access_metadata_refresh_dois.txt`, the exact scope for the subsequent
Unpaywall/OpenAlex access-metadata refresh.

For a fresh screening generation followed by a full extraction rerun, use that
generation's queue and pre-screen candidate snapshot, with
`--include-previously-processed`. This audits **all current eligible inclusions**,
including older abstract-only papers, while preserving the ordinary incremental
workflow by default. Complete access refresh, PMC/PDF retrieval, identity checks,
conversion and reconciliation before freezing extraction inputs or reporting a
final extraction cost. Existing local packets alone do not establish readiness.
The Luna rerun preparation command requires a completed full-text recovery state
tied to the exact screening-table hash.

After the refresh, rebuild the worklist. OA-positive records that still lack a
provider-declared PDF are assigned `resolve_oa_landing_page` and written to
`fulltext_oa_landing_dois.txt`. Records for which providers report closed access
are assigned `no_accessible_fulltext` and written separately to
`fulltext_no_accessible_fulltext_dois.txt`. They are not PDF-download or browser
recovery tasks. A concrete PDF URL remains actionable even if its OA status
field is negative, unless the candidate ledger already records a completed,
non-retryable failure. `download_failed` rows with
`pdf_download_retry_recommended=true` remain actionable; non-retryable failures
are assigned `no_accessible_fulltext` and use abstract-level extraction for the
current run. The downloader records `pdf_download_attempt_count` and, by
default, permits two DOI-level retrieval runs (`--max-download-attempts 2`). A
retryable failure on the second run is marked
`pdf_download_retry_budget_exhausted=true`, becomes non-retryable, and therefore
cannot be silently requeued forever. HTTP retries inside a single retrieval run
remain controlled separately by `--max-retries`. A later successful/manual
import supersedes the failure because
local PDF and verified full-text state take precedence. The worklist retains
the download status, failure categories, retry flag, and terminal-state flag
so this decision remains auditable after regeneration.

After PMC recovery and worklist regeneration, refresh missing PDF links only
for that discovery scope:

```bash
python pipeline/ingest/refresh_open_access_links.py \
  --doi-file data/processed/corpus/fulltext_access_metadata_refresh_dois.txt \
  --pmc-report data/processed/fulltext/pmc_xml_report.postscreen_<run>.json \
  --report-json data/processed/fulltext/open_access_link_refresh_report.postscreen_<run>.json \
  --only-missing-pdf-url \
  --provider-order unpaywall,openalex,pmc \
  --progress-every 100
```

Retrieve PMC XML first, then PDFs:

```bash
python pipeline/fulltext/fetch_pmc_fulltext_xml.py \
  --selection-table data/processed/corpus/fulltext_enrichment_worklist.parquet \
  --workers 8

python pipeline/fulltext/download_fulltext_worklist_pdfs.py \
  --include-weak-pdf-urls \
  --workers 12 \
  --rps 2.0 \
  --progress-every 25 \
  --write-every 25
```

The first pass uses provider-declared PDF candidates from `download_known_pdf`
rows plus OA/DOI landing routes from `resolve_oa_landing_page` rows in the worklist,
including opaque publisher/repository download endpoints when
`--include-weak-pdf-urls` is set. `no_accessible_fulltext` and
`refresh_access_metadata` rows are never projected into the downloader.
After the direct pass, run a separately scoped recovery pass with
`--alternate-pdf-sources --alternate-sources-only`; this avoids replaying known
failed publisher endpoints before each repository lookup. Opaque candidates
are attempts, not accepted PDFs: the downloader
validates both PDF bytes and document identity before saving:

A failed unattended download does not establish that full text is unavailable.
When a candidate URL or positive open-access signal remains, exhausted direct
HTTP attempts move the record to `resolve_oa_landing_page` for browser/manual
recovery. Only explicit provider-closed evidence without a usable location, or
a curator-confirmed access decision, moves it to `no_accessible_fulltext`.
the expected title must match the bounded top region of page one. A title that
appears later on page one or elsewhere in the document is not sufficient,
because proceedings and supplement PDFs can contain many valid paper titles.
The only exception is an explicit DOI-plus-SHA-256 decision in
`source_identity_pdf_hash_registry.json`; that decision applies only to the
reviewed byte-identical PDF. The downloader updates `candidate_papers.parquet`
but does not build extraction routes when a selection table is supplied. Build
routes once after retrieval and conversion are finished.

For human recovery, `build_manual_pdf_exploration_queue.py` converts the
current actionable `download_known_pdf` population into recovery-oriented lanes. It also
writes a host summary and a representative pattern-scout list so a reviewer
can identify repeatable publisher or repository click paths before automating
them. Retrieval outcomes do not change study eligibility: records with
terminal retrieval failures remain eligible for abstract-level extraction and
can be reactivated later if a usable full text is imported.

Before presenting that scout, audit title language on macOS with the local
Natural Language framework:

```bash
python pipeline/fulltext/audit_manual_pdf_queue_languages.py
python pipeline/fulltext/register_retrieved_pdf_exclusions.py \
  --audit-csv data/processed/corpus/audits/manual_pdf_recovery_language_audit.csv
python pipeline/fulltext/register_retrieved_pdf_exclusions.py \
  --audit-csv data/processed/corpus/audits/manual_pdf_recovery_language_audit.csv \
  --apply
python pipeline/fulltext/apply_post_retrieval_publication_format_screen.py --apply
```

Only high-confidence non-English titles are excluded. Short titles,
scientific-name false positives, and metadata/title disagreements enter a
language-review lane instead. Rebuild the worklist and manual queue afterward;
the exploration scout automatically omits both confirmed non-English records
and unresolved language-review records.

For large host-diverse queues, `--workers` overlaps slow cross-host responses;
all workers still share the single global `--rps` request budget. The standard
pipeline wrapper defaults to eight workers, four requests per second globally,
host-aware interleaving, and a 30-second cooldown after transient host failures.
Override those values downward for a host-concentrated queue. Candidate-table
checkpoints and JSON reports are replaced atomically, so an interruption cannot
leave a partial Parquet or JSON file.

For lower-level retry runs, `download_routed_pdfs.py` can also query alternate
open-access sources before giving up on a DOI:

```bash
python pipeline/fulltext/download_routed_pdfs.py \
  --selection-table data/processed/corpus/fulltext_enrichment_worklist.parquet \
  --alternate-pdf-sources pmc,openalex \
  --alternate-sources-only \
  --workers 8 \
  --rps 4 \
  --progress-every 100
```

The alternate-source layer supports PMC ID conversion for an XML-retrieval
handoff and OpenAlex repository locations. PMC viewer pages are not scraped;
use the approved full-text APIs above. Access challenges enter manual review.
A Semantic Scholar
`openAccessPdf` resolver remains available as an explicit optional strategy, but
is disabled by default and is not part of the standard recovery sequence. Successful files are written as ordinary local PDFs and
candidate rows keep the standard `downloaded` status; report records include
the alternate source that supplied the winning URL. Unsuccessful alternate-only
lookups do not overwrite the prior publisher failure in the candidate ledger.

When `--include-weak-pdf-urls` is enabled, the concurrent downloader also adds
the record's open-access landing URL and `doi.org` resolver URL. It follows
deterministic PDF links found on those pages and still requires DOI/title
identity validation before acceptance. Export the manual queue only after this
landing-page pass; browser work is then limited to the remaining challenge,
paywall, and complex-JavaScript exceptions.

Use targeted repository recovery diagnostics when needed:

```bash
python pipeline/fulltext/recover_pdf_landing_pages.py \
  --standard-recovery-only \
  --categories forbidden,non_pdf_response,rate_limited,provider_error,timeout,other_download_failure,not_found
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

## Historical Full-Text Backfill

Use the historical backfill when an already processed DOI was extracted from
its abstract but may now have an open-access full text. The cohort is derived
from successful `abstract_only` outputs in the active routed extraction run;
it is not inferred from missing graph fields or from the presence of an old
URL.

Build the initial cohort:

```bash
python pipeline/fulltext/build_historical_fulltext_backfill.py
```

Refresh every eligible DOI against Unpaywall, OpenAlex, and PMC even when the
record already has a stale or non-PDF link:

```bash
python pipeline/ingest/refresh_open_access_links.py \
  --doi-file data/processed/corpus/historical_fulltext_backfill/oa_refresh_dois.txt \
  --provider-order unpaywall,openalex,pmc \
  --expand-existing-pdf-candidates \
  --report-json data/processed/corpus/historical_fulltext_backfill/oa_refresh_report.json
```

Then rebuild the cohort with that report:

```bash
python pipeline/fulltext/build_historical_fulltext_backfill.py \
  --oa-refresh-report data/processed/corpus/historical_fulltext_backfill/oa_refresh_report.json
```

Only records with fresh positive OA evidence enter `oa_retrieval_dois.txt`.
A provider-declared PDF becomes `download_known_pdf`; an OA-positive landing
page without a declared PDF becomes `resolve_oa_landing_page`. Link presence
alone is not evidence of open access, and fresh OA-negative records are not
sent through unattended download attempts. Curated `abstract_only` and
`suppress_pdf_download` decisions remain authoritative. The builder refuses an
incomplete refresh report and reads the report's per-run OA observations, so a
stale stored OA label cannot qualify a historical record. Likewise, a stored
`flag_has_local_pdf` does not qualify a record unless the referenced PDF still
exists on disk; moved or quarantined files go back through OA retrieval.

Run automated retrieval with backfill-specific reports so it cannot overwrite
the new-paper or browser-manual queues:

```bash
python pipeline/fulltext/run_pdf_retrieval_pipeline.py \
  --selection-table data/processed/corpus/historical_fulltext_backfill/historical_fulltext_backfill_worklist.parquet \
  --doi-file data/processed/corpus/historical_fulltext_backfill/oa_retrieval_dois.txt \
  --direct-include-weak-pdf-urls \
  --alternate-pdf-sources pmc,openalex \
  --direct-report data/processed/corpus/historical_fulltext_backfill/pdf_direct_report.json \
  --recovery-report data/processed/corpus/historical_fulltext_backfill/pdf_recovery_report.json \
  --manual-queue-csv data/processed/corpus/historical_fulltext_backfill/manual_queue.csv \
  --manual-queue-txt data/processed/corpus/historical_fulltext_backfill/manual_queue_dois.txt \
  --report data/processed/corpus/historical_fulltext_backfill/pdf_pipeline_report.json
```

After automated retrieval, rebuild the worklist and convert only its actual
local PDFs with the route-independent managed converter:

```bash
python pipeline/fulltext/run_local_pdf_conversion_pipeline.py \
  --selection-table data/processed/corpus/historical_fulltext_backfill/historical_fulltext_backfill_worklist.parquet \
  --doi-file data/processed/corpus/historical_fulltext_backfill/local_pdf_conversion_dois.txt
```

This worklist is retrieval-only. Downloading or converting a full text never
changes the active extraction output or graph. After PDF identity validation,
conversion, and successful full-text model extraction, replace evidence using
the DOI-scoped update transaction:

```text
run_scoped_paper_update.py prepare
full-text extraction for the prepared tasks
run_scoped_paper_update.py finalize
review the finalized candidate
run_scoped_paper_update.py promote
```

The scoped update removes all old abstract-derived outputs and evidence for
each promoted DOI and adds the validated current full-text outputs atomically;
out-of-scope graph rows are preserved. Do not prepare a promotion scope merely
because a PDF was downloaded, and do not submit model jobs automatically as
part of OA refresh or retrieval.

## Browser Manual Recovery

For a retrieval run with many OA-positive failures, first build a scoped pilot
that keeps only unresolved browser candidates with a location beyond DOI,
PubMed, and OpenAlex resolvers. Supply the main report first and retries
afterward so the latest result for each DOI wins. The pilot is host-balanced
and takes tiers A-C before tier D:

```bash
python pipeline/fulltext/build_browser_recovery_pilot.py \
  --scope-report data/processed/corpus/audits/pdf_oa_landing_new_dois_20260717.json \
  --scope-report data/processed/corpus/audits/pdf_oa_landing_new_dois_rate_limit_retry_20260717.json \
  --scope-report data/processed/corpus/audits/pdf_oa_landing_new_dois_timeout_provider_retry_20260717.json \
  --pilot-limit 50
```

The full independent-location queue and the pilot are written separately, so
pilot yield can be assessed before scaling browser work. Each attempt uses only
the canonical DOI landing page and follows the publisher's article/full-text
controls. If that page shows purchase, subscription, login, or institutional
access requirements, record `closed_access` and stop; do not navigate to the
independent URL. Those URLs are retained only as provenance for why the record
entered this pilot. Resolver-only DOI records remain in the ranked manual queue
for a later, lower-yield pass.

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

For a resumable automated DOI-browser pass, use
`recover_pdfs_via_doi_browser.cjs`. If a prior run contains technical browser
errors, first create a scoped retry queue and then rerun only those records:

```bash
python pipeline/fulltext/build_doi_browser_retry_queue.py
node pipeline/fulltext/recover_pdfs_via_doi_browser.cjs \
  --doi-file data/processed/corpus/audits/doi_browser_technical_retry_queue_20260719.txt \
  --report data/processed/corpus/audits/doi_browser_technical_retry_report.json \
  --workers 4 --timeout-ms 30000 --settle-ms 1000
```

The browser runner waits for redirect chains to settle and retries page
inspection when navigation destroys the JavaScript execution context. It
writes only to the manual inbox; every captured file must still pass the
post-retrieval identity and publication-format audit before canonical import.

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
one, a recognized Elsevier PII (including legacy 16-character PIIs), or an
exact DOI-plus-SHA-256 registry decision. Ambiguous and conflicting files stay
out of the canonical PDF store. For a curated browser queue, pass its CSV as
`--manual-csv`; this preserves the source URL and title identity evidence used
to construct that queue.

When a curator has confirmed that an existing canonical PDF is the wrong file
for a DOI, rerun the importer with `--replace-existing`. The old canonical PDF
is moved to `data/raw/papers/pdf_conflicts/` and the candidate row is refreshed
with the replacement checksum.

After importing manual PDFs, rebuild routes and convert any newly local PDFs:

```bash
python pipeline/extract/build_extraction_routes.py
python pipeline/fulltext/run_local_pdf_conversion_pipeline.py --batch-size 25
```

When both the new-paper worklist and historical full-text backfill contain
local PDFs, rebuild both worklists and create one canonical conversion
selection before starting GROBID:

```bash
python pipeline/fulltext/build_local_pdf_conversion_selection.py
python pipeline/fulltext/run_local_pdf_conversion_pipeline.py \
  --selection-table data/processed/corpus/local_pdf_conversion_selection.parquet \
  --batch-size 25
```

The selection builder requires current deterministic-prescreen retention and
current downstream eligibility, resolves registered DOI aliases, deduplicates
the two explicit cohorts, and also reconciles any retained
`convert_local_pdf_then_extract` route that predates those worklists. This
route-based union is a conversion safety net, not the source of the initial
full-text discovery scope. The builder blocks unresolved byte-identical PDFs assigned to
different non-alias DOIs. The managed runner and lower-level converter also
re-check the current prescreen table and fail before conversion if a stale
selection contains an excluded DOI.

Successful conversion writes canonical artifacts under
`data/processed/fulltext/articles/` and the final route rebuild moves those
papers from `needs_pdf_conversion` to `ready_for_article_text_extraction`.
Refresh manual queue outputs after route changes:

```bash
python pipeline/fulltext/export_manual_pdf_queue.py
python pipeline/fulltext/rank_manual_pdf_queue.py
```

For a route-independent OA/full-text worklist, also pass the browser progress
ledger. Recovered canonical PDFs and terminal manual outcomes are removed,
while interrupted/rate-limited records remain queued with their status and
notes:

```bash
python pipeline/fulltext/export_manual_pdf_queue.py \
  --selection-table path/to/fulltext_worklist.parquet \
  --manual-progress-csv path/to/browser_manual_progress.csv \
  --output-csv path/to/manual_queue.csv \
  --output-txt path/to/manual_queue_dois.txt
```

Reserve a new host-balanced DOI batch before opening browser tabs. Every DOI
already present in the progress ledger is skipped, including interrupted rows,
so they can be resumed separately without being opened twice:

```bash
python pipeline/fulltext/prepare_browser_doi_batch.py \
  --queue-csv path/to/manual_queue.csv \
  --progress-csv path/to/browser_manual_progress.csv \
  --batch-size 50 \
  --output-csv path/to/browser_batch.csv \
  --output-txt path/to/browser_batch_urls.txt \
  --apply-progress
```

The selector round-robins DOI registrant prefixes to avoid opening a large
single-publisher block that is likely to trigger platform throttling.

Before treating every missing download as closed access, reconcile the browser
ledger with the importer report. `partial_review_rate_limited` rows remain
pending; completed rows without a usable PDF can be written as durable access
overrides:

```bash
python pipeline/fulltext/reconcile_browser_recovery_batch.py \
  --batch-csv path/to/browser_manual_progress.csv \
  --import-report path/to/manual_pdf_import_report.json \
  --output-csv path/to/browser_manual_reconciliation.csv \
  --report-json path/to/browser_manual_reconciliation.json \
  --update-progress-ledger path/to/browser_manual_progress.csv \
  --apply-access-overrides
```

If browser/manual review confirms that a DOI has no usable open article PDF,
record that durable decision in
`pipeline/fulltext/manual_fulltext_access_overrides.json` with
`manual_access_action=suppress_pdf_download`, then rebuild routes. If the record
is not an eligible source article or evidence synthesis, record the authoritative
publisher, repository, or document evidence in
`data/curated/post_retrieval_eligibility_decisions.json`, then run the
dedicated post-retrieval eligibility checkpoint:

```bash
python pipeline/fulltext/audit_deterministic_repository_formats.py
python pipeline/fulltext/register_retrieved_pdf_exclusions.py \
  --audit-csv data/processed/corpus/audits/deterministic_repository_format_audit.csv
python pipeline/fulltext/register_retrieved_pdf_exclusions.py \
  --audit-csv data/processed/corpus/audits/deterministic_repository_format_audit.csv \
  --apply
python pipeline/fulltext/apply_post_retrieval_publication_format_screen.py
python pipeline/fulltext/apply_post_retrieval_publication_format_screen.py --apply
```

The repository audit recognizes only stable, high-precision identifier,
repository-route, and supplement/coded-title signals (for example thesis
collections, data deposits, books, Morressier records, and conference
supplement abstracts). Registration and the first checkpoint command are dry
runs. The applied pass writes dedicated
`post_retrieval_*` candidate fields and the current exclusion-stage projection;
it does not rewrite the original deterministic prescreen decision. Confirmed
exclusions clear stale extraction and graph projections. Never infer an
eligibility exclusion, a paywall, or a terminal access outcome from a failed
download alone. Timeouts, WAF responses, missing controls, and other unresolved
attempts remain only in retrieval logs and retry queues.

The checkpoint now preserves the model-screening result table by default and
filters the active primary, review-relationship and meta-analysis task queues.
It sets `retained_for_extraction_candidate=false` immediately for confirmed
exclusions; a later `retain` decision alone never resurrects a model-excluded
paper. Rebuilding routes also honors the materialized record decision.

To apply a reviewed subset, use the existing registration schema (CSV fields
`doi`, `recommended_action=exclude_publication_format`, `publication_format`,
`format_evidence`, plus optional specific `reason`, `decision_method` and
`reviewer`). Records with access/retry/review actions are not registrations.
Book chapters, news/CME summaries, supplementary objects and correction records
have explicit formats; their reasons must describe the actual source evidence.

```bash
python pipeline/fulltext/register_retrieved_pdf_exclusions.py \
  --audit-csv path/to/reviewed_exclusions.csv --run-id publication_cleanup_DATE
python pipeline/fulltext/register_retrieved_pdf_exclusions.py \
  --audit-csv path/to/reviewed_exclusions.csv --run-id publication_cleanup_DATE --apply
python pipeline/fulltext/apply_post_retrieval_publication_format_screen.py \
  --doi-file path/to/approved_dois.txt --run-id publication_cleanup_DATE
python pipeline/fulltext/apply_post_retrieval_publication_format_screen.py \
  --doi-file path/to/approved_dois.txt --run-id publication_cleanup_DATE --apply
```

The DOI scope limits candidate mutations while the materialized decision table
still mirrors the complete canonical ledger. The 22 October 2026 application
uses the previously reviewed 293 record exclusions. It does not convert the
19 unresolved records into exclusions or blacklist any journal/publisher.
Future-safe reusable format rules live in the prescreen module; source-verified
record evidence stays in this ledger. No separate source blacklist or second
eligibility ledger is needed. Keep original documents, raw Luna answers and
past audit artifacts; do not edit them to imitate an earlier prescreen finding.

The document auditor checks report identity before assigning an exclusion to
the intended DOI: a wrong thesis or meeting PDF is quarantined for source
review. Non-Latin script proportions are review signals, not language verdicts;
mixed metadata containing an English language code is not automatically a
non-English exclusion. Confirmed source-specific language findings can still
be registered in the same eligibility ledger after review.

For a browser-retrieval batch, run the document-level checkpoint before the
manual importer. It separates validated articles from definite format/language
exclusions, unresolved identities, and wrong documents:

```bash
python pipeline/fulltext/audit_retrieved_pdf_publication_formats.py
python pipeline/fulltext/register_retrieved_pdf_exclusions.py
python pipeline/fulltext/register_retrieved_pdf_exclusions.py --apply
python pipeline/fulltext/apply_post_retrieval_publication_format_screen.py
python pipeline/fulltext/apply_post_retrieval_publication_format_screen.py --apply
python pipeline/fulltext/register_retrieved_pdf_aliases.py \
  --audit-csv path/to/document_audit.csv
python pipeline/fulltext/stage_retrieved_pdf_audit.py
python pipeline/fulltext/stage_retrieved_pdf_audit.py --apply
python pipeline/fulltext/import_manual_pdfs.py
python pipeline/fulltext/import_manual_pdfs.py --apply --move
```

The registration and staging commands are dry runs by default. Only definite
conference/meeting abstracts, dissertations or theses, and non-English
documents are promoted from this audit into the curated exclusion ledger.
Unresolved document identities, wrong downloads, suspicious-but-unconfirmed
formats, and differing alternate bytes are moved into separate quarantine or
review directories, not deleted and not imported. High-confidence repository
wrapper DOI aliases require a matching title and a published DOI on the
document front page. The importer can consume those audited hashes with
`--validated-document-audit` and never silently overwrite an existing PDF.

## Source identity of stored texts

Every path that stores a full text (`fetch_pmc_fulltext_xml.py`,
`convert_routed_local_pdfs.py` and `run_local_pdf_conversion_pipeline.py`, which
runs it in batches) checks the text with the identity module before writing it
(`pipeline/identity/intake.py`; rule in `pipeline/identity/README.md`). A
verified text is stored and used. A text that is not verified is stored for
review and left unused until it is decided, but never replaces a stored text
that the verdict table allows. Every written text then gets its rows in the
verdict table, so the next route build reads it. `python -m pipeline.identity
audit` lists the texts awaiting a decision.

The older acquisition audit (`audit_fulltext_source_identity.py` and its report
`source_identity_audit.json`) was removed on 8 November 2026; its decisions were
migrated into the identity decision file. The completed July 2026 repair
campaign is retained as a provenance record in
`pipeline/fulltext/attestations/source_identity_repair_20260710.json`.

The gate (`pipeline/identity/gate.py`) decides per artifact from the verdict
table (`pipeline/identity/README.md`). An artifact is used only when the table
has a usable row for that file and that DOI and the file has not changed since.
Otherwise that artifact alone is rejected with one of these reasons, and the run
continues:

- not in the table;
- the table does not allow it;
- content changed after the table was built (a newer file time with an unchanged
  hash is not a change).

Packet building leaves rejected artifacts out and lists them with their
reasons. Route building sends a paper whose stored text is rejected to its
abstract (`extract_from_abstract_only`), or to `hold_until_text_available` when
it has no abstract, instead of queueing the same PDF for conversion again. The
route table records the gate's verdict in `fulltext_identity_status`. Recording a
decision and running `python -m pipeline.identity apply --install` restores
usable text. A writer adds rows for the artifacts it has just written and reports
any the table does not make usable (`written_not_usable`).

PMC/Europe PMC XML acquisition is DOI-selective as well. For JATS collections
containing multiple `<article>` or `<sub-article>` records, the fetcher requires
exactly one requested-DOI match and serializes only that node. Whole proceedings
containers and adjacent abstracts cannot be stored under an item DOI.

## Canonical Article Text Store

New full-text artifacts should be written to
`data/processed/fulltext/articles/`. This is the only production article-text
store; no split-source fallback directories are read.

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

## Post-screen Local-PDF Conversion

Convert locally available PDFs from the post-screen worklist with:

```bash
python pipeline/fulltext/convert_fulltext_worklist_pdfs.py \
  --backend grobid
```

`convert_pdfs.py` contains only shared parser and artifact helpers used by the
full-text conversion entry points; it is not a separate production command.

## PMC XML Recovery

Some retained papers have reusable PMC full-text XML even when no local PDF has
been downloaded. Retrieve those XML records before finalizing abstract-only
routes:

```bash
python pipeline/fulltext/fetch_pmc_fulltext_xml.py \
  --selection-table data/processed/corpus/fulltext_enrichment_worklist.parquet \
  --progress-every 25 \
  --rps 1.5
```

With `--selection-table`, the script targets post-screen `fetch_pmc_xml` rows
and skips papers that already have a converted full-text artifact or valid
local PDF.
It tries the Europe PMC XML endpoint first and falls back to PMC OAI/JATS. Each
successful XML record is written to `data/processed/fulltext/articles/` with
the same artifact shape as PDF conversion, including section summaries and raw
XML for article text input building. It refreshes the source-identity audit but
does not build extraction routes in selection-table mode. Regenerate the
full-text worklist after retrieval to refresh remaining actions, then build
final extraction routes after all enrichment passes are complete.

Pass every completed versioned PMC report in chronological order when
regenerating the worklist so
`not_available` and `failed` records advance to PDF-link discovery instead of
being queued for PMC again:

```bash
python pipeline/fulltext/build_fulltext_enrichment_worklist.py \
  --pmc-report data/processed/fulltext/pmc_xml_report.postscreen_<initial_run>.json \
  --pmc-report data/processed/fulltext/pmc_xml_report.postscreen_<incremental_run>.json
```

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

JATS inputs also preserve figure captions and table wrappers, including labels,
captions, footnotes, source IDs, and section headings. Table cells retain header
and row/column-span metadata in the packet; nested tables are not emitted again
as separate copies of their wrapper. Caption and note text is included in the
table/figure text passed downstream.

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

Use `build_article_text_inputs.py` with the canonical `fulltext/articles/`
store for route-table extraction runs.

For a small route-table section-selection audit:

```bash
python pipeline/fulltext/audit_article_text_inputs.py \
  --per-strategy 3
```

Use `primary_study` for primary-study section selection.

For reviewed source repairs, persist bibliography in
`data/curated/paper_metadata_overrides.json` and verified duplicate identifiers
in `pipeline/validate/doi_alias_registry.json`. A wrong, supplementary,
incomplete or unverified draft download can use the existing
`manual_fulltext_access_overrides.json` action `abstract_only` while its parent
paper remains eligible. Preserve the original source bytes and repair evidence.
Confirmed publication/language exclusions remain in the post-retrieval
eligibility ledger described above.

When report identity or publication eligibility cannot be established, use
`pipeline/extract/manual_extraction_route_overrides.json` with
`manual_action=hold_source_review` and a specific evidence-linked reason.
Rebuilding routes makes that record ineligible for extraction and records
`extraction_route_status=hold_source_review`. This is a reversible source hold;
it does not rewrite completed model screening or register a confirmed exclusion.
Resolve the evidence and remove the hold explicitly before rebuilding inputs.
