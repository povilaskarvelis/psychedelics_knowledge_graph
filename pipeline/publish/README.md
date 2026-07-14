# Publish Prep: Evidence Payload Export

This step exports compact route-native evidence files for the web UI. The
public site reads a manifest plus graph and detail bootstrap files keyed by the
actual routed extraction domains, not by the old two-dataset UI split.

The browser can still render the existing graph, cards, filters, and
bibliography layout. It derives its display grouping from each finding's
`domain` and `entity_kind` after loading the compact detail bootstrap.

## Run

Build a versioned routed KG and payload without changing the public graph:

```bash
RUN_ID=gemini3_flash_YYYYMMDD_first_batch
scripts/build_routed_kg_payload.sh "$RUN_ID"
```

After reviewing that versioned run, promote it without rebuilding it:

```bash
python pipeline/publish/promote_routed_run.py --run-id "$RUN_ID"
```

The promoter validates the KG, payload, author tables, and extraction inputs;
materializes every final graph decision into the canonical
`candidate_papers.parquet` corpus ledger; serializes promotions with a lock;
stages the Methods and `dist/` rebuilds; and updates the extraction and
public-graph compatibility pointers to the same release. The promotion fails if
any selected report lacks a final disposition or if screening, routing, graph,
or release decisions contradict one another. `ACTIVATE_DEFAULT=1
scripts/build_routed_kg_payload.sh "$RUN_ID"` remains a one-command
build-and-promote shorthand and uses the same guarded promoter.

The wrapper is non-activating by default. This keeps historical or diagnostic
rebuilds from changing the public graph by accident. `scripts/build_site.sh`
validates the committed public pointer, manifest, and browser payloads before
building. The promoter separately checks that the extraction pointer, public
pointer, and canonical corpus identify the same release; that deeper check
stays in promotion because its extraction and Parquet inputs are intentionally
not part of a clean deployment checkout.

If the KG tables have already been rebuilt and only the public payload needs to
be regenerated, make sure `pipeline/kg/build_author_tables.py` has run after the
last `papers.parquet` change. The exporter checks `authors.parquet`,
`paper_authors.parquet`, and
`author_resolution_report.json` against `papers.parquet` by default and fails
when the author layer is missing or stale. `--allow-stale-authors` is available
only for deliberate diagnostic exports.

Promotion also rebuilds the Methods PRISMA flow and unified bibliography solely
from the updated canonical corpus ledger. The Methods build has no fallback to
the routed KG, active pointers, normalization audit, or disposition override
file. Do not run a separate bibliography step afterward.

## Outputs

- `data/processed/graph_payload_active.json`
- `data/processed/extraction/active_routed_run.json`
- `data/processed/graph_payload_runs/<RUN_ID>/graph_payload_manifest.json`
- `data/processed/graph_payload_runs/<RUN_ID>/graph_bootstrap_<source>.json`
- `data/processed/graph_payload_runs/<RUN_ID>/detail_bootstrap_<source>.json`
- `data/kg/views/pipeline_status_graph.json`
- `data/kg/views/methods_bibliography.json`

## Contract

The two active pointer files are compatibility views for different consumers,
not independent release switches. Both contain the same `run_id` and
`release_id` after guarded promotion. The extraction pointer additionally names
the combined raw outputs and evidence rows required by the next scoped update;
the public graph pointer names only compact browser artifacts.

`graph_payload_manifest.json` contains:

- `schema_version`
- `evidence_source`
- `kg_dir`
- `row_count`
- `author_tables`
- `summary_stats`
- `graph_bootstraps`
- `detail_bootstraps`

`summary_stats.paper_counts` is the generated source of truth for the four
public header metrics: primary studies, reviews, meta-analyses, and their total
represented anywhere in the underlying normalized evidence graph. These values
are deduplicated by DOI, then OpenAlex ID, then title and year, and regenerated
whenever the routed KG payload is exported. A report does not need to appear in
the visual overview to count as graph-represented. Reports that are not
represented are explained, with final plain-language reasons, in the Methods
page PRISMA flow. `visualized_overview_represented` retains the stricter
visual-overview counts for diagnostics; primary studies and reviews use the
two-report overview-node rule, while meta-analyses use a one-report rule.

`graph_bootstrap_<source>.json` contains aggregate graph edges for
fast initial rendering: compound, graph-anchor entity label, graph-anchor
entity kind, finding count, study count, and full-text-seen counts. It is
intentionally limited to graph-visible anchor kinds. Metadata/detail kinds such
as outcome scales, compound classes, symptoms and outcomes, brain measures, and
pharmacokinetic parameters stay out of this aggregate graph file.

`detail_bootstrap_<source>.json` contains the row-level public UI
data in a compact field/value/row representation:

- `fields[]`
- `values[]`
- `rows[]`

The decoded rows are flat and route-native. Important fields include:

- `domain`
- `finding_type`
- `evidence_type`
- `compound`
- `entity_label`
- `entity_kind`
- `text_depth`
- report metadata such as `study_doi`, `openalex_id`, `study_title`, and `study_year`
- domain-specific evidence fields such as `support`, `effect_size`,
  `outcome_measure`, `sample_size_total`, `mechanism_type`, `assay_type`, and
  `assessment_timepoint`
- meta-analysis fields such as result role, population, comparator, follow-up
  window, included-study count, effect metric and interval, heterogeneity,
  subgroup or moderator, risk-of-bias summary, and evidence strength

Detail rows may include metadata/detail entity kinds that are not graph
anchors, such as `outcome_scale`, `compound`, `symptom_problem`, and
`pharmacokinetic_parameter`. These feed right-panel facets and evidence cards;
they are not top-level graph views.

The meta-analysis right panel uses clickable stacked-bar filters for synthesis
design, comparator, follow-up window, and included-study count.
Article-text filtering is handled by the shared control above the graph, and
population and result role remain finding context rather than composition plots. More
sparsely reported assessments such as heterogeneity, risk of bias, and certainty
are shown in finding cards when present rather than treated as complete
composition fields.

Primary-research and review graph nodes require support from at least two source
reports. Meta-analysis nodes are exempt from that replication threshold because
each source report already represents a synthesis and the meta-analysis graph is
comparatively sparse.

The public export does not use the old `claim_type` field, does not split
routed findings into multiple legacy export files, and does not publish the
heavy full-evidence JSON dump.
