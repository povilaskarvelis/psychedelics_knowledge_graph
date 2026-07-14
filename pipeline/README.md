# Pipeline

This pipeline builds and maintains the evidence base behind the Psychedelics
Knowledge Graph. It records how records were found, screens them for relevance,
prepares the best available report text, extracts structured findings, and
publishes reviewed releases of the graph, record audit, and Methods page.

This README is the living operational map for the current pipeline. When a
step changes, update this file first, then update the narrower stage README if
the change affects a specific script family.

## Current Workflow

```mermaid
flowchart TD
  A["Plan grouped and focused searches"] --> B["Find and deduplicate records"]
  B --> C["Build the record corpus and enrich metadata"]
  C --> D["Initial rules-based record screening"]
  D --> E["Title and abstract screening and report classification"]
  E --> F["Prepare report extraction assignments"]
  G["Reviewed exceptions"] --> F
  F --> H["Retrieve and convert available article text"]
  F --> I["Use abstracts when article text is unavailable"]
  H --> J["Extract primary-study findings"]
  H --> K["Extract meta-analysis results"]
  H --> L["Extract review relationships"]
  I --> J
  I --> K
  I --> L
  J --> M["Check source support, align names, and assemble evidence"]
  K --> M
  L --> M
  M --> N["Build a versioned graph release"]
  N --> O["Publish graph, bibliography, Methods data, and site together"]
```

1. **Search planning** defines grouped domain searches and targeted direct-pair
   searches from the current compound, condition, clinical, molecular,
   brain-system, cognitive-behavioral, safety, pharmacology, intervention, and
   public-health vocabularies.
2. **Literature discovery** queries the selected literature sources and stores
   source/run provenance for every retrieved DOI. Duplicate DOIs are deduplicated
   at the corpus level, but their search-source provenance is retained.
3. **Corpus table build** normalizes discovered records into the table-native
   corpus under `data/processed/corpus/`, especially `candidate_papers.parquet`,
   `candidate_contexts.parquet`, and `candidate_sources.parquet`.
4. **Metadata enrichment** adds titles, abstracts, publication metadata,
   publication-type labels, identifiers, open-access status, and PDF URL
   candidates. Provider roles are explicit: bibliographic metadata and
   abstracts, PubMed publication types, and open-access/PDF-link discovery are
   refreshed as separate passes.
5. **Initial screening** removes only records that clearly lack usable
   title/abstract evidence or clearly fall outside the project scope. It writes
   decisions to `paper_prescreen_decisions.parquet` and can be rerun for the
   whole corpus or a DOI subset.
6. **Title and abstract screening and classification** assesses retained records
   for relevance, evidence topics, and report type. Primary studies,
   meta-analyses, other reviews, and non-primary context remain distinguishable
   throughout extraction and publication. The current implementation uses a
   structured model-assisted pass, with exact technical details recorded in the
   generated corpus fields and run artifacts.
7. **Extraction preparation** combines the screening decisions, report type,
   evidence topics, available source text, and narrowly reviewed exceptions in
   `paper_extraction_routes.parquet`. Despite the filename, this is best
   described publicly as the set of extraction assignments for each report.
8. **Source-text preparation** refreshes open-access links, downloads available legal
   PDFs, retrieves reusable PMC XML when available, and converts local full-text
   sources into structured artifacts. Records without usable full text remain
   eligible for abstract-only extraction when they otherwise meet the selection
   criteria.
9. **Structured evidence extraction** uses different report-centered contracts
   for primary studies, meta-analyses, and other reviews. Primary-study results,
   pooled estimates, and review-level relationships are not flattened into one
   evidence type. Guidelines, context-only records, and other non-extraction
   records remain available for corpus accounting without becoming findings.
10. **Validation and graph preparation** checks extracted information against
    its source, preserves source locations, uses consistent names for compounds
    and related topics, and writes one final graph-inclusion decision, reason,
    and provenance record back to `candidate_papers.parquet` for every DOI.
11. **Staging and publication** builds versioned graph tables, author data, and
    compact browser files. A guarded promotion first materializes and validates
    the release's final decisions in the canonical corpus ledger, then generates
    the bibliography and PRISMA flow from that ledger alone. It updates the
    ledger, active evidence release, graph, Methods outputs, and static site as
    one atomic unit.

