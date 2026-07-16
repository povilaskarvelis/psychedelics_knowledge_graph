# Living Literature Discovery

This directory is the standard discovery stage for the Psychedelics Knowledge
Graph. It supports recurring elapsed-period updates and all-time recovery after
a material search-strategy or compound-scope change.

The stage is deliberately separate from screening and graph mapping:

1. build and save the exact provider-specific search plan;
2. retrieve and reconcile every provider record ID;
3. measure query yield and provider overlap;
4. resume safely after request-budget or provider pauses;
5. promote only when the configured retrieval-completeness gates pass; and
6. classify new records and extract compound/entity relationships downstream.

## Strategy versions

`search_strategy.v2.json` is frozen for auditability. Its Cartesian pair grid
was empirically inefficient and must not be used for a new run.

`search_strategy.v3.json` is the active protocol. It keeps the useful v2 run
infrastructure while changing query generation:

- PubMed uses Text Word branches plus MeSH and Supplementary Concept branches.
- OpenAlex uses the title-and-abstract field filter for every keyword search,
  not its much noisier title/abstract/full-text default search.
- OpenAlex receives a high-specificity compound alias set. Spaced short-code
  variants such as `2c c` and `4 ho met` are excluded.
- Core modules use compound/class plus a broad evidence domain.
- Scope searches use compound identity alone and are cross-domain; screening
  assigns mechanistic, clinical, safety, and other downstream routes.
- Newly added compounds receive all-time identity recovery searches.
- Adding targets, brain systems, tasks, or disorders triggers downstream
  reclassification, not a database-query cross-product.
- Pair searches are generated only from explicit `targeted_pairs` entries in
  the strategy. Every entry must be in scope and include a rationale.
- A plan-size guard refuses plans above `planning.max_query_executions` unless
  the operator explicitly supplies `--allow-large-plan` after inspection.

OpenAlex currently supports `title_and_abstract.search` but marks field-specific
search filters as deprecated. Provider tests cover the request shape so removal
will fail visibly rather than silently widening the search.

## Configuration

Research scope and provider credentials are separate inputs:

- `--scope-config pipeline/config.example.yaml` supplies canonical validation
  allowlists used to generate queries.
- `--config pipeline/config.local.yaml` supplies local API keys, email, and rate
  settings and should not be used as the scope source.

This prevents a credentials-only local file from accidentally creating an
empty or altered research scope.

## Elapsed-period update

The update window begins at the end date of the latest successfully promoted
v3 standard run, with a 14-day indexing overlap. If no v3 run has been
promoted, it begins from the legacy coverage date, 2026-05-28, with the same
overlap.

```bash
python pipeline/discovery/run_literature_search.py \
  --mode update \
  --run-id living_update_v3_YYYYMMDD \
  --config pipeline/config.local.yaml \
  --scope-config pipeline/config.example.yaml \
  --layers core,scope
```

PubMed publication-date and Entrez-date streams are searched. OpenAlex
publication-date search is standard. Created-date filtering requires a paid
OpenAlex plan and remains an explicit `--openalex-created-date-updates` option;
periodic historical recovery searches recover older works newly added to the
index.

Only a complete standard update across both providers, all three discovery
datasets (`mechanistic`, `disorder`, and cross-domain `general`), the `core` and
`scope` layers, and scope-delta compound recovery can advance the shared update
watermark.

## Full strategy rerun

Use a full run after materially changing the concepts, aliases, source role, or
query structure:

```bash
python pipeline/discovery/run_literature_search.py \
  --mode full \
  --run-id living_full_v3_YYYYMMDD \
  --config pipeline/config.local.yaml \
  --scope-config pipeline/config.example.yaml \
  --layers core,scope
```

The full v3 plan searches from 1800 onward and does not include an automatic
pair grid. Add `targeted_pairs` only after screening or coverage review finds a
concrete gap, then request `--layers core,scope,targeted_pairs`.

## Reusing a completed update in a historical baseline

When an elapsed-period v3 update has already completed, do not rerun its recent
window. Build only the missing historical component and reuse all-time
scope-delta searches already completed by the update:

```bash
python pipeline/discovery/run_literature_search.py \
  --mode historical_gap \
  --run-id living_historical_gap_v3_YYYYMMDD \
  --reuse-run-id living_update_v3_YYYYMMDD \
  --config pipeline/config.local.yaml \
  --scope-config pipeline/config.example.yaml \
  --layers core,scope \
  --no-known-record-calibration
```

After both components pass retrieval completeness, compose them into one full
baseline:

```bash
python pipeline/discovery/compose_search_runs.py \
  --run-id living_full_composite_v3_YYYYMMDD \
  --update-run-id living_update_v3_YYYYMMDD \
  --historical-gap-run-id living_historical_gap_v3_YYYYMMDD
```

The update and historical-gap manifests are marked as non-promotable
components. Only the composite run establishes the all-time scope baseline and
advances the living-search watermark.

For an unattended long historical retrieval, the guarded finisher can wait for
the gap, compose it, and promote only if all completion checks pass:

```bash
python pipeline/discovery/finish_composite_baseline.py \
  --run-id living_full_composite_v3_YYYYMMDD \
  --update-run-id living_update_v3_YYYYMMDD \
  --historical-gap-run-id living_historical_gap_v3_YYYYMMDD \
  --promote
```

