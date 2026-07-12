# Publish Prep: Evidence Payload Export

This step exports compact route-native evidence files for the web UI. The
public site reads a manifest plus graph and detail bootstrap files keyed by the
actual routed extraction domains, not by the old two-dataset UI split.

The browser can still render the existing graph, cards, filters, and
bibliography layout. It derives its display grouping from each finding's
`domain` and `entity_kind` after loading the compact detail bootstrap.

## Run

Export a routed KG run and make it the UI default:

```bash
RUN_ID=gemini3_flash_YYYYMMDD_first_batch
scripts/build_routed_kg_payload.sh "$RUN_ID"
```

If the KG tables have already been rebuilt and only the public payload needs to
be regenerated, make sure `pipeline/kg/build_author_tables.py` has run after the
last `papers.parquet` change. The exporter checks `authors.parquet`,
`paper_authors.parquet`, and
`author_resolution_report.json` against `papers.parquet` by default and fails
when the author layer is missing or stale. `--allow-stale-authors` is available
only for deliberate diagnostic exports.

The wrapper also rebuilds the Methods PRISMA flow and unified bibliography from
the same routed KG run. Do not run a separate bibliography step after an
activating graph build.

## Outputs

- `data/processed/graph_payload_active.json`
- `data/processed/graph_payload_runs/<RUN_ID>/graph_payload_manifest.json`
- `data/processed/graph_payload_runs/<RUN_ID>/graph_bootstrap_<source>.json`
- `data/processed/graph_payload_runs/<RUN_ID>/detail_bootstrap_<source>.json`
- `data/kg/views/pipeline_status_graph.json`
- `data/kg/views/methods_bibliography.json`

## Contract

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
public header metrics: graph-represented primary studies, reviews,
meta-analyses, and their total. These values are deduplicated by DOI, then
OpenAlex ID, then title and year. They are regenerated whenever the routed KG
payload is exported; meta-analysis counts use the same one-paper visibility
rule as the meta-analysis graph, while primary studies and reviews use the
two-paper overview-node rule. The nested `awaiting_graph_inclusion` counts use
the corresponding relevant-paper candidate set as their denominator and report
papers that have not yet produced a graph-represented relationship.

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
- paper metadata such as `study_doi`, `openalex_id`, `study_title`, and `study_year`
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
papers. Meta-analysis nodes are exempt from that replication threshold because
each source paper already represents a synthesis and the meta-analysis graph is
comparatively sparse.

The public export does not use the old `claim_type` field, does not split
routed findings into multiple legacy export files, and does not publish the
heavy full-evidence JSON dump.