Generated Parquet tables are rebuildable. Durable decisions should live in
tracked code, configuration, search strategy files, model prompts, or small
manual-review files such as `pipeline/extract/manual_extraction_route_overrides.json`
and `pipeline/fulltext/manual_fulltext_access_overrides.json`. Curated screening
decisions in `data/curated/screening_decision_overrides.json` are applied before
extraction. Final post-extraction exceptions may be staged in
`data/curated/graph_inclusion_disposition_overrides.json`, but public outputs do
not read that file directly; promotion writes the resolved decision into the
canonical corpus first.
CSV audit files are human-readable inspection artifacts unless a script
explicitly takes them as input.

## Main Commands

### Updating one report or a DOI list

Do not rerun all model extraction or edit KG rows directly for a correction.
Use the three-phase scoped updater:

```bash
python pipeline/update/run_scoped_paper_update.py prepare \
  --update-id paper_fix_YYYYMMDD \
  --doi-file path/to/update_dois.txt \
  --refresh-derived

# Run only the generated ready_tasks*.jsonl files through extraction.

python pipeline/update/run_scoped_paper_update.py finalize \
  --update-id paper_fix_YYYYMMDD \
  --patch-outputs path/to/scoped_route_extraction_outputs.jsonl

python pipeline/update/run_scoped_paper_update.py promote \
  --update-id paper_fix_YYYYMMDD
```

Preparation and finalization do not change the active KG. Finalization removes
all previous output/evidence rows for the DOI scope and refuses incomplete or
stale replacements. See
[`docs/scoped_paper_updates.md`](../docs/scoped_paper_updates.md) for batch API
commands, exclusion-only updates, audits, and rollback behavior.

### Search Planning

Build the current search files from configured registries:

```bash
python pipeline/ingest/build_boolean_search_modules.py --dataset all --run-id search_2026_05
python pipeline/ingest/build_comprehensive_search_plan.py --dataset all --profile standard --run-id search_2026_05
```

If `--run-id` is omitted, scripts write to the neutral
`data/raw/search_strategies/literature_search/` run directory.

### Literature Discovery

Run grouped search modules or direct pair-search files through
`discover_literature.py` or the batch runners in `pipeline/ingest/`.

Example:

```bash
python pipeline/ingest/discover_literature.py \
  --dataset mechanistic \
  --provider pubmed \
  --seed-file data/raw/search_strategies/search_2026_05/grouped_modules/mechanistic_grouped_pubmed_seeds.csv \
  --max-results-per-seed 500 \
  --max-results 0
```

### Corpus Table Build

```bash
python pipeline/validate/build_context_provenance_audit.py \
  --table-out-dir data/processed/corpus
```

This writes `candidate_papers.parquet`, `candidate_contexts.parquet`,
`candidate_sources.parquet`, and `candidate_corpus_manifest.parquet`.
Rediscovered records are deduplicated by DOI while keeping
their source/query provenance in the context and source tables.

### Metadata Enrichment

Run role-aware metadata enrichment on the corpus table:

```bash
python pipeline/ingest/run_standard_metadata_enrichment.py \
  --dataset all \
  --write-every 100 \
  --progress-every 100
```

This writes `paper_metadata_enrichment.parquet`. Core metadata and abstracts
are refreshed separately from PubMed publication types and open-access/PDF URL
candidates. The default provider roles are controlled in
`run_standard_metadata_enrichment.py`: core metadata uses
PubMed/PMC/OpenAlex/Crossref/Semantic Scholar fallbacks, publication types come
from PubMed, and open-access/PDF links use Unpaywall/OpenAlex/PMC.

Scope a small update with `--doi-file <doi_list>` rather than rerunning the
whole table.

### Rule-Based Pre-Screen

```bash
python pipeline/review/run_deterministic_prescreen.py \
  --run-id deterministic_prescreen_YYYY_MM_DD
```

This writes `paper_prescreen_decisions.parquet` and
`paper_prescreen_summary.parquet`. It excludes only clear title/abstract
no-signal records, unusable abstract artifacts, and records that are clearly
outside scope. Use `--doi-file <doi_list>` or repeated `--doi <doi>` for scoped
updates.

### Gemini Domain Routing

Prepare batch requests:

```bash
python pipeline/review/build_gemini_domain_routing_batch_queue.py --prepare
```

Advance the queue one submitted part at a time:

```bash
python pipeline/review/advance_gemini_domain_routing_batch_queue.py
```