If the gap fails, pauses for budget, or remains incomplete, the finisher exits
without composing or changing the canonical candidate corpus.

## Plan before retrieval

```bash
python pipeline/discovery/run_literature_search.py \
  --mode update \
  --run-id living_update_v3_YYYYMMDD \
  --config pipeline/config.local.yaml \
  --scope-config pipeline/config.example.yaml \
  --layers core,scope \
  --plan-only
```

Inspect `search_plan.csv` for provider, search surface, date basis, date window,
layer, compound, entity, and exact query. The manifest also records whether an
automatic pair grid was disabled, how many targeted pairs were configured, and
whether a large-plan override was used.

## Resume and provider budgets

OpenAlex search calls have a usage allowance. The runner checks the account's
live allowance and uses the available daily plus prepaid search calls. Pauses
are expected resumable states, never successful completion:

```bash
python pipeline/discovery/run_literature_search.py \
  --resume \
  --run-id living_update_v3_YYYYMMDD \
  --config pipeline/config.local.yaml \
  --providers openalex
```

Every query is counted before retrieval. Results above the provider's safe
window are recursively partitioned by date, cursor/offset pagination is
checkpointed, and unique provider IDs must reconcile to every partition count.
If a live index count changes during pagination, the runner recounts and makes
a bounded recrawl; an unresolved shortfall still fails visibly.

## Diagnostics and completion gates

Mechanical retrieval completeness is mandatory: every selected execution must
finish with no unresolved provider error or result-count shortfall. Query-group
diagnostics report zero-result rates, raw and unique retrieval, request/page
counts, provider overlap, and records exclusive to each layer/search type.

The initial 50-paper known-record pilot is retired and is not used by newly
planned living-search runs. `--no-known-record-calibration` remains accepted
only for compatibility with runs planned before this change.

`retrieval_completion_gate_passed` remains required. The legacy manifest field
`calibration_gate_passed` remains true when the retired check is not applicable;
it is not an estimate of search recall.

Run states include `planned`, `paused_budget`, `failed`, `calibration_failed`,
`complete`, and `promoted`.

If provider retrieval completed but the process was interrupted while building
large Parquet artifacts, rerun only the out-of-core finalization stage:

```bash
python pipeline/discovery/finalize_search_run.py \
  --run-id living_historical_gap_v3_YYYYMMDD
```

This reuses the checkpoint and any current deduplicated hit Parquet; it does not
repeat provider requests or weaken retrieval-completeness checks.

## Optional bounded citation expansion

Citation expansion is not part of the default living-search protocol and does
not use the retired pilot set implicitly. When a separately justified citation
search is needed, provide the reviewed seed cohort and its bound explicitly:

```bash
python pipeline/discovery/run_citation_expansion.py \
  --run-id citation_update_YYYYMMDD \
  --config pipeline/config.local.yaml \
  --seed-source PATH_TO_REVIEWED_RECORDS \
  --seed-flag-column BOOLEAN_REVIEW_COLUMN \
  --max-seeds EXPLICIT_BOUND \
  --directions citing \
  --from-date YYYY-MM-DD \
  --to-date YYYY-MM-DD
```

For a reviewed historical recovery, use `--directions references,citing`.
The stage caps records per seed, reconciles citing-work counts, batches
referenced-work IDs in groups of 100, preserves seed/direction provenance, and
writes standard `provider_hits.parquet` and `retrieved_records.parquet`
artifacts. Start with `--plan-only`; exceeding a per-seed record bound fails
visibly rather than silently truncating the citation network.

## Promotion and downstream handoff

Promotion refuses a run unless its configured completion gates pass:

```bash
python pipeline/discovery/promote_search_run.py \
  --run-id living_update_v3_YYYYMMDD
```

Promotion backs up the canonical tables, appends new DOI-bearing records,
updates rediscovery provenance, retains no-DOI records for identifier
resolution, and writes `new_candidate_dois.txt`. Run metadata enrichment and
screening on that DOI file; relationship routing occurs downstream rather than
through a provider-side pair grid.

## Retiring superseded runs

Do not keep large raw checkpoints from an incomplete search indefinitely, but
do not delete a run without retaining enough information to audit why it was
discarded. Preview and then retire an unpromoted, non-promotable run with:

```bash
python pipeline/discovery/retire_search_run.py \
  --run-id RUN_ID \
  --reason "Superseded by a revised search strategy"

python pipeline/discovery/retire_search_run.py \
  --run-id RUN_ID \
  --reason "Superseded by a revised search strategy" \
  --apply
```

The retirement bundle keeps the manifest, compressed search and execution
plans, an aggregate run-state summary, and records found exclusively by direct
pair searches. It deletes raw provider hits, deduplicated bulk records, the
restart checkpoint, and other large transient files. The command refuses to
retire promoted runs or complete runs that are eligible for promotion.

## Run artifacts

Each run directory contains:

- `run_manifest.json` and `run_state.json`;
- `search_plan.csv` and `search_plan.parquet`;
- `provider_hits.checkpoint.jsonl` and `provider_hits.parquet`;
- `retrieved_records.parquet` and `query_executions.parquet`;
- `search_calibration_report.json`;
- `search_calibration_groups.csv`;
- `known_relevant_coverage.csv`; and
- promotion backups, reports, and new/rediscovered DOI files after promotion.

Do not manually mark a run complete or advance `search_history.json`. Only a
successful guarded promotion advances the next update window.
