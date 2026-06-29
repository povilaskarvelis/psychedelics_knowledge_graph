# Publish Prep: Evidence Payload Export

This step exports route-native evidence findings for the web UI. The default
UI payload is a single findings file keyed by the actual routed extraction
domains, not by the old two-dataset UI split.

The browser can still render the existing graph, cards, filters, and
bibliography layout. It derives its display grouping from each finding's
`domain` and `entity_kind` after loading the route-native payload.

## Run

Export a routed KG run and make it the UI default:

```bash
RUN_ID=gemini3_flash_YYYYMMDD_first_batch
python pipeline/publish/export_evidence_payload.py \
  --kg-dir "data/processed/kg_routed_runs/$RUN_ID" \
  --out-dir "data/processed/graph_payload_runs/$RUN_ID" \
  --activate-default
```

Export the interim bibliography payloads:

```bash
python pipeline/publish/export_bibliography_payload.py
```

Legacy comparison exports are still available in
`pipeline/publish/export_graph_payload.py`, but they are not the preferred
default path for new routed extraction runs.

## Outputs

- `data/processed/graph_payload_active.json`
- `data/processed/graph_payload_runs/<RUN_ID>/graph_payload_evidence.json`
- `data/processed/graph_payload_runs/<RUN_ID>/graph_preview_evidence.json`
- `data/processed/graph_payload_runs/<RUN_ID>/graph_payload_manifest.json`
- `data/processed/bibliography_payload_mechanistic.json`
- `data/processed/bibliography_payload_disorder.json`
- `data/processed/bibliography_payload_manifest.json`

## Contract

`graph_payload_evidence.json` contains:

- `schema_version`
- `evidence_source`
- `kg_dir`
- `row_count`
- `summary_stats`
- `findings[]`

Each finding is flat and route-native. Important fields include:

- `finding_id`
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

The payload does not use the old `claim_type` field and does not split routed
findings into old mechanistic/disorder export files.