This writes `paper_domain_routing_gemini.parquet`,
`paper_domain_routing_gemini_summary.json`, and
`paper_domain_routing_gemini_counts.csv`. The Gemini response includes
`screening_decision`, `domain_tags`, `primary_domain`, `paper_type_group`, and
`paper_type`; this table is the source of report type for new extraction routes.

### Extraction Routes

```bash
python pipeline/extract/build_extraction_routes.py \
  --domain-routing-table data/processed/corpus/paper_domain_routing_gemini.parquet
```

This writes `paper_extraction_routes.parquet`,
`paper_extraction_routes_summary.json`, and
`paper_extraction_routes_counts.csv`. Preprint and unpublished posted-content
records are excluded before routing by deterministic pre-screening, and the
route build treats the pre-screen table as authoritative. The build also
applies two narrow DOI-level manual review files:

- `pipeline/extract/manual_extraction_route_overrides.json` for route/domain
  decisions such as context-only, conference abstracts, corrections, or
  non-article records.
- `pipeline/fulltext/manual_fulltext_access_overrides.json` for access
  decisions such as suppressing a misleading probable-PDF URL after manual
  review confirms there is no usable open article PDF.
- `data/curated/screening_decision_overrides.json` for reviewed report-level
  exclusions that must prevent extraction tasks.

The build also updates `candidate_papers.parquet` as the DOI-level pipeline
ledger. It backfills publication-stage fields, pre-screen summaries, Gemini
report-type/domain summaries, extraction-route status, route counts, prompt and
schema profiles, manual full-text access decisions, and the best available text
tier. Promotion then adds the final graph status, disposition, reason, decision
source, run ID, and release ID. The detailed many-row route assignments stay in
`paper_extraction_routes.parquet`; `candidate_papers.parquet` keeps one row per
DOI and is the sole input for the public PRISMA flow and complete bibliography.
The Methods build fails when this ledger is missing a decision or contains a
contradictory screening, extraction-selection, or graph status.

Access tiers are intentionally operational:

- `full_text_available`: converted full-text artifact exists locally.
- `local_pdf_available`: valid PDF exists in `data/raw/papers/pdfs/`, but
  conversion is still needed.
- `pdf_download_url_available`: a metadata-derived URL looks like a direct PDF
  endpoint, but no valid local PDF or converted full text has been found yet.
- `abstract_only`: no local full text, local PDF, or probable PDF download URL is
  currently available. Weaker landing-page or repository URLs are still kept in
  the corpus table for manual access checks.

### Canonical PDF Store

The current pipeline stores active source PDFs in one canonical directory:

```text
data/raw/papers/pdfs/
```

Same-DOI alternate PDFs are preserved under `data/raw/papers/pdf_conflicts/`;
files with `.pdf` names that are not valid PDF content are kept under
`data/raw/papers/invalid/`.

To reconcile the file store and corpus table:

```bash
python pipeline/fulltext/migrate_pdf_store.py --mode move --apply --move-conflicts
```

Run without `--apply` for a dry run. The script updates
`candidate_papers.parquet` so `pdf_local_path`, `local_pdf_paths`, and
`local_pdf_count` reflect only the canonical PDF store.

### Open-Access Links And PDF Retrieval

Refresh PDF URL candidates for routed extraction candidates:

```bash
python pipeline/ingest/refresh_open_access_links.py \
  --routing-table data/processed/corpus/paper_extraction_routes.parquet \
  --only-missing-pdf-url \
  --provider-order unpaywall,openalex,pmc \
  --progress-every 100
```

Use the route table to keep PDF download attempts scoped to retained extraction
candidates and to avoid retrying known closed-access or already-downloaded
records.

Run the standard routed PDF retrieval stage:

```bash
python pipeline/fulltext/run_pdf_retrieval_pipeline.py \
  --route-table data/processed/corpus/paper_extraction_routes.parquet \
  --progress-every 25 \
  --write-every 25
```

