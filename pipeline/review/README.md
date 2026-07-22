# Review

This stage contains table-native deterministic pre-screening and the separate
model-based screening/routing workflow that follows it. It reads and writes
canonical corpus tables; it does not maintain dataset-specific paper libraries,
DOI queues, claim stubs, or curated claim files.

## Table-native deterministic pre-screen

The corpus-first path reads the unified Parquet corpus tables and writes
screening decisions back as Parquet tables. It also promotes the current
decision into `candidate_papers.parquet` and reconciles downstream active state;
historical decision and raw-run artifacts remain provenance.

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

Deterministic prescreen uses only reusable rules over canonical candidate
metadata, text, and safely scoped identifier patterns. DOI-specific decisions
discovered through provider-record, landing-page, or document review belong to
the separate post-retrieval eligibility ledger and dedicated candidate columns,
even when the decision is based on explicit, machine-readable provider metadata
(for example, a DataCite resource type identifying a dissertation).

After the configured metadata-enrichment attempts have run, records without a
usable abstract are marked `exclude_no_usable_abstract`; title-only records are
not sent to model-assisted screening. Records with an abstract but no title are
screened normally from the abstract. Placeholder and citation-only abstract
fields count as unusable abstracts. Abstracts containing fewer than 50 words
also count as unusable; the threshold is inclusive, so an abstract with exactly
50 words remains eligible for screening. The decision table records both the
character count and word count used by this rule.

For records with usable abstracts, title, abstract, keywords, and MeSH terms
can provide an in-scope signal. Publication-format exclusions, such as
protocols and corrections, run first. A record labelled as a letter or comment
is not excluded solely on that label when its metadata or text identifies
substantive empirical evidence, such as a case report or trial.

Conference-format rules use high-confidence evidence: explicit publication
types (including `conference-paper`), dedicated poster/event DOI namespaces,
named congress DOI tokens, publisher-verified conference collection blocks,
or a numbered/coded title combined with meeting/proceedings metadata. Journal
issue and page metadata can corroborate known conference supplements without
using unsafe DOI-suffix guesses; ordinary issue/page ranges remain eligible.
Explicit
`supplement`/`suppl` tokens in an item DOI identify an excluded supplement
contribution; the dedicated `10.1254/jpssuppl.*` annual-meeting namespace is
classified as a conference abstract. Literal supplementary objects are also
excluded when their title or identifier identifies supplementary material,
data, files, figures, or tables. A bare provider
`publication_type=supplementary-materials` label is not sufficient because
provider type metadata can be wrong. Uppercase or coded poster-like titles and
journal identity remain insufficient without a corroborating format signal.

For small updates, recompute only the affected DOIs:

```bash
python pipeline/review/run_deterministic_prescreen.py \
  --doi-file /tmp/changed_dois.txt
```

Deterministic prescreen reads bibliographic input exclusively from
`candidate_papers.parquet`. Metadata enrichment must therefore complete its
candidate-materialization step first. `paper_metadata_enrichment.parquet`
remains a provider/provenance cache and cannot silently replace candidate
values during prescreen.

Scoped updates require an existing decisions table. The script replaces or
adds only the requested DOI rows and then rebuilds the summary from the merged
table. If `--run-id` is omitted, it reuses the existing decisions table's run
ID. After a prescreen schema/rule upgrade, run one full pass before using scoped
updates; the command refuses to mix incompatible decision-table versions.

The reusable title/abstract rules live in
`pipeline/review/deterministic_prescreen_rules.py`. They are kept separate from
the command so scoped-update and audit code can use the same rules without
depending on a legacy screening implementation.

Decision changes use the shared stage-aware reconciler in
`pipeline/workflow/decision_state.py`. Only records included by both the
previous and current decision at a stage retain downstream projections. New
includes and current excludes have later-stage candidate fields reset, and
declared active derived views are filtered. Bibliographic metadata, discovery
provenance, PDFs, converted text, raw model responses, and published run
archives are not deleted.

## Gemini screening, domain routing, and report-type routing

Scope, domain, and report type for extraction are assigned together from
title/abstract metadata by the Gemini routing stage. This is the sole owner of
domain and report-type routing; the deterministic pre-screen only decides which
records proceed to it.

The model screen is binary: plausibly in-scope records are included and only
clearly out-of-scope records are excluded. There is no `unclear` state because
it had no distinct downstream workflow. Validated abstracts are sent in full;
the metadata repair stage must run before queue preparation so reconstructed
full text or multi-record container text is never passed as an abstract.

Prepare and advance the current batch queue with:

```bash
python pipeline/review/build_gemini_domain_routing_batch_queue.py \
  --previous-candidate-table path/to/pre-promotion-candidate_papers.parquet \
  --prepare

# Submission requires explicit authorization.
python pipeline/review/advance_gemini_domain_routing_batch_queue.py --submit
```

The canonical routing output is
`data/processed/corpus/paper_domain_routing_gemini.parquet`.

Once that table is complete, run the independent provider-only funding stage:

```bash
python pipeline/ingest/enrich_paper_funding.py \
  --run-id funding_enrichment_YYYYMMDD
```

Its default scope is the distinct `include_in_scope` DOI cohort, with curated
screening exclusions and DOI aliases removed. It does not change screening,
extraction routes, or the graph; see `pipeline/ingest/README.md` for its table
contracts and resume behavior.
