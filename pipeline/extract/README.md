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

The runner currently processes registered route profiles only. Unsupported
terminal routes are never sent to the model. Review coverage profiles remain
scaffolded and are skipped by default; include them only for deliberate local
pilots:

```bash
python pipeline/extract/run_route_extraction.py \
  --input-jsonl data/processed/extraction/route_extraction_tasks.jsonl \
  --schema-profile review_coverage_schema \
  --include-scaffold-profiles \
  --dry-run
```

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

## Older Manifest-Based Prepare Extraction Inputs

This path is retained for first-generation extraction runs that still use the
corpus manifest and dataset-specific candidate files. The current route-aware
workflow should use `paper_extraction_routes.parquet` as the extraction source.

After literature discovery, abstract screening, PDF retrieval, and full-text
conversion, the older path builds the DOI-level extraction cohort:

```bash
python pipeline/extract/prepare_extraction_inputs.py --dataset all
```

By default this reads `data/processed/corpus_manifest.json`, combines screened
`relevant` and `uncertain` papers across all included screening reports,
deduplicates by DOI, and writes:

- `data/processed/extraction/*_extraction_candidates.jsonl`
- `data/processed/extraction/*_extraction_candidates.csv`
- `data/raw/doi_queue.*.extraction_candidates.txt`
- `data/raw/doi_queue.*.extraction_fulltext_ready.txt`
- `data/raw/doi_queue.*.extraction_abstract_only.txt`
- `data/processed/extraction/extraction_readiness_report.json`
- `data/processed/extraction/extraction_readiness_report.md`

To include a new literature update, add its completed abstract-screening report
to `data/processed/corpus_manifest.json` and rerun this command. Do not edit the
candidate files by hand; they are regenerated views of the manifest and paper
library.

Then build clean primary-study article text input files for the papers that
already have converted full text:

```bash
python pipeline/fulltext/build_llm_evidence_packets.py \
  --dataset mechanistic \
  --doi-file data/raw/doi_queue.mechanistic.extraction_fulltext_ready.txt \
  --out-jsonl data/processed/extraction/mechanistic_fulltext_packets.jsonl \
  --report-json data/processed/extraction/mechanistic_fulltext_packets_report.json \
  --omit-section-text \
  --omit-candidate-contexts \
  --section-selection-strategy primary_study \
  --max-references 0

python pipeline/fulltext/build_llm_evidence_packets.py \
  --dataset disorder \
  --doi-file data/raw/doi_queue.disorder.extraction_fulltext_ready.txt \
  --out-jsonl data/processed/extraction/disorder_fulltext_packets.jsonl \
  --report-json data/processed/extraction/disorder_fulltext_packets_report.json \
  --omit-section-text \
  --omit-candidate-contexts \
  --section-selection-strategy primary_study \
  --max-references 0
```

The `--omit-candidate-contexts` flag keeps previous claim/context hints out of
the extraction inputs. The extraction model should infer findings from the paper
text itself. The primary study section selection strategy keeps title/abstract
metadata, methods/results-like chunks, tables, and marker-matched
mechanistic/clinical sections while dropping most discussion, conclusion,
references, and secondary-review body text.

## Extraction V1 Pilot

Before scaling the frontier-model extraction pass, build a deterministic pilot
set that covers full-text, abstract-only, relevant, and uncertain rows:

```bash
python pipeline/extract/build_extraction_v1_pilot.py --dataset all --per-bucket 10
```

Papers previously marked `irrelevant` are excluded from Gemini extraction by
default. For a deliberate calibration run with old negative controls, add
`--include-irrelevant-controls`; do not use that flag for normal extraction
scaling.

To build a fresh, non-overlapping pilot after an earlier run, pass the earlier
pilot JSONL as an exclusion list:

```bash
python pipeline/extract/build_extraction_v1_pilot.py \
  --dataset all \
  --per-bucket 5 \
  --exclude-jsonl data/processed/extraction/extraction_v1_pilot_inputs.50.jsonl \
  --exclude-meta-analyses \
  --out-jsonl data/processed/extraction/extraction_v1_pilot_inputs.50b.jsonl \
  --out-csv data/processed/extraction/extraction_v1_pilot_inputs.50b.csv \
  --report-json data/processed/extraction/extraction_v1_pilot_report.50b.json
```