This step targets retained `download_pdf_then_extract` reports, deduplicates by
DOI, writes successful downloads to `data/raw/papers/pdfs/`, and updates
`candidate_papers.parquet` with the canonical local PDF path and checksum. It
then runs the standard repository recovery pass for OSF/PsyArXiv and
Figshare-style records, rebuilds `paper_extraction_routes.parquet`, and exports
the remaining manual-download queue to
`data/processed/corpus/audits/manual_pdf_download_dois.csv/.txt`. Use
`--dry-run` to inspect the direct-download queue before network calls, and
`--limit <N>` for a small pilot. Use `--skip-standard-recovery` for debugging
when only the direct downloader should run. The runner prints an immediate
queue summary, logs each DOI before and after its direct download attempt, and
logs candidate-URL attempts/results by default. For
quieter supervised runs, set `--attempt-log-every <N>`,
`--candidate-log-every <N>`, or use `0` for either option; use
`--progress-every <N>` for aggregate progress summaries.
The route builder and downloader distinguish probable PDF endpoints from weaker
landing-page or repository links. Automated downloads use probable PDF URLs by
default; weaker links stay visible as `other_url_candidates` for refreshed link
discovery or manual download. Use `--include-weak-pdf-urls` only for diagnostic
or manually supervised recovery runs.

By default, the downloader interleaves queued reports by primary PDF host instead
of processing table order. This avoids sending long consecutive runs of requests
to one repository or publisher, which reduces avoidable rate limiting while
still keeping all reports in the same first-pass retrieval stage. If a host
returns a temporary failure such as a rate-limit response, timeout, or 5xx
provider error, only that host is cooled down; alternative PDF candidate URLs
for the same DOI can still be tried. Use `--preserve-task-order` only for
diagnostics where deterministic table order is required.
The downloader records `pdf_download_failure_category`,
`pdf_download_failure_categories`, `pdf_download_error`, and
`pdf_download_retry_recommended` in `candidate_papers.parquet`. Retry only
temporary categories such as `rate_limited`, `provider_error`, and `timeout`;
do not repeatedly retry `forbidden`, `not_found`, `non_pdf_response`, or
`weak_pdf_url_only` unless new PDF URLs have been refreshed.

For low-level debugging, the direct downloader and repository-recovery steps can
still be run separately:

```bash
python pipeline/fulltext/download_routed_pdfs.py \
  --limit 25 \
  --alternate-pdf-sources pmc,openalex,semantic_scholar
python pipeline/fulltext/recover_pdf_landing_pages.py \
  --standard-recovery-only \
  --categories forbidden,non_pdf_response,provider_error,timeout,other_download_failure,not_found
python pipeline/fulltext/export_manual_pdf_queue.py
```

For explicit post-direct cleanup of publisher landing pages known to expose
downloadable same-host PDFs, use a named rescue preset instead of making broad
host probing the default retrieval path:

```bash
python pipeline/fulltext/recover_pdf_landing_pages.py \
  --rescue-preset akjournals \
  --apply \
  --rebuild-routes-after
python pipeline/fulltext/export_manual_pdf_queue.py
python pipeline/fulltext/rank_manual_pdf_queue.py
```

For normal-browser click-through recovery, configure Chrome or the save dialog
to write into `data/raw/papers/manual_pdf_inbox/` rather than the general
Downloads folder. Treat article pages as a click-through ladder: first open
controls such as "Article", "Full text", "View article", or "Read article" when
the PDF button is not yet visible, then look for "PDF", "Download PDF", "View
PDF", or the browser PDF-viewer download control. Before importing, triage the
browser output so HTML paywall, cookie, and other non-PDF saves are classified
and moved out of the inbox:

```bash
python pipeline/fulltext/browser_download_triage.py \
  --download-dir data/raw/papers/manual_pdf_inbox \
  --quarantine-non-pdf \
  --apply
python pipeline/fulltext/import_manual_pdfs.py \
  --inbox-dir data/raw/papers/manual_pdf_inbox \
  --apply \
  --move
```

If a manually inspected inbox PDF is known to replace an incorrect canonical
PDF for the same DOI, add `--replace-existing`; the prior canonical file is
backed up under `data/raw/papers/pdf_conflicts/` before replacement.

Visible browser states such as "Get access", "Log in", or "you do not have
access" should be recorded as `no_access_or_paywalled` instead of retried as
PDF downloads.

After importing manual PDFs or adding access/route overrides, rebuild routes,
convert any newly local PDFs, and refresh the manual queue exports:

```bash
python pipeline/extract/build_extraction_routes.py
python pipeline/fulltext/run_local_pdf_conversion_pipeline.py --batch-size 25
python pipeline/fulltext/export_manual_pdf_queue.py
python pipeline/fulltext/rank_manual_pdf_queue.py
```

