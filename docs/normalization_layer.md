# Normalization Layer

The extraction model is allowed to preserve raw endpoint detail, but clean graph
edges must pass through a deterministic normalization layer.

## Contract

Extraction rows should keep both:

- raw labels: `raw_entity_label`, `outcome_measure`, `target`, `disorder`
- graph intent: `graph_entity_label`, `graph_entity_type`,
  `graph_include_candidate`, `graph_exclusion_reason`

The normalizer treats the graph-intent fields as suggestions, not truth. A row
becomes a clean graph edge only when:

- `graph_include_candidate = true`
- `graph_entity_type` matches the dataset (`target` for mechanistic,
  `indication` for disorder)
- `entity_role` is compatible with a graph endpoint
- the compound matches the local compound registry
- the graph endpoint matches the local target or disorder registry

All other rows remain available in normalization audit files.

## Current Implementation

Run:

```bash
python pipeline/extract/normalize_extraction_claims.py
```

Inputs:

- `data/processed/extraction/mechanistic_claims.json`
- `data/processed/extraction/disorder_claims.json`
- `data/curated/entity_registry.json`
- `schema/disorder_canonicalization.json`

Outputs:

- `data/processed/extraction/mechanistic_graph_claims.json`
- `data/processed/extraction/disorder_graph_claims.json`
- `data/processed/extraction/mechanistic_normalization_audit.json`
- `data/processed/extraction/disorder_normalization_audit.json`
- `data/processed/extraction/normalization_report.json`

The graph files are narrow and registry-backed. The audit files are broad and
show why each extracted claim was included or held back.

## Library Strategy

The first normalization pass is intentionally local and reproducible. External
libraries and ontology services should enrich the registry and suggest
candidates for unmapped labels, but they should not silently decide graph edges.

Recommended roles:

- PubChem or ChEMBL for compound identifiers and chemical structure metadata
- ChEMBL targets, UniProt, and HGNC for target/gene/protein identifiers
- MONDO, EFO, MeSH, and OAK for disorder/indication ontology lookup
- Bioregistry for CURIE and prefix normalization
- scispaCy for optional candidate generation from messy free text, especially
  UMLS/MeSH/RxNorm suggestions

The safe workflow is:

1. Normalize against the local registry.
2. Review unmapped labels and high-frequency aliases in the audit files.
3. Use ontology/library-backed enrichment to propose registry additions.
4. Add accepted labels, aliases, and identifiers to `entity_registry.json`.
5. Rerun the deterministic normalizer.

This keeps the public graph stable while letting the registry improve over
time.