Use `--exclude-meta-analyses` for the normal v1 primary/secondary coverage
extraction stream. It filters metadata-detected meta-analyses and mega-analyses
before Gemini calls, writes them to a sibling `*.excluded.jsonl` file, and
reserves them for a later evidence-synthesis extraction schema.

Default outputs:

- `data/processed/extraction/extraction_v1_pilot_inputs.jsonl`
- `data/processed/extraction/extraction_v1_pilot_inputs.csv`
- `data/processed/extraction/extraction_v1_pilot_report.json`

The pilot records point to the shared prompt at
`docs/extraction_v1_prompt.md`, dataset addenda at
`docs/extraction_v1_mechanistic_prompt.md` and
`docs/extraction_v1_disorder_prompt.md`, `docs/extraction_v1_protocol.md`, and
`schema/extraction_v1.schema.json`. By default, the runner sends Gemini an
inlined dataset-specific schema view through native `response_json_schema` mode
while still validating parsed outputs against the full canonical schema. Use
`--schema-mode prompt` to fall back to prompt-embedded schema text, or
`--schema-mode both` for debugging. Full-text records embed the article text
input by default so the same JSONL can be sent to the model. Use
`--omit-fulltext-packet-content` for a lightweight inspection file.

Each pilot record includes a deterministic `route_hint` derived from
publication type, title, registry IDs, MeSH terms, and abstract phrases. The
model may override this hint, but it helps keep secondary/context literature
from being converted into primary evidence findings.

Run a Gemini pilot after setting `GEMINI_API_KEY` in the project-local `.env`:

```bash
python pipeline/extract/run_gemini_extraction_v1.py \
  --input-jsonl data/processed/extraction/extraction_v1_pilot_inputs.jsonl \
  --out-jsonl data/processed/extraction/extraction_v1_outputs.jsonl \
  --raw-jsonl data/processed/extraction/extraction_v1_gemini_raw.jsonl \
  --report-json data/processed/extraction/extraction_v1_gemini_report.json \
  --thinking-budget 0 \
  --limit 50 \
  --overwrite
```

For Gemini 2.5 Flash, omit `--thinking-budget` to use the model/API default
dynamic thinking, use `--thinking-budget -1` to request dynamic thinking
explicitly, or use `--thinking-budget 0` to disable thinking for lower-cost
bulk extraction. JSON repair calls default to `--json-repair-thinking-budget 0`
because repair is syntax-focused.

### Gemini Batch API

For larger, non-urgent extraction runs, use Gemini Batch API instead of the
synchronous runner. Batch mode keeps the same prompt/schema contract but submits
requests asynchronously through an uploaded JSONL file. Omit `--thinking-budget`
to keep Gemini 2.5 Flash on its default dynamic thinking behavior.

Prepare a batch request file:

```bash
python pipeline/extract/run_gemini_extraction_v1_batch.py prepare \
  --input-jsonl data/processed/extraction/extraction_v1_pilot_inputs.batch_300.jsonl \
  --batch-input-jsonl data/processed/extraction/extraction_v1_batch_requests.batch_300.jsonl \
  --manifest-json data/processed/extraction/extraction_v1_batch_manifest.batch_300.json
```

Submit it:

```bash
python pipeline/extract/run_gemini_extraction_v1_batch.py submit \
  --batch-input-jsonl data/processed/extraction/extraction_v1_batch_requests.batch_300.jsonl \
  --manifest-json data/processed/extraction/extraction_v1_batch_manifest.batch_300.json \
  --job-json data/processed/extraction/extraction_v1_batch_job.batch_300.json \
  --display-name psychedelics-kg-extraction-batch-300
```

Check or wait for completion:

```bash
python pipeline/extract/run_gemini_extraction_v1_batch.py status \
  --job-json data/processed/extraction/extraction_v1_batch_job.batch_300.json

python pipeline/extract/run_gemini_extraction_v1_batch.py wait \
  --job-json data/processed/extraction/extraction_v1_batch_job.batch_300.json \
  --poll-interval-sec 60
```

