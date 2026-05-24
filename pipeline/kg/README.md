# Knowledge Graph Projection

This stage builds the generated graph files used by the UI methods section,
including the literature graph and PRISMA-style flow. It does not replace the
main-page graph payloads or the claim files. It projects the current corpus manifest, paper libraries,
abstract-screening reports, full-text conversion status, and curated claim
files into graph-shaped outputs for visualization and QA.

The main-page graph is generated separately by
`pipeline/publish/export_graph_payload.py`, which defaults to the projected
Gemini extraction claim files in `data/processed/extraction/`.

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

For new search runs, add the completed abstract-screening report to
`data/processed/corpus_manifest.json`, regenerate extraction inputs if needed,
then rerun `python pipeline/kg/build_kg.py`. The methods graph and PRISMA flow
will update from the manifest-defined corpus without editing UI data by hand.
