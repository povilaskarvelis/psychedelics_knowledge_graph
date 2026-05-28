# Methods Flow Projection

This stage builds the generated files used by the UI methods section, including
the PRISMA-style paper flow. It does not replace the main-page graph payloads or
the claim files. It projects the current corpus manifest, paper libraries,
abstract-screening reports, full-text conversion status, and the normalized KG
claim table into a paper-flow view.

The main-page graph is generated separately by
`pipeline/publish/export_graph_payload.py`. The active main-page payloads use
the normalized KG evidence tables by default; the older projected Gemini claim
JSON files remain as source/audit artifacts.

Run:

```bash
python pipeline/kg/build_methods_flow.py --refresh-kg-tables
```

Default outputs are written under `data/kg/`:

- `views/pipeline_status_graph.json`: UI-oriented PRISMA paper-flow payload.
- `schema/methods_flow.schema.json`: minimal methods-flow payload contract.
- `manifests/build_manifest.json`: counts, input files, and validation notes.

The methods-flow payload is generated from pipeline artifacts. Human curation
should continue to happen in `data/curated/*` or upstream review files.

The final PRISMA inclusion count is derived from the normalized KG claim table.
The flow also reads the active extraction output named by
`data/processed/extraction/projection_report.json`, so full-text and abstract
branches can show Gemini-excluded, human-review, no-promoted-KG, and
not-yet-extracted counts separately.

## Normalized evidence tables

The main KG backbone is the normalized evidence-table layer:

```bash
python pipeline/kg/build_evidence_tables.py
```

Default outputs are written under `data/processed/kg/`:

- `papers.parquet`: one row per source paper represented in normalized evidence.
- `entities.parquet`: compounds plus normalized clinical/mechanistic entities.
- `claims.parquet`: one rich normalized claim row per projected evidence record.
- `evidence_edges.parquet`: graph-oriented compound-to-entity evidence edges.
- `normalization_audit.parquet`: normalization successes and misses for review.
- `manifest.json`: table counts, source counts, and entity-kind summaries.
- `kg.duckdb`: optional local DuckDB database materialized when the `duckdb`
  Python package is installed.

This table layer is the preferred place to build new graph views. The browser UI
should continue to load compact JSON payloads generated from these tables rather
than loading the whole KG directly.

The current main UI views are driven by `evidence_edges.entity_kind`:

- clinical: conditions, symptoms, safety/adverse events, and outcome scales
  currently have graph rows.
- mechanistic: targets, pathways/processes, biomarkers/readouts, and
  systems/families currently have canonical graph rows.

Clinical endpoint rows are derived from raw disorder extraction rows plus the
normalization audit. They keep only rows with canonicalized compounds and label
the endpoint separately from the condition field, so endpoint views do not
pollute the default condition graph.

Functional/patient-reported endpoints are retained in the raw extracted claim
details but are not promoted into a standalone graph layer. In practice this
category was too narrow and too ambiguous: wellbeing, quality of life,
functioning, and social connectedness often behave more like contextual outcome
details than stable graph nodes. If we revisit this later, it should be as a
new explicitly defined view rather than as a generic function bucket.

Condition versus symptom routing is row-aware. Generic labels such as
`Depression`, `Anxiety`, and `Pain` are treated as symptom/problem labels rather
than condition nodes. Specific diagnoses or indications, such as major
depressive disorder, treatment-resistant depression, social anxiety disorder,
chronic pain, neuropathic pain, or migraine, remain eligible for the condition
view.

For new search runs, add the completed abstract-screening report to
`data/processed/corpus_manifest.json`, regenerate extraction inputs if needed,
then rerun `python pipeline/kg/build_methods_flow.py --refresh-kg-tables`. The
methods PRISMA flow will update from the manifest-defined corpus and the current
normalized KG claim table without editing UI data by hand.
