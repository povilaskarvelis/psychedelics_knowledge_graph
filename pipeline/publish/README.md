# Publish Prep: Graph Payload Export

This step exports curated claims into deterministic graph payload JSON.

## Run
Export both datasets:
`python pipeline/publish/export_graph_payload.py`

Mechanistic only:
`python pipeline/publish/export_graph_payload.py --dataset mechanistic`

Custom output directory:
`python pipeline/publish/export_graph_payload.py --out-dir data/processed`

## Outputs
- `data/processed/graph_payload_mechanistic.json` (all evidence)
- `data/processed/graph_payload_mechanistic_primary_only.json`
- `data/processed/graph_payload_disorder.json` (all evidence)
- `data/processed/graph_payload_disorder_primary_only.json`
- `data/processed/graph_payload_manifest.json`

## Contract
Each payload contains:
- `contract_version`
- `dataset`
- `evidence_view` (`all_evidence` or `primary_only`)
- `template`
- `row_count`
- `contributions[]` with deterministic `external_id`
- `paper` (including `authors`), `resources`, `properties`, `provenance`

## Notes
- Export validates rows against dataset schema and records errors in the manifest.
- Manifest includes SHA-256 digests and row counts for both evidence views.
- Payload files avoid volatile timestamps so hashes are stable when data is unchanged.
