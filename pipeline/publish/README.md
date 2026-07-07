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
python pipeline/publish/export_evidence_payload.py \
  --kg-dir "data/processed/kg_routed_runs/$RUN_ID" \
  --out-dir "data/processed/graph_payload_runs/$RUN_ID" \
  --activate-default
```

Build the unified methods bibliography:

```bash
python pipeline/kg/build_methods_flow.py
```

## Outputs

- `data/processed/graph_payload_active.json`
- `data/processed/graph_payload_runs/<RUN_ID>/graph_payload_manifest.json`
- `data/processed/graph_payload_runs/<RUN_ID>/graph_bootstrap_view_<view>_<source>.json`
- `data/processed/graph_payload_runs/<RUN_ID>/detail_bootstrap_view_<view>_<source>.json`
- `data/kg/views/pipeline_status_graph.json`
- `data/kg/views/methods_bibliography.json`

## Contract

`graph_payload_manifest.json` contains:

- `schema_version`
- `evidence_source`
- `kg_dir`
- `row_count`
- `summary_stats`
- `graph_bootstraps`
- `detail_bootstraps`

`graph_bootstrap_view_<view>_<source>.json` contains aggregate graph edges for
fast initial rendering: compound, entity label, entity kind, finding count,
study count, and full-text-seen counts.

`detail_bootstrap_view_<view>_<source>.json` contains the row-level public UI
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
- domain-specific evidence fields such as `outcome_measure`, `sample_size_total`,
  `mechanism_type`, `assay_type`, `assessment_timepoint`, and `effect_size`

The public export does not use the old `claim_type` field, does not split
routed findings into old mechanistic/disorder export files, and does not publish
the heavy full-evidence JSON dump.
