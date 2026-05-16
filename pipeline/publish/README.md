# Publish Prep: Graph Payload Export

This step exports curated claims into deterministic graph payload JSON.

## Run
Export both datasets:
`python pipeline/publish/export_graph_payload.py`

Export the interim bibliography payloads from abstract-screened relevant papers:
`python pipeline/publish/export_bibliography_payload.py`

Mechanistic only:
`python pipeline/publish/export_graph_payload.py --dataset mechanistic`

Custom output directory:
`python pipeline/publish/export_graph_payload.py --out-dir data/processed`

## Outputs
- `data/processed/graph_payload_mechanistic.json` (all evidence)
- `data/processed/graph_payload_mechanistic_primary_only.json`
- `data/processed/graph_payload_mechanistic_secondary_sources.json`
- `data/processed/graph_payload_mechanistic_primary_with_secondary.json`
- `data/processed/graph_payload_disorder.json` (all evidence)
- `data/processed/graph_payload_disorder_primary_only.json`
- `data/processed/graph_payload_disorder_secondary_sources.json`
- `data/processed/graph_payload_disorder_primary_with_secondary.json`
- `data/processed/graph_payload_manifest.json`
- `data/processed/bibliography_payload_mechanistic.json`
- `data/processed/bibliography_payload_disorder.json`
- `data/processed/bibliography_payload_manifest.json`

## Contract
Each payload contains:
- `contract_version`
- `dataset`
- `evidence_view` (`all_evidence`, `primary_only`, `secondary_sources`, or `primary_with_secondary`)
- `template`
- `row_count`
- `contributions[]` with deterministic `external_id`
- `paper` (including `authors`), `resources`, `properties`, `provenance`

## Notes
- Export validates rows against dataset schema and records errors in the manifest.
- `secondary_sources` includes reviews, systematic reviews, and meta-analyses
  from both curated rows and exploratory/demoted rows. Protocols,
  commentaries, conference abstracts, and corrections remain non-primary
  context and are not included in that view by default.
- Manifest includes SHA-256 digests and row counts for all evidence views.
- Graph payload files avoid volatile timestamps so hashes are stable when data is unchanged.
- Bibliography payloads currently use `source: abstract_screening_relevant`
  so the UI can test citation formatting before the final bibliography source
  exists.
