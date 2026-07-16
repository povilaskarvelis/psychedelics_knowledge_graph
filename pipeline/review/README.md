# Review

This stage contains table-native deterministic pre-screening and the separate
model-based screening/routing workflow that follows it. It reads and writes
canonical corpus tables; it does not maintain dataset-specific paper libraries,
DOI queues, claim stubs, or curated claim files.

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

The deterministic stage has only two jobs: retain a record for model-assisted
title/abstract screening, or exclude it for a specific high-confidence reason.
It does not assign evidence-domain or report-type routing tags.

After the configured metadata-enrichment attempts have run, records without a
usable abstract are handled conservatively. An explicit in-scope compound or
intervention in the title is enough to retain the record as
`retain_for_screening`; otherwise it is marked
`exclude_no_usable_abstract`. Records with an abstract but no title are screened
normally from the abstract. Placeholder and citation-only abstract fields count
as unusable abstracts.

For records with usable abstracts, title, abstract, keywords, and MeSH terms
can provide an in-scope signal. Publication-format exclusions, such as
protocols and corrections, run first. A record labelled as a letter or comment
is not excluded solely on that label when its metadata or text identifies
substantive empirical evidence, such as a case report or trial.

For small updates, recompute only the affected DOIs:

```bash
python pipeline/review/run_deterministic_prescreen.py \
  --doi-file /tmp/changed_dois.txt
```

Scoped updates require an existing decisions table. The script replaces or
adds only the requested DOI rows and then rebuilds the summary from the merged
table. If `--run-id` is omitted, it reuses the existing decisions table's run
ID. After a prescreen schema/rule upgrade, run one full pass before using scoped
updates; the command refuses to mix incompatible decision-table versions.

The reusable title/abstract rules live in
`pipeline/review/deterministic_prescreen_rules.py`. They are kept separate from
the command so scoped-update and audit code can use the same rules without
depending on a legacy screening implementation.

## Gemini screening, domain routing, and report-type routing

Scope, domain, and report type for extraction are assigned together from
title/abstract metadata by the Gemini routing stage. This is the sole owner of
domain and report-type routing; the deterministic pre-screen only decides which
records proceed to it.

Prepare and advance the current batch queue with:

```bash
python pipeline/review/build_gemini_domain_routing_batch_queue.py --prepare
python pipeline/review/advance_gemini_domain_routing_batch_queue.py
```

The canonical routing output is
`data/processed/corpus/paper_domain_routing_gemini.parquet`.
