# Extract

This stage prepares routed papers for structured evidence extraction, then
promotes curated-ready extracted evidence into the graph inputs.

## Routing-Aware Extraction Routes

The table-native extraction handoff starts from the retained corpus rather than
the older dataset-specific extraction files. Build one row per DOI plus
extraction task:

```bash
python pipeline/extract/build_extraction_routes.py
```

Default outputs:

- `data/processed/corpus/paper_extraction_routes.parquet`
- `data/processed/corpus/paper_extraction_routes_summary.json`
- `data/processed/corpus/paper_extraction_routes_counts.csv`

The route table joins deterministic pre-screen decisions, metadata, Gemini
paper-type and domain routing, converted full-text artifacts, valid PDFs in
`data/raw/papers/pdfs/`, and PDF URL availability.
Each row includes the paper source family, source type, domain route, access
tier, route action, prompt profile, schema profile, priority, confidence, and
basis. If no model-assigned domain table is supplied, papers stay on coarse
fallback routes by access tier.

Preprint and unpublished posted-content records are excluded upstream by the
deterministic pre-screen stage. The route builder treats the pre-screen table as
the authority for whether a DOI is retained; stale domain-routing rows cannot
revive a DOI that pre-screen excluded.

The route build writes DOI-level status back into
`data/processed/corpus/candidate_papers.parquet` unless
`--no-update-candidate-table` is used. This keeps the candidate table as the
main corpus ledger: one row per DOI with publication stage, preprint flags,
prescreen status, paper type, extraction-route status, route counts, domain
summaries, prompt/schema profiles, and the best available text tier.
Detailed per-domain extraction rows remain in `paper_extraction_routes.parquet`.

Access tiers are not evidence-quality labels. They describe the next file
handling step:

- `full_text_available` -> `extract_from_full_text`
- `local_pdf_available` -> `convert_local_pdf_then_extract`
- `pdf_download_url_available` -> `download_pdf_then_extract`
- `abstract_only` -> `extract_from_abstract_only`

Build the Gemini routing table first, then pass it explicitly:

```bash
python pipeline/extract/build_extraction_routes.py \
  --domain-routing-table data/processed/corpus/paper_domain_routing_gemini.parquet
```

Use this table to audit extraction queues before model calls. The prompt and
schema profile labels are route assignments; route-specific model inputs and
schemas are built downstream from this table.

## Route Extraction Tasks

`route_id` is the stable unit for extraction. A DOI can have several route rows
when the same paper should be extracted for different evidence domains, so
downstream model runs should track `route_id`/`task_id` rather than DOI alone.

Build route-aware task records:

```bash
python pipeline/extract/build_extraction_tasks.py
```

Default outputs:

- `data/processed/extraction/route_extraction_tasks.jsonl`
- `data/processed/extraction/route_extraction_tasks_report.json`

Each task records the paper metadata, route context, selected prompt/schema,
expected output family, text source, and model-run status. Article-text routes
are marked `ready_for_model` only when a compatible article text input is
available. Otherwise they remain in the task file as `needs_fulltext_packet` or
`needs_expected_fulltext_packet` so missing text inputs are visible.

Route-aware extraction defaults to Gemini 3 Flash preview for article-text and
abstract-only tasks:

```bash
GEMINI_ROUTE_EXTRACTION_MODEL=gemini-3-flash-preview
GEMINI_ABSTRACT_EXTRACTION_MODEL=gemini-3-flash-preview
GEMINI_ARTICLE_TEXT_EXTRACTION_MODEL=gemini-3-flash-preview
```

The route-aware runner also defaults to `--thinking-budget 0`. Override
`--model` or `--thinking-budget` only for deliberate comparison runs.

Section selection strategies are route-specific:

- primary evidence routes -> primary study article text
- `secondary_meta_analysis` -> meta-analysis article text
- structured/narrative review routes -> review article text
- terminal no-model routes -> no article text input

Internally, current JSON files still call these `packet_profile` values:
`primary_empirical`, `secondary_synthesis`, `review_coverage`, and
`not_applicable`. Treat those as compatibility field values. `lean_primary` is
accepted only as a deprecated alias for `primary_empirical`.

## Route-Specific Extraction Schemas

Route profiles are registered with one of three statuses:

- `runnable`: detailed enough for normal model pilots.
- `scaffold`: schema and prompt shell exist, but the profile should be tuned
  before production-scale model calls.
- `terminal_no_model`: route is retained for audit/accounting but is not sent to
  an extraction model.

The primary KG extraction target is original empirical evidence. Primary
profiles are runnable and share:

- domain schemas under `schema/extraction_profiles/primary/`
- `docs/extraction_profiles/paper_type/primary_article_text.md`
- `docs/extraction_profiles/paper_type/primary_abstract_only.md`

Use these for `schema_profile=primary_evidence_schema`. Domain addenda under
`docs/extraction_domains/` are appended automatically from `domain_route`.
Primary extraction produces KG evidence candidates from original study results;
it is the first route family to pilot.

The route-specific meta-analysis contract is also runnable, but it is a
secondary layer:

- domain schemas under `schema/extraction_profiles/meta_analysis/`
- shared base schema at `schema/meta_analysis_evidence.schema.json`
- `docs/extraction_profiles/paper_type/meta_analysis_article_text.md`
- `docs/extraction_profiles/paper_type/meta_analysis_abstract_only.md`

Use this for `prompt_profile=secondary_meta_analysis` and
`schema_profile=meta_analysis_evidence_schema`. The runner selects the meta-analysis
domain schema from `domain_route`; text depth selects the prompt and is injected
as output provenance. The shared domain schema can hold meta-analysis scope,
aggregate included evidence summaries, pooled or network synthesis results, and
domain-specific result details. Abstract-only prompts ask the model to fill only
what is visible in the abstract and leave unavailable fields empty.
Meta-analysis extraction does not create primary-study graph findings.

## Article Text Inputs And Audits

Build article text inputs from the route table and the canonical
`fulltext/articles/` artifacts:

```bash
python pipeline/fulltext/build_article_text_inputs.py
```

The default section policy is primary-study selection for primary evidence
routes, and all extracted article sections for meta-analyses and reviews. This
keeps primary studies focused on methods/results while avoiding brittle section
filtering for secondary literature.

Default outputs:

- `data/processed/extraction/fulltext_packets.jsonl`
- `data/processed/extraction/article_text_inputs_report.json`
- `data/processed/extraction/article_text_inputs_audit.csv`
- `data/processed/extraction/article_text_inputs_audit.md`

After article text inputs have been built, rebuild route tasks:

```bash
python pipeline/extract/build_extraction_tasks.py
```

Before model calls, audit a small sample of the article text selected by each
section selection strategy:

```bash
python pipeline/fulltext/audit_article_text_inputs.py \
  --per-strategy 3
```

Default outputs:

- `data/processed/extraction/article_text_input_audit_report.json`
- `data/processed/extraction/article_text_input_audit.csv`
- `data/processed/extraction/article_text_input_audit.md`
- `data/processed/extraction/article_text_input_audit_sample.jsonl`

By default the audit uses `fulltext_artifact_paths` from the route table. Use
`--artifact-dir <final-extracted-text-dir>` only when deliberately overriding
those paths. This audit does not call a model.

Audit primary readiness before running extraction:

```bash
python pipeline/extract/audit_primary_extraction_readiness.py
```

Default outputs:

- `data/processed/extraction/primary_extraction_readiness_report.json`
- `data/processed/extraction/primary_extraction_readiness.csv`

The audit is no-model. It counts primary tasks by domain, prompt profile,
model-run status, access tier, text mode, expected section selection strategy,
actual article text input strategy, and compatibility status.

Dry-run primary extraction before making model calls:

```bash
python pipeline/extract/run_route_extraction.py \
  --input-jsonl data/processed/extraction/route_extraction_tasks.jsonl \
  --schema-profile primary_evidence_schema \
  --dry-run
```

The runner processes registered model-runnable route profiles only. Unsupported
terminal routes are never sent to the model. Use profile filters when you want a
dry run for a specific family:

```bash
python pipeline/extract/run_route_extraction.py \
  --input-jsonl data/processed/extraction/route_extraction_tasks.jsonl \
  --schema-profile review_coverage_schema \
  --dry-run
```

For the actual accumulating extraction, use the batch wrapper. It appends each
batch to a named routed extraction run, converts all accumulated outputs for that
run into evidence rows, and rebuilds versioned KG tables for that run. It does
not overwrite `data/processed/kg/`.

```bash
RUN_ID=gemini3_flash_20260628_routed_extraction
python pipeline/extract/run_routed_extraction_batch.py \
  --run-id "$RUN_ID" \
  --batch-size 100 \
  --shuffle \
  --seed 1
```

The same command can be rerun with the same `RUN_ID`; tasks already attempted in
that run are skipped. Use `--dry-run` first to inspect the selected tasks without
calling Gemini. Outputs accumulate under:

- `data/processed/extraction/routed_runs/<RUN_ID>/`
- `data/processed/kg_routed_runs/<RUN_ID>/`

Audit meta-analysis readiness before running extraction:

```bash
python pipeline/extract/audit_meta_analysis_extraction_readiness.py
```

Default outputs:

- `data/processed/extraction/meta_analysis_extraction_readiness_report.json`
- `data/processed/extraction/meta_analysis_extraction_readiness.csv`

The audit is no-model. It counts meta-analysis route tasks by readiness,
access tier, text mode, expected section selection strategy, actual article text
input strategy, and compatibility status.

## KG Evidence vs Audit Routes

Route categories are not all KG evidence categories. Keep these distinctions
explicit:

- `primary_*` profiles are KG evidence candidates. They extract original
  empirical findings that may later become compound-target, compound-disorder,
  endpoint, mechanism, or domain-specific evidence tables after deterministic
  normalization.
- `secondary_meta_analysis` extracts synthesis evidence. These rows should stay
  separate from primary-study graph claims. They can support evidence-synthesis
  views, certainty summaries, and later KG overlays.
- `secondary_structured_review`, `secondary_narrative_review`, and
  `secondary_review_coverage` are in-scope coverage routes, not primary KG
  evidence. They describe what a review covers, summarizes, or identifies as
  uncertain.
- `guideline_consensus` is an in-scope recommendation/context route when the
  paper is relevant, but it is not extracted into the KG for now.
- `context_only_or_skip` is for papers that may be useful for provenance,
  background, protocol tracking, commentary, or manual audit, but should not
  create KG evidence.
- `no_extraction` is a terminal audit route for records excluded before
  extraction, usually after domain screening. It means the paper was seen and
  intentionally did not enter evidence extraction.

In short: some documents are in scope for corpus accounting or evidence-map
context without being part of the main KG. Do not treat a route-table row as a
KG contribution unless its profile family is intended to produce evidence rows.

## PDF Retrieval For Routed Papers

PDF retrieval for `download_pdf_then_extract` rows is handled by the table-native
downloader:

```bash
python pipeline/fulltext/download_routed_pdfs.py
```

It writes active PDFs to `data/raw/papers/pdfs/` and updates the corpus table;
rerun `build_extraction_routes.py` afterward so newly available PDFs move to
the local-PDF/full-text path. Failed downloads are categorized so recovery runs
can target temporary failures (`rate_limited`, `provider_error`, `timeout`)
without repeatedly retrying blocked, stale, or non-PDF URLs.
The route table separates probable direct PDF URLs from weaker landing-page or
repository links. Only probable PDF endpoints enter the default automated
download route; weaker links are retained for refreshed link discovery or manual
download checks.

## Manual Route Overrides

Manual extraction-route review is stored as a small DOI-level input file:

- `pipeline/extract/manual_extraction_route_overrides.json`
- `pipeline/fulltext/manual_fulltext_access_overrides.json`

The route builder applies these files by default. Use them only for reviewed
edge cases where the automated route or access signal is too broad or clearly
wrong:

- `manual_action=context_only` keeps the paper in the route table for audit but
  removes it from extraction candidates.
- `manual_action=route_domains` replaces a broad route with specific domain
  routes such as `clinical_outcome`, `safety_tolerability`, or
  `molecular_target`.
- `manual_access_action=suppress_pdf_download` suppresses a misleading
  probable-PDF URL and lets a retained paper fall back to abstract extraction
  when manual review confirms there is no usable open PDF.

The generated route table records these rows with
`domain_routing_model=manual_extraction_route_review` or
`manual_fulltext_access_action`. The CSV audit files under
`data/processed/corpus/audits/` are inspection outputs, not durable pipeline
inputs.

## Retired Extraction V1 Path

The older extraction-v1 pilot, Gemini runner, batch queue, QA, projection,
projected-claim normalization, rerun promotion, and split graph-payload export
path has been removed. Use route-native extraction tasks
(`build_extraction_tasks.py`), `run_route_extraction.py` or routed batch
runners, `convert_routed_extractions_to_evidence_rows.py`, and parquet KG
tables instead.

## Retired Manifest-Based Extraction Prep

The older corpus-manifest and dataset-specific candidate-file handoff has been
removed. Use `paper_extraction_routes.parquet`, route-specific article text
inputs, `build_extraction_tasks.py`, and route-native extraction outputs
instead.

## Retired Stub Promotion

The older path that promoted curated-ready rows from
`data/processed/*_claim_stubs.json` into curated JSON/CSV datasets has been
removed. Build route-native evidence rows and parquet KG tables instead.