After the job reaches `JOB_STATE_SUCCEEDED`, download and parse results into the
same extraction-v1 output format used by the synchronous runner:

```bash
python pipeline/extract/run_gemini_extraction_v1_batch.py download \
  --job-json data/processed/extraction/extraction_v1_batch_job.batch_300.json \
  --batch-output-jsonl data/processed/extraction/extraction_v1_batch_results.batch_300.jsonl

python pipeline/extract/run_gemini_extraction_v1_batch.py parse \
  --batch-output-jsonl data/processed/extraction/extraction_v1_batch_results.batch_300.jsonl \
  --manifest-json data/processed/extraction/extraction_v1_batch_manifest.batch_300.json \
  --out-jsonl data/processed/extraction/extraction_v1_outputs.batch_300.jsonl \
  --raw-jsonl data/processed/extraction/extraction_v1_batch_raw.batch_300.jsonl \
  --report-json data/processed/extraction/extraction_v1_batch_parse_report.batch_300.json
```

Then run the usual QA, projection, normalization, and payload export steps on
`extraction_v1_outputs.batch_300.jsonl`. Batch creation is not idempotent: do
not re-run `submit` for the same request file unless you intentionally want a
second paid batch job.

The runner first parses Gemini output strictly, then applies small local JSON
cleanup such as code-fence removal, object extraction, and trailing-comma
removal. If parsing still fails, it makes one repair request to Gemini by
default and records `json_repair_method`, `response_text`, and
`repair_response_text` in the raw JSONL. `json_repair_method` is `not_needed`,
`local_cleanup`, or `model_repair`. Use `--disable-json-repair` to turn off the
repair call.

After parsing, the runner applies deterministic schema cleanup for predictable
model slips: JSON nulls become empty strings, primary-evidence coverage mentions
are dropped, compound-target `result_direction` is normalized to
`not_applicable`, abstract-only `text` evidence locations become `abstract`, and
commentary/protocol-like secondary outputs are routed to `context_only`. Raw
checkpoint rows record these as `normalization_changes`.

After model outputs are available, validate the extraction JSONL and verify
supporting quotes against the pilot/input context:

```bash
python pipeline/extract/qa_extraction_v1_outputs.py \
  --input-jsonl data/processed/extraction/extraction_v1_outputs.jsonl \
  --pilot-input-jsonl data/processed/extraction/extraction_v1_pilot_inputs.jsonl
```

Default QA outputs:

- `data/processed/extraction/extraction_v1_qa_report.json`
- `data/processed/extraction/extraction_v1_qa_rows.csv`

For graph ingestion, project valid extraction outputs into canonical graph-claim
rows without mutating the legacy curated files. The projection step also
validates input rows against `schema/extraction_v1.schema.json` and skips
invalid inputs:

```bash
python pipeline/extract/project_extraction_v1_claims.py \
  --input-jsonl data/processed/extraction/extraction_v1_outputs.jsonl \
  --pilot-input-jsonl data/processed/extraction/extraction_v1_pilot_inputs.jsonl
```

Default projection outputs:

- `data/processed/extraction/mechanistic_claims.json`
- `data/processed/extraction/mechanistic_claims.csv`
- `data/processed/extraction/disorder_claims.json`
- `data/processed/extraction/disorder_claims.csv`
- `data/processed/extraction/projection_report.json`

These projected extraction claim files feed the normalized KG evidence tables
and remain available as explicit comparison sources for the main-page graph
payload export. Use `--prefix some_label` for a comparison or calibration
projection that should not replace the canonical extraction claim files.

### Promote a DOI-Level Rerun

When a subset of papers is rerun with an improved prompt/schema, promote the
successful rerun outputs into the active extraction JSONL before projection.
This prevents duplicate DOI records and gives later projection, normalization,
KG, and UI payload steps a single source of truth.

Dry run first:

```bash
python pipeline/extract/promote_extraction_rerun.py \
  --rerun-output-jsonl data/processed/extraction/extraction_v1_outputs.some_rerun_tag.jsonl \
  --rerun-pilot-input-jsonl data/processed/extraction/extraction_v1_pilot_inputs.some_rerun_tag.jsonl
```

