# Review

This stage runs table-native pre-screening and model-based routing after
metadata enrichment. It reads and writes canonical corpus tables; it does not
maintain dataset-specific paper libraries, DOI queues, claim stubs, or curated
claim files.

## Table-native deterministic pre-screen

The corpus-first path reads the unified Parquet corpus tables and writes
screening decisions back as Parquet tables. It does not edit candidate papers
or delete older decisions.

Run:

```bash
python pipeline/review/run_deterministic_prescreen.py \
  --run-id deterministic_prescreen_YYYY_MM_DD
```

Outputs:

- `data/processed/corpus/paper_prescreen_decisions.parquet`
- `data/processed/corpus/paper_prescreen_summary.parquet`

Missing-abstract records are excluded by default. Existing downstream claim or
extraction provenance is not used by this pre-screen step.

For small updates, recompute only the affected DOIs:

```bash
python pipeline/review/run_deterministic_prescreen.py \
  --doi-file /tmp/changed_dois.txt
```

Scoped updates require an existing decisions table. The script replaces or
adds only the requested DOI rows and then rebuilds the summary from the merged
table. If `--run-id` is omitted, it reuses the existing decisions table's run
ID.

The reusable title/abstract rules live in
`pipeline/review/deterministic_prescreen_rules.py`. They are kept separate from
the command so scoped-update and audit code can use the same rules without
depending on a legacy screening implementation.

## Gemini screening, domain routing, and report-type routing

Scope, domain, and report type for extraction are assigned together from
title/abstract metadata by the Gemini routing stage. Pre-screen keyword tags
are high-recall screening signals, not production extraction routes.

Prepare and advance the current batch queue with:

```bash
python pipeline/review/build_gemini_domain_routing_batch_queue.py --prepare
python pipeline/review/advance_gemini_domain_routing_batch_queue.py
```

The canonical routing output is
`data/processed/corpus/paper_domain_routing_gemini.parquet`.
