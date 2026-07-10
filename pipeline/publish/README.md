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

Build the unified methods bibliography:

```bash
python pipeline/kg/build_methods_flow.py
```

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

`graph_bootstrap_<source>.json` contains aggregate graph edges for
fast initial rendering: compound, graph-anchor entity label, graph-anchor
entity kind, finding count, study count, and full-text-seen counts. It is
intentionally limited to graph-visible anchor kinds. Metadata/detail kinds such
as outcome scales, compound classes, symptoms that are not top-level graph
anchors, and pharmacokinetic parameters stay out of this aggregate graph file.

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

Detail rows may include metadata/detail entity kinds that are not graph
anchors, such as `outcome_scale`, `compound`, `symptom_problem`, and
`pharmacokinetic_parameter`. These feed right-panel facets and evidence cards;
they are not top-level graph views.

The public export does not use the old `claim_type` field, does not split
routed findings into multiple legacy export files, and does not publish the
heavy full-evidence JSON dump.