Apply after checking the report:

```bash
python pipeline/extract/promote_extraction_rerun.py \
  --rerun-output-jsonl data/processed/extraction/extraction_v1_outputs.some_rerun_tag.jsonl \
  --rerun-pilot-input-jsonl data/processed/extraction/extraction_v1_pilot_inputs.some_rerun_tag.jsonl \
  --report-json data/processed/extraction/extraction_v1_promote_rerun_report.some_rerun_tag.json \
  --apply
```

Successful rerun rows replace active rows by normalized `(dataset, DOI)`.
Rerun records that failed parsing are absent from the rerun output JSONL, so
they do not delete the older active row; keep their input rows in the retry
queue until a successful replacement exists.

The mechanistic projection is intentionally broad for inspection. It includes
supported, uncertain, not-supported, and review-needed primary-evidence claims
and does not require numeric affinity fields. The old strict affinity schema is
kept separately as `schema/legacy_mechanistic_affinity_claims.schema.json`;
the old disorder schema is similarly preserved as
`schema/legacy_disorder_claims.schema.json` for legacy exports.

## Normalize Graph Candidates

Projection keeps the extraction broad so we can inspect everything the model
found. Before those rows become clean graph edges, run the deterministic
normalization layer:

```bash
python pipeline/extract/normalize_extraction_claims.py
```

The normalizer reads the projected claim files, checks only
`graph_include_candidate=true` rows against `data/curated/entity_registry.json`,
and writes:

- `data/processed/extraction/mechanistic_graph_claims.json`
- `data/processed/extraction/mechanistic_graph_claims.csv`
- `data/processed/extraction/disorder_graph_claims.json`
- `data/processed/extraction/disorder_graph_claims.csv`
- `data/processed/extraction/mechanistic_normalization_audit.json`
- `data/processed/extraction/disorder_normalization_audit.json`
- `data/processed/extraction/normalization_report.json`

The audit files keep every projected claim with a normalization status such as
`normalized`, `not_graph_candidate`, `entity_unmapped`,
`compound_unmapped`, or `non_graph_entity_role`. The graph-claim files include
only rows where both the compound and graph endpoint matched the local entity
registry. Use `--prefix some_label` for targeted tests that should not replace
the canonical normalized graph files.

The main graph exporter can read these clean graph rows with:

```bash
python pipeline/publish/export_graph_payload.py --claim-source gemini_normalized
```

The current normalizer is intentionally local and reproducible. External
normalization tools such as PubChem, ChEMBL, UniProt, HGNC, MONDO/OAK, or
scispaCy should be used as enrichment and candidate-generation layers for
unmapped labels, not as silent replacements for the local registry decision.

## Optional Stub Promotion

This older path promotes curated-ready rows from processed stub files into
curated datasets. Use it for maintaining the existing graph while the extraction
pipeline is being replaced.

## Workflow
1. Generate context-level stubs from the triage-relevant DOI queue
   (`pipeline/ingest/seed_from_dois.py`). Stubs are keyed by
   `DOI + compound + target/disorder`.
2. Autofill and curate stubs in `data/processed/*_claim_stubs.json`:
   - fill required fields
   - add `authors`
   - set `stub_status` to `ready_for_promotion`
3. Run promotion in dry-run mode (default) to see blockers and duplicates.
4. Run with `--apply` to write curated JSON/CSV and remove promoted stubs.

## Commands
Mechanistic dry run:
`python pipeline/extract/promote_ready_stubs.py --dataset mechanistic`

Mechanistic apply:
`python pipeline/extract/promote_ready_stubs.py --dataset mechanistic --apply`

Disorder dry run:
`python pipeline/extract/promote_ready_stubs.py --dataset disorder`

Disorder apply:
`python pipeline/extract/promote_ready_stubs.py --dataset disorder --apply`

## Reports
- `data/processed/promotion_report_mechanistic.json`
- `data/processed/promotion_report_disorder.json`

## Notes
- Rows that match existing curated signatures are not promoted; their
  `stub_status` becomes `duplicate_existing` on apply.
- Rows failing required fields/types/enums are blocked and listed in report
  errors.
