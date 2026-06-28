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
RUN_ID=gemini3_flash_YYYYMMDD_first_batch
python pipeline/kg/convert_routed_extractions_to_evidence_rows.py \
  --run-id "$RUN_ID" \
  --input-jsonl "data/processed/extraction/routed_runs/$RUN_ID/route_extraction_outputs.jsonl"
python pipeline/kg/build_evidence_tables.py --source-preset routed --run-id "$RUN_ID"
```

Routed extraction builds are versioned by default under
`data/processed/kg_routed_runs/<RUN_ID>/`. The stable current KG remains under
`data/processed/kg/`; it is rebuilt with:

```bash
python pipeline/kg/build_evidence_tables.py --source-preset current
```

When a reviewed routed run should replace the current KG table, make that
promotion explicit:

```bash
python pipeline/kg/build_evidence_tables.py \
  --source-preset routed \
  --run-id "$RUN_ID" \
  --out-dir data/processed/kg \
  --allow-current-overwrite
```

Each KG output directory contains:

- `papers.parquet`: one row per source paper represented in normalized evidence.
- `entities.parquet`: compounds plus normalized graph entities.
- `claims.parquet`: one rich normalized claim row per projected evidence record.
- `evidence_edges.parquet`: graph-oriented compound-to-entity evidence edges.
- `normalization_audit.parquet`: normalization successes and misses for review.
- `manifest.json`: table counts, source counts, and entity-kind summaries.
- `kg.duckdb`: optional local DuckDB database materialized when the `duckdb`
  Python package is installed.

Author identity is resolved as a separate KG-side layer after `papers.parquet`
exists:

```bash
python pipeline/kg/build_author_tables.py
```

This writes:

- `authors.parquet`: one row per resolved author identity.
- `paper_authors.parquet`: ordered paper-author rows with first/last flags.
- `author_resolution_report.json`: OpenAlex vs fallback resolution counts.
- `openalex_author_cache.json`: cached OpenAlex authorship lookups for rebuilds.

This table layer is the preferred place to build new graph views. The browser UI
should continue to load compact JSON payloads generated from these tables rather
than loading the whole KG directly.

The converter reads route extraction outputs plus `route_extraction_tasks.jsonl`
and keeps one row per extracted finding or review/synthesis item. With
`--run-id`, it writes to
`data/processed/extraction/routed_runs/<RUN_ID>/routed_evidence_rows.json`.
The routed table builder reads the canonical routed evidence row file for the
selected run; the current-source builder does not mix routed extraction rows
into `data/processed/kg/` by accident.

The extraction-to-KG mapping is documented in
`docs/extraction_to_kg_mapping.md`, with the machine-readable mapping in
`schema/extraction_to_kg_mapping.json`. Use that mapping before adding or
renaming extraction fields that are meant to become graph nodes or graph-edge
attributes.

Seed alias vocabularies for newer node kinds are in
`schema/kg_node_vocabularies.json`. The evidence-table builder uses this file
to canonicalize common labels such as `DMN` to `Default mode network` while
pilot outputs reveal which aliases need to be added next.

The current main UI views are driven by `evidence_edges.entity_kind`:

- clinical: conditions, symptoms, safety/adverse events, and outcome scales
  currently have graph rows.
- mechanistic: targets, pathways/processes, biomarkers/readouts, and
  systems/families currently have canonical graph rows.
- routed extension domains: brain regions/networks/circuits, cognitive or
  behavioral constructs, subjective-experience constructs, PK/exposure
  parameters, intervention components, and public-health measures are supported
  by the normalized table layer before they are promoted into dedicated UI
  views.

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