When manual review confirms that a remaining DOI has no usable open article
PDF, add `manual_access_action=suppress_pdf_download` in
`pipeline/fulltext/manual_fulltext_access_overrides.json` and rebuild routes.
When manual review confirms a record is not an extractable article, add
`manual_action=context_only` in
`pipeline/extract/manual_extraction_route_overrides.json` and rebuild routes.

Rebuild failure categories from recorded download reports and corpus records:

```bash
python pipeline/fulltext/backfill_pdf_failure_categories.py
```

Example recovery pass:

```bash
python pipeline/fulltext/download_routed_pdfs.py \
  --only-failure-categories rate_limited,provider_error,timeout \
  --skip-candidate-statuses downloaded,already_present,manual_import \
  --rate-limit-cooldown-sec 30 \
  --timeout-sec 45 \
  --max-retries 1
```

### Full-Text Conversion

For retained reports with a PMCID but no converted full text and no local PDF,
retrieve reusable PMC XML before treating the record as abstract-only:

```bash
python pipeline/fulltext/fetch_pmc_fulltext_xml.py \
  --progress-every 25 \
  --rps 1.5
```

The script tries the Europe PMC XML endpoint first and then PMC OAI/JATS. It
writes successful XML into the canonical article-text store,
`data/processed/fulltext/articles/`, using the same artifact shape as PDF
conversion. After a real run writes artifacts, it rebuilds
`paper_extraction_routes.parquet` automatically, so successful XML records move
to `full_text_available` and are not kept in the PDF-download queue.

Local PDFs are converted into structured full-text artifacts before article-text
LLM extraction. The default backend is GROBID, which parses scholarly articles
into TEI XML so downstream model inputs can preserve sections, tables, figures,
references, and stable evidence locators.

```bash
python pipeline/fulltext/convert_routed_local_pdfs.py \
  --backend grobid
```

Article text already converted elsewhere can be imported into the canonical
store without converting the PDF again:

```bash
python pipeline/fulltext/consolidate_fulltext_artifacts.py
```

`paper_extraction_routes.parquet` reads converted article text only from
`data/processed/fulltext/articles/<doi_slug>.json`. The old split directories
are migration sources for `consolidate_fulltext_artifacts.py` only; route
building does not use them as fallbacks.

### Article Text Input Preparation

The extraction route table is the source of truth for the next extraction run.
Build route-specific article text inputs from `paper_extraction_routes.parquet`
and the canonical `fulltext/articles/` artifacts:

```bash
python pipeline/fulltext/build_article_text_inputs.py
```

The default section policy keeps primary studies focused on methods/results and
uses all extracted sections for meta-analyses and reviews.

Then build route-specific task records. These records preserve `route_id` as the
stable extraction-job key, because one DOI can have multiple domain-specific
extraction routes.

```bash
python pipeline/extract/build_extraction_tasks.py
```

Before model calls, audit selected article text from the canonical
`fulltext/articles/` store:

```bash
python pipeline/fulltext/audit_article_text_inputs.py \
  --per-strategy 3
```

Route-specific article text builders should use `fulltext_artifact_paths` from
`paper_extraction_routes.parquet` and preserve fields such as
`source_family`, `source_type`, `domain_route`, `access_tier`, `route_action`,
`prompt_profile`, and `schema_profile`. In public explanations, call these
extraction assignments and article text inputs.

Primary-study extraction uses topic-specific tasks built from the extraction
assignments. Meta-analyses and other reviews now use report-centered extraction
paths so a synthesis is interpreted as a whole report rather than as unrelated
topic fragments. The detailed commands and current contracts are documented in
[`pipeline/extract/README.md`](extract/README.md).

Guideline, context-only, and no-extraction assignments are retained for audit
and corpus accounting but are not sent for evidence extraction.

Not every selected report becomes a graph finding. Primary studies,
meta-analyses, and other reviews can each produce candidate findings, but they
remain separate source views and still have to pass validation and
normalization. Guidelines, context-only records, and no-extraction assignments
are retained for corpus accounting rather than graph relationships.

Inspect registered primary-study tasks without model calls:

```bash
python pipeline/extract/run_route_extraction.py \
  --schema-profile primary_evidence_schema \
  --dry-run
```

### Evidence Extraction

Primary studies use topic-specific extraction tasks. Build and run those tasks,
then convert successful results into the shared evidence-row format:

```bash
python pipeline/extract/build_extraction_tasks.py
python pipeline/extract/run_route_extraction.py \
  --input-jsonl data/processed/extraction/route_extraction_tasks.jsonl
python pipeline/kg/convert_routed_extractions_to_evidence_rows.py \
  --use-default-active-route-table
```

Meta-analyses use `build_meta_analysis_v2_tasks.py`,
`run_meta_analysis_v2_batch_api.py`, and
`convert_meta_analysis_v2_to_evidence_rows.py`. Other reviews use
`build_review_relationship_tasks.py`, the review relationship runner, and
`convert_review_relationship_bundles_to_evidence_rows.py`. These paths preserve
pooled estimates and review-level relationships separately from primary-study
findings.

Before building a graph release, assemble the complete accepted primary,
meta-analysis, and review layers into one explicit evidence snapshot. Do not let
a small retry or correction replace an unaffected evidence family. Then build a
versioned release without activating it:

```bash
scripts/build_routed_kg_payload.sh "$RUN_ID"
```

After review, publish the already-built release with the guarded promoter:

```bash
python pipeline/publish/promote_routed_run.py --run-id "$RUN_ID"
```

Promotion stages the release's final decisions into `candidate_papers.parquet`,
validates the complete ledger, generates the Methods selection flow and full
bibliography only from that staged ledger, and then refreshes the corpus, active
graph pointers, Methods outputs, and `dist/` site bundle together. For
corrections to selected reports, use the scoped updater described at the start
of this guide; it applies the same publication safeguards.

## Canonical Outputs

- `data/raw/doi_queue.<dataset>.discovered.txt`
- source/provider discovery reports under `data/raw/search_strategies/` and
  `data/processed/`
- `data/processed/corpus/candidate_papers.parquet`
- `data/processed/corpus/candidate_contexts.parquet`
- `data/processed/corpus/candidate_sources.parquet`
- `data/processed/corpus/paper_metadata_enrichment.parquet`
- `data/processed/corpus/paper_prescreen_decisions.parquet`
- `data/processed/corpus/paper_domain_routing_gemini.parquet`
- `data/processed/corpus/paper_extraction_routes.parquet`
- `data/processed/fulltext/articles/*.json`
- article text inputs under `data/processed/extraction/`
- versioned extraction outputs and assembled evidence snapshots under
  `data/processed/extraction/`
- checked graph releases under `data/processed/kg_routed_runs/<RUN_ID>/`
- compact graph and detail files under
  `data/processed/graph_payload_runs/<RUN_ID>/`
- the active extraction and public-graph release records at
  `data/processed/extraction/active_routed_run.json` and
  `data/processed/graph_payload_active.json`
- generated Methods flow and bibliography files under `data/kg/views/`
- the deployable public site under `dist/`

## Run Labels

Use run labels to separate artifacts from different searches or batches:

- Good labels describe the run: `grouped_search_2026_05`,
  `direct_pairs_2026_05`, `monthly_update_2026_06`.
- Do not use run labels as public method names.

## Corpus Tables

`data/processed/corpus/` contains the current table-based corpus. Downstream
steps should query these tables instead of large JSON snapshots.

The raw run reports remain append-only provenance. The files under
`data/processed/extraction/` are current views regenerated from corpus tables
and full-text artifacts.

Current corpus storage direction: use structured Parquet tables for records,
contexts, source/provenance events, and metadata enrichment. Later, load those
tables into Postgres for website search, API queries, and MCP-facing
record, report, and KG access.

Build the current candidate corpus tables:

```bash
python pipeline/validate/build_context_provenance_audit.py \
  --table-out-dir data/processed/corpus
```

This writes `candidate_papers.parquet`, `candidate_contexts.parquet`,
`candidate_sources.parquet`, and `candidate_corpus_manifest.parquet`.

## Local Config

Keep credentials in the ignored local config:

```bash
cp pipeline/config.local.example.yaml pipeline/config.local.yaml
chmod 600 pipeline/config.local.yaml
```

Common settings:

- `openalex.api_key`
- `pubmed.email`
- `pubmed.api_key`
- `crossref.email`
- `unpaywall.email`
- `semantic_scholar.api_key`

Scripts that use `pipeline/config.example.yaml` automatically overlay
`pipeline/config.local.yaml` when it exists.
