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

Current JSON files use these `packet_profile` values:
`primary_empirical`, `secondary_synthesis`, `review_coverage`, and
`not_applicable`.

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

The current paper-level meta-analysis contract is:

- `docs/extraction_profiles/meta_analysis_v2/full_text_extraction.md`
- `docs/extraction_profiles/meta_analysis_v2/abstract_extraction.md`
- `schema/meta_analysis_evidence_v2.schema.json`

This v2 contract records the paper's main synthesis questions and results. Each
result has explicit nullable population, intervention or exposure, comparator,
outcome or entity, and time-window fields. It also includes reported effect
estimates, uncertainty intervals, p values, evidence counts,
heterogeneity, network-meta-analysis details, risk of bias, certainty, and
publication-bias assessments. Optional fields are omitted when the supplied
paper does not report them.

The v2 pilot path is paper-level and isolated from the live routed
meta-analysis extraction. Build one task per retained meta-analysis with:

```bash
python pipeline/extract/build_meta_analysis_v2_tasks.py
```

Prepare a reproducible 100-paper asynchronous pilot with 50 article-text and
50 abstract-only tasks:

```bash
python pipeline/extract/run_meta_analysis_v2_batch_api.py prepare \
  --run-id meta_analysis_v2_pilot_100 \
  --batch-id batch_001 \
  --batch-size 100 \
  --full-text-count 50 \
  --shuffle \
  --seed 20260712
```

Submit and monitor the prepared batch:

```bash
python pipeline/extract/run_meta_analysis_v2_batch_api.py submit \
  --run-id meta_analysis_v2_pilot_100 \
  --batch-id batch_001

python pipeline/extract/run_meta_analysis_v2_batch_api.py status \
  --run-id meta_analysis_v2_pilot_100 \
  --batch-id batch_001
```

Download and parse it after the job succeeds:

```bash
python pipeline/extract/run_meta_analysis_v2_batch_api.py download \
  --run-id meta_analysis_v2_pilot_100 \
  --batch-id batch_001

python pipeline/extract/run_meta_analysis_v2_batch_api.py parse \
  --run-id meta_analysis_v2_pilot_100 \
  --batch-id batch_001
```

The parsed record envelope adds `schema_version`, `source_depth`, source
fingerprint, model, and task identity deterministically. The model receives
only the fields defined in `schema/meta_analysis_evidence_v2.schema.json`.
Human-readable schema descriptions are removed from the API request because
the prompt already supplies those instructions and Gemini's structured-output
validator rejects the more verbose full-text schema. The saved schema and input
snapshot retain the descriptions.
The existing routed meta-analysis path remains the live production path until
the v2 pilot has been reviewed.

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

## Main review extraction path

The review pipeline extracts one final relationship bundle per paper. It does
not create one extraction task per routed domain. The model first identifies
the paper's purpose and major aspects, then extracts the paper-defining,
major-supporting, and useful secondary relationships. Domain labels are added
to those relationships afterward, inside the same model response.

Full-text and abstract-only reviews use separate prompts because their evidence
boundaries differ, but both use the same output schema and require one model
call per paper. There is no automatic discovery pass, reconciliation pass, or
repair call.

By default, the task builder selects retained `review`, `systematic_review`,
`scoping_review`, `narrative_review`, `literature_review`, and
`umbrella_review` papers directly from `candidate_papers.parquet`. It includes
papers with verified article text or an abstract and reports papers whose
source is not ready. Meta-analyses continue to use their quantitative synthesis
profile; guidelines and consensus statements remain separate.

Build the production task list:

```bash
python pipeline/extract/build_review_relationship_tasks.py
```

Inspect the model-call plan without calling Gemini:

```bash
python pipeline/extract/run_review_relationship_extraction.py \
  --run-id review_relationships_v2 \
  --dry-run
```

Run extraction with a named run ID:

```bash
python pipeline/extract/run_review_relationship_extraction.py \
  --run-id review_relationships_v2
```

For a larger asynchronous run, prepare and submit the same paper-centered
requests through Gemini's Batch API:

```bash
python pipeline/extract/run_review_relationship_batch_api.py prepare \
  --run-id review_relationships_v2_main \
  --batch-id batch_001 \
  --batch-size 250 \
  --shuffle \
  --seed 1

python pipeline/extract/run_review_relationship_batch_api.py submit \
  --run-id review_relationships_v2_main \
  --batch-id batch_001
```

When the job has finished, download and parse it:

```bash
python pipeline/extract/run_review_relationship_batch_api.py status \
  --run-id review_relationships_v2_main \
  --batch-id batch_001

python pipeline/extract/run_review_relationship_batch_api.py download \
  --run-id review_relationships_v2_main \
  --batch-id batch_001

python pipeline/extract/run_review_relationship_batch_api.py parse \
  --run-id review_relationships_v2_main \
  --batch-id batch_001
```

The runner resumes a named run by skipping papers already recorded with an
`ok` result. Use `--overwrite` only to restart that run from the beginning.
Each run archives the exact full-text prompt, abstract prompt, schema, task
list, model name, and generation settings under `input_snapshot/` before any
model call.

Project the bundles without dropping classes, combinations, interactions, or
unmapped anchors:

```bash
python pipeline/kg/project_review_relationship_bundles.py
```

The extraction run and projection remain separate from the active KG until the
results have been checked. The routed primary-study and meta-analysis paths are
unchanged.

The manually read 50-paper comparison tool remains available for evaluation:

```bash
python pipeline/validate/compare_review_relationships_to_manual_gold.py
```

The older paper-complete routed evaluation below remains a historical baseline,
not the production review extraction design.

### Routed paper-complete review baseline

The normal batch runner selects paper-domain tasks independently. For an
evaluation where every selected review must be extracted across all of its
current routed domains, build a paper-complete cohort first:

```bash
python pipeline/extract/build_review_paper_complete_evaluation.py \
  --cohort-id review_paper_complete_50_20260711 \
  --cohort-size 50 \
  --seed 20260711 \
  --include-doi 10.3389/fphar.2021.749068
```

The cohort builder is review-only. It does not change primary-study routing or
the active KG. It exports every ready review task for each selected DOI plus
paper- and relationship-level annotation templates under
`data/processed/evaluation/<cohort-id>/`.

Pass the cohort's task JSONL to the existing Batch API runner. Use a separate
run ID so parsing and KG projection remain isolated:

```bash
python pipeline/extract/run_route_extraction_batch_api.py prepare \
  --run-id gemini3_flash_20260711_review_eval50 \
  --batch-id batch_001 \
  --input-jsonl data/processed/evaluation/review_paper_complete_50_20260711/route_extraction_tasks.jsonl \
  --batch-size 500 \
  --schema-profile review_coverage_schema \
  --include-legacy-review-routes \
  --model gemini-3-flash-preview
```

After downloading and parsing the batch, combine all domain outputs into one QA
bundle per paper:

```bash
python pipeline/extract/build_review_paper_complete_bundles.py \
  --cohort-jsonl data/processed/evaluation/review_paper_complete_50_20260711/cohort.jsonl \
  --outputs-jsonl data/processed/extraction/routed_runs/gemini3_flash_20260711_review_eval50/route_extraction_outputs.jsonl \
  --out-dir data/processed/evaluation/review_paper_complete_50_20260711/results
```

The bundle report checks paper/domain completeness, inventory-to-coverage-item
links, and peripheral coverage rows before any decision to publish the results.

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
