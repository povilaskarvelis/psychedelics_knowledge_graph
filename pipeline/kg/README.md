# Knowledge Graph Projection

This stage builds a deterministic file-based knowledge graph from the existing
pipeline outputs. It does not replace curated claim files; it projects them,
paper-library records, screening triage, and full-text conversion status into a
typed graph layer for visualization and QA.

Run:

```bash
python pipeline/kg/build_kg.py
```

Default outputs are written under `data/kg/`:

- `canonical/nodes.jsonl`: papers, entities, and evidence-record nodes.
- `canonical/edges.jsonl`: paper/evidence/entity relations.
- `canonical/evidence_records.jsonl`: rich claim and screening-context records.
- `indexes/*.json`: DOI, entity, and aggregate-edge lookup helpers.
- `aggregates/*.jsonl` and `aggregates/literature_gap_matrix.json`: collapsed
  compound-disorder and compound-target edges for analysis.
- `views/*.json`: UI-oriented graph payloads.
- `manifests/build_manifest.json`: counts, input files, and validation notes.

The canonical graph is generated. Human curation should continue to happen in
`data/curated/*` or upstream review files.
